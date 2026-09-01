"""Weekly news fetcher.

Reference implementation targets cryptocurrency.cv (RESEARCH.md §5.3 /
§13.1 sources) — a free, keyless, JSON REST crypto news aggregator that
explicitly advertises itself as "AI/LLM ready." This module's egress could
not be exercised or its exact response schema verified from the sandbox
this was authored in (outbound calls to arbitrary hosts were blocked there —
RESEARCH.md §12); the parsing below is defensive (tries a few plausible
field-name variants) specifically because of that unverified-schema risk.
**Confirm the real response shape against the live API before depending on
this for a real backtest or live tick**, and adjust `_parse_articles` if it
doesn't match.

`fetch_weekly_news` is intentionally a thin, swappable function rather than
a class hierarchy: to point this at a different provider (CoinGecko's news
tool, kukapay's crypto-news-mcp, LunarCrush/Santiment per RESEARCH.md §13.1)
once running inside Claude Code or Managed Agents with those MCP servers
attached, replace this function's body — the News Agent only depends on the
`NewsArticle` shape, not on how it was fetched.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import requests

CRYPTOCURRENCY_CV_BASE = "https://cryptocurrency.cv/api"


@dataclass
class NewsArticle:
    title: str
    body: str
    source: str
    published_at: str  # ISO date string


def _parse_articles(payload: dict, start: date, end: date) -> list[NewsArticle]:
    items = payload.get("articles") or payload.get("data") or payload.get("news") or []
    out: list[NewsArticle] = []
    for item in items:
        title = item.get("title") or item.get("headline") or ""
        body = item.get("summary") or item.get("body") or item.get("description") or ""
        source = item.get("source") or item.get("publisher") or "unknown"
        published_raw = item.get("published_at") or item.get("date") or item.get("publishedAt")
        if not published_raw:
            continue
        try:
            published_dt = datetime.fromisoformat(str(published_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        published_date = published_dt.astimezone(timezone.utc).date()
        if not (start <= published_date <= end):
            continue
        out.append(NewsArticle(
            title=title, body=body, source=source, published_at=published_date.isoformat(),
        ))
    return out


def fetch_weekly_news(
    start: date,
    end: date,
    category: str | None = None,
    session: requests.Session | None = None,
    max_retries: int = 3,
) -> list[NewsArticle]:
    """Fetch news articles published in [start, end] (inclusive), free,
    no key. `category` narrows to e.g. "bitcoin", "defi", "solana" if the
    provider supports it — passed through as a query param; harmless if
    ignored.
    """
    sess = session or requests.Session()
    url = f"{CRYPTOCURRENCY_CV_BASE}/news"
    params = {"from": start.isoformat(), "to": end.isoformat()}
    if category:
        params["category"] = category

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = sess.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return _parse_articles(resp.json(), start, end)
        except requests.RequestException as e:
            last_error = e
            time.sleep(2 ** attempt)
    raise RuntimeError(
        f"failed to fetch news for {start}..{end} after {max_retries} attempts"
    ) from last_error
