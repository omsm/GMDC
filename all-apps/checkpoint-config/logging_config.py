import logging

CONSOLE_LOG_LEVEL = logging.DEBUG
FILE_LOG_LEVEL = logging.DEBUG


class NullLogStream:
    """No-op stream for windowed PyInstaller EXE (sys.stdout/stderr may be None)."""

    def write(self, message):
        pass

    def flush(self):
        pass

    def isatty(self):
        return False


def safe_log_stream(stream):
    """Return stream if writable; otherwise a no-op sink so StreamHandler never crashes."""
    if stream is not None and hasattr(stream, "write"):
        return stream
    return NullLogStream()


def is_stdio_unavailable(stream) -> bool:
    return stream is None or not hasattr(stream, "write")
