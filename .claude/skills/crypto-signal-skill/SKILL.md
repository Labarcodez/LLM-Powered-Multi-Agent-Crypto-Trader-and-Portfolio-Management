---
name: crypto-signal-skill
description: Compute the skill-augmented technical composite signal (SMA7, SLMA golden-cross, MACD histogram, Bollinger mean-reversion) for a cryptocurrency from its 30-day daily price history. Use when acting as the Crypto Agent in the multi-agent trading desk, or whenever asked to read a technical/directional signal on a crypto asset from raw price data.
---

# Crypto Signal Skill

Implements the exact skill-augmented configuration from arXiv:2501.00826v3
(RESEARCH.md §2.2 at the repo root) — the paper's single best-performing
capability configuration across every architecture it tested.

## Quick start

Given a coin's last 30+ daily closing prices (oldest first), run:

```bash
python3 scripts/signal.py --closes "100.1,101.2,99.8,...(30+ values)..."
```

This prints the four component readings and the 0-4 composite bullish count.
No network access, no dependencies beyond numpy — deterministic and fast,
so use the script rather than re-deriving the arithmetic by hand.

## How to read the output

| bullish_count | Reading |
|---|---|
| 4 | Strong buy — all four indicators agree bullish |
| 3 | Moderate buy |
| 2 | Neutral / mixed |
| 1 | Moderate sell |
| 0 | Strong sell — all four indicators agree bearish |

Treat this as **one input among several**, not a mechanical override — combine
it with your own reading of the raw price/volume/market-cap trend and, if
acting as the Crypto Agent, your own confidence calibration. See
`crypto_desk/indicators/skill_signals.py` for the exact formulas (SMA7
vs. 7-day MA, SLMA 7d-vs-30d golden cross, MACD 12/26/9 histogram,
Bollinger 20-day/2-std contrarian oversold signal).

## When acting as the Crypto Agent

Read `crypto_desk/agents/crypto_agent.py`'s `SYSTEM_PROMPT_TEMPLATE` for the
full role description. In short: produce a directional signal in [-1, 1],
a confidence in [0, 1], and a short rationale per asset — using this skill's
composite signal alongside the raw market data, not instead of it.
