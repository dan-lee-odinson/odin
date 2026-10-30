"""The event log's two endpoints (CONTRACT.md §8.3), on the log port of config/ports.yaml.

POST /log/agent takes one of ODIN's records as {type, body}, and POST /report takes a report. Each
replies 200 {"record_id": n} once the record is written, or 400 {"problems": [...]} when it is refused
and nothing is written (the Director's ruling on U24, 26 October 2026). The harness starts the server
for a run, bound to that run's EventLog.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

from log.chain import LogError

PORTS = Path(__file__).resolve().parent.parent / "config" / "ports.yaml"


def log_address(ports=PORTS):
    """The host and port config/ports.yaml gives the log."""
    config = yaml.safe_load(Path(ports).read_text(encoding="utf-8"))
    return config["host"], config["ports"]["log"]


def make_server(event_log, address=None, *, on_failure=None):
    """A server for the run's event log. Call serve_forever() on it, and shutdown() to stop it.
    on_failure(detail) is told of each submission refused and each failure the server did not foresee: ODIN
    submits only what its own loop builds, so either is a defect of ours, and the harness ends the run with
    ERROR and it as RUN_END's detail (the Director's ruling of 29 October 2026, closing the record's gaps)."""
    routes = {"/log/agent": event_log.submit_agent, "/report": event_log.submit_report}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            # The body is read before any reply, a refusal included: a reply sent while the request is
            # still unread can reach the client as a reset connection instead, as it does on Windows.
            length = self.headers.get("Content-Length", "")
            data = self.rfile.read(int(length)) if length.isdigit() else None
            submit = routes.get(self.path)
            if submit is None:
                self._refuse(404, [f"no endpoint {self.path}; the log takes /log/agent and /report"])
                return
            try:
                if data is None:
                    raise ValueError(f"Content-Length is {length!r}, not a length")
                body = json.loads(data)
            except ValueError as error:
                self._refuse(400, [f"the body is not one JSON value ({error})"])
                return
            try:
                record = submit(body)
            except LogError as refusal:
                self._refuse(400, refusal.problems)
                return
            except Exception as error:
                self._reply(500, {"problems": [f"the log failed: {error!r}"]})
                if on_failure is not None:
                    on_failure(f"the log failed on ODIN's POST {self.path}: {error!r}")
                return
            self._reply(200, {"record_id": record["record_id"]})

        def _refuse(self, status, problems):
            self._reply(status, {"problems": problems})
            if on_failure is not None:
                on_failure(f"the log refused ODIN's POST {self.path} ({status}): {'; '.join(problems)}")

        def _reply(self, status, payload):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass   # the event log is the record; nothing is printed per request

    return ThreadingHTTPServer(address or log_address(), Handler)
