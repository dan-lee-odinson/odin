#!/usr/bin/env python3
"""VERDA's converter: run folders and the Director's passes in, timeline files out.

    python convert/verda_convert.py RUN_FOLDER [RUN_FOLDER ...]
    python convert/verda_convert.py --all FOLDER_OF_RUNS
        options: --out DIR (default page/timelines)  --dictionary PATH  --no-truth
                 --passes FOLDER_OF_PASSES  --plans FOLDER_OF_PLANS  --scripted FILE
                 --clips FOLDER_OF_CLIPS

For each run folder it reads events.jsonl and events.head, the saved turn
bundles in inputs/, and truth.jsonl and truth.head when present. A record file
may be gzip-compressed (truth.jsonl.gz, as phase 2's scored runs keep it); its
chain and head are checked on the records inside. A file in the run folder that
the converter does not read is never skipped silently: the timeline's warnings
name it, and the page and the converter's output show them. It checks the
log's hash chain (CONTRACT.md v0.6, sections 4 and 12) and each saved bundle's
hash, and writes <out>/<run_id>.js, the timeline file the page loads. It then
rewrites <out>/index.js, the list of timeline files the page offers, with each
file's SHA-256. With --clips it copies each animation clip and its sync file
into <out>/clips/ and lists them in index.js too (convert/clips.py). It writes
nothing else and never writes into a run folder.

The timeline file is data only: one JSON object, the "verda-timeline" format,
assigned to window.VERDA_TIMELINES[<id>]. The format is described in README.md.
It names its sources, so a pass the Director flew can sit in the same file as a
run ODIN flew.

Telemetry comes from two places, kept apart and labeled:
  - "odin": what ODIN's turn bundles held. Each bundle's observation (all points
    of the newest frame, with the limit states it carried) and its history rows
    (every received frame of the points its procedures name).
  - "truth": the simulator's true state, one record per tick, from truth.jsonl.
    ODIN never reads it. Shown only as "simulator truth, never seen by ODIN".
  - "director": the Director's own pass of the same scenario, flown in HUGINN:
    the commands he sent and the frames his ground station received
    (convert/pass_records.py). It is a separate flight, on the same MET axis.
  - "scenario": the commands the scenario sent by itself, which his pass
    carried (convert/scripted_commands.py). They sit on his side, apart from
    his own commands, and are never his. ODIN's runs keep the ones before
    contact and drop the ones in contact.

With --passes, each run is paired with the Director's pass flown under its plan,
or else of its scenario whose frames its MET span covers, and each pass that no
run pairs with gets a timeline of its own, beside its plan's contact window
(--plans). With --scripted, each pass's timeline also shows the scenario's own
commands.

A run paired with a pass is written as two files. <run_id>.js is the run's own
timeline, byte for byte what the converter makes of the run alone: an animation
clip of the run pins that file's SHA-256, so nothing on the Director's side of a
comparison ever changes it. <run_id>.beside.js holds what pairing adds (his pass,
the scenario's commands, the lanes they take) and pins the SHA-256 of the run's
file it was made for. The page loads both and puts them together; the converter
checks, before writing, that the two put together are the paired timeline.
"""

import argparse
import copy
import gzip
import hashlib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import clips  # noqa: E402
import huginn_dictionary  # noqa: E402
import pass_records  # noqa: E402
import record_types  # noqa: E402
import scripted_commands  # noqa: E402

FORMAT = "verda-timeline"
FORMAT_VERSION = 1

ODIN = "odin"
TRUTH = "truth"
TRUTH_LABEL = "Simulator truth, never seen by ODIN"
DIRECTOR = "director"
SCENARIO = "scenario"

DEFAULT_OUT = HERE.parent / "page" / "timelines"
DICTIONARY_CANDIDATES = (
    HERE.parent / "inputs" / "dictionaries" / "HUGINN" / "tlm_cmd.yaml",
    HERE.parent.parent / "deps" / "huginn" / "defs" / "tlm_cmd.yaml",
)

# The simulator's true state, mapped to the dictionary's points. Checked against
# every observation in the practice runs by tests/test_convert.py.
TRUTH_POINTS = {
    "EPS_BATT_V": ("eps", "battery_v"),
    "EPS_BATT_I": ("eps", "battery_i"),
    "EPS_BATT_SOC": ("eps", "soc_pct"),
    "EPS_SA1_I": ("eps", "string_i", 0),
    "EPS_SA2_I": ("eps", "string_i", 1),
    "EPS_BUS_V": ("eps", "bus_v"),
    "EPS_LOAD_I": ("eps", "load_i"),
    "EPS_MODE": ("eps", "mode"),
    "ADM_ECLIPSE": ("eps", "illuminated", {True: "SUNLIT", False: "ECLIPSE"}),
    "PLD_STATE": ("eps", "payload_on", {True: "ON", False: "OFF"}),
    "PLD_RATE": ("eps", "pld_rate_hz"),
    "CDH_FRAME_CNT": ("cdh", "frame_count"),
    "CDH_CMD_ACC_CNT": ("cdh", "acc_count"),
    "CDH_CMD_REJ_CNT": ("cdh", "rej_count"),
    "CDH_REJ_REASON": ("cdh", "rej_reason"),
}

# The telemetry lanes V1 shows: (lane id, label, points, kind).
TELEMETRY_LANES = (
    ("tlm:EPS_BATT_V", "Battery voltage", ("EPS_BATT_V",), "chart"),
    ("tlm:EPS_BATT_SOC", "Battery state of charge", ("EPS_BATT_SOC",), "chart"),
    ("tlm:EPS_LOAD_I", "Load current", ("EPS_LOAD_I",), "chart"),
    ("tlm:EPS_SA", "Solar-array strings 1 and 2", ("EPS_SA1_I", "EPS_SA2_I"), "chart"),
    ("tlm:PLD_RATE", "Payload rate", ("PLD_RATE",), "chart"),
    ("state:PLD_STATE", "Payload state", ("PLD_STATE",), "state"),
    ("state:EPS_MODE", "Spacecraft mode", ("EPS_MODE",), "state"),
)

STATE_SEVERITY = {
    "EPS_MODE": {"NOMINAL": "good", "LOW_POWER": "warn", "SAFE": "bad"},
    "PLD_STATE": {"ON": "info", "OFF": "muted"},
    "ADM_ECLIPSE": {"SUNLIT": "info", "ECLIPSE": "muted"},
}

# Lane heights in pixels, so that every lane of a run beside a pass fits a 1920 x 1080 screen.
CHART_H, STATE_H, AGE_H = 48, 38, 56
STRIP_H = 26  # the strip above the age chart for what a ground seat's bundles recorded
PAIRED_CHART_H = 44  # a chart's height beside the Director's pass

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RunFolderError(Exception):
    pass


def canonical_json(value):
    """CONTRACT.md section 4's canonical JSON, as bytes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_tag(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


# The record files of a run folder, each as JSON Lines or gzip-compressed JSON Lines.
RECORD_FILES = ("events", "truth")
HEAD_SUFFIX = ".head"


def record_file(run_dir, stem):
    """The run folder's <stem>.jsonl, or its <stem>.jsonl.gz; None if it has neither."""
    for name in (stem + ".jsonl", stem + ".jsonl.gz"):
        if (Path(run_dir) / name).is_file():
            return Path(run_dir) / name
    return None


def record_bytes(path):
    """A record file's lines as written: a .gz file is read through gzip."""
    data = Path(path).read_bytes()
    return gzip.decompress(data) if Path(path).name.endswith(".gz") else data


def unread_files(run_dir, read):
    """The files at the top of a run folder the converter did not read, for its warnings."""
    return sorted(p.name for p in Path(run_dir).iterdir() if p.is_file() and p.name not in read)


def read_chain(path, head_path):
    """Reads a hash-chained JSON Lines file and checks its chain and head.

    Returns (records, check). Each line must be its record's canonical JSON, its
    prev_hash the hash of the line before (null on the first), and its record_id
    its line number. The head file holds the hash of the last line. A .gz file
    is checked on the lines inside it.
    """
    try:
        data = record_bytes(path)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        raise RunFolderError("%s cannot be read: %s" % (Path(path).name, exc))
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    records, problems = [], []
    prev = None
    for number, line in enumerate(lines, start=1):
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append("line %d is not JSON (%s)" % (number, exc))
            prev = sha256_tag(line)
            continue
        if not isinstance(record, dict):
            problems.append("line %d is not a record" % number)
        else:
            if canonical_json(record) != line:
                problems.append("line %d is not its record's canonical JSON" % number)
            if record.get("prev_hash") != prev:
                problems.append("line %d's prev_hash is not the hash of line %d" % (number, number - 1))
            if record.get("record_id") != number:
                problems.append("line %d has record_id %r" % (number, record.get("record_id")))
            records.append(record)
        prev = sha256_tag(line)
    head_path = Path(head_path)
    if not head_path.exists():
        head = "MISSING"
    elif head_path.read_text(encoding="utf-8").strip() == (prev or ""):
        head = "MATCHES"
    else:
        head = "DIFFERS"
        problems.append("%s does not hold the hash of the last line" % head_path.name)
    check = {
        "file": Path(path).name,
        "records": len(records),
        "chain": "VERIFIED" if not problems else "BROKEN",
        "head": head,
        "problems": problems[:20],
    }
    return records, check


def load_bundle(run_dir, tag):
    """Reads a saved turn bundle by its hash and checks the bytes match it."""
    if not isinstance(tag, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", tag):
        return None, "bad bundle hash %r" % (tag,)
    path = Path(run_dir) / "inputs" / tag[len("sha256:"):]
    if not path.exists():
        return None, "saved input %s is missing" % path.name
    data = path.read_bytes()
    if sha256_tag(data) != tag:
        return None, "saved input %s does not match its hash" % path.name
    try:
        return json.loads(data.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "saved input %s is not JSON (%s)" % (path.name, exc)


def _truth_value(body, mapping):
    section = body.get(mapping[0])
    if not isinstance(section, dict):
        return None
    value = section.get(mapping[1])
    if len(mapping) > 2:
        extra = mapping[2]
        if isinstance(extra, int):
            value = value[extra] if isinstance(value, list) and len(value) > extra else None
        elif isinstance(extra, dict):
            value = extra.get(value)
    return value


def _fmt_params(parameters):
    if not parameters:
        return ""
    return " ".join("%s=%s" % (k, parameters[k]) for k in sorted(parameters))


def _first_failure(decision_body):
    for check in decision_body.get("checks") or []:
        if check.get("result") == "FAIL":
            return {"check": check.get("check"), "reason": check.get("reason"), "detail": check.get("detail")}
    return None


def _trigger_text(trigger):
    kind = trigger.get("type")
    detail = trigger.get("detail") or {}
    if kind == "LIMIT_CHANGE":
        return "%s %s %s->%s" % (kind, detail.get("point"), detail.get("from"), detail.get("to"))
    if kind in ("MODE_CHANGE", "STALENESS_CHANGE"):
        return "%s %s->%s" % (kind, detail.get("from"), detail.get("to"))
    if kind == "DECISION":
        return "DECISION %s" % detail.get("decision")
    if kind == "PLAN_START":
        return "PLAN_START %s" % detail.get("plan_id")
    if kind == "FEED_REPORT":
        return "FEED_REPORT %s" % detail.get("feed")
    return str(kind)


class _Builder:
    def __init__(self, run_dir, points, include_truth):
        self.run_dir = Path(run_dir)
        self.points = points
        self.include_truth = include_truth
        self.events, self.spans, self.warnings = [], [], []
        self.turns, self.requests, self.series = {}, {}, {}
        self.records = {}
        self.truth_records = {}
        self.integrity = []
        self.header = {}
        self.placed = set()
        self.plan_windows = {}
        self.frames = set()  # MET of every frame some bundle held
        self.observations = []  # (turn MET, observation, turn_id)
        self.truth_kinds = 0  # the kinds of truth flag, each drawn on a row of its own
        self.read_files = set()  # the files at the top of the run folder it read

    # -- helpers ---------------------------------------------------------
    def event(self, lane, met_s, label, severity, shape, refs, **extra):
        item = {"id": "e%d" % (len(self.events) + 1), "lane": lane, "met_s": met_s,
                "label": label, "severity": severity, "shape": shape, "refs": refs}
        item.update(extra)
        self.events.append(item)
        self.placed.update(r for r in refs if r.startswith("log:"))
        return item

    def span(self, lane, start, end, label, severity, refs, **extra):
        item = {"lane": lane, "start": start, "end": end, "label": label,
                "severity": severity, "refs": refs}
        item.update(extra)
        self.spans.append(item)
        self.placed.update(r for r in refs if r.startswith("log:"))
        return item

    def series_for(self, source, point):
        key = "%s:%s" % (source, point)
        if key not in self.series:
            info = self.points.get(point)
            kind = "state" if info and info.get("type") == "enum" else "numeric"
            self.series[key] = {
                "id": key, "source": source, "point": point,
                "units": info.get("units") if info else None,
                "kind": kind,
                "states": info.get("enum_values") if info else None,
                "limits": huginn_dictionary.chart_limits(info),
                "state_severity": STATE_SEVERITY.get(point),
                "samples": {},
            }
        return self.series[key]

    def add_sample(self, source, point, met_s, value, state, provenance):
        series = self.series_for(source, point)
        known = series["samples"].get(met_s)
        if known is not None and known[1] != value:
            self.warnings.append("%s at MET %s: two values for one frame (%r, %r)"
                                 % (series["id"], met_s, known[1], value))
        if known is not None and known[3] == "obs" and provenance != "obs":
            return  # keep the limit state the observation itself carried
        series["samples"][met_s] = [met_s, value, state, provenance]

    # -- the event log ---------------------------------------------------
    def read_log(self):
        path = record_file(self.run_dir, "events")
        if path is None:
            raise RunFolderError("%s has no events.jsonl" % self.run_dir)
        records, check = read_chain(path, self.run_dir / ("events" + HEAD_SUFFIX))
        self.read_files.update({path.name, "events" + HEAD_SUFFIX})
        self.integrity.append(dict(check, label="Event log"))
        for record in records:
            self.records[record["record_id"]] = record
        return records

    def read_truth(self):
        path = record_file(self.run_dir, "truth")
        if not self.include_truth:
            # Left out by choice (--no-truth): not a file the converter could not read.
            self.read_files.update(p.name for p in self.run_dir.iterdir() if p.name.startswith("truth."))
            return []
        if path is None:
            return []
        records, check = read_chain(path, self.run_dir / ("truth" + HEAD_SUFFIX))
        self.read_files.update({path.name, "truth" + HEAD_SUFFIX})
        self.integrity.append(dict(check, label="Simulator truth file"))
        return records

    def skipped_files(self):
        """Says, in the timeline's warnings, which files of the run folder it did not read."""
        for name in unread_files(self.run_dir, self.read_files):
            self.warnings.append("%s was not read: VERDA reads events.jsonl, truth.jsonl, each also as .gz, "
                                 "and their .head files" % name)

    def walk_log(self, records):
        contact_open = None
        rung_open = None
        for record in records:
            rid = record["record_id"]
            ref = "log:%d" % rid
            kind = record.get("type")
            body = record.get("body") or {}
            met = record.get("met_s")
            turn_id = body.get("turn_id") if isinstance(body, dict) else None

            if kind == "RUN_START":
                self.header.update({k: body.get(k) for k in (
                    "run_id", "scenario_id", "phase", "mode", "model_config", "provider",
                    "model_id", "endpoint", "reasoning_effort", "answer_method", "seed")})
                self.event("authority", met, "Run start", "info", "circle", [ref])
            elif kind == "PLAN_CHAIN_VERIFIED":
                ok = body.get("result") == "PASS"
                self.header["plan_chain"] = body.get("result")
                self.header["plans"] = [p.get("plan_id") for p in body.get("plans") or []]
                self.event("authority", met, "Plan chain %s" % body.get("result"),
                           "good" if ok else "bad", "square", [ref])
            elif kind == "ARMING_VERIFIED":
                ok = body.get("result") == "PASS"
                self.header["arming_act_id"] = body.get("act_id")
                self.event("authority", met, "Arming %s %s" % (body.get("result"), body.get("act_id")),
                           "good" if ok else "bad", "square", [ref])
                rung_open = (met, body.get("rung") if ok else "HUMAN_ONLY",
                             None if ok else "NOT_ARMED", [ref])
            elif kind == "PLAN_IN_FORCE":
                self.span("authority", body.get("valid_from_met_s"), body.get("valid_until_met_s"),
                          body.get("plan_id"), "plan", [ref], row=1)
            elif kind == "CONTACT":
                if body.get("state") == "AOS":
                    contact_open = (met, ref)
                elif body.get("state") == "LOS":
                    start, start_ref = contact_open if contact_open else (None, None)
                    refs = [r for r in (start_ref, ref) if r]
                    self.span("contact", start, met, "In contact", "good", refs, row=0)
                    contact_open = None
            elif kind == "REVOKE":
                self.event("authority", met, "Authority revoked", "bad", "flag", [ref])
                if rung_open:
                    self._close_rung(rung_open, met)
                rung_open = (met, "HUMAN_ONLY", "REVOKED", [ref])
            elif kind == "RESTORE":
                accepted = body.get("result") == "ACCEPTED"
                label = "Restore %s" % body.get("result")
                if not accepted:
                    label += " (%s)" % body.get("reason")
                self.event("authority", met, label, "good" if accepted else "bad", "flag", [ref])
                if accepted:
                    if rung_open:
                        self._close_rung(rung_open, met)
                    rung_open = (met, "AI_AUTONOMOUS", None, [ref])
            elif kind == "CHECK_IN":
                self.event("director", met, "Check-in", "director", "circle", [ref],
                           text=body.get("text"), source_kind=body.get("source"))
            elif kind == "RUN_END":
                self.header["run_end"] = {"reason": body.get("reason"), "turns": body.get("turns"),
                                          "detail": body.get("detail"), "met_s": met}
                self.event("authority", met, "Run end %s" % body.get("reason"),
                           "good" if body.get("reason") == "COMPLETE" else "bad", "circle", [ref])
            elif kind in ("REQUEST", "DECISION", "DECISION_VOIDED", "DISPATCH", "OUTCOME"):
                self._request_record(kind, body, met, ref)

            if turn_id is not None and kind in (
                    "TRIGGER", "AGENT_INPUT", "MODEL_CALL", "CANDIDATE", "ANSWER", "MALFORMED",
                    "REPORT", "REQUEST", "ESCALATION", "SPEND", "SPEND_STOP", "TOOL_USE"):
                self._turn_record(kind, body, met, ref, turn_id)
            elif kind not in record_types.SHOWN and kind not in record_types.NOT_SHOWN:
                self.warnings.append("record %d has a type the contract does not list: %r" % (rid, kind))
                self.event("authority", met, "Unlisted record %s" % kind, "warn", "x", [ref])

        end = self.met_end_hint(records)
        if contact_open:
            self.span("contact", contact_open[0], end, "In contact", "good", [contact_open[1]], row=0)
        if rung_open:
            self._close_rung(rung_open, end)

    def met_end_hint(self, records):
        mets = [r.get("met_s") for r in records if isinstance(r.get("met_s"), (int, float))]
        return max(mets) if mets else None

    def _close_rung(self, rung_open, end):
        start, rung, reason, refs = rung_open
        label = rung if not reason else "%s (%s)" % (rung, reason)
        self.span("authority", start, end, label,
                  "good" if rung == "AI_AUTONOMOUS" else "bad", refs, row=2)

    def _turn(self, turn_id):
        if turn_id not in self.turns:
            self.turns[turn_id] = {"turn_id": turn_id, "refs": [], "met_s": None,
                                   "answer": None, "tools": 0, "model_calls": 0,
                                   "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        return self.turns[turn_id]

    def _turn_record(self, kind, body, met, ref, turn_id):
        turn = self._turn(turn_id)
        turn["refs"].append(ref)
        self.placed.add(ref)
        if kind == "TRIGGER":
            turn.update({"met_s": met, "turn_kind": body.get("turn_kind"),
                         "report_kind": body.get("report_kind"),
                         "triggers": body.get("triggers") or [],
                         "bundle_sha256": body.get("bundle_sha256")})
            bundle, problem = load_bundle(self.run_dir, body.get("bundle_sha256"))
            if problem:
                self.warnings.append("turn %s: %s" % (turn_id, problem))
                turn["bundle_problem"] = problem
            else:
                self._bundle(turn, bundle)
        elif kind == "ANSWER":
            answer = body.get("answer") or {}
            if "kind" in answer:
                turn["answer"] = {"kind": answer.get("kind"), "command": answer.get("command"),
                                  "parameters": answer.get("parameters"),
                                  "escalation_kind": answer.get("escalation_kind"),
                                  "urgency": answer.get("urgency"),
                                  "rationale": answer.get("rationale")}
            else:
                turn["answer"] = {"kind": "report"}
        elif kind == "MALFORMED":
            turn["answer"] = {"kind": "malformed", "reason": body.get("reason"), "detail": body.get("detail")}
        elif kind == "MODEL_CALL":
            turn["model_calls"] += 1
            for key, field in (("input_tokens", "input_tokens"), ("output_tokens", "output_tokens")):
                if isinstance(body.get(field), int):
                    turn[key] += body[field]
            if isinstance(body.get("actual_cost_usd"), (int, float)):
                turn["cost_usd"] += body["actual_cost_usd"]
        elif kind == "TOOL_USE":
            turn["tools"] += 1
        elif kind == "SPEND":
            self.header["spend"] = {k: body.get(k) for k in (
                "meta_credit_usd", "baseten_credit_usd", "modal_credit_usd", "out_of_pocket_usd")}
        elif kind == "SPEND_STOP":
            self.event("turns", met, "Spending stop %s" % body.get("stop"), "bad", "x", [ref], turn_id=turn_id)
        elif kind == "REPORT":
            label = "Report %s" % body.get("report_kind")
            self.event("reports", met, label, "report", "square", [ref], turn_id=turn_id,
                       report_kind=body.get("report_kind"))
        elif kind == "ESCALATION":
            urgent = body.get("urgency") == "URGENT"
            self.event("reports", met, "Escalation %s %s" % (body.get("escalation_kind"), body.get("urgency")),
                       "bad" if urgent else "warn", "triangle", [ref], turn_id=turn_id)

    def _bundle(self, turn, bundle):
        observation = bundle.get("observation") or {}
        plan = bundle.get("plan") or {}
        turn["bundle"] = {
            "seat": bundle.get("seat"), "contact_state": bundle.get("contact_state"),
            "rung": bundle.get("rung"), "rung_reason": bundle.get("rung_reason"),
            "plan_id": plan.get("plan_id"), "uses_left": bundle.get("uses_left"),
            "check_in_text": bundle.get("check_in_text"),
            "gateway_feedback": bundle.get("gateway_feedback"),
            "own_requests": len(bundle.get("own_requests") or []),
            "history_columns": (bundle.get("history") or {}).get("columns"),
            "history_rows": len((bundle.get("history") or {}).get("rows") or []),
            "observation": observation,
        }
        self.header.setdefault("seat", bundle.get("seat"))
        window = plan.get("contact_window")
        if isinstance(window, dict):
            self.plan_windows[plan.get("plan_id")] = window
        frame = observation.get("frame_met_s")
        points = observation.get("points")
        if frame is not None and isinstance(points, dict):
            self.frames.add(frame)
            for name, point in points.items():
                if isinstance(point, dict):
                    self.add_sample(ODIN, name, frame, point.get("value"), point.get("limit_state"), "obs")
        self.observations.append((turn["met_s"], observation, turn["turn_id"]))
        history = bundle.get("history") or {}
        columns = history.get("columns") or []
        for row in history.get("rows") or []:
            if not row or len(row) != len(columns):
                continue
            frame_met = row[0]
            self.frames.add(frame_met)
            for name, value in zip(columns[1:], row[1:]):
                state = huginn_dictionary.limit_state(self.points.get(name), value)
                self.add_sample(ODIN, name, frame_met, value, state, "hist")

    def _request(self, request_id):
        if request_id not in self.requests:
            self.requests[request_id] = {"request_id": request_id, "refs": [], "turn_id": None,
                                         "command": None, "parameters": None, "rationale": None,
                                         "met_s": None, "decision": None, "decision_met_s": None,
                                         "refusal": None, "base_class": None, "class": None,
                                         "lease_id": None, "voided": None, "voided_met_s": None,
                                         "dispatch_met_s": None, "route": None, "outcome": None,
                                         "outcome_met_s": None, "outcome_point": None,
                                         "rej_reason": None}
        return self.requests[request_id]

    def _request_record(self, kind, body, met, ref):
        request = self._request(body.get("request_id"))
        request["refs"].append(ref)
        self.placed.add(ref)
        if kind == "REQUEST":
            request.update({"turn_id": body.get("turn_id"), "command": body.get("command"),
                            "parameters": body.get("parameters"), "rationale": body.get("rationale"),
                            "met_s": met, "plan_id": body.get("plan_id")})
        elif kind == "DECISION":
            request.update({"decision": body.get("decision"), "decision_met_s": met,
                            "refusal": _first_failure(body), "base_class": body.get("base_class"),
                            "class": body.get("class"), "lease_id": body.get("lease_id")})
        elif kind == "DECISION_VOIDED":
            request.update({"voided": {"check": body.get("check"), "reason": body.get("reason"),
                                       "detail": body.get("detail")}, "voided_met_s": met})
        elif kind == "DISPATCH":
            request.update({"dispatch_met_s": met, "route": body.get("route")})
            if request["command"] is None:
                request.update({"command": body.get("command"), "parameters": body.get("parameters")})
        elif kind == "OUTCOME":
            request.update({"outcome": body.get("outcome"), "outcome_met_s": met,
                            "outcome_point": body.get("point"), "rej_reason": body.get("rej_reason")})

    # -- the truth file --------------------------------------------------
    def walk_truth(self, records):
        intervals = {}  # name -> [start, last]
        closed = []
        last_met = None
        for record in records:
            kind = record.get("type")
            met = record.get("met_s")
            body = record.get("body") or {}
            if kind == "TRUE_STATE":
                for point, mapping in TRUTH_POINTS.items():
                    value = _truth_value(body, mapping)
                    if value is not None:
                        state = huginn_dictionary.limit_state(self.points.get(point), value)
                        self.add_sample(TRUTH, point, met, value, state, "truth")
                flags = set("fault: %s" % f for f in body.get("faults_active") or [])
                if body.get("frame_generated") is False:
                    flags.add("no frame generated")
                if (body.get("cdh") or {}).get("hk_halted"):
                    flags.add("housekeeping halted")
                if body.get("downlink") is not None:
                    flags.add("downlink: %s" % json.dumps(body.get("downlink"), sort_keys=True))
                for name in list(intervals):
                    if name not in flags:
                        closed.append((name, intervals.pop(name)))
                # In sorted order: a set's order changes with Python's hash seed, and so would the file.
                for name in sorted(flags):
                    if name in intervals:
                        intervals[name][1] = met
                    else:
                        intervals[name] = [met, met]
                last_met = met
            else:
                self.truth_records[record["record_id"]] = record
                ref = "truth:%d" % record["record_id"]
                if kind == "FAULT_ONSET":
                    label = "Fault onset: %s" % body.get("fault")
                elif kind == "SCRIPTED_COMMAND_DROPPED":
                    label = "Scripted command dropped: %s" % body.get("command")
                else:
                    label = "Truth record %s" % kind
                    if kind not in record_types.TRUTH_SHOWN:
                        self.warnings.append("truth record %s has an unrecognized type %r"
                                             % (record["record_id"], kind))
                self.event("truth", met, label, "truth", "diamond", [ref])
        for name, (start, last) in list(intervals.items()):
            closed.append((name, [start, last]))
        rows = {}
        for name, (start, last) in sorted(closed, key=lambda item: item[1][0]):
            row = rows.setdefault(name.split(":")[0], len(rows))
            severity = "bad" if name.startswith("fault") or name.startswith("no frame") else "warn"
            # One row for each kind of flag, below the row of truth's own records. (Rows were once
            # capped at three, which drew a fourth kind over the third, as in phase 2's P4 runs.)
            self.span("truth", start, last + 1, name, severity, [], row=1 + row)
        self.truth_kinds = len(rows)
        return last_met

    # -- derived telemetry age -------------------------------------------
    def frame_age(self, start, coverage_end, limits):
        """The age of the newest frame in ODIN's bundles, at each second.

        Derived by VERDA from the frames the bundles held (observations and
        history rows). Covers the run up to the last turn, the last moment a
        bundle tells us which frames had arrived.
        """
        frames = sorted(self.frames)
        series = {"id": "odin:FRAME_AGE", "source": ODIN, "point": "FRAME_AGE", "units": "s",
                  "kind": "numeric", "states": None, "state_severity": None,
                  "limits": {"rl": None, "yl": None, "yh": limits["yellow_s"], "rh": limits["red_s"]},
                  "derived": True, "samples": {}}
        if not frames or start is None or coverage_end is None:
            self.series[series["id"]] = series
            return
        index = 0
        newest = None
        for t in range(int(start), int(coverage_end) + 1):
            while index < len(frames) and frames[index] <= t:
                newest = frames[index]
                index += 1
            if newest is None:
                continue
            age = t - newest
            if age >= limits["red_s"]:
                state = "RED"
            elif age >= limits["yellow_s"]:
                state = "YELLOW"
            else:
                state = "GREEN"
            series["samples"][t] = [t, age, state, "derived"]
        self.series[series["id"]] = series

    def observation_marks(self):
        """Recorded age, staleness state and ground link at each turn."""
        age = {"id": "odin:AGE_S", "source": ODIN, "point": "AGE_S", "units": "s", "kind": "numeric",
               "states": None, "state_severity": None, "limits": None, "samples": {}}
        for met, observation, turn_id in self.observations:
            if observation.get("age_s") is not None:
                age["samples"][met] = [met, observation.get("age_s"),
                                       observation.get("staleness_state"), "obs"]
            state = observation.get("staleness_state")
            link = observation.get("ground_link")
            if state is not None:
                self.event("staleness", met, "Ground staleness %s" % state,
                           {"GREEN": "good", "YELLOW": "warn", "RED": "bad"}.get(state, "info"),
                           "circle", ["turn:%d" % turn_id], turn_id=turn_id)
            if link is not None:
                self.event("staleness", met, "Ground link %s, %s packets" % (link.get("state"), link.get("received_count")),
                           "good" if link.get("state") == "CONNECTED" else "bad", "square",
                           ["turn:%d" % turn_id], turn_id=turn_id, row=1)
        self.series[age["id"]] = age

    # -- turn and request events -----------------------------------------
    def turn_events(self):
        for turn_id in sorted(self.turns):
            turn = self.turns[turn_id]
            triggers = ", ".join(_trigger_text(t) for t in turn.get("triggers") or [])
            answer = turn.get("answer") or {}
            kind = answer.get("kind")
            if kind == "command":
                said = "command %s %s" % (answer.get("command"), _fmt_params(answer.get("parameters")))
                severity = "odin"
            elif kind == "escalation":
                said = "escalation %s" % answer.get("escalation_kind")
                severity = "warn"
            elif kind == "malformed":
                said = "MALFORMED %s" % answer.get("reason")
                severity = "bad"
            elif kind == "report":
                said = "report"
                severity = "report"
            elif kind == "none":
                said = "no action"
                severity = "quiet"
            else:
                said = "no answer recorded"
                severity = "warn"
            turn["summary"] = "Turn %d (%s): %s -> %s" % (
                turn_id, turn.get("turn_kind") or "?", triggers or "no trigger recorded", said.strip())
            if turn.get("met_s") is None:
                turn["met_s"] = self._first_met(turn["refs"])
            self.event("turns", turn["met_s"], "T%d %s" % (turn_id, said.strip()), severity,
                       "x" if kind == "malformed" else "diamond", ["turn:%d" % turn_id], turn_id=turn_id)

    def _first_met(self, refs):
        for ref in refs:
            record = self.records.get(int(ref.split(":")[1]))
            if record is not None:
                return record.get("met_s")
        return None

    def request_rows(self):
        out = []
        for request in self.requests.values():
            if request["met_s"] is None:
                request["met_s"] = self._first_met(request["refs"])
            parts = ["%s %s" % (request["command"], _fmt_params(request["parameters"]))]
            if request["decision"] == "ALLOW":
                parts.append("ALLOW")
            elif request["decision"] == "REFUSE":
                failure = request["refusal"] or {}
                parts.append("REFUSE %s %s" % (failure.get("check"), failure.get("reason")))
            if request["voided"]:
                parts.append("VOIDED %s %s" % (request["voided"]["check"], request["voided"]["reason"]))
            if request["dispatch_met_s"] is not None:
                parts.append("sent")
            if request["outcome"]:
                parts.append(request["outcome"])
            request["summary"] = " -> ".join(p.strip() for p in parts)
            if request["outcome"] == "ACCEPTED":
                request["status"] = "good"
            elif request["decision"] == "REFUSE" or request["outcome"] == "REJECTED" or request["voided"]:
                request["status"] = "bad"
            elif request["outcome"] == "NO_ACKNOWLEDGEMENT":
                request["status"] = "warn"
            else:
                request["status"] = "info"
            out.append(request)
        out.sort(key=lambda r: (r["met_s"] if r["met_s"] is not None else 0))
        return out


def build_timeline(run_dir, dictionary_path, include_truth=True):
    """Builds the timeline object for one run folder."""
    run_dir = Path(run_dir)
    points = huginn_dictionary.read_points(dictionary_path)
    builder = _Builder(run_dir, points, include_truth)

    records = builder.read_log()
    builder.walk_log(records)
    truth_records = builder.read_truth()
    builder.skipped_files()
    truth_end = builder.walk_truth(truth_records) if truth_records else None

    run_id = builder.header.get("run_id") or run_dir.name
    if not _SAFE_ID.match(str(run_id)):
        raise RunFolderError("run_id %r cannot name a file" % (run_id,))

    mets = [r.get("met_s") for r in records if isinstance(r.get("met_s"), (int, float))]
    ends = [s.get("end") for s in builder.spans if isinstance(s.get("end"), (int, float))]
    start = min(mets) if mets else 0
    end = max(mets + ends + ([truth_end] if truth_end is not None else [])) if mets else 0

    for plan_id, window in builder.plan_windows.items():
        builder.span("contact", window.get("aos_met_s"), window.get("los_met_s"),
                     "Plan %s contact window" % plan_id, "planned", [], row=1)

    turn_mets = [t["met_s"] for t in builder.turns.values() if t.get("met_s") is not None]
    builder.frame_age(start, max(turn_mets) if turn_mets else None,
                      huginn_dictionary.staleness_limits(points))
    builder.observation_marks()
    builder.turn_events()
    requests = builder.request_rows()

    seat = builder.header.get("seat")
    recorded = any(e["lane"] == "staleness" for e in builder.events)
    staleness_short = "Line derived, marks recorded" if recorded else "Line: newest-frame age, derived"
    if seat == "ONBOARD":
        staleness_short = "Onboard seat: none recorded"
        staleness_note = ("Onboard seat: the ground staleness monitor and the ground link are the "
                          "ground seat's, so the bundles carry none (null by contract). The line is "
                          "the age of the newest frame in ODIN's bundles, derived by VERDA.")
    else:
        staleness_note = ("The line is the age of the newest frame in ODIN's bundles, derived by VERDA. "
                          "Dots on it are the age each turn's observation recorded. Above the chart are the "
                          "ground staleness state (circles) and the ground link (squares) the bundles recorded.")

    lanes = [
        {"id": "contact", "label": "Contact", "kind": "track", "height": 30, "rows": 2},
        {"id": "authority", "label": "Plan and authority", "kind": "track", "height": 48, "rows": 3},
        {"id": "director", "label": "The Director's check-ins", "kind": "track", "height": 30, "rows": 1},
        {"id": "turns", "label": "ODIN's turns", "kind": "track", "height": 38, "rows": 1},
        {"id": "reports", "label": "ODIN's reports and escalations", "kind": "track", "height": 30, "rows": 1},
        {"id": "commands", "label": "ODIN's requests, BALDUR-0", "kind": "requests", "height": 36},
    ]
    for lane_id, label, lane_points, kind in TELEMETRY_LANES:
        series_ids = []
        for point in lane_points:
            for source in (ODIN, TRUTH):
                key = "%s:%s" % (source, point)
                if key in builder.series:
                    series_ids.append(key)
        lanes.append({"id": lane_id, "label": label, "kind": kind, "height": CHART_H if kind == "chart" else STATE_H,
                      "series": series_ids, "points": list(lane_points)})
    lanes.append({"id": "staleness", "label": "Telemetry age and ground link", "kind": "chart",
                  "height": AGE_H + (STRIP_H if recorded else 0), "series": ["odin:FRAME_AGE"], "marks": "odin:AGE_S",
                  "points": ["FRAME_AGE"], "note": staleness_note, "note_short": staleness_short,
                  "rows": 2, "strip": recorded})
    if truth_records:
        extra = max(0, builder.truth_kinds - 3)  # a row more than the usual four, 12 px each
        lanes.append({"id": "truth", "label": "Simulator truth", "kind": "track", "height": 54 + 12 * extra,
                      "rows": 4 + extra, "source": TRUTH, "note": TRUTH_LABEL})

    for record in records:
        ref = "log:%d" % record["record_id"]
        if ref not in builder.placed:
            builder.warnings.append("record %d (%s) is drawn nowhere" % (record["record_id"], record.get("type")))

    counts = {}
    for record in records:
        counts[record.get("type")] = counts.get(record.get("type"), 0) + 1
    coverage = []
    for record_type in list(record_types.SHOWN) + list(record_types.NOT_SHOWN):
        coverage.append({"type": record_type, "count": counts.get(record_type, 0),
                         "shown_as": record_types.how_shown(record_type)})

    bundles_checked = sum(1 for t in builder.turns.values() if t.get("bundle_sha256"))
    bundle_problems = [t["bundle_problem"] for t in builder.turns.values() if t.get("bundle_problem")]
    builder.integrity.append({"label": "Saved turn bundles", "file": "inputs/", "records": bundles_checked,
                              "chain": "VERIFIED" if not bundle_problems else "BROKEN",
                              "head": None, "problems": bundle_problems[:20]})

    series = {}
    for key in sorted(builder.series):
        item = dict(builder.series[key])
        item["samples"] = [item["samples"][m] for m in sorted(item["samples"])]
        series[key] = item

    header = dict(builder.header)
    title = "%s" % run_id
    sources = {ODIN: {"label": "ODIN's run %s" % run_id, "kind": "odin_run", "folder": run_dir.name}}
    if truth_records:
        sources[TRUTH] = {"label": TRUTH_LABEL, "kind": "simulator_truth", "folder": run_dir.name}

    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "id": run_id,
        "title": title,
        "met_range": [start, end],
        "sources": sources,
        "header": header,
        "integrity": builder.integrity,
        "lanes": lanes,
        "spans": builder.spans,
        "events": builder.events,
        "requests": requests,
        "series": series,
        "turns": {str(k): builder.turns[k] for k in sorted(builder.turns)},
        "records": {str(k): builder.records[k] for k in sorted(builder.records)},
        "truth_records": {str(k): builder.truth_records[k] for k in sorted(builder.truth_records)},
        "record_types": coverage,
        "warnings": builder.warnings,
    }


# -- the Director's flown pass -------------------------------------------------

def _pass_note(pass_data):
    return ("The Director's own pass of this scenario, flown on %s in HUGINN: a separate flight, on the "
            "same MET axis, from his files commands.csv and telemetry_hk.csv. Each command is placed "
            "between the two frames his ground station received around its UTC time. What follows each "
            "command is read from his command counters (CDH_CMD_ACC_CNT, CDH_CMD_REJ_CNT), derived by VERDA."
            % pass_data["date"])


def _telemetry_lane(lane_id, label, lane_points, kind):
    return {"id": lane_id, "label": label, "kind": kind, "height": CHART_H if kind == "chart" else STATE_H,
            "series": [], "points": list(lane_points)}


SCRIPTED_FILE = "phase2_scripted_commands.json"


def _scenario_note(entry):
    window = entry["contact_window"]
    return ("Commands the scenario sent by itself, each at a set MET, from HUGINN's scenario file for this pass "
            "(the input %s; each command's details give its file and line). They are not the Director's. His pass "
            "carried all of them. ODIN's runs keep the ones before contact and drop the ones in contact, so every "
            "command during a pass is ODIN's (the Director's ruling on U35). The contact window is plan %s's, MET "
            "%d to %d. What his telemetry showed after each is read from his command counters, derived by VERDA."
            % (SCRIPTED_FILE, entry["plan_id"], window["aos_met_s"], window["los_met_s"]))


def add_pass(timeline, pass_data, plan, points, scripted=None):
    """Puts the Director's pass into a timeline as the source "director".

    With `scripted` (scripted_commands.read), the commands the scenario sent by
    itself go beside his, as the source "scenario"."""
    name = pass_data["name"]
    timeline["sources"][DIRECTOR] = {
        "label": "The Director's pass %s, flown in HUGINN" % name, "kind": "director_pass", "folder": name,
        "date": pass_data["date"], "plan_id": plan["plan_id"] if plan else None, "files": pass_data["files"]}
    timeline["header"]["pass"] = {"name": name, "date": pass_data["date"], "tag": pass_data["tag"],
                                  "plan_id": plan["plan_id"] if plan else None,
                                  "scenario_id": plan["scenario_id"] if plan else None}

    # His telemetry: every frame, for the points the lanes draw.
    lane_points = [p for _, _, pts, _ in TELEMETRY_LANES for p in pts]
    for point in lane_points:
        info = points.get(point)
        samples = [[f["met_s"], f["values"][point], pass_records.limit_state(points, point, f["values"][point]), "pass"]
                   for f in pass_data["frames"] if point in f["values"]]
        if not samples:
            continue
        timeline["series"]["%s:%s" % (DIRECTOR, point)] = {
            "id": "%s:%s" % (DIRECTOR, point), "source": DIRECTOR, "point": point,
            "units": info.get("units") if info else None,
            "kind": "state" if info and info.get("type") == "enum" else "numeric",
            "states": info.get("enum_values") if info else None,
            "limits": huginn_dictionary.chart_limits(info), "state_severity": STATE_SEVERITY.get(point),
            "samples": samples}
    limits = huginn_dictionary.staleness_limits(points)
    timeline["series"]["%s:FRAME_AGE" % DIRECTOR] = {
        "id": "%s:FRAME_AGE" % DIRECTOR, "source": DIRECTOR, "point": "FRAME_AGE", "units": "s",
        "kind": "numeric", "states": None, "state_severity": None, "derived": True,
        "limits": {"rl": None, "yl": None, "yh": limits["yellow_s"], "rh": limits["red_s"]},
        "samples": pass_records.frame_age(pass_data, limits)}

    # His commands, each with the rows it was placed from and what his counters showed next.
    records = timeline.setdefault("pass_records", {})
    commands = []
    by_line = {f["line"]: f for f in pass_data["frames"]}
    for c in pass_data["commands"]:
        refs = ["pass:c%d" % c["line"]]
        records["c%d" % c["line"]] = {"file": pass_records.COMMANDS_FILE, "line": c["line"], "fields": c["fields"]}
        frame_lines = list(c["frame_lines"])
        if c["outcome"].get("line"):
            frame_lines.append(c["outcome"]["line"])
        for line in frame_lines:
            refs.append("pass:h%d" % line)
            records["h%d" % line] = {"file": pass_records.TELEMETRY_FILE, "line": line, "fields": by_line[line]["fields"]}
        kind = c["outcome"]["kind"]
        commands.append({
            "id": "pc%d" % c["line"], "line": c["line"], "command": c["command"], "parameters": c["parameters"],
            "utc": c["utc"], "met_s": c["met_s"], "met_basis": c["met_basis"],
            "outcome": c["outcome"], "outcome_met_s": c["outcome"].get("met_s"),
            "summary": "%s -> sent -> %s" % (("%s %s" % (c["command"], _fmt_params(c["parameters"]))).strip(),
                                             {"unchanged": "no counter change"}.get(kind, kind)),
            "status": {"accepted": "good", "rejected": "bad"}.get(kind, "warn"), "refs": refs})

    # The scenario's own commands, which his pass carried: on his side, never his.
    entry = scripted_commands.for_plan(scripted, plan["plan_id"]) if scripted and plan else None
    scenario = []
    for k, s in enumerate(entry["commands"] if entry else [], start=1):
        result = pass_records.outcome_at_met(pass_data["frames"], s["met_s"])
        refs = []
        for line in (result.get("before_line"), result.get("line")):
            if line:
                refs.append("pass:h%d" % line)
                records["h%d" % line] = {"file": pass_records.TELEMETRY_FILE, "line": line, "fields": by_line[line]["fields"]}
        kind = result["kind"]
        scenario.append({
            "id": "sc%d" % k, "met_s": s["met_s"], "command": s["command"], "parameters": s["parameters"],
            "when": s["when"], "kept_in_odins_runs": s["kept_in_odins_runs"], "source": s["source"],
            "plan_id": entry["plan_id"], "contact_window": entry["contact_window"],
            "outcome": result, "outcome_met_s": result.get("met_s"),
            "summary": "%s, %s: ODIN's runs %s it" % (("%s %s" % (s["command"], _fmt_params(s["parameters"]))).strip(),
                                                    s["when"], "keep" if s["kept_in_odins_runs"] else "drop"),
            "status": {"accepted": "good", "rejected": "bad", "outside": "muted"}.get(kind, "warn"), "refs": refs})
    # A counter change in a span where both his command and the scenario's were sent is credited to neither.
    for mine, theirs, who in ((commands, scenario, "the scenario's"), (scenario, commands, "the Director's")):
        for c in mine:
            shared = pass_records.sharing(c["met_s"], c["outcome"], [(o["met_s"], who, o["command"]) for o in theirs])
            if shared and c["outcome"]["kind"] != "outside":
                c["outcome"] = dict(c["outcome"], shared=[{"met_s": m, "who": w, "command": n} for m, w, n in shared])
                c["outcome"]["text"] += "; %s %s at MET %.2f was sent in the same span, so the change may be its" % (
                    shared[0][1], shared[0][2], shared[0][0])
                c["status"] = "warn"
                c["summary"] += " (span shared with %s %s)" % (shared[0][1], shared[0][2])
    timeline["pass_commands"] = commands
    timeline["scenario_commands"] = scenario
    if scripted:
        timeline["sources"][SCENARIO] = {
            "label": "The scenario's own commands, carried by his pass %s" % name, "kind": "scenario_commands",
            "file": scripted["file"], "sha256": scripted["sha256"], "plan_id": entry["plan_id"] if entry else None}

    # The lanes: his commands beside ODIN's requests, his lines on every telemetry lane.
    lanes = timeline["lanes"]
    ids = [lane["id"] for lane in lanes]
    after = ids.index("commands") + 1 if "commands" in ids else (ids.index("contact") + 1 if "contact" in ids else 0)
    lanes.insert(after, {"id": "pass-commands", "label": "The Director's commands", "kind": "pass-commands",
                         "height": 36, "source": DIRECTOR, "note": _pass_note(pass_data),
                         "note_short": "His pass %s" % name})
    if entry:
        empty = None if scenario else "The scenario sent no command by itself in this pass."
        note, short = _scenario_note(entry), "ODIN's runs drop the in-contact ones"
    elif scripted:
        empty = "The scripted-commands file lists no pass flown under plan %s." % (plan["plan_id"] if plan else "(none)")
        note, short = empty, "Not listed in the file"
    else:
        empty = "Not shown: the converter was given no scripted-commands file (--scripted)."
        note, short = empty, "No file given"
    lanes.insert(after + 1, {"id": "scenario-commands", "label": "The scenario's commands", "kind": "scenario-commands",
                             "height": 36, "source": SCENARIO, "note": note, "note_short": short, "empty": empty})
    by_id = {lane["id"]: lane for lane in lanes}
    for lane_id, label, pts, kind in TELEMETRY_LANES:
        lane = by_id.get(lane_id)
        if lane is None:
            lane = _telemetry_lane(lane_id, label, pts, kind)
            lanes.append(lane)
            by_id[lane_id] = lane
        for point in pts:
            key = "%s:%s" % (DIRECTOR, point)
            if key in timeline["series"] and key not in lane["series"]:
                lane["series"].append(key)
        if kind == "state" and len(lane["series"]) >= 3:
            lane["height"] = STATE_H + 8  # a third row, the Director's
    staleness = by_id.get("staleness")
    if staleness is None:
        staleness = {"id": "staleness", "label": "Telemetry age", "kind": "chart", "height": AGE_H, "series": [],
                     "points": ["FRAME_AGE"], "rows": 2,
                     "note": "The age of the newest frame his ground station had received, derived by VERDA.",
                     "note_short": "His newest frame's age, derived"}
        lanes.append(staleness)
    staleness["series"].append("%s:FRAME_AGE" % DIRECTOR)
    if "truth" in by_id:  # the truth lane stays last
        lanes.remove(by_id["truth"])
        lanes.append(by_id["truth"])
    # Beside his pass, the charts are a little shorter, so that a ground seat's run with every lane
    # fits a 1920 x 1080 screen. This is the paired layout only: a run's own timeline keeps its own.
    for lane in lanes:
        if lane["kind"] == "chart" and lane["id"] != "staleness":
            lane["height"] = min(lane["height"], PAIRED_CHART_H)
        elif lane["id"] == "staleness" and lane.get("strip"):
            lane["height"] = AGE_H + STRIP_H - 8

    ok = not pass_data["problems"]
    timeline["integrity"].append({
        "label": "Director's pass", "kind": "pass_files", "ok": ok, "chain": None, "head": None,
        "records": len(pass_data["frames"]) + len(pass_data["commands"]), "problems": pass_data["problems"][:20],
        "file": name, "files": pass_data["files"],
        "summary": "%d frames, %d commands%s" % (len(pass_data["frames"]), len(pass_data["commands"]),
                                                  "" if pass_records.COMMANDS_FILE in pass_data["files"]
                                                  else " (no commands.csv: he sent none)")})
    if scripted:
        timeline["integrity"].append({
            "label": "Scenario's commands", "kind": "scripted_file", "ok": not scripted["problems"], "chain": None,
            "head": None, "records": len(scenario), "problems": scripted["problems"][:20], "file": scripted["file"],
            "summary": "%d of the scenario's commands for plan %s, each checked against its plan file" % (
                len(scenario), entry["plan_id"]) if entry else "no pass in the file is flown under this plan"})
    low = min([timeline["met_range"][0], pass_data["met_range"][0]] + [c["met_s"] for c in commands])
    high = max([timeline["met_range"][1], pass_data["met_range"][1]] + [c["met_s"] for c in commands])
    timeline["met_range"] = [low, high]
    return timeline


def pass_timeline(pass_data, plan, points, scripted=None):
    """A timeline for a pass no run pairs with yet: the Director's flight beside its plan's window."""
    tid = "pass-%s" % pass_data["name"]
    if not _SAFE_ID.match(tid):
        raise RunFolderError("pass %r cannot name a file" % pass_data["name"])
    spans = []
    lanes = [{"id": "contact", "label": "Plan contact window", "kind": "track", "height": 30, "rows": 1}]
    met_range = list(pass_data["met_range"])
    if plan:
        spans.append({"lane": "contact", "start": plan["aos_met_s"], "end": plan["los_met_s"],
                      "label": "Plan %s contact window" % plan["plan_id"], "severity": "planned", "refs": [], "row": 0})
        met_range = [min(met_range[0], plan["aos_met_s"]), max(met_range[1], plan["los_met_s"])]
    timeline = {
        "format": FORMAT, "format_version": FORMAT_VERSION, "id": tid,
        "title": "The Director's pass %s" % pass_data["name"], "met_range": met_range,
        "sources": {},
        "header": {"phase": 2, "pass_only": True,
                   "scenario_id": plan["scenario_id"] if plan else pass_data["tag"]},
        "integrity": [], "lanes": lanes, "spans": spans, "events": [], "requests": [], "series": {},
        "turns": {}, "records": {}, "truth_records": {}, "record_types": [],
        "warnings": [] if plan else ["no phase-2 plan's contact window holds this pass"],
    }
    return add_pass(timeline, pass_data, plan, points, scripted)


def run_summary(run_dir):
    """A run's scenario, the plans it flew under and its MET span, read from its event log, for pairing it
    with a pass."""
    scenario, mets, plans = None, [], set()
    path = record_file(run_dir, "events")
    for line in (record_bytes(path).decode("utf-8").splitlines() if path else []):
        if line.strip():
            record = json.loads(line)
            if record.get("type") == "RUN_START":
                scenario = record.get("body", {}).get("scenario_id")
            if record.get("type") == "PLAN_IN_FORCE" and record.get("body", {}).get("plan_id"):
                plans.add(record["body"]["plan_id"])
            if isinstance(record.get("met_s"), (int, float)):
                mets.append(record["met_s"])
    return {"scenario": pass_records.scenario_base(scenario), "plans": sorted(plans),
            "met_range": [min(mets), max(mets)] if mets else None}


def pass_for_run(run_dir, passes, plans=()):
    """The Director's pass flown under a plan the run flew under; failing that, the pass of the run's
    scenario that the run's MET span covers most of (at least half).

    A run that starts at MET 0 can cover two passes of its scenario whole (P2a and P2b), so its plan
    decides before its span does."""
    summary = run_summary(run_dir)
    flown = [p for p in passes if (pass_records.plan_for(p, plans) or {}).get("plan_id") in summary["plans"]]
    if len(flown) == 1:
        return flown[0]
    best, score = None, 0.5
    if summary["met_range"] is None:
        return None
    for p in passes:
        if p["scenario"] != summary["scenario"]:
            continue
        s = pass_records.overlap(p["met_range"], summary["met_range"])
        if s >= score:
            best, score = p, s
    return best


def read_passes(passes_dir, points):
    return [pass_records.read_pass(p, points) for p in sorted(Path(passes_dir).iterdir())
            if (p / pass_records.TELEMETRY_FILE).exists()]


def read_plans(plans_dir):
    return [pass_records.read_plan(p) for p in sorted(Path(plans_dir).glob("*.yaml"))] if plans_dir else []


def read_scripted(scripted_path, plans_dir):
    return scripted_commands.read(scripted_path, read_plans(plans_dir)) if scripted_path else None


# -- output ------------------------------------------------------------------

HEADER_PREFIX = "// VERDA timeline "


def timeline_script(timeline):
    """The text of a timeline file: a summary comment, then one assignment."""
    summary = {"id": timeline["id"], "title": timeline["title"], "met_range": timeline["met_range"],
               "format": FORMAT, "format_version": FORMAT_VERSION}
    data = json.dumps(timeline, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return (HEADER_PREFIX + json.dumps(summary, sort_keys=True, ensure_ascii=True) + "\n"
            + "window.VERDA_TIMELINES = window.VERDA_TIMELINES || {};\n"
            + "window.VERDA_TIMELINES[%s] = %s;\n" % (json.dumps(timeline["id"]), data))


def read_timeline_script(path):
    """Reads a timeline file back into its JSON object (for tests and the index)."""
    text = Path(path).read_text(encoding="utf-8")
    first, _, rest = text.partition("\n")
    if not first.startswith(HEADER_PREFIX):
        raise ValueError("%s is not a VERDA timeline file" % path)
    marker = "] = "
    body = rest[rest.index(marker) + len(marker):].rstrip()
    if not body.endswith(";"):
        raise ValueError("%s does not end with ';'" % path)
    return json.loads(first[len(HEADER_PREFIX):]), json.loads(body[:-1])


def _write_output(out_dir, name, text):
    """The converter's only way to write: one named file inside the output folder."""
    if "/" in name or "\\" in name or name in ("", ".", ".."):
        raise ValueError("refusing to write %r" % name)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / name
    temporary = out_dir / (name + ".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, target)
    return target


# -- a run beside the Director's pass: two files --------------------------------

BESIDE_PREFIX = "// VERDA beside "
BESIDE_SUFFIX = ".beside.js"
BESIDE_FORMAT = "verda-beside"
# What pairing adds to a run's timeline: new entries in these maps,
_BESIDE_ADD = ("sources", "header", "series")
# these whole fields, which a run alone does not have,
_BESIDE_NEW = ("pass_commands", "scenario_commands", "pass_records")
# and these, which it replaces.
_BESIDE_REPLACE = ("title", "met_range", "lanes")


def beside_of(plain, paired, run_sha256):
    """What pairing added to a run's own timeline, for its .beside.js file."""
    beside = {"format": BESIDE_FORMAT, "format_version": FORMAT_VERSION, "id": plain["id"], "run_sha256": run_sha256,
              "pass": paired["header"]["pass"]["name"],
              "add": {key: {k: v for k, v in paired[key].items() if k not in plain[key]} for key in _BESIDE_ADD},
              "new": {key: paired[key] for key in _BESIDE_NEW},
              "append": {"integrity": paired["integrity"][len(plain["integrity"]):]}}
    beside.update({key: paired[key] for key in _BESIDE_REPLACE})
    return beside


def with_beside(plain, beside):
    """A run's own timeline with its .beside.js put to it, as the page does."""
    out = dict(plain)
    for key in _BESIDE_ADD:
        out[key] = dict(plain[key], **beside["add"][key])
    out.update(beside["new"])
    out["integrity"] = plain["integrity"] + beside["append"]["integrity"]
    out.update({key: beside[key] for key in _BESIDE_REPLACE})
    return out


def beside_script(beside):
    summary = {"id": beside["id"], "title": beside["title"], "met_range": beside["met_range"],
               "pass": beside["pass"], "run_sha256": beside["run_sha256"],
               "format": BESIDE_FORMAT, "format_version": FORMAT_VERSION}
    data = json.dumps(beside, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return (BESIDE_PREFIX + json.dumps(summary, sort_keys=True, ensure_ascii=True) + "\n"
            + "window.VERDA_BESIDE = window.VERDA_BESIDE || {};\n"
            + "window.VERDA_BESIDE[%s] = %s;\n" % (json.dumps(beside["id"]), data))


def read_beside_script(path):
    first, _, rest = Path(path).read_text(encoding="utf-8").partition("\n")
    if not first.startswith(BESIDE_PREFIX):
        raise ValueError("%s is not a VERDA beside file" % path)
    body = rest[rest.index("] = ") + len("] = "):].rstrip()
    return json.loads(first[len(BESIDE_PREFIX):]), json.loads(body[:-1])


def _remove_output(out_dir, name):
    """Removes one of the converter's own files from the output folder, if it is there."""
    if "/" in name or "\\" in name or not name.endswith(BESIDE_SUFFIX):
        raise ValueError("refusing to remove %r" % name)
    target = Path(out_dir) / name
    if target.is_file():
        target.unlink()


def write_index(out_dir):
    """index.js: each timeline file with the SHA-256 of its bytes, the Director's pass beside it if it has one,
    and each animation clip placed beside them."""
    entries = []
    for path in sorted(Path(out_dir).glob("*.js")):
        if path.name == "index.js" or path.name.endswith(BESIDE_SUFFIX):
            continue
        first = path.read_text(encoding="utf-8").partition("\n")[0]
        if first.startswith(HEADER_PREFIX):
            summary = json.loads(first[len(HEADER_PREFIX):])
            summary["file"] = path.name
            summary["sha256"] = clips.sha256_of(path)
            beside_path = path.with_name(path.name[:-len(".js")] + BESIDE_SUFFIX)
            if beside_path.is_file():
                b = json.loads(beside_path.read_text(encoding="utf-8").partition("\n")[0][len(BESIDE_PREFIX):])
                summary["beside"] = {"file": beside_path.name, "sha256": clips.sha256_of(beside_path),
                                     "pass": b["pass"], "run_sha256": b["run_sha256"]}
                summary["title"], summary["met_range"] = b["title"], b["met_range"]
            entries.append(summary)
    text = ("// VERDA's list of timeline files and animation clips, written by verda_convert.py.\n"
            "window.VERDA_INDEX = %s;\n" % json.dumps(entries, sort_keys=True, indent=1, ensure_ascii=True)
            + "window.VERDA_CLIPS = %s;\n" % json.dumps(clips.index_entries(out_dir), sort_keys=True, indent=1,
                                                         ensure_ascii=True))
    return _write_output(out_dir, "index.js", text)


def convert(run_dir, out_dir=DEFAULT_OUT, dictionary_path=None, include_truth=True, pass_dir=None, plans_dir=None,
            scripted_path=None):
    """One run's timeline file; with pass_dir, the Director's pass beside it, and with scripted_path the
    scenario's own commands on his side."""
    dictionary_path = dictionary_path or find_dictionary()
    timeline = build_timeline(run_dir, dictionary_path, include_truth)
    text = timeline_script(timeline)
    beside_name = timeline["id"] + BESIDE_SUFFIX
    if pass_dir is None:
        path = _write_output(out_dir, timeline["id"] + ".js", text)
        _remove_output(out_dir, beside_name)  # the converter's own, from pairing this run before
        write_index(out_dir)
        return path, timeline
    points = huginn_dictionary.read_points(dictionary_path)
    pass_data = pass_records.read_pass(pass_dir, points)
    paired = copy.deepcopy(timeline)
    add_pass(paired, pass_data, pass_records.plan_for(pass_data, read_plans(plans_dir)), points,
             read_scripted(scripted_path, plans_dir))
    paired["title"] = "%s beside the Director's pass %s" % (timeline["id"], pass_data["name"])
    beside = beside_of(timeline, paired, "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest())
    if with_beside(timeline, beside) != paired:
        raise RunFolderError("%s: the run's timeline and its beside file do not put together to the paired timeline"
                             % timeline["id"])
    path = _write_output(out_dir, timeline["id"] + ".js", text)
    if clips.sha256_of(path) != beside["run_sha256"]:
        raise RunFolderError("%s.js on disk is not the text it was made from" % timeline["id"])
    _write_output(out_dir, beside_name, beside_script(beside))
    write_index(out_dir)
    return path, paired


def convert_pass(pass_dir, out_dir=DEFAULT_OUT, dictionary_path=None, plans_dir=None, scripted_path=None):
    """A timeline file for a pass of the Director's that no run pairs with yet."""
    dictionary_path = dictionary_path or find_dictionary()
    points = huginn_dictionary.read_points(dictionary_path)
    pass_data = pass_records.read_pass(pass_dir, points)
    timeline = pass_timeline(pass_data, pass_records.plan_for(pass_data, read_plans(plans_dir)), points,
                             read_scripted(scripted_path, plans_dir))
    name = timeline["id"] + ".js"
    path = _write_output(out_dir, name, timeline_script(timeline))
    write_index(out_dir)
    return path, timeline


def convert_all(runs, out_dir=DEFAULT_OUT, dictionary_path=None, include_truth=True, passes_dir=None, plans_dir=None,
                scripted_path=None):
    """Every run, each beside the Director's pass of its scenario if one lines up, then each pass no run took.

    Yields (what, path, timeline) or (what, None, the exception) for each timeline file."""
    dictionary_path = dictionary_path or find_dictionary()
    passes = read_passes(passes_dir, huginn_dictionary.read_points(dictionary_path)) if passes_dir else []
    plans = read_plans(plans_dir)
    taken = set()
    for run in runs:
        match = pass_for_run(run, passes, plans) if passes else None
        try:
            path, timeline = convert(run, out_dir, dictionary_path, include_truth,
                                     Path(passes_dir) / match["name"] if match else None, plans_dir, scripted_path)
        except (RunFolderError, huginn_dictionary.DictionaryError, pass_records.PassError,
                scripted_commands.ScriptedError, OSError) as exc:
            yield Path(run).name, None, exc
            continue
        if match:
            taken.add(match["name"])
        yield Path(run).name, path, timeline
    for p in passes:
        if p["name"] in taken:
            continue
        try:
            path, timeline = convert_pass(Path(passes_dir) / p["name"], out_dir, dictionary_path, plans_dir,
                                          scripted_path)
        except (RunFolderError, pass_records.PassError, scripted_commands.ScriptedError, OSError) as exc:
            yield p["name"], None, exc
            continue
        yield p["name"], path, timeline


def find_dictionary():
    for candidate in DICTIONARY_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit("HUGINN's dictionary (tlm_cmd.yaml) was not found; pass --dictionary")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Turn ODIN run folders and the Director's passes into VERDA timeline files.")
    parser.add_argument("runs", nargs="*", help="run folders, each holding events.jsonl")
    parser.add_argument("--all", metavar="FOLDER", help="convert every run folder inside FOLDER")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="where to write timeline files")
    parser.add_argument("--dictionary", help="HUGINN's tlm_cmd.yaml")
    parser.add_argument("--no-truth", action="store_true", help="leave the simulator truth out")
    parser.add_argument("--passes", metavar="FOLDER", help="the Director's pass folders, each holding telemetry_hk.csv")
    parser.add_argument("--plans", metavar="FOLDER", help="the plans, for each pass's contact window")
    parser.add_argument("--scripted", metavar="FILE",
                        help="each scenario's own scripted commands, shown on the Director's side")
    parser.add_argument("--clips", metavar="FOLDER",
                        help="animation clips, each with its sync file beside it, to place beside the timelines")
    args = parser.parse_args(argv)
    runs = [Path(r) for r in args.runs]
    if args.all:
        for folder in sorted(p for p in Path(args.all).iterdir() if p.is_dir()):
            if record_file(folder, "events") is None:
                print("SKIPPED %s: no events.jsonl in it" % folder.name, file=sys.stderr)
            else:
                runs.append(folder)
    if not runs and not args.passes and not args.clips:
        parser.error("name at least one run folder, or --all FOLDER, --passes FOLDER or --clips FOLDER")
    status = 0
    for name, path, timeline in convert_all(runs, args.out, args.dictionary, not args.no_truth, args.passes, args.plans,
                                            args.scripted):
        if path is None:
            print("FAILED %s: %s" % (name, timeline), file=sys.stderr)
            status = 1
            continue
        broken = [c["label"] for c in timeline["integrity"] if not c.get("ok", c["chain"] == "VERIFIED")]
        beside = timeline["header"].get("pass")
        print("%s -> %s (%d records, %d turns, %d requests%s%s%s)" % (
            name, path, len(timeline["records"]), len(timeline["turns"]), len(timeline["requests"]),
            ", beside the Director's pass %s (%d commands, %d of the scenario's)" % (
                beside["name"], len(timeline["pass_commands"]), len(timeline["scenario_commands"]))
            if beside and not timeline["header"].get("pass_only") else
            (", the Director's pass alone (%d commands, %d of the scenario's)" % (
                len(timeline["pass_commands"]), len(timeline["scenario_commands"])) if beside else ""),
            ", CHECK FAILED: " + ", ".join(broken) if broken else "",
            ", %d warnings" % len(timeline["warnings"]) if timeline["warnings"] else ""))
        for warning in timeline["warnings"]:
            print("  warning: " + warning)
        if broken:
            status = 1
    if args.clips:
        status = max(status, place_and_report_clips(args.clips, args.out))
    return status


def place_and_report_clips(clips_dir, out_dir):
    """Places the clips, rewrites index.js, and says for each whether its timeline on disk is the one it pins."""
    status = 0
    for sync_path, placed, problems in clips.place_clips(clips_dir, out_dir):
        if problems:
            print("CLIP NOT PLACED %s: %s" % (sync_path.name, "; ".join(problems)), file=sys.stderr)
            status = 1
    write_index(out_dir)
    timelines = {}
    for path in sorted(Path(out_dir).glob("*.js")):
        if path.name != "index.js":
            timelines[path.stem] = clips.sha256_of(path)
    for entry in clips.index_entries(out_dir):
        have = timelines.get(entry["run_id"])
        verdict = ("matches its timeline file" if have == entry["timeline_sha256"] else
                   "NO timeline file %s.js" % entry["run_id"] if have is None else
                   "pins %s, but %s.js is %s: the page will not play it" % (
                       entry["timeline_sha256"][:19], entry["run_id"], have[:19]))
        print("clip %s -> %s (%s)" % (entry["sync_file"], entry["file"], verdict))
    return status


if __name__ == "__main__":
    sys.exit(main())
