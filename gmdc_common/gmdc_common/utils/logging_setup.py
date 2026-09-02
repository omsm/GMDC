"""Shared rotating-file + console logging setup for GMDC apps."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Union


class ModbusTransactionNoiseFilter(logging.Filter):
    """
    Drop pymodbus transaction-id mismatch errors unless running at DEBUG.

    A shared or desynchronised Modbus device makes pymodbus log
    "request ask for transaction_id=N but got id=M, Skipping." for every stale
    frame it discards, several times per second. The I/O controller reports the
    condition once per resync, so these lines only bury real errors.

    pymodbus collapses an immediately repeated message into the literal
    "Repeating....", which carries no text of its own. It is dropped only when
    it stands in for a message this filter already suppressed, so a repeat of a
    genuine error still reaches the log.
    """

    _MARKER = "but got id="
    _REPEAT = "Repeating...."

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__()
        self.level = level
        self._suppressed_last = False

    def filter(self, record: logging.LogRecord) -> bool:
        if self.level <= logging.DEBUG:
            return True
        message = record.getMessage()
        if message.startswith(self._REPEAT):
            return not self._suppressed_last
        self._suppressed_last = self._MARKER in message
        return not self._suppressed_last


def _install_modbus_noise_filter(level: int) -> None:
    for name in ("pymodbus.logging", "pymodbus"):
        log = logging.getLogger(name)
        log.filters = [
            f for f in log.filters if not isinstance(f, ModbusTransactionNoiseFilter)
        ]
        log.addFilter(ModbusTransactionNoiseFilter(level))


def setup_logging(
    *,
    app_name: str = "gmdc",
    log_dir: Optional[Union[str, Path]] = None,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    max_bytes: int = 5_000_000,
    backup_count: int = 5,
) -> Path:
    """
    Configure root logging with console + rotating file handlers.

    Returns the resolved log file path. Safe to call more than once; existing
    root handlers are cleared so reloads do not duplicate output.
    """
    if log_dir is None:
        log_dir = Path.cwd() / "logs"
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    file_name = log_file or f"{app_name}.log"
    log_path = log_dir / file_name

    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(level)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    _install_modbus_noise_filter(level)

    logging.getLogger(app_name).info("Logging initialized -> %s", log_path)
    return log_path
