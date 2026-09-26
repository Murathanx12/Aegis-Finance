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

WHERE `PROBE` COMES FROM (chunk 23a-ii, 2026-09-21)
---------------------------------------------------
`decision_authority` sends a name to `PROBE` when it cleared every hard gate
and then had no measured read. That is the SMALL half. The larger half is
here: a refused, ranked name whose refusal MEANS an absence of measurement —
`NO_ACTION_VERDICT` (the engine has no view) or `NO_LICENSED_SIGNAL` (nothing
licensed speaks to it), `config.PROBE_REFUSAL_CLASSES` — becomes a PROBE row
too, at zero weight, keeping the gate's own refusal sentence on the row as
`probe_basis`. Nothing reopens a gate: the name is still refused CAPITAL, and
what changes is only that it is no longer refused out of the LEDGER
(roadmap §16.5 item 39).

The distinction the pinned 31 could not make is why `LOCAL_REFUSAL_CLASSES`
exists: `EDGE_BELOW_BAR` is the class for both "verdict HOLD, nothing
measured" and "the measurement came back negative", and PROBE must take the
first and refuse the second. The verdict is the second key, because
`_refusal_sentence` writes one sentence for every non-BUY/WATCH verdict and a
SELL is a view AGAINST the name rather than an absence of one.

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
from backend.services import decision_authority as DA

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
#:
#: `PROBE` joined them on 2026-09-21 (chunk 23a). It is a VIRTUAL row: weight
#: zero, dollars zero, graded at its own expiry like every other row, and it
#: exists because refusing a name for having no measurement is the right
#: capital decision and the wrong learning decision — nothing accrues, so the
#: absence perpetuates itself (roadmap §16.2, §16.5 item 39).
DIRECTIONS: tuple[str, ...] = ("BUY", "WATCH", "SELL", "PROBE", "REFUSED")

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
#:
#: **PROBE rows are exempt** (chunk 23a). They are not noise to be trimmed —
#: they are the panel, and a trim at 50 would silently cap what this programme
#: can ever measure. They carry their own, much larger ceiling
#: (`config.PROBE_MAX_NAMES_PER_DAY`, applied by RANK in `decision_authority`),
#: and the count that ceiling cut is on the payload too.
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

#: THIS repo's own answer to "what does the refusal MEAN", and it is NOT the
#: execution repo's vocabulary and is NOT pinned to it (chunk 23a-ii).
#:
#: It exists because the pinned 31 cannot make the one distinction PROBE turns
#: on. `EDGE_BELOW_BAR` is the class for BOTH "this name carries no view at
#: all" (verdict HOLD, nothing measured) and "the measurement came back
#: negative" — and those are opposite findings: the first is an absence of
#: evidence and the second IS evidence. Roadmap §16.5 item 39 ("a refusal to
#: fund is not a refusal to learn") applies to the first and must not apply to
#: the second, so the two need different names somewhere. They get them here,
#: on a SECOND field, while `refusal_class` stays byte-identical to the closed
#: vocabulary a cross-repo census joins on.
LOCAL_REFUSAL_CLASSES: tuple[str, ...] = (
    # ---- not enough measurement: these are PROBE's (config.PROBE_REFUSAL_CLASSES)
    "NO_ACTION_VERDICT",        # HOLD / NO_ACTION — the engine has no view
    "NO_LICENSED_SIGNAL",       # screened and priced; no licensed signal speaks
    # ---- a measurement, or a view, that says no --------------------------
    "MEASURED_NO_EV",           # the read came back at or below the floor
    "VIEW_AGAINST",             # SELL / AVOID — a view, not an absence
    "CALIBRATED_OUTRANKED",     # proven, and it lost its slot
    # ---- the book, the tape, the inputs ----------------------------------
    "EXPLORE_BUDGET_FULL", "VOL_MISSING", "INPUT_MISSING", "LIQUIDITY",
    "CAPACITY", "RANKED_OUT", "STRUCTURE", "MANDATE", "MDE", "PROBE_CEILING",
    # ---- LAST: nothing matched, and it is counted ------------------------
    "UNTYPED",
)

UNTYPED = "UNTYPED"

#: (class, terminal_state, pattern, basis, local_class) for THIS repo's own
#: refusal sentences. Ordered, first match wins, most specific first — the
#: execution repo's rule, because "no candidate clears the tilt gate" must not
#: be read as the per-name verdict refusal it quotes.
#:
#: `basis` is the FOURTH element and it exists because of 2026-09-20: the day's
#: contract carried 7 UNCLASSIFIED refusals and a reader could not tell whether
#: the sentence had matched a pattern that deliberately maps to UNCLASSIFIED or
#: had matched nothing at all. Those are opposite findings — the first is "the
#: closed vocabulary has no class for this", which is a fact about the execution
#: repo's 31 classes; the second is "a gate wrote a sentence nobody has typed",
#: which is work owed here. Every row now carries the basis that produced its
#: class, so the two are one field apart instead of indistinguishable.
_LOCAL_PATTERNS: tuple[tuple[str, str, str, str, str], ...] = (
    # ---- pass-level: nothing at all cleared -------------------------------
    ("NO_STRUCTURE_CLEARED", "STRUCTURE", r"no candidate clears the tilt gate",
     "the pass-level refusal: nothing at all cleared the tilt gate",
     "STRUCTURE"),
    # ---- MEASURED, and the measurement said no (chunk 23a-ii) -------------
    # This sentence is chunk 21's and it had NO pattern until 2026-09-21: it
    # was the ONE row on that day's contract whose basis said NO PATTERN
    # MATCHED, i.e. the one that actually owed work under this file's own
    # rule. It must be matched BEFORE the generic merit pattern below, and
    # its LOCAL class is what keeps it out of PROBE: a read that came back
    # negative is EVIDENCE, and probing it again would spend the panel on a
    # question that has already been answered.
    ("EDGE_BELOW_BAR", "NEGATIVE_EV",
     r"not above EXPLORE_MIN_NET_PCT|no positive expected value",
     "a measured read came back at or below the floor a hypothesis must clear "
     "to be worth paper risk; the execution repo's EDGE_BELOW_BAR is exact",
     "MEASURED_NO_EV"),
    # ---- proven, and it lost its slot -------------------------------------
    ("OUTRANKED_BY_SIBLING", "RANKED_OUT",
     r"does not fund a proven one|EXPLORE is for measured-but-UNPROVEN",
     "a CALIBRATED read that did not win an EXPLOIT place; the paper-risk "
     "budget does not fund it as a consolation, and there is no information "
     "left in it to buy",
     "CALIBRATED_OUTRANKED"),
    # ---- the paper-risk budget was already full ---------------------------
    ("BOOK_LIMIT", "CAPACITY", r"budget is a ceiling, not a guide",
     "the EXPLORE budget, not the candidate: the name was licensed and the "
     "ceiling bound first",
     "EXPLORE_BUDGET_FULL"),
    # ---- the risk penalty could not be computed ---------------------------
    (UNCLASSIFIED, "DATA_MISSING",
     r"no usable annualised volatility|Missing is missing, never average",
     "the closed 31 have no class for a missing INPUT on an otherwise "
     "licensed candidate; DATA_MISSING is exact and the sentence names the "
     "field",
     "VOL_MISSING"),
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
     "groups on",
     "NO_LICENSED_SIGNAL"),
    # ---- the inputs were not there ----------------------------------------
    # "CANNOT DETERMINE" is the execution repo's own DATA_MISSING pattern; a
    # missing funnel, a void ranking gate and an unreadable candidate all
    # arrive wearing it, which is why this repo writes those words literally.
    (UNCLASSIFIED, "DATA_MISSING",
     r"CANNOT DETERMINE|no funnel run available|ranking gate VOID",
     "an input the ranking needed was absent or void; the closed 31 classes are "
     "about candidates and books and none of them names a missing input, so the "
     "typed answer is the terminal state DATA_MISSING",
     "INPUT_MISSING"),
    # ---- the day's PROBE ceiling refused a ROW, not a hypothesis -----------
    # chunk 23a. It must be matched BEFORE the generic capacity patterns: the
    # sentence is about the size of the FILE, not about the book or the
    # candidate, and reading it as a book limit would report a virtual row
    # nobody wrote as a position the book had no room for.
    (UNCLASSIFIED, "CAPACITY",
     r"PROBE ceiling refused this name a virtual row",
     "the execution repo's closed 31 are about candidates competing for "
     "CAPITAL, and this refusal spent none: the day's PROBE ceiling "
     "(config.PROBE_MAX_NAMES_PER_DAY) refused the name a virtual row after "
     "the higher-ranked unmeasured names took the day's quota. The terminal "
     "state CAPACITY is exact — a ceiling was reached — and nothing about the "
     "hypothesis was decided",
     "PROBE_CEILING"),
    # ---- the size buys no unit / the book has no room ----------------------
    ("CAPITAL_ROUNDS_TO_ZERO", "CAPACITY",
     r"below one share|rounds to zero|buys no share",
     "the execution repo's CAPITAL_ROUNDS_TO_ZERO, in this repo's words",
     "CAPACITY"),
    ("BOOK_LIMIT", "CAPACITY", r"tilt budget|IC_MAX_TILT_NAMES|no room in the book",
     "the book, not the candidate: IC_MAX_TILT_NAMES or the total tilt budget",
     "CAPACITY"),
    # ---- the tape could not carry it --------------------------------------
    (UNCLASSIFIED, "LIQUIDITY",
     r"untradeable at \$|dollar volume|days to exit|participation",
     "the closed 31 carry no liquidity class — an options book refuses on the "
     "chain (CHAIN_UNUSABLE), not on median dollar volume — so the terminal "
     "state LIQUIDITY carries the meaning",
     "LIQUIDITY"),
    # ---- the ranker preferred a sibling -----------------------------------
    ("OUTRANKED_BY_SIBLING", "RANKED_OUT",
     r"ranked below|out-ranked|outranked",
     "the ranker preferred another name inside the same budget",
     "RANKED_OUT"),
    # ---- the candidate's own merit ----------------------------------------
    ("EDGE_BELOW_BAR", "NEGATIVE_EV",
     r"verdict .* is not BUY or WATCH|ranking score .* is not positive|"
     r"scores at or below zero",
     "a signal spoke and the candidate's own merit did not clear the bar",
     "NO_ACTION_VERDICT"),
    ("MDE", "CONFIDENCE", r"minimum detectable|not distinguishable from noise",
     "the move is under the minimum detectable effect",
     "MDE"),
    # ---- the archetype refused to fill a book -----------------------------
    ("NO_STRUCTURE_CLEARED", "STRUCTURE",
     r"cannot fill a book|the archetype needs at least",
     "the archetype could not be filled, which is a structure refusal",
     "STRUCTURE"),
    # ---- this policy may not express this claim ---------------------------
    ("CLAIM_MISMATCH", "MANDATE", r"not in the mandate|outside the declared",
     "the policy may not express this claim",
     "MANDATE"),
)

_COMPILED = tuple((cls, term, re.compile(pat, re.IGNORECASE), basis, local)
                  for cls, term, pat, basis, local in _LOCAL_PATTERNS)


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
                "local_refusal_class": "INPUT_MISSING",
                "refusal_reason": "CANNOT DETERMINE: the refusal carried no sentence",
                "refusal_class_basis": (
                    "the row carried no refusal sentence at all, so there was "
                    "nothing to classify")}
    for cls, term, rx, basis, local in _COMPILED:
        if rx.search(text):
            return {"refusal_class": cls, "terminal_state": term,
                    "local_refusal_class": local,
                    "refusal_reason": text, "refusal_class_basis": basis}
    return {"refusal_class": UNCLASSIFIED, "terminal_state": OTHER_TYPED,
            "local_refusal_class": UNTYPED,
            "refusal_reason": text,
            "refusal_class_basis": (
                "NO PATTERN MATCHED: a gate wrote a sentence `_LOCAL_PATTERNS` "
                "has never seen. This is the UNCLASSIFIED that owes work — add "
                "the pattern, or name why the closed 31 cannot hold it")}


def probe_eligible(classified: dict, verdict: Any) -> tuple[bool, str]:
    """(may this refused name be PROBED, why/why not) — chunk 23a-ii.

    Roadmap §16.5 item 39: *a refusal to fund is not a refusal to learn.* Two
    of this repo's refusals are an ABSENCE of measurement — "no licensed signal
    speaks to this name" and "the verdict is HOLD/NO_ACTION, so no tilt is
    licensed" — and refusing them out of the ledger is how the absence becomes
    permanent. Every other refusal is a measurement, a view, a ceiling or a
    missing input, and each of those is a reason to stop.

    TWO keys and not one. The LOCAL class says what the refusal means
    (`config.PROBE_REFUSAL_CLASSES`), and the VERDICT says whether the engine
    has no view or a view AGAINST: `_refusal_sentence` writes one sentence for
    every non-BUY/WATCH verdict, so HOLD and SELL arrive wearing the same words
    and only the verdict separates them. A SELL is a position the engine
    declined to take in the other direction, not a hypothesis nobody has
    measured.
    """
    local = str(classified.get("local_refusal_class") or UNTYPED)
    eligible = tuple(config.PROBE_REFUSAL_CLASSES)
    if local not in eligible:
        return False, (
            f"this refusal means {local}, which is not one of "
            f"{list(eligible)} (config.PROBE_REFUSAL_CLASSES): it is a "
            f"measurement, a view, a ceiling or a missing input, and each of "
            f"those is a reason to STOP rather than a reason to probe")
    v = str(verdict or "").strip().upper()
    allowed = tuple(str(x).upper() for x in config.PROBE_REFUSAL_VERDICTS)
    if v not in allowed:
        return False, (
            f"the refusal means {local}, but the verdict is {v}, which is not "
            f"one of {list(allowed)} (config.PROBE_REFUSAL_VERDICTS). A "
            f"{v} is a view AGAINST this name, not an absence of one, and "
            f"PROBE is for the absence")
    return True, (
        f"this refusal means {local} (config.PROBE_REFUSAL_CLASSES) on a "
        f"verdict of {v or 'NONE'}: the engine has NO view of this name, which "
        f"is an absence of measurement and not evidence about the mechanism. "
        f"§16.5 item 39 — a refusal to fund is not a refusal to learn")


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


def largest_admissible_book(capital: float | None = None) -> dict:
    """CLAUDE.md session protocol 4, computed rather than remembered.

    `n names x notional% x stop%` and `sum|notional| / equity` for the biggest
    book this module can ever emit: `IC_MAX_TILT_NAMES` at
    `IC_SINGLE_NAME_TILT_CAP`, capped by `IC_TOTAL_TILT_BUDGET`. It goes on the
    file, not in a comment, because the number that mattered on 28 Aug was the
    one nobody printed.

    `capital` is the contract's ONE capital base (review 2026-09-26 R4: the
    file said `capital_usd: 40000` and priced this block on $1,000,000). With
    no capital named it falls back to the largest configured level, as before.
    """
    capital = (float(capital) if capital is not None
               else max(float(c) for c in config.IC_CAPITAL_LEVELS))
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
# THE MANDATE — one capital base, one per-name cap, one worst case
# (review 2026-09-26 R4). Surfaces and reconciles; changes no limit.
# ===========================================================================


def pc_paper_equity() -> dict | None:
    """The PC-PAPER account's last broker-truth equity, from its own NAV rows.

    `pc_book/<YYYY-MM-DD>/nav.jsonl`, newest folder, last row with an
    `equity`. Read from the rows' own stamps, never a file time. None when no
    NAV row exists (CI, a fresh checkout). An indirection so a test replaces it.
    """
    root = Path(config.OPTIMUS_LEDGER_DIR) / "pc_book"
    if not root.is_dir():
        return None
    for d in sorted((p for p in root.iterdir() if p.is_dir()
                     and len(p.name) == 10 and p.name[4] == "-"), reverse=True):
        f = d / "nav.jsonl"
        if not f.is_file():
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for ln in reversed(lines):
            try:
                row = json.loads(ln)
            except ValueError:
                continue
            eq = row.get("equity")
            if isinstance(eq, (int, float)) and eq > 0:
                return {"equity_usd": float(eq), "as_of": row.get("t") or row.get("utc")
                        or d.name, "source": str(f)}
    return None


def per_name_caps() -> dict[str, float]:
    """Every per-name cap that can bind a name on the PC-PAPER account, by source."""
    caps = {
        "config.IC_SINGLE_NAME_TILT_CAP (committee tilt)": float(config.IC_SINGLE_NAME_TILT_CAP),
        "config.PROBE_MAX_WEIGHT (u_plan PROBE)": float(config.PROBE_MAX_WEIGHT),
        "config.ER_EXPLOIT_MAX_WEIGHT (u_plan EXPLOIT)": float(config.ER_EXPLOIT_MAX_WEIGHT),
    }
    try:
        from backend.services import pc_broker as _PB               # noqa: PLC0415
        caps["pc_broker.MAX_NAME_FRAC (broker hard limit)"] = float(_PB.MAX_NAME_FRAC)
    except Exception:                                              # noqa: BLE001
        pass
    return caps


def gross_caps() -> dict[str, float]:
    """Every gross cap that can bind the PC-PAPER account, by source."""
    probe = float(config.PROBE_GROSS_CAP)
    caps = {
        "config.IC_TOTAL_TILT_BUDGET (committee tilts)": float(config.IC_TOTAL_TILT_BUDGET),
        "config.PROBE_GROSS_CAP (u_plan PROBE)": probe,
        "1 - PROBE_GROSS_CAP (u_plan EXPLOIT room)": 1.0 - probe,
    }
    try:
        from backend.services import pc_broker as _PB               # noqa: PLC0415
        caps["pc_broker.MAX_INVESTED_FRAC (broker hard limit)"] = float(_PB.MAX_INVESTED_FRAC)
    except Exception:                                              # noqa: BLE001
        pass
    return caps


def _exploit_book_size() -> int:
    try:
        from scripts import sim_run as _S                           # noqa: PLC0415
        return int(_S.BOOK_SIZE)
    except Exception:                                              # noqa: BLE001
        return int(config.IC_MAX_TILT_NAMES)


def account_mandate(capital: float | None, *, equity: Any = "derive") -> dict:
    """ONE capital base, ONE per-name cap, and the worst case in dollars.

    Session protocol item 4 on every receipt: `n x notional% x stop%` and
    `sum|notional| / equity` for the LARGEST book any path can emit on the
    account (as configured), beside the book the TIGHTEST caps would allow.

    It REFUSES -- `status: REFUSED`, a named reason per disagreement -- when
    the capital bases or the caps disagree, instead of picking one silently.
    That is today's state (the contract sizes on the IPS's $40,000, the account
    holds ~$1,000,000; per-name caps are 2% / 3% / 10% / 12%), and it stays
    red until Murat confirms ONE mandate. No limit is changed here.
    """
    if equity == "derive":
        try:
            equity = pc_paper_equity()
        except Exception:                                          # noqa: BLE001
            equity = None
    base = float(capital) if capital is not None else max(
        float(c) for c in config.IC_CAPITAL_LEVELS)
    bases = {"contract capital (the rows are sized on it)": base,
             "max(config.IC_CAPITAL_LEVELS)": max(float(c) for c in config.IC_CAPITAL_LEVELS)}
    if equity:
        bases[f"PC-PAPER broker equity ({equity.get('as_of')})"] = float(equity["equity_usd"])
    pn = per_name_caps()
    gc = gross_caps()
    tight_name_src, tight_name = min(pn.items(), key=lambda kv: kv[1])
    tight_gross_src, tight_gross = min(gc.items(), key=lambda kv: kv[1])

    # the largest book any path can emit, AS CONFIGURED: EXPLOIT's names at its
    # own cap (never above the broker's) inside 1 - PROBE gross, plus PROBE's
    # full cap, all under the broker's invested ceiling.
    probe_w = float(config.PROBE_MAX_WEIGHT)
    probe_gross = float(config.PROBE_GROSS_CAP)
    n_probe = int(config.PROBE_MAX_NAMES)
    ex_w = min(float(config.ER_EXPLOIT_MAX_WEIGHT), pn.get(
        "pc_broker.MAX_NAME_FRAC (broker hard limit)", 1.0))
    n_ex = _exploit_book_size()
    ex_gross = min(n_ex * ex_w, 1.0 - probe_gross)
    ceiling = gc.get("pc_broker.MAX_INVESTED_FRAC (broker hard limit)", 1.0)
    gross = min(ex_gross + probe_gross, ceiling)
    k = float(config.PROBE_WORST_CASE_SIGMA)
    sig = float(config.PROBE_REF_DAILY_SIGMA)
    stop_pct = k * sig
    n_all = n_ex + n_probe
    loosest_w = max(ex_w, probe_w)
    configured = {
        "n_names": n_all, "per_name_pct_max": loosest_w,
        "gross_over_equity": gross, "stop_declared": False,
        "stop_pct_used": stop_pct,
        "stop_basis": (f"no stop is declared; the k-sigma session "
                       f"({k:g} x {sig:.2%}/day) stands in for stop%"),
        "worst_case_k_sigma_usd": -gross * stop_pct * base,
        "worst_case_no_stop_usd": -gross * base,
        "line": (f"as configured: {n_ex} EXPLOIT x {ex_w:.0%} (gross <= {1 - probe_gross:.0%}) "
                 f"+ {n_probe} PROBE x {probe_w:.0%} (<= {probe_gross:.0%}) = "
                 f"sum|notional|/equity {gross:.2f}; x stop {stop_pct:.2%} = "
                 f"-${gross * stop_pct * base:,.0f}; no stop, so the ceiling is "
                 f"-${gross * base:,.0f} on ${base:,.0f}"),
    }
    n_tight = int(tight_gross / tight_name) if tight_name > 0 else 0
    tight = {
        "n_names": n_tight, "per_name_pct": tight_name, "gross_over_equity": tight_gross,
        "worst_case_k_sigma_usd": -tight_gross * stop_pct * base,
        "worst_case_no_stop_usd": -tight_gross * base,
        "line": (f"if the tightest caps bound: {n_tight} x {tight_name:.0%} = "
                 f"{tight_gross:.2f} gross; x stop {stop_pct:.2%} = "
                 f"-${tight_gross * stop_pct * base:,.0f}; ceiling "
                 f"-${tight_gross * base:,.0f} on ${base:,.0f}"),
    }
    refusals: list[str] = []
    distinct_bases = sorted({round(v, 0) for v in bases.values()})
    if len(distinct_bases) > 1 and max(distinct_bases) > 1.05 * min(distinct_bases):
        refusals.append("CAPITAL_BASES_DISAGREE: " + "; ".join(
            f"{k_} ${v:,.0f}" for k_, v in bases.items()))
    if len(set(pn.values())) > 1:
        refusals.append("PER_NAME_CAPS_DISAGREE: " + "; ".join(
            f"{k_} {v:.0%}" for k_, v in sorted(pn.items(), key=lambda kv: kv[1])))
    if gross > tight_gross + 1e-12:
        refusals.append(f"GROSS_CAPS_DISAGREE: the largest book any path can emit is "
                        f"{gross:.2f}x equity, the tightest gross cap is "
                        f"{tight_gross:.2f} ({tight_gross_src})")
    status = "REFUSED" if refusals else "OK"
    big = max(bases.values())
    configured["on_largest_base_seen"] = {
        "equity_usd": big, "worst_case_k_sigma_usd": -gross * stop_pct * big,
        "worst_case_no_stop_usd": -gross * big}
    line = (f"MANDATE {status}: capital ${base:,.0f}; per-name cap {tight_name:.0%} "
            f"(tightest: {tight_name_src}); {configured['line']}"
            + (f" [on the largest base seen, ${big:,.0f}: -${gross * stop_pct * big:,.0f} "
               f"k-sigma, ceiling -${gross * big:,.0f}]" if big > base * 1.05 else "")
            + (f" -- {len(refusals)} disagreement(s); Murat must confirm ONE mandate"
               if refusals else ""))
    return {
        "status": status,
        "capital_usd": base,
        "capital_basis": "the contract's own capital -- every dollar on this file is sized on it",
        "capital_bases_seen": bases,
        "per_name_cap": tight_name, "per_name_cap_source": tight_name_src,
        "per_name_caps_seen": pn,
        "gross_cap": tight_gross, "gross_cap_source": tight_gross_src,
        "gross_caps_seen": gc,
        "largest_admissible_book_as_configured": configured,
        "largest_admissible_book_under_tightest_caps": tight,
        "refusals": refusals,
        "line": line,
        "note": ("surfaces and reconciles the limits; changes none of them. A REFUSED "
                 "mandate is a finding printed on every contract until one capital "
                 "base and one cap are confirmed (docs/RUNBOOK_2026-09-26_SYSTEMS_FIXES.md)."),
    }


def candidate_set(state: dict, book: dict | None, *,
                  funnel_path: Path | None = None) -> dict:
    """The size AND age of the candidate set at each hop (review 2026-09-26 R5).

    `roi_ranking.n_considered` is the count AFTER the committee's eligibility
    gate (BUY/WATCH verdict, licensed evidence, ranking score > 0), not the
    candidate set. Printed alone it read as "the ranker saw 2 names" for seven
    days beside a 25-name funnel. Every hop is on the receipt now.
    """
    from collections import Counter

    src = Path(funnel_path or config.IC_FUNNEL_PATH)
    gen = state.get("funnel_generated_at")
    age = None
    try:
        from backend.services import investment_committee as _IC  # noqa: PLC0415
        age = _IC._funnel_age_days(gen)
    except Exception:                                              # noqa: BLE001
        age = None
    recs = list(state.get("recs") or [])
    by_verdict = Counter(str(getattr(r, "recommendation", "?")) for r in recs)
    verdicts = set(getattr(config, "IC_TILT_VERDICT_SCALE", {}) or {})
    excluded: Counter = Counter()
    for r in recs:
        v = str(getattr(r, "recommendation", ""))
        if getattr(r, "evidence_grade", "NO_EVIDENCE") == "NO_EVIDENCE":
            excluded["no licensed evidence (NO_EVIDENCE)"] += 1
        elif not getattr(r, "ranking_score", 0.0) > 0:
            excluded["ranking score <= 0"] += 1
        elif v not in verdicts:
            excluded[f"verdict {v} not in {sorted(verdicts)}"] += 1
    n_cands = len(state.get("candidates") or {})
    n_cons = ((book or {}).get("roi_ranking") or {}).get("n_considered")
    age_s = f"{age:.1f} d old" if isinstance(age, (int, float)) else "age UNKNOWN"
    line = (f"candidates {n_cands} ({src.name}, generated {gen or 'UNKNOWN'}, {age_s}) "
            f"-> {len(recs)} scored {dict(by_verdict)} -> "
            f"{n_cons if n_cons is not None else '?'} eligible for the ROI ranking "
            f"(= n_considered); excluded: "
            + (", ".join(f"{n} {why}" for why, n in excluded.most_common()) or "none"))
    return {
        "candidates_source": str(src),
        "n_candidates": n_cands,
        "candidates_generated_at": gen,
        "candidates_age_days": age,
        "n_scored": len(recs),
        "scored_by_verdict": dict(by_verdict),
        "eligibility_gate": ("recommendation in config.IC_TILT_VERDICT_SCALE, "
                             "evidence_grade != NO_EVIDENCE, ranking_score > 0 "
                             "(investment_committee.compose_book step 1)"),
        "excluded_by_gate": dict(excluded),
        "n_considered": n_cons,
        "line": line,
    }


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
                asof: str, revision_of: str | None = None,
                horizon_sessions: int | None = None) -> str:
    """The row's identity. `revision_of` is what makes a same-day revision a
    DIFFERENT decision rather than a rewrite of the first one: without it, a
    child built from the same policy, ticker and date would collide with its
    own parent, and the ledger would read the supersession as a duplicate.

    `horizon_sessions` does the same job for a PROBE name, which writes one row
    per declared horizon on one day: four rows about one name that shared an id
    would be one row in the ledger, and three of the four grades would be lost
    to the idempotence rule that exists to stop double-counting. Absent, the
    blob is byte-identical to the one every stored row was written against."""
    blob = f"{policy_id}|{policy_version}|{ticker}|{asof}"
    if revision_of:
        blob = f"{blob}|revision_of:{revision_of}"
    if horizon_sessions is not None:
        blob = f"{blob}|h:{int(horizon_sessions)}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def sessions_expiry(asof: date, sessions: int) -> tuple[str, str]:
    """(expiry_utc, basis) for a horizon counted in TRADING SESSIONS.

    Uses the same session walker the counterfactual resolver already uses
    (`counterfactual_prices.sessions_after`), which returns the calendar it
    actually used — XNYS when `exchange_calendars` is installed, weekday
    arithmetic when it is not. The basis NAMES which of the two produced the
    date, because a 126-session horizon resolved on weekday arithmetic lands
    about six sessions late over a year of holidays, and a reader grading the
    row a year from now has no other way to know which ruler it was written
    against.
    """
    try:
        from backend.services.counterfactual_prices import sessions_after
        day, calendar = sessions_after(asof, int(sessions))
    except Exception as exc:                                       # noqa: BLE001
        days = -(-int(sessions) * 7 // 5)
        when = datetime.combine(asof, datetime.min.time(), timezone.utc) + \
            timedelta(days=days)
        return (when.isoformat(timespec="seconds"),
                f"{int(sessions)} sessions = {days} calendar days at 5 "
                f"sessions a week; the session calendar was unavailable "
                f"({type(exc).__name__}: {exc}), so the 7/5 approximation was "
                f"used and is named here rather than left to be inferred")
    when = datetime.combine(day, datetime.min.time(), timezone.utc)
    return (when.isoformat(timespec="seconds"),
            f"{int(sessions)} trading sessions after {asof} on the "
            f"{calendar} calendar (counterfactual_prices.sessions_after) = "
            f"{day}")


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
    # The authority split (chunk 21). Absent entirely when the legacy heuristic
    # sizing is back on, so that flag is a true revert here too.
    authority = book.get("authority") or None
    authority_refused = dict((authority or {}).get("refused") or {})
    probe_blocks = dict((authority or {}).get("probe_blocks") or {})
    # Every name the SPLIT saw, and the EXPLORE candidate rows keyed by name.
    # The second is what puts `selection_probability` on a candidate the
    # budget did not fund: an off-policy estimator needs the propensity of the
    # actions NOT taken as much as of the one that was, and a row that only
    # carried it when it won would be a log of winners.
    authority_of = dict(book.get("authority_of") or {})
    explore_by_ticker = {str(d.get("ticker")): d
                         for d in (authority or {}).get("explore_rows") or []}
    # The four expiries are computed ONCE for the day: they depend on the as-of
    # date and the horizon and on nothing about the name, and walking the
    # exchange calendar per name per horizon would be 800 walks for 200 names.
    probe_expiry = {int(h): sessions_expiry(asof, int(h))
                    for h in ((authority or {}).get("probe_horizons_sessions")
                              or config.PROBE_HORIZONS_SESSIONS)}
    degradation = list(book.get("degradation_reasons") or [])
    by_ticker_degradation: dict[str, str] = {}
    for line in degradation:
        head = line.split(":", 1)[0].strip()
        if head and head.isupper() and head.replace(".", "").isalnum():
            by_ticker_degradation.setdefault(head, line)

    rows: list[dict] = []
    refused: list[dict] = []
    #: (base row, probe block) in RANK order — both the authority's own PROBE
    #: names and the refusals chunk 23a-ii promotes. One list, so the day's
    #: ceiling is applied once and by rank across both sources.
    probe_candidates: list[tuple[dict, dict]] = []
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
        if authority is not None:
            row.update(_authority_fields(ticker, pos, authority_refused,
                                         probe_blocks))
            row.update(_hypothesis_and_propensity(
                ticker, r, signal, authority_of=authority_of,
                explore_row=explore_by_ticker.get(ticker),
                information_set=generated_at, asof=asof_s,
                action_set_sha=(authority or {}).get("action_set_sha256")))
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
        if ticker in probe_blocks:
            # PROBE (chunk 23a): one VIRTUAL row per declared horizon. Not a
            # refusal and not a position — a graded observation that costs
            # nothing, so a hypothesis with no panel can build one forward.
            probe_candidates.append((row, probe_blocks[ticker]))
            continue
        # REFUSED: name the gate that stopped it, in this repo's own words.
        # The authority split's own sentence wins when it has one: it is the
        # LAST thing that refused the name and therefore the closest to the
        # truth, and it is the sentence that says whether the refusal was
        # "no measured read at all" or "the paper-risk budget was full".
        why = (authority_refused.get(ticker)
               or _refusal_sentence(r, by_ticker_degradation.get(ticker)))
        classified = classify_refusal(why)
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
            **classified,
        })
        # CHUNK 23a-ii. The refusal that is an ABSENCE of measurement is not a
        # reason to keep the name out of the ledger — it is the reason to put
        # it in (§16.5 item 39). The refusal SENTENCE survives on the row as
        # `probe_basis`: it still says exactly why no capital was allocated,
        # and nothing here reopens the gate that refused it.
        may_probe, probe_why = probe_eligible(
            classified, getattr(r, "recommendation", None))
        if may_probe:
            probe_candidates.append((row, _contract_probe_block(
                r, ticker, signal, classified=classified, probe_why=probe_why,
                candidates=candidates, horizon_months=horizon_months,
                information_set=generated_at, asof=asof_s,
                action_set_sha=(authority or {}).get("action_set_sha256"))))
            continue
        row["probe_refused"] = probe_why
        refused.append(row)

    # THE DAY'S PROBE CEILING, applied ONCE and by RANK over both sources —
    # the authority's own unmeasured names and the refusals 23a-ii promotes.
    # A name over the ceiling keeps the REFUSED row it would have had, with
    # the sentence that says it was probe-eligible and the file was full: the
    # cap refuses a ROW, and nothing about the hypothesis was decided.
    probe_cap = int(config.PROBE_MAX_NAMES_PER_DAY)
    probe_candidates.sort(key=lambda t: (t[0].get("rank") is None,
                                         t[0].get("rank") or 0))
    probe_rows: list[dict] = []
    for i, (base, block) in enumerate(probe_candidates, start=1):
        if i > probe_cap:
            cut = (f"the day's PROBE ceiling refused this name a virtual row: "
                   f"it ranked #{i} of {len(probe_candidates)} unmeasured "
                   f"candidates and config.PROBE_MAX_NAMES_PER_DAY is "
                   f"{probe_cap}. This refuses a ROW, by rank; nothing about "
                   f"the hypothesis was decided")
            base["probe_refused"] = cut
            base["probe_eligible_but_capped"] = True
            base.update({
                "direction": "REFUSED",
                "position_budget": {
                    "weight": 0.0, "dollars": 0.0, "shares": 0,
                    "price": None, "capital_usd": float(capital),
                    "basis": "refused — no budget was allocated"},
                "maximum_loss": worst_case_no_stop(
                    n_names=0, notional_pct=0.0, equity_usd=float(capital),
                    gross_over_equity=0.0,
                    why=("refused — nothing is at risk on a row that was "
                         "not taken")),
                **classify_refusal(cut),
            })
            refused.append(base)
            continue
        probe_rows.extend(_probe_rows_for(
            base, block, expiries=probe_expiry, capital=capital,
            policy_id=policy_id, policy_version=policy_version, asof=asof_s))

    refused.sort(key=lambda d: (d.get("rank") is None, d.get("rank") or 0))
    kept = refused[:MAX_REFUSED_ROWS]
    # PROBE rows are NOT trimmed here: they are the panel, and their own
    # ceiling was applied BY RANK just above (`config.PROBE_MAX_NAMES_PER_DAY`,
    # with the cut named on each row it cut). Trimming them at
    # MAX_REFUSED_ROWS would cap what the programme can ever measure with a
    # constant chosen to keep a file readable.
    return rows + kept + probe_rows


#: The fields an ROI-scored row carries, in the order a reader wants them.
#: `mu_source` / `mu_basis` / `downside_source` are chunk 22's (2026-09-21):
#: WHICH measurement produced this row's expected return and its downside, and
#: the receipt path it came off. A reader must never have to infer whether a
#: number came from the candidate's own score decile or from its signal
#: family's average — those are different claims.
_ROI_ROW_FIELDS: tuple[str, ...] = (
    "expected_return_net_pct", "downside_pct", "roi_score", "roi_rank",
    "kelly_fraction", "kelly_weight", "roi_basis", "roi_measured_on", "roi_t",
    "roi_n_blocks", "expected_return_basis", "downside_basis",
    "kelly_fraction_basis", "mu_source", "mu_basis", "downside_source",
    "roi_horizon_months", "calibration_verdict", "calibration_decile",
    "calibration_se_pct", "calibration_verdict_seen")


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


def _hypothesis_and_propensity(ticker: str, rec: Any, signal: str, *,
                               authority_of: dict, explore_row: dict | None,
                               information_set: str | None, asof: str,
                               action_set_sha: str | None) -> dict:
    """The chunk-23a fields every row the AUTHORITY touched carries.

    `hypothesis_id` on all of them, because a row nobody can join to the panel
    is a row that can never become a measurement — and the join key has to be
    on EXPLOIT and REFUSED rows too, or a hypothesis's history would have a
    hole every time one of its names was funded or declined.

    `selection_probability` / `action_set_sha256` / `context_features` on every
    EXPLORE CANDIDATE, funded or not. A doubly-robust off-policy estimator
    divides by the propensity of the action that was taken and needs the choice
    set it was taken from; a log that carried those only for the winners is a
    log that cannot be replayed under any other policy (chunk 24).

    A name the split never saw gets nothing: it was refused at a hard gate
    before any authority existed, and inventing a hypothesis id for it would
    put a claim on a row that was never evaluated as one.
    """
    if str(ticker) not in authority_of:
        return {}
    sig = str(signal or "")
    if not sig or sig.startswith("CANNOT DETERMINE"):
        sig = DA.NO_LEAD_SIGNAL
    out = dict(DA.hypothesis_fields(rec, sig, information_set=information_set,
                                    asof=asof))
    if explore_row is not None:
        out["selection_probability"] = explore_row.get("selection_probability")
        out["selection_probability_basis"] = explore_row.get(
            "selection_probability_basis")
        out["context_features"] = explore_row.get("context_features")
        out["action_set_sha256"] = (explore_row.get("action_set_sha256")
                                    or action_set_sha)
    return out


def _contract_probe_block(rec: Any, ticker: str, signal: str, *,
                          classified: dict, probe_why: str, candidates: dict,
                          horizon_months: float, information_set: str | None,
                          asof: str, action_set_sha: str | None) -> dict:
    """The PROBE block for a name the AUTHORITY never saw (chunk 23a-ii).

    Same shape `decision_authority` builds for its own unmeasured names, so
    `_probe_rows_for` cannot tell the two apart — except by `probe_source`,
    which is printed, because the two are genuinely different statements. The
    authority's PROBE means "this candidate cleared every hard gate and then
    had no measured read"; this one means "a hard gate declined to fund it for
    a reason that is an absence of measurement, not evidence".

    The original refusal sentence is kept verbatim as `probe_basis`: it is
    still exactly why no capital was allocated, and nothing here reopens the
    gate that wrote it.
    """
    sig = str(signal or "")
    if not sig or sig.startswith("CANNOT DETERMINE"):
        sig = DA.NO_LEAD_SIGNAL
    hyp = DA.hypothesis_fields(rec, sig, information_set=information_set,
                               asof=asof)
    why = str(classified.get("refusal_reason") or "")
    return {
        "authority_basis": (
            f"PROBE (chunk 23a-ii): no capital, and not silence either. The "
            f"gate's own sentence stands — {why} — and {probe_why}"),
        "authority_weight": 0.0,
        "probe_source": "contract_refusal_class",
        "probe_basis": why,
        "action_set_sha256": action_set_sha,
        "probe": {
            **hyp,
            "signal": sig,
            "virtual": True,
            "virtual_notional_usd": float(config.PROBE_VIRTUAL_NOTIONAL_USD),
            "virtual_basis": (
                f"a PROBE row holds ZERO weight and ZERO dollars; "
                f"${float(config.PROBE_VIRTUAL_NOTIONAL_USD):,.0f} "
                f"(config.PROBE_VIRTUAL_NOTIONAL_USD) is the notional the "
                f"graded return is QUOTED at, and it buys nothing"),
            "horizons_sessions": [int(h) for h in
                                  config.PROBE_HORIZONS_SESSIONS],
            "selection_probability": 1.0,
            "selection_probability_basis": (
                "every unmeasured name probes; no draw. Nothing was allocated, "
                "so there was no scarce budget to be selected out of and the "
                "propensity is exactly 1.0"),
            "context_features": DA._context_features(
                candidates, ticker, rec, sig, horizon_months=horizon_months,
                decile=None),
            "refusal_class": classified.get("refusal_class"),
            "local_refusal_class": classified.get("local_refusal_class"),
            "terminal_state": classified.get("terminal_state"),
            "probe_eligibility_basis": probe_why,
        },
    }


def _probe_rows_for(base: dict, block: dict, *, expiries: dict,
                    capital: float, policy_id: str, policy_version: str,
                    asof: str) -> list[dict]:
    """One VIRTUAL row per declared horizon for one PROBE name.

    Four rows and not one, because a mechanism that shows up in a week and is
    gone by a quarter is a different finding from one that needs a quarter to
    appear, and a single horizon makes the two indistinguishable for ever. Each
    row is separately gradeable — its own `decision_id`, its own `expiry_utc` —
    and each carries the `hypothesis_id` the panel joins on.

    Nothing here holds capital: the weight, the dollars and the shares are zero
    by construction and `virtual_notional_usd` is the scale the graded return
    is QUOTED at, never a position. The day's capital resolution does not see
    these rows and cannot: it sums position budgets, and these are zero.
    """
    probe = dict(block.get("probe") or {})
    hid = str(probe.get("hypothesis_id") or "")
    if not hid:
        # A PROBE row without a hypothesis id cannot be written: the panel
        # would have nothing to accumulate it under, so the row could never
        # become a measurement and would be a cost with no return.
        logger.error("PROBE row for %s carries no hypothesis_id; no virtual "
                     "row was written", base.get("ticker"))
        return []
    ticker = str(base.get("ticker"))
    out: list[dict] = []
    for h in sorted(expiries):
        expiry, expiry_basis = expiries[h]
        row = dict(base)
        row["decision_id"] = decision_id(
            policy_id=policy_id, policy_version=policy_version,
            ticker=ticker, asof=asof, horizon_sessions=int(h))
        row.update({
            "direction": "PROBE",
            "authority": DA.PROBE,
            "authority_basis": block.get("authority_basis"),
            "probe_source": block.get("probe_source") or "authority",
            "probe_basis": (block.get("probe_basis")
                            or block.get("authority_basis")),
            "hypothesis_id": hid,
            "hypothesis_id_basis": probe.get("hypothesis_id_basis"),
            "hypothesis_signal": probe.get("hypothesis_signal"),
            "hypothesis_mechanism": probe.get("hypothesis_mechanism"),
            "hypothesis_information_set": probe.get(
                "hypothesis_information_set"),
            "horizon_sessions": int(h),
            "horizon": {"sessions": int(h),
                        "basis": "config.PROBE_HORIZONS_SESSIONS"},
            "expiry_utc": expiry,
            "expiry_basis": expiry_basis,
            "virtual": True,
            "selection_probability": probe.get("selection_probability"),
            "selection_probability_basis": probe.get(
                "selection_probability_basis"),
            "action_set_sha256": block.get("action_set_sha256"),
            "context_features": probe.get("context_features"),
            "position_budget": {
                "weight": 0.0, "dollars": 0.0, "shares": 0, "price": None,
                "capital_usd": float(capital),
                "virtual": True,
                "virtual_notional_usd": float(
                    config.PROBE_VIRTUAL_NOTIONAL_USD),
                "basis": probe.get("virtual_basis") or (
                    "PROBE — a virtual row: zero weight, zero dollars, zero "
                    "shares, graded at its own expiry"),
            },
            "maximum_loss": worst_case_no_stop(
                n_names=0, notional_pct=0.0, equity_usd=float(capital),
                gross_over_equity=0.0,
                why=("PROBE — nothing is at risk: the row holds no weight and "
                     "no dollars, and its whole cost is the grading call that "
                     "prices it at its expiry")),
        })
        out.append(row)
    return out


def _authority_fields(ticker: str, pos: dict | None, refused: dict,
                      probe_blocks: dict | None = None) -> dict:
    """The authority block for one name: EXPLOIT, EXPLORE, PROBE or REFUSED.

    Four populations and no fifth (chunk 21, amended by 23a). A name the split
    sent to PROBE carries its hypothesis, its virtual notional and the sentence
    that says which of the two unmeasured branches sent it there — and, like
    every other row here, a weight of zero it can never be read as holding.
    A name the split FUNDED carries
    the authority it was funded under, the sentence that licensed it, and — for
    an EXPLORE name — the whole posterior, the Thompson draw, the seed and the
    score, so tomorrow's reader can reproduce the allocation without rerunning
    it. A name the split refused carries the refusal sentence. A name that
    never reached it says exactly that.

    `authority: REFUSED` and `direction: REFUSED` are not the same statement
    and both are printed: the first says no authority licensed capital, the
    second says no budget was allocated. They agree today and must be able to
    disagree tomorrow (a capacity refusal after an EXPLORE allocation is
    exactly that case), which is why neither is derived from the other.
    """
    t = str(ticker)
    if pos is not None and pos.get("authority"):
        out = {"authority": pos.get("authority"),
               "authority_basis": pos.get("authority_basis")}
        if pos.get("explore"):
            out["explore"] = pos["explore"]
        if pos.get("sizing"):
            out["sizing"] = pos["sizing"]
        return out
    block = (probe_blocks or {}).get(t)
    if block:
        return {"authority": DA.PROBE,
                "authority_basis": block.get("authority_basis"),
                "probe": block.get("probe")}
    if t in refused:
        return {"authority": DA.REFUSED, "authority_basis": refused[t]}
    return {"authority": DA.REFUSED,
            "authority_basis": (
                "not considered — this name never reached the authority split, "
                "because the hard eligibility gates run first and the split "
                "only ever sees the candidates they admitted")}


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
        if not config.IC_LEGACY_HEURISTIC_SIZING:
            # An agency Option is a whole costed book under this repo's only
            # licence, `PRODUCT_EXPERIMENT` — which is the definition of
            # EXPLORE: it may be tested in paper and it may not claim anything.
            # Its SIZE is its own contract's (k, gross cap, cash floor), not a
            # slice of `EXPLORE_BUDGET_PCT`: the per-name paper-risk budget
            # sizes NAMES inside the committee's tilt sleeve, and applying it
            # to a whole book would silently re-size a strategy contract that
            # was frozen before the first decision.
            row["authority"] = DA.EXPLORE
            row["authority_basis"] = (
                f"EXPLORE by licence: an agency Option is a whole costed BOOK "
                f"under {LICENCE}, which permits internal simulation and PAPER "
                f"brokerage and licenses no claim. It is sized by its own "
                f"frozen strategy contract (k {data.get('k')}, gross cap "
                f"{data.get('gross_cap')}, cash floor "
                f"{data.get('cash_floor_pct')}), not out of "
                f"EXPLORE_BUDGET_PCT — that budget slices NAMES inside the "
                f"committee's tilt sleeve, and re-sizing a frozen contract "
                f"with it would break the one thing a PRODUCT_EXPERIMENT may "
                f"not do. It is excluded from the day's capital resolution for "
                f"the same reason the three personalities are: they are "
                f"ALTERNATIVES at one capital level, not additive holdings.")
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
                               if "REFUSED" not in d],
            asof=day,
            information_set=state.get("funnel_generated_at"))
    except Exception as exc:                                       # noqa: BLE001
        logger.exception("decision contract: compose_book failed")
        book = {"positions": [], "degradation_reasons":
                [f"CANNOT DETERMINE: compose_book raised {type(exc).__name__}: {exc}"]}
        notes.append(f"CANNOT DETERMINE: the book could not be composed "
                     f"({type(exc).__name__}: {exc})")

    rows = _ic_rows(state, book, asof=day, capital=capital)
    try:
        cset = candidate_set(state, book, funnel_path=funnel_path)
    except Exception as exc:                                       # noqa: BLE001
        cset = {"line": f"CANNOT DETERMINE the candidate set: {type(exc).__name__}: {exc}"}

    if agency_note:
        notes.append(agency_note)
    rows.extend(_agency_rows(options, asof=day))

    for row in rows:
        row["built_utc"] = _now()
        row["artifact_sha256"] = seal(row)

    if write:
        write_contracts(rows, asof=day, out_dir=out_dir, notes=notes,
                        capital=capital, book=book, candidates=cset)
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
                           if "REFUSED" not in d],
        asof=day,
        information_set=state.get("funnel_generated_at"))
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

    # "Held" is BUY or WATCH and nothing else. `!= "REFUSED"` was equivalent
    # until 2026-09-21; with PROBE in the enum it would read a virtual,
    # zero-weight row as a position and report a revision that moved no
    # capital as one that did.
    was_held = str(parent.get("direction")) in ("BUY", "WATCH")
    now_held = str(child.get("direction")) in ("BUY", "WATCH")
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
        ticker=ticker, asof=str(day), revision_of=str(parent_decision_id),
        horizon_sessions=child.get("horizon_sessions"))
    if len(fresh) > 1:
        # A re-run that lands on PROBE produces one row per declared horizon.
        # ONE of them supersedes the parent — the shortest, because it is the
        # one that resolves first and a supersession nobody can grade for six
        # months is a supersession nobody can check. The horizon is in the
        # child's id, so a later revision at another horizon cannot collide
        # with this one.
        child["revision_note"] = (
            f"the re-run produced {len(fresh)} rows for {ticker} (one per "
            f"horizon in config.PROBE_HORIZONS_SESSIONS); the shortest, "
            f"{child.get('horizon_sessions')} sessions, is the child written "
            f"here. The parent held capital and this row holds none — that IS "
            f"the change, and the other horizons are written by the next "
            f"ordinary daily contract, not by this revision.")
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
        cset_on_file = None
        if path.is_file():
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
                rows = list(blob.get("rows") or [])
                notes = list(blob.get("notes") or [])
                capital_on_file = blob.get("capital_usd") or capital
                cset_on_file = blob.get("candidate_set")
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
                                         book=book, candidates=cset_on_file))

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
            capital: float | None = None, book: dict | None = None,
            candidates: dict | None = None) -> dict:
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
    cset = candidates or {
        "candidates_source": None, "n_candidates": None,
        "candidates_generated_at": None,
        "line": ("CANNOT DETERMINE: this writer passed no candidate set, so the "
                 "size and age of what was ranked are unknown")}
    roi_block = _roi_payload_block(rows, book)
    if roi_block.get("roi_ranking") is not None:
        # n_considered is POST-gate; the pre-gate set travels beside it so the
        # number can never again be read as "the ranker saw 2 names".
        for k in ("candidates_source", "n_candidates", "candidates_generated_at"):
            roi_block["roi_ranking"][k] = cset.get(k)
    try:
        mandate = account_mandate(capital)
    except Exception as exc:                                       # noqa: BLE001
        mandate = {"status": "CANNOT DETERMINE",
                   "line": f"MANDATE CANNOT DETERMINE: {type(exc).__name__}: {exc}"}
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
        "mandate": mandate,
        "candidate_set": cset,
        "probe": probe_census_over_rows(rows),
        **roi_block,
        **_authority_payload_block(rows, book),
        "capital_resolution": capital_resolution(rows, capital=capital),
        "worst_case_largest_admissible_book": largest_admissible_book(capital),
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


def probe_census_over_rows(rows: list[dict]) -> dict:
    """What was PROBED, what stayed REFUSED, and the class breakdown of each.

    Chunk 23a-ii's `probe_honesty`, computed from the ROWS so the census and
    the file cannot disagree. The two halves are printed side by side on
    purpose: "31 names probed" means nothing without "8 stayed refused, and
    here is the class of each", because the whole claim of the chunk is that
    the split between them is the split between an ABSENCE of measurement and
    a measurement — and a reader has to be able to check it name by name.
    """
    probe = [r for r in rows if r.get("direction") == DA.PROBE]
    refused = [r for r in rows if r.get("direction") == "REFUSED"]
    by_source: dict[str, int] = {}
    probed_by_class: dict[str, int] = {}
    names: dict[str, str] = {}
    for r in probe:
        src = str(r.get("probe_source") or "authority")
        by_source[src] = by_source.get(src, 0) + 1
        names[str(r.get("ticker"))] = str(
            r.get("local_refusal_class")
            or (r.get("probe") or {}).get("local_refusal_class")
            or ("NO_MEASURED_READ" if src == "authority" else UNTYPED))
    for t, cls in names.items():
        probed_by_class[cls] = probed_by_class.get(cls, 0) + 1
    stayed: dict[str, int] = {}
    capped = 0
    for r in refused:
        cls = str(r.get("local_refusal_class") or UNTYPED)
        stayed[cls] = stayed.get(cls, 0) + 1
        if r.get("probe_eligible_but_capped"):
            capped += 1
    hypotheses = sorted({str(r.get("hypothesis_id")) for r in probe
                         if r.get("hypothesis_id")})
    return {
        "n_rows": len(probe),
        "n_names": len(names),
        "n_hypotheses": len(hypotheses),
        "hypotheses": hypotheses,
        "rows_by_source": by_source,
        "probed_by_local_refusal_class": probed_by_class,
        "stayed_refused_by_local_refusal_class": stayed,
        "probe_eligible_but_over_the_ceiling": capped,
        "eligible_classes": list(config.PROBE_REFUSAL_CLASSES),
        "eligible_verdicts": list(config.PROBE_REFUSAL_VERDICTS),
        "horizons_sessions": [int(h) for h in config.PROBE_HORIZONS_SESSIONS],
        "rows_without_a_hypothesis_id": sum(1 for r in probe
                                            if not r.get("hypothesis_id")),
        "honesty": (
            f"{len(names)} name(s) x {len(config.PROBE_HORIZONS_SESSIONS)} "
            f"horizon(s) = {len(probe)} virtual row(s) under "
            f"{len(hypotheses)} hypothesis id(s), holding ZERO capital. They "
            f"were probed because their refusal means one of "
            f"{list(config.PROBE_REFUSAL_CLASSES)} — an ABSENCE of "
            f"measurement — on a verdict in "
            f"{list(config.PROBE_REFUSAL_VERDICTS)}: {probed_by_class}. The "
            f"{len(refused)} name(s) that stayed REFUSED did so because their "
            f"refusal is a measurement, a view, a ceiling or a missing input: "
            f"{stayed}. Nothing here reopened a gate — every probed name is "
            f"still refused CAPITAL, and its gate's own sentence is on its "
            f"row as probe_basis (roadmap §16.5 item 39)."),
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


def capital_resolution(rows: list[dict], *, capital: float | None = None
                       ) -> dict:
    """Where EVERY dollar went today: benchmark / exploit / explore / cash.

    Murat's item 11, 2026-09-20: *"force a daily portfolio decision — every
    dollar resolves to benchmark, active exploit, active explore or cash. 'No
    active trade' is allowed; 'nothing happened' is not."*

    Derived from the ROWS, so the split and the file cannot disagree: the two
    active shares are the position budgets the authorities funded, cash is the
    declared floor (`config.IC_CASH_FLOOR_PCT`) and the benchmark core is the
    RESIDUAL — which is the honest direction, because the core is what the
    committee holds when nothing else is licensed, not a target of its own.

    Agency rows are excluded and say so on the block: the three personalities
    are ALTERNATIVE whole books at the same capital, so adding them would
    resolve the same dollar three times.
    """
    exploit = 0.0
    explore = 0.0
    n_exploit = 0
    n_explore = 0
    n_books = 0
    for r in rows:
        if r.get("instrument_kind") == "book":
            n_books += 1
            continue
        w = (r.get("position_budget") or {}).get("weight")
        try:
            w = float(w)
        except (TypeError, ValueError):
            continue
        if w <= 0:
            continue
        if r.get("authority") == DA.EXPLOIT:
            exploit += w
            n_exploit += 1
        elif r.get("authority") == DA.EXPLORE:
            explore += w
            n_explore += 1
    # chunk 23a. PROBE rows are COUNTED here and resolve no capital: their
    # weight is zero by construction, so they cannot enter the sums above even
    # by accident. The count sits beside the four buckets because a day that
    # wrote forty virtual rows and moved no dollar is a day that did something,
    # and a resolution that printed only the dollars would read as if it had
    # not.
    probe_rows = [r for r in rows if r.get("direction") == DA.PROBE]
    probe_names = sorted({str(r.get("ticker")) for r in probe_rows})
    probe_hypotheses = sorted({str(r.get("hypothesis_id")) for r in probe_rows
                               if r.get("hypothesis_id")})
    cash = float(config.IC_CASH_FLOOR_PCT)
    benchmark = 1.0 - exploit - explore - cash
    total = benchmark + exploit + explore + cash
    out = {
        "benchmark_pct": round(benchmark, 8),
        "active_exploit_pct": round(exploit, 8),
        "active_explore_pct": round(explore, 8),
        "cash_pct": round(cash, 8),
        "sums_to": round(total, 8),
        "capital_usd": (float(capital) if capital is not None else None),
        "n_exploit_names": n_exploit,
        "n_explore_names": n_explore,
        "probe_count": len(probe_rows),
        "n_probe_names": len(probe_names),
        "n_probe_hypotheses": len(probe_hypotheses),
        "probe_pct": 0.0,
        "probe_basis": (
            f"{len(probe_rows)} virtual PROBE row(s) across "
            f"{len(probe_names)} name(s) and {len(probe_hypotheses)} "
            f"hypothesis id(s) resolved 0.00% of capital, BY CONSTRUCTION: a "
            f"PROBE row carries zero weight and zero dollars and is graded at "
            f"its own expiry. It is counted here so a day that wrote virtual "
            f"rows and moved no dollar does not read as a day that did "
            f"nothing (roadmap §16.2)."),
        "agency_book_rows_excluded": n_books,
        "basis": (
            "benchmark = 1 - exploit - explore - cash; the two active shares "
            "are the position budgets the authorities funded, cash is "
            "config.IC_CASH_FLOOR_PCT, and the benchmark core is the residual. "
            "Agency Option rows are ALTERNATIVE whole books at this same "
            "capital and are excluded — counting them would resolve one dollar "
            "three times."),
        "nothing_happened_is_not_allowed": (
            f"every dollar resolved today: {benchmark:.2%} benchmark core, "
            f"{exploit:.2%} active EXPLOIT across {n_exploit} name(s), "
            f"{explore:.2%} active EXPLORE across {n_explore} name(s), "
            f"{cash:.2%} cash. 'No active trade' is an allowed outcome; "
            f"'nothing happened' is not, and this line is the proof it did "
            f"not happen."),
    }
    if abs(total - 1.0) > 1e-8 or benchmark < 0:
        out["refused"] = (
            f"CANNOT DETERMINE: the resolution does not add to one "
            f"({total:.8f}) or the benchmark residual is negative "
            f"({benchmark:.8f}) — the active budgets exceed the declared "
            f"capital, which is a defect in the sizing caps and not a book "
            f"anyone should hold")
    if capital is not None:
        out["dollars"] = {
            "benchmark_usd": round(benchmark * float(capital), 2),
            "active_exploit_usd": round(exploit * float(capital), 2),
            "active_explore_usd": round(explore * float(capital), 2),
            "cash_usd": round(cash * float(capital), 2),
        }
    return out


def _authority_payload_block(rows: list[dict], book: dict | None) -> dict:
    """The day's authority census, or nothing at all when the split is off.

    Counts each authority over the ROWS (not over the split's own candidate
    set) so the census and the file agree by construction, and prints the
    worst case the EXPLORE budget ADDS to the day's existing one — session
    protocol rule 4, which is about the number nobody printed.
    """
    split = (book or {}).get("authority")
    if not split:
        return {}
    counts = {a: 0 for a in DA.AUTHORITIES}
    buys_without_authority = []
    for r in rows:
        a = str(r.get("authority") or "")
        if a in counts:
            counts[a] += 1
        if (r.get("direction") in ("BUY", "WATCH")
                and a not in DA.ACTIVE_AUTHORITIES):
            buys_without_authority.append(r.get("ticker"))
    census = {k: v for k, v in split.items()
              if k not in ("explore_rows", "refused", "probe_blocks")}
    census["count_by_authority_over_rows"] = counts
    census["rows_with_a_budget_and_no_authority"] = buys_without_authority
    census["explore_rows"] = split.get("explore_rows") or []
    probe_rows = [r for r in rows if r.get("direction") == DA.PROBE]
    by_hypothesis: dict[str, int] = {}
    for r in probe_rows:
        hid = str(r.get("hypothesis_id") or "MISSING")
        by_hypothesis[hid] = by_hypothesis.get(hid, 0) + 1
    census["probe_rows_written"] = len(probe_rows)
    census["probe_rows_by_hypothesis"] = by_hypothesis
    census["probe_rows_without_a_hypothesis_id"] = sum(
        1 for r in probe_rows if not r.get("hypothesis_id"))
    census["probe_rows_exempt_from_the_refused_trim"] = (
        f"PROBE rows are not subject to MAX_REFUSED_ROWS ({MAX_REFUSED_ROWS}); "
        f"their own ceiling is config.PROBE_MAX_NAMES_PER_DAY "
        f"({int(config.PROBE_MAX_NAMES_PER_DAY)}), applied BY RANK once in "
        f"`_ic_rows` over BOTH sources — this module's unmeasured survivors "
        f"and the refusals chunk 23a-ii promotes. The names it cut carry "
        f"`probe_eligible_but_capped` on their REFUSED rows; the split's own "
        f"earlier cut was {split.get('n_probe_cut_by_cap', 0)} name(s)")
    return {
        "authority": census,
        "worst_case_explore_budget": split.get("worst_case_added_by_explore"),
    }


def write_contracts(rows: list[dict], *, asof: date, out_dir: Path | None = None,
                    notes: list[str] | None = None, capital: float | None = None,
                    book: dict | None = None, candidates: dict | None = None) -> Path:
    """Atomic write. A half-written receipt is worse than none: a reader cannot
    tell a truncated file from a day on which the engine found two names."""
    path = contracts_path(asof, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload(rows, asof=asof, notes=notes, capital=capital,
                              book=book, candidates=candidates),
                      ensure_ascii=False, indent=1)
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
            f"WATCH, {counts.get('REFUSED', 0)} REFUSED, "
            f"{counts.get('PROBE', 0)} PROBE (virtual rows at zero capital, "
            f"graded at their own expiry — never a recommendation).")
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
