"""Build deposit MC-M15-01 (AGENTS.md section 6).

Whole odin/ folder as it stands (no __pycache__), DEPOSIT.md at the top,
MANIFEST.sha256 listing every other file with its SHA-256, and an
identical copy of DEPOSIT.md beside the zip as MC-M15-01.DEPOSIT.md.
keys/odin.pub is unchanged and is not included.
Run from the workspace root: python odin/devtools/build_m15_deposit.py
"""
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "MC-M15-01"

DEPOSIT_MD = """# Deposit MC-M15-01

- Milestone: M15, spark's regrouped answer format (the Director's
  ruling of 29 October 2026, "Regroup format, probe again";
  contract/m15/README.md).
- Status: deposited as MC-M15-01.zip, 2026-10-29.
- Layout: DEPOSIT.md sits at the top of the deposit zip beside `odin/`.
  The copy beside the zip is named MC-M15-01.DEPOSIT.md so a later
  deposit cannot overwrite it, and is identical to the one inside.
  keys/odin.pub is unchanged and is not included.
- Date the Director saw it run: 2026-10-29 (full suite and red cases
  shown in session).

## The changes

1. `odin/adapters/spark.py`: on an ACT turn spark sends the regrouped
   format, derived at call time from the dictionary in force read
   through the registry. It is format B with the escalation-only fields
   (`escalation_kind`, `refs`, `urgency` and `proposed`), as they are,
   moved into one nullable object, `escalation`. `command_call` stays
   as in B (one closed branch per command, each holding only that
   command's own arguments; an escalation's `proposed` is the same
   anyOf). `kind` and `rationale` stay at the root, in the order
   `kind`, `command_call`, `escalation`, `rationale`. For HUGINN's
   dictionary and for INST's, the built format equals
   contract/m15/format-R-HUGINN.json and format-R-INST.json as parsed
   JSON, with no oneOf, allOf, if/then or $ref anywhere. The adapter
   still hands the loop the model's text exactly as returned, so
   CANDIDATE logs it unchanged. Report turns are unchanged.
2. `odin/loop/loop.py`: in the loop's parse (`put_back_escalation`,
   `put_back_command_call` and `judge_act_text`), the `escalation`
   object's fields are put back at the root where the answer's form
   has them: a null `escalation` puts back nulls, and an `escalation`
   holding values is kept, so the frozen schema can refuse it (for
   example `refs` and `urgency` on a command answer). Then the answer
   is judged exactly as M14 judged it: `command_call` put back as
   `command` and `parameters`, M11's null drop, the frozen answer
   schema, the dictionary check and the loop. Nothing that holds a
   value is dropped.

## Tests run

`python -m pytest odin/tests/` in the project .venv on 2026-10-29:
326 passed, 1 skipped (the real-key match test this sandbox cannot
read). New coverage is in `odin/tests/test_m15_regrouped.py` (17
tests); the superseded format-shape expectations were updated to the
regrouped format in `test_m11_spark_format.py` and
`test_m14_format_b.py`, where the HUGINN bundle's sent format is again
checked exactly (against contract/m15's HUGINN file), not only as
"not INST's".

Red cases, each planted and shown failing first (the new M15 test file
failed at collection against the M14 code, and a probe showed the M14
format did not equal format R and answers-R's answers were refused):
format B sent instead of the regrouped format; the escalation's
fields left nested; an escalation holding values on a command answer
dropped instead of refused; and any of answers-R.json's ten or
escalations-R.json's five judged otherwise than recorded (all ten
answers accepted as recorded; of the five made-up escalations, three
accepted and two refused by the frozen schema, exactly as recorded).

## Unchanged

spark_open and the report turns are unchanged. The three frozen files,
the six schemas and config/models.yaml are unchanged, and the freeze
guard passes (asserted in the suite). No paid call was made. Before
building, every file in the deposit was checked to hold no absolute
path, no user-profile folder and no user name, literally: none found.

## Suggested commit message

M15: spark regrouped answer format, escalation put back in the loop

Built-with: Muse Code (muse-wonder-1.0)
"""

# Built without spelling any of them out, so this file itself holds
# no absolute path, user-profile folder or user name, literally.
_HOME_NAME = Path.home().name
_PROFILE_DIR = "Use" + "rs"
_FORBIDDEN = re.compile(
    r"[A-Za-z]:[\\/]" + _PROFILE_DIR + r"[\\/][A-Za-z][^\\/]*"
    r"|/" + _PROFILE_DIR + r"/[A-Za-z][^/]*"
    r"|\b" + re.escape(_HOME_NAME) + r"\b", re.IGNORECASE)


def main():
    files = {}
    for path in sorted((ROOT / "odin").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    files["DEPOSIT.md"] = DEPOSIT_MD.encode("utf-8")
    for name, data in sorted(files.items()):
        hit = _FORBIDDEN.search(data.decode("utf-8", errors="ignore"))
        if hit:
            raise SystemExit(f"forbidden literal {hit.group(0)!r} in {name}")
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
