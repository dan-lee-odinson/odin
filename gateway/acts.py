"""Verifying the Director's arming and restore acts (CONTRACT.md §5.4, §9.4, §16.2 U18).

An arming act sets ODIN's rung for a batch of runs. BALDUR-0 verifies it before a run starts and
refuses to start a run no valid act covers. A restore act re-arms ODIN after the scripted revocation,
for exactly one run, and BALDUR-0 accepts it once. Both are signed under the namespace aesir-arm.
An act is in force until expires_utc, and expired from that moment on.
"""

from dataclasses import dataclass
from datetime import datetime

from contract.validate import check
from gateway.signed import ACT_NAMESPACE, KEYS_DIR, field, read_signed


def parse_utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


@dataclass(frozen=True)
class Act:
    """An act that arms a run: an arming act, or a restore act once accepted."""
    act_id: str
    kind: str
    rung: str
    runs: tuple
    expires_utc: str
    sha256: str

    def expired_at(self, utc):
        return parse_utc(utc) >= parse_utc(self.expires_utc)


def _read(path, mode, keys_dir, ssh_keygen):
    signed = read_signed(path, namespace=ACT_NAMESPACE, mode=mode, keys_dir=keys_dir, ssh_keygen=ssh_keygen)
    if signed.signature == "MISSING":
        return signed, ("UNSIGNED", f"{signed.path.name} has no {signed.path.name}.sig beside it")
    if signed.signature == "BAD":
        return signed, ("BAD_SIGNATURE", f"{signed.path.name}'s signature does not verify under {ACT_NAMESPACE}")
    return signed, None


def verify_arming_act(path, *, run_id, chain_hashes, utc, mode, keys_dir=KEYS_DIR, ssh_keygen=None):
    """(ARMING_VERIFIED body, Act or None) for the act that is to cover run_id, flying the chain whose
    plan-file hashes are chain_hashes."""
    signed, failure = _read(path, mode, keys_dir, ssh_keygen)
    act = signed.document
    if failure is None:
        problems = signed.problems or check("arming_act", act)
        if problems:
            failure = "SCHEMA_VIOLATION", f"{signed.path.name}: {'; '.join(problems)}"
        elif parse_utc(utc) >= parse_utc(act["expires_utc"]):
            failure = "EXPIRED", f"{act['act_id']} expired at {act['expires_utc']}"
        elif run_id not in act["runs"]:
            failure = "RUN_NOT_COVERED", f"{act['act_id']} does not cover run {run_id}"
        else:
            missing = [sha for sha in chain_hashes if sha not in act["plan_chain_hashes"]]
            if missing:
                failure = "PLAN_NOT_LISTED", f"{act['act_id']} does not list {', '.join(missing)}"
    rung = act.get("rung") if isinstance(act, dict) and act.get("rung") in ("HUMAN_ONLY", "AI_AUTONOMOUS") else None
    body = {"result": "FAIL" if failure else "PASS", "act_id": field(act, "act_id", "identifier"),
            "sha256": signed.sha256, "rung": rung, "reason": failure[0] if failure else None,
            "detail": failure[1] if failure else None}
    if failure:
        return body, None
    return body, Act(act["act_id"], "ARM", act["rung"], tuple(act["runs"]), act["expires_utc"], signed.sha256)


def verify_restore_act(path, *, run_id, plan_id, revoked, used, utc, mode, keys_dir=KEYS_DIR, ssh_keygen=None):
    """(RESTORE body, Act or None) for a restore act presented while plan_id is in force. used holds
    the act_ids of restore acts already accepted in the run."""
    signed, failure = _read(path, mode, keys_dir, ssh_keygen)
    act = signed.document
    if failure is None:
        problems = signed.problems or check("restore_act", act)
        if problems:
            failure = "SCHEMA_VIOLATION", f"{signed.path.name}: {'; '.join(problems)}"
        elif act["run_id"] != run_id:
            failure = "WRONG_RUN", f"{act['act_id']} is for run {act['run_id']}, not {run_id}"
        elif act["plan_id"] != plan_id:
            # The Director's ruling on U33 (27 October 2026): a restore act presented while another plan
            # is in force, or after the chain has ended, is refused as WRONG_PLAN.
            in_force = f"{plan_id} is in force" if plan_id else "no plan is in force"
            failure = "WRONG_PLAN", f"{act['act_id']} is for plan {act['plan_id']}, but {in_force}"
        elif parse_utc(utc) >= parse_utc(act["expires_utc"]):
            failure = "EXPIRED", f"{act['act_id']} expired at {act['expires_utc']}"
        elif act["act_id"] in used:
            failure = "ALREADY_USED", f"{act['act_id']} was accepted before in this run"
        elif not revoked:
            failure = "NOT_REVOKED", "ODIN's authority is not revoked, so there is nothing to restore"
    body = {"act_id": field(act, "act_id", "identifier"), "sha256": signed.sha256,
            "result": "REFUSED" if failure else "ACCEPTED", "reason": failure[0] if failure else None,
            "detail": failure[1] if failure else None}
    if failure:
        return body, None
    return body, Act(act["act_id"], "RESTORE", act["rung"], (act["run_id"],), act["expires_utc"], signed.sha256)
