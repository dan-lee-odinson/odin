"""A run's event log and its truth file (CONTRACT.md §12, §8.3).

runs/<run_id>/events.jsonl is the record of the run. Only the harness and BALDUR-0 write it, through
the EventLog they hold. ODIN's records reach it through submit_agent and submit_report, which take
the bodies of POST /log/agent and POST /report, and the writer stamps the record ID, time and chain
hash.

Fault onsets and the simulator's true state go to runs/<run_id>/truth.jsonl instead, through a
TruthLog. The event log refuses every type §12 does not list, so truth cannot be written into it. A
scored run's truth file is committed gzip-compressed, as truth.jsonl.gz; a development run's stays
plain (the Director's ruling on U36, 27 October 2026).
"""

import gzip
import json
from pathlib import Path

from contract.validate import SCHEMA_DIR, check
from log.chain import ChainWriter, LogError, head_file, utc_now, verify_chain, verify_held

EVENTS = "events.jsonl"
TRUTH = "truth.jsonl"
TRUTH_COMPRESSED = TRUTH + ".gz"


def _types(schema):
    return tuple(json.loads((SCHEMA_DIR / f"{schema}.schema.json").read_text(encoding="utf-8"))
                 ["properties"]["type"]["enum"])


TYPES = _types("log_record")
# What ODIN writes, by the Director's ruling on U21: seven types through POST /log/agent, and REPORT
# through POST /report. Nothing else may write them.
ODIN_TYPES = _types("log_agent") + ("REPORT",)


def check_record(record):
    """A record against the event log's schema, its body included where its type has a schema."""
    return check("log_record", record)


def check_truth_record(record):
    """A record against the truth file's schema, log/truth_record.schema.json: TRUE_STATE, FAULT_ONSET
    and SCRIPTED_COMMAND_DROPPED, as the wrapper writes them (the Director's rulings on U35 and U36)."""
    return check("truth_record", record, schema_dir=Path(__file__).resolve().parent)


def _named(path, name):
    if Path(path).name != name:
        raise LogError([f"{path} is not named {name}"])


class _Log:
    NAME = None
    CHECK = None

    def __init__(self, writer):
        self._writer = writer

    @classmethod
    def create(cls, path, *, met_clock, utc_clock=utc_now):
        """Start the file for a new run."""
        _named(path, cls.NAME)
        return cls(ChainWriter.create(path, met_clock=met_clock, utc_clock=utc_clock, check=cls.CHECK))

    @classmethod
    def resume(cls, path, *, met_clock, utc_clock=utc_now):
        """Carry on the file after a restart, once its chain verifies."""
        _named(path, cls.NAME)
        return cls(ChainWriter.resume(path, met_clock=met_clock, utc_clock=utc_clock, check=cls.CHECK))

    @property
    def path(self):
        return self._writer.path

    @property
    def head(self):
        """The hash of the last record written: what verify_chain's expected_head is checked against."""
        return self._writer.head

    def append(self, type_, body):
        return self._writer.append(type_, body)


class EventLog(_Log):
    """runs/<run_id>/events.jsonl. The harness and BALDUR-0 call append; ODIN's records come through
    submit_agent and submit_report."""

    NAME = EVENTS
    CHECK = staticmethod(check_record)

    def append(self, type_, body):
        """For the harness and BALDUR-0. ODIN's records come only through submit_agent and submit_report."""
        if type_ in ODIN_TYPES:
            raise LogError([f"{type_} is ODIN's record, which comes only through POST /log/agent or POST /report"])
        return self._writer.append(type_, body)

    def submit_agent(self, submission):
        """The body of POST /log/agent (§8.3): one of ODIN's seven record types, as {type, body}."""
        problems = check("log_agent", submission)
        if problems:
            raise LogError(problems)
        return self._writer.append(submission["type"], submission["body"])

    def submit_report(self, report):
        """The body of POST /report (§8.3), logged as a REPORT. It never reaches BALDUR-0's request path."""
        problems = check("report", report)
        if problems:
            raise LogError(problems)
        return self._writer.append("REPORT", report)


class TruthLog(_Log):
    """runs/<run_id>/truth.jsonl: fault onsets and the simulator's true state, for evaluation only.
    ODIN never reads it (§12)."""

    NAME = TRUTH
    CHECK = staticmethod(check_truth_record)


def verify_event_log(path, *, expected_head=None):
    """Every way an event log fails: its chain, and each record against the schema."""
    return verify_chain(path, expected_head=expected_head, check=check_record)


def compress_truth(path):
    """A scored run's truth file made ready for its commit: truth.jsonl compressed to truth.jsonl.gz
    beside it and its head file, truth.head (U36). The gzip header holds no file name or time, so a
    file always compresses to the same bytes. The plain file is removed only once the compressed one
    reads back to its bytes, and an existing truth.jsonl.gz is never overwritten."""
    path = Path(path)
    _named(path, TRUTH)
    data = path.read_bytes()
    packed = path.with_name(TRUTH_COMPRESSED)
    with open(packed, "xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as out:
        out.write(data)
    if gzip.decompress(packed.read_bytes()) != data:
        packed.unlink()
        raise LogError([f"{packed.name} did not read back to the bytes of {path.name}; {path.name} is kept"])
    path.unlink()
    return packed


def verify_truth(path, *, expected_head=None):
    """Every way a truth file fails, plain or compressed: its chain, its head file truth.head, and each
    record against the truth schema."""
    path = Path(path)
    if path.name == TRUTH_COMPRESSED:
        return verify_held(gzip.decompress(path.read_bytes()), head_file(path.with_name(TRUTH)),
                           expected_head=expected_head, check=check_truth_record)
    _named(path, TRUTH)
    return verify_chain(path, expected_head=expected_head, check=check_truth_record)
