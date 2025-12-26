from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

SignalMode = Literal["DSL", "RANKING"]
RankingCadence = Literal["WEEKLY", "MONTHLY"]
RankingMetric = Literal["PERF_PCT"]


class SignalBacktestConfigIn(BaseModel):
    timeframe: Literal["1d"] = "1d"
    start_date: date
    end_date: date

    mode: SignalMode = "DSL"
    dsl: str = ""

    forward_windows: list[int] = Field(default_factory=lambda: [1, 5, 20])

    ranking_metric: RankingMetric = "PERF_PCT"
    ranking_window: int = Field(default=20, ge=1, le=400)
    top_n: int = Field(default=10, ge=1, le=200)
    cadence: RankingCadence = "MONTHLY"


__all__ = [
    "RankingCadence",
    "RankingMetric",
    "SignalBacktestConfigIn",
    "SignalMode",
]
