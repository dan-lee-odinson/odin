"""Check phase 3's held-out files in ../sealed/ before they are sealed. Held out; writes nothing.

1. Every plan passes BALDUR-0's own plan checks, each scenario's plans form a valid chain, and every
   procedure and reference hash is a file in the repository or the phase-1 notes' placeholder.
2. The plans are identical but for their label, pass, span and window lines.
3. Nothing ODIN can read names or hints at a fault: file names, plan IDs, scenario IDs, every plan line,
   the procedures and the attachments the plans list.
4. HUGINN flies each scenario as written: its state at each contact and fault onset.
"""

import hashlib
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SEALED = HERE.parent / "sealed"
REPO = Path(__file__).resolve().parents[2]
HUGINN = REPO / "deps" / "huginn"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HUGINN))

from contract.validate import check  # noqa: E402
from gateway.plans import _chain_failure, _consistency, _protective_restrictions  # noqa: E402
from sim.scenario import Scenario  # noqa: E402
from wrapper.huginn import build  # noqa: E402

ZEROS = "sha256:" + "0" * 64
failures = []


def require(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        failures.append(what)


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


scenarios = {p.name.split(".")[0]: yaml.safe_load(p.read_text(encoding="utf-8"))
             for p in sorted(SEALED.glob("*.scenario.yaml"))}
plans = {p.stem: p for p in sorted(SEALED.glob("TYR0-*.yaml"))}

# --- 1. BALDUR-0's plan checks and the chains --------------------------------------------------------------
print("1. Plans and chains")
here = {sha(p.read_bytes()) for folder in (REPO / "inputs-pre-existing", REPO / "plans", REPO / "odin" / "study")
        for p in folder.rglob("*") if p.is_file()}
for name, path in plans.items():
    document = yaml.safe_load(path.read_bytes())
    problems = check("tyr0_plan", document) + _consistency(document) + _protective_restrictions(document)
    require(problems == [] and document["plan_id"] == name, f"{name}: well formed, protective commands untouched")
    listed = [r["sha256"] for r in document["procedures_in_force"] + document["references"]]
    require([s for s in listed if s != ZEROS and s not in here] == [], f"{name}: every hash is a repository file")
    require([r["name"] for r in document["references"] if r["sha256"] == ZEROS]
            == ["ODIN's phase-1 console notes (frozen after phase 1)"], f"{name}: only the phase-1 notes wait")
    for ref in document["procedures_in_force"]:
        on_disk = sha((REPO / "inputs-pre-existing" / "procedures" / f"v{ref['version']}" / f"{ref['id']}.md").read_bytes())
        require(on_disk == ref["sha256"] and ref["version"] == "0.3", f"{name}: {ref['id']} is v0.3 as placed")
for label, s in scenarios.items():
    chain = [yaml.safe_load(plans[Path(f).stem].read_bytes()) for f in s["plans"]]
    require(_chain_failure(chain) is None, f"{label}: its plans form a chain")
    require(chain[0]["valid_from_met_s"] == 0 and chain[-1]["valid_until_met_s"] == s["run"]["end_met_s"],
            f"{label}: the chain spans the run, 0 to {s['run']['end_met_s']}")
    windows = [(p["contact_window"]["aos_met_s"], p["contact_window"]["los_met_s"]) for p in chain]
    require(windows == [(c["aos_met_s"], c["los_met_s"]) for c in s["geometry"]["contacts"]],
            f"{label}: plan windows are the scenario's contacts")
    require(all(p["scenario_id"] == label for p in chain), f"{label}: every plan names it")
    require(Scenario(s["huginn"]).scenario_id == label, f"{label}: HUGINN loads its scenario")

# --- 2. Identical plans ------------------------------------------------------------------------------------------
print("2. Identical plans")
VARIABLE = re.compile(r"^(plan_id|scenario_id|pass_index|valid_from_met_s|valid_until_met_s|  aos_met_s|  los_met_s):")
bodies = {name: "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not VARIABLE.match(line))
          for name, path in plans.items()}
require(len(set(bodies.values())) == 1, "all seven plans are identical but for label, pass, span and window")


def without_label(name):
    return plans[name].read_text(encoding="utf-8").replace(name.split("-")[1], "HXX")


one = {without_label(n) for n in plans if "-C2-" not in n and not any(
    n == f"TYR0-{l}-C1-v1" for l, s in scenarios.items() if len(s["plans"]) == 2)}
require(len(one) == 1, "the one-contact plans are byte-identical but for their label")
two = {(without_label(f"TYR0-{l}-C1-v1"), without_label(f"TYR0-{l}-C2-v1"))
       for l, s in scenarios.items() if len(s["plans"]) == 2}
require(len(two) == 1, "the two-contact chains are byte-identical but for their label")

# --- 3. Clues -----------------------------------------------------------------------------------------------------
print("3. Clues in what ODIN can read")
CLUES = re.compile(r"(?i)latch|halt|upset|receiver|beacon|revok|revoc|restor|hand.?back|radiat|proton|flare|"
                   r"string|stuck|fault|anomal|damage|safety test|space weather|goes|kp\b|outage|"
                   r"scenario [a-e]\b|\bpass ?[a-e]\b|held.?out|hidden")
readable = {f"file name {name}.yaml": name for name in plans}
readable.update({f"{name}.yaml": path.read_text(encoding="utf-8") for name, path in plans.items()})
for name, text in readable.items():
    hits = sorted({m.group(0).lower() for m in CLUES.finditer(text)})
    expected = {"held out"} if name.endswith(".yaml") and not name.startswith("file name") else set()
    require(set(hits) <= expected, f"{name}: {hits or 'no clue words'}")
attachments = [REPO / "inputs-pre-existing" / "dictionary" / "tlm_cmd_dictionary_v0.5.md",
               REPO / "plans" / "BALDUR0-command-classes.md", REPO / "odin" / "study" / "cosmos_reference.md"]
attachments += sorted((REPO / "inputs-pre-existing" / "procedures" / "v0.3").glob("*.md"))
print("  The procedures and attachments are the same files in every plan, so they cannot tell scenarios apart.")
labels = sorted(scenarios)
order = [scenarios[l]["document"]["scenario"] for l in labels]
require(order != sorted(order), f"labels are not in the document's order: {dict(zip(labels, order))}")

# --- 4. HUGINN flies each scenario ---------------------------------------------------------------------------
print("4. HUGINN's state at each moment that matters (orbit illumination, no ODIN commands)")


def fly(huginn, marks, extra_faults=()):
    data = dict(huginn, faults=list(huginn["faults"]) + list(extra_faults))
    craft = build(Scenario(data))
    seen = {}
    while craft.t_s <= max(marks):
        if int(craft.t_s) in marks:
            e, st = craft.eps, craft.eps.state
            seen[int(craft.t_s)] = (round(e.soc_pct, 1), st.mode, round(st.load_current_a, 2), st.payload_on,
                                    st.illuminated, craft.cdh.hk_halted)
        craft.step()
    return seen


for label, s in scenarios.items():
    letter = s["document"]["scenario"]
    marks = {0: "start"}
    for c in s["geometry"]["contacts"]:
        marks[c["aos_met_s"]] = f"AOS {c['pass_index']}"
        marks[c["los_met_s"] - 1] = f"LOS {c['pass_index']}"
    extra = []
    script = s["script"]
    if "housekeeping_halt" in script:
        marks[script["housekeeping_halt"]["onset_met_s"] + 1] = "after halt"
    if "latch_up" in script:
        onset = script["latch_up"]["onset_met_s"]
        marks.update({onset - 1: "before latch-up", onset + 1: "latch-up (as the wrapper sets it)",
                      script["latch_up"]["damage"]["met_s"]: "damage time"})
        extra = [{"t_s": onset, "fault": "stuck_load"}]
    for f in s["huginn"]["faults"]:
        if f["fault"] != "hk_generation_halt":
            marks[f["t_s"] + 1] = f"after {f['fault']}"
    seen = fly(s["huginn"], set(marks), extra)
    print(f"  {label} ({letter}), epoch {s['huginn']['start_epoch_utc']}:")
    for met in sorted(marks):
        soc, mode, load, on, lit, halted = seen[met]
        print(f"    MET {met:>6} {marks[met]:<34} SOC {soc:5.1f} %  {mode:<9} load {load:4.2f} A  payload "
              f"{'ON ' if on else 'OFF'}  {'sunlit ' if lit else 'eclipse'}{'  HK HALTED' if halted else ''}")
    for met in sorted(marks):
        require(seen[met][1] == "NOMINAL", f"{label}: NOMINAL at MET {met}, no mode change before ODIN acts")

print("\nALL CHECKS HOLD" if not failures else f"\n{len(failures)} CHECKS FAIL")
sys.exit(1 if failures else 0)
