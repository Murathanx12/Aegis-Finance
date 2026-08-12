"""The auto-adopted default kill conditions — ONE source for five texts.

NIGHT-13 §0 ruling: the five recovered names (ABSI, AMSC, HUBS, KYTX, SLDP)
arrived from the 2026-07-11 conviction log with no exit rule from any source.
NIGHT-10's mirror challenge proposed one per name and parked them as
PROPOSED_AWAITING_MURAT; Murat's NIGHT-13 ruling is that proposed kill
conditions AUTO-ADOPT as defaults rather than blocking on him — honestly
labelled, with provenance, and with an explicit empty `murat_override:` slot
he can fill at any time.

These texts previously lived verbatim in scripts/mirror_challenge.py and as
trivially divergent copies in docs (docs/NIGHT10_MIRROR_CHALLENGE.md and the
generated docs/BUILD1/mirror_challenge.json). This module is now the single
source; the docs are historical records of the proposal and are not edited.

HARD CONSTRAINT (signal_registry.yaml, trailing-stop corpse, CANON §15):
a kill condition is a THESIS label used for paper/shadow evaluation only.
It is never an armed exit, never a stop, never an order path. The PM may
PRINT it; nothing may EXECUTE it.
"""
from __future__ import annotations

#: Provenance vocabulary for a position's kill condition.
#:   "murat_stated"          — Murat wrote it (book file / conviction sheets)
#:   "auto_adopted_default"  — one of the five NIGHT-13 §0 defaults below
#:   ""                      — no kill condition on record
PROVENANCE_MURAT_STATED = "murat_stated"
PROVENANCE_AUTO_ADOPTED = "auto_adopted_default"

#: The five names that had no kill condition from any source.
NO_KILL_CONDITION_NAMES: tuple[str, ...] = ("ABSI", "AMSC", "HUBS", "KYTX",
                                            "SLDP")

#: The adopted default texts, verbatim from the NIGHT-10 mirror-challenge
#: proposal. Adopted as DEFAULTS by the NIGHT-13 ruling; Murat may override
#: any of them via the book file's `murat_override:` field, at which point the
#: override becomes murat_stated and the default retires for that name.
AUTO_ADOPTED_KILL_CONDITIONS: dict[str, str] = {
    "ABSI": "cash runway falls below 12 months, or a lead programme is "
            "discontinued without a named successor",
    "AMSC": "two consecutive quarters of declining grid-segment backlog, or "
            "the largest customer concentration exceeds 40% of revenue",
    "HUBS": "net revenue retention falls below 100% for two consecutive "
            "quarters",
    "KYTX": "a lead clinical programme misses its primary endpoint, or cash "
            "runway falls below 12 months",
    "SLDP": "a named OEM partnership lapses without replacement, or cash "
            "runway falls below 12 months",
}

#: What every consumer must print beside an adopted default.
AUTO_ADOPTED_NOTE = (
    "auto-adopted default (NIGHT-13 §0) — a THESIS label for paper/shadow "
    "evaluation only, never an armed exit or an order path. Murat may "
    "override it in the book file (`murat_override:`)."
)


def default_for(ticker: str) -> str:
    """The adopted default text for a ticker, or "" if none exists."""
    return AUTO_ADOPTED_KILL_CONDITIONS.get(str(ticker).upper(), "")
