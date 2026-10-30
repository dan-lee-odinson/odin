# M17: one run, two models, picked by seat

The Director's ruling of 30 October 2026, "Loop picks model by seat (Recommended)". A run can move between the
ground seat, which works COSMOS, and the onboard seat, beside the simulator (CONTRACT.md §10.1). ODIN starts with
both models, and each turn's seat picks one. RUN_START names both, and S8 checks each model call against its own
model's frozen settings. Nothing here is from phase 3.

The Director approved this the same day ("Confirm all three (Recommended)"): Muse Code builds from it, with the
schema change in `contract/schemas/run_start.schema.json`.

## The contract

- **How a turn tells ODIN its seat:** the turn bundle's `seat`, `GROUND` or `ONBOARD`, as today. The bundle's schema
  is one of the six frozen ones and does not change. ODIN answers a `GROUND` turn with the run's model, and an
  `ONBOARD` turn with the run's onboard model when it has one, otherwise with the run's model.
- **What RUN_START carries:** everything it carries today for the run's model, plus `onboard`: null when the run's
  model flies every seat; otherwise the onboard model's `model_config`, `provider`, `model_id`, `reasoning_effort`,
  `endpoint` and `answer_method`, each found as the run's own are, from its frozen block (U56) and its adapter (U57).
  The harness writes RUN_START; ODIN never does.
- **Which schemas change:** `contract/schemas/run_start.schema.json` only, by one property, `onboard`. It is
  not one of the six frozen schemas. The bundle, MODEL_CALL (whose `config` already names each call's own model) and
  every other schema stay as they are.
- **The freeze:** each model keeps its own entry in `config/frozen.json`, and a run checks both before it starts.
- **S8:** each MODEL_CALL's `config` must be the run's model or its onboard model, and its settings that model's
  frozen block's. A call from any other model is a settings mismatch, set-aside cause 8.

## What Muse Code builds

1. **`odin/run_odin.py`:** an optional onboard model, `python -m odin.run_odin <model> --onboard <glimmer_local |
   glimmer_modal | stand_in>`. Without `--onboard`, nothing changes. With it, ODIN refuses to start unless both
   models' keys are set, and builds both adapters from their frozen blocks, as it builds one today.
2. **The loop (`odin/loop/`):** each turn's adapter is the one its bundle's `seat` picks: `ONBOARD` picks the onboard
   adapter when there is one; anything else picks the run's adapter. Every MODEL_CALL names the configuration of
   the adapter that made it, as today. The frozen instructions, the prompt and the answer judging are the same for
   both; each adapter keeps its own answer format (Glimmer's format G on ACT turns, M16).
3. **The spend meter:** each call reserves and settles against its own model's amount, as each adapter does today. A
   stop on either stops ODIN, as now (M8).
4. **Tests and planted red cases**, through a runner as M16's:
   - an `ONBOARD` turn answered by the run's model when an onboard model is given;
   - a `GROUND` turn answered by the onboard model;
   - a MODEL_CALL naming the other model's configuration;
   - ODIN starting without the onboard model's key;
   - after a change of seat between turns, the next turn going to the old seat's adapter.

The harness's side is Claude Code's: RUN_START's `onboard`, the freeze check of both models, starting ODIN with
`--onboard`, S8's per-call check, and the seat switching itself.

## Settled in drafting, confirmed by the Director

1. **`onboard` is not in RUN_START's required list**, though every other field is (U15). The phase-1 and phase-2 runs
   were recorded without it, and S8 checks every committed record against the schema (set-aside cause 5). Every run
   from M17 on writes it, null or not, and S8 requires it of those.
2. **The onboard model is one of Glimmer's configurations, or the stand-in in development.** Spark and spark_open fly
   the ground seat only.
3. **Its answer method is `STRUCTURED_OUTPUT` or `SCRIPTED`**, the methods Glimmer and the stand-in use.
