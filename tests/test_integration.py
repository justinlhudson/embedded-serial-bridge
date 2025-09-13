from __future__ import annotations

import pytest
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
        pytest.skip("TOML parser unavailable; install 'tomli' for Python <3.11", allow_module_level=True)
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "config.toml"
    with cfg_path.open("rb") as f:
        return _toml.load(f)


def _port_available(port: str) -> bool:
    for p in list_ports.comports():
        if p.device == port:
            return True
    return False


@pytest.fixture(scope="module")
def comm_params():
    cfg = _load_config()
    serial_cfg = cfg.get("serial", {})
    hdlc_cfg = cfg.get("hdlc", {})

    port = str(serial_cfg.get("port")) if serial_cfg.get("port") else None
    if not port:
        pytest.skip("serial.port missing in config.toml", allow_module_level=True)

    if not _port_available(port):
        pytest.skip(f"serial.port '{port}' not available on this system", allow_module_level=True)

    baudrate = int(serial_cfg.get("baudrate", 115200))
    timeout = float(serial_cfg.get("timeout", 0.5))
    crc_enabled = bool(hdlc_cfg.get("crc_enabled", False))
    max_payload = int(hdlc_cfg.get("max_payload", 4096))

    return {
        "port": port,
        "baudrate": baudrate,
        "timeout": timeout,
        "crc_enabled": crc_enabled,
        "max_payload": max_payload,
    }


@pytest.mark.parametrize(
    "payload",
    [
        b"",          # empty payload
        b"hello",     # simple text payload
    ],
)
def test_ping_roundtrip_payloads(comm_params, payload: bytes) -> None:
    try:
        with Comm(
            comm_params["port"],
            baudrate=comm_params["baudrate"],
            timeout=comm_params["timeout"],
            crc_enabled=comm_params["crc_enabled"],
            max_payload=comm_params["max_payload"],
        ) as c:
            msg = Message(
                command=int(Command.Ping),
                id=0,
                fragments=1,
                fragment=0,
                length=len(payload),
                payload=payload,
            )
            written = c.write_msg(msg)
            assert written > 0, "No bytes written to serial port"

            rx = c.read_msg(timeout=1.0)
            assert rx is not None, "No response within timeout; ensure loopback/echo is present"
            assert rx.command == int(Command.Ping)
            assert rx.id == 0
            assert rx.fragments == 1
            assert rx.fragment == 0
            assert rx.payload == payload
    except serial.SerialException as e:  # type: ignore
        pytest.skip(f"Unable to open serial port '{comm_params['port']}': {e}")
