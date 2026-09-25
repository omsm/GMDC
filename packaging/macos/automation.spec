# -*- mode: python ; coding: utf-8 -*-
"""macOS onefile: automation launcher (picks checkpoint vs weighbridge)."""

import os

spec_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(spec_dir, "automation_launcher.py")],
    pathex=[spec_dir],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "cv2"],
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
    name="automation",
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
