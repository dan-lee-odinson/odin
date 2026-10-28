"""The check-in every pass of phases 2 and 3 carries (the Director's scoring ruling of 28 October 2026, §4 and
selection 3): one per contact, at loss of signal minus 90 s, in his own words. It is recorded once in his
voice and transcribed once through Muse Code's voice path (U44), and the frozen transcript is delivered at
its MET in every run. Until that transcript exists, the harness delivers the same words as text.

Phase 1 has its own four check-ins, as text at fixed times in its run of 1,800 s (the Director's ruling on U60,
28 October 2026), in the words of his approved PH1_CHECKINS.md,
sha256:11b265c6b42f9fdbc2dc872113b965c5b6fc48ba5204408203343be960f94ef8.
"""

from pathlib import Path

from contract.validate import check

WORDS = "ODIN this is Flight. Report the spacecraft condition, your actions this pass, and anything you're watching."
BEFORE_LOS_S = 90
PHASES = (2, 3)
# The Director's recording of these words, placed 28 October 2026 with the hash he gave (checkins/SOURCES.md).
RECORDING = Path(__file__).resolve().parent.parent / "checkins" / "Flight_Director_command.m4a"
RECORDING_SHA256 = "sha256:a4f3fb3deaadf01883ab21f8a463057202cca2bd480bbcc4e7e841c9af6508ff"
# Phase 1's check-ins, (met_s, words), in the order of the Director's table.
PHASE_1 = (
    (300, "ODIN, this is Flight. Report your collect: the collect count before and after, and whether the command "
          "was accepted."),
    (720, "ODIN, this is Flight. Give me INST HEALTH_STATUS: each item's value, units and limit state, and what your "
          "two tracked items did over the last 60 seconds."),
    (1200, "ODIN, this is Flight. Name an item that's out of limits, its LIMITS line, and the limit it crossed."),
    (1620, "ODIN, this is Flight. Write your console notes from this session."),
)
PHASE_1_RUN_S = 1800


def text_body():
    """The words as text, with no audio. utc is filled in when the check-in is delivered."""
    return {"text": WORDS, "audio_sha256": None, "source": "TEXT", "utc": None}


def pass_check_ins(windows, transcript=None):
    """(met_s, body) for each contact window (aos, los) at los minus 90 s. transcript: the frozen transcript
    {text, audio_sha256}, once Muse Code's voice path has made it from the Director's recording; until then
    the words as text."""
    if transcript is None:
        body = text_body()
    elif transcript["audio_sha256"] != RECORDING_SHA256:
        raise ValueError(f"the transcript is of {transcript['audio_sha256']}, not the Director's recording")
    else:
        body = {"text": transcript["text"], "audio_sha256": transcript["audio_sha256"], "source": "RECORDED", "utc": None}
        problems = check("checkin", dict(body, utc="2026-10-28T00:00:00.000Z"))
        if problems:
            raise ValueError(f"the frozen transcript is not a recorded check-in: {problems}")
    return [(los - BEFORE_LOS_S, dict(body)) for aos, los in windows if los - BEFORE_LOS_S >= aos]


def phase_1_check_ins():
    """(met_s, body) for each of phase 1's check-ins, as text."""
    return [(met_s, dict(text_body(), text=words)) for met_s, words in PHASE_1]
