"""
Lab v12 — Hypothesis registry
===============================

Records every cycle's hypothesis, implementation summary, and verdict in
a single JSON ledger (`lab/hypotheses.json`). The rd_loop injects past
successes/failures into the next prompt so Claude stops repeating the
same failed ideas.

A hypothesis entry looks like:

    {
      "cycle": 7,
      "timestamp": "2026-04-17T03:30:00",
      "theme": "calibration",
      "hypothesis": "Blending ATM IV into GARCH vol reduces MC drift",
      "approach": "extract atm_iv from options_intelligence, weighted-blend 0.35 IV / 0.65 GARCH",
      "verdict": "success | failure | inconclusive",
      "score_delta": 0.04,
      "why": "drift dropped 15.5% → 14.3%; bounded by iv_blend_weight=0.35"
    }

The loop derives `hypothesis` + `approach` from Claude's experiment_report
(so Claude's own narrative becomes durable memory).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append(path: Path, entry: dict, max_keep: int = 200) -> None:
    items = load(path)
    items.append(entry)
    items = items[-max_keep:]
    path.write_text(json.dumps(items, indent=2, default=str), encoding="utf-8")


def _fingerprint(hypothesis: str) -> str:
    """Cheap lowercase-alpha fingerprint for dedup / similarity."""
    import re

    return re.sub(r"[^a-z0-9]+", " ", (hypothesis or "").lower()).strip()


def record_from_report(
    path: Path,
    *,
    cycle: int,
    theme: str,
    report: dict | None,
    scorecard: dict,
    baseline_score: Optional[float],
) -> Optional[dict]:
    """Extract a hypothesis record from a cycle's experiment_report + scorecard.

    Returns the appended entry, or None if report didn't define a hypothesis.
    """
    if not isinstance(report, dict):
        return None

    assessment = report.get("assessment") or {}
    impl = report.get("implementation") or {}
    obs = report.get("observation") or {}

    hypothesis_text = (
        report.get("hypothesis")
        or obs.get("gap_identified")
        or report.get("title")
        or ""
    )
    if not hypothesis_text:
        return None

    approach_text = (
        report.get("approach")
        or impl.get("feature_built")
        or impl.get("bugs_fixed")
        or impl.get("files_changed")
        or ""
    )
    if isinstance(approach_text, list):
        approach_text = "; ".join(str(x) for x in approach_text[:4])

    score = scorecard.get("composite_score", 0.0)
    score_delta = None
    if baseline_score is not None:
        score_delta = round(score - baseline_score, 4)

    verdict = scorecard.get("verdict", "warn")
    # Normalise scorecard verdict → hypothesis verdict
    hv = {
        "pass": "success",
        "warn": "inconclusive",
        "rollback": "failure",
    }.get(verdict, "inconclusive")

    why_text = (
        assessment.get("self_critique")
        or assessment.get("limitations")
        or (f"score {score:.3f}" + (f" (Δ{score_delta:+.3f})" if score_delta is not None else ""))
    )
    if isinstance(why_text, list):
        why_text = "; ".join(str(x) for x in why_text[:4])

    entry = {
        "cycle": cycle,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "theme": theme,
        "hypothesis": hypothesis_text[:240],
        "approach": str(approach_text)[:240],
        "verdict": hv,
        "composite_score": round(float(score), 3),
        "score_delta": score_delta,
        "why": str(why_text)[:280],
        "fingerprint": _fingerprint(hypothesis_text),
        "files_changed_count": len(impl.get("files_changed", []) or []),
        "files_created_count": len(impl.get("files_created", []) or []),
        "packages_installed": impl.get("packages_installed") or [],
        "rolled_back": scorecard.get("rolled_back", False),
    }
    append(path, entry)
    return entry


def summarise_for_prompt(path: Path, *, max_successes: int = 5, max_failures: int = 5) -> str:
    """Format a short block for injection into the next cycle's prompt."""
    items = load(path)
    if not items:
        return "No prior hypotheses on file."

    successes = [e for e in items if e.get("verdict") == "success"]
    failures = [e for e in items if e.get("verdict") == "failure"]

    lines: list[str] = []
    if successes:
        lines.append("### Past successful hypotheses (repeat patterns, not ideas)")
        for e in successes[-max_successes:]:
            lines.append(
                f"- cycle {e['cycle']} [{e.get('theme','?')}]: "
                f"{e['hypothesis']} → Δscore {_fmt_delta(e.get('score_delta'))}"
            )
            if e.get("why"):
                lines.append(f"    · why it worked: {e['why'][:180]}")

    if failures:
        lines.append("")
        lines.append("### Past failed hypotheses (DO NOT re-attempt without changing the approach)")
        for e in failures[-max_failures:]:
            lines.append(
                f"- cycle {e['cycle']} [{e.get('theme','?')}]: "
                f"{e['hypothesis']} (rolled_back={e.get('rolled_back', False)})"
            )
            if e.get("why"):
                lines.append(f"    · why it failed: {e['why'][:180]}")

    return "\n".join(lines)


def already_attempted(path: Path, hypothesis_text: str) -> Optional[dict]:
    """Return the most recent matching entry, or None."""
    fp = _fingerprint(hypothesis_text)
    if not fp:
        return None
    items = load(path)
    for e in reversed(items):
        if e.get("fingerprint") == fp:
            return e
    return None


def _fmt_delta(v: Optional[float]) -> str:
    if v is None:
        return "?"
    return f"{v:+.3f}"
