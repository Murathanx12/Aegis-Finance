"""
Lab v12 — Theme-driven cycle selection
========================================

Replaces the naive DEEP_AUDIT → BUILD → INTEGRATE rotation with a
metric-driven selector. Each cycle picks the theme that addresses the
weakest part of the engine, so the loop puts effort where it moves the
composite score fastest.

Selection logic:
  1. Hard-override on emergencies (failing tests, red frontend, severe
     declines) — always pick `stabilise`.
  2. Otherwise pick the theme whose target component has the lowest
     current value (normalised), breaking ties with a deterministic
     rotation seeded by cycle number so the loop doesn't fixate.

The themes are intentionally richer than the old 3-way rotation:
  - stabilise      : fix failing tests, restore dead services
  - quality        : reduce code smells, improve test coverage
  - integrate      : wire existing services into user-facing endpoints
  - build          : add a new institutional capability
  - audit          : read code, find bugs, write regression tests
  - robustness     : edge cases (flat vol, extreme markets, single-ticker)
  - performance    : profile + tighten hot paths
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


THEMES = [
    "stabilise",
    "quality",
    "integrate",
    "build",
    "audit",
    "robustness",
    "performance",
]


@dataclass
class ThemeDecision:
    theme: str
    reason: str
    component_scores: dict


def _norm(score: float) -> float:
    return max(0.0, min(1.0, score))


def select_theme(
    *,
    cycle: int,
    scorecard: Optional[dict] = None,
    trend: Optional[dict] = None,
    last_themes: list[str] | None = None,
) -> ThemeDecision:
    """Pick a theme from the current quality scorecard + trend.

    `scorecard` is the last cycle's quality scorecard (or None if first).
    `trend` is the output of quality.trend_summary(...).
    `last_themes` is the list of recent themes — we de-prioritise repeats.
    """
    last_themes = last_themes or []
    if not scorecard:
        # Cold start — begin with an audit to establish baseline
        return ThemeDecision(
            theme="audit",
            reason="cold start — no prior scorecard",
            component_scores={},
        )

    comps = dict(scorecard.get("components") or {})
    flags = scorecard.get("flags") or []

    # 1. Hard overrides
    if not scorecard.get("after", {}).get("frontend_build_ok", True):
        return ThemeDecision("stabilise", "frontend build broken", comps)
    if "frontend build broke" in flags:
        return ThemeDecision("stabilise", "frontend broke", comps)
    after = scorecard.get("after") or {}
    if after.get("tests_failed", 0) >= 3:
        return ThemeDecision(
            "stabilise",
            f"{after.get('tests_failed')} failing tests",
            comps,
        )
    if trend and trend.get("declining_trend"):
        return ThemeDecision(
            "stabilise",
            "rolling score has declined 3+ cycles — tighten up",
            comps,
        )

    # 2. Data-driven selection — weakest component drives the theme
    tests_part = _norm(comps.get("tests", 1.0))
    health_part = _norm(comps.get("health", 1.0))
    smells_part = _norm(comps.get("smells", 1.0))

    target: Optional[tuple[str, str, float]] = None
    if tests_part < 0.90:
        target = (
            "quality",
            f"test pass rate {tests_part:.2f} below 0.90 — add tests / fix regressions",
            tests_part,
        )
    elif health_part < 0.95:
        target = (
            "integrate",
            f"service health {health_part:.2f} — wire/fix modules that don't import",
            health_part,
        )
    elif smells_part < 0.90:
        target = (
            "quality",
            f"code-smell budget tight ({smells_part:.2f}) — clean up broad except / fillna",
            smells_part,
        )

    if target is None:
        # Healthy engine — rotate across discovery themes, avoiding immediate
        # repetition so we don't loop on the same area.
        rotation = ["build", "audit", "robustness", "integrate", "performance"]
        for offset in range(len(rotation)):
            candidate = rotation[(cycle + offset) % len(rotation)]
            if not last_themes or last_themes[-1] != candidate:
                target = (
                    candidate,
                    "engine healthy — rotating discovery themes",
                    1.0,
                )
                break

    theme, reason, _ = target  # type: ignore[misc]
    return ThemeDecision(theme=theme, reason=reason, component_scores=comps)


# ── Theme → instruction block used inside the prompt ─────────────────────────


THEME_INSTRUCTIONS: dict[str, str] = {
    "stabilise": """
## Theme: STABILISE
Focus exclusively on restoring tests and service health. Do NOT add features
this cycle. Identify and fix every failing test; re-import every dead service;
unbreak the frontend build.
""",
    "quality": """
## Theme: QUALITY
Improve test coverage or reduce code smells. Pick 3-5 services without
tests (or with thin tests) and write proper ones. Replace `except Exception`
with narrow exception classes where you can. No feature work.
""",
    "integrate": """
## Theme: INTEGRATE
Find services that exist but are not wired into any router endpoint, and
fix that. The goal is: a user calling /api/stock/{ticker} or
/api/portfolio/analyze should see every relevant new signal.
""",
    "build": """
## Theme: BUILD
Add a substantial new institutional capability. Check the hypothesis
ledger below first — do not re-attempt something that failed unless the
approach is materially different. Full service + tests + endpoint +
frontend client entry.
""",
    "audit": """
## Theme: AUDIT
Read code line-by-line to find bugs. For each: write a regression test
first, then fix. Target at least 3 real bugs (not style issues).
""",
    "robustness": """
## Theme: ROBUSTNESS
Stress the engine against edge cases: flat-vol markets, single-asset
portfolios, missing data, extreme shocks. Add probes and assertions that
catch silent failures. Don't invent features — fortify existing ones.
""",
    "performance": """
## Theme: PERFORMANCE
Profile hot paths. Measure — don't guess. Target: the slowest endpoint
and the slowest test. Document baseline ms/call before and after.
""",
}


def instructions_for(theme: str) -> str:
    return THEME_INSTRUCTIONS.get(theme, "")
