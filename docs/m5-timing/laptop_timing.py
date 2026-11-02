"""M5's timing of Muse Glimmer on the Director's laptop (his word of 30 October 2026): run it after phase 2, with
Docker stopped, against Glimmer served on this laptop. The same nine onboard-shaped prompts as the Modal timing, at
the setting and in the format Glimmer flies with (his ruling of 30 October 2026, "Low, tie type to command"), so the
two compare: reasoning strength `low`, Glimmer's chat-template variable `reasoning_strength`, sent as llama.cpp's
`chat_template_kwargs`; and format G, Glimmer's own format for HUGINN's dictionary (..\\m16\\format-G-HUGINN.json,
until it is in the repository as contract/m16/). Each prompt in turn order, as consecutive turns, after one throwaway
warm-up request. Before the first, the server's own /apply-template shows the system block the setting gives, so the
setting is seen to reach Glimmer; a server without /apply-template (Ollama) is recorded as unchecked, and its result
should not be trusted for the setting. It keeps each decision's wall time and the server's own timings, judges each
answer by ODIN's own loop, and says how many decisions took more than 60 s, the onboard seat's limit.

First serve the laptop's GGUF, D:\\models\\muse-glimmer\\Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf, on an
OpenAI-compatible endpoint. With llama.cpp, the same flags as on Modal (lower -c if the GPU runs out of memory; the
prompts are about 55,000 tokens, so keep it at 65536 or more):

    llama-server -m D:\\models\\muse-glimmer\\Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf --jinja -ngl 999 -fa on -c 131072 -np 1 --host 127.0.0.1 --port 8090

or with Ollama (0.32.7 or later, OLLAMA_MODELS on D:), whose endpoint is http://127.0.0.1:11434 and whose model name
is the one Ollama lists. Then, from any folder:

    python laptop_timing.py --endpoint http://127.0.0.1:8090
    python laptop_timing.py --endpoint http://127.0.0.1:11434 --model <the model's name in Ollama>

It writes laptop-timing-<UTC time>.json beside itself and prints one line a decision and a summary. It calls nothing
but the endpoint given, needs no key, and reads the repository only for the format and ODIN's answer check.

One decision, stopped at a clear miss (the Director's word of 30 October 2026, "One prompt, Claude Code runs it"):

    python laptop_timing.py --prompt turn01-met800.prompt.txt --stop-at 180

times only the prompt named, streaming its answer so that the end of prefill (the first token) is seen, and stops
waiting at the given second: a decision still running then is recorded as a clear miss, with what had arrived.
"""

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"
REPO = Path(__file__).resolve().parents[2]
LIMIT_S = 60


def post(endpoint, body, timeout_s, path="/v1/chat/completions"):
    request = urllib.request.Request(endpoint.rstrip("/") + path, data=json.dumps(body).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as reply:
            payload, status = json.loads(reply.read()), reply.status
    except urllib.error.HTTPError as error:
        payload, status = {"error_body": error.read().decode("utf-8", "replace")[:2000]}, error.code
    return status, payload, time.monotonic() - started


def post_streamed(endpoint, body, stop_at_s):
    """One streamed decision, waited on for at most stop_at_s: (status, payload, seconds, seen). The payload is
    assembled from the stream as a non-streamed reply would be; seen holds when the first token came (the end of
    prefill), how many chunks arrived, and whether the decision was still running when the wait stopped."""
    seen = {"first_token_s": None, "chunks": 0, "finished": False}
    reply = {"content": "", "reasoning_content": "", "finish_reason": None, "timings": None, "status": None}
    started = time.monotonic()

    def read():
        request = urllib.request.Request(endpoint.rstrip("/") + "/v1/chat/completions", method="POST",
                                         data=json.dumps(dict(body, stream=True)).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=stop_at_s + 60) as stream:
                reply["status"] = stream.status
                for raw in stream:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:") or line == "data: [DONE]":
                        continue
                    chunk = json.loads(line[5:])
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if (delta.get("content") or delta.get("reasoning_content")) and seen["first_token_s"] is None:
                            seen["first_token_s"] = round(time.monotonic() - started, 1)
                        reply["content"] += delta.get("content") or ""
                        reply["reasoning_content"] += delta.get("reasoning_content") or ""
                        reply["finish_reason"] = choice.get("finish_reason") or reply["finish_reason"]
                    seen["chunks"] += 1
                    reply["timings"] = chunk.get("timings") or reply["timings"]
            seen["finished"] = True
        except urllib.error.HTTPError as error:
            reply["status"], reply["error_body"] = error.code, error.read().decode("utf-8", "replace")[:2000]
            seen["finished"] = True
        except OSError as error:
            reply["error_body"] = repr(error)

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    worker.join(stop_at_s)
    seconds = time.monotonic() - started
    payload = {"choices": [{"message": {"content": reply["content"], "reasoning_content": reply["reasoning_content"]},
                            "finish_reason": reply["finish_reason"]}],
               "timings": reply["timings"], "error_body": reply.get("error_body")}
    return reply["status"], payload, seconds, dict(seen, still_running_at_stop=worker.is_alive())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--endpoint", default="http://127.0.0.1:8090")
    parser.add_argument("--model", default="Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf")
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--timeout", type=int, default=1800, help="seconds a decision may take before it is cut off")
    parser.add_argument("--reasoning-strength", default="low", help="Glimmer's reasoning_strength (the ruling: low)")
    parser.add_argument("--format", default=str(HERE.parents[1] / "contract" / "m16" / "format-G-HUGINN.json"),
                        help="the JSON schema sent (default: format G)")
    parser.add_argument("--prompt", help="time only this prompt (a file name in prompts/), not all nine")
    parser.add_argument("--stop-at", type=int, help="stream each decision and stop waiting at this many seconds")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO))
    from odin.loop.loop import judge_act_text
    from odin.loop.validate import dictionary_for_plan

    schema = json.loads(Path(args.format).read_text(encoding="utf-8"))
    setting = {"chat_template_kwargs": {"reasoning_strength": args.reasoning_strength}}
    summary = json.loads((PROMPTS / "SUMMARY.json").read_text(encoding="utf-8"))
    if args.prompt:
        summary = [row for row in summary if row["prompt"] == args.prompt]
        if not summary:
            parser.error(f"no prompt named {args.prompt} in prompts/SUMMARY.json")
    results = {"endpoint": args.endpoint, "model": args.model, "max_tokens": args.max_tokens,
               "reasoning_strength": args.reasoning_strength, "format": Path(args.format).name,
               "stop_at_s": args.stop_at, "decisions": []}

    status, rendered, _ = post(args.endpoint, {"messages": [{"role": "user", "content": "x"}], **setting}, 60,
                               path="/apply-template")
    line = next((part for part in (rendered.get("prompt") or "").split("\n") if "Reasoning strength" in part), None)
    results["setting_seen"] = line if status == 200 else f"unchecked: /apply-template gave HTTP {status}"
    print(f"setting: {results['setting_seen']!r}", flush=True)

    print("warm-up request ...", flush=True)
    warm = {"model": args.model, "max_tokens": 16,
            "messages": [{"role": "user", "content": "Warm-up only; answer OK. " + "telemetry frame " * 12000}]}
    status, _, seconds = post(args.endpoint, warm, args.timeout)
    results["warm_up"] = {"http_status": status, "seconds": round(seconds, 1)}
    print(f"warm-up: HTTP {status}, {seconds:.1f} s", flush=True)

    for row in summary:
        text = (PROMPTS / row["prompt"]).read_bytes().decode("utf-8")
        bundle = json.loads((PROMPTS / row["prompt"].replace(".prompt.txt", ".bundle.json")).read_bytes())
        body = {"model": args.model, "messages": [{"role": "user", "content": text}], "max_tokens": args.max_tokens,
                "response_format": {"type": "json_schema", "json_schema": {"name": "odin_answer", "schema": schema}},
                **setting}
        seen = None
        if args.stop_at:
            status, payload, seconds, seen = post_streamed(args.endpoint, body, args.stop_at)
        else:
            status, payload, seconds = post(args.endpoint, body, args.timeout)
        choice = (payload.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        _, commands = dictionary_for_plan(bundle["plan"])
        accepted, judged, reason, _ = judge_act_text(content, commands=commands)
        decision = {"prompt": row["prompt"], "met_s": row["met_s"], "http_status": status, "seconds": round(seconds, 1),
                    "finish_reason": choice.get("finish_reason"), "usage": payload.get("usage"),
                    "timings": payload.get("timings"), "streamed": seen, "content": content,
                    "error": payload.get("error_body"),
                    "judged": {"accepted": accepted, "kind": (judged or {}).get("kind"), "reason": reason}}
        results["decisions"].append(decision)
        if seen and seen["still_running_at_stop"]:
            print(f"{row['prompt']}: a clear miss, still running at {seconds:.1f} s; first token "
                  f"{seen['first_token_s']} s, {seen['chunks']} chunks so far", flush=True)
            break
        print(f"{row['prompt']}: HTTP {status}, {seconds:.1f} s{' (over 60 s)' if seconds > LIMIT_S else ''}, "
              f"finish {decision['finish_reason']}, judged "
              f"{'accepted ' + str(decision['judged']['kind']) if accepted else reason}", flush=True)

    seconds = [d["seconds"] for d in results["decisions"]]
    results["summary"] = {"decisions": len(seconds), "min_s": min(seconds), "max_s": max(seconds),
                          "mean_s": round(sum(seconds) / len(seconds), 1),
                          "over_60_s": sum(s > LIMIT_S for s in seconds),
                          "accepted": sum(d["judged"]["accepted"] for d in results["decisions"]),
                          "stopped_at_a_clear_miss": any((d["streamed"] or {}).get("still_running_at_stop")
                                                         for d in results["decisions"])}
    out = HERE / f"laptop-timing-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"summary: {json.dumps(results['summary'])}; written {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
