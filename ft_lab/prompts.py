"""Prompt formats shared by training, inference and the loader. One place, so the student
is always asked exactly what it was trained on."""
from __future__ import annotations

import json

SYSTEM_STUDENT = "You convert financial news into typed numeric fields. Reply with one JSON object only."

# the 41 event ids the teacher used on the panel (typed-event vocabulary v2); names are the ids
EVENT_IDS = [
    "no_event", "earnings_report", "analyst_target_change", "new_contract_or_partnership",
    "analyst_rating_change", "product_launch_or_innovation", "guidance_change",
    "insider_or_institutional_ownership_change", "mergers_acquisitions", "tariff_or_trade_policy",
    "regulatory_investigation_or_action", "clinical_trial_result", "regulatory_approval",
    "analyst_initiation", "management_change_appointment", "management_change_departure",
    "equity_issuance_dilution", "litigation_filed", "divestiture_asset_sale",
    "debt_issuance_or_obligation", "stock_buyback", "macro_rate_decision", "macro_inflation_print",
    "product_recall_or_defect", "litigation_settlement", "index_rebalance", "dividend_increase",
    "macro_labor_report", "earnings_preannouncement", "regular_dividend_declaration",
    "contract_loss_or_termination", "spinoff", "sanction", "cybersecurity_incident",
    "reverse_stock_split", "bankruptcy_or_going_concern", "dividend_cut_or_suspension",
    "delisting_or_listing_risk", "credit_rating_change", "stock_split", "special_dividend",
]
MAGS = ["NEGLIGIBLE", "SMALL", "MODERATE", "LARGE", "EXTREME"]
EMOTIONS = ["fear", "anxiety", "anger", "neutral", "optimism", "excitement", "relief"]

# the zero-shot BASE model is not trained on the schema, so it is given it in full
SYSTEM_BASE_EVENTS = (
    "You classify one financial news document about one named entity. Reply with ONLY one JSON object:\n"
    '{"event_type": one id from the list, "direction": -1, 0 or 1 (bad, neutral, good for the entity\'s '
    'shareholders), "magnitude": one of ' + json.dumps(MAGS) + ' (expected size of the price impact: '
    'NEGLIGIBLE <0.5%, SMALL 0.5-2%, MODERATE 2-5%, LARGE 5-10%, EXTREME >10%), "confidence": number 0-1}\n'
    "Use \"no_event\" when the document carries no discrete corporate or macro event (commentary, "
    "market wraps, lists, promotions).\nEvent ids: " + ", ".join(EVENT_IDS)
)


def events_user(scope: str, date: str, title: str, body: str, body_chars: int = 1200) -> str:
    return f"TASK: events\nEntity: {scope}\nDate: {date}\nTitle: {title}\nBody: {(body or '')[:body_chars]}"


def psych_user(symbol: str, text: str) -> str:
    return f"TASK: psych\nTicker: {symbol}\nNews:\n{text}"


def events_target(event_type: str, direction: int, magnitude: str, confidence: float) -> str:
    return json.dumps({"event_type": event_type, "direction": int(direction), "magnitude": magnitude,
                       "confidence": round(float(confidence), 2)})


PSYCH_KEYS = ["tone", "emotion", "uncertainty", "surprise", "mgmt_confidence", "novelty", "attention",
              "expected_move"]


def _clean_num(v):
    """Round floats to 2 dp and turn NaN into null. 2026-09-29: the first student was trained on
    targets like 0.7000000000000001 and NaN, learned to emit them, and ran out of its 110-token
    budget mid-object on 131 of 400 test replies -- the '67% valid' was truncation, not schema."""
    if isinstance(v, float):
        return None if v != v else round(v, 2)
    return v


PSYCH_MAX_NEW_TOKENS = 200   # the first run used 110; float noise made replies longer than that
EVENTS_MAX_NEW_TOKENS = 60


def psych_target(row: dict) -> str:
    return json.dumps({k: _clean_num(row.get(k)) for k in PSYCH_KEYS})


def parse_json(text: str) -> dict | None:
    if not text:
        return None
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        o = json.loads(text[a:b + 1])
    except json.JSONDecodeError:
        return None
    return o if isinstance(o, dict) else None


def valid_events(o: dict | None) -> dict | None:
    if not o:
        return None
    try:
        e, d, m, c = o["event_type"], int(o["direction"]), o["magnitude"], float(o["confidence"])
    except (KeyError, TypeError, ValueError):
        return None
    if e not in EVENT_IDS or d not in (-1, 0, 1) or m not in MAGS:
        return None
    return {"event_type": e, "direction": d, "magnitude": m, "confidence": min(max(c, 0.0), 1.0)}


def valid_psych(o: dict | None) -> dict | None:
    if not o:
        return None
    try:
        out = {"tone": min(max(float(o["tone"]), -1.0), 1.0), "emotion": o["emotion"],
               "uncertainty": float(o["uncertainty"]), "surprise": float(o["surprise"]),
               "mgmt_confidence": None if o.get("mgmt_confidence") is None or o.get("mgmt_confidence") != o.get("mgmt_confidence")
               else float(o["mgmt_confidence"]),
               "novelty": float(o["novelty"]), "attention": float(o["attention"]),
               "expected_move": o["expected_move"]}
    except (KeyError, TypeError, ValueError):
        return None
    if out["emotion"] not in EMOTIONS or out["expected_move"] not in MAGS:
        return None
    return out
