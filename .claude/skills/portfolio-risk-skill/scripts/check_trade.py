#!/usr/bin/env python3
"""Standalone risk-check CLI. Mirrors crypto_desk/risk/circuit_breakers.py's
thresholds directly (kept in sync by hand — this script has no import
dependency on the rest of the package, matching crypto-signal-skill's
copy-this-one-file design) so this Skill also works dropped into a project
that doesn't have the full crypto_desk package installed.
"""
import argparse
import sys

DAILY_BUG_DETECTOR = 0.20
WEEKLY_BUG_DETECTOR = 0.40
MONTHLY_ALERT_ONLY = 0.70
MAX_CONCENTRATION = 1.00


def check(action: float, daily_drawdown: float, weekly_drawdown: float, monthly_drawdown: float) -> int:
    action = max(-1.0, min(MAX_CONCENTRATION, action))
    print(f"risk-adjusted action (concentration-clipped): {action:+.4f}")

    breached = False
    if abs(daily_drawdown) >= DAILY_BUG_DETECTOR:
        print(f"[HALT] daily drawdown {daily_drawdown:.1%} >= {DAILY_BUG_DETECTOR:.0%} — "
              "more likely a bug than a bet. Halt new entries.")
        breached = True
    if abs(weekly_drawdown) >= WEEKLY_BUG_DETECTOR:
        print(f"[HALT] weekly drawdown {weekly_drawdown:.1%} >= {WEEKLY_BUG_DETECTOR:.0%} — "
              "force to cash, human review before next tick.")
        breached = True
    if abs(monthly_drawdown) >= MONTHLY_ALERT_ONLY:
        print(f"[ALERT-ONLY] monthly drawdown {monthly_drawdown:.1%} >= {MONTHLY_ALERT_ONLY:.0%} — "
              "this IS the capital-risk tolerance. Page the human; do not halt.")
        # deliberately does not set `breached` — this one never blocks execution

    return 1 if breached else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", type=float, required=True)
    parser.add_argument("--daily-drawdown", type=float, default=0.0)
    parser.add_argument("--weekly-drawdown", type=float, default=0.0)
    parser.add_argument("--monthly-drawdown", type=float, default=0.0)
    args = parser.parse_args()
    sys.exit(check(args.action, args.daily_drawdown, args.weekly_drawdown, args.monthly_drawdown))
