"""INTERNET-INVESTIGATOR-FWD-1 — one night, all five arms, one receipt.

Pre-registration: `Aegis module/TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md`.
Frozen parameters: `Aegis module/scripts/iif1_config.py`.

WHAT ONE NIGHT IS
=================
    1. score the universe and take the top k unusual names   (numerical, no LLM)
    2. hand THE SAME k names to every arm                    (this is the trial)
    3. each arm runs the microtask chain and returns forecasts
    4. assert every arm saw identical cells, or VOID the night
    5. mint prediction records under the belief-change contract
    6. append to the forward ledger and write a receipt

TWO CEILINGS, NOT ONE
---------------------
`research_budget.require()` is the standing campaign governor and is consulted
before every vendor request including retries. On top of it this runner holds
its own NIGHTLY ceiling, measured from the telemetry ledger — the same
belt-and-braces MARKET-GRAPH-1 used, for the same reason: the campaign gate is
sized for a campaign, and a runaway night could spend a fortnight's allowance
without ever tripping it.

Spend is READ FROM SERVED RESPONSES via the telemetry ledger, never estimated
from a price table. GRAND-ARENA halted a run at "estimated spend $40.00 >=
$40.00" computed from a stale price table that overstated cost 2.8x; true spend
at that moment was $12.57.

THE NIGHT IS VOID RATHER THAN PARTIAL
-------------------------------------
If the arms did not see identical cells, the paired Brier statistic silently
stops being paired. A partial night written to the ledger would look like data.
So a divergence raises, the night is recorded as void with its reason, and
nothing is minted.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.services import investigator_tools as IT
from backend.services import investigator_triggers as TR
from backend.services.belief_state import (Observable, PredictionRecord,
                                           make_prediction)
from backend.services.investigator_agent import Investigator

logger = logging.getLogger(__name__)

TRIAL = "INTERNET-INVESTIGATOR-FWD-1"
CAMPAIGN = "brain_v3"

ARMS = ("A_snapshot", "B_tools", "C_tools_only", "D_all", "B_anon")
NIGHTLY_MAX_USD = 12.00
NIGHTLY_MAX_CALLS = 3_000
REQUEST_MODEL = "deepseek-v4-flash"
BENCHMARK = "SPY"

RECEIPTS_DIR = (Path(__file__).resolve().parents[2] / "backend" / "data"
                / "optimus" / "iif1_nights")

# ── the funding arithmetic ──────────────────────────────────────────────────
# $10-15 is a SAFETY CEILING, not a planning budget, and the distinction is the
# whole point. The planning number is the funding average: the balance divided
# by the nights the design must survive. A $4 night is not "under budget" — it
# is nine fundable nights out of forty, and the accrual clock cannot honestly
# start until that arithmetic has been looked at.
GRADED_NIGHTS_TO_FIRST_LOOK = 40
#: DeepSeek console balance, read by Murat 2026-08-14. Passed in per-run where a
#: fresher figure exists; this is the dated default so the projection is never
#: silently computed against nothing.
DEFAULT_BALANCE_USD = 37.12
BALANCE_AS_OF = "2026-08-14"

#: Map the agent's observable strings onto the ledger enum. A cell the ledger
#: cannot grade is dropped rather than coerced.
_OBSERVABLE = {
    "abs_move_exceeds": Observable.ABS_MOVE_EXCEEDS,
    "return_sign": Observable.RETURN_SIGN,
    "beats_benchmark": Observable.BEATS_BENCHMARK,
}


class NightlyBudgetExhausted(IT.BudgetExhausted):
    """This night's own ceiling, distinct from the campaign governor.

    Subclasses `BudgetExhausted` so the agent recognises it as "stop" rather
    than "this cell failed". Before that inheritance existed, the agent's
    per-task `except Exception` swallowed it and the night kept calling the
    vendor after the ceiling had tripped — logging a warning per call. Caught
    by `test_budget_exhaustion_mid_night_marks_the_night_rather_than_pretending`.
    """


@dataclass
class NightResult:
    night: str
    status: str = "ok"                  # ok | void | budget_stopped
    void_reason: str = ""
    tickers: list[str] = field(default_factory=list)
    trigger_report: dict = field(default_factory=dict)
    per_arm: dict = field(default_factory=dict)
    records_written: int = 0
    calls: int = 0
    spend_usd: float = 0.0
    served_models: list[str] = field(default_factory=list)
    budget: dict = field(default_factory=dict)
    elapsed_s: float = 0.0

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["trial"] = TRIAL
        return d


def project_funding(measured_cost_usd: float, *,
                    balance_usd: float = DEFAULT_BALANCE_USD,
                    nights: int = GRADED_NIGHTS_TO_FIRST_LOOK,
                    ceiling_usd: float = NIGHTLY_MAX_USD) -> dict:
    """What this night's measured cost implies for the whole accrual.

    The four numbers the referee required after night one, computed rather than
    asserted. `fundable_nights` is the one that actually decides anything: it
    converts a per-night figure into the only currency the design cares about,
    which is how many of the forty nights the balance reaches.

    A measured cost of exactly zero is reported as `unknown`, not as free — a
    telemetry read that failed and a genuinely free night must not arrive as the
    same value (the house failure mode, and this trial's own tool-layer lesson).
    """
    known = measured_cost_usd is not None and measured_cost_usd > 0
    projected = float(measured_cost_usd) * nights if known else None
    funding_average = balance_usd / nights if nights else float("nan")
    return {
        "measured_cost_night_1": (round(float(measured_cost_usd), 6)
                                  if known else None),
        "measured_cost_status": "measured" if known else "unknown",
        "projected_40_night_cost": (round(projected, 4)
                                    if projected is not None else None),
        "current_balance": round(float(balance_usd), 4),
        "balance_as_of": BALANCE_AS_OF,
        "funding_gap_or_surplus": (round(balance_usd - projected, 4)
                                   if projected is not None else None),
        "fundable_nights_at_this_rate": (
            int(balance_usd // measured_cost_usd) if known else None),
        "nights_required": nights,
        "funding_average_per_night": round(funding_average, 4),
        "safety_ceiling_per_night": float(ceiling_usd),
        "note": ("The ceiling is a stop, not a plan. The planning number is "
                 "funding_average_per_night; a night under the ceiling but "
                 "over the average shortens the trial rather than fitting in "
                 "it. The funding decision is made BEFORE the accrual clock "
                 "starts, not when the balance runs out."),
    }


def _spend_since(since_iso: str) -> tuple[float, int]:
    """(usd, calls) from the telemetry ledger since `since_iso`.

    Raises on a read failure rather than returning zero: a telemetry read that
    fails and reports free would disarm the nightly ceiling at exactly the
    moment it is needed.
    """
    from backend.services import llm_telemetry
    s = llm_telemetry.spend(since=since_iso)
    if not s:
        raise NightlyBudgetExhausted(
            "telemetry ledger unreadable — nightly spend is UNKNOWN, not zero; "
            "refusing to continue rather than spend blind")
    return float(s.get("cost_usd", 0.0) or 0.0), int(s.get("n_calls", 0) or 0)


def make_llm_call(*, since_iso: str, max_usd: float = NIGHTLY_MAX_USD,
                  max_calls: int = NIGHTLY_MAX_CALLS,
                  counter: dict | None = None) -> Callable:
    """A budget-gated LLM call the agent can be handed.

    Two gates fire before every request: the campaign governor inside
    `default_llm_call`, and this night's own ceiling read from served responses.
    """
    from backend.services.llm_swarm import default_llm_call

    def call(*, system: str, user: str, model: str = REQUEST_MODEL,
             temperature: float = 0.0, max_tokens: int = 1600):
        usd, n = _spend_since(since_iso)
        if usd >= max_usd:
            raise NightlyBudgetExhausted(
                f"nightly ceiling reached: ${usd:.4f} >= ${max_usd:.2f} "
                f"(read from served responses, not estimated)")
        if n >= max_calls:
            raise NightlyBudgetExhausted(
                f"nightly call ceiling reached: {n} >= {max_calls}")
        reply = default_llm_call(system, user, model=model,
                                 temperature=temperature,
                                 max_tokens=max_tokens, campaign=CAMPAIGN,
                                 since=since_iso)
        if counter is not None:
            counter["calls"] = counter.get("calls", 0) + 1
            served = str(getattr(reply, "model_version", "") or "")
            counter.setdefault("served", set()).add(served)
        _record_telemetry(reply, model=model, system=system, user=user)
        return reply

    return call


def _record_telemetry(reply: Any, *, model: str, system: str,
                      user: str) -> None:
    """One telemetry row per vendor call, with the SERVED model.

    The API silently aliases — `deepseek-chat` and `deepseek-reasoner` were both
    served as `v4-flash`, which voided an entire model-diversity arm. The served
    name is read off the response body every time and it is what the row
    carries.
    """
    try:
        from backend.services import llm_telemetry
        llm_telemetry.record_call(
            provider="deepseek", model=model, purpose=TRIAL, agent=TRIAL,
            model_version=str(getattr(reply, "model_version", "") or model),
            prompt=system + user,
            tokens_in=int(getattr(reply, "tokens_in", 0) or 0),
            tokens_out=int(getattr(reply, "tokens_out", 0) or 0),
            cached_tokens=int(getattr(reply, "cached_tokens", 0) or 0),
            latency_ms=getattr(reply, "latency_ms", None),
            retries=int(getattr(reply, "retries", 0) or 0),
            meta={"trial": TRIAL})
    except Exception as exc:                                   # noqa: BLE001
        # Loud, and it matters: the ledger this writes to is the same one the
        # nightly ceiling reads from, so a silent telemetry failure would make
        # the night look cheaper than it is and let it overspend.
        logger.error("TELEMETRY WRITE FAILED for %s (%s: %s) — the nightly "
                     "ceiling now under-counts this call", TRIAL,
                     type(exc).__name__, exc)


def mint_records(inv, *, snapshot: dict, night: str) -> list[PredictionRecord]:
    """Forecasts -> ledger records under the belief-change contract.

    A cell the ledger cannot grade is DROPPED with a log line, never coerced.
    """
    out: list[PredictionRecord] = []
    for f in inv.forecasts:
        obs = _OBSERVABLE.get(f["observable"])
        if obs is None:
            logger.warning("[%s] unmappable observable %r dropped",
                           inv.arm, f["observable"])
            continue
        try:
            out.append(make_prediction(
                ticker=inv.ticker, specialist=f"investigator:{inv.arm}",
                observable=obs, horizon_days=int(f["horizon_days"]),
                probability=float(f["posterior"]),
                prior=float(f["prior"]), posterior=float(f["posterior"]),
                arm=inv.arm,
                threshold=f.get("threshold"),
                benchmark=(BENCHMARK if obs is Observable.BEATS_BENCHMARK
                           else None),
                thesis=(f.get("rationale") or "no rationale given")[:800],
                counter_thesis=((inv.critique or {}).get("strongest_objection")
                                or "no critique returned")[:800],
                next_observable=((inv.event or {}).get("what_changed")
                                 or "unspecified")[:400],
                model=REQUEST_MODEL,
                model_version=(sorted(inv.served_models)[0]
                               if inv.served_models else REQUEST_MODEL),
                prompt=f"{TRIAL}:{inv.arm}:{night}",
                input_snapshot={"snapshot": snapshot, "arm": inv.arm,
                                "dossier_hash": hash(inv.dossier)}))
        except ValueError as exc:
            logger.warning("[%s/%s] record refused by the ledger: %s",
                           inv.arm, inv.ticker, exc)
    return out


def run_night(features_by_ticker: dict[str, dict], *,
              snapshots: dict[str, dict] | None = None,
              k: int = TR.TRIGGERS_PER_NIGHT,
              arms: tuple[str, ...] = ARMS,
              llm_call: Callable | None = None,
              tool_runner: Callable | None = None,
              dry_run: bool = False,
              max_usd: float = NIGHTLY_MAX_USD,
              balance_usd: float = DEFAULT_BALANCE_USD,
              night: str | None = None) -> NightResult:
    """One night, end to end. Writes nothing when `dry_run`."""
    t0 = time.perf_counter()
    night = night or str(date.today())
    since_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res = NightResult(night=night)

    sel = TR.select_triggers(features_by_ticker, k=k)
    res.trigger_report = {kk: vv for kk, vv in sel.items()
                          if kk not in ("selected", "excluded")}
    res.tickers = list(sel["tickers"])
    if not res.tickers:
        res.status = "void"
        res.void_reason = "no eligible triggers tonight"
        res.elapsed_s = time.perf_counter() - t0
        return res

    counter: dict = {"calls": 0, "served": set()}
    call = llm_call or make_llm_call(since_iso=since_iso, max_usd=max_usd,
                                     counter=counter)

    per_arm_tickers: dict[str, list[str]] = {}
    all_records: list[PredictionRecord] = []
    stopped = ""

    # The cell set is frozen ONCE, here, before a single vendor call. Everything
    # below iterates this tuple and nothing may re-derive it.
    cells = tuple(res.tickers)

    for arm in arms:
        # Equality asserted BEFORE the calls as well as after them. The check at
        # the end catches an arm that dropped cells while running; this one
        # catches an arm that was handed the wrong ones to begin with — and it
        # catches it before any money is spent, rather than after five arms have
        # been paid for and the night is void anyway.
        arm_cells = list(cells)
        try:
            TR.assert_arms_share_cells({"__frozen_trigger_set__": list(cells),
                                        arm: arm_cells})
        except ValueError as exc:
            # VOID, not a crash. A traceback out of the nightly runner is an
            # ops incident that loses the receipt; a void night with its reason
            # on disk is a record. Same outcome for the trial, different
            # outcome for knowing why.
            res.status = "void"
            res.void_reason = f"pre-call cell check failed for {arm}: {exc}"
            logger.error("[%s] %s", arm, res.void_reason)
            break

        agent = Investigator(arm, llm_call=call,
                             tool_runner=tool_runner or IT.run_tool,
                             model=REQUEST_MODEL)
        rows, done = [], []
        for tkr in arm_cells:
            snap = (snapshots or {}).get(tkr, {})
            try:
                inv = agent.investigate(tkr, snap)
            except NightlyBudgetExhausted as exc:
                stopped = str(exc)
                logger.warning("[%s] nightly budget stopped the run: %s",
                               arm, exc)
                break
            rows.append(inv.as_row())
            done.append(tkr)
            if inv.forecasts:
                all_records.extend(mint_records(inv, snapshot=snap,
                                                night=night))
        per_arm_tickers[arm] = done
        res.per_arm[arm] = {
            "n_cells": len(done),
            "n_with_forecasts": sum(1 for r in rows if r["n_forecasts"] > 0),
            "n_tool_calls": sum(r["n_tool_calls"] for r in rows),
            "rows": rows,
        }
        if stopped:
            break

    # ── the pairing guard ───────────────────────────────────────────────────
    # A partial night written to the ledger would look like data. If the arms
    # diverged, nothing is minted and the reason is recorded.
    try:
        TR.assert_arms_share_cells(per_arm_tickers)
    except ValueError as exc:
        res.status = "void"
        res.void_reason = str(exc)
        all_records = []

    if stopped and res.status == "ok":
        res.status = "budget_stopped"
        res.void_reason = stopped

    try:
        res.spend_usd, res.calls = _spend_since(since_iso)
    except NightlyBudgetExhausted as exc:
        res.spend_usd, res.calls = -1.0, counter.get("calls", 0)
        logger.error("could not read this night's spend: %s", exc)
    res.served_models = sorted(m for m in counter.get("served", set()) if m)
    res.budget = project_funding(res.spend_usd, balance_usd=balance_usd)

    if all_records and not dry_run and res.status == "ok":
        from backend.services import belief_state
        belief_state.append(all_records)
        res.records_written = len(all_records)
    elif all_records:
        res.records_written = 0

    res.elapsed_s = time.perf_counter() - t0
    if not dry_run:
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        (RECEIPTS_DIR / f"{night}.json").write_text(
            json.dumps(res.as_dict(), indent=2, default=str), encoding="utf-8")
    return res
