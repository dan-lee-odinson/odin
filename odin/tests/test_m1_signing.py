"""M1: request signing (CONTRACT §4, §7.3, §16.3 U13)."""
import base64
import json
import os
from pathlib import Path

import pytest

from odin.loop import signing
from odin.loop.canonical import canonical_json

REPO_ROOT = Path(__file__).resolve().parents[2]


def _request(pub_priv, agent_hash="sha256:" + "a" * 64):
    from odin.loop.signing import build_signed_request

    return build_signed_request(
        command="CMD_PLD_SET_STATE",
        parameters={"state": "ON"},
        rationale="test",
        run_id="dev-run-m1",
        turn_id=1,
        plan_id="TYR0-DEV-PASS1-v1",
        met_s=100,
        utc="2026-10-28T14:10:04.210Z",
        agent_input_hash=agent_hash,
        private_key_path=str(pub_priv["priv"]),
    )


def test_signature_verifies_with_public_key(keypair):
    req = _request(keypair)
    assert signing.verify_request(req, str(keypair["pub"])) is True
    # Signature is 64 bytes, standard base64 with padding (88 chars ending ==).
    assert len(base64.b64decode(req["signature"])) == 64
    assert req["signature"].endswith("==")
    assert len(req["nonce"]) == 32
    assert req["origin"] == "ODIN"


def test_signature_fails_after_one_byte_change(keypair):
    req = _request(keypair)
    assert signing.verify_request(req, str(keypair["pub"])) is True
    tampered = dict(req)
    tampered["parameters"] = {"state": "OFF"}
    assert signing.verify_request(tampered, str(keypair["pub"])) is False
    # Flip one character of the canonical payload via met_s.
    tampered2 = dict(req)
    tampered2["met_s"] = req["met_s"] + 1
    assert signing.verify_request(tampered2, str(keypair["pub"])) is False
    # Corrupt the signature itself by one byte.
    raw = bytearray(base64.b64decode(req["signature"]))
    raw[0] ^= 0x01
    tampered3 = dict(req, signature=base64.b64encode(bytes(raw)).decode())
    assert signing.verify_request(tampered3, str(keypair["pub"])) is False


def test_canonical_json_sorted_compact():
    assert canonical_json({"b": 1, "a": {"d": 4, "c": 3}}) == b'{"a":{"c":3,"d":4},"b":1}'


def test_rfc8032_test_1():
    """Signer proven against RFC 8032 §7.1 TEST 1, not only its own verify."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    seed = bytes.fromhex(
        "9d61b19deffd5a60ba844af492ec2cc4" "4449c5697b326919703bac031cae7f60"
    )
    expected_pub = bytes.fromhex(
        "d75a980182b10ab7d54bfed3c964073a" "0ee172f3daa62325af021a68f707511a"
    )
    expected_sig = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a" "84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46b" "d25bf5f0595bbe24655141438e7a100b"
    )
    key = Ed25519PrivateKey.from_private_bytes(seed)
    assert signing.public_raw(key) == expected_pub
    assert signing.sign_bytes(key, b"") == expected_sig
    assert signing.verify_bytes(expected_pub, b"", expected_sig) is True
    assert signing.verify_bytes(expected_pub, b"x", expected_sig) is False


def test_repo_pub_matches_env_key_when_set(tmp_path):
    """When ODIN_KEY_PATH is set, keys/odin.pub is that key's public half;
    a different public key must not match (Director's M1 addition)."""
    env_path = os.environ.get("ODIN_KEY_PATH")
    if not env_path:
        if os.environ.get("ODIN_KEY_MATCH_REQUIRED") == "1":
            pytest.fail("ODIN_KEY_PATH not set but ODIN_KEY_MATCH_REQUIRED=1")
        pytest.skip("ODIN_KEY_PATH not set")
    try:
        private_key = signing.load_private_key(env_path)
    except (PermissionError, OSError) as exc:
        # Contract §2 rule 5: the private key stays out of this sandbox.
        if os.environ.get("ODIN_KEY_MATCH_REQUIRED") == "1":
            pytest.fail(f"ODIN key unreadable but ODIN_KEY_MATCH_REQUIRED=1: {exc}")
        pytest.skip(f"ODIN private key unreadable from this environment: {exc}")
    derived = signing.openssh_public_line(private_key).split()[:2]
    repo_line = (REPO_ROOT / "keys" / "odin.pub").read_text(encoding="utf-8").split()[:2]
    assert repo_line == derived
    # A request signed by the real key verifies with keys/odin.pub …
    req = signing.build_signed_request(
        command="CMD_PLD_SET_STATE", parameters={"state": "ON"}, rationale=None,
        run_id="dev-run-m1", turn_id=1, plan_id="TYR0-DEV-PASS1-v1", met_s=100,
        utc="2026-10-28T14:10:04.210Z", agent_input_hash="sha256:" + "a" * 64,
        private_key_path=env_path)
    assert signing.verify_request(req, str(REPO_ROOT / "keys" / "odin.pub")) is True
    # … and fails against a mismatched (throwaway) public key.
    other_priv = tmp_path / "other_key"
    other_pub = tmp_path / "other.pub"
    signing.generate_keypair_files(other_priv, other_pub)
    assert signing.verify_request(req, str(other_pub)) is False


def test_public_key_file_is_openssh_line(keypair):
    line = keypair["pub"].read_text(encoding="utf-8").strip()
    parts = line.split()
    assert parts[0] == "ssh-ed25519" and len(parts) >= 2
    json.loads("{}")  # sanity: no secret material in the public file
    assert "PRIVATE" not in line
