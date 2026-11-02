"""COSMOS's warm-up before a scored run (the Director's ruling of 31 October 2026, "Lift it; warm COSMOS first; re-fly
R3 as R8"): PH3-H03-SPARK-R3 lost its first frame when COSMOS, fresh from the machine's restart, showed it 0.516 s
after it was sent, past the ground seat's 0.5 s wait. R1 and R2 had theirs shown within 10 and 8 ms.

A stand-in development run of C (H03), as standin_switch.py flies it, through the real COSMOS, from its start to its
first acquisition of signal and on until the ground seat has had FRAMES frames sent, then stopped. No call to any model
provider. Each tick the ground seat waits for COSMOS is timed, by a wrapper around the harness's own _ground_frame in
this process only; no repository file changes. HELD OUT in use: the run folder is under a temporary root, deleted
afterward; the summary goes to the held-out folder's warmup/.

It passes when every one of the first FIRST frames is shown within WITHIN_S, tens of milliseconds as R1's and R2's
were, and no frame is missed. Exit 0 if it passes, 1 if not.

    python warm_cosmos.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HELD_OUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from eval import runlog  # noqa: E402
from harness import docs  # noqa: E402
from harness.phase3 import HeldOut  # noqa: E402
from harness.run import Run  # noqa: E402
from harness.procedures import ProcedureLibrary  # noqa: E402
from odin.adapters.stand_in import StandInAdapter  # noqa: E402
from odin.loop import signing  # noqa: E402
from odin.loop.loop import TurnLoop  # noqa: E402
from tests.harness_world import LOCAL, HarnessWorld  # noqa: E402

LABEL = "H03"
RUN_ID = "dev-ph3-warmup-h03"
FRAMES = 30          # frames sent in the ground seat before the run is stopped
FIRST = 10           # the first frames that must each be shown within WITHIN_S
WITHIN_S = 0.1       # "within tens of milliseconds"
LIMIT_S = 300        # the run is stopped by then whatever it has had
REFERENCE = json.loads((REPO / "odin" / "study" / "cosmos_reference.json").read_text(encoding="utf-8"))["sha256"]
CONFIG = {"seed": 20261031, "model_config": "stand_in", "answer_method": "SCRIPTED", "reference_sha256": REFERENCE}
OUT = HELD_OUT / "warmup"


def cosmos_containers():
    """{name: StartedAt} for ODIN's COSMOS containers (compose project odin), read-only."""
    names = subprocess.run(["docker", "ps", "--filter", "label=com.docker.compose.project=odin", "--format",
                            "{{.Names}}"], capture_output=True, text=True).stdout.split()
    started = {}
    for name in names:
        started[name] = subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}}", name],
                                       capture_output=True, text=True).stdout.strip()
    return started


WAITS = []   # each tick the link sent a frame on, in the ground seat: its MET, the seat's wait, what COSMOS showed
_ground_frame = Run._ground_frame


def timed(self, met):
    sent = self.link.counts["SENT"] > self._sent_seen
    started = time.monotonic()
    frame = _ground_frame(self, met)
    if sent:
        WAITS.append({"met_s": met, "waited_s": round(time.monotonic() - started, 4),
                      "shown_met_s": frame.get("CDH_MET") if frame else None})
    return frame


Run._ground_frame = timed


def answer(turn_id, bundle):
    if bundle["turn_kind"] == "REPORT":
        made = {"timeline": [], "actions": [], "condition": {"summary": "Stand-in's warm-up report.", "evidence": []},
                "deferred": [], "open_issues": []}
        return dict(made, answer="Stand-in's answer.") if bundle["report_kind"] == "CHECK_IN" else made
    return {"kind": "none", "rationale": "Stand-in: nothing to do."}


def utc(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def main():
    containers = cosmos_containers()
    held = HeldOut(HELD_OUT)
    scenario = held.scenario(LABEL)
    root = Path(tempfile.mkdtemp(prefix="odin-ph3-warmup-"))
    began = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        harness = HarnessWorld(root)
        documents = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in scenario.plan_paths]
        plans = harness.world.plans(documents, signer="dev")
        act = harness.world.act(plans, runs=[RUN_ID], signer="dev")
        restore = harness.world.restore_act(run_id=RUN_ID, plan_id=documents[-1]["plan_id"])
        onboard = "stand_in" if any(seat == "ONBOARD" for _, _, seat, _ in scenario.seats) else None
        run = harness.run(run_id=RUN_ID, plans=plans, act=act, root=root, addresses=LOCAL, phase=3,
                          scenario=scenario.huginn, scenario_id=scenario.scenario_id, rate=1.0, check_ins=(),
                          procedures=ProcedureLibrary(), config=CONFIG, docs_folder=docs.CACHE, mode="DEVELOPMENT",
                          seats=scenario.seats, feeds=scenario.all_feeds(), receiver_down=scenario.receiver_down,
                          revocation=scenario.revocation(restore), latch_up=scenario.latch_up, onboard=onboard)
        signing.load_private_key = lambda private_key_path=None: harness.world.odin
        assert run.start(), "the run did not start"
        adapter = StandInAdapter(lambda turn_id, bundle: json.dumps(answer(turn_id, bundle)))
        loop = TurnLoop(harness_url=run.url("harness"), baldur_url=run.url("baldur0"), log_url=run.url("log"),
                        adapter=adapter, onboard_adapter=adapter if onboard else None, repo_root=root)
        threading.Thread(target=lambda: loop.run(max_turns=2000), daemon=True).start()
        deadline = time.monotonic() + LIMIT_S
        while len(WAITS) < FRAMES and time.monotonic() < deadline and run.ended is None:
            time.sleep(0.2)
        run.stop()
        truth = runlog.truth(run.final)
        records = runlog.events(run.final)
        first = WAITS[0]["met_s"] if WAITS else None
        sent = next((r for r in truth if r["type"] == "TRUE_STATE" and r["met_s"] == first), None)
        aos = next((r for r in records if r["type"] == "CONTACT" and r["body"]["state"] == "AOS"), None)
        missed = [r["body"] for r in truth if r["type"] == "GROUND_MISSED"]
        firsts = WAITS[:FIRST]
        passed = (len(WAITS) >= FIRST and all(w["waited_s"] <= WITHIN_S and w["shown_met_s"] == w["met_s"]
                                              for w in firsts) and not missed)
        found = {"run_id": RUN_ID, "label": LABEL, "began_utc": began, "cosmos_containers_started": containers,
                 "frames_timed": len(WAITS), "first_frame_met_s": first,
                 "first_frame_as_r3_was_measured_s": round((utc(aos["utc"]) - utc(sent["utc"])).total_seconds(), 3)
                 if sent and aos else None,
                 "first_frames_waited_s": [w["waited_s"] for w in firsts],
                 "max_waited_s": max((w["waited_s"] for w in WAITS), default=None),
                 "shown_not_its_own": [w for w in WAITS if w["shown_met_s"] != w["met_s"]],
                 "ground_missed": missed, "within_s": WITHIN_S, "passed": passed, "waits": WAITS}
        OUT.mkdir(exist_ok=True)
        (OUT / f"warmup-{began.replace(':', '')}.json").write_text(json.dumps(found, indent=1), encoding="utf-8",
                                                                     newline="\n")
        print(json.dumps({k: v for k, v in found.items() if k != "waits"}, indent=1), flush=True)
        return 0 if passed else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)
        print(f"deleted {root}: {not root.exists()}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
