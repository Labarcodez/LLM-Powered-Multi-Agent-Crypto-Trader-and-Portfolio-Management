"""Crypto Agent — market-dynamics analyst (RESEARCH.md §2.1, §2.3).

The ablation study's single most important finding (RESEARCH.md §2.5):
removing this agent costs 42.6 percentage points of cumulative return and
collapses win rate to a coin flip. This is the alpha engine — get this
agent right before anything else in the system.

Reads 30-day market statistics (+ the skill-augmented composite signal by
default) and its own rolling memory; produces one directional signal per
asset with a confidence and a rationale.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field

from crypto_desk.agents.base import REACT_STYLE_INSTRUCTIONS, call_structured
from crypto_desk.config import Capability, DeskConfig
from crypto_desk.indicators.skill_signals import SkillSignal, composite_skill_signal
from crypto_desk.memory.rolling_memory import RollingMemory
from crypto_desk.risk.circuit_breakers import CircuitBreaker


class AssetMarketSignal(BaseModel):
    ticker: str
    signal: float = Field(ge=-1.0, le=1.0, description="-1 = strong bearish, +1 = strong bullish")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class CryptoAgentOutput(BaseModel):
    signals: list[AssetMarketSignal]


CRYPTO_AGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "signal": {"type": "number", "minimum": -1, "maximum": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                },
                "required": ["ticker", "signal", "confidence", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["signals"],
    "additionalProperties": False,
}


SYSTEM_PROMPT_TEMPLATE = """\
You are the Crypto Agent in a multi-agent cryptocurrency portfolio management \
system (see RESEARCH.md at the repo root for the full design). Your sole job \
is analyzing recent market dynamics for each asset in the universe and \
producing a directional signal, a confidence, and a one- or two-sentence \
rationale for each one. You do not decide trades or see the portfolio's \
current holdings — that is the Trading Agent's job, downstream of you.

For each asset you will be given the last 30 days of daily closing price, \
trading volume, and market capitalization.
{skill_block}
{react_instructions}

Output a signal in [-1, 1] per asset: -1 is strong bearish conviction, +1 is \
strong bullish conviction, 0 is neutral/no edge. Confidence in [0, 1] reflects \
how much the evidence actually supports the signal, independent of its \
direction or magnitude — a small, uncertain move should carry low confidence \
even if you lean one way."""

SKILL_BLOCK = """
You are also given a skill-augmented composite technical signal for each \
asset, computed from four classical indicators over the same 30-day window: \
SMA7 (price vs. 7-day moving average), SLMA (7-day vs. 30-day moving average \
golden-cross), MACD histogram (12/26/9 EMA momentum), and Bollinger Bands \
(20-day, 2-std contrarian mean-reversion). Each asset's report shows how many \
of the four are bullish (0-4) — treat 4 as a strong technical tailwind, 0 as \
a strong technical headwind, and use it as one input among several, not a \
mechanical override of your own reading of the raw price/volume/mcap data."""


def _build_system_prompt(capability: Capability) -> str:
    skill_block = SKILL_BLOCK if capability == Capability.SKILL else ""
    return SYSTEM_PROMPT_TEMPLATE.format(
        skill_block=skill_block, react_instructions=REACT_STYLE_INSTRUCTIONS
    )


@dataclass
class AssetMarketData:
    ticker: str
    coin_id: str
    daily_closes: list[float]  # oldest-first, >= 30 observations
    daily_volumes: list[float]
    daily_market_caps: list[float]


class CryptoAgent:
    def __init__(self, config: DeskConfig, memory_root: str = ".agent-memory"):
        self.config = config
        self.memory = RollingMemory(
            "crypto_agent", window_weeks=config.risk.memory_window_weeks, root=memory_root
        )
        self.system_prompt = _build_system_prompt(config.capability)

    def _build_user_message(self, iso_week: str, assets: list[AssetMarketData]) -> str:
        lines = [f"# Week {iso_week} — market data for {len(assets)} assets\n"]
        for a in assets:
            lines.append(f"## {a.ticker}")
            lines.append(f"Last close: {a.daily_closes[-1]:.6g}")
            lines.append(f"30d closes (oldest-first): {[round(c, 6) for c in a.daily_closes[-30:]]}")
            lines.append(f"30d volumes (oldest-first): {[round(v, 2) for v in a.daily_volumes[-30:]]}")
            lines.append(f"30d market caps (oldest-first): {[round(m, 2) for m in a.daily_market_caps[-30:]]}")
            if self.config.capability == Capability.SKILL:
                signal: SkillSignal = composite_skill_signal(a.daily_closes)
                lines.append(f"Skill signal: {signal.as_prompt_fragment(a.ticker)}")
            lines.append("")

        memory_block = self.memory.as_prompt_block(before_iso_week=iso_week)
        if memory_block:
            lines.append(memory_block)

        return "\n".join(lines)

    def run(
        self,
        iso_week: str,
        assets: list[AssetMarketData],
        circuit_breaker: CircuitBreaker | None = None,
        as_of: date | None = None,
    ) -> CryptoAgentOutput:
        user_message = self._build_user_message(iso_week, assets)
        result = call_structured(
            model=self.config.models.crypto_agent_model,
            system_prompt=self.system_prompt,
            user_content=user_message,
            json_schema=CRYPTO_AGENT_OUTPUT_SCHEMA,
            circuit_breaker=circuit_breaker,
            as_of=as_of,
            enable_thinking=(self.config.capability == Capability.CHAIN_OF_THOUGHT),
        )
        output = CryptoAgentOutput.model_validate(result.parsed)
        self.memory.record(iso_week, json.loads(output.model_dump_json()))
        return output
