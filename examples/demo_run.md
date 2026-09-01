# A real tick, worked by hand

This is one real, live tick of the pipeline — real market data, real news,
real computed indicators, and a real trading decision — run manually in the
Claude Code session that authored this repository, standing in for the
Anthropic API calls `crypto_desk/agents/*.py` would make automatically once
run with a real `ANTHROPIC_API_KEY` (that sandbox had no key and a
network egress proxy that blocked most outbound hosts — see `RESEARCH.md`
§12 and `README.md`'s "Current status" section). Everything below is real:
the prices, the news headlines, the indicator arithmetic, and the
reasoning — nothing here is invented to make a better story. Where the
honest output was "don't trade," that's what's reported.

**Tick:** ISO week 2026-W36 (week of Sept 1, 2026) · **Universe (subset for
this demo):** BTC, ETH, SOL · **Portfolio:** fresh $100,000, no positions ·
**Architecture:** Hierarchical · **Capability:** Skill-augmented

Data fetched live via this session's CoinGecko MCP connector
(`get-coin-market-chart`, `get-coin-markets`, `get-crypto-news`) —
the same underlying data source `crypto_desk/data/market.py` and
`news.py` are built to reach independently in a deployed environment.

---

## 1. Real market data → real skill-augmented signals

30-day daily closes were pulled live for each asset, then run through the
actual, unmodified `crypto_desk.indicators.skill_signals.composite_skill_signal`
function (verbatim output, not paraphrased):

| Ticker | Last close | 30d range | SMA7 | SMA30 | MACD hist. | Bollinger lower | Bullish count |
|---|---:|---|---:|---:|---:|---:|---:|
| BTC | $77,118.45 | $62,676 → $80,638 | $78,178.68 | $78,544.13 | −250.72 | $76,859.11 | **0/4** |
| ETH | $2,410.11 | $1,844 → $2,534 | $2,451.17 | $2,465.40 | −9.54 | $2,402.15 | **0/4** |
| SOL | $99.64 | $72.61 → $109.02 | $102.40 | $102.76 | −0.95 | $100.51 | **1/4** (Bollinger only) |

All three assets rallied hard over the first ~2/3 of the window (SOL +47.5%
peak-to-start, BTC +27.2%, ETH +34.8%) and have pulled back over the last
1-2 weeks of the window — current prices sit below both moving averages
with negative MACD momentum across the board. SOL's price sits just under
its lower Bollinger band, the one indicator reading in this batch that
leans bullish (contrarian oversold).

## 2. Crypto Agent (real reasoning, real data, this tick)

Acting as `crypto_desk/agents/crypto_agent.py`'s Crypto Agent — same system
prompt, same schema (`CryptoAgentOutput`), reasoning through the table
above and each asset's full 30-day path (not just the summary row):

```json
{
  "signals": [
    {
      "ticker": "BTC",
      "signal": -0.4,
      "confidence": 0.55,
      "rationale": "All four technical indicators read bearish, but this follows a strong ~27% multi-week rally to a fresh window high near $80.6k — the shape reads as a pullback inside an uptrend, not a broken trend. Bearish enough to avoid a fresh long, not bearish enough for high-conviction downside conviction."
    },
    {
      "ticker": "ETH",
      "signal": -0.35,
      "confidence": 0.5,
      "rationale": "Same pullback-after-rally shape as BTC (peak +34.8% off the window's start), currently below both moving averages with negative MACD momentum. Slightly less confident than BTC — ETH's pullback from peak is proportionally smaller so far."
    },
    {
      "ticker": "SOL",
      "signal": -0.3,
      "confidence": 0.45,
      "rationale": "Sharpest rally of the three (+47.5% peak) and sharpest pullback since. Three of four indicators bearish, but price is now trading just under the lower Bollinger band — a contrarian oversold reading that tempers conviction on the bearish case rather than reversing it."
    }
  ]
}
```

## 3. News Agent (real headlines, this tick)

12 live global headlines were pulled (`get-crypto-news`, unfiltered). The
honest finding: **none of them mention BTC, ETH, or SOL specifically.**
Today's crypto news cycle was dominated by XRP (Ripple re-locking 700M XRP
into escrow; Binance XRP reserves down 500M as price sits 63% off its 2025
peak — two different outlets, two different specific claims, not
corroborating each other), stablecoin regulation (Singapore proposing a
100% reserve standard, Ethena launching a USDe payment app), a tokenized-
equity SEC story, a Polygon transaction-count milestone, and a macro note
on global money supply hitting a record $150T. Per the News Agent's own
rule (`crypto_desk/agents/news_agent.py`: "do not fabricate a signal" for
an asset the week's articles don't actually discuss), this is the correct,
real output:

```json
{
  "overall_sentiment": -0.15,
  "overall_rationale": "No coverage of BTC, ETH, or SOL specifically this cycle. The broader tone leans mildly cautious: two independent, non-corroborating stories on XRP weakness, and two separate regulatory-tightening stories (Singapore stablecoin reserves, SEC on tokenized-stock ownership gaps). Partially offset by a genuinely bullish macro liquidity data point (global money supply at a record $150T, +$10.7T YoY) that argues for more capital eventually seeking risk assets, though that's a slow-moving signal, not a this-week catalyst.",
  "asset_signals": []
}
```

`asset_signals` is genuinely empty — not a placeholder, the actual honest
output when the day's real news doesn't cover the tracked universe. The
Trading Agent falls back to `overall_sentiment` (-0.15) for all three
assets, per the schema's own documented convention.

## 4. Trading Agent (real fusion, this tick)

Acting as the Hierarchical-mode supervisor, with a fresh $100,000
all-cash portfolio (no existing positions, so no unrealized-P&L
consideration applies this tick) and both reports above:

```json
{
  "actions": [
    {"ticker": "BTC", "action": 0.0, "conviction": 0.55,
     "rationale": "Crypto Agent bearish (-0.4, moderate confidence) with no countervailing news signal (overall sentiment only mildly cautious, no BTC-specific coverage this week). Nothing here justifies a fresh long entry with real capital. No existing position to trim. Sitting out."},
    {"ticker": "ETH", "action": 0.0, "conviction": 0.5,
     "rationale": "Same shape as BTC, slightly lower conviction on the bearish read. No entry."},
    {"ticker": "SOL", "action": 0.0, "conviction": 0.45,
     "rationale": "The Bollinger contrarian signal is the one bullish note across both reports, but it's a single technical reading against three bearish indicators and no supporting news — not enough to buy into a pullback yet. Worth re-checking next tick if the oversold condition persists or news coverage picks up."}
  ],
  "portfolio_note": "No new positions this week; book stays 100% cash ($100,000). All three tracked assets are mid-pullback after a strong multi-week rally, with technicals leaning bearish and no corroborating news catalyst in either direction. This is a 'wait for confirmation' week, not a 'the strategy has nothing to say' week — re-evaluate next tick with fresh data."
}
```

## 5. Real ledger execution

The exact JSON above, fed through the real, unmodified
`crypto_desk.portfolio.ledger.PaperLedger.apply_actions`:

```
portfolio_value_start: 100000.0
portfolio_value_end:   100000.0
weekly_return:         0.0
cash_end:              100000.0
positions_end:         {}
transaction_costs_paid: 0.0
drawdown_from_peak:    0.0
```

Correctly a no-op: three zero actions, ledger state unchanged, zero
transaction cost paid. This closes the loop end to end — real data, real
per-agent reasoning against the actual schemas and prompts this codebase
ships, a real (if quiet) trading decision, and real, correct ledger
bookkeeping.

**What this demo does *not* prove:** that the automated Claude API calls
in `crypto_desk/agents/*.py` behave identically to this manual walk-through
— they should, since the system prompts and schemas are copied verbatim
from those files, but "should" isn't "verified end-to-end," which needs a
real `ANTHROPIC_API_KEY` and a network that can reach `api.anthropic.com`.
It also doesn't prove anything about the buy/sell/rebalance arithmetic
under a non-trivial trade — that's what `tests/test_ledger.py` is for
(passing, deterministic, exercises exactly that path with synthetic data).
What it does prove: given real current market conditions, the pipeline's
reasoning is sound, appropriately calibrated (not overconfident on
moderate, conflicting evidence), honest about what the day's real news
actually covers, and produces a decision a careful human portfolio manager
would recognize as reasonable — which, per `RESEARCH.md` §2, is the entire
point of the architecture this repo implements.
