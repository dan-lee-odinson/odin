"""Build deposit MC-M5-02 (AGENTS.md section 6).

Whole odin/ folder as it stands (no __pycache__), DEPOSIT.md at the top,
MANIFEST.sha256 listing every other file with its SHA-256, and an
identical copy of DEPOSIT.md beside the zip as MC-M5-02.DEPOSIT.md.
keys/odin.pub is unchanged and is not included. MC-M5-01 stays as it is.
Run from the workspace root: python odin/devtools/build_m5_02_deposit.py
"""
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "MC-M5-02"

DEPOSIT_MD = """# Deposit MC-M5-02

- Milestone: M5 prep, the glimmer_modal adapter (Muse Glimmer 30B on
  Modal, the onboard seat's fallback; CONTRACT.md section 11.1,
  AGENTS.md section 4.2, the Director's message for M5's prep).
  M5's timing (section 4.6) is run by Claude Code this time, at the
  Director's ruling of 29 October 2026.
- Status: deposited as MC-M5-02.zip, 2026-10-30. This deposit adds the
  planted red-case runner the Director asked for after MC-M5-01; the
  M5 prep code itself is unchanged from MC-M5-01. MC-M5-01 is left
  where it is.
- Layout: DEPOSIT.md sits at the top of the deposit zip beside `odin/`.
  The copy beside the zip is named MC-M5-02.DEPOSIT.md so a later
  deposit cannot overwrite it, and is identical to the one inside.
  keys/odin.pub is unchanged and is not included.
- Date the Director saw it run: 2026-10-30 (test output with its red
  cases shown in session, then the runner's output shown in session).

## The changes

1. `odin/adapters/glimmer_modal.py` (new): Muse Glimmer 30B on Modal
   behind Modal's proxy auth. It is spark's call sequence with Modal's
   endpoint, headers and charging: POST <endpoint>/v1/chat/completions,
   OpenAI-compatible, with the endpoint read from
   config/glimmer_modal.yaml, and a response_format of type json_schema
   on ACT and REPORT turns exactly as spark sends. The loop judges the
   answer through the same validator and logs CANDIDATE exactly as for
   spark. Every request carries the Modal-Key and Modal-Secret headers,
   read from ODIN_MODAL_PROXY_KEY and ODIN_MODAL_PROXY_SECRET at call
   time; a missing variable is refused naming the variable, never its
   value, and the values are never logged, printed or written. The
   adapter only ever sends that chat request: it imports no Modal
   library and has no code path that starts, warms or stops a server.
   Reasoning level, output cap and timeout come from configuration, as
   for every model; given none, it raises. Glimmer's frozen model block
   comes after M5, so the tests use a test configuration and
   config/models.yaml is untouched.
2. `odin/spend/meter.py`: STOPS["MODAL"] is 125.0, and glimmer_modal
   maps to the MODAL stop and the MODAL_CREDIT bucket. The new
   gpu_cost() charges at per_gpu_second from config/prices.yaml: the
   reservation for a call is its timeout in GPU-seconds (the worst
   case), the settled charge is its measured wall time in
   GPU-seconds, and a call whose reserved charge would pass $125 is
   refused (SPEND_STOP) before anything is sent. M2's modal-stop test
   was updated from the superseded $12 figure to $125.
3. `odin/adapters/settings.py`: glimmer_modal is a known configuration;
   build_adapter builds it from a settings entry (a test configuration
   holding only glimmer_modal is accepted; its `model` is optional and
   becomes the served model id when given).
4. `odin/run_odin.py`: `python -m odin.run_odin glimmer_modal` starts
   it with the same start checks as the other models, plus a refusal
   naming ODIN_MODAL_PROXY_KEY or ODIN_MODAL_PROXY_SECRET when either
   is missing, before any adapter is built.

## Tests run

`python -m pytest odin/tests/test_m5_glimmer_modal.py`: 15 passed.
`python -m pytest odin/tests/`: 341 passed, 1 skipped (the real-key
match test this sandbox cannot read). New coverage is in
`odin/tests/test_m5_glimmer_modal.py`. Every test talks only to a
local stub: this sandbox forbids listening sockets, so the stub is
injected as the adapter's http_post and records url, headers and body
exactly as a server would see them; the harness, log and BALDUR-0
doubles are the in-process FakeServices. No paid call was made, no
Glimmer or Modal server was run, and no GPU was used.

Red cases: `odin/devtools/red_cases_m5.py` plants one fault at a
time in the real source, runs the one M5 test that covers it, counts
only tests that ran and failed (a collection failure or an error
does not count), restores the file byte for byte and checks its hash,
then runs the whole M5 file green at the end. Its output in session:
each plant ran and failed with 0 errors, and the restored file is
15 passed. The plants: a URL other than the configured endpoint; the
Modal-Secret header dropped; a response_format that is not
json_schema; a proxy value put into the MODEL_CALL log record's
provider; the start check for a missing proxy variable disabled (2
parametrised tests ran and failed); the charge computed per call
instead of per GPU-second; the Modal stop raised so a call past $125
is allowed; and a planted `server.start()` code path in the adapter.

## Unchanged

config/models.yaml, the three frozen files and the six schemas are
unchanged, and the freeze guard passes (asserted in the suite).

## Suggested commit message

M5 prep: glimmer_modal adapter with planted red-case runner

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
