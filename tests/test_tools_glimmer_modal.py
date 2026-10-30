"""tools/glimmer_modal.py, Muse Glimmer on Modal (the Director's ruling of 29 October 2026): read as text, so a clone
without Modal's client still runs it. Both endpoints sit behind proxy auth, the server image is pinned to one build,
the weights are the laptop's exact file, and no key, token or secret is in the file."""

import re

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
