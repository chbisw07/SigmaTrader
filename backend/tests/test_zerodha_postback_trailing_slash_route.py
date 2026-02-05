from __future__ import annotations


def test_zerodha_postback_trailing_slash_route_exists() -> None:
    from app.api import zerodha

    paths = {getattr(r, "path", None) for r in zerodha.router.routes}
    assert "/postback" in paths
    assert "/postback/" in paths

