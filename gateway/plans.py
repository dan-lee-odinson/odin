"""Verifying a run's TYR-0 plan chain before it starts (CONTRACT.md §5.1, §5.3, §5.5).

Every plan in the chain must be signed, unaltered, well formed, free of any restriction on the
protective commands, and for the run's scenario, and the spans of the chain must meet end to start.
A chain that fails stops the run before it starts. A chain that passes is fixed for the run, and the
simulation clock selects which plan is in force: a plan is in force from valid_from_met_s up to, not
including, valid_until_met_s, which is the only reading under which spans that meet end to start
neither overlap nor leave a gap.
"""

from dataclasses import dataclass

from contract.validate import check
from gateway.rules import PROTECTIVE
from gateway.signed import KEYS_DIR, PLAN_NAMESPACE, field, read_signed


@dataclass(frozen=True)
class Plan:
    plan_id: str
    sha256: str
    valid_from_met_s: int
    valid_until_met_s: int
    document: dict

    def in_force_at(self, met_s):
        return self.valid_from_met_s <= met_s < self.valid_until_met_s

    def lease(self, lease_id):
        return next(lease for lease in self.document["leases"] if lease["lease_id"] == lease_id)


@dataclass(frozen=True)
class Chain:
    plans: tuple

    def plan_at(self, met_s):
        return next((plan for plan in self.plans if plan.in_force_at(met_s)), None)

    @property
    def hashes(self):
        return [plan.sha256 for plan in self.plans]


def _protective_restrictions(document):
    """§5.5: a plan may not prohibit or lease CMD_SAFE_ENTER or CMD_SYS_RESET. Any other field that
    could condition or limit them is a field §5.1 does not list, which the schema refuses."""
    if not isinstance(document, dict):
        return []
    found = []
    prohibited = document.get("prohibited")
    if isinstance(prohibited, list):
        found += [f"prohibited names {command}" for command in prohibited if command in PROTECTIVE]
    leases = document.get("leases")
    if isinstance(leases, list):
        found += [f"lease {lease.get('lease_id')!r} names {lease.get('command')}" for lease in leases
                  if isinstance(lease, dict) and lease.get("command") in PROTECTIVE]
    return found


def _shared(one, other):
    """What two leases of a plan both allow, described, or None when they could never cover the same
    request: another command, or an argument with no value (state, target) or rate (a range) in common."""
    if one["command"] != other["command"] or set(one["arguments"]) != set(other["arguments"]):
        return None
    shared = []
    for name in sorted(one["arguments"]):
        mine, theirs = one["arguments"][name], other["arguments"][name]
        if isinstance(mine, dict) and isinstance(theirs, dict):
            low, high = max(mine["min"], theirs["min"]), min(mine["max"], theirs["max"])
            if low > high:
                return None
            shared.append(f"{name} {low} to {high}")
        elif isinstance(mine, list) and isinstance(theirs, list):
            common = [value for value in mine if value in theirs]
            if not common:
                return None
            shared.append(f"{name} {', '.join(map(str, common))}")
        else:
            return None
    return "; ".join(shared)


def _consistency(plan):
    """What the schema cannot express about one well-formed plan."""
    # The Director's ruling on U32 (27 October 2026): these checks, each refused as SCHEMA_VIOLATION.
    # lease_id's uniqueness is the contract's (§5.2). A span that ends where it starts is never in
    # force, and an empty rate range covers nothing. Two leases that could cover one request are
    # refused (the ruling on U27), so the LEASE check always has a single lease to apply.
    problems = []
    if plan["valid_from_met_s"] >= plan["valid_until_met_s"]:
        problems.append(f"valid_from_met_s {plan['valid_from_met_s']} is not before "
                        f"valid_until_met_s {plan['valid_until_met_s']}")
    lease_ids = [lease["lease_id"] for lease in plan["leases"]]
    problems += [f"lease_id {lease_id!r} appears {lease_ids.count(lease_id)} times"
                 for lease_id in sorted(set(lease_ids)) if lease_ids.count(lease_id) > 1]
    for lease in plan["leases"]:
        rate = lease["arguments"].get("rate")
        if rate is not None and rate["min"] > rate["max"]:
            problems.append(f"lease {lease['lease_id']!r} allows rates from {rate['min']} to {rate['max']}, "
                            "which is no rate")
    leases = plan["leases"]
    for index, one in enumerate(leases):
        for other in leases[index + 1:]:
            shared = _shared(one, other)
            if shared is not None:
                problems.append(f"leases {one['lease_id']!r} and {other['lease_id']!r} both cover "
                                f"{one['command']} with {shared}")
    return problems


def _plan_failure(signed, scenario_id):
    """(reason, detail) for the first way one plan fails, or None."""
    if signed.signature == "MISSING":
        return "UNSIGNED", f"{signed.path.name} has no {signed.path.name}.sig beside it"
    if signed.signature == "BAD":
        return "BAD_SIGNATURE", f"{signed.path.name}'s signature does not verify under {PLAN_NAMESPACE}"
    if signed.document is None:
        return "SCHEMA_VIOLATION", f"{signed.path.name}: {signed.problems[0]}"
    restrictions = _protective_restrictions(signed.document)
    if restrictions:
        return "PROTECTIVE_RESTRICTED", f"{signed.path.name}: {'; '.join(restrictions)}"
    problems = check("tyr0_plan", signed.document) or _consistency(signed.document)
    if problems:
        return "SCHEMA_VIOLATION", f"{signed.path.name}: {'; '.join(problems)}"
    if signed.document["scenario_id"] != scenario_id:
        return "WRONG_SCENARIO", (f"{signed.path.name} is for scenario {signed.document['scenario_id']!r}, "
                                  f"not {scenario_id!r}")
    return None


def _chain_failure(plans):
    """(reason, detail) for the first way plans that each pass fail as a chain, or None."""
    # The Director's ruling on U32 (27 October 2026): plan_ids unique in the chain (§5.1 calls plan_id
    # unique) and pass_index counting 1, 2, … in chain order (§5.1 "which pass of the run"), each
    # refused as SCHEMA_VIOLATION.
    plan_ids = [plan["plan_id"] for plan in plans]
    for plan_id in plan_ids:
        if plan_ids.count(plan_id) > 1:
            return "SCHEMA_VIOLATION", f"plan_id {plan_id!r} appears {plan_ids.count(plan_id)} times in the chain"
    for position, plan in enumerate(plans, 1):
        if plan["pass_index"] != position:
            return "SCHEMA_VIOLATION", f"{plan['plan_id']} is pass {plan['pass_index']} but plan {position} of the chain"
    for before, after in zip(plans, plans[1:]):
        if after["valid_from_met_s"] > before["valid_until_met_s"]:
            return "GAP", (f"{before['plan_id']} ends at {before['valid_until_met_s']} and "
                           f"{after['plan_id']} starts at {after['valid_from_met_s']}")
        if after["valid_from_met_s"] < before["valid_until_met_s"]:
            return "OVERLAP", (f"{before['plan_id']} ends at {before['valid_until_met_s']} and "
                               f"{after['plan_id']} starts at {after['valid_from_met_s']}")
    return None


def verify_chain(paths, *, scenario_id, mode, keys_dir=KEYS_DIR, ssh_keygen=None):
    """(PLAN_CHAIN_VERIFIED body, Chain or None). Every plan's signature is checked so the record
    shows each; the reason is the first failure in chain order."""
    if not paths:
        raise ValueError("a run's plan chain holds at least one plan")
    signed = [read_signed(path, namespace=PLAN_NAMESPACE, mode=mode, keys_dir=keys_dir, ssh_keygen=ssh_keygen)
              for path in paths]
    entries = [{"plan_id": field(s.document, "plan_id", "identifier"), "sha256": s.sha256,
                "valid_from_met_s": field(s.document, "valid_from_met_s", "met_s"),
                "valid_until_met_s": field(s.document, "valid_until_met_s", "met_s"),
                "signature": s.signature} for s in signed]
    failure = next(filter(None, (_plan_failure(s, scenario_id) for s in signed)), None)
    if failure is None:
        failure = _chain_failure([s.document for s in signed])
    if failure is not None:
        reason, detail = failure
        return {"result": "FAIL", "plans": entries, "reason": reason, "detail": detail}, None
    chain = Chain(tuple(Plan(s.document["plan_id"], s.sha256, s.document["valid_from_met_s"],
                             s.document["valid_until_met_s"], s.document) for s in signed))
    return {"result": "PASS", "plans": entries, "reason": None, "detail": None}, chain
