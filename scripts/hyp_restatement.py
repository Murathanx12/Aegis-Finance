"""How much of quality's "t 6" is restated data? First-reported vs latest-reported SEC facts (2026-09-30).

    python -m scripts.hyp_restatement --part declare --tag <T>
    python -m scripts.hyp_restatement --part run     --tag <T>

The SEC companyfacts history on disk (`fundamentals_sec/sec_facts_history.parquet`,
2009-04 onward, ~2,900 CIKs picked from TODAY's tickers) keeps every filing that
reported a value, so each annual value exists in two vintages:

- FIRST: the value in the first filing that carried it (what an investor could read);
- LATEST: the value in the most recent filing that re-reported it (restated or
  reclassified comparatives) -- the "current vintage" a Compustat snapshot stores.

Both are timed at the FIRST filing date + 2 days, so the only difference is the vintage.
quality_composite and cash_lowvol are run with FIRST, LATEST and Compustat inputs on
IDENTICAL (date, name) coverage; the paired gap is the restatement effect. The universe
is survivor-selected (today's tickers), which touches all three versions alike; the
level of each is NOT a strategy estimate, only the differences are read.

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

from scripts.hyp_investable import (OUT, WRDS, _mem_ok, _now, _sha, _write, load, market_and_rf,  # noqa: E402
                                    picks_library, run_book, say, spreads_of)

FACTS = REPO / "backend" / "data" / "optimus" / "fundamentals_sec" / "sec_facts_history.parquet"
INPUTS_TAG = "INV_2026-09-30T0020Z"
FLOWS = ("revenue", "cogs", "operating_income")
STOCKS = ("assets", "equity", "debt", "cash")
USABLE_LAG_DAYS, STALE_DAYS = 2, 460
RULES = ("quality_composite", "cash_lowvol")
WINDOWS = {"all_2010_2024": ("2010-01-01", "2024-12-31"), "2010_2016": ("2010-01-01", "2016-12-31"),
           "2017_2024": ("2017-01-01", "2024-12-31")}
DECISION = ("Restatement effect = mean paired monthly difference (FIRST - LATEST) of rule gross - twin-basket gross, "
            "2010-2024 hold months, t on 3-month blocks. Declared reading: if |effect| < MDE, 'restatement does not "
            "measurably move the ranking'; if LATEST > FIRST at t >= 2, 'part of the edge is restated data', and the "
            "share = effect / LATEST's rule-twin mean is reported. Compustat is printed beside as the third vintage.")


# ── pure ─────────────────────────────────────────────────────────────────────

def vintages(F: pd.DataFrame) -> pd.DataFrame:
    """One row per (cik, fiscal-year end): first_filed and FIRST/LATEST values of each fact.
    Flows are annual (period 350-380 days); stocks are instants at the same end."""
    F = F.copy()
    F["end"] = pd.to_datetime(F["end"], errors="coerce")
    F = F.dropna(subset=["end", "filed", "val"])
    fl = F[F["fact"].isin(FLOWS) & F["period_days"].between(350, 380)]
    st = F[F["fact"].isin(STOCKS) & F["period_days"].isna()]
    X = pd.concat([fl, st], ignore_index=True).sort_values("filed", kind="stable")
    g = X.groupby(["cik", "end", "fact"])
    first = g.first()["val"].unstack("fact")
    latest = g.last()["val"].unstack("fact")
    ff = fl.groupby(["cik", "end"])["filed"].min().rename("first_filed")
    out = pd.concat([first.add_suffix("_first"), latest.add_suffix("_latest")], axis=1).join(ff, how="inner")
    return out.reset_index()


def ratios(V: pd.DataFrame, which: str) -> pd.DataFrame:
    s = f"_{which}"
    a = V.get("assets" + s)
    eq = V.get("equity" + s)
    out = pd.DataFrame(index=V.index)
    out["gp_at"] = (V.get("revenue" + s) - V.get("cogs" + s)) / a.where(a > 0)
    out["ope_be"] = V.get("operating_income" + s) / eq.where(eq > 0)
    out["debt_at"] = V.get("debt" + s) / a.where(a > 0)
    out["cash_at"] = V.get("cash" + s) / a.where(a > 0)
    return out


def asof_join(keys: pd.DataFrame, R: pd.DataFrame, cols: list) -> pd.DataFrame:
    """keys (date, permno) <- the latest firm-year with usable <= date, not staler than STALE_DAYS."""
    k = keys.sort_values("date").reset_index()
    r = R.sort_values("usable")
    j = pd.merge_asof(k, r[["permno", "usable"] + cols], left_on="date", right_on="usable", by="permno",
                      direction="backward")
    stale = (j["date"] - j["usable"]).dt.days > STALE_DAYS
    j.loc[stale, cols] = np.nan
    return j.set_index("index").sort_index()[cols]


def link_permno(V: pd.DataFrame) -> pd.Series:
    comp = pd.read_parquet(WRDS / "bulk" / "comp__company.parquet", columns=["gvkey", "cik"]).dropna()
    comp["cik"] = pd.to_numeric(comp["cik"], errors="coerce")
    L = pd.read_parquet(WRDS / "bulk" / "crsp__ccmxpf_lnkhist.parquet",
                        columns=["gvkey", "linktype", "linkprim", "lpermno", "linkdt", "linkenddt"])
    L = L[L["linktype"].isin(["LC", "LU"]) & L["linkprim"].isin(["P", "C"])].dropna(subset=["lpermno"])
    L["linkdt"] = pd.to_datetime(L["linkdt"], errors="coerce")
    L["linkenddt"] = pd.to_datetime(L["linkenddt"], errors="coerce").fillna(pd.Timestamp("2100-01-01"))
    m = V[["cik", "end"]].reset_index().merge(comp, on="cik", how="left").merge(L, on="gvkey", how="left")
    m = m[(m["end"] >= m["linkdt"]) & (m["end"] <= m["linkenddt"])]
    m = m.drop_duplicates("index")
    return m.set_index("index")["lpermno"].astype("int64").reindex(V.index)


# ── parts ────────────────────────────────────────────────────────────────────

def part_declare(tag: str) -> int:
    p = OUT / f"restatement_DECLARATION_{tag}.json"
    if p.exists():
        say(f"REFUSED: {p.name} exists")
        return 2
    body = {"schema": "hyp_lab/restatement_declaration/1", "rules": list(RULES), "decision": DECISION,
            "windows": WINDOWS, "inputs_tag": INPUTS_TAG, "flows": FLOWS, "stocks": STOCKS,
            "timing": f"both vintages usable from the FIRST annual filing + {USABLE_LAG_DAYS} days; stale after "
                      f"{STALE_DAYS} days", "coverage_rule": "rows where FIRST, LATEST and Compustat all give the "
                                                            "rule's inputs", "search_count_added": 0,
            "search_note": "a measurement of the data, not a new rule; the rules are unchanged"}
    body["sha16"] = _sha(body)
    body["written_utc"] = _now()
    _write(p, body)
    say(f"-> {p.name} sha {body['sha16']}")
    return 0


def part_run(tag: str) -> int:
    from backend.services import hyp_investable as HI                # noqa: PLC0415
    d = json.loads((OUT / f"restatement_DECLARATION_{tag}.json").read_text(encoding="utf-8"))
    if _sha({k: v for k, v in d.items() if k not in ("sha16", "written_utc")}) != d["sha16"]:
        say("REFUSED: declaration hash mismatch")
        return 2
    rp = OUT / f"restatement_RESULTS_{tag}.json"
    if rp.exists():
        say(f"REFUSED: {rp.name} exists")
        return 2
    t0 = time.time()
    F = pd.read_parquet(FACTS, columns=["cik", "fact", "filed", "end", "period_days", "val"])
    V = vintages(F)
    del F
    V["permno"] = link_permno(V)
    V = V.dropna(subset=["permno"])
    V["permno"] = V["permno"].astype("int64")
    V["usable"] = V["first_filed"] + pd.Timedelta(days=USABLE_LAG_DAYS)
    diff_share = {}
    for f in FLOWS + STOCKS:
        a, b = V.get(f + "_first"), V.get(f + "_latest")
        if a is None:
            continue
        ok = a.notna() & b.notna() & (a.abs() > 0)
        diff_share[f] = {"firm_years": int(ok.sum()),
                         "share_changed_gt_1pct": float(((b - a).abs() / a.abs() > 0.01)[ok].mean())}
    say(f"  vintages {len(V):,} firm-years, {V['permno'].nunique()} permnos {time.time()-t0:.0f}s; {diff_share}")
    P = load(INPUTS_TAG)
    P = P[P["date"] >= pd.Timestamp("2009-12-01")].reset_index(drop=True)
    P["_sp"] = spreads_of(P)
    keys = P[["date", "permno"]]
    cols = ["gp_at", "ope_be", "debt_at", "cash_at"]
    vers = {}
    for which in ("first", "latest"):
        R = pd.concat([V[["permno", "usable"]], ratios(V, which)], axis=1)
        vers[which] = asof_join(keys, R, cols)
    vers["compustat"] = P[cols].astype(float)
    mkt, _rf = market_and_rf(sorted(P["date"].unique()))
    res = {"firm_years": int(len(V)), "permnos": int(V["permno"].nunique()), "share_changed": diff_share}
    for rid in RULES:
        need = ["gp_at", "ope_be", "debt_at"] if rid == "quality_composite" else ["cash_at"]
        cover = np.ones(len(P), dtype=bool)
        for v in vers.values():
            cover &= v[need].notna().all(axis=1).to_numpy()
        series, picks = {}, {}
        for which, v in vers.items():
            Q = P.copy()
            for c in cols:
                Q[c] = np.where(cover, v[c].to_numpy(dtype=float), np.nan)
            pk = picks_library(Q, rid)
            picks[which] = pk
            B = run_book(Q, pk, start="2009-12-01")
            B["market"] = mkt.reindex(B.index)
            series[which] = B
            B.to_parquet(OUT / f"restatement_book_{tag}_{rid}_{which}.parquet")
            del Q
            gc.collect()
        rr = {"covered_rows_per_month": float(pd.Series(cover).groupby(P["date"].to_numpy()).sum().mean())}
        for which, B in series.items():
            sel = B["gross"] - B["twin_gross"]
            net = B["gross"] - B["cost"] - B["market"]
            rr[which] = {w: {"rule_minus_twin_gross": HI.spread_stats(sel, lo, hi),
                             "rule_net_minus_market": HI.spread_stats(net, lo, hi)} for w, (lo, hi) in WINDOWS.items()}
        for a, b in (("first", "latest"), ("first", "compustat"), ("latest", "compustat")):
            dd = (series[a]["gross"] - series[a]["twin_gross"]) - (series[b]["gross"] - series[b]["twin_gross"])
            rr[f"paired_{a}_minus_{b}"] = {w: HI.spread_stats(dd, lo, hi) for w, (lo, hi) in WINDOWS.items()}
        ov = [len(set(picks["first"].get(k_, [])) & set(picks["latest"].get(k_, []))) / max(1, len(picks["first"][k_]))
              for k_ in picks["first"]]
        rr["pick_overlap_first_vs_latest"] = float(np.mean(ov)) if ov else None
        res[rid] = rr
        say(f"  {rid}: first-latest {rr['paired_first_minus_latest']['all_2010_2024']['mean_monthly']} "
            f"t {rr['paired_first_minus_latest']['all_2010_2024']['t_blocks']} {time.time()-t0:.0f}s")
    doc = {"schema": "hyp_lab/restatement_results/1", "tag": tag, "declaration_sha16": d["sha16"],
           "written_utc": _now(), "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "decision": DECISION,
           "results": res, "seconds": round(time.time() - t0, 1)}
    _write(rp, doc)
    say(f"-> {rp.name} {time.time()-t0:.0f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", required=True, choices=["declare", "run"])
    ap.add_argument("--tag", required=True)
    a = ap.parse_args(argv)
    if a.part == "run" and not _mem_ok():
        say("REFUSED: under 3 GB free for 30 minutes")
        return 3
    return {"declare": part_declare, "run": part_run}[a.part](a.tag)


if __name__ == "__main__":
    raise SystemExit(main())
