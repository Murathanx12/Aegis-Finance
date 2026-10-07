"""C15 (2026-10-07; review C5 F9): the vendor-revisions log is a TIMELINE and rotates monthly.

* a flip-flop A(stored) -> B -> A is TWO revisions (B, then a REVERTED_TO_STORED row);
  A -> B -> C -> B is three; the same B seen again is still one;
* closed months (by each row's own `asof_utc`) move to a sealed monthly parquet with a
  manifest (rows, kinds, sha256), written once; the timeline spans the rotation.
Offline; every date derives from `today` (protocol item 5).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from nn_lab import membership as MB
from nn_lab.tests.test_membership_freeze import _cal, _merge, _rebuilt_from, _stored


def _log(tmp_path):
    p = tmp_path / "nn" / "table" / "revisions.parquet"
    p.parent.mkdir(parents=True)
    return p


def _rev(d, sym, h, kind="FEATURES_REVISED", asof="2026-10-07T00:00:00+00:00", columns="close"):
    return pd.DataFrame({"date": [pd.Timestamp(d)], "symbol": [sym], "kind": [kind], "reason": ["x"],
                         "columns": [columns], "max_rel_change": [0.02], "rebuilt_values_hash": [h],
                         "asof_utc": [asof], "run_id": ["t"], "vendor_bars_through": [""]})


def _empty():
    return pd.DataFrame(columns=MB.REV_COLS)


def test_a_vendor_flip_flop_a_b_a_is_two_revisions_through_the_real_merge(tmp_path):
    cal = _cal(160)
    st = _stored(cal, cal[10:150:5])
    p = _log(tmp_path)
    ts = st["date"].min()
    rb = _rebuilt_from(st)
    rb.loc[rb["symbol"] == "S002", "ret_1"] += 0.05                    # night 1: vendor says B
    _, revs_b, _ = _merge(st, rb, cal)
    assert len(revs_b) and set(revs_b["symbol"]) == {"S002"}
    a1 = MB.append_revisions(revs_b, p, checked_from=ts, run_id="n1")
    _, revs_a, _ = _merge(st, _rebuilt_from(st), cal)                   # night 2: back to stored A
    assert len(revs_a) == 0
    a2 = MB.append_revisions(revs_a, p, checked_from=ts, run_id="n2")
    assert a2["n_reverted"] == a1["n_appended"] > 0
    log = pd.read_parquet(p)
    one = log[(log["symbol"] == "S002") & (log["date"] == log["date"].min())]
    assert list(one["rebuilt_values_hash"].iloc[1:]) == [MB.REVERTED_HASH]   # B, then the reversion
    # night 3: the same A again changes nothing; night 4: B again is a NEW revision
    assert MB.append_revisions(revs_a, p, checked_from=ts)["n_appended"] == 0
    assert MB.append_revisions(revs_b, p, checked_from=ts)["n_appended"] == a1["n_appended"]


def test_b_c_b_is_three_and_the_same_value_twice_is_one(tmp_path):
    p = _log(tmp_path)
    d = date.today().replace(day=1)
    assert MB.append_revisions(_rev(d, "X", "B"), p)["n_appended"] == 1
    assert MB.append_revisions(_rev(d, "X", "B"), p)["n_appended"] == 0
    assert MB.append_revisions(_rev(d, "X", "C"), p)["n_appended"] == 1
    assert MB.append_revisions(_rev(d, "X", "B"), p)["n_appended"] == 1
    assert list(pd.read_parquet(p)["rebuilt_values_hash"]) == ["B", "C", "B"]


def test_reversion_is_only_for_checked_dates_and_frozen_kinds(tmp_path):
    p = _log(tmp_path)
    old, new = pd.Timestamp("2026-01-05"), pd.Timestamp("2026-03-02")
    MB.append_revisions(pd.concat([_rev(old, "X", "B"), _rev(new, "Y", "B"),
                                   _rev(new, "Z", "L", kind="LABEL_RECOMPUTED", columns="y_5")]), p)
    out = MB.append_revisions(_empty(), p, checked_from=pd.Timestamp("2026-02-01"))
    log = pd.read_parquet(p)
    rev = log[log["rebuilt_values_hash"] == MB.REVERTED_HASH]
    assert out["n_reverted"] == 1 and list(rev["symbol"]) == ["Y"]     # X unchecked; a label is applied, not reverted
    assert MB.append_revisions(_empty(), p, checked_from=pd.Timestamp("2026-02-01"))["n_reverted"] == 0


def _two_months(tmp_path):
    p = _log(tmp_path)
    today = datetime.now(timezone.utc)
    prev = (pd.Timestamp(today.date()).replace(day=1) - pd.Timedelta(days=1))
    MB.append_revisions(pd.concat([_rev(prev, "X", "B", asof=prev.isoformat()),
                                   _rev(prev, "Y", "B", asof=prev.isoformat()),
                                   _rev(today.date(), "Z", "B", asof=today.isoformat())]), p)
    return p, today, prev, prev.strftime("%Y-%m")


def test_a_sealed_but_untracked_month_keeps_every_row_live(tmp_path):
    """Review C15 M4: C10's rule -- rows leave the live file only once git TRACKS the parquet."""
    p, today, prev, pm = _two_months(tmp_path)
    out = MB.rotate_revisions(p, now=today, tracked=lambda _p: False)
    assert [s["month"] for s in out["sealed"]] == [pm] and out["removed"] == []
    assert out["pending"][0]["state"] == "SEALED_PENDING_COMMIT" and "git add" in out["pending"][0]["why"]
    assert sorted(pd.read_parquet(p)["symbol"]) == ["X", "Y", "Z"]      # nothing removed
    adir = MB.revisions_archive_dir(p)
    assert adir == tmp_path / "nn" / "revisions_archive"
    arch = adir / f"revisions_{pm}.parquet"
    man = json.loads((adir / f"revisions_{pm}.json").read_text(encoding="utf-8"))
    assert man["rows"] == 2 and man["kinds"] == {"FEATURES_REVISED": 2}
    assert man["parquet_sha256"] == hashlib.sha256(arch.read_bytes()).hexdigest()
    # the history counts the duplicated month once in effect: B seen again is still not new
    assert MB.append_revisions(_rev(prev, "X", "B", asof=today.isoformat()), p)["n_appended"] == 0


def test_once_tracked_the_month_leaves_the_live_file_and_the_timeline_spans_it(tmp_path):
    p, today, prev, pm = _two_months(tmp_path)
    MB.rotate_revisions(p, now=today, tracked=lambda _p: False)          # night N: sealed, pending
    out = MB.rotate_revisions(p, now=today, tracked=lambda _p: True)     # night N+1: committed
    assert out["status"] == "OK" and out["removed"] == [{"month": pm, "rows": 2}] and out["sealed"] == []
    assert list(pd.read_parquet(p)["symbol"]) == ["Z"]
    assert MB.append_revisions(_rev(prev, "X", "B", asof=today.isoformat()), p)["n_appended"] == 0


def test_a_tampered_or_mismatched_month_is_refused_never_removed(tmp_path):
    p, today, prev, pm = _two_months(tmp_path)
    MB.rotate_revisions(p, now=today, tracked=lambda _p: False)
    live = pd.read_parquet(p)
    pd.concat([live, _rev(prev, "Q", "B", asof=prev.isoformat())]).to_parquet(p, index=False)
    out = MB.rotate_revisions(p, now=today, tracked=lambda _p: True)
    assert out["status"] == "REFUSED" and "differ from" in out["refused"][0]["why"]
    assert "Q" in set(pd.read_parquet(p)["symbol"])                     # never lost
    arch = MB.revisions_archive_dir(p) / f"revisions_{pm}.parquet"
    pd.read_parquet(arch).head(1).to_parquet(arch, index=False)          # truncate the sealed month
    with pytest.raises(MB.RevisionsArchiveCorrupt):
        MB.revisions_history(p)
    assert "hash" in MB.rotate_revisions(p, now=today, tracked=lambda _p: True)["refused"][0]["why"]


def test_gitignore_tracks_the_rotated_months():
    from pathlib import Path
    gi = (Path(MB.C.REPO) / ".gitignore").read_text(encoding="utf-8")
    assert "!backend/data/optimus/nn_lab/revisions_archive/*.parquet" in gi

