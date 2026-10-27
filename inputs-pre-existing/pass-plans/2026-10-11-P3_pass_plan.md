# Pass plan — 2026-10-11-P3

| Field | Value |
|---|---|
| Pass | `2026-10-11-P3` |
| Scenario | `P3_stuck_load` |
| Contact length | 430 s, the length of computed contact 9 |
| Acquisition (AOS) | MET 800, chosen for this pass |
| Loss of signal (LOS) | MET 1230, computed: acquisition plus contact length |
| Dictionary version | 0.5 |
| Generated (UTC) | 2026-10-11T13:42:22+00:00 |

## What this plan is

This is the mission as it would run if nothing went wrong: the same scenario, with
the same scripted commands, the same illumination and the same starting state, and
with its faults removed. It was computed before the pass and has not seen the pass.

During the contact, compare live telemetry against it. Where the two agree, the
spacecraft is doing what was planned. Where they diverge, **the divergence is the
fault's signature** — which point, by how much, starting when. Write the divergence
down; it is the observation.

A telemetry halt shows up differently. It costs no power, so the values that do
arrive can agree perfectly with this plan. Its signature is frames this plan expects
that never arrive — count them.

## Predicted values at the procedure's checkpoints

| Checkpoint | Step | Timing | MET | EPS_BATT_SOC % | EPS_BATT_I A | EPS_LOAD_I A | ADM_ECLIPSE | EPS_MODE |
|---|---|---|---:|---:|---:|---:|---|---|
| Acquisition | PROC-001-S04 | AOS | 800 | 65.813 | +1.3053 | 1.400 | SUNLIT | NOMINAL |
| Acquisition + 2 min | PROC-001-S06 | AOS + 2 min | 920 | 66.646 | +1.3035 | 1.400 | SUNLIT | NOMINAL |
| Loss of signal - 2 min | PROC-001-S15 | LOS - 2 min | 1110 | 67.965 | +1.3005 | 1.400 | SUNLIT | NOMINAL |
| Loss of signal | PROC-001-S16 | LOS | 1229 (last frame) | 68.792 | +1.2986 | 1.400 | SUNLIT | NOMINAL |

## Expected frames

**430 frames**, MET 800 through 1229, one per second.

Count what arrives. Frames that should have arrived and did not are an observation
in their own right, even when every value that did arrive agrees with this plan.

## Predicted illumination transitions

None inside this contact: SUNLIT throughout.

## Predicted profile, every 30 s

| MET | EPS_BATT_SOC % | EPS_BATT_I A | EPS_LOAD_I A | ADM_ECLIPSE | EPS_MODE |
|---:|---:|---:|---:|---|---|
| 800 | 65.813 | +1.3053 | 1.400 | SUNLIT | NOMINAL |
| 830 | 66.021 | +1.3049 | 1.400 | SUNLIT | NOMINAL |
| 860 | 66.229 | +1.3044 | 1.400 | SUNLIT | NOMINAL |
| 890 | 66.438 | +1.3039 | 1.400 | SUNLIT | NOMINAL |
| 920 | 66.646 | +1.3035 | 1.400 | SUNLIT | NOMINAL |
| 950 | 66.854 | +1.3030 | 1.400 | SUNLIT | NOMINAL |
| 980 | 67.063 | +1.3025 | 1.400 | SUNLIT | NOMINAL |
| 1010 | 67.271 | +1.3020 | 1.400 | SUNLIT | NOMINAL |
| 1040 | 67.479 | +1.3016 | 1.400 | SUNLIT | NOMINAL |
| 1070 | 67.688 | +1.3011 | 1.400 | SUNLIT | NOMINAL |
| 1100 | 67.896 | +1.3006 | 1.400 | SUNLIT | NOMINAL |
| 1130 | 68.104 | +1.3002 | 1.400 | SUNLIT | NOMINAL |
| 1160 | 68.313 | +1.2997 | 1.400 | SUNLIT | NOMINAL |
| 1190 | 68.521 | +1.2992 | 1.400 | SUNLIT | NOMINAL |
| 1220 | 68.729 | +1.2987 | 1.400 | SUNLIT | NOMINAL |
| 1229 (last frame) | 68.792 | +1.2986 | 1.400 | SUNLIT | NOMINAL |
