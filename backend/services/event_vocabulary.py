"""L2 -- the frozen typed-event vocabulary, as code, with a hash.

WHAT THIS IS
============
`docs/research_notes/2026-09-11/spec_events_and_calibration.md` section 1.2 is a
markdown table: 39 substantive event ids plus `no_event`, each with a
definition, the 8-K item(s) it maps to, a direction PRIOR, a typical magnitude
bucket, one example headline and one counter-example. This module is that table
as data, plus the section 1.3 definitions of `direction`, `magnitude_bucket` and
`confidence` that make two extractions comparable by Cohen's kappa.

WHY A TABLE AND A HASH RATHER THAN A TUPLE OF STRINGS
=====================================================
`scenario_forecasts.EVENT_TYPES` already carries the 40 ids, and that was enough
for a schema enum. It is not enough for an extraction prompt: the model is shown
the DEFINITIONS and the counter-examples, so a silent edit to a definition
changes what the model was asked without changing any id. `VOCABULARY_HASH`
covers every field of every row, is stamped into every typed row L2 writes, and
is what lets a later reader say whether two rows were typed against the same
vocabulary. It is computed over a canonical serialisation with sorted keys, so
reordering the dataclass fields does not move it -- editing a definition does.

THE COUNT, AND THE SPEC'S OWN MISCOUNT
======================================
The section heading says "39 event types + `no_event`"; the section's closing
sentence says "38 substantive + `no_event` = 39". The TABLE has 39 substantive
rows, so the heading is right and the sentence is off by one.
`test_event_vocabulary.py` derives the count from the table rather than from
either sentence -- which is also why `N_SUBSTANTIVE` below is computed and not
typed.

DIRECTION PRIOR IS A PRIOR, NOT A LABEL
=======================================
`direction_prior` is `None` for every "ambiguous" row, because the true sign
depends on content the reader must read (beat vs miss, upgrade vs downgrade). It
exists for calibration sanity-checking: if the extractor's realised direction for
`bankruptcy_or_going_concern` comes back positive 40% of the time, either the
reader or the prior is wrong and somebody should look. It is NOT a default the
extractor may fall back on, and nothing here fills a missing direction from it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

#: `magnitude_bucket`, ordered. Spec section 1.3: thresholds are on the expected
#: |same-scope abnormal return| over the next 1-2 sessions, and deliberately NOT
#: scaled by market cap (`AEGIS_STRATEGIC_INVARIANTS.md`: size does not bound the
#: move -- the repo's own chain implied 5.10% in one session for a ~$5T company,
#: which is why LARGE starts at 5%).
MAGNITUDE_BUCKETS: tuple[str, ...] = ("NEGLIGIBLE", "SMALL", "MODERATE", "LARGE", "EXTREME")

#: (lower, upper) bound on expected |abnormal return|, as a FRACTION. EXTREME has
#: no upper bound, and `None` says so rather than a large number pretending to be
#: one.
MAGNITUDE_THRESHOLDS: dict[str, tuple[float, float | None]] = {
    "NEGLIGIBLE": (0.0, 0.005),
    "SMALL": (0.005, 0.02),
    "MODERATE": (0.02, 0.05),
    "LARGE": (0.05, 0.10),
    "EXTREME": (0.10, None),
}

#: The ONLY admissible values of `direction`, relative to the named scope entity
#: and never to the market.
DIRECTIONS: tuple[int, ...] = (-1, 0, 1)

DIRECTION_DEFINITIONS: dict[int, str] = {
    1: ("the event, taken alone, is expected to move the scope entity's price UP "
        "relative to its pre-event expectation"),
    -1: "expected DOWN, same frame",
    0: ("the event is real and dated but has no directional implication by itself "
        "-- a regular dividend declaration at an unchanged rate, a scheduled "
        "earnings date with no number attached, `no_event`"),
}

#: Why there is no fourth value. Quoted in the prompt and in every prereg that
#: reports a kappa: an escape hatch one prompt uses more than the other makes the
#: two incomparable, which is the whole point of the inter-rater control.
NO_FOURTH_DIRECTION = (
    "There is no value for 'I do not know'. A genuinely uncertain call commits to "
    "the best-guess sign AND sets `confidence` low. Cohen's kappa cannot be "
    "computed over a set that includes an escape hatch one rater uses more than "
    "the other.")

CONFIDENCE_DEFINITION = (
    "`confidence` in [0, 1] is the model's stated probability that the emitted "
    "(event_type, direction) PAIR, taken together, is the correct reading of the "
    "document. It is NOT `event_intel.extraction.tier`, which is a PARSE-FIDELITY "
    "judgment (HIGH/MEDIUM/LOW/FAILED) barred by the D4 closure ruling from being "
    "read as an outcome probability. This one IS allowed to be read as a "
    "probability, because inter-rater kappa is the external check that catches a "
    "reader free-lancing high confidence.")

#: How two prompts (or two checkpoints) are compared on the same sample.
KAPPA_PROTOCOL = {
    "event_type": "Cohen's kappa, 40-way categorical, unweighted",
    "direction": "weighted kappa, ordinal -1/0/+1, LINEAR weights",
    "magnitude_bucket": "weighted kappa, ordinal over MAGNITUDE_BUCKETS, LINEAR weights",
    "confidence": "mean absolute difference -- it is continuous, so kappa does not apply",
    "sample": "the SAME rows under both prompts; the spec's control is 500 rows",
}

NO_EVENT = "no_event"


@dataclass(frozen=True)
class EventType:
    """One row of the frozen vocabulary, verbatim from the spec's own table."""

    id: str
    definition: str
    #: 8-K item codes parsed out of `sec_items_text` (`()` when the row maps to none).
    sec_items: tuple[str, ...]
    #: the spec's 8-K cell as written, including the "(Forms 3/4/13D/13F, not
    #: 8-K)" style notes that carry information a code tuple cannot.
    sec_items_text: str
    #: `None` when the spec's prior is "ambiguous": the sign depends on content.
    direction_prior: int | None
    #: the spec's direction-prior cell, verbatim.
    direction_prior_text: str
    magnitude_bucket: str
    example: str
    counter_example: str


def _prior(text: str) -> int | None:
    """The spec's prose prior as a sign, or `None` for ambiguous.

    "positive (target) / ambiguous (acquirer)" and "ambiguous (positive on
    addition, negative on removal)" are both AMBIGUOUS: they name two signs, and
    collapsing either to one would be the prior asserting what only the document
    can say.
    """
    t = text.strip().lower()
    if t.startswith("ambiguous"):
        return None
    if t.startswith("neutral"):
        return 0
    if "ambiguous" in t:
        return None
    if t.startswith("positive"):
        return 1
    if t.startswith("negative"):
        return -1
    raise ValueError(f"unrecognised direction prior: {text!r}")


def _t(id_, definition, sec_items, sec_items_text, prior_text, magnitude,
       example, counter_example) -> EventType:
    if magnitude not in MAGNITUDE_BUCKETS:
        raise ValueError(f"{id_}: {magnitude!r} is not a magnitude bucket")
    return EventType(id=id_, definition=definition, sec_items=tuple(sec_items),
                     sec_items_text=sec_items_text, direction_prior=_prior(prior_text),
                     direction_prior_text=prior_text, magnitude_bucket=magnitude,
                     example=example, counter_example=counter_example)


#: THE TABLE. Generated from the spec's markdown and checked back against it by
#: `test_event_vocabulary.py`, which re-parses that table on every run -- an edit
#: to either side that does not reach the other is a red suite, not a drift.
VOCABULARY: tuple[EventType, ...] = (
    _t(
        "earnings_report",
        "Company reports a completed period's financial results (EPS/revenue) vs. consensus or vs. year-ago.",
        ('2.02',),
        "2.02",
        "ambiguous",
        "MODERATE",
        "\"Acme Corp reports Q3 EPS of $1.20, beating estimates of $1.05\"",
        "A forward-looking statement issued separately from the print → `guidance_change`.",
    ),
    _t(
        "earnings_preannouncement",
        "Company discloses expected results BEFORE the scheduled report date (profit warning or positive pre-announce).",
        ('2.02', '7.01'),
        "2.02 / 7.01",
        "ambiguous",
        "MODERATE",
        "\"Acme warns Q3 revenue will miss guidance, cites soft demand\"",
        "The scheduled earnings date itself with no number attached → `no_event` (calendar item).",
    ),
    _t(
        "guidance_change",
        "Company raises, cuts, reaffirms, or withdraws forward financial guidance.",
        ('7.01', '8.01'),
        "7.01 / 8.01",
        "ambiguous",
        "MODERATE",
        "\"Acme raises full-year revenue guidance to $4.1-4.3B\"",
        "A one-time earnings print with no forward statement → `earnings_report`.",
    ),
    _t(
        "mergers_acquisitions",
        "One company agrees to acquire, or be acquired by, another (definitive agreement or completion).",
        ('1.01', '2.01'),
        "1.01, 2.01",
        "positive (target) / ambiguous (acquirer)",
        "LARGE",
        "\"Acme to acquire Widget Inc for $2.1B in cash and stock\"",
        "Rumor/speculation with no confirmed deal → still `mergers_acquisitions` but `confidence` low and `evidence_span` must quote hedge language (\"in talks\", \"considering\").",
    ),
    _t(
        "divestiture_asset_sale",
        "Company sells a business unit, subsidiary, or major asset (not the whole company).",
        ('2.01',),
        "2.01",
        "ambiguous",
        "MODERATE",
        "\"Acme sells its European logistics unit to PE firm for $400M\"",
        "Sale of the entire company → `mergers_acquisitions`.",
    ),
    _t(
        "spinoff",
        "Company separates a division into an independent, separately-traded entity.",
        ('2.01', '8.01'),
        "2.01 / 8.01",
        "ambiguous",
        "LARGE",
        "\"Acme to spin off its healthcare division as a standalone public company\"",
        "A minority stake sale with no new listing → `divestiture_asset_sale`.",
    ),
    _t(
        "bankruptcy_or_going_concern",
        "Chapter 11/7 filing, receivership, or auditor's going-concern doubt disclosed.",
        ('1.03', '4.02'),
        "1.03, 4.02",
        "negative",
        "EXTREME",
        "\"Acme Corp files for Chapter 11 bankruptcy protection\"",
        "A debt covenant warning with no bankruptcy filing → `debt_covenant_or_default_trigger`.",
    ),
    _t(
        "delisting_or_listing_risk",
        "Exchange notifies of non-compliance, delisting, or the company voluntarily delists/uplists.",
        ('3.01',),
        "3.01",
        "negative",
        "LARGE",
        "\"NYSE notifies Acme of non-compliance with minimum share price rule\"",
        "A reverse split done proactively with no exchange notice → `reverse_stock_split`.",
    ),
    _t(
        "debt_issuance_or_obligation",
        "Company issues new debt or enters a material financial obligation (bond, credit facility).",
        ('2.03',),
        "2.03",
        "ambiguous",
        "MODERATE",
        "\"Acme issues $500M in senior notes due 2033\"",
        "The obligation being triggered/accelerated by a covenant breach → `debt_covenant_or_default_trigger`.",
    ),
    _t(
        "debt_covenant_or_default_trigger",
        "An existing obligation is accelerated, a covenant is breached, or default is triggered.",
        ('2.04',),
        "2.04",
        "negative",
        "LARGE",
        "\"Acme triggers cross-default clause on $200M term loan\"",
        "Routine refinancing with no breach → `debt_issuance_or_obligation`.",
    ),
    _t(
        "equity_issuance_dilution",
        "Company sells new shares (secondary offering, private placement, convertible) diluting existing holders.",
        ('3.02',),
        "3.02",
        "negative",
        "MODERATE",
        "\"Acme prices $300M secondary offering at $42/share\"",
        "A buyback (share count DOWN, not up) → `stock_buyback`.",
    ),
    _t(
        "stock_buyback",
        "Company authorizes or executes a share repurchase program. (EDT: `Stock Repurchase`)",
        ('8.01',),
        "— / 8.01",
        "positive",
        "SMALL",
        "\"Acme board authorizes $1B share buyback program\"",
        "A tender offer to acquire a DIFFERENT company → `mergers_acquisitions`.",
    ),
    _t(
        "dividend_increase",
        "Regular per-share dividend is raised. (EDT: `Dividend Increase`)",
        ('8.01',),
        "— / 8.01",
        "positive",
        "SMALL",
        "\"Acme raises quarterly dividend 8% to $0.54/share\"",
        "Initiating a dividend for the first time → still this type, note \"initiation\" in `evidence_span`.",
    ),
    _t(
        "dividend_cut_or_suspension",
        "Regular dividend is cut or suspended. (EDT: `Dividend Cut`)",
        ('8.01',),
        "— / 8.01",
        "negative",
        "MODERATE",
        "\"Acme suspends dividend to preserve cash amid downturn\"",
        "A special (one-time) dividend not being paid again → `no_event` (it was never regular).",
    ),
    _t(
        "special_dividend",
        "A one-time, non-recurring dividend is declared. (EDT: `Special Dividend`)",
        ('8.01',),
        "— / 8.01",
        "positive",
        "SMALL",
        "\"Acme declares special dividend of $2.00/share following asset sale\"",
        "The regular quarterly dividend amount → `dividend_increase`/`no_event`.",
    ),
    _t(
        "regular_dividend_declaration",
        "Routine declaration of the regular dividend at an unchanged rate. (EDT: `Regular Dividend`)",
        (),
        "—",
        "neutral (0)",
        "NEGLIGIBLE",
        "\"Acme declares regular quarterly dividend of $0.50/share\"",
        "Any change in rate → `dividend_increase`/`dividend_cut_or_suspension`.",
    ),
    _t(
        "stock_split",
        "Forward stock split (share count up, price down, no fundamental change). (EDT: `Stock Split`)",
        ('8.01',),
        "— / 8.01",
        "ambiguous",
        "SMALL",
        "\"Acme announces 4-for-1 stock split\"",
        "Reverse split → `reverse_stock_split`.",
    ),
    _t(
        "reverse_stock_split",
        "Reverse split (share count down, price up), often defensive. (EDT: `Reverse Stock Split`)",
        ('3.01',),
        "— / 3.01-adjacent",
        "negative",
        "SMALL",
        "\"Acme completes 1-for-10 reverse stock split to regain Nasdaq compliance\"",
        "Forward split → `stock_split`.",
    ),
    _t(
        "credit_rating_change",
        "A rating agency upgrades, downgrades, or changes outlook on the company's debt.",
        ('8.01',),
        "— / 8.01",
        "ambiguous",
        "MODERATE",
        "\"Moody's downgrades Acme to Ba1, outlook negative\"",
        "The company's own guidance change → `guidance_change`.",
    ),
    _t(
        "new_contract_or_partnership",
        "Company signs a material new customer contract, supply deal, or strategic partnership. (EDT: `New Contract`)",
        ('1.01',),
        "1.01",
        "positive",
        "SMALL",
        "\"Acme signs 5-year, $800M supply agreement with MegaCorp\"",
        "An acquisition of the partner company → `mergers_acquisitions`.",
    ),
    _t(
        "contract_loss_or_termination",
        "A material contract is terminated or lost (by either party).",
        ('1.02',),
        "1.02",
        "negative",
        "SMALL",
        "\"Acme loses renewal of $150M contract with largest customer\"",
        "The contract expiring on schedule with no early termination → `no_event`.",
    ),
    _t(
        "product_launch_or_innovation",
        "Company launches, unveils, or announces a new product/service.",
        ('8.01',),
        "8.01",
        "ambiguous",
        "SMALL",
        "\"Acme unveils next-generation chip architecture\"",
        "A product being recalled → `product_recall_or_defect`.",
    ),
    _t(
        "product_recall_or_defect",
        "Company recalls a product or discloses a material defect/safety issue.",
        ('8.01',),
        "8.01",
        "negative",
        "MODERATE",
        "\"Acme recalls 2.1M vehicles over brake defect\"",
        "A competitor's product recall mentioned in passing → `no_event` for this scope (direction only applies to the named scope entity).",
    ),
    _t(
        "clinical_trial_result",
        "Biotech/pharma discloses a clinical trial result, readout, or data milestone (not FDA action itself). (EDT: `Clinical Trials`)",
        ('8.01',),
        "8.01",
        "ambiguous",
        "LARGE",
        "\"Acme Therapeutics reports Phase 3 trial met primary endpoint\"",
        "The FDA's approval/rejection decision itself → `regulatory_approval`/`regulatory_investigation_or_action`.",
    ),
    _t(
        "regulatory_approval",
        "A regulator (FDA, FCC, antitrust body, etc.) approves a product, deal, or application.",
        ('8.01',),
        "8.01",
        "positive",
        "LARGE",
        "\"FDA approves Acme's lead drug candidate for commercial sale\"",
        "The company's own trial readout submitted TO the regulator → `clinical_trial_result`.",
    ),
    _t(
        "regulatory_investigation_or_action",
        "A regulator opens an investigation, files a complaint, imposes a fine, or denies approval.",
        ('8.01',),
        "8.01",
        "negative",
        "MODERATE",
        "\"SEC opens formal investigation into Acme's revenue recognition\"",
        "A private lawsuit with no regulator involved → `litigation_filed`.",
    ),
    _t(
        "litigation_filed",
        "A lawsuit, arbitration, or legal claim is filed against or by the company.",
        ('8.01',),
        "8.01",
        "negative",
        "SMALL",
        "\"Shareholders file class-action suit against Acme over disclosure\"",
        "Settlement of an existing suit → `litigation_settlement`.",
    ),
    _t(
        "litigation_settlement",
        "An existing legal matter is settled, dismissed, or resolved.",
        ('8.01',),
        "8.01",
        "ambiguous",
        "SMALL",
        "\"Acme settles patent dispute with Rival Corp for $40M\"",
        "The filing of the original suit → `litigation_filed`.",
    ),
    _t(
        "management_change_departure",
        "A named executive or director departs, resigns, or is removed.",
        ('5.02',),
        "5.02",
        "negative",
        "SMALL",
        "\"Acme CEO steps down effective immediately, no successor named\"",
        "A planned, announced-well-in-advance retirement with a named successor → still this type; `evidence_span` should note \"planned\" (affects magnitude, not type).",
    ),
    _t(
        "management_change_appointment",
        "A named executive or director is appointed or promoted.",
        ('5.02',),
        "5.02",
        "ambiguous",
        "SMALL",
        "\"Acme names former Rival Corp CFO as new Chief Financial Officer\"",
        "The prior person's departure in the same article → both types emitted (one row per document per §2, so extract the DOMINANT one; see §2.4).",
    ),
    _t(
        "auditor_or_accounting_change",
        "Company changes its auditor, or restates/non-relies on prior financials.",
        ('4.01', '4.02'),
        "4.01, 4.02",
        "negative",
        "MODERATE",
        "\"Acme dismisses auditor, restates two years of financial statements\"",
        "A routine, non-restatement auditor rotation with no dispute → magnitude drops to SMALL, type unchanged.",
    ),
    _t(
        "cybersecurity_incident",
        "Company discloses a material cybersecurity breach or incident.",
        ('1.05',),
        "1.05",
        "negative",
        "MODERATE",
        "\"Acme discloses ransomware attack affecting customer data\"",
        "A routine security-patch announcement with no breach → `no_event`.",
    ),
    _t(
        "insider_or_institutional_ownership_change",
        "A Form 4 insider transaction or a 13F/13D institutional stake change is disclosed.",
        (),
        "— (Forms 3/4/13D/13F, not 8-K)",
        "ambiguous",
        "NEGLIGIBLE",
        "\"Acme CEO sells 50,000 shares under a 10b5-1 plan\"",
        "A tender offer to acquire the whole company → `mergers_acquisitions`.",
    ),
    _t(
        "macro_rate_decision",
        "A central bank (Fed, ECB, BOJ, PBOC, etc.) announces or changes a policy interest rate.",
        (),
        "—",
        "ambiguous",
        "MODERATE",
        "\"Fed raises rates 25bp to 5.00-5.25%, signals one more hike\"",
        "A rate-related comment by a company executive, not a central bank → `no_event` for macro, may still tag the company's own type.",
    ),
    _t(
        "macro_inflation_print",
        "A CPI/PCE/inflation statistic is released.",
        (),
        "—",
        "ambiguous",
        "SMALL",
        "\"US CPI rises 3.2% y/y, above the 3.0% consensus\"",
        "A company's own cost inflation commentary in an earnings call → `earnings_report`/`guidance_change`.",
    ),
    _t(
        "macro_labor_report",
        "A jobs/employment statistic (NFP, unemployment rate, etc.) is released.",
        (),
        "—",
        "ambiguous",
        "SMALL",
        "\"US adds 180,000 jobs in August, unemployment holds at 4.1%\"",
        "Company-specific layoffs → `no_event` at the macro scope; tag the company scope separately if a per-ticker row exists.",
    ),
    _t(
        "tariff_or_trade_policy",
        "A government announces, imposes, or changes tariffs or trade restrictions.",
        (),
        "—",
        "negative",
        "MODERATE",
        "\"US announces 25% tariff on imported steel and aluminum\"",
        "A company passing costs through via price increases → `guidance_change` for that company.",
    ),
    _t(
        "sanction",
        "A government imposes or lifts sanctions on a country, entity, or individual.",
        (),
        "—",
        "negative",
        "MODERATE",
        "\"Treasury sanctions three companies over export control violations\"",
        "A company's own compliance investigation unrelated to sanctions → `regulatory_investigation_or_action`.",
    ),
    _t(
        "index_rebalance",
        "A stock is added to or removed from a major index (S&P 500, Russell, etc.).",
        (),
        "—",
        "ambiguous (positive on addition, negative on removal)",
        "SMALL",
        "\"Acme Corp set to join the S&P 500, replacing Widget Inc\"",
        "A company's own share buyback changing its float → `stock_buyback`.",
    ),
    _t(
        "no_event",
        "The document contains no new, dated, decision-relevant information about the scope entity — a recap, opinion piece, old-news restatement, analyst commentary with no new fact, or pure noise.",
        (),
        "—",
        "neutral (0)",
        "NEGLIGIBLE",
        "\"5 things to know about Acme Corp before the market opens\"",
        "Any of the 38 types above, even if buried in an otherwise fluffy article — `no_event` is for documents with NOTHING extractable, not low-magnitude documents.",
    ),
)

#: The ids, in the spec's order. `no_event` is last.
EVENT_TYPES: tuple[str, ...] = tuple(t.id for t in VOCABULARY)

#: Everything that is not the refusal class.
SUBSTANTIVE_TYPES: tuple[str, ...] = tuple(t for t in EVENT_TYPES if t != NO_EVENT)

#: DERIVED, never typed: the spec's prose miscounts and the table does not.
N_TYPES = len(EVENT_TYPES)
N_SUBSTANTIVE = len(SUBSTANTIVE_TYPES)

_BY_ID: dict[str, EventType] = {t.id: t for t in VOCABULARY}


def by_id(event_type: str) -> EventType:
    """One row, or a `KeyError` that names the vocabulary.

    An unknown id is a REFUSAL: a novel string passed through silently is exactly
    the enum drift `event_extraction`'s schema validation exists to catch.
    """
    try:
        return _BY_ID[event_type]
    except KeyError:
        raise KeyError(
            f"{event_type!r} is not in the frozen L2 vocabulary "
            f"({N_TYPES} ids, hash {VOCABULARY_HASH[:12]}). Add it to the spec's "
            "table AND here, and the hash moves -- which is the point: rows typed "
            "before and after are then distinguishable."
        ) from None


def table() -> list[dict]:
    """The vocabulary as plain dicts -- what the hash is taken over, and what a
    receipt embeds."""
    return [asdict(t) for t in VOCABULARY]


def vocabulary_hash(rows: list[dict] | None = None) -> str:
    """sha256 over the canonical serialisation.

    `sort_keys=True` so the hash is a function of the CONTENT and not of the
    dataclass's field order; the row ORDER is significant and is preserved,
    because the spec's order is itself part of the frozen contract -- the JSON
    Schema enum is generated from it.
    """
    payload = json.dumps(rows if rows is not None else table(),
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


VOCABULARY_HASH: str = vocabulary_hash()


def items_index() -> dict[str, tuple[str, ...]]:
    """8-K item code -> the vocabulary ids that name it.

    One item maps to several ids (2.01 is an acquisition, a divestiture AND a
    spinoff), which is why this does not and cannot replace `edgar_events`'s
    item -> direction map: that one is a function, this one is a relation.
    """
    out: dict[str, list[str]] = {}
    for t in VOCABULARY:
        for item in t.sec_items:
            out.setdefault(item, []).append(t.id)
    return {k: tuple(v) for k, v in sorted(out.items())}


def declaration() -> dict:
    """What a receipt prints to say which vocabulary typed its rows."""
    return {
        "source": ("docs/research_notes/2026-09-11/spec_events_and_calibration.md "
                   "section 1.2 (the TABLE; the section's closing sentence "
                   "miscounts by one)"),
        "n_types": N_TYPES,
        "n_substantive": N_SUBSTANTIVE,
        "n_ambiguous_priors": sum(1 for t in VOCABULARY if t.direction_prior is None),
        "refusal_class": NO_EVENT,
        "vocabulary_hash": VOCABULARY_HASH,
        "magnitude_thresholds": {k: list(v) for k, v in MAGNITUDE_THRESHOLDS.items()},
        "directions": list(DIRECTIONS),
        "no_fourth_direction": NO_FOURTH_DIRECTION,
        "confidence": CONFIDENCE_DEFINITION,
        "kappa_protocol": KAPPA_PROTOCOL,
    }
