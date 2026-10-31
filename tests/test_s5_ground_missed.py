"""A frame the link sent that the ground seat never received is written into the truth file, GROUND_MISSED; S8 does
not count it as received; and it sets the run aside, LINK_LOST (the Director's word of 30 October 2026). Against
tests/fake_cosmos.py, as S5's other tests are."""

import time
from types import SimpleNamespace

import pytest

import eval.set_aside as aside
from connector.api import CosmosApi
from eval import runlog
from harness import run as harness_run
from harness.run import Run
from tests.fake_cosmos import FakeCosmos
from tests.test_s5_connector import PASSWORD, cosmos, flown, fly, free_port, scripted  # noqa: F401  (fixtures)
from wrapper.link import Link

scripted_answers = scripted


def truth_of(run, type_):
    return [r for r in runlog.read_jsonl(run.final / runlog.TRUTH) if r["type"] == type_]


def test_red_frames_cosmos_never_shows_are_written_as_missed_and_set_the_run_aside(tmp_path, monkeypatch):
    monkeypatch.setattr(harness_run, "GROUND_WAIT_S", 0.05)
    link_at = ("127.0.0.1", free_port())
    fake = FakeCosmos(link_at, PASSWORD, decode=False).start()   # connected, and showing nothing
    try:
        run = fly(tmp_path, monkeypatch, (fake, CosmosApi(fake.url, PASSWORD), link_at), scripted())
    finally:
        fake.stop()
    ticks = truth_of(run, "TRUE_STATE")
    sent = [r["met_s"] for r in ticks if r["body"]["downlink"] == "SENT"]
    missed = [r["body"] for r in truth_of(run, "GROUND_MISSED")]
    assert missed and {m["how"] for m in missed} == {"NOT_SHOWN"}
    # The run ticks on after loss of signal, so every frame sent long enough before its last tick is judged.
    last = max(r["met_s"] for r in ticks)
    assert [m["frame_met_s"] for m in missed] == [m for m in sent if m + harness_run.MISSED_AFTER_S <= last]
    assert all(m["noticed_met_s"] - m["frame_met_s"] == harness_run.MISSED_AFTER_S for m in missed)
    truth = runlog.read_jsonl(run.final / runlog.TRUTH)
    assert not set(runlog.received_frames(truth)) & {m["frame_met_s"] for m in missed}
    assert [c["key"] for c in aside.link_causes(truth)] == ["LINK_LOST NOT_SHOWN"]


def test_a_ground_run_whose_cosmos_shows_every_frame_misses_none(flown):
    run, _, _ = flown
    assert truth_of(run, "GROUND_MISSED") == []


OUTAGE = (820, 840)   # a scripted receiver outage, as S4's live pass and wrapper/serve.py script one


def test_red_frames_a_scripted_receiver_fault_withholds_are_the_scenarios_not_link_lost(tmp_path, monkeypatch, cosmos):
    # The Director's word of 30 October 2026: the scenario's own link fault keeps frames from the seat by design; only
    # frames our link or COSMOS lost are ours.
    downlink = Link.downlink

    def scripted(link, raw, met_s):
        link.receiver_up = not OUTAGE[0] <= met_s < OUTAGE[1]
        return downlink(link, raw, met_s)
    monkeypatch.setattr(Link, "downlink", scripted)
    run = fly(tmp_path, monkeypatch, cosmos, scripted_answers())
    ticks = truth_of(run, "TRUE_STATE")
    withheld = [r["met_s"] for r in ticks if r["body"]["downlink"] == "RECEIVER_DOWN"]
    assert withheld == list(range(*OUTAGE))
    truth = runlog.read_jsonl(run.final / runlog.TRUTH)
    assert truth_of(run, "GROUND_MISSED") == [] and aside.link_causes(truth) == []
    assert not set(runlog.received_frames(truth)) & set(withheld)


def test_red_a_runs_scripted_receiver_fault_reaches_the_ground_seats_link(tmp_path, monkeypatch, cosmos):
    # S9, piece 3: the run gives its scenario's ground-receiver fault to the link, which withholds those frames only.
    run = fly(tmp_path, monkeypatch, cosmos, scripted_answers(), run_options={"receiver_down": [OUTAGE]})
    ticks = truth_of(run, "TRUE_STATE")
    assert [r["met_s"] for r in ticks if r["body"]["downlink"] == "RECEIVER_DOWN"] == list(range(*OUTAGE))
    assert aside.link_causes(runlog.read_jsonl(run.final / runlog.TRUTH)) == []


def awaiting(*mets):
    written = []
    seat = SimpleNamespace(_awaited=set(mets), truth=SimpleNamespace(append=lambda t, b: written.append((t, b))))
    return seat, written


def test_red_a_frame_the_seat_moved_past_is_missed_as_superseded():
    seat, written = awaiting(900, 901)
    Run._missed(seat, 902, 902)   # COSMOS showed 902 first: 900 and 901 will never come
    assert [b for _, b in written] == [{"frame_met_s": 900, "noticed_met_s": 902, "how": "SUPERSEDED"},
                                       {"frame_met_s": 901, "noticed_met_s": 902, "how": "SUPERSEDED"}]
    assert seat._awaited == set()


def test_a_frame_shown_or_still_awaited_is_not_missed():
    seat, written = awaiting(900, 901)
    Run._missed(seat, 901, 900)   # 900 shown; 901 only a second old
    assert written == [] and seat._awaited == {901}
    Run._missed(seat, 901 + harness_run.MISSED_AFTER_S, None)
    assert [b["how"] for _, b in written] == ["NOT_SHOWN"] and seat._awaited == set()


def test_red_a_frame_cosmos_showed_while_an_earlier_tick_waited_is_the_seats(monkeypatch):
    # The Director's ruling of 31 October 2026: two frames reached COSMOS before the first one's tick had looked, so it
    # showed the newer, which the seat then had. Only the older is missed; the newer is neither awaited again, to be
    # written as missed once a later frame is shown, nor waited for.
    monkeypatch.setattr(harness_run, "GROUND_WAIT_S", 0.3)
    seat, written = awaiting()
    link, showing, pending, received = SimpleNamespace(counts={"SENT": 0}), {"received_count": 0}, [], []

    def send(met):   # the link sends met's frame, and COSMOS shows it
        link.counts["SENT"] += 1
        showing.update(received_count=showing["received_count"] + 1, frame={"CDH_MET": met},
                       received_utc="2026-07-29T14:00:00Z")

    def packet():
        while pending:   # the clock stepped on while this tick waited
            send(pending.pop())
        return dict(showing)

    vars(seat).update(link=link, cosmos=SimpleNamespace(packet=packet), _sent_seen=0, _ground_count=0, _shown_met=None,
                      store=SimpleNamespace(receive=lambda frame, utc, met: received.append(frame["CDH_MET"])),
                      _missed=lambda met, shown: Run._missed(seat, met, shown))
    send(900)
    pending.append(901)
    assert Run._ground_frame(seat, 900)["CDH_MET"] == 901
    started = time.monotonic()
    assert Run._ground_frame(seat, 901) is None
    assert time.monotonic() - started < 0.15
    send(902)
    assert Run._ground_frame(seat, 902)["CDH_MET"] == 902
    assert [b for _, b in written] == [{"frame_met_s": 900, "noticed_met_s": 900, "how": "SUPERSEDED"}]
    assert seat._awaited == set() and received == [901, 902]


def test_s8_does_not_count_a_missed_frame_as_received():
    state = {"frame_generated": True, "downlink": "SENT", "illuminated": True,
             "eps": {"battery_v": 7.7, "battery_i": 1.3, "soc_pct": 66.0, "string_i": [1.7, 1.7], "bus_v": 5.0,
                     "load_i": 1.4, "mode": "NOMINAL", "illuminated": True, "payload_on": True, "pld_rate_hz": 1.0},
             "cdh": {"frame_count": 900, "acc_count": 1, "rej_count": 0, "rej_reason": "NONE"}}
    truth = [{"type": "TRUE_STATE", "met_s": 900, "body": state}, {"type": "TRUE_STATE", "met_s": 901, "body": state}]
    assert sorted(runlog.received_frames(truth)) == [900, 901]
    missed = {"type": "GROUND_MISSED", "met_s": 906, "body": {"frame_met_s": 900, "noticed_met_s": 906,
                                                                "how": "NOT_SHOWN"}}
    assert sorted(runlog.received_frames(truth + [missed])) == [901]


@pytest.mark.parametrize("record, key", [
    ({"type": "TRUE_STATE", "met_s": 950, "body": {"downlink": "NO_GROUND"}}, "LINK_LOST NO_GROUND"),
    ({"type": "GROUND_MISSED", "met_s": 956, "body": {"frame_met_s": 950, "noticed_met_s": 956, "how": "NOT_SHOWN"}},
     "LINK_LOST NOT_SHOWN")])
def test_red_14_a_frame_lost_to_our_link_or_cosmos_sets_the_run_aside_from_the_first(record, key):
    ours = aside.link_causes([record])
    assert [c["key"] for c in ours] == [key] and "the first at MET 950" in ours[0]["detail"]


def test_frames_the_scenario_kept_from_the_seat_are_not_ours():
    scripted_out = [{"type": "TRUE_STATE", "met_s": 950, "body": {"downlink": how}}
                    for how in ("RECEIVER_DOWN", "OUT_OF_CONTACT", "SENT", None)]
    assert aside.link_causes(scripted_out) == []
