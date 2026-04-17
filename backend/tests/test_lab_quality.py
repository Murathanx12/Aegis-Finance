"""Tests for lab/quality.py — the cycle scorecard + rollback gate."""

import json
import sys
from pathlib import Path

import pytest

LAB = Path(__file__).parent.parent.parent / "lab"
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

from quality import (  # noqa: E402
    CycleMetrics, DEFAULT_WEIGHTS, PASS_THRESHOLD, ROLLBACK_THRESHOLD,
    append_history, read_history, score_cycle, trend_summary,
)


def _metrics(**overrides) -> CycleMetrics:
    m = CycleMetrics(
        tests_passed=1000, tests_failed=0,
        services_total=60, services_healthy=60,
        code_smells_count=100, warnings_count=0,
        frontend_build_ok=True,
    )
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def test_cycle_metrics_rates():
    m = _metrics(tests_passed=80, tests_failed=20)
    assert m.test_pass_rate() == 0.8
    m2 = _metrics(services_total=10, services_healthy=9)
    assert m2.service_health_rate() == 0.9


def test_cycle_metrics_empty_counts_default_to_perfect():
    m = CycleMetrics()
    assert m.test_pass_rate() == 1.0
    assert m.service_health_rate() == 1.0


def test_score_cycle_perfect_stays_perfect():
    before = _metrics()
    after = _metrics()
    sc = score_cycle(before, after)
    assert sc["composite_score"] == 1.0
    assert sc["verdict"] == "pass"
    assert sc["flags"] == []


def test_score_cycle_test_failure_penalizes_tests_component():
    before = _metrics()
    after = _metrics(tests_passed=800, tests_failed=200)
    sc = score_cycle(before, after)
    assert sc["components"]["tests"] == 0.8
    # Other components should still be perfect
    assert sc["components"]["smells"] == 1.0
    assert sc["components"]["health"] == 1.0
    expected = sum(DEFAULT_WEIGHTS[k] * sc["components"][k] for k in DEFAULT_WEIGHTS)
    assert sc["composite_score"] == pytest.approx(round(expected, 3))


def test_score_cycle_smell_increase_penalizes_smells_component():
    before = _metrics(code_smells_count=100)
    after = _metrics(code_smells_count=120)
    sc = score_cycle(before, after)
    # +20 smells drives smells component to 0.0
    assert sc["components"]["smells"] == 0.0


def test_score_cycle_smell_decrease_keeps_full_credit():
    before = _metrics(code_smells_count=100)
    after = _metrics(code_smells_count=95)
    sc = score_cycle(before, after)
    assert sc["components"]["smells"] == 1.0
    assert "+" not in "".join(sc["flags"])


def test_score_cycle_frontend_break_flags_and_penalizes():
    before = _metrics(frontend_build_ok=True)
    after = _metrics(frontend_build_ok=False)
    sc = score_cycle(before, after)
    assert sc["components"]["frontend"] == 0.0
    assert any("frontend build broke" in f for f in sc["flags"])


def test_score_cycle_service_regression_flags():
    before = _metrics(services_total=60, services_healthy=60)
    after = _metrics(services_total=60, services_healthy=55)
    sc = score_cycle(before, after)
    assert sc["components"]["health"] < 1.0
    assert any("services stopped importing" in f for f in sc["flags"])


def test_score_cycle_verdict_bands():
    # Perfect → pass
    assert score_cycle(_metrics(), _metrics())["verdict"] == "pass"

    # Catastrophic regression → rollback
    bad = _metrics(
        tests_passed=200, tests_failed=800,        # test_pass_rate = 0.2
        code_smells_count=150,                     # +50 smells → smells component = 0
        services_total=60, services_healthy=40,    # health = 0.67
        frontend_build_ok=False,                   # frontend = 0
    )
    sc = score_cycle(_metrics(code_smells_count=100), bad)
    assert sc["verdict"] == "rollback"
    assert sc["composite_score"] < ROLLBACK_THRESHOLD

    # Middle ground (moderate regression) → warn but keep
    mid = _metrics(tests_passed=600, tests_failed=400, code_smells_count=115)
    sc = score_cycle(_metrics(code_smells_count=100), mid)
    assert sc["verdict"] == "warn"
    assert ROLLBACK_THRESHOLD <= sc["composite_score"] < PASS_THRESHOLD


def test_history_append_and_read(tmp_path):
    hp = tmp_path / "history.json"
    for c in range(1, 6):
        append_history(hp, {"cycle": c, "composite_score": c / 10, "verdict": "pass"})
    hist = read_history(hp, last_n=3)
    assert len(hist) == 3
    assert [h["cycle"] for h in hist] == [3, 4, 5]


def test_history_rejects_corrupt(tmp_path):
    hp = tmp_path / "bad.json"
    hp.write_text("not json", encoding="utf-8")
    assert read_history(hp) == []
    # append should tolerate corrupted file by starting fresh
    append_history(hp, {"cycle": 1, "composite_score": 0.9, "verdict": "pass"})
    restored = json.loads(hp.read_text())
    assert len(restored) == 1


def test_trend_summary_detects_declining(tmp_path):
    hist = [
        {"cycle": 1, "composite_score": 0.9, "verdict": "pass"},
        {"cycle": 2, "composite_score": 0.85, "verdict": "pass"},
        {"cycle": 3, "composite_score": 0.7, "verdict": "warn"},
        {"cycle": 4, "composite_score": 0.5, "verdict": "rollback"},
    ]
    summary = trend_summary(hist)
    assert summary["available"] is True
    assert summary["declining_trend"] is True
    assert summary["avg_score"] == pytest.approx(0.7375, rel=1e-3)
    assert summary["last_verdicts"] == ["pass", "pass", "warn", "rollback"]


def test_trend_summary_empty():
    assert trend_summary([]) == {"available": False}
