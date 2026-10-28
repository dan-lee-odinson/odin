"""Fake harness + fake BALDUR-0 + fake log for ODIN's own testing (§8).

Implements every §8 interface against in-memory fixtures: nominal bundles
supplied by the caller, made-up plans, no fault content. Tests drive it
in-process via `transport` (no listening socket needed); `serve_http()`
exposes the same handlers over real HTTP for a Director demo.
The fake BALDUR-0 verifies ODIN's signature with keys/odin.pub and allows
well-formed requests; gateway policy itself is Claude Code's BALDUR-0 (M1
tests ODIN's side only).
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from odin.loop import signing
from odin.loop.validate import validate_against_schema

REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeServices:
    def __init__(self, bundles=None, public_key_path=None):
        self._bundles = list(bundles or [])
        self.public_key_path = str(public_key_path or (REPO_ROOT / "keys" / "odin.pub"))
        self.log_records = []
        self.requests = []
        self.decisions = []
        self.escalations = []
        self.reports = []
        self.checkins = []
        self.request_attempts = 0
        self.force_status = {}
        self._server = None
        self.url = "inprocess://fake"

    # -- in-process transport (used by tests) ------------------------------
    def transport(self, method, url, data=None):
        """Callable matching TurnLoop's transport: (method, url, bytes) -> (status, bytes)."""
        parsed = urlparse(url)
        path = parsed.path or url  # allow bare paths
        body = json.loads(data) if data else {}
        if method == "POST" and path.endswith("/request"):
            self.request_attempts += 1
        if method == "GET" and path == "/turn/next":
            if self._bundles:
                return 200, self._bundles.pop(0)
            return 200, json.dumps({"run_complete": True}).encode()
        if method == "GET" and path == "/docs/lookup":
            q = parse_qs(parsed.query).get("q", [""])[0]
            return 200, json.dumps({"query": q, "results": []}).encode()
        if method == "GET" and path == "/history":
            return 200, json.dumps({"columns": ["met_s"], "rows": []}).encode()
        if method == "POST" and path == "/log/agent":
            # U21 (seven record types) + U24 replies, validated on the schemas.
            problems = validate_against_schema("log_agent.schema.json", body)
            if problems:
                return 400, json.dumps({"problems": problems}).encode()
            self.log_records.append(body)
            return 200, json.dumps({"record_id": len(self.log_records)}).encode()
        if method == "POST" and path == "/report":
            problems = validate_against_schema("report.schema.json", body)
            if problems:
                return 400, json.dumps({"problems": problems}).encode()
            self.reports.append(body)
            return 200, json.dumps({"record_id": len(self.reports)}).encode()
        if method == "POST" and path == "/request":
            # U30: every decision (ALLOW or REFUSE) is 200 with the decision
            # record; an invalid body is 400 with problems, nothing logged.
            if path in self.force_status or "/request" in self.force_status:
                return self.force_status.get(path, self.force_status.get("/request")), \
                    json.dumps({"problems": ["forced by test"]}).encode()
            problems = validate_against_schema("command_request.schema.json", body)
            if problems:
                return 400, json.dumps({"problems": problems}).encode()
            self.requests.append(body)
            try:
                ok = signing.verify_request(body, self.public_key_path)
            except Exception:
                ok = False
            decision = self._decision(body, ok)
            self.decisions.append(decision)
            return 200, json.dumps(decision).encode()
        if method == "POST" and path == "/escalation":
            problems = validate_against_schema("escalation.schema.json", body)
            if problems:
                return 400, json.dumps({"problems": problems}).encode()
            self.escalations.append(body)
            return 200, json.dumps({"record_id": len(self.escalations), "delivery": "NOW"}).encode()
        if method == "POST" and path == "/checkin":
            self.checkins.append(body)
            return 200, json.dumps({"ok": True}).encode()
        return 404, json.dumps({"error": "not found"}).encode()

    _CLASSES = {"CMD_PLD_SET_STATE": "C1", "CMD_PLD_SET_RATE": "C2",
                "CMD_SAFE_ENTER": "C3", "CMD_SYS_RESET": "C3", "CMD_MODE_SET": "C4"}

    def _decision(self, request, signature_ok):
        names = ["PLAN", "ARMING", "ORIGIN", "CEILING", "PROHIBITED", "CLASS", "LEASE", "RECORD"]
        command_class = self._CLASSES.get(request.get("command"))
        if signature_ok:
            checks = [{"check": n, "result": "PASS", "reason": None, "detail": None}
                      for n in names]
            return {
                "request_id": request.get("request_id"), "decision": "ALLOW",
                "checks": checks, "plan_id": request.get("plan_id"),
                "arming_act_id": "ARM-DEV-01", "rung": "AI_AUTONOMOUS",
                "base_class": command_class, "class": command_class,
                "lease_id": "L1" if command_class == "C4" else None,
                "met_s": request.get("met_s"), "utc": request.get("utc"),
            }
        checks = []
        for name in names:
            if name in ("PLAN", "ARMING"):
                checks.append({"check": name, "result": "PASS", "reason": None, "detail": None})
            elif name == "ORIGIN":
                checks.append({"check": name, "result": "FAIL",
                               "reason": "BAD_SIGNATURE", "detail": None})
            elif name == "RECORD":
                checks.append({"check": name, "result": "PASS", "reason": None, "detail": None})
            else:
                checks.append({"check": name, "result": "NOT_RUN", "reason": None, "detail": None})
        return {
            "request_id": request.get("request_id"), "decision": "REFUSE",
            "checks": checks, "plan_id": request.get("plan_id"),
            "arming_act_id": "ARM-DEV-01", "rung": "AI_AUTONOMOUS",
            "base_class": None, "class": None, "lease_id": None,
            "met_s": request.get("met_s"), "utc": request.get("utc"),
        }

    # -- real HTTP (Director demo only; not used by tests) ------------------
    def start(self):
        return self

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def serve_http(self, host="127.0.0.1", port=0):
        services = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _dispatch(self, method):
                length = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(length) if length else None
                status, body = services.transport(method, self.path, data)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._dispatch("GET")

            def do_POST(self):
                self._dispatch("POST")

        self._server = ThreadingHTTPServer((host, port), Handler)
        self.url = f"http://{host}:{self._server.server_address[1]}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self
