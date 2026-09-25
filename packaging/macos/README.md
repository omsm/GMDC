# macOS offline packaging (PyInstaller)

Build machine needs Python 3.11+ and network **once** to download wheels into a venv.
Target Macs need **no** Python and **no** internet for the app binaries.

## Output layout

```text
dist/Mines-Automation/
  iot-configuration      # GUI commissioning (checkpoint-config)
  automation             # reads iot_configuration.json → starts CP or WB
  mines-checkpoint
  mines-weighbridge
  iot_configuration.json
  conversion.py
  timeout_config.py
  .env
  voice/
  README-DEPLOY.txt
```

On macOS there is **no** `.exe` extension; binaries are Mach-O executables.

## Build

```bash
chmod +x packaging/macos/build_macos.sh
./packaging/macos/build_macos.sh
```

Result: `dist/Mines-Automation/` — zip or copy that folder to site Macs.

## Site Mac usage

1. **Mosquitto** must already be available locally (1883 MQTT / 9001 WebSocket).  
   The bundled apps do not download Python or Mosquitto at runtime.
2. Run `./iot-configuration` once to set `checkpoint_type` and hardware.
3. Run `./automation` — it starts `mines-checkpoint` or `mines-weighbridge` from the JSON.

If Gatekeeper blocks unsigned binaries:

```bash
cd Mines-Automation
xattr -cr .
# or right-click → Open the first time
```

## Specs

| Spec | Binary |
|------|--------|
| `iot_configuration.spec` | `iot-configuration` |
| `automation.spec` | `automation` |
| `mines_checkpoint.spec` | `mines-checkpoint` |
| `mines_weighbridge.spec` | `mines-weighbridge` |

Sidecar files (`conversion.py`, `timeout_config.py`, `.env`, `voice/`, JSON) stay **outside** the binaries so sites can edit them without rebuilding.
