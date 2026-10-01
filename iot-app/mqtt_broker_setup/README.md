# Shared Mosquitto MQTT broker bootstrap for GMDC IoT apps
#
# Ensures local Mosquitto listens on:
#   1883  – MQTT (backend / digitizer / display)
#   9001  – WebSockets (frontend dashboard)
#
# Usage from any sibling app:
#
#   import sys
#   from pathlib import Path
#   root = Path(__file__).resolve().parent.parent
#   sys.path.insert(0, str(root))
#   from mqtt_broker_setup import ensure_mqtt_broker_ready, add_package_to_sys_path
#   # or:
#   from mqtt_broker_setup.ensure import add_package_to_sys_path, ensure_mqtt_broker_ready
#   add_package_to_sys_path()
#   ok, msg = ensure_mqtt_broker_ready(app_data_path=...)
#
# On Windows the official Mosquitto installer is downloaded when needed.
# On macOS: prefer vendored Homebrew bottles under Mines-Automation/vendor/
# (or packaging/macos/vendor/); otherwise brew install (network). Homebrew
# itself can be bootstrapped from vendor/homebrew/brew.tar.gz or install.sh.
# Conf is written with listeners 1883 + 9001, then the broker is started as a service.
