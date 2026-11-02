"""Every outside feed of all five sealed scenarios, generated with the feeds' code as it was before every feed rule was
read from the seal and as it is now, compared report by report (the Director's ruling of 30 October 2026, RULINGS.md
item 9). Held out; reads the repository, writes nothing.

    PYTHONDONTWRITEBYTECODE=1 python compare_feeds.py [BEFORE_COMMIT]      from the repository's root

Before: wrapper/feeds.py and harness/phase3.py as they were at BEFORE_COMMIT (4ab988c by default), the rules in the
code. Now: the working tree's, every rule read from the sealed feed details. Each version reads the sealed folder
against the seal in force and builds the scenario's four feeds as the harness does. Each scenario's own simulator then
steps from its first acquisition of signal to its end, with its scripted latch-up, as a run's does (no ODIN, so no
command), and each tick's true state goes to both versions' feeds. Every report of both, in order, is compared as
JSON, key order included. Also shown: the draw rule read from the seal reproduces each scenario's sealed schedule
exactly, as the code's constants did, and the replay every scenario reads is the sealed file, byte for byte.
"""

import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HELD_OUT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.dont_write_bytecode = True

BEFORE = sys.argv[1] if len(sys.argv) > 1 else "4ab988c"


def source_at(commit, path):
    return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def module(name, source):
    made = types.ModuleType(name)
    made.__file__ = str(REPO / "harness" / f"{name}.py")   # so its ROOT, two folders up, is the repository
    sys.modules[name] = made
    exec(compile(source, f"<{name} at {BEFORE}>", "exec"), made.__dict__)
    return made


# The code as it was: its feeds module under its own name, and its phase3 module reading it.
feeds_before = module("feeds_before", source_at(BEFORE, "wrapper/feeds.py"))
phase3_source = source_at(BEFORE, "harness/phase3.py")
old_import = "from wrapper.feeds import CoreFeeds, Feeds, OtherStations, SpaceWeather\n"
assert phase3_source.count(old_import) == 1
phase3_before = module("phase3_before", phase3_source.replace(
    old_import, "from feeds_before import CoreFeeds, Feeds, OtherStations, SpaceWeather\n"))

# The code as it is.
import harness.phase3 as phase3_now  # noqa: E402
import wrapper.feeds as feeds_now  # noqa: E402
from wrapper.simulator import Simulator  # noqa: E402

before_held, now_held = phase3_before.HeldOut(HELD_OUT), phase3_now.HeldOut(HELD_OUT)
assert before_held.labels() == now_held.labels() and len(now_held.labels()) == 5
manifest = {line.split("  ")[1]: line.split("  ")[0]
            for line in (HELD_OUT / "sealed" / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()}
print(f"seal in force: {phase3_now.seal_in_force()}; before {BEFORE}, now the working tree")

problems = []
for label in now_held.labels():
    before, now = before_held.scenario(label), now_held.scenario(label)
    # The replay: the sealed file, byte for byte, the same one each version reads.
    name = now.feeds["space_weather"]["replay"]
    replay_ok = (hashlib.sha256((HELD_OUT / "sealed" / name).read_bytes()).hexdigest() == manifest[name]
                 and before.replay == now.replay)
    # The draw rule read from the seal, and the code's constants before, against the sealed schedule.
    rule, sealed_schedule = now.draw_rule, now.feeds["other_stations"]["schedule"]
    drawn_now = feeds_now.draw_schedule(rule["seed"], now.beacon_mets(), rule["stations"], rule["heard_p"],
                                        rule["delay_s"])
    drawn_before = feeds_before.draw_schedule(rule["seed"], now.beacon_mets(), rule["stations"])
    # Every feed, both versions, one simulator.
    feeds_b, feeds_n = before.all_feeds(), now.all_feeds()
    first_aos, end = before.windows[0][0], before.run["end_met_s"]
    sim = Simulator(before.huginn, windows=before.windows, start_at=first_aos, latch_up=before.latch_up)
    reports_b, reports_n = [], []
    while sim.met_s < end:
        sim.step()
        met, state = sim.met_s, sim.true_state()
        utc = f"made-up-utc-{met}"   # the same for both; a run's comes from its clock
        reports_b += feeds_b.tick(met, utc, state)
        reports_n += feeds_n.tick(met, utc, state)
    same = bool(reports_n) and json.dumps(reports_b) == json.dumps(reports_n)
    counts = Counter(r["feed"] for r in reports_n)
    # The core rules over a sweep of inputs too, wider than one flight's states: every range from 200 to 3,000 km by
    # 0.25 km, and every battery voltage from 5.5 to 8.5 V by 0.001 V and state of charge from 0 to 100 % by 0.05 %.
    rules = now.core_rules
    levels = all(feeds_before.signal_level_dbm(km / 4) == feeds_now.signal_level_dbm(km / 4, rules)
                 for km in range(800, 12001))
    swept = [{"eps": {"mode": mode, "battery_v": mv / 1000, "soc_pct": 50.0}}
             for mode in ("NOMINAL", "LOW_POWER", "SAFE") for mv in range(5500, 8501)] + \
            [{"eps": {"mode": "NOMINAL", "battery_v": 7.4, "soc_pct": soc / 20}} for soc in range(0, 2001)]
    beacons = all(feeds_before.beacon_content(s) == feeds_now.beacon_content(s, rules) for s in swept)
    ok = same and drawn_now == sealed_schedule and drawn_before == sealed_schedule and replay_ok and levels and beacons
    print(f"{label}: METs {first_aos} to {end}, receiver fault {now.receiver_down or 'none'}; reports before "
          f"{len(reports_b)}, now {len(reports_n)}, {'identical' if same else 'DIFFERENT'} "
          f"({dict(sorted(counts.items()))}); sealed schedule of {len(sealed_schedule)} reproduced by the rule read "
          f"from the seal: {drawn_now == sealed_schedule}, by the code's constants before: "
          f"{drawn_before == sealed_schedule}; replay the sealed file: {replay_ok}; signal levels over the sweep "
          f"identical: {levels}; beacon contents over the sweep identical: {beacons}")
    if not ok:
        problems.append(label)
print("every feed of all five sealed scenarios identical before and now" if not problems
      else f"NOT identical: {problems}")
sys.exit(1 if problems else 0)
