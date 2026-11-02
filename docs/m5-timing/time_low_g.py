"""M5's timing of record on Modal (the Director's ruling of 30 October 2026, "Low, tie type to command": after phase 2,
re-time the nine prompts at low with format G on the H100). The same nine onboard prompts as before
(ODIN\\m5-timing\\prompts), in turn order, with format G (ODIN\\m16\\format-G-HUGINN.json) as the JSON schema, and
Glimmer's reasoning_strength sent as llama.cpp's chat_template_kwargs; max_tokens stays at 8192.

First the server's own /apply-template shows which way of sending the level reaches Glimmer's template: the request
field reasoning_effort (how the glimmer_modal adapter of MC-M5-02 sends it), chat_template_kwargs, or nothing. Before
the nine prompts it shows the system block the setting gives. Keys come from the environment (run_modal.py).

    python run_modal.py python <this file> h100 low
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
import glimmer_modal as gm  # noqa: E402
from odin.loop.loop import judge_act_text  # noqa: E402
from odin.loop.validate import dictionary_for_plan  # noqa: E402

PROMPTS = Path(__file__).resolve().parent / "prompts"
PRICES = {"h100": 0.001097, "h200": 0.001261}   # per GPU-second, modal.com/pricing, 29 and 30 October 2026
GPU, SETTINGS = sys.argv[1], sys.argv[2:]
SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "contract" / "m16" / "format-G-HUGINN.json").read_text(encoding="utf-8"))
OUT = Path(__file__).resolve().parent / f"timing-{GPU}-{'-'.join(SETTINGS)}-G.json"


def post(url, path, body, timeout_s=900):
    request = urllib.request.Request(url + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", **gm.proxy_headers()})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as reply:
            return reply.status, json.loads(reply.read()), time.monotonic() - started
    except urllib.error.HTTPError as error:
        return error.code, {"error_body": error.read().decode("utf-8", "replace")[:2000]}, time.monotonic() - started


def kwargs_of(setting):
    return {} if setting == "default" else {"chat_template_kwargs": {"reasoning_strength": setting}}


summary = json.loads((PROMPTS / "SUMMARY.json").read_text(encoding="utf-8"))
results = {"gpu": GPU, "image": gm.LLAMA_IMAGE, "price_per_gpu_s": PRICES[GPU], "settings": {}}
url = gm.endpoint(GPU)
fn = gm.modal.Function.from_name(gm.APP_NAME, gm.FUNCTIONS[GPU])
warm_started = time.monotonic()
fn.autoscaler.update(min_containers=1)
try:
    results["cold_start_s"] = round(gm.wait_until_serving(GPU), 1)
    results["warm_up_s"] = round(gm.warm_up(GPU), 1)
    print(f"{GPU}: serving after {results['cold_start_s']} s; warm-up request {results['warm_up_s']} s", flush=True)
    for label, extra in (("reasoning_effort: low (the adapter's field)", {"reasoning_effort": "low"}),
                         ("chat_template_kwargs reasoning_strength: low", {"chat_template_kwargs": {"reasoning_strength": "low"}}),
                         ("nothing", {})):
        status, rendered, _ = post(url, "/apply-template", {"messages": [{"role": "user", "content": "x"}], **extra}, 60)
        seen = next((part for part in (rendered.get("prompt") or "").split("\n") if "Reasoning strength" in part), None)
        results.setdefault("how_the_level_reaches_glimmer", {})[label] = seen
        print(f"{label}: the system block says {seen!r} (HTTP {status})", flush=True)
    for setting in SETTINGS:
        status, rendered, _ = post(url, "/apply-template", {"messages": [{"role": "user", "content": "x"}],
                                                            **kwargs_of(setting)}, 60)
        line = next((part for part in (rendered.get("prompt") or "").split("\n") if "Reasoning strength" in part), None)
        print(f"{setting}: the system block says {line!r} (HTTP {status})", flush=True)
        decisions = []
        for row in summary:
            text = (PROMPTS / row["prompt"]).read_bytes().decode("utf-8")
            bundle = json.loads((PROMPTS / row["prompt"].replace(".prompt.txt", ".bundle.json")).read_bytes())
            body = {"model": gm.FILENAME, "messages": [{"role": "user", "content": text}], "max_tokens": 8192,
                    "response_format": {"type": "json_schema", "json_schema": {"name": "odin_answer", "schema": SCHEMA}},
                    **kwargs_of(setting)}
            status, payload, seconds = post(url, "/v1/chat/completions", body)
            choice = (payload.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            _, commands = dictionary_for_plan(bundle["plan"])
            accepted, judged, reason, _ = judge_act_text(content, commands=commands)
            t = payload.get("timings") or {}
            decision = {"prompt": row["prompt"], "met_s": row["met_s"], "http_status": status,
                        "seconds": round(seconds, 1), "finish_reason": choice.get("finish_reason"),
                        "prefill_tokens": t.get("prompt_n"), "prefill_s": round((t.get("prompt_ms") or 0) / 1000, 1),
                        "decode_tokens": t.get("predicted_n"), "decode_s": round((t.get("predicted_ms") or 0) / 1000, 1),
                        "reasoning_chars": len(message.get("reasoning_content") or ""), "content": content,
                        "judged": {"accepted": accepted, "kind": (judged or {}).get("kind"), "reason": reason},
                        "error": payload.get("error_body")}
            decisions.append(decision)
            print(f"{GPU} {setting} {row['prompt']}: {decision['seconds']} s, finish {decision['finish_reason']}, "
                  f"prefill {decision['prefill_tokens']} tok {decision['prefill_s']} s, decode {decision['decode_tokens']} "
                  f"tok {decision['decode_s']} s, judged {'accepted ' + str(decision['judged']['kind']) if accepted else reason}",
                  flush=True)
        seconds = [d["seconds"] for d in decisions]
        results["settings"][setting] = {"system_block_line": line, "decisions": decisions,
                                        "mean_s": round(sum(seconds) / len(seconds), 1), "max_s": max(seconds),
                                        "over_60_s": sum(s > 60 for s in seconds),
                                        "accepted": sum(d["judged"]["accepted"] for d in decisions)}
        print(f"{GPU} {setting}: mean {results['settings'][setting]['mean_s']} s, max {max(seconds)} s, over 60 s "
              f"{results['settings'][setting]['over_60_s']}, accepted {results['settings'][setting]['accepted']} of 9",
              flush=True)
finally:
    fn.autoscaler.update(min_containers=0)
    results["warm_wall_s"] = round(time.monotonic() - warm_started, 1)
    results["billed_s_estimate"] = round(results["warm_wall_s"] + gm.IDLE_S, 1)
    results["cost_usd_estimate"] = round(results["billed_s_estimate"] * PRICES[GPU], 4)
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"{GPU}: warm for {results['warm_wall_s']} s; billed about {results['billed_s_estimate']} s, "
      f"${results['cost_usd_estimate']}; written {OUT.name}")
