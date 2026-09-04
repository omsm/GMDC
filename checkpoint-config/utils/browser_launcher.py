# UI launcher: pywebview native window, Chrome app mode, or default browser.

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser

logger = logging.getLogger(__name__)

_chrome_process = None
_ui_hwnd = None
_DEFAULT_UI_TITLE_HINTS = (
    "Device Configuration",
    "GMDC Checkpoint Config",
    "127.0.0.1:8080",
    "localhost:8080",
)

VALID_UI_MODES = ("auto", "webview", "chromium_app", "browser")


def build_local_app_url(port):
    """Local URL for the Flask app (loopback avoids some binding issues)."""
    return f"http://127.0.0.1:{port}"


def is_webview2_runtime_available():
    """Return True if Microsoft WebView2 runtime is likely installed (Windows)."""
    if sys.platform != "win32":
        return True

    try:
        import winreg

        client_id = r"{F3017266-B2F3-4270-904F-3127A428CC91}"
        key_paths = [
            (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{client_id}"),
            (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{client_id}"),
            (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{client_id}"),
        ]
        for hive, path in key_paths:
            try:
                with winreg.OpenKey(hive, path):
                    return True
            except OSError:
                continue
    except ImportError:
        pass

    search_roots = []
    for env_key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        value = os.environ.get(env_key)
        if value:
            search_roots.append(os.path.join(value, "Microsoft", "EdgeWebView", "Application"))

    for root in search_roots:
        if not os.path.isdir(root):
            continue
        try:
            for name in os.listdir(root):
                exe = os.path.join(root, name, "msedgewebview2.exe")
                if os.path.isfile(exe):
                    return True
        except OSError:
            continue

    return False


def find_chrome_executable(custom_path=""):
    """Locate Google Chrome executable; empty string if not found."""
    if custom_path and os.path.isfile(custom_path):
        return custom_path

    candidates = []
    for env_key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env_key)
        if base:
            candidates.append(
                os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            )

    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def is_window_visible(title):
    """Return True if a top-level window with the given title is visible (Windows)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if hwnd and user32.IsWindowVisible(hwnd):
            return True
    except Exception:
        pass
    return False


def wait_for_webview_window(title, timeout_sec):
    """Poll until a window with title is visible or timeout expires. Returns True if visible."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if is_window_visible(title):
            return True
        time.sleep(0.5)
    return False


def _get_primary_screen_size():
    """Return (width, height) of the primary display, or (1920, 1080) fallback."""
    if sys.platform != "win32":
        return 1920, 1080
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        return 1920, 1080


def _get_work_area():
    """
    Return (left, top, width, height) for the primary monitor work area
    (excludes taskbar). Falls back to full screen metrics.
    """
    if sys.platform != "win32":
        w, h = _get_primary_screen_size()
        return 0, 0, w, h
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        rect = wintypes.RECT()
        SPI_GETWORKAREA = 0x0030
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            left = int(rect.left)
            top = int(rect.top)
            width = max(800, int(rect.right - rect.left))
            height = max(600, int(rect.bottom - rect.top))
            return left, top, width, height
    except Exception:
        pass
    w, h = _get_primary_screen_size()
    return 0, 0, w, h


def _force_hwnd_fit_screen(hwnd):
    """Maximize / size a Win32 window to fit the primary work area (fit to screen)."""
    import ctypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    SW_MAXIMIZE = 3
    SWP_SHOWWINDOW = 0x0040
    HWND_TOP = 0

    left, top, width, height = _get_work_area()
    # Restore first so SetWindowPos applies, then maximize to fit screen
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(
        hwnd,
        HWND_TOP,
        left,
        top,
        width,
        height,
        SWP_SHOWWINDOW,
    )
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    user32.SetForegroundWindow(hwnd)


def _force_hwnd_fullscreen(hwnd):
    """Stretch a Win32 window to cover the primary screen (borderless fullscreen)."""
    global _ui_hwnd
    import ctypes

    user32 = ctypes.windll.user32
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_SYSMENU = 0x00080000
    WS_BORDER = 0x00800000
    WS_DLGFRAME = 0x00400000
    WS_POPUP = 0x80000000
    WS_VISIBLE = 0x10000000
    WS_EX_WINDOWEDGE = 0x00000100
    WS_EX_CLIENTEDGE = 0x00000200
    WS_EX_DLGMODALFRAME = 0x00000001
    SWP_FRAMECHANGED = 0x0020
    SWP_SHOWWINDOW = 0x0040
    SW_SHOW = 5
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2

    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)

    width, height = _get_primary_screen_size()
    style = get_long(hwnd, GWL_STYLE)
    style &= ~(
        WS_CAPTION
        | WS_THICKFRAME
        | WS_MINIMIZEBOX
        | WS_MAXIMIZEBOX
        | WS_SYSMENU
        | WS_BORDER
        | WS_DLGFRAME
    )
    style |= WS_POPUP | WS_VISIBLE
    set_long(hwnd, GWL_STYLE, style)

    exstyle = get_long(hwnd, GWL_EXSTYLE)
    exstyle &= ~(WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_DLGMODALFRAME)
    set_long(hwnd, GWL_EXSTYLE, exstyle)

    user32.ShowWindow(hwnd, SW_SHOW)
    # TOPMOST briefly so Windows applies the size over the taskbar, then clear topmost
    user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0,
        0,
        width,
        height,
        SWP_FRAMECHANGED | SWP_SHOWWINDOW,
    )
    user32.SetWindowPos(
        hwnd,
        HWND_NOTOPMOST,
        0,
        0,
        width,
        height,
        SWP_FRAMECHANGED | SWP_SHOWWINDOW,
    )
    user32.SetForegroundWindow(hwnd)
    _ui_hwnd = hwnd


def _collect_descendant_pids(root_pid):
    """Return set of root_pid plus all descendant process ids (Windows)."""
    pids = {int(root_pid)}
    if sys.platform != "win32":
        return pids
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

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

        kernel32 = ctypes.windll.kernel32
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == INVALID_HANDLE_VALUE:
            return pids

        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        children = {}
        if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            while True:
                children.setdefault(int(entry.th32ParentProcessID), []).append(
                    int(entry.th32ProcessID)
                )
                if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    break
        kernel32.CloseHandle(snap)

        stack = [int(root_pid)]
        while stack:
            parent = stack.pop()
            for child in children.get(parent, []):
                if child not in pids:
                    pids.add(child)
                    stack.append(child)
    except Exception as exc:
        logger.debug("Could not enumerate Chrome child PIDs: %s", exc)
    return pids


def _find_largest_hwnd_for_pids(target_pids):
    """Return the largest visible top-level window hwnd owned by any pid in the set."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    IsWindowVisible = user32.IsWindowVisible
    GetWindowTextLengthW = user32.GetWindowTextLengthW

    wanted = {int(p) for p in target_pids}
    found = []

    def _callback(hwnd, _lparam):
        pid = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in wanted:
            return True
        if not IsWindowVisible(hwnd):
            return True
        if GetWindowTextLengthW(hwnd) <= 0:
            return True
        found.append(hwnd)
        return True

    EnumWindows(EnumWindowsProc(_callback), 0)
    if not found:
        return None

    best = found[0]
    try:
        rect = wintypes.RECT()
        area_best = 0
        for hwnd in found:
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
                if area >= area_best:
                    area_best = area
                    best = hwnd
    except Exception:
        best = found[0]
    return best


def _find_hwnd_by_title_substrings(title_substrings):
    """Find largest visible window whose title contains any of the substrings."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    IsWindowVisible = user32.IsWindowVisible
    GetWindowTextLengthW = user32.GetWindowTextLengthW
    GetWindowTextW = user32.GetWindowTextW

    needles = [s.lower() for s in title_substrings if s]
    found = []

    def _callback(hwnd, _lparam):
        if not IsWindowVisible(hwnd):
            return True
        length = GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buf, length + 1)
        title = (buf.value or "").strip().lower()
        if any(n in title for n in needles):
            found.append(hwnd)
        return True

    EnumWindows(EnumWindowsProc(_callback), 0)
    if not found:
        return None

    best = found[0]
    try:
        rect = wintypes.RECT()
        area_best = 0
        for hwnd in found:
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
                if area >= area_best:
                    area_best = area
                    best = hwnd
    except Exception:
        best = found[0]
    return best


def _find_largest_hwnd_for_pid(target_pid):
    """Return the largest visible top-level window hwnd for a process tree."""
    return _find_largest_hwnd_for_pids(_collect_descendant_pids(target_pid))


def _restore_hwnd_windowed(hwnd):
    """
    Restore title bar / min / max / close so the user can leave exclusive fullscreen.
    Window is maximized to the work area (taskbar visible).
    """
    global _ui_hwnd
    import ctypes

    user32 = ctypes.windll.user32
    GWL_STYLE = -16
    WS_OVERLAPPEDWINDOW = 0x00CF0000
    WS_VISIBLE = 0x10000000
    WS_POPUP = 0x80000000
    SWP_FRAMECHANGED = 0x0020
    SWP_SHOWWINDOW = 0x0040
    SW_RESTORE = 9
    SW_MAXIMIZE = 3
    HWND_TOP = 0

    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)

    left, top, width, height = _get_work_area()
    style = get_long(hwnd, GWL_STYLE)
    style &= ~WS_POPUP
    style |= WS_OVERLAPPEDWINDOW | WS_VISIBLE
    set_long(hwnd, GWL_STYLE, style)

    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(
        hwnd,
        HWND_TOP,
        left,
        top,
        width,
        height,
        SWP_FRAMECHANGED | SWP_SHOWWINDOW,
    )
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    user32.SetForegroundWindow(hwnd)
    _ui_hwnd = hwnd


def _resolve_ui_hwnd(title_hints=None):
    """Best-effort find the active UI window hwnd."""
    global _ui_hwnd
    import ctypes

    user32 = ctypes.windll.user32
    hints = title_hints or _DEFAULT_UI_TITLE_HINTS

    if _ui_hwnd and user32.IsWindow(_ui_hwnd) and user32.IsWindowVisible(_ui_hwnd):
        return _ui_hwnd

    proc = _chrome_process
    if proc is not None and proc.poll() is None:
        hwnd = _find_largest_hwnd_for_pids(_collect_descendant_pids(proc.pid))
        if hwnd:
            _ui_hwnd = hwnd
            return hwnd

    hwnd = _find_hwnd_by_title_substrings(hints)
    if hwnd:
        _ui_hwnd = hwnd
    return hwnd


def exit_ui_fullscreen(title_hints=None):
    """Leave borderless fullscreen and restore a normal maximizable window."""
    if sys.platform != "win32":
        return False
    try:
        hwnd = _resolve_ui_hwnd(title_hints)
        if not hwnd:
            logger.warning("exit_ui_fullscreen: UI window not found")
            return False
        _restore_hwnd_windowed(hwnd)
        logger.info("UI window restored from fullscreen (hwnd=%s)", hwnd)
        return True
    except Exception as exc:
        logger.warning("exit_ui_fullscreen failed: %s", exc)
        return False


def enter_ui_fullscreen(title_hints=None):
    """Force the UI window back into borderless fullscreen."""
    if sys.platform != "win32":
        return False
    try:
        hwnd = _resolve_ui_hwnd(title_hints)
        if not hwnd:
            logger.warning("enter_ui_fullscreen: UI window not found")
            return False
        _force_hwnd_fullscreen(hwnd)
        logger.info("UI window forced to fullscreen (hwnd=%s)", hwnd)
        return True
    except Exception as exc:
        logger.warning("enter_ui_fullscreen failed: %s", exc)
        return False


def minimize_ui_window(title_hints=None):
    """Minimize the UI window (restores frame first if needed)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        SW_MINIMIZE = 6
        hwnd = _resolve_ui_hwnd(title_hints)
        if not hwnd:
            return False
        # Ensure system menu / minimize box exist, then minimize
        _restore_hwnd_windowed(hwnd)
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        logger.info("UI window minimized (hwnd=%s)", hwnd)
        return True
    except Exception as exc:
        logger.warning("minimize_ui_window failed: %s", exc)
        return False


def force_chrome_app_fullscreen(proc, timeout_sec=15.0, title_hints=None):
    """
    After Chrome launch, find its window (process tree or title) and force fullscreen.
    Runs in a background thread so startup is not blocked.
    """
    if sys.platform != "win32" or proc is None:
        return

    hints = title_hints or _DEFAULT_UI_TITLE_HINTS

    def _worker():
        try:
            deadline = time.time() + timeout_sec
            target_pid = int(proc.pid)
            while time.time() < deadline:
                if proc.poll() is not None:
                    return
                pids = _collect_descendant_pids(target_pid)
                best = _find_largest_hwnd_for_pids(pids)
                if best is None:
                    best = _find_hwnd_by_title_substrings(hints)
                if best:
                    # Apply repeatedly - Chrome often re-asserts chrome UI after paint
                    for delay in (0.0, 0.4, 0.9, 1.5):
                        if delay:
                            time.sleep(delay)
                        if proc.poll() is not None:
                            return
                        _force_hwnd_fullscreen(best)
                    logger.info("Forced Chrome window to fullscreen (hwnd=%s pids=%s)", best, sorted(pids)[:8])
                    return
                time.sleep(0.3)
            logger.warning("Could not find Chrome window to fullscreen within %ss", timeout_sec)
        except Exception as exc:
            logger.warning("Force Chrome fullscreen failed: %s", exc)

    threading.Thread(target=_worker, daemon=True).start()


# Back-compat alias used by older call sites
force_chrome_app_fit_screen = force_chrome_app_fullscreen


def force_native_window_fullscreen(title, timeout_sec=12.0):
    """
    Force a native UI window (pywebview / Qt / Edge WebView2 host) into fullscreen
    by matching its window title. Runs in a background thread.
    """
    if sys.platform != "win32" or not title:
        return

    def _worker():
        try:
            import ctypes

            user32 = ctypes.windll.user32
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                hwnd = user32.FindWindowW(None, title)
                if not hwnd:
                    hwnd = _find_hwnd_by_title_substrings((title, "Device Configuration"))
                if hwnd and user32.IsWindowVisible(hwnd):
                    for delay in (0.0, 0.4, 0.9):
                        if delay:
                            time.sleep(delay)
                        if not user32.IsWindow(hwnd):
                            break
                        _force_hwnd_fullscreen(hwnd)
                    logger.info("Forced native window to fullscreen (title=%r hwnd=%s)", title, hwnd)
                    return
                time.sleep(0.35)
            logger.warning("Could not find native window %r to fullscreen within %ss", title, timeout_sec)
        except Exception as exc:
            logger.warning("Force native fullscreen failed: %s", exc)

    threading.Thread(target=_worker, daemon=True).start()


def launch_chromium_app_mode(url, chrome_path):
    """Open URL in Google Chrome app mode, then force fullscreen (Esc restores window)."""
    global _chrome_process

    if not chrome_path or not os.path.isfile(chrome_path):
        logger.warning("Google Chrome not found; cannot launch app mode")
        return None

    try:
        import tempfile

        # Dedicated profile so this session does not touch the user's main Chrome
        user_data = os.path.join(tempfile.gettempdir(), "gmdc-checkpoint-config-chrome")
        os.makedirs(user_data, exist_ok=True)

        width, height = _get_primary_screen_size()
        # App mode (not kiosk) so Esc / minimize can restore normal window controls
        _chrome_process = subprocess.Popen(
            [
                chrome_path,
                f"--user-data-dir={user_data}",
                f"--app={url}",
                "--start-maximized",
                f"--window-size={width},{height}",
                "--window-position=0,0",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-session-crashed-bubble",
                "--disable-features=TranslateUI",
                "--check-for-update-interval=31536000",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        force_chrome_app_fullscreen(_chrome_process)
        logger.info("Launched Chrome app mode (fullscreen, Esc to exit): %s", url)
        return _chrome_process
    except Exception as exc:
        logger.error("Failed to launch Chrome app mode: %s", exc)
        _chrome_process = None
        return None


def launch_default_browser(url):
    """Open URL in the system default browser."""
    try:
        webbrowser.open(url)
        logger.info("Opened URL in default browser: %s", url)
        return True
    except Exception as exc:
        logger.error("Failed to open default browser: %s", exc)
        return False


def terminate_chrome_process():
    """Best-effort terminate Chrome subprocess launched by this module (incl. children)."""
    global _chrome_process
    proc = _chrome_process
    if proc is None:
        return
    pid = None
    try:
        pid = int(proc.pid)
    except Exception:
        pid = None

    try:
        if sys.platform == "win32" and pid:
            # Kill process tree - Chrome spawns child processes for the app window
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            logger.info("Terminated Chrome process tree (pid=%s)", pid)
        elif proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
    except Exception as exc:
        logger.warning("terminate_chrome_process failed: %s", exc)
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    finally:
        _chrome_process = None


def close_ui_windows_by_title(title_substrings=None):
    """
    Close top-level windows whose titles contain any of the given substrings.
    Used to shut the Chrome app / browser frontend after setup completes.
    """
    if sys.platform != "win32":
        return
    if not title_substrings:
        title_substrings = (
            "GMDC Checkpoint Config",
            "Device Configuration",
            "127.0.0.1:8080",
            "localhost:8080",
        )
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        GetWindowTextW = user32.GetWindowTextW
        IsWindowVisible = user32.IsWindowVisible
        PostMessageW = user32.PostMessageW
        WM_CLOSE = 0x0010

        needles = [s.lower() for s in title_substrings if s]
        closed = []

        def _callback(hwnd, _lparam):
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = (buf.value or "").strip()
            title_l = title.lower()
            if any(n in title_l for n in needles):
                PostMessageW(hwnd, WM_CLOSE, 0, 0)
                closed.append(title)
            return True

        EnumWindows(EnumWindowsProc(_callback), 0)
        if closed:
            logger.info("Closed UI window(s): %s", closed)
    except Exception as exc:
        logger.warning("close_ui_windows_by_title failed: %s", exc)


def run_webview_start(app_name, timeout_sec, debug=False, gui=None):
    """
    Call webview.start() with a visibility monitor (window must be created first).
    Returns True if the session ended without a visibility-timeout fallback signal.
    """
    import webview

    fallback_reason = {"value": None}

    def monitor():
        if wait_for_webview_window(app_name, timeout_sec):
            return
        fallback_reason["value"] = "timeout"
        logger.warning(
            "WebView window not ready within %ss; closing webview for fallback",
            timeout_sec,
        )
        try:
            from utils.webview_stderr import destroy_webview_window_quietly
            destroy_webview_window_quietly()
        except Exception as exc:
            logger.debug("destroy_window during monitor: %s", exc)

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()

    start_kwargs = {"debug": debug}
    if gui:
        start_kwargs["gui"] = gui

    try:
        from utils.webview_stderr import suppress_native_stderr
        with suppress_native_stderr():
            webview.start(**start_kwargs)
    except SystemExit:
        pass
    except Exception as exc:
        if fallback_reason["value"] != "timeout":
            fallback_reason["value"] = "error"
            logger.warning("webview.start() failed: %s", exc)

    return fallback_reason["value"] is None


def run_ui_with_auto_fallback(
    url,
    ui_mode,
    webview_timeout_sec,
    chrome_executable_path,
    app_name,
    flask_thread,
    setup_and_run_webview,
    cleanup_callback,
):
    """
    Launch the application UI according to ui_mode.

    setup_and_run_webview: callable() -> bool
        Creates the webview window, runs webview.start (via run_webview_start inside app),
        returns True if the native window session completed without needing fallback.

    Returns the launch mode used: webview, chromium_app, or browser.
    """
    mode = (ui_mode or "auto").strip().lower()
    if mode not in VALID_UI_MODES:
        logger.warning("Unknown APPLICATION_UI_MODE %r; using auto", ui_mode)
        mode = "auto"

    def _wait_flask():
        if flask_thread and flask_thread.is_alive():
            flask_thread.join()

    def _cleanup():
        if cleanup_callback:
            try:
                cleanup_callback()
            except Exception as exc:
                logger.warning("Cleanup callback error: %s", exc)

    def _try_chrome():
        chrome = find_chrome_executable(chrome_executable_path)
        proc = launch_chromium_app_mode(url, chrome)
        if proc is not None:
            _wait_flask()
            return "chromium_app"
        return None

    def _try_browser():
        launch_default_browser(url)
        _wait_flask()
        return "browser"

    if mode == "browser":
        logger.info("UI mode: browser (default)")
        return _try_browser()

    if mode == "chromium_app":
        logger.info("UI mode: chromium_app (Google Chrome)")
        result = _try_chrome()
        if result:
            return result
        logger.error("chromium_app mode requires Google Chrome; falling back to default browser")
        return _try_browser()

    if mode == "webview":
        logger.info("UI mode: webview (native window only)")
        try:
            if setup_and_run_webview():
                _cleanup()
                return "webview"
        except ImportError:
            logger.error("pywebview not installed; cannot use webview mode")
        _cleanup()
        raise RuntimeError("Failed to start native application window (webview mode)")

    # auto
    logger.info("UI mode: auto (webview -> Chrome app -> default browser)")

    if is_webview2_runtime_available():
        try:
            if setup_and_run_webview():
                _cleanup()
                return "webview"
        except ImportError:
            logger.info("pywebview not available; skipping native window")
        except Exception as exc:
            logger.warning("Native window failed: %s", exc)
    else:
        logger.info(
            "WebView2 runtime not detected; skipping pywebview native window"
        )

    result = _try_chrome()
    if result:
        _cleanup()
        return result

    logger.info("Chrome not available; opening default browser")
    result = _try_browser()
    _cleanup()
    return result
