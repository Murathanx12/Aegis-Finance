"""W4b -- re-run the graph-momentum screen on the edges COMPANYWORLD v1 bought.

WHAT CHANGED SINCE W4, AND WHAT DELIBERATELY DID NOT
====================================================
W4 (`learner/features_graph.py`, run by `scripts/weekend_lab_jobs.W4_graph_momentum`)
returned CANNOT DETERMINE, and the reason it gave was scope: MARKET-GRAPH-1's
edges live in 2014-05..2024-12 -- 11 of the long panel's 26 years -- over 386 of
8,981 names, so the join reached 2.08% of panel rows against a 4.4% ceiling. The
best arm (customer momentum, equal weight, FM t 1.45) needed 18.6 years of tape
and had 9.75.

This run adds edges from 10-K filings **1999-2013** -- the half of the panel the
graph had never seen -- extracted by `scripts/companyworld_extract.py` with the
SAME prompt, the same eight-type taxonomy, the same liveness rule and the same
resolver conservatism. The extraction question is unchanged on purpose: an edge
set built by a different procedure would not be poolable with the one W4 already
measured, and "we changed the years AND the method" is not a scope repair.

Three arms are reported, never one:

  * `companyworld_only` -- the new 1999-2013 edges alone. This is the clean
    out-of-sample test: no month of it overlaps the tape W4's t 1.45 came from.
  * `market_graph_1_only` -- W4's own edges, re-run here so the two numbers come
    out of the same code path on the same day.
  * `pooled` -- both, which is the widest cross-section and the one with the
    most years, and is therefore the arm most exposed to the multiplicity the
    inference block below prices.

THE FLOORS ARE IN THE TRAINING UNIVERSE, NOT ONLY AT GRADING
============================================================
`learner.evaluate.TRADABLE_DOLLAR_VOL` ($3m/day) and a $5 close are applied to
the panel BEFORE any monthly regression is fitted, not afterwards to the book.
A coefficient fitted on names that cannot be bought is a coefficient about a
different universe; W3's 698x-to-64.9x collapse is what that difference costs.

VERDICT VOCABULARY
==================
This is a FEATURE SCREEN. It has no book and no Sharpe to deflate, so **it
cannot reach NOVEL** -- NOVEL is reserved for something that survived a book, a
family and a deflation. `scripts/weekend_lab_jobs._normalise_screen_verdict`
makes the same correction to W4/W5/W6 and the reasoning is quoted there. The
strongest word available here is SCREEN SUPPORT.

    python -m scripts.w4_companyworld_rerun --variant 0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                              # noqa: BLE001
    pass

from learner import features_graph as FG                       # noqa: E402
from learner import inference                                  # noqa: E402
from learner import long_panel as LP                           # noqa: E402
from learner.evaluate import TRADABLE_DOLLAR_VOL               # noqa: E402

CW_EDGES = REPO / "backend" / "data" / "optimus" / "graph" / "companyworld_v1.parquet"
RECEIPT_DIR = REPO / "backend" / "data" / "optimus" / "continuation_2026-09-06"
POOLED = REPO / "backend" / "data" / "optimus" / "graph" / "companyworld_pooled_tmp.parquet"

PRICE_FLOOR = 5.0
MIN_ROWS = getattr(FG, "MIN_ROWS", 5000)
MIN_MONTHS = getattr(FG, "MIN_MONTHS", 24)
MIN_NAMES = getattr(FG, "MIN_NAMES_PER_MONTH", 30)


def tradable_panel() -> tuple[pd.DataFrame, dict]:
    """The long panel with the HOUSE FLOORS applied to the training universe."""
    df = LP.load_long()
    n0 = len(df)
    dv = np.exp(df["log_dollar_vol_20d"]) - 1.0 if "log_dollar_vol_20d" in df.columns else None
    if dv is None:
        raise SystemExit("REFUSED: the long panel has no log_dollar_vol_20d, so "
                         "the $3m/day floor cannot be applied to the TRAINING "
                         "universe. Refusing rather than grading on a universe "
                         "the floor never touched.")
    keep = (dv >= TRADABLE_DOLLAR_VOL) & (df["close"] >= PRICE_FLOOR)
    out = df[keep.fillna(False)].copy()
    return out, {
        "rule": f"dollar_vol_20d >= ${TRADABLE_DOLLAR_VOL:,.0f}/day AND close >= ${PRICE_FLOOR}",
        "applied_to": "the TRAINING universe, before any monthly regression",
        "rows_before": int(n0), "rows_after": int(len(out)),
        "share_kept": round(len(out) / max(n0, 1), 4),
        "names_before": int(df["permno"].nunique()),
        "names_after": int(out["permno"].nunique()),
    }


def build_features(edges_path: Path, tag: str) -> tuple[pd.DataFrame, dict]:
    feats, rec = FG.build(edges_path=edges_path, verbose=False)
    rec["arm"] = tag
    return feats, rec


def pooled_edges() -> Path | None:
    """companyworld_v1 + MARKET-GRAPH-1, if the latter is on this machine.

    Absence of a local object is not evidence of absence (CLAUDE.md): if the
    sibling repo's parquet is not here the pooled arm is REFUSED by name, not
    silently reduced to the new edges alone -- which would produce a "pooled"
    row that is a copy of another row and read as agreement.
    """
    src = FG.DEFAULT_EDGE_SOURCE
    if not src.exists():
        return None
    a = pd.read_parquet(CW_EDGES)
    b = pd.read_parquet(src)
    cols = list(FG.EDGE_COLUMNS)
    out = pd.concat([a[cols], b[cols]], ignore_index=True).drop_duplicates()
    out.to_parquet(POOLED, index=False)
    return POOLED


def screen(feats: pd.DataFrame, panel: pd.DataFrame, variant: int) -> dict:
    """The W4 regression, with the panel already floored. Same shape as
    `features_graph.job` -- rank IC AND the controlled Fama-MacBeth t, because
    the raw IC of a graph feature is mostly the controls."""
    df, join_note = FG.attach(panel.copy(), feats)
    ret = "excess_vw_3m" if variant == 2 else "excess_vw_1m"
    base = ["mom_12_1", "log_market_cap", "vol_60d"]
    if variant == 1:
        df["_sector_mom_1m"] = FG._sector_momentum(df)
        base = base + ["ret_1m", "_sector_mom_1m"]
    have = [c for c in base if c in df.columns]
    from scripts.weekend_lab_jobs import era_sign_table

    rows, series = [], {}
    for feat in FG.FEATURES:
        d = df[["month", feat, ret, *have]].dropna()
        if len(d) < MIN_ROWS:
            rows.append({"feature": feat, "family": FG.family_of(feat),
                         "verdict": "CANNOT DETERMINE", "rows": int(len(d)),
                         "why": f"fewer than {MIN_ROWS:,} usable rows AFTER the floors"})
            continue
        ics, betas, months, names = [], [], [], []
        for m, g in d.groupby("month", sort=True):
            if len(g) < MIN_NAMES:
                continue
            ics.append(float(g[feat].rank().corr(g[ret].rank())))
            betas.append(FG._fm_month(g, feat, ret, have))
            months.append(str(m))
            names.append(int(len(g)))
        if len(ics) < MIN_MONTHS:
            rows.append({"feature": feat, "family": FG.family_of(feat),
                         "verdict": "CANNOT DETERMINE", "rows": int(len(d)),
                         "months": len(ics),
                         "why": f"fewer than {MIN_MONTHS} months with {MIN_NAMES}+ names"})
            continue
        ic = pd.Series(ics, index=months)
        be = pd.Series(betas, index=months, dtype="float64")
        series[feat] = be
        rows.append({
            "feature": feat, "family": FG.family_of(feat),
            "rows": int(len(d)), "months": int(len(ic)),
            "median_names_per_month": int(np.median(names)),
            "mean_rank_ic": round(float(ic.mean()), 5),
            "t_rank_ic": (round(FG._t(ic), 3) if FG._t(ic) is not None else None),
            "mean_fm_beta_controlled": round(float(be.mean(skipna=True)), 8),
            "t_fm_beta_controlled": (round(FG._t(be), 3) if FG._t(be) is not None else None),
            "controls": have,
            "era_sign_table": era_sign_table(be),
            "power": inference.power_note(be.dropna().tolist()),
        })
    return {"rows": rows, "series": series, "join": join_note, "target": ret,
            "controls": have}


def inference_block(rows: list[dict], series: dict) -> dict:
    """Family size, family-max p, DSR, SPA, PBO, MDE -- on the SAME family.

    The monthly FM-beta series is treated as the arm's return stream. That is
    what it is: a monthly number whose mean over months is the estimate and
    whose t is the claim. Every feature in the family goes into the family, so
    the deflation prices the whole search and not the survivor.
    """
    fam = {k: v.dropna().tolist() for k, v in series.items() if v.notna().sum() >= 24}
    if not fam:
        return {"verdict": "CANNOT DETERMINE",
                "why": "no feature produced 24+ usable monthly betas"}
    ts = {r["feature"]: r["t_fm_beta_controlled"] for r in rows
          if r.get("t_fm_beta_controlled") is not None}
    if not ts:
        return {"verdict": "CANNOT DETERMINE", "why": "no feature produced a t"}
    best = max(ts, key=lambda k: abs(ts[k]))
    # Two-sided normal p on the family-max |t|, then Sidak over the family.
    from math import erfc, sqrt
    p_raw = erfc(abs(ts[best]) / sqrt(2.0))
    n_fam = len(ts)
    p_fam = 1.0 - (1.0 - p_raw) ** n_fam
    # Equal-length family => PBO is computable; SPA against a zero benchmark
    # (the null that the neighbourhood adds nothing over the controls).
    L = min(len(v) for v in fam.values())
    fam_eq = {k: v[-L:] for k, v in fam.items()}
    paired = {k: v for k, v in fam_eq.items()}
    rep = inference.full_report(fam_eq[best], family=fam_eq, paired_excess=paired,
                                n_trials=n_fam, periods_per_year=12, seed=20260906)
    return {
        "family_id": "W4b-companyworld-graph-momentum",
        "family_size": n_fam,
        "family_members": sorted(ts),
        "family_max_t_feature": best,
        "family_max_t": ts[best],
        "p_raw_two_sided": round(p_raw, 6),
        "p_family_max_sidak": round(p_fam, 6),
        "deflated_sharpe": rep.get("deflated_sharpe"),
        "spa": rep.get("spa"),
        "pbo": rep.get("pbo"),
        "mde_power": rep.get("power"),
        "note": ("the arm's 'returns' are its monthly Fama-MacBeth betas, which "
                 "is the object whose t is being claimed. It is NOT a book: no "
                 "position was taken, no cost was paid, and W5b is the standing "
                 "demonstration that an FM t of 4.15 can lose money gross."),
    }


def verdict_for(rows: list[dict], inf: dict) -> tuple[str, list]:
    tested = [r for r in rows if r.get("t_fm_beta_controlled") is not None]
    survivors = [r for r in tested
                 if abs(r["t_fm_beta_controlled"]) >= 2.0
                 and (r.get("era_sign_table") or {}).get("same_sign_in_2_of_3")]
    underpowered = [r for r in tested if (r.get("power") or {}).get("powered") is False]
    if not tested:
        return "CANNOT DETERMINE (coverage)", survivors
    if survivors:
        # A SCREEN CANNOT REACH NOVEL. The family correction decides whether the
        # survivor is a result or the best of n draws.
        pf = inf.get("p_family_max_sidak")
        if pf is not None and pf < 0.05:
            return "SCREEN SUPPORT (family-corrected)", survivors
        return "SCREEN SUPPORT (uncorrected only -- family-max p >= 0.05)", survivors
    if len(underpowered) == len(tested):
        return "CANNOT DETERMINE (underpowered)", survivors
    return "NOISE", survivors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", type=int, default=0)
    ap.add_argument("--tag", default="run01")
    a = ap.parse_args(argv)
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    if not CW_EDGES.exists():
        out = {"job": "W4b_companyworld_rerun", "verdict": "REFUSED",
               "why": f"no edge file at {CW_EDGES} -- run scripts/companyworld_extract.py first"}
        p = RECEIPT_DIR / f"W4b_companyworld_rerun_{a.tag}.json"
        p.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2))
        return 1

    panel, floor_note = tradable_panel()
    print(f"panel after floors: {len(panel):,} rows, "
          f"{panel['permno'].nunique():,} names", flush=True)

    arms = {"companyworld_only": CW_EDGES}
    src = FG.DEFAULT_EDGE_SOURCE
    if src.exists():
        arms["market_graph_1_only"] = src
        pp = pooled_edges()
        if pp is not None:
            arms["pooled"] = pp
    else:
        arms["market_graph_1_only"] = None
        arms["pooled"] = None

    results = {}
    for name, path in arms.items():
        if path is None:
            results[name] = {"verdict": "REFUSED",
                             "why": (f"MARKET-GRAPH-1's edge parquet is not on this "
                                     f"machine ({src}); this arm is refused by name "
                                     "rather than silently replaced by the new edges")}
            continue
        try:
            feats, rec = build_features(Path(path), name)
            sc = screen(feats, panel, a.variant)
            inf = inference_block(sc["rows"], sc["series"])
            vd, surv = verdict_for(sc["rows"], inf)
            cov = rec.get("coverage") or {}
            results[name] = {
                "verdict": vd,
                "scope": (f"{cov.get('feature_years')} of {cov.get('long_panel_years')} "
                          f"panel years ({cov.get('feature_date_first')}.."
                          f"{cov.get('feature_date_last')}), {rec.get('permnos')} graph "
                          f"names of {panel['permno'].nunique():,} floored-panel names"),
                "graph_receipt": {k: rec.get(k) for k in
                                  ("source", "source_rows", "max_age_days",
                                   "relations", "coverage", "permnos")},
                "join": sc["join"], "target": sc["target"], "controls": sc["controls"],
                "features": sc["rows"],
                "survivors_t2_and_same_sign_2of3_eras": [
                    {"feature": r["feature"], "t": r["t_fm_beta_controlled"],
                     "sign": (r.get("era_sign_table") or {}).get("dominant_sign")}
                    for r in surv],
                "inference": inf,
            }
        except SystemExit as exc:
            results[name] = {"verdict": "REFUSED", "why": str(exc)}
        except Exception as exc:                               # noqa: BLE001
            results[name] = {"verdict": "REFUSED",
                             "why": f"{type(exc).__name__}: {exc}"}
        print(f"  {name}: {results[name].get('verdict')}", flush=True)

    receipt = {
        "job": "W4b_companyworld_rerun",
        "question": ("does a name's customers'/suppliers'/competitors' last month "
                     "predict its next one, once its own momentum, size and vol are "
                     "in the same regression -- on a graph that now reaches 1999?"),
        "family_id": "W4b-companyworld-graph-momentum",
        "licence": "PRODUCT_EXPERIMENT",
        "ts_utc": pd.Timestamp.utcnow().isoformat(),
        "variant": a.variant,
        "training_universe_floors": floor_note,
        "verdict_vocabulary_note": (
            "This is a FEATURE SCREEN: no book, no Sharpe to deflate, so it CANNOT "
            "reach NOVEL. NOVEL is reserved for something that survived a book, a "
            "family and a deflation -- see weekend_lab_jobs._normalise_screen_verdict "
            "and W5b, where two options coefficients with FM t 4.15 and -5.37 built "
            "24 book cells that all lost GROSS."),
        "arms": results,
        "wall_seconds": round(time.time() - t0, 1),
    }
    p = RECEIPT_DIR / f"W4b_companyworld_rerun_{a.tag}.json"
    p.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(f"receipt -> {p}", flush=True)
    for k, v in results.items():
        print(f"{k:24s} {v.get('verdict')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
