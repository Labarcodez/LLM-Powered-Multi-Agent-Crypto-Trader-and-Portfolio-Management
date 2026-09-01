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

Universe for this log: **BTC, ETH, SOL** (a deliberate subset — see
`crypto_desk/config.py`'s `UNIVERSE_TICKERS` for the full 15-asset
universe; expanding this Routine to the full set is future work, not
done yet). Architecture: Hierarchical. Capability: Skill-augmented.

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
