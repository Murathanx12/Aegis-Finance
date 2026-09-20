"""THE DECISION CONTRACT — one row that says what would be bought, at what size,
why, and what would make it wrong (roadmap §14.4 chunk 18; spec
`docs/research_notes/2026-09-19/spec_decision_contract_and_path_audit.md` §4).

THE GAP THIS CLOSES, AND THE GAP IT DOES NOT
============================================
The audit's one-paragraph finding: the engines that DO decide
(`investment_committee.compose_book`, `agency.propose`) never hand their output
to the two surfaces Murat talks to, and the fleet's 43-sentence refusal
taxonomy is read by neither. So when he asks the local model "what's a good
buy", the router sends the question to the CANON and the model answers with
TIER 0 file names.

This module composes ONE object on top of computation that already exists. It
does **not** rank, size, price or forecast anything of its own: every number
here was produced by `investment_committee`/`agency` before this module ran,
and every number that does NOT exist is carried as a named absence
(`"NOT CALIBRATED"`, `"CANNOT DETERMINE: ..."`) rather than as a default. A
fabricated field on a decision receipt is worse than an empty page, because the
whole purpose of the receipt is to be gradeable tomorrow.

WHAT IT IS NOT
--------------
It is not an order path, not a capital authority and not an LLM output. Nothing
here places, sizes, arms or seals anything; the LLM surfaces READ these rows and
explain them (`ask_tools.tool_decisions`, `copilot.get_todays_decisions`), which
is why `control_ask.ASK_SYSTEM`'s "you cannot size positions" clause does not
have to move: the engine sized it, the model reads the receipt.

ONE REFUSAL VOCABULARY, RE-DERIVED AND PINNED
=============================================
The execution repo (`aegis-alpha-terminal/alpha/refusal_classes.py`, 383 lines)
already normalises **43 distinct refusal sentences** from 7,599 refused ledger
rows into **31 post-hoc classes** (+ `UNCLASSIFIED`, which is COUNTED and never
a silent catch-all) and **18 closed terminal states**. Both closed sets are
re-derived here as frozen tuples rather than imported, because:

* the two repos are separate checkouts that move by hand — an import would be a
  filesystem assumption that is false in CI, in the Docker image and in the
  frozen desktop build;
* a COPY that drifts silently is the real danger, so `test_decision_contract.py`
  pins the sha256 of each tuple. A change over there becomes a visible red test
  here, which is the cheapest possible cross-repo alarm.

The PATTERNS are NOT copied. The execution repo's regexes are tuned to its own
gates' sentences ("BOOK LIMIT:", "aggregate convex risk is already") and match
none of this repo's prose; `_LOCAL_PATTERNS` below maps THIS repo's refusal
sentences into the SAME two closed vocabularies, so a census can union the two
repos' refused rows without a translation table.

WHERE `SELL` IS
---------------
`DIRECTIONS` carries `SELL` and no source in this repo emits one today:
`recommendation._verdict` produces only `BUY`/`WATCH`/`HOLD`/`NO_ACTION`, and
`agency.propose` proposes long books. The value stays in the enum because the
agency's own `sell` review label and the execution artery both produce it, and
an enum that grows when the first such row arrives is an enum every stored row
was written against a different version of. The file's
`directions_not_produced_today` block says this in words, on the receipt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend import config

logger = logging.getLogger(__name__)


class CostModelRefused(ValueError):
    """A book priced at zero cost without declaring the frictionless diagnostic.

    Same rule and same words as `portfolio_farm.Policy` (CLAUDE.md, EXPLORE
    DIRTY rule 3): costs are never omitted, and a zero that arrives by default
    rather than by declaration is how a strategy reaches a leaderboard on
    friction it never paid.
    """


def _repo_root() -> Path:
    """The checkout, the same three lines as `morning.py:60`."""
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


REPO = _repo_root()
DECISIONS_DIR = REPO / "backend" / "data" / "optimus" / "decisions"

#: Every contract row is `PRODUCT_EXPERIMENT` by construction (CLAUDE.md, THREE
#: LICENCES). It can never be `CAPITAL_CANDIDATE`: promotion to real money is
#: attended and needs matured forward evidence, which a row written this morning
#: does not have by definition.
LICENCE = "PRODUCT_EXPERIMENT"

#: The four directions a row can carry. `REFUSED` is one of them on purpose —
#: "why no trade" is a decision with the same provenance requirements as a
#: trade, and a refused candidate that simply vanished from the file would make
#: the day's coverage unauditable.
DIRECTIONS: tuple[str, ...] = ("BUY", "WATCH", "SELL", "REFUSED")

#: The string the committee already prints instead of a per-name expected
#: return, carried as a FIELD rather than omitted (CLAUDE.md: a headline number
#: belongs in a receipt; an absent field reads as an oversight, a named absence
#: reads as a finding).
NOT_CALIBRATED = "NOT CALIBRATED"

#: The ROI rule's own named absence, spelled with an underscore so a reader
#: greping either file finds both halves of the same idea
#: (`roi_rank.NOT_CALIBRATED`). Re-declared rather than imported for the same
#: reason the refusal vocabularies are: this module is the one that writes the
#: receipt, and the word on the receipt must not change because an import moved.
NOT_CALIBRATED_ROI = "NOT_CALIBRATED"

#: At most this many REFUSED rows, best rank first. A funnel of 5,324 screened
#: names would otherwise write a file nobody opens; the count that was elided is
#: on the payload, so the cap is visible rather than silent.
MAX_REFUSED_ROWS = 50


# ===========================================================================
# THE TWO CLOSED VOCABULARIES, RE-DERIVED (see the module docstring)
# ===========================================================================

#: SOURCE: `aegis-alpha-terminal/alpha/refusal_classes.py::PATTERNS` (31 class
#: names, in its own order) plus its `UNCLASSIFIED`. That file normalises the
#: 43 distinct refusal sentences its ledger carries; the CLASS count is 31, and
#: the two numbers are different things — 43 is what the gates wrote, 31 is what
#: they mean. Pinned by sha256 in `test_decision_contract.py`.
REFUSAL_CLASSES: tuple[str, ...] = (
    "NO_STRUCTURE_CLEARED", "PAST_LIQUIDATION_DEADLINE", "CLOCK_SKEW",
    "SESSION_CLOSED", "GROSS_NOTIONAL", "DRIVER_CONCENTRATION", "CROSS_BOOK",
    "OPENING_RANGE", "CONVEX_RULE", "BOOK_LIMIT", "PER_NAME_CONCENTRATION",
    "TOMORROWS_OPTIONALITY", "THETA_BURN", "DELTA_STRESS", "DAILY_LOSS_LATCH",
    "AGGREGATE_RISK", "CAPITAL_ROUNDS_TO_ZERO", "REFUTED_ROUTE", "MDE",
    "EDGE_BELOW_BAR", "CLAIM_MISMATCH", "OUTRANKED_BY_SIBLING", "CASH_BEATS_IT",
    "SPREAD_EATS_THE_EDGE", "CLAIM_MISMATCH_PAIR", "DRAWDOWN_UNKNOWN",
    "ALREADY_HELD", "BOOK_UNBOUNDED", "EVENT_NODE_CAP", "CHAIN_UNUSABLE",
    "VENUE_REJECTED",
    # LAST, and part of the closed set: a row that matches nothing is
    # UNCLASSIFIED and is COUNTED in every report that uses this module.
    "UNCLASSIFIED",
)

#: SOURCE: the same file's `TERMINAL_STATES` (18, its own order). This is the
#: field the two repos' censuses join on: the post-hoc class is only meaningful
#: for a sentence one of THEIR gates wrote, while every refusal anywhere
#: finishes in exactly one of these.
TERMINAL_STATES: tuple[str, ...] = (
    "ADMITTED", "ALREADY_HELD", "RANKED_OUT", "NEGATIVE_EV", "CONFIDENCE",
    "LIQUIDITY", "CAPACITY", "GROSS", "CONCENTRATION", "OPENING_RANGE",
    "MANDATE", "STRUCTURE", "DATA_STALE", "DATA_MISSING", "RISK", "DUPLICATE",
    "VENUE_REJECTED", "OTHER_TYPED",
)

UNCLASSIFIED = "UNCLASSIFIED"
OTHER_TYPED = "OTHER_TYPED"

#: The lifecycle states a decision moves through. Declared HERE beside the row
#: that starts it and re-exported by `decision_ledger`, so the ledger and the
#: contract cannot drift apart by a typo.
#:
#: `ORDER_SUBMITTED` and `FILLED` are **written by the execution artery, not by
#: this repo**. Nothing in `aegis-finance` submits an order; they are in the
#: enum because a stored row must be written against the whole lifecycle, and a
#: ledger that grew a state later would be a ledger whose old rows mean
#: something else.
#:
#: `REVISED` (spec §D) sits between `SEEN_BY_EXECUTOR` and `FILLED`/`SCORED`
#: and is written on the PARENT when a re-run of the same ranking supersedes
#: it. The superseding row is a NEW contract row with its own `decision_id` and
#: a `parent_decision_id` — never an in-place edit, because the original must
#: stay gradeable exactly as it was decided.
DECISION_STATES: tuple[str, ...] = (
    "DECIDED", "DELIVERED", "SEEN_BY_EXECUTOR", "REFUSED", "ORDER_SUBMITTED",
    "REVISED", "FILLED", "SCORED",
)

#: (class, terminal_state, pattern, basis) for THIS repo's own refusal
#: sentences. Ordered, first match wins, most specific first — the execution
#: repo's rule, because "no candidate clears the tilt gate" must not be read as
#: the per-name verdict refusal it quotes.
#:
#: `basis` is the FOURTH element and it exists because of 2026-09-20: the day's
#: contract carried 7 UNCLASSIFIED refusals and a reader could not tell whether
#: the sentence had matched a pattern that deliberately maps to UNCLASSIFIED or
#: had matched nothing at all. Those are opposite findings — the first is "the
#: closed vocabulary has no class for this", which is a fact about the execution
#: repo's 31 classes; the second is "a gate wrote a sentence nobody has typed",
#: which is work owed here. Every row now carries the basis that produced its
#: class, so the two are one field apart instead of indistinguishable.
_LOCAL_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    # ---- pass-level: nothing at all cleared -------------------------------
    ("NO_STRUCTURE_CLEARED", "STRUCTURE", r"no candidate clears the tilt gate",
     "the pass-level refusal: nothing at all cleared the tilt gate"),
    # ---- the engine has nothing it is ALLOWED to say about this name ------
    # MEASURED 2026-09-20: all 7 UNCLASSIFIED rows on that day's contract were
    # this one sentence, from `_refusal_sentence`'s NO_EVIDENCE branch. It stays
    # UNCLASSIFIED after reading all 31 classes in
    # `aegis-alpha-terminal/alpha/refusal_classes.py`: that vocabulary was
    # derived from an options book whose candidates are STRUCTURES on a forecast
    # that already exists, so it has classes for a refuted route (REFUTED_ROUTE),
    # an edge under the bar (EDGE_BELOW_BAR), a move under the MDE (MDE) and an
    # unquotable chain (CHAIN_UNUSABLE) — and none at all for a screened, liquid,
    # priced name that NO licensed signal covers. The terminal state DATA_MISSING
    # does fit and is what a census joins on, which is why the row is not lost.
    (UNCLASSIFIED, "DATA_MISSING",
     r"no licensed signal|NO_EVIDENCE",
     "no class in the execution repo's closed 31 covers 'screened and priced, "
     "and no licensed signal speaks to this name'; the nearest merit classes "
     "(REFUTED_ROUTE, EDGE_BELOW_BAR, MDE) all presuppose a signal that spoke. "
     "The terminal state DATA_MISSING is exact and is what a cross-repo census "
     "groups on"),
    # ---- the inputs were not there ----------------------------------------
    # "CANNOT DETERMINE" is the execution repo's own DATA_MISSING pattern; a
    # missing funnel, a void ranking gate and an unreadable candidate all
    # arrive wearing it, which is why this repo writes those words literally.
    (UNCLASSIFIED, "DATA_MISSING",
     r"CANNOT DETERMINE|no funnel run available|ranking gate VOID",
     "an input the ranking needed was absent or void; the closed 31 classes are "
     "about candidates and books and none of them names a missing input, so the "
     "typed answer is the terminal state DATA_MISSING"),
    # ---- the size buys no unit / the book has no room ----------------------
    ("CAPITAL_ROUNDS_TO_ZERO", "CAPACITY",
     r"below one share|rounds to zero|buys no share",
     "the execution repo's CAPITAL_ROUNDS_TO_ZERO, in this repo's words"),
    ("BOOK_LIMIT", "CAPACITY", r"tilt budget|IC_MAX_TILT_NAMES|no room in the book",
     "the book, not the candidate: IC_MAX_TILT_NAMES or the total tilt budget"),
    # ---- the tape could not carry it --------------------------------------
    (UNCLASSIFIED, "LIQUIDITY",
     r"untradeable at \$|dollar volume|days to exit|participation",
     "the closed 31 carry no liquidity class — an options book refuses on the "
     "chain (CHAIN_UNUSABLE), not on median dollar volume — so the terminal "
     "state LIQUIDITY carries the meaning"),
    # ---- the ranker preferred a sibling -----------------------------------
    ("OUTRANKED_BY_SIBLING", "RANKED_OUT",
     r"ranked below|out-ranked|outranked",
     "the ranker preferred another name inside the same budget"),
    # ---- the candidate's own merit ----------------------------------------
    ("EDGE_BELOW_BAR", "NEGATIVE_EV",
     r"verdict .* is not BUY or WATCH|ranking score .* is not positive|"
     r"scores at or below zero",
     "a signal spoke and the candidate's own merit did not clear the bar"),
    ("MDE", "CONFIDENCE", r"minimum detectable|not distinguishable from noise",
     "the move is under the minimum detectable effect"),
    # ---- the archetype refused to fill a book -----------------------------
    ("NO_STRUCTURE_CLEARED", "STRUCTURE",
     r"cannot fill a book|the archetype needs at least",
     "the archetype could not be filled, which is a structure refusal"),
    # ---- this policy may not express this claim ---------------------------
    ("CLAIM_MISMATCH", "MANDATE", r"not in the mandate|outside the declared",
     "the policy may not express this claim"),
)

_COMPILED = tuple((cls, term, re.compile(pat, re.IGNORECASE), basis)
                  for cls, term, pat, basis in _LOCAL_PATTERNS)


def enum_fingerprint(names: tuple[str, ...]) -> str:
    """sha256 over the enum's members, in order, one per line.

    In ORDER because order is meaning in the source file (first match wins), so
    a reordering is a change worth a red test even when the set is identical.
    """
    blob = "\n".join(names).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def classify_refusal(reason: str | None) -> dict:
    """`{refusal_class, terminal_state, refusal_reason, refusal_class_basis}`
    — never raises, never blank.

    `UNCLASSIFIED`/`OTHER_TYPED` is a typed answer and is counted by the caller,
    not a silent bucket: a new refusal sentence added without a pattern surfaces
    as a number on the day's file instead of dissolving.

    `refusal_class_basis` says WHY the class is what it is, and it matters most
    when the class is `UNCLASSIFIED`, because that word covers two opposite
    findings: a sentence this repo has typed and deliberately mapped to
    UNCLASSIFIED (the closed 31 have no class for it — nothing is owed), and a
    sentence nothing matched at all (a gate wrote prose nobody has typed — work
    is owed). One field separates them.
    """
    text = str(reason or "").strip()
    if not text:
        return {"refusal_class": UNCLASSIFIED, "terminal_state": "DATA_MISSING",
                "refusal_reason": "CANNOT DETERMINE: the refusal carried no sentence",
                "refusal_class_basis": (
                    "the row carried no refusal sentence at all, so there was "
                    "nothing to classify")}
    for cls, term, rx, basis in _COMPILED:
        if rx.search(text):
            return {"refusal_class": cls, "terminal_state": term,
                    "refusal_reason": text, "refusal_class_basis": basis}
    return {"refusal_class": UNCLASSIFIED, "terminal_state": OTHER_TYPED,
            "refusal_reason": text,
            "refusal_class_basis": (
                "NO PATTERN MATCHED: a gate wrote a sentence `_LOCAL_PATTERNS` "
                "has never seen. This is the UNCLASSIFIED that owes work — add "
                "the pattern, or name why the closed 31 cannot hold it")}


# ===========================================================================
# COSTS — named, or refused
# ===========================================================================


def cost_model_row(name: str, *, round_trip_bps: float | None,
                   zero_cost_diagnostic: bool = False,
                   basis: str = "") -> dict:
    """Name the model that priced this row, or say it was not priced.

    Three outcomes and no fourth:

    * a positive cost with a name — the ordinary case;
    * `round_trip_bps=None` — NOT PRICED, carried by name. The investment
      committee composes weights and never prices a round trip, so pretending
      otherwise would put a fabricated number on a receipt;
    * `round_trip_bps=0` without `zero_cost_diagnostic=True` — **refused**,
      because a silent zero is a strategy that reached the page on friction it
      never paid (`portfolio_farm.Policy`'s rule, same words).
    """
    if round_trip_bps is None:
        return {"name": "CANNOT DETERMINE", "priced": False,
                "round_trip_bps": None,
                "zero_cost_diagnostic": bool(zero_cost_diagnostic),
                "reason": (basis or
                           f"{name} composes weights and does not price a round "
                           f"trip; no cost model was applied to this row")}
    bps = float(round_trip_bps)
    if bps <= 0 and not zero_cost_diagnostic:
        raise CostModelRefused(
            f"cost model {name!r} prices the round trip at {bps} bps. Zero costs "
            f"are a DIAGNOSTIC, not a default: pass zero_cost_diagnostic=True, "
            f"and the flag travels onto every row it priced.")
    if bps > 0 and zero_cost_diagnostic:
        raise CostModelRefused(
            f"cost model {name!r} declares zero_cost_diagnostic=True with "
            f"{bps} bps of cost — the flag and the number disagree.")
    return {"name": str(name), "priced": True, "round_trip_bps": bps,
            "zero_cost_diagnostic": bool(zero_cost_diagnostic),
            "reason": basis or f"round trip priced by {name} at {bps:.1f} bps"}


# ===========================================================================
# WORST CASE — session protocol rule 4, printed in dollars
# ===========================================================================


def worst_case_no_stop(*, n_names: int, notional_pct: float,
                       equity_usd: float, gross_over_equity: float | None = None,
                       why: str = "") -> dict:
    """The same SHAPE `strategy.contract.loss_budget_worst_case` returns, for a
    long cash book that declares no stop.

    Not a copy of that function: it takes a `Strategy` and this path has none.
    What is copied deliberately is the RULE — gross beside stop, both or
    neither — and the `CANNOT DETERMINE` verdict it already returns when a stop
    is absent. A long cash position's worst case is its whole notional, and
    that number is printed in dollars rather than described.
    """
    gross = (float(gross_over_equity) if gross_over_equity is not None
             else float(n_names) * float(notional_pct))
    return {
        "n_names": int(n_names),
        "notional_pct_per_name": float(notional_pct),
        "gross_over_equity": gross,
        "stop_pct": None,
        "worst_case_usd": -abs(gross * float(equity_usd)),
        "worst_case_pct_of_equity": gross,
        "equity_usd": float(equity_usd),
        "verdict": (why or
                    f"no stop is declared, so the worst case is the WHOLE gross "
                    f"exposure: {int(n_names)} names x "
                    f"{float(notional_pct):.2%} = {gross:.2%} of "
                    f"${float(equity_usd):,.0f} = "
                    f"${abs(gross * float(equity_usd)):,.0f}"),
    }


def largest_admissible_book() -> dict:
    """CLAUDE.md session protocol 4, computed rather than remembered.

    `n names x notional% x stop%` and `sum|notional| / equity` for the biggest
    book this module can ever emit: `IC_MAX_TILT_NAMES` at
    `IC_SINGLE_NAME_TILT_CAP`, capped by `IC_TOTAL_TILT_BUDGET`, at the largest
    configured capital level. It goes on the file, not in a comment, because
    the number that mattered on 28 Aug was the one nobody printed.
    """
    capital = max(float(c) for c in config.IC_CAPITAL_LEVELS)
    n = int(config.IC_MAX_TILT_NAMES)
    per_name = float(config.IC_SINGLE_NAME_TILT_CAP)
    uncapped = n * per_name
    gross = min(uncapped, float(config.IC_TOTAL_TILT_BUDGET))
    row = worst_case_no_stop(
        n_names=n, notional_pct=per_name, equity_usd=capital,
        gross_over_equity=gross,
        why=(f"{n} names x {per_name:.0%} = {uncapped:.0%} uncapped, held to "
             f"{gross:.0%} by IC_TOTAL_TILT_BUDGET; no stop is declared, so the "
             f"worst case is the whole tilt exposure "
             f"${gross * capital:,.0f} of ${capital:,.0f}"))
    row["tilt_gross_over_equity"] = gross
    row["book_gross_over_equity"] = 1.0
    row["book_gross_note"] = (
        "the core funds the tilts (core_scale = 1 - tilt_total), so total gross "
        "is 1.00x equity and no path here levers the book")
    return row


# ===========================================================================
# THE INDIRECTIONS. Every outside call this module makes has a NAME here, so a
# test replaces the call rather than the network (`morning.py`'s pattern).
# ===========================================================================


def funnel_state(funnel_path: Path | None = None) -> dict:
    from backend.services import investment_committee as IC
    return IC.funnel_state(funnel_path)


def compose_book(recs, **kw) -> dict:
    from backend.services import investment_committee as IC
    return IC.compose_book(recs, **kw)


def kill_condition(rec) -> tuple[str, str]:
    from backend.services import investment_committee as IC
    return IC._kill_condition(rec)


def agency_options(asof: date) -> tuple[list, str]:
    """(options, note). Never raises: the absence of an IPS is the common case.

    An `Option` is a whole costed `Strategy` (three per neighbour personality),
    not a ticker, so an agency row is a BOOK-level decision beside the
    committee's name-level ones. When no policy document exists the note says
    so by name and the day has zero agency rows — which is a fact about the
    store, not a failure of this step.
    """
    from backend.services import agency as AG

    try:
        store = AG.ips_dir()
        hashes = sorted(p.stem for p in Path(store).glob("*.json")) if Path(store).is_dir() else []
    except Exception as exc:                                       # noqa: BLE001
        return [], f"CANNOT DETERMINE: the IPS store is unreadable ({type(exc).__name__}: {exc})"
    if not hashes:
        return [], ("CANNOT DETERMINE: no IPS document is in the store, so the "
                    "agency has surfaced no option today. A policy is written by "
                    "a person through /api/control/agency/intake; nothing here "
                    "invents one.")
    try:
        ips = AG.load_ips(hashes[-1])
        from backend.services import paper_books as PB
        bars = PB.load_bars()
        return list(AG.propose(ips, bars=bars, asof=asof)), ""
    except Exception as exc:                                       # noqa: BLE001
        return [], (f"CANNOT DETERMINE: the agency could not propose against "
                    f"{hashes[-1][:12]} ({type(exc).__name__}: {exc})")


# ===========================================================================
# ROW CONSTRUCTION
# ===========================================================================


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str,
                      separators=(",", ":"))


def seal(row: dict) -> str:
    """sha256 over the row's canonical serialisation, EXCLUDING the seal itself.

    The same style `seal_authority.py` hashes the prediction book with: sorted
    keys, no whitespace, so two processes that built the same row agree on its
    identity without agreeing on their JSON encoder's mood.
    """
    body = {k: v for k, v in row.items() if k != "artifact_sha256"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def decision_id(*, policy_id: str, policy_version: str, ticker: str,
                asof: str, revision_of: str | None = None) -> str:
    """The row's identity. `revision_of` is what makes a same-day revision a
    DIFFERENT decision rather than a rewrite of the first one: without it, a
    child built from the same policy, ticker and date would collide with its
    own parent, and the ledger would read the supersession as a duplicate."""
    blob = f"{policy_id}|{policy_version}|{ticker}|{asof}"
    if revision_of:
        blob = f"{blob}|revision_of:{revision_of}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def universe_hash(candidates: Any, generated_at: str | None) -> str:
    """DERIVED, because the funnel does not carry one.

    `assert_registry_discipline` gates the RANKING, not the universe, and the
    funnel payload has no hash field — so this hashes what a universe actually
    is: the sorted tickers that survived the screen, plus the snapshot's own
    timestamp. A funnel that is absent returns the words, not a zero digest.
    """
    try:
        tickers = sorted(str(t) for t in (candidates or {}))
    except TypeError:
        tickers = []
    if not tickers:
        return "CANNOT DETERMINE: no funnel candidates in this checkout"
    blob = f"{generated_at or 'no-generated-at'}|" + ",".join(tickers)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


#: Named windows a falsifier can declare, and the sessions they mean. Calendar
#: days, not trading days: the kill condition is a claim about the world, and a
#: quarter is a quarter whatever the exchange did.
_FALSIFIER_WINDOWS: tuple[tuple[str, int], ...] = (
    ("two consecutive quarters", 182),
    ("two quarters", 182),
    ("one quarter", 91),
    ("a quarter", 91),
    ("one month", 30),
    ("one session", 1),
)

#: "hold each name up to 21 sessions" — the agency `hold_rule`'s own maximum.
_SESSIONS_RE = re.compile(r"up to (\d+) sessions?")


def falsifier_expiry(falsifier: str, *, asof: date,
                     horizon_months: int) -> tuple[str | None, str]:
    """(expiry_utc, basis). The falsifier's OWN window when it names one.

    A kill condition that says "two consecutive quarters" expires in 182 days;
    one that names no window falls back to the policy horizon and the basis
    SAYS which of the two produced the date. A bare default would make an
    expiry that came from a guess indistinguishable from one that came from the
    condition.
    """
    low = str(falsifier or "").lower()
    for phrase, days in _FALSIFIER_WINDOWS:
        if phrase in low:
            when = datetime.combine(asof, datetime.min.time(), timezone.utc) + timedelta(days=days)
            return (when.isoformat(timespec="seconds"),
                    f"the falsifier's own window ({phrase} = {days} days)")
    # A hold rule that counts SESSIONS ("hold each name up to 21 sessions") is
    # the agency's own expiry and is far tighter than any policy horizon. Five
    # sessions to the week, so N sessions is ceil(N x 7/5) calendar days — the
    # conversion is named on the receipt rather than assumed by the reader.
    m = _SESSIONS_RE.search(low)
    if m:
        sessions = int(m.group(1))
        days = -(-sessions * 7 // 5)
        when = datetime.combine(asof, datetime.min.time(), timezone.utc) + timedelta(days=days)
        return (when.isoformat(timespec="seconds"),
                f"the hold rule's own maximum ({sessions} sessions = {days} "
                f"calendar days at 5 sessions a week)")
    if not low:
        return (None, "CANNOT DETERMINE: the row carries no falsifier, so it has "
                      "no window of its own and no policy horizon was declared")
    days = int(round(float(horizon_months) * 30.44))
    when = datetime.combine(asof, datetime.min.time(), timezone.utc) + timedelta(days=days)
    return (when.isoformat(timespec="seconds"),
            f"the policy horizon ({horizon_months} months = {days} days); the "
            f"falsifier names no window of its own")


def _base_row(*, policy_id: str, policy_version: str, ticker: str, asof: str,
              information_cutoff_utc: str | None, uni_hash: str) -> dict:
    return {
        "decision_id": decision_id(policy_id=policy_id,
                                   policy_version=policy_version,
                                   ticker=ticker, asof=asof),
        "asof": asof,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "information_cutoff_utc": information_cutoff_utc or (
            "CANNOT DETERMINE: the source payload carries no snapshot timestamp"),
        "licence": LICENCE,
        "universe_hash": uni_hash,
        "ticker": ticker,
    }


def _ic_rows(state: dict, book: dict, *, asof: date, capital: float) -> list[dict]:
    """One row per name the committee ranked: the tilts, then the refusals."""
    asof_s = str(asof)
    recs = list(state.get("recs") or [])
    candidates = state.get("candidates") or {}
    generated_at = state.get("funnel_generated_at")
    uni = universe_hash(candidates, generated_at)
    policy_id = "INVESTMENT_COMMITTEE_CORE_AND_TILTS"
    policy_version = str(generated_at or "CANNOT DETERMINE: no funnel generated_at")
    horizon_months = int(config.IC_WEALTH_HORIZON_MONTHS)
    cost = cost_model_row(
        "investment_committee.compose_book", round_trip_bps=None,
        basis=("the committee composes WEIGHTS on a benchmark core and prices no "
               "round trip; capacity is a DELAY-ONLY lower bound (CANON §17) and "
               "is not a cost. No cost model priced this row."))

    tilts = {p["ticker"]: p for p in (book.get("positions") or [])
             if p.get("source") == "evidence-led"}
    # The ROI rule's block for every name it considered (chunk 18c). Absent
    # entirely when `config.IC_ROI_RANKING` is off, so the flag is a true
    # revert: no key appears that today's rows do not already carry.
    roi_ranking = book.get("roi_ranking") or None
    roi_rows = dict((roi_ranking or {}).get("rows_by_ticker") or {})
    roi_unranked = dict((roi_ranking or {}).get("not_calibrated") or {})
    degradation = list(book.get("degradation_reasons") or [])
    by_ticker_degradation: dict[str, str] = {}
    for line in degradation:
        head = line.split(":", 1)[0].strip()
        if head and head.isupper() and head.replace(".", "").isalnum():
            by_ticker_degradation.setdefault(head, line)

    rows: list[dict] = []
    refused: list[dict] = []
    for r in recs:
        ticker = str(getattr(r, "ticker", "") or "")
        if not ticker:
            continue
        kill, kill_status = kill_condition(r)
        expiry, expiry_basis = falsifier_expiry(kill, asof=asof,
                                                horizon_months=horizon_months)
        lead = r.leader() if hasattr(r, "leader") else None
        signal = getattr(lead, "signal_id", None) or (
            "CANNOT DETERMINE: no rank-bearing signal is available for this name")
        row = _base_row(policy_id=policy_id, policy_version=policy_version,
                        ticker=ticker, asof=asof_s,
                        information_cutoff_utc=generated_at, uni_hash=uni)
        row.update({
            "source": "investment_committee",
            "signal": signal,
            "horizon": {"months": horizon_months,
                        "basis": "config.IC_WEALTH_HORIZON_MONTHS"},
            "expected_payoff": NOT_CALIBRATED,
            "expected_payoff_basis": (
                "the committee reports an ORDERING and refuses a per-name return "
                "it cannot defend; the licensed pickers are SUPPORTED, not "
                "VALIDATED"),
            "estimated_probability": None,
            "estimated_probability_reason": (
                "no agency Option covers this name, and the committee publishes "
                "no calibrated P(win) for a tilt"),
            "cost_model": cost,
            "falsifier": kill or (
                "CANNOT DETERMINE: no kill condition is set for this name"),
            "falsifier_status": kill_status,
            "expiry_utc": expiry,
            "expiry_basis": expiry_basis,
            "rank": getattr(r, "rank", None),
            "confidence": getattr(r, "confidence", None),
            "evidence_grade": getattr(r, "evidence_grade", None),
            "ranking_score": getattr(r, "ranking_score", None),
            "verdict": getattr(r, "recommendation", None),
        })
        if roi_ranking is not None:
            row.update(_roi_fields(ticker, roi_rows, roi_unranked))
        pos = tilts.get(ticker)
        if pos is not None:
            verdict = str(getattr(r, "recommendation", "") or "")
            row["direction"] = "BUY" if verdict == "BUY" else "WATCH"
            row["position_budget"] = {
                "weight": pos.get("weight"), "dollars": pos.get("dollars"),
                "shares": pos.get("shares"), "price": pos.get("price"),
                "capital_usd": float(capital),
                "basis": "investment_committee.compose_book at this capital level",
            }
            row["maximum_loss"] = worst_case_no_stop(
                n_names=1, notional_pct=float(pos.get("weight") or 0.0),
                equity_usd=float(capital))
            row["reason"] = pos.get("reason")
            row["capacity"] = pos.get("capacity")
            rows.append(row)
            continue
        # REFUSED: name the gate that stopped it, in this repo's own words.
        why = _refusal_sentence(r, by_ticker_degradation.get(ticker))
        row.update({
            "direction": "REFUSED",
            "position_budget": {
                "weight": 0.0, "dollars": 0.0, "shares": 0, "price": None,
                "capital_usd": float(capital),
                "basis": "refused — no budget was allocated"},
            "maximum_loss": worst_case_no_stop(
                n_names=0, notional_pct=0.0, equity_usd=float(capital),
                gross_over_equity=0.0,
                why="refused — nothing is at risk on a row that was not taken"),
            **classify_refusal(why),
        })
        refused.append(row)

    refused.sort(key=lambda d: (d.get("rank") is None, d.get("rank") or 0))
    kept = refused[:MAX_REFUSED_ROWS]
    return rows + kept


#: The fields an ROI-scored row carries, in the order a reader wants them.
_ROI_ROW_FIELDS: tuple[str, ...] = (
    "expected_return_net_pct", "downside_pct", "roi_score", "roi_rank",
    "kelly_fraction", "kelly_weight", "roi_basis", "roi_measured_on", "roi_t",
    "roi_n_blocks", "expected_return_basis", "downside_basis",
    "kelly_fraction_basis")


def _roi_fields(ticker: str, rows: dict, unranked: dict) -> dict:
    """The ROI block for one name: the numbers, or the reason there are none.

    Three populations and no fourth. A name the rule SCORED carries the two
    measured inputs, the ratio, its rank and its Kelly fraction, plus the
    receipt path the expected return came off. A name the rule CONSIDERED and
    could not score carries the sentence naming the missing field. A name that
    never reached the rule — every REFUSED row, because the hard gates run
    first and the rule only ever sees survivors — says exactly that, so a
    reader can never mistake "refused at the gate" for "the ROI rule declined
    it".
    """
    t = str(ticker)
    if t in rows:
        body = rows[t]
        out = {k: body[k] for k in _ROI_ROW_FIELDS if k in body}
        out["roi"] = "SCORED"
        return out
    if t in unranked:
        return {"roi": unranked[t]}
    return {"roi": (f"{NOT_CALIBRATED_ROI}: not considered — this name never "
                    f"entered the ROI ranking, because the hard eligibility "
                    f"gates run first and the rule only ever sees the "
                    f"candidates they admitted")}


def _refusal_sentence(r: Any, degradation_line: str | None) -> str:
    """WHY this candidate is not a tilt, in the gate's own terms.

    Ordered the way `compose_book` itself checks, so the sentence names the
    FIRST gate that stopped the name rather than the last one a reader noticed.
    """
    grade = getattr(r, "evidence_grade", "NO_EVIDENCE")
    verdict = str(getattr(r, "recommendation", "") or "")
    score = getattr(r, "ranking_score", 0.0) or 0.0
    if grade == "NO_EVIDENCE":
        return ("no licensed signal speaks to this name (evidence grade "
                "NO_EVIDENCE): screened, liquid and priced, and the engine has "
                "nothing it is allowed to say about it")
    if verdict not in config.IC_TILT_VERDICT_SCALE:
        return (f"verdict {verdict or 'NONE'} is not BUY or WATCH, so no tilt is "
                f"licensed")
    if float(score) <= 0:
        return f"ranking score {float(score):.4f} is not positive"
    if degradation_line:
        return degradation_line
    return (f"ranked below the IC_MAX_TILT_NAMES cap "
            f"({config.IC_MAX_TILT_NAMES} names) or outranked inside the "
            f"{config.IC_TOTAL_TILT_BUDGET:.0%} total tilt budget")


def _agency_rows(options: list, *, asof: date) -> list[dict]:
    """One row per surfaced `Option`. A BOOK, not a ticker — and it says so."""
    asof_s = str(asof)
    rows: list[dict] = []
    for opt in options or []:
        try:
            data = opt.as_row()
        except Exception as exc:                                   # noqa: BLE001
            logger.warning("agency option unreadable: %s", exc)
            continue
        personality = str(data.get("personality") or "unknown")
        contract_hash = str(data.get("contract_hash") or "")
        name = f"AGENCY_BOOK:{personality}"
        row = _base_row(policy_id=f"AGENCY_{personality.upper()}",
                        policy_version=contract_hash or "CANNOT DETERMINE: the "
                                                        "option carries no contract hash",
                        ticker=name, asof=asof_s,
                        information_cutoff_utc=asof_s, uni_hash=contract_hash or "")
        worst = dict(data.get("worst_case") or {})
        costs_priced = data.get("cost_model") or data.get("cost_curve")
        row.update({
            "source": "agency",
            "instrument_kind": "book",
            "signal": data.get("signal") or "CANNOT DETERMINE: the strategy names no signal",
            "direction": "BUY",
            "horizon": {"cadence": data.get("cadence"),
                        "basis": "the agency Strategy's own rebalance cadence"},
            "expected_payoff": NOT_CALIBRATED,
            "expected_payoff_basis": (
                "an Option carries its contract, its twins and its worst case and "
                "never a return, because it has not run"),
            "estimated_probability": None,
            "estimated_probability_reason": (
                "a probability exists only once the book is HELD and reviewed "
                "(agency.decide_label reads a realised price path); a proposal "
                "has none"),
            "cost_model": cost_model_row(
                str(costs_priced or "agency.build_strategy costs"),
                round_trip_bps=_maybe_bps(data),
                basis=("the Strategy's own declared cost row travels on every "
                       "option (`strategy.costs.as_row()`)")),
            "position_budget": {
                "weight": data.get("max_single_name"),
                "dollars": data.get("notional_usd"),
                "shares": None,
                "k": data.get("k"),
                "gross_cap": data.get("gross_cap"),
                "cash_floor_pct": data.get("cash_floor_pct"),
                "basis": "agency.propose -> Strategy.sizing / construction",
            },
            "maximum_loss": worst or worst_case_no_stop(
                n_names=int(data.get("k") or 0),
                notional_pct=float(data.get("max_single_name") or 0.0),
                equity_usd=float(data.get("notional_usd") or 0.0)),
            "falsifier": data.get("hold_rule") or (
                "CANNOT DETERMINE: the option carries no hold rule"),
            "falsifier_status": "DECLARED_BY_CONTRACT",
            "is_declared_choice": data.get("is_declared_choice"),
            "twins": data.get("twins"),
        })
        expiry, basis = falsifier_expiry(
            str(data.get("hold_rule") or ""), asof=asof,
            horizon_months=int(config.IC_WEALTH_HORIZON_MONTHS))
        row["expiry_utc"] = expiry
        row["expiry_basis"] = basis
        if config.IC_ROI_RANKING:
            row["roi"] = (
                f"{NOT_CALIBRATED_ROI}: not a name — an agency Option is a "
                f"whole costed BOOK. The ROI rule ranks candidates inside the "
                f"committee's tilt sleeve against each other; there is no "
                f"measured per-book expected return that would let it rank one "
                f"personality's book against another's, and the three books "
                f"are not alternatives at one capital level anyway.")
        rows.append(row)
    return rows


def _maybe_bps(data: dict) -> float | None:
    """The round-trip cost the strategy declares, or None — never a zero.

    `Strategy.costs.as_row()` spells its fields differently across versions, so
    the lookup is by NAME over the keys that exist and the absence of all of
    them is CANNOT DETERMINE rather than a helpful 0.0.
    """
    for key in ("round_trip_bps", "cost_bps", "total_bps", "one_way_bps"):
        v = data.get(key)
        if v is None:
            continue
        try:
            bps = float(v)
        except (TypeError, ValueError):
            continue
        return bps * 2.0 if key == "one_way_bps" else bps
    return None


# ===========================================================================
# THE BUILD
# ===========================================================================


def contracts_path(asof: str | date, out_dir: Path | None = None) -> Path:
    return Path(out_dir or DECISIONS_DIR) / f"{asof}.json"


def build_daily_contracts(asof: date | str | None = None, *,
                          capital: float | None = None,
                          funnel_path: Path | None = None,
                          out_dir: Path | None = None,
                          write: bool = True) -> list[dict]:
    """The day's rows: every committee tilt, every refusal, every agency option.

    Derived end to end from computation that already happened. The only thing
    this function decides is the SHAPE of the receipt; if an input is absent the
    row says CANNOT DETERMINE by name and the payload counts it.
    """
    day = _as_date(asof)
    notes: list[str] = []

    options, agency_note = agency_options(day)
    if capital is None:
        capital, capital_basis = _capital_from(options)
    else:
        capital, capital_basis = float(capital), "named by the caller"
    notes.append(f"capital ${capital:,.0f} — {capital_basis}")
    try:
        state = funnel_state(funnel_path)
    except Exception as exc:                                       # noqa: BLE001
        logger.exception("decision contract: funnel state failed")
        state = {"available": False, "recs": [], "candidates": {},
                 "degradation_reasons": [f"CANNOT DETERMINE: {type(exc).__name__}: {exc}"]}
        notes.append(f"CANNOT DETERMINE: the funnel state could not be built "
                     f"({type(exc).__name__}: {exc})")
    if not state.get("available"):
        notes.append("CANNOT DETERMINE: no funnel run available in this checkout, "
                     "so the committee ranked nothing today")

    try:
        book = compose_book(
            state.get("recs") or [], capital=capital,
            candidates=state.get("candidates") or {},
            refusal_reasons=(state.get("books") or {}).get("refused") or {},
            extra_degradation=[d for d in state.get("degradation_reasons") or []
                               if "REFUSED" not in d])
    except Exception as exc:                                       # noqa: BLE001
        logger.exception("decision contract: compose_book failed")
        book = {"positions": [], "degradation_reasons":
                [f"CANNOT DETERMINE: compose_book raised {type(exc).__name__}: {exc}"]}
        notes.append(f"CANNOT DETERMINE: the book could not be composed "
                     f"({type(exc).__name__}: {exc})")

    rows = _ic_rows(state, book, asof=day, capital=capital)

    if agency_note:
        notes.append(agency_note)
    rows.extend(_agency_rows(options, asof=day))

    for row in rows:
        row["built_utc"] = _now()
        row["artifact_sha256"] = seal(row)

    if write:
        write_contracts(rows, asof=day, out_dir=out_dir, notes=notes,
                        capital=capital, book=book)
    return rows


def _capital_from(options: list) -> tuple[float, str]:
    """The equity both halves of the contract are sized against.

    The IPS's own `capital_usd` when a policy exists, because that is the
    number Murat declared and the agency has already sized against it — a
    committee book quoted at a different capital beside it would put two
    incomparable dollar columns on one page. With no policy it falls back to
    the largest CONFIGURED level, and the basis travels onto the receipt so a
    reader never has to guess which of the two produced the dollars.
    """
    for opt in options or []:
        try:
            notional = float(opt.as_row().get("notional_usd") or 0.0)
        except Exception:                                          # noqa: BLE001
            continue
        if notional > 0:
            return notional, ("the declared IPS capital (agency "
                              "Strategy.sizing.notional_usd)")
    levels = [float(c) for c in config.IC_CAPITAL_LEVELS]
    return max(levels), ("no IPS document exists, so the largest CONFIGURED "
                         "level (config.IC_CAPITAL_LEVELS) is used and named")


# ===========================================================================
# REVISION — spec §D. A new row, never a rewritten one.
# ===========================================================================


def find_contract_row(decision_id_: str, *, out_dir: Path | None = None,
                      days: int = 366) -> tuple[dict | None, Path | None]:
    """(row, file) for one `decision_id`, newest file first, or (None, None).

    A year of per-day files, the same window `decision_ledger._open_contract_
    rows` reads, for the same reason: a revision is about a decision whose
    window is still open, and scanning five years of receipts to find one is
    budget spent on rows nobody can act on.
    """
    folder = Path(out_dir or DECISIONS_DIR)
    if not folder.is_dir():
        return None, None
    want = str(decision_id_)
    floor = datetime.now(timezone.utc).date() - timedelta(days=int(days))
    for p in sorted(folder.glob("*.json"), reverse=True):
        try:
            if date.fromisoformat(p.stem) < floor:
                continue
        except ValueError:
            continue
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in blob.get("rows") or []:
            if str(row.get("decision_id")) == want:
                return row, p
    return None, None


def _typed_updates(updates: dict | None) -> tuple[dict, str]:
    """({ticker: {field: number|None}}, refusal) — numbers only, never text.

    The firewall the spec names: *no LLM output writes a revision directly*. A
    typed event reaches this function as a CANDIDATE FIELD — the same kind of
    thing a price update is — and the ranking rule is the only thing that can
    move a direction. So a string, a dict, a list or a bool in the update
    payload is REFUSED by name rather than coerced: a free-text "very bullish"
    that silently became a field would be the LLM sizing a position through the
    back door, which is the one thing `belief_state.py`'s firewall forbids.
    """
    clean: dict[str, dict] = {}
    for ticker, fields in (updates or {}).items():
        if not isinstance(fields, dict):
            return {}, (f"CANNOT DETERMINE: the update for {ticker!r} is a "
                        f"{type(fields).__name__}, not a mapping of candidate "
                        f"fields to numbers")
        row: dict = {}
        for name, value in fields.items():
            if value is None:
                row[str(name)] = None
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return {}, (
                    f"REFUSED: {ticker}.{name} = {value!r} is a "
                    f"{type(value).__name__}. A revision takes CANDIDATE "
                    f"FIELDS — numbers the signal scorer reads — never text. "
                    f"The LLM proposes and forecasts; the engine computes and "
                    f"allocates, and that firewall is enforced here rather "
                    f"than intended.")
            row[str(name)] = float(value)
        clean[str(ticker)] = row
    return clean, ""


def _restate(state: dict, updates: dict) -> tuple[dict, str]:
    """Re-run the SAME signal-scoring path over updated candidate fields."""
    from backend.services import recommendation as REC
    from backend.services import signal_registry as SR

    cands = [dict(c) for c in (state.get("candidates") or {}).values()]
    if not cands:
        return state, ("CANNOT DETERMINE: the funnel state carries no "
                       "candidates, so there is nothing to re-rank")
    for c in cands:
        patch = updates.get(str(c.get("ticker")))
        if patch:
            c.update(patch)
    reg = SR.load()
    try:
        REC.assert_registry_discipline(cands, registry=reg)
    except REC.RankLeadershipError as exc:
        return state, (f"CANNOT DETERMINE: the ranking gate is VOID on the "
                       f"revised candidates, so no revision is licensed ({exc})")
    out = dict(state)
    out["candidates"] = {str(c.get("ticker")): c for c in cands}
    out["recs"] = REC.score_candidates(cands, registry=reg)
    return out, ""


def revise(parent_decision_id: str, *, asof: date | str | None = None,
           reason: str = "", candidate_updates: dict | None = None,
           funnel_path: Path | None = None, out_dir: Path | None = None,
           ledger_path: Path | None = None, write: bool = True) -> dict:
    """Re-run the ranking over the affected capital level; supersede or don't.

    The rule, and the whole of it: re-score the candidates through
    `recommendation.score_candidates`, recompose the book at the PARENT's own
    capital, and compare the parent row's direction and rank-cut with the new
    one. If neither moved, **nothing is written** — a revision that changes no
    decision is not an event, and a ledger that recorded it would report
    activity it did not have. If either moved, a NEW row is written with
    `parent_decision_id` set, `REVISED` is recorded on the parent and `DECIDED`
    on the child.

    `reason` is recorded and READ BY NOBODY: it travels onto the ledger detail
    so a human can see why the re-run was triggered, and it cannot reach the
    ranking. `candidate_updates` is the only input that can change an outcome
    and it is numbers only (`_typed_updates`).
    """
    from backend.services import decision_ledger as DL

    day = _as_date(asof)
    parent, parent_path = find_contract_row(parent_decision_id, out_dir=out_dir)
    if parent is None:
        return {"status": "refused", "parent_decision_id": str(parent_decision_id),
                "reason": (f"CANNOT DETERMINE: no contract row in the last year "
                           f"carries decision_id {parent_decision_id!r}")}
    if parent.get("source") != "investment_committee":
        return {"status": "refused", "parent_decision_id": str(parent_decision_id),
                "reason": (f"REFUSED: {parent.get('ticker')} is a "
                           f"{parent.get('source')} row. An agency Option is a "
                           f"whole costed BOOK with its own contract hash; "
                           f"re-ranking one name inside it is not what this "
                           f"function does, and pretending otherwise would put "
                           f"a name-level revision on a book-level decision.")}

    updates, refusal = _typed_updates(candidate_updates)
    if refusal:
        return {"status": "refused", "parent_decision_id": str(parent_decision_id),
                "reason": refusal}

    capital = float((parent.get("position_budget") or {}).get("capital_usd")
                    or 0.0)
    if capital <= 0:
        return {"status": "refused", "parent_decision_id": str(parent_decision_id),
                "reason": ("CANNOT DETERMINE: the parent row names no capital "
                           "level, so there is no book to recompose it in")}

    try:
        state = funnel_state(funnel_path)
    except Exception as exc:                                       # noqa: BLE001
        return {"status": "refused", "parent_decision_id": str(parent_decision_id),
                "reason": (f"CANNOT DETERMINE: the funnel state could not be "
                           f"rebuilt ({type(exc).__name__}: {exc})")}
    state, refusal = _restate(state, updates)
    if refusal:
        return {"status": "refused", "parent_decision_id": str(parent_decision_id),
                "reason": refusal}

    book = compose_book(
        state.get("recs") or [], capital=capital,
        candidates=state.get("candidates") or {},
        refusal_reasons=(state.get("books") or {}).get("refused") or {},
        extra_degradation=[d for d in state.get("degradation_reasons") or []
                           if "REFUSED" not in d])
    ticker = str(parent.get("ticker"))
    fresh = [r for r in _ic_rows(state, book, asof=day, capital=capital)
             if str(r.get("ticker")) == ticker]
    if not fresh:
        return {"status": "refused", "parent_decision_id": str(parent_decision_id),
                "reason": (f"CANNOT DETERMINE: {ticker} is no longer in the "
                           f"funnel's candidate set, so the ranking cannot be "
                           f"re-run for it. The parent stays exactly as it was "
                           f"decided; a name that left the universe is a fact "
                           f"about the universe, not a revision.")}
    child = fresh[0]

    was_held = str(parent.get("direction")) != "REFUSED"
    now_held = str(child.get("direction")) != "REFUSED"
    changed = {
        "direction": (str(parent.get("direction")), str(child.get("direction"))),
        "rank_cut": (was_held, now_held),
    }
    moved = (changed["direction"][0] != changed["direction"][1]
             or was_held != now_held)
    if not moved:
        return {"status": "unchanged", "parent_decision_id": str(parent_decision_id),
                "ticker": ticker, "capital_usd": capital,
                "comparison": changed,
                "reason": ("the re-run produced the same direction and the same "
                           "side of the rank cut, so nothing was superseded and "
                           "nothing was written")}

    child["decision_id"] = decision_id(
        policy_id=str(child.get("policy_id")),
        policy_version=str(child.get("policy_version")),
        ticker=ticker, asof=str(day), revision_of=str(parent_decision_id))
    child["parent_decision_id"] = str(parent_decision_id)
    child["revision_reason"] = str(reason or "")
    child["revision_comparison"] = changed
    child["built_utc"] = _now()
    child["artifact_sha256"] = seal(child)

    written_to = None
    if write:
        path = contracts_path(str(day), out_dir)
        rows: list[dict] = []
        notes: list[str] = []
        capital_on_file = capital
        if path.is_file():
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                rows = list(blob.get("rows") or [])
                notes = list(blob.get("notes") or [])
                capital_on_file = blob.get("capital_usd") or capital
            except (OSError, ValueError):
                rows, notes = [], []
        rows = [r for r in rows
                if str(r.get("decision_id")) != child["decision_id"]]
        rows.append(child)
        notes.append(f"revision: {child['decision_id']} supersedes "
                     f"{parent_decision_id} for {ticker} "
                     f"({changed['direction'][0]} -> {changed['direction'][1]}); "
                     f"the parent row is untouched")
        written_to = str(write_contracts(rows, asof=day, out_dir=out_dir,
                                         notes=notes, capital=capital_on_file,
                                         book=book))

    detail = {"child_decision_id": child["decision_id"], "ticker": ticker,
              "reason": str(reason or ""), "comparison": changed,
              "candidate_updates": updates}
    if not DL.states_of(str(parent_decision_id), path=ledger_path):
        DL.record(str(parent_decision_id), "DECIDED", by="contract_file",
                  asof=parent.get("asof"), path=ledger_path,
                  detail={"backfilled": True,
                          "why": ("the contract file carries this row and the "
                                  "ledger did not")})
    DL.record(child["decision_id"], "DECIDED", by="decision_contract.revise",
              asof=str(day), path=ledger_path,
              detail={"parent_decision_id": str(parent_decision_id)})
    parent_state = DL.record(str(parent_decision_id), "REVISED",
                             by="decision_contract.revise",
                             asof=parent.get("asof"), path=ledger_path,
                             detail=detail)

    return {"status": "revised", "parent_decision_id": str(parent_decision_id),
            "child_decision_id": child["decision_id"], "ticker": ticker,
            "capital_usd": capital, "comparison": changed, "child": child,
            "written_to": written_to, "parent_ledger_row": parent_state,
            "parent_contract_file": str(parent_path) if parent_path else None}


def _as_date(asof: date | str | None) -> date:
    if asof is None:
        return datetime.now(timezone.utc).date()
    if isinstance(asof, date):
        return asof
    return date.fromisoformat(str(asof))


def payload(rows: list[dict], *, asof: date, notes: list[str] | None = None,
            capital: float | None = None, book: dict | None = None) -> dict:
    counts = {d: sum(1 for r in rows if r.get("direction") == d)
              for d in DIRECTIONS}
    by_class: dict[str, int] = {}
    by_terminal: dict[str, int] = {}
    # Why each UNCLASSIFIED row is unclassified, counted. A day whose
    # UNCLASSIFIED rows all carry a basis this repo wrote deliberately owes
    # nothing; a day with an `unmatched` entry owes a pattern.
    unclassified_basis: dict[str, int] = {}
    for r in rows:
        if r.get("direction") != "REFUSED":
            continue
        by_class[r.get("refusal_class", UNCLASSIFIED)] = \
            by_class.get(r.get("refusal_class", UNCLASSIFIED), 0) + 1
        by_terminal[r.get("terminal_state", OTHER_TYPED)] = \
            by_terminal.get(r.get("terminal_state", OTHER_TYPED), 0) + 1
        if r.get("refusal_class", UNCLASSIFIED) == UNCLASSIFIED:
            key = str(r.get("refusal_class_basis")
                      or "CANNOT DETERMINE: the row carries no class basis")
            unclassified_basis[key] = unclassified_basis.get(key, 0) + 1
    produced = {r.get("direction") for r in rows}
    return {
        "receipt": "decision_contract",
        "roadmap_item": "chunk 18",
        "licence": LICENCE,
        "date": str(asof),
        "written_utc": _now(),
        "n_rows": len(rows),
        "count_by_direction": counts,
        "count_by_refusal_class": by_class,
        "count_by_terminal_state": by_terminal,
        "count_by_unclassified_basis": unclassified_basis,
        "unclassified_owing_a_pattern": sum(
            n for b, n in unclassified_basis.items() if b.startswith("NO PATTERN MATCHED")),
        "capital_usd": capital,
        "directions_not_produced_today": sorted(d for d in DIRECTIONS
                                                if d not in produced),
        **_roi_payload_block(rows, book),
        "worst_case_largest_admissible_book": largest_admissible_book(),
        "notes": list(notes or []),
        "degradation_reasons": list((book or {}).get("degradation_reasons") or []),
        "rows": rows,
        "read_me_first": (
            "Every number here was computed by `investment_committee` or "
            "`agency` before this file existed; nothing in it was forecast, "
            "sized or priced by a model. `expected_payoff` is the string "
            f"{NOT_CALIBRATED!r} because no calibrated per-name return exists — "
            "it is a FIELD, not an omission. A REFUSED row carries one class "
            "from the execution repo's own closed vocabulary, so 'why no trade' "
            "groups across both repos. Nothing here places, sizes, arms or "
            "seals anything: the engine decided, this file records, and the two "
            "LLM surfaces read it."),
    }


def _roi_payload_block(rows: list[dict], book: dict | None) -> dict:
    """The day's ROI census, or nothing at all when the flag is off.

    Counts the rows the rule SCORED and groups the rest by the FIELD that was
    missing, because "38 rows are not calibrated" is not a finding and "36 of
    them have no measured return for their leading signal, 2 have no
    volatility" is. The per-ticker sentences stay on the rows; only the census
    is here, so the file does not carry the same prose twice.
    """
    ranking = (book or {}).get("roi_ranking")
    if not ranking:
        return {}
    scored = sum(1 for r in rows if r.get("roi") == "SCORED")
    by_field: dict[str, int] = {}
    for r in rows:
        text = str(r.get("roi") or "")
        if not text.startswith(NOT_CALIBRATED_ROI):
            continue
        tail = text[len(NOT_CALIBRATED_ROI):].lstrip(": ")
        field_name = tail.split("—")[0].strip() or "unstated"
        by_field[field_name] = by_field.get(field_name, 0) + 1
    census = {k: v for k, v in ranking.items()
              if k not in ("rows_by_ticker", "not_calibrated")}
    census["n_rows_scored"] = scored
    census["n_rows_not_calibrated_by_missing_field"] = by_field
    return {"roi_ranking": census}


def write_contracts(rows: list[dict], *, asof: date, out_dir: Path | None = None,
                    notes: list[str] | None = None, capital: float | None = None,
                    book: dict | None = None) -> Path:
    """Atomic write. A half-written receipt is worse than none: a reader cannot
    tell a truncated file from a day on which the engine found two names."""
    path = contracts_path(asof, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload(rows, asof=asof, notes=notes, capital=capital,
                              book=book), ensure_ascii=False, indent=1)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(blob, encoding="utf-8")
    os.replace(tmp, path)
    return path


def latest(asof: str | date | None = None, out_dir: Path | None = None) -> dict | None:
    """Today's contract file, or None. Reads; never builds anything."""
    day = str(_as_date(asof))
    path = contracts_path(day, out_dir)
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("decision contract unreadable at %s: %s", path, exc)
        return None
    blob["path"] = str(path)
    return blob


def ranked_rows(blob: dict, *, directions: tuple[str, ...] = ("BUY", "WATCH"),
                limit: int = 10) -> list[dict]:
    """The actionable rows, best rank first. Shared by both LLM surfaces so the
    web copilot and the desktop Ask cannot disagree about what today said."""
    rows = [r for r in (blob.get("rows") or [])
            if r.get("direction") in directions]
    rows.sort(key=lambda r: (r.get("direction") != "BUY",
                             r.get("rank") is None, r.get("rank") or 0))
    return rows[:limit]


def summarise_for_reader(blob: dict | None, *,
                         record: Optional[Callable[[str], None]] = None) -> str:
    """The sentence the two chat surfaces answer with — computed, not generated.

    A model asked "what would you buy" with a contract in front of it may read
    these rows out; a model asked the same question with no contract must say
    the engine has not written one. Both answers are built HERE, from the file,
    so the two surfaces cannot drift and neither can invent a name.
    """
    if not blob:
        return ("No decision contract has been written for today, so the engine "
                "has not said what it would buy. Run the morning (it writes one "
                "contract row per ranked name before it answers). I will not "
                "invent one: a decision that is not in the contract cannot be "
                "graded tomorrow.")
    rows = ranked_rows(blob)
    counts = blob.get("count_by_direction") or {}
    head = (f"Today's decision contract ({blob.get('date')}), written by the "
            f"engine: {counts.get('BUY', 0)} BUY, {counts.get('WATCH', 0)} "
            f"WATCH, {counts.get('REFUSED', 0)} REFUSED.")
    if not rows:
        return (head + " No name cleared the tilt gate today, so there is "
                       "nothing the engine would buy. The refusal classes are on "
                       "the receipt.")
    lines = [head]
    for r in rows:
        if record is not None:
            record(str(r.get("decision_id")))
        budget = r.get("position_budget") or {}
        loss = r.get("maximum_loss") or {}
        # A BOOK row and a NAME row size differently and must not be read with
        # one sentence: `weight` is a per-name cap on the first and the whole
        # position on the second, and printing both as "x% of the book" is how
        # a 10% cap gets read as a 10% position.
        if r.get("instrument_kind") == "book":
            size = (f"a whole book of {budget.get('k')} names at "
                    f"{_usd(budget.get('dollars'))}, capped "
                    f"{_pct(budget.get('weight'))} per name")
        else:
            size = (f"{_pct(budget.get('weight'))} of the book "
                    f"({_usd(budget.get('dollars'))}, "
                    f"{budget.get('shares')} shares)")
        lines.append(
            f"- {r.get('direction')} {r.get('ticker')} — {size}; "
            f"signal {r.get('signal')}; expected payoff {r.get('expected_payoff')}; "
            f"worst case {_usd(loss.get('worst_case_usd'))}; "
            f"falsifier: {r.get('falsifier')}; expires {r.get('expiry_utc')}.")
    lines.append(f"Policy: {rows[0].get('policy_id')} "
                 f"version {rows[0].get('policy_version')}, licence "
                 f"{blob.get('licence')}. The engine sized these; nothing here "
                 f"placed an order.")
    return "\n".join(lines)


def _pct(v) -> str:
    try:
        return f"{100.0 * float(v):.2f}%"
    except (TypeError, ValueError):
        return "—"


def _usd(v) -> str:
    """`-$20,000`, never `$-20,000`. The sign belongs outside the symbol, and a
    loss that reads as a price is a loss a reader skims past."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "CANNOT DETERMINE"
    return f"{'-' if x < 0 else ''}${abs(x):,.0f}"
