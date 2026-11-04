# SPDX-License-Identifier: GPL-3.0-or-later
"""A7 tests: the Modal renderer for the final clean cut.

Everything here is plain stdlib logic, checked locally with no Modal,
no GPU, no Blender render and no network (as with the music folder's
Modal script, the cloud half stays untested until the Director runs
it). Every test has a red case in tests/show_red.py.
"""

import ast
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import render_clip as R  # noqa: E402
import render_modal as M  # noqa: E402

# The SHA-256 Blender publishes for the Linux x64 tarball, in
# blender-5.2.3.sha256 beside the tarball on download.blender.org.
PUBLISHED_BLENDER_SHA256 = \
    "78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec"


def load_pure_function(source_path, name):
    """Exec one bpy-free function out of a Blender script source."""
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            namespace = {}
            exec(compile(ast.Module([node], []), str(source_path), "exec"),
                 namespace)
            return namespace[name]
    raise AssertionError("function %s not found in %s" % (name, source_path))


class TestBlenderPins(unittest.TestCase):
    def test_blender_version_and_hash_pins(self):
        self.assertEqual(M.BLENDER_VERSION, "5.2.3")
        self.assertEqual(M.BLENDER_ARCHIVE, "blender-5.2.3-linux-x64.tar.xz")
        self.assertEqual(M.BLENDER_SHA256, PUBLISHED_BLENDER_SHA256)
        self.assertEqual(
            M.BLENDER_URL,
            "https://download.blender.org/release/Blender5.2/"
            "blender-5.2.3-linux-x64.tar.xz")
        commands = " ".join(M.blender_download_commands())
        # The image build downloads that exact tarball and refuses it
        # unless its hash matches, before anything is extracted.
        self.assertIn(M.BLENDER_URL, commands)
        self.assertIn(PUBLISHED_BLENDER_SHA256, commands)
        self.assertIn("sha256sum -c", commands)
        self.assertLess(commands.index("sha256sum -c"),
                        commands.index("tar "))
        # Every image version is pinned, and the GPU and rate are named.
        self.assertEqual(M.PYTHON_VERSION, "3.11")
        self.assertEqual(M.GPU_TYPE, "L40S")
        self.assertEqual(M.L40S_USD_PER_HOUR, 1.95)
        self.assertGreater(M.TIMEOUT_SECONDS, 0)
        for package in M.IMAGE_APT_PACKAGES:
            self.assertNotIn(" ", package)


class TestRenderCommand(unittest.TestCase):
    def test_exact_render_command(self):
        self.assertEqual(M.build_render_command(800, 1225, M.FINAL_CLIP), [
            "python3", "/opt/huginn-render/render_clip.py",
            "--timeline",
            "/opt/huginn-render/inputs/timelines/dev-ph2-p3-open-01.js",
            "--inputs", "/opt/huginn-render/inputs",
            "--output", "/tmp/huginn-final-out",
            "--clip", "dev-ph2-p3-open-01_final_clean.mp4",
            "--width", "1920", "--height", "1080",
            "--met-start", "800", "--met-end", "1225",
            "--met-step", "1", "--fps", "30",
            "--engine", "CYCLES", "--samples", "48",
            "--cut", "clean",
            "--blender", "/opt/blender/blender",
            "--require-gpu", "--perceptually-lossless"])

    def test_new_switch_defaults_leave_preview_command_unchanged(self):
        base = ["--timeline", "some/run.js", "--output", "some/out",
                "--dry-run"]
        plain = R.build_command(R.parse_args(base))
        self.assertNotIn("--require-gpu", plain)
        self.assertNotIn("--perceptually-lossless", plain)
        flagged = R.build_command(R.parse_args(
            base + ["--require-gpu", "--perceptually-lossless"]))
        self.assertEqual(flagged[:len(plain)], plain)
        self.assertEqual(flagged[len(plain):],
                         ["--require-gpu", "--perceptually-lossless"])


class TestManifestCheck(unittest.TestCase):
    def _fake_inputs(self, tmp):
        inputs = Path(tmp) / "inputs"
        inputs.mkdir()
        (inputs / "a.txt").write_bytes(b"alpha\n")
        digest = hashlib.sha256(b"alpha\n").hexdigest()
        (inputs / "MANIFEST.sha256").write_text(
            "%s  a.txt\n" % digest, encoding="utf-8")
        return inputs

    def test_manifest_check_refuses_changed_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self._fake_inputs(tmp)
            self.assertEqual(M.verify_inputs_manifest(inputs), 1)
            (inputs / "a.txt").write_bytes(b"tampered\n")
            with self.assertRaises(ValueError):
                M.verify_inputs_manifest(inputs)

    def test_manifest_check_refuses_missing_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = self._fake_inputs(tmp)
            (inputs / "a.txt").unlink()
            with self.assertRaises(ValueError):
                M.verify_inputs_manifest(inputs)


class TestGpuSwitch(unittest.TestCase):
    def test_gpu_switch_refuses_cpu_only(self):
        error_for = load_pure_function(ROOT / "build_a5.py",
                                       "gpu_requirement_error")
        # CPU only + the switch on: an error, so the render stops.
        error = error_for("CPU", True)
        self.assertIsNotNone(error)
        self.assertIn("no GPU", error)
        # CPU only + the switch off (the default): today's behavior.
        self.assertIsNone(error_for("CPU", False))
        # A real GPU device passes either way.
        self.assertIsNone(error_for("OPTIX: NVIDIA L40S", True))
        build_a5 = (ROOT / "build_a5.py").read_text(encoding="utf-8")
        self.assertIn('"--require-gpu" in ARGS', build_a5)
        self.assertIn('"--perceptually-lossless" in ARGS', build_a5)
        self.assertIn('"PERC_LOSSLESS"', build_a5)
        self.assertIn('"H264"', build_a5)


class TestProbeAndCost(unittest.TestCase):
    def test_probe_frame_range(self):
        self.assertEqual((M.MET_START, M.PROBE_MET_END), (800, 802))
        self.assertEqual(M.frame_count(M.MET_START, M.PROBE_MET_END,
                                       M.MET_STEP), 3)
        self.assertEqual(M.frame_count(M.MET_START, M.MET_END,
                                       M.MET_STEP), 426)
        self.assertEqual(M.FULL_FRAME_COUNT, 426)
        probe = M.build_render_command(M.MET_START, M.PROBE_MET_END,
                                       M.PROBE_CLIP)
        self.assertEqual(probe[probe.index("--met-end") + 1], "802")
        self.assertEqual(probe[probe.index("--clip") + 1], M.PROBE_CLIP)

    def test_cost_cap(self):
        # 10 s a frame: 426 frames at $1.95 an hour.
        self.assertAlmostEqual(M.projected_cost_usd(10.0),
                               10.0 * 426 / 3600.0 * 1.95)
        self.assertEqual(M.DEFAULT_COST_CAP_USD, 15.0)
        M.check_cost_cap(15.0, 15.0)  # at the cap is not over it
        with self.assertRaises(ValueError):
            M.check_cost_cap(15.01, 15.0)
        with self.assertRaises(ValueError):
            M.check_cost_cap(M.projected_cost_usd(200.0),
                             M.DEFAULT_COST_CAP_USD)


class TestNoOverwrite(unittest.TestCase):
    def test_save_outputs_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "final"
            written = M.save_outputs({"clip.mp4": b"one",
                                      "clip.sync.json": b"{}"}, out)
            self.assertEqual(len(written), 2)
            with self.assertRaises(FileExistsError):
                M.save_outputs({"clip.mp4": b"two"}, out)
            self.assertEqual((out / "clip.mp4").read_bytes(), b"one")

    def test_save_outputs_writes_nothing_when_one_target_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "final"
            M.save_outputs({"b.mp4": b"old"}, out)
            with self.assertRaises(FileExistsError):
                M.save_outputs({"a.mp4": b"new", "b.mp4": b"new"}, out)
            self.assertFalse((out / "a.mp4").exists())
            self.assertEqual((out / "b.mp4").read_bytes(), b"old")


# Captured from out/a6anim_clean_log.txt (Blender 5.2.3, this scene),
# trimmed to the lines around the first three frames. Blender stamps
# each appended frame with its cumulative clock, so a frame's own
# render time is the gap since the previous append: 12.719 and 13.953.
CAPTURED_BLENDER_OUTPUT = [
    "A5 ANIM device: OPTIX: NVIDIA GeForce RTX 5050 Laptop GPU",
    "00:03.875  cycles           | WARNING Could not create directory",
    "00:15.938  render           | Video append frame 1",
    "00:16.047  cycles           | WARNING Could not create directory",
    "00:28.657  render           | Video append frame 2",
    "00:42.610  render           | Video append frame 3",
    "A5 ANIM OK dev-ph2-p3-open-01_a5_clean.mp4 3 frames",
]

# The classic Blender frame line, in case a build prints those instead.
CLASSIC_BLENDER_OUTPUT = [
    "Fra:1 Mem:100.00M | Time:00:04.00 | Rendering 1 / 48 samples",
    "Fra:1 Mem:100.00M | Time:00:10.00 | Compositing",
    "Fra:2 Mem:100.00M | Time:00:12.50 | Compositing",
    "Fra:3 Mem:100.00M | Time:00:11.00 | Compositing",
]


class TestProbeProjection(unittest.TestCase):
    def test_parse_frame_times_from_captured_output(self):
        times = M.parse_frame_times(CAPTURED_BLENDER_OUTPUT)
        self.assertEqual(len(times), 2)
        self.assertAlmostEqual(times[0], 28.657 - 15.938)
        self.assertAlmostEqual(times[1], 42.610 - 28.657)
        # Classic lines give each frame's final Time directly.
        classic = M.parse_frame_times(CLASSIC_BLENDER_OUTPUT)
        self.assertEqual(classic, [10.0, 12.5, 11.0])

    def test_probe_projection_from_frame_times(self):
        # Known inputs: a 180 s probe whose three frames render in
        # about 13.3 s each (from the captured output above), so most
        # of the probe time is start-up and scene build, counted once.
        times = M.parse_frame_times(CAPTURED_BLENDER_OUTPUT)
        proj = M.probe_projection(180.0, times, 3)
        mean = (12.719 + 13.953) / 2.0
        startup = 180.0 - mean * 3
        self.assertEqual(proj["timing_method"], "frame_times")
        self.assertAlmostEqual(proj["mean_frame_seconds"], mean)
        self.assertAlmostEqual(proj["startup_seconds"], startup)
        self.assertAlmostEqual(proj["projected_seconds"],
                               startup + mean * 426)
        self.assertAlmostEqual(proj["projected_cost_usd"],
                               (startup + mean * 426) / 3600.0 * 1.95)
        # The old whole-time rate (180 / 3 a frame) would project far
        # past this, and past the cap; the frame-times projection does
        # not. This is what the red case plants back in.
        old_cost = 180.0 / 3 * 426 / 3600.0 * 1.95
        self.assertLess(proj["projected_cost_usd"], old_cost / 4.0)
        M.check_cost_cap(proj["projected_cost_usd"],
                         M.DEFAULT_COST_CAP_USD)

    def test_probe_projection_falls_back_without_frame_times(self):
        self.assertEqual(M.parse_frame_times(["no render lines"]), [])
        proj = M.probe_projection(180.0, [], 3)
        self.assertEqual(proj["timing_method"], "whole_time_fallback")
        self.assertAlmostEqual(proj["projected_seconds"], 180.0 / 3 * 426)


if __name__ == "__main__":
    unittest.main()
