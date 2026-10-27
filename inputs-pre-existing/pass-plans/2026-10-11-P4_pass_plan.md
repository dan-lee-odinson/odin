# Pass plan — 2026-10-11-P4

| Field | Value |
|---|---|
| Pass | `2026-10-11-P4` |
| Scenario | `P4_hk_generation_halt` |
| Contact length | 430 s, the length of computed contact 2 |
| Acquisition (AOS) | MET 1100, chosen for this pass |
| Loss of signal (LOS) | MET 1530, computed: acquisition plus contact length |
| Dictionary version | 0.5 |
| Generated (UTC) | 2026-10-11T19:09:27+00:00 |

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
| Acquisition | PROC-001-S04 | AOS | 1100 | 72.896 | +1.2894 | 1.400 | SUNLIT | NOMINAL |
| Acquisition + 2 min | PROC-001-S06 | AOS + 2 min | 1220 | 73.729 | +1.2876 | 1.400 | SUNLIT | NOMINAL |
| Loss of signal - 2 min | PROC-001-S15 | LOS - 2 min | 1410 | 75.049 | +1.2847 | 1.400 | SUNLIT | NOMINAL |
| Loss of signal | PROC-001-S16 | LOS | 1529 (last frame) | 75.875 | +1.2829 | 1.400 | SUNLIT | NOMINAL |

## Expected frames

**430 frames**, MET 1100 through 1529, one per second.

Count what arrives. Frames that should have arrived and did not are an observation
in their own right, even when every value that did arrive agrees with this plan.

## Predicted illumination transitions

None inside this contact: SUNLIT throughout.

## Predicted profile, every 30 s

| MET | EPS_BATT_SOC % | EPS_BATT_I A | EPS_LOAD_I A | ADM_ECLIPSE | EPS_MODE |
|---:|---:|---:|---:|---|---|
| 1100 | 72.896 | +1.2894 | 1.400 | SUNLIT | NOMINAL |
| 1130 | 73.104 | +1.2890 | 1.400 | SUNLIT | NOMINAL |
| 1160 | 73.313 | +1.2885 | 1.400 | SUNLIT | NOMINAL |
| 1190 | 73.521 | +1.2881 | 1.400 | SUNLIT | NOMINAL |
| 1220 | 73.729 | +1.2876 | 1.400 | SUNLIT | NOMINAL |
| 1250 | 73.938 | +1.2871 | 1.400 | SUNLIT | NOMINAL |
| 1280 | 74.146 | +1.2867 | 1.400 | SUNLIT | NOMINAL |
| 1310 | 74.354 | +1.2862 | 1.400 | SUNLIT | NOMINAL |
| 1340 | 74.563 | +1.2858 | 1.400 | SUNLIT | NOMINAL |
| 1370 | 74.771 | +1.2853 | 1.400 | SUNLIT | NOMINAL |
| 1400 | 74.979 | +1.2848 | 1.400 | SUNLIT | NOMINAL |
| 1430 | 75.188 | +1.2844 | 1.400 | SUNLIT | NOMINAL |
| 1460 | 75.396 | +1.2839 | 1.400 | SUNLIT | NOMINAL |
| 1490 | 75.604 | +1.2835 | 1.400 | SUNLIT | NOMINAL |
| 1520 | 75.813 | +1.2830 | 1.400 | SUNLIT | NOMINAL |
| 1529 (last frame) | 75.875 | +1.2829 | 1.400 | SUNLIT | NOMINAL |
