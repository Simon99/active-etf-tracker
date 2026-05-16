"""Base fetcher interface.

Each issuer-specific fetcher implements `fetch(etf_id, date)` returning a list of
holding dicts with the unified schema:
    { 'date', 'etf_id', 'stock_id', 'stock_name', 'shares', 'weight', 'market_value' }

Plus optional `meta` dict on the fetcher result for fund-level data
(NAV, total assets, units outstanding).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


@dataclass
class FetchResult:
    etf_id: str
    date: dt.date
    holdings: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and len(self.holdings) > 0


def to_roc(d: dt.date) -> str:
    """2026-05-16 → 115/05/16"""
    return f'{d.year - 1911}/{d.month:02d}/{d.day:02d}'
