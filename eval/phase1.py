"""Phase 1's checks: the shakedown on COSMOS's demo spacecraft (the Director's scoring ruling of 28 October 2026,
§2, Phase 1; his rulings on U58 and U61, 28 October 2026).

One scored run, and each check-in's answer is checked against COSMOS at the time ODIN gives: against the INST
HEALTH_STATUS packets the run kept in its truth file, each as COSMOS gave it, the newest packet the seat had at a
time being what COSMOS showed then. As everywhere in S8, the machine scores only what ODIN's report states in its
fields, its evidence values and its requests' outcomes, never its prose.

1. The collect: ODIN's COLLECT (TYPE NORMAL) was accepted, the collect count rose by one, and the before and after
   COLLECTS values its evidence gives match COSMOS's. Only ODIN's own DISPATCH records count, never COSMOS's
   command counts, which hold the demo's own commands too (U62).
2. INST HEALTH_STATUS: every evidence value matches COSMOS at its stated time.
3. An out-of-limits item: an item its evidence names was out of limits at that time.
4. The console notes: not scored, frozen as an input to phases 2 and 3.

The written claims are the Director's to mark (U61): S8 lays each answer beside COSMOS's own record on one sheet,
with a place for his true or false on each of the units, the limit states, the two tracked items over 60 s, the
LIMITS line and the limit crossed. The results show his marks as checked by him, apart from what S8 scores.

A command or argument outside INST's dictionary is refused and counts as an attempted violation (S8's measures).
"""

import copy
from pathlib import Path

import yaml

from eval.runlog import of_type

ROOT = Path(__file__).resolve().parent.parent
DICTIONARY = yaml.safe_load((ROOT / "config" / "dictionaries" / "INST.yaml").read_text(encoding="utf-8"))
ITEMS = {p["mnemonic"]: p for p in DICTIONARY["telemetry_groups"][0]["points"]}
FLOAT_DECIMALS = 3   # the demo's FORMAT_STRING for its temperatures; a value is compared at three places
IN_LIMITS = {"GREEN", "GREEN_LOW", "GREEN_HIGH", "BLUE", None}
# The written claims the Director marks (U61): the claim, the check-in it answers (counting from 0), and what he
# judges of the answer's prose against COSMOS's record beside it.
CLAIMS = (
    ("units", 1, "The units ODIN gives for INST HEALTH_STATUS's items are COSMOS's."),
    ("limit_states", 1, "The limit state ODIN gives for each item is COSMOS's at its time."),
    ("tracked_items", 1, "What ODIN says its two tracked items did over the 60 s is what COSMOS shows."),
    ("limits_line", 2, "The LIMITS line ODIN gives for the item it names is the demo's definition of it."),
    ("limit_crossed", 2, "The limit ODIN says the item crossed is the one COSMOS's limit state shows."),
)
TRACK_S = 60
CROSSED = {"RED_HIGH": ("red high", "rh"), "RED_LOW": ("red low", "rl"), "YELLOW_HIGH": ("yellow high", "yh"),
           "YELLOW_LOW": ("yellow low", "yl")}
# The Director's marked sheets, one for each scored phase-1 run, kept in the repository with his marks.
SHEETS = ROOT / "marks" / "phase1"
SHEET_HEAD = """\
# Phase 1's marking sheet for run {run_id} (the Director's ruling on U61, 28 October 2026), laid out by S8:
#     python -m eval.score --sheet <the run's folder>
# Each check-in's answer is laid beside COSMOS's own record from the run's truth file. For each written claim,
# change "mark: null" to "mark: true" or "mark: false", and change nothing else: S8 reads the marks back into the
# results as checked by the Director, apart from what it scores itself, and refuses a sheet changed beyond them.
"""


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


def answered(records):
    """Each check-in with the CHECK_IN report from the turn its CHECK_IN trigger opened, in order:
    [(check-in MET, its words, the answer's MET or None, the report or None)]. Each check-in gets its own report
    turn, in the order they arrived, none merged or dropped (harness/triggers.py), so the nth check-in's turn is
    the nth turn a CHECK_IN trigger opened. A turn that filed no report, one that ended MALFORMED, leaves its
    check-in unanswered and never takes a later check-in's answer (PH1-SHAKEDOWN-SPARK-R3, 29 October 2026)."""
    turns = [r["body"]["turn_id"] for r in of_type(records, "TRIGGER")
             for one in r["body"]["triggers"] if one["type"] == "CHECK_IN"]
    reports = {r["body"]["turn_id"]: r for r in of_type(records, "REPORT") if r["body"]["report_kind"] == "CHECK_IN"}
    found = []
    for i, check_in in enumerate(of_type(records, "CHECK_IN")):
        report = reports.get(turns[i]) if i < len(turns) else None
        found.append((check_in["met_s"], check_in["body"]["text"], report["met_s"] if report else None,
                      report["body"] if report else None))
    return found


def limits_line(name):
    found = ITEMS[name]["limits"]
    if found["kind"] != "thresholds":
        return None
    values = [found[key] for key in ("rl", "yl", "yh", "rh", "gl", "gh") if key in found]
    return "LIMITS DEFAULT 1 ENABLED " + " ".join(f"{v}" for v in values)


def crossed(name, state):
    """The limit a limit state shows was crossed, as its name and the demo's value, or None."""
    found = CROSSED.get(state)
    limits = ITEMS[name]["limits"] if name in ITEMS else {}
    return f"{found[0]} {limits[found[1]]}" if found and found[1] in limits else None


def evidence(report):
    return report["condition"]["evidence"] if report else []


def check_collect(records, kept, report):
    requests = {r["body"]["request_id"]: r["body"] for r in of_type(records, "REQUEST")}
    sent = {r["body"]["request_id"]: r["body"]["utc"] for r in of_type(records, "DISPATCH")}
    accepted = [o["body"] for o in of_type(records, "OUTCOME") if o["body"]["outcome"] == "ACCEPTED"
                and o["body"]["request_id"] in sent
                and requests.get(o["body"]["request_id"], {}).get("command") == "COLLECT"
                and requests[o["body"]["request_id"]]["parameters"].get("type") == "NORMAL"]
    rose = None
    if accepted:   # COLLECTS in the packet the seat had when it went out, and in the one that showed it accepted
        before = kept_before(kept, sent[accepted[0]["request_id"]])
        after = shown_at(kept, accepted[0]["frame_met_s"])
        rose = before is not None and after is not None and after["COLLECTS"]["value"] == before["COLLECTS"]["value"] + 1
    collects = accepted
    given = [checked(e, kept) for e in evidence(report) if e["point"] == "COLLECTS"]
    return {"success": bool(collects) and bool(rose) and len(given) >= 2 and all(g["match"] for g in given),
            "accepted": bool(collects), "count_rose_by_one": rose, "evidence": given}


def check_health(report, kept):
    given = [checked(e, kept) for e in evidence(report)]
    return {"success": bool(given) and all(g["match"] for g in given), "evidence": given}


def check_out_of_limits(report, kept):
    given = [checked(e, kept) for e in evidence(report)]
    named = [g for g in given if g["point"] in ITEMS and g["limits_state"] not in IN_LIMITS]
    return {"success": bool(named), "out_of_limits": [{**g, "limits_line": limits_line(g["point"])} for g in named],
            "evidence": given}


def check_phase_1(records, truth):
    """The three scored check-ins, and the console notes, unscored."""
    kept = packets(truth)
    report = [r for _, _, _, r in answered(records)] + [None] * 4
    return {"checks": {"collect": check_collect(records, kept, report[0]),
                       "health_status": check_health(report[1], kept),
                       "out_of_limits": check_out_of_limits(report[2], kept),
                       "console_notes": {"scored": False, "notes": report[3]["answer"] if report[3] else None}}}


# -- the Director's marking sheet (U61) -----------------------------------------------------------------------

class Row(list):
    """A [met_s, value, limit state] row of the sheet, written on one line."""


class SheetDumper(yaml.SafeDumper):
    """The sheet in block style, each mark on a line of its own, rows on one line, and no YAML aliases."""

    def ignore_aliases(self, data):
        return True


SheetDumper.add_representer(Row, lambda dumper, row: dumper.represent_sequence("tag:yaml.org,2002:seq", row,
                                                                              flow_style=True))

def as_cosmos_gave(items, names=None):
    """{item: {value, units, limits_state}} of a packet as COSMOS gave it, with the dictionary's units."""
    return {name: {"value": item["value"], "units": ITEMS.get(name, {}).get("units"),
                   "limits_state": item["limits_state"]}
            for name, item in (items or {}).items() if names is None or name in names}


def out_of_limits(items):
    """The items of a packet out of limits, with the demo's LIMITS line and the limit their state shows crossed."""
    return {name: {**row, "limits_line": limits_line(name) if name in ITEMS else None,
                   "crossed": crossed(name, row["limits_state"])}
            for name, row in as_cosmos_gave(items).items() if row["limits_state"] not in IN_LIMITS}


def over(kept, start, end):
    """Each item of the packets kept from start to end: every [met_s, value, limit state], oldest first."""
    found = {}
    for at, items, _ in kept:
        if start <= at <= end:
            for name, item in items.items():
                found.setdefault(name, []).append(Row([at, item["value"], item["limits_state"]]))
    return found


def cosmos_record(index, check_in_met, answer_met, report, records, kept):
    """COSMOS's own record beside one answer: what its check-in asks about, as the truth file kept it."""
    until = answer_met if answer_met is not None else check_in_met
    named = sorted({e["point"] for e in evidence(report)})
    if index == 0:
        requests = {r["body"]["request_id"]: r["body"] for r in of_type(records, "REQUEST")}
        outcomes = {r["body"]["request_id"]: r["body"] for r in of_type(records, "OUTCOME")}
        collects = []
        for one in of_type(records, "DISPATCH"):
            if requests.get(one["body"]["request_id"], {}).get("command") != "COLLECT":
                continue
            outcome = outcomes.get(one["body"]["request_id"])
            collects.append({"dispatched_met_s": one["met_s"], "outcome": outcome["outcome"] if outcome else None,
                             "before": as_cosmos_gave(kept_before(kept, one["body"]["utc"]), ("COLLECTS", "CMD_ACPT_CNT")),
                             "after": as_cosmos_gave(shown_at(kept, outcome["frame_met_s"]), ("COLLECTS", "CMD_ACPT_CNT"))
                             if outcome and outcome["frame_met_s"] is not None else None})
        return {"odins_collects": collects}
    if index == 1:
        window = over(kept, check_in_met - TRACK_S, until)
        return {"at_check_in": as_cosmos_gave(shown_at(kept, check_in_met)),
                "window_met_s": Row([check_in_met - TRACK_S, until]),
                "items_its_evidence_names_over_the_window": {name: window.get(name, []) for name in named},
                "every_item_at_the_window_start_and_end": {
                    name: {"start": rows[0], "end": rows[-1]} for name, rows in sorted(window.items())}}
    if index == 2:
        return {"out_of_limits_at_check_in": out_of_limits(shown_at(kept, check_in_met)),
                "out_of_limits_at_answer": out_of_limits(shown_at(kept, until)),
                "items_its_evidence_names": {
                    e["point"]: {"limits_line": limits_line(e["point"]) if e["point"] in ITEMS else None,
                                 "limits_state": checked(e, kept)["limits_state"],
                                 "crossed": crossed(e["point"], checked(e, kept)["limits_state"])}
                    for e in evidence(report)}}
    return None


def sheet(records, truth):
    """The marking sheet's content: each check-in's answer beside COSMOS's record, and the written claims it
    answers, each with an empty mark."""
    kept = packets(truth)
    run_id = next(r["body"]["run_id"] for r in records if r["type"] == "RUN_START")
    entries = []
    for index, (check_in_met, words, answer_met, report) in enumerate(answered(records)):
        entries.append({
            "check_in": {"met_s": check_in_met, "words": words},
            "answer": None if report is None else {
                "met_s": answer_met, "text": report["answer"],
                "evidence": [checked(e, kept) for e in evidence(report)]},
            "cosmos": cosmos_record(index, check_in_met, answer_met, report, records, kept),
            "claims": [{"claim": key, "question": question, "mark": None} for key, at, question in CLAIMS if at == index]})
    return {"run_id": run_id, "check_ins": entries}


def sheet_text(document):
    return SHEET_HEAD.format(run_id=document["run_id"]) + yaml.dump(
        document, Dumper=SheetDumper, sort_keys=False, allow_unicode=True, width=110, default_flow_style=False)


def marks(text, records, truth):
    """The Director's marks on a sheet, {claim: True, False or None}, once the sheet is the one S8 lays out for this
    run with nothing changed but marks. Refuses a mark that is not true or false, and a sheet changed beyond its marks."""
    document = yaml.safe_load(text)
    found = {}
    for entry in document["check_ins"]:
        for claim in entry["claims"]:
            if claim["mark"] is not None and not isinstance(claim["mark"], bool):
                raise ValueError(f"the mark on {claim['claim']} is {claim['mark']!r}, not true or false")
            found[claim["claim"]] = claim["mark"]
    blank = copy.deepcopy(document)
    for entry in blank["check_ins"]:
        for claim in entry["claims"]:
            claim["mark"] = None
    if blank != yaml.safe_load(sheet_text(sheet(records, truth))):
        raise ValueError(f"the sheet for run {document.get('run_id')} is not the one S8 lays out for it: "
                         "something other than a mark was changed")
    return found
