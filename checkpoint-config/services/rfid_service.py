import socket
import threading
import time
import re
import logging

from utils.timeout_config_loader import load_timeout_config_module

logger = logging.getLogger(__name__)

try:
    from config import PORT as _CONFIG_APP_PORT
except ImportError:
    _CONFIG_APP_PORT = 8080

# API-mode Check & Save: wait this long for Zebra POST /rfid_data
RFID_API_WAIT_SEC = 120


def _load_rfid_recv_size() -> int:
    """
    Load RFID socket recv buffer size from editable timeout_config.py.
    Falls back safely to 1024 if file/module is unavailable.
    """
    default_size = 1024
    module = load_timeout_config_module()
    if module is not None:
        timeouts = getattr(module, "TIMEOUTS", None)
        if timeouts is not None:
            try:
                value = int(
                    getattr(
                        timeouts,
                        "RFID_SOCKET_RECV_SIZE",
                        getattr(timeouts, "RFID_BUFFER_SIZE", default_size),
                    )
                )
                return value if value > 0 else default_size
            except (TypeError, ValueError):
                pass
    return default_size


RFID_SOCKET_RECV_SIZE = _load_rfid_recv_size()

FASTAG_RFID_HEX_LENGTH = 24
_DEFAULT_VALID_CARDS_START_INDEX = []
_DEFAULT_VALID_CARD_CHAR_LENGTHS = [24, 32]
_INVALID_FASTAG_MESSAGE = "The given data is not a valid fastag"


def get_valid_cards_start_index() -> list:
    """Return VALID_CARDS_START_INDEX from editable timeout_config.py."""
    module = load_timeout_config_module()
    if module is not None:
        prefixes = getattr(module, "VALID_CARDS_START_INDEX", None)
        if isinstance(prefixes, (list, tuple)) and prefixes:
            return [str(p).strip() for p in prefixes if str(p).strip()]
    return list(_DEFAULT_VALID_CARDS_START_INDEX)


def get_valid_card_char_lengths() -> list:
    """
    Return accepted RFID/FASTag hex lengths (CHAR_LENGTH) from editable timeout_config.py.
    Values are coerced to a sorted list of positive ints (e.g. [24, 32]).
    """
    module = load_timeout_config_module()
    lengths: list = []
    if module is not None:
        raw = getattr(module, "CHAR_LENGTH", None)
        if isinstance(raw, (list, tuple)):
            for item in raw:
                try:
                    value = int(str(item).strip())
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    lengths.append(value)
    if not lengths:
        lengths = list(_DEFAULT_VALID_CARD_CHAR_LENGTHS)
    return sorted(set(lengths))


def validate_fastag_rfid_tag(tag: str) -> str | None:
    """
    Validate vendor-application RFID for calibration save.
    Returns an error message, or None when valid.
    """
    if tag is None:
        return "Please enter RFID value from vendor application."

    normalized = "".join(c for c in str(tag).strip().upper() if c in "0123456789ABCDEF")
    if not normalized:
        return "Please enter RFID value from vendor application."
    if not re.fullmatch(r"[0-9A-F]+", normalized):
        return "RFID must contain only hexadecimal characters (0-9, A-F)."
    valid_lengths = get_valid_card_char_lengths()
    if len(normalized) not in valid_lengths:
        allowed = " or ".join(str(n) for n in valid_lengths)
        return f"RFID must be exactly {allowed} hexadecimal characters."
    prefixes = get_valid_cards_start_index()
    if not any(normalized.startswith(p.upper()) for p in prefixes):
        return _INVALID_FASTAG_MESSAGE
    return None


def validate_rfid_reader_calibration(data: dict) -> str | None:
    """Validate manual_match_sample on an RFID reader config dict."""
    if not isinstance(data, dict):
        return None
    sample = (data.get("manual_match_sample") or "").strip()
    if not sample:
        return None
    return validate_fastag_rfid_tag(sample)


def validate_rfid_section_save(section: str, data: dict) -> str | None:
    """
    Validate RFID calibration fields when saving /api/config/<section>.
    Returns an error message, or None when valid.
    """
    if section == "rfid":
        return validate_rfid_reader_calibration(data or {})
    if section == "rfids":
        if not isinstance(data, dict):
            return None
        for dir_key in ("entry_a", "entry_b"):
            reader = data.get(dir_key)
            if isinstance(reader, dict):
                err = validate_rfid_reader_calibration(reader)
                if err:
                    return err
    return None


class RFIDService:
    def __init__(self):
        self.rfid_ip = None
        self.port = None
        self.laptop_ip = None
        self.mode = None  # "CLIENT" or "SERVER"
        self.sock = None
        self.client_conn = None
        self.connected = False
        # Card read test status
        self._test_status = {
            "testing": False,
            "time_remaining": 0,
            "card_read": False,
            "card_data": None,
            "card_display": None,
            "parsed_tag": None,
            "test_complete": False,
            "mode": None,  # Store the mode (CLIENT or SERVER) for status polls
            "message": None  # Final message after test completes
        }
        self._test_lock = threading.Lock()
        self._last_check_ip = None
        self._api_cloud_ctrl = None
        self._extract_id_hexes = None
        self._last_check_port = None
        self._api_listen_port = None
        self._temp_push_server = None
        self._temp_push_thread = None
    
    def get_local_ip(self):
        """Get local IP address"""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            logger.info(f"[RFID] Local IP detected: {ip}")
            return ip
        except Exception as e:
            logger.info(f"[RFID] Failed to get local IP: {e}, using 0.0.0.0")
            return "0.0.0.0"
    
    def ping_host(self, ip, timeout=2):
        """Check if host is reachable via socket"""
        logger.info(f"[RFID] Pinging host {ip}...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, 80))
            sock.close()
            logger.info(f"[RFID] Ping result: {result} ({'reachable' if result == 0 else 'not reachable'})")
            return result == 0
        except Exception as e:
            logger.info(f"[RFID] Ping failed: {e}")
            return False
    
    def check_connection(
        self,
        rfid_ip,
        port,
        preferred_mode=None,
        username=None,
        password=None,
        api_port=None,
    ):
        """Check RFID connection with optional preferred mode."""
        logger.info(f"\n{'='*50}")
        logger.info(f"[RFID] Starting connection check...")
        logger.info(f"[RFID] RFID IP: {rfid_ip}, Port: {port}, api_port={api_port}")
        logger.info(f"{'='*50}")

        preferred = (preferred_mode or "").upper()
        if preferred in ("API", "HTTP", "CLOUD", "REST", "HTTPS"):
            return self._try_api_mode(
                rfid_ip, username=username, password=password, api_port=api_port
            )

        if not rfid_ip or not port:
            logger.info("[RFID] ERROR: IP or Port missing!")
            return {
                "status": 400,
                "message": "RFID IP and Port are required"
            }
        
        # IMPORTANT: Stop any existing test/connection before starting new one
        # This prevents old test threads from interfering with new tests
        # Note: reset_test_status() was already called by the API endpoint, but stop() ensures cleanup
        self.stop()
        
        # Small delay to ensure stop() completes and threads exit before starting new test
        time.sleep(0.2)
        
        self.rfid_ip = rfid_ip
        self.port = int(port)
        self.laptop_ip = self.get_local_ip()
        
        logger.info(f"[RFID] Local IP: {self.laptop_ip}")
        
        if preferred in ("CLIENT", "SERVER"):
            logger.info(f"[RFID] Preferred mode from UI/config: {preferred}")
            if preferred == "CLIENT":
                logger.info(f"\n[RFID] === TRYING CLIENT MODE (Application as Client, RFID as Server) ===")
                result = self._try_client_mode_connection_only()
                if result.get("status") == 200:
                    logger.info(f"[RFID] CLIENT MODE CONNECTION SUCCESS!")
                    return {
                        "status": 200,
                        "mode": "CLIENT",
                        "message": "Reader Connected. Waiting for RFID card read (30 seconds)...",
                        "testing": True,
                        "test_complete": False,
                        "card_read": False
                    }
                return result
            else:
                logger.info(f"\n[RFID] === TRYING SERVER MODE (RFID as Client) ===")
                result = self._try_server_mode()
                logger.info(f"[RFID] Server mode result: {result}")
                return result

        # Default / auto: prefer Zebra cloud API (Mine-entry), then legacy TCP.
        api_result = self._try_api_mode(
            rfid_ip, username=username, password=password, api_port=api_port
        )
        if api_result.get("status") == 200:
            return api_result
        logger.info(f"[RFID] API mode failed: {api_result.get('message')}")

        logger.info(f"\n[RFID] === TRYING CLIENT MODE (Application as Client, RFID as Server) ===")
        result = self._try_client_mode_connection_only()
        if result["status"] == 200:
            logger.info(f"[RFID] CLIENT MODE CONNECTION SUCCESS!")
            return {
                "status": 200,
                "mode": "CLIENT",
                "message": "Reader Connected. Waiting for RFID card read (30 seconds)...",
                "testing": True,
                "test_complete": False,
                "card_read": False
            }

        logger.info(f"[RFID] Client mode failed: {result['message']}")

        logger.info(f"\n[RFID] === TRYING SERVER MODE (RFID as Client) ===")
        result = self._try_server_mode()
        logger.info(f"[RFID] Server mode result: {result}")
        return result

    def _try_api_mode(self, rfid_ip, username=None, password=None, api_port=None):
        """
        Zebra cloud REST login + mode/start, then wait for tag POST on
        http://{mac_ip}:{RFID_API_PORT}/rfid_data (temporary listener when
        RFID_API_PORT differs from the config UI port).
        """
        if not rfid_ip:
            return {"status": 400, "message": "RFID IP is required for API mode"}

        user = (username or "admin").strip() or "admin"
        pwd = password if password is not None else ""

        try:
            listen_port = int(api_port) if api_port not in (None, "") else int(_CONFIG_APP_PORT)
        except (TypeError, ValueError):
            return {
                "status": 400,
                "mode": "API",
                "message": "RFID_API_PORT must be a valid port number (1–65535).",
            }
        if listen_port < 1 or listen_port > 65535:
            return {
                "status": 400,
                "mode": "API",
                "message": "RFID_API_PORT must be between 1 and 65535.",
            }

        logger.info(
            f"\n[RFID] === TRYING API MODE (Zebra cloud login @ {rfid_ip}, "
            f"RFID_API_PORT={listen_port}) ==="
        )
        self.stop()
        self.rfid_ip = rfid_ip
        self.mode = "API"
        self.laptop_ip = self.get_local_ip()
        self._api_listen_port = listen_port

        try:
            from gmdc_common.services.rfid_control import RFIDCloudControl
            from gmdc_common.hardware.rfid_reader import extract_id_hexes

            self._extract_id_hexes = extract_id_hexes
            ctrl = RFIDCloudControl.from_rfid_ip(rfid_ip, username=user, password=pwd)
            ok = ctrl.login()
            if not ok:
                return {
                    "status": 400,
                    "mode": "API",
                    "message": (
                        "RFID login failed. Check reader IP, username/password, "
                        "and network connectivity."
                    ),
                }

            self._api_cloud_ctrl = ctrl

            # Temporary (or reuse main) HTTP endpoints for Zebra push
            started, start_err = self._start_temp_rfid_push_server(listen_port)
            if not started:
                return {
                    "status": 500,
                    "mode": "API",
                    "message": start_err
                    or f"Could not listen on port {listen_port} for /rfid_data",
                }

            with self._test_lock:
                self._test_status = {
                    "testing": True,
                    "time_remaining": RFID_API_WAIT_SEC,
                    "card_read": False,
                    "card_data": None,
                    "card_display": None,
                    "parsed_tag": None,
                    "test_complete": False,
                    "mode": "API",
                    "message": None,
                    "api_port": listen_port,
                }

            push_url = f"http://{self.laptop_ip}:{listen_port}/rfid_data"
            mgmt_url = f"http://{self.laptop_ip}:{listen_port}/rfid_management"
            logger.info("[RFID][API] Expecting tag push at %s", push_url)
            logger.info("[RFID][API] Management keepalive at %s", mgmt_url)
            with self._test_lock:
                self._test_status["push_url"] = push_url
                self._test_status["management_url"] = mgmt_url

            test_thread = threading.Thread(target=self._run_api_tag_wait_test, daemon=True)
            test_thread.start()

            return {
                "status": 200,
                "mode": "API",
                "message": (
                    f"Reader connected. Waiting for RFID data ({RFID_API_WAIT_SEC} seconds)... "
                    f"POST tags to {push_url}"
                ),
                "testing": True,
                "test_complete": False,
                "card_read": False,
                "time_remaining": RFID_API_WAIT_SEC,
                "push_url": push_url,
                "management_url": mgmt_url,
                "api_port": listen_port,
            }
        except ImportError:
            logger.exception("[RFID] gmdc_common not installed")
            self._stop_temp_rfid_push_server()
            return {
                "status": 500,
                "mode": "API",
                "message": "gmdc_common is not installed. Run: pip install -e ../gmdc_common",
            }
        except Exception as e:
            logger.exception("[RFID] API mode check failed")
            self._stop_temp_rfid_push_server()
            return {
                "status": 400,
                "mode": "API",
                "message": f"API mode check failed: {e}",
            }

    def _start_temp_rfid_push_server(self, listen_port: int):
        """
        Bind temporary /rfid_data + /rfid_management on listen_port.

        If listen_port is the main checkpoint-config PORT, reuse the existing
        Flask routes (already registered) and do not start a second server.
        """
        self._stop_temp_rfid_push_server()
        if int(listen_port) == int(_CONFIG_APP_PORT):
            logger.info(
                "[RFID][API] Using main app port %s for /rfid_data "
                "(no temporary server)",
                listen_port,
            )
            return True, None

        try:
            from flask import Flask, jsonify, request
            from werkzeug.serving import make_server
        except ImportError as e:
            return False, f"Flask/Werkzeug required for temporary RFID API: {e}"

        # Probe bind before starting
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("0.0.0.0", int(listen_port)))
        except OSError as e:
            probe.close()
            return (
                False,
                f"Port {listen_port} is not available ({e}). "
                "Choose another RFID_API_PORT or free the port.",
            )
        finally:
            try:
                probe.close()
            except Exception:
                pass

        app = Flask("gmdc_rfid_temp_push")

        @app.post("/rfid_data")
        def _temp_rfid_data():
            try:
                payload = request.get_json(force=True, silent=False)
            except Exception as exc:
                return jsonify({"status": "error", "message": str(exc)}), 400
            if payload is None:
                return jsonify({"status": "error", "message": "Empty body"}), 400
            logger.info(
                "[RFID][API][temp] POST /rfid_data from %s",
                request.remote_addr,
            )
            http_status, body = self.accept_api_payload(payload)
            return jsonify(body), http_status

        @app.route("/rfid_management", methods=["GET", "POST"])
        def _temp_rfid_management():
            logger.debug(
                "[RFID][API][temp] /rfid_management from %s",
                request.remote_addr,
            )
            return jsonify({"status": "success"}), 200

        try:
            server = make_server("0.0.0.0", int(listen_port), app, threaded=True)
        except OSError as e:
            return False, f"Could not bind RFID_API_PORT {listen_port}: {e}"

        self._temp_push_server = server

        def _serve():
            logger.info(
                "[RFID][API] Temporary push server listening on 0.0.0.0:%s "
                "(/rfid_data, /rfid_management)",
                listen_port,
            )
            try:
                server.serve_forever()
            except Exception:
                logger.exception("[RFID][API] Temporary push server stopped with error")

        self._temp_push_thread = threading.Thread(
            target=_serve, name="RfidTempPush", daemon=True
        )
        self._temp_push_thread.start()
        time.sleep(0.15)
        return True, None

    def _stop_temp_rfid_push_server(self):
        server = self._temp_push_server
        self._temp_push_server = None
        self._temp_push_thread = None
        if not server:
            return
        try:
            server.shutdown()
        except Exception:
            logger.debug("[RFID][API] temp server shutdown error", exc_info=True)
        try:
            server.server_close()
        except Exception:
            pass
        logger.info("[RFID][API] Temporary push server stopped")

    def accept_api_payload(self, payload):
        """
        Accept Zebra POST /rfid_data during API wait window.
        Returns (http_status, body_dict).
        """
        try:
            from gmdc_common.hardware.rfid_reader import extract_id_hexes
        except ImportError:
            extract_id_hexes = getattr(self, "_extract_id_hexes", None)
            if not extract_id_hexes:
                return 500, {"status": "error", "message": "gmdc_common not available"}

        with self._test_lock:
            testing = self._test_status.get("testing") and self._test_status.get("mode") == "API"
            already = self._test_status.get("card_read")

        if not testing:
            return 200, {"status": "ignored", "message": "Not waiting for RFID data"}

        if already:
            return 200, {"status": "success", "message": "Already received"}

        id_hexes = extract_id_hexes(payload)
        if not id_hexes:
            return 400, {"status": "error", "message": "No RFID tag data found in payload"}

        tag = str(id_hexes[0]).strip().upper()
        logger.info("[RFID][API] Tag received via /rfid_data: %s", tag)

        with self._test_lock:
            if not (self._test_status.get("testing") and self._test_status.get("mode") == "API"):
                return 200, {"status": "ignored", "message": "Wait ended"}
            self._test_status["card_read"] = True
            self._test_status["parsed_tag"] = tag
            self._test_status["card_data"] = tag
            self._test_status["card_display"] = tag
            self._test_status["testing"] = False  # signal wait loop to finish
            self._test_status["test_complete"] = True
            self._test_status["time_remaining"] = 0
            self._test_status["message"] = tag

        # Stop reader inventory (best effort)
        ctrl = getattr(self, "_api_cloud_ctrl", None)
        if ctrl:
            try:
                ctrl.stop()
            except Exception:
                logger.exception("[RFID][API] cloud stop after tag failed")

        return 200, {"status": "success", "tags": id_hexes}

    def _run_api_tag_wait_test(self):
        """Wait for POST /rfid_data while reader inventory runs (RFID_API_WAIT_SEC)."""
        try:
            logger.info(
                "[RFID][API] Starting %s-second wait for RFID data...",
                RFID_API_WAIT_SEC,
            )
            ctrl = getattr(self, "_api_cloud_ctrl", None)
            if ctrl:
                try:
                    # login already done; set mode + start scanning
                    if not ctrl.set_mode():
                        logger.warning("[RFID][API] set_mode failed - still waiting for push")
                    elif not ctrl.start():
                        logger.warning("[RFID][API] start failed - still waiting for push")
                    else:
                        logger.info("[RFID][API] Reader inventory started")
                except Exception:
                    logger.exception("[RFID][API] prepare inventory failed")

            end_time = time.time() + float(RFID_API_WAIT_SEC)
            while time.time() < end_time:
                with self._test_lock:
                    if not self._test_status.get("testing", False):
                        break
                    if self._test_status.get("card_read"):
                        break
                    remaining = max(0, int(end_time - time.time()))
                    self._test_status["time_remaining"] = remaining
                time.sleep(0.25)

            with self._test_lock:
                card_read = bool(self._test_status.get("card_read"))
                tag = self._test_status.get("parsed_tag") or self._test_status.get("card_data")
                self._test_status["testing"] = False
                self._test_status["time_remaining"] = 0
                self._test_status["test_complete"] = True
                if card_read:
                    self._test_status["message"] = tag
                    logger.info("[RFID][API] Wait complete - tag=%s", tag)
                else:
                    self._test_status["message"] = "No RFID data received. Please try again."
                    logger.info(
                        "[RFID][API] Wait complete - no tag within %s seconds",
                        RFID_API_WAIT_SEC,
                    )

            # Ensure inventory stopped if timed out
            if not card_read and ctrl:
                try:
                    ctrl.stop()
                except Exception:
                    logger.exception("[RFID][API] cloud stop on timeout failed")
        except Exception:
            logger.exception("[RFID][API] tag wait test error")
            with self._test_lock:
                self._test_status["testing"] = False
                self._test_status["time_remaining"] = 0
                self._test_status["test_complete"] = True
                self._test_status["card_read"] = False
                self._test_status["message"] = "RFID wait failed. Please try again."
        finally:
            self._stop_temp_rfid_push_server()
    
    def _try_client_mode_connection_only(self):
        """Try connecting as client (RFID is server) - connection test only"""
        try:
            logger.info(f"[RFID] Testing TCP connection to {self.rfid_ip}:{self.port}...")
            
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(5)  # 5 second timeout for connection
            test_sock.connect((self.rfid_ip, self.port))
            test_sock.close()
            
            self.mode = "CLIENT"
            
            logger.info(f"[RFID] TCP connection SUCCESS - RFID reader is online!")
            logger.info(f"[RFID] RFID is Server, Application will be Client")
            
            # IMPORTANT: Initialize test status BEFORE starting thread
            # This prevents the thread from immediately exiting due to testing=False from stop()
            with self._test_lock:
                self._test_status = {
                    "testing": True,  # Set to True BEFORE starting thread
                    "time_remaining": 30,
                    "card_read": False,
                    "card_data": None,
                    "card_display": None,
                    "parsed_tag": None,
                    "test_complete": False,
                    "mode": "CLIENT",
                    "message": None
                }
            
            # Small delay to ensure status is fully set before thread starts
            time.sleep(0.1)
            
            # Start the card read test in background thread
            test_thread = threading.Thread(target=self._run_card_read_test, daemon=True)
            test_thread.start()
            
            return {
                "status": 200,
                "mode": "CLIENT"
            }
            
        except socket.timeout:
            logger.info(f"[RFID] Connection timeout - RFID not responding")
            return {
                "status": 408,
                "mode": "CLIENT",
                "message": "Connection timeout - RFID reader not responding"
            }
        except ConnectionRefusedError:
            logger.info(f"[RFID] Connection refused - RFID not accepting connections")
            return {
                "status": 500,
                "mode": "CLIENT",
                "message": "Connection refused - RFID not accepting connections as server"
            }
        except Exception as e:
            logger.exception("[RFID] Client mode connection failed")
            return {
                "status": 500,
                "mode": "CLIENT",
                "message": "RFID connection failed. Please verify reader IP/port and network."
            }
    
    def _is_valid_rfid_data(self, data):
        """
        Validate if received data is actual RFID data (not connection messages).
        
        This matches the logic from Weighbridge-App to filter out connection
        acknowledgment messages like "TCP Server Connected!".
        
        Valid RFID data examples:
        - "34161" (numeric string)
        - "E200..." (hex string starting with E2)
        - Binary data that looks like RFID (hex patterns)
        
        Invalid (connection messages):
        - "TCP Server Connected!"
        - "Tcp Server Connected!"
        - "TcpServerConnected!"
        - "Connection established"
        - Other status messages
        """
        if not data or len(data) == 0:
            return False
        
        try:
            # Try to decode as string to check for connection ack messages
            # This matches Weighbridge-App logic
            try:
                decoded = data.decode('ascii', errors='ignore').strip()
                # Remove whitespace for comparison (handles "Tcp Server Connected!" vs "TcpServerConnected!")
                decoded_clean = "".join(decoded.split())
                
                # Connection acknowledgment messages to ignore (case-insensitive)
                # These match Weighbridge-App's _connection_ack_messages
                connection_ack_messages = [
                    "TcpServerConnected!",
                    "Tcp Server Connected!",
                    "TCP Server Connected!",
                    "Connected",
                    "Server Connected",
                    "connection established",
                    "server ready",
                    "listening",
                    "waiting for connection"
                ]
                
                # Check if it matches any known connection ack messages
                is_ack = any(
                    ack_msg.lower() in decoded_clean.lower() or 
                    decoded_clean.lower() in ack_msg.lower() 
                    for ack_msg in connection_ack_messages
                )
                
                if is_ack:
                    return False
            except:
                # If decode fails, it's likely binary RFID data, not a text ack
                # Continue to check if it's valid RFID data
                pass
            
            # Now check if it's valid RFID data
            try:
                text = data.decode('ascii', errors='ignore').strip()
                
                # Check if it's numeric (like "34161")
                if text.isdigit() and len(text) >= 4:
                    logger.info(f"[RFID] Valid RFID data (numeric): {text}")
                    return True
                
                # Check if it's a hex string (all hex characters, reasonable length)
                if all(c in '0123456789ABCDEFabcdef' for c in text) and len(text) >= 8:
                    logger.info(f"[RFID] Valid RFID data (hex string): {text}")
                    return True
            except:
                pass

            # Identium and similar readers may send framed binary packets
            # containing embedded ASCII-hex EPC/TID values.
            extracted = self._extract_rfid_payload(data)
            if extracted:
                logger.info(f"[RFID] Valid RFID data (embedded payload): {extracted}")
                return True
            
            # Check if it starts with E2 (common RFID prefix)
            hex_str = data.hex().upper()
            if hex_str.startswith('E2') and len(hex_str) >= 8:
                logger.info(f"[RFID] Valid RFID data (E2 prefix): {hex_str[:24]}")
                return True
            
            # Check if binary data has RFID-like patterns (hex digits, reasonable length)
            if len(data) >= 4 and len(data) <= 32:
                # Check if most bytes are printable or common RFID patterns
                hex_data = data.hex().upper()
                if len(hex_data) >= 8 and all(c in '0123456789ABCDEF' for c in hex_data):
                    logger.info(f"[RFID] Valid RFID data (binary/hex): {hex_data[:24]}")
                    return True
            
            logger.info(f"[RFID] Data doesn't look like RFID: {data.hex()[:50]}")
            return False
            
        except Exception as e:
            logger.info(f"[RFID] Error validating RFID data: {e}")
            # If we can't validate, assume it might be valid (better to accept than reject)
            return len(data) >= 4

    def _extract_rfid_payload(self, data):
        """
        Try to extract RFID payload (EPC/TID-like hex token) from raw packet.

        Handles plain ASCII readers and framed binary packets that contain
        ASCII-hex payload segments (common with Identium integrations).
        """
        if not data:
            return None

        # 1) Direct ASCII text token scan
        try:
            ascii_text = data.decode('ascii', errors='ignore').strip()
            ascii_tokens = re.findall(r'[0-9A-Fa-f]{8,32}', ascii_text)
            if ascii_tokens:
                preferred = next(
                    (t for t in ascii_tokens if t.upper().startswith(("E2", "C0"))),
                    ascii_tokens[0]
                )
                return preferred.upper()
        except Exception:
            pass

        # 2) Identium framed packets often contain EPC blocks as:
        #    ... 05 0C <12-byte EPC> ...
        #    Example EPCs in your packets:
        #      E200002046100107162051E9
        #      C00000000000000006000228
        raw_hex = data.hex().upper()
        framed_epc_tokens = re.findall(r'050C([0-9A-F]{24})', raw_hex)
        if framed_epc_tokens:
            preferred = next(
                (t for t in framed_epc_tokens if t.startswith(("E2", "C0"))),
                framed_epc_tokens[0]
            )
            return preferred

        # 3) Scan raw bytes for embedded ASCII-hex runs (byte range for 0-9A-Fa-f)
        byte_tokens = re.findall(rb'[0-9A-Fa-f]{8,32}', data)
        if byte_tokens:
            normalized = [t.decode('ascii', errors='ignore').upper() for t in byte_tokens]
            preferred = next((t for t in normalized if t.startswith(("E2", "C0"))), normalized[0])
            return preferred

        return None

    def _to_human_readable_data(self, data):
        """
        Convert raw socket bytes for calibration modal.
        - If payload is clearly plain ASCII hex RFID text, show decoded text.
        - Otherwise show full raw HEX frame.
        """
        if not data:
            return None
        try:
            decoded = data.decode('ascii', errors='ignore').replace('\r', '').replace('\n', '').strip()
            # Use decoded text only when it is a clean ASCII-hex token
            # (example: E200001D7507013115006BB9). For framed/binary packets,
            # always return raw hex so installer sees complete frame data.
            if decoded and re.fullmatch(r'[0-9A-Fa-f]{8,64}', decoded):
                return decoded.upper()
        except Exception:
            pass
        return data.hex().upper()
    
    def _run_card_read_test(self):
        """Run the 30-second card read test in background thread (CLIENT mode)"""
        try:
            logger.info(f"[RFID] Starting 30-second card read test in background (CLIENT mode)...")
            
            # Verify test status (should already be initialized before thread starts)
            # Check if test was stopped (by new check_connection call)
            with self._test_lock:
                if not self._test_status.get("testing", False):
                    logger.info(f"[RFID] Test was stopped, exiting...")
                    return
                # Ensure status is correct (should already be set, but verify)
                if self._test_status.get("mode") != "CLIENT":
                    self._test_status["mode"] = "CLIENT"
                if self._test_status.get("time_remaining", 0) != 30:
                    self._test_status["time_remaining"] = 30
            
            # Identium readers often publish data right after TCP connect and may close.
            # So we reconnect in a loop until timeout, similar to the working test client.
            start_time = time.time()
            test_duration = 30.0
            card_read = False
            card_data = None
            card_display = None
            parsed_tag = None
            connection_ack_received = False  # Track if we've received connection ack
            last_wait_log = 0
            connect_attempt = 0
            
            while time.time() - start_time < test_duration:
                # Check if test was stopped
                with self._test_lock:
                    if not self._test_status.get("testing", True):
                        logger.info(f"[RFID] Test was stopped during execution, exiting...")
                        break
                
                remaining = int(test_duration - (time.time() - start_time))
                
                # Update status
                with self._test_lock:
                    self._test_status["time_remaining"] = remaining
                
                try:
                    # (Re)connect if needed
                    if not self.sock:
                        connect_attempt += 1
                        logger.info(f"[RFID][CLIENT] Connect attempt #{connect_attempt} to {self.rfid_ip}:{self.port}")
                        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self.sock.settimeout(5)
                        self.sock.connect((self.rfid_ip, self.port))
                        self.connected = True
                        connection_ack_received = False
                        logger.info(f"[RFID][CLIENT] Connected. Waiting for RFID card data...")

                    # Receive data (short timeout so we can update status/stop quickly)
                    self.sock.settimeout(1.0)
                    data = self.sock.recv(RFID_SOCKET_RECV_SIZE)
                    if not data:
                        # Reader closed connection; reconnect and continue
                        try:
                            self.sock.close()
                        except:
                            pass
                        self.sock = None
                        self.connected = False
                        logger.info(f"[RFID][CLIENT] recv returned empty bytes (remote closed). Reconnecting...")
                        continue

                    if data and len(data) > 0:
                        logger.info(f"[RFID][CLIENT] Raw data received ({len(data)} bytes)")
                        logger.info(f"[RFID][CLIENT] Raw HEX: {data.hex()}")
                        # First, check if this is a connection acknowledgment (skip it)
                        if not connection_ack_received:
                            # Check if it's a connection ack message
                            try:
                                decoded = data.decode('ascii', errors='ignore').strip()
                                decoded_clean = "".join(decoded.split())
                                connection_ack_messages = [
                                    "TcpServerConnected!",
                                    "Tcp Server Connected!",
                                    "TCP Server Connected!",
                                    "Connected",
                                    "Server Connected"
                                ]
                                is_ack = any(
                                    ack_msg.lower() in decoded_clean.lower() or 
                                    decoded_clean.lower() in ack_msg.lower() 
                                    for ack_msg in connection_ack_messages
                                )
                                if is_ack:
                                    connection_ack_received = True
                                    continue  # Skip this message, wait for actual RFID data
                            except:
                                # If decode fails, it's likely binary RFID data
                                pass
                            connection_ack_received = True
                        
                        # Validate if it's actual RFID data (not connection message)
                        if self._is_valid_rfid_data(data):
                            extracted = self._extract_rfid_payload(data)
                            parsed_tag = extracted
                            card_data = data.hex().upper()
                            card_display = self._to_human_readable_data(data)
                            card_read = True
                            logger.info(f"[RFID][CLIENT] Raw hex data: {card_data}")
                            logger.info(f"[RFID][CLIENT] Human-readable data: {card_display}")
                            logger.info(f"[RFID][CLIENT] Parsed RFID payload: {parsed_tag}")
                            logger.info(f"[RFID][CLIENT] Card read condition met, ending test loop")
                            break
                        else:
                            # Not valid RFID data, continue waiting
                            logger.info(f"[RFID][CLIENT] Received data but not valid RFID, continuing to wait...")
                            continue
                except socket.timeout:
                    # No data received in this second, continue
                    now = time.time()
                    if now - last_wait_log >= 5:
                        logger.info(f"[RFID][CLIENT] Waiting for RFID data... ({remaining}s remaining)")
                        last_wait_log = now
                    continue
                except Exception as e:
                    logger.info(f"[RFID][CLIENT] Error during connect/recv: {type(e).__name__}: {e}")
                    # Drop socket and retry connect in next loop
                    if self.sock:
                        try:
                            self.sock.close()
                        except:
                            pass
                        self.sock = None
                        self.connected = False
                    time.sleep(0.2)
                    continue
            
            # Update final status
            with self._test_lock:
                # Only update if test wasn't stopped
                if self._test_status.get("testing", False):
                    self._test_status["testing"] = False
                    self._test_status["card_read"] = card_read
                    self._test_status["card_data"] = card_data
                    self._test_status["card_display"] = card_display
                    self._test_status["parsed_tag"] = parsed_tag
                    self._test_status["test_complete"] = True
                    self._test_status["time_remaining"] = 0
                    
                    if card_read:
                        self._test_status["message"] = "Reader Connected and Valid RFID received"
                    else:
                        self._test_status["message"] = "Reader Connected, but no card read"
                    logger.info(f"[RFID][CLIENT] Final test status: card_read={card_read}, card_data={card_data}")
            
            # Close the test connection
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
                self.connected = False
            
            if card_read:
                logger.info(f"[RFID] Card read test SUCCESS - Valid RFID card data received!")
            else:
                logger.info(f"[RFID] Card read test WARNING - No valid RFID card read within 30 seconds")
                
        except Exception as e:
            logger.exception("[RFID] Card read test error")
            with self._test_lock:
                self._test_status["testing"] = False
                self._test_status["test_complete"] = True
                self._test_status["time_remaining"] = 0
                self._test_status["card_read"] = False
                self._test_status["card_data"] = None
                self._test_status["card_display"] = None
                self._test_status["parsed_tag"] = None
                self._test_status["message"] = "Reader Connected, but no card read"
            
            # Close the test connection if it exists
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
                self.connected = False
    
    def _try_server_mode(self):
        """Try running as server (RFID is client)
        
        Start a TCP server and return immediately. The connection and card read test
        will run in a background thread, similar to CLIENT mode.
        """
        try:
            self.mode = "SERVER"
            logger.info(f"[RFID] Creating server socket...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            bind_ip = "0.0.0.0"
            logger.info(f"[RFID] Binding to {bind_ip}:{self.port}...")
            self.sock.bind((bind_ip, self.port))
            self.sock.listen(5)
            logger.info(f"[RFID] Server listening on {bind_ip}:{self.port}")
            logger.info(f"[RFID] Starting 30-second connection and card read test in background...")
            
            # IMPORTANT: Initialize test status BEFORE starting thread
            # This prevents the thread from immediately exiting due to testing=False from stop()
            with self._test_lock:
                self._test_status = {
                    "testing": True,  # Set to True BEFORE starting thread
                    "time_remaining": 30,
                    "card_read": False,
                    "card_data": None,
                    "card_display": None,
                    "parsed_tag": None,
                    "test_complete": False,
                    "mode": "SERVER",
                    "message": None
                }
            
            # Small delay to ensure status is fully set before thread starts
            time.sleep(0.1)
            
            # Start the server mode test in background thread
            test_thread = threading.Thread(target=self._run_server_mode_test, daemon=True)
            test_thread.start()
            
            return {
                "status": 200,
                "mode": "SERVER"
            }
            
        except OSError as e:
            logger.info(f"[RFID] Port binding error: {e}")
            return {
                "status": 500,
                "mode": "SERVER",
                "message": f"Cannot bind to port {self.port}. Port may be in use."
            }
        except Exception as e:
            logger.exception("[RFID] Server mode startup error")
            return {
                "status": 500,
                "mode": "SERVER",
                "message": "Failed to start RFID server mode. Please verify port and network settings."
            }
    
    def _run_server_mode_test(self):
        """Run the 30-second server mode test in background thread"""
        try:
            logger.info(f"[RFID] Starting 30-second server mode test in background...")
            
            # Verify test status (should already be initialized before thread starts)
            with self._test_lock:
                # Check if test was stopped (by new check_connection call)
                if not self._test_status.get("testing", False):
                    logger.info(f"[RFID] Test was stopped, exiting...")
                    return
                # Ensure status is correct (should already be set, but verify)
                if self._test_status.get("mode") != "SERVER":
                    self._test_status["mode"] = "SERVER"
                if self._test_status.get("time_remaining", 0) != 30:
                    self._test_status["time_remaining"] = 30
            
            end_time = time.time() + 30.0  # 30 second timeout
            card_read = False
            card_data = None
            card_display = None
            parsed_tag = None
            conn = None
            connection_ack_received = False  # Track if we've received connection ack
            
            while time.time() < end_time:
                # Check if test was stopped
                with self._test_lock:
                    if not self._test_status.get("testing", True):
                        logger.info(f"[RFID] Test was stopped during execution, exiting...")
                        break
                
                remaining = int(end_time - time.time())
                
                # Update status
                with self._test_lock:
                    self._test_status["time_remaining"] = remaining
                
                self.sock.settimeout(1.0)  # 1 second timeout for accept
                try:
                    if conn is None:
                        # Waiting for connection
                        logger.info(f"[RFID][SERVER] Waiting for RFID to connect... ({remaining}s remaining)")
                        conn, addr = self.sock.accept()
                        self.client_conn = conn
                        self.connected = True
                        logger.info(f"[RFID][SERVER] CONNECTION ACCEPTED from {addr}!")
                        logger.info(f"[RFID][SERVER] RFID connected. Now waiting for RFID card read...")
                        conn.settimeout(1.0)  # 1 second timeout for each read attempt
                        connection_ack_received = False  # Reset for new connection
                    
                    # Connection established - now listen for RFID card data
                    try:
                        data = conn.recv(RFID_SOCKET_RECV_SIZE)
                        if data and len(data) > 0:
                            logger.info(f"[RFID][SERVER] Raw data received ({len(data)} bytes)")
                            logger.info(f"[RFID][SERVER] Raw HEX: {data.hex()}")
                            # First, check if this is a connection acknowledgment (skip it)
                            if not connection_ack_received:
                                # Check if it's a connection ack message
                                try:
                                    decoded = data.decode('ascii', errors='ignore').strip()
                                    decoded_clean = "".join(decoded.split())
                                    connection_ack_messages = [
                                        "TcpServerConnected!",
                                        "Tcp Server Connected!",
                                        "TCP Server Connected!",
                                        "Connected",
                                        "Server Connected"
                                    ]
                                    is_ack = any(
                                        ack_msg.lower() in decoded_clean.lower() or 
                                        decoded_clean.lower() in ack_msg.lower() 
                                        for ack_msg in connection_ack_messages
                                    )
                                    if is_ack:
                                        connection_ack_received = True
                                        continue  # Skip this message, wait for actual RFID data
                                except:
                                    # If decode fails, it's likely binary RFID data
                                    pass
                                connection_ack_received = True
                            
                            # Validate if it's actual RFID data (not connection message)
                            if self._is_valid_rfid_data(data):
                                extracted = self._extract_rfid_payload(data)
                                parsed_tag = extracted
                                card_data = data.hex().upper()
                                card_display = self._to_human_readable_data(data)
                                card_read = True
                                logger.info(f"[RFID][SERVER] Raw hex data: {card_data}")
                                logger.info(f"[RFID][SERVER] Human-readable data: {card_display}")
                                logger.info(f"[RFID][SERVER] Parsed RFID payload: {parsed_tag}")
                                logger.info(f"[RFID][SERVER] Card read condition met, ending test loop")
                                break
                            else:
                                # Not valid RFID data, continue waiting
                                logger.info(f"[RFID][SERVER] Received data but not valid RFID, continuing to wait...")
                                continue
                    except socket.timeout:
                        # No data received in this second, continue
                        continue
                    except Exception as e:
                        logger.info(f"[RFID][SERVER] Error receiving data: {type(e).__name__}: {e}")
                        break
                        
                except socket.timeout:
                    # No connection yet, continue waiting
                    continue
                except Exception as e:
                    logger.info(f"[RFID][SERVER] Error accepting connection: {type(e).__name__}: {e}")
                    break
            
            # Update final status
            with self._test_lock:
                # Only update if test wasn't stopped
                if self._test_status.get("testing", False):
                    self._test_status["testing"] = False
                    self._test_status["card_read"] = card_read
                    self._test_status["card_data"] = card_data
                    self._test_status["card_display"] = card_display
                    self._test_status["parsed_tag"] = parsed_tag
                    self._test_status["test_complete"] = True
                    self._test_status["time_remaining"] = 0
                    
                    if card_read:
                        self._test_status["message"] = "Reader Connected and Valid RFID received"
                    else:
                        self._test_status["message"] = "Reader Connected, but no card read"
                    logger.info(f"[RFID][SERVER] Final test status: card_read={card_read}, card_data={card_data}")
            
            # Cleanup
            if conn:
                try:
                    conn.close()
                except:
                    pass
                self.client_conn = None
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
            self.connected = False
            
            if card_read:
                logger.info(f"[RFID] Server mode test SUCCESS - Valid RFID card data received!")
            else:
                logger.info(f"[RFID] Server mode test WARNING - No valid RFID card read within 30 seconds")
                
        except Exception as e:
            logger.exception("[RFID] Server mode test error")
            with self._test_lock:
                self._test_status["testing"] = False
                self._test_status["test_complete"] = True
                self._test_status["time_remaining"] = 0
                self._test_status["card_read"] = False
                self._test_status["card_data"] = None
                self._test_status["card_display"] = None
                self._test_status["parsed_tag"] = None
                self._test_status["message"] = "Reader Connected, but no card read"
            
            # Cleanup
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None
            self.connected = False
    
    def get_test_status(self):
        """Get current RFID card read test status"""
        with self._test_lock:
            return self._test_status.copy()
    
    def reset_test_status(self):
        """Reset the test status - used when starting a new check"""
        # First stop any running tests to ensure clean state
        # This is important to prevent race conditions
        with self._test_lock:
            if self._test_status.get("testing", False):
                # Signal threads to stop
                self._test_status["testing"] = False
            # Reset status
            self._test_status = {
                "testing": False,
                "time_remaining": 0,
                "card_read": False,
                "card_data": None,
                "card_display": None,
                "parsed_tag": None,
                "test_complete": False,
                "mode": None,
                "message": None
            }
        logger.info("[RFID] Test status reset")
    
    def stop(self):
        """Stop RFID connection and cleanup"""
        logger.info(f"[RFID] Stopping RFID connection and any running tests...")
        try:
            # First, signal test threads to stop by setting testing to False
            with self._test_lock:
                if self._test_status.get("testing", False):
                    logger.info(f"[RFID] Signaling test threads to stop...")
                    self._test_status["testing"] = False
            
            # Give threads a moment to check the flag and exit gracefully
            time.sleep(0.5)

            ctrl = getattr(self, "_api_cloud_ctrl", None)
            if ctrl:
                try:
                    ctrl.stop()
                except Exception:
                    pass
                self._api_cloud_ctrl = None

            self._stop_temp_rfid_push_server()
            
            # Now close connections
            if self.client_conn:
                try:
                    logger.info(f"[RFID] Closing client connection...")
                    self.client_conn.close()
                except:
                    pass
                self.client_conn = None
            if self.sock:
                try:
                    logger.info(f"[RFID] Closing socket...")
                    self.sock.close()
                except:
                    pass
                self.sock = None
            self.connected = False
            self.mode = None
            
            # Reset test status completely
            with self._test_lock:
                self._test_status = {
                    "testing": False,
                    "time_remaining": 0,
                    "card_read": False,
                    "card_data": None,
                    "card_display": None,
                    "parsed_tag": None,
                    "test_complete": False,
                    "mode": None,
                    "message": None
                }
            logger.info(f"[RFID] Connection stopped successfully")
            return {"status": 200, "message": "RFID connection stopped"}
        except Exception as e:
            logger.exception("[RFID] Error stopping connection")
            return {"status": 500, "message": "Failed to stop RFID connection cleanly."}

