"""Paper-trading ledger — the ONLY execution path until RESEARCH.md §9.4's
Phase 2 custody bar is cleared (non-custodial, spend-capped wallet). No
network calls, no real orders; a plain, JSON-persisted simulated portfolio.

Execution rule, matching the blueprint paper exactly (RESEARCH.md §2.1):
each action a_i in [-1, 1] is a fractional adjustment. Positive: buy that
fraction of the post-sell cash pool. Negative: sell that fraction of the
current holding. All sells execute first; the resulting cash is then
redistributed across positive actions, scaled down proportionally if their
sum exceeds 1. A transaction cost is applied to every executed order.

Persistence (`save`/`load`) exists specifically so a state-less, fresh
session — a scheduled Claude Code Routine firing weekly, RESEARCH.md §6.7's
"Claude Code" column, no separate ANTHROPIC_API_KEY involved — can pick up
exactly where the previous week's session left off, the same "state lives
in files, not in a conversation" pattern memory/rolling_memory.py already
uses.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class Position:
    ticker: str
    units: float = 0.0
    cost_basis_usd: float = 0.0  # total USD paid for currently-held units, for unrealized P&L

    def market_value(self, price: float) -> float:
        return self.units * price

    def unrealized_pnl(self, price: float) -> float:
        return self.market_value(price) - self.cost_basis_usd


@dataclass
class WeekResult:
    iso_week: str
    portfolio_value_start: float
    portfolio_value_end: float
    weekly_return: float
    cash_end: float
    positions_end: dict[str, float]  # ticker -> market value
    transaction_costs_paid: float
    actions_applied: dict[str, float]


class PaperLedger:
    """A single long-only book. `max_single_asset_concentration` and
    leverage are enforced upstream by risk/position_sizing.py — this class
    just executes whatever fractional actions it's given, correctly."""

    def __init__(self, starting_cash_usd: float, transaction_cost_per_side: float = 0.001):
        self.cash = starting_cash_usd
        self.transaction_cost_per_side = transaction_cost_per_side
        self.positions: dict[str, Position] = {}
        self.history: list[WeekResult] = []

    def to_dict(self) -> dict:
        return {
            "cash": self.cash,
            "transaction_cost_per_side": self.transaction_cost_per_side,
            "positions": {t: asdict(p) for t, p in self.positions.items()},
            "history": [asdict(w) for w in self.history],
        }

    def save(self, path: Path | str) -> None:
        """Write full ledger state to a JSON file — call this at the end of
        every tick. Atomic-ish: writes to a temp file then renames, so a
        crash mid-write can't leave a half-written, unparseable ledger for
        the next session to load."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path | str) -> "PaperLedger":
        """Reconstruct a ledger from a file written by `save()`. Raises
        FileNotFoundError if `path` doesn't exist yet — callers (e.g. a
        Routine's first-ever firing) should catch that and construct a
        fresh `PaperLedger(starting_cash_usd=...)` instead."""
        data = json.loads(Path(path).read_text())
        ledger = cls(
            starting_cash_usd=data["cash"],
            transaction_cost_per_side=data["transaction_cost_per_side"],
        )
        ledger.positions = {t: Position(**p) for t, p in data["positions"].items()}
        ledger.history = [WeekResult(**w) for w in data["history"]]
        return ledger

    def portfolio_value(self, prices: dict[str, float]) -> float:
        value = self.cash
        for ticker, pos in self.positions.items():
            if pos.units > 0:
                value += pos.market_value(prices[ticker])
        return value

    def apply_actions(
        self,
        iso_week: str,
        actions: dict[str, float],
        prices: dict[str, float],
    ) -> WeekResult:
        """`actions`: ticker -> a_i in [-1, 1]. `prices`: ticker -> current
        USD price for every ticker referenced in `actions` or currently held.
        """
        value_start = self.portfolio_value(prices)
        costs_paid = 0.0

        # 1) Sells execute first.
        for ticker, a in actions.items():
            if a >= 0:
                continue
            pos = self.positions.get(ticker)
            if pos is None or pos.units <= 0:
                continue
            price = prices[ticker]
            sell_fraction = min(1.0, -a)
            units_to_sell = pos.units * sell_fraction
            proceeds = units_to_sell * price
            cost = proceeds * self.transaction_cost_per_side
            costs_paid += cost
            self.cash += proceeds - cost
            sold_cost_basis = pos.cost_basis_usd * sell_fraction
            pos.units -= units_to_sell
            pos.cost_basis_usd -= sold_cost_basis
            if pos.units <= 1e-12:
                pos.units = 0.0
                pos.cost_basis_usd = 0.0

        # 2) Cash from sells is redistributed across buys, scaled down
        #    proportionally if their sum exceeds unity (paper's own rule).
        buy_actions = {t: a for t, a in actions.items() if a > 0}
        total_buy_fraction = sum(buy_actions.values())
        scale = 1.0 if total_buy_fraction <= 1.0 else 1.0 / total_buy_fraction
        available_cash = self.cash

        for ticker, a in buy_actions.items():
            price = prices[ticker]
            spend = available_cash * a * scale
            if spend <= 0:
                continue
            cost = spend * self.transaction_cost_per_side
            net_spend = spend - cost
            if net_spend <= 0:
                continue
            units_bought = net_spend / price
            costs_paid += cost
            self.cash -= spend
            pos = self.positions.setdefault(ticker, Position(ticker=ticker))
            pos.units += units_bought
            pos.cost_basis_usd += net_spend

        value_end = self.portfolio_value(prices)
        weekly_return = (value_end / value_start) - 1.0 if value_start > 0 else 0.0

        result = WeekResult(
            iso_week=iso_week,
            portfolio_value_start=value_start,
            portfolio_value_end=value_end,
            weekly_return=weekly_return,
            cash_end=self.cash,
            positions_end={t: p.market_value(prices[t]) for t, p in self.positions.items() if p.units > 0},
            transaction_costs_paid=costs_paid,
            actions_applied=dict(actions),
        )
        self.history.append(result)
        return result

    def weekly_returns(self) -> list[float]:
        return [w.weekly_return for w in self.history]

    def concentration(self, prices: dict[str, float]) -> dict[str, float]:
        """Each held position's share of total portfolio value — for the
        pre-trade concentration-cap check (RESEARCH.md §9.1)."""
        total = self.portfolio_value(prices)
        if total <= 0:
            return {}
        return {
            t: p.market_value(prices[t]) / total
            for t, p in self.positions.items() if p.units > 0
        }

    def drawdown_from_peak(self) -> float:
        """Current drawdown from the highest portfolio value seen so far in
        this ledger's history — feeds the circuit breakers directly."""
        if not self.history:
            return 0.0
        values = [w.portfolio_value_end for w in self.history]
        peak = max(values)
        if peak <= 0:
            return 0.0
        return (values[-1] / peak) - 1.0
