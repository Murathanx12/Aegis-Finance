"""PR #147 fix round: one test per review finding. Synthetic fixtures only.

Shares the fixtures of `test_rolling_cohorts` (past synthetic business days, injected calendar).
"""
from __future__ import annotations

import json
import threading
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from backend import config as _config
from backend.services import disk_guard
from backend.services.portfolio_intelligence import branch_population_rolling as R
from backend.tests.test_rolling_cohorts import (ANCHOR_I, DAYS, _books, cfg, make_root,  # noqa: F401
                                                run, subset_specs, utc)


# ── finding 4: one run at a time; duplicate marks fail loud ─────────────────

def test_a_second_concurrent_run_waits_cleanly(tmp_path, monkeypatch):
    root = make_root(tmp_path, ANCHOR_I + 1)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    monkeypatch.setattr(_config, "ROLLING_COHORT_LOCK_WAIT_S", 0.2)
    held, release = threading.Event(), threading.Event()

    def holder():
        with disk_guard.file_lock(out / "run.lock", timeout_s=5):
            held.set()
            release.wait(10)

    t = threading.Thread(target=holder)
    t.start()
    held.wait(5)
    try:
        r = run("step", root, out, specs, utc(DAYS[ANCHOR_I]))
    finally:
        release.set()
        t.join()
    assert r["action"] == "WAIT_LOCK" and r["rc"] == 0 and r["born"] == []
    assert not (out / "cohorts").exists()
    assert run("step", root, out, specs, utc(DAYS[ANCHOR_I]))["action"] == "BORN"


def test_duplicate_marks_fail_loud(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 31)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    now = utc(DAYS[ANCHOR_I + 31])
    run("backfill", root, out, specs, now, date_from=DAYS[ANCHOR_I])
    st = R.Store(out)
    part = next((out / "marks").glob("part-*.parquet"))
    pd.read_parquet(part).to_parquet(out / "marks" / "part-racer.parquet", index=False)   # the racer's copy
    with pytest.raises(R.RollingCohortRefused, match="duplicate"):
        st.marks()
    with pytest.raises(R.RollingCohortRefused, match="duplicate"):
        run("step", root, out, specs, now + timedelta(minutes=1))


# ── finding 3: no zero costs; the grading config is bound to the declaration ──

@pytest.mark.parametrize("what", ["bands", "spy", "borrow"])
def test_zero_costs_are_refused(tmp_path, monkeypatch, what):
    from backend.services import xs_ranker as XR
    if what == "bands":
        monkeypatch.setattr(XR, "COST_BPS_BY_BAND", {k: 0.0 for k in XR.COST_BPS_BY_BAND})
    elif what == "spy":
        monkeypatch.setattr(_config, "ROLLING_COHORT_SPY_COST_BPS", 0.0)
    else:
        monkeypatch.setattr(_config, "ROLLING_COHORT_SHORT_BORROW_BPS_YR", 0.0)
    root = make_root(tmp_path, ANCHOR_I + 1)
    with pytest.raises(R.RollingCohortRefused, match="cost"):
        run("step", root, tmp_path / "out", subset_specs(tmp_path), utc(DAYS[ANCHOR_I]))


def test_zero_cost_diagnostic_is_carried_onto_every_row(tmp_path, monkeypatch):
    from backend.services import xs_ranker as XR
    monkeypatch.setattr(XR, "COST_BPS_BY_BAND", {k: 0.0 for k in XR.COST_BPS_BY_BAND})
    monkeypatch.setattr(_config, "ROLLING_COHORT_ZERO_COST_DIAGNOSTIC", True)
    root = make_root(tmp_path, ANCHOR_I + 31)
    out = tmp_path / "out"
    run("backfill", root, out, subset_specs(tmp_path), utc(DAYS[ANCHOR_I + 31]), date_from=DAYS[ANCHOR_I])
    m = R.Store(out).marks()
    assert len(m) and m["zero_cost_diagnostic"].all()
    _, rec = _books(out, DAYS[ANCHOR_I])
    assert rec["zero_cost_diagnostic"] is True


def test_a_changed_grading_config_is_refused_by_name(tmp_path, monkeypatch):
    root = make_root(tmp_path, ANCHOR_I + 31)
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    now = utc(DAYS[ANCHOR_I + 31])
    run("backfill", root, out, specs, now, date_from=DAYS[ANCHOR_I])
    m = R.Store(out).marks()
    decl = R.Store(out).declaration()
    assert (m["config_hash"] == decl["config_hash"]).all() and "code_version" in m.columns
    monkeypatch.setattr(_config, "ROLLING_COHORT_SHORT_BORROW_BPS_YR", 45.0)
    with pytest.raises(R.RollingCohortRefused, match="ROLLING_COHORT_SHORT_BORROW_BPS_YR"):
        run("step", root, out, specs, now + timedelta(minutes=1))
    monkeypatch.setattr(_config, "ROLLING_COHORT_SHORT_BORROW_BPS_YR", decl["config"]["ROLLING_COHORT_SHORT_BORROW_BPS_YR"])
    monkeypatch.setattr(_config, "ROLLING_COHORT_LOCK_WAIT_S", 5.0)        # operational, not grading
    assert run("step", root, out, specs, now + timedelta(minutes=2))["rc"] == 0


# ── finding 7: news versions cached after the cutoff never change a cohort ──

def test_a_news_retype_cached_after_the_cutoff_does_not_change_a_backfilled_cohort(tmp_path):
    from backend.tests.test_rolling_cohorts import news_lines
    d, e = DAYS[ANCHOR_I], DAYS[ANCHOR_I + 1]
    clean = make_root(tmp_path / "c", ANCHOR_I + 26)
    pois = make_root(tmp_path / "p", ANCHOR_I + 26)
    late = []
    for ln in news_lines(d, n=20):                                  # the reviewer's fixture B
        rec = json.loads(ln)
        rec["row"]["event_type"] = "guidance"
        rec["cached_utc"] = (pd.Timestamp(e) + pd.Timedelta(days=3)).tz_localize("UTC").isoformat()
        late.append(json.dumps(rec))
    with (pois / R.NEWS_REL).open("a", encoding="utf8") as f:
        f.write("\n".join(late) + "\n")
    sp = subset_specs(tmp_path, per_family=10)
    now = utc(DAYS[ANCHOR_I + 30])
    for root, name in ((clean, "a"), (pois, "b")):
        run("backfill", root, tmp_path / name, sp, now, date_from=d, date_to=d)
    ba, ra = _books(tmp_path / "a", d)
    bb, rb = _books(tmp_path / "b", d)
    assert ra["input_status"]["news"]["status"] == "OK"
    assert ra["input_status"]["news"]["n_items_5d"] == rb["input_status"]["news"]["n_items_5d"] == 20
    assert ba == bb
