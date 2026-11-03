# VERDA-06: the demo video's VERDA shots, and the replay site

| Field | Value |
|---|---|
| Deposit | VERDA-06, after VERDA-05, which is committed in the repository's `viewer` folder. It replaces every VERDA file in that folder; no file of VERDA-05's is left out, and four are new: `capture/verda_capture.py`, `site/build_site.py`, `tests/test_capture.py` and `tests/test_site.py`. |
| Milestone | VERDA-06, as the Director set it on 2 November 2026, in three stages: (1) the timeline the animation session renders PH2-PASS3-SPARK-R2's instrument cut from, and the animation pane's size; (2) the footage, three shots filmed from the page a frame at a time; (3) the replay site, built from the repository's committed records for GitHub Pages. With his four additions of 3 November 2026: the page as filmed goes on the site (the cites view, the no-clip layout, the name rules, the fixed grid rows), the capture tool's seek stays out of the site's page, the capture tool goes in this deposit, and SPARK-R2 on the site gets the site clip only. |
| Seen running by the Director | 3 November 2026: the footage of stage 2, take 2, three shots of the page as filmed, which he checked against their hashes, probed, looked at frame by frame and accepted. For stage 3 he decided the pane's caption on 3 November 2026 and said to deposit VERDA-06 as built. |
| Built by | The VERDA session (Claude Code), directed by Dan Lee-Odinson, Director |
| Inputs it was built and tested against | inputs/MANIFEST.sha256 as of 2 November 2026, sha256 `301c2e9852d830f7394516e7f49c01bb9e2f4e6f0f97dc8b07d6e2459854ef60`, 2,444 files, all matching: the 1,498 of 30 October 2026; phase 3's scenarios A and D, twenty run folders (`runs/PH3-H02-*`, `runs/PH3-H04-*`, from the repository's runs/scored/ at f32c34d) and their two plans, added by Claude Code on 2 November 2026; and PH2-PASS3-SPARK-R2's two instrument-cut clips with their sync files, copied by VERDA on 2 November 2026 from the render session's out/final/ by the SHA-256 the Director gave |

## What is in it

| Path | What it is |
|---|---|
| `README.md` | What VERDA is, how to use it, the look, where each thing on the page comes from, the Director's flown pass, the scenario's own commands, the animation pane and its caption, one of ODIN's reports, the replay site, the video's VERDA shots, the pre-existing files, the timeline format, the checks |
| `site/build_site.py` (new) | Builds the replay site's folder from the committed records: exactly its seventy runs, the site clip with its full caption, and every check below |
| `capture/verda_capture.py` (new) | Films the page a frame at a time and encodes the frames with ffmpeg: how the video's VERDA shots were made |
| `convert/verda_convert.py` | The converter, unchanged since VERDA-05 |
| `convert/clips.py` | Reads each animation clip's sync file, copies the clip, its sync file and its caption if it has one beside the timelines, and lists them for `index.js` |
| `convert/pass_records.py`, `convert/scripted_commands.py`, `convert/huginn_dictionary.py`, `convert/record_types.py` | Unchanged since VERDA-05 |
| `page/index.html`, `page/verda.css`, `page/verda.js` | The page: static, from disk or served, no network request, writes nothing |
| `page/fonts/Michroma-Regular.ttf`, `page/fonts/OFL.txt` | Pre-existing, unchanged since VERDA-02: the Michroma font, used for titles only, and its license (SIL Open Font License 1.1) |
| `tests/` | 88 tests (unittest), the red-case runner `show_red.py`, and `browser_probe.py`, which drives headless Chrome or Edge and serves a folder on 127.0.0.1 as GitHub Pages serves it |
| `MANIFEST.sha256` | Every other file in this deposit with its SHA-256 |
| `DEPOSIT.md` | This file |

All of it is new, written from 28 October to 3 November 2026, except the two font files (see VERDA-02 and the README's Pre-existing section). It uses no third-party library. It holds no clip, no timeline file, no site and no shot.

Left out, as the brief and the Director say: `inputs/`, every run folder, pass folder and clip, the timeline files the converter writes (`page/timelines/`, generated), the site the build writes, the footage and its frame logs, the render timeline in VERDA's `out/`, and ffmpeg, which the capture tool encodes with: a third-party program (9.0.2, gyan.dev's essentials build, GPL v3) kept in a folder of VERDA's that no deposit takes. Also left out: the brief, scratch files and caches. Nothing secret is in it. No file in it holds a path under a user's folder, a user name, a machine name or an email address: the clean-room test checks for the first in every file listed here, this DEPOSIT.md and MANIFEST.sha256 included, and before writing the zip the VERDA session's deposit script checked every file for all four and would not have written it if it had found one.

## What changed since VERDA-05

- **The replay site** (`site/build_site.py`). It converts exactly phase 2's fifty scored runs, each beside the Director's pass flown under its plan, and phase 3's scenarios A (`PH3-H02-*`) and D (`PH3-H04-*`), each alone; B, C and E stay off. It places PH2-PASS3-SPARK-R2's site clip and no other clip, with the clip's full caption beside it. It fails, and leaves no site, if a run is missing or will not convert, if any of a run's checks fails or the converter warns of a file it could not read, if a clip is not the site clip, if a clip pins a timeline file the site does not hold byte for byte, or if PH2-PASS3-SPARK-R2's own timeline is not the stage-1 file both its clips pin (sha256 `d0f1a57349d60cbee5835f3bac6a945e02762ecf49387ebca6caa968d12fe617`). The page goes on the site as it is, its Content-Security-Policy with it: watch-only, reading only its own files. The site's folder must not exist yet; the build writes beside it and renames it into place when whole.
- **On the page, for the site.** A line in the header: "These are replays of recorded runs in a simulation." Under a clip, the Director's caption line: "The animation shows simulated data drawn from the run's own record. The spacecraft's look and pose are drawn." and a "Full caption" link that opens the clip's whole caption in the Record panel, in its renderer's words: for the site clip, CAPTIONS.md's caption for an A5 clip with its instrument cut's sentences, its space-weather sentence said for this run ("this run carries none"), and no epoch sentence (the PASS-3 runs' epochs are not shifted). A clip's caption travels with it as `<name>.caption.txt`; the site build writes the site clip's.
- **The page as filmed.** One of ODIN's reports opens in the Record panel beside the records it links by ID, and only those: the trigger of its turn (`turn_id`) and the records of each request its actions name (`request_id`), as far as the log had come; its answer exactly as written, nothing said of whether it is right, each record picked out in turn. With no clip listed for a run, the pane steps aside and the event log takes its place, with no notice. A name cut short by the next mark on its row is written whole before its own mark, as one near the right edge already was. The timeline and side column hold their rows: the hidden banner had shifted the page's grid, so that the main area followed the side column's text and the timeline gained a scrollbar mid-shot.
- **The turns lane** (the item left from VERDA-04's round, "T11 MALFOR..."): a turn's name near the right edge is written before its mark when the row is clear there, and where it fits neither way, as T11's does in the development run (T10's name fills the room before it), the turn's number alone is written, whole; the hover has the rest.
- **The capture tool** (`capture/verda_capture.py`), which filmed the three shots. It makes the page in a temporary folder with one clip at most, adds its own seek (`VERDA_SEEK`) to its copy of `verda.js` only, and for each frame sets the playhead to that frame's MET, waits until the pane shows the clip frame the sync file gives, checks that frame against the frame the browser presented and the page's layout against the first frame's, and takes a screenshot; ffmpeg encodes them as H.264. The shots were filmed with the page and tool at the hashes FOOTAGE.md lists, with the seek then in the page; since then the seek has moved into the tool's copy, and the page has gained the site's line, the caption, the turns-lane rule and the Record panel's room for the caption.
- **Tests.** 88 now, 24 of them new, marked in the table below.

## Timeline files, and the clips that pin them

The converter's timeline code is unchanged since VERDA-05 (`convert/verda_convert.py` byte for byte), so every timeline file and beside file is the one VERDA-05 makes. `convert/clips.py` changed only to carry captions: `index.js` lists a `caption` with each clip. PH2-PASS3-SPARK-R2's own timeline is `d0f1a57349d60cbee5835f3bac6a945e02762ecf49387ebca6caa968d12fe617`, 504,249 bytes, the file in VERDA's `out/for-render/` that both its clips pin; the site build checks it, and a test does too.

## For Claude Code's workflow: building the site

Claude Code adds the GitHub Actions workflow that runs the build and publishes the folder; nothing the build writes is committed. From the repository's `viewer` folder:

```
python site/build_site.py \
  --runs ../runs/scored \
  --passes <the Director's pass folders> \
  --plans <a folder holding the five phase-2 TYR-0 plans> \
  --scripted <phase2_scripted_commands.json> \
  --dictionary <HUGINN's defs/tlm_cmd.yaml> \
  --clip <PH2-PASS3-SPARK-R2_instrument_site.sync.json, its .mp4 beside it> \
  --out <the folder to publish, which must not exist yet>
```

| Option | What VERDA's inputs used, and where they came from |
|---|---|
| `--runs` | `inputs/runs`: the phase-2 runs from the repository's runs/scored/ (at ae92800, as the inputs manifest now names it), the phase-3 runs from runs/scored/ at f32c34d. The build takes only the seventy it names. |
| `--passes` | `inputs/pass-records`: the Director's flown passes, from the repository's inputs-pre-existing/comparison-only/pass-records/ |
| `--plans` | `inputs/plans`: the five phase-2 TYR-0 plans, unsigned, placed on 28 October 2026 (the folder also holds phase 3's two plans, which the build reads and pairs with no pass) |
| `--scripted` | `inputs/scripted-commands/phase2_scripted_commands.json`, sha256 `2347479e847ab284d196173adbeed8602c9d3fae226834c9124492f3bc0483e3`, derived by Claude Code from HUGINN's sim/scenarios/ at b4dbe61; the workflow needs this file committed or made the same way |
| `--dictionary` | `inputs/dictionaries/HUGINN/tlm_cmd.yaml`, HUGINN's defs/tlm_cmd.yaml, sha256 `5e1c2750ef9e0d5463f8b2fcb27abeb1dbde63c1b749717ed170cc2bacd60679`. Another dictionary makes other timeline bytes, and the build then fails on SPARK-R2's pin. |
| `--clip` | `inputs/clips/PH2-PASS3-SPARK-R2_instrument_site.sync.json` (sha256 `ea62af066346a75ba20bb4355ad9d7725f2cc91b252bde20dc1318f1d70cf670`) with `PH2-PASS3-SPARK-R2_instrument_site.mp4` (sha256 `cc0432f4598f10af8c3d6f3dca5c5a9236b98481ca3918db22802baeef12a09b`) beside it, from the render session's out/final/; the workflow needs them committed |

The build needs Python 3 and nothing else (it was run with Python 3.14.4); it reads the records and writes only `--out`. It printed, with VERDA's inputs: `site -> ...: 70 runs (50 beside the Director's pass, 20 alone), clips PH2-PASS3-SPARK-R2_instrument_site.mp4 for PH2-PASS3-SPARK-R2, PH2-PASS3-SPARK-R2.js as pinned`. On any failure it prints `SITE NOT BUILT:` and the reason, and exits 1. The page works served from any folder of a site: its links are relative.

## The video's VERDA shots

FOOTAGE.md, in the video-edit folder beside the three shots, lists each shot's SHA-256, run, MET range, speed and the timeline and clip hashes it shows. The capture tool's command for each, from VERDA's folder (with `--ffmpeg` naming an ffmpeg build; the shots used 9.0.2, gyan.dev's essentials build, `ffmpeg-9.0.2-essentials_build.zip`, sha256 `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`):

```
python capture/verda_capture.py --run inputs/runs/PH2-PASS3-SPARK-R2 --passes inputs/pass-records --plans inputs/plans --scripted inputs/scripted-commands/phase2_scripted_commands.json --clip inputs/clips/PH2-PASS3-SPARK-R2_instrument_footage.sync.json --expect-timeline d0f1a57349d60cbee5835f3bac6a945e02762ecf49387ebca6caa968d12fe617 --from 880 --to 1000 --speed 2 --out <shot 1>
python capture/verda_capture.py --run inputs/runs/PH2-PASS3-SPARK-R2 --passes inputs/pass-records --plans inputs/plans --scripted inputs/scripted-commands/phase2_scripted_commands.json --clip inputs/clips/PH2-PASS3-SPARK-R2_instrument_site.sync.json --expect-timeline d0f1a57349d60cbee5835f3bac6a945e02762ecf49387ebca6caa968d12fe617 --hold 1158 --seconds 12 --steps <shot 2's clicks> --out <shot 2>
python capture/verda_capture.py --run inputs/runs/PH3-H04-SPARK-R1 --passes inputs/pass-records --plans inputs/plans --scripted inputs/scripted-commands/phase2_scripted_commands.json --from 7159 --to 7309 --speed 5 --view 7150-7320 --out <shot 3>
```

Shot 2's clicks: `[{"frame": 1, "click_label": "Report CHECK_IN"}, {"frame": 91, "pick_record": 66}, {"frame": 145, "pick_record": 31}, {"frame": 199, "pick_record": 32}, {"frame": 253, "pick_record": 33}, {"frame": 307, "pick_record": 36}]`.

## Tests run, and their results

In the VERDA folder, on these files (with VERDA-05's DEPOSIT.md in place of this one, which the rehearsal below covers), on 3 November 2026:

- `python tests/show_red.py`: **100 red cases, 100 caught**, then the whole suite: **Ran 88 tests, OK.** "RESULT: every red case caught, and the suite passes." It took 57 minutes.

A red case counts as caught only if its test ran and failed. A test that did not run, passed, or stopped on an error does not count. Each was planted, run alone and restored byte for byte. A test that checks two things that could each go wrong alone has a red case for each:

| # | Test | Planted change | Result |
|---|---|---|---|
| 1 | `test_capture.CaptureTool.test_the_seek_is_the_capture_tools_own` (new) | the site's page carries a seek of its own | caught |
| 2 | `test_capture.CaptureTool.test_a_moving_shot_runs_from_its_first_met_to_its_last` (new) | a shot stops a frame short of its last MET | caught |
| 3 | `test_capture.CaptureTool.test_the_capture_names_each_clip_frame_as_the_page_does` (new) | the capture rounds the clip frame down with no allowance | caught |
| 4 | `test_capture.CaptureTool.test_a_clip_pinned_to_another_timeline_is_not_filmed` (new) | the clip's pinned hash is not compared | caught |
| 5 | `test_clean_room.CleanRoom.test_the_scan_sees_verda_files` | the scan skips the convert folder | caught |
| 6 | `test_clean_room.CleanRoom.test_nothing_imports_the_old_viewer_package` | a planted file imports the old viewer package | caught |
| 7 | `test_clean_room.CleanRoom.test_nothing_names_the_old_viewer_folders` | a planted file names the old viewer folder | caught |
| 8 | `test_clean_room.CleanRoom.test_no_deposited_file_holds_a_user_folder_path` | README.md gives the runs folder by its full path | caught |
| 9 | `test_clips.BesideFiles.test_a_paired_run_is_its_own_timeline_and_a_beside_file` | the paired timeline is written as the run's own file | caught |
| 10 | `test_clips.BesideFiles.test_the_preview_pins_the_run_timeline_as_converted` | a timeline file's summary line gains a field | caught |
| 11 | `test_clips.PlacedClips.test_places_each_clip_and_lists_it_in_the_index` | only the sync file is copied, not its clip | caught |
| 12 | `test_clips.PlacedClips.test_a_clips_caption_goes_with_it_into_the_index` (new) | a clip's caption is left out of the index | caught |
| 13 | `test_clips.PlacedClips.test_a_sync_file_with_no_clip_or_a_bad_field_is_not_placed` | an fps of 0 is let through | caught |
| 14 | `test_convert.CanonicalJson.test_reproduces_every_contract_vector` | canonical JSON gains a space after commas | caught |
| 15 | `test_convert.HashChain.test_every_run_verifies` | one record of a copied practice run is changed | caught |
| 16 | `test_convert.HashChain.test_every_run_verifies` | one record of the copied ground-seat run is changed | caught |
| 17 | `test_convert.HashChain.test_a_changed_record_breaks_the_chain` | the chain check stops comparing prev_hash | caught |
| 18 | `test_convert.Limits.test_dictionary_has_the_sixteen_points` | a copied dictionary's yellow staleness limit is 12 s | caught |
| 19 | `test_convert.Limits.test_limit_states_match_every_observation` | a copied dictionary's load-current yellow high is 1.9 A | caught |
| 20 | `test_convert.TruthMapping.test_truth_matches_every_observation` | battery voltage is mapped to the bus voltage | caught |
| 21 | `test_convert.Timelines.test_each_practice_run_has_a_timeline_file` | the index leaves P4 out | caught |
| 22 | `test_convert.Timelines.test_p3_payload_shed_is_one_allowed_accepted_chain` | outcomes are dropped | caught |
| 23 | `test_convert.Timelines.test_p4_reset_and_the_frame_gap` | frame age turns yellow 20 s late | caught |
| 24 | `test_convert.Timelines.test_p3_process_has_two_malformed_turns_and_no_request` | malformed answers read as no action | caught |
| 25 | `test_convert.Timelines.test_check_ins_reports_and_contact` | check-ins land on the reports lane | caught |
| 26 | `test_convert.Timelines.test_v1_points_from_both_sources` | the payload rate lane is gone | caught |
| 27 | `test_convert.Timelines.test_every_record_is_drawn` | turn records are not marked as drawn | caught |
| 28 | `test_convert.Repeatable.test_the_same_inputs_give_the_same_files_whatever_the_hash_seed` | the truth flags are walked in their set's order | caught |
| 29 | `test_convert.PhaseTwo.test_reads_gzipped_truth` | a .gz record file is never looked for | caught |
| 30 | `test_convert.PhaseTwo.test_says_when_it_skips_a_record_file` | a file it did not read goes unmentioned | caught |
| 31 | `test_convert.PhaseTwo.test_says_when_it_skips_a_record_file` | a folder with no event log is passed over in silence | caught |
| 32 | `test_convert.PhaseTwo.test_each_kind_of_truth_flag_has_a_row_of_its_own` | truth flags are capped at three rows, as before | caught |
| 33 | `test_convert.PhaseTwo.test_the_fifty_each_beside_the_pass_of_its_plan_with_every_check_passing` | a tool use is not counted on its turn | caught |
| 34 | `test_convert.GroundSeat.test_its_bundles_staleness_and_ground_link_are_drawn` | the ground link a bundle recorded is dropped | caught |
| 35 | `test_convert.GroundSeat.test_its_derived_frame_age_agrees_with_the_age_it_recorded` | the derived age is a second short | caught |
| 36 | `test_page.NoNetwork.test_no_network_calls_or_addresses` | verda.js gains a fetch | caught |
| 37 | `test_page.NoNetwork.test_html_loads_only_files_beside_it` | index.html gains an icon link | caught |
| 38 | `test_page.NoNetwork.test_content_security_policy_refuses_connections` | the policy allows connections to the page's origin | caught |
| 39 | `test_page.NoNetwork.test_content_security_policy_refuses_connections` | the policy lets video come from anywhere | caught |
| 40 | `test_page.NoWriting.test_page_writes_nothing` | verda.js saves to localStorage | caught |
| 41 | `test_page.NoWriting.test_recorded_text_is_never_parsed_as_html` | the inspector takes records as HTML | caught |
| 42 | `test_page_in_browser.PageInBrowser.test_asks_only_for_its_own_files_on_disk` | the page asks a local address for an image | caught |
| 43 | `test_page_in_browser.PageInBrowser.test_no_script_or_console_errors` | the page writes an error to the console | caught |
| 44 | `test_page_in_browser.PageInBrowser.test_draws_every_lane_of_each_run` | the contact lane is not drawn | caught |
| 45 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_a_request_and_its_records` | clicks on the timeline do nothing | caught |
| 46 | `test_page_in_browser.PageInBrowser.test_play_moves_the_playhead` | playback stands still | caught |
| 47 | `test_page_in_browser.PageInBrowser.test_a_name_near_the_right_edge_is_written_whole` | a name near the right edge is cut, as before | caught |
| 48 | `test_page_in_browser.PageInBrowser.test_a_name_near_the_right_edge_is_written_whole` | a request's label always goes after its marks | caught |
| 49 | `test_page_in_browser.PageInBrowser.test_a_run_opens_on_its_pass` | a run opens on the whole of it | caught |
| 50 | `test_page_in_browser.PageInBrowser.test_a_known_met_lands_on_the_frame_the_sync_file_gives` | the clip runs a frame ahead of the playhead | caught |
| 51 | `test_page_in_browser.PageInBrowser.test_a_mismatched_hash_shows_nothing` | the pinned hash is not compared | caught |
| 52 | `test_page_in_browser.PageInBrowser.test_the_clip_holds_outside_its_frames_and_follows_play_and_pause` | the clip runs past its last frame | caught |
| 53 | `test_page_in_browser.PageInBrowser.test_the_clip_holds_outside_its_frames_and_follows_play_and_pause` | pausing the timeline leaves the clip playing | caught |
| 54 | `test_page_in_browser.PageInBrowser.test_every_lane_fits_a_1920_by_1080_screen` | the charts never give up height to fit the screen | caught |
| 55 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_directors_command_and_his_rows` | clicks on the Director's command show nothing | caught |
| 56 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_scenarios_command_apart_from_his` | a click names the scenario's command the Director's | caught |
| 57 | `test_page_in_browser.PageInBrowser.test_hover_and_click_show_the_scenarios_command_apart_from_his` | the lane's note is cut to the label column | caught |
| 58 | `test_page_in_browser.PageInBrowser.test_the_ground_seat_age_lane_names_what_its_bundles_recorded` | the strip above the age chart is never drawn | caught |
| 59 | `test_page_in_browser.PageInBrowser.test_a_turn_name_near_the_right_edge_is_written_whole` (new) | a turn's name goes after its mark even past the edge | caught |
| 60 | `test_page_in_browser.PageInBrowser.test_the_layout_holds_still_as_the_playhead_moves` (new) | the timeline and side column take the row the hidden banner leaves | caught |
| 61 | `test_page_in_browser.PageInBrowser.test_a_name_cut_short_by_the_next_mark_is_written_whole_before_its_own` (new) | a name is written before its mark only at the right edge | caught |
| 62 | `test_page_in_browser.PageInBrowser.test_a_run_with_no_clip_shows_its_event_log_and_no_clip_notice` (new) | the pane stays, saying there is no clip | caught |
| 63 | `test_page_in_browser.PageInBrowser.test_a_report_opens_beside_the_records_it_names_by_id` (new) | every check-in before the report is linked to it | caught |
| 64 | `test_page_in_browser.PageInBrowser.test_a_report_opens_beside_the_records_it_names_by_id` (new) | the view calls what the report links verified | caught |
| 65 | `test_page_in_browser.PageInBrowser.test_the_capture_seek_puts_the_footage_clip_on_the_frame_of_each_met` (new) | the capture's seek rounds the MET to a whole second | caught |
| 66 | `test_page_in_browser.PageInBrowser.test_the_capture_seek_puts_the_footage_clip_on_the_frame_of_each_met` (new) | the clip frame is rounded down with no allowance for float error | caught |
| 67 | `test_passes.PassFiles.test_reads_all_five_passes` | each pass takes the last plan of its scenario, whatever its window | caught |
| 68 | `test_passes.PassFiles.test_p1_reads_both_blocks_of_repeated_columns` | arguments are read from the header's first block only | caught |
| 69 | `test_passes.PassFiles.test_what_his_telemetry_showed_next` | his counters are watched for 0 s after a command | caught |
| 70 | `test_passes.KnownCommandTimes.test_one_known_command_time_on_each_side` | the Director's command takes the MET of the frame after it | caught |
| 71 | `test_passes.KnownCommandTimes.test_one_known_command_time_on_each_side` | ODIN's dispatch is placed a second late | caught |
| 72 | `test_passes.LineUp.test_each_pass_lines_up_with_its_runs` | no run pairs with a pass | caught |
| 73 | `test_passes.LineUp.test_a_run_pairs_with_the_pass_flown_under_its_plan` | a run's plan is never looked at | caught |
| 74 | `test_passes.LineUp.test_his_frame_age_shows_the_gap_in_his_p4_frames` | his frame age forgets the gap in his frames | caught |
| 75 | `test_passes.ScenarioCommands.test_reads_the_seven_and_checks_each_against_its_plan` | a copied file says P4's reset falls before contact and is kept | caught |
| 76 | `test_passes.ScenarioCommands.test_on_his_side_as_the_scenarios_and_never_his` | the scenario's commands are filed among his | caught |
| 77 | `test_passes.ScenarioCommands.test_on_his_side_as_the_scenarios_and_never_his` | the lane no longer says ODIN's runs drop the in-contact ones | caught |
| 78 | `test_passes.ScenarioCommands.test_what_his_telemetry_showed_after_the_scenarios_commands` | the frame stamped with the command's MET counts as before it | caught |
| 79 | `test_passes.ScenarioCommands.test_a_span_his_command_shares_with_the_scenarios_is_credited_to_neither` | a shared span is never looked for | caught |
| 80 | `test_passes.ScenarioCommands.test_odins_runs_dropped_exactly_the_in_contact_ones` | a copied file puts P4's reset at MET 1321 | caught |
| 81 | `test_record_types.RecordTypes.test_contract_and_schema_agree` | a copied contract drops TOOL_USE from its list | caught |
| 82 | `test_record_types.RecordTypes.test_every_contract_type_is_shown_or_listed` | TOOL_USE is missing from VERDA's table | caught |
| 83 | `test_site.SiteBuild.test_the_site_holds_exactly_its_runs_and_the_page_as_it_is` (new) | scenario D's runs are left off the site | caught |
| 84 | `test_site.SiteBuild.test_each_phase_2_run_is_beside_its_pass_and_each_phase_3_run_alone` (new) | phase 2's runs go on the site alone | caught |
| 85 | `test_site.SiteBuild.test_spark_r2_carries_the_site_clip_and_no_other` (new) | the site clip is left off the site | caught |
| 86 | `test_site.SiteBuild.test_spark_r2_is_the_file_its_clips_were_rendered_from` (new) | the site's runs are converted without their truth | caught |
| 87 | `test_site.SiteRefusals.test_a_run_missing_from_the_records_stops_the_build` (new) | missing runs are not looked for | caught |
| 88 | `test_site.SiteRefusals.test_a_clip_the_site_does_not_carry_is_refused` (new) | any clip of a site run's is let through | caught |
| 89 | `test_site.SiteRefusals.test_a_clip_pinned_to_another_timeline_stops_the_build` (new) | a clip's pinned hash is not compared | caught |
| 90 | `test_site.SiteRefusals.test_spark_r2_in_other_bytes_stops_the_build` (new) | SPARK-R2's timeline is not compared with its pin | caught |
| 91 | `test_site.SiteRefusals.test_a_run_whose_check_fails_or_that_left_a_file_unread_stops_the_build` (new) | a run whose check failed goes on the site | caught |
| 92 | `test_site.SiteRefusals.test_the_build_never_writes_into_a_folder_that_exists` (new) | the build writes into a folder that exists | caught |
| 93 | `test_site.SiteInBrowser.test_the_pane_carries_its_caption_and_the_column_holds_it` (new) | the pane's line drops "simulated" | caught |
| 94 | `test_site.SiteInBrowser.test_the_pane_carries_its_caption_and_the_column_holds_it` (new) | the Record panel keeps its old minimum beside a clip | caught |
| 95 | `test_site.SiteInBrowser.test_the_pane_carries_its_caption_and_the_column_holds_it` (new) | the full caption opens in the Record panel's old place | caught |
| 96 | `test_site.SiteInBrowser.test_served_over_http_the_page_works_and_the_clip_plays` (new) | the page's scripts may come only from disk | caught |
| 97 | `test_site.SiteInBrowser.test_from_disk_the_page_works_and_the_clip_plays` (new) | the page asks for its timelines from the root of a site | caught |
| 98 | `test_watch_only.WatchOnly.test_converter_writes_only_its_files_and_leaves_the_run_untouched` | the converter leaves a file in the run folder | caught |
| 99 | `test_watch_only.WatchOnly.test_with_passes_it_writes_only_timelines_and_leaves_passes_and_plans_untouched` | the converter leaves a file in a pass folder | caught |
| 100 | `test_watch_only.WatchOnly.test_output_names_cannot_leave_the_folder` | output names may hold a backslash | caught |

Changed since VERDA-05: the right-edge name test's plant switches the rule off on its new line, the one rule now also covering a name cut short by the next mark; the capture seek's plant ("the capture's seek rounds the MET") is planted in the capture tool, where the seek now lives. Two older tests were brought to the inputs of 2 November 2026: the scripted-commands test checks the five phase-2 plans by name (phase 3's two have no pass of the Director's), and the clip-placement test expects the three clips now in the inputs.

## Rehearsal

A draft of this deposit was unpacked into an empty `viewer` folder with no `inputs/` beside it, as in the repository, and run there on 3 November 2026 with only `VERDA_INPUTS` and `PYTHONDONTWRITEBYTECODE` set. The draft had the same files as this deposit, except that this section was not yet written. Result: **Ran 88 tests, OK** (in about four minutes); then **100 red cases, 100 caught; then the whole suite again, Ran 88 tests, OK**, in 58 minutes. Afterwards every deposited file was unchanged (checked against its SHA-256 before the run), no file had been added, and the only thing left was an empty `.scratch` folder.

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
| `VERDA_CLIPS` | leave unset | Defaults to `VERDA_INPUTS\clips` |
| `VERDA_PAGE` | leave unset | Defaults to the deposited `page` folder |
| `VERDA_BROWSER` | leave unset | The browser test finds Chrome or Edge in their usual places |
| `PYTHONDONTWRITEBYTECODE` | `1` | Keeps `__pycache__` folders out of the viewer folder; the repeatability test passes it on to the converter runs it starts |

What to expect: the unittest run ends `Ran 88 tests` and `OK`, in about six minutes; `show_red.py` lists 100 red cases, each `caught`, ends with `RESULT: every red case caught, and the suite passes`, and exits 0, in about 57 minutes. It needs Chrome or Edge installed, able to play MP4 clips, and nothing else: the tests build the site in a temporary folder and serve it from 127.0.0.1 themselves, and need no ffmpeg. The clean-room test reads this DEPOSIT.md and MANIFEST.sha256 too, so they must sit in the viewer folder as deposited. The tests need the inputs of 2 November 2026 (2,444 files): with fewer, the tests that read phase 3's runs or SPARK-R2's clips stop on an error naming the missing input, and the run does not pass.

What the run touches: `show_red.py` plants each change in a file in the viewer folder and restores it byte for byte before the next; it keeps each original in `.scratch\red-backup` inside the viewer folder while planted and deletes it after, which leaves an empty `.scratch` folder there (git does not track empty folders). The tests write their timeline files, sites and placed clips to temporary folders only. If a run is stopped partway, the next run restores any planted file from that backup first. After the run, `git status` should show the tree unchanged.

## The converter, with VERDA's inputs

In the VERDA folder, where `inputs\` sits beside VERDA's files:

```
python convert/verda_convert.py --all inputs/runs --passes inputs/pass-records --plans inputs/plans --scripted inputs/scripted-commands/phase2_scripted_commands.json --clips inputs/clips
```

It writes, into `page/timelines/`, one timeline file for each run and each pass no run pairs with, a beside file for each run paired with a pass, and a copy of each clip and its sync file in `clips/`, and lists them all in `page/timelines/index.js`; it ends with a line for each clip saying whether its timeline file is the one it pins. With the inputs of 2 November 2026, two clips pin PH2-PASS3-SPARK-R2's timeline, and the page plays neither until it is given one: that choice is the site build's (the site clip) and the capture tool's (the clip each shot names). Then open `page/index.html` from disk. From the repository's `viewer` folder, the same command works with each `inputs/` read as `<VERDA folder>\inputs\`. It writes `page/timelines/` inside the `viewer` folder, which is generated and not part of the deposit: leave it untracked, or delete it after viewing.

## Suggested commit message

```
viewer: VERDA-06, the demo video's VERDA shots and the replay site

site/build_site.py builds VERDA's replay site from the committed records
for GitHub Pages: phase 2's fifty scored runs, each beside the
Director's pass of its plan, and phase 3's A and D, each alone, with
PH2-PASS3-SPARK-R2's site clip and its full caption. It fails, leaving
no site, on a missing run, a failed check, a clip it does not carry or
pinned to another timeline, or SPARK-R2's timeline in other bytes than
the file its clips were rendered from. The page goes on the site as it
is: watch-only, reading only its own files, its policy kept.

capture/verda_capture.py filmed the video's three VERDA shots from the
page a frame at a time, each frame checked against the clip's sync file
and the page's layout.

The page now opens one of ODIN's reports beside the records it links
by ID, steps the animation pane aside for the event log when a run has
no clip, says what its replays are, captions the animation, writes
names whole near the next mark and in the turns lane, and holds its
grid rows when the banner is hidden.

88 tests, each shown failing on a planted red case (100 red cases,
tests/show_red.py).
```
