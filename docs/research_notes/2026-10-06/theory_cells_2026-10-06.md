# Theory cells at $0, and a hypothesis lab that stops generating what keeps dying (CHUNK C12, 2026-10-06)

**RESULT IMPROVEMENT: NONE.** All three declared cells came back `FAILED_VARIANT`, so no new
actionable finding. The lab's generation is now posterior-fed (D6). LLM spend for the cells and
the wiring: **$0.00**. The nightly caps ($3/night, $0.40/run) are unchanged.

| cell | family | primary (validate 2009-2016) | verdict |
|---|---|---|---|
| (a) standalone `hi52` (price / 52-week high), CRSP, fair twin | price_location | fair-twin net **-0.31%/mo**, t -1.00, 2 of 8 years | `FAILED_VARIANT` |
| (b) insider buy with no sale by the buyers within 90 days | insider_hold | HOLD H63 net vs size band **-1.82%/63d**, t -5.75, 0 of 8 years | `FAILED_VARIANT` |
| (c) consecutive EPS beats >= 3 minus first beats, H63 drift | earnings_streak | design-signed **-0.48%/mo**, t -1.11, 3 of 8 years | `FAILED_VARIANT` |

None of the primaries was positive, so protocol item 11 (by year plus leave-one-year-out on any
positive) had nothing to rescue or kill. Both are still printed in every receipt and below.

---

## 1. The generation shrink (D6, borrowed from RD-Agent(Q))

**What changed.** `hyp_lab.family_record()` already held a Beta(1,4) posterior per family, but
until now it only re-ranked hypotheses that had already been generated. It now feeds backward
into generation.

- `backend/config.py`: `HYP_LAB_FAMILY_POSTERIOR_FLOOR = 0.15`, `HYP_LAB_FAMILY_MIN_WEIGHT = 0.25`,
  `HYP_LAB_FAMILY_MAX_SHARE = 0.5`.
- A family's weight is 1.0 at or above the floor. Below it, the weight is `max(0.25, p / 0.15)`.
  - **Generation quota** = `floor(ceil(n x 0.5) x weight)`, never below 1. With n = 8, a healthy
    family may take 4 of the round; a family at p = 0.087 may take 2.
  - The quota is enforced in two places: in the prompt (a `FAMILY BUDGET` line names each shrunk
    family and its cap) and after parsing. Rows over the quota are appended as
    `DEFERRED_FAMILY_BUDGET`. They are not dropped, and `rank()` re-admits them once the family's
    posterior is back at the floor.
- **EV shrink** in `score()`: `ev = weight x p_change x value - cost`. `ev_unshrunk` sits beside
  it. The weight is read from a new declared `policy_state` key, `hyp_family_ev_weight`. That key
  is bounded below by 0.25, so `policy_state` itself refuses a zero: it is a preference, not a
  kill. Writes are journaled, with the posteriors as evidence.
- `CANDIDATE` was added to `VERDICTS` and counts as a positive in the posterior.
- The nightly (`scripts/hyp_lab.py nightly`) applies the policy before generating. Its receipt
  now carries `family_policy` with per-family `posterior / weight / quota / n_generated_tonight /
  n_deferred_tonight / n_shrunk`. LEDGER.md's family table prints the same columns.
- `python -m scripts.hyp_lab plan [--apply]` gives the same report at $0.

**First receipt:** `backend/data/optimus/hyp_lab/receipts/family_budget_20261006T160625Z.json`
(`--apply`, so the preference was WRITTEN to policy_state).

| family | posterior | weight | quota of 8 | queue rows shrunk |
|---|---|---|---|---|
| macro_readthrough_commodity | 0.087 | 0.58 | 2 | 6 |
| event_readthrough_corr_peer | 0.133 | 0.889 | 3 | 10 |
| llm_size_reading | 0.143 | 0.953 | 3 | 0 |
| every other family (16 at the time) | 0.16-0.35 | 1.0 | 4 | 0 |

`n_generated_tonight` was 0 everywhere: the plan made no generation call. The three new
families this chunk created (`price_location`, `insider_hold`, `earnings_streak`) now each sit
at 0.1667 (one FAILED_VARIANT against the prior), which is above the floor. The prior is
Beta(1,4), so a family reaches the floor on its second clean failure.

---

## 2. The cells (declared, hashed, then run, sequentially)

All three declarations were written and sha256-hashed **before** any cell ran, and entered the
ledger as `DECLARED`:

| cell | declaration | sha256 (16) | hyp_id |
|---|---|---|---|
| hi52 | `hyp_lab/theory_hi52_DECLARATION_TC_2026-10-06_1.json` | 751bd2b23de6176f | H-25702b3bfd |
| insider_hold | `hyp_lab/theory_insider_hold_DECLARATION_TC_2026-10-06_1.json` | 32984679f7ccc686 | H-aca81f5b8f |
| beat_streak | `hyp_lab/theory_beat_streak_DECLARATION_TC_2026-10-06_1.json` | f2697a8784a993f7 | H-3471279117 |

Shared decision rule (`scripts/hyp_theory_cells.py` `DECISION`):

- `CANDIDATE` needs all four: design > 0, validate > 0 at t >= 2 (3-month blocks), a strict
  majority of validate years > 0, and a leave-one-year-out worst validate mean > 0.
- `FAILED_VARIANT` if validate <= 0, or if t < 2 with an MDE no larger than the effect worth having.
- Anything else is `CANNOT_DISTINGUISH`.
- A run refuses on a declaration hash mismatch, on an input-file sha change (hi52), and below
  4 GB free RAM. The RAM gate polls every 2 minutes for up to 40 minutes.

Cell (c) polled seven times, about 14 minutes, while another lab and the C1 board held the
memory, and then started at 6.99 GB free.

### (a) `hi52` standalone: FAILED_VARIANT

Results: `hyp_lab/theory_hi52_RESULTS_TC_2026-10-06_1.json`. Input: today's fair-twin board
series `hyp_lab/fair_twin_series_FT_2026-10-06_1/{hi52,hi52_large,hi52_q}.parquet`, with file
shas pinned in the declaration.

**Correction to the snowball note.** That note says standalone `hi52` was "not found by name in
any CRSP-run receipt". That is wrong. `hi52` was run by name in
`crsp_rebuild/library_rules_LIB_2026-09-29T0802Z.jsonl`, with headline `FAILED_VARIANT` (rule
minus twin21 -0.33%/mo, t -2.44). This cell is therefore a **re-read under the hyp_lab rule on
the fair twin, not a fresh test**: search count +0. The declaration says so.

| rule | column | design 1991-08 | validate 2009-16 | late 2017-24 | full |
|---|---|---|---|---|---|
| hi52 | pure_selection | -0.44% t -2.50 | -0.12% t -0.39 | -0.20% t -0.55 | -0.31% t -2.26 |
| hi52 | **fair_twin_net** | -0.67% t -3.81 | **-0.31% t -1.00** | -0.43% t -1.17 | -0.53% t -3.88 (5 of 34 yrs) |
| hi52 | net_minus_market | -0.81% t -3.97 | -0.94% t -3.35 | -1.06% t -3.03 | -0.90% t -6.05 |
| hi52_large | fair_twin_net | +0.59% t 1.43 | -0.22% t -0.73 | -0.34% t -0.92 | +0.12% t 0.53 |
| hi52_q | fair_twin_net | -0.02% t -0.11 | -0.18% t -0.74 | +0.24% t 0.85 | +0.00% t 0.03 |

- Every rule and every column is `FAILED_VARIANT`.
- LOO worst on the primary: design -0.84%, validate -0.38%, late -0.52%.
- In a k = 20 book over the full CRSP universe, the price-location feature selects against
  itself in pure selection. The large-cap version's design-era positive does not survive 2009.
- Not run, and still NEEDS_DATA (a small build): ATR / day-range position (roadmap §5 row 12).

### (b) Insider buy, no sale within 90 days: FAILED_VARIANT

Results: `hyp_lab/theory_insider_hold_RESULTS_TC_2026-10-06_1.json`. Events:
`hyp_lab/theory_insider_hold_events_TC_2026-10-06_1.parquet`. Source:
`backend/data/optimus/sec_insider/insider_events_v1.parquet` (the path named in the note).

- **Event construction.** An event is a firm-level, quiet-then-buy officer/director open-market
  buy (not 10b5-1). It is HOLD if none of that day's buyers files a sale of the same stock within
  90 days. Entry is the open of the first session after day 90, the first day "no sale" is
  knowable.
- **Counts.** 44,129 events, 43,339 of them HOLD.
- **The separating variable barely separates.** 97-99% of buys are HOLD in every year, almost
  certainly because Section 16(b) short-swing profit rules deter an officer from selling within
  six months of a purchase. "No sale in 90 days" is close to the default state, not a
  conviction signal. The SOLD control has only 766 events (H63).

| cohort | horizon | vs | mean round trip | event gross | event net | validate net (t) |
|---|---|---|---|---|---|---|
| HOLD | 63 | market | 130 bps | -0.26% | -1.56% | +0.30% (t 0.29) |
| HOLD | 63 | size band | 130 bps | -1.10% | -2.39% | **-1.82% (t -5.75)** |
| HOLD | 21 | market | 130 bps | -0.35% | -1.65% | -0.75% (t -2.75) |
| SOLD | 63 | market | 117 bps | -0.06% | -1.23% | +2.12% (t 1.07, n 766) |

- **Spread beside gross.** The round trip (~1.3%) is larger than any gross number here.
- **Memory check.** The insider-cluster lesson was "real gross, equals the spread". On this
  definition (not clustered, entered 90 days late) the gross is about zero against the market,
  so this cut never had an edge to give up to costs.
- HOLD minus SOLD (gross, H63): validate -1.76%, t -0.82, MDE 5.98%. Underpowered by
  construction, given 766 SOLD events.
- Primary by hold year: negative in all 19 years (2006-2024). LOO is moot.

**Benchmark caveat (affects (b) and (c)).** The size-band equal-weight index is rebalanced daily
over CRSP common stocks. Over the same sessions it beat the market by about 0.8 pp/63d (r_band
3.52% vs r_mkt 2.69% on these events). That is the known upward bias of a daily-rebalanced
equal-weight benchmark. The band-relative lines therefore read too negative. The verdict does
not depend on it: against the market, the HOLD validate net is +0.30% at t 0.29, design is
-3.79%, late is -3.09%, so it is `FAILED_VARIANT` either way.

### (c) Consecutive-beat streaks: FAILED_VARIANT (the bar does NOT measurably rise)

Results: `hyp_lab/theory_beat_streak_RESULTS_TC_2026-10-06_1.json`. Events:
`hyp_lab/theory_beat_streak_events_TC_2026-10-06_1.parquet`.

- **Instrument.** IBES `surpsumu`, EPS, quarterly, US. A beat is actual > consensus mean. The
  streak resets on a miss or meet and on a fiscal gap of more than 4 months.
- **Link.** Ticker to permno via `ibcrsphist` on the announcement day, through the existing
  `crsp_event_bridge.link_permno`. 424,721 of 513,640 linked (82.7%); 423,833 announcements
  after de-duplication. Streak shares: miss/meet 40%, 1: 20%, 2: 11%, 3: 7%, 4: 5%, 5+: 17%.
- **Entry.** Open of the first session after announcement day + 1 business day.

**Primary.** The within-month difference, streak >= 3 minus streak 1, gross H63 drift vs the
size band. Being a difference, it cancels the benchmark bias. The design fold fixed the sign
toward the **ratchet** (design raw difference -0.37%/mo, so the sign applied is -1).

| window | signed mean | t | MDE | years positive |
|---|---|---|---|---|
| design 1994-2008 | +0.37% | 0.84 | 1.25% | 5 of 15 |
| **validate 2009-2016** | **-0.48%** | **-1.11** | 1.20% | 3 of 8 |
| late 2017-2024 | -0.09% | -0.07 | 3.63% | 2 of 8 |

**The owner's question, drift by streak length** (H63 gross drift vs size band; the [e-1, e+1]
reaction in brackets):

| streak | design 1994-08 | validate 2009-16 | late 2017-24 | full |
|---|---|---|---|---|
| miss/meet | -4.88% [-2.19%] | -1.78% [-3.21%] | -1.64% [-3.27%] | -3.54% |
| 1 | -1.76% [+2.18%] | -0.88% [+2.92%] | -0.56% [+2.44%] | -1.35% |
| 2 | -2.18% [+1.84%] | -0.65% [+2.08%] | -0.16% [+1.70%] | -1.42% |
| 3 | -2.14% [+1.67%] | -0.91% [+1.76%] | +0.32% [+1.46%] | -1.33% |
| 4 | -1.80% [+1.70%] | -0.59% [+1.83%] | +0.16% [+1.61%] | -1.11% |
| 5+ | -2.03% [+1.48%] | -0.43% [+1.43%] | +0.49% [+0.88%] | -0.90% |

How to read it:

- **The bar rises in the REACTION, not the drift.** The 3-day announcement reaction shrinks
  monotonically with streak length in every window: +2.2-2.9% for a first beat down to
  +0.9-1.5% at 5+. The market does price streaks in at the announcement.
- **Post-event drift does not shrink with the streak.** After 2009 it slightly improves with the
  streak, the rival story. That is not the declared direction, and it is not significant.
- **The only standing fact is the old one.** Misses drift down (PEAD's negative leg) relative to
  beats. That is not this cell's question.
- Levels sit below zero everywhere because of the band bias above; only the cross-bucket
  differences are read.
- **Tradeable leg** (streak >= 3, net vs market): validate H63 +0.12% (t 0.21), late -1.48%
  (t -1.97), mean round trip 97 bps. Nothing to trade.

---

## 3. TRIAL-ANALYST-SNOWBALL-1: UNSIGNED DRAFT

`docs/TRIALS/TRIAL-ANALYST-SNOWBALL-1.md` is written in the house format from the note's §1:

- t0 = `crsp_pit_bridges.first_movers(raises, gap_days=90)` plus the coverage-start exclusion.
- Primary 1 = P(>= 2 other brokers raise within 21/63 sessions) vs matched chaser raises.
- Primary 2 = 21/63-session return from the first session after t0, against the market, net of
  costs, conditioned on nothing after t0.
- MDE context comes from the 24,323 yfinance events by year.
- Five look-ahead traps are closed in writing.
- `Resurrects:` lines name the 30-day `first_mover_raises` closure and ANALYST-SKILL-1.

**Licence, stated honestly:** the return leg is `PRODUCT_EXPERIMENT`-shadow grade, underpowered as
a `RESEARCH_CLAIM`. It is NOT signed and NOT in the experiment registry.

Linter output (`C:/Users/mrthn/Aegis module/scripts/lint_prereg.py`; the skill names this path,
and there is no `scripts.lint_prereg` in this repo):

```
TRIAL-ANALYST-SNOWBALL-1.md: UNPOWERED_AT_REGISTRATION  (vs 358 prior experiments)
  R13: resolving a 0.4pp effect at dispersion 12pp needs **7064** independent observations. At 1.5e+03 per year over 26 years the corpus can ever supply **312** (R13b: capped from 39000 — your 1.5e+03 events/yr overlap 125.0x at a 21-day horizon, where only 12.0 independent windows fit in a year). This design cannot resolve this claim, and running it would produce a NOT_DETECTABLE that says nothing about the world. The smallest effect this corpus could resolve is **1.9pp** — either declare an effect at least that large AND defend it from turnover, cost, capacity and drawdown consequence, or change the conditioning unit (R14: events, not regimes).
  R13: n_required 7064  n_available 312  smallest resolvable effect 1.9pp
   [near     ] 0.226  prereg    REGISTERED             PREREG_ANALYST_SKILL_1
   [near     ] 0.213  prereg    REGISTERED             PREREG_REVISION_FORECASTER_1
exit=1
```

- No corpse blocks it.
- R13 refuses the return leg. This is the same conclusion as the licence line, now in numbers.
- The draft lays out three options for the signer: (a) sign the follow-through leg only and
  shadow-log the return leg; (b) measure `cross_sectional_rho` and re-lint; (c) reject.
  The builder recommends (a).

---

## 4. Files, tests, receipts

**Code.**
- `backend/services/hyp_lab.py`: family weight, budget, deferral, EV shrink, prompt, LEDGER table,
  `CANDIDATE`.
- `scripts/hyp_lab.py`: `family_policy`, the `plan` command, budget applied in `generate`,
  `family_policy` in the nightly receipt.
- `backend/services/policy_state.py`: `hyp_family_ev_weight` key.
- `backend/config.py`: three `HYP_LAB_FAMILY_*` constants.
- `scripts/hyp_theory_cells.py`: new; the three declared cells.

**Tests.**
- `backend/tests/test_hyp_lab_family_budget.py` (11): includes "posterior 0.10 generates fewer
  than 0.40", nothing dropped, deferral returns, policy key refuses 0, caps untouched, and a
  stubbed generation path with no paid call.
- `backend/tests/test_hyp_theory_cells.py` (9): includes the mutated declaration refusing and
  being recorded, the never-overwrite rule, the RAM gate, insider no-look-ahead, the streak reset,
  and the LOO guard.

**Receipts.** Under `backend/data/optimus/hyp_lab/`: the three `theory_*_DECLARATION_*` and
`theory_*_RESULTS_*` files, two `theory_*_events_*.parquet` files,
`receipts/family_budget_20261006T160625Z.json`, two run logs, and a regenerated LEDGER.md.

**What is owed.**
- ATR / day-range position (row 12 remainder).
- A non-daily-rebalanced size-band benchmark for event studies. The current one is biased upward
  by about 0.8 pp/63d.
- A measured `cross_sectional_rho` before the snowball draft can be signed for its return leg.
