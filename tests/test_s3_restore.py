"""Revocation and the signed restore act (CONTRACT.md §5.4, §9.4; §16.4 RESTORE).

From the moment of revocation every request is refused, the protective commands too. A restore act,
signed in advance for exactly one run, re-arms ODIN; BALDUR-0 verifies it and accepts it once.
"""

from datetime import timedelta

import pytest

from tests import sshsig
from tests.baldur_world import START, World, failure, utc_text


@pytest.fixture
def world(tmp_path):
    world = World(tmp_path)
    assert world.start()
    return world


def test_a_valid_restore_act_re_arms_odin(world):
    world.gateway.revoke()
    body = world.gateway.restore(world.restore_act())
    assert body["result"] == "ACCEPTED" and body["reason"] is None
    assert world.bodies("RESTORE") == [body]
    assert world.gateway.rung() == ("AI_AUTONOMOUS", None)
    record = world.decide("CMD_MODE_SET", {"target": "LOW_POWER"})
    assert record["decision"] == "ALLOW"
    assert record["arming_act_id"] == "RESTORE-DEV-0001"


def test_a_restore_act_is_accepted_once(world):
    act = world.restore_act()
    world.gateway.revoke()
    assert world.gateway.restore(act)["result"] == "ACCEPTED"
    assert world.gateway.restore(act)["reason"] == "ALREADY_USED"
    world.gateway.revoke()
    assert world.gateway.restore(act)["reason"] == "ALREADY_USED"
    assert failure(world.decide("CMD_SAFE_ENTER", {})) == ("CEILING", "REVOKED")


def test_a_request_voided_by_revocation_never_goes_out_even_after_a_restore(world):
    world.decide("CMD_SAFE_ENTER", {})
    world.gateway.revoke()
    world.gateway.restore(world.restore_act())
    assert world.gateway.dispatch_pending() == [] and world.sent == []


def test_once_restored_the_restore_acts_own_expiry_applies(world):
    world.gateway.revoke()
    world.gateway.restore(world.restore_act(expires_utc=utc_text(START + timedelta(seconds=60))))
    world.advance(60)
    record = world.decide("CMD_SAFE_ENTER", {})
    assert failure(record) == ("ARMING", "ACT_EXPIRED")
    assert record["arming_act_id"] == "RESTORE-DEV-0001"


REFUSALS = [
    ("UNSIGNED", {"signer": None}),
    ("BAD_SIGNATURE", {"namespace": "tyr0"}),
    ("BAD_SIGNATURE", {"signer": "odin"}),
    ("SCHEMA_VIOLATION", {"kind": "ARM"}),
    ("WRONG_RUN", {"run_id": "dev-run-0002"}),
    ("WRONG_PLAN", {"plan_id": "TYR0-DEV-PASS2-v1"}),
    ("EXPIRED", {"expires_utc": utc_text(START)}),
]


@pytest.mark.parametrize("reason, changes", REFUSALS, ids=[f"{r} {c}" for r, c in REFUSALS])
def test_red_a_restore_act_is_refused_and_odin_stays_revoked(world, reason, changes):
    world.gateway.revoke()
    body = world.gateway.restore(world.restore_act(**changes))
    assert (body["result"], body["reason"]) == ("REFUSED", reason)
    assert world.bodies("RESTORE") == [body]
    assert world.gateway.rung() == ("HUMAN_ONLY", "REVOKED")
    assert failure(world.decide("CMD_SAFE_ENTER", {})) == ("CEILING", "REVOKED")


def test_red_a_restore_act_with_nothing_revoked(world):
    body = world.gateway.restore(world.restore_act())
    assert (body["result"], body["reason"]) == ("REFUSED", "NOT_REVOKED")
    world.gateway.revoke()
    assert world.gateway.restore(world.restore_act())["result"] == "ACCEPTED"


def test_red_a_restore_act_once_the_chain_has_ended(world):
    world.gateway.revoke()
    world.advance(10700)
    body = world.gateway.restore(world.restore_act())
    assert body["reason"] == "WRONG_PLAN"
    assert body["detail"] == "RESTORE-DEV-0001 is for plan TYR0-DEV-PASS1-v1, but no plan is in force"


def test_red_a_restore_act_signed_with_a_key_no_mode_accepts(world):
    world.gateway.revoke()
    assert world.gateway.restore(world.restore_act(signer=sshsig.new_key()))["reason"] == "BAD_SIGNATURE"


def test_red_scored_mode_refuses_a_restore_act_signed_with_the_test_key(tmp_path):
    world = World(tmp_path)
    assert world.start(mode="SCORED", signer="director")
    world.gateway.revoke()
    assert world.gateway.restore(world.restore_act(signer="dev"))["reason"] == "BAD_SIGNATURE"
    assert world.gateway.restore(world.restore_act(signer="director"))["result"] == "ACCEPTED"
