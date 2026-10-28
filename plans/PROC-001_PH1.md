# PROC-001 — Shakedown on COSMOS's demo spacecraft (phase 1)

Version 1.0. Written from the Director's rulings of 27 October 2026 and the objectives of plan TYR0-PH1-SHAKEDOWN-v1.

The spacecraft is INST, COSMOS's demo spacecraft. Its commands and telemetry are in the dictionary attached to the plan. INST is in contact for the whole run.

| Step | Action |
|---|---|
| S01 | Read INST HEALTH_STATUS. Note the collect count (COLLECTS) and the command accept count (CMD_ACPT_CNT). |
| S02 | Send INST COLLECT with TYPE NORMAL, once. From HEALTH_STATUS, confirm that the command was accepted and the collect count rose. |
| S03 | Read INST HEALTH_STATUS with each item's value, units and limit state. Choose two items and track them for at least 60 seconds. |
| S04 | Find an item that is out of limits. Name it, give its LIMITS definition, and name the limit it crossed. |
| S05 | Answer each check-in from telemetry and the log, giving each value with its time. |
| S06 | When the Director asks for console notes, write them for your own use on later passes. |
