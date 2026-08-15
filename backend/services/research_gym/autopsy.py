"""AUTOPSY-TO-RULE-1 — turn one resolved decision into a rule that must travel.

THE MOVE THIS MAKES
===================
A failure taxonomy says *where* a decision went wrong. That is a label, and a
label does not generalise. The autopsy asks the next question — *what would have
had to be true about the world for this to be a repeatable mistake rather than
one bad afternoon* — and it demands the answer in a form that can be checked
somewhere else.

So an autopsy is not an explanation. It is a **hypothesis with a bill attached**:
a precursor that can be evaluated on any episode, states where the mechanism
must show up, states where it must NOT, a falsifier, and a rival explanation
that gets tested alongside it.

WHY THE OUTPUT IS A TYPE AND NOT A PARAGRAPH
============================================
Optimus is allowed to see the outcome while performing an autopsy — it has to,
that is what an autopsy is. The cost of that permission is that hindsight leaks
into the prose in ways nobody can audit: "the market was clearly capitulating"
is contemporaneous or post-hoc depending entirely on a fact the sentence does
not carry.

`Autopsy` therefore keeps `contemporaneous_evidence` and `post_outcome_evidence`
in **separate fields**, and the rule built from it may only use the first. That
is checkable. A paragraph is not.

THE THREE REFUSALS
==================
1. **A mechanism that names no unaffected states is refused.** "Extreme stress
   is followed by recovery" with no declared place it should fail is not a
   hypothesis; it is a mood. The unaffected list is the half that makes the
   affected list mean something.
2. **A precursor that is not executable is refused.** Free text cannot be run
   against 10,000 other episodes, and a rule that cannot be run against other
   episodes can never leave the Gym.
3. **The parent episode may not prove the rule** — wired through
   `TransferTest`/`request_export` mechanically here, not by convention. A rule
   that fires only on the episodes that generated it DIES, and the death is
   ledgered rather than silently dropped, because a search whose failures go
   unrecorded reports a multiple-comparison count that understates (SS20).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from backend.services.research_gym import charter as CH
from backend.services.research_gym import power as PW
from backend.services.research_gym import scope as SC

#: The closed vocabulary a precursor may be written in. Closed on purpose: an
#: `eval`-based predicate would accept anything, including a predicate that
#: reads the outcome. Every operator here is a comparison against a value the
#: episode legally knew at decision time.
OPS: dict[str, Callable[[Any, Any], bool]] = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}

#: Keys a precursor may never read. These are outcome fields; a precursor that
#: reads one is not a precursor, it is a description of what happened.
FORBIDDEN_FEATURES = frozenset({
    "realised_return_pct", "outcome", "resolved_at", "forward_return",
    "regret", "failure_mode", "evidence_strength",
})

#: THE SHARED VOCABULARY. A precursor may only read features that BOTH the
#: autopsied episodes and the transfer corpus can supply.
#:
#: This exists because of what happened on the first real run (2026-08-15). The
#: model wrote precursors over `sp500_1m_return_pct` — a perfectly reasonable
#: feature, present on every dataset-zero episode. The transfer probes carried
#: `vix` and `drawdown_pct`. Every mechanism came back "DEAD, never fires
#: outside its parent", which was false: they were never RUN.
#:
#: The lesson is not "count unevaluable episodes" — that is the symptom, and it
#: is now counted. It is that a rule written in a vocabulary the test corpus
#: does not speak is untestable BY CONSTRUCTION, and the only place to catch
#: that cheaply is when the rule is built.
TRANSFERABLE_FEATURES = frozenset({
    "vix", "vix_bucket",
    "drawdown_pct",          # % below the trailing 252d high, negative
    "ret_1m_pct", "ret_3m_pct", "ret_6m_pct",
    "realised_vol_20d",      # annualised, %
    "vol_ratio_20_60",       # short-window vol / long-window vol
    "security",
})


class PrecursorRefused(ValueError):
    """The precursor cannot be executed, or reads something it must not."""


class VocabularyRefused(PrecursorRefused):
    """A precursor written in words the transfer corpus does not speak."""


class AutopsyRefused(ValueError):
    """The autopsy is not falsifiable enough to be worth testing."""


def compile_precursor(spec: dict, *,
                      vocabulary: frozenset[str] | None = None
                      ) -> Callable[[dict], bool]:
    """Turn a declared precursor into a callable over an episode's STATE.

    Grammar (deliberately tiny):

        {"all": [clause, ...]}   every clause must hold
        {"any": [clause, ...]}   at least one must hold
        {"not": clause}
        clause = {"feature": str, "op": str, "value": Any}

    A missing feature raises rather than evaluating False. That distinction is
    the whole reason this is not a `dict.get` chain: a precursor that silently
    returns False on a typo produces a mechanism that never fires, which reads
    on every report as "tested and did not transfer" when it was never run.
    """
    if not isinstance(spec, dict) or not spec:
        raise PrecursorRefused("a precursor must be a non-empty dict")

    if "all" in spec or "any" in spec:
        key = "all" if "all" in spec else "any"
        parts = spec[key]
        if not isinstance(parts, (list, tuple)) or not parts:
            raise PrecursorRefused(f"{key!r} needs at least one clause")
        subs = [compile_precursor(p, vocabulary=vocabulary) for p in parts]
        agg = all if key == "all" else any
        return lambda state: agg(f(state) for f in subs)

    if "not" in spec:
        inner = compile_precursor(spec["not"], vocabulary=vocabulary)
        return lambda state: not inner(state)

    feat, op, val = spec.get("feature"), spec.get("op"), spec.get("value")
    if not isinstance(feat, str) or not feat:
        raise PrecursorRefused(f"clause {spec!r} names no feature")
    if feat in FORBIDDEN_FEATURES:
        raise PrecursorRefused(
            f"{feat!r} is an OUTCOME field. A precursor that reads the outcome "
            f"is not a precursor — it will fire on exactly the episodes that "
            f"already happened and transfer to nothing")
    if vocabulary is not None and feat not in vocabulary:
        raise VocabularyRefused(
            f"{feat!r} is not in the transferable vocabulary "
            f"{sorted(vocabulary)}. A rule written over a feature the transfer "
            f"corpus cannot supply is untestable BY CONSTRUCTION — it would "
            f"run, evaluate nothing, and be reported as a mechanism that "
            f"failed to transfer")
    if op not in OPS:
        raise PrecursorRefused(
            f"unknown operator {op!r}; the vocabulary is {sorted(OPS)} and it "
            f"is closed so a precursor cannot become arbitrary code")
    fn = OPS[op]

    def _run(state: dict) -> bool:
        if feat not in state:
            raise PrecursorRefused(
                f"episode state has no {feat!r}; evaluating this as False "
                f"would report an untested mechanism as a failed one")
        v = state[feat]
        if v is None:
            # UNMEASURED IS NOT ZERO AND NOT FALSE.
            #
            # An episode early in a series has no 60-day realised volatility
            # yet. The first version of the corpus filled that with 0.0, so a
            # rule reading `realised_vol_20d < 5` fired on every one of them
            # for a reason that had nothing to do with volatility. `None` is
            # now carried through and refused here, which turns a silently
            # wrong answer into a counted unevaluable episode.
            raise PrecursorRefused(
                f"{feat!r} is None on this episode — the feature was not "
                f"measurable here. Treating that as a value would make the "
                f"rule fire (or not) for a reason unrelated to the feature")
        return bool(fn(v, val))

    return _run


@dataclass(frozen=True)
class Autopsy:
    """One resolved episode, dissected into something that can be tested.

    Every field is required to be non-trivial. An autopsy with an empty
    falsifier or no rival explanation is not a cheap autopsy, it is a
    non-autopsy, and admitting it would let the count of "mechanisms generated"
    grow without the count of testable things growing with it.
    """
    episode_id: str
    #: Facts knowable AT the decision. Only these may appear in the precursor.
    contemporaneous_evidence: list[str]
    #: Facts knowable only afterwards. Kept, because the autopsy genuinely used
    #: them — and kept SEPARATE, so the rule can be audited for leaning on them.
    post_outcome_evidence: list[str]
    failed_assumption: str
    proposed_mechanism: str
    #: Executable, in the grammar above.
    executable_precursor: dict
    expected_affected_states: list[str]
    #: The discriminating half. A mechanism with no declared null territory
    #: cannot be wrong anywhere, which means it cannot be right anywhere either.
    expected_unaffected_states: list[str]
    falsifier: str
    alternative_explanation: str
    #: THE DISCRIMINATING HALF, MADE EXECUTABLE.
    #:
    #: `expected_affected_states` / `expected_unaffected_states` above are prose,
    #: and prose is exactly what the machinery could not test — it required
    #: them, validated them, wrote them to the lineage row, and then adjudicated
    #: on a flat slice count that had no idea they existed.
    #:
    #: These two predicates are the same declarations in the closed grammar, so
    #: every episode can be labelled AFFECTED / UNAFFECTED / OUT_OF_SCOPE from
    #: the FROZEN declaration before a single number is computed. That ordering
    #: is what makes the labels unchoosable after the fact.
    #:
    #: `None` is permitted only for pre-scope autopsies being replayed; they
    #: adjudicate exactly as before and are reported as unscoped.
    affected_precursor: dict | None = None
    unaffected_precursor: dict | None = None
    #: The action the mechanism recommends where it fires — a policy name from
    #: the declared menu, so the transfer test can actually run it.
    proposed_action: str = "hold"
    #: THE INCUMBENT the mechanism proposes to replace, pre-declared and never
    #: chosen after seeing the result. For dataset zero that is `sell_100`: the
    #: question the whole exercise asks is *we sold — what if we had held?*, and
    #: the answer is only a number if both halves are named in advance.
    default_action: str = "sell_100"
    minimum_transfer_slices: int = CH.MIN_TRANSFER_SLICES
    author: str = ""
    #: Features the precursor is allowed to read. `None` disables the check,
    #: which is only correct when the caller has already guaranteed the corpus
    #: speaks the same language.
    vocabulary: frozenset[str] | None = TRANSFERABLE_FEATURES

    def __post_init__(self) -> None:
        for name in ("failed_assumption", "proposed_mechanism", "falsifier",
                     "alternative_explanation"):
            if not str(getattr(self, name) or "").strip():
                raise AutopsyRefused(
                    f"{name} is empty. An autopsy without a {name} produces a "
                    f"mechanism that cannot be argued with, and one that cannot "
                    f"be argued with cannot be tested either")
        if not self.expected_affected_states:
            raise AutopsyRefused("no states where the mechanism should appear")
        if not self.expected_unaffected_states:
            raise AutopsyRefused(
                "no states where the mechanism should be ABSENT. A mechanism "
                "that predicts every state predicts nothing, and the absent "
                "list is the half that makes the present list falsifiable")
        if self.proposed_action == self.default_action:
            raise AutopsyRefused(
                f"proposed_action and default_action are both "
                f"{self.proposed_action!r}, so the mechanism's edge is zero by "
                f"construction on every slice. It would run, report 0.00pp "
                f"everywhere, and be recorded as tested — the most expensive "
                f"kind of null, because it looks like a measurement")
        overlap = (set(self.expected_affected_states)
                   & set(self.expected_unaffected_states))
        if overlap:
            raise AutopsyRefused(
                f"{sorted(overlap)} are declared both affected and unaffected — "
                f"a prediction that resolves either way is not a prediction")
        # Compiles IN THE SHARED VOCABULARY, or the autopsy does not exist.
        compile_precursor(self.executable_precursor,
                          vocabulary=self.vocabulary)
        for name in ("affected_precursor", "unaffected_precursor"):
            spec = getattr(self, name)
            if spec is not None:
                compile_precursor(spec, vocabulary=self.vocabulary)
        if (self.affected_precursor is None) != (self.unaffected_precursor
                                                 is None):
            raise AutopsyRefused(
                "affected_precursor and unaffected_precursor must be declared "
                "together. One without the other gives an adjudicator a region "
                "to score and no region to control it against, which is the "
                "flat slice count this replaced")

    @property
    def is_scoped(self) -> bool:
        return self.affected_precursor is not None

    def fires_on(self, state: dict) -> bool:
        return compile_precursor(self.executable_precursor,
                                 vocabulary=self.vocabulary)(state)

    def scope_of(self, state: dict) -> str:
        """Label one episode from the FROZEN declaration.

        Raises `PrecursorRefused` when the state cannot be evaluated, for the
        same reason `fires_on` does: an unevaluable episode is not an episode
        outside the mechanism's scope, and collapsing the two is how fifteen
        never-run cells were reported DEAD.

        An episode matching BOTH declarations is `OUT_OF_SCOPE`, not a coin
        toss — the declaration is self-contradictory there, and the contradiction
        is counted and surfaced rather than resolved by whichever check ran
        first.
        """
        if not self.is_scoped:
            return SC.OUT_OF_SCOPE
        a = compile_precursor(self.affected_precursor,
                              vocabulary=self.vocabulary)(state)
        u = compile_precursor(self.unaffected_precursor,
                              vocabulary=self.vocabulary)(state)
        if a and not u:
            return SC.AFFECTED
        if u and not a:
            return SC.UNAFFECTED
        return SC.OUT_OF_SCOPE

    def declaration_conflicts_on(self, state: dict) -> bool:
        """True where the two declarations both fire — an incoherent scope."""
        if not self.is_scoped:
            return False
        return bool(
            compile_precursor(self.affected_precursor,
                              vocabulary=self.vocabulary)(state)
            and compile_precursor(self.unaffected_precursor,
                                  vocabulary=self.vocabulary)(state))

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["citable"] = False
        d["note"] = ("Gym autopsy. A hypothesis with a bill attached, not a "
                     "result. R2 wall 1.")
        return d


# ── the transfer test, with the parent barred mechanically ──────────────────

@dataclass
class SliceResult:
    """What the mechanism did on one slice that did not generate it."""
    slice_key: str
    n_episodes: int
    n_fired: int
    mean_edge_pp: float | None
    se_pp: float | None
    t_stat: float | None
    mde_pp: float | None
    n_effective: float | None
    passed: bool
    reason: str
    #: Episodes whose state could not be evaluated at all. Reported separately
    #: from `n_fired` because "the mechanism did not fire" and "the mechanism
    #: was never run" are different facts that produce the same zero.
    n_unevaluable: int = 0

    @property
    def was_actually_run(self) -> bool:
        return self.n_unevaluable == 0

    def as_dict(self) -> dict:
        return {"slice": self.slice_key, "n_episodes": self.n_episodes,
                "n_fired": self.n_fired,
                "n_unevaluable": self.n_unevaluable,
                "was_actually_run": self.was_actually_run,
                "mean_edge_pp": (None if self.mean_edge_pp is None
                                 else round(self.mean_edge_pp, 3)),
                "se_pp": None if self.se_pp is None else round(self.se_pp, 3),
                "t": None if self.t_stat is None else round(self.t_stat, 3),
                "mde_pp": None if self.mde_pp is None else round(self.mde_pp, 3),
                "n_effective": self.n_effective,
                "passed": self.passed, "reason": self.reason}


def _edge(surface, proposed: str, default: str) -> float | None:
    """Net return of the proposed action minus the pre-declared default.

    Read off the stored surface rather than recomputed, so the transfer test
    and the episode record cannot disagree about what a policy returned.
    """
    a, b = surface.results.get(proposed), surface.results.get(default)
    if a is None or b is None:
        return None
    return a.net_return_pct - b.net_return_pct


def evaluate_slice(autopsy: Autopsy, records: Sequence[tuple], slice_key: str,
                   *, horizon_days: int = 63) -> SliceResult:
    """Run the mechanism on one slice. Passing requires clearing its own MDE.

    `records` are `(episode, surface)` pairs. The edge is measured only on the
    episodes where the precursor FIRES, against the pre-declared default — the
    same three-denominator discipline the Gym now applies everywhere, because a
    mechanism validated against the best-of-menu would inherit G1 wholesale.
    """
    fired, unevaluable = [], 0
    for ep, surface in records:
        try:
            if not autopsy.fires_on(ep.state):
                continue
        except PrecursorRefused:
            # A state that cannot be EVALUATED is not a state where the
            # mechanism did not fire.
            #
            # THIS DISTINCTION WAS COLLAPSED ON THE FIRST REAL RUN, 2026-08-15.
            # The model wrote precursors reading `sp500_1m_return_pct`; the
            # transfer probes carried only `vix` and `drawdown_pct`; every
            # lookup raised, every raise was swallowed as `continue`, and all
            # three mechanisms were reported "DEAD — never fires outside its
            # parent". Confident, plausible, and wrong — and wrong in the
            # direction that LOOKS rigorous, which is the hardest direction to
            # notice. Counting them is the fix.
            unevaluable += 1
            continue
        e = _edge(surface, autopsy.proposed_action, autopsy.default_action)
        if e is not None:
            fired.append(e)

    n = len(fired)
    if unevaluable and n == 0:
        return SliceResult(
            slice_key, len(records), 0, None, None, None, None, None, False,
            f"UNEVALUABLE — {unevaluable} of {len(records)} episodes on this "
            f"slice do not carry the features this precursor reads, so the "
            f"mechanism was never RUN here. This is not a refutation and must "
            f"not be counted as one",
            n_unevaluable=unevaluable)
    if n == 0:
        return SliceResult(slice_key, len(records), 0, None, None, None, None,
                           None, False,
                           "the precursor never fired on this slice — untested "
                           "here, which is not the same as refuted here",
                           n_unevaluable=unevaluable)

    import statistics
    mean = statistics.fmean(fired)
    sd = statistics.stdev(fired) if n > 1 else None
    # Episodes inside a slice overlap in time far less than daily windows do,
    # but they are not independent either; the count is shrunk by the horizon
    # only when the slice is dense enough for that to bite.
    n_eff = PW.effective_n(n, 1)
    se = (sd / (n ** 0.5)) if sd else None
    mde = PW.mde_mean(sd, n_eff) if sd else None
    t = (mean / se) if se else None

    if mde is None:
        return SliceResult(slice_key, len(records), n, mean, se, t, mde, n_eff,
                           False,
                           f"n={n} on this slice carries no MDE — below the "
                           f"floor at which a pass could mean anything (SS19)")
    passed = bool(mean > 0 and abs(mean) >= mde)
    return SliceResult(
        slice_key, len(records), n, mean, se, t, mde, n_eff, passed,
        (f"edge {mean:+.2f}pp vs its own MDE {mde:.2f}pp on n={n}"
         + ("" if passed else " — below its own MDE, which is NOT a refutation, "
                              "it is an undetectable test (SS19)")))


def run_transfer(autopsy: Autopsy, records_by_slice: dict[str, Sequence[tuple]],
                 *, origin_episode_ids: Iterable[str] | None = None
                 ) -> tuple[CH.TransferTest, dict[str, SliceResult]]:
    """Test the mechanism everywhere EXCEPT where it came from.

    The exclusion is performed here rather than trusted to the caller. That is
    the entire point of wiring the wall mechanically: "remember not to include
    the parent" is a rule that holds until the one time it does not, and the
    failure is invisible because the contaminated result looks stronger.
    """
    origins = set(origin_episode_ids or [autopsy.episode_id])
    cleaned: dict[str, list[tuple]] = {}
    excluded = 0
    for key, recs in records_by_slice.items():
        keep = []
        for ep, s in recs:
            if ep.episode_id in origins:
                excluded += 1
                continue
            keep.append((ep, s))
        cleaned[key] = keep

    results = {k: evaluate_slice(autopsy, v, k) for k, v in cleaned.items()}
    tested_ids = [ep.episode_id for recs in cleaned.values() for ep, _ in recs]
    tt = CH.TransferTest(
        mechanism=autopsy.proposed_mechanism,
        origin_episode_ids=sorted(origins),
        tested_episode_ids=tested_ids,
        slices=sorted(results),
        result_by_slice={k: r.as_dict() | {"passed": r.passed}
                         for k, r in results.items()})
    return tt, results


# ── scope-aware measurement (P0, 2026-08-16 order §2.5) ─────────────────────

#: Probe episodes are sampled MONTHLY and graded over a 63-trading-day forward
#: window — about three months. Consecutive probes therefore share two thirds of
#: their window, so a slice's rows are worth roughly a third of their count.
PROBE_HORIZON_MONTHS = 3


def _month_index(decision_ts: str) -> int | None:
    """Calendar month as a single integer, for overlap and burst counting."""
    try:
        y, m = str(decision_ts)[:7].split("-")
        return int(y) * 12 + int(m)
    except (ValueError, AttributeError):
        return None


def _cell(slice_key: str, scope: str, edges: list[float], n_unevaluable: int,
          months: list[int] | None = None) -> SC.ScopedCell:
    """One (slice x scope) measurement, with an HONEST sample size.

    TWO CORRECTIONS, BOTH FOUND BY CHECKING THE KILLS (§37, 2026-08-16)
    ==================================================================
    The first scoped run reported five REFUTED_IN_SCOPE, every one of them
    driven by the placebo arm clearing an MDE. Before reporting a kill, the
    instrument that produced it was checked — and it could not have been right:

    1. `n_effective` was `effective_n(n, 1)`, i.e. **`n` itself**. But the
       probes are monthly draws of a ~3-month window across SIX correlated
       tickers (QQQ, IWM, XLF, XLE, XLK, EFA all move together). Counting 150
       such rows as 150 independent observations understates every MDE by more
       than a factor of three, and an understated MDE does not produce a
       neutral error — it manufactures detections, which here means it
       manufactures REFUTATIONS.

    2. `se_pp` was `sd/sqrt(n)` while `mde_pp` was computed from
       `n_effective`. The two disagreed about the sample size of the same
       number. That was invisible for exactly as long as `n_effective == n`.

    Both are corrected here: the count shrinks to distinct months divided by the
    window overlap, further shrunk by burst clustering, and the SE is computed
    from that same count so a cell's t-statistic and its MDE describe one
    sample. The SD is still estimated on every row — more rows genuinely do
    estimate dispersion better; they just do not add independent evidence.
    """
    import statistics
    n = len(edges)
    if n == 0:
        return SC.ScopedCell(slice_key, scope, 0, n_unevaluable,
                             None, None, None, None)
    mean = statistics.fmean(edges)
    sd = statistics.stdev(edges) if n > 1 else None

    if months:
        distinct = sorted(set(months))
        n_eff = PW.effective_n(
            len(distinct), PROBE_HORIZON_MONTHS,
            # A gap of one month unit: consecutive months are one burst, months
            # further apart are separate events.
            n_episodes=PW.count_episodes(distinct, gap_days=1))
    else:
        n_eff = PW.effective_n(n, 1)

    se = (sd / (n_eff ** 0.5)) if (sd and n_eff) else None
    return SC.ScopedCell(slice_key, scope, n, n_unevaluable, mean, se,
                         PW.mde_mean(sd, n_eff) if sd else None, n_eff)


def evaluate_slice_scoped(autopsy: Autopsy, records: Sequence[tuple],
                          slice_key: str) -> dict:
    """Split one slice into AFFECTED / UNAFFECTED / OUT_OF_SCOPE cells.

    THE ASYMMETRY IS INTENTIONAL, AND IT IS THE PLACEBO
    ===================================================
    In the `AFFECTED` region the edge is measured where the precursor FIRES —
    that is the mechanism's own claim.

    In the `UNAFFECTED` region the same action swap is measured on **every**
    episode, whether or not the precursor fires. That is the placebo arm: it
    asks whether `proposed_action` beats `default_action` in the very states the
    mechanism declared it should not, which is the difference between having
    found a mechanism and having found the action. Buying beats selling in calm
    markets for reasons that have nothing to do with any autopsy, and a
    hypothesis that cannot survive being asked is not conditional — it is beta
    with a story.
    """
    aff: list[float] = []
    unaff: list[float] = []
    oos: list[float] = []
    aff_m: list[int] = []
    unaff_m: list[int] = []
    oos_m: list[int] = []
    n_unevaluable = 0
    n_conflict = 0
    n_fired_in_unaffected = 0

    for ep, surface in records:
        try:
            scope = autopsy.scope_of(ep.state)
            conflict = autopsy.declaration_conflicts_on(ep.state)
            fires = autopsy.fires_on(ep.state)
        except PrecursorRefused:
            n_unevaluable += 1
            continue
        if conflict:
            n_conflict += 1
        e = _edge(surface, autopsy.proposed_action, autopsy.default_action)
        if e is None:
            continue
        mi = _month_index(getattr(ep, "decision_ts", ""))
        if scope == SC.AFFECTED:
            if fires:
                aff.append(e)
                if mi is not None:
                    aff_m.append(mi)
        elif scope == SC.UNAFFECTED:
            unaff.append(e)              # placebo: no `fires` condition
            if mi is not None:
                unaff_m.append(mi)
            if fires:
                n_fired_in_unaffected += 1
        elif fires:
            oos.append(e)
            if mi is not None:
                oos_m.append(mi)

    return {
        "cells": {
            SC.AFFECTED: _cell(slice_key, SC.AFFECTED, aff, n_unevaluable,
                               aff_m),
            SC.UNAFFECTED: _cell(slice_key, SC.UNAFFECTED, unaff,
                                 n_unevaluable, unaff_m),
            SC.OUT_OF_SCOPE: _cell(slice_key, SC.OUT_OF_SCOPE, oos,
                                   n_unevaluable, oos_m),
        },
        "n_unevaluable": n_unevaluable,
        "n_declaration_conflicts": n_conflict,
        "n_fired_inside_declared_unaffected": n_fired_in_unaffected,
    }


def adjudicate_scoped(autopsy: Autopsy,
                      records_by_slice: dict[str, Sequence[tuple]],
                      *, origin_episode_ids: Iterable[str] | None = None,
                      min_slices: int | None = None) -> dict:
    """The effect SURFACE, and a verdict that only claims what it measured.

    Returns per-slice-per-scope verdicts rather than a scalar, because a
    mechanism may be positive in one state and negative in another and that is
    allowed — it is, in fact, the thing the whole ruling exists to be able to
    say.
    """
    if not autopsy.is_scoped:
        raise SC.ScopeRefused(
            "this autopsy declares no executable scope, so it cannot be "
            "adjudicated by scope. Use `adjudicate` for pre-scope replays")

    k = int(min_slices if min_slices is not None
            else autopsy.minimum_transfer_slices)
    origins = set(origin_episode_ids or [autopsy.episode_id])

    per_slice: dict[str, dict] = {}
    for key, recs in records_by_slice.items():
        clean = [(ep, s) for ep, s in recs if ep.episode_id not in origins]
        per_slice[key] = evaluate_slice_scoped(autopsy, clean, key)

    # ── the effect surface ──
    surface: dict[str, dict[str, SC.ScopedVerdict]] = {}
    for key, res in per_slice.items():
        surface[key] = {sc: cell.verdict()
                        for sc, cell in res["cells"].items()}

    supported = [k2 for k2, v in surface.items()
                 if v[SC.AFFECTED].verdict == SC.SUPPORTED_IN_SCOPE]
    refuted_affected = [k2 for k2, v in surface.items()
                        if v[SC.AFFECTED].verdict == SC.REFUTED_IN_SCOPE]
    placebo_fired = [k2 for k2, v in surface.items()
                     if v[SC.UNAFFECTED].verdict == SC.REFUTED_IN_SCOPE]
    ran_anywhere = any(res["cells"][SC.AFFECTED].ran
                       for res in per_slice.values())
    powered_anywhere = any(res["cells"][SC.AFFECTED].powered
                           for res in per_slice.values())
    conflicts = sum(r["n_declaration_conflicts"] for r in per_slice.values())

    # ── §18: the interaction, pooled, tested as its own quantity ──
    def _pool(scope: str):
        """Pool across slices weighting by EFFECTIVE sample size.

        Weighting by raw `n` would hand the pooled mean to whichever slice
        happened to contain the most correlated rows — which, after the
        n_effective correction, is precisely the slice contributing least
        independent evidence.
        """
        cells = [r["cells"][scope] for r in per_slice.values()
                 if r["cells"][scope].n and r["cells"][scope].n_effective]
        if not cells:
            return None, None, None
        w = sum(c.n_effective for c in cells)
        mean = sum(c.mean_pp * c.n_effective for c in cells) / w
        var = sum((c.se_pp ** 2) * (c.n_effective ** 2)
                  for c in cells if c.se_pp)
        se = (var ** 0.5) / w if var else None
        return mean, se, float(w)

    ma, sa, na = _pool(SC.AFFECTED)
    mu, su, nu = _pool(SC.UNAFFECTED)
    inter = SC.interaction("AFFECTED - UNAFFECTED (pooled)",
                           ma, sa, na, mu, su, nu)

    # ── the overall verdict ──
    exportable = (len(supported) >= k and not placebo_fired
                  and inter.detectable and (inter.diff_pp or 0) > 0
                  and not conflicts)
    if conflicts:
        overall = SC.ScopedVerdict(
            SC.UNTESTED, "declared scope",
            (f"{conflicts} episode(s) satisfy BOTH the affected and unaffected "
             f"declarations, so the mechanism's own scope is self-contradictory "
             f"and no cell can be labelled honestly"),
            revisit_when="the two declarations are re-stated as disjoint")
    elif not ran_anywhere:
        overall = SC.ScopedVerdict(
            SC.UNTESTED, "all declared-affected slices",
            ("the precursor never fired in any declared-affected region "
             "outside its parent — it was not refuted here, it was not run"),
            revisit_when=("the transfer corpus gains episodes inside the "
                          "declared affected region"))
    elif not powered_anywhere:
        overall = SC.ScopedVerdict(
            SC.UNPOWERED_IN_SCOPE, "all declared-affected slices",
            "no affected cell carries an MDE — nothing here could resolve it",
            revisit_when="affected cells reach an effective sample carrying an MDE")
    elif exportable:
        overall = SC.ScopedVerdict(
            SC.SUPPORTED_IN_SCOPE,
            f"{len(supported)} declared-affected slice(s): {sorted(supported)}",
            (f"clears its own MDE in {len(supported)} of {k} required affected "
             f"slices, stays silent in every declared-unaffected region, and the "
             f"AFFECTED-UNAFFECTED interaction is itself detectable "
             f"({inter.diff_pp:+.2f}pp vs MDE {inter.mde_pp:.2f}pp)"),
            effect_pp=inter.diff_pp, mde_pp=inter.mde_pp)
    elif placebo_fired:
        overall = SC.ScopedVerdict(
            SC.REFUTED_IN_SCOPE,
            f"declared-unaffected regions: {sorted(placebo_fired)}",
            (f"the same action swap pays off in {len(placebo_fired)} region(s) "
             f"the mechanism declared it should be silent in. What was found is "
             f"broader than the mechanism — on this evidence it is the ACTION, "
             f"not the conditioning"),
            revisit_when=("a narrower mechanism is declared whose unaffected "
                          "region genuinely excludes these, or the interaction "
                          "is shown detectable on its own"))
    elif supported:
        overall = SC.ScopedVerdict(
            SC.TRANSFER_PENDING,
            f"{len(supported)} of {k} declared-affected slices",
            (f"survives where it said it would on {sorted(supported)}, which is "
             f"real but short of the {k} independent slices export requires"),
            revisit_when=(f"the pre-declared transfer atlas supplies "
                          f"{k - len(supported)} more independent slice(s) "
                          f"inside the declared affected region"))
    elif refuted_affected and len(refuted_affected) == len(
            [s for s in surface if per_slice[s]["cells"][SC.AFFECTED].powered]):
        overall = SC.ScopedVerdict(
            SC.REFUTED_IN_SCOPE,
            f"declared-affected slices {sorted(refuted_affected)}",
            ("a POWERED effect in the wrong direction everywhere the mechanism "
             "claimed it would work — this closes THIS rule in THESE "
             "environments and nothing wider"),
            revisit_when=("a mechanistically distinct descendant is declared "
                          "prospectively, carrying this corpse as control"))
    else:
        overall = SC.ScopedVerdict(
            SC.NOT_DETECTABLE_IN_SCOPE,
            "declared-affected slices",
            ("ran and fired, and no affected cell cleared its own MDE. SS19: "
             "the instrument could not have seen an effect this size, so this "
             "is absence of evidence"),
            revisit_when=("affected cells reach the effective sample the "
                          "observed effect sizes would need"))

    return {
        "mechanism": autopsy.proposed_mechanism,
        "episode_id": autopsy.episode_id,
        "scoped": True,
        "verdict": overall.verdict,
        "verdict_detail": overall.as_dict(),
        "exportable": exportable,
        "effect_surface": {kk: {sc: v.as_dict() for sc, v in vv.items()}
                           for kk, vv in surface.items()},
        "cells": {kk: {sc: c.as_dict()
                       for sc, c in r["cells"].items()}
                  for kk, r in per_slice.items()},
        "interaction": inter.as_dict(),
        "supported_slices": sorted(supported),
        "refuted_affected_slices": sorted(refuted_affected),
        "placebo_fired_slices": sorted(placebo_fired),
        "n_declaration_conflicts": conflicts,
        "n_unevaluable": sum(r["n_unevaluable"] for r in per_slice.values()),
        "n_fired_inside_declared_unaffected": sum(
            r["n_fired_inside_declared_unaffected"] for r in per_slice.values()),
        "slices_required": k,
        "citable": False,
    }


def adjudicate(autopsy: Autopsy, records_by_slice: dict[str, Sequence[tuple]],
               *, origin_episode_ids: Iterable[str] | None = None,
               ledger_path=None) -> dict:
    """Transfer, verdict, and a lineage row either way.

    A mechanism that explains only its parent dies here, and the death is
    WRITTEN. An unledgered death is worse than no test: the campaign's true
    multiple-comparison count silently understates, and every deflation
    computed against it is too generous (SS20).
    """
    tt, results = run_transfer(autopsy, records_by_slice,
                               origin_episode_ids=origin_episode_ids)
    report = CH.request_export(autopsy.proposed_mechanism, tt)

    # A scoped autopsy earns the scoped verdict. The flat path below still runs
    # so both numbers exist side by side — the order asks which verdicts MOVE,
    # and that question needs the old answer computed on the same data rather
    # than remembered from a report.
    scoped = None
    if autopsy.is_scoped:
        scoped = adjudicate_scoped(autopsy, records_by_slice,
                                   origin_episode_ids=origin_episode_ids)

    n_fired = sum(r.n_fired for r in results.values())
    n_unevaluable = sum(r.n_unevaluable for r in results.values())
    ran_anywhere = any(r.was_actually_run for r in results.values())
    never_fired = n_fired == 0

    # A mechanism is only DEAD if it was actually RUN and did not fire. If the
    # slices could not evaluate its precursor, the honest verdict is that the
    # test did not happen — and saying "dead" there would retire a hypothesis
    # on the strength of a schema mismatch.
    if never_fired and not ran_anywhere:
        verdict = (f"UNTESTED — the precursor reads features the transfer "
                   f"corpus does not carry ({n_unevaluable} episode(s) could "
                   f"not be evaluated). No verdict is available; this is a "
                   f"vocabulary failure, not a refutation")
    elif never_fired:
        # `DEAD` was removed here on 2026-08-16. It was the wrong word for two
        # different facts: a precursor whose conditions never OCCUR in the
        # corpus has not been refuted by the corpus, it has been missed by it —
        # and SS19 has always said that a rule which ran and fired but did not
        # clear its MDE is NOT_DETECTABLE. Emitting one blunt kill for both is
        # how 195 existing kills quietly became absence-of-evidence.
        verdict = (f"{SC.UNTESTED} — the mechanism ran outside its parent and "
                   f"its precursor's conditions never occurred there, so the "
                   f"corpus never presented it with a chance to be wrong. "
                   f"Revisit when the transfer atlas supplies episodes inside "
                   f"the declared region")
    else:
        verdict = report["verdict"]

    CH.record_lineage(CH.LineageRow(
        candidate_id=f"autopsy:{autopsy.episode_id}",
        campaign=CH.CAMPAIGN,
        hypothesis=autopsy.proposed_mechanism,
        parent_id=autopsy.episode_id,
        parent_failure=autopsy.failed_assumption,
        params={"precursor": autopsy.executable_precursor,
                "proposed_action": autopsy.proposed_action,
                "default_action": autopsy.default_action,
                "affected": autopsy.expected_affected_states,
                "unaffected": autopsy.expected_unaffected_states},
        fitness={"slices_passed": report["slices_passed"],
                 "slices_required": report["slices_required"],
                 "n_fired_outside_parent": n_fired,
                 "n_unevaluable": n_unevaluable,
                 "was_actually_run": ran_anywhere,
                 "verdict": verdict,
                 # Both, always. A lineage row that recorded only the scoped
                 # verdict would make the migration unauditable in exactly the
                 # way SS20 warns about.
                 "flat_verdict": verdict,
                 "scoped_verdict": (None if scoped is None
                                    else scoped["verdict"]),
                 "scoped_interaction": (None if scoped is None
                                        else scoped["interaction"])},
        n_episodes=len(tt.tested_episode_ids)), path=ledger_path)

    return {
        "mechanism": autopsy.proposed_mechanism,
        "episode_id": autopsy.episode_id,
        "verdict": (scoped["verdict"] if scoped else verdict),
        "flat_verdict": verdict,
        "scoped": scoped,
        "exportable": (scoped["exportable"] if scoped
                       else (report["exportable"] and not never_fired)),
        "missing": report["missing"],
        "n_fired_outside_parent": n_fired,
        "n_unevaluable": n_unevaluable,
        "was_actually_run": ran_anywhere,
        "slices": {k: r.as_dict() for k, r in results.items()},
        "transfer_clean": tt.is_clean(),
        "citable": False,
    }
