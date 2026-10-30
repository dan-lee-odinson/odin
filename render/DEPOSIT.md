# ANIM-02 — A1, A2, and A3 (scene, record driver, sync file and derived Sun)

Deposit 02 of the animation session, for committal unchanged into
`render/`. It supersedes ANIM-01, which is held and will not be committed:
its scene file stored a user-profile path. Per the Director's ruling, no
deposit carries a `.blend` from now on — `build_a1.py` rebuilds it. That
ruling replaces "scene file" in the brief's deposit list (section 6).
ANIM-01.zip and its DEPOSIT.md stay where they are, untouched.

## Milestones and build record

- **A1**: the 6U CubeSat and its scene as 1920 x 1080 stills.
  Muse Wonder Full, high effort. Director saw the frames 29 October 2026.
- **A2**: the record drives the scene at a 5 s MET step, with a
  low-resolution preview of `dev-ph2-p3-open-01`.
  Muse Wonder Full, medium effort. Director saw the preview
  29 October 2026.
- **A3**: the sync file beside each clip (run ID, timeline SHA-256, first
  frame MET, MET step, frame rate), and the Sun's direction derived from
  the run's UTC epoch in `inputs/epochs.json` with a low-precision solar
  formula, checked against the record's `ADM_ECLIPSE`.
  Muse Wonder Full, medium effort. **Director saw A3's preview and sync
  file on 29 October 2026.**

## Tests run, with results (29 October 2026)

`python tests/show_red.py` — exit 0. All 16 tests pass clean; all 16 red
cases ran and failed as required (brief rule 8):

- A1 (9): input manifest; latitude/longitude math; station on Earth's
  surface; orbit known moments; 6U proportions; scene report against the
  inputs; stills at 1920 x 1080; no absolute user paths; read-only build.
- A2 (5): open-01 known moments (contact 800, load YELLOW_HIGH 900, shed
  and ALLOW 912, payload off and load GREEN 913); fixture eclipse, safe
  mode, red limit, deny; no feed, no weather; phase 1 has no orbit; the
  preview report's 87 frames carry the timeline's state.
- A3 (2): the derived Sun agrees with `ADM_ECLIPSE` at all 86 orbit rows
  the record covers (and is night six hours earlier); the sync file's
  frame for frame METs match the keyframed frames, hash included.
- Red cases (16): manifest_hash_mismatch,
  latlon_longitude_sign_flipped, station_longitude_sign_flipped,
  orbit_interpolates_from_next_row, cubesat_bus_too_wide,
  report_missing_sun, still_wrong_size, absolute_user_path_planted,
  build_reaches_network, a2_sample_misses_exact_met,
  a2_eclipse_read_backwards, a2_weather_from_nowhere,
  a2_phase1_given_an_orbit, a2_report_frame_dropped,
  a3_sun_longitude_backwards, a3_sync_frame_off_by_one.

Also verified by eye: the regenerated A1 stills; sampled frames of the A3
preview (level horizon, pulled-back camera, no Sun disk); fixture stills
for eclipse and space weather as radiation streaks. All rendering was
local in Blender 5.2 LTS (EEVEE). No downloads, no paid calls, no cloud
jobs.

## Contents

Source (`build_a1.py`, `build_a2.py`, `scene_spec.py`, `timeline.py`,
`solar.py`, `sync.py`), tests (`tests/`, red-case runner and fixture),
`README.md`, `LICENSE.md`, `CAPTIONS.md` (the video's captions come from
it; corrected this deposit: the wide still's marker is a labeled dot, and
the Sun's direction is computed from the run's UTC time), this file as
`DEPOSIT.md`, and `MANIFEST.sha256` listing every other file. **No
`.blend`.** Left out: `inputs/`, rendered frames and clips, caches.
Every file in the zip — not only the text files — was byte-scanned for
an absolute path, a user-profile folder, and a user name: none found.

Pre-existing: Blender (GPL; these scripts are GPL-3.0-or-later); the NASA
Blue Marble textures in `inputs/imagery/` (credit NASA Earth
Observatory; not in this zip); Python's standard library only.

## Suggested commit message

```
Add HUGINN animation A1-A3: scene, record driver, sync file (ANIM-02)

A1 builds the 6U spacecraft and scene; A2 keyframes it from a VERDA
timeline; A3 adds the sync file VERDA's pane reads and derives the Sun
from each run's UTC epoch. No .blend: build_a1.py rebuilds the scene.
Tests and red cases in tests/.
```

(Plus the brief's `Built-with:` line, this deposit's name, and its
SHA-256, as Claude Code adds them.)
