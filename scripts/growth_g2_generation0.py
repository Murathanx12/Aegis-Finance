"""G2 — GENERATION 0 OF THE GROWTH BOOK, ON THE DEVELOPMENT ERA ONLY.

`docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §3, item G2.

WHAT THIS JOB DOES, IN ORDER, AND WHY THE ORDER IS THE POINT
===========================================================
1. Builds the panel and the market context. NOTHING is evaluated yet.
2. Writes `DECLARATION.json` — objective, constraints, benchmark set, the
   development/sealed split, and the full generation-0 genome list — and hashes
   it. **Before the first evaluation.** A family size recorded after the search
   is the family that survived, not the family that was opened, and the DSR
   deflation is only honest against the second one.
3. Evaluates every genome at 10 and 25 bps on the DEVELOPMENT window only.
   `learner.growth_lab.assert_development_only` raises if any series reaches
   2016; the sealed era is opened once, by G4, through the append-only ledger.
4. Ranks by leverage-neutral terminal wealth, prints beta first, and reports
   the raw p, the family-corrected p and the DSR **separately** so the verdict
   can name which bar failed rather than collapsing three questions into the
   word NOISE.

THE DATA, AND WHY IT IS NOT REFITTED HERE
=========================================
The two learner genomes read the W3b stage parquets — walk-forward OOS
predictions over the floored long panel, universe fingerprint `616fa0a5…`,
test years 2004-2024, produced 2026-09-05. Refitting them here would be a
different experiment wearing the same name (`w3_neural_floored._read_stage`
refuses a fingerprint or scope mismatch, and this job checks the same two
things). **A prediction is not an evaluation:** the stages carry 2016-2024
rows, and this job never grades them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP        # noqa: E402
from learner import growth as GR                             # noqa: E402
from learner import growth_lab as GL                         # noqa: E402

OUT_DIR = GL.OUT_DIR
FINRATIO = REPO / "backend" / "data" / "optimus" / "wrds" / "finratio_monthly.parquet"
FINRATIO_EARLY = REPO / "backend" / "data" / "optimus" / "wrds" / "finratio_monthly_early.parquet"

SERIES_CACHE = OUT_DIR / "G2_genome_series.parquet"


def _r(v, nd=5):
    try:
        f = float(v)
        return round(f, nd) if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_sided_p(t: float | None) -> float | None:
    if t is None or not math.isfinite(t):
        return None
    return round(2.0 * (1.0 - _ncdf(abs(float(t)))), 6)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p, in the order the family was declared."""
    items = sorted(((k, v) for k, v in pvals.items() if v is not None),
                   key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        run = max(run, adj)
        out[k] = round(run, 6)
    for k, v in pvals.items():
        if v is None:
            out[k] = None
    return out


def bh_fdr(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(((k, v) for k, v in pvals.items() if v is not None),
                   key=lambda kv: kv[1])
    m, out = len(items), {}
    prev = 1.0
    for i in range(m - 1, -1, -1):
        k, p = items[i]
        adj = min(prev, p * m / (i + 1))
        out[k] = round(adj, 6)
        prev = adj
    for k, v in pvals.items():
        if v is None:
            out[k] = None
    return out


# ----------------------------------------------------------------- the panel

def load_panel(tracker: RP.InputTracker, verbose: bool = True):
    """The FLOORED long panel plus the W3b stage predictions, joined by row.

    The floor is `neural_long.tradable_universe` — $3m/day and close >= $5 —
    applied to the TRAINING universe, which is what the stage predictions were
    fitted on. Grading them against a differently floored population would
    average two populations; `universe_fingerprint` is checked, not assumed.
    """
    from learner import long_panel as LP
    from scripts import w3_neural_floored as W3B

    tracker.opened(LP.LONG_TABLE, note="the 1999-2024 long panel")
    df, uni, fp = W3B.load_universe(verbose=verbose)
    # DO NOT reset this index. `_write_stage` stores `_row` = the ORIGINAL panel
    # index label of each floored row, and `w3_neural_floored.run` joins on it by
    # LABEL. The first version of this loader called `reset_index(drop=True)` and
    # then `reindex(range(len(df)))`, which matched labels 0..530,446 against
    # panel labels 0..925,756 -- 57.3% of them exist (exactly the floor's
    # share_kept) so every column came back looking populated while sitting on
    # the WRONG ROWS, and the 2002-2003 predictions it produced are dated before
    # the first test year of the fit that produced them. That is the tell, and it
    # is the only tell: nothing else about the run looked wrong.

    scope = {"test_years": [2004, 2024], "n_test_years": 21,
             "seeds": [20260906 + i for i in range(8)]}
    stages = {}
    for tag, want in (("incumbents", {k: v for k, v in scope.items() if k != "seeds"}),
                      ("nn_pre_causal", scope)):
        path = W3B._stage_path(tag)
        meta_path = W3B.STAGE_DIR / f"w3b_meta_{tag}.json"
        if not path.exists() or not meta_path.exists():
            raise SystemExit(
                f"REFUSED: the W3b stage {tag!r} is not on disk ({path}). The "
                "learner genomes read walk-forward OOS predictions that already "
                "exist; this job does not refit them, and a genome silently "
                "dropped from the family would change the DSR deflation.")
        tracker.opened(path, note=f"W3b stage predictions: {tag}")
        tracker.opened(meta_path, note=f"W3b stage meta: {tag}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("universe_fingerprint_sha256") != fp:
            raise SystemExit(
                f"REFUSED: stage {tag!r} was fitted on universe "
                f"{str(meta.get('universe_fingerprint_sha256'))[:16]} and this job "
                f"grades {fp[:16]}.")
        got = dict(meta.get("scope") or {})
        if tag == "incumbents":
            got.pop("seeds", None)
        if got != want:
            raise SystemExit(
                f"REFUSED: stage {tag!r} scope {got} != {want}.")
        d = pd.read_parquet(path).set_index("_row")
        if not df.index.isin(d.index).all():
            missing = int((~df.index.isin(d.index)).sum())
            raise SystemExit(
                f"REFUSED: stage {tag!r} covers {len(d):,} rows and the floored "
                f"panel has {len(df):,}, of which {missing:,} carry no stage row. "
                "The stage and the panel are not the same population; a join that "
                "silently NaNs them would grade a different universe.")
        for c in meta["columns"]:
            df[c] = d[c]                       # LABEL-aligned. See the note above.
        cov = {c: float(df[c].notna().mean()) for c in meta["columns"][:1]}
        first_year = df.loc[df[meta["columns"][0]].notna(), "month"].astype(str).min()[:4]
        if int(first_year) < 2004:
            raise SystemExit(
                f"REFUSED: stage {tag!r} has a non-null prediction in {first_year}, "
                "before the 2004 first test year of the fit that produced it. "
                "That is a row-alignment failure, not an early prediction.")
        stages[tag] = {"path": str(path), "columns": list(meta["columns"]),
                       "non_null_share_first_column": round(cov[meta["columns"][0]], 4),
                       "first_year_with_a_prediction": first_year,
                       "rows": int(meta["rows"]),
                       "universe_fingerprint_sha256": meta["universe_fingerprint_sha256"],
                       "scope": meta.get("scope")}

    # ---- derived signal columns, both cross-sectional and both PIT.
    df["month"] = df["month"].astype(str)
    v = df["vol_60d"].to_numpy(dtype="float64")
    df["mom_over_vol"] = np.where(np.isfinite(v) & (v > 0),
                                  df["mom_12_1"].to_numpy(dtype="float64") / v, np.nan)

    roe = _load_roe(tracker)
    df = _attach_quality(df, roe)
    q = df.groupby("month")["roe_pit"].rank(pct=True)
    m = df.groupby("month")["mom_12_1"].rank(pct=True)
    df["quality_mom"] = (q + m) / 2.0

    uni["stages"] = stages
    uni["quality_coverage_share"] = round(float(df["roe_pit"].notna().mean()), 4)
    uni["quality_mom_coverage_share"] = round(float(df["quality_mom"].notna().mean()), 4)
    return df, uni, fp


def _load_roe(tracker: RP.InputTracker) -> pd.DataFrame:
    """ROE from WRDS `wrdsapps_finratio`, early + modern, on `public_date`.

    `gprof` (gross profitability, the Novy-Marx quantity the amendment's
    "profitability" would prefer) exists only from 2013-01 in this repo's pull —
    it is absent for two thirds of the development era — so the quality leg is
    ROE, which runs 1990-2024 in both files. That substitution is DECLARED here
    and printed in the receipt rather than made silently: a quality genome
    graded on a column that is empty before 2013 is a momentum genome.
    """
    frames = []
    for p in (FINRATIO_EARLY, FINRATIO):
        if not p.exists():
            raise SystemExit(f"REFUSED: {p} is missing; the quality genome has no "
                             "profitability leg and would silently become momentum.")
        tracker.opened(p, note="WRDS wrdsapps_finratio, ROE leg")
        d = pd.read_parquet(p, columns=["permno", "public_date", "roe"])
        frames.append(d)
    r = pd.concat(frames, ignore_index=True)
    r = r.dropna(subset=["permno", "public_date"])
    r["permno"] = r["permno"].astype("int64")
    r["public_date"] = pd.to_datetime(r["public_date"])
    r = r.dropna(subset=["roe"]).sort_values("public_date")
    return r


def _attach_quality(df: pd.DataFrame, roe: pd.DataFrame) -> pd.DataFrame:
    """As-of merge: the latest ROE whose `public_date` is on or before entry.

    `public_date` IS the availability date in the WRDS financial-ratios suite,
    so no extra lag is added — and that choice is stated rather than assumed.
    """
    left = df[["permno", "entry_date"]].copy()
    left["permno"] = left["permno"].astype("int64")
    left["entry_date"] = pd.to_datetime(left["entry_date"])
    left["_i"] = np.arange(len(left))
    left = left.sort_values("entry_date")
    merged = pd.merge_asof(left, roe.rename(columns={"public_date": "entry_date"}),
                           on="entry_date", by="permno", direction="backward")
    out = merged.sort_values("_i")["roe"].to_numpy()
    df = df.copy()
    df["roe_pit"] = out
    return df


# ----------------------------------------------------------- genome building

def build_all(genomes, panel: pd.DataFrame, ctx: pd.DataFrame,
              cost_bps: float, verbose: bool = True):
    """Every genome's monthly net series at ONE cost rate. Full history.

    The series are built over the whole tape and sliced afterwards. Every
    overlay here is backward-looking (a trailing drawdown, an expanding median,
    a moving average read at entry), so the development values of a full-tape
    build are identical to those of a development-only build — and building
    once means the sealed era is computed by the same code path that G4 opens,
    rather than by a second one written months later.
    """
    base_series: dict[str, pd.Series] = {}
    metas: dict[str, dict] = {}
    for g in genomes:
        if g.base == "blend":
            continue
        key = f"{g.base}|{json.dumps(g.spec, sort_keys=True)}"
        if key not in base_series:
            if g.base.startswith("spy_"):
                s, m = GL.build_spy_base(g.base, ctx, g.spec, cost_bps=cost_bps)
            else:
                s, m = GL.build_panel_base(g.base, panel, g.spec, cost_bps=cost_bps)
            base_series[key] = s
            metas[key] = m
        s, m = base_series[key], metas[key]
        if g.overlay:
            s, om = GL.apply_overlays(s, ctx, g.overlay, cost_bps=cost_bps)
            m = {**m, "overlay_meta": om}
        yield g, s, m

    # blends read the finished base series by genome id
    by_id = {}
    for g in genomes:
        if g.base == "blend":
            continue
        key = f"{g.base}|{json.dumps(g.spec, sort_keys=True)}"
        if not g.overlay:
            by_id[g.genome_id] = base_series[key]
        else:
            by_id[g.genome_id] = GL.apply_overlays(
                base_series[key], ctx, g.overlay, cost_bps=cost_bps)[0]
    for g in genomes:
        if g.base != "blend":
            continue
        legs = [(by_id[lid], float(w)) for lid, w in g.spec["legs"]]
        s = GL.build_blend(legs)
        yield g, s, {"rule": "50/50 return blend",
                     "legs": [[lid, float(w)] for lid, w in g.spec["legs"]]}


# ---------------------------------------------------------------- the verdict

def verdict_naming_the_bar(raw_p, holm_p, dsr, constraints_pass, pbo_val) -> str:
    """Three bars, named separately. B1's `verdict_from` collapses them.

    The Labor Day lab's B1 lane found that a real planted edge at Holm p 0.0154
    was called NOISE because there is no word for "significant, did not clear
    the deflation bar". A growth verdict names the bar that failed.
    """
    bars = []
    if not constraints_pass:
        bars.append("CONSTRAINTS")
    if raw_p is None:
        bars.append("RAW_P_UNAVAILABLE")
    elif raw_p >= 0.05:
        bars.append("RAW_P")
    if holm_p is not None and holm_p >= 0.05:
        bars.append("FAMILY_HOLM")
    if dsr is not None and dsr < 0.95:
        bars.append("DSR_DEFLATION")
    if pbo_val is not None and pbo_val >= 0.5:
        bars.append("PBO")
    if not bars:
        return "CLEARS_EVERY_BAR"
    return "FAILS: " + "+".join(bars)


# --------------------------------------------------------------------- run

def run(*, verbose: bool = True, argv=None) -> dict:
    t0 = datetime.now(timezone.utc)
    tracker = RP.InputTracker()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    from scripts import w3_neural_floored as W3B
    free = W3B.free_gb()
    if free is not None and free < 6.0:
        raise SystemExit(f"REFUSED: {free:.1f} GB free, floor 6.0 GB. "
                         "Runner or standalone job, never both.")

    panel, uni, fp = load_panel(tracker, verbose=verbose)
    ctx = GL.market_context(panel, tracker)
    genomes = GL.generation_zero()

    # ---- THE DECLARATION, WRITTEN AND HASHED BEFORE THE FIRST EVALUATION ----
    decl = GL.declaration(genomes, extra={
        "universe": {k: v for k, v in uni.items() if k != "stages"},
        "universe_fingerprint_sha256": fp,
        "stage_sources": uni["stages"],
        "quality_leg": {
            "column": "roe_pit",
            "source": "WRDS wrdsapps_finratio (early 1990-2012 + modern 2013-2024)",
            "why_not_gprof": ("gross profitability exists only from 2013-01 in this "
                              "repo's pull and is absent for two thirds of the "
                              "development era"),
            "coverage_share_of_panel_rows": uni["quality_coverage_share"],
        },
        "market_context": {
            "months": int(len(ctx)),
            "window": [str(ctx.index[0]), str(ctx.index[-1])],
            "construction": ("each market leg compounded over the book month's OWN "
                             "window (entry_date[m], entry_date[m+1]] from the "
                             "pinned daily tapes"),
            "spy_tape_sha256": json.loads(GL.SPY_META.read_text(encoding="utf-8"))["sha256"]
            if GL.SPY_META.exists() else None,
        },
    })
    decl["family_cells_declared"] = len(genomes) * len(GL.COST_RATES_BPS)
    sha = GL.declaration_sha256(decl)
    decl["sha256"] = sha
    RP.attach(decl, argv or sys.argv, {"job": "G2_generation0"}, tracker)
    GL.DECLARATION.write_text(json.dumps(decl, indent=1, default=str), encoding="utf-8")
    if verbose:
        print(f"DECLARATION written and hashed BEFORE the first evaluation: "
              f"{sha[:16]}  ({len(genomes)} genomes x {len(GL.COST_RATES_BPS)} cost "
              f"rates = {decl['family_cells_declared']} cells)", flush=True)

    # ---------------------------------------------------------- evaluate ----
    cells: dict[str, dict] = {}
    series_dev: dict[str, pd.Series] = {}
    series_full: dict[str, pd.Series] = {}
    spy_dev = GL.dev(ctx["spy"].dropna())
    rf_dev = GL.dev(ctx["rf"].dropna())
    GL.assert_development_only(spy_dev, "the SPY leg")

    for bps in GL.COST_RATES_BPS:
        for g, s, meta in build_all(genomes, panel, ctx, bps, verbose=verbose):
            s = pd.Series(s.to_numpy(), index=pd.Index([str(x) for x in s.index]))
            s = s.dropna().sort_index()
            series_full[f"{g.genome_id}|{bps:.0f}bps"] = s
            d = GL.dev(s)
            GL.assert_development_only(d, f"genome {g.genome_id}")
            if len(d) < 24:
                cells[f"{g.genome_id}|{bps:.0f}bps"] = {
                    "genome": g.to_json(), "cost_bps_per_side": bps,
                    "verdict": "CANNOT DETERMINE",
                    "why": f"only {len(d)} development months"}
                continue
            ev = GR.evaluate_growth(d, spy_dev, rf_dev, cost_bps=bps,
                                    label=f"{g.genome_id}|{bps:.0f}bps",
                                    n_boot=1000)
            ev["genome"] = g.to_json()
            ev["build"] = {k: v for k, v in meta.items() if k != "_series"}
            cells[f"{g.genome_id}|{bps:.0f}bps"] = ev
            series_dev[f"{g.genome_id}|{bps:.0f}bps"] = d
            if verbose:
                print(f"  {g.genome_id:38s} {bps:5.0f}bps  "
                      f"beta {str(ev.get('beta')):>7s}  "
                      f"LN-TW {str((ev.get('leverage_neutral') or {}).get('terminal_wealth')):>8s}  "
                      f"TW {str((ev.get('book') or {}).get('terminal_wealth')):>8s}",
                      flush=True)

    # cache the full series so G3/G4/G5 do not rebuild (and cannot rebuild
    # differently). The SEALED months live here and are not graded.
    idx = sorted({m for s in series_full.values() for m in s.index})
    pd.DataFrame({k: s.reindex(idx) for k, s in series_full.items()},
                 index=pd.Index(idx, name="month")).to_parquet(SERIES_CACHE)

    # ------------------------------------------------ family-level statistics
    from learner import inference as INF

    graded = {k: v for k, v in cells.items() if v.get("beta") is not None}
    raw_p = {k: two_sided_p((v.get("market_model") or {}).get("intercept_t_hac"))
             for k, v in graded.items()}
    holm_p = holm(raw_p)
    fdr_p = bh_fdr(raw_p)

    common = None
    for k in sorted(graded):
        i = pd.Index(series_dev[k].index)
        common = i if common is None else common.intersection(i)
    M = np.column_stack([series_dev[k].reindex(common).to_numpy()
                         for k in sorted(graded)])
    pbo_all = INF.pbo(M, n_splits=8)
    splits = INF.cpcv_splits(len(common), n_groups=6, k_test=2)
    cpcv = _cpcv_rank_stability(M, sorted(graded), splits)

    n_trials = decl["family_cells_declared"]
    for k, v in graded.items():
        excess = (series_dev[k] - spy_dev.reindex(series_dev[k].index)).dropna()
        d = INF.deflated_sharpe(excess.to_numpy(), n_trials=n_trials)
        v["significance"] = {
            "raw_p_intercept_hac": raw_p[k],
            "family_holm_p": holm_p.get(k),
            "family_bh_fdr_p": fdr_p.get(k),
            "dsr_over_family": d.get("dsr"),
            "dsr_block": d,
            "family_size_cells": n_trials,
            "pbo_family": pbo_all.get("pbo"),
            "note": ("three bars, printed separately: the raw HAC t on the "
                     "intercept, the family correction over every cell declared, "
                     "and the deflated Sharpe. A single word cannot say which "
                     "one failed."),
        }
        v["verdict_growth"] = verdict_naming_the_bar(
            raw_p[k], holm_p.get(k), d.get("dsr"),
            bool((v.get("constraints") or {}).get("passes")), pbo_all.get("pbo"))

    board = leaderboard(graded)

    out = {
        "job": "G2_generation0",
        "lane": "G growth book",
        "licence": "PRODUCT_EXPERIMENT",
        "question": ("under the PRODUCT ruler — after-cost terminal wealth at a "
                     "declared drawdown budget with beta reported first — which "
                     "generation-0 genome leads on the DEVELOPMENT era?"),
        "declaration_sha256": sha,
        "declaration_path": str(GL.DECLARATION),
        "sealed_era_openings": len(GL.sealed_openings()),
        "sealed_era_touched_by_this_job": False,
        "development_window": [GL.COMMON_DEV_START, GL.DEV_END],
        "development_months": int(len(common)),
        "llm_spend_usd": 0.0,
        "llm_calls": 0,
        "network_calls": 0,
        "memory_free_gb_before": free,
        "universe": {k: v for k, v in uni.items() if k != "stages"},
        "universe_fingerprint_sha256": fp,
        "family_cells_declared": n_trials,
        "family_cells_graded": len(graded),
        "family_raw_p_min": min([p for p in raw_p.values() if p is not None], default=None),
        "family_raw_p_max": max([p for p in raw_p.values() if p is not None], default=None),
        "family_holm_best": min([p for p in holm_p.values() if p is not None], default=None),
        "family_bh_fdr_best": min([p for p in fdr_p.values() if p is not None], default=None),
        "family_survivors_holm_0_05": [k for k, p in holm_p.items()
                                       if p is not None and p < 0.05],
        "pbo_over_the_whole_family": pbo_all,
        "cpcv_rank_stability": cpcv,
        "leaderboard_by_leverage_neutral_tw": board,
        "cells": cells,
        "series_cache": str(SERIES_CACHE),
        "wall_seconds": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    top = board[0] if board else {}
    out["headline"] = (
        f"beta {top.get('beta')}: {top.get('cell')} leads generation 0 on "
        f"{out['development_months']} development months with leverage-neutral "
        f"TW {top.get('leverage_neutral_tw')} vs SPY {top.get('spy_tw')} "
        f"(raw TW {top.get('raw_tw')}, maxDD {top.get('max_drawdown')} vs budget "
        f"{top.get('maxdd_budget')}); family {n_trials} cells, "
        f"PBO {pbo_all.get('pbo')}, best Holm {out['family_holm_best']}"
        if top else "no genome produced a gradeable development series")
    RP.attach(out, argv or sys.argv,
              {"job": "G2_generation0", "cost_rates_bps": list(GL.COST_RATES_BPS),
               "development_window": [GL.COMMON_DEV_START, GL.DEV_END]}, tracker)
    (OUT_DIR / "G2_generation0.json").write_text(
        json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def _cpcv_rank_stability(M: np.ndarray, names: list[str], splits) -> dict:
    """How often the in-sample champion is still top-quartile out of sample.

    PBO answers "is the top row a coin flip". This answers the softer question
    a leaderboard reader actually has: across 15 purged partitions, which cells
    keep appearing at the top, and does the full-sample champion appear there.
    """
    if not splits:
        return {"verdict": "CANNOT DETERMINE (no CPCV splits)"}
    wins: dict[str, int] = {n: 0 for n in names}
    champ_oos_rank = []
    for tr, te in splits:
        def sr(idx, j):
            a = M[idx, j]
            a = a[np.isfinite(a)]
            if a.size < 3 or a.std(ddof=1) == 0:
                return np.nan
            return float(a.mean() / a.std(ddof=1))
        is_sr = np.array([sr(tr, j) for j in range(M.shape[1])])
        oos_sr = np.array([sr(te, j) for j in range(M.shape[1])])
        if not np.isfinite(is_sr).any():
            continue
        c = int(np.nanargmax(is_sr))
        wins[names[c]] += 1
        fin = np.isfinite(oos_sr)
        if fin[c]:
            champ_oos_rank.append(
                float((oos_sr[fin] < oos_sr[c]).sum()) / max(1, fin.sum() - 1))
    top = sorted(wins.items(), key=lambda kv: -kv[1])[:8]
    return {
        "n_partitions": len(splits),
        "in_sample_champion_counts_top8": {k: v for k, v in top if v},
        "median_oos_percentile_of_the_is_champion":
            round(float(np.median(champ_oos_rank)), 4) if champ_oos_rank else None,
        "reading": ("1.0 means the in-sample champion was also the best out of "
                    "sample; 0.5 is the median of the field."),
    }


def _first(d, *keys):
    d = d or {}
    for k in keys:
        if d.get(k) is not None:
            return d[k]
    return None


def leaderboard(graded: dict) -> list[dict]:
    rows = []
    for k, v in graded.items():
        ln = v.get("leverage_neutral") or {}
        adm = v.get("largest_admissible") or {}
        rows.append({
            "cell": k,
            "beta": v.get("beta"),
            "intercept_annual_pct": (v.get("market_model") or {}).get("intercept_annualised_pct"),
            "intercept_t_hac": (v.get("market_model") or {}).get("intercept_t_hac"),
            "leverage_neutral_tw": ln.get("terminal_wealth"),
            "leverage_neutral_scale": ln.get("scale"),
            "raw_tw": (v.get("book") or {}).get("terminal_wealth"),
            "spy_tw": (v.get("spy") or {}).get("terminal_wealth"),
            "max_drawdown": (v.get("book") or {}).get("max_drawdown"),
            "maxdd_budget": (v.get("constraints") or {}).get("maxdd_budget"),
            "constraints_pass": (v.get("constraints") or {}).get("passes"),
            "admissible_leverage": adm.get("leverage"),
            "tw_at_admissible_leverage": adm.get("terminal_wealth"),
            "p_ruin": (v.get("p_ruin") or {}).get("p_ruin"),
            # READ EITHER KEY. G3 enlarges the family and names its columns
            # accordingly (`..._over_gen0_plus_children`, `dsr_over_enlarged_
            # family`); a reader that only knew G2's names printed None for
            # every child and the leaderboard's DSR column silently emptied.
            "raw_p": (v.get("significance") or {}).get("raw_p_intercept_hac"),
            "family_holm_p": _first(v.get("significance"), "family_holm_p",
                                    "family_holm_p_over_gen0_plus_children"),
            "dsr": _first(v.get("significance"), "dsr_over_family",
                          "dsr_over_enlarged_family"),
            "verdict": v.get("verdict_growth"),
            "months": v.get("months"),
        })
    rows.sort(key=lambda r: (r["leverage_neutral_tw"] is None,
                             -(r["leverage_neutral_tw"] or 0.0)))
    return rows


def main(argv=None) -> int:                                # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    out = run(verbose=not a.quiet, argv=sys.argv)
    print("\n" + out["headline"])
    print(f"\nreceipt: {OUT_DIR / 'G2_generation0.json'}")
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
