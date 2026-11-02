"""Local tests for musicgen_modal. No Modal, GPU, torch or network needed.

Every behaviour has a planted red case beside it: bad input that must be
rejected, or tampered data that must be detected.
Run:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import hashlib
import io
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import musicgen_modal as m

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_PROMPT = (
    "Retro 1980s synthwave instrumental, 125 BPM, A minor, dark and cinematic. "
    "Driving four-on-the-floor kick, gated-reverb snare on two and four, "
    "pulsing sidechained analog bassline in sixteenth notes, bright "
    "arpeggiated sawtooth synths, wide detuned pads, soaring overdriven lead "
    "synth. Neon night drive into space: futuristic, confident, steady "
    "groove throughout."
)


def make_wav_bytes(seconds=1.0, rate=32000, channels=2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * channels * int(seconds * rate))
    return buf.getvalue()


class PromptTests(unittest.TestCase):
    def test_prompt_txt_is_exactly_the_directors_text(self):
        self.assertEqual(m.read_prompt(ROOT / "prompt.txt"), EXPECTED_PROMPT)

    def test_read_prompt_strips_surrounding_blank_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.txt"
            p.write_text("\n  hello prompt \n\n", encoding="utf-8")
            self.assertEqual(m.read_prompt(p), "hello prompt")

    def test_red_empty_prompt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.txt"
            p.write_text("  \n", encoding="utf-8")
            with self.assertRaises(ValueError):
                m.read_prompt(p)

    def test_red_missing_prompt_rejected(self):
        with self.assertRaises((FileNotFoundError, ValueError)):
            m.read_prompt(Path(tempfile.gettempdir()) / "no-such-prompt.txt")


class SeedAndModelTests(unittest.TestCase):
    def test_seeds_are_distinct_and_deterministic(self):
        self.assertEqual(m.derive_seeds(100, 4), [100, 101, 102, 103])
        self.assertEqual(m.derive_seeds(100, 4), m.derive_seeds(100, 4))

    def test_red_duplicate_seeds_rejected(self):
        with self.assertRaises(ValueError):
            m.validate_seeds([7, 7, 8])

    def test_red_zero_takes_rejected(self):
        with self.assertRaises(ValueError):
            m.derive_seeds(1, 0)

    def test_models_allowed(self):
        self.assertEqual(m.validate_model(m.DEFAULT_MODEL),
                         "facebook/musicgen-stereo-large")
        self.assertEqual(m.validate_model("facebook/musicgen-stereo-medium"),
                         "facebook/musicgen-stereo-medium")

    def test_red_other_model_rejected(self):
        with self.assertRaises(ValueError):
            m.validate_model("facebook/musicgen-small")


class OutputNamingTests(unittest.TestCase):
    def test_unique_path_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            first = Path(d) / "take.wav"
            first.write_bytes(b"original")
            chosen = m.unique_output_path(Path(d), "take.wav")
            self.assertNotEqual(chosen, first)
            self.assertFalse(chosen.exists())
            self.assertEqual(first.read_bytes(), b"original")

    def test_red_taken_stem_gets_numbered_name(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "take.wav").write_bytes(b"a")
            (Path(d) / "take-2.wav").write_bytes(b"b")
            self.assertEqual(m.unique_output_path(Path(d), "take.wav").name,
                             "take-3.wav")


class SidecarTests(unittest.TestCase):
    def _sidecar(self, wav_bytes, **over):
        kw = dict(file="take.wav", model=m.DEFAULT_MODEL, prompt="p",
                  seed=42, duration_seconds=30.0, audiocraft_version="1.3.0",
                  gpu="NVIDIA A10G", source_take=None)
        kw.update(over)
        return m.build_sidecar(wav_bytes=wav_bytes, **kw)

    def test_sidecar_has_every_required_field_and_correct_hash(self):
        data = make_wav_bytes()
        s = self._sidecar(data)
        for field in m.REQUIRED_SIDECAR_FIELDS:
            self.assertIn(field, s)
        self.assertEqual(s["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(s["sample_rate_hz"], 32000)
        self.assertEqual(s["channels"], 2)
        m.validate_sidecar(s, wav_bytes=data)  # must not raise

    def test_red_tampered_wav_fails_hash_check(self):
        s = self._sidecar(make_wav_bytes())
        with self.assertRaises(ValueError):
            m.validate_sidecar(s, wav_bytes=make_wav_bytes() + b"x")

    def test_red_missing_field_rejected(self):
        s = self._sidecar(make_wav_bytes())
        del s["gpu"]
        with self.assertRaises(ValueError):
            m.validate_sidecar(s)

    def test_red_wrong_sample_rate_rejected_in_wav_info(self):
        with self.assertRaises(ValueError):
            m.validate_output_wav(m.wav_info_from_bytes(make_wav_bytes(rate=22050)))

    def test_extend_sidecar_names_its_source_take(self):
        s = self._sidecar(make_wav_bytes(), source_take="take-001.wav")
        self.assertEqual(s["source_take"], "take-001.wav")


class ExtensionPlanTests(unittest.TestCase):
    def test_plan_covers_target_in_overlapping_windows(self):
        steps = m.plan_extension(30.0, 185.0)
        self.assertTrue(steps)
        self.assertTrue(all(s["generation_seconds"] <= 30.0 for s in steps))
        self.assertTrue(all(s["prompt_seconds"] == 10.0 for s in steps))
        reached = 30.0 + sum(s["new_seconds"] for s in steps)
        self.assertAlmostEqual(reached, 185.0)

    def test_red_target_not_longer_than_take_rejected(self):
        with self.assertRaises(ValueError):
            m.plan_extension(30.0, 30.0)

    def test_red_overlap_must_be_smaller_than_window(self):
        with self.assertRaises(ValueError):
            m.plan_extension(30.0, 60.0, window_seconds=30.0, overlap_seconds=30.0)


class SaveOutputTests(unittest.TestCase):
    def test_save_writes_wav_and_matching_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            data = make_wav_bytes()
            wav_path, json_path = m.save_output(
                Path(d), "take-001-seed42", data,
                model=m.DEFAULT_MODEL, prompt="p", seed=42,
                duration_seconds=1.0, audiocraft_version="1.3.0",
                gpu="NVIDIA A10G")
            self.assertEqual(wav_path.read_bytes(), data)
            sidecar = json.loads(json_path.read_text(encoding="utf-8"))
            m.validate_sidecar(sidecar, wav_bytes=wav_path.read_bytes())

    def test_red_second_save_does_not_overwrite_first(self):
        with tempfile.TemporaryDirectory() as d:
            kw = dict(model=m.DEFAULT_MODEL, prompt="p", seed=42,
                      duration_seconds=1.0, audiocraft_version="1.3.0",
                      gpu="NVIDIA A10G")
            w1, _ = m.save_output(Path(d), "take", make_wav_bytes(), **kw)
            w2, _ = m.save_output(Path(d), "take", make_wav_bytes(), **kw)
            self.assertNotEqual(w1, w2)
            self.assertTrue(w1.exists() and w2.exists())


class PinTests(unittest.TestCase):
    def test_torch_pins_match_audiocraft_130(self):
        self.assertEqual(m.TORCH_VERSION, "2.1.0")
        self.assertEqual(m.TORCHAUDIO_VERSION, "2.1.0")
        self.assertIn("torch==2.1.0", m.IMAGE_PIP_PACKAGES)
        self.assertIn("torchaudio==2.1.0", m.IMAGE_PIP_PACKAGES)

    def test_numpy_and_transformers_constrained_for_torch_21(self):
        self.assertIn("numpy<2", m.IMAGE_PIP_PACKAGES)
        tf = [p for p in m.IMAGE_PIP_PACKAGES if p.startswith("transformers==")]
        self.assertEqual(len(tf), 1)
        major = int(tf[0].split("==")[1].split(".")[0])
        self.assertEqual(major, 4)

    def test_red_incompatible_torch_not_in_image_packages(self):
        self.assertNotIn("torch==2.3.1", m.IMAGE_PIP_PACKAGES)
        self.assertNotIn("torchaudio==2.3.1", m.IMAGE_PIP_PACKAGES)

    def test_av_build_dependencies_installed_in_image(self):
        for pkg in ("build-essential", "pkg-config", "libavformat-dev",
                    "libavcodec-dev", "libavdevice-dev", "libavutil-dev",
                    "libavfilter-dev", "libswscale-dev", "libswresample-dev"):
            self.assertIn(pkg, m.IMAGE_APT_PACKAGES)


class Pcm16WavTests(unittest.TestCase):
    def test_container_encoding_is_read_by_wav_info(self):
        # 0.1 s of stereo silence-ish samples, interleaved L/R.
        samples = [0.0, 0.25] * 3200
        data = m.encode_pcm16_wav_bytes(samples, sample_rate=32000, channels=2)
        info = m.wav_info_from_bytes(data)
        self.assertEqual(info["sample_rate_hz"], 32000)
        self.assertEqual(info["channels"], 2)
        self.assertAlmostEqual(info["duration_seconds"], 0.1)
        m.validate_output_wav(info)  # extend accepts what takes produce

    def test_red_out_of_range_samples_clamp_not_wrap(self):
        data = m.encode_pcm16_wav_bytes([2.0, -2.0] * 100,
                                        sample_rate=32000, channels=2)
        with wave.open(io.BytesIO(data), "rb") as w:
            raw = w.readframes(200)
        values = [int.from_bytes(raw[i:i + 2], "little", signed=True)
                  for i in range(0, len(raw), 2)]
        self.assertEqual(max(values), 32767)
        self.assertEqual(min(values), -32767)

    def test_red_partial_frame_rejected(self):
        with self.assertRaises(ValueError):
            m.encode_pcm16_wav_bytes([0.0, 0.0, 0.0],
                                     sample_rate=32000, channels=2)


class DeviceTests(unittest.TestCase):
    def test_extend_brings_continuation_output_to_cpu_before_joining(self):
        # AudioCraft moves the continuation prompt to the GPU itself, so
        # each window comes back on cuda:0 while the track built from the
        # torchaudio-loaded take stays on CPU. The join must not mix them.
        src = (ROOT / "musicgen_modal.py").read_text(encoding="utf-8")
        body = src.split("def _extend_remote")[1].split("\ndef ")[0]
        gen = body.index("generate_continuation")
        cat = body.index("torch.cat")
        self.assertIn(".detach().cpu()", body[gen:cat])


EXPECTED_V2_PROMPTS = {
    "theme.txt": (
        "Dark retro synthwave instrumental, 108 BPM, D minor, brooding and "
        "cinematic. Steady four-on-the-floor kick, deep gated-reverb snare, "
        "warm pulsing analog bassline, low-pass filtered arpeggio, dark "
        "analog pads, and one slow, memorable lead melody on a mellow, warm "
        "synth. Night over Earth from orbit: tense, focused, determined."),
    "develop.txt": (
        "Dark retro synthwave instrumental, 108 BPM, D minor, brooding and "
        "cinematic. The same kick, snare, analog bass and dark pads, with "
        "the lead melody developed in variations, a low counter-melody, and "
        "fuller drums building tension, then easing. Night over Earth from "
        "orbit: tense, focused, determined."),
    "reprise.txt": (
        "Dark retro synthwave instrumental, 108 BPM, D minor, brooding and "
        "cinematic. The opening lead melody returns on the mellow warm "
        "synth over the steady kick, analog bass and dark pads, resolving "
        "to a calm, final ending. Night over Earth from orbit: quiet resolve."),
}


class V2PromptTests(unittest.TestCase):
    def test_three_prompt_files_hold_exact_text(self):
        for name, text in EXPECTED_V2_PROMPTS.items():
            self.assertEqual(m.read_prompt(ROOT / "prompts" / name), text)

    def test_takes_now_defaults_to_theme_prompt(self):
        self.assertEqual(m.DEFAULT_PROMPT_FILE, "prompts/theme.txt")

    def test_melody_model_allowed(self):
        self.assertEqual(m.validate_model(m.MELODY_MODEL),
                         "facebook/musicgen-stereo-melody-large")

    def test_prompt_txt_unchanged(self):
        self.assertEqual(m.read_prompt(ROOT / "prompt.txt"), EXPECTED_PROMPT)


class CompositionPlanTests(unittest.TestCase):
    def test_plan_adds_up_to_total(self):
        plan = m.plan_composition(total_seconds=180.0, theme_seconds=30.0,
                                  bpm=108)
        self.assertEqual(plan["theme"]["start_seconds"], 0.0)
        self.assertEqual(plan["theme"]["end_seconds"], 30.0)
        self.assertEqual(plan["reprise"]["end_seconds"], 180.0)
        covered = (plan["theme"]["end_seconds"]
                   + (plan["crossfade"]["start_seconds"]
                      - plan["theme"]["end_seconds"])
                   + (plan["reprise"]["end_seconds"]
                      - plan["crossfade"]["start_seconds"]))
        self.assertAlmostEqual(covered, 180.0)
        self.assertLessEqual(plan["reprise"]["generation_seconds"], 30.0)
        self.assertAlmostEqual(plan["reprise"]["generation_seconds"],
                               13 * plan["bar_seconds"], places=6)

    def test_crossfade_and_fade_on_bar_lines(self):
        plan = m.plan_composition(180.0, 30.0, 108)
        bar = plan["bar_seconds"]
        self.assertAlmostEqual(bar, 240.0 / 108.0)
        for point in (plan["crossfade"]["start_seconds"],
                      plan["crossfade"]["end_seconds"],
                      plan["fade_out"]["start_seconds"]):
            self.assertAlmostEqual(point / bar, round(point / bar), places=6)
        self.assertAlmostEqual(plan["crossfade"]["duration_seconds"], bar)
        self.assertAlmostEqual(plan["fade_out"]["duration_seconds"], 2 * bar)
        self.assertEqual(plan["fade_out"]["end_seconds"], 180.0)

    def test_red_nonpositive_bpm_rejected(self):
        with self.assertRaises(ValueError):
            m.plan_composition(180.0, 30.0, 0)

    def test_red_total_must_exceed_theme_plus_reprise(self):
        with self.assertRaises(ValueError):
            m.plan_composition(40.0, 30.0, 108)


class CrossfadeTests(unittest.TestCase):
    def test_equal_power_gains_keep_total_power_one(self):
        out_g, in_g = m.equal_power_gains(64)
        for a, b in zip(out_g, in_g):
            self.assertAlmostEqual(a * a + b * b, 1.0, places=9)

    def test_equal_power_crossfade_keeps_steady_level(self):
        import random
        rng = random.Random(2026)
        n = 16000
        a = [rng.gauss(0.0, 1.0) for _ in range(n)]
        b = [rng.gauss(0.0, 1.0) for _ in range(n)]
        mixed = m.crossfade_samples(a, b)
        rms = (sum(x * x for x in mixed) / n) ** 0.5
        self.assertTrue(0.9 < rms < 1.1, f"RMS drifted to {rms}")

    def test_red_linear_crossfade_dips_in_the_middle(self):
        # The planted wrong method: linear gains lose ~half the power
        # mid-fade for uncorrelated signals, so it must fail the level
        # check above.
        import random
        rng = random.Random(2026)
        n = 16000
        a = [rng.gauss(0.0, 1.0) for _ in range(n)]
        b = [rng.gauss(0.0, 1.0) for _ in range(n)]
        mixed = [x * (1 - i / (n - 1)) + y * (i / (n - 1))
                 for i, (x, y) in enumerate(zip(a, b))]
        mid = mixed[n // 4: 3 * n // 4]
        rms = (sum(x * x for x in mid) / len(mid)) ** 0.5
        self.assertLess(rms, 0.85)

    def test_red_mismatched_lengths_rejected(self):
        with self.assertRaises(ValueError):
            m.crossfade_samples([0.0, 0.1], [0.0])

    def test_red_empty_crossfade_rejected(self):
        with self.assertRaises(ValueError):
            m.equal_power_gains(0)


class ComposeSaveTests(unittest.TestCase):
    SECTIONS = [
        {"name": "theme", "start_seconds": 0.0, "end_seconds": 30.0,
         "prompt_file": "prompts/theme.txt", "prompt": "theme text",
         "model": m.DEFAULT_MODEL if hasattr(m, "DEFAULT_MODEL") else "x",
         "seeds": [3100]},
        {"name": "reprise", "start_seconds": 151.111, "end_seconds": 180.0,
         "prompt_file": "prompts/reprise.txt", "prompt": "reprise text",
         "model": "facebook/musicgen-stereo-melody-large", "seeds": [3200]},
    ]

    def test_compose_save_records_sections_and_hash(self):
        # Access attributes lazily so this test runs (and fails) on v1 too.
        sections = [dict(s, model=(m.MELODY_MODEL
                                   if s["name"] == "reprise" else m.DEFAULT_MODEL))
                    for s in self.SECTIONS]
        with tempfile.TemporaryDirectory() as d:
            data = make_wav_bytes()
            wav_path, json_path = m.save_compose_output(
                Path(d), "composed-from-take", data, sections=sections,
                crossfade={"start_seconds": 151.111, "end_seconds": 153.333,
                           "duration_seconds": 2.222},
                fade_out={"start_seconds": 175.556, "end_seconds": 180.0,
                          "duration_seconds": 4.444},
                audiocraft_version="1.3.0", gpu="NVIDIA A10G",
                source_take="take.wav", base_seed=3100)
            sidecar = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(sidecar["sections"], sections)
            self.assertEqual(sidecar["sha256"],
                             hashlib.sha256(data).hexdigest())
            self.assertEqual(sidecar["source_take"], "take.wav")
            m.validate_compose_sidecar(sidecar, wav_bytes=data)
            w2, _ = m.save_compose_output(
                Path(d), "composed-from-take", data, sections=sections,
                crossfade=sidecar["crossfade"], fade_out=sidecar["fade_out"],
                audiocraft_version="1.3.0", gpu="NVIDIA A10G",
                source_take="take.wav", base_seed=3100)
            self.assertNotEqual(wav_path, w2)

    def test_red_compose_sidecar_missing_section_field_rejected(self):
        bad = dict(self.SECTIONS[0])
        del bad["prompt_file"]
        sidecar = {"file": "x.wav", "models": [], "seed": 1,
                   "duration_seconds": 180.0, "sample_rate_hz": 32000,
                   "channels": 2, "audiocraft_version": "1.3.0",
                   "gpu": "NVIDIA A10G", "sha256": "0" * 64,
                   "source_take": "take.wav", "sections": [bad],
                   "crossfade": {}, "fade_out": {}}
        with self.assertRaises(ValueError):
            m.validate_compose_sidecar(sidecar)


class FrameLengthTests(unittest.TestCase):
    def test_request_rounds_up_to_whole_codec_frames(self):
        self.assertEqual(m.codec_frame_samples(32000), 640)
        self.assertEqual(m.ceil_to_codec_frames(71111), 71680)
        secs = m.requested_generation_seconds(71111, 32000)
        self.assertGreaterEqual(secs * 32000, 71111)
        self.assertAlmostEqual((secs * 32000) % 640, 0.0, places=6)

    def test_red_negative_length_rejected(self):
        with self.assertRaises(ValueError):
            m.ceil_to_codec_frames(-1)

    def test_red_rate_not_divisible_by_codec_frames_rejected(self):
        with self.assertRaises(ValueError):
            m.codec_frame_samples(22051)


class FitAndAssembleTests(unittest.TestCase):
    CS, BAR, TOTAL = 80, 10, 120

    def _assemble(self, dev, rep):
        return m.assemble_composition(
            dev, rep, crossfade_start_samples=self.CS,
            bar_samples=self.BAR, total_samples=self.TOTAL)

    def test_exact_sections_assemble_to_total_on_bar_line(self):
        final = self._assemble([[1.0] * 100], [[0.5] * 40])
        self.assertEqual(len(final[0]), self.TOTAL)
        self.assertEqual(final[0][self.CS - 1], 1.0)       # before the bar
        self.assertEqual(final[0][self.CS + self.BAR], 0.5)  # reprise after it
        self.assertAlmostEqual(final[0][self.CS], 1.0, places=9)

    def test_long_sections_trimmed_to_total(self):
        final = self._assemble([[1.0] * 105], [[0.5] * 47])
        self.assertEqual(len(final[0]), self.TOTAL)

    def test_short_sections_padded_to_total(self):
        final = self._assemble([[1.0] * 87], [[0.5] * 37])
        self.assertEqual(len(final[0]), self.TOTAL)
        self.assertEqual(final[0][self.CS - 1], 1.0)

    def test_red_crossfade_past_total_rejected(self):
        with self.assertRaises(ValueError):
            m.assemble_composition([[1.0] * 100], [[0.5] * 40],
                                   crossfade_start_samples=115,
                                   bar_samples=10, total_samples=120)

    def test_red_channel_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            self._assemble([[1.0] * 100, [1.0] * 100], [[0.5] * 40])

    def test_fit_to_length_trims_and_pads(self):
        self.assertEqual(m.fit_to_length([[1.0] * 10], 4), [[1.0] * 4])
        self.assertEqual(m.fit_to_length([[1.0] * 2], 4),
                         [[1.0, 1.0, 0.0, 0.0]])

    def test_red_ragged_channels_rejected(self):
        with self.assertRaises(ValueError):
            m.fit_to_length([[1.0] * 3, [1.0] * 2], 3)


class FadeOutTests(unittest.TestCase):
    def test_fade_built_from_actual_length(self):
        track = [[1.0] * 10]
        faded = m.apply_fade_out(track, 6)
        self.assertEqual(len(faded[0]), 10)
        self.assertEqual(faded[0][5], 1.0)
        self.assertEqual(faded[0][-1], 0.0)
        self.assertTrue(0.0 < faded[0][8] < 1.0)

    def test_red_fade_start_beyond_track_rejected(self):
        with self.assertRaises(ValueError):
            m.apply_fade_out([[1.0] * 5], 5)

    def test_red_negative_fade_start_rejected(self):
        with self.assertRaises(ValueError):
            m.apply_fade_out([[1.0] * 5], -1)


class WavChannelRoundTripTests(unittest.TestCase):
    def test_channels_survive_encode_decode(self):
        channels = [[0.0, 0.5, -0.5], [0.25, -0.25, 0.0]]
        data = m.encode_channels_pcm16(channels, 32000)
        decoded, rate = m.decode_pcm16_channels(data)
        self.assertEqual(rate, 32000)
        self.assertEqual(len(decoded), 2)
        self.assertAlmostEqual(decoded[0][1], 0.5, places=3)
        self.assertAlmostEqual(decoded[1][0], 0.25, places=3)

    def test_red_float_wav_rejected_by_decoder(self):
        # encode_pcm16 only writes 16-bit; a hand-made 8-bit WAV must fail.
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(1)
            w.setframerate(32000)
            w.writeframes(bytes([128] * 10))
        with self.assertRaises(ValueError):
            m.decode_pcm16_channels(buf.getvalue())


class JoinSectionBytesTests(unittest.TestCase):
    PLAN = {"total_seconds": 120 / 32000,
            "crossfade": {"start_seconds": 80 / 32000,
                          "duration_seconds": 10 / 32000},
            "fade_out": {"start_seconds": 100 / 32000}}

    def test_join_short_long_and_exact_all_hit_total(self):
        for dev_len, rep_len in ((90, 40), (87, 37), (97, 47)):
            dev = m.encode_channels_pcm16([[1.0] * dev_len], 32000)
            rep = m.encode_channels_pcm16([[0.5] * rep_len], 32000)
            joined = m.join_section_bytes(dev, rep, self.PLAN)
            channels, rate = m.decode_pcm16_channels(joined)
            self.assertEqual(rate, 32000)
            self.assertEqual(len(channels[0]), 120)
            self.assertEqual(channels[0][79], 1.0)
            self.assertEqual(channels[0][-1], 0.0)

    def test_red_join_wrong_sample_rate_rejected(self):
        dev = m.encode_channels_pcm16([[1.0] * 90], 22050)
        rep = m.encode_channels_pcm16([[0.5] * 40], 32000)
        with self.assertRaises(ValueError):
            m.join_section_bytes(dev, rep, self.PLAN)


if __name__ == "__main__":
    unittest.main()
