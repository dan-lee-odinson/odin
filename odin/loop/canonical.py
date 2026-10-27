"""Canonical JSON and hashing (CONTRACT.md §4, ruling U22). Stdlib only.

Canonical bytes are exactly the UTF-8 of
json.dumps(value, sort_keys=True, separators=(",", ":"),
ensure_ascii=False, allow_nan=False), with no trailing newline.
NaN and infinity are not JSON and are refused (allow_nan=False raises).
Proven against contract/schemas/canonical_vectors.json.
"""
import hashlib
import json


def canonical_json(obj) -> bytes:
    """UTF-8, keys sorted, no insignificant whitespace, no trailing newline."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_tag(data: bytes) -> str:
    return "sha256:" + sha256_hex(data)
