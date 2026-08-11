"""
Recommendation engine — the registry decides what may LEAD a BUY ranking
=========================================================================

The defect this file closes
---------------------------

BUILD-1.2 printed `EVIDENCE CONFLICT (HIGH)` on every brief and was right. The
PM's candidate order was produced by this chain::

    implied_upside -> expected_return.mu -> certainty_equivalent -> sort

Every link after the first is a positive, per-name monotone transform, so the
order of the BUY list was monotone in `implied_upside`. That is
`analyst_target_upside_xs`: graded PERVERSE/CLOSED, measured at **-8 to -18%/yr
gross** over 21 years of PIT IBES (ANALYST-IBES-1, 2026-08-11). The closed
signal was ranking the book under the name of its RISK_INPUT cousin
`analyst_target_level_haircut`.

The distinction that fixes it
-----------------------------

Using an analyst target LEVEL to set a per-name haircut, cap or size discount
is a RISK_INPUT, and the registry permits it. Using that level's
CROSS-SECTIONAL ORDER to decide which name outranks which IS the closed signal,
whatever it is called. This module separates the two *by construction*:

* only signals the registry `permits(..., "PICKER")` carry `rank_bearing=True`,
  and only rank-bearing contributions may enter `ranking_score`;
* FILTER signals apply a **bounded** penalty — they may adjust at the margin
  but may never be the largest contributor to any name's score;
* RISK_INPUT and CLOSED signals are computed, printed, and forced to exactly
  zero rank influence. They act only on SIZE, after the order is already fixed.

The enforcement is not a convention. `rank_invariance()` re-ranks with a
signal's values permuted across names and requires Spearman rho == 1.0: a
signal that cannot reorder the list cannot lead it. `audit_leadership()` is the
permanent invariant the brief keeps printing. Both have tests that fail if a
closed signal ever leads.

What this module refuses to do
------------------------------

It does not invent an expected return. The PICKER signals are SUPPORTED, not
VALIDATED, and no calibrated map from picker composite to 12-month expected
return exists in this programme. So `expected_return` is None and
`expected_return_basis` says `NOT_CALIBRATED`, and the page prints a ranking
score with a percentile instead. `reliability_weight` is a bounded confidence
multiplier; it is not, and may not be read as, an expected return.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from backend import config
from backend.services import signal_registry as registry_mod

logger = logging.getLogger(__name__)

#: Ceiling on how much of a name's score a FILTER-role signal may move. A
#: filter that can swing the score more than this is a picker wearing a filter's
#: badge, which is the exact failure this module exists to prevent.
FILTER_PENALTY_CAP = 0.40

#: Rank-bearing contributions are z-scored across the candidate set and then
#: squashed, so one wild outlier cannot own the whole ranking. Bounded in
#: [-Z_CLIP, +Z_CLIP] before weighting.
Z_CLIP = 3.0

#: Evidence grades in descending order of how much the programme trusts them.
_GRADE_ORDER = ["VALIDATED", "SUPPORTED", "SHELF", "OBSERVATIONAL",
                "HYPOTHESIS", "REJECTED", "PERVERSE"]


class RankLeadershipError(RuntimeError):
    """A signal that may not lead the BUY ranking was leading it.

    Not recoverable by retrying: the ranking that produced it is void.
    """


@dataclass
class SignalContribution:
    """One signal's reading on one name, and what it was ALLOWED to do with it."""

    signal_id: str
    role: str                       # registry permitted_role
    grade: str                      # registry evidence_grade
    raw_value: Optional[float]      # what the data said, before any gating
    weight: float                   # registry reliability weight, bounded [0,1]
    contribution: float             # what actually entered ranking_score
    rank_bearing: bool              # may this signal move the ORDER at all?
    basis: str                      # why it contributed what it did
    available: bool = True
    missing_reason: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Recommendation:
    """The full decomposition for one name. Every field is printed, none implied."""

    ticker: str
    rank: int = 0
    recommendation: str = "HOLD"
    ranking_score: float = 0.0
    percentile: Optional[float] = None

    # Expected return is None unless a CALIBRATED map exists. See module docstring.
    expected_return: Optional[float] = None
    expected_return_low: Optional[float] = None
    expected_return_high: Optional[float] = None
    expected_return_basis: str = "NOT_CALIBRATED"

    confidence: str = "LOW"
    evidence_grade: str = "OBSERVATIONAL"
    signal_contributions: list[SignalContribution] = field(default_factory=list)
    positive_catalysts: list[str] = field(default_factory=list)
    negative_catalysts: list[str] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)
    kill_condition: str = ""
    kill_condition_status: str = "NONE_SET"
    position_size_candidate: Optional[float] = None
    size_caps_applied: list[str] = field(default_factory=list)
    reason_for_rank: str = ""
    better_alternatives: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    price: Optional[float] = None
    sector: str = ""
    market_cap: Optional[float] = None

    def leader(self) -> Optional[SignalContribution]:
        """The signal that decided this name's place in the order.

        Keyed on "was this signal allowed to rank AND did it have data", not on
        a nonzero contribution: the name sitting exactly at the cross-sectional
        mean scores 0.0 and is still ranked by the signal that put it there.
        """
        ranked = [c for c in self.signal_contributions
                  if c.rank_bearing and c.available]
        if not ranked:
            return None
        return max(ranked, key=lambda c: abs(c.contribution))

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["signal_contributions"] = [c.to_dict() for c in self.signal_contributions]
        lead = self.leader()
        d["rank_led_by"] = lead.signal_id if lead else None
        return d


# ──────────────────────── signal adapters ────────────────────────────────────
#
# Each adapter names the candidate field that feeds a registered signal and what
# a missing reading MEANS. A signal that cannot be read is recorded as
# unavailable with a reason — never silently dropped, never defaulted to a
# neutral value that looks like evidence. (Silent fragility is the house
# failure mode: a collector that returns nothing must not look like a collector
# that returned "fine".)

@dataclass(frozen=True)
class _Adapter:
    signal_id: str
    field_name: str
    higher_is_better: bool
    missing_reason: str


_ADAPTERS: tuple[_Adapter, ...] = (
    _Adapter("profitability_small", "quality", True,
             "no gross-profit/assets reading (fundamentals fetch returned nothing)"),
    _Adapter("insider_opportunistic", "insider_score", True,
             "no insider signal wired into the funnel candidate yet"),
    _Adapter("fusion_insider_profitability", "fusion_score", True,
             "fusion signal needs both insider and profitability legs"),
    _Adapter("low_volatility", "vol_annual", False,
             "no annualised volatility (price history too short)"),
    _Adapter("short_interest_level", "short_interest", False,
             "short interest not wired into the funnel candidate yet"),
    _Adapter("earnings_surprise_monthly", "earnings_surprise", True,
             "earnings surprise not wired into the funnel candidate yet"),
    _Adapter("rating_drift_3m", "rating_drift_3m", True,
             "no 3-month rating drift"),
    # Computed and printed, structurally barred from the order:
    _Adapter("analyst_target_level_haircut", "analyst_upside", True,
             "no consensus target"),
    _Adapter("analyst_target_upside_xs", "analyst_upside", True,
             "no consensus target"),
    _Adapter("momentum_12_1", "mom_12_1", True,
             "no 12-1 momentum (price history too short)"),
)


def _get(cand: Any, name: str) -> Optional[float]:
    if isinstance(cand, dict):
        v = cand.get(name)
    else:
        v = getattr(cand, name, None)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _ticker(cand: Any) -> str:
    return (cand.get("ticker") if isinstance(cand, dict)
            else getattr(cand, "ticker", "")) or ""


def cap_band(market_cap: Optional[float]) -> Optional[str]:
    """'small' | 'mid' | 'large', or None when the cap is unknown."""
    if market_cap is None or not math.isfinite(market_cap) or market_cap <= 0:
        return None
    if market_cap <= config.SIGNAL_UNIVERSE_SMALL_MAX_USD:
        return "small"
    if market_cap <= config.SIGNAL_UNIVERSE_MID_MAX_USD:
        return "mid"
    return "large"


def in_universe(signal: registry_mod.Signal,
                market_cap: Optional[float]) -> tuple[bool, str]:
    """May this signal be applied to a name of this size?

    The registry has always recorded the universe each signal was MEASURED in.
    Nothing enforced it until NIGHT-10, and the cost was concrete:
    `profitability_small`, whose own entry reads "Net-dead in large/mid", was
    the leading contributor to NVDA, AAPL and META in the opportunity funnel.
    Applying a signal outside the segment it was supported in is the same
    defect as ranking on a closed one — evidence borrowed from somewhere it
    was measured NOT to hold.

    Unknown universe strings and unknown market caps both resolve to "no", for
    the same reason `reliability_weight: null` resolves to UNCALIBRATED rather
    than to 1.0: not knowing is not permission.
    """
    allowed = config.SIGNAL_UNIVERSE_BANDS.get((signal.universe or "").strip())
    if allowed is None:
        return False, (f"universe {signal.universe!r} is not a recognised band, "
                       f"so this signal has no licensed segment")
    band = cap_band(market_cap)
    if band is None:
        return False, "market cap unknown, so the licensed segment cannot be checked"
    if band not in allowed:
        return False, (f"measured in {signal.universe} ({'/'.join(sorted(allowed))}); "
                       f"this name is {band}-cap — out of the licensed universe")
    return True, f"{band}-cap, inside {signal.universe}"


def _zscores(values: list[Optional[float]]) -> list[Optional[float]]:
    """Cross-sectional z-score, clipped. None passes through as None."""
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return [None if v is None else 0.0 for v in values]
    mu = sum(present) / len(present)
    var = sum((v - mu) ** 2 for v in present) / (len(present) - 1)
    sd = math.sqrt(var)
    if sd <= 0:
        return [None if v is None else 0.0 for v in values]
    return [None if v is None
            else max(-Z_CLIP, min(Z_CLIP, (v - mu) / sd)) for v in values]


def _spearman(a: list[float], b: list[float]) -> float:
    """Rank correlation. Used only to prove a signal CANNOT reorder — never to
    corroborate a money result (NIGHT-9 standing constraint)."""
    n = len(a)
    if n < 2:
        return 1.0

    def ranks(xs: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: xs[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = math.sqrt(sum((ra[i] - ma) ** 2 for i in range(n)))
    db = math.sqrt(sum((rb[i] - mb) ** 2 for i in range(n)))
    if da <= 0 or db <= 0:
        return 1.0
    return num / (da * db)


# ────────────────────────────── the ranking ──────────────────────────────────

def score_candidates(candidates: Iterable[Any],
                     *, registry: Optional[registry_mod.Registry] = None,
                     ) -> list[Recommendation]:
    """Rank candidates using ONLY signals the registry permits as PICKERs.

    Returns one `Recommendation` per candidate, sorted best-first. The order is
    a function of rank-bearing contributions alone; every other signal is read,
    printed and given exactly zero influence on it.
    """
    reg = registry or registry_mod.load()
    cands = list(candidates)
    if not cands:
        return []

    # 1. read every adapter across the whole cross-section at once — z-scoring
    #    is a cross-sectional operation and cannot be done name by name.
    raw: dict[str, list[Optional[float]]] = {}
    for ad in _ADAPTERS:
        raw[ad.signal_id] = [_get(c, ad.field_name) for c in cands]

    zed: dict[str, list[Optional[float]]] = {}
    for ad in _ADAPTERS:
        vals = raw[ad.signal_id]
        z = _zscores(vals)
        if not ad.higher_is_better:
            z = [None if v is None else -v for v in z]
        zed[ad.signal_id] = z

    # 2. build each name's decomposition
    recs: list[Recommendation] = []
    for i, c in enumerate(cands):
        contribs: list[SignalContribution] = []
        picker_sum = 0.0
        filter_penalty = 0.0

        for ad in _ADAPTERS:
            try:
                sig = reg.get(ad.signal_id)
            except registry_mod.RegistryError:
                logger.warning("adapter references unknown signal %s", ad.signal_id)
                continue

            value, z = raw[ad.signal_id][i], zed[ad.signal_id][i]
            available = value is not None
            # The registry, not this file, decides what may move the order —
            # and only inside the segment the signal was measured in.
            licensed, universe_note = in_universe(sig, _get(c, "market_cap"))
            rank_bearing = reg.permits(ad.signal_id, "PICKER") and licensed
            w = sig.weight
            contribution = 0.0
            if reg.permits(ad.signal_id, "PICKER") and not licensed:
                contribs.append(SignalContribution(
                    signal_id=ad.signal_id, role=sig.permitted_role,
                    grade=sig.evidence_grade, raw_value=value, weight=w,
                    contribution=0.0, rank_bearing=False,
                    basis=f"PICKER, but OUT OF UNIVERSE: {universe_note}",
                    available=available,
                    missing_reason="" if available else ad.missing_reason))
                continue
            if rank_bearing and available:
                contribution = w * float(z)
                picker_sum += contribution
                basis = (f"PICKER, weight {w:.2f} x z {z:+.2f} "
                         f"= {contribution:+.3f}")
            elif sig.permitted_role == "FILTER" and sig.usable_now and available:
                # bounded penalty only, and only downward
                pen = min(FILTER_PENALTY_CAP,
                          max(0.0, -float(z)) * w * (FILTER_PENALTY_CAP / Z_CLIP))
                filter_penalty += pen
                basis = (f"FILTER, bounded penalty {pen:.3f} "
                         f"(cap {FILTER_PENALTY_CAP:.2f}); cannot lead")
            elif sig.is_closed:
                basis = (f"CLOSED/{sig.evidence_grade} — read and printed, "
                         f"ZERO rank influence by construction")
            elif sig.permitted_role == "RISK_INPUT":
                basis = ("RISK_INPUT — may cap SIZE after the order is fixed; "
                         "may not order names")
            else:
                basis = f"{sig.permitted_role}/{sig.evidence_grade} — not rank-bearing"

            contribs.append(SignalContribution(
                signal_id=ad.signal_id, role=sig.permitted_role,
                grade=sig.evidence_grade, raw_value=value, weight=w,
                contribution=round(contribution, 6), rank_bearing=rank_bearing,
                basis=basis, available=available,
                missing_reason="" if available else ad.missing_reason))

        score = picker_sum - min(FILTER_PENALTY_CAP, filter_penalty)
        n_pick = sum(1 for x in contribs if x.rank_bearing and x.available)
        recs.append(Recommendation(
            ticker=_ticker(c),
            ranking_score=round(score, 6),
            signal_contributions=contribs,
            price=_get(c, "price"),
            sector=((c.get("sector") if isinstance(c, dict)
                     else getattr(c, "sector", "")) or ""),
            market_cap=_get(c, "market_cap"),
            evidence_grade=_evidence_grade(contribs),
            confidence=_confidence(n_pick, contribs),
            blocked_by=[f"{x.signal_id} is {x.grade}/{x.role} — printed, not ranked"
                        for x in contribs
                        if x.role == "CLOSED" and x.available],
        ))

    recs.sort(key=lambda r: -r.ranking_score)
    n = len(recs)
    for idx, r in enumerate(recs):
        r.rank = idx + 1
        r.percentile = round(100.0 * (n - idx) / n, 1) if n else None
        r.recommendation = _verdict(r)
        r.reason_for_rank = _reason(r)
    for idx, r in enumerate(recs):
        r.better_alternatives = [x.ticker for x in recs[:idx][:3]]
    return recs


def _evidence_grade(contribs: list[SignalContribution]) -> str:
    """The WORST grade among the signals that actually moved the order.

    Taking the best would let one SUPPORTED leg launder a pile of HYPOTHESIS
    ones; the ranking is only as good as the weakest thing deciding it.
    """
    grades = [c.grade for c in contribs if c.rank_bearing and c.available]
    if not grades:
        return "NO_EVIDENCE"
    return max(grades, key=lambda g: _GRADE_ORDER.index(g)
               if g in _GRADE_ORDER else len(_GRADE_ORDER))


def _confidence(n_pickers: int, contribs: list[SignalContribution]) -> str:
    """Confidence is about the EVIDENCE, never about the volatility.

    Murat's ruling, in force: risk and evidence are different dimensions. A
    35%-vol name with two SUPPORTED pickers agreeing is HIGH confidence and
    high risk, and the page prints both columns.
    """
    if n_pickers == 0:
        return "NONE"
    calibrated = sum(1 for c in contribs
                     if c.rank_bearing and c.available and c.weight > 0)
    if n_pickers >= 3 and calibrated >= 3:
        return "HIGH"
    if n_pickers >= 2:
        return "MEDIUM"
    return "LOW"


def _verdict(r: Recommendation) -> str:
    if r.evidence_grade == "NO_EVIDENCE":
        return "NO_ACTION"
    if r.ranking_score <= 0:
        return "HOLD"
    if r.rank <= 10 and r.confidence in ("HIGH", "MEDIUM"):
        return "BUY"
    return "WATCH"


def _reason(r: Recommendation) -> str:
    lead = r.leader()
    if lead is None:
        return "no rank-bearing signal available for this name"
    others = [c for c in r.signal_contributions
              if c.rank_bearing and c.available and c.signal_id != lead.signal_id]
    tail = (f"; also {', '.join(f'{c.signal_id} {c.contribution:+.2f}' for c in others[:2])}"
            if others else "; single-signal rank")
    return (f"led by {lead.signal_id} ({lead.grade}/{lead.role}, "
            f"{lead.contribution:+.2f}){tail}")


# ─────────────────────── the permanent invariants ────────────────────────────

def audit_leadership(recs: list[Recommendation],
                     *, registry: Optional[registry_mod.Registry] = None,
                     ) -> list[dict]:
    """Every way a non-PICKER could be deciding the order. Empty list == clean.

    This is the successor to the printed EVIDENCE CONFLICT: the warning is not
    hidden, it is turned into a check that can actually fail.
    """
    reg = registry or registry_mod.load()
    violations: list[dict] = []
    for r in recs:
        for c in r.signal_contributions:
            if not c.rank_bearing and c.contribution == 0.0:
                continue
            if not c.rank_bearing:
                violations.append({
                    "ticker": r.ticker, "signal": c.signal_id,
                    "severity": "HIGH", "grade": c.grade, "role": c.role,
                    "what": "a non-PICKER signal carries nonzero rank weight",
                    "contribution": c.contribution})
                continue
            sig = reg.get(c.signal_id)
            if sig.evidence_grade in registry_mod.NEVER_PICKS:
                violations.append({
                    "ticker": r.ticker, "signal": c.signal_id,
                    "severity": "HIGH", "grade": c.grade, "role": c.role,
                    "what": "a NEVER_PICKS grade is ranking names",
                    "contribution": c.contribution})
        lead = r.leader()
        if lead is not None and lead.role == "FILTER":
            violations.append({
                "ticker": r.ticker, "signal": lead.signal_id,
                "severity": "MEDIUM", "grade": lead.grade, "role": lead.role,
                "what": "a FILTER is the largest contributor — a picker in a filter's badge",
                "contribution": lead.contribution})
    return violations


def rank_invariance(candidates: list[Any], signal_id: str,
                    *, registry: Optional[registry_mod.Registry] = None,
                    rank_fn: Optional[Callable[..., list[Recommendation]]] = None,
                    ) -> dict:
    """Prove a signal CANNOT reorder the BUY list.

    Re-ranks with that signal's field REVERSED across names — the most hostile
    order-preserving perturbation available without inventing data — and
    compares the resulting order. Spearman rho must be exactly 1.0. A signal
    that cannot move the order cannot lead it, whatever any docstring claims.

    This is a structural check, not a statistical one: rho is being used to
    detect *any* reordering, not to corroborate a return (NIGHT-9).
    """
    reg = registry or registry_mod.load()
    fn = rank_fn or score_candidates
    ad = next((a for a in _ADAPTERS if a.signal_id == signal_id), None)
    if ad is None:
        raise registry_mod.RegistryError(
            f"{signal_id} has no adapter, so it reads no data and cannot rank")

    base = fn(candidates, registry=reg)
    base_order = {r.ticker: r.rank for r in base}

    # reverse that one field across the cross-section, leave everything else
    perturbed: list[dict] = []
    vals = [_get(c, ad.field_name) for c in candidates]
    for c, v in zip(candidates, reversed(vals)):
        d = dict(c) if isinstance(c, dict) else dict(c.__dict__)
        d[ad.field_name] = v
        perturbed.append(d)

    after = fn(perturbed, registry=reg)
    after_order = {r.ticker: r.rank for r in after}

    common = [t for t in base_order if t in after_order]
    # Round before comparing: a perfect rank correlation computed in floating
    # point comes back as 0.9999999999999998, and an invariant that fails on
    # that is an invariant nobody can ever satisfy.
    rho = round(_spearman([float(base_order[t]) for t in common],
                          [float(after_order[t]) for t in common]), 12)
    moved = [t for t in common if base_order[t] != after_order[t]]
    sig = reg.get(signal_id)
    may_reorder = reg.permits(signal_id, "PICKER") or (
        sig.permitted_role == "FILTER" and sig.usable_now)
    return {
        "signal_id": signal_id,
        "role": sig.permitted_role,
        "grade": sig.evidence_grade,
        "may_reorder": may_reorder,
        "spearman_rho": rho,
        "n_names_moved": len(moved),
        "names_moved": moved[:10],
        "invariant_holds": (rho == 1.0 and not moved) if not may_reorder else True,
        "reading": (
            f"{signal_id} is {sig.evidence_grade}/{sig.permitted_role}; "
            + ("it may legitimately affect the order."
               if may_reorder else
               f"reversing it moved {len(moved)} name(s) — "
               f"{'PASS: it cannot reorder the BUY list' if not moved else 'FAIL: it CAN reorder the BUY list'}")),
    }


def assert_registry_discipline(candidates: list[Any],
                               *, registry: Optional[registry_mod.Registry] = None,
                               ) -> dict:
    """The gate. Raises RankLeadershipError if anything closed is steering.

    Called by the brief before it prints a BUY list, so the failure mode is a
    loud refusal to publish a ranking rather than a quiet warning nobody acts
    on for a night.
    """
    reg = registry or registry_mod.load()
    recs = score_candidates(candidates, registry=reg)
    violations = audit_leadership(recs, registry=reg)

    checks: list[dict] = []
    for sig in list(reg.closed()) + reg.by_role("RISK_INPUT"):
        if not any(a.signal_id == sig.signal_id for a in _ADAPTERS):
            continue
        try:
            checks.append(rank_invariance(candidates, sig.signal_id, registry=reg))
        except registry_mod.RegistryError:
            continue
    broken = [c for c in checks if not c["invariant_holds"]]

    if violations or broken:
        raise RankLeadershipError(
            f"BUY ranking is steered by signals that may not steer it: "
            f"{len(violations)} contribution violation(s), "
            f"{len(broken)} invariance failure(s): "
            f"{[c['signal_id'] for c in broken]}")
    return {"status": "CLEAN", "n_candidates": len(recs),
            "invariance_checks": checks, "violations": violations}
