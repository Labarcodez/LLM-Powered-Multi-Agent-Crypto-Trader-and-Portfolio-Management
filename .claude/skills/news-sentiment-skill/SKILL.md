---
name: news-sentiment-skill
description: Read a week's crypto news/social-sentiment articles and produce an overall market sentiment score plus per-asset signals for explicitly-mentioned coins, with source-corroboration discounting for unconfirmed single-source claims. Use when acting as the News Agent in the multi-agent trading desk, or whenever asked to gauge crypto market sentiment from a batch of articles.
---

# News Sentiment Skill

Implements the News Agent role from arXiv:2501.00826v3 (RESEARCH.md §2.1),
extended with the "uniform trust" mitigation from RESEARCH.md §15.1
(TrustTrade, arXiv:2603.22567).

## The one rule that matters most

**Do not treat every source as equally credible.** Crypto news and social
feeds mix legitimate reporting with promotional content, rumor, and —
especially on social platforms — coordinated pump-and-dump activity. A
single loud post is not market consensus.

For every asset-level signal, tag it with `corroboration`:

- `single-source` — one outlet/post, unconfirmed elsewhere. Discount it.
- `multi-source-consistent` — the same read appears across independent
  sources. Weight it normally.
- `multi-source-conflicting` — sources disagree. Lower confidence, note the
  disagreement explicitly rather than picking a side arbitrarily.

## Output shape

```json
{
  "overall_sentiment": -1.0..1.0,
  "overall_rationale": "...",
  "asset_signals": [
    {"ticker": "BTC", "signal": -1.0..1.0, "confidence": 0.0..1.0,
     "rationale": "...", "corroboration": "single-source|multi-source-consistent|multi-source-conflicting"}
  ]
}
```

Only include `asset_signals` entries for coins explicitly discussed that
week — do not fabricate a signal for an asset the articles never mention;
downstream, the Trading Agent falls back to `overall_sentiment` for those.

See `crypto_desk/agents/news_agent.py` for the full schema and system
prompt this Skill mirrors, and RESEARCH.md §13.1 for recommended
additional sources (LunarCrush, Santiment) beyond a single news feed —
apply the same corroboration discipline especially hard to social-volume
data, which is the easiest of all these sources to manufacture.
