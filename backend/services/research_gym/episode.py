"""The DecisionEpisode — what was known, what was believed, what was done.

RULING R3. A backtest says "the strategy did X and the result was Y". That is
not enough to learn from, because it cannot answer the question that started
this: *we knew there was stress and we sold — but what if we had held?* The
answer requires the decision to be reconstructable, and a P&L series is not.

So every important decision becomes a record with four separable parts:

    STATE      everything the system legally knew at decision time (PIT)
    BELIEFS    what it thought would happen — as probabilities, not a label
    ACTION     what it did, and the reason it gave AT THE TIME
    OUTCOME    what actually happened afterwards, attached later

The separation is the whole design. A wrong outcome could come from a wrong
belief (the world did something else) or from a right belief converted into the
wrong action (the policy layer). Those demand opposite fixes, and a record that
stores only "sold, lost money" cannot tell them apart. R4's taxonomy is only
computable because BELIEFS and ACTION are stored as different fields.

THE STATED REASON IS EVIDENCE, NOT DECORATION
=============================================
`stated_reason` is captured at decision time and frozen. When the autopsy layer
(R5) later proposes a mechanism, the thing it must beat is what we actually
believed then — not a reconstruction of what we would now say we believed. Post
hoc reasons are the most persuasive and least reliable data in research.

GYM MATERIAL IS NOT EVIDENCE
============================
Every episode carries `provenance`. Historical episodes are `GYM`; only forward
ones can ever be `CERTIFICATION`. `GymResult` in `charter.py` enforces what that
means downstream. Here it is simply recorded, so that no episode is ever
ambiguous about which world it came from.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── provenance: which world an episode came from ────────────────────────────
GYM = "GYM"                    #: historical; overfitting licensed; never cited
CERTIFICATION = "CERTIFICATION"  #: forward; the only surface that can certify
PROVENANCE = frozenset({GYM, CERTIFICATION})

# ── R4: where a bad outcome actually went wrong ─────────────────────────────
# A closed vocabulary, because "the model was wrong" is the explanation that
# fits every failure and therefore distinguishes none of them.
FORECAST_FAILURE = "forecast_failure"
#: The state was READ correctly and the inference from that state to an expected
#: return contradicted the state's own historical base rate.
#:
#: Added after the first dataset-zero run, which classified every de-risking
#: failure as `forecast_failure` — true, and an artefact: a SELL followed by a
#: rally can barely classify as anything else under that definition. Murat's
#: directive is sharper than the label was: "stress detection itself was
#: correct; the failure came from mapping high stress to zero exposure". That
#: separates perception (VIX really was 57 — measured, not forecast) from the
#: INFERENCE drawn from it, and only the second was wrong.
#:
#: The distinction is mechanical rather than rhetorical: an expectation that
#: contradicted the conditional base rate was wrong in a way the data already
#: knew, and is therefore fixable. One that agreed with the base rate and still
#: lost was an unlucky draw, and "fixing" it is fitting noise.
STATE_TO_FORECAST_FAILURE = "state_to_forecast_failure"
#: Perception was right; the policy layer turned it into the wrong action. THE
#: prize category — it is what the timing backtest actually shows, and it is
#: invisible to any framework that scores predictions instead of decisions.
ACTION_MAPPING_FAILURE = "action_mapping_failure"
TIMING_FAILURE = "timing_failure"
SIZING_FAILURE = "sizing_failure"
REGIME_TRANSITION_FAILURE = "regime_transition_failure"
CONCENTRATION_FAILURE = "concentration_failure"
COST_FAILURE = "cost_failure"
#: Not a failure. Recorded explicitly so "no failure mode assigned" and "we did
#: not classify this" are never the same value.
NO_FAILURE = "no_failure"
UNCLASSIFIED = "unclassified"

FAILURE_MODES = frozenset({
    FORECAST_FAILURE, STATE_TO_FORECAST_FAILURE,
    ACTION_MAPPING_FAILURE, TIMING_FAILURE, SIZING_FAILURE,
    REGIME_TRANSITION_FAILURE, CONCENTRATION_FAILURE, COST_FAILURE,
    NO_FAILURE, UNCLASSIFIED,
})

FAILURE_DESCRIPTIONS = {
    FORECAST_FAILURE: "the world did something the beliefs assigned low "
                      "probability to, and the state's own history said it "
                      "probably would not — an unlucky draw, not a fixable one",
    STATE_TO_FORECAST_FAILURE:
        "the state was read correctly and the expectation drawn from it "
        "contradicted that state's historical base rate — wrong in a way the "
        "data already knew, and therefore learnable",
    ACTION_MAPPING_FAILURE: "the beliefs were right and the action taken on "
                            "them was not the best available action on them",
    TIMING_FAILURE: "the direction of the action was right and the entry or "
                    "re-entry moment lost what the direction earned",
    SIZING_FAILURE: "the direction was right and the size was wrong",
    REGIME_TRANSITION_FAILURE: "the prevailing regime was identified correctly "
                               "and its END was not",
    CONCENTRATION_FAILURE: "the decision was right on average and the "
                           "portfolio's concentration destroyed it",
    COST_FAILURE: "a gross edge existed and turnover consumed it",
    NO_FAILURE: "the decision did as well as the best alternative available",
    UNCLASSIFIED: "not yet classified — never a synonym for 'nothing wrong'",
}


@dataclass
class Beliefs:
    """What the system thought would happen, as distributions.

    Every field is optional and defaults to None, and None means UNKNOWN rather
    than 0.5. A missing belief and a coin flip are different states: one says
    the system had no opinion, the other says it had one and it was maximally
    uncertain. Attribution treats them differently and would be wrong to fill
    either in.
    """
    p_up: float | None = None
    p_down: float | None = None
    p_abs_move_gt_3pct: float | None = None
    p_abs_move_gt_5pct: float | None = None
    expected_vol_annualised: float | None = None
    expected_max_drawdown_pct: float | None = None
    p_rebound: float | None = None
    p_regime_change: float | None = None
    horizon_days: int | None = None

    def is_empty(self) -> bool:
        return all(v is None for v in asdict(self).values())


@dataclass
class Outcome:
    """What happened. Attached AFTER the fact and never at decision time.

    Kept as a separate object so that an unresolved episode is structurally
    unresolved — `outcome is None` — rather than an episode carrying zeros that
    a downstream mean would happily average.
    """
    resolved_at: str = ""
    horizon_days: int = 0
    realised_return_pct: float | None = None
    realised_vol_annualised: float | None = None
    max_drawdown_pct: float | None = None
    path_min_pct: float | None = None
    path_max_pct: float | None = None
    days_to_trough: int | None = None
    days_to_recovery: int | None = None


@dataclass
class DecisionEpisode:
    """One decision, fully reconstructable.

    `episode_id` is a content hash of the identifying fields, so the same
    decision replayed twice is the same episode rather than two, and an episode
    whose state was edited gets a different id instead of silently becoming a
    different decision under the old name.
    """
    decision_ts: str
    security: str
    action: str                       # SELL | BUY | HOLD | REDUCE | ADD ...
    provenance: str = GYM
    #: Position exposure BEFORE and AFTER the action, as fractions of capital.
    #: Fractions, never percent — the size-bound-in-percent bug has already been
    #: paid for once in this repo, in a different module.
    exposure_before: float = 1.0
    exposure_after: float = 1.0
    stated_reason: str = ""
    #: Everything the system legally knew. Free-form because the state vector
    #: grows, but PIT by contract: a key here that could not have been computed
    #: at `decision_ts` is leakage, not a feature.
    state: dict = field(default_factory=dict)
    beliefs: Beliefs = field(default_factory=Beliefs)
    outcome: Outcome | None = None
    #: R4 classification. Only meaningful once the counterfactual surface
    #: exists — you cannot say "the action was wrong given right beliefs"
    #: without knowing what the other actions would have done.
    failure_mode: str = UNCLASSIFIED
    failure_detail: str = ""
    #: All three regret denominators (`regret.RegretTriple.as_dict()`), never a
    #: scalar. Written by `attribute_in_place`. A single regret number on this
    #: record would be the G1 defect reintroduced: the obvious denominator is a
    #: maximum over the menu and has a large positive null.
    regret: dict = field(default_factory=dict)
    #: How firmly the base rate contradicted the belief: established /
    #: suggestive / too_thin. Carried separately from `failure_mode` so counts
    #: can be split by evidence strength rather than reported as one total.
    evidence_strength: str = ""
    #: What produced this episode, for the lineage ledger.
    source: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc)
        .isoformat(timespec="seconds"))

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE:
            raise ValueError(f"unknown provenance {self.provenance!r}")
        if self.failure_mode not in FAILURE_MODES:
            raise ValueError(f"unknown failure_mode {self.failure_mode!r}")
        for name in ("exposure_before", "exposure_after"):
            v = getattr(self, name)
            if not (0.0 <= float(v) <= 2.0):
                raise ValueError(
                    f"{name}={v} is not an exposure fraction in [0, 2]. "
                    f"A size expressed in percent (50 rather than 0.50) has "
                    f"broken this project's records before.")

    @property
    def episode_id(self) -> str:
        blob = json.dumps({"ts": self.decision_ts, "sec": self.security,
                           "act": self.action, "prov": self.provenance,
                           "state": self.state}, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    @property
    def is_resolved(self) -> bool:
        return self.outcome is not None and \
            self.outcome.realised_return_pct is not None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["episode_id"] = self.episode_id
        d["failure_description"] = FAILURE_DESCRIPTIONS.get(self.failure_mode, "")
        return d
