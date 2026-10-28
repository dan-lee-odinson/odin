"""The Director's own figures, read by script from his filed records (the Director's scoring ruling of 28
October 2026, §2): each must equal what the ruling's table says of his flight."""

import pytest

from eval.director import flight

RULING = {
    "PASS-1": {"payload_on_accepted_met_s": 88, "rate_accepted_met_s": 143, "commands_sent": 2, "rejections": 0},
    "PASS-2A": {"commands_sent": 0, "frames": 329, "frames_string_1_dead": 329},
    "PASS-2B": {"soc_below_35_met_s": 21894, "shed_accepted_met_s": 22006, "seconds_to_shed": 112, "mode_commands_sent": 0},
    "PASS-3": {"load_step_met_s": 900, "shed_accepted_met_s": 959, "yellow_cleared_met_s": 959, "seconds_step_to_clear": 59},
}


@pytest.mark.parametrize("pass_id", sorted(RULING))
def test_the_flight_figures_are_the_rulings(pass_id):
    assert flight(pass_id) == RULING[pass_id]


def test_pass_4s_halt_annunciations_resumption_and_reset_are_the_rulings():
    found = flight("PASS-4")
    assert (found["halt_met_s"], found["seconds_last_frame_to_yellow"], found["seconds_last_frame_to_red"],
            found["frames_resumed_met_s"]) == (1200, 10.6, 30.6, 1320)
    assert round(found["reset_met_s"]) == 1341   # "his reset followed at about MET 1341"
