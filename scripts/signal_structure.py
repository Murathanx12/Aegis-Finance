"""Signal structure of one VALID strategy-library run: distinct bets, ETF decomposition, lead-lag.

    python -m scripts.signal_structure                          # run 2026-09-26T150811Z
    python -m scripts.signal_structure --run-id <id> --refresh-etf

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
SHARE_FLOOR = 0.002    # 20 bps/month: below this there is no 2024-26 excess to attribute


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=DEFAULT_RUN)
    ap.add_argument("--refresh-etf", action="store_true")
    a = ap.parse_args(argv)
    run_id = a.run_id
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

    # ── decomposition ─────────────────────────────────────────────────────
    X = SS.factor_spreads(etf).reindex(active.index)
    cand = [r for r in board["all_rows"] if not r.get("control")
            and r.get("sealed_vs_spy") is not None and r.get("dev_vs_spy") is not None]
    top_sealed = sorted(cand, key=lambda r: (-r["sealed_vs_spy"], r["id"]))[:TOP_N]
    top_dev = sorted(cand, key=lambda r: (-r["dev_vs_spy"], r["id"]))[:TOP_N]
    decomp = {}
    for r in {x["id"]: x for x in top_sealed + top_dev}.values():
        cid = SS.cell_id(r["id"], r["k"])
        if cid not in active.columns:
            decomp[r["id"]] = {"status": "REFUSED", "why": f"{cid} has no series"}
            continue
        y = active[cid]
        out = {"cell": cid, "family": r["family"], "hold_months": r.get("hold_months"),
               "sealed_vs_spy": r["sealed_vs_spy"], "dev_vs_spy": r["dev_vs_spy"],
               "in_sealed_top30": r in top_sealed, "in_dev_top30": r in top_dev}
        for wname in ("sealed", "dev"):
            try:
                out[wname] = SS.ols(y[masks[wname]], X[masks[wname]])
            except SS.InsufficientHistory as e:
                out[wname] = {"status": "REFUSED", "why": str(e)}
        for wname in ("sealed", "dev"):
            try:
                out[f"{wname}_smh_mtum"] = SS.ols(y[masks[wname]], X.loc[masks[wname], ["SMH-SPY", "MTUM-SPY"]])
            except SS.InsufficientHistory as e:
                out[f"{wname}_smh_mtum"] = {"status": "REFUSED", "why": str(e)}
        s = out.get("sealed") or {}
        if "t_alpha" in s:
            ma = s["mean_active_monthly"]
            semis_mom = s["contribution_monthly"]["SMH-SPY"] + s["contribution_monthly"]["MTUM-SPY"]
            has_excess = bool(r["sealed_vs_spy"] > 0 and ma >= SHARE_FLOOR)
            out["smh_mtum_share_of_sealed_active"] = (semis_mom / ma) if has_excess else None
            out["mostly_smh_or_mtum_beta"] = bool(has_excess and s["t_alpha"] < 1 and semis_mom / ma >= 0.5)
            out["alpha_t_below_1_after_etfs"] = bool(s["t_alpha"] < 1)
        d = out.get("dev") or {}
        out["survives_both"] = bool(s.get("t_alpha", -9) >= 2 and d.get("t_alpha", -9) >= 2)
        decomp[r["id"]] = out
    # the ETF spreads' own collinearity in the sealed window (a 32-block regression on 6 of them)
    xs = X[masks["sealed"]].dropna()
    xcorr = xs.corr().round(2).to_dict()

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
        "etf_spread_corr_sealed": xcorr,
        "lead_lag": lead_lag,
        "frozen_books": books, "frozen_book_pairs_rho_ge_0_8_full": pairs,
        "frozen_books_same_full_cluster": same_bet_groups,
        "deprioritized_duplicates": dup,
        "notes": [
            "active = rule net - SPY per monthly period; correlation is pairwise-complete, "
            f"a series needs >= {SS.MIN_PAIR_MONTHS} months in the window",
            "clusters: average linkage on 1 - rho, cut at rho 0.8 (distance 0.2); NaN rho = distance 1",
            "representative = highest DEV-window DSR at n = trial cells",
            "OLS standard errors are plain; hold>1 rules (quarterly books) have serially dependent "
            "monthly active returns, so their t is optimistic",
            "32 sealed blocks and 7 parameters: a t of 2 on alpha is one-in-twenty by noise per rule",
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
    L += ["## Decomposition: monthly active return on ETF spreads (each minus SPY)", "",
          "Sorted by 2024-26 vs SPY. alpha is monthly; t plain OLS. `SMH+MTUM share` = (beta_SMH x mean(SMH-SPY) + "
          "beta_MTUM x mean(MTUM-SPY)) / mean active, 2024-26, printed only when the rule beat SPY and its mean "
          "active is >= 20 bps/month. [S] = 2024-26 top-30, [D] = dev top-30.", "",
          "| rule | 2024-26 vs SPY | a 24-26 | t | b SMH | b IWM | b MTUM | b USMV | b QUAL | b VLUE | R2 | SMH+MTUM share | t a (SMH,MTUM only) | a dev | t dev | R2 dev | verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    dec = sorted(((k, v) for k, v in r["decomposition"].items() if "sealed" in v),
                 key=lambda kv: -(kv[1]["sealed_vs_spy"] or -9))
    for rid, v in dec:
        s, d = v.get("sealed") or {}, v.get("dev") or {}
        if "t_alpha" not in s:
            continue
        bt = s["betas"]
        verdict = ("SURVIVES (t>=2 both)" if v["survives_both"] else
                   "MOSTLY SMH/MTUM BETA" if v.get("mostly_smh_or_mtum_beta") else
                   "alpha t<1 after ETFs" if v.get("alpha_t_below_1_after_etfs") else "")
        tag = ("S" if v["in_sealed_top30"] else "") + ("D" if v["in_dev_top30"] else "")
        L.append(f"| `{rid}` [{tag}] | {_pct(v['sealed_vs_spy'])} | {_pct(s['alpha_monthly'], 2)} | {_f(s['t_alpha'], 2)} | "
                 + " | ".join(_f(bt[f'{e}-SPY'], 2) for e in ("SMH", "IWM", "MTUM", "USMV", "QUAL", "VLUE"))
                 + f" | {_f(s['r2'], 2)} | {_pct(v.get('smh_mtum_share_of_sealed_active'), 0)} | "
                 f"{_f((v.get('sealed_smh_mtum') or {}).get('t_alpha'), 2)} | "
                 f"{_pct(d.get('alpha_monthly'), 2)} | {_f(d.get('t_alpha'), 2)} | {_f(d.get('r2'), 2)} | {verdict} |")
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
