# SPDX-License-Identifier: GPL-3.0-or-later
"""A5 tests: true-scale geometry, the two cuts, and the look-pass stills.

Every test has a red case in tests/show_red.py.
Env override for red cases: ANIM_A5_REPORT.
"""

import json
import math
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import render_clip as R  # noqa: E402
import scene_spec as S  # noqa: E402
import solar  # noqa: E402
import truescale as TS  # noqa: E402
from test_a4 import png_rows  # noqa: E402

FIXTURES = Path(os.environ.get("ANIM_FIXTURE_DIR", ROOT / "out" / "a2"))

A5_REPORT = Path(os.environ.get("ANIM_A5_REPORT",
                                ROOT / "out" / "a5" / "a5_still_report.json"))


def png_size(path):
    data = Path(path).read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG: %s" % path
    return struct.unpack(">II", data[16:24])


class TestTrueScale(unittest.TestCase):
    def test_local_basis_known(self):
        east, north, up = TS.local_basis(0.0, 0.0)
        for got, want in ((up, (1, 0, 0)), (east, (0, 1, 0)),
                          (north, (0, 0, 1))):
            for g, w in zip(got, want):
                self.assertAlmostEqual(g, w, places=9)
        # The craft's own subpoint is straight down, one altitude away.
        row = S.orbit_row_at(S.read_orbit(), 900.0)
        basis = TS.local_basis(row["lat_deg"], row["lon_deg"])
        below = TS.point_local_m(row["lat_deg"], row["lon_deg"],
                                 TS.EARTH_RADIUS_M, basis,
                                 (row["lat_deg"], row["lon_deg"]),
                                 row["alt_km"])
        self.assertAlmostEqual(below[0], 0.0, places=3)
        self.assertAlmostEqual(below[1], 0.0, places=3)
        self.assertAlmostEqual(below[2], -row["alt_km"] * 1000.0, places=3)
        # Earth's center is one radius further down the same line.
        self.assertEqual(TS.earth_center_m(row["alt_km"])[2],
                         below[2] - TS.EARTH_RADIUS_M)
        # The station is west and north of the MET-900 subpoint, and below.
        station = S.read_station()
        local = TS.point_local_m(station["lat_deg"], station["lon_deg"],
                                 TS.EARTH_RADIUS_M, basis,
                                 (row["lat_deg"], row["lon_deg"]),
                                 row["alt_km"])
        self.assertLess(local[0], 0.0)     # west
        self.assertGreater(local[1], 0.0)  # north
        self.assertLess(local[2], 0.0)     # below
        # The derived Sun at MET 900 is above the horizon (record: sunlit).
        epoch = solar.read_epoch("dev-ph2-p3-open-01")
        sun = TS.to_local(S.latlon_to_xyz(*solar.sun_latlon_at(epoch, 900), 1.0),
                          basis)
        self.assertGreater(sun[2], 0.3)
        self.assertAlmostEqual(math.sqrt(sum(v * v for v in sun)), 1.0,
                               places=9)


class TestCuts(unittest.TestCase):
    def test_cut_argument(self):
        args = R.parse_args(["--timeline", "some/run.js", "--output",
                             "some/out", "--cut", "clean", "--dry-run"])
        self.assertIn("--cut clean", " ".join(R.build_command(args)))
        args = R.parse_args(["--timeline", "some/run.js", "--output",
                             "some/out", "--dry-run"])
        self.assertIn("--cut instrument", " ".join(R.build_command(args)))


class TestStills(unittest.TestCase):
    def test_a5_still_report(self):
        self.assertTrue(A5_REPORT.is_file(),
                        "no A5 still report - run build_a5.py in Blender")
        report = json.loads(A5_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["met_s"], 900)
        self.assertEqual(report["engine"], "CYCLES")
        # Round three works at 960 x 540 until the Director approves
        # the look (finals return to full size after approval).
        self.assertEqual(report["resolution"], [960, 540])
        self.assertAlmostEqual(report["camera_distance_m"], 3.1, delta=0.6)
        row = S.orbit_row_at(S.read_orbit(), 900.0)
        self.assertAlmostEqual(report["alt_km"], row["alt_km"], places=3)
        for cut in ("clean", "instrument"):
            still = ROOT / "out" / "a5" / report["stills"][cut]
            self.assertTrue(still.is_file())
            self.assertGreater(still.stat().st_size, 100000)
            self.assertEqual(png_size(still), (960, 540))
        # Same moment, same state, both cuts.
        self.assertEqual(report["state"]["load_limit"], "YELLOW_HIGH")
        self.assertTrue(report["state"]["sunlit"])
        self.assertTrue(report["state"]["in_contact"])


class TestFixtureLook(unittest.TestCase):
    def test_fixture_stills_new_look(self):
        for name in ("fixture_890_sunlit.png", "fixture_920_eclipse_red.png",
                     "fixture_945_safe_deny.png"):
            path = FIXTURES / name
            self.assertTrue(path.is_file(), "missing %s" % name)
            self.assertEqual(png_size(path), (960, 540), name)
        # Sensor strikes: the denoiser softens each 1-3 px speck into a
        # small bright blob, so count small bright components ringed by
        # dark pixels. Clouds and glints are large components and do
        # not count; an old-look or strike-less still has none.
        width, height, rows = png_rows(FIXTURES / "fixture_920_eclipse_red.png")
        channels = rows[0][0]
        gray = [[(rows[y][1][x * channels] + rows[y][1][x * channels + 1]
                  + rows[y][1][x * channels + 2]) / 3.0
                 for x in range(width)] for y in range(height)]
        seen = [[False] * width for _ in range(height)]
        blobs = 0
        for y in range(height):
            for x in range(width):
                if gray[y][x] <= 205 or seen[y][x]:
                    continue
                stack, comp = [(x, y)], []
                seen[y][x] = True
                while stack:
                    cx, cy = stack.pop()
                    comp.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < width and 0 <= ny < height \
                                and not seen[ny][nx] and gray[ny][nx] > 205:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
                if len(comp) > 12:
                    continue
                comp_set = set(comp)
                xs = [c[0] for c in comp]
                ys = [c[1] for c in comp]
                ring = [gray[yy][xx]
                        for yy in range(max(0, min(ys) - 2), min(height, max(ys) + 3))
                        for xx in range(max(0, min(xs) - 2), min(width, max(xs) + 3))
                        if (xx, yy) not in comp_set]
                if ring and sum(ring) / len(ring) < 90:
                    blobs += 1
        self.assertGreater(blobs, 5, "no camera strikes in the eclipse still")


if __name__ == "__main__":
    unittest.main()
