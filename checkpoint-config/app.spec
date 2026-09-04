# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for E-Rawanna IoT Configuration Application
This spec file configures PyInstaller to build a standalone executable (ONEFILE mode)
Creates a single .exe file with all dependencies bundled

Recent Updates:
- Digitizer configuration now supports bytesize, parity, and stopbits
- Enhanced digitizer parsing for "kg" format: {spaces}{number} kg    G 000000 A
- Boom barrier direct mode with separate open_pin and close_pin support
"""

import os

from PyInstaller.utils.hooks import collect_all

# Bundle NumPy and OpenCV completely (hiddenimports alone is insufficient for one-file EXE).
numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")
cv2_datas, cv2_binaries, cv2_hiddenimports = collect_all("cv2")

# Application metadata
app_name = 'configuration'
app_version = '2.3.5.4'

# Get the directory where this spec file is located
spec_root = os.path.dirname(os.path.abspath(SPEC))

# Data files to include (templates, static files, config files)
# Note: OpenCV and numpy data files are handled automatically by PyInstaller hooks
# IMPORTANT: Include services directory to ensure all Python modules are bundled
datas = [
    # Flask templates
    ('templates', 'templates'),
    # Static files (CSS, JS, audio)
    ('static', 'static'),
    # Application icon (copy to exe directory)
    ('rajmines.ico', '.'),
    # Editable files loaded at runtime from beside configuration.exe (not bundled):
    # - conversion.py
    # - logging_config.py
    # - timeout_config.py  (ONE file for both EXEs - built from Weighbridge-App/timeout_config.py)
    # NOTE: Do NOT add services/ or utils/ to datas - they are Python packages
    # and should be auto-detected by PyInstaller's analysis
]

# Analysis: Collect all Python files and dependencies
a = Analysis(
    # Main entry point
    ['app.py'],
    
    # Pathex: Additional paths to search for modules
    pathex=[
        spec_root,
        os.path.join(spec_root, 'services'),
        os.path.join(spec_root, 'utils'),
    ],
    
    # Binaries: External binaries to include (NumPy/OpenCV native libs)
    binaries=numpy_binaries + cv2_binaries,
    
    # Datas: Data files to include (templates, static files, config files)
    datas=datas + numpy_datas + cv2_datas,
    
    # Hidden imports: Modules that PyInstaller might not detect automatically
    hiddenimports=[
        # Flask and related
        'flask',
        'flask_cors',
        'werkzeug',
        'jinja2',
        'jinja2.ext',
        
        # OpenCV (cv2) - often needs explicit imports
        'cv2',
        'numpy',
        'numpy.core._methods',
        'numpy.lib.format',
        
        # Serial communication (pyserial)
        # Required for digitizer with configurable bytesize, parity, stopbits
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'serial.serialutil',
        'serial.win32',  # Windows-specific serial support
        
        # Modbus (pymodbus 3.6.3 uses new API, no .sync module)
        'pymodbus',
        'pymodbus.client',
        'pymodbus.client.tcp',
        'pymodbus.client.udp',
        'pymodbus.client.serial',
        'pymodbus.exceptions',
        'minimalmodbus',
        
        # MQTT
        'paho.mqtt',
        'paho.mqtt.client',
        
        # HTTP requests
        'requests',
        'requests.adapters',
        'requests.auth',
        'requests.compat',
        'requests.cookies',
        'requests.exceptions',
        'requests.models',
        'requests.packages',
        'requests.sessions',
        'requests.structures',
        'requests.utils',
        'urllib3',
        'urllib3._base_connection',
        'urllib3._collections',
        'urllib3._request_methods',
        'urllib3._version',
        'urllib3.connection',
        'urllib3.connectionpool',
        'urllib3.exceptions',
        'urllib3.fields',
        'urllib3.filepost',
        'urllib3.poolmanager',
        'urllib3.response',
        'urllib3.util',
        'urllib3.util.connection',
        'urllib3.util.proxy',
        'urllib3.util.request',
        'urllib3.util.response',
        'urllib3.util.retry',
        'urllib3.util.ssl_',
        'urllib3.util.timeout',
        'urllib3.util.url',
        'urllib3.contrib',
        'urllib3.contrib.pyopenssl',
        'certifi',
        # Character encoding detection (required by requests)
        'chardet',
        'chardet.charsetgroupprober',
        'chardet.charsetprober',
        'chardet.codingstatemachine',
        'chardet.compat',
        'chardet.enums',
        'chardet.escprober',
        'chardet.hebrewprober',
        'chardet.langbulgarianmodel',
        'chardet.langcyrillicmodel',
        'chardet.langgreekmodel',
        'chardet.langhebrewmodel',
        'chardet.langthaimodel',
        'chardet.latin1prober',
        'chardet.mbcharsetprober',
        'chardet.mbcsgroupprober',
        'chardet.mbcssm',
        'chardet.sbcharsetprober',
        'chardet.sjisprober',
        'chardet.universaldetector',
        'chardet.utf8prober',
        'charset_normalizer',  # Alternative charset detection
        'charset_normalizer.api',
        'charset_normalizer.constant',
        'charset_normalizer.models',
        'charset_normalizer.utils',
        'idna',  # Internationalized Domain Names support
        
        # PDF generation (ReportLab) - comprehensive imports
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.pdfgen.canvas',
        'reportlab.pdfgen.textobject',
        'reportlab.lib',
        'reportlab.lib.colors',
        'reportlab.lib.enums',  # Required for TA_CENTER, TA_LEFT, TA_RIGHT
        'reportlab.lib.pagesizes',
        'reportlab.lib.styles',
        'reportlab.lib.units',
        'reportlab.lib.utils',
        'reportlab.lib.rl_accel',  # ReportLab acceleration module
        'reportlab.platypus',
        'reportlab.platypus.doctemplate',
        'reportlab.platypus.flowables',
        'reportlab.platypus.frames',
        'reportlab.platypus.images',
        'reportlab.platypus.paragraph',
        'reportlab.platypus.paraparser',
        'reportlab.platypus.tableofcontents',
        'reportlab.platypus.tables',
        'reportlab.platypus.xpreformatted',
        'reportlab.rl_config',  # ReportLab configuration
        'reportlab.rl_settings',  # ReportLab settings
        # Pillow (PIL) - required by reportlab for image handling
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'PIL._tkinter_finder',  # PIL tkinter support
        
        # Application modules - IMPORTANT: List all service modules explicitly
        'config',
        'services',
        'services.config_manager',
        'services.server_service',
        'services.rfid_service',
        'services.camera_service',
        'services.display_service',
        'services.digitizer_service',  # Digitizer with enhanced parsing
        'services.io_controller_service',  # I/O controller with boom barrier support
        'services.network_scanner',
        'services.pdf_report_generator',  # PDF report generation
        
        # Webview for native application window (pywebview)
        'webview',
        'pywebview',
        'pywebview.platforms',
        'pywebview.platforms.winforms',  # Windows-specific webview
        'pywebview.platforms.edgechromium',
        'pywebview.js',
        'pywebview.js.api',
        'utils.browser_launcher',
        
        # Standard library modules that might be missed
        'threading',
        'json',
        'webbrowser',
        'socket',
        'struct',
        'queue',
        'time',
        're',  # Regex for digitizer parsing
        'ctypes',  # Windows API calls for icon setting
        'ctypes.wintypes',  # Windows types
        'importlib.util',  # Dynamic module loading for conversion.py
        'base64',  # Base64 encoding for file save dialog
        # Tkinter for splash screen
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.font',
        # Application utility modules
        'utils',
        'utils.splash_screen',
        'utils.browser_launcher',
        'utils.mosquitto_manager',
        'utils.mosquitto_progress_ui',
        'utils.fatal_error',
        'utils.webview_stderr',
        'utils.instance_guard',
        'utils.timeout_config_loader',
        'utils.logging_config_loader',
        'services.audio_service',
        'services.updater_service',
    ] + numpy_hiddenimports + cv2_hiddenimports,
    
    # Hookspath: Custom hooks directory (if any)
    hookspath=[],
    
    # Runtime hooks: Custom runtime hooks (if any)
    runtime_hooks=[],
    
    # Excludes: Modules to exclude (to reduce size)
    excludes=[
        'matplotlib',
        'pandas',
        'scipy',
        'conversion',
        'logging_config',
        'timeout_config',
        # Note: PIL is NOT excluded - it's required by reportlab for image handling
    ],
    
    # Noarchive: Don't create archive (for debugging)
    noarchive=False,
)

# PYZ: Python bytecode archive
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,  # No encryption
)

# EXE: Executable configuration (ONEFILE mode - single .exe)
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
    console=False,  # Set to True temporarily to see errors, change back to False after debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(spec_root, 'rajmines.ico'),  # Application icon - embeds icon in .exe file
)
