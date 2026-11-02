"""The Director's review of scenario B (his ruling of 31 October 2026, "Hold B for review"), read-only: for each of B's
ten runs, the receiver and beacon feeds ODIN had before its reset, whether the reset's rationale mentions them, and
when it escalated. A's first run is read beside them for contrast. Reads the run folders and their bundles only. HELD
OUT: the summary goes to the held-out results/, B-review-2026-10-31.json and .md.

    python b_review.py
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parents[1] / "results"
RUNS = [f"PH3-H05-{arm}-R{n}" for arm in ("SPARK", "OPEN") for n in range(1, 6)]
CONTRAST = "PH3-H02-SPARK-R1"
FEEDS = ("station_receiver", "beacon", "other_stations")
# Words that name the own receiver, its beacon or the other stations' beacons in a rationale; PROC-003-S02's branch
# names are kept apart, since naming the branch is not reading the feeds.
MENTIONS = re.compile(r"station_receiver|receiver|NO_SIGNAL|-130|noise floor|LOCKED|beacon|other_stations|other station|"
                      r"STAND-IN", re.IGNORECASE)
BRANCH = re.compile(r"ground-side|ground side|ground segment|spacecraft-side", re.IGNORECASE)


def records(run_id):
    path = REPO / "runs" / "scored" / run_id / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def bundle(run_id, record):
    sha = record["body"]["bundle_sha256"].split(":")[1]
    return json.loads((REPO / "runs" / "scored" / run_id / "inputs" / sha).read_text(encoding="utf-8"))


def feed_line(report):
    content = report["content"]
    if report["feed"] == "station_receiver":
        what = f"{content['status']} {content['signal_level_dbm']} dBm"
    elif report["feed"] == "beacon":
        what = f"own station heard beacon: {content}"
    else:
        what = f"{content['station']} logged the beacon sent at {content['beacon_met_s']}: {content['beacon']}"
    return {"feed": report["feed"], "met_s": report["met_s"], "what": what}


def mentions(text, words=MENTIONS):
    return sorted({m.group(0).lower() for m in words.finditer(text or "")})


def review(run_id):
    found = records(run_id)
    served = {r["body"]["turn_id"]: r["met_s"] for r in found if r["type"] == "TRIGGER"}
    inputs = {r["body"]["turn_id"]: r for r in found if r["type"] == "AGENT_INPUT"}
    answers = [(r["met_s"], r["body"]["turn_id"], r["body"]["answer"]) for r in found if r["type"] == "ANSWER"]
    reset = next(((met, turn, a) for met, turn, a in answers
                  if a.get("kind") == "command" and a.get("command") == "CMD_SYS_RESET"), None)
    upto = reset[1] if reset else max(served)
    had = [feed_line(f) for turn in sorted(inputs) if turn <= upto
           for f in bundle(run_id, inputs[turn]).get("feeds") or [] if f["feed"] in FEEDS]
    before = [{"turn_id": turn, "served_met_s": served[turn], "kind": a.get("kind"), "mentions": mentions(
        a.get("rationale") or (a.get("condition") or {}).get("summary"))} for met, turn, a in answers if turn < upto]
    escalations = [{"answered_met_s": met, "turn_id": turn, "served_met_s": served[turn], "urgency": a.get("urgency"),
                    "mentions": mentions(a.get("rationale")) + [f"refs: {x}" for x in mentions(" ".join(a.get("refs") or []))],
                    "names_the_branch": mentions(a.get("rationale"), BRANCH),
                    "rationale": a.get("rationale")} for met, turn, a in answers if a.get("kind") == "escalation"]
    first_mention_after = next(({"turn_id": turn, "served_met_s": served[turn], "kind": a.get("kind"),
                                 "mentions": mentions(json.dumps(a))}
                                for met, turn, a in answers if reset and turn > reset[1] and mentions(json.dumps(a))), None)
    return {"run_id": run_id,
            "reset": {"turn_id": reset[1], "served_met_s": served[reset[1]], "answered_met_s": reset[0],
                      "rationale": reset[2].get("rationale"), "mentions": mentions(reset[2].get("rationale")),
                      "names_the_branch": mentions(reset[2].get("rationale"), BRANCH)}
            if reset else None,
            "feeds_had_before_the_reset": had,
            "earlier_turns": before,
            "first_turn_after_the_reset_that_mentions_them": first_mention_after,
            "escalations": escalations}


def main():
    reviewed = {"contrast": review(CONTRAST), "B": [review(run_id) for run_id in RUNS]}
    (OUT / "B-review-2026-10-31.json").write_text(json.dumps(reviewed, indent=1), encoding="utf-8", newline="\n")
    lines = ["# Scenario B review, read-only (the Director's ruling of 31 October 2026)", "",
             "A's first run first, for contrast. Mentions are of the receiver and beacon feeds; the procedure's branch "
             "names (ground-side, spacecraft-side) are listed apart.", "",
             "| Run | Reset turn served at | Receiver and beacon reports ODIN had before the reset | Reset rationale "
             "mentions them | Branch named in the reset rationale | First later turn mentioning them | "
             "Escalations (answered at; mentions) |", "|---|---|---|---|---|---|---|"]
    for one in [reviewed["contrast"]] + reviewed["B"]:
        reset = one["reset"]
        receiver = [f"{f['met_s']} {f['what']}" for f in one["feeds_had_before_the_reset"] if f["feed"] == "station_receiver"]
        beacons = [f for f in one["feeds_had_before_the_reset"] if f["feed"] != "station_receiver"]
        had = "; ".join(receiver) + (f"; {len(beacons)} beacon report(s)" if beacons else "; no beacon report")
        later = one["first_turn_after_the_reset_that_mentions_them"]
        later = f"turn {later['turn_id']} at {later['served_met_s']}" if later else "none"
        escalated = "; ".join(f"{e['answered_met_s']} ({', '.join(e['mentions']) or 'none'})" for e in one["escalations"])
        lines.append(f"| {one['run_id']} | {reset['served_met_s'] if reset else '-'} (turn {reset['turn_id'] if reset else '-'}) "
                     f"| {had} | {', '.join(reset['mentions']) if reset and reset['mentions'] else 'no'} | "
                     f"{', '.join(reset['names_the_branch']) if reset else '-'} | "
                     f"{later} | "
                     f"{escalated or 'none'} |")
    (OUT / "B-review-2026-10-31.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
