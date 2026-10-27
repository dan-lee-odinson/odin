"""What BALDUR-0 decides by: the command classes and the rung table (CONTRACT.md §7.4), telemetry
freshness (§9.6), and the conditions of envelopes and leases (§5.1, §5.2, §16.2 U8).
"""

import operator

# §7.4. A request carries no class; BALDUR-0 looks it up here.
COMMAND_CLASS = {
    "CMD_PLD_SET_STATE": "C1",
    "CMD_PLD_SET_RATE": "C2",
    "CMD_SAFE_ENTER": "C3",
    "CMD_SYS_RESET": "C3",
    "CMD_MODE_SET": "C4",
}

# §5.5: no plan can prohibit or restrict these, envelope limits never raise them to C4, and missing
# telemetry never blocks them.
PROTECTIVE = frozenset(command for command, class_ in COMMAND_CLASS.items() if class_ == "C3")

# §7.4, the rung-by-class table reduced to the rungs this build uses. C4 is allowed at AI_AUTONOMOUS only under a
# lease, which the LEASE check decides.
RUNG_ALLOWS = {
    "HUMAN_ONLY": frozenset(),
    "AI_AUTONOMOUS": frozenset({"C1", "C2", "C3", "C4"}),
}

# §9.6: a frame more than 10 seconds of simulation time old is not fresh.
FRESH_S = 10

# §16.2 U8: the operators, written as words.
OPS = {"lt": operator.lt, "le": operator.le, "gt": operator.gt, "ge": operator.ge,
       "eq": operator.eq, "ne": operator.ne}


def frame_age(frame, met_s):
    """Simulation seconds since the newest frame, or None when there is no frame."""
    return None if frame is None else met_s - frame["frame_met_s"]


def is_fresh(frame, met_s):
    age = frame_age(frame, met_s)
    return age is not None and age <= FRESH_S


def staleness(frame, met_s):
    """The detail of a NO_FRESH_TELEMETRY refusal."""
    age = frame_age(frame, met_s)
    return "no frame received" if age is None else f"newest frame is {age:g} s old, more than {FRESH_S} s"


def describe(condition):
    return f"{condition['point']} {condition['op']} {condition['value']}"


def failing(conditions, frame):
    """The conditions that do not hold on the frame, each described with the value it found. A
    point missing from the frame, or a value of the wrong kind, does not hold."""
    points = frame["points"]
    found = []
    for condition in conditions:
        actual = points.get(condition["point"])
        try:
            holds = (actual is not None and not isinstance(actual, bool)
                     and OPS[condition["op"]](actual, condition["value"]))
        except TypeError:
            holds = False
        if not holds:
            found.append(f"{describe(condition)} does not hold ({condition['point']} is {actual!r})")
    return found


def rate_covered(rate, allowed):
    return allowed["min"] <= rate <= allowed["max"]


def arguments_covered(lease, parameters):
    """Whether a lease's allowed values cover a request's parameters (§16.2 U9): a list for state and
    target, an inclusive {min, max} for rate."""
    for name, allowed in lease["arguments"].items():
        value = parameters.get(name)
        if isinstance(allowed, dict):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not rate_covered(value, allowed):
                return False
        elif value not in allowed:
            return False
    return set(parameters) == set(lease["arguments"])
