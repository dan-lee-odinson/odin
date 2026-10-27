"""Prompt assembly (§4.1): stable content first, changing parts last."""
import json


def build_prompt(bundle: dict, instructions: str, frozen_reference: str) -> bytes:
    """Instructions, frozen reference, plan and procedures first (cacheable);
    the turn's changing bundle last."""
    stable = {
        "instructions": instructions,
        "frozen_reference": frozen_reference,
        "plan": bundle.get("plan"),
        "procedures": bundle.get("procedures"),
    }
    stable_text = json.dumps(stable, sort_keys=True, ensure_ascii=False)
    bundle_text = json.dumps(bundle, sort_keys=True, ensure_ascii=False)
    text = (
        "=== INSTRUCTIONS ===\n" + instructions
        + "\n=== FROZEN REFERENCE ===\n" + frozen_reference
        + "\n=== PLAN AND PROCEDURES (stable) ===\n" + stable_text
        + "\n=== THIS TURN (changing) ===\n" + bundle_text + "\n"
    )
    return text.encode("utf-8")
