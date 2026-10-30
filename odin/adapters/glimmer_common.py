"""Shared Glimmer call sequence (M16): format G and the timed-out call.

Both Glimmer adapters (local and Modal) serve the same weights through
llama.cpp and answer in format G. A call is run on its own thread so
the adapter's timeout is its own give-up point: if the call is still
open at the timeout, the adapter asks the same server's /slots --
with the same headers, while the call is still open -- whether it is
processing. Only that flag is kept: the MODEL_CALL is logged with
status TIMEOUT (and the call's latency) when the server says it is
processing, and ERROR for anything else (no answer, refused, not
processing). Nothing else /slots returns is stored or logged anywhere.
"""
import json
import threading
import time
import urllib.error
import urllib.request

from odin.spend.meter import SpendStop

from .openai_compat import ProviderError, model_call_body
from .spark import SparkAdapter, act_format_g

SLOTS_PROBE_TIMEOUT_S = 5
TRANSPORT_GRACE_S = 30


def http_get_json(url, headers, timeout):
    req = urllib.request.Request(url, method="GET", headers=dict(headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:
            return exc.code, {}


def slots_processing(payload) -> bool:
    """The one flag taken from a /slots answer: is any slot processing?"""
    slots = payload.get("slots") if isinstance(payload, dict) else payload
    if not isinstance(slots, list):
        slots = [payload] if isinstance(payload, dict) else []
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        if slot.get("is_processing") is True:
            return True
        if slot.get("state") == "processing" or slot.get("status") == "processing":
            return True
    return False


class GlimmerAdapter(SparkAdapter):
    """Spark's call sequence, format G, and the /slots timeout flag."""

    def __init__(self, *args, http_get=None, monotonic=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.http_get = http_get or http_get_json
        self._monotonic = monotonic or time.monotonic

    def _act_format(self, commands):
        return act_format_g(commands)

    # -- hooks the two Glimmer adapters fill in -------------------------------
    def _headers(self):
        return {}

    def _worst_case_usd(self, meter):
        return 0.0

    def _settle(self, reservation, meter, latency):
        if reservation is None:
            return None
        return reservation.settle(actual_usd=0.0)

    # -- endpoints --------------------------------------------------------------
    def _url(self) -> str:
        base = self.base_url
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _slots_url(self) -> str:
        base = self.base_url
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        return f"{base}/slots"

    def _probe_slots(self, headers) -> bool:
        try:
            status, payload = self.http_get(
                self._slots_url(), headers, SLOTS_PROBE_TIMEOUT_S)
        except Exception:
            return False
        if status >= 400:
            return False
        return slots_processing(payload)

    def _record(self, sink, *, turn_id, call_index, status, usage,
                reservation, actual, latency):
        if sink is not None:
            sink.append(model_call_body(
                config=self.name, provider=self.provider, model_id=self.model_id,
                reasoning_effort=self.reasoning_effort,
                max_output_tokens=self.max_output_tokens, turn_id=turn_id,
                call_index=call_index, status=status, usage=usage,
                reserved=reservation.reserved_usd if reservation else 0.0,
                actual=actual, latency=latency))

    def _one_call(self, messages, *, tools, meter, turn_id, call_index, sink,
                  response_format=None):
        body = {
            "model": self.model_id, "messages": messages,
            "max_tokens": self.max_output_tokens,
            "reasoning_effort": self.reasoning_effort,
        }
        if tools:
            body["tools"] = tools
        if response_format is not None:
            body["response_format"] = response_format
        headers = self._headers()
        reservation = None
        if meter is not None:
            reservation = meter.reserve(
                config=self.name, input_tokens=0,
                max_output_tokens=self.max_output_tokens,
                turn_id=turn_id, call_index=call_index,
                reserved_usd=self._worst_case_usd(meter))
            if reservation is None:
                self._record(sink, turn_id=turn_id, call_index=call_index,
                             status="SPEND_STOP", usage=None, reservation=None,
                             actual=None, latency=None)
                raise SpendStop("spend meter refused the call")
        box = {}

        def run():
            try:
                box["result"] = self.http_post(
                    self._url(), headers, body, self.timeout_s + TRANSPORT_GRACE_S)
            except BaseException as exc:  # kept until the call's own thread ends
                box["error"] = exc

        worker = threading.Thread(target=run, daemon=True)
        t0 = self._monotonic()
        worker.start()
        worker.join(self.timeout_s)
        latency = self._monotonic() - t0
        if worker.is_alive():
            # Before giving up, while the call is still open: ask /slots.
            processing = self._probe_slots(headers)
            status = "TIMEOUT" if processing else "ERROR"
            actual = self._settle(reservation, meter, latency)
            self._record(sink, turn_id=turn_id, call_index=call_index,
                         status=status, usage=None, reservation=reservation,
                         actual=actual, latency=latency)
            if processing:
                raise TimeoutError(
                    f"glimmer call timed out after {latency:.3f}s; server is processing")
            raise RuntimeError(
                f"glimmer call timed out after {latency:.3f}s; server not processing")
        if "error" in box:
            self._record(sink, turn_id=turn_id, call_index=call_index,
                         status="ERROR", usage=None, reservation=reservation,
                         actual=None, latency=latency)
            raise box["error"]
        status, payload = box["result"]
        if status >= 400:
            message = ""
            if isinstance(payload, dict):
                message = str((payload.get("error") or {}).get("message") or payload)
            self._record(sink, turn_id=turn_id, call_index=call_index,
                         status="ERROR", usage=None, reservation=reservation,
                         actual=None, latency=latency)
            raise ProviderError(status, message or f"provider returned {status}")
        usage = payload.get("usage") or {}
        actual = self._settle(reservation, meter, latency)
        self._record(sink, turn_id=turn_id, call_index=call_index,
                     status="OK", usage=usage, reservation=reservation,
                     actual=actual, latency=latency)
        return payload, usage, latency
