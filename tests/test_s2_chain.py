"""The chain check (00_HANDOFF.md §4, S2: "The chain check passes, and fails after a one-byte change";
CONTRACT.md §12). Each red case changes a copy of the example log, or its head file, and the check
must fail.

The chain alone catches a change to any record but the last, since the next record's prev_hash holds
its hash. A change to the last record shows only against the head: the head file beside the log
(events.head), which the chain check compares when it is present, or for a scored run the final hash
in the evaluation report (the Director's ruling on U23, 26 October 2026).
"""

import json

import pytest

from log.canonical import canonical_json, sha256_tag
from log.chain import verify_bytes, verify_chain
from tests.test_s2_event_log import EXAMPLE_HEAD, EXAMPLE_LOG, write_example_log

DATA = EXAMPLE_LOG.read_bytes()
LINES = DATA.split(b"\n")[:-1]
TYPES = [json.loads(line)["type"] for line in LINES]
HEAD = sha256_tag(LINES[-1])
LAST_LINE_START = len(DATA) - len(LINES[-1]) - 1


def at(type_):
    return TYPES.index(type_)


def _join(lines):
    return b"".join(line + b"\n" for line in lines)


def _changed(index, change):
    index %= len(LINES)
    record = json.loads(LINES[index])
    change(record)
    return LINES[:index] + [canonical_json(record)] + LINES[index + 1:]


def _check(data, **kwargs):
    return verify_bytes(data, **kwargs)


def _in_folder(tmp_path, data, head=None):
    log = tmp_path / "events.jsonl"
    log.write_bytes(data)
    if head is not None:
        (tmp_path / "events.head").write_bytes(head)
    return log


def test_example_chain_verifies_against_its_head(tmp_path):
    assert HEAD == write_example_log(tmp_path / "events.jsonl").head
    assert EXAMPLE_HEAD.read_bytes() == HEAD.encode("ascii") + b"\n"
    assert _check(DATA, expected_head=HEAD) == []


def test_red_every_one_byte_change_is_caught_against_the_head():
    missed = []
    for offset in range(len(DATA)):
        data = bytearray(DATA)
        data[offset] ^= 0x01
        if _check(bytes(data), expected_head=HEAD) == []:
            missed.append(offset)
    assert missed == [], f"one-byte changes at these offsets were not caught: {missed}"


def test_red_every_one_byte_change_before_the_last_record_is_caught_by_the_chain_alone():
    missed = []
    for offset in range(LAST_LINE_START):
        data = bytearray(DATA)
        data[offset] ^= 0x01
        if _check(bytes(data)) == []:
            missed.append(offset)
    assert missed == [], f"one-byte changes at these offsets were not caught: {missed}"


def test_a_change_to_the_last_record_shows_only_against_the_head():
    lines = _changed(-1, lambda record: record.update(met_s=record["met_s"] + 1))
    assert _check(_join(lines)) == []
    assert _check(_join(lines), expected_head=HEAD) != []


def test_red_a_rewritten_tail_is_caught_against_the_head():
    lines = _changed(at("REQUEST"), lambda record: record["body"].update(parameters={"state": "OFF"}))
    for index in range(at("REQUEST") + 1, len(lines)):
        record = json.loads(lines[index])
        record["prev_hash"] = sha256_tag(lines[index - 1])
        lines[index] = canonical_json(record)
    assert _check(_join(lines)) == [], "every link was recomputed, so the chain alone cannot tell"
    assert _check(_join(lines), expected_head=HEAD) != []


# The head file (U23)

def test_the_chain_check_compares_the_head_file_when_present(tmp_path):
    assert verify_chain(_in_folder(tmp_path, DATA, EXAMPLE_HEAD.read_bytes())) == []


def test_without_a_head_file_the_chain_alone_is_checked(tmp_path):
    lines = _changed(-1, lambda record: record.update(met_s=record["met_s"] + 1))
    assert verify_chain(_in_folder(tmp_path, _join(lines))) == []


HEAD_TAMPERS = {
    "the last record changed": lambda: (_join(_changed(-1, lambda r: r.update(met_s=r["met_s"] + 1))),
                                        EXAMPLE_HEAD.read_bytes()),
    "a record appended without its head": lambda: (DATA + LINES[-1] + b"\n", EXAMPLE_HEAD.read_bytes()),
    "the last record dropped": lambda: (_join(LINES[:-1]), EXAMPLE_HEAD.read_bytes()),
    "the head file holding another hash": lambda: (DATA, sha256_tag(b"").encode("ascii") + b"\n"),
    "the head file holding a hash in capitals": lambda: (DATA, HEAD.upper().encode("ascii") + b"\n"),
    "the head file holding two hashes": lambda: (DATA, EXAMPLE_HEAD.read_bytes() * 2),
    "the head file empty": lambda: (DATA, b""),
    "a head file beside an empty log": lambda: (b"", EXAMPLE_HEAD.read_bytes()),
}


@pytest.mark.parametrize("tamper", HEAD_TAMPERS)
def test_red_the_head_file_catches(tmp_path, tamper):
    data, head = HEAD_TAMPERS[tamper]()
    assert verify_chain(_in_folder(tmp_path, data, head)) != []


# The chain alone

def _reordered(line):
    record = json.loads(line)
    return json.dumps(dict(reversed(list(record.items()))), separators=(",", ":"), ensure_ascii=False).encode()


TAMPERS = {
    "a middle record deleted": lambda: _join(LINES[:3] + LINES[4:]),
    "two records swapped": lambda: _join(LINES[:2] + [LINES[3], LINES[2]] + LINES[4:]),
    "a record repeated": lambda: _join(LINES[:3] + [LINES[2]] + LINES[3:]),
    "a blank line inserted": lambda: _join(LINES[:2] + [b""] + LINES[2:]),
    "whitespace added inside a record": lambda: _join(LINES[:2] + [LINES[2].replace(b'":', b'": ', 1)] + LINES[3:]),
    "a record's keys reordered": lambda: _join(LINES[:2] + [_reordered(LINES[2])] + LINES[3:]),
    "a record renumbered": lambda: _join(_changed(2, lambda r: r.update(record_id=30))),
    "the first record given a prev_hash": lambda: _join(_changed(0, lambda r: r.update(prev_hash=sha256_tag(b"")))),
    "a field added to a record": lambda: _join(_changed(2, lambda r: r.update(writer="BALDUR-0"))),
    "a decision changed": lambda: _join(_changed(at("DECISION"), lambda r: r["body"].update(decision="REFUSE"))),
    "a request's bundle hash changed": lambda: _join(_changed(at("REQUEST"), lambda r: r["body"].update(
        agent_input_hash=sha256_tag(b"another bundle")))),
    "line endings turned to CRLF": lambda: DATA.replace(b"\n", b"\r\n"),
    "the file cut short": lambda: DATA[:-20],
    "the first record dropped": lambda: _join(LINES[1:]),
}


@pytest.mark.parametrize("tamper", TAMPERS)
def test_red_the_chain_check_catches(tamper):
    assert _check(TAMPERS[tamper]()) != []
