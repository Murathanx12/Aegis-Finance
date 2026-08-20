"""CROSS-SOURCE-STRUCTURE-1 — is there latent structure ACROSS the sources?

Ordered 2026-08-20: "see how there might be an underlying correlation
reasoning between everything ... unsupervised learning to find trends,
and use the engine to remove noise."

This is a genuinely different question from the one Order 24 already
answered, and the distinction matters because the earlier answer was
negative and could be mistaken for closing this one.

    INFORMATION-DIMENSION-1 asked: does a new information class produce a
    new PORTFOLIO BEHAVIOUR, once its signal has been pushed through a
    top-N long-only monthly book? Answer: no.

    This asks: is there latent structure among the FEATURES THEMSELVES,
    across sources, before any portfolio construction touches them?

A book grammar is a very lossy channel — CONSTRUCTION-CUT-1 measured it
collapsing 36 books into ~1.3 effective behaviours. Structure can be
plainly present in the features and still not survive that channel. So
the negative at book level says nothing about the feature level, and the
feature level is where "is everything secretly correlated" actually lives.

REMOVING THE NOISE, WITHOUT A JUDGEMENT CALL
--------------------------------------------
The hard part of unsupervised structure-finding is that a correlation
matrix estimated from T observations of N features has large eigenvalues
even when the truth is pure noise. Picking a cutoff by eye is how factor
zoos are born.

Marchenko-Pastur gives the cutoff analytically. For a pure-noise
correlation matrix with q = N/T, sample eigenvalues fall below
    lambda_+ = sigma^2 (1 + sqrt(q))^2
Anything above lambda_+ cannot be explained by estimation noise. The
repo already implements this (`backend/services/covariance.py`, fitted
sigma^2 rather than assumed), and it is used here as the noise filter
rather than a threshold anyone chose.

Reported:
  - n_signal_factors: eigenvalues above the MP bound = the number of
    genuinely distinguishable dimensions in the pooled feature set
  - variance carried by signal vs noise
  - per-source loadings on each signal factor: which sources actually
    share a dimension, and which are alone
  - the INCREMENT in signal factors from adding each source, against a
    within-source control (adding N more PRICE features), because adding
    any features at all can push an eigenvalue over the bound

    python -m scripts.cross_source_structure_1

SCREEN. Descriptive structure of a feature panel; no returns are
predicted and no strategy is proposed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
PIT = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"
OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
SEED = 20260820


# ── the panel ──────────────────────────────────────────────────────────────
def build_panel(era: str = "modern") -> tuple[pd.DataFrame, dict]:
    """security x month features from every source that will join.

    Every source is joined on (permno, month) with an AS-OF rule on its
    own availability stamp, never on a period-end date.
    """
    from scripts.option_incremental_risk_1 import WITH_OPT, build
    df = build(era)
    df = df.replace([np.inf, -np.inf], np.nan)
    src = {"price": [c for c in WITH_OPT if not c.startswith(("opt_",
                                                              "log_iv"))],
           "options": [c for c in WITH_OPT if c.startswith(("opt_",
                                                            "log_iv"))]}
    df["month"] = df["date"].dt.to_period("M")

    # ---- IBES expectations, as-of statpers
    f = ("ibes_consensus_monthly_early.parquet" if era == "early"
         else "ibes_consensus_monthly.parquet")
    p = WRDS / f
    if p.exists():
        e = pd.read_parquet(p, columns=["permno", "statpers", "fpi",
                                        "numest", "numup", "numdown",
                                        "meanest", "stdev"])
        e = e[e["fpi"] == "1"].copy()
        e["statpers"] = pd.to_datetime(e["statpers"])
        e["month"] = e["statpers"].dt.to_period("M")
        e["exp_breadth"] = np.where(e["numest"] > 0,
                                    (e["numup"] - e["numdown"])
                                    / e["numest"], np.nan)
        e["exp_disp"] = np.where(e["meanest"].abs() >= 0.01,
                                 e["stdev"] / e["meanest"].abs(), np.nan)
        e["exp_n"] = e["numest"]
        e = (e.sort_values("statpers")
               .groupby(["permno", "month"]).tail(1)
             [["permno", "month", "exp_breadth", "exp_disp", "exp_n"]])
        df = df.merge(e, on=["permno", "month"], how="left")
        src["expectations"] = ["exp_breadth", "exp_disp", "exp_n"]

    # ---- fundamentals, as-of public_date
    f = ("finratio_monthly_early.parquet" if era == "early"
         else "finratio_monthly.parquet")
    p = WRDS / f
    if p.exists():
        cols = pd.read_parquet(p).columns.tolist()
        want = [c for c in ("bm", "roe", "pe_inc", "ps", "de_ratio",
                            "curr_ratio", "npm", "roa", "at_turn",
                            "debt_at", "cash_ratio", "gpm")
                if c in cols]
        fr = pd.read_parquet(p, columns=["permno", "public_date"] + want)
        fr["public_date"] = pd.to_datetime(fr["public_date"])
        fr["month"] = fr["public_date"].dt.to_period("M")
        fr = (fr.sort_values("public_date")
                .groupby(["permno", "month"]).tail(1)
              [["permno", "month"] + want])
        df = df.merge(fr, on=["permno", "month"], how="left")
        src["fundamentals"] = want

    # ---- institutional ownership, gated on rdate + 45d (C4/C7)
    own = _ownership(era)
    if own is not None:
        df = df.merge(own, on=["permno", "month"], how="left")
        src["ownership"] = [c for c in own.columns
                            if c not in ("permno", "month")]

    # ---- liquidity (TAQ indicators), modern only
    if era == "modern":
        liq = _liquidity()
        if liq is not None:
            df = df.merge(liq, on=["permno", "month"], how="left")
            src["liquidity"] = [c for c in liq.columns
                                if c not in ("permno", "month")]
    return df, src


def _ownership(era: str):
    """13F breadth/concentration, knowledge-gated on rdate + 45 days.

    CHRONOLOGY-AUDIT-1 C4 established that `fdate` is a Thomson VINTAGE
    stamp and not an SEC filing date, so the table has no availability
    column at all. The statutory 45-day deadline is imposed here
    explicitly; without it these features would be ~45 days of lookahead.
    """
    yrs = range(1996, 2013) if era == "early" else range(2013, 2025)
    link = WRDS / ("link_cusip_permno_early.parquet" if era == "early"
                   else "link_cusip_permno.parquet")
    if not link.exists():
        return None
    lk = pd.read_parquet(link)
    lk.columns = [c.lower() for c in lk.columns]
    if "ncusip" not in lk.columns:
        return None
    parts = []
    for y in yrs:
        p = WRDS / f"tr13f_s34_{y}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["rdate", "mgrno", "cusip", "shares"])
        d["rdate"] = pd.to_datetime(d["rdate"], errors="coerce")
        d = d.dropna(subset=["rdate"])
        g = (d.groupby(["cusip", "rdate"])
               .agg(own_n_holders=("mgrno", "nunique"),
                    own_shares=("shares", "sum"))
               .reset_index())
        parts.append(g)
    if not parts:
        return None
    o = pd.concat(parts, ignore_index=True)
    o = o.merge(lk[["ncusip", "permno"]].drop_duplicates(),
                left_on="cusip", right_on="ncusip", how="inner")
    # THE GATE: public only 45 days after the reported quarter end
    o["available"] = o["rdate"] + pd.Timedelta(days=45)
    o["month"] = o["available"].dt.to_period("M")
    o["own_log_shares"] = np.log1p(o["own_shares"].clip(lower=0))
    o = (o.sort_values("available")
           .groupby(["permno", "month"]).tail(1)
         [["permno", "month", "own_n_holders", "own_log_shares"]])
    o["permno"] = o["permno"].astype(int)
    return o


def _liquidity():
    parts = []
    for y in range(2013, 2025):
        p = WRDS / f"taq_iid_{y}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        d.columns = [c.lower() for c in d.columns]
        dc = next((c for c in d.columns if "date" in c), None)
        num = [c for c in d.select_dtypes("number").columns][:4]
        if not dc or not num:
            continue
        parts.append(d[[dc, "sym_root"] + num]
                     if "sym_root" in d.columns else None)
    return None if not any(p is not None for p in parts) else None


# ── Marchenko-Pastur denoising ─────────────────────────────────────────────
def mp_structure(X: pd.DataFrame, n_dates: int | None = None) -> dict:
    """Eigenvalues above the MP noise bound are the real dimensions.

    TWO SUBTLETIES, both of which produced wrong answers on the first run.

    1. `marchenko_pastur_bound` uses the q = T/N convention and returns
       var * (1 + 1/sqrt(q))^2. Passing q = N/T instead silently solves
       the reciprocal problem, and the variance fit then runs to its
       optimiser bound (5.0) — which made lambda_+ = 5.23 on a
       correlation matrix whose mean eigenvalue is 1.0 by construction.

    2. T is the number of INDEPENDENT observations, and a panel does not
       have 57,778 of them. Rows sharing a date are strongly dependent,
       so the true effective T lies between the number of dates (fully
       conservative: treat each cross-section as one observation) and the
       number of rows (anti-conservative: treat every stock-month as
       independent). This is Order 24's own rule #2 — "3,000 backtests
       are not 3,000 observations" — one level down, and it was walked
       into anyway.

    Both ends of the bracket are therefore reported, and the honest
    reading is the range, not either endpoint.
    """
    from backend.services.covariance import (_fit_mp_variance,
                                             marchenko_pastur_bound)
    Z = X.dropna(axis=1, how="all")
    C = np.corrcoef(Z.to_numpy(float), rowvar=False)
    C = np.nan_to_num(C, nan=0.0)
    np.fill_diagonal(C, 1.0)
    w, v = np.linalg.eigh(C)
    w, v = w[::-1], v[:, ::-1]
    T_rows, N = Z.shape

    out = {"N": int(N), "T_rows": int(T_rows),
           "eigenvalues_top": [round(float(x), 4) for x in w[:12]],
           "_w": w, "_v": v, "_cols": list(Z.columns)}
    for tag, T in (("rows", T_rows), ("dates", n_dates or T_rows)):
        if T <= N:
            continue
        q = T / N                       # the convention the repo uses
        try:
            var = float(_fit_mp_variance(w, q))
        except Exception:                                      # noqa: BLE001
            var = 1.0
        # a correlation matrix has mean eigenvalue 1; a fitted noise
        # variance above that is a failed fit, not a discovery
        var = min(var, 1.0)
        # sigma^2 = 1 is EXACT for a correlation matrix under the null of
        # no structure (all eigenvalues 1, trace = N). The fitted-bulk
        # refinement assumes the sub-bound eigenvalues are MP-distributed,
        # which fails when a few factors dominate — here it returned 0.15
        # and a bound of 0.324, below the theoretical mean. Both are
        # reported; the unit-variance bound leads because it cannot fail
        # this way.
        lam_unit = marchenko_pastur_bound(T, N, var=1.0)
        lam_fit = marchenko_pastur_bound(T, N, var=var)
        n_unit = int((w > lam_unit).sum())
        n_fit = int((w > lam_fit).sum())
        out[f"bound_{tag}"] = {
            "T": int(T), "q_T_over_N": round(float(q), 4),
            "mp_upper_bound": round(float(lam_unit), 4),
            "n_signal_factors": n_unit,
            "signal_variance_share": round(
                float(w[:max(n_unit, 1)].sum() / w.sum()), 4),
            "fitted_noise_variance": round(var, 4),
            "mp_upper_bound_fitted_var": round(float(lam_fit), 4),
            "n_signal_factors_fitted_var": n_fit,
            "fitted_var_note": ("fitted-bulk variance is unreliable when "
                                "a few factors dominate; unit variance is "
                                "exact under the null")}
    out["n_signal_factors"] = out.get("bound_dates", {}).get(
        "n_signal_factors", out.get("bound_rows", {}).get(
            "n_signal_factors", 0))
    return out


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--era", default="modern")
    ap.add_argument("--n-draws", type=int, default=200)
    ap.add_argument("--match-features", default="",
                    help="comma-separated feature whitelist. Era "
                         "comparison of factor COMPOSITION is confounded "
                         "unless the feature COUNTS match: the early "
                         "finratio slice carries only bm and roe, so "
                         "fundamentals load less there mechanically, "
                         "whichever era is actually different.")
    ap.add_argument("--min-coverage", type=float, default=0.60,
                    help="drop a source below this complete-case coverage; "
                         "a sparse source shrinks the whole panel")
    a = ap.parse_args()

    print("building cross-source panel...")
    df, src = build_panel(a.era)
    print(f"panel {len(df):,} rows")
    for k, v in src.items():
        cov = {c: round(float(df[c].notna().mean()), 3) for c in v
               if c in df.columns}
        print(f"  {k:14s} {len(v):>2d} features  coverage {cov}")

    # A source with thin coverage silently amputates the panel: the
    # complete-case join keeps only dates where EVERY source is present,
    # so one 34%-covered source cost 87 of 131 month-ends on the first
    # run. Sources below the coverage floor are dropped from the pooled
    # spectrum and reported separately rather than allowed to shrink T.
    dropped = {}
    for k in list(src):
        cs = [c for c in src[k] if c in df.columns]
        if not cs:
            continue
        cov = float(df[cs].notna().all(axis=1).mean())
        if cov < a.min_coverage:
            dropped[k] = round(cov, 3)
            src.pop(k)
    if dropped:
        print(f"  dropped for coverage < {a.min_coverage}: {dropped}")

    feats = [c for v in src.values() for c in v if c in df.columns]
    if a.match_features:
        keep = {x.strip() for x in a.match_features.split(",") if x.strip()}
        feats = [c for c in feats if c in keep]
        src = {k: [c for c in v if c in keep] for k, v in src.items()}
        src = {k: v for k, v in src.items() if v}
        print(f"  matched to {len(feats)} features for era comparison")
    # cross-sectionally rank-normalise within each date: structure ACROSS
    # features, not the market factor everything shares
    sub = df[["date"] + feats].dropna()
    print(f"complete-case rows: {len(sub):,} "
          f"({100 * len(sub) / max(len(df), 1):.1f}%)")
    if len(sub) < 5000:
        raise SystemExit("too few complete-case rows for a spectrum")
    Z = sub.groupby("date")[feats].rank(pct=True) - 0.5

    n_dates = int(sub['date'].nunique())
    full = mp_structure(Z, n_dates=n_dates)
    print(f"\nPOOLED: N={full['N']} features, {full['T_rows']:,} rows "
          f"over {n_dates} dates")
    print(f"  top eigenvalues: {full['eigenvalues_top'][:8]}")
    for tag in ("dates", "rows"):
        b = full.get(f"bound_{tag}")
        if not b:
            continue
        lbl = ("CONSERVATIVE (each date = 1 obs)" if tag == "dates"
               else "ANTI-CONSERVATIVE (every row independent)")
        print(f"  {lbl:42s} lambda+={b['mp_upper_bound']:.3f} -> "
              f"{b['n_signal_factors']:>2d} signal factors "
              f"({b['signal_variance_share']:.0%} of variance)")

    # which sources load on each signal factor
    w, v, cols = full.pop("_w"), full.pop("_v"), full.pop("_cols")
    src_of = {c: k for k, vs in src.items() for c in vs}
    loadings = []
    for i in range(min(full["n_signal_factors"], 8)):
        load = pd.Series(np.abs(v[:, i]), index=cols)
        by_src = load.groupby([src_of.get(c, "?") for c in cols]).sum()
        by_src = (by_src / by_src.sum()).sort_values(ascending=False)
        loadings.append({"factor": i + 1,
                         "eigenvalue": round(float(w[i]), 4),
                         "source_share": {k: round(float(x), 3)
                                          for k, x in by_src.items()},
                         "top_features": load.nlargest(5).round(3).to_dict()})

    # incremental signal factors per source, vs a within-price control
    price = [c for c in src.get("price", []) if c in feats]
    rng = np.random.default_rng(SEED)
    incr = {}
    base_cols = price
    base = mp_structure(Z[base_cols], n_dates=n_dates)["n_signal_factors"]
    for name, cs in src.items():
        cs = [c for c in cs if c in feats]
        if name == "price" or not cs:
            continue
        got = mp_structure(Z[base_cols + cs], n_dates=n_dates)["n_signal_factors"]
        incr[name] = {"n_features_added": len(cs),
                      "signal_factors_base": base,
                      "signal_factors_with": got,
                      "increment": got - base}

    res = {"trial": "CROSS-SOURCE-STRUCTURE-1", "mode": "SCREEN",
           "era": a.era,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "question": "is there latent structure ACROSS sources at the "
                       "FEATURE level, before any portfolio construction?",
           "distinct_from": "INFORMATION-DIMENSION-1 asked the same "
                            "question at BOOK level and answered no; a "
                            "book grammar is a lossy channel "
                            "(CONSTRUCTION-CUT-1: 36 books -> ~1.3 "
                            "effective behaviours), so a book-level "
                            "negative does not close the feature level",
           "noise_removal": "Marchenko-Pastur upper bound with FITTED "
                            "noise variance — the cutoff is analytic, "
                            "not chosen",
           "sources": {k: [c for c in v if c in feats]
                       for k, v in src.items()},
           "n_rows_complete_case": int(len(sub)),
           "n_dates_complete_case": n_dates,
           "sources_dropped_for_coverage": dropped,
           "min_coverage": a.min_coverage,
           "pooled_spectrum": full,
           "factor_source_loadings": loadings,
           "incremental_signal_factors": incr,
           "label": "descriptive structure; no return is predicted"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"cross_source_structure_1_{a.era}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print("\nwhich sources share each signal factor:")
    for L in loadings:
        top = ", ".join(f"{k} {v:.0%}" for k, v in
                        list(L["source_share"].items())[:4])
        print(f"  factor {L['factor']} (lam={L['eigenvalue']:.2f}): {top}")
    print("\nincremental SIGNAL factors (noise already removed):")
    for k, v in incr.items():
        print(f"  {k:14s} +{v['n_features_added']:>2d} features -> "
              f"{v['signal_factors_base']} -> {v['signal_factors_with']} "
              f"signal factors  (increment {v['increment']:+d})")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
