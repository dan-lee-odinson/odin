# VERDA-05: V4, phase 2's fifty runs and the animation pane

| Field | Value |
|---|---|
| Deposit | VERDA-05, a reissue of VERDA-04 with one commit ID changed, after VERDA-03, which is committed in the repository's `viewer` folder. It replaces every VERDA file in that folder; no file of VERDA-03's is left out, and two files are new: `convert/clips.py` and `tests/test_clips.py`. |
| Milestone | V4, as the Director set it on 30 October 2026. (1) Real runs: the converter handles phase 2's fifty scored runs and lines each up beside the Director's flight of the same pass. (2) The animation pane: beside the timeline, the clip of the run on screen, locked to the playhead, played only when its sync file's run_id and timeline_sha256 match the timeline on screen. (3) The fix from VERDA-03's round: the ground-seat run's "Fault onset" label is written whole. V3, live viewing, is skipped by the Director's word of 30 October 2026. |
| Seen running by the Director | 30 October 2026: 1920 × 1080 screenshots of the page running in headless Chrome: the phase-2 development run beside his P3 flight, captured while playing at 10× with the preview clip playing in the pane; and R1 of each model on each of the five passes, beside his flight of that pass; with the test run and both red-case logs. The Director confirmed them and said to deposit on 30 October 2026. |
| Built by | The VERDA session (Claude Code), directed by Dan Lee-Odinson, Director |
| Inputs it was built and tested against | inputs/MANIFEST.sha256 as of 30 October 2026, 1,498 files, all matching: the 251 of 29 October 2026, and 1,247 added by Claude Code on 30 October 2026: phase 2's fifty scored runs (`runs/PH2-<pass>-<arm>-R<n>/`, from the repository's runs/scored/ at e78bb5b), the phase-2 development run `runs/dev-ph2-p3-open-01/`, and `clips/`, the animation session's preview of that run with its sync file and SYNC.md |

## What is in it

| Path | What it is |
|---|---|
| `README.md` | What VERDA is, how to use it, the look, where each thing on the page comes from, the Director's flown pass, the scenario's own commands, the animation pane, the pre-existing files, the timeline format, the checks |
| `convert/verda_convert.py` | The converter: run folders (a record file plain or gzip-compressed), the Director's passes, the plans and the scripted-commands file in, timeline files out, with a beside file for each run paired with a pass, after checking each log's hash chain and head and each saved bundle's hash |
| `convert/clips.py` (new) | Reads each animation clip's sync file, copies the clip and its sync file beside the timelines, and lists them for `index.js` |
| `convert/pass_records.py` | Reads the Director's pass folders and places his commands on the MET axis |
| `convert/scripted_commands.py` | Reads the scenarios' scripted commands and checks each against its plan |
| `convert/huginn_dictionary.py` | Reads the telemetry points and limits from HUGINN's dictionary, and applies the contract's limit-state rule (section 16.2, U7) |
| `convert/record_types.py` | How each of the contract's 25 record types is shown (all 25 are) |
| `page/index.html`, `page/verda.css`, `page/verda.js` | The page: static, opened from disk, no network request, writes nothing; it plays an animation clip with the browser's own video element |
| `page/fonts/Michroma-Regular.ttf`, `page/fonts/OFL.txt` | Pre-existing, unchanged since VERDA-02: the Michroma font, used for titles only, and its license (SIL Open Font License 1.1) |
| `tests/` | 64 tests (unittest), the red-case runner `show_red.py`, and `browser_probe.py`, which drives headless Chrome or Edge for the browser test |
| `MANIFEST.sha256` | Every other file in this deposit with its SHA-256 |
| `DEPOSIT.md` | This file |

All of it is new, written from 28 to 30 October 2026, except the two font files (see VERDA-02 and the README's Pre-existing section). It uses no third-party library. It holds no clip and no timeline file.

Left out, as the brief says: `inputs/`, every run folder, pass folder and clip, the timeline files the converter writes (`page/timelines/`, generated, with the clips it places there; a reader runs the converter to make them), the brief itself, scratch files and caches. Nothing secret is in it. No file in it holds a path under a user's folder, a user name, a machine name or an email address: the clean-room test checks for the first in every file listed here, this DEPOSIT.md and MANIFEST.sha256 included, and before writing the zip the VERDA session's deposit script checked every file for all four and would not have written it if it had found one.

## What changed since VERDA-03

- **Phase 2's fifty scored runs.** Their truth is kept as `truth.jsonl.gz`; the converter reads it through gzip and checks its chain and head on the records inside, so each run has its truth lane and truth check. The converter never skips a file silently: a file in a run folder that it does not read is named in the timeline's warnings, which the page and the converter's output show, and `--all` names each folder it passes over for having no event log.
- **Each run beside the Director's pass of its plan.** A run is paired with the pass flown under the plan it flew under, and only failing that with the pass of its scenario its MET span covers most of. A P2B run starts at MET 0 and covers his P2a frames as wholly as his P2b ones; its plan decides. Each scored run opens on its pass, its contact windows and a little either side; "Whole run" shows all of it.
- **Two files for a run beside a pass.** `<id>.js` is the run's own timeline, byte for byte what the converter makes of the run alone; `<id>.beside.js` holds what pairing adds (his pass, the scenario's commands, the lanes they take) and pins the SHA-256 of the `<id>.js` it was made for. The converter checks before writing that the two put together are the paired timeline; the page puts them together only when the pin matches. An animation clip pins the run's own file, so nothing on the Director's side of a comparison changes what it pins.
- **The animation pane** (`--clips`). The converter copies each clip and its sync file into `<out>/clips/`, and `index.js` gives each timeline file's SHA-256 and each clip's sync fields. The page plays a clip only when its sync file's `run_id` and `timeline_sha256` match the timeline on screen; otherwise it shows nothing and says why, with both hashes. At playhead MET t the clip is (t − first_frame_met_s) / met_step_s / fps seconds in; before the first frame or after the last it holds and says so. It plays at the timeline's pace while the timeline plays (stepping frame to frame when that pace is below or above what the browser can play), and pausing and scrubbing move it to the playhead's frame. Frames are counted from 1, as SYNC.md counts them. With a clip on screen, the event log gives its place to the pane and the readouts drop their gauges. The page's policy lets media come only from its own folder.
- **Fixes.** A name near the plot's right edge is written whole before its mark (the ground-seat run's "Fault onset"), and a request's or command's label that would run past the edge goes before its marks. Each kind of truth flag has a row of its own (phase 2's P4 runs have four at MET 1200, and the old three-row cap drew one over another). A run whose lanes would overflow a 1920 × 1080 screen has its charts give up a few pixels each, down to 36; beside his pass the charts start at 44. The model badge names the model's configuration, with its full name on hover.
- **Tests.** 64 now, 15 of them new, marked in the table below.

## Timeline files, and the clips that pin them

Each animation clip pins the SHA-256 of the timeline file it was rendered from. Against VERDA-03's converter, on the same inputs:

- **Unchanged, byte for byte:** every practice run's own timeline, the ground-seat run's, and the phase-2 development run's. The preview clip pins `dev-ph2-p3-open-01.js` at sha256 `eb7a03c74747fb8c78b1f768efa90b375313914a941d10cc8b11acd4fe126c8f`, and VERDA-04 makes that file byte for byte, alone or beside his pass; a test checks it.
- **Changed:** the fifty scored runs' timelines, which now carry their simulator truth; the ten P4 runs' changed again for the truth rows. No clip pinned them. By the Director's word of 30 October 2026, the final clips are rendered from VERDA-04's timelines.
- **Changed in form:** with `--passes`, a run beside a pass is two files, as above, where VERDA-03 wrote one.

## Known, for the next round

In the shot of the development run, ODIN's last turn's label is cut off at the plot's right edge ("T11 MALFOR..."). The Director noted it on 30 October 2026 for the next round: the edge rule the request, command and truth labels now follow should cover the turns lane too.

## Tests run, and their results

In the VERDA folder, on these exact files, on 30 October 2026:

- `python -m unittest discover -s tests -v`: **Ran 64 tests, OK.**
- `python tests/show_red.py`: **72 red cases, 72 caught**, then the whole suite again: **Ran 64 tests, OK.** "RESULT: every red case caught, and the suite passes."

A red case counts as caught only if its test ran and failed. A test that did not run, passed, or stopped on an error does not count. Each was planted, run alone and restored byte for byte. A test that checks two things that could each go wrong alone has a red case for each:

| # | Test | Planted change | Result |
|---|---|---|---|
| 1 | `test_clean_room.CleanRoom.test_the_scan_sees_verda_files` | the scan skips the convert folder | caught |
| 2 | `test_clean_room.CleanRoom.test_nothing_imports_the_old_viewer_package` | a planted file imports the old viewer package | caught |
| 3 | `test_clean_room.CleanRoom.test_nothing_names_the_old_viewer_folders` | a planted file names the old viewer folder | caught |
| 4 | `test_clean_room.CleanRoom.test_no_deposited_file_holds_a_user_folder_path` | README.md gives the runs folder by its full path | caught |
| 5 | `test_clips.BesideFiles.test_a_paired_run_is_its_own_timeline_and_a_beside_file` (new) | the paired timeline is written as the run's own file | caught |
| 6 | `test_clips.BesideFiles.test_the_preview_pins_the_run_timeline_as_converted` (new) | a timeline file's summary line gains a field | caught |
| 7 | `test_clips.PlacedClips.test_places_each_clip_and_lists_it_in_the_index` (new) | only the sync file is copied, not its clip | caught |
| 8 | `test_clips.PlacedClips.test_a_sync_file_with_no_clip_or_a_bad_field_is_not_placed` (new) | an fps of 0 is let through | caught |
| 9 | `test_convert.CanonicalJson.test_reproduces_every_contract_vector` | canonical JSON gains a space after commas | caught |
| 10 | `test_convert.HashChain.test_every_run_verifies` | one record of a copied practice run is changed | caught |
| 11 | `test_convert.HashChain.test_every_run_verifies` | one record of the copied ground-seat run is changed | caught |
| 12 | `test_convert.HashChain.test_a_changed_record_breaks_the_chain` | the chain check stops comparing prev_hash | caught |
| 13 | `test_convert.Limits.test_dictionary_has_the_sixteen_points` | a copied dictionary's yellow staleness limit is 12 s | caught |
| 14 | `test_convert.Limits.test_limit_states_match_every_observation` | a copied dictionary's load-current yellow high is 1.9 A | caught |
| 15 | `test_convert.TruthMapping.test_truth_matches_every_observation` | battery voltage is mapped to the bus voltage | caught |
| 16 | `test_convert.Timelines.test_each_practice_run_has_a_timeline_file` | the index leaves P4 out | caught |
| 17 | `test_convert.Timelines.test_p3_payload_shed_is_one_allowed_accepted_chain` | outcomes are dropped | caught |
| 18 | `test_convert.Timelines.test_p4_reset_and_the_frame_gap` | frame age turns yellow 20 s late | caught |
| 19 | `test_convert.Timelines.test_p3_process_has_two_malformed_turns_and_no_request` | malformed answers read as no action | caught |
| 20 | `test_convert.Timelines.test_check_ins_reports_and_contact` | check-ins land on the reports lane | caught |
| 21 | `test_convert.Timelines.test_v1_points_from_both_sources` | the payload rate lane is gone | caught |
| 22 | `test_convert.Timelines.test_every_record_is_drawn` | turn records are not marked as drawn | caught |
| 23 | `test_convert.Repeatable.test_the_same_inputs_give_the_same_files_whatever_the_hash_seed` | the truth flags are walked in their set's order | caught |
| 24 | `test_convert.PhaseTwo.test_reads_gzipped_truth` (new) | a .gz record file is never looked for | caught |
| 25 | `test_convert.PhaseTwo.test_says_when_it_skips_a_record_file` (new) | a file it did not read goes unmentioned | caught |
| 26 | `test_convert.PhaseTwo.test_says_when_it_skips_a_record_file` (new) | a folder with no event log is passed over in silence | caught |
| 27 | `test_convert.PhaseTwo.test_each_kind_of_truth_flag_has_a_row_of_its_own` (new) | truth flags are capped at three rows, as before | caught |
| 28 | `test_convert.PhaseTwo.test_the_fifty_each_beside_the_pass_of_its_plan_with_every_check_passing` (new) | a tool use is not counted on its turn | caught |
| 29 | `test_convert.GroundSeat.test_its_bundles_staleness_and_ground_link_are_drawn` | the ground link a bundle recorded is dropped | caught |
| 30 | `test_convert.GroundSeat.test_its_derived_frame_age_agrees_with_the_age_it_recorded` | the derived age is a second short | caught |
| 31 | `test_page.NoNetwork.test_no_network_calls_or_addresses` | verda.js gains a fetch | caught |
| 32 | `test_page.NoNetwork.test_html_loads_only_files_beside_it` | index.html gains an icon link | caught |
| 33 | `test_page.NoNetwork.test_content_security_policy_refuses_connections` | the policy allows connections to the page's origin | caught |
| 34 | `test_page.NoNetwork.test_content_security_policy_refuses_connections` | the policy lets video come from anywhere | caught |
| 35 | `test_page.NoWriting.test_page_writes_nothing` | verda.js saves to localStorage | caught |
| 36 | `test_page.NoWriting.test_recorded_text_is_never_parsed_as_html` | the inspector takes records as HTML | caught |
| 37 | `test_page_in_browser.PageInBrowser.test_asks_only_for_its_own_files_on_disk` | the page asks a local address for an image | caught |
| 38 | `test_page_in_browser.PageInBrowser.test_no_script_or_console_errors` | the page writes an error to the console | caught |
| 39 | `test_page_in_browser.PageInBrowser.test_draws_every_lane_of_each_run` | the contact lane is not drawn | caught |
| 40 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_a_request_and_its_records` | clicks on the timeline do nothing | caught |
| 41 | `test_page_in_browser.PageInBrowser.test_play_moves_the_playhead` | playback stands still | caught |
| 42 | `test_page_in_browser.PageInBrowser.test_a_name_near_the_right_edge_is_written_whole` (new) | a name near the right edge is cut, as before | caught |
| 43 | `test_page_in_browser.PageInBrowser.test_a_name_near_the_right_edge_is_written_whole` (new) | a request's label always goes after its marks | caught |
| 44 | `test_page_in_browser.PageInBrowser.test_a_run_opens_on_its_pass` (new) | a run opens on the whole of it | caught |
| 45 | `test_page_in_browser.PageInBrowser.test_a_known_met_lands_on_the_frame_the_sync_file_gives` (new) | the clip runs a frame ahead of the playhead | caught |
| 46 | `test_page_in_browser.PageInBrowser.test_a_mismatched_hash_shows_nothing` (new) | the pinned hash is not compared | caught |
| 47 | `test_page_in_browser.PageInBrowser.test_the_clip_holds_outside_its_frames_and_follows_play_and_pause` (new) | the clip runs past its last frame | caught |
| 48 | `test_page_in_browser.PageInBrowser.test_the_clip_holds_outside_its_frames_and_follows_play_and_pause` (new) | pausing the timeline leaves the clip playing | caught |
| 49 | `test_page_in_browser.PageInBrowser.test_every_lane_fits_a_1920_by_1080_screen` (new) | the charts never give up height to fit the screen | caught |
| 50 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_directors_command_and_his_rows` | clicks on the Director's command show nothing | caught |
| 51 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_scenarios_command_apart_from_his` | a click names the scenario's command the Director's | caught |
| 52 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_scenarios_command_apart_from_his` | the lane's note is cut to the label column | caught |
| 53 | `test_page_in_browser.PageInBrowser.test_the_ground_seat_age_lane_names_what_its_bundles_recorded` | the strip above the age chart is never drawn | caught |
| 54 | `test_passes.PassFiles.test_reads_all_five_passes` | each pass takes the last plan of its scenario, whatever its window | caught |
| 55 | `test_passes.PassFiles.test_p1_reads_both_blocks_of_repeated_columns` | arguments are read from the header's first block only | caught |
| 56 | `test_passes.PassFiles.test_what_his_telemetry_showed_next` | his counters are watched for 0 s after a command | caught |
| 57 | `test_passes.KnownCommandTimes.test_one_known_command_time_on_each_side` | the Director's command takes the MET of the frame after it | caught |
| 58 | `test_passes.KnownCommandTimes.test_one_known_command_time_on_each_side` | ODIN's dispatch is placed a second late | caught |
| 59 | `test_passes.LineUp.test_each_pass_lines_up_with_its_runs` | no run pairs with a pass | caught |
| 60 | `test_passes.LineUp.test_a_run_pairs_with_the_pass_flown_under_its_plan` (new) | a run's plan is never looked at | caught |
| 61 | `test_passes.LineUp.test_his_frame_age_shows_the_gap_in_his_p4_frames` | his frame age forgets the gap in his frames | caught |
| 62 | `test_passes.ScenarioCommands.test_reads_the_seven_and_checks_each_against_its_plan` | a copied file says P4's reset falls before contact and is kept | caught |
| 63 | `test_passes.ScenarioCommands.test_on_his_side_as_the_scenarios_and_never_his` | the scenario's commands are filed among his | caught |
| 64 | `test_passes.ScenarioCommands.test_on_his_side_as_the_scenarios_and_never_his` | the lane no longer says ODIN's runs drop the in-contact ones | caught |
| 65 | `test_passes.ScenarioCommands.test_what_his_telemetry_showed_after_the_scenarios_commands` | the frame stamped with the command's MET counts as before it | caught |
| 66 | `test_passes.ScenarioCommands.test_a_span_his_command_shares_with_the_scenarios_is_credited_to_neither` | a shared span is never looked for | caught |
| 67 | `test_passes.ScenarioCommands.test_odins_runs_dropped_exactly_the_in_contact_ones` | a copied file puts P4's reset at MET 1321 | caught |
| 68 | `test_record_types.RecordTypes.test_contract_and_schema_agree` | a copied contract drops TOOL_USE from its list | caught |
| 69 | `test_record_types.RecordTypes.test_every_contract_type_is_shown_or_listed` | TOOL_USE is missing from VERDA's table | caught |
| 70 | `test_watch_only.WatchOnly.test_converter_writes_only_its_files_and_leaves_the_run_untouched` | the converter leaves a file in the run folder | caught |
| 71 | `test_watch_only.WatchOnly.test_with_passes_it_writes_only_timelines_and_leaves_passes_and_plans_untouched` | the converter leaves a file in a pass folder | caught |
| 72 | `test_watch_only.WatchOnly.test_output_names_cannot_leave_the_folder` | output names may hold a backslash | caught |

One red case was rewritten before this deposit. In the run the Director saw, the 1920 × 1080 fit test's plant (the paired layout's charts kept their full height) no longer made the test fail, because the page's own rule, written after the plant, trims the charts to fit; the plant now switches that rule off (row 49 above). The run above is the whole set with that plant.

## Rehearsal

A draft of this deposit was unpacked into an empty `viewer` folder with no `inputs/` beside it, as in the repository, and run there on 30 October 2026 with only `VERDA_INPUTS` and `PYTHONDONTWRITEBYTECODE` set. The draft had the same files as this deposit, except that this section was not yet written. Result: **Ran 64 tests, OK; 72 red cases, 72 caught; then the whole suite again, Ran 64 tests, OK.** Afterwards every deposited file was unchanged (checked against `MANIFEST.sha256`), no file had been added, and the only thing left was an empty `.scratch` folder.

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
| `VERDA_SCRIPTED` | leave unset | Defaults to `VERDA_INPUTS\scripted-commands\phase2_scripted_commands.json` |
| `VERDA_CLIPS` | leave unset | New. Defaults to `VERDA_INPUTS\clips` |
| `VERDA_PAGE` | leave unset | Defaults to the deposited `page` folder |
| `VERDA_BROWSER` | leave unset | The browser test finds Chrome or Edge in their usual places |
| `PYTHONDONTWRITEBYTECODE` | `1` | Keeps `__pycache__` folders out of the viewer folder; the repeatability test passes it on to the converter runs it starts |

What to expect: the unittest run ends `Ran 64 tests` and `OK`, in about four minutes; `show_red.py` lists 72 red cases, each `caught`, ends with `RESULT: every red case caught, and the suite passes`, and exits 0, in about forty minutes. It needs Chrome or Edge installed, able to play the preview clip (an MP4). The clean-room test reads this DEPOSIT.md and MANIFEST.sha256 too, so they must sit in the viewer folder as deposited. The tests need the inputs of 30 October 2026 (1,498 files): with fewer, the tests that read the new runs or the clips stop on an error naming the missing input, and the run does not pass.

What the run touches: `show_red.py` plants each change in a file in the viewer folder and restores it byte for byte before the next; it keeps each original in `.scratch\red-backup` inside the viewer folder while planted and deletes it after, which leaves an empty `.scratch` folder there (git does not track empty folders). The tests write their timeline files and placed clips to temporary folders only. If a run is stopped partway, the next run restores any planted file from that backup first. After the run, `git status` should show the tree unchanged.

## The converter, with VERDA's inputs

In the VERDA folder, where `inputs\` sits beside VERDA's files:

```
python convert/verda_convert.py --all inputs/runs --passes inputs/pass-records --plans inputs/plans --scripted inputs/scripted-commands/phase2_scripted_commands.json --clips inputs/clips
```

It writes, into `page/timelines/`, one timeline file for each run and each pass no run pairs with, a beside file for each run paired with a pass, and a copy of each clip and its sync file in `clips/`, and lists them all in `page/timelines/index.js`; it ends with a line for each clip saying whether its timeline file is the one it pins. Then open `page/index.html` from disk. From the repository's `viewer` folder, the same command works with each `inputs/` read as `<VERDA folder>\inputs\`. It then writes `page/timelines/` inside the `viewer` folder, which is generated and not part of the deposit: leave it untracked, or delete it after viewing.

For the animation session: the timeline file a clip should be rendered from is the run's own `<run_id>.js` this command writes; its SHA-256 is the one `index.js` lists for it. A beside file is never what a clip pins.

## Suggested commit message

```
viewer: VERDA-05, V4, phase 2's runs and the animation pane

VERDA now plays phase 2's fifty scored runs, each beside the Director's
flight of the pass flown under its plan, with the simulator truth the
runs keep gzip-compressed, checked on the records inside. The converter
never skips a run folder's file silently: what it does not read is
named in the timeline's warnings.

A run beside a pass is two files: the run's own timeline, byte for
byte the run alone, and a beside file with what pairing adds, which
pins the run's file. An animation clip pins the run's own file, and
beside the timeline the page plays it, locked to the playhead, only
when its sync file's run_id and timeline_sha256 match the timeline on
screen; otherwise it shows nothing and says why. It holds before the
first frame and after the last, and moves with play, pause and scrub,
using the browser's own video element.

Fixed: a name or label near the right edge is written before its mark;
each kind of truth flag has a row of its own; a run with more rows
than most still fits a 1920 x 1080 screen.

64 tests, each shown failing on a planted red case (72 red cases,
tests/show_red.py).
```
