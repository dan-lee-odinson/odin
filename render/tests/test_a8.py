# SPDX-License-Identifier: GPL-3.0-or-later
"""A8 tests: the scored run's input, a MET step that need not be whole,
and render_modal.py generalized beyond the final clean cut.

Every test has a red case in tests/show_red.py.
Env override for red cases: ANIM_A8_INPUTS.
"""

import ast
import json
import os
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import render_clip as R  # noqa: E402
import render_modal as M  # noqa: E402
import sync as Y  # noqa: E402
import timeline as T  # noqa: E402

INPUTS = Path(os.environ.get("ANIM_A8_INPUTS", ROOT / "inputs"))
SCORED_RUN = "PH2-PASS3-SPARK-R2"
SCORED_SHA256 = ("d0f1a57349d60cbee5835f3bac6a945e02762ecf"
                 "49387ebca6caa968d12fe617")
SCORED_TIMELINE = INPUTS / "timelines" / (SCORED_RUN + ".js")


def need(path):
    """Skip, with the reason stated, when a needed file is absent
    (the deposit leaves out the inputs' data files and outputs)."""
    if not Path(path).is_file():
        raise unittest.SkipTest(
            "needs %s - inputs/ and out/ are not in the deposit" % path)
    return path


class TestScoredInput(unittest.TestCase):
    def test_scored_timeline_input(self):
        need(SCORED_TIMELINE)
        self.assertTrue(SCORED_TIMELINE.is_file())
        self.assertEqual(SCORED_TIMELINE.stat().st_size, 504249)
        self.assertEqual(Y.timeline_sha256(SCORED_TIMELINE), SCORED_SHA256)
        timeline = T.load_timeline(SCORED_TIMELINE)
        self.assertEqual(timeline["id"], SCORED_RUN)
        self.assertEqual(T.telemetry_span(timeline), (800, 1229))
        # Known moments from the record itself, as in A2's checks.
        at900 = T.state_at(timeline, 900)
        self.assertTrue(at900["sunlit"] and at900["in_contact"])
        self.assertEqual(at900["load_limit"], "YELLOW_HIGH")
        self.assertIsNone(at900["weather"])  # this run carries no feed
        cus = {(c["met_s"], c["kind"]) for c in T.request_cues(timeline)}
        self.assertIn((909, "baldur"), cus)
        # The epochs mark it in the inputs; the manifest covers it.
        epochs = json.loads((INPUTS / "epochs.json").read_text())
        entry = epochs["runs"][SCORED_RUN]
        self.assertTrue(entry["timeline_in_your_inputs"])
        self.assertFalse(entry["shifted"])
        self.assertEqual(M.verify_inputs_manifest(INPUTS), 18)

    def test_scored_run_orbit(self):
        self.assertEqual(T.orbit_path_for(SCORED_RUN), T.P3_ORBIT_CSV)
        self.assertEqual(T.orbit_path_for("PH2-PASS3-OPEN-R9"),
                         T.P3_ORBIT_CSV)
        self.assertEqual(T.orbit_path_for("dev-ph2-p3-open-01"),
                         T.P3_ORBIT_CSV)
        self.assertIsNone(T.orbit_path_for("PH1-SHAKEDOWN-SPARK-R4"))
        self.assertIsNone(T.orbit_path_for("PH2-PASS1-SPARK-R1"))


class TestFractionalStep(unittest.TestCase):
    def test_fractional_step_exact(self):
        need(SCORED_TIMELINE)
        mets = Y.frame_mets(880, 1000, Fraction(1, 15))
        self.assertEqual(len(mets), 1801)
        self.assertEqual(mets[0], Fraction(880))
        self.assertEqual(mets[-1], Fraction(1000))
        for i, met in enumerate(mets):
            self.assertEqual(met, Fraction(880) + i * Fraction(1, 15))
        sync = Y.make_sync(SCORED_RUN, SCORED_TIMELINE,
                           Y.sync_number(mets[0]),
                           Y.sync_number(Fraction(1, 15)), 30)
        self.assertEqual(sync["timeline_sha256"], SCORED_SHA256)
        self.assertEqual(sync["first_frame_met_s"], 880)
        self.assertAlmostEqual(sync["met_step_s"], 1.0 / 15, places=15)
        for i, met in enumerate(mets, start=1):
            self.assertAlmostEqual(Y.frame_met(sync, i), float(met),
                                   places=9)
        self.assertEqual(Y.step_text(Fraction(1, 15)), "1/15")
        self.assertEqual(Y.parse_met_step("1/15"), Fraction(1, 15))

    def test_whole_step_unchanged(self):
        need(INPUTS / "timelines" / "dev-ph2-p3-open-01.js")
        need(ROOT / "out" / "a6anim"
             / "dev-ph2-p3-open-01_a5_clean.sync.json")
        mets = Y.frame_mets(800, 1225, 5)
        self.assertEqual([Y.sync_number(m) for m in mets],
                         list(range(800, 1226, 5)))
        self.assertTrue(all(isinstance(Y.sync_number(m), int)
                            for m in mets))
        # The sync file a whole-second step writes is byte-identical
        # in content to the one already beside the A6 clean clip.
        made = Y.make_sync("dev-ph2-p3-open-01",
                           INPUTS / "timelines" / "dev-ph2-p3-open-01.js",
                           800, Y.sync_number(Y.parse_met_step("5")), 10)
        saved = Y.read_sync(ROOT / "out" / "a6anim"
                            / "dev-ph2-p3-open-01_a5_clean.sync.json")
        self.assertEqual(made, saved)
        self.assertIsInstance(made["met_step_s"], int)
        self.assertEqual(Y.step_text(5), "5")

    def test_render_clip_fractional_command(self):
        args = R.parse_args([
            "--timeline", "some/run.js", "--output", "some/out",
            "--met-start", "880", "--met-end", "13202/15",
            "--met-step", "1/15", "--dry-run"])
        joined = " ".join(R.build_command(args))
        self.assertIn("--step 1/15", joined)
        self.assertIn("--met-start 880", joined)
        self.assertIn("--met-end 13202/15", joined)
        # build_a5 carries the fraction exactly, through the frame
        # METs and into the sync file (no int() truncation of the step).
        build_a5 = (ROOT / "build_a5.py").read_text(encoding="utf-8")
        self.assertIn("Y.frame_mets(start_met, end_met, step)", build_a5)
        self.assertIn("Y.sync_number(step)", build_a5)
        self.assertNotIn('int(arg("--step"', build_a5)


class TestModalGeneralized(unittest.TestCase):
    SITE = dict(run_id=SCORED_RUN, cut="instrument", width=1024,
                height=576, met_start="800", met_end="1225",
                met_step="1", clip=SCORED_RUN + "_instrument_site.mp4")
    FOOTAGE = dict(run_id=SCORED_RUN, cut="instrument", width=1024,
                   height=576, met_start="880", met_end="1000",
                   met_step="1/15",
                   clip=SCORED_RUN + "_instrument_footage.mp4")

    def test_modal_defaults_unchanged(self):
        spec = M.resolve_render()
        self.assertEqual(spec["run_id"], "dev-ph2-p3-open-01")
        self.assertEqual(spec["cut"], "clean")
        self.assertEqual((spec["width"], spec["height"]), (1920, 1080))
        self.assertEqual(spec["frame_count"], 426)
        self.assertEqual(spec["probe_frame_count"], 3)
        self.assertEqual(spec["clip"], M.FINAL_CLIP)
        self.assertEqual(spec["probe_clip"], M.PROBE_CLIP)
        self.assertEqual(Y.sync_number(spec["probe_met_end"]), 802)
        self.assertEqual(spec["timing_name"], M.PROBE_TIMING_NAME)
        command = M.build_render_command(
            spec["met_start"], spec["met_end"], spec["clip"])
        self.assertEqual(command, M.build_render_command(
            800, 1225, M.FINAL_CLIP))

    def test_modal_two_clips_commands(self):
        site = M.resolve_render(**self.SITE)
        self.assertEqual(site["frame_count"], 426)
        self.assertEqual(M.build_render_command(
            site["met_start"], site["met_end"], site["clip"],
            run_id=site["run_id"], cut=site["cut"],
            width=site["width"], height=site["height"],
            met_step=site["met_step"]), [
            "python3", "/opt/huginn-render/render_clip.py",
            "--timeline",
            "/opt/huginn-render/inputs/timelines/PH2-PASS3-SPARK-R2.js",
            "--inputs", "/opt/huginn-render/inputs",
            "--output", "/tmp/huginn-final-out",
            "--clip", "PH2-PASS3-SPARK-R2_instrument_site.mp4",
            "--width", "1024", "--height", "576",
            "--met-start", "800", "--met-end", "1225",
            "--met-step", "1", "--fps", "30",
            "--engine", "CYCLES", "--samples", "48",
            "--cut", "instrument",
            "--blender", "/opt/blender/blender",
            "--require-gpu", "--perceptually-lossless"])
        footage = M.resolve_render(**self.FOOTAGE)
        self.assertEqual(footage["frame_count"], 1801)
        self.assertEqual(footage["probe_frame_count"], 3)
        self.assertEqual(Y.step_text(footage["probe_met_end"]), "13202/15")
        joined = " ".join(M.build_render_command(
            footage["met_start"], footage["met_end"], footage["clip"],
            run_id=footage["run_id"], cut=footage["cut"],
            width=footage["width"], height=footage["height"],
            met_step=footage["met_step"]))
        self.assertIn("--met-step 1/15", joined)
        self.assertIn("--clip PH2-PASS3-SPARK-R2_instrument_footage.mp4",
                      joined)

    def test_each_render_keeps_its_own_probe_timing(self):
        site = M.resolve_render(**self.SITE)
        footage = M.resolve_render(**self.FOOTAGE)
        self.assertEqual(site["timing_name"],
                         "PH2-PASS3-SPARK-R2_instrument_site"
                         "_probe_timing.json")
        self.assertNotEqual(site["timing_name"], footage["timing_name"])
        self.assertNotEqual(site["timing_name"], M.PROBE_TIMING_NAME)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for name, cost in ((site["timing_name"], 2.5),
                               (footage["timing_name"], 9.5)):
                (out / name).write_text(json.dumps(
                    {"projected_full_cost_usd": cost}), encoding="utf-8")
            self.assertEqual(
                M.read_probe_projection_usd(out, site["timing_name"]), 2.5)
            self.assertEqual(
                M.read_probe_projection_usd(out, footage["timing_name"]),
                9.5)
            with self.assertRaises(FileNotFoundError):
                M.read_probe_projection_usd(out, M.PROBE_TIMING_NAME)


def load_cue_frames():
    """cue_frames (and its flash-length helper) out of build_a2.py.

    build_a2 imports bpy, so the pure functions are exec'd from its
    source with just the names they use."""
    tree = ast.parse((ROOT / "build_a2.py").read_text(encoding="utf-8"))
    wanted = [node for node in tree.body
              if isinstance(node, ast.FunctionDef)
              and node.name in ("cue_frames", "cue_flash_frames")]
    namespace = {"Fraction": Fraction, "MET_STEP_S": 5}
    exec(compile(ast.Module(wanted, []), "build_a2.py", "exec"), namespace)
    return namespace["cue_frames"]


CUES = [{"met_s": 909, "kind": "odin"},
        {"met_s": 909, "kind": "baldur", "decision": "ALLOW"},
        {"met_s": 909, "kind": "dispatch"}]


class TestCueFlash(unittest.TestCase):
    def test_cue_flash_fractional_step(self):
        cue_frames = load_cue_frames()
        # Footage geometry: MET 880 at 1/15 s a frame. The cue at
        # MET 909 lands on frame 436 and lights 30 frames: two full
        # seconds of MET, not two frames (2/15 s, invisible at 2x).
        active = cue_frames(CUES, 880, 1801, Fraction(1, 15))
        lit = sorted(f for f in active if "odin" in active[f])
        self.assertEqual(lit, list(range(436, 436 + 30)))
        self.assertEqual(len(lit), 30)
        self.assertIn("baldur:ALLOW", active[465])
        self.assertNotIn(466, active)

    def test_cue_flash_whole_steps_unchanged(self):
        cue_frames = load_cue_frames()
        # A6 geometry at 5 s a frame, and the site clip at 1 s a
        # frame: two frames already cover two MET seconds or more,
        # so the mapping is exactly the pre-A8B two-frame flash.
        at5 = cue_frames(CUES, 800, 86, 5)
        frame5 = int(round((909 - 800) / 5)) + 1
        self.assertEqual(sorted(at5), [frame5, frame5 + 1])
        at1 = cue_frames(CUES, 800, 426, 1)
        self.assertEqual(sorted(at1), [110, 111])
        for active in (at5, at1):
            for kinds in active.values():
                self.assertEqual(
                    kinds, {"odin", "baldur", "baldur:ALLOW", "dispatch"})


if __name__ == "__main__":
    unittest.main()
