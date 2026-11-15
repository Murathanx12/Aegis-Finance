"""Read-only report over the rolling paper cohorts (CH-16 follow-up).

    python -m scripts.rolling_cohorts report --data-root <optimus> [--out <dir>]

Reads `<data-root>/rolling_cohorts/{cohorts,marks}` (and the bars panel, for
daily paths) and writes `cohort_report_<stamp>.json` + `.md` under `--out`.
It never writes under the data root's cohort folder, takes no lock, and does
not touch a stored file, hash, declaration or the step/backfill behaviour.

What it answers, in the owner's terms: how many INDEPENDENT bets are the books
(effective number of the correlation matrix of daily excess-vs-SPY paths over
DISTINCT portfolios), and how many more cohorts are needed before a difference
of a declared size could be seen under the module's own blocking rule.
Backfilled rows are backtest data, never forward evidence; no number here is a
skill claim.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services.portfolio_intelligence import branch_population_rolling as R
from backend.services.portfolio_intelligence.branch_population import digest

REPORT_SCHEMA = "rolling_cohort_report/1"
CANNOT = "CANNOT_DETERMINE"
_MARK_COLS = ["kind", "book_id", "cohort_id", "entry_session", "mark_k", "backfilled", "holdings_hash",
              "family", "excess_same_share", "excess_vs_random", "excess_vs_spy"]
_VOLATILE = ("report_id", "generated_utc", "sha256")


# ───────────────────────────── effective bets ───────────────────────────────

def _participation(corr: np.ndarray) -> float:
    """Same formula as `book_dna.participation_ratio` ((sum l)^2 / sum l^2); kept
    local so this report does not import the 2.2k-line book_dna module."""
    lam = np.clip(np.linalg.eigvalsh(corr), 0.0, None)
    return float(lam.sum() ** 2 / (lam ** 2).sum()) if (lam ** 2).sum() > 0 else float("nan")


def effective_bets(paths: dict[str, np.ndarray], *, min_sessions: Optional[int] = None) -> dict:
    """Effective number of bets over daily excess paths (one array per DISTINCT portfolio).

    CANNOT_DETERMINE below `min_sessions` common sessions (the count is printed).
    A flat path has no correlation and is dropped (counted)."""
    min_s = int(_config.COHORT_REPORT_MIN_SESSIONS if min_sessions is None else min_sessions)
    n_p = len(paths)
    n_s = min((len(v) for v in paths.values()), default=0)
    base = {"n_portfolios": n_p, "n_sessions": int(n_s), "min_sessions": min_s}
    if n_p == 0:
        return {**base, "status": CANNOT, "why": "no portfolios", "effective_bets": None,
                "corr_median": None, "share_corr_above": None}
    if n_s < min_s:
        return {**base, "status": CANNOT, "why": f"{n_s} common sessions of {min_s} needed",
                "effective_bets": None, "corr_median": None, "share_corr_above": None}
    keys = sorted(paths)
    M = np.column_stack([np.asarray(paths[k][:n_s], dtype=float) for k in keys])
    live = np.isfinite(M).all(axis=0) & (M.std(axis=0) > 1e-12)
    base["n_flat_or_nonfinite_dropped"] = int((~live).sum())
    M = M[:, live]
    if M.shape[1] == 0:
        return {**base, "status": CANNOT, "why": "every path is flat", "effective_bets": None,
                "corr_median": None, "share_corr_above": None}
    if M.shape[1] == 1:
        return {**base, "status": "OK", "effective_bets": 1.0, "corr_median": None, "share_corr_above": None}
    C = np.corrcoef(M.T)
    iu = np.triu_indices(M.shape[1], 1)
    pair = C[iu]
    return {**base, "status": "OK", "effective_bets": round(_participation(C), 3),
            "corr_median": round(float(np.median(pair)), 4),
            "share_corr_above": round(float((pair > float(_config.COHORT_REPORT_HIGH_CORR)).mean()), 4)}


def pairwise_by_family(paths: dict[str, np.ndarray], fams: dict[str, set], *,
                       min_sessions: Optional[int] = None) -> dict:
    """Median pairwise correlation and share above the high-corr line, WITHIN a
    family (both portfolios carry it) and ACROSS families (no family in common)."""
    min_s = int(_config.COHORT_REPORT_MIN_SESSIONS if min_sessions is None else min_sessions)
    n_s = min((len(v) for v in paths.values()), default=0)
    if n_s < min_s or len(paths) < 2:
        return {"status": CANNOT, "n_sessions": int(n_s), "why": f"{n_s} common sessions of {min_s} needed"}
    keys = sorted(paths)
    M = np.column_stack([np.asarray(paths[k][:n_s], dtype=float) for k in keys])
    live = np.isfinite(M).all(axis=0) & (M.std(axis=0) > 1e-12)
    keys = [k for k, ok in zip(keys, live) if ok]
    M = M[:, live]
    if len(keys) < 2:
        return {"status": CANNOT, "n_sessions": int(n_s), "why": "fewer than 2 non-flat paths"}
    C = np.corrcoef(M.T)
    hi = float(_config.COHORT_REPORT_HIGH_CORR)
    within: dict[str, list] = {}
    across: list = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            fi, fj = fams.get(keys[i], set()), fams.get(keys[j], set())
            common = fi & fj
            for f in common:
                within.setdefault(f, []).append(C[i, j])
            if not common:
                across.append(C[i, j])

    def summ(v: list) -> dict:
        a = np.asarray(v, dtype=float)
        return {"pairs": int(len(a)), "median": round(float(np.median(a)), 4) if len(a) else None,
                "share_above": round(float((a > hi).mean()), 4) if len(a) else None}
    return {"status": "OK", "n_sessions": int(n_s), "high_corr": hi,
            "within_family": {f: summ(v) for f, v in sorted(within.items())}, "across_families": summ(across)}


# ───────────────────────── MDE and cohorts still needed ─────────────────────

def mde_at(n_blocks: int, sd_block: float) -> Optional[float]:
    """The module's MDE (t_{1-a/2} + t_{power}, n-1 df) x sd / sqrt(n)."""
    if n_blocks < 2 or not (sd_block >= 0):
        return None
    from scipy import stats as S
    a, pw = float(_config.ROLLING_COHORT_ALPHA), float(_config.ROLLING_COHORT_POWER)
    dof = n_blocks - 1
    return float((S.t.ppf(1 - a / 2, dof) + S.t.ppf(pw, dof)) * sd_block / math.sqrt(n_blocks))


def blocks_needed(sd_block: float, target: float, *, cap: int = 5000) -> Optional[int]:
    """Smallest strict-block count N >= MIN_STRICT_BLOCKS whose MDE <= target."""
    if not (sd_block > 0) or not (target > 0):
        return None
    n = max(2, int(_config.ROLLING_COHORT_MIN_STRICT_BLOCKS))
    while n <= cap:
        m = mde_at(n, sd_block)
        if m is not None and m <= target:
            return n
        n += 1
    return None


def cohorts_still_needed(sd_block: Optional[float], target: float, *, horizon: int, n_cohorts_have: int) -> dict:
    """Cohorts that must still MATURE at `horizon` for the MDE to reach `target`.

    N blocks of 2 x horizon sessions, one cohort every CADENCE sessions, so
    ceil(N x 2h / cadence) cohorts in all; weeks = entries spread over those
    sessions plus the last cohort's own hold (5 sessions = 1 week)."""
    cadence = int(_config.ROLLING_COHORT_CADENCE_SESSIONS)
    out = {"target_mde": target, "n_blocks_needed": None, "cohorts_total_needed": None,
           "cohorts_still_needed": None, "weeks_at_cadence": None}
    if sd_block is None:
        return {**out, "status": CANNOT, "why": "no block dispersion to plan from"}
    n = blocks_needed(sd_block, target)
    if n is None:
        return {**out, "status": CANNOT, "why": "dispersion is zero or the target is unreachable"}
    total = math.ceil(n * 2 * horizon / cadence)
    still = max(0, total - int(n_cohorts_have))
    weeks = round((still * cadence + horizon) / 5.0, 1) if still else 0.0
    return {**out, "status": "OK", "n_blocks_needed": n, "cohorts_total_needed": total,
            "cohorts_still_needed": still, "weeks_at_cadence": weeks}


def _per_cohort(g: pd.DataFrame, col: str) -> pd.DataFrame:
    d = g.drop_duplicates(["cohort_id", "holdings_hash"])               # per DISTINCT portfolio
    d = d[d[col].notna()]
    return d.groupby(["cohort_id", "sidx"])[col].mean().reset_index()


def _stat_row(per_c: pd.DataFrame, col: str, *, horizon: int) -> dict:
    st = R.block_stats(per_c[col].tolist(), per_c["sidx"].tolist(), horizon=horizon)
    block = 2 * horizon
    sd_cohort = float(per_c[col].std(ddof=1)) if len(per_c) >= 2 else None
    sd_blocks = None
    if len(per_c) >= 2:
        bm = pd.DataFrame({"v": per_c[col].to_numpy(), "b": (per_c["sidx"].astype(int) // block).to_numpy()}).groupby("b")["v"].mean()
        sd_blocks = float(bm.std(ddof=1)) if len(bm) >= 2 else None
    return {**st, "sd_cohort": sd_cohort, "sd_blocks": sd_blocks}


def _plan_sd(row: dict) -> tuple[Optional[float], str]:
    """sd of ONE block mean for planning: the block dispersion when >= 2 blocks
    exist, else the cohort-to-cohort dispersion (conservative: assumes no
    averaging inside a block, which overstates the need, never understates)."""
    if row.get("sd_blocks"):
        return row["sd_blocks"], "block_means"
    if row.get("sd_cohort"):
        return row["sd_cohort"], "cohort_dispersion_conservative"
    return None, "none"


def horizon_family_stats(marks: pd.DataFrame, sidx: dict[str, int], *, horizons: tuple, forward_counts: dict,
                         daily_sd: Optional[dict] = None) -> dict:
    """Per family x horizon x view x control: n cohorts, strict blocks, mean, SE, MDE,
    and the cohorts still needed. `forward` is the only view that is evidence."""
    out: dict = {}
    if marks.empty:
        return out
    b = marks[marks["kind"] == "book"].copy()
    b["sidx"] = b["entry_session"].map(sidx)
    b = b[b["sidx"].notna()]
    b["sidx"] = b["sidx"].astype(int)
    metrics = (("excess_same_share", "vs_spy_same_invested_share"), ("excess_vs_random", "vs_random_same_band"))
    plan_cache: dict = {}
    for k in sorted(horizons):
        target = float(_config.COHORT_REPORT_TARGET_MDE.get(k, _config.COHORT_REPORT_TARGET_MDE[min(_config.COHORT_REPORT_TARGET_MDE)]))
        bk = b[b["mark_k"] == k]
        for fam in sorted(b["family"].dropna().unique()):
            for view, sub in (("forward", bk[~bk["backfilled"]]), ("all_incl_backfilled", bk)):
                g = sub[sub["family"] == fam]
                for col, label in metrics:
                    if g.empty or g[col].notna().sum() == 0:
                        row = {"n_cohorts": 0, "n_blocks_strict": 0, "mean": None, "se": None, "mde": None}
                    else:
                        row = _stat_row(_per_cohort(g, col), col, horizon=k)
                    cell = {key: row.get(key) for key in ("n_cohorts", "n_blocks_strict", "mean", "se", "mde",
                                                           "sd_blocks", "sd_cohort", "block_sessions")}
                    if view == "all_incl_backfilled":
                        plan_cache[(fam, k, col)] = row
                    out.setdefault(fam, {}).setdefault(str(k), {}).setdefault(label, {})[view] = cell
    # planning: forward-need uses the all-incl-backfilled dispersion (the only data there is)
    for fam, hz in out.items():
        for ks, labels in hz.items():
            k = int(ks)
            target = float(_config.COHORT_REPORT_TARGET_MDE.get(k, 0.02))
            for col, label in metrics:
                row = plan_cache.get((fam, k, col))
                sd, src = _plan_sd(row) if row else (None, "none")
                if sd is None and (daily_sd or {}).get(fam):   # one cohort cannot show dispersion over time
                    sd, src = float(daily_sd[fam]) * math.sqrt(k / 2.0), "daily_sd_x_sqrt(h/2)_iid_assumed"
                if sd is None:                      # borrow a shorter matured horizon, scaled by sqrt(h)
                    for k0 in sorted(h for h in horizons if h < k):
                        r0 = plan_cache.get((fam, k0, col))
                        s0, _ = _plan_sd(r0) if r0 else (None, "none")
                        if s0:
                            sd, src = s0 * math.sqrt(k / k0), f"borrowed_from_h{k0}_scaled_sqrt(h)"
                            break
                have = int(forward_counts.get((fam, k), 0))
                labels[label]["planning"] = {**cohorts_still_needed(sd, target, horizon=k, n_cohorts_have=have),
                                             "sd_block_assumed": sd, "sd_source": src,
                                             "n_forward_cohorts_matured": have}
    return out


# ─────────────────────────────── loading ────────────────────────────────────

def load_cohorts(data_root: Path) -> tuple[list[dict], pd.DataFrame]:
    store = R.Store(Path(data_root) / "rolling_cohorts")       # constructing creates nothing
    cohorts = store.cohorts()
    try:
        marks = store.marks(columns=_MARK_COLS)
    except Exception:                                           # older mark files lack columns
        marks = store.marks()
        marks = marks[[c for c in _MARK_COLS if c in marks.columns]]
    if "mark_k" in marks.columns:
        marks = marks[marks["mark_k"].isin([int(x) for x in _config.ROLLING_COHORT_HORIZONS])]
    return cohorts, marks


def load_bars_for(data_root: Path, cohorts: list[dict]) -> Optional[pd.DataFrame]:
    p = Path(data_root) / R.BARS_REL
    if not p.is_file() or not cohorts:
        return None
    names = {R.BENCH}
    for c in cohorts:
        for b in c["books"]:
            if b["status"] == "READY":
                names.update(b["long"])
    lo = min(pd.Timestamp(c["entry_session"]) for c in cohorts)
    f = pd.read_parquet(p, columns=["symbol", "date", "open", "close"],
                        filters=[("symbol", "in", sorted(names)), ("date", ">=", lo)])
    f["date"] = pd.to_datetime(f["date"])
    return f


def family_daily_sd(paths: dict, fams: dict) -> dict:
    """Std of the DAILY excess path of each family's equal-weight mean over its
    distinct portfolios (one cohort). A planning input when no horizon has two
    matured cohorts; assumed iid across days, so sd(h) = sd x sqrt(h); a strict block (2h sessions) averages two
    independent holds, so one block mean has sd(h)/sqrt(2)."""
    out: dict = {}
    for f in sorted({x for v in fams.values() for x in v}):
        cols = [paths[h] for h in paths if f in fams.get(h, set())]
        if not cols:
            continue
        n = min(len(c) for c in cols)
        if n < 5:
            continue
        m = np.mean(np.column_stack([c[:n] for c in cols]), axis=1)
        sd = float(np.std(m, ddof=1))
        if math.isfinite(sd) and sd > 0:
            out[f] = sd
    return out


def cohort_paths(cohort: dict, bars: pd.DataFrame) -> tuple[dict, dict, int]:
    """Daily excess-vs-SPY return path per DISTINCT portfolio of one cohort:
    ({holdings_hash: array}, {holdings_hash: {families}}, n_sessions)."""
    sessions = R.bench_sessions(bars)
    e = pd.Timestamp(cohort["entry_session"])
    if e not in set(sessions):
        return {}, {}, 0
    days = sessions[sessions.index(e):]
    need = {R.BENCH}
    ready = [b for b in cohort["books"] if b["status"] == "READY"]
    for b in ready:
        need.update(b["long"])
    sub = bars[bars["symbol"].isin(need) & (bars["date"] >= days[0])]
    close = sub.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").reindex(days)
    opn = sub.pivot_table(index="date", columns="symbol", values="open", aggfunc="last").reindex(days)
    spy_c = close[R.BENCH].to_numpy(dtype=float)
    spy_o0 = float(opn[R.BENCH].iloc[0])
    spy_r = np.diff(np.concatenate([[spy_o0], spy_c])) / np.concatenate([[spy_o0], spy_c[:-1]])
    paths: dict = {}
    fams: dict = {}
    for b in ready:
        hh = b["holdings_hash"]
        fams.setdefault(hh, set()).add(b["family"])
        if hh in paths:
            continue
        nav, _ = R._path_for(b["long"], b["short"], close, opn, spy_c, spy_o0)
        r = np.diff(np.concatenate([[1.0], nav])) / np.concatenate([[1.0], nav[:-1]])
        paths[hh] = r - spy_r
    return paths, fams, len(days)


# ───────────────────────────── the report ───────────────────────────────────

def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return round(f, 8) if math.isfinite(f) else None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _is_forward(c: dict) -> bool:
    return bool(c.get("forward_evidence", not c.get("backfilled", False)))


def _holdings(cohorts: list[dict]) -> dict:
    top_n = int(_config.COHORT_REPORT_TOP_NAMES)

    def table(cs: list[dict]) -> dict:
        books = [b for c in cs for b in c["books"] if b["status"] == "READY"]
        distinct = {}
        for c in cs:
            for b in c["books"]:
                if b["status"] == "READY":
                    distinct.setdefault((c["cohort_id"], b["holdings_hash"]), b)
        cnt, wsum = Counter(), Counter()
        for b in books:
            for t, w in b["long"].items():
                cnt[t] += 1
                wsum[t] += float(w)
        dcnt = Counter(t for b in distinct.values() for t in b["long"])
        names = sorted(cnt, key=lambda t: (-cnt[t], t))[:top_n]
        return {"n_books": len(books), "n_distinct_portfolios": len(distinct),
                "top_names": [{"name": t, "n_books": cnt[t], "share_of_books": round(cnt[t] / len(books), 4),
                               "share_of_distinct_portfolios": round(dcnt[t] / max(1, len(distinct)), 4),
                               "mean_weight_when_held": round(wsum[t] / cnt[t], 4)} for t in names]}
    newest = [max(cohorts, key=lambda c: c["cohort_id"])] if cohorts else []
    return {"all_cohorts": table(cohorts), "newest_cohort": table(newest)}


def build_report(data_root: Path, *, stamp: Optional[str] = None) -> dict:
    """The report as a dict. Reads only. `stamp` fixes the filename/id for tests."""
    data_root = Path(data_root)
    cohorts, marks = load_cohorts(data_root)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n_forward = sum(_is_forward(c) for c in cohorts)
    newest = max((c["cohort_id"] for c in cohorts), default=None)
    horizons = tuple(int(x) for x in _config.ROLLING_COHORT_HORIZONS)
    bars = None
    bars_note = None
    try:
        bars = load_bars_for(data_root, cohorts)
    except Exception as exc:                                   # a bars panel that will not read
        bars_note = f"bars unreadable: {type(exc).__name__}: {exc}"
    if bars is None and bars_note is None:
        bars_note = f"bars panel {R.BARS_REL} absent or no cohorts"
    # sessions index for strict blocks: bars calendar, else weekdays (flagged)
    entries = sorted({c["entry_session"] for c in cohorts})
    if bars is not None and not bars.empty:
        sess = [s.date().isoformat() for s in R.bench_sessions(bars)]
        sidx = {d: i for i, d in enumerate(sess)}
        sidx_source = "SPY bars calendar"
    else:
        base = pd.Timestamp(entries[0]) if entries else pd.Timestamp("2000-01-03")
        sidx = {d: int(np.busday_count(base.date(), pd.Timestamp(d).date())) for d in entries}
        sidx_source = "weekday count (bars unavailable; holidays ignored)"
    # forward cohorts matured per (family, horizon)
    fwd_counts: dict = {}
    if not marks.empty:
        f = marks[(marks["kind"] == "book") & (~marks["backfilled"])]
        for (fam, k), g in f.groupby(["family", "mark_k"]):
            fwd_counts[(fam, int(k))] = int(g["cohort_id"].nunique())
    # 1. books / distinct / effective bets
    fam_names = sorted({b["family"] for c in cohorts for b in c["books"]})
    per_cohort, ref, daily_sd = [], None, {}
    for c in sorted(cohorts, key=lambda x: x["cohort_id"]):
        ready = [b for b in c["books"] if b["status"] == "READY"]
        paths, fams, n_sess = ({}, {}, 0)
        if bars is not None:
            paths, fams, n_sess = cohort_paths(c, bars)
        fam_rows = {}
        for f in fam_names:
            fb = [b for b in ready if b["family"] == f]
            hs = {b["holdings_hash"] for b in fb}
            row = {"books": len(fb), "distinct_portfolios": len(hs)}
            row["bets"] = effective_bets({h: paths[h] for h in hs if h in paths}) if paths else \
                {"status": CANNOT, "why": bars_note or "no paths", "effective_bets": None,
                 "n_sessions": 0, "n_portfolios": len(hs)}
            fam_rows[f] = row
        overall = effective_bets(paths) if paths else {"status": CANNOT, "why": bars_note or "no paths",
                                                       "effective_bets": None, "n_sessions": 0,
                                                       "n_portfolios": len({b['holdings_hash'] for b in ready})}
        pw = pairwise_by_family(paths, fams) if paths else {"status": CANNOT, "why": bars_note or "no paths"}
        rec = {"cohort_id": c["cohort_id"], "entry_session": c["entry_session"],
               "backfilled": bool(c.get("backfilled")), "forward_evidence": _is_forward(c),
               "books": len(ready), "distinct_portfolios": len({b["holdings_hash"] for b in ready}),
               "sessions_since_entry": int(n_sess), "families": fam_rows, "overall_bets": overall, "pairwise": pw}
        per_cohort.append(rec)
        if overall["status"] == "OK":
            ref = rec
            daily_sd = family_daily_sd(paths, fams)                                 # the newest cohort with enough sessions
    if ref is None and per_cohort:
        ref = max(per_cohort, key=lambda r: r["sessions_since_entry"])
    total_books = sum(r["books"] for r in per_cohort)
    body = {
        "schema": REPORT_SCHEMA,
        "first_line": (f"{n_forward} forward cohort(s) of {len(cohorts)}; backfilled rows are backtest data, "
                       f"not forward evidence. Observations only: no skill claim."),
        "n_cohorts": len(cohorts), "n_forward": n_forward, "newest_cohort": newest,
        "cohort_flags": {c["cohort_id"]: ("forward" if _is_forward(c) else "backfilled") for c in cohorts},
        "inputs": {"marks_rows": int(len(marks)), "marks_horizons": list(horizons),
                   "bars_note": bars_note, "sidx_source": sidx_source,
                   "cohort_ids": [c["cohort_id"] for c in sorted(cohorts, key=lambda x: x["cohort_id"])]},
        "section_1_bets": {
            "totals": {"book_cohort_rows": total_books,
                       "distinct_portfolio_cohort_rows": sum(r["distinct_portfolios"] for r in per_cohort)},
            "reference_cohort": None if ref is None else ref["cohort_id"],
            "reference_overall": None if ref is None else ref["overall_bets"],
            "reference_families": None if ref is None else {f: v["bets"] | {"books": v["books"],
                                                                           "distinct_portfolios": v["distinct_portfolios"]}
                                                            for f, v in ref["families"].items()},
            "per_cohort": per_cohort},
        "section_2_pairwise_and_concentration": {
            "pairwise_reference_cohort": None if ref is None else ref["pairwise"],
            "holdings": _holdings(cohorts)},
        "section_3_horizons": {
            "unit_note": ("net excess return; 'vs_spy_same_invested_share' and 'vs_random_same_band' are the "
                          "module's own controls (never cash); SE on strict date blocks of 2 x horizon sessions"),
            "target_mde": {str(k): float(v) for k, v in _config.COHORT_REPORT_TARGET_MDE.items()},
            "families": horizon_family_stats(marks, sidx, horizons=horizons, forward_counts=fwd_counts,
                                                daily_sd=daily_sd)},
    }
    body = _clean(body)
    sha = digest(body)
    report_id = f"cohort_report_{stamp}"
    return {**body, "generated_utc": datetime.now(timezone.utc).isoformat(), "report_id": report_id,
            "sha256": sha,
            "citation": {"report_id": report_id, "sha256": sha, "newest_cohort": newest, "n_forward": n_forward}}


# ───────────────────────────────── text ─────────────────────────────────────

def _f(x: Any, pct: bool = False, nd: int = 2) -> str:
    if x is None:
        return "-"
    return f"{x * 100:.{nd}f}pp" if pct else f"{x:.{nd}f}"


def render_md(rep: dict) -> str:
    L = [f"# Rolling cohort report  {rep['report_id']}", "", rep["first_line"], ""]
    L.append(f"Newest cohort: {rep['newest_cohort']}.  Cohorts: " + ", ".join(
        f"{k} [{v}]" for k, v in rep["cohort_flags"].items()))
    s1 = rep["section_1_bets"]
    L += ["", "## 1. Books, distinct portfolios, independent bets", ""]
    ro = s1["reference_overall"]
    if ro is None:
        L.append("No cohorts.")
    else:
        L.append(f"Reference cohort {s1['reference_cohort']} (newest with enough sessions, else the longest): "
                 f"{ro.get('n_portfolios')} distinct portfolios, {ro.get('n_sessions')} sessions of daily excess "
                 f"vs SPY. Independent bets: " +
                 (f"{ro['effective_bets']} (status OK)" if ro["status"] == "OK" else
                  f"{CANNOT} ({ro.get('why')})") + ".")
        L += ["", "| family | books | distinct | sessions | independent bets | status |", "|---|---|---|---|---|---|"]
        for f, v in (s1["reference_families"] or {}).items():
            L.append(f"| {f} | {v['books']} | {v['distinct_portfolios']} | {v.get('n_sessions', 0)} | "
                      f"{_f(v.get('effective_bets'))} | {v['status']} |")
    L += ["", "Per cohort (n = distinct portfolios; bets over that cohort's own sessions):", "",
          "| cohort | flag | books | distinct | sessions | bets | status |", "|---|---|---|---|---|---|---|"]
    for r in s1["per_cohort"]:
        o = r["overall_bets"]
        L.append(f"| {r['cohort_id']} | {'forward' if r['forward_evidence'] else 'backfilled'} | {r['books']} | "
                 f"{r['distinct_portfolios']} | {r['sessions_since_entry']} | {_f(o.get('effective_bets'))} | {o['status']} |")
    s2 = rep["section_2_pairwise_and_concentration"]
    L += ["", "## 2. Pairwise correlation and concentration", ""]
    pw = s2["pairwise_reference_cohort"] or {}
    if pw.get("status") == "OK":
        L.append(f"Reference cohort, {pw['n_sessions']} sessions; share above {pw['high_corr']}:")
        L += ["", "| group | pairs | median corr | share above |", "|---|---|---|---|"]
        a = pw["across_families"]
        L.append(f"| across families | {a['pairs']} | {_f(a['median'], nd=3)} | {_f(a['share_above'], nd=3)} |")
        for f, v in pw["within_family"].items():
            L.append(f"| within {f} | {v['pairs']} | {_f(v['median'], nd=3)} | {_f(v['share_above'], nd=3)} |")
    else:
        L.append(f"{CANNOT}: {pw.get('why')}")
    for key, title in (("newest_cohort", "newest cohort"), ("all_cohorts", "all cohorts")):
        h = s2["holdings"][key]
        L += ["", f"Most-held names, {title} (n = {h['n_books']} books, {h['n_distinct_portfolios']} distinct portfolios):",
              "", "| name | books | share of books | share of distinct | mean weight |", "|---|---|---|---|---|"]
        for t in h["top_names"]:
            L.append(f"| {t['name']} | {t['n_books']} | {t['share_of_books']:.3f} | "
                      f"{t['share_of_distinct_portfolios']:.3f} | {t['mean_weight_when_held']:.3f} |")
    s3 = rep["section_3_horizons"]
    L += ["", "## 3. Matured horizons and cohorts still needed", "", s3["unit_note"] + ".", "",
          "Target MDE (declared): " + ", ".join(f"{k} sessions {v*100:.1f}pp" for k, v in s3["target_mde"].items()) + ".",
          "Forward rows are the only evidence; the backfilled view is descriptive and is used only as the planning dispersion.", ""]
    L += ["| family | h | control | fwd cohorts | backfilled cohorts (descriptive) | strict blocks | mean (backfilled) | SE | "
          "MDE now | planning sd (source) | cohorts still needed | ~weeks |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for fam, hz in s3["families"].items():
        for ks, labels in hz.items():
            for label, cell in labels.items():
                pl, fw, al = cell["planning"], cell["forward"], cell["all_incl_backfilled"]
                need = f"{pl['cohorts_still_needed']}" if pl["status"] == "OK" else CANNOT
                wk = f"{pl['weeks_at_cadence']}" if pl["status"] == "OK" else ""
                L.append(f"| {fam} | {ks} | {label} | {fw['n_cohorts']} | {al['n_cohorts']} | {al['n_blocks_strict']} | "
                          f"{_f(al['mean'], True)} | {_f(al['se'], True)} | {_f(al['mde'], True)} | "
                          f"{_f(pl['sd_block_assumed'], True)} ({pl['sd_source']}) | {need} | {wk} |")
    L += ["", "## Headline", ""]
    heads = []
    for fam, hz in s3["families"].items():
        parts = []
        for ks, labels in hz.items():
            needs = [(c["planning"]["cohorts_still_needed"], c["planning"]["weeks_at_cadence"])
                     for c in labels.values() if c["planning"]["status"] == "OK"]
            if needs:
                n, w = max(needs)
                parts.append(f"{n} more cohorts (~{w} weeks) at {ks} sessions (target {s3['target_mde'][ks]*100:.1f}pp)")
            else:
                parts.append(f"{CANNOT} at {ks} sessions")
        heads.append(f"- {fam}: nothing can be said for " + "; ".join(parts) +
                     f". Forward cohorts today: {rep['n_forward']}.")
    L += heads or ["- no family has marks yet."]
    c = rep["citation"]
    L += ["", "```json", json.dumps(c, sort_keys=True), "```", ""]
    return "\n".join(L)


def write_report(rep: dict, out: Path) -> tuple[Path, Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pj, pm = out / f"{rep['report_id']}.json", out / f"{rep['report_id']}.md"
    pj.write_text(json.dumps(rep, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf8", newline="\n")
    pm.write_text(render_md(rep), encoding="utf8", newline="\n")
    return pj, pm
