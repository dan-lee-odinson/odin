"""The Director's own figures for each phase-2 pass, read by script from his filed records in
inputs-pre-existing/comparison-only/ (his scoring ruling of 28 October 2026, §2): the telemetry and command
extracts his COSMOS wrote, and, for the staleness annunciations COSMOS keeps only in its log, his report's
event timeline.
"""

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

RECORDS = Path(__file__).resolve().parent.parent / "inputs-pre-existing" / "comparison-only" / "pass-records"
FLIGHTS = {"PASS-1": "2026-09-13-P1", "PASS-2A": "2026-09-20-P2a", "PASS-2B": "2026-09-20-P2b",
           "PASS-3": "2026-10-11-P3", "PASS-4": "2026-10-11-P4"}
NUMBERS = ("CDH_MET", "CDH_FRAME_CNT", "CDH_CMD_ACC_CNT", "CDH_CMD_REJ_CNT")
FLOATS = ("EPS_BATT_V", "EPS_BATT_I", "EPS_BATT_SOC", "EPS_SA1_I", "EPS_SA2_I", "EPS_BUS_V", "EPS_LOAD_I", "PLD_RATE")


def utc_seconds(text):
    """Seconds since the epoch from COSMOS's ISO time, nanoseconds and all."""
    whole, _, fraction = text.rstrip("Z").partition(".")
    base = datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    return base + (float("0." + fraction) if fraction else 0.0)


def telemetry(flight):
    rows = []
    with open(RECORDS / flight / "telemetry_hk.csv", newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            frame = {k: v for k, v in row.items() if k in NUMBERS + FLOATS + ("EPS_MODE", "PLD_STATE", "TIME")}
            frame.update({k: int(row[k]) for k in NUMBERS})
            frame.update({k: float(row[k]) for k in FLOATS})
            frame["seconds"] = utc_seconds(row["TIME"])
            rows.append(frame)
    return sorted(rows, key=lambda f: f["CDH_MET"])


def command_rows(flight):
    path = RECORDS / flight / "commands.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as file:
        return [{"packet": row["PACKET"], "seconds": utc_seconds(row["TIME"])} for row in csv.DictReader(file)]


def acceptances(frames):
    """The frames on which CDH_CMD_ACC_CNT rose: where an accepted command shows."""
    return [f for before, f in zip(frames, frames[1:]) if f["CDH_CMD_ACC_CNT"] > before["CDH_CMD_ACC_CNT"]]


def met_at(frames, seconds):
    """The MET a UTC time maps to, from the newest frame received at or before it."""
    frame = max((f for f in frames if f["seconds"] <= seconds), key=lambda f: f["seconds"])
    return frame["CDH_MET"] + (seconds - frame["seconds"])


def pass_1():
    frames = telemetry(FLIGHTS["PASS-1"])
    accepted = acceptances(frames)
    on = next(f["CDH_MET"] for f in accepted if f["PLD_STATE"] == "ON")
    rate = next(f["CDH_MET"] for f in accepted if f["PLD_RATE"] == 2.0)
    return {"payload_on_accepted_met_s": on, "rate_accepted_met_s": rate,
            "commands_sent": len(command_rows(FLIGHTS["PASS-1"])),
            "rejections": max(f["CDH_CMD_REJ_CNT"] for f in frames)}


def pass_2a():
    frames = telemetry(FLIGHTS["PASS-2A"])
    return {"commands_sent": len(command_rows(FLIGHTS["PASS-2A"])), "frames": len(frames),
            "frames_string_1_dead": sum(f["EPS_SA1_I"] == 0.0 and f["EPS_SA2_I"] == 1.7 for f in frames)}


def pass_2b():
    frames = telemetry(FLIGHTS["PASS-2B"])
    crossing = next(f["CDH_MET"] for f in frames if f["EPS_BATT_SOC"] < 35)
    shed = next(f["CDH_MET"] for f in acceptances(frames) if f["PLD_STATE"] == "OFF")
    return {"soc_below_35_met_s": crossing, "shed_accepted_met_s": shed, "seconds_to_shed": shed - crossing,
            "mode_commands_sent": sum(c["packet"] == "CMD_MODE_SET" for c in command_rows(FLIGHTS["PASS-2B"]))}


def pass_3():
    frames = telemetry(FLIGHTS["PASS-3"])
    step = next(f["CDH_MET"] for f in frames if f["EPS_LOAD_I"] >= 1.5)
    shed = next(f["CDH_MET"] for f in acceptances(frames) if f["PLD_STATE"] == "OFF")
    cleared = next(f["CDH_MET"] for f in frames if f["CDH_MET"] >= shed and f["EPS_LOAD_I"] < 1.5)
    return {"load_step_met_s": step, "shed_accepted_met_s": shed, "yellow_cleared_met_s": cleared,
            "seconds_step_to_clear": cleared - step}


STALENESS = re.compile(r"staleness (YELLOW|RED) at (\d\d:\d\d:\d\d(?:\.\d+)?)Z")


def pass_4():
    flight = FLIGHTS["PASS-4"]
    frames = telemetry(flight)
    gap = next(i for i, (a, b) in enumerate(zip(frames, frames[1:])) if b["CDH_MET"] - a["CDH_MET"] > 1)
    last, resumed = frames[gap], frames[gap + 1]
    report = yaml.safe_load((RECORDS / flight / "report.yaml").read_text(encoding="utf-8"))
    day = last["TIME"][:10]
    annunciated = {}
    for item in report["event_timeline"]:
        match = STALENESS.search(item["event"])
        if match and match.group(1) not in annunciated:
            annunciated[match.group(1)] = round(utc_seconds(f"{day}T{match.group(2)}Z") - last["seconds"], 1)
    [reset] = [c for c in command_rows(flight) if c["packet"] == "CMD_SYS_RESET"]
    return {"last_frame_met_s": last["CDH_MET"], "halt_met_s": last["CDH_MET"] + 1,
            "seconds_last_frame_to_yellow": annunciated["YELLOW"], "seconds_last_frame_to_red": annunciated["RED"],
            "frames_resumed_met_s": resumed["CDH_MET"], "reset_met_s": round(met_at(frames, reset["seconds"]), 1)}


FLIGHT_FIGURES = {"PASS-1": pass_1, "PASS-2A": pass_2a, "PASS-2B": pass_2b, "PASS-3": pass_3, "PASS-4": pass_4}


def flight(pass_id):
    return FLIGHT_FIGURES[pass_id]()
