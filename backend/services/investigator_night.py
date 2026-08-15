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
#: DeepSeek console balance. Passed in per-run where a fresher figure exists;
#: this is the dated default so the projection is never silently computed
#: against nothing.
#:
#: 2026-08-15: $37.12 + Murat's $20 top-up = $57.12, ratified in the brain's
#: order (§3, "FUNDED, proceed"). Updated here rather than left to a CLI flag
#: because a stale default is what the projection quietly uses when nobody
#: passes one, and the whole point of the funding rule is that it decides
#: against a real number. NOT part of the frozen pre-registration — checked
#: before changing it, because a change to a frozen field would REFUSE the
#: night rather than merely misreport it.
DEFAULT_BALANCE_USD = 57.12
BALANCE_AS_OF = "2026-08-15"

#: How many cells in a row may produce NO gradeable forecast before the night
#: stops. This is the information guard the campaign governor's zero-yield rule
#: cannot be for a chain campaign: that rule is consulted per CALL and a cell's
#: yield is not knowable until every arm has finished, so applied here it fired
#: at 100% on every night regardless of what the model returned. The unit that
#: can actually yield or not yield is the CELL, and five barren ones in a row is
#: a night that is buying tokens — the same judgement, at the unit that supports
#: it. Deliberately not a fraction: the first cells are the cheap place to find
#: out, and a ratio only crosses its threshold once the money is spent.
MAX_BARREN_CELLS = 5

#: Fraction of a night's cells that may die at the TOKEN CEILING before the
#: night is void.
#:
#: Distinct from `MAX_BARREN_CELLS`, which is a money guard: it asks "is this
#: night buying tokens and getting nothing", and five barren cells in a row is
#: a cheap place to find out. This is an INTEGRITY guard and it asks a different
#: question: "are the cells that survived a fair sample of the cells we tried".
#:
#: Truncation is not a random tax. An arm that gathers more evidence writes
#: longer prompts, thinks longer, and truncates more — so a night can lose most
#: of `B_tools` while keeping most of `A_snapshot` and still hand the paired
#: statistic a full-looking, silently biased cell set. Night 1 was doing exactly
#: that (`B_tools` 8/10 barren vs `A_snapshot` 15/40) and nothing would have
#: said so. Set low deliberately: with the ceiling correctly sized, truncation
#: should be rare, and a night where it is not is a night whose configuration
#: has drifted, not a night with slightly less data.
MAX_TRUNCATION_RATE = 0.05

#: Minutes a production night may start AFTER the decision timestamp its
#: snapshot was frozen at.
#:
#: The tool layer states its own rule plainly: "the trial is forward-only, so
#: *now* is point-in-time by construction". The tools read the live internet at
#: the moment they are called. That is only equivalent to the record's
#: `decision_ts` if the night runs close to it. Start a night three hours after
#: its snapshot and the four tool-bearing arms have three hours of hindsight on
#: a one-day horizon, stamped with a decision time before the market opened —
#: which is not a slow night, it is a forecast made with the answer partly in
#: view.
#:
#: Nothing enforced this. Night 1 happened to run 16 minutes after its snapshot,
#: so the protocol held by luck and habit rather than by construction.
MAX_DECISION_LAG_MINUTES = 45


class DecisionTimeStale(RuntimeError):
    """The snapshot is older than a production night may act on."""


def assert_decision_time_fresh(decision_ts, *, now=None,
                               max_lag_minutes: int = MAX_DECISION_LAG_MINUTES
                               ) -> float:
    """Refuse a paying night whose snapshot has gone stale. Returns lag minutes.

    Deliberately a REFUSAL rather than a warning, and deliberately before the
    first vendor call. A night that discovers this afterwards has already
    bought the contaminated forecasts.
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(decision_ts, str):
        decision_ts = datetime.fromisoformat(decision_ts)
    if decision_ts.tzinfo is None:
        decision_ts = decision_ts.replace(tzinfo=timezone.utc)
    lag = (now - decision_ts).total_seconds() / 60.0
    if lag > max_lag_minutes:
        raise DecisionTimeStale(
            f"the frozen snapshot's decision_ts is {lag:.0f} minutes old "
            f"(limit {max_lag_minutes}). The tool-bearing arms read the live "
            f"internet, so they would investigate a world {lag:.0f} minutes "
            f"newer than the timestamp their forecasts are graded from — "
            f"hindsight on the horizon, handed specifically to the arms under "
            f"test. Freeze a new snapshot and run the night against it.")
    return lag

#: Map the agent's observable strings onto the ledger enum. A cell the ledger
#: cannot grade is dropped rather than coerced.
_OBSERVABLE = {
    "abs_move_exceeds": Observable.ABS_MOVE_EXCEEDS,
    "return_sign": Observable.RETURN_SIGN,
    "beats_benchmark": Observable.BEATS_BENCHMARK,
}


#: The one encoding any receipt or ledger this trial writes is ever opened
#: with, on BOTH sides. Night 1's void reason came back mojibaked on read, and
#: the file was clean UTF-8 the whole time — the damage was a cp1252 default on
#: the reading end. Pinning only the write side would have left that intact.
RECEIPT_ENCODING = "utf-8"


def read_receipt(night: str, *, sandbox: bool = False) -> dict:
    """Read a night's receipt. UTF-8, explicitly, always."""
    d = SANDBOX_RECEIPTS_DIR if sandbox else RECEIPTS_DIR
    return json.loads((d / f"{night}.json").read_text(encoding=RECEIPT_ENCODING))


def amend_receipt(night: str, amendment: dict, *,
                  sandbox: bool = False) -> dict:
    """Append a dated correction to a receipt WITHOUT altering what it said.

    The original fields stay exactly as the night wrote them — including a
    `spend_usd: 0.0` that is now known to be wrong. Overwriting it would erase
    the evidence that the ceiling had been unarmed, which is the finding; the
    receipt has to be able to say "I reported zero, and here is why that was
    false" rather than quietly become correct.

    Amendments accumulate in order and are never rewritten in place.
    """
    d = SANDBOX_RECEIPTS_DIR if sandbox else RECEIPTS_DIR
    path = d / f"{night}.json"
    receipt = json.loads(path.read_text(encoding=RECEIPT_ENCODING))
    row = dict(amendment)
    row.setdefault("amended_at",
                   datetime.now(timezone.utc).isoformat(timespec="seconds"))
    prior = list(receipt.get("amendments") or [])
    row.setdefault("seq", len(prior) + 1)
    receipt["amendments"] = prior + [row]
    path.write_text(json.dumps(receipt, indent=2, default=str),
                    encoding=RECEIPT_ENCODING)
    return receipt


def measured_spend_for_night(night: str) -> tuple[float, int]:
    """(usd, n_calls) this trial actually spent on `night`, from telemetry.

    Read from the served-response ledger by trial and date, which is the only
    place Night 1's cost survived: the receipt said $0.00 because the ceiling
    was reading a key `spend()` has never returned.
    """
    from backend.services import llm_telemetry
    rows = [r for r in llm_telemetry.read_calls()
            if r.get("row_type") != "amendment"
            and str(r.get("ts", ""))[:10] == night
            and r.get("purpose") == TRIAL]
    return (round(sum(float(r.get("cost_usd") or 0.0) for r in rows), 8),
            len(rows))


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
    #: What the telemetry ledger was told each cell's calls jointly minted.
    #: `n_chains_minted_nothing` is the honest zero-yield count for the night.
    chain_yield: dict = field(default_factory=dict)
    #: How many cells died at the token ceiling, per arm. On EVERY receipt,
    #: including clean nights: the number that matters is that it stayed near
    #: zero, and a field that only appears when it is bad teaches the reader to
    #: assume its absence means fine.
    truncation: dict = field(default_factory=dict)
    #: Minutes between the snapshot's decision_ts and the night starting. On the
    #: receipt because it bounds how much of the horizon the tool arms could
    #: already see.
    decision_lag_minutes: float | None = None
    #: The same quantity measured when the LAST cell finished.
    #:
    #: `decision_lag_minutes` is checked once, before the first paid call, and
    #: that is correct — a guard that aborts halfway has bought contaminated
    #: forecasts and thrown away the night as well. But it means a night that
    #: STARTS 30 minutes stale and RUNS for 60 ends with its tool arms reading
    #: a world 90 minutes newer than the timestamp their forecasts are graded
    #: from, and the guard reported 30. The exposure is differential — the tool
    #: arms get it, the snapshot arm does not — which is the same bias
    #: structure that voided Night 1, so it is measured on every receipt rather
    #: than argued about. No behaviour depends on it yet; the number has to
    #: exist before anyone can say what an acceptable value is.
    decision_lag_minutes_at_end: float | None = None
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


#: The key `llm_telemetry.spend()` actually returns the money under. Named as a
#: constant because reading the WRONG key is not an error anywhere — it returns
#: None, `or 0.0` turns that into a number, and a ceiling that compares against
#: zero passes forever. Night 1 spent $0.0665 and reported $0.00.
SPEND_KEY = "total_cost_usd"


def _spend_since(since_iso: str, *, purpose: str | None = None,
                 path=None) -> tuple[float, int]:
    """(usd, calls) from the telemetry ledger since `since_iso`.

    Raises on a read failure rather than returning zero: a telemetry read that
    fails and reports free would disarm the nightly ceiling at exactly the
    moment it is needed.

    AND IT RAISES ON A MISSING KEY, for the same reason. This function read
    `s["cost_usd"]` — a key `spend()` has never returned — so every ceiling
    check compared `0.00 + 0.05 > $12.00` and the nightly USD ceiling was
    decorative from the day it was written. It was found because Night 1's
    funding block, the entire point of the night, printed `measured_cost:
    unknown` while the telemetry ledger held 224 priced rows totalling $0.0665.
    A default of 0.0 is what let a typo become an unarmed ceiling; there is now
    no default.
    """
    from backend.services import llm_telemetry
    s = llm_telemetry.spend(since=since_iso, purpose=purpose, path=path)
    if not s:
        raise NightlyBudgetExhausted(
            "telemetry ledger unreadable — nightly spend is UNKNOWN, not zero; "
            "refusing to continue rather than spend blind")
    if SPEND_KEY not in s:
        raise NightlyBudgetExhausted(
            f"the telemetry summary has no {SPEND_KEY!r} (got {sorted(s)}) — "
            f"nightly spend is UNKNOWN, not zero, and a ceiling that cannot "
            f"read spend must stop the night rather than wave it through")
    return float(s[SPEND_KEY] or 0.0), int(s.get("n_calls", 0) or 0)


#: A rehearsal's telemetry. Separate FILE, not a suppressed write: the chain
#: bookkeeping — mint an id, collect it under a chain, amend it with what the
#: chain produced — is the machinery that was wrong on Night 1, and a rehearsal
#: that skipped it would be simulating everything except the part that broke.
#: Writing it into the real ledger instead would put $0.00 rows for calls that
#: never happened beside the rows the funding rule reads.
SANDBOX_TELEMETRY = _config.OPTIMUS_LEDGER_DIR / "llm_calls_sandbox.jsonl"


def make_llm_call(*, since_iso: str, max_usd: float = NIGHTLY_MAX_USD,
                  max_calls: int = NIGHTLY_MAX_CALLS,
                  counter: dict | None = None,
                  chain: dict | None = None,
                  transport: Callable | None = None,
                  telemetry_path=None) -> Callable:
    """A budget-gated LLM call the agent can be handed.

    Two gates fire before every request: the campaign governor inside
    `default_llm_call`, and this night's own ceiling read from served responses.

    `chain`, when given, is the runner's live cursor: `chain["id"]` is the cell
    currently being investigated and `chain["calls"]` collects the telemetry ids
    each cell produced, so the night can tell the ledger afterwards what those
    five calls jointly minted. Without it every row of a chain campaign reads as
    zero-yield forever — see `llm_telemetry._yield_pending`.
    """
    from backend.services.llm_swarm import default_llm_call

    def call(*, system: str, user: str, model: str = REQUEST_MODEL,
             temperature: float = 0.0, max_tokens: int = 1600):
        usd, n = _spend_since(since_iso, path=telemetry_path)
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
        if transport is None:
            reply = default_llm_call(system, user, model=model,
                                     temperature=temperature,
                                     max_tokens=max_tokens, campaign=CAMPAIGN,
                                     since=since_iso)
        else:
            reply = transport(system=system, user=user, model=model,
                              temperature=temperature, max_tokens=max_tokens)
        if counter is not None:
            counter["calls"] = counter.get("calls", 0) + 1
            served = str(getattr(reply, "model_version", "") or "")
            counter.setdefault("served", set()).add(served)
        _record_telemetry(reply, model=model, system=system, user=user,
                          chain=chain, path=telemetry_path)
        return reply

    return call


def _record_telemetry(reply: Any, *, model: str, system: str,
                      user: str, chain: dict | None = None,
                      path=None) -> None:
    """One telemetry row per vendor call, with the SERVED model.

    The API silently aliases — `deepseek-chat` and `deepseek-reasoner` were both
    served as `v4-flash`, which voided an entire model-diversity arm. The served
    name is read off the response body every time and it is what the row
    carries.
    """
    try:
        from backend.services import llm_telemetry
        chain_id = (chain or {}).get("id")
        meta = {"trial": TRIAL}
        if chain_id:
            # Declared, not inferred. The ledger has no way to know that five
            # rows are one unit of work unless the call site says so.
            meta.update({"yield_unit": llm_telemetry.YIELD_UNIT_CHAIN,
                         "chain_id": chain_id})
        row = llm_telemetry.build_call(
            provider="deepseek", model=model, purpose=TRIAL, agent=TRIAL,
            model_version=str(getattr(reply, "model_version", "") or model),
            prompt=system + user,
            tokens_in=int(getattr(reply, "tokens_in", 0) or 0),
            tokens_out=int(getattr(reply, "tokens_out", 0) or 0),
            cached_tokens=int(getattr(reply, "cached_tokens", 0) or 0),
            latency_ms=getattr(reply, "latency_ms", None),
            retries=int(getattr(reply, "retries", 0) or 0),
            meta=meta)
        # `build_call` + `append` rather than `record_call`, only because the id
        # has to be kept: `record_call` deliberately returns nothing usable, and
        # a chain that cannot name its own rows can never resolve them.
        llm_telemetry.append([row], path=path)
        if chain_id and chain is not None:
            chain.setdefault("calls", {}).setdefault(chain_id,
                                                     []).append(row.call_id)
    except Exception as exc:                                   # noqa: BLE001
        # Loud, and it matters: the ledger this writes to is the same one the
        # nightly ceiling reads from, so a silent telemetry failure would make
        # the night look cheaper than it is and let it overspend.
        logger.error("TELEMETRY WRITE FAILED for %s (%s: %s) — the nightly "
                     "ceiling now under-counts this call", TRIAL,
                     type(exc).__name__, exc)


def chain_id(night: str, arm: str, ticker: str) -> str:
    """The unit of work five microtask calls share. One cell, one arm."""
    return f"{night}:{arm}:{ticker}"


def resolve_chain_yield(chain: dict, records: list, *, night: str,
                        path=None) -> dict:
    """Tell the ledger what each cell's calls jointly minted. Never raises.

    Every call of a finished chain is amended — with the cell's prediction ids,
    or with none. The empty case is the important one: a cell that produced
    nothing lands in the zero-yield bucket exactly as a barren single call does,
    so declaring the chain unit costs the governor no strictness. It only stops
    it from reading "the night has not finished yet" as "this campaign is buying
    tokens".
    """
    from backend.services import llm_telemetry
    by_chain: dict[str, list[str]] = {}
    for r in records:
        cid = chain_id(night, getattr(r, "arm", "") or "", r.ticker)
        by_chain.setdefault(cid, []).append(r.prediction_id)

    n_calls = n_barren_calls = n_chains = n_barren_chains = 0
    for cid, call_ids in (chain.get("calls") or {}).items():
        pids = by_chain.get(cid, [])
        n_chains += 1
        n_calls += len(call_ids)
        if not pids:
            n_barren_chains += 1
            n_barren_calls += len(call_ids)
        for call_id in call_ids:
            try:
                llm_telemetry.attach_outputs(call_id, prediction_ids=pids,
                                             yield_resolved=True, path=path)
            except Exception as exc:                           # noqa: BLE001
                logger.error("could not resolve chain yield for %s/%s "
                             "(%s: %s) — that row stays PENDING and the "
                             "governor's denominator is short by one",
                             cid, call_id, type(exc).__name__, exc)
    return {"n_chains": n_chains, "n_chains_minted_nothing": n_barren_chains,
            "n_calls_resolved": n_calls, "n_calls_in_barren_chains":
                n_barren_calls}


def _tally(dicts) -> dict:
    """Sum a sequence of {code: count} maps. Sorted, so receipts diff cleanly."""
    out: dict[str, int] = {}
    for d in dicts:
        for k, v in (d or {}).items():
            out[k] = out.get(k, 0) + int(v)
    return dict(sorted(out.items()))


def truncation_report(per_arm: dict) -> dict:
    """How many cells died at the token ceiling, and how unevenly.

    `worst_arm_rate` is the number that decides, not the pooled rate. Pooling
    is what hides the failure: 15/40 in the control and 8/10 in the treatment
    pools to 46%, but the damage is the 25-point GAP, and a night that lost a
    quarter of each arm uniformly would be a much less dangerous night than one
    that lost four fifths of one.
    """
    arms = {a: v for a, v in per_arm.items() if v.get("n_cells")}
    rates = {a: (v.get("n_cells_truncated", 0) / v["n_cells"])
             for a, v in arms.items()}
    n_cells = sum(v["n_cells"] for v in arms.values())
    n_trunc = sum(v.get("n_cells_truncated", 0) for v in arms.values())
    return {
        "n_cells": n_cells,
        "n_cells_truncated": n_trunc,
        "pooled_rate": (n_trunc / n_cells) if n_cells else 0.0,
        "per_arm_rate": {a: round(r, 4) for a, r in rates.items()},
        "worst_arm": (max(rates, key=lambda a: rates[a]) if rates else None),
        "worst_arm_rate": (max(rates.values()) if rates else 0.0),
        "spread": (max(rates.values()) - min(rates.values())) if rates else 0.0,
    }


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
              transport: Callable | None = None,
              dry_run: bool = False,
              sandbox: bool = False,
              max_usd: float = NIGHTLY_MAX_USD,
              balance_usd: float = DEFAULT_BALANCE_USD,
              decision_ts: str | None = None,
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
        # Before the first dollar, like every other refusal here. A sandbox run
        # may replay a snapshot of any age — that is what a rehearsal is for.
        if decision_ts is not None:
            res.decision_lag_minutes = round(
                assert_decision_time_fresh(decision_ts), 2)
        else:
            logger.warning(
                "run_night: no decision_ts supplied, so the snapshot-staleness "
                "guard DID NOT RUN. The tool arms read live data; if this "
                "snapshot is hours old they are forecasting with hindsight.")

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
    chain_ctx: dict = {"id": None, "calls": {}}
    tele_path = None
    if transport is not None:
        # A REHEARSAL WITH THE CHAIN MACHINERY ATTACHED. `llm_call=` bypasses
        # `make_llm_call` entirely, so a stubbed rehearsal never minted a
        # telemetry id, never collected one under a chain, and never amended it
        # — it reported `n_chains: 0` and simulated everything except the part
        # that broke. Night 1's whole divergence was that the zero-yield gate
        # cannot see a chain, and the rehearsal was structurally incapable of
        # showing it. Swapping only the TRANSPORT keeps every layer above the
        # wire in the test.
        if not sandbox:
            raise SandboxRequired(
                "transport= replaces the vendor and may only be used with "
                "sandbox=True; a production night uses the frozen client")
        tele_path = SANDBOX_TELEMETRY
        call = make_llm_call(since_iso=since_iso, max_usd=max_usd,
                             counter=counter, chain=chain_ctx,
                             transport=transport, telemetry_path=tele_path)
    else:
        call = llm_call or make_llm_call(since_iso=since_iso, max_usd=max_usd,
                                         counter=counter, chain=chain_ctx)

    per_arm_tickers: dict[str, list[str]] = {}
    per_arm_inv: dict[str, list] = {}
    per_arm_snaps: dict[str, dict] = {}
    stopped = ""
    barren_stop = ""

    # The cell set is frozen ONCE, here, before a single vendor call. Everything
    # below iterates this tuple and nothing may re-derive it.
    cells = tuple(res.tickers)

    # Equality asserted BEFORE the calls as well as after them. The check at the
    # end catches an arm that dropped cells while running; this one catches an
    # arm that was handed the wrong ones to begin with — and it catches it
    # before any money is spent, rather than after five arms have been paid for
    # and the night is void anyway.
    try:
        TR.assert_arms_share_cells(
            {"__frozen_trigger_set__": list(cells),
             **{arm: list(cells) for arm in arms}})
    except ValueError as exc:
        # VOID, not a crash. A traceback out of the nightly runner is an ops
        # incident that loses the receipt; a void night with its reason on disk
        # is a record. Same outcome for the trial, different outcome for
        # knowing why.
        res.status = "void"
        res.void_reason = f"pre-call cell check failed: {exc}"
        logger.error(res.void_reason)
        cells = ()

    agents = {arm: Investigator(arm, llm_call=call,
                                tool_runner=tool_runner or IT.run_tool,
                                model=REQUEST_MODEL)
              for arm in arms}
    rows_by_arm: dict[str, list] = {arm: [] for arm in arms}
    barren_run: dict[str, int] = {arm: 0 for arm in arms}
    for arm in arms:
        per_arm_tickers[arm], per_arm_inv[arm] = [], []

    # ── CELL-MAJOR, NOT ARM-MAJOR, AND IT IS AN INTEGRITY FIX ────────────────
    # This loop used to run every cell of arm A, then every cell of arm B, and
    # so on. The tool layer states its own PIT rule as "the trial is
    # forward-only, so *now* is point-in-time by construction" — the tools read
    # the live internet at the moment they are called. So in arm-major order the
    # arms are not merely different treatments, they are different TIMES: on a
    # 200-cell night the last arm sees hours more of the world than the first,
    # and the ordering is fixed, so `B_tools` had a systematic information
    # advantage over `A_snapshot` that the trial would have attributed to tools.
    # That is the primary contrast, confounded by loop order.
    #
    # Cell-major makes the pairing temporal as well as nominal: the five arms of
    # one cell run within seconds of each other, against the same world. It also
    # fails better — a night that stops early now leaves every arm with the SAME
    # completed cells, which is a shorter paired night instead of a void one.
    for tkr in cells:
        snap = (snapshots or {}).get(tkr, {})
        for arm in arms:
            chain_ctx["id"] = chain_id(night, arm, tkr)
            try:
                inv = agents[arm].investigate(tkr, snap)
            except NightlyBudgetExhausted as exc:
                stopped = str(exc)
                logger.warning("[%s] nightly budget stopped the run: %s",
                               arm, exc)
                break
            rows_by_arm[arm].append(inv.as_row())
            per_arm_tickers[arm].append(tkr)
            per_arm_inv[arm].append(inv)
            per_arm_snaps.setdefault(arm, {})[tkr] = snap

            barren_run[arm] = 0 if inv.forecasts else barren_run[arm] + 1
            if barren_run[arm] >= MAX_BARREN_CELLS:
                barren_stop = (
                    f"information guard: {barren_run[arm]} consecutive cells "
                    f"in arm {arm} produced no gradeable forecast — stopping "
                    f"rather than paying for the remaining "
                    f"{len(cells) - len(per_arm_tickers[arm])} cells across "
                    f"{len(arms)} arms")
                logger.error(barren_stop)
                break
        if stopped or barren_stop:
            # Drop the partial cell: an arm that was cut off mid-cell leaves the
            # others holding a cell it does not have, and a ragged edge is the
            # thing the pairing guard exists to refuse. Trimming to the shortest
            # completed prefix keeps what was paid for AND paired.
            keep = min(len(v) for v in per_arm_tickers.values())
            for arm in arms:
                del per_arm_tickers[arm][keep:]
                del per_arm_inv[arm][keep:]
                del rows_by_arm[arm][keep:]
            break

    for arm in arms:
        rows, done = rows_by_arm[arm], per_arm_tickers[arm]
        res.per_arm[arm] = {
            "n_cells": len(done),
            "n_with_forecasts": sum(1 for r in rows if r["n_forecasts"] > 0),
            "n_tool_calls": sum(r["n_tool_calls"] for r in rows),
            # Per-arm, not just per-night: the whole danger of truncation is
            # that it lands UNEVENLY across the arms being compared, and a
            # night-level rate would average that away into a number that looks
            # tolerable while the primary contrast is already broken.
            "n_cells_truncated": sum(1 for r in rows
                                     if r.get("n_truncated_calls")),
            "drop_reasons": _tally(r.get("forecast_drops") for r in rows),
            "rows": rows,
        }

    # ── the pairing guards ──────────────────────────────────────────────────
    # A partial night written to the ledger would look like data. If the arms
    # diverged, nothing is minted and the reason is recorded.
    all_records: list[PredictionRecord] = []
    # The information stop is still reported FIRST, though for a weaker reason
    # than before: under cell-major order an early stop leaves the arms holding
    # the SAME trimmed cell set, so "the arms disagree" is no longer even true.
    # It is reported first because it is the CAUSE — a short night and a barren
    # arm are the same event, and the receipt should name the one that decided.
    res.truncation = truncation_report(res.per_arm)
    if barren_stop:
        res.status = "void"
        res.void_reason = barren_stop
    elif res.truncation["worst_arm_rate"] > MAX_TRUNCATION_RATE:
        # Ordered AFTER the barren stop and BEFORE the pairing checks, because
        # each of the three describes the one below it. A truncated night still
        # produces a tidy paired cell set — that is exactly what makes it
        # dangerous — so "the arms agree" would be true and meaningless here.
        t = res.truncation
        res.status = "void"
        res.void_reason = (
            f"truncation guard: arm {t['worst_arm']} lost "
            f"{t['worst_arm_rate']:.0%} of its cells at the token ceiling "
            f"(limit {MAX_TRUNCATION_RATE:.0%}; spread across arms "
            f"{t['spread']:.0%}). The surviving cells are the ones the model "
            f"could answer INSIDE the budget, which is not a random subset — "
            f"arms that gather more evidence think longer and truncate more, "
            f"so accruing this night would bias the primary contrast by a "
            f"constant that is not in the pre-registration")
        logger.error(res.void_reason)
    else:
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

    # Resolve the chains WHATEVER the night's verdict. These calls happened and
    # what they minted — including nothing — is now known; leaving them pending
    # would take them out of the governor's denominator permanently, which is
    # the failure this whole change exists to avoid, one level up.
    res.chain_yield = resolve_chain_yield(chain_ctx, all_records, night=night,
                                          path=tele_path)

    try:
        # SCOPED TO THIS TRIAL for the receipt, while the ceiling above stays
        # unscoped. The ceiling should be conservative — any spend on the box
        # counts against the night's $12 — but `measured_cost_night_1` is the
        # number the funding rule reads, so it must be this trial's own money.
        # The rehearsal that spent nothing reported $0.115184 before this split,
        # which was the day's diagnostic probes wearing the night's name.
        res.spend_usd, res.calls = _spend_since(since_iso, purpose=TRIAL,
                                               path=tele_path)
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
    # How stale the snapshot had become by the time the LAST cell ran — see
    # `decision_lag_minutes_at_end`. Measured, never enforced: aborting a night
    # midway would throw away the forecasts already paid for AND leave the
    # trial with nothing.
    if decision_ts is not None:
        try:
            _dts = (datetime.fromisoformat(decision_ts)
                    if isinstance(decision_ts, str) else decision_ts)
            if _dts.tzinfo is None:
                _dts = _dts.replace(tzinfo=timezone.utc)
            res.decision_lag_minutes_at_end = round(
                (datetime.now(timezone.utc) - _dts).total_seconds() / 60.0, 2)
        except Exception:                                        # noqa: BLE001
            # Instrumentation may degrade to absent; the night it describes
            # may not be taken down by it.
            res.decision_lag_minutes_at_end = None
    if not dry_run:
        out_dir = SANDBOX_RECEIPTS_DIR if sandbox else RECEIPTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{night}.json").write_text(
            json.dumps(res.as_dict(), indent=2, default=str), encoding="utf-8")
    return res
