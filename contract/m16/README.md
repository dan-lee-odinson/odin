# Format G, Glimmer's own answer format, for Muse Code's M16

The Director's ruling of 30 October 2026, "Low, tie type to command (Recommended)", and his approval of the same
day, "Approve, but a 60 s timeout". Glimmer flies at reasoning strength `low` on one H100. It answers in its own
format, derived from the dictionary in force as M15's is, in which an answer's kind allows only its own fields:

- a kind of `none` has no `command_call` and no `escalation`;
- a `command` has a `command_call` and no `escalation`;
- an `escalation` has an `escalation` and no `command_call`.

Spark's and spark_open's formats don't change. Nothing here is from phase 3.

## The format

Format R (M15) is one plain object, as Meta's API requires. Glimmer's server, llama.cpp, compiles a JSON schema into
a grammar and can hold alternatives apart, so format G is three closed objects under one `anyOf`, one per kind. Each
has R's four fields in R's order: `kind`, `command_call`, `escalation`, `rationale`. `command_call` and an escalation's
`proposed` are R's, one closed branch per command of the dictionary in force, each with only its own arguments.

As drafted and approved:

1. **A field a kind does not allow is kept, and must be null**, rather than left out. The answer keeps R's shape, so
   the loop's put-backs (`put_back_escalation`, `put_back_command_call`, the null drop) work unchanged; the change is
   the format the glimmer_modal adapter sends.
2. **An escalation's own fields are those the frozen answer schema requires of one.** `escalation_kind`, `refs` and
   `urgency` are never null, and `proposed` is a command or null. In R each could be null, and a null one was refused
   by the frozen schema after the call; in G the server cannot write it.
3. **`rationale` stays as in R:** a string or null.

## Files

- `format-G-HUGINN.json`: the format with HUGINN's dictionary in force (phases 2 and 3; Glimmer flies only these).
- `format-G-INST.json`: with INST's, as M15 has both; Glimmer never flies a phase-1 plan.
- `checks-G.json`: every answer Glimmer gave in format R on the nine M5 timing prompts, on 29 and 30 October (36
  answers), each with how ODIN's loop judged it and whether format R and format G admit it. The prompts themselves
  are not here.
- `escalations-G.json`: hand-made answers, no call, each judged as the loop would: the four kinds of good answer,
  and six shapes format G must refuse, among them the two shapes of 30 October's five refusals.
- `answers-G.json`: Glimmer's nine answers in format G, on the H100 at reasoning strength `low`, each verbatim with
  its finish reason, seconds, prefill and decode, whether it matched format G, and how the loop judged it.

## What the checks found (30 October 2026)

- **With no call** (`checks-G.json`, `escalations-G.json`): of Glimmer's 36 answers in format R, the 31 the loop
  accepted all match format G, and the 5 it refused (each a kind and command_call that disagree) match none of its
  branches. The four hand-made good answers match and are accepted; the six shapes it must refuse are refused.
- **With the call** (`answers-G.json`): Glimmer on the H100 at `low` with format G, the nine prompts once each. All
  nine matched format G, finished with `stop`, and were accepted by the loop: the shed (`CMD_PLD_SET_STATE` OFF) at
  MET 900, no action at the other eight, as at `high` on 29 October. Seconds: mean 27.8, max 33.2.
- **The timing of record**, after phase 2, the same nine on the H100 at `low` with format G: all nine accepted; mean
  29.0 s, max 34.6 s, none over 60 s.

## Glimmer's model block, as approved

The Director approved it on 30 October 2026 with a 60 s timeout. It goes into `config/models.yaml`, and its hash
into `config/frozen.json`, once M16 is committed; until then `config/glimmer_modal.yaml` holds the endpoint. By the
Director's word, M16's adapter reads the endpoint from this block.

```yaml
glimmer_modal:
  model: Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf
  reasoning_effort: low
  max_output_tokens: 8192
  timeout_s: 60
  endpoint: https://dan-lee-odinson--odin-glimmer-serve-h100.us-east.modal.run
  gpu: H100
  source: the Director's ruling and approval of 30 October 2026 ("Low, tie type to command"; "Approve, but a 60 s timeout"), from M5's timing on Modal
  date: 2026-10-30
```
