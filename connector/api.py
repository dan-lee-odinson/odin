"""The COSMOS connector (CONTRACT.md §3, §6.4, §9.3; 00_HANDOFF.md §4, S5): reads telemetry from ODIN's COSMOS
and sends the commands BALDUR-0 allowed.

It speaks COSMOS's JSON-RPC API on API_URL, authorized by the service password, which comes from the
ODIN_COSMOS_* user environment variables and is never shown. The harness holds it; ODIN's process never does
(U38).

Telemetry is HUGINN's housekeeping packet as COSMOS decommutated it, its 16 points with COSMOS's received
time and count. Commands go out only through send(), which the harness gives BALDUR-0 as its COSMOS route, so
only a command BALDUR-0 allowed and rechecked reaches it. A command HUGINN's dictionary marks hazardous goes
through COSMOS's no-hazardous-check send, as §9.3 requires; COSMOS would refuse it through the ordinary one.
Every other command goes through the ordinary send.
"""

import datetime
import itertools
import json
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


def send_method(command):
    """cmd_no_hazardous_check for a command HUGINN's dictionary marks hazardous, cmd for any other."""
    return "cmd_no_hazardous_check" if COMMANDS[command]["hazardous"] else "cmd"


class CosmosApi:
    def __init__(self, url=API_URL, password=None, timeout_s=5):
        """password: COSMOS's service password; by default from the ODIN_COSMOS_* variables."""
        self.url = url
        self._password = password if password is not None else credentials()["OPENC3_SERVICE_PASSWORD"]
        self.timeout_s = timeout_s

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
        """HUGINN's newest housekeeping packet as COSMOS holds it: {frame, received_count, received_utc}, the
        frame being the 16 points in the dictionary's order with COSMOS's converted values. received_count is
        COSMOS's count of the packet since it started, 0 before the first."""
        items = {name: value for name, value, *_ in self.call("get_tlm_packet", TARGET, PACKET)}
        count = items.get("RECEIVED_COUNT") or 0
        return {"frame": {name: items[name] for name in POINTS} if count else None, "received_count": count,
                "received_utc": utc_of(items["RECEIVED_TIMESECONDS"]) if count else None}

    def ground_link(self):
        """HUGINN_INT's {state, received_count} as COSMOS reports them (the observation's ground_link)."""
        interface = self.call("get_interface", INTERFACE)
        return {"state": interface["state"], "received_count": interface["rxcnt"]}

    def send(self, command, parameters):
        """Send one command BALDUR-0 allowed. Returns the send used."""
        method = send_method(command)
        self.call(method, TARGET, command, {name.upper(): value for name, value in parameters.items()})
        return method
