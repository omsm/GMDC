"""Fatal startup errors for windowed PyInstaller EXE (no console for input/print)."""

import os
import sys
from typing import Optional

def is_stdio_unavailable(stream) -> bool:
    return stream is None or not hasattr(stream, "write")


try:
    from logging_config import is_stdio_unavailable as _lc_is_stdio_unavailable

    is_stdio_unavailable = _lc_is_stdio_unavailable
except ImportError:
    pass


def has_interactive_console() -> bool:
    """True when stdin/stdout support an interactive terminal."""
    if is_stdio_unavailable(sys.stdout) or is_stdio_unavailable(sys.stdin):
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def append_fatal_log(log_path: str, message: str) -> None:
    if not log_path:
        return
    try:
        log_dir = os.path.dirname(log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except Exception:
        pass


def show_fatal_message(title: str, message: str) -> None:
    text = str(message).strip() or "The application could not start."
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
            return
        except Exception:
            pass
    if not is_stdio_unavailable(sys.stderr):
        try:
            print(f"{title}\n{text}", file=sys.stderr)
        except Exception:
            pass


def fatal_exit(
    message: str,
    title: str = "E-Rawanna",
    log_path: Optional[str] = None,
    exit_code: int = 1,
) -> None:
    """
    Log, show a dialog when console is unavailable, then exit.
    Use instead of input() + sys.exit() in windowed EXE builds.
    """
    text = str(message).strip()
    try:
        import logging

        logging.getLogger("iot_config.fatal").critical(text)
    except Exception:
        pass
    append_fatal_log(log_path, text)
    show_fatal_message(title, text)
    if has_interactive_console():
        try:
            input("\nPress Enter to exit...")
        except Exception:
            pass
    raise SystemExit(exit_code)
