"""Score runs (the Director's scoring ruling of 28 October 2026).

    python -m eval.score runs/scored/<run_id>             one run, as JSON
    python -m eval.score --summary runs/scored/<run_id>... the results table over several runs, with its totals
    python -m eval.score --sheet runs/scored/<run_id>     lay out a phase-1 run's marking sheet (U61)
    python -m eval.score --held-out <folder> runs/...     a phase-3 run, by S8's sealed checks in <folder>/checks

Each run's pass is the plan its log names; scores come from its event log and truth file alone. A phase-1 run's
results carry the Director's marks from its sheet in marks/phase1/, apart from what S8 scores. A scored run of
phase 2 or 3 that S8 sets aside is written into marks/set_aside.yaml with what S8 found (the Director's ruling
of 29 October 2026); a development run never is.
"""

import json
import sys
from pathlib import Path

import eval.set_aside as aside
from eval import phase1, runlog
from eval.phase3 import load_checks
from eval.results import score_phase_1, score_run, summarize, totals


def score(folder, set_aside_path=None, checks=None):
    run_start = next(r["body"] for r in runlog.events(folder) if r["type"] == "RUN_START")
    if run_start["phase"] == 1:
        return score_phase_1(folder)
    run = score_run(folder, checks=checks)
    if run_start["mode"] == "SCORED" and aside.mark(run["run_id"], run_start["phase"], run.get("set_aside"),
                                                    set_aside_path):
        print(f"{run['run_id']} set aside by S8, written into marks/set_aside.yaml", file=sys.stderr)
    return run


def write_sheet(folder):
    """Lay out a phase-1 run's marking sheet in marks/phase1/, never over one that exists."""
    document = phase1.sheet(runlog.events(folder), runlog.truth(folder))
    path = phase1.SHEETS / f"{document['run_id']}.yaml"
    if path.exists():
        sys.exit(f"{path} exists, perhaps with the Director's marks; nothing was written")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(phase1.sheet_text(document).encode("utf-8"))
    print(f"laid out {path.as_posix()}")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    summary = "--summary" in argv
    held_out = argv[argv.index("--held-out") + 1] if "--held-out" in argv else None
    folders = [a for a in argv if a not in ("--summary", "--sheet", "--held-out", held_out)]
    if not folders:
        sys.exit(__doc__)
    if "--sheet" in argv:
        return max(write_sheet(folder) for folder in folders)
    checks = load_checks(Path(held_out) / "checks") if held_out else None
    runs = [score(folder, checks=checks) for folder in folders]
    if summary:
        table = {f"{p} {m}": row for (p, m), row in summarize(runs).items()}
        print(json.dumps({**table, "totals": totals(runs)}, indent=2, default=str))
    else:
        print(json.dumps(runs if len(runs) > 1 else runs[0], indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
