"""TRIAL-LIB-FWD-TWIN-1: freeze the inputs of the one forward comparison (lane M6).

    python -m scripts.lib_forward_trial              # count, estimate, write the receipt
    python -m scripts.lib_forward_trial --register   # + register in rule_experiments (local DB)

Counts the frozen library books and their twins FROM DISK
(`llm_portfolio/books.jsonl`), takes the clusters from the bridge receipt, and
freezes the sigma each book's (book - twin) difference is read against, from
the backtest's own single-draw twin series. Writes
`backend/data/optimus/trials/lib_forward_trial_<run id>.json` (never
overwritten) with the luck table and the MDE. Creates no book; places no order;
$0 LLM.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                       # noqa: E402
from backend.services import lib_forward_trial as LT     # noqa: E402

OPT = Path(_cfg.OPTIMUS_LEDGER_DIR)
BOOKS = OPT / "llm_portfolio" / "books.jsonl"
BRIDGE = OPT / "bridge" / "bridge_2026-09-28.json"
RUN = "2026-09-27T082553Z"
TWIN_SERIES = OPT / "signal_structure" / f"matched_twins_monthly_{RUN}.parquet"
NET_SERIES = OPT / "signal_structure" / f"monthly_returns_{RUN}.parquet"
OUT = OPT / "trials"
MDE_Z = 2.8


def _cell_for(rule: str, cols: list) -> str | None:
    hits = sorted(c for c in cols if c.split("@")[0] == rule)
    return hits[0] if hits else None


def estimate(pairs: list, bridge_rows: list) -> dict:
    """Per-book sigma at 21 and 63 sessions, and the within / between cluster
    correlations of the single-draw (book - twin) difference, from the backtest."""
    tw = pd.read_parquet(TWIN_SERIES)
    d0 = tw["rule_minus_twin0"]
    net = pd.read_parquet(NET_SERIES)
    r1 = net["random_1@k50"].astype(float)
    rule_of = {r["book"]: r.get("rule") for r in bridge_rows}
    clusters = {p["name"]: LT.cluster_of(p["name"], bridge_rows) for p in pairs}
    series, series_read, s21, s63, how = {}, {}, {}, {}, {}
    for p in pairs:
        cell = _cell_for(rule_of.get(p["name"]) or "", list(d0.columns))
        if cell is None:
            continue
        d = d0[cell].astype(float).dropna()
        sd21 = float(d.std(ddof=1))
        q = d.groupby(np.arange(len(d)) // 3).sum()
        sd63 = float(q.std(ddof=1))
        basis = "rule - matched twin (single draw), backtest"
        d_read = d
        if p["twin_type"] != "matched_random" and cell in net.columns:
            # the frozen twin is matched on SIZE BAND only: its difference also
            # carries the vol / momentum style the matched twin removes. Take
            # the larger of the matched sigma and rule - random_1 (unmatched)
            # so the z is never flattered by a too-small sigma.
            dr = (net[cell].astype(float) - r1).dropna()
            qr = dr.groupby(np.arange(len(dr)) // 3).sum()
            sd21, sd63 = max(sd21, float(dr.std(ddof=1))), max(sd63, float(qr.std(ddof=1)))
            basis = "max(rule - matched twin, rule - random_1@k50), backtest (band-only twin)"
            d_read = dr
        series[p["name"]] = d
        # AMENDMENT 2026-09-28 (review F2): the correlation must be estimated on
        # the SAME difference type the trial reads. A band-only twin leaves the
        # vol / momentum style in the difference, so its proxy is rule - random_1.
        series_read[p["name"]] = d_read
        s21[p["name"]], s63[p["name"]], how[p["name"]] = sd21, sd63, basis
    med21 = float(np.median(list(s21.values())))
    med63 = float(np.median(list(s63.values())))
    for p in pairs:
        if p["name"] not in s21:
            s21[p["name"]], s63[p["name"]] = med21, med63
            how[p["name"]] = "no backtest series (forward-only): the median of the others"
    w, b = _cluster_rhos(series, clusters)
    wr, br = _cluster_rhos(series_read, clusters)
    return {"sigma_21": s21, "sigma_63": s63, "sigma_basis": how, "clusters": clusters,
            "rho_within": float(np.mean(w)) if w else 0.0,
            "rho_between": float(np.mean(b)) if b else 0.0,
            "n_pairs_within": len(w), "n_pairs_between": len(b),
            "rho_all_median": float(np.median(w + b)) if (w or b) else 0.0,
            "rho_within_as_read": float(np.mean(wr)) if wr else 0.0,
            "rho_between_as_read": float(np.mean(br)) if br else 0.0,
            "n_pairs_within_as_read": len(wr), "n_pairs_between_as_read": len(br),
            "series_last_month": str(max(pd.DataFrame(series_read).dropna(how="all").index).date())
            if series_read else None,
            "pool_empirical_sd_as_read": _pool_empirical_sd(series_read, clusters)}


def _cluster_rhos(series: dict, clusters: dict) -> tuple[list, list]:
    names = list(series)
    C = pd.DataFrame(series).corr(min_periods=24)
    w, b = [], []
    for i, a in enumerate(names):
        for c in names[i + 1:]:
            v = C.loc[a, c]
            if np.isfinite(v):
                (w if clusters[a] == clusters[c] else b).append(float(v))
    return w, b


def _pool_empirical_sd(series: dict, clusters: dict) -> dict:
    """sd of the cluster-pooled monthly and quarterly difference, measured directly
    (a cross-check on the closed form; books with a series only)."""
    if not series:
        return {}
    f = pd.DataFrame(series)
    by_c = {}
    for n in f.columns:
        by_c.setdefault(clusters[n], []).append(n)
    pool = pd.concat([f[m].mean(axis=1) for m in by_c.values()], axis=1).mean(axis=1).dropna()
    q = pool.groupby(np.arange(len(pool)) // 3).sum()
    return {"21": float(pool.std(ddof=1)), "63": float(q.std(ddof=1)), "n_months": int(len(pool))}


def _phi(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def amend(frozen_receipt: Path) -> int:
    """AMENDMENT 2026-09-28 (review F2), written BEFORE the 13:30Z open.

    Re-estimates ONLY the two correlations, on the difference type the trial
    actually reads, from the SAME backtest series the registration used (last
    month 2026-07-31: no return from 2026-09-28 or later). The frozen pairs,
    clusters and per-book sigmas are copied from the registration receipt and
    checked equal to a fresh estimate; a mismatch REFUSES. Writes a NEW receipt
    `lib_forward_trial_amendment_<run id>.json`; the original is never touched."""
    reg = json.loads(frozen_receipt.read_text(encoding="utf-8"))
    bridge = json.loads(BRIDGE.read_text(encoding="utf-8"))
    est = estimate(reg["pairs"], bridge.get("rows") or [])
    for h in (21, 63):
        a_, b_ = est[f"sigma_{h}"], reg["frozen"][f"sigma_{h}"]
        if set(a_) != set(b_) or any(abs(a_[k] - b_[k]) > 1e-12 for k in b_):
            print(f"REFUSED: sigma_{h} does not reproduce the registration receipt", flush=True)
            return 2
    if est["clusters"] != reg["clusters"]:
        print("REFUSED: clusters do not reproduce the registration receipt", flush=True)
        return 2
    last = est["series_last_month"]
    if last is None or last >= LT.ENTRY_SESSION:
        print(f"REFUSED: backtest series reach {last}, on/after the entry session", flush=True)
        return 2
    names = [p["name"] for p in reg["pairs"]]
    rw_o, rb_o = reg["frozen"]["rho_within"], reg["frozen"]["rho_between"]
    rw_n, rb_n = est["rho_within_as_read"], est["rho_between_as_read"]
    if abs(rw_n - LT.RHO_WITHIN_AS_READ) > 1e-9 or abs(rb_n - LT.RHO_BETWEEN_AS_READ) > 1e-9:
        print(f"REFUSED: estimate ({rw_n}, {rb_n}) differs from the module constants", flush=True)
        return 2
    out = {}
    for h in (21, 63):
        sg = {n: reg["frozen"][f"sigma_{h}"][n] for n in names}
        so = LT.pooled_sd(sg, reg["clusters"], rw_o, rb_o)
        sn = LT.pooled_sd(sg, reg["clusters"], rw_n, rb_n)
        out[str(h)] = {"sd_registered": so, "sd_corrected": sn, "ratio": sn / so,
                       "mde80_registered": MDE_Z * so, "mde80_corrected": MDE_Z * sn,
                       "p_false_fire_one_sided_at_registered_bar": _phi(-2.0 * so / sn),
                       "p_false_fire_one_sided_at_corrected_bar": _phi(-2.0)}
    # joint zero-skill false-fire of the whole rule on the corrected bar: EARLY_KILL
    # (z21 <= -2) or SURVIVES (z63 >= 2 and D21 > 0); D63 contains D21, corr sqrt(21/63)
    rng = np.random.default_rng(20260928)
    n = 2_000_000
    z21 = rng.standard_normal(n)
    z63 = math.sqrt(1 / 3) * z21 + math.sqrt(2 / 3) * rng.standard_normal(n)
    ek = z21 <= LT.Z_EARLY_KILL
    sv = (~ek) & (z63 >= LT.Z_PASS) & (z21 > 0)
    ff = {"p_early_kill": float(ek.mean()), "p_survives": float(sv.mean()),
          "p_any_false_fire": float((ek | sv).mean()), "n_sim": n, "seed": 20260928,
          "note": "zero skill, z on the CORRECTED bar; KILL (z63 < 1) under zero skill is the correct outcome, not a false fire"}
    ncl = len(set(reg["clusters"][x] for x in names))
    s21, s63 = out["21"]["sd_corrected"], out["63"]["sd_corrected"]
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y-%m-%dT%H%M%SZ")
    rp = OUT / f"lib_forward_trial_amendment_{run_id}.json"
    if rp.exists():
        print(f"REFUSED: {rp.name} exists", flush=True)
        return 2
    doc = {"schema": "trials/lib_forward_amendment/1", "trial": LT.TRIAL_ID, "run_id": run_id,
           "written_utc": now.isoformat(timespec="seconds"), "amends": str(frozen_receipt.relative_to(REPO)).replace("\\", "/"),
           "why": ("review F2 (docs/reviews/REVIEW_2026-09-28_LANE_M_MEASUREMENT.md): the registered "
                   "correlations were estimated on the matched-twin differences while 25 of 30 books are "
                   "read against a size-band-only twin; re-estimated on the difference type read"),
           "uses_forward_data": False, "backtest_series_last_month": last,
           "sigmas": "unchanged (copied from the registration receipt, re-derived and checked equal)",
           "rho_registered": {"within": rw_o, "between": rb_o},
           "rho_corrected_as_read": {"within": rw_n, "between": rb_n,
                                     "n_pairs_within": est["n_pairs_within_as_read"],
                                     "n_pairs_between": est["n_pairs_between_as_read"],
                                     "band_only_proxy": "rule - random_1@k50 (not size-matched: an upper-side estimate)"},
           "pool_empirical_sd_as_read": est["pool_empirical_sd_as_read"],
           "pooled_sd": out, "deciding": "corrected",
           "effective_bets": {"n_clusters": ncl, "registered": LT.effective_bets(ncl, rb_o),
                              "corrected": LT.effective_bets(ncl, rb_n)},
           "thresholds_z_unchanged": {"early_kill": LT.Z_EARLY_KILL, "pass": LT.Z_PASS, "kill": LT.Z_KILL},
           "thresholds_in_pooled_D": {"early_kill_D21_at_or_below": LT.Z_EARLY_KILL * s21,
                                      "survives_D63_at_or_above": LT.Z_PASS * s63,
                                      "kill_D63_below": LT.Z_KILL * s63},
           "zero_skill_false_fire_corrected": ff}
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = rp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(rp)
    print(json.dumps({k: doc[k] for k in ("rho_registered", "rho_corrected_as_read", "pooled_sd",
                                           "effective_bets", "thresholds_in_pooled_D",
                                           "zero_skill_false_fire_corrected", "pool_empirical_sd_as_read")}, indent=1))
    print(f"-> {rp}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--amend", default=None, help="registration receipt to amend (F2 correlations)")
    a = ap.parse_args(argv)
    if a.amend:
        return amend(Path(a.amend).resolve())
    rows = [json.loads(x) for x in BOOKS.read_text(encoding="utf-8").splitlines() if x.strip()]
    bridge = json.loads(BRIDGE.read_text(encoding="utf-8"))
    pairs = LT.select_pairs(rows)
    counts = {
        "books_jsonl_rows": len(rows),
        "parents_live": sum(1 for r in rows if r.get("kind") not in ("twin", "void")
                            and r.get("book_id") not in {v.get("book_id") for v in rows
                                                         if v.get("kind") == "void"}),
        "twins": sum(1 for r in rows if r.get("kind") == "twin"),
        "void": sum(1 for r in rows if r.get("kind") == "void"),
        "lib_books_in_trial": len(pairs),
        "lib_with_matched_random_twin": sum(1 for p in pairs if p["twin_type"] == "matched_random"),
        "lib_with_band_only_twin": sum(1 for p in pairs if p["twin_type"] == "random_same_band"),
    }
    est = estimate(pairs, bridge.get("rows") or [])
    counts["clusters_in_trial"] = len(set(est["clusters"].values()))
    counts["bridge_distinct_bets_full"] = (bridge.get("distinct_bets") or {}).get("full", {}).get("n_distinct")
    frozen = {k: est[k] for k in ("sigma_21", "sigma_63", "rho_within", "rho_between")}
    names = [p["name"] for p in pairs]
    sd = {h: LT.pooled_sd({n: est[f"sigma_{h}"][n] for n in names}, est["clusters"],
                          est["rho_within"], est["rho_between"]) for h in (21, 63)}
    mde = {h: MDE_Z * sd[h] for h in (21, 63)}
    rhos = sorted({0.0, round(est["rho_between"], 2), round(est["rho_all_median"], 2), 0.30})
    luck = LT.luck_table([counts["lib_books_in_trial"], counts["clusters_in_trial"],
                          counts["parents_live"]], rhos)
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y-%m-%dT%H%M%SZ")
    OUT.mkdir(parents=True, exist_ok=True)
    rp = OUT / f"lib_forward_trial_{run_id}.json"
    if rp.exists():
        print(f"REFUSED: {rp.name} exists", flush=True)
        return 2
    doc = {"schema": "trials/lib_forward/1", "trial": LT.TRIAL_ID, "param": LT.PARAM, "run_id": run_id,
           "written_utc": now.isoformat(timespec="seconds"), "licence": "PRODUCT_EXPERIMENT",
           "creates_books": False, "llm_spend_usd": 0.0, "doc": LT.DOC,
           "entry_session": LT.ENTRY_SESSION, "read_21": LT.READ_21, "read_63": LT.READ_63,
           "counts": counts, "pairs": pairs, "clusters": est["clusters"],
           "frozen": frozen, "sigma_basis": est["sigma_basis"],
           "correlation_estimates": {k: est[k] for k in ("rho_within", "rho_between", "rho_all_median",
                                                          "n_pairs_within", "n_pairs_between")},
           "pooled_sd": {str(h): sd[h] for h in sd}, "mde_80pct": {str(h): mde[h] for h in mde},
           "luck_table": luck,
           "decision_rule": {"survives": f"z_63 >= {LT.Z_PASS} and the 21-session pooled sign > 0",
                             "kill": f"z_63 < {LT.Z_KILL}", "early_kill": f"z_21 <= {LT.Z_EARLY_KILL}",
                             "otherwise": "CANNOT_DISTINGUISH: extend to 126 sessions under the same rule"},
           "sources": {"books": str(BOOKS.relative_to(REPO)).replace("\\", "/"),
                       "bridge": str(BRIDGE.relative_to(REPO)).replace("\\", "/"),
                       "twin_series": str(TWIN_SERIES.relative_to(REPO)).replace("\\", "/"),
                       "net_series": str(NET_SERIES.relative_to(REPO)).replace("\\", "/")}}
    tmp = rp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(rp)
    print(f"counts {counts}")
    print(f"rho within {est['rho_within']:.2f} ({est['n_pairs_within']} pairs), between "
          f"{est['rho_between']:.2f} ({est['n_pairs_between']}), median {est['rho_all_median']:.2f}")
    print(f"pooled sd: 21 {sd[21]*100:.2f}%  63 {sd[63]*100:.2f}%; MDE 21 {mde[21]*100:.2f}%  63 {mde[63]*100:.2f}%")
    for r in luck:
        print(f"  K={r['k']:3d} rho={r['rho']:.2f}: P(best z >= 2) {r['p_best_ge_z']:.1%}, E[best z] {r['e_best_z']:.2f}")
    print(f"-> {rp}")
    if a.register:
        rid = LT.ensure_lib_forward_trial(frozen_receipt=str(rp.relative_to(REPO)).replace("\\", "/"))
        print(f"registered rule_experiments row {rid} (local DB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
