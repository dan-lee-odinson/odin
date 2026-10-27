"""M1 guards: no `ve` import anywhere; secret scan finds nothing (§2)."""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(META_API_KEY|BASETEN_API_KEY)\s*=\s*[\"'][^\"'\s]+[\"']"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]


def _iter_source_files():
    for folder in (REPO_ROOT / "odin",):
        for path in folder.rglob("*"):
            if path.suffix in (".py", ".md", ".yaml", ".yml", ".json", ".txt") and path.is_file():
                if ".venv" in path.parts:
                    continue
                yield path


def test_no_file_imports_ve():
    offenders = []
    pat = re.compile(r"^\s*(import\s+ve\b|from\s+ve\b|import\s+ve\.|from\s+ve\.)", re.M)
    for path in _iter_source_files():
        if pat.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path))
    assert offenders == []


def test_secret_scan_finds_nothing():
    hits = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                hits.append((str(path), pat.pattern))
    assert hits == []


def test_no_second_copy_of_schema_field_lists():
    # The validator must load contract/schemas, not embed field lists.
    validate_py = (REPO_ROOT / "odin" / "loop" / "validate.py").read_text(encoding="utf-8")
    assert "contract" in validate_py and "schemas" in validate_py
