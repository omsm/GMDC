"""Mines-Checkpoint logging: one daily file per lane, keep 10 days."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import re
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence

from gmdc_common.utils.logging_setup import ModbusTransactionNoiseFilter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
KEEP_DAYS = 10

_current_lane: contextvars.ContextVar[str] = contextvars.ContextVar(
    "mines_checkpoint_lane", default=""
)

_LANE_HANDLERS: dict[str, TimedRotatingFileHandler] = {}


def slug_lane_name(value: str) -> str:
    """Filesystem-safe lane folder / file stem."""
    text = str(value or "").strip().lower().replace(" ", "_")
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "checkpoint"


def get_lane_log_context() -> str:
    return str(_current_lane.get() or "").strip()


def set_lane_log_context(lane_id: str) -> contextvars.Token:
    return _current_lane.set(slug_lane_name(lane_id) if lane_id else "")


@contextlib.contextmanager
def lane_log_scope(lane_id: str) -> Iterator[str]:
    """Route log lines in this block (and same-thread work) to one lane file."""
    key = slug_lane_name(lane_id) if lane_id else ""
    token = _current_lane.set(key)
    try:
        yield key
    finally:
        _current_lane.reset(token)


def _record_lane(record: logging.LogRecord) -> str:
    """Explicit lane on the record, else the active context lane."""
    raw = str(getattr(record, "lane_id", "") or "").strip()
    if raw and raw != "-":
        return slug_lane_name(raw)
    return get_lane_log_context()


class _LaneFilter(logging.Filter):
    """Accept only records for one lane (from context or record.lane_id)."""

    def __init__(self, lane_id: str) -> None:
        super().__init__()
        self.lane_id = slug_lane_name(lane_id)

    def filter(self, record: logging.LogRecord) -> bool:
        return _record_lane(record) == self.lane_id


class _UnassignedFilter(logging.Filter):
    """Process-level / shared lines that are not tied to a lane."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not _record_lane(record)


class _LaneFormatter(logging.Formatter):
    """Fill %(lane_id)s from context without poisoning other handlers."""

    def format(self, record: logging.LogRecord) -> str:
        record.lane_id = _record_lane(record) or "-"
        return super().format(record)


def _make_daily_handler(
    path: Path, *, level: int, formatter: logging.Formatter
) -> TimedRotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        filename=str(path),
        when="midnight",
        interval=1,
        backupCount=KEEP_DAYS,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


def _close_root_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        try:
            handler.flush()
            handler.close()
        except Exception:
            pass
        root.removeHandler(handler)
    _LANE_HANDLERS.clear()


def _purge_old_lane_logs(lane_dir: Path, stem: str) -> None:
    """
    Keep only the current log plus the newest KEEP_DAYS dated backups.

    TimedRotatingFileHandler already enforces backupCount; this cleans stray
    files left by older naming schemes.
    """
    if not lane_dir.is_dir():
        return
    dated: List[Path] = []
    current = lane_dir / f"{stem}.log"
    for path in lane_dir.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name == f"{stem}.log":
            continue
        if name.startswith(f"{stem}.log.") or (
            name.startswith(f"{stem}_") and name.endswith(".log")
        ):
            dated.append(path)
    dated.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in dated[KEEP_DAYS:]:
        try:
            stale.unlink()
        except OSError:
            pass
    # Touch current so the folder always has today's file when logging starts.
    if not current.exists():
        try:
            current.touch()
        except OSError:
            pass


def setup_logging(
    level: Optional[int] = None,
    lane_ids: Optional[Sequence[str]] = None,
) -> Path:
    """
    Console + main process log + one daily-rotating file per lane.

    Layout::

        logs/main/mines_checkpoint.log
        logs/mines_entry/mines_entry.log
        logs/traffic_in/traffic_in.log
        ...

    Rolled names are ``*.log.YYYY-MM-DD``. Only the last 10 days are kept.
    """
    log_level = logging.INFO if level is None else level
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(log_level)
    _close_root_handlers()

    fmt = _LaneFormatter(
        "%(asctime)s [%(levelname)s] [%(lane_id)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(log_level)
    root.addHandler(console)

    main_dir = LOG_DIR / "main"
    main_path = main_dir / "mines_checkpoint.log"
    main_handler = _make_daily_handler(main_path, level=log_level, formatter=fmt)
    main_handler.addFilter(_UnassignedFilter())
    root.addHandler(main_handler)
    _purge_old_lane_logs(main_dir, "mines_checkpoint")

    seen = set()
    ids: Iterable[str] = lane_ids or ()
    for raw in ids:
        key = slug_lane_name(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        lane_dir = LOG_DIR / key
        lane_path = lane_dir / f"{key}.log"
        handler = _make_daily_handler(lane_path, level=log_level, formatter=fmt)
        handler.addFilter(_LaneFilter(key))
        root.addHandler(handler)
        _LANE_HANDLERS[key] = handler
        _purge_old_lane_logs(lane_dir, key)

    for name in ("pymodbus.logging", "pymodbus"):
        log = logging.getLogger(name)
        log.filters = [
            f for f in log.filters if not isinstance(f, ModbusTransactionNoiseFilter)
        ]
        log.addFilter(ModbusTransactionNoiseFilter(log_level))

    logging.getLogger("mines_checkpoint").info(
        "Logging initialized -> %s (lanes=%s, daily rotate, keep %s days)",
        LOG_DIR,
        sorted(seen) or ["(none)"],
        KEEP_DAYS,
    )
    return main_path
