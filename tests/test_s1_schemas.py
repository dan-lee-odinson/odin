"""contract/schemas/: each schema validates its good examples and rejects bad ones (00_HANDOFF.md §4, S1)."""

import base64
import copy
import uuid

import pytest
import yaml
from jsonschema import Draft7Validator

from tests.schema_checks import (DEFINITIONS_ONLY, EXAMPLE_DIR, check_document, load_document,
                                 load_schema, schema_names)

SCHEMAS = schema_names()
DOCUMENT_SCHEMAS = [name for name in SCHEMAS if name not in DEFINITIONS_ONLY]
GOOD = sorted(p for p in EXAMPLE_DIR.glob("*/good-*") if p.suffix in {".json", ".yaml"})


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_is_valid_draft7(name):
    Draft7Validator.check_schema(load_schema(name))


@pytest.mark.parametrize("path", GOOD, ids=lambda p: p.relative_to(EXAMPLE_DIR).as_posix())
def test_good_example_validates(path):
    assert check_document(path.parent.name, load_document(path)) == []


# Red cases. Each takes a good example, changes one thing, and expects the schema to refuse it.

def _walk(document, path):
    for key in path:
        document = document[key]
    return document


def setting(*path, to):
    def change(document):
        _walk(document, path[:-1])[path[-1]] = to
    return change


def dropping(*path):
    def change(document):
        del _walk(document, path[:-1])[path[-1]]
    return change


def appending(*path, item):
    def change(document):
        _walk(document, path).append(item)
    return change


def replacing(*path, old, new):
    def change(document):
        parent = _walk(document, path[:-1])
        parent[path[-1]] = parent[path[-1]].replace(old, new)
    return change


def swapping(*path, first, second):
    def change(document):
        items = _walk(document, path)
        items[first], items[second] = items[second], items[first]
    return change


def doubling(*path):
    def change(document):
        items = _walk(document, path)
        items.extend(copy.deepcopy(items))
    return change


def unwrapping_feedback(document):
    document["gateway_feedback"][0] = document["gateway_feedback"][0]["record"]


PLAN = "tyr0_plan/good-plan.yaml"
PLAN2 = "tyr0_plan/good-plan-pass2.yaml"
ARM = "arming_act/good-arm.yaml"
RESTORE = "restore_act/good-restore.yaml"
GROUND = "observation/good-ground.json"
ONBOARD = "observation/good-onboard.json"
NO_FRAME = "observation/good-no-frame.json"
FEED = "feed_report/good-station-receiver.json"
ACT = "turn_bundle/good-act.json"
CHECK_IN_TURN = "turn_bundle/good-report-check-in.json"
NO_PLAN = "turn_bundle/good-no-plan.json"
PAYLOAD = "answer/good-command-payload.json"
ESCALATE = "answer/good-escalation.json"
ESCALATE_NONE = "answer/good-escalation-no-proposal.json"
PASS_START = "report/good-pass-start.json"
CHECK_IN = "report/good-check-in.json"
BODY = "report_body/good-check-in.json"
REQUEST = "command_request/good-request.json"
ALLOW = "decision_record/good-allow.json"
REFUSE = "decision_record/good-refuse.json"
REFUSE_LEASE = "decision_record/good-refuse-lease.json"
REFUSE_PLAN = "decision_record/good-refuse-plan-mismatch.json"
REFUSE_RUN = "decision_record/good-refuse-wrong-run.json"
VOID_BASIS = "decision_voided/good-basis-changed.json"
VOID_FAIL = "decision_voided/good-condition-failed.json"
VOID_PLAN = "decision_voided/good-plan-mismatch.json"
TO_COSMOS = "dispatch/good-cosmos.json"
TO_UPLINK = "dispatch/good-uplink.json"
ACCEPTED = "outcome/good-accepted.json"
NO_ACK = "outcome/good-no-acknowledgement.json"
INPUT = "agent_input/good-input.json"
CALL = "model_call/good-spark.json"
STOPPED = "model_call/good-spend-stop.json"
STAND_IN = "model_call/good-stand-in.json"
CONTENT = "candidate/good-content.json"
TOOL_CALLS = "candidate/good-tool-calls.json"
ANSWERED = "answer_record/good-command.json"
REPORTED = "answer_record/good-report.json"
MALFORMED = "malformed/good-not-json.json"
LOG_INPUT = "log_agent/good-agent-input.json"
LOG_MALFORMED = "log_agent/good-malformed.json"
ESCALATION = "escalation/good-escalation.json"
REPLY = "escalation_reply/good-queued.json"
LOOKUP = "docs_lookup_reply/good-lookup.json"
HISTORY = "history_reply/good-history.json"
TOOL_USE = "tool_use/good-history.json"
DOCS_USE = "tool_use/good-docs-lookup.json"
CHECKIN = "checkin/good-recorded.json"
FIRST = "log_record/good-first-record.json"
LOGGED = "log_record/good-decision.json"
RUN_SPARK = "run_start/good-spark.json"
RUN_STAND_IN = "run_start/good-stand-in.json"
CHAIN_PASS = "plan_chain_verified/good-pass.json"
CHAIN_UNSIGNED = "plan_chain_verified/good-unsigned.json"
ARMED = "arming_verified/good-pass.json"
EXPIRED = "arming_verified/good-expired.json"
IN_FORCE = "plan_in_force/good-in-force.json"
LEFT_CHAIN = "plan_in_force/good-left-chain.json"
TRIGGER = "trigger_record/good-act.json"
TRIGGER_CHECK_IN = "trigger_record/good-check-in.json"
RESTORED = "restore_record/good-accepted.json"
RESTORE_REFUSED = "restore_record/good-already-used.json"
SPEND = "spend/good-after-call.json"
SPEND_STOP = "spend_stop/good-baseten.json"

UUID1 = str(uuid.UUID("3f2b8c1e-9a4d-1f6b-8e2a-7c5d1b0e9f34"))
BARE_HEX = "4e086337f7dfd018dde67cf48b14feb8390b59d741d0c2c4c90bd96dfa0cae1e"
SHA = "sha256:" + BARE_HEX
SIG = base64.b64encode(bytes(range(64))).decode()
PASSED = {"check": "PROHIBITED", "result": "PASS", "reason": None, "detail": None}
FAILED = {"check": "PROHIBITED", "result": "FAIL", "reason": "PROHIBITED_BY_PLAN", "detail": None}

BAD = [
    # §5.1, §5.2, §5.5, §16.2: the plan
    ("tyr0_plan", "prohibits CMD_SAFE_ENTER", PLAN, appending("prohibited", item="CMD_SAFE_ENTER")),
    ("tyr0_plan", "prohibits CMD_SYS_RESET", PLAN, appending("prohibited", item="CMD_SYS_RESET")),
    ("tyr0_plan", "leases CMD_SYS_RESET", PLAN, setting("leases", 0, "command", to="CMD_SYS_RESET")),
    ("tyr0_plan", "an extra field limiting the protective commands", PLAN,
     setting("protective_limits", to={"CMD_SAFE_ENTER": {"max_uses": 1}})),
    ("tyr0_plan", "pass_index 0", PLAN, setting("pass_index", to=0)),
    ("tyr0_plan", "valid_from_met_s not an integer", PLAN, setting("valid_from_met_s", to=0.5)),
    ("tyr0_plan", "an envelope point not in the dictionary", PLAN,
     setting("envelope", 0, "point", to="EPS_BATT_TEMP")),
    ("tyr0_plan", "an op written as a symbol", PLAN, setting("envelope", 0, "op", to=">=")),
    ("tyr0_plan", "an op §16.2 does not list", PLAN, setting("envelope", 0, "op", to="between")),
    ("tyr0_plan", "a numeric limit valued as text", PLAN, setting("envelope", 0, "value", to="35")),
    ("tyr0_plan", "a state condition compared with lt", PLAN, setting("leases", 1, "conditions", 0, "op", to="lt")),
    ("tyr0_plan", "a state condition valued outside its states", PLAN,
     setting("leases", 1, "conditions", 0, "value", to="HIBERNATE")),
    ("tyr0_plan", "a state limit valued as a number", PLAN2, setting("envelope", 1, "value", to=0)),
    ("tyr0_plan", "a lease allowing target SAFE", PLAN,
     setting("leases", 0, "arguments", "target", to=["SAFE"])),
    ("tyr0_plan", "lease arguments empty", PLAN, setting("leases", 0, "arguments", to={})),
    ("tyr0_plan", "a lease's allowed values not a list", PLAN,
     setting("leases", 0, "arguments", "target", to="NOMINAL")),
    ("tyr0_plan", "lease arguments of another command", PLAN,
     setting("leases", 1, "arguments", to={"target": ["NOMINAL"]})),
    ("tyr0_plan", "a rate lease without max", PLAN2, dropping("leases", 0, "arguments", "rate", "max")),
    ("tyr0_plan", "a rate lease reaching 12 Hz", PLAN2, setting("leases", 0, "arguments", "rate", "max", to=12.0)),
    ("tyr0_plan", "a rate lease starting below 0.1 Hz", PLAN2,
     setting("leases", 0, "arguments", "rate", "min", to=0.05)),
    ("tyr0_plan", "a rate lease written as a list", PLAN2,
     setting("leases", 0, "arguments", "rate", to=[0.5, 2.0])),
    ("tyr0_plan", "max_uses below zero", PLAN, setting("leases", 0, "max_uses", to=-1)),
    ("tyr0_plan", "a procedure hash without sha256:", PLAN,
     setting("procedures_in_force", 0, "sha256", to=BARE_HEX)),
    ("tyr0_plan", "a procedure version as a number", PLAN, setting("procedures_in_force", 0, "version", to=1)),
    ("tyr0_plan", "a procedure version empty", PLAN, setting("procedures_in_force", 0, "version", to="")),
    ("tyr0_plan", "objectives missing", PLAN, dropping("objectives")),
    # §5.4, §16.2: the acts
    ("arming_act", "kind RESTORE", ARM, setting("kind", to="RESTORE")),
    ("arming_act", "rung HUMAN_ONLY", ARM, setting("rung", to="HUMAN_ONLY")),
    ("arming_act", "expires_utc without milliseconds", ARM, setting("expires_utc", to="2026-11-04T23:59:59Z")),
    ("arming_act", "runs missing", ARM, dropping("runs")),
    ("arming_act", "a plan hash without sha256:", ARM, setting("plan_chain_hashes", 0, to=BARE_HEX)),
    ("arming_act", "a plan named instead of hashed", ARM, setting("plan_chain_hashes", 0, to="TYR0-DEV-PASS1-v1")),
    ("restore_act", "a list of runs, not exactly one", RESTORE, setting("run_id", to=["dev-run-0001", "dev-run-0002"])),
    ("restore_act", "kind ARM", RESTORE, setting("kind", to="ARM")),
    ("restore_act", "plan_id missing", RESTORE, dropping("plan_id")),
    # §6.4, §16.2: the observation
    ("observation", "ground seat without staleness_state", GROUND, dropping("staleness_state")),
    ("observation", "ground seat with staleness_state null", GROUND, setting("staleness_state", to=None)),
    ("observation", "onboard seat with staleness_state", ONBOARD, setting("staleness_state", to="GREEN")),
    ("observation", "onboard seat without staleness_state", ONBOARD, dropping("staleness_state")),
    ("observation", "ground seat without its ground link", GROUND, setting("ground_link", to=None)),
    ("observation", "onboard seat carrying a ground link", ONBOARD,
     setting("ground_link", to={"state": "CONNECTED", "received_count": 3100})),
    ("observation", "a link state COSMOS never reports", GROUND, setting("ground_link", "state", to="LOCKED")),
    ("observation", "a negative received count", GROUND, setting("ground_link", "received_count", to=-1)),
    ("observation", "a point missing", GROUND, dropping("points", "CDH_REJ_REASON")),
    ("observation", "a seventeenth point", GROUND,
     setting("points", "EPS_BATT_TEMP", to={"value": 20.0, "units": "C", "limit_state": "NONE"})),
    ("observation", "EPS_MODE outside its states", GROUND, setting("points", "EPS_MODE", "value", to="SHUTDOWN")),
    ("observation", "EPS_BATT_V in the wrong units", GROUND, setting("points", "EPS_BATT_V", "units", to="mV")),
    ("observation", "a counter below zero", GROUND, setting("points", "CDH_CMD_ACC_CNT", "value", to=-1)),
    ("observation", "a point without limits reporting GREEN", GROUND,
     setting("points", "CDH_MET", "limit_state", to="GREEN")),
    ("observation", "a limit state as a plain color", GROUND,
     setting("points", "EPS_BATT_V", "limit_state", to="YELLOW")),
    ("observation", "EPS_BATT_SOC above a limit it does not have", GROUND,
     setting("points", "EPS_BATT_SOC", "limit_state", to="YELLOW_HIGH")),
    ("observation", "EPS_LOAD_I below a limit it does not have", GROUND,
     setting("points", "EPS_LOAD_I", "limit_state", to="RED_LOW")),
    ("observation", "EPS_MODE in SAFE reporting GREEN", GROUND, setting("points", "EPS_MODE", "value", to="SAFE")),
    ("observation", "EPS_MODE NOMINAL reporting RED", GROUND,
     setting("points", "EPS_MODE", "limit_state", to="RED")),
    ("observation", "a frame with received_utc null", GROUND, setting("received_utc", to=None)),
    ("observation", "a frame with no points", GROUND, setting("points", to=None)),
    ("observation", "no frame but an age", NO_FRAME, setting("age_s", to=3.0)),
    ("observation", "no frame but points", NO_FRAME, setting("points", to={})),
    ("observation", "received_utc left out rather than null", NO_FRAME, dropping("received_utc")),
    ("feed_report", "a feed §6.5 does not list", FEED, setting("feed", to="radar")),
    ("feed_report", "content missing", FEED, dropping("content")),
    # §6.2, §16.1: the bundle
    ("turn_bundle", "turn_kind neither ACT nor REPORT", ACT, setting("turn_kind", to="THINK")),
    ("turn_bundle", "turn_id 0", ACT, setting("turn_id", to=0)),
    ("turn_bundle", "a field §6.2 does not list", ACT, setting("debug", to=True)),
    ("turn_bundle", "a run folder field", ACT, setting("run_folder", to="runs/dev-run-0001/inputs/")),
    ("turn_bundle", "an observation missing a point", ACT, dropping("observation", "points", "PLD_RATE")),
    ("turn_bundle", "a plan that prohibits CMD_SYS_RESET", ACT, appending("plan", "prohibited", item="CMD_SYS_RESET")),
    ("turn_bundle", "an earlier request carrying a class", ACT, setting("own_requests", 0, "class", to="C1")),
    ("turn_bundle", "a trigger type §16.1 does not list", ACT, setting("triggers", 0, "type", to="ALARM")),
    ("turn_bundle", "triggers as bare names", ACT, setting("triggers", to=["DECISION", "OUTCOME"])),
    ("turn_bundle", "a trigger without its time", ACT, dropping("triggers", 0, "met_s")),
    ("turn_bundle", "a DECISION trigger without its decision", ACT, dropping("triggers", 0, "detail", "decision")),
    ("turn_bundle", "an OUTCOME trigger carrying the result", ACT,
     setting("triggers", 1, "detail", "outcome", to="ACCEPTED")),
    ("turn_bundle", "a CHECK_IN trigger carrying a detail", CHECK_IN_TURN,
     setting("triggers", 0, "detail", "text", to="How is the battery?")),
    ("turn_bundle", "rung_reason given at AI_AUTONOMOUS", ACT, setting("rung_reason", to="REVOKED")),
    ("turn_bundle", "HUMAN_ONLY without a reason", NO_PLAN, setting("rung_reason", to=None)),
    ("turn_bundle", "a rung_reason §16.1 does not list", NO_PLAN, setting("rung_reason", to="EXPIRED")),
    ("turn_bundle", "the rung and its reason in one string", NO_PLAN, setting("rung", to="HUMAN_ONLY (NO_PLAN)")),
    ("turn_bundle", "AI_AUTONOMOUS with no plan in force", ACT, setting("plan", to=None)),
    ("turn_bundle", "report_kind on an ACT turn", ACT, setting("report_kind", to="PASS_START")),
    ("turn_bundle", "a REPORT turn without report_kind", CHECK_IN_TURN, setting("report_kind", to=None)),
    ("turn_bundle", "check_in_text on a turn that is not a check-in", ACT,
     setting("check_in_text", to="How is the battery?")),
    ("turn_bundle", "a check-in turn without the Director's words", CHECK_IN_TURN, setting("check_in_text", to=None)),
    ("turn_bundle", "check_in_text left out rather than null", ACT, dropping("check_in_text")),
    ("turn_bundle", "feeds left out rather than null", ACT, dropping("feeds")),
    ("turn_bundle", "history as a list of rows", ACT, setting("history", to=[])),
    ("turn_bundle", "history not starting with met_s", ACT, setting("history", "columns", 0, to="CDH_MET")),
    ("turn_bundle", "history naming a point twice", ACT, appending("history", "columns", item="EPS_MODE")),
    ("turn_bundle", "a history row without its time", ACT, setting("history", "rows", 0, 0, to="602")),
    ("turn_bundle", "uses_left as a list", ACT, setting("uses_left", to=[{"L1": 2}])),
    ("turn_bundle", "uses_left below zero", ACT, setting("uses_left", "L1", to=-1)),
    ("turn_bundle", "uses left with no plan in force", NO_PLAN, setting("uses_left", "L1", to=1)),
    ("turn_bundle", "the old single procedure field", ACT, setting("procedure", to={"id": "PROC-001"})),
    ("turn_bundle", "a procedure without its text", ACT, dropping("procedures", 0, "text")),
    ("turn_bundle", "an attachment that is not text", ACT,
     appending("procedures", 0, "attachments", item={"name": "orbit.png", "sha256": SHA, "data": "iVBORw0KGgo="})),
    ("turn_bundle", "procedures given with no plan in force", NO_PLAN, setting("procedures", to=[])),
    ("turn_bundle", "gateway feedback carrying an OUTCOME", ACT,
     appending("gateway_feedback", item={"type": "OUTCOME", "record": {"request_id": UUID1}})),
    ("turn_bundle", "gateway feedback not wrapped as {type, record}", ACT, unwrapping_feedback),
    ("turn_bundle", "a decision record filed as DECISION_VOIDED", ACT,
     setting("gateway_feedback", 0, "type", to="DECISION_VOIDED")),
    # §7.1, §7.2, §16.3: the answer
    ("answer", "a command not in the dictionary", PAYLOAD, setting("command", to="CMD_DEPLOY")),
    ("answer", "CMD_MODE_SET to SAFE", "answer/good-command-mode.json", setting("parameters", "target", to="SAFE")),
    ("answer", "rate above 10 Hz", "answer/good-command-rate.json", setting("parameters", "rate", to=12.0)),
    ("answer", "rate below 0.1 Hz", "answer/good-command-rate.json", setting("parameters", "rate", to=0.05)),
    ("answer", "an argument CMD_SAFE_ENTER does not take", "answer/good-command-safe.json",
     setting("parameters", "immediate", to=True)),
    ("answer", "an argument missing", PAYLOAD, dropping("parameters", "state")),
    ("answer", "parameters missing", "answer/good-command-safe.json", dropping("parameters")),
    ("answer", "the model writing request_id", PAYLOAD, setting("request_id", to="3f2b8c1e-9a4d-4f6b-8e2a-7c5d1b0e9f34")),
    ("answer", "the model writing signature", PAYLOAD, setting("signature", to=SIG)),
    ("answer", "a field no form has", PAYLOAD, setting("confidence", to=0.9)),
    ("answer", "an escalation kind §7.1 does not list", ESCALATE, setting("escalation_kind", to="HELP")),
    ("answer", "an urgency §7.1 does not list", ESCALATE, setting("urgency", to="HIGH")),
    ("answer", "an escalation without refs", ESCALATE, dropping("refs")),
    ("answer", "refs as one string", ESCALATE, setting("refs", to="PROC-001")),
    ("answer", "a ref that is not text", ESCALATE, setting("refs", 0, to=5)),
    ("answer", "proposed with a field besides command and parameters", ESCALATE,
     setting("proposed", "urgency", to="URGENT")),
    ("answer", "a proposed command with another command's arguments", ESCALATE,
     setting("proposed", "parameters", to={"state": "ON"})),
    ("answer", "a proposed command not in the dictionary", ESCALATE, setting("proposed", "command", to="CMD_DEPLOY")),
    ("answer", "proposed left out rather than null", ESCALATE_NONE, dropping("proposed")),
    ("answer", "proposed as prose", ESCALATE_NONE, setting("proposed", to="Enter safe mode.")),
    ("answer", "kind none carrying a command", "answer/good-none.json", setting("command", to="CMD_SAFE_ENTER")),
    ("answer", "a kind §7.1 does not list", "answer/good-none.json", setting("kind", to="nothing")),
    ("answer", "a rationale that is not text", PAYLOAD, setting("rationale", to=2)),
    # §7.5, §16.3: the report, and the model's part of it
    ("report", "a report_kind §7.5 does not list", PASS_START, setting("report_kind", to="STATUS")),
    ("report", "a check-in report without an answer", CHECK_IN, dropping("answer")),
    ("report", "an answer on a PASS_START report", PASS_START, setting("answer", to="All nominal.")),
    ("report", "an answer that is not text", CHECK_IN, setting("answer", to={"text": "The battery is fine."})),
    ("report", "timeline missing", PASS_START, dropping("timeline")),
    ("report", "turn_id 0", PASS_START, setting("turn_id", to=0)),
    ("report", "plan_id left out rather than null", PASS_START, dropping("plan_id")),
    ("report", "a timeline item as text", PASS_START, setting("timeline", 0, to="120: acquisition of signal")),
    ("report", "a timeline item without its time", CHECK_IN, dropping("timeline", 0, "met_s")),
    ("report", "an action outcome §16.3 does not list", CHECK_IN,
     setting("actions", 0, "outcome", to="accepted; PLD_STATE ON")),
    ("report", "an action without its request_id", CHECK_IN, dropping("actions", 0, "request_id")),
    ("report", "an action whose parameters do not fit its command", CHECK_IN,
     setting("actions", 0, "parameters", to={"rate": 2.0})),
    ("report", "condition as text", PASS_START, setting("condition", to="Nominal.")),
    ("report", "evidence as text", CHECK_IN, setting("condition", "evidence", 0, to="EPS_BATT_SOC 77 %")),
    ("report", "evidence valuing a state point as a number", CHECK_IN,
     setting("condition", "evidence", 1, "value", to=1)),
    ("report", "evidence valuing a numeric point as text", CHECK_IN,
     setting("condition", "evidence", 0, "value", to="77 %")),
    ("report", "a deferred objective without its reason", CHECK_IN, dropping("deferred", 0, "reason")),
    ("report", "an open issue that is not text", CHECK_IN, setting("open_issues", 0, to={"issue": "battery"})),
    ("report_body", "the model writing run_id", BODY, setting("run_id", to="dev-run-0001")),
    ("report_body", "the model writing report_kind", BODY, setting("report_kind", to="CHECK_IN")),
    ("report_body", "the model writing plan_id", BODY, setting("plan_id", to="TYR0-DEV-PASS1-v1")),
    ("report_body", "condition missing", BODY, dropping("condition")),
    ("report_body", "an action outcome §16.3 does not list", BODY, setting("actions", 0, "outcome", to="DONE")),
    # §7.3, §16.3: the request
    ("command_request", "origin other than ODIN", REQUEST, setting("origin", to="DIRECTOR")),
    ("command_request", "request_id not a version 4 UUID", REQUEST, setting("request_id", to=UUID1)),
    ("command_request", "agent_input_hash without sha256:", REQUEST, setting("agent_input_hash", to=BARE_HEX)),
    ("command_request", "signature missing", REQUEST, dropping("signature")),
    ("command_request", "a class, which a request never carries", REQUEST, setting("class", to="C1")),
    ("command_request", "parameters that do not fit the command", REQUEST,
     setting("parameters", to={"target": "NOMINAL"})),
    ("command_request", "utc with a local offset", REQUEST, setting("utc", to="2026-10-28T10:10:03.120-04:00")),
    ("command_request", "plan_id left out rather than null", REQUEST, dropping("plan_id")),
    ("command_request", "a nonce of 64 bits", REQUEST, setting("nonce", to="b7d1c94e0a2f4e7d")),
    ("command_request", "a nonce in capitals", REQUEST, setting("nonce", to="6D1F0C3A9B2E4F5781A6C0D9E3B7F214")),
    ("command_request", "a nonce as a number", REQUEST, setting("nonce", to=12345678901234567890)),
    ("command_request", "a signature in hex", REQUEST, setting("signature", to="ab" * 64)),
    ("command_request", "a signature in URL-safe base64", REQUEST, replacing("signature", old="+", new="-")),
    ("command_request", "a signature without its padding", REQUEST, replacing("signature", old="==", new="")),
    ("command_request", "a signature one byte short", REQUEST,
     setting("signature", to=base64.b64encode(bytes(range(63))).decode())),
    # §9.2, §16.4: the decision record
    ("decision_record", "a decision neither ALLOW nor REFUSE", ALLOW, setting("decision", to="DEFER")),
    ("decision_record", "a check §9.1 does not have", ALLOW, setting("checks", 0, "check", to="SPEND")),
    ("decision_record", "a rung this build does not use", ALLOW, setting("rung", to="SUPERVISED")),
    ("decision_record", "checks missing", REFUSE, dropping("checks")),
    ("decision_record", "seven checks, not eight", ALLOW, dropping("checks", 7)),
    ("decision_record", "a ninth check", ALLOW,
     appending("checks", item={"check": "RECORD", "result": "PASS", "reason": None, "detail": None})),
    ("decision_record", "checks out of order", ALLOW, swapping("checks", first=0, second=1)),
    ("decision_record", "a check run after a failure", REFUSE, setting("checks", 5, "result", to="PASS")),
    ("decision_record", "a refusal whose checks all pass", REFUSE, setting("checks", 4, to=PASSED)),
    ("decision_record", "an allowance with a failed check", ALLOW, setting("checks", 4, to=FAILED)),
    ("decision_record", "RECORD not passing", REFUSE, setting("checks", 7, "result", to="NOT_RUN")),
    ("decision_record", "a result §16.4 does not list", ALLOW, setting("checks", 0, "result", to="SKIPPED")),
    ("decision_record", "a failed check with no reason", REFUSE, setting("checks", 4, "reason", to=None)),
    ("decision_record", "a reason belonging to another check", REFUSE, setting("checks", 4, "reason", to="REVOKED")),
    ("decision_record", "a reason on a passing check", ALLOW, setting("checks", 0, "reason", to="NO_PLAN_IN_FORCE")),
    ("decision_record", "a detail that is not text", REFUSE_LEASE, setting("checks", 6, "detail", to=3)),
    ("decision_record", "a class written as words", ALLOW, setting("class", to="ROUTINE")),
    ("decision_record", "base_class left out rather than null", REFUSE, dropping("base_class")),
    ("decision_record", "a class though the decision stopped before the lookup", REFUSE, setting("class", to="C2")),
    ("decision_record", "an allowed C4 command with no lease", ALLOW, setting("class", to="C4")),
    ("decision_record", "an allowed C1 command naming a lease", ALLOW, setting("lease_id", to="L1")),
    ("decision_record", "a C3 command raised", ALLOW, setting("base_class", to="C3")),
    ("decision_record", "a lease refusal below C4", REFUSE_LEASE, setting("class", to="C1")),
    ("decision_record", "an allowance with no plan", ALLOW, setting("plan_id", to=None)),
    ("decision_record", "PLAN_MISMATCH with no plan in force (U29)", REFUSE_PLAN, setting("plan_id", to=None)),
    ("decision_record", "NO_PLAN_IN_FORCE naming a plan in force (U29)", REFUSE_PLAN,
     setting("checks", 0, "reason", to="NO_PLAN_IN_FORCE")),
    ("decision_record", "WRONG_RUN given at ARMING, not ORIGIN (U28)", REFUSE_RUN,
     setting("checks", 1, to={"check": "ARMING", "result": "FAIL", "reason": "WRONG_RUN", "detail": None})),
    ("decision_voided", "PLAN_MISMATCH on ARMING (U29)", VOID_PLAN, setting("check", to="ARMING")),
    ("decision_voided", "BASIS_CHANGED on ORIGIN", VOID_BASIS, setting("check", to="ORIGIN")),
    ("decision_voided", "a reason belonging to another check", VOID_FAIL, setting("reason", to="REVOKED")),
    ("decision_voided", "a reason §16.4 does not list", VOID_FAIL, setting("reason", to="TOO_LATE")),
    ("decision_voided", "naming RECORD", VOID_BASIS, setting("check", to="RECORD")),
    ("decision_voided", "decision_record_id 0", VOID_BASIS, setting("decision_record_id", to=0)),
    ("decision_voided", "detail left out rather than null", VOID_FAIL, dropping("detail")),
    # §9.3, §16.4: dispatch and outcome
    ("dispatch", "a route §16.4 does not list", TO_COSMOS, setting("route", to="RADIO")),
    ("dispatch", "parameters that do not fit the command", TO_COSMOS, setting("parameters", to={"state": "ON"})),
    ("dispatch", "lease_id left out rather than null", TO_UPLINK, dropping("lease_id")),
    ("dispatch", "request_id not a version 4 UUID", TO_UPLINK, setting("request_id", to=UUID1)),
    ("outcome", "REFUSED, which is BALDUR-0's word, not the spacecraft's", ACCEPTED, setting("outcome", to="REFUSED")),
    ("outcome", "ACCEPTED with no counter after", ACCEPTED, setting("acc_after", to=None)),
    ("outcome", "ACCEPTED with no frame time", ACCEPTED, setting("frame_met_s", to=None)),
    ("outcome", "REJECTED with no reject reason set", ACCEPTED, setting("outcome", to="REJECTED")),
    ("outcome", "a counter past 65535", ACCEPTED, setting("acc_after", to=65536)),
    ("outcome", "the point as a bare mnemonic", ACCEPTED, setting("point", to="PLD_STATE")),
    ("outcome", "the point valued outside its states", ACCEPTED, setting("point", "value", to="STANDBY")),
    ("outcome", "a reject reason the dictionary does not have", NO_ACK, setting("rej_reason", to="TIMEOUT")),
    ("outcome", "point left out rather than null", NO_ACK, dropping("point")),
    # §8.3, §16.5: ODIN's log submissions
    ("agent_input", "a bundle hash without sha256:", INPUT, setting("bundle_sha256", to=BARE_HEX)),
    ("agent_input", "the prompt hash missing", INPUT, dropping("prompt_sha256")),
    ("agent_input", "a run folder field", INPUT, setting("inputs_dir", to="runs/dev-run-0001/inputs/")),
    ("model_call", "a status §16.5 does not list", CALL, setting("status", to="RATE_LIMITED")),
    ("model_call", "a configuration §11.1 does not list", CALL, setting("config", to="spark_pro")),
    ("model_call", "pays_from not one of the four amounts", CALL, setting("pays_from", to="CARD")),
    ("model_call", "an OK call with no output count", CALL, setting("output_tokens", to=None)),
    ("model_call", "an OK call with no actual cost", CALL, setting("actual_cost_usd", to=None)),
    ("model_call", "a real model with no maximum output", CALL, setting("max_output_tokens", to=None)),
    ("model_call", "a real model with no reasoning setting", STOPPED, setting("reasoning_effort", to=None)),
    ("model_call", "a stopped call with a latency", STOPPED, setting("latency_s", to=1.2)),
    ("model_call", "a reservation below zero", CALL, setting("reserved_cost_usd", to=-0.01)),
    ("model_call", "provider usage as text", CALL, setting("provider_usage", to="prompt_tokens=18234")),
    ("model_call", "a token count left out rather than null", STOPPED, dropping("reasoning_tokens")),
    ("model_call", "a negative token count", STAND_IN, setting("input_tokens", to=-1)),
    ("model_call", "call_index counting from 0", CALL, setting("call_index", to=0)),
    ("model_call", "call_index as text", CALL, setting("call_index", to="1")),
    ("candidate", "reasoning content as a channel", CONTENT, setting("channel", to="REASONING")),
    ("candidate", "tool calls parsed rather than kept raw", TOOL_CALLS, setting("raw", to=[{"id": "call_0"}])),
    ("candidate", "raw missing", CONTENT, dropping("raw")),
    ("answer_record", "an answer of neither form", ANSWERED, setting("answer", "command", to="CMD_DEPLOY")),
    ("answer_record", "a report body carrying report_kind", REPORTED, setting("answer", "report_kind", to="CHECK_IN")),
    ("answer_record", "turn_id 0", ANSWERED, setting("turn_id", to=0)),
    ("malformed", "a timeout filed as malformed", MALFORMED, setting("reason", to="TIMEOUT")),
    ("malformed", "detail missing", MALFORMED, dropping("detail")),
    ("log_agent", "ODIN submitting a decision", LOG_INPUT, setting("type", to="DECISION")),
    ("log_agent", "a body that does not fit its type", LOG_INPUT, setting("type", to="MODEL_CALL")),
    ("log_agent", "ODIN stamping its own record_id", LOG_MALFORMED, setting("record_id", to=12)),
    ("log_agent", "body missing", LOG_INPUT, dropping("body")),
    # §8.1, §8.2, §16.5: escalations and the read-only tools
    ("escalation", "the loop's agent_input_hash missing", ESCALATION, dropping("agent_input_hash")),
    ("escalation", "a signature, which escalations do not carry", ESCALATION, setting("signature", to=SIG)),
    ("escalation", "an escalation kind §7.1 does not list", ESCALATION, setting("escalation_kind", to="HELP")),
    ("escalation", "plan_id left out rather than null", ESCALATION, dropping("plan_id")),
    ("escalation", "kind command", ESCALATION, setting("kind", to="command")),
    ("escalation_reply", "a delivery §16.5 does not list", REPLY, setting("delivery", to="LATER")),
    ("escalation_reply", "record_id 0", REPLY, setting("record_id", to=0)),
    ("docs_lookup_reply", "more than three results", LOOKUP, doubling("results")),
    ("docs_lookup_reply", "text past 4,000 characters", LOOKUP, setting("results", 0, "text", to="x" * 4001)),
    ("docs_lookup_reply", "truncated as text", LOOKUP, setting("results", 0, "truncated", to="yes")),
    ("docs_lookup_reply", "a page hash without sha256:", LOOKUP, setting("results", 0, "sha256", to=BARE_HEX)),
    ("docs_lookup_reply", "the query missing", LOOKUP, dropping("query")),
    ("history_reply", "a row starting with text", HISTORY, setting("rows", 0, 0, to="0")),
    ("history_reply", "a column that is not a point", HISTORY, appending("columns", item="EPS_BATT_TEMP")),
    ("history_reply", "columns missing", HISTORY, dropping("columns")),
    ("history_reply", "a row as an object", HISTORY, setting("rows", 0, to={"met_s": 0, "EPS_BATT_V": 7.9})),
    ("tool_use", "a result hash without sha256:", TOOL_USE, setting("result_sha256", to=BARE_HEX)),
    ("tool_use", "turn_id missing", TOOL_USE, dropping("turn_id")),
    ("tool_use", "the reply itself instead of its hash", TOOL_USE,
     setting("result", to={"columns": ["met_s"], "rows": []})),
    ("tool_use", "a tool named by its path", TOOL_USE, setting("tool", to="/history")),
    ("tool_use", "a tool §8.4 does not have", DOCS_USE, setting("tool", to="send_command")),
    ("tool_use", "arguments as the raw query string", TOOL_USE,
     setting("arguments", to="points=EPS_BATT_V,EPS_BATT_SOC&window_s=900")),
    ("tool_use", "points left as the comma-separated text", TOOL_USE,
     setting("arguments", "points", to="EPS_BATT_V,EPS_BATT_SOC")),
    ("tool_use", "a point not in the dictionary", TOOL_USE, setting("arguments", "points", 0, to="EPS_BATT_TEMP")),
    ("tool_use", "window_s left as text", TOOL_USE, setting("arguments", "window_s", to="900")),
    ("tool_use", "window_s past 3,600", TOOL_USE, setting("arguments", "window_s", to=3601)),
    ("tool_use", "a history use without window_s", TOOL_USE, dropping("arguments", "window_s")),
    ("tool_use", "a history argument the call does not take", TOOL_USE, setting("arguments", "q", to="battery")),
    ("tool_use", "a docs lookup without q", DOCS_USE, dropping("arguments", "q")),
    ("tool_use", "a docs lookup recorded as the history call", DOCS_USE, setting("tool", to="history")),
    # §12: the event log record (S2)
    ("log_record", "record_id 0", FIRST, setting("record_id", to=0)),
    ("log_record", "the first record with a prev_hash", FIRST, setting("prev_hash", to=SHA)),
    ("log_record", "a later record with no prev_hash", LOGGED, setting("prev_hash", to=None)),
    ("log_record", "a prev_hash without sha256:", LOGGED, setting("prev_hash", to=BARE_HEX)),
    ("log_record", "a type §12 does not list", LOGGED, setting("type", to="FAULT_ONSET")),
    ("log_record", "a field §12 does not list", LOGGED, setting("writer", to="BALDUR-0")),
    ("log_record", "a body that does not fit its type", LOGGED, setting("type", to="DISPATCH")),
    ("log_record", "a trigger whose body is missing its bundle hash", FIRST, dropping("body", "bundle_sha256")),
    ("log_record", "a decision whose checks are wrong", LOGGED, setting("body", "checks", 5, "result", to="FAIL")),
    ("log_record", "met_s missing", LOGGED, dropping("met_s")),
    ("log_record", "utc without milliseconds", LOGGED, setting("utc", to="2026-10-28T14:10:03Z")),
    ("log_record", "a body that is not an object", LOGGED, setting("body", to="ALLOW")),
    ("log_record", "a trigger whose bundle hash is bare hex", FIRST, setting("body", "bundle_sha256", to=BARE_HEX)),
    ("log_record", "a spend total below zero", "log_record/good-spend.json",
     setting("body", "meta_credit_usd", to=-1)),
    # §10.2, §11, §12: the records U21 settled
    ("run_start", "a phase the build does not have", RUN_SPARK, setting("phase", to=4)),
    ("run_start", "a mode neither DEVELOPMENT nor SCORED", RUN_SPARK, setting("mode", to="PRACTICE")),
    ("run_start", "a seed that is not an integer", RUN_SPARK, setting("seed", to="1")),
    ("run_start", "a model configuration §11.1 does not list", RUN_SPARK, setting("model_config", to="spark_pro")),
    ("run_start", "spark answering by answer tools", RUN_SPARK, setting("answer_method", to="ANSWER_TOOLS")),
    ("run_start", "the stand-in answering by structured output", RUN_STAND_IN,
     setting("answer_method", to="STRUCTURED_OUTPUT")),
    ("run_start", "a real model with no model ID", RUN_SPARK, setting("model_id", to=None)),
    ("run_start", "no configuration hash", RUN_SPARK, setting("config_sha256", to=None)),
    ("run_start", "a plan chain named instead of hashed", RUN_SPARK, setting("plan_chain_sha256", to="TYR0-DEV-PASS1-v1")),
    ("run_start", "reference_sha256 left out rather than null", RUN_STAND_IN, dropping("reference_sha256")),
    ("plan_chain_verified", "a pass with a reason", CHAIN_PASS, setting("reason", to="GAP")),
    ("plan_chain_verified", "a failure without a reason", CHAIN_UNSIGNED, setting("reason", to=None)),
    ("plan_chain_verified", "a pass with a missing signature", CHAIN_PASS, setting("plans", 1, "signature", to="MISSING")),
    ("plan_chain_verified", "a pass with no plans", CHAIN_PASS, setting("plans", to=[])),
    ("plan_chain_verified", "UNSIGNED with every plan signed", CHAIN_UNSIGNED, setting("plans", 1, "signature", to="GOOD")),
    ("plan_chain_verified", "a reason U21 does not list", CHAIN_UNSIGNED, setting("reason", to="EXPIRED")),
    ("plan_chain_verified", "a plan hash without sha256:", CHAIN_PASS, setting("plans", 0, "sha256", to=BARE_HEX)),
    ("plan_chain_verified", "a pass with a plan whose ID could not be read", CHAIN_PASS, setting("plans", 0, "plan_id", to=None)),
    ("arming_verified", "a pass with a reason", ARMED, setting("reason", to="EXPIRED")),
    ("arming_verified", "a failure without a reason", EXPIRED, setting("reason", to=None)),
    ("arming_verified", "a pass at HUMAN_ONLY", ARMED, setting("rung", to="HUMAN_ONLY")),
    ("arming_verified", "a pass with no act", ARMED, setting("act_id", to=None)),
    ("arming_verified", "a reason U21 does not list", EXPIRED, setting("reason", to="ALREADY_USED")),
    ("plan_in_force", "a plan ID with no hash", IN_FORCE, setting("sha256", to=None)),
    ("plan_in_force", "leaving the chain with a span left over", LEFT_CHAIN, setting("valid_from_met_s", to=10800)),
    ("plan_in_force", "a validity span in fractions", IN_FORCE, setting("valid_until_met_s", to=5400.5)),
    ("contact", "a state other than AOS or LOS", "contact/good-aos.json", setting("state", to="IN_CONTACT")),
    ("trigger_record", "a REPORT turn with no report_kind", TRIGGER_CHECK_IN, setting("report_kind", to=None)),
    ("trigger_record", "an ACT turn with a report_kind", TRIGGER, setting("report_kind", to="PASS_START")),
    ("trigger_record", "a trigger type §16.1 does not list", TRIGGER, setting("triggers", 0, "type", to="ALARM")),
    ("trigger_record", "the bundle hash missing", TRIGGER, dropping("bundle_sha256")),
    ("trigger_record", "the bundle itself instead of its hash", TRIGGER, setting("bundle", to={"turn_id": 4})),
    ("revoke", "a revocation from a source other than the script", "revoke/good-script.json",
     setting("source", to="DIRECTOR")),
    ("restore_record", "accepted with a reason", RESTORED, setting("reason", to="EXPIRED")),
    ("restore_record", "refused without a reason", RESTORE_REFUSED, setting("reason", to=None)),
    ("restore_record", "accepted though for another plan (U33)", "restore_record/good-wrong-plan.json",
     setting("result", to="ACCEPTED")),
    ("restore_record", "accepted with no act", RESTORED, setting("act_id", to=None)),
    ("restore_record", "a reason U21 does not list", RESTORE_REFUSED, setting("reason", to="NOT_ARMED")),
    ("spend", "a total below zero", SPEND, setting("baseten_credit_usd", to=-0.01)),
    ("spend", "an amount U21 does not list", SPEND, setting("total_usd", to=0.0412318)),
    ("spend", "call_index counting from 0", SPEND, setting("call_index", to=0)),
    ("spend", "a total left out", SPEND, dropping("modal_credit_usd")),
    ("spend_stop", "spark_open stopped at the Meta stop", SPEND_STOP, setting("stop", to="META")),
    ("spend_stop", "a stop U21 does not list", SPEND_STOP, setting("stop", to="OUT_OF_POCKET")),
    ("spend_stop", "a limit of zero", SPEND_STOP, setting("limit_usd", to=0)),
    ("spend_stop", "the reservation missing", SPEND_STOP, dropping("reserved_usd")),
    ("run_end", "a reason U21 does not list", "run_end/good-complete.json", setting("reason", to="TIMEOUT")),
    ("run_end", "turns below zero", "run_end/good-complete.json", setting("turns", to=-1)),
    # §8.3, U24: the log's replies
    ("log_reply", "record_id 0", "log_reply/good-reply.json", setting("record_id", to=0)),
    ("log_reply", "problems on a success", "log_reply/good-reply.json", setting("problems", to=["none"])),
    ("log_refusal", "a refusal with no problems", "log_refusal/good-refusal.json", setting("problems", to=[])),
    ("log_refusal", "a refusal with a record_id", "log_refusal/good-refusal.json", setting("record_id", to=7)),
    ("log_refusal", "problems as one string", "log_refusal/good-refusal.json", setting("problems", to="bad type")),
    ("log_agent", "a spend stop whose body is a spend", "log_agent/good-spend.json", setting("type", to="SPEND_STOP")),
    ("log_agent", "ODIN submitting RUN_END", "log_agent/good-spend.json", setting("type", to="RUN_END")),
    # A-1: the check-in
    ("checkin", "a source A-1 does not list", CHECKIN, setting("source", to="PHONE")),
    ("checkin", "audio hash without sha256:", CHECKIN, setting("audio_sha256", to=BARE_HEX)),
    ("checkin", "text missing", CHECKIN, dropping("text")),
    ("checkin", "a field that would touch authority", CHECKIN, setting("rung", to="HUMAN_ONLY")),
    ("checkin", "a recording with no audio hash", CHECKIN, setting("audio_sha256", to=None)),
    ("checkin", "text carrying an audio hash", CHECKIN, setting("source", to="TEXT")),
    # §8.1: run complete
    ("run_complete", "run_complete false", "run_complete/good-reply.json", setting("run_complete", to=False)),
    ("run_complete", "a field besides run_complete", "run_complete/good-reply.json", setting("turn_id", to=9)),
]


@pytest.mark.parametrize("schema, label, example, change", BAD,
                         ids=[f"{schema} - {label}" for schema, label, _, _ in BAD])
def test_red_bad_example_is_rejected(schema, label, example, change):
    document = load_document(EXAMPLE_DIR / example)
    assert check_document(schema, document) == [], "the good example must pass before it is broken"
    change(document)
    assert check_document(schema, document) != []


@pytest.mark.parametrize("name", DOCUMENT_SCHEMAS)
def test_every_schema_has_a_good_example_and_a_red_case(name):
    assert any(path.parent.name == name for path in GOOD), f"{name}: no good example"
    assert any(schema == name for schema, *_ in BAD), f"{name}: no red case"


# YAML reads unquoted ON and OFF as true and false, an unquoted timestamp as a datetime, and an
# unquoted version such as 1.0 as a number. Plans and acts are YAML, so the schemas must refuse all three.

def test_red_unquoted_on_off_in_a_yaml_lease_is_rejected():
    plan = load_document(EXAMPLE_DIR / PLAN)
    plan["leases"].append({"lease_id": "L3", "command": "CMD_PLD_SET_STATE",
                           "arguments": yaml.safe_load("state: [OFF, ON]"),
                           "conditions": [], "max_uses": None})
    assert check_document("tyr0_plan", plan) != []
    plan["leases"][-1]["arguments"] = yaml.safe_load('state: ["OFF", "ON"]')
    assert check_document("tyr0_plan", plan) == []


def test_red_unquoted_on_in_a_yaml_condition_is_rejected():
    plan = load_document(EXAMPLE_DIR / PLAN)
    plan["envelope"].append(yaml.safe_load("{point: PLD_STATE, op: eq, value: ON}"))
    assert check_document("tyr0_plan", plan) != []
    plan["envelope"][-1] = yaml.safe_load('{point: PLD_STATE, op: eq, value: "ON"}')
    assert check_document("tyr0_plan", plan) == []


def test_red_unquoted_procedure_version_in_a_yaml_plan_is_rejected():
    text = (EXAMPLE_DIR / PLAN).read_text(encoding="utf-8")
    assert 'version: "1"' in text
    assert check_document("tyr0_plan", yaml.safe_load(text.replace('version: "1"', "version: 1.0"))) != []


def test_red_unquoted_timestamp_in_a_yaml_act_is_rejected():
    text = (EXAMPLE_DIR / RESTORE).read_text(encoding="utf-8")
    act = yaml.safe_load(text.replace('"2026-11-04T23:59:59.000Z"', "2026-11-04T23:59:59.000Z"))
    assert check_document("restore_act", act) != []
