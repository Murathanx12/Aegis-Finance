"""Analyst price targets and, far more importantly, how they CHANGE.

    python -m scripts.pull_analyst_targets --universe bars --limit 3000

WHY THIS EXISTS, AND WHY IT IS NOT A PRICE-TARGET SCREEN
=========================================================
Murat, 2026-09-24: *"we need analyst price targets they matter ... and monitor
how they change"*. The second half is the whole value, and this repo has already
measured why.

`signal_registry` carries `analyst_target_upside_xs` as **CLOSED/PERVERSE**:
high implied upside was a NEGATIVE cross-sectional predictor at t -3.6 in
large/mid and -7.2 in small. Sorting a universe by "analyst says it will go up
40%" is the obvious move and it is the one that loses money -- the names with
the largest implied upside are the ones whose price fell away from a target
nobody refreshed. `opportunity_funnel` therefore records the LEVEL for sizing
and refuses to rank on it.

REVISIONS are a different object. A target moving from $250 to $268, dated, with
the analyst named, is new information arriving; the level is a stale opinion.
This module collects both and keeps them apart, because conflating them is how
the perverse result gets rediscovered.

THE POINT-IN-TIME SPLIT, WHICH IS THE ONLY THING THAT CAN GO BADLY WRONG HERE
=============================================================================
The vendor returns two very different kinds of object and they must never be
joined as if they were the same:

  BACKTESTABLE      `upgrades_downgrades` carries a real GradeDate per row --
                    firm, from-grade, to-grade, prior target, current target.
                    MRVL has 443 rows, MU has 883. That is a genuine revision
                    history and it can be used as of its own dates.

  NOT BACKTESTABLE  `analyst_price_targets`, `eps_trend`, `recommendations`,
                    `earnings_estimate`, `revenue_estimate` are SNAPSHOTS OF
                    TODAY. They have no history. `eps_trend` looks like history
                    -- it reports current vs 7/30/60/90 days ago -- but those
                    are today's estimate for a FIXED future period, restated;
                    they are not what the consensus was on those past dates for
                    the period that was then in front of it.

Every snapshot row is therefore written with `observed_at = now` and
`pit_safe = False`, and every revision row with `pit_safe = True` and its own
event date. A backtest that reads a snapshot as if it were known in the past
will report an edge that cannot be traded, which is the single most common way
analyst data produces a fake result.

WHY NOT A PAID API, AND WHY NOT SCRAPING
========================================
Measured 2026-09-24: 10/10 tickers returned complete data at **1.02 s/ticker**,
which is ~51 minutes for 3,000 names single-threaded. Free, and the dependency
is already in `requirements.txt`.

Scraping the same fields off TradingView / Investing.com / Yahoo pages would be
9,000-15,000 page loads for one pass at 3-5 links a name, 12-40 hours of
browsing, and rate-limited or blocked long before finishing. OpenClaw is better
spent on the twenty or thirty names actually under consideration, reading IR
pages and transcripts that no API carries -- which is what it did on
2026-09-24, finding that Lumentum's own 10-K attributes +173% transceiver growth
to VOLUME "partially offset by" falling ASPs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config           # noqa: E402

OUT = Path(_config.OPTIMUS_LEDGER_DIR) / "analyst"

#: Polite pacing. The vendor throttles, and a throttled run that returns half a
#: universe silently is worse than a slower one that returns all of it.
SLEEP_S = 0.15
#: Consecutive failures before the run stops and says so. A collector that
#: quietly returns 40 names out of 3,000 is the house failure mode.
MAX_CONSECUTIVE_FAILURES = 25


def universe_from_bars(limit: int | None = None) -> list[str]:
    from backend.services import xs_ranker as XR
    bars = XR.load_bars(XR.survivorship_free_paths())
    last = bars["date"].max()
    live = bars[bars["date"] >= last - pd.Timedelta(days=10)]
    liq = (live.groupby("symbol")["close"].count().index.tolist())
    syms = sorted(set(liq))
    return syms[:limit] if limit else syms


def pull_one(ticker: str) -> dict:
    """Everything the vendor has for one name, kept in its two kinds."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: dict = {"ticker": ticker, "observed_at": now,
                 "snapshot": None, "revisions": [], "eps_trend": None,
                 "errors": []}

    try:
        pt = t.analyst_price_targets
        if pt:
            cur = pt.get("current")
            mean = pt.get("mean")
            out["snapshot"] = {
                "price": _f(cur), "target_mean": _f(mean),
                "target_median": _f(pt.get("median")),
                "target_high": _f(pt.get("high")), "target_low": _f(pt.get("low")),
                # The PERVERSE field. Recorded for sizing and for research on
                # the revision signal; NEVER for ranking. See the module note.
                "implied_upside": (_f(mean) / _f(cur) - 1.0)
                if (_f(cur) and _f(mean)) else None,
                "pit_safe": False,
            }
    except Exception as exc:                                       # noqa: BLE001
        out["errors"].append(f"price_targets: {type(exc).__name__}")

    try:
        ud = t.upgrades_downgrades
        if ud is not None and len(ud):
            ud = ud.reset_index()
            datecol = "GradeDate" if "GradeDate" in ud.columns else ud.columns[0]
            for r in ud.itertuples():
                d = getattr(r, datecol, None)
                prior = _f(getattr(r, "priorPriceTarget", None))
                curr = _f(getattr(r, "currentPriceTarget", None))
                out["revisions"].append({
                    "event_date": str(pd.Timestamp(d))[:19] if d is not None else None,
                    "firm": str(getattr(r, "Firm", "") or ""),
                    "from_grade": str(getattr(r, "FromGrade", "") or ""),
                    "to_grade": str(getattr(r, "ToGrade", "") or ""),
                    "action": str(getattr(r, "Action", "") or ""),
                    "target_action": str(getattr(r, "priceTargetAction", "") or ""),
                    "prior_target": prior, "current_target": curr,
                    # A prior of 0 means "no previous target", not "target was
                    # zero". Treating it as zero would report every initiation
                    # as an infinite raise.
                    "target_change": (curr / prior - 1.0)
                    if (prior and curr and prior > 0) else None,
                    "pit_safe": True,
                })
    except Exception as exc:                                       # noqa: BLE001
        out["errors"].append(f"upgrades_downgrades: {type(exc).__name__}")

    try:
        et = t.eps_trend
        if et is not None and len(et):
            rows = {}
            for period, r in et.iterrows():
                cur = _f(r.get("current"))
                rows[str(period)] = {
                    "current": cur,
                    "d7": _delta(cur, _f(r.get("7daysAgo"))),
                    "d30": _delta(cur, _f(r.get("30daysAgo"))),
                    "d90": _delta(cur, _f(r.get("90daysAgo"))),
                }
            # NOT point-in-time: these are today's numbers for a fixed future
            # period, restated. See the module docstring.
            out["eps_trend"] = {"periods": rows, "pit_safe": False}
    except Exception as exc:                                       # noqa: BLE001
        out["errors"].append(f"eps_trend: {type(exc).__name__}")

    return out


def _f(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else f


def _delta(cur, past):
    if cur is None or past is None or past == 0:
        return None
    return cur / past - 1.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=None, help="comma-separated; overrides --universe")
    ap.add_argument("--universe", default="bars", choices=("bars",))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    syms = ([s.strip().upper() for s in a.tickers.split(",") if s.strip()]
            if a.tickers else universe_from_bars(a.limit))
    print(f"pulling analyst data for {len(syms):,} tickers "
          f"(~{len(syms)*1.02/60:.0f} min at the measured rate)", flush=True)

    snaps, revs, trends = [], [], []
    fails = 0
    consecutive = 0
    t0 = time.time()
    for i, s in enumerate(syms, 1):
        try:
            r = pull_one(s)
        except Exception as exc:                                   # noqa: BLE001
            fails += 1
            consecutive += 1
            if consecutive >= MAX_CONSECUTIVE_FAILURES:
                print(f"\nSTOPPING: {consecutive} consecutive failures "
                      f"(last {type(exc).__name__}). A collector that returns a "
                      f"fraction of the universe silently is worse than one that "
                      f"stops and says so.", flush=True)
                break
            continue
        consecutive = 0
        if r["snapshot"]:
            snaps.append({"ticker": s, "observed_at": r["observed_at"],
                          **r["snapshot"]})
        for rev in r["revisions"]:
            revs.append({"ticker": s, "pulled_at": r["observed_at"], **rev})
        if r["eps_trend"]:
            for period, v in r["eps_trend"]["periods"].items():
                trends.append({"ticker": s, "observed_at": r["observed_at"],
                               "period": period, "pit_safe": False, **v})
        if i % 200 == 0:
            el = time.time() - t0
            print(f"  {i:,}/{len(syms):,}  {el/60:.1f} min  "
                  f"{len(revs):,} revisions  {fails} failed", flush=True)
        time.sleep(SLEEP_S)

    OUT.mkdir(parents=True, exist_ok=True)
    day = str(date.today())
    written = {}
    # Snapshots APPEND. Each night's row is a new observation, and the series of
    # them is what eventually makes the level point-in-time usable -- from the
    # day collection started, never before it.
    if snaps:
        p = OUT / "target_snapshots.parquet"
        df = pd.DataFrame(snaps)
        if p.exists():
            df = pd.concat([pd.read_parquet(p), df], ignore_index=True)
            df = df.drop_duplicates(["ticker", "observed_at"], keep="last")
        df.to_parquet(p, index=False)
        written["target_snapshots"] = f"{len(df):,} rows"
    if revs:
        p = OUT / "target_revisions.parquet"
        df = pd.DataFrame(revs)
        if p.exists():
            df = pd.concat([pd.read_parquet(p), df], ignore_index=True)
            # The vendor re-serves the same historical events every pull.
            df = df.drop_duplicates(["ticker", "event_date", "firm", "to_grade"],
                                    keep="last")
        df.to_parquet(p, index=False)
        written["target_revisions"] = f"{len(df):,} rows (deduped on event)"
    if trends:
        p = OUT / "eps_trend_snapshots.parquet"
        df = pd.DataFrame(trends)
        if p.exists():
            df = pd.concat([pd.read_parquet(p), df], ignore_index=True)
            df = df.drop_duplicates(["ticker", "observed_at", "period"], keep="last")
        df.to_parquet(p, index=False)
        written["eps_trend_snapshots"] = f"{len(df):,} rows"

    res = {"receipt": "analyst_pull", "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0, "day": day,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_requested": len(syms), "n_snapshots": len(snaps),
           "n_revision_rows": len(revs), "n_failed": fails,
           "elapsed_min": round((time.time() - t0) / 60, 1),
           "files": written,
           "point_in_time": {
               "target_revisions": "PIT SAFE -- each row carries its own event_date",
               "target_snapshots": "NOT PIT before the first pull; usable from "
                                   f"{day} forward as a series",
               "eps_trend_snapshots": "NOT PIT -- today's estimate for a fixed "
                                      "future period, restated; the 7/30/90-day "
                                      "columns are NOT what consensus was then",
           },
           "standing_warning": (
               "signal_registry carries analyst_target_upside_xs as "
               "CLOSED/PERVERSE: t -3.6 large/mid, -7.2 small. Do not rank on "
               "the LEVEL. The revision series is the thing being collected.")}
    p = OUT / f"analyst_pull_{day}.json"
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\n{len(snaps):,} snapshots, {len(revs):,} revision rows, "
          f"{fails} failed, {res['elapsed_min']} min")
    for k, v in written.items():
        print(f"  {k}: {v}")
    print(f"-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
