"""The check-in every pass of phases 2 and 3 carries (the Director's scoring ruling of 28 October 2026, §4 and
selection 3): one per contact at loss of signal minus 90 s, in his words, as text until his recording is
transcribed once (U44), then the frozen transcript with its audio's hash; none in phase 1, which has its own
four as text (U60)."""

import hashlib

import pytest

from harness.checkins import (PHASE_1, PHASE_1_RUN_S, PHASES, RECORDING, RECORDING_SHA256, WORDS, pass_check_ins,
                              phase_1_check_ins)
from tests.harness_world import HarnessWorld

TRANSCRIPT = {"text": "ODIN this is Flight. Report the spacecraft condition, your actions this pass, and anything "
                      "you're watching.", "audio_sha256": RECORDING_SHA256}


def test_the_words_are_the_directors_own():
    assert WORDS == ("ODIN this is Flight. Report the spacecraft condition, your actions this pass, "
                     "and anything you're watching.")


def test_the_recording_is_placed_byte_for_byte_with_the_hash_the_director_gave():
    assert RECORDING_SHA256 == "sha256:a4f3fb3deaadf01883ab21f8a463057202cca2bd480bbcc4e7e841c9af6508ff"
    assert "sha256:" + hashlib.sha256(RECORDING.read_bytes()).hexdigest() == RECORDING_SHA256


def test_one_check_in_per_contact_at_loss_of_signal_minus_90_s_as_text_until_transcribed():
    assert pass_check_ins([(800, 1230), (21800, 22230)]) == [
        (1140, {"text": WORDS, "audio_sha256": None, "source": "TEXT", "utc": None}),
        (22140, {"text": WORDS, "audio_sha256": None, "source": "TEXT", "utc": None})]


def test_once_transcribed_the_frozen_transcript_plays_with_its_audio_hash():
    [(met, body)] = pass_check_ins([(800, 1230)], transcript=TRANSCRIPT)
    assert (met, body["source"], body["audio_sha256"]) == (1140, "RECORDED", TRANSCRIPT["audio_sha256"])


def test_red_a_transcript_without_its_audio_hash_is_refused():
    with pytest.raises(ValueError):
        pass_check_ins([(800, 1230)], transcript=dict(TRANSCRIPT, audio_sha256=None))


def test_red_a_transcript_of_other_audio_is_refused():
    with pytest.raises(ValueError, match="not the Director's recording"):
        pass_check_ins([(800, 1230)], transcript=dict(TRANSCRIPT, audio_sha256="sha256:" + "3d" * 32))


def test_phase_1_does_not_carry_it():
    # Phase 1 flies COSMOS's demo target, with its own four check-ins as text (the Director's rulings of 27
    # October 2026, §1); it is never a pass of HUGINN's.
    assert 1 not in PHASES


# The Director's approved phase-1 check-ins (U60): PH1_CHECKINS.md, whose table is the harness's row for row, so
# the words are his exactly when the file rebuilds from the harness's table to the hash he gave.
PH1_CHECKINS_SHA256 = "11b265c6b42f9fdbc2dc872113b965c5b6fc48ba5204408203343be960f94ef8"
PH1_CHECKINS_HEAD = ("# Phase-1 check-ins (drafted for the Director, 28 October 2026)\n\n"
                     "Delivered as text (source TEXT), at these mission-elapsed times, in a run of 1,800 s:\n\n"
                     "| MET (s) | Check-in |\n|---:|---|\n")


def test_phase_1s_four_check_ins_are_the_directors_approved_table_word_for_word():
    rebuilt = PH1_CHECKINS_HEAD + "".join(f"| {met} | {words} |\n" for met, words in PHASE_1)
    assert hashlib.sha256(rebuilt.encode("utf-8")).hexdigest() == PH1_CHECKINS_SHA256
    assert [met for met, _ in PHASE_1] == [300, 720, 1200, 1620] and PHASE_1_RUN_S == 1800
    assert [(met, body["text"], body["source"], body["audio_sha256"]) for met, body in phase_1_check_ins()] == [
        (met, words, "TEXT", None) for met, words in PHASE_1]


@pytest.mark.parametrize("phase, expected", [(2, [1140]), (3, [1140])])
def test_phases_2_and_3_carry_it(tmp_path, phase, expected):
    harness = HarnessWorld(tmp_path)
    run = harness.run(phase=phase)
    assert run.start()
    try:
        assert [met for met, body in run.check_ins if body["text"] == WORDS] == expected
    finally:
        run.stop()
