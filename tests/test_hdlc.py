from __future__ import annotations

import unittest

from embedded_serial_bridge.hdlc import (
    FLAG,
    ESC,
    ESC_MASK,
    HDLCDeframer,
    hdlc_encode,
)


class TestHDLC(unittest.TestCase):
    def test_basic_roundtrip(self):
        payload = b"hello world"
        frame = hdlc_encode(payload)
        self.assertGreaterEqual(len(frame), len(payload) + 4)  # flags + FCS at least
        self.assertEqual(frame[0], FLAG)
        self.assertEqual(frame[-1], FLAG)

        d = HDLCDeframer()
        out = d.input(frame)
        self.assertEqual(out, [payload])

    def test_escaping_flag_and_esc(self):
        # Payload containing FLAG and ESC must be escaped
        payload = bytes([0x01, FLAG, 0x02, ESC, 0x03])
        frame = hdlc_encode(payload)
        # outer flags present
        self.assertEqual(frame[0], FLAG)
        self.assertEqual(frame[-1], FLAG)
        # inner bytes should contain escapes for FLAG/ESC occurrences
        inner = frame[1:-1]
        # Expect "ESC, FLAG^ESC_MASK" present
        self.assertIn(bytes([ESC, FLAG ^ ESC_MASK]), inner)
        self.assertIn(bytes([ESC, ESC ^ ESC_MASK]), inner)

        d = HDLCDeframer()
        out = d.input(frame)
        self.assertEqual(out, [payload])

    def test_escape_ctrl_option(self):
        # Control characters (<0x20) should be escaped when option enabled
        payload = bytes(range(0x00, 0x20)) + b"ABC"  # include printable too
        frame_no = hdlc_encode(payload, escape_ctrl=False)
        frame_yes = hdlc_encode(payload, escape_ctrl=True)
        # With escape_ctrl=True, expect many ESC bytes
        self.assertGreater(frame_yes.count(bytes([ESC])), frame_no.count(bytes([ESC])))

        d = HDLCDeframer(escape_ctrl=True)
        out = d.input(frame_yes)
        self.assertEqual(out, [payload])

    def test_multiple_frames_in_one_chunk(self):
        payloads = [b"A", b"BC", b"DEF"]
        frames = b"".join(hdlc_encode(p) for p in payloads)
        d = HDLCDeframer()
        out = d.input(frames)
        self.assertEqual(out, payloads)

    def test_partial_frames_across_calls(self):
        payload = b"chunky"
        frame = hdlc_encode(payload)
        d = HDLCDeframer()
        # feed in halves
        mid = len(frame) // 2
        out1 = d.input(frame[:mid])
        out2 = d.input(frame[mid:])
        self.assertEqual(out1, [])
        self.assertEqual(out2, [payload])

    def test_empty_and_single_byte_payloads(self):
        # Test edge cases that might lose bytes
        test_cases = [
            b"",
            b"A",
            b"AB",
            b"ABC",
        ]

        for payload in test_cases:
            with self.subTest(payload=payload):
                frame = hdlc_encode(payload, escape_ctrl=True)

                # Test without CRC validation
                d = HDLCDeframer(escape_ctrl=True, require_crc=False)
                out = d.input(frame)
                self.assertEqual(
                    len(out), 1, f"Should decode exactly one frame for payload {payload!r}"
                )
                self.assertEqual(
                    out[0],
                    payload,
                    f"Payload mismatch: expected {payload!r}, got {out[0]!r}",
                )

                # Test with CRC validation
                d_crc = HDLCDeframer(escape_ctrl=True, require_crc=True)
                out_crc = d_crc.input(frame)
                self.assertEqual(
                    len(out_crc),
                    1,
                    f"Should decode exactly one frame with CRC for payload {payload!r}",
                )
                self.assertEqual(
                    out_crc[0],
                    payload,
                    f"Payload mismatch with CRC: expected {payload!r}, got {out_crc[0]!r}",
                )


if __name__ == "__main__":
    unittest.main()
