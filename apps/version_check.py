"""
version_check.py - MCU Firmware Version Check

Pings the board until it responds, then requests the firmware version string.
The ping confirms the board is alive before asking for version.

Usage:
    python apps/version_check.py
    python apps/version_check.py --port /dev/ttyUSB0
    python apps/version_check.py --port /dev/ttyUSB0 --baudrate 9600
    python apps/version_check.py --retries 10 --timeout 3.0
"""
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import os
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from embedded_serial_bridge.comm import Comm, Command, Message
from embedded_serial_bridge.auto_discovery import AutoDiscovery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def ping_board(comm: Comm, timeout: float) -> bool:
    """
    Send a Ping (0x03) and return True if the board echoes back.
    """
    msg = Message.make(command=Command.Ping, payload=b"")
    comm.write(msg)
    response = comm.read(timeout=timeout, message=True)
    if response is None or isinstance(response, bool):
        return False
    return response.command == int(Command.Ping)


def request_version(comm: Comm, timeout: float) -> str | None:
    """
    Send a Version request (0x05) and return the version string from the MCU.
    Returns None if no response, empty string if response has no payload.
    """
    msg = Message.make(command=Command.Version, payload=b"")
    comm.write(msg)
    response = comm.read(timeout=timeout, message=True)

    if response is None or isinstance(response, bool):
        return None

    if response.payload:
        try:
            return response.payload.decode("utf-8").strip()
        except UnicodeDecodeError:
            return response.payload.hex()

    return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ping board until alive, then request firmware version"
    )
    parser.add_argument("--port", "-p",
        help="Serial port (e.g. /dev/ttyUSB0). Auto-discovers if omitted.")
    parser.add_argument("--baudrate", "-b", type=int, default=115200,
        help="Baud rate (default: 115200)")
    parser.add_argument("--timeout", "-t", type=float, default=2.0,
        help="Per-attempt timeout in seconds (default: 2.0)")
    parser.add_argument("--retries", "-r", type=int, default=5,
        help="Ping attempts before giving up (default: 5)")
    args = parser.parse_args()

    # --- Find port ---
    port = args.port
    if not port:
        print("No port specified — auto-discovering...")
        discovery = AutoDiscovery(baudrate=args.baudrate, timeout=args.timeout)
        port = discovery.run()
        if not port:
            print("ERROR: No serial port found. Use --port to specify one.")
            sys.exit(1)
        print(f"Found port: {port}")

    print(f"Port: {port}  Baud: {args.baudrate}")

    with Comm(port, baudrate=args.baudrate, timeout=args.timeout) as comm:

        # --- Step 1: Ping until alive ---
        print(f"Pinging board (0x03)... up to {args.retries} attempts")
        alive = False
        for attempt in range(1, args.retries + 1):
            sys.stdout.write(f"  Attempt {attempt}/{args.retries}... ")
            sys.stdout.flush()
            if ping_board(comm, args.timeout):
                print("OK — board responded to ping")
                alive = True
                break
            else:
                print("no response")
                time.sleep(0.5)

        if not alive:
            print(f"FAIL: Board did not respond to ping after {args.retries} attempts.")
            sys.exit(1)

        # --- Step 2: Request version ---
        print("Requesting firmware version (0x05)...")
        version = request_version(comm, args.timeout)

        if version is None:
            print("FAIL: Board alive but did not respond to version request.")
            sys.exit(1)

        print()
        print(f"  Board   : OK")
        print(f"  Port    : {port}")
        print(f"  Version : {version if version else '(empty payload)'}")


if __name__ == "__main__":
    main()
