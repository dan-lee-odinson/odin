# Contract schemas

JSON Schema (Draft 7) for the records and messages of `CONTRACT.md` v0.6 §4–§9 and §12, settled in its §16, plus Addendum A-1's check-in. These files are the single source for the fields; the contract points to them (its preamble).

| Schema | What it checks | Contract |
|---|---|---|
| `common.schema.json` | Shared definitions: time, hashes, identifiers, classes, commands and their arguments, telemetry points, conditions, point tables | §4, §7.4, §16 |
| `tyr0_plan.schema.json` | A TYR-0 mission plan, with its leases | §5.1, §5.2, §5.5, §16.2, U27 |
| `arming_act.schema.json` | An arming act | §5.4, §16.2 |
| `restore_act.schema.json` | A restore act | §5.4 |
| `turn_bundle.schema.json` | The turn bundle from `GET /turn/next` | §6.2, §8.1, §16.1 |
| `observation.schema.json` | The observation inside a bundle | §6.4, §16.2 |
| `feed_report.schema.json` | One outside-feed report | §6.5 |
| `run_complete.schema.json` | `GET /turn/next`'s reply when the run has ended | §8.1 |
| `answer.schema.json` | The model's answer on an action turn | §7.1, §7.2, §16.3 |
| `report_body.schema.json` | The model's answer on a report turn: the fields of the report it writes | §7.5, §16.3 |
| `command_request.schema.json` | A signed `COMMAND_REQUEST` to `POST /request` | §7.3, §8.2, §16.3 |
| `escalation.schema.json` | The body of `POST /escalation` | §8.2, §16.5 |
| `escalation_reply.schema.json` | `POST /escalation`'s reply | §8.2, §16.5 |
| `report.schema.json` | A report to `POST /report` | §7.5, §8.3, §16.3 |
| `log_agent.schema.json` | The body of `POST /log/agent`: one of ODIN's seven record types, as `{type, body}` | §8.3, §12, U21 |
| `agent_input.schema.json` | ODIN's `AGENT_INPUT` record | §6.3, §16.5 |
| `model_call.schema.json` | ODIN's `MODEL_CALL` record | §11, §16.5 |
| `candidate.schema.json` | ODIN's `CANDIDATE` record | §8.3, §16.5 |
| `answer_record.schema.json` | ODIN's `ANSWER` record | §8.3, §16.5 |
| `malformed.schema.json` | ODIN's `MALFORMED` record | §7.2, §16.5 |
| `decision_record.schema.json` | BALDUR-0's decision record (`DECISION`), also `POST /request`'s reply | §9.1, §9.2, §16.4, U25, U28, U29 |
| `decision_voided.schema.json` | BALDUR-0's `DECISION_VOIDED` record | §9.3, §16.4 |
| `dispatch.schema.json` | BALDUR-0's `DISPATCH` record | §9.3, §16.4 |
| `outcome.schema.json` | BALDUR-0's `OUTCOME` record | §9.3, §16.4 |
| `docs_lookup_reply.schema.json` | `GET /docs/lookup`'s reply | §8.1, §16.5 |
| `history_reply.schema.json` | `GET /history`'s reply | §8.1, §16.5 |
| `tool_use.schema.json` | The harness's `TOOL_USE` record | §12, §16.5 |
| `checkin.schema.json` | The check-in to `POST /checkin` | A-1 |
| `log_record.schema.json` | One line of a run's event log, `runs/<run_id>/events.jsonl` | §12 |
| `run_start.schema.json` | The harness's `RUN_START` record | §10.2, §12, U21 |
| `plan_chain_verified.schema.json` | BALDUR-0's `PLAN_CHAIN_VERIFIED` record | §5.3, §12, U21 |
| `arming_verified.schema.json` | BALDUR-0's `ARMING_VERIFIED` record | §5.4, §12, U21 |
| `plan_in_force.schema.json` | BALDUR-0's `PLAN_IN_FORCE` record | §5.1, §12, U21 |
| `contact.schema.json` | The harness's `CONTACT` record | §6.1, §12, U21 |
| `trigger_record.schema.json` | The harness's `TRIGGER` record, with the hash of the bundle it served | §6.1, §12, U21 |
| `revoke.schema.json` | The harness's `REVOKE` record | §9.4, §12, U21 |
| `restore_record.schema.json` | BALDUR-0's `RESTORE` record | §9.4, §12, U21, U33 |
| `spend.schema.json` | ODIN's `SPEND` record | §11.3, §12, U21 |
| `spend_stop.schema.json` | ODIN's `SPEND_STOP` record | §11.3, §12, U21 |
| `run_end.schema.json` | The harness's `RUN_END` record | §12, U21 |
| `log_reply.schema.json` | `POST /log/agent`'s and `POST /report`'s reply when the record is written (HTTP 200) | §8.3, U24 |
| `log_refusal.schema.json` | Their reply when it is refused (HTTP 400) | §8.3, U24 |

References between schemas are relative file references, such as `common.schema.json#/definitions/utc`. Load the folder as a whole, as `contract/validate.py` does.

Point names, units, value types and limit states, and the commands with their arguments, are those of HUGINN's pinned dictionary, `deps/huginn/defs/tlm_cmd.yaml` at commit `b4dbe61`. A repository test fails if the two drift apart.

**Every field is present.** By §16's general rule, a record the system writes carries every field its schema lists, with `null` where the field's subject does not exist. Only the model may leave a field out, and only `rationale`.

**UNSETTLED.** A description containing `UNSETTLED (Un)` marks a field the contract names without settling its type or shape. Such a field accepts more than it should until the Director rules, and `tests/test_s1_settled.py` fails while any marker remains.

**Canonical JSON.** `canonical_vectors.json` holds values with their exact canonical bytes (§4, as the Director ruled on U22) and the SHA-256 of those bytes. Every canonical JSON writer in the build, ODIN's request signer included, must reproduce every vector.

**Not here.** The contract gives no reply body for `POST /checkin`, so none is defined here.

`examples/` holds the good examples. The bad ones are in `tests/test_s1_schemas.py`.
