"""HUGINN's scenarios as the S4 tests use them, and the contact windows the Director flew them in.

FLOWN holds each campaign pass's contact as MET [aos, los), from HUGINN's docs/pass_reports/: PASS-1
(2026-09-13-P1) flew contact 17's 410 s from MET 0; PASS-2 flew 330 s at MET 2190 (2026-09-20-P2a) and
430 s at MET 21800 (2026-09-20-P2b); PASS-3 (2026-10-11-P3) flew MET 800 to 1230; PASS-4
(2026-10-11-P4) flew MET 1100 to 1530.
"""

from wrapper.huginn import Scenario, load_scenario

FLOWN = {
    "P1_nominal": [(0, 410)],
    "P2_array_string_loss": [(2190, 2520), (21800, 22230)],
    "P3_stuck_load": [(800, 1230)],
    "P4_hk_generation_halt": [(1100, 1530)],
}


def bare(name):
    """A scenario with every scripted command removed, in memory, for tests of the link, the tap and the
    clock that must see no command but their own."""
    scenario = load_scenario(name)
    return Scenario(dict(scenario.data, commands=[]), scenario.path)
