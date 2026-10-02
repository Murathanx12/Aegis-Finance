"""Insider cluster buys as a DAILY event study, entered the session after the public date (2026-09-30).

    python -m scripts.hyp_insider_events --part declare --tag <T>
    python -m scripts.hyp_insider_events --part run     --tag <T>

Why this is not a repeat: the 20 monthly insider rules on CRSP (EVT runs, 2026-09-29) and C02
entered at the NEXT MONTH-END, up to a month after the filing. The documented insider-buy
drift is front-loaded, so the question the monthly engine could not ask is: entered at the
OPEN of the first session after the Form 4 is public, net of a round-trip spread, does a
cluster (>= 3 distinct officer/director open-market buyers inside 30 days) beat the market
and a same-band equal-weight benchmark over 5 and 21 sessions?

Tonight's live table (`official/tables/insider_tx.jsonl`) holds 7 days: no power. The
history is `sec_insider/insider_events_v1.parquet` (Form 4 bulk, 2006q1-2026q2, observed
date = the filing date, end of day New York). CRSP daily ends 2024.

Licence `PRODUCT_EXPERIMENT`. $0, no LLM, no network.
"""
from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.hyp_investable import CR_OUT, OUT, WRDS, _mem_ok, _now, _sha, _write, say  # noqa: E402

PRIOR_SEARCH = 42_693            # 42,666 + 19 investable + 8 vol-managed
INS = REPO / "backend" / "data" / "optimus" / "sec_insider" / "insider_events_v1.parquet"
PANEL_RUN = "2026-09-29T075640Z"
CS_RUN = "FU_2026-09-29T0855Z"
MIN_BUYERS, WINDOW_DAYS, REFRACTORY_DAYS = 3, 30, 90
HORIZONS = (5, 21)
SPLITS = {"design": ("2006-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
          "late": ("2017-01-01", "2024-12-31")}
DECISION = ("A cell (horizon x benchmark) SURVIVES iff the monthly mean (events grouped by entry month) of "
            "net abnormal return is > 0 in design (entries 2006-2008) AND > 0 in validate (2009-2016) with t >= 2 on "
            "3-month blocks AND a strict majority of validate years > 0. Net = stock return from the entry-session "
            "OPEN to the close H-1 sessions later, minus the benchmark over the same sessions (market: FF mkt+rf "
            "close-to-close incl. the entry day; band: equal-weight CRSP common stocks of the name's size band), minus "
            "a round trip of max(Corwin-Schultz, flat band). 2017-2024 is read last.")


def clusters(B: pd.DataFrame) -> pd.DataFrame:
    """Rows (permno, public_date, n_buyers): the first public date on which >= MIN_BUYERS distinct
    officer/director buyers have filed inside WINDOW_DAYS; then none for REFRACTORY_DAYS."""
    out = []
    for p, g in B.sort_values("pub").groupby("permno", sort=False):
        pub = g["pub"].to_numpy(dtype="datetime64[ns]")
        cik = g["insider_cik"].to_numpy()
        last = None
        lo = 0
        for i in range(len(g)):
            while pub[lo] < pub[i] - np.timedelta64(WINDOW_DAYS, "D"):
                lo += 1
            if last is not None and pub[i] < last + np.timedelta64(REFRACTORY_DAYS, "D"):
                continue
            n = len(set(cik[lo:i + 1]))
            if n >= MIN_BUYERS and (i + 1 == len(g) or pub[i + 1] != pub[i]):
                out.append((p, pd.Timestamp(pub[i]), n))
                last = pub[i]
    return pd.DataFrame(out, columns=["permno", "pub", "n_buyers"])


def part_declare(tag: str) -> int:
    p = OUT / f"insider_events_DECLARATION_{tag}.json"
    if p.exists():
        say(f"REFUSED: {p.name} exists")
        return 2
    body = {"schema": "hyp_lab/insider_events_declaration/1", "licence": "PRODUCT_EXPERIMENT",
            "written_before_any_return_was_read": True,
            "event": (f">= {MIN_BUYERS} distinct insider CIKs (officer or director), event_type insider_open_market_buy, "
                      f"filed inside {WINDOW_DAYS} calendar days; the event is the public date completing the "
                      f"cluster; one event per permno per {REFRACTORY_DAYS} days"),
            "entry": "OPEN of the first CRSP session strictly after the public (filing) date",
            "horizons": HORIZONS, "benchmarks": ["market", "band_ew"], "splits": SPLITS, "decision": DECISION,
            "power_note": "tonight's live insider_tx table (7 days) is not used; history 2006-2024 is",
            "search_count": {"prior": PRIOR_SEARCH, "cells": 4, "after": PRIOR_SEARCH + 4}}
    body["sha16"] = _sha(body)
    body["written_utc"] = _now()
    _write(p, body)
    say(f"-> {p.name} sha {body['sha16']}")
    return 0


def part_run(tag: str) -> int:
    from backend.services import hyp_investable as HI                # noqa: PLC0415
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    from backend.services import xs_ranker as XR                     # noqa: PLC0415
    d = json.loads((OUT / f"insider_events_DECLARATION_{tag}.json").read_text(encoding="utf-8"))
    if _sha({k: v for k, v in d.items() if k not in ("sha16", "written_utc")}) != d["sha16"]:
        say("REFUSED: declaration hash mismatch")
        return 2
    rp = OUT / f"insider_events_RESULTS_{tag}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists")
        return 2
    t0 = time.time()
    B = pd.read_parquet(INS, columns=["permno", "event_type", "observed_at_utc", "insider_cik", "insider_is_officer",
                                      "insider_is_director", "insider_plan_10b5_1"],
                        filters=[("event_type", "=", "insider_open_market_buy")])
    B = B.dropna(subset=["permno", "observed_at_utc", "insider_cik"])
    B = B[(B["insider_is_officer"] | B["insider_is_director"]) & (B["insider_plan_10b5_1"] != "YES")]
    B["permno"] = B["permno"].astype("int64")
    B["pub"] = B["observed_at_utc"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    E = clusters(B[["permno", "pub", "insider_cik"]])
    del B
    gc.collect()
    say(f"  {len(E):,} cluster events {time.time()-t0:.0f}s")
    # size band and spread at the last month-end before the event
    K = pd.read_parquet(CR_OUT / f"library_panel_{PANEL_RUN}.parquet", columns=["date", "symbol", "median_dollar_vol"],
                        filters=[("date", ">=", pd.Timestamp("2005-06-01"))])
    K["date"] = pd.to_datetime(K["date"])
    K["permno"] = pd.to_numeric(K["symbol"], errors="coerce")
    K = K.dropna(subset=["permno"])
    K["permno"] = K["permno"].astype("int64")
    D = pd.read_parquet(CR_OUT / f"followups_daily_{CS_RUN}.parquet", columns=["date", "permno", "cs_spread"],
                        filters=[("date", ">=", pd.Timestamp("2005-06-01"))])
    D["date"] = pd.to_datetime(D["date"])
    D["permno"] = pd.to_numeric(D["permno"], errors="coerce").astype("int64")
    K = K.merge(D, on=["date", "permno"], how="left")
    del D
    K["band"] = MT.size_band(K["median_dollar_vol"].to_numpy(dtype=float))
    flat = np.array([XR.COST_BPS_BY_BAND[XR.liquidity_band(v)] / 1e4 if np.isfinite(v) else 0.0035
                     for v in K["median_dollar_vol"].to_numpy(dtype=float)])
    cs = np.minimum(K["cs_spread"].to_numpy(dtype=float), 0.20)
    K["rt"] = np.where(np.isfinite(cs), np.maximum(cs, flat), flat)
    E = pd.merge_asof(E.sort_values("pub"), K[["date", "permno", "band", "rt"]].sort_values("date"),
                      left_on="pub", right_on="date", by="permno", direction="backward").drop(columns=["date"])
    bandmap = K[["date", "permno", "band"]].copy()
    bandmap["ym"] = (bandmap["date"] + pd.offsets.MonthBegin(1)).dt.to_period("M")   # month-end band used next month
    bandmap = bandmap.drop_duplicates(["permno", "ym"]).set_index(["permno", "ym"])["band"]
    del K
    gc.collect()
    ff = pd.read_parquet(WRDS / "ff_factors_daily.parquet", columns=["date", "mktrf", "rf"])
    ff["date"] = pd.to_datetime(ff["date"])
    mkt = (ff.set_index("date")["mktrf"] + ff.set_index("date")["rf"]).astype(float)
    rows, band_daily = [], []
    need = set(E["permno"])
    for y in range(2006, 2025):
        te = time.time()
        f = WRDS / f"crsp_dsf_{y}.parquet"
        if not f.exists():
            continue
        X = pd.read_parquet(f, columns=["permno", "date", "ret", "prc", "openprc"])
        X["date"] = pd.to_datetime(X["date"])
        for c in ("ret", "prc", "openprc", "permno"):
            X[c] = pd.to_numeric(X[c], errors="coerce")
        X = X.dropna(subset=["permno"])
        X["permno"] = X["permno"].astype("int64")
        ym = X["date"].dt.to_period("M")
        X["band"] = bandmap.reindex(pd.MultiIndex.from_arrays([X["permno"], ym])).to_numpy()
        bd = X.dropna(subset=["ret", "band"]).groupby(["date", "band"])["ret"].mean().unstack("band")
        band_daily.append(bd)
        rows.append(X[X["permno"].isin(need)][["permno", "date", "ret", "prc", "openprc"]])
        del X
        gc.collect()
        say(f"    {y} {time.time()-te:.0f}s")
    BD = pd.concat(band_daily).sort_index()
    R = pd.concat(rows, ignore_index=True).sort_values(["permno", "date"])
    del rows, band_daily
    cal = BD.index
    recs = []
    for p, g in R.groupby("permno", sort=False):
        ev = E[E["permno"] == p]
        dts = g["date"].to_numpy(dtype="datetime64[ns]")
        ret = g["ret"].to_numpy(dtype=float)
        prc = np.abs(g["prc"].to_numpy(dtype=float))
        opn = np.abs(g["openprc"].to_numpy(dtype=float))
        for _, e in ev.iterrows():
            i = int(np.searchsorted(dts, np.datetime64(e["pub"]), side="right"))
            if i >= len(dts):
                continue
            if not (np.isfinite(opn[i]) and opn[i] > 0 and np.isfinite(prc[i])):
                continue
            ci = int(np.searchsorted(cal, dts[i]))
            for H in HORIZONS:
                j = i + H - 1
                if j >= len(dts) or (dts[j] - dts[i]) > np.timedelta64(int(H * 1.6) + 5, "D"):
                    continue
                r_stock = (prc[i] / opn[i]) * np.prod(1.0 + np.nan_to_num(ret[i + 1:j + 1])) - 1.0
                days = cal[ci:ci + H]
                r_m = float(np.prod(1.0 + mkt.reindex(days).fillna(0.0).to_numpy()) - 1.0)
                b = e["band"] if isinstance(e["band"], str) else "small"
                r_b = float(np.prod(1.0 + BD[b].reindex(days).fillna(0.0).to_numpy()) - 1.0) if b in BD else np.nan
                rt = float(e["rt"]) if np.isfinite(e["rt"]) else 0.0035
                recs.append({"permno": p, "pub": e["pub"], "entry": pd.Timestamp(dts[i]), "H": H, "band": b,
                             "n_buyers": int(e["n_buyers"]), "r": r_stock, "r_mkt": r_m, "r_band": r_b, "rt": rt})
    Ev = pd.DataFrame(recs)
    Ev.to_parquet(OUT / f"insider_events_{tag}.parquet")
    res = {"n_events": int(len(E)), "n_measured": {str(H): int((Ev["H"] == H).sum()) for H in HORIZONS},
           "events_by_year": E["pub"].dt.year.value_counts().sort_index().astype(int).to_dict(),
           "band_share": Ev[Ev["H"] == 21]["band"].value_counts(normalize=True).round(3).to_dict(),
           "mean_round_trip_bps": float(Ev["rt"].mean() * 1e4), "cells": {}}
    for H in HORIZONS:
        for bm in ("market", "band_ew"):
            x = Ev[Ev["H"] == H].copy()
            x["ab"] = x["r"] - (x["r_mkt"] if bm == "market" else x["r_band"]) - x["rt"]
            x["ab_gross"] = x["r"] - (x["r_mkt"] if bm == "market" else x["r_band"])
            mon = x.groupby(x["entry"].dt.to_period("M"))[["ab", "ab_gross"]].mean()
            mon.index = mon.index.to_timestamp(how="start") - pd.Timedelta(days=1)
            st = {k: HI.spread_stats(mon["ab"], lo, hi) for k, (lo, hi) in SPLITS.items()}
            ok, fails = HI.survives(st["design"], st["validate"])
            res["cells"][f"H{H}_{bm}"] = {**st, "gross": {k: HI.spread_stats(mon["ab_gross"], lo, hi)
                                                         for k, (lo, hi) in SPLITS.items()},
                                          "event_mean_net": float(x["ab"].mean()), "event_hit": float((x["ab"] > 0).mean()),
                                          "survives": ok, "fails": fails}
            v = st["validate"]
            say(f"  H{H} {bm:7s}: D {st['design']['mean_monthly']:+.4f} V {v['mean_monthly']:+.4f} t {v['t_blocks']} "
                f"yrs {v['years_positive']} L {st['late']['mean_monthly']:+.4f} {'SURVIVES' if ok else ''}")
    doc = {"schema": "hyp_lab/insider_events_results/1", "tag": tag, "declaration_sha16": d["sha16"],
           "written_utc": _now(), "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "decision": DECISION,
           "results": res, "seconds": round(time.time() - t0, 1)}
    _write(rp, doc)
    say(f"-> {rp.name} {time.time()-t0:.0f}s")
    return 0


LOWCOST_RT = 0.0040
LOWCOST_NOTE = ("Declared AFTER the aggregate read (gross +1.1-1.5%/5 sessions, round trip 136 bps mean, net ~0): the "
                "low-cost subset (event round trip <= 40 bps) was NOT read. Same cells, same decision rule, "
                "search +4.")


def part_declare_lowcost(tag: str) -> int:
    p = OUT / f"insider_lowcost_DECLARATION_{tag}.json"
    if p.exists():
        say(f"REFUSED: {p.name} exists")
        return 2
    body = {"schema": "hyp_lab/insider_lowcost_declaration/1", "parent_tag": tag, "subset": f"rt <= {LOWCOST_RT}",
            "note": LOWCOST_NOTE, "decision": DECISION, "splits": SPLITS,
            "search_count": {"prior": PRIOR_SEARCH + 4, "cells": 4, "after": PRIOR_SEARCH + 8}}
    body["sha16"] = _sha(body)
    body["written_utc"] = _now()
    _write(p, body)
    say(f"-> {p.name} sha {body['sha16']}")
    return 0


def part_run_lowcost(tag: str) -> int:
    from backend.services import hyp_investable as HI                # noqa: PLC0415
    d = json.loads((OUT / f"insider_lowcost_DECLARATION_{tag}.json").read_text(encoding="utf-8"))
    if _sha({k: v for k, v in d.items() if k not in ("sha16", "written_utc")}) != d["sha16"]:
        say("REFUSED: declaration hash mismatch")
        return 2
    rp = OUT / f"insider_lowcost_RESULTS_{tag}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists")
        return 2
    Ev = pd.read_parquet(OUT / f"insider_events_{tag}.parquet")
    Ev = Ev[Ev["rt"] <= LOWCOST_RT]
    res = {"n_events": {str(H): int((Ev["H"] == H).sum()) for H in HORIZONS},
           "band_share": Ev[Ev["H"] == 21]["band"].value_counts(normalize=True).round(3).to_dict(),
           "mean_round_trip_bps": float(Ev["rt"].mean() * 1e4), "cells": {}}
    for H in HORIZONS:
        for bm in ("market", "band_ew"):
            x = Ev[Ev["H"] == H].copy()
            ref = x["r_mkt"] if bm == "market" else x["r_band"]
            x["ab"], x["ab_gross"] = x["r"] - ref - x["rt"], x["r"] - ref
            mon = x.groupby(x["entry"].dt.to_period("M"))[["ab", "ab_gross"]].mean()
            mon.index = mon.index.to_timestamp(how="start") - pd.Timedelta(days=1)
            st = {k: HI.spread_stats(mon["ab"], lo, hi) for k, (lo, hi) in SPLITS.items()}
            ok, fails = HI.survives(st["design"], st["validate"])
            res["cells"][f"H{H}_{bm}"] = {**st, "gross": {k: HI.spread_stats(mon["ab_gross"], lo, hi)
                                                         for k, (lo, hi) in SPLITS.items()},
                                          "survives": ok, "fails": fails}
            v = st["validate"]
            say(f"  lowcost H{H} {bm:7s}: D {st['design']['mean_monthly']} V {v['mean_monthly']} t {v['t_blocks']} "
                f"yrs {v['years_positive']} L {st['late']['mean_monthly']} {'SURVIVES' if ok else ''}")
    _write(rp, {"schema": "hyp_lab/insider_lowcost_results/1", "tag": tag, "declaration_sha16": d["sha16"],
                "written_utc": _now(), "results": res})
    say(f"-> {rp.name}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True, choices=["declare", "run", "declare_lowcost", "run_lowcost"])
    ap.add_argument("--tag", required=True)
    a = ap.parse_args(argv)
    if a.part == "run" and not _mem_ok():
        say("REFUSED: under 3 GB free for 30 minutes")
        return 3
    return {"declare": part_declare, "run": part_run, "declare_lowcost": part_declare_lowcost,
            "run_lowcost": part_run_lowcost}[a.part](a.tag)


if __name__ == "__main__":
    raise SystemExit(main())
