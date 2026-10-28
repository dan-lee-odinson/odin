"""Refreshing Muse Code's workspace (00_HANDOFF.md §5): the shared files as they are on main, byte for byte,
each checked by SHA-256; nothing written into Muse Code's own folders and nothing deleted. The workspaces
here are scratch folders."""

import subprocess

import pytest

from tests.repo_checks import REPO_ROOT
from tests.test_s0_hashes import AGENTS_SHA256
from tools.refresh_workspace import MUSE_FOLDERS, check, digest, extras, files_on, refresh


def scratch_repo(tmp_path):
    """A git repository with one file in each shared place, committed on main."""
    repo = tmp_path / "repo"
    for name, text in {".agents/AGENTS.md": "rules\n", "CONTRACT.md": "contract\n", "config/ports.yaml": "log: 8712\n",
                       "keys/allowed_signers": "dan ssh-ed25519 AAAA\n", "keys/odin.pub": "ssh-ed25519 BBBB odin\n",
                       "contract/schemas/a.schema.json": "{}\n", "checkins/a.m4a": "\x00ftyp\n",
                       "gateway/other.py": "x = 1\n"}.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_bytes(text.encode("utf-8"))
    git = ["git", "-C", str(repo)]
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"], check=True)
    return repo


@pytest.fixture
def shared(tmp_path):
    return files_on("main", repo=scratch_repo(tmp_path), huginn_file=None)


def test_the_files_come_from_main_not_the_working_tree(tmp_path):
    repo = scratch_repo(tmp_path)
    (repo / "config" / "ports.yaml").write_bytes(b"log: 9999\n")   # changed, not committed
    files = files_on("main", repo=repo, huginn_file=None)
    assert files["config/ports.yaml"] == b"log: 8712\n"
    assert set(files) == {".agents/AGENTS.md", "CONTRACT.md", "config/ports.yaml", "keys/allowed_signers",
                          "keys/odin.pub", "contract/schemas/a.schema.json", "checkins/a.m4a"}


def test_muse_codes_rules_are_copied_and_checked_like_the_rest():
    files = files_on("main")
    assert digest(files[".agents/AGENTS.md"]) == "sha256:" + AGENTS_SHA256
    assert {"CONTRACT.md", "config/ports.yaml", "keys/allowed_signers"} <= set(files)


def test_huginns_dictionary_comes_from_the_commit_main_pins():
    files = files_on("main")
    pinned = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-tree", "main", "deps/huginn"],
                            capture_output=True, text=True, check=True).stdout.split()[2]
    assert pinned.startswith("b4dbe61")
    assert files["deps/huginn/defs/tlm_cmd.yaml"] == (REPO_ROOT / "deps/huginn/defs/tlm_cmd.yaml").read_bytes()
    assert not any(name.split("/")[0] in MUSE_FOLDERS for name in files)


def test_a_refresh_copies_byte_for_byte_and_every_copy_checks(tmp_path, shared):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "keys").mkdir()
    (workspace / "keys" / "odin.pub").write_bytes(shared["keys/odin.pub"])
    written = refresh(shared, workspace)
    assert written == {name: "ADDED" for name in shared if name != "keys/odin.pub"}
    assert check(shared, workspace) == []
    assert refresh(shared, workspace) == {}


def test_a_changed_file_on_main_is_written_again(tmp_path, shared):
    workspace = tmp_path / "workspace"
    refresh(shared, workspace)
    newer = dict(shared, **{"contract/schemas/a.schema.json": b'{"type": "object"}\n'})
    assert refresh(newer, workspace) == {"contract/schemas/a.schema.json": "CHANGED"}


def test_red_one_byte_changed_in_a_copy_is_caught(tmp_path, shared):
    workspace = tmp_path / "workspace"
    refresh(shared, workspace)
    (workspace / "keys" / "odin.pub").write_bytes(shared["keys/odin.pub"])
    copy = workspace / "contract" / "schemas" / "a.schema.json"
    data = bytearray(copy.read_bytes())
    data[0] ^= 0x01
    copy.write_bytes(bytes(data))
    [problem] = check(shared, workspace)
    assert problem.startswith("contract/schemas/a.schema.json: sha256:")


def test_red_a_missing_copy_is_caught(tmp_path, shared):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    assert "CONTRACT.md: missing from the workspace" in check(shared, workspace)


def test_muse_codes_own_key_is_checked_but_never_overwritten(tmp_path, shared):
    workspace = tmp_path / "workspace"
    (workspace / "keys").mkdir(parents=True)
    (workspace / "keys" / "odin.pub").write_bytes(b"ssh-ed25519 CCCC odin\n")
    refresh(shared, workspace)
    assert (workspace / "keys" / "odin.pub").read_bytes() == b"ssh-ed25519 CCCC odin\n"
    [problem] = check(shared, workspace)
    assert problem.startswith("keys/odin.pub:") and "never overwritten" in problem


@pytest.mark.parametrize("folder", MUSE_FOLDERS)
def test_red_nothing_is_ever_written_into_muse_codes_folders(tmp_path, shared, folder):
    workspace = tmp_path / "workspace"
    with pytest.raises(ValueError):
        refresh(dict(shared, **{f"{folder}/planted.txt": b"x\n"}), workspace)
    assert not workspace.exists()   # refused before anything was written


def test_muse_codes_folders_are_left_as_they_were_and_nothing_is_deleted(tmp_path, shared):
    workspace = tmp_path / "workspace"
    theirs = {f"{folder}/work.txt": f"{folder}\n".encode() for folder in MUSE_FOLDERS}
    theirs["contract/schemas/old.schema.json"] = b"{}\n"
    for name, data in theirs.items():
        (workspace / name).parent.mkdir(parents=True, exist_ok=True)
        (workspace / name).write_bytes(data)
    refresh(shared, workspace)
    assert all((workspace / name).read_bytes() == data for name, data in theirs.items())
    assert extras(shared, workspace) == ["contract/schemas/old.schema.json"]
