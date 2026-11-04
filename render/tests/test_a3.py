# SPDX-License-Identifier: GPL-3.0-or-later
"""A3 tests: the sync file, and the derived Sun agreeing with the record.

The sync test the brief asks for: a frame's MET from the sync file must
match the frame the driver actually keyframed at that MET (a2_report).
The solar test checks the low-precision Sun at the run's epoch against
the record's ADM_ECLIPSE at every orbit row the record covers, in the
form inputs/epochs.json itself was checked.
Every test has a red case in tests/show_red.py.
Env overrides for red cases: ANIM_SYNC, ANIM_A2_REPORT.
"""

import hashlib
import json
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scene_spec as S  # noqa: E402
import solar  # noqa: E402
import sync as Y  # noqa: E402
import timeline as T  # noqa: E402

OPEN01 = ROOT / "inputs" / "timelines" / "dev-ph2-p3-open-01.js"
SYNC_FILE = Path(os.environ.get(
    "ANIM_SYNC", ROOT / "out" / "a2" / "dev-ph2-p3-open-01_preview.sync.json"))
A2_REPORT = Path(os.environ.get("ANIM_A2_REPORT",
                                ROOT / "out" / "a2" / "a2_report.json"))


def need(path):
    """Skip, with the reason stated, when a needed file is absent
    (the deposit leaves out the inputs' data files and outputs)."""
    if not Path(path).is_file():
        raise unittest.SkipTest(
            "needs %s - inputs/ and out/ are not in the deposit" % path)
    return path


class TestSolarAgreement(unittest.TestCase):
    def test_derived_sun_agrees_with_record(self):
        need(ROOT / "inputs" / "epochs.json")
        need(OPEN01)
        need(S.ORBIT_CSV)
        epoch = solar.read_epoch("dev-ph2-p3-open-01")
        self.assertIsNotNone(epoch)
        self.assertEqual(epoch.isoformat(), "2026-08-01T13:28:23+00:00")
        tl = T.load_timeline(OPEN01)
        rows = [r for r in S.read_orbit() if 800 <= r["met_s"] <= 1225]
        self.assertEqual(len(rows), 86)
        for row in rows:
            lat, lon = solar.sun_latlon_at(epoch, row["met_s"])
            sun = S.latlon_to_xyz(lat, lon, 1.0)
            pos = S.latlon_to_xyz(row["lat_deg"], row["lon_deg"],
                                  6371.0 + row["alt_km"])
            derived = solar.sunlit_cylindrical(pos, sun)
            recorded = T.state_at(tl, int(row["met_s"]))["sunlit"]
            self.assertEqual(derived, recorded,
                             "sun disagreement at MET %s" % row["met_s"])
            self.assertEqual(derived, bool(row["sunlit_by_orbit"]))
        # Discrimination: the same geometry six hours earlier is night,
        # so the agreement above is the epoch working, not a constant.
        early = epoch - timedelta(hours=6)
        lit = 0
        for row in rows:
            lat, lon = solar.sun_latlon_at(early, row["met_s"])
            sun = S.latlon_to_xyz(lat, lon, 1.0)
            pos = S.latlon_to_xyz(row["lat_deg"], row["lon_deg"],
                                  6371.0 + row["alt_km"])
            lit += solar.sunlit_cylindrical(pos, sun)
        self.assertLessEqual(lit, 4)
        # Phase 1 has no epoch: no Sun to derive.
        self.assertIsNone(solar.read_epoch("PH1-SHAKEDOWN-SPARK-R4"))


class TestSyncFile(unittest.TestCase):
    def test_sync_file_matches_frames(self):
        need(SYNC_FILE)
        need(A2_REPORT)
        need(OPEN01)
        self.assertTrue(SYNC_FILE.is_file(),
                        "no sync file - run build_a2.py in Blender")
        self.assertTrue(A2_REPORT.is_file())
        sync = Y.read_sync(SYNC_FILE)
        self.assertEqual(sync["run_id"], "dev-ph2-p3-open-01")
        self.assertEqual(sync["timeline_sha256"],
                         hashlib.sha256(OPEN01.read_bytes()).hexdigest())
        self.assertEqual(sync["first_frame_met_s"], 800)
        self.assertEqual(sync["met_step_s"], 5)
        self.assertEqual(sync["fps"], 10)
        report = json.loads(A2_REPORT.read_text(encoding="utf-8"))
        # Every keyframed frame sits where the sync file puts it.
        for frame in report["frames"]:
            self.assertEqual(Y.frame_met(sync, frame["frame"]), frame["met_s"],
                             "frame %s" % frame["frame"])
        # The known moment: MET 900 (load yellow) is frame 21.
        self.assertEqual(Y.frame_met(sync, 21), 900)
        by_met = {f["met_s"]: f for f in report["frames"]}
        self.assertEqual(by_met[900]["frame"], 21)


if __name__ == "__main__":
    unittest.main()
