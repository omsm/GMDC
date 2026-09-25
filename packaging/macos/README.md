# macOS offline packaging (PyInstaller)

Build machine needs Python 3.11+ and network **once** to download wheels into a venv
and (optionally) Homebrew Mosquitto bottles into `packaging/macos/vendor/`.
Target Macs need **no** Python. Mosquitto is installed from the bundled `vendor/`
when possible; otherwise Homebrew may download once.

## Output layout

```text
dist/Mines-Automation/
  iot-configuration      # GUI commissioning (checkpoint-config)
  automation             # reads iot_configuration.json → starts CP or WB
  mines-checkpoint
  mines-weighbridge
  vendor/                # Homebrew installer + Mosquitto bottles (gitignored source)
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

The build script auto-runs `vendor/download_vendor.sh` when bottles / Homebrew
installer are missing (requires brew + network on the build Mac). To refresh
manually:

```bash
./packaging/macos/vendor/download_vendor.sh
./packaging/macos/vendor/download_vendor.sh --arch both   # arm64 + Intel bottles
```

Result: `dist/Mines-Automation/` — zip or copy that folder to site Macs.
Do **not** commit `vendor/homebrew/` or `vendor/bottles/` (see root `.gitignore`).

## Site Mac usage

1. Run `./iot-configuration` once. It installs Mosquitto from `vendor/` when present
   (local bottles → user Homebrew bootstrap → local `install.sh` → network fallback).
2. Complete commissioning (`checkpoint_type` + hardware).
3. Run `./automation` — starts `mines-checkpoint` or `mines-weighbridge` from the JSON.

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

Sidecar files (`conversion.py`, `timeout_config.py`, `.env`, `voice/`, JSON, `vendor/`) stay **outside** the binaries so sites can edit or refresh them without rebuilding.
