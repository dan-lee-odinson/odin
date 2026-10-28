"""One run, from RUN_START to RUN_END (CONTRACT.md §6, §8, §9.4, §10, §12).

The harness writes RUN_START and has BALDUR-0 verify the plan chain and the arming act; a run either
fails stops before it starts. The run's contact windows come from its verified plan chain (the
Director's ruling of 27 October 2026). The simulator then steps on the run's clock. After each tick
the harness gives BALDUR-0 the frame the seat received, so outcomes are read from telemetry, and turns
what happened into triggers. ODIN takes its turns at GET /turn/next, one in flight at a time, and the
event log, BALDUR-0 and the harness each serve their endpoints on 127.0.0.1.

In CHARGED pacing, phase 3's onboard seat out of contact, the simulator pauses at the tick that raises
a turn, and when the turn ends it advances by the turn's measured wall-clock time before BALDUR-0's
dispatch recheck (§10.1; the Director's ruling on U37).

Where a run starts and ends, and where its folder is (the Director's ruling on U46, 27 October 2026):
the run starts at its chain's first valid_from and ends at its last valid_until. The simulator rolls
on silently and at once from the start to the first acquisition of signal, so no frame and no turn
comes before it. Once the clock reaches the end, the turns already waiting are still served, then GET
/turn/next answers run_complete and RUN_END is written. While it runs, the run's folder is
runs/<run_id>/, where ODIN keeps its inputs too (§16.1 U16); when it stops, the harness moves the
folder to runs/scored/<run_id>/ or runs/dev/<run_id>/. .gitignore ignores everything under runs/ but
runs/scored/, so a run cut off before its move is never committed.
"""

import json
import threading
import time
from pathlib import Path

from contract.validate import check
from gateway import server as baldur_server
from gateway.gateway import Gateway
from gateway.signed import KEYS_DIR, load_yaml
from harness import docs
from harness.checkins import PHASES, pass_check_ins
from harness.bundle import build_bundle, bundle_bytes, read_records
from harness.server import Refused, make_server
from harness.telemetry import FrameStore
from harness.triggers import TriggerQueue, trigger
from harness.watch import Watcher
from log import server as log_server
from log.canonical import canonical_json, sha256_tag
from log.chain import utc_now
from log.event_log import EventLog, TruthLog, compress_truth
from wrapper.clock import RunClock
from wrapper.link import in_window
from wrapper.simulator import Simulator

RUN_COMPLETE = json.dumps({"run_complete": True}).encode("utf-8")
RUN_START_CONFIG = ("seed", "model_config", "provider", "model_id", "reasoning_effort", "answer_method",
                    "prompt_template_sha256", "reference_sha256")


def recorded(check_ins):
    """The recorded check-ins a run plays, as (met_s, POST /checkin body), in MET order. Each is a
    transcript made once through Muse Code's voice path and frozen with its audio's hash, then delivered
    at its MET in every run (the Director's ruling on U44, 27 October 2026, where CONTRACT.md §13 has each
    recording played through the voice path in every run). The live demo uses the voice path live."""
    for met_s, body in check_ins:
        problems = check("checkin", body) + ([] if body.get("source") == "RECORDED" else ["source is not RECORDED"])
        if problems:
            raise ValueError(f"the recorded check-in at MET {met_s} is not one: {problems}")
    return sorted(check_ins, key=lambda item: item[0])


class Run:
    def __init__(self, *, run_id, scenario, scenario_id, phase, mode, plan_paths, act_path, root, procedures,
                 config, seat="ONBOARD", pacing="CHARGED", rate=1.0, check_ins=(), pass_transcript=None,
                 revoke_at=None, restore=None, docs_folder=docs.CACHE, keys_dir=KEYS_DIR, addresses=None,
                 utc_clock=utc_now):
        """config: the run's frozen configuration as RUN_START records it (RUN_START_CONFIG). check_ins:
        recorded check-ins to play, as (met_s, POST /checkin body); a phase-2 or phase-3 run also carries
        one at each contact's loss of signal minus 90 s (harness/checkins.py). pass_transcript: that
        check-in's frozen transcript {text, audio_sha256}, or None for the words as text until it exists.
        revoke_at: the scripted revocation's
        MET, in the one revoke scenario. restore: (met_s, restore act path). addresses: {harness,
        baldur0, log} to serve on, each (host, port); config/ports.yaml's by default."""
        if seat != "ONBOARD":
            raise NotImplementedError("the ground seat reads COSMOS through the connector, stage S5")
        self.run_id, self.scenario, self.scenario_id, self.phase, self.mode = run_id, scenario, scenario_id, phase, mode
        self.plan_paths, self.act_path, self.procedures, self.config = list(plan_paths), act_path, procedures, config
        self.seat, self.pacing, self.rate = seat, pacing, rate
        self.check_ins = recorded(check_ins)
        self.pass_transcript = pass_transcript
        self.revoke_at, self.restore = revoke_at, restore
        self.docs_folder, self.keys_dir, self.addresses = docs_folder, keys_dir, addresses or {}
        self._utc = utc_clock
        self.folder = Path(root) / "runs" / run_id
        self.final = Path(root) / "runs" / ("scored" if mode == "SCORED" else "dev") / run_id
        self.start_met_s = self.end_met_s = None
        self.queue = TriggerQueue()
        self.store = FrameStore("ONBOARD")
        self.simulator = None
        self.clock = None
        self.turn_id = 0
        self.ended = None   # RUN_END's reason once written
        self._lock = threading.RLock()
        self._servers = []
        self._served_at = None
        self._charged = False
        self._windows = []

    # -- clocks and seat -------------------------------------------------------------------------

    def met_s(self):
        return self.simulator.met_s if self.simulator is not None else (self.start_met_s or 0)

    def contact(self):
        return "IN_CONTACT" if in_window(self.met_s(), self._windows) else "OUT_OF_CONTACT"

    def _send(self, command, parameters, route):
        """BALDUR-0's route. The onboard seat's is the wrapper's uplink (§9.3)."""
        if route != "UPLINK":
            raise NotImplementedError("the COSMOS route is the connector's, stage S5")
        self.simulator.uplink(command, parameters)

    # -- start -----------------------------------------------------------------------------------

    def _run_start(self):
        chain_hashes = [sha256_tag(Path(p).read_bytes()) for p in self.plan_paths]
        return {"run_id": self.run_id, "scenario_id": self.scenario_id, "phase": self.phase, "mode": self.mode,
                **{name: self.config[name] for name in RUN_START_CONFIG},
                "config_sha256": sha256_tag(canonical_json(self.config)),
                "plan_chain_sha256": sha256_tag(canonical_json(chain_hashes)) if chain_hashes else None}

    def _claimed_start(self):
        """The chain's first valid_from as its files give it, for the records written before BALDUR-0 has
        verified the chain: 0 if a file cannot be read."""
        starts = []
        for path in self.plan_paths:
            document, problems = load_yaml(Path(path).read_bytes())
            if problems or not isinstance(document, dict) or not isinstance(document.get("valid_from_met_s"), int):
                return 0
            starts.append(document["valid_from_met_s"])
        return min(starts, default=0)

    def start(self):
        """Start the run. False if it stopped before starting, with RUN_END written."""
        for folder in (self.folder, self.final):
            if folder.exists():
                raise FileExistsError(f"{folder} already exists; a run's folder is never reused")
        self.start_met_s = self._claimed_start()
        self.events = EventLog.create(self.folder / "events.jsonl", met_clock=self.met_s, utc_clock=self._utc)
        self.events.append("RUN_START", self._run_start())
        self.gateway = Gateway(self.events, met_clock=self.met_s, telemetry=self.store.telemetry, sender=self._send,
                               utc_clock=self._utc, seat=lambda: self.seat, contact=self.contact, keys_dir=self.keys_dir)
        if not self.gateway.start_run(run_id=self.run_id, scenario_id=self.scenario_id, mode=self.mode,
                                      plan_paths=self.plan_paths, act_path=self.act_path):
            armed = [r for r in read_records(self.events.path) if r["type"] == "ARMING_VERIFIED"]
            self.stop("NOT_ARMED" if armed else "PLAN_CHAIN_FAILED")
            return False
        if self.procedures.missing(self.gateway.chain):
            self.stop("ERROR")
            return False
        plans = self.gateway.chain.plans
        self.start_met_s = min(p.valid_from_met_s for p in plans)
        self.end_met_s = max(p.valid_until_met_s for p in plans)
        self._windows = sorted((p.document["contact_window"]["aos_met_s"], p.document["contact_window"]["los_met_s"])
                               for p in plans)
        first_aos = min((aos for aos, los in self._windows if los > self.start_met_s), default=self.start_met_s)
        self.truth = TruthLog.create(self.folder / "truth.jsonl", met_clock=self.met_s, utc_clock=self._utc)
        self.simulator = Simulator(self.scenario, windows=self._windows, truth=self.truth,
                                   start_at=max(self.start_met_s, first_aos))
        if self.phase in PHASES:
            self.check_ins = sorted(self.check_ins + pass_check_ins(self._windows, self.pass_transcript),
                                    key=lambda item: item[0])
        self.watcher = Watcher(self._windows)
        self.clock = RunClock(self.simulator, until_met_s=self.end_met_s, pacing=self.pacing, rate=self.rate,
                              on_tick=self._on_tick)
        self._serve(log_server.make_server(self.events, self.addresses.get("log")))
        self._serve(baldur_server.make_server(self.gateway, self.addresses.get("baldur0"),
                                              after_request=self._after_request))
        self._serve(make_server(self, self.addresses.get("harness")))
        self.clock.start()
        return True

    def _serve(self, server):
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self._servers.append(server)

    def url(self, which):
        """The URL a service is listening on: harness, baldur0 or log."""
        host, port = self._servers[("log", "baldur0", "harness").index(which)].server_address[:2]
        return f"http://{host}:{port}"

    # -- each tick ---------------------------------------------------------------------------------

    def _on_tick(self, frame):
        with self._lock:
            met = self.simulator.met_s
            received = self.simulator.tap.latest() if frame is not None else None
            if received is not None:
                self.store.receive(received, self._utc(), met)
            self.gateway.update_clock()
            telemetry = {"frame_met_s": received["CDH_MET"], "points": dict(received)} if received else None
            outcomes = [trigger("OUTCOME", met, request_id=o["request_id"]) for o in self.gateway.observe(telemetry)
                        if o["outcome"] != "NO_ACKNOWLEDGEMENT"]
            plan = self.gateway.chain.plan_at(met)
            found = self.watcher.tick(met, plan_id=plan.plan_id if plan else None, frame=received,
                                      staleness=self.store.staleness(met))
            for contact in (t for t in found if t["type"] in ("AOS", "LOS")):
                self.events.append("CONTACT", {"state": contact["type"]})
            found += outcomes
            check_ins = []
            while self.check_ins and self.check_ins[0][0] <= met:
                _, body = self.check_ins.pop(0)
                if body["utc"] is None:   # a pass check-in is stamped when it is delivered
                    body = dict(body, utc=self._utc())
                self.events.append("CHECK_IN", body)
                check_ins.append((trigger("CHECK_IN", met), body["text"]))
            revoked = None
            if self.revoke_at is not None and met >= self.revoke_at:
                self.revoke_at = None
                self.events.append("REVOKE", {"source": "SCRIPT"})
                self.gateway.revoke()
                revoked = trigger("REVOKE", met)
                found.append(revoked)
            if self.restore is not None and met >= self.restore[0]:
                _, act_path = self.restore
                self.restore = None
                self.gateway.restore(act_path)
                found.append(trigger("RESTORE", met))
            with self.queue.together():   # one tick's triggers arrive together (§6.1, U47)
                if not found and not check_ins and self.queue.periodic_due(met):
                    found.append(trigger("PERIODIC", met))
                if found:
                    self.queue.add(*found)
                for one, text in check_ins:
                    self.queue.add(one, check_in_text=text)
                # Revocation makes ODIN take both turns the contract names (the Director's ruling on U40,
                # 27 October 2026): REVOKE, which §6.1 counts among the action triggers, joins the next
                # action turn, and the HAND_BACK report turn of §9.4 and §13 follows it.
                if revoked is not None:
                    self.queue.add_report("HAND_BACK", revoked)
                if self.pacing == "CHARGED" and self.queue.waiting():
                    self.clock.pause()

    # -- ODIN's turns ------------------------------------------------------------------------------

    # GET /turn/next holds the request until a turn is due or the run is complete (the Director's ruling
    # on U39, 27 October 2026). A quiet stretch in real time lasts up to 60 s before PERIODIC, so Muse
    # Code's loop waits 120 s, and on a wait that times out it asks again.
    def next_turn(self):
        """GET /turn/next: ODIN asking for its next turn ends the one in flight."""
        self._end_turn()
        with self.queue.changed:
            while True:
                turn = self.queue.take()
                if turn is not None:
                    break
                if self.clock is None or self.clock.finished:
                    return self._complete()
                if self.pacing == "CHARGED":
                    self.clock.resume()   # nothing is due: quiet time runs as fast as the simulator steps
                self.queue.changed.wait(timeout=0.2)
        with self._lock:
            self.turn_id += 1
            met = self.met_s()
            bundle = build_bundle(run_id=self.run_id, turn_id=self.turn_id, turn=turn, met_s=met, utc=self._utc(),
                                  contact_state=self.contact(), seat=self.seat, gateway=self.gateway,
                                  store=self.store, procedures=self.procedures, records=read_records(self.events.path))
            data = bundle_bytes(bundle)
            self.events.append("TRIGGER", {"turn_id": self.turn_id, "turn_kind": turn.turn_kind,
                                           "report_kind": turn.report_kind, "triggers": turn.triggers,
                                           "bundle_sha256": sha256_tag(data)})
            self._served_at, self._charged = time.monotonic(), False
            return data

    def _charge_for_turn(self):
        """In CHARGED pacing, the turn's time from the bundle served (the Director's ruling on U37)."""
        if self.pacing == "CHARGED" and not self._charged and self._served_at is not None:
            self._charged = True
            self.clock.charge(time.monotonic() - self._served_at)

    def _end_turn(self):
        with self._lock:
            if self.queue.in_flight is None:
                return
            if not self.clock.finished:
                self._charge_for_turn()
                self.gateway.dispatch_pending()
            self.queue.finish()

    def _after_request(self, record):
        """BALDUR-0 has decided and replied: the decision is a trigger (§6.1). An allowed command is
        dispatched now in real time, and in CHARGED pacing once the simulator has advanced by the
        turn's time to BALDUR-0's receipt of the request (§9.3, §10.1)."""
        with self._lock:
            self.queue.add(trigger("DECISION", self.met_s(), request_id=record["request_id"],
                                   decision=record["decision"]))
            if self.queue.in_flight is not None and not self.clock.finished:
                self._charge_for_turn()
            self.gateway.dispatch_pending()

    # -- the tools and the check-in ------------------------------------------------------------------

    def _tool_use(self, tool, arguments, reply):
        if self.turn_id == 0:
            raise Refused(400, ["no turn has been served yet; the tools are for use within a turn"])
        self.events.append("TOOL_USE", {"run_id": self.run_id, "turn_id": self.turn_id, "tool": tool,
                                        "arguments": arguments, "result_sha256": sha256_tag(canonical_json(reply))})
        return reply

    def docs_lookup(self, q):
        with self._lock:
            return self._tool_use("docs_lookup", {"q": q}, docs.lookup(q, self.docs_folder))

    def history(self, points, window_s):
        with self._lock:
            return self._tool_use("history", {"points": points, "window_s": window_s},
                                  self.store.history(points, self.met_s(), window_s))

    # POST /checkin replies {record_id}, the CHECK_IN record's ID (the Director's ruling on U44, 27 October
    # 2026). Recorded check-ins are played at their METs from frozen transcripts: see recorded().
    def check_in(self, body):
        with self._lock:
            logged = self.events.append("CHECK_IN", body)
            with self.queue.changed:
                self.queue.add(trigger("CHECK_IN", self.met_s()), check_in_text=body["text"])
                if self.pacing == "CHARGED" and self.clock is not None and self.queue.in_flight is None:
                    self.clock.pause()
            return {"record_id": logged["record_id"]}

    # -- the end ---------------------------------------------------------------------------------------

    def _complete(self):
        self._end("COMPLETE")
        return RUN_COMPLETE

    def _end(self, reason):
        with self._lock:
            if self.ended is None:
                self.ended = reason
                self.events.append("RUN_END", {"reason": reason, "turns": self.turn_id})

    def stop(self, reason="ABORTED"):
        """Stop the clock and the servers. RUN_END is written with reason unless the run has ended. A
        scored run's truth file is then compressed for its commit (the Director's ruling on U36), and the
        run's folder moved to runs/scored/ or runs/dev/ (U46). Call it once ODIN has stopped, since ODIN
        keeps its inputs in the folder."""
        if self.clock is not None:
            self.clock.stop()
        for server in self._servers:
            server.shutdown()
            server.server_close()
        self._servers = []
        self._end(reason)
        if self.mode == "SCORED" and self.simulator is not None and (self.folder / "truth.jsonl").exists():
            compress_truth(self.folder / "truth.jsonl")
        if self.folder != self.final and self.folder.exists():
            self.final.parent.mkdir(parents=True, exist_ok=True)
            self.folder.rename(self.final)
            self.folder = self.final
