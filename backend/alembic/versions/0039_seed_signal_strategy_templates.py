"""Seed default Signal Strategy templates (DSL V3).

Revision ID: 0039
Revises: 0038
Create Date: 2025-12-24
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, List

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def _norm_regime(raw: str) -> str:
    return re.sub(r"\s+", "_", (raw or "").strip().upper())


def _dump_regimes(regimes: List[str]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for r in regimes:
        rr = _norm_regime(r)
        if not rr or not re.fullmatch(r"[A-Z][A-Z0-9_]*", rr):
            continue
        if rr in seen:
            continue
        seen.add(rr)
        out.append(rr)
    return _json_dump(out)


def _dump_tags(tags: List[str]) -> str:
    cleaned = [t.strip() for t in tags if (t or "").strip()]
    out: list[str] = []
    seen: set[str] = set()
    for t in cleaned:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return _json_dump(out)


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)

    strategies_table = sa.table(
        "signal_strategies",
        sa.column("id", sa.Integer),
        sa.column("scope", sa.String),
        sa.column("owner_id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("tags_json", sa.Text),
        sa.column("regimes_json", sa.Text),
        sa.column("latest_version", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    versions_table = sa.table(
        "signal_strategy_versions",
        sa.column("id", sa.Integer),
        sa.column("strategy_id", sa.Integer),
        sa.column("version", sa.Integer),
        sa.column("inputs_json", sa.Text),
        sa.column("variables_json", sa.Text),
        sa.column("outputs_json", sa.Text),
        sa.column("compatibility_json", sa.Text),
        sa.column("enabled", sa.Boolean),
        sa.column("created_at", sa.DateTime),
    )

    templates: list[dict[str, Any]] = [
        {
            "name": "T-BULL SMA crossover + RSI",
            "description": (
                "Bull-trend template: fast SMA above slow SMA with RSI confirmation. "
                "Use for swing entries in bullish regimes."
            ),
            "tags": ["template", "trend", "momentum", "sma", "rsi"],
            "regimes": ["BULL", "SWING_TRADING"],
            "inputs": [
                {"name": "FAST", "type": "number", "default": 20},
                {"name": "SLOW", "type": "number", "default": 50},
                {"name": "RSI_LEN", "type": "number", "default": 14},
                {"name": "RSI_MIN", "type": "number", "default": 50},
                {"name": "TF", "type": "timeframe", "default": "1d"},
            ],
            "variables": [],
            "outputs": [
                {
                    "name": "signal",
                    "kind": "SIGNAL",
                    "dsl": (
                        "SMA(close, FAST, TF) > SMA(close, SLOW, TF) "
                        "AND RSI(close, RSI_LEN, TF) > RSI_MIN"
                    ),
                },
                {
                    "name": "fast_sma",
                    "kind": "OVERLAY",
                    "dsl": "SMA(close, FAST, TF)",
                    "plot": "price",
                },
                {
                    "name": "slow_sma",
                    "kind": "OVERLAY",
                    "dsl": "SMA(close, SLOW, TF)",
                    "plot": "price",
                },
            ],
        },
        {
            "name": "T-BEAR SMA breakdown + RSI",
            "description": (
                "Bear-trend template: fast SMA below slow SMA with weak RSI. "
                "Use for risk-off filters or short-bias screening."
            ),
            "tags": ["template", "trend", "bear", "sma", "rsi"],
            "regimes": ["BEAR", "SWING_TRADING"],
            "inputs": [
                {"name": "FAST", "type": "number", "default": 20},
                {"name": "SLOW", "type": "number", "default": 50},
                {"name": "RSI_LEN", "type": "number", "default": 14},
                {"name": "RSI_MAX", "type": "number", "default": 50},
                {"name": "TF", "type": "timeframe", "default": "1d"},
            ],
            "variables": [],
            "outputs": [
                {
                    "name": "signal",
                    "kind": "SIGNAL",
                    "dsl": (
                        "SMA(close, FAST, TF) < SMA(close, SLOW, TF) "
                        "AND RSI(close, RSI_LEN, TF) < RSI_MAX"
                    ),
                },
                {
                    "name": "fast_sma",
                    "kind": "OVERLAY",
                    "dsl": "SMA(close, FAST, TF)",
                    "plot": "price",
                },
                {
                    "name": "slow_sma",
                    "kind": "OVERLAY",
                    "dsl": "SMA(close, SLOW, TF)",
                    "plot": "price",
                },
            ],
        },
        {
            "name": "T-SIDEWAYS RSI mean reversion",
            "description": (
                "Sideways/mean-reversion template: buy when RSI is oversold and "
                "sell when RSI is overbought. Useful in range-bound markets."
            ),
            "tags": ["template", "sideways", "mean-reversion", "rsi"],
            "regimes": ["SIDEWAYS", "SWING_TRADING"],
            "inputs": [
                {"name": "RSI_LEN", "type": "number", "default": 14},
                {"name": "RSI_LO", "type": "number", "default": 30},
                {"name": "RSI_HI", "type": "number", "default": 70},
                {"name": "TF", "type": "timeframe", "default": "1d"},
            ],
            "variables": [],
            "outputs": [
                {
                    "name": "buy",
                    "kind": "SIGNAL",
                    "dsl": "RSI(close, RSI_LEN, TF) < RSI_LO",
                },
                {
                    "name": "sell",
                    "kind": "SIGNAL",
                    "dsl": "RSI(close, RSI_LEN, TF) > RSI_HI",
                },
                {
                    "name": "rsi",
                    "kind": "OVERLAY",
                    "dsl": "RSI(close, RSI_LEN, TF)",
                    "plot": "separate",
                },
            ],
        },
        {
            "name": "T-DAY VWAP reclaim",
            "description": (
                "Day-trading template: price above VWAP on intraday timeframe. "
                "Use as a simple trend filter for intraday momentum."
            ),
            "tags": ["template", "day-trading", "vwap", "intraday"],
            "regimes": ["DAY_TRADING"],
            "inputs": [
                {"name": "TF", "type": "timeframe", "default": "5m"},
            ],
            "variables": [],
            "outputs": [
                {
                    "name": "signal",
                    "kind": "SIGNAL",
                    "dsl": "close > VWAP(hlc3, volume, TF)",
                },
                {
                    "name": "vwap",
                    "kind": "OVERLAY",
                    "dsl": "VWAP(hlc3, volume, TF)",
                    "plot": "price",
                },
            ],
        },
        {
            "name": "T-SWING EMA trend + returns",
            "description": (
                "Swing-trading template: price above EMA with positive short-term "
                "return. Use for momentum swing entries."
            ),
            "tags": ["template", "swing", "ema", "momentum"],
            "regimes": ["SWING_TRADING"],
            "inputs": [
                {"name": "EMA_LEN", "type": "number", "default": 20},
                {"name": "TF", "type": "timeframe", "default": "1d"},
                {"name": "RET_MIN", "type": "number", "default": 0.0},
            ],
            "variables": [],
            "outputs": [
                {
                    "name": "signal",
                    "kind": "SIGNAL",
                    "dsl": (
                        "close > EMA(close, EMA_LEN, TF) "
                        "AND RET(close, TF) > RET_MIN"
                    ),
                },
                {
                    "name": "ema",
                    "kind": "OVERLAY",
                    "dsl": "EMA(close, EMA_LEN, TF)",
                    "plot": "price",
                },
            ],
        },
    ]

    for t in templates:
        name = t["name"]
        existing_id = conn.execute(
            sa.text(
                "SELECT id FROM signal_strategies "
                "WHERE scope = 'GLOBAL' AND owner_id IS NULL AND name = :name"
            ),
            {"name": name},
        ).scalar()

        if existing_id is None:
            conn.execute(
                sa.insert(strategies_table).values(
                    scope="GLOBAL",
                    owner_id=None,
                    name=name,
                    description=t["description"],
                    tags_json=_dump_tags(t["tags"]),
                    regimes_json=_dump_regimes(t["regimes"]),
                    latest_version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            strategy_id = conn.execute(
                sa.text(
                    "SELECT id FROM signal_strategies "
                    "WHERE scope = 'GLOBAL' AND owner_id IS NULL AND name = :name"
                ),
                {"name": name},
            ).scalar()
        else:
            strategy_id = existing_id

        if strategy_id is None:
            continue

        ver_exists = conn.execute(
            sa.text(
                "SELECT id FROM signal_strategy_versions "
                "WHERE strategy_id = :sid AND version = 1"
            ),
            {"sid": int(strategy_id)},
        ).scalar()
        if ver_exists is None:
            conn.execute(
                sa.insert(versions_table).values(
                    strategy_id=int(strategy_id),
                    version=1,
                    inputs_json=_json_dump(t["inputs"]),
                    variables_json=_json_dump(t["variables"]),
                    outputs_json=_json_dump(t["outputs"]),
                    compatibility_json=_json_dump({"requires_holdings_metrics": False}),
                    enabled=True,
                    created_at=now,
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    names = [
        "T-BULL SMA crossover + RSI",
        "T-BEAR SMA breakdown + RSI",
        "T-SIDEWAYS RSI mean reversion",
        "T-DAY VWAP reclaim",
        "T-SWING EMA trend + returns",
    ]
    conn.execute(
        sa.text(
            "DELETE FROM signal_strategies "
            "WHERE scope = 'GLOBAL' AND owner_id IS NULL AND name IN :names"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": names},
    )
