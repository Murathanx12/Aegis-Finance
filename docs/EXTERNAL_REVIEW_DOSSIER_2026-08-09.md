# AEGIS — EXTERNAL REVIEW DOSSIER
### Everything built, everything measured, everything still open — and an invitation to attack it
**Compiled 2026-08-09. Self-contained: an AI with no repo access can engage with all of it.**

---

## 0. How to use this document

Sections 1-9 are the briefing. **Section 10 is the prompt to paste into another
AI** (ChatGPT, Gemini, Grok, Claude, DeepSeek — ideally several, separately, so
their answers stay independent). Section 11 lists what we specifically want back.

Two things to hold onto while reading:

1. **Almost everything here is a negative result.** That is the point, not an
   apology. 35 documented dead ends, 83 registered trials, and exactly one
   strategy that has ever cleared the full gate ladder — and even that one is
   labelled "retrospective" and has not graduated.
2. **The system is designed to stop us fooling ourselves, and it keeps
   succeeding at that.** The most valuable finding of the most recent night was
   that our own best-looking result was an artifact, caught by a control we
   registered specifically to kill it.

---

## 1. The repositories

| repo | URL | what lives there |
|---|---|---|
| **Aegis module** (the research engine) | `https://github.com/Murathanx12/investing-test-module` | the survivorship-free panel harness, the strategy factory, the belief network, the trial registry, all campaign verdicts |
| **Aegis Finance** (the product) | `https://github.com/Murathanx12/Aegis-Finance` | Next.js + FastAPI web platform, ~130 API endpoints, ~100 service modules, the execution standard and design docs |

*(Private repos. Everything an external reviewer needs is reproduced in this
document; nothing below depends on repo access.)*

**Key files, by name**, if a reviewer is given access:

- `Aegis module/TRIALS/registry.jsonl` — 83 pre-registered trials, append-only,
  each with hypothesis / expected effect / kill condition / UTC timestamp.
- `Aegis module/docs/PF1_CAMPAIGN_VERDICT_2026-08-08.md`,
  `PF2_CAMPAIGN_VERDICT_2026-08-09.md`, `NIGHT3_VERDICT_2026-08-09.md` — the
  three most recent campaign verdicts.
- `Aegis module/docs/AMNESIA_VERDICT_2026-08-08.md` — the LLM contamination
  measurement programme.
- `aegis-finance/docs/EXECUTION_STANDARD_2026-08-08.md` (+ two 2026-08-09
  amendments) — the frozen rule that decides what may be believed.
- `aegis-finance/docs/CANON.md` — non-negotiable guardrails.
- `aegis-finance/NEGATIVE_RESULTS.md` — 35 numbered dead ends with receipts.

---

## 2. Who is doing this and what they asked for

**Murathan** — HKU freshman, robotics and quant. Aegis is simultaneously a
portfolio tool, a research programme, and an intended paper. He is not an
institution; the compute budget is a laptop, a DeepSeek API key, and a WRDS
academic subscription.

### 2.1 The standing brief, in his own words

> *"Don't focus on my portfolio — create winning portfolios, engine chooses
> stocks, create scenarios test them, full freedom."*

> *"I want to make even more profits yearly using the LLM and the engine…
> we just have to win with bigger margins where the user can just copy the
> strategy for their own portfolio."*

> *"Get the data from that time, change the names as we did and ask what it
> thinks, based on the results we can learn what happened vs what we imagined.
> From this we can create a reasoning context brain/MCP for the LLM. I think
> using this for the backtest would be revolutionary. We need to come up with
> workarounds like this."*

> *"If we can turn that into an actual thinking engine, a reasoning engine that
> learns from mistakes and what worked, we can create weights, use kNN or other
> data science methods to create a brain similar to a NN or a CNN."*

> *"Sometimes LLMs have noise and they give different answers to same question.
> I would want it to be consistent — see what it said before (per instance, not
> overall)."*

> *"There can be 1 paper account that just does what worked on 10 different
> accounts and just uses the winning strategies."*

> *"Is this novel? … once we do a novel approach our ROI-maximizing goal will be
> closer, since if it was already known it wouldn't work."*

### 2.2 What that decomposes into

1. **A portfolio factory** — the engine generates candidate strategies, tests
   them honestly, and publishes ones a retail user could copy.
2. **An LLM reasoning brain** — masked historical replay, graded
   expected-vs-actual, retrievable lessons, model-agnostic.
3. **A meta-account** — one paper lane that copies whatever is working.
4. **Consistency** — the LLM must not contradict itself.
5. **Novelty** — because a known edge is an arbitraged edge.

**Every one of those five has now been tested. Results in §5.**

---

## 3. What exists — the system as built

### 3.1 Data spine (this is the part most retail projects get wrong)

- **63-year survivorship-free CRSP monthly panel**, stitched from two certified
  panels: `1962-2001` (20,902 permnos) and `2002-2024` (11,098 permnos), with
  **real delisting returns** flowing through. A held name whose return goes NaN
  is force-liquidated to cash and the count is reported — dropping it silently
  would re-import survivorship bias.
- **Benchmark:** "beat the S&P" over 63 years cannot be measured against SPY —
  SPY starts in 1993. The benchmark is the **CRSP value-weighted total return**
  (Kenneth French `mktrf + rf`, pinned vintage), which is the index SPY tracks.
- **Point-in-time source hierarchy** (binding):
  `CRSP > SEC EDGAR > FDA > GDELT > Bigdata > FMP > yfinance`, and
  **yfinance is forbidden for any money claim** — measured basis: it recovers
  **1 of 20** delisted S&P names.
- Compustat/CCM fundamentals, OSAP signal library, WRDS BoardEx, Form 4 insider
  data, FRED macro.
- **Cost model:** Kyle-Obizhaeva measured half-spreads, or a flat 25 bps, charged
  on traded value.

### 3.2 The strategy factory

A frozen `StrategySpec` (universe, signal weights, top-N, weighting, rebalance
schedule, cost model, benchmark, dates, seed) hashes to an ID. That hash is
registered **before** the run. Output is a full scorecard: CAGR, excess, max
drawdown, Sharpe/Sortino/Calmar, turnover, costs, exposure, concentration, time
underwater, terminal-wealth distribution, per-regime blocks, ruin probability
via paired stationary block bootstrap, FF5+UMD and CAPM factor regressions, and
a **turnover-matched random-selection placebo band** (≥100 seeded draws).

Write-once artifacts: re-running a spec you already ran is a no-op or a new spec.

### 3.3 The belief network (`aegis_brain/abn/`)

- **Hash-chained claim ledger** — a silently edited history fails verification.
- **One write path only:** a posterior can be updated by a `Resolution`, and a
  `Resolution` can only be constructed from an observed outcome. **P&L may read
  beliefs and brake exposure; it may never write one.** This is enforced as a
  *type check* with a test named `test_pnl_cannot_write_a_belief`.
- **Outcome embargo** (a claim's resolution is invisible until it has realized)
  and **ticker-blind retrieval** by default.
- Two-timescale posteriors, Platt calibration α=√3, **effective-n deflation for
  cohort correlation**, and a promotion gate anchored at t ≈ 4.0 that
  **refuses retrospective evidence by construction**.

### 3.4 The forward ledger

**10 paper lanes, inception 2026-06-08.** No skill claims before 24 months
regardless of what interim numbers say. Nothing seeds a lane except through the
frozen graduation gates. The live product is a Next.js/FastAPI web app.

### 3.5 The execution standard — the gate ladder

Stage ladder: `research → backtest → LLM-replay → daily-sim → paper → capital`.

| gate | requirement |
|---|---|
| G1 | net excess CAGR ≥ +3 %/yr over the benchmark |
| G2 | **holdout** — 2023-01..2024-12, one attended read, failure final |
| G3 | beats the turnover-matched random-selection placebo band |
| G4 | beats the equal-weight-universe control |
| **G4a** | **FF5+UMD alpha ≥ +2 %/yr at t ≥ 2.0** — required for any *skill* claim |
| G5 | grid stability — the variation grid is positive, not one lucky cell |
| G6 | not driven by a single best year |
| G7 | survives a **sequential daily simulator** with production timing |
| G8 | ruin constraint: P(max drawdown > 60 %) ≤ 0.20 |
| G9 | regime breadth — positive excess in ≥4 of 5 evaluable regime blocks |

Ranking is by **excess terminal wealth under a ruin constraint — never
Sharpe-maximization**. Verdicts: `WINNER` / `NEAR-MISS(gate)` /
`UNRESOLVED(reason)` / `FAILED`. **Unresolved ≠ dead.**

**Two tracks (added 2026-08-09):** *engine-skill* (G4a and regime breadth
gating) versus *factor-harvest product* (product bar gating, regime breadth as
mandatory disclosure, and the word "alpha" permanently prohibited).

---

## 4. The methodology — the part we think is actually novel

The strategies are mostly known. **The measurement apparatus may not be.** Nine
practices, all enforced by code rather than intention:

1. **Pre-registration before compute, with the git commit timestamp as tamper
   evidence.** Hypothesis, the single deciding metric, the adopt/reject
   threshold, the frozen parameters, and the kill condition — all committed
   before the first number exists. Metric substitution is forbidden; everything
   not named as deciding is "reported, never deciding."
2. **Registered predictions, scored publicly, including the misses.** Recent
   records: PF-1 **2/5**, PF-2 **4½/8**, NIGHT-3 **5/7**. Several predictions
   were deliberately written *against our own candidates*.
3. **The multiple-testing denominator is printed on every campaign.** PF-1: 648
   experiments. PF-2: 342. NIGHT-3: 406 graded LLM calls, 16,320 graded
   decisions. A registry showing only adoptions is lying to itself.
4. **Controls are gates, not diagnostics.** A candidate that beats the market
   but not its turnover-matched random-selection placebo is dead, not
   "interesting."
5. **Power analysis before interpretation.** Report the **minimum detectable
   effect** so a null reads as "smaller than X", never "zero".
6. **Adversarial self-attack on our own best result.** When an arm looks good,
   we register a control designed to kill it *before* running it.
7. **A holdout the code physically refuses to read**, plus a verification script
   that scans every artifact and every cached prompt and exits non-zero on
   violation.
8. **Contamination is measured, not assumed.** See §5.4.
9. **The LLM never grades itself.** Attribution enums are computed by engine
   code. No posterior touches a position size.

---

## 5. What has actually been measured

### 5.1 The one strategy that cleared every gate — and why it still hasn't graduated

**`PF-PROF-COMPOSITE-150`** — three profitability signals (gross profitability,
operating profitability incl. R&D, cash-based operating profitability),
equal-weight, 150 small-cap names, monthly rebalance, 25 bps, 1982-11 → 2022-12
(40.2 years):

| metric | value |
|---|---|
| net excess CAGR vs CRSP VW | **+4.67 %/yr** (t 2.85, Newey-West 2.52) |
| regime blocks positive | **5 of 5** |
| P(max drawdown > 60 %) | 0.102 |
| grid configurations positive | 8 of 8 |
| first half / second half | +5.00 % / +4.33 % |
| turnover-matched placebo | **all 100 random books negative** (best −0.77 %) |
| **FF5+UMD alpha** | **+5.01 %/yr, t = 3.39** |
| RMW (profitability factor) loading | **0.135** |

That last row is the mechanism: a book built *entirely* from profitability
signals barely loads on the published profitability factor, because RMW is
value-weighted and large-cap-dominated while this book is equal-weighted small
caps. **The small-cap profitability premium is not spanned by RMW.**

**It is labelled RETROSPECTIVE and does not graduate**, because the deciding
factor-alpha number already existed on disk in an earlier campaign's grid card.
The only evidence we did not peek is that the registered prediction said it
would **fail** that gate. The holdout and the daily simulator have not run.

*Honest framing: this is a known effect (Novy-Marx 2013; Asness et al. on
quality in small caps), independently rediscovered by a blind pipeline. The
value is not the discovery — it is that the instrument found the real thing and
correctly rejected five look-alikes around it.*

### 5.2 The membership-vs-ordering result (2026-08-09) — the most useful thing we know

Inside the engine's own top-40 profitability slate, **sorting by the composite is
worth +1.46 %/yr at t = 0.43.** Nothing. A stratified slate spanning all five
composite quintiles is *worse* (t = 0.15).

Independently corroborated by the already-banked concentration grid:

| names held (small-cap) | 10 | 25 | 50 | 100 | 150 | 200 |
|---|---|---|---|---|---|---|
| net excess CAGR | +4.46 % | +4.35 % | +4.71 % | +4.36 % | +4.67 % | +3.87 % |
| Newey-West t | 1.92 | 2.00 | 2.30 | 2.36 | 2.52 | 2.34 |

**Flat return, monotonically rising t-stat.** If ordering carried information,
deepening from 10 to 150 names would progressively add worse names and returns
would fall. They don't.

> **The edge is MEMBERSHIP — which ~150 names out of ~2,000 — not ORDERING.**

Consequences: concentration adds risk without return; the margin levers are
universe, depth and cost, not better picking. Same signal pays **+4.67 %** in
small caps, **+2.29 %** all-cap, **+1.56 %** large/mid.

### 5.3 What is dead, with receipts

- **Market timing.** Regime-switching destroyed 3.34 %/yr. Conditional
  volatility targeting: the 2020 crash outran the signal. Timing has now failed
  every test we have run.
- **Conviction / concentration.** A 10-name high-conviction book returned
  −2.25 %/yr at **P(drawdown > 60 %) = 0.994**.
- **Strategy-level timing (the "11th account").** Copying whichever strategy has
  been winning returned **6.63×** against **7.18×** for simply equal-weighting
  the same six strategies, at **six times the ruin probability** (0.604 vs
  0.097) and 164 switches vs 3. Switching costs alone took 1.6 %/yr.
- **Insider signals.** Closed after a construction defect was found *and fixed*
  (the old signal had 14 distinct values in its top 100, so 86 names were chosen
  by arbitrary tie-break; the fix gave 100/100) — and the signal was still dead:
  −5.16 %/yr, beaten by 71 of 100 random books.
- **Core-satellite blending as a regime fix.** Proven impossible arithmetically:
  blended excess = (1 − X) × strategy excess, so a constant blend scales every
  regime block and **preserves its sign**. Eight backtests were run before one
  line of algebra was noticed. Recorded against ourselves.
- **Residualisation** (three separate receipts): subtracting a factor from a
  signal removed information rather than noise.
- **The crash model's offline performance** was inflated by two leaks; fixed, it
  has no skill at any horizon.
- **72-month confirmation windows are structurally underpowered** — the minimum
  detectable effect is ~0.6 annualized Sharpe, and SPY itself only prints t ≈ 1.1
  over 72 months.
- 35 numbered dead ends in total.

### 5.4 The LLM programme — measured, not assumed

**Contamination (1,080 DeepSeek calls, "AMNESIA"):**
- Instructing a model to "not use knowledge after this date" does **nothing**
  (15.8 % recall vs 15.8 %).
- Masking works: **0 identifications out of 240**.
- **Synthetic scenarios ≈ masked scenarios** (ΔBrier 0.0004) ⇒ manufacturing
  scenarios from the panel is a validated, unlimited instrument.
- Memory is sparse but near-perfect where it fires (declines 95.8 % of the time;
  5/5 correct where it answers, all famous collapses) ⇒ **aggregate metrics hide
  contamination; canaries must gate per case.**

**Decision replay (2026-08-09, 204 months, 16,320 graded decisions):** at each
month the engine emits a masked 40-name slate; the LLM and the engine see the
*same* percentile facts (the composite's rank is withheld) and each pick 20.

| arm | net excess CAGR | Newey-West t |
|---|---|---|
| engine composite top-20 | +3.64 % | 1.34 |
| equal-weight all 40 | +3.32 % | 1.54 |
| LLM, no memory | +4.67 % | 2.30 |
| LLM + episodic kNN memory | **+6.21 %** | **2.58** |

That bottom row beat 99 of 100 recosted random books and was the best number in
the campaign. **It does not count**, for two reasons we made ourselves confront:

1. Those t-stats are against the benchmark, and *every* arm — including the
   placebo — carries the same small-cap profitability premium. The **paired**
   difference is what isolates the LLM: **t = 0.04** (LLM vs engine) and
   **t = 0.93** (memory vs no-memory). Both **REJECT**.
2. **A registered control killed it.** An arm receiving memory of identical
   shape, volume and marginal distribution — with *only the situation→outcome
   mapping destroyed* by a seeded permutation — printed **+5.07 %/yr, still
   above no-memory's +4.67 %**. Real-minus-scrambled: **t = 0.43**.
   **What helped was the memory *block*, not its *content*.**

**Other measured LLM facts:**
- **Consistency:** at temperature 0, 96.5 % of per-name decisions repeat on an
  identical re-ask; **at temperature 0.7, 21.6 % flip.** 3.5 % non-determinism
  survives even at temperature 0.
- **Self-report is not evidence:** the model's *stated* belief update
  ("STRENGTHEN"/"WEAKEN") disagrees with its own *measured* conviction change
  **37 %** of the time.
- **Coherence:** across 500 single-variable perturbation pairs the model made
  **0 wrong-direction calls** — but tied 115 of them. Asking in **basis points**
  instead of decimals cut ties to 35 and took the battery from 3/5 to 5/5
  directions passing. *Its logic was never broken; its numeric resolution was.*
- **Contamination ceiling:** given only a real ticker and date and **no data**,
  the model **refused 120/120 times**. Forced to answer, it scored AUC 0.571 —
  *above every full-information arm* — but with a bootstrap CI of
  **[0.481, 0.656]**. Everything in that comparison is within noise of a coin
  flip.
- **Calibration at scale (10,154 claims):** stated probability 0.13 → realized
  0.439; stated 0.85 → realized 0.489, on a 0.475 base rate. **A 5-point spread
  across the entire conviction range.** ECE 0.316 raw.
- **Orthogonality:** the LLM's ordering has mean Spearman **0.014** against the
  engine's over 204 months. It is not copying the signal. It is doing something
  else, and that something else is not better.
- **Behaviour:** on a slate selected *for profitability*, the LLM reasons mostly
  by **momentum (68 %)**. Memory shifts it toward profitability and value —
  it changes *how it thinks* without changing outcomes.

---

## 6. Answers to Murat's five asks

| ask | measured answer |
|---|---|
| Portfolio factory | **Built and calibrated.** One strategy has cleared all 8 historical gates; it has not graduated. |
| LLM picks stocks | **No.** M1 and M2 both REJECT. Route LLM attention to narration and event triage. |
| Brain that learns from mistakes | **Not demonstrated.** The memory block helped; its content did not. |
| The "11th account" that copies winners | **Inverted.** Equal-weighting all lanes beat copying the winner, at 1/6 the ruin. |
| Consistency | **Solved by architecture, not prompting** — an immutable cache keyed by (model, prompt hash) plus deterministic grading of belief updates. |
| Novelty | **The finding is known; the apparatus may not be.** See §7. |

---

## 7. Where we think novelty actually lives — and where it doesn't

**Not novel:** the small-cap profitability premium. Novy-Marx (2013), Asness et
al. on quality-in-small-caps, Fama-French. Our pipeline rediscovered it blind,
which is a reason to trust the instrument, not a discovery.

**Possibly novel, and the honest candidates for a paper:**

1. **The masked-decision-replay methodology itself** — synthetic-equals-masked
   validated at ΔBrier 0.0004, per-case canaries, immutable prompt-hash caching,
   and a memory-content placebo (shuffled situation→outcome mapping). We are not
   aware of published work that runs the memory-content control.
2. **The measurement that instruction-based "forgetting" does literally nothing**
   while masking works completely — with the corollary that *aggregate* metrics
   hide contamination because model memory is sparse and self-selecting.
3. **Membership-vs-ordering decomposition of a factor premium.** Showing that a
   factor's alpha lives in set membership and not in within-set ranking, with an
   oracle bracket bounding what any selector could achieve.
4. **A forward claim ledger for CRL/PDUFA-type biotech events** — we found *no*
   existing literature on run-up prediction for these, so our forward ledger
   would be first-mover if it accrues.
5. **The negative result itself**: a well-instrumented demonstration that an LLM
   with graded episodic memory does **not** beat a deterministic factor screen at
   monthly stock selection, with the power analysis to say how large an effect
   would have been detectable.

---

## 8. Known weaknesses — please attack these first

1. **Sample size is the binding constraint everywhere.** Minimum detectable
   effects on our paired LLM comparisons were 3.6-5.9 %/yr. We can reject big
   effects; we cannot see small ones.
2. **One model.** Nearly all LLM measurement is `deepseek-chat`. We do not know
   how much generalizes.
3. **Monthly horizon only.** Every LLM decision test used a 1-month horizon.
4. **Raw text has never been tested.** The single channel where an LLM might add
   value — reading filings — was never built. All our tests fed it *digested
   percentiles*, which is exactly where prior work says it loses.
5. **The forward ledger is 2 months old.** Inception 2026-06-08; no skill claim
   is permitted before 24 months. Everything else is backtest.
6. **Our best strategy is retrospective-labelled**, and its holdout is a
   one-shot we have deliberately not fired.
7. **The 2023-24 holdout is a mega-cap-led regime**, i.e. the worst possible
   weather for a small-cap book. An early kill is a real possibility and we know
   it in advance.
8. **Costs.** 25 bps flat on small caps over 40 years may be optimistic; the
   measured Kyle-Obizhaeva model exists but was not used everywhere.
9. **We found two of our own harness defects in one night** (an overcharged
   placebo, and persistence graded against unshown priors). Both were caught by
   re-reading our own code. **How many did we not catch?**

---

## 9. What is queued next

- **G7 — a sequential daily simulator** with production timing and idempotency,
  as the last gate before the attended holdout read.
- **Raw-text event triage** (SEC EDGAR full text) as the LLM's remaining chance.
- The product track: `PF-ENGINE-ALPHA-PRODUCT-2`, registered self-labelled
  retrospective, awaiting G7 and G2.

---

# 10. THE PROMPT — paste this into another AI

> **Copy everything from here to the end of §10 into ChatGPT / Gemini / Grok /
> DeepSeek. Paste sections 1-9 above it as context. Ask each one separately so
> their answers stay independent.**

---

**You are being asked to adversarially review and extend a quantitative finance
research programme. The full briefing is above. Read it carefully before
answering.**

I do not want encouragement. I want to find out what is wrong with this and what
we have not thought of. **Answer at length and in detail — a long, specific,
technical response is what is useful here. Short or hedged answers are not.**

Address all six parts:

**PART A — ATTACK THE EXISTING WORK.**
Find the errors. Specifically:
- Is the "membership not ordering" conclusion (§5.2) sound, or is it an artifact
  of the test design? The claim rests on a within-slate top-20-minus-bottom-20
  spread of +1.46 %/yr at t = 0.43 and on a flat concentration curve from 10 to
  150 names. What alternative explanations are there? What would falsify it?
- Is a monthly-rebalance, equal-weight, 150-name small-cap book actually
  implementable at retail scale, net of real spreads, market impact, and the
  price/liquidity floors described? At what AUM does it break?
- The FF5+UMD alpha of +5.01 %/yr with an RMW loading of 0.135 is offered as
  evidence the small-cap profitability premium is not spanned by RMW. Is that
  inference correct, or is it what you would expect mechanically from any
  equal-weighted small-cap book? What additional factor controls should we run
  (e.g. a size-matched profitability factor, an equal-weighted RMW, QMJ, BAB, or
  the Hou-Xue-Zhang q-factors)?
- The memory-content placebo (scrambled situation→outcome mapping) is our
  cleanest control. Is it actually clean, or does the permutation leak something?
- Where else in this design would you expect look-ahead, survivorship, or
  multiple-testing bias that the described guards would **not** catch?

**PART B — NOVEL METHODS WE HAVE NOT TRIED.**
Propose approaches that are **genuinely under-explored, not textbook**. The
premise is explicit: a widely-known edge is an arbitraged edge, so we are
looking for things that have not been done. For each proposal give:
mechanism, why it might work, how to test it, what the control is, how it could
fail, and roughly how much data and compute it needs. Areas we have deliberately
flagged:
- Using LLMs for backtesting via masked/synthetic scenario manufacture — the
  briefing shows this validated at ΔBrier 0.0004. What else does that unlock?
- Ways to give an LLM an edge that do **not** require it to rank stocks, given
  our measurement that its ranking is orthogonal to and no better than a factor
  screen.
- Memory / retrieval architectures beyond kNN over fingerprints that would
  survive a shuffled-content control.
- Anything that exploits **membership** rather than ordering, given §5.2.

**PART C — THE MISSING EXPERIMENT.**
What is the single most informative experiment this project has not run? Not the
most impressive — the most *informative*, meaning the one whose outcome would
most change what we do next, in either direction. Say precisely what it would
measure, what the pre-registered prediction should be, and what result would
kill it.

**PART D — IS ANY OF THIS NOVEL?**
Be blunt. For each of the five novelty candidates in §7, tell us whether it is
already in the literature, and cite specific papers where you can. If something
has been done, we want to know now rather than after writing it up. If something
genuinely has **not** been done, say which and why it matters.

**PART E — THE METHODOLOGY ITSELF.**
Critique the apparatus in §4, not the strategies. Is pre-registration with git
timestamps, printed multiple-testing denominators, turnover-matched placebos as
gates, minimum-detectable-effect reporting, and a promotion gate that refuses
retrospective evidence — is that the right machine? What is over-engineered?
What is missing? Where is it giving false comfort? Note specifically: we set an
adopt threshold *looser* than our own t-statistic requirement implied, so the
t-bar always bound. What other internal inconsistencies of that kind should we
look for?

**PART F — THE PRODUCT.**
The goal is a strategy a retail user can copy and beat the market with, by a
margin large enough to be worth the tracking error and the effort. Given that
the best-evidenced candidate is a 150-name small-cap profitability book at
roughly +4.7 %/yr excess over 40 years with a −52 % max drawdown — is that a
product? What would make it one? What would you tell a 19-year-old to actually
hold, and why?

**Constraints on your answer:** be specific and quantitative wherever possible.
Name papers, name methods, give numbers. If you think a part of this project is
wasted effort, say so directly and say what to do instead. **Do not soften
criticism.** If you are uncertain, mark the uncertainty rather than hedging the
whole answer.

---

# 11. What we want back

For each reviewer, we will extract:

1. **Falsifiable criticisms** — anything we can test becomes a registered trial
   with a pre-declared kill condition, and gets scored publicly whether it
   confirms or refutes them.
2. **Novelty adjudication** — Part D answers get cross-checked against each
   other and against the literature; anything already published gets recorded so
   we stop claiming it.
3. **The missing experiment** — Part C answers from independent reviewers get
   compared; convergence is a strong signal.

**Reviewers will disagree with each other. That is the point.** Prior rounds of
this exercise produced five external reviews that we adjudicated blind, adopted
three items from, and rejected the rest with reasons recorded. Reviews are
evidence, not instructions.
