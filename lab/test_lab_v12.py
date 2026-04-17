"""Tests for Lab v12 additions: hypothesis registry, theme selector, robustness probes.

Run from the repo root:
    python -m pytest lab/test_lab_v12.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LAB = Path(__file__).parent
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

import hypotheses  # noqa: E402
import themes  # noqa: E402
import robustness  # noqa: E402


# ── Hypothesis registry ──────────────────────────────────────────────────────


class TestHypothesisRegistry:
    def test_append_and_load(self, tmp_path):
        path = tmp_path / "h.json"
        assert hypotheses.load(path) == []
        hypotheses.append(path, {"cycle": 1, "hypothesis": "x"})
        items = hypotheses.load(path)
        assert len(items) == 1 and items[0]["cycle"] == 1

    def test_max_keep_enforced(self, tmp_path):
        path = tmp_path / "h.json"
        for i in range(10):
            hypotheses.append(path, {"cycle": i, "hypothesis": f"h{i}"}, max_keep=5)
        items = hypotheses.load(path)
        assert len(items) == 5
        assert [e["cycle"] for e in items] == [5, 6, 7, 8, 9]

    def test_record_from_report_success(self, tmp_path):
        path = tmp_path / "h.json"
        entry = hypotheses.record_from_report(
            path,
            cycle=3,
            theme="build",
            report={
                "title": "Add earnings calendar",
                "observation": {"gap_identified": "No earnings visibility"},
                "implementation": {"feature_built": "Finnhub /calendar/earnings wiring"},
                "assessment": {"verdict": "improved", "self_critique": "small scope"},
            },
            scorecard={"composite_score": 0.82, "verdict": "pass"},
            baseline_score=0.78,
        )
        assert entry is not None
        assert entry["verdict"] == "success"
        assert entry["theme"] == "build"
        assert abs(entry["score_delta"] - 0.04) < 1e-6
        assert entry["composite_score"] == 0.82

    def test_record_from_report_failure(self, tmp_path):
        path = tmp_path / "h.json"
        entry = hypotheses.record_from_report(
            path,
            cycle=4,
            theme="build",
            report={"title": "Refactor risk engine"},
            scorecard={"composite_score": 0.4, "verdict": "rollback", "rolled_back": True},
            baseline_score=0.75,
        )
        assert entry["verdict"] == "failure"
        assert entry["rolled_back"] is True
        assert entry["score_delta"] < 0

    def test_record_handles_missing_report(self, tmp_path):
        path = tmp_path / "h.json"
        out = hypotheses.record_from_report(
            path,
            cycle=5,
            theme="audit",
            report=None,
            scorecard={"composite_score": 0.7, "verdict": "warn"},
            baseline_score=0.7,
        )
        assert out is None

    def test_summarise_for_prompt_mixes_success_failure(self, tmp_path):
        path = tmp_path / "h.json"
        hypotheses.append(
            path,
            {"cycle": 1, "theme": "build", "verdict": "success",
             "hypothesis": "add WEI tile", "score_delta": 0.05, "why": "filled global view gap"},
        )
        hypotheses.append(
            path,
            {"cycle": 2, "theme": "audit", "verdict": "failure",
             "hypothesis": "rewrite monte carlo", "score_delta": -0.15,
             "why": "calibration drift worsened", "rolled_back": True},
        )
        text = hypotheses.summarise_for_prompt(path)
        assert "successful hypotheses" in text
        assert "failed hypotheses" in text
        assert "WEI tile" in text
        assert "rewrite monte carlo" in text

    def test_already_attempted_dedup(self, tmp_path):
        path = tmp_path / "h.json"
        hypotheses.append(
            path,
            {"cycle": 1, "hypothesis": "Add FX carry signal",
             "fingerprint": hypotheses._fingerprint("Add FX carry signal")},
        )
        found = hypotheses.already_attempted(path, "add fx carry signal")
        assert found is not None and found["cycle"] == 1
        assert hypotheses.already_attempted(path, "completely different idea") is None


# ── Theme selector ───────────────────────────────────────────────────────────


class TestThemeSelector:
    def test_cold_start_picks_audit(self):
        d = themes.select_theme(cycle=1, scorecard=None, trend=None)
        assert d.theme == "audit"

    def test_frontend_broken_forces_stabilise(self):
        sc = {
            "components": {"tests": 1.0, "health": 1.0, "smells": 1.0},
            "after": {"frontend_build_ok": False, "tests_failed": 0},
            "flags": ["frontend build broke"],
        }
        d = themes.select_theme(cycle=5, scorecard=sc)
        assert d.theme == "stabilise"

    def test_failing_tests_force_stabilise(self):
        sc = {
            "components": {"tests": 0.88, "health": 1.0, "smells": 1.0},
            "after": {"frontend_build_ok": True, "tests_failed": 5},
            "flags": [],
        }
        d = themes.select_theme(cycle=5, scorecard=sc)
        assert d.theme == "stabilise"

    def test_declining_trend_forces_stabilise(self):
        sc = {
            "components": {"tests": 0.95, "health": 1.0, "smells": 1.0},
            "after": {"frontend_build_ok": True, "tests_failed": 0},
            "flags": [],
        }
        d = themes.select_theme(cycle=5, scorecard=sc, trend={"declining_trend": True})
        assert d.theme == "stabilise"

    def test_low_test_rate_picks_quality(self):
        sc = {
            "components": {"tests": 0.85, "health": 1.0, "smells": 1.0},
            "after": {"frontend_build_ok": True, "tests_failed": 2},
            "flags": [],
        }
        d = themes.select_theme(cycle=5, scorecard=sc, trend={})
        assert d.theme == "quality"

    def test_low_health_picks_integrate(self):
        sc = {
            "components": {"tests": 1.0, "health": 0.80, "smells": 1.0},
            "after": {"frontend_build_ok": True, "tests_failed": 0},
            "flags": [],
        }
        d = themes.select_theme(cycle=7, scorecard=sc, trend={})
        assert d.theme == "integrate"

    def test_healthy_rotates_discovery(self):
        sc = {
            "components": {"tests": 1.0, "health": 1.0, "smells": 1.0},
            "after": {"frontend_build_ok": True, "tests_failed": 0},
            "flags": [],
        }
        d1 = themes.select_theme(cycle=10, scorecard=sc, trend={}, last_themes=["build"])
        d2 = themes.select_theme(cycle=11, scorecard=sc, trend={}, last_themes=["audit"])
        # Both should be valid discovery themes but not repeat the previous one
        assert d1.theme in {"audit", "robustness", "integrate", "performance"}
        assert d2.theme != "audit"

    def test_instructions_for_every_theme(self):
        for t in themes.THEMES:
            block = themes.instructions_for(t)
            assert t.upper() in block


# ── Robustness probes ────────────────────────────────────────────────────────


class TestRobustness:
    def test_run_all_returns_shape(self):
        report = robustness.run_all()
        assert set(report.keys()) == {"score", "passed", "total", "probes"}
        assert 0.0 <= report["score"] <= 1.0
        assert report["total"] == len(robustness.PROBES)
        for p in report["probes"]:
            assert {"name", "ok", "detail"} <= p.keys()

    def test_summary_line_contains_score(self):
        report = robustness.run_all()
        line = robustness.summary_line(report)
        assert "Robustness:" in line
        assert "/" in line  # "5/5" format

    def test_single_asset_optimizer_passes(self):
        """The single-asset-optimizer probe specifically must be OK — anything
        else here would mean our MPC wrapper broke on a trivial input."""
        name, ok, detail = robustness._probe_single_asset_optimizer()
        assert ok, f"single-asset optimizer probe failed: {detail}"

    def test_crash_timeline_monotone_passes(self):
        name, ok, detail = robustness._probe_crash_timeline_monotone()
        assert ok, f"crash timeline monotonicity failed: {detail}"
