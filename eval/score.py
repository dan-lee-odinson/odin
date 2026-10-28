"""Score phase-2 runs (the Director's scoring ruling of 28 October 2026).

    python -m eval.score runs/scored/<run_id>             one run, as JSON
    python -m eval.score --summary runs/scored/<run_id>... the results table over several runs

Each run's pass is the plan its log names; scores come from its event log and truth file alone.
"""

import json
import sys

from eval.results import score_run, summarize


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    summary = "--summary" in argv
    folders = [a for a in argv if a != "--summary"]
    if not folders:
        sys.exit(__doc__)
    runs = [score_run(folder) for folder in folders]
    if summary:
        print(json.dumps({f"{p} {m}": row for (p, m), row in summarize(runs).items()}, indent=2, default=str))
    else:
        print(json.dumps(runs if len(runs) > 1 else runs[0], indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
