"""Ed25519 request signing (CONTRACT §7.3, §16.3 U13).

Uses the `cryptography` package only — no hand-rolled Ed25519.
ODIN's private key is an OpenSSH private key at the path in
ODIN_KEY_PATH (outside the repository), read with
`load_ssh_private_key`. `keys/odin.pub` is that key's public half as
one OpenSSH line (`ssh-ed25519 AAAA… odin`).
"""
import base64
import os
import secrets
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .canonical import canonical_json


def load_private_key(private_path=None) -> Ed25519PrivateKey:
    """Read ODIN's OpenSSH private key from ODIN_KEY_PATH (or the given path)."""
    path = private_path or os.environ.get("ODIN_KEY_PATH")
    if not path:
        raise RuntimeError("ODIN_KEY_PATH is not set and no private_key_path given")
    key = serialization.load_ssh_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("ODIN private key is not Ed25519")
    return key


def load_public_key(public_path) -> Ed25519PublicKey:
    key = serialization.load_ssh_public_key(Path(public_path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimeError("public key is not Ed25519")
    return key


def public_raw(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def openssh_public_line(private_key: Ed25519PrivateKey, comment: str = "odin") -> str:
    line = private_key.public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH
    ).decode("ascii")
    return f"{line} {comment}"


def generate_keypair_files(private_path, public_path) -> None:
    """Write a fresh keypair: OpenSSH private to private_path (outside the
    repo), one OpenSSH public line to public_path (keys/odin.pub)."""
    private_key = Ed25519PrivateKey.generate()
    Path(private_path).write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        )
    )
    Path(public_path).write_text(openssh_public_line(private_key) + "\n", encoding="utf-8")


def sign_bytes(private_key: Ed25519PrivateKey, msg: bytes) -> bytes:
    return private_key.sign(msg)


def verify_bytes(public_raw_bytes: bytes, msg: bytes, signature: bytes) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(public_raw_bytes).verify(signature, msg)
        return True
    except (InvalidSignature, ValueError):
        return False


def build_signed_request(*, command, parameters, rationale, run_id, turn_id, plan_id,
                         met_s, utc, agent_input_hash, private_key_path=None) -> dict:
    """Fill every loop-owned field and sign (the model never writes these)."""
    request = {
        "request_id": str(uuid.uuid4()),
        "origin": "ODIN",
        "utc": utc,
        "met_s": met_s,
        "nonce": secrets.token_hex(16),
        "run_id": run_id,
        "turn_id": turn_id,
        "plan_id": plan_id,
        "agent_input_hash": agent_input_hash,
        "command": command,
        "parameters": parameters,
    }
    if rationale is not None:
        request["rationale"] = rationale
    private_key = load_private_key(private_key_path)
    signature = sign_bytes(private_key, canonical_json(request))
    request["signature"] = base64.b64encode(signature).decode("ascii")
    return request


def verify_request(request: dict, public_key_path) -> bool:
    payload = {k: v for k, v in request.items() if k != "signature"}
    try:
        signature = base64.b64decode(request["signature"])
        load_public_key(public_key_path).verify(signature, canonical_json(payload))
        return True
    except Exception:
        return False
