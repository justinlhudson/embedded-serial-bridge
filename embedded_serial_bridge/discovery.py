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
from typing import Optional, List, Tuple
from serial.tools import list_ports  # type: ignore
import serial  # type: ignore

# Add the parent directory to Python path so we can import the package
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import from the package
from embedded_serial_bridge.comm import Comm, Command, Message

try:  # Python 3.11+
    import tomllib as _toml
except Exception:  # pragma: no cover
    try:
        import tomli as _toml  # type: ignore
    except Exception:
        _toml = None


def _load_config(config_path: str = "config.toml") -> dict:
    """Load configuration from TOML file."""
    if _toml is None:
        print("Warning: TOML parser not available. Using default values.")
        return {}

    try:
        with open(config_path, "rb") as f:
            return _toml.load(f)
    except FileNotFoundError:
        print(f"Warning: Config file {config_path} not found. Using default values.")
        return {}
    except Exception as e:
        print(f"Warning: Failed to parse config: {e}. Using default values.")
        return {}


def _get_serial_config(config: dict) -> tuple[int, float, bool, int]:
    """Extract serial configuration from config dict."""
    serial_cfg = config.get("serial", {})
    hdlc_cfg = config.get("hdlc", {})

    baudrate = int(serial_cfg.get("baudrate", 115200))
    timeout = float(serial_cfg.get("timeout", 1.0))
    crc_enabled = bool(hdlc_cfg.get("crc_enabled", False))
    max_payload = int(hdlc_cfg.get("max_payload", 4096))

    return baudrate, timeout, crc_enabled, max_payload


def _get_available_ports() -> List[str]:
    """Get list of available serial ports on the current platform."""
    ports = []
    for port_info in list_ports.comports():
        ports.append(port_info.device)
    return sorted(ports)


def _get_likely_ports() -> List[str]:
    """Get likely serial ports based on platform and common patterns."""
    system = platform.system().lower()
    all_ports = _get_available_ports()

    if system == "linux":
        # Common Linux USB-serial patterns
        patterns = ["/dev/ttyUSB", "/dev/ttyACM", "/dev/ttyS"]
        likely = [p for p in all_ports if any(pattern in p for pattern in patterns)]
        # Prioritize USB devices
        likely.sort(key=lambda x: (0 if "USB" in x or "ACM" in x else 1, x))

    elif system == "darwin":  # macOS
        # Common macOS USB-serial patterns
        patterns = ["/dev/cu.usbserial", "/dev/cu.usbmodem", "/dev/cu.SLAB_USBtoUART", "/dev/cu.wchusbserial"]
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

    return likely


def _ping_port_test(port: str, baudrate: int = 115200, timeout: float = 1.0,
                   crc_enabled: bool = False, max_payload: int = 128) -> bool:
    """
    Test if a serial port responds to ping command.

    Args:
        port: Serial port device path
        baudrate: Baud rate for communication
        timeout: Timeout for response in seconds
        crc_enabled: Enable CRC validation
        max_payload: Maximum payload size

    Returns:
        True if port responds to ping, False otherwise
    """
    try:
        with Comm(port, baudrate=baudrate, timeout=timeout,
                 crc_enabled=crc_enabled, max_payload=max_payload) as comm:

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
            response = comm.read(timeout=timeout, message=True)
            if response is None:
                return False

            # Check if it's a valid ping response
            if (response.command == int(Command.Ping) and
                response.id == unique_id):
                return True

            return False

    except (serial.SerialException, OSError, ValueError, Exception):
        # Any error means this port doesn't work
        return False


def discover(config_path: str = "config.toml") -> Optional[str]:
    """
    Discover the correct serial port by testing with ping commands using config settings.

    Args:
        config_path: Path to config.toml file
        test_all: If True, test all ports; if False, test likely ports first

    Returns:
        Path to working serial port, or None if none found
    """
    # Load configuration
    config = _load_config(config_path)
    baudrate, timeout, crc_enabled, max_payload = _get_serial_config(config)

    print(f"Using config: baudrate={baudrate}, timeout={timeout}, crc_enabled={crc_enabled}, max_payload={max_payload}")

    # Test likely ports first, then fallback to all ports
    likely_ports = _get_likely_ports()
    all_ports = _get_available_ports()
    other_ports = [p for p in all_ports if p not in likely_ports]
    ports_to_test = likely_ports + other_ports

    print(f"Discovering serial port on {platform.system()}...")
    print(f"Available ports: {_get_available_ports()}")

    for port in ports_to_test:
        print(f"Testing {port}...", end=" ", flush=True)

        if _ping_port_test(port, baudrate=baudrate, timeout=timeout,
                         crc_enabled=crc_enabled, max_payload=max_payload):
            print("✓ FOUND")
            return port
        else:
            print("✗")

    print("No responding serial port found.")
    return None


if __name__ == "__main__":
    port = discover()
    if port:
        print(f"\n{port}")
        sys.exit(0)
    else:
        sys.exit(1)
