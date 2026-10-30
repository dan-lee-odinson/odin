"""Build deposit MC-M16-01 (AGENTS.md section 6).

Whole odin/ folder as it stands (no __pycache__), DEPOSIT.md at the top,
MANIFEST.sha256 listing every other file with its SHA-256, and an
identical copy of DEPOSIT.md beside the zip as MC-M16-01.DEPOSIT.md.
keys/odin.pub is unchanged and is not included.
Run from the workspace root: python odin/devtools/build_m16_deposit.py
"""
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "MC-M16-01"

DEPOSIT_MD = """# Deposit MC-M16-01

- Milestone: M16, Glimmer's own answer format G (the Director's
  rulings of 30 October 2026, "Low, tie type to command" and
  "Approve, but a 60 s timeout"; contract/m16/README.md).
- Status: deposited as MC-M16-01.zip, 2026-10-30.
- Layout: DEPOSIT.md sits at the top of the deposit zip beside `odin/`.
  The copy beside the zip is named MC-M16-01.DEPOSIT.md so a later
  deposit cannot overwrite it, and is identical to the one inside.
  keys/odin.pub is unchanged and is not included.
- Date the Director saw it run: 2026-10-30 (test output and the
  red-case runner's output shown in session).

## The changes

1. `odin/adapters/spark.py`: a new `act_format_g` builds format G from
   the dictionary in force -- three closed objects under one anyOf,
   one per kind, each keeping R's four fields in R's order, a field
   the kind does not allow kept and required null, and an
   escalation's own fields never null (proposed a command or null),
   exactly as contract/m16's two format files as parsed JSON. Spark
   sends it through a new `_act_format` hook that spark itself leaves
   at format R; spark's and spark_open's formats are unchanged.
2. `odin/adapters/glimmer_common.py` (new): the shared Glimmer call
   sequence. Both Glimmer adapters send format G on ACT turns (REPORT
   turns unchanged), and the loop's M15 put-backs, null drop, frozen
   schema and dictionary check judge the answer exactly as before;
   CANDIDATE stays the model's exact text. A call runs on its own
   thread: if it is still open at the adapter's timeout, the adapter
   asks the same server's /slots, with the same headers and while the
   call is still open, whether it is processing. Only that flag is
   kept -- the MODEL_CALL is logged with status TIMEOUT and the call's
   latency when the server says processing, and ERROR for anything
   else (no answer, refused, not processing). Nothing else /slots
   returns is stored or written anywhere.
3. `odin/adapters/glimmer_modal.py`: now a GlimmerAdapter. Its
   endpoint comes from glimmer_modal's model block in configuration
   (settings entry, or the constructor in tests); the old M5-prep
   endpoint file is never read, and an adapter given no endpoint
   refuses naming the missing endpoint. Modal-Key/Modal-Secret are
   still read from ODIN_MODAL_PROXY_KEY/ODIN_MODAL_PROXY_SECRET at
   call time, never logged or written, and the GPU-second charging
   against the $125 Modal stop is unchanged.
4. `odin/adapters/glimmer_local.py`: rewritten as a GlimmerAdapter
   (it was a stub that always refused). Same weights, same format G,
   same /slots timeout flag, no key; its endpoint comes from
   configuration, with the local llama.cpp serve address as the
   replaceable default. `odin/adapters/settings.py` passes a Glimmer
   entry's endpoint and model from its block.
5. Tests superseded and updated: the two M5 expectations (Glimmer now
   sends G, and the endpoint no longer comes from the old file).

## Tests run

`python -m pytest odin/tests/test_m16_format_g.py`: 17 passed.
`python -m pytest odin/tests/`: 358 passed, 1 skipped (the real-key
match test this sandbox cannot read). New coverage is in
`odin/tests/test_m16_format_g.py`: format G equal to both contract
files as parsed JSON and sent by both Glimmer adapters (and not by
spark or spark_open); all 9 answers in answers-G.json, all 10 in
escalations-G.json and all 36 in checks-G.json judged and admitted
exactly as recorded; the endpoint from a test model block (reasoning
low, 8192, 60 s); the timeout flag through a loop run; CANDIDATE
exact; and the freeze guard. Every test is local: injected stubs and
the in-process FakeServices. No paid call was made, no server was
run, and no GPU was used.

Red cases: `odin/devtools/red_cases_m16.py` plants one fault at a
time, runs the covering test(s), counts only tests that ran and
failed, restores the file byte for byte and checks its hash, then
runs the whole M16 file green. Its output in session, every plant
RED OK with 0 errors: format R sent to Glimmer instead of G (2
failed); spark sent G (1); spark_open sent a json_schema format (1);
the escalation put-back dropped, so answers judged otherwise than
recorded (3); the endpoint read from the old file (1); a timeout
logged as ERROR while processing (1); a timeout logged as TIMEOUT
when not processing (1 failed, 1 passed of the pair); /slots asked
only after the call was dropped (1); and a key's value written into
the MODEL_CALL usage the run logs (1). Restored: 17 passed.

## Unchanged

The three frozen files, the six schemas and config/models.yaml are
unchanged, and the freeze guard passes (asserted in the suite).

## Suggested commit message

M16: Glimmer format G, model-block endpoint, /slots timeout flag

Built-with: Muse Code (muse-wonder-1.0)
"""

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
