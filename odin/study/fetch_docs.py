"""Fetch OpenC3 COSMOS docs pinned to tag v7.2.1 (AGENTS §4.4).

Writes the docs.openc3.com/docs tree to cache/cosmos-docs-7.2.1/ (read by
Claude Code's docs lookup as well) and records every file's SHA-256 in
odin/study/cosmos_docs_hashes.json. The repository keeps this script and
the hash list, never the docs.
"""
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

TAG = "v7.2.1"
REPO_URL = "https://github.com/OpenC3/cosmos.git"
DOCS_SUBPATH = "docs.openc3.com/docs"
REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "cache" / "cosmos-docs-7.2.1"
HASH_LIST = Path(__file__).resolve().parent / "cosmos_docs_hashes.json"


def clone_command(dest) -> list:
    return ["git", "clone", "--depth", "1", "--branch", TAG, REPO_URL, str(dest)]


def _entries(tree: Path) -> list:
    entries = []
    for path in sorted(tree.rglob("*")):
        if path.is_file():
            entries.append({
                "path": path.relative_to(tree).as_posix(),
                "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    return entries


def fetch_tree(source_tree, cache_dir, hash_list_path=None, license_file=None,
               record: bool = True) -> list:
    """Copy a docs tree into the cache, including docs.openc3.com/LICENSE.md
    beside the tree. The hash list is written only when record=True and a
    path is given; a plain script run never writes it (M7 fix 1)."""
    source_tree, cache_dir = Path(source_tree), Path(cache_dir)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    shutil.copytree(source_tree, cache_dir)
    if license_file is not None:
        shutil.copyfile(license_file, cache_dir / "LICENSE.md")
    entries = _entries(cache_dir)
    if record and hash_list_path is not None:
        Path(hash_list_path).write_text(
            json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return entries


def verify_hashes(cache_dir, hash_list_path) -> list:
    """Problems list; empty when every file matches the recorded list."""
    cache_dir = Path(cache_dir)
    recorded = json.loads(Path(hash_list_path).read_text(encoding="utf-8"))
    problems = []
    for entry in recorded:
        target = cache_dir / entry["path"]
        if not target.exists():
            problems.append(f"{entry['path']}: missing")
        elif "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
            problems.append(f"{entry['path']}: hash mismatch")
    return problems


def check_tree(cache_dir, hash_list_path) -> list:
    """Full check (fetch --verify plus extras): every recorded file present
    and matching, and no extra file in the tree."""
    problems = verify_hashes(cache_dir, hash_list_path)
    recorded = {e["path"] for e in json.loads(
        Path(hash_list_path).read_text(encoding="utf-8"))}
    actual = {e["path"] for e in _entries(Path(cache_dir))}
    for extra in sorted(actual - recorded):
        problems.append(f"{extra}: not in recorded list")
    return problems


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="fetch_docs")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--write-hashes", action="store_true",
                        help="write a new recorded hash list (refused if one exists)")
    parser.add_argument("--source", default=None,
                        help="existing clone to copy from instead of cloning")
    args = parser.parse_args(argv)
    if args.verify:
        problems = check_tree(CACHE_DIR, HASH_LIST)
        print("hash check:", "OK" if not problems else problems)
        return 0 if not problems else 1
    if args.write_hashes and HASH_LIST.exists():
        print(f"refusing to overwrite the recorded hash list: {HASH_LIST}")
        return 2

    def _fetch(clone_root):
        return fetch_tree(Path(clone_root) / DOCS_SUBPATH, CACHE_DIR, HASH_LIST,
                          license_file=Path(clone_root) / "docs.openc3.com" / "LICENSE.md",
                          record=args.write_hashes)

    if args.source:
        entries = _fetch(args.source)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(clone_command(tmp), check=True)
            entries = _fetch(tmp)
    total = sum((CACHE_DIR / e["path"]).stat().st_size for e in entries)
    print(f"fetched {len(entries)} files ({total} bytes) at {TAG} into {CACHE_DIR}")
    if args.write_hashes:
        print(f"recorded hash list written: {HASH_LIST}")
        return 0
    # A plain run checks the cache against the recorded list, never writes it.
    if not HASH_LIST.exists():
        print(f"no recorded hash list at {HASH_LIST}; run with --write-hashes first")
        return 1
    problems = check_tree(CACHE_DIR, HASH_LIST)
    print("hash check:", "OK" if not problems else problems)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
