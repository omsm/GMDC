"""Mines Entry workflow orchestrator - PDF checkpoint flow."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from config.constants import (
    MSG_ANPR_API_ERR,
    MSG_ANPR_ERR,
    MSG_ANPR_ERR_2,
    MSG_ENTRY_GRANTED_FMT,
    MSG_FREE_PASS,
    MSG_RFID_ERR,
    TIMEOUTS,
    Event,
    State,
)
from core.app_context import AppContext
from core.state_machine import StateMachine
from core.transaction import TransactionStore
from services.frontend_mqtt import (
    STEP_ENTRY_GRANTED,
    STEP_EXIT_COMPLETED,
    STEP_RFID_READ,
    STEP_VALIDATING_ANPR,
    STEP_VALIDATING_RFID,
    STEP_WAIT_CROSSING,
)
from services.oci_client import (
    OCIResponse,
    is_ce_truck_details,
    parse_truck_details,
    status_code_from_response,
)
from services.api_errors import (
    KIND_UNREACHABLE,
    extract_api_message,
    is_api_failure,
    is_service_alert,
    is_transport_failure,
    operator_copy,
)

logger = logging.getLogger("mines_checkpoint.core.workflow")


class CheckpointWorkflow:
    """
    Drives the Mines Entry PDF flow:

    IDLE → RFID_READ → RFID_VALIDATE → (DISPLAY_TRUCK → ANPR)
         → ENTRY_GRANTED / MANUAL_UPDATE → WAIT_CROSSING → IDLE
    """

    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self._worker_lock = threading.Lock()
        self._manual_stop = threading.Event()
        self._busy = False
        self._crossing_timer: Optional[threading.Timer] = None
        self._crossing_timer_lock = threading.Lock()
        self._boom_close_timer: Optional[threading.Timer] = None
        self._boom_close_timer_lock = threading.Lock()
        self._status_check_alerted = False

    def _collect_reset_fields(self) -> tuple[str, str, str]:
        settings = self.ctx.settings
        device_ip = str(getattr(settings, "device_ip", "") or "") if settings else ""
        store = self.ctx.transactions
        txn = getattr(store, "current", store) if store else None
        rfid = ""
        details = ""
        if txn is not None:
            rfid = str(
                getattr(txn, "validated_rfid", None)
                or getattr(txn, "rfid", None)
                or ""
            )
            if not rfid:
                tags = list(
                    getattr(txn, "rfid_tags", None)
                    or getattr(txn, "tags", None)
                    or []
                )
                if tags:
                    rfid = str(tags[0] or "")
            details = str(getattr(txn, "truck_details", "") or "")
            device_ip = str(getattr(txn, "device_ip", "") or device_ip)
        return device_ip, rfid, details

    def _notify_gmdc_reset(self, *, manual: bool = False) -> None:
        """Tell GMDC this lane is idle. Manual UI reset always posts."""
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
                STEP_RFID_READ,
                resp,
                fallback="Reset service not reachable",
            )

    def notify_gmdc_reset(self) -> None:
        """Startup IDLE: POST reset_checkpoint with device_ip and empty RFID/truck."""
        self._notify_gmdc_reset(manual=True)

    # ------------------------------------------------------------------
    # Hardware reset (PDF step 1 / step 5)
    # ------------------------------------------------------------------
    def apply_idle_hardware(self, delay_boom_close: bool = False) -> None:
        """
        Entry TL red/off, boom closed, clear display.

        ``delay_boom_close`` holds the boom up for
        ``TIMEOUTS.BOOM_CLOSE_DELAY_SEC`` so a truck that just cleared the
        sensor is fully past the barrier before it drops.
        """
        tl = self.ctx.traffic_light
        boom = self.ctx.boom_barrier
        display = self.ctx.display
        if tl:
            tl.set_red()
        if delay_boom_close:
            self._schedule_boom_close()
        else:
            self._cancel_boom_close_timer()
            if boom:
                boom.close()
        if display:
            display.clear()
        logger.info(
            "Hardware reset to IDLE (TL red, boom %s)",
            (
                f"closing in {TIMEOUTS.BOOM_CLOSE_DELAY_SEC}s"
                if delay_boom_close
                else "closed"
            ),
        )
        self._ui_devices()

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
    ) -> None:
        fe = self._frontend()
        if fe:
            fe.publish_status(
                step, status, message, popup=popup, popup_title=popup_title
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

    def _ui_position(self, position: int) -> None:
        fe = self._frontend()
        if fe:
            fe.publish_position(position)

    def _ui_devices(self) -> None:
        fe = self._frontend()
        if fe:
            fe.publish_device_status()

    def _ui_rfid(self, rfid: str, truck_number: Optional[str] = None) -> None:
        fe = self._frontend()
        if fe:
            fe.publish_rfid(rfid, truck_number)

    def _announce(self, msg: str) -> None:
        display = self.ctx.display
        if display:
            display.send(msg)
        fe = self._frontend()
        if fe:
            fe.publish_display(msg)

    def _schedule_boom_close(self) -> None:
        """Close the boom after the post-crossing delay."""
        if not self.ctx.boom_barrier:
            return
        self._cancel_boom_close_timer()

        def _close():
            boom = self.ctx.boom_barrier
            if boom:
                boom.close()
                logger.info(
                    "Boom closed after %ss crossing delay",
                    TIMEOUTS.BOOM_CLOSE_DELAY_SEC,
                )

        timer = threading.Timer(TIMEOUTS.BOOM_CLOSE_DELAY_SEC, _close)
        timer.daemon = True
        with self._boom_close_timer_lock:
            self._boom_close_timer = timer
            timer.start()

    def _cancel_boom_close_timer(self) -> None:
        with self._boom_close_timer_lock:
            timer = self._boom_close_timer
            self._boom_close_timer = None
        if timer is not None:
            timer.cancel()

    def grant_entry_hardware(self, truck_no: str) -> Optional[OCIResponse]:
        """
        Call OCI boom-close first; only open boom if status == 200.
        Then set TL green and show entry granted message.
        """
        # A pending post-crossing close must not drop the boom on this truck.
        self._cancel_boom_close_timer()
        tl = self.ctx.traffic_light
        boom = self.ctx.boom_barrier
        settings = self.ctx.settings
        oci = self.ctx.oci
        txn = self.ctx.transactions.current if self.ctx.transactions else None

        rfid = (txn.validated_rfid if txn else "") or ""
        device_ip = ""
        if txn and txn.device_ip:
            device_ip = txn.device_ip
        elif settings:
            device_ip = settings.device_ip
        truck_details = (txn.truck_details if txn else "") or ""
        anpr_payload = (txn.anpr_raw if txn else None) or {}

        boom_ok = False
        close_resp: Optional[OCIResponse] = None
        if oci:
            close_resp = oci.boom_close(
                rfid=rfid,
                device_ip=device_ip,
                close_type="auto",
                truck_details=truck_details,
                anpr_payload=anpr_payload,
            )
            boom_ok = close_resp.status == 200
            logger.info(
                "boom-close status=%s ok=%s - %s boom open",
                close_resp.status,
                boom_ok,
                "allowing" if boom_ok else "skipping",
            )
        else:
            logger.warning("OCI client missing - opening boom without boom-close API")
            boom_ok = True

        if tl:
            tl.set_green()
        if boom and boom_ok:
            boom.open()
        elif boom and not boom_ok:
            logger.error("Boom NOT opened - boom-close API status != 200")

        msg = MSG_ENTRY_GRANTED_FMT.format(truck=truck_no or "TRUCK")
        self._announce(msg)
        self._ui_devices()
        logger.info("Entry granted: %s (boom_opened=%s)", msg, boom_ok)
        return close_resp

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def on_rfid_tags(self, id_hexes: List[str], raw_tags: Optional[List[dict]] = None) -> None:
        sm = self.ctx.state_machine
        if not sm:
            return
        if sm.current_state != State.IDLE:
            logger.warning(
                "Ignoring RFID tags while in state %s", sm.current_state.name
            )
            return
        if not id_hexes:
            logger.warning("Empty RFID tag list - ignored")
            return

        if not self._worker_lock.acquire(blocking=False):
            logger.warning("Workflow busy - ignoring RFID")
            return

        def _run():
            try:
                self._process_rfid_cycle(id_hexes, raw_tags or [])
            finally:
                self._worker_lock.release()

        threading.Thread(target=_run, name="RFIDCycle", daemon=True).start()

    def on_rfid_from_mobile(self, rfid: str) -> Dict[str, Any]:
        """
        Mobile fallback when fixed RFID reader cannot read.

        Synchronously calls OCI rfid-validate and returns that response body
        so the mobile API can echo it (HTTP 200). Continues the Mines Entry
        cycle in a background thread without re-validating.
        """
        sm = self.ctx.state_machine
        oci = self.ctx.oci
        settings = self.ctx.settings
        txn_store = self.ctx.transactions
        if not sm or not oci or not settings or not txn_store:
            raise RuntimeError("Workflow not ready")
        if sm.current_state != State.IDLE:
            raise RuntimeError(
                f"Ignoring RFID while in state {sm.current_state.name}"
            )
        if not rfid:
            raise ValueError("Empty RFID tag")

        if not self._worker_lock.acquire(blocking=False):
            raise RuntimeError("Workflow busy - ignoring RFID")

        try:
            self._manual_stop.clear()
            txn = txn_store.current
            txn.start([rfid], [{"source": "mobile_app"}])
            txn.device_ip = settings.device_ip

            sm.trigger(Event.RFID_RECEIVED)  # IDLE -> RFID_READ
            self._ui_position(0)
            self._ui_status(STEP_RFID_READ, "info", "Reading RFID; present a valid tag.")
            self._ui_rfid(rfid)
            self._stop_rfid_reader()
            sm.trigger(Event.RFID_RECEIVED)  # RFID_READ -> RFID_VALIDATE
            self._ui_status(STEP_VALIDATING_RFID, "info", "Validating RFID with OCI.")

            logger.info("Validating mobile RFID tag %s", rfid)
            resp = oci.validate_rfid(rfid, settings.device_ip)
            oci_body = self._oci_body(resp)

            valid = bool(resp.ok and resp.status == 200)
            if valid:
                self._apply_rfid_validation(txn, rfid, resp)
            else:
                logger.warning(
                    "RFID invalid for mobile tag %s: %s", rfid, resp.message
                )

            service_alert = (
                resp if (not valid and is_api_failure(resp)) else None
            )

            def _run():
                try:
                    self._continue_after_rfid_validation(
                        valid, service_alert=service_alert
                    )
                finally:
                    self._worker_lock.release()

            threading.Thread(
                target=_run, name="MobileRFIDCycle", daemon=True
            ).start()
            return oci_body
        except Exception:
            self._worker_lock.release()
            raise

    @staticmethod
    def _oci_body(resp: OCIResponse) -> Dict[str, Any]:
        if isinstance(resp.raw, dict) and resp.raw:
            return dict(resp.raw)
        return {"status": resp.status, "message": resp.message or ""}

    def on_exit_sensor(self) -> None:
        """
        Vehicle cleared the entry sensor (FALSE after TRUE) while waiting to cross.
        Close boom, set TL red, reset to IDLE.
        """
        sm = self.ctx.state_machine
        if not sm:
            return
        if sm.current_state not in (
            State.ENTRY_GRANTED,
            State.WAIT_CROSSING,
            State.FREE_PASS,
        ):
            logger.debug(
                "Crossing-clear ignored in state %s (sensor idle/validation)",
                sm.current_state.name,
            )
            return
        if sm.current_state == State.FREE_PASS:
            logger.info(
                "Entry sensor cleared - free pass complete, delayed boom close, reset"
            )
        else:
            logger.info(
                "Entry sensor cleared (truck passed) - TL red, delayed boom close, reset"
            )
            self._ui_status(STEP_EXIT_COMPLETED, "success", "Transaction complete.")
        self._cancel_crossing_timer()
        sm.trigger(Event.EXIT_SENSOR)
        self._reset_to_idle(delay_boom_close=True, notify_gmdc=False)

    def force_reset(self) -> None:
        logger.info("Force reset requested")
        self._manual_stop.set()
        self._cancel_crossing_timer()
        sm = self.ctx.state_machine
        if sm:
            sm.trigger(Event.RESET)
            sm.force_state(State.IDLE)
        self._reset_to_idle(manual=True)

    def start_free_pass(self) -> None:
        """Open traffic light and boom; return to IDLE after entry sensor."""
        logger.info("Free pass - opening traffic light and boom barrier")
        self._manual_stop.set()
        self._cancel_crossing_timer()
        self._cancel_boom_close_timer()
        self._stop_rfid_reader()
        sm = self.ctx.state_machine
        if sm:
            sm.force_state(State.FREE_PASS)
        self._notify_gmdc_reset(manual=False)
        if self.ctx.transactions:
            self.ctx.transactions.clear()
        poller = self.ctx.sensor_poller
        if poller and hasattr(poller, "reset_edge_state"):
            poller.reset_edge_state()
        tl = self.ctx.traffic_light
        boom = self.ctx.boom_barrier
        if tl:
            tl.set_green()
        if boom:
            boom.open()
        self._announce(MSG_FREE_PASS)
        fe = self._frontend()
        if fe:
            fe.publish_position(2)
            fe.publish_status(
                STEP_WAIT_CROSSING,
                "info",
                "Free pass - traffic light green, boom open. Waiting for entry sensor.",
            )
            fe.publish_device_status()


    def _reset_to_idle(
        self,
        delay_boom_close: bool = False,
        *,
        notify_gmdc: bool = True,
        manual: bool = False,
    ) -> None:
        if notify_gmdc:
            self._notify_gmdc_reset(manual=manual)
        self._cancel_crossing_timer()
        if self.ctx.transactions:
            self.ctx.transactions.clear()
        self.apply_idle_hardware(delay_boom_close=delay_boom_close)
        poller = self.ctx.sensor_poller
        if poller and hasattr(poller, "reset_edge_state"):
            poller.reset_edge_state()
        sm = self.ctx.state_machine
        if sm and sm.current_state != State.IDLE:
            sm.force_state(State.IDLE)
        # IDLE: login -> mode -> start so reader can scan next vehicle
        self._prepare_rfid_idle()
        fe = self._frontend()
        if fe:
            fe.reset_idle()

    def _stop_rfid_reader(self) -> None:
        cloud = self.ctx.rfid_cloud
        if not cloud:
            logger.debug("RFID cloud control not configured - skip stop")
            return
        ok = cloud.stop()
        logger.info("RFID reader stop requested ok=%s", ok)

    def prepare_rfid_for_idle(self) -> None:
        """Public: login -> mode -> start when entering IDLE."""
        self._prepare_rfid_idle()

    def _prepare_rfid_idle(self) -> None:
        """login (Basic) -> mode (Bearer) -> start (Bearer)."""
        cloud = self.ctx.rfid_cloud
        if not cloud:
            return
        ok = cloud.prepare_idle()
        logger.info("RFID IDLE prepare (login/mode/start) ok=%s", ok)

    def _start_rfid_reader(self) -> None:
        # Kept for compatibility; prefer full IDLE prepare
        self._prepare_rfid_idle()

    # ------------------------------------------------------------------
    # Main cycle
    # ------------------------------------------------------------------
    def _process_rfid_cycle(
        self, id_hexes: List[str], raw_tags: List[dict]
    ) -> None:
        sm = self.ctx.state_machine
        txn_store = self.ctx.transactions
        oci = self.ctx.oci
        settings = self.ctx.settings
        assert sm and txn_store and oci and settings

        self._manual_stop.clear()
        self._status_check_alerted = False
        txn = txn_store.current
        txn.start(id_hexes, raw_tags)
        txn.device_ip = settings.device_ip

        sm.trigger(Event.RFID_RECEIVED)  # IDLE -> RFID_READ
        self._ui_position(0)
        self._ui_status(STEP_RFID_READ, "info", "Reading RFID; present a valid tag.")
        if id_hexes:
            self._ui_rfid(id_hexes[0])
        # 6. Stop reader, then 7. OCI RFID validate
        self._stop_rfid_reader()
        sm.trigger(Event.RFID_RECEIVED)  # RFID_READ -> RFID_VALIDATE
        self._ui_status(STEP_VALIDATING_RFID, "info", "Validating RFID with OCI.")

        # Validate tags one-by-one; first valid wins
        valid = False
        service_alert: Optional[OCIResponse] = None
        last_resp: Optional[OCIResponse] = None
        for tag in id_hexes:
            logger.info("Validating RFID tag %s", tag)
            resp = oci.validate_rfid(tag, settings.device_ip)
            last_resp = resp
            if is_api_failure(resp):
                service_alert = resp
                break
            if resp.ok and resp.status == 200:
                self._apply_rfid_validation(txn, tag, resp)
                valid = True
                break
            logger.warning("RFID invalid for tag %s: %s", tag, resp.message)

        if service_alert is not None:
            self._continue_after_rfid_validation(
                False, service_alert=service_alert
            )
            return

        self._continue_after_rfid_validation(valid, last_resp=last_resp)

    def _apply_rfid_validation(self, txn, tag: str, resp: OCIResponse) -> None:
        parsed = parse_truck_details(resp.truck_details)
        txn.validated_rfid = parsed.get("rfid") or tag
        txn.vehicle_no = parsed.get("vehicle_no", "")
        txn.truck_no = txn.vehicle_no
        txn.token_no = parsed.get("token_no", "")
        txn.truck_details = resp.truck_details
        if parsed.get("device_ip"):
            txn.device_ip = parsed["device_ip"]
        logger.info(
            "RFID valid: vehicle=%s token=%s",
            txn.vehicle_no,
            txn.token_no,
        )

    def _continue_after_rfid_validation(
        self,
        valid: bool,
        service_alert: Optional[OCIResponse] = None,
        last_resp: Optional[OCIResponse] = None,
    ) -> None:
        sm = self.ctx.state_machine
        txn_store = self.ctx.transactions
        oci = self.ctx.oci
        settings = self.ctx.settings
        assert sm and txn_store and oci and settings
        txn = txn_store.current

        if service_alert is not None:
            sm.trigger(Event.RFID_INVALID)
            self._announce(MSG_RFID_ERR)
            self._ui_api_failure(
                STEP_VALIDATING_RFID,
                service_alert,
                fallback="RFID service not reachable",
            )
            logger.info(
                "RFID service error - waiting %ss", TIMEOUTS.RFID_ERROR_DISPLAY_SEC
            )
            time.sleep(TIMEOUTS.RFID_ERROR_DISPLAY_SEC)
            sm.trigger(Event.RFID_ERROR_TIMEOUT)
            self._reset_to_idle()
            return

        if not valid:
            sm.trigger(Event.RFID_INVALID)
            detail = "RFID validation failed."
            if last_resp is not None:
                detail = str(
                    getattr(last_resp, "operator_message", "")
                    or extract_api_message(last_resp)
                    or detail
                )
            self._ui_status(STEP_VALIDATING_RFID, "error", detail)
            self._announce(MSG_RFID_ERR)
            logger.info("RFID ERR 1 - waiting %ss", TIMEOUTS.RFID_ERROR_DISPLAY_SEC)
            time.sleep(TIMEOUTS.RFID_ERROR_DISPLAY_SEC)
            sm.trigger(Event.RFID_ERROR_TIMEOUT)
            self._reset_to_idle()
            return

        sm.trigger(Event.RFID_VALID)  # -> DISPLAY_TRUCK
        self._ui_status(STEP_VALIDATING_RFID, "success", f"Truck No: {txn.vehicle_no or txn.validated_rfid}")
        self._ui_rfid(txn.validated_rfid, txn.vehicle_no or None)
        self._announce(txn.vehicle_no or txn.validated_rfid)

        # Operator may disable ANPR: skip /api/detect; invalid-truck anpr_status=2.
        # Status-check only for CE trips (all ANPR paths); non-CE disabled grants.
        if not bool(getattr(settings, "anpr_enabled", True)):
            logger.info(
                "ANPR disabled - skipping /api/detect; invalid-truck anpr_status=2"
            )
            self._ui_status(
                STEP_VALIDATING_ANPR,
                "success",
                "ANPR skipped (disabled by operator).",
            )
            txn.anpr_status = 2
            txn.anpr_raw = {
                "vehicleNo_web": txn.vehicle_no or "",
                "vehicleNo_anpr": "",
                "rfid": txn.validated_rfid or "",
                "device_ip": txn.device_ip or settings.device_ip,
                "anpr_status": 2,
            }
            invalid_resp = oci.invalid_truck_number(
                rfid=txn.validated_rfid,
                truck_number=txn.vehicle_no,
                device_ip=txn.device_ip or settings.device_ip,
                anpr_payload=txn.anpr_raw,
                token=txn.token_no,
                anpr_status=2,
            )
            if is_api_failure(invalid_resp):
                self._ui_api_failure(
                    STEP_VALIDATING_ANPR,
                    invalid_resp,
                    fallback="Invalid-truck service not reachable",
                )
            if is_ce_truck_details(txn.truck_details or ""):
                sm.trigger(Event.ANPR_MISMATCH)
                self._ce_check_status_loop(sm, txn, oci, settings.device_ip)
                return
            sm.trigger(Event.ANPR_MATCH)
            self._do_grant_entry(txn.truck_no or txn.vehicle_no)
            return

        self._ui_status(STEP_VALIDATING_ANPR, "info", "ANPR validation in progress.")

        # ANPR with up to 3 retries on exception / transport failure
        anpr = self._call_anpr_with_retry(
            oci,
            vehicle_number=txn.vehicle_no,
            rfid=txn.validated_rfid,
            token_no=txn.token_no,
        )
        if anpr is None or is_api_failure(anpr):
            self._announce(MSG_ANPR_API_ERR)
            if anpr is not None:
                self._ui_api_failure(
                    STEP_VALIDATING_ANPR, anpr, fallback="ANPR not reachable"
                )
            else:
                short, title = operator_copy("anpr-detect", KIND_UNREACHABLE)
                self._ui_status(
                    STEP_VALIDATING_ANPR,
                    "error",
                    short,
                    popup=True,
                    popup_title=title,
                )
            logger.error(
                "ANPR API failed after %s retries - reset to IDLE",
                TIMEOUTS.ANPR_API_MAX_RETRIES,
            )
            time.sleep(TIMEOUTS.ANPR_ERR_2_DISPLAY_SEC)
            self._reset_to_idle()
            return

        txn.anpr_status = anpr.status
        txn.anpr_raw = anpr.raw

        # Always invalid-truck. Status-check: CE → all ANPR 0/1/2 (statusCode 200 loop);
        # non-CE → only mismatch 0/2 (vehicleStatus loop); match grants without it.
        sm.trigger(Event.ANPR_MISMATCH)
        invalid_resp = oci.invalid_truck_number(
            rfid=txn.validated_rfid,
            truck_number=txn.vehicle_no,
            device_ip=txn.device_ip or settings.device_ip,
            anpr_payload=anpr.raw,
            token=txn.token_no,
            anpr_status=anpr.status,
        )
        if is_api_failure(invalid_resp):
            self._ui_api_failure(
                STEP_VALIDATING_ANPR,
                invalid_resp,
                fallback="Invalid-truck service not reachable",
            )

        if is_ce_truck_details(txn.truck_details or ""):
            if anpr.status == 1:
                self._ui_status(STEP_VALIDATING_ANPR, "success", "ANPR matched.")
            elif anpr.status == 2:
                self._announce(MSG_ANPR_ERR_2)
                self._ui_status(
                    STEP_VALIDATING_ANPR,
                    "warning",
                    "ANPR Err-2, Number not readable",
                )
            else:
                self._announce(MSG_ANPR_ERR)
                self._ui_status(
                    STEP_VALIDATING_ANPR,
                    "warning",
                    "ANPR Err-0, Number plate mismatch",
                )
            self._ce_check_status_loop(sm, txn, oci, settings.device_ip)
            return

        if anpr.status == 1:
            self._ui_status(STEP_VALIDATING_ANPR, "success", "ANPR matched.")
            sm.trigger(Event.ANPR_MATCH)
            self._do_grant_entry(txn.truck_no or txn.vehicle_no)
            return

        if anpr.status == 2:
            self._announce(MSG_ANPR_ERR_2)
            self._ui_status(
                STEP_VALIDATING_ANPR,
                "warning",
                "ANPR Err-2, Number not readable",
            )
        else:
            self._announce(MSG_ANPR_ERR)
            self._ui_status(
                STEP_VALIDATING_ANPR,
                "warning",
                "ANPR Err-0, Number plate mismatch",
            )
        if anpr.status in (0, 2):
            self._manual_update_loop(sm, txn, oci, settings.device_ip)

    def _call_anpr_with_retry(
        self,
        oci,
        *,
        vehicle_number: str,
        rfid: str,
        token_no: str = "",
        device_ip: str = "",
    ):
        """
        Call ANPR detect up to ANPR_API_MAX_RETRIES times.
        Retries on raised Exception or transport failure (http_status == 0).
        Returns OCIResponse on success, None if all retries fail.
        """
        max_retries = int(TIMEOUTS.ANPR_API_MAX_RETRIES)
        delay_sec = float(TIMEOUTS.ANPR_API_RETRY_DELAY_SEC)
        last_error: Optional[str] = None
        last_resp = None

        for attempt in range(1, max_retries + 1):
            try:
                resp = oci.anpr_detect(
                    vehicle_number=vehicle_number,
                    rfid=rfid,
                    token_no=token_no,
                    device_ip=device_ip,
                )
                last_resp = resp
                # _post maps RequestException -> http_status=0 and empty raw
                if is_transport_failure(resp):
                    raise ConnectionError(
                        getattr(resp, "operator_message", None)
                        or "ANPR not reachable"
                    )
                logger.info(
                    "ANPR API OK on attempt %s/%s status=%s",
                    attempt,
                    max_retries,
                    resp.status,
                )
                return resp
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "ANPR API exception attempt %s/%s: %s",
                    attempt,
                    max_retries,
                    e,
                )
                if attempt < max_retries:
                    time.sleep(delay_sec)

        logger.error(
            "ANPR API exhausted %s retries. last_error=%s",
            max_retries,
            last_error,
        )
        return last_resp

    def _status_check_retry_sec(self) -> float:
        settings = self.ctx.settings
        retry_sec = float(
            getattr(settings, "truck_anpr_retry_timer", None)
            or TIMEOUTS.MANUAL_UPDATE_POLL_SEC
        )
        if retry_sec <= 0:
            retry_sec = TIMEOUTS.MANUAL_UPDATE_POLL_SEC
        return retry_sec

    def _ce_check_status_loop(self, sm, txn, oci, device_ip: str) -> None:
        """
        CE| truck_details: after invalid-truck, poll check-status until
        JSON statusCode == 200 (ANPR match or mismatch), then grant entry.
        """
        retry_sec = self._status_check_retry_sec()
        logger.info(
            "CE trip - polling check-status until statusCode=200 (every %ss)",
            retry_sec,
        )
        self._ui_status(
            STEP_VALIDATING_ANPR,
            "info",
            "Waiting for check-status (CE)…",
        )
        while not self._manual_stop.is_set():
            if sm.current_state != State.MANUAL_UPDATE:
                break
            resp = oci.update_truck_number(
                rfid=txn.validated_rfid,
                truck_number=txn.vehicle_no,
                device_ip=txn.device_ip or device_ip,
                anpr_payload=txn.anpr_raw,
            )
            code = status_code_from_response(resp)
            logger.info(
                "CE check-status statusCode=%s http=%s message=%s",
                code,
                getattr(resp, "http_status", None),
                resp.raw.get("statusMessage") or resp.message,
            )

            if code == 200:
                if resp.raw.get("truck_number") or resp.raw.get("vehicleNo_web"):
                    txn.truck_no = str(
                        resp.raw.get("truck_number")
                        or resp.raw.get("vehicleNo_web")
                    )
                    txn.vehicle_no = txn.truck_no
                sm.trigger(Event.UPDATE_STATUS_1)
                self._do_grant_entry(txn.truck_no or txn.vehicle_no)
                return

            if is_api_failure(resp) and is_service_alert(resp):
                if not self._status_check_alerted:
                    self._status_check_alerted = True
                    self._ui_api_failure(
                        STEP_VALIDATING_ANPR,
                        resp,
                        fallback="Status-check service not reachable",
                    )
            else:
                self._ui_anpr_waiting(txn)

            sm.trigger(Event.UPDATE_STATUS_0)
            time.sleep(retry_sec)

        logger.info("CE check-status loop stopped")

    def _manual_update_loop(self, sm, txn, oci, device_ip: str) -> None:
        """
        Non-CE: poll status_check every truck_anpr_retry_timer seconds while
        vehicleStatus == 0. Grant on 1, reset on 2.
        """
        retry_sec = self._status_check_retry_sec()

        logger.info(
            "Entering manual truck update loop (retry every %ss while vehicleStatus=0)",
            retry_sec,
        )
        while not self._manual_stop.is_set():
            if sm.current_state != State.MANUAL_UPDATE:
                break
            resp = oci.update_truck_number(
                rfid=txn.validated_rfid,
                truck_number=txn.vehicle_no,
                device_ip=txn.device_ip or device_ip,
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
                sm.trigger(Event.UPDATE_STATUS_0)
                time.sleep(retry_sec)
                continue

            vehicle_status = resp.status
            if "vehicleStatus" in resp.raw:
                try:
                    vehicle_status = int(resp.raw["vehicleStatus"])
                except (TypeError, ValueError):
                    vehicle_status = resp.status

            logger.info(
                "status_check vehicleStatus=%s message=%s",
                vehicle_status,
                resp.raw.get("statusMessage") or resp.message,
            )

            if vehicle_status == 1:
                if resp.raw.get("truck_number") or resp.raw.get("vehicleNo_web"):
                    txn.truck_no = str(
                        resp.raw.get("truck_number")
                        or resp.raw.get("vehicleNo_web")
                    )
                    txn.vehicle_no = txn.truck_no
                sm.trigger(Event.UPDATE_STATUS_1)
                self._do_grant_entry(txn.truck_no or txn.vehicle_no)
                return

            if vehicle_status == 2:
                sm.trigger(Event.UPDATE_STATUS_2)
                logger.info(
                    "vehicleStatus 2 - wait %ss then reset",
                    TIMEOUTS.UPDATE_STATUS_2_RESET_SEC,
                )
                self._ui_status(
                    STEP_VALIDATING_ANPR,
                    "error",
                    str(
                        resp.raw.get("statusMessage")
                        or resp.message
                        or "Check-status rejected this vehicle."
                    ),
                )
                time.sleep(TIMEOUTS.UPDATE_STATUS_2_RESET_SEC)
                self._reset_to_idle()
                return

            # vehicleStatus == 0 (or unknown): keep retrying
            self._ui_anpr_waiting(txn)
            sm.trigger(Event.UPDATE_STATUS_0)
            logger.info(
                "vehicleStatus=0 - retry status_check in %ss", retry_sec
            )
            time.sleep(retry_sec)

        logger.info("Manual update loop stopped")

    def _do_grant_entry(self, truck_no: str) -> None:
        sm = self.ctx.state_machine
        txn = self.ctx.transactions.current if self.ctx.transactions else None
        if txn:
            txn.granted = True
            txn.truck_no = truck_no or txn.truck_no
        close_resp = self.grant_entry_hardware(truck_no)
        self._ui_position(2)
        if close_resp is not None and close_resp.status != 200:
            self._ui_api_failure(
                STEP_ENTRY_GRANTED,
                close_resp,
                fallback="Boom-close rejected.",
            )
        else:
            self._ui_status(
                STEP_ENTRY_GRANTED,
                "success",
                f"{truck_no or 'TRUCK'} Entry Granted",
            )
        if sm and sm.current_state == State.ENTRY_GRANTED:
            sm.trigger(Event.ENTRY_OPENED)  # -> WAIT_CROSSING
        elif sm:
            sm.force_state(State.WAIT_CROSSING)
        self._ui_status(
            STEP_WAIT_CROSSING,
            "info",
            "Waiting for vehicle to clear entry sensor.",
        )
        self._ui_devices()
        timeout_sec = self._crossing_timeout_sec()
        logger.info(
            "Waiting for truck to pass entry sensor "
            "(TRUE while on sensor, then FALSE to close boom; "
            "auto IDLE in %ss if no clear)",
            timeout_sec,
        )
        self._start_crossing_timer(timeout_sec)

    def _crossing_timeout_sec(self) -> float:
        settings = self.ctx.settings
        sec = float(
            getattr(settings, "vehicle_crossing_timeout", None)
            or TIMEOUTS.VEHICLE_CROSSING_TIMEOUT_SEC
        )
        return sec if sec > 0 else TIMEOUTS.VEHICLE_CROSSING_TIMEOUT_SEC

    def _start_crossing_timer(self, timeout_sec: float) -> None:
        self._cancel_crossing_timer()

        def _on_timeout():
            sm = self.ctx.state_machine
            if not sm:
                return
            if sm.current_state not in (State.ENTRY_GRANTED, State.WAIT_CROSSING):
                logger.debug(
                    "Crossing timeout ignored - state is %s",
                    sm.current_state.name,
                )
                return
            logger.info(
                "Vehicle crossing timeout (%ss) - auto reset to IDLE",
                timeout_sec,
            )
            sm.trigger(Event.CROSSING_TIMEOUT)
            self._reset_to_idle()

        timer = threading.Timer(timeout_sec, _on_timeout)
        timer.daemon = True
        with self._crossing_timer_lock:
            self._crossing_timer = timer
            timer.start()
        logger.info("Started vehicle crossing timer (%ss)", timeout_sec)

    def _cancel_crossing_timer(self) -> None:
        with self._crossing_timer_lock:
            timer = self._crossing_timer
            self._crossing_timer = None
        if timer is not None:
            timer.cancel()
            logger.debug("Cancelled vehicle crossing timer")
