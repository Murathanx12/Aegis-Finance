"""Conviction lane: does the PROD DECISION LOG explain the NAV divergence?

The cross-arm replay (Order 20 §5) found the authoritative conviction NAV
diverges from YAML-seed buy-and-hold in discrete jumps (06-24, 07-14,
07-30) and refused all live-lane economics until the book was read. The
attended positions read stays attended — but the prod DECISION LOG is
exposed read-only (`/api/pi/conviction/decisions`, pulled 2026-08-19 into
`docs/conviction_replay/prod_reads_2026-08-19/`), and it contains twelve
retro-entries all logged 2026-07-11 05:52–05:57 ("stocks I bought months
ago", four flagged late_entry).

HYPOTHESIS TESTED HERE (mechanism attribution, not lane economics): from
the re-book onward the lane IS this 12-name book, so the reconstructed
book's daily returns should track the authoritative NAV's daily returns
tightly after 07-14, leaving 06-24 as the only unexplained jump.

Cash is declared UNRECOVERABLE by the book endpoint, so the comparison is
RETURNS with a fitted scale (an equity-only reconstruction against a lane
holding cash shows beta < 1), never levels. Output: a dated receipt under
docs/conviction_replay/. This script asserts nothing about skill and does
not touch prod.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

READS = REPO / "docs" / "conviction_replay" / "prod_reads_2026-08-19"
OUT = REPO / "docs" / "conviction_replay"
PRICES_CACHE = READS / "decision_book_prices.json"


def load_decisions() -> pd.DataFrame:
    d = json.load(open(READS / "conviction_decisions.json",
                       encoding="utf-8"))["decisions"]
    df = pd.DataFrame(d)
    if df.empty:
        raise SystemExit("decision log empty — nothing to reconstruct")
    df["ts"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("ts")


def load_authoritative_nav() -> pd.Series:
    snap = json.load(open(OUT / "track_record_snapshot_2026-08-18.json",
                          encoding="utf-8"))
    rows = snap["lanes"]["conviction"]
    s = pd.Series({r["date"]: r["value"] for r in rows}, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def fetch_prices(tickers: list[str], start: str) -> pd.DataFrame:
    if PRICES_CACHE.exists():
        raw = json.load(open(PRICES_CACHE, encoding="utf-8"))
        return pd.DataFrame(raw["close"]).set_index(
            pd.to_datetime(raw["dates"]))
    import yfinance as yf
    px = yf.download(tickers, start=start, end="2026-08-19",
                     auto_adjust=True, progress=False)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame(tickers[0])
    PRICES_CACHE.write_text(json.dumps(
        {"dates": [d.date().isoformat() for d in px.index],
         "close": {c: [None if pd.isna(v) else round(float(v), 6)
                       for v in px[c]] for c in px.columns},
         "pulled_at": date.today().isoformat(),
         "source": "yfinance auto_adjust close"}), encoding="utf-8")
    return px


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    dec = load_decisions()
    nav = load_authoritative_nav()
    book = dec.groupby("ticker")["shares_delta"].sum()
    tickers = sorted(book.index)
    print(f"decision book: {len(tickers)} names, all entered "
          f"{dec['ts'].min():%Y-%m-%d %H:%M}..{dec['ts'].max():%H:%M}")

    px = fetch_prices(tickers, start="2026-06-01")
    missing = [t for t in tickers if t not in px.columns
               or px[t].dropna().empty]
    if missing:
        print(f"NOTE: no prices for {missing} — excluded and counted")
    live = [t for t in tickers if t not in missing]
    equity = (px[live] * book[live]).sum(axis=1)
    equity = equity[equity.index >= "2026-07-11"]

    # daily returns, aligned on shared dates
    nav_r = nav.pct_change().dropna()
    eq_r = equity.pct_change().dropna()
    joined = pd.concat([nav_r.rename("nav"), eq_r.rename("book")],
                       axis=1, join="inner").dropna()
    seg = joined[joined.index >= "2026-07-15"]      # post re-book settling

    corr = float(seg["nav"].corr(seg["book"]))
    beta = float(np.polyfit(seg["book"], seg["nav"], 1)[0]) if len(seg) > 2 \
        else float("nan")
    te = float((seg["nav"] - beta * seg["book"]).std() * np.sqrt(252))

    # jump attribution: authoritative NAV daily moves > 4% while the
    # reconstructed book moved < 1% the same day = a RE-BOOK artifact
    jumps = []
    for d, row in joined.iterrows():
        if abs(row["nav"]) > 0.04 and abs(row["book"]) < 0.01:
            jumps.append({"date": d.date().isoformat(),
                          "nav_move": round(row["nav"], 4),
                          "book_move": round(row["book"], 4),
                          "reading": "NAV moved without the book — "
                                     "accounting event, not the market"})

    verdict = {
        "post_rebook_daily_corr": round(corr, 4),
        "post_rebook_beta_nav_on_book": round(beta, 4),
        "tracking_error_ann": round(te, 4),
        "n_shared_days_post_0715": int(len(seg)),
        "explained": bool(corr > 0.9),
    }
    print(f"\npost-07-15 daily correlation nav~book: {corr:.4f}  "
          f"beta {beta:.3f}  TE {te:.2%}  (n={len(seg)})")
    for j in jumps:
        print(f"  JUMP {j['date']}: nav {j['nav_move']:+.2%} vs book "
              f"{j['book_move']:+.2%} — {j['reading']}")

    receipt = {
        "script": "conviction_decision_reconstruction",
        "generated_on": date.today().isoformat(),
        "decision_log": {"n": int(len(dec)),
                         "all_entered": "2026-07-11T05:52..05:57",
                         "late_entry_flags": int(dec["late_entry"].sum())},
        "book": {t: float(book[t]) for t in tickers},
        "excluded_no_prices": missing,
        "comparison_basis": ("RETURNS with fitted scale — cash declared "
                             "UNRECOVERABLE, so levels are not comparable"),
        "verdict": verdict,
        "nav_jumps_without_book_moves": jumps,
        "scope": ("mechanism attribution for the conviction lane's NAV path "
                  "ONLY; no economics, no skill claim, mirror lane still "
                  "needs its rebalance_events (attended or the branch's "
                  "read-only endpoint after merge)"),
    }
    p = OUT / "decision_reconstruction_2026-08-19.json"
    p.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"\nreceipt: {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
