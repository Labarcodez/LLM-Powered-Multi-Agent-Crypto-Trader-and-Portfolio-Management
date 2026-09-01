import pytest

from crypto_desk.portfolio.ledger import PaperLedger


def test_buy_deducts_cash_and_transaction_cost():
    ledger = PaperLedger(starting_cash_usd=100_000.0, transaction_cost_per_side=0.01)
    prices = {"BTC": 100.0}
    result = ledger.apply_actions("2025-W01", {"BTC": 1.0}, prices)

    # Spend 100% of cash on BTC; 1% transaction cost taken out of the spend.
    assert ledger.cash == pytest.approx(0.0, abs=1e-6)
    expected_units = (100_000.0 * 0.99) / 100.0
    assert ledger.positions["BTC"].units == pytest.approx(expected_units)
    assert result.transaction_costs_paid == pytest.approx(1_000.0)


def test_sell_before_buy_ordering_matches_paper_rule():
    """RESEARCH.md §2.1: all sells execute first; cash raised funds buys the
    same week."""
    ledger = PaperLedger(starting_cash_usd=100_000.0, transaction_cost_per_side=0.0)
    ledger.apply_actions("2025-W01", {"BTC": 1.0}, {"BTC": 100.0})
    assert ledger.cash == pytest.approx(0.0)

    # Sell half of BTC and use the proceeds to buy ETH, same week.
    result = ledger.apply_actions("2025-W02", {"BTC": -0.5, "ETH": 1.0}, {"BTC": 100.0, "ETH": 50.0})
    assert ledger.positions["BTC"].units == pytest.approx(500.0)  # half of original 1000 units
    assert "ETH" in ledger.positions
    assert result.portfolio_value_end == pytest.approx(result.portfolio_value_start, rel=1e-6)


def test_buy_actions_summing_over_one_are_scaled_down_proportionally():
    ledger = PaperLedger(starting_cash_usd=100_000.0, transaction_cost_per_side=0.0)
    result = ledger.apply_actions("2025-W01", {"A": 0.8, "B": 0.8}, {"A": 10.0, "B": 10.0})
    # Both wanted 0.8 (sum 1.6 > 1) -> each scaled to 0.5 of cash.
    assert ledger.positions["A"].units == pytest.approx(ledger.positions["B"].units)
    assert ledger.cash == pytest.approx(0.0, abs=1e-6)
    assert result.portfolio_value_end == pytest.approx(100_000.0, rel=1e-6)


def test_portfolio_value_tracks_price_moves():
    ledger = PaperLedger(starting_cash_usd=100_000.0, transaction_cost_per_side=0.0)
    ledger.apply_actions("2025-W01", {"BTC": 1.0}, {"BTC": 100.0})
    assert ledger.portfolio_value({"BTC": 150.0}) == pytest.approx(150_000.0)
    assert ledger.portfolio_value({"BTC": 50.0}) == pytest.approx(50_000.0)


def test_drawdown_from_peak_tracks_correctly():
    ledger = PaperLedger(starting_cash_usd=100_000.0, transaction_cost_per_side=0.0)
    ledger.apply_actions("2025-W01", {}, {})  # no-op week, value stays 100k
    ledger.apply_actions("2025-W02", {"BTC": 1.0}, {"BTC": 100.0})  # still 100k
    ledger.apply_actions("2025-W03", {}, {"BTC": 50.0})  # value drops to 50k
    assert ledger.drawdown_from_peak() == pytest.approx(-0.5, abs=1e-6)


def test_concentration_reports_share_of_total_value():
    ledger = PaperLedger(starting_cash_usd=100_000.0, transaction_cost_per_side=0.0)
    ledger.apply_actions("2025-W01", {"BTC": 0.5}, {"BTC": 100.0})
    conc = ledger.concentration({"BTC": 100.0})
    assert conc["BTC"] == pytest.approx(0.5, abs=1e-6)
