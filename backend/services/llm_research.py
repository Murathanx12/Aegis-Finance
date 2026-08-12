"""
LLM as a research scientist — inside the firewall, with a ledger
================================================================

Murat's NIGHT-10 ruling: $0 LLM spend is a defect from tonight forward. The LLM
is a component of the system, not a luxury — but a component with hard limits
that predate it and do not bend for it.

What the LLM may do
-------------------
* generate hypotheses, each of which must NAME ITS CLOSEST CORPSE and say why
  it is different — proposals that cannot are sent to the linter anyway;
* review a portfolio adversarially ("why is this probably overfit or wrong?");
* mine contradictions across price, revisions, insiders, options, guidance;
* diagnose a failed experiment and propose descendants, on EXPLORE data only;
* extract structure from filings and events where that feeds a MEASURABLE
  fundamental prediction.

What the LLM may never do
-------------------------
* assign a production weight — the deterministic PM owns allocation;
* see validation or confirmation data before a strategy is frozen;
* grade its own experiment as passed;
* have its output treated as evidence. Everything it emits is a HYPOTHESIS
  until the engine measures it. NIGHT-3 settled this on 16,320 graded
  decisions: the LLM does not earn a role in stock selection (M1 t 0.04,
  M2 t 0.93), and temperature 0.7 flipped 21.6% of its own answers.

Ask in basis points, not prose: NIGHT-3 measured 5/5 coherence when the model
was asked for a number in bps against 3/5 in prose, and that is the adopted
house style.

Every call is ledgered — model, purpose, tokens, cost, output hash — so the
night's spend and what it bought are both auditable after the fact.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

LEDGER_PATH = Path(__file__).resolve().parents[2] / "docs" / "BUILD1" / "llm_ledger.jsonl"

#: Hard campaign ceiling in USD (Murat's ruling). The client refuses to call
#: once the ledger's running total reaches it — a budget that is not enforced
#: in code is a hope.
CAMPAIGN_BUDGET_USD = 30.00

#: DeepSeek published rates, USD per 1M tokens. Used to price the ledger; if
#: they drift the ledger is wrong in a KNOWN direction and the note says so.
PRICE_PER_MTOK = {
    "deepseek-chat": {"in": 0.27, "out": 1.10},
    "deepseek-reasoner": {"in": 0.55, "out": 2.19},
}
DEFAULT_MODEL = "deepseek-chat"


class LLMUnavailable(RuntimeError):
    """No LLM path answered. Not recoverable inside a single call."""


class BudgetExhausted(RuntimeError):
    """The campaign budget is spent. Refusing to call."""


@dataclass
class LLMCall:
    purpose: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    output_sha256: str
    seconds: float
    temperature: float
    ok: bool
    error: str = ""
    meta: dict = field(default_factory=dict)


def _price(model: str, pin: int, pout: int) -> float:
    p = PRICE_PER_MTOK.get(model) or PRICE_PER_MTOK[DEFAULT_MODEL]
    return (pin * p["in"] + pout * p["out"]) / 1_000_000.0


def spent_usd(ledger_path: Optional[Path] = None) -> float:
    p = ledger_path or LEDGER_PATH
    if not p.exists():
        return 0.0
    total = 0.0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            total += float(json.loads(line).get("cost_usd") or 0.0)
        except Exception:  # noqa: BLE001 — a corrupt line must not hide spend
            logger.warning("unreadable ledger line; spend may be understated")
    return total


def _record(call: LLMCall, ledger_path: Optional[Path] = None) -> None:
    p = ledger_path or LEDGER_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    row = asdict(call)
    row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def _mirror(call: LLMCall, *, prompt: str, schema_valid: bool) -> str:
    """Mirror this call into the PROGRAMME-WIDE ledger; return its call_id.

    This module's own `llm_ledger.jsonl` predates the unified one and stays: it
    is what enforces `CAMPAIGN_BUDGET_USD`, and re-pointing a budget gate during
    an instrumentation change is how budgets stop being enforced. The mirror
    exists so research spend appears in the same accounting as specialist and
    product spend — one ledger that can answer "what did the night cost".

    Returns "" when the mirror fails, which is a signal to skip the later
    `attach_outputs` rather than attach to a row that was never written.
    """
    from backend.services import llm_telemetry as _tel

    try:
        row = _tel.build_call(
            provider="deepseek", model=call.model, purpose=call.purpose,
            agent="research", prompt=prompt,
            tokens_in=call.prompt_tokens, tokens_out=call.completion_tokens,
            latency_ms=call.seconds * 1000.0, schema_valid=schema_valid,
            error=call.error or None,
            meta={"temperature": call.temperature,
                  "output_sha256": call.output_sha256,
                  "module_ledger_cost_usd": call.cost_usd})
        _tel.append([row])
        return row.call_id
    except Exception as exc:                              # noqa: BLE001
        logger.warning("llm_research: telemetry mirror failed (%s: %s) — the "
                       "call itself is unaffected, this spend is missing from "
                       "the unified ledger", type(exc).__name__, exc)
        return ""


def available() -> tuple[bool, str]:
    """Is any LLM path usable? Returns (ok, reason)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception as exc:  # noqa: BLE001
        logger.warning("dotenv load failed (%s); relying on the ambient "
                       "environment for keys", exc)
    if os.getenv("DEEPSEEK_API_KEY"):
        return True, "deepseek"
    if os.getenv("ANTHROPIC_API_KEY"):
        return True, "anthropic"
    return False, ("no DEEPSEEK_API_KEY or ANTHROPIC_API_KEY in the "
                   "environment — the LLM roles cannot run")


def ask(prompt: str, *, purpose: str, model: str = DEFAULT_MODEL,
        temperature: float = 0.0, max_tokens: int = 2000,
        schema_hint: str = "", ledger_path: Optional[Path] = None) -> dict:
    """One ledgered call. Returns {"text", "call"}.

    Temperature defaults to 0.0. NIGHT-1/NIGHT-3 measured 21.6% answer flips at
    0.7 on an identical prompt, so anything above zero must be a deliberate,
    stated choice rather than a default nobody looked at.
    """
    ok, why = available()
    if not ok:
        raise LLMUnavailable(why)

    already = spent_usd(ledger_path)
    if already >= CAMPAIGN_BUDGET_USD:
        raise BudgetExhausted(
            f"${already:.2f} of the ${CAMPAIGN_BUDGET_USD:.2f} campaign budget "
            f"is already spent; refusing to call")

    import requests
    key = os.getenv("DEEPSEEK_API_KEY")
    full = prompt if not schema_hint else f"{prompt}\n\n{schema_hint}"
    t0 = time.time()
    try:
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": model, "temperature": temperature,
                  "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": full}]},
            timeout=180)
        r.raise_for_status()
        body = r.json()
        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        pin = int(usage.get("prompt_tokens") or 0)
        pout = int(usage.get("completion_tokens") or 0)
        call = LLMCall(purpose=purpose, model=body.get("model") or model,
                       prompt_tokens=pin, completion_tokens=pout,
                       cost_usd=round(_price(model, pin, pout), 6),
                       output_sha256=hashlib.sha256(text.encode()).hexdigest()[:16],
                       seconds=round(time.time() - t0, 2),
                       temperature=temperature, ok=True)
        _record(call, ledger_path)
        # `schema_valid` here is provisional: whether the reply matched the
        # role's schema is only knowable after `parse_json_block`, so the roles
        # below amend it. A call with a schema_hint that produced no parseable
        # block is the zero-yield case, and the amendment is what records it.
        call_id = _mirror(call, prompt=full,
                          schema_valid=bool(text and text.strip()))
        return {"text": text, "call": asdict(call), "call_id": call_id}
    except Exception as exc:  # noqa: BLE001 — a failed call is ledgered too
        call = LLMCall(purpose=purpose, model=model, prompt_tokens=0,
                       completion_tokens=0, cost_usd=0.0, output_sha256="",
                       seconds=round(time.time() - t0, 2),
                       temperature=temperature, ok=False,
                       error=f"{type(exc).__name__}: {exc}")
        _record(call, ledger_path)
        _mirror(call, prompt=full, schema_valid=False)
        raise LLMUnavailable(str(exc)) from exc


def hypothesis_id(h: Any) -> str:
    """Content id for one proposed mechanism.

    Keyed on the mechanism text rather than a counter so the SAME proposal
    re-emitted on a later night carries the SAME id — otherwise a model that
    repeats itself looks like a model producing new ideas, and spend-per-idea
    is measured against a denominator that only grows.
    """
    key = h.get("mechanism", "") if isinstance(h, dict) else str(h)
    return "hyp_" + hashlib.sha256(str(key).strip().lower().encode()
                                   ).hexdigest()[:14]


def _attach(out: dict, *, hypothesis_ids: Optional[list] = None,
            schema_valid: Optional[bool] = None) -> None:
    """Amend the mirrored telemetry row once the reply has been parsed."""
    from backend.services.llm_telemetry import attach_outputs

    cid = out.get("call_id") or ""
    if not cid:
        return
    attach_outputs(cid, hypothesis_ids=hypothesis_ids or (),
                   schema_valid=schema_valid)


def parse_json_block(text: str) -> Any:
    """Pull the first JSON array/object out of a model reply.

    Models fence JSON, prefix it with prose, or both. A parse failure returns
    None and the caller records the raw text — an unparseable answer is a
    result about the model, not an exception to swallow.
    """
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = s.find(opener), s.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(s[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


# ────────────────────────────── the roles ────────────────────────────────────

HYPOTHESIS_SCHEMA = """Reply with ONLY a JSON array. Each element:
{
 "mechanism": "<one sentence, the economic object being traded>",
 "economic_rationale": "<why this should exist at all>",
 "why_market_underreacts": "<the friction or constraint that leaves it unpriced>",
 "data_required": ["<PIT source>", ...],
 "pit_available": true|false,
 "horizon": "<1m|3m|6m|12m|annual+>",
 "expected_turnover_x_per_year": <number>,
 "expected_gross_edge_bps_per_year": <number>,
 "best_falsification": "<the single test most likely to kill it>",
 "closest_existing_corpse": "<the signal_id or trial name it most resembles>",
 "why_genuinely_different": "<what distinguishes it from that corpse>",
 "implementation": "<how the signal is computed from the named data>"
}
Give numbers in basis points per year, never in prose."""


def generate_hypotheses(*, registry_summary: str, graveyard: str,
                        data_inventory: str, n: int = 8,
                        ledger_path: Optional[Path] = None) -> dict:
    """Ask for economically distinct mechanisms, each naming its closest corpse.

    The corpse requirement is not politeness. This programme has 195 closed
    experiments, and a proposal that cannot say which one it resembles has not
    been checked against them. Whatever the model claims, the output still goes
    through `scripts/lint_prereg.py` — the corpse check is code, not a norm.
    """
    prompt = f"""You are a quantitative research scientist proposing testable
equity-return mechanisms for a research programme that has already run and
KILLED 195 experiments. Your proposals will be checked against that graveyard
by an automated linter, so a proposal that merely renames a dead idea wastes
everyone's time and will be rejected mechanically.

THE SIGNAL REGISTRY (what is permitted, and what is closed):
{registry_summary}

THE GRAVEYARD (what has already been killed, and why):
{graveyard}

THE DATA ACTUALLY ON DISK (a mechanism needing data not listed here cannot be
tested and is worthless to us tonight):
{data_inventory}

HARD CONSTRAINTS on what counts as a usable proposal:
- It must be computable from the data listed above, point-in-time.
- It must be a LONG-ONLY implementable idea: this programme cannot hold the
  short leg, and 99.9% of a long-short spread living in the short leg is a
  known failure mode here.
- Turnover is what kills things here. A mechanism needing more than ~6x annual
  turnover must justify why the edge survives it.
- Do NOT propose: analyst target levels or upside (PERVERSE, killed on three
  instruments), 12-1 momentum, book-to-market value, accruals, 1-month
  reversal, raw 13F following, trailing stops, or LLM-based stock selection.
  All are closed with receipts.

Propose {n} ECONOMICALLY DISTINCT mechanisms. Distinct means a different
economic reason for mispricing, not a different parameter on the same one.

{HYPOTHESIS_SCHEMA}"""
    out = ask(prompt, purpose="hypothesis_generation", max_tokens=4000,
              ledger_path=ledger_path)
    parsed = parse_json_block(out["text"])
    hyps = parsed if isinstance(parsed, list) else []
    _attach(out, hypothesis_ids=[hypothesis_id(h) for h in hyps],
            schema_valid=isinstance(parsed, list))
    return {"hypotheses": hyps,
            "parsed_ok": isinstance(parsed, list),
            "raw": out["text"], "call": out["call"]}


def adversarial_review(portfolio_json: str,
                       ledger_path: Optional[Path] = None) -> dict:
    """"Why is this portfolio probably overfit or wrong?" — a separate pass.

    Deliberately not the same call that produced anything: a model asked to
    critique its own output in one breath produces agreement, not review.
    """
    prompt = f"""You are an adversarial reviewer. Your job is to find the
reasons this portfolio is probably WRONG. Do not balance your answer with
strengths; another process handles those.

{portfolio_json}

Attack it on: selection effects and multiple testing; whether the evidence
grades justify the weights; whether the signals are independent or the same
factor three times; capacity and turnover; regime dependence; whether any
number is a point estimate being read as a fact; and whether anything looks
like it was chosen after seeing the result.

Reply with ONLY a JSON array of objects:
{{"concern": "<one sentence>",
  "severity": "HIGH"|"MEDIUM"|"LOW",
  "why_it_matters_bps_per_year": <number, your estimate of the damage>,
  "how_to_check": "<a specific test that would settle it>"}}"""
    out = ask(prompt, purpose="adversarial_portfolio_review", max_tokens=2500,
              ledger_path=ledger_path)
    parsed = parse_json_block(out["text"])
    # No hypothesis_ids on purpose: a concern is prose with a number in it, not
    # a record anything will later grade. This call therefore lands in the
    # zero-gradeable bucket, which is the honest reading of what it bought.
    _attach(out, schema_valid=isinstance(parsed, list))
    return {"concerns": parsed if isinstance(parsed, list) else [],
            "parsed_ok": isinstance(parsed, list),
            "raw": out["text"], "call": out["call"]}


def diagnose_failure(experiment_summary: str,
                     ledger_path: Optional[Path] = None) -> dict:
    """Classify WHY a strategy died, into the failure taxonomy.

    The taxonomy matters because the corpses are not alike: a strategy with no
    information is finished, and one with information and bad delivery is a
    re-delivery candidate — a NEW pre-registered trial carrying the original
    corpse as a control arm, never a quiet resurrection.
    """
    prompt = f"""Classify why this experiment failed, using EXACTLY one of
these labels: NO_INFORMATION, WRONG_DIRECTION, TOO_WEAK, TURNOVER_KILLED,
COST_KILLED, CAPACITY_KILLED, REGIME_SPECIFIC, CLOCK_SENSITIVE, TAIL_DEPENDENT,
OVERFIT, DATA_QUALITY, DELIVERY_FAILURE, UNKNOWN.

{experiment_summary}

The distinction that matters most: did the signal carry INFORMATION that the
vehicle failed to deliver (DELIVERY_FAILURE / TURNOVER_KILLED / COST_KILLED),
or was there nothing there (NO_INFORMATION / TOO_WEAK)? Be honest about
UNKNOWN; a confident wrong label is worse than an admitted gap.

Reply with ONLY JSON:
{{"label": "<one label>",
  "confidence": "HIGH"|"MEDIUM"|"LOW",
  "evidence_for": "<what in the numbers supports this label>",
  "evidence_against": "<what argues against it>",
  "redelivery_worth_trying": true|false,
  "redelivery_vehicle": "<if true, the specific low-turnover vehicle to try>"}}"""
    out = ask(prompt, purpose="failure_diagnosis", max_tokens=1200,
              ledger_path=ledger_path)
    parsed = parse_json_block(out["text"])
    _attach(out, schema_valid=isinstance(parsed, dict))
    return {"diagnosis": parsed if isinstance(parsed, dict) else {},
            "parsed_ok": isinstance(parsed, dict),
            "raw": out["text"], "call": out["call"]}


def ledger_summary(ledger_path: Optional[Path] = None) -> dict:
    """What the night's calls cost and what they bought."""
    p = ledger_path or LEDGER_PATH
    if not p.exists():
        return {"n_calls": 0, "total_usd": 0.0, "by_purpose": {},
                "budget_usd": CAMPAIGN_BUDGET_USD, "note": "no calls made"}
    rows, unreadable = [], 0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001 — counted, never silently dropped
            unreadable += 1
    if unreadable:
        logger.warning("%d unreadable ledger line(s); reported spend is a "
                       "LOWER BOUND", unreadable)
    by: dict[str, dict] = {}
    for r in rows:
        b = by.setdefault(r.get("purpose", "?"),
                          {"n": 0, "usd": 0.0, "ok": 0, "failed": 0})
        b["n"] += 1
        b["usd"] = round(b["usd"] + float(r.get("cost_usd") or 0), 6)
        b["ok" if r.get("ok") else "failed"] += 1
    total = round(sum(float(r.get("cost_usd") or 0) for r in rows), 4)
    return {"n_calls": len(rows), "total_usd": total,
            "unreadable_ledger_lines": unreadable,
            "spend_is_lower_bound": bool(unreadable),
            "budget_usd": CAMPAIGN_BUDGET_USD,
            "budget_remaining_usd": round(CAMPAIGN_BUDGET_USD - total, 4),
            "by_purpose": by,
            "n_failed": sum(1 for r in rows if not r.get("ok")),
            "pricing_note": ("costs are computed from published per-token "
                             "rates, not billed amounts; if the rates have "
                             "drifted this understates or overstates by that "
                             "drift and nothing else")}
