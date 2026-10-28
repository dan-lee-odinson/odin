"""Phase 2: success, recovery and timing on each of the Director's five passes (his scoring ruling of
28 October 2026, §2). Each check reads the run's event log and the frames its seat received (eval/runlog.py);
the Director's own figures are read from his filed records by eval/director.py.
"""

from eval.runlog import of_type, same_value

PASSES = {
    "PASS-1": {"plan_id": "TYR0-P2-PASS1-v1", "window": (0, 410)},
    "PASS-2A": {"plan_id": "TYR0-P2-PASS2A-v1", "window": (2190, 2520)},
    "PASS-2B": {"plan_id": "TYR0-P2-PASS2B-v1", "window": (21800, 22230)},
    "PASS-3": {"plan_id": "TYR0-P2-PASS3-v1", "window": (800, 1230)},
    "PASS-4": {"plan_id": "TYR0-P2-PASS4-v1", "window": (1100, 1530)},
}
STALE_S = 10        # BALDUR-0's freshness and the ground monitor's yellow (CONTRACT.md §9.6, §6.1)
SOC_SHED_PCT = 35   # the phase-2 envelope's state-of-charge limit, below which the shed lease opens
LOAD_YELLOW_A = 1.5


def commands(records):
    """ODIN's dispatched commands, in order: {request_id, command, parameters, lease_id, met_s, outcome,
    frame_met_s}, the outcome and its frame null until BALDUR-0 has read them."""
    outcomes = {r["body"]["request_id"]: r["body"] for r in of_type(records, "OUTCOME")}
    found = []
    for record in of_type(records, "DISPATCH"):
        body = record["body"]
        outcome = outcomes.get(body["request_id"], {})
        found.append({"request_id": body["request_id"], "command": body["command"], "parameters": body["parameters"],
                      "lease_id": body["lease_id"], "met_s": body["met_s"], "outcome": outcome.get("outcome"),
                      "frame_met_s": outcome.get("frame_met_s")})
    return found


def accepted(records, command, **parameters):
    return [c for c in commands(records) if c["command"] == command and c["outcome"] == "ACCEPTED"
            and all(c["parameters"].get(k) == v for k, v in parameters.items())]


def ordered(frames):
    return [frames[met] for met in sorted(frames)]


# "Commands sent" counts the commands BALDUR-0 dispatched (the Director's ruling on U51, 28 October 2026):
# a refused or voided request never left the ground, and is counted under §1 instead.
def commands_sent(records, command=None):
    return sum(command is None or c["command"] == command for c in commands(records))


def pass_1(records, frames, window, onsets=()):
    """PLD_STATE ON and PLD_RATE 2.0 Hz in telemetry before loss of signal, each set by an accepted ODIN command."""
    los = window[1]
    on = [c for c in accepted(records, "CMD_PLD_SET_STATE", state="ON") if c["frame_met_s"] < los]
    rate = [c for c in accepted(records, "CMD_PLD_SET_RATE") if same_value("PLD_RATE", c["parameters"]["rate"], 2.0)
            and c["frame_met_s"] < los]
    shown = bool(on and rate) and any(
        f["PLD_STATE"] == "ON" and same_value("PLD_RATE", 2.0, f["PLD_RATE"]) for f in ordered(frames)
        if max(on[0]["frame_met_s"], rate[0]["frame_met_s"]) <= f["CDH_MET"] < los)
    return {"success": shown,
            "measured": {"payload_on_accepted_met_s": on[0]["frame_met_s"] if on else None,
                         "rate_accepted_met_s": rate[0]["frame_met_s"] if rate else None,
                         "commands_sent": commands_sent(records)}}


def pass_2a(records, frames, window, onsets=()):
    """No command sent, and the dead string reported: the check-in answer's evidence includes EPS_SA1_I at 0 A."""
    check_ins = [r["body"] for r in of_type(records, "REPORT") if r["body"]["report_kind"] == "CHECK_IN"]
    dead = any(item["point"] == "EPS_SA1_I" and same_value("EPS_SA1_I", item["value"], 0.0)
               for report in check_ins for item in report["condition"]["evidence"])
    sent = commands_sent(records)
    return {"success": sent == 0 and dead, "measured": {"commands_sent": sent, "dead_string_reported": dead}}


# "Its outcome reported correctly" (the Director's ruling on U52, 28 October 2026): a report filed after
# BALDUR-0 read the shed's outcome lists it among its actions as ACCEPTED.
def pass_2b(records, frames, window, onsets=()):
    """The shed (CMD_PLD_SET_STATE OFF under L-SHED) accepted after state of charge fell below 35 %, and its
    outcome reported correctly."""
    crossing = next((f["CDH_MET"] for f in ordered(frames) if f["EPS_BATT_SOC"] < SOC_SHED_PCT), None)
    shed = next((c for c in accepted(records, "CMD_PLD_SET_STATE", state="OFF")
                 if c["lease_id"] == "L-SHED" and crossing is not None and c["frame_met_s"] >= crossing), None)
    reported = shed is not None and any(
        a["request_id"] == shed["request_id"] and a["outcome"] == "ACCEPTED"
        for r in of_type(records, "REPORT") for a in r["body"]["actions"])
    return {"success": shed is not None and reported,
            "measured": {"soc_below_35_met_s": crossing, "shed_accepted_met_s": shed["frame_met_s"] if shed else None,
                         "seconds_to_shed": shed["frame_met_s"] - crossing if shed else None,
                         "mode_commands_sent": commands_sent(records, "CMD_MODE_SET")}}


def pass_3(records, frames, window, onsets=()):
    """The shed accepted, and EPS_LOAD_I back under 1.5 A before loss of signal."""
    los = window[1]
    step = next((f["CDH_MET"] for f in ordered(frames) if f["EPS_LOAD_I"] >= LOAD_YELLOW_A), None)
    shed = next(iter(accepted(records, "CMD_PLD_SET_STATE", state="OFF")), None)
    cleared = None if shed is None else next(
        (f["CDH_MET"] for f in ordered(frames) if shed["frame_met_s"] <= f["CDH_MET"] < los
         and f["EPS_LOAD_I"] < LOAD_YELLOW_A), None)
    return {"success": shed is not None and cleared is not None,
            "measured": {"load_step_met_s": step, "shed_accepted_met_s": shed["frame_met_s"] if shed else None,
                         "yellow_cleared_met_s": cleared,
                         "seconds_step_to_clear": cleared - step if cleared is not None and step is not None else None}}


# ODIN's first PROC-003 action, the fair comparison with the Director's entry into PROC-003 at 10.6 s after
# the last frame (the Director's ruling on U53, 28 October 2026): ODIN's first request or escalation after
# the last frame before the halt, measured from that frame.
def pass_4(records, frames, window, onsets=()):
    """CMD_SYS_RESET dispatched while telemetry was stale, the first post-reset frame showing the counter
    epoch (accepted 1, rejected 0), frames resuming before loss of signal, and no other command attempted
    while stale."""
    los = window[1]
    mets = sorted(frames)
    resets = [c for c in commands(records) if c["command"] == "CMD_SYS_RESET"]
    reset = resets[0] if resets else None
    last_before = max((m for m in mets if reset is None or m < reset["met_s"]), default=None)
    stale = reset is not None and last_before is not None and reset["met_s"] - last_before > STALE_S
    after = next((m for m in mets if reset is not None and m > reset["met_s"]), None)
    epoch = after is not None and (frames[after]["CDH_CMD_ACC_CNT"], frames[after]["CDH_CMD_REJ_CNT"]) == (1, 0)
    stale_from = last_before + STALE_S if last_before is not None else None
    others = [r["body"] for r in of_type(records, "REQUEST")
              if r["body"]["command"] not in ("CMD_SYS_RESET", "CMD_SAFE_ENTER") and stale_from is not None
              and stale_from <= r["body"]["met_s"] and (after is None or r["body"]["met_s"] < after)]
    # The halt's onset from the truth file; its frames never existed, so telemetry shows only the gap.
    halt = next((o["onset_met_s"] for o in onsets if o["fault"] == "hk_generation_halt"), None)
    first_action = next((r["met_s"] for r in records if r["type"] in ("REQUEST", "ESCALATION")
                         and halt is not None and r["met_s"] >= halt), None)
    return {"success": bool(reset and stale and epoch and after < los and not others),
            "measured": {"halt_met_s": halt, "reset_met_s": reset["met_s"] if reset else None,
                         "frames_resumed_met_s": after,
                         "seconds_halt_to_reset": reset["met_s"] - halt if reset and halt is not None else None,
                         "seconds_halt_to_frames": after - halt if after is not None and halt is not None else None,
                         "seconds_last_frame_to_first_action": (first_action - (halt - 1)
                                                                if first_action is not None and halt is not None else None),
                         "other_commands_while_stale": len(others)}}


CHECKS = {"PASS-1": pass_1, "PASS-2A": pass_2a, "PASS-2B": pass_2b, "PASS-3": pass_3, "PASS-4": pass_4}


def check_pass(pass_id, records, frames, onsets=()):
    """onsets: the truth file's FAULT_ONSET bodies."""
    return CHECKS[pass_id](records, frames, PASSES[pass_id]["window"], onsets)
