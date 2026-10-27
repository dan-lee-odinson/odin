"""An append-only JSON Lines file whose records are chained by hash (CONTRACT.md §12).

Each line is the canonical JSON (§4) of one record, {record_id, utc, met_s, type, body, prev_hash}.
record_id counts from 1. prev_hash is the hash of the previous line, which is the previous record's
canonical JSON, and null on the first record, whose previous record does not exist (§16, U15).
Because every line must be canonical, a change to any byte of a line breaks either the line itself
or the next line's link to it.

The last line has no next line, so a change to it shows only against a head hash kept apart from
the file. Beside each log the writer keeps a head file, events.jsonl's being events.head, holding
the hash of the last record and rewritten after every record; the chain check compares it when it
is present (the Director's ruling on U23, 26 October 2026). For scored runs, each log's final hash
also goes into the committed evaluation report.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from log.canonical import canonical_json, sha256_tag

FIELDS = ("record_id", "utc", "met_s", "type", "body", "prev_hash")
HEAD_FORM = re.compile(rb"sha256:[0-9a-f]{64}\n")


class LogError(Exception):
    """A record was refused, or a file is not as its writer left it."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


def utc_now():
    """Wall-clock time in UTC with milliseconds (§4)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def head_file(path):
    """The head file beside a log: events.jsonl's is events.head."""
    return Path(path).with_suffix(".head")


def _split(data):
    lines = data.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    return lines


def _line_problems(line, number, prev, check):
    try:
        record = json.loads(line)
    except ValueError as error:
        return [f"not a JSON record ({error})"]
    if not isinstance(record, dict):
        return ["not a JSON object"]
    problems = []
    try:
        if canonical_json(record) != line:
            problems.append("not in canonical form (§4)")
    except ValueError:
        problems.append("holds a number JSON does not allow")
    if sorted(record) != sorted(FIELDS):
        problems.append(f"its fields are {sorted(record)}, not {sorted(FIELDS)}")
    record_id = record.get("record_id")
    if record_id != number or isinstance(record_id, bool):
        problems.append(f"record_id is {record_id!r}, not {number}")
    if record.get("prev_hash") != prev:
        problems.append("prev_hash is not the hash of the previous record" if number > 1
                        else "the first record's prev_hash is not null")
    if check is not None:
        problems += check(record)
    return problems


def verify_bytes(data, *, expected_head=None, check=None):
    """Every way a log's bytes fail to be an intact chain; an empty list means they are one.

    check(record) may add problems of its own, such as a schema's. With expected_head, the last
    record's hash must equal it, which is what catches a change to the last record.
    """
    problems = []
    if data and not data.endswith(b"\n"):
        problems.append("the last line is not terminated: the file was cut short or changed")
    prev = None
    for number, line in enumerate(_split(data), 1):
        problems += [f"line {number}: {p}" for p in _line_problems(line, number, prev, check)]
        prev = sha256_tag(line)
    if expected_head is not None and prev != expected_head:
        problems.append(f"the last record's hash is {prev}, not the expected head {expected_head}")
    return problems


def verify_chain(path, *, expected_head=None, check=None):
    """verify_bytes on the log at path, and against its head file when that is present. With
    expected_head, from an evaluation report say, the last record's hash must equal that too."""
    return verify_held(Path(path).read_bytes(), head_file(path), expected_head=expected_head, check=check)


def verify_held(data, head, *, expected_head=None, check=None):
    """verify_chain on a log's bytes read some other way, such as from a compressed file, with the path
    of its head file."""
    problems = verify_bytes(data, expected_head=expected_head, check=check)
    head = Path(head)
    if head.exists():
        held = head.read_bytes()
        lines = _split(data)
        last = sha256_tag(lines[-1]) if lines else None
        if not HEAD_FORM.fullmatch(held):
            problems.append(f"{head.name} does not hold one hash written sha256:<hex>")
        elif held.decode("ascii").strip() != last:
            problems.append(f"{head.name} holds {held.decode('ascii').strip()}, "
                            f"but the last record's hash is {last}")
    return problems


class ChainWriter:
    """Appends records to one chained file, and only appends.

    The writer stamps record_id, utc, met_s and prev_hash; callers give the type and body. It
    writes each record whole and flushed to disk, then rewrites the head file. It refuses to write
    if the log's size is not what it last left, which is how it notices another writer or a hand edit.
    """

    def __init__(self, path, *, met_clock, utc_clock, check, next_id, head, size):
        self._path = Path(path)
        self._head_path = head_file(path)
        self._met_clock = met_clock
        self._utc_clock = utc_clock
        self._check = check
        self._next_id = next_id
        self._head = head
        self._size = size
        self._lock = threading.Lock()

    @classmethod
    def create(cls, path, *, met_clock, utc_clock=utc_now, check=None):
        """Start a new log. One that already exists, or whose head file does, is refused: a log is
        never started twice."""
        path = Path(path)
        if head_file(path).exists():
            raise LogError([f"{head_file(path)} already exists"])
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "xb"):
                pass
        except FileExistsError:
            raise LogError([f"{path} already exists"]) from None
        return cls(path, met_clock=met_clock, utc_clock=utc_clock, check=check, next_id=1, head=None, size=0)

    @classmethod
    def resume(cls, path, *, met_clock, utc_clock=utc_now, check=None):
        """Carry on an existing log, after a restart, once its whole chain verifies against its head
        file. A head file one record behind, from a crash between a record and its head or from a
        record added by hand, is refused like any other mismatch."""
        problems = verify_chain(path, check=check)
        data = Path(path).read_bytes()
        lines = _split(data)
        if lines and not head_file(path).exists():
            problems.append(f"{head_file(path).name} is missing")
        if problems:
            raise LogError(problems)
        return cls(path, met_clock=met_clock, utc_clock=utc_clock, check=check, next_id=len(lines) + 1,
                   head=sha256_tag(lines[-1]) if lines else None, size=len(data))

    @property
    def path(self):
        return self._path

    @property
    def head(self):
        """The hash of the last record written, or None before the first."""
        return self._head

    def append(self, type_, body):
        """Stamp, check and write one record, then its head; return the record. A refused record
        writes nothing."""
        with self._lock:
            if not self._path.exists() or self._path.stat().st_size != self._size:
                raise LogError([f"{self._path} changed since this writer last wrote it"])
            record = {"record_id": self._next_id, "utc": self._utc_clock(), "met_s": self._met_clock(),
                      "type": type_, "body": body, "prev_hash": self._head}
            problems = self._check(record) if self._check is not None else []
            if problems:
                raise LogError(problems)
            line = canonical_json(record)
            with open(self._path, "ab") as file:
                file.write(line + b"\n")
                file.flush()
                os.fsync(file.fileno())
            self._head = sha256_tag(line)
            self._next_id += 1
            self._size += len(line) + 1
            self._write_head()
            return record

    def _write_head(self):
        # Written beside the head file and moved over it, so the head file is never half written.
        spare = self._head_path.with_name(self._head_path.name + ".new")
        with open(spare, "wb") as file:
            file.write(self._head.encode("ascii") + b"\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(spare, self._head_path)
