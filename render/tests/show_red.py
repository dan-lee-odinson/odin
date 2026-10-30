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
                '"--engine", args.engine, "--samples", str(args.samples)]',
                '"--engine", args.engine]',
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
