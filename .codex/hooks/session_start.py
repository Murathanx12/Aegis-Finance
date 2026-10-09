"""Wrap the shared Aegis session state in Codex's SessionStart output shape."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def context(state_builder=None) -> str:
    try:
        if state_builder is None:
            sys.path.insert(0, str(REPO))
            from scripts.session_state import build_state

            state_builder = build_state
        state = dict(state_builder())
        # The shared Claude builder sorts pointers by filesystem mtime. Keep
        # that source intact, but use the maintained index for Codex navigation.
        if "docs" in state:
            state["docs"] = {
                "index": "docs/INDEX.md",
                "codex_workflow": "docs/CODEX_OPERATING_MODEL.md",
                "note": "Read the active pointers in INDEX; checkout mtime is not freshness.",
            }
        return "Aegis session state (machine-derived):\n" + json.dumps(state, indent=1, default=str)
    except Exception as exc:  # A failed probe must be visible to the session.
        return f"Aegis session state unavailable: {type(exc).__name__}: {exc}"


def main() -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context(),
    }}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
