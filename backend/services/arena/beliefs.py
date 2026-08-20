"""Persistent beliefs: yesterday's number comes from disk, not from the model.

THE DEFECT THIS EXISTS TO FIX
=============================
`perception.perceive` asked the LLM for its prior AND its posterior in the
same call. That is not a belief revision. A model asked "what did you think
before, and what do you think now" writes both halves to make the second half
look reasoned, and `belief_change = posterior - prior` — the quantity the
whole belief-change contract is built on, and the quantity the engine turns
into a weight tilt — becomes a free parameter the forecaster sets itself.

Here the prior is READ FROM THE LEDGER: the last posterior this book recorded
for this name, with the date it was recorded and the thesis it came with. The
model is shown it, told it may not revise it, and asked only for what today's
evidence does to it. A first-ever look has no stored prior, so it opens at a
DECLARED base rate (`OPENING_PRIOR`) and is stamped `INITIATION` — an opening
level is not a belief change and must never be counted as one.

WHAT IT IS NOT
==============
It does not trade. It does not size. It runs on every session, including the
~19 of every 20 on which nothing is due, because thinking daily and trading
daily are different things and only the second one costs money. Every review
mints a gradeable PredictionRecord in the arena's own ledger, so a year from
now the question "was the daily review worth its API bill" has an answer
instead of a narrative.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.services.arena import store

logger = logging.getLogger(__name__)

SPECIALIST = "arena:belief_review:v1"
MODEL_VERSION = "arena-belief-review-v1"

#: The opening level for a name never reviewed before. Declared, not learned:
#: P(a name beats SPY over the horizon) has no reason to start anywhere but
#: even, and starting it anywhere else would smuggle a view in as a default.
OPENING_PRIOR = 0.5

THESIS_STATUSES = ("NEW", "INTACT", "WEAKENING", "BROKEN")

#: Reasons a name enters the day's review list. Recorded per row so the
#: population being graded is a fact, not a reconstruction.
REVIEW_REASONS = ("HOLDING", "CHALLENGER", "STATE_CHANGE")

_SCHEMA_HINT = (
    'Reply with ONE json object and nothing else:\n'
    '{"posterior": <float 0..1>, "evidence": "<what is new today, or NONE>",\n'
    ' "interpretation": "<why that moves or does not move the belief>",\n'
    ' "thesis": "<one sentence>", "thesis_status": "INTACT|WEAKENING|BROKEN|NEW",\n'
    ' "invalidation": "<observable that would prove this wrong>",\n'
    ' "next_observable": "<what to watch next>"}\n'
    'Your PRIOR IS GIVEN TO YOU and you may not restate, revise or reinterpret '
    'it. Report only the posterior after today\'s evidence. If today changes '
    'nothing, posterior MUST equal the prior exactly — "no update" is a valid, '
    'gradeable answer and is the correct answer most days.')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── stored state ────────────────────────────────────────────────────────────
def current_beliefs(root=None) -> dict[tuple[str, str], dict]:
    """Last recorded belief per (book_id, ticker). Append-only file, so the
    last row wins and the history stays readable."""
    out: dict[tuple[str, str], dict] = {}
    for r in store.read_beliefs(root):
        out[(r.get("book_id"), r.get("ticker"))] = r
    return out


def prior_for(book_id: str, ticker: str, *, beliefs: dict | None = None,
              root=None) -> tuple[float, dict | None]:
    """(prior, the row it came from). No row → the declared opening level."""
    beliefs = current_beliefs(root) if beliefs is None else beliefs
    prev = beliefs.get((book_id, ticker))
    if prev is None or prev.get("posterior") is None:
        return OPENING_PRIOR, None
    return float(prev["posterior"]), prev


# ── which names get looked at today ────────────────────────────────────────
def review_list(day_state: dict, *, holdings: set[str], challengers: list[str],
                beliefs: dict, book_id: str, max_names: int,
                signal: str = "arena_composite",
                min_state_change: float = 0.5) -> list[dict]:
    """Holdings first, then challengers, then names whose score moved.

    Deterministic and explicit: a review population chosen by an LLM, or by
    whatever happened to be cheap that day, cannot be graded as a population.
    Holdings are never dropped for budget — a book that stops thinking about
    what it owns is the failure this whole layer is aimed at.
    """
    names = day_state.get("names", {})
    picked: list[dict] = []
    seen: set[str] = set()

    for t in sorted(holdings):
        if names.get(t, {}).get("status") == "ok":
            picked.append({"ticker": t, "reason": "HOLDING"})
            seen.add(t)

    for t in challengers:
        if t in seen or names.get(t, {}).get("status") != "ok":
            continue
        picked.append({"ticker": t, "reason": "CHALLENGER"})
        seen.add(t)

    moved: list[tuple[float, str]] = []
    for t, row in names.items():
        if t in seen or row.get("status") != "ok":
            continue
        score = (row.get("scores") or {}).get(signal)
        prev = beliefs.get((book_id, t))
        last = (prev or {}).get("score_at_review")
        if score is None or last is None:
            continue
        if abs(float(score) - float(last)) >= min_state_change:
            moved.append((-abs(float(score) - float(last)), t))
    for _, t in sorted(moved):
        picked.append({"ticker": t, "reason": "STATE_CHANGE"})

    return picked[:max_names]


# ── the review ──────────────────────────────────────────────────────────────
def daily_review(day_state: dict, *, book_id: str, holdings: set[str],
                 challengers: list[str], llm_cfg: dict, root=None,
                 event_context: dict | None = None) -> dict:
    """One belief-update pass. Returns tilts + what it wrote + why it stopped.

    A refusal is a finding: no LLM, over budget or an unparseable reply all
    produce a status string that reaches the receipt, never a silent skip.
    """
    max_names = int(llm_cfg.get("max_names_per_day", 10))
    cap = int(llm_cfg.get("daily_call_cap", 25))
    horizon = int(llm_cfg.get("horizon_days", 20))
    tilt_scale = float(llm_cfg.get("tilt_scale", 2.0))
    result = {"status": "ok", "book_id": book_id, "tilts": {}, "reviewed": [],
              "attempted": 0, "failed": 0, "initiations": 0, "unchanged": 0,
              "event_context": ("none" if event_context is None
                                else event_context.get("status", "?")),
              "names_with_events": 0}

    try:
        from backend.services import belief_state as B
        from backend.services import llm_research as R
    except ImportError as exc:
        result["status"] = f"import_failed: {exc}"
        return result

    ok, why = R.available()
    if not ok:
        result["status"] = f"llm_unavailable: {why}"
        return result

    beliefs = current_beliefs(root)
    todo = review_list(day_state, holdings=holdings, challengers=challengers,
                       beliefs=beliefs, book_id=book_id, max_names=max_names)
    if not todo:
        result["status"] = "nothing_to_review"
        return result

    today = str(day_state.get("date"))
    already = sum(1 for r in store._read_jsonl(store.predictions_path(root))
                  if str(r.get("made_at", "")).startswith(today[:10])
                  and r.get("specialist") == SPECIALIST)
    names = day_state.get("names", {})
    records, rows = [], []

    for item in todo:
        t = item["ticker"]
        if already + result["attempted"] >= cap:
            result["status"] = "daily_cap_reached"
            break
        prior, prev = prior_for(book_id, t, beliefs=beliefs)
        row = names.get(t) or {}
        state = {"ticker": t, "date": today, "close": row.get("close"),
                 "ret21": row.get("ret21"), "vol63": row.get("vol63"),
                 "streak_up": row.get("streak_up"),
                 "coverage": (row.get("scores") or {}).get("coverage"),
                 "pit_scores": {k: v for k, v in (row.get("scores") or {}).items()
                                if k not in ("coverage",)},
                 "in_book": t in holdings}
        prior_block = {
            "prior": round(prior, 4),
            "set_on": (prev or {}).get("date", "never — this is an INITIATION"),
            "previous_thesis": (prev or {}).get("thesis", ""),
            "previous_invalidation": (prev or {}).get("invalidation", ""),
            "previous_next_observable": (prev or {}).get("next_observable", ""),
        }
        ev: dict = {}
        if event_context is not None:
            from backend.services.arena import events as _ev
            ev = _ev.for_name(event_context, t)
            if ev.get("coverage") == "FETCHED":
                result["names_with_events"] += 1
        prompt = (
            "You are the daily belief-review layer of a PAPER-TRADING "
            "experiment (PRODUCT_EXPERIMENT — no real capital, no advice). "
            "You are NOT deciding a trade and you never choose position "
            f"sizes.\n\nThe belief you must update is: P({t} beats SPY over "
            f"the next {horizon} trading days).\n\n"
            f"YOUR PRIOR (from the ledger, not from you):\n"
            f"{json.dumps(prior_block, default=str)}\n\n"
            f"TODAY'S FROZEN STATE:\n{json.dumps(state, default=str)}"
            + (f"\n\nEVENT CONTEXT (news / 8-K filings / earnings, as of this "
               f"session's close):\n{json.dumps(ev, default=str)}"
               if event_context is not None else ""))
        result["attempted"] += 1
        try:
            reply = R.ask(prompt, purpose="arena_belief_review",
                          max_tokens=500, schema_hint=_SCHEMA_HINT)
            parsed = R.parse_json_block(reply["text"]) or {}
            posterior = float(parsed["posterior"])
            if not 0.0 <= posterior <= 1.0:
                raise ValueError(f"posterior {posterior} is not a probability")
            status = str(parsed.get("thesis_status", "")).upper()
            if status not in THESIS_STATUSES:
                status = "NEW" if prev is None else "INTACT"
            rec = B.make_prediction(
                ticker=t, specialist=SPECIALIST,
                observable=B.Observable.BEATS_BENCHMARK,
                horizon_days=horizon, probability=posterior,
                threshold=None, benchmark="SPY",
                thesis=str(parsed.get("thesis", ""))[:400],
                counter_thesis=str(parsed.get("interpretation", ""))[:400],
                next_observable=str(parsed.get("next_observable", ""))[:200],
                model=reply["call"].get("model", "unknown"),
                model_version=MODEL_VERSION, prompt=prompt,
                input_snapshot={"state": state, "prior_block": prior_block,
                                "event_context": ev},
                prior=prior, posterior=posterior, arm="arena_belief_review")
            records.append(rec)
            belief_row = {
                "ts": _now(), "date": today, "book_id": book_id, "ticker": t,
                "review_reason": item["reason"],
                "prior": round(prior, 6), "posterior": round(posterior, 6),
                "belief_change": round(posterior - prior, 6),
                "prior_source": ("LEDGER" if prev is not None
                                 else "DECLARED_OPENING_PRIOR"),
                "is_initiation": prev is None,
                "thesis": str(parsed.get("thesis", ""))[:400],
                "thesis_status": status,
                "evidence": str(parsed.get("evidence", ""))[:400],
                "interpretation": str(parsed.get("interpretation", ""))[:400],
                "invalidation": str(parsed.get("invalidation", ""))[:300],
                "next_observable": str(parsed.get("next_observable", ""))[:200],
                "score_at_review": (row.get("scores") or {}).get("arena_composite"),
                # Which arm this row belongs to, recorded per row so the
                # NUMERIC_ONLY vs NUMERIC_PLUS_EVENTS ablation is a filter on
                # the ledger rather than a reconstruction from book config.
                "event_coverage": ev.get("coverage", "NOT_REQUESTED"),
                "n_events_shown": len(ev.get("events") or []),
                "prediction_id": rec.prediction_id,
                "horizon_days": horizon,
                "validation_status": "PRODUCT_EXPERIMENT", "simulation": True,
            }
            rows.append(belief_row)
            result["reviewed"].append(
                {k: belief_row[k] for k in ("ticker", "review_reason", "prior",
                                            "posterior", "thesis_status",
                                            "is_initiation")})
            if prev is None:
                result["initiations"] += 1
            elif abs(posterior - prior) < 1e-9:
                result["unchanged"] += 1
            # An INITIATION is a level, not a change: tilting on it would let
            # the opening prior masquerade as new information on day one.
            if prev is not None:
                result["tilts"][t] = 1.0 + tilt_scale * (posterior - prior)
        except Exception as exc:  # noqa: BLE001 — one name never kills the pass
            result["failed"] += 1
            logger.warning("ARENA belief review failed for %s/%s: %s",
                           book_id, t, exc)

    if rows:
        store.append_beliefs(rows, root)
    if records:
        from backend.services import belief_state as B
        B.append(records, store.predictions_path(root))
    result["written"] = len(rows)
    return result


def history(book_id: str, ticker: str, root=None) -> list[dict]:
    """Every recorded belief for one name, oldest first — the audit trail the
    prior is read from."""
    return [r for r in store.read_beliefs(root)
            if r.get("book_id") == book_id and r.get("ticker") == ticker]
