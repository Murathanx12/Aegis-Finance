"""Signal structure of one VALID strategy-library run: distinct bets, ETF decomposition, lead-lag.

    python -m scripts.signal_structure                          # run 2026-09-26T150811Z
    python -m scripts.signal_structure --run-id <id> --refresh-etf
    python -m scripts.signal_structure --rekey --run-id 2026-09-26T164302Z   # hold-month sidecar
    python -m scripts.signal_structure --run-id <id> --rekey --hac --matched-twins --family-pool
        (the flags run in that order; --matched-twins covers EVERY primary cell when the
         factory wrote holdings_<id>.manifest.json, else the 2024-26 top-10 file)

$0, no LLM. Network: one yfinance pull of eight ETFs (adjusted close), cached
under `backend/data/optimus/signal_structure/etf_monthly.parquet` with its fetch
stamp beside it. Does NOT run the factory and does not read the bars panel.

Series source: the factory checkpoint whose `config.panel` equals the run
receipt's panel fingerprint -- the working-tree copy if it matches, else the
committed copy (`git show HEAD:`), else REFUSE. A checkpoint from another run
(e.g. the INVALID T153843Z) is never read in its place.

Outputs (all under `signal_structure/`):
  monthly_returns_<run>.parquet  date x cell, monthly NET returns (active + SPY)
  signal_structure_<run>.json    the receipt: clusters, DSR at n=clusters vs n=cells,
                                 decomposition, lead-lag hypotheses, frozen-book overlap
  tables_<run>.md                the tables the doc quotes
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.services import signal_structure as SS  # noqa: E402

LIB = REPO / "backend" / "data" / "optimus" / "strategy_library"
OUT = REPO / "backend" / "data" / "optimus" / "signal_structure"
BRIDGE = REPO / "backend" / "data" / "optimus" / "bridge"
CKPT_REL = "backend/data/optimus/strategy_library/checkpoint_{date}.json"
DEFAULT_RUN = "2026-09-26T150811Z"
TOP_N = 30


# ── inputs ──────────────────────────────────────────────────────────────────

def load_checkpoint(run: dict) -> tuple[dict, str]:
    fp = run["panel"]["fingerprint"]
    rel = CKPT_REL.format(date=run["date"])
    tried = []
    p = REPO / rel
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        if (d.get("config") or {}).get("panel") == fp:
            return d, f"working tree {rel}"
        tried.append(f"working tree: panel {(d.get('config') or {}).get('panel')} != {fp}")
    try:
        raw = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO, capture_output=True,
                             check=True).stdout
        d = json.loads(raw.decode("utf-8"))
        if (d.get("config") or {}).get("panel") == fp:
            head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                                  capture_output=True, text=True).stdout.strip()
            return d, f"git HEAD ({head}):{rel}, written {d.get('written_utc')}"
        tried.append(f"HEAD: panel {(d.get('config') or {}).get('panel')} != {fp}")
    except Exception as e:  # noqa: BLE001 -- recorded in the refusal
        tried.append(f"HEAD: {e}")
    raise SystemExit(f"REFUSED: no checkpoint matches run panel {fp}: {tried}")


def etf_monthly(refresh: bool) -> tuple[pd.DataFrame, dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    pq, meta_p = OUT / "etf_monthly.parquet", OUT / "etf_monthly.json"
    if pq.exists() and meta_p.exists() and not refresh:
        return pd.read_parquet(pq), json.loads(meta_p.read_text(encoding="utf-8"))
    import yfinance as yf
    px = yf.download(list(SS.ETF_TICKERS), start="2016-11-01", progress=False,
                     auto_adjust=True)["Close"]
    px.index = pd.DatetimeIndex(px.index)
    if getattr(px.index, "tz", None) is not None:
        px.index = px.index.tz_localize(None)
    missing = [t for t in SS.ETF_TICKERS if t not in px.columns or px[t].notna().sum() < 250]
    if missing:
        raise SystemExit(f"REFUSED: yfinance returned no usable history for {missing}")
    daily = px.pct_change(fill_method=None)
    dd = SS.month_end_sessions(px["SPY"].dropna().index)
    mon = pd.DataFrame({t: SS.period_returns(daily[t].dropna(), dd) for t in SS.ETF_TICKERS})
    mon.index.name = "decision_date"
    meta = {"fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "yfinance auto_adjust=True Close (total return)",
            "construction": "daily pct_change compounded over (month-end session, next month-end session]; "
                            "indexed by the period's START decision date (the factory's spy_leg convention)",
            "tickers": list(SS.ETF_TICKERS),
            "first_valid": {t: str(px[t].first_valid_index().date()) for t in SS.ETF_TICKERS},
            "last_session": str(px.index.max().date())}
    mon.to_parquet(pq)
    meta_p.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return mon, meta


# ── helpers ─────────────────────────────────────────────────────────────────

def _f(v, nd=3):
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:+.{nd}f}"


def _pct(v, nd=1):
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{100 * v:+.{nd}f}%"


def cluster_block(active: pd.DataFrame, mask: np.ndarray, cells: dict, dev_dsr: dict,
                  rows_by_rule: dict, label: str) -> dict:
    sub = active[mask]
    corr = SS.corr_matrix(sub)
    lab = SS.cluster(corr)
    clusters = []
    for c_id, members in lab.groupby(lab).groups.items():
        mem = list(members)
        rep = max(mem, key=lambda m: (dev_dsr.get(m) if dev_dsr.get(m) is not None else -1, m))
        rr = rows_by_rule.get(cells[rep]["rule"]) or {}
        cell_ck = cells[rep]
        fam = Counter(cells[m]["family"] for m in mem)
        inner = corr.loc[mem, mem].to_numpy()
        iu = np.triu_indices(len(mem), 1)
        clusters.append({
            "cluster": int(c_id), "n": len(mem), "members": sorted(mem),
            "rules": sorted({cells[m]["rule"] for m in mem}),
            "family_mix": dict(fam.most_common()),
            "mean_inner_rho": float(np.nanmean(inner[iu])) if len(mem) > 1 else None,
            "representative": rep, "rep_dev_dsr": dev_dsr.get(rep),
            "rep_dev_vs_spy": cell_ck.get("dev_vs_spy"), "rep_sealed_vs_spy": cell_ck.get("sealed_vs_spy"),
            "rep_beat_spy_both": bool((cell_ck.get("dev_vs_spy") or -1) > 0
                                      and (cell_ck.get("sealed_vs_spy") or -1) > 0),
            "rep_is_primary_cell": bool(cell_ck["primary"]),
        })
    clusters.sort(key=lambda c: (-c["n"], c["representative"]))
    excluded = [c for c in active.columns if c not in corr.columns]
    return {"window": label, "n_series": int(len(corr.columns)), "n_excluded_short": len(excluded),
            "n_clusters": int(lab.nunique()) if len(lab) else 0, "labels": lab.to_dict(),
            "clusters": clusters, "min_pair_months": SS.MIN_PAIR_MONTHS}


def stored_series_check(pq: Path, net: pd.DataFrame) -> dict:
    """The stored monthly series is the input of record: if the parquet exists
    it is compared with this reconstruction and KEPT (never rewritten); a
    disagreement above 1e-9 refuses the run by name."""
    if not pq.exists():
        return {"status": "WRITTEN", "path": str(pq.relative_to(REPO))}
    old = pd.read_parquet(pq)
    cols = sorted(set(old.columns) & set(net.columns))
    extra = sorted(set(net.columns) ^ set(old.columns))
    a = old[cols].reindex(net.index).to_numpy(dtype=float)
    b = net[cols].to_numpy(dtype=float)
    both = np.isfinite(a) & np.isfinite(b)
    gap = float(np.max(np.abs(a[both] - b[both]))) if both.any() else 0.0
    nan_mismatch = int((np.isfinite(a) ^ np.isfinite(b)).sum())
    if gap > 1e-9 or nan_mismatch or extra:
        raise SystemExit(f"REFUSED: stored {pq.name} disagrees with the checkpoint reconstruction "
                         f"(max gap {gap:.2e}, {nan_mismatch} NaN mismatches, "
                         f"{len(extra)} columns in only one)")
    return {"status": "STORED_SERIES_MATCHES", "path": str(pq.relative_to(REPO)),
            "max_abs_gap": gap, "n_columns": len(cols)}


def _fit(y: pd.Series, X: pd.DataFrame, hold_months: int = 1) -> dict:
    try:
        return SS.ols(y, X, hold_months=hold_months)
    except SS.InsufficientHistory as e:
        return {"status": "REFUSED", "why": str(e)}


def decompose(active: pd.DataFrame, X: pd.DataFrame, masks: dict, board: dict,
              cells: dict, primary: list, *, hac: bool = True) -> tuple[dict, dict]:
    """{rule: decomposition} over every primary cell, plus (dev beta, 2024-26
    beta) pairs per spread for the beta-stability correlation.

    `hac` (default): a rule held h > 1 months gets Newey-West SEs at lag h - 1
    and its verdict reads the HAC t; hac=False reproduces the plain readout."""
    cand = [r for r in board["all_rows"] if not r.get("control")
            and r.get("sealed_vs_spy") is not None and r.get("dev_vs_spy") is not None]
    top_sealed = {r["id"] for r in sorted(cand, key=lambda r: (-r["sealed_vs_spy"], r["id"]))[:TOP_N]}
    top_dev = {r["id"] for r in sorted(cand, key=lambda r: (-r["dev_vs_spy"], r["id"]))[:TOP_N]}
    by_id = {r["id"]: r for r in board["all_rows"]}
    decomp, pairs = {}, {c: [] for c in X.columns}
    for cid in primary:
        rid = cells[cid]["rule"]
        r = by_id.get(rid) or {}
        y = active[cid]
        hm = cells[cid]["hold_months"] if hac else 1
        out = {"cell": cid, "family": cells[cid]["family"], "hold_months": cells[cid]["hold_months"],
               "se_basis": "hac" if hm > 1 else "plain",
               "sealed_vs_spy": r.get("sealed_vs_spy", cells[cid].get("sealed_vs_spy")),
               "dev_vs_spy": r.get("dev_vs_spy", cells[cid].get("dev_vs_spy")),
               "in_sealed_top30": rid in top_sealed, "in_dev_top30": rid in top_dev}
        for w in ("sealed", "dev"):
            out[w] = _fit(y[masks[w]], X[masks[w]], hm)
            out[f"{w}_smh_mtum"] = _fit(y[masks[w]], X.loc[masks[w], ["SMH-SPY", "MTUM-SPY"]], hm)
        out["full"] = _fit(y, X, hm)
        s, d = out["sealed"], out["dev"]
        if "t_alpha" in s and "t_alpha" in d:
            try:
                h = SS.exante_hedge(y[masks["sealed"]], X[masks["sealed"]], d["betas"],
                                    hold_months=hm)
            except SS.InsufficientHistory as e:
                h = {"status": "REFUSED", "why": str(e)}
            out["alpha_after_pre2024_hedge"] = h
            if "t" in h:
                out["verdict"] = SS.verdict(h, s["mean_active_monthly"])
                out["alpha_sign"] = "+" if h["alpha_monthly"] > 0 else "-"
            else:
                out["verdict"] = "REFUSED"
            out["beta_stability"] = {c.split("-")[0]: {"dev": d["betas"][c], "2024_26": s["betas"][c]}
                                     for c in X.columns}
            for c in X.columns:
                pairs[c].append((d["betas"][c], s["betas"][c]))
        else:
            out["verdict"] = "REFUSED"
        out["survives_both"] = bool(s.get("t_alpha_used", s.get("t_alpha", -9)) >= 2
                                    and d.get("t_alpha_used", d.get("t_alpha", -9)) >= 2)
        decomp[rid] = out
    return decomp, pairs


def summarise_decomposition(decomp: dict, pairs: dict) -> dict:
    ok = [v for v in decomp.values() if "t_alpha" in (v.get("sealed") or {})]

    def med(xs):
        xs = [x for x in xs if x is not None and np.isfinite(x)]
        return float(np.median(xs)) if xs else None

    def dist(vs):
        return dict(sorted(Counter(v.get("verdict") for v in vs).items()))
    st = {}
    for c, pr in pairs.items():
        a = np.array(pr, dtype=float)
        st[c.split("-")[0]] = (float(np.corrcoef(a[:, 0], a[:, 1])[0, 1]) if len(a) > 2 else None)
    return {
        "n_primary_cells": len(decomp), "n_decomposed": len(ok),
        "median_se_alpha_2024_26": med([v["sealed"]["se_alpha"] for v in ok]),
        "median_mde_alpha_2024_26": med([v["sealed"]["mde_alpha_80"] for v in ok]),
        "median_se_alpha_dev": med([v["dev"].get("se_alpha") for v in ok if "se_alpha" in v["dev"]]),
        "n_t_ge_2_dev": sum(1 for v in ok if v["dev"].get("t_alpha", -9) >= 2),
        "n_t_ge_2_2024_26": sum(1 for v in ok if v["sealed"]["t_alpha"] >= 2),
        "n_t_ge_2_full": sum(1 for v in ok if (v.get("full") or {}).get("t_alpha", -9) >= 2),
        "n_t_ge_2_both": sum(1 for v in ok if v["survives_both"]),
        "n_t_used_ge_2_2024_26": sum(1 for v in ok if v["sealed"].get("t_alpha_used", -9) >= 2),
        "se_basis": "survives_both and *_used read the HAC t for hold > 1 (plain for hold 1)",
        "verdicts_all_primary": dist(decomp.values()),
        "verdicts_2024_26_top30": dist([v for v in decomp.values() if v["in_sealed_top30"]]),
        "verdicts_dev_top30": dist([v for v in decomp.values() if v["in_dev_top30"]]),
        "alpha_detected_negative": sorted(k for k, v in decomp.items()
                                          if v.get("verdict") == "ALPHA_DETECTED"
                                          and v.get("alpha_sign") == "-"),
        "beta_stability_corr_dev_vs_2024_26": st,
        "note": ("beta stability = correlation across primary cells of each spread's dev beta with "
                 "its 2024-26 beta; a low number means the loading is a regime, not a style"),
    }


def bet_count_curve(active_p: pd.DataFrame, net_p: pd.DataFrame, X: pd.DataFrame) -> dict:
    """Clusters over the primary cells, full window, at each rho cut, on the
    raw net, the active and the residual (after SMH/IWM/MTUM, after all six
    spreads) returns. The residual count is the multiplicity denominator for
    ALPHA claims; the active/raw counts are the ones for RISK."""
    series = {"raw_net": net_p, "active": active_p,
              "residual_smh_iwm_mtum": SS.residualise(active_p, X[["SMH-SPY", "IWM-SPY", "MTUM-SPY"]]),
              "residual_6_etf": SS.residualise(active_p, X)}
    out = {}
    for name, df in series.items():
        corr = SS.corr_matrix(df)
        out[name] = {"n_series": int(len(corr)), "clusters_by_rho": SS.cluster_curve(corr),
                     **SS.pair_rho_summary(corr)}
    return out


AXES = (("universe", "universe_rule"), ("weighting", "weight_rule"),
        ("hold/offset", "hold_months"), ("hold/offset", "rebalance_months"))
#: construction suffixes: a rule id minus these is its SIGNAL (mom_6_1_large -> mom_6_1)
CONSTRUCTION_SUFFIXES = ("_mid_plus", "_large", "_small", "_mid", "_mega", "_q", "_ivw",
                         "_secrel", "_calm")


def base_signal(rule_id: str) -> str:
    b, changed = rule_id, True
    while changed:
        changed = False
        for suf in CONSTRUCTION_SUFFIXES:
            if b.endswith(suf) and len(b) > len(suf):
                b, changed = b[: -len(suf)], True
    return b


def member_axis(meta: dict, anchor: dict, k: int, k_anchor: int,
                rule: str = "", rule_anchor: str = "") -> str:
    """The axes on which two cluster members differ: construction (universe /
    k / weighting / hold-offset) and, when their base signals differ,
    "signal/filter"."""
    diff = sorted({ax for ax, key in AXES if str(meta.get(key)) != str(anchor.get(key))})
    if k != k_anchor:
        diff.append("k")
    if rule and rule_anchor and base_signal(rule) != base_signal(rule_anchor):
        diff = ["signal/filter"] + diff
    return "+".join(diff) if diff else "same construction"


def pair_persistence(rows: list, metas: dict, cells: dict) -> list:
    """Every member pair: the axes it differs on, and whether its dev ordering
    (a beat b before 2024) held in 2024-26."""
    out = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if None in (a["dev_vs_spy"], b["dev_vs_spy"], a["sealed_vs_spy"], b["sealed_vs_spy"]):
                continue
            ra, rb = cells[a["cell"]]["rule"], cells[b["cell"]]["rule"]
            ax = member_axis(metas[a["cell"]], metas[b["cell"]], cells[a["cell"]]["k"],
                             cells[b["cell"]]["k"], ra, rb)
            out.append({"a": a["cell"], "b": b["cell"], "axis": ax,
                        "persists": bool((a["dev_vs_spy"] - b["dev_vs_spy"])
                                         * (a["sealed_vs_spy"] - b["sealed_vs_spy"]) > 0)})
    return out


def pair_axis_class(axis: str) -> str:
    """signal/filter if the base signal differs; else construction only."""
    return "signal/filter" if axis.startswith("signal/filter") else "construction only"


def within_cluster(block: dict, active: pd.DataFrame, net: pd.DataFrame, spy: pd.Series,
                   masks: dict, done: dict, cells: dict, X: pd.DataFrame, *,
                   min_members: int = 3) -> list:
    """Level 2 of the bridge, historically: inside each full-window cluster of
    >= `min_members` primary cells, the member spread of 2024-26 excess, the
    tracking error of member - cluster mean, the dev -> 2024-26 rank
    persistence, and the axis the members differ on. Level 1 beside it: the
    cluster's EW mean, hedged ex ante (dev betas) over 2024-26."""
    from scipy.stats import spearmanr

    from backend.services import strategy_library as SL
    out = []
    for cl in block["clusters"]:
        mem = [m for m in cl["members"] if m in active.columns]
        if len(mem) < min_members:
            continue
        anchor = cl["representative"]
        am = (done[cells[anchor]["rule"]].get("meta") or {})
        rows, metas = [], {}
        for m in mem:
            b = SL.panel_benchmarks(net[m], {"dev": masks["dev"], "sealed": masks["sealed"]},
                                    {"spy": spy})
            metas[m] = done[cells[m]["rule"]].get("meta") or {}
            rows.append({"cell": m, "dev_vs_spy": b.get("dev_vs_spy"),
                         "sealed_vs_spy": b.get("sealed_vs_spy"),
                         "axis": "anchor" if m == anchor else member_axis(
                             metas[m], am, cells[m]["k"], cells[anchor]["k"],
                             cells[m]["rule"], cells[anchor]["rule"])})
        pairs = pair_persistence(rows, metas, cells)
        cm = active[mem].mean(axis=1)
        # the cluster mean inherits the LONGEST hold among its members (HAC lag)
        hm = max(cells[m]["hold_months"] for m in mem)
        te = [float((active[m] - cm).dropna().std(ddof=1) * np.sqrt(12)) for m in mem]
        sv = [r["sealed_vs_spy"] for r in rows if r["sealed_vs_spy"] is not None]
        both = [(r["dev_vs_spy"], r["sealed_vs_spy"]) for r in rows
                if r["dev_vs_spy"] is not None and r["sealed_vs_spy"] is not None]
        rho = float(spearmanr([a for a, _ in both], [b for _, b in both])[0]) if len(both) >= 3 else None
        axes = Counter(r["axis"] for r in rows if r["axis"] != "anchor")
        lvl1: dict = {}
        d = _fit(cm[masks["dev"]], X[masks["dev"]], hm)
        s_ = _fit(cm[masks["sealed"]], X[masks["sealed"]], hm)
        if "betas" in d and "mean_active_monthly" in s_:
            try:
                h = SS.exante_hedge(cm[masks["sealed"]], X[masks["sealed"]], d["betas"],
                                    hold_months=hm)
                lvl1 = {"mean_active_2024_26": s_["mean_active_monthly"],
                        "alpha_in_window": s_["alpha_monthly"], "t_in_window": s_["t_alpha"],
                        "mde_in_window": s_["mde_alpha_80"],
                        "alpha_after_pre2024_hedge": h["alpha_monthly"], "se_hedged": h["se"],
                        "t_hedged": h["t"], "mde_hedged": h["mde_80"],
                        "verdict": SS.verdict(h, s_["mean_active_monthly"]),
                        "alpha_sign": "+" if h["alpha_monthly"] > 0 else "-"}
            except SS.InsufficientHistory as e:
                lvl1 = {"status": "REFUSED", "why": str(e)}
        out.append({"cluster": cl["cluster"], "n": len(mem), "anchor": anchor,
                    "family_mix": cl["family_mix"], "mean_inner_rho": cl["mean_inner_rho"],
                    "sealed_vs_spy_min": min(sv) if sv else None,
                    "sealed_vs_spy_max": max(sv) if sv else None,
                    "sealed_vs_spy_sd": float(np.std(sv, ddof=1)) if len(sv) > 1 else None,
                    "median_te_vs_cluster_mean_annual": float(np.median(te)),
                    "rank_corr_dev_vs_2024_26": rho, "axes": dict(axes.most_common()),
                    "dominant_axis": axes.most_common(1)[0][0] if axes else None,
                    "pairs_by_class": {k: {"n": len(v), "share_order_persists":
                                           float(np.mean([x["persists"] for x in v]))}
                                       for k, v in _group(pairs).items()},
                    "level1_cluster_mean": lvl1, "members": rows, "pairs": pairs})
    return out


def _group(pairs: list) -> dict:
    g: dict = {}
    for x in pairs:
        g.setdefault(pair_axis_class(x["axis"]), []).append(x)
    return g


def persistence_summary(within: list) -> dict:
    """Across every cluster: does a member's dev ordering persist into 2024-26,
    for pairs that differ only in construction vs pairs whose signal differs?"""
    allp = [x for c in within for x in c.get("pairs") or []]
    by = {k: {"n_pairs": len(v), "share_order_persists": float(np.mean([x["persists"] for x in v]))}
          for k, v in sorted(_group(allp).items())}
    fine: dict = {}
    for x in allp:
        if pair_axis_class(x["axis"]) == "construction only":
            fine.setdefault(x["axis"], []).append(x["persists"])
    by_axis = {k: {"n_pairs": len(v), "share_order_persists": float(np.mean(v))}
               for k, v in sorted(fine.items())}
    return {"pairs": by, "construction_pairs_by_axis": by_axis,
            "note": ("a pair's order persists when (dev_a - dev_b) and (2024-26_a - 2024-26_b) "
                     "have the same sign; 50% is a coin")}


# ── REKEY: hold-month keying + panel-relative benchmarks, from stored series ──
#
# Review 2026-09-27 §4b: the factory keyed `by_year`, `leave_one_year_out` and
# `loo_worst_*` on the DECISION date, one month early. This recomputes them for a
# past run of record from its own stored monthly series (no factory rerun), prints
# both keys, and lists the rules whose verdict moves. §2: every row also gets
# vs_iwm and vs_random_panel beside vs_spy.

LOO_GATE = 0.0            # night_backtest_factory.freeze_gate: loo_worst_mean_active > 0
TOP5_GATE = 0.6           # night_backtest_factory.GATE_TOP5_SHARE_MAX


def _sha256(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _match_board(done: dict, rows: list) -> dict:
    """How well a checkpoint reproduces a board's rows (exact mean active,
    dev_vs_spy within 1e-5: the SPY leg is re-pulled between runs)."""
    n = exact = 0
    worst = 0.0
    for r in rows:
        c = ((done.get(r["id"]) or {}).get("cells") or {}).get(str(r["k"])) or {}
        if c.get("status") != "OK":
            continue
        n += 1
        if abs((c.get("mean_active_monthly") or 0) - (r.get("mean_active_monthly") or 0)) < 1e-9:
            exact += 1
        if c.get("dev_vs_spy") is not None and r.get("dev_vs_spy") is not None:
            worst = max(worst, abs(c["dev_vs_spy"] - r["dev_vs_spy"]))
    return {"n_rows": len(rows), "n_cells_found": n, "n_mean_active_exact": exact,
            "max_abs_dev_vs_spy_gap": worst}


def find_series_source(run: dict, rows: list) -> tuple[dict, dict]:
    """The checkpoint whose panel is the run's AND whose cells reproduce every
    board row. Working tree, then git HEAD, then every checkpoint file on disk
    (a later run on the same date overwrites the date-named one; its `.bak`
    keeps the earlier). Refuses when none reproduces the board."""
    fp = run["panel"]["fingerprint"]
    cands: list = []
    rel = CKPT_REL.format(date=run["date"])
    for p in [REPO / rel] + sorted(p for p in LIB.glob("checkpoint_*.json") if p != REPO / rel):
        cands.append(("file", p))
    cands.insert(1, ("head", rel))
    tried = []
    for kind, p in cands:
        try:
            if kind == "file":
                raw = p.read_bytes()
                src = {"path": str(p.relative_to(REPO)).replace("\\", "/"), "sha256": _sha256(p)}
            else:
                raw = subprocess.run(["git", "show", f"HEAD:{p}"], cwd=REPO, capture_output=True,
                                     check=True).stdout
                src = {"path": f"git HEAD:{p}"}
            d = json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001 -- recorded in the refusal
            tried.append(f"{p}: {e}")
            continue
        if (d.get("config") or {}).get("panel") != fp:
            tried.append(f"{src['path']}: panel {(d.get('config') or {}).get('panel')} != {fp}")
            continue
        m = _match_board(d["state"]["done"], rows)
        if m["n_cells_found"] == len(rows) and m["n_mean_active_exact"] == len(rows) \
                and m["max_abs_dev_vs_spy_gap"] < 1e-5:
            return d, {**src, "written_utc": d.get("written_utc"), "board_match": m,
                       "config": d.get("config")}
        tried.append(f"{src['path']}: panel matches but reproduces {m['n_mean_active_exact']} of "
                     f"{len(rows)} rows")
    raise SystemExit(f"REFUSED: no checkpoint reproduces the board of run {run.get('run_id')}: {tried}")


def rekey_row(net: pd.Series, spy: pd.Series) -> dict:
    """Both keys for one cell's monthly net series (indexed by decision date)."""
    from backend.services import strategy_library as SL
    s = net.dropna()
    sp = spy.reindex(s.index)
    act = s - sp
    dec_y, hold_y = s.index.year, SL.hold_years(s.index)
    out = {}
    for key, ys in (("decision", dec_y), ("hold", hold_y)):
        by = SL.by_year_table(s, sp, ys)
        loo = SL.leave_one_year_out(act, ys)
        out[key] = {"by_year": by, "by_year_signs": SL._signs(by),
                    "positive_excess_years_2020_2025": SL._positive_years(by),
                    "leave_one_year_out_mean_active": loo,
                    "loo_worst_mean_active": min(loo.values()) if loo else None,
                    "loo_worst_dropped_year": min(loo, key=loo.get) if loo else None}
    lr = np.log1p(s.to_numpy(dtype=float))
    tot = float(lr.sum())
    out["top5_months_share_of_log_return"] = float(np.sort(lr)[::-1][:5].sum() / tot) if tot > 0 else None
    out["top5_months_hold"] = SL.top_months(s, 5)
    return out


def rekey(run_id: str) -> dict:
    from backend.services import strategy_library as SL
    run = json.loads((LIB / f"run_{run_id}.json").read_text(encoding="utf-8"))
    bp = LIB / f"leaderboard_{run_id}.json"
    board = json.loads(bp.read_text(encoding="utf-8"))
    rows = list(board["all_rows"]) + [dict(c, control=True) for c in board.get("controls") or []]
    ck, src = find_series_source(run, rows)
    done = ck["state"]["done"]
    cells, refused = SS.cells_from_checkpoint(done)
    etf, _meta = etf_monthly(False)
    active, ref2 = SS.active_frame(cells, pd.DatetimeIndex(etf.index))
    refused += ref2
    active = active.loc[active.notna().any(axis=1)]
    spy = etf["SPY"].reindex(active.index)
    net = active.add(spy, axis=0)
    gap = SS.reconstruction_gap(cells, net)
    iwm = etf["IWM"].reindex(active.index) if "IWM" in etf.columns else None
    try:
        panel = SL.random_panel(net)
        panel_status = {"status": "OK", "cells": [c for c in net.columns
                                                  if c in {f"{r}@k{SL.RANDOM_PANEL_K}"
                                                           for r in SL.RANDOM_PANEL_RULES}]}
    except SL.BenchmarkMissing as e:
        panel, panel_status = None, {"status": "REFUSED", "why": str(e)}
    masks = SS.window_masks(active.index)
    wm = {"dev": masks["dev"], "sealed": masks["sealed"]}
    out_rows, changed, check = [], {"loo_verdict": [], "loo_dropped_year": [], "top5_verdict": [],
                                    "positive_years_2020_2025": []}, []
    for r in rows:
        cid = SS.cell_id(r["id"], r["k"])
        if cid not in net.columns:
            out_rows.append({"id": r["id"], "k": r["k"], "status": "NO_SERIES"})
            continue
        rk = rekey_row(net[cid], spy)
        bm = SL.panel_benchmarks(net[cid], wm, {"spy": spy, "iwm": iwm, "random_panel": panel})
        d, h = rk["decision"], rk["hold"]
        v_dec = None if d["loo_worst_mean_active"] is None else d["loo_worst_mean_active"] > LOO_GATE
        v_hold = None if h["loo_worst_mean_active"] is None else h["loo_worst_mean_active"] > LOO_GATE
        t5 = rk["top5_months_share_of_log_return"]
        row = {"id": r["id"], "k": r["k"], "family": r.get("family"), "control": bool(r.get("control")),
               "by_year_hold": h["by_year"], "by_year_decision": d["by_year"],
               "by_year_decision_status": SL.DECISION_KEY_DEPRECATED,
               "by_year_signs_hold": h["by_year_signs"], "by_year_signs_decision": d["by_year_signs"],
               "positive_excess_years_2020_2025_hold": h["positive_excess_years_2020_2025"],
               "positive_excess_years_2020_2025_decision": d["positive_excess_years_2020_2025"],
               "loo_worst_mean_active_hold": h["loo_worst_mean_active"],
               "loo_worst_dropped_year_hold": h["loo_worst_dropped_year"],
               "loo_worst_mean_active_decision": d["loo_worst_mean_active"],
               "loo_worst_dropped_year_decision": d["loo_worst_dropped_year"],
               "leave_one_year_out_mean_active_hold": h["leave_one_year_out_mean_active"],
               "leave_one_year_out_mean_active_decision": d["leave_one_year_out_mean_active"],
               "top5_months_share_of_log_return": t5, "top5_months_hold": rk["top5_months_hold"],
               "loo_gt_0_decision": v_dec, "loo_gt_0_hold": v_hold,
               "top5_lt_0_6": None if t5 is None else t5 < TOP5_GATE,
               "board_loo_worst_mean_active": r.get("loo_worst_mean_active"),
               "board_dev_vs_spy": r.get("dev_vs_spy"), "board_sealed_vs_spy": r.get("sealed_vs_spy"),
               **bm}
        if r.get("loo_worst_mean_active") is not None and d["loo_worst_mean_active"] is not None:
            check.append(abs(r["loo_worst_mean_active"] - d["loo_worst_mean_active"]))
        if v_dec != v_hold:
            changed["loo_verdict"].append({"id": r["id"], "control": row["control"],
                                           "decision": d["loo_worst_mean_active"],
                                           "hold": h["loo_worst_mean_active"],
                                           "gate_decision": v_dec, "gate_hold": v_hold})
        if d["loo_worst_dropped_year"] != h["loo_worst_dropped_year"]:
            changed["loo_dropped_year"].append({"id": r["id"], "decision": d["loo_worst_dropped_year"],
                                                "hold": h["loo_worst_dropped_year"]})
        if d["positive_excess_years_2020_2025"] != h["positive_excess_years_2020_2025"]:
            changed["positive_years_2020_2025"].append({
                "id": r["id"], "decision": d["positive_excess_years_2020_2025"],
                "hold": h["positive_excess_years_2020_2025"]})
        out_rows.append(row)
    ok = [x for x in out_rows if x.get("status") != "NO_SERIES"]
    prim = [x for x in ok if not x["control"]]

    def both(bn):
        have = [x for x in prim if x.get(f"dev_vs_{bn}") is not None and x.get(f"sealed_vs_{bn}") is not None]
        return {"n_beat_both": sum(1 for x in have if x[f"dev_vs_{bn}"] > 0 and x[f"sealed_vs_{bn}"] > 0),
                "n_rules": len(have)}
    counts = {bn: both(bn) for bn in ("spy",) + SL.PANEL_BENCHMARKS}
    # the random controls' own IWM tilt: the panel is small-cap before any rule acts
    X1 = (etf["IWM"] - etf["SPY"]).reindex(active.index).rename("IWM-SPY").to_frame()
    tilt = {}
    for c in sorted(c for c in net.columns if cells.get(c, {}).get("family") == "control"):
        try:
            tilt[c] = SS.ols(active[c], X1)["betas"]["IWM-SPY"]
        except SS.InsufficientHistory:
            tilt[c] = None
    brow = [dict(r, **{k: x.get(k) for k in ("dev_vs_iwm", "sealed_vs_iwm", "dev_vs_random_panel",
                                                "sealed_vs_random_panel")})
            for r, x in zip(rows, out_rows) if not r.get("control")]
    dse = SL.dev_selected_sealed_evaluated(brow)
    shifts = []
    for x in ok:
        for y in sorted(set(x["by_year_hold"]) | set(x["by_year_decision"])):
            a = (x["by_year_decision"].get(y) or {}).get("excess")
            b = (x["by_year_hold"].get(y) or {}).get("excess")
            if a is not None and b is not None:
                shifts.append({"id": x["id"], "year": y, "excess_decision": a, "excess_hold": b,
                               "shift": b - a})
    shifts.sort(key=lambda z: -abs(z["shift"]))
    doc = {
        "schema": "strategy_library/rekeyed/1", "job": "signal_structure --rekey", "run_id": run_id,
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "board": str(bp.relative_to(REPO)).replace("\\", "/"),
        "why": ("review 2026-09-27 §4b + §2: per-period statistics re-keyed on the month the money "
                "was HELD, and vs_iwm / vs_random_panel beside vs_spy; recomputed from the run's own "
                "stored monthly series, no factory rerun"),
        "year_key": SL.YEAR_KEY_NOTE, "decision_key": SL.DECISION_KEY_DEPRECATED,
        "series_source": src, "reconstruction_check": {
            **gap, "what": "net = active + SPY (cached ETF series) vs the checkpoint's decision-keyed by_year net"},
        "recompute_check_loo_worst_decision_vs_board": {
            "n": len(check), "max_abs_gap": max(check) if check else None},
        "benchmarks": {"note": SL.PANEL_BENCHMARK_NOTE, "random_panel": panel_status,
                       "iwm": "OK" if iwm is not None else "IWM_SERIES_MISSING",
                       "random_controls_iwm_beta_full": tilt,
                       "beat_in_both_windows": counts},
        "dev_selected_sealed_evaluated": dse,
        "gates": {"loo": f"loo_worst_mean_active > {LOO_GATE}", "top5": f"top5 share < {TOP5_GATE}"},
        "changed": {**changed,
                    "top5_note": ("the top-5-month share is a sum over the five best months; the key "
                                  "does not change it, so no top-5 verdict can move -- WHICH months "
                                  "it names is now printed as hold months (`top5_months_hold`)")},
        "n_changed": {k: len(v) for k, v in changed.items()},
        "largest_year_shifts": shifts[:25],
        "rows": out_rows, "refused": refused,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"leaderboard_{run_id}.rekeyed.json"
    p.write_text(json.dumps(doc, indent=1, default=lambda o: None if isinstance(o, float)
                            and not np.isfinite(o) else str(o)), encoding="utf-8")
    print(f"rekeyed -> {p}")
    print(json.dumps({"n_changed": doc["n_changed"], "beat_in_both_windows": counts,
                      "series_source": {k: src[k] for k in ("path", "board_match")}}, indent=1))
    return doc


# ── HAC: Newey-West t for multi-month holds, readout of a run of record ─────
#
# Owed item 2 (adjudication 2026-09-27): a rule held h > 1 months has serially
# dependent monthly active returns, so its plain t is optimistic. The readout is
# recomputed with Newey-West SEs at lag h - 1 (Bartlett) from the run's stored
# series (no factory), beside the plain one, and every verdict that moves is named.

def load_series_of_record(run_id: str) -> dict:
    """The run's board, cells and monthly active/net frames from its series of
    record (the checkpoint that reproduces the board). Writes
    monthly_returns_<run>.parquet if absent; if present it must agree."""
    run = json.loads((LIB / f"run_{run_id}.json").read_text(encoding="utf-8"))
    bp = LIB / f"leaderboard_{run_id}.json"
    board = json.loads(bp.read_text(encoding="utf-8"))
    rows = list(board["all_rows"]) + [dict(c, control=True) for c in board.get("controls") or []]
    ck, src = find_series_source(run, rows)
    done = ck["state"]["done"]
    del ck
    cells, refused = SS.cells_from_checkpoint(done)
    etf, _meta = etf_monthly(False)
    active, ref2 = SS.active_frame(cells, pd.DatetimeIndex(etf.index))
    refused += ref2
    for cid, _ in ref2:
        cells.pop(cid, None)
    active = active.loc[active.notna().any(axis=1)]
    spy = etf["SPY"].reindex(active.index)
    net = active.add(spy, axis=0)
    net.index.name = "decision_date"
    pq = OUT / f"monthly_returns_{run_id}.parquet"
    pcheck = stored_series_check(pq, net)
    if pcheck["status"] == "WRITTEN":
        OUT.mkdir(parents=True, exist_ok=True)
        net.to_parquet(pq)
        pcheck["source"] = src.get("path")
    return {"run": run, "board": board, "board_path": bp, "done": done, "cells": cells,
            "refused": refused, "etf": etf, "active": active, "net": net, "spy": spy,
            "series_source": src, "stored_series_check": pcheck}


def hac_readout(run_id: str) -> dict:
    S_ = load_series_of_record(run_id)
    board, cells, etf, active = S_["board"], S_["cells"], S_["etf"], S_["active"]
    src, pcheck, refused, bp = S_["series_source"], S_["stored_series_check"], S_["refused"], S_["board_path"]
    masks = SS.window_masks(active.index)
    primary = [c for c in active.columns if not cells[c]["control"] and cells[c]["primary"]]
    X = SS.factor_spreads(etf).reindex(active.index)
    d_hac, _ = decompose(active, X, masks, board, cells, primary, hac=True)
    d_pl, _ = decompose(active, X, masks, board, cells, primary, hac=False)
    changed, table = [], []
    for rid, v in d_hac.items():
        w = d_pl[rid]
        hp, hh = w.get("alpha_after_pre2024_hedge") or {}, v.get("alpha_after_pre2024_hedge") or {}
        s_ = v.get("sealed") or {}
        row = {"rule": rid, "cell": v["cell"], "hold_months": v["hold_months"],
               "hac_lags": SS.hac_lags_for(v["hold_months"]),
               "in_sealed_top30": v["in_sealed_top30"], "in_dev_top30": v["in_dev_top30"],
               "sealed_vs_spy": v.get("sealed_vs_spy"),
               "hedged_alpha_monthly": hh.get("alpha_monthly"),
               "hedged_t_plain": hh.get("t_plain", hp.get("t")), "hedged_t_hac": hh.get("t_hac"),
               "hedged_mde_plain": hh.get("mde_80_plain", hp.get("mde_80")),
               "hedged_mde_hac": hh.get("mde_80_hac"),
               "t_alpha_2024_26_plain": s_.get("t_alpha"), "t_alpha_2024_26_hac": s_.get("t_alpha_hac"),
               "t_alpha_dev_plain": (v.get("dev") or {}).get("t_alpha"),
               "t_alpha_dev_hac": (v.get("dev") or {}).get("t_alpha_hac"),
               "hedged_se_basis": hh.get("se_used"),
               "verdict_plain": w.get("verdict"), "verdict_hac": v.get("verdict"),
               "verdict_hac_unfloored": (SS.verdict({"t": hh.get("t_hac"), "mde_80": hh.get("mde_80_hac")},
                                                    s_.get("mean_active_monthly"))
                                         if "t_hac" in hh else None),
               "alpha_sign": v.get("alpha_sign"),
               "survives_both_plain": w.get("survives_both"), "survives_both_hac": v.get("survives_both")}
        if v["hold_months"] > 1:
            table.append(row)
        if row["verdict_plain"] != row["verdict_hac"] or row["survives_both_plain"] != row["survives_both_hac"]:
            changed.append(row)
    table.sort(key=lambda r: (-r["hold_months"], r["rule"]))
    doc = {
        "schema": "signal_structure/hac_readout/1", "job": "signal_structure --hac", "run_id": run_id,
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": "HINDSIGHT: every rule was registered 2026-09-26, after every month here",
        "why": ("owed item 2 (adjudication 2026-09-27): Newey-West HAC SEs, lag hold_months - 1 "
                "(Bartlett), for rules held longer than a month; the verdict reads the HAC t when "
                "hold_months > 1; plain and HAC printed side by side"),
        "series_source": src, "stored_series_check": pcheck,
        "board": str(bp.relative_to(REPO)).replace(chr(92), "/"),
        "n_primary_cells": len(primary),
        "n_multi_month_primary": sum(1 for c in primary if cells[c]["hold_months"] > 1),
        "hold_months_mix": {str(k): v for k, v in sorted(Counter(cells[c]["hold_months"] for c in primary).items())},
        "verdicts_plain": dict(sorted(Counter(v.get("verdict") for v in d_pl.values()).items())),
        "verdicts_hac": dict(sorted(Counter(v.get("verdict") for v in d_hac.values()).items())),
        "verdicts_2024_26_top30_plain": dict(sorted(Counter(v.get("verdict") for v in d_pl.values()
                                                            if v["in_sealed_top30"]).items())),
        "verdicts_2024_26_top30_hac": dict(sorted(Counter(v.get("verdict") for v in d_hac.values()
                                                          if v["in_sealed_top30"]).items())),
        "n_changed": len(changed), "changed": changed,
        "multi_month_rules": table,
        "method": ("NW cov = (A'A)^-1 S (A'A)^-1 x n/(n-p); S with Bartlett weights 1 - l/(L+1); "
                   "the hedged alpha is an intercept-only NW SE on the dev-beta-hedged 2024-26 series"),
        "hac_floor": SS.HAC_FLOOR_NOTE,
        "n_changed_unfloored": sum(1 for r in table if r["verdict_hac_unfloored"] != r["verdict_plain"]),
        "n_multi_month_hac_below_plain_hedged": sum(1 for r in table if r["hedged_t_hac"] is not None
                                                    and r["hedged_t_plain"] is not None
                                                    and abs(r["hedged_t_hac"]) > abs(r["hedged_t_plain"])),
        "refused": refused,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    rp = OUT / f"hac_readout_{run_id}.json"
    rp.write_text(json.dumps(doc, indent=1, default=lambda o: None if isinstance(o, float)
                             and not np.isfinite(o) else str(o)), encoding="utf-8")
    print(f"hac readout -> {rp}")
    print(json.dumps({k: doc[k] for k in ("n_primary_cells", "n_multi_month_primary", "hold_months_mix",
                                          "verdicts_plain", "verdicts_hac", "n_changed",
                                          "n_changed_unfloored", "n_multi_month_hac_below_plain_hedged")},
                     indent=1))
    for r in changed:
        print(f"  CHANGED {r['rule']} h={r['hold_months']}: {r['verdict_plain']} -> {r['verdict_hac']} "
              f"(hedged t {_f(r['hedged_t_plain'], 2)} -> {_f(r['hedged_t_hac'], 2)}; "
              f"survives_both {r['survives_both_plain']} -> {r['survives_both_hac']})")
    return doc


# ── MATCHED RANDOM TWINS (reviewer idea 2, owed item 3) ─────────────────────
#
# For each of the run's 2024-26 top-10 rules (top10_for_replication_<run>.json,
# which carries each rule's holdings by rebalance), a random twin matched on
# size band x vol_63 tercile x 12-1 tercile at every rebalance, drawn from the
# same survivorship-free panel and seeded from the rule id. rule - matched twin
# beside rule - random_1 (the stored k50 random control) in dev and 2024-26.

def _twin_panel(run_id: str, dates: list) -> tuple[pd.DataFrame, dict]:
    from backend import config as _cfg
    from backend.services import llm_portfolio as LP
    from backend.services import matched_twins as MT
    from backend.services import xs_ranker as XR
    pq = OUT / f"matched_twins_panel_{run_id}.parquet"
    if pq.exists():
        panel = pd.read_parquet(pq)
        return panel, {"status": "CACHED", "path": str(pq.relative_to(REPO)).replace(chr(92), "/"),
                       "rows": int(len(panel))}
    paths = XR.survivorship_free_paths()
    panel = MT.build_panel(paths, start=_cfg.STRATEGY_LIB_START,
                           delist_return=float(_cfg.STRATEGY_LIB_DELIST_RETURN), decision_dates=dates,
                           min_price=XR.MIN_PRICE, max_price=XR.MAX_PRICE,
                           min_mdv=XR.MIN_MEDIAN_DOLLAR_VOL, min_history=XR.MIN_HISTORY_SESSIONS)
    syms = panel["symbol"].unique()
    excl = {s_ for s_ in syms if s_ in XR.INDEX_PROXIES or LP.is_etf(s_)}
    panel.loc[panel["symbol"].isin(excl), "eligible"] = False
    OUT.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(pq)
    return panel, {"status": "BUILT", "path": str(pq.relative_to(REPO)).replace(chr(92), "/"),
                   "rows": int(len(panel)), "bars": [p_.name for p_ in paths],
                   "start": _cfg.STRATEGY_LIB_START, "n_excluded_etf_or_index": len(excl)}


def matched_twins_readout(run_id: str) -> dict:
    if (LIB / f"holdings_{run_id}.manifest.json").exists():
        return matched_twins_all_cells(run_id)
    return matched_twins_top10(run_id)


def matched_twins_top10(run_id: str) -> dict:
    from backend.services import matched_twins as MT
    from backend.services import strategy_library as SL
    top = json.loads((LIB / f"top10_for_replication_{run_id}.json").read_text(encoding="utf-8"))
    rules = top["rows"]
    pq = OUT / f"monthly_returns_{run_id}.parquet"
    if not pq.exists():
        raise SystemExit(f"REFUSED: {pq.name} absent; run --hac (or the receipt job) for {run_id} first")
    stored = pd.read_parquet(pq)
    rcol = f"random_1@k{SL.RANDOM_PANEL_K}" if hasattr(SL, "RANDOM_PANEL_K") else "random_1@k50"
    if rcol not in stored.columns:
        raise SystemExit(f"REFUSED: {rcol} not in {pq.name}")
    random_1 = stored[rcol].astype(float)
    dates = sorted({m["date"] for r in rules for m in r["monthly_return_series"]})
    panel, pmeta = _twin_panel(run_id, dates)
    by_date = MT.panel_by_date(panel)
    cache: dict = {}
    out_rows = []
    for r in rules:
        rid = r["id"]
        ts = MT.twin_series(r, panel, seed=MT.seed_for(rid), by_date=by_date, cache=cache)
        idx = ts.index
        rule_net = ts["stored_net"].astype(float)
        twin_net = ts["twin_gross"] - ts["cost"].astype(float)
        win = SL.split_windows(idx)
        recon = (ts["rule_gross_recon"] - ts["stored_gross"].astype(float)).abs()
        fb: dict = {}
        for f in ts["fallbacks"]:
            for k_, v_ in (f or {}).items():
                fb[k_] = fb.get(k_, 0) + v_
        row = {"rule": rid, "k": r["k"], "hold_months": r["hold_months"], "universe": r["universe_rule"],
               "weight_rule": r["weight_rule"], "seed": MT.seed_for(rid),
               "recon_check": {"max_abs_gap_gross": float(recon.max()),
                               "median_abs_gap_gross": float(recon.median()),
                               "n_months_gap_gt_1e-6": int((recon > 1e-6).sum())},
               "twin_fallbacks": fb, "board_sealed_vs_spy": (r.get("board") or {}).get("sealed_vs_spy")}
        for w in ("dev", "sealed"):
            row[w] = MT.compare(rule_net, twin_net, random_1, win[w])
        # the twin's own sampling noise: N_EXTRA_DRAWS more seeds
        extra = {"dev": [], "sealed": []}
        for j in range(1, MT.N_EXTRA_DRAWS + 1):
            tj = MT.twin_series(r, panel, seed=MT.seed_for(rid, j), by_date=by_date, cache=cache)
            tn = tj["twin_gross"] - tj["cost"].astype(float)
            for w in extra:
                extra[w].append(MT.compare(rule_net, tn, random_1, win[w])["rule_minus_twin"])
        for w, xs in extra.items():
            xs = [x for x in xs if x is not None]
            row[w]["rule_minus_twin_draws_mean"] = float(np.mean(xs)) if xs else None
            row[w]["rule_minus_twin_draws_sd"] = float(np.std(xs, ddof=1)) if len(xs) > 1 else None
            row[w]["n_extra_draws"] = len(xs)
        out_rows.append(row)

    def med(w, key):
        xs = [x[w][key] for x in out_rows if x[w].get(key) is not None]
        return float(np.median(xs)) if xs else None
    summary = {w: {"median_rule_minus_twin": med(w, "rule_minus_twin"),
                   "median_rule_minus_random_1": med(w, "rule_minus_random_1"),
                   "median_removed_by_matching": med(w, "removed_by_matching"),
                   "median_share_removed": med(w, "share_removed"),
                   "n_rule_minus_twin_gt_0": sum(1 for x in out_rows if (x[w]["rule_minus_twin"] or 0) > 0),
                   "n_rules": len(out_rows)} for w in ("dev", "sealed")}
    doc = {
        "schema": "signal_structure/matched_twins/1", "job": "signal_structure --matched-twins",
        "run_id": run_id, "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": "HINDSIGHT: every rule was registered 2026-09-26, after every month here",
        "why": ("reviewer idea 2 (review 2026-09-27), owed item 3: separate 'the rule selects' from "
                "'the rule buys a style' with a DGTW-style characteristic-matched random twin"),
        "rules_source": f"strategy_library/top10_for_replication_{run_id}.json ({top.get('selection')})",
        "random_1": {"column": rcol, "source": str(pq.relative_to(REPO)).replace(chr(92), "/")},
        "panel": pmeta,
        "matching": ("size band (mega >= 1e9 / large >= 1e8 / mid >= 2e7 / small, on 63-session median "
                     "dollar volume) x vol_63 tercile x mom_252_21 tercile, terciles among the date's "
                     "eligible names; one twin name per held name, same weight, excluding the rule's own "
                     "holdings, without replacement within a date; redrawn at every rebalance; weights "
                     "drift between rebalances; fallback band x vol -> band -> any"),
        "net_convention": ("rule net = the stored series; twin net = twin gross - the RULE's own cost that "
                           "month (the twin trades the same weights in the same bands), so rule - twin "
                           "net = rule gross - twin gross; random_1 = the stored k50 control, net"),
        "windows": top.get("split"),
        "summary": summary, "rows": out_rows,
        "reading": ("removed_by_matching = (rule - random_1) - (rule - twin) = twin - random_1 in CAGR: "
                    "the part of the excess over a uniform random draw that the size / vol / past-return "
                    "cell explains. share_removed = removed / (rule - random_1)."),
    }
    rp = OUT / f"matched_twins_{run_id}.json"
    rp.write_text(json.dumps(doc, indent=1, default=lambda o: None if isinstance(o, float)
                             and not np.isfinite(o) else str(o)), encoding="utf-8")
    print(f"matched twins -> {rp}")
    print(render_twins(doc))
    return doc


# ── matched twins for EVERY primary cell (the factory's holdings sidecar) ─────

def holdings_source(run_id: str) -> dict:
    """The factory's per-cell holdings, monthly series and twin panel for a run,
    each checked against the sha256 its manifest recorded. A file that moved
    since the run refuses by name: the twins would be drawn for a different
    book than the one the board scored."""
    mp = LIB / f"holdings_{run_id}.manifest.json"
    man = json.loads(mp.read_text(encoding="utf-8"))
    out = {"manifest": man, "manifest_path": str(mp.relative_to(REPO)).replace(chr(92), "/")}
    for name in ("holdings", "cell_monthly", "twin_panel"):
        f = REPO / man["files"][name]["path"]
        if not f.exists():
            raise SystemExit(f"REFUSED: {f.name} (named by {mp.name}) is absent")
        if _sha256(f) != man["files"][name]["sha256"]:
            raise SystemExit(f"REFUSED: {f.name} does not match the sha256 in {mp.name}")
        out[name] = pd.read_parquet(f)
    return out


def matched_twins_all_cells(run_id: str) -> dict:
    from backend.services import matched_twins as MT
    from backend.services import strategy_library as SL
    S_ = load_series_of_record(run_id)
    cells, net = S_["cells"], S_["net"]
    rcol = f"random_1@k{SL.RANDOM_PANEL_K}"
    if rcol not in net.columns:
        raise SystemExit(f"REFUSED: {rcol} not in the run's series")
    random_1 = net[rcol].astype(float)
    src = holdings_source(run_id)
    primary = sorted(c for c in net.columns if not cells[c]["control"] and cells[c]["primary"])
    want = {(cells[c]["rule"], cells[c]["k"]) for c in primary}
    H, M = src["holdings"], src["cell_monthly"]
    keyH = list(zip(H["rule"].astype(str), H["k"].astype(int)))
    keyM = list(zip(M["rule"].astype(str), M["k"].astype(int)))
    H = H[[k_ in want for k_ in keyH]]
    M = M[[k_ in want for k_ in keyM]]
    recs = MT.cell_records(H, M)
    grid = sorted(pd.to_datetime(src["cell_monthly"]["date"]).unique())
    panel = src["twin_panel"]
    by_date = MT.panel_by_date(panel)
    cache: dict = {}
    rows, refused = [], []
    diff0, diffm = {}, {}
    for cid in primary:
        key = (cells[cid]["rule"], cells[cid]["k"])
        rec = recs.get(key)
        if rec is None:
            refused.append({"cell": cid, "why": "no holdings in the sidecar"})
            continue
        rec = dict(rec, id=cid)
        try:
            ts = MT.twin_series(rec, panel, seed=MT.seed_for(cid), by_date=by_date, cache=cache,
                                grid=grid)
        except MT.TwinInputMissing as e:
            refused.append({"cell": cid, "why": str(e)})
            continue
        idx = ts.index
        rule_net = ts["stored_net"].astype(float)
        cost = ts["cost"].astype(float)
        twin0 = ts["twin_gross"] - cost
        win = SL.split_windows(idx)
        recon = (ts["rule_gross_recon"] - ts["stored_gross"].astype(float)).abs()
        board_gap = (rule_net - net[cid].reindex(idx)).abs()
        fb: dict = {}
        for f in ts["fallbacks"]:
            for k_, v_ in (f or {}).items():
                fb[k_] = fb.get(k_, 0) + v_
        twins = [twin0]
        for j in range(1, MT.N_EXTRA_DRAWS + 1):
            tj = MT.twin_series(rec, panel, seed=MT.seed_for(cid, j), by_date=by_date, cache=cache,
                                grid=grid)
            twins.append(tj["twin_gross"] - cost)
        tmean = pd.concat(twins, axis=1).mean(axis=1)
        row = {"cell": cid, "rule": key[0], "k": key[1], "family": cells[cid]["family"],
               "hold_months": cells[cid]["hold_months"], "seed": MT.seed_for(cid),
               "recon_check": {"max_abs_gap_gross": float(recon.max()),
                               "n_months_gap_gt_1e-6": int((recon > 1e-6).sum()),
                               "max_abs_gap_net_vs_series_of_record": float(board_gap.max())},
               "twin_fallbacks": fb}
        for w in ("dev", "sealed"):
            r_ = MT.compare(rule_net, twin0, random_1, win[w])
            xs = [MT.compare(rule_net, t, random_1, win[w])["rule_minus_twin"] for t in twins[1:]]
            xs = [x for x in xs if x is not None]
            r_["rule_minus_twin_draws_mean"] = float(np.mean(xs)) if xs else None
            r_["rule_minus_twin_draws_sd"] = float(np.std(xs, ddof=1)) if len(xs) > 1 else None
            r_["n_extra_draws"] = len(xs)
            dm = (rule_net - tmean)[win[w]].dropna()
            se = float(dm.std(ddof=1) / np.sqrt(len(dm))) if len(dm) > 1 else float("nan")
            r_["mean_monthly_rule_minus_twin21"] = float(dm.mean()) if len(dm) else None
            r_["t_monthly_rule_minus_twin21"] = (float(dm.mean() / se) if np.isfinite(se) and se > 0
                                                 else None)
            row[w] = r_
        rows.append(row)
        diff0[cid] = rule_net - twin0
        diffm[cid] = rule_net - tmean

    def med(w, key_):
        xs = [x[w][key_] for x in rows if x[w].get(key_) is not None]
        return float(np.median(xs)) if xs else None
    summary = {w: {"n_cells": len(rows),
                   "median_rule_minus_twin": med(w, "rule_minus_twin"),
                   "median_rule_minus_random_1": med(w, "rule_minus_random_1"),
                   "median_removed_by_matching": med(w, "removed_by_matching"),
                   "median_share_removed": med(w, "share_removed"),
                   "median_twin_draw_sd": med(w, "rule_minus_twin_draws_sd"),
                   "n_rule_minus_twin_gt_0": sum(1 for x in rows if (x[w]["rule_minus_twin"] or 0) > 0),
                   "n_t_twin21_ge_2": sum(1 for x in rows
                                          if (x[w].get("t_monthly_rule_minus_twin21") or -9) >= 2),
                   "n_t_twin21_le_minus_2": sum(1 for x in rows
                                                if (x[w].get("t_monthly_rule_minus_twin21") or 9) <= -2)}
               for w in ("dev", "sealed")}
    both = sorted(x["cell"] for x in rows
                  if (x["dev"].get("t_monthly_rule_minus_twin21") or -9) >= 2
                  and (x["sealed"].get("t_monthly_rule_minus_twin21") or -9) >= 2)
    pq = OUT / f"matched_twins_monthly_{run_id}.parquet"
    frame = pd.concat({"rule_minus_twin21": pd.DataFrame(diffm), "rule_minus_twin0": pd.DataFrame(diff0)},
                      axis=1)
    frame.index.name = "decision_date"
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(pq)
    doc = {
        "schema": "signal_structure/matched_twins/2", "job": "signal_structure --matched-twins (all cells)",
        "run_id": run_id, "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": "HINDSIGHT: every rule was registered 2026-09-26, after every month here",
        "why": ("reviewer idea 2 for EVERY primary cell: the factory now stores each cell's holdings "
                "(holdings_<run>.parquet), so the twin no longer depends on the top-10 file"),
        "rules_source": src["manifest_path"],
        "holdings_sha256": {k_: v_["sha256"] for k_, v_ in src["manifest"]["files"].items()},
        "random_1": {"column": rcol, "source": "the run's series of record"},
        "panel": {"source": src["manifest"]["files"]["twin_panel"]["path"],
                  "rows": int(len(panel)), "what": "the factory's own panel of this run"},
        "matching": ("size band (mega >= 1e9 / large >= 1e8 / mid >= 2e7 / small, 63-session median "
                     "dollar volume) x vol_63 tercile x mom_252_21 tercile among the date's eligible "
                     "names; one twin per held name, same weight, excluding the rule's own names, "
                     "without replacement within a date; redrawn at every rebalance; weights held "
                     "between rebalances as the factory holds them; fallback band x vol -> band -> any"),
        "net_convention": ("twin net = twin gross - the RULE's own cost that month; draw 0 is seeded "
                           "from the cell id, draws 1-20 give the twin's sampling sd; `twin21` = the mean "
                           "of all 21 draws' net, the lower-noise twin the family pool reads"),
        "month_check": ("a cell whose monthly series has a hole inside its span, or a month off the "
                        "panel, REFUSES by name (matched_twins.check_months)"),
        "summary": summary, "cells_t_twin21_ge_2_both_windows": both,
        "n_primary_cells": len(primary), "n_refused": len(refused), "refused": refused,
        "series": str(pq.relative_to(REPO)).replace(chr(92), "/"),
        "rows": rows,
    }
    rp = OUT / f"matched_twins_{run_id}.json"
    rp.write_text(json.dumps(doc, indent=1, default=lambda o: None if isinstance(o, float)
                             and not np.isfinite(o) else str(o)), encoding="utf-8")
    print(f"matched twins (all {len(rows)} primary cells, {len(refused)} refused) -> {rp}")
    for w, v in summary.items():
        print(f"  {w}: median rule - twin {_pct(v['median_rule_minus_twin'])}, rule - random_1 "
              f"{_pct(v['median_rule_minus_random_1'])}, removed {_pct(v['median_removed_by_matching'])} "
              f"(share {_pct(v['median_share_removed'], 0)}); beats twin {v['n_rule_minus_twin_gt_0']}/"
              f"{v['n_cells']}; t(twin21) >= 2: {v['n_t_twin21_ge_2']}, <= -2: {v['n_t_twin21_le_minus_2']}")
    print(f"  t(rule - twin21) >= 2 in BOTH windows: {len(both)} {both[:10]}")
    for r_ in refused:
        print(f"  REFUSED {r_['cell']}: {r_['why']}")
    return doc


# ── pooled per-family tests (reviewer idea 3) ────────────────────────────────

def family_pool_readout(run_id: str) -> dict:
    from backend.services import family_pool as FP
    from backend.services import strategy_library as SL
    S_ = load_series_of_record(run_id)
    cells, net, active, etf = S_["cells"], S_["net"], S_["active"], S_["etf"]
    idx = active.index
    masks = SS.window_masks(idx)
    X = SS.factor_spreads(etf).reindex(idx)
    rp = SL.random_panel(net)
    vs = {"random_panel": net.sub(rp, axis=0), "spy": active}
    primary = sorted(c for c in net.columns if not cells[c]["control"] and cells[c]["primary"])
    fams, small = FP.families(cells, primary)
    tw_path = OUT / f"matched_twins_monthly_{run_id}.parquet"
    tw = pd.read_parquet(tw_path)["rule_minus_twin21"] if tw_path.exists() else None
    # single-rule reference (same estimators), library-wide, 2024-26 and dev
    ref: dict = {}
    for w in ("dev", "sealed"):
        ses, oses = [], []
        for c in primary:
            try:
                ses.append(FP.mean_test(vs["random_panel"][c][masks[w]].dropna(),
                                        hold_months=cells[c]["hold_months"])["se_used"])
            except FP.FamilyPoolRefused:
                pass
            o = _fit(active[c][masks[w]], X[masks[w]], cells[c]["hold_months"])
            if "se_alpha_used" in o:
                oses.append(o["se_alpha_used"])
        ref[w] = {"median_se_mean_vs_panel": float(np.median(ses)) if ses else None,
                  "median_mde_mean_vs_panel": float(SS.MDE_Z * np.median(ses)) if ses else None,
                  "median_se_etf_alpha_vs_spy": float(np.median(oses)) if oses else None,
                  "median_mde_etf_alpha_vs_spy": float(SS.MDE_Z * np.median(oses)) if oses else None,
                  "n_cells": len(ses)}
    rows, pooled_full = [], {"random_panel": {}, "spy": {}, "twin": {}}
    for f, members in fams.items():
        hold = max(cells[c]["hold_months"] for c in members)
        row = {"family": f, "n_rules": len(members), "hold_months_used": hold, "members": members}
        for b, A in vs.items():
            t_ = FP.family_test(A[members], masks, family=f, hold_months=hold, X=X)
            t_.pop("members", None)
            row[f"vs_{b}"] = t_
            pooled_full[b][f] = FP.pool(A[members])[0]
        if tw is not None:
            have = [c for c in members if c in tw.columns]
            if len(have) >= FP.MIN_RULES:
                t_ = FP.family_test(tw[have].reindex(idx), masks, family=f, hold_months=hold, X=None)
                t_.pop("members", None)
                t_["n_rules_with_twins"] = len(have)
                row["rule_minus_twin"] = t_
                pooled_full["twin"][f] = FP.pool(tw[have].reindex(idx))[0]
            else:
                row["rule_minus_twin"] = {"status": "REFUSED",
                                          "why": f"{len(have)} member(s) with twins < {FP.MIN_RULES}"}
        else:
            row["rule_minus_twin"] = {"status": "NOT_RUN", "why": f"{tw_path.name} absent: run --matched-twins"}
        rows.append(row)
    n_f = len(fams)
    dsr = {b: FP.dsr_over_families(v, n_f) for b, v in pooled_full.items() if v}
    best = {}
    for b, d in dsr.items():
        ok = {k_: v_ for k_, v_ in d.items() if v_ is not None}
        if ok:
            k_ = max(ok, key=ok.get)
            best[b] = {"family": k_, "dsr_at_n_families": ok[k_], "n_families": n_f}

    alpha_both = {b: sorted(r["family"] for r in rows if (r.get(f"vs_{b}") or {}).get("mean_t_ge_2_both_windows"))
                  for b in vs}
    alpha_both_etf = {b: sorted(r["family"] for r in rows
                                if (r.get(f"vs_{b}") or {}).get("ols_alpha_t_ge_2_both_windows"))
                      for b in vs}
    twin_both = sorted(r["family"] for r in rows if (r.get("rule_minus_twin") or {}).get("mean_t_ge_2_both_windows"))
    pooled_mde = {w: float(np.median([r["vs_random_panel"]["windows"][w]["pooled"]["mde_80"] for r in rows
                                      if "mde_80" in r["vs_random_panel"]["windows"][w]["pooled"]]))
                  for w in ("dev", "sealed")}
    pooled_etf_se = [((r["vs_spy"]["windows"]["sealed"]["ols"]) or {}).get("se_alpha_used") for r in rows]
    pooled_etf_se = [x for x in pooled_etf_se if x is not None]
    doc = {
        "schema": "signal_structure/family_pool/1", "job": "signal_structure --family-pool",
        "run_id": run_id, "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": "HINDSIGHT: every rule was registered 2026-09-26, after every month here",
        "why": ("reviewer idea 3 (review 2026-09-27 §8): the equal-weight mean of a family's primary "
                "cells' monthly active returns as ONE series; multiplicity over FAMILIES"),
        "series_source": S_["series_source"].get("path"),
        "method": {
            "pooled": "equal-weight mean across the family's primary cells present that month",
            "benchmarks": ("vs_random_panel = net - mean(random_1..3 @k50) (the panel's own random "
                           "portfolio); vs_spy = net - SPY; rule_minus_twin = net - the mean of 21 "
                           "characteristic-matched twin draws' net"),
            "se": ("plain sd/sqrt(T) and Newey-West at lag max(member hold) - 1; used = max(plain, HAC); "
                   "MDE = 2.8 x used SE"),
            "effective_n": "n / (1 + (n-1) mean pairwise rho), rho floored at 0, printed per window",
            "verdict": ("signal_structure.verdict on the 2024-26 pooled series hedged with its DEV "
                        "ETF betas (SMH, IWM, MTUM, USMV, QUAL, VLUE minus SPY); rule_minus_twin reads "
                        "its plain pooled 2024-26 mean"),
            "alpha_both_windows": "pooled mean t_used >= 2 in dev AND in 2024-26",
            "windows": "entry-date split: dev = entry < 2024, 2024-26 = entry >= 2024-01, full = all"},
        "n_primary_cells": len(primary), "n_families_pooled": n_f,
        "families_too_small": small,
        "single_rule_reference": ref,
        "pooled_median_mde_vs_panel": pooled_mde,
        "pooled_median_se_etf_alpha_vs_spy_2024_26": float(np.median(pooled_etf_se)) if pooled_etf_se else None,
        "dsr_at_n_families": dsr, "best_family_by_dsr": best,
        "alpha_both_windows_mean": alpha_both, "alpha_both_windows_etf_alpha": alpha_both_etf,
        "rule_minus_twin_t_ge_2_both_windows": twin_both,
        "verdicts": {b: dict(sorted(Counter((r.get(f"vs_{b}") or {}).get("verdict") for r in rows).items()))
                     for b in vs},
        "rows": rows,
    }
    rpth = OUT / f"family_pool_{run_id}.json"
    rpth.write_text(json.dumps(doc, indent=1, default=lambda o: None if isinstance(o, float)
                               and not np.isfinite(o) else str(o)), encoding="utf-8")
    md = render_family_pool(doc)
    (OUT / f"family_pool_{run_id}.md").write_text(md, encoding="utf-8")
    print(f"family pool -> {rpth}")
    print(md)
    return doc


def render_family_pool(doc: dict) -> str:
    def g(r, path):
        x = r
        for p_ in path:
            x = (x or {}).get(p_) if isinstance(x, dict) else None
        return x

    L = [f"## Pooled family tests -- run {doc['run_id']} (HINDSIGHT)", "",
         f"{doc['n_families_pooled']} families with >= 3 primary rules ({doc['n_primary_cells']} primary cells); "
         f"too small to pool: {len(doc['families_too_small'])}.", "",
         "Pooled monthly mean vs the random panel (t = used SE; MDE at 80% power), n_eff in 2024-26, "
         "the verdict on the dev-hedged 2024-26 alpha vs SPY, and rule - matched twin (21-draw mean):", "",
         "| family | n | n_eff 24-26 (rho) | vs panel dev: mean (t) | vs panel 24-26: mean (t) | MDE 24-26 | "
         "vs SPY ETF alpha dev (t) | 24-26 (t) | verdict (vs SPY) | rule-twin dev (t) | rule-twin 24-26 (t) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in doc["rows"]:
        P, S = r["vs_random_panel"]["windows"], r["vs_spy"]["windows"]
        en = P["sealed"]["effective_n"]
        tw = r.get("rule_minus_twin") or {}
        twd = g(tw, ["windows", "dev", "pooled"]) or {}
        tws = g(tw, ["windows", "sealed", "pooled"]) or {}

        def mt(x):
            return (f"{_pct(x.get('mean_monthly'), 2)} ({_f(x.get('t_used'), 2)})"
                    if x and "mean_monthly" in x else "n/a")

        def ot(x):
            return (f"{_pct(x.get('alpha_monthly'), 2)} ({_f(x.get('t_alpha_used'), 2)})"
                    if x and "alpha_monthly" in x else "n/a")
        L.append(f"| {r['family']} | {r['n_rules']} | {_f(en.get('n_eff'), 1)} ({_f(en.get('mean_pair_rho'), 2)}) | "
                 f"{mt(P['dev']['pooled'])} | {mt(P['sealed']['pooled'])} | "
                 f"{_pct(P['sealed']['pooled'].get('mde_80'), 2)} | {ot(S['dev']['ols'])} | {ot(S['sealed']['ols'])} | "
                 f"{r['vs_spy'].get('verdict')} | {mt(twd)} | {mt(tws)} |")
    ref = doc["single_rule_reference"]
    L += ["", f"Single rule, median, same estimator: MDE of the mean vs panel dev "
              f"{_pct(ref['dev']['median_mde_mean_vs_panel'], 2)}/mo, 2024-26 "
              f"{_pct(ref['sealed']['median_mde_mean_vs_panel'], 2)}/mo; pooled family median "
              f"{_pct(doc['pooled_median_mde_vs_panel']['dev'], 2)} / "
              f"{_pct(doc['pooled_median_mde_vs_panel']['sealed'], 2)}/mo. ETF-alpha SE 2024-26: single "
              f"{_pct(ref['sealed']['median_se_etf_alpha_vs_spy'], 2)} (MDE "
              f"{_pct(ref['sealed']['median_mde_etf_alpha_vs_spy'], 2)}), pooled "
              f"{_pct(doc['pooled_median_se_etf_alpha_vs_spy_2024_26'], 2)} (MDE "
              f"{_pct((doc['pooled_median_se_etf_alpha_vs_spy_2024_26'] or 0) * SS.MDE_Z, 2)}).",
          f"Alpha (pooled mean t >= 2) in BOTH windows: vs panel {doc['alpha_both_windows_mean']['random_panel']}; "
          f"vs SPY {doc['alpha_both_windows_mean']['spy']}. ETF alpha t >= 2 both: "
          f"vs panel {doc['alpha_both_windows_etf_alpha']['random_panel']}; vs SPY {doc['alpha_both_windows_etf_alpha']['spy']}.",
          f"Rule - matched twin, pooled t >= 2 in BOTH windows: {doc['rule_minus_twin_t_ge_2_both_windows']}.",
          f"Best family by DSR at n = {doc['n_families_pooled']} families: "
          + "; ".join(f"{b}: {v['family']} {_f(v['dsr_at_n_families'], 3)}" for b, v in doc["best_family_by_dsr"].items()),
          f"Verdicts: {doc['verdicts']}"]
    return "\n".join(L) + "\n"


def render_twins(doc: dict) -> str:
    L = [f"## Matched random twins -- run {doc['run_id']} (2024-26 top-10)", "",
         "| rule | k | hold | recon gap (max) | dev: rule - twin | dev: rule - random_1 | dev removed | "
         "24-26: rule - twin (draw sd) | 24-26: rule - random_1 | 24-26 removed | share removed 24-26 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in doc["rows"]:
        d, s_ = x["dev"], x["sealed"]
        L.append(f"| `{x['rule']}` | {x['k']} | {x['hold_months']} | {x['recon_check']['max_abs_gap_gross']:.1e} | "
                 f"{_pct(d['rule_minus_twin'])} | {_pct(d['rule_minus_random_1'])} | {_pct(d['removed_by_matching'])} | "
                 f"{_pct(s_['rule_minus_twin'])} ({_pct(s_.get('rule_minus_twin_draws_sd'))}) | "
                 f"{_pct(s_['rule_minus_random_1'])} | {_pct(s_['removed_by_matching'])} | "
                 f"{_pct(s_['share_removed'], 0)} |")
    for w, v in doc["summary"].items():
        L.append(f"\n{w}: median rule - twin {_pct(v['median_rule_minus_twin'])}, median rule - random_1 "
                 f"{_pct(v['median_rule_minus_random_1'])}, median removed {_pct(v['median_removed_by_matching'])}; "
                 f"rule beats its twin in {v['n_rule_minus_twin_gt_0']} of {v['n_rules']}.")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=DEFAULT_RUN)
    ap.add_argument("--refresh-etf", action="store_true")
    ap.add_argument("--rekey", action="store_true",
                    help="hold-month re-key + panel benchmarks of --run-id's board, from stored series")
    ap.add_argument("--hac", action="store_true",
                    help="Newey-West readout (plain vs HAC verdicts) of --run-id, from stored series")
    ap.add_argument("--matched-twins", action="store_true",
                    help=("characteristic-matched random twins: every primary cell when the factory "
                          "stored holdings for --run-id, else its 2024-26 top-10"))
    ap.add_argument("--family-pool", action="store_true",
                    help="pooled per-family tests (vs panel, vs SPY, rule - matched twin)")
    a = ap.parse_args(argv)
    run_id = a.run_id
    jobs = [(a.rekey, rekey), (a.hac, hac_readout), (a.matched_twins, matched_twins_readout),
            (a.family_pool, family_pool_readout)]
    if any(on for on, _ in jobs):
        for on, fn in jobs:
            if on:
                fn(run_id)
        return 0
    if (LIB / f"leaderboard_{run_id}.INVALID.md").exists():
        raise SystemExit(f"REFUSED: run {run_id} is marked INVALID")
    run = json.loads((LIB / f"run_{run_id}.json").read_text(encoding="utf-8"))
    board = json.loads((LIB / f"leaderboard_{run_id}.json").read_text(encoding="utf-8"))
    ck, ck_src = load_checkpoint(run)
    done = ck["state"]["done"]
    rows_by_rule = {r["id"]: r for r in board["all_rows"]}

    cells, refused = SS.cells_from_checkpoint(done)
    # attach the checkpoint's window numbers to each cell
    for cid, c in cells.items():
        cc = done[c["rule"]]["cells"][str(c["k"])]
        c["dev_vs_spy"], c["sealed_vs_spy"] = cc.get("dev_vs_spy"), cc.get("sealed_vs_spy")
        c["dsr_board"] = None

    etf, etf_meta = etf_monthly(a.refresh_etf)
    grid = pd.DatetimeIndex(etf.index)
    active, ref2 = SS.active_frame(cells, grid)
    refused += ref2
    for cid, _ in ref2:
        cells.pop(cid, None)
    active = active.loc[active.notna().any(axis=1)]
    SS.require_months(len(active), "library active-return frame")
    spy = etf["SPY"].reindex(active.index)
    net = active.add(spy, axis=0)
    gap = SS.reconstruction_gap(cells, net)
    OUT.mkdir(parents=True, exist_ok=True)
    pq = OUT / f"monthly_returns_{run_id}.parquet"
    net.index.name = "decision_date"
    parquet_check = stored_series_check(pq, net)
    if parquet_check["status"] == "WRITTEN":
        net.to_parquet(pq)

    masks = SS.window_masks(active.index)
    trial_cells = [c for c in active.columns if not cells[c]["control"]]
    primary = [c for c in trial_cells if cells[c]["primary"]]
    n_cells = len(trial_cells)

    # dev DSR per cell at the nominal cell count (the representative criterion)
    dev_dsr, full_dsr, sealed_dsr = {}, {}, {}
    for c in active.columns:
        s = active[c]
        dv = s[masks["dev"]].dropna()
        sv = s[masks["sealed"]].dropna()
        dev_dsr[c] = SS.dsr_at(dv, n_cells) if len(dv) >= 8 else None
        full_dsr[c] = SS.dsr_at(s.dropna(), n_cells)
        sealed_dsr[c] = SS.dsr_at(sv, n_cells) if len(sv) >= 8 else None

    full_mask = np.ones(len(active), dtype=bool)
    blocks = {}
    for scope, cols in (("cells", trial_cells), ("rules", primary)):
        for wname, mk in (("dev", masks["dev"]), ("sealed", masks["sealed"]), ("full", full_mask)):
            blocks[f"{scope}_{wname}"] = cluster_block(active[cols], mk, cells, dev_dsr,
                                                       rows_by_rule, wname)

    # DSR at n = clusters vs n = cells, for every representative; report the best
    def dsr_compare(block_key: str, window: str) -> dict:
        b = blocks[block_key]
        nk = b["n_clusters"]
        best = None
        for cl in b["clusters"]:
            rep = cl["representative"]
            s = active[rep]
            s = s[masks[window]] if window in masks else s
            s = s.dropna()
            if len(s) < 8:
                continue
            row = {"representative": rep, "n_months": int(len(s)),
                   "dsr_at_n_cells": SS.dsr_at(s, n_cells), "dsr_at_n_clusters": SS.dsr_at(s, nk),
                   "n_cells": n_cells, "n_clusters": nk}
            if best is None or (row["dsr_at_n_clusters"] or 0) > (best["dsr_at_n_clusters"] or 0):
                best = row
        return best or {}
    dsr_cmp = {"full": dsr_compare("cells_full", "full"),
               "dev": dsr_compare("cells_dev", "dev"),
               "sealed": dsr_compare("cells_sealed", "sealed")}
    # the board's own best-DSR cell, at both counts
    best_board = max(trial_cells, key=lambda c: full_dsr.get(c) or 0)
    dsr_cmp["board_best_cell"] = {
        "cell": best_board, "dsr_at_n_cells": full_dsr.get(best_board),
        "dsr_at_n_clusters_full": SS.dsr_at(active[best_board].dropna(), blocks["cells_full"]["n_clusters"]),
        "n_clusters_full": blocks["cells_full"]["n_clusters"]}

    # ── decomposition (review 2026-09-27 §1, §7) ──────────────────────────
    # Every PRIMARY cell (not only the two top-30s), each alpha with its SE and
    # MDE, and the verdict on the alpha left after the EX-ANTE hedge: the dev
    # (pre-2024) betas applied to the 2024-26 spreads. The in-sample "SMH+MTUM
    # share" label is deleted: it could not tell beta from no power.
    X = SS.factor_spreads(etf).reindex(active.index)
    decomp, beta_pairs = decompose(active, X, masks, board, cells, primary)
    decomp_summary = summarise_decomposition(decomp, beta_pairs)
    # the ETF spreads' own collinearity in the sealed window (a 32-block regression on 6 of them)
    xs = X[masks["sealed"]].dropna()
    xcorr = xs.corr().round(2).to_dict()

    # ── the bet count as a CURVE, on active AND residual returns (§3) ──────
    curve = bet_count_curve(active[primary], net[primary], X)
    res6 = SS.residualise(active[primary], X)
    ncl_res = int(SS.cluster(SS.corr_matrix(res6), rho_cut=SS.RHO_CUT).nunique())
    dsr_resid = {c: {"n_residual_clusters": ncl_res,
                     "dsr_at_n_residual_clusters": SS.dsr_at(active[c].dropna(), ncl_res),
                     "dsr_at_n_cells": full_dsr.get(c), "n_cells": n_cells}
                 for c in sorted({best_board, SS.cell_id("mom_12_1_q", 20)}) if c in active.columns}

    # ── within-cluster spread and rank persistence (§5): the construction test
    within = within_cluster(blocks["rules_full"], active, net, spy, masks, done, cells, X)

    # ── lead-lag (full window, rule-level representatives) ────────────────
    mom_cell = SS.cell_id("mom_12_1", 20)
    xs_series = {"mom_12_1_active": active[mom_cell], "SMH-SPY": X["SMH-SPY"]}
    ll_rows, n_tests = [], 0
    reps = [cl["representative"] for cl in blocks["rules_full"]["clusters"]]
    for rep in reps:
        y = active[rep]
        for xname, x in xs_series.items():
            for lag in SS.LEAD_LAGS:
                for direction in ("x_leads_rule", "rule_leads_x"):
                    if lag == 0 and direction == "rule_leads_x":
                        continue
                    if direction == "x_leads_rule":
                        rho, n = SS.lagged_corr(y, x, lag)
                    else:
                        rho, n = SS.lagged_corr(x, y, lag)
                    if lag > 0:
                        n_tests += 1
                    ll_rows.append({"rep": rep, "x": xname, "lag": lag, "direction": direction,
                                    "rho": rho, "n": n})
    hyps = [r for r in ll_rows if r["lag"] > 0 and np.isfinite(r["rho"]) and abs(r["rho"]) >= SS.LEAD_LAG_RHO]
    n_typ = int(np.median([r["n"] for r in ll_rows if r["lag"] > 0])) if ll_rows else 0
    from math import erf, sqrt
    z = SS.LEAD_LAG_RHO * sqrt(max(n_typ - 3, 1))
    p_two = 1 - erf(z / sqrt(2))
    lead_lag = {"series": list(xs_series), "n_tests_positive_lag": n_tests, "typical_n": n_typ,
                "null_p_abs_rho_ge_0_3": p_two, "expected_false_hits": n_tests * p_two,
                "hypotheses": sorted(hyps, key=lambda r: -abs(r["rho"])),
                "lag0": [r for r in ll_rows if r["lag"] == 0],
                "news_flow": {"status": "SKIPPED",
                              "why": ("news_corpus/alpaca_benzinga_news stamps first_seen_utc at PULL time "
                                      "(all 36,720 rows = 2026-09) and its published_utc covers 2015-01..2015-02 "
                                      "only; no monthly news-flow count exists for 2017-2026")}}

    # ── frozen forward books: same bet? ────────────────────────────────────
    bridge = json.loads((BRIDGE / "bridge_2026-09-26.json").read_text(encoding="utf-8"))
    books = {}
    for b in bridge["rows"]:
        rr = rows_by_rule.get(b["rule"])
        if rr is None:
            books[b["book"]] = {"rule": b["rule"], "cell": None, "why": "no backtest row"}
            continue
        cid = SS.cell_id(b["rule"], rr["k"])
        books[b["book"]] = {"rule": b["rule"], "cell": cid if cid in active.columns else None,
                            "cluster_full": blocks["rules_full"]["labels"].get(cid),
                            "cluster_dev": blocks["rules_dev"]["labels"].get(cid),
                            "cluster_sealed": blocks["rules_sealed"]["labels"].get(cid)}
    bcells = sorted({v["cell"] for v in books.values() if v.get("cell")})
    bc = {w: active.loc[mk if w != "full" else full_mask, bcells].corr(min_periods=SS.MIN_PAIR_MONTHS)
          for w, mk in (("full", full_mask), ("dev", masks["dev"]), ("sealed", masks["sealed"]))}
    pairs = []
    for i, p in enumerate(bcells):
        for q in bcells[i + 1:]:
            rf, rd, rs = (bc[w].loc[p, q] for w in ("full", "dev", "sealed"))
            if np.isfinite(rf) and rf >= SS.RHO_CUT:
                pairs.append({"a": p, "b": q, "rho_full": float(rf),
                              "rho_dev": float(rd) if np.isfinite(rd) else None,
                              "rho_sealed": float(rs) if np.isfinite(rs) else None})
    same_bet_groups = {}
    for bk, v in books.items():
        if v.get("cluster_full") is not None:
            same_bet_groups.setdefault(int(v["cluster_full"]), []).append(bk)
    same_bet_groups = {k: v for k, v in same_bet_groups.items() if len(v) > 1}

    # ── duplicates to deprioritize: same full cluster AND rho >= 0.8 with the rep in dev and sealed
    dup = []
    for cl in blocks["rules_full"]["clusters"]:
        rep = cl["representative"]
        for m in cl["members"]:
            if m == rep:
                continue
            ok = True
            rhos = {}
            for w in ("dev", "sealed"):
                d2 = active.loc[masks[w], [rep, m]].dropna()
                rho = float(d2[rep].corr(d2[m])) if len(d2) >= SS.MIN_PAIR_MONTHS else float("nan")
                rhos[w] = rho
                ok = ok and np.isfinite(rho) and rho >= SS.RHO_CUT
            if ok:
                dup.append({"rule": cells[m]["rule"], "duplicate_of": cells[rep]["rule"],
                            "family": cells[m]["family"], "rho_dev": rhos["dev"],
                            "rho_sealed": rhos["sealed"], "status": "DEPRIORITIZED"})

    receipt = {
        "job": "signal_structure", "run_id": run_id, "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": "HINDSIGHT: every rule was registered 2026-09-26, after every month here",
        "series_source": ck_src, "panel_fingerprint": run["panel"]["fingerprint"],
        "monthly_returns_parquet": str(pq.relative_to(REPO)),
        "n_months": int(len(active)), "span": [str(active.index.min().date()), str(active.index.max().date())],
        "n_cells_with_series": int(active.shape[1]), "n_trial_cells": n_cells,
        "n_primary_rule_cells": len(primary), "refused": refused,
        "reconstruction_check": {**gap, "what": "net = active + SPY(yfinance, this pull) vs the checkpoint's by_year net"},
        "etf": etf_meta,
        "distinct_bets": {k: {kk: v[kk] for kk in ("window", "n_series", "n_clusters", "n_excluded_short")}
                          for k, v in blocks.items()},
        "clusters": {k: v["clusters"] for k, v in blocks.items()},
        "dsr_compare": dsr_cmp,
        "decomposition": decomp,
        "decomposition_summary": decomp_summary,
        "etf_spread_corr_sealed": xcorr,
        "bet_count_curve": curve,
        "dsr_at_residual_clusters": dsr_resid,
        "within_cluster": within,
        "within_cluster_persistence": persistence_summary(within),
        "stored_series_check": parquet_check,
        "lead_lag": lead_lag,
        "frozen_books": books, "frozen_book_pairs_rho_ge_0_8_full": pairs,
        "frozen_books_same_full_cluster": same_bet_groups,
        "deprioritized_duplicates": dup,
        "notes": [
            "active = rule net - SPY per monthly period; correlation is pairwise-complete, "
            f"a series needs >= {SS.MIN_PAIR_MONTHS} months in the window",
            "clusters: average linkage on 1 - rho, cut at rho 0.8 (distance 0.2); NaN rho = distance 1",
            "representative = highest DEV-window DSR at n = trial cells",
            "OLS standard errors: plain for hold-1 rules; for hold > 1 (serially dependent monthly "
            "active returns) Newey-West HAC at lag hold - 1 is printed beside the plain one and the "
            "verdict reads it (2026-09-27, owed item 2)",
            "32 sealed blocks and 7 parameters: a t of 2 on alpha is one-in-twenty by noise per rule",
            "MDE = 2.8 x SE (two-sided 5%, 80% power); at ~32 blocks the MDE is ~2.5%/month, so "
            "t < 1 is mostly NO POWER, not no alpha (review 2026-09-27 §1)",
            "verdict (on the ex-ante hedged alpha = 2024-26 active - dev betas x 2024-26 spreads): "
            "ALPHA_DETECTED |t| >= 2 (sign printed); BETA_EXPLAINS |t| < 1 AND MDE < |mean "
            "2024-26 active|; else CANNOT_DISTINGUISH",
        ],
    }
    rp = OUT / f"signal_structure_{run_id}.json"
    rp.write_text(json.dumps(receipt, indent=1, default=lambda o: None if isinstance(o, float) and not np.isfinite(o) else str(o)),
                  encoding="utf-8")
    md = render_tables(receipt, cells)
    (OUT / f"tables_{run_id}.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"\nreceipt {rp}\nparquet {pq}")
    return 0


def render_tables(r: dict, cells: dict) -> str:
    L = [f"## Distinct bets (rho cut 0.8) -- run {r['run_id']}", "",
         "| scope | window | series | clusters (distinct bets) | excluded (<24 months) |", "|---|---|---|---|---|"]
    for k, v in r["distinct_bets"].items():
        sc = k.split("_")[0]
        L.append(f"| {sc} | {v['window']} | {v['n_series']} | **{v['n_clusters']}** | {v['n_excluded_short']} |")
    L += ["", f"Reconstruction check: max |by-year net gap| = {r['reconstruction_check']['max_abs_gap_by_year']:.2e} "
               f"over {r['reconstruction_check']['n_year_cells_compared']} rule-years.", ""]
    dc = r["dsr_compare"]
    L += ["## DSR at n = clusters vs n = cells", "",
          "| window | best representative | months | DSR @ n=cells | n cells | DSR @ n=clusters | n clusters |",
          "|---|---|---|---|---|---|---|"]
    for w in ("full", "dev", "sealed"):
        d = dc.get(w) or {}
        if d:
            L.append(f"| {w} | `{d['representative']}` | {d['n_months']} | {_f(d['dsr_at_n_cells'])} | "
                     f"{d['n_cells']} | {_f(d['dsr_at_n_clusters'])} | {d['n_clusters']} |")
    b = dc["board_best_cell"]
    L += ["", f"Board's best full-sample DSR cell `{b['cell']}`: {_f(b['dsr_at_n_cells'])} at n={r['n_trial_cells']}, "
              f"{_f(b['dsr_at_n_clusters_full'])} at n={b['n_clusters_full']} clusters.", ""]
    for key, title in (("rules_full", "Rule-level clusters, full window (members > 1 first)"),
                       ("rules_sealed", "Rule-level clusters, 2024-26 window (members > 1 only)"),
                       ("rules_dev", "Rule-level clusters, dev window (members > 1 only)")):
        cl = r["clusters"][key]
        L += [f"## {title}", "",
              "| # | n | mean inner rho | representative | rep dev vs SPY | rep 2024-26 vs SPY | beat SPY both | families | members |",
              "|---|---|---|---|---|---|---|---|---|"]
        for c in cl:
            if c["n"] < 2:
                continue
            fam = ", ".join(f"{k} {v}" for k, v in c["family_mix"].items())
            mem = ", ".join(c["rules"]) if len(c["rules"]) <= 14 else ", ".join(c["rules"][:14]) + f", ... (+{len(c['rules']) - 14})"
            L.append(f"| {c['cluster']} | {c['n']} | {_f(c['mean_inner_rho'], 2)} | `{cells[c['representative']]['rule']}` | "
                     f"{_pct(c['rep_dev_vs_spy'])} | {_pct(c['rep_sealed_vs_spy'])} | {'yes' if c['rep_beat_spy_both'] else 'no'} | "
                     f"{fam} | {mem} |")
        n1 = sum(1 for c in cl if c["n"] == 1)
        L += ["", f"Singletons: {n1}.", ""]
    ds = r.get("decomposition_summary") or {}
    L += ["## Decomposition: monthly active return on ETF spreads (each minus SPY)", "",
          "Every primary cell is decomposed; the table prints the 2024-26 top-30 [S] and the dev "
          "top-30 [D], sorted by 2024-26 vs SPY. alpha is monthly; SE plain OLS; **MDE = 2.8 x SE** "
          "(the alpha a 32-block window detects 80% of the time). **hedged** = mean 2024-26 active "
          "return minus the DEV (pre-2024) betas x the 2024-26 spreads: the alpha left after betas "
          "you could have known. **verdict** on the hedged alpha: ALPHA_DETECTED |t| >= 2 (sign "
          "shown); BETA_EXPLAINS |t| < 1 AND MDE < |mean 2024-26 active|; else CANNOT_DISTINGUISH. "
          "The in-sample `SMH+MTUM share` column and its `MOSTLY SMH/MTUM BETA` label are deleted "
          "(review 2026-09-27 §7): a ratio of contributions on regressors correlated at 0.69 cannot "
          "tell beta from no power.", ""]
    if ds:
        vs = ds["verdicts_2024_26_top30"]
        L += [f"Over all {ds['n_decomposed']} primary cells: median SE(alpha) 2024-26 "
              f"{_pct(ds['median_se_alpha_2024_26'], 2)}/mo, median MDE "
              f"**{_pct(ds['median_mde_alpha_2024_26'], 2)}/mo** (dev SE {_pct(ds['median_se_alpha_dev'], 2)}); "
              f"t >= 2 in dev {ds['n_t_ge_2_dev']}, in 2024-26 {ds['n_t_ge_2_2024_26']}, full "
              f"{ds['n_t_ge_2_full']}, both windows {ds['n_t_ge_2_both']}. Verdicts, all primary: "
              + ", ".join(f"{k} {v}" for k, v in ds["verdicts_all_primary"].items())
              + "; 2024-26 top-30: " + ", ".join(f"{k} {v}" for k, v in vs.items())
              + (f" (negative ALPHA_DETECTED: {', '.join(ds['alpha_detected_negative'])})"
                 if ds.get("alpha_detected_negative") else "") + ".", "",
              "Beta stability (correlation across primary cells of dev beta vs 2024-26 beta): "
              + ", ".join(f"{k} {_f(v, 2)}" for k, v in ds["beta_stability_corr_dev_vs_2024_26"].items())
              + ". Low = the loading is a regime, not a style.", ""]
    L += ["| rule | 2024-26 vs SPY | a 24-26 (t) | SE | MDE | b SMH dev->24-26 | b IWM dev->24-26 | "
          "b MTUM dev->24-26 | R2 | a dev (t) | **hedged a 24-26** | SE | t | MDE | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    dec = sorted(((k, v) for k, v in r["decomposition"].items()
                  if v.get("in_sealed_top30") or v.get("in_dev_top30")),
                 key=lambda kv: -(kv[1]["sealed_vs_spy"] if kv[1]["sealed_vs_spy"] is not None else -9))
    for rid, v in dec:
        s, d = v.get("sealed") or {}, v.get("dev") or {}
        if "t_alpha" not in s:
            continue
        h = v.get("alpha_after_pre2024_hedge") or {}
        bs = v.get("beta_stability") or {}

        def bb(e):
            x = bs.get(e) or {}
            return f"{_f(x.get('dev'), 2)} -> {_f(x.get('2024_26'), 2)}"
        tag = ("S" if v["in_sealed_top30"] else "") + ("D" if v["in_dev_top30"] else "")
        vd = v.get("verdict", "")
        if vd == "ALPHA_DETECTED":
            vd += f" ({v.get('alpha_sign')})"
        L.append(f"| `{rid}` [{tag}] | {_pct(v['sealed_vs_spy'])} | {_pct(s['alpha_monthly'], 2)} "
                 f"({_f(s['t_alpha'], 2)}) | {_pct(s.get('se_alpha'), 2)} | {_pct(s.get('mde_alpha_80'), 2)} | "
                 f"{bb('SMH')} | {bb('IWM')} | {bb('MTUM')} | {_f(s['r2'], 2)} | "
                 f"{_pct(d.get('alpha_monthly'), 2)} ({_f(d.get('t_alpha'), 2)}) | "
                 f"**{_pct(h.get('alpha_monthly'), 2)}** | {_pct(h.get('se'), 2)} | {_f(h.get('t'), 2)} | "
                 f"{_pct(h.get('mde_80'), 2)} | {vd} |")
    cv = r.get("bet_count_curve") or {}
    if cv:
        cuts = list(next(iter(cv.values()))["clusters_by_rho"])
        L += ["", "## Distinct bets as a CURVE (primary cells, full window)", "",
              "The count is set by the cut as much as by the data. Residual clustering RAISES it "
              "(the shared factor inflated the correlations): the residual count is the multiplicity "
              "denominator for ALPHA claims, the active/raw counts are the ones for RISK (what "
              "loses together).", "",
              "| series clustered | " + " | ".join(f"rho {c}" for c in cuts)
              + " | median pair rho | share of pairs >= 0.8 |",
              "|---|" + "---|" * (len(cuts) + 2)]
        for name, v in cv.items():
            L.append(f"| {name} | " + " | ".join(str(v["clusters_by_rho"][c]) for c in cuts)
                     + f" | {_f(v['median_pair_rho'], 2)} | {_pct(v['share_pairs_ge_cut'], 1)} |")
        for c, v in (r.get("dsr_at_residual_clusters") or {}).items():
            L.append(f"\nDSR of `{c}`: {_f(v['dsr_at_n_cells'])} at n = {v['n_cells']} cells, "
                     f"{_f(v['dsr_at_n_residual_clusters'])} at n = {v['n_residual_clusters']} "
                     "residual clusters (rho 0.8).")
    wc = r.get("within_cluster") or []
    if wc:
        L += ["", "## Within-cluster spread: does construction matter? (rule-level full clusters, n >= 3)", "",
              "Level 1 = the cluster's equal-weight mean, hedged ex ante (dev betas over 2024-26). "
              "Level 2 = the members around it: range and sd of 2024-26 excess vs SPY, median "
              "annualised tracking error of member - cluster mean, and the Spearman rank "
              "correlation of member dev excess vs 2024-26 excess. `axis` = how members differ "
              "from the cluster's anchor (universe / k / weighting / hold-offset; "
              "`signal/filter` when only the selection rule differs).", "",
              "| cluster | n | mean rho | dominant axis | 2024-26 vs SPY min .. max | sd | median TE | "
              "rank corr dev->24-26 | L1 hedged a/mo (t; MDE) | L1 verdict |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for c in wc:
            l1 = c.get("level1_cluster_mean") or {}
            L.append(f"| {c['cluster']} | {c['n']} | {_f(c['mean_inner_rho'], 2)} | "
                     f"{c['dominant_axis']} ({', '.join(f'{k} {v}' for k, v in c['axes'].items())}) | "
                     f"{_pct(c['sealed_vs_spy_min'])} .. {_pct(c['sealed_vs_spy_max'])} | "
                     f"{_pct(c['sealed_vs_spy_sd'])} | {_pct(c['median_te_vs_cluster_mean_annual'])} | "
                     f"{_f(c['rank_corr_dev_vs_2024_26'], 2)} | "
                     f"{_pct(l1.get('alpha_after_pre2024_hedge'), 2)} ({_f(l1.get('t_hedged'), 2)}; "
                     f"{_pct(l1.get('mde_hedged'), 2)}) | {l1.get('verdict', l1.get('status', 'n/a'))}"
                     + (f" ({l1['alpha_sign']})" if l1.get("verdict") == "ALPHA_DETECTED" else "") + " |")
        ps = r.get("within_cluster_persistence") or {}
        if ps:
            L += ["", "Pairwise order persistence (dev -> 2024-26) across every cluster above: "
                  + "; ".join(f"{k}: {v['share_order_persists']*100:.0f}% of {v['n_pairs']} pairs"
                              for k, v in ps["pairs"].items())
                  + ". Construction-only pairs by axis: "
                  + "; ".join(f"{k} {v['share_order_persists']*100:.0f}% of {v['n_pairs']}"
                              for k, v in ps["construction_pairs_by_axis"].items())
                  + ". 50% is a coin."]
    ll = r["lead_lag"]
    L += ["", "## Lead-lag (HYPOTHESIS, never finding)", "",
          f"{ll['n_tests_positive_lag']} tests at lag +1/+2, typical n {ll['typical_n']}; under the null "
          f"P(|rho| >= 0.3) = {ll['null_p_abs_rho_ge_0_3']:.4f}, expected false hits {ll['expected_false_hits']:.1f}.", "",
          "| representative | x | direction | lag | rho | n |", "|---|---|---|---|---|---|"]
    for h in ll["hypotheses"]:
        L.append(f"| `{h['rep']}` | {h['x']} | {h['direction']} | +{h['lag']} | {_f(h['rho'], 2)} | {h['n']} |")
    L += ["", f"News flow: {ll['news_flow']['status']} -- {ll['news_flow']['why']}", "",
          "## Frozen forward books", "", "| book | rule | full cluster | dev cluster | 2024-26 cluster |", "|---|---|---|---|---|"]
    for bk, v in r["frozen_books"].items():
        L.append(f"| `{bk}` | `{v['rule']}` | {v.get('cluster_full')} | {v.get('cluster_dev')} | {v.get('cluster_sealed')} |")
    L += ["", "Same full-window cluster: " + ("; ".join(", ".join(f"`{x}`" for x in g)
                                                       for g in r["frozen_books_same_full_cluster"].values()) or "none"),
          "", "Frozen-book pairs with full-window rho >= 0.8:", ""]
    for p in r["frozen_book_pairs_rho_ge_0_8_full"]:
        L.append(f"- `{p['a']}` ~ `{p['b']}`: full {_f(p['rho_full'], 2)}, dev {_f(p['rho_dev'], 2)}, 2024-26 {_f(p['rho_sealed'], 2)}")
    L += ["", f"## DEPRIORITIZED duplicates ({len(r['deprioritized_duplicates'])}; same full cluster AND rho >= 0.8 with the representative in dev AND 2024-26)", "",
          "| rule | duplicate of | family | rho dev | rho 2024-26 |", "|---|---|---|---|---|"]
    for d in sorted(r["deprioritized_duplicates"], key=lambda d: (d["duplicate_of"], d["rule"])):
        L.append(f"| `{d['rule']}` | `{d['duplicate_of']}` | {d['family']} | {_f(d['rho_dev'], 2)} | {_f(d['rho_sealed'], 2)} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
