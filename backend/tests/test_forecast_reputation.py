"""The reputation layer: held-out skill -> shrunk, floored weights -> log-odds pool.

The first four tests are chunk R of
`docs/HANDOFF_2026-09-25_FABLE_TO_OPUS_BUILD_PLAN.md`, verbatim. The rest pin
the behaviours that make the layer honest on the real ledger: an all-negative
bench pools to nothing (not to a division by zero), a pool with no weighted arm
refuses rather than inventing 0.5, the Profit-Mirage restriction reports how
many rows it excluded, and `refit` writes its tuned constants into the receipt.

Fixture dates derive from `today` (CLAUDE.md protocol item 5).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services import forecast_reputation as fr


# ── chunk R, verbatim ────────────────────────────────────────────────────────
def test_negative_skill_arm_gets_zero_weight():
    skill = pd.DataFrame({"n":[2000, 5000], "skill":[0.05, -0.28]}, index=["investigator:a","persona:x"])
    w = fr.weights(skill, k_prior=500, gamma=2.0, floor=0.0)
    assert w["persona:x"] == 0.0
    assert abs(w.sum() - 1.0) < 1e-9

def test_shrink_by_n_moves_small_samples_toward_zero():
    skill = pd.DataFrame({"n":[10, 10000], "skill":[0.10, 0.10]}, index=["small","big"])
    w = fr.weights(skill, k_prior=500, gamma=1.0)
    assert w["big"] > w["small"]

def test_pool_is_log_odds_and_extremized():
    w = pd.Series({"a":0.5, "b":0.5})
    p = fr.pool({"a":0.6, "b":0.6}, w, kappa=1.0)
    assert abs(p - 0.6) < 1e-9
    assert fr.pool({"a":0.6, "b":0.6}, w, kappa=2.0) > 0.6

def test_arm_skill_is_held_out_by_date():
    rng = np.random.default_rng(0)
    n = 4000
    y = rng.integers(0, 2, n)
    df = pd.DataFrame({"arm":"good", "p": np.clip(0.5 + 0.3*(y-0.5) + rng.normal(0,0.1,n), 0.01, 0.99),
                       "y": y, "resolved_at": pd.date_range("2026-01-01", periods=n, freq="h")})
    out = fr.arm_skill(df)
    assert out.loc["good","skill"] > 0
    assert out.loc["good","n"] < n           # the test half only


# ── helpers ──────────────────────────────────────────────────────────────────
def _synthetic_ledger(n_days: int = 150, per_day: int = 20, seed: int = 1) -> list[dict]:
    """A good investigator arm, an anti-signal persona, same questions.

    Spans ~5 months ending yesterday, so it crosses at least one quarter
    boundary whatever `today` is.
    """
    rng = np.random.default_rng(seed)
    start = date.today() - timedelta(days=n_days + 1)
    rows = []
    for d in range(n_days):
        day = start + timedelta(days=d)
        for q in range(per_day):
            y = int(rng.integers(0, 2))
            tk = f"T{q:03d}"
            base = {"ticker": tk, "observable": "return_sign", "horizon_days": 1,
                    "threshold": None, "benchmark": None,
                    "made_at": f"{day.isoformat()}T12:00:00+00:00",
                    "resolves_after": (day + timedelta(days=2)).isoformat(),
                    "resolved_at": (day + timedelta(days=3)).isoformat(),
                    "outcome": y,
                    "resolution_detail": {"realised_return": 0.01 * (2 * y - 1),
                                          "vs_benchmark": 0.005 * (2 * y - 1)}}
            good = float(np.clip(0.5 + 0.25 * (y - 0.5) * 2 + rng.normal(0, 0.1), 0.02, 0.98))
            bad = float(np.clip(0.5 - 0.25 * (y - 0.5) * 2 + rng.normal(0, 0.1), 0.02, 0.98))
            rows.append({**base, "specialist": "investigator:a", "probability": good})
            rows.append({**base, "specialist": "geopolitical", "probability": bad})
    return rows


def _write(tmp_path, rows) -> Path:
    p = tmp_path / "predictions.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


# ── weights / pool edge cases ────────────────────────────────────────────────
def test_all_negative_bench_gets_all_zero_weight_not_nan():
    skill = pd.DataFrame({"n": [100, 200], "skill": [-0.1, -0.3]}, index=["a", "b"])
    w = fr.weights(skill, k_prior=100, gamma=2.0)
    assert (w == 0.0).all()
    assert not w.isna().any()


def test_nan_skill_is_zero_weight():
    skill = pd.DataFrame({"n": [100, 200], "skill": [np.nan, 0.1]}, index=["a", "b"])
    w = fr.weights(skill, k_prior=100, gamma=1.0)
    assert w["a"] == 0.0 and abs(w["b"] - 1.0) < 1e-12


def test_pool_refuses_when_no_present_arm_carries_weight():
    w = pd.Series({"a": 1.0, "b": 0.0})
    assert fr.pool({"b": 0.9, "c": 0.8}, w, kappa=1.0) is None
    assert fr.pool({}, w, kappa=1.0) is None


def test_pool_renormalises_over_present_arms_and_ignores_zero_weight():
    w = pd.Series({"a": 0.25, "b": 0.75, "persona": 0.0})
    # only `a` present: the pool is `a`'s own number, not a quarter of it
    assert abs(fr.pool({"a": 0.7, "persona": 0.01}, w, kappa=1.0) - 0.7) < 1e-9


def test_pool_kappa_below_one_shrinks_toward_half():
    w = pd.Series({"a": 1.0})
    assert 0.5 < fr.pool({"a": 0.8}, w, kappa=0.5) < 0.8


# ── arm_skill ────────────────────────────────────────────────────────────────
def test_arm_skill_reports_anti_signal_as_negative_discrimination():
    g = fr.graded_frame_from_rows(_synthetic_ledger(n_days=40))
    s = fr.arm_skill(g)
    assert s.loc["investigator:a", "skill"] > 0 and s.loc["investigator:a", "disc"] > 0
    assert s.loc["geopolitical", "skill"] < 0 and s.loc["geopolitical", "disc"] < 0
    for c in ("n", "brier", "clim", "skill", "disc"):
        assert c in s.columns


def test_arm_skill_test_half_is_the_later_half():
    n = 100
    df = pd.DataFrame({"arm": "x", "p": 0.5, "y": [0, 1] * 50,
                       "made_at": pd.date_range("2026-01-01", periods=n, freq="D")})
    s = fr.arm_skill(df)
    assert s.loc["x", "n"] == 50
    assert str(s.loc["x", "test_from"])[:10] == "2026-02-20"


def test_graded_frame_drops_ungraded_and_out_of_range_rows():
    rows = _synthetic_ledger(n_days=3, per_day=2)
    rows.append({**rows[0], "outcome": None})
    rows.append({**rows[0], "probability": 1.7})
    rows.append({**rows[0], "outcome": True})
    g = fr.graded_frame_from_rows(rows)
    assert len(g) == len(rows) - 2
    assert set(g["y"].unique()) <= {0.0, 1.0}


# ── calibration ──────────────────────────────────────────────────────────────
def test_calibration_curve_is_by_year_and_carries_relative_return():
    g = fr.graded_frame_from_rows(_synthetic_ledger(n_days=60))
    cal = fr.calibration_curve(g, horizon=1)
    assert not cal.empty
    assert {"year", "observable", "bin", "n", "p_mean", "base_rate",
            "ret_mean", "rel_ret_mean"} <= set(cal.columns)
    assert set(cal["arm_prefix"]) == {"investigator:"}
    # a discriminating arm: the top bin realises more than the bottom bin
    first = cal.sort_values("bin").groupby(["year", "observable"]).first()
    last = cal.sort_values("bin").groupby(["year", "observable"]).last()
    assert (last["base_rate"] > first["base_rate"]).all()
    assert cal["rel_ret_mean"].notna().all()


def test_calibration_curve_horizon_with_no_rows_is_empty_not_an_error():
    g = fr.graded_frame_from_rows(_synthetic_ledger(n_days=10))
    assert fr.calibration_curve(g, horizon=5).empty


# ── Profit-Mirage restricted check ───────────────────────────────────────────
def test_restricted_check_counts_what_it_excluded():
    g = fr.graded_frame_from_rows(_synthetic_ledger(n_days=40))
    cut = (date.today() - timedelta(days=20)).isoformat()
    r = fr.restricted_check(g, since=cut)
    assert r["n_rows_full"] == len(g)
    assert 0 < r["n_rows_restricted"] < len(g)
    assert r["n_rows_excluded"] == r["n_rows_full"] - r["n_rows_restricted"]
    arms = {a["arm"]: a for a in r["by_arm"]}
    assert "skill_full" in arms["investigator:a"] and "skill_restricted" in arms["investigator:a"]


def test_restricted_check_says_when_the_restriction_binds_nothing():
    g = fr.graded_frame_from_rows(_synthetic_ledger(n_days=10))
    r = fr.restricted_check(g, since="2000-01-01")
    assert r["n_rows_excluded"] == 0
    assert r["restriction_binds"] is False


# ── refit ────────────────────────────────────────────────────────────────────
def test_refit_writes_receipt_with_tuned_constants_and_zero_persona(tmp_path):
    p = _write(tmp_path, _synthetic_ledger(n_days=150, per_day=8))
    out = tmp_path / "rep"
    today = date.today().isoformat()
    r = fr.refit(p, today=today, out_dir=out)
    assert r["status"] == "OK"
    f = out / f"reputation_{today}.json"
    assert f.exists()
    disk = json.loads(f.read_text(encoding="utf-8"))
    t = disk["tuned"]
    for k in ("k_prior", "gamma", "kappa"):
        assert k in t
    assert disk["cv"]["unit"] in ("quarter", "day")
    arms = {a["arm"]: a for a in disk["arms"]}
    assert arms["geopolitical"]["weight"] == 0.0
    assert arms["investigator:a"]["weight"] > 0.0
    for a in disk["arms"]:
        for k in ("n", "skill", "weight"):
            assert k in a
    assert "calibration" in disk and "h1" in disk["calibration"]
    assert "restricted_check" in disk
    assert (out / f"calibration_{today}.json").exists()


def test_refit_falls_back_to_day_blocks_inside_one_quarter(tmp_path):
    rows = _synthetic_ledger(n_days=10, per_day=8)
    p = _write(tmp_path, rows)
    r = fr.refit(p, today=date.today().isoformat(), out_dir=tmp_path / "rep")
    # ten consecutive days can straddle a quarter end; either way the unit is named
    assert r["cv"]["unit"] in ("quarter", "day")
    assert r["cv"]["n_folds"] >= 2


def test_refit_refuses_an_ungraded_ledger_and_still_writes_the_receipt(tmp_path):
    rows = _synthetic_ledger(n_days=3, per_day=2)
    for x in rows:
        x["outcome"] = None
    p = _write(tmp_path, rows)
    today = date.today().isoformat()
    r = fr.refit(p, today=today, out_dir=tmp_path / "rep")
    assert r["status"] == "REFUSED"
    assert (tmp_path / "rep" / f"reputation_{today}.json").exists()


def test_refit_records_agreement_with_the_previous_refit(tmp_path):
    p = _write(tmp_path, _synthetic_ledger(n_days=150, per_day=8))
    out = tmp_path / "rep"
    d1 = (date.today() - timedelta(days=1)).isoformat()
    d2 = date.today().isoformat()
    fr.refit(p, today=d1, out_dir=out)
    r2 = fr.refit(p, today=d2, out_dir=out)
    assert r2["previous"]["date"] == d1
    assert r2["previous"]["agrees"] is True


def test_refit_says_when_k_prior_is_not_identified(tmp_path):
    # one weighted arm: its n cancels in the normalisation, so k cannot matter
    p = _write(tmp_path, _synthetic_ledger(n_days=150, per_day=8))
    r = fr.refit(p, today=date.today().isoformat(), out_dir=tmp_path / "rep")
    assert r["tuned"]["identified"]["k_prior"] is False
    assert r["tuned"]["k_prior"] == 300.0     # tie-break: nearest DEFAULTS, not the data
