import serial
import serial.tools.list_ports
import threading
import time
import logging

from utils.timeout_config_loader import load_timeout_config_module

try:
    from digitizer_index_engine import (
        WIZARD_CAPTURE_BYTES,
        extract_weight_from_indexing,
        validate_indexing_for_calibration,
    )
except ImportError:
    WIZARD_CAPTURE_BYTES = 45
    extract_weight_from_indexing = None

logger = logging.getLogger(__name__)


def _load_digitizer_serial_read_sizes():
    """Load DIGITIZER_SERIAL_READ_SIZE / DRAIN_MAX from shared timeout_config.py beside EXE."""
    read_size = 50
    drain_max = 512
    module = load_timeout_config_module()
    if module is not None:
        timeouts = getattr(module, "TIMEOUTS", None)
        if timeouts is not None:
            try:
                read_size = int(getattr(timeouts, "DIGITIZER_SERIAL_READ_SIZE", read_size))
                drain_max = int(getattr(timeouts, "DIGITIZER_SERIAL_DRAIN_MAX", drain_max))
                return max(1, min(read_size, 4096)), max(read_size, min(drain_max, 4096))
            except (TypeError, ValueError):
                pass
    return read_size, drain_max


def get_digitizer_calibration_min_weight_kg() -> int:
    """Minimum parsed weight (kg) required during IoT digitizer calibration."""
    default = 500
    module = load_timeout_config_module()
    if module is not None:
        timeouts = getattr(module, "TIMEOUTS", None)
        if timeouts is not None:
            try:
                return max(1, int(getattr(timeouts, "DIGITIZER_CALIBRATION_MIN_WEIGHT_KG", default)))
            except (TypeError, ValueError):
                pass
    return default


def _resolve_calibration_sample(data: dict, digitizer_service) -> tuple[bytes | None, str | None]:
    """
    Resolve raw bytes for calibration validation.

    Prefers sample_hex from the save payload (index-picker flow), then the
    in-memory cache populated by capture_sample / check_connection reads.
    """
    sample_hex = (
        (data.get("calibration_sample_hex") or data.get("sample_hex") or "").strip()
    )
    if sample_hex:
        try:
            raw = bytes.fromhex(sample_hex)
        except ValueError:
            return None, "Invalid calibration sample hex."
        if raw:
            logger.info(
                "Digitizer calibration save: using %d byte sample from save payload",
                len(raw),
            )
            return raw, None
        return None, "Calibration sample hex is empty."

    if digitizer_service:
        raw = digitizer_service.get_latest_raw_sample()
        if raw:
            logger.info(
                "Digitizer calibration save: using %d byte cached sample",
                len(raw),
            )
            return raw, None

    return None, None


def validate_digitizer_section_save(data: dict, digitizer_service, digitizer_converter_cls) -> str | None:
    """
    Validate digitizer calibration save when validated=true.
    Requires a live sample and parsed weight >= DIGITIZER_CALIBRATION_MIN_WEIGHT_KG.
    """
    if not data or not data.get("validated"):
        return None

    min_kg = get_digitizer_calibration_min_weight_kg()
    method_id = (data.get("conversion_method") or "").strip()
    if not method_id:
        return "Please select a digitizer conversion method before saving."

    raw, sample_err = _resolve_calibration_sample(data, digitizer_service)
    if sample_err:
        return sample_err
    if not raw:
        return (
            "No digitizer sample available. Place weight on the scale, check connection, "
            "then run Check & Save again."
        )

    weight = None
    if method_id == "index_based":
        indexing = data.get("indexing")
        if not indexing or not isinstance(indexing, dict):
            return "Index-based calibration requires an indexing configuration."
        indexing_err = validate_indexing_for_calibration(indexing)
        if indexing_err:
            return indexing_err
        if extract_weight_from_indexing is None:
            return "digitizer_index_engine is not available."
        weight = extract_weight_from_indexing(raw, indexing)
    elif digitizer_converter_cls is not None:
        try:
            text = raw.decode("ascii", errors="ignore")
        except Exception:
            text = ""

        converter = digitizer_converter_cls()
        if hasattr(converter, "set_preferred_method"):
            converter.set_preferred_method(method_id)
        if hasattr(converter, "set_index_config") and method_id == "index_based":
            converter.set_index_config(data.get("indexing"))
        if text and hasattr(converter, "_pat_pct_buffer"):
            converter._pat_pct_buffer = text[-500:]

        if hasattr(converter, "_convert_by_method"):
            weight = converter._convert_by_method(method_id, raw, text)
        elif hasattr(converter, "convert"):
            weight = converter.convert(raw)

    if weight is None:
        return (
            "Unable to parse weight with the selected conversion method. "
            "Ensure live data is on the scale and try again."
        )

    try:
        parsed_kg = float(weight)
    except (TypeError, ValueError):
        return "Unable to parse a numeric weight from the digitizer sample."

    if parsed_kg < min_kg:
        return (
            f"Place at least {min_kg} kg on the weighbridge for digitizer calibration. "
            f"The selected method parsed {parsed_kg:g} kg, which is too low for reliable conversion selection."
        )
    return None


class DigitizerService:
    """Service for managing digitizer (weight scale) serial communication."""
    
    def __init__(self, digitizer_converter_cls=None):
        self.serial_conn = None
        self.connected = False
        self.received_data = []
        self.running = False
        self.read_thread = None
        # Store recent raw samples for conversion preview (IoT-Configuration only)
        self.raw_samples = []
        self._converter = None
        if digitizer_converter_cls is not None:
            try:
                self._converter = digitizer_converter_cls()
            except Exception:
                logger.exception("Failed to initialize Digitizer_Convert for DigitizerService")
    
    def _open_serial_port(
        self,
        port,
        baud_rate,
        bytesize=8,
        parity='N',
        stopbits=1,
        *,
        timeout=1,
    ):
        """Open a serial port with standard digitizer settings and warm-up."""
        if bytesize == 7:
            bytesize_val = serial.SEVENBITS
        else:
            bytesize_val = serial.EIGHTBITS

        parity_map = {
            'N': serial.PARITY_NONE,
            'E': serial.PARITY_EVEN,
            'O': serial.PARITY_ODD,
            'M': serial.PARITY_MARK,
            'S': serial.PARITY_SPACE,
        }
        parity_val = parity_map.get(str(parity).upper(), serial.PARITY_NONE)

        if stopbits == 1.5:
            stopbits_val = serial.STOPBITS_ONE_POINT_FIVE
        elif stopbits == 2:
            stopbits_val = serial.STOPBITS_TWO
        else:
            stopbits_val = serial.STOPBITS_ONE

        max_open_retries = 3
        conn = None
        for attempt in range(max_open_retries):
            try:
                conn = serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    timeout=timeout,
                    bytesize=bytesize_val,
                    parity=parity_val,
                    stopbits=stopbits_val,
                    write_timeout=1,
                    rtscts=False,
                    dsrdtr=False,
                    xonxoff=False,
                )
                break
            except serial.SerialException:
                if attempt >= max_open_retries - 1:
                    raise
                logger.warning(
                    "Digitizer open failed on %s (attempt %d/%d), retrying...",
                    port,
                    attempt + 1,
                    max_open_retries,
                )
                time.sleep(0.6)

        if conn is None or not conn.is_open:
            raise serial.SerialException(f"Failed to open serial port {port}")

        try:
            conn.setDTR(False)
            conn.setRTS(False)
            time.sleep(0.1)
            conn.reset_input_buffer()
            conn.reset_output_buffer()
            conn.setDTR(True)
            conn.setRTS(True)
            time.sleep(0.25)
            conn.reset_input_buffer()
        except Exception:
            logger.debug("Digitizer serial warm-up skipped due to driver limitations", exc_info=True)

        return conn

    def _log_raw_sample(self, context, raw_data, port=None):
        """Log digitizer serial payload at INFO for field troubleshooting."""
        port_part = f" on {port}" if port else ""
        if not raw_data:
            logger.info("Digitizer %s: no data received%s", context, port_part)
            return
        try:
            ascii_preview = raw_data.decode("ascii", errors="replace")
        except Exception:
            ascii_preview = ""
        hex_preview = raw_data.hex()
        if len(hex_preview) > 200:
            hex_preview = hex_preview[:200] + "..."
        if len(ascii_preview) > 120:
            ascii_preview = ascii_preview[:120] + "..."
        logger.info(
            "Digitizer %s%s: %d bytes | hex=%s | ascii=%r",
            context,
            port_part,
            len(raw_data),
            hex_preview,
            ascii_preview,
        )

    def _store_raw_sample(self, raw_data):
        """Keep recent raw samples for save validation and preview APIs."""
        if not raw_data:
            return
        self.raw_samples.append(raw_data)
        if len(self.raw_samples) > 10:
            self.raw_samples = self.raw_samples[-10:]

    def _read_serial_frame(self, conn, nbytes, timeout):
        """
        Clear serial buffers, wait for incoming data, read up to nbytes.

        Uses short polling so slow digitizers (e.g. 2400 baud) can fill the frame.
        """
        read_size, drain_max = _load_digitizer_serial_read_sizes()
        conn.reset_input_buffer()
        conn.reset_output_buffer()

        deadline = time.time() + float(timeout)
        buffer = bytearray()
        poll_interval = 0.05

        logger.info(
            "Digitizer serial read: target=%d bytes, timeout=%.1fs, read_size=%d, drain_max=%d",
            nbytes,
            timeout,
            read_size,
            drain_max,
        )

        while time.time() < deadline:
            waiting = conn.in_waiting
            if waiting > 0:
                to_read = min(waiting, drain_max, max(nbytes - len(buffer), 1))
                chunk = conn.read(to_read)
                if chunk:
                    buffer.extend(chunk)
                    logger.info(
                        "Digitizer serial chunk: %d bytes (total=%d/%d, in_waiting=%d)",
                        len(chunk),
                        len(buffer),
                        nbytes,
                        waiting,
                    )
            if len(buffer) >= nbytes:
                break
            time.sleep(poll_interval)

        if len(buffer) < nbytes:
            remaining = nbytes - len(buffer)
            conn.timeout = max(0.1, deadline - time.time())
            extra = conn.read(remaining)
            if extra:
                buffer.extend(extra)
                logger.info(
                    "Digitizer serial final read: %d bytes (total=%d/%d)",
                    len(extra),
                    len(buffer),
                    nbytes,
                )

        return bytes(buffer)

    def capture_sample(
        self,
        port,
        baud_rate,
        bytesize=8,
        parity='N',
        stopbits=1,
        timeout=10,
        nbytes=None,
    ):
        """
        Open port, flush buffers, read exactly nbytes, close port.

        Used by the index-picker wizard (FUTURE_INDEX_PICKER_UI_SPEC.md).
        """
        if not port:
            return {"status": 400, "message": "Serial port is required"}

        nbytes = int(nbytes or WIZARD_CAPTURE_BYTES)
        timeout = float(timeout or 10)

        self.stop()

        conn = None
        try:
            conn = self._open_serial_port(
                port,
                int(baud_rate),
                bytesize,
                parity,
                stopbits,
                timeout=timeout,
            )
            sample = self._read_serial_frame(conn, nbytes, timeout)
            self._log_raw_sample("capture_sample", sample, port=port)
            if not sample:
                return {
                    "status": 400,
                    "message": (
                        f"No data received within {timeout}s. Check wiring, baud rate, "
                        "and that the digitizer is transmitting."
                    ),
                    "sample_hex": "",
                    "length": 0,
                }

            self._store_raw_sample(sample)

            message = f"Captured {len(sample)} byte(s) from {port}"
            if len(sample) < nbytes:
                message += (
                    f" (expected {nbytes}; increase timeout if the stream is slow)"
                )

            return {
                "status": 200,
                "message": message,
                "sample_hex": sample.hex(),
                "length": len(sample),
                "port": port,
                "baud_rate": int(baud_rate),
                "bytesize": int(bytesize),
                "parity": parity,
                "stopbits": stopbits,
                "timeout": timeout,
            }
        except serial.SerialException:
            logger.exception("Digitizer sample capture failed on port %s", port)
            return {
                "status": 500,
                "message": "Unable to open serial port. Please verify COM port and serial settings.",
            }
        except Exception:
            logger.exception("Digitizer sample capture error on port %s", port)
            return {
                "status": 500,
                "message": "Digitizer sample capture failed. Please verify wiring and communication settings.",
            }
        finally:
            if conn is not None:
                try:
                    if conn.is_open:
                        conn.close()
                except Exception:
                    pass
            time.sleep(0.25)

    def get_available_ports(self):
        """Get list of available serial ports"""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid
            })
        return ports
    
    def check_connection(self, port, baud_rate, bytesize=8, parity='N', stopbits=1):
        """
        Check digitizer connectivity via serial port.
        
        Args:
            port: Serial port name (e.g., 'COM1' or '/dev/ttyUSB0')
            baud_rate: Baud rate for serial communication
            bytesize: Number of data bits (default: 8)
            parity: Parity setting ('N', 'E', 'O', 'M', 'S') (default: 'N')
            stopbits: Number of stop bits (1, 1.5, or 2) (default: 1)
        
        Returns:
            dict: Status dictionary with 'status', 'message', and optional 'data_sample'
        """
        if not port:
            return {
                "status": 400,
                "message": "Serial port is required"
            }
        
        # Stop existing connection
        self.stop()
        
        try:
            self.serial_conn = self._open_serial_port(
                port,
                baud_rate,
                bytesize,
                parity,
                stopbits,
                timeout=1,
            )
            
            self.connected = True
            self.running = True
            self.received_data = []
            
            # Start reading thread
            self.read_thread = threading.Thread(target=self._read_serial, daemon=True)
            self.read_thread.start()
            
            # Wait for data (up to 20 seconds) after warm-up.
            timeout = time.time() + 20
            while time.time() < timeout:
                if len(self.received_data) > 0:
                    # Verify we actually got valid weight data (not just connection noise)
                    # Check if any entry contains a weight value
                    has_valid_data = False
                    for entry in self.received_data:
                        if 'Weight:' in entry.get('data', '') or any(char.isdigit() for char in entry.get('data', '')):
                            has_valid_data = True
                            break
                    
                    if has_valid_data:
                        return {
                            "status": 200,
                            "message": "Digitizer connected and receiving weight data",
                            "data_sample": self.received_data[:5],
                            "has_data": True
                        }
                time.sleep(0.5)
            
            # No data received - connection established but no weight data
            # Close connection since we can't verify it's a digitizer
            self.stop()
            return {
                "status": 400,
                "message": "COM port connected but no weight data received. Please check: 1) Correct COM port selected, 2) Digitizer is powered on, 3) Weight is placed on scale, 4) Baud rate matches device settings",
                "data_sample": [],
                "has_data": False
            }
            
        except serial.SerialException as e:
            self.stop()
            logger.exception("Digitizer serial error on port %s", port)
            return {
                "status": 500,
                "message": "Unable to open serial port. Please verify COM port and serial settings."
            }
        except Exception as e:
            self.stop()
            logger.exception("Digitizer connection error on port %s", port)
            return {
                "status": 500,
                "message": "Digitizer connection failed. Please verify wiring and communication settings."
            }
    
    def _read_serial(self):
        """
        Read serial data continuously and delegate parsing to conversion.py.

        IMPORTANT:
        - No site-specific regex parsing is implemented here.
        - All weight conversion logic must be handled by Digitizer_Convert.
        """
        while self.running and self.serial_conn:
            try:
                if self.serial_conn.in_waiting > 0:
                    read_size, drain_max = _load_digitizer_serial_read_sizes()
                    waiting = self.serial_conn.in_waiting
                    to_read = min(waiting, drain_max)
                    raw_data = self.serial_conn.read(to_read)
                    logger.info(
                        "Digitizer background read: %d bytes (in_waiting=%d, drain_max=%d, read_size_cfg=%d)",
                        len(raw_data or b""),
                        waiting,
                        drain_max,
                        read_size,
                    )
                    if raw_data:
                        self._log_raw_sample("check_connection", raw_data)
                        self._store_raw_sample(raw_data)
                        parsed_weight = None
                        if self._converter is not None:
                            try:
                                parsed_weight = self._converter.convert(raw_data)
                            except Exception:
                                logger.exception("Digitizer conversion failed for incoming serial data")

                        if parsed_weight is not None:
                            try:
                                raw_preview = raw_data.decode('ascii', errors='ignore')
                            except Exception:
                                raw_preview = raw_data.hex()

                            display_text = f"Weight: {parsed_weight} kg | Raw: {raw_preview[:80]}"
                            self.received_data.append({
                                "time": time.strftime("%H:%M:%S"),
                                "data": display_text
                            })
                        else:
                            # Keep raw visibility for troubleshooting when conversion has no match.
                            self.received_data.append({
                                "time": time.strftime("%H:%M:%S"),
                                "data": f"Raw (hex): {raw_data.hex()[:80]}"
                            })

                        if len(self.received_data) > 100:
                            self.received_data = self.received_data[-100:]
                time.sleep(0.1)
            except Exception as e:
                logger.debug(f"Error reading serial: {e}")
                break
    
    def get_latest_raw_sample(self):
        """Return the latest raw digitizer sample (bytes) for conversion preview."""
        if not self.raw_samples:
            return None
        return self.raw_samples[-1]
    
    def get_latest_data(self):
        """Get latest received data"""
        if not self.received_data:
            return []
        return self.received_data[-10:]
    
    def stop(self):
        """Stop serial connection"""
        try:
            self.running = False
            
            if self.read_thread:
                self.read_thread.join(timeout=1)
                self.read_thread = None
            
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    self.serial_conn.reset_input_buffer()
                    self.serial_conn.reset_output_buffer()
                except Exception:
                    pass
                self.serial_conn.close()
            
            self.serial_conn = None
            self.connected = False
            self.received_data = []
            # Allow OS driver to release COM handle fully before next connect.
            time.sleep(0.25)
            
            return {"status": 200, "message": "Digitizer connection stopped"}
        except Exception as e:
            logger.exception("Error stopping digitizer connection")
            return {"status": 500, "message": "Failed to stop digitizer connection cleanly."}
