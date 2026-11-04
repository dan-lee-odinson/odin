# SPDX-License-Identifier: GPL-3.0-or-later
"""A6 tests: the materials pass close-up exists at full size and the
arrays really do catch the Sun in it (a large near-white glint area
that the ordinary follow still does not have).

Every test has a red case in tests/show_red.py.
Env override for red cases: ANIM_A6_CLOSEUP.
"""

import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from test_a4 import png_rows  # noqa: E402

CLOSEUP = Path(os.environ.get("ANIM_A6_CLOSEUP",
                              ROOT / "out" / "a5" / "a6_closeup.png"))
BUS_DIR = Path(os.environ.get("ANIM_A6_BUS_DIR", ROOT / "out" / "a5"))


def need(path):
    """Skip, with the reason stated, when a needed file is absent
    (the deposit leaves out the inputs' data files and outputs)."""
    if not Path(path).is_file():
        raise unittest.SkipTest(
            "needs %s - inputs/ and out/ are not in the deposit" % path)
    return path


def png_size(path):
    data = Path(path).read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG: %s" % path
    return struct.unpack(">II", data[16:24])


def near_white_count(path):
    width, height, rows = png_rows(path)
    channels = rows[0][0]
    count = 0
    for y in range(height):
        line = rows[y][1]
        for x in range(width):
            o = x * channels
            if line[o] > 240 and line[o + 1] > 240 and line[o + 2] > 240:
                count += 1
    return count


class TestA6BusFace(unittest.TestCase):
    def test_busface_two_styles(self):
        need(BUS_DIR / "a6_bus_plate.png")
        stills = {}
        for style in ("plate", "paint"):
            path = BUS_DIR / ("a6_bus_%s.png" % style)
            self.assertTrue(path.is_file(),
                            "missing %s - run build_a5.py --busface" % path)
            self.assertEqual(png_size(path), (1920, 1080), style)
            stills[style] = path.read_bytes()
        # Two lettering styles must actually differ on the face.
        self.assertNotEqual(stills["plate"], stills["paint"],
                            "plate and paint bus-face stills are identical")


class TestA6Closeup(unittest.TestCase):
    def test_closeup_glint(self):
        need(CLOSEUP)
        self.assertTrue(CLOSEUP.is_file(),
                        "missing %s - run build_a5.py --closeup" % CLOSEUP)
        self.assertEqual(png_size(CLOSEUP), (1920, 1080))
        # The Sun's glint sweeping the coverglass blows a large area to
        # near-white; the plain follow still has none (measured 0).
        self.assertGreater(near_white_count(CLOSEUP), 20000,
                           "no Sun glint in the array close-up")


if __name__ == "__main__":
    unittest.main()
