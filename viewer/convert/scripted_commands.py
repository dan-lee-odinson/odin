"""Each phase-2 scenario's own scripted commands, read for VERDA.

The scenario of each phase-2 pass sends some commands by itself, each at a set
MET. The Director's flown passes carried all of them, so on his side of a
comparison they sit beside his own commands, and they are never his. ODIN's
runs keep the ones before contact and drop the ones in contact (the Director's
ruling on U35), so every command during a pass is ODIN's.

The input that lists them, phase2_scripted_commands.json, is data only: for each
pass, its plan, its contact window, and each command's MET, arguments, whether
it falls before or in contact, whether ODIN's runs keep it, and where it comes
from. VERDA checks each entry against the pass's own plan file: the contact
window is half-open, [aos_met_s, los_met_s), and a command in it must not be
kept. An entry that disagrees is listed as a problem, and the page shows it.

This module only reads. It never writes.
"""

import hashlib
import json
from pathlib import Path

BEFORE, IN_CONTACT, AFTER = "before contact", "in contact", "after contact"


class ScriptedError(Exception):
    pass


def when(met_s, window):
    """Where a MET falls against a contact window, half-open [aos_met_s, los_met_s)."""
    if met_s < window["aos_met_s"]:
        return BEFORE
    if met_s < window["los_met_s"]:
        return IN_CONTACT
    return AFTER


def read(path, plans):
    """Reads the scripted-commands file. `plans` is the plans' fields (pass_records.read_plan)."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ScriptedError("%s cannot be read: %s" % (path.name, exc))
    if not isinstance(data, dict) or not isinstance(data.get("passes"), list):
        raise ScriptedError("%s holds no list of passes" % path.name)
    by_plan = {plan["plan_id"]: plan for plan in plans}
    problems, passes = [], {}
    for entry in data["passes"]:
        plan_id = entry.get("plan_id")
        window = entry.get("contact_window") or {}
        plan = by_plan.get(plan_id)
        if plan is None:
            problems.append("%s: no plan file %s to check it against" % (entry.get("pass"), plan_id))
        elif [window.get("aos_met_s"), window.get("los_met_s")] != [plan["aos_met_s"], plan["los_met_s"]]:
            problems.append("%s: its contact window %s is not its plan's, MET %d to %d" % (
                entry.get("pass"), window, plan["aos_met_s"], plan["los_met_s"]))
        if plan is not None:
            window = {"aos_met_s": plan["aos_met_s"], "los_met_s": plan["los_met_s"]}
        commands = []
        for n, item in enumerate(entry.get("commands") or [], start=1):
            met = item.get("met_s")
            if not isinstance(met, (int, float)) or not item.get("command"):
                problems.append("%s command %d names no MET or no command" % (entry.get("pass"), n))
                continue
            kept = item.get("kept_in_odins_runs")
            # With no plan file to check it against, the entry keeps its own word, and the missing plan is the problem.
            found = when(met, window) if plan is not None else None
            if found is not None and item.get("when") != found:
                problems.append("%s %s at MET %s: the file says %r, its plan's window says %r" % (
                    entry.get("pass"), item["command"], met, item.get("when"), found))
            if found is not None and kept is not (found != IN_CONTACT):
                problems.append("%s %s at MET %s: kept in ODIN's runs is %r, but it falls %s" % (
                    entry.get("pass"), item["command"], met, kept, found))
            commands.append({"met_s": met, "command": item["command"], "parameters": item.get("arguments") or {},
                             "when": found or item.get("when"),
                             "kept_in_odins_runs": kept if found is None else found != IN_CONTACT,
                             "source": item.get("source")})
        passes[plan_id] = {"pass": entry.get("pass"), "plan_id": plan_id, "scenario": entry.get("scenario"),
                           "contact_window": window, "commands": sorted(commands, key=lambda c: c["met_s"])}
    return {"file": path.name, "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            "derived_from": data.get("derived_from"), "passes": passes, "problems": problems}


def for_plan(scripted, plan_id):
    """The scripted commands of the pass flown under a plan, or None when the file lists none."""
    return (scripted or {}).get("passes", {}).get(plan_id)
