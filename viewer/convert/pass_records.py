"""The Director's flown passes, read for VERDA.

A pass folder holds what the Director's ground station recorded in one pass he
flew in HUGINN: telemetry_hk.csv, every housekeeping frame it received, and
commands.csv, every command he sent (absent when he sent none). Both are OpenC3
COSMOS exports.

His pass also carried the commands the scenario sent by itself, at set METs
(convert/scripted_commands.py). What his telemetry showed after one of those is
read here the same way, from his command counters.

Each frame carries the spacecraft's own mission elapsed time (CDH_MET), so it
sits on the same MET axis as a run ODIN flew. A command carries only the UTC
time it went out. Its MET is read from the frames received just before and just
after it, by linear interpolation between them: the spacecraft's clock and UTC
drift apart by up to 1 % in these passes, so one fixed offset would misplace a
command by several seconds.

The column order differs from pass to pass, and a commands.csv that holds two
kinds of command packet repeats column names (one block of columns per packet),
so every row is read by position against its own header, never through a
name-to-value map that would keep only one of two same-named columns.

This module only reads. It never writes.
"""

import csv
import datetime
import hashlib
import re
from pathlib import Path

import huginn_dictionary

TELEMETRY_FILE = "telemetry_hk.csv"
COMMANDS_FILE = "commands.csv"
# A command row's columns that describe the packet, not the command's arguments.
COMMAND_META = {"TIME", "TARGET", "PACKET", "USERNAME", "OPCODE", "PACKET_TIMESECONDS", "PACKET_TIMEFORMATTED",
                "RECEIVED_TIMESECONDS", "RECEIVED_TIMEFORMATTED", "RECEIVED_COUNT"}
# How long after a command its counters are watched for the spacecraft's answer.
OUTCOME_WINDOW_S = 10
_UTC = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z$")
_PASS_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-(P\d+[A-Za-z]?)$")


class PassError(Exception):
    pass


def utc_seconds(text):
    """'2026-10-11T17:07:43.660450048Z' as seconds since 1970, UTC."""
    m = _UTC.match(text or "")
    if not m:
        raise PassError("not a UTC time: %r" % (text,))
    base = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    return base.timestamp() + (float("0." + m.group(2)) if m.group(2) else 0.0)


def scenario_base(text):
    """The scenario's number as a pass and a run both name it: 'P3' from 'P3', 'P3_stuck_load' or 'P2a'."""
    m = re.match(r"(P\d+)", text or "", re.I)
    return m.group(1).upper() if m else None


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise PassError("%s is empty" % path.name)
    return rows[0], rows[1:]


def _fields(header, row):
    """A row as {column: value}, empty cells left out; a repeated column name gets '#2', '#3'."""
    out, seen = {}, {}
    for name, value in zip(header, row):
        seen[name] = seen.get(name, 0) + 1
        if value != "":
            out[name if seen[name] == 1 else "%s#%d" % (name, seen[name])] = value
    return out


def _typed(info, text):
    if info is None:
        return text
    kind = info.get("type")
    try:
        if kind == "float":
            return float(text)
        if kind and re.fullmatch(r"u?int\d*", kind):
            return int(text)
    except ValueError:
        return text
    return text


def _argument(text):
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d*", text):
        return float(text)
    return text


def _sha256(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_pass(folder, points):
    """Reads one pass folder. `points` is the dictionary's telemetry points (huginn_dictionary.read_points)."""
    folder = Path(folder)
    m = _PASS_NAME.match(folder.name)
    if not m:
        raise PassError("%s is not named <date>-<pass>, as 2026-10-11-P3" % folder.name)
    telemetry = folder / TELEMETRY_FILE
    if not telemetry.exists():
        raise PassError("%s has no %s" % (folder.name, TELEMETRY_FILE))
    problems = []
    files = {TELEMETRY_FILE: {"sha256": _sha256(telemetry)}}

    header, rows = _read_csv(telemetry)
    for needed in ("TIME", "CDH_MET"):
        if needed not in header:
            raise PassError("%s has no %s column" % (TELEMETRY_FILE, needed))
    i_time, i_met = header.index("TIME"), header.index("CDH_MET")
    frames = []
    for n, row in enumerate(rows, start=2):
        if len(row) < len(header):
            problems.append("%s line %d has %d of %d columns" % (TELEMETRY_FILE, n, len(row), len(header)))
            continue
        try:
            frame = {"line": n, "utc": row[i_time], "utc_s": utc_seconds(row[i_time]), "met_s": int(row[i_met])}
        except (PassError, ValueError) as exc:
            problems.append("%s line %d: %s" % (TELEMETRY_FILE, n, exc))
            continue
        frame["values"] = {name: _typed(points.get(name), row[i]) for i, name in enumerate(header) if name in points}
        frame["fields"] = _fields(header, row)
        if frames and frame["met_s"] <= frames[-1]["met_s"]:
            problems.append("%s line %d: MET %d does not follow MET %d" % (TELEMETRY_FILE, n, frame["met_s"], frames[-1]["met_s"]))
        if frames and frame["utc_s"] <= frames[-1]["utc_s"]:
            problems.append("%s line %d: its time does not follow the line before" % (TELEMETRY_FILE, n))
        frames.append(frame)
    files[TELEMETRY_FILE]["rows"] = len(rows)
    if not frames:
        raise PassError("%s holds no frames" % TELEMETRY_FILE)

    commands = []
    command_file = folder / COMMANDS_FILE
    if command_file.exists():
        files[COMMANDS_FILE] = {"sha256": _sha256(command_file)}
        c_header, c_rows = _read_csv(command_file)
        files[COMMANDS_FILE]["rows"] = len(c_rows)
        for n, row in enumerate(c_rows, start=2):
            if len(row) < 3:
                problems.append("%s line %d is too short to name a command" % (COMMANDS_FILE, n))
                continue
            try:
                t = utc_seconds(row[0])
            except PassError as exc:
                problems.append("%s line %d: %s" % (COMMANDS_FILE, n, exc))
                continue
            arguments = {}
            for i, name in enumerate(c_header[3:], start=3):
                if i < len(row) and row[i] != "" and name not in COMMAND_META:
                    arguments[name.lower()] = _argument(row[i])
            command = {"line": n, "utc": row[0], "utc_s": t, "target": row[1], "command": row[2],
                       "parameters": arguments, "fields": _fields(c_header, row)}
            command.update(place(frames, t))
            command["outcome"] = outcome(frames, command)
            commands.append(command)
    for k in range(1, len(commands)):
        if commands[k]["utc_s"] < commands[k - 1]["utc_s"]:
            problems.append("%s line %d: sent before the line above it" % (COMMANDS_FILE, commands[k]["line"]))

    return {"name": folder.name, "date": m.group(1), "tag": m.group(2), "scenario": scenario_base(m.group(2)),
            "files": files, "frames": frames, "commands": commands, "problems": problems,
            "met_range": [frames[0]["met_s"], frames[-1]["met_s"]]}


def place(frames, t):
    """A command's MET, from the frames received just before and just after its UTC time."""
    before = None
    for frame in frames:
        if frame["utc_s"] <= t:
            before = frame
        else:
            break
    after = next((f for f in frames if f["utc_s"] > t), None)
    if before is not None and after is not None:
        rate = (after["met_s"] - before["met_s"]) / (after["utc_s"] - before["utc_s"])
        met = before["met_s"] + (t - before["utc_s"]) * rate
        basis = "between his frames at MET %d (line %d) and MET %d (line %d)" % (
            before["met_s"], before["line"], after["met_s"], after["line"])
    else:
        # Before the first frame or after the last: one second of MET for each second of UTC.
        near = after if before is None else before
        met = near["met_s"] + (t - near["utc_s"])
        basis = "outside his frames: from the nearest, MET %d (line %d), at one second per second" % (
            near["met_s"], near["line"])
    return {"met_s": round(met, 3), "met_basis": basis,
            "frame_lines": [f["line"] for f in (before, after) if f is not None]}


def outcome(frames, command):
    """What his telemetry showed after a command: his command counters, from the frame before it."""
    t = command["utc_s"]
    before = None
    for frame in frames:
        if frame["utc_s"] <= t:
            before = frame
    return _counters(before, [f for f in frames if f["utc_s"] > t], command["met_s"])


def outcome_at_met(frames, met_s):
    """What his telemetry showed after a command the scenario sent by itself at a set MET.

    Its frame before is the last one from before that MET; the frame stamped with
    that MET already shows what the command did."""
    if not frames or not frames[0]["met_s"] < met_s <= frames[-1]["met_s"]:
        return {"kind": "outside", "text": "outside his frames (MET %d to %d): his telemetry does not cover it"
                % (frames[0]["met_s"], frames[-1]["met_s"]) if frames else "he received no frames"}
    before = None
    for frame in frames:
        if frame["met_s"] < met_s:
            before = frame
    return _counters(before, [f for f in frames if f["met_s"] >= met_s], met_s)


def _counters(before, later, met_s):
    if before is None:
        return {"kind": "unknown", "text": "no frame before it to compare with"}
    return dict(_change(before, later, met_s), before_line=before["line"], before_met_s=before["met_s"])


def _change(before, later, met_s):
    acc0, rej0 = before["values"].get("CDH_CMD_ACC_CNT"), before["values"].get("CDH_CMD_REJ_CNT")
    for frame in later:
        if frame["met_s"] > met_s + OUTCOME_WINDOW_S:
            break
        acc, rej = frame["values"].get("CDH_CMD_ACC_CNT"), frame["values"].get("CDH_CMD_REJ_CNT")
        if acc is not None and acc0 is not None and acc > acc0:
            return {"kind": "accepted", "met_s": frame["met_s"], "line": frame["line"],
                    "text": "accepted: CDH_CMD_ACC_CNT %s -> %s in his frame at MET %d" % (acc0, acc, frame["met_s"])}
        if rej is not None and rej0 is not None and rej > rej0:
            reason = frame["values"].get("CDH_REJ_REASON")
            return {"kind": "rejected", "met_s": frame["met_s"], "line": frame["line"], "reason": reason,
                    "text": "rejected: CDH_CMD_REJ_CNT %s -> %s, reason %s, in his frame at MET %d" % (
                        rej0, rej, reason, frame["met_s"])}
    return {"kind": "unchanged",
            "text": "no change in his command counters in the %d s after it (CDH_CMD_ACC_CNT %s, CDH_CMD_REJ_CNT %s)"
                    % (OUTCOME_WINDOW_S, acc0, rej0)}


def watched_until(met_s, result):
    """The end of the span his counters were read over for a command: its change, or the whole window."""
    return result["met_s"] if result.get("met_s") is not None else met_s + OUTCOME_WINDOW_S


def sharing(met_s, result, others):
    """The other commands sent inside the span a command's counters were read over.

    A counter change in that span may be any of theirs, so it cannot be credited to
    the one command alone. `others` is [(met_s, who, command)]."""
    end = watched_until(met_s, result)
    return [o for o in others if met_s <= o[0] <= end]


# -- the phase-2 plans, for each pass's contact window ------------------------

def read_plan(path):
    """The few fields of a plan file VERDA uses: its id, scenario and contact window."""
    text = Path(path).read_text(encoding="utf-8")
    found = {}
    for key in ("plan_id", "scenario_id", "aos_met_s", "los_met_s"):
        m = re.search(r"^\s*%s:\s*(\S+)\s*$" % key, text, re.M)
        if not m:
            raise PassError("%s has no %s" % (Path(path).name, key))
        found[key] = m.group(1)
    return {"plan_id": found["plan_id"], "scenario_id": found["scenario_id"],
            "aos_met_s": int(found["aos_met_s"]), "los_met_s": int(found["los_met_s"]),
            "file": Path(path).name, "sha256": _sha256(path)}


def overlap(a, b):
    """How much of span a lies inside span b, from 0 to 1."""
    inside = min(a[1], b[1]) - max(a[0], b[0])
    return max(0.0, inside) / max(1e-9, a[1] - a[0])


def plan_for(pass_data, plans):
    """The plan whose contact window holds most of the pass's frames, if it holds at least half."""
    best, score = None, 0.5
    for plan in plans:
        if scenario_base(plan["scenario_id"]) != pass_data["scenario"]:
            continue
        s = overlap(pass_data["met_range"], [plan["aos_met_s"], plan["los_met_s"]])
        if s >= score:
            best, score = plan, s
    return best


def frame_age(pass_data, limits):
    """The age of the newest frame his ground station had received, at each second of his pass."""
    mets = [f["met_s"] for f in pass_data["frames"]]
    samples, index, newest = [], 0, None
    for t in range(mets[0], mets[-1] + 1):
        while index < len(mets) and mets[index] <= t:
            newest = mets[index]
            index += 1
        age = t - newest
        state = "RED" if age >= limits["red_s"] else "YELLOW" if age >= limits["yellow_s"] else "GREEN"
        samples.append([t, age, state, "derived"])
    return samples


def limit_state(points, point, value):
    info = points.get(point)
    return huginn_dictionary.limit_state(info, value) if info else None
