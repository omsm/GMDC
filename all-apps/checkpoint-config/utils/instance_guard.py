"""
Single-instance replacement guard for Windows.

Goal: when a new copy of the SAME executable starts, terminate the previous
copy (releasing COM ports / sockets / file handles) before the new copy opens
any hardware, then continue launching.

Design notes
------------
* NO third-party dependency. Everything uses the Windows API through ctypes,
  so it works reliably inside a frozen one-file PyInstaller EXE (where extra
  pip packages such as psutil are frequently NOT bundled).
* Two complementary detection methods:
    1. PID lock file  -> exact PID recorded by the previous instance.
    2. Image-path scan (CreateToolhelp32Snapshot) -> catches the one-file
       PyInstaller helper/child processes that share the same .exe path.
* Termination sequence:
    detect -> graceful (named event) -> wait -> force TerminateProcess -> COM settle.
* weighbridge-app.exe and configuration.exe use different `instance_key`
  values, so they never terminate each other.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Dict, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# Tunables (seconds)
# ---------------------------------------------------------------------------
GRACEFUL_SHUTDOWN_TIMEOUT_S = 5.0   # wait for the old instance to exit on its own
FORCE_KILL_WAIT_S = 3.0             # wait after TerminateProcess
POST_EXIT_SETTLE_S = 1.5            # let the OS release COM ports before hardware init

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------
_TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE_VALUE = -1
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_TERMINATE = 0x0001
_SYNCHRONIZE = 0x00100000
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_ERROR_ALREADY_EXISTS = 183
_STILL_ACTIVE = 259

_listener_stop = threading.Event()
_listener_thread: Optional[threading.Thread] = None
_mutex_handle = None  # keep the runtime mutex handle alive for the process lifetime


# ===========================================================================
# Logging helpers
# ===========================================================================
def _get_logger(logger_name: str = "instance_guard") -> logging.Logger:
    """Return a logger; fall back to basicConfig only if nothing is configured yet."""
    log = logging.getLogger(logger_name)
    if not logging.getLogger().handlers and not log.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        )
    return log


def should_skip_instance_guard(argv: Optional[Sequence[str]] = None) -> bool:
    """
    Skip replacement for the detached self-update workers, which deliberately
    re-launch the same EXE and must not kill the parent/sibling worker.
    """
    args = list(argv or sys.argv)
    skip_flags = ("--wb-update-worker", "--iot-update-worker")
    return any(flag in args for flag in skip_flags)


# ===========================================================================
# Win32 process helpers (ctypes only)
# ===========================================================================
def _is_windows() -> bool:
    return sys.platform == "win32"


def _kernel32():
    if not _is_windows():
        return None
    import ctypes

    return ctypes.windll.kernel32


def _normalize_path(path: Optional[str]) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return os.path.normcase(path)


def _self_image_path() -> str:
    """Full path of THIS application binary (the .exe when frozen)."""
    if getattr(sys, "frozen", False):
        return _normalize_path(sys.executable)
    return _normalize_path(os.path.abspath(sys.argv[0]))


def _query_image_path(pid: int) -> str:
    """Full image path of a PID, or '' if it cannot be opened/queried."""
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    if k32 is None:
        return ""
    handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        QueryFullProcessImageNameW = k32.QueryFullProcessImageNameW
        QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        QueryFullProcessImageNameW.restype = wintypes.BOOL
        if QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return _normalize_path(buf.value)
        return ""
    finally:
        k32.CloseHandle(handle)


def _snapshot_processes() -> List[Tuple[int, int, str]]:
    """
    Return [(pid, parent_pid, exe_name_lower), ...] for all processes via the
    ToolHelp snapshot API.
    """
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    if k32 is None:
        return []

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    snapshot = k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot == _INVALID_HANDLE_VALUE:
        return []

    results: List[Tuple[int, int, str]] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not k32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return []
        while True:
            results.append(
                (
                    int(entry.th32ProcessID),
                    int(entry.th32ParentProcessID),
                    str(entry.szExeFile).lower(),
                )
            )
            if not k32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        k32.CloseHandle(snapshot)
    return results


def _self_and_ancestor_pids() -> Set[int]:
    """
    PIDs that belong to THIS instance's own process tree (self + parents).
    Excluding these prevents the new instance from killing its own one-file
    PyInstaller bootloader parent.
    """
    own = os.getpid()
    pids: Set[int] = {own}
    parent_map: Dict[int, int] = {}
    for pid, ppid, _name in _snapshot_processes():
        parent_map[pid] = ppid
    cur = own
    # Walk up the parent chain (bounded to avoid cycles).
    for _ in range(16):
        ppid = parent_map.get(cur)
        if not ppid or ppid in pids:
            break
        pids.add(ppid)
        cur = ppid
    return pids


def _process_is_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    if k32 is None or pid <= 0:
        return False
    handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if k32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return exit_code.value == _STILL_ACTIVE
        return False
    finally:
        k32.CloseHandle(handle)


def _wait_for_pid_exit(pid: int, timeout_s: float) -> bool:
    """Block up to timeout_s for the PID to exit. Returns True if it exited."""
    k32 = _kernel32()
    if k32 is None:
        return True
    handle = k32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        # Cannot open for sync -> assume already gone (or inaccessible).
        return not _process_is_alive(pid)
    try:
        ms = int(max(0.0, timeout_s) * 1000)
        rc = k32.WaitForSingleObject(handle, ms)
        return rc == _WAIT_OBJECT_0
    finally:
        k32.CloseHandle(handle)


def _terminate_pid(pid: int, logger: logging.Logger) -> None:
    """Force-terminate a PID and wait briefly for it to disappear."""
    k32 = _kernel32()
    if k32 is None:
        return
    handle = k32.OpenProcess(_PROCESS_TERMINATE, False, pid)
    if not handle:
        return
    try:
        if k32.TerminateProcess(handle, 1):
            logger.warning("Timeout reached, force kill executed (PID %s)", pid)
        else:
            logger.error("TerminateProcess failed for PID %s", pid)
    finally:
        k32.CloseHandle(handle)
    _wait_for_pid_exit(pid, FORCE_KILL_WAIT_S)


# ===========================================================================
# PID lock file
# ===========================================================================
def _app_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pid_file_path(instance_key: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in instance_key)
    return os.path.join(_app_base_dir(), f".{safe}.pid")


def _read_pid_file(instance_key: str) -> Optional[int]:
    path = _pid_file_path(instance_key)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return int((fh.read() or "").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _write_pid_file(instance_key: str) -> None:
    path = _pid_file_path(instance_key)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass


# ===========================================================================
# Named-event graceful shutdown channel
# ===========================================================================
def _shutdown_event_name(instance_key: str) -> str:
    # Local\ namespace -> per-session; both instances are launched by the same
    # operator session, so no Global\ privilege is required.
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in instance_key)
    return f"Local\\E_Rawanna_IoT_{safe}_Shutdown"


def _mutex_name(instance_key: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in instance_key)
    return f"Local\\E_Rawanna_IoT_{safe}_Mutex"


def signal_graceful_shutdown(instance_key: str, logger: logging.Logger) -> bool:
    """Pulse the named event so the running instance can shut down cleanly."""
    k32 = _kernel32()
    if k32 is None:
        return False
    name = _shutdown_event_name(instance_key)
    handle = k32.OpenEventW(_EVENT_MODIFY_STATE | _SYNCHRONIZE, False, name)
    if not handle:
        logger.info("No graceful-shutdown listener present (event not found)")
        return False
    try:
        if k32.SetEvent(handle):
            logger.info("Shutdown request sent via named event")
            return True
        logger.warning("Failed to set shutdown event")
        return False
    finally:
        k32.CloseHandle(handle)


# ===========================================================================
# Detection
# ===========================================================================
def find_prior_instance_pids(instance_key: str, logger: logging.Logger) -> List[int]:
    """
    Detect prior instances of THIS application:
      * PID from the lock file (if still alive), plus
      * any process whose image path equals ours (one-file parent + child),
    excluding our own process tree.
    """
    own_tree = _self_and_ancestor_pids()
    our_image = _self_image_path()
    found: Set[int] = set()

    # 1) PID lock file (exact, works in dev + frozen)
    lock_pid = _read_pid_file(instance_key)
    if lock_pid and lock_pid not in own_tree and _process_is_alive(lock_pid):
        # In frozen mode, verify the image path matches to avoid PID reuse hits.
        if not getattr(sys, "frozen", False) or _query_image_path(lock_pid) == our_image:
            found.add(lock_pid)

    # 2) Image-path scan (frozen only; in dev sys.executable is python.exe and
    #    would match unrelated python processes, so we rely on the lock file).
    if getattr(sys, "frozen", False) and our_image:
        own_exe_name = os.path.basename(our_image)
        for pid, _ppid, exe_name in _snapshot_processes():
            if pid in own_tree:
                continue
            # Cheap filter by exe file name before the OpenProcess query.
            if exe_name != own_exe_name:
                continue
            if _query_image_path(pid) == our_image:
                found.add(pid)

    pids = sorted(found)
    for pid in pids:
        logger.warning("Existing instance detected (PID %s, image=%s)", pid, our_image)
    return pids


# ===========================================================================
# Public entry points
# ===========================================================================
def replace_prior_instances(instance_key: str, logger_name: str = "instance_guard") -> int:
    """
    Startup sequencing (call BEFORE opening any COM port or socket):
      detect -> graceful signal -> wait -> force terminate -> COM settle.
    Records this process's PID in the lock file afterwards.
    Returns the count of prior instances that were replaced.
    """
    log = _get_logger(logger_name)

    if not _is_windows():
        log.info("Instance guard: non-Windows platform, skipping")
        _write_pid_file(instance_key)
        return 0

    prior = find_prior_instance_pids(instance_key, log)
    if not prior:
        log.info("No prior instance found - starting new instance (key=%s)", instance_key)
        _write_pid_file(instance_key)
        return 0

    # Ask the old instance to shut down gracefully (closes COM ports in its own
    # shutdown handler), then wait for the whole prior set to exit.
    signal_graceful_shutdown(instance_key, log)

    deadline = time.monotonic() + GRACEFUL_SHUTDOWN_TIMEOUT_S
    for pid in prior:
        remaining = max(0.0, deadline - time.monotonic())
        if _wait_for_pid_exit(pid, remaining):
            log.info("Process terminated successfully (PID %s)", pid)

    # Force-terminate anything still alive after the grace period.
    replaced = 0
    for pid in prior:
        if _process_is_alive(pid):
            _terminate_pid(pid, log)
        if not _process_is_alive(pid):
            replaced += 1

    if replaced and POST_EXIT_SETTLE_S > 0:
        log.info(
            "Waiting %.1fs for COM ports / handles to be released...",
            POST_EXIT_SETTLE_S,
        )
        time.sleep(POST_EXIT_SETTLE_S)

    _write_pid_file(instance_key)
    log.info("New instance started (replaced %s prior instance(s))", replaced)
    return replaced


def register_shutdown_listener(
    instance_key: str,
    on_shutdown,
    logger_name: str = "instance_guard",
) -> None:
    """
    Run a background thread that waits on the named shutdown event. When a newer
    instance signals it, `on_shutdown()` is invoked so this instance can release
    COM ports and exit gracefully.
    """
    global _listener_thread

    log = _get_logger(logger_name)
    k32 = _kernel32()
    if k32 is None:
        return
    if _listener_thread and _listener_thread.is_alive():
        return

    name = _shutdown_event_name(instance_key)
    _listener_stop.clear()

    def _listen() -> None:
        # Manual-reset event, initially non-signaled.
        handle = k32.CreateEventW(None, True, False, name)
        if not handle:
            log.error("Could not create shutdown event listener")
            return
        log.info("Shutdown listener active")
        try:
            while not _listener_stop.is_set():
                rc = k32.WaitForSingleObject(handle, 500)
                if rc == _WAIT_OBJECT_0:
                    log.info("Shutdown request received - starting graceful exit")
                    try:
                        on_shutdown()
                    except Exception as exc:  # pragma: no cover
                        log.error("Graceful shutdown callback error: %s", exc)
                    break
        finally:
            k32.CloseHandle(handle)

    _listener_thread = threading.Thread(
        target=_listen, name="InstanceShutdownListener", daemon=True
    )
    _listener_thread.start()


def acquire_runtime_mutex(instance_key: str, logger_name: str = "instance_guard") -> bool:
    """Create/hold a named mutex marking this instance as the live owner."""
    global _mutex_handle

    k32 = _kernel32()
    if k32 is None:
        return True
    log = _get_logger(logger_name)
    name = _mutex_name(instance_key)
    handle = k32.CreateMutexW(None, False, name)
    if not handle:
        log.warning("Could not create application mutex")
        return False
    _mutex_handle = handle  # keep alive for process lifetime
    if k32.GetLastError() == _ERROR_ALREADY_EXISTS:
        log.debug("Application mutex already existed (handoff in progress)")
    return True


def stop_shutdown_listener() -> None:
    """Stop the background shutdown listener (e.g. for tests)."""
    _listener_stop.set()
