import logging
import os
import sys
import platform
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Platform-specific audio playback (same approach as Weighbridge-App)
if platform.system() == "Windows":
    try:
        import winsound  # type: ignore
        WINSOUND_AVAILABLE = True
    except ImportError:
        WINSOUND_AVAILABLE = False
else:
    WINSOUND_AVAILABLE = False


def _get_app_base_path() -> str:
    """
    Resolve the base path of the IoT-Configuration application.

    When running as a PyInstaller exe (ONEFILE/ONEDIR), returns the PyInstaller bundle
    extraction directory (sys._MEIPASS) so bundled assets (templates/static) are readable.
    When running as a script, returns the project root (IoT-Configuration/).
    """
    try:
        if getattr(sys, "frozen", False):
            # Running as compiled executable - use PyInstaller temp folder for bundled files
            base_path = getattr(sys, "_MEIPASS", None)
            if base_path:
                return base_path
            # Fallback (should be rare): use exe directory
            return os.path.dirname(sys.executable)
        # Running as script - use project root (parent of services/)
        services_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(services_dir)
    except Exception as e:
        logger.error(f"[AudioService] Error resolving app base path: {e}")
        return os.path.abspath(".")


class AudioService:
    """
    Simple audio test service for IoT-Configuration.

    Uses Windows winsound (like Weighbridge-App) to play a test WAV file
    on the configuration PC. This helps verify that the announcement
    system / audio driver is available.
    """

    def __init__(self, test_relative_path: str = os.path.join("static", "audio", "test_audio.wav")):
        self.base_dir = _get_app_base_path()

        # Prefer bundled static assets path in PyInstaller ONEFILE mode (sys._MEIPASS/static/...)
        bundled_path = os.path.join(self.base_dir, test_relative_path)

        # Allow optional external override next to exe (useful if site wants to replace the WAV)
        exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else self.base_dir
        external_path = os.path.join(exe_dir, test_relative_path)

        # Choose the first existing path; otherwise keep bundled_path for clearer error message
        if os.path.exists(bundled_path):
            self.test_audio_path = bundled_path
            source = "bundled"
        elif os.path.exists(external_path):
            self.test_audio_path = external_path
            source = "external"
        else:
            self.test_audio_path = bundled_path
            source = "missing"

        logger.info(f"[AudioService] Initialized ({source}) with test file: {self.test_audio_path}")

    def _play_safe(self, file_path: str) -> Dict[str, Any]:
        """
        Safely play an audio file with error handling.

        Returns a dict with:
            success: bool
            reason: optional machine-readable error code
            message: human-readable message
        """
        if not os.path.exists(file_path):
            msg = f"Audio file not found: {file_path}"
            logger.error(f"[AudioService] {msg}")
            return {"success": False, "reason": "FILE_NOT_FOUND", "message": msg}

        if not WINSOUND_AVAILABLE:
            # Matches the behavior in Weighbridge-App when winsound is unavailable
            msg = "Failed to play audio: Windows audio system not available (winsound missing)"
            logger.error(f"[AudioService] {msg}")
            return {"success": False, "reason": "NO_AUDIO_DRIVER", "message": msg}

        try:
            winsound.PlaySound(file_path, winsound.SND_FILENAME)  # type: ignore[name-defined]
            logger.info(f"[AudioService] Played test audio: {file_path}")
            return {"success": True, "message": "Audio played successfully"}
        except Exception as e:
            msg = f"Please connect audio device and try again."
            logger.error(f"[AudioService] Error: {str(e)}")
            return {"success": False, "reason": "PLAYBACK_ERROR", "message": msg}

    def play_test_audio(self) -> Dict[str, Any]:
        """
        Play the configured test audio file.

        This is used by the /api/audio/test endpoint.
        """
        logger.debug(f"[AudioService] Attempting to play test audio at: {self.test_audio_path}")
        return self._play_safe(self.test_audio_path)

