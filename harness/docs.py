"""The read-only COSMOS page lookup, GET /docs/lookup?q= (CONTRACT.md §8.1, §8.4, §16.5 U17).

It reads the pinned docs in cache/cosmos-docs-7.2.1/, which Muse Code's fetch script writes and git
ignores (00_HANDOFF.md §5), and answers {query, results}: at most three pages, each {path, title,
sha256, text, truncated}, the text cut at 4,000 characters.
"""

import re
from pathlib import Path

from log.canonical import sha256_tag

CACHE = Path(__file__).resolve().parent.parent / "cache" / "cosmos-docs-7.2.1"
MAX_RESULTS, MAX_TEXT = 3, 4000


def _title(text, path):
    heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE) or re.search(r"<title>(.*?)</title>", text, re.I | re.S)
    return heading.group(1).strip() if heading else path.stem


# How pages are found and ranked (the Director's ruling on U42, 27 October 2026): every file in the
# cache is read as UTF-8 text and scored by how often the query's words occur in it as whole words,
# ignoring case, and the three highest are returned, ties by path. A page's title is its first Markdown
# heading or HTML title, else its file name; its path is relative to the cache. The cache is what Muse
# Code's M4 fetch script writes (00_HANDOFF.md §5, AGENTS.md §4.4) and nothing else: never the docs
# plugin inside COSMOS. Until M4 lands, the tests use a small fixture cache, tests/fixtures/cosmos-docs/.
def lookup(query, folder=CACHE):
    folder = Path(folder)
    words = re.findall(r"\w+", query.lower())
    scored = []
    for path in sorted(folder.rglob("*")) if folder.is_dir() and words else ():
        if not path.is_file():
            continue
        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        lowered = text.lower()
        score = sum(len(re.findall(rf"\b{re.escape(word)}\b", lowered)) for word in words)
        if score:
            scored.append((-score, path.relative_to(folder).as_posix(), path, data, text))
    results = [{"path": rel, "title": _title(text, path), "sha256": sha256_tag(data), "text": text[:MAX_TEXT],
                "truncated": len(text) > MAX_TEXT} for _, rel, path, data, text in sorted(scored)[:MAX_RESULTS]]
    return {"query": query, "results": results}
