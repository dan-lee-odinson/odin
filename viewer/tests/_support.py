"""Where VERDA's tests find their inputs.

By default the inputs are the folder's inputs/, as Claude Code placed them.
Environment variables point a test at other copies, which is how
tests/show_red.py plants a changed input without touching the real one:

    VERDA_INPUTS      the inputs folder
    VERDA_RUNS        the folder holding the practice run folders
    VERDA_DICTIONARY  HUGINN's tlm_cmd.yaml
    VERDA_SCRIPTED    the scenarios' scripted commands, phase2_scripted_commands.json
    VERDA_CLIPS       the animation clips, each with its sync file
    VERDA_PAGE        the page folder (index.html, verda.js, verda.css)

The Director's passes and the plans are read from the inputs folder, as
pass-records/ and plans/, and the scenarios' own commands from
scripted-commands/.

A test whose inputs are missing fails. None of VERDA's tests skips.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _folder in ("convert", "capture", "site"):
    if str(ROOT / _folder) not in sys.path:
        sys.path.insert(0, str(ROOT / _folder))

PRACTICE_RUNS = ("dev-practice-p3", "dev-practice-p3-process", "dev-practice-p4")
# S5's live check of 28 October 2026: P3's pass flown in the ground seat, its run_id dev-s6-0001.
GROUND_SEAT_RUN = "dev-s5-live-ground-seat"
# Phase 2's fifty scored runs: each pass flown five times by each model, spark and spark_open.
SCORED_PASSES = ("PASS1", "PASS2A", "PASS2B", "PASS3", "PASS4")
SCORED_ARMS = ("SPARK", "OPEN")
SCORED_RUNS = tuple("PH2-%s-%s-R%d" % (p, a, n) for p in SCORED_PASSES for a in SCORED_ARMS for n in range(1, 6))
# The Director's pass each scored run is flown beside, by the plan both were flown under.
PASS_OF = {"PASS1": "2026-09-13-P1", "PASS2A": "2026-09-20-P2a", "PASS2B": "2026-09-20-P2b",
           "PASS3": "2026-10-11-P3", "PASS4": "2026-10-11-P4"}
# A phase-2 development run, P3 flown by spark_open: the run the animation's preview clip shows.
PREVIEW_RUN = "dev-ph2-p3-open-01"
ALL_RUNS = PRACTICE_RUNS + (GROUND_SEAT_RUN, PREVIEW_RUN) + SCORED_RUNS
# The Director's five phase-2 passes, in inputs/pass-records/.
PASSES = ("2026-09-13-P1", "2026-09-20-P2a", "2026-09-20-P2b", "2026-10-11-P3", "2026-10-11-P4")

# What a deposit holds: VERDA's own files and, beside them, the deposit's DEPOSIT.md
# and MANIFEST.sha256. Never the inputs, run folders, generated timelines, scratch
# files or caches.
DEPOSITED = ("README.md", "DEPOSIT.md", "MANIFEST.sha256", "capture", "convert", "page", "site", "tests")
NOT_DEPOSITED_DIRS = {"__pycache__", "timelines"}


def need(path):
    path = Path(path)
    if not path.exists():
        raise AssertionError("missing input: %s" % path)
    return path


def inputs_dir():
    return Path(os.environ.get("VERDA_INPUTS", ROOT / "inputs"))


def runs_dir():
    return Path(os.environ.get("VERDA_RUNS", inputs_dir() / "runs"))


def dictionary_path():
    default = inputs_dir() / "dictionaries" / "HUGINN" / "tlm_cmd.yaml"
    return need(os.environ.get("VERDA_DICTIONARY", default))


def contract_path():
    return need(inputs_dir() / "CONTRACT.md")


def schemas_dir():
    return need(inputs_dir() / "contract" / "schemas")


def page_dir():
    return need(os.environ.get("VERDA_PAGE", ROOT / "page"))


def deposit_files():
    """Every file a deposit takes from this folder, in path order."""
    out = []
    for top in DEPOSITED:
        path = ROOT / top
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            for item in path.rglob("*"):
                rel = item.relative_to(ROOT)
                if item.is_file() and not (set(rel.parts) & NOT_DEPOSITED_DIRS) and item.suffix != ".pyc":
                    out.append(item)
    return sorted(out, key=lambda p: p.relative_to(ROOT).as_posix())


def passes_dir():
    folder = need(inputs_dir() / "pass-records")
    for name in PASSES:
        need(folder / name / "telemetry_hk.csv")
    return folder


def plans_dir():
    return need(inputs_dir() / "plans")


def practice_runs():
    return [need(runs_dir() / name / "events.jsonl").parent for name in PRACTICE_RUNS]


def ground_seat_run():
    return need(runs_dir() / GROUND_SEAT_RUN / "events.jsonl").parent


def all_runs():
    return [need(runs_dir() / name / "events.jsonl").parent for name in ALL_RUNS]


def clips_dir():
    return need(os.environ.get("VERDA_CLIPS", inputs_dir() / "clips"))


def record_lines(run_dir, stem):
    """A run's events or truth file as lines, read through gzip when it is a .gz file."""
    import gzip
    for name in (stem + ".jsonl", stem + ".jsonl.gz"):
        path = Path(run_dir) / name
        if path.is_file():
            data = path.read_bytes()
            return (gzip.decompress(data) if name.endswith(".gz") else data).decode("utf-8").splitlines()
    raise AssertionError("missing input: %s/%s.jsonl" % (run_dir, stem))


def scripted_path():
    default = inputs_dir() / "scripted-commands" / "phase2_scripted_commands.json"
    return need(os.environ.get("VERDA_SCRIPTED", default))


def bundles(run_dir):
    """Yields (trigger record, bundle) for each turn of a run, in order."""
    import json
    with open(Path(run_dir) / "events.jsonl", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    for record in records:
        if record["type"] == "TRIGGER":
            tag = record["body"]["bundle_sha256"]
            path = need(Path(run_dir) / "inputs" / tag[len("sha256:"):])
            yield record, json.loads(path.read_text(encoding="utf-8"))
