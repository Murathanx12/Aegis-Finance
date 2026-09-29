"""The whole strategy library re-read on CRSP total returns, 1991-2024 (2026-09-29).

    python -m scripts.library_on_crsp --part panel                 # wide CRSP panel (local parquet)
    python -m scripts.library_on_crsp --part fundamentals --panel-run <id>   # WRDS ratios, PIT
    python -m scripts.library_on_crsp --part run --panel-run <id> [--run-id <id>]   # every rule
    python -m scripts.library_on_crsp --part board --run-id <id>   # leaderboard + candidates

Licence `PRODUCT_EXPERIMENT`, $0, no LLM, no network. HINDSIGHT: every rule was
registered 2026-09-26. 1991-2016 was never seen by the library's development
(the vendor panel starts 2016): it is the HONEST HOLDOUT for these rules (not for
mechanisms published before it). 2017-2024 is the library's own window.

WHY: `momentum_on_crsp` found that the vendor panel keeps a living name only if
it was liquid on 2026-09-01 (survivorship by END-OF-SAMPLE liquidity). Every row
of the 2026-09-27/28 leaderboard was measured on that panel. This runs every
rule whose inputs exist in the CRSP era through the same engine, unchanged:
`night_backtest_factory.build_panel` on the CRSP bridge, `run_one` (costs on,
the 21-draw matched twin, two seed sets), the quarterly offset triplet for
3-month holds, by year keyed on the HOLD month, leave-one-year-out worst,
3-month-block t with the MDE beside it, share of total by date, and a deflated
Sharpe over EVERY cell tried (library cells + CRSP cells + combinations).

WHAT IT WRITES (all under `backend/data/optimus/crsp_rebuild/`, run id in every
name, never overwritten): `library_panel_<id>.parquet/.json` (local panel),
`library_fund_<id>.parquet/.json`, `library_rules_<run>.jsonl` (one line per
rule, appended as each rule finishes: a cut-off loses nothing),
`library_series_<run>/<rule>.parquet`, `library_board_<run>.json` + `.md`.
No book, ledger, bar file, leaderboard or past receipt is touched.
"""
from __future__ import annotations

import argparse
import gc
import itertools
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JOB = "library_on_crsp"
OPT = REPO / "backend" / "data" / "optimus"
WRDS = OPT / "wrds"
OUT = OPT / "crsp_rebuild"
#: the vendor matched-twin monthly series the side-by-side reads (2017-01 .. 2026)
VENDOR_TWIN_MONTHLY = OPT / "signal_structure" / "matched_twins_monthly_2026-09-27T082553Z.parquet"
#: cells the vendor library already looked at (LEADERBOARD.md multiplicity line, run 2026-09-28T141504Z)
VENDOR_CELLS_LOOKED_AT = 877
HOLDOUT = ("1991-01-01", "2016-12-31")
LIBWIN = ("2017-01-01", "2024-12-31")
#: PROXY map: library column -> WRDS financial-ratio column (wrdsapps firm_ratio,
#: point-in-time on `public_date`). NOT the library's SEC-facts definitions;
#: every rule run on a proxy is labelled so on the board.
FUND_PROXY = {"gp_at": "gprof", "book_to_market": "bm", "debt_at": "debt_at",
              "gross_margin": "gpm", "ni_be": "roe"}
FLOAT32_KEEP64 = {"close", "fwd_ret", "median_dollar_vol"}
#: candidate filter (declared BEFORE the board is read; PRODUCT_EXPERIMENT)
CAND_MIN_SHARE_POS_YEARS = 0.5          # strictly more than half of hold years positive
CAND_MAX_TOP5PCT_SHARE = 0.75           # v1 (retired, see CANDIDATE_RULE_AMENDMENT): top 5% carry < 75%
CANDIDATE_RULE_AMENDMENT = (
    "2026-09-29, after the first 132 rules were read: the v1 'top 5% of months carry < 75% of the total' "
    "test cannot go green for a realistic edge (a +0.5%/mo mean with a 3-4%/mo sd puts ~70-110% of the "
    "34-year total in the best 5% of months by arithmetic alone; 0 of 132 rules passed, including every "
    "t > 2 rule). It is replaced by the symmetric version: the mean after dropping the best AND worst 5% "
    "of months must stay > 0 (not carried by a handful of months, noise-neutral). Changed after looking: "
    "PRODUCT_EXPERIMENT exploration, and every candidate is a finding to test forward, never a prior.")
HEADLINE_RULE = (
    "headline, in order: FAILED_VARIANT if the calendar-neutral rule - twin21 mean over "
    "1991-2024 is <= 0; CALENDAR_ARTEFACT if the quarterly v2 calendar verdict says so; "
    "ALPHA_DETECTED if rule - twin21 t >= 2 on 3-month blocks AND the 1991-2016 holdout "
    "mean > 0 AND the FF3+UMD verdict of the net book is not BETA_EXPLAINS; BETA_EXPLAINS "
    "if the twin t >= 2 but the net book's FF3+UMD verdict is BETA_EXPLAINS; else "
    "CANNOT_DISTINGUISH. ROBUST_TO_CALENDAR is printed beside (never replaces) the headline.")


def say(*a) -> None:
    print(*a, flush=True)


# ── pure helpers (tested offline) ────────────────────────────────────────────

def coverable(rule_requires, columns) -> tuple[bool, list]:
    """(runnable, missing columns) for one rule on a panel's columns."""
    miss = sorted(set(rule_requires) - set(columns))
    return (not miss), miss


def headline(twin_full: dict, calendar: Optional[str], holdout: dict, factor_net: Optional[str]) -> str:
    m, t = twin_full.get("mean_monthly"), twin_full.get("t_blocks")
    if m is None:
        return "NOT_COMPUTED"
    if m <= 0:
        return "FAILED_VARIANT"
    if calendar == "CALENDAR_ARTEFACT":
        return "CALENDAR_ARTEFACT"
    if t is not None and t >= 2.0:
        if factor_net == "BETA_EXPLAINS":
            return "BETA_EXPLAINS"
        if (holdout.get("mean_monthly") or 0.0) > 0:
            return "ALPHA_DETECTED"
    return "CANNOT_DISTINGUISH"


def top_share(diff: pd.Series, q: float = 0.05) -> Optional[float]:
    """Share of the total carried by the best `q` of months (> 1 = the rest is negative)."""
    s = pd.Series(diff, dtype=float).dropna()
    tot = float(s.sum())
    if not len(s) or tot <= 0:
        return None
    n = max(1, int(math.ceil(q * len(s))))
    return float(s.sort_values(ascending=False).iloc[:n].sum() / tot)


def trimmed_mean(diff: pd.Series, q: float = 0.05) -> Optional[float]:
    """Mean after dropping the best and the worst `q` of months (symmetric, noise-neutral)."""
    s = pd.Series(diff, dtype=float).dropna().sort_values()
    n = int(math.floor(q * len(s)))
    if len(s) - 2 * n < 12:
        return None
    return float(s.iloc[n:len(s) - n].mean())


def hold_year_index(idx) -> pd.Index:
    return (pd.DatetimeIndex(idx) + pd.offsets.BDay(1)).year


def year_signs(diff: pd.Series) -> dict:
    """Hold-year sums of a decision-date-keyed monthly series (hold = decision + 1 BDay)."""
    s = pd.Series(diff, dtype=float).dropna()
    g = s.groupby(hold_year_index(s.index)).sum()
    return {"n_years": int(len(g)), "n_positive": int((g > 0).sum()),
            "share_positive": float((g > 0).mean()) if len(g) else None}


def loo_worst_mean(s: pd.Series) -> Optional[float]:
    """Leave-one-hold-year-out mean monthly value: the worst year to lose."""
    s = pd.Series(s, dtype=float).dropna()
    yrs = hold_year_index(s.index)
    vals = [float(s[yrs != y].mean()) for y in sorted(set(yrs))]
    return min(vals) if vals else None


def is_candidate(row: dict) -> tuple[bool, list]:
    """The declared filter: positive rule - twin in BOTH halves, a majority of positive
    hold years, not carried by a handful of months, LOO-worst > 0. Returns (ok, reasons failed)."""
    why = []
    if not ((row.get("holdout") or {}).get("mean_monthly") or 0) > 0:
        why.append("holdout_1991_2016<=0")
    if not ((row.get("libwin") or {}).get("mean_monthly") or 0) > 0:
        why.append("libwin_2017_2024<=0")
    sp = (row.get("years") or {}).get("share_positive")
    if sp is None or sp <= CAND_MIN_SHARE_POS_YEARS:
        why.append("positive_years<=half")
    if "trimmed5_mean" in row:
        tm = row.get("trimmed5_mean")
        if tm is None or tm <= 0:
            why.append("carried_by_extreme_months")
    else:
        ts = row.get("top5pct_share")
        if ts is None or ts >= CAND_MAX_TOP5PCT_SHARE:
            why.append("carried_by_top_months")
    lw = (row.get("loo_worst") or {}).get("worst")
    if lw is None or lw <= 0:
        why.append("loo_worst<=0")
    return (not why), why


def n_distinct_bets(corr: pd.DataFrame, rho_cut: float = 0.5) -> int:
    """Connected components of the graph |rho| >= rho_cut (single linkage)."""
    cols = list(corr.columns)
    seen, n = set(), 0
    for c in cols:
        if c in seen:
            continue
        n += 1
        stack = [c]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack += [y for y in cols if y not in seen and abs(float(corr.loc[x, y])) >= rho_cut]
    return n


def combos(series: dict, names: list, max_size: int = 3) -> dict:
    """Equal-weight blends of rule - twin series (a book holding each rule's names in
    equal parts is, to first order, the average of their differences)."""
    out = {}
    for n in range(2, max_size + 1):
        for c in itertools.combinations(names, n):
            df = pd.concat([series[x] for x in c], axis=1).dropna()
            if len(df) >= 24:
                out["+".join(c)] = df.mean(axis=1)
    return out


def vendor_side(vm: Optional[pd.DataFrame], rule_id: str, k: int) -> dict:
    """The vendor panel's rule - twin21 for the same cell (2017..2026 and 2017-2024)."""
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    if vm is None:
        return {"status": "NOT_COMPUTED: vendor twin monthly absent"}
    col = ("rule_minus_twin21", f"{rule_id}@k{k}")
    if col not in vm.columns:
        alt = [c for c in vm.columns if c[0] == "rule_minus_twin21" and str(c[1]).split("@")[0] == rule_id]
        if not alt:
            return {"status": "NOT_COMPUTED: cell absent from the vendor twin run"}
        col = alt[0]
    s = vm[col].dropna()
    return {"cell": col[1], "full_2017_2026": CR.window_stats(s, None, None),
            "overlap_2017_2024": CR.window_stats(s, *LIBWIN)}


def load_vendor_monthly() -> Optional[pd.DataFrame]:
    if not VENDOR_TWIN_MONTHLY.exists():
        return None
    vm = pd.read_parquet(VENDOR_TWIN_MONTHLY)
    if "decision_date" in vm.columns:
        vm = vm.set_index("decision_date")
    vm.index = pd.to_datetime(vm.index)
    return vm


# ── part 1: the wide panel ───────────────────────────────────────────────────

def part_panel(run_id: str) -> int:
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    from backend.services import xs_ranker as XR                     # noqa: PLC0415
    from scripts import momentum_on_crsp as M                         # noqa: PLC0415
    from scripts import night_backtest_factory as F                   # noqa: PLC0415
    from scripts.calendar_offset_triplet import peak_rss_mb          # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    OUT.mkdir(parents=True, exist_ok=True)
    pq_path, rj = OUT / f"library_panel_{run_id}.parquet", OUT / f"library_panel_{run_id}.json"
    if pq_path.exists() or rj.exists():
        say(f"REFUSED: {pq_path.name} exists")
        return 2
    t0 = time.time()
    mkt = M.market_daily()
    dl = pd.read_parquet(WRDS / "bulk" / "crsp__dsedelist.parquet",
                         columns=["permno", "dlstdt", "dlstcd", "dlret"])
    dl["dlstdt"] = pd.to_datetime(dl["dlstdt"])
    for c in ("dlstcd", "dlret"):
        dl[c] = pd.to_numeric(dl[c], errors="coerce").astype("float64")
    parts, audits = [], []
    for a, b in M.ERAS:
        te = time.time()
        daily = M.load_years(a - 2, b + 1)
        W = CR.wide_from_crsp(daily, dl, mkt)
        del daily
        gc.collect()
        with CR.price_band_disabled(XR) as (lo, hi):
            panel = F.build_panel(W, delist_return=0.0, min_index=252)
        panel = CR.apply_actual_price(panel, W, min_price=lo, max_price=hi)
        del W
        gc.collect()
        yrs = pd.DatetimeIndex(panel["date"]).year
        panel = panel[(yrs >= a) & (yrs <= b) & panel["is_month_end"].astype(bool)].reset_index(drop=True)
        for c in panel.columns:
            if panel[c].dtype == np.float64 and c not in FLOAT32_KEEP64:
                panel[c] = panel[c].astype(np.float32)
        audits.append({"era": [a, b], "rows": int(len(panel)), "cols": int(panel.shape[1]),
                       "seconds": round(time.time() - te, 1), "peak_mb": peak_rss_mb()})
        say(f"  era {a}-{b}: {len(panel):,} rows x {panel.shape[1]} cols {audits[-1]['seconds']}s "
            f"peak {audits[-1]['peak_mb']} MB")
        parts.append(panel)
        gc.collect()
    P = pd.concat(parts, ignore_index=True)
    del parts
    P.to_parquet(pq_path, index=False)
    doc = {"schema": "crsp_rebuild/library_panel/1", "job": JOB, "run_id": run_id,
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "construction": ("momentum_on_crsp --part panel, unchanged, keeping EVERY build_panel column "
                            "(floats stored as float32 except close / fwd_ret / median_dollar_vol)"),
           "rows": int(len(P)), "dates": int(P["date"].nunique()), "symbols": int(P["symbol"].nunique()),
           "columns": list(P.columns), "eras": audits, "seconds": round(time.time() - t0, 1)}
    atomic_write_json(rj, F._round(doc), indent=1)
    say(f"-> {pq_path.name} ({len(P):,} rows, {P.shape[1]} cols) {time.time()-t0:.0f}s")
    return 0


# ── part 2: fundamentals (WRDS ratios, point in time) ────────────────────────

def part_fundamentals(panel_run: str) -> int:
    from scripts import night_backtest_factory as F                   # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    fp, fj = OUT / f"library_fund_{panel_run}.parquet", OUT / f"library_fund_{panel_run}.json"
    if fp.exists():
        say(f"REFUSED: {fp.name} exists")
        return 2
    t0 = time.time()
    kp = OUT / f"library_panel_{panel_run}.parquet"
    if not kp.exists():                                   # the narrow momentum panel has the same rows
        kp = OUT / f"panel_{panel_run}.parquet"
    keys = pd.read_parquet(kp, columns=["date", "symbol"])
    keys["date"] = pd.to_datetime(keys["date"])
    keys["permno"] = pd.to_numeric(keys["symbol"].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    src = WRDS / "bulk" / "wrdsapps__firm_ratio.parquet"
    cols = ["permno", "public_date", "gsector", *sorted(set(FUND_PROXY.values()))]
    fr = pd.read_parquet(src, columns=cols)
    fr["public_date"] = pd.to_datetime(fr["public_date"])
    fr["permno"] = pd.to_numeric(fr["permno"], errors="coerce").astype("float64")
    fr = fr.dropna(subset=["permno", "public_date"])
    for c in FUND_PROXY.values():
        fr[c] = pd.to_numeric(fr[c], errors="coerce").astype("float32")
    fr = fr.sort_values("public_date")
    left = keys.reset_index().dropna(subset=["permno"]).sort_values("date")
    m = pd.merge_asof(left, fr, left_on="date", right_on="public_date", by="permno",
                      direction="backward", tolerance=pd.Timedelta(days=70))
    m = m.set_index("index").reindex(keys.index)
    out = keys[["date", "symbol"]].copy()
    for lib, w in FUND_PROXY.items():
        out[lib] = m[w].to_numpy()
    out["gsector"] = m["gsector"].astype("string").to_numpy()
    out.to_parquet(fp, index=False)
    cov = {c: float(out[c].notna().mean()) for c in [*FUND_PROXY, "gsector"]}
    by_year = out.groupby(out["date"].dt.year)["gp_at"].apply(lambda s: round(float(s.notna().mean()), 3))
    doc = {"schema": "crsp_rebuild/library_fund/1", "job": JOB, "panel_run": panel_run,
           "source": str(src.relative_to(REPO)).replace("\\", "/"),
           "pit_rule": ("merge_asof on public_date <= decision date by permno, 70-day tolerance "
                        "(WRDS Financial Ratios Suite: public_date already lags the filing)"),
           "proxy_map": FUND_PROXY, "gsector": "GICS sector as carried on the ratio row (point in time)",
           "caveat": ("PROXIES: the library's gp_at/debt_at/gross_margin/book_to_market/ni_be come from "
                      "SEC facts; these are WRDS's ratios for the same concepts, not byte-identical"),
           "coverage_all_rows": cov, "gp_at_coverage_by_year": {str(k): v for k, v in by_year.items()},
           "seconds": round(time.time() - t0, 1)}
    atomic_write_json(fj, F._round(doc), indent=1)
    say(f"-> {fp.name}: coverage {cov}")
    return 0


def attach_sector_pit(P: pd.DataFrame) -> pd.DataFrame:
    """sector_mom / sector_ret_21 / mom_minus_sector from a point-in-time gsector
    (attach_sector's arithmetic, not its static current-classification map)."""
    el = P["eligible"] & P["gsector"].notna()
    sm = P[el].groupby(["date", "gsector"]).agg(sector_mom=("mom_252_21", "mean"),
                                                sector_ret_21=("mom_21", "mean")).reset_index()
    P = P.merge(sm, on=["date", "gsector"], how="left")
    P["mom_minus_sector"] = P["mom_252_21"] - P["sector_mom"]
    return P


# ── part 3: every rule ───────────────────────────────────────────────────────

def load_full_panel(panel_run: str, fund_run: Optional[str] = None) -> tuple[pd.DataFrame, dict]:
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from backend.services import strategy_library_ext as EXT         # noqa: PLC0415
    P = pd.read_parquet(OUT / f"library_panel_{panel_run}.parquet")
    P["date"] = pd.to_datetime(P["date"])
    P["eligible"] = P["eligible"].astype(bool)
    meta = {"fundamentals": "ABSENT"}
    fp = OUT / f"library_fund_{fund_run or panel_run}.parquet"
    if fp.exists():
        f = pd.read_parquet(fp)
        f["date"] = pd.to_datetime(f["date"])
        P = P.merge(f, on=["date", "symbol"], how="left")
        P = attach_sector_pit(P)
        meta["fundamentals"] = fp.name
    P = EXT.derive_columns(P)
    P["tiebreak"] = SL._tiebreak(P)
    return P, meta


def part_run(panel_run: str, run_id: str, only: Optional[list] = None, fund_run: Optional[str] = None) -> int:
    from backend.services import calendar_offsets as CO              # noqa: PLC0415
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    from backend.services import matched_twins as MT                 # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from scripts import momentum_on_crsp as M                         # noqa: PLC0415
    from scripts import night_backtest_factory as F                   # noqa: PLC0415
    from scripts.calendar_offset_triplet import peak_rss_mb, run_one  # noqa: PLC0415
    t0 = time.time()
    jl = OUT / f"library_rules_{run_id}.jsonl"
    sdir = OUT / f"library_series_{run_id}"
    sdir.mkdir(parents=True, exist_ok=True)
    done = set()
    if jl.exists():
        for ln in jl.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(ln)["rule"])
            except Exception:                                        # noqa: BLE001 -- torn tail line
                pass
    P, meta = load_full_panel(panel_run, fund_run)
    say(f"{JOB} run {run_id}: panel {panel_run} {len(P):,} rows x {P.shape[1]} cols; "
        f"fundamentals {meta['fundamentals']}; {len(done)} rules already done; peak {peak_rss_mb()} MB")
    spy = M.spy_series(P)
    try:
        rpanel, _ = F.random_panel_leg(P)
    except Exception as e:                                           # noqa: BLE001
        rpanel = f"RANDOM_PANEL_SERIES_MISSING: {type(e).__name__}: {e}"
    benches = {"iwm": "IWM_SERIES_MISSING: no IWM on CRSP common stock", "random_panel": rpanel}
    ff = M.ff_monthly()
    grid = sorted(pd.DatetimeIndex(P.loc[P["fwd_ret"].notna(), "date"].unique()))
    by_date = MT.panel_by_date(P)
    cache: dict = {}
    fund_cols = set(FUND_PROXY) | {"gsector", "sector_mom", "sector_ret_21", "mom_minus_sector"}
    quiet = lambda *a: None                                          # noqa: E731
    for rule in SL.rules():
        if only and rule.id not in only:
            continue
        if rule.id in done:
            continue
        ok, miss = coverable(rule.requires, P.columns)
        base = {"rule": rule.id, "family": rule.family, "k": int(rule.k), "hold_months": int(rule.hold_months),
                "control": bool(rule.control or SL.is_random_control(rule.id)),
                "requires": list(rule.requires),
                "proxy_inputs": sorted(set(rule.requires) & fund_cols)}
        if not ok:
            _append(jl, {**base, "status": "NOT_RUN", "why": f"inputs absent in the CRSP era: {miss}"})
            continue
        te = time.time()
        try:
            row = run_one(P, spy, benches, rule, k=int(rule.k), by_date=by_date, cache=cache, grid=grid,
                          n_spy=VENDOR_CELLS_LOOKED_AT, n_twin=VENDOR_CELLS_LOOKED_AT, log=quiet,
                          flagged=set(), refuse_defects=False)
            ser = {"default": row.pop("_series")}
            cal = {"verdict": "n/a (hold != 3 months)"}
            if int(rule.hold_months) == 3:
                offs = {}
                for tag, var in CO.offset_variants(rule).items():
                    r_ = run_one(P, spy, benches, var, k=int(rule.k), by_date=by_date, cache=cache,
                                 grid=grid, n_spy=VENDOR_CELLS_LOOKED_AT, n_twin=VENDOR_CELLS_LOOKED_AT,
                                 log=quiet, flagged=set(), refuse_defects=False)
                    ser[tag] = r_.pop("_series")
                    offs[tag] = r_
                c_ = CO.classify(offs)
                cal = {"verdict": c_["verdict"], "why": c_["why"],
                       "offset_t": (c_.get("set_a") or {}).get("t_blocks"),
                       "offset_mean": c_.get("mean_monthly_rule_minus_twin21")}
                neutral = {t: s for t, s in ser.items() if t != "default"}
            else:
                neutral = {"default": ser["default"]}
        except Exception as e:                                       # noqa: BLE001 -- named per rule
            _append(jl, {**base, "status": "REFUSED", "why": f"{type(e).__name__}: {e}"})
            say(f"  REFUSED {rule.id}: {type(e).__name__}: {e}")
            continue
        common = None
        for df in neutral.values():
            common = df.index if common is None else common.intersection(df.index)
        common = pd.DatetimeIndex(sorted(common))
        rn = pd.concat([d["rule_net"].reindex(common) for d in neutral.values()], axis=1).mean(axis=1)
        tn = pd.concat([d["twin21_net"].reindex(common) for d in neutral.values()], axis=1).mean(axis=1)
        mk = next(iter(neutral.values()))["spy"].reindex(common)
        diff = (rn - tn).dropna()
        try:
            fr = M.factor_read(rn.dropna(), ff, hold_months=max(1, min(3, int(rule.hold_months))))
        except Exception as e:                                       # noqa: BLE001
            fr = {"ff3_umd": {"verdict": f"NOT_COMPUTED: {type(e).__name__}"}}
        f4 = (fr.get("ff3_umd") or {})
        vs_mkt = (rn - mk).dropna()
        stats = {
            "full": CR.window_stats(diff), "holdout": CR.window_stats(diff, *HOLDOUT),
            "libwin": CR.window_stats(diff, *LIBWIN),
            "vs_market_full": CR.window_stats(vs_mkt), "vs_market_holdout": CR.window_stats(vs_mkt, *HOLDOUT),
            "vs_market_libwin": CR.window_stats(vs_mkt, *LIBWIN),
            "years": year_signs(diff), "by_hold_year": CO.by_hold_year(diff),
            "loo_worst": CO.loo_worst(diff), "top5pct_share": top_share(diff),
            "share_of_total_by_date": CR.share_of_total_by_date(diff),
            "cagr_net": SL._cagr(rn.dropna()), "cagr_market": SL._cagr(mk.dropna()),
            "cagr_twin21": SL._cagr(tn.dropna()), "max_dd_net": SL._max_dd(rn.dropna()),
            "calendar": cal,
            "ff3_umd_net": {k_: f4.get(k_) for k_ in ("alpha_monthly", "t_alpha_used", "mde_alpha_80_used",
                                                      "verdict", "betas")},
            "mean_cost_bps_per_month": row.get("mean_cost_bps_per_month"),
            "n_delisting_fills": row.get("n_delisting_fills"),
        }
        stats["loo_worst"].pop("all", None)
        stats["headline"] = headline(stats["full"], cal.get("verdict"), stats["holdout"], f4.get("verdict"))
        stats["robust_to_calendar"] = cal.get("verdict") == "ROBUST_TO_CALENDAR"
        ok_c, why_c = is_candidate(stats)
        stats["candidate"], stats["candidate_fails"] = ok_c, why_c
        pd.DataFrame({"rule_net": rn, "twin21_net": tn, "market": mk}).to_parquet(sdir / f"{rule.id}.parquet")
        _append(jl, F._round({**base, "status": "RUN", **stats, "seconds": round(time.time() - te, 1)}))
        w = stats["full"]
        say(f"  {rule.id:42s} k{rule.k:<3d} h{rule.hold_months} rule-twin full "
            f"{_pc(w['mean_monthly'])} t {_n(w['t_blocks'])} MDE {_pc(w['mde_monthly'])} | holdout "
            f"{_pc(stats['holdout']['mean_monthly'])} | 2017-24 {_pc(stats['libwin']['mean_monthly'])} | "
            f"{stats['headline']}{' CAND' if ok_c else ''}  {time.time()-te:.0f}s peak {peak_rss_mb()} MB")
        del ser, neutral
        gc.collect()
    say(f"-> {jl.name} ({time.time()-t0:.0f}s)")
    return 0


def _append(path: Path, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, default=str) + "\n")


def _pc(v, nd=2):
    return "n/a" if v is None else f"{v*100:+.{nd}f}%"


def _n(v):
    return "n/a" if v is None else f"{v:+.2f}"


# ── part 4: the board ────────────────────────────────────────────────────────

def read_rows(run_id: str) -> list:
    rows = {}
    for ln in (OUT / f"library_rules_{run_id}.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
        except Exception:                                            # noqa: BLE001
            continue
        rows[r["rule"]] = r
    return list(rows.values())


def part_board(run_id: str) -> int:
    from backend.services import crsp_rebuild as CR                  # noqa: PLC0415
    from backend.services import strategy_library as SL              # noqa: PLC0415
    from scripts import night_backtest_factory as F                   # noqa: PLC0415
    from scripts.night_checkpoint import atomic_write_json           # noqa: PLC0415
    bid = F.new_run_id()
    bj, bm = OUT / f"library_board_{run_id}__{bid}.json", OUT / f"library_board_{run_id}__{bid}.md"
    rows = read_rows(run_id)
    ran = [r for r in rows if r.get("status") == "RUN"]
    sdir = OUT / f"library_series_{run_id}"
    diffs = {}
    for r in ran:
        p = sdir / f"{r['rule']}.parquet"
        if p.exists():
            d = pd.read_parquet(p)
            diffs[r["rule"]] = (d["rule_net"] - d["twin21_net"]).dropna()
    vm = load_vendor_monthly()
    for r in ran:
        r["vendor"] = vendor_side(vm, r["rule"], r["k"])
        r["candidate_as_run_v1"], r["candidate_fails_v1"] = r.get("candidate"), r.get("candidate_fails")
        r["trimmed5_mean"] = trimmed_mean(diffs[r["rule"]]) if r["rule"] in diffs else None
        r["candidate"], r["candidate_fails"] = is_candidate(r)
    tested = [r for r in ran if not r["control"]]
    cands = [r["rule"] for r in tested if r.get("candidate")]
    by_mean = sorted(cands, key=lambda x: -(next(r for r in tested if r["rule"] == x)["full"]["mean_monthly"] or 0))
    cmb = combos(diffs, by_mean[:12], max_size=3) if len(by_mean) >= 2 else {}
    combo_rows = []
    for name, s in cmb.items():
        st = {"full": CR.window_stats(s), "holdout": CR.window_stats(s, *HOLDOUT),
              "libwin": CR.window_stats(s, *LIBWIN), "years": year_signs(s),
              "top5pct_share": top_share(s), "trimmed5_mean": trimmed_mean(s),
              "loo_worst": {"worst": loo_worst_mean(s)}}
        st["candidate"], st["candidate_fails"] = is_candidate(st)
        combo_rows.append({"combo": name, **st})
    n_crsp = len(tested)
    n_total = VENDOR_CELLS_LOOKED_AT + n_crsp + len(combo_rows)
    cells = [{"id": r["rule"], "active_returns": diffs[r["rule"]].tolist()} for r in tested if r["rule"] in diffs]
    cells += [{"id": c["combo"], "active_returns": cmb[c["combo"]].tolist()} for c in combo_rows]
    cells2 = [dict(c) for c in cells]
    SL.deflate(cells, n_trials=n_total)
    SL.deflate(cells2, n_trials=max(1, n_crsp + len(combo_rows)))
    dsr = {c["id"]: (c.get("dsr"), c.get("dsr_z")) for c in cells}
    dsr2 = {c["id"]: c.get("dsr") for c in cells2}
    for r in tested:
        r["dsr_rule_minus_twin"], r["dsr_z"] = dsr.get(r["rule"], (None, None))
        r["dsr_crsp_cells_only"] = dsr2.get(r["rule"])
    for c in combo_rows:
        c["dsr_rule_minus_twin"], c["dsr_z"] = dsr.get(c["combo"], (None, None))
        c["dsr_crsp_cells_only"] = dsr2.get(c["combo"])
    corr_block = {}
    if len(cands) >= 2:
        df = pd.DataFrame({c: diffs[c] for c in cands}).dropna()
        corr = df.corr()
        corr_block = {"series": cands, "n_months": int(len(df)), "corr": corr.round(3).to_dict(),
                      "distinct_bets": {f"{c:.1f}": n_distinct_bets(corr, c) for c in (0.3, 0.5, 0.7)}}
    counts: dict = {}
    for r in tested:
        counts[r["headline"]] = counts.get(r["headline"], 0) + 1
    ctrl = [{"rule": r["rule"], "full": r["full"], "holdout": r["holdout"], "libwin": r["libwin"]}
            for r in ran if r["control"]]
    not_run = [{"rule": r["rule"], "why": r.get("why"), "status": r.get("status")} for r in rows
               if r.get("status") != "RUN"]
    surviving = [r["rule"] for r in tested if (r["full"].get("mean_monthly") or 0) > 0
                 and (r["holdout"].get("mean_monthly") or 0) > 0 and (r["libwin"].get("mean_monthly") or 0) > 0]
    vend_pos = [r["rule"] for r in tested if ((r["vendor"].get("full_2017_2026") or {}).get("mean_monthly") or 0) > 0]
    doc = {"schema": "crsp_rebuild/library_board/1", "job": JOB, "run_id": run_id, "board_id": bid,
           "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "label": ("HINDSIGHT. 1991-2016 = honest holdout for these rules (never seen by the library's "
                     "development); 2017-2024 = the library's window. Candidates are chosen AFTER looking: "
                     "they are findings to be tested forward, never priors."),
           "headline_rule": HEADLINE_RULE,
           "candidate_rule": (f"rule - twin21 mean > 0 in 1991-2016 AND in 2017-2024; share of positive hold "
                              f"years > {CAND_MIN_SHARE_POS_YEARS}; mean after dropping the best and worst 5% "
                              f"of months > 0; leave-one-year-out worst > 0"),
           "candidate_rule_amendment": CANDIDATE_RULE_AMENDMENT,
           "n_rules_in_library": len(rows), "n_run": len(ran), "n_tested_non_control": n_crsp,
           "n_not_run": len(not_run), "n_combinations_tried": len(combo_rows),
           "dsr_n_trials": {"primary_all_cells_ever": n_total, "vendor_cells": VENDOR_CELLS_LOOKED_AT,
                            "crsp_cells": n_crsp, "combinations": len(combo_rows)},
           "headline_counts": counts, "positive_in_all_three_windows": surviving,
           "vendor_positive_rule_minus_twin": len(vend_pos),
           "candidates": cands, "candidate_correlation": corr_block,
           "combinations": sorted(combo_rows, key=lambda c: -(c["full"]["mean_monthly"] or 0))[:40],
           "combinations_passing": [c["combo"] for c in combo_rows if c["candidate"]],
           "controls": ctrl, "not_run": not_run, "rows": ran,
           "vendor_source": VENDOR_TWIN_MONTHLY.name}
    atomic_write_json(bj, F._round(doc), indent=1)
    bm.write_text(render_md(doc), encoding="utf-8")
    say(f"-> {bj.name} + {bm.name}: {n_crsp} rules tested, {len(surviving)} positive in all three windows, "
        f"{len(cands)} candidates; headlines {counts}")
    return 0


def _w(x):
    x = x or {}
    m, t, e = x.get("mean_monthly"), x.get("t_blocks"), x.get("mde_monthly")
    s = "n/a" if m is None else f"{m*100:+.2f}"
    if t is not None and e is not None:
        s += f" (t {t:+.2f}, MDE {e*100:.2f})"
    return s


def _row_md(r: dict) -> str:
    v = r.get("vendor") or {}
    ys = r.get("years") or {}
    f4 = r.get("ff3_umd_net") or {}
    lw = (r.get("loo_worst") or {}).get("worst")
    fa = "n/a" if f4.get("alpha_monthly") is None else \
        f"{f4['alpha_monthly']*100:+.2f} (t {(f4.get('t_alpha_used') or 0):+.2f}) {f4.get('verdict')}"
    tag = (" (control)" if r.get("control") else "") + (" [proxy]" if r.get("proxy_inputs") else "")
    return (f"| {r['rule']}{tag} | {r['k']} | {r['hold_months']} | {_w(r['full'])} | {_w(r['holdout'])} | "
            f"{_w(r['libwin'])} | {_w(v['full_2017_2026']) if 'full_2017_2026' in v else 'n/a'} | "
            f"{_w(v['overlap_2017_2024']) if 'overlap_2017_2024' in v else 'n/a'} | "
            f"{ys.get('n_positive')}/{ys.get('n_years')} | "
            f"{'n/a' if r.get('top5pct_share') is None else round(r['top5pct_share'], 2)} | "
            f"{'n/a' if lw is None else f'{lw*100:+.2f}'} | "
            f"{'n/a' if r.get('dsr_rule_minus_twin') is None else round(r['dsr_rule_minus_twin'], 3)} | "
            f"{(r.get('calendar') or {}).get('verdict')} | {fa} | "
            f"**{r.get('headline', 'n/a')}**{' CAND' if r.get('candidate') else ''} |")


def render_md(doc: dict) -> str:
    L = [f"# Library on CRSP -- run {doc['run_id']} (board {doc['board_id']})", "",
         f"> {doc['label']}", "",
         f"Rules in the library: {doc['n_rules_in_library']}; run on CRSP: {doc['n_run']} "
         f"({doc['n_tested_non_control']} non-control); not run: {doc['n_not_run']}; combinations tried: "
         f"{doc['n_combinations_tried']}. DSR at n = {doc['dsr_n_trials']['primary_all_cells_ever']} "
         f"(every cell ever looked at).", "",
         f"Headline rule: {doc['headline_rule']}", "",
         f"Headline counts: {doc['headline_counts']}", "",
         f"Positive rule - twin in all three windows (full, 1991-2016, 2017-2024): "
         f"{len(doc['positive_in_all_three_windows'])}. Positive on the vendor panel: "
         f"{doc['vendor_positive_rule_minus_twin']}.", "",
         f"Candidates ({doc['candidate_rule']}): {doc['candidates']}", "",
         "All numbers are rule - matched twin (21 draws), %/month, net of costs; t on 3-month blocks, "
         "MDE = 2.8 x SE. Years keyed on the hold month.", ""]
    hdr = ("| rule | k | h | CRSP 1991-2024 | holdout 1991-2016 | 2017-2024 | vendor 2017-2026 | "
           "vendor 2017-2024 | pos yrs | top5% share | LOO-worst | DSR | calendar | FF3+UMD net alpha | headline |")
    L += ["## Every rule run, sorted by CRSP rule - twin (1991-2024)", "", hdr, "|" + "---|" * 15]
    for r in sorted(doc["rows"], key=lambda r: -(r["full"].get("mean_monthly") if r["full"].get("mean_monthly") is not None else -9)):
        L.append(_row_md(r))
    L += ["", "## Combinations (equal-weight blends of candidate rule - twin series)", ""]
    for c in doc["combinations"][:20]:
        L.append(f"- {c['combo']}: full {_w(c['full'])}; holdout {_w(c['holdout'])}; 2017-24 {_w(c['libwin'])}; "
                 f"pos yrs {c['years'].get('n_positive')}/{c['years'].get('n_years')}; DSR "
                 f"{c.get('dsr_rule_minus_twin')}; passes filter: {c['candidate']}")
    cb = doc.get("candidate_correlation") or {}
    if cb:
        L += ["", "## Candidate correlation (rule - twin series)", "",
              f"distinct bets by |rho| cut: {cb.get('distinct_bets')}", ""]
        names = cb["series"]
        L.append("| | " + " | ".join(names) + " |")
        L.append("|" + "---|" * (len(names) + 1))
        for a in names:
            L.append(f"| {a} | " + " | ".join(f"{cb['corr'][a][b]:+.2f}" for b in names) + " |")
    L += ["", "## Controls", ""]
    for c in doc["controls"]:
        L.append(f"- {c['rule']}: full {_w(c['full'])}; holdout {_w(c['holdout'])}; 2017-24 {_w(c['libwin'])}")
    L += ["", "## Not run on CRSP, and why", ""]
    for n in doc["not_run"]:
        L.append(f"- {n['rule']} ({n.get('status')}): {n['why']}")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    from scripts import night_backtest_factory as F                   # noqa: PLC0415
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=("panel", "fundamentals", "run", "board"), required=True)
    ap.add_argument("--panel-run", default=None)
    ap.add_argument("--run-id", default=None, help="resume a run (rules already in its jsonl are skipped)")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--fund-run", default=None, help="panel id whose library_fund_<id>.parquet to merge (keys are (date, symbol))")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.part == "panel":
        return part_panel(F.new_run_id())
    if a.part == "board":
        if not a.run_id:
            say("REFUSED: --run-id is required")
            return 2
        return part_board(a.run_id)
    if not a.panel_run:
        say("REFUSED: --panel-run is required")
        return 2
    if a.part == "fundamentals":
        return part_fundamentals(a.panel_run)
    return part_run(a.panel_run, a.run_id or F.new_run_id(), only=a.only, fund_run=a.fund_run)


if __name__ == "__main__":
    raise SystemExit(main())
