"""Command-line entrypoint.

    python -m crypto_desk.cli check                       # verify the environment is ready
    python -m crypto_desk.cli backtest --year 2025          # full 52-week reproduction run
    python -m crypto_desk.cli backtest --year 2025 --weeks 4 --universe bitcoin,ethereum  # quick smoke test

Requires ANTHROPIC_API_KEY in the environment for `backtest` (the agents
make real Claude API calls) and outbound network access to
api.coingecko.com and the configured news provider. See README.md.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from crypto_desk.config import DEFAULT_CONFIG, UNIVERSE, UNIVERSE_TICKERS, DeskConfig
from crypto_desk.data.market import fetch_market_history, iso_week_bounds
from crypto_desk.data.news import fetch_weekly_news


def cmd_check(_args: argparse.Namespace) -> int:
    ok = True

    if os.environ.get("ANTHROPIC_API_KEY"):
        print("[ok]   ANTHROPIC_API_KEY is set")
    else:
        print("[warn] ANTHROPIC_API_KEY is not set — agent calls will fail. "
              "See README.md 'Configuration'.")
        ok = False

    try:
        import anthropic  # noqa: F401
        print("[ok]   anthropic package importable")
    except ImportError:
        print("[fail] `anthropic` package not installed — run: pip install -r requirements.txt")
        ok = False

    try:
        import requests  # noqa: F401
        print("[ok]   requests package importable")
    except ImportError:
        print("[fail] `requests` package not installed — run: pip install -r requirements.txt")
        ok = False

    try:
        import numpy  # noqa: F401
        print("[ok]   numpy package importable")
    except ImportError:
        print("[fail] `numpy` package not installed — run: pip install -r requirements.txt")
        ok = False

    from crypto_desk.indicators.skill_signals import composite_skill_signal
    try:
        composite_skill_signal([100.0 + i * 0.1 for i in range(30)])
        print("[ok]   skill-signal indicators compute correctly (no network needed)")
    except Exception as e:  # noqa: BLE001
        print(f"[fail] skill-signal self-check failed: {e}")
        ok = False

    print()
    print("Environment ready for a backtest." if ok else
          "Environment NOT ready — fix the items above before running `backtest`.")
    return 0 if ok else 1


def cmd_backtest(args: argparse.Namespace) -> int:
    from crypto_desk.backtest.harness import BacktestHarness, run_hold_baseline

    universe = args.universe.split(",") if args.universe else UNIVERSE
    config = DeskConfig(universe=universe)
    config.backtest.weeks = args.weeks

    year = args.year
    first_monday, _ = iso_week_bounds(year, 1)
    last_monday, last_sunday = iso_week_bounds(year, args.weeks)
    # Fetch enough lead-in history for a full 30-day lookback on week 1.
    fetch_start = date(first_monday.year - 1, first_monday.month, first_monday.day) \
        if first_monday.month == 1 else first_monday.replace(month=max(1, first_monday.month - 1))

    print(f"Fetching {len(universe)} assets' market history ({fetch_start} .. {last_sunday})...")
    histories = {}
    for coin_id in universe:
        print(f"  {coin_id} ({UNIVERSE_TICKERS.get(coin_id, coin_id)})...", end=" ", flush=True)
        histories[coin_id] = fetch_market_history(coin_id, fetch_start, last_sunday)
        print(f"{len(histories[coin_id].dates)} daily observations")

    print("Fetching weekly news...")
    news_by_week = {}
    for w in range(1, args.weeks + 1):
        week_start, week_end = iso_week_bounds(year, w)
        iso_week = f"{year}-W{w:02d}"
        news_by_week[iso_week] = fetch_weekly_news(week_start, week_end)

    print(f"\nRunning {args.weeks}-week backtest: {config.architecture.value} / {config.capability.value}...")
    harness = BacktestHarness(config, histories, news_by_week)
    result = harness.run(year, start_week=1, n_weeks=args.weeks)

    print("\n=== Multi-agent system ===")
    print(result.metrics.as_dict())

    print("\n=== Baselines ===")
    print("BTC hold:  ", run_hold_baseline(histories, universe, year, 1, args.weeks, weighting="btc").as_dict())
    print("MCap hold: ", run_hold_baseline(histories, universe, year, 1, args.weeks, weighting="mcap").as_dict())

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crypto_desk", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Verify the environment is ready to run a backtest.")

    p_backtest = sub.add_parser("backtest", help="Run the multi-agent backtest.")
    p_backtest.add_argument("--year", type=int, default=2025)
    p_backtest.add_argument("--weeks", type=int, default=52)
    p_backtest.add_argument(
        "--universe", type=str, default=None,
        help="Comma-separated CoinGecko coin IDs (default: full top-15 L1 universe)."
    )

    args = parser.parse_args(argv)
    if args.command == "check":
        return cmd_check(args)
    if args.command == "backtest":
        return cmd_backtest(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
