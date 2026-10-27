"""Signed documents: TYR-0 plans and the Director's acts (CONTRACT.md §5.3, §5.4, §11.4).

Each document is a YAML file with its signature beside it, <name>.yaml.sig, made by ssh-keygen -Y sign.
BALDUR-0 reads a document's bytes once, verifies the signature over exactly those bytes with
ssh-keygen -Y verify, passing them on standard input, and parses the same bytes. Plans are signed
under the namespace tyr0 and acts under aesir-arm, so neither can be presented as the other.

Scored runs accept only the Director's key, principal dan in keys/allowed_signers. Development runs
accept the test key in keys/dev-test.pub as well as his (§11.4; the Director's ruling on U31).
"""

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from log.canonical import sha256_tag

KEYS_DIR = Path(__file__).resolve().parent.parent / "keys"
PLAN_NAMESPACE = "tyr0"
ACT_NAMESPACE = "aesir-arm"
MODES = ("DEVELOPMENT", "SCORED")
DIRECTOR = "dan"
DEV_TEST = "dev-test"


def find_ssh_keygen():
    program = shutil.which("ssh-keygen")
    if program is None:
        raise RuntimeError("ssh-keygen is not on PATH; BALDUR-0 cannot verify signatures without it")
    return program


def signers(mode, keys_dir=KEYS_DIR):
    """The (principal, allowed-signers line) pairs a mode accepts."""
    if mode not in MODES:
        raise ValueError(f"mode {mode!r} is not one of {MODES}")
    keys_dir = Path(keys_dir)
    director = [line for line in (keys_dir / "allowed_signers").read_text(encoding="utf-8").splitlines()
                if line.split(" ", 1)[0] == DIRECTOR]
    accepted = [(DIRECTOR, line) for line in director]
    if mode == "DEVELOPMENT":
        # The Director's ruling on U31 (27 October 2026): development mode accepts the test key and
        # also the Director's key, so his real plans can be tried in development.
        keytype, key = (keys_dir / "dev-test.pub").read_text(encoding="utf-8").split()[:2]
        accepted.append((DEV_TEST, f"{DEV_TEST} {keytype} {key}"))
    return accepted


def verify_signature(data, signature_path, *, namespace, mode, keys_dir=KEYS_DIR, ssh_keygen=None):
    """GOOD if a key the mode accepts signed exactly these bytes under the namespace, MISSING if
    there is no signature file, and BAD otherwise."""
    signature_path = Path(signature_path)
    accepted = signers(mode, keys_dir)
    if not signature_path.is_file():
        return "MISSING"
    program = ssh_keygen or find_ssh_keygen()
    with tempfile.TemporaryDirectory() as folder:
        for principal, line in accepted:
            allowed = Path(folder) / f"{principal}.allowed_signers"
            allowed.write_text(line + "\n", encoding="utf-8")
            result = subprocess.run(
                [program, "-Y", "verify", "-f", str(allowed), "-I", principal, "-n", namespace,
                 "-s", str(signature_path)],
                input=data, capture_output=True, timeout=30)
            if result.returncode == 0:
                return "GOOD"
    return "BAD"


class _StrictLoader(yaml.SafeLoader):
    """YAML's safe loader, refusing a key written twice in one mapping. PyYAML would keep the last,
    so a reader of the signed file and BALDUR-0 could see different values."""

    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                repeated = key in seen
            except TypeError:
                raise yaml.constructor.ConstructorError(
                    None, None, f"a key that is not a plain value: {key!r}", key_node.start_mark) from None
            if repeated:
                raise yaml.constructor.ConstructorError(
                    None, None, f"the key {key!r} appears twice", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(data):
    """(document, problems): the parsed bytes, or None and why they could not be parsed."""
    try:
        return yaml.load(data.decode("utf-8"), Loader=_StrictLoader), []
    except UnicodeDecodeError as error:
        return None, [f"not UTF-8 ({error})"]
    except yaml.YAMLError as error:
        return None, [f"not YAML BALDUR-0 accepts ({' '.join(str(error).split())})"]


@dataclass(frozen=True)
class Signed:
    path: Path
    data: bytes
    sha256: str
    signature: str        # GOOD, BAD or MISSING
    document: object      # the parsed YAML, or None
    problems: list        # why it could not be parsed


def read_signed(path, *, namespace, mode, keys_dir=KEYS_DIR, ssh_keygen=None):
    """A document and its signature, from one read of its bytes."""
    path = Path(path)
    data = path.read_bytes()
    signature = verify_signature(data, path.with_name(path.name + ".sig"), namespace=namespace, mode=mode,
                                 keys_dir=keys_dir, ssh_keygen=ssh_keygen)
    document, problems = load_yaml(data)
    return Signed(path, data, sha256_tag(data), signature, document, problems)


def field(document, name, kind):
    """A field of a document that may not have parsed, or None when it is missing or not of the kind
    a record can carry (§16 U15)."""
    value = document.get(name) if isinstance(document, dict) else None
    if kind == "identifier":
        return value if isinstance(value, str) and value else None
    if kind == "met_s":
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    raise ValueError(kind)
