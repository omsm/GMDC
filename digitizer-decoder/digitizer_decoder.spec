# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for GMDC Digitizer Decoder (Windows .exe).

ONEFILE build with console so the dashboard URL is visible.
Writable files live beside the .exe:
  - config.json  (copied from the bundle on first run)
  - logs/
"""

from __future__ import annotations

import os

spec_root = os.path.dirname(os.path.abspath(SPEC))
app_name = "DigitizerDecoder"

datas = [
    (os.path.join(spec_root, "static"), "static"),
    (os.path.join(spec_root, "VERSION"), "."),
    (os.path.join(spec_root, "config.json"), "."),
]

hiddenimports = [
    "flask",
    "werkzeug",
    "jinja2",
    "serial",
    "serial.tools",
    "serial.tools.list_ports",
    "serial.serialutil",
    "serial.win32",
    "paho",
    "paho.mqtt",
    "paho.mqtt.client",
    "api",
    "api.server",
    "api.endpoints",
    "config",
    "config.settings",
    "core",
    "core.app_context",
    "services",
    "services.index_engine",
    "services.mqtt_bridge",
    "services.serial_service",
    "services.weight_runtime",
    "ui_os",
]

a = Analysis(
    [os.path.join(spec_root, "main.py")],
    pathex=[spec_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "pandas",
        "scipy",
        "tkinter",
        "PySide6",
        "PyQt5",
        "PyQt6",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

_icon = os.path.join(spec_root, "gmdc.ico")
_exe_kwargs = {}
if os.path.isfile(_icon):
    _exe_kwargs["icon"] = _icon

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    **_exe_kwargs,
)
