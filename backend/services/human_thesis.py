"""H2 -- the journal -> thesis bridge. A conviction decision becomes a THESIS.

    from backend.services import human_thesis as ht

    t = ht.build(symbol="NVDA", action="enter", direction="up",
                 expected_move=0.06, catalyst="Q3 FY27 print",
                 catalyst_at_utc="2026-11-19T21:20:00Z",
                 reason="AI demand accelerating faster than the guide implies",
                 falsifier="Q4 revenue guide at or below $104bn, or GM below 74%",
                 horizon_sessions=21, min_normal_hold_sessions=5,
                 loss_budget_ref="human_v1")
    ht.record(t)                      # append-only; returns the thesis id
    ht.book_entry(t)                  # the pre-open prediction-book row

WHY THIS EXISTS
===============
`POST /api/pi/conviction/decision` has written an immutable row since P1, and
that row cannot be GRADED. It has a rationale and a conviction 1-5; it has no
falsifier, no catalyst date, no horizon and no declared hold, so the only
question it can answer afterwards is "did the position go up", which is the
question a matched control exists to make meaningless. Meanwhile the execution
repo has had a schema that refuses all five omissions since 2026-08-26
(`alpha/human.py`), and the two have never been wired together.

Mode A is how Mode B gets its labels. A journal row that cannot be graded
produces no label, so the bridge is not a convenience -- it is the only thing in
this programme that manufactures labelled decision data nobody else has.

THE SCHEMA IS NOT REDEFINED HERE
================================
`Thesis` is loaded from `backend/vendor/aat/alpha/human.py`, a byte-identical
mirror of the execution repo's module (see `backend/vendor/__init__.py`). Every
refusal below the `HumanThesis` line is INHERITED, not restated:

  * a thesis with no direction and no width claim is not a thesis;
  * `direction` without `expected_move` cannot pick an instrument;
  * a sign disagreement between the two is refused;
  * a falsifier under 15 characters is refused;
  * a reason under 10 characters is refused;
  * **`stated_at >= catalyst_at` is refused** -- a thesis recorded after its own
    catalyst is a memory, and grading a memory as a forecast poisons every
    calibration number the arm exists to produce.

WHAT THIS FILE ADDS, AND WHY EXACTLY THREE FIELDS
=================================================
The fleet was remapped by horizon on 2026-09-08 (`contract.HORIZON_REMAP`):
every book now declares a horizon, a minimum normal hold and a loss budget, and
no book has a zero hold by accident. A human decision has to declare the same
three or it cannot be graded the same way -- and "graded the same way" is the
entire content of invariant 18.

  horizon_sessions          when the row RESOLVES. The grader uses the row's OWN
                            horizon, never a fixed 5 days.
  min_normal_hold_sessions  under which an exit is BOUGHT_SOLD_EARLY rather than
                            a decision. 0 is legal ONLY under a budget whose book
                            declares an event strategy (`event_v1`/hack2), so
                            "min hold 0" is a choice with a name on it rather
                            than the default that emptied hack2 for a week.
  loss_budget_ref           invariant 19: how many positions this book is judged
                            at and how many it expects to lose, declared BEFORE
                            the first position. An idea is retired by its book's
                            scoreboard, never by its own first loss.

WHAT THIS FILE DOES NOT DO
==========================
**It does not seal.** `book_entry()` returns the row a pre-open prediction book
would carry, with its own `content_sha256`, and `export_for_seal()` returns that
row plus the exact attended command. Writing into
`aegis-alpha-terminal/state/predictions/<day>.json` is an ATTENDED act in the
other repo: sealed receipts are immutable, an agent session does not seal, and a
row appended to a sealed book by a background process is exactly the tamper the
seal exists to detect. The finance-side log (`HUMAN_BOOK_LOG`) is append-only and
carries the same hash, so the seal, when a human performs it, is verifiable
against a record that already existed.

It also places no order, sizes nothing, and imports no broker.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import (HUMAN_BOOK_GENERATOR, HUMAN_BOOK_LOG,
                            HUMAN_DEFAULT_HORIZON_SESSIONS,
                            HUMAN_DEFAULT_LOSS_BUDGET_REF,
                            HUMAN_DEFAULT_MIN_HOLD_SESSIONS,
                            HUMAN_LOOP_VERSION, HUMAN_REVIEW_CADENCE_SESSIONS,
                            HUMAN_THESIS_AUTHOR, HUMAN_THESIS_LOG, LOSS_BUDGETS)

logger = logging.getLogger(__name__)

#: The mirror root. `alpha/human.py` keeps its own
#: `from alpha.brains.base import Forecast` line byte-identical, so the mirror
#: has to be importable UNDER THE NAME `alpha` -- which is why it lives in its
#: own directory that is put on `sys.path` for the duration of one import and
#: then taken off again.
_MIRROR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "aat"

#: The execution repo path the mirror was taken from. Used ONLY by the drift
#: test; nothing at runtime reads it, and nothing ever imports from it.
UPSTREAM_SCHEMA_RELPATH = "alpha/human.py"


class SchemaUnavailable(RuntimeError):
    """The vendored `Thesis` schema could not be loaded.

    A refusal and not a fallback. Re-deriving the validation rules locally is
    how two repos start refusing different things while both claim to enforce
    one contract, and the whole point of H2 is that there is ONE schema.
    """


def _load_mirror():
    """Import the mirrored `alpha.human`, or refuse.

    The modules land in `sys.modules` under `alpha`, `alpha.brains` and
    `alpha.brains.base`. That name is free in this repository (there is no
    top-level `alpha` package here -- the one that exists lives in the execution
    repo), so the binding is unambiguous, and
    `test_human_thesis.py::test_the_loaded_schema_is_the_mirror_not_the_repo`
    asserts the loaded `__file__` sits under `backend/vendor/`. If it ever
    resolved to the execution repo, a web request handler would have
    `alpha.brains` -- the package that owns the broker client -- one import away.
    """
    if "alpha.human" in sys.modules:
        return sys.modules["alpha.human"]
    root = str(_MIRROR_ROOT)
    if not (_MIRROR_ROOT / "alpha" / "human.py").is_file():
        raise SchemaUnavailable(
            f"the vendored thesis schema is missing at {_MIRROR_ROOT}. It is a "
            "byte-identical mirror of the execution repo's alpha/human.py and "
            "there is no second copy to fall back to -- see "
            "backend/vendor/__init__.py.")
    inserted = root not in sys.path
    if inserted:
        sys.path.insert(0, root)
    try:
        mod = importlib.import_module("alpha.human")
    except Exception as exc:                                     # noqa: BLE001
        raise SchemaUnavailable(
            f"the vendored thesis schema at {_MIRROR_ROOT} did not import: "
            f"{type(exc).__name__}: {exc}") from exc
    finally:
        if inserted and root in sys.path:
            sys.path.remove(root)
    return mod


_alpha_human = _load_mirror()

#: Re-exported so a caller of THIS module never imports the mirror directly.
Thesis = _alpha_human.Thesis
ThesisRefusal = _alpha_human.ThesisRefusal
DIRECTIONS = _alpha_human.DIRECTIONS
MAGNITUDES = _alpha_human.MAGNITUDES

#: The conviction-journal actions that OPEN or ADD to exposure. A `trim`/`exit`
#: is a decision too and is logged, but it is not a new thesis: it resolves one.
OPENING_ACTIONS = ("enter", "add")
CLOSING_ACTIONS = ("trim", "exit")


@dataclass(frozen=True)
class HumanThesis(Thesis):                                       # type: ignore[misc]
    """`Thesis` plus the three hold fields the remapped fleet made mandatory.

    A SUBCLASS, not a re-declaration: every rule in the parent's `__post_init__`
    runs first and unchanged, so the bridge cannot accidentally become more
    permissive than the execution repo it feeds.
    """

    horizon_sessions: int = 0
    min_normal_hold_sessions: int = -1
    loss_budget_ref: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if int(self.horizon_sessions) <= 0:
            raise ThesisRefusal(
                "horizon_sessions must be a positive number of SESSIONS. Every "
                "book in the remapped fleet declares one (contract.HORIZON_REMAP); "
                "a human decision graded at a fixed 5 days is graded against a "
                "clock it never agreed to.")
        if int(self.min_normal_hold_sessions) < 0:
            raise ThesisRefusal(
                "min_normal_hold_sessions is required. It is what separates a "
                "sold-early exit from a decision, and BOUGHT_SOLD_EARLY is one "
                "of the four taxonomy states this row will be graded into.")
        if int(self.min_normal_hold_sessions) > int(self.horizon_sessions):
            raise ThesisRefusal(
                f"min_normal_hold_sessions={self.min_normal_hold_sessions} exceeds "
                f"horizon_sessions={self.horizon_sessions}: the row could never "
                "reach its own horizon without first being early.")
        budget = LOSS_BUDGETS.get(self.loss_budget_ref)
        if budget is None:
            raise ThesisRefusal(
                f"loss_budget_ref={self.loss_budget_ref!r} is not declared; known: "
                f"{sorted(LOSS_BUDGETS)}. Invariant 19: a loss budget is declared "
                "BEFORE the first position, so that an idea is retired by its "
                "book's scoreboard and never by its own first loss.")
        if int(self.min_normal_hold_sessions) == 0 and self.loss_budget_ref != "event_v1":
            raise ThesisRefusal(
                "min_normal_hold_sessions=0 is admissible only under an EVENT "
                "budget (`event_v1`/hack2), where it is a declared choice. Under "
                f"{self.loss_budget_ref!r} it is the default that let a book exit "
                "before its own thesis could resolve.")

    # -- derived -------------------------------------------------------------
    @property
    def loss_budget(self) -> dict:
        return dict(LOSS_BUDGETS[self.loss_budget_ref])

    @property
    def review_cadence_sessions(self) -> int:
        """Sessions to the next SCHEDULED review -- counterfactual #2's clock.

        Never longer than the horizon: a review that falls after the row has
        already resolved is not a review, and the second counterfactual would
        silently become a duplicate of the first.
        """
        return min(int(HUMAN_REVIEW_CADENCE_SESSIONS), int(self.horizon_sessions))


def build(*, symbol: str, direction: str, catalyst: str, catalyst_at_utc: str,
          reason: str, falsifier: str, expected_move: float | None = None,
          magnitude: str = "unknown", conviction: float = 1.0,
          horizon_sessions: int | None = None,
          min_normal_hold_sessions: int | None = None,
          loss_budget_ref: str | None = None,
          stated_at_utc: str | None = None,
          author: str = HUMAN_THESIS_AUTHOR,
          evidence: dict[str, Any] | None = None) -> HumanThesis:
    """Build a `HumanThesis`, or raise `ThesisRefusal` naming what is missing.

    The three hold fields fall back to `config` defaults, and the fallback is
    RECORDED (`evidence.horizon_source`) rather than hidden: a row that declared
    21 sessions and a row that inherited 21 sessions are different facts, and a
    calibration curve that cannot tell them apart is measuring two populations.
    """
    ev = dict(evidence or {})
    horizon = HUMAN_DEFAULT_HORIZON_SESSIONS if horizon_sessions is None else horizon_sessions
    min_hold = (HUMAN_DEFAULT_MIN_HOLD_SESSIONS if min_normal_hold_sessions is None
                else min_normal_hold_sessions)
    budget_ref = HUMAN_DEFAULT_LOSS_BUDGET_REF if loss_budget_ref is None else loss_budget_ref
    ev.setdefault("horizon_source",
                  "declared" if horizon_sessions is not None else "config_default")
    ev.setdefault("min_hold_source",
                  "declared" if min_normal_hold_sessions is not None else "config_default")
    ev.setdefault("loss_budget_source",
                  "declared" if loss_budget_ref is not None else "config_default")
    ev.setdefault("bridge_version", HUMAN_LOOP_VERSION)

    #: `horizon_days` is the PARENT's field and stays in calendar days, because
    #: the parent computes nothing from it that a session count would change.
    #: The two are related by the calendar, not by a constant, so the conversion
    #: is deliberate and stamped rather than assumed:
    horizon_days = float(_sessions_to_calendar_days(int(horizon)))
    ev.setdefault("horizon_days_basis",
                  f"{int(horizon)} sessions -> {horizon_days:.0f} calendar days "
                  "(7/5 weekday scaling, no holiday calendar). The GRADER uses "
                  "sessions; horizon_days exists only for the parent schema.")

    return HumanThesis(
        author=author, symbol=str(symbol).upper().strip(), direction=direction,
        magnitude=magnitude, catalyst=catalyst, catalyst_at_utc=catalyst_at_utc,
        horizon_days=horizon_days, reason=reason, falsifier=falsifier,
        expected_move=expected_move, conviction=float(conviction),
        stated_at_utc=stated_at_utc or datetime.now(timezone.utc).isoformat(),
        evidence=ev,
        horizon_sessions=int(horizon),
        min_normal_hold_sessions=int(min_hold),
        loss_budget_ref=str(budget_ref),
    )


def _sessions_to_calendar_days(sessions: int) -> int:
    """Weekday scaling, declared. Not a trading calendar and does not pretend."""
    return max(1, int(round(sessions * 7.0 / 5.0)))


# ── the pre-open prediction-book row ────────────────────────────────────────
#: The execution repo's book schema, as read off
#: `state/predictions/2026-09-08.json` on 2026-09-08. Named so a drift in the
#: other repo is a failing test here rather than a silently mis-shaped row.
BOOK_SCHEMA = "prediction-book-3"


def book_entry(t: HumanThesis, *, day: str | date | None = None) -> dict:
    """The row a pre-open prediction book would carry for this thesis.

    Shaped like the book's own `predictions[]` rows (schema
    `prediction-book-3`): `symbol`, `generator`, `claims`, `direction`,
    `horizon_sessions`, `checkpoint_sessions`, `falsifier`, `confidence`,
    `which_book_acts`. The generator is the BRAIN -- `human:murat` -- so the row
    enters the ordinary counterfactual machinery under a brain name and gets no
    private path through the engine.
    """
    if not isinstance(t, HumanThesis):
        raise ThesisRefusal(
            "book_entry() takes a HumanThesis. A bare Thesis has no declared "
            "hold, and a book row without one cannot be graded beside a book.")
    day_s = str(day or datetime.now(timezone.utc).date())
    budget = t.loss_budget
    row = {
        "schema": BOOK_SCHEMA,
        "day": day_s,
        "symbol": t.symbol,
        "generator": HUMAN_BOOK_GENERATOR,
        "brain": t.brain,
        "claims": True,
        "direction": None if t.direction == "none" else t.direction,
        "magnitude": t.magnitude,
        "claim": t.claim,
        "horizon_sessions": int(t.horizon_sessions),
        "min_normal_hold_sessions": int(t.min_normal_hold_sessions),
        "checkpoint_sessions": int(t.review_cadence_sessions),
        "loss_budget_ref": t.loss_budget_ref,
        "loss_budget": budget,
        "exp_return": float(t.expected_move or 0.0),
        "exp_return_basis": (
            "the HUMAN'S OWN stated expected move over the declared horizon. "
            "Not measured, not a base rate, and not evidence of anything until "
            "it has been graded against four counterfactuals."),
        "exp_return_validation": "HUMAN_STATED",
        "confidence": float(t.conviction),
        "confidence_basis": (
            "the human's own conviction, recorded so a calibration curve can be "
            "drawn against it. Invariant 20: it is NOT a probability until "
            "something has plotted it against outcomes."),
        "catalyst": t.catalyst,
        "catalyst_at_utc": t.catalyst_at_utc,
        "stated_at_utc": t.stated_at_utc,
        "falsifier": t.falsifier,
        "reason": t.reason,
        "thesis_id": t.thesis_id(),
        "which_book_acts": f"{budget['book']} (HUMAN BOOK, roadmap F) -- ATTENDED",
        "authority": (
            "NOT SELF-EXECUTING. This row sizes and orders NOTHING. It becomes "
            "tradable only on an account whose AAT_LOOP_BRAINS names "
            f"{t.brain!r}, which is an attended flip in the execution repo."),
        "bridge_version": HUMAN_LOOP_VERSION,
    }
    row["content_sha256"] = _content_hash(row)
    return row


def _content_hash(row: dict) -> str:
    body = {k: v for k, v in row.items() if k != "content_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"),
                   default=str).encode()).hexdigest()


def verify_book_entry(row: dict) -> bool:
    """True when the row's `content_sha256` still matches its content."""
    return bool(row.get("content_sha256")) and row["content_sha256"] == _content_hash(row)


def export_for_seal(t: HumanThesis, *, day: str | date | None = None) -> dict:
    """The payload for the ATTENDED seal, and the command that performs it.

    This function does not seal. It cannot: sealing writes into another repo's
    `state/predictions/<day>.json`, sealed receipts are immutable, and an agent
    session that appends to a sealed book is the tamper the seal detects.
    """
    row = book_entry(t, day=day)
    return {
        "version": HUMAN_LOOP_VERSION,
        "authority": "READ_ONLY -- this function seals nothing.",
        "brain": t.brain,
        "book_schema": BOOK_SCHEMA,
        "row": row,
        "seal_is_attended": True,
        "how_to_seal": (
            "In aegis-alpha-terminal, with a human present: append this row to "
            "state/predictions/<day>.json::predictions[] BEFORE the open, then "
            "re-run the repo's own sealer so state/predictions/seals.jsonl "
            "records the new content_sha256. Never edit a book already sealed "
            "for a past day -- reseal a NEW file, which is what the "
            "`.resealed_HHMMSS.json` names in that directory are."),
        "local_record": str(HUMAN_BOOK_LOG),
    }


# ── append-only storage ─────────────────────────────────────────────────────
def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def record(t: HumanThesis, *, day: str | date | None = None,
           decision_id: int | None = None,
           thesis_path: Path | None = None,
           book_path: Path | None = None) -> dict:
    """Append the thesis and its book row. Returns the ids and the hash.

    Append-only, like `alpha/human.py::record` and like `personal_decisions`:
    a thesis is not editable, and a correction is a new row.
    """
    row = {"thesis_id": t.thesis_id(), "decision_id": decision_id,
           "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           **asdict(t)}
    _append(Path(thesis_path or HUMAN_THESIS_LOG), row)
    entry = book_entry(t, day=day)
    entry["decision_id"] = decision_id
    _append(Path(book_path or HUMAN_BOOK_LOG), entry)
    return {"thesis_id": row["thesis_id"], "content_sha256": entry["content_sha256"],
            "brain": t.brain, "day": entry["day"],
            "horizon_sessions": t.horizon_sessions,
            "min_normal_hold_sessions": t.min_normal_hold_sessions,
            "loss_budget_ref": t.loss_budget_ref}


def load_all(path: Path | None = None) -> list[HumanThesis]:
    """Every recorded thesis. A row that no longer validates is SKIPPED and
    counted by `load_report()` -- never silently repaired."""
    return load_report(path)["theses"]


def load_report(path: Path | None = None) -> dict:
    p = Path(path or HUMAN_THESIS_LOG)
    out: list[HumanThesis] = []
    rejected: list[dict] = []
    if p.exists():
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as exc:
                rejected.append({"line": i, "reason": f"not JSON: {exc}"})
                continue
            for k in ("thesis_id", "decision_id", "recorded_at_utc"):
                d.pop(k, None)
            try:
                out.append(HumanThesis(**d))
            except (ThesisRefusal, TypeError) as exc:
                rejected.append({"line": i, "reason": str(exc)[:300]})
    return {"path": str(p), "n": len(out), "theses": out,
            "n_rejected": len(rejected), "rejected": rejected}


def schema_provenance() -> dict:
    """Where the schema came from -- part of every response, not a docstring."""
    p = Path(_alpha_human.__file__).resolve()
    return {
        "module": "alpha.human",
        "file": str(p),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "is_vendored_mirror": str(_MIRROR_ROOT) in str(p),
        "upstream": f"aegis-alpha-terminal/{UPSTREAM_SCHEMA_RELPATH}",
        "note": ("byte-identical mirror; drift from the execution repo fails "
                 "test_human_thesis.py::TestSchemaIsVerbatim when that repo is "
                 "on the machine, and SKIPS with a reason when it is not."),
    }
