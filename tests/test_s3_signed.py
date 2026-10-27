"""Before a run starts: the plan chain and the arming act (CONTRACT.md §5.1, §5.3, §5.4, §5.5, §11.4).

Every plan is verified with ssh-keygen -Y verify under the namespace tyr0, and the act under
aesir-arm. Scored runs accept only the Director's key; development runs accept the test key. A chain
or act that fails is logged and the run does not start.
"""

import base64
import hashlib

import pytest

from gateway.plans import verify_chain
from gateway.signed import KEYS_DIR, signers
from tests import sshsig
from tests.baldur_world import RUN, SCENARIO, START, World, changed, dump, example_plan, utc_text

DEV_TEST_FINGERPRINT = "SHA256:ddr1rVBujtsTaWLHdR+qldFr5dViQF7/1Jc9NoGPHR4"


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def chain_record(world):
    [body] = world.bodies("PLAN_CHAIN_VERIFIED")
    return body


def did_not_start(world):
    assert world.bodies("PLAN_IN_FORCE") == []
    assert world.gateway.rung() == ("HUMAN_ONLY", "NO_PLAN")
    assert world.decide("CMD_SAFE_ENTER", {})["checks"][0]["reason"] == "NO_PLAN_IN_FORCE"


# -- a run that starts -------------------------------------------------------------------------

def test_a_signed_chain_and_act_start_the_run(world):
    assert world.start()
    chain = chain_record(world)
    assert (chain["result"], chain["reason"]) == ("PASS", None)
    assert [(p["plan_id"], p["valid_from_met_s"], p["valid_until_met_s"], p["signature"]) for p in chain["plans"]] == [
        ("TYR0-DEV-PASS1-v1", 0, 5400, "GOOD"), ("TYR0-DEV-PASS2-v1", 5400, 10800, "GOOD")]
    [armed] = world.bodies("ARMING_VERIFIED")
    assert (armed["result"], armed["act_id"], armed["rung"], armed["reason"]) == ("PASS", "ARM-DEV-01",
                                                                                  "AI_AUTONOMOUS", None)
    [in_force] = world.bodies("PLAN_IN_FORCE")
    assert in_force == {"plan_id": "TYR0-DEV-PASS1-v1", "sha256": chain["plans"][0]["sha256"],
                        "valid_from_met_s": 0, "valid_until_met_s": 5400}
    assert [r["type"] for r in world.records()] == ["PLAN_CHAIN_VERIFIED", "ARMING_VERIFIED", "PLAN_IN_FORCE"]
    assert world.gateway.rung() == ("AI_AUTONOMOUS", None)


def test_the_clock_selects_the_plan_in_force_and_each_change_is_logged_once(world):
    assert world.start()
    world.advance(5300)
    world.gateway.update_clock()
    world.gateway.update_clock()
    world.advance(5400)
    world.gateway.update_clock()
    assert [b["plan_id"] for b in world.bodies("PLAN_IN_FORCE")] == ["TYR0-DEV-PASS1-v1", "TYR0-DEV-PASS2-v1", None]
    assert world.bodies("PLAN_IN_FORCE")[-1] == {"plan_id": None, "sha256": None, "valid_from_met_s": None,
                                                 "valid_until_met_s": None}
    assert world.gateway.rung() == ("HUMAN_ONLY", "NO_PLAN")


def test_a_gateway_serves_one_run(world):
    assert world.start()
    with pytest.raises(RuntimeError):
        world.start()


def test_a_chain_holds_at_least_one_plan(world):
    with pytest.raises(ValueError):
        verify_chain([], scenario_id=SCENARIO, mode="DEVELOPMENT", keys_dir=world.keys_dir)


# -- whose keys each mode accepts (§5.3, §11.4) -------------------------------------------------

def test_scored_mode_accepts_the_directors_key(world):
    assert world.start(mode="SCORED", signer="director")


def test_red_scored_mode_refuses_plans_signed_with_the_test_key(world):
    assert not world.start(mode="SCORED")
    chain = chain_record(world)
    assert (chain["result"], chain["reason"]) == ("FAIL", "BAD_SIGNATURE")
    assert [p["signature"] for p in chain["plans"]] == ["BAD", "BAD"]
    assert world.bodies("ARMING_VERIFIED") == []
    did_not_start(world)


def test_red_scored_mode_refuses_an_act_signed_with_the_test_key(world):
    plans = world.plans(signer="director")
    assert not world.start(mode="SCORED", plans=plans, act=world.act(plans, signer="dev"))
    [armed] = world.bodies("ARMING_VERIFIED")
    assert (armed["result"], armed["reason"]) == ("FAIL", "BAD_SIGNATURE")
    did_not_start(world)


def test_development_mode_accepts_the_test_key(world):
    assert world.start(mode="DEVELOPMENT", signer="dev")


def test_development_mode_also_accepts_the_directors_key(world):
    assert world.start(mode="DEVELOPMENT", signer="director")


@pytest.mark.parametrize("mode", ["DEVELOPMENT", "SCORED"])
def test_red_neither_mode_accepts_any_other_key(world, mode):
    assert not world.start(mode=mode, signer=sshsig.new_key())
    assert chain_record(world)["reason"] == "BAD_SIGNATURE"


def test_the_repositorys_keys_each_mode_accepts():
    assert [principal for principal, _ in signers("SCORED")] == ["dan"]
    assert [principal for principal, _ in signers("DEVELOPMENT")] == ["dan", "dev-test"]
    keytype, key = (KEYS_DIR / "dev-test.pub").read_text(encoding="utf-8").split()[:2]
    assert keytype == "ssh-ed25519"
    fingerprint = base64.b64encode(hashlib.sha256(base64.b64decode(key)).digest()).decode("ascii").rstrip("=")
    assert f"SHA256:{fingerprint}" == DEV_TEST_FINGERPRINT


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        signers("PRACTICE")


# -- a chain that stops the run (§5.1, §5.3, §5.5; §16.4 PLAN_CHAIN_VERIFIED) -------------------

def _unsigned_second(world):
    paths = world.plans()
    paths[1].with_name(paths[1].name + ".sig").unlink()
    return paths


def _altered_first(world):
    paths = world.plans()
    paths[0].write_bytes(paths[0].read_bytes() + b"# one line added after signing\n")
    return paths


def _first(world, data, **write):
    return [world.write("plan1.yaml", data, namespace=write.get("namespace", "tyr0"),
                        signer=write.get("signer", "dev")),
            world.write("plan2.yaml", dump(example_plan(2)), namespace="tyr0")]


def _plans(first=None, second=None):
    return lambda world: world.plans([first or example_plan(1), second or example_plan(2)])


P1, P2 = example_plan(1), example_plan(2)
RATE_BACKWARDS = {**P2["leases"][0], "arguments": {"rate": {"min": 2.0, "max": 0.5}}}
SYS_RESET_LEASE = {**P1["leases"][0], "lease_id": "L9", "command": "CMD_SYS_RESET", "arguments": {}}
# U27: leases that could cover one request, and leases that only come close.
LOW_POWER_LEASE = {"lease_id": "L3", "command": "CMD_MODE_SET", "arguments": {"target": ["LOW_POWER"]},
                   "conditions": [], "max_uses": 1}
STATE_LEASE = {"lease_id": "L4", "command": "CMD_PLD_SET_STATE", "arguments": {"state": ["ON", "OFF"]},
               "conditions": [], "max_uses": None}
NOMINAL_ONLY = {**P1["leases"][0], "arguments": {"target": ["NOMINAL"]}}


def rate_lease(lease_id, low, high):
    return {**P2["leases"][0], "lease_id": lease_id, "arguments": {"rate": {"min": low, "max": high}}}


OVERLAPPING = [
    ("two mode leases both allowing LOW_POWER", _plans(changed(P1, leases=P1["leases"] + [LOW_POWER_LEASE])),
     "plan1.yaml: leases 'L1' and 'L3' both cover CMD_MODE_SET with target LOW_POWER"),
    ("two payload-state leases both allowing OFF", _plans(changed(P1, leases=P1["leases"] + [STATE_LEASE])),
     "plan1.yaml: leases 'L2' and 'L4' both cover CMD_PLD_SET_STATE with state OFF"),
    ("two rate leases whose ranges meet at 2.0",
     _plans(second=changed(P2, leases=[rate_lease("L1", 0.5, 2.0), rate_lease("L2", 2.0, 4.0)])),
     "plan2.yaml: leases 'L1' and 'L2' both cover CMD_PLD_SET_RATE with rate 2.0 to 2.0"),
]

CHAINS = [
    ("UNSIGNED", "the second plan's signature removed", _unsigned_second),
    ("BAD_SIGNATURE", "a line added to the first plan after signing", _altered_first),
    ("BAD_SIGNATURE", "the first plan signed under aesir-arm, an act's namespace",
     lambda w: _first(w, dump(P1), namespace="aesir-arm")),
    ("SCHEMA_VIOLATION", "the first plan not YAML", lambda w: _first(w, b"plan_id: [unclosed\n")),
    ("SCHEMA_VIOLATION", "a key written twice", lambda w: _first(w, dump(P1) + b"plan_version: 2\n")),
    ("SCHEMA_VIOLATION", "objectives missing",
     _plans({k: v for k, v in P1.items() if k != "objectives"})),
    ("SCHEMA_VIOLATION", "a field the contract does not list", _plans(changed(P1, safe_enter_delay_s=60))),
    ("SCHEMA_VIOLATION", "a span that ends where it starts",
     _plans(changed(P1, valid_from_met_s=5400))),
    ("SCHEMA_VIOLATION", "a lease_id used twice in one plan",
     _plans(changed(P1, leases=[P1["leases"][0], {**P1["leases"][1], "lease_id": "L1"}]))),
    ("SCHEMA_VIOLATION", "a rate range from 2.0 down to 0.5", _plans(second=changed(P2, leases=[RATE_BACKWARDS]))),
    ("SCHEMA_VIOLATION", "two plans with one plan_id", _plans(second=changed(P2, plan_id=P1["plan_id"]))),
    ("SCHEMA_VIOLATION", "the second plan numbered pass 3", _plans(second=changed(P2, pass_index=3))),
    ("PROTECTIVE_RESTRICTED", "CMD_SAFE_ENTER prohibited",
     _plans(changed(P1, prohibited=["CMD_PLD_SET_RATE", "CMD_SAFE_ENTER"]))),
    ("PROTECTIVE_RESTRICTED", "a lease for CMD_SYS_RESET",
     _plans(changed(P1, leases=P1["leases"] + [SYS_RESET_LEASE]))),
    ("WRONG_SCENARIO", "both plans for DEV-S02",
     _plans(changed(P1, scenario_id="DEV-S02"), changed(P2, scenario_id="DEV-S02"))),
    ("GAP", "the second plan starting at 5500", _plans(second=changed(P2, valid_from_met_s=5500))),
    ("OVERLAP", "the second plan starting at 5300", _plans(second=changed(P2, valid_from_met_s=5300))),
] + [("SCHEMA_VIOLATION", title, build) for title, build, _ in OVERLAPPING]


@pytest.mark.parametrize("reason, title, build", CHAINS, ids=[f"{r} - {t}" for r, t, _ in CHAINS])
def test_red_a_chain_that_fails_stops_the_run(world, reason, title, build):
    plans = build(world)
    assert not world.start(plans=plans)
    chain = chain_record(world)
    assert (chain["result"], chain["reason"]) == ("FAIL", reason)
    assert chain["detail"]
    assert world.bodies("ARMING_VERIFIED") == []
    did_not_start(world)


@pytest.mark.parametrize("title, build, detail", OVERLAPPING, ids=[t for t, _, _ in OVERLAPPING])
def test_red_overlapping_leases_are_named_in_the_refusal(world, title, build, detail):
    world.start(plans=build(world))
    assert chain_record(world)["detail"] == detail


@pytest.mark.parametrize("title, build", [
    ("a mode lease for NOMINAL and another for LOW_POWER",
     _plans(changed(P1, leases=[NOMINAL_ONLY, P1["leases"][1], LOW_POWER_LEASE]))),
    ("rate leases from 0.5 to 2.0 and from 2.1 to 4.0",
     _plans(second=changed(P2, leases=[rate_lease("L1", 0.5, 2.0), rate_lease("L2", 2.1, 4.0)]))),
])
def test_leases_for_one_command_that_never_cover_the_same_request_pass(world, title, build):
    assert world.start(plans=build(world))


def test_a_chain_record_shows_every_plans_signature(world):
    world.start(plans=_unsigned_second(world))
    assert [p["signature"] for p in chain_record(world)["plans"]] == ["GOOD", "MISSING"]


def test_a_plan_that_did_not_parse_is_listed_with_nulls(world):
    world.start(plans=_first(world, b"plan_id: [unclosed\n"))
    assert chain_record(world)["plans"][0]["plan_id"] is None


def test_the_first_plan_that_fails_names_the_reason(world):
    plans = world.plans([changed(P1, scenario_id="DEV-S02"), P2])
    plans[1].with_name("plan2.yaml.sig").unlink()
    world.start(plans=plans)
    assert chain_record(world)["reason"] == "WRONG_SCENARIO"


# -- an act that stops the run (§5.4; §16.4 ARMING_VERIFIED) ------------------------------------

ACTS = [
    ("UNSIGNED", "no signature", {"signer": None}),
    ("BAD_SIGNATURE", "signed under tyr0, a plan's namespace", {"namespace": "tyr0"}),
    ("SCHEMA_VIOLATION", "rung HUMAN_ONLY, which no act grants", {"rung": "HUMAN_ONLY"}),
    ("SCHEMA_VIOLATION", "kind RESTORE", {"kind": "RESTORE"}),
    ("EXPIRED", "expired the moment the run starts", {"expires_utc": utc_text(START)}),
    ("RUN_NOT_COVERED", "for dev-run-0002 only", {"runs": ["dev-run-0002"]}),
]


@pytest.mark.parametrize("reason, title, changes", ACTS, ids=[f"{r} - {t}" for r, t, _ in ACTS])
def test_red_an_act_that_fails_stops_the_run(world, reason, title, changes):
    plans = world.plans()
    assert not world.start(plans=plans, act=world.act(plans, **changes))
    [armed] = world.bodies("ARMING_VERIFIED")
    assert (armed["result"], armed["reason"]) == ("FAIL", reason)
    assert armed["detail"]
    did_not_start(world)


def test_red_an_act_that_does_not_list_every_plan_of_the_chain(world):
    plans = world.plans()
    assert not world.start(plans=plans, act=world.act(plans[:1]))
    [armed] = world.bodies("ARMING_VERIFIED")
    assert armed["reason"] == "PLAN_NOT_LISTED"
    did_not_start(world)


def test_red_a_signed_plan_presented_as_the_act(world):
    plans = world.plans()
    assert not world.start(plans=plans, act=plans[0])
    assert world.bodies("ARMING_VERIFIED")[0]["reason"] == "BAD_SIGNATURE"


def test_an_act_covers_a_batch_of_runs(world):
    plans = world.plans()
    assert world.start(plans=plans, act=world.act(plans, runs=["dev-run-0000", RUN, "dev-run-0002"]))
