"""Show S6's stand-in run: P3's pass flown by Muse Code's turn loop and stand-in adapter against the
harness, BALDUR-0 and the event log over HTTP, with a recorded check-in landing on the load-current alarm
at MET 900. Not collected by pytest.

    python tests/show_s6_run.py

It prints every turn ODIN took, with its triggers, BALDUR-0's decision and the outcome read from
telemetry, where the run's folder ended up, and whether the event log and truth file verify. The run is
a development run in a temporary folder, in the onboard seat with CHARGED pacing; every key is made in
memory, and the plan and act are signed with the development test key.
"""

import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from log.event_log import verify_event_log, verify_truth  # noqa: E402
from tests.harness_world import CHECK_IN, HarnessWorld  # noqa: E402
from tests.test_s6_run import stand_in  # noqa: E402


def main():
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop

    root = Path(tempfile.mkdtemp(prefix="odin-s6-run-"))
    harness = HarnessWorld(root)
    run = harness.run(check_ins=[(900, CHECK_IN)])
    signing.load_private_key = lambda private_key_path=None: harness.world.odin
    if not run.start():
        print("the run did not start")
        return 1
    seen = []
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(stand_in(seen)), repo_root=root)
    odin = threading.Thread(target=lambda: loop.run(max_turns=500), daemon=True)
    odin.start()
    odin.join(120)
    run.stop()
    records = [json.loads(line) for line in (run.folder / "events.jsonl").read_bytes().splitlines()]
    answers = {r["body"]["turn_id"]: r["body"]["answer"] for r in records if r["type"] == "ANSWER"}

    print(f"run {run.run_id}: plan in force MET {run.start_met_s} to {run.end_met_s}, contact 800 to 1230\n")
    print(" turn  MET   kind               triggers                                        ODIN")
    for bundle in seen:
        kind = bundle["turn_kind"] + (f" {bundle['report_kind']}" if bundle["report_kind"] else "")
        triggers = ", ".join(f"{t['type']} {t['met_s']}" for t in bundle["triggers"])
        answer = answers.get(bundle["turn_id"], {})
        said = answer.get("kind") or ("report" if bundle["turn_kind"] == "REPORT" else "")
        if answer.get("command"):
            said += f" {answer['command']} {answer['parameters']}"
        print(f" {bundle['turn_id']:>4}  {bundle['met_s']:>4}  {kind:<18} {triggers:<47} {said}")
    print()
    for type_ in ("CHECK_IN", "DECISION", "DISPATCH", "OUTCOME"):
        for record in (r for r in records if r["type"] == type_):
            body = record["body"]
            detail = {"CHECK_IN": lambda: f"{body['source']}: {body['text']!r}",
                      "DECISION": lambda: f"{body['decision']}, class {body['class']}, plan {body['plan_id']}",
                      "DISPATCH": lambda: f"{body['command']} {body['parameters']} by route {body['route']}",
                      "OUTCOME": lambda: f"{body['outcome']}, accepted {body['acc_before']} to {body['acc_after']}, "
                                         f"{body['point']['mnemonic']} {body['point']['value']}"}[type_]()
            print(f" {type_:<9} MET {record['met_s']:>4}  {detail}")
    attached = seen[-1]["procedures"][0]["attachments"]
    print(f"\n beside {seen[-1]['procedures'][0]['id']}: {[a['name'] for a in attached]}")
    print(f" folder: {run.folder.relative_to(root)}; runs/{run.run_id}/ left behind: {(root / 'runs' / run.run_id).exists()}")
    print(f" event log verifies: {verify_event_log(run.folder / 'events.jsonl') == []}; "
          f"truth file verifies: {verify_truth(run.folder / 'truth.jsonl') == []}; "
          f"RUN_END: {records[-1]['body']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
