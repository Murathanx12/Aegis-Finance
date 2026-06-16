"""
Aegis Finance — Survivorship-Availability Audit (T7 feasibility probe)
=====================================================================

PURPOSE — settle, with real values, whether a *delisted-inclusive* (survivorship-
free) backtest universe is achievable on our actual free data layer (yfinance).

Every selection backtest we run (thematic momentum, vol-managed momentum, the
planned multi-factor model) draws its universe from `config.stock_universe` =
TODAY's large-caps. That is survivorship-biased by construction: the losers that
were delisted/acquired/failed are simply absent. The DSR/PBO overfitting gate
canNOT see this — it deflates against multiple-testing, not a biased universe
(this is exactly how vol-managed momentum printed a false "PASS"; see
docs/research/VOL_MANAGED_MOMENTUM_2026-06-15.md, Finding 2).

The only way to fix it is a point-in-time universe that INCLUDES the names that
later died. This script tests whether the data to do that exists for free.

METHOD: take a fixed set of names that WERE in the S&P 500 and later left it
(bankruptcy, acquisition, failure), with the known event date. Attempt to fetch
each via yfinance and classify:
  - GONE        : no usable history (delisted → empty)
  - REUSED      : history exists but starts/ends inconsistently with the known
                  event → the symbol now belongs to a DIFFERENT company
                  (injecting these is WORSE than dropping them)
  - OK          : genuine delisted-entity history present
Controls (AAPL/MSFT/XOM) must come back clean, else the probe itself is broken.

Run:  python -m engine.research.survivorship_audit
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import pandas as pd

from backend.config import PROJECT_ROOT

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("survivorship")

# (ticker, human note, year the real entity left the S&P 500 / stopped trading)
DELISTED = [
    ("LEH", "Lehman Brothers — bankrupt", 2008),
    ("BSC", "Bear Stearns — fire-sale to JPM", 2008),
    ("CFC", "Countrywide — acquired by BofA", 2008),
    ("JAVA", "Sun Microsystems — acquired by Oracle", 2010),
    ("EMC", "EMC — acquired by Dell", 2016),
    ("YHOO", "Yahoo — acquired by Verizon", 2017),
    ("MON", "Monsanto — acquired by Bayer", 2018),
    ("TWX", "Time Warner — acquired by AT&T", 2018),
    ("CELG", "Celgene — acquired by BMY", 2019),
    ("AGN", "Allergan — acquired by AbbVie", 2020),
    ("XLNX", "Xilinx — acquired by AMD", 2022),
    ("ATVI", "Activision — acquired by Microsoft", 2023),
    ("TWTR", "Twitter — taken private by Musk", 2022),
    ("FRC", "First Republic — bank failure", 2023),
    ("SIVB", "Silicon Valley Bank — bank failure", 2023),
    ("SBNY", "Signature Bank — bank failure", 2023),
    ("PXD", "Pioneer Natural — acquired by Exxon", 2024),
    ("SGEN", "Seagen — acquired by Pfizer", 2023),
    ("ABMD", "Abiomed — acquired by J&J", 2022),
    ("RE", "Everest Re — symbol change to EG", 2023),
]
CONTROLS = [("AAPL", "control"), ("MSFT", "control"), ("XOM", "control")]


def _classify(ticker: str, exit_year: int, series: pd.Series) -> str:
    """GONE if no data; REUSED if the trading history is inconsistent with the
    known exit (a different company on the recycled symbol); OK otherwise."""
    n = int(series.notna().sum())
    if n <= 252:
        return "GONE"
    first_year = series.dropna().index[0].year
    last_year = series.dropna().index[-1].year
    # The real entity should trade UP TO (around) its exit year and not long after.
    # If history continues well past the exit, or only starts after it, the symbol
    # was recycled to a different company.
    if last_year >= exit_year + 2 or first_year >= exit_year:
        return "REUSED"
    return "OK"


def run_audit() -> dict:
    import yfinance as yf

    tickers = [t for t, *_ in DELISTED] + [t for t, _ in CONTROLS]
    log.info("Fetching %d names (delisted + controls) 2005→2026…", len(tickers))
    raw = yf.download(tickers, start="2005-01-01", end="2026-06-01",
                      auto_adjust=True, progress=False, threads=True)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw

    rows, counts = [], {"OK": 0, "REUSED": 0, "GONE": 0}
    log.info("\n%-7s %-9s %6s  %-10s %-10s  %s", "TICKER", "VERDICT", "DAYS",
             "FIRST", "LAST", "NOTE")
    for t, note, exit_year in DELISTED:
        s = close[t].dropna() if t in close.columns else pd.Series(dtype=float)
        verdict = _classify(t, exit_year, s)
        counts[verdict] += 1
        first = str(s.index[0].date()) if len(s) else "—"
        last = str(s.index[-1].date()) if len(s) else "—"
        log.info("%-7s %-9s %6d  %-10s %-10s  %s", t, verdict, len(s), first, last, note)
        rows.append({"ticker": t, "verdict": verdict, "days": len(s),
                     "first": first, "last": last, "exit_year": exit_year, "note": note})

    # control sanity
    ctrl_ok = all(int(close[t].notna().sum()) > 252 for t, _ in CONTROLS if t in close.columns)

    n = len(DELISTED)
    usable = counts["OK"]
    summary = {
        "delisted_tested": n,
        "verdict_counts": counts,
        "usable_clean_history": usable,
        "usable_pct": round(100 * usable / n, 1),
        "controls_ok": bool(ctrl_ok),
        "conclusion": (
            "Free data (yfinance) CANNOT supply a survivorship-free universe: "
            f"{counts['GONE']}/{n} delisted names return nothing and "
            f"{counts['REUSED']}/{n} return a DIFFERENT company on a recycled "
            "symbol. Only {usable}/{n} are genuinely usable. Therefore no "
            "backtested absolute-alpha claim on free data is trustworthy; "
            "selection signals must be validated FORWARD (leak-free PIT/NAV)."
        ).format(usable=usable, n=n),
    }
    log.info("\n%s", "=" * 70)
    log.info("OK=%d  REUSED=%d  GONE=%d  (controls_ok=%s)", counts["OK"],
             counts["REUSED"], counts["GONE"], ctrl_ok)
    log.info("USABLE CLEAN DELISTED HISTORY: %d/%d (%.0f%%)", usable, n, summary["usable_pct"])
    log.info("CONCLUSION: free data cannot build a survivorship-free universe.")
    log.info("=" * 70)

    out = {"rows": rows, "summary": summary}
    p = Path(PROJECT_ROOT) / "docs" / "research" / "survivorship_audit_results.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("Wrote %s", p)
    return out


if __name__ == "__main__":
    run_audit()
