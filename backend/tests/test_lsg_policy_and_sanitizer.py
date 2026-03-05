from __future__ import annotations

import os

from app.core.config import get_settings
from app.schemas.ai_settings import AiSettings
from app.services.ai_toolcalling.lsg_policy import evaluate_lsg_policy
from app.services.ai_toolcalling.lsg_sanitizer import sanitize_digest_payload, sanitize_kite_payload


def _settings():
    os.environ["ST_CRYPTO_KEY"] = "test-lsg-salt"
    get_settings.cache_clear()
    return get_settings()


def test_policy_allows_remote_market_data_when_toggle_enabled() -> None:
    cfg = AiSettings()
    cfg.hybrid_llm.enabled = True
    cfg.hybrid_llm.allow_remote_market_data_tools = True
    d = evaluate_lsg_policy(source="remote", tool_name="get_ltp", tm_cfg=cfg)
    assert d.allowed is True


def test_policy_denies_remote_identity_auth_always() -> None:
    cfg = AiSettings()
    cfg.hybrid_llm.enabled = True
    cfg.hybrid_llm.allow_remote_market_data_tools = True
    d = evaluate_lsg_policy(source="remote", tool_name="get_profile", tm_cfg=cfg)
    assert d.allowed is False
    assert d.denial_reason in {"capability", "policy"}


def test_policy_denies_remote_trading_write_always() -> None:
    cfg = AiSettings()
    cfg.hybrid_llm.enabled = True
    d = evaluate_lsg_policy(source="remote", tool_name="place_order", tm_cfg=cfg)
    assert d.allowed is False
    assert d.denial_reason in {"capability", "policy"}


def test_policy_denies_remote_raw_holdings_always() -> None:
    cfg = AiSettings()
    cfg.hybrid_llm.enabled = True
    cfg.hybrid_llm.allow_remote_account_digests = True
    d = evaluate_lsg_policy(source="remote", tool_name="get_holdings", tm_cfg=cfg)
    assert d.allowed is False
    assert d.denial_reason in {"capability", "policy"}

    cfg.hybrid_llm.remote_portfolio_detail_level = "FULL_SANITIZED"  # type: ignore[assignment]
    d2 = evaluate_lsg_policy(source="remote", tool_name="get_holdings", tm_cfg=cfg)
    assert d2.allowed is True


def test_policy_allows_remote_portfolio_digest_only_when_toggle_enabled() -> None:
    cfg = AiSettings()
    cfg.hybrid_llm.enabled = True
    cfg.hybrid_llm.allow_remote_account_digests = False
    d1 = evaluate_lsg_policy(source="remote", tool_name="portfolio_digest", tm_cfg=cfg)
    assert d1.allowed is False

    cfg.hybrid_llm.allow_remote_account_digests = True
    d2 = evaluate_lsg_policy(source="remote", tool_name="portfolio_digest", tm_cfg=cfg)
    assert d2.allowed is True


def test_sanitizer_hashes_ids_and_redacts_identity_fields() -> None:
    settings = _settings()
    payload = {
        "order_id": "oid-123",
        "client_id": "CID-1",
        "email": "a@example.com",
        "name": "Alice",
        "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaaaaaaaaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbb",
        "opaque": "Abcdefghijklmnopqrstuvwxyz0123456789_-Abcdefghijklmnopqrstuvwxyz",
        "ok": True,
    }
    out, meta = sanitize_kite_payload("get_orders", payload, settings=settings, bucket_numbers=False)
    assert isinstance(out, dict)
    assert out.get("order_id", "").startswith("h_")
    assert "client_id" not in out
    assert "email" not in out
    assert "name" not in out
    assert out.get("jwt") == "[REDACTED]"
    assert out.get("opaque") == "[REDACTED]"
    assert "order_id" in out
    assert meta.hashed_fields
    assert meta.redacted_fields


def test_sanitizer_buckets_sensitive_numbers_for_digests_but_not_counts() -> None:
    settings = _settings()
    payload = {"qty": 12, "pnl_total": 1500.0, "count": 3, "counts": {"holdings": 2, "positions": 1}}
    out, _meta = sanitize_digest_payload(payload, settings=settings)
    assert out["qty"] != 12
    assert isinstance(out["qty"], str)
    assert out["pnl_total"] != 1500.0
    assert isinstance(out["pnl_total"], str)
    assert out["count"] == 3
    assert isinstance(out["counts"], dict)
    assert out["counts"]["holdings"] == 2
