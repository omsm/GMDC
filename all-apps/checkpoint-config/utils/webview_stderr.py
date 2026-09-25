# Suppress harmless Chromium / pywebview stderr noise on Windows (especially on exit).

import os
import sys
from contextlib import contextmanager

_installed = False
_original_stderr = None


def _null_stderr_sink():
    """No-op stderr when PyInstaller windowed EXE leaves sys.stderr as None."""

    class _Sink:
        def write(self, message):
            pass

        def flush(self):
            pass

    return _Sink()


def _stderr_writable(stream) -> bool:
    return stream is not None and hasattr(stream, "write")


def is_chromium_shutdown_noise(message) -> bool:
    """Return True for known benign WebView2/Chromium messages on window teardown."""
    msg_str = str(message)
    if not msg_str.strip():
        return False
    if "Failed to unregister class Chrome_WidgetWin" in msg_str:
        return True
    if "Chrome_WidgetWin" in msg_str and "unregister" in msg_str.lower():
        return True
    if "Error = 1411" in msg_str:
        return True
    if "window_impl.cc" in msg_str and (
        "unregister" in msg_str.lower() or "Failed to unregister" in msg_str
    ):
        return True
    if "ui\\gfx\\win\\window_impl.cc" in msg_str and "ERROR" in msg_str:
        return True
    return False


class FilteredStderr:
    """Wrap stderr and drop known Chromium teardown messages."""

    def __init__(self, original_stderr):
        self.original_stderr = original_stderr

    def write(self, message):
        if is_chromium_shutdown_noise(message):
            return
        if not _stderr_writable(self.original_stderr):
            return
        self.original_stderr.write(message)

    def flush(self):
        if not _stderr_writable(self.original_stderr):
            return
        self.original_stderr.flush()

    def __getattr__(self, name):
        if self.original_stderr is None:
            raise AttributeError(name)
        return getattr(self.original_stderr, name)


def install_webview_stderr_filter():
    """Install Chromium stderr filter for the rest of the process (idempotent)."""
    global _installed, _original_stderr
    if _installed:
        return
    _original_stderr = sys.stderr
    underlying = _original_stderr if _stderr_writable(_original_stderr) else _null_stderr_sink()
    sys.stderr = FilteredStderr(underlying)
    _installed = True


def restore_webview_stderr_filter():
    """Restore original stderr (optional; usually not needed before exit)."""
    global _installed, _original_stderr
    if not _installed or _original_stderr is None:
        return
    sys.stderr = _original_stderr
    _installed = False
    _original_stderr = None


@contextmanager
def suppress_native_stderr():
    """
    Redirect OS file descriptor 2 (stderr).

    Chromium/WebView2 logs such as:
      Failed to unregister class Chrome_WidgetWin_0. Error = 1411
    bypass Python's sys.stderr; this silences them on Windows during window teardown.
    """
    if sys.platform != "win32":
        yield
        return

    stderr_fd = 2
    saved_fd = os.dup(stderr_fd)
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull_fd, stderr_fd)
            yield
        finally:
            os.close(devnull_fd)
    finally:
        os.dup2(saved_fd, stderr_fd)
        os.close(saved_fd)


def destroy_webview_window_quietly():
    """Close pywebview window while suppressing known Chromium shutdown stderr noise."""
    import webview

    install_webview_stderr_filter()
    with suppress_native_stderr():
        webview.destroy_window()
