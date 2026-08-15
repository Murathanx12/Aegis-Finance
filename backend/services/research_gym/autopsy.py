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

    def fires_on(self, state: dict) -> bool:
        return compile_precursor(self.executable_precursor,
                                 vocabulary=self.vocabulary)(state)

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
        verdict = ("DEAD — the mechanism was run outside the episodes that "
                   "generated it and never fired, so it explains its parent "
                   "and nothing else")
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
                 "verdict": verdict},
        n_episodes=len(tt.tested_episode_ids)), path=ledger_path)

    return {
        "mechanism": autopsy.proposed_mechanism,
        "episode_id": autopsy.episode_id,
        "verdict": verdict,
        "exportable": report["exportable"] and not never_fired,
        "missing": report["missing"],
        "n_fired_outside_parent": n_fired,
        "n_unevaluable": n_unevaluable,
        "was_actually_run": ran_anywhere,
        "slices": {k: r.as_dict() for k, r in results.items()},
        "transfer_clean": tt.is_clean(),
        "citable": False,
    }
