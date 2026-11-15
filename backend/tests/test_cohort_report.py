"""Read-only cohort report: synthetic marks and paths, no network, no live data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services.portfolio_intelligence import cohort_report as CR


def _paths(n_port, n_sess, kind, seed=0):
    rng = np.random.default_rng(seed)
    if kind == "same":
        x = rng.normal(0, 0.01, n_sess)
        return {f"p{i}": x.copy() for i in range(n_port)}
    return {f"p{i}": rng.normal(0, 0.01, n_sess) for i in range(n_port)}


def test_identical_portfolios_are_one_bet():
    r = CR.effective_bets(_paths(2, 30, "same"))
    assert r["status"] == "OK" and abs(r["effective_bets"] - 1.0) < 1e-6
    r = CR.effective_bets(_paths(7, 30, "same"))
    assert abs(r["effective_bets"] - 1.0) < 1e-6 and r["share_corr_above"] == 1.0


def test_orthogonal_paths_are_about_n():
    n = 8
    t = np.arange(400)
    paths = {f"p{i}": np.sin(2 * np.pi * (i + 1) * t / 400) for i in range(n)}   # exactly orthogonal
    r = CR.effective_bets(paths)
    assert r["status"] == "OK" and abs(r["effective_bets"] - n) < 1e-6
    r2 = CR.effective_bets(_paths(10, 5000, "ind", seed=3))
    assert 8.5 < r2["effective_bets"] <= 10.0


def test_below_twenty_sessions_cannot_determine_and_says_how_many():
    r = CR.effective_bets(_paths(5, 19, "ind"))
    assert r["status"] == CR.CANNOT and r["n_sessions"] == 19 and "19 common sessions" in r["why"]
    assert r["effective_bets"] is None


def test_mde_falls_with_cohorts_and_needed_is_monotone():
    sd = 0.03
    mdes = [CR.mde_at(n, sd) for n in range(2, 40)]
    assert all(a > b for a, b in zip(mdes, mdes[1:]))
    # larger target -> fewer blocks; larger dispersion -> more blocks
    nt = [CR.blocks_needed(sd, t) for t in (0.01, 0.02, 0.04)]
    assert nt[0] > nt[1] > nt[2] or nt[1] >= nt[2]
    ns = [CR.blocks_needed(s, 0.02) for s in (0.01, 0.02, 0.04)]
    assert ns[0] <= ns[1] <= ns[2]
    # more cohorts in hand -> fewer still needed, never negative
    still = [CR.cohorts_still_needed(sd, 0.02, horizon=21, n_cohorts_have=h)["cohorts_still_needed"]
             for h in (0, 10, 100, 10_000)]
    assert still == sorted(still, reverse=True) and still[-1] == 0
    assert CR.cohorts_still_needed(None, 0.02, horizon=21, n_cohorts_have=0)["status"] == CR.CANNOT


def _cohort(cid, backfilled, hh_by_fam):
    books = []
    for fam, hhs in hh_by_fam.items():
        for hh in hhs:
            books.append({"status": "READY", "family": fam, "holdings_hash": hh, "long": {"AAA": 0.5, "BBB": 0.5},
                          "short": 0.0, "policy_id": f"{fam}-{hh}"})
    return {"cohort_id": cid, "entry_session": cid, "backfilled": backfilled, "forward_evidence": not backfilled,
            "books": books, "controls": []}


def _write_store(root: Path, cohorts, marks):
    d = root / "rolling_cohorts"
    (d / "cohorts").mkdir(parents=True)
    (d / "marks").mkdir()
    for c in cohorts:
        (d / "cohorts" / f"cohort_{c['cohort_id']}.json").write_text(json.dumps(c), encoding="utf8")
    pd.DataFrame(marks).to_parquet(d / "marks" / "part-x.parquet", index=False)


def _marks(cohorts, k=21, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for c in cohorts:
        for i, b in enumerate(b for b in c["books"]):
            rows.append({"kind": "book", "book_id": f"{c['cohort_id']}-{b['policy_id']}", "cohort_id": c["cohort_id"],
                         "entry_session": c["entry_session"], "mark_k": k, "backfilled": c["backfilled"],
                         "holdings_hash": b["holdings_hash"], "family": b["family"],
                         "excess_same_share": float(rng.normal(0, 0.03)),
                         "excess_vs_random": float(rng.normal(0, 0.03)), "excess_vs_spy": 0.0})
    return rows


def _tree(root: Path):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _setup(tmp_path, n=4):
    cs = [_cohort(f"2026-01-{5 + 7 * i:02d}" if False else (pd.Timestamp("2026-01-05") + pd.Timedelta(days=7 * i)).date().isoformat(),
                  True, {"fam_a": ["h1", "h2"], "fam_b": ["h3"]}) for i in range(n)]
    _write_store(tmp_path, cs, _marks(cs))
    return cs


def test_report_is_read_only_flags_backfilled_and_is_byte_stable(tmp_path):
    _setup(tmp_path / "data")
    before = _tree(tmp_path / "data")
    a = CR.build_report(tmp_path / "data", stamp="S1")
    b = CR.build_report(tmp_path / "data", stamp="S2")
    assert _tree(tmp_path / "data") == before                       # nothing written, nothing changed
    assert a["n_forward"] == 0 and a["first_line"].startswith("0 forward cohort(s) of 4")
    assert set(a["cohort_flags"].values()) == {"backfilled"}
    assert a["sha256"] == b["sha256"]                                # body is stable apart from the stamp
    assert a["citation"] == {"report_id": "cohort_report_S1", "sha256": a["sha256"],
                             "newest_cohort": a["newest_cohort"], "n_forward": 0}
    # every row at a horizon carries its n; forward rows are empty, backfilled rows are not
    cell = a["section_3_horizons"]["families"]["fam_a"]["21"]["vs_spy_same_invested_share"]
    assert cell["forward"]["n_cohorts"] == 0 and cell["all_incl_backfilled"]["n_cohorts"] == 4
    assert cell["planning"]["n_forward_cohorts_matured"] == 0
    # distinct portfolios counted per family, bets CANNOT_DETERMINE with no bars
    fam = a["section_1_bets"]["per_cohort"][0]["families"]
    assert fam["fam_a"]["books"] == 2 and fam["fam_a"]["distinct_portfolios"] == 2
    assert fam["fam_a"]["bets"]["status"] == CR.CANNOT
    p1, m1 = CR.write_report(a, tmp_path / "out")
    p2, m2 = CR.write_report(b, tmp_path / "out")
    j1, j2 = json.loads(p1.read_text()), json.loads(p2.read_text())
    for k in CR._VOLATILE:
        j1.pop(k), j2.pop(k)
    j1.pop('citation'), j2.pop('citation')
    assert j1 == j2
    md = m1.read_text(encoding="utf8")
    assert "backfilled rows are backtest data" in md and "no skill claim" in md
    assert "```json" in md and a["sha256"] in md


def test_forward_cohort_counts_and_needed_falls_as_forward_cohorts_arrive(tmp_path):
    cs = [_cohort(f"2026-02-{2 + 7 * i:02d}", i >= 0 and i < 3, {"fam_a": ["h1"]}) for i in range(4)]   # 1 forward
    _write_store(tmp_path, cs, _marks(cs))
    r = CR.build_report(tmp_path, stamp="S")
    assert r["n_forward"] == 1 and r["cohort_flags"][cs[3]["cohort_id"]] == "forward"
    pl = r["section_3_horizons"]["families"]["fam_a"]["21"]["vs_spy_same_invested_share"]["planning"]
    assert pl["n_forward_cohorts_matured"] == 1


def test_cohort_paths_from_synthetic_bars(tmp_path):
    days = pd.bdate_range("2026-03-02", periods=30)
    rng = np.random.default_rng(5)
    rows = []
    for sym in ("SPY", "AAA", "BBB"):
        px = 100 * np.cumprod(1 + rng.normal(0, 0.01, len(days)))
        for d, p in zip(days, px):
            rows.append({"symbol": sym, "date": d, "open": p, "close": p})
    bars = pd.DataFrame(rows)
    c = _cohort(days[0].date().isoformat(), True, {"fam_a": ["h1", "h2"]})
    c["books"][0]["long"] = {"AAA": 1.0}
    c["books"][1]["long"] = {"BBB": 1.0}
    paths, fams, n = CR.cohort_paths(c, bars)
    assert n == 30 and set(paths) == {"h1", "h2"} and fams["h1"] == {"fam_a"}
    r = CR.effective_bets(paths)
    assert r["status"] == "OK" and 1.0 <= r["effective_bets"] <= 2.0
    assert CR.family_daily_sd(paths, fams)["fam_a"] > 0
