"""Crypto Desk — a Claude-native multi-agent crypto trading and portfolio-management system.

Architecture follows arXiv:2501.00826v3 ("LLM-Powered Multi-Agent System for
Automated Crypto Portfolio Management"): a Crypto Agent and a News Agent report
structured signals to a Trading Agent, which fuses them against portfolio state
and a rolling memory into per-asset trade sizing.

See /RESEARCH.md at the repo root for the full research behind every design
choice in this package, and /README.md for how to run it.
"""

__version__ = "0.1.0"
