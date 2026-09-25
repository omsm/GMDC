"""
Detect this PC's LAN IPv4 for storage as device_ip in iot_configuration.json.

Preference order:
  1. Ethernet (wired) interface with a usable IPv4
  2. Wi-Fi / other non-loopback IPv4
  3. UDP "route trick" fallback (outbound socket local address)
"""

from __future__ import annotations

import logging
import platform
import re
import socket
import subprocess
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_PRIVATE_OR_LINK = re.compile(
    r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.|169\.254\.)"
)


def _is_usable_ipv4(ip: str) -> bool:
    if not ip or not isinstance(ip, str):
        return False
    ip = ip.strip()
    if ip in ("", "0.0.0.0", "127.0.0.1"):
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    if any(n < 0 or n > 255 for n in nums):
        return False
    if nums[0] == 127:
        return False
    return True


def _classify_iface(name: str, media_hint: str = "") -> str:
    """Return 'ethernet', 'wifi', or 'other'."""
    n = (name or "").lower()
    m = (media_hint or "").lower()
    blob = f"{n} {m}"
    if any(
        x in blob
        for x in (
            "wi-fi",
            "wifi",
            "wireless",
            "wlan",
            "airport",
            "wlp",
            "wlx",
        )
    ):
        return "wifi"
    if any(
        x in blob
        for x in (
            "ethernet",
            "lan",
            "enp",
            "ens",
            "eth",
            "usb 10/100",
            "thunderbolt",
            "bridge",
        )
    ):
        # en0 on older Macs can be Wi-Fi — rely on media_hint when present
        if "wi-fi" in m or "wifi" in m or "wireless" in m:
            return "wifi"
        return "ethernet"
    # Generic en* without hint — treat as other (often Wi-Fi on Apple Silicon)
    if n.startswith("en"):
        return "other"
    return "other"


def _macos_hardware_ports() -> List[Tuple[str, str, str]]:
    """
    List (device, hardware_port_label, kind) via networksetup.
    kind is ethernet | wifi | other.
    """
    try:
        out = subprocess.check_output(
            ["networksetup", "-listallhardwareports"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    ports: List[Tuple[str, str, str]] = []
    current_port = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Hardware Port:"):
            current_port = line.split(":", 1)[1].strip()
        elif line.startswith("Device:") and current_port:
            device = line.split(":", 1)[1].strip()
            kind = _classify_iface(device, current_port)
            ports.append((device, current_port, kind))
            current_port = ""
    return ports


def _macos_ifaddr(device: str) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["ipconfig", "getifaddr", device],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
        return out if _is_usable_ipv4(out) else None
    except (OSError, subprocess.SubprocessError):
        return None


def _linux_iface_addrs() -> List[Tuple[str, str, str]]:
    """(iface, ip, kind) from `ip -4 -o addr show`."""
    results: List[Tuple[str, str, str]] = []
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return results
    for line in out.splitlines():
        # 2: eth0    inet 192.168.1.10/24 ...
        parts = line.split()
        if len(parts) < 4:
            continue
        iface = parts[1].rstrip(":")
        if iface == "lo" or iface.startswith("docker") or iface.startswith("veth"):
            continue
        cidr = parts[3]
        ip = cidr.split("/")[0]
        if not _is_usable_ipv4(ip):
            continue
        results.append((iface, ip, _classify_iface(iface)))
    return results


def _windows_iface_addrs() -> List[Tuple[str, str, str]]:
    """Best-effort via PowerShell Get-NetIPAddress + Get-NetAdapter."""
    ps = (
        "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
        "Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | "
        "ForEach-Object { "
        "$a = Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue; "
        "$media = if ($a) { $a.MediaType + ' ' + $a.InterfaceDescription + ' ' + $a.Name } else { '' }; "
        "Write-Output ($_.IPAddress + '|' + $_.InterfaceAlias + '|' + $media) "
        "}"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    results: List[Tuple[str, str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        bits = line.split("|", 2)
        if len(bits) < 2:
            continue
        ip, alias = bits[0].strip(), bits[1].strip()
        media = bits[2].strip() if len(bits) > 2 else ""
        if not _is_usable_ipv4(ip):
            continue
        results.append((alias, ip, _classify_iface(alias, media)))
    return results


def _udp_fallback_ip() -> Optional[str]:
    """Local address used for an outbound UDP datagram (no packets sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip if _is_usable_ipv4(ip) else None
    except OSError:
        return None


def list_candidate_ips() -> List[Tuple[str, str, str]]:
    """
    Return list of (iface_or_label, ip, kind) with kind in ethernet|wifi|other.
    Ethernet entries first, then wifi, then other.
    """
    system = platform.system().lower()
    found: List[Tuple[str, str, str]] = []

    if system == "darwin":
        for device, label, kind in _macos_hardware_ports():
            ip = _macos_ifaddr(device)
            if ip:
                found.append((f"{label} ({device})", ip, kind))
    elif system == "linux":
        found.extend(_linux_iface_addrs())
    elif system == "windows":
        found.extend(_windows_iface_addrs())

    # Deduplicate by IP, keep first (prefer earlier ethernet listing)
    seen = set()
    unique: List[Tuple[str, str, str]] = []
    for item in found:
        if item[1] in seen:
            continue
        seen.add(item[1])
        unique.append(item)

    order = {"ethernet": 0, "wifi": 1, "other": 2}
    unique.sort(key=lambda t: order.get(t[2], 9))
    return unique


def detect_device_ip() -> Optional[str]:
    """
    Pick the best LAN IPv4 for this PC.
    Prefer Ethernet; fall back to Wi-Fi / other; then UDP route trick.
    """
    candidates = list_candidate_ips()
    for label, ip, kind in candidates:
        if kind == "ethernet":
            logger.info("Selected Ethernet device_ip=%s (%s)", ip, label)
            return ip
    for label, ip, kind in candidates:
        if kind == "wifi":
            logger.info("Selected Wi-Fi device_ip=%s (%s)", ip, label)
            return ip
    for label, ip, kind in candidates:
        logger.info("Selected device_ip=%s (%s, kind=%s)", ip, label, kind)
        return ip

    fallback = _udp_fallback_ip()
    if fallback:
        logger.info("Selected device_ip=%s via UDP fallback", fallback)
        return fallback

    logger.warning("Could not detect a local LAN IP for device_ip")
    return None
