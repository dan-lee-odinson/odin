"""BALDUR-0's two endpoints (CONTRACT.md §8.2), on the baldur0 port of config/ports.yaml.

POST /request takes a signed COMMAND_REQUEST and replies with the decision record. POST /escalation
takes an escalation and replies {record_id, delivery}. The harness starts the server for a run, bound
to that run's Gateway, and says through after_request what follows an allowed request: in the ground
seat, dispatch at once; in the onboard seat, dispatch once the simulator has advanced (§10.1).
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

from gateway.gateway import RequestRefused

PORTS = Path(__file__).resolve().parent.parent / "config" / "ports.yaml"


def baldur0_address(ports=PORTS):
    """The host and port config/ports.yaml gives BALDUR-0."""
    config = yaml.safe_load(Path(ports).read_text(encoding="utf-8"))
    return config["host"], config["ports"]["baldur0"]


def _no_constant(name):
    raise ValueError(f"{name} is not a JSON number")


def make_server(gateway, address=None, *, after_request=None):
    """A server for the run's Gateway. Call serve_forever() on it, and shutdown() to stop it.
    after_request(decision_record) runs once the reply to an allowed or refused request is sent."""
    routes = {"/request": gateway.receive_request, "/escalation": gateway.receive_escalation}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            # The body is read before any reply, a refusal included: a reply sent while the request is
            # still unread can reach the client as a reset connection instead, as it does on Windows.
            length = self.headers.get("Content-Length", "")
            data = self.rfile.read(int(length)) if length.isdigit() else None
            receive = routes.get(self.path)
            if receive is None:
                self._reply(404, {"problems": [f"no endpoint {self.path}; BALDUR-0 takes /request and /escalation"]})
                return
            try:
                if data is None:
                    raise ValueError(f"Content-Length is {length!r}, not a length")
                body = json.loads(data, parse_constant=_no_constant)
            except ValueError as error:
                self._reply(400, {"problems": [f"the body is not one JSON value ({error})"]})
                return
            try:
                reply = receive(body)
            except RequestRefused as refusal:
                self._reply(400, {"problems": refusal.problems})
                return
            # The Director's ruling on U30 (27 October 2026): every decision record, ALLOW or REFUSE, is
            # sent with 200; the refusal is in the record.
            self._reply(200, reply)
            if receive == gateway.receive_request and after_request is not None:
                after_request(reply)

        def _reply(self, status, payload):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass   # the event log is the record; nothing is printed per request

    return ThreadingHTTPServer(address or baldur0_address(), Handler)
