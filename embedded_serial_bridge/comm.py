from __future__ import annotations

import time
from typing import Optional, List, Final, Union
import serial
from .hdlc import HDLC
from enum import IntEnum

DEFAULT_MAX_PAYLOAD: int = 4096


class Command(IntEnum):
    """
    Command types for embedded serial bridge protocol.
    Ack = 0x01: Acknowledge
    Nak = 0x02: Negative acknowledge
    Ping = 0x03: Ping (for discovery/echo)
    Raw = 0x04: Raw data
    """
    Ack = 0x01
    Nak = 0x02
    Ping = 0x03
    Raw = 0x04

class Message:
    """
    Represents a protocol message for the embedded serial bridge.
    Fields:
        command: u16
        id: u8
        fragments: u16
        fragment: u16
        length: u16
        payload: bytes
    HEADER_LEN: Number of bytes in the header (9).
    """
    HEADER_LEN: Final[int] = 9

    def __init__(self, *, command: int, id: int, fragments: int, fragment: int, length: int, payload: bytes) -> None:
        """
        Initialize a Message instance.
        Args:
            command (int): Command type (u16)
            id (int): Message ID (u8)
            fragments (int): Total fragments (u16)
            fragment (int): Fragment index (u16)
            length (int): Payload length (u16)
            payload (bytes): Message payload
        """
        self.command = command
        self.id = id
        self.fragments = fragments
        self.fragment = fragment
        self.length = length
        self.payload = payload

    def to_bytes(self) -> bytes:
        """
        Serialize the message to bytes (header + payload).
        Returns:
            bytes: Serialized message
        Raises:
            ValueError: If any field is out of range or payload too large
        """
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
        """
        Parse a Message from bytes.
        Args:
            data (bytes): Byte sequence containing header and payload
        Returns:
            Message: Parsed message
        """
        command = int.from_bytes(data[0:2], "little")
        id_ = data[2]
        fragments = int.from_bytes(data[3:5], "little")
        fragment = int.from_bytes(data[5:7], "little")
        length = int.from_bytes(data[7:9], "little")
        payload = data[9:9 + length]
        return cls(command=command, id=id_, fragments=fragments, fragment=fragment, length=length, payload=payload)


class Comm:
    """
    Serial communication handler for embedded serial bridge protocol.
    Uses HDLC framing and CRC-16/X25 for robust message transfer.
    Features:
        - Escapes control characters (<0x20), FLAG, and ESC
        - Optional CRC verification on receive
        - Configurable max payload size
    """

    _serial: serial.Serial
    _hdlc: HDLC
    _rx_queue: List[bytes]
    _fcs: bool
    _payload_limit: int

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.1, *, fcs: bool = False, payload_limit: int = DEFAULT_MAX_PAYLOAD, **serial_kwargs) -> None:
        """
        Initialize Comm for serial port communication.
        Args:
            port (str): Serial port name
            baudrate (int): Baud rate
            timeout (float): Read timeout in seconds
            fcs (bool): Enable FCS (CRC) checking on receive
            payload_limit (int): Maximum allowed payload size
            serial_kwargs: Additional serial.Serial arguments
        """
        # Keep constructor minimal but allow overrides via kwargs (e.g., bytesize, parity, stopbits, rtscts, etc.)
        self._serial = serial.Serial(port=port, baudrate=baudrate, timeout=timeout, write_timeout=1.0, **serial_kwargs)
        self._fcs = bool(fcs)
        self._payload_limit = int(payload_limit)
        self._hdlc = HDLC(escape_ctrl=True, require_crc=self._fcs)
        self._rx_queue = []

    def close(self) -> None:
        """
        Close the serial port.
        """
        try:
            self._serial.close()
        except Exception:
            pass

    def __enter__(self) -> "Comm":
        """
        Enter context manager, returns self.
        """
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """
        Exit context manager, closes serial port.
        """
        self.close()

    def write(self, data: Union[bytes, Message]) -> int:
        """
        Write a raw payload or Message to the serial port.
        Args:
            data (bytes or Message): Data to send
        Returns:
            int: Number of bytes written
        Raises:
            ValueError: If payload exceeds payload_limit
        """
        if isinstance(data, Message):
            pl_len = len(data.payload or b"")
            if pl_len > self._payload_limit:
                raise ValueError(f"payload too large (max {self._payload_limit} bytes)")
            frame = self._hdlc.encode(data.to_bytes())
        else:
            raw = bytes(data)
            if len(raw) > self._payload_limit:
                raise ValueError(f"payload too large (max {self._payload_limit} bytes)")
            frame = self._hdlc.encode(raw)
        return self._serial.write(frame)

    def read(self, timeout: Optional[float] = None, *, message: bool = True) -> Optional[Union[bytes, Message]]:
        """
        Read one HDLC frame from the serial port.
        Args:
            timeout (float, optional): Timeout in seconds
            message (bool): If True, parse and return Message; else return raw bytes
        Returns:
            Message or bytes or None or False:
                - Message: Parsed message if message=True
                - bytes: Raw payload if message=False
                - None: On timeout or parse failure
                - False: If CRC check fails
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

            frames = []
            try:
                frames = self._hdlc.decode(chunk)
            except ValueError as ex:
                return False
            except Exception as ex:
                return None

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
