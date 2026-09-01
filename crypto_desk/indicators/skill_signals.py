"""The paper's "skill-augmented" indicator set (RESEARCH.md §2.2 / §5.1).

Four classical, rule-based technical indicators, each producing a binary
bullish/bearish reading from a 30-day price history. Collapsed into a 0-4
composite "bullish count" that the Crypto Agent's prompt maps to signal
strength: 4 = strong buy, 0 = strong sell, intermediate = proportionally
moderate. This is the single configuration the blueprint paper found
outperforms in every one of the three communication architectures — it is
implemented here as deterministic, zero-token, zero-latency Python rather
than something an LLM re-derives every tick (the same "code for reliability,
reasoning for judgment" split the Agent Skills architecture is built around).

No network calls in this module — pass it a plain list/array of daily closes
(oldest first) and it returns the four readings plus the composite count.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SkillSignal:
    """One asset's skill-augmented reading for one tick."""
    sma7_bullish: bool
    slma_bullish: bool
    macd_bullish: bool
    bb_bullish: bool
    bullish_count: int  # 0-4
    strength: float  # bullish_count / 4, in [0, 1] — 1.0 = strong buy, 0.0 = strong sell
    macd_histogram: float
    sma7: float
    sma30: float
    bb_lower: float

    def as_prompt_fragment(self, ticker: str) -> str:
        """Render as the compact table row the paper's Crypto Agent prompt
        injects alongside raw market data (RESEARCH.md §2.2)."""
        return (
            f"{ticker}: SMA7={'bull' if self.sma7_bullish else 'bear'} "
            f"SLMA={'bull' if self.slma_bullish else 'bear'} "
            f"MACD={'bull' if self.macd_bullish else 'bear'} "
            f"BB={'bull' if self.bb_bullish else 'bear'} "
            f"-> bullish_count={self.bullish_count}/4 (strength={self.strength:.2f})"
        )


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    """Exponential moving average, matching pandas' `.ewm(span=span).mean()`
    convention (alpha = 2/(span+1)), computed with plain numpy so this module
    has no pandas dependency."""
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def composite_skill_signal(closes: list[float] | np.ndarray) -> SkillSignal:
    """Compute the paper's exact four indicators from a 30-day (or longer)
    daily close-price history, oldest-first.

    Raises ValueError if fewer than 30 observations are supplied — the
    Bollinger Band and SLMA readings need a full 30-day lookback.
    """
    closes = np.asarray(closes, dtype=float)
    if closes.ndim != 1:
        raise ValueError("closes must be a 1-D sequence of daily close prices")
    if len(closes) < 30:
        raise ValueError(
            f"need at least 30 daily closes for the skill-augmented signal, got {len(closes)}"
        )

    price_t = float(closes[-1])

    # SMA7: bullish when price > 7-day simple moving average.
    sma7 = float(np.mean(closes[-7:]))
    sma7_bullish = bool(price_t > sma7)

    # SLMA: bullish when the short MA (7d) has crossed above the long MA (30d) — golden cross.
    sma30 = float(np.mean(closes[-30:]))
    slma_bullish = bool(sma7 > sma30)

    # MACD: bullish when the histogram (MACD line minus its own 9-period
    # signal line) is positive, i.e. upward momentum.
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    histogram = float(macd_line[-1] - signal_line[-1])
    macd_bullish = bool(histogram > 0)

    # Bollinger Bands: CONTRARIAN bullish signal when price closes below the
    # lower band (20-day mean minus 2 standard deviations) — an oversold /
    # potential mean-reversion condition, not a momentum one.
    window20 = closes[-20:]
    mean20 = float(np.mean(window20))
    std20 = float(np.std(window20, ddof=0))
    bb_lower = mean20 - 2.0 * std20
    bb_bullish = bool(price_t < bb_lower)

    bullish_count = int(sum([sma7_bullish, slma_bullish, macd_bullish, bb_bullish]))

    return SkillSignal(
        sma7_bullish=sma7_bullish,
        slma_bullish=slma_bullish,
        macd_bullish=macd_bullish,
        bb_bullish=bb_bullish,
        bullish_count=bullish_count,
        strength=bullish_count / 4.0,
        macd_histogram=histogram,
        sma7=sma7,
        sma30=sma30,
        bb_lower=bb_lower,
    )
