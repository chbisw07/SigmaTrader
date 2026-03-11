from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Tuple


def _norm_query(q: str) -> str:
    s = (q or "").strip().lower()
    # Collapse whitespace and remove trailing punctuation that commonly causes duplicates.
    s = " ".join(s.split())
    while s and s[-1] in {".", "?", "!", ","}:
        s = s[:-1].strip()
    return s


def _cache_key(*, account_id: str, thread_id: str, query: str, symbol: str | None) -> Tuple[str, str, str, str]:
    return (str(account_id or "default"), str(thread_id or "default"), _norm_query(query), str((symbol or "").strip().upper()))


@dataclass
class _Entry:
    ts: float
    value: Any


class TavilyResultCache:
    """Best-effort in-memory cache to avoid duplicate Tavily credits."""

    def __init__(self) -> None:
        self._data: Dict[Tuple[str, str, str, str], _Entry] = {}

    def get(self, *, account_id: str, thread_id: str, query: str, symbol: str | None, ttl_seconds: int) -> Any | None:
        ttl = int(ttl_seconds or 0)
        if ttl <= 0:
            return None
        k = _cache_key(account_id=account_id, thread_id=thread_id, query=query, symbol=symbol)
        e = self._data.get(k)
        if e is None:
            return None
        if (time.time() - float(e.ts)) > float(ttl):
            self._data.pop(k, None)
            return None
        return e.value

    def set(self, *, account_id: str, thread_id: str, query: str, symbol: str | None, value: Any) -> None:
        k = _cache_key(account_id=account_id, thread_id=thread_id, query=query, symbol=symbol)
        self._data[k] = _Entry(ts=time.time(), value=value)


tavily_cache = TavilyResultCache()

