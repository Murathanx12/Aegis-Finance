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


# ── finding 1: a dead price feed is DEGRADED after the grace, never IDLE forever ──

def _reader(tmp_path, row):
    from datetime import datetime
    from backend.services import system_health as SH, task_receipts as TR
    p = tmp_path / "runs_reader.jsonl"
    p.write_text(json.dumps(row, default=str) + "\n", encoding="utf8")
    ctx = SH.ProbeCtx(optimus_dir=tmp_path / "o", now=datetime.fromisoformat(row["utc"]), repo=tmp_path,
                      paths={"rolling_cohort_runs": p})
    return TR.r_rolling_cohorts(ctx, None)


def test_a_dead_price_feed_goes_degraded_and_due_cohorts_are_missed_then_born_late(tmp_path):
    root = make_root(tmp_path, ANCHOR_I + 1)                       # the reviewer's attack A
    specs, out = subset_specs(tmp_path), tmp_path / "out"
    assert run("step", root, out, specs, utc(DAYS[ANCHOR_I]))["action"] == "BORN"
    r1 = run("step", root, out, specs, utc(DAYS[ANCHOR_I + 1], 22))           # 1 h after the close
    assert r1["action"] == "WAIT_PRICES" and _reader(tmp_path, r1).status == "IDLE"
    r6 = run("step", root, out, specs, utc(DAYS[ANCHOR_I + 6], 22))
    assert r6["action"] == "STALE_PRICES" and r6["rc"] == 0
    assert "bars have not advanced since" in r6["reason"]
    assert r6["forward_age_sessions"] == 6                         # exchange sessions, not bars sessions
    assert [m["cohort_id"] for m in r6["missed"]] == [DAYS[ANCHOR_I + 5].date().isoformat()]
    assert _reader(tmp_path, r6).status == "DEGRADED"
    # the feed comes back on the evening of +6: the missed slot is born LATE, decided on +6
    pd.read_parquet(make_root(tmp_path / "fresh", ANCHOR_I + 7) / R.BARS_REL).to_parquet(root / R.BARS_REL, index=False)
    r7 = run("step", root, out, specs, utc(DAYS[ANCHOR_I + 6], 23))
    assert r7["action"] == "BORN" and r7["born"][0]["born_late"] is True
    _, rec = _books(out, DAYS[ANCHOR_I + 5])
    assert rec["born_late"] is True and rec["decision_date"] == DAYS[ANCHOR_I + 6].date().isoformat()
    assert rec["entry_session"] == DAYS[ANCHOR_I + 7].date().isoformat() and rec["forward_evidence"] is True
    assert _reader(tmp_path, r7).status == "DEGRADED"              # the miss is reported once


# ── finding 2: the scoreboard is calibrated under pure noise ─────────────────

def _null_series(kind: str, n_blocks: int, rng, h: int = 21):
    n_sessions = n_blocks * 2 * h
    idx = list(range(0, n_sessions, 5))                           # weekly cohorts
    if kind == "independent":
        return list(rng.normal(0, 0.03, len(idx))), idx
    daily = rng.normal(0, 0.03 / np.sqrt(h), n_sessions + h)       # overlapping 21-session holds
    return [float(daily[i:i + h].sum()) for i in idx], idx


@pytest.mark.parametrize("kind", ["independent", "overlapping"])
@pytest.mark.parametrize("n_blocks", [6, 12])
def test_pure_noise_specs_are_labelled_at_or_below_the_nominal_rate(kind, n_blocks):
    rng = np.random.default_rng(1000 + n_blocks + (kind == "overlapping"))
    stats = [R.block_stats(*_null_series(kind, n_blocks, rng), horizon=21) for _ in range(400)]
    head = R.label_tests(stats)
    raw = np.mean([s["p"] is not None and s["p"] < 0.05 for s in stats])
    labelled = np.mean([s["verdict"].startswith("OBSERVED") for s in stats])
    assert raw <= 0.05 + 0.03                                      # the t on strict blocks is calibrated
    assert labelled <= 0.05 + 0.01                                 # BH across the run, never above nominal
    assert head["crossings_expected_by_chance"] == pytest.approx(0.05 * head["eligible_tests"])
    assert "crossings expected by chance" in head["line"]


def test_too_few_strict_blocks_is_never_labelled():
    rng = np.random.default_rng(3)
    v, idx = _null_series("independent", 4, rng)
    s = R.block_stats([x + 0.5 for x in v], idx, horizon=21)        # a huge mean, 4 strict blocks
    R.label_tests([s])
    assert s["n_blocks_strict"] == 4 and s["verdict"] == "CANNOT DETERMINE (4 blocks of 6)"
    assert s["block_sessions"] == 42 and s["df"] == 3


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


# ── finding 5: one clock -- a 1-day spec sees the 24 h before the cutoff ────

def test_one_day_revision_specs_see_the_day_before_the_cutoff(tmp_path):
    d, e = DAYS[ANCHOR_I], DAYS[ANCHOR_I + 1]
    assert (e - d).days == 1                                     # the fixture's cohort is mid-week
    root = make_root(tmp_path, ANCHOR_I + 1)
    rv = pd.read_parquet(root / R.REVISIONS_REL)
    fresh = [dict(ticker="S03", event_date=str(d + pd.Timedelta(hours=15)), firm=f"N{f}", target_action="Raises",
                  prior_target=50.0, current_target=60.0, pit_safe=True,
                  first_seen_utc=(d + pd.Timedelta(hours=18)).tz_localize("UTC").isoformat()) for f in range(5)]
    pd.concat([rv, pd.DataFrame(fresh)], ignore_index=True).to_parquet(root / R.REVISIONS_REL, index=False)
    full = json.loads(R.Path(subset_specs(tmp_path)).read_bytes())
    allspecs = json.loads((R.REPO / "docs/TRIALS/ROLLING-COHORTS-SPECIFICATIONS-v2.json").read_bytes())
    full["specifications"] = [s for s in allspecs["specifications"]
                              if s["family"] == "revision_flow" and s["max_age_days"] == 1][:6]
    sp = tmp_path / "oneday.json"
    sp.write_text(json.dumps(full), encoding="utf8")
    run("step", root, tmp_path / "out", sp, utc(d))
    _, rec = _books(tmp_path / "out", d)
    ready = [b for b in rec["books"] if b["status"] == "READY"]
    assert ready and all(set(b["long"]) == {"S03"} for b in ready)
    assert rec["decision_utc"] == rec["available_before_utc"]      # one clock


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
