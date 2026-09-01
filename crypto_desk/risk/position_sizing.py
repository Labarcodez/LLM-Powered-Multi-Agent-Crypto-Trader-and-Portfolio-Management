"""Fractional-Kelly position sizing (RESEARCH.md §9.2), driven by the Crypto
Agent's skill-augmented composite signal (RESEARCH.md §5.1) instead of a flat
size — systematizing "aggressive" rather than leaving it to prompt language.

Kelly's classic assumptions (known edge, effectively infinite repeated bets)
don't literally hold for crypto. Two deliberate dampers, per RESEARCH.md
§9.2: a `kelly_fraction` (default 0.5, i.e. half-Kelly) to control the
downside of a mis-estimated edge, and a hard concentration cap applied after
Kelly sizing so a single overconfident signal can never exceed the
configured maximum regardless of what the raw Kelly formula says.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetSignal:
    ticker: str
    signal_strength: float  # -1..+1, e.g. from the skill-augmented composite (2*strength-1) or agent confidence
    win_probability: float  # p: probability the bet is a winner, in (0, 1)
    win_loss_ratio: float   # b: avg win size / avg loss size, > 0


def kelly_criterion(win_probability: float, win_loss_ratio: float) -> float:
    """Raw (full) Kelly fraction: f* = p - (1-p)/b.

    Can be negative (meaning: don't take this bet / bet against it) or, for
    a strong enough edge, greater than 1 (meaning: leverage). Callers should
    apply `kelly_fraction` damping and a concentration cap — this function
    intentionally does neither, so it stays a pure, testable implementation
    of the textbook formula.
    """
    if not 0.0 < win_probability < 1.0:
        raise ValueError("win_probability must be in (0, 1)")
    if win_loss_ratio <= 0:
        raise ValueError("win_loss_ratio must be positive")
    return win_probability - (1.0 - win_probability) / win_loss_ratio


def fractional_kelly_size(
    signal: AssetSignal,
    kelly_fraction: float = 0.5,
    max_single_asset_concentration: float = 1.0,
    max_leverage: float = 1.0,
) -> float:
    """Position size as a fraction of book, in [-max_leverage, +max_leverage],
    sign matching the signal's direction. Long-only callers should clip the
    result at 0 before use (this project's paper ledger, per the blueprint
    paper, is long-only — see portfolio/ledger.py).
    """
    if not -1.0 <= signal.signal_strength <= 1.0:
        raise ValueError("signal_strength must be in [-1, 1]")

    raw_kelly = kelly_criterion(signal.win_probability, signal.win_loss_ratio)
    damped = raw_kelly * kelly_fraction

    # Scale by conviction direction/magnitude and cap at the concentration
    # limit and the leverage ceiling, whichever binds first.
    sized = damped * abs(signal.signal_strength)
    direction = 1.0 if signal.signal_strength >= 0 else -1.0
    sized = direction * min(abs(sized), max_single_asset_concentration, max_leverage)
    return sized


def size_portfolio(
    signals: list[AssetSignal],
    kelly_fraction: float = 0.5,
    max_single_asset_concentration: float = 1.0,
    max_leverage: float = 1.0,
    long_only: bool = True,
) -> dict[str, float]:
    """Size every asset independently via `fractional_kelly_size`, then
    rescale proportionally if the long book would otherwise exceed 100% of
    capital — the paper's own execution rule (RESEARCH.md §2.1): sells
    execute first, remaining cash is redistributed pro-rata across buys,
    scaled down if their sum exceeds unity.
    """
    sizes = {
        s.ticker: fractional_kelly_size(
            s, kelly_fraction, max_single_asset_concentration, max_leverage
        )
        for s in signals
    }
    if long_only:
        sizes = {t: max(0.0, w) for t, w in sizes.items()}

    total_long = sum(w for w in sizes.values() if w > 0)
    if total_long > 1.0:
        scale = 1.0 / total_long
        sizes = {t: (w * scale if w > 0 else w) for t, w in sizes.items()}
    return sizes
