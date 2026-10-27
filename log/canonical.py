"""Canonical JSON and hashes (CONTRACT.md §4): the bytes every hash and signature in this build
is taken over.
"""

import hashlib
import json


def canonical_json(value):
    """The UTF-8 encoding of Python's json.dumps(value, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False, allow_nan=False), with no trailing newline (the Director's ruling on U22,
    26 October 2026). NaN and infinity are refused. contract/schemas/canonical_vectors.json holds
    the bytes every canonical writer in this build must reproduce.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def sha256_tag(data):
    """SHA-256 of bytes, written sha256:<hex> (§4)."""
    return "sha256:" + hashlib.sha256(data).hexdigest()
