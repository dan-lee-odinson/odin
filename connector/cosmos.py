"""ODIN's COSMOS: OpenC3 COSMOS 7.2.1 with HUGINN's plugin, run as its own Compose project, odin
(00_HANDOFF.md §3.4; S4, S5).

    python -m connector.cosmos credentials   once: make COSMOS's credentials, kept as environment variables
    python -m connector.cosmos up            start it
    python -m connector.cosmos plugin        once it is up: install HUGINN's plugin, dialing the link
    python -m connector.cosmos demo-load     before a phase-1 run: load COSMOS's demo plugin, its INST target only
    python -m connector.cosmos demo-unload   after it: unload the demo plugin
    python -m connector.cosmos status        its containers
    python -m connector.cosmos stop          stop its containers, keeping everything
    python -m connector.cosmos down          remove its containers and network, keeping its volumes

Every Compose command here names the project odin, with HUGINN's compose file unchanged and
connector/compose/odin.yaml over it. None removes a volume: there is no down -v, volume rm or prune,
here or anywhere (00_HANDOFF.md §3.4). Before starting, it checks that no other install holds ODIN's
COSMOS ports, and stops rather than touch one that does.

The settings file and the Redis ACL are rendered from HUGINN's own templates, read as they are, into a
folder outside the repository. The settings file holds no credential: Compose passes each one through
from the environment it runs in, which this module builds from ODIN_COSMOS_* variables.
"""

import hashlib
import os
import re
import secrets
import socket
import subprocess
import sys
from pathlib import Path

from wrapper.huginn import HUGINN
from wrapper.link import link_address

PROJECT = "odin"
GROUND = HUGINN / "gnd" / "openc3"
COMPOSE_FILES = (GROUND / "compose.yaml", Path(__file__).resolve().parent / "compose" / "odin.yaml")
SETTINGS_TEMPLATE = GROUND / ".env.template"
ACL_TEMPLATE = GROUND / "openc3-redis" / "users.acl.template"
WEB_PORTS = (2920, 2963)
EXTERNAL_URL = f"http://localhost:{WEB_PORTS[0]}"
# Where ODIN's code calls COSMOS's API: the address odin.yaml publishes it on, 127.0.0.1 alone. "localhost"
# names ::1 first, and on Windows each call then waits 2 s for that connection to be refused (found in
# S4's live pass, 27 October 2026). EXTERNAL_URL stays COSMOS's own setting, for browsers.
API_URL = f"http://127.0.0.1:{WEB_PORTS[0]}"
NEVER = ("-v", "--volumes", "prune", "rm")

# COSMOS's credential settings, as its services read them. Each is kept under an ODIN_COSMOS_ name, never
# its own: an OPENC3_ name in the Director's environment would override his HUGINN install's .env.
CREDENTIALS = ("OPENC3_TSDB_USERNAME", "OPENC3_TSDB_PASSWORD", "OPENC3_REDIS_USERNAME", "OPENC3_REDIS_PASSWORD",
               "OPENC3_BUCKET_USERNAME", "OPENC3_BUCKET_PASSWORD", "OPENC3_SR_REDIS_USERNAME",
               "OPENC3_SR_REDIS_PASSWORD", "OPENC3_SR_BUCKET_USERNAME", "OPENC3_SR_BUCKET_PASSWORD",
               "OPENC3_REDIS_ADMIN_PASSWORD", "OPENC3_SERVICE_PASSWORD", "SECRET_KEY_BASE")
GENERATED = "__GENERATE__"
PLACEHOLDER = re.compile(r"__[A-Z0-9_]+__")

# COSMOS's credentials live only as the Director's user environment variables, ODIN_COSMOS_*, made once
# by the credentials command without being shown (the Director's ruling on U38, 27 October 2026). ODIN
# holds no ground-system credential (CONTRACT.md §9): Muse Code's start command removes every
# ODIN_COSMOS_* variable, and whatever launches ODIN's process passes it no ODIN_COSMOS_* or OPENC3_*
# variable.


def kept_name(name):
    return "ODIN_COSMOS_" + name.removeprefix("OPENC3_")


def state_folder():
    """Where the rendered settings and ACL go: outside the repository and outside OneDrive."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "odin" / "cosmos"


# -- credentials -------------------------------------------------------------------------------

def _user_environment(name):
    """A user environment variable set after this process started (Windows keeps them in the registry)."""
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def credentials(environ=None, user_environment=_user_environment):
    """{OPENC3 name: value} from the ODIN_COSMOS_* variables. Raises naming any that are missing, never
    a value."""
    environ = os.environ if environ is None else environ
    found = {name: environ.get(kept_name(name)) or user_environment(kept_name(name)) for name in CREDENTIALS}
    missing = [kept_name(name) for name, value in found.items() if not value]
    if missing:
        raise SystemExit(f"missing {', '.join(missing)}; run python -m connector.cosmos credentials once")
    return found


def make_credentials():
    """Fresh credentials, {ODIN_COSMOS name: value}."""
    made = {}
    for name in CREDENTIALS:
        if name.endswith("USERNAME"):
            made[kept_name(name)] = "odin_" + secrets.token_hex(4)
        elif name.startswith("SECRET"):   # Rails's secret key base, 128 hex characters
            made[kept_name(name)] = secrets.token_hex(64)
        else:
            made[kept_name(name)] = secrets.token_urlsafe(24)
    return made


def keep_credentials(made):
    """Store them as the user's environment variables. Windows only; nothing is printed or written to a
    file."""
    import ctypes
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        for name, value in made.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    # Tell running programs that the environment changed, so new terminals see the variables.
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)


# -- what Compose is given ---------------------------------------------------------------------

# The one COSMOS setting where ODIN's COSMOS differs from HUGINN's (the Director's ruling, 27 October 2026).
# Local mode copies installed plugins, edited targets and saved tool settings into /plugins/DEFAULT, which
# in ODIN's COSMOS is HUGINN's plugin folder, mounted read-only, so every such copy would fail. HUGINN's
# template says to disable it by leaving the variable out, never by setting it to 0.
LOCAL_MODE = "OPENC3_LOCAL_MODE"


def render_settings(template):
    """HUGINN's .env.template as ODIN's settings: the project named odin, its own address, local mode off,
    and every credential line left out. Comments and blank lines are dropped."""
    lines = []
    for line in template.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, _, value = line.partition("=")
        if value == GENERATED or name in CREDENTIALS or name == LOCAL_MODE:
            continue
        if name == "COMPOSE_PROJECT_NAME":
            value = PROJECT
        elif name == "OPENC3_EXTERNAL_URL":
            value = EXTERNAL_URL
        lines.append(f"{name}={value}")
    if any(line.startswith("OPENC3_DEMO=") for line in lines):
        raise ValueError("OPENC3_DEMO is set; any value installs COSMOS's demo plugin")
    return "\n".join(lines) + "\n"


def render_acl(template, found):
    """HUGINN's Redis ACL template with each user's name and the SHA-256 of its password. Only user
    lines are kept: Valkey refuses comments."""
    def sha(name):
        return hashlib.sha256(found[name].encode("utf-8")).hexdigest()

    filled = {"__REDIS_USERNAME__": found["OPENC3_REDIS_USERNAME"], "__SR_USERNAME__": found["OPENC3_SR_REDIS_USERNAME"],
              "__REDIS_PASSWORD_SHA256__": sha("OPENC3_REDIS_PASSWORD"),
              "__SR_PASSWORD_SHA256__": sha("OPENC3_SR_REDIS_PASSWORD"),
              "__ADMIN_PASSWORD_SHA256__": sha("OPENC3_REDIS_ADMIN_PASSWORD")}
    lines = [line for line in template.splitlines() if line.startswith("user ")]
    text = "\n".join(lines) + "\n"
    for placeholder, value in filled.items():
        text = text.replace(placeholder, value)
    if PLACEHOLDER.search(text):
        raise ValueError(f"the ACL template has a placeholder this module does not fill: {PLACEHOLDER.search(text)[0]}")
    return text


def compose(*args, folder=None):
    """The docker compose command for ODIN's project. Refuses anything that would remove a volume."""
    refused = [arg for arg in args if arg in NEVER]
    if refused:
        raise ValueError(f"refused: {' '.join(refused)} could remove a volume; ODIN's COSMOS keeps its volumes")
    folder = folder or state_folder()
    files = [part for path in COMPOSE_FILES for part in ("-f", str(path))]
    return ["docker", "compose", "-p", PROJECT, *files, "--env-file", str(folder / "settings.env"), *args]


def environment(found, folder=None):
    """The environment Compose runs in: this process's, with the credentials under their COSMOS names
    and the paths of the rendered files."""
    folder = folder or state_folder()
    return {**os.environ, **found, "ODIN_COSMOS_SETTINGS": (folder / "settings.env").as_posix(),
            "ODIN_COSMOS_ACL": (folder / "users.acl").as_posix()}


def ports_held(ports=WEB_PORTS):
    """The ports something on this machine already listens on."""
    held = []
    for port in ports:
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                held.append(port)
    return held


def _run(command, env=None):
    return subprocess.run(command, env=env, check=False).returncode


def _ours_running(env):
    result = subprocess.run(compose("ps", "-q", "openc3-traefik"), env=env, capture_output=True, text=True)
    return bool(result.stdout.strip())


def up():
    found = credentials()
    folder = state_folder()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "settings.env").write_text(render_settings(SETTINGS_TEMPLATE.read_text(encoding="utf-8")),
                                         encoding="utf-8", newline="\n")
    (folder / "users.acl").write_text(render_acl(ACL_TEMPLATE.read_text(encoding="utf-8"), found),
                                      encoding="utf-8", newline="\n")
    env = environment(found, folder)
    held = ports_held()
    if held and not _ours_running(env):
        raise SystemExit(f"ports {held} are already held by something other than ODIN's COSMOS; "
                         f"nothing was started or stopped. Ask the Director before going on.")
    # The COSMOS 7.2.1 images are already on this machine; nothing is downloaded.
    return _run(compose("up", "-d", "--pull", "never"), env)


# -- HUGINN's plugin ---------------------------------------------------------------------------

PLUGIN_FOLDER = "/plugins/openc3-cosmos-huginn"   # HUGINN's plugin folder, mounted read-only
PLUGIN_GEMSPEC = GROUND / "plugins" / "openc3-cosmos-huginn" / "openc3-cosmos-huginn.gemspec"
API_SERVICE = "openc3-cosmos-cmd-tlm-api"
PLUGIN_HASH = "/tmp/odin-huginn-plugin.json"


def plugin_gem():
    """The gem's path in the container, named by the version HUGINN's gemspec gives."""
    version = re.search(r's\.version\s*=\s*"([^"]+)"', PLUGIN_GEMSPEC.read_text(encoding="utf-8"))[1]
    return f"/tmp/openc3-cosmos-huginn-{version}.gem"


def plugin_commands(link_port=None):
    """Build HUGINN's plugin from its read-only folder into the container's /tmp, then load it with
    huginn_sim_port set to the link's port, so that HUGINN_INT dials the link and never HUGINN's own
    simulator on 7801. The plugin's other variables keep plugin.txt's defaults.

    The load runs with OPENC3_LOCAL_MODE unset. With local mode on, as HUGINN's settings have it, an install
    copies the plugin into /plugins/DEFAULT, which here is HUGINN's folder, read-only: the copy fails and
    the load exits 1 (found in S4's live pass, 27 October 2026). ODIN's settings now leave local mode off
    (LOCAL_MODE); the load unsets it as well, so a COSMOS started before that change installs the same way.
    The plugin is kept in ODIN's COSMOS's own volumes, as any plugin installed from the Admin tool is."""
    link_port = link_port or link_address()[1]
    gem, run_in_api = plugin_gem(), ("exec", "-T", API_SERVICE)
    variables = (f'require "json"; require "openc3"; require "openc3/models/plugin_model"; '
                 f'plugin = OpenC3::PluginModel.install_phase1("{gem}", scope: "DEFAULT"); '
                 f'plugin["variables"]["huginn_sim_port"] = "{link_port}"; '
                 f'File.write("{PLUGIN_HASH}", JSON.generate(plugin))')
    return [compose(*run_in_api, "sh", "-c", f"cd {PLUGIN_FOLDER} && gem build openc3-cosmos-huginn.gemspec -o {gem}"),
            compose(*run_in_api, "ruby", "-e", variables),
            compose(*run_in_api, "env", "-u", "OPENC3_LOCAL_MODE",
                    "ruby", "/openc3/bin/openc3cli", "load", gem, "DEFAULT", PLUGIN_HASH)]


def install_plugin():
    env = environment(credentials())
    for command in plugin_commands():
        returncode = _run(command, env)
        if returncode:
            return returncode
    return 0


# -- COSMOS's demo plugin, for phase 1 only -------------------------------------------------------

# The Director's ruling on U58 (28 October 2026): COSMOS's demo plugin is loaded into ODIN's COSMOS for a
# phase-1 run only and unloaded after each run, since its 1 Hz targets filled 117 GB in August; never into
# HUGINN's COSMOS, which nothing here addresses, every command naming the project odin. Only the INST target
# and its simulated interface, INST_INT, are loaded: the plugin's own variables leave out its other targets,
# its router and its microservices, and keep its logs for the shortest retention it offers. The gem is
# OpenC3's own, copied from its init image (tools/inst_dictionary.py fetch), and checked by its SHA-256.
DEMO_GEM_IN_CONTAINER = "/tmp/openc3-cosmos-demo-7.2.1.gem"
DEMO_HASH = "/tmp/odin-demo-plugin.json"
DEMO_PREFIX = "openc3-cosmos-demo-"
DEMO_VARIABLES = {"inst2_target_name": "", "example_target_name": "", "templated_target_name": "",
                  "system_target_name": "", "inst_router_name": "", "example_microservice_name": "",
                  "templated_microservice_name": "", "log_retain_time": "86400"}
_DEMO_NAMES = ('require "openc3"; require "openc3/models/plugin_model"; '
               f'puts OpenC3::PluginModel.names(scope: "DEFAULT").select {{ |n| n.start_with?("{DEMO_PREFIX}") }}')


def demo_load_commands(gem):
    """Copy the demo gem into the API container, set its variables, and load it with local mode unset, as
    HUGINN's plugin is loaded."""
    run_in_api = ("exec", "-T", API_SERVICE)
    settings = "; ".join(f'plugin["variables"]["{name}"] = "{value}"' for name, value in DEMO_VARIABLES.items())
    variables = (f'require "json"; require "openc3"; require "openc3/models/plugin_model"; '
                 f'plugin = OpenC3::PluginModel.install_phase1("{DEMO_GEM_IN_CONTAINER}", scope: "DEFAULT"); '
                 f'{settings}; File.write("{DEMO_HASH}", JSON.generate(plugin))')
    return [compose("cp", str(gem), f"{API_SERVICE}:{DEMO_GEM_IN_CONTAINER}"),
            compose(*run_in_api, "ruby", "-e", variables),
            compose(*run_in_api, "env", "-u", "OPENC3_LOCAL_MODE",
                    "ruby", "/openc3/bin/openc3cli", "load", DEMO_GEM_IN_CONTAINER, "DEFAULT", DEMO_HASH)]


def demo_unload_commands():
    """Unload every installed demo plugin."""
    return [compose("exec", "-T", API_SERVICE, "sh", "-c",
                    f"for name in $(ruby -e '{_DEMO_NAMES}'); do "
                    f"env -u OPENC3_LOCAL_MODE ruby /openc3/bin/openc3cli unload $name DEFAULT || exit 1; done")]


def demo_installed(env):
    """The demo plugins installed in ODIN's COSMOS, by name."""
    result = subprocess.run(compose("exec", "-T", API_SERVICE, "ruby", "-e", _DEMO_NAMES), env=env,
                            capture_output=True, text=True)
    return result.stdout.split()


def load_demo():
    from tools.inst_dictionary import GEM, GEM_SHA256, sha256
    if not GEM.exists() or sha256(GEM.read_bytes()) != GEM_SHA256:
        raise SystemExit(f"{GEM} is missing or not the demo plugin's {GEM_SHA256}; "
                         "python -m tools.inst_dictionary fetch copies it")
    env = environment(credentials())
    if demo_installed(env):
        raise SystemExit("the demo plugin is already loaded; unload it first")
    for command in demo_load_commands(GEM):
        returncode = _run(command, env)
        if returncode:
            return returncode
    return 0


def unload_demo():
    env = environment(credentials())
    for command in demo_unload_commands():
        returncode = _run(command, env)
        if returncode:
            return returncode
    return 1 if demo_installed(env) else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = argv[0] if argv else "status"
    if command == "credentials":
        if any(os.environ.get(kept_name(n)) or _user_environment(kept_name(n)) for n in CREDENTIALS):
            raise SystemExit("ODIN's COSMOS credentials already exist; nothing was changed")
        keep_credentials(make_credentials())
        print(f"made {len(CREDENTIALS)} ODIN_COSMOS_* user environment variables; their values were not shown")
        return 0
    if command == "up":
        return up()
    if command == "plugin":
        return install_plugin()
    if command == "demo-load":
        return load_demo()
    if command == "demo-unload":
        return unload_demo()
    if command in ("status", "stop", "down"):
        env = environment(credentials())
        return _run(compose({"status": "ps", "stop": "stop", "down": "down"}[command]), env)
    raise SystemExit(f"unknown command {command!r}; use credentials, up, plugin, demo-load, demo-unload, status, "
                     f"stop or down")


if __name__ == "__main__":
    sys.exit(main())
