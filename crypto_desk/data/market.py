"""Market data fetcher — CoinGecko's free public API (RESEARCH.md §5.3: no
API key required for this endpoint at this project's request volume).

This module makes plain HTTP calls via `requests`, deliberately NOT going
through an MCP tool-call, because a 52-week backtest needs a precise,
deterministic, leakage-free historical slice for each week (RESEARCH.md
§2.3) — that's a data-retrieval problem the harness should control exactly,
not something to leave to a model's own tool-calling judgment. For LIVE
operation, RESEARCH.md §5.2 documents granting the agents direct MCP access
to CoinGecko/SQD/Twelve Data for real-time data beyond a fixed backtest
window — a reasonable live-mode enhancement, out of scope for this module.

Not exercised end-to-end in the sandbox this was authored in: its egress
proxy blocks direct calls to api.coingecko.com (confirmed via a direct probe
during development — see RESEARCH.md §12). This will work from a normal
network. Verify the exact response shape against
https://docs.coingecko.com/reference/coins-id-market-chart-range before
relying on it for a real backtest.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


@dataclass
class DailyMarketHistory:
    coin_id: str
    dates: list[date]
    closes: list[float]
    volumes: list[float]
    market_caps: list[float]

    def window(self, end: date, lookback_days: int = 30) -> "DailyMarketHistory":
        """The last `lookback_days` observations strictly on/before `end` —
        the exact leakage-free slice the paper's design requires (no
        observation from after the decision date)."""
        idx = [i for i, d in enumerate(self.dates) if d <= end]
        idx = idx[-lookback_days:]
        return DailyMarketHistory(
            coin_id=self.coin_id,
            dates=[self.dates[i] for i in idx],
            closes=[self.closes[i] for i in idx],
            volumes=[self.volumes[i] for i in idx],
            market_caps=[self.market_caps[i] for i in idx],
        )


def _to_unix(d: date) -> int:
    return int(datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc).timestamp())


def _resample_to_daily(series: list[list[float]]) -> dict[date, float]:
    """CoinGecko's /market_chart/range returns finer-than-daily granularity
    for ranges under ~90 days (hourly or 5-min depending on span). Collapse
    to one observation per UTC day by keeping the LAST timestamped value
    seen for that day — the standard "daily close" convention."""
    by_day: dict[date, tuple[int, float]] = {}
    for ts_ms, value in series:
        d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
        if d not in by_day or ts_ms > by_day[d][0]:
            by_day[d] = (ts_ms, value)
    return {d: v for d, (_, v) in by_day.items()}


def fetch_market_history(
    coin_id: str,
    start: date,
    end: date,
    vs_currency: str = "usd",
    session: requests.Session | None = None,
    max_retries: int = 3,
) -> DailyMarketHistory:
    """Fetch daily close price, volume, and market cap for `coin_id` from
    `start` to `end` (inclusive), free public API, no key.

    Retries on 429 (rate limit) with a fixed backoff, matching the free
    tier's documented ~10-30 calls/minute ceiling — fetching 15 assets for a
    52-week backtest will legitimately take a few minutes on the free tier;
    this is expected, not a bug.
    """
    sess = session or requests.Session()
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart/range"
    params = {"vs_currency": vs_currency, "from": _to_unix(start), "to": _to_unix(end)}

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = sess.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                time.sleep(2 ** attempt * 5)
                continue
            resp.raise_for_status()
            payload = resp.json()
            break
        except requests.RequestException as e:
            last_error = e
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(
            f"failed to fetch market history for {coin_id} after {max_retries} attempts"
        ) from last_error

    closes_by_day = _resample_to_daily(payload["prices"])
    volumes_by_day = _resample_to_daily(payload["total_volumes"])
    mcaps_by_day = _resample_to_daily(payload["market_caps"])

    days = sorted(set(closes_by_day) & set(volumes_by_day) & set(mcaps_by_day))
    return DailyMarketHistory(
        coin_id=coin_id,
        dates=days,
        closes=[closes_by_day[d] for d in days],
        volumes=[volumes_by_day[d] for d in days],
        market_caps=[mcaps_by_day[d] for d in days],
    )


def iso_week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Monday..Sunday date range for an ISO (year, week) pair — the paper's
    tick granularity (RESEARCH.md §2.3)."""
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday
