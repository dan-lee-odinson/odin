"""Prompt assembly (U43): built from the bundle alone.

The loop no longer loads any frozen reference itself: the harness attaches
every reference a plan lists, resolved by hash, in the bundle's procedures.
Order keeps prompt caching working: instructions first, then the plan, the
procedures and their attachments (unchanging during a run), then the turn's
changing parts last.
"""
import json


def build_prompt(bundle: dict, instructions: str) -> bytes:
    plan_text = json.dumps(bundle.get("plan"), sort_keys=True, ensure_ascii=False)
    procedures_text = json.dumps(bundle.get("procedures"), sort_keys=True,
                                 ensure_ascii=False)
    changing = {k: v for k, v in bundle.items() if k not in ("plan", "procedures")}
    changing_text = json.dumps(changing, sort_keys=True, ensure_ascii=False)
    text = (
        "=== INSTRUCTIONS ===\n" + instructions
        + "\n=== PLAN (stable) ===\n" + plan_text
        + "\n=== PROCEDURES AND ATTACHMENTS (stable) ===\n" + procedures_text
        + "\n=== THIS TURN (changing) ===\n" + changing_text + "\n"
    )
    return text.encode("utf-8")
