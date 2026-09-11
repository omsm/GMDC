"""
Mosquitto Broker Setup Module
Automatically checks for, installs, and configures Mosquitto MQTT broker
Runs in background without blocking the GUI application
"""
import os
import sys
import subprocess
import shutil
import tempfile
import logging
import urllib.request
import time
from pathlib import Path

# app_data_path will be passed as parameter to functions that need it

# Configure logger
logger = logging.getLogger(__name__)


def is_admin():
    """Check if the current process has admin privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_elevated(file_path, arguments="", wait=True):
    """
    Run an executable with elevated (admin) privileges using ShellExecuteW.
    This will trigger a visible UAC prompt for the user to approve.
    
    Args:
        file_path: Path to the executable to run
        arguments: Command line arguments (optional)
        wait: Whether to wait for the command to complete
        
    Returns:
        tuple: (success: bool, error_message: str)
    """
    try:
        import ctypes
        
        logger.info(f"Requesting admin privileges for: {file_path} {arguments}")
        
        # Use ShellExecuteW to trigger UAC prompt (this will show the black screen)
        # SW_SHOWNORMAL = 1 - shows the window normally
        # runas verb triggers UAC elevation
        
        if arguments:
            # Combine file path and arguments
            command_line = f'"{file_path}" {arguments}'
        else:
            command_line = f'"{file_path}"'
        
        # ShellExecuteW parameters:
        # hwnd: Parent window handle (None = no parent)
        # lpOperation: "runas" triggers UAC elevation
        # lpFile: File to execute
        # lpParameters: Command line arguments
        # lpDirectory: Working directory (None = current)
        # nShowCmd: SW_SHOWNORMAL = 1 (show window normally)
        
        result = ctypes.windll.shell32.ShellExecuteW(
            None,  # hwnd
            "runas",  # lpOperation - triggers UAC
            file_path,  # lpFile
            arguments,  # lpParameters
            None,  # lpDirectory
            1  # nShowCmd - SW_SHOWNORMAL (show window)
        )
        
        # ShellExecuteW returns a value > 32 on success
        if result > 32:
            if wait:
                # For ShellExecuteW, we can't directly wait for the process
                # Use a simple time-based wait for installations
                # The actual process will run in the background
                import time
                
                # For installers, wait a reasonable amount of time
                # The caller should verify completion separately
                if "install" in file_path.lower() or file_path.endswith(".exe"):
                    # Wait a bit for the process to start
                    time.sleep(2)
                    # For installers, we'll verify completion by checking for installed files
                    # So we don't need to wait here - just return success
                else:
                    # For other commands, wait a short time
                    time.sleep(1)
            
            logger.info("Elevated command executed successfully")
            return True, ""
        else:
            # Error codes from ShellExecuteW
            error_codes = {
                0: "Out of memory or resources",
                2: "File not found",
                3: "Path not found",
                5: "Access denied",
                8: "Out of memory",
                11: "Invalid .exe file",
                26: "Sharing violation",
                27: "File association incomplete or invalid",
                28: "DDE transaction timed out",
                29: "DDE transaction failed",
                30: "DDE transaction busy",
                31: "No file association",
                32: "DLL not found"
            }
            error_msg = error_codes.get(result, f"Unknown error (code: {result})")
            logger.error(f"Elevated command failed: {error_msg}")
            return False, error_msg
            
    except ImportError:
        # Fallback to PowerShell method if psutil not available
        logger.warning("psutil not available, using PowerShell fallback for elevation")
        try:
            wait_flag = "-Wait" if wait else ""
            
            if arguments:
                ps_command = f'Start-Process -FilePath "{file_path}" -ArgumentList \'{arguments}\' -Verb RunAs {wait_flag}'
            else:
                ps_command = f'Start-Process -FilePath "{file_path}" -Verb RunAs {wait_flag}'
            
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                # Don't use CREATE_NO_WINDOW to allow UAC prompt to show
            )
            
            if result.returncode == 0:
                logger.info("Elevated command executed successfully")
                return True, ""
            else:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                logger.error(f"Elevated command failed: {error_msg}")
                return False, error_msg
        except Exception as e:
            logger.error(f"Error running elevated command: {e}")
            return False, str(e)
    except Exception as e:
        logger.error(f"Error running elevated command: {e}")
        return False, str(e)


def diagnose_mosquitto_startup(install_path):
    """
    Try to run mosquitto directly to diagnose why it fails to start.
    This captures the actual error message.
    """
    try:
        if IS_WINDOWS:
            mosquitto_exe = os.path.join(install_path, "mosquitto.exe")
        else:
            mosquitto_exe = os.path.join(install_path, "mosquitto")
            if not os.path.exists(mosquitto_exe):
                mosquitto_exe = shutil.which("mosquitto") or mosquitto_exe
        config_path = find_mosquitto_config_path(install_path)
        
        if not os.path.exists(mosquitto_exe):
            return "mosquitto binary not found"
        
        logger.info("Running mosquitto directly to diagnose startup issues...")
        
        cmd = [mosquitto_exe, "-v"]
        if config_path and os.path.exists(config_path):
            cmd.extend(["-c", config_path])
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,  # Short timeout - we just want to see if it starts
            cwd=install_path if install_path and os.path.isdir(install_path) else None,
            **_subprocess_kwargs(),
        )
        
        output = result.stdout.decode('utf-8', errors='ignore')
        error = result.stderr.decode('utf-8', errors='ignore')
        
        logger.info(f"Mosquitto direct run output: {output}")
        if error:
            logger.error(f"Mosquitto direct run error: {error}")
        
        return output + error
        
    except subprocess.TimeoutExpired:
        # If it times out, it might actually be running
        return "Mosquitto started (timeout waiting for output)"
    except Exception as e:
        return f"Error running mosquitto: {str(e)}"


def start_service_elevated(service_name):
    """
    Start a Windows service with elevated privileges using PowerShell.
    This method properly captures the service start result.
    
    Args:
        service_name: Name of the Windows service to start
        
    Returns:
        tuple: (success: bool, error_message: str)
    """
    try:
        logger.info(f"Starting service '{service_name}' with elevated PowerShell...")
        
        # Create a temp batch file that starts the service and saves the result
        temp_dir = tempfile.gettempdir()
        batch_file = os.path.join(temp_dir, "start_mosquitto_service.bat")
        result_file = os.path.join(temp_dir, "mosquitto_service_result.txt")
        
        # Clean up old result file
        if os.path.exists(result_file):
            try:
                os.remove(result_file)
            except:
                pass
        
        # Create batch file that starts service and saves result
        batch_content = f'''@echo off
net start {service_name} > "{result_file}" 2>&1
echo EXIT_CODE=%errorlevel% >> "{result_file}"
'''
        
        with open(batch_file, 'w') as f:
            f.write(batch_content)
        
        # Run the batch file with elevation
        success, error = run_elevated(batch_file, "")
        
        # Wait for result file
        time.sleep(3)
        
        # Read result file
        result_content = ""
        if os.path.exists(result_file):
            try:
                with open(result_file, 'r') as f:
                    result_content = f.read()
                logger.info(f"Service start result: {result_content}")
            except:
                pass
        
        # Clean up
        try:
            os.remove(batch_file)
            if os.path.exists(result_file):
                os.remove(result_file)
        except:
            pass
        
        # Check if service is running
        check_result = subprocess.run(
            ["powershell", "-Command", f'(Get-Service -Name "{service_name}").Status'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            creationflags=0x08000000
        )
        
        status = check_result.stdout.decode('utf-8', errors='ignore').strip()
        logger.info(f"Service status after elevated start: {status}")
        
        if status == "Running":
            return True, ""
        else:
            # Include the actual error from the batch file result
            error_detail = result_content if result_content else f"Service status is {status}"
            return False, error_detail
            
    except subprocess.TimeoutExpired:
        logger.error("Service start timed out")
        return False, "Command timed out"
    except Exception as e:
        logger.error(f"Error starting service: {e}")
        return False, str(e)


# Mosquitto version to install (Windows installer pin)
MOSQUITTO_VERSION = "2.0.18"
MOSQUITTO_INSTALLER_URL = f"https://mosquitto.org/files/binary/win64/mosquitto-{MOSQUITTO_VERSION}-install-windows-x64.exe"

IS_WINDOWS = sys.platform == "win32"
IS_DARWIN = sys.platform == "darwin"

# Common Windows installation paths
COMMON_PATHS = [
    r"C:\Program Files\mosquitto",
    r"C:\Program Files (x86)\mosquitto",
]

# Common macOS Homebrew locations (Apple Silicon + Intel)
# Newer Homebrew Mosquitto packages ship the broker under sbin/, not bin/.
MAC_MOSQUITTO_BINS = [
    "/opt/homebrew/sbin/mosquitto",
    "/opt/homebrew/bin/mosquitto",
    "/opt/homebrew/opt/mosquitto/sbin/mosquitto",
    "/usr/local/sbin/mosquitto",
    "/usr/local/bin/mosquitto",
    "/usr/local/opt/mosquitto/sbin/mosquitto",
]
MAC_MOSQUITTO_CONFIGS = [
    "/opt/homebrew/etc/mosquitto/mosquitto.conf",
    "/usr/local/etc/mosquitto/mosquitto.conf",
    "/opt/homebrew/etc/mosquitto.conf",
    "/usr/local/etc/mosquitto.conf",
]
MAC_BREW_CANDIDATES = [
    "/opt/homebrew/bin/brew",
    "/usr/local/bin/brew",
]

# Service name
MOSQUITTO_SERVICE_NAME = "mosquitto"


def _subprocess_kwargs():
    """Platform-safe subprocess kwargs (hide console on Windows only)."""
    kwargs = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return kwargs


def find_homebrew():
    """Return path to brew executable, or None."""
    brew = shutil.which("brew")
    if brew:
        return brew
    for path in MAC_BREW_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _brew_prefix(brew_path=None):
    brew = brew_path or find_homebrew()
    if not brew:
        return None
    try:
        result = subprocess.run(
            [brew, "--prefix"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            text=True,
        )
        if result.returncode == 0:
            return (result.stdout or "").strip() or None
    except Exception as e:
        logger.debug("brew --prefix failed: %s", e)
    return None


def check_mosquitto_installed():
    """
    Check if Mosquitto is already installed on the system.
    
    Returns:
        tuple: (is_installed: bool, install_path: str or None)
    """
    try:
        mosquitto_path = shutil.which("mosquitto")
        if mosquitto_path and os.path.isfile(mosquitto_path):
            install_dir = os.path.dirname(os.path.realpath(mosquitto_path))
            logger.info("Mosquitto found in PATH at: %s", mosquitto_path)
            return True, install_dir

        if IS_DARWIN:
            for path in MAC_MOSQUITTO_BINS:
                if os.path.isfile(path):
                    install_dir = os.path.dirname(os.path.realpath(path))
                    logger.info("Mosquitto found at: %s", path)
                    return True, install_dir
            brew = find_homebrew()
            if brew:
                formula_prefix = ""
                try:
                    result = subprocess.run(
                        [brew, "--prefix", "mosquitto"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=30,
                        text=True,
                    )
                    if result.returncode == 0:
                        formula_prefix = (result.stdout or "").strip()
                except Exception:
                    formula_prefix = ""
                roots = [p for p in (formula_prefix, _brew_prefix(brew)) if p]
                candidates = []
                for root in roots:
                    candidates.extend(
                        [
                            os.path.join(root, "sbin", "mosquitto"),
                            os.path.join(root, "bin", "mosquitto"),
                        ]
                    )
                    if os.path.basename(root.rstrip(os.sep)) != "mosquitto":
                        candidates.extend(
                            [
                                os.path.join(root, "opt", "mosquitto", "sbin", "mosquitto"),
                                os.path.join(root, "opt", "mosquitto", "bin", "mosquitto"),
                            ]
                        )
                for candidate in candidates:
                    if os.path.isfile(candidate):
                        logger.info("Mosquitto found via brew prefix: %s", candidate)
                        return True, os.path.dirname(candidate)

        if IS_WINDOWS:
            for path in COMMON_PATHS:
                mosquitto_exe = os.path.join(path, "mosquitto.exe")
                if os.path.exists(mosquitto_exe):
                    logger.info("Mosquitto found at: %s", mosquitto_exe)
                    return True, path

        logger.info("Mosquitto not found on system")
        return False, None

    except Exception as e:
        logger.error("Error checking for Mosquitto installation: %s", e)
        return False, None


def install_mosquitto_macos(progress_callback=None):
    """
    Install Mosquitto on macOS via Homebrew.

    Returns:
        tuple: (success: bool, message: str)
    """
    def _progress(percent, message):
        if progress_callback:
            progress_callback(percent, message)

    brew = find_homebrew()
    if not brew:
        msg = (
            "Homebrew is not installed. Install it from https://brew.sh "
            "then re-run, or run: brew install mosquitto"
        )
        logger.error(msg)
        return False, msg

    logger.info("Using Homebrew at: %s", brew)
    _progress(10, "Checking Homebrew Mosquitto formula...")

    try:
        # Already linked?
        list_result = subprocess.run(
            [brew, "list", "--versions", "mosquitto"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            text=True,
        )
        if list_result.returncode == 0 and (list_result.stdout or "").strip():
            logger.info("Mosquitto already installed via brew: %s", list_result.stdout.strip())
            _progress(80, "Mosquitto already installed via Homebrew")
            return True, "already_installed"

        _progress(20, "Installing Mosquitto with Homebrew (may take a few minutes)...")
        logger.info("Running: brew install mosquitto")
        result = subprocess.run(
            [brew, "install", "mosquitto"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=900,
            text=True,
        )
        if result.stdout:
            logger.info("brew install stdout:\n%s", result.stdout[-4000:])
        if result.stderr:
            logger.info("brew install stderr:\n%s", result.stderr[-4000:])

        if result.returncode != 0:
            msg = f"brew install mosquitto failed (code {result.returncode})"
            logger.error(msg)
            return False, msg

        # Ensure binary is present (Homebrew places broker in sbin/)
        is_installed, install_path = check_mosquitto_installed()
        if not is_installed:
            msg = "brew install finished but mosquitto binary was not found"
            logger.error(msg)
            return False, msg

        logger.info("Mosquitto installed via Homebrew at %s", install_path)
        _progress(80, "Mosquitto installed via Homebrew")
        return True, "installed"
    except subprocess.TimeoutExpired:
        msg = "brew install mosquitto timed out"
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"macOS Mosquitto install failed: {e}"
        logger.error(msg, exc_info=True)
        return False, msg


def resolve_mosquitto_binary(install_path=None):
    """Return absolute path to mosquitto broker binary, or None."""
    found, path = check_mosquitto_installed()
    if found and path:
        for name in ("mosquitto", "mosquitto.exe"):
            candidate = os.path.join(path, name)
            if os.path.isfile(candidate):
                return candidate
    which = shutil.which("mosquitto")
    if which and os.path.isfile(which):
        return which
    if install_path:
        for name in ("mosquitto", "mosquitto.exe"):
            candidate = os.path.join(install_path, name)
            if os.path.isfile(candidate):
                return candidate
    for path in MAC_MOSQUITTO_BINS:
        if os.path.isfile(path):
            return path
    return None


def check_mosquitto_running_macos():
    """Return True if a mosquitto process appears to be running."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "mosquitto"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def start_mosquitto_macos(install_path=None, config_path=None, app_data_path=None):
    """
    Start Mosquitto on macOS. Prefer app-local config + daemon so listeners match
    the checkpoint UI (1883 MQTT + 9001 websockets). Fall back to brew services.
    """
    if check_mosquitto_running_macos():
        logger.info("Mosquitto process already running")
        return True

    local_cfg = None
    if app_data_path:
        candidate = os.path.join(app_data_path, "mosquitto", "mosquitto.conf")
        if os.path.isfile(candidate):
            local_cfg = candidate
    cfg = local_cfg or config_path or find_mosquitto_config_path(install_path)

    mosquitto_bin = resolve_mosquitto_binary(install_path)

    if mosquitto_bin and cfg and os.path.isfile(cfg):
        try:
            cmd = [mosquitto_bin, "-c", cfg, "-d"]
            logger.info("Starting Mosquitto daemon: %s", " ".join(cmd))
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(1.0)
            if check_mosquitto_running_macos():
                logger.info("Mosquitto daemon started with config %s", cfg)
                return True
            logger.warning("Daemon start attempted but process not found; trying brew services")
        except Exception as e:
            logger.warning("Failed to start Mosquitto daemon: %s", e)

    brew = find_homebrew()
    if brew:
        try:
            logger.info("Starting Mosquitto via brew services...")
            result = subprocess.run(
                [brew, "services", "start", "mosquitto"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=120,
                text=True,
            )
            if result.stdout:
                logger.info("brew services stdout: %s", result.stdout.strip())
            if result.stderr:
                logger.info("brew services stderr: %s", result.stderr.strip())
            time.sleep(1.5)
            if check_mosquitto_running_macos() or result.returncode == 0:
                logger.info("Mosquitto started via brew services")
                return True
            logger.warning("brew services start returned %s", result.returncode)
        except Exception as e:
            logger.warning("brew services start failed: %s", e)

    if not mosquitto_bin:
        logger.error("Cannot start Mosquitto: binary not found")
        return False

    cmd = [mosquitto_bin, "-d"]
    if cfg and os.path.isfile(cfg):
        cmd.extend(["-c", cfg])
    try:
        logger.info("Starting Mosquitto daemon (fallback): %s", " ".join(cmd))
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(1.0)
        if check_mosquitto_running_macos():
            logger.info("Mosquitto daemon started")
            return True
        logger.error("Mosquitto daemon start attempted but process not found")
        return False
    except Exception as e:
        logger.error("Failed to start Mosquitto daemon: %s", e)
        return False


def download_mosquitto_installer(download_path, progress_callback=None):
    """
    Download Mosquitto Windows installer from official source.
    """
    try:
        logger.info(f"Downloading Mosquitto {MOSQUITTO_VERSION} installer...")
        logger.info(f"URL: {MOSQUITTO_INSTALLER_URL}")
        
        if progress_callback:
            progress_callback(0, "Starting download...")
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(download_path), exist_ok=True)
        
        last_percent = [-1]  # Use list to allow modification in nested function
        
        # Download with progress tracking
        def download_progress_hook(count, block_size, total_size):
            if total_size > 0:
                percent = min(100, int(count * block_size * 100 / total_size))
                # Update on every percent change (not just when it changes) for smoother progress
                if percent != last_percent[0]:
                    last_percent[0] = percent
                    if percent % 10 == 0:  # Log every 10%
                        logger.info(f"Download progress: {percent}%")
                    # Call progress callback for UI update - only percentage, no text
                    if progress_callback:
                        progress_callback(percent, "")
        
        urllib.request.urlretrieve(
            MOSQUITTO_INSTALLER_URL,
            download_path,
            reporthook=download_progress_hook
        )
        
        if os.path.exists(download_path):
            file_size = os.path.getsize(download_path)
            logger.info(f"Download complete. File size: {file_size / (1024*1024):.2f} MB")
            if progress_callback:
                # Final update to 100% without extra text
                progress_callback(100, "")
            return True
        else:
            logger.error("Downloaded file not found")
            return False
            
    except Exception as e:
        logger.error(f"Error downloading Mosquitto installer: {e}")
        return False


def install_mosquitto(installer_path):
    """
    Install Mosquitto using the downloaded Windows installer.
    Will automatically request admin privileges via UAC if needed.
    """
    if not IS_WINDOWS:
        logger.error("install_mosquitto(installer) is Windows-only")
        return False
    try:
        logger.info("Starting Mosquitto installation (silent mode)...")
        
        # Installation requires admin privileges to write to Program Files
        # and register the Windows service
        
        if is_admin():
            # Already running as admin - run installer directly
            logger.info("Running installer with existing admin privileges...")
            result = subprocess.run(
                [installer_path, "/S"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=300,  # 5 minute timeout
                **_subprocess_kwargs(),
            )
            
            if result.returncode == 0:
                logger.info("Mosquitto installation completed successfully")
                return True
            else:
                logger.error(f"Mosquitto installation failed with return code: {result.returncode}")
                if result.stderr:
                    logger.error(f"Installation error: {result.stderr.decode('utf-8', errors='ignore')}")
                return False
        else:
            # Not running as admin - request elevation via UAC
            logger.info("Requesting admin privileges for Mosquitto installation...")
            success, error = run_elevated(installer_path, "/S")
            
            if success:
                # Wait for installation to complete and verify
                logger.info("Waiting for installation to complete...")
                time.sleep(5)
                
                # Verify installation by checking if mosquitto.exe exists
                is_installed, install_path = check_mosquitto_installed()
                if is_installed:
                    logger.info(f"Mosquitto installed successfully at: {install_path}")
                    return True
                else:
                    logger.warning("Elevated installer completed but Mosquitto not found. Checking again...")
                    time.sleep(3)
                    is_installed, install_path = check_mosquitto_installed()
                    if is_installed:
                        logger.info(f"Mosquitto installed successfully at: {install_path}")
                        return True
                    else:
                        logger.error("Installation verification failed - Mosquitto not found after installation")
                        return False
            else:
                logger.error(f"Failed to install Mosquitto with elevated privileges: {error}")
                return False
            
    except subprocess.TimeoutExpired:
        logger.error("Mosquitto installation timed out")
        return False
    except Exception as e:
        logger.error(f"Error during Mosquitto installation: {e}")
        return False


def find_mosquitto_config_path(install_path=None):
    """
    Find the path to mosquitto.conf file.
    """
    try:
        if install_path:
            config_path = os.path.join(install_path, "mosquitto.conf")
            if os.path.exists(config_path):
                return config_path
            brew_cfg = os.path.abspath(
                os.path.join(install_path, "..", "etc", "mosquitto", "mosquitto.conf")
            )
            if os.path.exists(brew_cfg):
                return brew_cfg

        if IS_DARWIN:
            for config_path in MAC_MOSQUITTO_CONFIGS:
                if os.path.exists(config_path):
                    return config_path
            brew = find_homebrew()
            prefix = _brew_prefix(brew) if brew else None
            if prefix:
                return os.path.join(prefix, "etc", "mosquitto", "mosquitto.conf")
            return MAC_MOSQUITTO_CONFIGS[0]

        if IS_WINDOWS:
            for path in COMMON_PATHS:
                config_path = os.path.join(path, "mosquitto.conf")
                if os.path.exists(config_path):
                    return config_path
            default_path = r"C:\Program Files\mosquitto\mosquitto.conf"
            if os.path.exists(os.path.dirname(default_path)):
                return default_path

        mosquitto_path = shutil.which("mosquitto")
        if mosquitto_path:
            install_dir = os.path.dirname(mosquitto_path)
            config_path = os.path.join(install_dir, "mosquitto.conf")
            if os.path.exists(config_path):
                return config_path
            brew_cfg = os.path.abspath(
                os.path.join(install_dir, "..", "etc", "mosquitto", "mosquitto.conf")
            )
            return brew_cfg

        return os.path.join(COMMON_PATHS[0], "mosquitto.conf")

    except Exception as e:
        logger.error("Error finding mosquitto.conf path: %s", e)
        return None


def create_mosquitto_config(install_path=None, app_data_path=None):
    """
    Create or update mosquitto.conf with required settings.
    
    Args:
        install_path: Installation directory (optional)
        app_data_path: Application data directory for log files (optional)
        
    Returns:
        bool: True if config created/updated successfully, False otherwise
    """
    try:
        config_path = find_mosquitto_config_path(install_path)
        
        if not config_path:
            logger.error("Could not determine mosquitto.conf path")
            return False
        
        logger.info(f"Configuring mosquitto.conf at: {config_path}")
        
        # Ensure log directory exists
        if app_data_path:
            log_dir = os.path.join(app_data_path, 'configuration_logs')
        elif IS_WINDOWS:
            # Fallback to default location
            log_dir = r"C:\MyAppData\DeviceConfiguration"
        else:
            log_dir = os.path.join(os.path.expanduser("~"), "Library", "Logs", "GMDC-Checkpoint-Config")
        os.makedirs(log_dir, exist_ok=True)
        log_file_path = os.path.join(log_dir, "mosquitto.log")

        # On macOS prefer an app-local config if system/brew path is not writable.
        if IS_DARWIN and app_data_path:
            local_cfg_dir = os.path.join(app_data_path, "mosquitto")
            os.makedirs(local_cfg_dir, exist_ok=True)
            local_cfg = os.path.join(local_cfg_dir, "mosquitto.conf")
            logger.info("Using app-local Mosquitto config on macOS: %s", local_cfg)
            config_path = local_cfg

        # Required configuration for Mosquitto 2.x
        # Note: log_dest file requires the path on the same line
        config_content = f"""# Mosquitto MQTT Broker Configuration
allow_anonymous true
listener 1883 0.0.0.0
protocol mqtt
listener 9001 0.0.0.0
protocol websockets
socket_domain ipv4
"""
        
        # Create directory if it doesn't exist
        config_dir = os.path.dirname(config_path)
        os.makedirs(config_dir, exist_ok=True)
        
        # Read existing config to merge settings (if exists)
        existing_content = ""
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
            except Exception as e:
                logger.warning(f"Could not read existing config: {e}")
        
        # Check if our settings already exist
        needs_update = True
        if existing_content:
            has_allow_anonymous = "allow_anonymous true" in existing_content
            has_listener = "listener 1883 0.0.0.0" in existing_content or "listener 1883" in existing_content
            has_ws_listener = (
                "listener 9001 0.0.0.0" in existing_content
                or "listener 9001" in existing_content
            )
            has_websockets = "protocol websockets" in existing_content
            has_socket_domain = "socket_domain ipv4" in existing_content
            # For Mosquitto 2.x, log_dest file must have the path on the same line
            # Check for "log_dest file " followed by a path (not just "log_dest file" alone)
            import re
            has_valid_log_dest = bool(re.search(r'log_dest\s+file\s+\S+', existing_content))
            has_log_type = "log_type all" in existing_content
            has_log_timestamp = "log_timestamp true" in existing_content
            has_log_format = "log_timestamp_format" in existing_content
            
            # Check for invalid old config format (log_dest file without path)
            has_invalid_log_dest = "log_dest file\n" in existing_content or "log_dest file\r\n" in existing_content
            
            if has_invalid_log_dest:
                logger.warning("Found invalid 'log_dest file' without path - config needs update")
                needs_update = True
            elif (
                has_allow_anonymous
                and has_listener
                and has_ws_listener
                and has_websockets
                and has_socket_domain
            ):
                # Log lines are optional; MQTT 1883 + WS 9001 are required.
                logger.info("Required MQTT/WS settings already present in config file")
                needs_update = False
                _ = (
                    has_valid_log_dest,
                    has_log_type,
                    has_log_timestamp,
                    has_log_format,
                )
        
        # Write config file
        if needs_update:
            try:
                # Try to get admin permissions or write to user-writable location
                # For Program Files, we might need admin rights
                try:
                    with open(config_path, 'w', encoding='utf-8') as f:
                        if existing_content and not existing_content.strip().startswith("# Mosquitto MQTT Broker Configuration"):
                            # Prepend our config to existing
                            f.write(config_content)
                            f.write("\n# Existing configuration below:\n")
                            f.write(existing_content)
                        else:
                            f.write(config_content)
                    
                    logger.info("mosquitto.conf created/updated successfully")
                    return True
                except PermissionError:
                    logger.warning(f"Permission denied writing to {config_path}. Falling back...")
                    
                    # Write config to temp file first
                    temp_config = os.path.join(tempfile.gettempdir(), "mosquitto_temp.conf")
                    try:
                        with open(temp_config, 'w', encoding='utf-8') as f:
                            if existing_content and not existing_content.strip().startswith("# Mosquitto MQTT Broker Configuration"):
                                f.write(config_content)
                                f.write("\n# Existing configuration below:\n")
                                f.write(existing_content)
                            else:
                                f.write(config_content)
                        
                        if IS_WINDOWS:
                            logger.info("Requesting admin privileges to write config file...")
                            success, error = run_elevated("cmd.exe", f'/c copy /Y "{temp_config}" "{config_path}"')
                            if success:
                                logger.info("Config file written with elevated privileges")
                                try:
                                    os.remove(temp_config)
                                except Exception:
                                    pass
                                return True
                            logger.error(f"Failed to write config with elevated privileges: {error}")

                        alt_path = os.path.join(os.path.expanduser("~"), "mosquitto.conf")
                        if IS_DARWIN and app_data_path:
                            alt_dir = os.path.join(app_data_path, "mosquitto")
                            os.makedirs(alt_dir, exist_ok=True)
                            alt_path = os.path.join(alt_dir, "mosquitto.conf")
                        shutil.copy2(temp_config, alt_path)
                        logger.warning(
                            "Config saved to %s. You may need to copy it to %s manually.",
                            alt_path,
                            config_path,
                        )
                        return True
                            
                    except Exception as e:
                        logger.error(f"Could not write config: {e}")
                        return False
            except Exception as e:
                logger.error(f"Error writing mosquitto.conf: {e}")
                return False
        else:
            logger.info("Config file already has required settings")
            return True
            
    except Exception as e:
        logger.error(f"Error creating mosquitto.conf: {e}")
        return False


def check_mosquitto_service():
    """
    Check if Mosquitto service/process exists and is running.
    
    Returns:
        tuple: (service_exists: bool, is_running: bool)
    """
    if IS_DARWIN:
        running = check_mosquitto_running_macos()
        # brew services counts as "exists" when formula is installed
        exists = check_mosquitto_installed()[0] or running
        logger.info("macOS Mosquitto process running=%s", running)
        return exists, running

    try:
        # Query service status
        result = subprocess.run(
            ["sc", "query", MOSQUITTO_SERVICE_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            **_subprocess_kwargs(),
        )
        
        if result.returncode == 0:
            output = result.stdout.decode('utf-8', errors='ignore')
            is_running = "RUNNING" in output.upper()
            logger.info(f"Mosquitto service exists. Running: {is_running}")
            return True, is_running
        else:
            logger.info("Mosquitto service does not exist")
            return False, False
            
    except Exception as e:
        logger.error(f"Error checking Mosquitto service: {e}")
        return False, False


def start_mosquitto_service(app_data_path=None):
    """
    Start the Mosquitto service (Windows service or macOS brew/daemon).
    """
    if IS_DARWIN:
        is_installed, install_path = check_mosquitto_installed()
        cfg = find_mosquitto_config_path(install_path) if is_installed else None
        return start_mosquitto_macos(
            install_path=install_path,
            config_path=cfg,
            app_data_path=app_data_path,
        )

    try:
        service_exists, is_running = check_mosquitto_service()
        
        if not service_exists:
            logger.warning("Mosquitto service does not exist. Service may need to be created manually.")
            return False
        
        if is_running:
            logger.info("Mosquitto service is already running")
            return True
        
        logger.info("Starting Mosquitto service...")
        
        # If already running as admin, use direct method
        if is_admin():
            result = subprocess.run(
                ["net", "start", MOSQUITTO_SERVICE_NAME],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                **_subprocess_kwargs(),
            )
            
            if result.returncode == 0:
                logger.info("Mosquitto service started successfully")
                return True
            else:
                error_msg = result.stderr.decode('utf-8', errors='ignore')
                logger.error(f"Failed to start Mosquitto service: {error_msg}")
                return False
        
        # Not running as admin - try normal method first
        result = subprocess.run(
            ["net", "start", MOSQUITTO_SERVICE_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            **_subprocess_kwargs(),
        )
        
        if result.returncode == 0:
            logger.info("Mosquitto service started successfully")
            return True
        
        error_msg = result.stderr.decode('utf-8', errors='ignore')
        logger.warning(f"Normal start failed: {error_msg}")
        
        # Try alternative method using sc command
        logger.info("Trying alternative method to start service...")
        result2 = subprocess.run(
            ["sc", "start", MOSQUITTO_SERVICE_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            **_subprocess_kwargs(),
        )
        
        if result2.returncode == 0:
            logger.info("Mosquitto service started successfully (alternative method)")
            return True
        
        logger.warning(f"Alternative start method also failed: {result2.stderr.decode('utf-8', errors='ignore')}")
        
        # Both methods failed - request elevation via UAC using PowerShell Start-Service
        logger.info("Requesting admin privileges to start Mosquitto service...")
        success, error = start_service_elevated(MOSQUITTO_SERVICE_NAME)
        
        if success:
            logger.info("Mosquitto service started successfully with elevated privileges")
            return True
        else:
            logger.error(f"Failed to start service with elevated privileges: {error}")
            
            # Run diagnostics to find the actual problem
            _, install_path = check_mosquitto_installed()
            if install_path:
                diag_result = diagnose_mosquitto_startup(install_path)
                logger.error(f"Mosquitto startup diagnostics: {diag_result}")
                
                # Check for common issues
                if "libssl" in diag_result.lower() or "libcrypto" in diag_result.lower() or "dll" in diag_result.lower():
                    logger.error("Missing OpenSSL DLLs detected. Mosquitto 2.x requires OpenSSL.")
                    logger.info("Please download OpenSSL from https://slproweb.com/products/Win32OpenSSL.html")
                elif "bind" in diag_result.lower() or "address already in use" in diag_result.lower():
                    logger.error("Port 1883 may already be in use by another application.")
                elif "config" in diag_result.lower() or "configuration" in diag_result.lower():
                    logger.error("Configuration file issue detected.")
            
            return False
                
    except subprocess.TimeoutExpired:
        logger.error("Timeout while starting Mosquitto service")
        return False
    except Exception as e:
        logger.error(f"Error starting Mosquitto service: {e}")
        return False


def setup_mosquitto(progress_callback=None, app_data_path=None):
    """
    Main setup function that orchestrates the entire Mosquitto installation and configuration process.
    Runs in background thread - all errors are logged but never raised.
    
    Args:
        progress_callback: Optional callback function(percent, message) for progress updates
        app_data_path: Application data directory for log files (optional)
    
    Returns:
        dict: Status information with keys: success, installed, configured, service_started
    """
    status = {
        "success": False,
        "installed": False,
        "configured": False,
        "service_started": False,
        "message": ""
    }
    
    def update_progress(percent, message):
        """Helper to call progress callback if provided"""
        if progress_callback:
            progress_callback(percent, message)
    
    try:
        logger.info("=" * 60)
        logger.info("Starting Mosquitto Broker Setup")
        logger.info("=" * 60)
        
        update_progress(0, "Checking Mosquitto installation...")
        
        # Step 1: Check if already installed
        is_installed, install_path = check_mosquitto_installed()
        
        if is_installed:
            logger.info("Mosquitto is already installed. Skipping installation.")
            status["installed"] = True
            update_progress(80, "Mosquitto already installed")
        elif IS_DARWIN:
            logger.info("Mosquitto not found. Installing via Homebrew...")
            update_progress(5, "Installing Mosquitto via Homebrew...")
            ok, detail = install_mosquitto_macos(update_progress)
            if not ok:
                status["message"] = detail or "Failed to install Mosquitto via Homebrew"
                logger.error(status["message"])
                return status
            status["installed"] = True
            update_progress(80, "Mosquitto installed successfully")
            time.sleep(1)
            is_installed, install_path = check_mosquitto_installed()
        elif IS_WINDOWS:
            # Step 2: Download Windows installer
            temp_dir = tempfile.gettempdir()
            installer_filename = f"mosquitto-{MOSQUITTO_VERSION}-installer.exe"
            installer_path = os.path.join(temp_dir, installer_filename)
            
            logger.info("Mosquitto not found. Proceeding with installation...")
            update_progress(0, "Downloading Mosquitto installer...")
            
            # Pass progress callback for download progress (scale 0-50% of overall 0-80%)
            def download_progress(percent, msg):
                # Scale download progress from 0% to 50% of the 0-80% range
                # So 0% download = 0% overall, 100% download = 50% overall (40% of 80%)
                scaled_percent = int(percent * 0.40)  # 0-40% for download
                update_progress(scaled_percent, msg)
            
            if not download_mosquitto_installer(installer_path, download_progress):
                status["message"] = "Failed to download Mosquitto installer"
                logger.error(status["message"])
                return status
            
            # Step 3: Install Mosquitto (40-80% of overall)
            update_progress(40, "Installing Mosquitto (Admin approval may be required)...")
            if not install_mosquitto(installer_path):
                status["message"] = "Failed to install Mosquitto"
                logger.error(status["message"])
                # Clean up installer
                try:
                    if os.path.exists(installer_path):
                        os.remove(installer_path)
                except Exception:
                    pass
                return status
            
            status["installed"] = True
            logger.info("Mosquitto installed successfully")
            update_progress(80, "Mosquitto installed successfully")
            
            # Clean up installer
            try:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
                    logger.info("Installer file cleaned up")
            except Exception as e:
                logger.warning(f"Could not remove installer file: {e}")
            
            # Wait a moment for installation to complete
            time.sleep(2)
            
            # Re-check install path after installation
            is_installed, install_path = check_mosquitto_installed()
        else:
            status["message"] = (
                f"Automatic Mosquitto install is not supported on this platform ({sys.platform}). "
                "Install mosquitto manually and ensure it is on PATH."
            )
            logger.error(status["message"])
            return status
        
        # Step 4: Create/update configuration (81-90% of overall)
        update_progress(81, "Configuring Mosquitto...")
        if is_installed:
            if create_mosquitto_config(install_path, app_data_path):
                status["configured"] = True
                logger.info("Mosquitto configuration completed")
                update_progress(90, "Configuration completed")
            else:
                status["message"] = "Mosquitto installed but configuration failed"
                logger.warning(status["message"])
        else:
            status["message"] = "Could not verify Mosquitto installation"
            logger.warning(status["message"])
            return status
        
        # Step 5: Start service (91-100% of overall)
        update_progress(91, "Starting Mosquitto service...")
        if start_mosquitto_service(app_data_path=app_data_path):
            status["service_started"] = True
            logger.info("Mosquitto service started")
            update_progress(100, "Mosquitto service running!")
        else:
            status["message"] = "Mosquitto configured but service could not be started"
            logger.warning(status["message"])
            update_progress(100, "Service could not be started (may need manual start)")
            # This is not a critical failure - service might need manual start
        
        # Overall success
        if status["installed"] and status["configured"]:
            status["success"] = True
            if not status["message"]:
                status["message"] = "Mosquitto setup completed successfully"
        
        logger.info("=" * 60)
        logger.info("Mosquitto Broker Setup Complete")
        logger.info(f"Status: {status['message']}")
        logger.info("=" * 60)
        
    except Exception as e:
        status["message"] = f"Unexpected error during Mosquitto setup: {str(e)}"
        logger.error(status["message"], exc_info=True)
    
    return status
