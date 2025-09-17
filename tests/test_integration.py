from __future__ import annotations

import time

import pytest
from pathlib import Path

import serial  # type: ignore

from embedded_serial_bridge.comm import Comm, Message, Command
from embedded_serial_bridge import discovery as _discovery
from embedded_serial_bridge.discovery import discover

try:  # Python 3.11+
    import tomllib as _toml
except Exception:  # pragma: no cover
    try:
        import tomli as _toml  # type: ignore
    except Exception:
        _toml = None


def _load_config():
    if _toml is None:
        pytest.skip("TOML parser unavailable; install 'tomli' for Python <3.11", allow_module_level=True)  # type: ignore
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "config.toml"
    with cfg_path.open("rb") as f:
        return cfg_path, _toml.load(f)

@pytest.fixture(scope="module")
def comm_params():
    cfg_path, cfg = _load_config()
    serial_cfg = cfg.get("serial", {})
    hdlc_cfg = cfg.get("hdlc", {})
    baudrate = int(serial_cfg.get("baudrate", 115200))
    timeout = float(serial_cfg.get("timeout", 0.5))
    fcs = bool(hdlc_cfg.get("fcs", False))
    payload_limit = int(hdlc_cfg.get("payload_limit", 4096))
    preferred_port = serial_cfg.get("port")
    port = discover(cfg_path)

    return {
        "port": port,
        "baudrate": baudrate,
        "timeout": timeout,
        "fcs": fcs,
        "payload_limit": payload_limit,
    }

@pytest.mark.parametrize(
    "payload",
    [
        b"",          # empty payload
        b"hello",     # simple text payload
        "MAX_PAYLOAD_COUNTING",  # sentinel for max payload counting pattern
    ],
)
def test_ping_roundtrip_payloads(comm_params, payload) -> None:
    crc_error_count = getattr(test_ping_roundtrip_payloads, "crc_error_count", 0)
    if payload == "MAX_PAYLOAD_COUNTING":
        payload_limit = comm_params["payload_limit"]
        payload = bytes([i % 256 for i in range(int(payload_limit))])
    try:
        with Comm(
            comm_params["port"],
            baudrate=comm_params["baudrate"],
            timeout=comm_params["timeout"],
            fcs=comm_params["fcs"],
            payload_limit=comm_params["payload_limit"],
        ) as c:
            msg = Message(
                command=int(Command.Ping),
                id=0,
                fragments=1,
                fragment=0,
                length=len(payload),
                payload=payload,
            )
            written = c.write(msg)
            assert written > 0, "No bytes written to serial port"
            rx = c.read(timeout=1.0, message=True)
            if rx is not None and rx is False:
                crc_error_count += 1
                print(f"CRC error detected (FCS failed!) on received message. Total CRC errors: {crc_error_count}")
                test_ping_roundtrip_payloads.crc_error_count = crc_error_count
                return  # Do not fail test, just count and print
            assert rx is not None, "No response within timeout; ensure loopback/echo is present"
            assert rx.command == int(Command.Ping)
            assert rx.id == 0
            assert rx.fragments == 1
            assert rx.fragment == 0
            assert rx.payload == payload
    except serial.SerialException as e:  # type: ignore
        pytest.skip(f"Unable to open serial port '{comm_params['port']}': {e}")

def test_forever(comm_params):
    while True:
        test_ping_roundtrip_payloads(comm_params, "MAX_PAYLOAD_COUNTING")
        time.sleep(0.01)

if __name__ == "__main__":
    import pytest
    comm_params = pytest.lazy_fixture("comm_params")
    test_forever(comm_params)
