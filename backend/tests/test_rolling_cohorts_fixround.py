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
