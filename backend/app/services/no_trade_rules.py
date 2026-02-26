from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time as dt_time, timedelta
from typing import Iterable, Literal, Optional, Set


TradeAction = Literal["TRADE", "NO_TRADE"]
TradeKey = Literal["CNC_BUY", "CNC_SELL", "MIS_BUY", "MIS_SELL"]


@dataclass(frozen=True)
class NoTradeRule:
    start: dt_time
    end: dt_time
    action: TradeAction
    keys: Set[TradeKey]
    raw: str


def _parse_hhmm(s: str) -> Optional[dt_time]:
    raw = (s or "").strip()
    if not raw:
        return None
    if ":" not in raw:
        return None
    hh_s, mm_s = raw.split(":", 1)
    try:
        hh = int(hh_s)
        mm = int(mm_s)
    except Exception:
        return None
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return dt_time(hour=hh, minute=mm)


def _in_range(t: dt_time, start: dt_time, end: dt_time) -> bool:
    # [start, end) in local time; supports cross-midnight windows (end < start).
    if start == end:
        return True
    if end > start:
        return start <= t < end
    return t >= start or t < end


def _expand_keys(tokens: Iterable[str]) -> Set[TradeKey]:
    out: Set[TradeKey] = set()
    for tok in tokens:
        t = (tok or "").strip().upper()
        if not t:
            continue
        if t == "ALL":
            out.update({"CNC_BUY", "CNC_SELL", "MIS_BUY", "MIS_SELL"})
            continue
        if t == "BUY":
            out.update({"CNC_BUY", "MIS_BUY"})
            continue
        if t == "SELL":
            out.update({"CNC_SELL", "MIS_SELL"})
            continue
        if t == "CNC":
            out.update({"CNC_BUY", "CNC_SELL"})
            continue
        if t == "MIS":
            out.update({"MIS_BUY", "MIS_SELL"})
            continue
        if t in {"CNC_BUY", "CNC_SELL", "MIS_BUY", "MIS_SELL"}:
            out.add(t)  # type: ignore[arg-type]
            continue
    return out


def parse_no_trade_rules(text: str | None) -> tuple[list[NoTradeRule], list[str]]:
    """Parse a simple line-oriented ruleset.

    Syntax (one rule per line):
      HH:MM-HH:MM  TRADE|NO_TRADE  <keys>

    keys: comma/space separated tokens from:
      ALL, BUY, SELL, CNC, MIS, CNC_BUY, CNC_SELL, MIS_BUY, MIS_SELL
    """

    raw = (text or "").strip("\n")
    if not raw.strip():
        return [], []

    rules: list[NoTradeRule] = []
    warnings: list[str] = []

    for i, line in enumerate(raw.splitlines(), start=1):
        src = line
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        # Allow trailing comments.
        if "#" in s:
            s = s.split("#", 1)[0].strip()
        parts = [p for p in s.replace("\t", " ").split(" ") if p.strip()]
        if len(parts) < 3:
            warnings.append(f"Line {i}: expected '<start>-<end> <TRADE|NO_TRADE> <keys>'")
            continue

        time_part = parts[0]
        if "-" not in time_part:
            warnings.append(f"Line {i}: invalid time range '{time_part}'")
            continue
        start_s, end_s = time_part.split("-", 1)
        start = _parse_hhmm(start_s)
        end = _parse_hhmm(end_s)
        if start is None or end is None:
            warnings.append(f"Line {i}: invalid HH:MM in range '{time_part}'")
            continue

        action = parts[1].strip().upper()
        if action not in {"TRADE", "NO_TRADE"}:
            warnings.append(f"Line {i}: invalid action '{parts[1]}' (use TRADE or NO_TRADE)")
            continue

        keys_raw = " ".join(parts[2:])
        # Split on commas or spaces.
        toks = []
        for chunk in keys_raw.split(","):
            toks.extend([p for p in chunk.strip().split(" ") if p.strip()])
        keys = _expand_keys(toks)
        if not keys:
            warnings.append(f"Line {i}: no valid keys in '{keys_raw}'")
            continue

        rules.append(NoTradeRule(start=start, end=end, action=action, keys=keys, raw=src))

    return rules, warnings


@dataclass(frozen=True)
class NoTradeMatch:
    action: TradeAction
    start: dt_time
    end: dt_time
    key: TradeKey
    raw: str


def resolve_no_trade_action(
    *,
    rules_text: str | None,
    now_utc: datetime,
    product: str,
    side: str,
) -> NoTradeMatch | None:
    """Return the final matched rule for a given product/side, or None."""

    rules, _warnings = parse_no_trade_rules(rules_text)
    if not rules:
        return None

    try:
        from zoneinfo import ZoneInfo

        now_local = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
        t = now_local.time()
    except Exception:
        t = now_utc.time()

    prod = (product or "").strip().upper()
    sd = (side or "").strip().upper()
    key: TradeKey | None = None
    if prod in {"CNC", "MIS"} and sd in {"BUY", "SELL"}:
        key = f"{prod}_{sd}"  # type: ignore[assignment]
    if key is None:
        return None

    matched: NoTradeMatch | None = None
    for r in rules:
        if key not in r.keys:
            continue
        if not _in_range(t, r.start, r.end):
            continue
        matched = NoTradeMatch(action=r.action, start=r.start, end=r.end, key=key, raw=r.raw)
    return matched


def compute_no_trade_defer_until_utc(
    *,
    now_utc: datetime,
    start: dt_time,
    end: dt_time,
) -> datetime:
    """Compute the next window end as a UTC datetime for deferral.

    The ruleset uses local (IST) wall-clock times. When a match is active,
    AUTO dispatch should be deferred until the end of the matched window.
    """

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Asia/Kolkata")
        now_local = now_utc.astimezone(tz)
    except Exception:
        # Best-effort fallback: treat now_utc as local time.
        tz = None
        now_local = now_utc

    d = now_local.date()
    t = now_local.time()

    # Special case: start==end means "all day" (or "always") per _in_range.
    # Defer until the next day's same wall-clock time.
    if start == end:
        end_local_dt = datetime.combine(d + timedelta(days=1), end)
    elif end > start:
        end_local_dt = datetime.combine(d, end)
    else:
        # Cross-midnight window.
        if t >= start:
            end_local_dt = datetime.combine(d + timedelta(days=1), end)
        else:
            end_local_dt = datetime.combine(d, end)

    if tz is not None:
        end_local_dt = end_local_dt.replace(tzinfo=tz)
        return end_local_dt.astimezone(UTC)
    # Fallback path: keep naive/offset-less datetimes in UTC for storage.
    if end_local_dt.tzinfo is None:
        return end_local_dt.replace(tzinfo=UTC)
    return end_local_dt.astimezone(UTC)


__all__ = [
    "NoTradeMatch",
    "NoTradeRule",
    "TradeAction",
    "TradeKey",
    "compute_no_trade_defer_until_utc",
    "parse_no_trade_rules",
    "resolve_no_trade_action",
]
