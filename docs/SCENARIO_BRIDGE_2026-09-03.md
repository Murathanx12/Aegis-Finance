# SCENARIO BRIDGE — the LLM proposes, code retrieves, reality grades

**Date:** 2026-09-03 · **Licence:** `PRODUCT_EXPERIMENT` · **Status:** built, run, graded
**Receipt:** `backend/data/optimus/tracker_backtest/scenario_bridge_20260903.json`
**Code:** `scripts/scenario_bridge.py`, `scripts/scenario_bridge_grade.py`
**Data:** `backend/data/optimus/scenario_bridge/{schema.json, scenarios_20260903.jsonl}`
**Test:** `backend/tests/test_scenario_bridge.py` (22 tests, offline, no network)

---

## RESULTS SCOREBOARD

| line | value |
|---|---|
| scenarios generated / valid | **20 / 20** (DeepSeek `deepseek-chat`) |
| graded against real outcomes | **18 of 20** · 1 refused too thin · 1 had no observable state |
| retrieval fields mapping **DIRECTLY** | **5 of 15 (33%)**; +2 proxy, +1 coarse, **7 unmappable (47%)** |
| best matched-vs-control spread at the declared horizon | **+2.02% net over 6m, t 2.08, 130 month blocks** (SB-07) |
| cross-model agreement on the fields retrieval RUNS ON | **0.225** |
| cross-model agreement on everything else | **0.531** |
| LLM spend | **$0.003768 priced** + 11 free-tier NVIDIA calls (cap was $0.50) |
| **RESULT IMPROVEMENT** | **NONE to the book.** No new selector, no paper lane, no order. What moved is the *measurement of how far an LLM scenario can travel*, and it is shorter than expected. |

---

## What was built

An LLM invents a **structured causal scenario** — a chain from a real-world
change to a change in returns, written entirely as observable state. Code then
finds the **real 2013–2024 company-months** whose observable state matched,
builds **matched controls** (same month × sector × size tercile × liquidity
tercile, minus the scenario's distinguishing configuration), and grades both
with the **value-weighted excess returns that actually happened**, paired by
month block.

Three properties are enforced in code, not intention:

1. **The LLM never labels its own hypothesis correct.** The model's `direction`
   touches exactly one thing — the *sign* of a number computed from realised
   returns. `test_direction_only_flips_a_sign_it_never_creates_one` pins that it
   cannot change the magnitude.
2. **A synthetic scenario never gets a synthetic return.** No code path attaches
   an outcome to anything but a real `(permno, month)`.
   `test_no_outcome_without_a_real_row` runs the full pipeline over a panel of
   all-NaN targets and proves the grade comes back with *no number*, not a zero.
   An invented return here would inject fiction straight into the alpha target,
   which is the one failure downstream cannot undo.
3. **No number appears in the prompt.** The vocabulary is ordinal words —
   `deep_drawdown`, `neglected`, `targets_cut` — and every quantile that turns a
   word into a filter lives in `_BANDS`, which the model never sees. This is the
   2026-08-30 lesson: *a bound the model can see is an anchor* (eleven of
   thirteen answers came back at exactly the stated bound).
   `test_schema_carries_no_number_the_model_could_see` pins it.

The panel is the learner's PIT training table (441,278 rows, 144 months, 5,713
names, 2013-01 → 2024-12), read-only, plus a 13F holder-event aggregate joined
at the **statutory 45-day filing deadline** (96.6% coverage).

---

## FINDING 1 — the models agree on the story and disagree on the state

Two different models (DeepSeek `deepseek-chat` and NVIDIA NIM
`openai/gpt-oss-20b`) were given the **same seed** and asked for the same
schema. Agreement, 8 paired scenarios, 104 field comparisons:

| field | agreement | is it a retrieval predicate? |
|---|---|---|
| `event_type` | **0.88** | no |
| `company_role` | **0.88** | no (UNMAPPABLE) |
| `sic_division_hint` | **0.88** | stratum only (COARSE) |
| `direction` | 0.75 | grading control |
| `capacity_constraint` | 0.50 | no (UNMAPPABLE) |
| `attention_state` | 0.38 | **YES** |
| `price_state.momentum_12_1_sign` | 0.38 | **YES** |
| `demand_change` | 0.25 | no (UNMAPPABLE) |
| `holder_action` | 0.25 | **YES** |
| `expected_horizon_months` | 0.12 | grading control |
| `price_state.drawdown_state` | 0.12 | **YES** |
| `analyst_change` | **0.00** | **YES** |
| `supply_change` | **0.00** | no (UNMAPPABLE) |

> **The five fields the retrieval actually runs on agree 0.225 of the time.
> Everything else agrees 0.531. The models converge on WHAT HAPPENED and diverge
> on WHERE THE COMPANY WAS STANDING WHEN IT HAPPENED.**

That is a first-order caveat on the whole method, and it is the most valuable
thing this run produced. It means the analogue set a scenario retrieves — and
therefore every spread in the receipt — is **substantially an artefact of which
model was asked**. Not a reason to abandon the bridge; a reason that the next
version must ask N models and retrieve on the **intersection** of the states
they agree on, treating a disputed state as `unknown` rather than as a filter.

Agreement is *not* correctness. Two models agreeing that demand rose says the
concept is easy to guess, not that demand rose. Only the panel grades.

---

## FINDING 2 — two opposite trades, one identical retrieval

Twenty causally distinct stories collapsed to **18 distinct observable
configurations**. One collapse is instructive:

| | SB-00 | SB-10 |
|---|---|---|
| story | jet-engine casting bottleneck: orders outrun capacity, the bottleneck holder gains pricing power | tariff-deadline pull-forward: a temporary order boom inflates earnings, then orders collapse |
| `direction` | **long** | **short** |
| retrieved rows | 5,870 | **5,870 — the same rows** |
| matched month blocks | 136 | 136 |
| net spread at 6m | **+0.43%** | **−1.43%** |
| paired t | **+2.00** | **−2.00** |

The two scenarios are causally opposite and **observably identical**: both are
Manufacturing, mild pullback, positive 12-1 momentum, elevated attention,
targets raised. Reality graded the configuration at +0.93% gross over six
months, so the bottleneck long is (weakly) supported and the pull-forward short
is refuted **at exactly the same t**, and neither the LLM nor this panel can
tell the two stories apart from what is observable at entry.

This is the Micron test in miniature: *explaining a winner afterwards is
trivial; the research problem is a precursor observable beforehand.* Two
mechanisms with opposite predictions and the same precursor are not two
hypotheses — they are one, until a field arrives that separates them. Which
brings us to:

---

## FINDING 3 — the unmappable list, which IS the acquisition queue

Seven of fifteen retrieval fields (47%) have nothing in this panel to map onto.
All seven were used by **all 20** scenarios:

| concept | why it does not map | what would map it |
|---|---|---|
| `demand_change` | no revenue/unit fundamentals joined | **Compustat `fundq` ↔ permno link** (the parquet is already on disk at `wrds/bulk/comp__*`; the CCM link is not built) |
| `supply_change` | no industry capacity/utilisation series | Fed G.17 industrial capacity utilisation by NAICS; ISM supplier deliveries |
| `capacity_constraint` | no utilisation, backlog or lead-time data | Compustat backlog; lead-time surveys |
| `company_role` (supplier/customer/substitute) | **no customer–supplier edges** | FactSet Revere / Bloomberg SPLC, or 10-K Item 1 major-customer extraction |
| `actors` | no entity graph linking a named actor to a permno | an entity resolver over filings + news |
| `event_type` | **no dated event tape covers 2013–2024 here** | EDGAR 8-K item codes (free, and the collector shape already exists) |
| `sector_theme` | SIC division is 10 buckets; a *theme* does not survive | GICS sub-industry, or a text-embedding sector |

Ranked by cheapness × leverage the queue is:
**(1) EDGAR 8-K item codes** — free, dated, gives `event_type` a real column and
would let a scenario condition on *an event actually having happened*;
**(2) the Compustat↔permno CCM link** — the data is already local, and it turns
`demand_change` from prose into a filter;
**(3) supply-chain edges** — the only thing that would have separated SB-00 from
SB-10, and the most expensive.

Two proxies are also declared rather than hidden: `attention_state` is standing
in as *analyst coverage percentile* (no news counts, no search volume, no filing
counts exist before 2026-08-30), and `holder_action` covers accumulation and
distribution only — **`activist_stake`, `insider_buying` and `insider_selling`
are refused, not faked**, because 13D/G and Form 4 are not in the panel.

---

## The three strongest matched-vs-control spreads, with honest n

All are at each scenario's **own declared horizon**, gross and net of a
**50 bps** charge (25 bps round trip × 2 legs — a treated-minus-control spread
is a two-legged position if it is ever traded), paired by month block, with
`n_effective` counting **date blocks, not rows**.

| rank | id | h | dir | gross | **net** | **t** | month blocks | treated rows | control rows | months positive |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | SB-07 | 6m | short | +2.52% | **+2.02%** | **2.08** | 130 | 1,841 | 64,810 | 66.2% |
| 2 | SB-00 | 6m | long | +0.93% | **+0.43%** | **2.00** | 136 | 5,618 | 68,416 | 55.1% |
| 3 | SB-06 | 12m | short | +5.76% | **+5.26%** | **1.74** | 100 | 453 | 15,211 | 55.0% |

- **SB-07** — *"a new technology standard makes the incumbent's installed base
  non-compliant; customers defer replacement parts and service."* Retrieved as:
  Manufacturing, deep drawdown, negative 12-1, elevated attention, downgrades,
  institutional distribution. Shorting that configuration earned +2.02% net over
  six months in 66% of 130 months.
- **SB-00** — the bottleneck long above. Note it is **the same rows as SB-10's
  short**, so it is one result reported twice with opposite signs, not two.
- **SB-06** — *"a bank tightens underwriting; developers cancel projects; a
  property-services firm loses fee income."* The largest spread and the thinnest
  cell (453 treated rows over 100 months).

**Read these as a queue, not a verdict.** Twenty scenarios are twenty looks at
one panel, there is no multiplicity control here and there is not supposed to be
one under `PRODUCT_EXPERIMENT`. Under BH-FDR across 18 graded scenarios a t of
2.08 does not survive. What these rows license is *pre-registration of SB-07's
configuration as its own `PRODUCT_EXPERIMENT` book*, which is where the house
rule says a new mechanism arrives — never as a weight in `arena_composite`.

Every graded scenario also carries a **matched-loser** block: inside the treated
cell, the bottom outcome quartile against the top, with the feature gap between
them. For SB-00 the winners' only visible separation from the losers is
`holder_net__xs` +0.043 and `mom_12_1` +0.046 — descriptive, in-sample, and
where to look next, not a signal.

---

## Two defects found and fixed during the run

**The evidence floor was checked on the wrong quantity.** The first live run
ranked SB-18 third on a t of 1.78 — computed from **six month blocks and six
treated rows**. The floor (100 treated rows, 24 month blocks) had been applied
to the *retrieved* set (233 rows, 120 months); only six strata ever held enough
controls to form a difference. A check that did not run on the quantity being
reported is not a check that passed. The floor now binds on the **matched** set,
SB-18 is correctly `REFUSED_TOO_THIN`, and
`test_the_floor_binds_on_the_matched_set_not_the_retrieved_one` pins it.

**A sector label that means "we don't know".**
`tracker_ibes_backtest.SIC_DIVISIONS` sends SIC 9000–9999 to *"Public
Administration"*. In CRSP that range is **98.8% code 9999 = NONCLASSIFIABLE
ESTABLISHMENTS** (3,580 of 3,625 name-rows), so the panel's second-largest
"sector" — **99,334 of 441,278 rows, 22.5%** — is a label for absence of
information. The bridge renames it `_UNCLASSIFIED_SIC9999`, never lets a
scenario map *onto* it, and still uses it as a matching stratum (unknowns
compared with unknowns). **Anything else in the repo that groups by this
`sector` column is silently treating a fifth of the market as one industry.**

---

## What this does NOT license

- No order, no lane, no book. Nothing here touched paper or capital.
- No `RESEARCH_CLAIM`. Full preregistration, MDE, multiplicity control and a
  holdout would all be required first, and none of them was run.
- No claim that LLM scenarios "work". The measured result is that **an LLM
  scenario survives the trip to a filter about a third of the way** (5 of 15
  fields direct), and that **the third it survives on is the third two models
  disagree about most** (0.225 vs 0.531).

## Reproduce

```bash
python -m scripts.scenario_bridge --write-schema
python -m scripts.scenario_bridge --generate 20 --second-opinion 10   # ~$0.004
python -m scripts.scenario_bridge_grade
python -m pytest backend/tests/test_scenario_bridge.py -q             # 22, offline
```
