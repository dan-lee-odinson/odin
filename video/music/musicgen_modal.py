"""MusicGen on Modal for ODIN's demo video.

Commands (run them yourself; see README.md):
    modal run musicgen_modal.py::takes
    modal run musicgen_modal.py::extend --take-path out\\take-001-seed1234.wav
    modal run musicgen_modal.py::compose --take-path out\\take-001-seed3100.wav

Only the WAV bytes come back to this machine. Model weights are downloaded
inside Modal's container into a Modal Volume and reused on later runs.
Modal reads MODAL_TOKEN_ID / MODAL_TOKEN_SECRET from your environment;
no credential is stored in any file here.

The top half of this file is plain stdlib logic (prompt, seeds, naming,
sidecar JSON, WAV hash, extension planning) so it can be unit-tested
locally with no Modal, GPU, torch or network. Torch/AudioCraft are only
imported inside the Modal container.
"""
import hashlib
import io
import json
import math
import struct
import wave
from pathlib import Path

# --------------------------------------------------------------------------
# Pins. The Modal image is built in the cloud from exactly these versions.
# --------------------------------------------------------------------------
AUDIOCRAFT_VERSION = "1.3.0"
TORCH_VERSION = "2.1.0"  # AudioCraft 1.3.0 requires torch==2.1.0
TORCHAUDIO_VERSION = "2.1.0"  # and torchaudio>=2.0.0,<2.1.2
SOUNDFILE_VERSION = "0.12.1"
TRANSFORMERS_VERSION = "4.44.2"  # 4.x: runs on torch 2.1 (5.x does not)

# The cloud image's pip packages, in one place so tests and the resolver
# check see exactly what Modal will install. numpy<2 because torch 2.1
# is built against NumPy 1.x.
IMAGE_PIP_PACKAGES = (
    f"audiocraft=={AUDIOCRAFT_VERSION}",
    f"torch=={TORCH_VERSION}",
    f"torchaudio=={TORCHAUDIO_VERSION}",
    f"soundfile=={SOUNDFILE_VERSION}",
    f"transformers=={TRANSFORMERS_VERSION}",
    "numpy<2",
)

# av==11.0.0 (pinned exactly by AudioCraft) ships no wheels, only an
# sdist, so the image needs a C toolchain and FFmpeg's dev libraries to
# build it.
IMAGE_APT_PACKAGES = (
    "ffmpeg", "libsndfile1", "build-essential", "pkg-config",
    "libavformat-dev", "libavcodec-dev", "libavdevice-dev",
    "libavutil-dev", "libavfilter-dev", "libswscale-dev",
    "libswresample-dev",
)

DEFAULT_MODEL = "facebook/musicgen-stereo-large"
MELODY_MODEL = "facebook/musicgen-stereo-melody-large"
ALLOWED_MODELS = ("facebook/musicgen-stereo-large",
                  "facebook/musicgen-stereo-medium",
                  MELODY_MODEL)
DEFAULT_PROMPT_FILE = "prompts/theme.txt"
DEFAULT_TOTAL_SECONDS = 180.0
DEFAULT_BPM = 108.0
REPRISE_NOMINAL_SECONDS = 30.0
SAMPLE_RATE = 32000
CHANNELS = 2
GPU_TYPE = "A10G"
TIMEOUT_SECONDS = 30 * 60  # a stuck job stops itself after 30 minutes
MAX_WINDOW_SECONDS = 30.0  # MusicGen generates about 30 s at a time
DEFAULT_OVERLAP_SECONDS = 10.0

REQUIRED_SIDECAR_FIELDS = (
    "file", "model", "prompt", "seed", "duration_seconds",
    "sample_rate_hz", "channels", "audiocraft_version", "gpu",
    "sha256", "source_take",
)

try:
    import modal
except Exception:  # local unit tests run without a usable Modal client
    modal = None


# --------------------------------------------------------------------------
# Pure local logic (unit-tested, no third-party imports)
# --------------------------------------------------------------------------
def read_prompt(path):
    """Return the prompt text in *path*, stripped. Empty/missing is an error."""
    text = Path(path).read_text(encoding="utf-8")
    prompt = text.strip()
    if not prompt:
        raise ValueError(f"prompt file is empty: {path}")
    return prompt


def validate_model(model):
    if model not in ALLOWED_MODELS:
        raise ValueError(
            f"model must be one of {list(ALLOWED_MODELS)}, got {model!r}")
    return model


def derive_seeds(base_seed, count):
    """One distinct, reproducible seed per take: base, base+1, ..."""
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    seeds = [int(base_seed) + i for i in range(count)]
    validate_seeds(seeds)
    return seeds


def validate_seeds(seeds):
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError(f"seeds must be non-empty and distinct, got {seeds}")
    return list(seeds)


def unique_output_path(directory, filename):
    """A path inside *directory* that does not exist yet (never overwrites)."""
    directory = Path(directory)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = Path(filename).stem, Path(filename).suffix
    n = 2
    while True:
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wav_info_from_bytes(data):
    """Sample rate, channels and duration of a PCM WAV held in memory."""
    with wave.open(io.BytesIO(data), "rb") as w:
        rate = w.getframerate()
        frames = w.getnframes()
        return {"sample_rate_hz": rate, "channels": w.getnchannels(),
                "duration_seconds": frames / rate if rate else 0.0}


def encode_pcm16_wav_bytes(samples, sample_rate=SAMPLE_RATE, channels=CHANNELS):
    """Encode interleaved float samples as a 16-bit PCM WAV.

    Samples are clamped to [-1, 1] (never wrapped). This is the exact
    encoding the Modal container writes, so every take is readable by
    Python's wave module -- a float WAV from torchaudio.save is not.
    """
    samples = list(samples)
    if channels < 1 or len(samples) % channels != 0:
        raise ValueError(
            f"{len(samples)} samples do not make whole {channels}-channel frames")
    if not samples:
        raise ValueError("no samples to encode")
    frames = b"".join(
        struct.pack("<h", int(round(max(-1.0, min(1.0, float(s))) * 32767)))
        for s in samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(frames)
    return buf.getvalue()


def validate_output_wav(info):
    """Only the contracted output is accepted: 32 kHz stereo."""
    if info["sample_rate_hz"] != SAMPLE_RATE:
        raise ValueError(f"expected {SAMPLE_RATE} Hz, got {info['sample_rate_hz']}")
    if info["channels"] != CHANNELS:
        raise ValueError(f"expected {CHANNELS} channels, got {info['channels']}")
    if info["duration_seconds"] <= 0:
        raise ValueError("WAV has no audio frames")
    return info


def build_sidecar(*, wav_bytes, file, model, prompt, seed, duration_seconds,
                  audiocraft_version, gpu, source_take=None):
    """The JSON that sits beside every WAV. Hash is over the exact WAV bytes."""
    try:
        info = wav_info_from_bytes(wav_bytes)
        sample_rate, channels = info["sample_rate_hz"], info["channels"]
    except Exception:
        sample_rate, channels = SAMPLE_RATE, CHANNELS
    return {
        "file": file,
        "model": validate_model(model),
        "prompt": prompt,
        "seed": int(seed),
        "duration_seconds": round(float(duration_seconds), 3),
        "sample_rate_hz": int(sample_rate),
        "channels": int(channels),
        "audiocraft_version": audiocraft_version,
        "gpu": gpu,
        "sha256": sha256_bytes(wav_bytes),
        "source_take": source_take,
    }


def validate_sidecar(sidecar, wav_bytes=None):
    """Raise ValueError if a sidecar is incomplete or its hash does not match."""
    missing = [f for f in REQUIRED_SIDECAR_FIELDS if f not in sidecar]
    if missing:
        raise ValueError(f"sidecar missing fields: {missing}")
    if not sidecar["prompt"] or not sidecar["gpu"]:
        raise ValueError("sidecar prompt and gpu must be non-empty")
    digest = sidecar["sha256"]
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("sidecar sha256 must be a 64-char hex digest")
    if wav_bytes is not None and sha256_bytes(wav_bytes) != digest:
        raise ValueError("WAV bytes do not match sidecar sha256")
    return sidecar


def plan_extension(current_seconds, target_seconds,
                   window_seconds=MAX_WINDOW_SECONDS,
                   overlap_seconds=DEFAULT_OVERLAP_SECONDS):
    """Overlapping continuation windows from current length to target length.

    Each step re-feeds the last `overlap_seconds` of audio so far as the
    continuation prompt, generates at most `window_seconds`, and appends
    only the audio after that prompt. Nothing restarts from scratch.
    """
    if target_seconds <= current_seconds:
        raise ValueError(
            f"target ({target_seconds}s) must exceed current ({current_seconds}s)")
    if not 0 < overlap_seconds < window_seconds:
        raise ValueError("overlap must be between 0 and the window length")
    if window_seconds > MAX_WINDOW_SECONDS:
        raise ValueError(f"window must be <= {MAX_WINDOW_SECONDS}s")
    steps, reached = [], float(current_seconds)
    while reached < target_seconds - 1e-9:
        generation = min(float(window_seconds),
                         overlap_seconds + (target_seconds - reached))
        steps.append({
            "prompt_seconds": float(overlap_seconds),
            "generation_seconds": round(generation, 3),
            "new_seconds": round(generation - overlap_seconds, 3),
            "start_seconds": round(reached, 3),
            "end_seconds": round(reached + generation - overlap_seconds, 3),
        })
        reached += generation - overlap_seconds
    return steps


def bar_seconds(bpm):
    """One bar is four beats."""
    if bpm <= 0:
        raise ValueError(f"bpm must be positive, got {bpm}")
    return 240.0 / float(bpm)


def plan_composition(total_seconds=DEFAULT_TOTAL_SECONDS, theme_seconds=30.0,
                     bpm=DEFAULT_BPM,
                     reprise_nominal_seconds=REPRISE_NOMINAL_SECONDS,
                     window_seconds=MAX_WINDOW_SECONDS,
                     overlap_seconds=DEFAULT_OVERLAP_SECONDS):
    """Section plan for compose: theme, development, melody reprise.

    The reprise lasts a whole number of bars (about 30 s, never more
    than one 30 s generation), starts on a bar line, and overlaps the
    development by a one-bar equal-power crossfade. The fade-out covers
    the last two bars.
    """
    bar = bar_seconds(bpm)
    if theme_seconds <= 0:
        raise ValueError("theme must have a positive length")
    reprise_bars = int(reprise_nominal_seconds // bar)
    if reprise_bars < 1:
        raise ValueError("reprise must be at least one bar long")
    reprise_span = reprise_bars * bar
    if total_seconds <= theme_seconds + reprise_span:
        raise ValueError(
            f"total ({total_seconds}s) must exceed theme + reprise "
            f"({theme_seconds + reprise_span:.1f}s)")
    crossfade_start = round(
        math.floor((total_seconds - reprise_span) / bar + 1e-9) * bar, 6)
    generation = round(total_seconds - crossfade_start, 6)
    if generation > MAX_WINDOW_SECONDS:
        raise ValueError(
            f"reprise would need a {generation:.1f}s generation "
            f"(> {MAX_WINDOW_SECONDS}s); adjust total or bpm")
    crossfade_end = round(crossfade_start + bar, 6)
    return {
        "bpm": float(bpm),
        "bar_seconds": bar,
        "total_seconds": float(total_seconds),
        "theme": {"start_seconds": 0.0,
                  "end_seconds": round(float(theme_seconds), 6)},
        "development": {"start_seconds": round(float(theme_seconds), 6),
                        "end_seconds": crossfade_end},
        "reprise": {"start_seconds": crossfade_start,
                    "end_seconds": round(float(total_seconds), 6),
                    "generation_seconds": generation},
        "crossfade": {"start_seconds": crossfade_start,
                      "end_seconds": crossfade_end,
                      "duration_seconds": bar},
        "fade_out": {"start_seconds": round(total_seconds - 2 * bar, 6),
                     "end_seconds": round(float(total_seconds), 6),
                     "duration_seconds": 2 * bar},
        "development_windows": plan_extension(
            theme_seconds, crossfade_end, window_seconds, overlap_seconds),
    }


def equal_power_gains(count):
    """(fade-out, fade-in) gains with a^2 + b^2 == 1 at every point."""
    if count < 1:
        raise ValueError("crossfade must have at least one sample")
    if count == 1:
        return [math.sqrt(0.5)], [math.sqrt(0.5)]
    out_g, in_g = [], []
    for i in range(count):
        angle = (math.pi / 2.0) * (i / (count - 1))
        out_g.append(math.cos(angle))
        in_g.append(math.sin(angle))
    return out_g, in_g


CODEC_FRAME_RATE = 50  # MusicGen's codec: 50 frames/s at 32 kHz


def codec_frame_samples(sample_rate=SAMPLE_RATE):
    """Samples per codec frame. Generation lengths are whole frames."""
    if sample_rate % CODEC_FRAME_RATE != 0:
        raise ValueError(
            f"sample rate {sample_rate} is not divisible by the codec "
            f"frame rate {CODEC_FRAME_RATE}")
    return sample_rate // CODEC_FRAME_RATE


def ceil_to_codec_frames(samples, sample_rate=SAMPLE_RATE):
    if samples < 0:
        raise ValueError(f"samples must be >= 0, got {samples}")
    frame = codec_frame_samples(sample_rate)
    return int(((samples + frame - 1) // frame) * frame)


def requested_generation_seconds(needed_samples, sample_rate=SAMPLE_RATE,
                                 extra_frames=1):
    """Ask for a little more than needed, rounded up to whole frames."""
    if needed_samples < 1:
        raise ValueError("needed_samples must be positive")
    asked = (ceil_to_codec_frames(needed_samples, sample_rate)
             + extra_frames * codec_frame_samples(sample_rate))
    return asked / sample_rate


def _check_channels(channel_samples):
    channels = [list(c) for c in channel_samples]
    if not channels:
        raise ValueError("no channels")
    lengths = {len(c) for c in channels}
    if len(lengths) != 1:
        raise ValueError(f"ragged channels: lengths {sorted(lengths)}")
    return channels


def fit_to_length(channel_samples, target_samples):
    """Trim each channel to exactly target_samples, zero-padding if short.

    This is only the last-resort fit: the cloud code generates any real
    shortfall before joining, so padding should never be heard.
    """
    if target_samples < 0:
        raise ValueError("target_samples must be >= 0")
    out = []
    for channel in _check_channels(channel_samples):
        fitted = channel[:target_samples]
        out.append(fitted + [0.0] * (target_samples - len(fitted)))
    return out


def apply_fade_out(channel_samples, fade_start_samples):
    """Linear fade to zero, built from the track's actual length."""
    channels = _check_channels(channel_samples)
    actual = len(channels[0])
    if fade_start_samples < 0 or fade_start_samples >= actual:
        raise ValueError(
            f"fade start {fade_start_samples} outside track of {actual}")
    count = actual - fade_start_samples
    out = []
    for channel in channels:
        faded = list(channel)
        for i in range(count):
            gain = 1.0 - (i / (count - 1)) if count > 1 else 0.0
            faded[fade_start_samples + i] = channel[fade_start_samples + i] * gain
        out.append(faded)
    return out


def assemble_composition(development, reprise, *, crossfade_start_samples,
                         bar_samples, total_samples, fade_start_samples=None):
    """Join a development track and a reprise into exactly total_samples.

    Sections may come back a few samples short or long: each is fitted
    to its planned length first, then joined with a one-bar equal-power
    crossfade starting at crossfade_start_samples.
    """
    if bar_samples <= 0:
        raise ValueError("bar_samples must be positive")
    if crossfade_start_samples < 0 or \
            crossfade_start_samples + bar_samples > total_samples:
        raise ValueError("crossfade must lie inside the total length")
    dev, rep = _check_channels(development), _check_channels(reprise)
    if len(dev) != len(rep):
        raise ValueError(
            f"channel mismatch: development {len(dev)}, reprise {len(rep)}")
    dev = fit_to_length(dev, crossfade_start_samples + bar_samples)
    rep = fit_to_length(rep, total_samples - crossfade_start_samples)
    final = []
    for d, r in zip(dev, rep):
        mixed = crossfade_samples(d[crossfade_start_samples:], r[:bar_samples])
        final.append(d[:crossfade_start_samples] + mixed + r[bar_samples:])
    if fade_start_samples is not None:
        final = apply_fade_out(final, fade_start_samples)
    return final


def encode_channels_pcm16(channels, sample_rate=SAMPLE_RATE):
    """Interleave per-channel float samples and encode as 16-bit PCM."""
    channels = _check_channels(channels)
    interleaved = [s for frame in zip(*channels) for s in frame]
    return encode_pcm16_wav_bytes(interleaved, sample_rate=sample_rate,
                                  channels=len(channels))


def decode_pcm16_channels(wav_bytes):
    """Decode a 16-bit PCM WAV into (per-channel float samples, rate)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("expected a 16-bit PCM WAV")
        n_channels, rate = w.getnchannels(), w.getframerate()
        raw = w.readframes(w.getnframes())
    values = struct.unpack(f"<{len(raw) // 2}h", raw)
    channels = [[v / 32767.0 for v in values[i::n_channels]]
                for i in range(n_channels)]
    return channels, rate


def join_section_bytes(development_bytes, reprise_bytes, plan):
    """Join two saved section WAVs per the plan. Pure stdlib, no GPU."""
    dev, dev_rate = decode_pcm16_channels(development_bytes)
    rep, rep_rate = decode_pcm16_channels(reprise_bytes)
    if dev_rate != SAMPLE_RATE or rep_rate != SAMPLE_RATE:
        raise ValueError("sections must be 32 kHz WAVs")
    sr = SAMPLE_RATE
    final = assemble_composition(
        dev, rep,
        crossfade_start_samples=int(round(
            plan["crossfade"]["start_seconds"] * sr)),
        bar_samples=int(round(plan["crossfade"]["duration_seconds"] * sr)),
        total_samples=int(round(plan["total_seconds"] * sr)),
        fade_start_samples=int(round(plan["fade_out"]["start_seconds"] * sr)))
    return encode_channels_pcm16(final, sr)


def crossfade_samples(fade_out_samples, fade_in_samples):
    """Equal-power crossfade of two equal-length sample sequences."""
    a, b = list(fade_out_samples), list(fade_in_samples)
    if len(a) != len(b):
        raise ValueError("crossfade sides must have the same length")
    out_g, in_g = equal_power_gains(len(a))
    return [x * ga + y * gb for x, y, ga, gb in zip(a, b, out_g, in_g)]


REQUIRED_SECTION_FIELDS = ("name", "start_seconds", "end_seconds",
                           "prompt_file", "prompt", "model", "seeds")
REQUIRED_COMPOSE_FIELDS = (
    "file", "models", "seed", "duration_seconds", "sample_rate_hz",
    "channels", "audiocraft_version", "gpu", "sha256", "source_take",
    "sections", "crossfade", "fade_out",
)


def build_compose_sidecar(*, wav_bytes, file, sections, crossfade, fade_out,
                          audiocraft_version, gpu, source_take, base_seed):
    """JSON for a composed piece: every section, join and hash recorded."""
    try:
        info = wav_info_from_bytes(wav_bytes)
        sample_rate, channels = info["sample_rate_hz"], info["channels"]
        duration = info["duration_seconds"]
    except Exception:
        sample_rate, channels, duration = SAMPLE_RATE, CHANNELS, 0.0
    return {
        "file": file,
        "models": sorted({s["model"] for s in sections}),
        "seed": int(base_seed),
        "duration_seconds": round(float(duration), 3),
        "sample_rate_hz": int(sample_rate),
        "channels": int(channels),
        "audiocraft_version": audiocraft_version,
        "gpu": gpu,
        "sha256": sha256_bytes(wav_bytes),
        "source_take": source_take,
        "sections": sections,
        "crossfade": crossfade,
        "fade_out": fade_out,
    }


def validate_compose_sidecar(sidecar, wav_bytes=None):
    missing = [f for f in REQUIRED_COMPOSE_FIELDS if f not in sidecar]
    if missing:
        raise ValueError(f"compose sidecar missing fields: {missing}")
    if not sidecar["sections"]:
        raise ValueError("compose sidecar has no sections")
    for section in sidecar["sections"]:
        absent = [f for f in REQUIRED_SECTION_FIELDS if f not in section]
        if absent:
            raise ValueError(f"section missing fields: {absent}")
    if wav_bytes is not None and sha256_bytes(wav_bytes) != sidecar["sha256"]:
        raise ValueError("WAV bytes do not match sidecar sha256")
    return sidecar


def save_compose_output(out_dir, stem, wav_bytes, *, sections, crossfade,
                        fade_out, audiocraft_version, gpu, source_take,
                        base_seed):
    """Write a composed WAV plus its JSON. Never overwrites."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = unique_output_path(out_dir, f"{stem}.wav")
    while wav_path.with_suffix(".json").exists():
        wav_path = unique_output_path(out_dir, wav_path.name)
    sidecar = build_compose_sidecar(
        wav_bytes=wav_bytes, file=wav_path.name, sections=sections,
        crossfade=crossfade, fade_out=fade_out,
        audiocraft_version=audiocraft_version, gpu=gpu,
        source_take=source_take, base_seed=base_seed)
    validate_compose_sidecar(sidecar, wav_bytes=wav_bytes)
    wav_path.write_bytes(wav_bytes)
    json_path = wav_path.with_suffix(".json")
    json_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return wav_path, json_path


def save_output(out_dir, stem, wav_bytes, *, model, prompt, seed,
                duration_seconds, audiocraft_version, gpu, source_take=None):
    """Write a WAV plus its JSON sidecar. Never overwrites an earlier take."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = unique_output_path(out_dir, f"{stem}.wav")
    while wav_path.with_suffix(".json").exists():
        wav_path = unique_output_path(out_dir, wav_path.name)
    sidecar = build_sidecar(
        wav_bytes=wav_bytes, file=wav_path.name, model=model, prompt=prompt,
        seed=seed, duration_seconds=duration_seconds,
        audiocraft_version=audiocraft_version, gpu=gpu,
        source_take=source_take)
    validate_sidecar(sidecar, wav_bytes=wav_bytes)
    wav_path.write_bytes(wav_bytes)
    json_path = wav_path.with_suffix(".json")
    json_path.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return wav_path, json_path


def _local_path(path_str):
    """Resolve a CLI path against the cwd first, then this script's folder."""
    p = Path(path_str)
    if p.exists() or p.is_absolute():
        return p
    return Path(__file__).resolve().parent / p


# --------------------------------------------------------------------------
# Modal app. The image and the weights live in the cloud, never locally.
# --------------------------------------------------------------------------
if modal is not None:
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install(*IMAGE_APT_PACKAGES)
        .pip_install(*IMAGE_PIP_PACKAGES)
        .env({"HF_HOME": "/models/huggingface", "TORCH_HOME": "/models/torch"})
    )
    weights = modal.Volume.from_name("odin-musicgen-weights",
                                     create_if_missing=True)
    app = modal.App("odin-musicgen")
else:
    image = weights = app = None


def _remote(fn):
    """Apply the Modal function decorator when Modal is available."""
    if modal is None:
        return fn
    return app.function(image=image, gpu=GPU_TYPE, timeout=TIMEOUT_SECONDS,
                        volumes={"/models": weights})(fn)


def _load_model(model_name):
    """Inside the container only: load MusicGen, caching weights in the Volume."""
    import torch
    from audiocraft.models import MusicGen

    model = MusicGen.get_pretrained(model_name)
    try:
        weights.commit()
    except Exception:
        pass
    gpu = (torch.cuda.get_device_name(0) if torch.cuda.is_available()
           else "no GPU visible")
    return model, gpu


def _encode_wav(audio_tensor, sample_rate):
    """Encode one (channels, samples) tensor as 16-bit PCM WAV bytes."""
    audio = audio_tensor.detach().cpu()
    interleaved = audio.transpose(0, 1).reshape(-1).tolist()
    return encode_pcm16_wav_bytes(interleaved, sample_rate=sample_rate,
                                  channels=audio.shape[0])


def _audiocraft_version():
    from importlib.metadata import version
    return version("audiocraft")


@_remote
def _generate_takes_remote(prompt, seeds, duration, model_name):
    """All takes in one call: one container, one GPU, sequential seeds."""
    import torch

    model, gpu = _load_model(model_name)
    results = []
    for seed in seeds:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        model.set_generation_params(duration=duration, top_k=250, top_p=0.0,
                                    temperature=1.0, cfg_coef=3.0)
        audio = model.generate([prompt], progress=False)[0]
        results.append({
            "seed": seed,
            "wav_bytes": _encode_wav(audio, model.sample_rate),
            "audiocraft_version": _audiocraft_version(),
            "gpu": gpu,
            "duration_seconds": audio.shape[-1] / model.sample_rate,
        })
    return results


@_remote
def _extend_remote(source_wav_bytes, prompt, target_seconds, base_seed,
                   model_name, window_seconds, overlap_seconds):
    """Continue a take to target length in overlapping continuation windows."""
    import torch
    import torchaudio
    from audiocraft.data.audio_utils import convert_audio

    model, gpu = _load_model(model_name)
    sr = model.sample_rate
    src, src_sr = torchaudio.load(io.BytesIO(source_wav_bytes))
    current = convert_audio(src, src_sr, sr, model.audio_channels)
    steps = plan_extension(current.shape[-1] / sr, target_seconds,
                           window_seconds, overlap_seconds)
    prompt_samples = int(round(overlap_seconds * sr))
    for i, step in enumerate(steps):
        seed = int(base_seed) + i
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        model.set_generation_params(duration=step["generation_seconds"],
                                    top_k=250, top_p=0.0, temperature=1.0,
                                    cfg_coef=3.0)
        prompt_audio = current[:, -prompt_samples:]
        # AudioCraft moves the prompt to the GPU itself, so the window
        # comes back on cuda:0; the track being built stays on CPU.
        out = model.generate_continuation(
            prompt_audio, sr, [prompt], progress=False)[0].detach().cpu()
        new_audio = (out[:, prompt_samples:] if out.shape[-1] > prompt_samples
                     else out)
        want = int(round(step["new_seconds"] * sr))
        current = torch.cat([current, new_audio[:, :want]], dim=-1)
    current = current[:, : int(round(target_seconds * sr))]
    return {
        "wav_bytes": _encode_wav(current, sr),
        "audiocraft_version": _audiocraft_version(),
        "gpu": gpu,
        "duration_seconds": current.shape[-1] / sr,
        "windows": len(steps),
    }


@_remote
def _compose_remote(source_wav_bytes, develop_prompt, reprise_prompt, plan,
                    theme_model_name, base_seed):
    """Compose theme + development + melody reprise, one model at a time."""
    import gc

    import torch
    import torchaudio
    from audiocraft.data.audio_utils import convert_audio

    sr = SAMPLE_RATE
    src, src_sr = torchaudio.load(io.BytesIO(source_wav_bytes))

    max_samples = int(round(MAX_WINDOW_SECONDS * sr))
    prompt_samples = int(round(DEFAULT_OVERLAP_SECONDS * sr))
    max_new = max_samples - prompt_samples

    def _ask(model_, needed_samples, seed):
        """One generation asking for a bit more than needed, frame-aligned."""
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        asked = min(max_samples, int(round(
            requested_generation_seconds(needed_samples, sr) * sr)))
        model_.set_generation_params(duration=asked / sr, top_k=250,
                                     top_p=0.0, temperature=1.0, cfg_coef=3.0)

    # --- Development: stereo model, continuing the theme like extend does.
    # Lengths are never trusted: loop on the actual length, asking each
    # window for a frame-aligned bit extra and trimming to the plan, so
    # any shortfall is generated by the next window instead of failing.
    model, gpu = _load_model(theme_model_name)
    current = convert_audio(src, src_sr, sr, model.audio_channels)
    theme_audio = current.clone()
    dev_end = int(round(plan["development"]["end_seconds"] * sr))
    dev_seeds = []
    while current.shape[-1] < dev_end:
        seed = int(base_seed) + len(dev_seeds)
        dev_seeds.append(seed)
        remaining = dev_end - current.shape[-1]
        _ask(model, prompt_samples + min(remaining, max_new), seed)
        out = model.generate_continuation(
            current[:, -prompt_samples:], sr, [develop_prompt],
            progress=False)[0].detach().cpu()
        new_audio = (out[:, prompt_samples:] if out.shape[-1] > prompt_samples
                     else out)
        if new_audio.shape[-1] <= 0:
            raise RuntimeError("continuation returned no new audio")
        current = torch.cat(
            [current, new_audio[:, :remaining]], dim=-1)
    development_bytes = _encode_wav(current[:, :dev_end], sr)
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # --- Reprise: melody model, conditioned on the theme take's melody.
    # Same discipline: trim to the planned length, and if it still comes
    # back short, generate the shortfall by continuation.
    planned_rep = int(round(plan["reprise"]["generation_seconds"] * sr))
    reprise_seed = int(base_seed) + len(dev_seeds)
    melody_model, gpu = _load_model(MELODY_MODEL)
    _ask(melody_model, planned_rep, reprise_seed)
    reprise = melody_model.generate_with_chroma(
        [reprise_prompt], theme_audio.unsqueeze(0), sr,
        progress=False)[0].detach().cpu()
    reprise_seeds = [reprise_seed]
    while reprise.shape[-1] < planned_rep:
        seed = reprise_seed + len(reprise_seeds)
        reprise_seeds.append(seed)
        shortfall = planned_rep - reprise.shape[-1]
        _ask(melody_model, prompt_samples + min(shortfall, max_new), seed)
        out = melody_model.generate_continuation(
            reprise[:, -prompt_samples:], sr, [reprise_prompt],
            progress=False)[0].detach().cpu()
        new_audio = (out[:, prompt_samples:] if out.shape[-1] > prompt_samples
                     else out)
        if new_audio.shape[-1] <= 0:
            raise RuntimeError("reprise continuation returned no new audio")
        reprise = torch.cat([reprise, new_audio[:, :shortfall]], dim=-1)
    reprise_bytes = _encode_wav(reprise[:, :planned_rep], sr)
    del melody_model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Sections are returned separately; the local side saves them before
    # any joining happens, so a failed join never loses generated audio.
    return {
        "development_wav_bytes": development_bytes,
        "reprise_wav_bytes": reprise_bytes,
        "audiocraft_version": _audiocraft_version(),
        "gpu": gpu,
        "development_seeds": dev_seeds,
        "reprise_seeds": reprise_seeds,
    }


def _entrypoint(fn):
    if modal is None:
        return fn
    return app.local_entrypoint()(fn)


@_entrypoint
def takes(count: int = 4, duration: float = 30.0, base_seed: int = 1234,
          model: str = DEFAULT_MODEL, prompt_file: str = DEFAULT_PROMPT_FILE,
          out_dir: str = "out"):
    """Make several short takes (default prompt: prompts/theme.txt)."""
    if modal is None:
        raise RuntimeError("Modal client not installed; see README.md setup")
    if not 1 <= count <= 20:
        raise ValueError("count must be between 1 and 20")
    if not 0 < duration <= MAX_WINDOW_SECONDS:
        raise ValueError(f"duration must be in (0, {MAX_WINDOW_SECONDS}] seconds")
    prompt = read_prompt(_local_path(prompt_file))
    model = validate_model(model)
    seeds = derive_seeds(base_seed, count)
    print(f"{count} takes x {duration}s, model={model}, seeds={seeds}")
    results = _generate_takes_remote.remote(prompt, seeds, duration, model)
    for i, r in enumerate(results, start=1):
        wav_path, json_path = save_output(
            out_dir, f"take-{i:03d}-seed{r['seed']}", r["wav_bytes"],
            model=model, prompt=prompt, seed=r["seed"],
            duration_seconds=r["duration_seconds"],
            audiocraft_version=r["audiocraft_version"], gpu=r["gpu"])
        print(f"wrote {wav_path} and {json_path}")


@_entrypoint
def extend(take_path: str, target_seconds: float = 185.0,
           base_seed: int = 1234, model: str = "",
           window_seconds: float = MAX_WINDOW_SECONDS,
           overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
           out_dir: str = "out"):
    """Continue the picked take to full length; never restarts the music."""
    if modal is None:
        raise RuntimeError("Modal client not installed; see README.md setup")
    src = _local_path(take_path)
    wav_bytes = src.read_bytes()
    info = validate_output_wav(wav_info_from_bytes(wav_bytes))
    sidecar_path = src.with_suffix(".json")
    prompt, src_model = None, DEFAULT_MODEL
    if sidecar_path.exists():
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        prompt, src_model = sidecar.get("prompt"), sidecar.get("model", src_model)
    if prompt is None:
        prompt = read_prompt(Path(__file__).resolve().parent / "prompt.txt")
    model = validate_model(model or src_model)
    steps = plan_extension(info["duration_seconds"], target_seconds,
                           window_seconds, overlap_seconds)
    print(f"extending {src.name}: {info['duration_seconds']:.1f}s -> "
          f"{target_seconds}s in {len(steps)} overlapping windows")
    r = _extend_remote.remote(wav_bytes, prompt, target_seconds, base_seed,
                              model, window_seconds, overlap_seconds)
    wav_path, json_path = save_output(
        out_dir, f"extended-from-{src.stem}", r["wav_bytes"],
        model=model, prompt=prompt, seed=base_seed,
        duration_seconds=r["duration_seconds"],
        audiocraft_version=r["audiocraft_version"], gpu=r["gpu"],
        source_take=src.name)
    print(f"wrote {wav_path} and {json_path}")


@_entrypoint
def compose(take_path: str, total_seconds: float = DEFAULT_TOTAL_SECONDS,
            bpm: float = DEFAULT_BPM, base_seed: int = 5100,
            prompts_dir: str = "prompts", out_dir: str = "out"):
    """Build the whole piece: theme take, development, melody reprise."""
    if modal is None:
        raise RuntimeError("Modal client not installed; see README.md setup")
    src = _local_path(take_path)
    wav_bytes = src.read_bytes()
    info = validate_output_wav(wav_info_from_bytes(wav_bytes))
    prompts = Path(__file__).resolve().parent / prompts_dir \
        if not Path(prompts_dir).exists() else Path(prompts_dir)
    theme_text = read_prompt(prompts / "theme.txt")
    develop_text = read_prompt(prompts / "develop.txt")
    reprise_text = read_prompt(prompts / "reprise.txt")
    theme_model, theme_seed = DEFAULT_MODEL, base_seed
    sidecar_path = src.with_suffix(".json")
    if sidecar_path.exists():
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        theme_model = sidecar.get("model", theme_model)
        theme_seed = sidecar.get("seed", theme_seed)
        theme_text = sidecar.get("prompt", theme_text)
    theme_model = validate_model(theme_model)
    plan = plan_composition(total_seconds, info["duration_seconds"], bpm)
    print(f"composing from {src.name}: theme 0-{plan['theme']['end_seconds']}s, "
          f"development to {plan['development']['end_seconds']}s, reprise "
          f"{plan['reprise']['start_seconds']}-{plan['reprise']['end_seconds']}s "
          f"at {bpm} BPM")
    r = _compose_remote.remote(wav_bytes, develop_text, reprise_text, plan,
                               theme_model, base_seed)
    sections = [
        {"name": "theme", "start_seconds": plan["theme"]["start_seconds"],
         "end_seconds": plan["theme"]["end_seconds"],
         "prompt_file": "prompts/theme.txt", "prompt": theme_text,
         "model": theme_model, "seeds": [theme_seed]},
        {"name": "development",
         "start_seconds": plan["development"]["start_seconds"],
         "end_seconds": plan["development"]["end_seconds"],
         "prompt_file": "prompts/develop.txt", "prompt": develop_text,
         "model": theme_model, "seeds": r["development_seeds"]},
        {"name": "reprise", "start_seconds": plan["reprise"]["start_seconds"],
         "end_seconds": plan["reprise"]["end_seconds"],
         "prompt_file": "prompts/reprise.txt", "prompt": reprise_text,
         "model": MELODY_MODEL, "seeds": r["reprise_seeds"]},
    ]
    # Save the generated sections first: a failed join loses nothing.
    dev_path, dev_json = save_output(
        out_dir, f"section-development-from-{src.stem}",
        r["development_wav_bytes"], model=theme_model, prompt=develop_text,
        seed=r["development_seeds"][0],
        duration_seconds=plan["development"]["end_seconds"],
        audiocraft_version=r["audiocraft_version"], gpu=r["gpu"],
        source_take=src.name)
    rep_path, rep_json = save_output(
        out_dir, f"section-reprise-from-{src.stem}", r["reprise_wav_bytes"],
        model=MELODY_MODEL, prompt=reprise_text,
        seed=r["reprise_seeds"][0],
        duration_seconds=plan["reprise"]["generation_seconds"],
        audiocraft_version=r["audiocraft_version"], gpu=r["gpu"],
        source_take=src.name)
    print(f"saved sections {dev_path} and {rep_path}; joining locally")
    joined = join_section_bytes(dev_path.read_bytes(),
                                rep_path.read_bytes(), plan)
    wav_path, json_path = save_compose_output(
        out_dir, f"composed-from-{src.stem}", joined,
        sections=sections, crossfade=plan["crossfade"],
        fade_out=plan["fade_out"],
        audiocraft_version=r["audiocraft_version"], gpu=r["gpu"],
        source_take=src.name, base_seed=base_seed)
    print(f"wrote {wav_path} and {json_path}")


def join_saved_sections(development_path, reprise_path, take_path,
                        total_seconds=DEFAULT_TOTAL_SECONDS,
                        bpm=DEFAULT_BPM, prompts_dir="prompts",
                        out_dir="out", base_seed=5100):
    """Join two saved sections locally. No GPU, no torch, no cloud."""
    dev_path, rep_path, src = (Path(development_path), Path(reprise_path),
                               Path(take_path))
    src_bytes = src.read_bytes()
    info = validate_output_wav(wav_info_from_bytes(src_bytes))
    prompts_root = Path(prompts_dir)
    if not prompts_root.exists():
        prompts_root = Path(__file__).resolve().parent / prompts_dir
    theme_text = read_prompt(prompts_root / "theme.txt")
    develop_text = read_prompt(prompts_root / "develop.txt")
    reprise_text = read_prompt(prompts_root / "reprise.txt")

    def _sidecar_of(path, key, default):
        beside = path.with_suffix(".json")
        if beside.exists():
            return json.loads(beside.read_text(encoding="utf-8")).get(
                key, default)
        return default

    theme_model = _sidecar_of(src, "model", DEFAULT_MODEL)
    theme_seed = _sidecar_of(src, "seed", base_seed)
    theme_text = _sidecar_of(src, "prompt", theme_text)
    plan = plan_composition(total_seconds, info["duration_seconds"], bpm)
    sections = [
        {"name": "theme", "start_seconds": plan["theme"]["start_seconds"],
         "end_seconds": plan["theme"]["end_seconds"],
         "prompt_file": "prompts/theme.txt", "prompt": theme_text,
         "model": theme_model, "seeds": [theme_seed]},
        {"name": "development",
         "start_seconds": plan["development"]["start_seconds"],
         "end_seconds": plan["development"]["end_seconds"],
         "prompt_file": "prompts/develop.txt", "prompt": develop_text,
         "model": _sidecar_of(dev_path, "model", theme_model),
         "seeds": [_sidecar_of(dev_path, "seed", base_seed)]},
        {"name": "reprise", "start_seconds": plan["reprise"]["start_seconds"],
         "end_seconds": plan["reprise"]["end_seconds"],
         "prompt_file": "prompts/reprise.txt", "prompt": reprise_text,
         "model": _sidecar_of(rep_path, "model", MELODY_MODEL),
         "seeds": [_sidecar_of(rep_path, "seed", base_seed)]},
    ]
    joined = join_section_bytes(dev_path.read_bytes(),
                                rep_path.read_bytes(), plan)
    wav_path, json_path = save_compose_output(
        out_dir, f"composed-from-{src.stem}", joined, sections=sections,
        crossfade=plan["crossfade"], fade_out=plan["fade_out"],
        audiocraft_version=_sidecar_of(rep_path, "audiocraft_version", "1.3.0"),
        gpu=_sidecar_of(rep_path, "gpu", "unknown"),
        source_take=src.name, base_seed=base_seed)
    print(f"wrote {wav_path} and {json_path}")
    return wav_path, json_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    join_parser = sub.add_parser(
        "join", help="join saved development/reprise sections locally")
    join_parser.add_argument("--development", required=True)
    join_parser.add_argument("--reprise", required=True)
    join_parser.add_argument("--take-path", required=True)
    join_parser.add_argument("--total-seconds", type=float,
                             default=DEFAULT_TOTAL_SECONDS)
    join_parser.add_argument("--bpm", type=float, default=DEFAULT_BPM)
    join_parser.add_argument("--base-seed", type=int, default=5100)
    join_parser.add_argument("--prompts-dir", default="prompts")
    join_parser.add_argument("--out-dir", default="out")
    args = parser.parse_args()
    if args.command == "join":
        join_saved_sections(args.development, args.reprise, args.take_path,
                            total_seconds=args.total_seconds, bpm=args.bpm,
                            prompts_dir=args.prompts_dir, out_dir=args.out_dir,
                            base_seed=args.base_seed)

