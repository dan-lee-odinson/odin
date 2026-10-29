"""Build deposit MC-M6-02 (AGENTS.md section 6).

Whole odin/ folder as it stands (no __pycache__), DEPOSIT.md at the top,
MANIFEST.sha256 listing every other file with its SHA-256, and an
identical copy of DEPOSIT.md beside the zip as MC-M6-01.DEPOSIT.md.
keys/odin.pub is unchanged since MC-M1-01 and is not included.
Run from the workspace root: python odin/devtools/build_m6_deposit.py
"""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "MC-M6-02"

DEPOSIT_MD = """# Deposit MC-M6-02

- This deposit replaces MC-M6-01. MC-M6-01 was stopped at Claude
  Code's identity scan on four made-up paths in
  odin/tests/test_m6_voice.py (the inputs to the red case for a record
  holding an absolute path). None was a real path, but the scan reads
  text. Those four paths are now built at run time from pieces, as the
  M3 canary key names are, so no file holds a user-profile path
  literally; the test still plants the same paths and fails the same
  way (its red case was shown failing again). Nothing else changed:
  the record, its sidecar, the WAV and the spend ledger are byte for
  byte as in MC-M6-01. MC-M6-01 stays where it is.

- Milestone: M6, the voice check-in. The Director's recorded check-in,
  transcribed once through Muse Voice Transcribe (U44), frozen with the
  recording's hash, and delivered as a POST /checkin body with source
  RECORDED.
- Status: deposited as MC-M6-02.zip on the Director's word, 2026-10-29.
- Layout: DEPOSIT.md sits at the top of the deposit zip beside `odin/`. The
  copy beside the zip is named MC-M6-02.DEPOSIT.md so a later deposit
  cannot overwrite it, and is identical to the one inside.
  keys/odin.pub is unchanged since MC-M1-01 and is not included.
- Date the Director saw it run: 2026-10-29; the one real transcription
  he ran himself in his own window the same day (ffmpeg 9.0.2, the
  Gyan build from winget).

## What was built

- `odin/voice/transcribe.py`: the recording's SHA-256 is checked against
  the pinned hash before anything is sent and any other file refused;
  the .m4a is converted with ffmpeg (mono 16-bit WAV at 24 kHz, run
  from the workspace root with relative paths); the price from
  config/prices.yaml's voice_transcribe entry (per audio hour, META
  stop) is reserved through the spend meter before the call and settled
  after, from Meta's reported duration when given and otherwise the
  WAV's, with the spend record naming which; a missing or malformed
  price entry refuses the call; the key comes only from META_API_KEY.
  The frozen record (canonical JSON, refusing to overwrite) holds the
  text exactly as returned, audio_sha256, wav_sha256, the exact
  conversion command, model, endpoint and utc, with its own SHA-256
  recorded in a sidecar like the instructions' freeze. A record holding
  an absolute path or a user-profile folder in any field is refused.
  The record becomes a POST /checkin body with source RECORDED that
  the fake harness accepts and checkin.schema.json validates.
- `odin/spend/meter.py`: voice_transcribe draws on the META stop and
  META_CREDIT bucket; a settle may name its duration_source.
- `odin/devtools/rewrite_m6_record.py`: the one-time rewrite below.
- Tests: `odin/tests/test_m6_voice.py`, every test against a fake
  transcriber, no network, no paid call by Muse Code.

## The real transcription and the rewrite

The Director ran the one real transcription in his own window. It
returned, exactly as Meta gave it: "Oden, this is flight report the
spacecraft condition your actions this past and anything you're
watching." The text stands exactly as returned. That record's SHA-256
was sha256:0e3b195787717a3ea6c5908aaa479a026709bc263d6306af16b99a62e4898053.

One defect: its conversion field held the ffmpeg command with absolute
paths, through his private user folder. By his ruling, only that field
was rewritten: `odin/devtools/rewrite_m6_record.py`, run once, replaced
the workspace root with "." in conversion, left every other field
exactly as it was, kept the canonical form, and wrote a new sidecar
holding "derived_from" the original's hash and one line saying only
conversion changed, and why. The rewritten record's conversion equals
byte for byte what the fixed code writes for the same run (checked).
The rewritten record, its sidecar, the WAV and the spend ledger are in
this deposit under odin/voice/. A private copy of the original record,
its sidecar and the spend ledger is kept outside the workspace.

Before this deposit was built, every file in it was checked as
before: no file holds the workspace's absolute path, a real
user-profile folder, a user name, or (now) a made-up user-profile
path literally either.

## Tests run

`python -m pytest odin/tests/` in the project .venv on 2026-10-29:
283 passed, 1 skipped (the real-key match test this sandbox cannot read).
Red cases, each planted and shown failing, then restored byte for byte:
(a) a recording with one changed byte sent; (b) an existing record
overwritten; (c) a call made without a reservation; (d) a check-in body
with source TEXT built from a recording; (e) a missing voice_transcribe
price entry accepted; (f) a record with an absolute path in a field
allowed through.

## Unchanged

The three frozen files still hash as recorded, the freeze guard passes,
the six schemas and config/models.yaml are unchanged. The one paid
call was the Director's own transcription, run by him.

## Suggested commit message

M6: voice check-in path, frozen transcript of the Director's recording, conversion paths made relative

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
