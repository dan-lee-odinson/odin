"""Transcribe the Director's recorded check-in, once (M6, U44).

Meta's documentation (https://dev.meta.ai/docs/speech-to-text, and the
cookbook recipe it links) gives: model `muse-voice-transcribe-1.0`, a
recording posted as multipart/form-data to
POST https://api.meta.ai/v1/asr/transcribe with an Authorization Bearer
header, a JSON `request` part {mode, model, audioEncoding: "WAV"} and
the audio as a second part, priced per audio hour. The recording is
.m4a, so it is converted to a mono 16-bit WAV at 24 kHz with ffmpeg
first (Meta's recipe's own step). The key comes only from META_API_KEY.

The recording's SHA-256 is checked before anything is sent and any
other file is refused. The price (config/prices.yaml `voice_transcribe`,
per audio hour, META stop) is reserved through the spend meter before
the call and settled after, from the duration Meta reports when it
gives one and otherwise the WAV's own duration, measured from the file;
the spend record names which it used. The frozen record refuses to
overwrite an existing one.
"""
import argparse
import io
import json
import math
import os
import re
import subprocess
import urllib.request
import wave
from pathlib import Path

import yaml

from odin.loop.canonical import canonical_json, sha256_tag
from odin.loop.loop import _http_json, utc_now
from odin.loop.validate import validate_against_schema
from odin.spend.meter import SpendMeter

REPO_ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = "https://api.meta.ai/v1/asr/transcribe"
DEFAULT_MODEL = "muse-voice-transcribe-1.0"
CONFIG_NAME = "voice_transcribe"
EXPECTED_AUDIO_SHA256 = "sha256:a4f3fb3deaadf01883ab21f8a463057202cca2bd480bbcc4e7e841c9af6508ff"
MODE = "PUSH_TO_TALK"


class VoiceError(RuntimeError):
    """The voice path refused, before or instead of sending anything."""


class HashMismatchError(VoiceError):
    """The recording is not the Director's pinned recording."""


class RecordExistsError(VoiceError):
    """The frozen record already exists and is never overwritten."""


class PriceError(VoiceError):
    """The voice_transcribe price entry is missing or malformed."""


class SpendRefusedError(VoiceError):
    """The spend meter refused the transcription call."""


def verify_recording(audio_path, expected_sha256=EXPECTED_AUDIO_SHA256) -> str:
    """The recording's hash, checked before anything is sent."""
    actual = sha256_tag(Path(audio_path).read_bytes())
    if actual != expected_sha256:
        raise HashMismatchError(
            f"recording hashes to {actual}, expected {expected_sha256}; refusing to send it")
    return actual


def load_voice_price(prices_path=None) -> dict:
    """The voice_transcribe entry, or PriceError. Never a default."""
    path = Path(prices_path) if prices_path else REPO_ROOT / "config" / "prices.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entry = doc.get(CONFIG_NAME)
    if not isinstance(entry, dict):
        raise PriceError(f"{path} has no {CONFIG_NAME!r} entry; refusing the call")
    model = entry.get("model")
    per_hour = entry.get("per_audio_hour")
    stop = entry.get("stop")
    if not isinstance(model, str) or not model:
        raise PriceError(f"{CONFIG_NAME}.model missing or not a string; refusing the call")
    if isinstance(per_hour, bool) or not isinstance(per_hour, (int, float)) or not per_hour > 0:
        raise PriceError(f"{CONFIG_NAME}.per_audio_hour missing or not a positive number; refusing the call")
    if stop != "META":
        raise PriceError(f"{CONFIG_NAME}.stop must be 'META'; refusing the call")
    return {"model": model, "per_audio_hour": float(per_hour), "stop": stop}


def wav_duration_s(wav_bytes: bytes) -> float:
    """The WAV's duration, measured from the file itself."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.getnframes() / w.getframerate()


def _relative_to_root(path) -> str:
    """`path` relative to the workspace root, written with a leading
    dot, so no record ever holds an absolute or private path."""
    try:
        rel = Path(path).resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return str(path)
    return "." + os.sep + str(rel)


def conversion_command(audio_path, wav_path) -> list:
    """Meta's recipe's conversion: mono 16-bit WAV at 24 kHz, run from
    the workspace root with paths relative to it."""
    return ["ffmpeg", "-y", "-i", _relative_to_root(audio_path), "-ac", "1",
            "-ar", "24000", "-sample_fmt", "s16", _relative_to_root(wav_path)]


_ABS_PATH = re.compile(r"(?i)([A-Z]:\\|\\\\|/Users/|/home/|\\Users\\)")


def assert_no_private_paths(record: dict) -> None:
    """Refuse a record holding an absolute path or a user-profile
    folder in any field (the Director's rewrite ruling)."""
    home = str(Path.home())
    for field, value in record.items():
        if not isinstance(value, str):
            continue
        if _ABS_PATH.search(value) or home in value:
            raise VoiceError(f"record field {field!r} holds an absolute or private path; refusing")


def ffmpeg_converter(audio_path, wav_path):
    """Convert with ffmpeg (the Director's window provides it)."""
    command = conversion_command(audio_path, wav_path)
    done = subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT)
    if done.returncode != 0:
        raise VoiceError(f"ffmpeg conversion failed: {done.stderr.strip()[:300]}")
    return Path(wav_path).read_bytes(), " ".join(command)


def _http_post_multipart(url, headers, body, content_type, timeout):
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": content_type, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:
            return exc.code, {}


def meta_transcriber(http_post=None, timeout_s=300):
    """The real transcriber: Meta's one-shot endpoint, key from
    META_API_KEY only. Returns a callable like the tests' fakes."""
    post = http_post or _http_post_multipart

    def transcribe(wav_bytes, *, model, endpoint):
        key = os.environ.get("META_API_KEY")
        if not key:
            raise VoiceError("META_API_KEY is not set; refusing to call Meta")
        boundary = "odin-voice-boundary"
        request_part = json.dumps({"mode": MODE, "model": model, "audioEncoding": "WAV"})
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="request"\r\n',
            b"Content-Type: application/json\r\n\r\n",
            request_part.encode(), b"\r\n",
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="audio"; filename="audio.wav"\r\n',
            b"Content-Type: audio/wav\r\n\r\n",
            wav_bytes, b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        status, payload = post(endpoint, {"Authorization": f"Bearer {key}"}, body,
                               f"multipart/form-data; boundary={boundary}", timeout_s)
        if status >= 400:
            raise VoiceError(f"Meta transcription failed with HTTP {status}: {payload}")
        return payload

    return transcribe


def _response_text(response) -> str:
    text = response.get("transcript")
    if isinstance(text, str):
        return text
    turns = response.get("turns") or []
    joined = " ".join(str(t.get("transcript", "")) for t in turns).strip()
    if joined:
        return joined
    raise VoiceError(f"Meta response carries no transcript: {sorted(response)[:5]}")


def _sidecar_path(record_path) -> Path:
    return record_path.with_suffix(".sha256.json")


def transcribe_recording(*, audio_path, record_path, wav_path=None, meter,
                         prices_path=None, converter=None, transcriber=None,
                         expected_sha256=EXPECTED_AUDIO_SHA256, now_fn=None) -> dict:
    """Transcribe once and write the frozen record. Refusals, in order:
    wrong recording, existing record, missing/malformed price, missing
    key, spend stop — all before anything is sent."""
    audio_path, record_path = Path(audio_path), Path(record_path)
    audio_sha256 = verify_recording(audio_path, expected_sha256)
    if record_path.exists() or _sidecar_path(record_path).exists():
        raise RecordExistsError(f"frozen record {record_path} already exists; refusing to overwrite it")
    price = load_voice_price(prices_path)
    if transcriber is None:
        transcriber = meta_transcriber()
        if not os.environ.get("META_API_KEY"):
            raise VoiceError("META_API_KEY is not set; refusing to call Meta")
    converter = converter or ffmpeg_converter
    wav_path = Path(wav_path) if wav_path else record_path.parent / (audio_path.stem + ".wav")
    wav_bytes, conversion = converter(audio_path, wav_path)
    assert_no_private_paths({"conversion": conversion})
    wav_sha256 = sha256_tag(wav_bytes)
    wav_seconds = wav_duration_s(wav_bytes)
    # Meta bills per audio hour, rounded down to whole seconds.
    reserved_usd = math.floor(wav_seconds) / 3600 * price["per_audio_hour"]
    reservation = meter.reserve(config=CONFIG_NAME, input_tokens=0, max_output_tokens=0,
                                turn_id=1, call_index=1, reserved_usd=reserved_usd)
    if reservation is None:
        raise SpendRefusedError("spend meter refused the transcription (META stop)")
    response = transcriber(wav_bytes, model=price["model"], endpoint=ENDPOINT)
    reported_ms = response.get("audioDurationMs")
    if isinstance(reported_ms, (int, float)) and not isinstance(reported_ms, bool) and reported_ms > 0:
        actual_usd = math.floor(reported_ms / 1000) / 3600 * price["per_audio_hour"]
        duration_source = "META_REPORT"
    else:
        actual_usd = reserved_usd
        duration_source = "WAV_FILE"
    reservation.settle(actual_usd=actual_usd, duration_source=duration_source)
    record = {
        "text": _response_text(response),
        "audio_sha256": audio_sha256,
        "wav_sha256": wav_sha256,
        "conversion": conversion,
        "model": price["model"],
        "endpoint": ENDPOINT,
        "utc": (now_fn or utc_now)(),
    }
    assert_no_private_paths(record)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with record_path.open("xb") as handle:
        handle.write(canonical_json(record))
    sidecar = {"file": record_path.name, "sha256": sha256_tag(record_path.read_bytes()),
               "frozen": True, "frozen_at_utc": record["utc"]}
    with _sidecar_path(record_path).open("xb") as handle:
        handle.write((json.dumps(sidecar, indent=2) + "\n").encode("utf-8"))
    return record


def build_checkin_body(record: dict) -> dict:
    """The frozen record as a POST /checkin body. A recording's check-in
    is RECORDED, never TEXT."""
    if record.get("audio_sha256") != EXPECTED_AUDIO_SHA256:
        raise ValueError("record's audio_sha256 is not the Director's pinned recording")
    body = {"text": record["text"], "audio_sha256": record["audio_sha256"],
            "source": "RECORDED", "utc": record["utc"]}
    errors = validate_against_schema("checkin.schema.json", body)
    if errors:
        raise ValueError("check-in body fails checkin.schema.json: " + "; ".join(errors[:3]))
    return body


checkin_body = build_checkin_body


def post_checkin(body: dict, *, harness_url, transport=None) -> int:
    """Deliver the body to the harness (A-1). Returns the HTTP status."""
    errors = validate_against_schema("checkin.schema.json", body)
    if errors:
        raise ValueError("check-in body fails checkin.schema.json: " + "; ".join(errors[:3]))
    status, _ = _http_json("POST", f"{harness_url.rstrip('/')}/checkin", body,
                           transport=transport)
    return status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", default=str(REPO_ROOT / "checkins" / "Flight_Director_command.m4a"))
    parser.add_argument("--record", default=str(Path(__file__).parent / "flight_director_command.json"))
    parser.add_argument("--wav", default=None)
    parser.add_argument("--prices", default=str(REPO_ROOT / "config" / "prices.yaml"))
    parser.add_argument("--ledger", default=str(Path(__file__).parent / "transcribe.spend.jsonl"))
    parser.add_argument("--checkin-url", default=None,
                        help="also POST the check-in body to this harness URL")
    args = parser.parse_args(argv)
    meter = SpendMeter(ledger_path=args.ledger, prices_path=args.prices)
    record = transcribe_recording(
        audio_path=args.audio, record_path=args.record, wav_path=args.wav,
        meter=meter, prices_path=args.prices)
    print(f"record: {args.record}")
    print(f"record sha256: {sha256_tag(Path(args.record).read_bytes())}")
    print(f"text: {record['text']}")
    if args.checkin_url:
        status = post_checkin(build_checkin_body(record), harness_url=args.checkin_url)
        print(f"POST /checkin -> {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
