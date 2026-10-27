"""CONTRACT.md and .agents/AGENTS.md are the approved files, byte for byte (00_HANDOFF.md §4, S0)."""

import pytest

from tests.repo_checks import REPO_ROOT, check_file_hash

# From 00_HANDOFF.md (the v0.6 packet), 26 October 2026: contract v0.6, and Muse Code's rules
# as frozen that day.
CONTRACT_SHA256 = "9d39b83e42fbe0854b1d88813305273058df61ac57e278ebb5431e0437a91857"
AGENTS_SHA256 = "d3f26dcb46d267c47e1f5d0c6b00f5bd77ffb7adabdd04d6cc66a71c3193e4b7"

GOVERNING = {
    "CONTRACT.md": CONTRACT_SHA256,
    ".agents/AGENTS.md": AGENTS_SHA256,
}


def test_contract_hash():
    assert check_file_hash(REPO_ROOT / "CONTRACT.md", CONTRACT_SHA256) == []


def test_agents_rules_hash():
    assert check_file_hash(REPO_ROOT / ".agents" / "AGENTS.md", AGENTS_SHA256) == []


# Red cases: the same check on a scratch copy of each file with one defect planted.

TAMPERS = {
    "one byte appended": lambda b: b + b" ",
    "one byte changed": lambda b: b[:100] + bytes([b[100] ^ 0x01]) + b[101:],
    "line endings turned to CRLF": lambda b: b.replace(b"\n", b"\r\n"),
    "emptied": lambda b: b"",
}


@pytest.mark.parametrize("tamper", TAMPERS)
@pytest.mark.parametrize("rel", GOVERNING)
def test_red_hash_check_catches(tmp_path, rel, tamper):
    copy = tmp_path / "copy.md"
    copy.write_bytes(TAMPERS[tamper]((REPO_ROOT / rel).read_bytes()))
    assert check_file_hash(copy, GOVERNING[rel]) != []


def test_red_hash_check_catches_a_missing_file(tmp_path):
    assert check_file_hash(tmp_path / "CONTRACT.md", CONTRACT_SHA256) != []
