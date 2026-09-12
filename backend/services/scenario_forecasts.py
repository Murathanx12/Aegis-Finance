"""X3 -- scenario forecasts: the contract, the grader, and nothing wired.

Murat's framing (roadmap section 10, X3): *"these are the things that might
happen"* -- for each name the model writes k plausible next-session headlines
with probabilities, the ENGINE prices each by historical analogue, and the
ledger grades which scenario reality picked and the Brier of the set. That is
"probabilities, not confidence" as a graded object.

THIS MODULE IS THE CONTRACT ONLY. IT IS NOT WIRED INTO THE MORNING.
===================================================================
Two prerequisites are missing and neither is in chunk 7:

* **L2's typed-event extraction over the daily corpus.** Grading asks "which
  typed event actually happened to this symbol the next session", and nothing
  produces that row per day yet. Without it the grader has a rule and no
  realised side.
* **E1's base-rate table.** Section 4.2 prices a scenario by the
  `(event_type, era)` cell's own historical mean forward abnormal return. The
  builder could not confirm that `event_table_v1.parquet` carries the 39-id
  vocabulary; `pricer` therefore takes the table as an ARGUMENT and REFUSES
  when a cell is absent rather than defaulting to zero. A missing base rate is
  not a base rate of zero.

So: the schema, the prompt contract, the `PredictionRecord` shape, the grader
and the base-rate control live here and are tested against synthetic sets.
Wiring is chunk 9's E1 prerequisite. Saying that plainly is the point -- a
module that looks wired and is not is how `event_intel.py` became the 17th
collector feeding nobody.

THE PRICE COMES FROM THE ENGINE, NEVER FROM THE MODEL
=====================================================
Invariant 5 / X5: the LLM proposes the scenario and classifies it; the
deterministic engine supplies the dollar-shaped number. `pricer` is a LOOKUP.
Nothing here lets a model-authored figure become a `priced_return`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

#: The frozen vocabulary, `docs/research_notes/2026-09-11/spec_events_and_calibration.md`
#: section 1.2, in the document's own order. 39 substantive ids plus `no_event`
#: = 40. (That section's closing sentence says "38 substantive + no_event = 39";
#: its own table has 39 substantive rows, and `test_scenario_forecasts.py`
#: derives this tuple from the table so a future edit to either cannot drift
#: silently past the other.)
EVENT_TYPES: tuple[str, ...] = (
    "earnings_report", "earnings_preannouncement", "guidance_change",
    "mergers_acquisitions", "divestiture_asset_sale", "spinoff",
    "bankruptcy_or_going_concern", "delisting_or_listing_risk",
    "debt_issuance_or_obligation", "debt_covenant_or_default_trigger",
    "equity_issuance_dilution", "stock_buyback", "dividend_increase",
    "dividend_cut_or_suspension", "special_dividend",
    "regular_dividend_declaration", "stock_split", "reverse_stock_split",
    "credit_rating_change", "new_contract_or_partnership",
    "contract_loss_or_termination", "product_launch_or_innovation",
    "product_recall_or_defect", "clinical_trial_result", "regulatory_approval",
    "regulatory_investigation_or_action", "litigation_filed",
    "litigation_settlement", "management_change_departure",
    "management_change_appointment", "auditor_or_accounting_change",
    "cybersecurity_incident", "insider_or_institutional_ownership_change",
    "macro_rate_decision", "macro_inflation_print", "macro_labor_report",
    "tariff_or_trade_policy", "sanction", "index_rebalance", "no_event",
)

MAGNITUDES: tuple[str, ...] = ("NEGLIGIBLE", "SMALL", "MODERATE", "LARGE", "EXTREME")

K_DEFAULT = 3
MECHANISM_ID = "x3_scenario_forecast_v1"

#: Why this is not in the Morning yet, in one string a receipt can print.
NOT_WIRED = (
    "X3 is a CONTRACT in chunk 7, not a live lane. Grading needs L2's typed-event "
    "extraction over the daily corpus (nothing produces a realised typed event per "
    "symbol per day yet) and pricing needs E1's (event_type, era) base-rate table "
    "confirmed in the 39-id vocabulary. Both are chunk 9's E1 prerequisite. Until "
    "then this module is exercised by its tests and by nothing else.")


# ----------------------------------------------------------------- the schema

SCENARIO_SET_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "aegis://schemas/scenario_forecast_row.json",
    "title": "AegisScenarioForecastRow",
    "type": "object",
    "additionalProperties": False,
    "required": ["scenario_set_id", "symbol", "as_of", "scenarios"],
    "properties": {
        "scenario_set_id": {
            "type": "string",
            "description": "uuid or content-hash, one per (symbol, as_of) call"},
        "symbol": {"type": "string"},
        "as_of": {
            "type": "string",
            "description": "ISO date, the last session's close this forecast is made after"},
        "scenarios": {
            "type": "array", "minItems": 1, "maxItems": K_DEFAULT,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["headline", "probability", "event_type", "direction",
                             "magnitude_bucket"],
                "properties": {
                    "headline": {
                        "type": "string", "maxLength": 200,
                        "description": ("a plausible next-session headline, not the "
                                        "actual future")},
                    "probability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "event_type": {"type": "string", "enum": list(EVENT_TYPES)},
                    "direction": {"type": "integer", "enum": [-1, 0, 1]},
                    "magnitude_bucket": {"type": "string", "enum": list(MAGNITUDES)},
                },
            },
        },
    },
}


def validate_scenario_set(obj: Any) -> list[str]:
    """Every reason this object is not a valid scenario set, naming the field.

    Hand-written rather than `jsonschema`-driven so the refusal names the field
    the way `protocol_p16.validate` does; the schema above is the published
    contract and `test_scenario_forecasts.py` checks the two agree.

    `sum(probability)` is NOT required to equal 1.0 -- the k scenarios are not
    exhaustive, which is Murat's own framing. It IS reported (see
    `probability_mass`), so three scenarios each claimed at 0.9 is visible as a
    calibration defect instead of hidden.
    """
    out: list[str] = []
    if not isinstance(obj, dict):
        return [f"the scenario set is a {type(obj).__name__}, not an object"]
    for key in SCENARIO_SET_SCHEMA["required"]:
        if key not in obj:
            out.append(f"{key}: missing")
    extra = set(obj) - set(SCENARIO_SET_SCHEMA["properties"])
    for k in sorted(extra):
        out.append(f"{k}: not in the schema (additionalProperties is false)")
    scenarios = obj.get("scenarios")
    if not isinstance(scenarios, list):
        if "scenarios" in obj:
            out.append("scenarios: must be an array")
        return out
    if not 1 <= len(scenarios) <= K_DEFAULT:
        out.append(f"scenarios: {len(scenarios)} items, the contract allows 1 to {K_DEFAULT}")
    for i, s in enumerate(scenarios):
        if not isinstance(s, dict):
            out.append(f"scenarios[{i}]: not an object")
            continue
        item = SCENARIO_SET_SCHEMA["properties"]["scenarios"]["items"]
        for key in item["required"]:
            if key not in s:
                out.append(f"scenarios[{i}].{key}: missing")
        for k in sorted(set(s) - set(item["properties"])):
            out.append(f"scenarios[{i}].{k}: not in the schema")
        p = s.get("probability")
        if p is not None and (not isinstance(p, (int, float)) or isinstance(p, bool)
                              or not 0.0 <= float(p) <= 1.0):
            out.append(f"scenarios[{i}].probability: {p!r} is not a number in [0, 1]")
        if "event_type" in s and s["event_type"] not in EVENT_TYPES:
            out.append(f"scenarios[{i}].event_type: {s['event_type']!r} is not one of the "
                       f"{len(EVENT_TYPES)} frozen ids")
        if "direction" in s and s["direction"] not in (-1, 0, 1):
            out.append(f"scenarios[{i}].direction: {s['direction']!r} is not -1, 0 or 1")
        if "magnitude_bucket" in s and s["magnitude_bucket"] not in MAGNITUDES:
            out.append(f"scenarios[{i}].magnitude_bucket: {s['magnitude_bucket']!r} is not "
                       f"one of {list(MAGNITUDES)}")
        h = s.get("headline")
        if isinstance(h, str) and len(h) > 200:
            out.append(f"scenarios[{i}].headline: {len(h)} chars, the contract caps it at 200")
    return out


def probability_mass(scenario_set: dict) -> float:
    """`sum(probability)`. Printed on every receipt: a set whose mass is 2.7 is
    a calibration defect that must be visible, not a schema violation."""
    return float(sum(float(s.get("probability") or 0.0)
                     for s in scenario_set.get("scenarios") or []))


def set_id(symbol: str, as_of: str, scenarios: Iterable[dict]) -> str:
    """A content hash, so the same call twice is the same set id."""
    payload = json.dumps({"symbol": symbol, "as_of": as_of,
                          "scenarios": list(scenarios)},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


# ----------------------------------------------------------------- the prompt

SYSTEM = (
    "You are a markets analyst writing SCENARIOS, not predictions of fact. "
    "Given what is known at the close, you list the small number of distinct "
    "things that might plausibly be reported about this company in the next "
    "trading session, each with your probability that it happens. You never "
    "state what WILL happen. You output JSON only. Respond in English only."
)

PROMPT = (
    "Symbol: {symbol}\n"
    "As of the close on {as_of}.\n"
    "What is known:\n{context}\n\n"
    "List at most {k} DISTINCT scenarios for the next trading session. For each:\n"
    "  headline          - a plausible next-session headline, at most 200 characters. "
    "Write it as a headline, not as a prediction about the price.\n"
    "  probability       - your probability that this scenario occurs, 0.0 to 1.0. "
    "They need NOT sum to 1: these are the things that might happen, not an "
    "exhaustive partition.\n"
    "  event_type        - exactly one id from this list: {event_types}\n"
    "  direction         - -1, 0 or +1, relative to THIS company, never the market\n"
    "  magnitude_bucket  - NEGLIGIBLE, SMALL, MODERATE, LARGE or EXTREME, on the "
    "expected absolute abnormal return over 1-2 sessions. LARGE means 5% or more in "
    "absolute terms, whatever the company's size.\n\n"
    "Output a JSON array of at most {k} objects with exactly those five keys and "
    "nothing else. Do not state an expected return or a price target: the scenario is "
    "yours, the price is not."
)


def prompt_for(symbol: str, as_of: str, context: str, k: int = K_DEFAULT) -> str:
    return PROMPT.format(symbol=symbol, as_of=as_of, context=context, k=k,
                         event_types=", ".join(EVENT_TYPES))


def prompt_fingerprint() -> dict:
    """sha256 of the frozen prompt pair, so a receipt pins what was asked."""
    return {"system_sha256": hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest(),
            "user_template_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
            "event_types_sha256": hashlib.sha256(
                "|".join(EVENT_TYPES).encode("utf-8")).hexdigest(),
            "n_event_types": len(EVENT_TYPES), "k": K_DEFAULT}


# ------------------------------------------------------------- the engine price

class BaseRateMissing(KeyError):
    """No `(event_type, era)` cell. A missing base rate is not zero."""


def pricer(base_rates: dict) -> Any:
    """`(event_type, era) -> historical mean forward abnormal return`, as a lookup.

    `base_rates` is `{(event_type, era): {"mean": float, "sd": float, "n": int}}`
    built from ALREADY-RESOLVED typed events. A cell that is not in the table
    RAISES: pricing a scenario at zero because nobody measured its analogue
    would put a made-up number where an engine price belongs, which is the one
    thing X5 forbids.
    """
    def price(event_type: str, era: str) -> dict:
        cell = base_rates.get((event_type, era))
        if cell is None:
            raise BaseRateMissing(
                f"no historical analogue for ({event_type}, {era}); this scenario "
                "cannot be priced and is not priced at zero")
        return {"priced_return": float(cell["mean"]),
                "dispersion": cell.get("sd"), "analogue_n": cell.get("n"),
                "analogue_cell": f"{event_type}|{era}"}
    return price


# --------------------------------------------------- the PredictionRecord shape

def prediction_rows(scenario_set: dict, *, price=None, era: str,
                    made_at: str, model: str, prompt_hash: str,
                    input_snapshot_hash: str) -> list[dict]:
    """One row PER SCENARIO, all sharing `scenario_set_id`.

    Field names are `belief_state.PredictionRecord`'s own (schema 1.4.0);
    `test_scenario_forecasts.py` checks every key here exists on that dataclass,
    so this shape cannot drift away from the ledger it is meant to enter.
    `scenario_set_id` is the one genuinely new grouping key and travels in
    `inputs_used` until the dataclass gains it.

    `costs_charged=False` and it is stated: an informational forecast sizes
    nothing. Costs apply if and when E1 sizes off it, and the row that does
    that is a different row.
    """
    rows = []
    sid = scenario_set["scenario_set_id"]
    for i, s in enumerate(scenario_set["scenarios"]):
        priced = None
        priced_error = None
        if price is not None:
            try:
                priced = price(s["event_type"], era)
            except BaseRateMissing as exc:
                priced_error = str(exc)
        rows.append({
            "prediction_id": f"{sid}-{i}",
            "ticker": scenario_set["symbol"],
            "specialist": MECHANISM_ID,
            "observable": (f"the dominant typed event for {scenario_set['symbol']} on "
                           f"the session after {scenario_set['as_of']} is "
                           f"{s['event_type']}"),
            "horizon_days": 1,
            "probability": float(s["probability"]),
            "threshold": None, "benchmark": None,
            "made_at": made_at,
            "resolves_after": scenario_set["as_of"],
            "thesis": s["headline"],
            "counter_thesis": ("reality picks a different scenario, or none of the k "
                               "(which is a miss for all k, not a data gap)"),
            "next_observable": "the next session's typed-event extraction for this symbol",
            "model": model, "model_version": MECHANISM_ID,
            "prompt_hash": prompt_hash,
            "input_snapshot_hash": input_snapshot_hash,
            "mechanism_id": MECHANISM_ID,
            "licence": "PRODUCT_EXPERIMENT",
            "era_tag": era,
            "decision_date": scenario_set["as_of"],
            "costs_charged": False, "cost_rate_bps": None,
            "control_twin_id": f"{sid}-baserate",
            "control_construction": (
                "a base-rate scenario set for the same (symbol, as_of): the era's "
                "top-k unconditional event-type frequencies, each at its own "
                "frequency. Graded identically; the LLM set is compared against this, "
                "never against zero"),
            "inputs_used": {
                "scenario_set_id": sid,
                "scenario_index": i,
                "event_type": s["event_type"],
                "direction": s["direction"],
                "magnitude_bucket": s["magnitude_bucket"],
                "priced_return": (priced or {}).get("priced_return"),
                "analogue_cell": (priced or {}).get("analogue_cell"),
                "analogue_n": (priced or {}).get("analogue_n"),
                "pricing_refusal": priced_error,
                "priced_by": ("the deterministic engine's (event_type, era) lookup; the "
                              "model proposed the scenario and never a number"),
            },
        })
    return rows


# ------------------------------------------------------------------ the grader

def dominant_event(realised: Iterable[dict]) -> dict | None:
    """The realised day's dominant typed event for one symbol.

    Ties are broken by the HIGHEST realised magnitude, matching
    `spec_events_and_calibration.md` section 2.4's "one row per document,
    extract the dominant one". `None` when the day produced no extraction at
    all -- which is NOT the same as a day whose extraction said `no_event`, and
    the grader treats the two differently.
    """
    rows = [r for r in realised if r.get("event_type")]
    if not rows:
        return None
    order = {m: i for i, m in enumerate(MAGNITUDES)}
    return max(rows, key=lambda r: (order.get(str(r.get("magnitude_bucket")), -1),
                                    float(r.get("confidence") or 0.0)))


def grade_set(scenario_set: dict, realised: Iterable[dict]) -> dict:
    """Which scenario reality picked, and the Brier of the set.

    Spec section 4.4. Two things the arithmetic must not hide:

    * a set where NOTHING matched -- including a realised `no_event` day when
      no scenario declared `no_event` -- is a miss for all k and is scored,
      never excluded. A set that never listed the true outcome is a
      calibration failure, not a data gap.
    * the residual mass `1 - sum(probability)` is itself scored against an
      implicit "none of these" bucket, so a set that hedges by declaring 0.2 of
      total mass cannot look well calibrated by saying almost nothing.

    The headline `brier` is the SUM of the per-scenario squared errors plus the
    residual term, which is what spec section 7 step 6's known answer computes
    (0.135 for 0.7/0.15/0.15 with the first matching). `brier_mean` divides by
    k and is reported beside it, because section 4.4's formula is written with a
    `1/k` the worked example does not use -- both are printed rather than one
    chosen silently.
    """
    scenarios = list(scenario_set.get("scenarios") or [])
    k = len(scenarios)
    dom = dominant_event(realised)
    realised_type = (dom or {}).get("event_type")
    matched = None
    for i, s in enumerate(scenarios):
        if realised_type is not None and s.get("event_type") == realised_type:
            matched = i
            break
    terms = []
    total = 0.0
    for i, s in enumerate(scenarios):
        p = float(s.get("probability") or 0.0)
        o = 1.0 if i == matched else 0.0
        term = (p - o) ** 2
        total += term
        terms.append({"index": i, "event_type": s.get("event_type"),
                      "probability": p, "outcome": o, "term": round(term, 6)})
    mass = probability_mass(scenario_set)
    residual_p = 1.0 - mass
    residual_o = 0.0 if matched is not None else 1.0
    residual_term = (residual_p - residual_o) ** 2
    total += residual_term
    return {
        "scenario_set_id": scenario_set.get("scenario_set_id"),
        "symbol": scenario_set.get("symbol"), "as_of": scenario_set.get("as_of"),
        "k": k,
        "realised_event_type": realised_type,
        "realised_day_had_no_extraction": dom is None,
        "matched_index": matched,
        "matched": matched is not None,
        "terms": terms,
        "probability_mass": round(mass, 6),
        "residual_mass": round(residual_p, 6),
        "residual_outcome": residual_o,
        "residual_term": round(residual_term, 6),
        "brier": round(total, 6),
        "brier_mean": round(total / k, 6) if k else None,
        "note": ("a set that matched nothing is scored as a miss for all k plus a "
                 "residual term, never excluded: never listing the true outcome is a "
                 "calibration failure, not a data gap"),
    }


def base_rate_control(symbol: str, as_of: str, frequencies: dict,
                      k: int = K_DEFAULT) -> dict:
    """The control set: the era's top-k unconditional event-type frequencies.

    NO model call. Each scenario carries the frequency itself as its
    probability, so the control is exactly "what usually happens here". The LLM
    set is compared against this, never against zero -- the same discipline as
    R2's shuffled-digest control.
    """
    ranked = sorted(((t, float(f)) for t, f in frequencies.items() if t in EVENT_TYPES),
                    key=lambda kv: (-kv[1], kv[0]))[:k]
    scenarios = [{"headline": f"base rate: {t}", "probability": f, "event_type": t,
                  "direction": 0, "magnitude_bucket": "SMALL"} for t, f in ranked]
    return {"scenario_set_id": set_id(symbol, as_of, scenarios) + "-baserate",
            "symbol": symbol, "as_of": as_of, "scenarios": scenarios}


def compare(llm_graded: dict, control_graded: dict) -> dict:
    """The only comparison X3 makes: the set's Brier against its own control's."""
    a, b = llm_graded.get("brier"), control_graded.get("brier")
    return {"llm_brier": a, "control_brier": b,
            "difference": None if (a is None or b is None) else round(a - b, 6),
            "llm_better": None if (a is None or b is None) else bool(a < b),
            "control_construction": ("the era's top-k unconditional event-type "
                                     "frequencies for this symbol; no model call"),
            "never_against_zero": ("a Brier is compared against the base-rate set's "
                                   "own Brier, never against 0 and never against a "
                                   "uniform prior nobody would have used")}


def declaration() -> dict:
    """What X3 is and is not, for a receipt."""
    return {"mechanism_id": MECHANISM_ID, "k": K_DEFAULT,
            "vocabulary": {"n_event_types": len(EVENT_TYPES),
                           "source": ("docs/research_notes/2026-09-11/"
                                      "spec_events_and_calibration.md section 1.2")},
            "prompt": prompt_fingerprint(),
            "control": "base-rate scenario set (unconditional era frequencies)",
            "pricing": ("deterministic (event_type, era) lookup; a missing cell RAISES "
                        "rather than pricing at zero"),
            "wired": False, "why_not": NOT_WIRED}
