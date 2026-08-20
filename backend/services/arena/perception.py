"""LLM perception for arena books: perceive, revise, get graded. Never size.

Every accepted revision is minted as a PredictionRecord under the
belief-change contract (prior/posterior) into the ARENA'S OWN ledger
(`<arena>/predictions.jsonl`) — never `predictions.jsonl`, whose evidence
populations are spoken for. Spend rides the research governor's ledgered
`ask()` (programme-wide accounting via its mirror), with an arena daily call
cap on top.

The engine converts `belief_change` into a bounded multiplicative tilt in
policies.apply_llm_tilts. If the LLM is unavailable or over budget, books run
untitled and the receipt says so — a refusal is a finding, not an exception.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.services.arena import store

logger = logging.getLogger(__name__)

SPECIALIST = "arena:perception:v1"

_SCHEMA_HINT = (
    'Reply with ONE json object and nothing else:\n'
    '{"prior": <float 0..1>, "posterior": <float 0..1>,\n'
    ' "thesis": "<one sentence>", "counter_thesis": "<one sentence>",\n'
    ' "invalidation": "<observable that would prove this wrong>",\n'
    ' "next_observable": "<what to watch next>"}\n'
    'prior = P(name beats SPY over the next 20 trading days) BEFORE today\'s '
    'evidence; posterior = the same probability AFTER it. If today changes '
    'nothing, posterior MUST equal prior — "no update" is a valid, gradeable '
    'answer.')


def _today_call_count(root=None) -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    return sum(1 for r in store._read_jsonl(store.predictions_path(root))
               if str(r.get("made_at", "")).startswith(today))


def perceive(day_state: dict, tickers: list[str], *, llm_cfg: dict,
             root=None) -> dict:
    """Return {"tilts": {ticker: factor}, "minted": [...], "status": str}."""
    cap = int(llm_cfg.get("daily_call_cap", 25))
    max_names = int(llm_cfg.get("max_names_per_day", 10))
    horizon = int(llm_cfg.get("horizon_days", 20))
    result = {"tilts": {}, "minted": [], "status": "ok", "attempted": 0,
              "failed": 0}

    try:
        from backend.services import llm_research as R
        from backend.services import belief_state as B
    except ImportError as exc:
        result["status"] = f"import_failed: {exc}"
        return result

    ok, why = R.available()
    if not ok:
        result["status"] = f"llm_unavailable: {why}"
        return result

    already = _today_call_count(root)
    names = day_state.get("names", {})
    records = []
    for t in tickers[:max_names]:
        if already + result["attempted"] >= cap:
            result["status"] = "daily_cap_reached"
            break
        row = names.get(t)
        if not row or row.get("status") != "ok":
            continue
        state = {"ticker": t, "date": day_state.get("date"),
                 "close": row.get("close"), "ret21": row.get("ret21"),
                 "vol63": row.get("vol63"), "streak_up": row.get("streak_up"),
                 "pit_scores": row.get("scores")}
        prompt = (
            "You are the perception layer of a PAPER-TRADING experiment "
            "(PRODUCT_EXPERIMENT — no real capital, no advice). Given this "
            "frozen end-of-day state, state your belief revision for the "
            f"name.\n\nSTATE:\n{json.dumps(state, default=str)}")
        result["attempted"] += 1
        try:
            reply = R.ask(prompt, purpose="arena_perception",
                          max_tokens=400, schema_hint=_SCHEMA_HINT)
            parsed = R.parse_json_block(reply["text"]) or {}
            prior = float(parsed["prior"])
            posterior = float(parsed["posterior"])
            rec = B.make_prediction(
                ticker=t, specialist=SPECIALIST,
                observable=B.Observable.BEATS_BENCHMARK,
                horizon_days=horizon, probability=posterior,
                threshold=None, benchmark="SPY",
                thesis=str(parsed.get("thesis", ""))[:400],
                counter_thesis=str(parsed.get("counter_thesis", ""))[:400],
                next_observable=str(parsed.get("next_observable", ""))[:200],
                model=reply["call"].get("model", "deepseek"),
                model_version="arena-perception-v1",
                prompt=prompt, input_snapshot=state,
                prior=prior, posterior=posterior, arm="arena")
            records.append(rec)
            result["tilts"][t] = 1.0 + 2.0 * (posterior - prior)
            result["minted"].append({"ticker": t,
                                     "prediction_id": rec.prediction_id,
                                     "belief_change": rec.belief_change})
        except Exception as exc:  # noqa: BLE001 — one bad name never kills the pass
            result["failed"] += 1
            logger.warning("ARENA perception failed for %s: %s", t, exc)
    if records:
        # The arena path is not one of the declared evidence populations, so
        # append() leaves the population unstamped — arena records are
        # identified by specialist/arm, and they never enter predictions.jsonl.
        B.append(records, store.predictions_path(root))
    return result
