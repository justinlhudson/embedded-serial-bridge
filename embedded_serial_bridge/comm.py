from __future__ import annotations

import time
from typing import Optional, List
import serial
from .hdlc import hdlc_encode, HDLCDeframer
from enum import IntEnum
from dataclasses import dataclass

# Comms message format (little-endian):
# - command:      u16
# - id:           u8
# - fragments:    u16 (total fragments)
# - fragment:     u16 (0-based index)
# - length:       u16 (payload length in bytes)
# - payload:      [u8; length]
COMMS_HEADER_LEN: int = 9
# Default max payload (configurable via Comm)
DEFAULT_MAX_PAYLOAD: int = 128


class Command(IntEnum):
    Ack = 0x01
    Nak = 0x02
    Ping = 0x03

    @classmethod
    def from_u16(cls, value: int) -> "Command":
        try:
            return cls(value)
        except ValueError:
            raise ValueError("unknown Command")


@dataclass
class Message:
    command: int
    id: int
    fragments: int
    fragment: int
    length: int
    payload: bytes

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

    _ser: serial.Serial
    _deframer: HDLCDeframer
    _rx_queue: List[bytes]
    _crc_enabled: bool
    _max_payload: int

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.1, *, crc_enabled: bool = False, max_payload: int = DEFAULT_MAX_PAYLOAD, **serial_kwargs) -> None:
        # Keep constructor minimal but allow overrides via kwargs (e.g., bytesize, parity, stopbits, rtscts, etc.)
        self._ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout, write_timeout=1.0, **serial_kwargs)
        self._crc_enabled = bool(crc_enabled)
        self._max_payload = int(max_payload)
        self._deframer = HDLCDeframer(escape_ctrl=True, require_crc=self._crc_enabled)
        self._rx_queue = []

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass

    def __enter__(self) -> "Comm":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def write(self, payload: bytes) -> int:
        frame = hdlc_encode(payload, escape_ctrl=True)
        return self._ser.write(frame)

    # High-level helpers using Message
    def write_msg(self, msg: Message) -> int:
        # Enforce max payload size before framing
        pl_len = len(msg.payload or b"")
        if pl_len > self._max_payload:
            raise ValueError(f"payload too large (max {self._max_payload} bytes)")
        return self.write(msg.to_bytes())

    def send_payload(self, command: int | Command, payload: bytes, *, id: int = 0, fragments: int = 1, fragment: int = 0) -> int:
        if len(payload) > self._max_payload:
            raise ValueError(f"payload too large (max {self._max_payload} bytes)")
        cmd_val = int(command)
        msg = Message(command=cmd_val, id=id, fragments=fragments, fragment=fragment, length=len(payload), payload=payload)
        return self.write_msg(msg)

    def read(self, timeout: Optional[float] = None) -> Optional[bytes]:
        # Return any previously decoded payload first
        if self._rx_queue:
            return self._rx_queue.pop(0)

        deadline = time.time() + timeout if timeout is not None else None
        while True:
            if deadline is not None and time.time() >= deadline:
                return None

            # Read available bytes or at least one
            n = self._ser.in_waiting or 1
            chunk = self._ser.read(n)
            if not chunk:
                continue

            frames = self._deframer.input(chunk)
            if frames:
                # Cache any extras and return one payload
                self._rx_queue.extend(frames[1:])
                return frames[0]

    def read_msg(self, timeout: Optional[float] = None) -> Optional[Message]:
        """Read one HDLC frame and parse a Message; returns None on timeout or invalid frame."""
        payload = self.read(timeout=timeout)
        try:
            return Message.from_bytes(payload)
        except Exception as ex:
            pass
        return None
