# REVIEW 2026-10-07: C17 world state, regime rows, scenarios, dormant news wire

Reviewer: Opus 5.5, adversarial forecaster/quant. Read-only. No paid calls. Branch
`wip/2026-10-06-v1-beta` (uncommitted tree). Scope: `backend/services/world_state.py`
(new), the C17 edits in `world_digest.py`, `scripts/world_digest.py`,
`scripts/sim_run.py`, `opportunities.py`, `config.py`, and `test_world_state.py` plus
its fixture. Evidence comes from the code, the two real cycle receipts
(`digest/world_state_20261006T214456Z.json`, `..._20261006T223002Z.json`),
`world_state/beliefs.json`, the 14 `news_digest:regime_v0` rows in `predictions.jsonl`,
the 19,659 cached typed rows (`news_corpus/_digest_cache/extract_wd_v1.jsonl`), and
read-only Python I ran against them.

## VERDICT

**SHIP AS DORMANT PLUMBING. DO NOT READ ITS FIRST GRADES.** The engineering is careful:
it is idempotent per digest, writes receipts with a run id, turns failures into refusals,
keeps the wire dormant, and the flag-off path is provably a no-op. The forecasting
design has a different problem. Five of the 14 regime rows grade an event that
contradicts their own label. Weekend cycles mint duplicate rows for the same price
window. The belief table measures how much the LLM's output varies from one sample to
the next, not how the world changes. Trust key 1 is "met" at t = 0.13. The first grades
on 10-10 / 10-16 will say "the LLM lost to the base rate", and most of that loss is
built into the prompt and the grading code. That would be a negative result with no
evidence behind it (CLAUDE.md mission). F1-F4 should be fixed before 10-10.

**Score: 54 / 100.** The plumbing alone would earn about 80. The instrument (does
the broad LLM call beat persistence?) as written cannot answer its own question.

## Tests (item 7)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_world_state.py \
  backend/tests/test_world_digest*.py backend/tests/test_u_plan_probe.py -q
..............................................................           [100%]
62 passed in 11.56s
exit=0
```

Mocks and stand-ins in `test_world_state.py`:
- `FakeLLM` stands in for DeepSeek and captures the system prompt.
- `_px()` is a synthetic random-walk panel (`default_rng(3)`, 330 business days, drift
  0.0003, sd 0.01, identical for every ETF).
- `monkeypatch WD.optimus -> tmp_path` and `monkeypatch WS.load_scenarios`.
- `SimpleNamespace(symbol, weight)` stands in for `PB.Target`.
- `tmp_path` stands in for the prediction-market snapshot directory.

No test runs `u_plan` on real plan output. No test checks label/event coherence,
weekend duplication, or the stability of a belief between two overlapping digests. Each
of those is a defect found below.

## Findings

### F1 - HIGH: five of 14 regime rows grade an event that contradicts their label (items 2, 8)

`REGIME_SYSTEM` asks for "p = the probability that YOUR LABEL holds". It also tells
the model "state honest probabilities near 0.5". It never shows the model the base rate
of the event. `regime_records` then converts `p_label` into P(event) and the grader
scores it against base rates that are far from 0.5. Real rows from 2026-10-06:

| variable | h | label | p_label | graded P(event) raw | base rate | relative to base, the row says |
|---|---|---|---|---|---|---|
| sector_leadership | 1 | XLK | 0.30 | 0.30 (XLK beats SPY) | 0.587 | **XLK underperforms**, the opposite of "leader" |
| sector_leadership | 5 | XLK | 0.32 | 0.32 | 0.591 | **XLK underperforms** |
| geopolitical_stress | 1 | calm | 0.55 | 0.45 (elevated) | 0.353 | **more stress than normal**, the opposite of "calm" |
| geopolitical_stress | 5 | calm | 0.52 | 0.48 | 0.357 | **more stress than normal** |
| growth | 5 | up | 0.52 | 0.52 (SPY up) | 0.564 | **below-base up**, which is bearish |

For sector_leadership the model almost certainly answered P(XLK is the best of 13). A
0.30 on that event, against a 1/13 base, is a strong bullish call. The code grades it
as a 70% bearish call on "XLK beats SPY". That is a sign inversion. The leader of 13 ETFs
has P(beats SPY) at or above the cross-sectional mean (about 0.5-0.6) by construction,
so 0.30 cannot be coherent under the graded event.

Expected Brier penalty against the base rate, computed from these rows: **0.0167 per row
per date**. sector_leadership supplies 0.156 of the 0.233 total (67%). Simulating outcomes
at the base rate: E[improvement vs base] = -0.0167 and per-date sd = 0.0335. The arm
starts half an SD per date behind its null. After about 10 dates it will read t ~ -1.6,
"LLM loses to base rate", and the main cause is the prompt's semantics. **Fix:** ask for
P(event) for a fixed event (never "P(your label)"). Print the 252-session base rate and
persistence beside each variable in the user message. For sector_leadership, ask for
P(beats SPY) for each of the 13 ETFs, or for a top-3 set graded by rank. Add a write-time
coherence assert: when a label is the "positive" side, the event probability must sit
on the same side of the base rate as the label, otherwise refuse the row
(`LABEL_EVENT_INCOHERENT`).

### F2 - HIGH: weekend and Monday-UTC cycles mint duplicate rows for one window (item 2)

The digest runs every 6 h, seven days a week. The once-per-session key is the **UTC
calendar day** (`regime_existing_keys`). The resolver anchors at the first bar on or
after `made_at[:10]` (`belief_state.resolve_one`). Rows made on Saturday UTC, Sunday UTC
and Monday UTC before the open therefore all start at Monday's close and grade the
**same** window. That makes three "dates" for one outcome, and the same happens around
holidays. `trust_from` and `regime_grade` block on `decision_date`, so n_dates is
inflated by about 40% a week and the SE is understated. This is the
`n_effective counts DATE BLOCKS` rule in canon. **Fix:** key on the entry bar, the next
XNYS session close at or after `made_at`, not the UTC day. Write at most one row per
(variable, h, entry_session). Block h5 grading on non-overlapping entry sessions.

### F3 - HIGH: the "persistent belief table" is LLM resampling noise with about 12 hours of memory (item 1)

How the belief is built: direction and confidence are `mean(sign x implication.confidence)`
over the digest's **LLM-generated implications**, times `strength = min(1, n_sources/5)`.
"No model call" is true of this stage only. Every belief is second-hand LLM output.

- **Volume is not conviction, and outlet count is.** In the fixture probes I ran, one
  implication at 0.8 with one outlet gives confidence 0.16. The same wire story from 5
  outlets gives **0.80**. From 20 outlets it gives 0.80, and 11 implications at 0.4 give
  0.40. `n_sources` counts outlets, not root events, so one syndicated story becomes a
  5x belief. On real data `n_sources` is 18-99 for every directional topic, so strength
  is always saturated at 1 and confidence is just the mean implication confidence. On the
  real 21:44Z cycle, `dollar` reached 0.575 from **2** votes while `ai_demand` reached
  0.386 from **11**.
- **Memory.** Every topic was touched on both real cycles (16/16), so the decay
  half-lives (7-21 days) never act. The posterior is `0.5 x prior + 0.5 x evidence`
  **per cycle, independent of the time elapsed**, which makes it an EWMA with alpha = 0.5
  every 6 h.
- **Re-applied evidence.** Idempotency is per `digest_id`, but the digest window is 24-36
  h every 6 h, so each article is applied about four times.
- **Measured instability.** The two real digests were 45 minutes apart. Their windows
  overlapped by about 23 of 24 h (1,483 vs 1,459 items). Between them, four beliefs flipped:
  - `semiconductor_capex`: mixed 0 -> **up 0.567**
  - `china_policy`: none -> **up 0.50**
  - `energy_security`: up 0.283 -> **down 0.059**
  - `rates`: mixed -> up 0.25.

  With almost the same input, the table moved by the variance of the theme/implication
  sampling. That instability is the property this receipt should be reporting first.

**Fix:** weight the update by elapsed time (alpha = 1 - 0.5^(dh/hl)) and by **new**
evidence ids only (skip `item_id`s already applied). Collapse rows into root events (the
digest already has theme merges; reuse its clustering, or a title-shingle hash) before
counting sources. Make confidence a function of independent root events, for example
a Beta posterior on vote signs, not the mean implication confidence. Print
`belief_stability`, the share of beliefs that flip between two consecutive digests with
over 80% item overlap, on every receipt.

### F4 - HIGH: trust key 1 is "met" at t = 0.13 (item 3)

The shadow grade in `world_digest_20261006T223002Z.json` shows direction: n_rows 3,
n_dates 3, mean 0.01203, se 0.09263, posterior 0.000139, trust **0.0069**. That is
t = 0.13. `two_key_state` accepts any `max(trust_dir, trust_size) > 0`.

- Under zero skill, P(mean of 3 dates > 0) ~ 0.5 per arm. Taking the max of two arms
  puts it at about 0.75.
- Even the regime arm, which has a built-in -0.0167 handicap, shows `mean > 0` at 3
  dates with probability **0.198** in my simulation.
- Key 1 is a coin, and `max()` lets the size arm unlock a direction tilt and the reverse.

**Proposed rule:** key 1 holds for an arm only when all of the following are true:

- it is the **same arm** the tilt uses (`trust_dir` gates the `d` term, `trust_size`
  gates the `s` term; never `max`);
- n_independent_dates >= N_MDE, where N_MDE = ceil((2.8 * sd_date / delta)^2) and delta
  is declared now. With today's sd_date ~ 0.16 and delta = 0.02 Brier, N_MDE ~ **502**
  sessions. Say so rather than hide it;
- posterior mean - 1.64 * posterior sd > 0;
- trust >= 0.05 (posterior >= 0.001 Brier).

Leaving `MIN_DATES = 3` as the gate for a trust that can reach 0.25 is the defect. The
shrinkage is the same as the other arms (same `trust_from`, tau = 0.01, MIN_DATES 3), so
the regime arm is no looser than the others. It is equally meaningless at 3.

### F5 - MEDIUM: regime-row MDE, and when trust could leave 0 (item 2)

The regime arm has 14 rows a date (7 variables x 2 horizons) and a simulated per-date
sd of 0.0335 for the improvement against base.

| target per-row Brier improvement delta | independent dates for MDE (80%, 5%) |
|---|---|
| 0.005 | **353** |
| 0.0025 | 1,411 |
| 0.001 | 8,817 |

At one independent date per session (after F2), delta = 0.005 takes about 1.4 trading
years. The h5 rows overlap, so each h5 field needs at least 5x more calendar time. Under
the current rule trust can leave 0 at date 3 by luck (F4). Under an MDE rule it cannot
leave 0 before about 2028 unless the effect is large. That is the honest answer, and it
belongs on the receipt now. `regime_grade` prints a per-field MDE. It needs to print
N_needed beside it.

### F6 - MEDIUM: the stress observable is fair as "realised-vol regime" and mislabelled as geopolitics (item 2)

`|SPY h-return| > sigma63 * sqrt(h)`, with base rate 0.353 (h1) and 0.357 (h5), is a
reasonable realised-move event. It fires on CPI, FOMC and earnings days just as readily
as on wars. Calling it `geopolitical_stress` invites the model to reason about
geopolitics and then grades it on macro prints. Volatility is also the most forecastable
series here, so the binary persistence null (P(event | last window's event)) is a weak
null. A GARCH/EWMA P(|r| > thr), or the existing `WD.vol_prior_p` the size arm already
uses, is the null a quant would require. **Fix:** rename it to `realised_stress` and add
`vol_prior_p` as a third null.

### F7 - MEDIUM: baselines are point-in-time but one session stale; the measured moves too

The rows were made at 2026-10-06T21:46Z, after the 10-06 close. Their
`session_as_of` = **2026-10-05**. The baselines and the "MEASURED MOVES" in the prompt
both read a panel that ended a session before the one the row was written after. That is
point-in-time safe (no future bar; the resolver anchors at the 10-06 close). The cost is
twofold:

- The persistence null conditions on the 10-05 window, not the 10-06 window that sits
  immediately before the forecast. That is a lag-2 persistence, which is a weakened null.
- The model was not shown the session that had just closed.

**Fix:** refuse to write when `px.index[-1] < last completed XNYS session before
made_at`, or refresh the proxies first. Print `panel_lag_sessions` on the row.

### F8 - MEDIUM: scenario priors are dated and authored, but cannot be restated cleanly, and the cap makes them jump and saturate (item 4)

- **Who chose them.** `SCENARIO_DECLARED_BY = "C17 builder (Opus), 2026-10-07: declared
  priors, not learned; the owner may restate them"` covers all eight priors as one string.
  The priors live in code (`SEED_SCENARIOS`) with no per-scenario version or hash.
- **Restating corrupts the log.** If the owner edits a prior, the next
  `update_scenarios` appends an `update_log` entry whose `why` names the
  **belief indicators**, so the owner's restatement is recorded as a belief-driven move.
  **Fix:** move the priors into a dated, owner-signed config block
  (`declared_by`, `declared_at`, `prior_hash`). Log a prior change as
  `PRIOR_RESTATED` and never as a belief move.
- **Jumpy and saturating.** The shift is recomputed from the **current** table with
  K = 0.6 and a cap of +-0.5 logit. Because the table is F3's noise, 2027 probabilities
  moved within 45 minutes:
  - `ai_capex_supercycle_2027`: 0.481 -> **0.524**
  - `higher_for_longer_2027`: 0.300 -> 0.349
  - `ai_capex_digestion_2027`: 0.209 -> 0.168

  0.5236 is exactly sigmoid(logit(0.40) + 0.5): **the cap was reached on the second
  cycle**. A three-year scenario that hits its bound in 45 minutes is acting as a
  tri-state news-tone indicator (floor / prior / cap), not a probability.
  **Fix:** update on a slow EWMA of the belief table (weeks) with a per-day move cap,
  or show "prior + today's tilt" as two numbers and never as one probability.
- **The guard protects no real reader.** `Scenario.probability_for` refuses
  non-display purposes, but every real reader (`scenario_tags_for`,
  `opportunities._scenarios`, `scenarios.json`) reads `current_probability` straight from
  the dict and bypasses it. The guard sits on a path nobody uses. The label-only property
  actually rests on `scenario_tags_for` emitting only strings, which the test does pin.
  Say that, rather than credit `ScenarioNotForSizing`.
- **Stale market prior handled correctly.** The 46-day-old prediction-market snapshot
  is correctly reported and not used.

### F9 - MEDIUM: provenance is a fallthrough default, row-level, and decorative (item 5)

Across the 19,659 cached rows: FACT 13,155 (67%), INTERPRETATION 2,965, FORECAST 2,589,
COMPANY_CLAIM 950. I drew a 20-row random sample (seed 7100172), plus targeted pulls.

- **FACT is the residual bucket.** A row is FACT when no rule fires. Most sampled FACT
  rows are headlines with an empty summary, so nothing was checked.
- **FACT given to a management forward statement.** One FACT row (`product`/new_fact)
  reads "IonQ said its next-generation systems **will** be first installed at Nvidia's..."
  It is labelled FACT because the extractor emitted no `forward_claim`. 107 FACT rows
  carry forward language in their summary. Most headline-only rows have no summary to check.
- **FACT given to analyst opinions.** 70 `analyst_action` rows are FACT
  (new_fact/update/recap). "Analyst downgraded X" is a fact about an event whose content
  is an opinion.
- **COMPANY_CLAIM given to filed numbers.** Of the earnings rows, 40 are
  `COMPANY_FORWARD_CLAIM` and 3 are `TRANSCRIPT`. Among them, "Jefferies **reported
  higher third-quarter profit and revenue**, beating estimates" and "Agilysys **reported
  record Q1 revenue of $87.7M**" are whole-row COMPANY_CLAIM because one management
  forward claim was attached. The reported actuals, which are FACT, are relabelled. The
  label is per row and should be per claim.
- **Provenance changes no number.** It is carried into `provenance_mix` and nothing
  more. A third-party FORECAST row (an analyst estimate page) counts toward
  `n_sources` and topic evidence exactly like a FACT row.

**Fix:** stamp provenance per claim (actuals vs forward), use `UNCLASSIFIED` instead of
FACT as the fallthrough, and weight evidence by provenance, or state on the receipt that
provenance is observation-only.

### F10 - MEDIUM: the news wire is no-op when off, but would bypass the order-path gate when on (item 6)

**Flag off.** `_plan_news_tilt` assigns `t.weight` only inside `if res["applied"]`, and
`plan_news_tilt` returns `weights` itself (the same object) unless the flag is on and a
trust is above 0. So with the flag off the targets are byte-identical **by code reading**.
The test proves it on `SimpleNamespace` targets, not on a real `u_plan` receipt. I would
add a replay of one archived `u_plan` input with the flag forced on and both trusts 0,
asserting the orders list is equal.

**Flag on, the cases that are safe:**
- It cannot create an order from a zero weight: `min(..., 0 x 1.25) = 0`.
- It cannot drop a held name: the factor is at least 0.75 / 1.375 ~ 0.545 before
  renormalisation, and `round(v, 6)` would only drop a weight below 5e-7.
- A shrink below one share or below `MIN_ORDER_USD` becomes a refused small trim in
  `plan_orders`, which is long-only.

**Flag on, the cases that are not safe:**
- The tilt runs **after** `_order_path_gate`. A name can rise up to 1.25x its gated
  weight. Gross cannot rise, but the gate's **per-name sigma-based worst case** can,
  because weight moves from low-sigma names toward high-sigma names, for example a PROBE
  name. **Fix:** apply the tilt before the gate, or re-run the gate on the tilted weights.
- The tilt applies to EXPLOIT and PROBE as one sleeve. Key 2 measures
  `mdc_news_tilt` on the shadow book (SHADOW_BAYES_v0). Unlocking it on the PC book
  assumes the measurement transfers to a different book. Say so in the two-key rule.
- Daily tilt changes create rebalancing churn. Key 2's `mean_bps` must be net of those
  trades. I could not confirm that from this chunk.

### F11 - LOW: causal edges are co-occurrence, and contradict themselves

Within one cycle, `ai_demand -> semiconductor_capex` was stored as both **+** and **-**
from the same theme. `rates -> ai_demand (+)` came from a "global bond selloff" theme.
An edge is "topic A matches >= 25% of a theme's rows and an implication names topic B",
which is co-occurrence. Nothing consumes edges today, so this is a naming overclaim
rather than harm. **Fix:** rename to `co_mention_edges` and net the signs per (A, B, cycle).

### F12 - LOW: a hard-coded calendar literal that is already wrong

The `regime_grade` note says "not a finding before the first h5 grades (2026-10-09)".
The real first h5 `resolves_after` is **2026-10-16** (h1 is 2026-10-10). That is a
literal date in code, the protocol item 5 family. Derive it from the rows.

### F13 - LOW: two Briers for one row

The ledger's `brier` is computed on the shrunk `probability`. `regime_grade` uses
`raw_probability`. Any generic skill dashboard reading `brier` will show near-base-rate
rows that look skill-less by construction (shrink 0.2). Label the ledger field, or
exclude regime rows from generic skill tables.

## Item 8: the table a forecaster wants on 10-10, and whether the code produces it

The single table: **per (variable, horizon), over independent entry sessions:** n, the
Brier of the model's raw probability, the Brier of persistence, the Brier of the base
rate, the Brier of the EWMA-vol null for stress, delta vs each null +- a block SE that
does not overlap for h5, MDE and N_needed, the label hit rate, the count of
coherence-refused rows, and a verdict (BEATS / LOSES / CANNOT DISTINGUISH).

`regime_grade` covers part of this. It prints the per-field improvement vs both nulls,
trust, MDE and n_open, under a run-id file name. It does **not**:

- print the absolute Briers;
- deduplicate entry sessions (F2);
- correct h5 overlap;
- flag the incoherent rows (F1);
- print N_needed.

Because of F1, its first output will be dominated by sector_leadership's built-in
0.08 penalty per row. As shipped, the code would answer the question with an artefact.

## Three things I would have done instead

1. **Grade an event, not a label, and give the model the base rate.** Ask for P(SPY up
   | base 0.53, persistence 0.54), P(|SPY| > sigma*sqrt(h) | base 0.35, EWMA-vol null),
   and so on, for a fixed event each. Ask for 13 sector probabilities instead of a
   "leader". Then the only thing graded is the model's departure from the null, which is
   the question.
2. **Make the world state slow and evidence-incremental.** Use root-event clustering,
   update only on item ids not yet applied, use an elapsed-time alpha, use a Beta
   posterior on independent vote signs, and print belief stability on every receipt.
   Then two digests 45 minutes apart cannot flip `energy_security`, and a scenario
   cannot hit its cap in one evening.
3. **Write the decision rule as an MDE before any row exists.** Declare delta, N_needed
   per field, one row per entry session, and a key 1 that needs the lower bound above 0
   on the arm the tilt uses. Then "trust 0.0069 = key met" cannot happen, and the owner
   sees "about 350 independent sessions to detect delta = 0.005" on day one instead of
   discovering it in 2027.
