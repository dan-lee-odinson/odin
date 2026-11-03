"""Builds VERDA's replay site: the page and the timelines of the runs it shows, in one
folder for GitHub Pages to serve as it is.

    python site/build_site.py --runs <folder of run folders> --passes <the Director's passes> \\
        --plans <the phase-2 plans> --scripted <phase2_scripted_commands.json> \\
        --dictionary <HUGINN's tlm_cmd.yaml> --clip <the site clip's sync file> --out <site folder>

It converts exactly the runs SITE_RUNS names, no more and no fewer: phase 2's fifty
scored runs, each beside the Director's pass flown under its plan, and phase 3's
scenarios A (PH3-H02) and D (PH3-H04), each alone. Phase 3's B, C and E stay off: VERDA
would show C's and E's onboard turns as ground turns, and B's set-aside runs as ordinary
runs. It places the one clip SITE_CLIPS allows a run, and no other: PH2-PASS3-SPARK-R2's
site clip, never its footage clip. Beside it goes the clip's full caption (SITE_CAPTIONS),
which the page opens from the pane's "Full caption".

The page goes on the site as it is, its Content-Security-Policy with it: watch-only,
reading only its own files. The site's folder holds index.html, verda.js, verda.css and
fonts/, and timelines/ as the converter writes it.

It fails, and leaves no site, if a run is missing or will not convert, if any of a run's
checks fails or the converter warns of a file it could not read, if a clip is not the one
SITE_CLIPS allows, if a clip pins a timeline file the site does not hold byte for byte,
or if PH2-PASS3-SPARK-R2's own timeline is not the file its clips were rendered from
(PINNED). It reads the records and writes only the site's folder, which must not exist
yet; it builds the site beside it and renames it into place when whole. What it writes is
generated, and is never committed.
"""

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "convert"))
import clips  # noqa: E402
import huginn_dictionary  # noqa: E402
import verda_convert as vc  # noqa: E402

PHASE2_RUNS = tuple("PH2-%s-%s-R%d" % (p, a, n) for p in ("PASS1", "PASS2A", "PASS2B", "PASS3", "PASS4")
                    for a in ("SPARK", "OPEN") for n in range(1, 6))
PHASE3_RUNS = tuple("PH3-%s-%s-R%d" % (s, a, n) for s in ("H02", "H04") for a in ("SPARK", "OPEN") for n in range(1, 6))
SITE_RUNS = PHASE2_RUNS + PHASE3_RUNS
# The one clip each run may carry on the site, by its sync file's name.
SITE_CLIPS = {"PH2-PASS3-SPARK-R2": "PH2-PASS3-SPARK-R2_instrument_site.sync.json"}
# Each clip's full caption: CAPTIONS.md's caption for an A5 clip, with its instrument cut's
# sentences, the space-weather sentence said for this run as the A2/A4 caption says it, and
# no epoch sentence (the PASS-3 runs' epochs are not shifted). From the render session's
# CAPTIONS.md of 2 November 2026, sha256 f33106bb89c3fb0b9ed3a0425ed34b2a57eed7efdefb031cbcb2789e4e7e4f03.
SITE_CAPTIONS = {"PH2-PASS3-SPARK-R2": (
    "HUGINN at its true size, camera about three meters away, Earth 500 km below \u2014 flown from "
    "the run's own record (VERDA timeline): position, sunlight, contact, payload state, mode, and "
    "load limit state are the run's telemetry. The spacecraft's look and pose are drawn \u2014 a "
    "standard 6U CubeSat with twin solar arrays \u2014 since its definition gives no panel layout or "
    "colors. The Sun's direction is computed from the run's UTC time. Earth: NASA Blue Marble (NASA "
    "Earth Observatory); clouds and night lights are NASA composites (Blue Marble cloud layer; Black "
    "Marble 2016), not the run's date. Space weather appears only in runs whose record carries the "
    "feed; this run carries none. The thin line from the antenna is the ground-station radio link "
    "while in contact. Brief flashes mark ODIN's requests (cyan) and BALDUR-0's decisions (green "
    "allow, red deny); the strip shows the load limit state (green, amber, red)."
)}
# Timeline files whose bytes a clip was rendered from: the site must make these same bytes.
PINNED = {"PH2-PASS3-SPARK-R2": "d0f1a57349d60cbee5835f3bac6a945e02762ecf49387ebca6caa968d12fe617"}
PAGE_FILES = ("index.html", "verda.js", "verda.css")
PAGE_FOLDERS = ("fonts",)
TIMELINES = "timelines"


class SiteError(Exception):
    pass


def sha256_hex(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def chosen_clips(clip_paths):
    """The clips given, each one SITE_CLIPS allows, and every clip it names given."""
    chosen = {}
    for path in map(Path, clip_paths):
        run = next((r for r, name in SITE_CLIPS.items() if name == path.name), None)
        if run is None:
            raise SiteError("%s is not a clip the site carries; it carries only %s" % (path.name, ", ".join(SITE_CLIPS.values())))
        sync, problems = clips.read_sync(path)
        if problems:
            raise SiteError("; ".join(problems))
        if sync["run_id"] != run:
            raise SiteError("%s names run %s, not %s" % (path.name, sync["run_id"], run))
        found = clips.clip_beside(path)
        if len(found) != 1:
            raise SiteError("no single clip beside %s" % path.name)
        chosen[run] = (path, found[0])
    missing = sorted(set(SITE_CLIPS) - set(chosen))
    if missing:
        raise SiteError("no clip given for %s: give %s" % (", ".join(missing), ", ".join(SITE_CLIPS[r] for r in missing)))
    return chosen


def check_timeline(name, timeline):
    """A run goes on the site only with every check passing and nothing left unread."""
    broken = [c["label"] for c in timeline["integrity"] if not c.get("ok", c["chain"] == "VERIFIED")]
    if broken:
        raise SiteError("%s: a check failed: %s" % (name, ", ".join(broken)))
    if timeline["warnings"]:
        raise SiteError("%s: %s" % (name, "; ".join(timeline["warnings"])))


def check_clips(timelines_dir):
    """Each clip in the site pins a timeline file the site holds, byte for byte."""
    entries = clips.index_entries(timelines_dir)
    for entry in entries:
        if entry["problems"]:
            raise SiteError("%s: %s" % (entry["sync_file"], "; ".join(entry["problems"])))
        own = Path(timelines_dir) / (entry["run_id"] + ".js")
        if not own.is_file():
            raise SiteError("%s pins %s.js, which the site does not hold" % (entry["sync_file"], entry["run_id"]))
        if entry["timeline_sha256"] != "sha256:" + sha256_hex(own):
            raise SiteError("%s pins %s, and %s.js is sha256:%s" % (
                entry["sync_file"], entry["timeline_sha256"], entry["run_id"], sha256_hex(own)))
    return entries


def check_pins(timelines_dir):
    """The timelines the clips were rendered from are made again byte for byte."""
    for run, want in PINNED.items():
        have = sha256_hex(Path(timelines_dir) / (run + ".js"))
        if have != want:
            raise SiteError("%s.js is sha256 %s, not the %s its clips were rendered from" % (run, have, want))


def build(args):
    out = Path(args.out)
    if out.exists():
        raise SiteError("%s exists; the build never overwrites a folder" % out)
    runs_dir = Path(args.runs)
    missing = [r for r in SITE_RUNS if not (runs_dir / r).is_dir()]
    if missing:
        raise SiteError("missing from %s: %s" % (runs_dir, ", ".join(missing)))
    chosen = chosen_clips(args.clip or [])
    dictionary = Path(args.dictionary) if args.dictionary else vc.find_dictionary()
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=out.name + ".building-", dir=out.parent))
    try:
        for name in PAGE_FILES:
            shutil.copyfile(ROOT / "page" / name, staging / name)
        for name in PAGE_FOLDERS:
            shutil.copytree(ROOT / "page" / name, staging / name)
        timelines = staging / TIMELINES
        passes = vc.read_passes(args.passes, huginn_dictionary.read_points(dictionary))
        plans = vc.read_plans(args.plans)
        beside = {}
        for run in SITE_RUNS:
            match = vc.pass_for_run(runs_dir / run, passes, plans)
            if (match is None) != (run in PHASE3_RUNS):
                raise SiteError("%s: %s" % (run, "no pass of the Director's is flown under its plan" if match is None
                                             else "phase 3's runs go on the site alone, but it lines up with %s" % match["name"]))
            try:
                _, timeline = vc.convert(runs_dir / run, timelines, dictionary, True,
                                         Path(args.passes) / match["name"] if match else None, args.plans, args.scripted)
            except (vc.RunFolderError, huginn_dictionary.DictionaryError, OSError) as exc:
                raise SiteError("%s will not convert: %s" % (run, exc))
            check_timeline(run, timeline)
            beside[run] = match["name"] if match else None
        with tempfile.TemporaryDirectory() as source:
            for run, (sync_path, clip_path) in chosen.items():
                for p in (clip_path, sync_path):
                    shutil.copyfile(p, Path(source, p.name))
                Path(source, sync_path.name[:-len(".sync.json")] + clips.CAPTION).write_bytes(
                    SITE_CAPTIONS[run].encode("utf-8"))
            for sync_path, placed, problems in clips.place_clips(source, timelines):
                if problems:
                    raise SiteError("; ".join(problems))
        vc.write_index(timelines)
        entries = check_clips(timelines)
        for entry in entries:
            if entry["caption"] != SITE_CAPTIONS[entry["run_id"]]:
                raise SiteError("%s went on the site without its caption" % entry["sync_file"])
        check_pins(timelines)
        listed = sorted(p.stem for p in timelines.glob("*.js") if p.name != "index.js" and not p.name.endswith(vc.BESIDE_SUFFIX))
        if listed != sorted(SITE_RUNS):
            raise SiteError("the site would hold %s, not exactly its runs" % ", ".join(sorted(set(listed) ^ set(SITE_RUNS))))
        try:
            staging.rename(out)
        except OSError as exc:
            raise SiteError("the site could not be put in place at %s: %s" % (out, exc))
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"runs": len(SITE_RUNS), "beside": sum(1 for v in beside.values() if v), "alone": sum(1 for v in beside.values() if not v),
            "clips": [(e["run_id"], Path(e["file"]).name) for e in entries], "pinned": dict(PINNED), "out": str(out)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build VERDA's replay site from the committed records.")
    parser.add_argument("--runs", required=True, help="the folder holding the run folders")
    parser.add_argument("--passes", required=True, help="the Director's pass folders")
    parser.add_argument("--plans", required=True, help="the phase-2 plans")
    parser.add_argument("--scripted", required=True, help="phase2_scripted_commands.json")
    parser.add_argument("--dictionary", help="HUGINN's tlm_cmd.yaml")
    parser.add_argument("--clip", action="append", help="a clip's sync file, the clip beside it")
    parser.add_argument("--out", required=True, help="the site's folder, which must not exist yet")
    args = parser.parse_args(argv)
    try:
        result = build(args)
    except SiteError as exc:
        print("SITE NOT BUILT: %s" % exc, file=sys.stderr)
        return 1
    print("site -> %s: %d runs (%d beside the Director's pass, %d alone), clips %s, %s.js as pinned" % (
        result["out"], result["runs"], result["beside"], result["alone"],
        ", ".join("%s for %s" % (f, r) for r, f in result["clips"]), ", ".join(result["pinned"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
