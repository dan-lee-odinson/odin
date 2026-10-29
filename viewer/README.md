# VERDA

VERDA is a watch-only viewer for ODIN's runs. It plays back a finished run's records on one mission-elapsed-time (MET) axis: the contact windows, the telemetry that matters to a pass with its limit states, telemetry age and the ground link, each of ODIN's requests with BALDUR-0's decision, the dispatch and the outcome, and ODIN's reports and escalations beside the Director's check-ins.

VERDA was written during the Meta Global AI Developer Hackathon by a Claude Code session (the VERDA session), directed by Dan Lee-Odinson, Director. It is new code. It uses no third-party library; its one pre-existing file is the Michroma font (see Pre-existing).

## Use

1. Turn run folders into timeline files:

   ```
   python convert/verda_convert.py --all <folder holding run folders>
   python convert/verda_convert.py <run folder> [<run folder> ...]
   ```

   Options: `--out DIR` (default `page/timelines`), `--dictionary PATH` (HUGINN's `tlm_cmd.yaml`; found automatically beside VERDA or in the repository's pinned HUGINN), `--no-truth` (leave the simulator truth out).

2. Open `page/index.html` from disk in a browser. Pick a run, then press Play.

Keys: Space plays and pauses; Left and Right step to the previous and next event; Home and End; `+` and `-` zoom around the playhead; `0` shows the whole run. Hover over anything to see what it is; click it to show its record.

A link can open the page at a chosen moment: `index.html#run=<run_id>&met=<seconds>&future=1&truth=0&view=<from>-<to>`.

## The look

The page is drawn as a working spacecraft console: hairline-framed panels with notched corners and corner brackets, section headers in spaced capitals with a short accent bar and a thin rule, boxed readouts with large tabular numbers, segmented gauges, and a faint grid behind the lanes. Titles are set in Michroma; numbers are in a monospace font.

The colors are deep navy panels, cyan hairlines and ice-white text. Status colors keep one meaning (green good, amber caution, red alarm), and decoration is drawn only in lines and thin bars, never filled, hatched or worded. The one amber decoration is the short bar on each section header, kept off the data; the playhead and its MET marker are ice-white. A limit state always carries its name in words, and a shape: a green chip is an outline, a yellow one is filled and pointed on the right, a red one is filled and pointed at both ends; yellow and red limit bands are hatched and named on the chart.

## Watch-only, from disk

- The page is static HTML, CSS and JavaScript. It reads only the files beside it: its own three files, its font, `timelines/index.js` and the timeline file of the run it plays. It makes no network request; its Content-Security-Policy refuses every connection, and a test opens it in a browser and checks every request it makes.
- The page writes nothing: no storage, no downloads, no forms.
- The converter reads a run folder and writes two files, `<out>/<run_id>.js` and `<out>/index.js`. It never writes into a run folder.
- Text from the records (ODIN's rationales, reports, the Director's words) is always shown as text, never read as HTML.

## Where each thing on the page comes from

Every line, dot and mark has one source, and the page labels it:

| Source | What it is | How the page shows it |
|---|---|---|
| The event log, `events.jsonl` | Every record the harness and BALDUR-0 wrote | Markers, spans and request chains; click one for its record |
| ODIN's turn bundles, `inputs/<hash>` | What ODIN was given each turn: the observation (all points of the newest frame, with the limit states it carried) and the history rows (every received frame of the points its procedures name) | Solid lines and dots. A dot is a turn's observation |
| Simulator truth, `truth.jsonl` | The simulator's true state each tick, and fault onsets. ODIN never reads it | Dashed lines, the truth lane, and the words "Simulator truth, never seen by ODIN". A checkbox hides it |
| Derived by VERDA | The age of the newest frame in ODIN's bundles, and limit states for history rows and truth values, by the contract's rule (section 16.2, U7) | Said so in the lane and in each record |

The converter checks the event log's hash chain and head, the truth file's chain and head, and each saved bundle against its hash, and the header shows the result. If a check fails the page says so in red.

In the onboard seat the ground staleness monitor and the ground link are not recorded (they are the ground seat's and null by contract), and the page says so.

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
| `sources` | Each source of data by name (`odin`, `truth`), with a label and kind |
| `header` | The run's facts for the header: scenario, phase, seat, model, mode, plans, arming act, end |
| `integrity` | Each check the converter made, with its result and any problems |
| `lanes` | The lanes, top to bottom: `id`, `label`, `kind` (`track`, `requests`, `chart` or `state`), `height`, the `series` a chart draws, and any `note` |
| `spans` | Bars on a lane: `lane`, `start`, `end`, `label`, `severity`, `row`, `refs` |
| `events` | Marks on a lane: `lane`, `met_s`, `label`, `severity`, `shape`, `row`, `refs` |
| `requests` | Each request chain: the command, BALDUR-0's decision and its first failed check, any voiding, the dispatch and the outcome, with their times |
| `series` | Telemetry by `<source>:<point>`: units, kind, limits, and `samples` as `[met_s, value, limit_state, provenance]` |
| `turns` | Each turn: its triggers, answer, model calls and a summary of its bundle |
| `records`, `truth_records` | The raw records, by record ID, that `refs` such as `log:27` and `truth:101` point to |
| `record_types` | How each contract record type is shown, with its count |
| `warnings` | Anything the converter could not place |

The page draws whatever lanes, spans, events and series a timeline holds. A pass flown by hand in HUGINN fits the same format as a source of its own, with its commands as events and its telemetry as series.

## Checks

```
python -m unittest discover -s tests          the tests (about 20 seconds)
python tests/show_red.py                       every red case, then the suite again
python tests/browser_probe.py <run_id>         what one load of the page asked for
```

Each test has a red case in `tests/show_red.py`: a change planted in VERDA's source, or in a temporary copy of an input, that must make that test fail. The runner plants it, runs that one test alone and restores the source byte for byte. A red case counts only if its test ran and failed. A test that did not run, passed, or stopped on an error does not count.

| Test file | What it checks |
|---|---|
| `test_convert.py` | Canonical JSON against the contract's vectors; each practice run's hash chains; that a changed record breaks the chain; limit states against every limit state the bundles recorded; the truth mapping against every observed frame; each practice run's timeline |
| `test_record_types.py` | Every record type the contract lists is shown or listed as not shown |
| `test_watch_only.py` | The converter writes only its two files and leaves the run folder unchanged; output names cannot leave the output folder |
| `test_page.py` | The page's source: no network calls or addresses, a policy that refuses connections, no writing, no HTML built from recorded text |
| `test_page_in_browser.py` | The page opened from disk in headless Chrome or Edge: it asks only for its own files, has no script or console errors, draws every lane, shows a request's records on hover and click, and plays |
| `test_clean_room.py` | No VERDA file imports HUGINN's old viewer package or names the folders of HUGINN's old viewer or its replay schema; no file a deposit takes holds a path under a user's own folder (`Users` on Windows and macOS, `home` on Linux) |

The tests read their inputs from `inputs/` beside VERDA, or from the folders named by `VERDA_INPUTS`, `VERDA_RUNS`, `VERDA_DICTIONARY` and `VERDA_PAGE`. A test whose inputs are missing fails; none skips. The browser test needs Chrome or Edge installed (or `VERDA_BROWSER` naming one).
