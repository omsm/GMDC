"""Regression: logging and stderr filter must not crash when stdout/stderr are None (windowed EXE)."""

import logging
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import safe_log_stream, is_stdio_unavailable
from utils.webview_stderr import FilteredStderr, install_webview_stderr_filter


class TestFrozenStdioLogging(unittest.TestCase):
    def test_safe_log_stream_none_stdout(self):
        sink = safe_log_stream(None)
        sink.write("hello\n")
        sink.flush()

    def test_stream_handler_with_none_stdout(self):
        log_dir = tempfile.mkdtemp()
        log_file = os.path.join(log_dir, "test.log")
        try:
            from logging.handlers import TimedRotatingFileHandler

            file_handler = TimedRotatingFileHandler(
                log_file, when="midnight", interval=1, backupCount=1, encoding="utf-8"
            )
            console_handler = logging.StreamHandler(safe_log_stream(None))
            logging.basicConfig(
                level=logging.DEBUG,
                handlers=[file_handler, console_handler],
                force=True,
            )
            logger = logging.getLogger("test_frozen")
            logger.info("startup line with no stdout")
            with open(log_file, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("startup line with no stdout", content)
        finally:
            logging.shutdown()
            if os.path.exists(log_file):
                os.remove(log_file)
            os.rmdir(log_dir)

    def test_filtered_stderr_none_underlying(self):
        wrapper = FilteredStderr(None)
        wrapper.write("normal message\n")
        wrapper.flush()
        wrapper.write("Failed to unregister class Chrome_WidgetWin_0. Error = 1411\n")

    def test_install_filter_when_stderr_none(self):
        saved = sys.stderr
        try:
            sys.stderr = None
            install_webview_stderr_filter()
            sys.stderr.write("test\n")
            sys.stderr.flush()
        finally:
            sys.stderr = saved


if __name__ == "__main__":
    unittest.main()
