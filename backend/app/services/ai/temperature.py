from __future__ import annotations


def default_temperature_for_openai_model(model: str) -> float | None:
    """
    Some OpenAI models reject non-default temperature values.

    Return:
      - None => omit temperature (use provider default)
      - float => send explicit temperature
    """

    m = (model or "").strip().lower()
    if m.startswith("gpt-5"):
        return None
    return 0.0


def effective_temperature(*, provider_id: str, model: str, configured: float | None) -> float | None:
    """
    Compute temperature to send to the provider.

    If `configured` is set, always use it. Otherwise choose a safe default.
    """

    if configured is not None:
        return float(configured)

    pid = (provider_id or "").strip().lower()
    if pid == "openai":
        return default_temperature_for_openai_model(model)
    # For other providers, don't force a value unless explicitly set.
    return None


__all__ = ["default_temperature_for_openai_model", "effective_temperature"]

