"""
Load editable logging_config.py beside configuration.exe (shared deploy folder).

Must run before utils.fatal_error is imported (fatal_error uses is_stdio_unavailable).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
import types

logger = logging.getLogger(__name__)


def _logging_config_candidate_paths() -> list[str]:
    paths: list[str] = []
    if getattr(sys, "frozen", False):
        paths.append(os.path.join(os.path.dirname(sys.executable), "logging_config.py"))
    iot_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths.append(os.path.join(iot_root, "logging_config.py"))
    paths.append(os.path.join(os.path.dirname(iot_root), "Weighbridge-App", "logging_config.py"))
    paths.append(os.path.join(os.getcwd(), "logging_config.py"))
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        norm = os.path.normpath(path)
        if norm not in seen:
            seen.add(norm)
            unique.append(norm)
    return unique


def _default_logging_config_module() -> types.ModuleType:
    mod = types.ModuleType("logging_config")
    mod.CONSOLE_LOG_LEVEL = logging.DEBUG
    mod.FILE_LOG_LEVEL = logging.DEBUG

    class NullLogStream:
        def write(self, message):
            pass

        def flush(self):
            pass

        def isatty(self):
            return False

    def safe_log_stream(stream):
        if stream is not None and hasattr(stream, "write"):
            return stream
        return NullLogStream()

    def is_stdio_unavailable(stream) -> bool:
        return stream is None or not hasattr(stream, "write")

    mod.NullLogStream = NullLogStream
    mod.safe_log_stream = safe_log_stream
    mod.is_stdio_unavailable = is_stdio_unavailable
    return mod


def _apply_stdio_helpers(module: types.ModuleType) -> types.ModuleType:
    """
    Weighbridge deploy logging_config.py may only define log levels.
    IoT-Configuration also needs safe_log_stream / is_stdio_unavailable for windowed EXE.
    """
    defaults = _default_logging_config_module()
    if not hasattr(module, "CONSOLE_LOG_LEVEL"):
        module.CONSOLE_LOG_LEVEL = defaults.CONSOLE_LOG_LEVEL
    if not hasattr(module, "FILE_LOG_LEVEL"):
        module.FILE_LOG_LEVEL = defaults.FILE_LOG_LEVEL
    for name in ("NullLogStream", "safe_log_stream", "is_stdio_unavailable"):
        if not hasattr(module, name):
            setattr(module, name, getattr(defaults, name))
    return module


def bootstrap_logging_config() -> types.ModuleType:
    """
    Register logging_config in sys.modules from external file or built-in defaults.
    """
    existing = sys.modules.get("logging_config")
    if existing is not None:
        return _apply_stdio_helpers(existing)

    for cfg_path in _logging_config_candidate_paths():
        try:
            if not os.path.isfile(cfg_path):
                continue
            spec = importlib.util.spec_from_file_location("logging_config", cfg_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module = _apply_stdio_helpers(module)
                sys.modules["logging_config"] = module
                logger.info("[CONFIG] Loaded logging_config.py from: %s", cfg_path)
                return module
        except Exception as exc:
            logger.warning("[CONFIG] Failed to load logging_config from %s: %s", cfg_path, exc)

    module = _default_logging_config_module()
    sys.modules["logging_config"] = module
    logger.debug("[CONFIG] Using built-in logging_config defaults (no external file)")
    return module
