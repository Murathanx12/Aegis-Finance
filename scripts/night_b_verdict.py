"""B's HONEST CLOSURE — TRIAL-DRAFT-B §5 applied to the numbers already read.

WHY THIS JOB EXISTS, AND WHY IT RE-RUNS NOTHING
===============================================
`B_first_books_replay` run 1 (2026-09-12) read both insider-cluster arms:

    insider_cluster_length_v1    (spans 4-5)  -0.1354% per filing-month block,
                                              NW lag-2 t -0.0778, p 0.9380,
                                              212 blocks
    insider_cluster_same_day_v1  (span 0)     -0.1574%, t -0.3920, p 0.6951,
                                              223 blocks

Both point estimates are NEGATIVE, and the receipt carries a power warning that
is easy to read as a reason not to decide:

    "the registered MDE (7.17%) is ABOVE the published effect (5.0%): a
    non-significant result here is CONDITIONAL, never FAILED_VARIANT, unless
    the point estimate is <= 0"

That last clause is the whole job. §4's power finding protects an underpowered
design from being read as evidence of absence; it does NOT protect a design
whose point estimate is on the wrong side of zero, and §5's first
`FAILED_VARIANT` clause is exactly "net block-mean <= 0". A session that
re-reads the power warning and stops has turned a registered rule into a way of
never closing anything.

So this job reads the receipt and applies §5 verbatim. It runs no backtest,
loads no tape and takes seconds. What it adds over eyeballing the number is
that the arithmetic is in code, the clauses are named, and the two things a
reader is most likely to conflate are separated:

  * the same-day arm's verdict AS A BOOK (its own point estimate), and
  * the same-day arm's verdict AS BOOK B's FALSIFIER (did it BEAT non-cluster
    purchases?). It did not, so the falsifier SURVIVES -- which closes nothing
    and rescues nothing, and is reported as its own line rather than folded
    into the book's verdict.

WHAT IT REFUSES
===============
§5's third `FAILED_VARIANT` clause is "post-floor attrition leaves < 10
names/year", and run 1's receipt carries no per-year name count. That clause is
therefore `CANNOT_DETERMINE` and says so BY NAME. A guard derives its inputs or
refuses; silently treating an unmeasured clause as passed is how a gate that
cannot go green becomes a gate nobody reads.

And one era is one era. The 4-5-day arm's 2000-2009 cell is +6.11% (t 1.4718,
46 blocks) -- outside the confirm slice, inside Kang-Kim-Wang's own sample, and
not a rescue. It is reported under `single_positive_era` with that sentence
attached.

    python -m scripts.night_factory_jobs B_verdict
    python -m scripts.night_factory_jobs B_verdict --smoke   # reads the SMOKE receipt
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from scripts.night_first_books_replay import FAMILY, find_run_receipt

logger = logging.getLogger("b_verdict")

JOB = "B_verdict"
PREREG = "TRIAL-DRAFT-B-insider-cluster-length-v1 (UNSIGNED)"

#: The two arms of ONE registration. They share a prereg, a family and a
#: decision rule; they are not two books with two budgets.
ARMS = ("insider_cluster_length_v1", "insider_cluster_same_day_v1")

#: §2 and §3: 2017-2024 is the confirm slice, chosen because it is the first
#: period after Kang-Kim-Wang's sample ends. `by_era`'s key for it is the same
#: string, so the rule reads the era table rather than a second computation.
CONFIRM_SLICE = "2017-2024"

#: §4's computed MDE per filing-month block, which §5 uses as the
#: `PRODUCT_PROMISING` threshold. It is ABOVE Kang-Kim-Wang's published 5.0%
#: gap, which is the finding §4 records before the read.
DECLARED_MDE_PER_BLOCK = 0.0717
PUBLISHED_EFFECT = 0.05

#: §5's block-t threshold.
T_PASS = 2.0

#: §5's tradability gates, in qualifying names per year.
PROMOTE_NAMES_PER_YEAR = 20
CLOSE_NAMES_PER_YEAR = 10


def _mean(block: dict | None):
    """The mean a block reports, whichever of the two names it is filed under.

    `run_monthly`'s result calls it `mean_excess_net_monthly` and the BHAR arms
    call it `mean_bhar_excess_vs_twin`; `by_era` is generic and uses the first
    for both. Reading only one of them would silently return `None` for half
    the receipt and a `None` is not a zero.
    """
    if not block:
        return None
    for key in ("mean_bhar_excess_vs_twin", "mean_excess_net_monthly"):
        if block.get(key) is not None:
            return float(block[key])
    return None


def arm_numbers(book: dict) -> dict:
    """The four numbers §5 reads, pulled out of one book's receipt entry."""
    res = book.get("result") or {}
    eras = book.get("by_era") or {}
    confirm = eras.get(CONFIRM_SLICE) or {}
    return {
        "book": book.get("book"),
        "spans": book.get("spans"),
        "ran": bool(book.get("ran")),
        "pooled_mean": _mean(res),
        "pooled_t": res.get("nw_lag2_t"),
        "pooled_p": res.get("p_two_sided"),
        "pooled_n_blocks": res.get("n_blocks"),
        "confirm_slice": CONFIRM_SLICE,
        "confirm_mean": _mean(confirm),
        "confirm_t": confirm.get("nw_lag2_t"),
        "confirm_n_blocks": confirm.get("n_blocks"),
        "names_per_year": book.get("names_per_year"),
        "declared_mde_per_block": book.get("declared_mde_per_block"),
        "power_warning": book.get("power_warning"),
    }


def tradability_clause(n: dict) -> dict:
    """§5's third clause, or a refusal that names what is missing."""
    per_year = n.get("names_per_year")
    if per_year is None:
        return {"status": "CANNOT_DETERMINE",
                "fires": None,
                "why": ("run 1's receipt carries no post-floor name count per "
                        f"year, so §5's '< {CLOSE_NAMES_PER_YEAR} names/year' "
                        f"clause has no input. A guard DERIVES its inputs or "
                        f"REFUSES; treating an unmeasured clause as passed is "
                        f"how a gate stops being read. The cluster panel's own "
                        f"per-year count is what would answer it.")}
    worst = min(per_year.values()) if per_year else 0
    return {"status": "MEASURED", "min_names_per_year": worst,
            "fires": bool(worst < CLOSE_NAMES_PER_YEAR),
            "promote_gate_met": bool(worst >= PROMOTE_NAMES_PER_YEAR),
            "why": (f"the thinnest year carries {worst} qualifying names "
                    f"against a close-the-book floor of {CLOSE_NAMES_PER_YEAR} "
                    f"and a promote gate of {PROMOTE_NAMES_PER_YEAR}")}


def falsifier_status(same_day: dict) -> dict:
    """Did the SAME-DAY arm beat non-cluster purchases? §5 clause 2.

    This is a statement about BOOK B's mechanism, not a verdict on the same-day
    arm as a book of its own. Kang-Kim-Wang predict same-day clusters do WORSE;
    if ours does better, "slow multi-day clusters get priced slowly" is refuted
    whatever the 4-5-day arm did.
    """
    mean = same_day.get("pooled_mean")
    confirm = same_day.get("confirm_mean")
    if mean is None and confirm is None:
        return {"status": "CANNOT_DETERMINE", "beats_non_cluster": None,
                "why": "the same-day arm produced no readable block mean"}
    beats = bool((confirm if confirm is not None else mean) > 0)
    return {
        "status": "MEASURED",
        "beats_non_cluster": beats,
        "confirm_mean": confirm, "pooled_mean": mean,
        "why": (f"the same-day arm reads {confirm} on {CONFIRM_SLICE} and "
                f"{mean} pooled against its random Form-4-active twin. §5's "
                f"clause 2 fires only if it OUTPERFORMS; it does not, so the "
                f"mechanism's falsifier SURVIVES — which closes nothing and "
                f"rescues nothing. A falsifier that passes is not evidence for "
                f"the book."),
    }


def arm_verdict(n: dict, *, falsifier: dict, tradability: dict) -> dict:
    """TRIAL-DRAFT-B §5, verbatim, for one arm.

    The deciding number is the CONFIRM SLICE's block mean (§3: "the mean over
    filing-month date blocks 2017-01..2024-12"). The pooled mean is reported
    beside it and, when the two disagree in sign, the disagreement is named
    rather than resolved by whichever is more convenient.
    """
    if not n.get("ran"):
        return {"verdict": "CANNOT_DETERMINE",
                "why": "this arm did not run in the receipt being read"}
    decide_on = n.get("confirm_mean")
    if decide_on is None:
        decide_on = n.get("pooled_mean")
        basis = "pooled (the confirm slice carried no readable mean)"
    else:
        basis = f"the {CONFIRM_SLICE} confirm slice"
    if decide_on is None:
        return {"verdict": "CANNOT_DETERMINE",
                "why": "no readable block mean on either the confirm slice or pooled"}
    t = n.get("confirm_t") if n.get("confirm_mean") is not None else n.get("pooled_t")

    clauses = []
    if decide_on <= 0:
        clauses.append(f"§5 clause 1: the net block-mean on {basis} is "
                       f"{decide_on:+.6f}, which is <= 0")
    if falsifier.get("beats_non_cluster"):
        clauses.append("§5 clause 2: the same-day arm OUTPERFORMS non-cluster "
                       "purchases, so the length-conditioning mechanism is "
                       "falsified whatever the 4-5-day arm did")
    if tradability.get("fires"):
        clauses.append(f"§5 clause 3: post-floor attrition leaves fewer than "
                       f"{CLOSE_NAMES_PER_YEAR} names/year")
    if clauses:
        return {
            "verdict": "FAILED_VARIANT",
            "clauses_fired": clauses,
            "deciding_number": decide_on, "deciding_basis": basis,
            "nw_lag2_t": t,
            "why": (
                "; ".join(clauses) + ". §4's power warning does NOT hold this "
                "open: it says a non-significant result is CONDITIONAL, never "
                "FAILED_VARIANT, **unless the point estimate is <= 0** — and it "
                "is. An underpowered design that reports 'no effect' is "
                "reporting its own sample size; an underpowered design whose "
                "estimate is on the wrong side of zero has still not found the "
                "effect it registered."),
            "unevaluated_clauses": ([tradability["why"]]
                                    if tradability.get("fires") is None else []),
        }
    promising = bool(decide_on >= DECLARED_MDE_PER_BLOCK and t is not None
                     and t >= T_PASS
                     and falsifier.get("beats_non_cluster") is False
                     and tradability.get("promote_gate_met"))
    if promising:
        return {"verdict": "PRODUCT_PROMISING", "clauses_fired": [],
                "deciding_number": decide_on, "deciding_basis": basis,
                "nw_lag2_t": t,
                "why": (f"{decide_on:+.6f} on {basis} at t {t} clears the "
                        f"computed MDE of {DECLARED_MDE_PER_BLOCK:.4f}, the "
                        f"falsifier survives and the tradability gate is met")}
    return {
        "verdict": "CONDITIONAL", "clauses_fired": [],
        "deciding_number": decide_on, "deciding_basis": basis, "nw_lag2_t": t,
        "why": (f"{decide_on:+.6f} on {basis} at t {t} is above zero and below "
                f"the computed MDE of {DECLARED_MDE_PER_BLOCK:.4f} (§4: this "
                f"design is UNDERPOWERED for its own prior, {PUBLISHED_EFFECT} "
                f"< {DECLARED_MDE_PER_BLOCK}), which §5 calls CONDITIONAL and "
                f"§4 calls the modal case"),
        "unevaluated_clauses": ([tradability["why"]]
                                if tradability.get("fires") is None else []),
    }


def single_positive_era(book: dict) -> dict | None:
    """The one era that went the other way, reported as ONE ERA.

    Named here so a later reader finds it already accounted for rather than
    discovering it and treating it as a rescue.
    """
    eras = book.get("by_era") or {}
    pos = {k: v for k, v in eras.items()
           if _mean(v) is not None and _mean(v) > 0}
    if not pos:
        return None
    return {"eras": pos,
            "reading": ("ONE ERA, and it decides nothing. The confirm slice is "
                        f"{CONFIRM_SLICE} and was chosen before the read "
                        "because it is the first period after Kang-Kim-Wang's "
                        "sample ends; an era inside their sample going the "
                        "other way is what a decayed effect looks like, not a "
                        "reason to reopen the book. §5 has no 'best era' "
                        "clause.")}


def read_receipt(path: Path | None) -> dict | None:
    if path is None or not Path(path).is_file():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def B_verdict(*, smoke: bool = False, path=None) -> dict:         # noqa: N802
    """The night-factory entry point. Reads a receipt; runs no backtest."""
    receipt = Path(path) if path else find_run_receipt(smoke=smoke)
    payload = read_receipt(receipt)
    base = {
        "job": JOB, "family": FAMILY, "licence": "PRODUCT_EXPERIMENT",
        "prereg": PREREG, "arms": list(ARMS),
        "reads_receipt": (str(receipt) if receipt else None),
        "smoke": bool(smoke),
        "runs_no_backtest": ("this job re-computes nothing. It applies "
                             "TRIAL-DRAFT-B §5 to numbers a named receipt "
                             "already carries, so its output can be checked "
                             "against that receipt by hand."),
        "decision_rule": (
            "TRIAL-DRAFT-B §5. FAILED_VARIANT if the net block-mean is <= 0, "
            "OR the same-day arm outperforms non-cluster purchases, OR "
            "post-floor attrition leaves < 10 names/year. PRODUCT_PROMISING "
            "needs the block-mean >= the computed MDE of 7.17% at t >= 2.0 "
            "with the falsifier surviving and >= 20 names/year. Everything "
            "between is CONDITIONAL."),
        "power_finding": (
            f"§4, computed BEFORE the read: the MDE is "
            f"{DECLARED_MDE_PER_BLOCK:.4f} per block against a published gap "
            f"of {PUBLISHED_EFFECT:.2f}, so this design cannot confirm its own "
            f"prior at 80% power. That changes what the trial may CONCLUDE, "
            f"not whether it runs — and its protection is explicitly "
            f"conditional on the point estimate being above zero."),
    }
    if payload is None:
        return {**base, "ran": False,
                "refused": (f"no B_first_books_replay receipt found"
                            f"{' (smoke)' if smoke else ''}. Run "
                            f"`python -m scripts.night_factory_jobs "
                            f"B_first_books_replay` first; this job does not "
                            f"produce the numbers it grades."),
                "headline": "no replay receipt to read",
                "verdict": "REFUSED: nothing to grade"}

    books = {b.get("book"): b for b in (payload.get("books") or [])}
    numbers = {arm: arm_numbers(books.get(arm) or {}) for arm in ARMS}
    fals = falsifier_status(numbers["insider_cluster_same_day_v1"])
    out = {}
    for arm in ARMS:
        trad = tradability_clause(numbers[arm])
        out[arm] = {
            "numbers": numbers[arm],
            "tradability_clause": trad,
            "verdict_block": arm_verdict(numbers[arm], falsifier=fals,
                                         tradability=trad),
            "single_positive_era": single_positive_era(books.get(arm) or {}),
        }
    verdicts = {a: out[a]["verdict_block"]["verdict"] for a in ARMS}
    return {
        **base, "ran": True,
        "replay_run": payload.get("run"), "replay_window": payload.get("window"),
        "replay_written_utc": payload.get("written_utc"),
        "cost_curve": payload.get("cost_curve"),
        "falsifier_status": fals,
        "arm_verdicts": verdicts,
        "per_arm": out,
        "family_holm_from_the_receipt": payload.get("holm"),
        "next_test": (
            "MORE BLOCKS, i.e. time, is the only honest route to power on this "
            "construction (§4.3) — and a wider event definition is a NEW "
            "REGISTRATION, not an amendment. Per EXPLORE DIRTY, PROMOTE CLEAN, "
            "a FAILED_VARIANT here closes THIS implementation of cluster "
            "length, not insider clustering and not the Form-4 tape: the "
            "executive-only cut, the CMP opportunistic/routine 2x2 and the 1-3 "
            "day span bucket are each a separate registration §8 already "
            "forbids claiming from this one."),
        "headline": "; ".join(
            f"{a} {out[a]['verdict_block'].get('deciding_number')} on "
            f"{CONFIRM_SLICE} -> {verdicts[a]}" for a in ARMS),
        "verdict": ("; ".join(f"{a}: {verdicts[a]}" for a in ARMS)
                    + " — " + out[ARMS[0]]["verdict_block"].get("why", "")),
    }


__all__ = ["ARMS", "B_verdict", "arm_numbers", "arm_verdict",
           "falsifier_status", "read_receipt", "single_positive_era",
           "tradability_clause"]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--receipt", default=None)
    a = ap.parse_args()
    print(json.dumps(B_verdict(smoke=a.smoke, path=a.receipt), indent=1,
                     default=str))
