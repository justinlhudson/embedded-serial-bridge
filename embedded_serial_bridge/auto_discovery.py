#!/usr/bin/env python3
"""
Standalone script to run serial port discovery.
Can be run directly from the embedded_serial_bridge directory.
"""

from __future__ import annotations

import sys
import os
import platform
import uuid
from typing import Optional
from serial.tools import list_ports  # type: ignore
import serial  # type: ignore

# Add the parent directory to Python path so we can import the package
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import from the package
from embedded_serial_bridge.comm import Comm, Command, Message, DEFAULT_MAX_PAYLOAD


class AutoDiscovery:
    """Serial port auto-discovery using ping commands to find responding devices."""

    def __init__(
        self,
        baudrate: int = 115200,
        timeout: float = 1.0,
        fcs: bool = False,
        payload_limit: int = DEFAULT_MAX_PAYLOAD
    ):
        """
        Initialize auto-discovery with communication parameters.

        Args:
            baudrate: Baud rate for communication (default: 115200)
            timeout: Timeout for response in seconds (default: 1.0)
            fcs: Enable FCS validation (default: False)
            payload_limit: Maximum payload size (default: DEFAULT_MAX_PAYLOAD)
        """
        self.baudrate = baudrate
        self.timeout = timeout
        self.fcs = fcs
        self.payload_limit = payload_limit

    def _get_likely_ports(self) -> list[str]:
        """Get likely serial ports based on platform and common patterns."""
        system = platform.system().lower()
        all_ports = [port_info.device for port_info in list_ports.comports()]

        if system == "linux":
            # Common Linux USB-serial patterns
            patterns = ["/dev/ttyUSB", "/dev/ttyACM"]
            likely = [p for p in all_ports if any(pattern in p for pattern in patterns)]
            # Prioritize USB devices
            likely.sort(key=lambda x: (0 if "USB" in x or "ACM" in x else 1, x))

        elif system == "darwin":  # macOS
            # Common macOS USB-serial patterns
            patterns = ["/dev/cu.usbserial", "/dev/cu.usbmodem"]
            likely = [p for p in all_ports if any(pattern in p for pattern in patterns)]
            # Prioritize usbserial and usbmodem
            likely.sort(key=lambda x: (0 if "usbserial" in x or "usbmodem" in x else 1, x))

        elif system == "windows":
            # Windows COM ports
            likely = [p for p in all_ports if p.startswith("COM")]
            # Sort by COM number
            likely.sort(key=lambda x: int(x[3:]) if x[3:].isdigit() else 999)

        else:
            # Unknown platform, return all ports
            likely = all_ports

        # Add remaining ports
        other_ports = [p for p in all_ports if p not in likely]
        return likely + other_ports

    def _ping_port_test(self, port: str) -> bool:
        """
        Test if a serial port responds to ping command.

        Args:
            port: Serial port device path

        Returns:
            True if port responds to ping, False otherwise
        """
        try:
            with Comm(port, baudrate=self.baudrate, timeout=self.timeout,
                     fcs=self.fcs, payload_limit=self.payload_limit) as comm:

                # Generate unique ID from first byte of UUID
                unique_id = uuid.uuid4().bytes[0]  # Get first byte of UUID (0-255)

                # Send ping with empty payload
                ping_msg = Message(
                    command=int(Command.Ping),
                    id=unique_id,  # Use first byte of UUID as unique ID
                    fragments=1,
                    fragment=0,
                    length=0,
                    payload=b""
                )

                # Send ping
                written = comm.write(ping_msg)
                if written <= 0:
                    return False

                # Wait for response
                response = comm.read(timeout=self.timeout, message=True)
                if response is None or isinstance(response, bytes):
                    return False

                # Check if it's a valid ping response
                return (response.command == int(Command.Ping) and
                        response.id == unique_id)

        except (serial.SerialException, OSError, ValueError, Exception):
            # Any error means this port doesn't work
            return False

    def run(self) -> Optional[str]:
        """
        Discover the correct serial port by testing with ping commands.

        Returns:
            Path to working serial port, or None if none found
        """
        ports_to_test = self._get_likely_ports()

        print(f"Discovering serial port on {platform.system()}...")
        print(f"Testing {len(ports_to_test)} port(s)...")

        for port in ports_to_test:
            print(f"Testing {port}...", end=" ", flush=True)

            if self._ping_port_test(port):
                print("✓ FOUND")
                return port
            else:
                print("✗")

        print("No responding serial port found.")
        return None


def discover(
    baudrate: int = 115200,
    timeout: float = 1.0,
    fcs: bool = False,
    payload_limit: int = DEFAULT_MAX_PAYLOAD
) -> Optional[str]:
    """
    Public function to discover serial port.

    Args:
        baudrate: Baud rate for communication (default: 115200)
        timeout: Timeout for response in seconds (default: 1.0)
        fcs: Enable FCS validation (default: False)
        payload_limit: Maximum payload size (default: DEFAULT_MAX_PAYLOAD)

    Returns:
        Path to working serial port, or None if none found
    """
    discovery = AutoDiscovery(baudrate=baudrate, timeout=timeout, fcs=fcs, payload_limit=payload_limit)
    return discovery.run()


if __name__ == "__main__":
    port = discover()
    if port:
        print(f"\n{port}")
        sys.exit(0)
    else:
        sys.exit(1)
