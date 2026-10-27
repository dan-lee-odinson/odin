"""Each committed Muse Code deposit, recomputed from its zip, is odin/ at its commit, and the working
tree's odin/ is the newest deposit's (00_HANDOFF.md §5, step 5; .agents/AGENTS.md §6).

The red cases build a scratch git repository, commit a deposit the way §5 does, then change one
thing; the checks must fail. The greens show what the checks allow: several deposits in turn, a
deposit copied in but not yet committed, and Python's caches beside Muse Code's files.
"""

import hashlib
import io
import subprocess
import zipfile

import pytest

from tests.deposit_checks import (BUILT_WITH, check_committed_deposits, check_odin_is_the_newest_deposit,
                                  committed_deposits)
from tests.repo_checks import REPO_ROOT


def test_each_committed_deposit_is_odin_at_its_commit():
    assert committed_deposits(REPO_ROOT), "no deposit found in the history"
    assert check_committed_deposits(REPO_ROOT) == []


def test_odin_is_the_newest_deposit():
    assert check_odin_is_the_newest_deposit(REPO_ROOT) == []


# A scratch repository and deposits made the way §5 does.

PAYLOAD = {
    "odin/__init__.py": b"",
    "odin/loop/loop.py": b"def turn():\n    return 'one answer, one request'\n",
    "keys/odin.pub": b"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPlaceholderForTestsOnly000000000000000000 odin\n",
}


def make_zip(payload, *, manifest=None, extra=None):
    files = {**payload, "DEPOSIT.md": b"# Deposit\n"}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        listing = "".join(f"{hashlib.sha256(c).hexdigest()}  {n}\n" for n, c in files.items())
        archive.writestr("MANIFEST.sha256", manifest if manifest is not None else listing)
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


class Repo:
    def __init__(self, path):
        self.path = path
        path.mkdir(parents=True)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write("README.md", b"scratch\n")
        self.commit("start")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.path), *args], capture_output=True, check=True).stdout

    def write(self, rel, data):
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def deposit(self, name, payload=PAYLOAD, *, zip_data=None, odin=None, message=None, also=None):
        """Copy the zip into deposits/, replace odin/ (and keys/odin.pub) with its payload, and commit."""
        data = zip_data if zip_data is not None else make_zip(payload)
        self.write(f"deposits/{name}", data)
        for old in sorted((self.path / "odin").rglob("*"), reverse=True) if (self.path / "odin").exists() else []:
            old.unlink() if old.is_file() else old.rmdir()
        tree = odin if odin is not None else {p: c for p, c in payload.items() if p.startswith("odin/")}
        for rel, content in tree.items():
            self.write(rel, content)
        if "keys/odin.pub" in payload:
            self.write("keys/odin.pub", payload["keys/odin.pub"])
        for rel, content in (also or {}).items():
            self.write(rel, content)
        digest = hashlib.sha256(data).hexdigest()
        self.commit(message if message is not None else f"M1: test deposit\n\n{BUILT_WITH}\nDeposit: {name} sha256:{digest}")
        return data


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo")


def both(repo):
    return check_committed_deposits(repo.path) + check_odin_is_the_newest_deposit(repo.path)


# Greens

def test_a_deposit_made_as_s5_says_passes(repo):
    repo.deposit("MC-M1-01.zip")
    assert both(repo) == []


def test_a_later_deposit_replaces_odin_and_removed_files_go(repo):
    repo.deposit("MC-M1-01.zip")
    second = {"odin/__init__.py": b"", "odin/loop/turn.py": b"# renamed\n"}
    repo.deposit("MC-M1-02.zip", second)
    assert both(repo) == []
    assert not (repo.path / "odin" / "loop" / "loop.py").exists()


def test_a_deposit_copied_in_but_not_yet_committed_passes(repo):
    repo.deposit("MC-M1-01.zip")
    repo.write("deposits/MC-M1-02.zip", make_zip({"odin/__init__.py": b"# two\n"}))
    (repo.path / "odin" / "loop" / "loop.py").unlink()
    repo.write("odin/__init__.py", b"# two\n")
    assert both(repo) == []


def test_python_caches_beside_muse_codes_files_are_ignored(repo):
    repo.deposit("MC-M1-01.zip")
    repo.write("odin/loop/__pycache__/loop.cpython-314.pyc", b"\x00cache")
    assert check_odin_is_the_newest_deposit(repo.path) == []


# Red cases: the deposit commit not as the zip is

def _changed_byte(content):
    return content[:4] + bytes([content[4] ^ 0x01]) + content[5:]


COMMITTED = {
    "one byte of an odin/ file changed at the deposit commit": lambda r: r.deposit("MC-M1-01.zip", odin={
        "odin/__init__.py": b"", "odin/loop/loop.py": _changed_byte(PAYLOAD["odin/loop/loop.py"])}),
    "a file left out of odin/": lambda r: r.deposit("MC-M1-01.zip", odin={"odin/__init__.py": b""}),
    "a file added to odin/": lambda r: r.deposit("MC-M1-01.zip", odin={
        **{p: c for p, c in PAYLOAD.items() if p.startswith("odin/")}, "odin/helper.py": b"# not Muse's\n"}),
    "keys/odin.pub not the deposit's": lambda r: r.deposit("MC-M1-01.zip", also={"keys/odin.pub": b"ssh-ed25519 AAAAother odin\n"}),
    "the Deposit line naming another hash": lambda r: r.deposit(
        "MC-M1-01.zip", message=f"M1: test\n\n{BUILT_WITH}\nDeposit: MC-M1-01.zip sha256:{'0' * 64}"),
    "no Built-with line": lambda r: r.deposit(
        "MC-M1-01.zip", message="M1: test\n\nDeposit: MC-M1-01.zip sha256:" + hashlib.sha256(make_zip(PAYLOAD)).hexdigest()),
    "a co-author line": lambda r: r.deposit(
        "MC-M1-01.zip", message=f"M1: test\n\n{BUILT_WITH}\nDeposit: MC-M1-01.zip sha256:"
        + hashlib.sha256(make_zip(PAYLOAD)).hexdigest() + "\n\nCo-Authored-By: Claude <noreply@anthropic.com>"),
    "the deposit commit also changing README.md": lambda r: r.deposit("MC-M1-01.zip", also={"README.md": b"changed\n"}),
    "a file that does not match MANIFEST.sha256": lambda r: r.deposit(
        "MC-M1-01.zip", zip_data=make_zip(PAYLOAD, manifest=f"{'0' * 64}  odin/__init__.py\n")),
    "a file not in MANIFEST.sha256": lambda r: r.deposit(
        "MC-M1-01.zip", zip_data=make_zip(PAYLOAD, extra={"odin/unlisted.py": b"# unlisted\n"})),
    "a path outside Muse Code's scope": lambda r: r.deposit(
        "MC-M1-01.zip", {**PAYLOAD, "gateway/decide.py": b"# not Muse Code's to write\n"}),
    "a zip that cannot be read": lambda r: r.deposit("MC-M1-01.zip", zip_data=b"PK\x03\x04 not a zip"),
}


@pytest.mark.parametrize("case", COMMITTED)
def test_red_the_committed_deposit_check_catches(repo, case):
    COMMITTED[case](repo)
    assert check_committed_deposits(repo.path) != []


def _flip_working_zip(repo):
    repo.deposit("MC-M1-01.zip")
    zip_path = repo.path / "deposits" / "MC-M1-01.zip"
    data = bytearray(zip_path.read_bytes())
    data[len(data) // 2] ^= 0x01
    zip_path.write_bytes(bytes(data))


AFTERWARDS = {
    "the zip in deposits/ changed after its commit": (_flip_working_zip, check_committed_deposits),
    "the zip deleted from deposits/": (
        lambda r: (r.deposit("MC-M1-01.zip"), (r.path / "deposits" / "MC-M1-01.zip").unlink()),
        check_committed_deposits),
    "a later commit changing odin/": (
        lambda r: (r.deposit("MC-M1-01.zip"), r.write("odin/loop/loop.py", b"# edited\n"), r.commit("tidy")),
        check_odin_is_the_newest_deposit),
    "an uncommitted edit to odin/": (
        lambda r: (r.deposit("MC-M1-01.zip"), r.write("odin/loop/loop.py", b"# edited\n")),
        check_odin_is_the_newest_deposit),
    "a file added to odin/ in the working tree": (
        lambda r: (r.deposit("MC-M1-01.zip"), r.write("odin/extra.py", b"# extra\n")),
        check_odin_is_the_newest_deposit),
    "keys/odin.pub changed after the deposit": (
        lambda r: (r.deposit("MC-M1-01.zip"), r.write("keys/odin.pub", b"ssh-ed25519 AAAAother odin\n")),
        check_odin_is_the_newest_deposit),
    "odin/ present with no deposit at all": (
        lambda r: r.write("odin/__init__.py", b""), check_odin_is_the_newest_deposit),
}


@pytest.mark.parametrize("case", AFTERWARDS)
def test_red_a_change_after_the_deposit_is_caught(repo, case):
    make, check = AFTERWARDS[case]
    make(repo)
    assert check(repo.path) != []
