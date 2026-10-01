"""
Load editable timeout_config.py for IoT-Configuration at runtime.

Deploy layout (installer / application-exe zip):
  {install_folder}/
    configuration.exe
    weighbridge-app.exe
    timeout_config.py   <-- ONE shared file; edit this at site

Weighbridge-App loads the same path via config/constants.py.
This loader always prefers that external file over any bundled copy.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys

logger = logging.getLogger(__name__)


def timeout_config_candidate_paths() -> list[str]:
    """Paths to search for the shared editable timeout_config.py."""
    paths: list[str] = []
    if getattr(sys, "frozen", False):
        paths.append(os.path.join(os.path.dirname(sys.executable), "timeout_config.py"))
    iot_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(iot_root)
    # Dev: operators usually edit Weighbridge-App/timeout_config.py (shared with runtime EXE)
    paths.append(os.path.join(repo_root, "Weighbridge-App", "timeout_config.py"))
    paths.append(os.path.join(os.getcwd(), "timeout_config.py"))
    paths.append(os.path.join(iot_root, "timeout_config.py"))
    seen: set[str] = set()
    unique: list[str] = []
    for path in paths:
        norm = os.path.normpath(path)
        if norm not in seen:
            seen.add(norm)
            unique.append(norm)
    return unique


def get_timeout_config_path() -> str | None:
    """Return the first existing timeout_config.py path, or None."""
    for path in timeout_config_candidate_paths():
        if os.path.isfile(path):
            return path
    return None


def load_timeout_config_module():
    """
    Load timeout_config.py from the deploy folder (beside configuration.exe).
    Returns None only when no file exists and import fails.
    Re-reads the file on each call so VALID_CARDS_START_INDEX edits apply without restart.
    """
    module_name = "timeout_config_site_external"
    if module_name in sys.modules:
        del sys.modules[module_name]

    for cfg_path in timeout_config_candidate_paths():
        try:
            if not os.path.isfile(cfg_path):
                continue
            spec = importlib.util.spec_from_file_location(module_name, cfg_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                logger.info("[CONFIG] Loaded timeout_config.py from: %s", cfg_path)
                return module
        except Exception as exc:
            logger.warning("[CONFIG] Failed to load timeout_config from %s: %s", cfg_path, exc)
            continue

    try:
        import timeout_config as module  # type: ignore

        logger.debug("[CONFIG] Using in-tree timeout_config (development only)")
        return module
    except Exception:
        return None
