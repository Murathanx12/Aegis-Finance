"""Start the calibration clock: the first live PredictionRecords.

Forward calibration accrues from the first written record and from no earlier
date, so this runs tonight regardless of what the rest of the night concludes.
Every night without records is a night of calibration that cannot be recovered.

The candidate set is deliberately Murat's own names plus the MIRROR book: they
are the securities the programme will be asked about, they span exactly the
categories his process covered, and several are the binary-catalyst objects the
external reviews correctly said the machinery could not evaluate.

    python scripts/run_optimus_specialists.py [--dry-run]

Writes backend/data/optimus/predictions.jsonl and beliefs.jsonl (append-only),
plus a run receipt under docs/optimus/.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.services.belief_state import (append, append_belief, calibration,
                                           read_predictions)
from backend.services.conviction_prices import load_prices, price_on
from backend.services.conviction_sheets import load_sheet
from backend.services.optimus_specialists import (SPECIALISTS,
                                                  effective_distinct_ideas,
                                                  run_specialist)

logger = logging.getLogger(__name__)
RECEIPTS = ROOT / "docs" / "optimus"

#: Which specialist owns which name. Assigned here rather than by the LLM: a
#: model that chooses its own category can always claim the one it did best in.
ROUTING = {
    "biotech": ["NTLA", "BHVN", "ALMS", "AARD", "ABSI", "CRSP", "BEAM"],
    "semis_compute": ["MRVL", "AMPX", "RGTI", "QUBT", "TSM", "MU", "NVDA"],
    "energy_materials": ["SOC", "FSLR", "SLDP", "MP", "AMSC", "BE"],
    "software_consumer": ["DKNG", "PRCH", "ELF", "HUBS", "TTWO"],
}
#: The skeptic sees the whole set — its value is disagreement, and a skeptic
#: given a different universe cannot disagree with anyone.
SKEPTIC_SAMPLE = ["QUBT", "SOC", "NTLA", "RGTI", "ALMS", "MSTR"]


def _load_env() -> None:
    """Keys are env-only. This reads the local .env into the process only."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^([A-Z0-9_]+)\s*=\s*(.*)$", line.strip())
        if m and m.group(1) not in os.environ:
            val = m.group(2).split("#", 1)[0].strip().strip('"').strip("'")
            if val:
                os.environ[m.group(1)] = val


def snapshot_for(tickers: list[str]) -> list[dict]:
    """The frozen input the specialists see, hashed into every record.

    Deliberately thin: last price, his recorded analyst target and consensus,
    and 3/6-month trailing return. A specialist handed a rich derived feature set
    is being told the answer; a specialist handed the raw situation is being
    asked a question.
    """
    prices = load_prices()
    sheet = load_sheet("2026-01-13")
    by_tkr = {h.ticker: h for h in sheet.holdings}
    today = str(prices.index.max().date())
    out = []
    for t in tickers:
        px = price_on(prices, t, today)
        if px is None:
            logger.warning("%s: no price — excluded from the candidate set", t)
            continue
        h = by_tkr.get(t)
        s = prices[t].dropna()
        r3 = (float(px / s.iloc[-63] - 1) if len(s) > 63 else None)
        r6 = (float(px / s.iloc[-126] - 1) if len(s) > 126 else None)
        out.append({
            "ticker": t, "as_of": today, "price": round(px, 4),
            "analyst_target_12m": h.analyst_target if h else None,
            "consensus_rating": h.consensus_rating if h else None,
            "trailing_3m_return": round(r3, 4) if r3 is not None else None,
            "trailing_6m_return": round(r6, 4) if r6 is not None else None,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="build prompts and snapshots, call nothing, write nothing")
    ap.add_argument("--only", nargs="*", default=None,
                    help="run only these specialists (e.g. after a prompt fix "
                         "that lost one specialist's forecasts to a refusal)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    _load_env()
    t0 = time.time()

    plan = {k: v for k, v in ROUTING.items()}
    plan["skeptic"] = SKEPTIC_SAMPLE
    if args.only:
        plan = {k: v for k, v in plan.items() if k in set(args.only)}
        if not plan:
            raise SystemExit(f"--only {args.only} matched no specialist")
    receipt: dict = {
        "run": "OPTIMUS-SPECIALISTS-1",
        "date": str(date.today()),
        "provider": "deepseek",
        "why_deepseek": ("ANTHROPIC_API_KEY is still empty — the .env line "
                         "carries a trailing comment, not a key, which is why "
                         "a length check called it present. Verified by "
                         "attempting a live call, not by measuring a string."),
        "firewall": ("specialists propose and forecast; they never size, weight "
                     "or allocate. Recommendation language is refused at parse "
                     "time, not asked for politely."),
        "batches": [], "totals": {},
    }

    if args.dry_run:
        for name, tickers in plan.items():
            snap = snapshot_for(tickers)
            logger.info("%-18s %d candidates: %s", name, len(snap),
                        [c["ticker"] for c in snap])
        logger.info("dry run: no calls made, nothing written")
        return 0

    all_preds, all_beliefs = [], []
    for name, tickers in plan.items():
        snap = snapshot_for(tickers)
        if not snap:
            logger.warning("%s: empty candidate set — skipped", name)
            continue
        try:
            batch = run_specialist(name, snap)
        except Exception as exc:                        # noqa: BLE001
            logger.error("%s FAILED: %s %s", name, type(exc).__name__, exc)
            receipt["batches"].append({"specialist": name, "error":
                                       f"{type(exc).__name__}: {exc}"})
            continue
        eff = effective_distinct_ideas(batch.predictions)
        receipt["batches"].append({
            "specialist": name, "model": batch.model,
            "model_version": batch.model_version,
            "prompt_hash": batch.prompt_hash,
            "n_candidates": len(snap),
            "n_predictions": len(batch.predictions),
            "n_refused": len(batch.refusals), "refusals": batch.refusals,
            "canon_20_batch_check": eff,
        })
        logger.info("%-18s %2d predictions, %d refused, effective distinct "
                    "ideas %s/%s", name, len(batch.predictions),
                    len(batch.refusals), eff["effective_distinct_ideas"],
                    eff["n_forecasts"])
        all_preds.extend(batch.predictions)
        all_beliefs.extend(batch.beliefs)

    if all_preds:
        append(all_preds)
    if all_beliefs:
        append_belief(all_beliefs)

    across = effective_distinct_ideas(all_preds)
    receipt["totals"] = {
        "n_predictions_written": len(all_preds),
        "n_beliefs_written": len(all_beliefs),
        "canon_20_across_all_specialists": across,
        "ledger_size": len(read_predictions()),
        "calibration_now": calibration(),
        "runtime_secs": round(time.time() - t0, 1),
    }
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    (RECEIPTS / f"specialists_{date.today()}.json").write_text(
        json.dumps(receipt, indent=1, default=str), encoding="utf-8")

    logger.info("=" * 72)
    logger.info("%d predictions on the record; effective distinct ideas %s of "
                "%s across all specialists", len(all_preds),
                across["effective_distinct_ideas"], across["n_forecasts"])
    logger.info("nothing resolves yet — the earliest horizon is 5 trading days. "
                "That is the point: the clock started tonight.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
