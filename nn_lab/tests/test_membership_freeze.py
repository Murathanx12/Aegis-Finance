"""Frozen decision-time membership (owner decision 2026-10-06, nn_lab/membership.py).

From 2026-10-01 the nightly refused every night with TableShrink because a vendor dividend
re-adjustment moved two names across the dollar-volume floor on two stored January grid
dates. These tests pin the fix: a re-adjustment is a REVISION, a genuine drop is still a
refusal, a frozen date's membership hash never moves, and a refusal writes a receipt.
Synthetic data only; every date is derived from today."""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from nn_lab import config as C
from nn_lab import membership as MB
from nn_lab import nightly as N
from nn_lab import table as T


def _cal(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=n)


def _stored(cal: pd.DatetimeIndex, dates, n_names: int = 40, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = pd.DataFrame([(d, f"S{i:03d}") for d in dates for i in range(n_names)], columns=["date", "symbol"])
    n = len(t)
    t["on_grid"] = True
    t["close"] = rng.uniform(10, 50, n).astype("float32")
    t["med_dv"] = rng.uniform(4e6, 9e6, n).astype("float32")
    t["sessions_seen"] = 300
    t["ret_1"] = rng.normal(0, 0.02, n).astype("float32")
    t["mom_5"] = rng.normal(0, 0.05, n).astype("float32")
    pos = np.searchsorted(cal.values, t["date"].values)
    for h in C.HORIZONS:
        elapsed = pos + 1 + h < len(cal)
        t[f"fwd_{h}"] = np.where(elapsed, rng.normal(0, 0.05, n), np.nan)
        t[f"delist_exit_{h}"] = False
        t[f"y_{h}"] = np.where(elapsed, rng.normal(0, 0.05, n), np.nan).astype("float32")
    return t


def _rebuilt_from(stored: pd.DataFrame) -> pd.DataFrame:
    r = stored.copy()
    r["_rebuild_eligible"] = True
    return r


def _merge(stored, rebuilt, cal, tail_start=None):
    ts = tail_start if tail_start is not None else stored["date"].min()
    return MB.merge_frozen(stored, rebuilt, tail_start=ts, cal_stored=cal, run_id="nightly_test",
                           asof_utc="test", vendor_bars_through=str(cal[-1].date()))


@pytest.fixture
def world():
    cal = _cal(160)
    dates = cal[10:150:5]
    return cal, _stored(cal, dates)


# ── a vendor re-adjustment is a revision, never a refusal ─────────────────────

def test_a_readjustment_that_makes_a_stored_member_ineligible_appends_a_revision_and_keeps_the_row(world):
    cal, st = world
    rb = _rebuilt_from(st)
    d0 = st["date"].min()
    hit = (rb["date"] == d0) & (rb["symbol"] == "S007")
    # the EQBK/THFF shape: a dividend re-adjustment rescales the history and the trailing
    # median dollar volume falls below the floor
    rb.loc[hit, "_rebuild_eligible"] = False
    rb.loc[hit, "med_dv"] = 2.9e6
    rb.loc[hit, "close"] = rb.loc[hit, "close"] * 0.985
    rb.loc[(rb["symbol"] == "S011"), "close"] *= 0.99          # a plain re-adjustment, still eligible
    new, revs, stats = _merge(st, rb, cal)
    assert stats["rows_dropped"] == 0 and stats["membership_would_drop"] == 1
    assert ((new["date"] == d0) & (new["symbol"] == "S007")).sum() == 1
    k = revs[revs["kind"] == "MEMBERSHIP_WOULD_DROP"]
    assert list(zip(k["date"], k["symbol"])) == [(d0, "S007")]
    assert "2,900,000" in k["reason"].iloc[0]
    fr = revs[revs["kind"] == "FEATURES_REVISED"]
    assert set(fr["symbol"]) == {"S007", "S011"} and fr["reason"].str.contains("rescaled").all()
    # the stored (decision-time) values are what the table keeps
    old = st.set_index(["date", "symbol"]).loc[(d0, "S007"), "close"]
    assert new.set_index(["date", "symbol"]).loc[(d0, "S007"), "close"] == old
    N.shrink_check(st, new)
    MB.check_frozen(st, new)


def test_a_stored_member_the_rebuild_cannot_produce_is_kept_with_a_revision(world):
    cal, st = world
    rb = _rebuilt_from(st)
    gone = (rb["symbol"] == "S003") & (rb["date"] == rb["date"].min())
    new, revs, stats = _merge(st, rb[~gone], cal)
    assert stats["member_absent_from_rebuild"] == 1 and stats["rows_dropped"] == 0
    assert (revs["kind"] == "MEMBER_ABSENT_FROM_REBUILD").sum() == 1
    N.shrink_check(st, new)


def test_a_name_the_readjustment_would_add_to_a_frozen_date_is_recorded_not_added(world):
    cal, st = world
    rb = _rebuilt_from(st)
    d0 = st["date"].min()
    extra = rb[(rb["date"] == d0)].head(1).copy()
    extra["symbol"] = "NEWNAME"
    new, revs, stats = _merge(st, pd.concat([rb, extra], ignore_index=True), cal)
    assert stats["membership_would_add"] == 1
    assert not (new["symbol"] == "NEWNAME").any()
    assert (revs["kind"] == "MEMBERSHIP_WOULD_ADD").sum() == 1


# ── a genuine drop is still refused ────────────────────────────────────────────

def test_a_genuine_drop_of_a_stored_row_still_raises(world):
    cal, st = world
    with pytest.raises(N.TableShrink):
        N.shrink_check(st, st.drop(index=5))
    lost_label = st.copy()
    i = int(np.flatnonzero(lost_label["y_5"].notna().to_numpy())[0])
    lost_label.loc[i, "y_5"] = np.nan
    with pytest.raises(N.TableShrink, match="labels"):
        N.shrink_check(st, lost_label)


def test_a_rebuild_that_loses_a_large_share_of_membership_is_refused_not_revised(world):
    """The 2026-09-26 shape: a rebuild on a truncated input reproduces 25 names, not 3,000."""
    cal, st = world
    rb = _rebuilt_from(st)
    keep = rb["symbol"].isin([f"S{i:03d}" for i in range(5)])
    with pytest.raises(N.TableShrink, match="broken input"):
        _merge(st, rb[keep], cal)


# ── the frozen hash is byte-stable ─────────────────────────────────────────────

def test_the_membership_hash_of_a_frozen_date_is_byte_stable_across_rebuilds(world):
    cal, st = world
    h0 = MB.membership_hashes(st)
    rb = _rebuilt_from(st)
    rb.loc[rb["symbol"] == "S001", "_rebuild_eligible"] = False      # vendor moved eligibility
    rb["close"] = rb["close"] * 1.01                                   # vendor rescaled everything
    newd = cal[-1]
    live = rb[rb["date"] == rb["date"].max()].copy()
    live["date"], live["on_grid"] = newd, True                         # a NEW date may be added
    new1, _, _ = _merge(st, pd.concat([rb, live], ignore_index=True), cal)
    new2, _, _ = _merge(new1, _rebuilt_from(new1).sample(frac=1.0, random_state=7), cal)
    h1, h2 = MB.membership_hashes(new1), MB.membership_hashes(new2)
    for d, h in h0.items():
        assert h1[d] == h and h2[d] == h
    assert str(newd.date()) in h1 and str(newd.date()) not in h0
    # order-free: shuffling the stored rows does not change a hash
    assert MB.membership_hashes(st.sample(frac=1.0, random_state=3)) == h0


# ── labels (review F10): an outcome is not decision-time knowledge ──────────

def test_a_matured_label_is_filled_and_a_recomputed_final_label_is_applied_and_logged(world):
    cal, st = world
    st = st.copy()
    final_d = st["date"].min()
    i_nan = st.index[(st["date"] == final_d) & (st["symbol"] == "S020")][0]
    st.loc[i_nan, "y_5"] = np.nan                                     # an outcome not yet stored
    rb = _rebuilt_from(st)
    rb.loc[i_nan, "y_5"] = 0.0123
    j = st.index[(st["date"] == final_d) & (st["symbol"] == "S021")][0]
    rb.loc[j, "y_5"] = st.loc[j, "y_5"] + 0.0005                      # the vendor corrects a FINAL label by 5 bp
    new, revs, stats = _merge(st, rb, cal)
    s = new.set_index(["date", "symbol"])
    assert s.loc[(final_d, "S020"), "y_5"] == pytest.approx(0.0123)
    assert s.loc[(final_d, "S021"), "y_5"] == pytest.approx(rb.loc[j, "y_5"])     # best-known value trains
    assert stats["labels_filled"] >= 1 and stats["labels_final_recomputed_applied_and_logged"] == 1
    lr = revs[revs["kind"] == "LABEL_RECOMPUTED"]
    assert len(lr) == 1 and "applied" in lr["reason"].iloc[0]
    # the features of that row stay the stored (decision-time) ones
    assert s.loc[(final_d, "S021"), "ret_1"] == st.loc[j, "ret_1"]


def _label_world(delta_bp: float):
    cal = _cal(160)
    st = _stored(cal, cal[10:150:5], n_names=40)
    st["y_5"] = st["y_5"].astype("float64")
    d0 = st["date"].min()
    k = st.index[(st["date"] == d0) & (st["symbol"] == "S005")][0]
    st.loc[k, "y_5"] = 0.0
    rb = _rebuilt_from(st)
    rb.loc[k, "y_5"] = delta_bp * 1e-4
    return cal, st, rb, k


def test_exactly_one_bp_is_not_a_label_revision_and_just_over_is():
    cal, st, rb, k = _label_world(1.0)
    new, revs, stats = _merge(st, rb, cal)
    assert C.LABEL_REVISION_MIN_ABS == 1e-4
    assert new.loc[new.index[(new["date"] == st.loc[k, "date"]) & (new["symbol"] == "S005")][0], "y_5"] == 0.0
    assert stats["labels_final_recomputed_applied_and_logged"] == 0
    assert stats["labels_final_changed_within_tolerance_not_applied"] == 1
    cal, st, rb, k = _label_world(1.0001)
    _, revs, stats = _merge(st, rb, cal)
    assert stats["labels_final_recomputed_applied_and_logged"] == 1 and (revs["kind"] == "LABEL_RECOMPUTED").sum() == 1


def test_a_sub_tolerance_drift_cannot_accumulate_unlogged():
    """0.9 bp a night: night 1 is within tolerance (not applied), so the stored label stays put;
    night 2 is measured against the STORED value (1.8 bp) and is applied AND logged."""
    cal, st, rb, k = _label_world(0.9)
    new1, revs1, s1 = _merge(st, rb, cal)
    assert s1["labels_final_recomputed_applied_and_logged"] == 0 and not (revs1["kind"] == "LABEL_RECOMPUTED").any()
    rb2 = _rebuilt_from(new1)
    k2 = rb2.index[(rb2["date"] == st.loc[k, "date"]) & (rb2["symbol"] == "S005")][0]
    rb2.loc[k2, "y_5"] = 1.8e-4
    new2, revs2, s2 = _merge(new1, rb2, cal)
    assert s2["labels_final_recomputed_applied_and_logged"] == 1
    assert new2.loc[k2, "y_5"] == pytest.approx(1.8e-4)
    assert "0.000000 -> 0.000180" in revs2.loc[revs2["kind"] == "LABEL_RECOMPUTED", "reason"].iloc[0]


# ── feature materiality (review F3) ─────────────────────────────────────────────

def test_cent_rounding_is_not_a_feature_revision_and_a_real_change_is(world):
    cal, st = world
    rb = _rebuilt_from(st)
    rb.loc[rb["symbol"] == "S001", "ret_1"] += 5e-4            # one cent on a $20 stock, twice
    rb.loc[rb["symbol"] == "S002", "med_dv"] *= 1.004          # 0.4%: inside the level tolerance
    rb.loc[rb["symbol"] == "S003", "ret_1"] += 2e-3            # a real change
    rb.loc[rb["symbol"] == "S004", "med_dv"] *= 1.006          # 0.6%: a real level change
    _, revs, _ = _merge(st, rb, cal)
    fr = set(revs.loc[revs["kind"] == "FEATURES_REVISED", "symbol"])
    assert fr == {"S003", "S004"}
    th = MB.thresholds()
    assert th["feature_revision_abs_tol"] == C.FEATURE_REVISION_ABS_TOL
    assert th["feature_revision_level_rel_tol"] == C.FEATURE_REVISION_LEVEL_REL_TOL


# ── the refusal cap at its boundary (review F4) ────────────────────────────────

def test_exactly_the_cap_of_absent_members_passes_and_one_more_refuses(world, monkeypatch):
    cal, st = world
    monkeypatch.setattr(C, "MEMBERSHIP_REFUSE_FLOOR", 3)
    monkeypatch.setattr(C, "MEMBERSHIP_REFUSE_SHARE", 0.0)
    rb = _rebuilt_from(st)
    d0 = rb["date"].min()
    gone3 = (rb["date"] == d0) & rb["symbol"].isin(["S001", "S002", "S003"])
    _, _, stats = _merge(st, rb[~gone3], cal)
    assert stats["member_absent_from_rebuild"] == 3 and stats["drop_cap"] == 3
    gone4 = (rb["date"] == d0) & rb["symbol"].isin(["S001", "S002", "S003", "S004"])
    with pytest.raises(N.TableShrink, match="absent"):
        _merge(st, rb[~gone4], cal)


# ── night status reads the membership counts (review F5) ──────────────────────

def test_an_absent_member_degrades_the_night_and_a_few_dividend_crossings_do_not():
    assert MB.degraded_reasons({"member_absent_from_rebuild": 1, "membership_would_drop": 0})
    assert not MB.degraded_reasons({"member_absent_from_rebuild": 0, "membership_would_drop": 4})
    assert MB.degraded_reasons({"membership_would_drop": C.NIGHT_DEGRADED_WOULD_DROP_OVER + 1})
    assert MB.degraded_reasons({"etf_removed_from_frozen_dates": 2})
    assert N.night_status(500, degraded=["1 stored members ABSENT"]) == "DEGRADED"
    assert N.night_status(500) == "OK"
    assert N.night_status(500, stale=True, degraded=["x"]) == "STALE_BARS"


# ── the revisions file is append-only and de-duplicated ────────────────────────

def test_the_same_vendor_value_seen_twice_is_one_revision(world, tmp_path):
    cal, st = world
    rb = _rebuilt_from(st)
    rb.loc[rb["symbol"] == "S002", "close"] *= 0.98
    _, revs, _ = _merge(st, rb, cal)
    p = tmp_path / "revisions.parquet"
    a = MB.append_revisions(revs, p)
    b = MB.append_revisions(revs, p)
    assert a["n_appended"] == len(revs) > 0 and b["n_appended"] == 0 and b["n_total"] == a["n_total"]
    rb.loc[rb["symbol"] == "S002", "close"] *= 0.98                   # a FURTHER adjustment is new
    _, revs2, _ = _merge(st, rb, cal)
    assert MB.append_revisions(revs2, p)["n_appended"] > 0


# ── the rebuild produces a forced (frozen) member whatever its eligibility ────

def test_price_rows_produces_a_forced_member_and_flags_its_rebuilt_eligibility():
    cal = _cal(200)
    rng = np.random.default_rng(5)
    out = []
    for s, vol in (("SPY", 5e6), ("LIQ", 4e5), ("THIN", 1e3)):
        c = 20 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, len(cal))))
        out.append(pd.DataFrame({"symbol": s, "date": cal, "open": c, "high": c * 1.01, "low": c * 0.99,
                                 "close": c, "volume": vol, "vwap": c, "trades": 900.0}))
    bars = pd.concat(out, ignore_index=True)
    d = cal[180]
    force = pd.DataFrame({"date": [d], "symbol": ["THIN"]})
    r = T.price_rows(bars, cal, keep_dates=pd.DatetimeIndex([d]), force_keys=force)
    thin = r[r["symbol"] == "THIN"]
    assert len(thin) == 1 and not bool(thin["_rebuild_eligible"].iloc[0])
    assert bool(r.loc[r["symbol"] == "LIQ", "_rebuild_eligible"].iloc[0])
    r0 = T.price_rows(bars, cal, keep_dates=pd.DatetimeIndex([d]))
    assert "THIN" not in set(r0["symbol"]) and "_rebuild_eligible" not in r0.columns


# ── a refusal writes a receipt, with its reason and the table size ────────────

@pytest.fixture
def night(tmp_path, monkeypatch):
    out = tmp_path / "nn_lab"
    for k, v in {"OUT": out, "RECEIPT_DIR": out / "receipts", "TABLE_DIR": out / "table",
                 "TABLE_PATH": out / "table" / "train_table.parquet", "STOP_FILE": out / "STOP",
                 "FORWARD_GRADES": out / "forward_grades.jsonl"}.items():
        monkeypatch.setattr(C, k, v)
    monkeypatch.setattr(N, "STATE_PATH", out / "night_state.json")
    monkeypatch.setattr(N, "LOCK_PATH", out / "night.lock")
    monkeypatch.setattr(N, "refuse_reason", lambda: None)
    return out


def test_a_table_shrink_refusal_writes_a_receipt_with_its_reason(night, monkeypatch):
    (night / "table").mkdir(parents=True)
    cal = _cal(60)
    _stored(cal, cal[5:50:5], n_names=10).to_parquet(night / "table" / "train_table.parquet", index=False)

    def boom(run_id="x"):
        raise N.TableShrink("table would LOSE 4 stored grid rows (planted)")
    monkeypatch.setattr(N, "step_append", boom)
    rec = N.main(time_box_min=5)
    p = night / "receipts" / f"{rec['run_id']}.json"
    assert p.exists()
    r = json.loads(p.read_text())
    assert r["status"] == "REFUSED" and "TABLE_SHRINK" in r["refused"]
    assert r["evidence"].startswith("NO_NEW_EVIDENCE")
    assert r["table_before"]["grid_rows"] == 90 and r["table_after"] == r["table_before"]
    assert r["run_id"].startswith("nightly_") and "T" in r["run_id"]      # a run id, never only a date


def test_an_early_refusal_writes_a_receipt_with_no_new_evidence(night, monkeypatch):
    monkeypatch.setattr(N, "refuse_reason", lambda: "LOW_MEMORY: planted")
    rec = N.main(time_box_min=5)
    r = json.loads((night / "receipts" / f"{rec['run_id']}.json").read_text())
    assert r["status"] == "REFUSED" and r["evidence"].startswith("NO_NEW_EVIDENCE")
    assert r["table_before"] is None


def test_the_audit_names_a_frozen_date_whose_membership_moved_between_receipts(tmp_path, world):
    cal, st = world
    h = {d: v[:16] for d, v in MB.membership_hashes(st).items()}
    rd = tmp_path / "receipts"
    rd.mkdir()
    (rd / "nightly_20000101T000000Z.json").write_text(json.dumps({"append": {"membership_hash_by_date": h}}))
    (rd / "nightly_20000102T000000Z.json").write_text(json.dumps({"status": "REFUSED"}))
    (rd / "nightly_20000103T000000Z.json").write_text(json.dumps({"append": {"membership_hash_by_date": h}}))
    st.to_parquet(tmp_path / "t.parquet", index=False)
    ok = MB.audit(rd, tmp_path / "t.parquet")
    assert ok["n_moved"] == 0 and ok["receipts_without_hashes_after_first"] == ["nightly_20000102T000000Z.json"]
    st.drop(index=0).to_parquet(tmp_path / "t.parquet", index=False)        # a member vanished on disk
    bad = MB.audit(rd, tmp_path / "t.parquet")
    assert bad["n_moved"] == 1 and bad["moved"][0][0] == "table_on_disk"
    assert MB.audit(tmp_path / "empty", tmp_path / "t.parquet")["status"].startswith("CANNOT_DETERMINE")
