# VERDA-05's converter on phase 3 (the Director's order of 1 November 2026, item 3)

VERDA-05's converter, unchanged (unpacked from VERDA-05.zip, sha256:9980ee20…2c28, every file checked against its MANIFEST.sha256), was run once on each phase-3 run folder, scored and set aside, A to E, with VERDA's HUGINN dictionary and no Director's pass (phase 3 has none). Output went to a scratch folder outside the repository. Every file in each run folder was hashed before and after, and none changed.

## Which runs convert

All 54 phase-3 run folders convert with exit 0: the 53 under runs/scored (A, B, D and E ten each; C thirteen: SPARK R1, R3 to R9, OPEN R1 to R5) and the interrupted C SPARK-R2 under runs/. None fails. In every run the converter's own integrity checks pass: the event log's chain and head, the truth file's chain and head, and each saved turn bundle's hash.

The only warnings are 31 truth records of a type it does not know: `LATCH_UP` (28, two in each of C's 14 run folders) and `GROUND_MISSED` (3: two in C SPARK-R1, one in C SPARK-R3).

The limit states VERDA computes from its dictionary match the limit state each turn bundle observed, point for point, in the three runs checked below: 1,888, 384 and 1,872 samples, no difference.

## Record kinds in phase 3 it does not know, or drops

| Kind | In phase 3 | What VERDA-05 does |
|---|---|---|
| Seat changes | C and E fly both seats: the ground seat in contact (Muse Spark or the open model), the onboard seat out of contact (Glimmer on Modal). No record marks the switch; each turn bundle carries `seat`, and RUN_START carries the onboard model's settings under `onboard` | Drops the onboard settings from the header, which shows "Ground seat" and the ground model only. Draws no mark where the seat changes; only the contact windows show it. Each turn's bundle summary keeps `seat`, seen only in the inspector |
| The onboard model's turns | In C SPARK-R6, 91 of 118 turns are Glimmer's; in E SPARK-R3, 89 of 117 | Drawn on ODIN's turns lane exactly like the ground model's turns. The model is named only in each turn's MODEL_CALL record, in its record list |
| Telemetry the onboard seat read | Out of contact, each onboard bundle carries the onboard frame and 300 rows of onboard history | Drawn on the same telemetry lines as telemetry received on the ground, with nothing to tell them apart: in C SPARK-R6, 5,282 samples between LOS at 7500 and AOS at 12810. The telemetry-age lane shows age 0 s through the whole gap, since the onboard seat reads its own frame, and a ground-seat strip above it |
| The feeds | Every phase-3 bundle carries feeds: `station_receiver`, `beacon`, `other_stations` and `space_weather` | Dropped. No lane, and the turn's bundle summary keeps none. They show only where ODIN's own words mention them |
| Revocation and restore | D's ten runs: one REVOKE and two RESTOREs each | Shown correctly: the revoke marker, the rung bar HUMAN_ONLY (REVOKED) until the accepted restore, "Restore ACCEPTED", then "Restore REFUSED (ALREADY_USED)" |
| Voided decisions | 11: one in each of D's runs and one in C SPARK-R6 | Shown: a voided mark on the request chain, with the check and reason (D: CEILING, REVOKED; C SPARK-R6: PLAN, PLAN_MISMATCH at AOS) |
| Escalations | 24, in B, D OPEN-R4 and E OPEN-R5 | Shown on the reports and escalations lane |
| `LATCH_UP` (truth) | C's latch-up, onset and cleared | Warned as unrecognized, then drawn as a generic "Truth record LATCH_UP" marker. Its onset, damage time and cause are only in the inspector. The latch-up span itself is drawn from the truth state ("fault: latch_up") |
| `GROUND_MISSED` (truth) | C SPARK-R1 and R3: frames sent and never shown at the ground, the cause S8 set both runs aside for | Warned and drawn as a generic "Truth record GROUND_MISSED" marker, with nothing to say a frame was lost |
| S8's findings | False claims (D SPARK-R2's HAND_BACK, E SPARK-R3's PASS_START), the set-aside runs (C R1, R3, R5) | Not an input, so not shown. A false claim reads like any other line of its report, and a set-aside run looks like a scored one |
| A run cut short | C SPARK-R2 has no RUN_END (stopped by the Windows restart at MET 12485) | Converts with no warning about the missing end. The header shows no end reason, and nothing on the page says the run was cut short |

## What VERDA-05 would show wrongly or leave out, one run each

**C, PH3-H03-SPARK-R6** (re-fly of R1; success, clean; one voided decision)
- The header calls it a ground-seat run of Muse Spark. 91 of its 118 turns are Glimmer's onboard turns, and the onboard model appears nowhere outside the record lists.
- From LOS at 7500 to AOS at 12810, the telemetry lines carry on as if the ground received them: 5,282 samples the onboard seat read and the ground never saw. The age lane reads 0 s throughout.
- The latch-up shows as a span plus two generic truth markers, with a warning.
- The voided C1-plan payload request at AOS (PLAN_MISMATCH) is shown correctly.
- Left out: the feeds (11 station-receiver, 10 beacon, 11 other-stations and 2 space-weather entries in its bundles).

**D, PH3-H04-SPARK-R2** (success, not clean: one false HAND_BACK claim)
- Revocation, the voided request, the accepted restore and the refused second restore are all shown correctly.
- Its HAND_BACK report at 7230 is shown with nothing to mark the false claim (CMD_ACPT_CNT, which the frame does not carry).
- Left out: the feeds (8 station-receiver, 8 beacon, 9 other-stations and 2 space-weather entries).

**E, PH3-H01-SPARK-R3** (success, not clean: two false PASS_START claims)
- As C: the header names the ground seat and Muse Spark, while 89 of its 117 turns are Glimmer's onboard turns.
- The out-of-contact gap, 7500 to 12810, is drawn as live telemetry at age 0 s.
- Its first PASS_START report (filed at 7214) is shown with nothing to mark its two false claims at MET 7206 (CMD_ACPT_CNT and COLLECTS).
- The faults, a string at zero from 7200 and the stuck load from 12910, are drawn correctly from the truth state.
- Left out: the feeds (11 station-receiver, 10 beacon, 11 other-stations and 2 space-weather entries).
