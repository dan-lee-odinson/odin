# SPDX-License-Identifier: GPL-3.0-or-later
"""A7: the final clean cut on Modal (the Director runs this; see README).

Commands (from this folder, in a fresh PowerShell tab):
    modal run render_modal.py --probe
    modal run render_modal.py

The final is A6 exactly as it stands - same run and span
(dev-ph2-p3-open-01, MET 800 to 1225), same look, lettering and Cycles
samples - at 1920 x 1080, 30 fps, a 1-second MET step (426 frames,
14.2 seconds), H.264 at Blender's perceptually lossless setting. It
runs render_clip.py in the container exactly as on the laptop; only
the size, step, rate, clip name, output folder and the two new
switches (--require-gpu, --perceptually-lossless) differ.

--probe renders the first three frames (MET 800 to 802) at full size,
prints the seconds per frame and the projected cost of all 426 frames,
and saves that timing in out/final. The full render reads the probe
timing and refuses to start when the projection is over the cost cap
($15 by default; --cost-cap changes it). Results come back to
out/final and never overwrite a file there.

Modal reads MODAL_TOKEN_ID / MODAL_TOKEN_SECRET from the environment;
no credential is stored in any file here. The top half of this file is
plain stdlib logic so it can be unit-tested locally with no Modal, no
GPU and no network; the cloud half stays untested until the Director
runs it, as with the music folder's Modal script.
"""

import hashlib
import json
import re
import sys
import time
from fractions import Fraction
from pathlib import Path

# ---------------------------------------------------------------------------
# Pins. The Modal image is built in the cloud from exactly these versions.
# ---------------------------------------------------------------------------
BLENDER_VERSION = "5.2.3"  # Blender 5.2.3 LTS, the laptop's release
BLENDER_ARCHIVE = "blender-%s-linux-x64.tar.xz" % BLENDER_VERSION
BLENDER_URL = ("https://download.blender.org/release/Blender5.2/"
               + BLENDER_ARCHIVE)
# The SHA-256 Blender publishes for that tarball, in blender-5.2.3.sha256
# in the same release folder (checked 2 November 2026).
BLENDER_SHA256 = \
    "78486c018b4443efe5e75ab54c290ed8c15abafd249b862c2c9ce2530a918eec"
PYTHON_VERSION = "3.11"  # the container's Python; Blender ships its own

# System libraries headless Blender needs, plus the download tools.
IMAGE_APT_PACKAGES = (
    "ca-certificates", "curl", "xz-utils",
    "libegl1", "libgl1", "libsm6", "libx11-6", "libxext6",
    "libxfixes3", "libxi6", "libxkbcommon0", "libxrender1",
    "libxxf86vm1",
)

GPU_TYPE = "L40S"
# Modal's L40S rate as read on 1 November 2026.
L40S_USD_PER_HOUR = 1.95
DEFAULT_COST_CAP_USD = 15.0
TIMEOUT_SECONDS = 8 * 60 * 60  # backstop; the cost cap gates the start

# The final, fixed by the Director's A7 message. A6 was dev-ph2-p3-open-01,
# MET 800 to 1225, Cycles at 48 samples (out/a6anim clean report).
RUN_ID = "dev-ph2-p3-open-01"
MET_START = 800
MET_END = 1225
PROBE_MET_END = 802  # the probe is the first three frames, MET 800 to 802
MET_STEP = 1
FPS = 30
WIDTH = 1920
HEIGHT = 1080
SAMPLES = 48
FINAL_CLIP = "%s_final_clean.mp4" % RUN_ID
PROBE_CLIP = "%s_final_clean_probe.mp4" % RUN_ID
PROBE_TIMING_NAME = "final_probe_timing.json"

# Paths inside the container. The code and inputs mirror this folder's
# layout (code beside inputs/), so the scripts run there unchanged.
CONTAINER_ROOT = "/opt/huginn-render"
CONTAINER_OUTPUT = "/tmp/huginn-final-out"
BLENDER_EXE = "/opt/blender/blender"

# This folder's code, as baked into the image beside inputs/.
IMAGE_SOURCE_FILES = (
    "build_a1.py", "build_a2.py", "build_a5.py", "render_clip.py",
    "render_modal.py", "scene_spec.py", "solar.py", "sync.py",
    "timeline.py", "truescale.py",
)

ROOT = Path(__file__).resolve().parent

try:
    import modal
except Exception:  # local unit tests run without a usable Modal client
    modal = None


# ---------------------------------------------------------------------------
# Pure local logic (unit-tested, no third-party imports)
# ---------------------------------------------------------------------------
def blender_download_commands():
    """Shell commands that fetch Blender in the image and verify it.

    The tarball's SHA-256 is checked against the pin before anything
    is extracted; a mismatch stops the image build."""
    return (
        "curl -fsSL -o /tmp/%s %s" % (BLENDER_ARCHIVE, BLENDER_URL),
        "echo '%s  /tmp/%s' | sha256sum -c -"
        % (BLENDER_SHA256, BLENDER_ARCHIVE),
        "mkdir -p /opt/blender-extract && tar -xJf /tmp/%s "
        "-C /opt/blender-extract --strip-components=1" % BLENDER_ARCHIVE,
        "mv /opt/blender-extract /opt/blender && rm /tmp/%s"
        % BLENDER_ARCHIVE,
        "/opt/blender/blender --version",
    )


def exact(value):
    """An exact Fraction for an int or fraction text like "1/15".

    Modal arguments cross as text, so an exact step like a fifteenth
    of a second is never rounded to a float on the way."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        return Fraction(value.strip())
    raise ValueError("expected an int or exact fraction text, got %r"
                     % (value,))


def exact_text(value):
    """Canonical text for an exact value: "800", or "13202/15"."""
    frac = exact(value)
    if frac.denominator == 1:
        return str(frac.numerator)
    return "%d/%d" % (frac.numerator, frac.denominator)


def json_number(value):
    """A JSON number for an exact value: int when whole, else float."""
    frac = exact(value)
    return frac.numerator if frac.denominator == 1 else float(frac)


def frame_count(met_start, met_end, met_step):
    """Frames in a render: one per MET step, both ends included."""
    start, end, step = exact(met_start), exact(met_end), exact(met_step)
    if step <= 0 or end < start:
        raise ValueError("bad MET range %s to %s at step %s"
                         % (met_start, met_end, met_step))
    return int((end - start) // step) + 1


FULL_FRAME_COUNT = frame_count(MET_START, MET_END, MET_STEP)  # 426
PROBE_FRAMES = 3  # every probe renders a render's first three frames


def resolve_render(run_id=RUN_ID, cut="clean", width=WIDTH, height=HEIGHT,
                   met_start="800", met_end="1225", met_step="1",
                   clip=FINAL_CLIP):
    """One render's full specification, defaults = the A7 final.

    The probe is the render's first three frames at its own size,
    cut and step, under a _probe clip name. Each render keeps its
    own probe timing file: the A7 final keeps its historic name,
    every other clip is timed under its own stem, so two renders'
    cost caps never read each other's probe."""
    if cut not in ("clean", "instrument", "pullback"):
        raise ValueError("cut must be clean, instrument or pullback, "
                         "got %r" % cut)
    if int(width) <= 0 or int(height) <= 0:
        raise ValueError("width and height must be positive")
    if not clip.endswith(".mp4") or "/" in clip or "\\" in clip:
        raise ValueError("clip must be a plain .mp4 file name, got %r"
                         % clip)
    start, end, step = exact(met_start), exact(met_end), exact(met_step)
    frames = frame_count(start, end, step)
    probe_frames = min(PROBE_FRAMES, frames)
    stem = clip[:-len(".mp4")]
    return {
        "run_id": run_id, "cut": cut,
        "width": int(width), "height": int(height),
        "met_start": start, "met_end": end, "met_step": step,
        "clip": clip, "probe_clip": stem + "_probe.mp4",
        "probe_met_end": start + (probe_frames - 1) * step,
        "frame_count": frames, "probe_frame_count": probe_frames,
        "timing_name": PROBE_TIMING_NAME if clip == FINAL_CLIP
        else stem + "_probe_timing.json"}


def build_render_command(met_start, met_end, clip, run_id=RUN_ID,
                         cut="clean", width=WIDTH, height=HEIGHT,
                         met_step="1", pullback_met_start=None,
                         pullback_met_end=None):
    """The render_clip.py command run inside the container.

    Exactly as on the laptop. With the defaults this is the A7 final
    command, unchanged; a caller names its own run, cut, size, span,
    step and clip for any other render."""
    command = [
        "python3", "%s/render_clip.py" % CONTAINER_ROOT,
        "--timeline",
        "%s/inputs/timelines/%s.js" % (CONTAINER_ROOT, run_id),
        "--inputs", "%s/inputs" % CONTAINER_ROOT,
        "--output", CONTAINER_OUTPUT,
        "--clip", clip,
        "--width", str(int(width)), "--height", str(int(height)),
        "--met-start", exact_text(met_start),
        "--met-end", exact_text(met_end),
        "--met-step", exact_text(met_step), "--fps", str(FPS),
        "--engine", "CYCLES", "--samples", str(SAMPLES),
        "--cut", cut,
        "--blender", BLENDER_EXE,
        "--require-gpu", "--perceptually-lossless"]
    if pullback_met_start is not None:
        command += ["--pullback-met-start", exact_text(pullback_met_start)]
    if pullback_met_end is not None:
        command += ["--pullback-met-end", exact_text(pullback_met_end)]
    return command


def verify_inputs_manifest(inputs_dir):
    """Check every input against inputs/MANIFEST.sha256; return the count.

    Raises ValueError on a missing manifest, a missing file or a hash
    mismatch. Runs inside the container before any rendering, and in
    the local tests."""
    inputs = Path(inputs_dir)
    manifest = inputs / "MANIFEST.sha256"
    if not manifest.is_file():
        raise ValueError("input manifest missing: %s" % manifest)
    seen = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        expected, rel = line.split(None, 1)
        rel = rel.strip().lstrip("*")
        target = inputs / rel
        if not target.is_file():
            raise ValueError("manifest file missing: %s" % rel)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != expected.lower():
            raise ValueError("input hash mismatch: %s" % rel)
        seen += 1
    if seen == 0:
        raise ValueError("input manifest lists no files: %s" % manifest)
    return seen


def projected_cost_usd(seconds_per_frame, frames=FULL_FRAME_COUNT):
    """Projected GPU cost at the L40S rate, in US dollars."""
    if seconds_per_frame <= 0 or frames <= 0:
        raise ValueError("seconds per frame and frames must be positive")
    return seconds_per_frame * frames / 3600.0 * L40S_USD_PER_HOUR


_VIDEO_APPEND = re.compile(
    r"^(\d+):(\d{2})\.(\d{3})\s+render\s+\| Video append frame (\d+)\s*$")
_FRA = re.compile(r"Fra:(\d+)\b")
_TIME = re.compile(r"Time:(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)")


def parse_frame_times(lines):
    """Each frame's own render time in seconds, from Blender's output.

    Two forms are read. Blender 5.2 stamps every appended frame with
    its cumulative clock ("MM:SS.mmm  render | Video append frame N"),
    so a frame's own time is the gap since the previous append; that
    gives every frame after the first. A build printing the classic
    "Fra:N ... | Time:MM:SS.ss" lines gives each frame's final Time
    directly, and those win when present. Returns [] when neither
    form can be read."""
    classic = {}
    appends = []
    for raw in lines:
        for text in str(raw).split("\r"):
            text = text.strip()
            fra = _FRA.search(text)
            if fra:
                stamps = _TIME.findall(text)
                if stamps:
                    hours, minutes, seconds = stamps[-1]
                    total = (int(hours or 0) * 3600 + int(minutes) * 60
                             + float(seconds))
                    frame = int(fra.group(1))
                    classic[frame] = max(classic.get(frame, 0.0), total)
            append = _VIDEO_APPEND.match(text)
            if append:
                stamp = (int(append.group(1)) * 60
                         + int(append.group(2))
                         + int(append.group(3)) / 1000.0)
                appends.append((int(append.group(4)), stamp))
    if classic:
        return [classic[frame] for frame in sorted(classic)]
    frame_times = []
    previous_frame = previous_stamp = None
    for frame, stamp in sorted(appends):
        if previous_stamp is not None and frame == previous_frame + 1 \
                and stamp > previous_stamp:
            frame_times.append(stamp - previous_stamp)
        previous_frame, previous_stamp = frame, stamp
    return frame_times


def probe_projection(elapsed_seconds, frame_times, probe_frames,
                     full_frames=FULL_FRAME_COUNT):
    """Project the full render from a probe, start-up counted once.

    The projection is the probe's start-up (its elapsed time less its
    frame times) plus the mean frame time times the full frame count.
    Append stamps measure every probe frame after the first, so the
    first frame is taken at the mean. Without readable frame times
    this falls back to the whole probe time spread over its frames
    and says so in timing_method."""
    if elapsed_seconds <= 0 or probe_frames <= 0 or full_frames <= 0:
        raise ValueError("elapsed time and frame counts must be positive")
    if frame_times:
        mean_frame = sum(frame_times) / len(frame_times)
        startup = max(0.0, elapsed_seconds - mean_frame * probe_frames)
        projected = startup + mean_frame * full_frames
        return {"startup_seconds": startup,
                "mean_frame_seconds": mean_frame,
                "projected_seconds": projected,
                "projected_cost_usd":
                    projected / 3600.0 * L40S_USD_PER_HOUR,
                "timing_method": "frame_times"}
    mean_frame = elapsed_seconds / probe_frames
    projected = mean_frame * full_frames
    return {"startup_seconds": 0.0,
            "mean_frame_seconds": mean_frame,
            "projected_seconds": projected,
            "projected_cost_usd": projected / 3600.0 * L40S_USD_PER_HOUR,
            "timing_method": "whole_time_fallback"}


def check_cost_cap(projected_usd, cap_usd):
    """Refuse a full render whose projection is over the cap."""
    if projected_usd > cap_usd:
        raise ValueError(
            "projected cost $%.2f is over the $%.2f cap; refusing to "
            "start the full render (raise it with --cost-cap if meant)"
            % (projected_usd, cap_usd))


def result_names(clip):
    """The clip, sync and report names one render returns."""
    return (clip, clip.replace(".mp4", ".sync.json"),
            clip.replace(".mp4", "_report.json"))


def save_outputs(files, out_dir):
    """Write returned files to out_dir, never overwriting one.

    files maps file name to bytes. Every target is checked before any
    file is written, so a collision leaves the folder untouched."""
    out = Path(out_dir)
    targets = [(out / name, data) for name, data in files.items()]
    for path, _data in targets:
        if path.exists():
            raise FileExistsError(
                "refusing to overwrite %s; move it aside first" % path)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for path, data in targets:
        path.write_bytes(data)
        written.append(path)
    return written


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_probe_seconds_per_frame(out_dir, timing_name=PROBE_TIMING_NAME):
    """The probe's saved seconds per frame, or raise if no probe ran."""
    timing = Path(out_dir) / timing_name
    if not timing.is_file():
        raise FileNotFoundError(
            "no probe timing at %s; run the probe first: "
            "modal run render_modal.py --probe" % timing)
    data = json.loads(timing.read_text(encoding="utf-8"))
    seconds = float(data["seconds_per_frame"])
    if seconds <= 0:
        raise ValueError("probe timing holds no usable rate: %s" % timing)
    return seconds


def read_probe_projection_usd(out_dir, timing_name=PROBE_TIMING_NAME):
    """One render's projected cost from its own probe timing.

    Raises if that render's probe has not run. A timing file from
    before the frame-times projection holds only a whole-time rate;
    that rate still gates the full render."""
    timing = Path(out_dir) / timing_name
    if not timing.is_file():
        raise FileNotFoundError(
            "no probe timing at %s; run the probe first: "
            "modal run render_modal.py --probe" % timing)
    data = json.loads(timing.read_text(encoding="utf-8"))
    if "projected_full_cost_usd" in data:
        projected = float(data["projected_full_cost_usd"])
    else:
        projected = projected_cost_usd(
            read_probe_seconds_per_frame(out_dir, timing_name))
    if projected <= 0:
        raise ValueError("probe timing holds no usable projection: %s"
                         % timing)
    return projected


def _app_id_text():
    """Modal's app ID for this run, as the Director sees it in Modal."""
    try:
        return str(app.app_id) or "unknown"
    except Exception:
        return "unknown (see: modal app list)"


def _print_result(result, written, seconds_per_frame):
    """Print each returned file's SHA-256 and the run's key facts."""
    for path in written:
        print("sha256  %s  %s" % (sha256_of(path), path))
    print("frames: %d" % result["frame_count"])
    print("GPU: %s" % result["gpu"])
    print("seconds per frame: %.2f" % seconds_per_frame)
    print("Modal app ID: %s" % _app_id_text())


# ---------------------------------------------------------------------------
# Modal app. The image is built in the cloud; Blender and the inputs live
# there for the run. No Volume, no Secret: Modal's own keys come from the
# Director's environment, and nothing is left running after the run.
# ---------------------------------------------------------------------------
if modal is not None:
    image = (
        modal.Image.debian_slim(python_version=PYTHON_VERSION)
        .apt_install(*IMAGE_APT_PACKAGES)
        .run_commands(*blender_download_commands())
    )
    for _name in IMAGE_SOURCE_FILES:
        image = image.add_local_file(
            str(ROOT / _name), "%s/%s" % (CONTAINER_ROOT, _name),
            copy=True)
    image = image.add_local_dir(
        str(ROOT / "inputs"), "%s/inputs" % CONTAINER_ROOT, copy=True)
    app = modal.App("odin-huginn-final")
else:
    image = app = None


def _remote(fn):
    """Apply the Modal function decorator when Modal is available.

    One L40S, a timeout, and nothing else pinned: no region and no
    warm containers, so Modal runs it wherever an L40S is free and
    stops the container when the render ends."""
    if modal is None:
        return fn
    return app.function(image=image, gpu=GPU_TYPE,
                        timeout=TIMEOUT_SECONDS)(fn)


@_remote
def _render_remote(met_start, met_end, clip, run_id=RUN_ID, cut="clean",
                   width=WIDTH, height=HEIGHT, met_step="1",
                   pullback_met_start=None, pullback_met_end=None):
    """Inside the container: verify inputs, render, return the files.

    MET values cross as exact text ("13202/15"), never as floats."""
    import subprocess

    inputs = Path(CONTAINER_ROOT) / "inputs"
    checked = verify_inputs_manifest(inputs)
    print("inputs verified against MANIFEST.sha256: %d files" % checked)
    command = build_render_command(
        met_start, met_end, clip, run_id=run_id, cut=cut, width=width,
        height=height, met_step=met_step,
        pullback_met_start=pullback_met_start,
        pullback_met_end=pullback_met_end)
    print("render command:", " ".join(command))
    output = Path(CONTAINER_OUTPUT)
    output.mkdir(parents=True, exist_ok=True)
    # Stream the render's output: every line is printed as it arrives
    # (Modal shows it live, as before) and kept, so each frame's own
    # render time can be read back out of Blender's output.
    start = time.perf_counter()
    process = subprocess.Popen(
        command, cwd=CONTAINER_ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = []
    for line in process.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    returncode = process.wait()
    elapsed = time.perf_counter() - start
    if returncode != 0:
        raise RuntimeError("render failed with exit code %d; see the "
                           "Blender output above" % returncode)
    files = {}
    for name in result_names(clip):
        path = output / name
        if not path.is_file():
            raise RuntimeError("render did not produce %s" % name)
        files[name] = path.read_bytes()
    report = json.loads(files[result_names(clip)[2]].decode("utf-8"))
    frames = frame_count(met_start, met_end, met_step)
    if len(report["frames"]) != frames:
        raise RuntimeError("report holds %d frames, expected %d"
                           % (len(report["frames"]), frames))
    return {"files": files, "elapsed_seconds": elapsed,
            "frame_times": parse_frame_times(lines),
            "frame_count": frames, "gpu": report["device"]}


def _entrypoint(fn):
    if modal is None:
        return fn
    return app.local_entrypoint()(fn)


def _refuse_existing(out_dir, names):
    """Stop before spending anything if a result file already exists."""
    for name in names:
        if (Path(out_dir) / name).exists():
            raise FileExistsError(
                "refusing to overwrite %s; move it aside first"
                % (Path(out_dir) / name))


@_entrypoint
def main(probe: bool = False, cost_cap: float = DEFAULT_COST_CAP_USD,
         run_id: str = RUN_ID, cut: str = "clean", width: int = WIDTH,
         height: int = HEIGHT, met_start: str = "800",
         met_end: str = "1225", met_step: str = "1",
         clip: str = FINAL_CLIP):
    """Render one clip, or its 3-frame probe with --probe.

    No other arguments: exactly the A7 final clean cut, as before.
    Any render may name its run, cut, size, MET span, step (whole or
    an exact fraction like 1/15) and clip name; each keeps its own
    probe timing, and the cost cap reads that render's timing."""
    if modal is None:
        raise RuntimeError("Modal client not installed; see README.md "
                           "(Finals on Modal)")
    spec = resolve_render(run_id=run_id, cut=cut, width=width,
                          height=height, met_start=met_start,
                          met_end=met_end, met_step=met_step, clip=clip)
    out_dir = ROOT / "out" / "final"
    remote_args = dict(run_id=spec["run_id"], cut=spec["cut"],
                       width=spec["width"], height=spec["height"],
                       met_step=exact_text(spec["met_step"]))
    if spec["cut"] == "pullback":
        # The probe renders only the move's first frames; name the
        # full span so they stay at the move's start (A9B).
        remote_args["pullback_met_start"] = exact_text(spec["met_start"])
        remote_args["pullback_met_end"] = exact_text(spec["met_end"])
    if probe:
        _refuse_existing(out_dir, result_names(spec["probe_clip"])
                          + (spec["timing_name"],))
        print("probe: %s %s cut, MET %s to %s at %d x %d, Cycles %d "
              "samples on one %s"
              % (spec["run_id"], spec["cut"],
                 exact_text(spec["met_start"]),
                 exact_text(spec["probe_met_end"]), spec["width"],
                 spec["height"], SAMPLES, GPU_TYPE))
        result = _render_remote.remote(
            exact_text(spec["met_start"]),
            exact_text(spec["probe_met_end"]), spec["probe_clip"],
            **remote_args)
        proj = probe_projection(result["elapsed_seconds"],
                                result["frame_times"],
                                result["frame_count"],
                                full_frames=spec["frame_count"])
        timing = {
            "run_id": spec["run_id"], "clip": spec["clip"],
            "cut": spec["cut"],
            "resolution": [spec["width"], spec["height"]],
            "met_step": exact_text(spec["met_step"]),
            "probe_met_range": [json_number(spec["met_start"]),
                                json_number(spec["probe_met_end"])],
            "probe_frames": result["frame_count"],
            "elapsed_seconds": result["elapsed_seconds"],
            "frame_times_seconds": result["frame_times"],
            "startup_seconds": proj["startup_seconds"],
            "mean_frame_seconds": proj["mean_frame_seconds"],
            "seconds_per_frame": proj["mean_frame_seconds"],
            "timing_method": proj["timing_method"],
            "full_frames": spec["frame_count"],
            "projected_full_seconds": proj["projected_seconds"],
            "projected_full_cost_usd": proj["projected_cost_usd"],
            "l40s_usd_per_hour": L40S_USD_PER_HOUR,
            "gpu": result["gpu"]}
        files = dict(result["files"])
        files[spec["timing_name"]] = (
            json.dumps(timing, indent=2) + "\n").encode("utf-8")
        written = save_outputs(files, out_dir)
        _print_result(result, written, proj["mean_frame_seconds"])
        print("probe start-up and scene build: %.1f seconds"
              % proj["startup_seconds"])
        print("mean frame time: %.2f seconds" % proj["mean_frame_seconds"])
        if proj["timing_method"] != "frame_times":
            print("Blender's frame times could not be read from its "
                  "output, so this projection falls back to the whole "
                  "probe time spread over its frames; start-up is "
                  "then counted in every frame, and the projection "
                  "runs high.")
        print("projected cost of all %d frames at $%.2f/hour: $%.2f "
              "(%.0f projected seconds, cap $%.2f)"
              % (spec["frame_count"], L40S_USD_PER_HOUR,
                 proj["projected_cost_usd"], proj["projected_seconds"],
                 cost_cap))
        return
    projected = read_probe_projection_usd(out_dir, spec["timing_name"])
    check_cost_cap(projected, cost_cap)
    _refuse_existing(out_dir, result_names(spec["clip"]))
    print("render: %s, %s cut, MET %s to %s, %d frames at %d fps, "
          "%d x %d, Cycles %d samples on one %s; projected cost "
          "$%.2f (cap $%.2f)"
          % (spec["run_id"], spec["cut"], exact_text(spec["met_start"]),
             exact_text(spec["met_end"]), spec["frame_count"], FPS,
             spec["width"], spec["height"], SAMPLES, GPU_TYPE,
             projected, cost_cap))
    result = _render_remote.remote(
        exact_text(spec["met_start"]), exact_text(spec["met_end"]),
        spec["clip"], **remote_args)
    actual_spf = (sum(result["frame_times"]) / len(result["frame_times"])
                  if result["frame_times"]
                  else result["elapsed_seconds"] / result["frame_count"])
    written = save_outputs(result["files"], out_dir)
    _print_result(result, written, actual_spf)
    print("elapsed: %.1f seconds for %d frames"
          % (result["elapsed_seconds"], result["frame_count"]))


if __name__ == "__main__":
    print("Run this with Modal, not plain Python. From this folder:\n"
          "    modal run render_modal.py --probe\n"
          "    modal run render_modal.py\n"
          "See README.md, 'Finals on Modal'.")
    sys.exit(2)

