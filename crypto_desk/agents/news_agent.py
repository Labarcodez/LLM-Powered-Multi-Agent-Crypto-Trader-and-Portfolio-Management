"""News Agent — sentiment risk-dampener (RESEARCH.md §2.1, §2.5).

The ablation study found removing this agent costs little on raw return
(-0.9pp) but a real amount on risk (+6.8pp volatility, -3.8pp win rate) — its
job is calibrating conviction and catching what pure price action misses,
not generating alpha on its own.

Implements the "uniform trust" mitigation from RESEARCH.md §15.1
(TrustTrade, arXiv:2603.22567): the prompt explicitly instructs the agent
NOT to treat every source as equally credible, and the output schema
requires a `corroboration` field per claim so single-source, unconfirmed
narratives are visibly discounted rather than acted on as readily as
consistent, multi-source signals. This matters most once social-sentiment
sources (RESEARCH.md §13.1) are wired in alongside news articles — crypto
social volume is routinely manufactured by pump groups.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field

from crypto_desk.agents.base import REACT_STYLE_INSTRUCTIONS, call_structured
from crypto_desk.config import Capability, DeskConfig
from crypto_desk.memory.rolling_memory import RollingMemory
from crypto_desk.risk.circuit_breakers import CircuitBreaker


class AssetNewsSignal(BaseModel):
    ticker: str
    signal: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    corroboration: str = Field(
        description='One of "single-source", "multi-source-consistent", or '
        '"multi-source-conflicting" — RESEARCH.md §15.1: do not let an '
        "uncorroborated, single-source claim carry the same weight as a "
        "signal confirmed across independent sources."
    )


class NewsAgentOutput(BaseModel):
    overall_sentiment: float = Field(ge=-1.0, le=1.0)
    overall_rationale: str
    asset_signals: list[AssetNewsSignal] = Field(
        description="Only for assets explicitly mentioned in this week's articles."
    )


NEWS_AGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_sentiment": {"type": "number", "minimum": -1, "maximum": 1},
        "overall_rationale": {"type": "string"},
        "asset_signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "signal": {"type": "number", "minimum": -1, "maximum": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                    "corroboration": {
                        "type": "string",
                        "enum": ["single-source", "multi-source-consistent", "multi-source-conflicting"],
                    },
                },
                "required": ["ticker", "signal", "confidence", "rationale", "corroboration"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overall_sentiment", "overall_rationale", "asset_signals"],
    "additionalProperties": False,
}


SYSTEM_PROMPT_TEMPLATE = """\
You are the News Agent in a multi-agent cryptocurrency portfolio management \
system (see RESEARCH.md at the repo root). Your job is reading this week's \
crypto news/social-sentiment articles and producing an overall market \
sentiment signal plus a per-asset signal for any asset explicitly mentioned. \
You do not see market price/volume data or the portfolio — that is other \
agents' job.

Do not treat every source as equally credible. Real crypto news and social \
feeds mix legitimate reporting with promotional content, rumor, and — \
especially on social platforms — coordinated pump activity. Weigh a claim \
repeated consistently across independent sources far more heavily than a \
single unconfirmed post, and say so explicitly via the `corroboration` \
field on every asset signal. A single loud source is not the same thing as \
market consensus.

{react_instructions}

For assets not explicitly mentioned this week, do not fabricate a signal — \
simply omit them; the Trading Agent falls back to your overall sentiment \
for those."""


def _build_system_prompt(capability: Capability) -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(react_instructions=REACT_STYLE_INSTRUCTIONS)


@dataclass
class NewsArticle:
    title: str
    body: str
    source: str
    published_at: str  # ISO date string


class NewsAgent:
    def __init__(self, config: DeskConfig, memory_root: str = ".agent-memory"):
        self.config = config
        self.memory = RollingMemory(
            "news_agent", window_weeks=config.risk.memory_window_weeks, root=memory_root
        )
        self.system_prompt = _build_system_prompt(config.capability)

    def _build_user_message(self, iso_week: str, articles: list[NewsArticle]) -> str:
        lines = [f"# Week {iso_week} — {len(articles)} articles\n"]
        if not articles:
            lines.append("(No articles this week. Report overall_sentiment as neutral (0.0) "
                          "with an empty asset_signals list, and say so in the rationale.)")
        for i, a in enumerate(articles, 1):
            lines.append(f"## Article {i}: {a.title}")
            lines.append(f"Source: {a.source} | Published: {a.published_at}")
            lines.append(a.body)
            lines.append("")

        memory_block = self.memory.as_prompt_block(before_iso_week=iso_week)
        if memory_block:
            lines.append(memory_block)

        return "\n".join(lines)

    def run(
        self,
        iso_week: str,
        articles: list[NewsArticle],
        circuit_breaker: CircuitBreaker | None = None,
        as_of: date | None = None,
    ) -> NewsAgentOutput:
        user_message = self._build_user_message(iso_week, articles)
        result = call_structured(
            model=self.config.models.news_agent_model,
            system_prompt=self.system_prompt,
            user_content=user_message,
            json_schema=NEWS_AGENT_OUTPUT_SCHEMA,
            circuit_breaker=circuit_breaker,
            as_of=as_of,
            enable_thinking=(self.config.capability == Capability.CHAIN_OF_THOUGHT),
        )
        output = NewsAgentOutput.model_validate(result.parsed)
        self.memory.record(iso_week, json.loads(output.model_dump_json()))
        return output
