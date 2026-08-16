"""Which data has been looked at, by what, for what purpose — and what that costs.

WHY THIS EXISTS (2026-08-16)
============================
N9 froze a rule set and confirmed it on six pre-declared untouched securities
(DIA XLV XLI XLP XLU XLB) at lift 1.271, p=0.015. N9B then ran on the same six.
N9B's arithmetic is not wrong and its equivalence result stands, but it is
**not a second independent confirmation**: the experiment was designed after
information from that slice had already entered the research process.

Nothing in the codebase recorded that. The slice existed only in prose, in a
handoff, and the second consumption was noticed by a reader rather than
refused by a tool.

THE REGISTERED OBJECT IS NOT A TICKER LIST
==========================================
If the identity were the securities alone, the same six with a date window
shifted by a month would present as a fresh slice. The identity is therefore
the four-tuple

    universe  x  period  x  outcome definition  x  information cutoff

and reuse is detected by OVERLAP, not by equality — see `overlaps`. Two slices
that share any security and any calendar day at the same outcome horizon are
the same slice for the purpose of confirmation, whatever their labels say.

WHAT IS REFUSED
===============
Only CONFIRM. Exploration may revisit data freely; that is what exploration is.
A confirmation on a slice any prior trial has touched is refused unless the
pre-registration declares itself PAIRED or REANALYSIS, in which case it is
recorded as such and may not later be described as independent confirmation.

The refusal is the return value AND an exception, because a checker whose
result can be ignored is a comment (canon: the exit code IS the guard).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from backend import config as _config

REGISTER_PATH = (_config.OPTIMUS_LEDGER_DIR / "research_gym"
                 / "slice_register.jsonl")

#: What a trial intends to do with a slice.
#:
#: EXPLORE   — search, mine, tune. Consumes the slice for confirmation forever.
#: FOREIGN   — evaluate a rule whose parent was fitted elsewhere. Still looking.
#: CONFIRM   — the one that must be clean, and the only one this module refuses.
#: REANALYSIS— deliberately re-examining a spent slice with a new estimand.
#: PAIRED    — a difference test against a prior trial ON that slice, by design.
PURPOSES = ("EXPLORE", "FOREIGN", "CONFIRM", "REANALYSIS", "PAIRED")

#: Purposes that acknowledge the slice is already spent. A CONFIRM cannot be
#: rescued by relabelling after the fact — the prereg has to say so first.
NON_INDEPENDENT = ("REANALYSIS", "PAIRED")


class SliceRefusal(RuntimeError):
    """A confirmation was attempted on a slice that has already been read."""


@dataclass(frozen=True)
class SliceIdentity:
    """universe x period x outcome definition x information cutoff."""

    securities: tuple[str, ...]
    start: str
    end: str
    outcome_horizon_days: int
    outcome_definition: str
    #: The last timestamp a feature may be built from. Distinct from `end`:
    #: two trials can share a price window and differ in what they were
    #: allowed to know inside it.
    information_cutoff: str = ""

    def __post_init__(self) -> None:
        if not self.securities:
            object.__setattr__(self, "securities", ())
        object.__setattr__(self, "securities",
                           tuple(sorted({s.upper() for s in self.securities})))

    @property
    def slice_id(self) -> str:
        """Deterministic over the four-tuple. Labels do not enter it."""
        payload = "|".join((
            ",".join(self.securities), self.start, self.end,
            str(self.outcome_horizon_days),
            self.outcome_definition.strip().lower(),
            self.information_cutoff,
        ))
        return "slc_" + hashlib.sha256(payload.encode()).hexdigest()[:16]

    def overlaps(self, other: "SliceIdentity") -> dict:
        """Do these two read any of the same data at the same horizon?

        Deliberately permissive about what counts as the same: sharing ONE
        security on ONE day at the same outcome horizon is enough, because a
        confirmation contaminated on part of its universe is contaminated.
        """
        shared = set(self.securities) & set(other.securities)
        lo = max(self.start, other.start)
        hi = min(self.end, other.end)
        days_overlap = lo <= hi
        same_horizon = self.outcome_horizon_days == other.outcome_horizon_days
        return {
            "shared_securities": sorted(shared),
            "period_overlaps": bool(days_overlap),
            "overlap_start": lo if days_overlap else None,
            "overlap_end": hi if days_overlap else None,
            "same_horizon": same_horizon,
            "is_same_slice": bool(shared) and days_overlap and same_horizon,
        }


@dataclass
class Consumption:
    """One trial reading one slice, for one declared purpose."""

    slice_id: str
    identity: dict
    trial: str
    purpose: str
    consumed_at: str
    prereg: str = ""
    parent_hypotheses: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _load(path: Path) -> list[Consumption]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            out.append(Consumption(**json.loads(ln)))
    return out


class SliceRegister:
    """Append-only ledger of who read what.

    Append-only on purpose: a register a trial can edit is a register that will
    be edited by the trial that needs it edited.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else REGISTER_PATH
        self.records: list[Consumption] = _load(self.path)

    # ── queries ────────────────────────────────────────────────────────────
    def prior_readers(self, identity: SliceIdentity) -> list[Consumption]:
        """Every recorded consumption that touches this slice's data."""
        out = []
        for rec in self.records:
            try:
                other = SliceIdentity(**rec.identity)
            except TypeError:
                continue
            if identity.overlaps(other)["is_same_slice"]:
                out.append(rec)
        return out

    def is_spent(self, identity: SliceIdentity) -> bool:
        return bool(self.prior_readers(identity))

    # ── the guard ──────────────────────────────────────────────────────────
    def check(self, identity: SliceIdentity, purpose: str, *,
              trial: str = "", declared_non_independent: bool = False) -> dict:
        """May `trial` read this slice for `purpose`?

        Returns the verdict rather than only raising, so a caller can print it;
        `claim` raises on the same condition so a caller cannot ignore it.
        """
        purpose = purpose.upper()
        if purpose not in PURPOSES:
            raise ValueError(f"unknown purpose {purpose!r}; declared: {PURPOSES}")

        readers = self.prior_readers(identity)
        if purpose != "CONFIRM" or not readers:
            return {"allowed": True, "purpose": purpose,
                    "slice_id": identity.slice_id,
                    "prior_readers": [r.trial for r in readers],
                    "why": ("no prior reader" if not readers else
                            f"{purpose} does not require an unread slice")}

        if declared_non_independent:
            return {
                "allowed": True, "purpose": purpose,
                "slice_id": identity.slice_id,
                "prior_readers": [r.trial for r in readers],
                "why": ("spent slice, but the pre-registration declares this "
                        "non-independent — it may NOT be reported as "
                        "confirmation"),
                "may_claim_confirmation": False,
            }

        return {
            "allowed": False, "purpose": purpose,
            "slice_id": identity.slice_id,
            "prior_readers": [r.trial for r in readers],
            "why": (
                f"CONFIRM refused: {identity.slice_id} was already read by "
                f"{', '.join(r.trial + ' (' + r.purpose + ')' for r in readers)}"
                f". Information from this slice has entered the research "
                f"process, so a result here is a post-confirmation adaptive "
                f"comparison, not an independent confirmation. Either pick an "
                f"unread slice, or declare the trial REANALYSIS/PAIRED in its "
                f"pre-registration and give up the confirmation claim."),
        }

    def claim(self, identity: SliceIdentity, purpose: str, *, trial: str,
              consumed_at: str, prereg: str = "",
              parent_hypotheses: Sequence[str] = (), note: str = "",
              declared_non_independent: bool = False) -> Consumption:
        """Check, then record. Raises `SliceRefusal` if the check refuses.

        `consumed_at` is passed in rather than read from the clock, because a
        register that stamps its own times cannot be replayed or tested.
        """
        verdict = self.check(identity, purpose, trial=trial,
                             declared_non_independent=declared_non_independent)
        if not verdict["allowed"]:
            raise SliceRefusal(verdict["why"])

        rec = Consumption(
            slice_id=identity.slice_id, identity=asdict(identity),
            trial=trial, purpose=purpose.upper(), consumed_at=consumed_at,
            prereg=prereg, parent_hypotheses=list(parent_hypotheses),
            note=note)
        self.records.append(rec)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec.as_dict()) + "\n")
        return rec

    def unread_candidates(self, pool: Iterable[str],
                          identity_template: SliceIdentity) -> list[str]:
        """Securities in `pool` no recorded trial has read at this horizon.

        The register's constructive half: refusing a confirmation is only
        useful if it can also say where a clean one could run.
        """
        seen: set[str] = set()
        for rec in self.records:
            try:
                other = SliceIdentity(**rec.identity)
            except TypeError:
                continue
            if other.outcome_horizon_days != identity_template.outcome_horizon_days:
                continue
            lo = max(identity_template.start, other.start)
            hi = min(identity_template.end, other.end)
            if lo <= hi:
                seen.update(other.securities)
        return sorted({s.upper() for s in pool} - seen)
