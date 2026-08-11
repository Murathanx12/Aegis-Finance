"""Fetch and cache the price panel the conviction replay runs on.

Deliberately separate from the replay: the replay must be re-runnable without a
network, and a fetch that half-fails must not be indistinguishable from a fetch
that succeeded. Names that fail here are checked against the recorded corporate
actions, and anything failing for a reason NOT on that list aborts the fetch
rather than writing a panel with a hole in it.

    python scripts/fetch_conviction_prices.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yfinance as yf

from backend.services.conviction_prices import (BENCHMARKS, CACHE,
                                                CORPORATE_ACTIONS)
from backend.services.conviction_sheets import all_tickers

START, END = "2025-10-25", "2026-08-12"

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    tickers = sorted(set(all_tickers()) | set(BENCHMARKS))
    logger.info("fetching %d symbols %s -> %s", len(tickers), START, END)

    df = yf.download(tickers, start=START, end=END, auto_adjust=True,
                     progress=False)["Close"]
    empty = sorted(c for c in df.columns if df[c].notna().sum() == 0)
    expected = sorted(CORPORATE_ACTIONS)
    unexplained = [t for t in empty if t not in CORPORATE_ACTIONS]
    if unexplained:
        raise SystemExit(
            f"ABORT: {unexplained} returned no data and have no recorded "
            f"corporate action. Find out what happened to them before writing "
            f"a panel — a silently missing name is removed from one side of the "
            f"selection comparison and moves the answer with nothing to catch it.")
    if empty != expected:
        logger.warning("recorded actions %s but only %s came back empty — a "
                       "name may have resumed trading", expected, empty)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE)
    logger.info("wrote %s  %d bars x %d symbols  (%s .. %s)", CACHE,
                len(df), df.shape[1], df.index.min().date(), df.index.max().date())
    logger.info("terminated by corporate action, carried at payout: %s", empty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
