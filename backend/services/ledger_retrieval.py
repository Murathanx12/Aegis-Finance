"""RETRIEVAL THAT CANNOT SEE HINDSIGHT (roadmap lane M, item M3).

THE FAILURE THIS CLOSES BEFORE IT CAN HAPPEN
============================================
The agent-memory literature (Reflexion, ExpeL, Voyager, FinCon, FactorMiner
2026) agrees on one mechanism — store graded experience and retrieve it — and on
one failure: **hindsight contamination.** A rule distilled from outcomes that
had not happened yet, retrieved into a prompt about an earlier date, makes the
model look like a forecaster and makes the backtest look like alpha. It is the
same defect as training on future information, moved one layer up into text.

M2's rule store does not exist yet. This module ships anyway, and that is
deliberate: the gate has to be in place BEFORE the first rule is written, or the
first rule will be retrieved by whatever code happens to be convenient, and the
leak will be discovered by someone reading a suspiciously good number.

THE PREDICATE HAS THREE CLAUSES, NOT ONE
========================================
A record `R` may be retrieved for a forecast about decision date `t` iff::

    R.resolution_date < t      # its window closed before t
    AND R.resolved_at is not None   # it was actually graded, not merely due
    AND R.resolved_at <= t          # and graded on or before t
    AND R.outcome is not None       # a voided record contributes nothing

`resolution_date < t` alone would admit a rule whose window closed before `t`
but that the resolver had not yet graded by `t` — the resolver runs on its own
cron, and `belief_state`'s own rule is that *grading early is indistinguishable
from being right early*. The retriever must respect the same asymmetry:
retrieving a not-yet-computed Brier is retrieving the future as surely as
retrieving the outcome would be. `resolved_at <= t` is the operative gate in
practice; `resolution_date < t` is stated separately so a future reader can see
why the gate is dated the way it is.

IT IS A PRE-FILTER, NEVER A POST-FILTER
=======================================
The filter shrinks the candidate POOL before any relevance ranking. A
post-filter that drops the top-ranked leaking result and returns the next one
changes WHICH rule is retrieved without that being visible to a test which only
asks "was a leaking rule in the final list". Pool size before and after is
testable; silent substitution is not.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    """The checkout, honouring `AEGIS_REPO_ROOT`.

    Not `Path(__file__)`-rooted: inside the packaged app `__file__` is under
    `_internal/`, which is empty, so a path built that way reads a directory
    that does not exist and returns nothing WITHOUT failing. Defect family #14;
    `test_frozen_path_family.py` is the gate, and it caught this module on its
    first suite run.
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


#: Where M2's distilled rules will live. Read-only from here; this module never
#: creates it, and its absence is an empty retrieval rather than an error.
LEARNED_RULES = (_repo_root() / "backend" / "data" / "optimus" / "brain"
                 / "learned_rules.jsonl")

#: The reason a candidate was dropped, per clause. Returned in the report so a
#: retrieval that came back thin can be explained without re-running it.
REASONS = ("unresolved_window", "never_graded", "graded_after_t", "voided",
           "no_resolution_date", "rule_not_scored_yet")


def _as_date(value: Any) -> date | None:
    """A date from an ISO date, an ISO datetime, or a `date`. None otherwise.

    Lenient on FORM and strict on PRESENCE: `2026-06-15`, `2026-06-15T09:00:00Z`
    and `date(2026, 6, 15)` are the same day and all three appear in this
    repository's ledgers, but an unparseable stamp is None and a None stamp
    fails the gate. A stamp the code cannot read must never be treated as old
    enough.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def visible_at(record: dict, t: date) -> tuple[bool, str | None]:
    """(may this record be retrieved for date `t`, why not).

    `computed_through_date` is honoured where present: a DISTILLED rule's own
    evidence horizon. M2's rules are forecasts about future forecasts and get
    the same gate as the records they were distilled from.
    """
    # ORDER MATTERS, and it is the order of the clauses in the spec.
    #
    # An explicit `void_reason` is a void. A missing `outcome` is checked LAST,
    # after the date gates, because "never graded" and "graded and voided" are
    # different facts and the first version of this function reported both as
    # `voided` -- which would have sent a future reader looking for a voiding
    # decision that never happened.
    if record.get("void_reason"):
        return False, "voided"
    res = _as_date(record.get("resolution_date")
                   or record.get("resolves_after")
                   or record.get("computed_through_date"))
    if res is None:
        return False, "no_resolution_date"
    if not res < t:
        return False, "unresolved_window"
    graded = _as_date(record.get("resolved_at") or record.get("graded_at"))
    if graded is None:
        return False, "never_graded"
    if graded > t:
        return False, "graded_after_t"
    if record.get("outcome") is None:
        # THE ONE DOCUMENTED EXCEPTION (M2, spec section 1.7). A DISTILLED RULE
        # has no single binary outcome -- `state` and `brier` carry what
        # `outcome` would carry for a forecast -- so `outcome is None` is its
        # normal condition and this branch would gate out every rule M2 ever
        # writes, i.e. the retrieval that this module exists to make safe would
        # instead return nothing, forever, silently.
        #
        # A rule row is identified by its own `schema_version` prefix, never by
        # the absence of a field: "no outcome" is also what a half-written
        # forecast looks like, and the two must not be confused. For a rule,
        # having been SCORED (`GENERALISED` / `NOT_GENERALISED`) is what
        # `outcome is not None` means for a forecast: a verdict was reached on
        # evidence that closed before `t`. A `CANDIDATE` rule -- too few
        # firings to have a Brier -- is NOT visible, which is the same refusal
        # under a different name.
        if str(record.get("schema_version") or "").startswith("learned-rule-"):
            if record.get("state") in ("GENERALISED", "NOT_GENERALISED"):
                return True, None
            return False, "rule_not_scored_yet"
        return False, "voided"
    return True, None


def rules_visible_at(t: date | str, *, ledger: Iterable[dict] | None = None,
                     path: Path | None = None,
                     scope: str | None = None) -> list[dict]:
    """Every rule/record that was already GRADED before `t`. A pre-filter.

    `t` is injectable (the same pattern as `belief_state.resolve_one(...,
    today=None)`) so the tests need no clock mocking and run inside the offline,
    un-hangable fast suite.

    `scope` filters by `applies_to_scope` when given -- a ticker, a mechanism id,
    a lane. It is applied AFTER the date gate, never as a substitute for it.
    """
    t = _as_date(t)
    if t is None:
        raise ValueError("rules_visible_at needs a date it can parse; a "
                         "retrieval with an unreadable cut-off is a retrieval "
                         "with no cut-off")
    rows = list(ledger) if ledger is not None else _read(path)
    out: list[dict] = []
    for r in rows:
        ok, _ = visible_at(r, t)
        if not ok:
            continue
        if scope is not None and r.get("applies_to_scope") not in (None, scope):
            continue
        out.append(r)
    return out


def retrieval_report(t: date | str, *, ledger: Iterable[dict] | None = None,
                     path: Path | None = None, scope: str | None = None) -> dict:
    """What was visible, what was not, and WHY -- per clause.

    A retrieval that came back empty and a retrieval that was never run look the
    same to a prompt. This makes them different: `pool` is what existed,
    `visible` is what survived the gate, and `dropped` names the clause that
    fired for each one.
    """
    t_d = _as_date(t)
    rows = list(ledger) if ledger is not None else _read(path)
    dropped: dict[str, int] = {k: 0 for k in REASONS}
    visible: list[dict] = []
    for r in rows:
        ok, why = visible_at(r, t_d)
        if ok:
            if scope is not None and r.get("applies_to_scope") not in (None, scope):
                continue
            visible.append(r)
        elif why:
            dropped[why] = dropped.get(why, 0) + 1
    # THE OVER-TRUST COLUMN (M2 spec section 1.6). Every surfaced rule carries
    # the weight it is ALLOWED to have in a live prompt, which is its measured
    # Brier skill score capped at `MAX_RULE_WEIGHT` -- never its similarity to
    # the situation, which is the experience-following failure arXiv:2505.16067
    # measured. A row with no `prompt_weight` of its own is surfaced at ZERO:
    # an unscored rule may be shown and labelled, and must not move a number.
    surfaced = [{**r, "prompt_weight": float(r.get("prompt_weight") or 0.0)}
                for r in visible]
    return {"as_of": str(t_d), "scope": scope, "pool": len(rows),
            "visible": len(visible), "dropped": dropped,
            "rules": surfaced,
            "prompt_weight_note": (
                "capped by the rule's MEASURED Brier skill score, never by "
                "retrieval similarity or recency; an unscored rule surfaces "
                "at 0.0 and may be shown but never weighted"),
            "predicate": ("resolution_date < t AND resolved_at is not None AND "
                          "resolved_at <= t AND outcome is not None"),
            "note": ("a pre-filter on the candidate pool, not a post-filter on a "
                     "ranked list: a post-filter changes WHICH rule is returned "
                     "without that being visible to a test")}


def _read(path: Path | None) -> list[dict]:
    p = path or LEARNED_RULES
    if not Path(p).is_file():
        return []
    out: list[dict] = []
    for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
