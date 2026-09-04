"""
GMDC Digitizer App - standalone serial weight dashboard + local HTTP API.

- Reads weighbridge digitizer over COM
- ASCII index calibration for raw-data weight extraction
- Serves POST/GET /read_stable_weight → {"statusCode": 200, "stable_weight": <kg>}
- No outbound API client; no imports from other GMDC packages
"""

from __future__ import annotations

import datetime
import json
import os
import queue
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import serial
import serial.tools.list_ports
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from index_engine import (
    WIZARD_CAPTURE_BYTES,
    build_indexing_from_picks,
    build_ruler,
    byte_display_repr,
    extract_last_complete_index_frame,
    extract_weight_from_indexing,
    highlight_bands,
    picks_from_indexing,
    validate_indexing_for_calibration,
    validate_pick_indices,
)


def _frame_slice_from_picks(sample: bytes, picks: List[Optional[int]]) -> bytes:
    """
    Trim a long capture to the selected frame so STX/ETX length checks pass.
    Capture is often 45 bytes; a real frame is shorter.
    """
    if not sample:
        return sample
    i1, _i2, _i3, i4, i5, i6 = picks
    start = i1 if i1 is not None else 0
    end_idx = i6 if i6 is not None else i5 if i5 is not None else i4
    if end_idx is None:
        return sample[start:]
    end = min(len(sample), end_idx + 1)
    # Keep trailing CR/LF that often follow the frame end marker
    while end < len(sample) and sample[end] in (0x0D, 0x0A):
        end += 1
    return sample[start:end]


def _weight_from_absolute_picks(
    sample: bytes, picks: List[Optional[int]]
) -> Optional[float]:
    """Parse weight directly from the bytes the operator highlighted (R3..R4)."""
    i3, i4 = picks[2], picks[3]
    if i3 is None or i4 is None or i4 < i3 or i3 >= len(sample):
        return None
    field = sample[i3 : min(len(sample), i4 + 1)]
    digits = bytearray()
    for b in field:
        if 0x30 <= b <= 0x39 or b in (0x2B, 0x2D, 0x2E):  # + - .
            digits.append(b)
        elif b in (0x20, 0x09):
            continue
        elif digits:
            break
    if not digits:
        text = "".join(chr(b) if 0x20 <= b < 0x7F else " " for b in field)
        m = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None
    try:
        return float(digits.decode("ascii"))
    except ValueError:
        return None


def _calibration_extract(
    sample: bytes, picks: List[Optional[int]], indexing: Dict[str, Any]
) -> Optional[float]:
    """Extract weight for calibration save/preview (tolerant of long captures)."""
    # 1) Absolute slice the operator selected
    w = _weight_from_absolute_picks(sample, picks)
    if w is not None:
        return w
    # 2) Engine on trimmed frame (fixes STX length check on 45-byte captures)
    sliced = _frame_slice_from_picks(sample, picks)
    w = extract_weight_from_indexing(sliced, indexing)
    if w is not None:
        return w
    # 3) Engine on full sample
    return extract_weight_from_indexing(sample, indexing)


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_data_dir(), "config.json")
ICON_PATH = os.path.join(_app_dir(), "app_icon.ico")


def _resolve_log_dirs() -> tuple[str, str]:
    """
    Development (python serial_ui.py): logs next to the app (digitizer-app/app_log).
    Production (frozen exe): %PROGRAMDATA%\\WMS\\...
    """
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("PROGRAMDATA", os.path.expanduser("~")), "WMS")
        return os.path.join(base, "app_log"), os.path.join(base, "api_log")
    root = _data_dir()
    return os.path.join(root, "app_log"), os.path.join(root, "api_log")


APP_LOG_DIR, API_LOG_DIR = _resolve_log_dirs()
WINDOWS_APP_ID = "GMDC.DigitizerApp.1.0"
_log_lock = threading.Lock()

# Internal settings (not shown in Config UI)
STABLE_READ_COUNT = 10
READ_TIMEOUT_SEC = 30.0
API_HOST = "0.0.0.0"
API_PORT = 8800

INDEX_ROW_LABELS = [
    "R1 start",
    "R2 start",
    "R3 weight start",
    "R4 weight end",
    "R5 end",
    "R6 end",
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "port": "--Select--",
    "baud_rate": "--Select--",
    "data_bits": "--Select--",
    "parity": "--Select--",
    "stop_bits": "--Select--",
    "status": False,
    # ASCII index calibration
    "indexing": None,
    "calibration_sample_hex": "",
}


def _write_log(log_dir: str, message: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(log_dir, f"{date_str}.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    with _log_lock:
        try:
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(line)
        except IOError:
            pass


def log_app(message: str) -> None:
    _write_log(APP_LOG_DIR, message)


def log_api(message: str) -> None:
    _write_log(API_LOG_DIR, message)


def _init_windows_taskbar() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass


def _load_app_icon() -> QIcon:
    candidates = [ICON_PATH]
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "app_icon.ico"))
        candidates.append(os.path.join(exe_dir, "_internal", "app_icon.ico"))
    for path in candidates:
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
    return QIcon()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_calibrated(config: Dict[str, Any]) -> bool:
    """True when serial port + ASCII index calibration are both saved."""
    port = str(config.get("port") or "").strip()
    if not port or port in ("--Select--", "No ports found"):
        return False
    for key in ("baud_rate", "data_bits", "parity", "stop_bits"):
        val = config.get(key)
        if val is None or val == "" or val == "--Select--":
            return False
    indexing = config.get("indexing")
    if not indexing or not isinstance(indexing, dict):
        return False
    if validate_indexing_for_calibration(indexing):
        return False
    return True


# ---------------------------------------------------------------------------
# Shared runtime state for serial reader + HTTP API
# ---------------------------------------------------------------------------
class WeightRuntime:
    """Thread-safe live weight + stable-weight waiter used by HTTP handlers."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.connected = False
        self.current_weight: Optional[float] = None
        self.last_raw: str = ""
        self.last_raw_bytes: bytes = b""
        self.stable_weight: Optional[float] = None
        self.stable_count_seen = 0
        self.stable_count_required = STABLE_READ_COUNT
        self.read_timeout_sec = READ_TIMEOUT_SEC
        self.indexing: Optional[Dict[str, Any]] = None
        self._cond = threading.Condition(self._lock)

    def update_config(self, config: Dict[str, Any]) -> None:
        with self._lock:
            self.indexing = config.get("indexing") or None
            self.stable_count_required = STABLE_READ_COUNT
            self.read_timeout_sec = READ_TIMEOUT_SEC

    def set_connected(self, connected: bool) -> None:
        with self._lock:
            self.connected = connected
            if not connected:
                self.current_weight = None
                self.stable_weight = None
                self.stable_count_seen = 0
                self.last_raw = ""
                self.last_raw_bytes = b""
            self._cond.notify_all()

    def push_weight(self, weight: float, raw_message: str, raw_bytes: bytes) -> None:
        with self._lock:
            self.current_weight = weight
            self.last_raw = raw_message
            self.last_raw_bytes = raw_bytes

            if weight <= 0:
                self.stable_weight = None
                self.stable_count_seen = 0
            elif self.stable_weight is not None and weight == self.stable_weight:
                self.stable_count_seen += 1
            else:
                self.stable_weight = weight
                self.stable_count_seen = 1

            self._cond.notify_all()

    def is_stable(self) -> bool:
        with self._lock:
            return (
                self.stable_weight is not None
                and self.stable_weight > 0
                and self.stable_count_seen >= self.stable_count_required
            )

    def wait_stable(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        deadline = time.monotonic() + (
            self.read_timeout_sec if timeout is None else timeout
        )
        with self._cond:
            while True:
                if not self.connected:
                    return {
                        "statusCode": 503,
                        "stable_weight": None,
                        "message": "Digitizer serial not connected",
                    }
                if (
                    self.stable_weight is not None
                    and self.stable_weight > 0
                    and self.stable_count_seen >= self.stable_count_required
                ):
                    return {
                        "statusCode": 200,
                        "stable_weight": self.stable_weight,
                    }
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {
                        "statusCode": 408,
                        "stable_weight": self.current_weight,
                        "message": (
                            f"Stable weight not reached "
                            f"({self.stable_count_seen}/{self.stable_count_required})"
                        ),
                    }
                self._cond.wait(timeout=min(remaining, 0.25))


RUNTIME = WeightRuntime()


# ---------------------------------------------------------------------------
# Local HTTP API
# ---------------------------------------------------------------------------
class DigitizerAPIHandler(BaseHTTPRequestHandler):
    server_version = "GMDCDigitizer/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        log_api("%s - %s" % (self.address_string(), fmt % args))

    def _send_json(self, payload: Dict[str, Any], http_status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(http_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._handle()

    def do_POST(self) -> None:  # noqa: N802
        self._handle()

    def _handle(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/read_stable_weight":
            self._read_body()
            result = RUNTIME.wait_stable()
            http_status = 200 if result.get("statusCode") == 200 else int(
                result.get("statusCode") or 500
            )
            log_api(f"read_stable_weight -> {result}")
            self._send_json(result, http_status=http_status)
            return

        if path in ("/", "/health", "/api/status"):
            with RUNTIME._lock:
                payload = {
                    "statusCode": 200,
                    "service": "GMDC Digitizer",
                    "connected": RUNTIME.connected,
                    "current_weight": RUNTIME.current_weight,
                    "stable": RUNTIME.is_stable(),
                    "stable_weight": RUNTIME.stable_weight
                    if RUNTIME.is_stable()
                    else None,
                    "stable_count": f"{RUNTIME.stable_count_seen}/{RUNTIME.stable_count_required}",
                    "indexing_configured": bool(RUNTIME.indexing),
                }
            self._send_json(payload)
            return

        self._send_json(
            {"statusCode": 404, "stable_weight": None, "message": "Not found"},
            http_status=404,
        )


class DigitizerAPIServer:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        if self._httpd:
            return True
        try:
            self._httpd = ThreadingHTTPServer(
                (self.host, self.port), DigitizerAPIHandler
            )
        except OSError as exc:
            log_api(f"API_BIND_FAILED: {self.host}:{self.port} {exc}")
            return False
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="DigitizerAPI", daemon=True
        )
        self._thread.start()
        log_api(f"API_STARTED: http://{self.host}:{self.port}/read_stable_weight")
        return True

    def stop(self) -> None:
        if self._httpd:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass
        self._httpd = None
        self._thread = None


# ---------------------------------------------------------------------------
# Config dialog
# ---------------------------------------------------------------------------
class ConfigDialog(QDialog):
    """Serial + ASCII raw-data index calibration + local API settings."""

    def __init__(self, config: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Config")
        # Enable minimize / maximize / close (QDialog is close-only by default)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        icon = _load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.config = config.copy()
        self.current_ports: list = []
        self.port_refresh_timer: Optional[QTimer] = None
        self.sample_bytes: bytes = b""
        self.picks: List[Optional[int]] = [None, None, None, None, None, None]
        self.active_row = 0
        self.byte_buttons: List[QPushButton] = []
        self._build_ui()
        self._start_port_refresh_timer()
        self._restore_sample_from_config()

    def _build_ui(self) -> None:
        self.setMinimumWidth(900)
        self.setMinimumHeight(720)
        # Same gradient as main dashboard (#090e1b → #111827)
        app_bg = (
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #090e1b, stop:1 #111827)"
        )
        self.setStyleSheet(
            f"""
            QDialog {{ background-color: {app_bg}; color: #f8fafc; }}
            QLabel#headerLabel {{ font-size: 24px; font-weight: 800; color: #fde68a; }}
            QLabel#sectionLabel {{ font-size: 15px; font-weight: 700; color: #a5b4fc; margin-top: 4px; margin-bottom: 4px; }}
            QLabel#subtitleLabel {{ color: #a5b4fc; font-size: 13px; }}
            QLabel {{ font-size: 13px; color: #e2e8f0; }}
            QComboBox, QSpinBox {{ background: #111827; border: 1px solid #7c3aed; border-radius: 10px; padding: 8px; color: #f8fafc; min-width: 100px; }}
            QComboBox::drop-down {{ border: 0px; }}
            QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ec4899, stop:1 #f97316); color: #ffffff; border: none; border-radius: 12px; padding: 10px 16px; font-weight: 700; }}
            QPushButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f43f5e, stop:1 #fb923c); }}
            QPushButton#cancelButton {{ background: transparent; color: #cbd5e1; border: 1px solid #7c3aed; }}
            QPushButton#cancelButton:hover {{ background: rgba(124, 58, 237, 0.14); }}
            QPushButton#secondaryButton {{ background: rgba(59, 130, 246, 0.25); border: 1px solid rgba(96, 165, 250, 0.5); }}
            QPushButton#byteCell {{ background: {app_bg}; border: 1px solid rgba(59, 130, 246, 0.35); border-radius: 6px; padding: 2px; min-width: 34px; max-width: 42px; min-height: 42px; font-size: 11px; font-weight: 600; }}
            QPushButton#byteCell:hover {{ border: 1px solid #fbbf24; }}
            QPushButton#byteFrameStart {{ background: rgba(59, 130, 246, 0.45); border: 1px solid #60a5fa; }}
            QPushButton#byteWeight {{ background: rgba(16, 185, 129, 0.45); border: 1px solid #34d399; }}
            QPushButton#byteFrameEnd {{ background: rgba(244, 63, 94, 0.40); border: 1px solid #fb7185; }}
            QPushButton#rowActive {{ border: 2px solid #fde68a; }}
            QWidget#card {{ background: {app_bg}; border: none; border-radius: 0px; }}
            QWidget#rowPanel {{ background: {app_bg}; border: none; border-radius: 0px; }}
            QWidget#indexPanel {{ background: {app_bg}; border: none; border-radius: 0px; }}
            QScrollArea {{ border: none; border-radius: 0px; background: {app_bg}; }}
            QScrollArea > QWidget > QWidget {{ background: {app_bg}; }}
            QWidget#byteHost {{ background: {app_bg}; }}
            """
        )

        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(
            ["--Select--", "1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"]
        )
        self.data_bits_combo = QComboBox()
        self.data_bits_combo.addItems(["--Select--", "5", "6", "7", "8"])
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["--Select--", "N", "E", "O", "M", "S"])
        self.stop_bits_combo = QComboBox()
        self.stop_bits_combo.addItems(["--Select--", "1", "1.5", "2"])

        self._refresh_ports()
        self._load_serial_values()

        # ---- Row 1: Serial port (two columns) ----
        serial_left = QFormLayout()
        serial_left.setLabelAlignment(Qt.AlignRight)
        serial_left.setFormAlignment(Qt.AlignTop | Qt.AlignLeft)
        serial_left.setHorizontalSpacing(14)
        serial_left.setVerticalSpacing(8)
        serial_left.addRow("Port", self.port_combo)
        serial_left.addRow("Baud rate", self.baud_combo)
        serial_left.addRow("Data bits", self.data_bits_combo)

        serial_right = QFormLayout()
        serial_right.setLabelAlignment(Qt.AlignRight)
        serial_right.setFormAlignment(Qt.AlignTop | Qt.AlignLeft)
        serial_right.setHorizontalSpacing(14)
        serial_right.setVerticalSpacing(8)
        serial_right.addRow("Parity", self.parity_combo)
        serial_right.addRow("Stop bits", self.stop_bits_combo)

        top_row = QWidget()
        top_row.setObjectName("rowPanel")
        top_row_layout = QVBoxLayout(top_row)
        serial_cols = QHBoxLayout()
        serial_cols.setSpacing(24)
        serial_cols.addLayout(serial_left, 1)
        serial_cols.addLayout(serial_right, 1)
        top_row_layout.addLayout(serial_cols)
        top_row_layout.setContentsMargins(8, 8, 8, 8)

        # ---- Row 2: ASCII index calibration ----
        cal_section = QLabel("ASCII index calibration")
        cal_section.setObjectName("sectionLabel")

        self.capture_btn = QPushButton("Capture sample")
        self.capture_btn.setObjectName("secondaryButton")
        self.capture_btn.clicked.connect(self._capture_sample)
        self.clear_picks_btn = QPushButton("Clear picks")
        self.clear_picks_btn.setObjectName("secondaryButton")
        self.clear_picks_btn.clicked.connect(self._clear_picks)
        self.use_latest_btn = QPushButton("Use latest reading")
        self.use_latest_btn.setObjectName("secondaryButton")
        self.use_latest_btn.clicked.connect(self._use_latest_reading)

        self.sample_info = QLabel("")
        self.sample_info.setObjectName("subtitleLabel")
        self.preview_label = QLabel("")
        self.preview_label.setStyleSheet("color: #86efac; font-weight: 700; font-size: 14px;")

        # Index picks in two columns (3 + 3)
        self.row_buttons: List[QPushButton] = []
        self.row_spins: List[QSpinBox] = []
        picks_grid = QGridLayout()
        picks_grid.setHorizontalSpacing(16)
        picks_grid.setVerticalSpacing(6)
        for i, label in enumerate(INDEX_ROW_LABELS):
            cell = QHBoxLayout()
            rb = QPushButton(f"R{i + 1}")
            rb.setCheckable(True)
            rb.setChecked(i == 0)
            rb.setFixedWidth(40)
            rb.clicked.connect(lambda checked=False, idx=i: self._set_active_row(idx))
            self.row_buttons.append(rb)
            spin = QSpinBox()
            spin.setRange(-1, 999)
            spin.setSpecialValueText("-")
            spin.setValue(-1)
            spin.valueChanged.connect(lambda _v, idx=i: self._spin_changed(idx))
            self.row_spins.append(spin)
            cell.addWidget(rb)
            cell.addWidget(QLabel(label), 1)
            cell.addWidget(spin)
            picks_grid.addLayout(cell, i % 3, i // 3)

        # Byte grid (background matches main app)
        self.byte_scroll = QScrollArea()
        self.byte_scroll.setWidgetResizable(True)
        self.byte_scroll.setMinimumHeight(200)
        self.byte_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.byte_scroll.viewport().setStyleSheet(
            "background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #090e1b, stop:1 #111827);"
        )
        self.byte_host = QWidget()
        self.byte_host.setObjectName("byteHost")
        self.byte_host.setAttribute(Qt.WA_StyledBackground, True)
        self.byte_grid = QGridLayout(self.byte_host)
        self.byte_grid.setSpacing(4)
        self.byte_grid.setContentsMargins(8, 8, 8, 8)
        self.byte_scroll.setWidget(self.byte_host)

        bottom_row = QWidget()
        bottom_row.setObjectName("indexPanel")
        bottom_row.setAttribute(Qt.WA_StyledBackground, True)
        bottom_layout = QVBoxLayout(bottom_row)
        bottom_layout.addWidget(cal_section)
        bottom_layout.addWidget(self.sample_info)
        bottom_layout.addLayout(picks_grid)
        bottom_layout.addWidget(self.byte_scroll, 1)
        bottom_layout.addWidget(self.preview_label)
        bottom_layout.setContentsMargins(8, 8, 8, 8)

        rows = QVBoxLayout()
        rows.setSpacing(12)
        rows.addWidget(top_row)
        rows.addWidget(bottom_row, 1)

        # All action buttons at right-bottom
        save_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("cancelButton")
        save_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch(1)
        footer.addWidget(self.capture_btn)
        footer.addWidget(self.use_latest_btn)
        footer.addWidget(self.clear_picks_btn)
        footer.addWidget(save_button)
        footer.addWidget(cancel_button)

        card = QWidget()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.addLayout(rows, 1)
        card_layout.addLayout(footer)
        card_layout.setContentsMargins(16, 16, 16, 16)

        layout = QVBoxLayout(self)
        layout.addWidget(card)
        self._set_active_row(0)

    def _set_active_row(self, idx: int) -> None:
        self.active_row = idx
        for i, btn in enumerate(self.row_buttons):
            btn.setChecked(i == idx)
            btn.setObjectName("rowActive" if i == idx else "")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _spin_changed(self, idx: int) -> None:
        val = self.row_spins[idx].value()
        self.picks[idx] = None if val < 0 else val
        self._refresh_byte_highlights()
        self._update_preview()

    def _clear_picks(self) -> None:
        self.picks = [None, None, None, None, None, None]
        for spin in self.row_spins:
            spin.blockSignals(True)
            spin.setValue(-1)
            spin.blockSignals(False)
        self._refresh_byte_highlights()
        self._update_preview()

    def _use_latest_reading(self) -> None:
        parent = self.parent()
        raw = b""
        if parent is not None and hasattr(parent, "get_latest_raw_bytes"):
            raw = parent.get_latest_raw_bytes() or b""
        if not raw and RUNTIME.last_raw_bytes:
            raw = RUNTIME.last_raw_bytes
        if not raw:
            QMessageBox.warning(
                self,
                "No data",
                "No latest reading yet. Connect serial and wait for weight data, "
                "or use Capture sample.",
            )
            return
        self._set_sample(raw)

    def _capture_sample(self) -> None:
        parent = self.parent()
        if parent is None or not hasattr(parent, "capture_sample_bytes"):
            QMessageBox.warning(self, "Capture", "Capture is not available.")
            return
        # Use dialog serial settings for capture
        try:
            settings = {
                "port": self.port_combo.currentText(),
                "baud_rate": int(self.baud_combo.currentText()),
                "data_bits": int(self.data_bits_combo.currentText()),
                "parity": self.parity_combo.currentText(),
                "stop_bits": float(self.stop_bits_combo.currentText()),
            }
        except ValueError:
            QMessageBox.warning(
                self, "Capture", "Select valid serial settings before capturing."
            )
            return
        if settings["port"] in ("", "--Select--", "No ports found"):
            QMessageBox.warning(self, "Capture", "Please select a serial port.")
            return

        self.capture_btn.setEnabled(False)
        self.capture_btn.setText("Capturing…")
        QApplication.processEvents()
        try:
            raw = parent.capture_sample_bytes(
                settings, nbytes=WIZARD_CAPTURE_BYTES, timeout=8.0
            )
        finally:
            self.capture_btn.setEnabled(True)
            self.capture_btn.setText("Capture sample")

        if not raw:
            QMessageBox.warning(
                self,
                "Capture failed",
                "No bytes received. Check COM port / digitizer power.",
            )
            return
        self._set_sample(raw)

    def _set_sample(self, raw: bytes) -> None:
        self.sample_bytes = raw
        ruler = build_ruler(raw)
        self.sample_info.setText(f"{ruler['length']} bytes")
        # Restore picks if indexing matches this sample
        indexing = self.config.get("indexing")
        if indexing:
            restored = picks_from_indexing(raw, indexing)
            if any(p is not None for p in restored):
                self.picks = restored
                for i, p in enumerate(self.picks):
                    self.row_spins[i].blockSignals(True)
                    self.row_spins[i].setMaximum(max(len(raw) - 1, 0))
                    self.row_spins[i].setValue(-1 if p is None else p)
                    self.row_spins[i].blockSignals(False)
        else:
            for spin in self.row_spins:
                spin.setMaximum(max(len(raw) - 1, 0))
        self._rebuild_byte_grid()
        self._update_preview()

    def _rebuild_byte_grid(self) -> None:
        while self.byte_grid.count():
            item = self.byte_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.byte_buttons = []
        cols = 12
        for i, b in enumerate(self.sample_bytes):
            btn = QPushButton(f"{i}\n{byte_display_repr(b)}")
            btn.setObjectName("byteCell")
            btn.setToolTip(f"Index {i} · hex {b:02X} · ascii {byte_display_repr(b)}")
            btn.clicked.connect(lambda _=False, idx=i: self._byte_clicked(idx))
            self.byte_grid.addWidget(btn, i // cols, i % cols)
            self.byte_buttons.append(btn)
        self._refresh_byte_highlights()

    def _byte_clicked(self, idx: int) -> None:
        self.picks[self.active_row] = idx
        spin = self.row_spins[self.active_row]
        spin.blockSignals(True)
        spin.setMaximum(max(len(self.sample_bytes) - 1, 0))
        spin.setValue(idx)
        spin.blockSignals(False)
        # Auto-advance to next row
        if self.active_row < 5:
            self._set_active_row(self.active_row + 1)
        self._refresh_byte_highlights()
        self._update_preview()

    def _refresh_byte_highlights(self) -> None:
        bands = highlight_bands(self.picks)
        for i, btn in enumerate(self.byte_buttons):
            if i in bands["weight"]:
                btn.setObjectName("byteWeight")
            elif i in bands["frame_start"]:
                btn.setObjectName("byteFrameStart")
            elif i in bands["frame_end"]:
                btn.setObjectName("byteFrameEnd")
            else:
                btn.setObjectName("byteCell")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _update_preview(self) -> None:
        if not self.sample_bytes:
            self.preview_label.setText("")
            return
        err = validate_pick_indices(self.picks, len(self.sample_bytes))
        if err:
            self.preview_label.setText(err)
            self.preview_label.setStyleSheet(
                "color: #fca5a5; font-weight: 600; font-size: 13px;"
            )
            return
        try:
            indexing = build_indexing_from_picks(self.picks, self.sample_bytes)
        except ValueError as exc:
            self.preview_label.setText(str(exc))
            self.preview_label.setStyleSheet(
                "color: #fca5a5; font-weight: 600; font-size: 13px;"
            )
            return
        weight = _calibration_extract(self.sample_bytes, self.picks, indexing)
        if weight is None:
            i3, i4 = self.picks[2], self.picks[3]
            field = (
                self.sample_bytes[i3 : i4 + 1]
                if i3 is not None and i4 is not None
                else b""
            )
            shown = "".join(
                chr(b) if 0x20 <= b < 0x7F else "." for b in field
            )
            self.preview_label.setText(f"no digits in R3–R4: [{shown}]")
            self.preview_label.setStyleSheet(
                "color: #fca5a5; font-weight: 600; font-size: 13px;"
            )
        else:
            self.preview_label.setText(f"{weight:.2f} kg")
            self.preview_label.setStyleSheet(
                "color: #86efac; font-weight: 700; font-size: 14px;"
            )

    def _restore_sample_from_config(self) -> None:
        hex_str = (self.config.get("calibration_sample_hex") or "").strip()
        if not hex_str:
            return
        try:
            raw = bytes.fromhex(hex_str)
        except ValueError:
            return
        if raw:
            self._set_sample(raw)

    def accept(self) -> None:
        port = self.port_combo.currentText()
        if not port or port in ("--Select--", "No ports found"):
            QMessageBox.warning(self, "Port", "Please select a serial port.")
            return
        for label, combo in (
            ("Baud rate", self.baud_combo),
            ("Data bits", self.data_bits_combo),
            ("Parity", self.parity_combo),
            ("Stop bits", self.stop_bits_combo),
        ):
            if combo.currentText() == "--Select--":
                QMessageBox.warning(self, label, f"Please select {label}.")
                return
        if not self.sample_bytes:
            QMessageBox.warning(
                self,
                "Calibration",
                "Capture a raw sample and set ASCII index positions before saving.",
            )
            return
        err = validate_pick_indices(self.picks, len(self.sample_bytes))
        if err:
            QMessageBox.warning(self, "Calibration", err)
            return
        try:
            indexing = build_indexing_from_picks(self.picks, self.sample_bytes)
        except ValueError as exc:
            QMessageBox.warning(self, "Calibration", str(exc))
            return
        idx_err = validate_indexing_for_calibration(indexing)
        if idx_err:
            QMessageBox.warning(self, "Calibration", idx_err)
            return
        weight = _calibration_extract(self.sample_bytes, self.picks, indexing)
        if weight is None:
            i3, i4 = self.picks[2], self.picks[3]
            field = (
                self.sample_bytes[i3 : i4 + 1]
                if i3 is not None and i4 is not None
                else b""
            )
            shown = "".join(
                chr(b) if 0x20 <= b < 0x7F else f"\\x{b:02x}" for b in field
            )
            QMessageBox.warning(
                self,
                "Calibration",
                "Could not extract weight from R3–R4.\n\n"
                f"Selected bytes: [{shown}]\n"
                "Highlight only the numeric weight digits "
                "(R3 = first digit, R4 = last digit).",
            )
            return

        # Store trimmed frame sample when possible (cleaner for runtime restore)
        sliced = _frame_slice_from_picks(self.sample_bytes, self.picks)
        self._pending_indexing = indexing
        self._pending_sample_hex = (sliced or self.sample_bytes).hex()
        super().accept()

    def _start_port_refresh_timer(self) -> None:
        if not self.port_refresh_timer:
            self.port_refresh_timer = QTimer(self)
            self.port_refresh_timer.timeout.connect(self._refresh_ports)
            self.port_refresh_timer.start(500)

    def _stop_port_refresh_timer(self) -> None:
        if self.port_refresh_timer:
            self.port_refresh_timer.stop()
            self.port_refresh_timer = None

    def _refresh_ports(self) -> None:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if ports == self.current_ports:
            return
        self.current_ports = ports
        current_selection = self.port_combo.currentText()
        self.port_combo.clear()
        if ports:
            self.port_combo.addItems(ports)
            if current_selection in ports:
                idx = self.port_combo.findText(current_selection)
                if idx != -1:
                    self.port_combo.setCurrentIndex(idx)
        else:
            self.port_combo.addItem("No ports found")

    def _load_serial_values(self) -> None:
        if self.config.get("port"):
            idx = self.port_combo.findText(str(self.config["port"]))
            if idx != -1:
                self.port_combo.setCurrentIndex(idx)
        self.baud_combo.setCurrentText(
            str(self.config.get("baud_rate", DEFAULT_CONFIG["baud_rate"]))
        )
        self.data_bits_combo.setCurrentText(
            str(self.config.get("data_bits", DEFAULT_CONFIG["data_bits"]))
        )
        self.parity_combo.setCurrentText(
            str(self.config.get("parity", DEFAULT_CONFIG["parity"]))
        )
        self.stop_bits_combo.setCurrentText(
            str(self.config.get("stop_bits", DEFAULT_CONFIG["stop_bits"]))
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_port_refresh_timer()
        event.accept()

    def get_config(self) -> Dict[str, Any]:
        port = self.port_combo.currentText()
        if port == "No ports found":
            port = ""
        indexing = getattr(self, "_pending_indexing", None) or self.config.get(
            "indexing"
        )
        sample_hex = getattr(self, "_pending_sample_hex", None) or self.config.get(
            "calibration_sample_hex", ""
        )
        return {
            "port": port,
            "baud_rate": int(self.baud_combo.currentText()),
            "data_bits": int(self.data_bits_combo.currentText()),
            "parity": self.parity_combo.currentText(),
            "stop_bits": float(self.stop_bits_combo.currentText()),
            "indexing": indexing,
            "calibration_sample_hex": sample_hex,
        }


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class SerialReaderApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GMDC Digitizer")
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        icon = _load_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)
        self.resize(420, 520)

        self.running = False
        self.stop_event = threading.Event()
        self.queue: queue.Queue = queue.Queue()
        self.config = self._load_config()
        RUNTIME.update_config(self.config)

        self.last_message: Optional[str] = None
        self.last_raw_bytes: bytes = b""
        self.serial_port = None
        self.read_thread = None
        self.connection_status = False
        self.auto_reconnect_timer = None
        self.disconnect_time = None
        self.api_server: Optional[DigitizerAPIServer] = None
        self._capture_lock = threading.Lock()

        self._build_ui()
        self._update_config_summary()
        self._start_poll_timer()
        self._start_api_server()

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setStyleSheet(
            """
            QWidget { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #090e1b, stop:1 #111827); color: #f8fafc; }
            QPushButton { border-radius: 14px; padding: 12px 20px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ec4899, stop:1 #f59e0b); color: #ffffff; font-weight: 700; }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #db2777, stop:1 #ea580c); }
            QLabel { font-size: 20px; color: #f8fafc; }
            QLabel#titleLabel { font-size: 18px; font-weight: 900; color: #fde68a; }
            QLabel#valueLabel { font-size: 100px; font-weight: 600; color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #34d399, stop:1 #a78bfa); }
            QLabel#subtitleLabel { color: #93c5fd; font-size: 15px; }
            QWidget#panel { background: transparent; border: 1px solid rgba(59, 130, 246, 0.25); border-radius: 28px; }
            QWidget#card { background: rgba(15, 23, 42, 0.90); border: 1px solid rgba(168, 85, 247, 0.35); border-radius: 28px; }
            QWidget#controlCard { background: transparent; border: 1px solid rgba(59, 130, 246, 0.18); border-radius: 22px; }
            """
        )

        self.title_label = QLabel("Digitizer")
        self.title_label.setObjectName("titleLabel")
        self.port_label = QLabel()
        self.port_label.setObjectName("subtitleLabel")
        self.port_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        header_card = QWidget()
        header_card.setObjectName("panel")
        header_layout = QHBoxLayout(header_card)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.port_label)
        header_layout.setContentsMargins(24, 20, 24, 20)

        self.weight_label = QLabel("--")
        self.weight_label.setObjectName("valueLabel")
        self.weight_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.weight_label.setFont(QFont("Segoe UI", 140, QFont.Bold))

        self.weight_subtitle = QLabel("Kg")
        self.weight_subtitle.setObjectName("subtitleLabel")

        self.stable_label = QLabel("")
        self.stable_label.setObjectName("subtitleLabel")

        weight_card = QWidget()
        weight_card.setObjectName("card")
        weight_card_layout = QVBoxLayout(weight_card)
        weight_card_layout.addStretch(1)
        weight_card_layout.addWidget(self.weight_label, alignment=Qt.AlignLeft)
        weight_card_layout.addWidget(self.weight_subtitle, alignment=Qt.AlignLeft)
        weight_card_layout.addWidget(self.stable_label, alignment=Qt.AlignLeft)
        weight_card_layout.addStretch(1)
        weight_card_layout.setContentsMargins(36, 34, 36, 34)

        self.config_button = QPushButton("Config")
        self.config_button.clicked.connect(self.open_config)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.config_button)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(18)
        layout.addWidget(header_card)
        layout.addWidget(weight_card, 1)
        layout.addStretch(1)
        layout.addLayout(footer)

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(CONFIG_PATH):
            self._save_config(DEFAULT_CONFIG)
            log_app(f"CONFIG_LOADED: {json.dumps(DEFAULT_CONFIG)}")
            return DEFAULT_CONFIG.copy()

        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
                config = json.load(config_file)
        except (json.JSONDecodeError, IOError):
            QMessageBox.warning(
                self, "Config Error", "Unable to parse config.json. Loading defaults."
            )
            config = DEFAULT_CONFIG.copy()

        # Drop legacy keys
        for legacy in (
            "machine_id",
            "stable_count",
            "weight_scale",
            "weight_offset",
            "read_timeout_sec",
            "api_host",
            "api_port",
        ):
            config.pop(legacy, None)
        for key, value in DEFAULT_CONFIG.items():
            config.setdefault(key, value)

        log_app(f"CONFIG_LOADED: {json.dumps(config)}")
        return config

    def _save_config(self, config: Dict[str, Any]) -> None:
        clean = dict(config)
        for legacy in (
            "machine_id",
            "stable_count",
            "weight_scale",
            "weight_offset",
            "read_timeout_sec",
            "api_host",
            "api_port",
        ):
            clean.pop(legacy, None)
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as config_file:
                json.dump(clean, config_file, indent=4)
            log_app(f"CONFIG_SAVED: {json.dumps(clean)}")
        except IOError as exc:
            QMessageBox.critical(
                self, "Save Error", f"Unable to save config.json: {exc}"
            )

    def _update_config_summary(self) -> None:
        port_text = self.config.get("port", "") or "[unset]"
        if not is_calibrated(self.config):
            self.port_label.setText(f"{port_text} · setup required")
            return
        status = "Connected" if self.connection_status else "Disconnected"
        self.port_label.setText(f"{port_text} · {status}")

    def _start_api_server(self) -> None:
        if self.api_server:
            self.api_server.stop()
            self.api_server = None
        self.api_server = DigitizerAPIServer(API_HOST, API_PORT)
        if not self.api_server.start():
            QMessageBox.warning(
                self,
                "API Server",
                f"Could not bind API on {API_HOST}:{API_PORT}. "
                "Another process may be using that port.",
            )
            self.api_server = None
        self._update_config_summary()

    def get_latest_raw_bytes(self) -> bytes:
        return self.last_raw_bytes or RUNTIME.last_raw_bytes

    def capture_sample_bytes(
        self, settings: Dict[str, Any], nbytes: int = 45, timeout: float = 8.0
    ) -> bytes:
        """
        Capture one digitizer frame for index calibration.
        Prefers a complete line (readline); falls back to up to nbytes.
        """
        with self._capture_lock:
            was_running = self.running
            if was_running:
                self._stop_serial_for_capture()

            buf = bytearray()
            ser = None
            try:
                ser = serial.Serial(
                    port=settings["port"],
                    baudrate=int(settings["baud_rate"]),
                    bytesize=int(settings["data_bits"]),
                    parity=str(settings["parity"]),
                    stopbits=float(settings["stop_bits"]),
                    timeout=0.25,
                )
                # Flush stale bytes so we calibrate on a fresh frame
                try:
                    ser.reset_input_buffer()
                except Exception:
                    pass

                deadline = time.monotonic() + timeout
                # Prefer one terminated line/frame
                while time.monotonic() < deadline:
                    line = ser.readline()
                    if line:
                        buf.extend(line)
                        # Keep reading a bit if we only got a tiny fragment
                        if len(buf) >= 3:
                            break
                    QApplication.processEvents()

                # Fallback: raw block if no line terminator
                while time.monotonic() < deadline and len(buf) < nbytes:
                    chunk = ser.read(max(1, nbytes - len(buf)))
                    if chunk:
                        buf.extend(chunk)
                    else:
                        if buf:
                            break
                    QApplication.processEvents()
            except Exception as exc:
                log_app(f"CAPTURE_FAILED: {exc}")
                buf = bytearray()
            finally:
                if ser and ser.is_open:
                    try:
                        ser.close()
                    except Exception:
                        pass
                if was_running:
                    self._start_serial()

            raw = bytes(buf[:nbytes] if len(buf) > nbytes else buf)
            if raw:
                log_app(f"CAPTURE_OK: len={len(raw)} hex={raw.hex()}")
            return raw

    def _stop_serial_for_capture(self) -> None:
        """Stop serial without starting reconnect timer (capture owns the port)."""
        self.running = False
        self.stop_event.set()
        self._stop_reconnect_timer()
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass
        self.serial_port = None
        self.connection_status = False
        RUNTIME.set_connected(False)

    def open_config(self, startup: bool = False) -> bool:
        dialog = ConfigDialog(self.config, self)
        accepted = dialog.exec() == QDialog.Accepted
        if not accepted:
            return False

            self.config = dialog.get_config()
        self.config["status"] = is_calibrated(self.config)
            self._save_config(self.config)
        RUNTIME.update_config(self.config)
            self._update_config_summary()

        if not is_calibrated(self.config):
            self._reset_weight()
            return False

        if self.api_server is None:
            self._start_api_server()

        # Weight reading starts only after serial + index calibration
            if self.running:
                self._stop_serial()
                self._start_serial()
            return True

    def _start_serial(self) -> None:
        if not is_calibrated(self.config):
            log_app("SERIAL_SKIP: not calibrated")
            return

        self._stop_reconnect_timer()
        try:
            self.serial_port = serial.Serial(
                port=self.config["port"],
                baudrate=int(self.config["baud_rate"]),
                bytesize=int(self.config["data_bits"]),
                parity=str(self.config["parity"]),
                stopbits=float(self.config["stop_bits"]),
                timeout=0.2,
            )
        except (serial.SerialException, ValueError, TypeError) as exc:
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Unable to open {self.config['port']}: {exc}",
            )
            return

        self.running = True
        self.stop_event.clear()
        self.connection_status = True
        RUNTIME.set_connected(True)
        self._update_config_summary()
        log_app(
            "SERIAL_CONNECTED: "
            + json.dumps(
                {
                    "port": self.config.get("port"),
                    "baud_rate": self.config.get("baud_rate"),
                    "indexing": True,
                }
            )
        )
        self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
        self.read_thread.start()

    def _reset_weight(self) -> None:
        self.weight_label.setText("--")
        self.stable_label.setText("")

    def _stop_serial(self) -> None:
        self.running = False
        self.stop_event.set()
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass
        self.serial_port = None
        self.connection_status = False
        RUNTIME.set_connected(False)
        self._update_config_summary()
        self._reset_weight()
        self.disconnect_time = datetime.datetime.now()
        self._start_reconnect_timer()

    def _start_reconnect_timer(self) -> None:
        if not self.auto_reconnect_timer:
            self.auto_reconnect_timer = QTimer(self)
            self.auto_reconnect_timer.timeout.connect(self._attempt_reconnect)
            self.auto_reconnect_timer.start(2000)

    def _stop_reconnect_timer(self) -> None:
        if self.auto_reconnect_timer:
            self.auto_reconnect_timer.stop()
            self.auto_reconnect_timer = None
            self.disconnect_time = None

    def _attempt_reconnect(self) -> None:
        if self.running:
            return
        if not is_calibrated(self.config):
            return
        try:
            self.serial_port = serial.Serial(
                port=self.config["port"],
                baudrate=int(self.config["baud_rate"]),
                bytesize=int(self.config["data_bits"]),
                parity=str(self.config["parity"]),
                stopbits=float(self.config["stop_bits"]),
                timeout=0.2,
            )
            self.running = True
            self.stop_event.clear()
            self.connection_status = True
            RUNTIME.set_connected(True)
            self._update_config_summary()
            self._stop_reconnect_timer()
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            log_app("SERIAL_RECONNECTED")
        except (serial.SerialException, ValueError, TypeError):
            pass

    def _read_loop(self) -> None:
        while (
            not self.stop_event.is_set()
            and self.serial_port
            and self.serial_port.is_open
        ):
            try:
                line = self.serial_port.readline()
                if line:
                    self.queue.put(line)
            except serial.SerialException:
                break
            except Exception:
                break

        self.running = False
        self.queue.put(b"__SERIAL_STOPPED__")

    def _start_poll_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._process_queue)
        self.timer.start(100)

    def _process_queue(self) -> None:
        while not self.queue.empty():
            raw = self.queue.get_nowait()
            if raw == b"__SERIAL_STOPPED__":
                self._stop_serial()
                continue
            if not isinstance(raw, (bytes, bytearray)):
                continue
            message = bytes(raw).decode(errors="replace").rstrip("\r\n")
            log_app(f"SERIAL_RAW: {message}")
            self._update_weight(bytes(raw), message)

    def _update_weight(self, raw_bytes: bytes, message: str) -> None:
        # Live weight only after ASCII index calibration
        if not is_calibrated(self.config):
            return
        weight = self._extract_weight(raw_bytes, message)
        if weight is None:
            return
        self.last_message = message
        self.last_raw_bytes = raw_bytes
        RUNTIME.push_weight(weight, message, raw_bytes)
        display = RUNTIME.current_weight
        if display is not None:
            self.weight_label.setText(f"{display:.2f}")
        if RUNTIME.is_stable():
            self.stable_label.setText(
                f"{RUNTIME.stable_weight:.2f} kg "
                f"({RUNTIME.stable_count_seen}/{RUNTIME.stable_count_required})"
            )
        else:
            self.stable_label.setText(
                f"{RUNTIME.stable_count_seen}/{RUNTIME.stable_count_required}"
            )

    def _extract_weight(self, raw_bytes: bytes, message: str) -> Optional[float]:
        """Extract weight using saved ASCII index calibration only."""
        indexing = self.config.get("indexing")
        if not indexing:
            return None

        for buf in (bytes(raw_bytes), message.encode("latin-1", errors="replace")):
            frame = extract_last_complete_index_frame(buf, indexing) or buf
            weight = extract_weight_from_indexing(frame, indexing)
            if weight is not None:
                return weight
            # Soft fallback: weight slice + frame-start only (ignore distant end marker)
            soft = dict(indexing)
            soft["frame_end_char"] = None
            weight = extract_weight_from_indexing(buf, soft)
            if weight is not None:
                return weight
                return None

    def closeEvent(self, event) -> None:  # noqa: N802
        self.running = False
        self.stop_event.set()
        self._stop_reconnect_timer()
        if self.api_server:
            self.api_server.stop()
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass
        RUNTIME.set_connected(False)
        event.accept()


def main() -> None:
    _init_windows_taskbar()
    os.makedirs(APP_LOG_DIR, exist_ok=True)
    os.makedirs(API_LOG_DIR, exist_ok=True)
    log_app("APPLICATION_STARTED")
    app = QApplication(sys.argv)
    app.setApplicationName("GMDCDigitizer")
    app.setApplicationDisplayName("GMDC Digitizer")
    icon = _load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = SerialReaderApp()

    # 1) Serial + digitizer ASCII calibration must be done first
    if not is_calibrated(window.config):
        saved = window.open_config(startup=True)
        if not saved or not is_calibrated(window.config):
            sys.exit(0)

    # 2) After calibration - show dashboard and read indexed weight only
        window.show()
    if is_calibrated(window.config):
            window._start_serial()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
