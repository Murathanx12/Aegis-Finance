"""
Lab — canonical findings loader (the trial-densified brain layer).

`docs/KNOWLEDGE/findings.jsonl` is the curated, machine-readable distillation
of everything the project has MEASURED: every registry trial verdict,
NEGATIVE_RESULTS entry, canon constraint, and paid-for process lesson —
one JSON object per line. This module loads it and renders the block the
rd_loop injects into every cycle prompt (alongside the per-cycle hypothesis
memory in hypotheses.py), so autonomous sessions inherit the project's
accumulated knowledge instead of re-proposing refuted ideas.

Curation rule: entries are added when a trial CONCLUDES or a postmortem
lands — hand-distilled, reviewed in the same commit as the evidence. This is
deliberately NOT auto-generated: the distillation (what the result MEANS for
the next hypothesis) is the value.
"""

from __future__ import annotations

import json
from pathlib import Path

FINDINGS_PATH = Path(__file__).resolve().parent.parent / "docs" / "KNOWLEDGE" / "findings.jsonl"

_KIND_ORDER = ["constraint", "negative", "process", "positive", "accruing"]


def load(path: Path = FINDINGS_PATH) -> list[dict]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("finding"):
                items.append(obj)
        except json.JSONDecodeError:
            continue  # one bad line must not poison the ledger
    return items


def summarise_for_prompt(path: Path = FINDINGS_PATH, max_entries: int = 25) -> str:
    """Render the findings block for cycle prompts: constraints and negative
    results first (they gate what may be proposed), newest first within kind."""
    items = load(path)
    if not items:
        return ""
    items.sort(key=lambda f: (
        _KIND_ORDER.index(f.get("kind")) if f.get("kind") in _KIND_ORDER else 99,
        f.get("date", ""),
    ))
    lines = [
        "## Canonical findings (measured — do not re-litigate; violations waste the cycle)",
        "",
    ]
    for f in items[:max_entries]:
        kind = (f.get("kind") or "?").upper()
        lesson = f.get("lesson") or ""
        lines.append(f"- [{kind} {f.get('id', '?')} {f.get('date', '')}] "
                     f"{f.get('finding', '')} LESSON: {lesson}")
    lines.append("")
    lines.append("Full ledger: docs/KNOWLEDGE/findings.jsonl (evidence refs inside).")
    return "\n".join(lines)
