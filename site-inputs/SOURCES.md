# The replay site's inputs

Placed 3 November 2026 by the Director's word of that day: the three files the replay site's build reads that are not
already among this repository's records. `.github/workflows/pages.yml` gives them to `viewer/site/build_site.py`, with
the run folders in `runs/scored/`, the Director's passes in `inputs-pre-existing/comparison-only/pass-records/`, the
five phase-2 plans in `plans/`, and HUGINN's dictionary, which the workflow fetches from HUGINN's commit `b4dbe61` and
checks by its SHA-256.

| File | Dated | Source | SHA-256 |
|---|---|---|---|
| `PH2-PASS3-SPARK-R2_instrument_site.mp4` | 2026-11-02 | the animation session's `out/final/`, copied from there by VERDA into its `inputs/clips/`; H.264, 1024 x 576, 426 frames | `sha256:cc0432f4598f10af8c3d6f3dca5c5a9236b98481ca3918db22802baeef12a09b` |
| `PH2-PASS3-SPARK-R2_instrument_site.sync.json` | 2026-11-02 | the clip's sync file, from the same folder by the same way | `sha256:ea62af066346a75ba20bb4355ad9d7725f2cc91b252bde20dc1318f1d70cf670` |
| `phase2_scripted_commands.json` | 2026-10-29 | derived by Claude Code from HUGINN's `sim/scenarios/` at `b4dbe61`, as below, and given to VERDA in its `inputs/scripted-commands/` | `sha256:2347479e847ab284d196173adbeed8602c9d3fae226834c9124492f3bc0483e3` |

Each is copied from VERDA's inputs byte for byte, and each hash is the one the Director gave. They were scanned first
for private identity details (`tools/identity_scan.py`), which found none.

**The clip.** It was rendered on Modal on 2 November 2026 (app `ap-N9QvwXFJlHev8hXrcNaYpy`) by the animation session's
renderer: Blender 5.2.3 LTS, Cycles at 48 samples on an L40S. It is the instrument cut of PH2-PASS3-SPARK-R2, MET 800
to 1225, one second of MET a frame, 426 frames at 1024 x 576. Its sync file pins the run's timeline,
`sha256:d0f1a57349d60cbee5835f3bac6a945e02762ecf49387ebca6caa968d12fe617`, the file VERDA's converter makes from
`runs/scored/PH2-PASS3-SPARK-R2/`. The build stops unless it makes those same bytes, and the page plays the clip only
beside them.

**Its caption.** Under the clip, the site's page says: "The animation shows simulated data drawn from the run's own
record. The spacecraft's look and pose are drawn." Its "Full caption" link opens the renderer's whole caption, which
`viewer/site/build_site.py` carries.

**Its license.** The clip falls under the repository's documentation license, CC BY 4.0. The NASA imagery in it keeps
NASA's terms, as the README's third-party table gives them.

**The scripted commands.** Claude Code derived this file on 29 October 2026, at the Director's word of that day, for
VERDA's page, which shows each phase-2 scenario's own commands on the Director's side of his pass. For each of the five
phase-2 passes, it read the scenario file the pass's plan names, `sim/scenarios/<scenario>.yaml`, at HUGINN's commit
`b4dbe61` with `git show`, and wrote down the commands that file sends by itself: each one's MET, command and
arguments, and the file and line it comes from. No HUGINN file was copied. Each pass's contact window is its TYR-0
plan's (`plans/TYR0-P2-PASS*-v1.yaml`). Whether each command was kept in ODIN's runs was worked out by ODIN's own
simulator code, `split_scripted_commands` in `wrapper/simulator.py`, which applies the Director's ruling on U35
(27 October 2026): a scripted command outside every contact window is kept and one inside a window is dropped, so every
command during a pass is ODIN's. The file's own fields say the same.
