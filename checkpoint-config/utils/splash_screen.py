"""
Splash Screen - Simple Tkinter window showing startup message.

On macOS, Tk/NSWindow must be created on the main thread. Creating it on a
background thread aborts the process (NSInternalInconsistencyException).
Splash is therefore skipped on Darwin; startup continues with console/file logs.
"""

from __future__ import annotations

import logging
import sys
import threading
import time

logger = logging.getLogger("iot_config.splash")


class _NullSplash:
    """No-op splash used when Tk UI cannot safely run (e.g. macOS)."""

    def update(self) -> None:
        return

    def close(self) -> None:
        return

    def wait_for_close(self, timeout: float = 2.0) -> bool:
        return True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class SplashScreen:
    """Simple splash screen window (Windows / Linux)."""

    def __init__(self, message: str = "Starting Application, Please wait!"):
        self.message = message
        self.root = None
        self._closed = False
        self._thread = None
        self._lock = threading.Lock()
        self._create_window()

    def _create_window(self) -> None:
        """Create the splash window in a separate thread (non-macOS only)."""

        def _run_window():
            try:
                import tkinter as tk
                from tkinter import ttk

                self.root = tk.Tk()
                self.root.title("Starting...")
                self.root.resizable(False, False)
                self.root.attributes("-topmost", True)

                self._center_window(400, 150)
                self.root.protocol("WM_DELETE_WINDOW", lambda: None)

                main_frame = ttk.Frame(self.root, padding="30")
                main_frame.pack(fill=tk.BOTH, expand=True)

                ttk.Label(
                    main_frame,
                    text=self.message,
                    font=("Arial", 12),
                    justify=tk.CENTER,
                ).pack(pady=10)

                self.progress = ttk.Progressbar(
                    main_frame, mode="indeterminate", length=300
                )
                self.progress.pack(pady=10)
                self.progress.start(10)

                while not self._closed:
                    try:
                        self.root.update()
                        time.sleep(0.1)
                    except Exception:
                        break

                try:
                    if hasattr(self, "progress") and self.progress:
                        try:
                            self.progress.stop()
                        except Exception:
                            pass
                    if self.root:
                        try:
                            self.root.destroy()
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception as e:
                logger.error("Error in splash screen thread: %s", e)
                with self._lock:
                    self.root = None

        self._thread = threading.Thread(
            target=_run_window, daemon=True, name="SplashScreenThread"
        )
        self._thread.start()

        for _ in range(50):
            time.sleep(0.01)
            if self.root is not None:
                break

    def _center_window(self, width: int, height: int) -> None:
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

    def update(self) -> None:
        return

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def wait_for_close(self, timeout: float = 2.0) -> bool:
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
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def show_splash_screen(message: str = "Starting Application, Please wait!"):
    """
    Show a splash screen during application startup.

    Returns a SplashScreen (or null splash on macOS / on failure).
    """
    if sys.platform == "darwin":
        logger.info(
            "Skipping Tk splash on macOS (NSWindow must be created on the main thread)"
        )
        return _NullSplash()
    try:
        return SplashScreen(message)
    except Exception as e:
        logger.error("Error showing splash screen: %s", e)
        return _NullSplash()
