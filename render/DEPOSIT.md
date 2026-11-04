# ANIM-05 — A6 to A9C, and the Modal finals (materials, render_modal.py, scored pane clips, pull-back)

Deposit 05 of the animation session, for committal unchanged into
`render/`. It supersedes ANIM-04 in contents and brings the
repository's `render/` from before A6 up to the animation as it
stands after A9C, whose pull-back closes the published demo video.
Like ANIM-02 to ANIM-04 it carries **no `.blend`**: the scripts
rebuild every scene. ANIM-01 to ANIM-04 and their deposit notes stay
where they are, untouched. **No change in this deposit alters how
anything renders**: A10 fixed only `LICENSE.md`, `README.md`, test
skip guards for a deposit without its inputs, and this note.

## What changed since ANIM-04, milestone by milestone

- **A6 — the materials pass (30 October 2026).** Cell grid, brushed
  metals, glass and faceted foil moved into `build_a1.py`'s
  materials; coverglass glint off the arrays; AgX highlight roll-off;
  bus-face lettering in plate and paint styles (`--closeup`,
  `--busface` still modes in `build_a5.py`), then the materials-pass
  animation of `dev-ph2-p3-open-01`. The Director settled A6 as the
  video's look ("A6 is the look, and it goes into the video as it
  stands") in the A7 direction.
- **A7 — the final clean cut on Modal (`render_modal.py`).** The
  cloud renderer, after the music folder's pattern: pinned Blender
  5.2.3 LTS (Linux x64) verified against Blender's published
  SHA-256 in the image build, inputs verified in the container
  against `inputs/MANIFEST.sha256`, one L40S, `--require-gpu` so a
  GPU-less machine stops instead of rendering on the CPU, H.264 at
  Blender's perceptually lossless setting (`--perceptually-lossless`;
  both switches default to the old behavior), a three-frame probe
  and a $15 cost cap, results to `out/final/` never overwriting.
  **A7B** made the probe read each frame's own render time from
  Blender's output, so the projection counts start-up once
  (start-up + 426 x mean frame time), with a stated whole-time
  fallback; the README records OptiX where offered, CUDA otherwise.
- **A8 — the scored run's pane clips.** `PH2-PASS3-SPARK-R2`'s
  timeline joined the inputs by its SHA-256
  (`d0f1a57349d60cbee5835f3bac6a945e02762ecf49387ebca6caa968d12fe617`),
  manifest and epochs updated, and `orbit_path_for` gives
  `PH2-PASS3-*` the P3 orbit. The MET step need not be whole: it is
  carried exactly, as a fraction, through `sync.py`, `build_a5.py`,
  `render_clip.py` and the sync file, whole steps byte-identical to
  before. `render_modal.py` takes the run, cut, size, span, step
  and clip name — no arguments still means the A7 final — and each
  render keeps its own probe timing for its cost cap. Two
  instrument clips at 1024 x 576: the site clip (MET 800-1225, one
  second a frame) and the footage clip (MET 880-1000, 1/15 s a
  frame, 1,801 frames). **A8B** made cue flashes last two frames or
  two seconds of MET, whichever is longer (30 frames at 1/15 s;
  whole steps unchanged).
- **A9 to A9C — the pull-back.** A third cut, `pullback`, beside
  `clean` and `instrument`: camera only, starting on the clean
  cut's framing (about 3 m, 85 mm), easing out at a log pace with
  the lens widening to 40 mm, per-frame clip distances, finer Earth
  tessellation, spacecraft at true size vanishing with no marker,
  ending on the whole sunlit disc at 0.84 of the frame height.
  **A9B** diagnosed the hazy probe frame: probe progress was spread
  over the probe's own three frames, compressing the whole move so
  motion blur smeared the sunlit Earth; progress is now measured
  against the full pull-back span end to end, and the pull-back
  renders without motion blur. **A9C** held the limb in frame
  through the middle (black space and Earth's curve through frame
  160), swinging to the center only in the last third. Frames 1
  and 241 were unchanged by A9B/A9C and are pinned by tests.
- **A10 — this deposit.** Documentation accuracy only: `LICENSE.md`
  covers every script and test deposited, `README.md` says plainly
  what the deposit leaves out, and tests that need a left-out input
  or rendered output skip with a stated reason, so the suite runs
  from a fresh unzip alone.

## The three Modal renders the video and the site use

Each was run by the Director from the animation workspace (probe
first, as in `README.md`); Muse Code never ran Modal. Commands
are the full-render commands, prefixed as run:
`.\.venv\Scripts\modal.exe run render_modal.py ...`

- **Clean cut (the video's opening and closing shots).**
  Command: no further arguments (the A7 default:
  `dev-ph2-p3-open-01`, clean, 1920 x 1080, MET 800-1225 at 1 s,
  426 frames). App `ap-57eFEhSIfPfZlf0c130iTl`.
  `dev-ph2-p3-open-01_final_clean.mp4` SHA-256
  `088d2cfae7dd7d36b7be96fb4b7a717c7920bdf7299e78693435655d1727656b`.
  Returned 2 November 2026: 426 frames, OPTIX on an NVIDIA L40S,
  perceptually lossless.
- **Instrument footage (the video's first incident).**
  Command: `--run-id PH2-PASS3-SPARK-R2 --cut instrument --width
  1024 --height 576 --met-start 880 --met-end 1000 --met-step 1/15
  --clip PH2-PASS3-SPARK-R2_instrument_footage.mp4`.
  App `ap-6ntCogJZAZdPG13MuXsm7K`.
  `PH2-PASS3-SPARK-R2_instrument_footage.mp4` SHA-256
  `59e69c6dc705321f4ba34daabe1bed5a65461b8ec8eedb2776701116aa859a84`.
  1,801 frames; its sync file pins the scored timeline
  (`d0f1a573...`).
- **Pull-back (the video's last shot).**
  Command: `--run-id PH2-PASS3-SPARK-R2 --cut pullback --width
  1920 --height 1080 --met-start 1150 --met-end 1158 --met-step
  1/30 --clip PH2-PASS3-SPARK-R2_pullback.mp4`.
  App `ap-41k4LPTHgkCLzjlBYcWCz5`.
  `PH2-PASS3-SPARK-R2_pullback.mp4` SHA-256
  `8426ec32ad73f18eb53d134f72bbec3b086c4a487311d68cc5567174010e0eee`.
  241 frames, rendered cleanly 3 November 2026 after A9C.

(The site clip `PH2-PASS3-SPARK-R2_instrument_site.mp4` also
rendered under A8, SHA-256
`cc0432f4598f10af8c3d6f3dca5c5a9236b98481ca3918db22802baeef12a09b`.)

## Tests run, with results (4 November 2026)

`python tests/show_red.py` — exit 0. **58 tests pass; all 59 red
cases ran and failed first as required** (brief rule 8), covering
everything since ANIM-04 among the rest: the GPU and encoding
switches and their defaults, the manifest refusal, frame-time
projection with its whole-time-red plant, probe range, cost cap,
no-overwrite, the scored input's hash/manifest/epochs, the PASS-3
orbit, fractional steps exact and whole steps unchanged, the cue
flash length, Modal defaults unchanged, per-render probe timings,
pull-back distance without jumps, whole-disc final framing, the
limb held through frame 160, probe progress not spread over its
own frames, and the pull-back's motion blur off.

From a fresh unzip of this deposit alone, with no `inputs/` data
files and no `out/`: **57 tests collect; 30 pass and 27 skip**,
each skip stating the file it needs ("inputs/ and out/ are not in
the deposit"). The skipped checks are the ones that read a real
input or a rendered output: inputs-manifest/station/orbit/scene
report and stills (A1), known moments, no-feed state and the A2
report (A2), Sun agreement and the A2 sync pair (A3), eclipse
darkness and the A4 clip pair (A4), local basis, A5 still report
and fixture look (A5), both animated-frame sweeps (A5/A6 anim),
bus face and close-up (A6), scored input and the two fractional
sync comparisons (A8), and the four pull-back pose checks that
derive their start from the orbit and epochs (A9). In the
animation workspace, with inputs and outputs present, nothing
skips.

## Contents

Scripts (`build_a1.py`, `build_a2.py`, `build_a5.py`,
`render_clip.py`, `render_modal.py`, `scene_spec.py`, `solar.py`,
`sync.py`, `timeline.py`, `truescale.py`), tests (`tests/`,
including the red-case runner and the made-up-fixture timeline),
`README.md`, `LICENSE.md`, `CAPTIONS.md`, `requirements.txt`, this
file as `DEPOSIT.md`, and `MANIFEST.sha256` listing every other
file. As the record of what was rendered from, the deposit also
carries `inputs/MANIFEST.sha256` and `inputs/imagery/SOURCE.md`
and `SOURCES.md` as text. **Left out:** everything else under
`inputs/` (imagery, timelines, orbit and feed files), `out/`,
`.venv/`, `__pycache__/`, `optix7cache.db`, any `.blend`, and the
earlier deposits. Every file in the zip was byte-scanned for keys,
tokens, an absolute path, a user-profile folder and a user name:
none found (the scan's own pattern strings live in the tests, built
at runtime so no test file trips it).

Pre-existing: Blender 5.2.3 LTS (GPL; these scripts are
GPL-3.0-or-later) and Modal client 1.6.3 (`requirements.txt`, local
machine only); the NASA Blue Marble, cloud, and Black Marble
imagery recorded above (credit NASA Earth Observatory; not in this
zip); the VERDA timelines and orbit/epochs inputs (hashes in the
carried inputs manifest; not in this zip); Python's standard
library only otherwise.

Zip SHA-256: recorded here after packing (see the copy of this
note beside the zip, `ANIM-05.DEPOSIT.md` — a file inside a zip
cannot name that zip's own final hash).

## Suggested commit message

```
Add HUGINN animation A6-A9C: materials, Modal finals, pull-back (ANIM-05)

Bring render/ from ANIM-04 to the published video's animation: A6
materials and lettering, render_modal.py (pinned Blender 5.2.3 on
one L40S, GPU-required, perceptually lossless, probe + cost cap),
the scored PH2-PASS3-SPARK-R2 instrument clips with exact
fractional MET steps, and the pull-back closing shot (limb held
through the middle, no motion blur). Inputs are recorded by hash
and source notes only; the scripts rebuild every scene. Tests and
red cases in tests/.
```

(Plus the brief's `Built-with:` line, this deposit's name, and its
SHA-256, as Claude Code adds them.)
