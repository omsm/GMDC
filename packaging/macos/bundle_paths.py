"""Resolve install / bundle root for frozen (PyInstaller) and source runs."""

from __future__ import annotations

import sys
from pathlib import Path


def app_install_root() -> Path:
    """
    Directory that contains the shipped binaries and editable site files
    (iot_configuration.json, .env, voice/, conversion.py, …).

    Frozen: folder next to the executable (Mines-Automation/).
    Source: the application package root (Mines-Checkpoint/ or Mines-WB/).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # packaging/macos/automation_launcher.py → packaging/macos → packaging → repo
    # Callers in Mines-* pass their own package root via override when needed.
    return Path(__file__).resolve().parent


def mines_package_root(package_file: str) -> Path:
    """Root for a Mines-* package: frozen → install dir; else → package dir."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(package_file).resolve().parent.parent
