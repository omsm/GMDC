"""Tare WB logging - shared GMDC logger."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from gmdc_common.utils.logging_setup import setup_logging as _setup_logging

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"


def setup_logging(level: Optional[int] = None) -> None:
    kwargs = {
        "app_name": "tare_wb",
        "log_dir": LOG_DIR,
        "log_file": "tare_wb.log",
        "backup_count": 10,
    }
    if level is not None:
        kwargs["level"] = level
    _setup_logging(**kwargs)
