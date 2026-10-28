"""S5's check against ODIN's COSMOS running live (00_HANDOFF.md §4, S5). Not collected by pytest.

    python -m connector.cosmos up
    python tests/live_s5_pass.py

A ground-seat run of a short P3 contact, MET 800 to 900, in real time through the link on 8713, with
Muse Code's turn loop as ODIN answering from a script: it asks for CMD_MODE_SET, which the plan prohibits,
then CMD_PLD_SET_STATE OFF and CMD_SAFE_ENTER. The check reads COSMOS's own counts and telemetry: COSMOS
marks hazardous the commands the dictionary does; the refused command never reached COSMOS; the two allowed
ones did, the hazardous one through the no-hazardous-check send, and their outcomes were read from COSMOS's
telemetry; ODIN saw COSMOS's view with the ground link. Exits 0 only if every step holds. The credentials
come from the ODIN_COSMOS_* variables and are never shown.
"""

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connector.api import TARGET, CosmosApi  # noqa: E402
from tests.harness_world import HarnessWorld, records  # noqa: E402
from tests.test_s5_connector import ASKED, SHORT, scripted  # noqa: E402
from wrapper.frames import COMMANDS  # noqa: E402


def main():
    from odin.adapters.stand_in import StandInAdapter
    from odin.loop import signing
    from odin.loop.loop import TurnLoop

    cosmos = CosmosApi()
    results = []

    def check(what, ok, seen):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {what}: {seen}", flush=True)

    hazardous = {name: cosmos.call("get_cmd_hazardous", TARGET, name) for name in COMMANDS}
    check("COSMOS marks hazardous the commands the dictionary does",
          hazardous == {name: spec["hazardous"] for name, spec in COMMANDS.items()}, hazardous)
    before = {name: cosmos.call("get_cmd_cnt", TARGET, name) for name in COMMANDS}

    harness = HarnessWorld(Path(tempfile.mkdtemp(prefix="odin-s5-live-")))
    plans = harness.world.plans([harness.plan(**SHORT, prohibited=["CMD_MODE_SET"])], signer="dev")
    run = harness.run(plans=plans, seat="GROUND", pacing="REAL_TIME", rate=1.0, cosmos=cosmos)
    signing.load_private_key = lambda private_key_path=None: harness.world.odin
    print("waiting for COSMOS's HUGINN_INT to dial the link", flush=True)
    started = run.start()
    check("HUGINN_INT dialed the link and the run started", started, f"link clients {run.link.clients if run.link else 0}")
    if not started:
        return 1
    seen = []
    loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                    adapter=StandInAdapter(scripted(*ASKED, seen=seen)), repo_root=harness.tmp)
    odin = threading.Thread(target=lambda: loop.run(max_turns=200), daemon=True)
    odin.start()
    odin.join(200)
    run.stop()

    after = {name: cosmos.call("get_cmd_cnt", TARGET, name) for name in COMMANDS}
    sent = {name: after[name] - before[name] for name in COMMANDS}
    check("the command BALDUR-0 refused never reached COSMOS, the two it allowed did",
          sent == {name: 1 if name in ("CMD_PLD_SET_STATE", "CMD_SAFE_ENTER") else 0 for name in COMMANDS}, sent)
    decided = sorted(r["body"]["decision"] for r in records(run, "DECISION"))
    check("BALDUR-0 refused one request and allowed two", decided == ["ALLOW", "ALLOW", "REFUSE"], decided)
    applied = [(name, accepted) for _, name, accepted, _ in run.simulator.applied]
    check("both reached the spacecraft", applied == [("CMD_PLD_SET_STATE", True), ("CMD_SAFE_ENTER", True)], applied)
    outcomes = [r["body"]["outcome"] for r in records(run, "OUTCOME")]
    check("their outcomes were read from COSMOS's telemetry", outcomes == ["ACCEPTED", "ACCEPTED"], outcomes)
    states = {o["ground_link"]["state"] for o in seen}
    check("ODIN saw COSMOS's view with the ground link CONNECTED",
          bool(seen) and {o["source"] for o in seen} == {"COSMOS"} and states == {"CONNECTED"}, states)
    onboard = {f["CDH_MET"]: f for f in run.simulator.tap.history()}
    ground = [frame for frame, _ in run.store._frames]
    check("the ground seat's frames carry the values the spacecraft sent",
          bool(ground) and all(frame == onboard[frame["CDH_MET"]] for frame in ground),
          f"{len(ground)} frames from COSMOS, {len(onboard)} generated")
    print(f"run folder {run.folder}")
    print("every step held" if all(results) else f"{results.count(False)} step(s) failed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
