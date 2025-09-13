from __future__ import annotations

from typing import List, Final


class HDLC:
    FLAG: Final[int] = 0x7E
    ESC: Final[int] = 0x7D
    ESC_MASK: Final[int] = 0x20

    def __init__(self, max_frame_len: int = 4096, escape_ctrl: bool = True, require_crc: bool = False):
        self.escape_ctrl = escape_ctrl
        self.max_frame_len = max_frame_len
        self.require_crc = require_crc
        self._buf = bytearray()
        self._esc = False

    @staticmethod
    def _fcs16_ppp(data: bytes) -> int:
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

    @staticmethod
    def _needs_escape(b: int, escape_ctrl: bool) -> bool:
        if b in (HDLC.FLAG, HDLC.ESC):
            return True
        if escape_ctrl and b < 0x20:
            return True
        return False

    def encode(self, payload: bytes) -> bytes:
        fcs = HDLC._fcs16_ppp(payload)
        frame = bytearray()
        frame.append(HDLC.FLAG)
        to_send = payload + bytes((fcs & 0xFF, (fcs >> 8) & 0xFF))
        for b in to_send:
            if HDLC._needs_escape(b, self.escape_ctrl):
                frame.append(HDLC.ESC)
                frame.append(b ^ HDLC.ESC_MASK)
            else:
                frame.append(b)
        frame.append(HDLC.FLAG)
        return bytes(frame)

    def decode(self, data: bytes) -> List[bytes]:
        out: List[bytes] = []
        for b in data:
            if b == HDLC.FLAG:
                if self._buf:
                    payload = self._finalize_frame(self._buf)
                    if payload is not None:
                        out.append(payload)
                    self._buf.clear()
                self._esc = False
                continue

            if self._esc:
                b = b ^ HDLC.ESC_MASK
                self._esc = False
            elif b == HDLC.ESC:
                self._esc = True
                continue

            if len(self._buf) < self.max_frame_len:
                self._buf.append(b)
            else:
                self._buf.clear()
                self._esc = False
        return out

    def _finalize_frame(self, buf: bytearray) -> bytes | None:
        # Frame must contain at least 2 bytes (the CRC)
        if len(buf) < 2:
            return None

        if self.require_crc:
            # With CRC validation, validate and strip the 2-byte CRC
            if len(buf) < 2:  # Need at least the CRC
                return None
            payload = bytes(buf[:-2])
            rx_fcs = buf[-2] | (buf[-1] << 8)
            calc = self._fcs16_ppp(payload)
            if rx_fcs != calc:
                return None
            return payload
        else:
            # Without CRC validation, still strip the 2-byte CRC that was added during encoding
            # but don't validate it
            return bytes(buf[:-2])


# Backward-compatible module-level aliases
FLAG = HDLC.FLAG
ESC = HDLC.ESC
ESC_MASK = HDLC.ESC_MASK
