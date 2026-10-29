"""Reads the telemetry points and limits VERDA needs from HUGINN's dictionary.

The dictionary (tlm_cmd.yaml) is YAML. VERDA uses no third-party library, so this
module reads only the simple lines of the dictionary's telemetry_groups block:
"key: value" scalars, inline lists and one nested "limits:" map per point. It
fails loudly on anything it does not expect rather than guessing.

limit_state() applies the contract's rule (CONTRACT.md v0.6, section 16.2, U7):
below the red low limit RED_LOW, else below the yellow low limit YELLOW_LOW,
else above the red high limit RED_HIGH, else above the yellow high limit
YELLOW_HIGH, else GREEN; a state point is RED in an annunciating state and GREEN
otherwise; every other point is NONE.
"""

import re

THRESHOLD_KEYS = ("rl", "yl", "yh", "rh")

_TOP_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")
_POINT_START = re.compile(r"^(\s*)- mnemonic:\s*(\S+)\s*$")
_GROUP_START = re.compile(r"^\s*- name:")
_KEY_VALUE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*$")


class DictionaryError(Exception):
    pass


def _strip_comment(text):
    """Drops a trailing '# ...' comment that sits outside quotes."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text


def _scalar(text, where):
    text = _strip_comment(text).strip()
    if text in ("null", "~", ""):
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part, where) for part in inner.split(",")]
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+|\d+)([eE][-+]?\d+)?", text):
        return float(text)
    if text in ("|-", "|", ">", ">-"):
        raise DictionaryError("%s: block text is not expected here" % where)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text):
        return text  # a plain word, such as float or thresholds
    raise DictionaryError("%s: cannot read the value %r" % (where, text))


def read_points(path):
    """Returns {mnemonic: {type, units, enum_values, limits, order}} in frame order."""
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip() == "telemetry_groups:")
    except StopIteration:
        raise DictionaryError("%s has no telemetry_groups block" % path)
    points = {}
    current = None
    limits_indent = None
    for number, line in enumerate(lines[start + 1:], start=start + 2):
        where = "%s line %d" % (path, number)
        if _TOP_KEY.match(line):
            break  # the telemetry block has ended
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _POINT_START.match(line)
        if match:
            name = match.group(2)
            if name in points:
                raise DictionaryError("%s: %s is listed twice" % (where, name))
            current = {"mnemonic": name, "order": len(points), "limits": {}}
            points[name] = current
            limits_indent = None
            continue
        if _GROUP_START.match(line):
            current = None
            limits_indent = None
            continue
        if current is None:
            continue  # group-level keys such as limits_header
        match = _KEY_VALUE.match(line)
        if not match:
            raise DictionaryError("%s: cannot read %r" % (where, line))
        indent, key, value = len(match.group(1)), match.group(2), match.group(3)
        if key == "limits" and _strip_comment(value) == "":
            limits_indent = indent
            continue
        if limits_indent is not None and indent > limits_indent:
            current["limits"][key] = _scalar(value, where)
        else:
            limits_indent = None
            if key in ("description",):
                continue  # free text VERDA does not use
            current[key] = _scalar(value, where)
    if not points:
        raise DictionaryError("%s: no telemetry points found" % path)
    for name, info in points.items():
        kind = info["limits"].get("kind")
        if kind is None:
            raise DictionaryError("%s: %s has no limits kind" % (path, name))
        if kind == "thresholds":
            missing = [k for k in THRESHOLD_KEYS if k not in info["limits"]]
            if missing:
                raise DictionaryError("%s: %s lacks %s" % (path, name, ", ".join(missing)))
        info.setdefault("units", None)
        info.setdefault("enum_values", None)
    return points


def limit_state(info, value):
    """The limit state of one value of one point, by the contract's rule (U7)."""
    if value is None:
        return None
    if info is None:
        return None
    limits = info["limits"]
    kind = limits.get("kind")
    if kind == "thresholds":
        rl, yl, yh, rh = (limits[k] for k in THRESHOLD_KEYS)
        if rl is not None and value < rl:
            return "RED_LOW"
        if yl is not None and value < yl:
            return "YELLOW_LOW"
        if rh is not None and value > rh:
            return "RED_HIGH"
        if yh is not None and value > yh:
            return "YELLOW_HIGH"
        return "GREEN"
    if kind == "state":
        return "RED" if value in (limits.get("annunciates") or []) else "GREEN"
    return "NONE"


def chart_limits(info):
    """The thresholds a chart shades, or None for a point without them."""
    if info is None or info["limits"].get("kind") != "thresholds":
        return None
    return {k: info["limits"][k] for k in THRESHOLD_KEYS}


def staleness_limits(points):
    """The ground staleness monitor's thresholds from CDH_FRAME_CNT, in seconds."""
    for info in points.values():
        limits = info["limits"]
        if limits.get("kind") == "staleness":
            return {"yellow_s": limits["yellow_s"], "red_s": limits["red_s"]}
    raise DictionaryError("the dictionary has no staleness monitor")
