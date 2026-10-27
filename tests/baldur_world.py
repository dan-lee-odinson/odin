"""A scratch world for BALDUR-0's tests: keys, signed plans and acts, a clock, telemetry, a route
that records what it is given, and a Gateway writing a run's event log.

Every key is made in memory and never written. The Director's key is a stand-in, listed as principal
dan in a scratch allowed_signers, because his private key never leaves his machine. The plans and
acts start from the schema examples, which form one chain of two plans for scenario DEV-S01:
TYR0-DEV-PASS1-v1 in force from 0 up to 5400, and TYR0-DEV-PASS2-v1 from 5400 up to 10800.
"""

import base64
import copy
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import yaml

from contract.validate import SCHEMA_DIR
from gateway.gateway import Gateway
from log.canonical import canonical_json
from log.event_log import EventLog
from tests import sshsig

EXAMPLES = SCHEMA_DIR / "examples"
RUN = "dev-run-0001"
SCENARIO = "DEV-S01"
START = datetime(2026, 10, 27, 12, 0, 0, tzinfo=timezone.utc)

NOMINAL_POINTS = {
    "EPS_BATT_V": 8.1, "EPS_BATT_I": 0.4, "EPS_BATT_SOC": 80.0, "EPS_SA1_I": 0.6, "EPS_SA2_I": 0.6,
    "EPS_BUS_V": 8.0, "EPS_LOAD_I": 0.5, "EPS_MODE": "NOMINAL", "ADM_ECLIPSE": "SUNLIT", "PLD_STATE": "ON",
    "PLD_RATE": 1.0, "CDH_MET": 0, "CDH_FRAME_CNT": 0, "CDH_CMD_ACC_CNT": 0, "CDH_CMD_REJ_CNT": 0,
    "CDH_REJ_REASON": "NONE",
}


def utc_text(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def example_plan(n):
    name = "good-plan.yaml" if n == 1 else "good-plan-pass2.yaml"
    return yaml.safe_load((EXAMPLES / "tyr0_plan" / name).read_text(encoding="utf-8"))


def dump(document):
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")


def plan_at(met_s):
    """The example chain's plan in force at met_s, as ODIN's loop names it in a request, or None."""
    if met_s < 5400:
        return "TYR0-DEV-PASS1-v1"
    return "TYR0-DEV-PASS2-v1" if met_s < 10800 else None


class World:
    def __init__(self, tmp_path, *, met_s=100.0):
        self.tmp = tmp_path
        self.director, self.dev, self.odin = sshsig.new_key(), sshsig.new_key(), sshsig.new_key()
        self.keys_dir = tmp_path / "keys"
        self.keys_dir.mkdir()
        director_line = sshsig.public_line(self.director, "stand-in for the Director's TYR-0 key")
        (self.keys_dir / "allowed_signers").write_text(f"dan {director_line}\n", encoding="utf-8")
        (self.keys_dir / "dev-test.pub").write_text(sshsig.public_line(self.dev, "dev test") + "\n", encoding="utf-8")
        (self.keys_dir / "odin.pub").write_text(sshsig.public_line(self.odin, "odin") + "\n", encoding="utf-8")
        self.docs = tmp_path / "signed"
        self.docs.mkdir()
        self.met = met_s
        self.now = START
        self.points = dict(NOMINAL_POINTS)
        self.frame_age = 0.0
        self.no_frame = False
        self.sent = []
        self.route_down = False
        self.seat = "GROUND"
        self.contact = "IN_CONTACT"
        self.log = EventLog.create(tmp_path / "runs" / RUN / "events.jsonl",
                                   met_clock=lambda: self.met, utc_clock=self.utc)
        self.gateway = Gateway(self.log, met_clock=lambda: self.met, utc_clock=self.utc,
                               telemetry=self.frame, sender=self.send,
                               seat=lambda: self.seat, contact=lambda: self.contact, keys_dir=self.keys_dir)

    # -- clock and telemetry -------------------------------------------------------------------

    def utc(self):
        return utc_text(self.now)

    def advance(self, seconds):
        """Simulation and wall clock move on together; the newest frame keeps its age."""
        self.met += seconds
        self.now += timedelta(seconds=seconds)

    def frame(self):
        if self.no_frame:
            return None
        frame_met = self.met - self.frame_age
        return {"frame_met_s": frame_met, "points": {**self.points, "CDH_MET": int(frame_met)}}

    def send(self, command, parameters, route):
        """The route: records what it is given, or fails while route_down is set."""
        if self.route_down:
            raise ConnectionError(f"the {route} route is not answering")
        self.sent.append((command, parameters, route))

    # -- signed documents ----------------------------------------------------------------------

    def key(self, signer):
        return {"dev": self.dev, "director": self.director, "odin": self.odin}.get(signer, signer)

    def write(self, name, data, *, namespace, signer="dev"):
        """Write a document's bytes, and its signature beside it unless signer is None."""
        path = self.docs / name
        path.write_bytes(data)
        if signer is not None:
            (self.docs / (name + ".sig")).write_bytes(sshsig.sign(self.key(signer), data, namespace))
        return path

    def plans(self, documents=None, *, signer="dev"):
        documents = documents if documents is not None else [example_plan(1), example_plan(2)]
        return [self.write(f"plan{n}.yaml", d if isinstance(d, bytes) else dump(d), namespace="tyr0", signer=signer)
                for n, d in enumerate(documents, 1)]

    def act(self, plan_paths, *, signer="dev", namespace="aesir-arm", **changes):
        from log.canonical import sha256_tag
        document = {"act_id": "ARM-DEV-01", "kind": "ARM", "rung": "AI_AUTONOMOUS", "runs": [RUN, "dev-run-0002"],
                    "plan_chain_hashes": [sha256_tag(p.read_bytes()) for p in plan_paths],
                    "expires_utc": "2026-11-04T23:59:59.000Z", **changes}
        return self.write("arm.yaml", dump(document), namespace=namespace, signer=signer)

    def restore_act(self, name="restore.yaml", *, signer="dev", namespace="aesir-arm", **changes):
        document = {"act_id": "RESTORE-DEV-0001", "kind": "RESTORE", "rung": "AI_AUTONOMOUS", "run_id": RUN,
                    "plan_id": "TYR0-DEV-PASS1-v1", "expires_utc": "2026-11-04T23:59:59.000Z", **changes}
        return self.write(name, dump(document), namespace=namespace, signer=signer)

    def start(self, *, plans=None, act=None, mode="DEVELOPMENT", signer="dev"):
        plans = plans if plans is not None else self.plans(signer=signer)
        act = act if act is not None else self.act(plans, signer=signer)
        return self.gateway.start_run(run_id=RUN, scenario_id=SCENARIO, mode=mode, plan_paths=plans, act_path=act)

    # -- ODIN's requests -----------------------------------------------------------------------

    def request(self, command, parameters=None, *, signer="odin", **changes):
        """A request signed as ODIN's loop signs one (§7.3), naming the plan in force now, with any
        field changed before signing."""
        request = {"request_id": str(uuid.uuid4()), "origin": "ODIN", "utc": self.utc(), "met_s": self.met,
                   "nonce": secrets.token_hex(16), "run_id": RUN, "turn_id": 1, "plan_id": plan_at(self.met),
                   "agent_input_hash": "sha256:" + "ab" * 32, "command": command,
                   "parameters": parameters if parameters is not None else {}, **changes}
        signature = self.key(signer).sign(canonical_json(request))
        return {**request, "signature": base64.b64encode(signature).decode("ascii")}

    def decide(self, command, parameters=None, **changes):
        return self.gateway.receive_request(self.request(command, parameters, **changes))

    # -- the log -------------------------------------------------------------------------------

    def records(self, type_=None):
        records = [json.loads(line) for line in self.log.path.read_bytes().splitlines()]
        return [r for r in records if type_ is None or r["type"] == type_]

    def bodies(self, type_):
        return [r["body"] for r in self.records(type_)]


def failure(record):
    """(check, reason) where a decision record stopped, or None for ALLOW."""
    failed = [c for c in record["checks"] if c["result"] == "FAIL"]
    return (failed[0]["check"], failed[0]["reason"]) if failed else None


def changed(document, **changes):
    document = copy.deepcopy(document)
    document.update(changes)
    return document
