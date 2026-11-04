# SPDX-License-Identifier: GPL-3.0-or-later
"""A1 tests: the spacecraft and the scene.

Every test here has a red case in tests/show_red.py (the brief, rule 8).
Run:  python -m unittest discover -s tests
Optional env overrides (used by show_red.py to point a test at a planted
copy): ANIM_INPUTS, ANIM_REPORT, ANIM_STILLS, ANIM_SOURCES.
"""

import hashlib
import json
import math
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scene_spec as S  # noqa: E402

INPUTS = Path(os.environ.get("ANIM_INPUTS", ROOT / "inputs"))
REPORT = Path(os.environ.get("ANIM_REPORT", S.REPORT_JSON))
STILLS = Path(os.environ.get("ANIM_STILLS", S.OUT_DIR))
SOURCES = Path(os.environ.get("ANIM_SOURCES", ROOT))


def png_size(path):
    """(width, height) from a PNG file's IHDR chunk."""
    data = Path(path).read_bytes()[:24]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG: %s" % path
    return struct.unpack(">II", data[16:24])


def load_report():
    return json.loads(Path(REPORT).read_text(encoding="utf-8"))


def need(path):
    """Skip, with the reason stated, when a needed file is absent.

    The deposit leaves out the inputs' data files and rendered
    outputs, so from a fresh unzip the tests that read them skip
    instead of failing; with them present nothing is skipped."""
    if not Path(path).is_file():
        raise unittest.SkipTest(
            "needs %s - inputs/ and out/ are not in the deposit" % path)
    return path


class TestInputsManifest(unittest.TestCase):
    def test_manifest_hashes_match(self):
        manifest = INPUTS / "MANIFEST.sha256"
        need(INPUTS / "epochs.json")
        self.assertTrue(manifest.is_file(), "missing %s" % manifest)
        seen = 0
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            expected, rel = line.split(None, 1)
            target = INPUTS / rel.strip().lstrip("*")
            self.assertTrue(target.is_file(), "manifest file missing: %s" % rel)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            self.assertEqual(digest, expected.lower(), "hash mismatch: %s" % rel)
            seen += 1
        # 12 at A1; +2 in A3 (epochs, high-resolution texture); +3 more
        # imagery files placed during A4 (night lights, clouds, sources);
        # +1 in A8 (the scored PH2-PASS3-SPARK-R2 timeline).
        self.assertEqual(seen, 18, "expected 18 manifest entries, saw %d" % seen)


class TestLatLonMath(unittest.TestCase):
    def test_latlon_known_points(self):
        cases = [
            # (lat, lon) -> unit vector in the documented scene frame
            ((0.0, 0.0), (1.0, 0.0, 0.0)),
            ((0.0, 90.0), (0.0, 1.0, 0.0)),
            ((0.0, -90.0), (0.0, -1.0, 0.0)),
            ((90.0, 30.0), (0.0, 0.0, 1.0)),
            ((-90.0, 30.0), (0.0, 0.0, -1.0)),
            ((0.0, 180.0), (-1.0, 0.0, 0.0)),
        ]
        for (lat, lon), expected in cases:
            got = S.latlon_to_xyz(lat, lon, 1.0)
            for g, e in zip(got, expected):
                self.assertAlmostEqual(g, e, places=9,
                                       msg="latlon (%s, %s)" % (lat, lon))

    def test_station_on_earth_surface(self):
        station = S.read_station(need(INPUTS / "orbit" / "station.json"))
        self.assertEqual(station["name"], "GS-RAVENSROOST")
        self.assertAlmostEqual(station["lat_deg"], 28.5219, places=4)
        self.assertAlmostEqual(station["lon_deg"], -80.6817, places=4)
        x, y, z = S.station_xyz(station)
        self.assertAlmostEqual(math.sqrt(x * x + y * y + z * z),
                               S.SCENE_EARTH_RADIUS, places=9)
        # Florida: north (z > 0), western hemisphere toward -Y in this frame
        # for negative longitude past -0 (sin(lon) < 0), x > 0 before -90.
        self.assertGreater(z, 0.0)
        self.assertGreater(x, 0.0)
        self.assertLess(y, 0.0)


class TestOrbit(unittest.TestCase):
    def test_orbit_known_moments(self):
        rows = S.read_orbit(need(INPUTS / "orbit" / "P3-orbit.csv"))
        self.assertEqual(len(rows), 247)
        self.assertEqual(rows[0]["met_s"], 0.0)
        self.assertEqual(rows[-1]["met_s"], 1230.0)
        # Contact begins at MET 800 and lasts to the end (orbit README).
        first_visible = min(r["met_s"] for r in rows if r["station_visible"] == 1)
        self.assertEqual(first_visible, 800.0)
        self.assertTrue(all(r["station_visible"] == 1
                            for r in rows if r["met_s"] >= 800.0))
        # Sunlit for the whole run, as the telemetry says.
        self.assertTrue(all(r["sunlit_by_orbit"] == 1 for r in rows))
        # Exact row at the A1 placement MET.
        placed = S.orbit_row_at(rows, S.PLACEMENT_MET_S)
        self.assertAlmostEqual(placed["lat_deg"], 28.0742, places=4)
        self.assertAlmostEqual(placed["lon_deg"], -77.5194, places=4)
        self.assertAlmostEqual(placed["alt_km"], 507.997, places=3)
        # Interpolation halfway between MET 1000 and 1005.
        mid = S.orbit_row_at(rows, 1002.5)
        self.assertAlmostEqual(mid["lat_deg"], (28.0742 + 28.3882) / 2.0, places=4)
        # Drawn orbit height: about 510 km over a 6371 km Earth.
        radius = math.dist((0.0, 0.0, 0.0), S.orbit_xyz(placed))
        self.assertAlmostEqual(radius,
                               S.scene_radius_for_alt_km(507.997), places=9)
        self.assertTrue(10.7 < radius < 10.9)


class TestSpacecraftSpec(unittest.TestCase):
    def test_cubesat_proportions(self):
        # From inputs/spacecraft.md: about 10 x 22.6 x 36.6 cm.
        self.assertEqual(sorted(S.BUS_DIMS_M), [0.100, 0.226, 0.366])
        # Twin arrays, each of whole panels; wingspan wider than the bus.
        self.assertGreaterEqual(S.PANELS_PER_WING, 1)
        wing_m = S.PANELS_PER_WING * S.PANEL_SIZE_M[0]
        wingspan_m = S.BUS_DIMS_M[0] + 2.0 * wing_m
        self.assertGreater(wingspan_m, 3.0 * S.BUS_DIMS_M[0])
        # Panels are thin sheets, not blocks.
        self.assertLess(S.PANEL_SIZE_M[1], 0.02)
        # The enlargement next to Earth is large and must be stated, so the
        # report/caption value is pinned here against silent drift.
        self.assertGreater(S.spacecraft_enlargement(), 100000.0)


class TestSceneReport(unittest.TestCase):
    def test_scene_report(self):
        need(REPORT)
        need(INPUTS / "orbit" / "P3-orbit.csv")
        self.assertTrue(REPORT.is_file(),
                        "no scene report at %s - run build_a1.py in Blender" % REPORT)
        report = load_report()
        self.assertEqual(report["render"]["width"], S.RENDER_WIDTH)
        self.assertEqual(report["render"]["height"], S.RENDER_HEIGHT)
        self.assertEqual(report["earth"]["texture"], S.EARTH_TEXTURE_NAME)
        self.assertAlmostEqual(report["earth"]["radius"],
                               S.SCENE_EARTH_RADIUS, places=6)
        self.assertAlmostEqual(report["earth"]["texture_rotation_deg"],
                               S.EARTH_TEXTURE_ROTATION_DEG, places=6)
        self.assertEqual(report["station"]["name"], "GS-RAVENSROOST")
        station = S.read_station(INPUTS / "orbit" / "station.json")
        for got, want in zip(report["station"]["xyz"], S.station_xyz(station)):
            self.assertAlmostEqual(got, want, places=5)
        # Spacecraft built at true 6U proportions times the display scale.
        dims = report["spacecraft"]["bus_dims_scene"]
        for got, want_m in zip(dims, S.BUS_DIMS_M):
            self.assertAlmostEqual(got, want_m * S.SPACECRAFT_DISPLAY_SCALE,
                                   places=5)
        self.assertEqual(report["spacecraft"]["placement_met_s"],
                         S.PLACEMENT_MET_S)
        # Placed on the orbit, not floating at a guessed spot.
        rows = S.read_orbit(INPUTS / "orbit" / "P3-orbit.csv")
        placed = S.orbit_xyz(S.orbit_row_at(rows, S.PLACEMENT_MET_S))
        for got, want in zip(report["spacecraft"]["xyz"], placed):
            self.assertAlmostEqual(got, want, places=5)
        names = set(report["objects"])
        for required in ("Earth", "Sun", "SunLight", "OrbitPath",
                         "GroundStation", "HUGINN_Bus",
                         "SA1_Panel1", "SA2_Panel1", "Payload",
                         "CameraWide", "CameraHero", "CameraPayload"):
            self.assertIn(required, names)
        # The orbit curve carries every orbit row.
        self.assertEqual(report["orbit"]["point_count"], 247)
        # Sun disk sits along the drawn sun direction.
        sun = report["sun"]["xyz"]
        dist = math.dist((0.0, 0.0, 0.0), sun)
        self.assertAlmostEqual(dist, S.SUN_DISTANCE, places=5)
        for got, want in zip(sun, S.sun_direction()):
            self.assertAlmostEqual(got / dist, want, places=5)
        self.assertEqual(sorted(report["stills"]), sorted(S.STILL_NAMES))


class TestStills(unittest.TestCase):
    def test_still_files(self):
        need(STILLS / S.STILL_NAMES[0])
        for name in S.STILL_NAMES:
            path = STILLS / name
            self.assertTrue(path.is_file(), "missing still %s" % path)
            self.assertGreater(path.stat().st_size, 20000,
                               "still suspiciously small: %s" % name)
            self.assertEqual(png_size(path), (S.RENDER_WIDTH, S.RENDER_HEIGHT),
                             "still not 1920 x 1080: %s" % name)


class TestCleanSources(unittest.TestCase):
    def test_no_absolute_paths_in_sources(self):
        # Built at runtime so this file does not itself contain the pattern.
        banned = ["C:" + "\\" + "Users" + "\\", "/" + "Users" + "/",
                  "/" + "home" + "/"]
        checked = 0
        for path in sorted(Path(SOURCES).rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".py", ".md", ".json", ".txt"):
                continue
            if "inputs" in path.parts or "out" in path.parts:
                continue
            # .venv is the Modal client's install (A7 setup), tool
            # output like out/, never a source in this folder.
            if ".hg" in path.parts or ".eden" in path.parts or ".agents" in path.parts or ".venv" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="strict")
            for needle in banned:
                self.assertNotIn(needle, text,
                                 "absolute user path in %s" % path.name)
            checked += 1
        self.assertGreater(checked, 0, "no source files were checked")

    def test_build_is_read_only(self):
        # The build must not send commands or reach the network (brief rule 4).
        text = (ROOT / "build_a1.py").read_text(encoding="utf-8")
        for needle in ("urllib", "socket", "requests" + ".", "subprocess",
                       "os" + ".system"):
            self.assertNotIn(needle, text, "build script contains %r" % needle)


if __name__ == "__main__":
    unittest.main()
