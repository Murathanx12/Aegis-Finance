"""Risk as the product: volatility-managed market exposure driven by the size forecast (2026-09-30).

    python -m scripts.hyp_volmanaged --part declare --tag <T>   # hashed before any policy return exists
    python -m scripts.hyp_volmanaged --part run     --tag <T>   # design fit, ONE validate read, late last

Licence `PRODUCT_EXPERIMENT`. $0, no LLM, no network. Prior closures read first:
`docs/KNOWLEDGE/quant-investor-lessons.md` #3 (Moreira-Muir alpha refuted 0-3; vol overlays
are drawdown control at about flat Sharpe), `PREREG_N12_VOL_TARGETED_SIZING` (matched-vol
log wealth NOT_DETECTABLE_IN_SCOPE), BACKLOG T6 (vol-managed momentum, survivor-inflated).
What is new here is the FORECASTER: HAR fitted on the design window and HAR plus the
earnings-season intensity, the one market-level analogue of the replicated stock fact.
Pure pieces: `backend/services/hyp_volmanaged.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.hyp_investable import OUT, WRDS, _now, _sha, _write, say  # noqa: E402

PRIOR_SEARCH = 42_685          # 42,666 + the 19 investable cells of this night
SPLITS = {"design": ("1991-01-01", "2008-12-31"), "validate": ("2009-01-01", "2016-12-31"),
          "late": ("2017-01-01", "2024-12-31")}
FORECASTERS = ("rv22", "rv63", "har", "har_ei")
FREQS = {"M": 21, "W": 5}
EI_DAYS = {"M": 30, "W": 7}
DECISION = ("A cell (forecaster x rebalance) SURVIVES iff, against buy-and-hold at the SAME mean exposure over the "
            "window, the monthly log-return difference is > 0 in design (1991-2008) AND > 0 in validate (2009-2016) "
            "with t >= 2 on 3-month blocks AND a strict majority of validate years > 0. The ENGINE question is read "
            "separately: har_ei - rv22 (paired policies, same rebalance) > 0 in validate at t >= 2. The exposure "
            "constant c is set on DESIGN dates only (mean exposure 1 there); HAR coefficients are fitted on design "
            "decision dates whose target window ends by 2008-12-31. 2017-2024 is read last, as description.")


def earnings_intensity(days: pd.DatetimeIndex, horizon_days: int) -> pd.Series:
    """Share of market value EXPECTED to report in (t, t + horizon] -- each firm-quarter's
    report date one year earlier + 364 days, weighted by that quarter's market value --
    over the market value expected in (t - 182, t + 182]. Known at t."""
    q = pd.read_parquet(WRDS / "bulk" / "comp__fundq.parquet",
                        columns=["gvkey", "rdq", "cshoq", "prccq", "datafmt", "consol", "popsrc"])
    q = q[(q["datafmt"] == "STD") & (q["consol"] == "C") & (q["popsrc"] == "D")]
    q["rdq"] = pd.to_datetime(q["rdq"], errors="coerce")
    q["mv"] = pd.to_numeric(q["cshoq"], errors="coerce") * pd.to_numeric(q["prccq"], errors="coerce")
    q = q.dropna(subset=["rdq", "mv"])
    q = q[q["mv"] > 0]
    exp_day = (q["rdq"] + pd.Timedelta(days=364)).dt.normalize()
    daily = q["mv"].groupby(exp_day).sum().sort_index()
    cal = pd.date_range(min(days.min(), daily.index.min()) - pd.Timedelta(days=400),
                        max(days.max(), daily.index.max()) + pd.Timedelta(days=400), freq="D")
    s = daily.reindex(cal, fill_value=0.0)
    cs = s.cumsum()

    def between(a, b):
        return cs.reindex(b).to_numpy() - cs.reindex(a).to_numpy()

    d = pd.DatetimeIndex(days).normalize()
    num = between(d, d + pd.Timedelta(days=horizon_days))
    den = between(d - pd.Timedelta(days=182), d + pd.Timedelta(days=182))
    return pd.Series(np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan), index=days)


def part_declare(tag: str) -> int:
    p = OUT / f"volmanaged_DECLARATION_{tag}.json"
    if p.exists():
        say(f"REFUSED: {p.name} exists")
        return 2
    from backend.services import hyp_volmanaged as V                 # noqa: PLC0415
    body = {"schema": "hyp_lab/volmanaged_declaration/1", "licence": "PRODUCT_EXPERIMENT",
            "written_before_any_policy_return": True, "market": "FF daily mkt+rf (CRSP value-weighted, costless)",
            "forecasters": {"rv22": "sqrt(mean r^2, 22 sessions)", "rv63": "sqrt(mean r^2, 63 sessions)",
                            "har": "log RV(t+1..t+h) on log rv1, rv5, rv22 (design OLS), exp(fit + s^2/2)",
                            "har_ei": "har + earnings-season intensity over the hold window (known beforehand)"},
            "rebalance": FREQS, "exposure": f"w = c / sigma_hat, clipped to [0, {V.MAX_EXPOSURE}]",
            "costs": {"trade_per_unit_dw": V.TRADE_COST, "lever_spread_annual": V.LEVER_SPREAD_ANNUAL},
            "benchmark": "rf + mean(w over the window) x (mkt - rf): buy-and-hold at the SAME average exposure; "
                         "matched realised vol printed beside", "splits": SPLITS, "decision": DECISION,
            "search_count": {"prior": PRIOR_SEARCH, "cells": len(FORECASTERS) * len(FREQS),
                             "after": PRIOR_SEARCH + len(FORECASTERS) * len(FREQS)}}
    body["sha16"] = _sha(body)
    body["written_utc"] = _now()
    _write(p, body)
    say(f"-> {p.name} sha {body['sha16']}")
    return 0


def part_run(tag: str) -> int:
    from backend.services import hyp_volmanaged as V                 # noqa: PLC0415
    d = json.loads((OUT / f"volmanaged_DECLARATION_{tag}.json").read_text(encoding="utf-8"))
    if _sha({k: v for k, v in d.items() if k not in ("sha16", "written_utc")}) != d["sha16"]:
        say("REFUSED: declaration hash mismatch")
        return 2
    rp = OUT / f"volmanaged_RESULTS_{tag}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists (read once)")
        return 2
    t0 = time.time()
    ff = pd.read_parquet(WRDS / "ff_factors_daily.parquet", columns=["date", "mktrf", "rf"])
    ff["date"] = pd.to_datetime(ff["date"])
    ff = ff.set_index("date").astype(float)
    ff = ff[(ff.index >= "1989-01-01") & (ff.index <= "2024-12-31")]
    r, rf = ff["mktrf"] + ff["rf"], ff["rf"]
    X = V.realised_features(r)
    res, pols = {}, {}
    for fq, h in FREQS.items():
        dd = V.decision_days(r.index, fq)
        dd = dd[dd >= pd.Timestamp("1990-06-01")]
        Xd = X.reindex(dd).copy()
        Xd["ei"] = earnings_intensity(dd, EI_DAYS[fq]).to_numpy()
        y = V.future_var(r, h).reindex(dd)
        des = (dd >= pd.Timestamp(SPLITS["design"][0])) & (
            pd.DatetimeIndex([r.index[min(r.index.get_loc(x) + h, len(r) - 1)] for x in dd])
            <= pd.Timestamp(SPLITS["design"][1]))
        models = {"har": V.fit_har(Xd[des], y[des], ["rv1", "rv5", "rv22"]),
                  "har_ei": V.fit_har(Xd[des], y[des], ["rv1", "rv5", "rv22", "ei"])}
        var_hat = {"rv22": Xd["rv22"], "rv63": Xd["rv63"], "har": V.predict_har(models["har"], Xd),
                   "har_ei": V.predict_har(models["har_ei"], Xd)}
        for f in FORECASTERS:
            sig = np.sqrt(var_hat[f])
            c = V.scale_for_mean_exposure(sig[des])
            w = V.exposures(sig, c)
            pol = V.policy_returns(r, rf, w)
            pols[(f, fq)] = pol
            cell = {k: V.compare(pol, lo, hi) for k, (lo, hi) in SPLITS.items()}
            cell["full"] = V.compare(pol, "1991-01-01", "2024-12-31")
            val_mask = (dd >= pd.Timestamp(SPLITS["validate"][0])) & (dd <= pd.Timestamp(SPLITS["validate"][1]))
            cell["qlike_validate"] = V.qlike(var_hat[f][val_mask], y[val_mask])
            cell["qlike_design"] = V.qlike(var_hat[f][des], y[des])
            ds, vs = cell["design"], cell["validate"]
            yp = vs.get("years_positive", "0 of 0").split(" of ")
            ok = ((ds.get("diff_log_per_month") or 0) > 0 and (vs.get("diff_log_per_month") or 0) > 0
                  and (vs.get("t_blocks") or 0) >= 2 and int(yp[0]) * 2 > int(yp[1]))
            cell["survives"], cell["c"] = bool(ok), float(c)
            res[f"{f}_{fq}"] = cell
            say(f"  {f:7s} {fq}: V diff {vs['diff_log_per_month']*100:+.3f}%/mo t {vs['t_blocks']} yrs "
                f"{vs['years_positive']} DD {vs['max_dd_policy']:.3f} vs {vs['max_dd_bench']:.3f} "
                f"qlike {cell['qlike_validate']:.3f} {'SURVIVES' if ok else ''}")
        res[f"models_{fq}"] = models
    engine = {}
    for fq in FREQS:
        for a, b in (("har_ei", "rv22"), ("har_ei", "har"), ("har", "rv22")):
            pa, pb = pols[(a, fq)], pols[(b, fq)]
            j = pd.concat([np.log1p(pa["ret"]), np.log1p(pb["ret"])], axis=1, keys=["a", "b"]).dropna()
            mon = (j["a"] - j["b"]).groupby(j.index.to_period("M")).sum()
            mon.index = mon.index.to_timestamp(how="start") - pd.Timedelta(days=1)
            from backend.services import hyp_investable as HI         # noqa: PLC0415
            engine[f"{a}_minus_{b}_{fq}"] = {k: HI.spread_stats(mon, lo, hi)
                                             for k, (lo, hi) in SPLITS.items()}
    doc = {"schema": "hyp_lab/volmanaged_results/1", "tag": tag, "declaration_sha16": d["sha16"],
           "written_utc": _now(), "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "decision": DECISION,
           "cells": res, "engine_forecast_paired": engine,
           "n_survivors": sum(1 for k, v in res.items() if isinstance(v, dict) and v.get("survives")),
           "seconds": round(time.time() - t0, 1)}
    _write(rp, doc)
    say(f"-> {rp.name} survivors {doc['n_survivors']} {time.time()-t0:.0f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True, choices=["declare", "run"])
    ap.add_argument("--tag", required=True)
    a = ap.parse_args(argv)
    return {"declare": part_declare, "run": part_run}[a.part](a.tag)


if __name__ == "__main__":
    raise SystemExit(main())
