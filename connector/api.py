"""The COSMOS connector (CONTRACT.md §3, §6.4, §9.3; 00_HANDOFF.md §4, S5): reads telemetry from ODIN's COSMOS
and sends the commands BALDUR-0 allowed.

It speaks COSMOS's JSON-RPC API on API_URL, authorized by the service password, which comes from the
ODIN_COSMOS_* user environment variables and is never shown. The harness holds it; ODIN's process never does
(U38).

Telemetry is HUGINN's housekeeping packet as COSMOS decommutated it, its 16 points with COSMOS's received
time and count; in phase 1, the demo target's INST HEALTH_STATUS, its ten items with COSMOS's own limit states
(the Director's ruling on U58, 28 October 2026; inst()). Commands go out only through send(), which the harness gives BALDUR-0 as its COSMOS route, so
only a command BALDUR-0 allowed and rechecked reaches it. A command HUGINN's dictionary marks hazardous goes
through COSMOS's no-hazardous-check send, as §9.3 requires; COSMOS would refuse it through the ordinary one.
Every other command goes through the ordinary send.
"""

import datetime
import itertools
import json
import threading
import urllib.request

from connector.cosmos import API_URL, credentials
from wrapper.frames import COMMANDS, POINTS

TARGET, PACKET, INTERFACE = "HUGINN", "HK", "HUGINN_INT"
_ids = itertools.count(1)


class CosmosError(RuntimeError):
    """COSMOS answered a call with an error."""


def utc_of(seconds):
    """COSMOS's received time, Unix seconds, as §4's UTC with milliseconds."""
    moment = datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def decoded(value):
    """A value as COSMOS's JSON gives it. A float JSON cannot carry, as the demo's TEMP2 is at times, comes as
    {json_class: Float, raw: Infinity, -Infinity or NaN}, and is kept as that text, since no record in this
    build can carry it as a number (found in S7's live check, 28 October 2026)."""
    if isinstance(value, dict) and value.get("json_class") == "Float":
        return value["raw"]
    return value


def send_method(command):
    """cmd_no_hazardous_check for a command HUGINN's dictionary marks hazardous, cmd for any other."""
    return "cmd_no_hazardous_check" if COMMANDS[command]["hazardous"] else "cmd"


class CosmosApi:
    def __init__(self, url=API_URL, password=None, timeout_s=5, *, target=TARGET, packet=PACKET, interface=INTERFACE,
                 points=tuple(POINTS), hazardous=send_method):
        """password: COSMOS's service password; by default from the ODIN_COSMOS_* variables. target, packet,
        interface and points: what the seat reads, HUGINN's by default. hazardous: the send a command goes by."""
        self.url = url
        self._password = password if password is not None else credentials()["OPENC3_SERVICE_PASSWORD"]
        self.timeout_s = timeout_s
        self.target, self.packet_name, self.interface, self.points = target, packet, interface, tuple(points)
        self._send_method = hazardous
        self.sent = 0                            # the commands this connector has sent, which COSMOS took
        self._commanding = threading.Lock()      # a send, or a reading of COSMOS's command history, at a time
        self._commands = None                    # [[target, command], ...]: every command COSMOS knows the target by

    def call(self, method, *params, **keywords):
        body = json.dumps({"jsonrpc": "2.0", "method": method, "params": list(params), "id": next(_ids),
                           "keyword_params": {"scope": "DEFAULT", **keywords}}).encode("utf-8")
        request = urllib.request.Request(f"{self.url}/openc3-api/api", data=body, headers={
            "Content-Type": "application/json-rpc", "Authorization": self._password})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as reply:
            answer = json.loads(reply.read())
        if "error" in answer:
            raise CosmosError(f"{method}: {answer['error'].get('message')}")
        return answer["result"]

    def packet(self):
        """The newest packet as COSMOS holds it: {frame, limits, received_count, received_utc, packet_utc}, the
        frame being the points in the dictionary's order with COSMOS's converted values, and limits COSMOS's
        own limit state for each. received_count is COSMOS's count of the packet since it started, 0 before
        the first."""
        rows = self.call("get_tlm_packet", self.target, self.packet_name)
        items = {name: decoded(value) for name, value, *_ in rows}
        limits = {name: rest[0] if rest else None for name, _, *rest in rows}
        count = items.get("RECEIVED_COUNT") or 0
        return {"frame": {name: items[name] for name in self.points} if count else None,
                "limits": {name: limits[name] for name in self.points} if count else None,
                "received_count": count,
                "received_utc": utc_of(items["RECEIVED_TIMESECONDS"]) if count else None,
                "packet_utc": utc_of(items["PACKET_TIMESECONDS"]) if count and items.get("PACKET_TIMESECONDS") else None}

    def ground_link(self):
        """The seat's interface's {state, received_count} as COSMOS reports them (the observation's ground_link):
        HUGINN_INT, or in phase 1 the demo's own INST_INT."""
        interface = self.call("get_interface", self.interface)
        return {"state": interface["state"], "received_count": interface["rxcnt"]}

    def send(self, command, parameters):
        """Send one command BALDUR-0 allowed. Returns the send used."""
        method = self._send_method(command)
        with self._commanding:
            self.call(method, self.target, command, {name.upper(): value for name, value in parameters.items()})
            self.sent += 1
        return method

    def commands_by_others(self):
        """How many commands COSMOS has sent the target that this connector did not: COSMOS's command history, its
        count of each of the target's commands since it started, less this connector's own sends (the Director's
        ruling on U62, 28 October 2026). Read with no send of ours in between, so the two counts agree."""
        with self._commanding:
            if self._commands is None:
                self._commands = [[self.target, name] for name in self.call("get_all_cmd_names", self.target)]
            return sum(self.call("get_cmd_cnts", self._commands)) - self.sent


def inst(dictionary, **options):
    """The connector for phase 1: COSMOS's demo target, INST HEALTH_STATUS, the items of phase 1's dictionary,
    and the demo's own interface, INST_INT. None of its commands is hazardous in COSMOS (§1 of the Director's
    rulings of 27 October 2026), so each goes by the ordinary send."""
    group = dictionary["telemetry_groups"][0]
    hazardous = {command["mnemonic"]: command["hazardous"] for command in dictionary["commands"]}
    return CosmosApi(target="INST", packet=group["name"], interface="INST_INT",
                     points=[point["mnemonic"] for point in group["points"]],
                     hazardous=lambda command: "cmd_no_hazardous_check" if hazardous[command] else "cmd", **options)
