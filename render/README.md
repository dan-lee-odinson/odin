# HUGINN animation — A1: the spacecraft and the scene

Animation work for Project AESIR (ODIN / HUGINN), built with the Blender
workflow per the animation session brief. Milestone A1 is a still-frame
scene: a standard 6U CubeSat with twin solar arrays, Earth, the Sun, the
ground station's location, and the orbit, framed to read clearly at
1920 x 1080. Milestone A2 (the record drives the scene) is built; see
"A2" at the end of this file.

Build record (for each deposit's DEPOSIT.md): A1 was built on Muse Wonder
Full at high effort; A2 on Muse Wonder Full at medium effort, economically,
after the Director's ruling put ODIN's work first; A3 also on Muse Wonder
Full at medium. A1 and A2 as first built are deposited as ANIM-01
(SHA-256 985c1b5d03edcf3c25ce699d77fd05f431199e93d1a75bbdd3ddd176ff051f7e;
held, not committed — its scene file stored a user-profile path). A1 to
A3 are deposited as ANIM-02 without a scene file (SHA-256
a8030f3474e796035e35c954e80016408329d8f0184dd7ff58d558a2aeb4d661); A4 was
built after that deposit, also on Muse Wonder Full at medium, and A1 to
A4 are deposited as ANIM-03 (SHA-256
b9c7fab50e3de74d539a4e8e08efcaf892431f8de36534b541f639039ecc75ea). A5
(the look pass, its three still rounds, and its animation) was built
after that, also on Muse Wonder Full at medium.

## Run it

With Blender (built and tested with Blender 5.2 LTS) on the PATH, from this
folder:

```
blender -b --factory-startup --python-exit-code 1 -P build_a1.py
```

Modes, passed after `--`: `--preview` (half-size stills, faster),
`--calibrate` (one still looking straight at the ground station; see
Calibration below). A full run writes to `out/a1/`:

| File | What it is |
|---|---|
| `a1_01_wide.png` | Whole Earth, orbit path, ground station marker and label, spacecraft position marker |
| `a1_02_hero.png` | Close three-quarter view of HUGINN on its sunlit side, Earth behind |
| `a1_03_payload.png` | From the foil side: Earth in the lower frame, payload barrel pointing down at it |
| `huginn_a1.blend` | The scene file (Earth texture packed in) |
| `scene_report.json` | Machine-readable facts about the built scene; the tests check it |
| `CAPTIONS.md` | The caption text each still and clip must carry |

Tests (plain Python 3, no Blender needed):

```
python -m unittest discover -s tests
python tests/show_red.py
```

`show_red.py` runs every test's red case first (a planted change that must
make that one test fail — brief rule 8), then the full suite clean.

## What comes from the record, and what is drawn

From `inputs/` (hash-verified against `inputs/MANIFEST.sha256`):

- **Spacecraft size.** 6U = 10 x 22.6 x 36.6 cm, per `inputs/spacecraft.md`.
  The bus is built at those proportions.
- **Orbit.** All 247 rows of `inputs/orbit/P3-orbit.csv` (MET 0-1230 for the
  two phase-2 PASS-3 development runs), as a path at the altitude each row
  gives. Earth is 10 scene units in radius; the orbit's height above it is
  the row altitude against a 6371 km mean Earth radius.
- **Placement.** The spacecraft sits at the orbit row for MET 1000
  (28.0742 N, 77.5194 W, 508.0 km), inside the contact window the orbit
  file marks from MET 800 on, sunlit like the whole P3 run.
- **Ground station.** `GS-RAVENSROOST` at 28.5219 N, 80.6817 W, from
  `inputs/orbit/station.json`.
- **Earth texture.** NASA Blue Marble: Next Generation, July 2004, from
  `inputs/imagery/` (pre-existing; its source and license are in
  `inputs/imagery/SOURCE.md`. Credit: NASA Earth Observatory).

Drawn (the record holds no value for these; brief rule 2):

- **The spacecraft's look**: a standard 6U CubeSat — aluminum rails, dark
  side panels, a gold foil patch, payload barrel and lens on the nadir
  face, patch and stub antennas — with twin deployable arrays, two panels
  each, labeled SA1 and SA2 for the two array strings `EPS_SA1_I` /
  `EPS_SA2_I`. Every caption says the look is drawn.
- **Scale.** Next to Earth the spacecraft is enlarged about 892,000 times
  (the exact factor is in `scene_report.json`), or it would be far below
  one pixel. In the wide still its position is therefore marked with a
  small diamond instead of the model.
- **Pose.** The record carries no attitude, so the craft's nadir-pointing
  pose is fixed and drawn. (In ANIM-01 as deposited, the Sun's direction
  was drawn too; from A3 it is derived from the run's epoch — see A3
  below — and the regenerated stills use the derived Sun.)
- **Dressing**: a soft limb glow and a soft blue "earthshine" fill light
  under the craft, a small drawn Sun disk (wide still only), and labels.

## Coordinate mapping

Scene frame: +Z through the north pole, +X toward (0, 0) latitude/longitude,
+Y toward (0, +90). A point at geodetic latitude/longitude and scene radius
*r* maps by `scene_spec.latlon_to_xyz`. The same pure-Python module
(`scene_spec.py`) holds every constant the Blender script uses, so the
tests can check the math without Blender.

## Calibration

`blender ... -P build_a1.py -- --calibrate` renders one still from above the
ground station. With `EARTH_TEXTURE_ROTATION_DEG = 0.0` the station pin
sits on Florida's Cape coast and the MET-1000 marker sits offshore in the
Atlantic at the right latitude, so the texture lines up with the mapping
above. This was checked visually against that still; the tests pin the
rotation value and the station's scene position so a silent drift fails.

## Rules kept

- Read-only: the scripts read `inputs/` and write only under `out/`. No
  network, no commands sent anywhere, no keys (a test scans for this).
- No downloads, no paid calls, no cloud jobs: previews and finals rendered
  locally with EEVEE.
- No absolute paths, user-profile folders, or user names in any file (a
  test scans for this).
- American spelling in everything a reader sees.

## A2: the record drives the scene

`timeline.py` reads one VERDA timeline and gives the spacecraft state at
any MET; `build_a2.py` keyframes the A1 scene from it at a fixed 5 s MET
step (chosen to match the orbit rows and keep the preview cheap: 87 frames
at 10 fps, 640 x 360). It shows position along the orbit; sunlight and
eclipse on the craft and its arrays (the craft has its own sun light, so
an eclipse darkens it alone); a link line while the record says contact;
the payload lens lit while the payload is on; a mode beacon (green
NOMINAL, amber LOW_POWER, red SAFE); a load bar colored by `EPS_LOAD_I`'s
limit state; each wing's cells brightening with its own string's current;
brief cue flashes when ODIN requests and BALDUR-0 decides (green allow,
red deny; VERDA carries the text); and space weather as particles scaled
by proton flux, only when a feed is handed in with `--feed`.

```
blender -b --factory-startup --python-exit-code 1 -P build_a2.py
blender -b --factory-startup --python-exit-code 1 -P build_a2.py -- --fixture
```

The preview is `dev-ph2-p3-open-01`: contact from MET 800, the load going
YELLOW_HIGH at 900 (1.8 A), ODIN's shed at 912, BALDUR-0's ALLOW and the
dispatch, then the payload off and the load back to GREEN at 913 (1.2 A).
The run's telemetry starts at contact, so the preview covers MET 800-1230;
before that the record holds no spacecraft state to show. Spacecraft state
reads the timeline's `truth` source. That run was sunlit and NOMINAL
throughout and carries no feed, so eclipse, safe mode, a deny, and space
weather are exercised only by `--fixture`, on
`tests/fixtures/made_up_timeline.json` with the made-up feed (three stills
in `out/a2/`), never drawn over a real run. Phase 1's R4 flew a demo target
with no orbit, so the driver refuses it rather than inventing a position.
A1's fixes from the Director's review (station label with leader line, a
labeled HUGINN marker, soft limb glow, smooth high-resolution limb, the
reframed payload view, smaller Sun disk) are folded into `build_a1.py`.

## A3: the sync file, and the derived Sun

Beside the preview clip the driver writes
`dev-ph2-p3-open-01_preview.sync.json`: the run's ID, the timeline's
SHA-256 (of the file's bytes), the first frame's MET (800), the MET step
(5 s), and the frame rate (10 fps). Frame *i* (1-based) is at
MET = first + (i − 1) × step; a test checks every keyframed frame against
that (*tests/test_a3.py*).

From A3 the Sun's direction is no longer drawn. `solar.py` computes the
sub-solar point from the run's UTC epoch (`inputs/epochs.json`: MET 0 =
2026-08-01T13:28:23Z) with the NOAA low-precision series, standard library
only. A test checks the derived cylindrical-shadow sunlight against the
record's `ADM_ECLIPSE` at all 86 orbit rows the record covers (it agrees),
and that six hours earlier the same geometry is night. Where the record
and the geometry would disagree, the record wins. Folded fixes from the
Director's A2 review: no Sun disk in the preview (never in front of
Earth), the follow camera pulled back with the horizon kept level, the
eclipse craft kept readable on stronger earthshine, and space weather
drawn as fine streaks scaled by flux. Earth now uses the 21600 x 10800
input texture for close shots.

## A4: the render script

`render_clip.py` is the headless entry point for a cloud run. It takes
everything as arguments — `--timeline`, `--inputs`, `--output`,
`--width`, `--height`, `--met-start`, `--met-end`, `--met-step`, `--fps`,
`--engine` (`BLENDER_EEVEE` or `CYCLES`), `--samples`, `--feed`,
`--blender` — builds the scene from these scripts (no `.blend` needed),
renders, and leaves the clip with its sync file and frame report in the
output folder. `--dry-run` prints the Blender command. It holds no key.
Verified locally at preview size: a 9-frame clip over MET 890-930 of
`dev-ph2-p3-open-01` in `out/a4/`.

Eclipse readability (Director's A4 fix): in eclipse the craft's own sun
drops to near nothing, the earthshine fill stays faint, and an
eclipse-only rim light keeps the outline — every part darker than in
sunlight. A test decodes the fixture stills (MET 890 sunlit, MET 920
eclipse) and fails when the eclipse spacecraft region is not darker; it
caught the A3 cut, where eclipse measured brighter (75.0 vs 74.1).

## A5: the look pass (one frame first)

`build_a5.py` renders one follow-shot moment at true scale: the
spacecraft at its real size at the origin, Earth (6,371 km radius) moved
around it, camera about 3 m away on an 85 mm lens looking down about 26
degrees so the horizon crosses the frame. Cycles, a hard sun from the
derived direction, earthshine fill from below, AgX, slight bloom, motion
blur on. Earth carries the 21,600-pixel Blue Marble, a cloud shell 8 km
up casting shadows, Black Marble night lights fading in across the
terminator, a water glint from a mask derived from the Blue Marble
itself, and a thin limb glow; clouds and night lights are NASA
composites, not the run's date, and are captioned so. Two cuts from the
same scene (`--cut` on `render_clip.py`, the same switch here): clean
(camera only) and instrument (data cues kept: beacon, load bar, soft
contact beam toward the station; no station marker in the follow shot).
Space weather in clips is drawn as brief white camera strikes whose rate
follows the feed's flux. Per the Director, one moment (MET 900: sunlit,
in contact, load YELLOW_HIGH) was rendered as stills in both cuts and
animation of the look pass waits for the Director's word. Finals will run
at 30 fps with position smoothed between orbit rows; state changes stay
on their record times.

Round two (the Director's seven notes on the first frame): the camera
moved down-Sun for rim light and deep shadows with the Sun out of frame;
cells are deep blue-black with silver grid lines in the gaps; the limb
glow rolls off before the silhouette and ground haze fades distant land
into blue; clouds got a wide soft ramp; the clean cut carries no text
including painted plates; the contact link is a thin glowing line from
the antenna, never over the craft; the amber load color is saturated;
and space weather is 1-3 pixel sensor strikes of varied brightness. The
fixture stills were redrawn through this same true-scale scene
(`build_a5.py --fixture --met 890|920|945`).

Round three (the Director's notes on round two): side light instead of
down-Sun — the camera sits south of the craft and somewhat sunward, so
one face is lit and the other in shadow, and Earth keeps round one's
daylight colors (the water roughness floor was raised so side-lit ocean
no longer mirrors black space, and the haze was cut back). The camera
also moved to the cell side, so the cell grid reads with silver lines in
the gaps; the foil got object-space crinkle driving bump and roughness;
clouds are shaded by their own brightness under a capped soft ramp; the
link line starts at the patch antenna's own position; and the eclipse
fill and rim dropped so eclipse reads clearly against sunlight in the
890/920 fixture pair. Round three worked at 960 x 540.

Animation (the Director's go-ahead after round three): `build_a5.py
--animate` keyframes this same scene across a run's MET range — Earth
moving around the craft at the origin, derived Sun and terminator,
record state on the craft, the antenna-anchored link, brief ODIN and
BALDUR-0 cue flashes in the instrument cut, and feed-only sensor
strikes. Transform curves interpolate smoothly; record-state curves are
constant, so every state change lands on its record MET.
`render_clip.py` drives this mode and resolves every path argument to
an absolute path itself (relative arguments used to fail). Also folded
in: a thinner limb glow, and the wing labels moved one panel in from
the tips so the frame does not clip them. The first animated run is
`dev-ph2-p3-open-01` (MET 800-1225, 86 frames, both cuts with sync
files in `out/a5anim/`), because no scored PASS3 run's timeline is in
the animation inputs; the same command renders a scored run unchanged
when its timeline arrives. Where a run's epoch is marked shifted in
`inputs/epochs.json`, its caption says the Sun is set to agree with the
run's record, not the campaign clock (see `CAPTIONS.md`); the PASS-3
runs are not shifted.

## License

The scripts in this folder drive Blender and are licensed under the
GNU General Public License, version 3 or later (GPL-3.0-or-later),
compatible with Blender's own license (see `LICENSE.md`). The NASA Earth
texture is pre-existing material under the terms in
`inputs/imagery/SOURCE.md`; it is packed into the scene file for
convenience and must keep its credit.
