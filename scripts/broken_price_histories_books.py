"""Which frozen books hold a name whose signal rested on a broken price history? (2026-09-29)

    python -m scripts.broken_price_histories_books

READ-ONLY on `llm_portfolio/books.jsonl`, the bar files and the trial receipt.
For every position of every frozen book, at the book's `asof`, the 12-1
momentum (close 21 sessions ago / close 252 sessions ago - 1) and the 63-session
annualised volatility are computed twice from the same bar files:

  OFF  the reader before 2026-09-29's screen (stitch cut only)
  ON   the reader now (stitch cut + `bar_defects.screen`)

A position is SELECTED_ON_BROKEN_ROW when the screen changes what the name
looked like at the decision: its 12-1 momentum is finite OFF and NaN ON (the
history was cut inside the window), or |ln(1+mom_ON) - ln(1+mom_OFF)| >
`MOM_TOL`, or vol_63 changes by more than `VOL_TOL`x either way. A position
whose name has a SUSPECT (kept, unproven) level break in its window is listed
apart. No book, twin, weight or id is changed; the receipt is new
(`bar_defects/books_<run_id>.json`).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                             # noqa: E402
from backend.services import bar_defects as BD                 # noqa: E402
from backend.services import stitched_tickers as ST            # noqa: E402
from backend.services import xs_ranker as XR                   # noqa: E402

MOM_TOL = 0.10
VOL_TOL = 1.5
TRIAL_RECEIPT = "lib_forward_trial_2026-09-28T062024Z.json"


def load_raw() -> pd.DataFrame:
    cols = ["symbol", "date", "open", "high", "low", "close", "volume"]
    frames = [ST.tag_source(pd.read_parquet(p, columns=cols), Path(p).stem)
              for p in XR.survivorship_free_paths()]
    raw = pd.concat(frames, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["date"])
    return raw.drop_duplicates(subset=["symbol", "date"], keep="first")


def features(bars: pd.DataFrame, cal: pd.DatetimeIndex, tickers: set, asofs: list) -> dict:
    """{(ticker, asof): (mom_252_21, vol_63)} on the market calendar, ffilled closes."""
    b = bars[bars["symbol"].isin(tickers)]
    C = b.pivot_table(index="date", columns="symbol", values="close").reindex(cal)
    Cff = C.ffill()
    R = Cff.pct_change(fill_method=None).where(C.notna())
    out = {}
    for a in asofs:
        i = int(cal.searchsorted(pd.Timestamp(a), side="right")) - 1
        if i < 252:
            continue
        mom = Cff.iloc[i - 21] / Cff.iloc[i - 252] - 1.0
        w = R.iloc[i - 62: i + 1]
        vol = w.std(ddof=1) * math.sqrt(252)
        vol = vol.where(w.notna().sum() >= 40)
        for t in C.columns:
            out[(t, a)] = (float(mom.get(t, np.nan)), float(vol.get(t, np.nan)))
    return out


def main(argv=None) -> int:        # pragma: no cover - reads the real panel
    opt = Path(_cfg.OPTIMUS_LEDGER_DIR)
    books = [json.loads(x) for x in (opt / "llm_portfolio" / "books.jsonl").read_text(encoding="utf-8").splitlines()
             if x.strip()]
    pos = []
    for b in books:
        a = str(b.get("asof") or "")[:10]
        for p in b.get("positions") or []:
            if isinstance(p, dict) and (p.get("ticker") or p.get("symbol")):
                pos.append({"book_id": b.get("book_id"), "name": b.get("name"), "kind": b.get("kind"),
                            "asof": a, "ticker": str(p.get("ticker") or p.get("symbol")),
                            "weight": float(p.get("weight") or 0.0)})
    P = pd.DataFrame(pos)
    P = P[P["asof"].str.len() == 10]
    tickers = set(P["ticker"])
    asofs = sorted(P["asof"].unique())
    raw = load_raw()
    cal = pd.DatetimeIndex(np.sort(raw.loc[raw["symbol"] == "SPY", "date"].unique()))
    BD.ENABLED = False
    off = ST.cut_reader_bars(raw.copy())
    BD.ENABLED = True
    on = ST.cut_reader_bars(raw.copy())
    screen = dict((ST.LAST_AUDIT or {}).get("defect_screen") or {})
    f_off = features(off, cal, tickers, asofs)
    f_on = features(on, cal, tickers, asofs)
    sus = pd.DataFrame(screen.get("suspects") or [])
    rows = []
    for r in P.itertuples(index=False):
        mo, vo = f_off.get((r.ticker, r.asof), (np.nan, np.nan))
        mn, vn = f_on.get((r.ticker, r.asof), (np.nan, np.nan))
        why = []
        if np.isfinite(mo) and not np.isfinite(mn):
            why.append("history_cut_inside_12_1_window")
        elif np.isfinite(mo) and np.isfinite(mn) and abs(math.log1p(mn) - math.log1p(mo)) > MOM_TOL:
            why.append("mom_12_1_changed")
        if np.isfinite(vo) and np.isfinite(vn) and vo > 0 and vn > 0 and max(vo / vn, vn / vo) > VOL_TOL:
            why.append("vol_63_changed")
        suspect = False
        if len(sus):
            s = sus[sus["symbol"] == r.ticker]
            if len(s):
                d = pd.to_datetime(s["date"])
                a = pd.Timestamp(r.asof)
                suspect = bool(((d > a - pd.Timedelta(days=366)) & (d <= a)).any())
        rows.append({**r._asdict(), "mom_off": mo, "mom_on": mn, "vol_off": vo, "vol_on": vn,
                     "selected_on_broken_row": bool(why), "why": why, "suspect_in_window": suspect})
    R_ = pd.DataFrame(rows)
    hit = R_[R_["selected_on_broken_row"] | R_["suspect_in_window"]]
    by_book = []
    for bid, g in hit.groupby("book_id"):
        by_book.append({"book_id": bid, "name": g["name"].iloc[0], "kind": g["kind"].iloc[0],
                        "asof": g["asof"].iloc[0],
                        "weight_selected_on_broken_row": round(float(g.loc[g["selected_on_broken_row"], "weight"].sum()), 5),
                        "positions": g[["ticker", "weight", "why", "suspect_in_window", "mom_off", "mom_on",
                                        "vol_off", "vol_on"]].round(4).to_dict("records")})
    by_book.sort(key=lambda x: -x["weight_selected_on_broken_row"])
    # the trial's 30 pairs
    trial = json.loads((opt / "trials" / TRIAL_RECEIPT).read_text(encoding="utf-8"))
    hit_ids = {b["book_id"] for b in by_book if b["weight_selected_on_broken_row"] > 0}
    pairs = []
    for p in trial.get("pairs") or []:
        pb, tb = p["book_id"] in hit_ids, p["twin_book_id"] in hit_ids
        if pb or tb:
            wb = next((b["weight_selected_on_broken_row"] for b in by_book if b["book_id"] == p["book_id"]), 0.0)
            wt = next((b["weight_selected_on_broken_row"] for b in by_book if b["book_id"] == p["twin_book_id"]), 0.0)
            pairs.append({"book": p["name"], "book_id": p["book_id"], "twin_book_id": p["twin_book_id"],
                          "twin_type": p.get("twin_type"), "book_side": pb, "twin_side": tb,
                          "book_weight": wb, "twin_weight": wt})
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    outp = opt / BD.RECEIPT_SUBDIR / f"books_{run_id}.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema": "bar_defects/books/1", "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "llm_spend_usd": 0.0,
           "read_only": "books.jsonl, the bar files and the trial receipt were read, never written",
           "tolerances": {"mom_log_abs": MOM_TOL, "vol_ratio": VOL_TOL},
           "n_books": len(books), "n_positions": int(len(P)),
           "n_positions_selected_on_broken_row": int(R_["selected_on_broken_row"].sum()),
           "n_books_with_one": len({b["book_id"] for b in by_book if b["weight_selected_on_broken_row"] > 0}),
           "tickers_selected_on_broken_row": sorted(set(R_.loc[R_["selected_on_broken_row"], "ticker"])),
           "n_positions_suspect_only": int((R_["suspect_in_window"] & ~R_["selected_on_broken_row"]).sum()),
           "trial": {"receipt": TRIAL_RECEIPT, "n_pairs": len(trial.get("pairs") or []),
                     "pairs_affected": pairs},
           "books": by_book, "screen": BD.summary(screen)}
    tmp = outp.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    tmp.replace(outp)
    print(json.dumps({k: doc[k] for k in ("n_books", "n_positions", "n_positions_selected_on_broken_row",
                                          "n_books_with_one", "tickers_selected_on_broken_row",
                                          "n_positions_suspect_only")}, default=str))
    print(f"trial pairs affected: {len(pairs)} of {doc['trial']['n_pairs']}")
    for p in pairs:
        print("  ", p)
    for b in by_book[:40]:
        print(f"  {b['weight_selected_on_broken_row']:.3f} {b['name']} "
              f"{[(x['ticker'], x['weight'], x['why']) for x in b['positions']][:6]}")
    print(f"-> {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
