import logging
import os
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_SYSTEM = platform.system()

# Platform backends:
# - Windows: winsound
# - macOS: afplay (built-in)
# - Linux: aplay (alsa-utils) when available
WINSOUND_AVAILABLE = False
if _SYSTEM == "Windows":
    try:
        import winsound  # type: ignore

        WINSOUND_AVAILABLE = True
    except ImportError:
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
            base_path = getattr(sys, "_MEIPASS", None)
            if base_path:
                return base_path
            return os.path.dirname(sys.executable)
        services_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.dirname(services_dir)
    except Exception as e:
        logger.error("[AudioService] Error resolving app base path: %s", e)
        return os.path.abspath(".")


def _resolve_audio_backend() -> Optional[str]:
    if _SYSTEM == "Windows" and WINSOUND_AVAILABLE:
        return "winsound"
    if _SYSTEM == "Darwin" and shutil.which("afplay"):
        return "afplay"
    if _SYSTEM == "Linux" and shutil.which("aplay"):
        return "aplay"
    return None


class AudioService:
    """
    Simple audio test service for IoT-Configuration.

    Plays a test WAV on the configuration PC so operators can confirm the
    announcement / speaker path works (Windows winsound, macOS afplay, Linux aplay).
    """

    def __init__(
        self, test_relative_path: str = os.path.join("static", "audio", "test_audio.wav")
    ):
        self.base_dir = _get_app_base_path()
        self.backend = _resolve_audio_backend()

        bundled_path = os.path.join(self.base_dir, test_relative_path)
        exe_dir = (
            os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else self.base_dir
        )
        external_path = os.path.join(exe_dir, test_relative_path)

        if os.path.exists(bundled_path):
            self.test_audio_path = bundled_path
            source = "bundled"
        elif os.path.exists(external_path):
            self.test_audio_path = external_path
            source = "external"
        else:
            self.test_audio_path = bundled_path
            source = "missing"

        logger.info(
            "[AudioService] Initialized (%s, backend=%s) with test file: %s",
            source,
            self.backend or "none",
            self.test_audio_path,
        )

    def _play_with_backend(self, file_path: str) -> None:
        if self.backend == "winsound":
            import winsound  # type: ignore

            winsound.PlaySound(file_path, winsound.SND_FILENAME)
            return

        if self.backend == "afplay":
            cmd = [shutil.which("afplay") or "afplay", file_path]
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                err = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
                raise RuntimeError(err or f"afplay exited with code {result.returncode}")
            return

        if self.backend == "aplay":
            cmd = [shutil.which("aplay") or "aplay", file_path]
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=60,
                check=False,
            )
            if result.returncode != 0:
                err = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
                raise RuntimeError(err or f"aplay exited with code {result.returncode}")
            return

        raise RuntimeError("No audio backend available")

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
            logger.error("[AudioService] %s", msg)
            return {"success": False, "reason": "FILE_NOT_FOUND", "message": msg}

        if not self.backend:
            msg = (
                f"Failed to play audio: no audio backend on {platform.system()} "
                "(need winsound / afplay / aplay)"
            )
            logger.error("[AudioService] %s", msg)
            return {"success": False, "reason": "NO_AUDIO_DRIVER", "message": msg}

        try:
            self._play_with_backend(file_path)
            logger.info(
                "[AudioService] Played test audio via %s: %s", self.backend, file_path
            )
            return {"success": True, "message": "Audio played successfully"}
        except Exception as e:
            msg = "Please connect audio device and try again."
            logger.error("[AudioService] Playback error via %s: %s", self.backend, e)
            return {"success": False, "reason": "PLAYBACK_ERROR", "message": msg}

    def play_test_audio(self) -> Dict[str, Any]:
        """
        Play the configured test audio file.

        This is used by the /api/audio/test endpoint.
        """
        logger.debug(
            "[AudioService] Attempting to play test audio at: %s", self.test_audio_path
        )
        return self._play_safe(self.test_audio_path)
