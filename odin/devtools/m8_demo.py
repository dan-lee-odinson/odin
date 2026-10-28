"""Stand-in demo for M8: fake harness/BALDUR-0/log on the ports.yaml
ports in this process; ODIN's start command as its own subprocess.

    python -m odin.devtools.m8_demo

Demo only: a throwaway keypair in a temp folder, stand_in model, no paid
call. Not part of any scored run.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from odin.devtools.fake_harness import FakeServices  # noqa: E402
from odin.devtools.fixtures import bundle_bytes, make_m3_bundle  # noqa: E402
from odin.loop import signing  # noqa: E402


def _serve(services, port):
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

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    config = yaml.safe_load((REPO_ROOT / "config" / "ports.yaml").read_text())
    ports = config["ports"]
    tmp = Path(tempfile.mkdtemp(prefix="odin-m8-demo-"))
    priv, pub = tmp / "odin_key", tmp / "odin.pub"
    signing.generate_keypair_files(priv, pub)
    bundles = []
    for turn in (1, 2, 3):
        bundle = make_m3_bundle()
        bundle["turn_id"] = turn
        bundles.append(bundle_bytes(bundle))
    services = FakeServices(bundles=bundles, public_key_path=pub)
    servers = [_serve(services, ports[name]) for name in ("harness", "baldur0", "log")]
    env = dict(os.environ, ODIN_KEY_PATH=str(priv))
    for name in [n for n in env if n.startswith("ODIN_COSMOS_")]:
        del env[name]
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "odin.run_odin", "stand_in"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120)
        print(proc.stdout, end="")
        print(proc.stderr, end="", file=sys.stderr)
        agent_inputs = [r for r in services.log_records if r["type"] == "AGENT_INPUT"]
        print(f"fake harness saw {len(agent_inputs)} turn(s); "
              f"ODIN exit code {proc.returncode}")
        return proc.returncode
    finally:
        for server in servers:
            server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
