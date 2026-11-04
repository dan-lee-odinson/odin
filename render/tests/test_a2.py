# SPDX-License-Identifier: GPL-3.0-or-later
"""A2 tests: the record drives the scene.

Known moments are read off inputs/timelines/dev-ph2-p3-open-01.js itself
(contact start, the load going yellow and falling back, ODIN's shed and
BALDUR-0's allow). No input run carries an eclipse entry or a feed, so
those drawings are tested on tests/fixtures/made_up_timeline.json and the
made-up feed only, and are never drawn over a real run.
Every test has a red case in tests/show_red.py.
Env override for red cases: ANIM_A2_REPORT.
"""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import timeline as T  # noqa: E402

OPEN01 = ROOT / "inputs" / "timelines" / "dev-ph2-p3-open-01.js"
FEED = ROOT / "inputs" / "feeds" / "made-up-feed-timeline.json"
FIXTURE = ROOT / "tests" / "fixtures" / "made_up_timeline.json"
A2_REPORT = Path(os.environ.get("ANIM_A2_REPORT",
                                ROOT / "out" / "a2" / "a2_report.json"))


def need(path):
    """Skip, with the reason stated, when a needed file is absent
    (the deposit leaves out the inputs' data files and outputs)."""
    if not Path(path).is_file():
        raise unittest.SkipTest(
            "needs %s - inputs/ and out/ are not in the deposit" % path)
    return path


class TestKnownMoments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tl = T.load_timeline(need(OPEN01))

    def test_known_moments_open01(self):
        tl = self.tl
        self.assertEqual(tl["id"], "dev-ph2-p3-open-01")
        # Contact start: the recorded span, not the planned window alone.
        self.assertEqual(T.contact_spans(tl), [(800, 1229)])
        self.assertTrue(T.state_at(tl, 800)["in_contact"])
        # Telemetry starts at contact; before it there's no value.
        self.assertEqual(T.telemetry_span(tl), (800, 1229))
        self.assertIsNone(T.state_at(tl, 700)["sunlit"])
        # One limit change, each way, at the timeline's own values.
        at899 = T.state_at(tl, 899)
        self.assertEqual((at899["load_i"], at899["load_limit"]), (1.4, "GREEN"))
        at900 = T.state_at(tl, 900)
        self.assertEqual((at900["load_i"], at900["load_limit"]),
                         (1.8, "YELLOW_HIGH"))
        at913 = T.state_at(tl, 913)
        self.assertEqual((at913["load_i"], at913["load_limit"]), (1.2, "GREEN"))
        self.assertFalse(at913["payload_on"])
        self.assertTrue(T.state_at(tl, 912)["payload_on"])
        # Sunlit and NOMINAL throughout this run.
        for met in (800, 900, 1000, 1229):
            self.assertTrue(T.state_at(tl, met)["sunlit"])
            self.assertEqual(T.state_at(tl, met)["mode"], "NOMINAL")
        # ODIN's shed, BALDUR-0's allow, the dispatch.
        cues = T.request_cues(tl)
        self.assertIn({"met_s": 912, "kind": "odin",
                       "command": "CMD_PLD_SET_STATE"}, cues)
        self.assertIn({"met_s": 912, "kind": "baldur", "decision": "ALLOW"}, cues)
        self.assertIn({"met_s": 912, "kind": "dispatch",
                       "command": "CMD_PLD_SET_STATE"}, cues)


class TestFixtureDrawings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tl = T.load_timeline(FIXTURE)

    def test_fixture_eclipse_and_modes(self):
        tl = self.tl
        self.assertTrue(tl["made_up"])
        # The eclipse entry no real input run carries: MET 900.
        self.assertTrue(T.state_at(tl, 899)["sunlit"])
        self.assertFalse(T.state_at(tl, 900)["sunlit"])
        self.assertTrue(T.state_at(tl, 960)["sunlit"])
        self.assertEqual(T.state_at(tl, 900)["sa1_i"], 0.0)
        # Safe mode and a red limit, nowhere in the real runs either.
        self.assertEqual(T.state_at(tl, 930)["mode"], "SAFE")
        self.assertEqual(T.state_at(tl, 910)["load_limit"], "RED_HIGH")
        self.assertFalse(T.state_at(tl, 880)["payload_on"])
        # Recorded contact only, not the planned window.
        self.assertEqual(T.contact_spans(tl), [(820, 980)])
        self.assertFalse(T.state_at(tl, 810)["in_contact"])
        # A BALDUR-0 deny cue.
        self.assertIn({"met_s": 941, "kind": "baldur", "decision": "DENY"},
                      T.request_cues(tl))


class TestNoFeedNoOrbit(unittest.TestCase):
    def test_no_feed_no_weather(self):
        tl = T.load_timeline(need(OPEN01))
        need(FEED)
        for met in (800, 1000, 1229):
            self.assertIsNone(T.state_at(tl, met)["weather"])
        # The made-up feed drives weather state only when handed in.
        reports = T.load_feed(FEED)
        self.assertTrue(reports)
        got = T.state_at(tl, reports[0]["met_s"], reports)["weather"]
        self.assertEqual(got["proton_flux_pfu"],
                         reports[0]["content"]["proton_flux_pfu"])
        self.assertTrue(got["made_up"])

    def test_phase1_has_no_orbit(self):
        need(T.P3_ORBIT_CSV)
        self.assertIsNone(T.orbit_path_for("PH1-SHAKEDOWN-SPARK-R4"))
        self.assertIsNone(T.orbit_path_for("something-else"))
        for run in ("dev-ph2-p3-open-01", "dev-ph2-p3-spark-01"):
            path = T.orbit_path_for(run)
            self.assertIsNotNone(path)
            self.assertTrue(path.is_file())


class TestA2Report(unittest.TestCase):
    def test_a2_preview_report(self):
        need(A2_REPORT)
        self.assertTrue(A2_REPORT.is_file(),
                        "no A2 report - run build_a2.py in Blender")
        report = json.loads(A2_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["run_id"], "dev-ph2-p3-open-01")
        self.assertEqual(report["met_step_s"], 5)
        self.assertEqual(report["met_range"], [800, 1230])
        frames = report["frames"]
        self.assertEqual(len(frames), 87)
        by_met = {f["met_s"]: f for f in frames}
        # Frames carry the timeline's state at the known moments.
        self.assertTrue(by_met[800]["in_contact"])
        self.assertEqual(by_met[900]["load_limit"], "YELLOW_HIGH")
        self.assertTrue(by_met[910]["payload_on"])
        self.assertFalse(by_met[915]["payload_on"])
        self.assertEqual(by_met[915]["load_limit"], "GREEN")
        self.assertTrue(all(f["sunlit"] for f in frames))
        self.assertTrue(all(f["weather"] is None for f in frames))
        self.assertEqual(report["cues"]["baldur"],
                         [{"met_s": 912, "decision": "ALLOW"}])
        video = ROOT / "out" / "a2" / report["preview"]
        self.assertTrue(video.is_file())
        self.assertGreater(video.stat().st_size, 20000)


if __name__ == "__main__":
    unittest.main()
