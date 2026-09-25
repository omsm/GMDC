#IoT - Weighbridge Configuration

import sys
import os

# PyInstaller EXE must re-enter this binary for the post-exit update worker (see services/updater_service.py).
if __name__ == "__main__" and len(sys.argv) >= 3 and sys.argv[1] == "--iot-update-worker":
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)
    from services.updater_service import run_update_worker_main

    run_update_worker_main(sys.argv[2])
    raise SystemExit(0)

from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS
import json
import time
import logging
import threading
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import warnings

bootstrap_logger = logging.getLogger("iot_config.bootstrap")

# Handle PyInstaller executable paths
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    base_path = sys._MEIPASS  # PyInstaller temporary folder
    template_folder = os.path.join(base_path, 'templates')
    static_folder = os.path.join(base_path, 'static')
    # For logs and config, use executable directory (not temp folder)
    app_data_path = os.path.dirname(sys.executable)
    os.chdir(app_data_path)
    # CRITICAL: Ensure base_path is in sys.path so Python can find services package
    if base_path not in sys.path:
        sys.path.insert(0, base_path)
    # Ensure services and utils packages are in Python path
    if base_path not in sys.path:
        sys.path.insert(0, base_path)
else:
    # Running as script
    base_path = os.path.dirname(os.path.abspath(__file__))
    template_folder = os.path.join(base_path, 'templates')
    static_folder = os.path.join(base_path, 'static')
    app_data_path = base_path

log_dir = os.path.join(app_data_path, "configuration_logs")
log_file = os.path.join(log_dir, "IoT-Configuration.log")

# Load logging_config from deploy folder before fatal_error (uses is_stdio_unavailable).
if getattr(sys, "frozen", False) and base_path not in sys.path:
    sys.path.insert(0, base_path)
from utils.logging_config_loader import bootstrap_logging_config

bootstrap_logging_config()

from utils.fatal_error import fatal_exit

# Import configuration
from config import (
    DEBUG, APP_NAME, APP_VERSION, HOST, PORT,
    CONFIG_FILE, REQUIRE_DEVICE_INFO, UPDATE_CHECK_INTERVAL_SECONDS,
    ENABLE_CAMERA_CONFIGURATION,
    ENABLE_WB_SENSOR_TEST_SKIP,
    APPLICATION_UI_MODE,
    WEBVIEW_WINDOW_READY_TIMEOUT,
    CHROME_EXECUTABLE_PATH,
)

# Runtime debug flags (can be toggled via admin/debug API)
RUNTIME_DEBUG = DEBUG
RUNTIME_REQUIRE_DEVICE_INFO = REQUIRE_DEVICE_INFO

# Admin password for enabling debug mode via UI
ADMIN_DEBUG_PASSWORD = "osm@csmpl#123"

# Admin password for editing API endpoints during Finish Setup
ADMIN_API_ENDPOINTS_PASSWORD = "iot-app@Csmpl@123"

# Import logging configuration from root level (if available)
# Try multiple import paths to handle different execution contexts
try:
    # Try direct import (when running from root)
    from logging_config import FILE_LOG_LEVEL, CONSOLE_LOG_LEVEL, safe_log_stream, is_stdio_unavailable
except ImportError:
    try:
        # Try adding parent directory to path (when running as module)
        parent_dir = os.path.dirname(os.path.abspath(__file__))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from logging_config import FILE_LOG_LEVEL, CONSOLE_LOG_LEVEL, safe_log_stream, is_stdio_unavailable
    except ImportError:
        # Fallback to defaults if logging_config.py doesn't exist
        FILE_LOG_LEVEL = logging.DEBUG
        CONSOLE_LOG_LEVEL = logging.DEBUG

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

        def is_stdio_unavailable(stream):
            return stream is None or not hasattr(stream, "write")

# Import conversion helpers (for digitizer preview)
# ALWAYS load from external file (never from bundle) - same as Weighbridge-App
# This ensures site-specific edits are always used, even if file was bundled during development
import importlib.util

if getattr(sys, 'frozen', False):
    # Running as compiled executable - check for conversion.py in same directory
    conversion_base_path = os.path.dirname(sys.executable)
    conversion_path = os.path.join(conversion_base_path, 'conversion.py')
else:
    # Development mode - use project root
    conversion_base_path = os.path.dirname(os.path.abspath(__file__))
    conversion_path = os.path.join(conversion_base_path, 'conversion.py')

if os.path.exists(conversion_path):
    try:
        # Remove from sys.modules to force fresh load from external file
        if 'conversion' in sys.modules:
            del sys.modules['conversion']
        
        # Clear .pyc cache file if it exists
        pyc_path = conversion_path + 'c'
        if os.path.exists(pyc_path):
            try:
                os.remove(pyc_path)
            except Exception:
                pass
        
        # Load directly from file using importlib.util (bypasses import cache)
        spec = importlib.util.spec_from_file_location('conversion', conversion_path)
        if spec and spec.loader:
            conversion_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(conversion_module)
            
            # Get Digitizer_Convert class from the loaded module
            Digitizer_Convert = getattr(conversion_module, 'Digitizer_Convert', None)
            
            if Digitizer_Convert is None:
                raise ImportError("Digitizer_Convert class not found in conversion.py")
            
            # Log version and path for verification (using print since logger not initialized yet)
            version = getattr(conversion_module, '__version__', 'unknown')
            bootstrap_logger.info(f"[IoT-Config] Loaded conversion.py v{version} from: {conversion_path}")
        else:
            raise ImportError(f"Could not create spec for conversion.py at {conversion_path}")
    except Exception as e:
        bootstrap_logger.error(f"[IoT-Config] ERROR: Could not load conversion.py: {e}")
        fatal_exit(
            f"Could not load conversion.py:\n{e}\n\nExpected file:\n{conversion_path}",
            title=APP_NAME,
            log_path=log_file,
        )
else:
    fatal_exit(
        "conversion.py not found.\n\n"
        f"Place conversion.py next to the executable:\n{conversion_path}\n\n"
        "This file is required and is not bundled inside the EXE.",
        title="E-Rawanna",
        log_path=log_file,
    )

# Import services early to ensure PyInstaller includes them
# These imports are at top level so PyInstaller's static analysis can find them
# Using try/except to handle import errors gracefully
try:
    from services.config_manager import ConfigManager
    from services.server_service import ServerService
    from services.rfid_service import (
        RFIDService,
        get_valid_cards_start_index,
        get_valid_card_char_lengths,
        validate_rfid_section_save,
    )
    from services.camera_service import CameraService
    from services.display_service import DisplayService
    from services.digitizer_service import (
        DigitizerService,
        validate_digitizer_section_save,
        get_digitizer_calibration_min_weight_kg,
    )
    from services.io_controller_service import IOControllerService
    from services.network_scanner import NetworkScanner
    from services.pdf_report_generator import PDFReportGenerator
    from services.audio_service import AudioService
    from services.updater_service import UpdaterService
except ImportError as e:
    import traceback

    bootstrap_logger.critical(f"CRITICAL: Failed to import services: {e}")
    fatal_exit(
        f"Failed to load application modules:\n{e}\n\n"
        f"Working directory: {os.getcwd()}\n"
        f"Python path: {sys.path}",
        title="E-Rawanna",
        log_path=log_file,
    )

# ============== Setup Logging ==============
os.makedirs(log_dir, exist_ok=True)

# Configure logging
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

# Set up root logger - Use FILE_LOG_LEVEL from logging_config.py for file handler
# Create handlers separately to set different levels
file_handler = TimedRotatingFileHandler(
    filename=log_file,
    when='midnight',
    interval=1,
    backupCount=10,
    encoding='utf-8'
)
file_handler.setLevel(FILE_LOG_LEVEL)
file_handler.setFormatter(logging.Formatter(log_format, date_format))

_console_unavailable = is_stdio_unavailable(sys.stdout)
console_handler = logging.StreamHandler(safe_log_stream(sys.stdout))
console_handler.setLevel(CONSOLE_LOG_LEVEL)
console_handler.setFormatter(logging.Formatter(log_format, date_format))

# Set up root logger
logging.basicConfig(
    level=logging.DEBUG,  # Root logger at DEBUG to allow all levels
    format=log_format,
    datefmt=date_format,
    handlers=[
        file_handler,  # File handler uses FILE_LOG_LEVEL
        console_handler,  # Console handler uses CONSOLE_LOG_LEVEL (safe when stdout is None)
    ],
)

if _console_unavailable:
    logging.getLogger(__name__).info(
        "Console logging disabled (no stdout in windowed EXE); using file log only."
    )

# Get logger for this module
logger = logging.getLogger(__name__)

# Suppress Flask development server warning
os.environ['FLASK_ENV'] = 'production' if not RUNTIME_DEBUG else 'development'
# Set werkzeug to INFO level to show more Flask logs (but not too verbose)
logging.getLogger('werkzeug').setLevel(logging.INFO)

# Suppress warnings
warnings.filterwarnings('ignore', category=UserWarning)

# Log application startup
logger.info(f"{'='*50}")
logger.info(f"{APP_NAME} v{APP_VERSION} - Starting")
logger.info(f"Mode: {'DEBUG' if RUNTIME_DEBUG else 'PRODUCTION'}")
logger.info(f"Camera configuration UI: {'enabled' if ENABLE_CAMERA_CONFIGURATION else 'disabled'}")
logger.info(f"Log file: {log_file}")
logger.info(f"{'='*50}")

# Show splash screen first
from utils.splash_screen import show_splash_screen
splash = show_splash_screen("Starting Application, Please wait!")
if splash:
    splash.update()

# Give splash screen a moment to display
import time
time.sleep(0.3)

# Close splash screen before Mosquitto setup
if splash:
    logger.info("Closing splash screen...")
    try:
        # Close just sets a flag - completely non-blocking
        splash.close()
    except Exception as e:
        logger.warning(f"Error closing splash screen: {e}")
    finally:
        # Clear reference immediately
        splash = None
        # Small delay to let thread process the close flag
        time.sleep(0.3)

# Setup Mosquitto broker before starting application
logger.info("Importing Mosquitto manager...")
from utils.mosquitto_manager import ensure_mosquitto_ready

logger.info("Checking Mosquitto MQTT broker...")
try:
    logger.info("Calling ensure_mosquitto_ready()...")
    success, message = ensure_mosquitto_ready()
    logger.info(f"Mosquitto setup completed: success={success}, message={message}")
except Exception as e:
    logger.error(f"Error during Mosquitto setup: {e}", exc_info=True)
    success = False
    message = str(e)

if not success:
    error_msg = f"Mosquitto setup failed: {message}"
    logger.error(error_msg)
    logger.error(f"\n{'='*80}")
    logger.error("MOSQUITTO SETUP FAILED")
    logger.error("="*80)
    logger.error(f"Error: {message}")
    logger.error("The application cannot start without Mosquitto broker.")
    logger.error("Please install Mosquitto manually or run as administrator.")
    logger.error("="*80)
    fatal_exit(
        f"Mosquitto MQTT broker is required but setup failed.\n\n{message}\n\n"
        "Install Mosquitto or run the application as administrator.\n"
        f"See log: {log_file}",
        title=APP_NAME,
        log_path=log_file,
    )

logger.info(f"Mosquitto broker: {message}")

# Show splash screen again after Mosquitto setup completes
splash = show_splash_screen("Starting Application, Please wait!")
if splash:
    splash.update()

# Services are already imported at top of file for PyInstaller compatibility

# Initialize Flask with explicit paths for PyInstaller compatibility
app = Flask(__name__, 
            template_folder=template_folder,
            static_folder=static_folder)
CORS(app)

# Initialize services
config_manager = ConfigManager()


@app.context_processor
def inject_wb_type():
    from services.profiles import (
        CHECKPOINT_TYPE_CHOICES,
        profile_public_dict,
    )
    ct = config_manager.get_checkpoint_type()
    return {
        "wb_type": config_manager.get_wb_type(),
        "checkpoint_type": ct,
        "checkpoint_profile": profile_public_dict(ct),
        "checkpoint_type_choices": CHECKPOINT_TYPE_CHOICES,
        "valid_cards_start_index": get_valid_cards_start_index(),
        "valid_card_char_lengths": get_valid_card_char_lengths(),
        "config_port": PORT,
    }
pdf_generator = PDFReportGenerator(config_manager)

# External old configuration auto-fetch path (site-provided legacy file)
EXTERNAL_OLD_IOT_CONFIG_PATH = r"C:\Program Files\CSM Tech\eRawannaSetup\IotConfig\iot_configuration.json"

def _external_old_config_available() -> bool:
    try:
        return os.path.exists(EXTERNAL_OLD_IOT_CONFIG_PATH)
    except Exception:
        return False
server_service = ServerService()
rfid_service = RFIDService()
camera_service = CameraService()
display_service = DisplayService()
digitizer_service = DigitizerService(Digitizer_Convert)
from services.digitizer_api_service import digitizer_api_service
from services.handheld_rfid_service import handheld_rfid_service
io_controller_service = IOControllerService()
network_scanner = NetworkScanner()
audio_service = AudioService()
updater_service = UpdaterService(
    current_version=APP_VERSION,
    target_exe_name="configuration.exe",
    check_interval_seconds=UPDATE_CHECK_INTERVAL_SECONDS,
)
updater_service.start_background_checker()

def cleanup_all_connections():
    """Close all device connections before application exit"""
    logger.info("Closing all device connections...")
    try:
        # Close I/O Controller
        try:
            io_controller_service.disconnect()
            logger.info("I/O Controller disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting I/O Controller: {e}")
        
        # Stop RFID
        try:
            rfid_service.stop()
            logger.info("RFID connection stopped")
        except Exception as e:
            logger.error(f"Error stopping RFID: {e}")
        
        # Stop Digitizer
        try:
            digitizer_service.stop()
            logger.info("Digitizer connection stopped")
        except Exception as e:
            logger.error(f"Error stopping Digitizer: {e}")
        
        # Stop all Cameras
        try:
            camera_service.stop_all()
            logger.info("All cameras stopped")
        except Exception as e:
            logger.error(f"Error stopping cameras: {e}")
        
        # Disconnect Display
        try:
            display_service.disconnect()
            logger.info("Display disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting Display: {e}")
        
        logger.info("All connections closed successfully")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

IOT_CONFIGURATION_INSTANCE_KEY = "configuration"


def _handle_iot_instance_replacement_shutdown() -> None:
    """Graceful exit when a newer configuration.exe instance requests replacement."""
    logger.info("Prior-instance replacement: shutting down IoT-Configuration")
    try:
        cleanup_all_connections()
    except Exception as exc:
        logger.error("Instance guard cleanup error: %s", exc)
    try:
        import webview

        for window in webview.windows:
            window.destroy()
    except Exception:
        pass
    os._exit(0)


def _bootstrap_iot_instance_guard() -> None:
    """Replace prior configuration.exe and listen for external shutdown requests."""
    from utils.instance_guard import (
        acquire_runtime_mutex,
        register_shutdown_listener,
        replace_prior_instances,
        should_skip_instance_guard,
    )

    if should_skip_instance_guard():
        return

    logger_name = "iot_config.instance_guard"
    replace_prior_instances(IOT_CONFIGURATION_INSTANCE_KEY, logger_name=logger_name)
    register_shutdown_listener(
        IOT_CONFIGURATION_INSTANCE_KEY,
        _handle_iot_instance_replacement_shutdown,
        logger_name=logger_name,
    )
    acquire_runtime_mutex(IOT_CONFIGURATION_INSTANCE_KEY, logger_name=logger_name)


_POSIX_INSTANCE_LOCK_FH = None


def _acquire_posix_single_instance_lock() -> None:
    """
    macOS/Linux: keep a single iot-configuration process via flock.
    Prevents the Cocoa/argv-emulation re-entry loop from stacking copies on :8080.
    """
    global _POSIX_INSTANCE_LOCK_FH
    if sys.platform == "win32":
        return
    try:
        import fcntl
    except ImportError:
        return

    lock_path = os.path.join(app_data_path, ".iot-configuration.lock")
    try:
        fh = open(lock_path, "a+", encoding="utf-8")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        _POSIX_INSTANCE_LOCK_FH = fh  # keep alive for process lifetime
        logger.info("Single-instance lock acquired: %s", lock_path)
    except OSError:
        logger.error(
            "Another iot-configuration instance is already running (lock %s). Exiting.",
            lock_path,
        )
        try:
            fatal_exit(
                "IoT Configuration is already running.\n\n"
                "Close the existing window, or stop the other process, then try again.",
                title=APP_NAME,
                log_path=log_file,
            )
        except Exception:
            pass
        os._exit(1)

# ============== Main Routes ==============

@app.route('/')
def checklist_page():
    """Pre-Configuration Checklist Page"""
    return render_template(
        'checklist.html',
        debug=RUNTIME_DEBUG,
        require_device_info=RUNTIME_REQUIRE_DEVICE_INFO,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        enable_camera_configuration=ENABLE_CAMERA_CONFIGURATION,
        enable_wb_sensor_test_skip=ENABLE_WB_SENSOR_TEST_SKIP,
    )

@app.route('/discover')
def discover_page():
    """Network Discovery Page"""
    return render_template(
        'discover.html',
        debug=RUNTIME_DEBUG,
        require_device_info=RUNTIME_REQUIRE_DEVICE_INFO,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        enable_camera_configuration=ENABLE_CAMERA_CONFIGURATION,
        enable_wb_sensor_test_skip=ENABLE_WB_SENSOR_TEST_SKIP,
    )

@app.route('/devices')
def devices_page():
    """Device Configuration Page"""
    return render_template(
        'devices.html',
        debug=RUNTIME_DEBUG,
        require_device_info=RUNTIME_REQUIRE_DEVICE_INFO,
        app_name=APP_NAME,
        app_version=APP_VERSION,
        external_old_config_found=_external_old_config_available(),
        enable_camera_configuration=ENABLE_CAMERA_CONFIGURATION,
        enable_wb_sensor_test_skip=ENABLE_WB_SENSOR_TEST_SKIP,
    )

@app.route('/api/debug')
def get_debug():
    return jsonify({
        "debug": RUNTIME_DEBUG,
        "require_device_info": RUNTIME_REQUIRE_DEVICE_INFO,
        "enable_camera_configuration": ENABLE_CAMERA_CONFIGURATION,
        "enable_wb_sensor_test_skip": ENABLE_WB_SENSOR_TEST_SKIP,
        "app_name": APP_NAME,
        "app_version": APP_VERSION
    })


# ============== Update Routes ==============
@app.route('/api/update/status', methods=['GET'])
def update_status():
    return jsonify({"status": 200, "data": updater_service.get_status()})


@app.route('/api/update/progress', methods=['GET'])
def update_progress():
    return jsonify({"status": 200, "data": updater_service.get_progress()})


@app.route('/api/update/check', methods=['POST'])
def update_check():
    data = updater_service.check_for_updates(force=True)
    return jsonify({"status": 200, "data": data})


@app.route('/api/update/apply', methods=['POST'])
def update_apply():
    """
    Download latest release package, launch detached worker, then close app.
    Worker performs:
      - backup all install files to iot-update-backup/iot-app-YYYYMMDD-HHMMSS.zip
      - keep iot_configuration.json
      - replace with new files
      - relaunch configuration.exe
    """
    result = updater_service.launch_update_worker(parent_pid=os.getpid())
    if result.get("status") != 200:
        return jsonify(result), 500

    def close_after_update_start():
        try:
            cleanup_all_connections()
            time.sleep(0.5)
            try:
                from utils.webview_stderr import destroy_webview_window_quietly
                destroy_webview_window_quietly()
            except Exception:
                pass
        finally:
            os._exit(0)

    threading.Thread(target=close_after_update_start, daemon=False).start()
    return jsonify({"status": 200, "message": "Update started. Application will close now."})


@app.route('/api/debug/enable', methods=['POST'])
def enable_debug_mode():
    """
    Enable runtime DEBUG mode via admin password.
    This does NOT change config.py on disk – it only affects the current process.
    """
    try:
        data = request.get_json(silent=True) or {}
        password = data.get('password', '')

        if password != ADMIN_DEBUG_PASSWORD:
            logger.warning("Admin debug enable attempt failed: invalid password")
            return jsonify({
                "status": 401,
                "message": "Invalid admin password"
            }), 401

        global RUNTIME_DEBUG, RUNTIME_REQUIRE_DEVICE_INFO
        RUNTIME_DEBUG = True
        # In debug mode, device info is optional
        RUNTIME_REQUIRE_DEVICE_INFO = False

        logger.info("Admin debug mode ENABLED via /api/debug/enable")

        return jsonify({
            "status": 200,
            "message": "Debug mode enabled for this session",
            "debug": RUNTIME_DEBUG,
            "require_device_info": RUNTIME_REQUIRE_DEVICE_INFO
        })
    except Exception as e:
        logger.error(f"Error enabling debug mode: {e}", exc_info=True)
        return jsonify({
            "status": 500,
            "message": f"Failed to enable debug mode: {str(e)}"
        }), 500


@app.route('/api/admin/verify-api-endpoints-password', methods=['POST'])
def verify_api_endpoints_password():
    """Gate for Finish → Configure API-Endpoints editor."""
    try:
        data = request.get_json(silent=True) or {}
        password = data.get("password", "")
        if password != ADMIN_API_ENDPOINTS_PASSWORD:
            logger.warning("API-endpoints admin password rejected")
            return jsonify({
                "status": 401,
                "message": "Invalid admin password",
            }), 401
        return jsonify({
            "status": 200,
            "message": "Admin password accepted",
            "api_fields": config_manager.get_api_endpoint_fields(),
            "api_endpoints": config_manager.get_section("api_endpoints") or {},
        })
    except Exception as e:
        logger.error(f"Error verifying API-endpoints password: {e}", exc_info=True)
        return jsonify({
            "status": 500,
            "message": str(e),
        }), 500


@app.route('/api/config/api_endpoints', methods=['POST'])
def save_api_endpoints_config():
    """
    Save api_endpoints after admin password verification.
    Body: { password, ...endpoint fields }
    """
    try:
        data = request.get_json(silent=True) or {}
        password = data.pop("password", None)
        if password != ADMIN_API_ENDPOINTS_PASSWORD:
            return jsonify({
                "status": 401,
                "message": "Invalid admin password",
            }), 401

        # Merge onto existing so omitted keys are preserved
        current = dict(config_manager.get_section("api_endpoints") or {})
        for key, value in data.items():
            if value is None:
                continue
            current[key] = value

        success = config_manager.save_section("api_endpoints", current)
        if not success:
            return jsonify({
                "status": 500,
                "message": "Failed to save API endpoints",
            }), 500

        logger.info("API endpoints updated via finish-flow admin editor")
        return jsonify({
            "status": 200,
            "message": "API endpoints saved",
            "data": current,
        })
    except Exception as e:
        logger.error(f"Error saving api_endpoints: {e}", exc_info=True)
        return jsonify({"status": 500, "message": str(e)}), 500


@app.route('/api/debug/disable', methods=['POST'])
def disable_debug_mode():
    """
    Disable runtime DEBUG mode (no password required).
    Session-only - does not rewrite config.py.
    """
    try:
        global RUNTIME_DEBUG, RUNTIME_REQUIRE_DEVICE_INFO
        RUNTIME_DEBUG = False
        # Turning debug off always restores strict device-info validation,
        # even when config.py has DEBUG=True (REQUIRE_DEVICE_INFO would be False).
        RUNTIME_REQUIRE_DEVICE_INFO = True

        logger.info("Admin debug mode DISABLED via /api/debug/disable")

        return jsonify({
            "status": 200,
            "message": "Debug mode disabled for this session",
            "debug": RUNTIME_DEBUG,
            "require_device_info": RUNTIME_REQUIRE_DEVICE_INFO
        })
    except Exception as e:
        logger.error(f"Error disabling debug mode: {e}", exc_info=True)
        return jsonify({
            "status": 500,
            "message": f"Failed to disable debug mode: {str(e)}"
        }), 500

# ============== Configuration Routes ==============

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get configuration for the commissioning UI (excludes backend-only device_ip)."""
    return jsonify(config_manager.get_all_for_frontend())


@app.route('/api/config/wb-type', methods=['POST'])
def set_wb_type():
    """Persist weighbridge direction (unidirectional or bidirectional)."""
    data = request.json or {}
    wb_type = data.get('wb_type') or data.get('layout') or data.get('weighbridge_layout')
    if wb_type not in ('unidirectional', 'bidirectional'):
        return jsonify({
            'status': 400,
            'message': 'wb_type must be unidirectional or bidirectional',
        }), 400
    # Prefer checkpoint-type API when provided
    checkpoint_type = data.get('checkpoint_type') or config_manager.get_checkpoint_type()
    success, layout_changed = config_manager.set_checkpoint_type(checkpoint_type, wb_type)
    if success:
        payload = {
            'status': 200,
            'message': 'Weighbridge direction saved',
            'wb_type': wb_type,
            'checkpoint_type': checkpoint_type,
        }
        if layout_changed:
            payload['layout_changed'] = True
            payload['requires_reconfigure'] = ['rfid', 'io_controller']
            payload['message'] = (
                'Layout changed. Reconfigure RFID readers and '
                'traffic lights on the devices page.'
            )
        return jsonify(payload)
    return jsonify({'status': 500, 'message': 'Failed to save weighbridge type'}), 500


@app.route('/api/config/checkpoint-type', methods=['POST'])
def set_checkpoint_type():
    """Persist GMDC checkpoint profile + optional direction."""
    data = request.json or {}
    checkpoint_type = data.get('checkpoint_type') or data.get('type')
    direction = data.get('direction') or data.get('wb_type')
    if not checkpoint_type:
        return jsonify({'status': 400, 'message': 'checkpoint_type is required'}), 400
    success, layout_changed = config_manager.set_checkpoint_type(checkpoint_type, direction)
    if not success:
        return jsonify({
            'status': 400,
            'message': f'Unknown checkpoint_type: {checkpoint_type}',
        }), 400
    from services.profiles import profile_public_dict
    payload = {
        'status': 200,
        'message': 'Checkpoint type saved',
        'checkpoint_type': config_manager.get_checkpoint_type(),
        'wb_type': config_manager.get_wb_type(),
        'profile': profile_public_dict(config_manager.get_checkpoint_type()),
    }
    if layout_changed:
        payload['layout_changed'] = True
        payload['requires_reconfigure'] = ['rfid', 'io_controller', 'digitizer']
    return jsonify(payload)


@app.route('/api/profiles', methods=['GET'])
def list_profiles():
    """List all checkpoint profiles for the type picker."""
    from services.profiles import CHECKPOINT_TYPE_CHOICES, profile_public_dict
    return jsonify({
        'status': 200,
        'choices': CHECKPOINT_TYPE_CHOICES,
        'current': profile_public_dict(config_manager.get_checkpoint_type()),
        'wb_type': config_manager.get_wb_type(),
    })


@app.route('/api/config', methods=['POST'])
def save_all_config():
    """Save all configuration to JSON file"""
    data = request.json
    success = config_manager.save_all(data)
    if success:
        return jsonify({"status": 200, "message": "Configuration saved successfully"})
    return jsonify({"status": 500, "message": "Failed to save configuration"}), 500


@app.route('/api/config/reset-all', methods=['POST'])
def reset_all_config():
    """Reset entire iot_configuration to defaults (explicit Start fresh only)."""
    success = config_manager.reset_all()
    if success:
        return jsonify({
            "status": 200,
            "message": "All checkpoint configuration reset to defaults",
            "config": config_manager.get_all(),
        })
    return jsonify({"status": 500, "message": "Failed to reset configuration"}), 500


@app.route('/api/config/<section>/invalidate', methods=['POST'])
def invalidate_section_config(section):
    """Mark a section validated=false (and root status=false) after UI edits."""
    if section == 'device_ip':
        return jsonify({
            "status": 403,
            "message": "device_ip cannot be invalidated this way.",
        }), 403
    success = config_manager.invalidate_section(section)
    if success:
        return jsonify({
            "status": 200,
            "message": f"{section} marked as not validated",
            "completion": config_manager.get_completion_status(),
        })
    return jsonify({
        "status": 400,
        "message": f"Unknown or empty section: {section}",
    }), 400


@app.route('/api/config/<section>', methods=['POST'])
def save_section_config(section):
    """Save configuration for a specific section"""
    if section == 'device_ip':
        return jsonify({
            "status": 403,
            "message": "device_ip is set automatically when configuration is finished.",
        }), 403
    if section == 'camera' and not ENABLE_CAMERA_CONFIGURATION:
        return jsonify({
            "status": 400,
            "message": "Camera configuration is disabled (ENABLE_CAMERA_CONFIGURATION=False).",
        }), 400
    if section == 'api_endpoints':
        # Must use admin-gated /api/config/api_endpoints (password required)
        return jsonify({
            "status": 403,
            "message": "Use Finish Setup → Configure API Endpoints (admin password required).",
        }), 403
    data = request.json
    if section in ('rfid', 'rfids'):
        err = validate_rfid_section_save(section, data or {})
        if err:
            return jsonify({"status": 400, "message": err}), 400
    if section == 'digitizer':
        dig = data or {}
        mode = str(dig.get("mode") or "api").strip().lower()
        if mode == "mqtt":
            if not str(dig.get("broker_host") or dig.get("host") or "").strip():
                return jsonify({
                    "status": 400,
                    "message": "MQTT broker host is required (Mines-WB Mac IP)",
                }), 400
        elif mode == "api":
            if not str(dig.get("host") or dig.get("ip") or "").strip():
                return jsonify({
                    "status": 400,
                    "message": "Digitizer-app host is required",
                }), 400
        else:
            err = validate_digitizer_section_save(dig, digitizer_service, Digitizer_Convert)
            if err:
                return jsonify({"status": 400, "message": err}), 400
    if section == 'rfids' and config_manager.get_wb_type() == 'bidirectional':
        err = config_manager.validate_bidirectional_rfids(data or {})
        if err:
            return jsonify({"status": 400, "message": err}), 400
    if section == 'io_controller':
        err = config_manager.validate_io_pin_uniqueness(
            data or {}, config_manager.get_wb_type()
        )
        if err:
            return jsonify({"status": 400, "message": err}), 400
    success = config_manager.save_section(section, data)
    if success:
        # Ensure validation flag is updated for sections that are saved from UI
        # For I/O controller specifically, some older UIs may not send 'validated' in payload,
        # so explicitly mark the section as validated after a successful save.
        if section == 'io_controller':
            config_manager.set_validated('io_controller', True)
        return jsonify({"status": 200, "message": f"{section} configuration saved"})
    return jsonify({"status": 500, "message": f"Failed to save {section} configuration"}), 500

@app.route('/api/config/<section>/reset', methods=['POST'])
def reset_section_config(section):
    """Reset configuration for a specific section"""
    if section == 'camera' and not ENABLE_CAMERA_CONFIGURATION:
        return jsonify({
            "status": 400,
            "message": "Camera configuration is disabled (ENABLE_CAMERA_CONFIGURATION=False).",
        }), 400
    success = config_manager.reset_section(section)
    if success:
        return jsonify({"status": 200, "message": f"{section} configuration reset", "data": config_manager.get_section(section)})
    return jsonify({"status": 500, "message": f"Failed to reset {section} configuration"}), 500


# ============== Import Previous Configuration ==============

@app.route('/api/import-config', methods=['POST'])
def import_configuration():
    """
    Upload an older iot_configuration.json and import it into the current schema.
    After import:
      - RFID, Display, Digitizer, Audio(voice) are forced to validated=false
      - All other sections are marked validated=true
      - Root `status` is set to false (so weighbridge won't start until revalidated)
    """
    try:
        uploaded_file = request.files.get("configFile") or request.files.get("file")
        if not uploaded_file:
            return jsonify({"status": 400, "message": "No JSON file uploaded"}), 400

        raw = uploaded_file.read()
        # Handle UTF-8 BOM files too
        text = raw.decode("utf-8-sig")
        data = json.loads(text)
        if not isinstance(data, dict):
            return jsonify({"status": 400, "message": "Uploaded JSON must be an object"}), 400

        ok = config_manager.import_configuration_for_upgrade(data)
        if not ok:
            return jsonify({"status": 500, "message": "Failed to import configuration"}), 500

        return jsonify({
            "status": 200,
            "message": "Configuration imported. RFID/Display/Digitizer/Audio set for re-validation.",
            "config": config_manager.get_all(),
            "completion": config_manager.get_completion_status(),
        })
    except json.JSONDecodeError:
        return jsonify({"status": 400, "message": "Invalid JSON file"}), 400
    except Exception as e:
        logger.error(f"Import configuration error: {e}", exc_info=True)
        return jsonify({"status": 500, "message": f"Import failed: {str(e)}"}), 500


# ============== Auto Import Previous Configuration (Server-side) ==============
@app.route('/api/auto-import-config', methods=['POST'])
def auto_import_configuration():
    """
    Auto-import from the legacy config file path present on the installation PC.
    Used when user answers "Yes" on the /devices auto-fetch prompt.
    """
    try:
        if not os.path.exists(EXTERNAL_OLD_IOT_CONFIG_PATH):
            return jsonify({"status": 404, "message": "External legacy config not found"}), 404

        with open(EXTERNAL_OLD_IOT_CONFIG_PATH, "rb") as f:
            raw = f.read()

        text = raw.decode("utf-8-sig")
        data = json.loads(text)
        if not isinstance(data, dict):
            return jsonify({"status": 400, "message": "Legacy config JSON must be an object"}), 400

        ok = config_manager.import_configuration_for_upgrade(data)
        if not ok:
            return jsonify({"status": 500, "message": "Failed to import legacy configuration"}), 500

        return jsonify({
            "status": 200,
            "message": "Legacy configuration imported successfully",
            "completion": config_manager.get_completion_status()
        })
    except json.JSONDecodeError:
        return jsonify({"status": 400, "message": "Legacy config is not valid JSON"}), 400
    except Exception as e:
        logger.error(f"Auto import legacy config error: {e}", exc_info=True)
        return jsonify({"status": 500, "message": f"Auto import failed: {str(e)}"}), 500


# ============== Audio Test Route ==============

@app.route('/api/audio/test', methods=['POST'])
def test_audio():
    """
    Test system audio playback using the local PC audio system.

    Uses AudioService (winsound on Windows, afplay on macOS, aplay on Linux)
    to play the configured test file.
    If audio cannot be played due to missing driver/device, returns 500 so
    the frontend can show a clear error message.
    """
    try:
        result = audio_service.play_test_audio()
        status_code = 200 if result.get("success") else 500
        return jsonify(result), status_code
    except Exception as e:
        logger.error(f"[Audio Test] Unexpected error: {e}")
        return jsonify({
            "success": False,
            "reason": "UNEXPECTED_ERROR",
            "message": f"Unexpected error during audio test: {str(e)}"
        }), 500

# ============== Server Configuration Routes ==============

@app.route('/api/server/check', methods=['POST'])
def check_server():
    """Check server connectivity"""
    data = request.json
    ip = data.get('ip', '')
    port = data.get('port', '')
    result = server_service.check_connection(ip, port)
    return jsonify(result)

# ============== RFID Configuration Routes ==============

@app.route('/api/rfid/check', methods=['POST'])
def check_rfid():
    """Check RFID connectivity and auto-detect mode"""
    data = request.json
    ip = data.get('ip', '')
    port = data.get('port', 6000)
    mode = (data.get('mode', '') or '').upper()
    username = data.get('username') or data.get('user') or 'admin'
    password = data.get('password') if data.get('password') is not None else ''
    
    # POST to /api/rfid/check should ALWAYS start a new test
    # This endpoint is called when user clicks "Check & Save" button
    # Status polling should use /api/rfid/status endpoint instead
    
    # Reset test status and start fresh
    logger.info(f"[RFID API] Starting new check (IP/port: {ip}:{port}, mode={mode or 'auto'}). Resetting test status...")
    rfid_service.reset_test_status()
    rfid_service._last_check_ip = ip
    rfid_service._last_check_port = port
    
    # API mode does not need a TCP port; default safely for legacy modes
    try:
        port_int = int(port) if port not in (None, '') else 443
    except (TypeError, ValueError):
        port_int = 443

    result = rfid_service.check_connection(
        ip,
        port_int,
        mode or None,
        username=username,
        password=password,
    )
    
    # Update last check tracking after successful connection
    if result.get("status") == 200:
        rfid_service._last_check_ip = ip
        rfid_service._last_check_port = port
    
    # If connection successful (both CLIENT and SERVER modes), return appropriate status
    if result.get("status") == 200:
        test_status = rfid_service.get_test_status()
        
        # Always include test status in response
        result["testing"] = test_status.get("testing", False)
        result["test_complete"] = test_status.get("test_complete", False)
        result["time_remaining"] = test_status.get("time_remaining", 0)
        
        if result.get("mode") == "CLIENT":
            if result.get("testing") or not test_status.get("test_complete"):
                # Test is running in background - return "waiting" status
                result["message"] = "Reader Connected. Waiting for RFID card read (30 seconds)..."
                # Don't include card_read status yet - test is still running
            elif test_status.get("test_complete"):
                # Test completed - check final result
                result["card_read"] = test_status.get("card_read", False)
                result["card_data"] = test_status.get("card_data")
                # Use message from test_status if available, otherwise use defaults
                if test_status.get("message"):
                    result["message"] = test_status.get("message")
                elif test_status.get("card_read"):
                    result["message"] = "Reader Connected and Valid RFID received"
                else:
                    result["warning"] = True
                    result["message"] = "Reader Connected, but no card read"
        elif result.get("mode") == "SERVER":
            if result.get("testing") or not test_status.get("test_complete"):
                # Test is running in background - return "waiting" status
                result["message"] = "RFID server started. Waiting for RFID to connect and read card (30 seconds)..."
                # Don't include card_read status yet - test is still running
            elif test_status.get("test_complete"):
                # Test completed - check final result
                result["card_read"] = test_status.get("card_read", False)
                result["card_data"] = test_status.get("card_data")
                # Use message from test_status if available, otherwise use defaults
                if test_status.get("message"):
                    result["message"] = test_status.get("message")
                elif test_status.get("card_read"):
                    result["message"] = "Reader Connected and Valid RFID received"
                else:
                    result["warning"] = True
                    result["message"] = "Reader Connected, but no card read"
        elif result.get("mode") == "API":
            if not result.get("push_url") and test_status.get("push_url"):
                result["push_url"] = test_status.get("push_url")
            if result.get("testing") or not test_status.get("test_complete"):
                result["message"] = "Reader connected. Waiting for RFID data (30 seconds)..."
            elif test_status.get("test_complete"):
                result["card_read"] = test_status.get("card_read", False)
                result["card_data"] = test_status.get("card_data")
                result["parsed_tag"] = test_status.get("parsed_tag")
                if test_status.get("message"):
                    result["message"] = test_status.get("message")
                elif test_status.get("card_read"):
                    result["message"] = "RFID data received"
                else:
                    result["warning"] = True
                    result["message"] = "No RFID data received. Please try again."
    
    return jsonify(result)

@app.route('/api/rfid/status', methods=['GET'])
def get_rfid_test_status():
    """Get RFID card read test status"""
    status = rfid_service.get_test_status()
    return jsonify(status)

@app.route('/api/rfid/stop', methods=['POST'])
def stop_rfid():
    """Stop RFID connection"""
    result = rfid_service.stop()
    return jsonify(result)


@app.route('/rfid_data', methods=['POST'])
def rfid_data_intake():
    """
    Zebra reader push endpoint (same contract as Mine-entry / TareWb-App).
    Used during RFID Configuration Check & Save (API mode) 30s wait.
    """
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    if payload is None:
        return jsonify({"status": "error", "message": "Empty body"}), 400
    logger.info(
        "[RFID] POST /rfid_data from %s (bytes=%s)",
        request.remote_addr,
        request.content_length,
    )
    http_status, body = rfid_service.accept_api_payload(payload)
    return jsonify(body), http_status


@app.route('/rfid_management', methods=['POST'])
def rfid_management_intake():
    """Zebra keepalive / management - acknowledge during commissioning."""
    return jsonify({"status": "success"}), 200


@app.route('/api/rfid/fastag-validation-rules', methods=['GET'])
def rfid_fastag_validation_rules():
    """Return FASTag prefix and length rules from editable timeout_config.py."""
    return jsonify({
        "status": 200,
        "valid_cards_start_index": get_valid_cards_start_index(),
        "char_length": get_valid_card_char_lengths(),
    })

# ============== Camera Configuration Routes ==============

@app.route('/api/camera/check', methods=['POST'])
def check_camera():
    """Check camera connectivity"""
    if not ENABLE_CAMERA_CONFIGURATION:
        return jsonify({
            "status": 400,
            "message": "Camera configuration is disabled (ENABLE_CAMERA_CONFIGURATION=False).",
        }), 400
    data = request.json
    camera_id = data.get('camera_id', 'top')
    rtsp_url = data.get('rtsp_url', '')
    result = camera_service.check_connection(camera_id, rtsp_url)
    return jsonify(result)

@app.route('/video_feed/<camera_id>')
def video_feed(camera_id):
    """Video streaming route"""
    if not ENABLE_CAMERA_CONFIGURATION:
        return jsonify({
            "status": 400,
            "message": "Camera configuration is disabled (ENABLE_CAMERA_CONFIGURATION=False).",
        }), 400
    return Response(
        camera_service.generate_frames(camera_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/api/camera/stop/<camera_id>', methods=['POST'])
def stop_camera(camera_id):
    """Stop camera stream"""
    if not ENABLE_CAMERA_CONFIGURATION:
        return jsonify({
            "status": 400,
            "message": "Camera configuration is disabled (ENABLE_CAMERA_CONFIGURATION=False).",
        }), 400
    result = camera_service.stop_camera(camera_id)
    return jsonify(result)

# ============== Display Configuration Routes ==============

@app.route('/api/display/check', methods=['POST'])
def check_display():
    """Check display connectivity"""
    data = request.json
    display_type = data.get('type', 'api')
    display_ip = data.get('ip', '')
    display_port = data.get('port', '80')
    result = display_service.check_connection(display_type, display_ip, display_port)
    return jsonify(result)

# ============== Digitizer Configuration Routes ==============

@app.route('/api/digitizer/check', methods=['POST'])
def check_digitizer():
    """Check digitizer connectivity (API HTTP or MQTT status/weight)."""
    data = request.json or {}
    mode = str(data.get('mode') or 'api').strip().lower()
    if mode in ('api', 'mqtt') or data.get('host') or data.get('ip') or data.get('broker_host'):
        if mode not in ('api', 'mqtt'):
            data = dict(data)
            data['mode'] = 'api'
        result = digitizer_api_service.check_connection(data)
        return jsonify(result)
    # Legacy serial fallback (kept for brownfield labs)
    port = data.get('port', '')
    baud_rate = data.get('baud_rate', 9600)
    bytesize = int(data.get('bytesize', 8))
    parity = data.get('parity', 'N')
    stopbits = float(data.get('stopbits', 1))
    result = digitizer_service.check_connection(port, int(baud_rate), bytesize, parity, stopbits)
    return jsonify(result)


@app.route('/api/handheld-rfid/check', methods=['POST'])
def check_handheld_rfid():
    """
    Start handheld RFID live test: wait for POST /rfid_data_from_mobile_app
    with body {"rfid_data": "<non-blank>"}.
    """
    data = request.json or {}
    wait_seconds = data.get('wait_seconds', 60)
    handheld_rfid_service.stop()
    result = handheld_rfid_service.start_wait(data, wait_seconds=wait_seconds)
    return jsonify(result)


@app.route('/api/handheld-rfid/status', methods=['GET'])
def handheld_rfid_status():
    """Poll handheld RFID wait / receive status."""
    return jsonify({"status": 200, **handheld_rfid_service.get_status()})


@app.route('/api/handheld-rfid/stop', methods=['POST'])
def stop_handheld_rfid():
    """Cancel an in-progress handheld RFID wait."""
    handheld_rfid_service.stop()
    return jsonify({"status": 200, "message": "Handheld RFID wait stopped", **handheld_rfid_service.get_status()})


@app.route('/rfid_data_from_mobile_app', methods=['POST'])
def rfid_data_from_mobile_app():
    """
    Same path as Mine-entry: handheld posts {"rfid_data": "<tag>"}.
    During config Check & Save, a non-blank tag completes the handheld test.
    """
    payload = request.get_json(silent=True)
    result = handheld_rfid_service.receive_rfid_payload(payload)
    return jsonify(result["body"]), result["http_status"]


@app.route('/api/digitizer/ports', methods=['GET'])
def get_serial_ports():
    """Get available serial ports (legacy; not used for API digitizer)."""
    ports = digitizer_service.get_available_ports()
    return jsonify({"ports": ports})

@app.route('/api/digitizer/sample', methods=['POST'])
def digitizer_capture_sample():
    """Capture a fixed byte sample from the digitizer for index-picker setup."""
    from digitizer_index_engine import ROW_LABELS, build_ruler_payload, WIZARD_CAPTURE_BYTES

    data = request.json or {}
    port = data.get('port', '')
    baud_rate = data.get('baud_rate', 9600)
    bytesize = int(data.get('bytesize', 8))
    parity = data.get('parity', 'N')
    stopbits = float(data.get('stopbits', 1))
    timeout = float(data.get('timeout', 10))
    nbytes = int(data.get('nbytes', WIZARD_CAPTURE_BYTES))

    result = digitizer_service.capture_sample(
        port,
        int(baud_rate),
        bytesize,
        parity,
        stopbits,
        timeout=timeout,
        nbytes=nbytes,
    )
    if result.get('status') != 200:
        return jsonify(result)

    try:
        sample = bytes.fromhex(result['sample_hex'])
    except ValueError:
        return jsonify({
            "status": 500,
            "message": "Internal error: invalid sample buffer",
        })

    result['ruler'] = build_ruler_payload(sample)
    result['row_labels'] = ROW_LABELS
    return jsonify(result)


@app.route('/api/digitizer/index-preview', methods=['POST'])
def digitizer_index_preview():
    """Validate index picks and preview extracted weight for the captured sample."""
    from digitizer_index_engine import (
        ROW_LABELS,
        build_indexing_from_picks,
        build_ruler_payload,
        extract_weight,
        highlight_bands,
        index_config_from_dict,
        validate_indexing_for_calibration,
        validate_pick_indices,
    )

    data = request.json or {}
    sample_hex = data.get('sample_hex', '')
    picks = data.get('picks', [])

    if not sample_hex:
        return jsonify({"status": 400, "message": "sample_hex is required"})

    try:
        sample = bytes.fromhex(sample_hex)
    except ValueError:
        return jsonify({"status": 400, "message": "Invalid sample_hex"})

    if len(picks) != 6:
        return jsonify({"status": 400, "message": "Expected exactly 6 picker rows"})

    normalized_picks = []
    for pick in picks:
        if pick is None or pick == '':
            normalized_picks.append(None)
        else:
            try:
                normalized_picks.append(int(pick))
            except (TypeError, ValueError):
                return jsonify({"status": 400, "message": f"Invalid index value: {pick}"})

    validation_error = validate_pick_indices(normalized_picks, len(sample))
    if validation_error:
        return jsonify({
            "status": 200,
            "message": "Validation failed",
            "validation_error": validation_error,
            "weight": None,
            "indexing": None,
            "highlights": highlight_bands(normalized_picks),
            "ruler": build_ruler_payload(sample),
            "row_labels": ROW_LABELS,
        })

    indexing = build_indexing_from_picks(normalized_picks, sample)
    indexing_err = validate_indexing_for_calibration(indexing)
    if indexing_err:
        return jsonify({
            "status": 200,
            "message": "Validation failed",
            "validation_error": indexing_err,
            "weight": None,
            "indexing": None,
            "highlights": highlight_bands(normalized_picks),
            "ruler": build_ruler_payload(sample),
            "row_labels": ROW_LABELS,
        })

    cfg = index_config_from_dict(indexing)
    weight = extract_weight(sample, cfg) if cfg else None
    min_weight_kg = get_digitizer_calibration_min_weight_kg()
    meets_calibration_min = weight is not None and float(weight) >= min_weight_kg

    if weight is not None and not meets_calibration_min:
        return jsonify({
            "status": 400,
            "message": (
                f"Place at least {min_weight_kg} kg on the weighbridge for digitizer calibration. "
                f"Parsed weight was {float(weight):g} kg."
            ),
            "validation_error": None,
            "weight": weight,
            "indexing": indexing,
            "min_weight_kg": min_weight_kg,
            "meets_calibration_min": False,
            "highlights": highlight_bands(normalized_picks),
            "ruler": build_ruler_payload(sample),
            "row_labels": ROW_LABELS,
        })

    return jsonify({
        "status": 200,
        "message": "Preview generated",
        "validation_error": None,
        "weight": weight,
        "indexing": indexing,
        "min_weight_kg": min_weight_kg,
        "meets_calibration_min": meets_calibration_min,
        "highlights": highlight_bands(normalized_picks),
        "ruler": build_ruler_payload(sample),
        "row_labels": ROW_LABELS,
    })


@app.route('/api/digitizer/index-picks-from-indexing', methods=['POST'])
def digitizer_picks_from_indexing():
    """Restore 6-row picker indices from a saved indexing block and sample."""
    from digitizer_index_engine import picks_from_indexing

    data = request.json or {}
    sample_hex = data.get('sample_hex', '')
    indexing = data.get('indexing') or {}

    if not sample_hex:
        return jsonify({"status": 400, "message": "sample_hex is required"})
    if not indexing:
        return jsonify({"status": 400, "message": "indexing is required"})

    try:
        sample = bytes.fromhex(sample_hex)
    except ValueError:
        return jsonify({"status": 400, "message": "Invalid sample_hex"})

    picks = picks_from_indexing(sample, indexing)
    return jsonify({
        "status": 200,
        "message": "Picks restored from saved indexing",
        "picks": picks,
    })


@app.route('/api/digitizer/calibration-rules', methods=['GET'])
def digitizer_calibration_rules():
    """Return digitizer calibration thresholds from editable timeout_config.py."""
    return jsonify({
        "status": 200,
        "min_weight_kg": get_digitizer_calibration_min_weight_kg(),
    })

@app.route('/api/digitizer/conversion-preview', methods=['GET'])
def digitizer_conversion_preview():
    """
    Preview digitizer conversion methods for the latest raw sample.
    
    Used by the configuration UI to show possible weights for each
    supported conversion method so the user can select the correct one.
    """
    raw = digitizer_service.get_latest_raw_sample()
    if not raw:
        return jsonify({
            "status": 400,
            "message": "No raw digitizer data available. Please ensure the digitizer is sending data.",
            "candidates": []
        })
    
    converter = Digitizer_Convert()
    try:
        try:
            text = raw.decode('ascii', errors='ignore')
        except Exception:
            text = ""
        # Rolling-buffer methods (e.g. p_at_pct) need the same chunk the app would append in convert()
        if text and hasattr(converter, "_pat_pct_buffer"):
            converter._pat_pct_buffer = text[-500:]
        
        # Load method order from conversion.py so future site-specific changes
        # can be done by replacing conversion.py only (no EXE rebuild needed).
        if hasattr(Digitizer_Convert, 'get_preview_method_order'):
            method_order = Digitizer_Convert.get_preview_method_order()
        else:
            # Backward-compatible fallback for older conversion.py files.
            method_order = [
                ("bracket", "Method 1 - Bracket [000000] format"),
                ("kg", "Method 2 - Number + 'kg' format"),
                ("ga", "Method 3 - G ... A garbled format"),
                ("wt", "Method 4 - 'Wt:' buffered format"),
                ("st_gs", "Method 5 - ST,GS,+0000000kg format"),
                ("prefix", "Method 6 - Number prefix format"),
                ("plain_ascii", "Method 7 - Plain ASCII digits"),
            ]
        
        candidates = []
        min_weight_kg = get_digitizer_calibration_min_weight_kg()
        for method_id, label in method_order:
            weight = converter._convert_by_method(method_id, raw, text)
            if weight is not None:
                try:
                    weight_val = float(weight)
                except (TypeError, ValueError):
                    continue
                candidates.append({
                    "id": method_id,
                    "label": label,
                    "weight": weight_val,
                    "meets_calibration_min": weight_val >= min_weight_kg,
                })

        qualifying = [c for c in candidates if c.get("meets_calibration_min")]
        if not qualifying:
            max_seen = max((c["weight"] for c in candidates), default=0)
            return jsonify({
                "status": 400,
                "message": (
                    f"Place at least {min_weight_kg} kg on the weighbridge for digitizer calibration. "
                    f"Highest parsed weight in the sample was {max_seen:g} kg."
                ),
                "candidates": candidates,
                "min_weight_kg": min_weight_kg,
            })

        return jsonify({
            "status": 200,
            "message": "Preview generated",
            "candidates": candidates,
            "min_weight_kg": min_weight_kg,
        })
    except Exception as e:
        logger.error(f"Error generating digitizer conversion preview: {e}", exc_info=True)
        return jsonify({
            "status": 500,
            "message": f"Error generating preview: {e}",
            "candidates": []
        })

@app.route('/api/digitizer/stop', methods=['POST'])
def stop_digitizer():
    """Stop digitizer connection"""
    result = digitizer_service.stop()
    return jsonify(result)

# ============== I/O Controller Configuration Routes ==============

@app.route('/api/io/check', methods=['POST'])
def check_io_controller():
    """Check I/O controller connectivity"""
    data = request.json
    result = io_controller_service.check_connection(data)
    return jsonify(result)

@app.route('/api/io/test', methods=['POST'])
def test_io_pin():
    """Test a specific I/O pin"""
    data = request.json
    result = io_controller_service.test_pin(data)
    return jsonify(result)

@app.route('/api/io/test-traffic-light', methods=['POST'])
def test_traffic_light():
    """Test traffic light with mode awareness (direct/relay)"""
    data = request.json
    result = io_controller_service.test_traffic_light(data)
    return jsonify(result)

@app.route('/api/io/test-boom-barrier', methods=['POST'])
def test_boom_barrier():
    """Test boom barrier with mode awareness (direct/relay)"""
    data = request.json
    result = io_controller_service.test_boom_barrier(data)
    return jsonify(result)

@app.route('/api/io/test-sensor', methods=['POST'])
def test_sensor():
    """Test sensor reading"""
    data = request.json
    result = io_controller_service.test_sensor(data)
    return jsonify(result)

@app.route('/api/io/disconnect', methods=['POST'])
def disconnect_io():
    """Disconnect from I/O controller"""
    result = io_controller_service.disconnect()
    return jsonify(result)

# ============== Network Scanner Routes ==============

@app.route('/api/network/ip-range', methods=['GET'])
def get_suggested_ip_range():
    """Get suggested IP range based on local machine IP"""
    result = network_scanner.get_suggested_ip_range()
    return jsonify(result)

@app.route('/api/network/scan', methods=['POST'])
def start_network_scan():
    """Start network scan"""
    data = request.json
    start_ip = data.get('start_ip', '')
    end_ip = data.get('end_ip', '')
    
    if not start_ip or not end_ip:
        return jsonify({"status": 400, "message": "Start and End IP are required"}), 400
    
    # Save IP range to config for later use
    config_manager.save_section('ip_range', {'start_ip': start_ip, 'end_ip': end_ip})
    
    # Scan COM ports first
    network_scanner.scan_com_ports()
    
    # Scan network
    import threading
    def run_scan():
        network_scanner.scan_network(start_ip, end_ip)
    
    thread = threading.Thread(target=run_scan)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": 200,
        "message": "Scan started",
        "total_ips": len(network_scanner.parse_ip_range(start_ip, end_ip))
    })

@app.route('/api/network/status', methods=['GET'])
def get_scan_status():
    """Get network scan status"""
    return jsonify(network_scanner.get_status())

@app.route('/api/network/results', methods=['GET'])
def get_scan_results():
    """Get network scan results"""
    results = network_scanner.get_results()
    return jsonify({
        "status": network_scanner.get_status(),
        "network_devices": results["network_devices"],
        "com_ports": results["com_ports"],
        "candidates": {
            "rfid": network_scanner.get_rfid_candidates(),
            "cameras": network_scanner.get_camera_candidates(),
            "modbus": network_scanner.get_modbus_candidates(),
            "servers": network_scanner.get_server_candidates(),
            "all_ips": network_scanner.get_all_ips()
        }
    })

@app.route('/api/network/com-ports', methods=['GET'])
def get_com_ports():
    """Get available COM ports"""
    ports = network_scanner.scan_com_ports()
    return jsonify({"ports": ports})

# ============== Completion Status Routes ==============

@app.route('/api/status', methods=['GET'])
def get_completion_status():
    """Get completion status of all sections"""
    return jsonify(config_manager.get_completion_status())

@app.route('/api/config/setup_info', methods=['POST'])
def save_setup_info():
    """Save weighbridge setup information"""
    data = request.get_json()
    config_manager.save_section('setup_info', data)
    return jsonify({"status": 200, "message": "Setup info saved"})

def _sync_setup_info_from_wb_info():
    """
    Sync setup_info fields in iot_configuration.json from wb_info.json.
    Mapping:
      wb_info.Data.wb_id   -> setup_info.weighbridge_details
      wb_info.Data.wb_name -> setup_info.weighbridge_location
    """
    try:
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = app_data_path

        wb_info_path = os.path.join(base_path, "wb_info.json")
        if not os.path.exists(wb_info_path):
            logger.warning("wb_info.json not found for setup_info sync: %s", wb_info_path)
            return

        try:
            with open(wb_info_path, "r", encoding="utf-8") as f:
                wb_info = json.load(f)
        except Exception:
            with open(wb_info_path, "r", encoding="utf-8-sig") as f:
                wb_info = json.load(f)

        data = wb_info.get("Data", wb_info)
        wb_id = (data.get("wb_id") or "").strip()
        wb_name = (data.get("wb_name") or "").strip()

        payload = {}
        if wb_id:
            payload["weighbridge_details"] = wb_id
        if wb_name:
            payload["weighbridge_location"] = wb_name

        if payload:
            config_manager.save_section("setup_info", payload)
            logger.info("Synced setup_info from wb_info.json: %s", payload)
    except Exception as e:
        logger.error("Failed to sync setup_info from wb_info.json: %s", e, exc_info=True)

@app.route('/api/finish', methods=['POST'])
def finish_configuration():
    """Finalize and export configuration"""
    _sync_setup_info_from_wb_info()
    result = config_manager.finalize()
    return jsonify(result)

@app.route('/api/generate-pdf-report', methods=['GET', 'POST'])
def generate_pdf_report():
    """Generate PDF report with all configuration details"""
    try:
        logger.info("Starting PDF report generation...")
        _sync_setup_info_from_wb_info()
        
        # Generate PDF and get buffer with filename
        pdf_buffer, pdf_filename = pdf_generator.generate_report()
        logger.info(f"PDF buffer generated, filename: {pdf_filename}")
        logger.info(f"PDF buffer type: {type(pdf_buffer)}")
        
        # Get PDF data from buffer
        # Make sure buffer is at position 0
        if hasattr(pdf_buffer, 'seek'):
            pdf_buffer.seek(0)
        pdf_data = pdf_buffer.getvalue()
        logger.info(f"PDF data size: {len(pdf_data)} bytes")
        
        if len(pdf_data) == 0:
            logger.error("PDF buffer is empty after getvalue()!")
        
        if len(pdf_data) == 0:
            logger.error("PDF buffer is empty!")
            return jsonify({
                "status": 500,
                "message": "PDF generation failed: empty buffer"
            }), 500
        
        # Also save PDF to disk
        if getattr(sys, 'frozen', False):
            # Running as executable - save in executable directory
            output_dir = os.path.dirname(sys.executable)
        else:
            # Running as script - save in project directory
            output_dir = app_data_path
        
        logger.info(f"Output directory: {output_dir}")
        
        # Create reports subdirectory if it doesn't exist
        reports_dir = os.path.join(output_dir, 'reports')
        try:
            os.makedirs(reports_dir, exist_ok=True)
            logger.info(f"Reports directory: {reports_dir}")
        except Exception as e:
            logger.error(f"Failed to create reports directory: {e}")
            raise
        
        # Save PDF to disk
        pdf_path = os.path.join(reports_dir, pdf_filename)
        try:
            with open(pdf_path, 'wb') as f:
                f.write(pdf_data)
            logger.info(f"PDF report generated and saved to: {pdf_path}")
            
            # Verify file was created
            if os.path.exists(pdf_path):
                file_size = os.path.getsize(pdf_path)
                logger.info(f"PDF file verified: {pdf_path} ({file_size} bytes)")
            else:
                logger.error(f"PDF file was not created at: {pdf_path}")
        except Exception as e:
            logger.error(f"Failed to save PDF to disk: {e}", exc_info=True)
            # Continue anyway - still return the PDF as download
        
        # Return PDF data as JSON with base64 encoding for webview API
        # This allows the JavaScript to use pywebview's file save dialog
        import base64
        pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
        
        return jsonify({
            "status": 200,
            "filename": pdf_filename,
            "data": pdf_base64,
            "mime_type": "application/pdf"
        })
    except Exception as e:
        logger.error(f"Error generating PDF report: {e}", exc_info=True)
        return jsonify({
            "status": 500,
            "message": f"Failed to generate PDF report: {str(e)}"
        }), 500

@app.route('/api/ui/exit_fullscreen', methods=['POST'])
def api_exit_fullscreen():
    """Leave borderless fullscreen and restore title bar (minimize/close)."""
    try:
        from utils.browser_launcher import exit_ui_fullscreen
        ok = exit_ui_fullscreen()
        return jsonify({"status": 200 if ok else 404, "ok": ok})
    except Exception as e:
        logger.warning("exit_fullscreen API failed: %s", e)
        return jsonify({"status": 500, "ok": False, "message": str(e)}), 500


@app.route('/api/ui/enter_fullscreen', methods=['POST'])
def api_enter_fullscreen():
    """Force UI window into borderless fullscreen."""
    try:
        from utils.browser_launcher import enter_ui_fullscreen
        ok = enter_ui_fullscreen()
        return jsonify({"status": 200 if ok else 404, "ok": ok})
    except Exception as e:
        logger.warning("enter_fullscreen API failed: %s", e)
        return jsonify({"status": 500, "ok": False, "message": str(e)}), 500


@app.route('/api/ui/minimize', methods=['POST'])
def api_minimize_ui():
    """Minimize the UI window (restores frame first if needed)."""
    try:
        from utils.browser_launcher import minimize_ui_window
        ok = minimize_ui_window()
        return jsonify({"status": 200 if ok else 404, "ok": ok})
    except Exception as e:
        logger.warning("minimize API failed: %s", e)
        return jsonify({"status": 500, "ok": False, "message": str(e)}), 500


@app.route('/api/close', methods=['POST'])
def close_application():
    """Close the application window and cleanup all connections"""
    import os
    import threading
    
    # Set status to True before closing (finish setup completed, report generated, application closing)
    try:
        config_manager.set_status(True)
        logger.info("Configuration status set to True - setup completed successfully")
    except Exception as e:
        logger.error(f"Failed to set configuration status: {e}")
    
    # Close the application after cleanup and a short delay to allow response to be sent
    def close_app():
        # Cleanup all device connections first
        cleanup_all_connections()
        
        time.sleep(0.3)  # Small delay to ensure cleanup completes and response is sent
        
        # Close frontend UI (Chrome app window / browser tab)
        try:
            from utils.browser_launcher import (
                close_ui_windows_by_title,
                terminate_chrome_process,
            )
            close_ui_windows_by_title()
            terminate_chrome_process()
            # Second pass in case Chrome recreates/reparents the window briefly
            time.sleep(0.4)
            close_ui_windows_by_title()
        except Exception as e:
            logger.warning("Frontend close failed: %s", e)

        try:
            from utils.webview_stderr import destroy_webview_window_quietly
            destroy_webview_window_quietly()
        except Exception:
            pass

        # Always exit process (Chrome app mode has no webview to close)
        os._exit(0)
    
    # Close in a separate thread to not block the response
    threading.Thread(target=close_app, daemon=False).start()
    
    return jsonify({"status": 200, "message": "Application closing"})

if __name__ == '__main__':
    try:
        # Required for frozen apps on macOS if any library touches multiprocessing.
        try:
            import multiprocessing as _mp

            _mp.freeze_support()
        except Exception:
            pass

        _bootstrap_iot_instance_guard()
        _acquire_posix_single_instance_lock()

        logger.info(f"Device Info Required: {REQUIRE_DEVICE_INFO}")
        logger.info(f"\n{'='*50}")
        logger.info(f"  {APP_NAME} v{APP_VERSION}")
        logger.info(f"  Mode: {'DEBUG' if DEBUG else 'PRODUCTION'}")
        logger.info(f"  Device Info Required: {REQUIRE_DEVICE_INFO}")
        logger.info(f"  Log file: {log_file}")
        logger.info(f"{'='*50}\n")
        
        from utils.browser_launcher import build_local_app_url, run_ui_with_auto_fallback, run_webview_start
        from utils.webview_stderr import install_webview_stderr_filter

        install_webview_stderr_filter()

        def start_flask():
            # Never enable Werkzeug debugger in a frozen binary: on macOS it
            # pulls multiprocessing/mmap and can collide with pywebview.
            flask_debug = bool(RUNTIME_DEBUG) and not getattr(sys, "frozen", False)
            app.run(
                debug=flask_debug,
                host=HOST,
                port=PORT,
                use_reloader=False,
                threaded=True,
            )

        flask_thread = threading.Thread(target=start_flask, daemon=True)
        flask_thread.start()

        time.sleep(1.5)

        if splash:
            splash.close()
            splash = None

        url = build_local_app_url(PORT)
        logger.info("Application URL: %s", url)
        logger.info("UI launch mode: %s", APPLICATION_UI_MODE)
        logger.info("Close the application window (or browser tab) to exit.")

        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(os.path.dirname(sys.executable), 'rajmines.ico')
        else:
            icon_path = os.path.join(app_data_path, 'rajmines.ico')

        def setup_and_run_webview():
            import webview

            class WebViewAPI:
                def save_file(self, file_data_base64, filename, mime_type='application/pdf'):
                    try:
                        import base64
                        import tkinter.filedialog
                        from tkinter import Tk

                        file_data = base64.b64decode(file_data_base64)
                        root = Tk()
                        root.withdraw()
                        root.attributes('-topmost', True)
                        file_path = tkinter.filedialog.asksaveasfilename(
                            defaultextension='.pdf',
                            filetypes=[('PDF files', '*.pdf'), ('All files', '*.*')],
                            initialfile=filename,
                            title='Save PDF Report'
                        )
                        root.destroy()
                        if file_path:
                            with open(file_path, 'wb') as f:
                                f.write(file_data)
                            return {"success": True, "path": file_path}
                        return {"success": False, "message": "Save cancelled"}
                    except Exception as e:
                        logger.error(f"Error in save_file API: {e}", exc_info=True)
                        return {"success": False, "message": str(e)}

            logger.info("Creating native application window (force fullscreen)")
            webview.create_window(
                title=APP_NAME,
                url=url,
                min_size=(1200, 700),
                resizable=True,
                fullscreen=True,
                maximized=True,
                on_top=False,
                shadow=True,
                js_api=WebViewAPI(),
            )

            # Ensure borderless fullscreen even if the host (WebView2/Qt) ignores the flag
            try:
                from utils.browser_launcher import force_native_window_fullscreen
                force_native_window_fullscreen(APP_NAME)
            except Exception as e:
                logger.warning("Could not schedule force fullscreen: %s", e)

            if os.path.exists(icon_path) and sys.platform == 'win32':
                def set_window_icon():
                    try:
                        import ctypes

                        ICON_BIG = 1
                        ICON_SMALL = 0
                        WM_SETICON = 0x0080
                        IMAGE_ICON = 1
                        LR_LOADFROMFILE = 0x00000010
                        LR_DEFAULTSIZE = 0x00000040

                        user32 = ctypes.windll.user32
                        shell32 = ctypes.windll.shell32
                        time.sleep(1.5)

                        hwnd = None
                        for _attempt in range(10):
                            hwnd = user32.FindWindowW(None, APP_NAME)
                            if hwnd and user32.IsWindowVisible(hwnd):
                                break
                            time.sleep(0.3)

                        if hwnd:
                            hicon = user32.LoadImageW(
                                None, icon_path, IMAGE_ICON, 0, 0,
                                LR_LOADFROMFILE | LR_DEFAULTSIZE,
                            )
                            if not hicon:
                                hicon = user32.LoadImageW(
                                    None, icon_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE,
                                )
                            if hicon:
                                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
                                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
                                try:
                                    class_atom = user32.GetClassLongPtrW(hwnd, -14)
                                    if class_atom:
                                        user32.SetClassLongPtrW(hwnd, -14, hicon)
                                        user32.SetClassLongPtrW(hwnd, -10, hicon)
                                except Exception:
                                    pass
                                user32.InvalidateRect(hwnd, None, True)
                                user32.UpdateWindow(hwnd)
                                user32.SetWindowPos(
                                    hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0020,
                                )
                                try:
                                    shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
                                except Exception:
                                    pass
                                time.sleep(0.5)
                                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
                                logger.info("Window icon set successfully: %s", icon_path)
                            else:
                                logger.warning("Could not load icon from: %s", icon_path)
                        else:
                            logger.warning("Could not find window with title: %s", APP_NAME)
                    except Exception as e:
                        logger.warning("Could not set window icon: %s", e)

                threading.Thread(target=set_window_icon, daemon=True).start()

            gui = None
            if sys.platform == 'win32':
                gui = 'edgechromium'
            elif sys.platform == 'darwin':
                gui = 'cocoa'
            return run_webview_start(
                APP_NAME,
                WEBVIEW_WINDOW_READY_TIMEOUT,
                debug=False,
                gui=gui,
            )

        launch_mode = run_ui_with_auto_fallback(
            url=url,
            ui_mode=APPLICATION_UI_MODE,
            webview_timeout_sec=WEBVIEW_WINDOW_READY_TIMEOUT,
            chrome_executable_path=CHROME_EXECUTABLE_PATH,
            app_name=APP_NAME,
            flask_thread=flask_thread,
            setup_and_run_webview=setup_and_run_webview,
            cleanup_callback=cleanup_all_connections,
        )
        logger.info("Application UI launched using: %s", launch_mode)

    except Exception as e:
        import traceback

        logger.error(f"\n{'='*50}")
        logger.error("ERROR: Application failed to start!")
        logger.error(f"{'='*50}")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Error Type: {type(e).__name__}")
        logger.error(traceback.format_exc())
        logger.error(f"{'='*50}")
        fatal_exit(
            f"The application could not start.\n\n{type(e).__name__}: {e}\n\n"
            f"Details were written to:\n{log_file}",
            title=APP_NAME,
            log_path=log_file,
        )

