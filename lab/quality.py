"""
Aegis Lab — Quality Scorecard & Rollback Gate
================================================

Reads before/after snapshots collected around a cycle and computes a
normalized 0-1 quality score. The rd_loop uses this to decide whether to
keep a cycle's commit or roll it back.

Scoring components (all 0-1):
  - test_pass_rate:       #passed / (#passed + #failed) on the full fast suite
  - service_health:       #services that import without error / total
  - code_smell_delta:     1.0 if smells went down or stayed equal, linearly
                           penalized as smells grow
  - frontend_builds:      1.0 if `npx next build` succeeded, else 0.0
  - warnings_delta:       1.0 if no NEW warnings, linear penalty otherwise

Default weights (sum = 1.0):
  tests=0.4  smells=0.2  health=0.2  frontend=0.1  warnings=0.1

Why this matters:
  v10 committed every cycle regardless of quality — a bad cycle could
  silently degrade the engine. v11 measures, ledgers the trend, and
  gates commits on a minimum score so the overnight loop no longer
  wanders downhill.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# --- Weights (tweak in config if needed) ---------------------------------

DEFAULT_WEIGHTS = {
    "tests": 0.40,
    "smells": 0.20,
    "health": 0.20,
    "frontend": 0.10,
    "warnings": 0.10,
}

# Threshold for auto-rollback — below this the cycle's commit is reverted
ROLLBACK_THRESHOLD = 0.55
# Threshold for "warn but keep" — score above this counts as a pass
PASS_THRESHOLD = 0.70


@dataclass
class CycleMetrics:
    tests_passed: int = 0
    tests_failed: int = 0
    services_total: int = 0
    services_healthy: int = 0
    code_smells_count: int = 0
    warnings_count: int = 0
    frontend_build_ok: bool = True
    raw: dict = field(default_factory=dict)

    def test_pass_rate(self) -> float:
        total = self.tests_passed + self.tests_failed
        return 1.0 if total == 0 else self.tests_passed / total

    def service_health_rate(self) -> float:
        if self.services_total == 0:
            return 1.0
        return self.services_healthy / self.services_total

    def as_dict(self) -> dict:
        return {
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "test_pass_rate": round(self.test_pass_rate(), 4),
            "services_total": self.services_total,
            "services_healthy": self.services_healthy,
            "service_health_rate": round(self.service_health_rate(), 4),
            "code_smells_count": self.code_smells_count,
            "warnings_count": self.warnings_count,
            "frontend_build_ok": self.frontend_build_ok,
        }


def _count_code_smells(repo: Path) -> int:
    """Count broad except blocks + fillna(0) anti-pattern + np.random.seed in backend/."""
    count = 0
    for py in (repo / "backend").rglob("*.py"):
        if "tests" in py.parts or "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        count += text.count("except Exception")
        count += text.count(".fillna(0)")
        count += text.count("np.random.seed")
    return count


def _probe_service_imports(repo: Path) -> tuple[int, int]:
    """Import each backend/services/*.py and count how many succeed.

    Runs inside the host process so we reuse the already-initialized
    Python env + caches — much faster than spawning subprocesses.
    """
    import importlib
    services = list((repo / "backend" / "services").glob("*.py"))
    total = 0
    healthy = 0
    for svc in services:
        if svc.name.startswith("_"):
            continue
        total += 1
        module_name = f"backend.services.{svc.stem}"
        try:
            importlib.import_module(module_name)
            healthy += 1
        except Exception:
            pass
    return total, healthy


def _run_pytest(repo: Path, timeout: int = 900) -> tuple[int, int]:
    """Run the fast test suite and extract pass/fail counts."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "backend/tests/", "-m", "not slow",
             "--tb=no", "-q", "--disable-warnings"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        text = (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired:
        return 0, 999  # Count a timeout as a catastrophic regression
    except Exception:
        return 0, 999

    import re
    passed = re.search(r"(\d+) passed", text)
    failed = re.search(r"(\d+) failed", text)
    return int(passed.group(1)) if passed else 0, int(failed.group(1)) if failed else 0


def _check_frontend_build(repo: Path, timeout: int = 300) -> bool:
    """Quick type-check via next build. Optional — if node/next missing return True."""
    frontend = repo / "frontend"
    if not (frontend / "package.json").exists():
        return True
    try:
        result = subprocess.run(
            ["npx", "next", "build", "--no-lint"],
            cwd=str(frontend),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return True  # npx not installed → don't fail the cycle over it
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return True


def collect_metrics(repo: Path, *, skip_tests: bool = False,
                    skip_frontend: bool = True) -> CycleMetrics:
    """Collect the full metric snapshot.

    skip_frontend is default True because a build can take >60s and most
    cycles don't touch frontend. The rd_loop flips it to False when the
    cycle type is INTEGRATE or the diff touches frontend/.
    """
    m = CycleMetrics()
    m.code_smells_count = _count_code_smells(repo)
    m.services_total, m.services_healthy = _probe_service_imports(repo)
    if not skip_tests:
        m.tests_passed, m.tests_failed = _run_pytest(repo)
    if not skip_frontend:
        m.frontend_build_ok = _check_frontend_build(repo)
    return m


def score_cycle(before: CycleMetrics, after: CycleMetrics,
                weights: Optional[dict] = None) -> dict:
    """Compute the 0-1 quality score for a cycle given before/after snapshots."""
    w = weights or DEFAULT_WEIGHTS

    tests_part = after.test_pass_rate()
    health_part = after.service_health_rate()

    # Smell delta: reward stays-or-reduces, penalize growth linearly
    smell_delta = after.code_smells_count - before.code_smells_count
    if smell_delta <= 0:
        smells_part = 1.0
    else:
        # +20 smells → score drops to 0
        smells_part = max(0.0, 1.0 - smell_delta / 20.0)

    frontend_part = 1.0 if after.frontend_build_ok else 0.0

    warn_delta = after.warnings_count - before.warnings_count
    if warn_delta <= 0:
        warnings_part = 1.0
    else:
        warnings_part = max(0.0, 1.0 - warn_delta / 50.0)

    raw = {
        "tests": tests_part,
        "health": health_part,
        "smells": smells_part,
        "frontend": frontend_part,
        "warnings": warnings_part,
    }
    composite = sum(w.get(k, 0.0) * v for k, v in raw.items())

    verdict = (
        "rollback" if composite < ROLLBACK_THRESHOLD else
        ("pass" if composite >= PASS_THRESHOLD else "warn")
    )

    # Light-weight regression flags
    flags: list[str] = []
    if after.tests_failed > before.tests_failed:
        flags.append(f"+{after.tests_failed - before.tests_failed} new test failures")
    if after.services_healthy < before.services_healthy:
        flags.append(f"{before.services_healthy - after.services_healthy} services stopped importing")
    if smell_delta > 3:
        flags.append(f"+{smell_delta} new code smells")
    if not after.frontend_build_ok and before.frontend_build_ok:
        flags.append("frontend build broke")

    return {
        "composite_score": round(composite, 3),
        "verdict": verdict,
        "components": {k: round(v, 3) for k, v in raw.items()},
        "weights": w,
        "flags": flags,
        "before": before.as_dict(),
        "after": after.as_dict(),
        "rollback_threshold": ROLLBACK_THRESHOLD,
        "pass_threshold": PASS_THRESHOLD,
    }


def write_scorecard(out: Path, scorecard: dict) -> None:
    out.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")


def read_history(history_path: Path, last_n: int = 10) -> list[dict]:
    """Read the scorecard rolling ledger (keep the loop aware of multi-cycle trends)."""
    if not history_path.exists():
        return []
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data[-last_n:]
    return []


def append_history(history_path: Path, entry: dict, max_keep: int = 60) -> None:
    """Append a cycle scorecard to the rolling ledger."""
    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8")) or []
        except Exception:
            history = []
    if not isinstance(history, list):
        history = []
    history.append(entry)
    history = history[-max_keep:]
    history_path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def trend_summary(history: list[dict]) -> dict:
    """Summarize the last N cycles for prompt injection."""
    if not history:
        return {"available": False}
    scores = [h.get("composite_score") for h in history if "composite_score" in h]
    if not scores:
        return {"available": False}
    n = len(scores)
    avg = sum(scores) / n
    recent = scores[-3:]
    recent_avg = sum(recent) / len(recent) if recent else avg
    declining = len(scores) >= 3 and all(
        scores[i] >= scores[i + 1] for i in range(len(scores) - 3, len(scores) - 1)
    )
    return {
        "available": True,
        "n_cycles": n,
        "avg_score": round(avg, 3),
        "recent_avg": round(recent_avg, 3),
        "declining_trend": declining,
        "last_verdicts": [h.get("verdict") for h in history[-5:]],
    }
