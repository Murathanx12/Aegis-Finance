# World state, regime forecast rows, and the news-to-decision connection — design only (2026-10-07)

**RESULT IMPROVEMENT: NONE.** This is a design note (Sonnet, research licence, $0). Nothing here is built.
It answers owner asks A-E from the roadmap owner-review coverage matrix (`docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md`
§3 rows 22 ("LLM for broad regime calls"), 23 ("scenario backcasting"), 34 ("truth lane vs discovery lane"
→ field-level provenance), 43 ("news arm must be connected and weighed into decisions")) and the outside
guide's §17-21 vocabulary (`AEGIS_V1_BETA_FABLE_HANDOFF_2026-10-06.md` lines ~900-1020: world state belief
table, fact/claim/interpretation/prediction, latency edge, regime classification, scenario engine).

**Governing constraint, stated once:** every piece below is additive to code that already runs. The digest
(`backend/services/world_digest.py`) already writes typed, validated, enum-checked rows and graded forecast
rows under the three-licence doctrine (`PRODUCT_EXPERIMENT`, line 86). Nothing proposed here adds a second
measurement system; it extends the one that exists, because CLAUDE.md's rule — a module has a caller or the
suite fails — applies to a world-state table and a regime row exactly as it applies to any other service.

---

## 1. What exists today (file:line)

**Digest pipeline, two stages, both DeepSeek, both metered (`backend/services/world_digest.py`):**

- Stage 1 `extract_items` (line 721) types every item into a validated row via `type_row` (line 493-543):
  `topic, summary, event_type` (19-way enum, line 93), `tickers` / `tickers_unverified` (verified against the
  item's own text, never trusted from the model, line 499-510), `sectors` (26-way, line 97), `macro` (16-way,
  line 103), `sentiment/fear_greed/mgmt_confidence` (clipped -1..1), `uncertainty` (0..1), `novelty` (5-way),
  `forward_claims` (up to 3, each `{subject, direction, horizon, who}`). Cached by
  `sha(url|text|prompt_version)` (line 546) — nothing is ever paid for twice.
- Stage 2 `find_themes` (line 1013) → `implications_for` (line 1142) → `type_implication` (line 1091-1139):
  per theme, up to 8 implications, each `{subject, subject_type (ticker/sector/macro), direction, size_bucket
  (4-way), horizon_sessions (1/5/20), confidence, order (1st/2nd), chain, contradiction, mentioned}`. `chain`
  and `contradiction` are **required** (line 1129) — an implication without a stated mechanism and a stated
  falsifier is dropped, which is already the project's "a theory has a mechanism, a precursor and a
  falsifier" rule enforced in code, not prose.
- `implication_records` (line 1196-1287) turns one implication into 0-2 **frozen forecast ledger rows**
  (`backend/data/optimus/predictions.jsonl`, schema 1.4.0, `backend/services/belief_state.py` line 147-240):
  a **size** row (`ABS_MOVE_EXCEEDS`, probability = a frozen bucket map `WORLD_DIGEST_SIZE_BUCKET_P`, never the
  model's own number — line 1254-1266) and a **direction** row (`BEATS_BENCHMARK` vs SPY, shrunk `0.5 + 0.2 ×
  (raw-0.5)` toward the coin, line 1268-1286, because every LLM direction arm ever measured here is ≤ chance).
  Sample row read from `predictions.jsonl` (ticker DAL, 2026-09-29): `specialist: "news_digest:implication_v0"`,
  `observable: "abs_move_exceeds"`, `probability: 0.5`, `threshold: 0.0433`, `inputs_used.vol_prior_p: 0.397`
  (the control it must beat), `schema_version: "1.4.0"`, `evidence_population: "campaign_forward"`.
- Grading: `grade()` (line 1309) computes Brier(model) − Brier(control) per decision-date, per observable.
  `trust_from()` (line 1332-1354) takes the per-date mean, shrinks it under a **prior N(0, TAU²)**
  (`WORLD_DIGEST_TRUST_TAU=0.01`, `config.py:4983`), and only reports non-zero trust once
  `WORLD_DIGEST_TRUST_MIN_DATES=3` graded dates exist (`config.py:4986`) — trust is **exactly 0** below that,
  by construction, not by estimate.
- `shadow_contract()` (line 1359-1388) freezes the rule by content hash; `news_signal()` (line 1413) and
  `shadow_decision()` (line 1426-1446) are the only consumers: a tilt over a frozen base book
  (`WORLD_DIGEST_SHADOW_BASE_BOOK`), returning the base **exactly** when both trusts are 0 (line 1428,
  verified by the function's own docstring and the no-op arithmetic).

**Where the shadow tilt is actually used today (two places, both PAPER, neither is the real plan):**

1. `backend/services/decision_story.py` `freeze_plan` (line 650-661) computes `plan_plus_shadow_news` as a
   **frozen alternative** (`places_orders: false`, line 720) beside `actual`, `plan_full`, `buy_default`, etc.
   — graded, never executed.
2. `scripts/fleet_manager_run.py` `v2_body` (line 363-377) defines a **separate paper book** (hack6, "news
   sleeve"): long-only, `news_signal`'s `d_i>0` names, unit-sized, held a fixed number of sessions. This one
   *does* trade, in PAPER, under a deterministic rule with no LLM authority over size — but it is its own
   book, not the $1M PC-PAPER mandate.
3. `scripts/sim_run.py` — grepped for `shadow_decision` / `world_digest`: **zero matches** in `u_plan` (line
   1176). This is the C11 finding stated in the roadmap (§1): **the main plan reads no news.** Confirmed by
   decision_story's own `loo_news` leave-one-out, which returns `IDENTICAL_NOT_READ` (decision_story.py line
   584-590): removing news from the plan's inputs changes nothing, because it was never an input.
4. `backend/services/regret_ledger.py` (F7 note, line 32; loop at line 413-434) already grades the gap:
   `mdc_news_tilt = utility(plan + shadow tilt) − utility(plan)`, per session, per horizon, labelled
   `TRUST_AT_63` until 63 graded sessions exist. **This is the connection's report card; it already exists
   and needs no new code to start accruing** — it only needs a live `u_plan` session, which is the open item
   the 2026-10-06 handoff names (`docs/research_notes/2026-10-06/decision_story_and_regret_2026-10-06.md`,
   "No live story exists yet").

**Provenance taxonomy that already exists, one layer down (`backend/services/thesis_card.py`):**
`web_event_row` (line 1447-1489) tags every dated claim with `confidence_source` ∈ `{REGULATOR,
DIRECT_COMPANY_STATEMENT, MAJOR_WIRE, FORUM_CLAIM, AGGREGATOR}` (line 1474-1489) — a **source-credibility**
taxonomy, not the **epistemic-kind** taxonomy the owner asks for (fact vs. company claim vs. Aegis's own read
vs. a forecast). The two are orthogonal: a company's own 8-K is `DIRECT_COMPANY_STATEMENT` whether the number
in it is a filed fact (revenue) or a forward-looking claim (guidance). `vocab_type` (line 1377) separately
tags the claim's **event type** (19-way, unrelated to either axis). No existing field says which of
FACT/COMPANY_CLAIM/INTERPRETATION/FORECAST a given piece of text is — §4 below adds exactly that, reusing
these validators rather than building a fourth.

**No `thesis_cards.py` plural file exists** — the module is `backend/services/thesis_card.py` (singular);
the task brief's filename was close but not exact.

---

## 2. The world-state schema, and the update rule per cycle

### 2a. Schema (JSON, one document per digest cycle, additive to the digest's own output)

```json
{
  "schema": "world_state/v1",
  "as_of": "2026-10-07T12:00:01Z",
  "digest_id": "20261007T120001Z",
  "beliefs": {
    "ai_demand": {
      "direction": "up",
      "confidence": 0.62,
      "half_life_days": 10,
      "evidence_ids": ["item_a1b2...", "item_c3d4..."],
      "affected_entities": {"tickers": ["NVDA","AVGO"], "sectors": ["semiconductors"]},
      "causal_edges": [{"to": "semiconductor_capex", "sign": "+", "lag_sessions": 5}],
      "contradictions": [],
      "last_updated": "2026-10-07T12:00:01Z",
      "prior_direction": "up",
      "belief_change": 0.03,
      "provenance_mix": {"FACT": 2, "COMPANY_CLAIM": 3, "INTERPRETATION": 1}
    },
    "semiconductor_capex": {"...": "same shape"},
    "grid_power_demand": {"...": "..."},
    "commodity_shortages": {"...": "..."},
    "rates": {"...": "..."},
    "inflation": {"...": "..."},
    "credit": {"...": "..."},
    "dollar": {"...": "..."},
    "liquidity": {"...": "..."},
    "consumer_conditions": {"...": "..."},
    "china_policy": {"...": "..."},
    "geopolitical_risk": {"...": "..."},
    "defense_procurement": {"...": "..."},
    "energy_security": {"...": "..."},
    "biotech_regulatory": {"...": "..."},
    "prediction_market_state": {"...": "..."}
  },
  "unresolved_beliefs": ["defense_procurement"],
  "spend_usd": 0.021
}
```

Sixteen fixed topic keys (the owner's list, §17 of the outside guide). A topic with **no supporting evidence
this cycle is UNKNOWN, not fabricated**: it is omitted from `beliefs` and listed in `unresolved_beliefs`,
mirroring the project's own rule that a guard either derives its input or refuses (CLAUDE.md DO list). Each
belief's `direction` ∈ `{up, down, mixed, none}`, same enum discipline as `DIRECTIONS` (world_digest.py line
107); `confidence` and `half_life_days` are clipped/validated the same way `_clip` already validates
`sentiment` (line 196-204) — this is a new **validator function**, not a new validation philosophy.

### 2b. The update rule, per cycle

The belief table is **not** rebuilt from raw text. It is one more synthesis call, after `find_themes` and
`implications_for` already ran, over the **typed rows and implications that stage 2 produced** — the same
no-new-raw-text discipline the digest's own docstring states for stage 2 (`PROMPT INJECTION` section, line
45-55: "the synthesis never sees raw text: only enum-typed, length-capped, validated fields").

Per cycle, for each of the 16 topics with ≥1 relevant row this cycle (matched by the existing `macro` /
`sectors` enums on typed rows, no new matching logic needed):

1. Read the **previous** belief for that topic (the last digest's `world_state_*.json`, `previous_digest()`
   pattern already exists at world_digest.py line 1663).
2. Decay it by `half_life_days` (`confidence *= 0.5 ** (hours_since / (half_life_days*24))`) — an explicit,
   auditable number, not a vibe; this is the "evidence ages" mechanism the outside guide asks for (§17).
3. One DeepSeek call per topic-with-evidence (or one batched call across all topics-with-evidence this cycle
   — batching is cheaper and is exactly what `HEADLINE_SYSTEM` batching already does for headlines, line
   740-741) returns an updated `{direction, confidence, causal_edges, contradictions}` plus which prior
   evidence it still stands on.
4. Code (never the model) computes `belief_change = new_confidence×sign(new_direction) −
   old_confidence×sign(old_direction)`, exactly mirroring the existing `belief_change` contract already in
   the ledger schema (`belief_state.py`, 1.1.0 note, "BELIEF-CHANGE contract").
5. `provenance_mix` is a tally of the rows' `provenance` field (§4) that fed this update — printed, not
   decided by the model.

### 2c. Cost per cycle, estimated from the digest's own measured spend

Observed on a real run (`backend/data/optimus/digest/world_digest_<stamp>.json`, read directly): **$0.146
spent, 402 calls, 0 unpriced**, split `extract $0.116 / themes $0.013 / implications $0.014 / policy $0.003`.
Extraction dominates because it is one call per item; synthesis stages are cheap because they are O(themes),
not O(items) — themes ≤ `WORLD_DIGEST_MAX_THEMES=10` (config.py:4910), implications ≤ 8/theme.

A belief-table update is architecturally a **synthesis stage**, same shape as `themes` or `implications`: it
reads already-typed rows, not raw text, and is bounded by 16 topics rather than by item count. Using the
`themes`/`implications` stages ($0.013 and $0.014 for this run) as the comparable unit, batching the
topics-with-evidence into 1-3 calls of similar size puts a belief-table update at **roughly $0.01-0.02 per
cycle** — call it **+10-15% of the digest's current spend**.

A regime-forecast row (§3) is one more call of the same shape (reads the belief table + `tone()`'s already-
computed stats, line 920-997 — no new data fetch), similarly **~$0.01-0.02 per cycle**.

**Combined estimate: digest cost rises from the observed ~$0.146/cycle to roughly $0.18-0.20/cycle**, still
under half of `WORLD_DIGEST_BUDGET_USD=0.90` (config.py:4903) and the `Meter`'s own stage caps would refuse
before it could run away (`BudgetExceeded`, world_digest.py line 568-635). At `WORLD_DIGEST_EVERY_H=6`
(config.py:4992, 4 cycles/day): **~$0.72-0.80/day**, up from the observed ~$0.58/day (4 × $0.146). This is an
estimate, flagged as such — it should be read off the `Meter.summary()`'s new `by_stage_usd["world_state"]`
and `["regime"]` keys on the first real run, not trusted in advance (the project's own standing rule: a
headline number belongs in a receipt).

---

## 3. The regime-classification forecast row

### 3a. Fields (one row per **session**, not per 6h cycle — see 3c on why)

```json
{
  "specialist": "news_digest:regime_v0",
  "schema_version": "1.4.0",
  "observable": "regime_classification",
  "made_at": "2026-10-07T12:00:01Z",
  "session_as_of": "2026-10-07",
  "horizon_days": 1,
  "fields": {
    "growth": "up", "rates": "up", "liquidity": "tightening",
    "risk_appetite": "risk_on", "commodities": "up",
    "geopolitical_stress": "elevated", "sector_leadership": "semiconductors"
  },
  "confidence": {"growth": 0.55, "rates": 0.60, "...": "..."},
  "baseline_persistence": {"growth": "up", "...": "yesterday's label, copied"},
  "baseline_base_rate": {"growth": "up", "...": "unconditional mode over trailing 252 sessions"},
  "grading_plan": {
    "growth": "SPY total return sign, h1 and h5",
    "rates": "TLT total return sign (inverse), h1 and h5",
    "liquidity": "HYG-IEF spread change, h1 and h5",
    "risk_appetite": "IWM/SPY relative return, h1 and h5",
    "commodities": "USO/GLD basket return, h1 and h5",
    "geopolitical_stress": "VIX level change, h1 and h5",
    "sector_leadership": "which sector SPDR/ETF (XLK/XLE/XLF/.../SMH/XBI) has the top h5 return"
  },
  "mechanism_id": "news_digest_regime_v0",
  "licence": "PRODUCT_EXPERIMENT"
}
```

Horizons: **next-session (h=1)** and **next-week (h=5)**, exactly the pair the digest already uses elsewhere
(`WORLD_DIGEST_HORIZONS = (1,5,20)`, config.py:4916 — reuse 1 and 5, drop 20 for a macro call since nothing
macro is claimed to resolve in a month cleanly). Every field is graded against an instrument the data
pipeline **already pulls**: the full sector-ETF/macro-proxy panel (`WORLD_DIGEST_SUBJECT_PROXIES`,
config.py:4928-4959; `FORECAST_PROXY_ETFS`, config.py:4972) plus VIX, which the reader already ingests
(`^VIX`, `config.py:341`). No new data source.

### 3b. Grading rule

Reuse `world_digest.grade()` / `trust_from()` unchanged in shape, with a **third observable key**
(`"regime"` beside the existing `"size"` and `"direction"`, world_digest.py line 1329). For each field,
compute a **multiclass Brier** (or, for the binary fields, the existing 2-class Brier) of the model's stated
probability vs. **two baselines, not one** — the project's standing rule is that a null owes two tests
(`project_canon_standing_rules.md`): `baseline_persistence` (today's regime repeats — the cheap null every
regime-switching literature has to beat) and `baseline_base_rate` (the unconditional frequency over a
trailing window — catches a model that is "sticky" in a way that just matches long-run frequencies). The
model earns trust only if it beats **both**, graded and shrunk exactly as `trust_from()` already does
(prior N(0, TAU²), `WORLD_DIGEST_TRUST_MIN_DATES=3` graded date-blocks before trust leaves 0).

### 3c. Baseline, and why the row is per-session not per-cycle

Persistence and base-rate are computed from the **same forecast ledger**, not invented: `baseline_persistence`
is literally yesterday's `fields` dict copied forward; `baseline_base_rate` is the trailing-252-session mode
of each field, derivable once ~a year of rows exists (bootstrap period: until then, report `baseline_base_rate:
null, note: "insufficient history"` rather than fabricate one — the "a gate that cannot go green is a broken
gate" rule, inverted: a baseline that cannot be computed must say so, not silently default to 50%).

**One row per session, not per 6h cycle, by design.** Four cycles/day write to the *same* session's outcome
(SPY's h=1 return for 2026-10-07 is one number, however many times a digest ran that day). Writing 4 forecast
rows per session and grading all 4 would be the exact pseudo-replication the project's own CLAUDE.md flags
("n_effective counts DATE BLOCKS", standing rule) and that `implication_records` already guards against at the
ticker level ("one (day, ticker, observable, horizon, direction) is written once per day PER SUB-TAG", line
1206). The regime row inherits the identical guard: **the cycle closest to the prior session's close is the
one written and graded**; later same-day cycles may update the belief table (§2) but do not re-mint a regime
row. This is a one-line addition to `existing_keys()` (line 1290), not new design.

### 3d. MDE given one graded row per session

With the pseudo-replication fixed (3c), the series is genuinely one observation per session — the same rate
`news_digest:` size/direction rows already graded at. `trust_from()`'s own math (world_digest.py line
1332-1354) gives the answer directly: with `n` graded sessions, `se = sd(d_t)/sqrt(n)`, and detecting a true
per-session Brier improvement of `d` needs roughly `n ≳ (2.8 × sd/d)²` for 80% power at 5% two-sided (the same
`2.8·sd/√n` convention already used for `mde_bps` in the decision-story grader,
`docs/research_notes/2026-10-06/decision_story_and_regret_2026-10-06.md`, the h5 table). For a binary Brier
with `sd ≈ 0.25` (coin-flip variance) and a `d` of 0.02 (a 2-point Brier improvement — roughly the gap the
`shadow_decision` trust ceiling implies is "fully trusted", `WORLD_DIGEST_TRUST_FULL=0.02`): **n ≳ (2.8 ×
0.25/0.02)² ≈ 1,225 sessions** — about five years, at one row per day. This is the honest number, not a
hopeful one: a 7-field macro classifier with noisy binary outcomes needs a very long clock to clear a 2-point
Brier bar at conventional power. Two things soften it without pretending otherwise:
- `WORLD_DIGEST_TRUST_MIN_DATES=3` already caps the downside: trust is 0 for the first 3 sessions regardless,
  so nothing acts on noise meanwhile.
- The fields are not equally hard: `sector_leadership` (a 12-way categorical with real cross-sectional
  dispersion, unlike `rates` which asks one macro ETF to show meaningful serial structure) plausibly clears
  the bar on fewer sessions because its base-rate baseline is weaker (1/12 ≈ 8% vs. persistence's typically
  higher hit rate on sticky macro regimes) — the MDE should be computed **per field**, not as one number,
  echoing the project's "print by year" / "read the worst cell" discipline.

---

## 4. Provenance fields (FACT / COMPANY_CLAIM / INTERPRETATION / FORECAST)

Add one enum field, validated the same way every other digest enum is validated (`type_row`'s pattern: reject
silently to a safe default, never trust the model's self-report blindly where code can check it):

```python
PROVENANCE = ("FACT", "COMPANY_CLAIM", "INTERPRETATION", "FORECAST")
```

Placement, reusing structures that already exist rather than adding a fifth object:

| field | where it lives today | provenance rule |
|---|---|---|
| a reported number (revenue, EPS, a regulator's filed statistic) | `type_row.summary`/`event_type` (world_digest.py line 523-543); `thesis_card.web_event_row` when sourced from `sec`/`company_ir` (thesis_card.py line 1465-1489) | `FACT` whenever `source_type ∈ {sec, company_ir}` **and** the claim is retrospective (a filed, dated number); code-derivable from existing `confidence_source`, not the model's say-so |
| management's own forward words ("demand remains strong") | `type_row.mgmt_confidence` (line 539); `thesis_card` rows where `confidence_source == DIRECT_COMPANY_STATEMENT` and the text is forward-looking (`vocab_type` already distinguishes `guidance_change` from `earnings_report`, line 1339-1340) | `COMPANY_CLAIM` — authoritative about what was said, not about what will happen |
| Aegis's own read of the evidence | `type_implication.chain`/`contradiction` (line 1127-1136, already required fields) — this **already is** the interpretation layer, it just has no enum tag | `INTERPRETATION`, tagged on the implication object itself |
| a stated, falsifiable, resolvable probability | `implication_records`'s written ledger rows (`probability`, `threshold`, `resolves_after`) | `FORECAST` — the only kind of field `belief_state.resolve_one` (belief_state.py line 774) ever grades |

The enum is **computed in code** from fields that already exist (`source_type`, `event_type`/`vocab_type`,
whether the row carries a `probability`+`resolves_after`), not asked of the model as a fifth free-text field —
consistent with the digest's own stated design ("whether a ticker was MENTIONED is computed from the rows,
never taken from the model", line 53-55). This directly replaces the ad hoc "truth lane" language in the
roadmap (§3 row 34) with a field that is derivable, testable, and already has three of its four source
structures built.

---

## 5. The scenario object, probability sourcing, and labelled-only use

### 5a. Schema — distinct from `belief_state.ScenarioLeg` (per-ticker, belief_state.py line 166-177), because
this is a **macro/thematic** object, not a per-security payoff tree:

```json
{
  "scenario_id": "ai_capex_supercycle_2027",
  "schema": "macro_scenario/v1",
  "horizon_year": 2027,
  "name": "AI infrastructure buildout continues through 2027",
  "assumptions": ["hyperscaler capex grows >=20%/yr through 2027", "no major demand air-pocket"],
  "prior_probability": 0.40,
  "current_probability": 0.40,
  "probability_source": "DECLARED_PRIOR",
  "drivers": ["hyperscaler capex guidance", "grid interconnect queue length", "HBM supply"],
  "leading_indicators": ["semiconductor_capex belief direction", "grid_power_demand belief direction"],
  "falsifiers": ["two consecutive quarters of hyperscaler capex guidance cuts >=15%",
                 "a grid-interconnect moratorium in >=2 major US regions"],
  "beneficiary_sectors": ["semiconductors", "utilities_power", "industrials"],
  "loser_sectors": ["none named; a slowdown scenario is the paired loser case"],
  "causal_chain": "AI demand -> hyperscaler capex -> semiconductor + power + cooling orders",
  "evidence_ids": ["world_state belief ids this scenario reads"],
  "last_updated": "2026-10-07",
  "update_log": [{"date": "2026-10-07", "from": 0.40, "to": 0.40, "why": "no falsifier or confirming evidence this cycle"}]
}
```

5-10 named scenarios total (the outside guide's §21 option B, "probability-weighted scenario graph" —
explicitly **not** option A's single narrative future or option C's agent-based simulation, both rejected by
the guide itself as either unfalsifiable or too costly).

### 5b. Where probabilities come from

- **`MARKET_IMPLIED`**: where a real, liquid prediction market prices the same or a closely related question
  (e.g., a Polymarket/Kalshi contract on a rate-cut count, an election, a named macro threshold) — read
  **read-only**, through OpenClaw's existing browsing path (C7), never traded, never paid for. This is the
  `prediction_market_state` belief-table topic (§2a) feeding scenario probability directly when a match
  exists; `probability_source: "MARKET_IMPLIED"` and the market's own URL are carried on the row.
- **`DECLARED_PRIOR`** otherwise: a number Fable or the owner states explicitly, flagged as declared (never
  "learned"), consistent with the project's evidence-label discipline (`OBSERVED` → `EARLY_EVIDENCE` → ... —
  roadmap §7). A `DECLARED_PRIOR` is **not** silently relabelled; it only updates via the `update_log`, each
  entry naming the evidence (a belief-table entry crossing a stated falsifier or driver threshold) that moved
  it — code-checked the same way `belief_change` is code-computed, never the model editing its own prior
  freely.

### 5c. Labelled-only use in the Opportunity Explorer (C4)

Scenario probability is a **tag**, never a weight: `scenario_tags: ["ai_capex_supercycle_2027 (40%,
DECLARED_PRIOR)"]` shown on a name's card in the Explorer, exactly the way `C4`'s column order already
separates direction from magnitude (roadmap §3 row 54) — a scenario label is a *third*, clearly separate
column, not blended into either. A guard enforces this the same way `portfolio_farm.Policy` refuses a zero
cost rate unless explicitly flagged (CLAUDE.md DO NOT list): any caller that reads `scenario.current_probability`
from a sizing or ranking path (not a display path) should raise, with a test pinning it
(`test_scenario_label_only`, §7 below) — because a 2027 scenario is explicitly "not a deterministic future and
never as capital" (roadmap §2 item 23).

---

## 6. The news → decision connection, and the trust rule

**The minimal connection is already built and already graded — it needs a live session, not new code, to
start accruing**: `decision_story.freeze_plan`'s `plan_plus_shadow_news` alternative (decision_story.py line
650-661) and `regret_ledger`'s `mdc_news_tilt` (regret_ledger.py line 413-434, F7) compute, every session, what
the SHADOW_NEWS_v0 tilt would have been worth **if** it had been applied to the real plan. That is the
"connection that is graded" the owner asked for (ask E): it exists, is PIT-correct (reads the shadow ledger
read-only, line 135 of the research note), and costs $0 extra — it is waiting on `u_plan` restarting
(`docs/research_notes/2026-10-06/...`, "No live story exists yet").

**What is still missing is the flip from *measured counterfactual* to *actually sized*.** `shadow_decision()`
(world_digest.py line 1426-1446) is already written as a pure, idempotent function that returns its input
**unchanged** when both trusts are 0 — so wiring it into `u_plan`'s real post-gate weight, behind a config
flag defaulted `False`, is provably a no-op today and only changes behaviour once trust leaves 0. This is the
cheapest possible "wire it in" because the function was already built not to need a separate dry-run mode.

**The rule for trust to grow, stated precisely (nothing new — already in code):**
`world_digest.trust_from()` (line 1332-1354): trust is **exactly 0** while `n_dates <
WORLD_DIGEST_TRUST_MIN_DATES (=3)`; once ≥3 graded dates exist, trust = `clip(posterior_mean / 0.02, 0, 0.25)`
where `posterior_mean` is the per-date Brier improvement shrunk under a `N(0, 0.01²)` prior. The roadmap's
"SHADOW_NEWS trust may leave 0 ~10-11" (§1) is this clock: the digest has been writing graded rows since
2026-09-29, and 3 distinct graded dates land around 10-11 given the `news_digest:` rows' own `resolves_after`
schedule (the sample row read in §1 resolves 2026-10-09 at h=5).

**The two-key rule for flipping `FLEET_MANAGER_NEWS_TILT_LIVE` (proposed, owner-gated, not automatic):**
require **both** signals to agree before the flag may be set True — one null is not enough (the project's own
"a null owes two tests" rule, applied here to *enabling* rather than *rejecting*):
1. `world_digest.trust_from()`'s own trust (`trust_dir` or `trust_size`) > 0 — the shadow contract's internal
   measure that the tilt beats its own control.
2. `mdc_news_tilt`'s sign is **positive** over its own graded sessions (regret_ledger.py) — the *real plan's*
   measure that adding the tilt would have helped, net of costs, on the actual book.

Both are read from receipts that already exist or will exist the moment `u_plan` runs; no new statistics are
needed, only a guard that reads both and refuses to report "ready" until both agree, printed in a receipt
(`fleet_manager/news_tilt_flag_state.json`, §7). The flip itself stays an **owner decision** (the roadmap's
own table, §6, D-numbered rows) — never automatic, consistent with "an LLM proposes; deterministic code sizes,
stops and exits" and the project's standing refusal of unattended capital-affecting changes.

---

## 7. Build order for Opus — 3 chunks, acceptance tests, receipts

**B1 — World state + provenance fields.** (No dependency; can start immediately.)
- Add `provenance` enum (§4) computed in `type_row`/`type_implication`/`implication_records` — a derivation,
  not a new model-asked field, so it costs $0 extra.
- Add `world_state.py` (or a new section of `world_digest.py`): one batched synthesis call per cycle over the
  topics-with-evidence, decay + `belief_change` computed in code (§2b).
- **Receipt:** `backend/data/optimus/digest/world_state_<stamp>.json`, schema `world_state/v1`.
- **Acceptance tests:**
  - `test_world_state_provenance_enum`: every typed row and implication in a fixture digest carries a
    `provenance` value in `PROVENANCE`; an invalid/missing model value falls back to a derived default, never
    raises.
  - `test_world_state_unknown_not_fabricated`: a topic with zero matching rows this cycle is absent from
    `beliefs` and present in `unresolved_beliefs` — never silently carries a stale number without saying so.
  - `test_world_state_cost_printed`: `Meter.summary()["by_stage_usd"]` carries a `"world_state"` key after a
    real run; the run REFUSES (not silently overspends) past a stage cap, same `BudgetExceeded` contract
    already tested for `extract`/`themes`/`implications`.

**B2 — Regime forecast row + grading.** (Depends on B1's belief table as its input; independent of B3.)
- Add `regime_forecast()`: one call per cycle using the belief table (not raw text), written once per
  **session** (§3c dedupe, reusing the `existing_keys()` pattern) as `specialist: "news_digest:regime_v0"`.
- Extend `grade()`/`trust_from()` with a third observable key (`"regime"`), graded against **both**
  `baseline_persistence` and `baseline_base_rate` (§3b).
- **Receipt:** `backend/data/optimus/digest/regime_grade_<date>.json` — Brier(model) vs. both baselines, per
  field, `n_dates`, `trust`, and the **per-field MDE** (§3d), never one aggregate MDE.
- **Acceptance tests:**
  - `test_regime_one_row_per_session`: four digest cycles on the same session write exactly one
    `news_digest:regime_v0` row (the pseudo-replication guard, mirroring the existing per-ticker dedupe test
    for `implication_records`).
  - `test_regime_baseline_two_nulls`: both `baseline_persistence` and `baseline_base_rate` are present and
    independently computed; `baseline_base_rate` is `null` with a stated reason before ~252 sessions of
    history exist, never a fabricated 50/50.
  - `test_regime_trust_floor`: trust is exactly 0 for `n_dates < WORLD_DIGEST_TRUST_MIN_DATES`, identical
    contract to the existing size/direction trust test.

**B3 — Scenario objects + the dormant news-tilt wire.** (Depends on B1's belief table for `evidence_ids`;
independent of B2.)
- Add the `macro_scenario/v1` object (§5a), 5-10 seeded scenarios, `probability_source` honestly tagged.
- Wire `world_digest.shadow_decision()` into `u_plan`'s real post-gate weight, behind
  `FLEET_MANAGER_NEWS_TILT_LIVE = False` (new config flag, default False — the OWNER DECISIONS table pattern).
- **Receipts:** `scenarios/scenarios.json`; `fleet_manager/news_tilt_flag_state.json` (flag value, both trust
  numbers, `mdc_news_tilt`'s current sign and `n_sessions`, and whether the two-key rule (§6) is currently
  satisfied — printed even when the flag is False, so a reader can see "how close").
- **Acceptance tests:**
  - `test_news_tilt_noop_while_untrusted`: `u_plan`'s weights are **byte-identical** with the flag True vs.
    False while both trusts are 0 (proves the wire is inert today, same style as the existing PIT
    byte-identical test noted in the 10-06 research note for frozen alternatives).
  - `test_scenario_label_only`: a sizing/ranking code path that reads `scenario.current_probability` raises
    `ScenarioNotForSizing` (new guard) with a test exercising it; a *display* path (Explorer) reads it freely.
  - `test_flag_requires_two_keys`: an attempt to set `FLEET_MANAGER_NEWS_TILT_LIVE=True` through the setter
    (not the raw config edit, which stays owner-only by file) refuses when either of the two §6 keys is not
    yet satisfied, and the refusal reason names which key is missing.

All three chunks follow the roadmap's own process (§8 of the roadmap): a second-Opus adversarial review before
merge, one full-suite run, commit on exit 0, `ci_watch --wait`.

---

## 8. What must wait for 10-09 grades, and why

- **B1's belief table has no grade of its own** — a belief is a *running state*, not a falsifiable claim, so
  there is nothing to wait for; it can ship and run immediately. Its only dependency on later dates is
  qualitative: its `causal_edges` are hypotheses the macro_lead_lag hyp_lab cells (`scripts/hyp_lab.py`,
  `macro_readthrough_*` families, e.g. line 72-84) are *already* pre-registered to test independently — the
  belief table should **read**, never **write**, those cells' verdicts.
- **B2's regime-row grading is measurement plumbing until real grades exist.** The first `news_digest:`
  forecast rows (already accruing since 2026-09-29) grade at h=5 starting **2026-10-09** (roadmap §1, "digest
  5-session grades 10-09"). Nothing about B2's Brier numbers should be read as a finding before then — the
  chunk ships and starts accruing, but its first receipt will correctly show `n_dates: 0-2` and `trust: 0`,
  which is the expected, honest state, not a defect.
- **B3's live-tilt flip waits on both §6 keys, which in turn wait on ≥3 graded shadow-news dates (~10-11,
  roadmap §1) and on `mdc_news_tilt` accruing sessions after `u_plan` restarts.** The roadmap's own "Later"
  section already defers "regime-classification forecast rows from the digest (after 10-09 grades)" and "the
  world graph... until the digest has graded rows (10-09) to attach to" (§5 of the roadmap) — this note's B2
  and the belief-table-to-scenario linkage in B3 are exactly those two deferred items, now specified concretely
  enough to build once their gate date passes. Building them now and letting the acceptance tests pass on
  `n=0` graded rows is correct; **reporting their Brier numbers as a result before 10-09 (B2) or before the
  two-key rule is satisfied (B3) would be the same mistake CLAUDE.md's §11 lesson describes** — a number is
  not evidence until its sample is examined, and an n of 0-2 date-blocks is not a sample yet.

---

## Report back (for the caller)

**Three chunks for Opus:**
1. **B1** — world-state belief table (16 topics, decay, `belief_change`) + `provenance` enum (FACT /
   COMPANY_CLAIM / INTERPRETATION / FORECAST), computed in code from fields that already exist. No gate;
   start now.
2. **B2** — regime-classification forecast row (growth/rates/liquidity/risk_appetite/commodities/geopolitical
   stress/sector_leadership), one per session (not per cycle — dedupe guard), graded against **two** baselines
   (persistence + base rate) via the existing `trust_from()` machinery. No gate to *build*; its *grades* are
   not readable as a finding before 2026-10-09.
3. **B3** — scenario objects (5-10, `DECLARED_PRIOR` or `MARKET_IMPLIED`, labelled-only in the Explorer, a
   guard against sizing on them) + wiring `shadow_decision()` into `u_plan` behind a flag that is provably a
   no-op today and requires a two-key rule (world_digest's own trust AND `mdc_news_tilt`'s sign) before the
   owner may flip it live.

**Cost per digest cycle:** observed **$0.146/cycle** today (4 cycles/day, `WORLD_DIGEST_EVERY_H=6`); B1+B2
add an estimated **$0.03-0.05/cycle** (two more synthesis-scale calls, sized off the existing `themes`
$0.013 and `implications` $0.014 stages), for an estimated **$0.18-0.20/cycle (~$0.72-0.80/day)** — well
under the $0.90/cycle budget cap, and the `Meter`'s stage caps refuse before any run could overspend it. This
is an estimate to be replaced by the first real `by_stage_usd["world_state"]` / `["regime"]` reading, not a
promise.
