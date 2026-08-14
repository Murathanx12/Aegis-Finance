"""TEACHER-LIBRARY-1 — the canonical public-action event.

One schema that every public actor's disclosed decisions map into: corporate
insiders, politicians, institutional managers, activists, media recommenders,
public fund trajectories. Eight sources become eight adapters into one learning
system rather than eight disconnected experiments.

THE TIMESTAMP THAT MATTERS
==========================
`public_at` is the earliest moment Aegis could legally and technically have
observed the information. It is the ONLY timestamp a copy strategy or a
backtest may enter on.

`transaction_at` is stored separately and is never a signal timestamp. A Pelosi
purchase on 1 January disclosed on 10 February is not a 1 January signal, and a
backtest entering on the transaction date measures a portfolio nobody could have
held. That is not a legal posture — it is what makes the lane's numbers mean
anything.

Keeping both is what makes the interesting questions askable at all:

    disclosure_lag   = public_at - transaction_at
    actor edge       = what happened after transaction_at
    public copy edge = what happened after public_at

The gap between those two is the whole COPYABILITY-GAP research family, and it
cannot be measured by a schema that keeps only one of them.

WHAT THIS FILE DOES NOT DO
==========================
No outcomes. No returns. No scoring. Nothing here joins an event to what
happened next, because the moment a number could grade a hypothesis, a
pre-registration comes first (CANON §6, `pre-register-trial`). This is the
substrate; the trials come later and separately.

ACTOR TYPES ARE PRECISE ON PURPOSE
==================================
A politician is not a `CORPORATE_INSIDER`. That term has a statutory meaning —
officers, directors and >10% holders subject to Section 16 — and using it for a
congressional trader would put a legal claim into the database as a category
label. Nobody is called an insider trader here unless the category is the
statutory one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0.0"

# ── actor taxonomy ──────────────────────────────────────────────────────────
ACTOR_CORPORATE_INSIDER = "CORPORATE_INSIDER"      #: Section 16 filer, strictly
ACTOR_POLITICIAN = "POLITICIAN"
ACTOR_POLITICIAN_FAMILY = "POLITICIAN_FAMILY"
ACTOR_HEDGE_FUND_MANAGER = "HEDGE_FUND_MANAGER"
ACTOR_FUND_MANAGER = "FUND_MANAGER"                #: mutual fund / ETF
ACTOR_ACTIVIST_INVESTOR = "ACTIVIST_INVESTOR"
ACTOR_PUBLIC_INVESTOR = "PUBLIC_INVESTOR"
ACTOR_MEDIA_RECOMMENDER = "MEDIA_RECOMMENDER"
ACTOR_TRACKER_PORTFOLIO = "TRACKER_PORTFOLIO"

ACTOR_TYPES = frozenset({
    ACTOR_CORPORATE_INSIDER, ACTOR_POLITICIAN, ACTOR_POLITICIAN_FAMILY,
    ACTOR_HEDGE_FUND_MANAGER, ACTOR_FUND_MANAGER, ACTOR_ACTIVIST_INVESTOR,
    ACTOR_PUBLIC_INVESTOR, ACTOR_MEDIA_RECOMMENDER, ACTOR_TRACKER_PORTFOLIO,
})

# ── action taxonomy ─────────────────────────────────────────────────────────
# Behaviour, not celebrity. The library learns "a specialist manager initiated a
# high-weight position", never "Pelosi_score = 0.73".
ACTION_TYPES = frozenset({
    "INITIATE", "ADD", "CONVICTION_ADD", "TRIM", "FULL_EXIT", "REENTER",
    "BUY", "SELL", "RECOMMEND_BUY", "RECOMMEND_SELL",
    "BULLISH_COMMENT", "BEARISH_COMMENT",
    "ACTIVIST_STAKE", "PASSIVE_STAKE", "OPTION_POSITION", "OTHER",
})

# ── availability / quality status ───────────────────────────────────────────
# Same vocabulary as the tool layer, the feature layer and the Form 4 fetcher.
# "Source unavailable" is never encoded as "zero activity" anywhere in Aegis.
OK_DATA = "OK_DATA"
OK_EMPTY = "OK_EMPTY"
UNAVAILABLE = "UNAVAILABLE"
PARSE_ERROR = "PARSE_ERROR"
IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
SECURITY_MAPPING_AMBIGUOUS = "SECURITY_MAPPING_AMBIGUOUS"
LATE_FILING = "LATE_FILING"
OTHER_EXPLICIT_FAILURE = "OTHER_EXPLICIT_FAILURE"

STATUSES = frozenset({
    OK_DATA, OK_EMPTY, UNAVAILABLE, PARSE_ERROR, IDENTITY_AMBIGUOUS,
    SECURITY_MAPPING_AMBIGUOUS, LATE_FILING, OTHER_EXPLICIT_FAILURE,
})

#: Statuses a research or copy layer may consume as an observed action.
USABLE_STATUSES = frozenset({OK_DATA, LATE_FILING})


class TeacherEventInvalid(ValueError):
    """A row that would be a lie if written. Raised, never coerced."""


def _iso(v: Any) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        d = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    return str(v)


def _parse(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        try:
            d = datetime.strptime(str(v)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@dataclass
class TeacherEvent:
    """One disclosed decision by one public actor about one security."""

    # identity of the record
    source: str
    source_event_id: str
    actor_id: str
    actor_type: str
    action_type: str

    # what
    ticker_at_event: str | None = None
    security_id: str | None = None
    cusip: str | None = None
    issuer_cik: str | None = None
    actor_name: str = ""
    actor_subtype: str = ""

    # when — `public_at` is the only signal timestamp
    public_at: str | None = None
    transaction_at: str | None = None
    period_end: str | None = None
    filed_at: str | None = None
    accepted_at: str | None = None
    observed_at: str | None = None
    fetched_at: str | None = None

    # position / size
    shares: float | None = None
    position_before: float | None = None
    position_after: float | None = None
    delta_shares: float | None = None
    delta_pct: float | None = None
    weight_before: float | None = None
    weight_after: float | None = None
    portfolio_weight: float | None = None
    concentration_rank: int | None = None
    amount_low: float | None = None
    amount_high: float | None = None
    reported_price: float | None = None
    ownership_type: str = ""

    # context
    sector: str = ""
    industry: str = ""
    actor_specialization: str = ""
    domain_relevance: str = ""
    insider_role: str = ""
    is_officer: bool | None = None
    is_director: bool | None = None
    is_ten_pct_owner: bool | None = None
    rule_10b5_1: bool | None = None
    filing_type: str = ""

    # provenance / quality
    status: str = OK_DATA
    reason: str = ""
    source_quality: str = ""
    source_url: str = ""
    raw_sha256: str = ""
    parser_version: str = ""
    identity_quality: str = ""
    mapping_quality: str = ""
    data_quality_flags: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    # amendment chain
    amends_event_id: str | None = None
    is_amendment: bool = False

    def __post_init__(self) -> None:
        for name in ("public_at", "transaction_at", "period_end", "filed_at",
                     "accepted_at", "observed_at", "fetched_at"):
            setattr(self, name, _iso(getattr(self, name)))
        self.validate()

    # ── invariants ──────────────────────────────────────────────────────────
    def validate(self) -> None:
        if self.actor_type not in ACTOR_TYPES:
            raise TeacherEventInvalid(
                f"actor_type {self.actor_type!r} is not in the taxonomy. A "
                f"free-text actor type is how a politician ends up filed as a "
                f"CORPORATE_INSIDER, which is a statutory category and a legal "
                f"claim, not a label.")
        if self.action_type not in ACTION_TYPES:
            raise TeacherEventInvalid(
                f"action_type {self.action_type!r} is not in the taxonomy")
        if self.status not in STATUSES:
            raise TeacherEventInvalid(f"status {self.status!r} is not a status")
        if not self.source or not self.source_event_id or not self.actor_id:
            raise TeacherEventInvalid(
                "source, source_event_id and actor_id are all required — "
                "without them the row cannot be deduplicated, amended or "
                "traced back to a filing")

        if self.status in USABLE_STATUSES and not self.public_at:
            raise TeacherEventInvalid(
                f"a {self.status} event has no public_at. That is the only "
                f"timestamp a copy strategy may enter on; a row without it "
                f"cannot be used and must not pretend it can.")

        pub, txn = _parse(self.public_at), _parse(self.transaction_at)
        if pub and txn and txn > pub:
            raise TeacherEventInvalid(
                f"transaction_at {self.transaction_at} is AFTER public_at "
                f"{self.public_at}. Information cannot become public before "
                f"the act it describes; this is a parse error wearing a "
                f"plausible shape.")

        lo, hi = self.amount_low, self.amount_high
        if lo is not None and hi is not None and lo > hi:
            raise TeacherEventInvalid(
                f"amount_low {lo} > amount_high {hi}")

    # ── identity ────────────────────────────────────────────────────────────
    def event_id(self) -> str:
        """Deterministic SHA-256 over the fields that make the event that event.

        NOT `hash()`: Python salts string hashing per process, so the same
        filing would get a different identity on every run and deduplication
        would silently stop working. This repo has already paid for that once,
        in the prediction ledger's snapshot hash.
        """
        key = "|".join(str(x) for x in (
            self.source, self.source_event_id, self.actor_id,
            self.security_id or self.ticker_at_event or "", self.action_type,
            self.transaction_at or "", self.public_at or "",
            self.shares if self.shares is not None else "",
        ))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def disclosure_lag_days(self) -> float | None:
        """`public_at - transaction_at`, the quantity the copy question turns on.

        Returns None when the source does not report a transaction date — 13F
        gives a quarter-end holding and a filing date, never the trade date, and
        inventing one would manufacture a lag that was never measured.
        """
        pub, txn = _parse(self.public_at), _parse(self.transaction_at)
        if not pub or not txn:
            return None
        return (pub - txn).total_seconds() / 86400.0

    @property
    def usable(self) -> bool:
        return self.status in USABLE_STATUSES

    def as_dict(self) -> dict:
        d = asdict(self)
        d["event_id"] = self.event_id()
        d["disclosure_lag_days"] = self.disclosure_lag_days()
        return d

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, default=str)

    @classmethod
    def from_dict(cls, d: dict) -> "TeacherEvent":
        known = {k: v for k, v in d.items()
                 if k in cls.__dataclass_fields__}          # type: ignore[attr-defined]
        return cls(**known)


def sha256_of(payload: Any) -> str:
    """Provenance digest for a raw source payload. Stable across processes."""
    if isinstance(payload, (bytes, bytearray)):
        return hashlib.sha256(bytes(payload)).hexdigest()
    if isinstance(payload, str):
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
