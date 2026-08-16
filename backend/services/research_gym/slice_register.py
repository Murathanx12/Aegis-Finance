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

AND THE BINDING COORDINATE WAS THE CALENDAR (R13e, 2026-08-16)
==============================================================
The paragraph above was written the same day N9's confirmation was withdrawn,
and it is exactly one axis short. `overlaps` requires shared securities AND an
overlapping period, so a confirmation on *fresh tickers over the same calendar*
is clean by construction — which is precisely what N9's Amendment 1 was, and
precisely why nothing refused it:

    rules selected on SPY/XLF/XLE through 2015, confirmed on
    DIA XLV XLI XLP XLU XLB over 1999-2026

    1999-2015, calendar-OVERLAPPING : lift 1.464, p = 0.010
    2016+,     calendar-disjoint    : lift 0.765, p = 0.771

Different tickers, the same 2008, the same 2011, the same 2015. So there is a
second refusal, on a second axis, and it ignores securities entirely:

    a CONFIRM may not read a calendar its own LINEAGE has already read.

Lineage, not "anybody" — otherwise the first EXPLORE at a horizon would spend
the calendar for every unrelated mechanism forever, which is a guard nobody
would keep. `parents` is therefore required for a CONFIRM and refused when
absent, and the trial's OWN prior searching consumptions are added to it
without being declared, because that half is derivable and a declaration that
can be omitted will be.

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
import math
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
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

#: Purposes that consume a calendar for their lineage's future confirmations.
#: A FOREIGN evaluation is still looking at the data; a PAIRED/REANALYSIS is
#: reading data already spent. Only CONFIRM is excluded, because a lineage
#: re-reading its own confirmation is the rerun case, handled separately.
SEARCHING_PURPOSES = ("EXPLORE", "FOREIGN", "TRANSFER", "REANALYSIS", "PAIRED")

#: Trading days -> calendar days, plus a holiday/weekend buffer. Duplicated in
#: `Aegis module`'s `prereg_power.required_gap_days` and pinned by
#: `test_the_gap_constant_matches_the_register` — the linter lives in the other
#: repository and a gap that drifts between them is a gate that disagrees with
#: itself. 1.5x calendar days was MEASURED failing on 15.7% of 20-bar
#: boundaries against the real NYSE calendar (`audit_temporal_lineage`).
CALENDAR_DAYS_PER_TRADING_DAY = 7.0 / 5.0
HOLIDAY_BUFFER_DAYS = 14


def required_gap_days(horizon_days: float | None) -> int:
    """Calendar days a confirmation must start after its lineage's reads end.

    Zero overlap is necessary and not sufficient: labels run forward, so the
    last rows of a spent window carry outcomes formed inside the next one.
    Registration-time arithmetic — `research_gym.lineage` derives the exact
    boundary from the index at run time and this does not replace it.
    """
    if not horizon_days or horizon_days <= 0:
        return 0
    return int(math.ceil(float(horizon_days) * CALENDAR_DAYS_PER_TRADING_DAY)
               + HOLIDAY_BUFFER_DAYS)


def _shift(iso: str, days: int) -> str:
    y, m, d = (int(x) for x in iso.split("-")[:3])
    return (date(y, m, d) + timedelta(days=days)).isoformat()


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

    def calendar_overlaps(self, other: "SliceIdentity",
                          gap_days: int | None = None) -> dict:
        """Do these two read the same CALENDAR at the same horizon?

        Securities are deliberately not consulted. That is the whole point:
        N9's confirmation shared no security with its selection slices and
        shared seventeen years with them, and `overlaps` — which requires
        both — called that clean.

        `gap_days` extends the spent window forward by the horizon's calendar
        reach, so a confirmation starting the day after a spent window is
        caught too. Defaults to `required_gap_days(self.outcome_horizon_days)`.
        """
        if self.outcome_horizon_days != other.outcome_horizon_days:
            return {"calendar_overlaps": False, "same_horizon": False,
                    "overlap_start": None, "overlap_end": None, "gap_days": None}
        if gap_days is None:
            gap_days = required_gap_days(self.outcome_horizon_days)
        # Only the OTHER (already spent) window is extended: its labels reach
        # forward into whatever follows it. Extending both would refuse a
        # confirmation that legitimately precedes the spent window by more
        # than one label's reach.
        o_end = _shift(other.end, gap_days) if gap_days else other.end
        lo = max(self.start, other.start)
        hi = min(self.end, o_end)
        hit = lo <= hi
        return {"calendar_overlaps": bool(hit), "same_horizon": True,
                "overlap_start": lo if hit else None,
                "overlap_end": hi if hit else None,
                "gap_days": gap_days,
                "within_gap_only": bool(hit and lo > other.end)}


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

    def lineage_readers(self, identity: SliceIdentity,
                        lineage: Iterable[str]) -> list[tuple[Consumption, dict]]:
        """Consumptions BY THIS LINEAGE that touch this slice's calendar.

        Securities ignored (that is the R13e axis), CONFIRMs excluded (a
        lineage re-reading its own confirmation is the rerun case), horizon
        matched. Returns each hit with the overlap detail so a refusal can name
        the years rather than assert a conclusion.
        """
        names = {n for n in lineage if n}
        out: list[tuple[Consumption, dict]] = []
        for rec in self.records:
            if rec.trial not in names or rec.purpose not in SEARCHING_PURPOSES:
                continue
            try:
                other = SliceIdentity(**rec.identity)
            except TypeError:
                continue
            hit = identity.calendar_overlaps(other)
            if hit["calendar_overlaps"]:
                out.append((rec, hit))
        return out

    def calendar_clean_after(self, identity: SliceIdentity,
                             lineage: Iterable[str]) -> str | None:
        """The earliest date at which this lineage's calendar is unread.

        The constructive half of the R13e refusal, and the answer the slice
        register could not give when it named ten "clean" candidates: they were
        clean on the securities axis and unexamined on this one.

        None when the lineage has read nothing at this horizon.
        """
        ends = [SliceIdentity(**rec.identity).end
                for rec in self.records
                if rec.trial in set(lineage) and rec.purpose in SEARCHING_PURPOSES
                and rec.identity.get("outcome_horizon_days")
                == identity.outcome_horizon_days]
        if not ends:
            return None
        return _shift(max(ends),
                      required_gap_days(identity.outcome_horizon_days) + 1)

    # ── the guard ──────────────────────────────────────────────────────────
    def check(self, identity: SliceIdentity, purpose: str, *,
              trial: str = "", declared_non_independent: bool = False,
              parents: Sequence[str] | None = None) -> dict:
        """May `trial` read this slice for `purpose`?

        Returns the verdict rather than only raising, so a caller can print it;
        `claim` raises on the same condition so a caller cannot ignore it.

        `parents` names the trials whose data selected what is being confirmed.
        A CONFIRM must pass it — `()` is the declaration that nothing in this
        register chose the rule, and silence is refused rather than read as
        `()`, because the design that will not declare a parent is the one
        whose parent matters.
        """
        purpose = purpose.upper()
        if purpose not in PURPOSES:
            raise ValueError(f"unknown purpose {purpose!r}; declared: {PURPOSES}")

        readers = self.prior_readers(identity)

        # A trial re-running its OWN analysis is one consumption, not two.
        # Without this the register refuses the author who claimed the slice
        # correctly — which is not integrity, it is a trial that can never add
        # a diagnostic to its own registered result without an escape hatch,
        # and an escape hatch is what actually gets abused. Anyone ELSE
        # reading it is still refused; that is the property being protected.
        if readers and all(r.trial == trial for r in readers) and trial:
            return {"allowed": True, "purpose": purpose,
                    "slice_id": identity.slice_id,
                    "prior_readers": [r.trial for r in readers],
                    "why": (f"{trial} re-reading the slice it already claimed "
                            f"— one consumption, not a new one. This does NOT "
                            f"license a new claim: any result must be reported "
                            f"under the original pre-registration."),
                    "rerun_of_own_claim": True}

        if purpose != "CONFIRM":
            return {"allowed": True, "purpose": purpose,
                    "slice_id": identity.slice_id,
                    "prior_readers": [r.trial for r in readers],
                    "why": ("no prior reader" if not readers else
                            f"{purpose} does not require an unread slice")}

        # ── R13e: the calendar axis, checked BEFORE the securities axis ─────
        # Before, because this is the one that fires when the securities axis
        # is clean — which is the case it exists for. N9's confirmation had no
        # prior reader at all and was still reading its own selection window
        # under different tickers.
        if parents is None:
            return {
                "allowed": False, "purpose": purpose, "axis": "LINEAGE",
                "slice_id": identity.slice_id,
                "prior_readers": [r.trial for r in readers],
                "verdict": "UNDECLARED_LINEAGE",
                "why": ("CONFIRM refused: `parents` not declared. Name the "
                        "trials whose data selected the thing being confirmed, "
                        "or pass `()` to state that none in this register did. "
                        "Silence is not `()`: a guard whose input is on the "
                        "honour system is not a guard, and the calendar check "
                        "cannot run without knowing whose calendar to check."),
            }

        lineage = set(parents) | ({trial} if trial else set())
        confounds = self.lineage_readers(identity, lineage)
        if confounds and not declared_non_independent:
            years = "; ".join(
                f"{rec.trial} ({rec.purpose}) "
                f"{rec.identity.get('start')}..{rec.identity.get('end')} "
                f"-> shares {hit['overlap_start']}..{hit['overlap_end']}"
                + (" (inside the label reach, not the window)"
                   if hit.get("within_gap_only") else "")
                for rec, hit in confounds)
            clean_from = self.calendar_clean_after(identity, lineage)
            return {
                "allowed": False, "purpose": purpose, "axis": "CALENDAR",
                "slice_id": identity.slice_id,
                "prior_readers": [r.trial for r in readers],
                "calendar_confounds": [rec.trial for rec, _ in confounds],
                "verdict": "CALENDAR_CONFOUNDED",
                "clean_from": clean_from,
                "why": (
                    f"CONFIRM refused on the CALENDAR axis: this lineage has "
                    f"already read these dates at horizon "
                    f"{identity.outcome_horizon_days}d — {years}. Different "
                    f"securities do not make it different data when the "
                    f"securities co-move: N9 scored 1.464 (p=0.010) on the "
                    f"half of its confirmation that overlapped selection and "
                    f"0.765 (p=0.771) on the half that did not. "
                    + (f"A clean window starts {clean_from}."
                       if clean_from else "")),
            }
        if confounds and declared_non_independent:
            return {
                "allowed": True, "purpose": purpose, "axis": "CALENDAR",
                "slice_id": identity.slice_id,
                "prior_readers": [r.trial for r in readers],
                "calendar_confounds": [rec.trial for rec, _ in confounds],
                "why": ("calendar already read by this lineage, but the "
                        "pre-registration declares this non-independent — it "
                        "may NOT be reported as confirmation or transfer"),
                "may_claim_confirmation": False,
            }

        if not readers:
            return {"allowed": True, "purpose": purpose,
                    "slice_id": identity.slice_id, "prior_readers": [],
                    "axis": "CALENDAR+SECURITIES",
                    "why": ("no prior reader, and no calendar read by "
                            + (f"lineage {sorted(lineage)}" if lineage
                               else "any declared lineage"))}

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
              parent_hypotheses: Sequence[str] | None = None, note: str = "",
              declared_non_independent: bool = False) -> Consumption:
        """Check, then record. Raises `SliceRefusal` if the check refuses.

        `consumed_at` is passed in rather than read from the clock, because a
        register that stamps its own times cannot be replayed or tested.

        `parent_hypotheses` defaults to None rather than `()` since R13e: for a
        CONFIRM those are two different statements — "nothing selected this"
        versus "nobody said" — and the default used to make the second silently
        become the first.
        """
        # The declared parents ARE the lineage — one field, not two, so a
        # trial cannot pass the calendar check with a lineage it does not
        # record. `None` stays `None`: a CONFIRM that declares no parents is
        # refused rather than silently treated as parentless.
        verdict = self.check(
            identity, purpose, trial=trial,
            declared_non_independent=declared_non_independent,
            parents=(list(parent_hypotheses)
                     if parent_hypotheses is not None else None))
        if not verdict["allowed"]:
            raise SliceRefusal(verdict["why"])

        rec = Consumption(
            slice_id=identity.slice_id, identity=asdict(identity),
            trial=trial, purpose=purpose.upper(), consumed_at=consumed_at,
            prereg=prereg, parent_hypotheses=list(parent_hypotheses or ()),
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

        CLEAN ON ONE AXIS. This answers "which tickers are unread", which is
        the question N9 asked and passed. It says nothing about whether the
        CALENDAR those tickers would be scored over is unread — and that is
        the axis that carried N9's 1.271. Ten candidates named by this method
        on 2026-08-16 were reported as clean and were unexamined here. Use
        `clean_confirmation_windows` for the answer that spans both.
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

    def clean_confirmation_windows(self, pool: Iterable[str],
                                   identity_template: SliceIdentity,
                                   lineage: Iterable[str]) -> dict:
        """Where a clean CONFIRM could actually run — both axes, named.

        `unread_candidates` answers the securities axis. This answers it beside
        the calendar axis, because "clean" reported on one axis is how N9's
        confirmation was designed and how ten replacement candidates were
        offered afterwards. A caller that wants one number still has to read
        which coordinate it belongs to.
        """
        lineage = sorted({n for n in lineage if n})
        clean_from = self.calendar_clean_after(identity_template, lineage)
        unread = self.unread_candidates(pool, identity_template)
        window_ok = clean_from is None or clean_from <= identity_template.end
        return {
            "securities_axis": {
                "unread": unread,
                "spent": sorted({s.upper() for s in pool} - set(unread)),
            },
            "calendar_axis": {
                "lineage": lineage,
                "clean_from": clean_from,
                "requested_window": [identity_template.start,
                                     identity_template.end],
                "window_is_clean": bool(window_ok
                                        and identity_template.start
                                        >= (clean_from or "")),
                "usable_window": ([max(identity_template.start,
                                       clean_from or ""),
                                   identity_template.end]
                                  if window_ok else None),
                "gap_days": required_gap_days(
                    identity_template.outcome_horizon_days),
            },
            "why": ("A candidate is only clean where BOTH read clean. Unread "
                    "tickers over a spent calendar is what N9 confirmed on: "
                    "1.464 (p=0.010) overlapping, 0.765 (p=0.771) disjoint."),
        }
