"""A stand-in for COSMOS's demo target in phase 1's tests (the Director's ruling on U58, 28 October 2026): INST
HEALTH_STATUS packets made on a clock, with COSMOS's own limit states, from phase 1's dictionary; the demo's
interface, INST_INT; and COLLECT and ABORT carried out as the demo's simulator does, the accept counter rising
with each and the collect count with each collect. tests/live_s7_pass.py runs the same against ODIN's COSMOS
with the demo plugin loaded."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml

from tests.repo_checks import REPO_ROOT

DICTIONARY = yaml.safe_load((REPO_ROOT / "config" / "dictionaries" / "INST.yaml").read_text(encoding="utf-8"))
POINTS = {p["mnemonic"]: p for p in DICTIONARY["telemetry_groups"][0]["points"]}
# TEMP1 as the demo swings it, through every state its limits give.
TEMP1_SWING = [10.0, 30.0, 65.0, 85.0, 65.0, 30.0, 10.0, -30.0, -75.0, -85.0, -75.0, -30.0]
# TEMP2 as the demo spoils it at times, with the limit state COSMOS gave each in S7's live check.
NON_FINITE = {"Infinity": "RED_HIGH", "-Infinity": "RED_LOW", "NaN": "RED_LOW"}


def cosmos_limits(name, value):
    """COSMOS's limit state for an item of phase 1's dictionary."""
    limits = POINTS[name]["limits"]
    if value in NON_FINITE:
        return NON_FINITE[value]
    if limits["kind"] == "state_colors":
        return limits["colors"][value]
    if limits["kind"] != "thresholds":
        return None
    if value < limits["rl"]:
        return "RED_LOW"
    if value < limits["yl"]:
        return "YELLOW_LOW"
    if value > limits["rh"]:
        return "RED_HIGH"
    if value > limits["yh"]:
        return "YELLOW_HIGH"
    if "gl" in limits:
        return "BLUE" if limits["gl"] <= value <= limits["gh"] else "GREEN_LOW" if value < limits["gl"] else "GREEN_HIGH"
    return "GREEN"


class FakeInst:
    def __init__(self, password, *, period_s=0.1, state="CONNECTED"):
        self.password, self.period_s, self.state = password, period_s, state
        self.values = {"CMD_ACPT_CNT": 0, "COLLECTS": 0, "TEMP1": TEMP1_SWING[0], "TEMP2": 1.5, "TEMP3": 20.25,
                       "TEMP4": 0.5, "DURATION": 0.0, "COLLECT_TYPE": "NORMAL", "GROUND1STATUS": "CONNECTED",
                       "GROUND2STATUS": "UNAVAILABLE"}
        self.count, self.sent = 0, []
        self.packet_s = self.received_s = None
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._server = None

    def _produce(self):
        while not self._stopped.wait(self.period_s):
            with self._lock:
                self.count += 1
                self.values["TEMP1"] = TEMP1_SWING[self.count % len(TEMP1_SWING)]
                self.values["TEMP2"] = list(NON_FINITE)[self.count // 5 % 3] if self.count % 5 == 0 else 1.5
                self.packet_s = self.received_s = time.time()

    def _answer(self, method, params):
        with self._lock:
            if method == "get_tlm_packet":
                # COSMOS's JSON gives a float it cannot carry as {json_class: Float, raw: ...}.
                rows = [[name, {"json_class": "Float", "raw": value} if value in NON_FINITE else value,
                         cosmos_limits(name, value)] for name, value in self.values.items()]
                return rows + [["PACKET_TIMESECONDS", self.packet_s, None], ["RECEIVED_TIMESECONDS", self.received_s, None],
                               ["RECEIVED_COUNT", self.count, None]]
            if method == "get_interface":
                return {"name": params[0], "state": self.state, "rxcnt": self.count * 5, "txcnt": len(self.sent)}
            if method in ("cmd", "cmd_no_hazardous_check"):
                target, command, parameters = params
                self.sent.append((method, target, command, parameters))
                self.values["CMD_ACPT_CNT"] += 1
                if command == "COLLECT":
                    self.values["COLLECTS"] += 1
                    self.values["DURATION"] = parameters["DURATION"]
                    self.values["COLLECT_TYPE"] = parameters["TYPE"]
                return None
        raise ValueError(f"no method {method}")

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.headers.get("Authorization") != fake.password:
                    self.send_response(401)
                    self.end_headers()
                    return
                try:
                    body = {"jsonrpc": "2.0", "id": request["id"], "result": fake._answer(request["method"], request["params"])}
                except ValueError as error:
                    body = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -1, "message": str(error)}}
                data = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json-rpc")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        threading.Thread(target=self._produce, daemon=True).start()
        return self

    @property
    def url(self):
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self):
        self._stopped.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
