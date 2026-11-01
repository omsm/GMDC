#!/bin/bash
# Wait until a real LAN IPv4 is up (not only loopback).
# Optional: set LAN_PING_HOST to also require ping success (e.g. gateway or OCI host).

set -euo pipefail

MAX_WAIT_SEC="${LAN_WAIT_SEC:-180}"
PING_HOST="${LAN_PING_HOST:-}"
SLEEP_SEC=2

has_lan_ip() {
  # Any non-loopback IPv4
  ifconfig -a 2>/dev/null | awk '
    /^[a-z]/ { iface=$1; sub(":$","",iface) }
    /inet / {
      ip=$2
      if (iface != "lo0" && ip != "127.0.0.1" && ip !~ /^169\.254\./) {
        found=1
        exit
      }
    }
    END { exit(found ? 0 : 1) }
  '
}

can_ping() {
  [[ -z "$PING_HOST" ]] && return 0
  ping -c 1 -W 1000 "$PING_HOST" >/dev/null 2>&1
}

echo "[$(date '+%F %T')] Waiting for LAN (max ${MAX_WAIT_SEC}s)..."
elapsed=0
while (( elapsed < MAX_WAIT_SEC )); do
  if has_lan_ip && can_ping; then
    echo "[$(date '+%F %T')] LAN is up."
    exit 0
  fi
  sleep "$SLEEP_SEC"
  elapsed=$((elapsed + SLEEP_SEC))
done

echo "[$(date '+%F %T')] WARNING: LAN wait timed out after ${MAX_WAIT_SEC}s — starting anyway."
exit 0
