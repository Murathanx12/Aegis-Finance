"""AEGIS-RESEARCH-EXECUTOR-1 — the lifecycle, proven on declared worlds.

The queue's first receipt said tests_run: 0. These tests prove the executor
can take a job from queued to recorded WITHOUT loosening a gate: adapters
are pinned to the submitted job's period/universe, blocked jobs report
reasons in words, instrument audits never touch the result slot, and a
dying adapter is counted, not hidden.
"""

from __future__ import annotations

import pytest

from backend.services import research_executor as RE
from backend.services.research_daemon import (HypothesisJob, JobRefused,
                                              ResearchDaemon)


def _job(hid="TEST-JOB-1", **kw):
    base = dict(hypothesis_id=hid, question="does the planted effect exist",
                universe="test-universe", outcome="test-outcome",
                start="2020-01-01", end="2025-12-31",
                n_date_blocks=60, se_per_block=0.1, expected_effect=0.08,
                effect_units="synthetic-units",
                cost_usd=0.0, cost_minutes=1.0, p_resolves=0.9,
                decision_value=0.5, distinct_claim="synthetic")
    base.update(kw)
    return HypothesisJob(**base)


def _daemon(*jobs):
    d = ResearchDaemon(reserved=[])          # written declaration: none
    for j in jobs:
        d.submit(j)
    return d


def _adapter(hid="TEST-JOB-1", *, kind=RE.KIND_RESULT, blocked=None,
             run=None, start="2020-01-01", end="2025-12-31",
             universe="test-universe"):
    return RE.JobAdapter(
        hypothesis_id=hid, kind=kind, reads_universe=universe,
        reads_start=start, reads_end=end,
        run=run or (lambda: RE.JobOutcome(p_value=0.03,
                                          observed_effect=0.09)),
        blocked_reason=blocked)


# ── lifecycle: queued → runnable → recorded ────────────────────────────────
def test_result_adapter_runs_end_to_end_and_m_counts_it():
    d = _daemon(_job())
    ex = RE.Executor(d)
    ex.register(_adapter())
    assert d.tests_run() == 0
    receipt = ex.run_ready()
    assert [e["hypothesis_id"] for e in receipt["executed"]] == ["TEST-JOB-1"]
    assert d.tests_run() == 1, "the daemon's own m must count the run"
    assert d.get("TEST-JOB-1").p_value == 0.03


def test_blocked_job_reports_its_reason_in_words():
    d = _daemon(_job())
    ex = RE.Executor(d)
    ex.register(_adapter(blocked="awaiting Murat's signature on the prereg"))
    receipt = ex.run_ready()
    assert receipt["executed"] == []
    assert receipt["blocked"][0]["reason"].startswith("awaiting Murat")
    assert d.tests_run() == 0


def test_no_adapter_is_legible_not_silent():
    d = _daemon(_job())
    receipt = RE.Executor(d).run_ready()
    assert receipt["no_adapter"] == ["TEST-JOB-1"]


def test_adapter_period_substitution_refuses():
    d = _daemon(_job())
    ex = RE.Executor(d)
    ex.register(_adapter(start="2010-01-01"))    # not what was submitted
    receipt = ex.run_ready()
    assert receipt["executed"] == []
    assert "substitute" in receipt["failed"][0]["error"]
    assert d.tests_run() == 0


def test_instrument_audit_never_touches_the_result_slot():
    d = _daemon(_job())
    ex = RE.Executor(d)
    ex.register(_adapter(kind=RE.KIND_INSTRUMENT_AUDIT,
                         run=lambda: {"n_episodes": 5}))
    receipt = ex.run_ready()
    assert receipt["audited"][0]["audit"]["n_episodes"] == 5
    assert d.tests_run() == 0, "an audit is not the trial's result"
    assert d.get("TEST-JOB-1").p_value is None


def test_dying_adapter_is_counted_not_hidden():
    d = _daemon(_job(), _job("TEST-JOB-2"))
    ex = RE.Executor(d)

    def _boom():
        raise ValueError("synthetic death")
    ex.register(_adapter(run=_boom))
    ex.register(_adapter("TEST-JOB-2"))
    receipt = ex.run_ready(max_jobs=5)
    assert len(receipt["failed"]) == 1
    assert "synthetic death" in receipt["failed"][0]["error"]
    # the other job still ran — a dead job must not kill the night
    assert [e["hypothesis_id"] for e in receipt["executed"]] == ["TEST-JOB-2"]


def test_result_adapter_returning_a_dict_refuses():
    d = _daemon(_job())
    ex = RE.Executor(d)
    ex.register(_adapter(run=lambda: {"p": 0.01}))
    receipt = ex.run_ready()
    assert "not JobOutcome" in receipt["failed"][0]["error"]
    assert d.tests_run() == 0


def test_second_result_for_one_submission_refuses_via_daemon():
    d = _daemon(_job())
    ex = RE.Executor(d)
    ex.register(_adapter())
    ex.run_ready()
    with pytest.raises(JobRefused):
        d.record_result("TEST-JOB-1", p_value=0.5)


def test_double_registration_refuses():
    ex = RE.Executor(_daemon(_job()))
    ex.register(_adapter())
    with pytest.raises(RE.ExecutorRefused):
        ex.register(_adapter())


def test_max_jobs_bounds_a_run_but_not_the_bookkeeping():
    jobs = [_job(f"TEST-JOB-{i}") for i in range(4)]
    d = _daemon(*jobs)
    ex = RE.Executor(d)
    for j in jobs:
        ex.register(_adapter(j.hypothesis_id))
    receipt = ex.run_ready(max_jobs=2)
    assert len(receipt["executed"]) == 2
    assert d.tests_run() == 2


# ── the convexity power audit, on the real episode file ────────────────────
from backend import config as _config

_EPISODES = _config.OPTIMUS_LEDGER_DIR / "convexity" / "episodes_v1.parquet"


@pytest.mark.skipif(
    not _EPISODES.exists(),
    reason="episodes_v1.parquet is a gitignored DATA artifact — absent in "
           "CI's checkout (this exact test turned CI red on 947624e; the "
           "audit's refusal path is covered by ExecutorRefused in the "
           "audit itself and runs in both worlds)")
def test_convexity_power_audit_reads_real_episodes_and_states_its_basis():
    out = RE.convexity_power_audit()
    assert out["n_episodes"] > 20_000
    assert out["n_date_blocks"] >= 2
    assert "verdict" not in str(out.get("audit_basis")).lower() or \
        "signed" in out["audit_basis"]
    assert out["audit_basis"].startswith("descriptive + power only")
