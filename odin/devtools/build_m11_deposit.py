"""Build deposit MC-M11-01 (AGENTS.md section 6).

Whole odin/ folder as it stands (no __pycache__), DEPOSIT.md at the top,
MANIFEST.sha256 listing every other file with its SHA-256, and an
identical copy of DEPOSIT.md beside the zip as MC-M11-01.DEPOSIT.md.
keys/odin.pub is unchanged since MC-M1-01 and is not included.
Run from the workspace root: python odin/devtools/build_m11_deposit.py
"""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "MC-M11-01"

DEPOSIT_MD = """# Deposit MC-M11-01

- Milestone: M11, spark's answer format that Meta can enforce. After M10,
  ODIN still sent no command: all 145 action answers in the dev run and R1
  were "none" while their rationales said COLLECT, because
  answer.schema.json has a oneOf of the three forms at its root and Meta's
  structured output supports no oneOf/allOf and needs a plain object root.
- Status: deposited as MC-M11-01.zip on the Director's word, 2026-10-29.
- Layout: DEPOSIT.md sits at the top of the deposit zip beside `odin/`. The
  copy beside the zip is named MC-M11-01.DEPOSIT.md so a later deposit
  cannot overwrite it, and is identical to the one inside.
  keys/odin.pub is unchanged since MC-M1-01 and is not included.
- Date the Director saw it run: 2026-10-29 (full suite and red cases shown in session).
- Note: `build_m10_deposit.py` was not present at the workspace root when
  this build began (CONTRACT.md was the only root file), so there was
  nothing to move; this deposit's builder lives in `odin/devtools/`
  as `build_m11_deposit.py`.

## The change (odin/adapters/spark.py only)

1. The ACT format, derived at call time on every ACT turn, no file changed:
   one plain object at the root; no oneOf, allOf, if/then or $ref anywhere;
   no strict flag. `kind` is a required enum of command/escalation/none.
   Every other field of the three forms (command, parameters,
   escalation_kind, refs, proposed, urgency, rationale) is present,
   required but nullable through anyOf with null. `command` is an enum of
   the commands in the dictionary in force, read through the registry
   (`dictionary_for_plan` on the bundle's plan) exactly as the checker
   reads it. `parameters` is a closed object keyed by every argument of
   those commands in lower case, each key required but nullable, with its
   enum or its type and min/max (integer for uint). An escalation's
   `proposed` is typed the same way. escalation_kind, urgency and refs are
   as the frozen schema gives them. Two commands sharing an argument name
   with different types or ranges raise (stop and report).
2. After the call, before the loop checks the answer, the adapter drops
   nulls in the Director's order: null arguments inside parameters (and
   inside proposed's parameters) go first; a field of another form is
   dropped only if null or holding only nulls, otherwise kept so the
   frozen schema refuses it; a field of the chosen form is dropped only
   if optional (rationale) and null, required fields are kept as they
   stand, a no-argument command keeps parameters as {}, and an
   escalation's proposed may be null (and is kept). Then the frozen
   schema and dictionary check judge the answer as before.
3. Report turns keep the M10 $ref-free format; spark_open is unchanged.
   Both of the Director's recorded COLLECT responses are test fixtures.

## Tests run

`python -m pytest odin/tests/` in the project .venv on 2026-10-29:
224 passed, 1 skipped (the real-key match test this sandbox cannot read).
New coverage is in `odin/tests/test_m11_spark_format.py` (20 tests):
the format's shape for INST's and HUGINN's dictionaries, what spark
actually sends under each plan, both Director fixtures, a full COLLECT,
an ABORT and a "none" whose parameters hold only nulls passing, a
COLLECT with a null argument failing the dictionary check, a HUGINN
no-argument command, and the unchanged neighbours and frozen files.

Red cases, each planted in the real implementation, shown failing, then
restored byte for byte (SHA-256 fabd1956...e7922b verified after):
(a) a oneOf left in the format; (b) the command enum taken from the
default (HUGINN) dictionary instead of the plan's; (c) null arguments
kept inside parameters; (d) a non-null field of another form dropped
instead of kept; (e) an escalation's null proposed dropped.

## Unchanged

The three frozen files still hash as recorded, the freeze guard passes,
the six schemas and config/models.yaml are unchanged, and no contract
schema file was touched. No paid call was made; Claude Code flies a dev
run on spark after this deposit is committed.

## Suggested commit message

M11: flat plain-object ACT format for spark, derived from the dictionary in force, with nulls dropped after the call

Built-with: Muse Code (muse-wonder-1.0)
"""


def main():
    files = {}
    for path in sorted((ROOT / "odin").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    files["DEPOSIT.md"] = DEPOSIT_MD.encode("utf-8")
    manifest = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(files.items()))
    out_dir = ROOT / "to-claude-code"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / f"{NAME}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in sorted(files.items()):
            zf.writestr(name, data)
        zf.writestr("MANIFEST.sha256", manifest)
    (out_dir / f"{NAME}.DEPOSIT.md").write_bytes(files["DEPOSIT.md"])
    print(f"{zip_path} sha256:{hashlib.sha256(zip_path.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
