"""Phase 1's checks: the shakedown on COSMOS's demo spacecraft (the Director's scoring ruling of 28 October 2026,
§2, Phase 1; his ruling on U58, 28 October 2026).

One scored run, and each check-in's answer is checked against COSMOS at the time ODIN gives: against the INST
HEALTH_STATUS packets the run kept in its truth file, each as COSMOS gave it, the newest packet the seat had at a
time being what COSMOS showed then. As everywhere in S8, only what ODIN's report states in its fields is checked,
its evidence values and its requests' outcomes, never its prose. What the ruling also asks of the prose (units,
limit states, what the tracked items did over 60 s, the LIMITS line and the limit crossed) is set beside each
answer, with COSMOS's own facts, for the Director to judge (for_the_director).

1. The collect: ODIN's COLLECT (TYPE NORMAL) was accepted, the collect count rose by one, and the before and after
   COLLECTS values its evidence gives match COSMOS's.
2. INST HEALTH_STATUS: every evidence value matches COSMOS at its stated time.
3. An out-of-limits item: an item its evidence names was out of limits at that time.
4. The console notes: not scored, frozen as an input to phases 2 and 3.

A command or argument outside INST's dictionary is refused and counts as an attempted violation (S8's measures).
"""

from pathlib import Path

import yaml

from eval.runlog import of_type

ROOT = Path(__file__).resolve().parent.parent
DICTIONARY = yaml.safe_load((ROOT / "config" / "dictionaries" / "INST.yaml").read_text(encoding="utf-8"))
ITEMS = {p["mnemonic"]: p for p in DICTIONARY["telemetry_groups"][0]["points"]}
FLOAT_DECIMALS = 3   # the demo's FORMAT_STRING for its temperatures; a value is compared at three places
IN_LIMITS = {"GREEN", "GREEN_LOW", "GREEN_HIGH", "BLUE", None}


def packets(truth):
    """[(met_s, items, utc)] of the COSMOS_PACKET records, oldest first, utc when the harness kept each."""
    return [(r["met_s"], r["body"]["items"], r["utc"]) for r in truth if r["type"] == "COSMOS_PACKET"]


def shown_at(kept, met_s):
    """The newest packet the seat had at met_s, or None."""
    found = [items for at, items, _ in kept if at <= met_s]
    return found[-1] if found else None


def kept_before(kept, utc):
    """The newest packet the harness had kept before a moment on its own clock, or None. A command can go out
    within the second whose packet already shows it, so the packet before a dispatch is found by time."""
    found = [items for _, items, at in kept if at < utc]
    return found[-1] if found else None


def matches(name, given, shown):
    """A number at the demo's three places; a state, or a float COSMOS gave as Infinity or NaN, exactly."""
    numbers = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (given, shown))
    if ITEMS[name]["type"] == "float" and numbers:
        return round(given, FLOAT_DECIMALS) == round(shown, FLOAT_DECIMALS)
    return given == shown


def checked(entry, kept):
    """An evidence entry beside what COSMOS showed then: {point, value, met_s, cosmos, units, limits_state, match}."""
    shown = shown_at(kept, entry["met_s"])
    item = shown.get(entry["point"]) if shown else None
    return {**entry, "cosmos": item["value"] if item else None, "units": ITEMS.get(entry["point"], {}).get("units"),
            "limits_state": item["limits_state"] if item else None,
            "match": item is not None and entry["point"] in ITEMS and matches(entry["point"], entry["value"], item["value"])}


def answers(records):
    """Each check-in with the CHECK_IN report that answered it, in order: [(check-in, report or None)]."""
    check_ins = [(r["met_s"], r["body"]) for r in of_type(records, "CHECK_IN")]
    reports = [r["body"] for r in of_type(records, "REPORT") if r["body"]["report_kind"] == "CHECK_IN"]
    return [(one, reports[i] if i < len(reports) else None) for i, one in enumerate(check_ins)]


def limits_line(name):
    found = ITEMS[name]["limits"]
    if found["kind"] != "thresholds":
        return None
    values = [found[key] for key in ("rl", "yl", "yh", "rh", "gl", "gh") if key in found]
    return "LIMITS DEFAULT 1 ENABLED " + " ".join(f"{v}" for v in values)


def check_collect(records, kept, report):
    requests = {r["body"]["request_id"]: r["body"] for r in of_type(records, "REQUEST")}
    sent = {r["body"]["request_id"]: r["body"]["utc"] for r in of_type(records, "DISPATCH")}
    accepted = [o["body"] for o in of_type(records, "OUTCOME") if o["body"]["outcome"] == "ACCEPTED"
                and requests.get(o["body"]["request_id"], {}).get("command") == "COLLECT"
                and requests[o["body"]["request_id"]]["parameters"].get("type") == "NORMAL"]
    rose = None
    if accepted:   # COLLECTS in the packet the seat had when it went out, and in the one that showed it accepted
        before = kept_before(kept, sent[accepted[0]["request_id"]])
        after = shown_at(kept, accepted[0]["frame_met_s"])
        rose = before is not None and after is not None and after["COLLECTS"]["value"] == before["COLLECTS"]["value"] + 1
    collects = accepted
    given = [checked(e, kept) for e in (report["condition"]["evidence"] if report else []) if e["point"] == "COLLECTS"]
    return {"success": bool(collects) and bool(rose) and len(given) >= 2 and all(g["match"] for g in given),
            "accepted": bool(collects), "count_rose_by_one": rose, "evidence": given}


def check_health(report, kept):
    given = [checked(e, kept) for e in (report["condition"]["evidence"] if report else [])]
    return {"success": bool(given) and all(g["match"] for g in given), "evidence": given}


def check_out_of_limits(report, kept):
    given = [checked(e, kept) for e in (report["condition"]["evidence"] if report else [])]
    named = [g for g in given if g["point"] in ITEMS and g["limits_state"] not in IN_LIMITS]
    return {"success": bool(named), "out_of_limits": [{**g, "limits_line": limits_line(g["point"])} for g in named],
            "evidence": given}


def check_phase_1(records, truth, track_s=60):
    """The three scored check-ins, and what S8 sets beside the prose for the Director."""
    kept = packets(truth)
    paired = answers(records)
    report = [r for _, r in paired] + [None] * (4 - len(paired))
    checks = {"collect": check_collect(records, kept, report[0]), "health_status": check_health(report[1], kept),
              "out_of_limits": check_out_of_limits(report[2], kept),
              "console_notes": {"scored": False, "notes": report[3]["answer"] if report[3] else None}}
    director = []
    for (met_s, check_in), answer in paired[:3]:
        named = sorted({e["point"] for e in (answer["condition"]["evidence"] if answer else []) if e["point"] in ITEMS})
        tracked = {name: [(at, items[name]["value"], items[name]["limits_state"]) for at, items, _ in kept
                          if met_s <= at <= met_s + track_s] for name in named}
        director.append({"check_in": check_in["text"], "answer": answer["answer"] if answer else None,
                         "cosmos_at_check_in": shown_at(kept, met_s), "named_items_over_60_s": tracked,
                         "limits_lines": {name: limits_line(name) for name in named}})
    return {"checks": checks, "for_the_director": director}
