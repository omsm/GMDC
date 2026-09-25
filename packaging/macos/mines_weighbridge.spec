# -*- mode: python ; coding: utf-8 -*-
"""macOS onefile: mines-weighbridge runtime."""

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")

spec_dir = os.path.dirname(os.path.abspath(SPEC))
repo_root = os.path.abspath(os.path.join(spec_dir, "..", ".."))
app_root = os.path.join(repo_root, "Mines-WB")
gmdc_root = os.path.join(repo_root, "gmdc_common")

gmdc_datas, gmdc_binaries, gmdc_hidden = collect_all("gmdc_common")
gmdc_subs = collect_submodules("gmdc_common")

datas = (
    gmdc_datas
    + cv2_datas
    + numpy_datas
    + [(os.path.join(app_root, "static", "web"), os.path.join("static", "web"))]
)

a = Analysis(
    [os.path.join(app_root, "main.py")],
    pathex=[
        app_root,
        gmdc_root,
        repo_root,
        os.path.join(repo_root, "mqtt_broker_setup"),
    ],
    binaries=gmdc_binaries + cv2_binaries + numpy_binaries,
    datas=datas,
    hiddenimports=[
        "flask",
        "flask_cors",
        "werkzeug",
        "jinja2",
        "requests",
        "urllib3",
        "certifi",
        "dotenv",
        "pymodbus",
        "pymodbus.client",
        "pymodbus.client.tcp",
        "pymodbus.client.serial",
        "paho.mqtt",
        "paho.mqtt.client",
        "cv2",
        "numpy",
        "gmdc_common",
        "mqtt_broker_setup",
        "mqtt_broker_setup.ensure",
        "mqtt_broker_setup.mosquitto_setup",
        "api",
        "api.server",
        "config",
        "config.settings",
        "config.wb_branding",
        "core",
        "core.app_context",
        "core.state_machine",
        "core.transaction",
        "core.workflow",
        "hardware",
        "services",
        "services.digitizer_client",
        "services.display_service",
        "services.frontend_mqtt",
        "services.oci_client",
        "services.rfid_control",
        "services.voice_service",
        "utils",
        "utils.logging_setup",
    ]
    + list(gmdc_hidden)
    + list(gmdc_subs)
    + list(cv2_hiddenimports)
    + list(numpy_hiddenimports),
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "pandas", "scipy", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="mines-weighbridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
