"""The check-in every pass of phases 2 and 3 carries (the Director's scoring ruling of 28 October 2026, §4 and
selection 3): one per contact at loss of signal minus 90 s, in his words, as text until his recording is
transcribed once (U44), then the frozen transcript with its audio's hash; none in phase 1."""

import hashlib

import pytest

from harness.checkins import PHASES, RECORDING, RECORDING_SHA256, WORDS, pass_check_ins
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


@pytest.mark.parametrize("phase, expected", [(2, [1140]), (3, [1140])])
def test_phases_2_and_3_carry_it(tmp_path, phase, expected):
    harness = HarnessWorld(tmp_path)
    run = harness.run(phase=phase)
    assert run.start()
    try:
        assert [met for met, body in run.check_ins if body["text"] == WORDS] == expected
    finally:
        run.stop()
