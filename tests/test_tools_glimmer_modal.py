"""tools/glimmer_modal.py, Muse Glimmer on Modal (the Director's ruling of 29 October 2026): read as text, so a clone
without Modal's client still runs it. Both endpoints sit behind proxy auth, the server image is pinned to one build,
the weights are the laptop's exact file, and no key, token or secret is in the file. Each endpoint runs one container
at most, and a container takes no call until its model has loaded (the Director's ruling of 31 October 2026): its
start-up code is run here without Modal, compiled from the file's own text."""

import ast
import http.server
import re
import threading
import time
import urllib.request

import pytest

from tests.repo_checks import REPO_ROOT

TOOL = REPO_ROOT / "tools" / "glimmer_modal.py"
LAPTOP_SHA256 = "4cc57c0f51040a226e5a72cc47b7613f7772950e460a665f7083de89f183f60e"   # D:\models\muse-glimmer's copy


def text():
    return TOOL.read_text(encoding="utf-8")


def test_every_endpoint_sits_behind_proxy_auth_and_scales_to_zero():
    # The H100, the A100 80 GB, and the H200 the Director had timed on 30 October 2026.
    source = text()
    assert len(re.findall(r"@modal\.web_server\([^)]*requires_proxy_auth=True[^)]*\)", source)) == 3
    assert "requires_proxy_auth=False" not in source
    assert source.count("min_containers=0)") == 3


def test_the_server_image_is_one_pinned_llama_cpp_build_at_or_after_b10353():
    builds = re.findall(r'LLAMA_IMAGE = "ghcr\.io/ggml-org/llama\.cpp:server-cuda-b(\d+)"', text())
    assert len(builds) == 1 and int(builds[0]) >= 10353   # the model card: b10344 and older lack the architecture


def test_the_weights_are_the_laptops_file_at_its_revision():
    source = text()
    assert f'SHA256 = "{LAPTOP_SHA256}"' in source
    assert 'REVISION = "b44f1072cf75e918a1b82a3a17b45c4389b076e7"' in source
    assert 'FILENAME = "Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf"' in source


def test_no_key_token_or_secret_is_in_the_file():
    source = text()
    assert re.findall(r"\b(?:ak|as|wk|ws)-[A-Za-z0-9]{8,}", source) == []
    assert 'os.environ["ODIN_MODAL_PROXY_KEY"]' in source and 'os.environ["ODIN_MODAL_PROXY_SECRET"]' in source


# -- one container, and no call before the model has loaded (the Director's ruling of 31 October 2026) -----------

def constants():
    """The file's constants given as plain literals."""
    found = {}
    for node in ast.parse(text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                found[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return found


def function(name, **names):
    """One function of the file, compiled from its text with the names it uses, so Modal is never imported."""
    node = next(n for n in ast.parse(text()).body if isinstance(n, ast.FunctionDef) and n.name == name)
    space = {**constants(), **names}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(TOOL), "exec"), space)
    return space[name]


def test_red_each_endpoint_runs_one_container_at_most():
    served = re.findall(r'@app\.function\(image=server_image, gpu="[^"]+",[^)]*\)', text())
    assert len(served) == 3 and all("max_containers=1," in block for block in served)


def test_red_the_server_starts_as_before_and_returns_only_once_its_model_has_loaded():
    calls = []

    class Os:
        path = type("path", (), {"exists": staticmethod(lambda p: p == "/app/llama-server"),
                                 "join": staticmethod(lambda *parts: "/".join(parts))})

    class Subprocess:
        @staticmethod
        def Popen(argv):
            calls.append(("started", argv))

    start = function("_llama_server", os=Os, subprocess=Subprocess,
                     wait_until_loaded=lambda url: calls.append(("waited", url)))
    assert start() is None
    assert calls == [
        ("started", ["/app/llama-server", "-m", "/weights/Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf", "--jinja",
                     "-ngl", "999", "-fa", "on", "-c", "131072", "-np", "1", "--host", "0.0.0.0", "--port", "8080"]),
        ("waited", "http://127.0.0.1:8080/health")]


@pytest.fixture
def llama():
    """A stand-in for llama.cpp's health check on a local port: it answers each status in turn, then 503."""
    statuses, asked = [], []

    class Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            asked.append(self.path)
            self.send_response(statuses.pop(0) if statuses else 503)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/health", statuses, asked
    server.shutdown()
    server.server_close()


def test_red_the_start_up_waits_through_503_until_the_health_check_answers_200(llama):
    url, statuses, asked = llama
    statuses.extend([503, 503, 503, 200])
    wait = function("wait_until_loaded", urllib=urllib, time=time)
    assert wait(url, sleep=lambda s: None) is None
    assert asked == ["/health"] * 4


def test_red_the_start_up_gives_up_once_its_time_is_out(llama):
    url, statuses, asked = llama
    clock = iter([0.0, 450.0, 900.0])
    wait = function("wait_until_loaded", urllib=urllib, time=time)
    with pytest.raises(TimeoutError, match="model not loaded after 900 s"):
        wait(url, sleep=lambda s: None, monotonic=lambda: next(clock))
    assert asked == ["/health"] * 2
