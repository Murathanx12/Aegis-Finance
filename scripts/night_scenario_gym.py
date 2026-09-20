"""S2 -- the SCENARIO GYM: does the reader's "gut" MOVE when the story changes?

Murat, 2026-09-20, verbatim: *"we cant be fully sure but we can have a gut
feeling thats what we are trying to cover it it has a good feeling about
something (test with llm and made up scenarios (make good and bad scenarios
using data we have like same situation in a ficiton setting to see what it will
respond) and we can use this with the engine to make a decison and update it on
events and news."*

The spec is `docs/research_notes/2026-09-20/spec_decision_engine_and_scenario_gym.md`
Part C. Parts B and D are already built (`backend/services/roi_rank.py`,
`decision_contract.revise`); this job is Part C and nothing else.

WHAT IS NEW HERE, AND WHAT IS BORROWED
======================================
Borrowed verbatim, because a second copy is a second thing to get wrong:

* the masking -- `night_r2_monthly_llm.widened_digests`, which is
  `r7_news_representation.mask_company` over `tokenise`, the SAME function
  `night_x_anonymisation_gap` masks with;
* the cell draw -- `x_lane_data.stratified_cells` (equal across MONTH BLOCKS,
  canon section 58's dependence unit) and `cells_fingerprint`, frozen and
  hashed BEFORE any model call so a `PENDING_MODEL` day and the day the reader
  is up ask the same question;
* the grading arithmetic -- `night_r2_monthly_llm.grade` / `paired_vs`, so the
  long-short is priced at the same 25 bps a side on REALISED turnover, and the
  primary is a block-paired Newey-West difference against a shuffled control,
  never a level against zero;
* the receipt protocol -- `protocol_p16.block` (P1-P6), `lap`,
  `anonymisation_gap`;
* the calibration -- `calibration.brier_decomposition` via `protocol_p16.ece`.

New, and the reason this is not a third arm of an already 0-for-2 mechanism
(X_anon_gap's own 09-19 run: raw -18.89%/yr net, masked -16.87%/yr net):

1. **It grades a committed DECISION OBJECT** -- direction, size, expected
   return, confidence, falsifier -- not a direction label.
2. **It grades MOVEMENT UNDER PERTURBATION** (Fin-Force, EMNLP 2025 Findings).
   Each real scenario gets exactly one GOOD twin and one BAD twin: the same
   setup, byte-identical, with ONE appended development drawn from a frozen
   library keyed by the cell's dominant typed event and its vocabulary
   DIRECTION PRIOR. The library is deterministic and hashed. **No model writes
   a twin** -- a twin the reader authored tests whether it agrees with itself.
3. **A CONTROL twin**, which is the number that matters. A model that moves on
   the bad twin has proved nothing if it moves just as much on an unrelated
   appended sentence, so the third twin appends a development belonging to a
   DIFFERENT event family, and the headline is good-minus-control and
   bad-minus-control, never the raw pass rate.
4. **Fiction, not history.** Entity masking is X_anon_gap's; on top of it every
   date literal is shifted by a fixed per-cell seeded offset while every number
   is kept verbatim. The cell is a situation, not a month the model may recall.

THREE THINGS THIS JOB WILL NOT DO
=================================
It will **not start the model server**: llama-server is owned by the desktop
shell, and a research job that boots an 8 GB server collides with another one
mid-run. With the reader down it writes `PENDING_MODEL` with the frozen,
hashed cell list and the twin library's hash.

It will **not become a trading arm**. `adoption()` is a code-enforced cap:
`reliability_weight` is 0.0 until N >= `config.SCENARIO_GYM_ADOPT_MIN_N` AND a
forward record exists, whatever the Brier says. The gym's output may enter
`decision_contract` only as ONE candidate field,
`gut_signal {direction, confidence, reliability_weight}`, scored alongside the
licensed signals -- never a veto, never an override, and it can never flip a
REFUSED to a BUY (spec section C's adoption rule, `roi_rank`'s docstring).

It will **not quote the per-decision number alone**. The PRIMARY is the
block-paired figure over ~19 month blocks; the per-decision sign/Brier numbers
are secondary and the receipt says so in the same object that carries them.

    python -m scripts.night_scenario_gym --smoke --run 1
    python -m scripts.night_factory_jobs S2_scenario_gym --smoke
    NIGHT_QUEUE="S2_scenario_gym:90" python -m scripts.night_factory
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config                                              # noqa: E402
from backend.services import calibration as cal                         # noqa: E402
from backend.services import decision_contract as dc                    # noqa: E402
from backend.services import event_vocabulary as vocab                  # noqa: E402
from backend.services import free_inference as fi                       # noqa: E402
from backend.services import protocol_p16 as pp                         # noqa: E402
from backend.services import x_lane_data as xd                          # noqa: E402
from backend.services.model_provider import (LanguageRefused,           # noqa: E402
                                             ProviderRefusal)
from backend.services.portfolio_intelligence.r2_trial import (           # noqa: E402
    COST_BPS_PER_SIDE)
from scripts.night_r2_monthly_llm import (                              # noqa: E402
    _nw_t, _probe, _r, grade, paired_vs, widened_cells_and_docs,
    widened_digests)

#: Unset means TODAY. A literal date here is how three jobs overwrote committed
#: receipts three nights running (2026-09-18); `NIGHT_RUN_DATE` reproduces a day.
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
STOP = OUT / "STOP"
JOB = "S2_scenario_gym"
LANE = "GUT"

#: Where the typed rows live. L2 writes one file a day plus a `_refusals` file;
#: the refusals are not typed rows and are not read here.
TYPED_EVENTS = REPO / "backend" / "data" / "optimus" / "typed_events"

#: The four refusal names this job counts. EVERY receipt prints all four, at
#: zero when none fired: an absent line and a zero line read identically in a
#: summary and mean opposite things. Each maps to one of
#: `decision_contract.TERMINAL_STATES` so the gym does not invent a taxonomy.
REFUSAL_CLASSES: tuple[str, ...] = (
    "PENDING_MODEL", "REFUSED_SCHEMA", "REFUSED_LANGUAGE", "INSUFFICIENT_N")

REFUSAL_TERMINAL_STATE: dict[str, str] = {
    "PENDING_MODEL": "DATA_MISSING",
    "REFUSED_SCHEMA": "OTHER_TYPED",
    "REFUSED_LANGUAGE": "OTHER_TYPED",
    "INSUFFICIENT_N": "DATA_MISSING",
}


def refusal_ledger(counts: dict | None = None) -> dict:
    """All four classes, ALWAYS, with zeros where nothing fired.

    An absent line and a zero line read identically in a summary and mean
    opposite things -- `free_inference`'s own rule for a $0.00 spend line,
    applied to refusals. A class that fires and is not in the closed set is
    kept (it would be a bug, and dropping it would hide the bug).
    """
    out = {c: 0 for c in REFUSAL_CLASSES}
    for k, v in (counts or {}).items():
        out[str(k)] = int(out.get(str(k), 0)) + int(v)
    return out


def unknown_terminal_states() -> list[str]:
    """Any mapped state `decision_contract` does not declare. Derived.

    The spec says do not write a third taxonomy. This job needs four names of
    its own -- they describe the READER, not a portfolio gate, and none of the
    31 `REFUSAL_CLASSES` covers "the model returned prose" -- but every one of
    them still lands in one of `decision_contract.TERMINAL_STATES`, and this is
    the check rather than the comment that says so.
    """
    return sorted(set(REFUSAL_TERMINAL_STATE.values()) - set(dc.TERMINAL_STATES))

#: The six arms. `real` is the read; `good_twin`/`bad_twin` are the
#: perturbations; `control_good_twin`/`control_bad_twin` are the movement
#: controls; `control_shuffled` is the RETURN control -- the same cell given a
#: digest from a different month, exactly X_anon_gap's control.
#:
#: THE CONTROLS ARE SIGN-MATCHED, and the first smoke run is why. With ONE
#: control that appended an unrelated FAVOURABLE sentence, the good twin's
#: lift was +5.3 pp (t 0.40) and the bad twin's was +52.6 pp (t 3.89) -- but
#: the bad twin's number was comparing an adverse sentence against a
#: favourable one, so it measured VALENCE, not relevance, and would have read
#: as a strong result for the wrong reason. Each twin is now differenced
#: against an unrelated development of ITS OWN SIGN, so the lift isolates the
#: one thing being tested: does the reader move because the development bears
#: on THIS case, or because a sentence of that tone was appended at all?
ARMS: tuple[str, ...] = ("real", "good_twin", "bad_twin", "control_good_twin",
                         "control_bad_twin", "control_shuffled")

#: twin -> the sign-matched control it is differenced against, and the movement
#: direction that counts as the right way for it.
TWIN_CONTROL: dict[str, tuple[str, str]] = {
    "good_twin": ("control_good_twin", "up"),
    "bad_twin": ("control_bad_twin", "down"),
}

#: the arms built by appending ONE line to a byte-identical base. Derived from
#: `ARMS`, so adding an arm cannot leave a loop somewhere iterating the old four.
TWIN_ARMS: tuple[str, ...] = tuple(
    a for a in ARMS if a not in ("real", "control_shuffled"))

#: Consecutive provider refusals that end the run. The reader having gone away
#: mid-run is not a reason to spend the rest of the box writing PENDING_MODEL
#: rows at the speed of a failing socket; `--resume` continues from there.
MAX_CONSECUTIVE_PENDING = 10

DIRECTIONS: tuple[str, ...] = ("BUY", "SHORT", "HOLD", "CASH")

#: BUY/SHORT are directional calls; HOLD/CASH are abstentions and are excluded
#: from sign accuracy's numerator AND denominator, the same rule R2's grader
#: applies to FLAT -- counting an abstention as a miss makes it look like error.
DIRECTION_SIGN: dict[str, int] = {"BUY": 1, "SHORT": -1, "HOLD": 0, "CASH": 0}


# ═══════════════════════════════════════════════════ the committed decision

DECISION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["direction", "size_pct", "expected_return_20d", "confidence",
                 "falsifier"],
    "properties": {
        "direction": {"enum": list(DIRECTIONS)},
        "size_pct": {"type": "number", "minimum": 0.0,
                     "maximum": config.SCENARIO_GYM_MAX_SIZE_PCT},
        "expected_return_20d": {"type": "number",
                                "description": "signed percent over 20 sessions"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0,
                       "description": "your probability that the DIRECTION is right"},
        "falsifier": {"type": "string", "maxLength": 240,
                      "description": "the one observation that would make this wrong"},
    },
}

#: THE SCHEMA TRAVELS IN THE SYSTEM MESSAGE. 2026-09-13's lesson, paid for at
#: 54% refusals: a prompt that REFERS to a schema it never sends is a prompt
#: whose enum the model invents. The full field list, the four allowed
#: directions and both numeric ranges are written out below, in the system
#: message itself, and `prompt_fingerprint()` hashes what was actually sent.
SYSTEM = (
    "You are a disciplined portfolio manager working a FICTIONAL case study. "
    "The company is called [co]. Names have been removed and every date has "
    "been shifted, so nothing here can be looked up; the numbers are real and "
    "unchanged. Commit to ONE decision for the next 20 trading sessions.\n"
    "\n"
    "Reply with a single JSON object and NOTHING else. No prose, no code "
    "fence, no explanation outside the JSON. Respond in English only.\n"
    "\n"
    "The object has exactly these five fields:\n"
    '  "direction"            one of "BUY", "SHORT", "HOLD", "CASH". '
    "BUY and SHORT are directional calls. HOLD and CASH are abstentions and "
    "are the right answer when the text does not support a direction.\n"
    '  "size_pct"             a number from 0.0 to '
    f"{config.SCENARIO_GYM_MAX_SIZE_PCT:.1f}"
    ": the percent of the book you would commit. 0.0 for HOLD or CASH.\n"
    '  "expected_return_20d"  a SIGNED number: your expected percent return '
    "over the next 20 trading sessions, relative to the market. Negative for "
    "an expected fall.\n"
    '  "confidence"           a number from 0.0 to 1.0: your probability that '
    "the DIRECTION is right. Not your enthusiasm.\n"
    '  "falsifier"            one short sentence, at most 240 characters: the '
    "single observation that would show this decision was wrong.\n"
    "\n"
    "Example of the exact shape (the values are an example, not an answer):\n"
    '{"direction": "BUY", "size_pct": 2.5, "expected_return_20d": 1.8, '
    '"confidence": 0.58, "falsifier": "the next filing restates the quarter."}'
)

PROMPT = (
    "FICTIONAL CASE {case_id}\n"
    "As of the end of {as_of}, the reports on [co] are:\n"
    "{digest}\n"
    "\n"
    "Commit to your decision for the next 20 trading sessions. JSON only."
)


def prompt_fingerprint() -> dict:
    """The sha256 of what is actually sent, plus a proof the schema is in it.

    `schema_in_system` is not decoration. It is the 2026-09-13 check made
    executable: if a future edit moves the field list out of `SYSTEM` into a
    comment, this flag goes false on the receipt instead of the refusal rate
    going up three weeks later.
    """
    required = list(DECISION_SCHEMA["required"])
    return {
        "system_sha256": hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest(),
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(DECISION_SCHEMA, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")).hexdigest(),
        "schema_in_system": all(f'"{f}"' in SYSTEM for f in required)
        and all(f'"{d}"' in SYSTEM for d in DIRECTIONS),
        "required_fields": required,
        "temperature": 0.0,
        "max_tokens": int(config.SCENARIO_GYM_MAX_TOKENS),
    }


_JSON_RE = re.compile(r"\{.*\}", re.S)


def validate_decision(obj) -> list[str]:
    """Every reason this is not a committed decision, NAMING the field.

    Hand-written for the same reason `scenario_forecasts.validate_scenario_set`
    is: the refusal has to name the field, because the whole value of a schema
    refusal is telling the next reader what was wrong rather than that
    something was.
    """
    out: list[str] = []
    if not isinstance(obj, dict):
        return [f"the decision is a {type(obj).__name__}, not an object"]
    for key in DECISION_SCHEMA["required"]:
        if key not in obj:
            out.append(f"{key}: missing")
    for key in sorted(set(obj) - set(DECISION_SCHEMA["properties"])):
        out.append(f"{key}: not in the schema (additionalProperties is false)")
    d = obj.get("direction")
    if "direction" in obj and d not in DIRECTIONS:
        out.append(f"direction: {d!r} is not one of {list(DIRECTIONS)}")
    for key, lo, hi in (("size_pct", 0.0, float(config.SCENARIO_GYM_MAX_SIZE_PCT)),
                        ("confidence", 0.0, 1.0)):
        if key not in obj:
            continue
        v = obj.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) \
                or not math.isfinite(float(v)):
            out.append(f"{key}: {v!r} is not a finite number")
        elif not lo <= float(v) <= hi:
            out.append(f"{key}: {v!r} is outside [{lo}, {hi}]")
    er = obj.get("expected_return_20d")
    if "expected_return_20d" in obj:
        if isinstance(er, bool) or not isinstance(er, (int, float)) \
                or not math.isfinite(float(er)):
            out.append(f"expected_return_20d: {er!r} is not a finite number")
    f = obj.get("falsifier")
    if "falsifier" in obj:
        if not isinstance(f, str) or not f.strip():
            out.append("falsifier: must be a non-empty string")
        elif len(f) > int(DECISION_SCHEMA["properties"]["falsifier"]["maxLength"]):
            out.append(f"falsifier: {len(f)} chars, the contract caps it at "
                       f"{DECISION_SCHEMA['properties']['falsifier']['maxLength']}")
    return out


def parse_decision(text: str) -> tuple[dict | None, list[str]]:
    """`(decision, reasons)` -- never raises, never repairs.

    A reply that is not parsable JSON, or is parsable and fails the schema, is
    REFUSED_SCHEMA. It is not retried at a higher temperature and it is not
    patched into shape: a repaired answer is a different experiment run under
    the same job name.
    """
    raw = str(text or "")
    m = _JSON_RE.search(raw)
    if not m:
        return None, ["the reply contains no JSON object"]
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return None, [f"the reply's JSON does not parse: {exc.msg}"]
    reasons = validate_decision(obj)
    return (None, reasons) if reasons else (obj, [])


# ═══════════════════════════════════════════════ the fiction: shifted dates

_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")
_MONTH_NO = {m[:3]: i + 1 for i, m in enumerate(_MONTHS)}
_MONTH_ALT = "|".join(m.capitalize() for m in _MONTHS) + "|" \
    + "|".join(m[:3].capitalize() for m in _MONTHS)

#: ONE regex, ONE pass. Four separate substitutions would re-read their own
#: output: `17 June 2025` rewritten as `4 March 2027` is then matched AGAIN by
#: the bare month-year pattern and shifted a second time. A single alternation
#: with named groups cannot do that, because `re.sub` never rescans what it
#: has already replaced.
#: Every sub-part is a NAMED group. Positional numbering across four
#: alternatives is one inserted parenthesis away from reading the wrong field,
#: and it read `None` as a year on this module's first run.
_DATE_RE = re.compile(
    r"(?P<iso>\b(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})\b)"
    rf"|(?P<mdy>\b(?P<am>{_MONTH_ALT})\.?\s+(?P<ad>\d{{1,2}})(?:st|nd|rd|th)?,?"
    rf"\s+(?P<ay>\d{{4}})\b)"
    rf"|(?P<dmy>\b(?P<bd>\d{{1,2}})\s+(?P<bm>{_MONTH_ALT})\.?\s+(?P<by>\d{{4}})\b)"
    rf"|(?P<my>\b(?P<cm>{_MONTH_ALT})\.?\s+(?P<cy>\d{{4}})\b)")


def _mnum(name: str) -> int:
    return _MONTH_NO[name.strip().lower()[:3]]


def shift_dates(text: str, days: int) -> str:
    """Move every DATE LITERAL by `days`; leave every other number alone.

    Four shapes are recognised -- ISO `2025-06-17`, `June 17, 2025`,
    `17 June 2025` and the bare month-year `June 2025` (moved as its own 15th,
    then re-emitted as a month) -- and nothing else is touched. A bare
    four-digit year is DELIBERATELY not a date here: `2025` alone is as often a
    count, a model number or a price as it is a year, and shifting it would
    corrupt the numbers the spec requires be kept verbatim.
    """
    if not days:
        return str(text or "")

    def _one(m: re.Match) -> str:
        g = m.groupdict()
        try:
            if g["iso"] is not None:
                d = date(int(g["iy"]), int(g["im"]), int(g["id"]))
                return (d + timedelta(days=days)).isoformat()
            if g["mdy"] is not None:
                n = date(int(g["ay"]), _mnum(g["am"]),
                         int(g["ad"])) + timedelta(days=days)
                return f"{_MONTHS[n.month - 1].capitalize()} {n.day}, {n.year}"
            if g["dmy"] is not None:
                n = date(int(g["by"]), _mnum(g["bm"]),
                         int(g["bd"])) + timedelta(days=days)
                return f"{n.day} {_MONTHS[n.month - 1].capitalize()} {n.year}"
            n = date(int(g["cy"]), _mnum(g["cm"]), 15) + timedelta(days=days)
            return f"{_MONTHS[n.month - 1].capitalize()} {n.year}"
        except (ValueError, KeyError, OverflowError):
            # an impossible literal (`2025-02-31`) is left exactly as written:
            # it is not a date, and inventing one for it would be the job
            # editing the text it is supposed to be reading.
            return m.group(0)

    return _DATE_RE.sub(_one, str(text or ""))


def shift_month(month: str, days: int) -> str:
    """`2025-06` moved by `days`, as its own 15th. Same rule as the text."""
    try:
        y, m = (int(x) for x in str(month).split("-")[:2])
        n = date(y, m, 15) + timedelta(days=days)
    except (ValueError, TypeError):
        return str(month)
    return f"{n.year:04d}-{n.month:02d}"


def cell_offset(cell, seed: int) -> int:
    """The fixed, seeded date offset for one cell, in days. Signed.

    Per-cell rather than global: a single global shift is one subtraction away
    from being undone, and the point is that the case cannot be looked up.
    """
    lo, hi = (int(x) for x in config.SCENARIO_GYM_DATE_SHIFT_DAYS)
    payload = json.dumps([list(cell), int(seed)], separators=(",", ":"))
    h = int(hashlib.sha256(payload.encode("utf-8")).hexdigest(), 16)
    mag = lo + (h % max(hi - lo + 1, 1))
    return -mag if (h >> 8) % 2 else mag


# ═══════════════════════════════════ the counterfactual library (NO MODEL)

#: One (good, bad) development pair per FAMILY. Frozen, deterministic, hashed,
#: and written in the anonymised register the digests are in (`[co]`), so an
#: appended sentence cannot be the one token that de-anonymises the case.
#:
#: These are not predictions and they are not labels. They are the ONE thing
#: that varies between a real scenario and its twin, and the base setup is
#: byte-identical across the pair -- which is the whole design: anything the
#: decision does differently, it did because of this sentence.
DEVELOPMENT_FAMILIES: dict[str, tuple[str, str]] = {
    "analyst": (
        "Late in the period a major broker raised its rating on [co] to buy "
        "and lifted its target, citing the same figures above.",
        "Late in the period a major broker cut its rating on [co] to sell and "
        "lowered its target, citing the same figures above."),
    "guidance": (
        "Management then raised its outlook for the coming quarter and said "
        "demand had strengthened since the reports above.",
        "Management then withdrew its outlook for the coming quarter and said "
        "demand had weakened since the reports above."),
    "regulatory": (
        "The relevant regulator then cleared [co] and closed its file with no "
        "conditions attached.",
        "The relevant regulator then opened a formal proceeding against [co] "
        "and asked for documents."),
    "legal": (
        "The outstanding claim against [co] was then settled for an amount the "
        "company called immaterial.",
        "A further claim was then filed against [co] seeking damages the "
        "company called material."),
    "credit": (
        "A rating agency then affirmed [co] with a positive outlook and said "
        "its funding need was covered.",
        "A rating agency then placed [co] on watch for downgrade and "
        "questioned whether its funding need was covered."),
    "capital_return": (
        "The board then expanded its buyback and said it intended to keep "
        "returning capital.",
        "The board then suspended its buyback and said it would preserve cash "
        "instead."),
    "demand": (
        "A large customer then expanded its order with [co] and extended the "
        "term of the agreement.",
        "A large customer then cancelled its order with [co] and did not "
        "renew the agreement."),
    "operations": (
        "The disruption was then contained, and [co] said operations had "
        "returned to normal within days.",
        "The disruption then widened, and [co] said operations would stay "
        "impaired for some weeks."),
    "corporate_action": (
        "A second bidder then emerged for the assets in question and the terms "
        "improved for [co].",
        "The proposed transaction was then abandoned and [co] said the assets "
        "would stay where they are."),
    "macro": (
        "Policy then moved in [co]'s favour, and the cost pressure named above "
        "eased over the following weeks.",
        "Policy then moved against [co], and the cost pressure named above "
        "intensified over the following weeks."),
    "generic": (
        "Conditions for [co] then improved, and the trend described above "
        "continued in its favour.",
        "Conditions for [co] then deteriorated, and the trend described above "
        "reversed against it."),
}

#: event id -> family. TOTAL over the vocabulary as it stands
#: (`test_scenario_gym.py` fails naming any id that falls through), because an
#: unmapped id would silently take the `generic` pair and the receipt would say
#: the twin was "keyed by the dominant event" when it was not.
EVENT_FAMILY: dict[str, str] = {
    "earnings_report": "analyst",
    "earnings_preannouncement": "analyst",
    "guidance_change": "guidance",
    "analyst_rating_change": "analyst",
    "analyst_target_change": "analyst",
    "analyst_initiation": "analyst",
    "mergers_acquisitions": "corporate_action",
    "divestiture_asset_sale": "corporate_action",
    "spinoff": "corporate_action",
    "bankruptcy_or_going_concern": "credit",
    "delisting_or_listing_risk": "credit",
    "debt_issuance_or_obligation": "credit",
    "debt_covenant_or_default_trigger": "credit",
    "equity_issuance_dilution": "credit",
    "credit_rating_change": "credit",
    "stock_buyback": "capital_return",
    "dividend_increase": "capital_return",
    "dividend_cut_or_suspension": "capital_return",
    "special_dividend": "capital_return",
    "regular_dividend_declaration": "capital_return",
    "stock_split": "capital_return",
    "reverse_stock_split": "capital_return",
    "index_rebalance": "capital_return",
    "insider_or_institutional_ownership_change": "capital_return",
    "new_contract_or_partnership": "demand",
    "contract_loss_or_termination": "demand",
    "product_launch_or_innovation": "demand",
    "product_recall_or_defect": "demand",
    "foreign_entrant_capacity": "demand",
    "growth_constraint_cited": "demand",
    "clinical_trial_result": "regulatory",
    "regulatory_approval": "regulatory",
    "regulatory_investigation_or_action": "regulatory",
    "tariff_or_trade_policy": "macro",
    "sanction": "regulatory",
    "litigation_filed": "legal",
    "litigation_settlement": "legal",
    "auditor_or_accounting_change": "legal",
    "management_change_departure": "operations",
    "management_change_appointment": "operations",
    "cybersecurity_incident": "operations",
    "macro_rate_decision": "macro",
    "macro_inflation_print": "macro",
    "macro_labor_report": "macro",
    "no_event": "generic",
}


def unmapped_event_ids() -> list[str]:
    """Vocabulary ids with no family. Derived, so drift is a red suite."""
    return sorted(set(vocab.EVENT_TYPES) - set(EVENT_FAMILY))


def library_hash() -> str:
    """One hash over the pairs AND the id->family map. Both are the library."""
    payload = json.dumps({"families": DEVELOPMENT_FAMILIES,
                          "event_family": EVENT_FAMILY},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def family_of(event_id: str) -> str:
    return EVENT_FAMILY.get(str(event_id), "generic")


def developments_for(event_id: str) -> dict:
    """The good/bad pair for one event id, and the PRIOR that keyed it.

    `direction_prior` is carried onto the receipt for a reason the spec gives:
    the twins are built from the vocabulary's own priors, not from the model's,
    so a reader can check that the "good" sentence for a `-1`-prior event is
    still the favourable one and not an intensification of the bad news.
    """
    fam = family_of(event_id)
    good, bad = DEVELOPMENT_FAMILIES[fam]
    prior = None
    try:
        prior = vocab.by_id(str(event_id)).direction_prior
    except (KeyError, ValueError):
        prior = None
    return {"event_type": str(event_id), "family": fam, "good": good,
            "bad": bad, "direction_prior": prior,
            "keyed": str(event_id) in EVENT_FAMILY}


def control_family(event_id: str, seed: int, cell) -> str:
    """A family that is NOT this cell's, chosen deterministically.

    The control twins' job is to answer "would it have moved anyway?", so the
    appended sentence must be a development of the same register, the same
    SIGN, and nothing to do with the case. One family serves both controls, so
    the good and bad controls differ from each other in exactly the way the
    good and bad twins do.
    """
    fams = sorted(set(DEVELOPMENT_FAMILIES) - {family_of(event_id)})
    payload = json.dumps(["control", list(cell), int(seed)], separators=(",", ":"))
    h = int(hashlib.sha256(payload.encode("utf-8")).hexdigest(), 16)
    return fams[h % len(fams)]


def append_development(digest: str, sentence: str) -> str:
    """The twin: the base digest BYTE-IDENTICAL, plus one appended line."""
    return f"{str(digest)}\n- {str(sentence).strip()}"


def is_disjoint(digest: str, sentence: str) -> bool:
    """Is the appended sentence genuinely new text?

    Checked rather than assumed, and COUNTED on the receipt. If a development
    already appears in the base digest, the twin varies nothing and the pair is
    not a counterfactual -- it is the same scenario asked twice.
    """
    return str(sentence).strip() not in str(digest or "")


def build_case(digest: str, cell, event_id: str, *, seed: int) -> dict:
    """Every arm's TEXT for one cell. Deterministic; no model is involved.

    `control_shuffled` is not built here: it needs another cell's digest and is
    assembled by the job, exactly as `night_r2_monthly_llm._run_digests` does.
    """
    off = cell_offset(cell, seed)
    base = shift_dates(str(digest), off)
    dev = developments_for(event_id)
    ctl_fam = control_family(event_id, seed, cell)
    ctl_good, ctl_bad = DEVELOPMENT_FAMILIES[ctl_fam]
    # the controls append an unrelated family's GOOD and BAD sentences: the
    # same register, the same sign as the twin each one is differenced against,
    # and nothing to say about this case. That difference is the "would it have
    # moved anyway on a sentence of this tone?" baseline.
    appended = {"good_twin": dev["good"], "bad_twin": dev["bad"],
                "control_good_twin": ctl_good, "control_bad_twin": ctl_bad}
    return {
        "cell": list(cell),
        "as_of": shift_month(cell[1], off),
        "date_offset_days": off,
        "event_type": dev["event_type"], "family": dev["family"],
        "direction_prior": dev["direction_prior"],
        "control_family": ctl_fam,
        "texts": {"real": base,
                  **{a: append_development(base, s) for a, s in appended.items()}},
        "appended": appended,
        "disjoint": {a: is_disjoint(base, s) for a, s in appended.items()},
    }


# ═══════════════════════════════════════════════ the dominant typed event

def dominant_events(keys, path: Path | None = None) -> tuple[dict, dict]:
    """`(cell -> modal event_type, coverage)` from L2's typed rows.

    A cell with no typed row gets `no_event` and is COUNTED, not hidden: the
    share of cells whose twin was keyed by a real typed event is the difference
    between "the twins are keyed by the dominant event" and "most twins are
    generic", and only the receipt can tell a reader which run this was.
    """
    root = Path(path or TYPED_EVENTS)
    want = {(str(a), str(b)) for a, b in keys}
    tally: dict[tuple[str, str], Counter] = {}
    files = 0
    rows_read = 0
    if root.is_dir():
        for f in sorted(root.glob("*.jsonl")):
            if f.name.endswith("_refusals.jsonl"):
                continue
            files += 1
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue            # a half-written last line during a live typing run
                rows_read += 1
                if str(row.get("scope_kind") or "") != "ticker":
                    continue
                sym = str(row.get("scope") or "").upper()
                d = str(row.get("document_date") or "")[:7]
                k = (sym, d)
                if k not in want:
                    continue
                et = str(row.get("event_type") or "")
                if not et:
                    continue
                tally.setdefault(k, Counter())[et] += 1
    out: dict[tuple[str, str], str] = {}
    for k in want:
        c = tally.get(k)
        if not c:
            out[k] = vocab.NO_EVENT
            continue
        # ties break lexicographically, so the same corpus always yields the
        # same dominant event -- `Counter.most_common` does not promise that.
        top = max(c.items(), key=lambda kv: (kv[1], [-ord(ch) for ch in kv[0]]))
        out[k] = top[0]
    typed = sum(1 for k in want if out[k] != vocab.NO_EVENT)
    cov = {"typed_event_files_read": files, "typed_rows_scanned": rows_read,
           "cells": len(want), "cells_with_a_typed_event": typed,
           "coverage": _r(typed / max(len(want), 1), 4),
           "source": str(root),
           "vocabulary_hash": vocab.VOCABULARY_HASH,
           "vocabulary_version": vocab.VOCABULARY_VERSION,
           "note": ("a cell with no typed row is keyed `no_event` and takes the "
                    "generic development pair; the coverage above is what "
                    "separates 'twins keyed by the dominant event' from "
                    "'most twins were generic'")}
    return out, cov


# ══════════════════════════════════════════════════════════════ the grading

def decision_row(case: dict, arm: str, decision: dict | None, *, fwd,
                 refusal: str | None = None) -> dict:
    """One answer, in the shape `night_r2_monthly_llm.grade` already reads.

    `conf` is the book weight and it is `confidence`, not `size_pct`: R2's book
    weights by confidence and the two arms have to be priced by the same
    convention to be comparable at all. `size_pct` is carried beside it and is
    what the twin test moves on.
    """
    sym, month = case["cell"][0], case["cell"][1]
    d = decision or {}
    direction = d.get("direction")
    return {
        "tag": arm, "name": str(sym), "month": str(month),
        "dir": DIRECTION_SIGN.get(str(direction), None) if decision else None,
        "conf": float(d.get("confidence") or 0.0) if decision else 0.0,
        "fwd": fwd,
        "direction": direction,
        "size_pct": float(d.get("size_pct") or 0.0) if decision else None,
        "expected_return_20d": (float(d.get("expected_return_20d") or 0.0)
                                if decision else None),
        "falsifier": d.get("falsifier") if decision else None,
        "event_type": case.get("event_type"), "family": case.get("family"),
        "refusal_class": refusal,
        "terminal_state": REFUSAL_TERMINAL_STATE.get(refusal or "") or None,
    }


def _deltas(real: dict, twin: dict) -> dict:
    """The three movements the twin test grades, and the direction flip.

    Three deltas, not one: a "gut" that gets more confident without committing
    more capital has still moved, and a model that only ever moves `size_pct`
    has moved in one dimension. The majority rule over the three is the spec's,
    and both readings of it (strict, and `>= 0`) are returned.
    """
    d_size = float(twin.get("size_pct") or 0.0) - float(real.get("size_pct") or 0.0)
    d_conf = float(twin.get("conf") or 0.0) - float(real.get("conf") or 0.0)
    d_er = (float(twin.get("expected_return_20d") or 0.0)
            - float(real.get("expected_return_20d") or 0.0))
    ds = (d_size, d_conf, d_er)
    return {
        "_raw": ds,
        "d_size_pct": _r(d_size, 4), "d_confidence": _r(d_conf, 4),
        "d_expected_return_20d": _r(d_er, 4),
        "up_strict": sum(1 for x in ds if x > 0) >= 2,
        "down_strict": sum(1 for x in ds if x < 0) >= 2,
        "up_or_flat": sum(1 for x in ds if x >= 0) >= 2,
        "down_or_flat": sum(1 for x in ds if x <= 0) >= 2,
        "unmoved": all(abs(x) < 1e-12 for x in ds),
        "direction_flipped": (real.get("dir") is not None
                              and twin.get("dir") is not None
                              and int(real["dir"]) != 0 and int(twin["dir"]) != 0
                              and int(real["dir"]) != int(twin["dir"])),
    }


def movement(real_rows, twin_rows, label: str) -> dict:
    """Pair-by-pair movement of one twin arm against the real arm.

    BOTH readings are reported and the strict one is the headline. `Δ >= 0 on a
    majority` is the spec's literal pass condition, and a model that answers
    the same thing to every prompt passes it at 100% -- so `unmoved_rate` and
    the STRICT rates sit beside it, and the adjudication uses the strict rate
    minus the control's.
    """
    real_by = {(r["name"], r["month"]): r for r in real_rows
               if r.get("refusal_class") is None}
    pairs, by_block = [], {}
    for t in twin_rows:
        if t.get("refusal_class") is not None:
            continue
        r = real_by.get((t["name"], t["month"]))
        if r is None:
            continue
        d = _deltas(r, t)
        pairs.append(d)
        by_block.setdefault(str(t["month"]), []).append(d)
    n = len(pairs)
    if n == 0:
        return {"label": label, "n_pairs": 0,
                "verdict": "CANNOT DETERMINE: no real/twin pair was answered by both arms"}

    def rate(key: str) -> float:
        return sum(1 for p in pairs if p[key]) / n

    blocks = sorted(by_block)
    return {
        "label": label, "n_pairs": n, "date_blocks": len(blocks),
        "up_strict_rate": _r(rate("up_strict"), 4),
        "down_strict_rate": _r(rate("down_strict"), 4),
        "up_or_flat_rate": _r(rate("up_or_flat"), 4),
        "down_or_flat_rate": _r(rate("down_or_flat"), 4),
        "unmoved_rate": _r(rate("unmoved"), 4),
        "direction_flip_rate": _r(rate("direction_flipped"), 4),
        "mean_d_size_pct": _r(float(np.mean([p["_raw"][0] for p in pairs])), 4),
        "mean_d_confidence": _r(float(np.mean([p["_raw"][1] for p in pairs])), 4),
        "mean_d_expected_return_20d":
            _r(float(np.mean([p["_raw"][2] for p in pairs])), 4),
        "_blocks": blocks,
        "_up_by_block": [float(np.mean([p["up_strict"] for p in by_block[b]]))
                         for b in blocks],
        "_down_by_block": [float(np.mean([p["down_strict"] for p in by_block[b]]))
                           for b in blocks],
    }


def movement_lift(arm: dict, ctl: dict, key: str, label: str) -> dict:
    """Twin movement MINUS the control twin's, block-paired with a NW t.

    This is the gym's own version of "never against zero". A good twin that
    raises size 60% of the time has said nothing until the unrelated sentence's
    own rate is beside it.
    """
    a = arm.get(f"_{key}_by_block") or []
    c = ctl.get(f"_{key}_by_block") or []
    ab, cb = arm.get("_blocks") or [], ctl.get("_blocks") or []
    n = min(len(a), len(c))
    if n == 0:
        return {"label": label, "verdict": "CANNOT DETERMINE: no paired block"}
    if ab[:n] != cb[:n]:
        return {"label": label,
                "verdict": ("REFUSED: the arm and the control twin do not share "
                            "their month blocks, so a paired difference would "
                            "pair different dates")}
    d = np.asarray(a[:n], dtype="float64") - np.asarray(c[:n], dtype="float64")
    return {"label": label, "paired_blocks": int(n),
            "lift_pp": _r(float(d.mean()) * 100, 3),
            "t_nw_blocks": None if n < 6 else _r(_nw_t(d), 3),
            "arm_rate": arm.get(f"{key}_strict_rate"),
            "control_rate": ctl.get(f"{key}_strict_rate"),
            "note": ("the twin's strict movement rate minus the CONTROL twin's, "
                     "block by block; a difference over the same month blocks, "
                     "not two levels subtracted")}


def calibration_block(rows, min_n: int | None = None) -> dict:
    """Brier, ECE, Murphy's split and the confidence deciles -- or INSUFFICIENT_N.

    `confidence` is contractually P(the direction is right), so it grades
    directly against `sign correct`. HOLD/CASH rows make no directional call
    and are excluded, the same exclusion `sign_accuracy` applies.
    """
    floor = int(min_n if min_n is not None else config.SCENARIO_GYM_MIN_N_FOR_CALIBRATION)
    p, o = [], []
    for r in rows:
        if r.get("refusal_class") is not None:
            continue
        d, f = r.get("dir"), r.get("fwd")
        if d in (None, 0) or f is None or not np.isfinite(float(f)):
            continue
        p.append(float(r.get("conf") or 0.0))
        o.append(1.0 if (float(f) > 0) == (int(d) > 0) else 0.0)
    n = len(p)
    if n < floor:
        return {"refusal_class": "INSUFFICIENT_N", "n": n, "min_n": floor,
                "ece": None, "brier": None, "brier_decomposition": {},
                "by_decile": [],
                "reason": (f"{n} gradeable directional decisions is below the {floor} "
                           "this job refuses under; a decomposition on tiny bins is "
                           "noise wearing a calibration label")}
    block = pp.ece(p, o, n_bins=10)
    dec = cal.brier_decomposition(p, o, n_bins=10)
    return {"refusal_class": None, "n": n, "min_n": floor,
            "ece": block.get("ece"), "brier": block.get("brier"),
            "brier_decomposition": {k: dec.get(k) for k in
                                    ("reliability", "resolution", "uncertainty")},
            "by_decile": dec.get("bins") or [],
            "base_rate": _r(float(np.mean(o)), 4),
            "mean_confidence": _r(float(np.mean(p)), 4)}


def mde(n_decisions: int, sd_pct: float | None, block_series=None) -> dict:
    """What this run could have detected, and which number is the PRIMARY.

    Both are printed BECAUSE the per-decision number looks more precise and is
    the one a reader skips to (spec section E, and MEMORY's "check the tail
    before the mean"). The block figure is derived from the run's OWN monthly
    series when there is one; with none it says so rather than quoting a
    constant as if it had been measured here.
    """
    n = int(max(n_decisions, 0))
    per = {"N_decisions": n, "cross_sectional_sd_pct": _r(sd_pct, 4) if sd_pct else None,
           "MDE_mean_20d_pp": (None if (not sd_pct or n < 2)
                               else _r(2.8 * float(sd_pct) / math.sqrt(n), 3)),
           "MDE_sign_accuracy_pp": None if n < 2 else _r(140.0 / math.sqrt(n), 2),
           "basis": "2.8 * sd / sqrt(N), two-sided 5%, 80% power"}
    s = np.asarray(list(block_series or []), dtype="float64")
    s = s[np.isfinite(s)]
    if len(s) >= 2:
        blk = {"date_blocks": int(len(s)),
               "monthly_sd_pp": _r(float(s.std(ddof=1)) * 100, 4),
               "MDE_monthly_pp": _r(2.8 * float(s.std(ddof=1)) * 100 / math.sqrt(len(s)), 4),
               "MDE_annualised_pp": _r(2.8 * float(s.std(ddof=1)) * 12 * 100
                                       / math.sqrt(len(s)), 3),
               "basis": "the run's OWN monthly long-short series"}
    else:
        blk = {"date_blocks": int(len(s)),
               "MDE_monthly_pp": None, "MDE_annualised_pp": None,
               "basis": "CANNOT DETERMINE: fewer than two graded month blocks"}
    return {"PRIMARY_block_level": blk, "secondary_per_decision": per,
            "which_decides": ("the BLOCK figure. N decisions drawn from ~19 month "
                              "blocks collapse to an effective n near the block "
                              "count for anything that shares a month's market "
                              "move (canon section 58); the per-decision line is "
                              "reported and never deciding")}


def grade_and_adopt(by_arm: dict, *, refusals: dict | None = None,
                    sd_pct: float | None = None,
                    forward_record: bool = False) -> dict:
    """The whole graded half of the receipt, from answer ROWS and nothing else.

    Pure: it reads no file, calls no model and knows nothing about the panel.
    That is what lets `test_scenario_gym.py` hand it synthetic answers with a
    known sign accuracy and a known twin-movement share and check the receipt's
    own numbers, rather than checking a receipt that was produced by the same
    run that is being checked.
    """
    by_arm = {a: list(by_arm.get(a) or []) for a in ARMS}
    counts = refusal_ledger(refusals)
    graded = {a: grade([r for r in by_arm[a] if r.get("refusal_class") is None], a)
              for a in ARMS}
    real_g, ctl_g = graded["real"], graded["control_shuffled"]

    mv = {a: movement(by_arm["real"], by_arm[a], a) for a in TWIN_ARMS}
    good_lift = movement_lift(
        mv["good_twin"], mv["control_good_twin"], "up",
        "good twin raises, minus an UNRELATED favourable development")
    bad_lift = movement_lift(
        mv["bad_twin"], mv["control_bad_twin"], "down",
        "bad twin lowers, minus an UNRELATED adverse development")
    calib = calibration_block(by_arm["real"])
    if calib.get("refusal_class") == "INSUFFICIENT_N":
        counts["INSUFFICIENT_N"] += 1
    n_graded = int(calib.get("n") or 0)

    up = mv["good_twin"].get("up_strict_rate")
    dn = mv["bad_twin"].get("down_strict_rate")
    gut = None if (up is None or dn is None) else _r((float(up) + float(dn)) / 2, 4)
    gut_vs_ctl = None
    if isinstance(good_lift.get("lift_pp"), (int, float)) \
            and isinstance(bad_lift.get("lift_pp"), (int, float)):
        gut_vs_ctl = _r((float(good_lift["lift_pp"]) + float(bad_lift["lift_pp"])) / 2, 3)

    realised = real_g.get("turnover_per_rebalance")
    return {
        "arms": {a: {k: v for k, v in graded[a].items() if not k.startswith("_")}
                 for a in ARMS},
        "PRIMARY_twin_movement": {
            **{a: {k: v for k, v in mv[a].items() if not k.startswith("_")}
               for a in mv},
            "good_twin_lift_vs_control": good_lift,
            "bad_twin_lift_vs_control": bad_lift,
            "gut_score": gut,
            "gut_score_vs_control_pp": gut_vs_ctl,
            "reading": ("the pass rate on its own is not the finding: a model that "
                        "answers the same thing every time passes the spec's "
                        "`delta >= 0` condition at 100%, which is why unmoved_rate "
                        "and the strict rates are printed and the LIFT over the "
                        "SIGN-MATCHED control twin is the primary. Each lift "
                        "differences a twin against an unrelated development of "
                        "the same sign, so what it isolates is relevance, not "
                        "valence -- the first smoke run's single favourable "
                        "control made the bad twin look strong for the wrong "
                        "reason"),
        },
        "secondary_returns": {
            "real_minus_shuffled_control": paired_vs(
                real_g, ctl_g, "real decisions minus the shuffled-digest control"),
            "net_ann_pct_real": real_g.get("long_short_ann_pct_NET"),
            "net_ann_pct_shuffled_control": ctl_g.get("long_short_ann_pct_NET"),
            "caution": ("X_anon_gap's 09-19 run found BOTH of its arms lose money "
                        "net on this panel (raw -18.89%/yr, masked -16.87%/yr). "
                        "This block is reported, never deciding: the gym is graded "
                        "on MOVEMENT and may never become a trading arm"),
        },
        "calibration": calib,
        "MDE": mde(n_graded, sd_pct, block_series=real_g.get("_monthly_net")),
        "refusals": counts,
        "refusal_terminal_states": dict(REFUSAL_TERMINAL_STATE),
        "adoption": adoption(n_graded, calib, forward_record=forward_record,
                             n_blocks=real_g.get("date_blocks")),
        "adoption_line": adoption_line(n_graded, forward_record=forward_record,
                                       n_blocks=real_g.get("date_blocks")),
        "_summary": {"n_graded": n_graded, "gut_score": gut,
                     "gut_score_vs_control_pp": gut_vs_ctl,
                     "good_up_rate": up, "bad_down_rate": dn,
                     "sign_accuracy": real_g.get("sign_accuracy"),
                     "good_t": good_lift.get("t_nw_blocks"),
                     "bad_t": bad_lift.get("t_nw_blocks"),
                     "flip_rate": mv["bad_twin"].get("direction_flip_rate"),
                     "flip_n": int(mv["bad_twin"].get("n_pairs") or 0),
                     "realised_bps": (None if realised is None
                                      else _r(float(realised) * COST_BPS_PER_SIDE, 2))},
    }


def adoption(n_graded: int, calib: dict, *, forward_record: bool = False,
             n_blocks: int | None = None) -> dict:
    """The weight the gym is allowed to carry. A CAP IN CODE, not an intention.

    `reliability_weight` is 0.0 unless BOTH conditions hold, whatever the Brier
    decomposition says -- spec section C rule 4, and section E's named failure
    ("computed once and never re-measured is a thumb on the scale wearing a
    calibration label"). The MEASURED resolution is carried beside it so the
    reader can see what it WOULD be, which is a different claim and is labelled
    as one.
    """
    min_n = int(config.SCENARIO_GYM_ADOPT_MIN_N)
    min_blocks = int(config.SCENARIO_GYM_ADOPT_MIN_BLOCKS)
    measured = (calib or {}).get("brier_decomposition", {}).get("resolution")
    enough = int(n_graded) >= min_n
    # 2026-09-20 (Murat): "three hundred correlated scenarios are not 300
    # independent observations." The dependence unit is the month block; a
    # receipt that cannot count its blocks is CANNOT DETERMINE, not enough.
    blocks_known = n_blocks is not None
    enough_blocks = blocks_known and int(n_blocks) >= min_blocks
    ok = bool(enough and enough_blocks and forward_record)
    why = []
    if not enough:
        why.append(f"N {int(n_graded)} < {min_n}")
    if not blocks_known:
        why.append(f"independent month blocks CANNOT DETERMINE (need >= {min_blocks})")
    elif not enough_blocks:
        why.append(f"independent month blocks {int(n_blocks)} < {min_blocks}")
    if not forward_record:
        why.append("no forward record exists for this gym yet")
    return {
        "state": "ADOPTED" if ok else "NOT_ADOPTED",
        "reliability_weight": 0.0,
        "reliability_weight_measured_not_granted": measured,
        "entered_as": "candidate field only: gut_signal {direction, confidence, "
                      "reliability_weight}",
        "never": "veto or override; it can never flip a REFUSED to a BUY, never "
                 "override a hard gate, and never act alone",
        "requires": {"min_n": min_n, "min_independent_blocks": min_blocks,
                     "forward_record": True,
                     "re_measured_on": "calibration.py's rolling window "
                                       f"(ROLLING_N={cal.ROLLING_N}, "
                                       f"ROLLING_DAYS={cal.ROLLING_DAYS})"},
        "n_independent_blocks": (int(n_blocks) if blocks_known else None),
        "why_not": "; ".join(why) or None,
        "line": adoption_line(n_graded, forward_record=forward_record,
                              n_blocks=n_blocks),
    }


def adoption_line(n_graded: int, *, forward_record: bool = False,
                  n_blocks: int | None = None) -> str:
    """The one line a reader greps for. Derived, never a stored string."""
    min_n = int(config.SCENARIO_GYM_ADOPT_MIN_N)
    min_blocks = int(config.SCENARIO_GYM_ADOPT_MIN_BLOCKS)
    if (int(n_graded) >= min_n and forward_record
            and n_blocks is not None and int(n_blocks) >= min_blocks):
        return (f"adoption: ELIGIBLE - N {int(n_graded)} >= {min_n} over "
                f"{int(n_blocks)} >= {min_blocks} independent blocks and a forward "
                "record exists; the weight is still set by the rolling "
                "calibration, never by hand")
    return (f"adoption: NOT_ADOPTED — reliability_weight 0 until N>={min_n} "
            f"over >={min_blocks} independent month blocks and a forward "
            "record exists")


# ══════════════════════════════════════════════════════════════ the P1-P6

def _protocol(paths: dict, *, flip_rate=None, flip_n=0, realised_bps=None,
              calib: dict | None = None, nothing_was_read: bool = False) -> dict:
    calib = calib or {}
    return pp.block(
        anonymised=not nothing_was_read,
        anonymised_evidence=paths.get("masked_digests"),
        placebo_run=not nothing_was_read,
        placebo_evidence=paths.get("shuffled_control"),
        time_locked_run=False,
        time_locked_model=("ChronoGPT is not distributed as GGUF and needs a "
                           "transformers path this job does not have (spec_lane_x "
                           "section 1.6); the date SHIFT is a fiction device here, "
                           "not a time-locked model"),
        cutoff="2024-06-30", cutoff_source=(
            "community cutoff trackers + provider pages for Qwen2.5-7B-Instruct; NOT "
            "an official Alibaba cutoff page (spec_lane_x section 1.3)"),
        cutoff_confidence="MEDIUM",
        universe_vintage_id=paths.get("universe_vintage_id"),
        delisting_handled=True,
        universe_note=("the forward label requires the SUCCESSOR month to be literally "
                       "the next one, so a delisted or halted name contributes no "
                       "two-month return labelled as one "
                       "(night_r2_monthly_llm.widened_forward_excess)"),
        flip_pass_rate=flip_rate, flip_n=int(flip_n),
        flip_test=("the twin test IS this job's direction-flip test: one appended "
                   "development of known sign, and the rate at which the committed "
                   "decision's direction flips with it"),
        ece=calib.get("ece"), n_bins=10, brier=calib.get("brier"),
        brier_decomposition=calib.get("brier_decomposition") or {},
        cost_curve_id="r2_trial.COST_BPS_PER_SIDE (25 bps/side on realised turnover)",
        cost_bps_per_side=COST_BPS_PER_SIDE, realised_bps=realised_bps,
        costed=not nothing_was_read, gross_reported_separately=True,
        single_agent_baseline_run=True,
        field_provenance={
            "direction, size_pct, expected_return_20d, confidence, falsifier":
                "Qwen2.5-7B-Instruct-Q4_K_M via this job's frozen SYSTEM+PROMPT "
                "(sha256 on the receipt), temperature 0",
            "good_twin / bad_twin / control_good_twin / control_bad_twin text":
                "DETERMINISTIC: night_scenario_gym.DEVELOPMENT_FAMILIES keyed by the "
                "cell's dominant typed event, hashed as counterfactual_library_hash. "
                "No model wrote a twin",
            "masking": "night_r2_monthly_llm.widened_digests, i.e. "
                       "r7_news_representation.mask_company over tokenise -- the same "
                       "function night_x_anonymisation_gap masks with",
            "date shift": "night_scenario_gym.shift_dates, a fixed per-cell seeded "
                          "offset; numbers are kept verbatim",
            "fwd": "deterministic: SPY-excess open-to-open month return from bars.parquet",
            "movement, lift, t": "deterministic arithmetic in night_scenario_gym",
        },
        homogeneity_metric=None)


# ══════════════════════════════════════════════════════════════════ the job

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _answered(path: Path) -> set:
    """`(arm, symbol, month)` already on disk. The cursor IS the answers file.

    A separate cursor file can disagree with the answers beside it; this one
    cannot, because it is derived from them.
    """
    done = set()
    if not path.is_file():
        return done
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        done.add((str(r.get("tag")), str(r.get("name")), str(r.get("month"))))
    return done


def _load_rows(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _ask(text: str, backend: str, max_tokens: int) -> tuple[dict | None, str, dict, str | None]:
    """One completion. `(decision, class_or_ok, usage, why)` -- never raises.

    `LanguageRefused` is its own class because it is its own finding: the
    language pin lives in `free_inference.complete` and a refused reply is
    REFUSED, not repaired and not retried (CLAUDE.md, the DeepSeek lesson
    applied to the local path). A `ProviderRefusal` mid-run is the reader
    having stopped answering, which is the same state `PENDING_MODEL` names
    before the run starts.
    """
    try:
        rep = fi.complete(backend, text, system=SYSTEM, max_tokens=max_tokens,
                          temperature=0.0, purpose="S2_scenario_gym")
    except LanguageRefused as exc:
        return None, "REFUSED_LANGUAGE", {"tokens_in": 0, "tokens_out": 0}, str(exc)
    except ProviderRefusal as exc:
        return None, "PENDING_MODEL", {"tokens_in": 0, "tokens_out": 0}, str(exc)
    usage = {"tokens_in": int(getattr(rep, "tokens_in", 0) or 0),
             "tokens_out": int(getattr(rep, "tokens_out", 0) or 0)}
    decision, reasons = parse_decision(getattr(rep, "text", ""))
    if decision is None:
        return None, "REFUSED_SCHEMA", usage, "; ".join(reasons[:3])
    return decision, "ok", usage, None


def S2_scenario_gym(backend: str = "local_gguf", cells: int | None = None,
                    seed: int | None = None, smoke: bool = False, run: int = 1,
                    resume: bool = False,
                    box_minutes: float | None = None) -> dict:
    """The gym: N fictional decision points, three twins each, one receipt."""
    t0 = time.time()
    seed = int(config.SCENARIO_GYM_SEED if seed is None else seed)
    box_s = float(config.SCENARIO_GYM_BOX_MINUTES if box_minutes is None
                  else box_minutes) * 60.0
    OUT.mkdir(parents=True, exist_ok=True)
    refusals = refusal_ledger()
    base = {
        "job": JOB, "lane": LANE, "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "panel": "PANEL-B", "backend": backend,
        "stage": "features",
        "PREREGISTRATION": {
            "spec": "docs/research_notes/2026-09-20/"
                    "spec_decision_engine_and_scenario_gym.md Part C",
            "brief": "Murat, 2026-09-20: a gut feeling, tested against good and "
                     "bad made-up scenarios built from our own data",
            "primary": "the twin MOVEMENT lift over the control twin, block-paired "
                       "with a Newey-West lag-2 t",
            "secondary": "sign accuracy, Brier, calibration by confidence decile, "
                         "and the net long-short against the shuffled control",
            "prompt": prompt_fingerprint(),
            "counterfactual_library_hash": library_hash(),
            "unmapped_event_ids": unmapped_event_ids(),
        },
        "question": ("Does a committed decision MOVE the right way when one "
                     "favourable or one adverse development is appended to an "
                     "otherwise byte-identical fictional scenario -- and does it "
                     "move more than it does on an unrelated appended sentence?"),
        "cost_model": {"cost_bps_per_side": COST_BPS_PER_SIDE,
                       "charged_on": "realised turnover sum|dw| per monthly rebalance"},
        "counterfactual_library_hash": library_hash(),
        "adoption_line": adoption_line(0),
    }

    try:
        panel_cells, news, funnel = widened_cells_and_docs()
    except (FileNotFoundError, ValueError) as exc:
        refusals["PENDING_MODEL"] = 0
        return {**base, "verdict": f"REFUSED: {exc}",
                "headline": "the widened panel could not be built on this checkout",
                "refusals": refusal_ledger(refusals),
                "adoption": adoption(0, {}),
                "adoption_line": adoption_line(0),
                "P1_P6": _protocol({}, nothing_was_read=True),
                "LAP": pp.lap(False, reason=(
                    "PANEL-B (2025-01..2026-09) is entirely AFTER Qwen2.5-7B's "
                    "~2024-06 cutoff, so LAP is structurally near zero here")),
                "anonymisation_gap": pp.anonymisation_gap(
                    reason="the panel could not be built, so no arm was read"),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    dig_mask, _dig_real, cov = widened_digests(panel_cells, news)
    shared = sorted(dig_mask)
    n_draw = int(config.SCENARIO_GYM_SMOKE_CELLS if smoke
                 else (cells if cells else config.SCENARIO_GYM_CELLS))
    n_draw = min(n_draw, len(shared))
    drawn = xd.stratified_cells(shared, n=n_draw, seed=seed)
    fp = xd.cells_fingerprint(drawn)
    events, ev_cov = dominant_events(drawn)
    cases = {k: build_case(dig_mask[k], k, events[k], seed=seed) for k in drawn}
    not_disjoint = sum(1 for c in cases.values()
                       for v in c["disjoint"].values() if not v)

    suffix = f"_run{run:02d}{'_smoke' if smoke else ''}"
    # THE SUFFIX GOES AFTER THE RUN NUMBER: `night_leaderboard_sync.RECEIPT` is
    # `^(?P<job>.+)_run(\d{2})\.json$`, so `S2_scenario_gym_cells_run01.json`
    # would parse as a JOB called `S2_scenario_gym_cells` and reach the board as
    # a row with no P1_P6 block -- a true statement about a file that was never
    # a receipt.
    cells_path = OUT / f"{JOB}{suffix}_cells.json"
    cells_path.write_text(json.dumps(
        {"job": JOB, "run": run, "seed": seed, "stratified_by": "month block",
         "drawn_from_cells": len(shared), **fp,
         "counterfactual_library_hash": library_hash(),
         "cells": [{"cell": list(k), "event_type": cases[k]["event_type"],
                    "family": cases[k]["family"],
                    "control_family": cases[k]["control_family"],
                    "date_offset_days": cases[k]["date_offset_days"],
                    "as_of": cases[k]["as_of"]} for k in drawn],
         "written_utc": _now()}, indent=1), encoding="utf-8")

    fwd = {(str(r.symbol), str(r.month)): float(r.excess_vw_1m)
           for r in panel_cells.itertuples()}
    sd_pct = None
    vals = [fwd[k] for k in drawn if k in fwd and np.isfinite(fwd[k])]
    if len(vals) >= 2:
        sd_pct = float(np.std(np.asarray(vals, dtype="float64"), ddof=1)) * 100

    paths = {"masked_digests": str(cells_path),
             "shuffled_control": str(cells_path), "universe_vintage_id": None}
    base.update({
        "construction": funnel, "masking": cov, "typed_events": ev_cov,
        "cells_frozen": {**fp, "file": str(cells_path), "seed": seed,
                         "stratified_by": "month block (canon section 58's "
                                          "dependence unit)",
                         "drawn_from_cells": len(shared),
                         "months": sorted({k[1] for k in drawn})},
        "fiction": {
            "entity_masking": "night_r2_monthly_llm.widened_digests (the SAME "
                              "mask_company/tokenise X_anon_gap uses)",
            "date_shift_days_range": list(config.SCENARIO_GYM_DATE_SHIFT_DAYS),
            "numbers": "kept verbatim; a bare four-digit year is not shifted",
            "twins_whose_appended_text_already_appeared_in_the_base": not_disjoint,
            "arms": list(ARMS),
        },
        "MDE": mde(0, sd_pct),
    })

    refusal = _probe(backend)
    if refusal is not None:
        planned = len(drawn) * len(ARMS)
        refusals["PENDING_MODEL"] = planned
        return {**base,
                "refusals": refusal_ledger(refusals),
                "adoption": adoption(0, {}),
                "adoption_line": adoption_line(0),
                "P1_P6": _protocol(paths),
                "LAP": pp.lap(False, reason=(
                    "PANEL-B is entirely AFTER Qwen2.5-7B's ~2024-06 cutoff, so "
                    "every cell here is already the post-cutoff arm")),
                "anonymisation_gap": pp.anonymisation_gap(reason=(
                    "PENDING_MODEL: no arm was read, so there is no gap. The cell "
                    "list and the twin library are frozen and hashed so the run "
                    "that measures it asks the same question")),
                "pending_when_the_reader_is_up": [
                    f"real: the {len(drawn)} frozen fictional cases",
                    "good_twin / bad_twin: the SAME cases with one appended "
                    "development of known sign from the frozen library",
                    "control_good_twin / control_bad_twin: the same cases with one "
                    "appended development from an UNRELATED family, sign-matched to "
                    "the twin each one is differenced against -- the 'would it have "
                    "moved anyway on a sentence of this tone' baseline",
                    "control_shuffled: the same cells given a digest from a "
                    f"different month (rng seed {seed})",
                    f"one command: python -m scripts.night_scenario_gym "
                    f"--cells {n_draw} --seed {seed} --run {run}",
                ],
                "verdict": (
                    "PENDING_MODEL: the cell draw, the fiction, the twins and the "
                    "grading are built and frozen; the reader is not answering and "
                    "this job does not start it (the desktop shell owns "
                    f"llama-server). Probe said: {refusal}"),
                "headline": (
                    f"{len(drawn)} cases over {len(set(k[1] for k in drawn))} month "
                    f"blocks frozen at sha256 {fp['cells_sha256'][:12]}, twin library "
                    f"{library_hash()[:12]}; {planned} calls PENDING_MODEL"),
                "elapsed_s": round(time.time() - t0, 1), "written_utc": _now()}

    rows_path = OUT / f"{JOB}_answers{suffix}.jsonl"
    if not resume and rows_path.exists():
        rows_path.unlink()
    done = _answered(rows_path) if resume else set()
    rng = random.Random(seed)
    max_tokens = int(config.SCENARIO_GYM_MAX_TOKENS)
    tokens_in = tokens_out = asked = 0
    stopped_reason: str | None = None
    consecutive_pending = 0

    with rows_path.open("a", encoding="utf-8") as fh:
        for arm in ARMS:
            for i, k in enumerate(drawn):
                if STOP.exists():
                    stopped_reason = f"STOP file present; {arm} ended after {i} cases"
                    print(f"    {stopped_reason}", flush=True)
                    break
                if time.time() - t0 >= box_s:
                    stopped_reason = (f"the {box_s / 60:.0f}-minute box was reached "
                                      f"during {arm} after {i} cases")
                    print(f"    {stopped_reason}", flush=True)
                    break
                if consecutive_pending >= MAX_CONSECUTIVE_PENDING:
                    # the reader went away mid-run. Keeping the loop going would
                    # spend the box writing PENDING_MODEL rows at the speed of a
                    # failing socket and bury the answers already on disk.
                    # `--resume` continues from exactly here.
                    stopped_reason = (f"{consecutive_pending} consecutive provider "
                                      f"refusals during {arm}: the reader stopped "
                                      "answering; re-run with --resume when it is up")
                    print(f"    {stopped_reason}", flush=True)
                    break
                if (arm, str(k[0]), str(k[1])) in done:
                    continue
                case = cases[k]
                if arm == "control_shuffled":
                    other = [j for j in drawn if j[1] != k[1]]
                    if not other:
                        continue
                    text = PROMPT.format(case_id=f"{arm}-{i:04d}",
                                         as_of=case["as_of"],
                                         digest=cases[rng.choice(other)]["texts"]["real"])
                else:
                    text = PROMPT.format(case_id=f"{arm}-{i:04d}",
                                         as_of=case["as_of"],
                                         digest=case["texts"][arm])
                decision, status, usage, why = _ask(text, backend, max_tokens)
                tokens_in += usage["tokens_in"]
                tokens_out += usage["tokens_out"]
                asked += 1
                if status != "ok":
                    refusals[status] = refusals.get(status, 0) + 1
                consecutive_pending = (consecutive_pending + 1
                                       if status == "PENDING_MODEL" else 0)
                row = decision_row(case, arm, decision, fwd=fwd.get(k),
                                   refusal=None if status == "ok" else status)
                row["refusal_reason"] = why
                fh.write(json.dumps(row) + "\n")
                if (i + 1) % 25 == 0:
                    fh.flush()
                    print(f"    {arm}: {i + 1}/{len(drawn)}, "
                          f"{time.time() - t0:.0f}s", flush=True)
            if stopped_reason:
                break

    rows = _load_rows(rows_path)
    by_arm: dict[str, list[dict]] = {a: [] for a in ARMS}
    for r in rows:
        by_arm.setdefault(str(r.get("tag")), []).append(r)
    graded_half = grade_and_adopt(by_arm, refusals=refusals, sd_pct=sd_pct)
    s = graded_half.pop("_summary")
    calib = graded_half["calibration"]

    out = {
        **base,
        **graded_half,
        "answers_file": str(rows_path),
        "resumed": bool(resume), "already_on_disk_at_start": len(done),
        "stopped_early": bool(stopped_reason), "stopped_reason": stopped_reason,
        "usage": {"tokens_in": tokens_in, "tokens_out": tokens_out,
                  "cost_usd": 0.0, "calls": asked,
                  "planned_calls": len(drawn) * len(ARMS)},
        "P1_P6": _protocol(paths, flip_rate=s["flip_rate"], flip_n=s["flip_n"],
                           realised_bps=s["realised_bps"], calib=calib),
        "LAP": pp.lap(False, reason=(
            "PANEL-B is entirely AFTER Qwen2.5-7B's ~2024-06 cutoff, so every case "
            "here is already the post-cutoff arm; the date shift makes the case "
            "unlookuppable, it does not make the model older")),
        "anonymisation_gap": pp.anonymisation_gap(reason=(
            "not measured by this job: every arm reads the MASKED text, so there is "
            "no raw arm to difference. X_anon_gap measures the gap on these cells")),
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }
    fired = {k: v for k, v in out["refusals"].items() if v} or "none"
    out["headline"] = (
        f"{len(drawn)} cases x {len(ARMS)} arms, {asked} calls: gut score "
        f"{s['gut_score']} (good up {s['good_up_rate']}, bad down "
        f"{s['bad_down_rate']}), vs control {s['gut_score_vs_control_pp']} pp "
        f"(good t {s['good_t']}, bad t {s['bad_t']}); sign accuracy "
        f"{s['sign_accuracy']}; refusals {fired}; NOT_ADOPTED")
    out["verdict"] = (
        "NOT_ADOPTED (reliability_weight 0): the gym measures whether the reader's "
        "decision MOVES with the story. " + str(out["adoption"]["line"]).replace(
            "—", "-"))
    out["family_max_p"] = None
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="local_gguf")
    ap.add_argument("--cells", type=int, default=None,
                    help="decision points; default config.SCENARIO_GYM_CELLS")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--box-minutes", type=float, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    p = S2_scenario_gym(backend=a.backend, cells=a.cells, seed=a.seed,
                        smoke=a.smoke, run=a.run, resume=a.resume,
                        box_minutes=a.box_minutes)
    p["run"] = a.run
    OUT.mkdir(parents=True, exist_ok=True)
    out = (Path(a.out) if a.out else
           OUT / f"{JOB}_run{a.run:02d}{'_smoke' if a.smoke else ''}.json")
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\n{JOB}: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
