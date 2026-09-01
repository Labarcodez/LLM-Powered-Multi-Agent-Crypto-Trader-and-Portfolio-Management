import pytest

from crypto_desk.risk.position_sizing import (
    AssetSignal,
    fractional_kelly_size,
    kelly_criterion,
    size_portfolio,
)


def test_kelly_criterion_classic_coinflip_with_edge():
    # p=0.6, b=1 (even-money payoff) => f* = 0.6 - 0.4/1 = 0.2
    assert kelly_criterion(0.6, 1.0) == pytest.approx(0.2)


def test_kelly_criterion_negative_edge_is_negative():
    # p=0.4, b=1 => f* = 0.4 - 0.6/1 = -0.2 (don't take this bet)
    assert kelly_criterion(0.4, 1.0) == pytest.approx(-0.2)


def test_kelly_criterion_rejects_invalid_probability():
    with pytest.raises(ValueError):
        kelly_criterion(1.0, 1.0)
    with pytest.raises(ValueError):
        kelly_criterion(0.0, 1.0)


def test_fractional_kelly_damps_by_configured_fraction():
    signal = AssetSignal(ticker="BTC", signal_strength=1.0, win_probability=0.6, win_loss_ratio=1.0)
    full = fractional_kelly_size(signal, kelly_fraction=1.0, max_single_asset_concentration=1.0, max_leverage=1.0)
    half = fractional_kelly_size(signal, kelly_fraction=0.5, max_single_asset_concentration=1.0, max_leverage=1.0)
    assert half == pytest.approx(full / 2, rel=1e-9)


def test_fractional_kelly_respects_concentration_cap():
    # Deliberately strong edge that would exceed a tight cap.
    signal = AssetSignal(ticker="BTC", signal_strength=1.0, win_probability=0.9, win_loss_ratio=5.0)
    sized = fractional_kelly_size(
        signal, kelly_fraction=1.0, max_single_asset_concentration=0.10, max_leverage=1.0
    )
    assert sized == pytest.approx(0.10)


def test_fractional_kelly_sign_matches_signal_direction():
    bearish = AssetSignal(ticker="ETH", signal_strength=-0.8, win_probability=0.6, win_loss_ratio=1.0)
    sized = fractional_kelly_size(bearish, kelly_fraction=0.5, max_single_asset_concentration=1.0, max_leverage=1.0)
    assert sized < 0


def test_size_portfolio_rescales_when_long_book_exceeds_full_capital():
    signals = [
        AssetSignal(ticker="A", signal_strength=1.0, win_probability=0.9, win_loss_ratio=5.0),
        AssetSignal(ticker="B", signal_strength=1.0, win_probability=0.9, win_loss_ratio=5.0),
        AssetSignal(ticker="C", signal_strength=1.0, win_probability=0.9, win_loss_ratio=5.0),
    ]
    sizes = size_portfolio(
        signals, kelly_fraction=1.0, max_single_asset_concentration=1.0, max_leverage=1.0
    )
    assert sum(sizes.values()) <= 1.0 + 1e-9


def test_size_portfolio_long_only_clips_negative_signals_to_zero():
    signals = [AssetSignal(ticker="A", signal_strength=-0.5, win_probability=0.6, win_loss_ratio=1.0)]
    sizes = size_portfolio(signals, long_only=True)
    assert sizes["A"] == 0.0
