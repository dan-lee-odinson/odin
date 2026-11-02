"""The two fixes beside today's timing: per prompt, seconds, prefill and decode, and the loop's judgment.

    python table.py <baseline.json> <timing.json>...
"""

import json
import sys

baseline = json.load(open(sys.argv[1], encoding="utf-8"))
columns = [("h100 high (28 Oct)", baseline["decisions"], baseline)]
for path in sys.argv[2:]:
    timing = json.load(open(path, encoding="utf-8"))
    for setting, block in timing["settings"].items():
        label = f"{timing['gpu']} {'high' if setting == 'default' else setting}"
        columns.append((label, block["decisions"], timing))


def cell(d):
    t = d.get("timings")
    prefill_s = d["prefill_s"] if "prefill_s" in d else round(t["prompt_ms"] / 1000, 1)
    decode_n = d["decode_tokens"] if "decode_tokens" in d else t["predicted_n"]
    decode_s = d["decode_s"] if "decode_s" in d else round(t["predicted_ms"] / 1000, 1)
    j = d["judged"]
    judged = j["kind"] if j["accepted"] else j["reason"]
    return f"{d['seconds']:5.1f} s ({prefill_s:4.1f} + {decode_s:4.1f}; {decode_n:4} tok) {judged}"


for label, decisions, _ in columns:
    print(f"== {label}")
    for d in decisions:
        print(f"  {d['prompt'][:13]:14} {cell(d)}")
    seconds = [d["seconds"] for d in decisions]
    print(f"  mean {sum(seconds) / len(seconds):.1f} s, max {max(seconds)} s, over 60 s {sum(s > 60 for s in seconds)}, "
          f"accepted {sum(d['judged']['accepted'] for d in decisions)} of {len(decisions)}")
for path in sys.argv[2:]:
    timing = json.load(open(path, encoding="utf-8"))
    print(f"{timing['gpu']}: cold start {timing['cold_start_s']} s, warm-up {timing['warm_up_s']} s, warm "
          f"{timing['warm_wall_s']} s, billed about {timing['billed_s_estimate']} s, ${timing['cost_usd_estimate']}")
