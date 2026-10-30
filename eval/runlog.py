"""A run as S8 reads it: its event log and its truth file, and nothing of ODIN's prose (the Director's
scoring ruling of 28 October 2026, introduction; CONTRACT.md §12).

The telemetry a check reads is the frames the run's seat received. The truth file holds the model's
state after each tick, whether HUGINN generated a frame on it, and what the link did with that frame, so
the frames are rebuilt from it: one per tick on which a frame was generated and, in the ground seat, sent
down to COSMOS. Each value is the model's, as the 32-bit float HUGINN's codec packs, and is compared at
the dictionary's display decimals.
"""

import gzip
import json
import struct
from pathlib import Path

from wrapper.frames import POINTS

EVENTS = "events.jsonl"
TRUTH, TRUTH_COMPRESSED = "truth.jsonl", "truth.jsonl.gz"

# The display decimals of points the dictionary gives none (the Director's ruling on U48, 28 October 2026).
# HUGINN's dictionary gives decimals only with numeric limits (EPS_BATT_V 1, EPS_BATT_I 1, EPS_BATT_SOC 0,
# EPS_BUS_V 2, EPS_LOAD_I 1). The other float points, EPS_SA1_I, EPS_SA2_I and PLD_RATE, are compared at
# 2 places, as the Director wrote the string currents in his PASS-2 record ("0.00 A against 1.70 A").
OTHER_DECIMALS = 2


def decimals(point):
    return (POINTS[point].get("limits") or {}).get("decimals", OTHER_DECIMALS)


def read_jsonl(path):
    path = Path(path)
    data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def events(folder):
    return read_jsonl(Path(folder) / EVENTS)


def truth(folder):
    folder = Path(folder)
    return read_jsonl(folder / TRUTH if (folder / TRUTH).exists() else folder / TRUTH_COMPRESSED)


def of_type(records, *types):
    return [r for r in records if r["type"] in types]


def float32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def frame_of(met_s, state):
    """The 16 points of the frame HUGINN generated on this tick, from the model's state after it."""
    eps, cdh = state["eps"], state["cdh"]
    return {
        "EPS_BATT_V": float32(eps["battery_v"]), "EPS_BATT_I": float32(eps["battery_i"]),
        "EPS_BATT_SOC": float32(eps["soc_pct"]), "EPS_SA1_I": float32(eps["string_i"][0]),
        "EPS_SA2_I": float32(eps["string_i"][1]), "EPS_BUS_V": float32(eps["bus_v"]),
        "EPS_LOAD_I": float32(eps["load_i"]), "EPS_MODE": eps["mode"],
        "ADM_ECLIPSE": "SUNLIT" if eps["illuminated"] else "ECLIPSE",
        "PLD_STATE": "ON" if eps["payload_on"] else "OFF", "PLD_RATE": float32(eps["pld_rate_hz"]),
        "CDH_MET": met_s, "CDH_FRAME_CNT": cdh["frame_count"], "CDH_CMD_ACC_CNT": cdh["acc_count"],
        "CDH_CMD_REJ_CNT": cdh["rej_count"], "CDH_REJ_REASON": cdh["rej_reason"],
    }


def received_frames(truth_records):
    """{CDH_MET: frame} for every frame the seat received: generated, and sent down the link in the ground
    seat (downlink SENT) or read beside the simulator in the onboard seat (downlink null), less those the
    truth file says the ground seat never received, GROUND_MISSED (the Director's word of 30 October 2026)."""
    frames = {}
    for record in truth_records:
        if record["type"] != "TRUE_STATE":
            continue
        state = record["body"]
        if state["frame_generated"] and state["downlink"] in ("SENT", None):
            frames[record["met_s"]] = frame_of(record["met_s"], state)
    for record in truth_records:
        if record["type"] == "GROUND_MISSED":
            frames.pop(record["body"]["frame_met_s"], None)
    return frames


def same_value(point, claimed, actual):
    """A claimed value against the frame's, at the dictionary's display decimals; states and counts exactly."""
    if POINTS[point]["type"] == "float":
        if isinstance(claimed, bool) or not isinstance(claimed, (int, float)):
            return False
        places = decimals(point)
        return round(float(claimed), places) == round(float(actual), places)
    return claimed == actual


def fault_onsets(truth_records):
    return [r["body"] for r in truth_records if r["type"] == "FAULT_ONSET"]
