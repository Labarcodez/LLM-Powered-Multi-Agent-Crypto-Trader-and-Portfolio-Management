"""Trading Agent — supervisor (Hierarchical) or judge (Debate), the only
agent that sees portfolio state and issues trading actions (RESEARCH.md
§2.1, §7).

This module implements the Hierarchical framing fully (the build-first MVP
target, RESEARCH.md §7): the Crypto Agent and News Agent report once, and
this agent reconciles them. The `architecture` field switches the system
prompt's framing to "judge over a debate transcript" for when the harness
implements the Collaborative/Debate round-trip (RESEARCH.md §6.1's roster
follow-up pattern is the natural place for that orchestration) and passes a
`debate_transcript` instead of single-pass reports — the schema already
supports it so that extension doesn't require touching this file's output
contract.

Position sizing itself (RESEARCH.md §9.2, fractional Kelly + concentration
cap) is NOT done by the LLM here — the Trading Agent expresses conviction
(a signal + confidence per asset) and risk/position_sizing.py turns that
into the actual bounded position size deterministically. Keeping "how
strongly do I believe this" (the model's job) separate from "how big a bet
does that justify" (a pure math function) is the same code-for-reliability
split used throughout this codebase.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field

from crypto_desk.agents.base import REACT_STYLE_INSTRUCTIONS, call_structured
from crypto_desk.agents.crypto_agent import CryptoAgentOutput
from crypto_desk.agents.news_agent import NewsAgentOutput
from crypto_desk.config import Architecture, Capability, DeskConfig
from crypto_desk.memory.rolling_memory import RollingMemory
from crypto_desk.risk.circuit_breakers import CircuitBreaker


class AssetPosition(BaseModel):
    ticker: str
    units: float
    market_value_usd: float
    unrealized_pnl_usd: float
    concentration_pct: float = Field(ge=0.0, le=1.0, description="share of total portfolio value")


class PortfolioState(BaseModel):
    cash_usd: float
    total_value_usd: float
    positions: list[AssetPosition]


class TradingAction(BaseModel):
    ticker: str
    action: float = Field(
        ge=-1.0, le=1.0,
        description="Positive: buy this fraction of the post-sell cash pool. "
        "Negative: sell this fraction of the current holding. 0: no change.",
    )
    conviction: float = Field(ge=0.0, le=1.0)
    rationale: str


class TradingAgentOutput(BaseModel):
    actions: list[TradingAction]
    portfolio_note: str = Field(description="Brief overall assessment of this week's positioning.")


TRADING_AGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "action": {"type": "number", "minimum": -1, "maximum": 1},
                    "conviction": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                },
                "required": ["ticker", "action", "conviction", "rationale"],
                "additionalProperties": False,
            },
        },
        "portfolio_note": {"type": "string"},
    },
    "required": ["actions", "portfolio_note"],
    "additionalProperties": False,
}


HIERARCHICAL_ROLE = """\
You are the Trading Agent, acting as SUPERVISOR over two subordinate \
analysts: a Crypto Agent (market dynamics) and a News Agent (sentiment). \
Each has completed a single-pass analysis and reported to you. You bear \
sole responsibility for reconciling any conflicting signals and issuing \
this week's final trading actions. This mirrors a portfolio manager \
receiving reports from specialist analysts and having ultimate decision \
authority."""

DEBATE_ROLE = """\
You are the Trading Agent, acting as JUDGE over a two-round adversarial \
debate transcript between the Crypto Agent and the News Agent, each of \
whom was instructed to challenge the other's position and cite specific \
evidence. Weigh the strength of each side's arguments, identify points of \
convergence and persistent disagreement, and issue this week's final \
trading actions based on your evaluation of the complete dialectical \
record — not by simply averaging the two positions."""

CONVICTION_INSTRUCTIONS = """\
Express your conviction per asset via `conviction` in [0, 1] — this feeds a \
deterministic fractional-Kelly position sizer downstream (see \
risk/position_sizing.py), so it should genuinely reflect how much the \
evidence supports the trade, not be inflated to "make the trade happen." \
Be explicitly conservative — lower conviction, smaller |action| — when the \
Crypto Agent and News Agent signals conflict, or either reports low \
confidence. Consider each position's unrealized P&L when deciding whether \
to take profit or cut a loss, not just the fresh signal in isolation. \
Sells execute before buys; if your buy actions would sum to more than 1.0 \
of available cash, they will be scaled down proportionally — size them as \
you actually want them weighted relative to each other, not as if each has \
the whole book to itself."""


def _build_system_prompt(architecture: Architecture, capability: Capability) -> str:
    role = DEBATE_ROLE if architecture == Architecture.DEBATE else HIERARCHICAL_ROLE
    return "\n\n".join([role, CONVICTION_INSTRUCTIONS, REACT_STYLE_INSTRUCTIONS])


class TradingAgent:
    def __init__(self, config: DeskConfig, memory_root: str = ".agent-memory"):
        self.config = config
        self.memory = RollingMemory(
            "trading_agent", window_weeks=config.risk.memory_window_weeks, root=memory_root
        )
        self.system_prompt = _build_system_prompt(config.architecture, config.capability)

    def _build_user_message(
        self,
        iso_week: str,
        crypto_report: CryptoAgentOutput,
        news_report: NewsAgentOutput,
        portfolio: PortfolioState,
        debate_transcript: str | None = None,
    ) -> str:
        lines = [f"# Week {iso_week}\n"]

        if debate_transcript is not None:
            lines.append("## Full debate transcript")
            lines.append(debate_transcript)
        else:
            lines.append("## Crypto Agent report")
            lines.append(crypto_report.model_dump_json(indent=2))
            lines.append("\n## News Agent report")
            lines.append(news_report.model_dump_json(indent=2))

        lines.append("\n## Current portfolio state")
        lines.append(portfolio.model_dump_json(indent=2))

        memory_block = self.memory.as_prompt_block(before_iso_week=iso_week)
        if memory_block:
            lines.append("\n" + memory_block)

        return "\n".join(lines)

    def run(
        self,
        iso_week: str,
        crypto_report: CryptoAgentOutput,
        news_report: NewsAgentOutput,
        portfolio: PortfolioState,
        debate_transcript: str | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        as_of: date | None = None,
    ) -> TradingAgentOutput:
        user_message = self._build_user_message(
            iso_week, crypto_report, news_report, portfolio, debate_transcript
        )
        result = call_structured(
            model=self.config.models.trading_agent_model,
            system_prompt=self.system_prompt,
            user_content=user_message,
            json_schema=TRADING_AGENT_OUTPUT_SCHEMA,
            circuit_breaker=circuit_breaker,
            as_of=as_of,
            enable_thinking=(self.config.capability == Capability.CHAIN_OF_THOUGHT),
        )
        output = TradingAgentOutput.model_validate(result.parsed)
        self.memory.record(iso_week, json.loads(output.model_dump_json()))
        return output
