"""Muse Code's deposits (00_HANDOFF.md §5; .agents/AGENTS.md §6).

Claude Code commits each deposit byte for byte and never alters Muse Code's build. These checks
recompute every committed deposit from its zip and hold the repository to it:
- the zip's files match its MANIFEST.sha256, and every payload path is odin/ or keys/odin.pub;
- odin/ (and keys/odin.pub, when the deposit carries it) at the commit that added the zip is exactly
  the zip's payload: no file missing, none extra, none changed;
- that commit changes nothing else, names the zip's SHA-256 in its Deposit line, ends with the
  Built-with line, and carries no co-author line;
- the zip in deposits/ is still the one committed;
- odin/ in the working tree is the newest deposit's, so nothing changes Muse Code's build between
  deposits.

Like the other checks, each returns a list of problems; an empty list means it passed.
"""

import hashlib
import io
import re
import subprocess
import zipfile
import zlib
from pathlib import Path

from tests.repo_checks import iter_files

DEPOSIT_NAME = re.compile(r"MC-[A-Za-z0-9]+-[0-9]{2,}\.zip")
BUILT_WITH = "Built-with: Muse Code (muse-wonder-1.0)"
METADATA = {"MANIFEST.sha256", "DEPOSIT.md"}


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True).stdout


def _in_scope(path):
    return path.startswith("odin/") or path == "keys/odin.pub"


def deposit_payload(data):
    """A deposit zip's payload, {path: bytes}, and every problem with the zip itself."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError) as error:
        return {}, [f"not a readable zip ({error})"]
    problems = []
    listed = {}
    for number, line in enumerate(files.get("MANIFEST.sha256", b"").decode("utf-8", "replace").splitlines(), 1):
        digest, _, name = line.partition("  ")
        if line.strip():
            listed[name.lstrip("*")] = digest
    if "MANIFEST.sha256" not in files:
        problems.append("no MANIFEST.sha256")
    for name, digest in sorted(listed.items()):
        if name not in files:
            problems.append(f"MANIFEST.sha256 lists {name}, which the zip lacks")
        elif hashlib.sha256(files[name]).hexdigest() != digest:
            problems.append(f"{name} does not match MANIFEST.sha256")
    for name in sorted(set(files) - set(listed) - {"MANIFEST.sha256"}):
        problems.append(f"{name} is not in MANIFEST.sha256")
    payload = {name: content for name, content in files.items() if name not in METADATA}
    problems += [f"{name} is outside Muse Code's scope" for name in sorted(payload) if not _in_scope(name)]
    return payload, problems


def committed_deposits(root):
    """(name, commit) for each deposit zip added under deposits/, oldest first."""
    found, commit = [], None
    for line in _git(root, "log", "--reverse", "--diff-filter=A", "--format=commit %H", "--name-only",
                     "--", "deposits/").decode("utf-8").splitlines():
        if line.startswith("commit "):
            commit = line.split()[1]
        elif line.startswith("deposits/") and DEPOSIT_NAME.fullmatch(line[len("deposits/"):]):
            found.append((line[len("deposits/"):], commit))
    return found


def _blob_id(root, data):
    hashing = hashlib.new(_git(root, "rev-parse", "--show-object-format").decode().strip() or "sha1")
    hashing.update(b"blob %d\0" % len(data) + data)
    return hashing.hexdigest()


def _differences(expected, actual):
    """Paths missing from, extra in or changed in actual, against expected; both {path: content id}."""
    return ([f"{path} is missing" for path in sorted(set(expected) - set(actual))]
            + [f"{path} is extra" for path in sorted(set(actual) - set(expected))]
            + [f"{path} differs" for path in sorted(set(expected) & set(actual)) if expected[path] != actual[path]])


def check_committed_deposits(root):
    root = Path(root)
    problems = []
    for name, commit in committed_deposits(root):
        where = f"deposits/{name} (commit {commit[:7]})"
        data = _git(root, "show", f"{commit}:deposits/{name}")
        payload, zip_problems = deposit_payload(data)
        problems += [f"{where}: {p}" for p in zip_problems]

        lines = _git(root, "log", "-1", "--format=%B", commit).decode("utf-8").splitlines()
        deposit_line = f"Deposit: {name} sha256:{hashlib.sha256(data).hexdigest()}"
        if deposit_line not in lines:
            problems.append(f"{where}: the commit message lacks '{deposit_line}'")
        if BUILT_WITH not in lines:
            problems.append(f"{where}: the commit message lacks '{BUILT_WITH}'")
        if any(line.lower().startswith("co-authored-by:") for line in lines):
            problems.append(f"{where}: a deposit commit carries no co-author line")

        changed = _git(root, "show", "--format=", "--name-only", commit).decode("utf-8").splitlines()
        problems += [f"{where}: the deposit commit also changes {path}"
                     for path in changed if path and path != f"deposits/{name}" and not _in_scope(path)]

        tree = {}
        for entry in _git(root, "ls-tree", "-r", "-z", commit, "--", "odin", "keys/odin.pub").split(b"\0"):
            if entry:
                meta, path = entry.split(b"\t", 1)
                tree[path.decode("utf-8")] = meta.split()[2].decode()
        expected = {path: _blob_id(root, content) for path, content in payload.items() if _in_scope(path)}
        if "keys/odin.pub" not in payload:
            tree.pop("keys/odin.pub", None)
        problems += [f"{where}: at the deposit commit, {p}" for p in _differences(expected, tree)]

        working = root / "deposits" / name
        if not working.exists():
            problems.append(f"{where}: the zip is gone from deposits/")
        elif working.read_bytes() != data:
            problems.append(f"{where}: the zip in deposits/ is not the one committed")
    return problems


def check_odin_is_the_newest_deposit(root):
    """odin/ in the working tree, and keys/odin.pub when a deposit carried one, are the newest
    deposit's: the last committed, or one copied into deposits/ and not yet committed."""
    root = Path(root)
    committed = [name for name, _ in committed_deposits(root)]
    pending = sorted(p.name for p in (root / "deposits").glob("MC-*.zip")
                     if DEPOSIT_NAME.fullmatch(p.name) and p.name not in committed)
    order = committed + pending
    if not order:
        return ["odin/ exists but no deposit does"] if (root / "odin").exists() else []
    payloads = {name: deposit_payload((root / "deposits" / name).read_bytes())[0] for name in order}
    newest = payloads[order[-1]]
    expected = {path: hashlib.sha256(content).hexdigest() for path, content in newest.items()
                if path.startswith("odin/")}
    actual = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in iter_files(root / "odin")}
    problems = [f"odin/ is not {order[-1]}'s: {p}" for p in _differences(expected, actual)]
    with_key = [name for name in order if "keys/odin.pub" in payloads[name]]
    if with_key:
        key = root / "keys" / "odin.pub"
        if not key.exists() or key.read_bytes() != payloads[with_key[-1]]["keys/odin.pub"]:
            problems.append(f"keys/odin.pub is not {with_key[-1]}'s")
    return problems
