"""Circuit breakers — malfunction detectors, not loss limiters (RESEARCH.md
§9.1). This module NEVER decides "the strategy is doing badly, stop it" —
only "this looks more like a bug than a bet." It is deliberately dumb and
deterministic: no LLM call, no judgment call, so an agent mid-incident
(RESEARCH.md §8.3) cannot reason its way past it.

This is the code-level half of the kill switch described in RESEARCH.md
§8.3 / Fig. 3 — it decides WHEN to trip. What happens on a trip (freeze a
wallet, revoke an API key, page a human) is deliberately NOT this module's
job: RESEARCH.md is explicit that the action has to live outside the trading
loop's own control flow, e.g. a Managed Agents vault/session budget
(RESEARCH.md §6.3-6.4) or an external watchdog process — wire a real
handler in before this runs against anything but a paper ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from crypto_desk.config import RiskConfig


class BreachType(str, Enum):
    DAILY_DRAWDOWN = "daily_drawdown"
    WEEKLY_DRAWDOWN = "weekly_drawdown"
    MONTHLY_DRAWDOWN_ALERT = "monthly_drawdown_alert"
    CONSECUTIVE_PAID_CALLS = "consecutive_paid_calls"


@dataclass(frozen=True)
class BreachEvent:
    breach_type: BreachType
    observed: float
    threshold: float
    as_of: date
    message: str
    # Only MONTHLY_DRAWDOWN_ALERT is a real risk-tolerance signal; every
    # other breach type should halt new activity, per RESEARCH.md §9.1.
    should_halt_new_entries: bool


class CircuitBreaker:
    """Stateless-per-call checker. Call the relevant `check_*` method every
    tick with the observed drawdown/call-count; it returns a `BreachEvent`
    or `None`. Callers are responsible for actually halting on a breach —
    this class only detects and reports.
    """

    def __init__(self, config: RiskConfig):
        self.config = config
        self._consecutive_paid_calls = 0

    def check_daily_drawdown(self, drawdown_pct: float, as_of: date) -> BreachEvent | None:
        threshold = self.config.daily_drawdown_bug_detector
        if abs(drawdown_pct) >= threshold:
            return BreachEvent(
                BreachType.DAILY_DRAWDOWN, drawdown_pct, threshold, as_of,
                f"Daily drawdown {drawdown_pct:.1%} >= {threshold:.0%} bug-detector threshold. "
                "A move this large in one day from a functioning strategy is plausible, but a bug "
                "is more likely than a bet — halt new entries and investigate before continuing.",
                should_halt_new_entries=True,
            )
        return None

    def check_weekly_drawdown(self, drawdown_pct: float, as_of: date) -> BreachEvent | None:
        threshold = self.config.weekly_drawdown_bug_detector
        if abs(drawdown_pct) >= threshold:
            return BreachEvent(
                BreachType.WEEKLY_DRAWDOWN, drawdown_pct, threshold, as_of,
                f"Weekly drawdown {drawdown_pct:.1%} >= {threshold:.0%} bug-detector threshold. "
                "Force to cash; human review before the next tick.",
                should_halt_new_entries=True,
            )
        return None

    def check_monthly_drawdown(self, drawdown_pct: float, as_of: date) -> BreachEvent | None:
        threshold = self.config.monthly_drawdown_alert_only
        if abs(drawdown_pct) >= threshold:
            return BreachEvent(
                BreachType.MONTHLY_DRAWDOWN_ALERT, drawdown_pct, threshold, as_of,
                f"Monthly drawdown {drawdown_pct:.1%} >= {threshold:.0%}. This IS the capital-risk "
                "tolerance set by direction — no forced flatten. Page the human; do not halt trading.",
                should_halt_new_entries=False,
            )
        return None

    def record_paid_call(self, as_of: date) -> BreachEvent | None:
        """Call once per paid model invocation in a retry/reasoning loop;
        call `reset_call_counter()` once the loop completes normally."""
        self._consecutive_paid_calls += 1
        threshold = self.config.max_consecutive_paid_calls_before_lockout
        if self._consecutive_paid_calls >= threshold:
            return BreachEvent(
                BreachType.CONSECUTIVE_PAID_CALLS, self._consecutive_paid_calls, threshold, as_of,
                f"{self._consecutive_paid_calls} consecutive paid model calls without completing — "
                "likely a retry storm or reasoning loop, not legitimate work. Lock out further calls "
                "this cycle; a runaway loop should cost a few cents, not a runaway bill.",
                should_halt_new_entries=True,
            )
        return None

    def reset_call_counter(self) -> None:
        self._consecutive_paid_calls = 0
