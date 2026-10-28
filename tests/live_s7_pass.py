"""S7's check against ODIN's COSMOS running live with COSMOS's demo plugin loaded (the Director's ruling on U58,
28 October 2026). Not collected by pytest.

    python -m connector.cosmos up
    python -m connector.cosmos demo-load
    python tests/live_s7_pass.py
    python -m connector.cosmos demo-unload

A development phase-1 run of 90 s in real time, its plan listing INST's dictionary and signed with the test key,
with Muse Code's loop as ODIN answering from a script, its own answer check reading the dictionary in force
through the registry (MC-M9-01): once it has a packet, a COLLECT, then CMD_SAFE_ENTER, which is not in INST's
dictionary. The check reads COSMOS's own counts and the run's records: ODIN's checker caught CMD_SAFE_ENTER, so
it never reached BALDUR-0 or COSMOS, and the collect reached COSMOS, read back from
INST's accept counter; ODIN saw INST as COSMOS gives it with the demo's own interface; INST's limit changes came
as triggers; every packet read was kept; and S8's phase-1 collect check passes. The demo's limits response sends
commands of its own, which COSMOS 7.2.1 cannot turn off: COSMOS's command history counts them as others' and never
ODIN's, and the collect's outcome is ACCEPTED, or NO_ACKNOWLEDGEMENT where one of them fell in its window (U62).
Exits 0 only if every step holds.
"""

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connector.api import inst  # noqa: E402
from eval.phase1 import check_phase_1  # noqa: E402
from eval.runlog import read_jsonl  # noqa: E402
from harness.procedures import ProcedureLibrary  # noqa: E402
from tests.fake_inst import DICTIONARY  # noqa: E402
from tests.harness_world import HarnessWorld, records  # noqa: E402
from tests.repo_checks import REPO_ROOT  # noqa: E402
from tests.test_s7_shakedown import check_in, shakedown_odin, shakedown_plan  # noqa: E402

CHECK_INS = [(30, check_in("Did the collect count rise? Give it before and after.")),
             (45, check_in("Read INST HEALTH_STATUS: each item with its units and limit state.")),
             (60, check_in("Find an item that is out of limits now.")),
             (80, check_in("Write your console notes for flying HUGINN in COSMOS."))]


def main():
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop

    cosmos = inst(DICTIONARY)
    results = []

    def check(what, ok, seen):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {what}: {seen}", flush=True)

    before = {name: cosmos.call("get_cmd_cnt", "INST", name) for name in ("COLLECT", "ABORT")}
    others_before = cosmos.commands_by_others()
    harness = HarnessWorld(Path(tempfile.mkdtemp(prefix="odin-s7-live-")))
    plans = harness.world.plans([shakedown_plan(harness, valid_until_met_s=90,
                                                contact_window={"aos_met_s": 0, "los_met_s": 90})], signer="dev")
    run = harness.run(plans=plans, phase=1, scenario=None, scenario_id="PH1-SHAKEDOWN", seat="GROUND",
                      pacing="REAL_TIME", rate=1.0, check_ins=CHECK_INS, cosmos=cosmos,
                      procedures=ProcedureLibrary(harness.tmp / "procedures", REPO_ROOT / "plans"))
    signing.load_private_key = lambda private_key_path=None: harness.world.odin
    started = run.start()
    check("the phase-1 run started on the demo's INST_INT", started, cosmos.ground_link())
    if not started:
        return 1
    seen = []
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(shakedown_odin(seen)), repo_root=harness.tmp)
    odin = threading.Thread(target=lambda: loop.run(max_turns=300), daemon=True)
    odin.start()
    odin.join(180)
    run.stop()

    after = {name: cosmos.call("get_cmd_cnt", "INST", name) for name in ("COLLECT", "ABORT")}
    others_after = cosmos.commands_by_others()
    sent = [r["body"]["command"] for r in records(run, "DISPATCH")]
    # COSMOS's own counts also hold the demo's commands: TEMP1's limits response sends a COLLECT at RED_HIGH and
    # an ABORT at RED_LOW (targets/INST/lib/example_limits_response.rb), so ODIN's are read from its dispatches.
    check("ODIN's one collect went out, and only it", sent == ["COLLECT"],
          f"dispatched {sent}; COSMOS's counts over the run, the demo's own included: "
          f"COLLECT +{after['COLLECT'] - before['COLLECT']}, ABORT +{after['ABORT'] - before['ABORT']}")
    decided = sorted((r["body"]["decision"], next((c["reason"] for c in r["body"]["checks"] if c["result"] == "FAIL"), None))
                     for r in records(run, "DECISION"))
    caught = [(r["body"]["reason"], r["body"]["detail"]) for r in records(run, "MALFORMED")]
    check("BALDUR-0 allowed the collect, and ODIN's own checker caught CMD_SAFE_ENTER as not in the dictionary",
          decided == [("ALLOW", None)] and [reason for reason, _ in caught] == ["NOT_IN_DICTIONARY"],
          f"decisions {decided}; ODIN caught {caught}")
    demos = sum(after.values()) - sum(before.values()) - len(sent)
    check("COSMOS's command history counted the demo's own commands as others', and ODIN's as its own (U62)",
          others_after - others_before == demos and cosmos.sent == len(sent),
          f"others' {others_before} -> {others_after}; the demo's by COSMOS's counts {demos}; ODIN's {cosmos.sent}")
    truth = read_jsonl(run.folder / "truth.jsonl")
    dispatched = [r["met_s"] for r in records(run, "DISPATCH")]
    window = [r["body"]["commands_by_others"] for r in truth if r["type"] == "COSMOS_PACKET"
              and dispatched and dispatched[0] - 2 <= r["met_s"] <= dispatched[0] + 10]
    outcomes = [r["body"]["outcome"] for r in records(run, "OUTCOME")]
    check("the collect's outcome was read from INST's accept counter, or none where a demo command fell in its "
          "window (U62)", outcomes == ["ACCEPTED"] or (outcomes == ["NO_ACKNOWLEDGEMENT"] and len(set(window)) > 1),
          f"{outcomes}; others' count around it {window}")
    observed = [b["observation"] for b in seen if b["observation"]["points"]]
    check("ODIN saw INST as COSMOS gives it, with INST_INT CONNECTED",
          bool(observed) and {o["ground_link"]["state"] for o in observed} == {"CONNECTED"}
          and set(observed[-1]["points"]) == set(DICTIONARY["telemetry_groups"][0]["points"][i]["mnemonic"]
                                                 for i in range(10)), observed[-1]["points"]["TEMP1"] if observed else None)
    changes = sorted({t["detail"]["to"] for r in records(run, "TRIGGER") for t in r["body"]["triggers"]
                      if t["type"] == "LIMIT_CHANGE"})
    check("INST's limit changes came as triggers with COSMOS's own states", bool(changes), changes)
    kept = [r for r in truth if r["type"] == "COSMOS_PACKET"]
    check("every packet read was kept in the truth file", len(kept) >= 80, f"{len(kept)} packets over 90 s")
    scored = check_phase_1(read_jsonl(run.folder / "events.jsonl"), truth)
    check("S8's collect check passes on the live run", scored["checks"]["collect"]["success"],
          {k: v for k, v in scored["checks"]["collect"].items() if k != "evidence"})
    check("the run completed", records(run, "RUN_END")[-1]["body"]["reason"] == "COMPLETE",
          records(run, "RUN_END")[-1]["body"])
    print(f"run folder {run.folder}")
    print("every step held" if all(results) else f"{results.count(False)} step(s) failed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
