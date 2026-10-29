"""Where VERDA's tests find their inputs.

By default the inputs are the folder's inputs/, as Claude Code placed them.
Environment variables point a test at other copies, which is how
tests/show_red.py plants a changed input without touching the real one:

    VERDA_INPUTS      the inputs folder
    VERDA_RUNS        the folder holding the practice run folders
    VERDA_DICTIONARY  HUGINN's tlm_cmd.yaml
    VERDA_PAGE        the page folder (index.html, verda.js, verda.css)

A test whose inputs are missing fails. None of VERDA's tests skips.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "convert") not in sys.path:
    sys.path.insert(0, str(ROOT / "convert"))

PRACTICE_RUNS = ("dev-practice-p3", "dev-practice-p3-process", "dev-practice-p4")

# What a deposit holds: VERDA's own files and, beside them, the deposit's DEPOSIT.md
# and MANIFEST.sha256. Never the inputs, run folders, generated timelines, scratch
# files or caches.
DEPOSITED = ("README.md", "DEPOSIT.md", "MANIFEST.sha256", "convert", "page", "tests")
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


def practice_runs():
    return [need(runs_dir() / name / "events.jsonl").parent for name in PRACTICE_RUNS]


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
