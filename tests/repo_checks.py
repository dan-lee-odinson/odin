"""Repository-wide checks (00_HANDOFF.md §3, stage S0).

Each check returns a list of problems; an empty list means it passed. The tests beside this
module run every check on the repository (green) and on a scratch copy with a defect planted
on purpose (red), so a check that can no longer fail is caught. tests/show_red.py plants the
same defects in the real working tree and shows the real tests failing.

Some literals below are assembled from pieces so that this file does not trip its own scans.
"""

import ast
import base64
import binascii
import gzip
import hashlib
import os
import re
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Top-level folders that are never walked. deps/ is HUGINN, used unchanged: its own
# tools/demonstrate.py imports ve, and walking it would open the folders this repository
# must never open. cache/ holds the COSMOS docs, which are not ours.
SKIP_TOP = {".git", "deps", "cache"}
SKIP_ANYWHERE = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}

# Files that are code or configuration, as opposed to prose. The governing documents say in
# prose which HUGINN folders are off limits, so Markdown is not scanned for those paths.
CODE_SUFFIXES = {
    ".py", ".pyi", ".ps1", ".psm1", ".sh", ".bash", ".bat", ".cmd", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".rb", ".yaml", ".yml", ".toml", ".json", ".ini", ".cfg",
}
CODE_NAMES = {"Dockerfile", "Makefile"}


def iter_files(root):
    """Every file under root, in a stable order, without entering the skipped folders."""
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        at_top = Path(dirpath) == root
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_ANYWHERE and not (at_top and d in SKIP_TOP)
        )
        for name in sorted(filenames):
            yield Path(dirpath) / name


def _is_code(path):
    return (path.suffix.lower() in CODE_SUFFIXES or path.name in CODE_NAMES
            or path.name.startswith("compose"))


def _rel(path, root):
    return Path(path).relative_to(root).as_posix()


def _line_of(text, index):
    return text.count("\n", 0, index) + 1


# ---------------------------------------------------------------------------------------
# File hashes: CONTRACT.md and .agents/AGENTS.md are the approved files, byte for byte.

def sha256_hex(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_file_hash(path, expected_hex):
    path = Path(path)
    if not path.is_file():
        return [f"{path.name}: missing"]
    actual = sha256_hex(path)
    if actual != expected_hex:
        return [f"{path.name}: sha256 {actual}, expected {expected_hex}"]
    return []


# ---------------------------------------------------------------------------------------
# keys/allowed_signers: the Director's TYR-0 key under its principal, by fingerprint.

KEY_TYPE = re.compile(r"^(?:ssh-|ecdsa-|sk-)")


def ssh_fingerprint(key_b64):
    """OpenSSH's SHA256 fingerprint of a public key blob, as ssh-keygen -l prints it."""
    digest = hashlib.sha256(base64.b64decode(key_b64, validate=True)).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def check_allowed_signer(path, principal, expected_fingerprint):
    path = Path(path)
    if not path.is_file():
        return [f"{path.name}: missing"]
    keys = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        # An options field may sit between the principals and the key type (ssh-keygen(1)).
        rest = fields[1:] if len(fields) > 1 and KEY_TYPE.match(fields[1]) else fields[2:]
        if principal in fields[0].split(","):
            if len(rest) < 2:
                return [f"{path.name}:{number}: no key for principal {principal!r}"]
            keys.append((number, rest[1]))
    if len(keys) != 1:
        return [f"{path.name}: {len(keys)} keys for principal {principal!r}, expected 1"]
    number, key_b64 = keys[0]
    try:
        actual = ssh_fingerprint(key_b64)
    except (binascii.Error, ValueError):
        return [f"{path.name}:{number}: key for {principal!r} is not valid base64"]
    if actual != expected_fingerprint:
        return [f"{path.name}:{number}: fingerprint {actual}, expected {expected_fingerprint}"]
    return []


# ---------------------------------------------------------------------------------------
# HUGINN guard: nothing here imports ve or opens ve/, viewer/, replay/ or the replay schema.

VE = "ve"
# Fallback for Python files that do not parse; comments are stripped before matching.
VE_IMPORT_LINE = re.compile(
    r"^\s*(?:from\s+\.*(?:\w+\.)*" + VE + r"(?:\.\w+)*\s+import\b|import\s+.*\b" + VE + r"\b)"
)
# A script that runs ve as a module, e.g. python -m ve.
VE_RUN_MODULE = re.compile(r"-m\s+(?:\w+\.)*" + VE + r"(?![\w.])")
FORBIDDEN_PATH = re.compile(
    r"huginn[\\/]+(?:" + VE + r"|viewer|replay)(?![\w.-])|" + "replay" "_schema",
    re.IGNORECASE,
)


def _names_ve(name):
    return VE in (name or "").split(".")


def _call_name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _python_ve_imports(source):
    """Line numbers of Python statements that import ve, found by parsing the source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [n for n, line in enumerate(source.splitlines(), 1)
                if VE_IMPORT_LINE.match(line.split("#", 1)[0])]
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] + [alias.name for alias in node.names]
        elif (isinstance(node, ast.Call) and _call_name(node.func) in {"import_module", "__import__"}
              and node.args and isinstance(node.args[0], ast.Constant)
              and isinstance(node.args[0].value, str)):
            names = [node.args[0].value]
        else:
            continue
        if any(_names_ve(name) for name in names):
            lines.append(node.lineno)
    return sorted(lines)


def check_no_ve_import(root):
    root = Path(root)
    problems = []
    for path in iter_files(root):
        if not _is_code(path):
            continue
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        if path.suffix.lower() in {".py", ".pyi"}:
            lines = _python_ve_imports(text)
        else:
            lines = [_line_of(text, m.start()) for m in VE_RUN_MODULE.finditer(text)]
        problems += [f"{_rel(path, root)}:{n}: imports {VE}" for n in lines]
    return problems


def check_no_forbidden_huginn_paths(root):
    root = Path(root)
    problems = []
    for path in iter_files(root):
        if not _is_code(path):
            continue
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        for m in FORBIDDEN_PATH.finditer(text):
            problems.append(f"{_rel(path, root)}:{_line_of(text, m.start())}: "
                            f"refers to HUGINN's {m.group(0)!r}")
    return problems


# ---------------------------------------------------------------------------------------
# Truth kept apart: runs/<run_id>/truth.jsonl holds fault onsets and the simulator's true state,
# for evaluation only, and ODIN never reads it (CONTRACT.md §12). Only the folders that write it
# (the log, the wrapper and the harness) and the one that scores with it (eval) may name it in
# code. runs/ holds data, not code.

TRUTH_FILE = re.compile(r"truth\.jsonl")
TRUTH_FOLDERS = {"log", "wrapper", "harness", "eval", "tests", "runs"}


def check_truth_kept_apart(root):
    root = Path(root)
    problems = []
    for path in iter_files(root):
        rel = _rel(path, root)
        if rel.split("/")[0] in TRUTH_FOLDERS or not _is_code(path):
            continue
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
        for m in TRUTH_FILE.finditer(text):
            problems.append(f"{rel}:{_line_of(text, m.start())}: names the truth file, which only "
                            f"{', '.join(sorted(TRUTH_FOLDERS - {'tests', 'runs'}))} may")
    return problems


# ---------------------------------------------------------------------------------------
# Secret scan. A finding names the file, line and kind of secret, never the value.

# AGENTS.md §2.5 names META_API_KEY and BASETEN_API_KEY. The Modal names stay covered while
# Modal remains the Glimmer GPU fallback (CONTRACT.md §11.2). ODIN's COSMOS keeps its credentials
# as ODIN_COSMOS_* variables, and COSMOS reads them under its own OPENC3_ and SECRET_KEY_BASE names (S4).
SECRET_ENV_VARS = ["META_API_KEY", "BASETEN_API_KEY", "MODAL_ENDPOINT_URL",
                   "MODAL_PROXY_TOKEN_ID", "MODAL_PROXY_TOKEN_SECRET",
                   r"ODIN_COSMOS_\w*(?:PASSWORD|USERNAME|SECRET_KEY_BASE)", r"OPENC3_\w*PASSWORD", "SECRET_KEY_BASE"]
SECRET_PATTERNS = [
    ("private key", r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"),
    ("value written for a secret environment variable",
     r"\b(?:" + "|".join(SECRET_ENV_VARS) + r")[\"']?\s*[:=]\s*[\"']?"
     r"(?![$<{%]|os\.|getenv|environ)[^\s\"'<>]{8,}"),
    ("Modal token", r"\b(?:ak|as|wk|ws)-[A-Za-z0-9]{16,}"),
    ("sk- style API key", r"\bsk-[A-Za-z0-9_-]{20,}"),
    ("GitHub token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"),
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("Google API key", r"\bAIza[0-9A-Za-z_-]{35}"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("bearer token", r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{24,}=*"),
    ("Api-Key header", r"(?i)\bapi-key\s+[A-Za-z0-9._-]{20,}"),
    ("quoted secret assignment",
     r"(?i)\b(?:api[_-]?key|secret|token|passw(?:or)?d)[\"']?\s*[:=]\s*[\"'][^\"'\s]{16,}[\"']"),
]
_SECRETS = [(kind, re.compile(pattern)) for kind, pattern in SECRET_PATTERNS]


def _secret_findings(text, where):
    return [f"{where}:{_line_of(text, m.start())}: {kind}"
            for kind, rx in _SECRETS for m in rx.finditer(text)]


def check_no_secrets(root):
    root = Path(root)
    problems = []
    for path in iter_files(root):
        rel = _rel(path, root)
        data = path.read_bytes()
        if path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path) as archive:
                    for member in archive.namelist():
                        text = archive.read(member).decode("latin-1")
                        problems += _secret_findings(text, f"{rel}!{member}")
            except zipfile.BadZipFile:
                problems.append(f"{rel}: zip cannot be read, so it cannot be scanned")
            continue
        if path.suffix.lower() == ".gz":
            # A scored run's truth file is committed gzip-compressed (the Director's ruling on U36).
            try:
                problems += _secret_findings(gzip.decompress(data).decode("latin-1"), f"{rel}!")
            except (OSError, EOFError):
                problems.append(f"{rel}: gzip cannot be read, so it cannot be scanned")
            continue
        problems += _secret_findings(data.decode("latin-1"), rel)
    return problems
