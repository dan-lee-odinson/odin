"""Scan files for private identity details before they enter the repository (00_HANDOFF.md §3, item 8).

    python tools/identity_scan.py FILE...

Reports Windows usernames, machine names, private paths and private email addresses, each with its file
and line, and exits 1 if it finds any. It never edits a file: what it finds goes to the Director.

Nothing here names a private detail. The username and machine name are this machine's, read from its
environment; every user-profile path is reported whatever the name in it; and every email address is
reported except the public identities below.

A file compressed with zstd or gzip, such as a saved Blender scene, is scanned as it decompresses, layer by
layer, so a path inside it is seen, and its findings name the layers (the Director's ruling of 30 October
2026, after ANIM-01's scene held a user-profile path the scan of its compressed bytes could not see). One that
cannot be decompressed here is itself a finding, never passed unread.
"""

import gzip
import os
import re
import sys
from pathlib import Path

try:
    from compression import zstd   # Python 3.14 and later
except ImportError:
    zstd = None

PUBLIC_EMAILS = {"dan.lee.odinson@gmail.com", "noreply@anthropic.com"}
ZSTD_MAGIC, GZIP_MAGIC = b"\x28\xb5\x2f\xfd", b"\x1f\x8b"
MAX_LAYERS = 4
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


def decompressed(name, data):
    """(name, bytes, problem): a zstd or gzip file's contents, layer by layer, with its name telling the layers,
    as "scene.blend (zstd)"; problem says why a compressed file could not be read here, else None."""
    layers = []
    for _ in range(MAX_LAYERS):
        if data.startswith(GZIP_MAGIC):
            layer, opener = "gzip", gzip.decompress
        elif data.startswith(ZSTD_MAGIC):
            layer, opener = "zstd", zstd.decompress if zstd is not None else None
        else:
            break
        layers.append(layer)
        if opener is None:
            return f"{name} ({'/'.join(layers)})", None, "zstd cannot be decompressed by this Python (3.14 reads it)"
        try:
            data = opener(data)
        except Exception as error:   # a damaged or truncated file is reported, never passed unread
            return f"{name} ({'/'.join(layers)})", None, f"cannot be decompressed: {error!r}"
    return (f"{name} ({'/'.join(layers)})" if layers else name), data, None


def scan(name, data, environ=None):
    """[(name, line, kind, text)] for every private identity detail in data, a file's bytes, read through any
    zstd or gzip compression."""
    name, data, problem = decompressed(name, data)
    if problem is not None:
        return [(name, 0, "unreadable compressed file", problem)]
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
