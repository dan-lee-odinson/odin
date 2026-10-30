"""Build deposit MC-M17-01 (AGENTS.md section 6).

Whole odin/ folder as it stands (no __pycache__), DEPOSIT.md at the top,
MANIFEST.sha256 listing every other file with its SHA-256, and an
identical copy of DEPOSIT.md beside the zip as MC-M17-01.DEPOSIT.md.
keys/odin.pub is unchanged and is not included.
Run from the workspace root: python odin/devtools/build_m17_deposit.py
"""
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "MC-M17-01"

DEPOSIT_MD = """# Deposit MC-M17-01

- Milestone: M17, one run with two models picked by seat, and the
  freeze guards checked against config/frozen.json (the Director's
  rulings of 30 October 2026, "Loop picks model by seat" and "Check
  against frozen.json"; contract/m17/README.md).
- Status: deposited as MC-M17-01.zip, 2026-10-30.
- Layout: DEPOSIT.md sits at the top of the deposit zip beside `odin/`.
  The copy beside the zip is named MC-M17-01.DEPOSIT.md so a later
  deposit cannot overwrite it, and is identical to the one inside.
  keys/odin.pub is unchanged and is not included.
- Date the Director saw it run: 2026-10-30 (test output and the
  red-case runner's output shown in session).

## The changes

1. `odin/loop/loop.py`: TurnLoop takes an optional onboard adapter.
   Each turn, `adapter_for` picks it fresh from the bundle's seat: an
   ONBOARD turn goes to the onboard adapter when the run has one, and
   anything else goes to the run's adapter, so a change of seat
   between turns switches adapter at once. The frozen instructions,
   the prompt and the answer judging are the same for both, and each
   adapter keeps its own answer format (Glimmer's format G on ACT
   turns). Every MODEL_CALL names the configuration of the adapter
   that made it, including the loop's own fallback record. The spend
   meter is shared, and each adapter reserves and settles against its
   own model's amount, as before; a stop on either stops the run.
2. `odin/run_odin.py`: an optional `--onboard <glimmer_local |
   glimmer_modal | stand_in>`. Without it, nothing changes. With it,
   ODIN refuses to start unless both models' keys are set (naming the
   missing variable, never a value, before any adapter is built), and
   builds both adapters from their frozen blocks through the same
   build_adapter path as one model today. An onboard model outside
   the three named, or a malformed argument, is refused at start.
3. `odin/tests/freeze_guard.py` (new) and the freeze guards in the
   M6, M10, M11, M12, M14, M15 and M16 tests: the whole-file SHA-256
   pin of config/models.yaml is gone. Each guard now checks every
   model's block in config/models.yaml, as canonical JSON (contract
   section 4, dates as their ISO 8601 text), against that model's
   entry in config/frozen.json, the way the harness's freeze check
   does; a block changed, an entry changed, and a model with no entry
   are all failures. The six schemas' checks stay as whole-file
   checks. The guards pass on today's config, and on it with one more
   model added together with its matching frozen entry (a test in
   test_m17_two_models.py builds exactly that pair in a temp folder).

## Tests run

`python -m pytest odin/tests/test_m17_two_models.py`: 15 passed.
`python -m pytest odin/tests/`: 373 passed, 1 skipped (the real-key
match test this sandbox cannot read). New coverage is in
`odin/tests/test_m17_two_models.py`: seat picking (ONBOARD with and
without an onboard adapter, any other seat, a seat changing between
turns), MODEL_CALL naming per turn, each adapter keeping its format
and its spend bucket with a spend stop on the onboard model stopping
the run, starting with --onboard (both keys, both adapters built,
missing-key refusals, argument shape), and the freeze guard on
today's config and on a config with an added model and entry.
Every test is local: adapter doubles, injected stubs and the
in-process FakeServices. No paid call was made, no server was run,
and no GPU was used.

Red cases: `odin/devtools/red_cases_m17.py` plants one fault at a
time, runs the covering test(s), counts only tests that ran and
failed, restores the file byte for byte and checks its hash. The
three freeze plants are planted in config/models.yaml and
config/frozen.json themselves and restored the same way; both files
hash afterwards exactly as before. Its output in session, every
plant RED OK with 0 errors: an ONBOARD turn answered by the run's
model (1 failed); a GROUND turn answered by the onboard model (2);
a MODEL_CALL naming the other model's configuration (1); ODIN
starting without the onboard model's key (2); after a change of
seat, the next turn going to the old seat's adapter (1); a model's
settings changed with its frozen entry left (1); a frozen entry
changed with the settings left (1); and a model added with no
frozen entry (1). Restored: 15 passed.

## Unchanged

The three frozen files, the six schemas and config/models.yaml are
unchanged (config/models.yaml still hashes to the value the old
guards pinned; the guard change is in how it is checked).

## Suggested commit message

M17: two models picked by seat, freeze guards against frozen.json

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
