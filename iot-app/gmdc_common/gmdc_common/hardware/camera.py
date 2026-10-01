"""RTSP snapshot helpers shared by weighbridge / checkpoint apps."""

from __future__ import annotations

import logging
import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger("gmdc_common.hardware.camera")

_cv2 = None
_cv2_import_error: Optional[BaseException] = None

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _get_cv2():
    global _cv2, _cv2_import_error
    if _cv2 is not None:
        return _cv2
    if _cv2_import_error is not None:
        raise ImportError(
            "OpenCV (cv2) is required for RTSP capture. Install opencv-python."
        ) from _cv2_import_error
    try:
        import cv2

        _cv2 = cv2
        return cv2
    except ImportError as exc:
        _cv2_import_error = exc
        raise ImportError(
            "OpenCV (cv2) is required for RTSP capture. Install opencv-python."
        ) from exc


def get_local_ip(fallback: str = "0.0.0.0") -> str:
    """Best-effort local LAN IP of this PC (for checkpoint filename)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip:
                return str(ip)
        finally:
            sock.close()
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return str(ip)
    except OSError:
        pass
    return fallback


def sanitize_filename_part(value: str, default: str = "UNKNOWN") -> str:
    text = _SAFE_NAME.sub("_", str(value or "").strip())
    text = text.strip("._-")
    return text or default


def build_top_photo_filename(
    *,
    token_no: str,
    truck_no: str,
    checkpoint_ip: Optional[str] = None,
    when: Optional[datetime] = None,
) -> str:
    """
    {TOKEN}_{dd-mm-yy-HH-MM-SS}_{TRUCK}_{PC_IP}_TOP.jpg
    Example: TRIP001_06-08-26-19-54-30_OD05CA3273_192.168.10.223_TOP.jpg
    """
    ts = (when or datetime.now()).strftime("%d-%m-%y-%H-%M-%S")
    token = sanitize_filename_part(token_no, "TOKEN")
    truck = sanitize_filename_part(truck_no, "UNKNOWN")
    ip = sanitize_filename_part(
        checkpoint_ip or get_local_ip(), "0.0.0.0"
    )
    return f"{token}_{ts}_{truck}_{ip}_TOP.jpg"


def capture_rtsp_snapshot(
    rtsp_url: str,
    dest: Union[str, Path],
    *,
    open_timeout_ms: int = 5000,
    read_attempts: int = 5,
    jpeg_quality: int = 85,
) -> bool:
    """
    Grab one frame from ``rtsp_url`` and write JPEG to ``dest``.

    Returns True on success. Releases the capture handle in all cases.
    """
    url = (rtsp_url or "").strip()
    if not url:
        logger.error("RTSP capture skipped - empty URL")
        return False

    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        cv2 = _get_cv2()
    except ImportError as exc:
        logger.error("RTSP capture unavailable: %s", exc)
        return False

    cap = None
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        try:
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, float(open_timeout_ms))
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, float(open_timeout_ms))
        except Exception:
            pass
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            logger.error("RTSP open failed url=%s", url)
            return False

        frame = None
        for _ in range(max(1, int(read_attempts))):
            ok, frame = cap.read()
            if ok and frame is not None:
                break
        if frame is None:
            logger.error("RTSP connected but no frame url=%s", url)
            return False

        ok = cv2.imwrite(
            str(dest_path),
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
        )
        if not ok:
            logger.error("Failed to write JPEG %s", dest_path)
            return False
        logger.info("RTSP snapshot saved %s", dest_path.name)
        return True
    except Exception as exc:
        logger.exception("RTSP capture error: %s", exc)
        return False
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
