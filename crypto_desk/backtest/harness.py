"""The 52-week backtest harness, reproducing the blueprint paper's exact
setup (RESEARCH.md §2.3): weekly tick, top-15 L1 universe, $100k start,
0.1%/side transaction cost, leakage-free 30-day lookback windows.

Default behavior is PAPER-FAITHFUL: the Trading Agent's own `action` per
asset is applied directly (as in arXiv:2501.00826v3), after two
deterministic, non-LLM guardrails documented in RESEARCH.md §9.1 — a hard
concentration clip and the circuit breakers. This keeps Phase 1's job
(RESEARCH.md §11: reproduce the paper's baselines) honest: the harness
measures what the agents actually decided, not a re-sizing scheme layered
on top of them. risk/position_sizing.py's fractional-Kelly sizer is
available as an opt-in overlay for the aggressive live path (RESEARCH.md
§7, §9.2) once there's real calibration data for win-probability/win-loss
inputs to feed it — bolting it onto a backtest with invented numbers would
just be a different way of overstating confidence, exactly what RESEARCH.md
§14 argues against.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from crypto_desk.agents.crypto_agent import AssetMarketData, CryptoAgent
from crypto_desk.agents.news_agent import NewsAgent, NewsArticle
from crypto_desk.agents.trading_agent import AssetPosition, PortfolioState, TradingAgent
from crypto_desk.backtest.metrics import PerformanceMetrics, compute_metrics
from crypto_desk.config import DeskConfig, UNIVERSE_TICKERS
from crypto_desk.data.market import DailyMarketHistory, iso_week_bounds
from crypto_desk.portfolio.ledger import PaperLedger
from crypto_desk.risk.circuit_breakers import BreachEvent, CircuitBreaker


@dataclass
class WeekLog:
    iso_week: str
    portfolio_value: float
    weekly_return: float
    breaches: list[BreachEvent]
    trading_note: str


@dataclass
class BacktestResult:
    metrics: PerformanceMetrics
    week_logs: list[WeekLog]
    ledger: PaperLedger


def _portfolio_state_from_ledger(ledger: PaperLedger, prices: dict[str, float]) -> PortfolioState:
    total = ledger.portfolio_value(prices)
    positions = []
    for ticker, pos in ledger.positions.items():
        if pos.units <= 0:
            continue
        mv = pos.market_value(prices[ticker])
        positions.append(AssetPosition(
            ticker=ticker,
            units=pos.units,
            market_value_usd=mv,
            unrealized_pnl_usd=pos.unrealized_pnl(prices[ticker]),
            concentration_pct=(mv / total) if total > 0 else 0.0,
        ))
    return PortfolioState(cash_usd=ledger.cash, total_value_usd=total, positions=positions)


def _clip_actions_to_risk_limits(
    actions: dict[str, float], max_single_asset_concentration: float
) -> dict[str, float]:
    """Deterministic, non-LLM concentration clip (RESEARCH.md §9.1) — the
    Trading Agent's own instructions ask it to respect this, but a
    'portfolio-risk-skill' enforced in code, not hoped-for, is the point."""
    return {t: max(-1.0, min(max_single_asset_concentration, a)) for t, a in actions.items()}


class BacktestHarness:
    def __init__(
        self,
        config: DeskConfig,
        histories: dict[str, DailyMarketHistory],
        news_by_week: dict[str, list[NewsArticle]],
        memory_root: str = ".agent-memory",
    ):
        """`histories`: coin_id -> full-span DailyMarketHistory (fetched once
        up front; `.window()` slices the leakage-free 30-day lookback per
        week). `news_by_week`: ISO week string ("2025-W01") -> that week's
        articles, already fetched.
        """
        self.config = config
        self.histories = histories
        self.news_by_week = news_by_week
        self.crypto_agent = CryptoAgent(config, memory_root=memory_root)
        self.news_agent = NewsAgent(config, memory_root=memory_root)
        self.trading_agent = TradingAgent(config, memory_root=memory_root)
        self.circuit_breaker = CircuitBreaker(config.risk)
        self.ledger = PaperLedger(
            starting_cash_usd=config.backtest.starting_cash_usd,
            transaction_cost_per_side=config.backtest.transaction_cost_per_side,
        )

    def _prices_for_week(self, week_end: date) -> dict[str, float]:
        prices = {}
        for coin_id in self.config.universe:
            ticker = UNIVERSE_TICKERS[coin_id]
            window = self.histories[coin_id].window(week_end, lookback_days=30)
            if not window.closes:
                continue
            prices[ticker] = window.closes[-1]
        return prices

    def run_week(self, iso_year: int, iso_week_num: int) -> WeekLog:
        week_start, week_end = iso_week_bounds(iso_year, iso_week_num)
        iso_week = f"{iso_year}-W{iso_week_num:02d}"

        assets = []
        for coin_id in self.config.universe:
            ticker = UNIVERSE_TICKERS[coin_id]
            window = self.histories[coin_id].window(week_end, lookback_days=30)
            if len(window.closes) < 30:
                continue  # not enough history yet for this asset this early in the backtest
            assets.append(AssetMarketData(
                ticker=ticker, coin_id=coin_id,
                daily_closes=window.closes, daily_volumes=window.volumes,
                daily_market_caps=window.market_caps,
            ))

        crypto_report = self.crypto_agent.run(
            iso_week, assets, circuit_breaker=self.circuit_breaker, as_of=week_end
        )
        news_report = self.news_agent.run(
            iso_week, self.news_by_week.get(iso_week, []),
            circuit_breaker=self.circuit_breaker, as_of=week_end,
        )

        prices = self._prices_for_week(week_end)
        portfolio = _portfolio_state_from_ledger(self.ledger, prices)

        trading_report = self.trading_agent.run(
            iso_week, crypto_report, news_report, portfolio,
            circuit_breaker=self.circuit_breaker, as_of=week_end,
        )

        actions = {a.ticker: a.action for a in trading_report.actions if a.ticker in prices}
        actions = _clip_actions_to_risk_limits(actions, self.config.risk.max_single_asset_concentration)

        result = self.ledger.apply_actions(iso_week, actions, prices)

        breaches: list[BreachEvent] = []
        weekly_breach = self.circuit_breaker.check_weekly_drawdown(
            self.ledger.drawdown_from_peak(), week_end
        )
        if weekly_breach:
            breaches.append(weekly_breach)
        monthly_breach = self.circuit_breaker.check_monthly_drawdown(
            self.ledger.drawdown_from_peak(), week_end
        )
        if monthly_breach:
            breaches.append(monthly_breach)

        return WeekLog(
            iso_week=iso_week,
            portfolio_value=result.portfolio_value_end,
            weekly_return=result.weekly_return,
            breaches=breaches,
            trading_note=trading_report.portfolio_note,
        )

    def run(self, iso_year: int, start_week: int = 1, n_weeks: int | None = None) -> BacktestResult:
        n_weeks = n_weeks or self.config.backtest.weeks
        logs = [self.run_week(iso_year, w) for w in range(start_week, start_week + n_weeks)]
        returns = [log.weekly_return for log in logs]
        metrics = compute_metrics(returns, self.config.backtest.risk_free_rate_annual)
        return BacktestResult(metrics=metrics, week_logs=logs, ledger=self.ledger)


def run_hold_baseline(
    histories: dict[str, DailyMarketHistory],
    universe: list[str],
    iso_year: int,
    start_week: int = 1,
    n_weeks: int = 52,
    starting_cash_usd: float = 100_000.0,
    weighting: str = "mcap",  # "mcap" or "equal" or a single coin_id for a BTC-hold-style baseline
) -> PerformanceMetrics:
    """Passive buy-and-hold baselines (RESEARCH.md §2.4): 100% BTC, or the
    full universe weighted by market cap or equally, bought once and held.
    No transaction costs beyond the single entry (matching the paper's own
    hold-benchmark convention).
    """
    week_end_dates = [iso_week_bounds(iso_year, w)[1] for w in range(start_week, start_week + n_weeks)]

    if weighting in histories or weighting == "btc":
        coin_id = "bitcoin" if weighting == "btc" else weighting
        prices = [
            histories[coin_id].window(d, lookback_days=1).closes[-1]
            for d in week_end_dates
            if histories[coin_id].window(d, lookback_days=1).closes
        ]
        returns = [(prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices))]
        return compute_metrics(returns)

    # Full-universe weighted hold: value-track a fixed initial allocation.
    initial_prices = {
        c: histories[c].window(week_end_dates[0], lookback_days=1).closes[-1]
        for c in universe if histories[c].window(week_end_dates[0], lookback_days=1).closes
    }
    if weighting == "mcap":
        initial_mcaps = {
            c: histories[c].window(week_end_dates[0], lookback_days=1).market_caps[-1]
            for c in initial_prices
        }
        total_mcap = sum(initial_mcaps.values())
        weights = {c: m / total_mcap for c, m in initial_mcaps.items()}
    else:
        weights = {c: 1.0 / len(initial_prices) for c in initial_prices}

    units = {c: (starting_cash_usd * w) / initial_prices[c] for c, w in weights.items()}

    values = []
    for d in week_end_dates:
        v = 0.0
        for c, u in units.items():
            window = histories[c].window(d, lookback_days=1)
            if window.closes:
                v += u * window.closes[-1]
        values.append(v)

    returns = [(values[i] / values[i - 1]) - 1.0 for i in range(1, len(values)) if values[i - 1] > 0]
    return compute_metrics(returns)
