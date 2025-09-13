from __future__ import annotations

from dataclasses import dataclass
from typing import List

FLAG = 0x7E
ESC = 0x7D
ESC_MASK = 0x20


def fcs16_ppp(data: bytes) -> int:
    fcs = 0xFFFF
    for b in data:
        fcs ^= b
        for _ in range(8):
            if fcs & 1:
                fcs = (fcs >> 1) ^ 0x8408
            else:
                fcs >>= 1
    fcs ^= 0xFFFF
    return fcs & 0xFFFF


def _needs_escape(b: int, escape_ctrl: bool) -> bool:
    if b in (FLAG, ESC):
        return True
    if escape_ctrl and b < 0x20:
        return True
    return False


def hdlc_encode(payload: bytes, *, escape_ctrl: bool = False) -> bytes:
    fcs = fcs16_ppp(payload)
    frame = bytearray()
    frame.append(FLAG)
    to_send = payload + bytes((fcs & 0xFF, (fcs >> 8) & 0xFF))
    for b in to_send:
        if _needs_escape(b, escape_ctrl):
            frame.append(ESC)
            frame.append(b ^ ESC_MASK)
        else:
            frame.append(b)
    frame.append(FLAG)
    return bytes(frame)


@dataclass
class HDLCDeframer:
    escape_ctrl: bool = False
    max_frame_len: int = 4096
    require_crc: bool = False

    def __post_init__(self) -> None:
        self._buf = bytearray()
        self._esc = False

    def input(self, data: bytes) -> List[bytes]:
        out: List[bytes] = []
        for b in data:
            if b == FLAG:
                if self._buf:
                    payload = self._finalize_frame(self._buf)
                    if payload is not None:
                        out.append(payload)
                    self._buf.clear()
                self._esc = False
                continue

            if self._esc:
                b = b ^ ESC_MASK
                self._esc = False
            elif b == ESC:
                self._esc = True
                continue

            if len(self._buf) < self.max_frame_len:
                self._buf.append(b)
            else:
                self._buf.clear()
                self._esc = False
        return out

    def _finalize_frame(self, buf: bytearray) -> bytes | None:
        if len(buf) < 2:
            return None
        if self.require_crc:
            if len(buf) < 3:
                return None
            payload = bytes(buf[:-2])
            rx_fcs = buf[-2] | (buf[-1] << 8)
            calc = fcs16_ppp(payload)
            if rx_fcs != calc:
                return None
            return payload
        else:
            return bytes(buf[:-2])

