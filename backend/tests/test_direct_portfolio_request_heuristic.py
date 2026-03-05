from __future__ import annotations

from app.services.ai_toolcalling.orchestrator import _parse_direct_portfolio_request


def test_direct_portfolio_request_allows_simple_listing() -> None:
    req = _parse_direct_portfolio_request("Show my holdings")
    assert req is not None
    assert req.want_holdings is True


def test_direct_portfolio_request_skips_when_analysis_requested() -> None:
    req = _parse_direct_portfolio_request("Show my holdings and analyze sector developments")
    assert req is None


def test_direct_portfolio_request_skips_when_news_requested() -> None:
    req = _parse_direct_portfolio_request("Show my portfolio news impact today")
    assert req is None

