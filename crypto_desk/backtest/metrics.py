"""Performance metrics reproducing the blueprint paper's harness exactly
(RESEARCH.md §2.3, §10.1), plus the deflated Sharpe ratio (RESEARCH.md §14.2)
for judging whichever configuration comes out on top of this project's own
architecture x capability grid.

Formula note (worth keeping, since it wasn't obvious on first read of the
paper): the paper reports Sharpe = (mean_weekly_excess_return * 52) /
annualized_volatility. Algebraically that is IDENTICAL to the standard
per-period-Sharpe-scaled-by-sqrt(periods_per_year) formula, since
annualized_volatility = weekly_std * sqrt(52), so
(mean*52)/(weekly_std*sqrt(52)) == (mean/weekly_std)*sqrt(52). Implemented
below as the standard form. Verified against the paper's own published
number in tests/test_metrics.py: Hierarchical+Skill's reported Avg%=+2.12%,
Vol%=73.40%, Sharpe=1.502 reproduce exactly from this formula.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PerformanceMetrics:
    cumulative_return: float       # prod(1+r_t) - 1
    average_weekly_return: float   # mean(r_t)
    annualized_volatility: float   # std(r_t, ddof=1) * sqrt(periods_per_year)
    sharpe_ratio: float            # (mean(r_t) - rf) / std(r_t, ddof=1) * sqrt(periods_per_year)
    max_drawdown: float            # min_t( V_t / max_{s<=t}(V_s) - 1 ), <= 0
    win_rate: float                # mean(r_t > 0)
    n_periods: int

    def as_dict(self) -> dict:
        return {
            "cum_pct": round(self.cumulative_return * 100, 2),
            "avg_pct": round(self.average_weekly_return * 100, 2),
            "vol_pct": round(self.annualized_volatility * 100, 2),
            "sharpe": round(self.sharpe_ratio, 3),
            "mdd_pct": round(self.max_drawdown * 100, 2),
            "win_pct": round(self.win_rate * 100, 1),
            "n_periods": self.n_periods,
        }


def compute_metrics(
    returns: list[float] | np.ndarray,
    risk_free_rate_annual: float = 0.0,
    periods_per_year: int = 52,
) -> PerformanceMetrics:
    """`returns` is a sequence of per-period (weekly, by the paper's own
    convention) portfolio returns, e.g. [0.012, -0.03, 0.05, ...]."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        raise ValueError("need at least 2 periods of returns to compute volatility/Sharpe")

    rf_period = risk_free_rate_annual / periods_per_year

    cumulative = float(np.prod(1.0 + r) - 1.0)
    avg = float(np.mean(r))
    std = float(np.std(r, ddof=1))
    vol_annualized = std * math.sqrt(periods_per_year)

    sharpe = ((avg - rf_period) / std) * math.sqrt(periods_per_year) if std > 0 else 0.0

    equity_curve = np.cumprod(1.0 + r)
    running_peak = np.maximum.accumulate(equity_curve)
    drawdowns = equity_curve / running_peak - 1.0
    mdd = float(np.min(drawdowns))

    win_rate = float(np.mean(r > 0))

    return PerformanceMetrics(
        cumulative_return=cumulative,
        average_weekly_return=avg,
        annualized_volatility=vol_annualized,
        sharpe_ratio=sharpe,
        max_drawdown=mdd,
        win_rate=win_rate,
        n_periods=len(r),
    )


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse normal CDF via Acklam's rational approximation (no scipy
    dependency). Accurate to ~1e-9 across (0, 1), which is far more than
    this diagnostic needs."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low, p_high = 0.02425, 1 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    n_periods: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sharpe: float = 0.0,
) -> float:
    """PSR(SR*): the probability the TRUE Sharpe ratio exceeds a benchmark,
    given the observed Sharpe, sample length, and return distribution shape
    (Bailey & Lopez de Prado, 2012). `kurtosis` is the non-excess kurtosis
    (normal = 3.0), matching scipy's `fisher=False` convention.
    """
    if n_periods < 2:
        raise ValueError("need at least 2 periods")
    denom = math.sqrt(max(1e-12, 1 - skewness * observed_sharpe + ((kurtosis - 1) / 4) * observed_sharpe ** 2))
    z = (observed_sharpe - benchmark_sharpe) * math.sqrt(n_periods - 1) / denom
    return _norm_cdf(z)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_periods: int,
    n_trials: int,
    sharpe_std_across_trials: float,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """DSR: PSR evaluated against the *expected maximum* Sharpe ratio one
    would see under the null across `n_trials` independent strategy
    variants — the correction RESEARCH.md §14.2 flags as missing from "the
    best of many tested configurations" claims (Bailey & Lopez de Prado,
    2014). Report this, not the raw Sharpe, whenever a configuration was
    selected because it won a grid search (e.g. this project's own
    architecture x capability sweep, RESEARCH.md §7, §10).

    `sharpe_std_across_trials` is the standard deviation of the Sharpe
    ratios observed across all `n_trials` variants (not just the winner) —
    it has to be estimated from the actual sweep; there's no way around
    running the other configurations to get it.
    """
    if n_trials < 2:
        raise ValueError("deflation requires at least 2 trials to define a null")
    euler_mascheroni = 0.5772156649015329
    sr0 = sharpe_std_across_trials * (
        (1 - euler_mascheroni) * _norm_ppf(1 - 1.0 / n_trials)
        + euler_mascheroni * _norm_ppf(1 - 1.0 / (n_trials * math.e))
    )
    return probabilistic_sharpe_ratio(
        observed_sharpe, n_periods, skewness=skewness, kurtosis=kurtosis, benchmark_sharpe=sr0
    )
