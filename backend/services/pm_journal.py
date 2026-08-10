"""The portfolio memory — why each decision was made, so it can be scored.

The thing a manual Bloomberg workflow cannot do is tell you, three months
later, *which part* of a decision was wrong. Was the stock right and the size
wrong? Was the catalyst right and the timing wrong? Was the analyst right and
the haircut wrong? None of that is answerable unless the reason was written
down at the moment of the decision, in a form a machine can read.

This module is that record. Append-only JSONL, one line per recommendation,
with the state that produced it frozen alongside. Nothing here trades, and
nothing here is allowed to edit a past entry — a journal you can rewrite is a
story, not evidence.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

JOURNAL = Path(__file__).resolve().parents[1] / "data" / "pm_journal.jsonl"

#: The fields of the world that must be frozen with every instruction, so the
#: post-mortem can separate "the signal was wrong" from "the signal was right
#: and we sized it badly".
FREEZE = ("price", "target_median", "target_low", "target_high", "n_analysts",
          "consensus_score", "rating_drift_3m", "net_90d",
          "days_since_last_action", "binary_event_risk", "implied_upside")


def _row(brief: dict, r: dict, rec: dict, note: str) -> dict:
    st = r.get("state") or {}
    ev = st.get("evidence") or {}
    return {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "account": brief.get("account"),
        "positions_confirmed": brief.get("positions_confirmed"),
        # An entry is a RECOMMENDATION. Nothing in this codebase executes, and
        # an unconfirmed book cannot even be read as an executable ticket.
        "actionable": bool(brief.get("actionable")),
        "executed": False,
        "valuation_basis": (brief.get("valuation") or {}).get("basis"),
        "decisionable": st.get("decisionable"),
        "missing_reasons": st.get("missing_reasons"),
        "evidence_completeness": (ev.get("completeness") or {}).get("known_fraction"),
        "reliability_multiplier": (ev.get("reliability") or {}).get("multiplier"),
        "sizing_mode": brief.get("sizing_mode"),
        "ticker": r["ticker"],
        "action": rec["action"],
        "dollars": rec["dollars"],
        "current_weight": rec["current_weight"],
        "target_weight": rec["target_weight"],
        "thesis": r.get("thesis"),
        "kill_condition": r.get("kill_condition"),
        "alpha_score": (r.get("alpha") or {}).get("score"),
        "distribution": r.get("distribution"),
        "state": {k: st.get(k) for k in FREEZE},
        "evidence_grade": "observational — analyst consensus, unvalidated",
        "note": note,
        "resolved": False,
    }


def record_brief(brief: dict, *, note: str = "") -> dict:
    """Freeze every non-HOLD instruction in a brief. Returns what was written.

    An unconfirmed book is still recorded, and is marked as such: the reasoning
    is worth keeping even when the ticket sizes are placeholders. What it is
    NOT allowed to do is claim the trade happened.
    """
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    by_ticker = {r["ticker"]: r for r in brief.get("holdings", [])}
    written = []
    with JOURNAL.open("a", encoding="utf-8") as fh:
        for rec in brief.get("actions", []):
            r = by_ticker.get(rec["ticker"], {"ticker": rec["ticker"]})
            row = _row(brief, r, rec, note)
            fh.write(json.dumps(row, default=str) + "\n")
            written.append(row)
    return {"written": len(written), "path": str(JOURNAL),
            "entries": written,
            "actionable": bool(brief.get("actionable")),
            "caveat": None if brief.get("actionable") else
            "book is not actionable (" +
            "; ".join(brief.get("actionable_blockers") or ["unconfirmed"]) +
            ") — these are recorded as REASONING, never as executable tickets"}


def tail(limit: int = 50) -> list[dict]:
    if not JOURNAL.exists():
        return []
    lines = JOURNAL.read_text(encoding="utf-8").splitlines()
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def summary() -> dict:
    rows = tail(10_000)
    by_action: dict[str, int] = {}
    for r in rows:
        by_action[r.get("action", "?")] = by_action.get(r.get("action", "?"), 0) + 1
    return {"total": len(rows), "by_action": by_action,
            "resolved": sum(1 for r in rows if r.get("resolved")),
            "unresolved": sum(1 for r in rows if not r.get("resolved")),
            "note": "resolution is a separate pass — an entry becomes evidence "
                    "only when its outcome is scored against the thesis"}


def resolve(ticker: str, at_price: float, outcome: str,
            which: str = "thesis") -> dict:
    """Score one open entry. Appends a resolution row; never edits the original.

    `which` names the part being judged — thesis, catalyst, sizing, timing —
    because "it went down" is not a diagnosis.
    """
    row = {"recorded_at": datetime.now().isoformat(timespec="seconds"),
           "kind": "resolution", "ticker": ticker.upper(),
           "at_price": float(at_price), "outcome": outcome, "component": which}
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def last_brief_hash() -> Any:
    rows = tail(1)
    return rows[0].get("recorded_at") if rows else None
