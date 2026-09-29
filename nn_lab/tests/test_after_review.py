"""Tests for the fixes answering docs/reviews/REVIEW_2026-09-29_NN_LAB.md.

Synthetic data only, dates derived from today, no network, no GPU. Each test fails on
the code as it stood on 2026-09-28."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from nn_lab import config as C
from nn_lab import loop as L
from nn_lab import models as M
from nn_lab import nightly as N
from nn_lab import table as T


def _cal(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=n)


def _bars(cal, syms, seed=3, px=20.0):
    rng = np.random.default_rng(seed)
    out = []
    for s in syms:
        c = px * np.exp(np.cumsum(rng.normal(0.0004, 0.02, len(cal))))
        out.append(pd.DataFrame({"symbol": s, "date": cal, "open": c * (1 + rng.normal(0, 0.002, len(cal))),
                                 "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 4e5,
                                 "vwap": c, "trades": 1500.0}))
    return pd.concat(out, ignore_index=True)


# ── F1: a split AFTER t must not change anything known at t ──────────────────

def test_a_planted_later_split_changes_no_feature_and_no_eligibility_before_it():
    cal = _cal(420)
    b = _bars(cal, [C.MARKET, "AAA", "BBB"], px=20.0)
    t, split_day = cal[300], cal[360]
    # the vendor's adjustment=all history of a 10:1 split on `split_day`: every price before
    # it divided by 10, every volume multiplied by 10 (the raw stock traded near $20)
    adj = b.copy()
    pre = (adj["symbol"] == "AAA") & (adj["date"] < split_day)
    adj.loc[pre, ["open", "high", "low", "close", "vwap"]] /= 10.0
    adj.loc[pre, "volume"] *= 10.0
    r_raw = T.price_rows(b, cal, keep_dates=pd.DatetimeIndex([t]))
    r_adj = T.price_rows(adj, cal, keep_dates=pd.DatetimeIndex([t]))
    # eligibility: the adjusted close is $2 < $3 -- the old floor dropped AAA at t
    assert set(r_raw["symbol"]) == set(r_adj["symbol"]) == {"AAA", "BBB"}
    a1 = r_raw.set_index("symbol").loc["AAA"]
    a2 = r_adj.set_index("symbol").loc["AAA"]
    for c in T.PRICE_FEATURES:
        np.testing.assert_allclose(a1[c], a2[c], rtol=1e-4, equal_nan=True, err_msg=c)
    facts = pd.DataFrame({"ticker": ["AAA"] * 3, "fact": ["shares", "net_income", "equity"],
                          "filed": [t - pd.Timedelta(days=30)] * 3, "end": [t - pd.Timedelta(days=60)] * 3,
                          "period_days": [np.nan, 91.0, np.nan], "val": [1e8, 5e7, 1e9]})
    f1 = T.fundamentals(r_raw[r_raw["symbol"] == "AAA"].reset_index(drop=True), facts)
    f2 = T.fundamentals(r_adj[r_adj["symbol"] == "AAA"].reset_index(drop=True), facts)
    for c in T.FUND_FEATURES:
        np.testing.assert_allclose(f1[c].to_numpy(), f2[c].to_numpy(), equal_nan=True, err_msg=c)
    # without an unadjusted close there is no market cap: NaN, never a number, never zero
    assert f2[list(C.MCAP_FEATURES)].isna().all().all()


def test_market_cap_uses_the_unadjusted_close_when_one_exists():
    t = pd.Timestamp(date.today()) - pd.offsets.BDay(3)
    rows = pd.DataFrame({"symbol": ["AAA"], "date": [t], "close": [2.0], "close_raw": [20.0]})
    facts = pd.DataFrame({"ticker": ["AAA"], "fact": ["shares"], "filed": [t - pd.Timedelta(days=9)],
                          "end": [t - pd.Timedelta(days=40)], "period_days": [np.nan], "val": [1e8]})
    f = T.fundamentals(rows, facts)
    assert f["f_log_mcap"].iloc[0] == pytest.approx(np.log(20.0 * 1e8), rel=1e-5)


# ── F2: missingness decided by a later pull is not a feature ────────────────

def test_a_death_correlated_snapshot_is_unavailable_before_its_first_pull_and_carries_no_flag(tmp_path):
    cal = _cal(40)
    rows = pd.DataFrame({"symbol": ["LIVE", "DEAD"] * 20, "date": np.repeat(cal[:20], 2)})
    # the 2026 snapshot covers the survivor only: its coverage says who will die
    rev = pd.DataFrame({"ticker": ["LIVE"] * 30, "event_date": list(cal[:30]),
                        "action": ["up"] * 30, "target_change": [0.1] * 30})
    pit_from = cal[15]
    a = T.analyst(rows, rev, pit_from=pit_from)
    before = rows["date"] < pit_from
    assert a.loc[before, list(T.ANALYST_FEATURES)].isna().all().all()     # BOTH names, before the pull
    assert a.loc[~before & (rows["symbol"] == "LIVE"), "an_up_63"].notna().all()
    # no missing-indicator for a later-pull group, whatever its coverage
    df = pd.concat([rows.reset_index(drop=True), a], axis=1)
    for c in T.PRICE_FEATURES:
        df[c] = np.random.default_rng(0).normal(size=len(df))
    _, names = M.design_matrix(df, ["price", "analyst"])
    assert "missing_analyst" not in names and not any(n.startswith("missing_") for n in names)
    # the first pull receipt dates the snapshot
    (tmp_path / "analyst_pull_2026-09-26.json").write_text("{}")
    (tmp_path / "analyst_pull_2026-09-24.json").write_text("{}")
    assert T.analyst_pit_from(tmp_path) == pd.Timestamp("2026-09-24")
    assert T.analyst_pit_from(tmp_path / "none") is None


# ── F6: the shrink guard compares the TABLE ─────────────────────────────────

def _table(dates_grid, live_date, n_live, n_grid=50):
    g = pd.DataFrame([(d, f"S{i:03d}") for d in dates_grid for i in range(n_grid)], columns=["date", "symbol"])
    g["on_grid"] = True
    lv = pd.DataFrame({"date": live_date, "symbol": [f"S{i:03d}" for i in range(n_live)], "on_grid": False})
    t = pd.concat([g, lv], ignore_index=True)
    for h in C.HORIZONS:
        t[f"y_{h}"] = np.where(t["on_grid"], 0.01, np.nan)
    return t


def test_fewer_eligible_names_today_is_not_a_shrink():
    cal = _cal(30)
    old = _table(cal[:20:5], cal[-2], n_live=120)
    new = _table(cal[:20:5], cal[-1], n_live=80)          # today: 40 fewer live names
    assert len(new) < len(old)                            # the 2026-09-28 guard refused this
    r = N.shrink_check(old, new)
    assert r["grid_rows_kept"] == 4 * 50


def test_a_real_shrink_is_refused():
    cal = _cal(30)
    old = _table(cal[:20:5], cal[-2], n_live=10)
    lost_row = old.drop(index=3)
    with pytest.raises(N.TableShrink):
        N.shrink_check(old, lost_row)
    lost_label = old.copy()
    lost_label.loc[5, "y_21"] = np.nan
    with pytest.raises(N.TableShrink, match="labels"):
        N.shrink_check(old, lost_label)


def test_a_failed_night_is_resumed_only_the_same_utc_day(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "STATE_PATH", tmp_path / "state.json")
    now = datetime.now(timezone.utc)
    (tmp_path / "state.json").write_text(json.dumps({"run_id": f"nightly_{now:%Y%m%dT%H%M%SZ}",
                                                     "complete": False, "done": {"append": {}}}))
    assert N._resume_state(now)
    (tmp_path / "state.json").write_text(json.dumps({"run_id": "nightly_20000101T000000Z",
                                                     "complete": False, "done": {"append": {}}}))
    assert N._resume_state(now) == {}


def test_labels_count_only_when_the_calendar_says_the_window_elapsed():
    cal = _cal(100)
    d = N.labelled_dates(cal[::5], cal, 21)
    assert d.max() < cal[-22] and cal[75] in d


# ── F7 + item 11: freeze once, verify before grading, never drop the dead ───

@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "REPO", tmp_path)
    for k, v in {"FROZEN_DIR": "frozen", "FROZEN_LEDGER": "frozen_ledger.jsonl", "OUTCOMES_DIR": "outcomes",
                 "FORWARD_GRADES": "forward_grades.jsonl"}.items():
        monkeypatch.setattr(C, k, tmp_path / v)
    return tmp_path


def _preds(syms, h=5, score=None):
    return pd.DataFrame({"symbol": syms, "horizon": h,
                         "score": score if score is not None else np.arange(len(syms), dtype=float)})


def test_a_frozen_file_is_never_rewritten(lab):
    dd = _cal(5)[-1]
    syms = [f"S{i}" for i in range(30)]
    r1 = L.freeze(_preds(syms), model="lgbm", model_version="v1", decision_date=dd, run_id="r1", kind="direction")
    p = L.frozen_path(dd, "lgbm")
    before = p.read_bytes()
    r2 = L.freeze(_preds(syms, score=-np.arange(30.0)), model="lgbm", model_version="v2", decision_date=dd,
                  run_id="r2", kind="direction")
    assert r1["status"] == "FROZEN" and r2["status"] == "ALREADY_FROZEN" and r2["verified"]
    assert p.read_bytes() == before
    assert len(L._read_jsonl(C.FROZEN_LEDGER)) == 1


def test_the_row_hash_covers_the_values():
    a = {"decision_date": "2026-01-02", "symbol": "X", "horizon": 5, "model": "m", "model_version": "v",
         "score": 0.1}
    assert L.row_hash(a) != L.row_hash({**a, "score": 0.2})


def test_grading_refuses_a_tampered_file_and_exits_a_delisted_name_at_its_last_close(lab):
    cal = _cal(80)
    syms = [f"S{i:02d}" for i in range(30)]
    bars = _bars(cal, [C.MARKET] + syms, seed=9)
    dd = cal[50]
    # S00 delists 2 sessions into the hold: last bar cal[53]
    bars = bars[~((bars["symbol"] == "S00") & (bars["date"] > cal[53]))]
    w = (dd + pd.Timedelta(hours=22)).isoformat()          # written after dd's close
    L.freeze(_preds(syms), model="lgbm", model_version="v", decision_date=dd, run_id="r", kind="direction",
             written_utc=w)
    L.freeze(_preds(syms), model="ridge", model_version="v", decision_date=dd, run_id="r", kind="direction",
             written_utc=w)
    # tamper with ridge's file after the ledger row was written
    p = L.frozen_path(dd, "ridge")
    df = pd.read_parquet(p)
    df["score"] = -df["score"]
    p.unlink()
    df.to_parquet(p, index=False)
    res = L.step_grade(bars, cal)
    assert [r["model"] for r in res["refused_unverified"]] == ["ridge"]
    g = L._read_jsonl(C.FORWARD_GRADES)
    assert {r["model"] for r in g} == {"lgbm"}
    lg5 = [r for r in g if r["horizon"] == 5][0]
    assert lg5["n"] == 30 and lg5["n_delist_exit"] == 1                 # nobody dropped
    o = pd.read_parquet(C.OUTCOMES_DIR / f"{dd.date()}_h5.parquet").set_index("symbol")
    b0 = bars[bars["symbol"] == "S00"].set_index("date")
    ent = L.entry_session(dd, pd.read_parquet(L.frozen_path(dd, "lgbm"))["written_utc"].iloc[0], cal)
    exp = b0.loc[cal[53], "close"] / b0.loc[ent, "open"] - 1.0
    assert o.loc["S00", "raw_return"] == pytest.approx(exp)
    assert bool(o.loc["S00", "delist_exit"])
    # a second night grades nothing twice
    assert L.step_grade(bars, cal)["graded_now"] == 0


def test_in_frozen_book_reads_the_positions_books_actually_store(tmp_path):
    bp = tmp_path / "books.jsonl"
    bp.write_text('{"book_id": "a", "positions": [{"ticker": "JAZZ", "weight": 0.1}]}\n'
                  '{"book_id": "b", "weights": {"TS": 0.2}}\n', encoding="utf-8")
    assert N.books_symbols(bp) == {"JAZZ", "TS"}


# ── item 8: trust, ensemble, the model in charge ────────────────────────────

def test_trust_is_shrunk_toward_zero_by_the_number_of_graded_blocks():
    few = L.posterior(np.full(1, 0.05))
    many = L.posterior(np.full(44, 0.05))
    assert few["trust"] < 0.1 * 0.05 and many["trust"] > 0.75 * 0.05
    assert few["source"] == many["source"] == "forward"
    wf = L.posterior(np.array([]), wf_mean=0.02, wf_blocks=80)
    assert wf["source"] == "walk_forward_only" and 0 < wf["trust"] < 0.02 * 0.5
    assert L.posterior(np.array([]))["trust"] == 0.0


def test_the_ensemble_is_the_zero_until_something_is_trusted():
    s = {"a": np.array([1.0, 2.0, 3.0]), "b": np.array([3.0, 2.0, 1.0]), "zero": np.zeros(3)}
    e, w = L.ensemble_scores(s, {"a": {"h5": {"trust": -0.01}}, "b": {"h5": {"trust": 0.0}}}, 5)
    assert np.all(e == 0)
    e, w = L.ensemble_scores(s, {"a": {"h5": {"trust": 0.03}}, "b": {"h5": {"trust": 0.01}}}, 5)
    assert w == {"a": 0.75, "b": 0.25} and e[2] > e[0]


def test_the_model_in_charge_changes_only_on_forward_evidence():
    t = {"nn": {"h21": {"trust": 0.001}}, "lgbm": {"h21": {"trust": 0.010}}, "zero": {"h21": {"trust": 0.0}}}
    first = L.decide_in_charge(None, t, forward_added=False)
    assert first["model"] == "lgbm"
    t2 = {"nn": {"h21": {"trust": 0.030}}, "lgbm": {"h21": {"trust": 0.010}}, "zero": {"h21": {"trust": 0.0}}}
    kept = L.decide_in_charge(first, t2, forward_added=False)
    assert kept["model"] == "lgbm" and "no forward grade" in kept["why_kept"]
    moved = L.decide_in_charge(first, t2, forward_added=True)
    assert moved["model"] == "nn" and moved["history"][-1]["from"] == "lgbm"
    t3 = {"nn": {"h21": {"trust": 0.0105}}, "lgbm": {"h21": {"trust": 0.010}}}
    assert L.decide_in_charge(first, t3, forward_added=True)["model"] == "lgbm"     # inside the margin


def test_trust_table_reads_forward_grades_by_block():
    cal = _cal(300)
    grades = [{"model": "lgbm", "horizon": 21, "decision_date": str(d.date()), "rank_ic": 0.04}
              for d in cal[::5][:40]]
    tt = L.trust_table(grades, cal, {})
    v = tt["lgbm"]["h21"]
    assert v["graded_dates"] == 40 and v["n_forward_blocks"] == 10 and 0 < v["trust"] < 0.04
    assert tt["zero"]["h21"]["trust"] == 0.0 and tt["nn"]["h21"]["source"] == "prior_only"


# ── item 9: the size of the move ────────────────────────────────────────────

def test_the_simplest_magnitude_model_that_gets_most_of_the_gain_is_chosen():
    mag = {"trailing_vol": {"h21": {"improvement_over_vol": 0.0}},
           "ridge_abs": {"h21": {"improvement_over_vol": 0.012}},
           "nn_width": {"h21": {"improvement_over_vol": 0.016}}}
    assert L.choose_magnitude(mag, 21)[0] == "ridge_abs"
    mag["ridge_abs"]["h21"]["improvement_over_vol"] = 0.005
    assert L.choose_magnitude(mag, 21)[0] == "nn_width"
    mag = {m: {"h21": {"improvement_over_vol": -0.01 if m != "trailing_vol" else 0.0}} for m in C.MAGNITUDE_ROSTER}
    assert L.choose_magnitude(mag, 21)[0] == "trailing_vol"


def test_conformal_factors_widen_a_too_narrow_interval_to_its_nominal_coverage():
    rng = np.random.default_rng(1)
    sig = rng.uniform(0.02, 0.2, 20_000)
    x = rng.standard_t(4, 20_000) * sig
    pa = sig * 0.6                                                  # a forecast that is too narrow
    cf = L.conformal_factors(pa, x)
    cov = float((np.abs(x) <= cf["c90"] * pa).mean())
    assert abs(cov - 0.90) < 0.01 and cf["c90"] > 1.6449 / 0.6 * 0.9
