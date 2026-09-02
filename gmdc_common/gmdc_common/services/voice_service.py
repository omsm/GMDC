"""
Voice announcement service — pre-recorded WAV playback.

- Windows: winsound
- macOS: afplay (built-in)
- Linux: aplay or paplay when available

Layout expected under voice_directory:

  information/   forward.wav, welcome.wav, tare_final_weight.wav, …
  error/         error_start.wav, g*.wav, t*.wav, rfid_*.wav, …
  weight_ton/    Siren.wav, 1.wav–N.wav
  weight_kg/     10.wav, …
  VNO/           A–Z, 0–9
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
from threading import Lock, Thread
from typing import Optional, Union

logger = logging.getLogger("gmdc_common.services.voice")

_SYSTEM = platform.system()
_PLAYBACK_PROC = None
_PLAYBACK_LOCK = Lock()

if _SYSTEM == "Windows":
    try:
        import winsound

        WINSOUND_AVAILABLE = True
    except ImportError:
        winsound = None  # type: ignore
        WINSOUND_AVAILABLE = False
else:
    winsound = None  # type: ignore
    WINSOUND_AVAILABLE = False


def _audio_backend_name() -> str:
    if _SYSTEM == "Windows" and WINSOUND_AVAILABLE:
        return "winsound"
    if _SYSTEM == "Darwin" and shutil.which("afplay"):
        return "afplay"
    if _SYSTEM == "Linux":
        if shutil.which("aplay"):
            return "aplay"
        if shutil.which("paplay"):
            return "paplay"
    return "none"


AUDIO_BACKEND = _audio_backend_name()
AUDIO_AVAILABLE = AUDIO_BACKEND != "none"


def _stop_playback() -> None:
    """Stop any in-progress WAV playback."""
    global _PLAYBACK_PROC
    if _SYSTEM == "Windows" and WINSOUND_AVAILABLE:
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception as exc:
            logger.debug("Error stopping winsound: %s", exc)
        return

    with _PLAYBACK_LOCK:
        proc = _PLAYBACK_PROC
        _PLAYBACK_PROC = None
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception as exc:
        logger.debug("Error stopping playback process: %s", exc)


def _play_wav_file(file_path: str) -> bool:
    """Blocking WAV playback using the platform backend."""
    if _SYSTEM == "Windows" and WINSOUND_AVAILABLE:
        winsound.PlaySound(file_path, winsound.SND_FILENAME)
        return True

    if _SYSTEM == "Darwin":
        afplay = shutil.which("afplay")
        if not afplay:
            logger.warning("afplay not found on macOS — cannot play %s", file_path)
            return False
        cmd = [afplay, file_path]
    elif _SYSTEM == "Linux":
        player = shutil.which("aplay") or shutil.which("paplay")
        if not player:
            logger.warning("No aplay/paplay found on Linux — cannot play %s", file_path)
            return False
        cmd = [player, file_path]
    else:
        logger.warning("No audio backend for %s — cannot play %s", _SYSTEM, file_path)
        return False

    global _PLAYBACK_PROC
    try:
        with _PLAYBACK_LOCK:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _PLAYBACK_PROC = proc
        proc.wait()
        return proc.returncode == 0
    except Exception as exc:
        logger.error("Error playing audio %s: %s", file_path, exc)
        return False
    finally:
        with _PLAYBACK_LOCK:
            if _PLAYBACK_PROC is proc:
                _PLAYBACK_PROC = None


class VoiceService:
    """Async WAV announcements with interrupt + multi-clip sequences."""

    def __init__(
        self,
        voice_directory: str = "voice",
        error_prefix: bool = True,
        hardware_enabled: bool = True,
        base_path: Optional[str] = None,
    ):
        """
        Args:
            voice_directory: Absolute path, or path relative to base_path.
            error_prefix: Play error/error_start.wav before many errors.
            hardware_enabled: False when voice.validated is not true in config.
            base_path: App root used when voice_directory is relative.
        """
        if os.path.isabs(voice_directory):
            self.voice_dir = voice_directory
        else:
            root = base_path or os.getcwd()
            self.voice_dir = os.path.join(root, voice_directory)

        self._enabled = bool(hardware_enabled)
        self._currently_playing = False
        self.error_prefix = error_prefix
        self._interrupt_enabled = True
        self._play_lock = Lock()
        self._play_id = 0
        self._multi_play_active = False

        if not self._enabled:
            logger.info("VoiceService disabled (not validated / not enabled in config)")
        elif not os.path.isdir(self.voice_dir):
            logger.warning("Voice directory not found: %s", self.voice_dir)
            self._enabled = False
        elif not AUDIO_AVAILABLE:
            logger.warning(
                "No audio backend on %s (need winsound / afplay / aplay) — voice disabled",
                _SYSTEM,
            )
            self._enabled = False
        else:
            logger.info(
                "VoiceService ready dir=%s backend=%s",
                self.voice_dir,
                AUDIO_BACKEND,
            )

    # ------------------------------------------------------------------
    # Core playback
    # ------------------------------------------------------------------
    def stop(self) -> None:
        if not self._enabled:
            return
        _stop_playback()
        self._currently_playing = False

    def _play_safe(self, file_path: str, interrupt: bool = True) -> bool:
        if not self._enabled:
            return False
        try:
            if not os.path.exists(file_path):
                logger.warning("Audio file not found: %s", file_path)
                return False
            if not AUDIO_AVAILABLE:
                logger.debug("No audio backend — skip %s", file_path)
                return False
            if interrupt and self._interrupt_enabled:
                _stop_playback()
            return _play_wav_file(file_path)
        except Exception as e:
            logger.error("Error playing audio %s: %s", file_path, e)
            return False

    def _info(self, name: str) -> str:
        return os.path.join(self.voice_dir, "information", name)

    def _err(self, name: str) -> str:
        return os.path.join(self.voice_dir, "error", name)

    def _start_multi_play(self) -> int:
        if not self._enabled:
            return -1
        self._multi_play_active = True
        self._play_id += 1
        self.stop()
        self._play_lock.acquire()
        return self._play_id

    def _end_multi_play(self) -> None:
        self._multi_play_active = False
        try:
            self._play_lock.release()
        except RuntimeError:
            pass

    def is_multi_play_active(self) -> bool:
        return self._multi_play_active

    def _is_play_valid(self, play_id: int) -> bool:
        if not self._enabled or play_id < 0:
            return False
        return play_id == self._play_id

    def _play_error_prefix(self) -> None:
        if self.error_prefix:
            self._play_safe(self._err("error_start.wav"), interrupt=False)

    def _play_async(self, filepath: str, interrupt: bool = True) -> None:
        if not self._enabled:
            return
        if interrupt and self._interrupt_enabled and self._multi_play_active:
            logger.debug(
                "Deferring voice until multi-play finishes: %s",
                os.path.basename(filepath),
            )
            return

        self._play_id += 1
        current_play_id = self._play_id
        if interrupt and self._interrupt_enabled:
            self.stop()

        Thread(
            target=self._play_sync,
            args=(filepath, current_play_id),
            daemon=True,
        ).start()

    def _play_sync(self, filepath: str, play_id: int) -> None:
        if not self._enabled or play_id != self._play_id:
            return
        with self._play_lock:
            if play_id != self._play_id:
                return
            self._currently_playing = True
            self._play_safe(filepath, interrupt=False)
            self._currently_playing = False

    def _play_error_sequence(self, *relative_under_error: str) -> None:
        """Play optional error_start then one or more error/*.wav clips."""

        def _play():
            my_id = self._start_multi_play()
            try:
                if not self._is_play_valid(my_id):
                    return
                self._play_error_prefix()
                for name in relative_under_error:
                    if not self._is_play_valid(my_id):
                        return
                    self._play_safe(self._err(name), interrupt=False)
            finally:
                self._end_multi_play()

        Thread(target=_play, daemon=True).start()

    # ------------------------------------------------------------------
    # Information
    # ------------------------------------------------------------------
    def move_forward(self) -> None:
        self._play_async(self._info("forward.wav"))
        logger.info("Voice: Move Forward")

    def move_backward(self) -> None:
        self._play_async(self._info("backward.wav"))
        logger.info("Voice: Move Backward")

    def please_wait(self) -> None:
        path = self._info("please_wait.wav")
        if os.path.exists(path):
            self._play_async(path)
        else:
            # No dedicated clip in some packs — stay silent rather than wrong prompt
            logger.debug("please_wait.wav missing — skip")
        logger.info("Voice: Please Wait")

    def welcome(self) -> None:
        self._play_async(self._info("welcome.wav"))
        logger.info("Voice: Welcome")

    def application_reset(self) -> None:
        self._play_async(self._info("application_reset.wav"))
        logger.info("Voice: Application Reset")

    def rescan_card(self) -> None:
        self._play_async(self._info("rescan_card.wav"))
        logger.info("Voice: Rescan Card")

    def rescan_card_entry_timeout(self) -> None:
        def _play():
            my_id = self._start_multi_play()
            try:
                if not self._is_play_valid(my_id):
                    return
                self._play_safe(self._err("error_start.wav"), interrupt=False)
                if not self._is_play_valid(my_id):
                    return
                self._play_safe(self._info("rescan_card.wav"), interrupt=False)
            finally:
                self._end_multi_play()

        Thread(target=_play, daemon=True).start()
        logger.info("Voice: Entry timeout — error_start + rescan_card")

    def goto_exit(self) -> None:
        path = self._info("goto_exit.wav")
        if os.path.exists(path):
            self._play_async(path)
        else:
            self.move_forward()
        logger.info("Voice: Goto Exit")

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------
    def digitizer_error(self) -> None:
        self._play_async(self._err("Digitizer_error.wav"))
        logger.info("Voice: Digitizer error")

    def positioning_error(self) -> None:
        self._play_async(self._err("positioning_error.wav"))
        logger.info("Voice: Positioning error")

    def rfid_api_error(self) -> None:
        self._play_error_sequence("g7.wav")
        logger.info("Voice: RFID API Error (error_start + g7)")

    def rfid_not_found(self) -> None:
        path = self._err("rfid_not_found.wav")
        if os.path.exists(path):

            def _play():
                my_id = self._start_multi_play()
                try:
                    if not self._is_play_valid(my_id):
                        return
                    self._play_safe(self._err("error_start.wav"), interrupt=False)
                    if not self._is_play_valid(my_id):
                        return
                    self._play_safe(path, interrupt=False)
                finally:
                    self._end_multi_play()

            Thread(target=_play, daemon=True).start()
            logger.info("Voice: RFID not found")
        else:
            self.rescan_card()

    def rfid_error_by_status(self, status_code: Union[int, str]) -> None:
        try:
            code_str = str(int(str(status_code).strip()))
        except (ValueError, TypeError):
            self.rfid_api_error()
            return

        def _play():
            my_id = self._start_multi_play()
            try:
                if not self._is_play_valid(my_id):
                    return
                self._play_error_prefix()
                if not self._is_play_valid(my_id):
                    return
                played = self._play_safe(
                    self._err(f"rfid_{code_str}.wav"), interrupt=False
                )
                if not played and self._is_play_valid(my_id):
                    self._play_safe(self._err("g7.wav"), interrupt=False)
            finally:
                self._end_multi_play()

        Thread(target=_play, daemon=True).start()
        logger.info("Voice: RFID error status=%s", code_str)

    def tech_issue(self) -> None:
        self._play_error_sequence("g9.wav")
        logger.info("Voice: Technical Issue")

    def anpr_error(self) -> None:
        """ANPR mismatch — reuse technical-issue clip (no dedicated ANPR WAV)."""
        self.tech_issue()
        logger.info("Voice: ANPR error")

    def check_weighbridge(self) -> None:
        self._play_error_sequence("weighbridge_0.wav")
        logger.info("Voice: Check Weighbridge")

    def tare_weight_error(self, error_code: int) -> None:
        self._play_error_sequence(f"t{error_code}.wav")
        logger.info("Voice: Tare Weight Error T%s", error_code)

    def weight_submit_error_by_status(self, status_code: Union[int, str]) -> None:
        try:
            code_str = str(int(str(status_code).strip()))
        except (ValueError, TypeError):
            self.tech_issue()
            return

        def _play():
            my_id = self._start_multi_play()
            try:
                if not self._is_play_valid(my_id):
                    return
                self._play_error_prefix()
                if not self._is_play_valid(my_id):
                    return
                played = self._play_safe(
                    self._err(f"weight_submit_{code_str}.wav"), interrupt=False
                )
                if not played and self._is_play_valid(my_id):
                    self._play_safe(self._err("g9.wav"), interrupt=False)
            finally:
                self._end_multi_play()

        Thread(target=_play, daemon=True).start()
        logger.info("Voice: Weight submit error status=%s", code_str)

    # ------------------------------------------------------------------
    # Weight / vehicle number
    # ------------------------------------------------------------------
    def speak_weight(self, weight_type: str, weight_data) -> None:
        """
        Announce weight. weight_type: "t" (tare) or "g" (gross).
        Sequence: type intro → Siren → tons → kg (if > 0).
        """
        try:
            weight_type = str(weight_type).lower()
            weight_data = int(float(weight_data))
        except (ValueError, TypeError) as e:
            logger.error("Invalid weight for speak_weight: %s (%s)", weight_data, e)
            return

        weight_ton = str(weight_data // 1000)
        weight_kg = str(weight_data % 1000)

        def _play():
            my_id = self._start_multi_play()
            try:
                intro = (
                    "tare_final_weight.wav"
                    if weight_type == "t"
                    else "filled_final_weight.wav"
                )
                if not self._is_play_valid(my_id):
                    return
                self._play_safe(self._info(intro), interrupt=False)
                if not self._is_play_valid(my_id):
                    return
                self._play_safe(
                    os.path.join(self.voice_dir, "weight_ton", "Siren.wav"),
                    interrupt=False,
                )
                if not self._is_play_valid(my_id):
                    return
                self._play_safe(
                    os.path.join(self.voice_dir, "weight_ton", f"{weight_ton}.wav"),
                    interrupt=False,
                )
                if int(weight_kg) > 0:
                    if not self._is_play_valid(my_id):
                        return
                    self._play_safe(
                        os.path.join(self.voice_dir, "weight_kg", f"{weight_kg}.wav"),
                        interrupt=False,
                    )
            finally:
                self._end_multi_play()

        Thread(target=_play, daemon=True).start()
        logger.info(
            "Voice: Weight %s — %s t %s kg",
            weight_type.upper(),
            weight_ton,
            weight_kg,
        )

    def vehicle_number(self, vehicle_number: str) -> None:
        if not vehicle_number:
            return

        def _play():
            my_id = self._start_multi_play()
            try:
                for char in str(vehicle_number).upper():
                    if not self._is_play_valid(my_id):
                        return
                    self._play_safe(
                        os.path.join(self.voice_dir, "VNO", f"{char}.wav"),
                        interrupt=False,
                    )
                    time.sleep(0.1)
            finally:
                self._end_multi_play()

        Thread(target=_play, daemon=True).start()
        logger.info("Voice: Vehicle Number %s", vehicle_number)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def is_playing(self) -> bool:
        return self._currently_playing

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def is_enabled(self) -> bool:
        return self._enabled

    def get_status(self) -> dict:
        return {
            "voice_directory": self.voice_dir,
            "enabled": self._enabled,
            "currently_playing": self._currently_playing,
            "multi_play_active": self._multi_play_active,
            "directory_exists": os.path.isdir(self.voice_dir),
            "error_prefix": self.error_prefix,
            "platform": _SYSTEM,
            "audio_backend": AUDIO_BACKEND,
            "audio_available": AUDIO_AVAILABLE,
            "winsound": WINSOUND_AVAILABLE,
        }


def resolve_voice_directory(
    app_root: str,
    configured: str = "voice",
    extra_candidates: Optional[list] = None,
) -> str:
    """
    Pick first existing voice pack directory.

    Order: absolute configured → app_root/configured → app_root/voice →
    app_root/static/voice → extra_candidates.
    """
    candidates = []
    if configured and os.path.isabs(configured):
        candidates.append(configured)
    elif configured:
        candidates.append(os.path.join(app_root, configured))
    candidates.extend(
        [
            os.path.join(app_root, "voice"),
            os.path.join(app_root, "static", "voice"),
        ]
    )
    if extra_candidates:
        candidates.extend(extra_candidates)

    seen = set()
    for path in candidates:
        norm = os.path.normpath(path)
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isdir(norm):
            return norm
    return os.path.normpath(candidates[0] if candidates else os.path.join(app_root, "voice"))


# Backwards-compatible alias
Voice = VoiceService
