"""The important test in this file: `test_sharpe_matches_paper_reported_value`
reproduces arXiv:2501.00826v3's own published number from its own published
inputs, so the exact annualization convention this codebase uses is proven
to match the paper's, not just "a standard Sharpe formula" in the abstract.
"""
import math

import numpy as np
import pytest

from crypto_desk.backtest.metrics import (
    compute_metrics,
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
)


def test_cumulative_return_compounds():
    m = compute_metrics([0.10, 0.10, -0.10])
    expected = (1.10 * 1.10 * 0.90) - 1.0
    assert m.cumulative_return == pytest.approx(expected)


def test_win_rate():
    m = compute_metrics([0.01, -0.01, 0.02, 0.0, -0.005])
    assert m.win_rate == pytest.approx(2 / 5)


def test_max_drawdown_is_correct_and_non_positive():
    # Value path: 100 -> 120 -> 90 -> 108 (peak 120, trough 90 => -25%)
    returns = [0.20, -0.25, 0.20]
    m = compute_metrics(returns)
    assert m.max_drawdown <= 0
    assert m.max_drawdown == pytest.approx(-0.25, abs=1e-9)


def test_sharpe_matches_paper_reported_value():
    """RESEARCH.md §2.4: Hierarchical+Skill, full period, GPT-4o backbone —
    the paper reports Avg%=+2.12, Vol%=73.40 (annualized), Sharpe=+1.502.
    Reconstruct a 52-week return series with exactly that weekly mean and
    weekly std (sample, ddof=1) and confirm this module's Sharpe formula
    reproduces 1.502 to 2 decimal places, with a zero risk-free rate as the
    paper's own baseline case.
    """
    target_avg = 0.0212
    target_vol_annualized = 0.7340
    target_sharpe = 1.502
    n = 52

    weekly_std = target_vol_annualized / math.sqrt(n)

    # Construct a synthetic series with EXACTLY the target sample mean and
    # sample std: alternate +/- around the mean by a fixed amount that gives
    # the right std for an even n, then nudge for parity.
    rng = np.random.default_rng(seed=42)
    raw = rng.normal(loc=0.0, scale=1.0, size=n)
    raw = raw - raw.mean()  # zero mean
    raw = raw / raw.std(ddof=1)  # unit std
    returns = raw * weekly_std + target_avg  # now has exactly target mean/std

    m = compute_metrics(returns, risk_free_rate_annual=0.0, periods_per_year=52)

    assert m.average_weekly_return == pytest.approx(target_avg, abs=1e-9)
    assert m.annualized_volatility == pytest.approx(target_vol_annualized, abs=1e-6)
    assert m.sharpe_ratio == pytest.approx(target_sharpe, abs=0.01)


def test_probabilistic_sharpe_ratio_bounds():
    # A large observed Sharpe on a long sample should have high confidence
    # of beating a benchmark of 0.
    psr = probabilistic_sharpe_ratio(observed_sharpe=1.5, n_periods=52)
    assert 0.9 < psr <= 1.0

    # An observed Sharpe of exactly the benchmark should sit near 0.5.
    psr_at_benchmark = probabilistic_sharpe_ratio(
        observed_sharpe=0.0, n_periods=52, benchmark_sharpe=0.0
    )
    assert psr_at_benchmark == pytest.approx(0.5, abs=1e-9)


def test_deflated_sharpe_is_stricter_than_psr_against_zero():
    """RESEARCH.md §14.2: deflating against many trials should demand MORE
    of the observed Sharpe than testing it against a flat 0 benchmark —
    i.e. DSR <= PSR(0) for the same observed Sharpe, whenever the trial
    count is large enough that the implied null benchmark is positive."""
    observed_sharpe = 1.502  # the paper's own winning number (RESEARCH.md §2.4)
    n_periods = 52

    psr_vs_zero = probabilistic_sharpe_ratio(observed_sharpe, n_periods, benchmark_sharpe=0.0)
    dsr = deflated_sharpe_ratio(
        observed_sharpe, n_periods, n_trials=12, sharpe_std_across_trials=0.6
    )
    assert dsr <= psr_vs_zero


def test_compute_metrics_requires_at_least_two_periods():
    with pytest.raises(ValueError):
        compute_metrics([0.01])
