"""P0.2 — a versioned bus for admitting information into the frozen state.

THE PROBLEM THIS SOLVES
=======================
`SCORE_PREFIXES` in `discovery.py` is a bare module-level dict. Adding a key to
it silently widens the inputs of every book mid-trial, and nothing anywhere
records that it happened, when, or why. `information_state_hash` changes, but a
hash that changes for an undeclared reason tells a later reader only that
something moved.

The roadmap's constraint is the sharp part, and it is not the obvious one:

> the seeded books' `policy_fingerprint` must not change when a field they do
> not consume is added.

That constraint is what makes this hard, because today it is FALSE. Every
book's fingerprint carries `COMPOSITE_VERSION`, so any change to the estimator
drifts all ten at once. A book that never reads a new family would be forced to
re-identify itself because a different experiment gained an input.

THE DISTINCTION THAT MAKES IT WORK
==================================
Two different things get called "adding a factor", and conflating them is the
whole bug:

  ADMITTED_TO_COMPOSITE   the family enters `COMPOSITE_WEIGHTS` and therefore
                          changes what every composite-selecting book DECIDES.
                          Drifting those books is CORRECT — their policy really
                          did change, and a NAV series that spans the change
                          would describe two policies.

  ADMITTED_TO_STATE       the family is computed and frozen into the day state,
                          available for a future selector to read, and consumed
                          by NO current book. Nothing any book decides changes,
                          so nothing may drift. This is the case the roadmap is
                          protecting, and it is the case that lets a new
                          mechanism accumulate PIT history BEFORE its book
                          exists — which matters because history cannot be
                          backfilled for anything the vendor does not keep.

  CANDIDATE               declared, not yet computed. Present so that intent is
                          on the record before the code lands.

WHY A REGISTRY AND NOT A COMMENT
================================
`assert_registry_matches_code` refuses when the declared families and the ones
the code actually reads disagree in either direction. A family added to
`SCORE_PREFIXES` without a declaration is a red suite, not a discovery three
weeks later — the same rule `signal_reachability` enforces for modules, applied
to inputs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

#: Status values. See the module docstring for what each one licenses.
ADMITTED_TO_COMPOSITE = "ADMITTED_TO_COMPOSITE"
ADMITTED_TO_STATE = "ADMITTED_TO_STATE"
CANDIDATE = "CANDIDATE"

_VALID = frozenset({ADMITTED_TO_COMPOSITE, ADMITTED_TO_STATE, CANDIDATE})


#: THE DECLARED BUS. Every family the frozen information state may carry, with
#: the date it was admitted and the reason. Order is irrelevant; the version
#: hash sorts.
#:
#: `admitted_at` is the date the family first entered the state, NOT the date it
#: was written down. Backdating one would make a book look as though it had been
#: deciding on an input it did not have.
FAMILIES: dict[str, dict[str, Any]] = {
    "mom_12_1": {
        "status": ADMITTED_TO_COMPOSITE,
        "source": "arena-computed from the price panel",
        "admitted_at": "2026-08-20",
        "why": ("12-1 momentum, last month excluded — the anti-chase findings. "
                "This is the family 99.5% of names actually carry."),
    },
    "multifactor": {
        "status": ADMITTED_TO_COMPOSITE,
        "source": "PIT store, prefix multifactor_score:",
        "admitted_at": "2026-08-20",
        "why": "registered collector; itself momentum+insider+revisions",
    },
    "revisions": {
        "status": ADMITTED_TO_COMPOSITE,
        "source": "PIT store, prefix revisions_score:",
        "admitted_at": "2026-08-20",
        "why": "registered collector",
    },
    "insider_opp": {
        "status": ADMITTED_TO_COMPOSITE,
        "source": "PIT store, prefix insider_opp:",
        "admitted_at": "2026-08-20",
        "why": "registered collector",
    },
    "pead": {
        "status": ADMITTED_TO_COMPOSITE,
        "source": "PIT store, prefix pead_score:",
        "admitted_at": "2026-08-20",
        "why": "registered collector",
    },
    "quality": {
        "status": ADMITTED_TO_COMPOSITE,
        "source": "arena/fundamentals.py, arena's OWN universe",
        "admitted_at": "2026-08-23",
        "why": ("the PIT store's quality_score: covers only the ~12-name "
                "registered cross-section; mixing it with a universe-wide "
                "score would put two populations in one z-score"),
    },
    "insider_cmp": {
        "status": ADMITTED_TO_STATE,
        "source": "PIT store, prefix insider_cmp:",
        "admitted_at": "2026-08-20",
        "why": ("read into the state but carries NO composite weight — the "
                "companion to insider_opp, kept visible so a later selector "
                "can use it without a backfill it cannot have"),
    },
}


def _canonical(status_filter: set[str] | None = None) -> str:
    items = {k: v for k, v in FAMILIES.items()
             if status_filter is None or v["status"] in status_filter}
    return json.dumps(items, sort_keys=True, separators=(",", ":"),
                      default=str)


def bus_version() -> str:
    """Identity of the WHOLE declared bus, including candidates.

    Changes whenever anything about any family changes. This is the number that
    makes admitting a family a policy EVENT rather than a diff.
    """
    return hashlib.sha256(_canonical().encode()).hexdigest()[:16]


def composite_fingerprint() -> str:
    """Identity of only what a composite book DECIDES on.

    THE POINT OF THE MODULE. Deliberately blind to `ADMITTED_TO_STATE` and
    `CANDIDATE` families, so admitting a family no book consumes leaves this
    byte-identical and every seeded book keeps verifying under its inception.

    IT HASHES THE NAMES ONLY, NOT THE PROSE. The first version hashed the whole
    entry, which meant editing a `why` string re-identified every composite
    book — precisely the comment-only-edit defect that drifted 10 of 10 books on
    2026-08-23 and that per-book identity exists to prevent. A reason is
    documentation; the SET of families is policy. Prose still moves
    `bus_version`, which is the audit record and drifts nothing.
    """
    names = json.dumps(families(ADMITTED_TO_COMPOSITE), separators=(",", ":"))
    return hashlib.sha256(names.encode()).hexdigest()[:16]


def families(status: str | None = None) -> list[str]:
    return sorted(k for k, v in FAMILIES.items()
                  if status is None or v["status"] == status)


def state_families() -> list[str]:
    """Everything the frozen state should carry — composite plus state-only."""
    return sorted(k for k, v in FAMILIES.items()
                  if v["status"] in (ADMITTED_TO_COMPOSITE, ADMITTED_TO_STATE))


class BusDrift(RuntimeError):
    """The declared bus and the code that builds the state disagree.

    Refused rather than reconciled, because the two directions are different
    bugs and both are silent: a family in code but not declared is an
    undeclared widening of every book's inputs; a family declared but not in
    code is a book believing it decides on something it never sees.
    """


def assert_registry_matches_code() -> dict:
    """The declared bus must equal what `discovery` actually reads.

    Checked against the real code rather than a copy, so the two cannot drift.
    """
    from backend.services.arena.discovery import (COMPOSITE_WEIGHTS,
                                                  SCORE_PREFIXES)

    for name, spec in FAMILIES.items():
        if spec.get("status") not in _VALID:
            raise BusDrift(f"{name}: status {spec.get('status')!r} is not one "
                           f"of {sorted(_VALID)}")
        for field in ("source", "admitted_at", "why"):
            if not spec.get(field):
                raise BusDrift(f"{name}: missing {field} — a family admitted "
                               f"without a reason is exactly the silent "
                               f"widening this module exists to stop")

    # `mom_12_1` and `quality` are arena-computed, not PIT-store reads, so the
    # code-side set is the PIT prefixes PLUS those two.
    code_state = set(SCORE_PREFIXES) | {"mom_12_1", "quality"}
    declared_state = set(state_families())
    if code_state != declared_state:
        raise BusDrift(
            f"the frozen state reads {sorted(code_state)} but the bus declares "
            f"{sorted(declared_state)}. Undeclared: "
            f"{sorted(code_state - declared_state)}; declared but absent: "
            f"{sorted(declared_state - code_state)}. Admitting a family is a "
            f"policy event — declare it in FAMILIES with its reason.")

    code_composite = set(COMPOSITE_WEIGHTS)
    declared_composite = set(families(ADMITTED_TO_COMPOSITE))
    if code_composite != declared_composite:
        raise BusDrift(
            f"COMPOSITE_WEIGHTS carries {sorted(code_composite)} but the bus "
            f"declares {sorted(declared_composite)} as composite families. A "
            f"family that changes what books DECIDE must be "
            f"{ADMITTED_TO_COMPOSITE}, because that is what drifts their "
            f"identity — and drifting it is correct.")

    return {
        "bus_version": bus_version(),
        "composite_fingerprint": composite_fingerprint(),
        "n_composite": len(declared_composite),
        "n_state_only": len(families(ADMITTED_TO_STATE)),
        "n_candidate": len(families(CANDIDATE)),
        "state_families": sorted(declared_state),
    }


def health() -> dict:
    try:
        rep = assert_registry_matches_code()
    except BusDrift as e:
        return {"status": "DRIFTED", "reason": str(e)[:400]}
    except Exception as e:                                   # noqa: BLE001
        return {"status": "DEGRADED", "reason": f"{type(e).__name__}: {e}"}
    return {"status": "ok", **rep}
