from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.main import app


client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_AI_ASSISTANT_ENABLED"] = "1"
    os.environ["ST_AI_EXECUTION_KILL_SWITCH"] = "0"
    os.environ["ST_CRYPTO_KEY"] = "test-ai-websearch-prefetch"
    os.environ["ST_ENABLE_REMOTE_WEB_SEARCH"] = "1"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _enable_openai_provider_with_web_search() -> None:
    k = client.post(
        "/api/ai/keys",
        json={"provider": "openai", "key_name": "k1", "api_key_value": "sk-test-1234567890"},
    ).json()
    resp_cfg = client.put(
        "/api/ai/config",
        json={
            "enabled": True,
            "provider": "openai",
            "active_key_id": k["id"],
            "model": "gpt-test",
            "do_not_send_pii": True,
            "enable_web_search": True,
        },
    )
    assert resp_cfg.status_code == 200


@pytest.fixture()
def disable_kite_mcp() -> None:
    # Ensure broker MCP isn't required for a search-only question.
    resp = client.put("/api/settings/ai", json={"feature_flags": {"kite_mcp_enabled": False}, "kite_mcp": {"server_url": ""}})
    assert resp.status_code == 200


def test_openai_responses_web_search_prefetch_injects_context(monkeypatch: pytest.MonkeyPatch, disable_kite_mcp) -> None:
    _enable_openai_provider_with_web_search()

    from app.services.ai_toolcalling import orchestrator as orch
    from app.services.ai_toolcalling.openai_toolcaller import OpenAiAssistantTurn

    called = {"ws": 0}

    async def fake_openai_responses_plain(*, api_key, model, messages, **kwargs):  # noqa: ANN001, ARG001
        called["ws"] += 1
        # Return a small web-search summary; orchestrator should inject this into main messages.
        return OpenAiAssistantTurn(
            content="Web summary: recent headlines mention geopolitical escalation.",
            tool_calls=[],
            raw={"web_search": {"calls": 1, "source_domains": ["example.com"]}},
        )

    async def fake_openai_chat_with_tools(*, api_key, model, messages, tools, **kwargs):  # noqa: ANN001, ARG001
        # Confirm injected web_search_context is present.
        joined = "\n".join(str(m.get("content") or "") for m in (messages or []) if isinstance(m, dict))
        assert "web_search_context" in joined
        return OpenAiAssistantTurn(content="OK", tool_calls=[], raw={})

    monkeypatch.setattr(orch, "openai_responses_plain", fake_openai_responses_plain)
    monkeypatch.setattr(orch, "openai_chat_with_tools", fake_openai_chat_with_tools)

    msg = "Why ANANTRAJ stock price is falling since the war escalation?"
    resp = client.post("/api/ai/chat", json={"account_id": "default", "message": msg})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("assistant_message") == "OK"
    assert called["ws"] == 1
