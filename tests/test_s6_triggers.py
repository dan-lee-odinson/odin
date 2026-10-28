"""When ODIN takes a turn (CONTRACT.md §6.1): one turn in flight at a time, action triggers merged, each
report trigger its own report turn in order, and the action turn first when both wait, a report waiting
only behind the action triggers that arrived before it or with it (the Director's ruling on U47)."""

import pytest

from harness.triggers import TriggerQueue, trigger


def limit(met_s, point="EPS_LOAD_I", old="GREEN", new="YELLOW_HIGH"):
    return trigger("LIMIT_CHANGE", met_s, point=point, **{"from": old, "to": new})


def turns(queue):
    taken = []
    while (turn := queue.take()) is not None:
        taken.append((turn.turn_kind, turn.report_kind, [t["type"] for t in turn.triggers], turn.check_in_text))
        queue.finish()
    return taken


def test_action_triggers_waiting_together_are_one_turn_oldest_first():
    queue = TriggerQueue()
    queue.add(trigger("AOS", 800))
    queue.add(limit(900), trigger("MODE_CHANGE", 899, **{"from": "NOMINAL", "to": "LOW_POWER"}))
    assert turns(queue) == [("ACT", None, ["AOS", "MODE_CHANGE", "LIMIT_CHANGE"], None)]


def test_one_turn_in_flight_and_what_arrives_meanwhile_is_one_follow_up():
    queue = TriggerQueue()
    queue.add(trigger("AOS", 800))
    first = queue.take()
    queue.add(trigger("DECISION", 803, request_id="3f2b8c1e-9a4d-4f6b-8e2a-7c5d1b0e9f34", decision="ALLOW"))
    queue.add(trigger("OUTCOME", 804, request_id="3f2b8c1e-9a4d-4f6b-8e2a-7c5d1b0e9f34"))
    assert first.turn_kind == "ACT" and queue.take() is None   # still in flight
    queue.finish()
    assert turns(queue) == [("ACT", None, ["DECISION", "OUTCOME"], None)]


def test_each_report_trigger_gets_its_own_report_turn_in_order():
    queue = TriggerQueue()
    queue.add(trigger("CHECK_IN", 850), check_in_text="How is the battery?")
    queue.add(trigger("PLAN_START", 851, plan_id="TYR0-P3-PASS1-v1"))
    queue.add(trigger("CHECK_IN", 852), check_in_text="And the payload?")
    assert turns(queue) == [("REPORT", "CHECK_IN", ["CHECK_IN"], "How is the battery?"),
                            ("REPORT", "PASS_START", ["PLAN_START"], None),
                            ("REPORT", "CHECK_IN", ["CHECK_IN"], "And the payload?")]


def test_a_check_in_landing_on_an_alarm_runs_the_action_turn_first_and_the_report_next():
    queue = TriggerQueue()
    queue.add(trigger("CHECK_IN", 900), limit(900), check_in_text="What changed?")
    assert turns(queue) == [("ACT", None, ["LIMIT_CHANGE"], None),
                            ("REPORT", "CHECK_IN", ["CHECK_IN"], "What changed?")]


def test_a_report_waits_only_behind_action_triggers_that_arrived_before_or_with_it():
    queue = TriggerQueue()
    queue.add(trigger("CHECK_IN", 900), limit(900), check_in_text="What changed?")
    alarm = queue.take()
    queue.add(trigger("DECISION", 900, request_id="3f2b8c1e-9a4d-4f6b-8e2a-7c5d1b0e9f34", decision="ALLOW"))
    queue.finish()
    assert alarm.turn_kind == "ACT" and turns(queue) == [("REPORT", "CHECK_IN", ["CHECK_IN"], "What changed?"),
                                                         ("ACT", None, ["DECISION"], None)]


def test_an_action_trigger_that_arrived_before_the_report_runs_first_with_all_that_wait():
    queue = TriggerQueue()
    queue.add(limit(899))
    queue.add(trigger("CHECK_IN", 900), check_in_text="Status?")
    queue.add(trigger("OUTCOME", 901, request_id="3f2b8c1e-9a4d-4f6b-8e2a-7c5d1b0e9f34"))
    assert turns(queue) == [("ACT", None, ["LIMIT_CHANGE", "OUTCOME"], None),
                            ("REPORT", "CHECK_IN", ["CHECK_IN"], "Status?")]


def test_red_an_action_trigger_arriving_after_a_waiting_report_goes_behind_it():
    queue = TriggerQueue()
    queue.add(trigger("CHECK_IN", 900), check_in_text="Status?")
    queue.add(limit(900))
    assert turns(queue) == [("REPORT", "CHECK_IN", ["CHECK_IN"], "Status?"), ("ACT", None, ["LIMIT_CHANGE"], None)]


def test_triggers_added_together_arrive_together():
    queue = TriggerQueue()
    with queue.together():
        queue.add(trigger("CHECK_IN", 900), check_in_text="Status?")
        queue.add(limit(900))
    assert turns(queue) == [("ACT", None, ["LIMIT_CHANGE"], None), ("REPORT", "CHECK_IN", ["CHECK_IN"], "Status?")]


def test_red_a_report_turn_in_flight_still_holds_the_action_turn_back():
    queue = TriggerQueue()
    queue.add(trigger("CHECK_IN", 900), check_in_text="Status?")
    report = queue.take()
    queue.add(limit(901))
    assert report.turn_kind == "REPORT" and queue.take() is None
    queue.finish()
    assert queue.take().turn_kind == "ACT"


def test_the_hand_back_report_at_revocation_follows_the_action_turn():
    queue = TriggerQueue()
    revoke = trigger("REVOKE", 1000)
    queue.add(revoke)
    queue.add_report("HAND_BACK", revoke)
    assert turns(queue) == [("ACT", None, ["REVOKE"], None), ("REPORT", "HAND_BACK", ["REVOKE"], None)]


@pytest.mark.parametrize("met_s, due", [(859, False), (860, True), (900, True)])
def test_periodic_is_due_60_seconds_after_the_newest_trigger(met_s, due):
    queue = TriggerQueue()
    assert not queue.periodic_due(10_000)   # nothing yet to count from
    queue.add(trigger("AOS", 790))
    queue.add(trigger("PERIODIC", 800))
    assert queue.periodic_due(met_s) is due


def test_red_a_trigger_type_the_contract_does_not_list_is_refused():
    with pytest.raises(ValueError):
        trigger("ALARM", 900)
