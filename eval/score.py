"""Score runs (the Director's scoring ruling of 28 October 2026).

    python -m eval.score runs/scored/<run_id>             one run, as JSON
    python -m eval.score --summary runs/scored/<run_id>... the results table over several phase-2 runs
    python -m eval.score --sheet runs/scored/<run_id>     lay out a phase-1 run's marking sheet (U61)

Each run's pass is the plan its log names; scores come from its event log and truth file alone. A phase-1 run's
results carry the Director's marks from its sheet in marks/phase1/, apart from what S8 scores.
"""

import json
import sys

from eval import phase1, runlog
from eval.results import score_phase_1, score_run, summarize


def score(folder):
    phase = next(r["body"]["phase"] for r in runlog.events(folder) if r["type"] == "RUN_START")
    return score_phase_1(folder) if phase == 1 else score_run(folder)


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
    folders = [a for a in argv if a not in ("--summary", "--sheet")]
    if not folders:
        sys.exit(__doc__)
    if "--sheet" in argv:
        return max(write_sheet(folder) for folder in folders)
    runs = [score(folder) for folder in folders]
    if summary:
        print(json.dumps({f"{p} {m}": row for (p, m), row in summarize(runs).items()}, indent=2, default=str))
    else:
        print(json.dumps(runs if len(runs) > 1 else runs[0], indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
