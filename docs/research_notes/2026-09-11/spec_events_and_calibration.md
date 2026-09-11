# SPEC: Typed Event Vocabulary + Extraction Contract + Calibration Reporting

Status: DRAFT for builder implementation (Aegis Finance, roadmap
`docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
lane L item L2, lane M items M1/M3/M4). Written 2026-09-11.

Sourcing note (read before implementing): every claim about an external
artifact below is marked either **[VERIFIED LIVE]** (fetched this session from
the primary source — GitHub source file, arXiv/ACL metadata, or the
`Metaculus/forecasting-tools` repo via `gh api`/`raw.githubusercontent.com`) or
**[FROM TRAINING KNOWLEDGE, NOT RE-VERIFIED THIS SESSION]** (RavenPack's public
taxonomy pages 404'd on every guessed URL this session and the web-search
budget was exhausted before a working URL was found; the SEC Form 8-K item list
is long-standing public information reproduced here from training data). Do not
promote either kind of unverified line to a `RESEARCH_CLAIM` without an
independent check — this document is licensed as research input to a
`PRODUCT_EXPERIMENT` spec, not itself a verified citation.

---

## 0. What already exists in this repo (read first, do not re-invent)

- `backend/services/event_intel.py` — an existing, live, LLM-optional event
  extractor. Its vocabulary today is **11 flat types**: `earnings, guidance,
  regulatory, ma, management_change, bankruptcy, debt, product, legal, macro,
  other` (`_ALLOWED_EVENT_TYPES`, line ~48), with `_ALLOWED_DIRECTIONS =
  {"positive", "negative", "neutral", "unknown"}` and a direction **basis**
  taxonomy already pre-committed 2026-07-29B: `EXPLICIT` (stated by a
  structured source), `IMPLIED` (inferred from headline language),
  `NEUTRAL`, `UNKNOWN`. It already has an LLM classification path
  (`_classify_llm`, DeepSeek via `llm_analyzer._call_llm`) with a strict
  system prompt asking for JSON only, and a deterministic keyword fallback
  (`_classify_keywords`). **This spec's vocabulary (§1) supersedes and
  subdivides `_ALLOWED_EVENT_TYPES`** — the new type ids marked "(existing)"
  below map onto it 1:1 so `event_intel.py` can adopt the finer vocabulary
  without a breaking change (old callers reading `event_type` get a more
  specific string from the same enum-only contract).
- `backend/services/belief_state.py` — `PredictionRecord` dataclass,
  `make_prediction()`, `calibration()`, `ledger_health()`. Schema is
  `SCHEMA_VERSION = "1.3.0"`, append-only JSONL at
  `backend/data/optimus/predictions.jsonl` (24,828+ rows per the roadmap).
  Extension in §4 is **purely additive** on this dataclass, matching how
  1.1.0/1.2.0/1.3.0 were each added (all-optional fields, `SCHEMA_VERSION`
  bump, old rows read unchanged).
- `backend/services/llm_language.py` — the ONE place the non-Latin-script
  refusal lives: `LANGUAGE_PIN = " Respond in English only."`,
  `NON_LATIN_BAR = 0.10` (share of letters in CJK/Hangul/Cyrillic/Arabic/
  Hebrew/Devanagari/Thai Unicode blocks), `pin()`/`pin_messages()`,
  `refuse(provider, purpose, text)`, and a `REFUSALS` counter dict per
  provider. **The extraction prompt in §2 MUST call `llm_language.pin()` on
  its system prompt and `llm_language.refuse()` on the raw reply** — not
  reimplement the check, per the standing rule ("every guard belongs on the
  live path... do not fix this at a call site").
- `alpha/` does not exist in this repo (confirmed absent; it lives in the
  sibling `aegis-alpha-terminal` repo) — nothing in this spec depends on it.

---

## 1. THE EVENT VOCABULARY

### 1.1 Sources merged, and what came from where

**EDT dataset's 11 corporate event types — [VERIFIED LIVE].** Paper: Zhihan
Zhou, Liqian Ma, Han Liu, "Trade the Event: Corporate Events Detection for
News-Based Event-Driven Trading", *Findings of ACL-IJCNLP 2021*, pp. 2114-2124,
DOI `10.18653/v1/2021.findings-acl.186`
(https://aclanthology.org/2021.findings-acl.186.pdf). Repo:
`github.com/Zhihan1996/TradeTheEvent` (MIT-style research code release). The
exact 11 types were NOT recoverable from the paper's abstract/landing pages
(both 404'd/parsed as binary), but they ARE recoverable byte-exact from the
repo's own inference code, `tool/Analyze_news.py`, which hard-codes the
label set the trained classifier emits (`config.num_labels = 12` = 11 event
types + 1 "no event" background label, confirming the paper's own count):

```python
Event2color = {
    'Acquisitions': [...], 'Clinical Trials': [...], 'Dividend Cut': [...],
    'Dividend Increase': [...], 'Guidance Change': [...], 'New Contract': [...],
    'Regular Dividend': [...], 'Reverse Stock Split': [...],
    'Special Dividend': [...], 'Stock Repurchase': [...], 'Stock Split': [...],
}
```
i.e.: Acquisitions · Clinical Trials · Dividend Cut · Dividend Increase ·
Guidance Change · New Contract · Regular Dividend · Reverse Stock Split ·
Special Dividend · Stock Repurchase · Stock Split.

**RavenPack's public event taxonomy — [FROM TRAINING KNOWLEDGE, NOT
RE-VERIFIED THIS SESSION].** Every guessed public URL for RavenPack's/
Bigdata.com's taxonomy documentation returned 404 or DNS failure this session,
and the web-search tool's budget was exhausted (200/200) before a working URL
surfaced. RavenPack's News Analytics taxonomy has been reproduced in dozens of
peer-reviewed finance papers since ~2010 (e.g. Groß-Klußmann & Hautsch 2011,
"When machines read the news"), and its well-attested top-level category
names — used below only as category NAMES to check coverage against, not as a
verbatim reproduction of RavenPack's full proprietary subtype list — are:
`acquisitions-mergers, bankruptcy, credit-ratings, dividends, earnings,
employment (incl. layoffs), executive-changes, financing (debt/equity),
fraud-investigation, index-changes, insider-trading, labor-issues, legal,
partnerships, price-target, products-services, regulatory, reputation
(boycotts/protests), revenues, stock-prices, stock-split, technical-analysis`.
**Builder action: before this vocabulary is frozen in the prereg, re-attempt a
live fetch of RavenPack's/Bigdata.com's actual public taxonomy page (or ask
Murat — the connected `Bigdata.com` MCP tool in this environment is the
commercial successor to RavenPack and may expose its own taxonomy via
`bigdata_help` or a tearsheet call) and diff against the list above.** Nothing
in §1.2 depends on RavenPack subtypes not already covered by EDT + 8-K +
`event_intel.py`'s existing 11 — the macro/market-wide types Murat asked for
explicitly (rates, CPI, tariff, sanction, index rebalance) are added from the
roadmap text itself, not from RavenPack.

**SEC Form 8-K items 1.01-9.01 — [FROM TRAINING KNOWLEDGE, NOT RE-VERIFIED
THIS SESSION].** The live fetch of `sec.gov/files/form8-k.pdf` returned a
binary PDF this tool could not parse as text; poppler (`pdftoppm`) is not
installed locally so the Read tool could not render it either. The item list
below is the standard, unchanged-for-years public 8-K item list, reproduced
from training data. **Builder action: before relying on the item-code mapping
in §1.2 for anything that touches `backend/services/edgar_events.py`'s
existing `_CFG["edgar_item_direction"]` mapping (already live in
`event_intel.py`), diff against that file — it is the checked-in, tested
source of truth for which items this repo already parses, and it wins over
this section on any conflict.**

### 1.2 The frozen vocabulary (39 event types + `no_event`)

Format per row: `id` (snake_case, frozen) | one-line definition | 8-K item(s)
it maps to (`—` if none) | typical direction prior | typical magnitude bucket
| example headline | "not this" counter-example.

Direction prior and magnitude bucket are PRIORS for calibration sanity-
checking only (§1.3 defines how per-instance `direction`/`magnitude_bucket`
are actually emitted by the model) — an `ambiguous` prior means the true sign
depends on content the model must read (beat vs. miss, upgrade vs. downgrade),
not that the type is useless.

#### Corporate — earnings & guidance
| id | definition | 8-K | direction prior | magnitude | example | not this |
|---|---|---|---|---|---|---|
| `earnings_report` | Company reports a completed period's financial results (EPS/revenue) vs. consensus or vs. year-ago. | 2.02 | ambiguous | MODERATE | "Acme Corp reports Q3 EPS of $1.20, beating estimates of $1.05" | A forward-looking statement issued separately from the print → `guidance_change`. |
| `earnings_preannouncement` | Company discloses expected results BEFORE the scheduled report date (profit warning or positive pre-announce). | 2.02 / 7.01 | ambiguous | MODERATE | "Acme warns Q3 revenue will miss guidance, cites soft demand" | The scheduled earnings date itself with no number attached → `no_event` (calendar item). |
| `guidance_change` | Company raises, cuts, reaffirms, or withdraws forward financial guidance. | 7.01 / 8.01 | ambiguous | MODERATE | "Acme raises full-year revenue guidance to $4.1-4.3B" | A one-time earnings print with no forward statement → `earnings_report`. |

#### Corporate — structural
| id | definition | 8-K | direction prior | magnitude | example | not this |
|---|---|---|---|---|---|---|
| `mergers_acquisitions` | One company agrees to acquire, or be acquired by, another (definitive agreement or completion). | 1.01, 2.01 | positive (target) / ambiguous (acquirer) | LARGE | "Acme to acquire Widget Inc for $2.1B in cash and stock" | Rumor/speculation with no confirmed deal → still `mergers_acquisitions` but `confidence` low and `evidence_span` must quote hedge language ("in talks", "considering"). |
| `divestiture_asset_sale` | Company sells a business unit, subsidiary, or major asset (not the whole company). | 2.01 | ambiguous | MODERATE | "Acme sells its European logistics unit to PE firm for $400M" | Sale of the entire company → `mergers_acquisitions`. |
| `spinoff` | Company separates a division into an independent, separately-traded entity. | 2.01 / 8.01 | ambiguous | LARGE | "Acme to spin off its healthcare division as a standalone public company" | A minority stake sale with no new listing → `divestiture_asset_sale`. |
| `bankruptcy_or_going_concern` | Chapter 11/7 filing, receivership, or auditor's going-concern doubt disclosed. | 1.03, 4.02 | negative | EXTREME | "Acme Corp files for Chapter 11 bankruptcy protection" | A debt covenant warning with no bankruptcy filing → `debt_covenant_or_default_trigger`. |
| `delisting_or_listing_risk` | Exchange notifies of non-compliance, delisting, or the company voluntarily delists/uplists. | 3.01 | negative | LARGE | "NYSE notifies Acme of non-compliance with minimum share price rule" | A reverse split done proactively with no exchange notice → `reverse_stock_split`. |

#### Corporate — capital structure & financing
| id | definition | 8-K | direction prior | magnitude | example | not this |
|---|---|---|---|---|---|---|
| `debt_issuance_or_obligation` | Company issues new debt or enters a material financial obligation (bond, credit facility). | 2.03 | ambiguous | MODERATE | "Acme issues $500M in senior notes due 2033" | The obligation being triggered/accelerated by a covenant breach → `debt_covenant_or_default_trigger`. |
| `debt_covenant_or_default_trigger` | An existing obligation is accelerated, a covenant is breached, or default is triggered. | 2.04 | negative | LARGE | "Acme triggers cross-default clause on $200M term loan" | Routine refinancing with no breach → `debt_issuance_or_obligation`. |
| `equity_issuance_dilution` | Company sells new shares (secondary offering, private placement, convertible) diluting existing holders. | 3.02 | negative | MODERATE | "Acme prices $300M secondary offering at $42/share" | A buyback (share count DOWN, not up) → `stock_buyback`. |
| `stock_buyback` | Company authorizes or executes a share repurchase program. (EDT: `Stock Repurchase`) | — / 8.01 | positive | SMALL | "Acme board authorizes $1B share buyback program" | A tender offer to acquire a DIFFERENT company → `mergers_acquisitions`. |
| `dividend_increase` | Regular per-share dividend is raised. (EDT: `Dividend Increase`) | — / 8.01 | positive | SMALL | "Acme raises quarterly dividend 8% to $0.54/share" | Initiating a dividend for the first time → still this type, note "initiation" in `evidence_span`. |
| `dividend_cut_or_suspension` | Regular dividend is cut or suspended. (EDT: `Dividend Cut`) | — / 8.01 | negative | MODERATE | "Acme suspends dividend to preserve cash amid downturn" | A special (one-time) dividend not being paid again → `no_event` (it was never regular). |
| `special_dividend` | A one-time, non-recurring dividend is declared. (EDT: `Special Dividend`) | — / 8.01 | positive | SMALL | "Acme declares special dividend of $2.00/share following asset sale" | The regular quarterly dividend amount → `dividend_increase`/`no_event`. |
| `regular_dividend_declaration` | Routine declaration of the regular dividend at an unchanged rate. (EDT: `Regular Dividend`) | — | neutral (0) | NEGLIGIBLE | "Acme declares regular quarterly dividend of $0.50/share" | Any change in rate → `dividend_increase`/`dividend_cut_or_suspension`. |
| `stock_split` | Forward stock split (share count up, price down, no fundamental change). (EDT: `Stock Split`) | — / 8.01 | ambiguous | SMALL | "Acme announces 4-for-1 stock split" | Reverse split → `reverse_stock_split`. |
| `reverse_stock_split` | Reverse split (share count down, price up), often defensive. (EDT: `Reverse Stock Split`) | — / 3.01-adjacent | negative | SMALL | "Acme completes 1-for-10 reverse stock split to regain Nasdaq compliance" | Forward split → `stock_split`. |
| `credit_rating_change` | A rating agency upgrades, downgrades, or changes outlook on the company's debt. | — / 8.01 | ambiguous | MODERATE | "Moody's downgrades Acme to Ba1, outlook negative" | The company's own guidance change → `guidance_change`. |

#### Corporate — operations, legal, people
| id | definition | 8-K | direction prior | magnitude | example | not this |
|---|---|---|---|---|---|---|
| `new_contract_or_partnership` | Company signs a material new customer contract, supply deal, or strategic partnership. (EDT: `New Contract`) | 1.01 | positive | SMALL | "Acme signs 5-year, $800M supply agreement with MegaCorp" | An acquisition of the partner company → `mergers_acquisitions`. |
| `contract_loss_or_termination` | A material contract is terminated or lost (by either party). | 1.02 | negative | SMALL | "Acme loses renewal of $150M contract with largest customer" | The contract expiring on schedule with no early termination → `no_event`. |
| `product_launch_or_innovation` | Company launches, unveils, or announces a new product/service. | 8.01 | ambiguous | SMALL | "Acme unveils next-generation chip architecture" | A product being recalled → `product_recall_or_defect`. |
| `product_recall_or_defect` | Company recalls a product or discloses a material defect/safety issue. | 8.01 | negative | MODERATE | "Acme recalls 2.1M vehicles over brake defect" | A competitor's product recall mentioned in passing → `no_event` for this scope (direction only applies to the named scope entity). |
| `clinical_trial_result` | Biotech/pharma discloses a clinical trial result, readout, or data milestone (not FDA action itself). (EDT: `Clinical Trials`) | 8.01 | ambiguous | LARGE | "Acme Therapeutics reports Phase 3 trial met primary endpoint" | The FDA's approval/rejection decision itself → `regulatory_approval`/`regulatory_investigation_or_action`. |
| `regulatory_approval` | A regulator (FDA, FCC, antitrust body, etc.) approves a product, deal, or application. | 8.01 | positive | LARGE | "FDA approves Acme's lead drug candidate for commercial sale" | The company's own trial readout submitted TO the regulator → `clinical_trial_result`. |
| `regulatory_investigation_or_action` | A regulator opens an investigation, files a complaint, imposes a fine, or denies approval. | 8.01 | negative | MODERATE | "SEC opens formal investigation into Acme's revenue recognition" | A private lawsuit with no regulator involved → `litigation_filed`. |
| `litigation_filed` | A lawsuit, arbitration, or legal claim is filed against or by the company. | 8.01 | negative | SMALL | "Shareholders file class-action suit against Acme over disclosure" | Settlement of an existing suit → `litigation_settlement`. |
| `litigation_settlement` | An existing legal matter is settled, dismissed, or resolved. | 8.01 | ambiguous | SMALL | "Acme settles patent dispute with Rival Corp for $40M" | The filing of the original suit → `litigation_filed`. |
| `management_change_departure` | A named executive or director departs, resigns, or is removed. | 5.02 | negative | SMALL | "Acme CEO steps down effective immediately, no successor named" | A planned, announced-well-in-advance retirement with a named successor → still this type; `evidence_span` should note "planned" (affects magnitude, not type). |
| `management_change_appointment` | A named executive or director is appointed or promoted. | 5.02 | ambiguous | SMALL | "Acme names former Rival Corp CFO as new Chief Financial Officer" | The prior person's departure in the same article → both types emitted (one row per document per §2, so extract the DOMINANT one; see §2.4). |
| `auditor_or_accounting_change` | Company changes its auditor, or restates/non-relies on prior financials. | 4.01, 4.02 | negative | MODERATE | "Acme dismisses auditor, restates two years of financial statements" | A routine, non-restatement auditor rotation with no dispute → magnitude drops to SMALL, type unchanged. |
| `cybersecurity_incident` | Company discloses a material cybersecurity breach or incident. | 1.05 | negative | MODERATE | "Acme discloses ransomware attack affecting customer data" | A routine security-patch announcement with no breach → `no_event`. |
| `insider_or_institutional_ownership_change` | A Form 4 insider transaction or a 13F/13D institutional stake change is disclosed. | — (Forms 3/4/13D/13F, not 8-K) | ambiguous | NEGLIGIBLE | "Acme CEO sells 50,000 shares under a 10b5-1 plan" | A tender offer to acquire the whole company → `mergers_acquisitions`. |

#### Macro / market-wide (Murat's explicit ask: rates, CPI, tariff, sanction, index rebalance)
| id | definition | 8-K | direction prior | magnitude | example | not this |
|---|---|---|---|---|---|---|
| `macro_rate_decision` | A central bank (Fed, ECB, BOJ, PBOC, etc.) announces or changes a policy interest rate. | — | ambiguous | MODERATE | "Fed raises rates 25bp to 5.00-5.25%, signals one more hike" | A rate-related comment by a company executive, not a central bank → `no_event` for macro, may still tag the company's own type. |
| `macro_inflation_print` | A CPI/PCE/inflation statistic is released. | — | ambiguous | SMALL | "US CPI rises 3.2% y/y, above the 3.0% consensus" | A company's own cost inflation commentary in an earnings call → `earnings_report`/`guidance_change`. |
| `macro_labor_report` | A jobs/employment statistic (NFP, unemployment rate, etc.) is released. | — | ambiguous | SMALL | "US adds 180,000 jobs in August, unemployment holds at 4.1%" | Company-specific layoffs → `no_event` at the macro scope; tag the company scope separately if a per-ticker row exists. |
| `tariff_or_trade_policy` | A government announces, imposes, or changes tariffs or trade restrictions. | — | negative | MODERATE | "US announces 25% tariff on imported steel and aluminum" | A company passing costs through via price increases → `guidance_change` for that company. |
| `sanction` | A government imposes or lifts sanctions on a country, entity, or individual. | — | negative | MODERATE | "Treasury sanctions three companies over export control violations" | A company's own compliance investigation unrelated to sanctions → `regulatory_investigation_or_action`. |
| `index_rebalance` | A stock is added to or removed from a major index (S&P 500, Russell, etc.). | — | ambiguous (positive on addition, negative on removal) | SMALL | "Acme Corp set to join the S&P 500, replacing Widget Inc" | A company's own share buyback changing its float → `stock_buyback`. |

#### The refusal class
| id | definition | 8-K | direction prior | magnitude | example | not this |
|---|---|---|---|---|---|---|
| `no_event` | The document contains no new, dated, decision-relevant information about the scope entity — a recap, opinion piece, old-news restatement, analyst commentary with no new fact, or pure noise. | — | neutral (0) | NEGLIGIBLE | "5 things to know about Acme Corp before the market opens" | Any of the 38 types above, even if buried in an otherwise fluffy article — `no_event` is for documents with NOTHING extractable, not low-magnitude documents. |

That is 38 substantive types + `no_event` = **39 total**, inside the requested
25-40 band.

### 1.3 Definitions that make two prompts comparable by kappa

- **`direction ∈ {-1, 0, +1}`**, always relative to the named `scope` entity
  (ticker or macro aggregate), never to the market, matching
  `event_intel.py`'s existing `direction_relative_to` field.
  - `+1`: the event, taken alone, is expected to move the scope entity's price
    UP relative to its pre-event expectation.
  - `-1`: expected DOWN.
  - `0`: the event is real and dated but has **no directional implication by
    itself** (a regular dividend declaration at an unchanged rate; a scheduled
    earnings date with no number attached; `no_event`).
  - There is **no fourth value for "I don't know."** A genuinely uncertain
    call is expressed by committing to the best-guess sign AND setting
    `confidence` low (see below) — this is what makes two independent
    extractions comparable by Cohen's kappa on `direction`: kappa cannot be
    computed over a set that includes an escape hatch one prompt uses more
    than the other.
- **`magnitude_bucket`** — 5 ordered buckets, thresholds on **expected
  |same-scope abnormal return| over the next 1-2 sessions**, not on company
  size (per `AEGIS_STRATEGIC_INVARIANTS.md`: "size does not bound the move" —
  the repo's own chain implied 5.10% in one session for a ~$5T company, which
  is why the LARGE bucket floor is set at 5%, not scaled by market cap):
  - `NEGLIGIBLE`: expected |return| < 0.5%
  - `SMALL`: 0.5% – 2%
  - `MODERATE`: 2% – 5%
  - `LARGE`: 5% – 10%
  - `EXTREME`: ≥ 10%
  The model is asked for its **prior expectation of typical magnitude for
  this event type**, not a forecast conditioned on today's specific facts —
  that keeps the bucket assignment a property of the TYPE (checkable against
  the "typical magnitude" column in §1.2) rather than a return forecast in
  disguise (which would need its own calibration ledger entry, not a
  vocabulary field).
- **`confidence ∈ [0, 1]`** — the model's stated probability that the emitted
  `(event_type, direction)` pair, taken together, is the correct reading of
  the document. This is NOT the same axis as `event_intel.py`'s existing
  `extraction.tier` (HIGH/MEDIUM/LOW/FAILED, a PARSE-FIDELITY judgment,
  explicitly barred from being read as an outcome probability by the D4
  closure ruling in that file's docstring). `confidence` here IS allowed to
  be read as a probability, because inter-rater kappa (§1.4) is exactly the
  external check that would catch a model that free-lances high confidence.
- **Inter-rater comparability**: two prompts (e.g., a baseline system prompt
  vs. a candidate rewrite, or two model checkpoints) are compared on the SAME
  500-row sample by computing **Cohen's kappa on `event_type`** (39+1-way
  categorical) and **weighted kappa on `magnitude_bucket`** (ordinal, linear
  weights) and **on `direction`** (ordinal -1/0/+1, linear weights).
  `confidence` is compared by mean absolute difference, not kappa (it's
  continuous). This is L2's "inter-rater: a second prompt hash on a 500-row
  sample, kappa printed" control, made concrete.

---

## 2. THE EXTRACTION PROMPT CONTRACT

Target model: Qwen2.5-7B-Instruct, local, per roadmap L2/L4 (the repo's
existing local-inference path; DeepSeek is the *provider* for the separate
hosted-LLM calls in `llm_analyzer.py` — this is a DIFFERENT call path, local
and free, and must NOT go through `llm_analyzer._call_llm`, which is
DeepSeek-specific). Builder: confirm the local serving entry point (the
session memory references a local llama-server /Aegis-Desktop backend;
`backend/services/event_intel.py`'s `_classify_llm` currently hard-codes
DeepSeek via `llm_analyzer` and needs a second code path, or `llm_analyzer`
needs a `provider="local_qwen"` branch — out of scope for this spec, but the
prompt contract below is provider-agnostic).

### 2.1 JSON Schema (draft-07) for the output row

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "aegis://schemas/typed_event_row.json",
  "title": "AegisTypedEventRow",
  "type": "object",
  "additionalProperties": false,
  "required": ["event_type", "direction", "magnitude_bucket", "confidence", "evidence_span"],
  "properties": {
    "event_type": {
      "type": "string",
      "enum": [
        "earnings_report", "earnings_preannouncement", "guidance_change",
        "mergers_acquisitions", "divestiture_asset_sale", "spinoff",
        "bankruptcy_or_going_concern", "delisting_or_listing_risk",
        "debt_issuance_or_obligation", "debt_covenant_or_default_trigger",
        "equity_issuance_dilution", "stock_buyback", "dividend_increase",
        "dividend_cut_or_suspension", "special_dividend",
        "regular_dividend_declaration", "stock_split", "reverse_stock_split",
        "credit_rating_change", "new_contract_or_partnership",
        "contract_loss_or_termination", "product_launch_or_innovation",
        "product_recall_or_defect", "clinical_trial_result",
        "regulatory_approval", "regulatory_investigation_or_action",
        "litigation_filed", "litigation_settlement",
        "management_change_departure", "management_change_appointment",
        "auditor_or_accounting_change", "cybersecurity_incident",
        "insider_or_institutional_ownership_change",
        "macro_rate_decision", "macro_inflation_print", "macro_labor_report",
        "tariff_or_trade_policy", "sanction", "index_rebalance", "no_event"
      ]
    },
    "direction": { "type": "integer", "enum": [-1, 0, 1] },
    "magnitude_bucket": {
      "type": "string",
      "enum": ["NEGLIGIBLE", "SMALL", "MODERATE", "LARGE", "EXTREME"]
    },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "evidence_span": {
      "type": "string",
      "minLength": 0,
      "maxLength": 400,
      "description": "A verbatim substring of the input document (<=400 chars) that justifies event_type and direction. Empty string only when event_type is no_event."
    }
  }
}
```

### 2.2 System prompt (verbatim)

```
You are a financial-news event classifier. You read one news document about
one named entity (a company ticker, or a macro topic) and output exactly ONE
JSON object matching the schema you have been given. You classify into fixed
categories only — you never write free-form analysis, never predict future
prices, never give investment advice, and never add fields not in the schema.

Rules:
1. event_type must be exactly one value from the enum. If nothing in the
   document is a dated, decision-relevant event about the named entity, use
   "no_event".
2. direction is -1, 0, or +1, relative to the NAMED ENTITY ONLY, never the
   broad market. Use 0 when the event is real but has no directional
   implication by itself (e.g. a routine, unchanged dividend declaration).
   Never invent a fourth value. If you are unsure, still choose the single
   most likely direction and reflect your uncertainty in confidence instead.
3. magnitude_bucket is your prior expectation of how big a same-scope price
   reaction an event of THIS TYPE typically produces over the next 1-2
   trading sessions, not a forecast about today's specific facts:
   NEGLIGIBLE < 0.5%, SMALL 0.5-2%, MODERATE 2-5%, LARGE 5-10%, EXTREME >=10%
   (expected absolute return).
4. confidence is a number from 0 to 1: your probability that the event_type
   AND direction you chose together are the correct reading of the document.
5. evidence_span is a verbatim substring of the document (at most 400
   characters) that most directly supports your event_type and direction
   choice. Use an empty string only when event_type is "no_event".
6. A sarcastic, speculative, or hedged headline is read for its LITERAL
   claim, not its tone — quote the hedge language (e.g. "considering",
   "reportedly", "sources say") in evidence_span and lower confidence
   accordingly; do not change event_type just because a claim is uncertain.
7. A denial ("X is NOT acquiring Y") is NOT the event it denies. Classify the
   denial itself: if a denial is newsworthy corrective information, still
   pick the nearest matching event_type but set direction to the OPPOSITE of
   what the rumor implied (a denied acquisition rumor is a mild NEGATIVE for
   the would-be target, since an expected catalyst was removed), and quote
   the negation explicitly in evidence_span.
8. An article that only RECAPS an event that was already reported on an
   earlier date (no new fact, just a summary or "as previously announced")
   is "no_event" — the event was already extracted from the original article
   on its original date; extracting it again from a recap double-counts it.
9. Output EXACTLY the JSON object. No markdown fences, no explanation before
   or after, no additional keys. Respond in English only.
```

(Rule 9's final sentence is the repo's standing `llm_language.LANGUAGE_PIN`
text and MUST be produced by calling `llm_language.pin(system_prompt)` in
code, not hand-typed twice — hand-typing it here is only to show the builder
the exact string that ends up in the wire prompt.)

### 2.3 User template

```
Entity: {scope}  (type: {"ticker" if company else "macro_topic"})
Document date: {document_date_iso}   <!-- PIT anchor; never omit -->
Document source: {source_feed}       <!-- e.g. "yfinance_news", "edgar_8k" -->
Document title: {title}
Document body (may be truncated):
{body_text_truncated_to_2000_chars}

Classify this document about {scope} per your instructions. Output the JSON
object only.
```

### 2.4 One document → one row (the "numeric by construction" contract)

Per L2, the model emits **exactly one row per document**, not one row per
event mentioned. When a document plausibly contains two events (e.g. a CEO
departure AND their successor's appointment in the same article), the
extractor picks the **dominant** event — the one the headline and lede are
about — and the JSON schema does not support multi-event documents in v1. A
`not_dominant_events_seen: list[str]` free-text debug field MAY be logged
separately for future multi-label work but MUST NOT be part of the graded
schema (additionalProperties: false forbids it in the wire contract; log it
out-of-band if wanted).

### 2.5 The refusal shape for unparseable output

Mirrors `llm_language.refuse()` and `event_intel.py`'s existing
`_classify_llm` `None`-on-failure contract — no repair, no retry, degrade to
the deterministic keyword fallback that already exists in `event_intel.py`:

1. Strip markdown fences (`` ``` ``) and whitespace from the raw reply.
2. Run `llm_language.refuse(provider="local_qwen", purpose="event_extraction",
   text=raw_reply)` FIRST, before JSON parsing. If it returns `True`
   (>10% non-Latin-script letters), the row is `REFUSED_LANGUAGE` — log,
   increment `llm_language.REFUSALS["local_qwen"]`, fall back to keyword
   classification, do NOT attempt to parse the JSON.
3. `json.loads()` the stripped text. On `JSONDecodeError`: `REFUSED_UNPARSEABLE`
   — log the raw reply (capped at 1000 chars) for the golden-set/regression
   corpus, fall back to keyword classification.
4. Validate against the JSON Schema in §2.1 (a real validator —
   `jsonschema.validate`, not ad-hoc key checks, so an enum drift is caught
   as a schema violation, not a silent pass-through of a novel string). On
   `ValidationError`: `REFUSED_SCHEMA` — same fallback.
5. A row that reaches this point with `event_type == "no_event"` is a
   SUCCESSFUL classification, not a refusal — it must be written to the
   output store like any other row (a "no_event" row is how L2 measures the
   corpus's genuine event rate; discarding it would make the denominator
   silently wrong, the same failure class as `event_intel.py`'s canary
   discipline for "no events found" vs. "extraction unavailable").
6. Every refusal is counted per reason (`REFUSED_LANGUAGE`,
   `REFUSED_UNPARSEABLE`, `REFUSED_SCHEMA`) in a per-run receipt, same
   pattern as `ledger_health()`'s `problems` list — a refusal rate that
   silently climbs must be visible on the same surface Murat already reads.

### 2.6 Golden set (20 rows; pin this file for regression)

Format: `#. headline (source hint) → expected JSON` (abbreviated; builder
expands `evidence_span` to the exact quoted substring at implementation time).

1. "Acme Corp reports Q3 EPS of $1.20, beating estimates of $1.05, revenue up 12%" → `{event_type: earnings_report, direction: 1, magnitude_bucket: MODERATE, confidence: 0.9}`
2. "Acme Corp misses Q2 revenue estimates, shares fall in after-hours trading" → `{earnings_report, -1, MODERATE, 0.9}`
3. "Acme raises full-year guidance on strong cloud demand" → `{guidance_change, 1, MODERATE, 0.85}`
4. "Acme withdraws FY guidance citing macro uncertainty" → `{guidance_change, -1, MODERATE, 0.8}`
5. "Acme to acquire Widget Inc for $2.1B in cash and stock, deal expected to close Q1" → `{mergers_acquisitions, 1, LARGE, 0.9}` (scope = Widget Inc, the target)
6. "Acme shares fall as it agrees to pay $2.1B for Widget Inc, above market expectations" → `{mergers_acquisitions, -1, LARGE, 0.7}` (scope = Acme, the acquirer, priced as overpaying)
7. "Acme board authorizes new $1B share buyback program" → `{stock_buyback, 1, SMALL, 0.85}`
8. "Acme suspends dividend to preserve cash amid liquidity crunch" → `{dividend_cut_or_suspension, -1, MODERATE, 0.9}`
9. "Acme declares regular quarterly dividend of $0.50 per share, unchanged" → `{regular_dividend_declaration, 0, NEGLIGIBLE, 0.9}`
10. "Acme announces 4-for-1 stock split effective next month" → `{stock_split, 1, SMALL, 0.6}`
11. "Acme completes 1-for-10 reverse stock split to regain Nasdaq listing compliance" → `{reverse_stock_split, -1, SMALL, 0.75}`
12. "Moody's downgrades Acme's senior debt to Ba1, cites weakening margins" → `{credit_rating_change, -1, MODERATE, 0.85}`
13. "Acme signs five-year, $800M supply agreement with MegaCorp" → `{new_contract_or_partnership, 1, SMALL, 0.8}`
14. "Acme Therapeutics reports Phase 3 trial met primary endpoint with statistical significance" → `{clinical_trial_result, 1, LARGE, 0.85}`
15. "FDA rejects Acme's lead drug candidate, cites manufacturing concerns" → `{regulatory_investigation_or_action, -1, LARGE, 0.85}`
16. "Shareholders file class-action lawsuit against Acme over accounting disclosures" → `{litigation_filed, -1, SMALL, 0.8}`
17. "Acme CEO steps down effective immediately, board launches search for successor" → `{management_change_departure, -1, SMALL, 0.75}`
18. "Acme discloses ransomware attack affecting customer payment data" → `{cybersecurity_incident, -1, MODERATE, 0.85}`
19. "Fed raises interest rates 25 basis points to 5.00-5.25%, signals one more hike this year" → `{macro_rate_decision, -1, MODERATE, 0.7}` (scope = broad market; hikes read negative-prior)
20. "Acme Corp set to join the S&P 500 index, replacing Widget Inc effective next Monday" → `{index_rebalance, 1, SMALL, 0.85}`

### 2.7 Adversarial rows (3, required)

21. **Sarcasm.** "Acme's 'transformational' new CEO lasted all of four months before quietly resigning — shocking absolutely no one." → `{management_change_departure, -1, SMALL, 0.75}`. The sarcastic tone ("transformational", "shocking absolutely no one") must NOT change `event_type` — it is still a departure — but the loaded language is exactly the kind of thing that should show up quoted in `evidence_span`, and rule 6 covers it explicitly.
22. **Denial.** "Acme Corp denies it is in talks to acquire Widget Inc, calls rumors 'baseless'." → `{mergers_acquisitions, -1, SMALL, 0.6}` per rule 7 — the denial removes an expected catalyst, so scope=Acme gets a mild negative, NOT a positive `1` (which a naive keyword match on "acquire" would produce) and NOT `no_event` (a naive "nothing happened" reading, which throws away real information: the market had priced in a deal that is now off).
23. **Old-news recap.** "As previously reported in March, Acme completed its acquisition of Widget Inc; the combined company will report first joint earnings next quarter." → `{no_event, 0, NEGLIGIBLE, 0.7}` per rule 8 — "as previously reported" is the explicit recap marker; the event's information content was already extracted on the March article's own date, and a test must confirm the extractor does NOT re-emit `mergers_acquisitions` here.

A regression test (`test_event_vocabulary_golden_set.py`, builder's to write)
pins all 23 rows: run the prompt against the live local model, assert
`event_type` and `direction` match exactly for every row (magnitude/
confidence get a looser check — within one bucket / within 0.25 — since
those are inherently softer judgments), and fail loudly (not skip) if the
local model endpoint is unavailable, per the "a check that did not run is not
a check that passed" standing rule.

---

## 3. CALIBRATION UTILITIES

### 3.1 What `Metaculus/forecasting-tools` actually has — [VERIFIED LIVE via `gh api` + `raw.githubusercontent.com`, commit as of 2026-09-09]

Repo: `github.com/Metaculus/forecasting-tools` (MIT license, Python, built
around Metaculus's own `BinaryQuestion`/pydantic models and the Metaculus
platform's "community prediction" concept — it is a framework for RUNNING a
forecasting bot against Metaculus, not a general calibration-metrics library).

Two relevant subsystems, both read in full this session:

1. **`forecasting_tools/data_models/binary_report.py`** — `BinaryReport`
   class. Has:
   - `expected_baseline_score` (property): Metaculus's own "baseline score"
     formula, `100 * (c*(log2(p)+1) + (1-c)*(log2(1-p)+1))` where `p` is the
     model's prediction and `c` is the Metaculus **community prediction**
     (crowd forecast) — this scores a model AGAINST THE CROWD, not against
     ground-truth resolution. Not usable for Aegis: Aegis has no community
     prediction to score against, and even where it might (Headline Arena,
     M6), the graded quantity there is our own ledger's `outcome`, not a
     crowd number.
   - `inversed_expected_log_score`: same idea, a log score vs. community
     prediction, sign-flipped so lower is better.
   - `deviation_points` / `calculate_average_deviation_points`: `abs(p - c)`,
     again model-vs-crowd, not model-vs-outcome.
   - **No Brier score against ground truth, no Murphy decomposition, no
     reliability-diagram binning, anywhere in this file.**
2. **`forecasting_tools/calibration_adjustment/`** — `CalibrationAdjuster`
   abstract base class + 5 subclasses (`ConstantShiftAdjuster`,
   `DecisionTreeAdjuster`, `KMeansAdjuster`, `LogisticRecalibrationAdjuster`,
   `StepAdjuster`). API: `.train(forecasts: pd.DataFrame) -> None` (fits in
   place from a DataFrame with columns `type, probability_yes,
   probability_yes_per_category, options, resolution`), then
   `.adjust_binary_forecast(prediction: float) -> float` /
   `.adjust_multiple_choice_forecast(predictions) -> list[float]` to
   RECALIBRATE new forecasts (Platt-scaling / isotonic-adjacent post-hoc
   correction), and `.test(forecasts) -> float` which DOES compute a plain
   Brier score (`mean((adjusted_p - y)**2)`) as its training objective — but
   only the flat Brier mean, not the reliability/resolution/uncertainty
   decomposition, and it requires `sklearn` + `pandas` as hard runtime
   dependencies (`require_optional_package` at import time).

**Verdict: not worth depending on.** Three reasons: (1) it is built around
Metaculus's own pydantic `BinaryQuestion`/`ForecastReport` object graph and a
`type ∈ {"binary","multiple_choice"}` DataFrame schema neither of which maps
onto `PredictionRecord` without a translation layer that is more code than
the metrics themselves; (2) it has no Murphy 1973 decomposition, no
reliability-diagram output, no rolling/grouped calibration report, no
Tetlock-persistence check — everything §3.2 below asks for is simply absent,
so adopting it buys nothing for M4's actual deliverable; (3) it pulls in
`scikit-learn` and `pandas` as hard imports for functionality Aegis would use
maybe 20% of (the recalibration ADJUSTERS are a genuinely different, and
currently out-of-scope, capability — post-hoc correcting a forecaster's
probabilities — that could be revisited later as its own experiment against
a GBM/no-adjustment control, but is not part of M4's calibration REPORTING
ask). Write ~80-100 lines of numpy against `backend/data/optimus/predictions.jsonl`
directly, as specified below.

### 3.2 Brier decomposition (Murphy 1973)

For `n` resolved predictions with forecast probabilities `p_i` and binary
outcomes `o_i ∈ {0, 1}`, binned into `K` bins by forecast probability
(binning rule below):

```
Brier          = (1/n) Σ_i (p_i - o_i)^2
Reliability    = (1/n) Σ_k  n_k · (p̄_k - ō_k)^2        # lower is better
Resolution     = (1/n) Σ_k  n_k · (ō_k - ō̄)^2          # higher is better
Uncertainty    = ō̄ · (1 - ō̄)                            # base-rate variance, a property of the SAMPLE not the forecaster
Brier          = Reliability - Resolution + Uncertainty   # identity, must hold to float tolerance
```
where `k` indexes bins, `n_k` is the bin's count, `p̄_k` is the mean forecast
in bin `k`, `ō_k` is the mean outcome (empirical base rate) in bin `k`, and
`ō̄` is the overall base rate across all `n` predictions.

**Binning rule: equal-count (quantile) bins**, not equal-width. Target `K=10`
bins by default, each holding `n/K` predictions ordered by `p_i`; if the
resolved set for a slice has `n < 50`, drop to `K = max(3, n // 20)` so no
bin holds fewer than a **minimum of 15 predictions**; if `n < 45` (cannot
form even 3 bins of 15), skip decomposition entirely and report Brier only
with `"decomposition": "insufficient_n"` — a decomposition computed on tiny
bins is noise dressed as diagnosis, same failure class the ledger already
guards against ("a Brier score on eleven resolved records is a description
of eleven records").

### 3.3 Reliability diagram as JSON (the shape the board renders)

```json
{
  "group_key": "model:qwen2.5-7b-instruct|mechanism:reaction_longshort",
  "n_resolved": 812,
  "n_bins": 10,
  "brier": 0.183,
  "climatology_brier": 0.201,
  "beats_climatology": true,
  "decomposition": {
    "reliability": 0.014,
    "resolution": 0.032,
    "uncertainty": 0.201,
    "identity_check_abs_error": 0.0000012
  },
  "bins": [
    {"bin_id": 0, "p_lo": 0.02, "p_hi": 0.18, "n": 81,
     "mean_forecast": 0.11, "mean_outcome": 0.09,
     "outcome_se": 0.032, "overconfidence": 0.02},
    { "...": "one row per bin, sorted by p_lo" }
  ],
  "base_rate_row": {"brier": 0.201, "mean_forecast": 0.44, "mean_outcome": 0.44},
  "as_of": "2026-09-11T00:00:00Z"
}
```
`outcome_se` is the binomial standard error of `ō_k` (`sqrt(ō_k(1-ō_k)/n_k)`)
— every bin ships its own uncertainty, per the house rule that a headline
number without an n or an SE is not trusted here.

### 3.4 Grouping, rolling window, base-rate row, persistence

- **Per-model**: group by `PredictionRecord.model` (+ `model_version`).
- **Per-mechanism**: group by the new `mechanism_id` field (§4) — NOT by
  `specialist`, which names the calling code path, not the underlying
  hypothesis family; two specialists can share a mechanism, and this
  grouping is what lets M2's "winner vs. matched loser" distillation compare
  like with like.
- **Rolling window**: trailing `N` resolved predictions (default `N=200`) OR
  trailing `D` calendar days (default `D=90`), whichever the caller asks
  for — report BOTH the rolling and the all-time number side by side, never
  only the rolling one (a rolling-only report can hide a mechanism that was
  briefly calibrated and has since drifted).
- **Base-rate forecaster row**: for every real `PredictionRecord`, a
  synthetic twin is scored with `p = ō̄_asof(t)` — the outcome base rate
  computed ONLY from predictions whose `resolution_date < t` (the record's
  own `made_at`), i.e. **the base rate must itself be PIT-correct or it
  leaks the future into its own control**, exactly the hindsight-contam
  failure mode M3 is designed to prevent one layer down. This row is written
  into the SAME calibration report structure with `model = "base_rate_forecaster"`,
  never mixed silently into another model's numbers.
- **Tetlock-style persistence**: for a model/mechanism with resolved
  predictions in ≥2 consecutive calendar quarters (min `n=20` resolved per
  quarter, else the quarter is excluded, not zero-filled), compute the
  per-quarter Brier-skill-score `BSS_q = 1 - Brier_q / climatology_Brier_q`,
  then the Pearson correlation `r` of `BSS_q` vs. `BSS_{q+1}` across all
  consecutive quarter-pairs available. Report `r`, `n_pairs`, and refuse
  (report `"persistence": "insufficient_quarters"`) below `n_pairs = 3`,
  matching the repo's existing "a check that cannot go green is a broken
  check" discipline — a persistence correlation on 1-2 pairs is a coin flip
  reported as a coefficient.

### 3.5 Test cases with known answers

```python
import numpy as np

def test_perfectly_calibrated_synthetic_set_has_zero_reliability():
    """10 bins, each bin's mean forecast EQUALS its empirical outcome rate
    exactly (by construction: bin k has p=k/10 for all its members, and
    outcomes are the deterministic pattern that makes ō_k == p̄_k)."""
    # bin k (k=0..9): p = (k+0.5)/10 for all 20 members; outcomes constructed
    # so exactly round((k+0.5)/10 * 20) members resolve 1, rest resolve 0.
    p, o = [], []
    for k in range(10):
        pk = (k + 0.5) / 10
        n_pos = round(pk * 20)
        p += [pk] * 20
        o += [1] * n_pos + [0] * (20 - n_pos)
    result = brier_decomposition(np.array(p), np.array(o), n_bins=10)
    assert abs(result["reliability"]) < 1e-9

def test_constant_half_forecaster_has_zero_resolution():
    """A forecaster who always says p=0.5 regardless of outcome: with a
    single distinct forecast value there is only ONE bin, so ō_k == ō̄ by
    construction and resolution collapses to exactly 0."""
    rng = np.random.default_rng(0)
    o = rng.integers(0, 2, size=500).astype(float)
    p = np.full(500, 0.5)
    result = brier_decomposition(p, o, n_bins=10)
    assert abs(result["resolution"]) < 1e-9
    # and Brier == Uncertainty exactly, since Reliability and Resolution both vanish
    assert abs(result["brier"] - result["uncertainty"]) < 1e-9

def test_brier_identity_holds():
    """Reliability - Resolution + Uncertainty == Brier, to float tolerance,
    on a non-degenerate random forecast/outcome set."""
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.95, size=1000)
    o = (rng.uniform(size=1000) < p).astype(float)  # well-calibrated by construction
    result = brier_decomposition(p, o, n_bins=10)
    identity = result["reliability"] - result["resolution"] + result["uncertainty"]
    assert abs(identity - result["brier"]) < 1e-9

def test_well_calibrated_random_set_beats_climatology_on_average():
    """A forecaster whose p IS the true outcome probability should, in
    expectation over many draws, show low reliability and roughly match
    climatology minus its resolution term — a sanity bound, not an exact
    equality (Monte Carlo, seeded, wide tolerance)."""
    ...

def test_insufficient_n_refuses_decomposition():
    result = brier_decomposition(np.array([0.6, 0.4, 0.7]), np.array([1, 0, 1]), n_bins=10)
    assert result["decomposition"] == "insufficient_n"
```

---

## 4. LEDGER FIELD ADDITIONS for `PredictionRecord`

All additions are **optional, additive, backward-compatible** — every field
below defaults to `None` (or the stated default) so all 24,828+ existing rows
in `backend/data/optimus/predictions.jsonl` continue to read unchanged
(`dataclasses.asdict`/`json.loads` round-trip is unaffected by new fields
with defaults; the schema-version bump below is the only required code
touch). Bump `SCHEMA_VERSION` from `"1.3.0"` to **`"1.4.0"`**.

Column headers: **field** | **type** | **allowed values** | **who writes it**
| **required at creation?** | **required at resolution?** | **default for
absent (pre-1.4.0) rows**.

| field | type | allowed values | who writes | req. at creation | req. at resolution | default when absent |
|---|---|---|---|---|---|---|
| `mechanism_id` | `str \| None` | snake_case, frozen per hypothesis family (e.g. `"reaction_longshort_v1"`, `"typed_event_head_e1"`) — a REGISTRY of valid ids lives beside `Observable`, so a typo silently creating a new mechanism is impossible | the calling code (specialist/book/lab), from its own frozen contract | **yes**, for every record written after 1.4.0 ships | n/a (read-only after creation) | `None` — pre-1.4.0 rows are grouped by `specialist` only in calibration reports, and the report says so |
| `hypothesis_text` | `str` | free text, stripped | LLM/specialist proposal, human-reviewable | **yes**, for new records; existing `thesis` field is REUSED for this — no new field is added, this row documents that `thesis` now serves the M1 spec's `hypothesis_text` role | n/a | `thesis` already has a default of `""`; no change needed |
| `decision_date` | `str \| None` (ISO date) | the calendar date the DECISION was made, which may precede `made_at` (the write timestamp) for a batch/overnight job | caller | optional; defaults to `made_at[:10]` if absent | n/a | `None` → callers read `made_at[:10]` |
| `policy_hash` | `str \| None` | content hash (same `_hash()` convention as `prompt_hash`) of the frozen `Strategy`/contract this forecast was made under, when one exists (B2/B5 book forecasts) | caller, from `contract.py`'s fingerprint | required when `mechanism_id` refers to a book strategy (B5); `None` for ad-hoc/non-book forecasts | n/a | `None` |
| `inputs_used` | `dict` | PIT provenance: `{"source": ..., "as_of": ..., "snapshot_hash": ...}` list/dict, generalizing the existing `input_snapshot_hash` (kept unchanged) into a richer, human-readable provenance record | caller | optional (existing `input_snapshot_hash` remains the machine-checkable hash; this is the readable companion) | n/a | `{}` |
| `confidence` | `float \| None`, `0.0-1.0` | the forecaster's SECOND-ORDER confidence in its own `probability` estimate — distinct from `probability` itself, matching the event-vocabulary's `confidence` semantics in §1.3 (probability that the estimate itself is well-formed, not the graded first-order probability) | LLM/specialist | optional | n/a | `None` |
| `control_twin_id` | `str \| None` | `prediction_id` (or `portfolio_id`/fingerprint for a book) of the paired control this record is graded against | caller, at creation (per invariant 18: "a twin is created with the book, not after its number is known") | **yes** whenever `benchmark` is a constructed twin rather than a named index (B3/B5) | n/a | `None` — existing `benchmark` field (already optional) is the only twin reference on old rows |
| `control_construction` | `str \| None` | short text: how the twin was built (`"same construction, random universe draw, same cadence"`) | caller | required alongside `control_twin_id` | n/a | `None` |
| `vs_benchmark` | `float \| None` | realized return spread vs. `benchmark`, computed at resolution | resolver (`resolve_one`) | n/a | **yes**, whenever `benchmark` is set and resolves | `None` |
| `vs_control` | `float \| None` | realized return spread vs. `control_twin_id`'s own realized return | resolver | n/a | **yes**, whenever `control_twin_id` is set and both legs resolve | `None` |
| `costs_charged` | `bool` | `True`/`False` — whether transaction costs were applied in computing the graded outcome | caller, per `portfolio_farm.Policy`'s existing `zero_cost_diagnostic` convention (never silently `False`) | **yes** whenever this record informs a book/portfolio decision | n/a | `False` with a **loud** `"costs_charged_unknown_pre_1.4.0": true` marker in any report that aggregates old rows, never silently treated as "costs were charged" |
| `cost_rate_bps` | `float \| None` | the rate charged, in bps, when `costs_charged=True` | caller | required when `costs_charged=True` | n/a | `None` |
| `calibration_bucket` | `str \| None` | one of the 5 magnitude-style buckets OR a simple decile label (`"p0-10"`...`"p90-100"`) assigned from `probability` at resolution, for fast grouped queries without recomputing bins each read | resolver, computed, never hand-set | n/a | **yes**, once outcome is known | `None`, computed lazily by the calibration report if absent |
| `LAP_score` | `float \| None` | Lookahead Propensity score (L3, Gao-Jiang-Yan 2026 protocol) for this specific record's underlying model+date, when the record's `made_at` predates the model's training cutoff | the LAP measurement job (batch, post-hoc), written back by `prediction_id` | n/a (never at creation — LAP is measured AFTER, against a corpus of records) | required before the record's `probability` is quoted anywhere per invariant 21 ("a number from an LLM read over dates before that model's cutoff carries its LAP result or is not quoted") | `None` — and any report quoting a pre-cutoff record without a non-null `LAP_score` MUST say so, not silently omit the caveat |
| `anonymization_gap` | `float \| None` | for text-based forecasts (R2/X-lane): the same-date accuracy delta between an anonymized read and a raw read, when both exist | the X-lane comparison job | n/a | n/a, informational | `None` |
| `era_tag` | `str \| None` | PIT era label (`"2008-2015"`, `"2016-2024"`, `"2025-2026"`, etc.), assigned at write time from `made_at`, frozen — never recomputed retroactively if era boundaries change later (a changed boundary gets a NEW tag scheme version, not a rewrite) | caller/append(), derived | optional but strongly recommended | n/a | `None` — reports group `None`-era rows into an explicit `"era_unknown"` bucket, never silently drop them |
| `licence` | `str \| None` | one of the three: `"PRODUCT_EXPERIMENT"`, `"CAPITAL_CANDIDATE"`, `"RESEARCH_CLAIM"` | caller, from the mechanism's own frozen licence declaration | **yes** for new records (every artefact names one, per the Three Licences canon) | n/a | `None` — pre-1.4.0 rows are NOT assumed `PRODUCT_EXPERIMENT`; a report says `"licence": "unstated (pre-1.4.0)"` |
| `n_effective_trials_at_time` | `int \| None` | the mechanism's own trial-count-so-far AT THE TIME this forecast was made (a robustness/multiplicity bookkeeping field — lets a later multiplicity correction be computed honestly instead of reconstructed after the fact) | caller | optional | n/a | `None` |
| `notes_text` | `str` | free text, human or LLM annotation added later (e.g. a distillation job's note referencing this record) | anyone, append-style (never overwrites `thesis`/`counter_thesis`) | optional | optional | `""` |
| `embedding_id` | `str \| None` | pointer to a stored embedding of `hypothesis_text`/`counter_thesis` for M3's retrieval | the embedding job, written back by `prediction_id` | n/a | n/a | `None` |

Backward-compatibility test (builder's to write,
`test_ledger_schema_1_4_0_backward_compat.py`): load a fixture containing 10
real rows sampled from the pre-1.4.0 ledger (schema `1.3.0` and earlier),
assert every one parses into the extended dataclass with all new fields
`None`/default, and assert `calibration()`/`ledger_health()` still compute
identical numbers on that fixture before and after the dataclass change (a
migration that silently changes a historical Brier score is exactly the F7
failure class this file's own docstring warns about, one layer up).

---

## 5. HINDSIGHT-SAFE RETRIEVAL RULE (M3)

### 5.1 The predicate

A retriever building a prompt context for a forecast about decision date `t`
may return a learned rule / prior record `R` from the ledger **if and only
if**:

```
R.resolution_date < t          # R's outcome was already knowable before t
  AND
R.resolved_at IS NOT NULL      # R was actually graded, not merely due, before t
  AND
R.resolved_at <= t             # R was graded on or before t, not after
  AND
R.outcome IS NOT NULL          # a voided record contributes nothing (belief_state's own rule)
```

Three clauses, not one, because each closes a distinct leak:
`resolution_date < t` alone would admit a rule whose window closed before `t`
but that the resolver had not yet actually graded by `t` (the resolver runs
on its own cron, per `belief_state.py`'s own "grading early is
indistinguishable from being right early" — the retriever must respect the
SAME asymmetry: retrieving a not-yet-graded rule's would-be Brier is
retrieving information from the future just as surely as retrieving its
outcome would be). `resolved_at <= t` is the operative gate in practice
(since `resolved_at` is only ever set once `resolution_date` has passed, by
construction of `resolve_one`), but stating `resolution_date < t` separately
documents WHY the gate is dated the way it is, for a future reader who only
sees `resolved_at`.

For M2's distilled `learned_rules.jsonl` (text rules with their own Brier,
not raw `PredictionRecord`s), the identical predicate applies to the rule's
own `computed_through_date` field (the last date any evidence contributing to
the rule's Brier was resolved) — a learned rule is itself just a
higher-level `PredictionRecord` for this purpose and gets the same PIT gate,
per M2's "a rule is a forecast about future forecasts and is graded like
one."

### 5.2 Where it is enforced

In the retriever function itself (e.g.
`backend/services/rule_retrieval.py::retrieve_for_date(scope, t) ->
list[dict]`), as a hard filter applied to every candidate BEFORE relevance
ranking/embedding similarity — never as a post-filter on an already-ranked
list (a post-filter that silently drops the top-ranked hindsight-leaking
result and returns the next one changes WHICH rule gets retrieved without
that being visible in a test that only checks "was a leaking rule in the
final list"; a pre-filter that shrinks the candidate POOL is testable by
checking pool size before/after).

### 5.3 The test (both directions, per invariant 19's testing convention)

```python
from datetime import date
import pytest

def test_retrieval_excludes_rule_resolved_after_t():
    """Plant one rule resolved AFTER the query date t; assert it is NOT
    retrieved. This is the leak-prevention direction."""
    t = date(2026, 6, 1)
    planted = make_learned_rule(
        rule_id="R-LEAK-1",
        applies_to_scope="AAPL",
        resolution_date=date(2026, 6, 15),   # resolves AFTER t
        resolved_at=date(2026, 6, 16),
        outcome=1, brier=0.04,
    )
    ledger = [planted]
    result = retrieve_for_date("AAPL", t, ledger=ledger)
    assert planted["rule_id"] not in {r["rule_id"] for r in result}

def test_retrieval_includes_rule_resolved_before_t():
    """The same rule, resolved well BEFORE t, IS retrieved. Proves the
    filter is a date gate and not an accidental blanket exclusion —
    a retriever that returns [] for every query would pass the first test
    for the wrong reason."""
    t = date(2026, 6, 1)
    planted = make_learned_rule(
        rule_id="R-OK-1",
        applies_to_scope="AAPL",
        resolution_date=date(2026, 1, 15),   # resolves BEFORE t
        resolved_at=date(2026, 1, 16),
        outcome=1, brier=0.04,
    )
    ledger = [planted]
    result = retrieve_for_date("AAPL", t, ledger=ledger)
    assert planted["rule_id"] in {r["rule_id"] for r in result}

def test_retrieval_excludes_rule_due_but_not_yet_actually_resolved():
    """resolution_date < t but resolved_at is still None (the resolver
    cron simply had not run yet as of t in the historical replay this
    retrieval is being tested against) — must ALSO be excluded, closing
    the 'due but not graded' leak distinct from the plain future-date leak."""
    t = date(2026, 6, 1)
    planted = make_learned_rule(
        rule_id="R-LEAK-2",
        applies_to_scope="AAPL",
        resolution_date=date(2026, 5, 1),    # window closed before t
        resolved_at=None,                     # but never actually graded
        outcome=None, brier=None,
    )
    ledger = [planted]
    result = retrieve_for_date("AAPL", t, ledger=ledger)
    assert planted["rule_id"] not in {r["rule_id"] for r in result}
```

`retrieve_for_date`'s `today`/`t` parameter must be injectable (same pattern
as `belief_state.resolve_one(..., today: date | None = None)`) so this test
suite needs no clock-mocking and runs inside the offline, un-hangable fast
test suite.

---

## 6. Open items for the builder (not blocking, but flagged)

1. **RavenPack taxonomy §1.1 is unverified this session** — re-attempt a live
   fetch (or use the connected `Bigdata.com` MCP tools, which are that
   company's current product) before treating §1.2's macro/market types as
   RavenPack-sourced in any `RESEARCH_CLAIM`-licensed writeup. They are
   currently sourced from the roadmap text itself (Murat's explicit list),
   which is sufficient for a `PRODUCT_EXPERIMENT`.
2. **8-K item mapping in §1.2 is unverified this session** — diff against
   `backend/services/edgar_events.py`'s live `_CFG["edgar_item_direction"]`
   before shipping; that file is the tested source of truth in this repo.
3. **Local-model call path**: this spec assumes a `local_qwen`-style provider
   distinct from `llm_analyzer`'s DeepSeek-only `_call_llm`. Confirm how the
   Aegis Desktop local llama-server is actually invoked from `event_intel.py`
   today (session memory references a FastAPI-fronted llama-server; grep
   `backend/services/` for the local-inference entry point before wiring L2).
4. **`mechanism_id` registry**: §4 assumes a frozen enum/registry of valid
   mechanism ids exists or will be created alongside this change — not
   specified here because it is a roadmap-wide naming decision (every
   mechanism across lanes B/E/X needs one canonical id), not a
   calibration-reporting concern.
