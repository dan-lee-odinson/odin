"""How VERDA shows each record type of the event log (CONTRACT.md v0.6, section 12).

Every type the contract lists is either shown, with where and how, or listed in
NOT_SHOWN with the reason. tests/test_record_types.py checks that this table
names exactly the contract's types.
"""

SHOWN = {
    "RUN_START": "The header (scenario, phase, seat, model, mode) and a marker on the Plan and authority lane",
    "PLAN_CHAIN_VERIFIED": "A marker on the Plan and authority lane, and the header's plan chain badge",
    "ARMING_VERIFIED": "A marker on the Plan and authority lane, and the start of the rung bar",
    "PLAN_IN_FORCE": "The plan bar on the Plan and authority lane",
    "CONTACT": "The contact windows on the Contact lane",
    "TRIGGER": "A marker per turn on ODIN's turns lane, labeled with its triggers and answer",
    "AGENT_INPUT": "In its turn's record list, with the bundle it names",
    "MODEL_CALL": "In its turn's record list; tokens and cost in the turn's summary",
    "CANDIDATE": "In its turn's record list (the model's raw answer)",
    "ANSWER": "The answer named on its turn's marker, and in the turn's record list",
    "MALFORMED": "A red turn marker on ODIN's turns lane naming the reason",
    "REQUEST": "The start of a request chain on the Requests lane",
    "DECISION": "BALDUR-0's allow or refuse, with the failed check and reason, on the request chain",
    "DECISION_VOIDED": "A voided mark on the request chain, naming the check that failed at dispatch",
    "DISPATCH": "The dispatch mark on the request chain",
    "OUTCOME": "The outcome mark (accepted, rejected, no acknowledgement) that ends the request chain",
    "ESCALATION": "A marker on the Reports and escalations lane, with its kind and urgency",
    "REPORT": "A marker on the Reports and escalations lane, with its kind",
    "CHECK_IN": "A marker on the Director's lane, with his words",
    "REVOKE": "A marker on the Plan and authority lane, and the rung bar turning HUMAN_ONLY",
    "RESTORE": "A marker on the Plan and authority lane, and the rung bar returning when accepted",
    "SPEND": "In its turn's record list; the meter's totals in the header",
    "SPEND_STOP": "A red marker on ODIN's turns lane",
    "TOOL_USE": "In its turn's record list, and a tool count on the turn's marker",
    "RUN_END": "A marker on the Plan and authority lane, and the header's end reason",
}

NOT_SHOWN = {}

# The truth file's record types (not part of the contract's log). Shown on the
# truth lane, always labeled as simulator truth that ODIN never sees.
TRUTH_SHOWN = {
    "TRUE_STATE": "The dashed simulator-truth lines on the telemetry lanes, and the truth lane's spans",
    "FAULT_ONSET": "A marker on the truth lane",
    "SCRIPTED_COMMAND_DROPPED": "A marker on the truth lane",
}


def how_shown(record_type):
    if record_type in SHOWN:
        return SHOWN[record_type]
    if record_type in NOT_SHOWN:
        return "Not shown: " + NOT_SHOWN[record_type]
    return None
