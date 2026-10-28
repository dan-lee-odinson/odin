"""BALDUR-0, the gateway (CONTRACT.md §9). It holds the only route to the spacecraft.

One Gateway serves one run. Before the run starts it verifies the plan chain and the arming act
(§5.3, §5.4). For each command request it logs the request, decides (§9.1) and logs the decision.
Immediately before an allowed command goes out it decides again on the newest telemetry and the
current met_s, and sends the command only if the result and its basis are unchanged; otherwise it
logs DECISION_VOIDED and sends nothing (§9.3). It then reads each dispatched command's outcome from
telemetry and logs OUTCOME (§9.3). Revocation is applied at once and voids every request still waiting
to go out; a restore act re-arms the run once (§9.4).

The harness and the wrapper give the Gateway what it cannot know itself: the simulation clock, the
newest frame, the seat, the contact state, and the route that sends a command. The harness logs
REVOKE and calls revoke(); BALDUR-0 writes its own records (the Director's ruling on U21).
"""

import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_ssh_public_key

from contract.validate import check
from gateway import decision
from gateway.acts import verify_arming_act, verify_restore_act
from gateway.plans import Chain, verify_chain
from gateway.signed import KEYS_DIR
from log.chain import utc_now


class RequestRefused(Exception):
    """A body that is not a well-formed request or escalation. Nothing is logged."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = list(problems)


@dataclass
class _Pending:
    record_id: int     # the DECISION record that allowed it
    request: dict
    basis: dict


@dataclass
class _Awaiting:
    request: dict
    met_s: float       # when it was dispatched
    acc_before: int | None
    rej_before: int | None


# The point each command changes, from its effect in HUGINN's dictionary (defs/tlm_cmd.yaml).
AFFECTED = {"CMD_PLD_SET_STATE": "PLD_STATE", "CMD_PLD_SET_RATE": "PLD_RATE", "CMD_SAFE_ENTER": "EPS_MODE",
            "CMD_MODE_SET": "EPS_MODE", "CMD_SYS_RESET": None}
NO_ACKNOWLEDGEMENT_S = 10


class Gateway:
    def __init__(self, event_log, *, met_clock, telemetry, sender, utc_clock=utc_now,
                 seat=lambda: "GROUND", contact=lambda: "IN_CONTACT", keys_dir=KEYS_DIR, ssh_keygen=None):
        """telemetry() gives the newest frame as {frame_met_s, points} or None; sender(command,
        parameters, route) sends an allowed command; seat() is GROUND or ONBOARD and contact() is
        IN_CONTACT or OUT_OF_CONTACT."""
        self._log = event_log
        self._met_clock = met_clock
        self._utc_clock = utc_clock
        self._telemetry = telemetry
        self._sender = sender
        self._seat = seat
        self._contact = contact
        self._keys_dir = Path(keys_dir)
        self._ssh_keygen = ssh_keygen
        self._odin_key = load_ssh_public_key((self._keys_dir / "odin.pub").read_bytes())
        self._lock = threading.RLock()
        self.run_id = None
        self.mode = None
        self._chain = Chain(())
        self._arming = None
        self._revoked = False
        self._restores_used = set()
        self._nonces = set()
        self._lease_uses = {}
        self._pending = []
        self._awaiting = []
        self._plan_logged = None

    # -- before the run ------------------------------------------------------------------------

    def start_run(self, *, run_id, scenario_id, mode, plan_paths, act_path):
        """Verify the chain, then the act. True if the run may start. Each verification is logged; a
        failure stops the run before it starts, and ODIN stays HUMAN_ONLY."""
        with self._lock:
            if self.run_id is not None:
                raise RuntimeError(f"this gateway already serves run {self.run_id}")
            self.run_id, self.mode = run_id, mode
            verified, chain = verify_chain(plan_paths, scenario_id=scenario_id, mode=mode,
                                           keys_dir=self._keys_dir, ssh_keygen=self._ssh_keygen)
            self._log.append("PLAN_CHAIN_VERIFIED", verified)
            if chain is None:
                return False
            armed, act = verify_arming_act(act_path, run_id=run_id, chain_hashes=chain.hashes,
                                           utc=self._utc_clock(), mode=mode, keys_dir=self._keys_dir,
                                           ssh_keygen=self._ssh_keygen)
            self._log.append("ARMING_VERIFIED", armed)
            if act is None:
                return False
            self._chain, self._arming = chain, act
            self._log_plan_change()
            return True

    # -- what the harness reads ----------------------------------------------------------------

    @property
    def chain(self):
        """The verified plan chain, fixed for the run; empty until start_run has verified one."""
        return self._chain

    def update_clock(self):
        """Log PLAN_IN_FORCE if the simulation clock has selected another plan, or left the chain.
        The harness calls this as time advances; every decision calls it first."""
        with self._lock:
            self._log_plan_change()

    def rung(self):
        """(rung, rung_reason) for the turn bundle (§6.2, §16.1 U2)."""
        with self._lock:
            return decision.rung(self._context(nonce_reused=False))

    def uses_left(self):
        """For each lease of the plan in force with max_uses, the uses remaining (§16.1 U4)."""
        with self._lock:
            plan = self._chain.plan_at(self._met_clock())
            if plan is None:
                return {}
            return {lease["lease_id"]: lease["max_uses"] - self._lease_uses.get((plan.plan_id, lease["lease_id"]), 0)
                    for lease in plan.document["leases"] if lease["max_uses"] is not None}

    # -- POST /request ---------------------------------------------------------------------------

    def receive_request(self, request):
        """Log the request, decide, log the decision and return it (§8.2, §9.1)."""
        # The Director's ruling on U30 (27 October 2026): a body that is not a well-formed
        # COMMAND_REQUEST is refused with its problems and nothing is logged, as the log's endpoints
        # do (U24).
        problems = check("command_request", request)
        if problems:
            raise RequestRefused(problems)
        with self._lock:
            self._log_plan_change()
            self._log.append("REQUEST", request)
            ctx = self._context(nonce_reused=request["nonce"] in self._nonces)
            # A nonce is spent by any request that carries ODIN's signature, even one refused before
            # ORIGIN runs, so no request can be replayed.
            if decision.signature_verifies(request, self._odin_key):
                self._nonces.add(request["nonce"])
            record, basis = decision.decide(request, ctx)
            logged = self._log.append("DECISION", record)
            if record["decision"] == "ALLOW":
                self._pending.append(_Pending(logged["record_id"], request, basis))
            return record

    # -- dispatch ------------------------------------------------------------------------------

    def pending(self):
        """The request_ids allowed and not yet dispatched or voided, oldest first."""
        with self._lock:
            return [p.request["request_id"] for p in self._pending]

    def dispatch_pending(self):
        """Recheck each allowed request on the newest telemetry and the current met_s, oldest first,
        and send it only if the decision and its basis are unchanged (§9.3). Returns the records
        written, DISPATCH or DECISION_VOIDED, as (type, body)."""
        with self._lock:
            self._log_plan_change()
            written = []
            while self._pending:
                # A request leaves the queue only once it is dispatched or voided, so a route that
                # fails to send leaves it, and those behind it, waiting.
                # A request a plan boundary has passed fails PLAN as PLAN_MISMATCH (U29), no other lease
                # can cover it (U27), and a restore follows a revocation, which voids every waiting
                # request, so of the basis only the class can change while every check passes.
                item = self._pending[0]
                record, basis = decision.decide(item.request, self._context(nonce_reused=False))
                changed = [(key, check) for key, check in decision.BASIS if basis[key] != item.basis[key]]
                if record["decision"] == "REFUSE":
                    failed = decision.failed_check(record)
                    written.append(self._void(item, failed["check"], failed["reason"], failed["detail"]))
                elif changed:
                    key, check = changed[0]
                    written.append(self._void(item, check, "BASIS_CHANGED",
                                              f"{key} was {item.basis[key]} when allowed and is {basis[key]} now"))
                else:
                    written.append(self._dispatch(item, basis))
                self._pending.pop(0)
            return written

    def _dispatch(self, item, basis):
        request = item.request
        route = "COSMOS" if self._seat() == "GROUND" else "UPLINK"
        frame = self._telemetry()
        self._sender(request["command"], request["parameters"], route)
        self._awaiting.append(_Awaiting(request, self._met_clock(),
                                        frame["points"]["CDH_CMD_ACC_CNT"] if frame else None,
                                        frame["points"]["CDH_CMD_REJ_CNT"] if frame else None))
        if basis["lease_id"] is not None:   # a use is counted when the command is dispatched (§9.3)
            key = (basis["plan_id"], basis["lease_id"])
            self._lease_uses[key] = self._lease_uses.get(key, 0) + 1
        body = {"request_id": request["request_id"], "command": request["command"],
                "parameters": request["parameters"], "route": route, "lease_id": basis["lease_id"],
                "met_s": self._met_clock(), "utc": self._utc_clock()}
        self._log.append("DISPATCH", body)
        return "DISPATCH", body

    def _void(self, item, check_name, reason, detail):
        body = {"request_id": item.request["request_id"], "decision_record_id": item.record_id,
                "check": check_name, "reason": reason, "detail": detail,
                "met_s": self._met_clock(), "utc": self._utc_clock()}
        self._log.append("DECISION_VOIDED", body)
        return "DECISION_VOIDED", body

    # -- outcome (§9.3) --------------------------------------------------------------------------

    def observe(self, frame=None):
        """Read each dispatched command's outcome from telemetry, never assuming it (§9.3, §16.4 U17):
        the counters' change by the next frame, with the affected point, and a reset's acknowledgement
        the post-reset counter epoch (accepted 1, rejected 0). The harness calls this every tick, with
        the frame the seat received since the last, as {frame_met_s, points}, or None. A command whose
        counters have not moved 10 s of simulation time after dispatch is NO_ACKNOWLEDGEMENT. Returns
        the OUTCOME bodies written."""
        with self._lock:
            written = []
            if frame is not None:
                written += self._resolve(frame)
            now = self._met_clock()
            while self._awaiting and now - self._awaiting[0].met_s >= NO_ACKNOWLEDGEMENT_S:
                item = self._awaiting.pop(0)
                written.append(self._outcome(item, "NO_ACKNOWLEDGEMENT", None))
            return written

    # Two choices the contract leaves (the Director's ruling on U41, 27 October 2026): a reset's outcome
    # names no affected point, since its effect is the counter epoch itself; and when more than one
    # dispatched command waits, the counters' moves are given to them in the order they were dispatched,
    # the oldest first, the order in which HUGINN applies them.
    def _resolve(self, frame):
        written = []
        points = frame["points"]
        acc, rej = points["CDH_CMD_ACC_CNT"], points["CDH_CMD_REJ_CNT"]
        base_acc = base_rej = None
        while self._awaiting:
            item = self._awaiting[0]
            if frame["frame_met_s"] <= item.met_s:
                break   # a frame from before the dispatch cannot show its outcome
            if base_acc is None:
                base_acc, base_rej = item.acc_before, item.rej_before
            if item.request["command"] == "CMD_SYS_RESET":
                if (acc, rej) != (1, 0):
                    break
                outcome = "ACCEPTED"
            elif base_acc is not None and acc > base_acc:
                outcome, base_acc = "ACCEPTED", base_acc + 1
            elif base_rej is not None and rej > base_rej:
                outcome, base_rej = "REJECTED", base_rej + 1
            else:
                break
            self._awaiting.pop(0)
            written.append(self._outcome(item, outcome, frame))
        return written

    def _outcome(self, item, outcome, frame):
        points = frame["points"] if frame else None
        affected = AFFECTED.get(item.request["command"])
        body = {"request_id": item.request["request_id"], "outcome": outcome,
                "acc_before": item.acc_before, "acc_after": points["CDH_CMD_ACC_CNT"] if points else None,
                "rej_before": item.rej_before, "rej_after": points["CDH_CMD_REJ_CNT"] if points else None,
                "rej_reason": points["CDH_REJ_REASON"] if points else None,
                "point": {"mnemonic": affected, "value": points[affected]} if points and affected else None,
                "frame_met_s": frame["frame_met_s"] if frame else None,
                "met_s": self._met_clock(), "utc": self._utc_clock()}
        self._log.append("OUTCOME", body)
        return body

    # -- revocation and restore (§9.4) ---------------------------------------------------------

    def revoke(self):
        """Revoke ODIN's authority at once. Every request waiting to go out is voided now."""
        with self._lock:
            self._revoked = True
            pending, self._pending = self._pending, []
            return [self._void(item, "CEILING", "REVOKED", "ODIN's authority was revoked before dispatch")
                    for item in pending]

    def restore(self, act_path):
        """Present a restore act. Logs RESTORE, accepted or refused, and returns its body."""
        with self._lock:
            self._log_plan_change()
            plan = self._chain.plan_at(self._met_clock())
            body, act = verify_restore_act(act_path, run_id=self.run_id, plan_id=plan.plan_id if plan else None,
                                           revoked=self._revoked, used=self._restores_used, utc=self._utc_clock(),
                                           mode=self.mode, keys_dir=self._keys_dir, ssh_keygen=self._ssh_keygen)
            self._log.append("RESTORE", body)
            if act is not None:
                # The Director's ruling on U26 (27 October 2026): from now on the restore act arms the
                # run: its expiry applies, and decisions name it as arming_act_id.
                self._restores_used.add(act.act_id)
                self._arming, self._revoked = act, False
            return body

    # -- POST /escalation ----------------------------------------------------------------------

    def receive_escalation(self, escalation):
        """Log an escalation and say whether it is delivered now or queued until the next
        acquisition of signal (§7.1, §16.5). It carries no authority and is not a request."""
        problems = check("escalation", escalation)
        if problems:
            raise RequestRefused(problems)
        with self._lock:
            logged = self._log.append("ESCALATION", escalation)
            return {"record_id": logged["record_id"],
                    "delivery": "NOW" if self._contact() == "IN_CONTACT" else "QUEUED_UNTIL_AOS"}

    # -- the moment ----------------------------------------------------------------------------

    def _context(self, *, nonce_reused):
        met_s = self._met_clock()
        return decision.Context(run_id=self.run_id, met_s=met_s, utc=self._utc_clock(),
                                plan=self._chain.plan_at(met_s), arming=self._arming, revoked=self._revoked,
                                frame=self._telemetry(), odin_key=self._odin_key, nonce_reused=nonce_reused,
                                lease_uses=dict(self._lease_uses))

    def _log_plan_change(self):
        if self.run_id is None or not self._chain.plans:
            return
        plan = self._chain.plan_at(self._met_clock())
        plan_id = plan.plan_id if plan else None
        if plan_id == self._plan_logged:
            return
        self._plan_logged = plan_id
        self._log.append("PLAN_IN_FORCE", {
            "plan_id": plan_id, "sha256": plan.sha256 if plan else None,
            "valid_from_met_s": plan.valid_from_met_s if plan else None,
            "valid_until_met_s": plan.valid_until_met_s if plan else None})
