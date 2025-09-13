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


if __name__ == "__main__":
    unittest.main()
