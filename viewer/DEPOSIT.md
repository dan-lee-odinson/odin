# VERDA-02: V1 in the blue console

| Field | Value |
|---|---|
| Deposit | VERDA-02, the first deposit Claude Code commits. VERDA-01 is not committed, by the Director's ruling of 28 October 2026: its DEPOSIT.md gave a private folder path. VERDA-02 takes its place. |
| Milestone | V1 of the brief (section 5), one run played back from disk, after the design round: the blue console, the five layout fixes and the Michroma title font |
| Seen running by the Director | V1: 28 October 2026, opened from disk. The blue console with the ice-white playhead: shown on 28 October 2026 as a 1920 × 1080 screenshot of the page running in headless Chrome, with the test run and its red cases; the Director confirmed he had seen it and said to deposit on 29 October 2026. |
| Built by | The VERDA session (Claude Code), directed by Dan Lee-Odinson, Director |
| Inputs it was built and tested against | inputs/MANIFEST.sha256 as placed on 28 October 2026 (226 files, ODIN commit 46b3c33), all matching |

## What is in it

| Path | What it is |
|---|---|
| `README.md` | What VERDA is, how to use it, the look, where each thing on the page comes from, the pre-existing files, the timeline format, the checks |
| `convert/verda_convert.py` | The converter: a run folder in, a timeline file out, after checking the log's hash chain and head, the truth file's chain and head, and each saved turn bundle's hash |
| `convert/huginn_dictionary.py` | Reads the telemetry points and limits from HUGINN's dictionary, and applies the contract's limit-state rule (section 16.2, U7) |
| `convert/record_types.py` | How each of the contract's 25 record types is shown (all 25 are) |
| `page/index.html`, `page/verda.css`, `page/verda.js` | The page: static, opened from disk, no network request, writes nothing |
| `page/fonts/Michroma-Regular.ttf`, `page/fonts/OFL.txt` | Pre-existing: the Michroma font, used for titles only, and its license (SIL Open Font License 1.1), unchanged |
| `tests/` | 31 tests (unittest), the red-case runner `show_red.py`, and `browser_probe.py`, which drives headless Chrome or Edge for the browser test |
| `MANIFEST.sha256` | Every other file in this deposit with its SHA-256 |
| `DEPOSIT.md` | This file |

All of it is new, written on 28 October 2026, except the two font files. It uses no third-party library.

Pre-existing, with the Director's approval of 28 October 2026: `page/fonts/Michroma-Regular.ttf` (Michroma by Vernon Adams, Copyright 2011 The Michroma Project Authors; SHA-256 `b62301163788bc5b7f8fcac0b74b184e34e1827e577b499ecb724da065098f87`) and `page/fonts/OFL.txt` (SHA-256 `33c39ce59a45bfb0dae3280e98bdb46be59d6d68efc62d4dc5fae90a26d2f393`), both from `github.com/google/fonts`, folder `ofl/michroma/`, commit `8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5`, checked against the git blob hashes GitHub lists for them. The README lists them under Pre-existing.

Left out, as the brief says: `inputs/`, every run folder, the timeline files the converter writes (`page/timelines/`, generated from run folders; a reader runs the converter to make them), the brief itself, scratch files and caches. Nothing secret is in it. No file in it holds a path under a user's folder, a user name, a machine name or an email address: the new clean-room test checks for the first in every file listed here, this DEPOSIT.md and MANIFEST.sha256 included. Before writing the zip, the VERDA session's deposit script checked every file for all four and would not have written it if it had found one.

## What changed since V1 (VERDA-01)

The data and the checks on it are unchanged. The page's look and layout changed, and one test was added.

- **The look.** The page is drawn as a working spacecraft console in one look: deep navy panels, cyan hairlines, ice-white text; panels with notched corners and corner brackets; section headers in spaced capitals with a short amber bar and a thin rule; key readouts as large tabular numbers in boxed fields; segmented gauges; a faint grid behind the lanes. Titles are set in Michroma; numbers are in a monospace font.
- **Colors.** Green good, amber caution, red alarm, and nothing else is drawn in them as a fill, a hatch or a word. The one amber decoration is the bar on each section header, off the data. The playhead and its MET marker on the axis are ice-white, and so is the bar beside the newest record in the event log.
- **Limit states read without color.** Each limit chip names its state in words and has its own shape: green an outline, yellow filled and pointed on the right, red filled and pointed at both ends. Yellow and red limit bands are hatched and named on the chart ("YELLOW HIGH 1.5"). Observation dots are a circle when green, a triangle when yellow and a square when red.
- **The truth lane** has a dashed frame, a faint hatch and the words "SIMULATOR TRUTH · NEVER SEEN BY ODIN".
- **Layout fixes.** (1) Each chart's scale is in a gutter left of the plot, off the data. (2) Turns are labeled short ("T4 command") on a row beneath their markers; the hover has the detail. (3) The readouts at the playhead are boxes with no scroll of their own; panel headings shorten with an ellipsis, and the record panel wraps long hashes. (4) Solar string 1 is drawn as dots, string 2 as rings, with a key under the lane name. (5) The lone "note" is gone; hovering on a lane's name says what the lane holds.
- **Tests.** `test_clean_room.CleanRoom.test_no_deposited_file_holds_a_user_folder_path` is new (31 tests now). The browser test copies the font folder with the page and expects the page to ask for its font file. `tests/show_red.py` finds the real inputs through `VERDA_INPUTS`, `VERDA_RUNS` and `VERDA_DICTIONARY`, as the tests do.

## Tests run, and their results

In the VERDA folder, on these exact files, 28 October 2026, and again on 29 October 2026 just before this deposit was written, with the same results:

- `python -m unittest discover -s tests -v`: **Ran 31 tests, OK.**
- `python tests/show_red.py`: **31 red cases, 31 caught**, then the whole suite again: **Ran 31 tests, OK.** "RESULT: every red case caught, and the suite passes."

A red case counts as caught only if its test ran and failed. A test that did not run, passed, or stopped on an error does not count. Each was planted, run alone and restored byte for byte:

| # | Test | Planted change | Result |
|---|---|---|---|
| 1 | `test_clean_room.CleanRoom.test_the_scan_sees_verda_files` | the scan skips the convert folder | caught |
| 2 | `test_clean_room.CleanRoom.test_nothing_imports_the_old_viewer_package` | a planted file imports the old viewer package | caught |
| 3 | `test_clean_room.CleanRoom.test_nothing_names_the_old_viewer_folders` | a planted file names the old viewer folder | caught |
| 4 | `test_clean_room.CleanRoom.test_no_deposited_file_holds_a_user_folder_path` (new) | README.md gives the runs folder by its full path, under a Users folder | caught |
| 5 | `test_convert.CanonicalJson.test_reproduces_every_contract_vector` | canonical JSON gains a space after commas | caught |
| 6 | `test_convert.HashChain.test_practice_runs_verify` | one record of a copied run is changed | caught |
| 7 | `test_convert.HashChain.test_a_changed_record_breaks_the_chain` | the chain check stops comparing prev_hash | caught |
| 8 | `test_convert.Limits.test_dictionary_has_the_sixteen_points` | a copied dictionary's yellow staleness limit is 12 s | caught |
| 9 | `test_convert.Limits.test_limit_states_match_every_observation` | a copied dictionary's load-current yellow high is 1.9 A | caught |
| 10 | `test_convert.TruthMapping.test_truth_matches_every_observation` | battery voltage is mapped to the bus voltage | caught |
| 11 | `test_convert.Timelines.test_each_practice_run_has_a_timeline_file` | the index leaves P4 out | caught |
| 12 | `test_convert.Timelines.test_p3_payload_shed_is_one_allowed_accepted_chain` | outcomes are dropped | caught |
| 13 | `test_convert.Timelines.test_p4_reset_and_the_frame_gap` | frame age turns yellow 20 s late | caught |
| 14 | `test_convert.Timelines.test_p3_process_has_two_malformed_turns_and_no_request` | malformed answers read as no action | caught |
| 15 | `test_convert.Timelines.test_check_ins_reports_and_contact` | check-ins land on the reports lane | caught |
| 16 | `test_convert.Timelines.test_v1_points_from_both_sources` | the payload rate lane is gone | caught |
| 17 | `test_convert.Timelines.test_every_record_is_drawn` | turn records are not marked as drawn | caught |
| 18 | `test_page.NoNetwork.test_no_network_calls_or_addresses` | verda.js gains a fetch | caught |
| 19 | `test_page.NoNetwork.test_html_loads_only_files_beside_it` | index.html gains an icon link | caught |
| 20 | `test_page.NoNetwork.test_content_security_policy_refuses_connections` | the policy allows connections to the page's origin | caught |
| 21 | `test_page.NoWriting.test_page_writes_nothing` | verda.js saves to localStorage | caught |
| 22 | `test_page.NoWriting.test_recorded_text_is_never_parsed_as_html` | the inspector takes records as HTML | caught |
| 23 | `test_page_in_browser.PageInBrowser.test_asks_only_for_its_own_files_on_disk` | the page asks a local address for an image | caught |
| 24 | `test_page_in_browser.PageInBrowser.test_no_script_or_console_errors` | the page writes an error to the console | caught |
| 25 | `test_page_in_browser.PageInBrowser.test_draws_every_lane_of_each_run` | the contact lane is not drawn | caught |
| 26 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_a_request_and_its_records` | clicks on the timeline do nothing | caught |
| 27 | `test_page_in_browser.PageInBrowser.test_play_moves_the_playhead` | playback stands still | caught |
| 28 | `test_record_types.RecordTypes.test_contract_and_schema_agree` | a copied contract drops TOOL_USE from its list | caught |
| 29 | `test_record_types.RecordTypes.test_every_contract_type_is_shown_or_listed` | TOOL_USE is missing from VERDA's table | caught |
| 30 | `test_watch_only.WatchOnly.test_converter_writes_only_its_files_and_leaves_the_run_untouched` | the converter leaves a file in the run folder | caught |
| 31 | `test_watch_only.WatchOnly.test_output_names_cannot_leave_the_folder` | output names may hold a backslash | caught |

The new test's red case plants the path in `README.md`, built inside `show_red.py` from pieces, so that no deposited file holds such a path. The test finds paths under a user's folder written with backslashes or forward slashes, with doubled backslashes as in source code or JSON, as a file URL, and in the macOS form (a Users folder at the root) and the Linux form (a home folder at the root). Before the red case was written, the test was also checked against VERDA-01's DEPOSIT.md: it finds the four lines that hold the path.

Rehearsal of the run below: a draft of this deposit, the same files except that this DEPOSIT.md's results and dates were not yet filled in, unpacked into an empty `viewer` folder with no `inputs/` beside it (as in the repository), run with only `VERDA_INPUTS` set: **Ran 31 tests, OK; 31 red cases, 31 caught; every deposited file unchanged afterwards** (checked against `MANIFEST.sha256`).

## How Claude Code runs the tests at each VERDA deposit

By the Director's ruling of 28 October 2026 ("Run them at each deposit"): the repository's own test run leaves VERDA's tests out, so a fresh clone still passes; Claude Code runs VERDA's full tests at every VERDA deposit, with the inputs pointed at the VERDA folder, and records the result in the commit.

`<VERDA folder>` below stands for the VERDA session's folder on the Director's machine. Claude Code has its real path; this file does not give it.

From the repository's `viewer` folder, in PowerShell, on a clean working tree:

```
$env:VERDA_INPUTS = "<VERDA folder>\inputs"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m unittest discover -s tests -v
python tests\show_red.py
Remove-Item Env:VERDA_INPUTS, Env:PYTHONDONTWRITEBYTECODE
```

The same in a POSIX shell:

```
VERDA_INPUTS='<VERDA folder>\inputs' PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
VERDA_INPUTS='<VERDA folder>\inputs' PYTHONDONTWRITEBYTECODE=1 python tests/show_red.py
```

| Variable | Set it to | Notes |
|---|---|---|
| `VERDA_INPUTS` | `<VERDA folder>\inputs` | The only one needed |
| `VERDA_RUNS` | leave unset | Defaults to `VERDA_INPUTS\runs` |
| `VERDA_DICTIONARY` | leave unset | Defaults to `VERDA_INPUTS\dictionaries\HUGINN\tlm_cmd.yaml` |
| `VERDA_PAGE` | leave unset | Defaults to the deposited `page` folder |
| `VERDA_BROWSER` | leave unset | The browser test finds Chrome or Edge in their usual places |
| `PYTHONDONTWRITEBYTECODE` | `1` | Keeps `__pycache__` folders out of the viewer folder |

What to expect: the unittest run ends `Ran 31 tests` and `OK`; `show_red.py` lists 31 red cases, each `caught`, ends with `RESULT: every red case caught, and the suite passes`, and exits 0. It needs Chrome or Edge installed, and takes about three minutes. The new clean-room test reads this DEPOSIT.md and MANIFEST.sha256 too, so they must sit in the viewer folder as deposited.

What the run touches: `show_red.py` plants each change in a file in the viewer folder and restores it byte for byte before the next; it keeps each original in `.scratch\red-backup` inside the viewer folder while planted and deletes it after, which leaves an empty `.scratch` folder there (git does not track empty folders). If a run is stopped partway, the next run restores any planted file from that backup first. After the run, `git status` should show the tree unchanged.

## Suggested commit message

```
viewer: VERDA-02, V1 playback of one run, in the blue console

VERDA plays back a finished run's records on one MET axis: contact,
plan and rung, ODIN's turns, reports and escalations, the Director's
check-ins, each request with BALDUR-0's decision, the dispatch and the
outcome, and the pass telemetry with its limit states, telemetry age,
and the simulator truth, labeled as never seen by ODIN.

convert/verda_convert.py turns a run folder into a timeline file after
checking the log's hash chain, the truth file's chain and each saved
bundle's hash. page/index.html is a static page that opens from disk,
makes no network request and writes nothing. It is drawn as a console:
navy panels, cyan hairlines, an ice-white playhead, limit states in
words and shapes as well as color, and titles in the Michroma font
(pre-existing, SIL Open Font License, in page/fonts/ with its license).

31 tests, each shown failing on a planted red case (tests/show_red.py),
among them a check that no deposited file holds a path under a user's
folder.
```
