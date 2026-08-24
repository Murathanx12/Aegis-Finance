"""P0.2, part two — book identity that carries only what the book CONSUMES.

WHY THIS EXISTS
===============
`information_bus` shipped the registry and the fingerprint, and the tests
proved the fingerprint moves for the right reasons. But nothing consumed it:
`spec.book_fingerprint` still ended with the bare global

    parts = [book_config_payload(book_id, raw), COMPOSITE_VERSION]

so the bus was an AUDIT surface, not a dependency. Two consequences, and the
second is the one that blocks the roadmap:

1. Admitting a family to `COMPOSITE_WEIGHTS` re-identified the composite books
   only if somebody remembered to hand-bump `COMPOSITE_VERSION`. The registry
   knew; identity did not ask it.
2. A future `EVENT_RESPONSE_v1` — which reads options and event state and not
   one column of the composite — would have been re-identified every time the
   momentum composite changed, because `COMPOSITE_VERSION` was global. The
   whole point of "a new mechanism arrives as its own book" is that the books
   are independent; identity that couples them all makes that false.

THE SHAPE
=========
    book fingerprint = book config
                     + SELECTOR IDENTITY  <- this module
                     + router identity, if consumed
                     (+ execution-policy identity, when one exists)

and selector identity is itself two separable things, which is the part that
matters:

    ALGORITHM version   what the estimator MEANS. `arena_composite@3-...`.
                        Hand-declared, because "we changed how the z-scores are
                        blended" is not derivable from any input list.
    DEPENDENCY prints   WHICH information families it reads, and — for the
                        composite — the WEIGHTS it reads them at. Derived, never
                        declared, so it cannot be forgotten.

Both are required. Families alone would miss a re-weighting; the version alone
is what we already had, and it is only as reliable as the person editing it.

WHY EVERY BOOK'S FINGERPRINT IS BYTE-IDENTICAL TODAY
====================================================
The nine live books were seeded 2026-08-21 under `payload|COMPOSITE_VERSION`.
Appending anything unconditionally would re-identify all nine, and — because
they are still on the LEGACY whole-file scheme and migrate to per-book identity
on their next arena pass — would strand them behind `assert_config_current`.

So each dependency print contributes ONLY when it differs from the value the
live seeds were sealed under. This is the same two-axis scoping
`ROUTER_FINGERPRINT_BASELINE` already uses one file over, for the same reason
and with the same rule attached: **the baselines below record history and must
never be "updated" to track the current value.** Updating one silently
re-baselines the drift it exists to catch.

A selector with no seeded book (`baseline=None`) has no history to protect, so
its prints always contribute.
"""

from __future__ import annotations

import json


from backend.services.arena import information_bus


class SelectorNotDeclared(RuntimeError):
    """A book selects with something this module has no dependency map for.

    Refused rather than defaulted, and that refusal is the feature. The obvious
    fallback — "unknown selector, use the composite's identity" — is exactly
    the bug: an EVENT_RESPONSE book would silently inherit momentum's
    dependencies and drift whenever the composite moved, while every hash
    verified. A new selector must say what it reads before it can be run.
    """


def composite_weight_fingerprint() -> str:
    """Identity of the composite's WEIGHTS, not just its family names.

    `information_bus.composite_fingerprint()` moves when a family is admitted or
    removed. It does NOT move when `mom_12_1: 1.0` becomes `mom_12_1: 2.0` —
    same names, different policy, and today the only thing standing between
    that edit and ten un-drifted NAV series is whether the editor also bumped a
    string. That is the defect the review named for families; it is the same
    defect for weights.
    """
    from backend.services.arena.discovery import COMPOSITE_WEIGHTS

    payload = json.dumps(sorted((k, float(v))
                                for k, v in COMPOSITE_WEIGHTS.items()),
                         separators=(",", ":"))
    import hashlib
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _composite_algorithm_parts() -> list[str]:
    from backend.services.arena.discovery import COMPOSITE_VERSION
    return [COMPOSITE_VERSION]


#: The composite's admitted-family fingerprint at the 2026-08-21 seeding.
#: HISTORY, not a mirror of the current value — see the module docstring.
COMPOSITE_FAMILIES_BASELINE = "7418cb394c109879"

#: The composite's weight fingerprint at the same seeding. Same rule.
COMPOSITE_WEIGHTS_BASELINE = "41b4bbfa5d3df8c8"


#: THE DECLARED SELECTORS. Keyed by `defaults.selection_signal`, which is what
#: `policies.select` actually reads — the per-book `selection:` field is
#: descriptive (`spec.DESCRIPTIVE_BOOK_KEYS`), so keying on it would have made
#: this registry agree with a string nothing consumes.
SELECTORS: dict[str, dict] = {
    "arena_composite": {
        "algorithm": _composite_algorithm_parts,
        "dependencies": {
            "families": (lambda: information_bus.composite_fingerprint(),
                         COMPOSITE_FAMILIES_BASELINE),
            "weights": (composite_weight_fingerprint,
                        COMPOSITE_WEIGHTS_BASELINE),
        },
        "reads": lambda: information_bus.families(
            information_bus.ADMITTED_TO_COMPOSITE),
        "why": ("the arena's own z-score blend over the arena's own universe. "
                "Nine live books select on this and only this — the bottleneck "
                "the roadmap named."),
    },
}


def assert_declared(selection_signal: str) -> dict:
    if selection_signal not in SELECTORS:
        raise SelectorNotDeclared(
            f"selection_signal {selection_signal!r} has no entry in "
            f"selector_identity.SELECTORS, so there is no way to know which "
            f"information families its books consume. Declare it — with the "
            f"families it reads and baseline=None (it has no seeded history) — "
            f"before a book may select on it. Declared: {sorted(SELECTORS)}")
    return SELECTORS[selection_signal]


def selector_identity_parts(selection_signal: str) -> list[str]:
    """The fingerprint components a book selecting on this signal must carry.

    Ordered and prefixed, so a future reader of a hash preimage can tell an
    algorithm bump from a family admission.
    """
    spec = assert_declared(selection_signal)
    parts = list(spec["algorithm"]())
    for key, (fn, baseline) in sorted(spec["dependencies"].items()):
        value = fn()
        if value != baseline:
            parts.append(f"{key}:{value}")
    return parts


def selector_identity(selection_signal: str) -> str:
    """One string, for receipts and health. Not the fingerprint input."""
    return "|".join(selector_identity_parts(selection_signal))


def describe(selection_signal: str) -> dict:
    spec = assert_declared(selection_signal)
    return {
        "selection_signal": selection_signal,
        "algorithm": spec["algorithm"](),
        "reads": spec["reads"](),
        "dependencies": {k: fn() for k, (fn, _) in spec["dependencies"].items()},
        "at_seed_baseline": {k: (fn() == b)
                             for k, (fn, b) in spec["dependencies"].items()},
        "identity_parts": selector_identity_parts(selection_signal),
    }


def assert_books_declare_known_selectors(path=None) -> dict:
    """Every book in the config must select on a DECLARED selector.

    The counterpart to `information_bus.assert_registry_matches_code`: that one
    checks the families the state carries, this one checks that every book's
    selector has a dependency map at all. Between them, no book can consume an
    input whose identity nothing tracks.
    """
    import yaml

    from backend.services.arena.spec import CONFIG_PATH

    raw = yaml.safe_load((path or CONFIG_PATH).read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    out: dict[str, str] = {}
    for book_id in sorted((raw.get("books") or {})):
        signal = str((raw["books"][book_id] or {}).get("selection_signal")
                     or defaults.get("selection_signal") or "arena_composite")
        assert_declared(signal)
        out[book_id] = signal
    return out


def health() -> dict:
    try:
        books = assert_books_declare_known_selectors()
        return {
            "status": "ok",
            "n_declared_selectors": len(SELECTORS),
            "books_by_selector": books,
            "selectors": {s: describe(s) for s in sorted(SELECTORS)},
        }
    except SelectorNotDeclared as e:
        return {"status": "UNDECLARED_SELECTOR", "reason": str(e)[:400]}
    except Exception as e:                                   # noqa: BLE001
        return {"status": "DEGRADED", "reason": f"{type(e).__name__}: {e}"}
