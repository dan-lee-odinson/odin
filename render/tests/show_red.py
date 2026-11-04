# SPDX-License-Identifier: GPL-3.0-or-later
"""Red cases for every A1 test (the brief, rule 8).

Each case plants one change - in a temporary copy of an input, a generated
file, or (restored byte for byte) in the source - then runs that one test
alone. A case counts only if the test ran and failed with an assertion
failure: a test that did not run, passed, or stopped on an error does not
count. After all cases, the full suite runs clean and must pass.

Use:  python tests/show_red.py [case_name ...]   (default: all cases)
"""

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import scene_spec as S  # noqa: E402


def run_one_test(test_name, env_extra=None, pattern="test_a1.py"):
    """Run one test by name; return (ran_one, failed, errored, output)."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests",
         "-p", pattern, "-k", test_name, "-v"],
        cwd=str(ROOT), env=env, capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    ran_one = "Ran 1 test" in out
    failed = ("FAIL:" in out) and proc.returncode != 0
    errored = "ERROR:" in out
    return ran_one, failed, errored, out


def plant_in_file(path, old, new):
    """Replace text in a file; return the original bytes for restore."""
    original = Path(path).read_bytes()
    text = original.decode("utf-8")
    assert text.count(old) == 1, "plant target not unique in %s: %r" % (path, old)
    Path(path).write_text(text.replace(old, new), encoding="utf-8")
    return original


def restore(path, original):
    Path(path).write_bytes(original)
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    assert digest == hashlib.sha256(original).hexdigest(), "restore failed: %s" % path


def source_case(name, test_name, path, old, new, pattern="test_a1.py"):
    """Plant a change in the real source, run the test, restore byte for byte."""
    def run():
        original = plant_in_file(path, old, new)
        try:
            return run_one_test(test_name, pattern=pattern)
        finally:
            restore(path, original)
    return name, run


def manifest_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "inputs"
            shutil.copytree(ROOT / "inputs", copied)
            target = copied / "spacecraft.md"
            target.write_bytes(target.read_bytes() + b"\n")
            return run_one_test("test_manifest_hashes_match",
                                {"ANIM_INPUTS": str(copied)})
    return "manifest_hash_mismatch", run


def report_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            report = json.loads(S.REPORT_JSON.read_text(encoding="utf-8"))
            report["objects"].remove("Sun")
            planted = Path(tmp) / "scene_report.json"
            planted.write_text(json.dumps(report), encoding="utf-8")
            return run_one_test("test_scene_report",
                                {"ANIM_REPORT": str(planted)})
    return "report_missing_sun", run


def still_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            for name in S.STILL_NAMES:
                shutil.copy2(S.OUT_DIR / name, staged / name)
            # A PNG header claiming 8 x 8, padded past the minimum size.
            header = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                      + struct.pack(">II", 8, 8) + b"\x00" * 21000)
            (staged / S.STILL_NAMES[0]).write_bytes(header)
            return run_one_test("test_still_files",
                                {"ANIM_STILLS": str(staged)})
    return "still_wrong_size", run


def clean_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            banned = "C:" + "\\" + "Users" + "\\" + "someone"
            (staged / "planted.py").write_text(
                'PATH = "' + banned + '"\n', encoding="utf-8")
            return run_one_test("test_no_absolute_paths_in_sources",
                                {"ANIM_SOURCES": str(staged)})
    return "absolute_user_path_planted", run


CASES = [
    manifest_case(),
    source_case("latlon_longitude_sign_flipped", "test_latlon_known_points",
                ROOT / "scene_spec.py",
                "radius * cos_lat * math.sin(lon)",
                "radius * cos_lat * math.sin(-lon)"),
    source_case("station_longitude_sign_flipped", "test_station_on_earth_surface",
                ROOT / "scene_spec.py",
                "radius * cos_lat * math.sin(lon)",
                "radius * cos_lat * math.sin(-lon)"),
    source_case("orbit_interpolates_from_next_row", "test_orbit_known_moments",
                ROOT / "scene_spec.py",
                "out[key] = before[key] + frac * (after[key] - before[key])",
                "out[key] = after[key] + frac * (after[key] - before[key])"),
    source_case("cubesat_bus_too_wide", "test_cubesat_proportions",
                ROOT / "scene_spec.py",
                "BUS_DIMS_M = (0.226, 0.100, 0.366)",
                "BUS_DIMS_M = (0.326, 0.100, 0.366)"),
    report_case(),
    still_case(),
    clean_case(),
    source_case("build_reaches_network", "test_build_is_read_only",
                ROOT / "build_a1.py",
                "import bpy",
                "import bpy\nimport urllib.request  # planted red case"),
]


def a2_report_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            source = ROOT / "out" / "a2" / "a2_report.json"
            report = json.loads(source.read_text(encoding="utf-8"))
            report["frames"] = report["frames"][:-1]
            planted = Path(tmp) / "a2_report.json"
            planted.write_text(json.dumps(report), encoding="utf-8")
            return run_one_test("test_a2_preview_report",
                                {"ANIM_A2_REPORT": str(planted)},
                                pattern="test_a2.py")
    return "a2_report_frame_dropped", run


CASES += [
    source_case("a2_sample_misses_exact_met", "test_known_moments_open01",
                ROOT / "timeline.py",
                "if sample[0] <= met_s:",
                "if sample[0] < met_s:",
                pattern="test_a2.py"),
    source_case("a2_eclipse_read_backwards", "test_fixture_eclipse_and_modes",
                ROOT / "timeline.py",
                'eclipse == "SUNLIT"',
                'eclipse == "ECLIPSE"',
                pattern="test_a2.py"),
    source_case("a2_weather_from_nowhere", "test_no_feed_no_weather",
                ROOT / "timeline.py",
                "    weather = None",
                '    weather = {"proton_flux_pfu": 9.9}',
                pattern="test_a2.py"),
    source_case("a2_phase1_given_an_orbit", "test_phase1_has_no_orbit",
                ROOT / "timeline.py",
                "    return None  # no orbit on record for this run",
                "    return P3_ORBIT_CSV  # planted red case",
                pattern="test_a2.py"),
    a2_report_case(),
    source_case("a3_sun_longitude_backwards", "test_derived_sun_agrees_with_record",
                ROOT / "solar.py",
                "lon = 180.0 - 0.25 * (utc_minutes + eqtime_min)",
                "lon = 180.0 + 0.25 * (utc_minutes + eqtime_min)",
                pattern="test_a3.py"),
    source_case("a3_sync_frame_off_by_one", "test_sync_file_matches_frames",
                ROOT / "sync.py",
                'return sync["first_frame_met_s"] + (frame_index - 1) * sync["met_step_s"]',
                'return sync["first_frame_met_s"] + frame_index * sync["met_step_s"]',
                pattern="test_a3.py"),
    source_case("a4_command_drops_samples", "test_render_clip_command",
                ROOT / "render_clip.py",
                '"--engine", args.engine, "--samples", str(args.samples),',
                '"--engine", args.engine,',
                pattern="test_a4.py"),
    source_case("a4_relative_paths_unresolved", "test_render_clip_command",
                ROOT / "render_clip.py",
                "    return str(Path(value).resolve())",
                "    return str(Path(value))",
                pattern="test_a4.py"),
]


def a4_sync_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            source = ROOT / "out" / "a4"
            for name in ("a2_report.json",):
                shutil.copy2(source / name, staged / name)
            sync_path = sorted(source.glob("*.sync.json"))[-1]
            sync = json.loads(sync_path.read_text(encoding="utf-8"))
            sync["met_step_s"] = sync["met_step_s"] * 2
            (staged / sync_path.name).write_text(json.dumps(sync),
                                                 encoding="utf-8")
            report = json.loads((source / "a2_report.json").read_text())
            shutil.copy2(source / report["preview"],
                         staged / report["preview"])
            return run_one_test("test_a4_short_clip_sync",
                                {"ANIM_A4_DIR": str(staged)},
                                pattern="test_a4.py")
    return "a4_sync_step_doubled", run


def a4_eclipse_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            source = ROOT / "out" / "a2"
            # The sunlit still planted under the eclipse still's name.
            shutil.copy2(source / "fixture_890_sunlit.png",
                         staged / "fixture_890_sunlit.png")
            shutil.copy2(source / "fixture_890_sunlit.png",
                         staged / "fixture_920_eclipse_red.png")
            return run_one_test("test_eclipse_is_darker",
                                {"ANIM_FIXTURE_DIR": str(staged)},
                                pattern="test_a4.py")
    return "a4_eclipse_still_swapped", run


CASES += [a4_sync_case(), a4_eclipse_case()]


def a5_report_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            source = ROOT / "out" / "a5" / "a5_still_report.json"
            report = json.loads(source.read_text(encoding="utf-8"))
            report["met_s"] = report["met_s"] + 100
            planted = Path(tmp) / "a5_still_report.json"
            planted.write_text(json.dumps(report), encoding="utf-8")
            return run_one_test("test_a5_still_report",
                                {"ANIM_A5_REPORT": str(planted)},
                                pattern="test_a5.py")
    return "a5_report_wrong_met", run


CASES += [
    source_case("a5_zenith_pointed_down", "test_local_basis_known",
                ROOT / "truescale.py",
                'return (0.0, 0.0, -(EARTH_RADIUS_M + alt_km * 1000.0))',
                'return (0.0, 0.0, (EARTH_RADIUS_M + alt_km * 1000.0))',
                pattern="test_a5.py"),
    source_case("a5_cut_argument_dropped", "test_cut_argument",
                ROOT / "render_clip.py",
                '"--cut", args.cut]',
                '"--cut", "instrument"]',
                pattern="test_a5.py"),
    a5_report_case(),
]


def a5_fixture_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            # A strike-less clean still planted as the eclipse fixture.
            for name in ("fixture_890_sunlit.png",
                         "fixture_945_safe_deny.png"):
                shutil.copy2(ROOT / "out" / "a2" / name, staged / name)
            # Same 960x540 size, but an old strike-less A1 still: only
            # the strike count can catch it.
            shutil.copy2(ROOT / "out" / "a1" / "preview_a1_02_hero.png",
                         staged / "fixture_920_eclipse_red.png")
            return run_one_test("test_fixture_stills_new_look",
                                {"ANIM_FIXTURE_DIR": str(staged)},
                                pattern="test_a5.py")
    return "a5_fixture_still_replaced", run


CASES += [a5_fixture_case()]


def a5anim_sync_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            source = ROOT / "out" / "a5anim"
            for path in source.iterdir():
                if path.is_file():
                    shutil.copy2(path, staged / path.name)
            sync_path = staged / "dev-ph2-p3-open-01_a5_instrument.sync.json"
            sync = json.loads(sync_path.read_text(encoding="utf-8"))
            sync["met_step_s"] = sync["met_step_s"] * 2
            sync_path.write_text(json.dumps(sync), encoding="utf-8")
            return run_one_test("test_clips_syncs_and_frames",
                                {"ANIM_A5ANIM_DIR": str(staged)},
                                pattern="test_a5anim.py")
    return "a5anim_sync_step_doubled", run


CASES += [a5anim_sync_case()]


def a6_closeup_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            planted = Path(tmp) / "a6_closeup.png"
            # Same 1920 x 1080 size, but no array glint: an A1 still.
            shutil.copy2(ROOT / "out" / "a1" / "a1_01_wide.png", planted)
            return run_one_test("test_closeup_glint",
                                {"ANIM_A6_CLOSEUP": str(planted)},
                                pattern="test_a6.py")
    return "a6_closeup_without_glint", run


CASES += [a6_closeup_case()]


def a6_busface_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            # The plate still planted under the paint still's name:
            # the two lettering styles come out identical.
            shutil.copy2(ROOT / "out" / "a5" / "a6_bus_plate.png",
                         staged / "a6_bus_plate.png")
            shutil.copy2(ROOT / "out" / "a5" / "a6_bus_plate.png",
                         staged / "a6_bus_paint.png")
            return run_one_test("test_busface_two_styles",
                                {"ANIM_A6_BUS_DIR": str(staged)},
                                pattern="test_a6.py")
    return "a6_busface_styles_identical", run


CASES += [a6_busface_case()]


def a6anim_sync_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp)
            source = ROOT / "out" / "a6anim"
            for path in source.iterdir():
                if path.is_file():
                    shutil.copy2(path, staged / path.name)
            sync_path = staged / "dev-ph2-p3-open-01_a5_clean.sync.json"
            sync = json.loads(sync_path.read_text(encoding="utf-8"))
            sync["first_frame_met_s"] = sync["first_frame_met_s"] + 5
            sync_path.write_text(json.dumps(sync), encoding="utf-8")
            return run_one_test("test_clips_syncs_and_frames",
                                {"ANIM_A6ANIM_DIR": str(staged)},
                                pattern="test_a6anim.py")
    return "a6anim_sync_first_met_shifted", run


CASES += [a6anim_sync_case()]

CASES += [
    source_case("a7_blender_hash_pin_changed",
                "test_blender_version_and_hash_pins",
                ROOT / "render_modal.py",
                '"78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec"',
                '"88486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec"',
                pattern="test_a7.py"),
    source_case("a7_render_command_wrong_met_step",
                "test_exact_render_command",
                ROOT / "render_modal.py",
                '"--met-step", exact_text(met_step)',
                '"--met-step", "5"',
                pattern="test_a7.py"),
    source_case("a7_gpu_switch_on_by_default",
                "test_new_switch_defaults_leave_preview_command_unchanged",
                ROOT / "render_clip.py",
                "    if args.require_gpu:",
                "    if True:  # planted red case",
                pattern="test_a7.py"),
    source_case("a7_manifest_mismatch_accepted",
                "test_manifest_check_refuses_changed_input",
                ROOT / "render_modal.py",
                'raise ValueError("input hash mismatch: %s" % rel)',
                "pass  # planted red case",
                pattern="test_a7.py"),
    source_case("a7_manifest_missing_accepted",
                "test_manifest_check_refuses_missing_input",
                ROOT / "render_modal.py",
                'raise ValueError("manifest file missing: %s" % rel)',
                "return seen  # planted red case",
                pattern="test_a7.py"),
    source_case("a7_gpu_switch_lets_cpu_through",
                "test_gpu_switch_refuses_cpu_only",
                ROOT / "build_a5.py",
                '    if require_gpu and device == "CPU":',
                "    if False:  # planted red case",
                pattern="test_a7.py"),
    source_case("a7_probe_renders_too_far",
                "test_probe_frame_range",
                ROOT / "render_modal.py",
                "PROBE_MET_END = 802",
                "PROBE_MET_END = 805",
                pattern="test_a7.py"),
    source_case("a7_cost_cap_not_enforced",
                "test_cost_cap",
                ROOT / "render_modal.py",
                "    if projected_usd > cap_usd:",
                "    if projected_usd > cap_usd * 1000:  # planted red case",
                pattern="test_a7.py"),
    source_case("a7_save_outputs_overwrites",
                "test_save_outputs_never_overwrites",
                ROOT / "render_modal.py",
                "        if path.exists():",
                "        if False:  # planted red case",
                pattern="test_a7.py"),
    source_case("a7_save_outputs_partial_write",
                "test_save_outputs_writes_nothing_when_one_target_exists",
                ROOT / "render_modal.py",
                "        if path.exists():",
                "        if False:  # planted red case",
                pattern="test_a7.py"),
    source_case("a7b_frame_times_read_as_cumulative",
                "test_parse_frame_times_from_captured_output",
                ROOT / "render_modal.py",
                "            frame_times.append(stamp - previous_stamp)",
                "            frame_times.append(stamp)  # planted red case",
                pattern="test_a7.py"),
    source_case("a7b_projection_back_to_whole_time_rate",
                "test_probe_projection_from_frame_times",
                ROOT / "render_modal.py",
                "        mean_frame = sum(frame_times) / len(frame_times)",
                "        mean_frame = elapsed_seconds / probe_frames"
                "  # planted red case: the old whole-time rate",
                pattern="test_a7.py"),
    source_case("a7b_fallback_not_named",
                "test_probe_projection_falls_back_without_frame_times",
                ROOT / "render_modal.py",
                '"timing_method": "whole_time_fallback"',
                '"timing_method": "frame_times"',
                pattern="test_a7.py"),
]


def a8_scored_input_case():
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "inputs"
            shutil.copytree(ROOT / "inputs", copied)
            target = copied / "timelines" / "PH2-PASS3-SPARK-R2.js"
            target.write_bytes(target.read_bytes() + b"\n")
            return run_one_test("test_scored_timeline_input",
                                {"ANIM_A8_INPUTS": str(copied)},
                                pattern="test_a8.py")
    return "a8_scored_timeline_byte_added", run


CASES += [
    a8_scored_input_case(),
    source_case("a8_pass3_orbit_withheld", "test_scored_run_orbit",
                ROOT / "timeline.py",
                'if run_id.startswith(("dev-ph2-p3-", "PH2-PASS3-")):',
                'if run_id.startswith(("dev-ph2-p3-", "PH2-PASS9-")):',
                pattern="test_a8.py"),
    source_case("a8_fractional_last_frame_dropped",
                "test_fractional_step_exact",
                ROOT / "sync.py",
                "    count = int((end - start) // step) + 1",
                "    count = int((end - start) // step)  # planted red case",
                pattern="test_a8.py"),
    source_case("a8_whole_step_becomes_float", "test_whole_step_unchanged",
                ROOT / "sync.py",
                "    return frac.numerator if frac.denominator == 1"
                " else float(frac)",
                "    return float(frac)  # planted red case",
                pattern="test_a8.py"),
    source_case("a8_render_clip_step_truncated",
                "test_render_clip_fractional_command",
                ROOT / "render_clip.py",
                '"--step", Y.step_text(args.met_step),',
                '"--step", str(int(args.met_step) or 1),'
                "  # planted red case",
                pattern="test_a8.py"),
    source_case("a8_modal_final_timing_renamed",
                "test_modal_defaults_unchanged",
                ROOT / "render_modal.py",
                "PROBE_TIMING_NAME if clip == FINAL_CLIP",
                'PROBE_TIMING_NAME if clip == "never.mp4"',
                pattern="test_a8.py"),
    source_case("a8_modal_cut_forced_clean", "test_modal_two_clips_commands",
                ROOT / "render_modal.py",
                '"--cut", cut,',
                '"--cut", "clean",  # planted red case',
                pattern="test_a8.py"),
    source_case("a8_all_renders_share_one_timing",
                "test_each_render_keeps_its_own_probe_timing",
                ROOT / "render_modal.py",
                'else stem + "_probe_timing.json"',
                "else PROBE_TIMING_NAME",
                pattern="test_a8.py"),
    source_case("a8b_cue_flash_back_to_two_frames",
                "test_cue_flash_fractional_step",
                ROOT / "build_a2.py",
                "    return max(2, needed)",
                "    return 2  # planted red case",
                pattern="test_a8.py"),
    source_case("a8b_cue_flash_three_frame_floor",
                "test_cue_flash_whole_steps_unchanged",
                ROOT / "build_a2.py",
                "    return max(2, needed)",
                "    return max(3, needed)  # planted red case",
                pattern="test_a8.py"),
    source_case("a9_pullback_distance_linear_jumps",
                "test_camera_distance_grows_without_a_jump",
                ROOT / "truescale.py",
                "    distance = math.exp(math.log(r0)"
                " + (math.log(r1) - math.log(r0))\n"
                "                        * eased)",
                "    distance = r0 + (r1 - r0) * eased  # planted red case",
                pattern="test_a9.py"),
    source_case("a9_pullback_disc_overflows_frame",
                "test_last_frame_holds_whole_earth",
                ROOT / "truescale.py",
                "PULLBACK_DISC_FRACTION = 0.84",
                "PULLBACK_DISC_FRACTION = 1.2  # planted red case",
                pattern="test_a9.py"),
    source_case("a9_pullback_first_frame_lens_changed",
                "test_first_frame_and_existing_cuts_unchanged",
                ROOT / "truescale.py",
                '"lens_mm": 85.0 if u <= 0.0 else lens,',
                '"lens_mm": 50.0 if u <= 0.0 else lens,',
                pattern="test_a9.py"),
    source_case("a9_modal_cut_forced_clean",
                "test_modal_pullback_command_and_spec",
                ROOT / "render_modal.py",
                '"--cut", cut,',
                '"--cut", "clean",  # planted red case',
                pattern="test_a9.py"),
    source_case("a9_pullback_caption_section_renamed",
                "test_pullback_caption",
                ROOT / "CAPTIONS.md",
                "## A9 pull-back clip",
                "## A9 clip",
                pattern="test_a9.py"),
    source_case("a9b_probe_progress_spread_over_its_own_frames",
                "test_probe_progress_is_first_frames_of_full_move",
                ROOT / "sync.py",
                "    return float(min(Fraction(1),"
                " max(Fraction(0), progress)))",
                "    return float(min(Fraction(1),"
                " max(Fraction(0), progress * 120)))"
                "  # planted red case",
                pattern="test_a9.py"),
    source_case("a9b_pullback_motion_blur_back_on",
                "test_pullback_renders_without_motion_blur",
                ROOT / "build_a5.py",
                'H["scene"].render.use_motion_blur = False',
                'H["scene"].render.use_motion_blur = True'
                "  # planted red case",
                pattern="test_a9.py"),
    source_case("a9c_limb_hold_removed",
                "test_limb_stays_in_frame_through_frame_160",
                ROOT / "truescale.py",
                "    delta = max(0.0, alpha_now - 0.35 * beta_now)"
                " * (1.0 - centering)",
                "    delta = 0.0  # planted red case",
                pattern="test_a9.py"),
]


def main(argv):
    wanted = argv[1:]
    cases = [c for c in CASES if not wanted or c[0] in wanted]
    if not cases:
        print("no such case; known: %s" % ", ".join(c[0] for c in CASES))
        return 2
    bad = 0
    for name, run in cases:
        ran_one, failed, errored, out = run()
        ok = ran_one and failed and not errored
        print("%s  %s (ran_one=%s failed=%s errored=%s)"
              % ("RED OK " if ok else "NOT RED", name, ran_one, failed, errored))
        if not ok:
            bad += 1
            print(out)
    if bad:
        print("%d red case(s) did not count" % bad)
        return 1
    print("all %d red case(s) ran and failed as required" % len(cases))
    if not wanted:
        print("--- full suite, clean ---")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=str(ROOT))
        return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
