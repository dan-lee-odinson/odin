# SPDX-License-Identifier: GPL-3.0-or-later
"""A9 tests: the pullback cut - one continuous move from the clean
cut's true-scale framing out to the whole sunlit Earth.

The camera math is pure (truescale.pullback_camera), checked frame by
frame here with the scored run's real Sun geometry at MET 1150; no
Blender render runs. Every test has a red case in tests/show_red.py.
"""

import math
import sys
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import render_clip as R  # noqa: E402
import render_modal as M  # noqa: E402
import scene_spec as S  # noqa: E402
import solar  # noqa: E402
import sync as Y  # noqa: E402
import truescale as TS  # noqa: E402

SCORED_RUN = "PH2-PASS3-SPARK-R2"


def need(path):
    """Skip, with the reason stated, when a needed file is absent
    (the deposit leaves out the inputs' data files and outputs)."""
    if not Path(path).is_file():
        raise unittest.SkipTest(
            "needs %s - inputs/ and out/ are not in the deposit" % path)
    return path


def clean_start_and_sun():
    """(clean cut's camera offset, sun direction, Earth center) at 1150.

    The offset replicates apply_met's clean framing math (side light,
    A6 drift) from the run's own orbit row and derived Sun."""
    rows = S.read_orbit(need(S.INPUTS / "orbit" / "P3-orbit.csv"))
    need(S.INPUTS / "epochs.json")
    epoch = solar.read_epoch(SCORED_RUN, path=S.INPUTS / "epochs.json")
    row = S.orbit_row_at(rows, 1150.0)
    basis = TS.local_basis(row["lat_deg"], row["lon_deg"])
    sun = TS.to_local(S.latlon_to_xyz(
        *solar.sun_latlon_at(epoch, 1150), 1.0), basis)
    horiz = math.hypot(sun[0], sun[1])
    sunward = (sun[0] / horiz, sun[1] / horiz, 0.0)
    perp = (-sunward[1], sunward[0], 0.0)
    if perp[1] > 0:
        perp = tuple(-v for v in perp)
    drift = math.radians(-9.0 + 18.0 * (350.0 / 425.0))
    along = 1.6 * math.cos(drift) - 2.3 * math.sin(drift)
    across = 1.6 * math.sin(drift) + 2.3 * math.cos(drift)
    start = tuple(sunward[i] * along + perp[i] * across
                  for i in range(3))
    start = (start[0], start[1], start[2] + 1.35)
    return start, sun, TS.earth_center_m(row["alt_km"])


def poses():
    start, sun, center = clean_start_and_sun()
    return [TS.pullback_camera(u / 240.0, start, center, sun)
            for u in range(241)]


def angle_deg(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / (na * nb)))))


class TestPullbackMove(unittest.TestCase):
    def test_camera_distance_grows_without_a_jump(self):
        dists = [p["distance_m"] for p in poses()]
        self.assertEqual(len(dists), 241)
        for before, after in zip(dists, dists[1:]):
            self.assertGreater(after, before)
            # Log-paced with eased ends: never more than a small
            # fraction farther than the frame before (no jump).
            self.assertLessEqual(after / before, 1.15)

    def test_last_frame_holds_whole_earth(self):
        last = poses()[-1]
        center = (0.0, 0.0, -(TS.EARTH_RADIUS_M + 509452.0))
        to_center = tuple(c - p for c, p in zip(center,
                                                last["location"]))
        # Looking at Earth's center, whole disc inside the frame
        # height with a margin of black space around it.
        self.assertLess(angle_deg(last["view_dir"], to_center), 0.5)
        self.assertGreater(last["disc_fraction"], 0.75)
        self.assertLess(last["disc_fraction"], 0.92)
        # The Sun is well outside the picture (no glare across the
        # disc), yet the phase still shows a terminator.
        self.assertGreater(last["sun_view_angle_deg"], 60.0)
        self.assertGreater(last["phase_deg"], 25.0)
        self.assertLess(last["phase_deg"], 80.0)
        # Tens of thousands of kilometers out, far side unclipped.
        self.assertGreater(last["center_distance_m"], 2.0e7)
        self.assertGreater(last["clip_end_m"],
                           last["center_distance_m"] + TS.EARTH_RADIUS_M)
        self.assertLess(last["clip_start_m"],
                        last["center_distance_m"] - TS.EARTH_RADIUS_M)

    def test_limb_stays_in_frame_through_frame_160(self):
        # From each pose alone: Earth's angular radius as seen from
        # the camera, the view axis's offset from Earth's center,
        # and where the disc's top edge (the limb) falls in the
        # frame, in half-frame units (+1 is the top edge).
        _start, _sun, center = clean_start_and_sun()
        for index, pose in enumerate(poses()[:160], start=1):
            loc = pose["location"]
            to_center = tuple(c - p for c, p in zip(center, loc))
            dc = math.sqrt(sum(v * v for v in to_center))
            alpha = math.degrees(math.asin(TS.EARTH_RADIUS_M / dc))
            beta = math.degrees(math.atan(
                (36.0 / (16.0 / 9.0) / 2.0) / pose["lens_mm"]))
            delta = angle_deg(pose["view_dir"], to_center)
            limb = (alpha - delta) / beta
            self.assertGreater(limb, -0.95,
                               "frame %d limb below frame" % index)
            self.assertLess(limb, 0.95,
                            "frame %d limb above frame (offset %.2f)"
                            % (index, limb))
            # And the view axis still hits the disc, so Earth fills
            # the lower frame under that horizon.
            self.assertLess(delta, alpha,
                            "frame %d misses Earth" % index)

    def test_first_frame_and_existing_cuts_unchanged(self):
        start, sun, center = clean_start_and_sun()
        first = TS.pullback_camera(0.0, start, center, sun)
        for got, want in zip(first["location"], start):
            self.assertAlmostEqual(got, want, places=9)
        self.assertEqual(first["lens_mm"], 85.0)
        self.assertEqual(first["target"], (0.0, 0.0, 0.0))
        # The pullback is opt-in: clean and instrument commands are
        # exactly what they were before A9.
        base = ["--timeline", "some/run.js", "--output", "some/out",
                "--dry-run"]
        for cut in ("clean", "instrument"):
            joined = " ".join(R.build_command(
                R.parse_args(base + ["--cut", cut])))
            self.assertIn("--cut %s" % cut, joined)
            self.assertNotIn("pullback", joined)
        build_a5 = (ROOT / "build_a5.py").read_text(encoding="utf-8")
        self.assertIn("pullback=None", build_a5)
        self.assertIn('clean = cut in ("clean", "pullback")', build_a5)


class TestPullbackWiring(unittest.TestCase):
    def test_modal_pullback_command_and_spec(self):
        spec = M.resolve_render(
            run_id=SCORED_RUN, cut="pullback", width=1920, height=1080,
            met_start="1150", met_end="1158", met_step="1/30",
            clip="PH2-PASS3-SPARK-R2_pullback.mp4")
        self.assertEqual(spec["frame_count"], 241)
        self.assertEqual(spec["timing_name"],
                         "PH2-PASS3-SPARK-R2_pullback_probe_timing.json")
        joined = " ".join(M.build_render_command(
            spec["met_start"], spec["met_end"], spec["clip"],
            run_id=spec["run_id"], cut=spec["cut"],
            width=spec["width"], height=spec["height"],
            met_step=spec["met_step"]))
        for needle in ("--clip PH2-PASS3-SPARK-R2_pullback.mp4",
                       "--width 1920", "--height 1080",
                       "--met-start 1150", "--met-end 1158",
                       "--met-step 1/30", "--cut pullback",
                       "--samples 48", "--fps 30",
                       "--require-gpu", "--perceptually-lossless"):
            self.assertIn(needle, joined)
        mets = Y.frame_mets(1150, 1158, Fraction(1, 30))
        self.assertEqual(len(mets), 241)

    def test_pullback_caption(self):
        captions = (ROOT / "CAPTIONS.md").read_text(encoding="utf-8")
        self.assertIn("## A9 pull-back clip", captions)
        self.assertIn("PH2-PASS3-SPARK-R2_pullback.mp4", captions)
        self.assertIn("true size", captions)
        self.assertIn("too small to see", captions)
        self.assertIn("no marker", captions)


class TestProbeDoesNotCompressMove(unittest.TestCase):
    def test_probe_progress_is_first_frames_of_full_move(self):
        # The modal probe renders a span's first three frames. Their
        # pull-back progress must be 0, 1/240, 2/240 of the full
        # clip's span - not 0, 1/2, 1 of the probe's own three
        # frames, which squeezed the whole move between neighbors
        # and let motion blur smear the bright Earth over frame 1
        # (A9B: probe report distances 3.1 m, 8.6 km, 23,953 km).
        got = [Y.pullback_progress(Fraction(1150) + i * Fraction(1, 30),
                                   1150, 1158) for i in range(3)]
        self.assertEqual(got, [0.0, 1.0 / 240.0, 2.0 / 240.0])
        self.assertEqual(Y.pullback_progress(1158, 1150, 1158), 1.0)
        # The span is plumbed end to end, and only when asked.
        args = R.parse_args([
            "--timeline", "some/run.js", "--output", "some/out",
            "--pullback-met-start", "1150", "--pullback-met-end", "1158",
            "--dry-run"])
        joined = " ".join(R.build_command(args))
        self.assertIn("--pullback-met-start 1150", joined)
        self.assertIn("--pullback-met-end 1158", joined)
        plain = " ".join(R.build_command(R.parse_args([
            "--timeline", "some/run.js", "--output", "some/out",
            "--dry-run"])))
        self.assertNotIn("--pullback-met", plain)
        modal_src = (ROOT / "render_modal.py").read_text(encoding="utf-8")
        self.assertIn('remote_args["pullback_met_start"]', modal_src)

    def test_pullback_renders_without_motion_blur(self):
        build_a5 = (ROOT / "build_a5.py").read_text(encoding="utf-8")
        # Only the pull-back turns the shutter off: its log-paced
        # dolly is the one move fast enough for Blender's motion blur
        # to streak sunlit Earth into the black sky.
        self.assertIn('H["scene"].render.use_motion_blur = False',
                      build_a5)
        # Every other cut keeps the shared setup's motion blur.
        self.assertIn("scene.render.use_motion_blur = True", build_a5)


if __name__ == "__main__":
    unittest.main()
