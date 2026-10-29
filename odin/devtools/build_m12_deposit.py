"""Build deposit MC-M12-01 (AGENTS.md section 6).

Whole odin/ folder as it stands (no __pycache__), DEPOSIT.md at the top,
MANIFEST.sha256 listing every other file with its SHA-256, and an
identical copy of DEPOSIT.md beside the zip as MC-M12-01.DEPOSIT.md.
keys/odin.pub is unchanged since MC-M1-01 and is not included.
Run from the workspace root: python odin/devtools/build_m12_deposit.py
"""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "MC-M12-01"

DEPOSIT_MD = """# Deposit MC-M12-01

- Milestone: M12, a request stamped when it is signed. M11 worked in R2,
  but BALDUR-0 refused one COLLECT at ORIGIN with CLOCK_SKEW: the turn's
  two model calls took 13.4 s and 19.0 s and the request's utc, taken
  from its bundle, came out 32.5 s behind. The Director ruled: stamp it
  when signed.
- Status: deposited as MC-M12-01.zip on the Director's word, 2026-10-29.
- Layout: DEPOSIT.md sits at the top of the deposit zip beside `odin/`. The
  copy beside the zip is named MC-M12-01.DEPOSIT.md so a later deposit
  cannot overwrite it, and is identical to the one inside.
  keys/odin.pub is unchanged since MC-M1-01 and is not included.
- Date the Director saw it run: 2026-10-29 (full suite and red cases shown in session).

## The changes

1. `odin/loop/loop.py`: a COMMAND_REQUEST's utc is wall-clock taken just
   before the loop signs it (`TurnLoop._request_utc`, module `utc_now`
   in the contract's utc form), never the bundle's utc. The loop takes
   an optional `clock` (a callable returning a datetime or a
   contract-form string) so tests run on a fake clock; without one it
   reads the real wall clock. `met_s` and every other field are as
   they were, and the signature covers the new utc as before
   (`odin/loop/signing.py` is unchanged in behaviour). Reports and
   escalations keep the bundle's utc.
2. `odin/adapters/spark.py` (M11's null rule, one addition): after the
   null arguments inside an escalation's proposed parameters are
   dropped, a proposed that holds only nulls becomes null, so the
   frozen schema accepts an escalation that proposes nothing. A real
   proposed is untouched.

## Tests run

`python -m pytest odin/tests/` in the project .venv on 2026-10-29:
234 passed, 1 skipped (the real-key match test this sandbox cannot read).
New coverage is in `odin/tests/test_m12_signed_stamp.py` (10 tests):
a fake-clock turn whose model calls take 40 s still sends a request
whose utc is within a second of its sending and 40 s past the bundle's
utc; met_s and the other request fields are unchanged; the signature
verifies with the public key and fails when utc is changed after
signing; a proposed holding only nulls (three shapes, and through the
spark adapter) becomes null and passes the frozen checks, while a real
proposed is kept; and the unchanged frozen files, six schemas and
config/models.yaml.

Red cases, each planted in the real implementation, shown failing, then
restored byte for byte (SHA-256 verified after against bf694e87... for
loop.py, 57ec2071... for signing.py, c4734b06... for spark.py):
(a) the request stamped with the bundle's utc on the 40 s fake-clock
turn; (b) utc excluded from what is signed and verified, so a utc
changed after signing still verified; (c) an escalation's proposed
holding only nulls kept as an object, so the frozen schema refused it.

## Unchanged

The three frozen files still hash as recorded, the freeze guard passes,
the six schemas and config/models.yaml are unchanged, and no contract
schema file was touched. No paid call was made.

## Suggested commit message

M12: stamp each request's utc when it is signed; a proposed holding only nulls becomes null

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
