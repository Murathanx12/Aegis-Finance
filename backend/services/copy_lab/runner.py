"""One scheduled engine pass over the seeded, active COPY-LAB lanes.

Extracted from `scripts/copy_lab_run.py` (2026-08-20) so the scheduler can
call the same logic the script does. Found during the ORDER-25 audit: the
lanes were seeded 2026-08-14 and the engine had run exactly ONCE, because the
only driver was a script nobody scheduled — six days of a seeded lane doing
nothing while looking green. Seeding stays attended and script-only; THIS
function only advances lanes that were already seeded.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from backend.services.copy_lab import engine as E
from backend.services.copy_lab import lanes as L
from backend.services.copy_lab import store as S
from backend.services.copy_lab.prices import YFinancePanel
from backend.services.teacher_library import ledger as TL

logger = logging.getLogger(__name__)


def run_active_lanes(as_of: str | None = None,
                     lookback_days: int = 180) -> list[dict]:
    """Engine pass for every active+seeded lane. Returns one receipt each."""
    lanes = {k: v for k, v in L.load_lanes().items()
             if v.active and S.is_seeded(k)}
    if not lanes:
        logger.info("COPY-LAB: no seeded active lane — nothing to run")
        return []

    as_of_d = date.fromisoformat(as_of) if as_of else date.today()
    receipts = []
    for name, spec in lanes.items():
        try:
            seed_rec = S.read_seed(name) or {}
            events = TL.events_asof(f"{as_of_d}T23:59:59+00:00",
                                    actor_types=([spec.actor_type]
                                                 if spec.actor_type else None))
            events = [e for e in events
                      if not spec.action_types
                      or e.action_type in spec.action_types]
            tickers = sorted({(e.ticker_at_event or "").upper() for e in events
                              if e.ticker_at_event})
            start = str(min(date.fromisoformat(str(seed_rec["seeded_at"])[:10]),
                            as_of_d) - timedelta(days=lookback_days))
            prices = YFinancePanel(tickers, start=start,
                                   benchmark=spec.benchmark)
            r = E.run_lane(spec, prices=prices, events=events, as_of=as_of_d)
            receipts.append(r)
            logger.info("COPY-LAB %s: events=%s new_signals=%s fills=%s "
                        "open=%s nav=%s", name, r.get("events_considered"),
                        r.get("signals_new"), r.get("fills"),
                        r.get("open_positions"), r.get("nav"))
        except Exception as exc:  # noqa: BLE001 — one lane never kills the rest
            logger.exception("COPY-LAB %s: engine pass failed", name)
            receipts.append({"lane_id": name, "status": "error",
                             "error": f"{type(exc).__name__}: {exc}"})
    return receipts
