"""Signing as ssh-keygen -Y sign does, for tests, with Ed25519 keys made in memory and never written.

Windows' own ssh-keygen refuses to sign with a key file whose permissions it judges too open, which a
test's scratch folder can be, so tests sign here instead and BALDUR-0 still verifies every signature
with ssh-keygen -Y verify. The format is OpenSSH's PROTOCOL.sshsig: the blob below, armored, over
the signed data of magic, namespace, reserved, hash algorithm and the message's SHA-512.
"""

import base64
import hashlib
import struct

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

MAGIC = b"SSHSIG"
HASH = b"sha512"


def _string(data):
    return struct.pack(">I", len(data)) + data


def new_key():
    return Ed25519PrivateKey.generate()


def public_blob(key):
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _string(b"ssh-ed25519") + _string(raw)


def public_line(key, comment):
    """The key's OpenSSH public line, ssh-ed25519 AAAA... comment."""
    return f"ssh-ed25519 {base64.b64encode(public_blob(key)).decode('ascii')} {comment}"


def sign(key, data, namespace):
    """The armored signature ssh-keygen -Y sign -n <namespace> would write for data."""
    namespace = namespace.encode("utf-8")
    signed = MAGIC + _string(namespace) + _string(b"") + _string(HASH) + _string(hashlib.sha512(data).digest())
    signature = _string(b"ssh-ed25519") + _string(key.sign(signed))
    blob = (MAGIC + struct.pack(">I", 1) + _string(public_blob(key)) + _string(namespace) + _string(b"")
            + _string(HASH) + _string(signature))
    text = base64.b64encode(blob).decode("ascii")
    lines = [text[i:i + 70] for i in range(0, len(text), 70)]
    return ("-----BEGIN SSH SIGNATURE-----\n" + "\n".join(lines) + "\n-----END SSH SIGNATURE-----\n").encode("ascii")
