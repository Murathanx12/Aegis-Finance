"""G4 — the expectation layer. What happened, RELATIVE TO WHAT WAS EXPECTED.

WHY THIS EXISTS BEFORE THE FACTORY
==================================
The winner/matched-loser factory asks an LLM what observable difference explains
why A beat B. Without an expectation layer it will rediscover, repeatedly and
correctly, that companies with good earnings go up. That is an ANNOUNCEMENT
fact, it is in the price by construction, and it is not tradable.

The thing worth finding looks like:

    "beat an already-high expectation by X, while revisions improved, and the
     price reaction was abnormally SMALL"

which is a statement about four quantities the factory cannot compute unless
something records them. So this module is the vocabulary the factory needs, and
it is deliberately built first.

FOUR CLOCKS, AND CONFLATING THEM IS THE DEFECT THIS GUARDS AGAINST
==================================================================
An event has more timestamps than people expect, and the interesting research
lives in the gaps between them:

    expectation_asof   what the market believed, and WHEN it believed it
    first_public_ts    when the fact became public
    observed_at        when OUR source recorded it   (-> disclosure delay)
    tradable_at        the earliest we could have acted

`first_public_ts - expectation_asof > 0` is what makes a surprise a surprise.
`observed_at - first_public_ts` is the disclosure delay, and it is the whole
subject of actor intelligence — a Form 4 filed two days after the trade is a
different instrument from one filed the same hour.
`tradable_at - first_public_ts` is why an 8am announcement is not a 9:30 entry.

A record that cannot order these is refused. It is not repaired: a timestamp
guessed to make a record valid is the mechanism by which look-ahead enters a
dataset, and it enters looking exactly like diligence.

UNKNOWN IS A VALUE, AND IT HAS TO BE SAID OUT LOUD
==================================================
Every field may be unknown. What it may NOT be is silently absent: a `None`
with no entry in `unknown_reasons` is refused. This costs one line per missing
field and it buys the one thing a nullable column never gives you — the
difference between "we looked and there is none" and "nobody wired this up".

The house failure mode is a pipeline that returns zeros for missing inputs and
a model that learns from them. `fillna(0)` on a surprise column would teach a
factory that every uncovered company met expectations exactly.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "g4-0.1.0"

#: Revision states. FLAT is not "no information" — it is the measured absence of
#: revision, which is different from UNKNOWN and must not collapse into it.
REVISION_STATES = ("UP", "DOWN", "FLAT", "MIXED", "UNKNOWN")

#: Guidance states, from the issuer rather than from the analysts.
GUIDANCE_STATES = ("RAISED", "LOWERED", "MAINTAINED", "INITIATED",
                   "WITHDRAWN", "NONE", "UNKNOWN")

#: Fields an LLM may populate. Every one of them is a claim about the world and
#: therefore needs sources; see `validate`.
SEMANTIC_FIELDS = ("semantic_expected_state", "semantic_actual_state",
                   "semantic_surprise", "already_priced_estimate")

#: Fields that may never be produced by inference. Numeric features drive
#: sizing; a hallucinated one is indistinguishable from a measured one three
#: months later, and it is the one that pays or does not pay.
MEASURED_ONLY_FIELDS = ("numeric_expectation", "actual", "expectation_dispersion",
                        "n_estimates", "pre_event_price_runup",
                        "market_reaction", "options_implied_move")


def _ts(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    d = datetime.fromisoformat(str(v))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@dataclass
class ExpectationRecord:
    """One event, with what was expected of it before it happened."""

    # ── identity ────────────────────────────────────────────────────────────
    entity: str
    entity_id_kind: str          # "permno" | "ibes_ticker" | "cusip8" | ...
    entity_id: str
    event_type: str              # "EPS_ANNOUNCEMENT" | "GUIDANCE" | ...
    event_id: str

    # ── the four clocks ─────────────────────────────────────────────────────
    first_public_ts: str | None
    expectation_asof: str | None
    observed_at: str | None
    tradable_at: str | None

    # ── the expectation, and what actually happened ─────────────────────────
    numeric_expectation: float | None = None
    expectation_dispersion: float | None = None
    n_estimates: int | None = None
    actual: float | None = None

    # ── context that is measured, never inferred ────────────────────────────
    analyst_revision_state: str = "UNKNOWN"
    guidance_state: str = "UNKNOWN"
    pre_event_price_runup: float | None = None
    market_reaction: float | None = None
    options_implied_move: float | None = None

    # ── what an LLM may say, only with sources ──────────────────────────────
    semantic_expected_state: str | None = None
    semantic_actual_state: str | None = None
    semantic_surprise: str | None = None
    already_priced_estimate: str | None = None

    # ── provenance ──────────────────────────────────────────────────────────
    source_ids: list[str] = field(default_factory=list)
    unknown_reasons: dict[str, str] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    # ── derived, never stored as an input ───────────────────────────────────
    @property
    def numeric_surprise(self) -> float | None:
        """Actual minus expected, in units of ANALYST DISAGREEMENT.

        Scaled rather than raw on purpose: a 2-cent beat means something very
        different for a name where the analysts are 1 cent apart than for one
        where they are 20 cents apart. Raw cents would make the factory rank
        companies by how noisy their coverage is.

        Returns None when the scale is missing or degenerate. A zero dispersion
        with a nonzero miss is INFINITE surprise, not a large number, and
        pretending otherwise puts an outlier at the top of every ranking.
        """
        if self.actual is None or self.numeric_expectation is None:
            return None
        d = self.expectation_dispersion
        if d is None or not math.isfinite(d) or d <= 0:
            return None
        return (self.actual - self.numeric_expectation) / d

    @property
    def numeric_surprise_pct(self) -> float | None:
        """The same difference relative to the expectation's own magnitude.

        Reported beside the scaled one because they disagree exactly where it
        matters: near-zero expected EPS makes this explode while the scaled
        version stays sane, and a company crossing from loss to profit is the
        case both the literature and the factory care about most.
        """
        if self.actual is None or self.numeric_expectation is None:
            return None
        base = abs(self.numeric_expectation)
        if base < 1e-9:
            return None
        return (self.actual - self.numeric_expectation) / base

    @property
    def disclosure_delay_days(self) -> float | None:
        """`observed_at - first_public_ts`. The actor-intelligence quantity."""
        a, b = _ts(self.observed_at), _ts(self.first_public_ts)
        if a is None or b is None:
            return None
        return (a - b).total_seconds() / 86400.0

    def surprise_is_resolvable(self) -> bool:
        return self.numeric_surprise is not None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["numeric_surprise"] = self.numeric_surprise
        d["numeric_surprise_pct"] = self.numeric_surprise_pct
        d["disclosure_delay_days"] = self.disclosure_delay_days
        return d


class ExpectationRefused(ValueError):
    """A record that cannot be trusted to say what was knowable when."""


def validate(rec: ExpectationRecord, *, strict: bool = True) -> list[str]:
    """Every reason this record must not enter the dataset.

    Returns the list rather than raising by default, because a collector wants
    to COUNT its refusals and name them — a loader that raises on the first bad
    row reports one problem and hides nine hundred.
    """
    bad: list[str] = []

    # ── the ordering of the clocks ──────────────────────────────────────────
    pub, exp = _ts(rec.first_public_ts), _ts(rec.expectation_asof)
    obs, trd = _ts(rec.observed_at), _ts(rec.tradable_at)

    if pub is None:
        bad.append("first_public_ts is required: without it nothing can be "
                   "said about what was knowable before the event")
    if exp is None:
        bad.append("expectation_asof is required: an expectation with no date "
                   "is a number, not an expectation")
    if pub is not None and exp is not None and exp >= pub:
        # THE central guard. An expectation stamped at or after the event is
        # the announcement wearing the expectation's clothes, and the surprise
        # computed from it is identically zero-ish by construction.
        bad.append(f"expectation_asof {rec.expectation_asof} is not strictly "
                   f"before first_public_ts {rec.first_public_ts} — the "
                   f"'expectation' already contains the event")
    if pub is not None and trd is not None and trd < pub:
        bad.append(f"tradable_at {rec.tradable_at} precedes first_public_ts "
                   f"{rec.first_public_ts}: acting before the fact was public")
    if pub is not None and obs is not None and obs < pub:
        bad.append(f"observed_at {rec.observed_at} precedes first_public_ts "
                   f"{rec.first_public_ts}: our source recorded it before it "
                   f"existed, which means one of the two timestamps is wrong")

    # ── UNKNOWN has to be said, not defaulted ───────────────────────────────
    for f in MEASURED_ONLY_FIELDS:
        if getattr(rec, f) is None and f not in rec.unknown_reasons:
            bad.append(f"{f} is absent with no entry in `unknown_reasons`. "
                       f"State why it is unknown; silence and 'we checked and "
                       f"there is none' must not look the same")

    if rec.analyst_revision_state not in REVISION_STATES:
        bad.append(f"analyst_revision_state {rec.analyst_revision_state!r} "
                   f"is not one of {REVISION_STATES}")
    if rec.guidance_state not in GUIDANCE_STATES:
        bad.append(f"guidance_state {rec.guidance_state!r} is not one of "
                   f"{GUIDANCE_STATES}")

    # ── anything an LLM said has to resolve to something ────────────────────
    said = [f for f in SEMANTIC_FIELDS if getattr(rec, f) not in (None, "")]
    if said and not rec.source_ids:
        bad.append(f"semantic field(s) {said} populated with no `source_ids`. "
                   f"An unsourced factual claim becomes UNKNOWN, never a "
                   f"feature")

    # ── the dispersion trap, stated rather than silently returning None ─────
    if (rec.expectation_dispersion is not None
            and rec.expectation_dispersion < 0):
        bad.append("expectation_dispersion is negative")
    if (rec.n_estimates is not None and rec.n_estimates <= 1
            and rec.expectation_dispersion in (0, 0.0)):
        # One analyst gives zero disagreement, which is not agreement.
        bad.append("n_estimates <= 1 with zero dispersion: a single estimate "
                   "has no disagreement to measure, and scaling by it would "
                   "read as infinite consensus")

    if strict and bad:
        raise ExpectationRefused("; ".join(bad))
    return bad


def summarise(records: list[ExpectationRecord]) -> dict:
    """Denominators, because a collector that reports only what it kept is
    reporting its own filter."""
    n = len(records)
    resolvable = [r for r in records if r.surprise_is_resolvable()]
    delays = [r.disclosure_delay_days for r in records
              if r.disclosure_delay_days is not None]
    return {
        "n_records": n,
        "n_surprise_resolvable": len(resolvable),
        "n_surprise_unresolvable": n - len(resolvable),
        "n_with_guidance": sum(1 for r in records
                               if r.guidance_state not in ("UNKNOWN", "NONE")),
        "n_with_revision_state": sum(1 for r in records
                                     if r.analyst_revision_state != "UNKNOWN"),
        "n_with_price_reaction": sum(1 for r in records
                                     if r.market_reaction is not None),
        "n_with_implied_move": sum(1 for r in records
                                   if r.options_implied_move is not None),
        "n_with_semantic": sum(1 for r in records if any(
            getattr(r, f) not in (None, "") for f in SEMANTIC_FIELDS)),
        "median_disclosure_delay_days": (sorted(delays)[len(delays) // 2]
                                         if delays else None),
    }
