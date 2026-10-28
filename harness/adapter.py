"""What RUN_START records of the run's model's adapter (the Director's ruling on U57, 28 October 2026).

The adapter is Muse Code's, and its code makes the call, so it is the source of the provider and the
endpoint. RUN_START's provider is the adapter's, and its endpoint is the base URL the adapter calls, which
CONTRACT.md §11.1 asks every run to record; both are null for the stand-in. The adapter is built as ODIN
builds it, by Muse Code's build_adapter from config/models.yaml, and is given a development run's endpoint in
place of its built-in one. A SCORED run calls only the built-in endpoint. The adapter's model ID is checked
against the model's frozen block before any spend, as S8 checks every MODEL_CALL's at scoring (U56).
"""

from harness.instructions import NotFrozen


def adapter_settings(model_config, block, *, mode, endpoint=None):
    """{provider, endpoint} for RUN_START, both null for the stand-in. block: the model's frozen block
    (harness/freeze.py). endpoint: the base URL a development run gives the adapter instead of its built-in
    one. Raises NotFrozen if the adapter's model ID is not the block's model, and ValueError for a SCORED run
    given another endpoint, or a stand-in run given any."""
    if model_config == "stand_in":
        if endpoint is not None:
            raise ValueError("the stand-in calls no endpoint")
        return {"provider": None, "endpoint": None}
    from odin.adapters.settings import build_adapter

    adapter = build_adapter(model_config, **({"base_url": endpoint} if endpoint is not None else {}))
    if adapter.model_id != block["model"]:
        raise NotFrozen(f"{model_config}'s adapter calls {adapter.model_id}, not its frozen block's {block['model']}")
    built_in = type(adapter).endpoint.rstrip("/")
    if mode == "SCORED" and adapter.base_url != built_in:
        raise ValueError(f"a SCORED run calls only {model_config}'s built-in endpoint, {built_in}, "
                         f"not {adapter.base_url}")
    return {"provider": adapter.provider, "endpoint": adapter.base_url}
