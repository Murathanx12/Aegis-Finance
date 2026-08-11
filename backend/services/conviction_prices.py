"""Prices for the conviction replay, with the corporate actions that would
otherwise delete the answer.

THE FAILURE THIS MODULE EXISTS TO PREVENT
=========================================

Two of the 61 names on Murat's sheets stopped trading during the replay window,
and a plain price download returns nothing for either:

* **APLT** — Applied Therapeutics, in his PORTFOLIO, bought around $0.80 and
  taken out at **$0.088 cash** per share on 2026-02-03. A ~89% loss.
* **SLNO** — Soleno Therapeutics, on his WATCHLIST, taken out by Neurocrine at
  **$53.00 cash** per share on 2026-05-18, from a sheet price of $43.

Drop the missing ones and his selection looks better than it was *and* the pool
he is measured against looks worse than it was. The two errors do not cancel;
they compound, both in the direction that flatters the answer this session
exists to test. This is the house failure mode — a missing feed silently
changing a verdict — so the actions are recorded here with their sources and
asserted present at load time.

TREATMENT AFTER TERMINATION
---------------------------
Cash proceeds sit in cash and earn nothing. That is the assumption-free choice:
any reinvestment rule is a decision the replay is supposed to be measuring, not
one it should smuggle in. `reinvest_in` re-runs the whole comparison with the
proceeds rolled into a benchmark instead, and the two must agree in sign — if
they do not, the finding belongs to the cash treatment and not to the data.

CVRs are marked at ZERO. APLT holders received one non-tradeable contingent
value right per share; a non-tradeable claim has no observable price, and
marking it at anything else would be inventing the number that decides whether
his worst position was a total loss.

DATA SOURCE
-----------
yfinance, split/dividend adjusted. Under the PIT hierarchy yfinance is FORBIDDEN
for money claims. Nothing here makes one: this is a descriptive replay of a
record that already happened, over 2025-2026 dates no research-grade source in
this programme covers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parents[1] / "data" / "conviction_prices.csv"

#: Benchmarks the replay is measured against.
BENCHMARKS = ("SPY", "QQQ", "IWM", "XBI", "SMH")


@dataclass(frozen=True)
class CorporateAction:
    """A name that stopped trading, and what a holder actually received."""
    ticker: str
    effective: str
    cash_per_share: float
    kind: str
    source: str
    note: str = ""


#: Verified against primary reporting. Both are cash takeouts, so the holder's
#: terminal value is known exactly rather than estimated.
CORPORATE_ACTIONS: dict[str, CorporateAction] = {
    "APLT": CorporateAction(
        ticker="APLT", effective="2026-02-03", cash_per_share=0.088,
        kind="merger_cash_and_cvr",
        source="Cycle Group Holdings tender offer; Nasdaq delisting 2026-02-03",
        note=("plus one NON-TRADEABLE CVR per share, marked at zero — a "
              "non-tradeable claim has no observable price and inventing one "
              "would decide, by assumption, whether his worst position was a "
              "total loss")),
    "SLNO": CorporateAction(
        ticker="SLNO", effective="2026-05-18", cash_per_share=53.00,
        kind="merger_cash",
        source="Neurocrine Biosciences acquisition, $2.9bn, completed 2026-05-18",
        note="88.9% of shares tendered; watchlist name, not a holding"),
}


#: Entry prices for names that no free feed carries AT ALL after delisting —
#: not one pre-delisting bar survives for either. Without an entry price a
#: terminated name still has no computable return, so carrying it at its payout
#: is not enough: the first version of this module did exactly that, logged
#: "EXCLUDED", and dropped APLT out of his portfolio anyway. That silently
#: raised his picks by about ten points, because APLT is his worst position.
#:
#: These two entries come from HIS OWN SHEET rather than from a market feed.
#: That is a WEAKER source than every other name uses, and the replay reports
#: the result both ways so the difference is visible rather than assumed away.
SHEET_ENTRY_FALLBACK: dict[str, dict] = {
    "APLT": {"date": "2025-11-07", "price": 0.80,
             "why": "no surviving bars; entry from his 2025-11-07 sheet"},
    "SLNO": {"date": "2025-11-07", "price": 43.00,
             "why": "no surviving bars; entry from his 2025-11-07 sheet"},
}


def synthetic_names() -> set[str]:
    """Names whose series is reconstructed, not observed.

    They support total return and nothing else: there is no path between the
    two known points, so MFE/MAE and any daily statistic would be inventing the
    shape of a move rather than measuring it.
    """
    return set(SHEET_ENTRY_FALLBACK)


def load_prices(path: Path | None = None) -> pd.DataFrame:
    """Adjusted closes, wide, with terminated names carried at their payout.

    A terminated name's column is filled forward at its cash-per-share from the
    effective date onward, so that every downstream calculation sees a position
    that ENDED at a known value rather than a position that vanished.
    """
    path = path or CACHE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing — run scripts/fetch_conviction_prices.py. The "
            f"replay must not silently proceed on whatever happens to be cached")
    df = pd.read_csv(path, index_col=0, parse_dates=True).sort_index()

    for tkr, act in CORPORATE_ACTIONS.items():
        eff = pd.Timestamp(act.effective)
        if tkr not in df.columns:
            df[tkr] = pd.NA
        col = pd.to_numeric(df[tkr], errors="coerce")
        traded = int(col.notna().sum())
        if traded == 0 and tkr in SHEET_ENTRY_FALLBACK:
            fb = SHEET_ENTRY_FALLBACK[tkr]
            stamp = df.index[df.index >= pd.Timestamp(fb["date"])]
            if len(stamp) == 0:
                raise ValueError(f"{tkr}: fallback date {fb['date']} is outside "
                                 f"the panel; the entry price cannot be placed")
            col.loc[stamp[0]] = fb["price"]
            logger.warning("%s: no surviving bars — entry %.3f taken from HIS "
                           "SHEET at %s (%s). Weaker source than every other "
                           "name; the replay reports both with and without it.",
                           tkr, fb["price"], fb["date"], fb["why"])
        col.loc[df.index >= eff] = act.cash_per_share
        df[tkr] = col
        logger.info("corporate action %s: %d traded bars, then %.3f cash from "
                    "%s (%s)", tkr, traded, act.cash_per_share, act.effective,
                    act.kind)

    missing = [c for c in df.columns if df[c].notna().sum() == 0]
    if missing:
        raise ValueError(
            f"no usable price for {missing}. Every name on the sheets must "
            f"resolve to either a price series or a recorded corporate action; "
            f"a name that resolves to neither would be dropped from one side of "
            f"the comparison and change the verdict invisibly")

    # A corporate action must leave a name with a computable return, not merely
    # a non-empty column. Carrying the payout while the entry price is still
    # missing is what let APLT out of the portfolio on the first pass, so the
    # invariant is asserted on what the replay actually needs.
    for tkr in CORPORATE_ACTIONS:
        s = pd.to_numeric(df[tkr], errors="coerce").dropna()
        if len(s) < 2:
            raise ValueError(
                f"{tkr} resolves to {len(s)} usable price(s): a terminated name "
                f"needs BOTH an entry and a payout or it is dropped from one "
                f"side of the comparison exactly as if it had never existed")
    return df


def price_on(df: pd.DataFrame, ticker: str, when: str | date) -> float | None:
    """Last close at or before `when`. None if the name had not started trading."""
    if ticker not in df.columns:
        return None
    s = df[ticker].loc[:pd.Timestamp(when)].dropna()
    return float(s.iloc[-1]) if len(s) else None


def total_return(df: pd.DataFrame, ticker: str, start: str,
                 end: str) -> float | None:
    """Simple total return between two dates, terminations included."""
    p0, p1 = price_on(df, ticker, start), price_on(df, ticker, end)
    if p0 is None or p1 is None or p0 <= 0:
        return None
    return p1 / p0 - 1.0


def path_stats(df: pd.DataFrame, ticker: str, start: str,
               end: str) -> dict | None:
    """Maximum favourable and adverse excursion over the window.

    MFE is the best the position ever looked; MAE the worst. `capture` is the
    fraction of the best available move that the buy-and-hold outcome kept — the
    number that turns "I sold too early" from a feeling into a measurement.
    """
    if ticker not in df.columns or ticker in SHEET_ENTRY_FALLBACK:
        # A reconstructed series has two known points and no path between them.
        # An MFE read off that line would be the shape of an assumption.
        return None
    s = df[ticker].loc[pd.Timestamp(start):pd.Timestamp(end)].dropna()
    if len(s) < 20:
        return None
    p0 = float(s.iloc[0])
    if p0 <= 0:
        return None
    rel = s / p0 - 1.0
    mfe, mae = float(rel.max()), float(rel.min())
    final = float(rel.iloc[-1])
    return {
        "start_price": p0, "end_price": float(s.iloc[-1]),
        "total_return": final, "mfe": mfe, "mae": mae,
        "mfe_date": str(rel.idxmax().date()), "mae_date": str(rel.idxmin().date()),
        "capture_of_best": (final / mfe) if mfe > 0 else None,
        "n_bars": len(s),
    }
