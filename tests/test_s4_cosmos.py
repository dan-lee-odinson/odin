"""ODIN's COSMOS as its own Compose project (00_HANDOFF.md §3.4, S4): named odin, on ports no other install
holds, on OpenC3 COSMOS 7.2.1 as HUGINN pins it, with HUGINN's files read and never written, and no
command that could remove a volume. Nothing here needs Docker running; the merge test needs only the
docker CLI."""

import io
import json
import re
import shutil
import subprocess

import pytest
import yaml

from connector import cosmos
from wrapper.huginn import HUGINN

GROUND = yaml.safe_load((HUGINN / "defs" / "ground.yaml").read_text(encoding="utf-8"))
OTHER_INSTALLS = set(GROUND["deployment"]["host_ports"].values()) | set(GROUND["deployment"]["reserved_by_training_demo"])
DUMMY = {name: f"dummy-{number:02d}-value" for number, name in enumerate(cosmos.CREDENTIALS)}


def settings():
    return cosmos.render_settings(cosmos.SETTINGS_TEMPLATE.read_text(encoding="utf-8"))


def test_every_compose_command_names_the_odin_project_and_both_files():
    command = cosmos.compose("up", "-d")
    assert command[:4] == ["docker", "compose", "-p", "odin"]
    assert command.count("-f") == 2 and str(cosmos.COMPOSE_FILES[0]) in command and str(cosmos.COMPOSE_FILES[1]) in command
    assert cosmos.COMPOSE_FILES[0] == HUGINN / "gnd" / "openc3" / "compose.yaml"


@pytest.mark.parametrize("args", [("down", "-v"), ("down", "--volumes"), ("rm", "-f"), ("system", "prune")])
def test_red_no_compose_command_can_remove_a_volume(args):
    with pytest.raises(ValueError):
        cosmos.compose(*args)


def test_odins_ports_are_not_huginns_or_the_demos():
    assert OTHER_INSTALLS == {2910, 2953, 2900, 2943}
    assert not set(cosmos.WEB_PORTS) & OTHER_INSTALLS


def test_the_settings_are_huginns_with_the_project_named_odin_and_no_credential():
    text = settings()
    pairs = dict(line.split("=", 1) for line in text.splitlines())
    assert pairs["COMPOSE_PROJECT_NAME"] == "odin"
    assert pairs["OPENC3_TAG"] == "7.2.1"
    assert pairs["OPENC3_EXTERNAL_URL"] == "http://localhost:2920"
    assert not set(pairs) & set(cosmos.CREDENTIALS)
    assert cosmos.GENERATED not in text and "OPENC3_DEMO" not in pairs


def test_red_a_template_that_sets_the_demo_is_refused():
    with pytest.raises(ValueError):
        cosmos.render_settings("COMPOSE_PROJECT_NAME=huginn\nOPENC3_DEMO=0\n")


def test_the_acl_holds_hashes_and_never_a_password():
    acl = cosmos.render_acl(cosmos.ACL_TEMPLATE.read_text(encoding="utf-8"), DUMMY)
    assert all(line.startswith("user ") for line in acl.splitlines())
    for name in ("OPENC3_REDIS_PASSWORD", "OPENC3_SR_REDIS_PASSWORD", "OPENC3_REDIS_ADMIN_PASSWORD"):
        assert DUMMY[name] not in acl
    assert f"user {DUMMY['OPENC3_REDIS_USERNAME']} on #" in acl


def test_red_an_acl_placeholder_left_unfilled_is_refused():
    with pytest.raises(ValueError):
        cosmos.render_acl("user __NEW_USER__ on nopass\n", DUMMY)


def test_credentials_are_read_under_odins_names_only():
    kept = {cosmos.kept_name(name): value for name, value in DUMMY.items()}
    assert cosmos.credentials(kept, user_environment=lambda name: None) == DUMMY
    assert all(name.startswith("ODIN_COSMOS_") for name in kept)


def test_red_missing_credentials_are_named_and_no_value_is_shown():
    kept = {cosmos.kept_name(name): value for name, value in DUMMY.items()}
    del kept["ODIN_COSMOS_REDIS_PASSWORD"]
    with pytest.raises(SystemExit) as stopped:
        cosmos.credentials(kept, user_environment=lambda name: None)
    assert "ODIN_COSMOS_REDIS_PASSWORD" in str(stopped.value)
    assert not any(value in str(stopped.value) for value in DUMMY.values())


def test_made_credentials_are_fresh_and_complete():
    one, two = cosmos.make_credentials(), cosmos.make_credentials()
    assert set(one) == {cosmos.kept_name(name) for name in cosmos.CREDENTIALS}
    assert not set(one.values()) & set(two.values())


def test_red_up_stops_when_another_install_holds_the_ports(monkeypatch, tmp_path):
    kept = {cosmos.kept_name(name): value for name, value in DUMMY.items()}
    ran = []
    monkeypatch.setattr(cosmos.os, "environ", {**kept, "LOCALAPPDATA": str(tmp_path)})
    monkeypatch.setattr(cosmos, "ports_held", lambda: [2920])
    monkeypatch.setattr(cosmos, "_ours_running", lambda env: False)
    monkeypatch.setattr(cosmos, "_run", lambda command, env=None: ran.append(command) or 0)
    with pytest.raises(SystemExit) as stopped:
        cosmos.up()
    assert "2920" in str(stopped.value) and ran == []


def test_up_downloads_nothing(monkeypatch, tmp_path):
    kept = {cosmos.kept_name(name): value for name, value in DUMMY.items()}
    ran = []
    monkeypatch.setattr(cosmos.os, "environ", {**kept, "LOCALAPPDATA": str(tmp_path)})
    monkeypatch.setattr(cosmos, "ports_held", lambda: [])
    monkeypatch.setattr(cosmos, "_run", lambda command, env=None: ran.append(command) or 0)
    assert cosmos.up() == 0
    [command] = ran
    assert command[-4:] == ["up", "-d", "--pull", "never"]


def test_the_plugin_is_built_outside_its_read_only_folder_and_dials_the_link():
    build, variables, load = cosmos.plugin_commands()
    assert all(c[:4] == ["docker", "compose", "-p", "odin"] and c[c.index("exec"):][:3] == ["exec", "-T",
               "openc3-cosmos-cmd-tlm-api"] for c in (build, variables, load))
    assert build[-1] == ("cd /plugins/openc3-cosmos-huginn && "
                         "gem build openc3-cosmos-huginn.gemspec -o /tmp/openc3-cosmos-huginn-0.5.gem")
    assert 'plugin["variables"]["huginn_sim_port"] = "8713"' in variables[-1]
    assert load[-5:] == ["/openc3/bin/openc3cli", "load", "/tmp/openc3-cosmos-huginn-0.5.gem", "DEFAULT",
                         cosmos.PLUGIN_HASH]
    assert "7801" not in " ".join(build + variables + load)


def test_the_plugin_is_loaded_with_local_mode_off_so_nothing_is_copied_into_huginns_folder():
    load = cosmos.plugin_commands()[-1]
    assert load[load.index("exec") + 3:][:4] == ["env", "-u", "OPENC3_LOCAL_MODE", "ruby"]


def test_odins_code_calls_cosmos_on_the_address_it_is_published_on(monkeypatch):
    from tests import live_s4_pass
    published = re.findall(r'"([0-9.]+):2920:2900"', cosmos.COMPOSE_FILES[1].read_text(encoding="utf-8"))
    assert published == ["127.0.0.1"] and cosmos.API_URL == "http://127.0.0.1:2920"
    seen = []

    def urlopen(request, timeout):
        seen.append(request.full_url)
        return io.BytesIO(b'{"jsonrpc": "2.0", "result": 409, "id": 1}')

    monkeypatch.setattr(live_s4_pass, "credentials", lambda: DUMMY)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    assert live_s4_pass.Cosmos().tlm("CDH_MET") == 409
    assert seen == ["http://127.0.0.1:2920/openc3-api/api"]


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not on PATH")
def test_the_merged_project_is_odins_alone(tmp_path):
    (tmp_path / "settings.env").write_text(settings(), encoding="utf-8")
    (tmp_path / "users.acl").write_text("user default off\n", encoding="utf-8")
    result = subprocess.run(cosmos.compose("config", "--format", "json", folder=tmp_path),
                            env=cosmos.environment(DUMMY, tmp_path), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr.splitlines()[-1:]
    merged = json.loads(result.stdout)
    assert merged["name"] == "odin"
    published = [(p["host_ip"], int(p["published"])) for s in merged["services"].values() for p in s.get("ports", [])]
    assert sorted(published) == [("127.0.0.1", 2920), ("127.0.0.1", 2963)]
    plugins = [v for s in merged["services"].values() for v in s.get("volumes", []) if v["target"] == "/plugins"]
    assert len(plugins) == 4 and all(v.get("read_only") for v in plugins)
    assert all(v["name"].startswith("odin_") for v in merged["volumes"].values())
    assert "OPENC3_DEMO" not in json.dumps(merged)
    assert subprocess.run(["git", "-C", str(HUGINN), "status", "--porcelain", "--ignored"],
                          capture_output=True, text=True).stdout == ""
