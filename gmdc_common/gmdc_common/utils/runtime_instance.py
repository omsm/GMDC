"""Replace a prior copy of the same runtime (single instance per app)."""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("gmdc_common.utils.runtime_instance")

GRACEFUL_STOP_TIMEOUT_S = 5.0
POST_EXIT_SETTLE_S = 0.5


def _pid_file_path(base_dir: Path, instance_key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in instance_key)
    return base_dir / f".{safe}.pid"


def _read_pid(path: Path) -> Optional[int]:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text)
    except (FileNotFoundError, ValueError, OSError):
        return None


def _write_pid(path: Path) -> None:
    try:
        path.write_text(str(os.getpid()), encoding="utf-8")
    except OSError as exc:
        logger.debug("Could not write pid file %s: %s", path, exc)


def _pid_alive(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_pid(pid: int) -> None:
    if pid == os.getpid():
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return
    deadline = time.monotonic() + GRACEFUL_STOP_TIMEOUT_S
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def replace_prior_runtime_instance(instance_key: str, base_dir: Path) -> int:
    """
    Before opening hardware: stop the previous instance with the same key, if any.

    Uses a PID file in ``base_dir``. On Windows, tries ``checkpoint-config``
    instance_guard.replace_prior_instances when importable; otherwise PID file.
    """
    base_dir = Path(base_dir)
    if sys.platform == "win32":
        try:
            root = base_dir.parent if base_dir.name in ("Mines-Checkpoint", "Mines-WB") else base_dir
            cfg = root / "checkpoint-config"
            if cfg.is_dir() and str(cfg) not in sys.path:
                sys.path.insert(0, str(cfg))
            from utils.instance_guard import replace_prior_instances

            return int(
                replace_prior_instances(instance_key, logger_name="runtime_instance")
            )
        except Exception:
            logger.debug("Windows instance_guard unavailable; using pid file", exc_info=True)

    path = _pid_file_path(base_dir, instance_key)
    prior = _read_pid(path)
    replaced = 0
    if prior is not None and _pid_alive(prior):
        logger.warning(
            "Stopping prior %s instance (pid=%s)", instance_key, prior
        )
        _terminate_pid(prior)
        if POST_EXIT_SETTLE_S > 0:
            time.sleep(POST_EXIT_SETTLE_S)
        if not _pid_alive(prior):
            replaced = 1
    _write_pid(path)
    if replaced:
        logger.info("Replaced prior %s instance", instance_key)
    return replaced
