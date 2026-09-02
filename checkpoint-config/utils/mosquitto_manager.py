"""
Mosquitto Manager Wrapper
Provides a simple interface to ensure Mosquitto broker is ready before application starts
"""
import os
import sys
import threading

# Import mosquitto_setup from parent directory (IoT-Configuration/)
# Add parent directory to path to import mosquitto_setup
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from mosquitto_setup import setup_mosquitto

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
    
    logger.info("ensure_mosquitto_ready() called")
    
    # Determine app_data_path same way as app.py
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        app_data_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        app_data_path = os.path.dirname(os.path.abspath(__file__))
        app_data_path = os.path.dirname(app_data_path)  # Go up one level to IoT-Configuration directory
    
    logger.info(f"App data path: {app_data_path}")
    
    # Create progress window if available
    progress_window = None
    logger.info("Creating Mosquitto progress window...")
    if PROGRESS_UI_AVAILABLE and MosquittoProgressWindow:
        try:
            logger.info("MosquittoProgressWindow class available, creating instance...")
            # Small delay before creating new tkinter window to avoid conflicts
            import time
            time.sleep(0.2)
            progress_window = MosquittoProgressWindow()
            logger.info(f"Progress window created, root is None: {progress_window.root is None}")
            if progress_window.root is None:
                progress_window = None
                logger.warning("Progress window root is None, continuing without UI")
            else:
                logger.info("Progress window created successfully")
        except Exception as e:
            logger.error(f"Error creating progress window: {e}", exc_info=True)
            logger.info(f"Warning: Could not create progress window: {e}")
            progress_window = None
    else:
        logger.info("Progress UI not available or MosquittoProgressWindow not found")
    
    # Create progress callback function
    def progress_callback(percent, message):
        """Update progress window with current status"""
        if progress_window:
            progress_window.update_progress(percent, message)
        else:
            # Fallback to console output
            logger.info(f"[{percent}%] {message}")
    
    # Setup Mosquitto synchronously
    # If we have a progress window, run setup in background thread and process UI events
    if progress_window and progress_window.root:
        status = {"success": False, "message": ""}
        setup_complete = threading.Event()
        
        def run_setup():
            """Run setup in separate thread"""
            try:
                result = setup_mosquitto(progress_callback=progress_callback, app_data_path=app_data_path)
                status.update(result)
            except Exception as e:
                status["success"] = False
                status["message"] = f"Unexpected error: {str(e)}"
            finally:
                setup_complete.set()
        
        # Start setup in background thread
        setup_thread = threading.Thread(target=run_setup, daemon=True)
        setup_thread.start()
        
        # Process UI events while setup is running
        # Poll for progress updates from background thread
        import time
        update_count = 0
        while not setup_complete.is_set():
            try:
                # Process any pending progress updates (thread-safe)
                progress_window._process_pending_updates()
                
                # Process all pending tkinter events
                progress_window.root.update()
                
                # Small delay to prevent CPU spinning but keep UI responsive
                time.sleep(0.01)  # 10ms delay - responsive for progress updates
                
                # Debug: log every 100 updates to verify loop is running
                update_count += 1
                if update_count % 100 == 0:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"UI event loop running (processed {update_count} updates)")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Error in UI event loop: {e}")
                break
        
        # Wait for setup thread to complete
        setup_thread.join(timeout=300)  # 5 minute timeout
    else:
        # No UI - run setup directly
        status = setup_mosquitto(progress_callback=progress_callback, app_data_path=app_data_path)
    
    # Handle result
    if status["success"]:
        if progress_window and progress_window.root:
            progress_window.show_success(status["message"])
            # Process events and wait for auto-close (2 seconds)
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
    else:
        if progress_window and progress_window.root:
            progress_window.show_error(status["message"])
            # Process events until user clicks OK
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

