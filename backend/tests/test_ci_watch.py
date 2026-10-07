"""Tests for scripts/ci_watch.py (Q16, 2026-10-07).

Every fixture under backend/tests/fixtures/ci_watch/ is a REAL response saved
from the public GitHub API on 2026-10-07 while reproducing the day's two
false-negative incidents (see the module docstring in scripts/ci_watch.py for
the root-cause narrative). Tests mock `ci_watch._get` and the `git`-wrapping
helpers so the suite stays fully offline (network is blocked for non-slow
tests by backend/tests/conftest.py) while still exercising the exact JSON
shapes GitHub actually returned.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import ci_watch

FIXTURES = Path(__file__).parent / "fixtures" / "ci_watch"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# select_ci_run: the fix for root cause #1 (picking "newest run" by index
# across workflows masked CI behind the Vercel deploy run).
# ---------------------------------------------------------------------------

def test_select_ci_run_picks_ci_not_the_other_workflow():
    # 92f147f6 really did return the Vercel run before the CI run in GitHub's
    # own ordering (verified live) -- the fix must not depend on list order.
    all_runs = _load("runs_92f147f6_by_head_sha.json")["workflow_runs"]
    assert all_runs[0]["name"] == "Deploy frontend to Vercel"
    ci_run, others = ci_watch.select_ci_run(all_runs)
    assert ci_run is not None
    assert ci_run["name"] == "CI"
    assert ci_run["conclusion"] == "failure"
    assert [o["name"] for o in others] == ["Deploy frontend to Vercel"]


def test_select_ci_run_none_when_no_ci_workflow_present():
    ci_run, others = ci_watch.select_ci_run(
        [{"name": "Deploy frontend to Vercel", "status": "completed", "conclusion": "success"}]
    )
    assert ci_run is None
    assert len(others) == 1


# ---------------------------------------------------------------------------
# Case: success (e041ec14 -- the commit that actually went green on main).
# ---------------------------------------------------------------------------

def test_watch_success(monkeypatch):
    runs_payload = _load("runs_e041ec14_by_head_sha.json")
    jobs_payload = _load("jobs_e041ec14.json")

    calls = {"runs": 0}

    def fake_get(url):
        if "/actions/runs?head_sha=" in url:
            calls["runs"] += 1
            return runs_payload
        if "/jobs" in url:
            return jobs_payload
        if "/annotations" in url:
            return []
        raise AssertionError(f"unexpected URL in success case: {url}")

    monkeypatch.setattr(ci_watch, "_get", fake_get)
    monkeypatch.setattr(ci_watch, "ci_can_ever_run", lambda sha: (True, "on main"))

    sha = "e041ec140b91a9df680e13a65a5a5796f1c9270c"
    rc = ci_watch.watch(sha, wait=False, wait_minutes=40)
    assert rc == ci_watch.EXIT_SUCCESS
    assert calls["runs"] == 1


# ---------------------------------------------------------------------------
# Case: failure with annotations (92f147f6's CI run) -- the diagnosability
# requirement: print which job/step failed and the check-run annotation text
# without a token.
# ---------------------------------------------------------------------------

def test_watch_failure_prints_annotations(monkeypatch, capsys):
    runs_payload = _load("runs_92f147f6_by_head_sha.json")
    jobs_payload = _load("jobs_92f147f6_ci_failure.json")
    annotations_payload = _load("annotations_112633519248.json")

    def fake_get(url):
        if "/actions/runs?head_sha=" in url:
            return runs_payload
        if "/jobs" in url:
            return jobs_payload
        if "/check-runs/112633519248/annotations" in url:
            return annotations_payload
        if "/annotations" in url:
            return []
        raise AssertionError(f"unexpected URL in failure case: {url}")

    monkeypatch.setattr(ci_watch, "_get", fake_get)
    monkeypatch.setattr(ci_watch, "ci_can_ever_run", lambda sha: (True, "on main"))

    sha = "92f147f6334f3651a98277f0aada1eaa5c26671b"
    rc = ci_watch.watch(sha, wait=False, wait_minutes=40)
    assert rc == ci_watch.EXIT_CI_FAILED

    out = capsys.readouterr().out
    assert "(other workflow, not the verdict)" in out
    assert "Deploy frontend to Vercel" in out
    assert "backend (pytest offline + ruff + pip-audit): failure" in out
    # The actual failing-test message from the real annotation, so a session
    # can diagnose red CI from this one call, no token needed.
    assert "test_firm_reliability_is_byte_identical_to_the_pinned_fixture" in out


# ---------------------------------------------------------------------------
# Case: in-progress, then success, across two polls.
# ---------------------------------------------------------------------------

def test_watch_in_progress_then_success(monkeypatch):
    base_run = _load("runs_e041ec14_by_head_sha.json")["workflow_runs"][0]
    in_progress = {**base_run, "status": "in_progress", "conclusion": None}
    completed = base_run
    jobs_payload = _load("jobs_e041ec14.json")

    poll_sequence = [
        {"total_count": 1, "workflow_runs": [in_progress]},
        {"total_count": 1, "workflow_runs": [completed]},
    ]
    calls = {"runs": 0, "sleeps": 0}

    def fake_get(url):
        if "/actions/runs?head_sha=" in url:
            payload = poll_sequence[min(calls["runs"], len(poll_sequence) - 1)]
            calls["runs"] += 1
            return payload
        if "/jobs" in url:
            return jobs_payload
        if "/annotations" in url:
            return []
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(ci_watch, "_get", fake_get)
    monkeypatch.setattr(ci_watch, "ci_can_ever_run", lambda sha: (True, "on main"))
    monkeypatch.setattr(ci_watch.time, "sleep", lambda s: calls.__setitem__("sleeps", calls["sleeps"] + 1))

    sha = "e041ec140b91a9df680e13a65a5a5796f1c9270c"
    rc = ci_watch.watch(sha, wait=True, wait_minutes=40)
    assert rc == ci_watch.EXIT_SUCCESS
    assert calls["runs"] == 2
    assert calls["sleeps"] == 1


# ---------------------------------------------------------------------------
# Case: the Vercel run completes long before CI does -- must not be read as
# the verdict, and must not short-circuit the wait for CI itself.
# ---------------------------------------------------------------------------

def test_watch_vercel_run_does_not_mask_ci_still_running(monkeypatch):
    all_runs = _load("runs_92f147f6_by_head_sha.json")["workflow_runs"]
    ci_run = next(r for r in all_runs if r["name"] == "CI")
    vercel_run = next(r for r in all_runs if r["name"] != "CI")
    ci_in_progress = {**ci_run, "status": "in_progress", "conclusion": None}

    poll_sequence = [
        {"total_count": 2, "workflow_runs": [vercel_run, ci_in_progress]},
        {"total_count": 2, "workflow_runs": [vercel_run, ci_run]},  # ci_run: completed/failure
    ]
    calls = {"runs": 0}

    def fake_get(url):
        if "/actions/runs?head_sha=" in url:
            payload = poll_sequence[min(calls["runs"], len(poll_sequence) - 1)]
            calls["runs"] += 1
            return payload
        if "/jobs" in url:
            return {"jobs": []}
        if "/annotations" in url:
            return []
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(ci_watch, "_get", fake_get)
    monkeypatch.setattr(ci_watch, "ci_can_ever_run", lambda sha: (True, "on main"))
    monkeypatch.setattr(ci_watch.time, "sleep", lambda s: None)

    rc = ci_watch.watch("92f147f6334f3651a98277f0aada1eaa5c26671b", wait=True, wait_minutes=40)
    # The verdict must come from CI's own (eventual) conclusion, not Vercel's
    # success masking a still-running or differently-concluded CI run.
    assert rc == ci_watch.EXIT_CI_FAILED
    assert calls["runs"] == 2


# ---------------------------------------------------------------------------
# Case: eventual consistency -- the run has not appeared in the API yet.
# ---------------------------------------------------------------------------

def test_watch_no_run_yet_then_appears(monkeypatch):
    jobs_payload = _load("jobs_e041ec14.json")
    completed = _load("runs_e041ec14_by_head_sha.json")["workflow_runs"][0]

    poll_sequence = [
        {"total_count": 0, "workflow_runs": []},
        {"total_count": 0, "workflow_runs": []},
        {"total_count": 1, "workflow_runs": [completed]},
    ]
    calls = {"runs": 0}

    def fake_get(url):
        if "/actions/runs?head_sha=" in url:
            payload = poll_sequence[min(calls["runs"], len(poll_sequence) - 1)]
            calls["runs"] += 1
            return payload
        if "/jobs" in url:
            return jobs_payload
        if "/annotations" in url:
            return []
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(ci_watch, "_get", fake_get)
    monkeypatch.setattr(ci_watch, "ci_can_ever_run", lambda sha: (True, "on main"))
    monkeypatch.setattr(ci_watch.time, "sleep", lambda s: None)

    rc = ci_watch.watch("e041ec140b91a9df680e13a65a5a5796f1c9270c", wait=True, wait_minutes=40)
    assert rc == ci_watch.EXIT_SUCCESS
    assert calls["runs"] == 3


def test_watch_no_run_ever_appears_times_out(monkeypatch):
    def fake_get(url):
        if "/actions/runs?head_sha=" in url:
            return {"total_count": 0, "workflow_runs": []}
        raise AssertionError(f"unexpected URL: {url}")

    now = {"t": 0.0}
    monkeypatch.setattr(ci_watch, "_get", fake_get)
    monkeypatch.setattr(ci_watch, "ci_can_ever_run", lambda sha: (True, "on main"))
    monkeypatch.setattr(ci_watch.time, "time", lambda: now["t"])

    def fake_sleep(s):
        now["t"] += s

    monkeypatch.setattr(ci_watch.time, "sleep", fake_sleep)

    rc = ci_watch.watch("f" * 40, wait=True, wait_minutes=1)
    assert rc == ci_watch.EXIT_NO_RUN_APPEARED


# ---------------------------------------------------------------------------
# Case: a run exists but is still in progress when the wait window closes.
# ---------------------------------------------------------------------------

def test_watch_timed_out_while_in_progress(monkeypatch):
    base_run = _load("runs_e041ec14_by_head_sha.json")["workflow_runs"][0]
    in_progress = {**base_run, "status": "in_progress", "conclusion": None}

    def fake_get(url):
        if "/actions/runs?head_sha=" in url:
            return {"total_count": 1, "workflow_runs": [in_progress]}
        raise AssertionError(f"unexpected URL: {url}")

    now = {"t": 0.0}
    monkeypatch.setattr(ci_watch, "_get", fake_get)
    monkeypatch.setattr(ci_watch, "ci_can_ever_run", lambda sha: (True, "on main"))
    monkeypatch.setattr(ci_watch.time, "time", lambda: now["t"])
    monkeypatch.setattr(ci_watch.time, "sleep", lambda s: now.__setitem__("t", now["t"] + s))

    rc = ci_watch.watch("e041ec140b91a9df680e13a65a5a5796f1c9270c", wait=True, wait_minutes=1)
    assert rc == ci_watch.EXIT_TIMED_OUT_IN_PROGRESS


# ---------------------------------------------------------------------------
# Root cause #5: the resolved commit lives only on a branch that cannot
# trigger CI (not main, no open PR) -- must refuse immediately, no polling.
# ---------------------------------------------------------------------------

def test_ci_can_ever_run_refuses_wip_branch_with_no_pr(monkeypatch):
    monkeypatch.setattr(ci_watch, "sha_is_on_main", lambda sha: False)
    monkeypatch.setattr(ci_watch, "current_branch", lambda: "wip/2026-10-07-day")
    monkeypatch.setattr(ci_watch, "open_pr_for_branch", lambda branch: None)

    can_run, reason = ci_watch.ci_can_ever_run("0b6655f38363fd0420223c8b094553e27283151e")
    assert can_run is False
    assert "wip/2026-10-07-day" in reason


def test_ci_can_ever_run_allows_open_pr(monkeypatch):
    monkeypatch.setattr(ci_watch, "sha_is_on_main", lambda sha: False)
    monkeypatch.setattr(ci_watch, "current_branch", lambda: "feature/x")
    monkeypatch.setattr(
        ci_watch, "open_pr_for_branch",
        lambda branch: {"number": 42, "html_url": "https://github.com/x/y/pull/42"},
    )

    can_run, reason = ci_watch.ci_can_ever_run("a" * 40)
    assert can_run is True
    assert "#42" in reason


def test_ci_can_ever_run_unknown_is_not_a_refusal(monkeypatch):
    # sha_is_on_main returning None (git couldn't tell, e.g. origin/main not
    # fetched locally) must never be treated as grounds to refuse.
    monkeypatch.setattr(ci_watch, "sha_is_on_main", lambda sha: None)
    can_run, _ = ci_watch.ci_can_ever_run("a" * 40)
    assert can_run is True


def test_watch_refuses_before_polling_when_ci_can_never_run(monkeypatch):
    calls = {"runs": 0}

    def fake_get(url):
        calls["runs"] += 1
        raise AssertionError("must not call the API when refusing up front")

    monkeypatch.setattr(ci_watch, "_get", fake_get)
    monkeypatch.setattr(
        ci_watch, "ci_can_ever_run",
        lambda sha: (False, "0b6655f is not reachable from origin/main and branch has no open PR"),
    )

    rc = ci_watch.watch("0b6655f38363fd0420223c8b094553e27283151e", wait=True, wait_minutes=40)
    assert rc == ci_watch.EXIT_NEVER_TRIGGERS
    assert calls["runs"] == 0


# ---------------------------------------------------------------------------
# resolve_full_sha: short sha vs full sha (root cause #4).
# ---------------------------------------------------------------------------

def test_resolve_full_sha_rejects_short_result(monkeypatch):
    monkeypatch.setattr(ci_watch, "_git", lambda args: "e041ec1")  # 7 chars
    assert ci_watch.resolve_full_sha("e041ec1") is None


def test_resolve_full_sha_accepts_full_result(monkeypatch):
    full = "e041ec140b91a9df680e13a65a5a5796f1c9270c"
    monkeypatch.setattr(ci_watch, "_git", lambda args: full)
    assert ci_watch.resolve_full_sha("HEAD") == full


def test_main_exits_bad_ref_when_unresolvable(monkeypatch, capsys):
    monkeypatch.setattr(ci_watch, "resolve_full_sha", lambda ref: None)
    rc = ci_watch.main(["--sha", "nope"])
    assert rc == ci_watch.EXIT_BAD_REF
    assert "cannot resolve" in capsys.readouterr().out


@pytest.mark.parametrize("name", list(FIXTURES.glob("*.json")))
def test_every_fixture_is_valid_json(name):
    json.loads(name.read_text(encoding="utf-8"))
