"""Sensor polling thread for Modbus digital inputs."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from gmdc_common.hardware.io_controller import DemoIOController, IOController

logger = logging.getLogger("gmdc_common.hardware.sensor")


class SensorPoller:
    """
    Polls Modbus digital inputs (FC2 DI by default).

    Crossing sequence used by Mines Entry / checkpoint apps:
      IDLE / validation : sensor FALSE
      After boom open   : truck arrives → sensor TRUE (occupied)
      Truck clears      : sensor FALSE again → falling edge fires callback
                        → app sets TL red and closes boom

    Callbacks fire on falling edge only after a TRUE (occupied) was seen,
    not on rising edge.
    """

    def __init__(
        self,
        io: IOController,
        entry_pin: Optional[int] = 0,
        exit_pin: Optional[int] = None,
        di_start_address: int = 0,
        poll_interval: float = 0.3,
        active_high: bool = True,
        on_entry: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
        on_wb: Optional[Callable[[], None]] = None,
        wb_pin: Optional[int] = None,
        # Rising-edge (occupied) callbacks - used by weighbridge positioning
        on_entry_occupied: Optional[Callable[[], None]] = None,
        on_exit_occupied: Optional[Callable[[], None]] = None,
        on_wb_occupied: Optional[Callable[[], None]] = None,
        on_read_failure: Optional[Callable[[], None]] = None,
        on_read_recovered: Optional[Callable[[], None]] = None,
    ):
        self.io = io
        self.entry_pin = entry_pin
        self.exit_pin = exit_pin
        self.wb_pin = wb_pin
        self.di_start_address = di_start_address
        self.poll_interval = poll_interval
        self.active_high = active_high
        self.on_entry = on_entry
        self.on_exit = on_exit
        self.on_wb = on_wb
        self.on_entry_occupied = on_entry_occupied
        self.on_exit_occupied = on_exit_occupied
        self.on_wb_occupied = on_wb_occupied
        self.on_read_failure = on_read_failure
        self.on_read_recovered = on_read_recovered

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._prev_entry = False
        self._prev_exit = False
        self._prev_wb = False
        self._last_entry = False
        self._last_exit = False
        self._last_wb = False
        # Must see TRUE before a FALSE falling edge counts as "cleared"
        self._entry_occupied = False
        self._exit_occupied = False
        self._wb_occupied = False
        self._read_healthy = True
        self._consecutive_failures = 0

    def _addr(self, pin: int) -> int:
        return self.di_start_address + pin

    def _read_active(self, pin: Optional[int]) -> Optional[bool]:
        """
        Return True/False for beam active, or None when the Modbus read fails.

        Uses the controller's configured read_fc only (via read_discrete_inputs).
        Never falls back to the other function code. Sensors are realtime-only:
        on None the poller clears displayed levels and reconnects — it does not
        keep a stale occupied value.
        """
        if pin is None:
            return False
        addr = self._addr(pin)
        bits = self.io.read_discrete_inputs(addr, 1)
        if bits is None:
            return None
        if not bits:
            return None
        raw = bool(bits[0])
        return raw if self.active_high else not raw

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="SensorPoller", daemon=True
        )
        self._thread.start()
        logger.info(
            "SensorPoller started entry_pin=%s exit_pin=%s wb_pin=%s "
            "di_start=%s interval=%s edge=falling-after-occupied",
            self.entry_pin,
            self.exit_pin,
            self.wb_pin,
            self.di_start_address,
            self.poll_interval,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def reset_edge_state(self) -> None:
        """Clear occupied latch and previous samples (e.g. after force reset)."""
        self._entry_occupied = False
        self._exit_occupied = False
        self._wb_occupied = False
        self._prev_entry = False
        self._prev_exit = False
        self._prev_wb = False

    def _handle_channel(
        self,
        *,
        name: str,
        pin: Optional[int],
        current: bool,
        prev: bool,
        occupied: bool,
        callback: Optional[Callable[[], None]],
        occupied_callback: Optional[Callable[[], None]] = None,
        store: Optional[Callable[[bool], None]] = None,
    ) -> bool:
        """
        Update occupied latch.
        - Rising edge (FALSE→TRUE): optional occupied_callback
        - Falling edge after occupied (TRUE→FALSE): optional clear callback
        The latch is stored before either callback so readers see the new level.
        Returns new occupied flag.
        """
        if pin is None:
            return False

        def publish(value: bool) -> bool:
            if store:
                store(value)
            return value

        if current and not prev:
            occupied = publish(True)
            logger.info(
                "%s sensor TRUE (occupied) addr=%s",
                name,
                self._addr(pin),
            )
            if occupied_callback:
                try:
                    occupied_callback()
                except Exception as e:
                    logger.exception(
                        "%s sensor occupied callback error: %s", name, e
                    )
        elif current and prev and not occupied:
            # Already TRUE but latch unset (startup / after I/O recovery).
            occupied = publish(True)
            logger.info(
                "%s sensor already TRUE (occupied latch sync) addr=%s",
                name,
                self._addr(pin),
            )
            if occupied_callback:
                try:
                    occupied_callback()
                except Exception as e:
                    logger.exception(
                        "%s sensor occupied callback error: %s", name, e
                    )
        elif not current and prev and occupied:
            occupied = publish(False)
            logger.info(
                "%s sensor FALSE (cleared) addr=%s - falling edge",
                name,
                self._addr(pin),
            )
            if callback:
                try:
                    callback()
                except Exception as e:
                    logger.exception("%s sensor clear callback error: %s", name, e)
        return occupied

    def _mark_failure(self) -> None:
        was_healthy = self._read_healthy
        self._consecutive_failures += 1
        self._read_healthy = False
        # Realtime: drop stale levels immediately (no last-value hold).
        # Skip edge callbacks — I/O fault popup + reconnect owns the reaction.
        self._last_entry = False
        self._last_exit = False
        self._last_wb = False
        self._entry_occupied = False
        self._exit_occupied = False
        self._wb_occupied = False
        self._prev_entry = False
        self._prev_exit = False
        self._prev_wb = False
        ensure = getattr(self.io, "ensure_connected", None)
        if callable(ensure):
            try:
                ensure()
            except Exception:
                logger.debug(
                    "ensure_connected after sensor fail raised", exc_info=True
                )
        if was_healthy and self.on_read_failure:
            try:
                self.on_read_failure()
            except Exception:
                logger.exception("on_read_failure callback error")

    def _mark_success(self) -> None:
        was_healthy = self._read_healthy
        self._consecutive_failures = 0
        self._read_healthy = True
        if not was_healthy and self.on_read_recovered:
            try:
                self.on_read_recovered()
            except Exception:
                logger.exception("on_read_recovered callback error")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                entry = self._read_active(self.entry_pin)
                exit_ = self._read_active(self.exit_pin)
                wb = self._read_active(self.wb_pin)

                # Any configured channel returning None is a Modbus failure.
                failed = (
                    (self.entry_pin is not None and entry is None)
                    or (self.exit_pin is not None and exit_ is None)
                    or (self.wb_pin is not None and wb is None)
                )
                if failed:
                    self._mark_failure()
                    self._stop.wait(self.poll_interval)
                    continue

                self._mark_success()
                self._last_entry = bool(entry)
                self._last_exit = bool(exit_)
                self._last_wb = bool(wb)

                self._entry_occupied = self._handle_channel(
                    name="Entry",
                    pin=self.entry_pin,
                    current=self._last_entry,
                    prev=self._prev_entry,
                    occupied=self._entry_occupied,
                    callback=self.on_entry,
                    occupied_callback=self.on_entry_occupied,
                    store=lambda value: setattr(self, "_entry_occupied", value),
                )
                self._exit_occupied = self._handle_channel(
                    name="Exit",
                    pin=self.exit_pin,
                    current=self._last_exit,
                    prev=self._prev_exit,
                    occupied=self._exit_occupied,
                    callback=self.on_exit,
                    occupied_callback=self.on_exit_occupied,
                    store=lambda value: setattr(self, "_exit_occupied", value),
                )
                self._wb_occupied = self._handle_channel(
                    name="WB",
                    pin=self.wb_pin,
                    current=self._last_wb,
                    prev=self._prev_wb,
                    occupied=self._wb_occupied,
                    callback=self.on_wb,
                    occupied_callback=self.on_wb_occupied,
                    store=lambda value: setattr(self, "_wb_occupied", value),
                )

                self._prev_entry = self._last_entry
                self._prev_exit = self._last_exit
                self._prev_wb = self._last_wb
            except Exception as e:
                logger.error("Sensor poll error: %s", e)
                self._mark_failure()
            self._stop.wait(self.poll_interval)

    def simulate_entry(self) -> None:
        """Demo: TRUE then FALSE so falling-after-occupied fires."""
        self._pulse_pin(self.entry_pin, "entry")

    def simulate_exit(self) -> None:
        """Demo: pulse exit, or entry if exit not configured."""
        pin = self.exit_pin if self.exit_pin is not None else self.entry_pin
        self._pulse_pin(pin, "crossing")

    def simulate_wb(self) -> None:
        """Demo: pulse weighbridge sensor."""
        self._pulse_pin(self.wb_pin, "wb")

    def _pulse_pin(self, pin: Optional[int], label: str) -> None:
        if pin is None:
            return
        if isinstance(self.io, DemoIOController):
            addr = self._addr(pin)
            self.io.set_input(addr, True)
            time.sleep(max(self.poll_interval * 2, 0.2))
            self.io.set_input(addr, False)
            # Allow poller to observe falling edge
            time.sleep(max(self.poll_interval * 2, 0.2))
            logger.info("Simulated %s sensor pulse at addr=%s", label, addr)

    def get_status(self) -> dict:
        return {
            "entry_active": self._last_entry,
            "exit_active": self._last_exit,
            "wb_active": self._last_wb,
            "entry_occupied_latch": self._entry_occupied,
            "exit_occupied_latch": self._exit_occupied,
            "wb_occupied_latch": self._wb_occupied,
            "entry_pin": self.entry_pin,
            "exit_pin": self.exit_pin,
            "wb_pin": self.wb_pin,
            "di_start_address": self.di_start_address,
            "edge_mode": "falling_after_occupied",
            "read_healthy": self._read_healthy,
            "consecutive_failures": self._consecutive_failures,
            "entry_addr": (
                self._addr(self.entry_pin) if self.entry_pin is not None else None
            ),
        }
