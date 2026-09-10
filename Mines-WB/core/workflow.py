"""Mines Weighbridge workflow orchestrator (wb_plane.txt)."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.constants import (
    MSG_ANPR_ERR,
    MSG_ANPR_ERR_2,
    MSG_EXIT,
    MSG_FREE_PASS,
    MSG_MOVE_BACKWARD,
    MSG_MOVE_FORWARD,
    MSG_NO_RFID_READ,
    MSG_RFID_ERR,
    MSG_WEIGHING,
    TIMEOUTS,
    Event,
    State,
)
from core.app_context import AppContext
from gmdc_common.hardware.camera import (
    build_top_photo_filename,
    capture_rtsp_snapshot,
    get_local_ip,
)
from services.oci_client import (
    parse_truck_details,
    replace_truck_details_tolerance,
    rto_weight_band,
    under_or_over_type,
    weight_type_error_display,
    weight_within_rto_tolerance,
)
from services.api_errors import (
    extract_api_message,
    is_api_failure,
    is_service_alert,
)
from services.frontend_mqtt import (
    STEP_EXIT_COMPLETED,
    STEP_EXIT_START,
    STEP_READING_WEIGHT,
    STEP_RFID_READ,
    STEP_VALIDATING_ANPR,
    STEP_VALIDATING_RFID,
    STEP_VALIDATING_WEIGHT,
    STEP_VEHICLE_ENTERING,
)

logger = logging.getLogger("mines_wb.core.workflow")

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"


class MinesWbWorkflow:
    """
    IDLE → POSITIONING → WEIGHT → RFID → ANPR → FINAL_WEIGHT/IMAGES
         → WEIGHT_DETAILS → EXIT_GRANTED → IDLE
    """

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self._worker_lock = threading.Lock()
        self._manual_stop = threading.Event()
        self._pos_timer: Optional[threading.Timer] = None
        self._weight_timer: Optional[threading.Timer] = None
        self._rfid_timer: Optional[threading.Timer] = None
        self._exit_timer: Optional[threading.Timer] = None
        self._rfid_err_timer: Optional[threading.Timer] = None
        self._forward_timer: Optional[threading.Timer] = None
        self._boom_close_timer: Optional[threading.Timer] = None
        self._idle_s2_s3_timer: Optional[threading.Timer] = None
        self._backward_timer: Optional[threading.Timer] = None
        self._timer_lock = threading.Lock()
        self._rfid_control_lock = threading.Lock()
        self._awaiting_rfid = False
        self._forward_loop_active = False
        self._idle_s2_s3_loop_active = False
        self._backward_loop_active = False
        self._rfid_started_direction = ""
        self._pending_rfid_tags: Optional[tuple[List[str], List[dict]]] = None
        self._status_check_alerted = False

    def _collect_reset_fields(self) -> tuple[str, str, str]:
        settings = self.ctx.settings
        device_ip = str(getattr(settings, "device_ip", "") or "") if settings else ""
        txn = self.ctx.transactions
        rfid = ""
        details = ""
        if txn is not None:
            rfid = str(getattr(txn, "rfid", "") or "")
            if not rfid:
                tags = list(getattr(txn, "tags", None) or [])
                if tags:
                    rfid = str(tags[0] or "")
            details = str(getattr(txn, "truck_details", "") or "")
        return device_ip, rfid, details

    def _notify_gmdc_reset(self, *, manual: bool = False) -> None:
        """POST reset_checkpoint only for the operator Reset button."""
        oci = self.ctx.oci
        if oci is None or not hasattr(oci, "reset_checkpoint"):
            return
        device_ip, rfid, details = self._collect_reset_fields()
        if not rfid and not details:
            logger.info("reset_checkpoint skipped - no RFID/truck_details")
            return
        if not device_ip:
            logger.warning("reset_checkpoint skipped - device_ip missing")
            return
        logger.info(
            "Notifying GMDC reset device_ip=%s rfid=%s has_details=%s manual=%s",
            device_ip,
            rfid or "(empty)",
            bool(details),
            manual,
        )
        try:
            resp = oci.reset_checkpoint(
                device_ip=device_ip,
                rfid_no=rfid,
                truck_details=details,
            )
        except Exception:
            logger.exception("reset_checkpoint call failed")
            return
        if is_api_failure(resp):
            self._ui_api_failure(
                STEP_VEHICLE_ENTERING,
                resp,
                fallback="Reset service not reachable",
            )

    def notify_gmdc_reset(self) -> None:
        """No-op. reset_checkpoint is only posted from the UI Reset button."""
        logger.info("startup reset_checkpoint skipped - UI Reset only")

    # ------------------------------------------------------------------
    # Hardware helpers
    # ------------------------------------------------------------------
    def apply_idle_hardware(self, delay_exit_boom_close: bool = False) -> None:
        """
        Entry green + open; exit red + closed; clear display.

        ``delay_exit_boom_close`` holds the exit boom up for
        ``TIMEOUTS.BOOM_CLOSE_DELAY_SEC`` so a truck that just cleared the exit
        sensor is fully past the barrier before it drops.
        """
        # Forward loop already stopped by caller; do not purge error clips here
        if self.ctx.entry_tl:
            self.ctx.entry_tl.set_green()
        if self.ctx.exit_tl:
            self.ctx.exit_tl.set_red()
        if self.ctx.entry_boom:
            self.ctx.entry_boom.open()
        if delay_exit_boom_close:
            self._schedule_exit_boom_close()
        else:
            self._cancel_timer("_boom_close_timer")
            if self.ctx.exit_boom:
                self.ctx.exit_boom.close()
        if self.ctx.display:
            self.ctx.display.clear()
        fe = self._frontend()
        if fe:
            fe.reset_idle()
        else:
            self._ui_devices()
        self._stop_rfid_reader()
        logger.info(
            "Hardware reset to IDLE (entry green/open, exit red, exit boom %s)",
            (
                f"closing in {TIMEOUTS.BOOM_CLOSE_DELAY_SEC}s"
                if delay_exit_boom_close
                else "closed"
            ),
        )

    def _schedule_exit_boom_close(self) -> None:
        """Close the exit boom after the post-crossing delay."""
        if not self.ctx.exit_boom:
            return

        def _close():
            boom = self.ctx.exit_boom
            if boom:
                boom.close()
                logger.info(
                    "Exit boom closed after %ss crossing delay",
                    TIMEOUTS.BOOM_CLOSE_DELAY_SEC,
                )
                self._ui_devices()

        self._arm_timer(
            "_boom_close_timer", TIMEOUTS.BOOM_CLOSE_DELAY_SEC, _close
        )

    def _set_entry_closed(self) -> None:
        if self.ctx.entry_tl:
            self.ctx.entry_tl.set_red()
        if self.ctx.entry_boom:
            self.ctx.entry_boom.close()
        self._ui_devices()

    def _grant_exit_hardware(self) -> None:
        # A pending post-crossing close must not drop the boom on this truck.
        self._cancel_timer("_boom_close_timer")
        if self.ctx.exit_tl:
            self.ctx.exit_tl.set_green()
        if self.ctx.exit_boom:
            self.ctx.exit_boom.open()
        if self.ctx.display:
            self.ctx.display.send(MSG_EXIT)
        fe = self._frontend()
        if fe:
            fe.publish_display(MSG_EXIT)
            fe.publish_device_status()
        logger.info("Exit granted (exit green/open)")

    def _frontend(self):
        return getattr(self.ctx, "frontend", None)

    def _ui_status(
        self,
        step: str,
        status: str,
        message: str,
        *,
        popup: bool = False,
        popup_title: str = "",
        countdown_sec: Optional[float] = None,
    ) -> None:
        fe = self._frontend()
        if fe:
            fe.publish_status(
                step,
                status,
                message,
                popup=popup,
                popup_title=popup_title,
                countdown_sec=countdown_sec,
            )

    def _ui_api_failure(
        self, step: str, resp: Any, *, fallback: str = ""
    ) -> None:
        msg = str(
            getattr(resp, "operator_message", "")
            or extract_api_message(resp)
            or fallback
            or "Service failed"
        )
        popup = is_service_alert(resp)
        title = str(getattr(resp, "popup_title", "") or "")
        if popup and not title:
            title = "SERVICE ERROR"
        self._ui_status(step, "error", msg, popup=popup, popup_title=title)

    def _anpr_wait_message(self, txn: Any) -> str:
        try:
            status = int(getattr(txn, "anpr_status", 0) or 0)
        except (TypeError, ValueError):
            status = 0
        if status == 2:
            return "ANPR Err-2, Number not readable"
        return "ANPR Err-0, Number plate mismatch"

    def _ui_anpr_waiting(self, txn: Any) -> None:
        self._ui_status(
            STEP_VALIDATING_ANPR,
            "warning",
            self._anpr_wait_message(txn),
        )

    def _ui_result_failure(
        self, step: str, result: Dict[str, Any], *, fallback: str = ""
    ) -> None:
        msg = str(
            result.get("operator_message")
            or result.get("message")
            or fallback
            or "Service failed"
        )
        if any(
            marker in msg.lower()
            for marker in (
                "httpconnectionpool",
                "max retries exceeded",
                "traceback",
            )
        ):
            msg = fallback or "Service failed"
        popup = bool(result.get("popup"))
        title = str(result.get("popup_title") or "")
        if popup and not title:
            title = "SERVICE ERROR"
        self._ui_status(step, "error", msg, popup=popup, popup_title=title)

    def _ui_position(self, position: int) -> None:
        fe = self._frontend()
        if fe:
            fe.publish_position(position)

    def _ui_devices(self) -> None:
        fe = self._frontend()
        if fe:
            fe.publish_device_status()

    def _announce(self, msg: str) -> None:
        """Display text + mapped voice (wb-old style)."""
        display = self.ctx.display
        if display:
            display.send(msg)
        fe = self._frontend()
        if fe:
            fe.publish_display(msg)
        logger.info("Announce: %s", msg)

    def _voice(self):
        return self.ctx.voice

    def _start_move_forward_announcement(self, play_immediately: bool = True) -> None:
        """Play forward.wav immediately, then every 5s (legacy continuous)."""
        self._stop_move_forward_announcement(stop_audio=False)
        self._forward_loop_active = True
        if play_immediately:
            self._play_move_forward_once()
        self._schedule_forward_loop()

    def _play_move_forward_once(self) -> None:
        voice = self._voice()
        if not voice:
            return
        # Defer only while a real multi-clip sequence is playing.
        check = getattr(voice, "is_multi_play_active", None)
        if callable(check) and check() is True:
            return
        voice.move_forward()

    def _schedule_forward_loop(self) -> None:
        if not self._forward_loop_active:
            return

        def _tick():
            if not self._forward_loop_active:
                return
            sm = self.ctx.state_machine
            if not sm or sm.current_state not in (
                State.VEHICLE_POSITIONING,
                State.EXIT_GRANTED,
                State.WAIT_EXIT,
                State.FREE_PASS,
            ):
                self._forward_loop_active = False
                return
            self._play_move_forward_once()
            self._schedule_forward_loop()

        self._cancel_timer("_forward_timer")
        timer = threading.Timer(TIMEOUTS.MOVE_FORWARD_INTERVAL_SEC, _tick)
        timer.daemon = True
        with self._timer_lock:
            self._forward_timer = timer
        timer.start()

    def _stop_move_forward_announcement(self, stop_audio: bool = True) -> None:
        self._forward_loop_active = False
        self._cancel_timer("_forward_timer")
        if stop_audio:
            voice = self._voice()
            if voice:
                voice.stop()

    def _wb_and_exit_occupied(self) -> bool:
        poller = getattr(self.ctx, "sensor_poller", None)
        if not poller or not hasattr(poller, "get_status"):
            return False
        st = poller.get_status() or {}
        wb = bool(st.get("wb_active") or st.get("wb_occupied_latch"))
        exit_ = bool(st.get("exit_active") or st.get("exit_occupied_latch"))
        return wb and exit_

    def _start_idle_s2_s3_announcement(self) -> None:
        """Play weighbridge_0.wav while IDLE with platform (s2) and exit (s3) cut."""
        if self._idle_s2_s3_loop_active:
            return
        self._idle_s2_s3_loop_active = True
        self._play_idle_s2_s3_once()
        self._schedule_idle_s2_s3_loop()

    def _play_idle_s2_s3_once(self) -> None:
        voice = self._voice()
        if not voice:
            return
        play = getattr(voice, "weighbridge_0", None) or getattr(
            voice, "check_weighbridge", None
        )
        if callable(play):
            play()

    def _schedule_idle_s2_s3_loop(self) -> None:
        if not self._idle_s2_s3_loop_active:
            return

        def _tick():
            sm = self.ctx.state_machine
            if (
                not self._idle_s2_s3_loop_active
                or not sm
                or sm.current_state != State.IDLE
                or not self._wb_and_exit_occupied()
            ):
                self._stop_idle_s2_s3_announcement(stop_audio=False)
                return
            self._play_idle_s2_s3_once()
            self._schedule_idle_s2_s3_loop()

        self._cancel_timer("_idle_s2_s3_timer")
        timer = threading.Timer(TIMEOUTS.MOVE_FORWARD_INTERVAL_SEC, _tick)
        timer.daemon = True
        with self._timer_lock:
            self._idle_s2_s3_timer = timer
        timer.start()

    def _stop_idle_s2_s3_announcement(self, stop_audio: bool = False) -> None:
        self._idle_s2_s3_loop_active = False
        self._cancel_timer("_idle_s2_s3_timer")
        if stop_audio:
            voice = self._voice()
            if voice:
                voice.stop()

    def _maybe_announce_idle_s2_s3(self) -> bool:
        """True when IDLE and s2+s3 are cut (announcement started)."""
        sm = self.ctx.state_machine
        if not sm or sm.current_state != State.IDLE:
            self._stop_idle_s2_s3_announcement()
            return False
        if not self._wb_and_exit_occupied():
            self._stop_idle_s2_s3_announcement()
            return False
        self._start_idle_s2_s3_announcement()
        return True

    def _sensor_cut(self, which: str) -> bool:
        poller = getattr(self.ctx, "sensor_poller", None)
        if not poller or not hasattr(poller, "get_status"):
            return False
        st = poller.get_status() or {}
        if which == "wb":
            return bool(st.get("wb_active") or st.get("wb_occupied_latch"))
        if which == "exit":
            return bool(st.get("exit_active") or st.get("exit_occupied_latch"))
        return False

    def _start_backward_announcement(self) -> None:
        """Play backward.wav while positioning with exit (s3) cut."""
        if self._backward_loop_active:
            return
        self._stop_move_forward_announcement(stop_audio=True)
        self._backward_loop_active = True
        self._announce(MSG_MOVE_BACKWARD)
        self._ui_status(
            STEP_VEHICLE_ENTERING,
            "warning",
            "Move back - only the platform sensor should be occupied.",
        )
        self._play_backward_once()
        self._schedule_backward_loop()

    def _play_backward_once(self) -> None:
        voice = self._voice()
        if not voice:
            return
        play = getattr(voice, "move_backward", None)
        if callable(play):
            play()

    def _schedule_backward_loop(self) -> None:
        if not self._backward_loop_active:
            return

        def _tick():
            sm = self.ctx.state_machine
            if (
                not self._backward_loop_active
                or not sm
                or sm.current_state != State.VEHICLE_POSITIONING
                or not self._sensor_cut("exit")
            ):
                self._stop_backward_announcement(stop_audio=False)
                return
            self._play_backward_once()
            self._schedule_backward_loop()

        self._cancel_timer("_backward_timer")
        timer = threading.Timer(TIMEOUTS.MOVE_FORWARD_INTERVAL_SEC, _tick)
        timer.daemon = True
        with self._timer_lock:
            self._backward_timer = timer
        timer.start()

    def _stop_backward_announcement(self, stop_audio: bool = False) -> None:
        self._backward_loop_active = False
        self._cancel_timer("_backward_timer")
        if stop_audio:
            voice = self._voice()
            if voice:
                voice.stop()

    # ------------------------------------------------------------------
    # RFID cloud
    # ------------------------------------------------------------------
    def _is_bidirectional(self) -> bool:
        settings = self.ctx.settings
        return bool(
            settings
            and str(getattr(settings, "wb_type", "")).strip().lower()
            == "bidirectional"
        )

    def _active_direction_key(self) -> str:
        txn = self.ctx.transactions
        direction = str(getattr(txn, "direction", "") or "").strip().upper()
        return "entry_b" if direction == "ENTRY_B" else "entry_a"

    def _active_rfid_cloud(self):
        key = self._active_direction_key()
        cloud = self.ctx.rfid_clouds.get(key)
        if cloud is None and key == "entry_a":
            cloud = self.ctx.rfid_cloud
        return key, cloud

    def _stop_rfid_reader(self) -> None:
        with self._rfid_control_lock:
            clouds = dict(self.ctx.rfid_clouds)
            if not clouds and self.ctx.rfid_cloud:
                clouds["entry_a"] = self.ctx.rfid_cloud
            for direction, cloud in clouds.items():
                ok = cloud.stop()
                logger.info(
                    "RFID cloud stop direction=%s ok=%s", direction, ok
                )
            self._rfid_started_direction = ""
            self.ctx.active_rfid_direction = ""

    def stop_all_rfid_readers(self) -> None:
        """Login and stop every configured fixed reader (startup/shutdown safety)."""
        with self._rfid_control_lock:
            clouds = dict(self.ctx.rfid_clouds)
            if not clouds and self.ctx.rfid_cloud:
                clouds["entry_a"] = self.ctx.rfid_cloud
            for direction, cloud in clouds.items():
                login_ok = cloud.login()
                ok = cloud.stop() if login_ok else False
                logger.info(
                    "RFID cloud force-stop direction=%s login=%s stop=%s",
                    direction,
                    login_ok,
                    ok,
                )
            self._rfid_started_direction = ""
            self.ctx.active_rfid_direction = ""

    def _start_rfid_reader(self) -> None:
        key, cloud = self._active_rfid_cloud()
        if not cloud:
            logger.debug(
                "RFID cloud not configured direction=%s - tags via HTTP only",
                key,
            )
            return
        with self._rfid_control_lock:
            if self._rfid_started_direction == key:
                logger.debug("RFID cloud already scanning direction=%s", key)
                return
            # Ensure the opposite direction cannot continue scanning.
            for other_key, other in self.ctx.rfid_clouds.items():
                if other_key == key:
                    continue
                login_ok = other.login()
                stop_ok = other.stop() if login_ok else False
                logger.info(
                    "RFID opposite stop direction=%s login=%s stop=%s",
                    other_key,
                    login_ok,
                    stop_ok,
                )
            ok = cloud.prepare_idle()
            self._rfid_started_direction = key if ok else ""
            self.ctx.active_rfid_direction = key if ok else ""
            logger.info(
                "RFID cloud start direction=%s (login/mode/start) ok=%s",
                key,
                ok,
            )

    def _start_rfid_reader_async(self) -> None:
        threading.Thread(
            target=self._start_rfid_reader,
            name=f"RFIDStart-{self._active_direction_key()}",
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------
    def _cancel_timer(self, attr: str) -> None:
        with self._timer_lock:
            t = getattr(self, attr, None)
            if t:
                t.cancel()
                setattr(self, attr, None)

    def _cancel_all_timers(self) -> None:
        self._forward_loop_active = False
        self._idle_s2_s3_loop_active = False
        self._backward_loop_active = False
        for name in (
            "_pos_timer",
            "_weight_timer",
            "_rfid_timer",
            "_exit_timer",
            "_rfid_err_timer",
            "_forward_timer",
            "_boom_close_timer",
            "_idle_s2_s3_timer",
            "_backward_timer",
        ):
            self._cancel_timer(name)

    def _arm_timer(self, attr: str, delay: float, fn) -> None:
        self._cancel_timer(attr)
        timer = threading.Timer(delay, fn)
        timer.daemon = True
        with self._timer_lock:
            setattr(self, attr, timer)
        timer.start()

    # ------------------------------------------------------------------
    # Public sensor / RFID entry points
    # ------------------------------------------------------------------
    def _begin_vehicle_positioning(self, direction: str) -> None:
        sm = self.ctx.state_machine
        if not sm or not sm.trigger(Event.ENTRY_SENSOR):
            return
        self._stop_idle_s2_s3_announcement()
        if self.ctx.transactions:
            self.ctx.transactions.begin()
            self.ctx.transactions.direction = direction
        self.ctx.active_rfid_direction = ""
        self._pending_rfid_tags = None
        # Sensor occupied (edge or already active): announce inspection and
        # do not start RFID. Reader starts only after weight > minimum.
        self._stop_rfid_reader()
        voice = self._voice()
        #if voice:
        #    voice.weighbridge_janch()
        self._announce(MSG_MOVE_FORWARD)
        self._start_move_forward_announcement()
        self._arm_timer(
            "_pos_timer",
            TIMEOUTS.POSITIONING_SEC,
            self._on_positioning_timeout,
        )
        logger.info(
            "VEHICLE_POSITIONING started direction=%s rfid=%s",
            direction,
            direction.lower(),
        )
        self._ui_position(1)
        self._ui_status(
            STEP_VEHICLE_ENTERING,
            "info",
            "Vehicle approaching weighbridge - move forward.",
        )
        self._ui_devices()

    def on_entry_occupied(self) -> None:
        sm = self.ctx.state_machine
        if not sm:
            return
        if sm.current_state == State.FREE_PASS:
            return
        if sm.current_state != State.IDLE:
            return
        if not self._worker_lock.acquire(blocking=False):
            return
        try:
            self._begin_vehicle_positioning("ENTRY_A")
        finally:
            self._worker_lock.release()

    def on_entry_cleared(self) -> None:
        """ENTRY_B exit complete: uncut → cut → uncut on the entry sensor."""
        sm = self.ctx.state_machine
        if not sm:
            return
        if (
            self._is_bidirectional()
            and sm.current_state in (State.EXIT_GRANTED, State.WAIT_EXIT)
            and getattr(self.ctx.transactions, "direction", "") == "ENTRY_B"
        ):
            self._complete_lane_exit("ENTRY sensor cleared - ENTRY_B vehicle crossed")
            return

    def on_wb_occupied(self) -> None:
        sm = self.ctx.state_machine
        if not sm or sm.current_state == State.FREE_PASS:
            return
        if sm.current_state == State.IDLE:
            self._maybe_announce_idle_s2_s3()
            return
        if sm.current_state != State.VEHICLE_POSITIONING:
            return
        if self._sensor_cut("exit"):
            logger.info("WB occupied while exit (s3) cut - wait for reverse")
            self._start_backward_announcement()
            return
        self._stop_backward_announcement()
        if not self._worker_lock.acquire(blocking=False):
            return

        def _run():
            try:
                self._weight_capture_cycle()
            finally:
                self._worker_lock.release()

        threading.Thread(target=_run, name="WeightCycle", daemon=True).start()

    def on_exit_occupied(self) -> None:
        """Bidirectional ENTRY_B approach, or IDLE s2+s3 error voice."""
        sm = self.ctx.state_machine
        if not sm:
            return
        if sm.current_state == State.FREE_PASS:
            return
        if sm.current_state == State.VEHICLE_POSITIONING:
            logger.info("Exit (s3) cut during positioning - move backward")
            self._start_backward_announcement()
            return
        if sm.current_state == State.IDLE:
            if self._maybe_announce_idle_s2_s3():
                return
            if self._is_bidirectional():
                if not self._worker_lock.acquire(blocking=False):
                    return
                try:
                    self._begin_vehicle_positioning("ENTRY_B")
                finally:
                    self._worker_lock.release()
            return

    def on_exit_cleared(self) -> None:
        """
        Vehicle fully crossed the exit sensor (uncut → cut → uncut).
        Then reset IDLE and close the boom after the delay.
        """
        sm = self.ctx.state_machine
        if not sm:
            return
        if sm.current_state == State.FREE_PASS:
            self._complete_lane_exit(
                "EXIT sensor cleared - free pass complete",
                success_message="Free pass complete - vehicle exited.",
            )
            return
        if sm.current_state == State.IDLE:
            self._stop_idle_s2_s3_announcement()
            return
        if sm.current_state == State.VEHICLE_POSITIONING:
            self._stop_backward_announcement(stop_audio=True)
            if self._sensor_cut("wb"):
                logger.info("Exit (s3) cleared and platform (s2) occupied - weigh")
                self.on_wb_occupied()
            else:
                self._announce(MSG_MOVE_FORWARD)
                self._ui_status(
                    STEP_VEHICLE_ENTERING,
                    "info",
                    "Vehicle approaching weighbridge - move forward.",
                )
                self._start_move_forward_announcement()
            return
        if sm.current_state not in (State.EXIT_GRANTED, State.WAIT_EXIT):
            return
        if (
            self._is_bidirectional()
            and getattr(self.ctx.transactions, "direction", "") == "ENTRY_B"
        ):
            # ENTRY_B completes at the entry sensor after uncut → cut → uncut.
            return
        self._complete_lane_exit("EXIT sensor cleared - vehicle crossed")

    def _complete_lane_exit(
        self, reason: str, success_message: str = "Vehicle exit completed."
    ) -> None:
        logger.info("%s - resetting to IDLE", reason)
        self._ui_position(5)
        # Keep the failure cascade red until idle reset; do not paint exit green.
        exit_status = "error" if self._ui_had_flow_failure() else "success"
        self._ui_status(STEP_EXIT_COMPLETED, exit_status, success_message)
        self._ui_devices()
        self.force_reset(delay_boom_close=True)

    def _ui_had_flow_failure(self) -> bool:
        """True when the current cycle already published a red step failure."""
        fe = self._frontend()
        if not fe:
            return False
        st = getattr(fe, "last_status", None) or {}
        return str(st.get("status") or "").lower() == "error"

    def on_rfid_tags(
        self, id_hexes: List[str], raw_tags: Optional[List[dict]] = None
    ) -> None:
        sm = self.ctx.state_machine
        if id_hexes:
            # First action for every reader push: stop scanning immediately.
            self._stop_rfid_reader()
        if (
            sm
            and sm.current_state
            in (State.VEHICLE_POSITIONING, State.WEIGHT_CAPTURE)
        ):
            logger.info(
                "Ignoring RFID tags until after weight (state=%s)",
                sm.current_state.name,
            )
            return
        if not sm or sm.current_state != State.RFID_READ:
            logger.warning(
                "Ignoring RFID tags in state %s",
                sm.current_state.name if sm else "?",
            )
            return
        if not id_hexes:
            return
        if not self._awaiting_rfid:
            return
        if not self._worker_lock.acquire(blocking=False):
            logger.warning("Workflow busy - ignoring RFID")
            return

        def _run():
            try:
                self._rfid_and_beyond(id_hexes, raw_tags or [])
            finally:
                self._worker_lock.release()

        threading.Thread(target=_run, name="RFIDCycle", daemon=True).start()

    def on_rfid_from_mobile(self, rfid: str) -> Dict[str, Any]:
        """Handheld fallback during RFID_READ - validate and continue."""
        sm = self.ctx.state_machine
        oci = self.ctx.oci
        settings = self.ctx.settings
        if not sm or not oci or not settings:
            raise RuntimeError("Workflow not ready")
        if sm.current_state != State.RFID_READ:
            raise RuntimeError(
                f"Ignoring mobile RFID while in state {sm.current_state.name}"
            )

        resp = oci.validate_rfid(rfid, settings.device_ip)
        body = dict(resp.raw) if resp.raw else {
            "status": resp.status,
            "message": resp.message,
            "truck_details": resp.truck_details,
        }

        if not self._worker_lock.acquire(blocking=False):
            raise RuntimeError("Workflow busy")

        self._awaiting_rfid = False
        self._cancel_timer("_rfid_timer")

        def _run():
            try:
                if resp.ok:
                    self._stop_rfid_reader()
                    self._apply_valid_rfid(rfid, resp.truck_details)
                    sm.trigger(Event.RFID_RECEIVED)
                    sm.trigger(Event.RFID_VALID)
                    self._after_rfid_valid()
                else:
                    self._rfid_and_beyond([rfid], [])
            finally:
                self._worker_lock.release()

        threading.Thread(target=_run, name="MobileRFID", daemon=True).start()
        return body

    def force_reset(
        self,
        announce_reset: bool = False,
        stop_audio: bool = True,
        delay_boom_close: bool = False,
        notify_gmdc: Optional[bool] = None,
        manual: bool = False,
    ) -> None:
        logger.info("Force reset to IDLE")
        if announce_reset:
            self._notify_gmdc_reset(manual=True)
        self._manual_stop.set()
        self._awaiting_rfid = False
        self._pending_rfid_tags = None
        self._cancel_all_timers()
        self._stop_move_forward_announcement(stop_audio=False)
        self._stop_idle_s2_s3_announcement(stop_audio=False)
        self._stop_backward_announcement(stop_audio=False)
        sm = self.ctx.state_machine
        if sm:
            sm.trigger(Event.RESET)
            sm.force_state(State.IDLE)
        if self.ctx.transactions:
            self.ctx.transactions.clear()
        if self.ctx.sensor_poller and hasattr(
            self.ctx.sensor_poller, "reset_edge_state"
        ):
            self.ctx.sensor_poller.reset_edge_state()
        self.apply_idle_hardware(delay_exit_boom_close=delay_boom_close)
        voice = self._voice()
        if announce_reset and voice:
            voice.application_reset()
        elif stop_audio and voice:
            voice.stop()
        self._manual_stop.clear()

    def start_free_pass(self) -> None:
        """Open every traffic light and boom; IDLE after exit sensor uncut→cut→uncut."""
        logger.info("Free pass - opening all traffic lights and boom barriers")
        self._manual_stop.set()
        self._awaiting_rfid = False
        self._pending_rfid_tags = None
        self._cancel_all_timers()
        self._stop_move_forward_announcement(stop_audio=True)
        self._stop_rfid_reader()
        sm = self.ctx.state_machine
        if sm:
            sm.force_state(State.FREE_PASS)
        if self.ctx.transactions:
            self.ctx.transactions.clear()
        if self.ctx.sensor_poller and hasattr(
            self.ctx.sensor_poller, "reset_edge_state"
        ):
            self.ctx.sensor_poller.reset_edge_state()
        self._cancel_timer("_boom_close_timer")
        if self.ctx.entry_tl:
            self.ctx.entry_tl.set_green()
        if self.ctx.exit_tl:
            self.ctx.exit_tl.set_green()
        if self.ctx.entry_boom:
            self.ctx.entry_boom.open()
        if self.ctx.exit_boom:
            self.ctx.exit_boom.open()
        if self.ctx.display:
            self.ctx.display.send(MSG_FREE_PASS)
        fe = self._frontend()
        if fe:
            fe.publish_display(MSG_FREE_PASS)
            fe.publish_position(4)
            fe.publish_status(
                STEP_EXIT_START,
                "info",
                "Free pass - all lights green, all booms open. Waiting for exit sensor.",
            )
            fe.publish_device_status()
        self._start_move_forward_announcement()
        self._manual_stop.clear()

    # ------------------------------------------------------------------
    # Timeout handlers
    # ------------------------------------------------------------------
    def _on_positioning_timeout(self) -> None:
        sm = self.ctx.state_machine
        if sm and sm.current_state == State.VEHICLE_POSITIONING:
            logger.warning("Positioning timeout - reset IDLE")
            self._stop_move_forward_announcement()
            self._stop_backward_announcement()
            voice = self._voice()
            if voice:
                voice.rescan_card_entry_timeout()
            sm.trigger(Event.POSITIONING_TIMEOUT)
            self.force_reset(stop_audio=False)

    def _on_weight_timeout(self) -> None:
        sm = self.ctx.state_machine
        if sm and sm.current_state == State.WEIGHT_CAPTURE:
            logger.warning("Weight capture timeout - reset IDLE")
            sm.trigger(Event.WEIGHT_TIMEOUT)
            self.force_reset()

    def _on_rfid_timeout(self) -> None:
        sm = self.ctx.state_machine
        if sm and sm.current_state == State.RFID_READ:
            logger.warning("RFID collect timeout")
            self._awaiting_rfid = False
            sm.trigger(Event.RFID_TIMEOUT)
            voice = self._voice()
            if voice:
                voice.rfid_not_found()
            self._enter_rfid_error(
                message=MSG_NO_RFID_READ,
                step=STEP_RFID_READ,
            )

    def _on_exit_timeout(self) -> None:
        sm = self.ctx.state_machine
        if sm and sm.current_state in (State.EXIT_GRANTED, State.WAIT_EXIT):
            logger.warning("Exit wait timeout - reset IDLE")
            sm.trigger(Event.EXIT_TIMEOUT)
            self.force_reset()

    def _on_rfid_error_timeout(self) -> None:
        sm = self.ctx.state_machine
        if sm and sm.current_state == State.RFID_ERROR:
            logger.info("RFID error display done - grant exit to clear lane")
            sm.trigger(Event.RFID_ERROR_TIMEOUT)
            self._enter_exit_granted(reason="rfid_error")

    # ------------------------------------------------------------------
    # Weight capture
    # ------------------------------------------------------------------
    def _weight_capture_cycle(self) -> None:
        sm = self.ctx.state_machine
        settings = self.ctx.settings
        digitizer = self.ctx.digitizer
        assert sm and settings and digitizer

        self._cancel_timer("_pos_timer")
        if not sm.trigger(Event.WB_SENSOR):
            return

        self._stop_move_forward_announcement()
        self._stop_backward_announcement()
        self._announce(MSG_WEIGHING)
        self._ui_position(2)
        self._ui_status(
            STEP_READING_WEIGHT, "info", "Vehicle on platform - capturing weight."
        )
        self._ui_devices()
        voice = self._voice()
        # if voice:
        #     voice.weighbridge_janch()
        self._set_entry_closed()
        self._arm_timer(
            "_weight_timer",
            TIMEOUTS.WEIGHT_CAPTURE_SEC,
            self._on_weight_timeout,
        )

        result = digitizer.read_stable_weight()
        self._cancel_timer("_weight_timer")
        weight = result.get("weight")
        logger.info("Digitizer result ok=%s weight=%s", result.get("ok"), weight)

        if weight is None or not result.get("ok"):
            if voice:
                voice.digitizer_error()
            self._ui_result_failure(
                STEP_READING_WEIGHT,
                result,
                fallback="Digitizer failed",
            )
            sm.trigger(Event.WEIGHT_FAIL)
            self.force_reset()
            return

        min_kg = settings.min_weight_kg or TIMEOUTS.MIN_WEIGHT_KG
        if self.ctx.transactions:
            self.ctx.transactions.weight_kg = float(weight)
        fe = self._frontend()
        if fe:
            fe.publish_digitizer(weight)

        if float(weight) <= min_kg:
            logger.warning("Weight %.1f kg <= min %.1f - reset", weight, min_kg)
            if voice:
                voice.check_weighbridge()
            sm.trigger(Event.WEIGHT_LOW)
            self.force_reset()
            return

        sm.trigger(Event.WEIGHT_OK)
        self._enter_rfid_read()

    def _enter_rfid_read(self) -> None:
        sm = self.ctx.state_machine
        assert sm
        self._awaiting_rfid = True
        self._start_rfid_reader()
        if self._pending_rfid_tags:
            id_hexes, raw_tags = self._pending_rfid_tags
            self._pending_rfid_tags = None
            logger.info(
                "Using buffered RFID tags direction=%s count=%s",
                getattr(self.ctx.transactions, "direction", ""),
                len(id_hexes),
            )
            self._rfid_and_beyond(id_hexes, raw_tags)
            return
        collect_sec = float(TIMEOUTS.RFID_COLLECT_TIMEOUT_SEC)
        self._arm_timer(
            "_rfid_timer",
            collect_sec,
            self._on_rfid_timeout,
        )
        logger.info(
            "RFID_READ - waiting for tags via /rfid_data (timeout=%.0fs)",
            collect_sec,
        )
        self._ui_position(0)
        self._ui_status(
            STEP_RFID_READ,
            "info",
            "Reading RFID at platform; present a valid tag.",
            countdown_sec=collect_sec,
        )

    # ------------------------------------------------------------------
    # RFID + ANPR + details
    # ------------------------------------------------------------------
    def _rfid_and_beyond(
        self, id_hexes: List[str], raw_tags: List[dict]
    ) -> None:
        sm = self.ctx.state_machine
        oci = self.ctx.oci
        settings = self.ctx.settings
        txn = self.ctx.transactions
        assert sm and oci and settings and txn

        self._awaiting_rfid = False
        self._cancel_timer("_rfid_timer")
        sm.trigger(Event.RFID_RECEIVED)
        self._stop_rfid_reader()

        txn.tags = list(id_hexes)
        valid = False
        service_alert = None
        last_resp = None
        for tag in id_hexes:
            logger.info("Validating RFID %s", tag)
            resp = oci.validate_rfid(tag, settings.device_ip)
            last_resp = resp
            if is_api_failure(resp):
                service_alert = resp
                break
            if resp.ok:
                self._apply_valid_rfid(tag, resp.truck_details)
                valid = True
                break

        if service_alert is not None:
            sm.trigger(Event.RFID_INVALID)
            voice = self._voice()
            if voice:
                voice.rfid_api_error()
            self._stop_rfid_reader()
            self._announce(MSG_RFID_ERR)
            self._ui_api_failure(
                STEP_VALIDATING_RFID,
                service_alert,
                fallback="RFID service not reachable",
            )
            self._arm_timer(
                "_rfid_err_timer",
                TIMEOUTS.RFID_ERROR_DISPLAY_SEC,
                self._on_rfid_error_timeout,
            )
            return

        if not valid:
            sm.trigger(Event.RFID_INVALID)
            voice = self._voice()
            if voice:
                voice.rfid_api_error()
            api_msg = ""
            if last_resp is not None:
                api_msg = str(
                    getattr(last_resp, "operator_message", "")
                    or extract_api_message(last_resp)
                    or ""
                )
            self._enter_rfid_error(message=api_msg)
            return

        sm.trigger(Event.RFID_VALID)
        self._after_rfid_valid()

    def _apply_valid_rfid(self, rfid: str, truck_details: str) -> None:
        txn = self.ctx.transactions
        if not txn:
            return
        parsed = parse_truck_details(truck_details)
        txn.rfid = rfid
        txn.truck_details = truck_details
        txn.vehicle_no = parsed.get("vehicle_no") or ""
        logger.info(
            "RFID valid rfid=%s vehicle=%s", txn.rfid, txn.vehicle_no
        )
        fe = self._frontend()
        if fe:
            fe.publish_rfid(txn.rfid, txn.vehicle_no or None)
            fe.publish_position(0)
        self._ui_status(
            STEP_VALIDATING_RFID,
            "success",
            f"RFID validated: {txn.vehicle_no or txn.rfid}",
        )

    def _enter_rfid_error(
        self,
        message: str = "",
        *,
        step: str = STEP_VALIDATING_RFID,
    ) -> None:
        self._stop_rfid_reader()
        self._announce(MSG_RFID_ERR)
        detail = str(message or "").strip() or "RFID validation failed."
        self._ui_status(step, "error", detail)
        sm = self.ctx.state_machine
        if sm and sm.current_state != State.RFID_ERROR:
            # Already transitioned via RFID_INVALID / RFID_TIMEOUT
            pass
        self._arm_timer(
            "_rfid_err_timer",
            TIMEOUTS.RFID_ERROR_DISPLAY_SEC,
            self._on_rfid_error_timeout,
        )

    def _after_rfid_valid(self) -> None:
        """
        ANPR branch (tare WB):

        Always: invalid-truck after ANPR (or disabled stub).
        anpr_status 1: weight → weight_details → boom_close → exit
                       (no status-check)
        anpr_status 0/2: status_check loop until vehicleStatus=1 → same weight path
        ANPR disabled: skip detect → invalid-truck(anpr_status=2) → weight path
                       (no status-check)
        """
        sm = self.ctx.state_machine
        oci = self.ctx.oci
        settings = self.ctx.settings
        txn = self.ctx.transactions
        assert sm and oci and settings and txn

        parsed = parse_truck_details(txn.truck_details)

        # Operator may disable ANPR: skip /api/detect; invalid-truck anpr_status=2
        # then continue weight/exit (no status-check — not a CE checkpoint).
        if not bool(getattr(settings, "anpr_enabled", True)):
            logger.info(
                "ANPR disabled - skipping /api/detect and status_check; "
                "invalid-truck anpr_status=2 then weight details"
            )
            txn.anpr_status = 2
            txn.anpr_raw = {
                "vehicleNo_web": txn.vehicle_no or "",
                "vehicleNo_anpr": "",
                "rfid": txn.rfid or "",
                "device_ip": settings.device_ip,
                "anpr_status": 2,
            }
            self._ui_status(
                STEP_VALIDATING_ANPR,
                "success",
                "ANPR skipped (disabled by operator).",
            )
            self._capture_top_photo()
            top_photo_name = (txn.top_image or "").strip() or "error.jpg"
            txn.top_image = top_photo_name
            txn.anpr_raw = dict(txn.anpr_raw or {})
            txn.anpr_raw["top_image"] = top_photo_name
            invalid_resp = oci.invalid_truck_number(
                rfid=txn.rfid,
                truck_number=txn.vehicle_no,
                device_ip=settings.device_ip,
                anpr_payload=txn.anpr_raw,
                anpr_status=2,
                top_image=top_photo_name,
                token=parsed.get("token_no") or "",
            )
            if is_api_failure(invalid_resp):
                self._ui_api_failure(
                    STEP_VALIDATING_ANPR,
                    invalid_resp,
                    fallback="Invalid-truck service not reachable",
                )
            sm.trigger(Event.ANPR_MATCH)
            self._final_weight_and_details(
                boom_close_after=txn.truck_details
            )
            return

        anpr = oci.anpr_detect(
            vehicle_number=txn.vehicle_no,
            rfid=txn.rfid,
            device_ip=settings.device_ip,
            token_no=parsed.get("token_no") or "",
        )
        if is_api_failure(anpr):
            self._announce(MSG_ANPR_ERR)
            self._ui_api_failure(
                STEP_VALIDATING_ANPR, anpr, fallback="ANPR not reachable"
            )
            voice = self._voice()
            if voice:
                voice.tech_issue()
            logger.error("ANPR unreachable or server error - grant exit to clear lane")
            self._enter_exit_granted(reason="anpr_unreachable")
            return

        status = int(anpr.status)
        txn.anpr_status = status
        txn.anpr_raw = dict(anpr.raw) if isinstance(anpr.raw, dict) else {}
        logger.info("ANPR detect anpr_status=%s", status)
        if status in (0, 2):
            voice = self._voice()
            if voice:
                voice.anpr_error()
        self._ui_status(
            STEP_VALIDATING_ANPR, "info", "Validating vehicle number (ANPR)."
        )

        # Always invalid-truck. Status-check only for ANPR mismatch 0/2.
        self._capture_top_photo()
        top_photo_name = (txn.top_image or "").strip() or "error.jpg"
        txn.top_image = top_photo_name
        txn.anpr_raw = dict(txn.anpr_raw or {})
        txn.anpr_raw["top_image"] = top_photo_name
        logger.info(
            "OCI photo name for invalid-truck/weight-details: %s",
            top_photo_name,
        )
        invalid_resp = oci.invalid_truck_number(
            rfid=txn.rfid,
            truck_number=txn.vehicle_no,
            device_ip=settings.device_ip,
            anpr_payload=txn.anpr_raw,
            anpr_status=status,
            top_image=top_photo_name,
            token=parsed.get("token_no") or "",
        )
        if is_api_failure(invalid_resp):
            self._ui_api_failure(
                STEP_VALIDATING_ANPR,
                invalid_resp,
                fallback="Invalid-truck service not reachable",
            )

        if status == 1:
            sm.trigger(Event.ANPR_MATCH)
            self._ui_status(STEP_VALIDATING_ANPR, "success", "ANPR matched.")
            self._final_weight_and_details(
                boom_close_after=txn.truck_details
            )
            return

        # status 0 or 2 - manual status_check loop (vehicleStatus=1 → like status 1)
        sm.trigger(Event.ANPR_MISMATCH)
        if status == 2:
            self._announce(MSG_ANPR_ERR_2)
            self._ui_status(
                STEP_VALIDATING_ANPR, "warning", "ANPR Err-2, Number not readable"
            )
        else:
            self._announce(MSG_ANPR_ERR)
            self._ui_status(
                STEP_VALIDATING_ANPR, "warning", "ANPR Err-0, Number plate mismatch"
            )
        if self._manual_update_loop():
            sm.trigger(Event.UPDATE_STATUS_1)
            sm.trigger(Event.MANUAL_OK)
            self._final_weight_and_details(
                boom_close_after=txn.truck_details
            )
        else:
            logger.warning("Manual update aborted - grant exit")
            self._enter_exit_granted(reason="manual_abort")

    def _capture_top_photo(self) -> None:
        """
        Capture top-camera JPEG via RTSP after ANPR.

        Success filename:
          {TOKEN}_{dd-mm-yy-HH-MM-SS}_{TRUCK}_{PC_IP}_TOP.jpg
        Failure / any exception:
          error.jpg
        """
        txn = self.ctx.transactions
        settings = self.ctx.settings
        if not txn:
            return

        error_name = "error.jpg"
        top_name = error_name
        captured = False

        try:
            parsed = parse_truck_details(txn.truck_details)
            token = parsed.get("token_no") or ""
            truck = txn.vehicle_no or parsed.get("vehicle_no") or ""
            checkpoint_ip = get_local_ip(
                fallback=settings.device_ip if settings else "0.0.0.0"
            )
            IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            formatted_name = build_top_photo_filename(
                token_no=token,
                truck_no=truck,
                checkpoint_ip=checkpoint_ip,
            )
            dest = IMAGES_DIR / formatted_name

            rtsp = (settings.top_camera_rtsp_url if settings else "") or ""
            if not rtsp:
                logger.warning("Top camera RTSP URL not configured")
                raise RuntimeError("top camera RTSP URL not configured")

            captured = bool(capture_rtsp_snapshot(rtsp, dest))
            if not captured:
                raise RuntimeError("RTSP snapshot returned False")

            top_name = formatted_name
        except Exception as exc:
            captured = False
            top_name = error_name
            try:
                IMAGES_DIR.mkdir(parents=True, exist_ok=True)
                error_path = IMAGES_DIR / error_name
                if not error_path.exists():
                    error_path.write_bytes(b"")
            except Exception:
                pass
            logger.error("Top photo capture failed name=%s error=%s", top_name, exc)

        txn.top_image = top_name

        anpr_path = str(
            (txn.anpr_raw or {}).get("anpr_image")
            or (txn.anpr_raw or {}).get("front_image")
            or ""
        )
        anpr_name = Path(anpr_path).name if anpr_path else ""
        if top_name == error_name:
            txn.anpr_image = anpr_name or "error_ANPR.jpg"
            front_path = str((txn.anpr_raw or {}).get("front_image") or "")
            txn.front_image = Path(front_path).name if front_path else "error_FRONT.jpg"
        else:
            txn.anpr_image = anpr_name or f"{Path(top_name).stem.replace('_TOP', '')}_ANPR.jpg"
            front_path = str((txn.anpr_raw or {}).get("front_image") or "")
            txn.front_image = (
                Path(front_path).name
                if front_path
                else f"{Path(top_name).stem.replace('_TOP', '')}_FRONT.jpg"
            )
        txn.anpr_raw = dict(txn.anpr_raw or {})
        txn.anpr_raw["top_image"] = txn.top_image
        logger.info(
            "Top photo top=%s captured=%s anpr_image=%s front=%s",
            txn.top_image,
            captured,
            txn.anpr_image,
            txn.front_image,
        )

    def _manual_update_loop(self) -> bool:
        """
        Poll update_truck_url (status_check) until approved or abort.

        Mines Entry: vehicleStatus 0=retry, 1=ok, 2=abort.
        HTTP/statusCode 200 alone does not continue the flow.
        """
        oci = self.ctx.oci
        settings = self.ctx.settings
        txn = self.ctx.transactions
        sm = self.ctx.state_machine
        assert oci and settings and txn

        retry_sec = float(
            getattr(settings, "truck_anpr_retry_timer", None)
            or TIMEOUTS.MANUAL_UPDATE_POLL_SEC
        )
        self._manual_stop.clear()
        self._status_check_alerted = False
        while not self._manual_stop.is_set():
            resp = oci.update_truck_number(
                rfid=txn.rfid,
                truck_number=txn.vehicle_no,
                device_ip=settings.device_ip,
                anpr_payload=txn.anpr_raw,
            )
            if is_api_failure(resp):
                if is_service_alert(resp):
                    if not self._status_check_alerted:
                        self._status_check_alerted = True
                        self._ui_api_failure(
                            STEP_VALIDATING_ANPR,
                            resp,
                            fallback="Status-check service not reachable",
                        )
                else:
                    # Reachable 4xx while vehicleStatus is still 0: keep yellow wait.
                    self._ui_anpr_waiting(txn)
                if sm:
                    sm.trigger(Event.UPDATE_STATUS_0)
                time.sleep(retry_sec)
                continue

            vehicle_status = resp.status
            logger.info(
                "status_check vehicleStatus/status=%s message=%s",
                vehicle_status,
                resp.message,
            )

            # Proceed only when the response explicitly has vehicleStatus=1.
            if vehicle_status == 1:
                if sm:
                    sm.trigger(Event.UPDATE_STATUS_1)
                logger.info("Manual truck validation OK (status=%s)", vehicle_status)
                return True

            if vehicle_status == 2:
                if sm:
                    sm.trigger(Event.UPDATE_STATUS_2)
                logger.warning("status_check vehicleStatus=2 - abort to exit")
                time.sleep(TIMEOUTS.UPDATE_STATUS_2_RESET_SEC)
                return False

            self._ui_anpr_waiting(txn)
            if sm:
                sm.trigger(Event.UPDATE_STATUS_0)
            logger.info(
                "vehicleStatus=0 - retry status_check in %ss", retry_sec
            )
            time.sleep(retry_sec)
        return False

    def _speak_final_weight(self) -> None:
        """Play intro + ton/kg clips after weight-details HTTP/status 200."""
        voice = self._voice()
        txn = self.ctx.transactions
        if not voice or not txn or txn.weight_kg is None:
            return
        parsed = parse_truck_details(txn.truck_details or "")
        trip = (parsed.get("trip_type") or "").lower()[:1]
        # Tare intro is tare_final_weight; gross and vadhghat use filled_final_weight.
        voice.speak_weight("t" if trip == "t" else "g", txn.weight_kg)

    def _final_weight_and_details(
        self, *, boom_close_after: Optional[str] = None
    ) -> None:
        """
        Capture current weight → weight_details → optional boom_close → exit.

        Vadhghat (V|) out of RTO band: POST vadhghat_weight_adjustment, then
        exit without weight-details or boom-close.

        boom_close_after:
          "T|…"  → POST boom-close with current transaction truck_details
          None   → skip boom-close
        """
        sm = self.ctx.state_machine
        oci = self.ctx.oci
        settings = self.ctx.settings
        digitizer = self.ctx.digitizer
        txn = self.ctx.transactions
        assert sm and oci and settings and digitizer and txn

        result = digitizer.read_stable_weight()
        weight = result.get("weight")
        if weight is None or not result.get("ok"):
            voice = self._voice()
            if voice:
                voice.digitizer_error()
            self._ui_result_failure(
                STEP_READING_WEIGHT,
                result,
                fallback="Digitizer failed",
            )
            sm.trigger(Event.WEIGHT_FAIL)
            self._enter_exit_granted(reason="final_weight_fail")
            return
        txn.weight_kg = float(weight)
        fe = self._frontend()
        if fe:
            fe.publish_digitizer(weight)
            fe.publish_position(3)
        self._ui_status(
            STEP_READING_WEIGHT, "info", "Capturing final weight."
        )
        if sm.current_state != State.FINAL_WEIGHT:
            sm.force_state(State.FINAL_WEIGHT)

        parsed = parse_truck_details(txn.truck_details or "")
        trip = (parsed.get("trip_type") or "").upper()[:1]
        is_gross_like = trip in ("G", "V")
        if is_gross_like:
            band = rto_weight_band(txn.truck_details or "")
            if band:
                lo, hi, _ = band
                logger.info(
                    "RTO gross band %s–%s kg (gross=%s tare=%s tolerance=%s "
                    "current=%s)",
                    int(lo),
                    int(hi),
                    parsed.get("rto_gross"),
                    parsed.get("rto_tare"),
                    parsed.get("tolerance"),
                    int(txn.weight_kg),
                )

        # Tare (T): local RTO band + weight-confirm. G/V skip weight-confirm.
        if not is_gross_like:
            in_band, band_msg = weight_within_rto_tolerance(
                txn.weight_kg, txn.truck_details or ""
            )
            if not in_band:
                err_msg = weight_type_error_display(trip)
                logger.warning(
                    "Final weight out of tolerance type=%s: %s", trip, band_msg
                )
                self._announce(err_msg)
                self._ui_status(STEP_READING_WEIGHT, "warning", band_msg)
                voice = self._voice()
                if voice:
                    voice.weight_out_of_tolerance(trip)

                if not self._weight_confirm_until_in_band():
                    self._enter_exit_granted(reason="weight_confirm_rejected")
                    return

        # Vadhghat (V): out of RTO band → weight-adjustment, then exit (no boom-close).
        if trip == "V":
            in_band, band_msg = weight_within_rto_tolerance(
                txn.weight_kg, txn.truck_details or ""
            )
            if not in_band:
                err_msg = weight_type_error_display(trip)
                logger.warning(
                    "Vadhghat weight out of tolerance: %s", band_msg
                )
                self._announce(err_msg)
                self._ui_status(STEP_READING_WEIGHT, "warning", band_msg)
                voice = self._voice()
                if voice:
                    voice.weight_out_of_tolerance(trip)
                self._vadhghat_weight_adjustment_and_exit()
                return

        sm.trigger(Event.WEIGHT_OK)

        # Ensure top photo name is set before weight-details (same as invalid-truck).
        if not (txn.top_image or "").strip():
            self._capture_top_photo()
        top_photo_name = (txn.top_image or "").strip() or "error.jpg"
        txn.top_image = top_photo_name

        if sm.current_state != State.IMAGE_CAPTURE:
            sm.force_state(State.IMAGE_CAPTURE)
        sm.trigger(Event.DETAILS_OK)  # IMAGE_CAPTURE → WEIGHT_DETAILS
        self._ui_status(
            STEP_VALIDATING_WEIGHT, "info", "Validating weight with OCI."
        )

        logger.info(
            "OCI weight-details top_image_name=%s (success/failure naming)",
            top_photo_name,
        )
        details = oci.weight_details(
            current_weight=str(int(txn.weight_kg)),
            truck_details=txn.truck_details or "",
            front_image_name=txn.front_image,
            top_image_name=top_photo_name,
            anpr_image_name=txn.anpr_image,
        )

        skip_second_details = False
        if is_gross_like and details.status == 201:
            outcome = self._gross_tolerance_confirm_until_ok()
            if outcome == "ok":
                self._ui_status(
                    STEP_VALIDATING_WEIGHT,
                    "info",
                    "Submitting weight details with updated tolerance.",
                )
                details = oci.weight_details(
                    current_weight=str(int(txn.weight_kg or 0)),
                    truck_details=txn.truck_details or "",
                    front_image_name=txn.front_image,
                    top_image_name=top_photo_name,
                    anpr_image_name=txn.anpr_image,
                )
            else:
                skip_second_details = True
                logger.warning(
                    "gross-tolerance-confirm skipped second weight-details "
                    "(outcome=%s)",
                    outcome,
                )

        details_ok = (not skip_second_details) and (
            details.ok or details.status == 200
        )
        voice = self._voice()
        if skip_second_details or details_ok:
            sm.trigger(Event.DETAILS_OK)
            self._ui_status(
                STEP_VALIDATING_WEIGHT,
                "success",
                "Weight validation successful.",
            )
            if details_ok:
                self._speak_final_weight()
        else:
            if is_api_failure(details):
                self._ui_api_failure(
                    STEP_VALIDATING_WEIGHT,
                    details,
                    fallback="Weight-details service not reachable",
                )
            else:
                self._ui_status(
                    STEP_VALIDATING_WEIGHT,
                    "error",
                    "Weight validation failed.",
                )
            if voice:
                voice.weight_submit_error_by_status(
                    details.status or details.http_status
                )
            sm.trigger(Event.DETAILS_FAIL)

        if boom_close_after is not None:
            close_details = txn.truck_details or boom_close_after
            close = oci.boom_close(truck_details=close_details)
            logger.info(
                "boom-close (post-weight) truck_details=%r ok=%s status=%s",
                close_details,
                close.ok,
                close.status,
            )
            if close.status != 200:
                self._ui_api_failure(
                    STEP_EXIT_START,
                    close,
                    fallback="Boom-close rejected.",
                )

        self._enter_exit_granted(
            reason=(
                "details_ok"
                if (skip_second_details or details_ok)
                else "details_fail"
            )
        )

    def _vadhghat_weight_adjustment_and_exit(self) -> None:
        """
        Vadhghat out-of-tolerance: POST captured weight + o/u, then exit.
        Does not call weight-details or boom-close.
        """
        oci = self.ctx.oci
        settings = self.ctx.settings
        txn = self.ctx.transactions
        assert oci and settings and txn
        details = txn.truck_details or ""
        weight_type = under_or_over_type(txn.weight_kg or 0, details)
        device_ip = str(getattr(settings, "device_ip", "") or "")
        logger.info(
            "Vadhghat weight-adjustment weight=%s type=%s device_ip=%s",
            txn.weight_kg,
            weight_type,
            device_ip,
        )
        self._ui_status(
            STEP_VALIDATING_WEIGHT,
            "info",
            f"Submitting Vadhghat weight adjustment ({weight_type}).",
        )
        resp = oci.vadhghat_weight_adjustment(
            device_ip=device_ip,
            truck_details=details,
            weight=txn.weight_kg or 0,
            weight_type=weight_type,
        )
        if is_api_failure(resp) or not (resp.ok or resp.status == 200):
            self._ui_api_failure(
                STEP_VALIDATING_WEIGHT,
                resp,
                fallback="Vadhghat weight-adjustment failed",
            )
        else:
            self._ui_status(
                STEP_VALIDATING_WEIGHT,
                "success",
                str(resp.message or "Vadhghat weight adjustment processed."),
            )
        self._enter_exit_granted(reason="vadhghat_weight_adjustment")

    def _gross_tolerance_confirm_until_ok(self) -> str:
        """
        G/V weight-details status 201 loop.

        POST gross-tolerance-confirm every 5s with the same payload.
        tolerance_status 0 → retry.
        tolerance_status 1 → if current_weight is within
          (RFID gross - gross_tolerance) .. RFID gross, write gross_tolerance
          into truck_details and return "ok" (caller posts weight-details).
          If still out of band, keep looping.
        tolerance_status 2 → return "rejected" (skip second weight-details,
          still boom_close).
        """
        oci = self.ctx.oci
        settings = self.ctx.settings
        txn = self.ctx.transactions
        assert oci and settings and txn
        retry_sec = TIMEOUTS.WEIGHT_CONFIRM_POLL_SEC
        device_ip = str(getattr(settings, "device_ip", "") or "")
        confirm_alerted = False

        while not self._manual_stop.is_set():
            details = txn.truck_details or ""
            current_weight = str(int(txn.weight_kg or 0))
            logger.info(
                "gross-tolerance-confirm weight=%s device_ip=%s truck_details=%r",
                current_weight,
                device_ip,
                details,
            )
            self._ui_status(
                STEP_READING_WEIGHT,
                "warning",
                "Gross weight outside tolerance - waiting for confirmation.",
            )
            resp = oci.gross_tolerance_confirm(
                current_weight=current_weight,
                truck_details=details,
                device_ip=device_ip,
            )
            if is_api_failure(resp):
                if not confirm_alerted:
                    confirm_alerted = True
                    self._ui_api_failure(
                        STEP_VALIDATING_WEIGHT,
                        resp,
                        fallback="Gross-tolerance service not reachable",
                    )
                time.sleep(retry_sec)
                continue
            ts = resp.status
            logger.info(
                "gross-tolerance-confirm tolerance_status=%s gross_tolerance=%s",
                ts,
                resp.raw.get("gross_tolerance"),
            )

            if ts == 2:
                logger.warning(
                    "gross-tolerance-confirm rejected (tolerance_status=2) "
                    "- skip weight-details, continue boom-close"
                )
                self._ui_status(
                    STEP_READING_WEIGHT,
                    "warning",
                    "Gross tolerance waived - opening boom.",
                )
                return "rejected"

            if ts != 1:
                time.sleep(retry_sec)
                continue

            updated = resp.raw.get("gross_tolerance")
            candidate = details
            if updated is not None and str(updated).strip() != "":
                candidate = replace_truck_details_tolerance(details, updated)
            in_band, band_msg = weight_within_rto_tolerance(
                txn.weight_kg or 0, candidate
            )
            if in_band:
                txn.truck_details = candidate
                logger.info(
                    "Gross weight %s kg within tolerance truck_details=%r",
                    int(txn.weight_kg or 0),
                    txn.truck_details,
                )
                self._ui_status(
                    STEP_READING_WEIGHT,
                    "success",
                    "Weight within updated gross tolerance.",
                )
                return "ok"

            logger.warning(
                "Gross weight still out of band after tolerance_status=1: %s",
                band_msg,
            )
            time.sleep(retry_sec)

        return "rejected"

    def _weight_confirm_until_in_band(self) -> bool:
        """
        Out-of-tolerance loop:

        POST weight-confirm with type u/o.
        weight_status 0 → retry same payload.
        weight_status 1 → write updated_tolerance into truck_details,
          recapture weight, re-check band; if still out, confirm again.
        weight_status 2 → abort (skip weight_details / boom_close).
        """
        oci = self.ctx.oci
        digitizer = self.ctx.digitizer
        txn = self.ctx.transactions
        assert oci and digitizer and txn
        retry_sec = TIMEOUTS.WEIGHT_CONFIRM_POLL_SEC
        confirm_alerted = False

        while not self._manual_stop.is_set():
            details = txn.truck_details or ""
            weight_type = under_or_over_type(txn.weight_kg or 0, details)
            current_weight = str(int(txn.weight_kg or 0))
            logger.info(
                "weight-confirm type=%s weight=%s truck_details=%r",
                weight_type,
                current_weight,
                details,
            )
            self._ui_status(
                STEP_READING_WEIGHT,
                "warning",
                f"Weight {'under' if weight_type == 'u' else 'over'} - waiting for confirmation.",
            )
            resp = oci.weight_confirm(
                truck_details=details,
                current_weight=current_weight,
                weight_type=weight_type,
            )
            if is_api_failure(resp):
                if not confirm_alerted:
                    confirm_alerted = True
                    self._ui_api_failure(
                        STEP_READING_WEIGHT,
                        resp,
                        fallback="Weight-confirm service not reachable",
                    )
                time.sleep(retry_sec)
                continue
            ws = resp.status
            logger.info(
                "weight-confirm weight_status=%s updated_tolerance=%s",
                ws,
                resp.raw.get("updated_tolerance"),
            )

            if ws == 2:
                logger.warning("weight-confirm rejected (weight_status=2)")
                self._ui_status(
                    STEP_READING_WEIGHT, "error", "Weight rejected by server."
                )
                return False

            if ws != 1:
                time.sleep(retry_sec)
                continue

            updated = resp.raw.get("updated_tolerance")
            if updated is not None and str(updated).strip() != "":
                txn.truck_details = replace_truck_details_tolerance(
                    details, updated
                )
                logger.info(
                    "truck_details tolerance updated → %s", txn.truck_details
                )

            recapture = digitizer.read_stable_weight()
            recaptured = recapture.get("weight")
            if recaptured is None or not recapture.get("ok"):
                logger.warning("weight recapture failed after confirm - retrying")
                time.sleep(retry_sec)
                continue

            txn.weight_kg = float(recaptured)
            fe = self._frontend()
            if fe:
                fe.publish_digitizer(recaptured)
            in_band, band_msg = weight_within_rto_tolerance(
                txn.weight_kg, txn.truck_details or ""
            )
            if in_band:
                logger.info(
                    "Recaptured weight %s kg within updated tolerance",
                    int(txn.weight_kg),
                )
                self._ui_status(
                    STEP_READING_WEIGHT,
                    "success",
                    "Weight within updated tolerance.",
                )
                return True

            parsed = parse_truck_details(txn.truck_details or "")
            trip = (parsed.get("trip_type") or "").upper()[:1]
            logger.warning(
                "Recaptured weight still out of band: %s", band_msg
            )
            self._announce(weight_type_error_display(trip))
            self._ui_status(STEP_READING_WEIGHT, "warning", band_msg)
            time.sleep(retry_sec)

        return False

    def _enter_exit_granted(self, reason: str = "") -> None:
        sm = self.ctx.state_machine
        if sm and sm.current_state != State.EXIT_GRANTED:
            sm.force_state(State.EXIT_GRANTED)

        logger.info("EXIT_GRANTED reason=%s", reason)
        self._ui_position(4)
        reason_l = str(reason or "").lower()
        failure_exit = any(
            token in reason_l
            for token in (
                "error",
                "fail",
                "abort",
                "reject",
                "unreachable",
                "adjustment",
            )
        )
        if failure_exit:
            self._ui_status(
                STEP_EXIT_START,
                "error",
                "Exit after failure - clear the lane.",
            )
        else:
            self._ui_status(STEP_EXIT_START, "success", "Exit granted - proceed.")
        self._announce(MSG_MOVE_FORWARD)
        self._grant_exit_hardware()
        # Continuous move-forward while waiting for exit sensor (legacy)
        self._start_move_forward_announcement()
        self._arm_timer(
            "_exit_timer",
            TIMEOUTS.EXIT_WAIT_SEC,
            self._on_exit_timeout,
        )
