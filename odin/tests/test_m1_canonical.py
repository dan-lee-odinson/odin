"""M1/S2: canonical JSON must reproduce every shared vector (ruling U22)."""
import hashlib
import json
from pathlib import Path

import pytest

from odin.loop.canonical import canonical_json, sha256_tag

VECTORS_FILE = Path(__file__).resolve().parents[2] / "contract" / "schemas" / "canonical_vectors.json"
VECTORS = json.loads(VECTORS_FILE.read_text(encoding="utf-8"))["vectors"]


def test_vector_file_is_present_and_nonempty():
    assert len(VECTORS) >= 10


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_every_canonical_vector(vector):
    got = canonical_json(vector["value"])
    assert got == bytes.fromhex(vector["canonical_hex"])
    assert sha256_tag(got) == vector["sha256"]
    assert not got.endswith(b"\n")


def test_altered_vector_is_caught():
    """Red case: a vector with one altered byte must NOT reproduce."""
    vector = dict(VECTORS[0])
    raw = bytearray(bytes.fromhex(vector["canonical_hex"]))
    raw[3] ^= 0x01
    vector["canonical_hex"] = raw.hex()
    assert canonical_json(vector["value"]) != bytes.fromhex(vector["canonical_hex"])


def test_nan_and_infinity_refused():
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
    with pytest.raises(ValueError):
        canonical_json({"x": float("inf")})
