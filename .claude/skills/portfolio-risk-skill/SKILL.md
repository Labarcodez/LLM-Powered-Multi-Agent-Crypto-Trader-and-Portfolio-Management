---
name: portfolio-risk-skill
description: Enforce position-sizing, concentration, and drawdown-circuit-breaker rules on proposed crypto trading actions before they execute. Use when acting as the Trading Agent's risk check, when sizing a position from a conviction score, or whenever asked to validate a proposed crypto trade against risk limits.
---

# Portfolio Risk Skill

The mechanical, non-negotiable half of the Trading Agent's job (RESEARCH.md
§9) — position sizing and circuit breakers are enforced here as explicit
rules, not left to the model's discretion on a given tick.

## Two separate jobs — do not conflate them

1. **Position sizing** (`crypto_desk/risk/position_sizing.py`) — turns a
   conviction score into a bounded position size via fractional Kelly.
   Aggressive-mode defaults (RESEARCH.md §9.1): up to 100% concentration in
   one high-conviction asset, half-Kelly damping, 3-5x leverage ceiling
   (leverage is **not paper-tested** — the source paper is spot-only).

2. **Circuit breakers** (`crypto_desk/risk/circuit_breakers.py`) — malfunction
   detectors, not loss limiters. Below the monthly threshold, a breach means
   "this looks like a bug, not a bet" and halts new entries. Only the
   monthly threshold (70% drawdown, alert-only) is an actual capital-risk
   tolerance number — read RESEARCH.md §9.1 before changing any of these,
   especially before loosening them further.

## Running the checks

```bash
python3 scripts/check_trade.py --action 0.6 --daily-drawdown -0.05 --weekly-drawdown -0.12
```

Exits non-zero and prints the breach reason if any circuit breaker trips;
otherwise prints the risk-adjusted position size.

## The one line that does not move with risk appetite

Concentrated, leveraged, aggressive trades losing money is the strategy
working as designed. A circuit breaker tripping because of a bug, a stale
price, or a compromised credential is a different failure mode entirely —
see RESEARCH.md §8.3's kill switch, which this Skill's breach detection
feeds but does not itself execute (freezing a wallet or paging a human has
to live outside the trading loop's own control flow, per RESEARCH.md
Fig. 3).
