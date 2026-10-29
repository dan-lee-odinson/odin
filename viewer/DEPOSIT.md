# VERDA-03: V2, ODIN beside the Director's flight

| Field | Value |
|---|---|
| Deposit | VERDA-03, after VERDA-02, which is committed in the repository's `viewer` folder. It replaces every VERDA file in that folder; no file of VERDA-02's is left out. |
| Milestone | V2 of the brief (section 5), "ODIN beside your flight": a run ODIN flew and the Director's own pass of the same scenario on one MET axis, his commands placed from his files, what his telemetry showed after each, and the commands the scenario sent by itself shown on his side, apart from his. The ground-seat run's staleness and ground link are drawn. P1, P2a and P2b line up with ODIN's runs when those runs arrive; until then each is shown alone, beside its plan's contact window. By the Director's word of 29 October 2026, that part of V2's "done when" waits for the runs. |
| Seen running by the Director | 29 October 2026: 1920 × 1080 screenshots of the page running in headless Chrome, with each test run and its red cases. First the P3 practice run beside his P3 pass and the P4 run beside his P4 pass. Then, after the scripted-commands input arrived, P4 at MET 1380 with the scenario's reset at MET 1320 clicked, and the ground-seat run at MET 909 with ODIN's recorded YELLOW clicked. The Director confirmed both screenshots and said to deposit on 29 October 2026. |
| Built by | The VERDA session (Claude Code), directed by Dan Lee-Odinson, Director |
| Inputs it was built and tested against | inputs/MANIFEST.sha256 as of 29 October 2026, 251 files, all matching: the 226 placed on 28 October 2026 (ODIN commit 46b3c33), and 25 added by Claude Code on 29 October 2026, the ground-seat run `runs/dev-s5-live-ground-seat/` (run ID dev-s6-0001) and `scripted-commands/phase2_scripted_commands.json` |

## What is in it

| Path | What it is |
|---|---|
| `README.md` | What VERDA is, how to use it, the look, where each thing on the page comes from, the Director's flown pass, the scenario's own commands, the pre-existing files, the timeline format, the checks |
| `convert/verda_convert.py` | The converter: run folders, the Director's passes, the plans and the scripted-commands file in, timeline files out, after checking the log's hash chain and head, the truth file's chain and head, and each saved turn bundle's hash |
| `convert/pass_records.py` (new) | Reads the Director's pass folders (`telemetry_hk.csv`, `commands.csv`, COSMOS exports, read by position), places each of his commands on the MET axis between the two frames received around its UTC time, and reads what his command counters showed after it, and after each of the scenario's commands |
| `convert/scripted_commands.py` (new) | Reads `phase2_scripted_commands.json` and checks each entry against its pass's own plan file: the contact window, before or in contact, and that a command in contact is not kept |
| `convert/huginn_dictionary.py` | Reads the telemetry points and limits from HUGINN's dictionary, and applies the contract's limit-state rule (section 16.2, U7) |
| `convert/record_types.py` | How each of the contract's 25 record types is shown (all 25 are) |
| `page/index.html`, `page/verda.css`, `page/verda.js` | The page: static, opened from disk, no network request, writes nothing |
| `page/fonts/Michroma-Regular.ttf`, `page/fonts/OFL.txt` | Pre-existing, unchanged since VERDA-02: the Michroma font, used for titles only, and its license (SIL Open Font License 1.1) |
| `tests/` | 49 tests (unittest), the red-case runner `show_red.py`, and `browser_probe.py`, which drives headless Chrome or Edge for the browser test |
| `MANIFEST.sha256` | Every other file in this deposit with its SHA-256 |
| `DEPOSIT.md` | This file |

All of it is new, written on 28 and 29 October 2026, except the two font files (see VERDA-02 and the README's Pre-existing section). It uses no third-party library. `scripted_commands.py` reads a data file Claude Code derived from HUGINN's scenario files; VERDA reads no HUGINN file.

Left out, as the brief says: `inputs/`, every run folder and pass folder, the timeline files the converter writes (`page/timelines/`, generated; a reader runs the converter to make them), the brief itself, scratch files and caches. Nothing secret is in it. No file in it holds a path under a user's folder, a user name, a machine name or an email address: the clean-room test checks for the first in every file listed here, this DEPOSIT.md and MANIFEST.sha256 included, and before writing the zip the VERDA session's deposit script checked every file for all four and would not have written it if it had found one.

## What changed since VERDA-02

- **The Director's pass beside the run.** With `--passes` and `--plans`, each run is paired with the Director's pass of its scenario whose frames its MET span covers most of (at least half), and each pass takes the plan of its scenario whose contact window holds most of its frames. His telemetry is a violet line on each telemetry lane and a DIRECTOR row on each state lane; the age of his newest frame is on the telemetry-age lane; his commands are on their own lane under ODIN's requests. A pass no run pairs with yet (P1, P2a, P2b) has a timeline of its own, beside its plan's contact window.
- **His commands on the MET axis.** A command in `commands.csv` carries only its UTC time. VERDA places it between the frames his ground station received just before and just after it, by linear interpolation; the spacecraft's clock and UTC drift apart by up to 1 % in these passes, so one fixed offset would misplace a command by several seconds. What followed is read from his command counters in the next 10 s: "accepted", "rejected" with the reason, or "no counter change", labeled as derived by VERDA. Click a command for the rows of his files it came from.
- **The scenario's own commands** (`--scripted`). The commands each scenario sent by itself, which his passes carried, are on a lane of their own under his, as hollow diamonds, never his triangle, and the legend says "The scenario's commands, not his". Their hover and record say they are the scenario's, not the Director's, and give their HUGINN file and line. The lane says that ODIN's runs drop the in-contact ones (the Director's ruling on U35), and each command says whether ODIN's runs keep or drop it. A counter change in a span where both his command and the scenario's were sent is credited to neither; in the five passes, none is. Without the file, the lane says so and shows none. Nothing on the page says why a frame stream resumed: it shows only what the files hold.
- **The ground-seat run.** Its bundles record the ground staleness state and the ground link, so its telemetry-age lane has a strip above the chart: STALENESS (circles) and LINK (squares), each row named where its state changes, with the received-packet count on hover.
- **A fix: the same inputs now give the same files.** The truth lane's flags were walked in a set's order, which changes with Python's hash seed, so a timeline file (and the order of P4's truth rows) could change from one run of the converter to the next. They are now sorted, and a test converts every input under four hash seeds.
- **Layout.** A few lanes are a few pixels shorter, so that P4 beside his pass, with the scenario's lane, fits a 1920 × 1080 screen without scrolling. A lane with no scale may run its note into the scale's gutter. Two legend entries are shorter, so the footer stays on one line.
- **Tests.** 49 now: 18 new and 1 renamed, marked in the table below. `tests/_support.py` knows the ground-seat run and the scripted-commands file, and `VERDA_SCRIPTED` may point a test at another copy of it.

## Known, for the next deposit

On the ground-seat run, the truth lane's "Fault onset" label is cut off at the right edge ("Fault onse..."), because the fault starts at MET 900, near the end of the view. The Director noted it on 29 October 2026 for the next deposit, not this one.

## Tests run, and their results

In the VERDA folder, on these exact files, on 29 October 2026:

- `python -m unittest discover -s tests -v`: **Ran 49 tests, OK.**
- `python tests/show_red.py`: **53 red cases, 53 caught**, then the whole suite again: **Ran 49 tests, OK.** "RESULT: every red case caught, and the suite passes."

A red case counts as caught only if its test ran and failed. A test that did not run, passed, or stopped on an error does not count. Each was planted, run alone and restored byte for byte. A test that checks two things that could each go wrong alone has a red case for each:

| # | Test | Planted change | Result |
|---|---|---|---|
| 1 | `test_clean_room.CleanRoom.test_the_scan_sees_verda_files` | the scan skips the convert folder | caught |
| 2 | `test_clean_room.CleanRoom.test_nothing_imports_the_old_viewer_package` | a planted file imports the old viewer package | caught |
| 3 | `test_clean_room.CleanRoom.test_nothing_names_the_old_viewer_folders` | a planted file names the old viewer folder | caught |
| 4 | `test_clean_room.CleanRoom.test_no_deposited_file_holds_a_user_folder_path` | README.md gives the runs folder by its full path | caught |
| 5 | `test_convert.CanonicalJson.test_reproduces_every_contract_vector` | canonical JSON gains a space after commas | caught |
| 6 | `test_convert.HashChain.test_every_run_verifies` (renamed from `test_practice_runs_verify`; now every run) | one record of a copied practice run is changed | caught |
| 7 | `test_convert.HashChain.test_every_run_verifies` (renamed from `test_practice_runs_verify`; now every run) | one record of the copied ground-seat run is changed | caught |
| 8 | `test_convert.HashChain.test_a_changed_record_breaks_the_chain` | the chain check stops comparing prev_hash | caught |
| 9 | `test_convert.Limits.test_dictionary_has_the_sixteen_points` | a copied dictionary's yellow staleness limit is 12 s | caught |
| 10 | `test_convert.Limits.test_limit_states_match_every_observation` | a copied dictionary's load-current yellow high is 1.9 A | caught |
| 11 | `test_convert.TruthMapping.test_truth_matches_every_observation` | battery voltage is mapped to the bus voltage | caught |
| 12 | `test_convert.Timelines.test_each_practice_run_has_a_timeline_file` | the index leaves P4 out | caught |
| 13 | `test_convert.Timelines.test_p3_payload_shed_is_one_allowed_accepted_chain` | outcomes are dropped | caught |
| 14 | `test_convert.Timelines.test_p4_reset_and_the_frame_gap` | frame age turns yellow 20 s late | caught |
| 15 | `test_convert.Timelines.test_p3_process_has_two_malformed_turns_and_no_request` | malformed answers read as no action | caught |
| 16 | `test_convert.Timelines.test_check_ins_reports_and_contact` | check-ins land on the reports lane | caught |
| 17 | `test_convert.Timelines.test_v1_points_from_both_sources` | the payload rate lane is gone | caught |
| 18 | `test_convert.Timelines.test_every_record_is_drawn` | turn records are not marked as drawn | caught |
| 19 | `test_convert.Repeatable.test_the_same_inputs_give_the_same_files_whatever_the_hash_seed` (new) | the truth flags are walked in their set's order | caught |
| 20 | `test_convert.GroundSeat.test_its_bundles_staleness_and_ground_link_are_drawn` (new) | the ground link a bundle recorded is dropped | caught |
| 21 | `test_convert.GroundSeat.test_its_derived_frame_age_agrees_with_the_age_it_recorded` (new) | the derived age is a second short | caught |
| 22 | `test_page.NoNetwork.test_no_network_calls_or_addresses` | verda.js gains a fetch | caught |
| 23 | `test_page.NoNetwork.test_html_loads_only_files_beside_it` | index.html gains an icon link | caught |
| 24 | `test_page.NoNetwork.test_content_security_policy_refuses_connections` | the policy allows connections to the page's origin | caught |
| 25 | `test_page.NoWriting.test_page_writes_nothing` | verda.js saves to localStorage | caught |
| 26 | `test_page.NoWriting.test_recorded_text_is_never_parsed_as_html` | the inspector takes records as HTML | caught |
| 27 | `test_page_in_browser.PageInBrowser.test_asks_only_for_its_own_files_on_disk` | the page asks a local address for an image | caught |
| 28 | `test_page_in_browser.PageInBrowser.test_no_script_or_console_errors` | the page writes an error to the console | caught |
| 29 | `test_page_in_browser.PageInBrowser.test_draws_every_lane_of_each_run` | the contact lane is not drawn | caught |
| 30 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_a_request_and_its_records` | clicks on the timeline do nothing | caught |
| 31 | `test_page_in_browser.PageInBrowser.test_play_moves_the_playhead` | playback stands still | caught |
| 32 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_directors_command_and_his_rows` (new) | clicks on the Director's command show nothing | caught |
| 33 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_scenarios_command_apart_from_his` (new) | a click names the scenario's command the Director's | caught |
| 34 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_scenarios_command_apart_from_his` (new) | the lane's note is cut to the label column | caught |
| 35 | `test_page_in_browser.PageInBrowser.test_the_ground_seat_age_lane_names_what_its_bundles_recorded` (new) | the strip above the age chart is never drawn | caught |
| 36 | `test_passes.PassFiles.test_reads_all_five_passes` (new) | each pass takes the last plan of its scenario, whatever its window | caught |
| 37 | `test_passes.PassFiles.test_p1_reads_both_blocks_of_repeated_columns` (new) | arguments are read from the header's first block only | caught |
| 38 | `test_passes.PassFiles.test_what_his_telemetry_showed_next` (new) | his counters are watched for 0 s after a command | caught |
| 39 | `test_passes.KnownCommandTimes.test_one_known_command_time_on_each_side` (new) | the Director's command takes the MET of the frame after it | caught |
| 40 | `test_passes.KnownCommandTimes.test_one_known_command_time_on_each_side` (new) | ODIN's dispatch is placed a second late | caught |
| 41 | `test_passes.LineUp.test_each_pass_lines_up_with_its_runs` (new) | no run pairs with a pass | caught |
| 42 | `test_passes.LineUp.test_his_frame_age_shows_the_gap_in_his_p4_frames` (new) | his frame age forgets the gap in his frames | caught |
| 43 | `test_passes.ScenarioCommands.test_reads_the_seven_and_checks_each_against_its_plan` (new) | a copied file says P4's reset falls before contact and is kept | caught |
| 44 | `test_passes.ScenarioCommands.test_on_his_side_as_the_scenarios_and_never_his` (new) | the scenario's commands are filed among his | caught |
| 45 | `test_passes.ScenarioCommands.test_on_his_side_as_the_scenarios_and_never_his` (new) | the lane no longer says ODIN's runs drop the in-contact ones | caught |
| 46 | `test_passes.ScenarioCommands.test_what_his_telemetry_showed_after_the_scenarios_commands` (new) | the frame stamped with the command's MET counts as before it | caught |
| 47 | `test_passes.ScenarioCommands.test_a_span_his_command_shares_with_the_scenarios_is_credited_to_neither` (new) | a shared span is never looked for | caught |
| 48 | `test_passes.ScenarioCommands.test_odins_runs_dropped_exactly_the_in_contact_ones` (new) | a copied file puts P4's reset at MET 1321 | caught |
| 49 | `test_record_types.RecordTypes.test_contract_and_schema_agree` | a copied contract drops TOOL_USE from its list | caught |
| 50 | `test_record_types.RecordTypes.test_every_contract_type_is_shown_or_listed` | TOOL_USE is missing from VERDA's table | caught |
| 51 | `test_watch_only.WatchOnly.test_converter_writes_only_its_files_and_leaves_the_run_untouched` | the converter leaves a file in the run folder | caught |
| 52 | `test_watch_only.WatchOnly.test_with_passes_it_writes_only_timelines_and_leaves_passes_and_plans_untouched` (new) | the converter leaves a file in a pass folder | caught |
| 53 | `test_watch_only.WatchOnly.test_output_names_cannot_leave_the_folder` | output names may hold a backslash | caught |

## Rehearsal

A draft of this deposit was unpacked into an empty `viewer` folder with no `inputs/` beside it, as in the repository, and run there on 29 October 2026 with only `VERDA_INPUTS` and `PYTHONDONTWRITEBYTECODE` set. The draft had the same files as this deposit, except that this section was not yet written. Result: **Ran 49 tests, OK; 53 red cases, 53 caught; then the whole suite again, Ran 49 tests, OK.** Afterwards every deposited file was unchanged (checked against `MANIFEST.sha256`), no file had been added, and the only thing left was an empty `.scratch` folder.

The first rehearsal found one failure, in this file: the draft named the repository's viewer folder with a trailing slash, which the clean-room test bars because that is how HUGINN's old viewer folder would be named. The draft was reworded and rehearsed again, with the result above.

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
| `VERDA_SCRIPTED` | leave unset | New. Defaults to `VERDA_INPUTS\scripted-commands\phase2_scripted_commands.json` |
| `VERDA_PAGE` | leave unset | Defaults to the deposited `page` folder |
| `VERDA_BROWSER` | leave unset | The browser test finds Chrome or Edge in their usual places |
| `PYTHONDONTWRITEBYTECODE` | `1` | Keeps `__pycache__` folders out of the viewer folder; the repeatability test passes it on to the converter runs it starts |

What to expect: the unittest run ends `Ran 49 tests` and `OK`, in about 40 seconds; `show_red.py` lists 53 red cases, each `caught`, ends with `RESULT: every red case caught, and the suite passes`, and exits 0. It needs Chrome or Edge installed, and takes about seven minutes. The clean-room test reads this DEPOSIT.md and MANIFEST.sha256 too, so they must sit in the viewer folder as deposited. The tests need the inputs of 29 October 2026 (251 files): with only the 226 of 28 October, the tests that read the ground-seat run or the scripted-commands file stop on an error naming the missing input, and the run does not pass.

What the run touches: `show_red.py` plants each change in a file in the viewer folder and restores it byte for byte before the next; it keeps each original in `.scratch\red-backup` inside the viewer folder while planted and deletes it after, which leaves an empty `.scratch` folder there (git does not track empty folders). The tests write their timeline files to temporary folders only. If a run is stopped partway, the next run restores any planted file from that backup first. After the run, `git status` should show the tree unchanged.

## The converter, with VERDA's inputs

In the VERDA folder, where `inputs\` sits beside VERDA's files:

```
python convert/verda_convert.py --all inputs/runs --passes inputs/pass-records --plans inputs/plans --scripted inputs/scripted-commands/phase2_scripted_commands.json
```

It writes one timeline file for each run and each pass no run pairs with into `page/timelines/` and lists them in `page/timelines/index.js`; then open `page/index.html` from disk. From the repository's `viewer` folder, the same command works with each `inputs/` read as `<VERDA folder>\inputs\`. It then writes `page/timelines/` inside the `viewer` folder, which is generated and not part of the deposit: leave it untracked, or delete it after viewing.

## Suggested commit message

```
viewer: VERDA-03, V2, ODIN beside the Director's flight

VERDA now plays a run ODIN flew beside the Director's own pass of the
same scenario, on one MET axis. His telemetry is drawn on each lane;
his commands, from commands.csv, are placed between the two frames his
ground station received around each one's UTC time, since the
spacecraft's clock drifts up to 1 percent from UTC; and what his
command counters showed next is read from his telemetry, labeled as
derived by VERDA. A pass no run pairs with yet stands alone beside its
plan's contact window.

The commands each scenario sent by itself, which his passes carried,
are on his side in a lane of their own, never as his, and the page
says ODIN's runs drop the in-contact ones (U35). Each entry of the
scripted-commands input is checked against its plan's window. The
ground-seat run's recorded staleness and ground link are drawn above
its telemetry-age chart.

Fixed: the truth lane's flags were walked in set order, so a timeline
file could change with Python's hash seed; they are sorted now.

49 tests, each shown failing on a planted red case (53 red cases,
tests/show_red.py).
```
