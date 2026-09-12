# TRIAL-DRAFT-L2 — typed-event extraction as an E1 feature (`typed-events-v1`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-13, before the first extraction
call. It is not in `rule_experiments` and has not incremented
`cumulative_trials`: registration is the attended step, and a draft that
registered itself would make the attended step decorative. Signing it starts the
clock.

**Licence:** `PRODUCT_EXPERIMENT`. Accrues zero capital, places nothing, sizes
nothing.

**Frozen before any call:** vocabulary hash
`b55fcff7ef3e206ffb14b088a832367b1471a59bddbb8d514c4a01fbfc1d2e6a`
(`backend/services/event_vocabulary.py`, 39 substantive ids + `no_event`),
prompt hash `3e535a4c6f30…` variant A and `8f537df85a1d…` variant B
(`backend/services/event_extraction.py`), and the input list:
6,020 eligible corpus rows at `inputs_sha256 0d27f00243d9…`
(`backend/data/optimus/night_factory_2026-09-13/L2_typed_events_run01_inputs.json`).

---

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
— verdict recorded in §8.

**Resurrects: nothing refuted, and one thing half-answered.** Chunk 9's E1 run
(`backend/data/optimus/night_factory_2026-09-13/E1_event_head_h5_run02.json`)
tested a **keyword proxy** over this same vocabulary and closed *the proxy*,
not typed events — its own `next_test` field says so in as many words: *"L2's
LLM extraction over the same cells, graded through this identical table,
splits, book and controls — the ONLY difference being how the events were
typed."* That is this trial.

**New instrument.** Not "we are trying again": the read is a different
instrument from the proxy in a way that is stated in advance and is
falsifiable. The proxy's `direction` is a cue-word vote over fixed regex
patterns; it types "Acme raises full-year guidance" and misses "we now see the
year landing at the low end", and it cannot represent a denial, a recap or a
hedge at all. L2's read is asked for all three explicitly (rules 6, 7 and 8 of
the frozen system prompt) and its adversarial rows 21-23 are exactly those
three cases. If the extraction is not a better instrument, the three
adversarial classes are where it will show.

---

## 1. Hypothesis

> On the E1 panel, the typed-event feature table built from **L2's extracted
> rows** produces a higher net decile long-short return and a higher
> control-adjusted rank IC, at 5 and 21 sessions, than the identical table
> built from the **keyword proxy** — and both must clear the same three
> controls (shuffled events, TF-IDF, no-text) that E1 already runs.

**Honest prior: WEAK, and the direction is not obvious.** The proxy already
fails to beat shuffled events on the chunk-9 panel. Two of the three reasons a
reading could beat a regex — denials and recaps — are *rare* in a corpus
dominated by routine wire copy, and the third (hedged language) shows up mostly
in the low-magnitude tail. An extraction that is better at reading and no
better at predicting is the modal outcome, and it is a result: it separates
"the text carries nothing at this horizon" from "a regex cannot see what the
text carries", which is the question chunk 9 left open.

**What this trial may NOT do.** A typed row is a FEATURE. It never sizes, never
ranks, never orders, and no allocation may read `direction` as a position.
Invariant 5 and X5: the LLM classifies into enums, the engine allocates. The
extraction's output is numeric by construction precisely so that nothing
downstream has to trust a sentence.

---

## 2. The inter-rater floor, and where it comes from

The extraction is graded as a MEASUREMENT before it is graded as a feature.
`scripts/night_l2_typed_events.py` re-prompts a sample with prompt variant B —
the same nine rules, different wording and order — and computes, per spec
§1.3-1.4:

| statistic | on | how |
|---|---|---|
| Cohen's kappa | `event_type` | unweighted, 40-way categorical |
| weighted kappa | `direction` | ordinal −1/0/+1, **linear** weights |
| weighted kappa | `magnitude_bucket` | ordinal over the 5 buckets, linear weights |
| mean absolute difference | `confidence` | continuous; kappa does not apply |

**The floor: κ ≥ 0.61 on `event_type`.** Source: Landis & Koch, "The
Measurement of Observer Agreement for Categorical Data", *Biometrics*
33(1):159-174 (1977), whose benchmark scale puts 0.61-0.80 at "substantial" and
0.41-0.60 at "moderate". Two things are stated with it rather than left
implicit:

1. **Landis and Koch call their own divisions arbitrary.** The paper offers the
   scale as a convention for discussion, not as a test. A floor taken from it
   is a declared convention, not a significance threshold, and this trial
   treats it as one.
2. **Kappa falls as the number of categories rises** for a fixed reader, and
   this vocabulary has 40 of them with deliberately adjacent pairs
   (`litigation_filed` / `litigation_settlement`,
   `management_change_departure` / `management_change_appointment`). So a
   `event_type` kappa below the floor is reported beside the **weighted**
   direction and magnitude kappas, where an adjacent-category disagreement is
   not scored as a total miss.

**What the floor gates.** Under `PRODUCT_EXPERIMENT` the typed rows may be used
as a feature at any kappa, with the number printed in every receipt that reads
them — a licence that blocked exploration on a measurement threshold would be
the gate-that-blocks-work failure this repo has already paid for. The floor
binds **promotion**: no `RESEARCH_CLAIM` about typed events may be made on an
extraction whose `event_type` kappa is below 0.61 on a sample of at least
`KAPPA_ROWS_SPEC = 500` rows. Below the floor the honest statement is "the
reader does not agree with itself about the label", and no downstream number
can repair that.

**Sample size.** The spec's control is 500 rows; the job's default first pass is
50 (`KAPPA_ROWS`) because 500 re-prompts is an extra hour the first night does
not have. A 50-row kappa is reported as a 50-row kappa. It does not satisfy the
promotion gate and the receipt says which n it was computed on.

---

## 3. Primary metric (the ONE deciding number)

**Net decile long-short return, typed arm minus proxy arm, on identical cells,
identical splits, identical embargo, identical book and identical costs** — the
only changed variable being how the events were typed. Computed by
`scripts/night_e1_event_head.py` with `event_source: typed_l2` and again with
`event_source: keyword_proxy`, at the 5-session horizon.

Everything else is REPORTED, never deciding: the 21-session horizon, the
control-adjusted rank IC, the per-type coverage table, the `no_event` share, the
refusal rates, the evidence-span verbatim rate, and both kappas.

**The family and its multiplicity.** This trial's family is
`E1_TYPED_EVENTS_2026_09` and its members are the arms E1 already runs:
`EVENT` (typed), `EVENT` (proxy), `TFIDF`, `SHUFFLE`, `NOTEXT`, at two
horizons. Screening inside the family is BH-FDR; **any export — a
`CAPITAL_CANDIDATE` promotion or a `RESEARCH_CLAIM` — re-runs the family's
primary metrics under Holm** (canon §63). A typed arm cannot be promoted by
reading its own number while four siblings were tested beside it.

### 3.1 Power, declared BEFORE the estimate (canon §64)

R13's declared fields, in the linter's own units, so the design's resolvability
is machine-checkable and not a paragraph:

- event_frequency_per_year: 2722
- declared_effect_size: 1.0pp
- outcome_dispersion: single_name
- outcome_horizon_days: 5
- dependence_unit: date block — one (symbol, entry_date) cell is NOT an independent observation; every name on one date shares that date's market move (canon §58)
- cross_sectional_rho: 0.2
- corpus_years: 1.09

`event_frequency_per_year` is the whole cross-section's rate — 2,967 proxy event
rows over 1.09 years — not the per-name rate, because R13 reduces it by the
cross-sectional dependence itself and declaring a per-name rate as well would
divide by 120 twice. `declared_effect_size` is the 5-session SPY-excess return
difference per typed event between the typed and proxy arms.
`outcome_dispersion` uses the `single_name` preset (12.0pp) rather than a number
of this trial's own, because the cross-sectional dispersion of a 5-session
single-name excess return is not something this panel measures better than the
preset does. `cross_sectional_rho: 0.2` is a DECLARED assumption about the
average pairwise correlation of same-date 5-session excess returns, not a
measurement — it is the number this trial is most likely to be wrong about, and
it is stated so the next reader can measure it and move the verdict.


All three numbers come from chunk 9's own E1 receipt,
`night_factory_2026-09-13/E1_event_head_h5_run01_smoke.json` (120-symbol smoke
panel, 2025-08-01 → 2026-09-01, 249 date blocks, 5,720 cells) — the proxy arm's
measured behaviour, not a guess. They are re-stated from the FULL panel's own
receipt at signing, and the full-panel numbers supersede these.

- **`declared_effect_size`: +0.020 mean rank IC per date block** (typed arm minus
  proxy arm), equivalently a difference large enough to move the EVENT−SHUFFLE
  gap from its measured −0.0076 to clearly positive. Smaller than that is not
  worth a reader's hours at 20 tok/s, and this trial does not claim it.
- **`event_frequency_per_year`: 22.7 typed events per name per year** — 2,967
  proxy event rows over 120 symbols and 1.09 years on the smoke panel; 1,894 of
  5,720 cells (33.1%) carry at least one. L2's own rate is unknown until the
  reader runs and will differ: the extraction emits `no_event` rows, which the
  proxy never does, so L2's *event* rate is bounded above by the proxy's row
  count only if its `no_event` share is reported beside it — and it is.
- **`outcome_dispersion`: per-date-block sd 0.2995 on rank IC** (from the
  receipt's own mean −0.033082 and t −1.743 at n = 249), and **0.1206 on the
  net decile spread** (mean −0.00863, t −0.447, n = 39 book dates).

**THE LINTER REFUSES THIS DESIGN, AND IT IS RIGHT.**
`python scripts/lint_prereg.py` returns **`UNPOWERED_AT_REGISTRATION`**:

```
R13: resolving a 1pp effect at dispersion 12pp needs 1130 independent
observations. At 2.72e+03 per year over 1 years the corpus can ever supply 55
(R13b: capped from 2967 -- your 2.72e+03 events/yr overlap 54.0x at a 5-day
horizon, where only 50.4 independent windows fit in a year). The smallest
effect this corpus could resolve is 4.5pp.
```

Read it in plain words: 2,967 typed events on a 13-month panel are **55
independent observations**, because a 5-session window can only fit 50.4
non-overlapping times in a year and every name on a date moves with the date.
The smallest per-event effect this era could ever resolve is **4.5pp** over five
sessions — an effect no reasonable person expects from changing *how the events
were typed*. Running the primary metric here would produce a `NOT_DETECTABLE`
that says nothing about typed events, and that null would then be quoted for
months as though it did.

The same arithmetic on the panel's own IC agrees: at 249 date blocks and the
receipt's per-block IC sd of 0.2995 (from its mean −0.033082 and t −1.743), the
80%-power MDE on rank IC is **0.053**, against the −0.0076 EVENT−SHUFFLE gap the
proxy actually produced.

**So this trial is registered as a SCREEN and nothing else** (canon §63: SCREEN =
BH-FDR, EXPORT = Holm). Under `PRODUCT_EXPERIMENT` it may run, it may report,
and it may inform what gets built next. It may NOT export a verdict about typed
events from this era, and §4's `CANNOT DETERMINE` row is the expected outcome
rather than the unlucky one.

**What would change the verdict**, computed with the same linter rather than
hoped for:

| change | n_available | smallest resolvable effect |
|---|---|---|
| today: 2025-26, 5 sessions | 55 | 4.5pp |
| the backfill reaches 2015 (10 years), 5 sessions | 504 | **1.5pp** |
| 2015 + the corpus's own 2015-01-01 start (11.7 years) | 590 | 1.4pp |
| 10 years at the 21-session horizon | 120 | 3.1pp |

The corpus already publishes from **2015-01-01** (the Alpaca backfill, anchored
on `published_utc`), so the ten-year row is not a wish: it is what this trial is
waiting for, and §7's gate 2 is where it is enforced. A second lever, untested
here, is `cross_sectional_rho` — declared at 0.2 and never measured. If the true
same-date correlation of 5-session excess returns is materially lower, the
effective cross-section is wider and the floor falls; measuring it is cheap and
is the single highest-value thing anyone could do to this design.

---

## 4. Decision rule

| outcome | condition | consequence |
|---|---|---|
| `PRODUCT_PROMISING` | typed arm beats **shuffled events** at the family's BH-FDR level AND beats the proxy arm on the primary metric | typed rows become E1's default feature source; the proxy stays as the named fallback |
| `FAILED_VARIANT` | typed arm does not beat shuffled events | *the extraction* is closed for E1 at these horizons. **Typed events are not closed** — the vocabulary, the prompt and the corpus each remain separately testable, and the receipt names which one the run could not distinguish |
| `CANNOT DETERMINE` | fewer than the MDE's required date blocks carry a typed event | say so, print the count, and do not read the point estimate |

**Minimum window.** The panel must carry at least **20 distinct date blocks**
with at least one typed event, and the MDE at that block count is printed
BEFORE the point estimate (canon §64: the power check comes before the
confirmation). A run that cannot state its MDE reports `CANNOT DETERMINE`.

**Contamination clause.** If any input row is found to have been typed against a
different `vocabulary_hash` or `prompt_hash` than the ones frozen above, every
row carrying that hash is excluded and the trial's window restarts from the
first row typed under the frozen pair. Both hashes are on every row for exactly
this reason.

**Crash override.** If SPY draws down ≥ 20% inside the evaluation window, the
decision defers to ≥ 6 months past the trough, as for every other trial.

---

## 5. Frozen parameters

Not tuned mid-trial, on pain of invalidating it:

- the 40-id vocabulary and every field of it (`VOCABULARY_HASH`);
- both system prompts, the user template and the JSON Schema (`PROMPT_HASH`,
  `PROMPT_HASH_B`);
- the refusal contract: language first, then parse, then schema; no repair and
  no retry; `no_event` is a successful row and is written;
- the PIT anchor — `native_stamp` → `published_utc`, else `first_seen_utc` —
  which is the E1 panel's own `_anchor`, imported and not re-derived;
- one row per document, scoped to the document's first ticker, no fan-out;
- E1's own frozen block: cells, splits, embargo, the decile book, the
  25 bps-per-side cost on realised turnover, and the three controls;
- `temperature = 0.0` and the `local_gguf` backend.

## 6. Hard constraints

- **Descriptive only.** Until this trial passes, nothing surfaces a typed row
  with buy/sell/hold framing, and no book reads `direction` as a position.
- **No LLM authority over capital**, ever, at any kappa.
- **Costs are never omitted.** The consuming arm charges E1's own cost rate; a
  zero-cost run is refused by `portfolio_farm.Policy` unless explicitly flagged
  a diagnostic.
- **No backfilled forward evidence.** A row typed after the fact may not be
  presented as having been available before it was typed; `typed_utc` is on
  every row.

## 7. Earliest read — GATES, not dates

Three gates, all of which must be green (roadmap: gates outrank dates):

1. **The reader answers.** L2's receipt today is `PENDING_MODEL`: 6,020 rows
   frozen, zero calls, because llama-server is down and the job does not start
   it. Nothing about this trial can be read until it is up.
2. **The corpus covers the panel.** The typed rows must land on the E1 panel's
   own `(symbol, entry_date)` cells. The Alpaca backfill publishes from
   2015-01-01 and is anchored on `published_utc`, so this gate is a coverage
   COUNT (§4's 20 date blocks), not a calendar date, and
   `learner.event_head.typed_events` reports it (`dropped_symbol_not_in_panel`,
   `dropped_date_after_panel`).
3. **The measurement is reported.** Both kappas and the four refusal rates are
   in the receipt before the primary metric is read.

The earliest READ is therefore the first E1 run whose receipt carries
`event_source: typed_l2` and ≥ 20 qualifying date blocks. The earliest
**promotion** read additionally requires the 500-row kappa.

## 8. Corpse-check verdict

`python scripts/lint_prereg.py docs/TRIALS/TRIAL-DRAFT-L2-typed-events-v1.md`,
run from `C:/Users/mrthn/Aegis module` on 2026-09-13, against 358 prior
experiments:

```
TRIAL-DRAFT-L2-typed-events-v1.md: UNPOWERED_AT_REGISTRATION  (vs 358 prior experiments)
  R13: resolving a 1pp effect at dispersion 12pp needs 1130 independent
  observations. At 2.72e+03 per year over 1 years the corpus can ever supply 55
  (R13b: capped from 2967 -- your 2.72e+03 events/yr overlap 54.0x at a 5-day
  horizon, where only 50.4 independent windows fit in a year).
  n_required 1130  n_available 55  smallest resolvable effect 4.5pp
  [near] 0.224 prereg REGISTERED PREREG_MMC_SECOND_SELECTOR
  [near] 0.211 prereg REGISTERED PREREG_REVISION_FORECASTER_1
  [near] 0.202 prereg REGISTERED PREREG_AEGIS_NET_TOURNAMENT_1
```

**No corpse and no duplicate** — the nearest prior experiment scores 0.224 on
wording, well below any match, and the linter's objection is about POWER, not
about the question having been answered. §3.1 records what the objection means
and what moves it.

**This draft is therefore not signable as a confirmatory trial today.** It is
signable as a SCREEN, which is what §3.1 registers it as. A future version that
runs on the 2015-2026 corpus, or that declares an effect at or above the floor
its own era can resolve, is the confirmatory successor — a different document
with a different inception, never an amendment to this one.

## 9. What this trial may NOT claim

- Not that typed events work **in general** — only on this panel, these two
  horizons, this era (2025-26 only; say so), this corpus, and this reader.
- Not that the vocabulary is right. A `FAILED_VARIANT` closes this
  implementation of extraction, not the 40 ids, not the prompt, and not the
  idea that a reading beats a regex.
- Not a skill claim of any kind: the 24-month floor governs claims and nothing
  here is 24 months old.
- Not anything about **DeepSeek**. This is a local `local_gguf` read; the paid
  provider is dormant for this lane and is not an arm of this trial.
