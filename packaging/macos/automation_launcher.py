#!/usr/bin/env python3
"""
GMDC Mines Automation launcher (macOS / Windows frozen binary).

Reads iot_configuration.json next to this executable, then starts:
  - mines-checkpoint   when checkpoint_type is checkpoint
  - mines-weighbridge  when checkpoint_type is weighbridge

Usage (from Mines-Automation folder):
  ./automation
  ./automation --config /path/to/iot_configuration.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CHECKPOINT_TYPES = frozenset(
    {
        "checkpoint",
        "mines_entry",
        "tracking_1",
        "tracking_2",
        "mines_exit",
    }
)
WEIGHBRIDGE_TYPES = frozenset(
    {
        "weighbridge",
        "tare_wb",
        "vadaghat_wb",
        "gross_wb",
    }
)


def install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def binary_name(base: str) -> str:
    if sys.platform.startswith("win"):
        return f"{base}.exe"
    return base


def resolve_child_binary(root: Path, base: str) -> Path:
    name = binary_name(base)
    candidate = root / name
    if candidate.is_file():
        return candidate
    # onedir layout fallback: Mines-Automation/mines-checkpoint/mines-checkpoint
    nested = root / base / name
    if nested.is_file():
        return nested
    raise FileNotFoundError(
        f"Missing runtime binary: {candidate}\n"
        f"(also checked {nested})\n"
        "Build/copy mines-checkpoint and mines-weighbridge into Mines-Automation/."
    )


def load_checkpoint_type(config_path: Path) -> str:
    if not config_path.is_file():
        raise FileNotFoundError(
            f"iot_configuration.json not found:\n  {config_path}\n"
            "Run ./iot-configuration first to commission this site."
        )
    with config_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    ctype = str(data.get("checkpoint_type") or "").strip().lower()
    if not ctype:
        raise ValueError(
            f"{config_path} has no checkpoint_type.\n"
            "Finish setup in iot-configuration before starting automation."
        )
    return ctype


def select_runtime(checkpoint_type: str) -> str:
    if checkpoint_type in CHECKPOINT_TYPES:
        return "mines-checkpoint"
    if checkpoint_type in WEIGHBRIDGE_TYPES:
        return "mines-weighbridge"
    raise ValueError(
        f"Unknown checkpoint_type={checkpoint_type!r}.\n"
        f"Expected one of: {sorted(CHECKPOINT_TYPES | WEIGHBRIDGE_TYPES)}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GMDC Mines Automation launcher")
    parser.add_argument(
        "--config",
        default="",
        help="Path to iot_configuration.json (default: next to this binary)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print which binary would start, then exit",
    )
    args = parser.parse_args(argv)

    root = install_root()
    config_path = (
        Path(args.config).expanduser().resolve()
        if args.config
        else root / "iot_configuration.json"
    )

    print(f"[automation] install root : {root}")
    print(f"[automation] config       : {config_path}")

    try:
        ctype = load_checkpoint_type(config_path)
        runtime = select_runtime(ctype)
        binary = resolve_child_binary(root, runtime)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[automation] ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"[automation] checkpoint_type={ctype} → {runtime}")
    print(f"[automation] starting: {binary}")

    if args.dry_run:
        return 0

    env = os.environ.copy()
    env["IOT_CONFIG_PATH"] = str(config_path)
    env["GMDC_INSTALL_ROOT"] = str(root)
    # Child cwd = install root so relative voice/, .env, logs work
    try:
        proc = subprocess.Popen(
            [str(binary)],
            cwd=str(root),
            env=env,
        )
    except OSError as exc:
        print(f"[automation] failed to start {binary}: {exc}", file=sys.stderr)
        return 1

    print(f"[automation] pid={proc.pid} — waiting (Ctrl+C stops launcher only)")
    try:
        return int(proc.wait())
    except KeyboardInterrupt:
        print("\n[automation] interrupted — terminating child…")
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
