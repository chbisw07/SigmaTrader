from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

try:  # Pydantic v2
    from pydantic import ConfigDict, field_validator, model_validator

    PYDANTIC_V2 = True
except ImportError:  # pragma: no cover - Pydantic v1 fallback
    from pydantic import root_validator, validator

    PYDANTIC_V2 = False
    ConfigDict = dict  # type: ignore[assignment]

    def model_validator(*, mode: str = "after") -> Callable[[Callable[..., Any]], Any]:
        """Compatibility shim mapping model_validator -> root_validator.

        For Pydantic v1 this decorator behaves like:
        - mode=\"before\" -> root_validator(pre=True)
        - mode=\"after\"  -> root_validator(pre=False)
        """

        pre = mode == "before"

        def decorator(fn: Callable[..., Any]) -> Any:
            return root_validator(pre=pre, skip_on_failure=True)(fn)

        return decorator

    def field_validator(
        *names: str,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Any]:
        """Compatibility shim mapping field_validator -> validator for v1."""

        def decorator(fn: Callable[..., Any]) -> Any:
            return validator(*names, **kwargs)(fn)

        return decorator


def model_to_dict(model: BaseModel, **kwargs: Any) -> dict[str, Any]:
    """Return a model as a dict for both Pydantic v1 and v2."""

    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)  # type: ignore[call-arg]
    return model.dict(**kwargs)  # type: ignore[call-arg]


def model_to_json(model: BaseModel, **kwargs: Any) -> str:
    """Return a model as JSON for both Pydantic v1 and v2."""

    if hasattr(model, "model_dump_json"):
        return model.model_dump_json(**kwargs)  # type: ignore[call-arg]
    return model.json(**kwargs)  # type: ignore[call-arg]


__all__ = [
    "ConfigDict",
    "field_validator",
    "model_validator",
    "model_to_dict",
    "model_to_json",
    "PYDANTIC_V2",
]
