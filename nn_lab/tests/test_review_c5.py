"""Fixes from docs/reviews/REVIEW_2026-10-06_C5_NN_LAB_MEMBERSHIP_FREEZE.md (2026-10-07).

F1 vintage of new grid dates · F2 the scored inputs are saved and re-score exactly · F6 the
revisions log is written only after the table lands, and an exclusion-list change is counted ·
F7 the tournament's baseline set and age · F8 the health contract. Synthetic data only; every
date is derived from today; no network, no GPU."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import nn_lab
from nn_lab import config as C
from nn_lab import membership as MB
from nn_lab import nightly as N
from nn_lab import table as T
from nn_lab import universe_filter as U


def _cal(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=n)


# ── F1: each new grid date's vintage is recorded the night it is first stored ──

def test_a_new_grid_date_stored_from_its_own_night_is_point_in_time(tmp_path):
    cal = _cal(40)
    p = tmp_path / "vintage.jsonl"
    rows = MB.record_vintage([cal[-1], cal[-6]], str(cal[-1].date()), cal, "nightly_t1", path=p)
    by = {r["date"]: r for r in rows}
    assert by[str(cal[-1].date())]["lag_sessions"] == 0 and by[str(cal[-1].date())]["pit_dollar_volume"]
    assert by[str(cal[-6].date())]["lag_sessions"] == 5 and not by[str(cal[-6].date())]["pit_dollar_volume"]
    # append-only and first-stored only: a later night never re-dates a recorded date
    assert MB.record_vintage([cal[-1]], str(cal[-1].date()), cal, "nightly_t2", path=p) == []
    assert len(p.read_text().splitlines()) == 2
    assert "2026-10-06" in C.PRE_FREEZE_DV_NOTE and "-0.64%" in C.PRE_FREEZE_DV_NOTE


# ── an end-to-end night on synthetic bars: re-adjustment, ETF list, write order ──

def _bars(cal, syms, vol, seed=3):
    rng = np.random.default_rng(seed)
    out = []
    for s in syms:
        c = 20 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, len(cal))))
        if s == "N07":                      # flat price: its dollar volume sits just above the floor
            c = 20 * (1 + 0.01 * np.sin(np.arange(len(cal))))
        out.append(pd.DataFrame({"symbol": s, "date": cal, "open": c * (1 + rng.normal(0, 0.002, len(cal))),
                                 "high": c * 1.01, "low": c * 0.99, "close": c, "volume": vol.get(s, 4e5),
                                 "vwap": c, "trades": 1500.0}))
    return pd.concat(out, ignore_index=True)


@pytest.fixture
def e2e(tmp_path, monkeypatch):
    cal = _cal(300)
    syms = ["SPY"] + [f"N{i:02d}" for i in range(30)]
    deep = tmp_path / "deep.parquet"
    recent = tmp_path / "recent.parquet"
    dead = tmp_path / "dead.parquet"
    out = tmp_path / "nn_lab"
    for k, v in {"BARS_DEEP": deep, "BARS_RECENT": recent, "BARS_DELISTED": dead, "OUT": out,
                 "TABLE_DIR": out / "table", "TABLE_PATH": out / "table" / "train_table.parquet",
                 "RECEIPT_DIR": out / "receipts", "MEMBERSHIP_VINTAGE": out / "membership_vintage.jsonl"}.items():
        monkeypatch.setattr(C, k, v)
    monkeypatch.setattr(N, "REVISIONS_PATH", out / "table" / "revisions.parquet")
    def _no_side(rows, **k):
        rows = rows.reset_index(drop=True)
        for g, cols in T.GROUPS.items():
            if g != "price":
                for c in cols:
                    rows[c] = np.float32(np.nan)
        return rows
    monkeypatch.setattr(T, "attach_side_groups", _no_side)
    b = _bars(cal[:-3], syms, {"N07": 152_500})     # N07 sits just above the $3M floor
    b.to_parquet(deep, index=False)
    b.iloc[:0].to_parquet(dead, index=False)
    _bars(cal, syms, {"N07": 152_500})[lambda d: d["date"] > cal[-4]].to_parquet(recent, index=False)
    (out / "table").mkdir(parents=True)
    T.build(start=str(cal[0].date()), out=C.TABLE_PATH, bars_paths=[deep, dead])
    return cal, deep, out


def test_an_e2e_night_keeps_frozen_members_records_vintage_and_counts_an_exclusion(e2e, monkeypatch):
    cal, deep, out = e2e
    tab0 = pd.read_parquet(C.TABLE_PATH)
    h0 = MB.membership_hashes(tab0)
    # the vendor re-adjusts N07's history for a dividend: its stored dollar volume crosses the floor
    b = pd.read_parquet(deep)
    m = b["symbol"] == "N07"
    b.loc[m, ["open", "high", "low", "close", "vwap"]] *= 0.95
    b.to_parquet(deep, index=False)
    # and the exclusion list now names N03 (a declared universe change)
    (out / "etf.json").write_text(json.dumps({"symbols": ["N03"]}))
    monkeypatch.setattr(C, "ETF_EXCLUSIONS", out / "etf.json")
    U._CACHE.clear()
    r = N.step_append("nightly_e2e")
    new = pd.read_parquet(C.TABLE_PATH)
    hn = MB.membership_hashes(new)
    n07_stored = tab0[(tab0["symbol"] == "N07") & tab0["on_grid"] & (tab0["date"] >= pd.Timestamp(r["tail_start"]))]
    assert len(n07_stored) > 0
    assert r["membership"]["membership_would_drop"] == len(n07_stored)        # a revision each, no refusal
    assert ((new["symbol"] == "N07") & new["on_grid"]).sum() >= ((tab0["symbol"] == "N07") & tab0["on_grid"]).sum()
    st07 = tab0.set_index(["date", "symbol"]).loc[list(zip(n07_stored["date"], n07_stored["symbol"])), "med_dv"]
    nw07 = new.set_index(["date", "symbol"]).loc[st07.index, "med_dv"]
    assert (st07.to_numpy() == nw07.to_numpy()).all()                         # stored dollar volume unchanged
    # frozen dates unchanged except the declared exclusion
    assert r["membership"]["etf_removed_from_frozen_dates"] == int((tab0["symbol"] == "N03").sum() -
                                                                   (~tab0[tab0["symbol"] == "N03"]["on_grid"]).sum())
    assert r["membership"]["frozen_dates_changed_by_declared_exclusion"] > 0
    assert any("exclusion list" in x for x in r["membership"]["degraded_reasons"])
    revs = pd.read_parquet(N.REVISIONS_PATH)
    assert (revs["kind"] == "ETF_EXCLUDED_FROM_FROZEN_DATE").sum() == r["membership"]["etf_removed_from_frozen_dates"]
    assert set(hn) >= set(h0)
    # the receipt says plainly what "frozen" means and carries every threshold
    assert "FIRST-STORED VINTAGE" in r["frozen_means"] and r["pre_freeze_dollar_volume_note"] == C.PRE_FREEZE_DV_NOTE
    assert r["membership"]["thresholds"]["label_revision_min_abs"] == C.LABEL_REVISION_MIN_ABS
    assert isinstance(r["vintage_of_new_grid_dates"], list)


def test_revisions_are_not_written_when_the_table_write_fails(e2e, monkeypatch):
    cal, deep, out = e2e
    b = pd.read_parquet(deep)
    b.loc[b["symbol"] == "N05", ["open", "high", "low", "close", "vwap"]] *= 0.9
    b.to_parquet(deep, index=False)
    sha0 = N.sha256_file(C.TABLE_PATH)

    def boom(src, dst):
        raise OSError("planted: disk full")
    monkeypatch.setattr(N.os, "replace", boom)
    with pytest.raises(OSError):
        N.step_append("nightly_fail")
    assert not N.REVISIONS_PATH.exists()                    # nothing logged for a table that did not land
    assert N.sha256_file(C.TABLE_PATH) == sha0


# ── F2: the exact scored rows are saved and re-score to the same numbers ──────

def test_rescoring_from_the_saved_inputs_reproduces_the_stored_scores(tmp_path, monkeypatch):
    pytest.importorskip("lightgbm")
    import joblib
    from nn_lab import models as M
    monkeypatch.setattr(C, "REPO", tmp_path)
    rng = np.random.default_rng(11)
    cal = _cal(12)
    rows = []
    for d in cal:
        f = pd.DataFrame(rng.normal(size=(60, len(T.PRICE_FEATURES))), columns=list(T.PRICE_FEATURES))
        f["date"], f["symbol"] = d, [f"S{i:02d}" for i in range(60)]
        rows.append(f)
    tab = pd.concat(rows, ignore_index=True)
    tab.loc[rng.random(len(tab)) < 0.05, "vol_63"] = np.nan          # real tables have holes
    groups = ["price"]
    X, xn = M.design_matrix(tab, groups)
    feats = M.feature_list(groups)
    models = {}
    for h in C.HORIZONS:
        y = rng.normal(size=len(tab)).astype("float32")
        for name, obj in (("ridge", M.fit_ridge(X, y)), ("lgbm", M.fit_lgbm(tab[feats], y, seed=h)),
                          ("ridge_abs", M.fit_ridge(X, np.abs(y)))):
            p = tmp_path / f"{name}_h{h}.joblib"
            joblib.dump(obj, p)
            models.setdefault(name, {})[f"h{h}"] = str(p)
    state = {"groups": groups, "xnames": xn, "feats": feats, "models": models, "versions": {"ridge": "r1"}}
    live = tab[tab["date"] == cal[-1]].sort_values("symbol").reset_index(drop=True)
    scored = N.score_live(live, state, with_nn=False)
    inp = N.save_frozen_inputs(live, decision_date=cal[-1], run_id="nightly_x", state=state,
                               frozen_dir=tmp_path / "frozen", ledger=tmp_path / "inputs_ledger.jsonl")
    assert inp["status"] == "SAVED" and inp["rows"] == 60
    again = N.rescore_from_inputs(tmp_path / inp["file"], state, with_nn=False)
    for h in C.HORIZONS:
        for m in ("ridge", "lgbm", "mom_12_1"):
            assert np.array_equal(again["scores"][h][m], scored["scores"][h][m], equal_nan=True)
    led = [json.loads(x) for x in (tmp_path / "inputs_ledger.jsonl").read_text().splitlines()]
    assert led[0]["sha256"] == N.sha256_file(tmp_path / inp["file"])
    # immutable: a second save on the same run never rewrites
    assert N.save_frozen_inputs(live.assign(mom_5=0.0), decision_date=cal[-1], run_id="nightly_x", state=state,
                                frozen_dir=tmp_path / "frozen",
                                ledger=tmp_path / "inputs_ledger.jsonl")["status"] == "ALREADY_SAVED"
    assert N.sha256_file(tmp_path / inp["file"]) == led[0]["sha256"]


# ── F7: the tournament compares the NN with the single-column baseline too ────

def test_the_tournament_includes_momentum_states_its_age_and_the_zero_weights(tmp_path, monkeypatch):
    rd = tmp_path / "receipts"
    rd.mkdir()
    monkeypatch.setattr(C, "RECEIPT_DIR", rd)
    monkeypatch.setattr(C, "TABLE_PATH", tmp_path / "t.parquet")
    monkeypatch.setattr(C, "TRUST_LEDGER", tmp_path / "trust.jsonl")
    monkeypatch.setattr(C, "FORWARD_GRADES", tmp_path / "fg.jsonl")
    pd.DataFrame({"a": [1]}).to_parquet(tmp_path / "t.parquet")
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec="seconds")

    def ic(m, se=0.01):
        return {"rank_ic": {"mean": m, "se": se, "t_strict": 1.0, "n_blocks_nonoverlapping": 20},
                "top20_minus_random_net": {"mean": 0.0}}
    (rd / "wf_x.json").write_text(json.dumps({
        "post_review": True, "written_utc": old, "table_sha256": "not-tonight", "folds": [{}] * 7,
        "models": {"nndist": {"h21": ic(0.001)}, "lgbm": {"h21": ic(0.010)}, "ridge": {"h21": ic(0.012)},
                   "mom": {"h21": ic(0.020)}}}))
    (tmp_path / "trust.jsonl").write_text(json.dumps({"ensemble_weights": {"h21": {"models": {"nn": {"weight": 0.0}}}}}))
    t = N.tournament()
    w = t["walk_forward"]
    assert w["verdict"]["h21"]["best_baseline"] == "mom_12_1"
    assert "mom_12_1" in w["verdict"]["h21"]["baselines_compared"]
    assert 7.9 < w["age_days"] < 8.1 and w["same_table_as_tonight"] is False
    assert "BEFORE the CRSP-deaths rebuild" in w["note"]
    assert t["forward_weight_sentence"].startswith("no model has earned forward weight; ensemble weights are zero")


# ── F8: the health contract ────────────────────────────────────────────────────

def _rec(rd, name, status, hours_ago, **kw):
    t = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    (rd / f"{name}.json").write_text(json.dumps({"run_id": name, "status": status, "written_utc": t, **kw}))


def test_health_contract_alive_refused_stale_unknown(tmp_path):
    rd = tmp_path / "receipts"
    rd.mkdir()
    assert nn_lab.health_contract(rd)["status"] == "UNKNOWN"
    _rec(rd, "nightly_20000101T000000Z", "OK", 3)
    h = nn_lab.health_contract(rd)
    assert h["status"] == "ALIVE" and h["line"].startswith("nn_lab_nightly ALIVE")
    _rec(rd, "nightly_20000102T000000Z", "REFUSED", 2, refused="TABLE_SHRINK: planted")
    _rec(rd, "nightly_20000103T000000Z", "FAILED", 1, error="planted")
    h = nn_lab.health_contract(rd)
    assert h["status"] == "REFUSED" and h["consecutive_non_ok"] == 2 and "planted" in h["line"]
    _rec(rd, "nightly_20000104T000000Z", "DEGRADED", C.HEALTH_MAX_AGE_HOURS + 1)
    h = nn_lab.health_contract(rd)
    assert h["status"] == "STALE" and h["consecutive_non_ok"] == 0
    _rec(rd, "nightly_20000105T000000Z", "STALE_BARS", 1)
    assert nn_lab.health_contract(rd)["status"] == "REFUSED"         # only OK / DEGRADED are alive
