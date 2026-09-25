# Vendored Homebrew + Mosquitto bottles (macOS offline install)

This folder is populated on the **build Mac** and copied into `dist/Mines-Automation/vendor/`
so site Macs can install Mosquitto without downloading Homebrew packages.

## Layout (mostly gitignored)

```text
vendor/
  README.md                 # this file (tracked)
  download_vendor.sh        # tracked
  VENDOR_INFO.txt           # generated
  homebrew/
    install.sh              # official Homebrew installer script
    brew.tar.gz             # Homebrew/brew source (user-prefix bootstrap)
  bottles/
    arm64/*.bottle.tar.gz
    x86_64/*.bottle.tar.gz
```

## Populate (build Mac, once / when bottles go stale)

```bash
chmod +x packaging/macos/vendor/download_vendor.sh
./packaging/macos/vendor/download_vendor.sh          # current arch
./packaging/macos/vendor/download_vendor.sh --arch both
```

`build_macos.sh` runs the download automatically when bottles are missing, then
copies `vendor/` into the Mines-Automation bundle.

## Runtime behaviour (`mqtt_broker_setup`)

1. If Mosquitto already present → use it  
2. Else ensure Homebrew (system brew → local `brew.tar.gz` bootstrap → local `install.sh` → download install.sh)  
3. Install Mosquitto from local bottles when present; otherwise `brew install mosquitto` (network)

Do **not** commit bottle tarballs or `homebrew/` payloads — they are large and OS-specific.
