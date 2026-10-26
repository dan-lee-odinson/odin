"""CONTRACT.md and .agents/AGENTS.md are the approved files, byte for byte (00_HANDOFF.md §4, S0)."""

import pytest

from tests.repo_checks import REPO_ROOT, check_file_hash

# From 00_HANDOFF.md, 26 October 2026: contract v0.4, and Muse Code's rules as frozen that day.
CONTRACT_SHA256 = "f7e3eddf212015ed06a7accb80a03b72f0e81076c58f6de5919688d75e9999bc"
AGENTS_SHA256 = "bda6df727be32bc0091fd12253f9402b38d6d016d2398e4b40cdada9130204b3"

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
