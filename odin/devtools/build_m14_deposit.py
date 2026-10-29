"""Build deposit MC-M14-01 (AGENTS.md section 6).

Whole odin/ folder as it stands (no __pycache__), DEPOSIT.md at the top,
MANIFEST.sha256 listing every other file with its SHA-256, and an
identical copy of DEPOSIT.md beside the zip as MC-M14-01.DEPOSIT.md.
keys/odin.pub is unchanged and is not included.
Run from the workspace root: python odin/devtools/build_m14_deposit.py
"""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "MC-M14-01"

DEPOSIT_MD = """# Deposit MC-M14-01

- Milestone: M14, spark's answer format B, the exact log and
  spark_open's amended answer rule (contract section 11.1 as amended
  29 October 2026, AGENTS.md line 71, contract/m14/README.md).
- Status: deposited as MC-M14-01.zip, 2026-10-29.
- Layout: DEPOSIT.md sits at the top of the deposit zip beside `odin/`.
  The copy beside the zip is named MC-M14-01.DEPOSIT.md so a later
  deposit cannot overwrite it, and is identical to the one inside.
  keys/odin.pub is unchanged and is not included.
- Date the Director saw it run: 2026-10-29 (full suite and red cases
  shown in session).

## The changes

1. `odin/adapters/spark.py`: on an ACT turn spark sends format B,
   derived at call time from the dictionary in force read through the
   registry. `command` and `parameters` give way to `command_call`, an
   anyOf with one closed branch per command holding that command's name
   as a one-value enum and only its own arguments typed as before; a
   command with no arguments gets an empty closed object. An
   escalation's `proposed` is the same anyOf. Every other field is as
   in M11's format. For HUGINN's dictionary and for INST's, the built
   format equals contract/m14/format-B-HUGINN.json and
   format-B-INST.json as parsed JSON, with no oneOf, allOf, if/then or
   $ref anywhere. The adapter now hands the loop the model's text
   exactly as returned, never re-serialized, so CANDIDATE logs it
   unchanged. Report turns are unchanged.
2. `odin/loop/loop.py`: in the loop's parse (`put_back_command_call`
   and `judge_act_text`), `command_call` is put back as `command` and
   `parameters`, then M11's null drop (`drop_nulls`, in M11's order),
   then the frozen schema, the dictionary check and the loop judge the
   answer. Nothing repairs or drops an argument a command does not
   take, and a non-null field of another form (such as `urgency` on a
   command answer) is kept so the frozen schema refuses it. ANSWER
   records the judged form, MALFORMED's reason comes from it, and the
   judged form is reproducible from CANDIDATE by this same rule.
3. `odin/adapters/spark_open.py`: per contract section 11.1 as
   amended, if the turn ends with exactly one answer-tool call that
   call is the answer; if it ends with no answer-tool call, the
   message content with surrounding whitespace trimmed must parse as
   exactly one JSON object and that object is the answer; anything
   else (prose, a code fence, two objects, more than one answer-tool
   call, wrong fields) is MALFORMED. `reasoning_content` is never the
   answer. CANDIDATE has channel MESSAGE and its raw holds the final
   message's content and tool calls exactly as returned. Report turns
   are unchanged. Its answer tools are now typed from the frozen
   forms: the section 7.1 answer forms and the section 7.5 report
   body, $refs resolved from the frozen schema files at load.
4. `odin/devtools/m3_check.py` judges spark through the loop's parse
   and spark_open through the amended message rule, as the adapters
   now return them.

## Tests run

`python -m pytest odin/tests/` in the project .venv on 2026-10-29:
309 passed, 1 skipped (the real-key match test this sandbox cannot
read). New coverage is in `odin/tests/test_m14_format_b.py` (27 tests),
with the superseded M11/M12/M3 expectations updated to M14 in
`test_m11_spark_format.py`, `test_m12_signed_stamp.py` and
`test_m3_adapters.py`.

Red cases, each planted and shown failing first (the new M14 test file
failed at collection against the M13 code, and a probe showed the old
shared-argument format did not equal format B): M11's shared-argument
format sent on an ACT turn; format B built from a dictionary other
than the one in force; a command answer pairing CMD_PLD_SET_STATE
with `rate` passing validation against format B; an argument the
command does not take dropped instead of refused; CANDIDATE
re-serialized instead of exact; each of answers-B.json's four judged
otherwise than recorded (three accepted, the one with `urgency`
refused by the frozen schema); and for spark_open, accepting a code
fence, two objects, prose around an object, two answer-tool calls, or
an answer in `reasoning_content` with empty content.

## Unchanged

The three frozen files, the six schemas and config/models.yaml are
unchanged, and the freeze guard passes (asserted in the suite). No
paid call was made.

## Suggested commit message

M14: spark format B, exact CANDIDATE log, spark_open message answer rule

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
