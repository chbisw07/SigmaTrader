from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.config_files import load_zerodha_symbol_map
from app.models import User
from app.schemas.webhook import TradeDetails, TradingViewWebhookPayload
from app.services.tradingview_zerodha_adapter import (
    NormalizedAlert,
    normalize_tradingview_payload_for_zerodha,
)


def test_load_zerodha_symbol_map_missing_file(tmp_path) -> None:
    """When no symbol map exists, loader should return empty mapping."""

    os.environ["ST_CONFIG_DIR"] = str(tmp_path)
    mapping = load_zerodha_symbol_map()
    assert mapping == {}


def test_normalize_payload_uses_symbol_mapping(tmp_path, monkeypatch) -> None:
    """Adapter should apply config-based symbol overrides when present."""

    # Prepare a config dir with a minimal symbol map.
    cfg_dir = tmp_path
    os.environ["ST_CONFIG_DIR"] = str(cfg_dir)

    symbol_map = {"NSE": {"SCHNEIDER": "SCHNEIDER-EQ"}}
    (cfg_dir / "zerodha_symbol_map.json").write_text(
        json.dumps(symbol_map), encoding="utf-8"
    )

    # Build a synthetic TradingView payload.
    payload = TradingViewWebhookPayload(
        secret="s",
        platform="TRADINGVIEW",
        strategy_name="symmap-test",
        st_user_id="user",
        symbol="NSE:SCHNEIDER",
        exchange="NSE",
        interval="15",
        trade_details=TradeDetails(
            order_action="BUY",
            quantity=10,
            price=100.0,
            product="CNC",
        ),
        bar_time=datetime.now(timezone.utc),
    )
    user = User(
        id=1,  # type: ignore[arg-type]
        username="user",
        password_hash="x",
        role="TRADER",
        display_name="User",
    )

    normalized: NormalizedAlert = normalize_tradingview_payload_for_zerodha(
        payload, user
    )

    assert normalized.broker_exchange == "NSE"
    # Should be remapped using the symbol map.
    assert normalized.broker_symbol == "SCHNEIDER-EQ"
    # Symbol display should remain the original TradingView symbol.
    assert normalized.symbol_display == "NSE:SCHNEIDER"
