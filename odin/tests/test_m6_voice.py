"""M6: the voice check-in (CONTRACT §13, U44; Director's M6 ruling).

One recorded check-in, transcribed once through Muse Voice Transcribe:
hash checked before anything is sent, price per audio hour against the
META stop, frozen record that refuses to overwrite, and a POST /checkin
body with source RECORDED. Every test runs against a fake transcriber;
no network, no paid call.
"""
import hashlib
import io
import json
import wave
from pathlib import Path

import pytest
import yaml

from odin.loop.canonical import canonical_json, sha256_tag
from odin.loop.validate import validate_against_schema
from odin.spend.meter import SpendMeter
from odin.voice.transcribe import (
    ENDPOINT, EXPECTED_AUDIO_SHA256, HashMismatchError, PriceError,
    RecordExistsError, SpendRefusedError, VoiceError,
    assert_no_private_paths, build_checkin_body,
    checkin_body, conversion_command, load_voice_price, meta_transcriber,
    post_checkin, transcribe_recording,
)
from conftest import REPO_ROOT

RECORDING = REPO_ROOT / "checkins" / "Flight_Director_command.m4a"
TEXT = "ODIN this is Flight. Report the spacecraft condition, your actions this pass, and anything you're watching."


def _wav_bytes(seconds=2.0, rate=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def _prices(tmp_path, entry="default"):
    if entry == "default":
        doc = {"voice_transcribe": {"model": "muse-voice-transcribe-1.0",
                                    "per_audio_hour": 0.18, "stop": "META",
                                    "source": "https://dev.meta.ai/docs/speech-to-text",
                                    "date": "2026-10-29"}}
    elif entry is None:
        doc = {"spark": {"input_per_mtok": 1.25, "cached_input_per_mtok": 0.15,
                         "output_per_mtok": 4.25}}
    else:
        doc = {"voice_transcribe": entry}
    path = tmp_path / "prices.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return path


class FakeConverter:
    def __init__(self, wav):
        self.wav = wav
        self.calls = []

    def __call__(self, audio_path, wav_path):
        self.calls.append((audio_path, wav_path))
        Path(wav_path).write_bytes(self.wav)
        return self.wav, "ffmpeg -i ./clip.m4a -ac 1 -ar 24000 -sample_fmt s16 ./clip.wav"


class FakeTranscriber:
    def __init__(self, ledger=None, response=None):
        self.ledger = ledger
        self.response = response if response is not None else {"transcript": TEXT, "audioDurationMs": 2000}
        self.calls = []
        self.reserved_before_call = None

    def __call__(self, wav_bytes, *, model, endpoint):
        self.calls.append((wav_bytes, model, endpoint))
        if self.ledger is not None and Path(self.ledger).exists():
            kinds = [json.loads(l)["kind"] for l in Path(self.ledger).read_text().splitlines() if l.strip()]
            self.reserved_before_call = "RESERVE" in kinds
        return self.response


def _setup(tmp_path, response=None, seconds=2.0):
    audio = tmp_path / "clip.m4a"
    audio.write_bytes(b"fake audio bytes")
    expected = sha256_tag(audio.read_bytes())
    prices = _prices(tmp_path)
    ledger = tmp_path / "spend.jsonl"
    meter = SpendMeter(ledger_path=ledger, prices_path=prices)
    converter = FakeConverter(_wav_bytes(seconds))
    transcriber = FakeTranscriber(ledger, response)
    record = tmp_path / "record.json"
    kwargs = dict(audio_path=audio, record_path=record, wav_path=tmp_path / "clip.wav",
                  meter=meter, prices_path=prices, converter=converter,
                  transcriber=transcriber, expected_sha256=expected,
                  now_fn=lambda: "2026-10-29T12:00:00.000Z")
    return kwargs, converter, transcriber, ledger, record


# -- the recording's hash, before anything is sent --------------------------------

def test_real_recording_matches_the_pinned_hash():
    assert sha256_tag(RECORDING.read_bytes()) == EXPECTED_AUDIO_SHA256


def test_one_changed_byte_is_refused_and_nothing_is_sent(tmp_path):
    kwargs, converter, transcriber, _ledger, _record = _setup(tmp_path)
    data = bytearray(kwargs["audio_path"].read_bytes())
    data[0] ^= 1
    kwargs["audio_path"].write_bytes(bytes(data))
    with pytest.raises(HashMismatchError):
        transcribe_recording(**kwargs)
    assert converter.calls == [] and transcriber.calls == []


def test_fake_flow_on_the_real_recording(tmp_path):
    prices = _prices(tmp_path)
    ledger = tmp_path / "spend.jsonl"
    meter = SpendMeter(ledger_path=ledger, prices_path=prices)
    transcriber = FakeTranscriber(ledger, {"transcript": TEXT, "audioDurationMs": 8190})
    record = tmp_path / "record.json"
    result = transcribe_recording(
        audio_path=RECORDING, record_path=record, wav_path=tmp_path / "clip.wav",
        meter=meter, prices_path=prices, converter=FakeConverter(_wav_bytes(2.0)),
        transcriber=transcriber, now_fn=lambda: "2026-10-29T12:00:00.000Z")
    assert result["audio_sha256"] == EXPECTED_AUDIO_SHA256


# -- the frozen record --------------------------------------------------------------

def test_frozen_record_is_canonical_and_holds_every_field(tmp_path):
    kwargs, _c, _t, _l, record_path = _setup(tmp_path)
    record = transcribe_recording(**kwargs)
    assert record["text"] == TEXT  # exactly as returned
    assert record["audio_sha256"] == kwargs["expected_sha256"]
    assert record["wav_sha256"] == sha256_tag(_wav_bytes(2.0))
    assert record["model"] == "muse-voice-transcribe-1.0"
    assert record["endpoint"] == ENDPOINT == "https://api.meta.ai/v1/asr/transcribe"
    assert record["utc"] == "2026-10-29T12:00:00.000Z"
    assert "ffmpeg" in record["conversion"]
    assert record_path.read_bytes() == canonical_json(record)
    sidecar = json.loads((tmp_path / "record.sha256.json").read_text(encoding="utf-8"))
    assert sidecar["file"] == "record.json" and sidecar["frozen"] is True
    assert sidecar["sha256"] == sha256_tag(record_path.read_bytes())


def test_existing_record_is_refused_and_not_overwritten(tmp_path):
    kwargs, converter, transcriber, _l, record_path = _setup(tmp_path)
    record_path.write_bytes(b"already here")
    with pytest.raises(RecordExistsError):
        transcribe_recording(**kwargs)
    assert record_path.read_bytes() == b"already here"
    assert converter.calls == [] and transcriber.calls == []


# -- spend: per audio hour, META stop, reserved before the call ----------------------

def test_cost_reserved_before_and_settled_after_from_meta_duration(tmp_path):
    kwargs, _c, transcriber, ledger, _r = _setup(
        tmp_path, response={"transcript": TEXT, "audioDurationMs": 4000})
    transcribe_recording(**kwargs)
    assert transcriber.reserved_before_call is True
    events = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    reserve = next(e for e in events if e["kind"] == "RESERVE")
    settle = next(e for e in events if e["kind"] == "SETTLE")
    # WAV is 2.0 s: reserved at 2/3600 h; Meta reported 4.0 s: settled at 4/3600 h.
    assert reserve["reserved_usd"] == pytest.approx(2.0 / 3600 * 0.18)
    assert settle["actual_usd"] == pytest.approx(4.0 / 3600 * 0.18)
    assert settle["duration_source"] == "META_REPORT"
    assert reserve["bucket"] == settle["bucket"] == "META_CREDIT"
    assert kwargs["meter"].totals()["META_CREDIT"] == pytest.approx(4.0 / 3600 * 0.18)


def test_billing_rounds_down_to_whole_seconds(tmp_path):
    kwargs, _c, _t, ledger, _r = _setup(
        tmp_path, response={"transcript": TEXT, "audioDurationMs": 4900})
    transcribe_recording(**kwargs)
    settle = next(json.loads(l) for l in ledger.read_text().splitlines()
                  if l.strip() and json.loads(l)["kind"] == "SETTLE")
    assert settle["actual_usd"] == pytest.approx(4 / 3600 * 0.18)


def test_settle_falls_back_to_the_wav_duration_and_says_so(tmp_path):
    kwargs, _c, _t, ledger, _r = _setup(tmp_path, response={"transcript": TEXT})
    transcribe_recording(**kwargs)
    settle = next(json.loads(l) for l in ledger.read_text().splitlines()
                  if l.strip() and json.loads(l)["kind"] == "SETTLE")
    assert settle["actual_usd"] == pytest.approx(2.0 / 3600 * 0.18)
    assert settle["duration_source"] == "WAV_FILE"


def test_spend_stop_refuses_before_the_call(tmp_path):
    kwargs, _c, transcriber, _l, _r = _setup(tmp_path)
    meter = kwargs["meter"]
    big = meter.reserve(config="spark", input_tokens=0, max_output_tokens=1,
                        turn_id=9, call_index=1, reserved_usd=125.0)
    big.settle(actual_usd=125.0)
    with pytest.raises(SpendRefusedError):
        transcribe_recording(**kwargs)
    assert transcriber.calls == []


@pytest.mark.parametrize("entry", [
    None,
    {"per_audio_hour": 0.18, "stop": "META"},
    {"model": "muse-voice-transcribe-1.0", "stop": "META"},
    {"model": "muse-voice-transcribe-1.0", "per_audio_hour": "0.18", "stop": "META"},
    {"model": "muse-voice-transcribe-1.0", "per_audio_hour": 0, "stop": "META"},
    {"model": "muse-voice-transcribe-1.0", "per_audio_hour": -1, "stop": "META"},
    {"model": "muse-voice-transcribe-1.0", "per_audio_hour": 0.18},
    {"model": "muse-voice-transcribe-1.0", "per_audio_hour": 0.18, "stop": "BASETEN"},
])
def test_missing_or_malformed_price_entry_refuses(tmp_path, entry):
    with pytest.raises(PriceError):
        load_voice_price(_prices(tmp_path, entry))
    kwargs, _c, transcriber, _l, _r = _setup(tmp_path)
    kwargs["prices_path"] = _prices(tmp_path, entry)
    with pytest.raises(PriceError):
        transcribe_recording(**kwargs)
    assert transcriber.calls == []


# -- Meta's request form, key only from META_API_KEY ---------------------------------

def test_meta_transcriber_posts_multipart_with_the_env_key(tmp_path, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "meta-test-key")
    monkeypatch.setenv("MODEL_API_KEY", "wrong-key-must-not-be-used")
    sent = {}

    def fake_post(url, headers, body, content_type, timeout):
        sent.update(url=url, headers=headers, body=body, content_type=content_type)
        return 200, {"transcript": TEXT, "audioDurationMs": 2000}

    transcriber = meta_transcriber(http_post=fake_post)
    result = transcriber(_wav_bytes(1.0), model="muse-voice-transcribe-1.0", endpoint=ENDPOINT)
    assert result["transcript"] == TEXT
    assert sent["url"] == ENDPOINT
    assert sent["headers"]["Authorization"] == "Bearer meta-test-key"
    assert "multipart/form-data" in sent["content_type"]
    assert b"muse-voice-transcribe-1.0" in sent["body"]
    assert b'"audioEncoding":"WAV"' in sent["body"] or b'"audioEncoding": "WAV"' in sent["body"]
    assert _wav_bytes(1.0) in sent["body"]


def test_meta_transcriber_without_meta_key_refuses(monkeypatch):
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_API_KEY", "wrong-key-must-not-be-used")
    transcriber = meta_transcriber(http_post=lambda *a: (200, {}))
    with pytest.raises(RuntimeError):
        transcriber(_wav_bytes(1.0), model="muse-voice-transcribe-1.0", endpoint=ENDPOINT)


# -- the check-in ---------------------------------------------------------------------

def _record():
    return {"text": TEXT, "audio_sha256": EXPECTED_AUDIO_SHA256,
            "wav_sha256": sha256_tag(b"wav"), "conversion": "ffmpeg ...",
            "model": "muse-voice-transcribe-1.0", "endpoint": ENDPOINT,
            "utc": "2026-10-29T12:00:00.000Z"}


def test_checkin_body_is_recorded_and_validates():
    body = build_checkin_body(_record())
    assert body == {"text": TEXT, "audio_sha256": EXPECTED_AUDIO_SHA256,
                    "source": "RECORDED", "utc": "2026-10-29T12:00:00.000Z"}
    assert validate_against_schema("checkin.schema.json", body) == []
    # TEXT with a recording's hash is exactly what the schema refuses.
    assert validate_against_schema("checkin.schema.json", {**body, "source": "TEXT"}) != []


def test_checkin_body_goes_to_the_fake_harness():
    from odin.devtools.fake_harness import FakeServices

    services = FakeServices()
    body = build_checkin_body(_record())
    status = post_checkin(body, harness_url=services.url, transport=services.transport)
    assert status == 200
    assert services.checkins == [body]


def test_checkin_body_rejects_a_wrong_audio_hash():
    with pytest.raises(ValueError):
        build_checkin_body({**_record(), "audio_sha256": "sha256:" + "0" * 64})


# -- relative paths only (Director's rewrite ruling) -------------------------------

# Made-up profile paths, built from pieces (as the M3 canary key names
# are) so no file holds a user-profile path literally.
_PROFILE_WIN = "\\".join(["C:", "".join(["Use", "rs"]), "".join(["some", "one"])])
_PROFILE_POSIX = "/".join(["", "".join(["Use", "rs"]), "".join(["some", "one"])])
_SOMEONE = "".join(["some", "one"])

def test_conversion_command_uses_paths_relative_to_the_workspace_root():
    command = conversion_command(REPO_ROOT / "checkins" / "Flight_Director_command.m4a",
                                 REPO_ROOT / "odin" / "voice" / "Flight_Director_command.wav")
    assert command[0] == "ffmpeg"
    for arg in command:
        assert not Path(arg).is_absolute(), arg
    assert command[3].startswith("."), command
    assert command[-1].startswith("."), command


@pytest.mark.parametrize("field", ["text", "audio_sha256", "wav_sha256", "conversion",
                                   "model", "endpoint", "utc"])
@pytest.mark.parametrize("bad", ["\\".join([_PROFILE_WIN, "Documents", "x.wav"]),
                                 "/".join([_PROFILE_POSIX, "x.wav"]),
                                 "\\\\server\\share\\x.wav"])
def test_a_record_with_an_absolute_path_in_any_field_fails(field, bad):
    record = _record()
    record[field] = bad
    with pytest.raises(VoiceError):
        assert_no_private_paths(record)


def test_absolute_conversion_from_a_converter_fails_before_the_call(tmp_path):
    kwargs, _c, transcriber, _l, record_path = _setup(tmp_path)

    class AbsConverter:
        def __call__(self, audio_path, wav_path):
            Path(wav_path).write_bytes(_wav_bytes(1.0))
            return _wav_bytes(1.0), "ffmpeg -i " + "\\".join([_PROFILE_WIN, "x.m4a"]) + " -ac 1 x.wav"

    kwargs["converter"] = AbsConverter()
    with pytest.raises(VoiceError):
        transcribe_recording(**kwargs)
    assert transcriber.calls == [] and not record_path.exists()


# -- the one-time rewrite script ------------------------------------------------------

def _old_record(root):
    return {"text": TEXT, "audio_sha256": EXPECTED_AUDIO_SHA256,
            "wav_sha256": sha256_tag(b"wav"),
            "conversion": f"ffmpeg -y -i {root}\\checkins\\Flight_Director_command.m4a "
                          f"-ac 1 -ar 24000 -sample_fmt s16 {root}\\odin\\voice\\Flight_Director_command.wav",
            "model": "muse-voice-transcribe-1.0", "endpoint": ENDPOINT,
            "utc": "2026-10-29T20:03:19.011Z"}


def test_rewrite_changes_only_conversion_by_replacing_the_root():
    from odin.devtools.rewrite_m6_record import rewritten

    root = "\\".join([_PROFILE_WIN, "Documents", "ad-astra-simul", "odin"])
    old = _old_record(root)
    new = rewritten(old, root)
    for field in old:
        if field != "conversion":
            assert new[field] == old[field], field
    assert new["conversion"] == old["conversion"].replace(root, ".")
    assert _SOMEONE not in new["conversion"]


def test_rewrite_refuses_a_record_whose_hash_is_not_the_original(tmp_path):
    from odin.devtools.rewrite_m6_record import run

    record_path = tmp_path / "flight_director_command.json"
    record_path.write_bytes(canonical_json(_old_record(str(tmp_path))))
    before = record_path.read_bytes()
    with pytest.raises(RuntimeError):
        run(record_path=record_path, root=str(tmp_path))
    assert record_path.read_bytes() == before


def test_rewrite_writes_new_record_and_sidecar(tmp_path):
    from odin.devtools.rewrite_m6_record import run

    record_path = tmp_path / "flight_director_command.json"
    old = _old_record(str(tmp_path))
    record_path.write_bytes(canonical_json(old))
    digest = sha256_tag(record_path.read_bytes())
    new_record, sidecar = run(record_path=record_path, root=str(tmp_path),
                              expected_sha256=digest)
    assert json.loads(record_path.read_text(encoding="utf-8")) == new_record
    assert record_path.read_bytes() == canonical_json(new_record)
    written_sidecar = json.loads((tmp_path / "flight_director_command.sha256.json")
                                 .read_text(encoding="utf-8"))
    assert written_sidecar == sidecar
    assert sidecar["derived_from"] == digest
    assert sidecar["sha256"] == sha256_tag(record_path.read_bytes())
    assert "conversion" in sidecar["note"]


def test_frozen_files_six_schemas_and_models_unchanged():
    record = json.loads((REPO_ROOT / "odin" / "instructions" / "system_prompt.sha256.json").read_text(encoding="utf-8"))
    files = {
        record["sha256"]: REPO_ROOT / "odin" / "instructions" / "system_prompt.md",
        record["template_sha256"]: REPO_ROOT / "odin" / "instructions" / "template.md",
        record["prompt_template_sha256"]: REPO_ROOT / "odin" / "loop" / "prompt.py",
    }
    for expected, path in files.items():
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == expected, path
    frozen = json.loads((REPO_ROOT / "config" / "frozen.json").read_text(encoding="utf-8"))
    for rel, expected in frozen["schemas"].items():
        assert "sha256:" + hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest() == expected, rel
    # M17: each model's block checked against its frozen.json entry,
    # so a model can be added with its entry without breaking this.
    from freeze_guard import assert_model_blocks_match_frozen
    assert_model_blocks_match_frozen(REPO_ROOT / "config" / "models.yaml",
                                     REPO_ROOT / "config" / "frozen.json")
