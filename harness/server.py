"""The harness's endpoints (CONTRACT.md §8.1; Addendum A-1), on the harness port of config/ports.yaml.

GET /turn/next is a long poll: it answers with the next turn bundle, as its canonical JSON bytes, or
{"run_complete": true} once the run has ended. GET /docs/lookup?q= and GET /history?points=&window_s=
are ODIN's two read-only tools; every use is logged as TOOL_USE. POST /checkin takes the Director's
transcribed check-in and makes it a check-in trigger. A request that is not one of these, or whose
arguments do not fit, gets 400 or 404 with its problems, and nothing is logged.
"""

import json
import select
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from contract.validate import check
from wrapper.frames import POINTS

PORTS = Path(__file__).resolve().parent.parent / "config" / "ports.yaml"
MAX_WINDOW_S = 3600


def harness_address(ports=PORTS):
    """The host and port config/ports.yaml gives the harness."""
    config = yaml.safe_load(Path(ports).read_text(encoding="utf-8"))
    return config["host"], config["ports"]["harness"]


class Refused(Exception):
    def __init__(self, status, problems):
        super().__init__("; ".join(problems))
        self.status, self.problems = status, list(problems)


def _one(query, name):
    values = query.get(name, [])
    if len(values) != 1:
        raise Refused(400, [f"{name}: give it exactly once"])
    return values[0]


def history_arguments(query):
    """{points, window_s} from GET /history's query, points comma-separated (the Director's ruling on
    U19), window_s a whole number of seconds from 1 to 3,600 (§16.5)."""
    names = [name for name in _one(query, "points").split(",") if name]
    unknown = [name for name in names if name not in POINTS]
    window = _one(query, "window_s")
    problems = [f"points: {name} is not one of HUGINN's 16 points" for name in unknown]
    if not names:
        problems.append("points: name at least one point")
    if not window.isdigit() or not 1 <= int(window) <= MAX_WINDOW_S:
        problems.append(f"window_s: {window!r} is not a whole number of seconds from 1 to {MAX_WINDOW_S}")
    if problems:
        raise Refused(400, problems)
    return {"points": names, "window_s": int(window)}


def make_server(run, address=None):
    """A server for the run: run.next_turn(), run.docs_lookup(q), run.history(points, window_s) and
    run.check_in(body). Call serve_forever() on it, and shutdown() to stop it."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            try:
                if url.path == "/turn/next":
                    data = run.next_turn(gone=self._client_gone)
                    if data is not None:   # None: ODIN gave this poll up and has asked again
                        self._send(200, data)
                elif url.path == "/docs/lookup":
                    self._reply(200, run.docs_lookup(_one(query, "q")))
                elif url.path == "/history":
                    self._reply(200, run.history(**history_arguments(query)))
                else:
                    raise Refused(404, [f"no endpoint GET {url.path}; the harness serves /turn/next, "
                                        f"/docs/lookup and /history"])
            except Refused as refusal:
                self._reply(refusal.status, {"problems": refusal.problems})

        def do_POST(self):
            # The body is read before any reply, a refusal included: a reply sent while the request is
            # still unread can reach the client as a reset connection instead, as it does on Windows.
            length = self.headers.get("Content-Length", "")
            data = self.rfile.read(int(length)) if length.isdigit() else None
            try:
                if urlparse(self.path).path != "/checkin":
                    raise Refused(404, [f"no endpoint POST {self.path}; the harness takes /checkin"])
                try:
                    body = json.loads(data) if data is not None else None
                except ValueError as error:
                    raise Refused(400, [f"the body is not one JSON value ({error})"])
                problems = check("checkin", body)
                if problems:
                    raise Refused(400, problems)
                self._reply(200, run.check_in(body))
            except Refused as refusal:
                self._reply(refusal.status, {"problems": refusal.problems})

        def _client_gone(self):
            """Whether the client has hung up: its connection reads as closed, or is reset. A request has no
            body here, so anything readable on it is the end of the connection."""
            try:
                readable, _, _ = select.select([self.connection], [], [], 0)
                return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
            except OSError:
                return True

        def _reply(self, status, payload):
            self._send(status, json.dumps(payload).encode("utf-8"))

        def _send(self, status, data):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass   # the event log is the record

    return ThreadingHTTPServer(address or harness_address(), Handler)
