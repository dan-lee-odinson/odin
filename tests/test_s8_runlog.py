"""The frames a run's seat received, rebuilt from its truth file (the Director's scoring ruling of 28 October
2026, introduction): a frame generated and sent down to COSMOS in the ground seat, or read beside the simulator
in the onboard seat, and nothing the receiver dropped, nothing out of contact, and no tick of a halt."""

import pytest

from eval.runlog import received_frames, same_value


def state(downlink, generated=True, load=0.8):
    return {"frame_generated": generated, "downlink": downlink, "faults_active": [],
            "eps": {"soc_pct": 60.0, "energy_wh": 20.0, "battery_v": 7.6, "battery_i": 0.5, "bus_v": 5.0,
                    "load_i": load, "string_i": [1.7, 1.7], "mode": "NOMINAL", "illuminated": True,
                    "payload_on": True, "pld_rate_hz": 1.0},
            "cdh": {"hk_halted": not generated, "frame_count": 5, "acc_count": 1, "rej_count": 0, "rej_reason": "NONE"}}


def truth(*states):
    return [{"type": "TRUE_STATE", "met_s": met, "body": body} for met, body in states]


def test_the_ground_seat_received_only_the_frames_sent_down():
    frames = received_frames(truth((900, state("SENT", load=1.8)), (901, state("RECEIVER_DOWN")),
                                   (902, state("OUT_OF_CONTACT")), (903, state(None, generated=False))))
    assert list(frames) == [900] and frames[900]["EPS_LOAD_I"] == 1.7999999523162842   # as the 32-bit codec packs it


def test_the_onboard_seat_reads_every_frame_generated():
    assert list(received_frames(truth((900, state(None)), (901, state(None)), (902, state(None, generated=False))))) == [900, 901]


# -- a claimed value against the frame's (the Director's ruling of 30 October 2026, "Within half a display unit") --

@pytest.mark.parametrize("point, claimed, actual, same", [
    ("EPS_BATT_V", 7.75, 7.74965763092041, True),    # M5's PASS-1 claim, 0.0003 V off, either side of a rounding edge
    ("EPS_BATT_V", 7.75, 7.70, True),                # the boundary, half a display unit below, included
    ("EPS_BATT_V", 7.75, 7.80, True),                # and above
    ("EPS_BATT_I", 1.05, 1.0, True),                 # the boundary where the float difference lands just above 0.05
    ("EPS_BATT_V", 7.7501, 7.70, False),             # just outside the window
    ("EPS_BATT_V", 7.75, 7.8001, False),
    ("EPS_SA1_I", 0.105, 0.1, True),                 # 2 decimals: half a unit is 0.005
    ("EPS_SA1_I", 0.1051, 0.1, False),
    ("EPS_BATT_SOC", 35.5, 35.0, True),              # 0 decimals: half a unit is 0.5
    ("EPS_BATT_SOC", 35.51, 35.0, False)])
def test_red_a_claimed_float_is_the_same_within_half_a_display_unit_of_the_frames(point, claimed, actual, same):
    assert same_value(point, claimed, actual) is same


def test_red_states_and_counts_stay_exact():
    assert same_value("EPS_MODE", "NOMINAL", "NOMINAL") and not same_value("EPS_MODE", "SAFE", "NOMINAL")
    assert same_value("CDH_FRAME_CNT", 20, 20) and not same_value("CDH_FRAME_CNT", 20, 21)
    assert not same_value("EPS_BATT_V", True, 1.0) and not same_value("EPS_BATT_V", "7.75", 7.75)
