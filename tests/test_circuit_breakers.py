from datetime import date

from crypto_desk.config import RiskConfig
from crypto_desk.risk.circuit_breakers import BreachType, CircuitBreaker


def make_breaker(**overrides) -> CircuitBreaker:
    return CircuitBreaker(RiskConfig(**overrides))


def test_daily_breach_detected_and_halts():
    cb = make_breaker(daily_drawdown_bug_detector=0.20)
    breach = cb.check_daily_drawdown(-0.25, date(2025, 1, 1))
    assert breach is not None
    assert breach.breach_type == BreachType.DAILY_DRAWDOWN
    assert breach.should_halt_new_entries is True


def test_daily_no_breach_below_threshold():
    cb = make_breaker(daily_drawdown_bug_detector=0.20)
    assert cb.check_daily_drawdown(-0.05, date(2025, 1, 1)) is None


def test_monthly_breach_is_alert_only_not_halt():
    """RESEARCH.md §9.1: the monthly threshold is the one real capital-risk
    number and should NOT halt trading, only alert."""
    cb = make_breaker(monthly_drawdown_alert_only=0.70)
    breach = cb.check_monthly_drawdown(-0.75, date(2025, 1, 1))
    assert breach is not None
    assert breach.should_halt_new_entries is False


def test_consecutive_paid_calls_locks_out_at_threshold():
    cb = make_breaker(max_consecutive_paid_calls_before_lockout=3)
    d = date(2025, 1, 1)
    assert cb.record_paid_call(d) is None
    assert cb.record_paid_call(d) is None
    breach = cb.record_paid_call(d)
    assert breach is not None
    assert breach.breach_type == BreachType.CONSECUTIVE_PAID_CALLS


def test_reset_call_counter_clears_the_lockout():
    cb = make_breaker(max_consecutive_paid_calls_before_lockout=2)
    d = date(2025, 1, 1)
    cb.record_paid_call(d)
    cb.reset_call_counter()
    assert cb.record_paid_call(d) is None  # back to count=1, not tripped
