"""Lineage-clean is not the same as unspent, and the register cannot tell.

WHAT IS MISSING FROM `slice_register`
=====================================
R13e made the register refuse a confirmation whose LINEAGE already read that
calendar. That is exactly right for leakage and it is silent about the other
way a holdout gets used up:

    fifty UNRELATED mechanisms confirm on 2020-2026, each at p < 0.05.

No two share a lineage, so the register calls every one of those windows clean —
and it is right, on the axis it measures. Under the null, ~2.5 of them are
"confirmed" anyway. The factory exists to generate mechanisms in bulk, so this
fires on its FIRST batch rather than eventually.

The register answers "has this data been used to CHOOSE what I am testing?"
This answers "how many independent chances has this window already given us?"
Both are properties of the window; only one of them is about leakage.

THE DESIGN, AND WHY EACH PIECE HAS TO BE THERE
==============================================
**The budget is declared before the window is looked at.** A budget set after
the first result is a budget chosen to fit the result. `declare_budget` refuses
to change a budget once any result on that window has been recorded.

**A reservation is taken before the p-value exists.** `record_result` refuses a
p-value with no prior reservation, which is what stops the family from being
defined retroactively as "the tests that happened to work".

**Holm over the DECLARED budget, not the number of tests run.** If five slots
are reserved and three used, using m=3 is anti-conservative whenever the choice
of which three to run depended on anything seen in the window. m = max(declared
budget, results) is conservative, and conservative is the correct direction for
the last untouched window this corpus has.

**Holm rather than Bonferroni.** Same family-wise guarantee, uniformly more
power, no extra assumption. There is no reason to prefer the weaker procedure.

WHAT THIS IS NOT
================
It is not a literature standard. Harvey-Liu-Zhu argue for a much higher hurdle
(t > 3) after extensive mining, and Bailey-Lopez de Prado deflate Sharpe ratios
for the number of variants tried. Those attack the same problem from the effect
side. This is an ENGINEERING BUDGET on how many chances one irreplaceable window
gets, declared in advance and enforced mechanically — a complement to those, not
a substitute, and `variants_tried` is recorded so a deflated-Sharpe calculation
remains possible later.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from backend import config as _config

LEDGER_PATH = (_config.OPTIMUS_LEDGER_DIR / "research_gym"
               / "confirmation_budget.jsonl")

#: Family-wise error rate the budget is enforced at.
DEFAULT_FWER = 0.05

#: False-discovery rate for SCREENING. Deliberately looser than the FWER: a
#: screen that lets nothing through has no output to certify.
DEFAULT_FDR = 0.10

#: The recommended budget for one untouched historical window. Not derived —
#: an engineering choice, recorded so it can be argued with rather than
#: discovered in a footnote.
RECOMMENDED_BUDGET = 5

#: TWO PURPOSES, TWO ERROR CRITERIA, AND CONFLATING THEM WAS THE DEFECT.
#:
#: The first version applied Holm at a budget of five to everything. That is
#: right for the last untouched window and wrong for the Gym, where the whole
#: point is to generate in bulk — Holm over five hundred screening tests makes
#: the threshold 0.0001 and nothing survives. A machine that cannot pass its own
#: screen produces no candidates, and then the kill machinery IS the programme.
#:
#: SCREEN — the Gym. Hundreds of tests, cheap, and a false positive costs one
#:   wasted follow-up rather than a wrong belief. Benjamini-Hochberg controls
#:   the PROPORTION of discoveries that are false, which is the quantity that
#:   actually matters when you are producing a shortlist.
#: EXPORT — a shadow book, a paper lane, real money, or a claim in the paper.
#:   Here a false positive is a wrong belief that gets acted on, so the
#:   criterion is family-wise: Holm, over a budget declared in advance.
#:
#: A screen result may NEVER be reported as an export result. `decide` labels
#: which criterion produced each decision so the two cannot be quoted
#: interchangeably three sessions later.
SCREEN = "SCREEN"
EXPORT = "EXPORT"
PURPOSES = (SCREEN, EXPORT)


class MultiplicityRefusal(RuntimeError):
    """A confirmation this window has no remaining chances for."""


@dataclass
class Reservation:
    window_id: str
    trial: str
    hypothesis: str
    reserved_at: str
    #: How many variants were tried in the Gym to arrive at this one. Recorded,
    #: never enforced here — it is the input a deflated-Sharpe calculation
    #: needs, and reconstructing it afterwards is guesswork.
    variants_tried: int | None = None
    p_value: float | None = None
    result_recorded_at: str | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return {"kind": "reservation", **asdict(self)}


@dataclass
class Budget:
    window_id: str
    budget: int
    fwer: float
    declared_at: str
    declared_by: str
    note: str = ""
    #: SCREEN (Benjamini-Hochberg FDR) or EXPORT (Holm FWER). Defaults to
    #: EXPORT so a budget declared without thinking gets the STRICT criterion —
    #: the safe direction for a default is the one that refuses more.
    purpose: str = EXPORT
    #: The rate the purpose is enforced at. `fwer` is kept for the export path
    #: and back-compatibility; `rate` is what `decide` reads.
    rate: float | None = None

    def as_dict(self) -> dict:
        return {"kind": "budget", **asdict(self)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConfirmationBudget:
    """Append-only ledger of budgets, reservations and results per window."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else LEDGER_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── reading ────────────────────────────────────────────────────────────
    def _rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open(encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
        return out

    def _append(self, rec: dict) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def budget_of(self, window_id: str) -> Budget | None:
        last = None
        for r in self._rows():
            if r.get("kind") == "budget" and r["window_id"] == window_id:
                last = Budget(**{k: v for k, v in r.items() if k != "kind"})
        return last

    def reservations(self, window_id: str) -> list[Reservation]:
        """Latest state per (trial, hypothesis) — the ledger is append-only, so
        a result is a second row for a reservation that already exists."""
        by_key: dict[tuple, Reservation] = {}
        for r in self._rows():
            if r.get("kind") != "reservation" or r["window_id"] != window_id:
                continue
            res = Reservation(**{k: v for k, v in r.items() if k != "kind"})
            by_key[(res.trial, res.hypothesis)] = res
        return list(by_key.values())

    # ── writing ────────────────────────────────────────────────────────────
    def declare_budget(self, window_id: str, *, budget: int, declared_by: str,
                       fwer: float = DEFAULT_FWER, note: str = "",
                       purpose: str = EXPORT,
                       rate: float | None = None) -> Budget:
        """Declare how many chances this window gets. Once, before any result.

        Refuses to change after a result exists, because a budget raised to
        accommodate a sixth test is not a budget — it is the multiple-testing
        problem with a ledger entry.
        """
        if budget < 1:
            raise MultiplicityRefusal("a budget below 1 reserves nothing")
        existing = self.budget_of(window_id)
        scored = [r for r in self.reservations(window_id)
                  if r.p_value is not None]
        if existing is not None and scored:
            raise MultiplicityRefusal(
                f"{window_id} already has a declared budget of "
                f"{existing.budget} and {len(scored)} recorded result(s). "
                f"Changing it now would be choosing the family after seeing "
                f"the outcomes. Open a NEW window instead.")
        if purpose not in PURPOSES:
            raise MultiplicityRefusal(
                f"purpose {purpose!r} is not one of {PURPOSES}. A window whose "
                f"purpose is undeclared cannot be given an error criterion, and "
                f"guessing one is how a screen result becomes an export claim.")
        if rate is None:
            rate = DEFAULT_FDR if purpose == SCREEN else float(fwer)
        b = Budget(window_id=window_id, budget=int(budget), fwer=float(fwer),
                   declared_at=_now(), declared_by=declared_by, note=note,
                   purpose=purpose, rate=float(rate))
        self._append(b.as_dict())
        return b

    def reserve(self, window_id: str, *, trial: str, hypothesis: str,
                variants_tried: int | None = None,
                note: str = "") -> Reservation:
        """Take a slot BEFORE the confirmation is run."""
        b = self.budget_of(window_id)
        if b is None:
            raise MultiplicityRefusal(
                f"no confirmation budget declared for {window_id}. Declare one "
                f"before reserving — a family defined after the fact is not a "
                f"family, it is the tests that happened to work.")
        held = self.reservations(window_id)
        if any(r.trial == trial and r.hypothesis == hypothesis for r in held):
            raise MultiplicityRefusal(
                f"{trial}/{hypothesis} already holds a slot on {window_id}. "
                f"Re-running the same hypothesis is not a second chance at it.")
        if len(held) >= b.budget:
            extra = ("" if b.purpose == EXPORT else
                     " (this is a SCREEN window — raise its capacity "
                     "deliberately if the Gym needs more, but a screen that "
                     "never ends is a screen nobody is counting)")
            raise MultiplicityRefusal(
                f"{window_id} has {len(held)}/{b.budget} slots taken{extra}. This "
                f"window is SPENT for confirmations. Remaining options: forward "
                f"time, a genuinely foreign market, or a different outcome "
                f"variable — not one more test here.")
        r = Reservation(window_id=window_id, trial=trial, hypothesis=hypothesis,
                        reserved_at=_now(), variants_tried=variants_tried,
                        note=note)
        self._append(r.as_dict())
        return r

    def record_result(self, window_id: str, *, trial: str, hypothesis: str,
                      p_value: float) -> Reservation:
        """Attach a p-value to a slot that was reserved before it existed."""
        held = {(r.trial, r.hypothesis): r
                for r in self.reservations(window_id)}
        r = held.get((trial, hypothesis))
        if r is None:
            raise MultiplicityRefusal(
                f"{trial}/{hypothesis} has no reservation on {window_id}. A "
                f"p-value with no prior reservation is a test that was not "
                f"counted, and the family-wise rate is computed over tests "
                f"that WERE counted.")
        if r.p_value is not None:
            raise MultiplicityRefusal(
                f"{trial}/{hypothesis} already recorded p={r.p_value}. A "
                f"second p-value for one reservation is a second test.")
        if not 0.0 <= float(p_value) <= 1.0:
            raise MultiplicityRefusal(f"p={p_value} is not a p-value")
        r.p_value = float(p_value)
        r.result_recorded_at = _now()
        self._append(r.as_dict())
        return r

    # ── the decision ───────────────────────────────────────────────────────
    def holm(self, window_id: str) -> dict:
        """Holm step-down over the DECLARED budget.

        `m = max(declared budget, results recorded)`. Using the number of tests
        actually run would be anti-conservative whenever the choice of which to
        run depended on anything seen in this window — and the whole reason to
        reserve slots in advance is that we cannot promise it did not.
        """
        b = self.budget_of(window_id)
        if b is None:
            raise MultiplicityRefusal(
                f"no budget declared for {window_id}; nothing to control.")
        scored = sorted((r for r in self.reservations(window_id)
                         if r.p_value is not None),
                        key=lambda r: r.p_value)
        m = max(b.budget, len(scored))
        out, rejected_so_far = [], True
        for i, r in enumerate(scored):
            thresh = b.fwer / (m - i)
            # Step-down: once one fails, everything after it fails too,
            # regardless of its own p. Reporting the raw comparison without
            # that carry-forward is the most common way Holm is mis-applied.
            passes = rejected_so_far and r.p_value <= thresh
            rejected_so_far = passes
            out.append({"trial": r.trial, "hypothesis": r.hypothesis,
                        "p_value": r.p_value, "holm_threshold": thresh,
                        "rejected": passes, "rank": i + 1,
                        "variants_tried": r.variants_tried})
        return {
            "window_id": window_id, "criterion": "HOLM_FWER",
            "purpose": b.purpose, "fwer": b.rate if b.rate is not None else b.fwer,
            "declared_budget": b.budget, "m_used": m,
            "slots_taken": len(self.reservations(window_id)),
            "results_recorded": len(scored),
            "n_rejected": sum(1 for o in out if o["rejected"]),
            "naive_n_below_alpha": sum(1 for o in out
                                       if o["p_value"] <= b.fwer),
            "decisions": out,
            "note": ("`naive_n_below_alpha` is what would have been claimed "
                     "without family-wise control; the gap between it and "
                     "`n_rejected` is what this ledger bought."),
        }

    def benjamini_hochberg(self, window_id: str) -> dict:
        """FDR step-UP, for screening. Controls the PROPORTION of false finds.

        The direction is opposite to Holm and that is the whole difference:
        Holm steps DOWN and stops at the first failure, so one weak result
        blocks everything behind it. BH walks UP from the largest p, finds the
        LAST rank where p <= (i/m)q, and rejects everything at or below it — so
        a shortlist of a hundred with sixty genuine effects passes sixty rather
        than one.

        `m` is the number of tests RUN, not the declared budget. FDR is a
        property of the discovery set that was actually produced, and a screen's
        budget is a capacity limit rather than a family definition.
        """
        b = self.budget_of(window_id)
        if b is None:
            raise MultiplicityRefusal(
                f"no budget declared for {window_id}; nothing to control.")
        q = b.rate if b.rate is not None else DEFAULT_FDR
        scored = sorted((r for r in self.reservations(window_id)
                         if r.p_value is not None),
                        key=lambda r: r.p_value)
        m = len(scored)
        k = 0
        for i, r in enumerate(scored, start=1):
            if r.p_value <= (i / m) * q:
                k = i
        out = []
        for i, r in enumerate(scored, start=1):
            out.append({"trial": r.trial, "hypothesis": r.hypothesis,
                        "p_value": r.p_value, "bh_threshold": (i / m) * q,
                        "rejected": i <= k, "rank": i,
                        "variants_tried": r.variants_tried})
        return {
            "window_id": window_id, "criterion": "BH_FDR", "purpose": SCREEN,
            "q": q, "m_used": m, "declared_budget": b.budget,
            "results_recorded": m, "n_rejected": k,
            "naive_n_below_alpha": sum(1 for o in out if o["p_value"] <= q),
            "expected_false_among_rejected": round(k * q, 2),
            "decisions": out,
            "note": ("SCREENING result under FDR. Roughly "
                     f"{round(k * q, 1)} of these {k} are expected to be "
                     f"false, BY DESIGN. This may NOT be reported as a "
                     f"confirmation — an export needs its own EXPORT window "
                     f"and Holm."),
        }

    def decide(self, window_id: str) -> dict:
        """Apply whichever criterion this window's PURPOSE declared.

        One entry point on purpose. Letting a caller choose `holm` or
        `benjamini_hochberg` at the call site is letting it choose the error
        criterion after seeing the p-values, which is the thing every other
        guard here exists to prevent.
        """
        b = self.budget_of(window_id)
        if b is None:
            raise MultiplicityRefusal(
                f"no budget declared for {window_id}; nothing to control.")
        if b.purpose == SCREEN:
            return self.benjamini_hochberg(window_id)
        return self.holm(window_id)

    def remaining(self, window_id: str) -> int:
        b = self.budget_of(window_id)
        if b is None:
            return 0
        return max(0, b.budget - len(self.reservations(window_id)))


def window_id(*, universe: str, period: str, outcome: str) -> str:
    """A window is a universe x period x outcome, matching slice identity.

    The outcome is part of it deliberately: max-drawdown and terminal-return on
    the same dates are different questions with different power, and spending
    one does not spend the other (§59).
    """
    return f"{universe}|{period}|{outcome}"
