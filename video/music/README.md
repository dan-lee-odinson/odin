# Music for ODIN's demo video — MusicGen on Modal

## What this does

[musicgen_modal.py](musicgen_modal.py) runs Meta's MusicGen
(`facebook/musicgen-stereo-large` by default, from the AudioCraft release)
on a single Modal GPU and writes an instrumental bed for the demo video:

1. **Takes** — one command generates several short takes (default: 4 takes
   of 30 s) from [prompts/theme.txt](prompts/theme.txt), each with its own
   seed, all in one container on one GPU (A10G). Every take lands in `out/`
   as a 32 kHz stereo WAV, with a JSON sidecar beside it giving the model,
   the prompt, the seed, the length in seconds, the AudioCraft version,
   the GPU, and the WAV's SHA-256. ([prompt.txt](prompt.txt) is the
   original version-1 prompt, unchanged; pass
   `--prompt-file prompt.txt` to use it again.)
2. **Extend** — a second command takes the take you pick and continues it
   to full length (default 185 s). It never restarts the music: it
   re-feeds the last 10 s of the audio so far as a continuation prompt,
   generates the next window of at most 30 s, appends only the new audio,
   and repeats until the target length is reached. The result is saved the
   same way, and its JSON names the take it grew from (`source_take`).
3. **Compose** (version 2) — builds the whole 180 s piece from the theme
   take you pick, at 108 BPM (one bar = four beats ≈ 2.22 s). The take
   opens unchanged (0:00–0:30); the development continues it with
   [prompts/develop.txt](prompts/develop.txt) in overlapping windows, as
   extend does; the reprise (about 30 s) is generated separately by
   `facebook/musicgen-stereo-melody-large`, conditioned on the theme
   take's melody with [prompts/reprise.txt](prompts/reprise.txt), and
   joined to the development with a one-bar equal-power crossfade placed
   on a bar line; the last two bars fade out. The two models are loaded
   one at a time (the first is released before the melody model loads),
   so it fits on the same single A10G the takes already ran on. The JSON
   beside `composed-from-<take>.wav` records every section (start, end,
   prompt file and text, model, seeds), the crossfade and fade-out
   points, and the WAV's SHA-256. MusicGen returns whole codec frames
   (50/s), rarely the exact length asked, so every window and the
   reprise is asked for a frame-aligned bit extra, trimmed to the plan,
   and any shortfall is generated rather than failing — the composed
   piece is exactly the planned total. The development and reprise are
   also saved as their own WAVs (`section-development-…`,
   `section-reprise-…`, each with its JSON) before anything is joined,
   so a failed join never loses generated audio; joining itself happens
   locally, with no GPU.

A new take never overwrites an earlier one: if a file name is taken, the
next one gets `-2`, `-3`, … appended.

Nothing downloads to this machine except the finished WAVs. Modal builds
the image in the cloud from pinned versions (AudioCraft 1.3.0, torch
2.1.0, torchaudio 2.1.0, transformers 4.44.2, numpy<2 — see the top of
[musicgen_modal.py](musicgen_modal.py); the image also installs the C
toolchain and FFmpeg development libraries needed to build the
wheel-less `av==11.0.0` that AudioCraft pins), and the model weights download
inside Modal's container into a Modal Volume (`odin-musicgen-weights`),
so a second run does not fetch them again. Every cloud job has a
30-minute timeout, so a stuck job stops itself. The image's full
dependency set (139 packages, including `av==11.0.0`) was resolver-checked
for Linux and Python 3.11 with uv before first use; nothing was built
locally.

Modal reads `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` from your
environment when you run it. No key is stored in any file here, and no
service other than Modal is called. (The MusicGen weights are fetched by
the Modal container from their public model page on first use.)

## Setup (once, in your own PowerShell tab)

Run these from this folder (Python 3.10 or newer; tested here on 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` are already set as your user
environment variables, so they are present in any new PowerShell tab.
No key is typed, shown, or written to any file here.

Optional, before any cloud run — the local tests (no Modal, no GPU):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Run

Version 2, step 1 — new theme takes from `prompts/theme.txt` with a new
base seed (defaults: 4 takes × 30 s, large model):

```powershell
.\.venv\Scripts\modal.exe run musicgen_modal.py::takes --base-seed 3100
```

Version 2, step 2 — compose the whole piece from the take you pick
(defaults: 180 s total, 108 BPM):

```powershell
.\.venv\Scripts\modal.exe run musicgen_modal.py::compose --take-path out\take-001-seed3100.wav
.\.venv\Scripts\modal.exe run musicgen_modal.py::compose --take-path out\take-001-seed3100.wav --total-seconds 180 --bpm 108 --base-seed 5100
```

If a compose ever fails at the join, the generated sections are already
in `out/`; redo the join on this machine — no GPU, no Modal, no torch:

```powershell
.\.venv\Scripts\python.exe musicgen_modal.py join --development out\section-development-from-take-001-seed3100.wav --reprise out\section-reprise-from-take-001-seed3100.wav --take-path out\take-001-seed3100.wav
```

Variations:

```powershell
.\.venv\Scripts\modal.exe run musicgen_modal.py::takes --count 6 --duration 30 --base-seed 2000
.\.venv\Scripts\modal.exe run musicgen_modal.py::takes --model facebook/musicgen-stereo-medium
.\.venv\Scripts\modal.exe run musicgen_modal.py::takes --prompt-file prompt.txt
```

Extend the take you pick to 185 s (name the actual file in `out/`):

```powershell
.\.venv\Scripts\modal.exe run musicgen_modal.py::extend --take-path out\take-001-seed1234.wav
.\.venv\Scripts\modal.exe run musicgen_modal.py::extend --take-path out\take-001-seed1234.wav --target-seconds 185 --base-seed 1234
```

Outputs appear in `out/`, for example `out/take-001-seed3100.wav` +
`out/take-001-seed3100.json`,
`out/extended-from-take-001-seed1234.wav` + its `.json`, and
`out/composed-from-take-001-seed3100.wav` + its `.json`.

## Afterwards

Once the video is done, delete the cached model weights (the next run
would download them again):

```powershell
.\.venv\Scripts\modal.exe volume delete odin-musicgen-weights
```

## Rough cost on Modal

Modal bills GPU time by the second; an A10G is roughly US$1.10/hour at
the time of writing (prices change — check Modal's pricing page). On
that basis:

- **Takes (4 × 30 s):** about 5–15 minutes of GPU including model load,
  so roughly **US$0.10–0.30**. The first run also builds the cloud image
  and downloads the weights into the Volume; that is mostly one-off, and
  the stereo-large weights are several GB stored in the Volume at
  Modal's storage rates (cents per month at this size).
- **Compose (180 s):** development plus reprise with two model loads,
  roughly 15–30 minutes of GPU, so roughly **US$0.30–0.60**. The first
  compose also downloads the melody model's weights into the Volume.
- **Extend (to 185 s):** about 8 windows of generation, roughly
  10–25 minutes of GPU, so roughly **US$0.20–0.50**.

Expect well under US$1 per command in practice. The 30-minute timeout
caps a runaway job at roughly US$0.55 of A10G time.

## Tests

[tests/test_musicgen_modal.py](tests/test_musicgen_modal.py) covers
everything that can be checked without Modal: reading `prompt.txt`
(including that it holds the Director's exact text), distinct seeds,
output names that never overwrite, the sidecar JSON's fields and the
WAV's SHA-256, and the overlapping-window extension plan. Every check
has a planted red case beside it (empty prompt, duplicate seeds, a
tampered WAV, a missing JSON field, an already-taken file name, …) that
must be rejected. Version 2 adds: the three `prompts/` files hold their
exact texts, the composition plan adds up to the total with the
crossfade and fade-out on bar lines at 108 BPM, and the equal-power
crossfade keeps a steady level for uncorrelated signals (a linear
crossfade is planted as the red case — it dips mid-fade and fails).
Sections a few samples short, a few samples long, and exact are also
tested to assemble to exactly the planned total with the crossfade on
its bar line, and generation requests are tested to round up to whole
codec frames. The suite also checks the cloud image's pins
(torch/torchaudio versions AudioCraft 1.3.0 can actually install with,
plus the FFmpeg build libraries for `av`) and that the container's
16-bit PCM WAV encoding is readable by Python's `wave` module. They
were run failing first (module not yet written), then passing:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## License and credit

MusicGen's code is MIT-licensed and its model weights are licensed
CC-BY-NC 4.0. They are used here for a noncommercial, open-source demo.

Credit line for the video's description:

> Music generated with Meta's MusicGen (AudioCraft); model weights licensed CC-BY-NC 4.0.
