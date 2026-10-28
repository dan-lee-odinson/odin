"""Refresh Muse Code's workspace with the shared files as they are on main (00_HANDOFF.md §5).

    python tools/refresh_workspace.py            copy from main, then check every file
    python tools/refresh_workspace.py --check    check only; copy nothing

Copies .agents/AGENTS.md, CONTRACT.md, config/, keys/, contract/schemas/, the Director's recorded
check-in in checkins/ (his ruling of 28 October 2026, for Muse Code's M6) and HUGINN's
deps/huginn/defs/tlm_cmd.yaml from the main branch, not from the working tree, into
%USERPROFILE%\\Documents\\ad-astra-simul\\odin byte for byte, then reads every copy back and checks its
SHA-256 against main's. Exits 1 on any mismatch.

Nothing is written into Muse Code's odin/, to-claude-code/, cache/ or runs/, and nothing in the
workspace is deleted: a file there that main does not have is reported. keys/odin.pub is Muse Code's
own (its scope is odin/ and keys/odin.pub, 00_HANDOFF.md §5): it reaches main through Muse Code's
deposits, so it is checked but never overwritten, and a difference is reported as a mismatch.
"""

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = Path.home() / "Documents" / "ad-astra-simul" / "odin"
SHARED = (".agents/AGENTS.md", "CONTRACT.md", "config", "keys", "contract/schemas", "checkins")
HUGINN_FILE = ("deps/huginn", "defs/tlm_cmd.yaml")
MUSE_FOLDERS = ("odin", "to-claude-code", "cache", "runs")
MUSE_FILES = ("keys/odin.pub",)


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def files_on(ref="main", repo=REPO_ROOT, shared=SHARED, huginn_file=HUGINN_FILE):
    """{path: bytes} for the shared files as they are at ref, HUGINN's at the commit ref pins."""
    names = _git(repo, "ls-tree", "-r", "--name-only", "-z", ref, "--", *shared).decode("utf-8").split("\0")
    files = {name: _git(repo, "cat-file", "blob", f"{ref}:{name}") for name in names if name}
    if huginn_file is not None:
        submodule, inside = huginn_file
        mode, kind, commit = _git(repo, "ls-tree", ref, submodule).decode("utf-8").split("\t")[0].split()
        if kind != "commit":
            raise ValueError(f"{submodule} is not a submodule at {ref}")
        files[f"{submodule}/{inside}"] = _git(Path(repo) / submodule, "cat-file", "blob", f"{commit}:{inside}")
    return files


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _target(workspace, name):
    if name.split("/")[0] in MUSE_FOLDERS:
        raise ValueError(f"refused: {name} is in Muse Code's {name.split('/')[0]}/, which is never written")
    return Path(workspace) / name


def refresh(files, workspace=WORKSPACE):
    """Write each file whose copy is missing or differs. Returns {path: ADDED or CHANGED} for those."""
    for name in files:
        _target(workspace, name)   # every path is checked before anything is written
    written = {}
    for name, data in sorted(files.items()):
        if name in MUSE_FILES:
            continue
        target = _target(workspace, name)
        before = target.read_bytes() if target.is_file() else None
        if before == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written[name] = "ADDED" if before is None else "CHANGED"
    return written


def check(files, workspace=WORKSPACE):
    """Every copy read back and compared with main by SHA-256. Returns the problems."""
    problems = []
    for name, data in sorted(files.items()):
        target = _target(workspace, name)
        if not target.is_file():
            problems.append(f"{name}: missing from the workspace")
        elif digest(target.read_bytes()) != digest(data):
            mine = " (Muse Code's own file, never overwritten)" if name in MUSE_FILES else ""
            problems.append(f"{name}: {digest(target.read_bytes())} in the workspace, {digest(data)} on main{mine}")
    return problems


def extras(files, workspace=WORKSPACE, shared=SHARED):
    """Files in the workspace's shared folders that main does not have. Reported, never deleted."""
    found = []
    for part in shared:
        folder = Path(workspace) / part
        if folder.is_dir():
            found += [p.relative_to(workspace).as_posix() for p in folder.rglob("*") if p.is_file()]
    return sorted(set(found) - set(files))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="check only; copy nothing")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--workspace", type=Path, default=WORKSPACE)
    args = parser.parse_args(argv)
    if not args.workspace.is_dir():
        sys.exit(f"no workspace at {args.workspace}")
    files = files_on(args.ref)
    commit = _git(REPO_ROOT, "rev-parse", "--short", args.ref).decode().strip()
    if not args.check:
        written = refresh(files, args.workspace)
        for name, how in written.items():
            print(f"  {how:7}  {name}")
        print(f"{len(written)} of {len(files)} shared files written from {args.ref} ({commit}); "
              f"{len(files) - len(written)} were already identical")
    for name in extras(files, args.workspace):
        print(f"  NOT ON {args.ref}  {name} (left as it is)")
    problems = check(files, args.workspace)
    for problem in problems:
        print(f"  MISMATCH {problem}")
    print(f"checked {len(files)} files by SHA-256: " + ("all match " + args.ref if not problems
                                                       else f"{len(problems)} do not match"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
