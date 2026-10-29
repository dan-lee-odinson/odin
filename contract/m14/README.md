# Format B, for Muse Code's M14

The Director's ruling of 29 October 2026: M14 makes spark's ACT answer format B, with the log fix. These are the
files the probe of that day sent and got back, so that M14 can test against them. Nothing here is from phase 3.

- `format-B-HUGINN.json`: the format sent with phase 2's dictionary in force, HUGINN's five commands.
- `format-B-INST.json`: the format sent with phase 1's dictionary in force, INST's two commands.
- `answers-B.json`: spark's four answers to format B, each verbatim, with its finish reason, whether it matched the
  format sent, and how it was judged.

Format B, within Meta's limits (the root a plain object; no `oneOf`, `allOf`, `if`, `then` or `$ref`): `command` and
`parameters` give way to one field, `command_call`, an `anyOf` of branches, one per command in the dictionary in
force, each a closed object holding that command's name as a one-value enum and its own arguments in a closed shape,
typed as `act_format` types them now (a command with no arguments, an empty closed object). An escalation's
`proposed` is the same `anyOf`. Every other field is as in M11's format.

How each answer was judged, as the loop would: `command_call` put back as `command` and `parameters` where the
answer's form has them, then M11's null drop, then the frozen answer schema, the dictionary check and the loop.
Nothing repairs or drops an argument that a command does not take.

The probe's calls: phase 2's PASS-3 dev run, turn 4 (the stuck load), three times, and phase 1's turn 16 once.
Three were accepted. One, on PASS-3, put `"urgency": "ROUTINE"` on a command answer, which the frozen schema refuses.
`urgency` lies outside format B's change: M11's format leaves it open in the same way.
