"""Central configuration for the crypto desk.

Every number in this file that reflects a *risk-appetite* decision (position
caps, leverage, drawdown thresholds) is set to the AGGRESSIVE posture
documented in RESEARCH.md section 9 — concentrated conviction bets, leverage
on the table, wide drawdown tolerance. The circuit-breaker thresholds are
malfunction detectors, not loss limiters: see RiskConfig docstring.

Nothing here talks to a real exchange or a real wallet. Until EXECUTION_MODE
is changed from "paper" (and real credentials are wired in per
RESEARCH.md section 6.4 / 9.4), every trade this system "places" is a ledger
entry, not a real order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Universe — the paper's top-15 L1-blockchain-native cryptocurrencies by
# market cap as of January 2025 (RESEARCH.md §2.3). Fixed for a backtest to
# ensure liquidity; for live use this can be refreshed via
# data.market.top_l1_universe(), but re-fixing it mid-run is the paper's own
# convention and worth keeping.
# ---------------------------------------------------------------------------
UNIVERSE: list[str] = [
    "bitcoin", "ethereum", "binancecoin", "ripple", "solana",
    "tron", "cardano", "bitcoin-cash", "hyperliquid", "monero",
    "zcash", "litecoin", "sui", "avalanche-2", "hedera-hashgraph",
]
UNIVERSE_TICKERS: dict[str, str] = {
    "bitcoin": "BTC", "ethereum": "ETH", "binancecoin": "BNB", "ripple": "XRP",
    "solana": "SOL", "tron": "TRX", "cardano": "ADA", "bitcoin-cash": "BCH",
    "hyperliquid": "HYPE", "monero": "XMR", "zcash": "ZEC", "litecoin": "LTC",
    "sui": "SUI", "avalanche-2": "AVAX", "hedera-hashgraph": "HBAR",
}
# Kraken tradability note (RESEARCH.md §9.5, intended Phase 2 execution
# venue): 13 of these 15 are mainstream Kraken listings. XMR is delisted on
# Kraken in the EEA/Canada/India; ZEC is delisted in India/UAE, with more
# jurisdiction reviews ongoing for both. Irrelevant to paper trading — a
# live-execution adapter must check the connected account's actual
# tradability per asset, not assume universe membership implies it.


class Architecture(str, Enum):
    """How the Crypto Agent and News Agent communicate before the Trading
    Agent decides. See RESEARCH.md §2.3 for the full comparison.
    """
    HIERARCHICAL = "hierarchical"  # single pass, no cross-talk — validate the pipeline on this first
    COLLABORATIVE = "collaborative"  # R=1 mutual refinement round
    DEBATE = "debate"  # R=2 adversarial rounds — the aggressive live target (RESEARCH.md §7)


class Capability(str, Enum):
    """How much reasoning scaffolding each agent gets. See RESEARCH.md §2.2.
    SKILL is the paper's best-performing configuration in every architecture.
    """
    ZERO_SHOT = "zero_shot"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    RAG = "rag"
    SKILL = "skill"


class ExecutionMode(str, Enum):
    PAPER = "paper"  # simulated ledger — the only mode until RESEARCH.md §9.4 Phase 2 is cleared
    LIVE = "live"  # real orders via a real MCP/exchange connector — not wired up in this codebase yet


@dataclass(frozen=True)
class ModelConfig:
    """Per-agent model selection.

    Defaults to Opus for every agent, per Anthropic's own current guidance
    (don't downgrade for cost without an explicit instruction to do so).
    RESEARCH.md §3–§8 documents a Haiku-scouts/Sonnet-analyzes/Opus-decides
    tiering (crypto-claude-desk's production pattern, 40-60% cheaper) as an
    explicit, available *option* — set the tier fields below to opt into it.
    """
    crypto_agent_model: str = "claude-opus-5"
    news_agent_model: str = "claude-opus-5"
    trading_agent_model: str = "claude-opus-5"

    @classmethod
    def tiered(cls) -> "ModelConfig":
        """The crypto-claude-desk-style cost-optimized tiering: Haiku scouts,
        Sonnet analyzes, Opus decides. Opt in explicitly via
        `ModelConfig.tiered()` — not the default (see class docstring)."""
        return cls(
            crypto_agent_model="claude-sonnet-5",
            news_agent_model="claude-haiku-4-5",
            trading_agent_model="claude-opus-5",
        )


@dataclass(frozen=True)
class RiskConfig:
    """Circuit breakers, tuned aggressive, per direction (RESEARCH.md §9.1).

    IMPORTANT — read this before changing these numbers: below the monthly
    threshold, none of these caps are loss limiters. They are malfunction
    detectors. Losing money because a concentrated, leveraged bet went wrong
    is the trade this configuration is built for. Losing money because a bug
    sized an order wrong, a stale price triggered a phantom signal, or a key
    got exfiltrated is not a risk-tolerance question — it's exactly the
    failure mode these caps (and the kill switch in RESEARCH.md §8.3) exist
    to catch, regardless of how aggressive the strategy underneath them is.
    Only `monthly_drawdown_alert_only` is a genuine capital-risk tolerance
    number; everything else should trip on a functioning aggressive strategy
    only in extreme, not everyday, conditions.
    """
    # Position sizing (§9.1, §9.2)
    max_single_asset_concentration: float = 1.00  # up to 100% in one high-conviction asset
    kelly_fraction: float = 0.5  # fractional Kelly — half-Kelly damping against mis-estimated edge
    max_leverage: float = 5.0  # 3-5x on high-conviction signals; NOT paper-tested (source paper is spot-only)

    # Circuit breakers — malfunction detectors, not loss limiters (see docstring above)
    daily_drawdown_bug_detector: float = 0.20   # 20%: a same-day move this large is more likely a bug than a bet
    weekly_drawdown_bug_detector: float = 0.40  # 40%: same logic, matches the paper's own weekly tick
    monthly_drawdown_alert_only: float = 0.70   # 70%: the one number that's a real capital-risk tolerance

    # Cost circuit breaker (RESEARCH.md §8.3) — independent of capital risk
    max_consecutive_paid_calls_before_lockout: int = 5

    # Rolling memory window (RESEARCH.md §2.3)
    memory_window_weeks: int = 4


@dataclass(frozen=True)
class BacktestConfig:
    """Reproduces the paper's harness exactly (RESEARCH.md §2.3, §10.1)."""
    starting_cash_usd: float = 100_000.0
    transaction_cost_per_side: float = 0.001  # 0.1%
    weeks: int = 52
    risk_free_rate_annual: float = 0.0  # paper uses the 1-month T-bill; default to 0 unless supplied


@dataclass
class DeskConfig:
    architecture: Architecture = Architecture.HIERARCHICAL  # build/validate on this first (RESEARCH.md §7)
    capability: Capability = Capability.SKILL  # the paper's outright winner in every architecture
    models: ModelConfig = field(default_factory=ModelConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    execution_mode: ExecutionMode = ExecutionMode.PAPER
    universe: list[str] = field(default_factory=lambda: list(UNIVERSE))


DEFAULT_CONFIG = DeskConfig()

# The aggressive live target once Hierarchical+Skill has validated the
# pipeline (RESEARCH.md §7): highest bull-market return of any strategy the
# blueprint paper tested, at the cost of its deepest bear-market drawdown.
AGGRESSIVE_LIVE_CONFIG = DeskConfig(
    architecture=Architecture.DEBATE,
    capability=Capability.SKILL,
)
