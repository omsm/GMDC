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
        # Rising-edge (occupied) callbacks — used by weighbridge positioning
        on_entry_occupied: Optional[Callable[[], None]] = None,
        on_exit_occupied: Optional[Callable[[], None]] = None,
        on_wb_occupied: Optional[Callable[[], None]] = None,
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

    def _addr(self, pin: int) -> int:
        return self.di_start_address + pin

    def _read_active(self, pin: Optional[int]) -> bool:
        if pin is None:
            return False
        addr = self._addr(pin)
        bits = self.io.read_discrete_inputs(addr, 1)
        if bits is None:
            bits = self.io.read_coils(addr, 1)
        if not bits:
            return False
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
        """Clear occupied latch (e.g. after force reset to IDLE)."""
        self._entry_occupied = False
        self._exit_occupied = False
        self._wb_occupied = False

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
    ) -> bool:
        """
        Update occupied latch.
        - Rising edge (FALSE→TRUE): optional occupied_callback
        - Falling edge after occupied (TRUE→FALSE): optional clear callback
        Returns new occupied flag.
        """
        if pin is None:
            return False

        if current and not prev:
            occupied = True
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
        elif not current and prev and occupied:
            occupied = False
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

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                entry = self._read_active(self.entry_pin)
                exit_ = self._read_active(self.exit_pin)
                wb = self._read_active(self.wb_pin)
                self._last_entry = entry
                self._last_exit = exit_
                self._last_wb = wb

                self._entry_occupied = self._handle_channel(
                    name="Entry",
                    pin=self.entry_pin,
                    current=entry,
                    prev=self._prev_entry,
                    occupied=self._entry_occupied,
                    callback=self.on_entry,
                    occupied_callback=self.on_entry_occupied,
                )
                self._exit_occupied = self._handle_channel(
                    name="Exit",
                    pin=self.exit_pin,
                    current=exit_,
                    prev=self._prev_exit,
                    occupied=self._exit_occupied,
                    callback=self.on_exit,
                    occupied_callback=self.on_exit_occupied,
                )
                self._wb_occupied = self._handle_channel(
                    name="WB",
                    pin=self.wb_pin,
                    current=wb,
                    prev=self._prev_wb,
                    occupied=self._wb_occupied,
                    callback=self.on_wb,
                    occupied_callback=self.on_wb_occupied,
                )

                self._prev_entry = entry
                self._prev_exit = exit_
                self._prev_wb = wb
            except Exception as e:
                logger.error("Sensor poll error: %s", e)
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
            "entry_addr": (
                self._addr(self.entry_pin) if self.entry_pin is not None else None
            ),
        }
