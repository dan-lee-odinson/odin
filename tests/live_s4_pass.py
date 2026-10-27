"""S4's end-to-end check against ODIN's COSMOS running live (00_HANDOFF.md §4, S4). Not collected by pytest.

    python -m connector.cosmos up
    python -m connector.cosmos plugin
    python tests/live_s4_pass.py

P1_nominal flies its PASS-1 contact, MET [0, 410), in real time through the link on 8713. The check
reads COSMOS's own view through its JSON API: frames arriving, a command sent from COSMOS taking effect
in the next frame, the ground receiver dropping frames from MET 300 to 330 while HUGINN_INT stays
CONNECTED, and nothing after LOS with the interface still CONNECTED. The scenario's scripted commands at
180 and 240 fall inside the contact and are dropped (U35), so the only command is the check's own.
Exits 0 only if every step holds. The credentials come from the ODIN_COSMOS_* variables and are never
shown.
"""

import itertools
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connector.cosmos import EXTERNAL_URL, credentials  # noqa: E402
from log.event_log import TruthLog, verify_truth  # noqa: E402
from wrapper.clock import RunClock  # noqa: E402
from wrapper.huginn import load_scenario  # noqa: E402
from wrapper.link import Link  # noqa: E402
from wrapper.simulator import Simulator  # noqa: E402

CONTACT = (0, 410)
UNTIL = 430
COMMAND_AT = 60
RECEIVER_DOWN = (300, 330)
_ids = itertools.count(1)


class Cosmos:
    """COSMOS's JSON-RPC API on ODIN's port, authorized by the service password."""

    def __init__(self):
        self._password = credentials()["OPENC3_SERVICE_PASSWORD"]

    def call(self, method, *params):
        body = json.dumps({"jsonrpc": "2.0", "method": method, "params": list(params), "id": next(_ids),
                           "keyword_params": {"scope": "DEFAULT"}}).encode("utf-8")
        request = urllib.request.Request(f"{EXTERNAL_URL}/openc3-api/api", data=body, headers={
            "Content-Type": "application/json-rpc", "Authorization": self._password})
        with urllib.request.urlopen(request, timeout=10) as reply:
            answer = json.loads(reply.read())
        if "error" in answer:
            raise RuntimeError(f"{method}: {answer['error'].get('message')}")
        return answer["result"]

    def tlm(self, item):
        return self.call("tlm", f"HUGINN HK {item}")

    def interface_state(self):
        return self.call("get_interface", "HUGINN_INT")["state"]


def main():
    cosmos = Cosmos()
    results = []

    def check(what, ok, seen):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {what}: {seen}", flush=True)

    def wait_for(met_s):
        while simulator.met_s < met_s and not clock.finished:
            time.sleep(0.1)

    folder = Path(tempfile.mkdtemp(prefix="odin-s4-live-"))
    run = {}
    truth = TruthLog.create(folder / "truth.jsonl", met_clock=lambda: run["simulator"].met_s)
    link = Link([CONTACT]).start()
    simulator = run["simulator"] = Simulator(load_scenario("P1_nominal"), windows=[CONTACT], link=link, truth=truth)

    def on_tick(frame):
        upcoming = int(simulator.spacecraft.t_s)
        link.receiver_up = not RECEIVER_DOWN[0] <= upcoming < RECEIVER_DOWN[1]

    print(f"link on {link.address[0]}:{link.address[1]}; waiting for COSMOS's HUGINN_INT to dial it", flush=True)
    deadline = time.monotonic() + 90
    while link.clients < 1 and time.monotonic() < deadline:
        time.sleep(0.5)
    check("HUGINN_INT dialed the link before AOS", link.clients >= 1, f"{link.clients} connection(s)")
    if not link.clients:
        link.stop()
        return 1
    clock = RunClock(simulator, until_met_s=UNTIL, on_tick=on_tick)
    clock.start()
    try:
        wait_for(20)
        time.sleep(1.5)
        seen = cosmos.tlm("CDH_MET")
        check("frames reach COSMOS in contact", simulator.met_s - 3 <= seen <= simulator.met_s,
              f"COSMOS CDH_MET {seen} at simulator MET {simulator.met_s}")

        wait_for(COMMAND_AT)
        sent_at = simulator.met_s
        cosmos.call("cmd", "HUGINN CMD_PLD_SET_STATE with STATE ON")
        wait_for(sent_at + 3)
        time.sleep(1.5)
        check("the command from COSMOS reached the spacecraft by the next tick",
              [(name, accepted) for _, name, accepted, _ in simulator.applied] == [("CMD_PLD_SET_STATE", True)]
              and simulator.applied[0][0] <= sent_at + 2, f"applied {simulator.applied}, sent at MET {sent_at}")
        state, accepted = cosmos.tlm("PLD_STATE"), cosmos.tlm("CDH_CMD_ACC_CNT")
        check("COSMOS sees it in the next frame", (state, accepted) == ("ON", 1),
              f"PLD_STATE {state}, CDH_CMD_ACC_CNT {accepted}")

        wait_for(320)
        state, seen = cosmos.interface_state(), cosmos.tlm("CDH_MET")
        check("the receiver drops frames while HUGINN_INT stays CONNECTED",
              state == "CONNECTED" and seen == RECEIVER_DOWN[0] - 1 and link.counts["RECEIVER_DOWN"] >= 19,
              f"interface {state}, COSMOS CDH_MET {seen}, dropped {link.counts['RECEIVER_DOWN']}")

        wait_for(340)
        time.sleep(1.5)
        seen = cosmos.tlm("CDH_MET")
        check("frames resume when the receiver is back", seen >= RECEIVER_DOWN[1], f"COSMOS CDH_MET {seen}")

        wait_for(425)
        state, seen = cosmos.interface_state(), cosmos.tlm("CDH_MET")
        check("nothing after LOS, and HUGINN_INT still CONNECTED", state == "CONNECTED" and seen == CONTACT[1] - 1,
              f"interface {state}, COSMOS CDH_MET {seen}")
        clock.join()
    finally:
        clock.stop()
        link.stop()
    dropped = [c["mnemonic"] for c in simulator.dropped]
    check("P1's scripted commands inside the contact were dropped and recorded",
          dropped == ["CMD_PLD_SET_STATE", "CMD_PLD_SET_RATE"] and verify_truth(truth.path) == [],
          f"dropped {dropped}; truth file {truth.path}")
    print(f"link: {link.counts}, commands lost out of contact {link.commands_lost}")
    print("every step held" if all(results) else f"{results.count(False)} step(s) failed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
