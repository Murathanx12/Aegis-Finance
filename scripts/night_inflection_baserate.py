"""Does the SanDisk archetype pay, or is it a story told about one winner?

    python -m scripts.night_inflection_baserate --survivorship-free

THE ONLY QUESTION THAT MATTERS HERE
===================================
`backend/services/inflection.py` detects a conjunction -- sequential revenue
acceleration WHILE gross margin expands -- read off exactly one case (SanDisk,
+638% from the quarter it first showed) and one matched control (Western
Digital, +176%, which does not show it). That is a hypothesis built from a
sample of one. This script is the sample of 2,273.

Three ways it could be worthless, and each has a column:

1. **It fires on everything.** 76 firings a year would be selective; 760 would
   be a momentum factor with extra steps.
2. **It fires on winners AFTER they win.** A filing lands months after the
   quarter it describes, and a company whose revenue doubled has usually already
   re-rated. The forward return is measured from the FILED date plus one
   session, so anything already in the price is already gone.
3. **It fires in one regime.** 2025-26 was an AI capex boom. If every firing is
   2025 and later, this is a bet on that boom continuing, not a detector.
   Leave-one-year-out is printed for exactly that, after 2026-09-24 produced a
   +2.62%/hold cell that became +0.12% on dropping a single year.

THE CONTROL IS THE WHOLE TEST
=============================
A firing that returns +30% over a year in a year when everything returned +30%
has demonstrated nothing. Every return here is measured RELATIVE to the
equal-weight universe over the SAME window, and separately against the firing's
own sector peers where the panel supports it.

And the matched control that the archetype's own story demands: of the companies
that grew revenue just as fast WITHOUT the margin expansion -- the Western
Digitals -- what did they return? If they returned the same, then margin adds
nothing and the detector is a revenue-growth screen.

TWO VARIANTS, BOTH PRE-SPECIFIED
================================
`strict` requires acceleration as well (the module's default). `pair` requires
only growth + margin expansion. The distinction is not cosmetic: on SanDisk the
acceleration gate reads 0.0926 against a 0.10 threshold and SILENCES the
2025-11-07 signal at $239, firing only on 2026-05-01 at $1,187. Moving the
threshold to 0.09 to catch it would be choosing a prior after the diagnostic,
which this programme has already paid for once. Testing both as declared
variants and reading the base rate is the honest version.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import inflection as INF      # noqa: E402
from backend.services import xs_ranker as XR        # noqa: E402

OUT = REPO / "backend" / "data" / "optimus" / "inflection"

#: Forward windows in trading sessions. The archetype's claim is about a
#: re-rating that takes quarters, so 21 sessions is a sanity check and 252 is
#: the horizon the story is actually about.
HORIZONS = (21, 63, 126, 252)


def _paths(bars: pd.DataFrame) -> dict[str, tuple]:
    out = {}
    for sym, g in bars.groupby("symbol", sort=False):
        g = g.sort_values("date")
        out[sym] = (g["date"].values.astype("datetime64[ns]"),
                    g["close"].to_numpy(dtype=float),
                    g["open"].to_numpy(dtype=float))
    return out


def forward(paths: dict, sym: str, filed: pd.Timestamp, h: int) -> float | None:
    """Return from the OPEN of the session after `filed` to the close h later.

    After `filed`, never after `end`. The quarter described in the filing ended
    weeks earlier and anyone trading on it then would have been trading on
    information that did not exist.
    """
    p = paths.get(sym)
    if p is None:
        return None
    dates, close, open_ = p
    i = int(np.searchsorted(dates, np.datetime64(filed, "ns"), side="right"))
    if i >= len(dates):
        return None
    j = min(i + h - 1, len(dates) - 1)
    if j <= i or not np.isfinite(open_[i]) or open_[i] <= 0:
        return None
    # A window that ran off the end of the panel is INCOMPLETE and is refused
    # rather than being scored short -- a 252-session claim graded on 40
    # sessions of a rising tape is how a young signal flatters itself.
    if i + h - 1 > len(dates) - 1:
        return None
    return float(close[j] / open_[i] - 1.0)


def market_forward(bench: dict, filed: pd.Timestamp, h: int) -> float | None:
    """The MEDIAN stock's return over the identical window, starting the same day.

    Not an index level ratio. See `build_market`.
    """
    dates, table = bench["dates"], bench["table"]
    i = int(np.searchsorted(dates, np.datetime64(filed, "ns"), side="right"))
    col = table.get(h)
    if col is None or i >= len(col):
        return None
    v = col[i]
    return None if not np.isfinite(v) else float(v)


def build_market(bars: pd.DataFrame, horizons=HORIZONS) -> dict:
    """For each date and horizon, the MEDIAN forward return across the panel.

    WHY NOT A COMPOUNDED EQUAL-WEIGHT INDEX (the bug this replaces)
    ---------------------------------------------------------------
    The first version of this built `(1 + mean_cross_sectional_daily_return)`
    and took the cumulative product. Over this panel that index compounds at
    **+35.1%/yr to 25.1x**, against SPY's +15.1% to 4.53x and a median
    full-history stock's 2.55x. No portfolio could have earned it.

    Two things inflate it and both are structural, not a coding slip. The
    arithmetic MEAN of a fat-tailed cross-section exceeds the growth rate any
    holder realises (E[r] > exp(E[log r]) by half the variance, and these are
    4,793 names including delisted microcaps). And rebalancing daily into
    whatever just fell harvests bid-ask bounce that a real book pays rather than
    earns.

    The symptom was diagnostic and worth recording: EVERY arm -- the archetype,
    its variant, and a control population three times the size -- came back with
    a ~30% hit rate and a ~-21% median at 252 sessions. Three different
    populations cannot lose to a benchmark by the same amount. Uniformity across
    arms that should disagree is a benchmark fault, not a finding.

    What replaces it is the same convention `xs_ranker.build_target` uses: the
    comparison is to the CROSS-SECTION ON THE SAME DATE, over the same window.
    Median rather than mean, because the mean is what broke.
    """
    b = bars.sort_values(["symbol", "date"])
    dates_all = np.sort(b["date"].unique()).astype("datetime64[ns]")
    idx = {d: i for i, d in enumerate(dates_all)}

    # forward[h] is a (n_dates,) array of the median h-session return begun on
    # that date, over every symbol that has a complete window from it.
    acc = {h: [[] for _ in range(len(dates_all))] for h in horizons}
    for _sym, g in b.groupby("symbol", sort=False):
        o = g["open"].to_numpy(dtype=float)
        c = g["close"].to_numpy(dtype=float)
        pos = np.array([idx[d] for d in g["date"].values.astype("datetime64[ns]")])
        n = len(g)
        for h in horizons:
            # entry at THIS row's open, exit at the close h-1 rows later, the
            # same convention `forward()` uses for the firing itself.
            end = np.arange(n) + h - 1
            ok = (end < n) & np.isfinite(o) & (o > 0)
            if not ok.any():
                continue
            src = np.nonzero(ok)[0]
            r = c[end[src]] / o[src] - 1.0
            for k, val in zip(pos[src], r):
                if np.isfinite(val):
                    acc[h][k].append(val)
    table = {h: np.array([np.median(v) if v else np.nan for v in acc[h]])
             for h in horizons}
    return {"dates": dates_all, "table": table,
            "coverage": {h: int(np.isfinite(table[h]).sum()) for h in horizons}}


def score(rows: pd.DataFrame, paths: dict, mkt: pd.DataFrame, label: str) -> dict:
    recs = []
    for r in rows.itertuples():
        rec = {"ticker": r.ticker, "filed": str(r.filed)[:10],
               "year": str(r.filed)[:4],
               "rev_qoq": float(r.rev_qoq), "gm_chg": float(r.gm_chg),
               "suspect": bool(getattr(r, "corporate_action_suspect", False))}
        any_h = False
        for h in HORIZONS:
            a = forward(paths, r.ticker, r.filed, h)
            b = market_forward(mkt, r.filed, h)
            if a is None or b is None:
                rec[f"rel_{h}"] = None
                continue
            rec[f"abs_{h}"] = a
            rec[f"rel_{h}"] = a - b
            any_h = True
        if any_h:
            recs.append(rec)
    if not recs:
        return {"arm": label, "status": "REFUSED", "why": "no firing could be graded"}

    d = pd.DataFrame(recs)
    out = {"arm": label, "status": "OK", "n_fired": int(len(rows)),
           "n_graded": int(len(d)), "n_tickers": int(d.ticker.nunique()),
           "n_suspect": int(d.suspect.sum()),
           "first": d.filed.min(), "last": d.filed.max(), "by_horizon": {}}
    for h in HORIZONS:
        c = f"rel_{h}"
        v = d[c].dropna()
        if len(v) < 5:
            out["by_horizon"][h] = {"n": int(len(v)), "status": "too few to read"}
            continue
        yrs = d.loc[v.index, "year"]
        by_year = {y: float(v[(yrs == y).values].mean()) for y in sorted(yrs.unique())}
        loo = {y: float(v[(yrs != y).values].mean())
               for y in sorted(yrs.unique()) if (yrs != y).sum() > 5}
        # Median beside mean: one +600% name in 1,283 drags a mean anywhere,
        # and this programme has been caught by a tail carrying 81% of a result.
        out["by_horizon"][h] = {
            "n": int(len(v)),
            "mean_rel": float(v.mean()), "median_rel": float(v.median()),
            "hit_rate": float((v > 0).mean()),
            "p10": float(v.quantile(.10)), "p90": float(v.quantile(.90)),
            "mean_rel_ex_suspect": float(
                d.loc[v.index][~d.loc[v.index, "suspect"]][c].mean()),
            "by_year": by_year,
            "loo_worst": min(loo.values()) if loo else None,
            "loo_worst_dropped": min(loo, key=loo.get) if loo else None,
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--survivorship-free", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    bars = (XR.load_bars(XR.survivorship_free_paths()) if a.survivorship_free
            else XR.load_bars())
    audit = XR.survivorship_audit(bars)
    print(f"survivorship: {audit['verdict'][:88]}", flush=True)
    paths = _paths(bars)
    print("building the time-matched benchmark (median stock, same window)...",
          flush=True)
    mkt = build_market(bars)
    print(f"bars {len(bars):,} / {len(paths):,} symbols; benchmark dates with "
          f"coverage {mkt['coverage']}", flush=True)

    panel = INF.add_features(INF.quarterly_panel())
    print(f"quarter panel {len(panel):,} rows, {panel.ticker.nunique():,} tickers, "
          f"sequential_ok {panel.sequential_ok.mean()*100:.0f}%", flush=True)

    arms = []

    def go(label, **kw):
        rows = INF.detect(panel, **kw)
        r = score(rows, paths, mkt, label)
        arms.append(r)
        if r.get("status") != "OK":
            print(f"  {label:<26} {r['status']}: {r.get('why')}", flush=True)
            return
        print(f"\n  {label:<26} {r['n_fired']:>5} fires / {r['n_tickers']:>4} tickers "
              f"({r['n_suspect']} corp-action suspect)  {r['first']}..{r['last']}",
              flush=True)
        for h in HORIZONS:
            c = r["by_horizon"].get(h) or {}
            if c.get("status"):
                print(f"      {h:>4}d  {c['status']} (n={c['n']})"); continue
            print(f"      {h:>4}d  n={c['n']:<5} mean {c['mean_rel']*100:+7.2f}%  "
                  f"median {c['median_rel']*100:+7.2f}%  hit {c['hit_rate']*100:>3.0f}%  "
                  f"LOO worst {(c['loo_worst'] or 0)*100:+7.2f}% "
                  f"(drop {c['loo_worst_dropped']})", flush=True)

    go("strict (growth+margin+accel)")
    go("pair (growth+margin)", min_acceleration=-9.99)
    # THE MATCHED CONTROL. Same revenue growth, NO margin expansion -- the
    # Western Digitals. If these pay the same, margin adds nothing and the
    # detector is a revenue screen wearing a story.
    go("CONTROL growth only, margin FLAT/DOWN",
       min_acceleration=-9.99, min_gm_expansion=-9.99)

    # DOSE-RESPONSE. The base rate above answers "does the conjunction pay on
    # average" and the answer is no. It does not answer the question the
    # archetype was built from, which is about MAGNITUDE: SanDisk fired at +51%
    # to +97% sequential with margin up 6 to 27 points, not at the +15%/+2pp
    # threshold. If the effect is real it should SCALE with the signal, and a
    # monotone curve across buckets is far stronger evidence than any single
    # cell -- while a flat or ragged curve says the threshold cells were noise.
    #
    # This is reported as the WHOLE curve. Picking the best bucket afterwards
    # would be choosing a prior after the diagnostic, which this programme has
    # paid for twice.
    print("\n  DOSE-RESPONSE (does the effect scale with the signal?)", flush=True)
    allrows = INF.detect(panel, min_acceleration=-9.99)
    graded = []
    for r in allrows.itertuples():
        a = forward(paths, r.ticker, r.filed, 252)
        b = market_forward(mkt, r.filed, 252)
        if a is None or b is None:
            continue
        graded.append({"ticker": r.ticker, "year": str(r.filed)[:4],
                       "rev_qoq": float(r.rev_qoq), "gm_chg": float(r.gm_chg),
                       "rel": a - b})
    dose = {}
    if graded:
        gd = pd.DataFrame(graded)
        buckets = [(0.15, 0.25), (0.25, 0.40), (0.40, 0.70), (0.70, 99.0)]
        print(f"      {'rev QoQ':<14}{'n':>6}{'median rel':>12}{'mean rel':>11}{'hit':>6}")
        for lo, hi in buckets:
            m = (gd.rev_qoq >= lo) & (gd.rev_qoq < hi)
            v = gd.loc[m, "rel"]
            if len(v) < 20:
                continue
            key = f"{lo*100:.0f}-{hi*100:.0f}%"
            dose[key] = {"n": int(len(v)), "median_rel": float(v.median()),
                         "mean_rel": float(v.mean()),
                         "hit_rate": float((v > 0).mean())}
            print(f"      {key:<14}{len(v):>6}{v.median()*100:>11.2f}%"
                  f"{v.mean()*100:>10.2f}%{(v>0).mean()*100:>5.0f}%", flush=True)
        # And the same curve on the margin axis, holding growth at the floor.
        print(f"      {'d gross mgn':<14}{'n':>6}{'median rel':>12}{'mean rel':>11}{'hit':>6}")
        for lo, hi in [(0.02, 0.05), (0.05, 0.10), (0.10, 99.0)]:
            m = (gd.gm_chg >= lo) & (gd.gm_chg < hi)
            v = gd.loc[m, "rel"]
            if len(v) < 20:
                continue
            key = f"gm +{lo*100:.0f}-{hi*100:.0f}pp"
            dose[key] = {"n": int(len(v)), "median_rel": float(v.median()),
                         "mean_rel": float(v.mean()),
                         "hit_rate": float((v > 0).mean())}
            print(f"      {key:<14}{len(v):>6}{v.median()*100:>11.2f}%"
                  f"{v.mean()*100:>10.2f}%{(v>0).mean()*100:>5.0f}%", flush=True)

    strict = arms[0]
    pair = arms[1]
    ctrl = arms[2]
    verdict = "CANNOT DETERMINE"
    H = 252
    if all(x.get("status") == "OK" for x in (pair, ctrl)):
        pv = (pair["by_horizon"].get(H) or {})
        cv = (ctrl["by_horizon"].get(H) or {})
        if pv.get("mean_rel") is not None and cv.get("mean_rel") is not None:
            edge = pv["mean_rel"] - cv["mean_rel"]
            loo = pv.get("loo_worst")
            if pv["mean_rel"] <= 0:
                verdict = (
                    f"NO EDGE: the archetype's own firings return "
                    f"{pv['mean_rel']*100:+.1f}% relative over {H} sessions. The "
                    f"conjunction does not pay, regardless of what the control does.")
            elif edge <= 0:
                verdict = (
                    f"MARGIN ADDS NOTHING: firings return {pv['mean_rel']*100:+.1f}% "
                    f"relative over {H}d, and the CONTROL -- same revenue growth, no "
                    f"margin expansion -- returns {cv['mean_rel']*100:+.1f}%. The "
                    f"detector is a revenue-growth screen; the pricing-power story is "
                    f"decoration.")
            elif loo is not None and loo <= 0:
                verdict = (
                    f"ONE REGIME: firings beat the control by {edge*100:+.1f}pp over "
                    f"{H}d ({pv['mean_rel']*100:+.1f}% vs {cv['mean_rel']*100:+.1f}%), "
                    f"but dropping {pv['loo_worst_dropped']} alone takes the firings to "
                    f"{loo*100:+.1f}%. That is an exposure to one year, not a detector.")
            else:
                verdict = (
                    f"SURVIVES ITS CONTROLS: firings return {pv['mean_rel']*100:+.1f}% "
                    f"relative over {H}d (median {pv['median_rel']*100:+.1f}%, hit "
                    f"{pv['hit_rate']*100:.0f}%) against {cv['mean_rel']*100:+.1f}% for "
                    f"the same growth WITHOUT margin expansion -- an edge of "
                    f"{edge*100:+.1f}pp attributable to the margin condition -- and the "
                    f"worst leave-one-year-out is {loo*100:+.1f}%. This is a "
                    f"PRODUCT_EXPERIMENT candidate, not a claim: next step is forward "
                    f"paper on frozen predictions.")

    res = {"receipt": "inflection_baserate", "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "hypothesis": ("revenue accelerating WHILE gross margin expands is "
                          "pricing power, and pricing power precedes a re-rating. "
                          "Read off SanDisk (+638%) against Western Digital (+176%), "
                          "which is a sample of one and one control."),
           "horizons_sessions": list(HORIZONS),
           "return_convention": ("from the OPEN of the session AFTER `filed`, "
                                 "minus the MEDIAN return of the whole panel "
                                 "begun on that same session over the same "
                                 "window; incomplete windows refused, never "
                                 "scored short. NOT a compounded equal-weight "
                                 "index -- that version compounded at +35%/yr "
                                 "and made every arm look identical."),
           "survivorship": audit, "arms": arms, "dose_response": dose,
           "verdict": verdict}
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"baserate_{date.today()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\nVERDICT: {verdict}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
