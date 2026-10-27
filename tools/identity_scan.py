"""Scan files for private identity details before they enter the repository (00_HANDOFF.md §3, item 8).

    python tools/identity_scan.py FILE...

Reports Windows usernames, machine names, private paths and private email addresses, each with its file
and line, and exits 1 if it finds any. It never edits a file: what it finds goes to the Director.

Nothing here names a private detail. The username and machine name are this machine's, read from its
environment; every user-profile path is reported whatever the name in it; and every email address is
reported except the public identities below.
"""

import os
import re
import sys
from pathlib import Path

PUBLIC_EMAILS = {"dan.lee.odinson@gmail.com", "noreply@anthropic.com"}
PATTERNS = [
    ("user-profile path", r"(?i)\b[A-Z]:[\\/]+(?:Users|Documents and Settings)[\\/]+[^\\/\s\"'<>|]+"),
    ("user-profile path", r"(?i)(?<![\w.:])/(?:[a-z]/)?(?:Users|home)/[^/\s\"'<>|]+"),
    ("email address", r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    ("default machine name", r"\b(?:DESKTOP|LAPTOP)-[A-Z0-9]{6,}\b"),
]


def patterns(environ=None):
    """The patterns, with this machine's username and machine name added from its environment."""
    environ = os.environ if environ is None else environ
    found = list(PATTERNS)
    for kind, name in (("Windows username", "USERNAME"), ("machine name", "COMPUTERNAME")):
        value = environ.get(name)
        if value:
            found.append((kind, rf"(?i)(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])"))
    return [(kind, re.compile(pattern)) for kind, pattern in found]


def scan(name, data, environ=None):
    """[(name, line, kind, text)] for every private identity detail in data, a file's bytes."""
    text = data.decode("utf-8", errors="replace")
    findings = []
    for kind, pattern in patterns(environ):
        for match in pattern.finditer(text):
            if kind == "email address" and match.group(0).lower() in PUBLIC_EMAILS:
                continue
            findings.append((name, text.count("\n", 0, match.start()) + 1, kind, match.group(0)))
    return sorted(findings, key=lambda f: (f[0], f[1], f[2]))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    findings = [f for path in argv for f in scan(path, Path(path).read_bytes())]
    for name, line, kind, text in findings:
        print(f"{name}:{line}: {kind}: {text}")
    print(f"scanned {len(argv)} files: " + (f"{len(findings)} findings" if findings else "nothing found"))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
