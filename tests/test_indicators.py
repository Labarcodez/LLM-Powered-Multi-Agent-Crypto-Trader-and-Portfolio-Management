import numpy as np
import pytest

from crypto_desk.indicators.skill_signals import composite_skill_signal


def test_raises_below_30_observations():
    with pytest.raises(ValueError):
        composite_skill_signal([100.0] * 29)


def test_flat_price_is_not_sma7_bullish_and_not_bb_bullish():
    """A perfectly flat 30-day price: price == SMA7 (not strictly greater,
    so not bullish), and price is not below the lower Bollinger Band
    (std == 0, so bb_lower == price, and strict '<' is false)."""
    closes = [100.0] * 30
    s = composite_skill_signal(closes)
    assert s.sma7_bullish is False
    assert s.bb_bullish is False
    assert s.macd_histogram == pytest.approx(0.0, abs=1e-9)
    assert s.bullish_count == 0
    assert s.strength == 0.0


def test_strong_uptrend_is_bullish_on_sma_and_macd():
    """A steadily rising price series should read SMA7-bullish (price above
    its own recent average), SLMA-bullish (short MA above long MA in an
    uptrend), and MACD-bullish (positive momentum)."""
    closes = [100.0 + i * 1.5 for i in range(30)]  # steady uptrend
    s = composite_skill_signal(closes)
    assert s.sma7_bullish is True
    assert s.slma_bullish is True
    assert s.macd_bullish is True
    assert s.bullish_count >= 3


def test_sharp_drop_below_lower_band_is_bb_bullish_contrarian():
    """29 flat days then a sharp one-day crash should trip the Bollinger
    contrarian buy signal (oversold relative to the 20-day distribution)."""
    closes = [100.0] * 29 + [70.0]
    s = composite_skill_signal(closes)
    assert s.bb_bullish is True


def test_composite_strength_is_bullish_count_over_four():
    closes = [100.0 + i * 1.5 for i in range(30)]
    s = composite_skill_signal(closes)
    assert s.strength == pytest.approx(s.bullish_count / 4.0)
    assert 0.0 <= s.strength <= 1.0


def test_accepts_numpy_array_input():
    closes = np.array([100.0 + i for i in range(30)])
    s = composite_skill_signal(closes)
    assert isinstance(s.bullish_count, int)


def test_prompt_fragment_contains_ticker_and_count():
    closes = [100.0 + i for i in range(30)]
    s = composite_skill_signal(closes)
    frag = s.as_prompt_fragment("BTC")
    assert "BTC" in frag
    assert f"{s.bullish_count}/4" in frag
