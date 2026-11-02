# M5's timing prompts (kept by Claude Code)

The Director's word of 30 October 2026: "Claude Code keeps them". These are the onboard-shaped prompts Muse Glimmer is
timed on, for M5: on Modal by Claude Code, and on the Director's laptop by `laptop_timing.py`, after phase 2, with
Docker stopped. Muse Code never gets them: their feed reports follow the sealed phase-3 design's feed details, which
are held out.

- `prompts/turnNN-metMMMM.prompt.txt`: the nine prompts, each the exact bytes ODIN's own prompt builder makes, with
  its frozen instructions, from one ACT turn of the phase-2 development run `dev-ph2-p3-spark-03` (P3, the stuck load),
  made the onboard seat's: its observation the onboard seat's, with no ground link, and the core feeds' reports
  (`wrapper/feeds.py`, station_receiver and beacon) since the turn before, each with its FEED_REPORT trigger.
- `prompts/turnNN-metMMMM.bundle.json`: the bundle each prompt was built from, valid against the contract's
  turn_bundle schema.
- `prompts/SUMMARY.json`: each prompt's MET, feed reports, size and SHA-256.
- `make_prompts.py`: what made them (it was run from Claude Code's scratchpad).
- `MANIFEST.sha256`: the SHA-256 of every file under `prompts/`.

Nothing here comes from a held-out scenario: the run, its plan and its place in the campaign week are phase 2's.

## Timings on Modal

- `timing-h100-onboard.json`: 29 October 2026, the H100, Glimmer's own reasoning setting (`high`).
- `timing-h100-medium-low.json`, `timing-h200-default.json`: 30 October 2026, the Director's two fixes for 60 s,
  by `time_settings.py`: the H100 at reasoning strength `medium` and `low`, and the H200 at `high`. The setting is
  Glimmer's chat-template variable `reasoning_strength`, passed per request as llama.cpp's `chat_template_kwargs`
  and seen in the server's `/apply-template` output before each setting's nine prompts; max_tokens stays 8192.
- `table.py`: the per-prompt table of all three.
- `timing-h100-low-G.json`: 30 October 2026, after phase 2, the timing of record by the Director's ruling "Low,
  tie type to command": the H100 at reasoning strength `low` with format G (`../../contract/m16/format-G-HUGINN.json`), by
  `time_low_g.py`. Nine of nine accepted; mean 29.0 s, max 34.6 s, none over 60 s. It also records that the request
  field `reasoning_effort`, as the glimmer_modal adapter (MC-M5-02) sends the level, reaches Glimmer's template
  as `chat_template_kwargs` does.
- `laptop_timing.py` sends the same: `reasoning_strength` low and format G, and checks the setting first. Since the
  Director's word of 30 October 2026, "One prompt, Claude Code runs it", `--prompt` times one prompt only, and
  `--stop-at` streams each decision and stops waiting at that second, recording a decision still running as a clear
  miss, with when its first token came (the end of prefill).

## Timing on the laptop

- `laptop-timing-20261030T120450Z.json`, with the server's own log `laptop-server-20261030T120450Z.log`: 30 October
  2026, by the Director's word "One prompt, Claude Code runs it". Docker Desktop was quit, and nothing else heavy ran.
  - **The setup:** llama.cpp b12002, CUDA 13.4 build; both zips matched GitHub's SHA-256 digests. It served the
    laptop's GGUF with `--jinja -fa on -c 65536 -np 1 -ub 2048`, GPU layers left to llama.cpp's fit.
  - **The hardware:** an RTX 5050 Laptop GPU with 8 GB, which held 7.3 GB of the model. The rest of Glimmer, a dense
    28B model of 16.8 GB with 52 layers, ran from system RAM, on an i5-13450HX with 64 GB.
  - **The run:** `reasoning_strength` low (seen in the system block) and format G, on the shortest prompt,
    `turn01-met800` (43,154 tokens), stopped at 180 s. The warm-up took 72.1 s.
  - **The result: a clear miss.** Prefill alone took 121.0 s (357 tokens/s), and the first token came at 124.7 s. At
    180 s it was still thinking: 131 tokens, at 2.35 tokens/s. The H100 wrote 413 tokens for this prompt, so the whole
    decision would take about 300 s here, five times the onboard limit. Every longer prompt takes longer still.
  - **What follows**, by the Director's ruling of 29 October 2026 (../../phase3/RULINGS.md item 5): Glimmer flies the onboard seat
    on Modal.

- `glimmer-model-block-DRAFT.md`: Glimmer's frozen model block, approved on 30 October 2026 with a 60 s timeout; it
  goes into `config/models.yaml` once Muse Code's M16 is committed.
