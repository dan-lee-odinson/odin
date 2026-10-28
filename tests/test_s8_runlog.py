"""The frames a run's seat received, rebuilt from its truth file (the Director's scoring ruling of 28 October
2026, introduction): a frame generated and sent down to COSMOS in the ground seat, or read beside the simulator
in the onboard seat, and nothing the receiver dropped, nothing out of contact, and no tick of a halt."""

from eval.runlog import received_frames


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
