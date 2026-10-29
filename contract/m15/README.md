# The regrouped format, for Muse Code's M15

The Director's ruling of 29 October 2026, "Regroup format, probe again": format B regrouped, so that a command
answer has nowhere to put an escalation's fields. These are the files the probe of that day sent and got back, so
that the change can be tested against them. Nothing here is from phase 3.

- `format-R-HUGINN.json`: the format sent with phase 2's dictionary in force, HUGINN's five commands.
- `format-R-INST.json`: the format sent with phase 1's dictionary in force, INST's two commands.
- `answers-R.json`: spark's ten answers to it, each verbatim, with its finish reason, whether it matched the format
  sent, what its `escalation` held, how it was judged, and its cost.
- `escalations-R.json`: five made-up answers in the regrouped format, judged the same way with no call, since no
  saved prompt has an escalation as its right answer.

The regrouped format, within Meta's limits (the root a plain object; no `oneOf`, `allOf`, `if`, `then` or `$ref`):
format B's escalation-only fields, `escalation_kind`, `refs`, `urgency` and `proposed`, move as they are into one
nullable object, `escalation`. `command_call` stays as in B. `kind` and `rationale` stay at the root. The root's
fields, in order: `kind`, `command_call`, `escalation`, `rationale`.

How each answer was judged, as the loop would: the `escalation` object's fields put back at the root where the
answer's form has them (an `escalation` of null puts back nulls; anything else is kept, so the frozen schema can
refuse it), then format B's judging as it stands (`odin.loop.loop.judge_act_text`): `command_call` put back as
`command` and `parameters`, M11's null drop, the frozen answer schema, the dictionary check and the loop. Nothing is
dropped that holds a value.

Why: in P3's spark dev run of 29 October 2026, `dev-ph2-p3-spark-02`, all five command answers were the right shed,
but each also carried `refs` (the procedure steps) and `urgency` `ROUTINE`. Format B allows both on any answer, and
the frozen schema refuses them on a command, so each was filed MALFORMED and no shed was sent.

The probe's calls: spark-02's turn 5 (the stuck load at MET 900) and turn 10 (MET 1200), and spark-01's turn 4 (MET
900), three times each, and phase 1's turn 16 (`dev-ph1-spark-m10`) once. All ten matched the format, finished with
`stop`, and were accepted; each was a command, and each command's `escalation` was null.
