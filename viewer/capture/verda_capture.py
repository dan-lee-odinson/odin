"""Films VERDA's page a frame at a time, for the demo video.

    python capture/verda_capture.py --run inputs/runs/PH2-PASS3-SPARK-R2 \\
        --passes inputs/pass-records --plans inputs/plans \\
        --scripted inputs/scripted-commands/phase2_scripted_commands.json \\
        --clip inputs/clips/PH2-PASS3-SPARK-R2_instrument_footage.sync.json \\
        --from 880 --to 1000 --speed 2 --out <folder>/shot.mp4

It makes the page as the converter makes it, in a temporary folder: the run's own
timeline, beside the Director's pass of its plan when --passes holds one, and at
most one clip, the one --clip names, so which clip is on screen is never left to
chance. Its copy of the page carries one thing VERDA's page does not: VERDA_SEEK,
which moves the playhead to any fraction of a second, as the scrub bar does to
whole seconds, and says what the pane then shows. It is added to the copy's
verda.js where the page leaves room for it (copy_page), and only there. The run's own timeline file must be the one the clip pins, and the one
--expect-timeline names when it is given.

It opens that page in headless Chrome or Edge at 1920 x 1080 and, for each video
frame k (counted from 0), moves the playhead to MET from + k x speed / fps, or
holds it at --hold; waits until the page is drawn and, with a clip, until the pane
shows the clip frame the page names for that MET; checks that frame against the
sync file, and that the page's boxes are where they were on the first frame with
nothing overflowing; and takes a screenshot. ffmpeg encodes the screenshots as they come,
H.264 at --fps frames a second. The first frame shows --from, the last --to.

No cursor is drawn and nothing is hovered. A shot's steps (--steps, a JSON list of
{"frame": n, "click_label": text} or {"frame": n, "pick_record": id}, frames
counted from 1) are clicks dispatched on the page's own elements before frame n.

It reads the run, the passes, the plans and the clip, and writes only the video
(written beside its name and renamed into place when whole), its frame log and any
frames --keep asks for. It never overwrites a file.
"""

import argparse
import base64
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "convert"))
sys.path.insert(0, str(ROOT / "tests"))
import browser_probe  # noqa: E402
import clips  # noqa: E402
import huginn_dictionary  # noqa: E402
import verda_convert as vc  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
SPEEDS = (1, 2, 5, 10, 20, 60)  # the page's own list
FFMPEG = ROOT / "ffmpeg" / "ffmpeg-9.0.2-essentials_build" / "bin" / "ffmpeg.exe"
PAGE_FILES = ("index.html", "verda.js", "verda.css")
PAGE_FOLDERS = ("fonts",)

# The capture's own hook, added to its copy of verda.js just before this line of it.
SEEK_ANCHOR = '  // The boxed MET readout. Its text reads "MET <s> s".\n'
SEEK_HOOK = """  // Added by VERDA's capture tool to its own copy of the page: moves the playhead to a
  // MET, as the scrub bar does but to any fraction of a second, and returns what the
  // pane then says. It reads and writes nothing else.
  window.VERDA_SEEK = function (met) {
    pause();
    setMet(Number(met));
    const c = S.clip && S.clip.clip;
    return { met: S.met, note: $('clip-note').textContent,
             clip: c && S.clip.frames ? { file: c.file, fps: c.fps, frames: S.clip.frames } : null };
  };

"""

# Keeps the last clip frame the browser presented, as the pane drew it.
WATCH = """(() => {
  const v = document.getElementById('clip');
  window.__verdaPresented = null;
  if (!v || !v.requestVideoFrameCallback) return false;
  const loop = (now, meta) => { window.__verdaPresented = meta.mediaTime; v.requestVideoFrameCallback(loop); };
  v.requestVideoFrameCallback(loop);
  return true;
})()"""

# Moves the playhead; with a clip, waits until the pane shows the frame the page names.
SEEK = """(async () => {
  const r = window.VERDA_SEEK(%r);
  const v = document.getElementById('clip');
  let presented = null;
  const t0 = performance.now();
  if (r.clip) {
    const m = /Frame (\\d+) of (\\d+)/.exec(r.note);
    const want = m ? (Number(m[1]) - 1) / r.clip.fps : null;
    while (want !== null && performance.now() - t0 < 8000) {
      const p = window.__verdaPresented;
      if (!v.seeking && v.readyState >= 2 && p !== null && Math.abs(p - want) < 0.25 / r.clip.fps) { presented = p; break; }
      await new Promise((res) => setTimeout(res, 4));
    }
  }
  await new Promise((res) => requestAnimationFrame(() => requestAnimationFrame(res)));
  const box = (q) => { const b = document.querySelector(q).getBoundingClientRect(); return [b.left, b.top, b.width, b.height].join(','); };
  const l = document.getElementById('lanes'), s = document.getElementById('side');
  return {met: r.met, note: r.note, clip: r.clip, presented: presented, waited_ms: performance.now() - t0,
          layout: [box('main'), box('#foot'), box('#lanes'), box('#side')].join(' '),
          overflow: Math.max(l.scrollHeight - l.clientHeight, s.scrollHeight - s.clientHeight,
                             document.documentElement.scrollHeight - innerHeight)};
})()"""

# Shows another clip frame for a moment, so the first frame filmed is one the browser is seen to present.
PRIME = """(async () => {
  const v = document.getElementById('clip');
  const want = %d / %r;
  v.currentTime = want + 0.5 / %r;
  const t0 = performance.now();
  while (performance.now() - t0 < 8000) {
    const p = window.__verdaPresented;
    if (!v.seeking && p !== null && Math.abs(p - want) < 0.25 / %r) return p;
    await new Promise((res) => setTimeout(res, 4));
  }
  return null;
})()"""

CLICK_LABEL = """(() => {
  const t = [...document.querySelectorAll('text[data-hit]')].find((e) => e.textContent === %s);
  if (!t) return false;
  t.dispatchEvent(new MouseEvent('click', {bubbles: true}));
  return true;
})()"""

PICK_RECORD = """(() => {
  const li = document.querySelector('#cites:not([hidden]) li[data-record="%d"]');
  if (!li) return false;
  li.dispatchEvent(new MouseEvent('click', {bubbles: true}));
  return li.classList.contains('selected');
})()"""


class CaptureError(Exception):
    pass


def sha256_hex(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frame_mets(args):
    """The MET each video frame shows, from the first to the last."""
    if args.hold is not None:
        count = int(round(args.seconds * args.fps))
        return [float(args.hold)] * count
    span = args.to - args.start
    count = span * args.fps / args.speed
    if span <= 0 or abs(count - round(count)) > 1e-9:
        raise CaptureError("from %s to %s at %sx is not a whole number of frames at %s fps" % (args.start, args.to, args.speed, args.fps))
    return [args.start + k * args.speed / args.fps for k in range(int(round(count)) + 1)]


def clip_frame(sync, frames, met):
    """The clip frame (counted from 0) the page shows at a MET, as the page works it out."""
    n = (met - sync["first_frame_met_s"]) / sync["met_step_s"]
    if n < 0:
        return 0
    if n > frames - 1:
        return frames - 1
    return math.floor(n + 1e-6)


def copy_page(page_dir):
    """VERDA's page, copied into a new folder, with the capture's seek hook added to its verda.js."""
    page_dir = Path(page_dir)
    page_dir.mkdir()
    for name in PAGE_FILES:
        shutil.copyfile(ROOT / "page" / name, page_dir / name)
    for name in PAGE_FOLDERS:
        shutil.copytree(ROOT / "page" / name, page_dir / name)
    js = (page_dir / "verda.js").read_bytes().decode("utf-8")
    if js.count(SEEK_ANCHOR) != 1 or "VERDA_SEEK" in js:
        raise CaptureError("verda.js has changed where the capture tool adds its seek; nothing is filmed")
    (page_dir / "verda.js").write_bytes(js.replace(SEEK_ANCHOR, SEEK_HOOK + SEEK_ANCHOR).encode("utf-8"))
    return page_dir


def build_page(args, folder):
    """The page and its timelines in a folder: the run beside its pass, and the one clip."""
    page_dir = copy_page(Path(folder, "page"))
    out = page_dir / "timelines"
    dictionary = Path(args.dictionary) if args.dictionary else vc.find_dictionary()
    match = None
    if args.passes:
        passes = vc.read_passes(args.passes, huginn_dictionary.read_points(dictionary))
        match = vc.pass_for_run(Path(args.run), passes, vc.read_plans(args.plans))
    path, timeline = vc.convert(Path(args.run), out, dictionary, True,
                                Path(args.passes) / match["name"] if match else None, args.plans, args.scripted)
    if any(not c.get("ok", c["chain"] == "VERIFIED") for c in timeline["integrity"]):
        raise CaptureError("%s: a check of the run failed; nothing is filmed" % timeline["id"])
    own = sha256_hex(path)
    if args.expect_timeline and own != args.expect_timeline.replace("sha256:", "").lower():
        raise CaptureError("%s is sha256 %s, not the %s it should be" % (path.name, own, args.expect_timeline))
    sync, frames = None, None
    if args.clip:
        sync, problems = clips.read_sync(args.clip)
        if problems:
            raise CaptureError("; ".join(problems))
        if sync["run_id"] != timeline["id"] or sync["timeline_sha256"] != "sha256:" + own:
            raise CaptureError("the clip pins %s %s, and the timeline is %s sha256:%s" % (
                sync["run_id"], sync["timeline_sha256"], timeline["id"], own))
        source = Path(folder, "clip")
        source.mkdir()
        found = clips.clip_beside(args.clip)
        if len(found) != 1:
            raise CaptureError("no single clip beside %s" % args.clip)
        for p in (found[0], Path(args.clip)):
            shutil.copyfile(p, source / p.name)
        placed = [p for _, p, problems in clips.place_clips(source, out) if p]
        if len(placed) != 1:
            raise CaptureError("the clip was not placed")
        vc.write_index(out)
    return page_dir, timeline, own, match, sync


def ffmpeg_command(args, partial):
    return [str(args.ffmpeg), "-hide_banner", "-loglevel", "error", "-n",
            "-f", "image2pipe", "-framerate", str(args.fps), "-c:v", "png", "-i", "-",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
                   "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
            "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf), "-profile:v", "high",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-r", str(args.fps), "-movflags", "+faststart", "-an", str(partial)]


def probe(args, path):
    ffprobe = Path(args.ffmpeg).with_name("ffprobe" + Path(args.ffmpeg).suffix)
    out = subprocess.run([str(ffprobe), "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_read_frames,pix_fmt",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["streams"][0]


def capture(args):
    out = Path(args.out)
    log_path = Path(args.log) if args.log else ROOT / "out" / "capture" / (out.stem + ".frames.csv")
    for p in (out, log_path):
        if p.exists():
            raise CaptureError("%s exists; the capture never overwrites a file" % p)
    partial = out.with_name(out.stem + ".partial" + out.suffix)
    if partial.exists():
        raise CaptureError("%s exists; remove it or name another file" % partial)
    mets = frame_mets(args)
    steps = json.loads(Path(args.steps).read_text(encoding="utf-8")) if args.steps else []
    keep = {int(k) for k in args.keep.split(",")} if args.keep else set()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="verda-capture-") as tmp:
        page_dir, timeline, own, match, sync = build_page(args, tmp)
        page = browser_probe.Page()
        encoder = None
        rows = []
        try:
            page.call("Emulation.setDeviceMetricsOverride", {"width": WIDTH, "height": HEIGHT, "deviceScaleFactor": 1, "mobile": False})
            extra = "&met=%r" % mets[0] + ("&view=%s" % args.view if args.view else "")
            page.open(browser_probe.page_url(page_dir, timeline["id"], extra), settle=2.5)
            shown = page.evaluate("({id: document.getElementById('run-select').value, vw: innerWidth, vh: innerHeight,"
                                  " seek: typeof window.VERDA_SEEK})")
            if shown != {"id": timeline["id"], "vw": WIDTH, "vh": HEIGHT, "seek": "function"}:
                raise CaptureError("the page is not ready to film: %r" % shown)
            if args.hold is None and args.speed in SPEEDS:
                # The page's speed box shows the shot's speed, as the page writes it ("2", not "2.0").
                if page.evaluate("(() => { const s = document.getElementById('speed'); s.value = '%g';"
                                 " s.dispatchEvent(new Event('change')); return s.value; })()" % args.speed) != "%g" % args.speed:
                    raise CaptureError("the page's speed box has no %gx" % args.speed)
            frames = None
            if sync:
                first = page.evaluate("window.VERDA_SEEK(%r)" % mets[0])
                if not first["clip"]:
                    raise CaptureError("the page plays no clip: %s" % first["note"])
                frames = first["clip"]["frames"]
                if not page.evaluate(WATCH):
                    raise CaptureError("this browser cannot say which clip frame it shows")
                other = frames - 1 if clip_frame(sync, frames, mets[0]) != frames - 1 else 0
                if page.evaluate(PRIME % (other, sync["fps"], sync["fps"], sync["fps"])) is None:
                    raise CaptureError("the browser never presented clip frame %d" % (other + 1))
            encoder = subprocess.Popen(ffmpeg_command(args, partial), stdin=subprocess.PIPE)
            layout = None
            for k, met in enumerate(mets):
                n = k + 1
                for step in (s for s in steps if s["frame"] == n):
                    if "click_label" in step:
                        done = page.evaluate(CLICK_LABEL % json.dumps(step["click_label"]))
                    else:
                        done = page.evaluate(PICK_RECORD % step["pick_record"])
                    if not done:
                        raise CaptureError("frame %d: the step %r did nothing" % (n, step))
                state = page.evaluate(SEEK % met)
                if abs(state["met"] - met) > 1e-9:
                    raise CaptureError("frame %d: the playhead is at MET %r, not %r" % (n, state["met"], met))
                # The page holds still around the playhead: the same boxes on every frame, nothing scrolled.
                layout = layout or state["layout"]
                if state["layout"] != layout or state["overflow"] > 0:
                    raise CaptureError("frame %d, MET %r: the page's layout moved or overflowed (%s, %s px over; frame 1 had %s)" % (
                        n, met, state["layout"], state["overflow"], layout))
                shown_frame = None
                if sync:
                    want = clip_frame(sync, frames, met)
                    words = state["note"].split("Frame ", 1)[-1].split(" of ", 1)[0]
                    shown_frame = int(words) - 1 if words.isdigit() else None
                    if shown_frame != want or state["presented"] is None or abs(state["presented"] * sync["fps"] - want) > 0.25:
                        raise CaptureError("frame %d, MET %r: the pane should show clip frame %d; it says %r and shows %r" % (
                            n, met, want + 1, state["note"], state["presented"]))
                png = page.call("Page.captureScreenshot", {"format": "png", "fromSurface": True}, timeout=60)["data"]
                data = base64.b64decode(png)
                encoder.stdin.write(data)
                if n in keep:
                    Path(args.keep_dir).mkdir(parents=True, exist_ok=True)
                    with open(Path(args.keep_dir) / ("%s-frame%04d.png" % (out.stem, n)), "xb") as handle:
                        handle.write(data)
                rows.append({"frame": n, "met_s": repr(met), "clip_frame": "" if shown_frame is None else shown_frame + 1,
                             "clip_media_time_s": "" if state["presented"] is None else repr(state["presented"]),
                             "pane_note": state["note"] if sync else "", "waited_ms": "%.1f" % state["waited_ms"]})
                if n % 100 == 0 or n == len(mets):
                    print("frame %d of %d, MET %.3f" % (n, len(mets), met), flush=True)
            if page.errors:
                raise CaptureError("the page reported errors: %s" % page.errors)
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise CaptureError("ffmpeg failed")
            encoder = None
        finally:
            page.close()
            if encoder is not None:
                encoder.kill()
                encoder.wait()
                partial.unlink(missing_ok=True)
    info = probe(args, partial)
    if (info["codec_name"], info["width"], info["height"], info["r_frame_rate"], int(info["nb_read_frames"])) != (
            "h264", WIDTH, HEIGHT, "%d/1" % args.fps, len(mets)):
        partial.unlink()
        raise CaptureError("the encoded video is not what was filmed: %r" % info)
    partial.rename(out)  # fails rather than overwrite
    with open(log_path, "x", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return {"file": out.name, "sha256": sha256_hex(out), "bytes": out.stat().st_size, "frames": len(mets),
            "seconds": len(mets) / args.fps, "first_met_s": mets[0], "last_met_s": mets[-1],
            "speed": None if args.hold is not None else args.speed, "run": timeline["id"],
            "beside": match["name"] if match else None, "timeline_sha256": own,
            "clip": Path(args.clip).name if args.clip else None,
            "clip_sha256": sha256_hex(clips.clip_beside(args.clip)[0]) if args.clip else None,
            "sync_sha256": sha256_hex(args.clip) if args.clip else None, "log": str(log_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Film VERDA's page a frame at a time.")
    parser.add_argument("--run", required=True, help="the run folder")
    parser.add_argument("--passes", help="the Director's pass folders")
    parser.add_argument("--plans", help="the plans")
    parser.add_argument("--scripted", help="the scenarios' own scripted commands")
    parser.add_argument("--dictionary", help="HUGINN's tlm_cmd.yaml")
    parser.add_argument("--clip", help="the one clip's sync file; without it, no clip is on screen")
    parser.add_argument("--expect-timeline", help="the SHA-256 the run's own timeline file must have")
    parser.add_argument("--from", dest="start", type=float, help="the MET of the first frame")
    parser.add_argument("--to", type=float, help="the MET of the last frame")
    parser.add_argument("--speed", type=float, help="seconds of MET for each second of video")
    parser.add_argument("--hold", type=float, help="hold the playhead at this MET")
    parser.add_argument("--seconds", type=float, help="with --hold, how long")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--view", help="the timeline's window, FROM-TO in MET")
    parser.add_argument("--steps", help="a JSON file of clicks, each before a frame")
    parser.add_argument("--keep", help="frames to save as PNG too, counted from 1, comma-separated")
    parser.add_argument("--keep-dir", default=str(ROOT / ".scratch" / "capture-frames"))
    parser.add_argument("--out", required=True, help="the video file to write")
    parser.add_argument("--log", help="the frame log to write (CSV)")
    parser.add_argument("--ffmpeg", default=str(FFMPEG))
    parser.add_argument("--crf", type=int, default=12)
    parser.add_argument("--preset", default="slow")
    args = parser.parse_args(argv)
    if (args.hold is None) == (args.start is None):
        parser.error("give --from, --to and --speed, or --hold and --seconds")
    if args.hold is None and (args.to is None or not args.speed):
        parser.error("--from needs --to and --speed")
    if args.hold is not None and not args.seconds:
        parser.error("--hold needs --seconds")
    try:
        result = capture(args)
    except (CaptureError, vc.RunFolderError, OSError) as exc:
        print("NOT FILMED: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
