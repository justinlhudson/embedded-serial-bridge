from __future__ import annotations

import os
import unittest
from pathlib import Path

import serial  # type: ignore
from serial.tools import list_ports  # type: ignore

from embedded_serial_bridge.comm import Comm, Message, Command

try:  # Python 3.11+
    import tomllib as _toml
except Exception:  # pragma: no cover
    try:
        import tomli as _toml  # type: ignore
    except Exception:
        _toml = None


def _load_config() -> dict:
    if _toml is None:
        raise unittest.SkipTest("TOML parser unavailable; install 'tomli' for Python <3.11")
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "config.toml"
    with cfg_path.open("rb") as f:
        return _toml.load(f)


def _port_available(port: str) -> bool:
    for p in list_ports.comports():
        if p.device == port:
            return True
    return False


class Test_Integration(unittest.TestCase):
    def setUp(self) -> None:
        # Load and validate config once per test; store on self
        cfg = _load_config()
        serial_cfg = cfg.get("serial", {})
        hdlc_cfg = cfg.get("hdlc", {})

        port = str(serial_cfg.get("port")) if serial_cfg.get("port") else None
        if not port:
            self.skipTest("serial.port missing in config.toml")
        assert port is not None

        if not _port_available(port):
            self.skipTest(f"serial.port '{port}' not available on this system")

        self.port = port
        self.baudrate = int(serial_cfg.get("baudrate", 115200))
        self.timeout = float(serial_cfg.get("timeout", 0.5))
        self.crc_enabled = bool(hdlc_cfg.get("crc_enabled", False))
        self.max_payload = int(hdlc_cfg.get("max_payload", 128))

    def test_ping_roundtrip(self) -> None:
        try:
            with Comm(
                self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                crc_enabled=self.crc_enabled,
                max_payload=self.max_payload,
            ) as c:
                payload = b""  # empty ping payload
                msg = Message(
                    command=int(Command.Ping),
                    id=0,
                    fragments=1,
                    fragment=0,
                    length=len(payload),
                    payload=payload,
                )
                written = c.write_msg(msg)
                self.assertGreater(written, 0, "No bytes written to serial port")

                rx = c.read_msg(timeout=2.0)
                self.assertIsNotNone(rx, "No response received within timeout; ensure loopback/echo is present")
                assert rx is not None
                self.assertEqual(rx.command, int(Command.Ping))
                self.assertEqual(rx.id, 0)
                self.assertEqual(rx.fragments, 1)
                self.assertEqual(rx.fragment, 0)
                self.assertEqual(rx.payload, payload)
        except serial.SerialException as e:  # type: ignore
            self.skipTest(f"Unable to open serial port '{self.port}': {e}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
