"""
Splash Screen - Simple Tkinter window showing startup message
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
import logging

logger = logging.getLogger("iot_config.splash")


class SplashScreen:
    """Simple splash screen window"""
    
    def __init__(self, message: str = "Starting Application, Please wait!"):
        """
        Initialize the splash screen.
        
        Args:
            message: Message to display
        """
        self.message = message
        self.root = None
        self._closed = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Create window and run mainloop in a separate thread
        self._create_window()
    
    def _create_window(self):
        """Create the splash window in a separate thread"""
        def _run_window():
            """Run Tkinter window in this thread"""
            try:
                self.root = tk.Tk()
                self.root.title("Starting...")
                self.root.resizable(False, False)
                self.root.attributes('-topmost', True)  # Keep on top
                
                # Center window on screen
                self._center_window(400, 150)
                
                # Prevent window close button
                self.root.protocol("WM_DELETE_WINDOW", lambda: None)
                
                # Main frame
                main_frame = ttk.Frame(self.root, padding="30")
                main_frame.pack(fill=tk.BOTH, expand=True)
                
                # Message label
                message_label = ttk.Label(
                    main_frame,
                    text=self.message,
                    font=("Arial", 12),
                    justify=tk.CENTER
                )
                message_label.pack(pady=10)
                
                # Progress bar (indeterminate)
                self.progress = ttk.Progressbar(
                    main_frame,
                    mode='indeterminate',
                    length=300
                )
                self.progress.pack(pady=10)
                self.progress.start(10)  # Start animation
                
                # Run the mainloop - this keeps the window responsive
                # Check _closed flag periodically and exit if closed
                while not self._closed:
                    try:
                        self.root.update()
                        time.sleep(0.1)
                    except:
                        break
                
                # Cleanup when closed
                try:
                    if hasattr(self, 'progress') and self.progress:
                        try:
                            self.progress.stop()
                        except:
                            pass
                    if self.root:
                        try:
                            self.root.destroy()
                        except:
                            pass
                except:
                    pass
                
            except Exception as e:
                logger.error(f"Error in splash screen thread: {e}")
                with self._lock:
                    self.root = None
        
        # Start the window in a separate thread
        self._thread = threading.Thread(target=_run_window, daemon=True, name="SplashScreenThread")
        self._thread.start()
        
        # Wait a bit for the window to be created
        for _ in range(50):  # Wait up to 0.5 seconds
            time.sleep(0.01)
            if self.root is not None:
                break
    
    def _center_window(self, width: int, height: int):
        """Center the window on the screen"""
        if not self.root:
            return
        try:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
            self.root.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass
    
    def update(self):
        """Update the window (process events) - not needed when using mainloop in thread"""
        # The mainloop in the thread handles updates automatically
        pass
    
    def close(self):
        """Close the splash screen - non-blocking, just marks as closed"""
        # Just mark as closed - the thread loop will check this and exit
        with self._lock:
            self._closed = True
    
    def wait_for_close(self, timeout=2.0):
        """
        Wait for the splash screen to fully close.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if closed, False if timeout
        """
        if self._closed and self.root is None:
            return True
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._lock:
                if self._closed and self.root is None:
                    return True
            time.sleep(0.1)
        
        return False
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def show_splash_screen(message: str = "Starting Application, Please wait!"):
    """
    Show a splash screen during application startup.
    
    Args:
        message: Message to display
        
    Returns:
        SplashScreen instance
    """
    try:
        splash = SplashScreen(message)
        return splash
    except Exception as e:
        logger.error(f"Error showing splash screen: {e}")
        return None

