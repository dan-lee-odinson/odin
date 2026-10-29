# Standing rules for Muse Code: ODIN's side of the build

These rules load at the start of every Muse Code session in this repository. Muse Code cannot change them; only the Director can.

## 0. What governs

- **`CONTRACT.md`** in the repository root is the build contract, version 0.6, approved by the Director on 26 October 2026 and amended by his ruling of 29 October 2026 (§11.1, how `spark_open`'s answer is taken). Its SHA-256 is `2c3255b275be61da746f3eb3386bc84071153efb29d4ed3444d23c323398198c`. Check it before starting: if `CONTRACT.md` does not hash to that value, stop and report.
- **`contract/schemas/`** (JSON Schema, Draft 7), which Claude Code copies into your workspace, is the single source for every message and record in contract §4–§9 and §16. Validate against it, and never keep a second copy of a field list in your code.
- Where these rules and the contract disagree, the contract governs. Where either is silent on a choice, stop and report (§9). Never settle a design choice yourself.
- **The Director** is Dan Lee-Odinson. He holds design authority and makes every ruling. Claude Code builds the other half of the system. An advisor session drafts documents for the Director outside this repository.

## 1. Your scope

You build ODIN's side: everything under `odin/`. Outside it you write only the public key file `keys/odin.pub`, the saved turn inputs in `runs/<run_id>/inputs/` (contract §4), the docs cache in `cache/cosmos-docs-7.2.1/` (§4.4), and your deposits in `to-claude-code/` (§6). Nothing else.

**Your workspace** is `%USERPROFILE%\Documents\ad-astra-simul\odin`. It is a working copy, not a git repository. Claude Code keeps the shared reference files in it current and never touches `odin/`, `to-claude-code/`, `cache/` or `runs/`. From HUGINN it holds only `deps/huginn/defs/tlm_cmd.yaml`.

Claude Code sets up your workspace before you start: `CONTRACT.md`, `config/ports.yaml`, `config/prices.yaml`, `keys/allowed_signers`, `deps/huginn/defs/tlm_cmd.yaml` and the folder layout. If any of these is missing when you begin, stop and report.

| Piece | Folder | Contract |
|---|---|---|
| Turn loop: fetch a turn bundle, build the prompt, save and hash the inputs, call the model, check the answer, sign and send the request, file reports | `odin/loop/` | §6, §7, §8 |
| Model adapters: `spark`, `spark_open`, `glimmer_local`, `stand_in` | `odin/adapters/` | §11.1 |
| Spend meter | `odin/spend/` | §11.2, §11.3 |
| COSMOS docs study step | `odin/study/` | §1 phase list, §10.4 |
| Voice check-in path | `odin/voice/` | §13, and §4 of this file |
| Glimmer onboard test | `odin/glimmer_test/` | §11.1 |
| ODIN's instructions (the system prompt) and its template | `odin/instructions/` | §5 of this file |
| Your tests, red cases beside passing ones | `odin/tests/` | |
| A fake harness and fake BALDUR-0 for your own testing | `odin/devtools/` | §8 |

Never edit `gateway/`, `connector/`, `wrapper/`, `log/`, `harness/`, `eval/`, `plans/`, `acts/`, `viewer/`, `config/`, `contract/`, `CONTRACT.md`, `README.md` or `.agents/`. Claude Code owns them. If you need something from one of them, stop and report.

## 2. Hard rules

1. **All implementation is new**, written from 26 October 2026 on. Copy nothing from anywhere.
2. **HUGINN** is pinned at commit `b4dbe61`. Your workspace holds only its dictionary, `deps/huginn/defs/tlm_cmd.yaml`, which you read for the commands and telemetry points. Ask the Director before needing anything else from HUGINN. **Never open, import or copy anything in `deps/huginn/ve/`, `deps/huginn/viewer/` or `deps/huginn/replay/`, or HUGINN's replay schema.** A repository test fails if any file imports `ve`.
3. **Held out means held out.** The phase-3 scenarios are not in this repository and never will be while you are building. Never ask for them, guess at them, or write instructions aimed at particular faults. Build ODIN to fly by its plan, its procedures and its telemetry.
4. **Never open `inputs-pre-existing/comparison-only/`.** It holds the Director's pass reports and flown records, which are used only to score ODIN against his flights. ODIN's instructions must not be shaped by them.
5. **Secrets.** API keys and tokens come from environment variables only: `META_API_KEY` and `BASETEN_API_KEY`. ODIN's private signing key lives at the path in `ODIN_KEY_PATH`, outside the repository. No key, token or private key may appear in a file, a log, a prompt, a test fixture or your output. A test scans the repository for secrets and fails if it finds one.
6. **Paid calls.** Build and test against `stand_in` and the fake harness. A real model call is allowed only in the one short daily check (§7, milestone M3) and when the Director starts a scored run. Never put a paid call inside a loop or a retry storm.
7. **You do not commit.** Claude Code commits your work exactly as you deposit it and never alters it (§6). When a piece is ready, show it running (§8), then deposit it.
8. **A check is a callable that can fail.** Every test you write gets a red case beside it that makes it fail on purpose, and you show the red case failing before you trust the green.
9. **No Streamlit**, no web UI. ODIN is a process, not a dashboard.

## 3. The interfaces you use (contract §8)

Ports come from `config/ports.yaml`. Your fake harness reads the same file.

- From the harness: `GET /turn/next` (long poll), `GET /docs/lookup?q=`, `GET /history?points=&window_s=`.
- To BALDUR-0: `POST /request` (a signed `COMMAND_REQUEST`), `POST /escalation`.
- To the log: `POST /log/agent` (`AGENT_INPUT`, `CANDIDATE`, `ANSWER` or `MALFORMED`, `MODEL_CALL`), `POST /report`.
- **Addendum A-1, check-in delivery (approved with this handoff):** the harness exposes `POST /checkin` with `{"text": <transcript>, "audio_sha256": <hash of the audio>, "source": "LIVE" | "RECORDED", "utc": ...}`. Your voice path calls it after transcribing. The harness turns it into a check-in trigger.

Your fake harness implements all of these against fixtures you write yourself: nominal HUGINN frames built from the dictionary, made-up plans signed with a test key, and no fault content.

## 4. What each piece must do

### 4.1 Turn loop
- One turn in flight at a time. Wait on `GET /turn/next`.
- Save the exact bundle bytes and the exact prompt bytes as files named by their SHA-256 (`runs/<run_id>/inputs/` under the repository root you run from, derived from `run_id`; contract §16.1, U16). Then post `AGENT_INPUT` with both hashes, **before** calling the model (contract §4, §6.3).
- Build the prompt with everything that does not change during a run first (instructions, the frozen COSMOS reference, the plan, the procedures) and the turn's changing parts last, so prompt caching works.
- On an `ACT` turn, the model answers with exactly one JSON object of one of three forms (contract §7.1). On a `REPORT` turn, it answers with exactly one report (contract §7.5). Anything else is `MALFORMED`: log it and send nothing.
- Validate against the dictionary: a command exists, with exactly its arguments and allowed values.
- Fill in `request_id`, `origin` (`ODIN`), `utc`, `met_s`, `nonce`, `run_id`, `turn_id`, `plan_id`, `agent_input_hash`, then sign with Ed25519 over the canonical JSON of every other field (contract §4, §7.3). The model never writes these fields.
- **One answer, one request.**
- A timeout, an error or a malformed answer produces no request and is logged (contract §9.5).

### 4.2 Model adapters (contract §11.1)
- `spark`: Meta Model API, OpenAI-compatible at `https://api.meta.ai/v1`, model `muse-spark-1.3`, Standard-mode key from `META_API_KEY`. Use structured output for the answer schemas (ruled 26 October: each model at its best, by its strongest structured method) and tool calling for the two read-only tools (docs lookup and history). No tool may send a command.
- `spark_open`: Baseten Model API, OpenAI-compatible at `https://inference.baseten.co/v1`, model exactly `meta-models/muse-spark-open-1026` (Baseten's docs show `meta-models/muse-spark-open`; the hackathon key works only with the `-1026` name), key from `BASETEN_API_KEY`. Baseten offers no structured output or JSON mode for this model, so it answers by tool calling (contract §11.1, ruled 26 October): define one answer tool for each answer form of contract §7.1 and one for the report of §7.5, each with the fields the model writes for that form as its parameters. The model may call the two read-only tools, then ends the turn (contract §11.1, as amended 29 October 2026). If the turn ends with exactly one answer-tool call, turn that call into the §7.2 JSON object. If it ends with no answer-tool call, the message content, with the whitespace around it trimmed, must parse as exactly one JSON object, and that object is the answer. Either way, pass it through the same validator as `spark`. Anything else is `MALFORMED`: prose, a code fence, two objects, more than one answer-tool call, or wrong fields. `reasoning_content` is never the answer. Log the message that ends the turn as `CANDIDATE` with channel `MESSAGE`: its content and its tool calls, exactly as returned (contract §16.5). Set `reasoning_effort` explicitly on every call (Baseten's default is `xhigh`). Record the endpoint and model ID in every run's configuration.
- `glimmer_local`: Muse Glimmer 30B on the Director's laptop, served by Ollama (≥ 0.32.7, `OLLAMA_MODELS` on D:) or llama.cpp `llama serve` pointed at `D:\models\muse-glimmer\Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf`. Never download the model again to C:.
- `glimmer_modal` (M5's prep; the Director's ruling of 29 October 2026): Muse Glimmer 30B on Modal, the onboard seat's fallback should `glimmer_local` miss 60 s a decision. It is the same weights, served by llama.cpp behind Modal's proxy auth. Call `POST <endpoint>/v1/chat/completions`, OpenAI-compatible, where `<endpoint>` is the URL Claude Code puts in configuration; send the headers `Modal-Key` and `Modal-Secret` with the values of `ODIN_MODAL_PROXY_KEY` and `ODIN_MODAL_PROXY_SECRET`, read from the environment and never written anywhere. Answer with structured output (`response_format` of type `json_schema`), as for `spark`. Charge the meter per GPU-second of each call's wall time, at the `per_gpu_second` price in `config/prices.yaml`, against the Modal stop, set in `odin/spend/meter.py` to $125 (the Director's ruling of 29 October 2026). Never start, warm or stop the server: Claude Code does that around each run.
- `stand_in`: scripted answers in every form, reports included, plus deliberately malformed ones. It never calls a network.
- Every call sets a maximum output (reasoning included) and a timeout, both read from configuration. **Reasoning effort is the Director's to set:** run M3's measurement and report the results; do not pick a value for scored runs.

### 4.3 Spend meter (contract §11.2, §11.3)
- Prices come from `config/prices.yaml`, read at run time. Never keep a second copy.
- **Before each call:** reserve the worst-case cost (known input tokens at the full input price, plus the call's maximum output at the output price). If spent plus reserved would pass a stop, refuse the call and log `SPEND_STOP`. **After the call:** replace the reservation with the actual cost.
- Stops: Meta **$125**, Baseten **$90**, Modal **$12.00**. Track four amounts separately: Meta hackathon credit used, Baseten hackathon credit used, Modal plan credit used, out-of-pocket.
- The meter's ledger survives a restart: the spend file is appended, never overwritten.

### 4.4 Study step
- A fetch script pinned to OpenC3 COSMOS tag **v7.2.1**, the `docs.openc3.com/docs` tree, records each file's hash and writes to `cache/cosmos-docs-7.2.1/` (git-ignored; Claude Code's docs lookup reads the same folder). The repository keeps the script and the hashes, never the docs.
- One `spark` call reads all the docs and writes ODIN's operations reference. The reference is frozen, hashed, and listed in each plan's `references`. It carries OpenC3's notice and is labeled as derived from OpenC3's documentation. Enterprise-only features are marked absent.

### 4.5 Voice check-in
- Muse Voice Transcribe turns audio into text. The same path serves a recorded clip (scored runs) and a live push-to-talk recording (the demo and finals).
- After transcribing, call `POST /checkin` (A-1). A check-in never changes ODIN's authority.

### 4.6 Glimmer onboard test
- Run a fixed set of turn bundles from your fake harness through `glimmer_local` at the reasoning levels the Director names, and record seconds per decision and whether each answer is well formed.
- The pass mark is the Director's ruling: **under 60 seconds per decision, plus the same quality checks as `spark`.** Your test measures speed and well-formedness; the quality checks come from the scored runs.

## 5. ODIN's instructions (the system prompt)

You write them in `odin/instructions/`. They must:
- say that ODIN is Project AESIR's operational intelligence, flying a simulated CubeSat under a signed TYR-0 mission plan at the rung its arming act sets;
- tell ODIN to fly by the plan and the procedures in force, act only within them, and read every command's outcome from telemetry rather than assume it;
- define the answer forms and the report exactly as contract §7 does, and require exactly one JSON object with nothing else;
- state "one answer, one request";
- explain escalations as a record of ODIN's judgment, which in this build asks nothing of anyone;
- contain nothing about any particular fault, scenario or expected answer.

They are frozen and hashed before the held-out runs (contract §10.4). After the freeze they do not change.

## 6. Deposits

**The Director's ruling (26 October 2026), verbatim:** "1. Approved. 2. Approved, with one exception - a shared folder where Muse code deposits a frozen zip for Claude Code, for the purposes of #3: 3. Claude Code commits Muses' portion as well as its own but does not alter Muse's build. 4. Approved. 5. Approved."

When the Director has seen a piece run and says to deposit it:
1. Write one zip to `to-claude-code/`, named `MC-<milestone>-<NN>.zip` (for example `MC-M1-01.zip`), numbered upward. Never overwrite or delete a deposit; a correction is a new deposit with the next number.
2. Put in it your whole `odin/` folder as it stands, `keys/odin.pub` if it changed, a `MANIFEST.sha256` listing every file with its SHA-256, and a `DEPOSIT.md` stating the milestone, the tests run with their results (red cases included), the date the Director saw it run, and the commit message you suggest.
3. Nothing outside your scope goes in a deposit: no `runs/`, no `cache/`, no secrets.

Claude Code checks the manifest, commits the deposit byte for byte with your message plus the lines `Built-with: Muse Code (muse-wonder-1.0)` and the deposit's name and SHA-256, and changes nothing in it. If a repository-wide test fails on your deposit, Claude Code stops and reports, and the fix comes from you as a new deposit.

## 7. Milestones and goals

Work in this order. Pin each goal with `/goal` at the start of the session that works on it.

**M1. The loop on the stand-in.**
`/goal Build ODIN's turn loop, answer check, input saving, request signing and the fake harness and fake BALDUR-0 per CONTRACT.md §4, §6–§8 and .agents/AGENTS.md §4.1. Done ONLY when python -m pytest odin/tests/test_m1_*.py passes, with red cases shown failing first, covering: a stand-in run of 20 turns end to end; every malformed form rejected; saved input bytes hash to the logged hashes; a request's signature verifies with keys/odin.pub and fails after a one-byte change; the model never sets request_id, origin, nonce or signature; `spark_open`'s answer-tool conversion, tested on recorded responses with no network call: one answer-tool call becomes the §7.2 object, and no call, two calls, or wrong fields are MALFORMED; no file imports ve; the secret scan finds nothing.`

**M2. The spend meter.**
`/goal Build the spend meter per CONTRACT.md §11.2–§11.3 and .agents/AGENTS.md §4.3. Done ONLY when python -m pytest odin/tests/test_m2_*.py passes, red cases shown failing first, covering: a call refused when spent plus reserved would pass $125 (Meta), $90 (Baseten) or $12.00 (Modal); actual cost replacing the reservation; the four amounts kept apart; the ledger surviving a restart.`

**M3. One real check, and the reasoning measurement.** With the Director present: one short `spark` call through the whole loop, then the same small fixed bundle at reasoning low, medium and high, through `spark` and through `spark_open`, recording tokens, cost, seconds and whether the answer was well formed for each. Report the table and stop. The Director picks the reasoning level.

**M4. The study step.**
`/goal Build the COSMOS docs fetch and study step per .agents/AGENTS.md §4.4. Done ONLY when python -m pytest odin/tests/test_m4_*.py passes, red cases shown failing first, covering: the fetch is pinned to v7.2.1 and every file's hash matches the recorded list; the repository contains no docs; the frozen reference's hash is recorded and changes if one byte of it changes.` The real study call itself runs with the Director present.

**M5. The Glimmer onboard test** (§4.6), with the Director present.

**M6. The voice check-in** (§4.5): a recorded clip goes through transcription and `POST /checkin` to the fake harness.

**M7. ODIN's instructions** (§5), reviewed by the Director before they are frozen.

## 8. Show the Director before anything is done

No piece is finished until the Director has seen it run: the test output with its red cases, a short clip, or a command he runs himself. Then you deposit it (§6).

## 9. Stop and report

When the contract or these rules do not settle something, or a check fails that you cannot fix within your scope, stop and write:

```
STOP AND REPORT
What I was doing:
What is unsettled or failing:
The options I can see, in plain language, with what each costs:
What I need from the Director:
```

Then wait. Do not choose an option yourself.
