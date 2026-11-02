"""Score A's and B's twenty phase-3 runs with S8 as the working tree has it (the clock and ground-seat fix of 31 October
2026) and compare each with the results file on record in the held-out results/, as JSON. Reads the run folders only;
writes nothing but this script's own output file beside it.

    python rescore_ab.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HELD_OUT = Path(__file__).resolve().parents[1]
RUNS = [f"PH3-{label}-{arm}-R{n}" for label in ("H02", "H05") for arm in ("SPARK", "OPEN") for n in range(1, 6)]
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

lines, differ = [], []
for run_id in RUNS:
    scored = subprocess.run([sys.executable, "-m", "eval.score", "--held-out", str(HELD_OUT),
                             str(REPO / "runs" / "scored" / run_id)], cwd=REPO, capture_output=True, text=True, env=ENV)
    if scored.returncode != 0:
        sys.exit(f"{run_id}: S8 could not score it: {scored.stderr[-600:]}")
    now = json.loads(scored.stdout)
    on_record = json.loads((HELD_OUT / "results" / f"{run_id}.json").read_text(encoding="utf-8"))
    same = now == on_record
    if not same:
        differ.append(run_id)
    lines.append(f"{run_id}: {'identical' if same else 'DIFFERS'}; success {now['success']}, clean {now['clean']}, "
                 f"report accuracy {now['report_accuracy']['score']}")
lines.append(f"{len(RUNS) - len(differ)} of {len(RUNS)} identical to the results on record")
text = "\n".join(lines) + "\n"
(Path(__file__).with_name("rescore-ab-result.txt")).write_text(text, encoding="utf-8", newline="\n")
print(text, end="")
sys.exit(1 if differ else 0)
