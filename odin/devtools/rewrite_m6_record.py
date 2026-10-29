"""Rewrite the M6 frozen record's conversion field, once.

The Director's real transcription wrote the ffmpeg command with
absolute paths, which include his private user folder; nothing in a
deposit may hold such a path. This script replaces the workspace root
in `conversion` with ".", leaving every other field byte for byte,
keeps the canonical form, and writes a new sidecar recording what
changed and why. It refuses if the record's hash is not the original's,
or if any field but conversion would change. The old record and
sidecar are removed only after the new ones are written (to temporary
names in the same folder, then moved into place).

Run once from the workspace root:
    python odin/devtools/rewrite_m6_record.py
"""
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from odin.loop.canonical import canonical_json, sha256_tag
ORIGINAL_SHA256 = "sha256:0e3b195787717a3ea6c5908aaa479a026709bc263d6306af16b99a62e4898053"
NOTE = ("Only conversion changed: the workspace root in the ffmpeg command "
        "was replaced with \".\", because the original held an absolute path "
        "through a private user folder, which no deposit may hold.")


def rewritten(old: dict, root: str) -> dict:
    """The record with only `conversion` rewritten; refuses otherwise."""
    if root not in old.get("conversion", ""):
        raise RuntimeError("conversion does not contain the workspace root; refusing to rewrite")
    new = dict(old)
    new["conversion"] = old["conversion"].replace(root, ".")
    for field in old:
        if field != "conversion" and new[field] != old[field]:
            raise RuntimeError(f"field {field!r} would change; refusing to rewrite")
    return new


def run(*, record_path, root=None, expected_sha256=ORIGINAL_SHA256):
    """Rewrite the record at `record_path`. Returns (record, sidecar)."""
    record_path = Path(record_path)
    root = str(REPO_ROOT) if root is None else root
    data = record_path.read_bytes()
    actual = sha256_tag(data)
    if actual != expected_sha256:
        raise RuntimeError(f"record hashes to {actual}, expected {expected_sha256}; refusing")
    old = json.loads(data)
    new = rewritten(old, root)
    sidecar_path = record_path.with_suffix(".sha256.json")
    sidecar = {"file": record_path.name, "sha256": sha256_tag(canonical_json(new)),
               "frozen": True, "frozen_at_utc": new["utc"],
               "derived_from": expected_sha256, "note": NOTE}
    new_record_tmp = record_path.with_suffix(".json.new")
    new_sidecar_tmp = sidecar_path.with_suffix(".json.new")
    new_record_tmp.write_bytes(canonical_json(new))
    new_sidecar_tmp.write_bytes((json.dumps(sidecar, indent=2) + "\n").encode("utf-8"))
    # New files are written; only now are the old ones removed.
    record_path.unlink()
    if sidecar_path.exists():
        sidecar_path.unlink()
    new_record_tmp.rename(record_path)
    new_sidecar_tmp.rename(sidecar_path)
    return new, sidecar


def main() -> int:
    record, sidecar = run(
        record_path=Path(__file__).resolve().parents[1] / "voice" / "flight_director_command.json")
    print(f"record sha256: {sidecar['sha256']}")
    print(f"conversion: {record['conversion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
