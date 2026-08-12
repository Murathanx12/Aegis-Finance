"""Run TRANSACTION-ENSEMBLE-1 end to end and write its two artifacts.

Usage:  python scripts/run_transaction_ensemble.py

Everything produced here is SYNTHETIC — an ensemble of transaction histories
consistent with declared anchor subsets, per the frozen prereg
(`Aegis module/TRIALS/PREREG_TRANSACTION_ENSEMBLE_1.md`, commit c5b81aa).
The range across members IS the result; no member is the answer.

Outputs:
    docs/conviction_replay/transaction_ensemble_members_checkpoint.json
        raw member rows (checkpoint; never quote one row)
    docs/conviction_replay/transaction_ensemble_1.json
        the graded Q1-Q4 answers + anchor-consistency matrix
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import (TE_GAP_RETURN_BOUNDS, TE_MAGNITUDE_CLASS_EDGES,  # noqa: E402
                            TE_MASTER_SEED, TE_MAX_ATTEMPTS_PER_MEMBER,
                            TE_MEMBERS_PER_ARM, TE_QUBT_ARMS, TE_SUBSETS)
from backend.services import transaction_ensemble as te  # noqa: E402

OUT_DIR = ROOT / "docs" / "conviction_replay"
CHECKPOINT = OUT_DIR / "transaction_ensemble_members_checkpoint.json"
FINAL = OUT_DIR / "transaction_ensemble_1.json"

logging.basicConfig(level=logging.WARNING)
logging.getLogger("backend.services.conviction_sheets").setLevel(logging.ERROR)
logging.getLogger("backend.services.conviction_prices").setLevel(logging.ERROR)


def main() -> None:
    t0 = time.time()
    ctx = te.Ctx()
    print(f"context: {len(ctx.days)} bars, exits feasible days "
          f"{{k: len(v) for k, v in ctx.exit_feasible.items()}}="
          f"{ {k: len(v) for k, v in ctx.exit_feasible.items()} }, "
          f"tolerances={ {k: round(v, 3) for k, v in ctx.exit_price_tol.items()} }")

    ens = te.generate_ensemble(ctx)
    n = len(ens["members"])
    print(f"generated {n} members over {ens['n_slots']} slots "
          f"in {time.time() - t0:.0f}s; unfilled arms: {ens['unfilled']}")

    answers = te.answer_questions(ens)
    rows = answers.pop("member_rows")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps({
        "SYNTHETIC": ("every row is a generated history consistent with its "
                      "declared anchors — NONE is Murat's record; never quote "
                      "one row as an answer, the range across rows is the "
                      "result"),
        "trial": "TRANSACTION-ENSEMBLE-1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "master_seed": TE_MASTER_SEED,
        "rows": rows,
    }, indent=1), encoding="utf-8")
    print(f"checkpoint: {CHECKPOINT} ({len(rows)} rows)")

    final = {
        "trial": "TRANSACTION-ENSEMBLE-1",
        "prereg": "Aegis module/TRIALS/PREREG_TRANSACTION_ENSEMBLE_1.md",
        "prereg_commit": "c5b81aa",
        "SYNTHETIC": ("bounds derived from generated transaction histories, "
                      "not from Murat's records; accrues ZERO; can promote "
                      "nothing; CONVICTION-REPLAY-1's UNRESOLVED stands"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_members": n,
        "n_slots": ens["n_slots"],
        "members_per_arm": TE_MEMBERS_PER_ARM,
        "arms": [f"{{{','.join(map(str, s))}}}|QUBT{a:g}"
                 for s in TE_SUBSETS for a in TE_QUBT_ARMS],
        "master_seed": TE_MASTER_SEED,
        "max_attempts_per_member": TE_MAX_ATTEMPTS_PER_MEMBER,
        "gap_bounds": list(TE_GAP_RETURN_BOUNDS),
        "magnitude_class_edges_pts": list(TE_MAGNITUDE_CLASS_EDGES),
        "grading_rule": ("ensemble_robust iff sign AND magnitude class agree "
                         "across every member of every arm; otherwise "
                         "DATA_NEEDED with the minimal exact ask (prereg §4)"),
        "exit_fill_tolerances": {k: round(v, 4)
                                 for k, v in ctx.exit_price_tol.items()},
        "rejections": ens["rejections"],
        "unfilled": ens["unfilled"],
        "Q1": answers["Q1"],
        "Q2": answers["Q2"],
        "Q3": answers["Q3"],
        "Q4": answers["Q4"],
        "what_this_may_not_do": [
            "enter murat_book.yaml, book_lanes.yaml, any lane, ledger or NAV table",
            "train anything — members are bounds, not data",
            "overturn CONVICTION-REPLAY-1 (UNRESOLVED stands)",
            "claim skill in either direction",
            "be collapsed to a preferred member (outcome-shopping)",
        ],
    }
    FINAL.write_text(json.dumps(final, indent=1), encoding="utf-8")
    print(f"final: {FINAL}")

    # console digest — ranges and counts only
    for q in ("Q1", "Q2", "Q3", "Q4"):
        print(f"\n-- {q} " + "-" * 60)  # ASCII: Windows consoles are cp1252
        if q == "Q2":
            for k, v in answers["Q2"]["matrix"].items():
                gaps = {a: v.get(f"required_gap_anchor{a[-1]}")
                        for a in ("anchor7", "anchor8", "anchor9")
                        if v.get(f"required_gap_anchor{a[-1]}")}
                print(f"  {k:16s} accepted {v['n_accepted']:2d}/{v['n_slots']}"
                      f"  admits={v['admits_a_consistent_history']}")
            print("  maximal witnessed:",
                  answers["Q2"]["maximal_consistent_subset"])
            continue
        node = answers[q]
        for k, v in node.items():
            if isinstance(v, dict) and "label" in v:
                r = v.get("range")
                rng = (f"[{r['min']:+.2f} .. {r['max']:+.2f}]"
                       if r else "n/a")
                print(f"  {k:24s} {v['label']:16s} {rng}  "
                      f"n={v.get('n_members', 0)}")
    print(f"\ndone in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
