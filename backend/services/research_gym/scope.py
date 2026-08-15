"""Scope-aware verdicts — a negative result may only claim what it measured.

WHY THIS MODULE EXISTS (found by reading `adjudicate()`, 2026-08-15)
===================================================================
`Autopsy` **requires** `expected_unaffected_states`. It validates them non-empty,
validates they do not overlap the affected list, and writes them into the
lineage row. Then the verdict is produced by `charter.request_export` ->
`TransferTest.n_independent_slices_passed()`, which is a **flat count of slices
where `passed` is true**, with no notion of which slices the mechanism itself
declared it should work in.

So the machinery collected the discriminating half of every hypothesis and threw
it away. A mechanism that is real in its declared regime and correctly silent
everywhere else scored its correctly-silent slices as failures and came back
`REFUSED - survived 1 of 3`. There was no way for it to distinguish *does not
generalise* from *is conditional, exactly as declared* — and firing everywhere is
what beta does.

WHAT CHANGES, AND WHAT DELIBERATELY DOES NOT
============================================
The bar does not move. What moves is the **claim a failure is allowed to make**.

  * A verdict now carries its scope. `REFUTED_IN_SCOPE` closes one environment,
    not an idea.
  * `DEAD` is gone. Where the old code emitted it for a mechanism that ran and
    did not clear its MDE, SS19 has always said `NOT_DETECTABLE` — which is how
    195 existing kills quietly became absence-of-evidence.
  * Only `REFUTED_IN_SCOPE` and `STRUCTURALLY_CLOSED` close anything, and the
    first closes only its own scope.
  * Every non-support carries `revisit_when`. A kill without a resurrection
    condition is how a project loses ideas it never disproved.

THE SIGN INVERSION, WHICH IS THE POINT
======================================
Failing in a declared-`UNAFFECTED` region is **confirming**. Firing strongly
there is **disconfirming** — whatever was found is broader and dumber than the
mechanism claimed, and is probably the action rather than the mechanism.

That makes the unaffected declaration a placebo family built into the hypothesis
itself. Canon has demanded "carry your corpse as control" for months and has
never had it structurally; this is it, and it costs nothing extra to collect
because the declaration was already being required and discarded.

THE GUARD THAT STOPS THIS BECOMING SUBGROUP MINING
==================================================
§18, and it is load-bearing. "Significant in A, insignificant in B" is NOT
evidence of conditionality. The A-B interaction is tested here directly, with
its own SE and its own MDE (`interaction`). Without that, scope-awareness is
just a machine for manufacturing regimes, and it would manufacture one for every
mechanism that happened to have a noisy slice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from backend.services.research_gym import power as PW

# ── the three scope labels ──────────────────────────────────────────────────

#: The mechanism declared it should work here. Evidence counts FOR it.
AFFECTED = "AFFECTED"
#: The mechanism declared it should be silent here. Evidence is INVERTED: a
#: null is confirming, a strong effect is disconfirming.
UNAFFECTED = "UNAFFECTED"
#: Declared neither way. Reported, never scored — scoring it would let the
#: adjudicator pick a side after seeing the number.
OUT_OF_SCOPE = "OUT_OF_SCOPE"

SCOPES = (AFFECTED, UNAFFECTED, OUT_OF_SCOPE)

# ── the nine verdicts ───────────────────────────────────────────────────────

SUPPORTED_IN_SCOPE = "SUPPORTED_IN_SCOPE"
REFUTED_IN_SCOPE = "REFUTED_IN_SCOPE"
NOT_DETECTABLE_IN_SCOPE = "NOT_DETECTABLE_IN_SCOPE"
UNPOWERED_IN_SCOPE = "UNPOWERED_IN_SCOPE"
UNTESTED = "UNTESTED"
DATA_BLOCKED = "DATA_BLOCKED"
CONDITIONAL_OPEN = "CONDITIONAL_OPEN"
TRANSFER_PENDING = "TRANSFER_PENDING"
STRUCTURALLY_CLOSED = "STRUCTURALLY_CLOSED"

VERDICTS: dict[str, str] = {
    SUPPORTED_IN_SCOPE: "detectable evidence in the declared environment",
    REFUTED_IN_SCOPE: ("POWERED evidence against this exact rule in this "
                       "environment"),
    NOT_DETECTABLE_IN_SCOPE: ("ran, fired, below its own MDE — SS19, never a "
                              "kill"),
    UNPOWERED_IN_SCOPE: "too little effective sample to have resolved it",
    UNTESTED: "never actually evaluated (vocabulary or coverage failure)",
    DATA_BLOCKED: "the necessary data does not exist yet",
    CONDITIONAL_OPEN: ("global result weak or null, state dependence "
                       "untested"),
    TRANSFER_PENDING: "transferred partly, not enough",
    STRUCTURALLY_CLOSED: "genuine impossibility only",
}

#: The only two verdicts that close anything — and the first closes only its own
#: scope. Everything else leaves the question open by construction.
CLOSING_VERDICTS = frozenset({REFUTED_IN_SCOPE, STRUCTURALLY_CLOSED})

#: A verdict that is not support owes a resurrection condition.
NON_SUPPORT = frozenset(set(VERDICTS) - {SUPPORTED_IN_SCOPE})

#: `STRUCTURALLY_CLOSED` is reserved, and reserved narrowly. Left open it would
#: become the new `DEAD` within a week — the vocabulary problem does not fix
#: itself by having more words in it.
STRUCTURAL_CLOSURE_GROUNDS = frozenset({
    "mathematical_impossibility",
    # An oracle establishing no economically meaningful headroom IN THE SAME
    # OBJECTIVE. GRAPH-COVARIANCE-1 qualifies: perfect foresight of forward
    # correlation was worth <=15.4% against the trailing sample matrix.
    "oracle_no_headroom_same_objective",
    "exact_duplicate_of_corpse",
    "infeasible_source",
    # A fully powered exact rule exhausted across its whole declared scope.
    "exhausted_powered_scope",
})


class ScopeRefused(ValueError):
    """A verdict that claims more than it measured, or closes without ground."""


@dataclass(frozen=True)
class ScopedVerdict:
    """One verdict, and the environment it is allowed to speak about.

    The `scope` field is not decoration. A verdict without it is a claim about
    the world; with it, it is a claim about a measured region of the world, and
    the difference is the entire ruling.
    """
    verdict: str
    #: Human-readable environment this speaks about ("VIX>=35 crisis slices",
    #: "1990-2005 large-cap US"). Never empty.
    scope: str
    reason: str
    #: What would make re-testing worthwhile. REQUIRED on every non-support.
    revisit_when: str = ""
    #: Only for STRUCTURALLY_CLOSED, and only from the closed list.
    closure_ground: str = ""
    n_effective: float | None = None
    mde_pp: float | None = None
    effect_pp: float | None = None

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ScopeRefused(
                f"{self.verdict!r} is not one of the nine verdicts "
                f"{sorted(VERDICTS)}. An open vocabulary is how `DEAD` came to "
                f"mean 'below its MDE'")
        if not str(self.scope or "").strip():
            raise ScopeRefused(
                "a verdict with no scope is a global claim, and a global claim "
                "is exactly what a slice of evidence cannot support")
        if self.verdict in NON_SUPPORT and not str(self.revisit_when
                                                   or "").strip():
            raise ScopeRefused(
                f"{self.verdict} carries no revisit_when. A negative without a "
                f"resurrection condition is how a project loses ideas it never "
                f"disproved — name the condition (n_effective > X, the regime "
                f"recurs, the corpus gains a feature) or do not record it")
        if self.verdict == STRUCTURALLY_CLOSED:
            if self.closure_ground not in STRUCTURAL_CLOSURE_GROUNDS:
                raise ScopeRefused(
                    f"STRUCTURALLY_CLOSED needs a ground from "
                    f"{sorted(STRUCTURAL_CLOSURE_GROUNDS)}, got "
                    f"{self.closure_ground!r}. Almost nothing qualifies, and "
                    f"an unreserved closure verdict is just DEAD wearing a "
                    f"longer name")
        elif self.closure_ground:
            raise ScopeRefused(
                f"closure_ground is only meaningful on STRUCTURALLY_CLOSED, "
                f"not on {self.verdict}")

    @property
    def closes_anything(self) -> bool:
        return self.verdict in CLOSING_VERDICTS

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict, "scope": self.scope,
            "meaning": VERDICTS[self.verdict],
            "reason": self.reason,
            "revisit_when": self.revisit_when or None,
            "closure_ground": self.closure_ground or None,
            "closes": self.closes_anything,
            "n_effective": (None if self.n_effective is None
                            else round(self.n_effective, 3)),
            "mde_pp": None if self.mde_pp is None else round(self.mde_pp, 3),
            "effect_pp": (None if self.effect_pp is None
                          else round(self.effect_pp, 3)),
            "citable": False,
        }


# ── §18: the interaction, tested as its own quantity ────────────────────────

@dataclass(frozen=True)
class Interaction:
    """The A-B difference, with its own SE and its own MDE.

    Two point estimates on opposite sides of a significance threshold do not
    make a conditional mechanism. This is the object that does, and its
    `detectable` flag is the only thing entitled to the word "conditional".
    """
    label: str
    mean_a_pp: float | None
    mean_b_pp: float | None
    diff_pp: float | None
    se_diff_pp: float | None
    t_stat: float | None
    mde_pp: float | None
    n_effective_a: float | None
    n_effective_b: float | None

    @property
    def detectable(self) -> bool:
        return bool(self.diff_pp is not None and self.mde_pp is not None
                    and abs(self.diff_pp) >= self.mde_pp)

    def as_dict(self) -> dict:
        r = (lambda x: None if x is None else round(x, 3))
        return {"label": self.label, "mean_a_pp": r(self.mean_a_pp),
                "mean_b_pp": r(self.mean_b_pp), "diff_pp": r(self.diff_pp),
                "se_diff_pp": r(self.se_diff_pp), "t": r(self.t_stat),
                "mde_pp": r(self.mde_pp),
                "n_effective_a": r(self.n_effective_a),
                "n_effective_b": r(self.n_effective_b),
                "detectable": self.detectable,
                "note": ("SS18 — this is the DIFFERENCE tested directly. "
                         "'Significant in A, not in B' is not this number.")}


def interaction(label: str,
                mean_a: float | None, se_a: float | None, n_eff_a: float | None,
                mean_b: float | None, se_b: float | None, n_eff_b: float | None
                ) -> Interaction:
    """Test A-B as its own quantity (§18)."""
    if mean_a is None or mean_b is None:
        return Interaction(label, mean_a, mean_b, None, None, None, None,
                           n_eff_a, n_eff_b)
    diff = mean_a - mean_b
    se = None
    if se_a is not None and se_b is not None:
        se = math.sqrt(se_a ** 2 + se_b ** 2)
    return Interaction(label, mean_a, mean_b, diff, se,
                       (diff / se) if se else None,
                       PW.mde_from_se(se), n_eff_a, n_eff_b)


# ── labelling a measurement cell, from a FROZEN declaration ─────────────────

@dataclass
class ScopedCell:
    """One measurement, in one slice, under one scope label.

    `scope` is set from the autopsy's frozen declaration BEFORE any number in
    this object is computed. That ordering is the reason labels cannot be chosen
    to fit results, and it is enforced by construction rather than by review.
    """
    slice_key: str
    scope: str
    n: int
    n_unevaluable: int
    mean_pp: float | None
    se_pp: float | None
    mde_pp: float | None
    n_effective: float | None

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise ScopeRefused(f"{self.scope!r} is not one of {SCOPES}")

    @property
    def ran(self) -> bool:
        """Did the mechanism actually get evaluated here at all?"""
        return self.n > 0

    @property
    def powered(self) -> bool:
        return self.mde_pp is not None

    @property
    def detectable_effect(self) -> bool:
        return bool(self.powered and self.mean_pp is not None
                    and abs(self.mean_pp) >= self.mde_pp)

    def verdict(self, *, revisit_when: str = "") -> ScopedVerdict:
        """The scoped verdict for this cell — WITH the sign inversion.

        In an `AFFECTED` cell a positive detectable effect supports the
        mechanism. In an `UNAFFECTED` cell the SAME result disconfirms it: the
        mechanism declared it should be silent here, and it was not, so what was
        found is broader than the mechanism and more likely to be the action
        than the mechanism.
        """
        where = f"{self.slice_key} [{self.scope}]"
        rv = revisit_when or _default_revisit(self)
        if not self.ran:
            return ScopedVerdict(
                UNTESTED, where,
                (f"the mechanism was never evaluated here "
                 f"({self.n_unevaluable} episode(s) unevaluable, 0 fired) — "
                 f"this is not a refutation"),
                revisit_when=rv, n_effective=self.n_effective)
        if not self.powered:
            return ScopedVerdict(
                UNPOWERED_IN_SCOPE, where,
                (f"n={self.n} (n_effective "
                 f"{'n/a' if self.n_effective is None else f'{self.n_effective:.1f}'}) "
                 f"carries no MDE — nothing here could have resolved it either "
                 f"way"),
                revisit_when=rv, n_effective=self.n_effective,
                effect_pp=self.mean_pp)

        if self.scope == UNAFFECTED:
            # THE INVERSION. Silence here is the prediction coming true.
            if not self.detectable_effect:
                return ScopedVerdict(
                    SUPPORTED_IN_SCOPE, where,
                    (f"declared silent here and is: {self.mean_pp:+.2f}pp "
                     f"against an MDE of {self.mde_pp:.2f}pp. A powered null in "
                     f"a declared-unaffected region is CONFIRMING — it is the "
                     f"mechanism's own placebo arm coming back empty"),
                    n_effective=self.n_effective, mde_pp=self.mde_pp,
                    effect_pp=self.mean_pp)
            return ScopedVerdict(
                REFUTED_IN_SCOPE, where,
                (f"declared silent here and fired anyway: {self.mean_pp:+.2f}pp "
                 f"vs MDE {self.mde_pp:.2f}pp. Whatever this is, it is broader "
                 f"than the declared mechanism — the action, not the "
                 f"conditioning"),
                revisit_when=("a narrower mechanism is declared whose "
                              "unaffected region actually excludes this one"),
                n_effective=self.n_effective, mde_pp=self.mde_pp,
                effect_pp=self.mean_pp)

        if self.scope == OUT_OF_SCOPE:
            return ScopedVerdict(
                CONDITIONAL_OPEN, where,
                (f"{self.mean_pp:+.2f}pp here, but this region was declared "
                 f"neither affected nor unaffected, so no verdict is earned — "
                 f"scoring it would be choosing a side after seeing the number"),
                revisit_when=("the mechanism is re-declared with this region "
                              "assigned to a side, in advance"),
                n_effective=self.n_effective, mde_pp=self.mde_pp,
                effect_pp=self.mean_pp)

        # AFFECTED
        if self.detectable_effect and self.mean_pp > 0:
            return ScopedVerdict(
                SUPPORTED_IN_SCOPE, where,
                f"{self.mean_pp:+.2f}pp clears its own MDE {self.mde_pp:.2f}pp "
                f"on n_effective {self.n_effective:.1f}",
                n_effective=self.n_effective, mde_pp=self.mde_pp,
                effect_pp=self.mean_pp)
        if self.detectable_effect:
            return ScopedVerdict(
                REFUTED_IN_SCOPE, where,
                (f"{self.mean_pp:+.2f}pp — a POWERED effect in the WRONG "
                 f"direction against MDE {self.mde_pp:.2f}pp. This is the one "
                 f"kind of negative that genuinely closes its own scope"),
                revisit_when=rv, n_effective=self.n_effective,
                mde_pp=self.mde_pp, effect_pp=self.mean_pp)
        return ScopedVerdict(
            NOT_DETECTABLE_IN_SCOPE, where,
            (f"{self.mean_pp:+.2f}pp against an MDE of {self.mde_pp:.2f}pp — "
             f"the instrument could not have seen an effect this size. SS19: "
             f"not a kill"),
            revisit_when=rv, n_effective=self.n_effective,
            mde_pp=self.mde_pp, effect_pp=self.mean_pp)

    def as_dict(self) -> dict:
        r = (lambda x: None if x is None else round(x, 3))
        return {"slice": self.slice_key, "scope": self.scope, "n": self.n,
                "n_unevaluable": self.n_unevaluable, "mean_pp": r(self.mean_pp),
                "se_pp": r(self.se_pp), "mde_pp": r(self.mde_pp),
                "n_effective": r(self.n_effective),
                "ran": self.ran, "powered": self.powered,
                "detectable_effect": self.detectable_effect}


# ── scope-aware corpse check (§2.6) — more precise, not weaker ─────────────

BLOCKED = "BLOCKED"
RESURRECTION_TAX = "RESURRECTION_TAX"
ALLOWED_WITH_PARENT_CONTROL = "ALLOWED_WITH_PARENT_CONTROL"


@dataclass(frozen=True)
class Corpse:
    """A dead hypothesis, with the scope its death is allowed to speak for."""
    mechanism_id: str
    precursor: dict
    proposed_action: str
    default_action: str
    verdict: str
    scope: str
    affected_precursor: dict | None = None

    @property
    def blocks_anything(self) -> bool:
        """A corpse that was never powered enough to die blocks nothing.

        This single property is where "195 kills are absence-of-evidence"
        becomes operational rather than rhetorical. A register full of
        `NOT_DETECTABLE_IN_SCOPE` rows stops gate-keeping the moment the
        verdicts are honest about what they measured.
        """
        return self.verdict in CLOSING_VERDICTS


def _clauses(spec: Any) -> list[dict]:
    """Flatten a precursor into its leaf comparisons."""
    out: list[dict] = []
    if not isinstance(spec, dict):
        return out
    for key in ("all", "any"):
        if key in spec:
            for p in spec[key]:
                out.extend(_clauses(p))
            return out
    if "not" in spec:
        return _clauses(spec["not"])
    if "feature" in spec:
        out.append(spec)
    return out


def rule_shape(spec: Any) -> tuple:
    """(feature, op) pairs — the rule with its THRESHOLDS removed.

    Two rules with the same shape and different numbers are the same mechanism
    at a different threshold. That is the resurrection this check exists to
    price: re-running `vix >= 30` after `vix >= 35` died is not a new idea.
    """
    return tuple(sorted((str(c.get("feature")), str(c.get("op")))
                        for c in _clauses(spec)))


def rule_exact(spec: Any) -> tuple:
    return tuple(sorted((str(c.get("feature")), str(c.get("op")),
                         repr(c.get("value"))) for c in _clauses(spec)))


def corpse_check(*, precursor: dict, proposed_action: str, default_action: str,
                 scope: str, corpses: Sequence[Corpse],
                 prospectively_declared: bool) -> dict:
    """May this candidate run, and what must it carry if so?

    Three outcomes, matching §2.6:

      * exact failed rule                          -> BLOCKED
      * same mechanism, same environment, only the
        thresholds moved                           -> RESURRECTION_TAX
      * mechanistically distinct, PROSPECTIVELY
        declared, state-conditioned descendant     -> ALLOWED, parent as a
                                                      MANDATORY control

    The third is the one the ruling opens, and the word doing the work is
    *prospectively*: discovering a condition in the sample that suggested it
    confers zero certification, so a descendant declared after seeing the
    parent's slice results is treated as the parent.
    """
    actions = (proposed_action, default_action)
    relevant = [c for c in corpses if c.blocks_anything]
    ignored = [c for c in corpses if not c.blocks_anything]

    for c in relevant:
        if (rule_exact(c.precursor) == rule_exact(precursor)
                and (c.proposed_action, c.default_action) == actions
                and c.scope == scope):
            return _cc(BLOCKED, c,
                       f"identical rule, identical action pair, identical "
                       f"scope {scope!r} — this is {c.mechanism_id} again",
                       ignored)

    for c in relevant:
        if (rule_shape(c.precursor) == rule_shape(precursor)
                and (c.proposed_action, c.default_action) == actions
                and c.scope == scope):
            if not prospectively_declared:
                return _cc(BLOCKED, c,
                           f"same mechanism and same environment as "
                           f"{c.mechanism_id} with only the thresholds moved, "
                           f"and declared AFTER its result was known",
                           ignored)
            return _cc(RESURRECTION_TAX, c,
                       f"same rule shape as {c.mechanism_id} at different "
                       f"thresholds — admissible only as a pre-declared "
                       f"descendant carrying the parent corpse as control, and "
                       f"its evidence bar rises with the count of attempts "
                       f"(SS20)",
                       ignored)

    parents = [c for c in relevant
               if rule_shape(c.precursor) == rule_shape(precursor)
               or (c.proposed_action, c.default_action) == actions]
    if parents and not prospectively_declared:
        return _cc(BLOCKED, parents[0],
                   f"a descendant of {parents[0].mechanism_id} declared after "
                   f"seeing its results is not a new hypothesis — it is the "
                   f"same search, re-scored",
                   ignored)

    return _cc(ALLOWED_WITH_PARENT_CONTROL, parents[0] if parents else None,
               ("mechanistically distinct from every CLOSING corpse"
                + (f"; {parents[0].mechanism_id} is a mandatory control"
                   if parents else "")),
               ignored)


def _cc(outcome: str, parent: Corpse | None, reason: str,
        ignored: Sequence[Corpse]) -> dict:
    return {
        "outcome": outcome,
        "parent": None if parent is None else parent.mechanism_id,
        "parent_control_required": outcome != BLOCKED and parent is not None,
        "reason": reason,
        # Named, not merely dropped. A corpse that stopped blocking is a fact
        # about the register that somebody has to be able to audit.
        "corpses_that_block_nothing": [
            {"id": c.mechanism_id, "verdict": c.verdict, "scope": c.scope}
            for c in ignored],
        "note": ("only REFUTED_IN_SCOPE and STRUCTURALLY_CLOSED can block, and "
                 "the first blocks only inside its own scope"),
    }


def _default_revisit(cell: ScopedCell) -> str:
    """A concrete resurrection condition, computed rather than boilerplate.

    Where the cell is unpowered the honest condition is a sample size, and the
    sample size is derivable: to detect the effect actually observed, n_effective
    must grow by roughly (mde / effect)^2.
    """
    if cell.mean_pp and cell.mde_pp and abs(cell.mean_pp) > 0:
        need = (cell.mde_pp / abs(cell.mean_pp)) ** 2
        if cell.n_effective:
            return (f"n_effective on this slice reaches about "
                    f"{cell.n_effective * need:.0f} (currently "
                    f"{cell.n_effective:.1f}) — enough to resolve an effect the "
                    f"size of the one observed")
    return ("this environment recurs often enough to carry an MDE, or the "
            "corpus gains the features this slice is missing")
