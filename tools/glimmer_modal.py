"""Muse Glimmer on Modal: the onboard seat's fallback (the Director's ruling of 29 October 2026, should Glimmer miss
60 s a decision on the laptop in M5; Fireworks is the backup if Modal won't serve it). Outside odin/: Muse Code's
adapter calls this endpoint; it never runs this file.

The laptop's exact weights, Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf from meta-models/Muse-Glimmer-30B-GGUF at
revision b44f1072, downloaded once into a Modal Volume and checked against the laptop copy's SHA-256. They are served
by llama.cpp's own CUDA server image, pinned at build b11977 (the model card asks for b10353 or newer), through its
OpenAI-compatible API with JSON-schema output, behind Modal's proxy auth: every request carries the Modal-Key and
Modal-Secret headers of a proxy-auth token. One endpoint per GPU, so each can be timed; the one the Director picks
flies. Each scales to zero when idle, and is kept warm only while a run needs it, so a cold start never lands inside
a turn.

Keys and tokens come from environment variables only, never from a file: Modal's own client reads MODAL_TOKEN_ID and
MODAL_TOKEN_SECRET, and the proxy-auth token is ODIN_MODAL_PROXY_KEY and ODIN_MODAL_PROXY_SECRET. Nothing here prints
or writes any of them.

    python tools/glimmer_modal.py deploy              deploy the app (both endpoints, scaled to zero)
    python tools/glimmer_modal.py download            once: the weights into the Volume, checked by SHA-256
    python tools/glimmer_modal.py warm <gpu>          keep one container of that endpoint up, and wait until it serves
    python tools/glimmer_modal.py cold <gpu>          let it scale to zero again
    python tools/glimmer_modal.py url <gpu>           the endpoint's URL
<gpu> is h100 or a100-80gb.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import modal

APP_NAME = "odin-glimmer"
REPO_ID = "meta-models/Muse-Glimmer-30B-GGUF"
REVISION = "b44f1072cf75e918a1b82a3a17b45c4389b076e7"
FILENAME = "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf"
SHA256 = "4cc57c0f51040a226e5a72cc47b7613f7772950e460a665f7083de89f183f60e"   # the laptop's copy, D:\models\muse-glimmer
LLAMA_IMAGE = "ghcr.io/ggml-org/llama.cpp:server-cuda-b11977"
WEIGHTS_DIR = "/weights"
PORT = 8080
CONTEXT = 131072   # the model's own context; one slot (-np 1), so one request has all of it
IDLE_S = 120       # seconds a container stays up after its last request before scaling to zero
FUNCTIONS = {"h100": "serve_h100", "a100-80gb": "serve_a100_80gb"}

app = modal.App(APP_NAME)
weights = modal.Volume.from_name("odin-glimmer-weights", create_if_missing=True)
download_image = modal.Image.debian_slim(python_version="3.12").pip_install("huggingface_hub==0.26.2")
server_image = modal.Image.from_registry(LLAMA_IMAGE, add_python="3.12").entrypoint([])


@app.function(image=download_image, volumes={WEIGHTS_DIR: weights}, timeout=3600)
def download():
    from huggingface_hub import hf_hub_download
    path = os.path.join(WEIGHTS_DIR, FILENAME)
    if not os.path.exists(path):
        hf_hub_download(repo_id=REPO_ID, filename=FILENAME, revision=REVISION, local_dir=WEIGHTS_DIR)
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            digest.update(block)
    if digest.hexdigest() != SHA256:
        os.remove(path)
        weights.commit()
        raise RuntimeError(f"{FILENAME} hashes to {digest.hexdigest()}, not the laptop copy's {SHA256}; removed")
    weights.commit()
    return {"file": FILENAME, "bytes": os.path.getsize(path), "sha256": digest.hexdigest()}


def _llama_server():
    binary = next(p for p in ("/app/llama-server", "/usr/local/bin/llama-server", "/llama-server") if os.path.exists(p))
    subprocess.Popen([binary, "-m", os.path.join(WEIGHTS_DIR, FILENAME), "--jinja", "-ngl", "999", "-fa", "on",
                      "-c", str(CONTEXT), "-np", "1", "--host", "0.0.0.0", "--port", str(PORT)])


@app.function(image=server_image, gpu="H100", volumes={WEIGHTS_DIR: weights}, timeout=3600,
              scaledown_window=IDLE_S, min_containers=0)
@modal.concurrent(max_inputs=4)
@modal.web_server(port=PORT, startup_timeout=900, requires_proxy_auth=True)
def serve_h100():
    _llama_server()


@app.function(image=server_image, gpu="A100-80GB", volumes={WEIGHTS_DIR: weights}, timeout=3600,
              scaledown_window=IDLE_S, min_containers=0)
@modal.concurrent(max_inputs=4)
@modal.web_server(port=PORT, startup_timeout=900, requires_proxy_auth=True)
def serve_a100_80gb():
    _llama_server()


def proxy_headers():
    """The proxy-auth headers, from the environment only."""
    return {"Modal-Key": os.environ["ODIN_MODAL_PROXY_KEY"], "Modal-Secret": os.environ["ODIN_MODAL_PROXY_SECRET"]}


def endpoint(gpu):
    return modal.Function.from_name(APP_NAME, FUNCTIONS[gpu]).get_web_url()


def wait_until_serving(gpu, timeout_s=1200):
    url = endpoint(gpu) + "/health"
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=proxy_headers()), timeout=30) as reply:
                if reply.status == 200:
                    return time.monotonic() - started
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(10)
    raise TimeoutError(f"{gpu}: not serving after {timeout_s} s")


def warm_up(gpu, words=12000):
    """One throwaway request of a long prompt once the server answers: llama.cpp's first long prefill on a fresh
    container runs at about a third of its later speed, so it lands here, before a run, never inside its first turn."""
    body = {"model": FILENAME, "max_tokens": 16,
            "messages": [{"role": "user", "content": "Warm-up only; answer OK. " + "telemetry frame " * words}]}
    request = urllib.request.Request(endpoint(gpu) + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json", **proxy_headers()})
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=600) as reply:
        reply.read()
    return time.monotonic() - started


def main(argv):
    command, *rest = argv or ["help"]
    if command == "deploy":
        with modal.enable_output():
            app.deploy()
        return 0
    if command == "download":
        with modal.enable_output(), app.run():
            print(download.remote())
        return 0
    if command in ("warm", "cold", "url"):
        gpu = rest[0]
        if command == "url":
            print(endpoint(gpu))
            return 0
        modal.Function.from_name(APP_NAME, FUNCTIONS[gpu]).autoscaler.update(min_containers=1 if command == "warm" else 0)
        if command == "warm":
            print(f"{gpu}: serving after {wait_until_serving(gpu):.0f} s; warmed up in {warm_up(gpu):.0f} s")
        else:
            print(f"{gpu}: scales to zero once idle for {IDLE_S} s")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
