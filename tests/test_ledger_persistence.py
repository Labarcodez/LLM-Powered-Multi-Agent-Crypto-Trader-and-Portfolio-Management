import pytest

from crypto_desk.portfolio.ledger import PaperLedger


def test_save_load_roundtrip_preserves_full_state(tmp_path):
    ledger = PaperLedger(starting_cash_usd=100_000.0, transaction_cost_per_side=0.001)
    ledger.apply_actions("2026-W36", {"BTC": 0.5}, {"BTC": 77_118.45})
    ledger.apply_actions("2026-W37", {"BTC": -0.2, "ETH": 0.3}, {"BTC": 80_000.0, "ETH": 2_500.0})

    path = tmp_path / "ledger.json"
    ledger.save(path)
    assert path.exists()

    restored = PaperLedger.load(path)
    assert restored.cash == ledger.cash
    assert restored.transaction_cost_per_side == ledger.transaction_cost_per_side
    assert set(restored.positions.keys()) == set(ledger.positions.keys())
    for ticker in ledger.positions:
        assert restored.positions[ticker].units == ledger.positions[ticker].units
        assert restored.positions[ticker].cost_basis_usd == ledger.positions[ticker].cost_basis_usd
    assert len(restored.history) == len(ledger.history) == 2
    assert restored.drawdown_from_peak() == ledger.drawdown_from_peak()


def test_load_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        PaperLedger.load(tmp_path / "does-not-exist.json")


def test_a_freshly_loaded_ledger_can_keep_trading(tmp_path):
    """The actual use case: a fresh Routine session loads last week's state
    and applies this week's actions on top of it."""
    week1 = PaperLedger(starting_cash_usd=100_000.0, transaction_cost_per_side=0.0)
    week1.apply_actions("2026-W36", {"BTC": 1.0}, {"BTC": 100.0})
    path = tmp_path / "ledger.json"
    week1.save(path)

    week2 = PaperLedger.load(path)
    result = week2.apply_actions("2026-W37", {"BTC": -1.0}, {"BTC": 120.0})
    assert result.portfolio_value_end == pytest.approx(120_000.0)
    assert week2.cash == pytest.approx(120_000.0)
