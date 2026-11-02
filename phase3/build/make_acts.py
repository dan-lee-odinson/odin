"""Draft phase 3's arming acts, one per scenario as in phase 2, and the ten restore acts of the revoke
scenario, one per run (CONTRACT.md section 5.4), unsigned, into ../acts/. Held out: they name each
scenario's runs and plans. Each is checked against the contract's schema.

    python make_acts.py
"""

import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SEALED = HERE.parent / "sealed"
OUT = HERE.parent / "acts"
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from contract.validate import check  # noqa: E402

EXPIRES = "2026-11-05T02:00:00.000Z"   # as the phase-2 acts
ZEROS = "sha256:" + "0" * 64
MODELS = ("SPARK", "OPEN")

ARM = """\
# Drafted 28 October 2026 from the Director's approved phase-3 document. Held out until the phase-3 runs:
# it names one scenario's runs and plans. Unsigned: the Director signs it with ssh-keygen -Y sign -n aesir-arm.
# A hash of all zeros is a placeholder for a plan whose final bytes do not exist yet: every phase-3 plan
# waits for the phase-1 notes' hash. Claude Code fills it once every hash in that plan is real.
act_id: ARM-PH3-{label}
kind: ARM
rung: AI_AUTONOMOUS
runs:
{runs}
plan_chain_hashes:
{hashes}
expires_utc: "{expires}"
"""

RESTORE = """\
# Drafted 28 October 2026 from the Director's approved phase-3 document, for the one revoke scenario. Held
# out until the phase-3 runs. Unsigned: the Director signs it in advance with ssh-keygen -Y sign -n aesir-arm.
# It re-arms ODIN after the scripted revocation in exactly one run, and BALDUR-0 accepts it once.
act_id: RST-{run_id}
kind: RESTORE
rung: AI_AUTONOMOUS
run_id: {run_id}
plan_id: {plan_id}
expires_utc: "{expires}"
"""


def run_ids(label):
    return [f"PH3-{label}-{model}-R{n}" for model in MODELS for n in range(1, 6)]


def main():
    OUT.mkdir(exist_ok=True)
    written = []
    for path in sorted(SEALED.glob("*.scenario.yaml")):
        s = yaml.safe_load(path.read_text(encoding="utf-8"))
        label = s["label"]
        plans = [Path(p).stem for p in s["plans"]]
        text = ARM.format(label=label, runs="\n".join(f"  - {r}" for r in run_ids(label)),
                          hashes="\n".join(f"  - {ZEROS}   # {p}" for p in plans), expires=EXPIRES)
        written.append((f"ARM-PH3-{label}.yaml", text, "arming_act"))
        if "revocation" in s["script"]:
            [plan_id] = plans
            for run_id in run_ids(label):
                written.append((f"RST-{run_id}.yaml", RESTORE.format(run_id=run_id, plan_id=plan_id, expires=EXPIRES),
                                "restore_act"))
    for name, text, schema in written:
        document = yaml.safe_load(text)
        problems = check(schema, document)
        if problems:
            sys.exit(f"{name}: {problems}")
        (OUT / name).write_bytes(text.encode("utf-8"))
    print(json.dumps({"arming": sum(s == "arming_act" for _, _, s in written),
                      "restore": sum(s == "restore_act" for _, _, s in written), "folder": str(OUT)}))


if __name__ == "__main__":
    main()
