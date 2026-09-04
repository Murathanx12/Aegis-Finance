"""Write the `<oldname>.SUPERSEDED_BY.json` sidecars for the four void tape receipts.

WHY A SIDECAR AND NOT AN EDIT
=============================
A sealed receipt is NEVER edited. Repairing a tamper-evident artefact IS the
tampering -- the ledger hash chain in the terminal repo has been broken since
25 August precisely because nobody was allowed to "fix" it quietly. So a
correction is a NEW receipt plus a sidecar that points at it, and the sidecar
records BOTH sha256s so a later reader can tell whether either side moved after
the link was made. `backend/tests/test_reissued_tape_receipts.py` re-hashes the
sealed file and fails if it no longer matches.

WHY THE SIDECARS QUOTE NO RETURN NUMBERS
========================================
`backend/tests/test_benchmark_canonical.py` scans every `*.json` under
`tracker_backtest/` and demands a canonical `learner.benchmark` stamp beside any
market-relative return. A sidecar that quoted an old excess figure would need a
stamp for a number whose entire purpose is to be void, so the sidecars carry
prose and hashes only. The prose names the numbers; no key does.

IDEMPOTENT: a rerun rewrites a sidecar only when something other than the
timestamp changed, so `git status` stays honest about what actually moved.

Run:  python -m scripts.write_superseded_sidecars [--check]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RECEIPTS = REPO / "backend" / "data" / "optimus" / "tracker_backtest"

#: sealed (void) receipt -> (its replacement, why the sealed one is void).
PAIRS: dict[str, tuple[str, str]] = {
    "band_horizon_20260903.json": (
        "band_horizon_20260905.json",
        "Computed on `learner-train-table-1`, whose `ratio` divided the SPLIT-ADJUSTED "
        "IBES consensus (`ptgsum`) by the RAW CRSP close. The `toxic_ge_5` cell was "
        "therefore largely a FUTURE-REVERSE-SPLIT detector: 74.4% of its 26,199 "
        "name-months carried one, and splitting that cell on `cfacpr` gives -13.4%/yr "
        "for the clean half against -48.9%/yr for the contaminated half -- the lookahead "
        "WAS the effect. Re-run on `learner-train-table-2` (`ibes__ptgsumu` over the same "
        "raw close), the four bands land at -2.2 / -6.8 / -5.3 / +40.1 pp/yr at one month "
        "against -0.8 / +3.8 / +18.9 / -37.0, the BH-FDR screen goes from 8 survivors "
        "(all of them the toxic cell) to ZERO, and the +40.1 toxic cell flips sign to "
        "-34.3%/yr under a $5 price floor. The defensible statement from the new receipt "
        "is the NEGATIVE one: under a point-in-time ratio no band premium survives."),
    "toxic_band_short_20260904.json": (
        "toxic_band_short_20260905.json",
        "Void twice over. (1) Same corrupted-ratio panel: the short it priced was a short "
        "of names that were about to reverse-split. (2) Its headline numbers were 'hedged "
        "gross' -- a P&L per $1 of SHORT notional against an unfunded LONG index leg of "
        "beta dollars. Its best line, `liq_floored_hedged_beta` at +76.63%/yr with a block "
        "t of 7.24 (and `hedged_beta` at +61.94%/yr, t 6.85), embedded the equity premium "
        "that long leg earned, and the capital the pair requires never entered the "
        "denominator. The new receipt reports `-resid` (the per-name beta leg already "
        "subtracted) on Reg-T capital (0.5 x short + 0.5 x long) and quotes the "
        "`beta_matched` leg beside it. On the rebuilt panel those two constructions are "
        "-29.25%/yr (t_b -0.88) and -32.29%/yr (t_b -2.07), against beta_matched legs of "
        "+34.89%/yr and +18.78%/yr respectively: the population the old receipt wanted to "
        "SHORT is a population whose corrected return is POSITIVE. Shorting it loses."),
    "revision_6m_cohorts_20260904.json": (
        "revision_6m_cohorts_20260905.json",
        "Void for a reason stronger than the panel defect: every arm selected inside "
        "`in_admissible`, which is a RATIO threshold, so the revision mechanism was "
        "measured inside a pool carved by the corrupted split-adjusted ratio. A revision "
        "result measured in a contaminated pool is not a revision result. The new receipt "
        "runs the same engine over the FULL PIT HYGIENE universe (363,684 name-months "
        "against 66,821 -- 5.4x wider) and reports TWO independent definitions of a "
        "revision, `target_rev_1m` (a pct change of the consensus price TARGET, derived "
        "from the same level whose share basis was the defect) and `net_rev_1m` (a count "
        "of UP minus DOWN analyst revisions, which touches no price at all), each with "
        "its own >=64-draw permutation null. Neither beats the value-weighted market "
        "(terminal wealth 2.937 and 3.102 against 3.236 at 25bps per side); both beat "
        "ALL 64 draws from their own pool. Ranking skill and money are separate "
        "questions and the old receipt could not tell them apart."),
    "holding_period_policy_20260903.json": (
        "holding_period_policy_20260905.json",
        "Same corrupted-ratio panel, and every arm selects inside `in_admissible` -- so "
        "the arms were buying a different set of names than the receipt said. The "
        "instrument (the horizon sweep) was sound; its opportunity set was not. Re-run on "
        "`learner-train-table-2` the conclusion REVERSES: at 25bps per side no arm in the "
        "receipt has a positive excess CAGR over the value-weighted market, and the S36 "
        "champion `rev_top50/fixed_H6m_25bps` goes from terminal wealth 3.743 (excess "
        "+1.674pp/yr, t +0.69) to 1.284 (excess -10.08pp/yr, t -1.00) against an unchanged "
        "market terminal wealth of 3.41. The market leg did not move; the selection did, "
        "which is exactly what a share-basis defect in an admission threshold does."),
}

#: The one mutable field. Excluded from the change comparison so a rerun that
#: alters nothing else leaves the file (and `git status`) alone.
_VOLATILE = "written_at_utc"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(old: str, new: str, reason: str) -> dict:
    op, np_ = RECEIPTS / old, RECEIPTS / new
    return {
        "artefact": "SUPERSEDED_BY_SIDECAR",
        "written_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sealed_receipt": old,
        "sealed_receipt_sha256": _sha(op),
        "sealed_receipt_bytes": op.stat().st_size,
        "superseded_by": new,
        "superseded_by_sha256": _sha(np_),
        "status": "VOID -- DO NOT QUOTE ANY NUMBER FROM THE SEALED RECEIPT",
        "reason": reason,
        "authority": ("roadmap B1 task 4 (docs/ROADMAP_2026-09-04_PROFIT_ENGINE.md) and "
                      "docs/VERIFICATION_2026-09-04_OPUS5_ON_FABLE51.md"),
        "panel_rebuild_receipt": "panel_rebuild_20260904.json",
        "written_by": "scripts/write_superseded_sidecars.py",
        "never_edit": (
            "the sealed receipt is NOT edited and NOT deleted. Repairing a "
            "tamper-evident artefact is the tampering. Both sha256s are recorded here so "
            "a later reader can tell whether either file moved after this link was made."),
        "no_return_fields_here_on_purpose": (
            "this sidecar quotes no return numbers in any KEY. "
            "test_benchmark_canonical.py scans every *.json in this directory, and a "
            "sidecar carrying an old excess figure would need a canonical benchmark stamp "
            "for a number whose whole purpose is to be void."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report what would change and write nothing (exit 1 if stale)")
    a = ap.parse_args(argv)

    stale = 0
    for old, (new, reason) in PAIRS.items():
        op, np_ = RECEIPTS / old, RECEIPTS / new
        if not op.exists():
            print(f"REFUSED: sealed receipt missing: {op}")
            return 2
        if not np_.exists():
            print(f"REFUSED: replacement missing: {np_} -- run its script first")
            return 2
        side = RECEIPTS / (old + ".SUPERSEDED_BY.json")
        body = build(old, new, reason)
        if side.exists():
            try:
                cur = json.loads(side.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cur = {}
            if {k: v for k, v in cur.items() if k != _VOLATILE} == \
               {k: v for k, v in body.items() if k != _VOLATILE}:
                print(f"unchanged  {side.name}")
                continue
        stale += 1
        if a.check:
            print(f"STALE      {side.name}")
            continue
        side.write_text(json.dumps(body, indent=2), encoding="utf-8")
        print(f"wrote      {side.name}")
    if a.check and stale:
        print(f"\n{stale} sidecar(s) stale -- run without --check")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
