"""ODIN's turn loop (CONTRACT §6, §7, §8; AGENTS §4.1).

One turn in flight at a time: fetch a bundle, save and hash the exact
inputs, log AGENT_INPUT before calling the model, check the answer, then
sign and send at most one request ("one answer, one request").

`agent_input_hash` is the SHA-256 of the exact turn-bundle bytes
(Director's ruling); AGENT_INPUT (§16.5) also records the prompt hash.
"""
import json
import urllib.request
from pathlib import Path

from .canonical import sha256_tag
from .prompt import build_prompt
from .signing import build_signed_request
from .validate import validate_act_text, validate_report_text


def _urllib_transport(method, url, data=None, timeout=30):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def _http_json(method, url, payload=None, timeout=30, transport=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    if transport is not None:
        return transport(method, url, data)
    return _urllib_transport(method, url, data, timeout=timeout)


class TurnLoop:
    def __init__(self, *, harness_url, baldur_url, log_url, adapter, repo_root,
                 private_key_path=None, instructions="", frozen_reference="", transport=None):
        self.harness_url = harness_url.rstrip("/")
        self.baldur_url = baldur_url.rstrip("/")
        self.log_url = log_url.rstrip("/")
        self.adapter = adapter
        self.repo_root = Path(repo_root)
        self.private_key_path = private_key_path
        self.instructions = instructions
        self.frozen_reference = frozen_reference
        self.transport = transport

    # -- logging ---------------------------------------------------------
    def _log(self, record_type, body):
        _http_json("POST", f"{self.log_url}/log/agent", {"type": record_type, "body": body},
                   transport=self.transport)

    def _model_call_record(self, bundle, call_index, result, status=None):
        return {
            "run_id": bundle["run_id"], "turn_id": bundle["turn_id"],
            "call_index": call_index,
            "config": getattr(self.adapter, "name", "stand_in"),
            "provider": result.get("provider") if result else None,
            "model_id": result.get("model_id") if result else None,
            "reasoning_effort": result.get("reasoning_effort") if result else None,
            "max_output_tokens": result.get("max_output_tokens") if result else None,
            "status": status or (result.get("status", "OK") if result else "ERROR"),
            "input_tokens": result.get("input_tokens") if result else None,
            "cached_input_tokens": result.get("cached_input_tokens") if result else None,
            "output_tokens": result.get("output_tokens") if result else None,
            "reasoning_tokens": result.get("reasoning_tokens") if result else None,
            "reserved_cost_usd": 0.0, "actual_cost_usd": 0.0 if result else None,
            "pays_from": None,
            "latency_s": result.get("latency_s", 0.0) if result else None,
            "provider_usage": result.get("provider_usage") if result else None,
        }

    # -- one turn ----------------------------------------------------------
    def run_turn(self, bundle_bytes: bytes) -> dict:
        bundle = json.loads(bundle_bytes)
        run_id, turn_id = bundle["run_id"], bundle["turn_id"]
        prompt_bytes = build_prompt(bundle, self.instructions, self.frozen_reference)
        bundle_hash = sha256_tag(bundle_bytes)
        prompt_hash = sha256_tag(prompt_bytes)
        # Save exact bytes, each file named by its hash (§4), then log
        # AGENT_INPUT before calling the model (§6.3).
        inputs_dir = self.repo_root / "runs" / run_id / "inputs"
        inputs_dir.mkdir(parents=True, exist_ok=True)
        (inputs_dir / bundle_hash.split(":", 1)[1]).write_bytes(bundle_bytes)
        (inputs_dir / prompt_hash.split(":", 1)[1]).write_bytes(prompt_bytes)
        self._log("AGENT_INPUT", {"run_id": run_id, "turn_id": turn_id,
                                  "bundle_sha256": bundle_hash, "prompt_sha256": prompt_hash})
        plan = bundle.get("plan") or {}
        plan_id = plan.get("plan_id")
        try:
            result = self.adapter.complete(prompt=prompt_bytes, bundle=bundle, call_index=1)
        except Exception as exc:  # timeout/error: no request, logged (§9.5)
            self._log("MODEL_CALL", self._model_call_record(bundle, 1, None, status="ERROR"))
            return {"turn_id": turn_id, "outcome": "error", "detail": str(exc)}
        self._log("MODEL_CALL", self._model_call_record(bundle, 1, result))
        channel = result.get("channel", "CONTENT")
        raw = result.get("raw", "")
        self._log("CANDIDATE", {"run_id": run_id, "turn_id": turn_id, "channel": channel, "raw": raw})

        if channel == "TOOL_CALLS":
            from odin.adapters.spark_open import convert_tool_calls
            try:
                tool_calls = json.loads(raw)
            except Exception:
                tool_calls = []
            ok, answer, reason, detail = convert_tool_calls(
                tool_calls, turn_kind=bundle["turn_kind"], report_kind=bundle.get("report_kind"))
        elif bundle["turn_kind"] == "REPORT":
            ok, answer, reason, detail = validate_report_text(raw, bundle.get("report_kind") or "PASS_START")
        else:
            ok, answer, reason, detail = validate_act_text(raw)

        if not ok:
            self._log("MALFORMED", {"run_id": run_id, "turn_id": turn_id,
                                    "reason": reason, "detail": detail})
            return {"turn_id": turn_id, "outcome": "malformed", "reason": reason, "detail": detail}
        self._log("ANSWER", {"run_id": run_id, "turn_id": turn_id, "answer": answer})

        if bundle["turn_kind"] == "REPORT":
            report = {
                "report_kind": bundle["report_kind"], "run_id": run_id, "turn_id": turn_id,
                "met_s": bundle["met_s"], "utc": bundle["utc"], "plan_id": plan_id, **answer,
            }
            _http_json("POST", f"{self.log_url}/report", report, transport=self.transport)
            return {"turn_id": turn_id, "outcome": "report", "report": report}

        kind = answer.get("kind")
        if kind == "none":
            return {"turn_id": turn_id, "outcome": "none"}
        if kind == "escalation":
            escalation = {**answer, "run_id": run_id, "turn_id": turn_id,
                          "met_s": bundle["met_s"], "utc": bundle["utc"],
                          "plan_id": plan_id, "agent_input_hash": bundle_hash}
            _http_json("POST", f"{self.baldur_url}/escalation", escalation, transport=self.transport)
            return {"turn_id": turn_id, "outcome": "escalation", "escalation": escalation}
        # kind == command: fill loop-owned fields, sign, send one request.
        request = build_signed_request(
            command=answer["command"], parameters=answer["parameters"],
            rationale=answer.get("rationale"), run_id=run_id, turn_id=turn_id,
            plan_id=plan_id, met_s=bundle["met_s"], utc=bundle["utc"],
            agent_input_hash=bundle_hash, private_key_path=self.private_key_path)
        _http_json("POST", f"{self.baldur_url}/request", request, transport=self.transport)
        return {"turn_id": turn_id, "outcome": "request", "request": request}

    def run(self, max_turns=1000) -> list:
        results = []
        for _ in range(max_turns):
            _, body = _http_json("GET", f"{self.harness_url}/turn/next", timeout=30, transport=self.transport)
            if json.loads(body).get("run_complete"):
                break
            results.append(self.run_turn(body))
        return results
