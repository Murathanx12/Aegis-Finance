"""T2/H4 -- the decision log and the four-counterfactual regret grader.

    from backend.services import decision_log as dl

    row  = dl.open_row(source="human:murat", symbol="NVDA", direction="up", ...)
    gr   = dl.resolve(row, as_of="2026-08-03")     # at the row's OWN horizon
    dl.record_grade(gr)
    dl.lessons(as_of="2026-08-04")                 # only what was learnable then

WHAT A ROW IS FOR
=================
Invariant 18: **two authority levels, one ledger.** Mode A (Murat decides) and
Mode B (the machine decides) write the SAME typed row and are graded by the SAME
four counterfactuals. A row that only the human writes is a diary; a grader that
only the machine faces is a backtest. The pair is the product.

THE FOUR COUNTERFACTUALS, AND WHY THESE FOUR
============================================
1. **held_to_horizon**     -- the row's OWN declared horizon in sessions. Not a
                              fixed 5 days: a 63-session thesis graded at 5 days
                              is graded against a clock it never agreed to, and
                              that single default is what made "sold early" and
                              "wrong" indistinguishable for every book.
2. **held_to_next_review**  -- the next SCHEDULED review. Separates *the thesis
                              was wrong* from *the review cadence was wrong*,
                              which are different repairs.
3. **engine_pick_same_day** -- what the machine would have bought on the same day.
                              This is the only leg that compares the two AUTHORITY
                              LEVELS on identical information, and it is the leg
                              that eventually answers "should Mode B be trusted".
4. **spy**                  -- the benchmark. The `market` paper account
                              (PA3I7VTCC0BM, `PASSIVE_BETA_v1`) holds SPY and its
                              keys are NOT in this environment, so this leg is
                              computed from PRICE DATA and **names the source that
                              answered**. It is never 0.0-by-default: a missing
                              benchmark reads `NOT_AVAILABLE`, because a silent
                              zero would make the benchmark free exactly when the
                              data was worst.

SIGN CONVENTION, STATED ONCE
============================
`regret_vs_X = X - actual`. **Positive regret means the counterfactual would have
been better.** A short thesis (`direction="down"`) has its returns negated before
anything else happens, so a stock that fell 4% on a down thesis is +4% actual.
Every graded row carries `sign` and `sign_basis` so this paragraph is checkable
from the data rather than from this docstring.

PENDING, AND THE `as_of` GATE
=============================
A row is written PENDING at decision time and carries `resolves_on` and
`learnable_at_utc`. `lessons(as_of=...)` returns ONLY rows whose lesson had
already been learnable at `as_of`; asking for one that had not raises
`LessonNotYetLearnable`. Without that gate a reflection written today leaks into
a replay of last month, and the replay measures the reflection instead of the
decision. The gate is the cheap version of "no training on future information".

THE HONESTY GATE
================
Under `config.DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM` (20) fully graded rows,
`scoreboard()` reports PROCESS metrics only and stamps
`claim: "a receipt, not a result"`. It does not report a mean P&L, an edge or a
hit rate, because 6 rows of anything support none of those.

WHAT THIS MODULE DOES NOT DO
============================
It places nothing, sizes nothing, seals nothing and trains nothing. It turns a
decision into a graded row, and the LLM in it writes 2-4 sentences of English on
a FREE backend after the arithmetic is already finished.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.config import (COUNTERFACTUAL_BENCHMARK_ACCOUNT,
                            COUNTERFACTUAL_BENCHMARK_CONTRACT,
                            COUNTERFACTUAL_BENCHMARK_SYMBOL,
                            DECISION_GRADE_LOG_PATH, DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM,
                            DECISION_LOG_PATH, DECISION_REFLECTION_BACKENDS,
                            DECISION_REFLECTION_MAX_SENTENCES,
                            DECISION_REFLECTION_MAX_TOKENS,
                            DECISION_REFLECTION_MIN_SENTENCES,
                            HUMAN_LOOP_VERSION, HUMAN_REVIEW_CADENCE_SESSIONS,
                            LOSS_BUDGETS)
from backend.services import counterfactual_prices as cp

logger = logging.getLogger(__name__)

SCHEMA = "decision_log_v1"

#: The recall taxonomy, taken VERBATIM from the execution repo's
#: `alpha/recall.py` (receipt: `B3_2_autopsy_and_opportunity_recall.json`
#: §typed_misses). Five states, not four: `CAPTURED` is "not a miss", and a
#: taxonomy with no not-a-miss state types every success as a failure.
TAXONOMY = ("NOT_OBSERVED", "GENERATED_NOT_RANKED", "RANKED_NOT_BOUGHT",
            "BOUGHT_SOLD_EARLY", "CAPTURED")

#: Sixth state, and it is a REFUSAL rather than a class. If we do not know
#: whether the day was ranked or whether a fill exists, typing the row anyway
#: blames a stage at random -- the exact mistake the execution repo's ledger
#: refuses to make when a seal is missing.
UNCLASSIFIED = "UNCLASSIFIED"

TAXONOMY_MEANING = {
    "NOT_OBSERVED": "never entered any AEGIS list. The repair is COVERAGE.",
    "GENERATED_NOT_RANKED": ("we had the name; the ranking did not surface it. "
                             "The repair is the MODEL."),
    "RANKED_NOT_BOUGHT": ("the ranking named it and no position exists. The "
                          "repair is EXECUTION or an admission gate."),
    "BOUGHT_SOLD_EARLY": ("closed inside the declared minimum hold. The repair "
                          "is the EXIT RULE."),
    "CAPTURED": "not a miss.",
    UNCLASSIFIED: ("an input needed to type this row is UNKNOWN. Absence of a "
                   "code is not evidence of one."),
}

COUNTERFACTUALS = ("held_to_horizon", "held_to_next_review",
                   "engine_pick_same_day", "spy")

MODE_A, MODE_B = "A", "B"


class DecisionRefused(ValueError):
    """A decision row is missing something without which it cannot be graded."""


class LessonNotYetLearnable(LookupError):
    """A lesson was requested before its own row had resolved.

    A refusal, not an empty result: "there is no lesson" and "the lesson exists
    and you are not allowed to have seen it yet" are opposite facts, and only
    one of them is a leak.
    """


# ── the row ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DecisionRow:
    source: str                       # "human:murat" | "engine:<book>"
    symbol: str
    direction: str                    # up | down | none
    action: str                       # enter | add | trim | exit
    decided_at_utc: str
    decision_day: str                 # the SESSION the decision is priced from
    horizon_sessions: int
    min_normal_hold_sessions: int
    loss_budget_ref: str
    entry_price: float | None = None
    shares_delta: float | None = None
    review_cadence_sessions: int | None = None
    thesis_id: str | None = None
    falsifier: str | None = None
    engine_pick_symbol: str | None = None
    engine_pick_source: str | None = None
    #: TRI-STATE on purpose. `None` is "unknown", not "no".
    observed: bool | None = None
    ranked: bool | None = None
    bought: bool | None = None
    exit_day: str | None = None
    exit_price: float | None = None
    status: str = "PENDING"
    notes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in ("up", "down", "none"):
            raise DecisionRefused(
                f"direction must be up/down/none, got {self.direction!r}.")
        if self.action not in ("enter", "add", "trim", "exit"):
            raise DecisionRefused(
                f"action must be enter/add/trim/exit, got {self.action!r}.")
        if ":" not in self.source:
            raise DecisionRefused(
                f"source={self.source!r} must be a BRAIN name -- 'human:<author>' "
                "or 'engine:<book>'. Invariant 18: both authority levels write "
                "the same row, so the row has to say which one wrote it.")
        if int(self.horizon_sessions) <= 0:
            raise DecisionRefused(
                "horizon_sessions must be positive: the row is resolved at its "
                "OWN horizon, never at a fixed 5 days.")
        if int(self.min_normal_hold_sessions) < 0:
            raise DecisionRefused("min_normal_hold_sessions is required (>= 0).")
        if self.loss_budget_ref not in LOSS_BUDGETS:
            raise DecisionRefused(
                f"loss_budget_ref={self.loss_budget_ref!r} is not declared; "
                f"known: {sorted(LOSS_BUDGETS)} (invariant 19).")
        try:
            cp._as_date(self.decision_day)
        except Exception as exc:                                  # noqa: BLE001
            raise DecisionRefused(
                f"decision_day={self.decision_day!r} is not a date: {exc}") from exc
        if self.review_cadence_sessions is None:
            object.__setattr__(self, "review_cadence_sessions",
                               min(int(HUMAN_REVIEW_CADENCE_SESSIONS),
                                   int(self.horizon_sessions)))
        object.__setattr__(self, "symbol", str(self.symbol).upper().strip())

    # -- derived -------------------------------------------------------------
    @property
    def mode(self) -> str:
        return MODE_A if self.source.startswith("human:") else MODE_B

    @property
    def sign(self) -> int:
        return -1 if self.direction == "down" else 1

    def decision_id(self) -> str:
        body = json.dumps({k: v for k, v in asdict(self).items()
                           if k not in ("status", "notes")},
                          sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(body.encode()).hexdigest()[:16]

    def resolves_on(self) -> tuple[str, str]:
        d, cal = cp.sessions_after(self.decision_day, int(self.horizon_sessions))
        return d.isoformat(), cal

    def reviews_on(self) -> tuple[str, str]:
        d, cal = cp.sessions_after(self.decision_day, int(self.review_cadence_sessions))
        return d.isoformat(), cal

    def as_row(self) -> dict:
        resolves, cal = self.resolves_on()
        reviews, _ = self.reviews_on()
        return {
            "schema": SCHEMA, "version": HUMAN_LOOP_VERSION,
            "decision_id": self.decision_id(), "mode": self.mode,
            "resolves_on": resolves, "reviews_on": reviews,
            "session_calendar": cal,
            #: The lesson from this row may not be READ before this instant.
            "learnable_at_utc": f"{resolves}T21:00:00+00:00",
            "learnable_basis": ("the close of the resolving session (21:00 UTC "
                                "≈ 16:00 ET, no DST table consulted -- the "
                                "error is one hour and it is on the LATE side)"),
            **asdict(self),
        }


def open_row(**kwargs) -> DecisionRow:
    """Build a PENDING row, or refuse naming what is missing."""
    kwargs.setdefault("decided_at_utc",
                      datetime.now(timezone.utc).isoformat(timespec="seconds"))
    kwargs.setdefault("decision_day", str(cp._as_date(kwargs["decided_at_utc"])))
    return DecisionRow(**kwargs)


def from_thesis(t, *, action: str = "enter", decision_day: str | None = None,
                entry_price: float | None = None, shares_delta: float | None = None,
                engine_pick_symbol: str | None = None,
                engine_pick_source: str | None = None,
                observed: bool | None = None, ranked: bool | None = None,
                bought: bool | None = None) -> DecisionRow:
    """The H2 -> T2 wire: a `HumanThesis` becomes a PENDING decision row.

    Every hold field comes from the THESIS, so a human row and a book row are
    graded on the same three declarations.
    """
    return open_row(
        source=t.brain, symbol=t.symbol, direction=t.direction, action=action,
        decided_at_utc=t.stated_at_utc,
        decision_day=decision_day or str(cp._as_date(t.stated_at_utc)),
        horizon_sessions=int(t.horizon_sessions),
        min_normal_hold_sessions=int(t.min_normal_hold_sessions),
        review_cadence_sessions=int(t.review_cadence_sessions),
        loss_budget_ref=t.loss_budget_ref, thesis_id=t.thesis_id(),
        falsifier=t.falsifier, entry_price=entry_price, shares_delta=shares_delta,
        engine_pick_symbol=engine_pick_symbol, engine_pick_source=engine_pick_source,
        observed=observed, ranked=ranked, bought=bought,
        notes={"expected_move": t.expected_move, "conviction": t.conviction,
               "catalyst": t.catalyst, "catalyst_at_utc": t.catalyst_at_utc},
    )


# ── the taxonomy ────────────────────────────────────────────────────────────
def classify(row: DecisionRow, *, sessions_held: int | None = None) -> dict:
    """Type the row into the recall taxonomy, or refuse.

    Refuses (UNCLASSIFIED) whenever an input is UNKNOWN rather than FALSE. The
    execution repo's ledger learned this on 2026-09-04: with no seal for the day,
    treating the ranking as empty types every observed name GENERATED_NOT_RANKED
    and blames the MODEL for a night the seal never ran.
    """
    if row.observed is False:
        return {"state": "NOT_OBSERVED", "reason": TAXONOMY_MEANING["NOT_OBSERVED"]}
    if row.observed is None:
        return {"state": UNCLASSIFIED,
                "reason": "`observed` is UNKNOWN; coverage cannot be blamed or cleared."}
    if row.ranked is None:
        return {"state": UNCLASSIFIED,
                "reason": ("`ranked` is UNKNOWN (no seal for the day). Treating it "
                           "as an empty ranking would blame the MODEL for a night "
                           "the seal never ran.")}
    if row.ranked is False:
        return {"state": "GENERATED_NOT_RANKED",
                "reason": TAXONOMY_MEANING["GENERATED_NOT_RANKED"]}
    if row.bought is None:
        return {"state": UNCLASSIFIED,
                "reason": ("`bought` is UNKNOWN (no decisions ledger). Everything "
                           "ranked would otherwise type RANKED_NOT_BOUGHT and "
                           "blame EXECUTION.")}
    if row.bought is False:
        return {"state": "RANKED_NOT_BOUGHT",
                "reason": TAXONOMY_MEANING["RANKED_NOT_BOUGHT"]}
    held = sessions_held
    if held is None and row.exit_day:
        held = cp.sessions_between(row.decision_day, row.exit_day)[0]
    if held is None:
        return {"state": "CAPTURED",
                "reason": ("no exit is recorded, so the position is treated as "
                           "held. sold_early is TRI-STATE: absence of an exit "
                           "code is not evidence of one."),
                "sessions_held": None}
    if int(held) < int(row.min_normal_hold_sessions):
        return {"state": "BOUGHT_SOLD_EARLY",
                "reason": (f"closed after {held} sessions, inside the declared "
                           f"minimum hold of {row.min_normal_hold_sessions}. "
                           + TAXONOMY_MEANING["BOUGHT_SOLD_EARLY"]),
                "sessions_held": int(held)}
    return {"state": "CAPTURED", "reason": TAXONOMY_MEANING["CAPTURED"],
            "sessions_held": int(held)}


# ── the grader ──────────────────────────────────────────────────────────────
#: The injected price function's contract: it takes (symbol, start, end) and
#: returns `{"ok": bool, "ret": float|None, "source": str, "reason": str|None}`.
#: A double that omits `source` is REFUSED -- otherwise a test could smuggle a
#: number with no provenance through the one place provenance is enforced.
PriceFn = Callable[..., dict]


def _ret(price_fn: PriceFn, symbol: str, start: str, end: str) -> dict:
    out = price_fn(symbol, start, end)
    if not isinstance(out, dict) or "source" not in out:
        raise DecisionRefused(
            "the price function returned a value with no `source`. Every "
            "counterfactual must name what answered it; an unsourced number is "
            "the zero this grader exists to refuse.")
    return out


def _leg(name: str, out: dict, sign: int) -> dict:
    if not out.get("ok"):
        return {"leg": name, "available": False, "ret": None,
                "source": out.get("source", "NOT_AVAILABLE"),
                "reason": out.get("reason") or "the source could not answer",
                "attempts": out.get("attempts", [])}
    return {"leg": name, "available": True,
            "ret": float(sign) * float(out["ret"]),
            "raw_ret": float(out["ret"]), "source": out["source"],
            "start_day": out.get("start_day"), "end_day": out.get("end_day"),
            "start_price": out.get("start_price"), "end_price": out.get("end_price"),
            "reason": None}


def resolve(row: DecisionRow, *, as_of: str | None = None,
            price_fn: PriceFn | None = None,
            sessions_held: int | None = None) -> dict:
    """Grade one row at ITS OWN horizon against the four counterfactuals.

    `as_of` is the date the grader is standing on. A row whose horizon has not
    arrived comes back `status: "PENDING"` with the date it will resolve -- that
    is a state, not an error. A row that HAS resolved comes back `"RESOLVED"`
    with four legs, each naming its price source, and a regret per leg.
    """
    pf = price_fn or cp.window_return
    resolves_on, cal = row.resolves_on()
    reviews_on, _ = row.reviews_on()
    today = str(cp._as_date(as_of)) if as_of else str(cp._as_date(
        datetime.now(timezone.utc)))

    base = {
        "schema": "decision_grade_v1", "version": HUMAN_LOOP_VERSION,
        "decision_id": row.decision_id(), "source": row.source, "mode": row.mode,
        "symbol": row.symbol, "direction": row.direction, "action": row.action,
        "decision_day": row.decision_day, "resolves_on": resolves_on,
        "reviews_on": reviews_on, "session_calendar": cal,
        "horizon_sessions": int(row.horizon_sessions),
        "review_cadence_sessions": int(row.review_cadence_sessions),
        "min_normal_hold_sessions": int(row.min_normal_hold_sessions),
        "loss_budget_ref": row.loss_budget_ref,
        "loss_budget": dict(LOSS_BUDGETS[row.loss_budget_ref]),
        "thesis_id": row.thesis_id, "as_of": today,
        "sign": row.sign,
        "sign_basis": ("a `down` thesis has its returns negated before anything "
                       "else; regret_vs_X = X - actual, so POSITIVE regret means "
                       "the counterfactual would have been better"),
        "graded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "learnable_at_utc": f"{resolves_on}T21:00:00+00:00",
        "benchmark": {"symbol": COUNTERFACTUAL_BENCHMARK_SYMBOL,
                      "account": COUNTERFACTUAL_BENCHMARK_ACCOUNT,
                      "contract": COUNTERFACTUAL_BENCHMARK_CONTRACT,
                      "keys_present": False,
                      "note": ("no key for that account exists in this "
                               "environment, so the SPY leg is computed from "
                               "PRICE DATA and names its source")},
    }

    if today < resolves_on:
        base.update({"status": "PENDING",
                     "reason": (f"the row's own horizon of {row.horizon_sessions} "
                                f"sessions resolves on {resolves_on}; as_of is "
                                f"{today}. Resolving early would grade a "
                                "different horizon than the one declared."),
                     "counterfactuals": None, "regret": None,
                     "taxonomy": classify(row, sessions_held=sessions_held)})
        return base

    legs = {
        "held_to_horizon": _leg("held_to_horizon",
                                _ret(pf, row.symbol, row.decision_day, resolves_on),
                                row.sign),
        "held_to_next_review": _leg("held_to_next_review",
                                    _ret(pf, row.symbol, row.decision_day, reviews_on),
                                    row.sign),
        "spy": _leg("spy",
                    _ret(pf, COUNTERFACTUAL_BENCHMARK_SYMBOL,
                         row.decision_day, resolves_on),
                    1),
    }
    if row.engine_pick_symbol:
        legs["engine_pick_same_day"] = _leg(
            "engine_pick_same_day",
            _ret(pf, row.engine_pick_symbol, row.decision_day, resolves_on), 1)
        legs["engine_pick_same_day"]["pick"] = row.engine_pick_symbol
        legs["engine_pick_same_day"]["pick_source"] = row.engine_pick_source
    else:
        legs["engine_pick_same_day"] = {
            "leg": "engine_pick_same_day", "available": False, "ret": None,
            "source": "NOT_AVAILABLE", "pick": None,
            "reason": ("no engine pick was recorded for this day. The engine leg "
                       "is the only one that compares the two AUTHORITY LEVELS "
                       "on identical information, so its absence is reported "
                       "rather than filled with the benchmark.")}

    # ACTUAL: what the decision earned. An exit makes it observable; no exit
    # means the position ran to horizon, and the row says which it was.
    if row.exit_day:
        actual_leg = _leg("actual",
                          _ret(pf, row.symbol, row.decision_day, row.exit_day),
                          row.sign)
        actual_basis = f"priced to the logged exit on {row.exit_day}"
    else:
        actual_leg = dict(legs["held_to_horizon"], leg="actual")
        actual_basis = ("no exit is logged, so the position is treated as held to "
                        "horizon and `actual` EQUALS held_to_horizon. Its regret "
                        "is therefore exactly 0.0 by construction, not by luck.")

    regret, best = {}, None
    for name in COUNTERFACTUALS:
        leg = legs[name]
        if leg.get("available") and actual_leg.get("available"):
            r = float(leg["ret"]) - float(actual_leg["ret"])
            regret[name] = r
            if best is None or r > best[1]:
                best = (name, r)
        else:
            regret[name] = None

    n_ok = sum(1 for v in regret.values() if v is not None)
    base.update({
        "status": "RESOLVED" if actual_leg.get("available") else "UNGRADEABLE",
        "actual": actual_leg, "actual_basis": actual_basis,
        "counterfactuals": legs, "regret": regret,
        "regret_basis": "regret_vs_X = X - actual; positive means X was better",
        "worst_regret": ({"leg": best[0], "regret": best[1]} if best else None),
        "n_counterfactuals_available": n_ok,
        "fully_graded": bool(actual_leg.get("available") and n_ok == len(COUNTERFACTUALS)),
        "price_sources": sorted({leg.get("source") for leg in
                                 list(legs.values()) + [actual_leg]
                                 if leg.get("source")}),
        "taxonomy": classify(row, sessions_held=sessions_held),
        "reason": None if actual_leg.get("available") else actual_leg.get("reason"),
    })
    return base


# ── the free-model reflection ───────────────────────────────────────────────
_SENTENCE = re.compile(r"[^.!?]+[.!?]")

REFLECTION_SYSTEM = (
    "You review ONE already-graded investment decision. Write 2 to 4 sentences "
    "of plain English. Say what the decision earned, which alternative would "
    "have done better, and what that implies about the decision PROCESS. Do not "
    "give advice, do not suggest a trade, do not invent numbers that are not in "
    "the input, and do not use bullet points. Answer in English only."
)


def reflection_prompt(graded: dict) -> str:
    def pct(x):
        return "unavailable" if x is None else f"{100.0 * float(x):+.2f}%"
    legs = graded.get("counterfactuals") or {}
    lines = [
        f"Decision {graded['decision_id']} by {graded['source']} "
        f"({'human' if graded['mode'] == 'A' else 'machine'}).",
        f"{graded['action']} {graded['symbol']} {graded['direction']} on "
        f"{graded['decision_day']}, horizon {graded['horizon_sessions']} sessions, "
        f"resolved {graded['resolves_on']}.",
        f"Actual return over the held window: {pct((graded.get('actual') or {}).get('ret'))}.",
    ]
    for name in COUNTERFACTUALS:
        leg = legs.get(name) or {}
        if leg.get("available"):
            lines.append(f"Counterfactual {name}: {pct(leg.get('ret'))} "
                         f"(regret {pct((graded.get('regret') or {}).get(name))}).")
        else:
            lines.append(f"Counterfactual {name}: NOT AVAILABLE "
                         f"({str(leg.get('reason'))[:120]}).")
    lines.append(f"Recall taxonomy: {(graded.get('taxonomy') or {}).get('state')}.")
    return "\n".join(lines)


def reflect(graded: dict, *, backends: tuple[str, ...] | None = None,
            record: bool = True) -> dict:
    """2-4 sentences on a FREE backend, with the $0.00 cost line kept.

    DeepSeek is not in `config.DECISION_REFLECTION_BACKENDS` and a test asserts
    it never enters: the ~$9 balance is reserved for the era replay, and a
    reflection is the most optional thing in this module.
    """
    chain = tuple(backends or DECISION_REFLECTION_BACKENDS)
    if any(b == "deepseek" for b in chain):
        raise DecisionRefused(
            "the reflection may not run on the PAID provider. It is the most "
            "optional output in this module and the balance is reserved.")
    prompt = reflection_prompt(graded)
    attempts = []
    for backend in chain:
        try:
            from backend.services import free_inference as fi        # noqa: PLC0415

            reply = fi.complete(backend, prompt, system=REFLECTION_SYSTEM,
                                purpose="decision_reflection",
                                max_tokens=DECISION_REFLECTION_MAX_TOKENS,
                                temperature=0.0, record=record)
        except Exception as exc:                                     # noqa: BLE001
            attempts.append({"backend": backend, "ok": False,
                             "reason": f"{type(exc).__name__}: {str(exc)[:200]}"})
            continue
        text = (reply.text or "").strip()
        n = len(_SENTENCE.findall(text)) or (1 if text else 0)
        if not (DECISION_REFLECTION_MIN_SENTENCES <= n <= DECISION_REFLECTION_MAX_SENTENCES):
            attempts.append({"backend": backend, "ok": False,
                             "reason": f"{n} sentences, wanted "
                                       f"{DECISION_REFLECTION_MIN_SENTENCES}-"
                                       f"{DECISION_REFLECTION_MAX_SENTENCES}",
                             "text": text[:400]})
            continue
        return {"status": "OK", "text": text, "sentences": n,
                "backend": reply.backend, "model": reply.model,
                "cost_usd": float(reply.cost_usd), "cost_class": reply.cost_class,
                "tokens_in": reply.tokens_in, "tokens_out": reply.tokens_out,
                "latency_s": round(reply.latency_s, 3), "attempts": attempts,
                "paid_provider_used": False}
    return {"status": "REFUSED", "text": None, "cost_usd": 0.0,
            "paid_provider_used": False, "attempts": attempts,
            "reason": ("no free backend produced a usable 2-4 sentence "
                       "reflection. The GRADE is unaffected: the arithmetic is "
                       "finished before this function is called.")}


# ── append-only storage ─────────────────────────────────────────────────────
def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def record_decision(row: DecisionRow, *, path: Path | None = None) -> dict:
    out = row.as_row()
    _append(Path(path or DECISION_LOG_PATH), out)
    return out


def record_grade(graded: dict, *, path: Path | None = None) -> dict:
    _append(Path(path or DECISION_GRADE_LOG_PATH), graded)
    return graded


def _read(path: Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load_decisions(path: Path | None = None) -> list[dict]:
    return _read(Path(path or DECISION_LOG_PATH))


def load_grades(path: Path | None = None) -> list[dict]:
    """Newest grade per decision_id, in decision order (a grade is append-only,
    so a re-grade appends and the LAST line wins)."""
    latest: dict[str, dict] = {}
    for g in _read(Path(path or DECISION_GRADE_LOG_PATH)):
        latest[str(g.get("decision_id"))] = g
    return list(latest.values())


# ── the as_of gate ──────────────────────────────────────────────────────────
def _learnable(g: dict, as_of_utc: str) -> bool:
    return str(g.get("learnable_at_utc") or "9999") <= as_of_utc


def _norm_as_of(as_of) -> str:
    s = str(as_of)
    return f"{s}T23:59:59+00:00" if len(s) == 10 else s


def lessons(*, as_of, path: Path | None = None,
            decision_id: str | None = None) -> dict:
    """Graded rows whose lesson had ALREADY been learnable at `as_of`.

    Asking for a named `decision_id` that had not resolved raises
    `LessonNotYetLearnable`. Asking for the whole set simply filters, and
    reports how many were withheld -- a count of what you were not allowed to
    see is itself information a replay needs.
    """
    cutoff = _norm_as_of(as_of)
    all_grades = load_grades(path)
    if decision_id is not None:
        hit = [g for g in all_grades if g.get("decision_id") == decision_id]
        if not hit:
            raise LessonNotYetLearnable(
                f"no graded row {decision_id!r} exists at all.")
        g = hit[0]
        if not _learnable(g, cutoff):
            raise LessonNotYetLearnable(
                f"decision {decision_id} does not become learnable until "
                f"{g.get('learnable_at_utc')}, and as_of is {cutoff}. Returning "
                "it would let a lesson written after the fact enter a replay of "
                "the period it was learnt from.")
        return {"as_of": cutoff, "n": 1, "n_withheld": 0, "lessons": [g]}
    ok = [g for g in all_grades if _learnable(g, cutoff)]
    return {"as_of": cutoff, "n": len(ok),
            "n_withheld": len(all_grades) - len(ok),
            "withheld_note": ("rows whose horizon had not yet resolved at as_of. "
                              "They exist; they are not readable from here."),
            "lessons": ok}


# ── the scoreboard, with the honesty gate ───────────────────────────────────
def scoreboard(*, path: Path | None = None, as_of=None) -> dict:
    grades = (lessons(as_of=as_of, path=path)["lessons"] if as_of is not None
              else load_grades(path))
    graded = [g for g in grades if g.get("fully_graded")]
    resolved = [g for g in grades if g.get("status") == "RESOLVED"]
    pending = [g for g in grades if g.get("status") == "PENDING"]
    tax: dict[str, int] = {}
    for g in grades:
        tax[(g.get("taxonomy") or {}).get("state", UNCLASSIFIED)] = \
            tax.get((g.get("taxonomy") or {}).get("state", UNCLASSIFIED), 0) + 1
    by_mode: dict[str, int] = {}
    for g in grades:
        by_mode[g.get("mode", "?")] = by_mode.get(g.get("mode", "?"), 0) + 1
    leg_cover = {name: sum(1 for g in resolved
                           if ((g.get("counterfactuals") or {}).get(name) or {}).get("available"))
                 for name in COUNTERFACTUALS}

    gate = len(graded) >= DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM
    out = {
        "version": HUMAN_LOOP_VERSION,
        "n_rows": len(grades), "n_resolved": len(resolved),
        "n_pending": len(pending), "n_fully_graded": len(graded),
        "gate": {
            "rule": ("no P&L claim under "
                     f"{DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM} graded rows "
                     "with four counterfactuals each"),
            "have": len(graded),
            "need": DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM,
            "met": gate,
        },
        "process_metrics": {
            "taxonomy_histogram": tax,
            "rows_by_mode": by_mode,
            "counterfactual_coverage": leg_cover,
            "n_unclassified": tax.get(UNCLASSIFIED, 0),
        },
        "claim": ("a receipt, not a result" if not gate else
                  "the gate is met; a P&L line may be computed and must still "
                  "print beta and the benchmark beside it"),
    }
    if not gate:
        out["pnl"] = None
        out["pnl_withheld_because"] = (
            f"{len(graded)} fully graded rows is under the gate of "
            f"{DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM}. Process metrics only.")
    else:
        rets = [float(g["actual"]["ret"]) for g in graded]
        out["pnl"] = {
            "n": len(rets), "mean_actual_ret": sum(rets) / len(rets),
            "mean_regret": {
                name: (lambda v: (sum(v) / len(v)) if v else None)(
                    [float(g["regret"][name]) for g in graded
                     if (g.get("regret") or {}).get(name) is not None])
                for name in COUNTERFACTUALS},
            "caveat": ("simple mean over graded rows. NOT beta-adjusted, NOT "
                       "multiplicity-corrected, and not an alpha claim."),
        }
    return out


# ── KNOWN-ANSWER BATTERY ────────────────────────────────────────────────────
#: A grader nobody has shown to produce the RIGHT regret on a constructed
#: example is not a grader. This battery plants a price panel whose answers are
#: computable by hand, runs the real `resolve()` over it, and compares against
#: numbers written down BEFORE the code ran. It is a function rather than a test
#: so that it can also be executed as a receipt:
#:
#:     python -m backend.services.decision_log
#:
#: Every case names what it would catch if it failed. A battery of six cases
#: that all pass for the same reason catches one bug.

#: A synthetic panel: {symbol: {day: close}}. Sessions are consecutive weekdays
#: from 2026-03-02 (a Monday), so the XNYS calendar and weekday arithmetic agree
#: over the window and the battery cannot fail for a calendar reason.
#: The dates are NOT hand-counted: 2026-03-02 is a Monday, so 5 XNYS sessions
#: later is 2026-03-09 and 10 sessions later is 2026-03-16. The first draft of
#: this panel used 03-06 and 03-13 -- an off-by-one from counting the decision
#: day itself -- and the battery FAILED on it before any of this shipped, which
#: is the whole argument for having a battery.
_SYNTH_PANEL = {
    #: +10% over the first 5 sessions, +21% over 10. Chosen so the horizon leg
    #: and the review leg are DIFFERENT numbers: a grader that silently used one
    #: clock for both would pass a flat panel.
    "AAA": {"2026-03-02": 100.0, "2026-03-09": 110.0, "2026-03-16": 121.0},
    #: falls 20% over 10 sessions -- the SHORT case, where sign handling is the
    #: whole question.
    "BBB": {"2026-03-02": 100.0, "2026-03-09": 90.0, "2026-03-16": 80.0},
    #: the engine's pick: +5% over the horizon.
    "ENG": {"2026-03-02": 50.0, "2026-03-09": 51.0, "2026-03-16": 52.5},
    #: the benchmark: +2% over the horizon.
    "SPY": {"2026-03-02": 400.0, "2026-03-09": 404.0, "2026-03-16": 408.0},
}


def _synth_price_fn(symbol: str, start, end) -> dict:
    """A price function over `_SYNTH_PANEL` with the SAME contract as the real
    one -- `ok`, `ret`, `source`, `reason`. It names a source, so it cannot be
    used to smuggle an unsourced number past `_ret`."""
    tbl = _SYNTH_PANEL.get(str(symbol).upper())
    s, e = str(start)[:10], str(end)[:10]
    if tbl is None:
        return {"ok": False, "ret": None, "source": "NOT_AVAILABLE",
                "reason": f"{symbol} is not in the synthetic panel"}
    if s not in tbl or e not in tbl:
        return {"ok": False, "ret": None, "source": "NOT_AVAILABLE",
                "reason": f"{symbol} has no synthetic close on {s} or {e}"}
    return {"ok": True, "ret": (tbl[e] / tbl[s]) - 1.0, "source": "synthetic_panel",
            "start_day": s, "end_day": e,
            "start_price": tbl[s], "end_price": tbl[e], "reason": None}


def known_answer_battery() -> dict:
    """Run the planted cases and report pass/fail per assertion.

    Returns a receipt-shaped dict. Nothing here is random, nothing is fetched,
    and every expected number is written in this file beside the case.
    """
    tol = 1e-9
    cases: list[dict] = []

    def case(name: str, catches: str, got, want, ok=None):
        passed = (ok if ok is not None else
                  ((want is None and got is None) or
                   (got is not None and want is not None
                    and abs(float(got) - float(want)) < tol)))
        cases.append({"case": name, "catches": catches, "got": got,
                      "want": want, "pass": bool(passed)})

    # --- 1. LONG, held to horizon, no exit ---------------------------------
    # AAA 100 -> 121 over 10 sessions (2026-03-02 -> 2026-03-16) = +21%.
    # Review at 5 sessions (2026-03-09): 100 -> 110 = +10%. ENG +5%. SPY +2%.
    # actual == held_to_horizon with no exit logged, so its regret is exactly 0.
    long_row = DecisionRow(
        source="human:murat", symbol="AAA", direction="up", action="enter",
        decided_at_utc="2026-03-02T13:00:00+00:00", decision_day="2026-03-02",
        horizon_sessions=10, min_normal_hold_sessions=5,
        review_cadence_sessions=5, loss_budget_ref="human_v1",
        engine_pick_symbol="ENG", engine_pick_source="synthetic",
        observed=True, ranked=True, bought=True)
    g1 = resolve(long_row, as_of="2026-03-16", price_fn=_synth_price_fn)
    case("long/status", "a resolved row reported PENDING", g1["status"], None,
         ok=g1["status"] == "RESOLVED")
    case("long/resolves_on", "the horizon walked the wrong number of sessions",
         g1["resolves_on"], None, ok=g1["resolves_on"] == "2026-03-16")
    case("long/actual", "the actual return", g1["actual"]["ret"], 0.21)
    case("long/held_to_horizon", "the first counterfactual",
         g1["counterfactuals"]["held_to_horizon"]["ret"], 0.21)
    case("long/held_to_next_review",
         "the review leg silently reusing the horizon clock",
         g1["counterfactuals"]["held_to_next_review"]["ret"], 0.10)
    case("long/engine_pick",
         "the engine leg -- the only one comparing the two authority levels",
         g1["counterfactuals"]["engine_pick_same_day"]["ret"], 0.05)
    case("long/spy", "the benchmark leg (must be PRICE data, never a broker)",
         g1["counterfactuals"]["spy"]["ret"], 0.02)
    case("long/regret_horizon", "regret sign when actual == the counterfactual",
         g1["regret"]["held_to_horizon"], 0.0)
    case("long/regret_review", "regret = X - actual (review was WORSE, so negative)",
         g1["regret"]["held_to_next_review"], 0.10 - 0.21)
    case("long/regret_spy", "the benchmark regret",
         g1["regret"]["spy"], 0.02 - 0.21)
    case("long/worst_regret", "the worst alternative is picked by max regret",
         g1["worst_regret"]["leg"], None,
         ok=g1["worst_regret"]["leg"] == "held_to_horizon")
    case("long/fully_graded", "a row missing a leg claiming to be fully graded",
         g1["fully_graded"], None, ok=g1["fully_graded"] is True)
    case("long/taxonomy", "a held winner typed as a miss",
         g1["taxonomy"]["state"], None, ok=g1["taxonomy"]["state"] == "CAPTURED")

    # --- 2. SHORT: BBB falls 20%, so a DOWN thesis EARNED +20% -------------
    short_row = DecisionRow(
        source="engine:hack3", symbol="BBB", direction="down", action="enter",
        decided_at_utc="2026-03-02T13:00:00+00:00", decision_day="2026-03-02",
        horizon_sessions=10, min_normal_hold_sessions=5,
        review_cadence_sessions=5, loss_budget_ref="thesis_3m_v1",
        observed=True, ranked=True, bought=True)
    g2 = resolve(short_row, as_of="2026-03-16", price_fn=_synth_price_fn)
    case("short/actual", "SIGN HANDLING -- the single most expensive bug here",
         g2["actual"]["ret"], 0.20)
    case("short/raw", "the raw (unsigned) return is kept beside the signed one",
         g2["actual"]["raw_ret"], -0.20)
    case("short/spy_not_flipped", "flipping the BENCHMARK's sign with the thesis",
         g2["counterfactuals"]["spy"]["ret"], 0.02)
    case("short/mode", "a machine row typed as Mode A", g2["mode"], None,
         ok=g2["mode"] == "B")

    # --- 3. PENDING: the same row asked one session too early ---------------
    g3 = resolve(long_row, as_of="2026-03-13", price_fn=_synth_price_fn)
    case("pending/status", "grading a row before its own horizon",
         g3["status"], None, ok=g3["status"] == "PENDING")
    case("pending/no_numbers", "a PENDING row leaking counterfactual numbers",
         g3["counterfactuals"], None, ok=g3["counterfactuals"] is None)

    # --- 4. A MISSING BENCHMARK MUST NOT BE ZERO ---------------------------
    def no_spy(symbol, start, end):
        if str(symbol).upper() == "SPY":
            return {"ok": False, "ret": None, "source": "NOT_AVAILABLE",
                    "reason": "planted: the benchmark source is down"}
        return _synth_price_fn(symbol, start, end)

    g4 = resolve(long_row, as_of="2026-03-16", price_fn=no_spy)
    case("no_spy/ret_is_none",
         "A MISSING BENCHMARK RETURNING 0.0 -- the failure this module prevents",
         g4["counterfactuals"]["spy"]["ret"], None)
    case("no_spy/regret_is_none", "a missing leg producing a regret anyway",
         g4["regret"]["spy"], None)
    case("no_spy/not_fully_graded", "a 3-leg row counted toward the 20-row gate",
         g4["fully_graded"], None, ok=g4["fully_graded"] is False)
    case("no_spy/source_named", "a leg with no named source",
         g4["counterfactuals"]["spy"]["source"], None,
         ok=g4["counterfactuals"]["spy"]["source"] == "NOT_AVAILABLE")

    # --- 5. SOLD EARLY: exit at 3 sessions under a 5-session minimum hold ---
    early = DecisionRow(
        source="human:murat", symbol="AAA", direction="up", action="enter",
        decided_at_utc="2026-03-02T13:00:00+00:00", decision_day="2026-03-02",
        horizon_sessions=10, min_normal_hold_sessions=5, review_cadence_sessions=5,
        loss_budget_ref="human_v1", exit_day="2026-03-05",
        observed=True, ranked=True, bought=True)
    g5 = resolve(early, as_of="2026-03-16", price_fn=_synth_price_fn,
                 sessions_held=3)
    case("early/taxonomy", "an early exit typed CAPTURED",
         g5["taxonomy"]["state"], None,
         ok=g5["taxonomy"]["state"] == "BOUGHT_SOLD_EARLY")
    case("early/actual_unavailable_is_not_zero",
         "an unpriceable exit becoming a 0% actual",
         g5["actual"]["ret"], None)

    # --- 6. NO ENGINE PICK: the leg refuses instead of borrowing SPY -------
    no_pick = DecisionRow(
        source="human:murat", symbol="AAA", direction="up", action="enter",
        decided_at_utc="2026-03-02T13:00:00+00:00", decision_day="2026-03-02",
        horizon_sessions=10, min_normal_hold_sessions=5, review_cadence_sessions=5,
        loss_budget_ref="human_v1", observed=True, ranked=True, bought=True)
    g6 = resolve(no_pick, as_of="2026-03-16", price_fn=_synth_price_fn)
    case("no_pick/leg_unavailable", "the engine leg quietly falling back to SPY",
         g6["counterfactuals"]["engine_pick_same_day"]["ret"], None)
    case("no_pick/not_fully_graded", "a 3-leg row counted as four",
         g6["fully_graded"], None, ok=g6["fully_graded"] is False)

    # --- 7. UNCLASSIFIED beats a guess -------------------------------------
    unknown = DecisionRow(
        source="human:murat", symbol="AAA", direction="up", action="enter",
        decided_at_utc="2026-03-02T13:00:00+00:00", decision_day="2026-03-02",
        horizon_sessions=10, min_normal_hold_sessions=5, review_cadence_sessions=5,
        loss_budget_ref="human_v1", observed=True, ranked=None, bought=None)
    g7 = resolve(unknown, as_of="2026-03-16", price_fn=_synth_price_fn)
    case("unknown/unclassified", "an unknown ranking blaming the MODEL",
         g7["taxonomy"]["state"], None,
         ok=g7["taxonomy"]["state"] == UNCLASSIFIED)

    # --- 8. AN UNSOURCED NUMBER IS REFUSED ---------------------------------
    def sourceless(symbol, start, end):
        return {"ok": True, "ret": 0.5}

    try:
        resolve(long_row, as_of="2026-03-16", price_fn=sourceless)
        refused = False
    except DecisionRefused:
        refused = True
    case("unsourced/refused", "a number with no provenance passing the grader",
         refused, None, ok=refused)

    n_pass = sum(1 for c in cases if c["pass"])
    return {
        "battery": "decision_log_known_answer_v1",
        "version": HUMAN_LOOP_VERSION,
        "n_cases": len(cases), "n_pass": n_pass, "n_fail": len(cases) - n_pass,
        "all_pass": n_pass == len(cases),
        "panel": _SYNTH_PANEL,
        "note": ("every expected value is written in "
                 "`backend/services/decision_log.py` beside its case, before the "
                 "code runs. A battery whose expectations are read off the "
                 "output is a screenshot of a bug."),
        "cases": cases,
    }


def main() -> int:
    r = known_answer_battery()
    for c in r["cases"]:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['case']:34s} "
              f"got={c['got']!r} want={c['want']!r}")
    print(f"\n{r['n_pass']}/{r['n_cases']} known-answer cases pass")
    return 0 if r["all_pass"] else 1


if __name__ == "__main__":                                    # pragma: no cover
    raise SystemExit(main())
