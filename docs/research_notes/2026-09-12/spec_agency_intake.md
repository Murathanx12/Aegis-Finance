# SPEC — Lane A Agency Intake: IPS, the Three Options, the Daily Review, Protect-First

Source: `docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
§7 (problem statement), §8 (Lane A, items A1-A5), §3 Lane B (B1-B6), §9 Lane M
(M1, PredictionRecord ledger). Licence: `PRODUCT_EXPERIMENT` throughout (no
significance gate, no MDE, no 24-month floor — a frozen contract before the
first decision is the only requirement, per CLAUDE.md THREE LICENCES).

Repo objects this spec builds on, read in full before writing this document:
- `backend/strategy/contract.py` — `Strategy`, `Universe`, `Signal`,
  `Construction`, `HoldRule`, `Sizing`, `CostModel`, `Benchmark`, `Objective`,
  `LossBudget`, `Licence`, `loss_budget_worst_case()`.
- `backend/services/belief_state.py` — `PredictionRecord`, `Observable`,
  `HORIZONS`, `make_prediction()`, `append()`, `_hash()`.
- `backend/data/paper_portfolios.yaml` — the THREE existing personality-keyed
  sleeve mandates (`conservative`/`balanced`/`aggressive`) with concrete
  `max_single_name`, `max_sector`, `rebalance_frequency`, `crash_overlay`
  numbers. This is the closest same-repo precedent for "personality to number"
  and is the primary numeric source for section 1's table, extrapolated to
  the fourth (`extreme_growth`) tier where the repo has no precedent (flagged).
- `backend/data/book_lanes.yaml` — how a lane's config hash and seeding
  discipline work today (no historical buy prices, current-market seeding).
- `docs/OPTIMUS_OBJECTIVE.md` section 0.9 — "One brain, several utility
  functions ... capital preservation, balanced, aggressive, extreme growth.
  Murat's own book may run aggressive without the public system inheriting
  one universal risk profile" — the four personalities are DECLARED
  PREFERENCES, not inferred from data.
- `docs/research_notes/2026-09-11/research_agency.md` section 1 (CFA IPS
  five-part shape) and section 2 (SEC IM Guidance 2017-02 boundary).
- `CLAUDE.md` SESSION START PROTOCOL rule 4 — the worst-case-in-dollars
  formula (n times notional% times stop%, gross-over-equity) and the rule
  that a wider stop on uncapped gross is a BIGGER loss, so gross and stop are
  always printed together, never one alone.

---

## 1. THE IPS SCHEMA

### 1.1 JSON Schema (draft-07)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://aegis.local/schemas/ips.schema.json",
  "title": "InvestmentPolicyStatement",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "ips_id", "ips_hash", "created_utc", "schema_version", "licence",
    "client_facts", "objectives_and_constraints", "risk_profile",
    "eligible_universe", "review_cadence", "personality", "amends_ips_hash"
  ],
  "properties": {
    "ips_id": {"type": "string", "description": "stable across amendments; the human-facing identity"},
    "ips_hash": {"type": "string", "pattern": "^[0-9a-f]{16}$", "description": "SHA-256 of the canonical JSON (1.7), truncated to 16 hex, matching Strategy.fingerprint's width in contract.py"},
    "created_utc": {"type": "string", "format": "date-time"},
    "schema_version": {"const": "1.0.0"},
    "licence": {"const": "PRODUCT_EXPERIMENT"},
    "amends_ips_hash": {"type": ["string", "null"], "pattern": "^[0-9a-f]{16}$", "description": "null for the first IPS in a lineage; else the ips_hash this one amends (1.8)"},

    "client_facts": {
      "type": "object",
      "additionalProperties": false,
      "required": ["capital_usd", "horizon_months", "intake_answers_hash"],
      "properties": {
        "capital_usd": {"type": "number", "exclusiveMinimum": 0},
        "horizon_months": {"type": "integer", "minimum": 1},
        "intake_answers_hash": {"type": "string", "pattern": "^[0-9a-f]{16}$", "description": "hash of the raw questionnaire answers (1.3), so the IPS is traceable to the exact answers that produced it without re-storing them inline"}
      }
    },

    "objectives_and_constraints": {
      "type": "object",
      "additionalProperties": false,
      "required": ["personality", "liquidity_need", "cash_floor_pct", "constraints"],
      "properties": {
        "personality": {"enum": ["preservation", "balanced", "aggressive", "extreme_growth"]},
        "liquidity_need": {"type": "number", "minimum": 0, "maximum": 1, "description": "fraction of capital that must be reachable within 90 days"},
        "cash_floor_pct": {"type": "number", "minimum": 0, "maximum": 1, "description": "derived: max(liquidity_need, personality minimum cash floor) -- see 1.5"},
        "constraints": {
          "type": "array",
          "items": {"type": "string", "pattern": "^(NO_SINGLE_NAME:[A-Z.]{1,10}|NO_SECTOR:[A-Z_]+|ESG_EXCLUDE:[a-z_]+|TAX_LOT:DEFERRED)$"}
        }
      }
    },

    "risk_profile": {
      "type": "object",
      "additionalProperties": false,
      "required": ["ability_score", "willingness_score", "composite_score", "questionnaire_version", "answers"],
      "properties": {
        "ability_score": {"type": "number", "minimum": 0, "maximum": 4},
        "willingness_score": {"type": "number", "minimum": 0, "maximum": 4},
        "composite_score": {"type": "number", "minimum": 0, "maximum": 4, "description": "min(ability_score, willingness_score) -- CFA IPS convention: stated willingness never overrides measured ability (1.3)"},
        "questionnaire_version": {"const": "AEGIS-RQ-1"},
        "answers": {"type": "array", "minItems": 8, "maxItems": 8, "items": {"type": "integer", "minimum": 0, "maximum": 4}}
      }
    },

    "eligible_universe": {
      "type": "object",
      "additionalProperties": false,
      "required": ["source", "floor_dollar_vol_usd", "excluded_tickers", "excluded_sectors"],
      "properties": {
        "source": {"type": "string", "description": "maps to Universe.source in contract.py"},
        "floor_dollar_vol_usd": {"type": "number", "minimum": 0},
        "excluded_tickers": {"type": "array", "items": {"type": "string"}},
        "excluded_sectors": {"type": "array", "items": {"type": "string"}}
      }
    },

    "review_cadence": {
      "type": "object",
      "additionalProperties": false,
      "required": ["daily_review", "rebalance_frequency"],
      "properties": {
        "daily_review": {"const": true, "description": "A3: the daily review always runs regardless of rebalance_frequency"},
        "rebalance_frequency": {"enum": ["daily", "weekly", "monthly", "quarterly"]}
      }
    },

    "personality": {"enum": ["preservation", "balanced", "aggressive", "extreme_growth"], "description": "duplicated at top level for cheap filtering; must equal objectives_and_constraints.personality"}
  }
}
```

### 1.2 CFA five parts, mapped from intake

Intake body: `{capital, horizon_months, personality, constraints[], liquidity_need}`
(`POST /api/agency/intake`, item A1).

| CFA IPS part (research_agency.md section 1, CFA position paper) | IPS field | filled from |
|---|---|---|
| 1. Client factual data | `client_facts` | `capital`, `horizon_months` verbatim; `intake_answers_hash` from the questionnaire (1.3) |
| 2. Objectives & constraints (time horizon, liquidity, risk tolerance) | `objectives_and_constraints` | `personality` (declared, 1.3, or overridden by user), `liquidity_need` verbatim, `cash_floor_pct` derived (1.5), `constraints[]` verbatim, validated against the vocabulary (1.6) |
| 3. Risk profile: ability vs willingness | `risk_profile` | the 8-question instrument (1.3); `composite_score = min(ability, willingness)` |
| 4. Eligible investments (approved list, exclusions) | `eligible_universe` | `Universe` fields from `contract.py`, filtered by `constraints[]` |
| 5. Review cadence / governance | `review_cadence` | `daily_review = true` always (A3); `rebalance_frequency` from the personality table (1.4) |

The LLM drafts the prose explanation shown to the user (A1: "the LLM drafts
the prose; the engine fills every number") — the JSON above is the number the
engine fills; the prose lives in a sibling field the schema does not
constrain (`ips_prose_md`, free text, not hashed — see 1.7).

### 1.3 The risk questionnaire (8 questions)

CFA IPS practice: **composite risk tolerance is bounded by the LOWER of
ability and willingness** — a client who says "I can take a lot of risk" but
has a 3-month emergency fund and no other assets is not high-ability, and the
IPS may not let stated willingness override it. Sources (verified via
WebSearch this session, not from memory alone): Grable & Lytton 1999
("Financial Risk Tolerance Revisited: The Development of a Risk Assessment
Instrument," *Financial Services Review* 8(3), pp. 163-181 — the 13-item
scale; Cronbach's alpha 0.77 in a 2007-13 replication) for Q5, Q7, Q8's
hypothetical-loss, experience, and loss-aversion item shapes; the Federal
Reserve Board's Survey of Consumer Finances (SCF) risk-tolerance question —
four ordinal categories, "take substantial financial risk expecting
substantial returns" / "above average risk, above average returns" /
"average risk, average returns" / "not willing to take any financial risk" —
for Q6's four-point risk ladder; `research_agency.md` section 1 CFA position
paper for the ability/willingness split itself.

| # | question | scores (0-4) | dimension | source |
|---|---|---|---|---|
| Q1 | Years until you need this money (horizon) | 0=under 1yr .. 4=10yr+ | ability | CFA IPS time horizon |
| Q2 | What fraction might you need within 12 months? | 0=over 50% .. 4=0% | ability | CFA IPS liquidity constraint |
| Q3 | How stable is your income over the next 2 years? | 0=very unstable .. 4=very stable | ability | SCF-style income-stability proxy |
| Q4 | What fraction of your total net worth is this capital? | 0=over 75% .. 4=under 10% | ability | capacity-for-loss (CFA IPS ability) |
| Q5 | If this dropped 20% in a month, what would you do? | 0=sell everything .. 4=buy more | willingness | Grable-Lytton hypothetical-loss item |
| Q6 | Which statement best matches the risk you're willing to take? (SCF's own 4 categories: not willing to take any risk / average risk for average return / above-average risk for above-average return / substantial risk for substantial return) | 0=not willing .. 4=substantial (SCF's 4 categories mapped onto the 0-4 scale, with room for a neutral tie-break) | willingness | Federal Reserve SCF risk-tolerance item |
| Q7 | Investment experience (years actively investing) | 0=none .. 4=10yr+ | willingness | Grable-Lytton experience item |
| Q8 | "I am more concerned about losing money than about missing gains" (1-5 Likert, reverse-scored) | 0=strongly agree .. 4=strongly disagree | willingness | Grable-Lytton loss-aversion item |

`ability_score = mean(Q1..Q4)`, `willingness_score = mean(Q5..Q8)`,
`composite_score = min(ability_score, willingness_score)`. Personality bands
(engine default; user may override downward but never upward without an
explicit acknowledgement string stored in `notes_text`):

| composite_score range | personality |
|---|---|
| [0.0, 1.0) | preservation |
| [1.0, 2.0) | balanced |
| [2.0, 3.0) | aggressive |
| [3.0, 4.0] | extreme_growth |

### 1.4 personality to numbers (the four-row table)

Sources: `backend/data/paper_portfolios.yaml` lines 133-190 (`conservative`,
`balanced`, `aggressive` lanes — the repo's only existing personality-keyed
numeric lanes) for `max_sector`, `rebalance_frequency`, and the crash-overlay
shape; `backend/strategy/contract.py` `Construction` defaults (`k=12`,
`max_single_name=0.20`) and `Objective.__post_init__`'s own worked example
(`drawdown_budget`, e.g. -0.35, "aggressive personality," line 309) for the
`aggressive` row, which is therefore not extrapolated but quoted from source;
CLAUDE.md rule 4 for the worst-case formula. `extreme_growth` has **no repo
precedent** — every number in that row is an extrapolation along the same
step-size the other three rows already show, flagged explicitly, and OWED a
receipt once the first extreme_growth book runs (CLAUDE.md: "a headline
number belongs in a RECEIPT").

| personality | `k` (Construction) | `max_single_name` | `gross_cap` | `stop_loss` | worst case (n x notional% x stop%) | `drawdown_budget` (Objective) | `rebalance_frequency` | cash floor minimum |
|---|---|---|---|---|---|---|---|---|
| preservation | 20 | 0.05 | 1.00 | -0.08 | 20 x 5.0% x 8% = **8.0%** of equity, gross 1.00x | **-0.10** | monthly | 0.10 |
| balanced | 15 | 0.10 | 1.00 | -0.10 | 15 x 6.67% x 10% = **10.0%** of equity, gross 1.00x | **-0.20** | monthly | 0.05 |
| aggressive | 12 | 0.20 | 1.00 | -0.12 | 12 x 8.33% x 12% = **10.0%** of equity, gross 1.00x | **-0.35** (contract.py:309, quoted) | weekly | 0.02 |
| extreme_growth (extrapolated, no repo precedent) | 8 | 0.30 | **1.50** | -0.15 | 8 x 18.75% x 15% = **22.5%** of equity, gross **1.50x** (printed beside the stop per CLAUDE.md rule 4 — never quote the stop without the gross) | **-0.50** | daily | 0.00 |

Notes:
- `k` and `max_single_name` come from `Construction` (contract.py); weighting
  is `ew` for all four rows so `notional%_per_name = gross_cap / k`.
- `extreme_growth` is the only tier permitted `gross_cap > 1.00` (leverage).
  This is the exact failure mode CLAUDE.md rule 4 names ("twelve names times
  25% = 300% gross") — the builder MUST print `gross_over_equity` beside
  every worst-case number for this tier, never the stop alone;
  `loss_budget_worst_case()` (contract.py) already returns both fields.
- preservation/balanced/aggressive all land at 10.0% worst-case-of-equity or
  below by construction (k and max_single_name were chosen to land there);
  this is a deliberate design choice for this spec, not a repo invariant —
  the builder may re-tune k/max_single_name as long as the worst-case number
  is recomputed and re-printed, never hand-edited.
- cash floor minimum is a floor, not a target: see 1.5.

### 1.5 `liquidity_need` to a cash floor

```
cash_floor_pct = max(liquidity_need, PERSONALITY_CASH_FLOOR[personality])
```

`liquidity_need` from intake is a fraction in [0, 1] — "what fraction of
capital might you need within 90 days." `PERSONALITY_CASH_FLOOR` is the last
column of the table in 1.4. The cash sleeve is EXCLUDED from
`loss_budget_worst_case()`'s `n_names`/`gross` calculation (it cannot be
stopped out) and is the first thing a protect-first breach (section 4) grows,
never shrinks.

If `liquidity_need > 1 - (the chosen personality's minimum invested
fraction)` — i.e. the declared liquidity need cannot be met without
breaching the personality's own risk budget — the engine REFUSES the intake
with a typed error naming which of `personality` or `liquidity_need` must
change. It does not silently down-shift the personality, because that would
be the engine overriding a declared preference (OPTIMUS_OBJECTIVE section 0.9).

### 1.6 `constraints[]` vocabulary

Regex-validated against the JSON Schema pattern in 1.1:

| token | meaning | engine effect |
|---|---|---|
| `NO_SINGLE_NAME:<TICKER>` | exclude one ticker from `eligible_universe` | ticker removed from `Universe`; if it was already held, next daily review forces `sell` |
| `NO_SECTOR:<SECTOR>` | exclude a sector, using one of `paper_portfolios.yaml`'s 11 sector-ETF codes as the vocabulary | all names tagged with that sector removed from `Universe` |
| `ESG_EXCLUDE:<category>` | exclude a category (`fossil_fuels`, `tobacco`, `weapons`, `gambling`, `alcohol`) | mapped to a static ticker/sector exclusion list maintained alongside `paper_portfolios.yaml`; `gambling` would exclude `DKNG`, already a real holding in `book_lanes.yaml`, so the mapping table is a real reviewed file, not a stub |
| `TAX_LOT:DEFERRED` | acknowledgement placeholder only | the engine ECHOES BACK "tax-loss harvesting not yet implemented" on every review that touches a lot-level decision (house rule: a check that did not run is not a check that passed — CLAUDE.md) |

Unknown tokens are a hard refusal at intake (422), not a silently-dropped
constraint — same house rule as `Strategy`'s "unknown field to refusal"
(roadmap B2).

### 1.7 The hash rule

Canonical form, identical algorithm to `contract.py::_sha` and
`belief_state.py::_hash`:

```python
import hashlib, json

def ips_hash(ips_dict_without_hash_field: dict) -> str:
    blob = json.dumps(ips_dict_without_hash_field, sort_keys=True,
                       separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
```

`ips_hash` is computed over the full IPS document with the `ips_hash` field
itself, `ips_prose_md`, and `created_utc` excluded (a hash cannot include
itself; timestamps must not perturb the identity of an otherwise-identical
IPS re-submitted a second later). `sort_keys=True` makes the hash stable
across key order — this is the exact property Test 1 (section 6) checks.

### 1.8 What requires a new IPS vs an amendment

| change | new IPS (`ips_id` changes, `amends_ips_hash=null`) | amendment (same `ips_id`, `amends_ips_hash = prior ips_hash`) |
|---|---|---|
| `capital` changes by more than +/-20% | yes | |
| `capital` changes by <= 20% | | yes |
| `horizon_months` changes | yes | |
| `personality` changes | yes (a different personality is a different declared preference, not a tweak — OPTIMUS_OBJECTIVE section 0.9) | |
| `liquidity_need` changes and forces a personality-band conflict (1.5) | yes | |
| `liquidity_need` changes, no conflict | | yes |
| `constraints[]` added or removed | | yes |

Every `PaperBook` (Lane B) carries the `ips_hash` it was created under (A1
acceptance: "the IPS hash is on every book the intake creates"). An amendment
does not retroactively change a book's `ips_hash`; a NEW IPS starts a new
generation of books, and the old generation's books are archived, not
deleted (same "mutation is a new object" discipline as `Strategy.with_`).

---

## 2. THE THREE OPTIONS

A2: "From one IPS the engine proposes three books — preservation / balanced /
aggressive expressions of the same IPS — each with its twin, worst case in
dollars, expected drawdown at the declared budget, and the hold rule. Murat
picks one; the other two are held as shadow books." Note the IPS's own
`personality` may be `extreme_growth` (1.3); when it is, the three proposed
books are `balanced` / `aggressive` / `extreme_growth` — the engine always
proposes the chosen personality plus its two neighbours on the risk ladder in
1.4, so the human sees one step more conservative and (if not already at the
ceiling) one step more aggressive than what they said, not three arbitrary
buckets. `preservation` is always one of the three unless the IPS's chosen
personality already is `preservation`, in which case the neighbours are
`preservation` (chosen) / `balanced` / and a placebo-safe cash-heavy fourth is
NOT invented — three books, never four, per A2's own count.

### 2.1 Per-personality `Strategy` contract instantiation

Each proposed book is one `backend.strategy.contract.Strategy`, built from the
IPS's `eligible_universe` and the row of the table in section 1.4 matching
that book's personality label (not necessarily the IPS's chosen personality —
the two neighbour books use their OWN row).

```python
Strategy(
    strategy_id=f"agency-{ips.ips_id}-{personality}",
    title=f"{ips.ips_id} / {personality}",
    universe=Universe(
        name=f"agency-{ips.ips_id}-universe",
        source="ips_eligible_universe",
        floor_dollar_vol_usd=ips.eligible_universe.floor_dollar_vol_usd,
        max_names=None,           # Construction.k is the binding cap, not Universe
        note="filtered by constraints[] at IPS build time (1.6)",
    ),
    signal=Signal(
        name="agency_default_composite",   # NOT arena_composite -- THE BOTTLENECK
        column="composite_rank",           # a Lane A book is its OWN mechanism entry,
        direction=1,                       # never a weight folded into an existing one
        source="lane_a_v1",
    ),
    construction=Construction(
        rule="top_k",
        k=TABLE[personality].k,                       # 20/15/12/8, section 1.4
        weighting="ew",
        max_single_name=TABLE[personality].max_single_name,
        gross_cap=TABLE[personality].gross_cap,        # 1.00 except extreme_growth 1.50
    ),
    hold=HoldRule(
        horizon_periods=HOLD_HORIZON[personality],     # 21/21/21/5 sessions -- 2.2 below
        stop_loss=TABLE[personality].stop_loss,
        roi_ladder=ROI_LADDER[personality],             # 2.2
        scheduled_review_periods=1,                     # daily review always runs (A3)
    ),
    sizing=Sizing(
        rule="equal_weight",
        gross_cap=TABLE[personality].gross_cap,
        notional_usd=ips.client_facts.capital_usd * (1 - cash_floor_pct),
    ),
    costs=CostModel(transaction_cost_bps=5.0, slippage_bps=1.0),   # never zero (CostModel refusal)
    benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=True),
    objective=Objective(
        name="terminal_wealth_at_drawdown_budget",       # the PRODUCT ruler, not alpha_intercept
        drawdown_budget=TABLE[personality].drawdown_budget,
        utility="risk_adjusted" if personality != "extreme_growth" else "risk_seeking",
    ),
    loss_budget=LossBudget(
        positions_judged=TABLE[personality].k * 4,        # ~one year of turnover at the book's cadence
        expected_losers=round(TABLE[personality].k * 4 * 0.45),  # 45% base-rate loser fraction, a receipt-owed placeholder until the farm has a same-shape control
    ),
    licence=Licence.PRODUCT_EXPERIMENT,
    engine_params={"ips_hash": ips.ips_hash, "personality": personality,
                   "origin": "human_text", "origin_text": ips.intake_raw_text},
)
```

### 2.2 Hold-rule families

Three named families, one per risk tier, matching the `roi_ladder` shape in
`HoldRule` (freqtrade's `minimal_roi`, contract.py docstring):

| family | personalities | `horizon_periods` | `roi_ladder` | `min_hold_periods` |
|---|---|---|---|---|
| `protect_first_ladder` | preservation | 21 | `{0: 0.15, 10: 0.08, 20: 0.03}` (hold for a big move, take a smaller one sooner) | 5 |
| `core_ladder` | balanced | 21 | `{0: 0.20, 10: 0.10, 20: 0.04}` | 3 |
| `momentum_ladder` | aggressive, extreme_growth | 21 (aggressive) / 5 (extreme_growth) | `{0: 0.25, 5: 0.12}` (aggressive) / `{0: 0.15}` (extreme_growth — one rung, matches the shorter horizon) | 0 |

### 2.3 The twin (B3)

Every proposed book gets a twin at creation, `PaperBook.control_twin_id`
pointing to a `Strategy` identical in `universe`, `cadence`, `costs`,
`benchmark`, and `licence`, but with `signal.name = "random_genome_null"` and
a universe DRAWN AT RANDOM from the same liquidity band (RW1's random-genome
null, roadmap B3). Long-only books additionally get a beta-matched twin
(`signal.name = "beta_matched_index_sleeve"`, weights chosen to match the
proposed book's realised beta over its own trailing window). **A book's
number is never shown without its twin's** (B3 acceptance) — the board always
renders `(book_return, book_drawdown)` beside `(twin_return, twin_drawdown)`.

### 2.4 Worst case in dollars, printed

For `capital_usd = C` and the chosen personality's row from 1.4:

```
worst_case_usd = -(k * (gross_cap/k) * |stop_loss|) * C * (1 - cash_floor_pct)
                = -(gross_cap * |stop_loss|) * C * (1 - cash_floor_pct)
```

Worked for a $50,000 IPS, `balanced`, `cash_floor_pct=0.05`:
`worst_case_usd = -(1.00 * 0.10) * 50000 * 0.95 = -$4,750`. This number, its
`gross_over_equity`, and the `verdict` string are exactly the return shape of
`contract.py::loss_budget_worst_case()` — the builder calls that function
directly rather than re-deriving the arithmetic (CLAUDE.md rule 4 exists
precisely so this is never hand-rederived per caller).

### 2.5 Shadow books (A2)

The two un-chosen personality books are created identically to the chosen
one (`PaperBook.origin = "night_job"`, not `human_text`, since Murat did not
click Hold on them — B2's "Murat clicks Hold" gate applies only to the chosen
book) and marked `shadow=True`. Shadow books:
- run the same cadence, mark from the same bars (B4), and get forecast rows
  (B5) exactly like the chosen book;
- are NEVER shown as the primary number on the board — they render in a
  collapsed "what if you'd picked..." panel beside the chosen book, always
  with their own twins (2.3);
- are graded on the SAME clock as the chosen book, so "the choice itself is
  graded" (A2) becomes a literal three-arm comparison with a shared start
  date, not three backtests run whenever someone asks.

---

## 3. THE DAILY REVIEW

A3: "for each holding, `{hold, sell, buy_more, trim}` with a probability,
the news and events that moved it..., and the forecast row written BEFORE
the call is shown."

### 3.1 Decision vocabulary and probability semantics

| decision | meaning | probability field's meaning |
|---|---|---|
| `hold` | no change to the position | `P(position beats control_twin over the book's hold horizon)` |
| `sell` | close the position entirely | `P(position beats control_twin \| held to horizon)` -- LOW, is the reason for the call |
| `buy_more` | increase the position, bounded by `max_single_name` | `P(position beats control_twin over the book's hold horizon)` -- HIGH, is the reason |
| `trim` | reduce the position toward, not to, zero | same probability, MIDDLE of the book's calibration range; used when `probability` is positive but `Construction.max_single_name` or `Sizing.gross_cap` would otherwise be breached |

In every row, `probability` is `Observable.BEATS_BENCHMARK`'s probability
(`belief_state.Observable`, contract already exists) with `benchmark =
control_twin_id` (2.3) and `horizon_days` the book's cadence mapped to the
nearest value in `belief_state.HORIZONS = (1, 2, 5, 20, 60, 120, 252)`. The
decision itself (`hold`/`sell`/`buy_more`/`trim`) is a DERIVED label from
`probability` and the current position size relative to `max_single_name`, not
a second free-floating number the LLM can set independently of the
probability it just gave — a `sell` label attached to `probability=0.62` is a
contract violation the engine refuses to render.

### 3.2 Inputs to one review row

| input | source |
|---|---|
| typed news events for the name, since the last review | Lane L2 (typed events) |
| upcoming prints (earnings, macro calendar) for the name | the existing calendar service |
| the calibrated target's interval | Lane E3 (adaptive conformal interval on the head with positive control-adjusted IC) |
| current drawdown state for the BOOK | section 4.1 (peak-to-trough on the book's NAV) |
| the market sensor's regime read | invariant 4 / X4 (NVDA/SPY sensor) — informs, does not override, the probability |

### 3.3 The forecast-row shape

One `belief_state.PredictionRecord` per (book, holding, review date), built
through `make_prediction()`, never constructed by hand (so the existing
validation — horizon in `HORIZONS`, probability in [0, 1], `BEATS_BENCHMARK`
requires a `benchmark` — applies unchanged):

| `PredictionRecord` field | filled from |
|---|---|
| `prediction_id` | generated, `{book_id}-{ticker}-{review_date}` |
| `ticker` | the holding |
| `specialist` | `"agency_daily_review"` |
| `observable` | `Observable.BEATS_BENCHMARK` |
| `horizon_days` | the book's cadence, nearest `HORIZONS` value |
| `probability` | 3.1 |
| `benchmark` | `control_twin_id` (2.3) |
| `made_at` | the review's wall-clock timestamp |
| `resolves_after` | `PredictionRecord.resolution_date(made_at, horizon_days)` |
| `thesis` / `counter_thesis` | the LLM's typed-event read and its negation, one sentence each |
| `next_observable` | the specific typed event that would flip the call (X2's direction-flip test, applied prospectively) |
| `model`, `model_version`, `prompt_hash`, `input_snapshot_hash` | DeepSeek call provenance (the sole provider) |
| `prior` / `posterior` / `belief_change` | filled when the belief-change contract is used: `prior` = yesterday's `probability` for the same (book, ticker); required, not optional, for a review row (A3 exists to show the review MOVED because of something) |
| `arm` | the book's `strategy_id` |
| `session_as_of` | the trading session the review is ABOUT |
| `evidence_population` | stamped by `append()` from the ledger being written (belief_state.py's own stamping rule) |

### 3.4 The ordering constraint

**The row is written and hashed BEFORE the call is displayed.** Concretely:
1. The engine computes `probability`, builds the `PredictionRecord` via
   `make_prediction()`, and calls `belief_state.append([record])`.
   `append()` returns `None` by house rule (belief_state.py docstring: "so no
   caller can branch on a write") — the render path must not branch on the
   append's return value, only on having successfully called it.
2. `record_outcome()` (used later, at resolution) likewise returns `None` —
   grading never lets a caller act on the resolution instant.
3. Only after step 1 succeeds does the API response include the decision
   label and probability for that (book, ticker, date). If step 1 raises
   (e.g. `ValueError` from `make_prediction`'s guards), the review row for
   that holding is NOT shown — a refusal, not a silently-ungraded display.

This ordering is what makes "every call has a forecast row; every forecast
row is graded" (A3 acceptance) a structural guarantee rather than a hope: it
is impossible for the UI to show a call whose `PredictionRecord` does not
already exist on disk with an earlier `made_at` timestamp and a hash the test
in section 6 can independently recompute.

---

## 4. PROTECT-FIRST

A4: "Drawdown budget per book from the IPS; a breach flips the book to its
preservation twin's construction, logged, reversible by a human."

### 4.1 The breach rule

Measured on NAV at the close, once per session (never intraday — the same
"marks are one row per (book, timestamp)" discipline as B4):

```
peak_nav = max(nav[t'] for t' <= t)          # running peak, this book's own history since inception or last reset
drawdown_t = (nav[t] - peak_nav) / peak_nav   # <= 0
breach = drawdown_t <= objective.drawdown_budget   # both negative ratios; breach when drawdown is AS BAD OR WORSE than the budget
```

`peak_nav` resets only at IPS regeneration (1.8's "new IPS"), never at an
amendment and never at a protect-first flip itself — a book that breaches,
flips, and recovers is still measured against its ORIGINAL peak, so a second
breach cannot be avoided merely by the act of flipping.

### 4.2 The flip

On `breach = True`:
1. The book's live `Strategy` is replaced by `Strategy.with_(construction=...,
   hold=..., sizing=..., objective=...)` copying every field from the
   **preservation** row of the table in section 1.4 (not necessarily "this
   book's own twin" — the twin (2.3) is a random/beta-matched control used
   for grading, never a construction the book can BE; "preservation twin's
   construction" in A4 means the preservation PERSONALITY's construction,
   the most conservative row of 2.1's table, applied as a new frozen
   `Strategy` via `with_`, which contract.py's own docstring names as "a
   mutation is a new strategy, never an edit").
2. A new `strategy_id` is minted (`{original_id}-PROTECTED-{flip_seq}`); the
   original `Strategy` object is retained, unmutated, in the book's history.
3. The book's `origin` field gains `origin_text = f"protect-first flip on
   {date}, drawdown {drawdown_t:.2%} vs budget {budget:.2%}"`.

### 4.3 The log entry

One row per flip (and per reversal), appended to the same ledger family as
`PredictionRecord` (a receipt, not a log line that can scroll away):

```json
{
  "event": "protect_first_flip",
  "book_id": "...",
  "ips_hash": "...",
  "flip_seq": 1,
  "triggered_utc": "...",
  "nav_at_trigger": 0.0,
  "peak_nav": 0.0,
  "drawdown_at_trigger": -0.211,
  "drawdown_budget": -0.20,
  "from_strategy_fingerprint": "...",
  "to_strategy_fingerprint": "...",
  "reversible": true,
  "reversed_utc": null,
  "reversed_by": null
}
```

### 4.4 Human reversal

A human (Murat, attended — same discipline as `seed-a-lane`) may reverse a
flip via an explicit action that: (a) restores the pre-flip `Strategy` (the
retained object from 4.2 step 2, not a re-derivation), (b) writes
`reversed_utc`/`reversed_by` onto the SAME log row (never a new row that
could be read independently of the flip it reverses), and (c) does NOT reset
`peak_nav` — a reversed flip that breaches again immediately is a real second
breach, not a bug. The engine never reverses its own flip; protect-first is
one-directional automatically and bidirectional only by hand, matching
CLAUDE.md's "no LLM authority over real capital" posture extended to paper
capital's protective state.

### 4.5 The base-rate control

**How often would this rule fire on a book that is doing nothing unusual?**
Run the SAME breach rule (4.1) against the book's own control twin's NAV path
(2.3) over the same window. Because the twin shares the book's universe
liquidity band and cadence but carries no signal, the twin's breach rate is
the rate at which `drawdown_budget` would be crossed by CONSTRUCTION-LEVEL
volatility alone — the false-positive rate of protect-first under "nothing
is actually wrong, the signal just typically has this much noise." A book
whose real breach rate is not distinguishably higher than its twin's breach
rate is a book whose "protection" event was not informative; that
comparison, not the raw flip count, is what the Regret page (B6) reports for
this feature. This is the same shape as CLAUDE.md's "a null owes two tests"
standing rule (canon): the flip mechanism itself must be tested against the
null of "the same rule applied to noise," not only shown to fire.

---

## 5. PLAIN WORDS

A5: "Every number the agency shows has a one-sentence explanation the local
model writes from the receipt, and the receipt path. The average investor
reads the sentence; the sceptic reads the path."

### 5.1 Explanation template, per number

| number | template | receipt path |
|---|---|---|
| target / probability | "{TICKER} has a {probability:.0%} chance of beating its benchmark twin over the next {horizon} sessions, based on {n_events} recent news events and its {regime} market regime." | `predictions.jsonl#{prediction_id}` |
| interval | "The model's {lower:.1%} to {upper:.1%} range covers what actually happened {realised_coverage:.0%} of the time recently — {calibrated_or_not}." | `evidence_memory/calibration/{model}_{mechanism}.json` |
| worst case | "If every position in this book hit its stop on the same day, you would be down about ${worst_case_usd:,.0f} ({worst_case_pct:.1%} of this book), at {gross_over_equity:.2f}x gross exposure." | `contract.py::loss_budget_worst_case()` output, stored alongside the `Strategy` fingerprint |
| drawdown | "This book is down {drawdown_t:.1%} from its peak on {peak_date}; its budget is {drawdown_budget:.1%}, {distance} away." | `protect_first_flip` log family (4.3), even when no flip has fired (the row still exists, `breach=false`) |

Every sentence is generated by the local model FROM the receipt fields above
(never from a free-text summary the model invents independently of them) —
the same "the engine fills every number, the LLM drafts the prose" split as
A1.

### 5.2 The limits sentence

Appended, verbatim, to every plain-words panel (not only once per session):

> "This is a paper-trading tool for personal use; it is not investment
> advice, and nothing here should be read as an offer to manage money for
> anyone but the person running it. A tool that advises OTHERS for
> compensation is a different, regulated activity (SEC Investment Advisers
> Act; see `research_agency.md` §2) — before this becomes a multi-user
> product, that boundary is a question for counsel, not for this repo."

---

## 6. TESTS WITH KNOWN ANSWERS

| # | test | known answer |
|---|---|---|
| T1 | `ips_hash` is stable across key order | build the same IPS dict twice with `objectives_and_constraints` and `client_facts` inserted in reversed key order; `ips_hash(d1) == ips_hash(d2)` — guaranteed by `sort_keys=True` (1.7), and this test is the one thing that would catch a future refactor that swaps in a hash call without that flag |
| T2 | a personality row yields its documented worst case | `loss_budget_worst_case(strategy=<aggressive Strategy from 2.1>, n_names=12, notional_pct=1/12, equity_usd=100_000)["worst_case_usd"] == pytest.approx(-10_000.0, rel=1e-6)` and `["gross_over_equity"] == pytest.approx(1.0)` — the exact number in the `aggressive` row of 1.4's table, computed by the SAME function the builder must call, not re-derived in the test |
| T3 | a breach flips and reverts | seed a book at `drawdown_budget=-0.20`, feed a NAV path that touches `-0.21` from its peak on day N; assert `protect_first_flip` fires at day N with `to_strategy_fingerprint` equal to the `preservation`-row `Strategy`'s fingerprint (not the book's own twin's); then call the reversal action and assert the SAME log row (`flip_seq=1`) now carries `reversed_utc` non-null while `peak_nav` is unchanged from before the reversal (4.4's "does not reset peak_nav") |
| T4 | a review row precedes its display | mock the display layer to record the timestamp it received the call; assert `PredictionRecord.made_at < display_timestamp` for every row on a review pass, AND that `hashlib.sha256` over the persisted `PredictionRecord` (re-read from `predictions.jsonl` after `append()` returns) matches a hash computed independently from the same fields BEFORE the row was written — proving the persisted row is exactly the row the display used, not a re-serialization that could silently drift; additionally assert the API call that triggers `make_prediction()` raising (e.g. an out-of-range `probability`) results in NO row for that holding in the day's review response, per 3.4 point 3 |

Each test is written against the real `contract.py` / `belief_state.py`
functions (`loss_budget_worst_case`, `make_prediction`, `append`), not
against re-implementations in the test file — the point of T2 in particular
is that it fails the moment someone hand-codes a different worst-case
formula for the agency instead of calling the one function the repo already
has.
