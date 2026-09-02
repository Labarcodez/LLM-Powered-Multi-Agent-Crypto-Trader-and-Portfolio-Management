# LLM-Powered Multi-Agent Crypto Trader and Portfolio Management

A Claude-native multi-agent crypto trading and portfolio-management desk,
built to the design in [`RESEARCH.md`](./RESEARCH.md) — grounded in
[arXiv:2501.00826v3](https://arxiv.org/abs/2501.00826) ("LLM-Powered
Multi-Agent System for Automated Crypto Portfolio Management") and extended
with real-world evidence, statistical-rigor checks, and an aggressive risk
posture set by direct request. **Read `RESEARCH.md` first** — it's the
design document this code implements section by section; this README is
just how to run it.

**Status:** implemented, unit-tested, paper-trading only. No code in this
repo has ever placed a real order or touched real funds — see
[Current status & limitations](#current-status--limitations).

## Architecture, in one paragraph

Three agents. A **Crypto Agent** reads 30 days of price/volume/market-cap
(plus a skill-augmented technical composite — SMA7, golden-cross, MACD,
Bollinger — RESEARCH.md §2.2, the paper's best-performing configuration) and
produces a directional signal per asset. A **News Agent** reads the week's
articles and produces sentiment, discounting single-source/uncorroborated
claims (RESEARCH.md §15.1). A **Trading Agent** fuses both reports against
current portfolio state and a rolling 4-week memory into per-asset trading
actions. All three run on Claude via the Anthropic API with structured
(schema-guaranteed) JSON output. See `crypto_desk/agents/` and
`RESEARCH.md` §2, §7.

```
crypto_desk/
├── config.py           # universe, architecture/capability choice, risk posture
├── indicators/          # the paper's 4 skill-augmented TA rules (pure Python, no network)
├── agents/               # Crypto / News / Trading agents — real Anthropic API calls
├── data/                 # market + news fetchers (CoinGecko, free news API)
├── memory/               # rolling K=4 weekly memory (JSON-file backed)
├── risk/                 # circuit breakers + fractional-Kelly position sizing
├── portfolio/            # paper-trading ledger (the ONLY execution path right now)
├── backtest/             # 52-week harness reproducing the paper's exact setup + metrics
└── cli.py                # `python -m crypto_desk.cli backtest|check`

.claude/skills/           # the same logic as standalone Claude Code Skills
tests/                     # pytest — see "Tests" below
examples/                  # a worked demo tick with real live data (see below)
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

Verify the environment:

```bash
python -m crypto_desk.cli check
```

## Running it

**Tests** (no API key or network needed — pure logic, runs in well under a
second):

```bash
pytest tests/ -v
```

33 tests, all passing as of this commit, including one that reconstructs
the blueprint paper's own reported Sharpe ratio (1.502) from its own
reported inputs to prove this codebase's Sharpe formula matches the paper's
exactly, not just "a standard Sharpe formula" in the abstract
(`tests/test_metrics.py::test_sharpe_matches_paper_reported_value`).

**A quick smoke-test backtest** (needs `ANTHROPIC_API_KEY` + network to
CoinGecko and the news provider — see [Current status](#current-status--limitations)):

```bash
python -m crypto_desk.cli backtest --year 2025 --weeks 4 --universe bitcoin,ethereum,solana
```

**The full 52-week reproduction** (RESEARCH.md §10.1 Phase 1 — this is what
"reproduce the paper's baselines" means concretely):

```bash
python -m crypto_desk.cli backtest --year 2025
```

This will make real, billed Claude API calls (3 agents × 52 weeks, plus any
retries) and take a while on CoinGecko's free-tier rate limit. Start with
the smoke test above.

## Configuration

Everything risk-related lives in `crypto_desk/config.py` and is documented
there with the RESEARCH.md section that justifies each number — read the
docstrings before changing anything, especially `RiskConfig`. Two presets:

- `DEFAULT_CONFIG` — Hierarchical + Skill, the build-and-validate target
  (simplest architecture, the paper's best risk-adjusted result).
- `AGGRESSIVE_LIVE_CONFIG` — Debate + Skill, the aggressive live target once
  Hierarchical has validated the pipeline (RESEARCH.md §7).

Model selection defaults to Opus 5 for all three agents (Anthropic's own
current guidance: don't downgrade for cost without being asked). A
Haiku/Sonnet/Opus cost-tiered option — the `crypto-claude-desk` production
pattern documented in RESEARCH.md §4 — is available via
`ModelConfig.tiered()`, opt-in, not default.

## Current status & limitations

Read this before assuming more works than actually does.

- **Paper trading only.** `crypto_desk/portfolio/ledger.py` is a simulated
  ledger. There is no code anywhere in this repo that places a real order,
  holds a real credential, or touches a real wallet. Getting to real capital
  means clearing RESEARCH.md §9.4 Phase 2 (a non-custodial, spend-capped
  wallet) first — deliberately not built yet.
- **The agent layer needs your `ANTHROPIC_API_KEY` to do anything.** It was
  authored and unit-tested in a sandboxed environment with no API key and a
  restrictive egress proxy (outbound calls to arbitrary hosts, including
  `api.coingecko.com`, were blocked there) — see RESEARCH.md §12. The code
  follows the current documented Anthropic API surface exactly (structured
  outputs via `output_config.format`, prompt caching, typed error handling),
  and every pure-logic component it depends on is tested and passing, but
  the agents' actual Claude API calls have not been exercised end-to-end
  from within that sandbox. `examples/demo_run.md` documents a real,
  live-data worked example run manually (by Claude, in-session, using tools
  that sandbox did have) as a stand-in — read it for what a real tick's
  input/output actually looks like before you spend API budget on the first
  real run.
- **`data/news.py`'s response parsing is defensive but unverified.** Same
  root cause — see the module's own docstring for exactly what to check
  before trusting it.
- **The circuit breakers detect; they don't act.** `risk/circuit_breakers.py`
  deliberately only returns a `BreachEvent` — freezing a wallet, revoking a
  key, or paging a human has to live outside the trading loop's own control
  flow (RESEARCH.md §8.3, Fig. 3) and isn't wired to anything yet.
- **Live 24/7 scheduling IS wired up, execution-path B.** A weekly Claude
  Code Routine reasons directly as the three agents (Bash + this repo's
  real code — no `ANTHROPIC_API_KEY`, ever) and paper-trades the full
  15-asset universe every Monday, persisting state to `.agent-memory/` and
  logging each tick to `examples/live_ticks.md`. See that file for the real
  running history and RESEARCH.md §6.7/§9.5 for the design and its one hard
  limitation found in practice: this workspace doesn't allow granting a
  *fresh*, headless session push credentials or MCP connectors, so the
  Routine is bound to a specific long-running session rather than spawning
  a new one each week — documented there, not glossed over.
- **Intended live-execution venue: Kraken** (RESEARCH.md §9.5) — still
  paper-only. A Kraken MCP connector exists but isn't connected yet;
  getting to a real order needs the user to create the account, complete
  KYC, fund it, and generate a **trade-only** API key (no withdrawal scope)
  — none of which Claude can do. §9.5 also has a live tradability
  cross-check for the universe against Kraken's actual listings.

None of this is hidden or a surprise if you've read `RESEARCH.md` — it's
the roadmap in §11, Phases 1-2 done, the rest ahead of us.

## Tests

```bash
pytest tests/ -v
```

Covers: the four skill-augmented indicators against hand-constructed price
series with known answers; performance metrics (cumulative return, Sharpe —
verified against the paper's own number, max drawdown, deflated Sharpe);
fractional-Kelly position sizing math; circuit-breaker trip/no-trip
thresholds including the "monthly is alert-only, everything else halts"
distinction; and the paper-trading ledger's buy/sell/rebalancing execution
rule (sells first, pro-rata buy scaling).

## Full research

Everything behind every design decision in this codebase — the blueprint
paper's complete results, real-world evidence (Alpha Arena, live trading
products), statistical-rigor caveats, the free-MCP audit, Managed Agents,
the aggressive risk posture rationale, and the phased roadmap — is in
[`RESEARCH.md`](./RESEARCH.md).
