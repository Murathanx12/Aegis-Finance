"""LANE-AUTOPSY-1++ — run the mirror/conviction decomposition on real prices.

    python -m scripts.lane_autopsy_run                    # since inception
    python -m scripts.lane_autopsy_run --end 2026-08-15

Writes `docs/conviction_replay/lane_autopsy_1pp.json` and prints the table.

DESCRIPTIVE ONLY. Nothing here seeds a lane, flips a flag, writes a `paper_nav`
row or licenses a change to either lane. Order 17: the 2027 decision date gates
the verdict, not the diagnosis.

THE RECONCILIATION THIS DOES NOT DO
====================================
The replayed NAV is a RECONSTRUCTION from adjusted closes, not the lane's
recorded `paper_nav`. Those live in production and are the authority. Where the
replay's total return disagrees with the recorded one, the recorded one is
right and the replay has a bug — so the script prints its own reconstruction
loudly as a reconstruction, and reconciling it against production is an
attended item under `lane-integrity-check`, not something a script should do
unsupervised.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import lane_autopsy as LA        # noqa: E402

OUT = REPO / "docs" / "conviction_replay" / "lane_autopsy_1pp.json"
INCEPTION = "2026-06-08"


def _load_book() -> dict:
    import yaml
    d = yaml.safe_load((REPO / "backend" / "data" / "book_lanes.yaml")
                       .read_text(encoding="utf-8"))
    return d


def _fetch(tickers: list[str], start: str, end: str):
    import pandas as pd
    import yfinance as yf
    df = yf.download(tickers, start=start, end=end, auto_adjust=True,
                     progress=False, group_by="column")
    if isinstance(df.columns, pd.MultiIndex):
        df = df["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(tickers[0])
    return df.dropna(how="all")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lane_autopsy_run")
    ap.add_argument("--start", default=INCEPTION)
    ap.add_argument("--end", default=str(date.today()))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    book = _load_book()
    shares = {k: float(v) for k, v in book["holdings"].items()}

    print("=" * 78)
    print("LANE-AUTOPSY-1++ — the mirror/conviction gap, one difference at a time")
    print("=" * 78)
    print(f"window     {a.start} -> {a.end}   (inception {INCEPTION})")
    print(f"holdings   {len(shares)} names")
    print("DESCRIPTIVE. No lane is seeded, no flag flipped, nothing annualised.")
    print()

    px = _fetch(sorted(shares), a.start, a.end)
    have = [t for t in shares if t in px.columns and px[t].notna().any()]
    missing = sorted(set(shares) - set(have))
    if missing:
        # NAMED, never dropped silently: a name that vanishes lets the others
        # re-normalise, which reads as a return.
        print(f"NO PRICES for {missing} — these are excluded and the replay "
              f"below is over {len(have)} of {len(shares)} names. That is a "
              f"DIFFERENT book, and the difference is stated rather than "
              f"absorbed.")
    shares = {t: shares[t] for t in have}
    px = px[have].ffill().dropna(how="any")
    print(f"price rows {len(px)}   first {px.index[0].date()}  "
          f"last {px.index[-1].date()}")

    try:
        out = LA.decompose(px, shares)
    except LA.ReplayRefused as e:
        print(f"\nREFUSED: {e}")
        return 2

    b, t = out["base"], out["target"]
    print(f"\n  conviction   total return {b['total_return']:+8.2%}   "
          f"rebalances {b['n_rebalances']:2d}  turnover {b['turnover_total']:.3f}")
    print(f"  mirror       total return {t['total_return']:+8.2%}   "
          f"rebalances {t['n_rebalances']:2d}  turnover {t['turnover_total']:.3f}")
    print(f"  GAP          {out['gap_total']:+8.2%}   "
          f"(mirror minus conviction)")
    if t["hrp_fallback"]:
        print(f"  *** {t['hrp_fallback']} — the mirror lane's HRP history gate "
              f"(252 obs) cannot pass on this window, so every rebalance ran "
              f"the lane's own loud fallback to equal weight. This replays what "
              f"the lane DOES, not what its label says.")

    print(f"\n  {'mechanism':16s} {'marginal':>10s} {'leave-1-out':>12s} "
          f"{'interaction':>12s}  separable")
    print("  " + "-" * 62)
    for r in out["mechanisms"]:
        tag = "  <- INERT" if r.get("inert") else ""
        print(f"  {r['mechanism']:16s} {r['marginal_effect']:+10.2%} "
              f"{r['leave_one_out_effect']:+12.2%} {r['interaction']:+12.2%}"
              f"  {'yes' if r['separable'] else 'NO'}{tag}")
    print("  " + "-" * 62)
    print(f"  {'sum of marginals':16s} {out['sum_of_marginals']:+10.2%}")
    print(f"  {'residual':16s} {out['residual']:+10.2%}"
          f"   ({out['residual_share_of_gap']} of the gap)"
          if out["residual_share_of_gap"] is not None else "")
    if out["additive"]:
        print("\n  additive? yes")
    else:
        print("\n  additive? NO — the mechanisms interact, and no single "
              "per-mechanism attribution exists")
    for r in out["mechanisms"]:
        if r.get("inert"):
            print(f"  INERT: `{r['mechanism']}` {r['inert_note']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "trial": "LANE-AUTOPSY-1++",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"start": a.start, "end": a.end, "inception": INCEPTION,
                   "n_price_rows": len(px)},
        "names_used": have, "names_missing": missing,
        "basis": "RECONSTRUCTION from adjusted closes, NOT the recorded "
                 "paper_nav; production is the authority and reconciling "
                 "against it is an attended lane-integrity item",
        "result": out,
    }
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
