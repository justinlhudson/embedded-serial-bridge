from __future__ import annotations

import time
from typing import Optional, List, Final, Union
import serial
from .hdlc import HDLC
from enum import IntEnum

DEFAULT_MAX_PAYLOAD: int = 4096


class Command(IntEnum):
    Ack = 0x01
    Nak = 0x02
    Ping = 0x03
    Raw = 0x04

class Message:
    # Header length constant (bytes) for the message format above
    HEADER_LEN: Final[int] = 9

    def __init__(self, *, command: int, id: int, fragments: int, fragment: int, length: int, payload: bytes) -> None:
        self.command = command
        self.id = id
        self.fragments = fragments
        self.fragment = fragment
        self.length = length
        self.payload = payload

    def to_bytes(self) -> bytes:
        if not (0 <= self.command <= 0xFFFF):
            raise ValueError("command out of range (u16)")
        if not (0 <= self.id <= 0xFF):
            raise ValueError("id out of range (u8)")
        if not (0 <= self.fragments <= 0xFFFF):
            raise ValueError("fragments out of range (u16)")
        if not (0 <= self.fragment <= 0xFFFF):
            raise ValueError("fragment out of range (u16)")
        pl = bytes(self.payload or b"")
        # length is derived from payload
        length = len(pl)
        if not (0 <= length <= 0xFFFF):
            raise ValueError("payload length exceeds u16 limit")
        header = bytearray()
        header += int(self.command).to_bytes(2, "little")
        header += int(self.id).to_bytes(1, "little")
        header += int(self.fragments).to_bytes(2, "little")
        header += int(self.fragment).to_bytes(2, "little")
        header += int(length).to_bytes(2, "little")
        return bytes(header) + pl

    @classmethod
    def from_bytes(cls, data: bytes) -> "Message":
        command = int.from_bytes(data[0:2], "little")
        id_ = data[2]
        fragments = int.from_bytes(data[3:5], "little")
        fragment = int.from_bytes(data[5:7], "little")
        length = int.from_bytes(data[7:9], "little")
        payload = data[9:9 + length]
        return cls(command=command, id=id_, fragments=fragments, fragment=fragment, length=length, payload=payload)


class Comm:
    """
    Minimal serial comms using shared HDLC framing (see hdlc.py) and CRC-16/X25.
    - Always escapes control characters (<0x20) in addition to FLAG/ESC.
    - Optional CRC verification on receive (require_crc) and configurable max payload.
    """

    _serial: serial.Serial
    _hdlc: HDLC
    _rx_queue: List[bytes]
    _crc_enabled: bool
    _max_payload: int

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.1, *, crc_enabled: bool = False, max_payload: int = DEFAULT_MAX_PAYLOAD, **serial_kwargs) -> None:
        # Keep constructor minimal but allow overrides via kwargs (e.g., bytesize, parity, stopbits, rtscts, etc.)
        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout, write_timeout=1.0, **serial_kwargs)
        self._crc_enabled = bool(crc_enabled)
        self._max_payload = int(max_payload)
        self._hdlc = HDLC(escape_ctrl=True, require_crc=self._crc_enabled)
        self._rx_queue = []

    def close(self) -> None:
        try:
            self._serial.close()
        except Exception:
            pass

    def __enter__(self) -> "Comm":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def write(self, data: Union[bytes, Message]) -> int:
        """Write either raw payload bytes or a Message.
        Returns number of bytes written to the serial port.
        """
        if isinstance(data, Message):
            pl_len = len(data.payload or b"")
            if pl_len > self._max_payload:
                raise ValueError(f"payload too large (max {self._max_payload} bytes)")
            frame = self._hdlc.encode(data.to_bytes())
        else:
            raw = bytes(data)
            if len(raw) > self._max_payload:
                raise ValueError(f"payload too large (max {self._max_payload} bytes)")
            frame = self._hdlc.encode(raw)
        return self._serial.write(frame)

    def read(self, timeout: Optional[float] = None, *, message: bool = True) -> Optional[Union[bytes, Message]]:
        """Read one HDLC frame.
        - If message=True (default), parses and returns a Message object, or None on timeout/parse failure.
        - If message=False, returns the raw payload bytes (without CRC), or None on timeout.
        """
        # Return any previously decoded payload first
        if self._rx_queue:
            payload = self._rx_queue.pop(0)
            if message:
                try:
                    return Message.from_bytes(payload)
                except Exception:
                    return None
            return payload

        deadline = time.time() + timeout if timeout is not None else None
        while True:
            if deadline is not None and time.time() >= deadline:
                return None

            # Read available bytes or at least one
            n = self._serial.in_waiting or 1
            chunk = self._serial.read(n)
            if not chunk:
                continue

            frames = self._hdlc.decode(chunk)
            if frames:
                # Cache any extras and return one payload
                self._rx_queue.extend(frames[1:])
                payload = frames[0]
                if message:
                    try:
                        return Message.from_bytes(payload)
                    except Exception:
                        return None
                return payload
