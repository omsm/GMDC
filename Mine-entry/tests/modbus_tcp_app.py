"""
Modbus TCP Test Application (Ethernet controller).

This app supports:
- Read function code: FC1 (read coils) or FC2 (read discrete inputs)
- Write function code: FC5 (write single coil) or FC6 (write single register)

Function codes and DI/DO ranges can be passed via CLI or entered interactively.
"""

import argparse
import os
import sys
import time
from typing import Optional

_PKG_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:
    try:
        from pymodbus.client.sync import ModbusTcpClient
    except ImportError:
        print("Error: pymodbus is not installed. Run: pip install pymodbus")
        sys.exit(1)

from utils.pymodbus_compat import (
    pymodbus_unit_kw,
    read_coils_compat,
    write_coil_compat,
)


class ModbusTcpApp:
    def __init__(
        self,
        host: str,
        port: int,
        slave_id: int,
        timeout: float,
        read_fc: int,
        write_fc: int,
        di_start: int,
        di_count: int,
        do_start: int,
        do_count: int,
    ):
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.timeout = timeout
        self.read_fc = read_fc
        self.write_fc = write_fc
        self.di_start = di_start
        self.di_count = di_count
        self.do_start = do_start
        self.do_count = do_count
        self.client: Optional[ModbusTcpClient] = None

    def connect(self) -> bool:
        self.client = ModbusTcpClient(self.host, port=self.port, timeout=self.timeout)
        if self.client.connect():
            print(f"[OK] Connected to {self.host}:{self.port}")
            return True
        print(f"[ERROR] Could not connect to {self.host}:{self.port}")
        return False

    def disconnect(self) -> None:
        if self.client:
            self.client.close()
        print("[OK] Disconnected")

    def _read_inputs(self, start: int, count: int):
        if not self.client:
            return None
        if self.read_fc == 2:
            method = self.client.read_discrete_inputs
            return method(
                address=start,
                count=count,
                **pymodbus_unit_kw(method, self.slave_id),
            )
        return read_coils_compat(self.client, start, count, self.slave_id)

    def _write_output(self, address: int, state: bool):
        if not self.client:
            return None
        if self.write_fc == 6:
            method = self.client.write_register
            return method(
                address=address,
                value=1 if state else 0,
                **pymodbus_unit_kw(method, self.slave_id),
            )
        return write_coil_compat(self.client, address, state, self.slave_id)

    def monitor_inputs(self, interval: float = 0.5) -> None:
        print("\n" + "=" * 60)
        print("INPUT MONITOR")
        print("=" * 60)
        print(f"Read FC: {self.read_fc}, range: {self.di_start}-{self.di_start + self.di_count - 1}")
        print("Press Ctrl+C to stop")
        print("-" * 60)

        try:
            while True:
                result = self._read_inputs(self.di_start, self.di_count)
                if result is None:
                    print("[ERROR] Client not connected")
                elif result.isError():
                    print(f"[ERROR] Read failed: {result}")
                else:
                    bits = list(result.bits[: self.di_count])
                    stamp = time.strftime("%H:%M:%S")
                    as_binary = "".join("1" if v else "0" for v in bits)
                    print(f"[{stamp}] Inputs: {bits} | Binary: {as_binary}")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[INFO] Monitor stopped")

    def test_outputs(self) -> None:
        print("\n" + "=" * 60)
        print("OUTPUT TEST")
        print("=" * 60)
        print(f"Write FC: {self.write_fc}, range: {self.do_start}-{self.do_start + self.do_count - 1}")
        print("-" * 60)
        for i in range(self.do_count):
            addr = self.do_start + i
            for state in (True, False):
                label = "ON" if state else "OFF"
                print(f"Address {addr} -> {label}")
                result = self._write_output(addr, state)
                if result is None:
                    print("  [ERROR] Client not connected")
                elif result.isError():
                    print(f"  [ERROR] Write failed: {result}")
                else:
                    print("  [OK]")
                time.sleep(0.6 if state else 0.3)

    def repl(self) -> None:
        print("\n" + "=" * 60)
        print("Interactive Modbus TCP App")
        print("=" * 60)
        print("Commands:")
        print("  read [start] [count]   - Read inputs using configured read FC")
        print("  write <addr> <0|1>     - Write one output using configured write FC")
        print("  monitor                - Monitor default input range")
        print("  test                   - Test default output range")
        print("  config                 - Show active configuration")
        print("  quit                   - Exit")

        while True:
            try:
                raw = input(f"modbus[{self.host}]> ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                break

            if not raw:
                continue

            parts = raw.split()
            cmd = parts[0].lower()

            if cmd in {"quit", "exit", "q"}:
                break
            if cmd == "config":
                print(
                    f"Host={self.host}:{self.port}, slave={self.slave_id}, timeout={self.timeout}, "
                    f"read_fc={self.read_fc}, write_fc={self.write_fc}, "
                    f"di={self.di_start}/{self.di_count}, do={self.do_start}/{self.do_count}"
                )
            elif cmd == "read":
                start = self.di_start
                count = self.di_count
                if len(parts) >= 2:
                    start = int(parts[1])
                if len(parts) >= 3:
                    count = int(parts[2])
                result = self._read_inputs(start, count)
                if result is None:
                    print("[ERROR] Client not connected")
                elif result.isError():
                    print(f"[ERROR] Read failed: {result}")
                else:
                    bits = list(result.bits[:count])
                    print(f"[OK] Read {count} @ {start}: {bits}")
            elif cmd == "write":
                if len(parts) != 3:
                    print("Usage: write <addr> <0|1>")
                    continue
                addr = int(parts[1])
                state = parts[2] in {"1", "on", "true", "True"}
                result = self._write_output(addr, state)
                if result is None:
                    print("[ERROR] Client not connected")
                elif result.isError():
                    print(f"[ERROR] Write failed: {result}")
                else:
                    print("[OK] Write success")
            elif cmd == "monitor":
                self.monitor_inputs()
            elif cmd == "test":
                self.test_outputs()
            else:
                print(f"Unknown command: {cmd}")


def choose_fc(name: str, cli_value: Optional[int], allowed: tuple[int, int], default_value: int) -> int:
    if cli_value in allowed:
        return cli_value
    while True:
        raw = input(f"{name} function code {allowed} [default {default_value}]: ").strip()
        if not raw:
            return default_value
        try:
            value = int(raw)
            if value in allowed:
                return value
        except ValueError:
            pass
        print(f"Invalid value. Use one of: {allowed}")


def choose_int(name: str, cli_value: Optional[int], default_value: int, minimum: int = 0) -> int:
    if cli_value is not None and cli_value >= minimum:
        return cli_value
    while True:
        raw = input(f"{name} [default {default_value}]: ").strip()
        if not raw:
            return default_value
        try:
            value = int(raw)
            if value >= minimum:
                return value
        except ValueError:
            pass
        print(f"Invalid value. Must be >= {minimum}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Modbus TCP test app for Ethernet-based controllers")
    parser.add_argument("--host", default="192.168.31.89", help="Controller IP")
    parser.add_argument("--port", type=int, default=502, help="Modbus TCP port")
    parser.add_argument("--slave", type=int, default=1, help="Modbus slave/unit/device id")
    parser.add_argument("--timeout", type=float, default=1.0, help="TCP timeout in seconds")

    parser.add_argument("--read-fc", type=int, choices=[1, 2], default=2, help="Read function code: 1 or 2")
    parser.add_argument("--write-fc", type=int, choices=[5, 6], default=5, help="Write function code: 5 or 6")

    parser.add_argument("--di-start", type=int, default=0, help="Input start address")
    parser.add_argument("--di-count", "--di-length", dest="di_count", type=int, default=8, help="Number of inputs")
    parser.add_argument("--do-start", type=int, default=0, help="Output start address")
    parser.add_argument("--do-count", "--do-length", dest="do_count", type=int, default=8, help="Number of outputs")

    parser.add_argument("--mode", choices=["interactive", "input", "output"], default="interactive")
    parser.add_argument("--interval", type=float, default=0.5, help="Monitor interval in seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    read_fc = choose_fc("Input/read", args.read_fc, (1, 2), 2)
    write_fc = choose_fc("Output/write", args.write_fc, (5, 6), 5)
    di_start = choose_int("DI start address", args.di_start, 0, minimum=0)
    di_count = choose_int("DI length", args.di_count, 8, minimum=1)
    do_start = choose_int("DO start address", args.do_start, 0, minimum=0)
    do_count = choose_int("DO length", args.do_count, 8, minimum=1)

    app = ModbusTcpApp(
        host=args.host,
        port=args.port,
        slave_id=args.slave,
        timeout=args.timeout,
        read_fc=read_fc,
        write_fc=write_fc,
        di_start=di_start,
        di_count=di_count,
        do_start=do_start,
        do_count=do_count,
    )

    if not app.connect():
        return
    try:
        if args.mode == "input":
            app.monitor_inputs(args.interval)
        elif args.mode == "output":
            app.test_outputs()
        else:
            app.repl()
    finally:
        app.disconnect()


if __name__ == "__main__":
    main()
