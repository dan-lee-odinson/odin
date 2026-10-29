"""CONTRACT.md and .agents/AGENTS.md are the approved files, byte for byte (00_HANDOFF.md §4, S0)."""

import pytest

from tests.repo_checks import REPO_ROOT, check_file_hash

# From 00_HANDOFF.md (the v0.6 packet), 26 October 2026: contract v0.6, and Muse Code's rules
# as frozen that day. The contract as amended by the Director's ruling of 29 October 2026 on how
# spark_open's answer is taken (§11.1, with §7.1 and §16.5 U17 to match), and by his approval the same day of
# §11.1's glimmer_modal row, Muse Glimmer on Modal, with its line in the header's amendments; the packet's was
# 9d39b83e42fbe0854b1d88813305273058df61ac57e278ebb5431e0437a91857, and the first amendment's
# 9084106cbae14a4afba0d9059ac111872967ffe05aed5f88b9cad46c27af3e02.
CONTRACT_SHA256 = "2c3255b275be61da746f3eb3386bc84071153efb29d4ed3444d23c323398198c"
# Muse Code's rules brought up to date with that amendment by the Director's ruling of 29 October 2026, "Apply it":
# section 0 names the amended contract's hash, and 4.2 spark_open's answer rule; then, by his approval the same
# day, 4.2's glimmer_modal line for M5's prep and section 0 the contract's new hash. The packet's were
# d3f26dcb46d267c47e1f5d0c6b00f5bd77ffb7adabdd04d6cc66a71c3193e4b7, and the first amendment's
# 827284051c1819d2658afca2fc2a89976aefa998ce9f4d19ca6cf2753c091f98.
AGENTS_SHA256 = "715b5dd30bcf3cfa78e4217e70b7cd8cc549eb3d79d4e87bef70bff7b707a69d"

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
