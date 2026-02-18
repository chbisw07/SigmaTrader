from __future__ import annotations

import os
import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import SystemEvent
from app.services.ai.provider_keys import decrypt_key_value, get_key

client = TestClient(app)


def setup_module() -> None:  # type: ignore[override]
    os.environ["ST_CRYPTO_KEY"] = "test-ai-provider-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _enable_provider() -> None:
    resp = client.put("/api/ai/config", json={"enabled": True})
    assert resp.status_code == 200


def test_list_providers() -> None:
    resp = client.get("/api/ai/providers")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert {"openai", "google", "local_ollama", "local_lmstudio"}.issubset(ids)


def test_keys_crud_masked_only() -> None:
    resp = client.post(
        "/api/ai/keys",
        json={
            "provider": "openai",
            "key_name": "default",
            "api_key_value": "sk-test-secret-value-abcdef1234",
        },
    )
    assert resp.status_code == 201
    row = resp.json()
    assert row["provider"] == "openai"
    assert row["key_name"] == "default"
    assert "key_masked" in row and "abcdef" not in row["key_masked"]

    resp_list = client.get("/api/ai/keys?provider=openai")
    assert resp_list.status_code == 200
    rows = resp_list.json()
    assert len(rows) >= 1
    assert all("api_key_value" not in r for r in rows)

    kid = row["id"]
    resp_upd = client.put(
        f"/api/ai/keys/{kid}",
        json={"key_name": "renamed", "api_key_value": "sk-new-secret-zzzz9999"},
    )
    assert resp_upd.status_code == 200
    assert resp_upd.json()["key_name"] == "renamed"

    resp_del = client.delete(f"/api/ai/keys/{kid}")
    assert resp_del.status_code == 204


def test_key_encrypt_roundtrip() -> None:
    original = "sk-roundtrip-1234567890"
    row = client.post(
        "/api/ai/keys",
        json={"provider": "openai", "key_name": "rt", "api_key_value": original},
    ).json()
    with SessionLocal() as db:
        k = get_key(db, key_id=int(row["id"]), user_id=None)
        assert k is not None
        assert decrypt_key_value(get_settings(), k) == original


def test_models_discover_requires_enabled() -> None:
    # Disabled by default.
    resp = client.post("/api/ai/models/discover", json={"provider": "local_ollama"})
    assert resp.status_code == 403
    _enable_provider()


def test_openai_models_discover_and_test(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_provider()

    # Create key.
    k = client.post(
        "/api/ai/keys",
        json={"provider": "openai", "key_name": "k1", "api_key_value": "sk-test-1234567890"},
    ).json()

    class FakeResp:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict:
            return self._payload

    class FakeHttpxClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
            pass

        def close(self) -> None:
            return None

        def get(self, url: str, *args, **kwargs) -> FakeResp:  # noqa: ANN002,ANN003
            assert url.endswith("/v1/models")
            return FakeResp(200, {"data": [{"id": "gpt-test"}]})

        def post(self, url: str, *args, **kwargs) -> FakeResp:  # noqa: ANN002,ANN003
            assert url.endswith("/v1/chat/completions")
            return FakeResp(
                200,
                {
                    "choices": [{"message": {"content": "OK"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

    monkeypatch.setattr("app.services.ai.providers.openai.httpx.Client", FakeHttpxClient)

    resp_m = client.post(
        "/api/ai/models/discover",
        json={"provider": "openai", "key_id": k["id"]},
    )
    assert resp_m.status_code == 200
    models = resp_m.json()["models"]
    assert any(m["id"] == "gpt-test" for m in models)

    # Set config so /test can use defaults too.
    resp_cfg = client.put(
        "/api/ai/config",
        json={"provider": "openai", "active_key_id": k["id"], "model": "gpt-test", "do_not_send_pii": True},
    )
    assert resp_cfg.status_code == 200

    resp_t = client.post("/api/ai/test", json={"prompt": "Say OK"})
    assert resp_t.status_code == 200
    out = resp_t.json()
    assert out["text"] == "OK"
    assert out["latency_ms"] >= 0

    with SessionLocal() as db:
        ev = (
            db.query(SystemEvent)
            .filter(SystemEvent.category == "AI_PROVIDER")
            .order_by(SystemEvent.created_at.desc())
            .first()
        )
        assert ev is not None
        details_raw = ev.details or "{}"
        details = json.loads(details_raw) if isinstance(details_raw, str) else {}
        assert details.get("event_type") == "AI_TEST_RUN"
        # When do_not_send_pii is true we should not store prompt preview.
        assert "prompt_preview" not in details
        assert isinstance(details.get("prompt_hash"), str)


def test_ollama_models_discover_and_test(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_provider()

    class FakeResp:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict:
            return self._payload

    class FakeHttpxClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
            pass

        def close(self) -> None:
            return None

        def get(self, url: str, *args, **kwargs) -> FakeResp:  # noqa: ANN002,ANN003
            assert url.endswith("/api/tags")
            return FakeResp(200, {"models": [{"name": "llama3"}]})

        def post(self, url: str, *args, **kwargs) -> FakeResp:  # noqa: ANN002,ANN003
            assert url.endswith("/api/generate")
            return FakeResp(200, {"response": "OK", "eval_count": 2, "prompt_eval_count": 1})

    monkeypatch.setattr("app.services.ai.providers.ollama.httpx.Client", FakeHttpxClient)

    # Configure provider.
    resp_cfg = client.put(
        "/api/ai/config",
        json={
            "provider": "local_ollama",
            "base_url": "http://localhost:11434",
            "model": "llama3",
        },
    )
    assert resp_cfg.status_code == 200

    resp_m = client.post(
        "/api/ai/models/discover",
        json={"provider": "local_ollama", "base_url": "http://localhost:11434"},
    )
    assert resp_m.status_code == 200
    models = resp_m.json()["models"]
    assert any(m["id"] == "llama3" for m in models)

    resp_t = client.post(
        "/api/ai/test",
        json={"provider": "local_ollama", "model": "llama3", "base_url": "http://localhost:11434", "prompt": "Say OK"},
    )
    assert resp_t.status_code == 200
    assert resp_t.json()["text"] == "OK"


def test_lmstudio_models_discover_and_test(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_provider()

    class FakeResp:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict:
            return self._payload

    class FakeHttpxClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
            pass

        def close(self) -> None:
            return None

        def get(self, url: str, *args, **kwargs) -> FakeResp:  # noqa: ANN002,ANN003
            assert url.endswith("/v1/models")
            return FakeResp(200, {"data": [{"id": "local-model"}]})

        def post(self, url: str, *args, **kwargs) -> FakeResp:  # noqa: ANN002,ANN003
            assert url.endswith("/v1/chat/completions")
            return FakeResp(
                200,
                {
                    "choices": [{"message": {"content": "OK"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

    monkeypatch.setattr("app.services.ai.providers.openai_compatible.httpx.Client", FakeHttpxClient)

    resp_cfg = client.put(
        "/api/ai/config",
        json={
            "provider": "local_lmstudio",
            "base_url": "http://localhost:1234/v1",
            "model": "local-model",
        },
    )
    assert resp_cfg.status_code == 200

    resp_m = client.post(
        "/api/ai/models/discover",
        json={"provider": "local_lmstudio", "base_url": "http://localhost:1234/v1"},
    )
    assert resp_m.status_code == 200
    assert any(m["id"] == "local-model" for m in resp_m.json()["models"])

    resp_t = client.post(
        "/api/ai/test",
        json={
            "provider": "local_lmstudio",
            "model": "local-model",
            "base_url": "http://localhost:1234/v1",
            "prompt": "Say OK",
        },
    )
    assert resp_t.status_code == 200
    assert resp_t.json()["text"] == "OK"


def test_google_models_discover_and_test(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_provider()

    k = client.post(
        "/api/ai/keys",
        json={"provider": "google", "key_name": "g1", "api_key_value": "AIza-test-1234567890"},
    ).json()

    class FakeResp:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = str(payload)

        def json(self) -> dict:
            return self._payload

    class FakeHttpxClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
            pass

        def close(self) -> None:
            return None

        def get(self, url: str, *args, **kwargs) -> FakeResp:  # noqa: ANN002,ANN003
            assert "models?key=" in url
            return FakeResp(
                200,
                {"models": [{"name": "models/gemini-test", "displayName": "Gemini Test"}]},
            )

        def post(self, url: str, *args, **kwargs) -> FakeResp:  # noqa: ANN002,ANN003
            assert ":generateContent?key=" in url
            return FakeResp(
                200,
                {
                    "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
                    "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1, "totalTokenCount": 2},
                },
            )

    monkeypatch.setattr("app.services.ai.providers.google_gemini.httpx.Client", FakeHttpxClient)

    resp_m = client.post(
        "/api/ai/models/discover",
        json={"provider": "google", "key_id": k["id"]},
    )
    assert resp_m.status_code == 200
    assert any(m["id"] == "gemini-test" for m in resp_m.json()["models"])

    resp_cfg = client.put(
        "/api/ai/config",
        json={"provider": "google", "active_key_id": k["id"], "model": "gemini-test"},
    )
    assert resp_cfg.status_code == 200

    resp_t = client.post("/api/ai/test", json={"prompt": "Say OK"})
    assert resp_t.status_code == 200
    assert resp_t.json()["text"] == "OK"
