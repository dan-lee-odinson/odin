"""Study step (AGENTS §4.4): one spark call reads all the COSMOS docs and
writes ODIN's operations reference. The reference is frozen and hashed;
its SHA-256 is recorded beside it. The real study call runs only with the
Director present; this module also provides the dry-run figures.
"""
import json
from pathlib import Path

import yaml

from odin.adapters.openai_compat import estimate_tokens
from odin.loop.canonical import sha256_tag

REPO_ROOT = Path(__file__).resolve().parents[2]

STUDY_INSTRUCTIONS = """You are writing the body of ODIN's COSMOS operations
reference from the OpenC3 COSMOS documentation below. Code adds the license
header; you write the body only, with no license text and no header.

Who reads it: an AI operator that reads telemetry and sends commands
through COSMOS. Write for that reader, in plain operational language.

Scope: COSMOS only, including command and telemetry definitions, units,
states, limits, limit states and alarms.

Length: at most about 10,000 words.

Requirements for the body:
- Mark every Enterprise-only feature as absent: this build uses the
  open-source edition, so anything the documentation describes as
  Enterprise-only is not available and must be marked absent, never
  presented as usable.

Write the reference body itself and nothing else.
"""

COPYRIGHT_LINE = "Copyright © 2026 OpenC3, Inc."


def license_name(license_text: str) -> str:
    """The license's name, read from the fetched LICENSE.md's title."""
    for line in license_text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line
    raise ValueError("license file has no title")


def reference_header(name: str) -> str:
    """The fixed header code writes (never the model)."""
    return (
        "Written by Muse Spark from the OpenC3 COSMOS v7.2.1 documentation, "
        "and modified from it.\n"
        f"{COPYRIGHT_LINE}\n"
        f"Used under the {name}, a copy of which is in this folder.\n\n"
    )


def validate_reference_header(text: str, name: str) -> None:
    header = text[:600]
    if "Apache" in header or (name and name not in header):
        raise ValueError("reference header names the wrong license")
    if COPYRIGHT_LINE not in header or "modified from it" not in header:
        raise ValueError("reference header missing notice or modification line")


def hash_reference(data: bytes) -> str:
    return sha256_tag(data)


def collect_docs(docs_dir) -> list:
    docs_dir = Path(docs_dir)
    docs = []
    for path in sorted(docs_dir.rglob("*")):
        if path.is_file() and path.name != "LICENSE.md":  # code handles the license
            docs.append({"path": path.relative_to(docs_dir).as_posix(),
                         "text": path.read_text(encoding="utf-8", errors="replace")})
    return docs


def _checked_license(license_path, hash_list_path):
    """(name, text); fails on a missing or altered license file."""
    import hashlib

    license_path = Path(license_path)
    if not license_path.exists():
        raise FileNotFoundError(f"license file missing: {license_path}")
    data = license_path.read_bytes()
    if hash_list_path is not None:
        recorded = {e["path"]: e["sha256"]
                    for e in json.loads(Path(hash_list_path).read_text(encoding="utf-8"))}
        expected = recorded.get("LICENSE.md")
        if expected is None:
            raise ValueError("LICENSE.md not in the recorded hash list")
        if "sha256:" + hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("license file altered: hash mismatch with recorded list")
    text = data.decode("utf-8")
    return license_name(text), text


def build_study_prompt(docs) -> str:
    """Instructions, then the docs, then the requirements once more
    (long inputs follow instructions better when they also come last)."""
    parts = [STUDY_INSTRUCTIONS]
    for doc in docs:
        parts.append(f"\n===== FILE: {doc['path']} =====\n{doc['text']}")
    parts.append("\n===== REQUIREMENTS (repeated) =====\n" + STUDY_INSTRUCTIONS)
    return "".join(parts)


def study_dry_run(docs_dir, max_output_tokens=32000) -> dict:
    """Figures for the Director's ruling; makes no call."""
    docs = collect_docs(docs_dir)
    prompt = build_study_prompt(docs)
    prices = yaml.safe_load(
        (REPO_ROOT / "config" / "prices.yaml").read_text(encoding="utf-8"))["spark"]
    input_tokens = estimate_tokens(prompt.encode("utf-8"))
    worst = (input_tokens * prices["input_per_mtok"]
             + max_output_tokens * prices["output_per_mtok"]) / 1_000_000
    return {
        "files": len(docs),
        "bytes": sum(len(d["text"].encode("utf-8")) for d in docs),
        "input_tokens_est": input_tokens,
        "max_output_tokens": max_output_tokens,
        "worst_case_usd": worst,
    }


def run_study(*, docs_dir, adapter, out_path, record_path, license_path=None,
              hash_list_path=None, meter=None) -> dict:
    """One study call through the given adapter; freeze and hash the result.

    Code prepends the fixed license header and keeps the license text
    beside the frozen reference, its hash checked against the recorded
    list. The model writes the body only. Docs are verified against the
    recorded list before any call; a cut-off or empty body freezes
    nothing (no reference, no license copy, no record).
    """
    import hashlib
    import shutil
    from datetime import datetime, timezone

    from odin.study.fetch_docs import check_tree

    docs_dir = Path(docs_dir)
    if hash_list_path is not None:
        problems = check_tree(docs_dir, hash_list_path)
        if problems:
            raise ValueError("docs check failed before the study call: "
                             + "; ".join(problems[:5]))
    name, _text = _checked_license(
        license_path or (docs_dir / "LICENSE.md"), hash_list_path)
    docs = collect_docs(docs_dir)
    prompt = build_study_prompt(docs)
    sink = []
    result = adapter.complete(prompt=prompt.encode("utf-8"),
                              bundle={"turn_kind": "ACT", "report_kind": None,
                                      "turn_id": 1},
                              plain_text=True, meter=meter, model_call_sink=sink)
    body = result["raw"]
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    if result.get("cut_off") or result.get("finish_reason") == "length":
        raise RuntimeError("study answer was cut off by the output cap; "
                           "nothing frozen")
    if not body.strip():
        raise RuntimeError("study answer was empty; nothing frozen")
    reference = (reference_header(name) + body).encode("utf-8")
    validate_reference_header(reference.decode("utf-8"), name)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(reference)
    shutil.copyfile(license_path or (docs_dir / "LICENSE.md"),
                    out_path.parent / "LICENSE.md")
    call = sink[-1] if sink else {}
    record = {
        "reference": out_path.name, "sha256": hash_reference(reference),
        "docs_files": len(docs),
        "model": getattr(adapter, "model_id", None),
        "provider": getattr(adapter, "provider", None),
        "reasoning_effort": getattr(adapter, "reasoning_effort", None),
        "max_output_tokens": getattr(adapter, "max_output_tokens", None),
        "timeout_s": getattr(adapter, "timeout_s", None),
        "input_tokens": result.get("input_tokens"),
        "cached_input_tokens": result.get("cached_input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "reasoning_tokens": result.get("reasoning_tokens"),
        "actual_cost_usd": call.get("actual_cost_usd"),
        "finish_reason": result.get("finish_reason"),
        "latency_s": result.get("latency_s"),
        "utc": datetime.now(timezone.utc).isoformat(),
        "instructions_sha256": sha256_tag(STUDY_INSTRUCTIONS.encode("utf-8")),
        "docs_hashes_sha256": (
            "sha256:" + hashlib.sha256(
                Path(hash_list_path).read_bytes()).hexdigest()
            if hash_list_path is not None else None),
    }
    Path(record_path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv=None) -> int:
    """Director-run entry point. Settings are required arguments: the study
    call's reasoning level, cap and timeout are the Director's to rule, so
    this script has no defaults for them. --dry-run makes no call."""
    import argparse

    from odin.adapters.spark import SparkAdapter
    from odin.study.fetch_docs import CACHE_DIR, HASH_LIST

    parser = argparse.ArgumentParser(prog="study")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reasoning", default=None)
    parser.add_argument("--max-output", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--docs", default=str(CACHE_DIR))
    parser.add_argument("--out", default=str(Path(__file__).parent / "cosmos_reference.md"))
    parser.add_argument("--record", default=str(Path(__file__).parent / "cosmos_reference.json"))
    args = parser.parse_args(argv)
    if args.dry_run:
        figures = study_dry_run(args.docs, max_output_tokens=args.max_output or 32000)
        print(f"files={figures['files']} bytes={figures['bytes']} "
              f"input_tokens_est={figures['input_tokens_est']} "
              f"worst_case_usd=${figures['worst_case_usd']:.4f} "
              f"(at cap {args.max_output or 32000})")
        print("the real call takes --reasoning, --max-output and --timeout "
              "on the command line (the Director's settings; no defaults here)")
        return 0
    if args.reasoning is None or args.max_output is None or args.timeout is None:
        print("missing study settings: --reasoning, --max-output and --timeout "
              "are all required (no defaults)")
        return 2
    from odin.spend.meter import SpendMeter

    adapter = SparkAdapter(reasoning_effort=args.reasoning,
                           max_output_tokens=args.max_output,
                           timeout_s=args.timeout)
    meter = SpendMeter(ledger_path=Path(args.record).with_suffix(".spend.jsonl"))
    try:
        record = run_study(docs_dir=args.docs, adapter=adapter, out_path=args.out,
                           record_path=args.record, hash_list_path=HASH_LIST,
                           meter=meter)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"study call not completed: {exc}")
        return 1
    print(f"reference written: {args.out} sha256={record['sha256']} "
          f"(LICENSE.md kept beside it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
