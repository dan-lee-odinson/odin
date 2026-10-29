"""Opens VERDA's page from disk in headless Chrome or Edge, and reports what it did.

It drives the browser through the DevTools protocol on 127.0.0.1, with a small
WebSocket client written here (the standard library has none). It records every
request the page starts, every script error and console error, and can run a
line of JavaScript in the page to read what the page drew. It belongs to the
tests only; VERDA's page needs no browser but the reader's own.

    python tests/browser_probe.py [RUN_ID]    prints what one load of the page did
"""

import base64
import http.client
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def find_browser():
    named = os.environ.get("VERDA_BROWSER")
    for candidate in ([named] if named else []) + list(BROWSERS):
        if candidate and Path(candidate).exists():
            return candidate
    raise AssertionError("no Chrome or Edge found; set VERDA_BROWSER to one")


class _Socket:
    """Just enough of RFC 6455 for one DevTools connection."""

    def __init__(self, port, path):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        request = ("GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, port, key))
        self.sock.sendall(request.encode())
        reply = b""
        while b"\r\n\r\n" not in reply:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("DevTools closed the connection during the handshake")
            reply += chunk
        head, _, self.buffer = reply.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError("DevTools refused the WebSocket: %r" % head[:200])

    def send(self, text):
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _read(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("DevTools closed the connection")
            self.buffer += chunk
        out, self.buffer = self.buffer[:n], self.buffer[n:]
        return out

    def receive(self):
        message = b""
        while True:
            first, second = self._read(2)
            opcode, n = first & 0x0F, second & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            if second & 0x80:
                mask = self._read(4)
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(self._read(n)))
            else:
                data = self._read(n)
            if opcode == 0x8:
                raise ConnectionError("DevTools closed the WebSocket")
            if opcode in (0x9, 0xA):
                continue
            message += data
            if first & 0x80:
                return message.decode("utf-8")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Page:
    """One headless browser with one page, recording what the page does."""

    def __init__(self):
        self.profile = tempfile.mkdtemp(prefix="verda-browser-")
        args = [find_browser(), "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", "--disable-extensions", "--window-size=1920,1080",
                "--remote-debugging-port=0", "--user-data-dir=" + self.profile, "about:blank"]
        self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = Path(self.profile, "DevToolsActivePort")
        deadline = time.time() + 30
        while not (port_file.exists() and port_file.read_text().strip()):
            if time.time() > deadline:
                self.close()
                raise AssertionError("the browser did not open its DevTools port")
            time.sleep(0.1)
        self.port = int(port_file.read_text().split()[0])
        target = None
        while target is None and time.time() < deadline:
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            connection.request("GET", "/json/list")
            listed = json.loads(connection.getresponse().read().decode())
            connection.close()
            target = next((t for t in listed if t.get("type") == "page"), None)
            if target is None:
                time.sleep(0.1)
        ws_path = "/" + target["webSocketDebuggerUrl"].split("/", 3)[3]
        self.ws = _Socket(self.port, ws_path)
        self.next_id = 0
        self.requests, self.errors, self.events = [], [], []
        for domain in ("Network", "Page", "Runtime", "Log"):
            self.call(domain + ".enable")

    def call(self, method, params=None, timeout=15):
        self.next_id += 1
        mine = self.next_id
        self.ws.send(json.dumps({"id": mine, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = json.loads(self.ws.receive())
            if message.get("id") == mine:
                if "error" in message:
                    raise AssertionError("%s failed: %s" % (method, message["error"]))
                return message.get("result", {})
            self._event(message)
        raise AssertionError("%s got no reply" % method)

    def _event(self, message):
        method, params = message.get("method"), message.get("params", {})
        self.events.append(method)
        if method == "Network.requestWillBeSent":
            self.requests.append(params["request"]["url"])
        elif method == "Runtime.exceptionThrown":
            details = params.get("exceptionDetails", {})
            self.errors.append("exception: %s" % (details.get("exception", {}).get("description") or details.get("text")))
        elif method == "Runtime.consoleAPICalled" and params.get("type") in ("error", "assert"):
            self.errors.append("console: %s" % " ".join(str(a.get("value", a.get("description"))) for a in params.get("args", [])))
        elif method == "Log.entryAdded" and params.get("entry", {}).get("level") == "error":
            self.errors.append("log: %s" % params["entry"].get("text"))

    def open(self, url, settle=2.0):
        self.call("Page.navigate", {"url": url})
        self.wait(settle)

    def wait(self, seconds):
        """Lets the page run, recording what it does meanwhile."""
        self.ws.sock.settimeout(0.2)
        end = time.time() + seconds
        try:
            while time.time() < end:
                try:
                    self._event(json.loads(self.ws.receive()))
                except socket.timeout:
                    pass
        finally:
            self.ws.sock.settimeout(10)

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            raise AssertionError("the page could not run %r: %s" % (expression[:80], result["exceptionDetails"].get("text")))
        return result["result"].get("value")

    def screenshot(self, path):
        data = self.call("Page.captureScreenshot", {"format": "png"})["data"]
        Path(path).write_bytes(base64.b64decode(data))

    def close(self):
        try:
            if getattr(self, "ws", None):
                try:
                    self.call("Browser.close", timeout=3)
                except (AssertionError, ConnectionError, OSError):
                    pass
                self.ws.close()
        finally:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            shutil.rmtree(self.profile, ignore_errors=True)


def page_url(page_dir, run_id, extra=""):
    return Path(page_dir, "index.html").resolve().as_uri() + "#run=" + run_id + extra


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _support
    run_id = sys.argv[1] if len(sys.argv) > 1 else _support.PRACTICE_RUNS[0]
    page = Page()
    try:
        page.open(page_url(_support.page_dir(), run_id))
        print("requests:", *page.requests, sep="\n  ")
        print("errors:", *(page.errors or ["none"]), sep="\n  ")
        print("lanes drawn:", page.evaluate("document.querySelectorAll('.lane-label').length"))
    finally:
        page.close()
