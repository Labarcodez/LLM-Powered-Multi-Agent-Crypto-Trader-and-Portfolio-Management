#!/usr/bin/env python3
"""Standalone CLI wrapper around crypto_desk.indicators.skill_signals so this
Skill has no import-path dependency on the rest of the package — copy this
one file plus the SKILL.md and it works on its own.

    python3 signal.py --closes "100.1,101.2,99.8,...(>=30 comma-separated values)"
"""
import argparse
import json
import sys

import numpy as np


def _ema(values: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def composite_skill_signal(closes: list[float]) -> dict:
    closes = np.asarray(closes, dtype=float)
    if len(closes) < 30:
        raise ValueError(f"need at least 30 daily closes, got {len(closes)}")

    price_t = float(closes[-1])
    sma7 = float(np.mean(closes[-7:]))
    sma7_bullish = bool(price_t > sma7)

    sma30 = float(np.mean(closes[-30:]))
    slma_bullish = bool(sma7 > sma30)

    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    histogram = float(macd_line[-1] - signal_line[-1])
    macd_bullish = bool(histogram > 0)

    window20 = closes[-20:]
    mean20, std20 = float(np.mean(window20)), float(np.std(window20, ddof=0))
    bb_lower = mean20 - 2.0 * std20
    bb_bullish = bool(price_t < bb_lower)

    bullish_count = int(sum([sma7_bullish, slma_bullish, macd_bullish, bb_bullish]))
    return {
        "sma7_bullish": sma7_bullish, "slma_bullish": slma_bullish,
        "macd_bullish": macd_bullish, "bb_bullish": bb_bullish,
        "bullish_count": bullish_count, "strength": bullish_count / 4.0,
        "macd_histogram": histogram, "sma7": sma7, "sma30": sma30, "bb_lower": bb_lower,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--closes", required=True, help="comma-separated daily closes, oldest first")
    args = parser.parse_args()
    try:
        closes = [float(x) for x in args.closes.split(",")]
        print(json.dumps(composite_skill_signal(closes), indent=2))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
