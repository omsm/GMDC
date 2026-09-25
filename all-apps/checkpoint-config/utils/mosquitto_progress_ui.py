"""
Mosquitto Setup Progress UI
Provides a tkinter-based progress window for displaying Mosquitto setup progress
"""
import tkinter as tk
from tkinter import ttk
import threading
import sys
import os


class MosquittoProgressWindow:
    """Progress window for Mosquitto setup process"""
    
    def __init__(self):
        """Initialize the progress window"""
        self.root = None
        self.percent_label = None
        self.status_label = None
        self.title_label = None
        self._lock = threading.Lock()
        self._closed = False
        # Thread-safe progress storage
        self._pending_percent = None
        self._pending_message = None
        
        # Try to create the window
        try:
            self._create_window()
        except Exception as e:
            # If tkinter fails, we'll just use console output
            logger.info(f"Warning: Could not create progress window: {e}")
            self.root = None
    
    def _create_window(self):
        """Create and configure the progress window"""
        self.root = tk.Tk()
        self.root.title("Installing required pre-requisites applications")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)  # Keep on top during setup
        
        # Set window size
        window_width = 500
        window_height = 200
        
        # Center window on screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # Try to set window icon
        try:
            if getattr(sys, 'frozen', False):
                # Running as executable
                icon_path = os.path.join(os.path.dirname(sys.executable), 'rajmines.ico')
            else:
                # Running as script
                icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'rajmines.ico')
            
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass  # Icon is optional
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title label
        self.title_label = ttk.Label(
            main_frame,
            text="Installing required pre-requisites applications",
            font=("Arial", 12, "bold")
        )
        self.title_label.pack(pady=(0, 15))
        
        # Percentage label (large and prominent)
        self.percent_label = ttk.Label(
            main_frame,
            text="0%",
            font=("Arial", 24, "bold"),
            foreground="blue"
        )
        self.percent_label.pack(pady=(0, 10))
        
        # Status label (hidden - we only show percentage)
        self.status_label = ttk.Label(
            main_frame,
            text="",
            font=("Arial", 10),
            wraplength=450,
            justify=tk.CENTER
        )
        self.status_label.pack(pady=(0, 10))
        self.status_label.pack_forget()  # Hide the status label
        
        # Info label
        info_label = ttk.Label(
            main_frame,
            text="Please wait while we set up the MQTT broker for you.",
            font=("Arial", 9),
            foreground="gray"
        )
        info_label.pack()
        
        # Update window to make it visible and ensure it's shown
        self.root.update()
        self.root.deiconify()  # Ensure window is visible
        self.root.lift()  # Bring window to front
        self.root.focus_force()  # Force focus to ensure it's active
    
    def update_progress(self, percent, message):
        """
        Update percentage and status message (thread-safe)
        Stores values to be picked up by the main loop
        
        Args:
            percent: Progress percentage (0-100)
            message: Status message to display
        """
        if self.root is None or self._closed:
            return
        
        # Clamp percent to valid range
        clamped_percent = min(100, max(0, int(percent)))
        
        # Store values in thread-safe way - main loop will pick these up
        with self._lock:
            self._pending_percent = clamped_percent
            self._pending_message = str(message)
    
    def _process_pending_updates(self):
        """
        Process any pending progress updates (called from main thread)
        Returns True if an update was processed
        """
        if self.root is None or self._closed:
            return False
        
        # Check for pending updates
        pending_percent = None
        pending_message = None
        
        with self._lock:
            if self._pending_percent is not None:
                pending_percent = self._pending_percent
                pending_message = self._pending_message
                # Clear pending values
                self._pending_percent = None
                self._pending_message = None
        
        # Update UI if there's a pending update
        if pending_percent is not None:
            try:
                # Update percentage label only (don't show status message)
                if self.percent_label:
                    self.percent_label.config(text=f"{pending_percent}%")
                
                # Don't update status message - we're hiding it
                # Status label is hidden, so we don't need to update it
                
                return True
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Error processing progress update: {e}")
        
        return False
    
    def show_success(self, message="Setup completed successfully!"):
        """
        Show success message and auto-close after 2 seconds
        
        Args:
            message: Success message to display
        """
        if self.root is None or self._closed:
            return
        
        def _show_success():
            if self.root is None or self._closed:
                return
            try:
                # Update percentage to 100%
                if self.percent_label:
                    self.percent_label.config(text="100%", foreground="green")
                
                # Don't update status message - it's hidden
                
                # Update title
                if self.title_label:
                    self.title_label.config(
                        text="✓ Installation Completed",
                        foreground="green"
                    )
                
                self.root.update()
                
                # Auto-close after 2 seconds
                self.root.after(2000, self.close)
            except Exception:
                pass
        
        try:
            self.root.after(0, _show_success)
            # Keep window alive for 2 seconds
            self.root.after(2000, lambda: None)
        except Exception:
            pass
    
    def show_error(self, message):
        """
        Show error message with OK button
        
        Args:
            message: Error message to display
        """
        if self.root is None or self._closed:
            return
        
        def _show_error():
            if self.root is None or self._closed:
                return
            try:
                # Update percentage to show error
                if self.percent_label:
                    self.percent_label.config(text="Error", foreground="red")
                
                # Don't update status message - it's hidden
                # Error message will be shown in title only
                
                # Update title
                if self.title_label:
                    self.title_label.config(
                        text="✗ Pre-Requisites Installation Failed",
                        foreground="red"
                    )
                
                # Remove info label and add OK button
                for widget in self.root.winfo_children():
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Label) and child.cget("foreground") == "gray":
                            child.destroy()
                
                # Add OK button
                ok_button = ttk.Button(
                    self.root.winfo_children()[0],  # main_frame
                    text="OK",
                    command=self.close
                )
                ok_button.pack(pady=(10, 0))
                
                self.root.update()
            except Exception as e:
                logger.info(f"Error showing error dialog: {e}")
        
        try:
            self.root.after(0, _show_error)
        except Exception:
            pass
    
    def close(self):
        """Close the progress window"""
        if self._closed:
            return
        
        self._closed = True
        
        if self.root is not None:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
    
    def wait_for_close(self, timeout=None):
        """
        Wait for window to be closed (for error dialogs)
        
        Args:
            timeout: Maximum time to wait in milliseconds (None = wait indefinitely)
        """
        if self.root is None or self._closed:
            return
        
        try:
            if timeout:
                self.root.after(timeout, self.root.quit)
            self.root.mainloop()
        except Exception:
            pass

