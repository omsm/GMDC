"""Background FTP upload of yard camera photos.

Separate helper used only by Mines-WB and Mines-Checkpoint:

  On IDLE (app start or after a transaction), the runtime launches this
  uploader in the background. It walks ``images/`` (including lane
  subfolders), STOR each image to the FTP server, then deletes the local
  file after a successful transfer so the next IDLE only sends new photos.

CLI (same code path the apps spawn)::

  python -m gmdc_common.services.ftp_image_upload \\
      --images-dir /path/to/Mines-WB/images \\
      --remote-dir /Mines-WB
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from ftplib import FTP, error_perm
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

logger = logging.getLogger("gmdc_common.services.ftp_image_upload")

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}

# One in-flight upload per absolute images directory (thread or process).
_locks_guard = threading.Lock()
_dir_locks: dict[str, threading.Lock] = {}
_spawned_procs: dict[str, subprocess.Popen] = {}


def _lock_path(images_dir: Path) -> Path:
    return Path(images_dir) / ".ftp_upload.lock"


def _try_acquire_file_lock(images_dir: Path) -> Optional[object]:
    """
    Cross-process lock so multi-lane IDLE does not start several FTP apps.

    Returns an open file handle to keep (caller must close to release), or None.
    """
    root = Path(images_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    path = _lock_path(root)
    handle = None
    try:
        handle = open(path, "a+b")
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                handle.close()
                return None
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()).encode("ascii", errors="ignore"))
            handle.flush()
            return handle
        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("ascii", errors="ignore"))
        handle.flush()
        return handle
    except Exception as exc:
        logger.debug("FTP file lock unavailable: %s", exc)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        return None


def _release_file_lock(handle: Optional[object]) -> None:
    if handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            handle.close()
        except Exception:
            pass


@dataclass(frozen=True)
class FtpUploadConfig:
    host: str
    username: str
    password: str
    port: int = 21
    remote_dir: str = "/"
    enabled: bool = True
    timeout_sec: float = 30.0
    delete_after_upload: bool = True

    @classmethod
    def from_env(
        cls,
        *,
        remote_dir: str = "/",
        default_host: str = "10.80.118.100",
        default_user: str = "ftpclient",
        default_password: str = "GmDC@$2k26",
    ) -> "FtpUploadConfig":
        enabled_raw = str(os.getenv("FTP_ENABLED", "true")).strip().lower()
        enabled = enabled_raw in ("1", "true", "yes", "on")
        port_raw = str(os.getenv("FTP_PORT") or "21").strip()
        try:
            port = int(port_raw) if port_raw else 21
        except ValueError:
            port = 21
        timeout_raw = str(os.getenv("FTP_TIMEOUT_SEC") or "30").strip()
        try:
            timeout_sec = float(timeout_raw) if timeout_raw else 30.0
        except ValueError:
            timeout_sec = 30.0
        delete_raw = str(os.getenv("FTP_DELETE_AFTER_UPLOAD", "true")).strip().lower()
        delete_after = delete_raw in ("1", "true", "yes", "on")
        remote = str(
            os.getenv("FTP_REMOTE_DIR") or remote_dir or "/"
        ).strip() or "/"
        return cls(
            host=str(os.getenv("FTP_HOST") or default_host).strip() or default_host,
            port=port if port > 0 else 21,
            username=str(os.getenv("FTP_USER") or default_user).strip() or default_user,
            password=str(
                os.getenv("FTP_PASSWORD")
                if os.getenv("FTP_PASSWORD") is not None
                else default_password
            ),
            remote_dir=remote,
            enabled=enabled,
            timeout_sec=timeout_sec,
            delete_after_upload=delete_after,
        )


def _dir_lock(images_dir: Path) -> threading.Lock:
    key = str(images_dir.resolve())
    with _locks_guard:
        lock = _dir_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _dir_locks[key] = lock
        return lock


def iter_image_files(images_dir: Path) -> List[Path]:
    """All image files under ``images_dir`` (recursive), stable order."""
    root = Path(images_dir)
    if not root.is_dir():
        return []
    files: List[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        files.append(path)
    return files


def _ftp_makedirs(ftp: FTP, remote_dir: str) -> None:
    """Ensure absolute or relative remote directory exists (cwd ends there)."""
    remote = str(remote_dir or "/").replace("\\", "/").strip()
    if not remote or remote == "/":
        ftp.cwd("/")
        return
    parts = [p for p in remote.split("/") if p]
    if remote.startswith("/"):
        ftp.cwd("/")
    for part in parts:
        try:
            ftp.cwd(part)
        except error_perm:
            try:
                ftp.mkd(part)
            except error_perm as exc:
                # Race: another uploader created it
                logger.debug("FTP mkd %s: %s", part, exc)
            ftp.cwd(part)


def upload_images(
    images_dir: Path,
    config: FtpUploadConfig,
) -> Tuple[int, int]:
    """
    Upload every image under ``images_dir`` to FTP.

    Remote layout mirrors relative paths under ``config.remote_dir``.
    Returns ``(uploaded_ok, failed)``.
    """
    root = Path(images_dir)
    files = iter_image_files(root)
    if not files:
        logger.info("FTP upload: no images in %s", root)
        return (0, 0)
    if not config.enabled:
        logger.info("FTP upload disabled - skip %s file(s)", len(files))
        return (0, 0)
    if not config.host or not config.username:
        logger.warning("FTP upload missing host/user - skip")
        return (0, len(files))

    ok = 0
    failed = 0
    ftp: Optional[FTP] = None
    try:
        ftp = FTP()
        ftp.connect(config.host, int(config.port), timeout=float(config.timeout_sec))
        ftp.login(config.username, config.password)
        try:
            ftp.set_pasv(True)
        except Exception:
            pass
        logger.info(
            "FTP connected %s:%s user=%s files=%s remote=%s",
            config.host,
            config.port,
            config.username,
            len(files),
            config.remote_dir,
        )
        for path in files:
            rel = path.relative_to(root).as_posix()
            remote_parent = str(Path(config.remote_dir) / Path(rel).parent).replace(
                "\\", "/"
            )
            if not remote_parent.startswith("/"):
                remote_parent = "/" + remote_parent
            try:
                _ftp_makedirs(ftp, remote_parent)
                with path.open("rb") as handle:
                    ftp.storbinary(f"STOR {path.name}", handle)
                ok += 1
                logger.info("FTP uploaded %s -> %s/%s", rel, remote_parent.rstrip("/"), path.name)
                if config.delete_after_upload:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning("FTP local delete failed %s: %s", path, exc)
            except Exception as exc:
                failed += 1
                logger.error("FTP upload failed %s: %s", rel, exc)
    except Exception as exc:
        failed = max(failed, len(files) - ok)
        logger.error("FTP session failed host=%s: %s", config.host, exc)
    finally:
        if ftp is not None:
            try:
                ftp.quit()
            except Exception:
                try:
                    ftp.close()
                except Exception:
                    pass
    logger.info("FTP upload done ok=%s failed=%s dir=%s", ok, failed, root)
    return (ok, failed)


def upload_images_locked(images_dir: Path, config: FtpUploadConfig) -> Tuple[int, int]:
    """Same as ``upload_images`` but skips if another upload holds the dir lock."""
    root = Path(images_dir)
    lock = _dir_lock(root)
    if not lock.acquire(blocking=False):
        logger.info("FTP upload already running for %s - skip", root)
        return (0, 0)
    file_lock = _try_acquire_file_lock(root)
    if file_lock is None:
        # Another process holds the lock (or lock unavailable after contention).
        # Brief retry once for slow starters.
        time.sleep(0.2)
        file_lock = _try_acquire_file_lock(root)
        if file_lock is None:
            lock.release()
            logger.info("FTP upload file-lock busy for %s - skip", root)
            return (0, 0)
    try:
        return upload_images(root, config)
    finally:
        _release_file_lock(file_lock)
        lock.release()


def schedule_idle_image_upload(
    images_dir: Path,
    config: Optional[FtpUploadConfig] = None,
    *,
    remote_dir: str = "/",
    use_subprocess: bool = True,
) -> bool:
    """
    Start background photo upload when the yard app enters IDLE.

    Default: spawn a detached Python process running this module (separate
    "FTP upload application"). Falls back to a daemon thread if spawn fails.
    """
    root = Path(images_dir)
    cfg = config or FtpUploadConfig.from_env(remote_dir=remote_dir)
    if not cfg.enabled:
        logger.debug("FTP upload disabled")
        return False
    if not iter_image_files(root):
        logger.debug("FTP upload: nothing to send under %s", root)
        return False

    key = str(root.resolve())
    with _locks_guard:
        proc = _spawned_procs.get(key)
        if proc is not None and proc.poll() is None:
            logger.info("FTP upload process still running for %s - skip", root)
            return False

    if use_subprocess:
        try:
            env = os.environ.copy()
            env["FTP_HOST"] = cfg.host
            env["FTP_PORT"] = str(cfg.port)
            env["FTP_USER"] = cfg.username
            env["FTP_PASSWORD"] = cfg.password
            env["FTP_REMOTE_DIR"] = cfg.remote_dir
            env["FTP_ENABLED"] = "true"
            env["FTP_DELETE_AFTER_UPLOAD"] = (
                "true" if cfg.delete_after_upload else "false"
            )
            env["FTP_TIMEOUT_SEC"] = str(cfg.timeout_sec)
            cmd = [
                sys.executable,
                "-m",
                "gmdc_common.services.ftp_image_upload",
                "--images-dir",
                str(root),
                "--remote-dir",
                cfg.remote_dir,
            ]
            # Detach so IDLE path returns immediately.
            kwargs = {
                "env": env,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
            }
            if os.name == "nt":
                kwargs["creationflags"] = (
                    getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            else:
                kwargs["start_new_session"] = True
            child = subprocess.Popen(cmd, **kwargs)
            with _locks_guard:
                _spawned_procs[key] = child
            logger.info(
                "FTP upload app started pid=%s dir=%s remote=%s",
                child.pid,
                root,
                cfg.remote_dir,
            )
            return True
        except Exception as exc:
            logger.warning(
                "FTP subprocess spawn failed (%s) - using background thread",
                exc,
            )

    def _run() -> None:
        upload_images_locked(root, cfg)

    threading.Thread(
        target=_run,
        name=f"ftp-upload-{root.name}",
        daemon=True,
    ).start()
    logger.info("FTP upload thread scheduled dir=%s remote=%s", root, cfg.remote_dir)
    return True


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload Mines-WB / Mines-Checkpoint images/ to the FTP server."
    )
    parser.add_argument(
        "--images-dir",
        required=True,
        help="Local images directory (e.g. Mines-WB/images)",
    )
    parser.add_argument(
        "--remote-dir",
        default="",
        help="Remote FTP folder (default: FTP_REMOTE_DIR or /)",
    )
    parser.add_argument(
        "--host",
        default="",
        help="Override FTP_HOST",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Override FTP_PORT",
    )
    parser.add_argument(
        "--user",
        default="",
        help="Override FTP_USER",
    )
    parser.add_argument(
        "--password",
        default="",
        help="Override FTP_PASSWORD",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [ftp_upload] %(message)s",
    )
    remote = str(args.remote_dir or "").strip()
    cfg = FtpUploadConfig.from_env(remote_dir=remote or "/")
    if args.host:
        cfg = FtpUploadConfig(
            host=args.host,
            port=args.port or cfg.port,
            username=args.user or cfg.username,
            password=args.password if args.password else cfg.password,
            remote_dir=remote or cfg.remote_dir,
            enabled=True,
            timeout_sec=cfg.timeout_sec,
            delete_after_upload=cfg.delete_after_upload,
        )
    elif args.user or args.password or args.port:
        cfg = FtpUploadConfig(
            host=cfg.host,
            port=args.port or cfg.port,
            username=args.user or cfg.username,
            password=args.password if args.password else cfg.password,
            remote_dir=remote or cfg.remote_dir,
            enabled=True,
            timeout_sec=cfg.timeout_sec,
            delete_after_upload=cfg.delete_after_upload,
        )
    elif remote:
        cfg = FtpUploadConfig(
            host=cfg.host,
            port=cfg.port,
            username=cfg.username,
            password=cfg.password,
            remote_dir=remote,
            enabled=cfg.enabled,
            timeout_sec=cfg.timeout_sec,
            delete_after_upload=cfg.delete_after_upload,
        )

    ok, failed = upload_images_locked(Path(args.images_dir), cfg)
    if failed and not ok:
        return 2
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
