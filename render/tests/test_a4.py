# SPDX-License-Identifier: GPL-3.0-or-later
"""A4 tests: the cloud render script's contract, and eclipse darkness.

The brightness test decodes the two fixture stills (sunlit MET 890 and
eclipse MET 920, same framing) with a small stdlib PNG reader and
compares the spacecraft region: in eclipse it must come out darker.
Env overrides for red cases: ANIM_FIXTURE_DIR, ANIM_A4_DIR.
"""

import json
import os
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import render_clip as R  # noqa: E402
import sync as Y  # noqa: E402

FIXTURES = Path(os.environ.get("ANIM_FIXTURE_DIR", ROOT / "out" / "a2"))
A4_OUT = Path(os.environ.get("ANIM_A4_DIR", ROOT / "out" / "a4"))


def png_rows(path):
    """(width, height, rows of RGBA bytes) for an 8-bit RGB/RGBA PNG."""
    data = Path(path).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, width, height, color_type = 8, b"", 0, 0, 0
    while pos < len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width = int.from_bytes(chunk[0:4], "big")
            height = int.from_bytes(chunk[4:8], "big")
            color_type = chunk[9]
        elif kind == b"IDAT":
            idat += chunk
        pos += 12 + length
    channels = 4 if color_type == 6 else 3
    raw = zlib.decompress(idat)
    stride = width * channels
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(height):
        filt, i = raw[i], i + 1
        line = bytearray(raw[i:i + stride])
        i += stride
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = prev[x]
            up_left = prev[x - channels] if x >= channels else 0
            if filt == 1:
                line[x] = (line[x] + left) & 255
            elif filt == 2:
                line[x] = (line[x] + up) & 255
            elif filt == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif filt == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                pred = left if (pa <= pb and pa <= pc) else up if pb <= pc else up_left
                line[x] = (line[x] + pred) & 255
        rows.append((channels, bytes(line)))
        prev = line
    return width, height, rows


def region_luminance(path):
    """Mean luminance over the frame's central region (the spacecraft)."""
    width, height, rows = png_rows(path)
    x0, x1 = int(width * 0.38), int(width * 0.62)
    y0, y1 = int(height * 0.32), int(height * 0.68)
    channels = rows[0][0]
    total, count = 0.0, 0
    for y in range(y0, y1):
        line = rows[y][1]
        for x in range(x0, x1):
            o = x * channels
            total += 0.2126 * line[o] + 0.7152 * line[o + 1] + 0.0722 * line[o + 2]
            count += 1
    return total / count


class TestEclipseDarkness(unittest.TestCase):
    def test_eclipse_is_darker(self):
        sunlit = FIXTURES / "fixture_890_sunlit.png"
        eclipse = FIXTURES / "fixture_920_eclipse_red.png"
        self.assertTrue(sunlit.is_file() and eclipse.is_file(),
                        "fixture stills missing - run build_a2 --fixture")
        bright = region_luminance(sunlit)
        dark = region_luminance(eclipse)
        self.assertLess(dark, bright,
                        "eclipse region %.1f not darker than sunlit %.1f"
                        % (dark, bright))
        # Readable, not vanished into the black either.
        self.assertGreater(dark, 4.0)


class TestRenderClipArgs(unittest.TestCase):
    def test_render_clip_command(self):
        args = R.parse_args([
            "--timeline", "some/run.js", "--output", "some/out",
            "--width", "1280", "--height", "720", "--met-start", "890",
            "--met-end", "930", "--engine", "CYCLES", "--samples", "128",
            "--dry-run"])
        command = R.build_command(args)
        joined = " ".join(command)
        for needle in ("build_a2.py", "--timeline", "some/run.js",
                       "--output-dir", "some/out", "--width 1280",
                       "--height 720", "--met-start 890", "--met-end 930",
                       "--engine CYCLES", "--samples 128"):
            self.assertIn(needle, joined)
        self.assertEqual(R.main([
            "--timeline", "some/run.js", "--output", "some/out",
            "--dry-run"]), 0)
        with self.assertRaises(SystemExit):
            R.parse_args(["--timeline", "does/not/exist.js",
                          "--output", "some/out"])

    def test_a4_short_clip_sync(self):
        syncs = sorted(A4_OUT.glob("*.sync.json"))
        self.assertTrue(syncs, "no A4 sync file - run render_clip.py")
        sync = Y.read_sync(syncs[-1])
        report = json.loads((A4_OUT / "a2_report.json").read_text())
        self.assertEqual(sync["first_frame_met_s"], report["met_range"][0])
        for frame in report["frames"]:
            self.assertEqual(Y.frame_met(sync, frame["frame"]), frame["met_s"])
        clip = A4_OUT / report["preview"]
        self.assertTrue(clip.is_file() and clip.stat().st_size > 10000)
        self.assertEqual(report["resolution"], [640, 360])


if __name__ == "__main__":
    unittest.main()
