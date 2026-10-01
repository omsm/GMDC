"""
Mosquitto Manager Wrapper
Ensures Mosquitto broker is ready before checkpoint-config starts.
Delegates install/config/service to shared mqtt_broker_setup package.
"""
import os
import sys
import threading

# Resolve shared installer: ../mqtt_broker_setup (repo root sibling)
_here = os.path.dirname(os.path.abspath(__file__))
_checkpoint_config = os.path.dirname(_here)
_repo_root = os.path.dirname(_checkpoint_config)
_shared = os.path.join(_repo_root, "mqtt_broker_setup")
for _p in (_shared, _repo_root, _checkpoint_config):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from mqtt_broker_setup.ensure import (
        add_package_to_sys_path,
        ensure_mqtt_broker_ready,
        mqtt_ports_ready,
    )

    add_package_to_sys_path()
    _USE_SHARED = True
except ImportError:
    # Fallback: local copy next to checkpoint-config (legacy / frozen builds)
    from mosquitto_setup import setup_mosquitto

    _USE_SHARED = False

    def mqtt_ports_ready(*_a, **_k):
        return False

    def ensure_mqtt_broker_ready(app_data_path=None, progress_callback=None, **_k):
        status = setup_mosquitto(
            progress_callback=progress_callback,
            app_data_path=app_data_path,
        )
        return bool(status.get("success")), status.get("message") or ""

# Try to import progress UI (fallback to None if tkinter not available)
try:
    from utils.mosquitto_progress_ui import MosquittoProgressWindow

    PROGRESS_UI_AVAILABLE = True
except ImportError:
    MosquittoProgressWindow = None
    PROGRESS_UI_AVAILABLE = False


def ensure_mosquitto_ready():
    """
    Ensure Mosquitto broker is installed, configured, and running.
    Determines app_data_path using the same logic as app.py.
    Shows progress window during setup.

    Returns:
        tuple: (success: bool, message: str)
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.info("ensure_mosquitto_ready() called (shared=%s)", _USE_SHARED)

    # Determine app_data_path same way as app.py
    if getattr(sys, "frozen", False):
        app_data_path = os.path.dirname(sys.executable)
    else:
        app_data_path = os.path.dirname(os.path.abspath(__file__))
        app_data_path = os.path.dirname(app_data_path)

    logger.info("App data path: %s", app_data_path)

    # Fast path: both listeners already up
    try:
        if mqtt_ports_ready():
            msg = "MQTT broker already listening on 1883 and 9001"
            logger.info(msg)
            return True, msg
    except Exception as e:
        logger.debug("Port check skipped: %s", e)

    progress_window = None
    logger.info("Creating Mosquitto progress window...")
    if sys.platform == "darwin":
        logger.info("Skipping Mosquitto progress UI on macOS (Tk main-thread restriction)")
    elif PROGRESS_UI_AVAILABLE and MosquittoProgressWindow:
        try:
            import time

            time.sleep(0.2)
            progress_window = MosquittoProgressWindow()
            if progress_window.root is None:
                progress_window = None
                logger.warning("Progress window root is None, continuing without UI")
            else:
                logger.info("Progress window created successfully")
        except Exception as e:
            logger.error("Error creating progress window: %s", e, exc_info=True)
            progress_window = None
    else:
        logger.info("Progress UI not available or MosquittoProgressWindow not found")

    def progress_callback(percent, message):
        if progress_window:
            progress_window.update_progress(percent, message)
        else:
            logger.info("[%s%%] %s", percent, message)

    if progress_window and progress_window.root:
        status = {"success": False, "message": ""}
        setup_complete = threading.Event()

        def run_setup():
            try:
                ok, msg = ensure_mqtt_broker_ready(
                    app_data_path=app_data_path,
                    progress_callback=progress_callback,
                )
                status["success"] = ok
                status["message"] = msg
            except Exception as e:
                status["success"] = False
                status["message"] = f"Unexpected error: {str(e)}"
            finally:
                setup_complete.set()

        setup_thread = threading.Thread(target=run_setup, daemon=True)
        setup_thread.start()

        import time

        update_count = 0
        while not setup_complete.is_set():
            try:
                progress_window._process_pending_updates()
                progress_window.root.update()
                time.sleep(0.01)
                update_count += 1
                if update_count % 100 == 0:
                    logger.debug(
                        "UI event loop running (processed %s updates)", update_count
                    )
            except Exception as e:
                logger.debug("Error in UI event loop: %s", e)
                break

        setup_thread.join(timeout=300)
    else:
        ok, msg = ensure_mqtt_broker_ready(
            app_data_path=app_data_path,
            progress_callback=progress_callback,
        )
        status = {"success": ok, "message": msg}

    if status["success"]:
        if progress_window and progress_window.root:
            progress_window.show_success(status["message"])
            import time

            end_time = time.time() + 2.5
            while time.time() < end_time:
                try:
                    progress_window.root.update()
                    time.sleep(0.1)
                except Exception:
                    break
        if progress_window:
            progress_window.close()
        return True, status["message"]

    if progress_window and progress_window.root:
        progress_window.show_error(status["message"])
        while progress_window.root and not progress_window._closed:
            try:
                progress_window.root.update()
                import time

                time.sleep(0.1)
            except Exception:
                break
    if progress_window:
        progress_window.close()
    return False, status["message"]
