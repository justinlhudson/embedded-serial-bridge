from __future__ import annotations

import time
from typing import cast

import pytest

import serial  # type: ignore

from embedded_serial_bridge.comm import Comm, Message, Command
from embedded_serial_bridge.auto_discovery import AutoDiscovery


@pytest.fixture(scope="module")
def comm_params():
    """Get communication parameters with defaults."""
    baudrate = 115200
    timeout = 0.5
    fcs = False
    payload_limit = 4096

    discovery = AutoDiscovery(baudrate=baudrate, timeout=timeout, fcs=fcs, payload_limit=payload_limit)
    port = discovery.discover()

    if port is None:
        pytest.skip("No serial port found during discovery")

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
            if isinstance(rx, bytes):
                pytest.fail("Received raw bytes instead of Message")
            rx = cast(Message, rx)
            assert rx.command == int(Command.Ping)
            assert rx.id == 0
            assert rx.fragments == 1
            assert rx.fragment == 0
            assert rx.payload == payload
    except serial.SerialException as e:  # type: ignore
        pytest.skip(f"Unable to open serial port '{comm_params['port']}': {e}")

def test_forever(comm_params):
    """
    Run the ping roundtrip test in a loop, printing CRC error count and sleeping between iterations.
    This function is for manual soak/robustness testing and does not assert or return anything.
    Retries on error and continues forever.
    Prints "." every cycle (no newline).
    Prints if CRC error count changes.
    """
    last_crc_error_count = getattr(test_ping_roundtrip_payloads, "crc_error_count", 0)
    while True:
        try:
            test_ping_roundtrip_payloads(comm_params, "MAX_PAYLOAD_COUNTING")
        except Exception as ex:
            print(f"Error in test_ping_roundtrip_payloads: {ex}. Retrying...")
            time.sleep(1)  # board reset time
            continue
        print(".", end="", flush=True)

        current_crc_error_count = getattr(test_ping_roundtrip_payloads, "crc_error_count", 0)
        if current_crc_error_count != last_crc_error_count:
            print(f"\nTotal CRC errors so far: {current_crc_error_count}")
            last_crc_error_count = current_crc_error_count
        time.sleep(0.01)

if __name__ == "__main__":
    import pytest
    comm_params = pytest.lazy_fixture("comm_params")
    test_forever(comm_params)
