# -*- mode: python ; coding: utf-8 -*-
"""macOS onefile: iot-configuration (checkpoint-config)."""

import os

from PyInstaller.utils.hooks import collect_all

numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")

try:
    wv_datas, wv_binaries, wv_hiddenimports = collect_all("webview")
except Exception:
    wv_datas, wv_binaries, wv_hiddenimports = [], [], []

spec_dir = os.path.dirname(os.path.abspath(SPEC))
repo_root = os.path.abspath(os.path.join(spec_dir, "..", ".."))
app_root = os.path.join(repo_root, "checkpoint-config")

datas = [
    (os.path.join(app_root, "templates"), "templates"),
    (os.path.join(app_root, "static"), "static"),
    (os.path.join(app_root, "rajmines.ico"), "."),
]

a = Analysis(
    [os.path.join(app_root, "app.py")],
    pathex=[
        app_root,
        os.path.join(app_root, "services"),
        os.path.join(app_root, "utils"),
        repo_root,
    ],
    binaries=numpy_binaries + cv2_binaries + wv_binaries,
    datas=datas + numpy_datas + cv2_datas + wv_datas,
    hiddenimports=[
        "flask",
        "flask_cors",
        "werkzeug",
        "jinja2",
        "jinja2.ext",
        "cv2",
        "numpy",
        "serial",
        "serial.tools",
        "serial.tools.list_ports",
        "serial.serialutil",
        "pymodbus",
        "pymodbus.client",
        "pymodbus.client.tcp",
        "pymodbus.client.udp",
        "pymodbus.client.serial",
        "pymodbus.exceptions",
        "minimalmodbus",
        "paho.mqtt",
        "paho.mqtt.client",
        "requests",
        "urllib3",
        "certifi",
        "chardet",
        "charset_normalizer",
        "idna",
        "reportlab",
        "PIL",
        "PIL.Image",
        "webview",
        "webview.platforms",
        "webview.platforms.cocoa",
        "objc",
        "AppKit",
        "Foundation",
        "WebKit",
        "config",
        "services",
        "services.config_manager",
        "services.server_service",
        "services.rfid_service",
        "services.camera_service",
        "services.display_service",
        "services.digitizer_service",
        "services.io_controller_service",
        "services.network_scanner",
        "services.pdf_report_generator",
        "services.audio_service",
        "services.updater_service",
        "utils",
        "utils.splash_screen",
        "utils.browser_launcher",
        "utils.mosquitto_manager",
        "utils.mosquitto_progress_ui",
        "utils.fatal_error",
        "utils.webview_stderr",
        "utils.instance_guard",
        "utils.timeout_config_loader",
        "utils.logging_config_loader",
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
        "importlib.util",
        "mmap",
        "multiprocessing",
        "multiprocessing.heap",
        "multiprocessing.sharedctypes",
        "mqtt_broker_setup",
        "mqtt_broker_setup.ensure",
        "mqtt_broker_setup.mosquitto_setup",
    ]
    + numpy_hiddenimports
    + cv2_hiddenimports
    + wv_hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "pandas",
        "scipy",
        "conversion",
        "logging_config",
        "timeout_config",
        "pywebview.platforms.winforms",
        "pywebview.platforms.edgechromium",
    ],
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
    name="iot-configuration",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    # Must stay False: argv emulation runs an Apple Event loop that conflicts
    # with pywebview/Cocoa and re-launches __main__ in a tight loop.
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(app_root, "rajmines.ico"),
)
