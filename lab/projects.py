"""
Lab — project ledger loader (the "what have we looked at" layer).

`docs/KNOWLEDGE/projects.jsonl` is the machine-readable ledger of every
external project, library, firm, and data source the project has EXAMINED —
absorbed, partially absorbed, rejected (with why), or still unmined. It is
the sibling of findings.jsonl: findings record what we MEASURED, this
records what we MINED. This module renders the block rd_loop injects into
every cycle prompt so autonomous sessions inherit "we already looked at X,
took Y, rejected Z" and the search TERMINATES instead of re-sweeping.

Curation rule (CANON §11): every project examined gets its entry in the
same commit as the work that examined it. Rejects are the most valuable
entries — they are what stop the re-examination loop.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECTS_PATH = Path(__file__).resolve().parent.parent / "docs" / "KNOWLEDGE" / "projects.jsonl"

# Rejections first (they gate what may be proposed), then the mining queue,
# then what is already taken (least useful to repeat).
_VERDICT_ORDER = ["rejected", "unmined", "partially-absorbed", "absorbed"]


def load(path: Path = PROJECTS_PATH) -> list[dict]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("name") and obj.get("verdict"):
                items.append(obj)
        except json.JSONDecodeError:
            continue  # one bad line must not poison the ledger
    return items


def summarise_for_prompt(path: Path = PROJECTS_PATH, max_entries: int = 40) -> str:
    """Render the project-ledger block for cycle prompts: rejected first
    (never re-examine), then unmined (the sanctioned mining queue)."""
    items = load(path)
    if not items:
        return ""
    items.sort(key=lambda p: (
        _VERDICT_ORDER.index(p.get("verdict")) if p.get("verdict") in _VERDICT_ORDER else 99,
        p.get("date_examined") or "",
    ))
    lines = [
        "## Project ledger (already examined — do NOT re-research; "
        "rejects are closed, unmined items are the only sanctioned queue)",
        "",
    ]
    for p in items[:max_entries]:
        verdict = (p.get("verdict") or "?").upper()
        detail = ""
        if p.get("verdict") == "rejected" and p.get("what_we_rejected"):
            detail = f" REJECTED-WHY: {p['what_we_rejected']}"
        elif p.get("verdict") == "unmined" and p.get("still_unmined"):
            detail = f" UNMINED: {p['still_unmined']}"
        elif p.get("what_we_took"):
            detail = f" TOOK: {p['what_we_took']}"
        lines.append(f"- [{verdict}] {p.get('name', '?')} ({p.get('category', '?')})"
                     f"{detail}")
    lines.append("")
    lines.append("Full ledger: docs/KNOWLEDGE/projects.jsonl (urls, licenses, "
                 "file pointers inside). New examinations MUST add an entry "
                 "in the same commit (CANON §11).")
    return "\n".join(lines)
