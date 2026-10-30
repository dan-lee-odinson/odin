# ANIM-03 — A1 to A4 (scene, record driver, sync file, derived Sun, cloud render script)

Deposit 03 of the animation session, for committal unchanged into
`render/`. It supersedes ANIM-02 in contents (A4 added). Like ANIM-02 it
carries **no `.blend`** (the Director's ruling of this session, replacing
"scene file" in the brief's deposit list, section 6): `build_a1.py`
rebuilds the scene file. ANIM-01 and ANIM-02 and their deposit notes stay
where they are, untouched.

## Milestones and build record

- **A1**: the 6U CubeSat and its scene as 1920 x 1080 stills.
  Muse Wonder Full, high effort. Director saw the frames 29 October 2026.
- **A2**: the record drives the scene at a 5 s MET step, with a
  low-resolution preview of `dev-ph2-p3-open-01`.
  Muse Wonder Full, medium effort. Director saw the preview
  29 October 2026.
- **A3**: the sync file beside each clip, and the Sun's direction derived
  from the run's UTC epoch (`inputs/epochs.json`) with a low-precision
  solar formula, checked against the record's `ADM_ECLIPSE`.
  Muse Wonder Full, medium effort. Director saw the preview and sync
  file 29 October 2026.
- **A4**: `render_clip.py`, the headless render script taking every path
  and setting as an argument (timeline, inputs, output, resolution, MET
  range, step, fps, engine, samples), building the scene from these
  scripts, rendering, and writing clip + sync + report. With the eclipse
  fix: the craft is darker in eclipse on every part, kept readable by a
  faint fill and an eclipse-only rim light.
  Muse Wonder Full, medium effort. **Director saw A4's short clip, its
  sync file, and the sunlit/eclipse fixture stills on 29 October 2026.**

## Tests run, with results (29 October 2026)

`python tests/show_red.py` — exit 0. All 19 tests pass clean; all 19 red
cases ran and failed as required (brief rule 8). Beyond ANIM-02's list,
A4 adds three tests and three red cases:

- The eclipse-darkness test decodes the fixture stills (MET 890 sunlit,
  MET 920 eclipse) and compares the spacecraft region. On the A3 cut it
  measured eclipse **brighter** than sunlit (75.0 vs 74.1) and failed;
  after the fix it passes. Red case `a4_eclipse_still_swapped` plants the
  sunlit still under the eclipse name.
- `render_clip.py`'s command carries every setting, and refuses a missing
  timeline. Red case `a4_command_drops_samples`.
- The locally rendered short clip (MET 890-930, 9 frames, 640 x 360) and
  its sync file agree frame for frame. Red case `a4_sync_step_doubled`.

Also verified by eye: the eclipse still next to the sunlit one (dark
arrays, dim readable body, red load bar) and the short clip's sync values.
All rendering stayed local at preview size. No downloads, no paid calls,
no cloud jobs; the cloud engine and GPU choice is Claude Code's timing
test on Modal, per the Director.

## Contents

Source (`build_a1.py`, `build_a2.py`, `render_clip.py`, `scene_spec.py`,
`timeline.py`, `solar.py`, `sync.py`), tests (`tests/`, red-case runner
and fixture), `README.md`, `LICENSE.md`, `CAPTIONS.md`, this file as
`DEPOSIT.md`, and `MANIFEST.sha256` listing every other file. **No
`.blend`.** Left out: `inputs/`, rendered frames and clips, caches. Every
file in the zip was byte-scanned (ASCII and UTF-16) for an absolute path,
a user-profile folder, and a user name: none found.

Pre-existing: Blender (GPL; these scripts are GPL-3.0-or-later); the NASA
Blue Marble textures in `inputs/imagery/` (credit NASA Earth
Observatory; not in this zip); Python's standard library only.

## Suggested commit message

```
Add HUGINN animation A1-A4: scene, driver, sync, cloud script (ANIM-03)

A1 builds the 6U spacecraft and scene; A2 keyframes it from a VERDA
timeline; A3 adds the sync file and derives the Sun from each run's UTC
epoch; A4 is the argument-driven headless render script, with the
eclipse-darkness fix. No .blend: the scripts rebuild the scene.
Tests and red cases in tests/.
```

(Plus the brief's `Built-with:` line, this deposit's name, and its
SHA-256, as Claude Code adds them.)
