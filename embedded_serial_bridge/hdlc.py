from __future__ import annotations

from typing import List, Final


class HDLC:
    """
    Implements HDLC framing and CRC-16/X25 for serial communication.
    Features:
        - Escapes FLAG, ESC, and optionally control characters (<0x20)
        - Optionally adds and validates CRC-16/X25
        - Decodes frames and checks CRC if required
    Args:
        max_frame_len (int): Maximum frame length
        escape_ctrl (bool): Escape control characters
        use_crc (bool): Append CRC when encoding and strip it when decoding
        require_crc (bool): Require CRC validation on decode
    """
    FLAG: Final[int] = 0x7E
    ESC: Final[int] = 0x7D
    ESC_MASK: Final[int] = 0x20

    def __init__(
        self,
        max_frame_len: int = 4096,
        escape_ctrl: bool = False,
        use_crc: bool = True,
        require_crc: bool = True,
    ):
        """
        Initialize HDLC framing handler.
        Args:
            max_frame_len (int): Maximum frame length
            escape_ctrl (bool): Escape control characters
            use_crc (bool): Append CRC when encoding and strip it when decoding
            require_crc (bool): Require CRC validation on decode
        """
        self.escape_ctrl = escape_ctrl
        self.max_frame_len = max_frame_len
        self.use_crc = use_crc
        self.require_crc = require_crc
        self._buf = bytearray()
        self._esc = False

    @staticmethod
    def _fcs16_ppp(data: bytes) -> int:
        """
        Calculate CRC-16/X25 (PPP FCS) for given data.
        Args:
            data (bytes): Data to calculate CRC for
        Returns:
            int: CRC-16 value
        """
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
        """
        Determine if a byte needs escaping in HDLC frame.
        Args:
            b (int): Byte value
            escape_ctrl (bool): Escape control characters
        Returns:
            bool: True if needs escaping
        """
        if b in (HDLC.FLAG, HDLC.ESC):
            return True
        if escape_ctrl and b < 0x20:
            return True
        return False

    def encode(self, payload: bytes) -> bytes:
        """
        Encode payload into HDLC frame with CRC and escaping.
        Args:
            payload (bytes): Data to encode
        Returns:
            bytes: Encoded HDLC frame
        """
        frame = bytearray()
        frame.append(HDLC.FLAG)
        if self.use_crc:
            fcs = HDLC._fcs16_ppp(payload)
            to_send = payload + bytes((fcs & 0xFF, (fcs >> 8) & 0xFF))
        else:
            to_send = payload
        for b in to_send:
            if HDLC._needs_escape(b, self.escape_ctrl):
                frame.append(HDLC.ESC)
                frame.append(b ^ HDLC.ESC_MASK)
            else:
                frame.append(b)
        frame.append(HDLC.FLAG)
        return bytes(frame)

    def decode(self, data: bytes) -> List[bytes]:
        """
        Decode HDLC frames from incoming data.
        Args:
            data (bytes): Incoming serial data
        Returns:
            List[bytes]: List of decoded payloads (CRC validated if required)
        Raises:
            ValueError: If CRC check fails (when require_crc is True)
        """
        out: List[bytes] = []
        for b in data:
            if b == HDLC.FLAG:
                if self._buf:
                    try:
                        payload = self._finalize_frame(self._buf)
                        if payload is not None:
                            out.append(payload)
                    finally:
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
        """
        Finalize and validate a received HDLC frame.
        Args:
            buf (bytearray): Frame buffer
        Returns:
            bytes | None: Payload if valid, None if too short
        Raises:
            ValueError: If CRC check fails (when require_crc is True)
        """
        if self.require_crc:
            # With CRC validation, validate and strip the 2-byte CRC
            if len(buf) < 2:  # Need at least the CRC
                return None
            payload = bytes(buf[:-2])
            rx_fcs = buf[-2] | (buf[-1] << 8)
            calc = self._fcs16_ppp(payload)
            if rx_fcs != calc:
                raise ValueError("FCS failed!")
            return payload
        if self.use_crc:
            if len(buf) < 2:
                return None
            return bytes(buf[:-2])
        return bytes(buf)


# Backward-compatible module-level aliases
FLAG = HDLC.FLAG
ESC = HDLC.ESC
ESC_MASK = HDLC.ESC_MASK
