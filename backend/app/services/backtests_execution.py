from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import BacktestRun
from app.schemas.backtests_execution import ExecutionBacktestConfigIn
from app.schemas.backtests_portfolio import PortfolioBacktestConfigIn
from app.services.backtests_portfolio import run_portfolio_backtest


def _parse_base_portfolio_config(
    base_run: BacktestRun,
) -> tuple[int, PortfolioBacktestConfigIn]:
    if base_run.kind != "PORTFOLIO":
        raise ValueError("base_run must be a PORTFOLIO backtest run.")
    if base_run.status != "COMPLETED":
        raise ValueError("base_run must be COMPLETED.")

    try:
        cfg = json.loads(base_run.config_json or "{}")
    except Exception as exc:
        raise ValueError("base_run config_json is not valid JSON.") from exc

    universe = (cfg.get("universe") or {}) if isinstance(cfg, dict) else {}
    group_id = universe.get("group_id")
    if group_id is None:
        raise ValueError("base_run has no universe.group_id.")

    base_config = (cfg.get("config") or {}) if isinstance(cfg, dict) else {}
    try:
        pf_cfg = PortfolioBacktestConfigIn.parse_obj(base_config)
    except ValidationError as exc:
        raise ValueError(f"base_run has invalid portfolio config: {exc}") from exc

    return int(group_id), pf_cfg


def run_execution_backtest(
    db: Session,
    settings: Settings,
    *,
    base_run: BacktestRun,
    config: ExecutionBacktestConfigIn,
    allow_fetch: bool = True,
) -> dict[str, Any]:
    group_id, base_pf_cfg = _parse_base_portfolio_config(base_run)

    ideal_cfg = base_pf_cfg.copy(
        update={
            "fill_timing": "CLOSE",
            "slippage_bps": 0.0,
            "charges_bps": 0.0,
            "charges_model": "BPS",
        }
    )
    realistic_cfg = base_pf_cfg.copy(
        update={
            "fill_timing": config.fill_timing,
            "slippage_bps": float(config.slippage_bps),
            "charges_bps": float(config.charges_bps),
            "charges_model": config.charges_model,
            "charges_broker": config.charges_broker,
            "product": config.product,
            "include_dp_charges": bool(config.include_dp_charges),
        }
    )

    ideal = run_portfolio_backtest(
        db,
        settings,
        group_id=group_id,
        config=ideal_cfg,
        allow_fetch=allow_fetch,
    )
    realistic = run_portfolio_backtest(
        db,
        settings,
        group_id=group_id,
        config=realistic_cfg,
        allow_fetch=allow_fetch,
    )

    ideal_series = (ideal.get("series") or {}) if isinstance(ideal, dict) else {}
    real_series = (realistic.get("series") or {}) if isinstance(realistic, dict) else {}
    ideal_eq = (
        (ideal_series.get("equity") or []) if isinstance(ideal_series, dict) else []
    )
    real_eq = (real_series.get("equity") or []) if isinstance(real_series, dict) else []
    ideal_end = float(ideal_eq[-1]) if ideal_eq else float("nan")
    real_end = float(real_eq[-1]) if real_eq else float("nan")
    delta_end = real_end - ideal_end if ideal_eq and real_eq else float("nan")
    delta_end_pct = (
        (delta_end / ideal_end * 100.0) if ideal_eq and ideal_end != 0 else float("nan")
    )

    return {
        "meta": {
            "base_run_id": int(base_run.id),
            "group_id": group_id,
            "timeframe": base_pf_cfg.timeframe,
            "start_date": base_pf_cfg.start_date.isoformat(),
            "end_date": base_pf_cfg.end_date.isoformat(),
            "strategy": {
                "method": base_pf_cfg.method,
                "cadence": base_pf_cfg.cadence,
            },
            "ideal": {
                "fill_timing": "CLOSE",
                "slippage_bps": 0.0,
                "charges_bps": 0.0,
                "charges_model": "BPS",
            },
            "realistic": {
                "fill_timing": config.fill_timing,
                "slippage_bps": float(config.slippage_bps),
                "charges_bps": float(config.charges_bps),
                "charges_model": config.charges_model,
                "charges_broker": config.charges_broker,
                "product": config.product,
                "include_dp_charges": bool(config.include_dp_charges),
            },
        },
        "ideal": ideal,
        "realistic": realistic,
        "delta": {
            "end_equity_delta": delta_end,
            "end_equity_delta_pct": delta_end_pct,
        },
    }


__all__ = ["run_execution_backtest"]
