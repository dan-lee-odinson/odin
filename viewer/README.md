# VERDA

VERDA is a watch-only viewer for ODIN's runs. It plays back a finished run's records on one mission-elapsed-time (MET) axis: the contact windows, the telemetry that matters to a pass with its limit states, telemetry age and the ground link, each of ODIN's requests with BALDUR-0's decision, the dispatch and the outcome, and ODIN's reports and escalations beside the Director's check-ins. Beside the run, on the same axis, it shows the Director's own flown pass of the same scenario: the commands he sent, when each went out, what his telemetry showed after it, and his telemetry; and, apart from his, the commands the scenario sent by itself, which his pass carried. Beside the timeline, an animation pane plays the clip rendered from the run on screen, locked to the playhead.

VERDA was written during the Meta Global AI Developer Hackathon by a Claude Code session (the VERDA session), directed by Dan Lee-Odinson, Director. It is new code. It uses no third-party library; its one pre-existing file is the Michroma font (see Pre-existing).

## Use

1. Turn run folders, and the Director's passes, into timeline files:

   ```
   python convert/verda_convert.py --all <folder holding run folders>
   python convert/verda_convert.py --all <folder of runs> --passes <folder of pass folders> --plans <folder of plans> --scripted <scripted-commands file> --clips <folder of clips>
   python convert/verda_convert.py <run folder> [<run folder> ...]
   ```

   Options: `--out DIR` (default `page/timelines`), `--dictionary PATH` (HUGINN's `tlm_cmd.yaml`; found automatically beside VERDA or in the repository's pinned HUGINN), `--no-truth` (leave the simulator truth out), `--passes DIR` (the Director's pass folders; see The Director's flown pass), `--plans DIR` (the plans, for each pass's contact window), `--scripted FILE` (each scenario's own scripted commands; see The scenario's own commands), `--clips DIR` (animation clips, each with its sync file; see The animation pane).

   With VERDA's inputs: `python convert/verda_convert.py --all inputs/runs --passes inputs/pass-records --plans inputs/plans --scripted inputs/scripted-commands/phase2_scripted_commands.json --clips inputs/clips`.

2. Open `page/index.html` from disk in a browser. Pick a run (or a pass of the Director's that no run pairs with yet), then press Play. A run opens on its pass, its contact windows and a little either side; "Whole run" (or `0`) shows all of it.

Keys: Space plays and pauses; Left and Right step to the previous and next event; Home and End; `+` and `-` zoom around the playhead; `0` shows the whole run. Hover over anything to see what it is; click it to show its record.

A link can open the page at a chosen moment: `index.html#run=<run_id>&met=<seconds>&future=1&truth=0&view=<from>-<to>`.

## The look

The page is drawn as a working spacecraft console: hairline-framed panels with notched corners and corner brackets, section headers in spaced capitals with a short accent bar and a thin rule, boxed readouts with large tabular numbers, segmented gauges, and a faint grid behind the lanes. Titles are set in Michroma; numbers are in a monospace font.

The colors are deep navy panels, cyan hairlines and ice-white text. Status colors keep one meaning (green good, amber caution, red alarm), and decoration is drawn only in lines and thin bars, never filled, hatched or worded. The one amber decoration is the short bar on each section header, kept off the data; the playhead and its MET marker are ice-white. A limit state always carries its name in words, and a shape: a green chip is an outline, a yellow one is filled and pointed on the right, a red one is filled and pointed at both ends; yellow and red limit bands are hatched and named on the chart.

## Watch-only, from disk

- The page is static HTML, CSS and JavaScript. It reads only the files beside it: its own three files, its font, `timelines/index.js`, the timeline file it plays (and its beside file, for a run beside the Director's pass) and that run's animation clip, if one is placed. It makes no network request; its Content-Security-Policy refuses every connection and lets media come only from the page's own folder, and a test opens it in a browser and checks every request it makes.
- The page writes nothing: no storage, no downloads, no forms.
- The converter reads run folders, the Director's pass folders, the plans, the scripted-commands file and the clips folder, and writes one timeline file for each run and for each pass no run pairs with, `<out>/<id>.js`, a beside file for each run paired with a pass, `<out>/<id>.beside.js`, `<out>/index.js`, and a copy of each clip and its sync file in `<out>/clips/`. It never writes into a run folder, a pass folder, a plan, the scripted-commands file or the clips folder.
- Text from the records (ODIN's rationales, reports, the Director's words) is always shown as text, never read as HTML.

## Where each thing on the page comes from

Every line, dot and mark has one source, and the page labels it:

| Source | What it is | How the page shows it |
|---|---|---|
| The event log, `events.jsonl` | Every record the harness and BALDUR-0 wrote | Markers, spans and request chains; click one for its record |
| ODIN's turn bundles, `inputs/<hash>` | What ODIN was given each turn: the observation (all points of the newest frame, with the limit states it carried) and the history rows (every received frame of the points its procedures name) | Solid lines and dots. A dot is a turn's observation |
| Simulator truth, `truth.jsonl` (or `truth.jsonl.gz`) | The simulator's true state each tick, and fault onsets. ODIN never reads it | Dashed lines, the truth lane, and the words "Simulator truth, never seen by ODIN". A checkbox hides it |
| The Director's flown pass, `commands.csv` and `telemetry_hk.csv` | What he sent, and every frame his ground station received, in a pass of the same scenario he flew in HUGINN: a separate flight, on the same MET axis | Violet: a line on each telemetry lane, a DIRECTOR row on each state lane, the age of his newest frame on the telemetry-age lane, and his commands on their own lane beside ODIN's requests; click one for the rows of his files it came from |
| The scenario's own commands, `phase2_scripted_commands.json` | The commands each phase-2 scenario sent by itself at a set MET, which his pass carried; for each, whether it falls before or in contact and whether ODIN's runs keep it, and where it comes from in HUGINN's scenario files | A hollow violet diamond on a lane of their own, "The scenario's commands", under his; never his triangle. The lane says that ODIN's runs drop the in-contact ones |
| An animation clip and its sync file | A rendering of the run, made by the animation session from the run's own timeline file | The animation pane, beside the timeline, locked to the playhead; played only when its sync file pins the timeline file on screen |
| Derived by VERDA | The age of the newest frame in ODIN's bundles and in the Director's frames; limit states for history rows, truth values and his frames, by the contract's rule (section 16.2, U7); the MET of each of his commands, and what his command counters showed after it and after each of the scenario's | Said so in the lane and in each record |

The converter checks the event log's hash chain and head, the truth file's chain and head, and each saved bundle against its hash, and the header shows the result. If a check fails the page says so in red.

A record file may be gzip-compressed: phase 2's scored runs keep their truth as `truth.jsonl.gz`, and its chain and head are checked on the records inside. The converter never skips a file silently: a file in a run folder that it does not read is named in the timeline's warnings, which the page and the converter's output show, and `--all` names each folder it passes over for having no event log.

In the onboard seat the ground staleness monitor and the ground link are not recorded (they are the ground seat's and null by contract), and the page says so. In the ground seat each turn's bundle records them, and the telemetry-age lane shows them in a strip above its chart: the staleness state as circles and the ground link as squares, each row named where its state changes, with the received-packet count on hover.

## The Director's flown pass

Each of the Director's pass folders (`<date>-<pass>`, as `2026-10-11-P3`) holds `telemetry_hk.csv`, every housekeeping frame his ground station received, and `commands.csv`, every command he sent; a pass in which he sent none has no `commands.csv`. Both are OpenC3 COSMOS exports. `convert/pass_records.py` reads them.

- **On ODIN's axis.** Each of his frames carries the spacecraft's own MET (`CDH_MET`), so it goes on the axis as it is. A command carries only the UTC time it went out; VERDA places it between the two frames his ground station received just before and just after that time, by linear interpolation. The spacecraft's clock and UTC drift apart by up to 1 % in these passes, so one fixed offset would misplace a command by several seconds.
- **What followed each command** is read from his own telemetry: his command counters (`CDH_CMD_ACC_CNT`, `CDH_CMD_REJ_CNT`) in the frames of the next 10 s, compared with the frame before the command. The page says "accepted", "rejected" with the reason his telemetry gave, or "no counter change". This is derived by VERDA and labeled so.
- **Columns are read by position.** The column order differs from pass to pass, and a `commands.csv` holding two kinds of command packet repeats column names, one block of columns per packet; each row is read against its own header, and a repeated name is kept as `NAME#2`.
- **Which pass beside which run.** A run is paired with the pass of its scenario (`P3` with `P3`, `P2` with `P2a` or `P2b`) whose frames its MET span covers most of, if it covers at least half. Each pass takes the plan of its scenario whose contact window holds most of its frames. A pass that no run pairs with gets a timeline of its own, beside its plan's contact window, until a run of it exists.
- **The checks.** The converter checks that his frames' MET and time each increase, and that every row reads; the header shows "Director's pass read", or the problems in red. His files' SHA-256 hashes are in the timeline's sources.

## The scenario's own commands

Each phase-2 scenario sends some commands by itself, each at a set MET, and the Director's passes carried them. They are on his side of the comparison, but they are not his: the page draws them on a lane of their own under his commands, as hollow diamonds, and their hover and record say "the scenario's own command, not the Director's". ODIN's runs keep the ones before contact and drop the ones in contact (the Director's ruling on U35), so that every command during a pass is ODIN's; the lane says so, and each command says whether ODIN's runs keep or drop it.

The input `phase2_scripted_commands.json` lists them for each pass: its plan and contact window, and for each command its MET, arguments, whether it falls before or in contact, whether ODIN's runs keep it, and its scenario file and line in HUGINN. It is data only, derived by Claude Code from HUGINN's scenario files; VERDA reads no HUGINN file. `convert/scripted_commands.py` reads it and checks each entry against the pass's own plan file: the contact window is half-open, from `aos_met_s` up to `los_met_s`, and a command in it must not be kept. A disagreement is a problem, and the header shows "Scenario's commands FAILED its check".

- **What his telemetry showed next** is read from his command counters as for his own commands, compared with his last frame from before the command's MET. A command that falls outside his frames (each pass's payload ON at MET 120, before contact) is named at the lane's edge and has no reading.
- **A shared span.** A counter change in a span where both his command and the scenario's were sent cannot be credited to one of them; the converter says so on both, and marks his command's outcome as uncertain. In the five passes, none is.
- Without `--scripted`, the lane says the scenario's commands were not given to the converter, and shows none.

## The animation pane

Beside the timeline, a pane plays the animation clip of the run on screen, locked to VERDA's playhead. Each clip comes with a sync file beside it, `<name>.sync.json` beside `<name>.mp4`:

| Field | Holds |
|---|---|
| `run_id` | The run the clip shows |
| `timeline_sha256` | The SHA-256 of the bytes of the timeline file it was rendered from |
| `first_frame_met_s` | The MET its first frame shows |
| `met_step_s` | The MET between one frame and the next |
| `fps` | Its frames a second |

- **Which clip plays.** A page opened from disk can read neither a JSON file nor a file's bytes, so the converter (`--clips`, `convert/clips.py`) copies each clip and its sync file into `<out>/clips/` and lists them in `index.js`, beside the SHA-256 of each timeline file. The page plays a clip only when its sync file's `run_id` and `timeline_sha256` match the timeline on screen. Otherwise it shows nothing and says why: no clip for this run, or a clip rendered from another timeline file, with both hashes.
- **Where the clip sits.** At playhead MET t, the clip is (t − `first_frame_met_s`) / `met_step_s` frames in, at that over `fps` seconds. The pane counts frames from 1, as the sync file's notes and the renderer do. Before the first frame or after the last, it holds there and says so.
- **Moving with the timeline.** While the timeline plays, the clip plays on its own at the timeline's pace (its speed over `fps` × `met_step_s`), and is put back on the playhead if it drifts more than two frames; when that pace is outside what the browser can play, the clip steps from frame to frame instead. Pausing pauses it on the playhead's frame, and scrubbing moves it there. It uses the browser's own video element, muted.
- **With a clip on screen**, the event log gives its place to the pane and the readouts drop their gauges, so that all of it fits a 1920 × 1080 screen.
- **A clip pins the run's own timeline.** A run beside the Director's pass is written as two files (see The timeline format): `<id>.js`, the run's own timeline, byte for byte what the converter makes of the run alone, and `<id>.beside.js`, what pairing adds. A clip rendered from `<id>.js` keeps matching whatever changes on the Director's side.

## Pre-existing

| File | What it is | Source | License |
|---|---|---|---|
| `page/fonts/Michroma-Regular.ttf` | Michroma, by Vernon Adams, Copyright 2011 The Michroma Project Authors. SHA-256 `b62301163788bc5b7f8fcac0b74b184e34e1827e577b499ecb724da065098f87` | `github.com/google/fonts`, `ofl/michroma/`, commit `8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5` | SIL Open Font License 1.1 |
| `page/fonts/OFL.txt` | The font's license, unchanged. SHA-256 `33c39ce59a45bfb0dae3280e98bdb46be59d6d68efc62d4dc5fae90a26d2f393` | The same folder and commit | |

Both were downloaded on 28 October 2026 with the Director's approval and checked against the git blob hashes GitHub lists for them. The page uses the font for titles only.

## Record types

`convert/record_types.py` says how each of the 25 record types the contract lists is shown. All 25 are shown; none is listed as not shown. The page's footer shows the same table with each type's count in the run.

## The timeline format

A timeline file is one JavaScript assignment of one JSON object, so that a page opened from disk can load it with a script tag:

```
// VERDA timeline {"format": "verda-timeline", "format_version": 1, "id": ..., "met_range": [...], "title": ...}
window.VERDA_TIMELINES = window.VERDA_TIMELINES || {};
window.VERDA_TIMELINES["<id>"] = { ...the timeline object... };
```

The object (format `verda-timeline`, version 1):

| Field | Holds |
|---|---|
| `id`, `title`, `met_range` | The timeline's name and its MET span `[start, end]` |
| `sources` | Each source of data by name (`odin`, `truth`, `director`, `scenario`), with a label and kind; the Director's names his pass, its date, its plan and his files' hashes; the scenario's names the scripted-commands file and its hash |
| `header` | The run's facts for the header: scenario, phase, seat, model, mode, plans, arming act, end; `pass`, the Director's pass beside it; `pass_only`, for a pass alone |
| `integrity` | Each check the converter made, with its result and any problems |
| `lanes` | The lanes, top to bottom: `id`, `label`, `kind` (`track`, `requests`, `pass-commands`, `scenario-commands`, `chart` or `state`), `height`, the `series` a chart draws, and any `note`; the telemetry-age lane's `strip` is set when the bundles recorded the ground staleness state and ground link |
| `spans` | Bars on a lane: `lane`, `start`, `end`, `label`, `severity`, `row`, `refs` |
| `events` | Marks on a lane: `lane`, `met_s`, `label`, `severity`, `shape`, `row`, `refs` |
| `requests` | Each request chain: the command, BALDUR-0's decision and its first failed check, any voiding, the dispatch and the outcome, with their times |
| `pass_commands` | Each command the Director sent: the command and its arguments, its UTC time, its MET and how it was placed, and what his counters showed after it |
| `scenario_commands` | Each command the scenario sent by itself in his pass: its MET, the command and its arguments, before or in contact and the plan window, whether ODIN's runs keep it, its source in HUGINN, and what his counters showed after it |
| `pass_records` | The rows of his files, by `c<line>` (commands.csv) and `h<line>` (telemetry_hk.csv), that his commands' and the scenario's `refs` point to |
| `series` | Telemetry by `<source>:<point>`: units, kind, limits, and `samples` as `[met_s, value, limit_state, provenance]` |
| `turns` | Each turn: its triggers, answer, model calls and a summary of its bundle |
| `records`, `truth_records` | The raw records, by record ID, that `refs` such as `log:27` and `truth:101` point to |
| `record_types` | How each contract record type is shown, with its count |
| `warnings` | Anything the converter could not place |

The page draws whatever lanes, spans, events and series a timeline holds. A pass the Director flew in HUGINN is a source of its own in the same format, `director`, with its commands in `pass_commands` and its telemetry as series, beside a run or alone; the scenario's own commands in his pass are the source `scenario`, in `scenario_commands`.

**A run beside the Director's pass** is two files. `<id>.js` is the run's own timeline, with none of the fields above that belong to his pass. `<id>.beside.js` (format `verda-beside`, version 1) holds what pairing adds, assigned to `window.VERDA_BESIDE["<id>"]`: `run_sha256`, the SHA-256 of the `<id>.js` it was made for; `add`, the new entries of `sources`, `header` (his `pass`) and `series`; `new`, the fields `pass_commands`, `scenario_commands` and `pass_records`; `append`, the checks added to `integrity`; and the `title`, `met_range` and `lanes` of the pair. The page puts the two together only when `run_sha256` is the SHA-256 `index.js` gives for `<id>.js`; otherwise it shows the run alone and says why. Before writing, the converter checks that the two put together are the paired timeline.

**`index.js`** lists each timeline file in `window.VERDA_INDEX` with its `sha256` and, for a run beside a pass, its `beside` file, and each placed animation clip in `window.VERDA_CLIPS`: its sync file's fields, its `file` and `sync_file` under `clips/`, their hashes and any `problems`.

## Checks

```
python -m unittest discover -s tests          the tests (about five minutes)
python tests/show_red.py                       every red case, then the suite again
python tests/browser_probe.py <run_id>         what one load of the page asked for
```

Each test has a red case in `tests/show_red.py`: a change planted in VERDA's source, or in a temporary copy of an input, that must make that test fail. The runner plants it, runs that one test alone and restores the source byte for byte. A red case counts only if its test ran and failed. A test that did not run, passed, or stopped on an error does not count.

| Test file | What it checks |
|---|---|
| `test_convert.py` | Canonical JSON against the contract's vectors; every run's hash chains, the ground-seat run's and the fifty scored runs' included; that a changed record breaks the chain; limit states against every limit state the bundles recorded; the truth mapping against every observed frame; each practice run's timeline; the ground-seat run's staleness state and ground link against what each bundle recorded, and its derived frame age against the age it recorded; the fifty scored runs: their gzipped truth read and checked, each beside the Director's pass of its plan with every check passing, their four tool uses on their turns, and each kind of truth flag on a row of its own; a file the converter does not read named in its warnings, and a folder with no event log named by `--all`; that the same inputs give the same files, byte for byte, under four hash seeds |
| `test_clips.py` | A run beside his pass written as its own timeline, byte for byte the run alone, and a beside file that pins it and puts together to the pair; the preview clip's pinned hash against the run's own timeline as converted, alone or paired; each clip and its sync file placed and listed in `index.js`; a sync file with no clip, or a bad field, not placed |
| `test_record_types.py` | Every record type the contract lists is shown or listed as not shown |
| `test_watch_only.py` | The converter writes only its timeline files, beside files, index and placed clips, and leaves every run folder, pass folder, plan, the scripted-commands file and the clips folder unchanged; output names cannot leave the output folder |
| `test_passes.py` | The Director's five passes read, each with its plan; P1's repeated columns; what his counters showed after each command; one known command time on each side against its source file (his P3 load shed from his two CSV files, ODIN's from its DISPATCH record); each run lined up with the Director's pass of its plan, all fifty scored runs included; a run paired by its plan when its span covers two passes; his frame age through the gap in his P4 frames (MET 1199 to 1320); the seven scripted commands, each checked against its plan's window; the scenario's commands on his side and never among his, with the lane saying ODIN's runs drop the in-contact ones; what his counters showed after the scenario's commands (P1's at MET 180 and 240, read from his CSV file too); a span his command shares with the scenario's credited to neither; and ODIN's runs dropping exactly the in-contact ones, against each run's own truth records |
| `test_page.py` | The page's source: no network calls or addresses, a policy that refuses connections and lets scripts, styles, fonts and media come only from the page's folder, no writing, no HTML built from recorded text |
| `test_page_in_browser.py` | The page opened from disk in headless Chrome or Edge: it asks only for its own files, has no script or console errors, draws every lane of each run beside its pass and of each pass alone, shows a request's records, the Director's command and his rows, and the scenario's command apart from his on hover and click; names in words what the ground-seat run's bundles recorded of staleness and the ground link; writes a name near the right edge whole, before its mark; opens a run on its pass; plays the animation clip on the frame its sync file gives for a known MET, shows nothing for a clip whose pinned hash does not match, holds the clip outside its frames and moves it with play and pause; fits every lane of a run beside the Director's pass on a 1920 × 1080 screen; and plays |
| `test_clean_room.py` | No VERDA file imports HUGINN's old viewer package or names the folders of HUGINN's old viewer or its replay schema; no file a deposit takes holds a path under a user's own folder (`Users` on Windows and macOS, `home` on Linux) |

The tests read their inputs from `inputs/` beside VERDA, or from the folders named by `VERDA_INPUTS`, `VERDA_RUNS`, `VERDA_DICTIONARY`, `VERDA_SCRIPTED`, `VERDA_CLIPS` and `VERDA_PAGE`. A test whose inputs are missing fails; none skips. The browser test needs Chrome or Edge installed (or `VERDA_BROWSER` naming one).
