# ANIM-04 - A1 to A5 (scene, record driver, sync file, derived Sun, cloud render script, true-scale look pass animated)

Deposit 04 of the animation session, for committal unchanged into
`render/`. It supersedes ANIM-03 in contents (A5 added). Like ANIM-02
and ANIM-03 it carries **no `.blend`** (the Director's ruling, replacing
"scene file" in the brief's deposit list, section 6): `build_a1.py`
rebuilds the A1 scene file and `build_a5.py` builds the true-scale
scene from script. ANIM-01, ANIM-02 and ANIM-03 and their deposit
notes stay where they are, untouched.

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
  and setting as an argument, with the eclipse-darkness fix.
  Muse Wonder Full, medium effort. Director saw A4's short clip, its
  sync file, and the sunlit/eclipse fixture stills on 29 October 2026.
- **A5**: the look pass. One true-scale follow-shot scene (spacecraft at
  its real size at the origin, Earth moved around it, Cycles, derived
  Sun, cloud shell, night lights, water glint, limb glow) in clean and
  instrument cuts, taken through three still rounds on the Director's
  notes (down-Sun rim light, then side light with round one's Earth
  colors, cell grid, antenna-anchored link line, clearly darker
  eclipse), then animated: `build_a5.py --animate` keyframes the scene
  across a run's MET range with record-state changes on their record
  times, driven by `render_clip.py`, which now resolves every path
  argument itself. Also folded in at animation: a thinner limb glow and
  wing labels moved one panel in from the tips.
  Muse Wonder Full, medium effort, throughout. **Director saw the
  round-three stills, then both animated clips, on 30 October 2026, and
  approved the look, keeping the ground motion blur and the link's wide
  translucent band.**

The animated run is `dev-ph2-p3-open-01` (MET 800-1225, 86 frames at
960 x 540, 48 samples, 10 fps, both cuts each with its sync file),
because no scored PASS3 run's timeline is in the animation inputs
(`epochs.json` marks every `PH2-PASS3-*` timeline not in inputs); the
Director's fallback named this run. The same `render_clip.py` command
renders a scored run unchanged when its timeline arrives. That run's
epoch is not shifted and it carries no feed, so its clips show no space
weather. Where a run's epoch is marked shifted, `CAPTIONS.md` now says
the Sun is set to agree with the run's record, not the campaign clock.

## Tests run, with results (30 October 2026)

`python tests/show_red.py` - exit 0. All 24 tests pass clean; all 25
red cases ran and failed as required (brief rule 8). Beyond ANIM-03's
list, A5 adds three tests and six red cases:

- True-scale geometry (local east/north/up basis, Earth center below
  the craft). Red case `a5_zenith_pointed_down`.
- The two cuts are one `--cut` argument end to end. Red case
  `a5_cut_argument_dropped`.
- The MET 900 still report and files (both cuts, Cycles, record state).
  Red case `a5_report_wrong_met`.
- The redrawn fixture stills carry 1-3 pixel sensor strikes. The first
  measure (near-white pixels in a sky band) failed on the true-scale
  framing, where Earth fills that band and the denoiser softens each
  speck; the check now counts small bright blobs ringed by dark
  pixels, tightened until a strike-less still of the same size fails
  it. Red case `a5_fixture_still_replaced`.
- `render_clip.py` resolves relative path arguments to absolute ones
  (Claude Code's run failed with relative paths). The updated command
  test was watched failing on the old code first. Red case
  `a4_relative_paths_unresolved`.
- Both animated clips: every frame's MET follows its sync file, and
  every frame's recorded state (sunlight, mode, payload, load limit,
  contact) equals the timeline's own state at that MET, with the known
  MET 900 moment (YELLOW_HIGH, in contact) pinned. The test was watched
  failing before the clips existed. Red case
  `a5anim_sync_step_doubled`.

Also verified by eye, from stills extracted out of the finished clips:
Earth drifting beneath the craft, the link tracking the station from
the antenna, amber strips at MET 900, both cue flashes at the MET 912
frames with the load back to green after the shed, and a text-free
clean cut. All rendering stayed local (Cycles on the laptop's GPU,
falling back to CPU elsewhere). No downloads, no paid calls, no cloud
jobs.

## Contents

Source (`build_a1.py`, `build_a2.py`, `build_a5.py`, `render_clip.py`,
`scene_spec.py`, `timeline.py`, `solar.py`, `sync.py`, `truescale.py`),
tests (`tests/`, red-case runner and fixture), `README.md`,
`LICENSE.md`, `CAPTIONS.md`, this file as `DEPOSIT.md`, and
`MANIFEST.sha256` listing every other file. **No `.blend`.** Left out:
`inputs/`, rendered frames and clips, caches. Every file in the zip
was byte-scanned (ASCII and UTF-16) for an absolute path, a
user-profile folder, and a user name: none found.

Pre-existing: Blender (GPL; these scripts are GPL-3.0-or-later); the
NASA Blue Marble, cloud, and Black Marble imagery in
`inputs/imagery/` (credit NASA Earth Observatory; not in this zip);
Python's standard library only. A6 will use Blender's own procedural
textures only, per the Director, so no new asset is expected.

## Suggested commit message

```
Add HUGINN animation A5: true-scale look pass, animated (ANIM-04)

A5 puts the spacecraft at its real size with Earth 500 km below:
derived Sun, cloud shell, night lights, water glint, limb glow, in
clean and instrument cuts. build_a5.py --animate keyframes the scene
from a run's record with state changes on their record times;
render_clip.py drives it and resolves every path argument itself.
No .blend: the scripts rebuild the scene. Tests and red cases in
tests/.
```

(Plus the brief's `Built-with:` line, this deposit's name, and its
SHA-256, as Claude Code adds them.)
