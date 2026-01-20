from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services import market_quotes

client = TestClient(app)


def test_market_quotes_endpoint_returns_day_pct(monkeypatch) -> None:
    def fake_get_bulk_quotes(_db, _settings, keys):
        _ = keys
        return {("NSE", "TCS"): {"last_price": 110.0, "prev_close": 100.0}}

    monkeypatch.setattr(
        "app.api.market_data.get_bulk_quotes",
        fake_get_bulk_quotes,
        raising=True,
    )

    res = client.post(
        "/api/market/quotes",
        json={"items": [{"symbol": "TCS", "exchange": "NSE"}]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["items"][0]["symbol"] == "TCS"
    assert data["items"][0]["exchange"] == "NSE"
    assert data["items"][0]["ltp"] == 110.0
    assert data["items"][0]["prev_close"] == 100.0
    assert round(data["items"][0]["day_pct"], 6) == 10.0


def test_market_quotes_service_caches_within_ttl(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_fetch(_db, _settings, instruments):
        calls["n"] += 1
        _ = instruments
        return {("NSE", "TCS"): {"last_price": 123.0, "prev_close": 120.0}}

    monkeypatch.setattr(market_quotes, "_fetch_zerodha_quotes", fake_fetch)

    class DummySettings:
        canonical_market_data_broker = "zerodha"

    dummy_db = object()
    settings = DummySettings()

    out1 = market_quotes.get_bulk_quotes(dummy_db, settings, [("NSE", "TCS")])
    out2 = market_quotes.get_bulk_quotes(dummy_db, settings, [("NSE", "TCS")])

    assert out1[("NSE", "TCS")]["last_price"] == 123.0
    assert out2[("NSE", "TCS")]["last_price"] == 123.0
    assert calls["n"] == 1

