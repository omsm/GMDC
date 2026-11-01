"""Idle-triggered FTP photo upload for Mines-Checkpoint."""

from __future__ import annotations

import logging
from pathlib import Path

from gmdc_common.services.ftp_image_upload import (
    FtpUploadConfig,
    schedule_idle_image_upload,
)

logger = logging.getLogger("mines_checkpoint.ftp_upload")

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"
DEFAULT_REMOTE_DIR = "/Mines-Checkpoint"


def start_idle_ftp_upload(settings=None) -> bool:
    """
    Launch the FTP upload application in the background when Checkpoint enters IDLE.

    Uploads everything under ``images/`` (including per-lane folders such as
    ``images/mines_entry/``). Remote folder defaults to ``/Mines-Checkpoint``.
    """
    enabled = True
    remote = DEFAULT_REMOTE_DIR
    if settings is not None:
        enabled = bool(getattr(settings, "ftp_enabled", True))
        remote = str(
            getattr(settings, "ftp_remote_dir", None) or DEFAULT_REMOTE_DIR
        ).strip() or DEFAULT_REMOTE_DIR
    if not enabled:
        logger.debug("FTP upload disabled in settings")
        return False
    cfg = FtpUploadConfig.from_env(remote_dir=remote)
    if settings is not None:
        host = str(getattr(settings, "ftp_host", "") or "").strip()
        user = str(getattr(settings, "ftp_user", "") or "").strip()
        password = getattr(settings, "ftp_password", None)
        port = int(getattr(settings, "ftp_port", 0) or 0)
        cfg = FtpUploadConfig(
            host=host or cfg.host,
            port=port or cfg.port,
            username=user or cfg.username,
            password=cfg.password if password is None else str(password),
            remote_dir=remote,
            enabled=True,
            timeout_sec=float(
                getattr(settings, "ftp_timeout_sec", cfg.timeout_sec) or cfg.timeout_sec
            ),
            delete_after_upload=bool(
                getattr(settings, "ftp_delete_after_upload", cfg.delete_after_upload)
            ),
        )
    ok = schedule_idle_image_upload(
        IMAGES_DIR,
        cfg,
        remote_dir=remote,
        use_subprocess=True,
    )
    if ok:
        logger.info("IDLE FTP upload scheduled dir=%s remote=%s", IMAGES_DIR, remote)
    return ok
