# SPDX-License-Identifier: GPL-3.0-or-later
"""A4: the headless render script Claude Code can run anywhere.

A plain command-line wrapper: it takes every path and setting as an
argument (resolving each path to an absolute one itself), builds the A5
true-scale look-pass scene from the scripts in this folder (no scene file
needed), renders with Blender headless, and the clip lands in the output
folder with its A3 sync file beside it. It holds no key and reaches no
network; the engine and samples are the caller's choice (for example a
timing test on a cloud GPU).

Example (preview size, as run locally):
    python render_clip.py --timeline inputs/timelines/dev-ph2-p3-open-01.js
        --output out/a4 --width 640 --height 360 --met-start 890
        --met-end 930 --engine BLENDER_EEVEE --samples 32
Use --dry-run to print the Blender command without running it. The Blender
executable comes from --blender, else the BLENDER environment variable,
else "blender" on the PATH.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINES = ("BLENDER_EEVEE", "CYCLES")


def resolved(value):
    """An absolute path string for any path argument, relative or not.

    Blender resolves its own paths against the blend file's folder, and
    a headless run has none, so relative arguments used to fail unless
    the caller made them absolute first (Director, A5 animate)."""
    return str(Path(value).resolve())


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Render one timeline's clip headless, with its sync file.")
    parser.add_argument("--timeline", required=True,
                        help="VERDA timeline file (.js) to render")
    parser.add_argument("--inputs", default=str(ROOT / "inputs"),
                        help="inputs folder (orbit, epochs, imagery)")
    parser.add_argument("--output", required=True, help="output folder")
    parser.add_argument("--clip", default=None, help="clip file name "
                        "(default: <run>_preview.mp4)")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--met-start", type=int, default=None,
                        help="first MET (default: first telemetry MET)")
    parser.add_argument("--met-end", type=int, default=None,
                        help="last MET (default: the orbit's last MET)")
    parser.add_argument("--met-step", type=int, default=5)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--engine", default="BLENDER_EEVEE", choices=ENGINES)
    parser.add_argument("--cut", default="instrument",
                        choices=("instrument", "clean"),
                        help="instrument keeps the data cues (VERDA pane); "
                             "clean is camera-only, for the video")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--feed", default=None,
                        help="a run's own feed file, when it carries one")
    parser.add_argument("--blender", default=None,
                        help="Blender executable (default: BLENDER env, "
                             "else blender on the PATH)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the Blender command and exit")
    args = parser.parse_args(argv)
    if args.width <= 0 or args.height <= 0 or args.samples <= 0 \
            or args.met_step <= 0 or args.fps <= 0:
        parser.error("width, height, samples, met-step and fps must be positive")
    if not args.dry_run:
        if not Path(args.timeline).is_file():
            parser.error("timeline not found: %s" % args.timeline)
        if not Path(args.inputs).is_dir():
            parser.error("inputs folder not found: %s" % args.inputs)
    args.timeline = resolved(args.timeline)
    args.inputs = resolved(args.inputs)
    args.output = resolved(args.output)
    if args.feed:
        args.feed = resolved(args.feed)
    return args


def blender_executable(args):
    exe = args.blender or os.environ.get("BLENDER") or "blender"
    if os.sep in exe or (os.altsep and os.altsep in exe):
        return resolved(exe)
    return shutil.which(exe) or exe


def build_command(args):
    """The headless Blender command that builds, renders, and writes sync."""
    command = [blender_executable(args), "-b", "--factory-startup",
               "--python-exit-code", "1", "-P", str(ROOT / "build_a5.py"),
               "--", "--animate", "--timeline", str(args.timeline),
               "--inputs", str(args.inputs),
               "--output-dir", str(args.output),
               "--width", str(args.width), "--height", str(args.height),
               "--step", str(args.met_step), "--fps", str(args.fps),
               "--engine", args.engine, "--samples", str(args.samples),
               "--cut", args.cut]
    if args.met_start is not None:
        command += ["--met-start", str(args.met_start)]
    if args.met_end is not None:
        command += ["--met-end", str(args.met_end)]
    if args.clip:
        command += ["--clip", args.clip]
    if args.feed:
        command += ["--feed", str(args.feed)]
    return command


def main(argv=None):
    args = parse_args(argv)
    command = build_command(args)
    print(" ".join(command))
    if args.dry_run:
        return 0
    Path(args.output).mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=str(ROOT))
    if result.returncode != 0:
        return result.returncode
    syncs = sorted(Path(args.output).glob("*.sync.json"))
    clips = sorted(Path(args.output).glob("*.mp4"))
    if not clips or not syncs:
        print("render finished but no clip/sync in %s" % args.output)
        return 1
    print("clip:", clips[-1].name)
    print("sync:", syncs[-1].name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
