"""
Auto-updater service for IoT-Configuration.

Checks GitHub releases, exposes update status/progress, and launches a detached
worker that performs backup + replace in install directory.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import requests


def _worker_log(msg: str, log_file: str) -> None:
    line = f"{datetime.now().isoformat()} {msg}"
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    except Exception:
        pass
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        try:
            alt = os.path.join(tempfile.gettempdir(), "iot-update-worker.log")
            with open(alt, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def _iot_find_best_source_root(extract_dir: str, target_exe: str) -> str:
    best_root = None
    best_score = -1
    for root, _dirs, files in os.walk(extract_dir):
        files_l = {f.lower() for f in files}
        score = 0
        if str(target_exe or "").lower() in files_l:
            score += 100
        if "configuration.exe" in files_l:
            score += 60
        if "weighbridge-app.exe" in files_l:
            score += 30
        if "erawanna-demo.exe" in files_l:
            score += 20
        if "iot_configuration.json" in files_l:
            score += 10
        if score > best_score:
            best_score = score
            best_root = root
    if best_root and best_score > 0:
        return best_root
    root_items = os.listdir(extract_dir)
    if len(root_items) == 1:
        candidate = os.path.join(extract_dir, root_items[0])
        if os.path.isdir(candidate):
            return candidate
    return extract_dir


def run_update_worker_main(cfg_path: str) -> None:
    """
    Invoked as: configuration.exe --iot-update-worker <cfg.json>
    See Weighbridge updater - same fix for PyInstaller (cannot run temp .py via frozen exe).
    """
    import ctypes
    import traceback
    import zipfile

    log_file = os.path.join(tempfile.gettempdir(), "iot-update-worker.log")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        bd = str(cfg.get("backup_dir") or "")
        if bd:
            log_file = os.path.join(bd, "iot-update-worker.log")
    except Exception as e:
        _worker_log(f"cannot read cfg {cfg_path!r}: {e}", log_file)
        raise

    _worker_log("=== worker start ===", log_file)
    _worker_log(f"argv exe={sys.executable!r} frozen={getattr(sys, 'frozen', False)} cfg={cfg_path!r}", log_file)

    try:
        parent_pid = int(cfg["parent_pid"])
        install_dir = str(cfg["install_dir"])
        backup_dir = str(cfg["backup_dir"])
        downloaded_zip = str(cfg["downloaded_zip"])
        target_exe = str(cfg["target_exe"])
        keep_file = "iot_configuration.json"
        log_file = os.path.join(backup_dir, "iot-update-worker.log")
        _worker_log(
            f"parent_pid={parent_pid} install_dir={install_dir!r} zip={downloaded_zip!r} target_exe={target_exe!r}",
            log_file,
        )

        def is_process_running(pid: int) -> bool:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False

        def remove_path(p: str) -> None:
            if not os.path.exists(p):
                return
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except Exception:
                    pass

        def _is_permission_denied(exc: BaseException) -> bool:
            if isinstance(exc, PermissionError):
                return True
            if isinstance(exc, OSError) and getattr(exc, "errno", None) == 13:
                return True
            return False

        _worker_log("waiting for parent process to exit...", log_file)
        for i in range(120):
            if not is_process_running(parent_pid):
                _worker_log(f"parent exited after {i}s", log_file)
                break
            time.sleep(1)
        else:
            _worker_log("timeout waiting for parent; continuing anyway", log_file)
        time.sleep(1.5)

        if not os.path.isdir(install_dir):
            raise RuntimeError(f"install_dir is not a directory: {install_dir}")
        if not os.path.isfile(downloaded_zip):
            raise RuntimeError(f"downloaded zip missing: {downloaded_zip}")

        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_zip = os.path.join(backup_dir, f"iot-app-{ts}.zip")

        _worker_log(f"writing backup zip {backup_zip!r}", log_file)
        with zipfile.ZipFile(backup_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(install_dir):
                rel_root = os.path.relpath(root, install_dir)
                if rel_root == ".":
                    rel_root = ""
                if rel_root.lower().startswith("iot-update-backup"):
                    continue
                for file_name in files:
                    fp = os.path.join(root, file_name)
                    arc = os.path.relpath(fp, install_dir)
                    zf.write(fp, arc)

        preserved_data = None
        keep_path = os.path.join(install_dir, keep_file)
        if os.path.exists(keep_path):
            with open(keep_path, "rb") as f:
                preserved_data = f.read()
            _worker_log(f"preserved {keep_file} ({len(preserved_data)} bytes)", log_file)

        last_error: Optional[BaseException] = None
        max_attempts = 5
        for attempt in range(max_attempts):
            _worker_log(f"install attempt {attempt + 1}/{max_attempts}: waiting 10s before replace...", log_file)
            time.sleep(10)
            extract_dir = os.path.join(tempfile.gettempdir(), f"iot-update-extract-{ts}-try{attempt}")
            try:
                _worker_log("removing old install files (except backup + config)...", log_file)
                for entry in os.listdir(install_dir):
                    if entry.lower() in ("iot-update-backup", keep_file.lower()):
                        continue
                    remove_path(os.path.join(install_dir, entry))

                remove_path(extract_dir)
                os.makedirs(extract_dir, exist_ok=True)
                _worker_log(f"extracting {downloaded_zip!r} -> {extract_dir!r}", log_file)
                with zipfile.ZipFile(downloaded_zip, "r") as zf:
                    zf.extractall(extract_dir)

                source_root = _iot_find_best_source_root(extract_dir, target_exe)
                _worker_log(f"source_root={source_root!r} contents={os.listdir(source_root)!r}", log_file)

                copied = 0
                for item in os.listdir(source_root):
                    src = os.path.join(source_root, item)
                    dst = os.path.join(install_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                    copied += 1
                _worker_log(f"copied {copied} entries from release", log_file)
                if copied == 0:
                    raise RuntimeError(
                        f"No files copied from release (source_root={source_root!r}). "
                        "Check that the GitHub zip layout matches the installer."
                    )

                if preserved_data is not None:
                    with open(keep_path, "wb") as f:
                        f.write(preserved_data)

                try:
                    remove_path(extract_dir)
                except Exception as ex:
                    _worker_log(f"cleanup extract_dir: {ex}", log_file)

                try:
                    if os.path.exists(downloaded_zip):
                        os.remove(downloaded_zip)
                except Exception as ex:
                    _worker_log(f"remove zip: {ex}", log_file)

                target_path = os.path.join(install_dir, target_exe)
                if os.path.exists(target_path):
                    _worker_log(f"launching {target_path!r}", log_file)
                    subprocess.Popen([target_path], cwd=install_dir)
                else:
                    raise RuntimeError(f"After update, target executable not found: {target_path}")

                _worker_log("=== worker finished OK ===", log_file)
                break
            except Exception as e:
                if _is_permission_denied(e):
                    last_error = e
                    _worker_log(f"attempt {attempt + 1} permission denied (retrying): {e!r}", log_file)
                    try:
                        remove_path(extract_dir)
                    except Exception:
                        pass
                    continue
                raise
        else:
            raise RuntimeError(
                f"Update failed after {max_attempts} attempts (permission denied). Last error: {last_error!r}"
            ) from last_error
    except Exception as e:
        _worker_log(f"FAILED: {e!r}\n{traceback.format_exc()}", log_file)
        raise


class UpdaterService:
    """Handles release checks and update worker launch."""

    def __init__(
        self,
        current_version: str,
        target_exe_name: str,
        repo: str = "omsm/RajMines-Application",
        install_dir: str = r"C:\RajeRawanna\IotConfig",
        check_interval_seconds: int = 120,
    ) -> None:
        self.current_version = str(current_version or "unknown")
        self.target_exe_name = target_exe_name
        self.repo = repo
        self.install_dir = install_dir
        self.backup_dir = os.path.join(self.install_dir, "iot-update-backup")
        self.check_interval_seconds = check_interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._running = False
        self.logger = logging.getLogger("iot_config.updater")

        self._state: Dict[str, Any] = {
            "current_version": self.current_version,
            "latest_version": self.current_version,
            "update_available": False,
            "checking": False,
            "applying": False,
            "last_checked_at": None,
            "last_error": "",
            "release_notes": "",
            "asset_name": "",
            "asset_url": "",
            "progress_step": "idle",
            "progress_percent": 0,
            "progress_message": "Idle",
        }

    @staticmethod
    def _normalize_version(v: str) -> str:
        return str(v or "").strip().lstrip("vV")

    @staticmethod
    def _parse_version(v: str) -> Tuple[int, int, int]:
        parts = UpdaterService._normalize_version(v).split(".")
        nums = []
        for p in parts[:3]:
            try:
                nums.append(int(p))
            except Exception:
                nums.append(0)
        while len(nums) < 3:
            nums.append(0)
        return nums[0], nums[1], nums[2]

    def _is_newer(self, latest: str, current: str) -> bool:
        return self._parse_version(latest) > self._parse_version(current)

    def _set_progress(self, step: str, percent: int, message: str) -> None:
        with self._lock:
            self._state["progress_step"] = step
            self._state["progress_percent"] = int(percent)
            self._state["progress_message"] = message

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def get_progress(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "step": self._state["progress_step"],
                "percent": self._state["progress_percent"],
                "message": self._state["progress_message"],
                "applying": self._state["applying"],
            }

    def start_background_checker(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._background_loop, name="IoTUpdaterCheck", daemon=True)
        self._thread.start()
        # Kick a non-blocking initial check in separate thread.
        threading.Thread(target=self.check_for_updates, kwargs={"force": True}, daemon=True).start()

    def _background_loop(self) -> None:
        while self._running:
            try:
                self.check_for_updates()
            except Exception as e:
                self.logger.error(f"Background update check failed: {e}", exc_info=True)
            for _ in range(max(1, int(self.check_interval_seconds))):
                if not self._running:
                    break
                time.sleep(1)

    def check_for_updates(self, force: bool = False) -> Dict[str, Any]:
        with self._lock:
            if self._state["checking"] and not force:
                return dict(self._state)
            self._state["checking"] = True
            self._state["last_error"] = ""
        self._set_progress("checking", 5, "Checking for updates...")

        try:
            url = f"https://api.github.com/repos/{self.repo}/releases/latest"
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            payload = resp.json()

            latest_version = self._normalize_version(payload.get("tag_name", ""))
            body = payload.get("body", "") or ""
            assets = payload.get("assets", []) or []
            asset_name = ""
            asset_url = ""
            for a in assets:
                name = str(a.get("name", ""))
                dl = str(a.get("browser_download_url", ""))
                if name.lower().endswith(".zip") and dl:
                    asset_name = name
                    asset_url = dl
                    break
            if not asset_url and assets:
                a0 = assets[0]
                asset_name = str(a0.get("name", ""))
                asset_url = str(a0.get("browser_download_url", ""))

            is_available = bool(latest_version) and self._is_newer(latest_version, self.current_version)
            with self._lock:
                self._state["latest_version"] = latest_version or self.current_version
                self._state["update_available"] = is_available
                self._state["release_notes"] = body[:8000]
                self._state["asset_name"] = asset_name
                self._state["asset_url"] = asset_url
                self._state["last_checked_at"] = datetime.now().isoformat()
                self._state["checking"] = False
            self._set_progress("checked", 0, "Update available" if is_available else "Already up to date")
            return self.get_status()
        except Exception as e:
            with self._lock:
                self._state["checking"] = False
                self._state["last_error"] = str(e)
                self._state["last_checked_at"] = datetime.now().isoformat()
            self._set_progress("error", 0, f"Update check failed: {e}")
            return self.get_status()

    def _download_release_asset(self, asset_url: str, asset_name: str) -> str:
        self._set_progress("downloading", 20, "Downloading update package...")
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = asset_name or f"update-{ts}.zip"
        temp_zip = os.path.join(tempfile.gettempdir(), f"iot-update-{ts}-{safe_name}")

        with requests.get(asset_url, timeout=60, stream=True) as r:
            r.raise_for_status()
            with open(temp_zip, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)

        if not os.path.exists(temp_zip) or os.path.getsize(temp_zip) == 0:
            raise RuntimeError("Downloaded update file is missing or empty")
        return temp_zip

    def launch_update_worker(self, parent_pid: int) -> Dict[str, Any]:
        status = self.check_for_updates(force=True)
        if not status.get("update_available"):
            return {"status": 400, "message": "No update available", "data": status}
        asset_url = status.get("asset_url") or ""
        asset_name = status.get("asset_name") or ""
        if not asset_url:
            return {"status": 500, "message": "No downloadable release asset found"}

        with self._lock:
            self._state["applying"] = True
            self._state["last_error"] = ""

        try:
            downloaded_zip = self._download_release_asset(asset_url, asset_name)
            self._set_progress("preparing", 60, "Preparing updater...")

            cfg = {
                "parent_pid": int(parent_pid),
                "install_dir": self.install_dir,
                "backup_dir": self.backup_dir,
                "downloaded_zip": downloaded_zip,
                "target_exe": self.target_exe_name,
            }
            cfg_path = os.path.join(tempfile.gettempdir(), f"iot-update-cfg-{int(time.time())}.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f)

            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

            exe_abs = os.path.abspath(sys.executable)
            inst_abs = os.path.abspath(self.install_dir)
            inst_abs_lower = inst_abs.lower()
            exe_lower = exe_abs.lower()
            use_temp_runner = os.name == "nt" and (
                exe_lower == os.path.join(inst_abs_lower, os.path.basename(exe_lower))
                or exe_lower.startswith(inst_abs_lower + os.sep)
            )
            if use_temp_runner:
                runner_path = os.path.join(
                    tempfile.gettempdir(),
                    f"iot-update-runner-{int(time.time())}.exe",
                )
                shutil.copy2(exe_abs, runner_path)
                worker_exe = runner_path
                self.logger.info("Update worker will run from temp copy: %s", runner_path)
            else:
                worker_exe = exe_abs

            subprocess.Popen(
                [worker_exe, "--iot-update-worker", cfg_path],
                cwd=self.install_dir,
                creationflags=creationflags,
                close_fds=True,
            )
            self._set_progress("worker_started", 80, "Updater started. Application will close.")
            return {"status": 200, "message": "Updater worker started"}
        except Exception as e:
            self.logger.error(f"Failed to start update worker: {e}", exc_info=True)
            with self._lock:
                self._state["last_error"] = str(e)
                self._state["applying"] = False
            self._set_progress("error", 0, f"Update failed: {e}")
            return {"status": 500, "message": f"Failed to start update: {e}"}
