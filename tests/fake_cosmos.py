"""A stand-in for ODIN's COSMOS in the ground seat's tests (S5): HUGINN_INT's side of the link, and the calls of
COSMOS's JSON-RPC API the connector makes, answered in the shapes COSMOS 7.2.1 gives them.

It dials the link as HUGINN_INT does, cuts each frame by its LENGTH field and decodes it as COSMOS's packet
definition does, and writes each command it is sent as COSMOS writes it. Like COSMOS, it refuses a hazardous
command sent through the ordinary send, and keeps its packet count from before a run. It records every
command it is asked to send, so a test can show what reached COSMOS.
"""

import json
import struct
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from wrapper.frames import CODEC, COMMANDS, HEADER_SIZE, POINTS, decode_frame, encode_command, limit_state


class FakeCosmos:
    def __init__(self, link_address, password, *, earlier=None, dial=True, decode=True):
        """link_address: the (host, port) the run's link listens on. earlier: a frame COSMOS holds from an
        earlier run, with its count, as (frame, received_count). dial: whether HUGINN_INT dials the link at all.
        decode: whether frames that arrive are decommutated; without it COSMOS stays connected and shows none."""
        self.password = password
        self.link_address = link_address
        self.sent = []   # every command asked for, as (method, command, parameters), refused ones included
        self.frame, self.count = earlier if earlier else (None, 0)
        self.received_s = time.time() if earlier else None
        self.state, self.rxcnt = "ATTEMPTING", 0
        self.dial, self.decode = dial, decode
        self._lock = threading.Lock()
        self._socket = None
        self._stopped = threading.Event()
        self._server = None

    # -- HUGINN_INT ----------------------------------------------------------------------------------

    def _connect(self):
        while not self._stopped.is_set():
            if not self.dial:
                time.sleep(0.05)
                continue
            try:
                sock = socket.create_connection(self.link_address, timeout=1)
            except OSError:
                time.sleep(0.05)
                continue
            sock.settimeout(None)
            with self._lock:
                self._socket, self.state = sock, "CONNECTED"
            self._read(sock)
            with self._lock:
                self._socket, self.state = None, "ATTEMPTING"

    def _read(self, sock):
        buffer = b""
        while not self._stopped.is_set():
            try:
                data = sock.recv(4096)
            except OSError:
                return
            if not data:
                return
            buffer += data
            while len(buffer) >= HEADER_SIZE:
                _, length = struct.unpack_from(CODEC.header_format, buffer, 0)
                if len(buffer) < HEADER_SIZE + length:
                    break
                frame = decode_frame(buffer[:HEADER_SIZE + length])
                buffer = buffer[HEADER_SIZE + length:]
                if not self.decode:
                    continue
                with self._lock:
                    self.frame, self.received_s = frame, time.time()
                    self.count += 1
                    self.rxcnt += 1

    # -- the API -------------------------------------------------------------------------------------

    def _answer(self, method, params):
        with self._lock:
            if method == "get_tlm_packet":
                values = self.frame or {name: None for name in POINTS}
                items = [[name, value, limit_state(name, value) if self.frame else None] for name, value in values.items()]
                return items + [["RECEIVED_TIMESECONDS", self.received_s, None], ["RECEIVED_COUNT", self.count, None]]
            if method == "get_interface":
                return {"name": params[0], "state": self.state, "rxcnt": self.rxcnt, "txcnt": len(self.sent)}
            if method == "get_cmd_hazardous":
                return COMMANDS[params[1]]["hazardous"]
            if method in ("cmd", "cmd_no_hazardous_check"):
                _, command, parameters = params
                self.sent.append((method, command, parameters))
                if method == "cmd" and COMMANDS[command]["hazardous"]:
                    raise ValueError(f"HazardousError: HUGINN {command} is Hazardous")
                if self._socket is not None:
                    self._socket.sendall(encode_command(command, {k.lower(): v for k, v in parameters.items()}))
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
                    body = {"jsonrpc": "2.0", "id": request["id"],
                            "result": fake._answer(request["method"], request["params"])}
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
        threading.Thread(target=self._connect, daemon=True).start()
        return self

    @property
    def url(self):
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self):
        self._stopped.set()
        with self._lock:
            if self._socket is not None:
                self._socket.close()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
