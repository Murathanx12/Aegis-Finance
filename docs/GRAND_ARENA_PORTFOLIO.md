# GRAND-ARENA-1 · Chunk 7 — PORTFOLIO-ARENA-1

**Fifteen complete systems, one eligible set, one clock, one cost model, five
risk matchings, four notionals. CRSP daily 2002-2024, 263 month-end decisions,
394,500 name-months.**

Pre-registered `TRIALS/PREREG_PORTFOLIO_ARENA_1.md` (`lint_prereg` **PASS**
against 327 prior experiments) and committed **before a single portfolio path
existed** (`58857e9` / `46d3d95`). Runner `scripts/arena_panel.py`,
`arena_core.py`, `arena_systems.py`, `run_portfolio_arena_1.py`,
`arena_decompose.py`, `arena_perturbation.py`. Receipts
`data/factory/portfolio_arena_1_{full,sub}.json`, `arena_decomposition.json`,
`arena_perturbation.json` (untracked — `/data/` is gitignored).

Binding law: `docs/GRAND_ARENA_1_AMENDMENT_A.md`. **A3** (raw AND matched),
**A5** (neutral priors), **A7** (this is not a pristine holdout), **A9** (the
objective was frozen first), **A10** (decompose the return).

---

> ## Verdict: **NOT ONE SYSTEM'S RANKING BEATS AN EQUALLY-CONCENTRATED RANDOM DRAW, AND THE ONLY TWO TERMS THAT CLEAR THEIR OWN RULERS ARE COSTS AND BETA.**
>
> **Gross of costs, all fourteen ranked-versus-random contrasts are below their
> own MDE.** The best of them — the NIGHT-11 revision score against a
> volatility-matched random basket of the same twenty names — is **+7.25 %/yr
> against an MDE of 10.14**. The shipping Aegis composite is **+1.93 against
> 10.64** versus a plain random draw. The learned meta-model is **+0.63 against
> 20.44**. Positive skew, the one system pre-declared to lose, is **−2.89
> against 14.57** and does not detectably lose either.
>
> **Net of the repo's own G7 cost model, every selection system loses to the
> market, and the loss is almost exactly the cost of trading.** Cost drag runs
> **−3.5 to −7.7 %/yr** at a 20-name monthly rebalance, against an MDE of
> **0.46 to 0.56** — the single most detectable number in the whole arena, at
> **t = −25 to −38, sign identical in 8 of 8 regime blocks.** Nothing else in
> the A10 decomposition comes within an order of magnitude of that certainty.
>
> **The second detectable term is beta/style, and it is the confound A3 was
> written for.** It contributes **−3.53 %/yr** to the low-beta Aegis composite
> and **+5.76 %/yr** to the high-beta positive-skew system, each clearing its
> own MDE in 7 of 8 blocks. Ranking these systems on raw returns would have been
> ranking their betas.
>
> **Selection, exposure, sizing and execution are below their own rulers in
> every system tested.** Twenty-four decomposition terms; **eight clear their
> MDE and every one of the eight is either costs or beta/style.**
>
> **The buyable index funds win by not trading.** SPY is **−0.37 %/yr** against
> the CRSP value-weighted market (MDE 0.99 — i.e. SPY *is* the market, which is
> the check that the instrument is calibrated). QQQ is **+4.15 against an MDE of
> 4.58 — NOT DETECTABLE**, which is the honest reading of twenty-two years of
> large-cap-growth outperformance measured against its own noise.
>
> **H5 is violated, and the violation is the most practically useful thing
> here.** The ranking is NOT invariant to notional. Equal-weighting the whole
> 1,500-name eligible set is the second-best system at $100k and $1m
> (**−1.06 / −1.08 %/yr**) and **−9.75 %/yr at $10,000**, because at ten
> thousand dollars a 1,500-name portfolio rounds to almost no whole shares and
> the book is mostly cash. A system is not a system until you say how much money
> it is for.
>
> **This is a DIRECTION CHECK on simulated portfolios. No alpha claim, no skill
> claim, no promotion, and under A7 no certification.**

---

## 1. The instrument

### 1.1 One eligible set, shared by every system

Identical to WINNER-GENOME-1 and EXIT-LAB-1, so the three instruments share a
universe and their nulls are comparable:

| property | value |
|---|---|
| source | CRSP daily 2002-2024, `shrcd` 10/11, `exchcd` 1/2/3 |
| decision dates | 263 month-ends, 2003-01-31 → 2024-11-29 |
| eligibility | price ≥ $5 · ≥252 trading days of history · 63-day median dollar volume ≥ $1m · top 1,500 by dollar volume |
| names per date | **exactly 1,500 on all 263 dates** |
| rows | 394,500 name-months, forward return finite on **100.0%** |
| death | 7,283 delistings spliced; performance delists with no `dlret` take Shumway (1997) −0.30; the dollar then sits in cash at `rf` |
| benchmark | CRSP value-weighted total return (`mktrf + rf`), per CANON |

**Every system sees the same names on the same dates with the same information,
and nothing computed after the decision date.**

### 1.2 The frozen objective (A9, declared before any optimisation)

> **Net annualised excess CAGR of terminal wealth over the CRSP VW market**,
> from one dollar compounded through monthly rebalancing, charged G7 on realised
> turnover.

Risk profiles change only the position budget (conservative K=40, **base K=20**,
concentrated K=10). **They change nothing about the evidence standard.** Every
verdict is read off the base profile; the other two appear as sensitivity and
were never allowed to select a winner.

### 1.3 The ruler

Sampling unit is the **month**. MDE = 2.80 × max(Newey-West, IID) SE of the
tested monthly series, annualised. The tested statistic is the arithmetic
monthly mean, because that is what has a standard error; the geometric CAGR is
reported beside it and is never what the MDE is applied to. Eight pre-declared
regime blocks and both sample halves. **Below its own MDE is NOT DETECTABLE and
is never a kill (CANON §19).**

### 1.4 Costs — G7, reused, not reinvented

Corwin-Schultz half-spread stamped at every decision date (median **24.2 bps**,
p90 **89.0 bps**) + 5 bps slippage + 1 bp commission, charged on the one-way
traded notional per name. Index legs pay a declared 5 bps all-in. A name with no
CS estimate pays that date's 90th percentile — an unpriceable spread is an
expensive spread.

Impact is **separate and declared**, because NIGHT-8 recorded that G7 cannot
price it: `impact_bps = 1e4 · C · σ_daily · √(Q/ADV)`, **C = 1.0, declared,
never fitted**, on for the notional sweep only.

### 1.5 No-lookahead proof — PASS on both surfaces

At probe date **2015-01-30**, every daily cell strictly after the probe was
replaced with garbage (returns ~ N(0.5, 1), prices 1e6, volumes 1e15, market cap
1e15, rf and market return 50%/day). **13 of 13 feature columns over 1,500
names came back bit-identical, and 40 of 40 LLM snapshots came back
bit-identical.** `arena_perturbation.json: PASS`.

### 1.6 P5 is the shipping code, and 45.7% of it cannot be run point-in-time

`P5_aegis_deterministic` ports the per-stock branches of
`backend/services/signal_engine.py` verbatim — same clips, same divisors, same
`config.stock_signal_weights`. **Five of the eleven declared branches have no
point-in-time input on this spine:**

| branch | weight | why unavailable |
|---|---:|---|
| `earnings_growth` | 0.30 | no PIT forward-P/E panel joined to this spine |
| `options_iv` | 0.12 | no PIT options-implied panel joined to this spine |
| `pe_bonus` | 0.10 | no PIT trailing-P/E panel joined to this spine |
| `insider_trading` | 0.10 | not joined; and NIGHT-10 found the insider field DOA under 12 green tests |
| `technical_analysis` | 0.08 | no PIT TA composite |

**That is 0.70 of the 1.532 declared weight — 45.7% of the production
cross-sectional stack, missing.** The remaining branches are renormalised and
the share is printed here rather than buried, because a composite quietly
missing nearly half its weight is a different object from the one whose name it
carries. Two further substitutions are declared: the market crash probability is
fixed at `config.crash_base_rate_pct` (12%) — there is no PIT market crash
probability for 2003-2024 and `crash_model.pkl` is recorded broken in CANON, and
cross-sectionally a constant changes the ordering not at all — and
`earnings_quality` is fed SUE through `clip(sue/3, −1, 1)`, a proxy for a
surprise *history*, named as one.

---

## 2. The arena, raw and matched (A3)

**Excess CAGR %/yr against the CRSP VW market, base profile K=20.**

| system | raw | beta-matched | vol-matched | turnover-matched | MDE (raw) | verdict (raw) |
|---|---:|---:|---:|---:|---:|---|
| `P0_SPY` | −0.37 | — | — | — | 0.99 | NOT DETECTABLE |
| `P1_QQQ` | **+4.15** | — | — | — | **4.58** | NOT DETECTABLE |
| `P2_equal_weight_all` | −1.05 | −2.29 | −2.53 | −1.05 | 4.05 | NOT DETECTABLE |
| `P3_random` | −9.48 | −9.25 | −8.68 | −7.57 | 6.47 | **DETECTABLE NEGATIVE** |
| `P4_volmatched_random` | −10.69 | −10.50 | −9.96 | −9.97 | 5.57 | **DETECTABLE NEGATIVE** |
| `P5_aegis_deterministic` | −5.17 | −4.58 | −4.49 | −4.42 | 8.26 | NOT DETECTABLE |
| `P9_learned_meta` | −16.31 | −9.95 | −7.83 | −16.05 | 22.58 | NOT DETECTABLE |
| `P11_momentum_event` | −7.76 | −7.58 | −7.67 | −7.29 | 10.77 | NOT DETECTABLE |
| `P12_revision` | −4.12 | −6.17 | −5.70 | −3.93 | 9.42 | NOT DETECTABLE |
| `P13_positive_skew` | −16.52 | −12.82 | −9.29 | −15.86 | 15.54 | NOT DETECTABLE |
| `P14_risk_targeted_positive_skew` | −9.29 | −8.99 | −8.96 | −9.29 | 7.65 | **DETECTABLE NEGATIVE** |
| `P10_evolutionary_survivor` | **DECLARED NON-RUN** — chunk 8 has not run; there is no survivor, and fabricating one would be inventing a competitor | | | | | |
| `P6/P7/P8` LLM-fed | run in `GRAND_ARENA_ABLATION.md`, **not here and not in the sub-arena table of §5**; they cannot choose from 1,500 names because the LLM panel covers 40. `run_portfolio_arena_1._llm_systems()` returns `{}` by design so that a sub-arena run made before the LLM panel landed cannot silently omit them — corrected 2026-08-12, an earlier revision of this row read "run in the sub-arena", which the code does not do | | | | | |

**The five A3 dimensions, measured rather than asserted.**

| system | vol %/yr | realised β | gross exposure | effective N | turnover 1-way/mo | cost %/yr | max DD % |
|---|---:|---:|---:|---:|---:|---:|---:|
| `P0_SPY` | 14.6 | 0.96 | 1.00 | 1.0 | 0.00 | 0.00 | −50.8 |
| `P1_QQQ` | 18.0 | 1.09 | 1.00 | 1.0 | 0.00 | 0.00 | −49.7 |
| `P2_equal_weight_all` | 19.3 | 1.22 | 1.00 | 1500.0 | 0.06 | 0.48 | −55.3 |
| `P3_random` | 20.8 | 1.20 | 1.00 | 20.0 | 0.99 | 6.33 | −55.1 |
| `P4_volmatched_random` | 17.1 | 0.95 | 0.81 | 20.0 | 0.80 | 5.13 | −47.9 |
| `P5_aegis_deterministic` | 16.3 | **0.67** | 1.00 | 20.0 | 0.84 | 4.95 | −47.4 |
| `P9_learned_meta` | **40.4** | **1.82** | 1.00 | 20.0 | 0.78 | 7.50 | **−84.7** |
| `P11_momentum_event` | 24.8 | 1.26 | 1.00 | 20.0 | 0.94 | 7.20 | −74.9 |
| `P12_revision` | 25.1 | 1.34 | 1.00 | 20.0 | 0.61 | 4.37 | −66.6 |
| `P13_positive_skew` | 33.9 | **1.54** | 1.00 | 20.0 | 0.74 | 7.03 | **−88.9** |
| `P14_risk_targeted_positive_skew` | 16.7 | 0.75 | 0.47 | 20.0 | 0.36 | 3.37 | −46.7 |

Gross exposure is **verified, not imposed**: every raw long-only system sits at
1.00 except the two that carry an explicit cash blend as part of their
definition (P4 at 0.81, P14 at 0.47), so gross-matching is satisfied by
construction and the measured column proves it. Concentration is matched by the
common K=20, and effective N confirms it at exactly 20.0 for every selection
system.

**The matched columns barely move anything, and that is itself the answer.**
Every raw number is already below its MDE except three, and all three of those
are *negative*. There is no raw winner for matching to destroy — which is a
weaker and more honest outcome than "the winner was an exposure artefact",
because it means the arena never produced a winner to interrogate.

### The one place matching moves a number a long way

`P9_learned_meta` goes from **−16.31 raw to −7.83 vol-matched** and
`P13_positive_skew` from **−16.52 to −9.29**. Both carry huge volatility (40.4%
and 33.9% against the market's ~16%) and both are levered *down* to the market's
volatility by the match. **Roughly half of what those two systems lost, they
lost by being volatile in a market that fell twice.** That is exposure, not
selection, and the raw column would have blamed the ranking.

---

## 3. H3 — the deciding clause: does the ranking beat random?

The clause was pre-registered because it is what separates "the ranking is
informative" from "being invested in twenty names is informative". It is run
**gross of costs**, so that trading friction cannot mask or manufacture the
answer.

| contrast, GROSS | Δ %/yr | its MDE | t | blocks | halves | verdict |
|---|---:|---:|---:|:--:|:--:|---|
| `P12_revision` − volmatched random | **+7.25** | 10.14 | 2.00 | 6/8 | yes | NOT DETECTABLE |
| `P11_momentum_event` − volmatched random | +6.56 | 11.48 | 1.60 | 5/8 | yes | NOT DETECTABLE |
| `P5_aegis` − volmatched random | +5.03 | 9.26 | 1.52 | 6/8 | yes | NOT DETECTABLE |
| `P2_equal_weight_all` − volmatched random | +4.91 | 5.10 | 2.69 | 7/8 | yes | NOT DETECTABLE |
| `P12_revision` − plain random | +4.15 | 9.56 | 1.22 | 6/8 | yes | NOT DETECTABLE |
| `P11_momentum_event` − plain random | +3.45 | 10.92 | 0.89 | 5/8 | no | NOT DETECTABLE |
| `P9_learned_meta` − volmatched random | +2.81 | 22.13 | 0.36 | 3/6 | no | NOT DETECTABLE |
| `P5_aegis` − plain random | +1.93 | 10.64 | 0.51 | 6/8 | yes | NOT DETECTABLE |
| `P2_equal_weight_all` − plain random | +1.80 | 4.84 | 1.04 | 6/8 | yes | NOT DETECTABLE |
| `P9_learned_meta` − plain random | +0.63 | 20.44 | 0.09 | 2/6 | no | NOT DETECTABLE |
| `P13_positive_skew` − volmatched random | +0.21 | 15.69 | 0.04 | 3/8 | no | NOT DETECTABLE |
| `P14_risk_targeted_skew` − volmatched random | −0.52 | 8.37 | −0.17 | 5/8 | no | NOT DETECTABLE |
| `P13_positive_skew` − plain random | −2.89 | 14.57 | −0.56 | 6/8 | no | NOT DETECTABLE |
| `P14_risk_targeted_skew` − plain random | −3.62 | 9.14 | −1.11 | 6/8 | yes | NOT DETECTABLE |

**Fourteen of fourteen NOT DETECTABLE.** Eight of the fourteen have a positive
point estimate and none of the eight clears its ruler; the largest, revisions at
+7.25, needs 10.14 to be seen. **This is not a refutation of selection — it is a
statement that at n = 263 months and a 20-name budget, this instrument cannot
see a selection effect smaller than roughly 10 %/yr, and none of these rankings
produces one.**

The *net* version of the same table (against P4, after costs) contains exactly
one detectable cell: `P2_equal_weight_all` at **+9.55 against an MDE of 5.10,
7/8 blocks**. It is real and it is not selection: P2 turns over **6% a month**
against P4's **80%**, and the gap is 5.1 percentage points of cost per year plus
the small-cap breadth premium. **Owning everything and not trading beats owning
twenty randomly chosen names and rebalancing them monthly. That is a statement
about turnover.**

---

## 4. Amendment A10 — the decomposition, each term beside its own MDE

| system | term | Δ %/yr | its MDE | t | blocks | verdict |
|---|---|---:|---:|---:|:--:|---|
| `P5_aegis` | selection (gross vs random) | +1.93 | 10.64 | 0.51 | 6/8 | NOT DETECTABLE |
| | exposure (raw − beta-matched) | −1.56 | 4.16 | −1.05 | 5/8 | NOT DETECTABLE |
| | sizing (K=10 − K=40) | +3.36 | 6.24 | 1.51 | 6/8 | NOT DETECTABLE |
| | execution (raw − turnover-matched) | −0.52 | 0.89 | −1.64 | 5/8 | NOT DETECTABLE |
| | **costs (1× − 0×)** | **−4.95** | **0.46** | **−29.87** | **8/8** | **DETECTABLE NEGATIVE** |
| | **beta/style** | **−3.53** | **3.03** | **−3.26** | **7/8** | **DETECTABLE NEGATIVE** |
| | timing | — | — | — | — | NOT MEASURED (chunk 6's instrument) |
| | LLM | — | — | — | — | see `GRAND_ARENA_ABLATION.md` |
| `P11_momentum_event` | selection | +3.45 | 10.92 | 0.89 | 5/8 | NOT DETECTABLE |
| | exposure | +0.89 | 3.83 | 0.65 | 4/8 | NOT DETECTABLE |
| | sizing | −0.41 | 7.90 | −0.14 | 4/8 | NOT DETECTABLE |
| | execution | −0.26 | 1.31 | −0.55 | 6/8 | NOT DETECTABLE |
| | **costs** | **−7.20** | **0.52** | **−38.39** | **8/8** | **DETECTABLE NEGATIVE** |
| | **beta/style** | **+2.82** | **2.42** | **3.26** | **7/8** | **DETECTABLE POSITIVE** |
| `P12_revision` | selection | +4.15 | 9.56 | 1.22 | 6/8 | NOT DETECTABLE |
| | exposure | +3.05 | 3.92 | 2.18 | 7/8 | NOT DETECTABLE |
| | sizing | −0.36 | 7.84 | −0.13 | 5/8 | NOT DETECTABLE |
| | execution | −0.09 | 0.54 | −0.49 | 5/8 | NOT DETECTABLE |
| | **costs** | **−4.36** | **0.48** | **−25.59** | **8/8** | **DETECTABLE NEGATIVE** |
| | **beta/style** | **+3.60** | **3.09** | **3.26** | **7/8** | **DETECTABLE POSITIVE** |
| `P13_positive_skew` | selection | −2.89 | 14.57 | −0.56 | 6/8 | NOT DETECTABLE |
| | exposure | −1.30 | 6.92 | −0.53 | 6/8 | NOT DETECTABLE |
| | sizing | +0.29 | 12.27 | 0.07 | 4/8 | NOT DETECTABLE |
| | execution | −0.33 | 0.62 | −1.46 | 3/8 | NOT DETECTABLE |
| | **costs** | **−7.03** | **0.56** | **−35.46** | **8/8** | **DETECTABLE NEGATIVE** |
| | **beta/style** | **+5.76** | **4.95** | **3.26** | **7/8** | **DETECTABLE POSITIVE** |

**Twenty-four terms. Eight clear their own MDE. Every one of the eight is either
costs or beta/style.** The four selection terms, the four exposure terms, the
four sizing terms and the four execution terms are all below their own rulers.

Two readings of that, and only the second is licensed:

- *Not*: "selection, exposure, sizing and execution do not matter." Their rulers
  are 4 to 15 %/yr wide, and an effect smaller than that is invisible here.
- **Licensed**: at this sample and this budget, the only things this arena can
  *see* are how much you pay to trade and how much market you are carrying —
  and it sees both with certainty (t up to 38, 8/8 blocks). Everything a system
  designer usually argues about is below the resolution of the instrument that
  is supposed to be judging it.

`timing` is deliberately absent. An always-invested, monthly-rebalanced arena
contains no timing decision, and printing a timing term from it would be
inventing a measurement. Chunk 6's `EXPOSURE-ARENA-1` is the instrument for that.

---

## 5. The sub-arena — 40 names, 119 months, where the LLM systems can live

The LLM panel declared in `PREREG_ABLATION_1` covers 40 names per date on 119
month-ends. Running LLM-fed systems against systems that chose from 1,500 names
would compare **opportunity sets, not systems**, so the identical machinery is
run a second time on the 40-name set where every system sees exactly the same
names.

| system | raw | 0× gross | MDE (raw) | turnover | realised β | verdict |
|---|---:|---:|---:|---:|---:|---|
| `P0_SPY` | +0.06 | — | 1.76 | 0.00 | 0.96 | NOT DETECTABLE |
| `P1_QQQ` | +5.29 | — | 7.03 | 0.00 | 1.07 | NOT DETECTABLE |
| `P2_equal_weight_all` (of the 40) | −7.50 | −0.91 | 8.74 | 0.97 | 1.20 | NOT DETECTABLE |
| `P3_random` | −5.81 | +1.13 | 10.69 | 0.98 | 1.25 | NOT DETECTABLE |
| `P4_volmatched_random` | −5.76 | +0.40 | 9.55 | 0.88 | 1.10 | NOT DETECTABLE |
| `P5_aegis_deterministic` | −6.48 | −0.39 | 7.57 | 0.98 | 1.04 | NOT DETECTABLE |
| `P9_learned_meta` | −15.42 | −8.92 | 18.94 | 0.97 | 1.11 | NOT DETECTABLE |
| `P11_momentum_event` | −7.13 | −0.67 | 9.71 | 0.98 | 1.09 | NOT DETECTABLE |
| `P12_revision` | −2.73 | +4.12 | 9.99 | 0.98 | 1.19 | NOT DETECTABLE |
| `P13_positive_skew` | −9.58 | −2.25 | 12.02 | 0.98 | 1.29 | NOT DETECTABLE |
| `P14_risk_targeted_positive_skew` | −8.70 | −3.95 | 7.78 | 0.64 | 0.86 | UNRESOLVED_UNSTABLE |

**A structural property of this sub-arena, stated because it changes how its
numbers must be read.** The 40 names are drawn independently at every date by
the seeded stratified sample the prereg declared, so consecutive months share
almost no names and **every arm is forced into ~98% one-way turnover.** That
cost — roughly 7 %/yr — is *identical across arms* and therefore cancels exactly
in every paired comparison, which is what the ablation uses. It does **not**
cancel in the levels, so the sub-arena's level column is not a portfolio anyone
could run, and it is not presented as one. The `0× gross` column is the
readable one.

`P6`, `P7` and `P8` live in `GRAND_ARENA_ABLATION.md`, where they are named
`llm_only_swarm`, `full` and `p8_confidence_weighted`. **P8's specialist
weights are NEUTRAL by Amendment A5** — the 20,073 swarm records are unresolved
and pricing reliability from them would be invented authority — so the only
thing separating P8 from P7 is the model's own stated confidence, which is an
output of the call and not an earned weight. Hierarchical partial-pooled
updating begins when forward records resolve, first on **2026-08-16**.

---

## 6. H5 — the notional sweep, and the one hypothesis that broke

Excess CAGR %/yr, base profile, with the **declared** square-root impact model
(C = 1.0, never fitted) and whole-share rounding at $10k and $40k.

| system | $10,000 | $40,000 | $100,000 | $1,000,000 |
|---|---:|---:|---:|---:|
| `P2_equal_weight_all` | **−9.75** | −4.98 | **−1.06** | **−1.08** |
| `P3_random` | −9.87 | −10.12 | −10.48 | −12.31 |
| `P4_volmatched_random` | −11.06 | −11.12 | −11.36 | −12.64 |
| `P5_aegis_deterministic` | −5.68 | −5.82 | −6.05 | −7.71 |
| `P9_learned_meta` | −15.86 | −16.66 | −17.15 | −18.76 |
| `P11_momentum_event` | −8.64 | −8.66 | −8.98 | −11.14 |
| `P12_revision` | −4.40 | −4.70 | −4.99 | −6.62 |
| `P13_positive_skew` | −16.35 | −17.13 | −17.76 | −19.93 |
| `P14_risk_targeted_positive_skew` | −9.27 | −9.62 | −9.87 | −11.01 |

**H5 is violated, in the direction the prereg predicted and by a mechanism it
did not.** The prediction was that $1m would break the ranking through impact.
Impact does cost the concentrated systems **1.3 to 2.2 %/yr** at $1m, exactly as
the square-root law says it should — but the ranking *inversion* happens at the
bottom, not the top. **`P2_equal_weight_all` is second-best at $100k and $1m and
sixth-worst at $10,000**, because a $10,000 book spread over 1,500 names buys
$6.67 of each and rounds to zero whole shares in almost every name, leaving the
book sitting in cash.

The practical statement: **breadth is the cheapest thing in this arena and it is
the one thing a small account cannot buy.** A $10k saver and a $1m saver are not
choosing between the same systems, and a report that quotes one number for both
is quoting a number that is wrong for at least one of them.

### Sizing sensitivity (K), never decisive

| profile | `P5_aegis` | `P11_momentum` | `P12_revision` | `P13_skew` | `P3_random` |
|---|---:|---:|---:|---:|---:|
| conservative K=40 | −5.21 | −9.19 | −4.21 | −13.85 | −8.95 |
| **base K=20** | −5.17 | −7.76 | −4.12 | −16.52 | −9.48 |
| concentrated K=10 | −2.33 | −10.11 | −5.91 | −16.16 | −8.35 |

The spread across budgets is 0.1 to 2.9 %/yr and every one of the four
decomposition `sizing` terms is below its own MDE. **WINNER-GENOME-1 found the
position budget dominant; this arena cannot see it at n = 263 months**, and the
two statements are compatible — WG1's instrument sampled thousands of teams per
window and this one runs one path per configuration.

---

## 7. Search denominator

Every configuration executed, including the ones that failed.

| stage | configurations | note |
|---|---:|---|
| panel build | 1 | 263 dates × 1,500 names, delisting spliced |
| no-lookahead perturbation | 1 | **PASS**, 13/13 feature columns + 40/40 snapshots bit-identical |
| learned meta-model fits | 8 | 4 purged walk-forward folds × 2 arenas |
| full arena, raw | 11 | 9 systems + 2 index funds |
| full arena, matched | 27 | 9 × (beta, vol, turnover) |
| full arena, cost sensitivity | 27 | 9 × (0×, 1×, 2×) |
| full arena, notional sweep | 36 | 9 × 4 notionals |
| full arena, profile sensitivity | 10 | 5 systems × 2 non-primary profiles |
| full arena, vs random (net) | 8 | |
| full arena, vs random (gross) | 14 | |
| full arena, CAPM fits | 11 | |
| sub-arena, all of the above | 144 | identical machinery on the 40-name set |
| A10 decomposition | 25 | 4 systems × 6 configurations + 1 shared control |
| **total** | **323** | 0 skipped, 0 voided, 0 dropped |

**Declared non-runs**, recorded rather than omitted:

- **P10 evolutionary survivor** — chunk 8 has not run. There is no survivor.
- **P6/P7/P8 in the FULL arena** — the LLM panel covers 40 names on 119 dates,
  not 1,500 on 263. They are run in the sub-arena and the ablation, on the set
  where the comparison is fair.

### 7.1 Reproduction check — every chunk-7 artefact re-derived from the committed code

**A fix that landed but whose dependants were not re-run is worse than no fix,
because the numbers look repaired.** So the claim in defect 1 was not taken from
its own commit message. Every artefact this chunk reports was regenerated from
scratch by the code as committed, and compared byte-for-byte:

| command | artefact | result |
|---|---|---|
| `python -m scripts.run_portfolio_arena_1` | `portfolio_arena_1_full.json` | **IDENTICAL** (76,566 bytes of canonicalised JSON, `wall_seconds` excluded) |
| `python -m scripts.run_portfolio_arena_1 --sub` | `portfolio_arena_1_sub.json` | **IDENTICAL** (76,183 bytes) |
| `python -m scripts.arena_decompose` | `arena_decomposition.json` | **IDENTICAL** |
| `python -m scripts.arena_tables` | `arena_tables.md` | **IDENTICAL** (`diff` clean) |

Every beta-matched cell reproduces to the last printed digit — `P5_aegis`
−4.58 %/yr at 1.321× gross, `P3_random` −9.25 at 0.865×, `P13_positive_skew`
−12.82 at 0.707× — and no book is levered anywhere near the 1.4-2.0× that was
the bug's signature. **The fix was in the working tree before the arena ran.
The artefacts on disk, the numbers in this document and the code in `357fef9`
are one consistent object.**

What the check does *not* establish: it re-derives the arena from the same
frozen panel (`arena_panel.parquet`, `arena_market.parquet`, `exit_lab_1_aux.npz`,
all unmodified since 19:39), so it proves the pipeline from panel to verdict is
reproducible and unaffected by the defect. It does not re-derive the panel.

### What went wrong, recorded rather than tidied away

1. **The ex-ante beta was computed from a doubly-differenced market series.**
   `load_lc` returned the daily log-return series where `exante` expected the
   cumulative one, so the beta-matching overlay levered long-only equity books
   to **1.4–2.0× gross** and reported an ex-ante beta of ~0.56 for a *random*
   20-name portfolio whose realised monthly beta is 1.20. Caught by the absurd
   gross-exposure column, fixed, and the whole arena and decomposition rerun.
   Volatility matching was unaffected (it never touched the market series) and
   its numbers are unchanged.

   **Independently re-verified 2026-08-12 22:0x — see §7.1.** The session that
   found this defect died to an API stall immediately after committing the fix,
   with its last words *"fixing and rerunning"*. Whether the rerun actually
   happened could not be read off the commit: the fix commit `357fef9` is
   stamped **20:14:45** and the arena artefacts were written at **20:05-20:07**,
   nine minutes EARLIER, which reads exactly like a fix whose dependants were
   never re-run. That reading is wrong, and the commit clock is why — it records
   when the change was committed, not when the file was edited.

2. **Effective N was computed on unnormalised weights**, so a vol-matched sleeve
   at scale 0.47 printed "effective 106.7 names" for a 20-name portfolio. Fixed
   to normalise to the stock sleeve; the arena was rerun.
3. **FF12 is zero-indexed**, and a one-indexed read labelled an air-ambulance
   operator "Finance" in the LLM snapshot smoke run — a wrong label a language
   model would have reasoned from happily. Fixed before the panel run.
4. **A smoke run lost 24 of 24 calls to a missing positional argument** and the
   counter reported them as vendor failures. The `except Exception` that
   swallowed it now prints every distinct exception once and counts them by
   type. **A harness bug must never be allowed to wear the costume of flaky
   infrastructure.**
5. **QQQ was not in the ETF price spine.** Fetched from EODHD (1999-03-10
   onward) rather than proxied, and stamped.

Nothing was dropped for being unflattering. The positive-skew systems were
pre-declared to lose and are reported at full length; the `P9_learned_meta` arm
was kept despite a 22.58 %/yr ruler that makes every one of its verdicts
UNRESOLVED by construction; the gross columns were kept even though they remove
the cost story; and all fourteen ranked-versus-random contrasts are printed,
including the eight with positive point estimates that would have been easy to
quote without their MDEs.

---

## 8. What this cannot tell us

Read this before quoting any number above.

1. **This is a direction check on simulated portfolios. It is not alpha
   evidence, not a Sharpe claim, not a skill claim, and it promotes nothing.**
   No lane, position size, product default or buy/sell surface changes because
   of it.
2. **Under Amendment A7, 2002-2024 is not a pristine holdout.** This programme
   has interrogated it across many nights. Certification comes from genuinely
   untouched data or the forward paper tournament, and this arena is
   development and secondary validation only.
3. **A null is a null on THESE fifteen systems.** Fourteen ranked-versus-random
   contrasts came back NOT DETECTABLE with rulers 5 to 22 %/yr wide. None of
   these rankings is *refuted*; each is below the resolution of an instrument
   running one path per configuration at n = 263 months. **A better ranker, a
   finer decision grid, or a longer sample could still find something, and the
   MDE beside each number says exactly how large it would have to be.**
4. **Monthly decisions only.** Nothing here sees intraday execution, and a null
   on selection is not a null on execution — the gap NIGHT-14 recorded and this
   arena inherits unchanged.
5. **The eligible set is liquid by construction** (price ≥ $5, ≥ $1m median
   dollar volume, top 1,500). None of these numbers transfers to a micro-cap or
   illiquid book, and the impact term is a **declared** model, not a measured
   one.
6. **The `P5_aegis_deterministic` result is a result about 54.3% of the shipping
   signal stack.** The other 45.7% by declared weight has no point-in-time input
   on this spine. Whatever P5 did here, the deployed composite could do
   something else.
7. **The sub-arena's levels are not investable**, because its universe is redrawn
   every month by design. Only its paired differences and its gross column mean
   anything, and the ablation uses only those.
8. **`timing` and `LLM` are absent from the A10 table on purpose.** Timing is
   chunk 6's instrument; the LLM term is `GRAND_ARENA_ABLATION.md`, and under
   Amendment A6 it is `ARCHITECTURE_RESULT_ONLY` whichever way it comes out.
9. **Below-MDE is never a kill.** Of the 24 decomposition terms, 16 came back
   NOT DETECTABLE. That is a statement about this ruler, not about those
   mechanisms.
