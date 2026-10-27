"""Checking a document against contract/schemas/, the single source for every record and message
(CONTRACT.md preamble). BALDUR-0, the harness, the event log and the repository tests all check
through here.
"""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft7Validator, RefResolver

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SUFFIX = ".schema.json"


@lru_cache(maxsize=None)
def _validator(name, schema_dir):
    folder = Path(schema_dir).resolve()
    # Every schema in the folder, keyed by its file URI, so relative $refs resolve without I/O.
    store = {p.as_uri(): json.loads(p.read_text(encoding="utf-8")) for p in folder.glob("*" + SUFFIX)}
    uri = (folder / (name + SUFFIX)).as_uri()
    return Draft7Validator(store[uri], resolver=RefResolver(uri, store[uri], store=store))


def _leaves(error):
    """The errors that say what is wrong. When none of a oneOf's or anyOf's shapes fits, the
    shape the document came closest to, the one with the fewest errors, explains it."""
    if not error.context:
        return [error]
    shapes = {}
    for sub in error.context:
        shapes.setdefault(sub.relative_schema_path[0], []).append(sub)
    candidates = [[leaf for sub in subs for leaf in _leaves(sub)] for subs in shapes.values()]
    # A shape the value is not even the type of (null, say, for an object) explains nothing.
    fitting = [leaves for leaves in candidates
               if not all(e.validator == "type" and e.absolute_path == error.absolute_path for e in leaves)]
    return min(fitting, key=len) if fitting else candidates[0]


def check(name, document, schema_dir=SCHEMA_DIR):
    """Every way the document fails the named schema; an empty list means it conforms."""
    problems = []
    for error in _validator(name, str(schema_dir)).iter_errors(document):
        for leaf in _leaves(error):
            problem = f"{'/'.join(map(str, leaf.absolute_path)) or '(top)'}: {leaf.message}"
            if problem not in problems:
                problems.append(problem)
    return problems
