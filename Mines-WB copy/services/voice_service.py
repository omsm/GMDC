"""Re-export shared voice service from gmdc_common."""

from gmdc_common.services.voice_service import (  # noqa: F401
    Voice,
    VoiceService,
    resolve_voice_directory,
)

__all__ = ["Voice", "VoiceService", "resolve_voice_directory"]
