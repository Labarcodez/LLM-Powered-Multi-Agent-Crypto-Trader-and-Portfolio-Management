# Live paper-trading log

Auto-appended weekly by the **"Weekly crypto paper-trading tick"** Claude
Code Routine — execution path B (RESEARCH.md §6.7, README.md's "Claude
runs it in its own terminal" path): a fresh Claude Code session reasons
directly as the Crypto/News/Trading agents each week using Bash, this
repo's own code, and the CoinGecko MCP connector. **No `ANTHROPIC_API_KEY`
is used anywhere in this loop.** Paper trading only — nothing here places a
real order, holds a real credential, or touches a real wallet (see
README.md's "Current status & limitations").

State lives in `.agent-memory/` (the ledger + each agent's rolling K=4
memory), force-committed alongside each entry below so a stateless fresh
session can resume exactly where the previous tick left off — see
`crypto_desk/portfolio/ledger.py`'s `save`/`load` and
`crypto_desk/memory/rolling_memory.py`.

For a fully narrated walkthrough of one tick — the actual reasoning, the
real indicator numbers, why a "no trade" week is a correct output and not
a failure — see [`demo_run.md`](./demo_run.md). That tick (2026-W36,
BTC/ETH/SOL) was worked by hand in a sandbox with no CoinGecko/git access
for the Routine itself, so it is **not** logged as an entry below; the
Routine's own first real firing is entry 1.

Universe for this log: **the full 15-asset universe** (`crypto_desk/config.py`'s
`UNIVERSE_TICKERS` — BTC, ETH, BNB, XRP, SOL, TRX, ADA, BCH, HYPE, XMR, ZEC,
LTC, SUI, AVAX, HBAR) as of the 2026-W37 tick onward. Tick 1 (2026-W36,
below) ran BTC/ETH/SOL only, while the Routine mechanism itself was still
being validated — see that entry and RESEARCH.md's execution-path section
for why. Architecture: Hierarchical. Capability: Skill-augmented.

**Intended eventual execution venue: Kraken** (paper-only for now — see
README.md's "Current status & limitations"). Two universe assets have
jurisdiction-dependent Kraken listings worth knowing about before Phase 2:
Monero (XMR) is delisted on Kraken in the EEA, Canada, and India; Zcash
(ZEC) is delisted in India and UAE, with more jurisdiction reviews ongoing
for both as of this writing. Neither affects paper trading.

---

## Format (illustrative only — not a real logged tick)

```
## <ISO week> — tick <N>

**Prices:** BTC $<price> · ETH $<price> · SOL $<price>
**Signals:** BTC <crypto signal>/<news sentiment> · ETH ... · SOL ...
**Actions:** BTC <a_i> · ETH <a_i> · SOL <a_i>  (<one-line reason each, if not 0>)
**Portfolio:** $<start> → $<end> (<±%>) · cash <%> · drawdown <%>
**Circuit breakers:** <none tripped | which one, and what happened>
```

Real entries appended by the Routine go below this line, oldest first.

---

## 2026-W36 — tick 1

**Prices:** BTC $77,411.00 · ETH $2,417.92 · SOL $99.97
**Signals:** BTC crypto −0.30 / news +0.30 (multi-source-consistent) · ETH crypto −0.30 / no news (falls back to overall +0.05) · SOL crypto +0.05 / no news (falls back to overall +0.05)
**Actions:** BTC 0.0 · ETH 0.0 · SOL 0.0 — BTC: bearish technicals vs. corroborated bullish news is a genuine wash, not a default no-signal; ETH/SOL: weak, non-corroborated signals, no entry.
**Portfolio:** $100,000.00 → $100,000.00 (0.00%) · cash 100% · drawdown 0.00%
**Circuit breakers:** none tripped (first tick, no prior history to measure drawdown against)

First real firing of the self-bound weekly Routine (RESEARCH.md §6.7) — two
earlier fresh-session attempts this same day failed to obtain push
credentials and produced no ledger entry; see the git history around this
commit for that trail. This tick ran live end-to-end: real CoinGecko data,
real `composite_skill_signal` computation, real agent reasoning against the
schemas in `crypto_desk/agents/`, real `PaperLedger`/`RollingMemory` state.
