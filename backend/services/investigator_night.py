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

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend import config as _config
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

#: WHERE THE RECEIPTS LIVE — the same lesson as NIGHT-14 defect F7, and this
#: file had reproduced the bug it fixed. The receipt was written under the repo
#: while the ledger it describes lives on the persistent volume, so a Railway
#: deploy would keep every prediction and destroy the evidence of how it was
#: produced. Locally AEGIS_DATA_DIR is unset and this resolves to the same
#: backend/data path it always had.
RECEIPTS_DIR = _config.OPTIMUS_LEDGER_DIR / "iif1_nights"

#: Sandbox receipts never mix with production ones. A rehearsal that wrote into
#: the evidence directory would be indistinguishable from a real night later.
SANDBOX_RECEIPTS_DIR = _config.OPTIMUS_LEDGER_DIR / "iif1_nights_sandbox"

#: Reserved against the ceiling BEFORE a request is transmitted. Checking
#: `spent >= ceiling` after the fact permits one more call at $11.99 against a
#: $12 cap, and that call can carry the night past a ceiling described as hard.
#: Sized well above MARKET-GRAPH-1's measured $0.00073/call on document-sized
#: payloads so the reserve is genuinely worst-case rather than typical.
WORST_CASE_CALL_USD = 0.05

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
    cell_pairing: dict = field(default_factory=dict)
    #: True for a rehearsal/test. A sandbox night never reaches the evidence
    #: ledger and never writes a production receipt, and the flag is carried on
    #: the receipt so the two can never be confused after the fact.
    sandbox: bool = False
    elapsed_s: float = 0.0
    #: The minted records, in memory only. Deliberately EXCLUDED from
    #: `as_dict()` and therefore from the receipt: it carries priors and
    #: posteriors, and the receipt is read by a human every morning during a
    #: 40-night blind. Present so a rehearsal can inspect exactly what a
    #: production night would have written, without writing it.
    records: list = field(default_factory=list, repr=False)

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d.pop("records", None)
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
        # RESERVE the worst case before transmitting, rather than checking
        # `usd >= max_usd` after. The old form permitted one more call at
        # $11.99 against a $12 cap and that call could carry the night past a
        # ceiling the pre-registration calls hard.
        if usd + WORST_CASE_CALL_USD > max_usd:
            raise NightlyBudgetExhausted(
                f"nightly ceiling would be breached: ${usd:.4f} spent + "
                f"${WORST_CASE_CALL_USD:.4f} reserved for this call > "
                f"${max_usd:.2f} (spend read from served responses, never "
                f"estimated; the reserve is what makes the ceiling hard rather "
                f"than approximate)")
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


def cell_key(ticker: str, f: dict) -> tuple:
    """The unit the paired statistic is actually computed on.

    `night x ticker x observable x horizon x threshold`. Ticker-level pairing is
    not enough: malformed forecasts are dropped (correctly — coercing one is
    scoring a judgement nobody made), so arm A can hold NVDA/abs_move/5d/5%
    while arm B lost exactly that cell, and a ticker-level guard sees two arms
    that both "did NVDA". The difference is then a comparison of two different
    cell sets wearing the name of a paired test.
    """
    t = f.get("threshold")
    return (str(ticker), str(f.get("observable")), int(f.get("horizon_days", 0)),
            None if t is None else round(float(t), 6))


def _forecast_served_model(inv) -> str:
    """The model that served the FORECAST call specifically.

    `sorted(inv.served_models)[0]` returns whichever name sorts first across
    five microtasks. If the extractor and the forecaster were served different
    models — the exact failure that voided a model-diversity arm — the record
    would carry a model that did not make the forecast it is attached to.
    """
    for c in inv.calls:
        if getattr(c, "task", "") == "forecast" and c.served_model:
            return c.served_model
    return ""


def mint_records(inv, *, snapshot: dict, night: str,
                 allowed_cells: set | None = None) -> list[PredictionRecord]:
    """Forecasts -> ledger records under the belief-change contract.

    A cell the ledger cannot grade is DROPPED with a log line, never coerced.
    `allowed_cells`, when given, is the cross-arm intersection: a cell missing
    from any arm is removed from EVERY arm, symmetrically, so the comparison
    stays paired.
    """
    out: list[PredictionRecord] = []
    served = _forecast_served_model(inv)
    dossier_sha = hashlib.sha256(
        (inv.dossier or "").encode("utf-8")).hexdigest()
    for f in inv.forecasts:
        if allowed_cells is not None and cell_key(inv.ticker, f) not in allowed_cells:
            continue
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
                model_version=served or REQUEST_MODEL,
                prompt=f"{TRIAL}:{inv.arm}:{night}",
                input_snapshot={"snapshot": snapshot, "arm": inv.arm,
                                # SHA-256, not `hash()`: Python's hash is salted
                                # per process, so the same dossier produced a
                                # different "identifier" on every run and the
                                # field could never link a record to its input.
                                "dossier_sha256": dossier_sha,
                                "all_served_models": sorted(inv.served_models)}))
        except ValueError as exc:
            logger.warning("[%s/%s] record refused by the ledger: %s",
                           inv.arm, inv.ticker, exc)
    return out


class SandboxRequired(RuntimeError):
    """A production invocation carried something only a sandbox may carry."""


def assert_production_invocation(*, k: int, arms: tuple[str, ...],
                                 max_usd: float,
                                 llm_call: Callable | None,
                                 tool_runner: Callable | None) -> dict:
    """The EFFECTIVE invocation must equal the registered rule.

    `verify_or_refuse()` compares module CONSTANTS against the frozen config.
    It cannot see arguments. So this was possible and passed every check:

        run_night(k=10, arms=("A_snapshot", "B_tools"), max_usd=100)

    — the verifier reads `TRIGGERS_PER_NIGHT == 40`, `ARMS` complete and
    `NIGHTLY_MAX_USD == 12.00`, reports the trial as registered, and the run
    then executes ten triggers across two arms at a hundred dollars. A frozen
    parameter that a caller can override is not frozen; it is a default.

    Injected dependencies are refused on the same footing. An injected
    `llm_call` skipped pre-registration verification on the theory that it
    spends nothing — but `dry_run` defaults to False, so a caller could pass a
    real paid client through that argument and write the evidence ledger with
    no verification at all. `tool_runner` is the same hole for tools.
    """
    from backend.services.iif1_prereg import verify_or_refuse
    frozen = verify_or_refuse()

    bad = []
    if llm_call is not None:
        bad.append("llm_call was injected — a production night uses the frozen "
                   "budget-gated client and nothing else")
    if tool_runner is not None:
        bad.append("tool_runner was injected — a production night uses the "
                   "frozen tool layer and nothing else")
    if int(k) != int(frozen["TRIGGERS_PER_NIGHT"]):
        bad.append(f"k={k} overrides the registered "
                   f"TRIGGERS_PER_NIGHT={frozen['TRIGGERS_PER_NIGHT']}")
    if tuple(arms) != tuple(frozen["ARMS"]):
        bad.append(f"arms={tuple(arms)} overrides the registered "
                   f"ARMS={tuple(frozen['ARMS'])}")
    if float(max_usd) != float(frozen["NIGHTLY_MAX_USD"]):
        bad.append(f"max_usd={max_usd} overrides the registered "
                   f"NIGHTLY_MAX_USD={frozen['NIGHTLY_MAX_USD']}")
    if bad:
        raise SandboxRequired(
            "this invocation cannot accrue against "
            f"{TRIAL}:\n  - " + "\n  - ".join(bad) +
            "\n\nPass sandbox=True to run it anyway. A sandbox run may "
            "override anything and can NEVER write the evidence ledger.")
    return frozen


def run_night(features_by_ticker: dict[str, dict], *,
              snapshots: dict[str, dict] | None = None,
              k: int = TR.TRIGGERS_PER_NIGHT,
              arms: tuple[str, ...] = ARMS,
              llm_call: Callable | None = None,
              tool_runner: Callable | None = None,
              dry_run: bool = False,
              sandbox: bool = False,
              max_usd: float = NIGHTLY_MAX_USD,
              balance_usd: float = DEFAULT_BALANCE_USD,
              night: str | None = None) -> NightResult:
    """One night, end to end.

    TWO MODES, AND THE SEPARATION IS THE POINT
    ------------------------------------------
    **Production** (`sandbox=False`, the default): every frozen parameter must
    equal the registered rule, dependencies may not be injected, the
    pre-registration must be readable, and the run may write the forward
    evidence ledger.

    **Sandbox** (`sandbox=True`): override anything, inject anything, run with
    no sibling tree — and it can never write the evidence ledger or a
    production receipt, whatever `dry_run` says. Rehearsals and tests live
    here.

    Before this split, dependency injection and production accrual shared one
    path, so a rehearsal was one default argument away from writing forward
    evidence.
    """
    t0 = time.perf_counter()
    night = night or str(date.today())
    since_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res = NightResult(night=night)
    res.sandbox = bool(sandbox)

    if not sandbox:
        assert_production_invocation(k=k, arms=arms, max_usd=max_usd,
                                     llm_call=llm_call,
                                     tool_runner=tool_runner)

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
    per_arm_inv: dict[str, list] = {}
    per_arm_snaps: dict[str, dict] = {}
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
        rows, done, invs = [], [], []
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
            invs.append(inv)
            per_arm_snaps.setdefault(arm, {})[tkr] = snap
        per_arm_tickers[arm] = done
        per_arm_inv[arm] = invs
        res.per_arm[arm] = {
            "n_cells": len(done),
            "n_with_forecasts": sum(1 for r in rows if r["n_forecasts"] > 0),
            "n_tool_calls": sum(r["n_tool_calls"] for r in rows),
            "rows": rows,
        }
        if stopped:
            break

    # ── the pairing guards ──────────────────────────────────────────────────
    # A partial night written to the ledger would look like data. If the arms
    # diverged, nothing is minted and the reason is recorded.
    all_records: list[PredictionRecord] = []
    try:
        TR.assert_arms_share_cells(per_arm_tickers)
    except ValueError as exc:
        res.status = "void"
        res.void_reason = str(exc)

    # Ticker-level agreement is necessary and NOT sufficient. Malformed
    # forecasts are dropped, so two arms can hold the same tickers and
    # different gradeable cells. Only the cross-arm INTERSECTION is minted, and
    # a cell missing anywhere is dropped everywhere — symmetrically, so the
    # removal cannot favour an arm.
    if res.status == "ok" and per_arm_inv:
        per_arm_keys = {
            arm: {cell_key(i.ticker, f) for i in invs for f in i.forecasts}
            for arm, invs in per_arm_inv.items()}
        shared: set = set.intersection(*per_arm_keys.values()) \
            if per_arm_keys else set()
        union: set = set().union(*per_arm_keys.values()) if per_arm_keys else set()

        # Differential drop rates are themselves an architectural result: an arm
        # that returns malformed JSON more often is telling us something about
        # the arm, so this is reported rather than silently repaired.
        res.cell_pairing = {
            "n_cells_union": len(union),
            "n_cells_paired": len(shared),
            "n_cells_dropped_unpaired": len(union - shared),
            "per_arm": {arm: {"n_cells": len(ks),
                              "n_dropped_for_pairing": len(ks - shared)}
                        for arm, ks in per_arm_keys.items()},
            "key": "night x ticker x observable x horizon_days x threshold",
        }
        if not shared:
            res.status = "void"
            res.void_reason = (
                f"no forecast cell survived cross-arm intersection "
                f"({len(union)} cells produced across {len(per_arm_keys)} arms, "
                f"0 held by all) — there is nothing paired to compare")
        else:
            for arm, invs in per_arm_inv.items():
                snaps = per_arm_snaps.get(arm, {})
                for i in invs:
                    if i.forecasts:
                        all_records.extend(mint_records(
                            i, snapshot=snaps.get(i.ticker, {}), night=night,
                            allowed_cells=shared))

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

    # THE EVIDENCE LEDGER IS PRODUCTION-ONLY. `sandbox` outranks every other
    # condition here: a rehearsal with a stubbed client must not be able to
    # write forward evidence by forgetting `dry_run=True`.
    res.records = all_records
    if all_records and not sandbox and not dry_run and res.status == "ok":
        from backend.services import belief_state
        belief_state.append(all_records)
        res.records_written = len(all_records)
    elif all_records:
        res.records_written = 0

    res.elapsed_s = time.perf_counter() - t0
    if not dry_run:
        out_dir = SANDBOX_RECEIPTS_DIR if sandbox else RECEIPTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{night}.json").write_text(
            json.dumps(res.as_dict(), indent=2, default=str), encoding="utf-8")
    return res
