"""CLI for the session budget receipt (Q10): a manager's view of model/worker
allocation per session, DECLARED by the orchestrator and reconciled against
the one paid-API number this repo can actually measure.

    python -m scripts.session_budget open  --session <id> [--date YYYY-MM-DD]
    python -m scripts.session_budget log   --session <id> --task <name> \\
        --worker {fable,opus,sonnet,deepseek,local,deterministic} \\
        --priority 1-7 --ev "<one line>" [--tokens N] [--usd X] [--note "..."]
    python -m scripts.session_budget close --session <id>
    python -m scripts.session_budget status [--session <id>]   # defaults to the open one

Logic lives in `backend/services/session_budget.py`; this is a thin CLI shell.
Exit 0 = ok, 1 = open/status found nothing to report, 2 = a row was REFUSED.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.session_budget import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
