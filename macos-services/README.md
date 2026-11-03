# macOS service control (like Linux systemctl)

Run **Mines-WB** or **Mines-Checkpoint** on a Mac Mini as a durable LaunchAgent (KeepAlive). Only **one** app per Mac.

**Product version:** 1.22 (see [`../version.md`](../version.md))

---

## Requirements

| Item | Value |
|------|--------|
| User | `csm-gmdc` |
| Project root | `/Users/csm-gmdc/GMDC_IOT` |
| Python | App-local `pyenv` under `Mines-WB/` or `Mines-Checkpoint/` |
| Login | Automatic login for `csm-gmdc` |
| Power | No sleep; start after power failure |

> **Do not** keep the tree under `~/Downloads`. LaunchAgents cannot execute scripts there (`Operation not permitted`, exit `126`).

---

## First-time install checklist

### 1. Place the project

```bash
# Preferred location
/Users/csm-gmdc/GMDC_IOT/

# If it is still in Downloads:
mv ~/Downloads/GMDC_IOT ~/GMDC_IOT
# or use: bash .../macos-services/migrate-out-of-downloads.sh
xattr -dr com.apple.quarantine ~/GMDC_IOT
```

### 2. Create the app Python env

**Weighbridge Mac:**

```bash
cd /Users/csm-gmdc/GMDC_IOT/Mines-WB
python3 -m venv pyenv
source pyenv/bin/activate
pip install -U pip
pip install -e ../gmdc_common
pip install -r requirements.txt
cp -n .env.example .env   # if needed; edit site values
python main.py            # smoke test, then Ctrl+C
deactivate
```

**Checkpoint Mac:** same steps under `Mines-Checkpoint/`.

Confirm:

```text
/Users/csm-gmdc/GMDC_IOT/Mines-WB/pyenv/bin/python3
# or
/Users/csm-gmdc/GMDC_IOT/Mines-Checkpoint/pyenv/bin/python3
```

### 3. Fix line endings and permissions

Scripts copied from Windows may have CRLF. Fix once:

```bash
cd /Users/csm-gmdc/GMDC_IOT/macos-services
sed -i '' $'s/\r$//' *.sh *.command *.plist
chmod +x *.sh *.command
```

### 4. Enable the service (one app only)

```bash
# Weighbridge
./enable-mines-wb.sh

# OR Checkpoint
./enable-mines-checkpoint.sh
```

`enable` = Linux `systemctl enable --now` (loads the agent and starts now).

### 5. Verify

```bash
# WB
launchctl print gui/$(id -u)/co.gmdc.mines-wb | grep -E 'state|pid|last exit'

# Checkpoint
launchctl print gui/$(id -u)/co.gmdc.mines-checkpoint | grep -E 'state|pid|last exit'

tail -f /Users/csm-gmdc/GMDC_IOT/logs/mines-wb-service.err.log
# or mines-checkpoint-service.err.log
```

Want: `state = running` and a numeric `pid`.

### 6. Reboot test

Reboot once. After automatic login, the same LaunchAgent should show `running` again without opening Terminal.

---

## Linux → macOS mapping

| Linux | macOS (Weighbridge) | macOS (Checkpoint) |
|-------|---------------------|--------------------|
| `sudo systemctl enable x.service` | `bash .../enable-mines-wb.sh` | `bash .../enable-mines-checkpoint.sh` |
| `sudo systemctl disable x.service` | `bash .../disable-mines-wb.sh` | `bash .../disable-mines-checkpoint.sh` |
| `sudo systemctl start x.service` | `bash .../start-mines-wb.sh` | `bash .../start-mines-checkpoint.sh` |
| `sudo systemctl stop x.service` | `bash .../stop-mines-wb.sh` | `bash .../stop-mines-checkpoint.sh` |

Meaning:

1. **enable** — autostart at login/power-on (also starts now).
2. **disable** — remove autostart permanently (and stop now).
3. **start** — start now (agent must already be enabled).
4. **stop** — stop now (autostart stays on for next login).

---

## 1. Enable service

```bash
bash /Users/csm-gmdc/GMDC_IOT/macos-services/enable-mines-wb.sh
# or
bash /Users/csm-gmdc/GMDC_IOT/macos-services/enable-mines-checkpoint.sh
```

## 2. Disable service

```bash
bash /Users/csm-gmdc/GMDC_IOT/macos-services/disable-mines-wb.sh
# or
bash /Users/csm-gmdc/GMDC_IOT/macos-services/disable-mines-checkpoint.sh
```

## 3. Start service

```bash
bash /Users/csm-gmdc/GMDC_IOT/macos-services/start-mines-wb.sh
# or
bash /Users/csm-gmdc/GMDC_IOT/macos-services/start-mines-checkpoint.sh
```

## 4. Stop service

```bash
bash /Users/csm-gmdc/GMDC_IOT/macos-services/stop-mines-wb.sh
# or
bash /Users/csm-gmdc/GMDC_IOT/macos-services/stop-mines-checkpoint.sh
```

After stop, optional Terminal debug:

```bash
open /Users/csm-gmdc/GMDC_IOT/macos-services/debug-mines-wb.command
# or
open /Users/csm-gmdc/GMDC_IOT/macos-services/debug-mines-checkpoint.command
```

---

## Fix: Operation not permitted (exit 126)

If logs show:

```text
/bin/bash: .../service-mines-wb.sh: Operation not permitted
last exit code = 126
```

the tree is still under Downloads (or quarantine). Fix:

```bash
launchctl bootout gui/$(id -u)/co.gmdc.mines-wb 2>/dev/null
rm -f ~/Library/LaunchAgents/co.gmdc.mines-wb.plist

mv ~/Downloads/GMDC_IOT ~/GMDC_IOT
xattr -dr com.apple.quarantine ~/GMDC_IOT

cd ~/GMDC_IOT/macos-services
chmod +x *.sh *.command
./enable-mines-wb.sh
```

Helper (from the old Downloads copy):

```bash
bash ~/Downloads/GMDC_IOT/macos-services/migrate-out-of-downloads.sh
cd ~/GMDC_IOT/macos-services && ./enable-mines-wb.sh
```

---

## Remove old service → install this one

Old method used **Login Items** + Terminal (`.command` / `UNKNOWN` / `MinesWBStart`).  
New method uses **launchd KeepAlive** only.

### Step A — remove the old one

```bash
launchctl bootout gui/$(id -u)/co.gmdc.mines-wb 2>/dev/null
launchctl bootout gui/$(id -u)/co.gmdc.mines-checkpoint 2>/dev/null
rm -f ~/Library/LaunchAgents/co.gmdc.mines-wb.plist
rm -f ~/Library/LaunchAgents/co.gmdc.mines-checkpoint.plist
```

**System Settings → General → Login Items** — remove:

- `UNKNOWN`
- `run-mines-wb-in-terminal`
- `run-mines-checkpoint-in-terminal`
- `MinesWBStart`
- `MinesCheckpointStart`

```bash
pkill -f "Mines-WB/pyenv/bin/python3 main.py" 2>/dev/null
pkill -f "Mines-Checkpoint/pyenv/bin/python3 main.py" 2>/dev/null
```

### Step B — install the new one

Copy updated `macos-services` into `/Users/csm-gmdc/GMDC_IOT/macos-services/`, then:

```bash
cd /Users/csm-gmdc/GMDC_IOT/macos-services
sed -i '' $'s/\r$//' *.sh *.command *.plist
chmod +x *.sh *.command
./enable-mines-wb.sh          # OR ./enable-mines-checkpoint.sh
```

### Step C — verify

```bash
launchctl print gui/$(id -u)/co.gmdc.mines-wb | grep -E 'state|pid'
```

Also set once: automatic login for `csm-gmdc`, Energy Saver no sleep / start after power failure.

---

## How it works

| File | Role |
|------|------|
| `co.gmdc.mines-wb.plist` / `co.gmdc.mines-checkpoint.plist` | LaunchAgent templates (`KeepAlive`, `RunAtLoad`) |
| `enable-*.sh` | Install plist under `~/Library/LaunchAgents` and bootstrap |
| `disable-*.sh` | bootout + remove plist |
| `start-*.sh` / `stop-*.sh` | kickstart / kill without removing the agent |
| `service-*.sh` | Wait for LAN, then `exec` app `pyenv` python `main.py` |
| `wait-for-lan.sh` | Poll until a non-loopback IPv4 appears |
| `_common.sh` | Shared paths (`ROOT=/Users/csm-gmdc/GMDC_IOT`) |
| `debug-*.command` | Manual Terminal run after `stop` |
| `migrate-out-of-downloads.sh` | Move tree out of Downloads + clear quarantine |

Service stdout/stderr:

```text
/Users/csm-gmdc/GMDC_IOT/logs/mines-wb-service.out.log
/Users/csm-gmdc/GMDC_IOT/logs/mines-wb-service.err.log
/Users/csm-gmdc/GMDC_IOT/logs/mines-checkpoint-service.out.log
/Users/csm-gmdc/GMDC_IOT/logs/mines-checkpoint-service.err.log
```

---

## Note about `enable-mines-wb.sh`

It matches Linux:

`sudo systemctl enable --now x.service`

because `RunAtLoad` starts the app when the agent is loaded. Use `stop` if you only want it stopped until next login / next `start`.
