"""ODIN's turn loop (CONTRACT §6, §7, §8; AGENTS §4.1).

One turn in flight at a time: fetch a bundle, save and hash the exact
inputs, log AGENT_INPUT before calling the model, check the answer, then
sign and send at most one request ("one answer, one request").

`agent_input_hash` is the SHA-256 of the exact turn-bundle bytes
(Director's ruling); AGENT_INPUT (§16.5) also records the prompt hash.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from odin.spend.meter import SpendStop

from .canonical import sha256_tag
from .prompt import build_prompt  # noqa: F401  (re-exported for callers)
from .signing import build_signed_request
from .validate import DictionaryError, dictionary_for_plan, validate_act_text, validate_report_text


def format_utc(moment) -> str:
    """Contract utc form (§4): ISO 8601 UTC with milliseconds."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def put_back_command_call(answer):
    """M14: put format B's `command_call` back as `command` and
    `parameters`, in the loop's parse. Anything else in the call is
    kept, so the frozen schema can refuse it; nothing is repaired."""
    if not isinstance(answer, dict) or "command_call" not in answer:
        return answer
    result = dict(answer)
    call = result.pop("command_call")
    if isinstance(call, dict):
        result["command"] = call.get("command")
        result["parameters"] = call.get("parameters")
        for key, value in call.items():
            if key not in ("command", "parameters"):
                result[key] = value
    elif call is None:
        result["command"] = None
        result["parameters"] = None
    else:
        result["command"] = call
        result["parameters"] = None
    return result


def judge_act_text(raw, commands=None):
    """Judge an ACT answer's text (M14): parse it, put `command_call`
    back, apply M11's null drop (`drop_nulls`, in M11's order), then
    the frozen schema, the dictionary check and the loop's verdict via
    `validate_act_text`. The judged form is reproducible from the
    CANDIDATE text by this same rule."""
    from odin.adapters.spark import drop_nulls

    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        obj = None
    if not isinstance(obj, dict):
        return validate_act_text(raw if isinstance(raw, str) else "", commands=commands)
    judged = drop_nulls(put_back_command_call(obj))
    return validate_act_text(json.dumps(judged), commands=commands)


def utc_now() -> str:
    """Wall-clock now, in the contract's utc form (M12)."""
    return format_utc(datetime.now(timezone.utc))


def _urllib_transport(method, url, data=None, timeout=30):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # U30: 4xx is an outcome, not a crash
        return exc.code, exc.read()


def _http_json(method, url, payload=None, timeout=30, transport=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    if transport is not None:
        return transport(method, url, data)
    return _urllib_transport(method, url, data, timeout=timeout)


class TurnLoop:
    def __init__(self, *, harness_url, baldur_url, log_url, adapter, repo_root,
                 private_key_path=None, instructions="", frozen_reference="", transport=None,
                 meter=None, registry_path=None, clock=None):
        self.harness_url = harness_url.rstrip("/")
        self.baldur_url = baldur_url.rstrip("/")
        self.log_url = log_url.rstrip("/")
        self.adapter = adapter
        self.repo_root = Path(repo_root)
        self.private_key_path = private_key_path
        self.instructions = instructions
        self.frozen_reference = frozen_reference
        self.transport = transport
        self.meter = meter
        self.registry_path = registry_path
        self.clock = clock
        self.errors = []

    def _request_utc(self) -> str:
        """Wall-clock stamped just before signing (M12). The clock, when
        given, may return a datetime or a contract-form string."""
        if self.clock is not None:
            moment = self.clock()
            return moment if isinstance(moment, str) else format_utc(moment)
        return utc_now()

    # -- logging ---------------------------------------------------------
    def _log(self, record_type, body):
        status, _ = _http_json("POST", f"{self.log_url}/log/agent",
                               {"type": record_type, "body": body},
                               transport=self.transport)
        return status

    def _tool_handler(self, name, args):
        """A read-only tool call (M10). Every argument is encoded with
        urllib.parse; points reach the harness comma-separated with no
        spaces (U19), whether the model gives a string or a list. A harness
        refusal body already goes back as the tool's result; any other
        error does the same, is written to stderr, and never ends the turn."""
        try:
            if name == "docs_lookup":
                query = urllib.parse.urlencode({"q": args.get("q", "")})
                _, body = _http_json("GET", f"{self.harness_url}/docs/lookup?{query}",
                                     transport=self.transport)
                return body.decode("utf-8")
            raw_points = args.get("points", "")
            if isinstance(raw_points, (list, tuple)):
                names = [str(p).strip() for p in raw_points]
            else:
                names = [p.strip() for p in str(raw_points).split(",")]
            points = ",".join(n for n in names if n)
            query = urllib.parse.urlencode(
                {"points": points, "window_s": args.get("window_s", 300)})
            _, body = _http_json("GET", f"{self.harness_url}/history?{query}",
                                 transport=self.transport)
            return body.decode("utf-8")
        except Exception as exc:
            print(f"tool {name} failed: {exc}", file=sys.stderr)
            return f"tool {name} error: {exc}"

    def _attachment_mismatch(self, bundle):
        """U43: each attachment's SHA-256 must match the plan's references."""
        references = {r.get("name"): r.get("sha256")
                      for r in ((bundle.get("plan") or {}).get("references") or [])}
        for procedure in bundle.get("procedures") or []:
            for attachment in procedure.get("attachments") or []:
                computed = sha256_tag(attachment.get("text", "").encode("utf-8"))
                if computed != attachment.get("sha256"):
                    return f"attachment {attachment.get('name')!r} hash mismatch"
                expected = references.get(attachment.get("name"))
                if expected is not None and expected != computed:
                    return f"attachment {attachment.get('name')!r} != plan reference"
        return None

    def _service_error(self, turn_id, service, status):
        # U30: a 400/404 ends the turn, no retry, never a crash.
        self.errors.append({"turn_id": turn_id, "service": service, "status": status})
        return {"turn_id": turn_id, "outcome": "error", "service": service, "status": status}

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
        prompt_bytes = build_prompt(bundle, self.instructions)
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
        mismatch = self._attachment_mismatch(bundle)
        if mismatch is not None:
            # U43: ends the turn, logged, no model call is made.
            self._log("MALFORMED", {"run_id": run_id, "turn_id": turn_id,
                                    "reason": "SCHEMA_VIOLATION", "detail": mismatch})
            return {"turn_id": turn_id, "outcome": "attachment_mismatch",
                    "detail": mismatch}
        plan = bundle.get("plan") or {}
        plan_id = plan.get("plan_id")
        try:
            # U58: the dictionary in force for this turn's plan. Choosing it
            # or trusting its file failing is an error, not a malformed
            # answer: send nothing, make no model call.
            _entry, dict_commands = dictionary_for_plan(plan, self.registry_path)
        except (DictionaryError, OSError, KeyError, ValueError) as exc:
            self.errors.append({"turn_id": turn_id, "service": "dictionary",
                                "detail": str(exc)})
            return {"turn_id": turn_id, "outcome": "error",
                    "service": "dictionary", "detail": str(exc)}
        sink = []
        try:
            result = self.adapter.complete(
                prompt=prompt_bytes, bundle=bundle, call_index=1, meter=self.meter,
                turn_id=turn_id, model_call_sink=sink, tool_handler=self._tool_handler)
        except SpendStop as exc:
            # M8: after a spend stop ODIN sends nothing more.
            for record in sink:
                record["run_id"] = run_id
                self._log("MODEL_CALL", record)
            if not sink:
                self._log("MODEL_CALL", self._model_call_record(
                    bundle, 1, None, status="SPEND_STOP"))
            return {"turn_id": turn_id, "outcome": "spend_stop", "detail": str(exc)}
        except Exception as exc:  # timeout/error: no request, logged (§9.5)
            for record in sink:
                record["run_id"] = run_id
                self._log("MODEL_CALL", record)
            if not sink:
                self._log("MODEL_CALL", self._model_call_record(bundle, 1, None, status="ERROR"))
            return {"turn_id": turn_id, "outcome": "error", "detail": str(exc)}
        if sink:
            for record in sink:
                record["run_id"] = run_id
                self._log("MODEL_CALL", record)
        else:
            self._log("MODEL_CALL", self._model_call_record(bundle, 1, result))
        channel = result.get("channel", "CONTENT")
        raw = result.get("raw", "")
        self._log("CANDIDATE", {"run_id": run_id, "turn_id": turn_id, "channel": channel, "raw": raw})

        if channel == "MESSAGE":
            from odin.adapters.spark_open import convert_message
            try:
                message = json.loads(raw)
            except Exception:
                message = {}
            if not isinstance(message, dict):
                message = {}
            ok, answer, reason, detail = convert_message(
                message.get("content"), message.get("tool_calls") or [],
                turn_kind=bundle["turn_kind"], report_kind=bundle.get("report_kind"),
                reasoning_content=message.get("reasoning_content"),
                commands=dict_commands)
        elif channel == "TOOL_CALLS":
            from odin.adapters.spark_open import convert_tool_calls
            try:
                tool_calls = json.loads(raw)
            except Exception:
                tool_calls = []
            ok, answer, reason, detail = convert_tool_calls(
                tool_calls, turn_kind=bundle["turn_kind"], report_kind=bundle.get("report_kind"),
                commands=dict_commands)
        elif bundle["turn_kind"] == "REPORT":
            ok, answer, reason, detail = validate_report_text(raw, bundle.get("report_kind") or "PASS_START")
        else:
            ok, answer, reason, detail = judge_act_text(raw, commands=dict_commands)

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
            status, _ = _http_json("POST", f"{self.log_url}/report", report,
                                   transport=self.transport)
            if status >= 400:
                return self._service_error(turn_id, "log/report", status)
            return {"turn_id": turn_id, "outcome": "report", "report": report}

        kind = answer.get("kind")
        if kind == "none":
            return {"turn_id": turn_id, "outcome": "none"}
        if kind == "escalation":
            escalation = {**answer, "run_id": run_id, "turn_id": turn_id,
                          "met_s": bundle["met_s"], "utc": bundle["utc"],
                          "plan_id": plan_id, "agent_input_hash": bundle_hash}
            status, _ = _http_json("POST", f"{self.baldur_url}/escalation", escalation,
                                   transport=self.transport)
            if status >= 400:
                return self._service_error(turn_id, "baldur/escalation", status)
            return {"turn_id": turn_id, "outcome": "escalation", "escalation": escalation}
        # kind == command: fill loop-owned fields, sign, send one request.
        # M12: utc is wall-clock taken just before signing, never the
        # bundle's utc; the signature covers it, as before.
        request = build_signed_request(
            command=answer["command"], parameters=answer["parameters"],
            rationale=answer.get("rationale"), run_id=run_id, turn_id=turn_id,
            plan_id=plan_id, met_s=bundle["met_s"], utc=self._request_utc(),
            agent_input_hash=bundle_hash, private_key_path=self.private_key_path)
        status, body = _http_json("POST", f"{self.baldur_url}/request", request,
                                  transport=self.transport)
        if status >= 400:  # U30: ends the turn, no retry, never a crash
            return self._service_error(turn_id, "baldur/request", status)
        decision = json.loads(body) if body else {}
        if decision.get("decision") == "REFUSE":
            # U30: a 200 REFUSE is a normal outcome; nothing more is sent.
            return {"turn_id": turn_id, "outcome": "refused", "request": request,
                    "decision": decision, "cut_off": bool(result.get("cut_off"))}
        return {"turn_id": turn_id, "outcome": "request", "request": request,
                "decision": decision, "cut_off": bool(result.get("cut_off"))}

    def run(self, max_turns=None, max_waits=10000) -> list:
        """Run until the harness says the run is complete (max_turns=None
        means no cap). Sets self.run_completed only on run_complete."""
        self.run_completed = False
        results = []
        waits = 0
        while (max_turns is None or len(results) < max_turns) and waits <= max_waits:
            try:
                # U39: GET /turn/next may wait up to 120 s; a timeout is not
                # an error — the loop asks again and never crashes on it.
                status, body = _http_json("GET", f"{self.harness_url}/turn/next",
                                          timeout=120, transport=self.transport)
            except TimeoutError:
                waits += 1
                continue
            except urllib.error.URLError as exc:
                # A long-poll timeout asks again (U39); a refused or
                # unreachable harness is an error, not a wait.
                if isinstance(exc.reason, TimeoutError):
                    waits += 1
                    continue
                raise ConnectionError(str(exc.reason)) from exc
            if status >= 400:
                results.append(self._service_error(
                    results[-1]["turn_id"] + 1 if results else 1, "harness/turn", status))
                break
            if json.loads(body).get("run_complete"):
                self.run_completed = True
                break
            result = self.run_turn(body)
            results.append(result)
            if result["outcome"] == "spend_stop":
                break  # M8: sends nothing more after a spend stop
        return results
