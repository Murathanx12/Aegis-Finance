"""The research lab's verdicts, as an object the portfolio manager can obey.

A finding written only in prose is a finding the code can ignore. This module
loads `backend/data/signal_registry.yaml` and turns it into two enforceable
questions:

    permits(signal_id, role)   -> may this signal play this role, right now?
    weight(signal_id)          -> how much of its contribution survives?

and one that matters more than either:

    check_closed(signal_id)    -> raise if a CLOSED mechanism is being used

The last one exists because the failure it prevents is not a wrong number, it
is a dead strategy walking back in under a new name. `inst_ownership_level_13f`
is closed; a future `follow_the_smart_money` that computes the same thing would
pass every test in this repo. What stops it is that a new mechanism must
declare `distinct_from` and name the corpse it is not.

UNCALIBRATED IS NOT PERFECT. `reliability_weight: null` means nobody has
measured this. It resolves to UNKNOWN (0.5), never to 1.0 — BUILD-1.1 found
that exact bug in the evidence layer, where an uncovered name scored above one
that had been upgraded yesterday.

The registry never AMPLIFIES. Every weight is in [0, 1] and multiplies a
contribution the engine computed on its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "signal_registry.yaml"

#: A signal nobody has calibrated is UNKNOWN, and unknown is the middle of the
#: range — not the top of it.
UNCALIBRATED = 0.5

ROLES = {
    "PICKER", "FILTER", "VETO", "RISK_INPUT", "EXPECTATION_SENSOR",
    "CATALYST_SENSOR", "ALLOCATOR", "CLOSED",
}

GRADES = {
    "VALIDATED", "SUPPORTED", "SHELF", "OBSERVATIONAL", "HYPOTHESIS",
    "REJECTED", "PERVERSE",
}

#: Grades that may never carry a role that chooses or promotes a name, no
#: matter what the YAML says. Belt and braces: the enforcement does not depend
#: on whoever edits the file getting `permitted_role` right.
NEVER_PICKS = {"REJECTED", "PERVERSE"}

PROMOTING_ROLES = {"PICKER"}


class ClosedSignalError(RuntimeError):
    """A closed mechanism was about to be used. This is not recoverable."""


class RegistryError(ValueError):
    """The registry itself is malformed. Loud, because everything reads it."""


@dataclass
class Signal:
    signal_id: str
    family: str = ""
    mechanism: str = ""
    description: str = ""
    research_status: str = ""
    evidence_grade: str = "OBSERVATIONAL"
    permitted_role: str = "CLOSED"
    allowed_in_pm: bool = False
    reliability_weight: Optional[float] = None
    horizon: str = ""
    universe: str = ""
    data_grade: str = ""
    known_effect: Optional[str] = None
    known_failure: Optional[str] = None
    receipts: list[str] = field(default_factory=list)
    implementation_notes: str = ""
    distinct_from: list[str] = field(default_factory=list)
    last_updated: str = ""

    @property
    def calibrated(self) -> bool:
        return self.reliability_weight is not None

    @property
    def weight(self) -> float:
        """Bounded multiplier. Uncalibrated resolves to UNKNOWN, not to 1."""
        if self.reliability_weight is None:
            return UNCALIBRATED
        return max(0.0, min(1.0, float(self.reliability_weight)))

    @property
    def is_closed(self) -> bool:
        """Adjudicated and killed. NOT the same as 'not yet permitted'.

        A HYPOTHESIS is `allowed_in_pm: false` because it has not been run —
        it is queued, and it may graduate. A CLOSED mechanism has been run and
        killed, and the re-litigation ban applies to it. Collapsing the two
        would make every unrun idea look like a corpse and every corpse look
        like an unrun idea, which is exactly the confusion this file exists to
        remove.
        """
        return self.permitted_role == "CLOSED"

    @property
    def usable_now(self) -> bool:
        """May the PM read this signal today?"""
        return self.allowed_in_pm and not self.is_closed

    @property
    def queued(self) -> bool:
        """Registered, not killed, not yet permitted — the graduation queue."""
        return not self.is_closed and not self.allowed_in_pm

    def label(self) -> str:
        """The five-word version a brief can print beside a number."""
        cal = "" if self.calibrated else ", UNCALIBRATED"
        return f"{self.evidence_grade}/{self.permitted_role}{cal}"


@dataclass
class Registry:
    schema: str
    written: str
    signals: dict[str, Signal]
    standing_constraints: list[dict] = field(default_factory=list)
    source_of_truth: str = ""

    def get(self, signal_id: str) -> Signal:
        try:
            return self.signals[signal_id]
        except KeyError:
            raise RegistryError(
                f"unknown signal {signal_id!r}. A signal the PM uses must be "
                f"registered before it can be used — an unregistered signal has "
                f"no evidence grade, and an ungraded number in a brief is "
                f"indistinguishable from a validated one."
            ) from None

    def permits(self, signal_id: str, role: str) -> bool:
        """May this signal play this role in the PM today?"""
        if role not in ROLES:
            raise RegistryError(f"unknown role {role!r}; expected one of {sorted(ROLES)}")
        s = self.get(signal_id)
        if not s.usable_now:
            return False
        if s.evidence_grade in NEVER_PICKS and role in PROMOTING_ROLES:
            return False
        return s.permitted_role == role

    def check_closed(self, signal_id: str) -> None:
        """Raise if a closed mechanism is about to be used. Call it early."""
        s = self.get(signal_id)
        if s.is_closed:
            raise ClosedSignalError(
                f"{signal_id} is CLOSED ({s.evidence_grade}). "
                f"{(s.known_effect or '').strip()[:200]} "
                f"Receipts: {'; '.join(s.receipts[:2])}. "
                f"A closed mechanism may not re-enter under a new name; register "
                f"a genuinely different mechanism with `distinct_from: "
                f"[{signal_id}]` and an arm that IS this corpse, so the "
                f"increment over it is what gets measured."
            )

    def weight(self, signal_id: str) -> float:
        return self.get(signal_id).weight

    def by_role(self, role: str) -> list[Signal]:
        return sorted((s for s in self.signals.values()
                       if s.permitted_role == role and s.usable_now),
                      key=lambda s: s.signal_id)

    def closed(self) -> list[Signal]:
        """Adjudicated and killed. The re-litigation ban applies to these."""
        return sorted((s for s in self.signals.values() if s.is_closed),
                      key=lambda s: s.signal_id)

    def queued(self) -> list[Signal]:
        """Registered and alive, but not yet permitted — the graduation queue."""
        return sorted((s for s in self.signals.values() if s.queued),
                      key=lambda s: s.signal_id)

    def pm_allowed(self) -> list[Signal]:
        return sorted((s for s in self.signals.values() if s.usable_now),
                      key=lambda s: s.signal_id)

    def uncalibrated(self) -> list[Signal]:
        return sorted((s for s in self.pm_allowed() if not s.calibrated),
                      key=lambda s: s.signal_id)

    def summary(self) -> dict:
        from collections import Counter
        return {
            "schema": self.schema,
            "written": self.written,
            "n_signals": len(self.signals),
            "n_allowed_in_pm": len(self.pm_allowed()),
            "n_closed": len(self.closed()),
            "n_queued": len(self.queued()),
            "n_uncalibrated": len(self.uncalibrated()),
            "by_grade": dict(Counter(s.evidence_grade for s in self.signals.values())),
            "by_role": dict(Counter(s.permitted_role for s in self.signals.values())),
            "standing_constraints": [c["id"] for c in self.standing_constraints],
        }


def _validate(sig: Signal, seen: set[str]) -> list[str]:
    """Everything wrong with one entry. A registry that lies is worse than none."""
    bad: list[str] = []
    if not sig.signal_id:
        bad.append("a signal has no signal_id")
        return bad
    if sig.signal_id in seen:
        bad.append(f"{sig.signal_id}: duplicated")
    if sig.evidence_grade not in GRADES:
        bad.append(f"{sig.signal_id}: unknown evidence_grade "
                   f"{sig.evidence_grade!r} (expected {sorted(GRADES)})")
    if sig.permitted_role not in ROLES:
        bad.append(f"{sig.signal_id}: unknown permitted_role {sig.permitted_role!r}")
    if sig.reliability_weight is not None:
        try:
            w = float(sig.reliability_weight)
        except (TypeError, ValueError):
            bad.append(f"{sig.signal_id}: reliability_weight is not a number")
        else:
            if not (0.0 <= w <= 1.0):
                bad.append(f"{sig.signal_id}: reliability_weight {w} outside "
                           f"[0,1] — the registry discounts, it never amplifies")
    # The rule the whole file exists to enforce.
    if sig.evidence_grade in NEVER_PICKS and sig.permitted_role in PROMOTING_ROLES:
        bad.append(f"{sig.signal_id}: graded {sig.evidence_grade} but given the "
                   f"role {sig.permitted_role} — a killed mechanism may not pick")
    if sig.evidence_grade in NEVER_PICKS and sig.allowed_in_pm and sig.weight > 0.5:
        bad.append(f"{sig.signal_id}: graded {sig.evidence_grade} yet allowed in "
                   f"the PM at weight {sig.weight}")
    if sig.evidence_grade in {"VALIDATED", "SUPPORTED", "REJECTED", "PERVERSE"} \
            and not sig.receipts:
        bad.append(f"{sig.signal_id}: graded {sig.evidence_grade} with no "
                   f"receipts — a verdict without a receipt is an opinion")
    return bad


@lru_cache(maxsize=4)
def load(path: str | None = None) -> Registry:
    """Load and VALIDATE the registry. A malformed registry raises."""
    p = Path(path or REGISTRY_PATH)
    if not p.exists():
        raise RegistryError(f"signal registry not found at {p}")
    try:
        raw: Any = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a parse failure must be loud
        raise RegistryError(f"signal registry did not parse: {exc}") from exc
    if not isinstance(raw, dict) or "signals" not in raw:
        raise RegistryError("signal registry has no `signals:` list")

    signals: dict[str, Signal] = {}
    problems: list[str] = []
    seen: set[str] = set()
    for entry in raw["signals"]:
        if not isinstance(entry, dict):
            problems.append(f"non-mapping entry: {entry!r}")
            continue
        known = {f for f in Signal.__dataclass_fields__}
        unknown = set(entry) - known
        if unknown:
            problems.append(f"{entry.get('signal_id')}: unknown field(s) "
                            f"{sorted(unknown)} — a typo silently drops a verdict")
        sig = Signal(**{k: v for k, v in entry.items() if k in known})
        problems.extend(_validate(sig, seen))
        seen.add(sig.signal_id)
        signals[sig.signal_id] = sig

    # A `distinct_from` must point at something real, or the whole
    # not-re-litigation claim is unverifiable.
    for sig in signals.values():
        if sig.evidence_grade == "HYPOTHESIS" and sig.is_closed:
            problems.append(
                f"{sig.signal_id}: graded HYPOTHESIS but given permitted_role "
                f"CLOSED. A hypothesis is queued, not killed — give it the role "
                f"it would play IF it resolves, and gate it with allowed_in_pm.")
        for corpse in sig.distinct_from:
            if corpse not in signals:
                problems.append(
                    f"{sig.signal_id}: distinct_from names {corpse!r}, which is "
                    f"not in the registry — the corpse it claims not to be must "
                    f"exist for the claim to mean anything")
            elif not signals[corpse].is_closed:
                problems.append(
                    f"{sig.signal_id}: distinct_from names {corpse!r}, which is "
                    f"not closed")

    if problems:
        raise RegistryError(
            "the signal registry is malformed and nothing may read it:\n  - "
            + "\n  - ".join(problems))

    return Registry(schema=raw.get("schema", ""), written=str(raw.get("written", "")),
                    signals=signals,
                    standing_constraints=list(raw.get("standing_constraints") or []),
                    source_of_truth=raw.get("source_of_truth", ""))


# ─────────────────────────── convenience wrappers ───────────────────────────

def permits(signal_id: str, role: str) -> bool:
    return load().permits(signal_id, role)


def check_closed(signal_id: str) -> None:
    load().check_closed(signal_id)


def weight(signal_id: str) -> float:
    return load().weight(signal_id)


def label(signal_id: str) -> str:
    return load().get(signal_id).label()


def evidence_lines(signal_ids: list[str]) -> list[str]:
    """One printable line per signal, for the brief's evidence block."""
    reg = load()
    out: list[str] = []
    for sid in signal_ids:
        try:
            s = reg.get(sid)
        except RegistryError:
            out.append(f"  {sid:34s} NOT REGISTERED — ungraded, do not act on it")
            continue
        note = (s.known_failure or s.known_effect or "").strip().split("\n")[0]
        out.append(f"  {sid:34s} {s.label():34s} {note[:70]}")
    return out
