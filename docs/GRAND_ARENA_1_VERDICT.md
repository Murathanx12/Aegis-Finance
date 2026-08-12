# GRAND-ARENA-1 — VERDICT

**Written 2026-08-12.** Governed by `GRAND_ARENA_1_PLAN.md` and, from chunk 4
onward, `GRAND_ARENA_1_AMENDMENT_A.md` (frozen after chunks 0–3, before any
result below was seen).

This document answers the question the campaign was built for:

> What actually adds predictive/portfolio value, what is only explanation, what
> is overfit, and what architecture deserves to become Optimus?

Every number is printed beside **its own 80%-power MDE**. Under §19, a number
inside its MDE is **not detectable** — it is not a kill, and it is not a result
in the other direction either. That distinction does most of the work here.

---

## 1. The one-paragraph answer

**Nothing tested in this campaign earned the right to change what a portfolio
does.** Across six independent instruments — exposure control, regime
conditioning, exit/replacement policy, portfolio construction, the LLM ablation
and the market graph — **one** hypothesis cleared its pre-registered bar with
its placebos intact, and it is about **co-movement structure**, not about
returns. The LLM's licensed role is unchanged and now measured rather than
assumed: `PRESENTATION_AND_RESEARCH_ASSISTANCE`. **No breakthrough is awarded
under A11.**

---

## 2. A10 — the decomposition, each number beside its own MDE

| component | best measured effect | MDE | reading |
|---|---|---|---|
| **exposure** | frontier **monotone increasing in mean exposure** on all 3 beds, 98 yrs; no interior optimum | — | the largest real effect in the campaign, and it is *how much*, not *when* |
| **timing** | oracle **+21.563 pp/yr** over matched | 2.07 (10.4×) | information EXISTS; best observable controller captured **7.4%** |
| **timing (observable)** | 42/45 configs (BED-1), 44/45 (BED-3) inside MDE | various | **not detectable**; 29 arms labelled `DE_RISKING_ONLY` |
| **selection** | oracle through selection **+13.179** | 20.6 (**0.64×**) | the *oracle itself* is not detectable — less is there to find |
| **selection (mechanisms)** | `SELL_BENCH − HOLD` = −0.04 pp @60d, −0.14 @252d | — | EXIT-LAB, 25.3M state-action rows |
| **sizing** | vol-target / ladder / regime cut 98-yr drawdown **14–27 pp** beyond matched | above own MDEs | the one place simple rules buy something real |
| **execution / management** | 20 rules, 6 learned policies, 16 single actions: **every point estimate negative** | several detectable | best out-of-fold baseline is `NEVER_SELL` |
| **LLM** | Full − no_llm **+3.37 %/yr**; shuffled − no_llm **+1.37** | p=0.105 → **0.185** | ~**40%** of the apparent contribution reproduced by *permuted noise* |
| **LLM (structure)** | market graph ΔR² **+0.000968** | 0.000623 (**t=4.35**) | **the campaign's only clean positive** |
| **beta/style** | chunk 5's one detectable arm dissolved on beta-matching (−7.364 → −3.130 [3.951]) | — | A3 earned its place |
| **costs** | LightGBM controller: 19.6×/yr turnover, **592 bps/yr**, −4.09 pp vs matched | — | learned policies pay for their cleverness |

---

## 3. What survived

### MARKET-GRAPH-1 H1 — the only hypothesis to clear its bar with placebos intact

LLM-extracted economic relationships carry co-movement information the trailing
correlation matrix does not already have.

- **ΔR² +0.000968 vs MDE 0.000623 (t = 4.35)**, baseline OOS R² 0.126
- **10.8%** of baseline squared error removed on edge-carrying pairs (MDE 5.8%)
- degree- and confidence-preserving placebo carries **nothing** (t = −0.22)
- matched-density random edges carry nothing
- survives same-sector exclusion **and** a cross-2-digit-SIC arm ⇒ **not a sector
  dummy in disguise**

**What it is not.** It predicts *how securities move together*, not *which one
to own*. It is historical, `ARCHITECTURE_RESULT_ONLY`, and uncertified under A7.
It is a risk-model result, and the honest next question is whether a better
covariance structure survives into portfolio outcomes — which this campaign has
not tested.

---

## 4. What was refused, and why the refusals matter more than the null

### H2 of the market graph — refused at 89% of its own bar

`semantic YES / numeric NO` posted **+5.98 pp vs MDE 2.48 (t = 6.76)** and
survived four of five controls. The prereg made it conditional on the fifth: the
**reversed-direction asymmetry** came in at **+0.00361 against MDE 0.00407** —
right sign, 89% of the bar, **not detectable**. **NOT ADOPTED.**

The graph found co-movement; nothing distinguishes it from causation. Under §19
the near-miss is not a kill either — the question stays open rather than closed
in our favour.

### The LLM ablation — the decisive arm is a coin flip

**H2 (chunk 9).** Full = −2.97 %/yr. Its own scores **permuted across
ticker/date** = −5.73 %/yr, and the observed value sits *inside* that
distribution: **p = 0.105 raw, 0.125 beta-matched, 0.145 vol-matched, 0.185
leakage-clean.**

Full − no_llm is +3.37; **shuffled − no_llm is +1.37**. Roughly **40% of the
apparent LLM contribution is reproduced by noise carrying the identical score
distribution.** That is precisely what A4 predicted the shuffled arm would
expose, and it is why "random text" alone was never sufficient.

**H3 — the specialist architecture does not justify itself.**
`swarm − generic = −0.60 [MDE 9.69]`, point estimate negative, and
**`llm_only_generic` is the best arm in the family by Sharpe.** Effective
distinct ideas: **0.49 (fourteen specialists) vs 0.85 (one generic agent)** — at
**5.2× the calls**. One agent is *more* informationally diverse per call than the
swarm.

That is an independent confirmation, from portfolio outcomes rather than from
prompt statistics, of the 0.2996 / 0.059 measurement that opened the night.

---

## 5. Instrument findings — the reusable ones

These outlive their trials.

1. **A permuted-label placebo is not centred on zero.** Chunk 5: a *random*
   partition of the trailing window (same marginals, same persistence, alignment
   destroyed, no information) is **−7.024 pp/yr in the selection family, 7/7
   blocks, 0/20 seeds positive — detectably negative**; **+2.008** with 20/20
   seeds positive in the risk-model family. Conditioning changes the answer
   *mechanically* by shortening the estimation window, and that effect is larger
   than every real state's effect in two of three families. **Any conditioned
   rule evaluated without a permuted-label placebo will read this as a
   discovery.**
2. **Matched-average-exposure is non-negotiable.** WORLD-L invented a timing
   edge in a world containing none by sitting at zero exposure 52% of the time.
   On real data, 29 arms were labelled `DE_RISKING_ONLY`.
3. **Reading a file that is still being appended to changes a sign.** Chunk 9's
   H3 went **+3.69 → −0.60** between a live read and a frozen snapshot.
4. **An arm can wear two names.** `no_quant ≡ llm_only_swarm` — counted twice in
   a 13-arm ladder until a family check found it. §20: **13 arms = 1.77
   effective.**
5. **Correlated beds count once.** The chunk 6 breakthrough clause counted one
   bed twice; replacing it with a measured independence check (excess-return
   correlation **1.000000**) **flipped the answer from true to false**.
6. **Leakage is concentrated, not uniform.** The recall canary is live — 7/10
   YES, **7/7 correct direction** on famous moves — and returns 0/419 on ordinary
   securities on ordinary dates. Masking: **0/399** ticker recoveries, 0 years
   named. **But the famous-month control refuses the easy reading**: on those
   months the `no_llm` arm gains 0.021 IC and random-text gains 0.085. Famous
   months are easier for *everything*. Flagged, not excluded.
7. **A commit timestamp is not an edit timestamp.** Chunk 7's artefacts predate
   their fix's commit by nine minutes and look exactly like the "fix landed,
   dependants never re-run" failure. They aren't — established by re-running from
   the code as committed and getting **byte-identical** artefacts.

---

## 6. A11 — the breakthrough test, applied

Pre-declared, so the word could not be awarded retroactively. At least one of:

| # | criterion | outcome |
|---|---|---|
| 1 | LLM value surviving risk matching AND the shuffled-LLM placebo | **NO** — p = 0.105 → 0.185; 40% reproduced by noise |
| 2 | exit/replacement policy surviving multiple unseen periods | **NO** — every point estimate negative; `NEVER_SELL` wins |
| 3 | exposure timing beating matched-average-exposure static sizing | **NO** — `breakthrough_eligible: false`, computed mechanically |
| 4 | a regime-conditioned improvement that replicates | **NO** — 35/36 inside MDE; the one exception negative and beta-explained |
| 5 | a selection mechanism surviving independent data plus costs | **NO** — the selection *oracle* is at 0.64× its MDE |

**No breakthrough.** One spectacular backtest was explicitly declared
insufficient in advance, and none was produced anyway.

---

## 7. Deflation — the number that keeps this honest

- Chunk 6: **207 scored policies**; 47 configs per bed worth **2.02–2.40**
  effective distinct arms.
- Chunk 5: 84 scored arms, **408 simulations**; 36 arms worth **5.60** effective;
  **PBO 0.257 / 0.271**; **family DSR break-even N = 5 against 5.60 effective
  arms in this trial alone** — the best arm does not survive its own trial's
  search.
- Chunk 9: **DSR 0.29 / 0.53 / 0.11** at three denominators, threshold 0.95.

Deflation is cumulative across every trial ever registered. Nothing above was
deflated *only* against its own chunk.

---

## 8. What did NOT run — stated, not implied

A check that did not run is not a check that passed.

- **Chunk 8 (evolution / genome search)** — not run.
- **Chunk 10 (protected evaluation)** — not run. Under A7 there is no pristine
  historical holdout left; certification must come from forward paper evidence.
- **Chunk 11 (forward tournament)** — not run.
- **LLM-ARCHITECTURE-ARENA-1** — **in progress.** Its historical run halted
  itself at **55% coverage (16,426 of 29,730 calls)** on `estimated spend $40.00
  >= $40.00` — a ceiling computed from the **stale price table**, which
  overstated cost 2.8×. True spend at that moment was **$12.57**. The fix landed
  an hour after the process loaded the old code. Resumed; **this verdict will be
  revised when it completes.**
- Chunk 9 gaps: A3 matching on the nine secondary arms; PBO/CSCV (n=119 against
  an effective family of 1.77 yields a number, not a diagnostic); §18 SE on the
  famous-month difference-of-differences; **the random-text arm is only 13.6%
  covered**, 86% neutral-filled.
- Chunk 5 gaps: no second bed, no impact model, no CPCV beyond CSCV, A3 matching
  on K=20 only.
- Market graph: the exact-only matcher was never re-graded end to end (worth 5.9%
  of edges) — unmeasured, not passed.

---

## 9. Consequences for the roadmap

1. **The bet is settled in one direction and open in the other.** *The losses are
   in management* — supported by three independent instruments. *The edge is in
   selection* — **no tested mechanism has produced a product-level advantage**,
   and chunk 5 now adds that the selection *oracle* is itself undetectable. Per
   A0 that is still not "selection does not matter"; it is a narrower and better
   supported claim than the one this programme started with.
2. **Stop buying diversity by adding personas.** Two independent measurements
   agree: 0.2996 effective-distinct from prompt statistics, and 0.49 vs 0.85
   from portfolio outcomes at 5.2× the calls.
3. **The graph is the live lead.** It is the only clean positive, and it is a
   *risk-model* result. The next question is whether a better covariance
   structure survives into portfolio outcomes — a question this campaign did not
   ask.
4. **Certification is forward-only.** ABLATION-FWD is `STATED_EMPTY` until
   **2026-08-16**. Nothing here may set a specialist weight, a lane, or a
   position size (A5, A6, A7).

---

## 10. Standing rules, unchanged

§19 · §20 · §18 · deflation cumulative · fabrication and outcome-shopping
refused · a check that did not run is not a check that passed · **a refusal is a
finding**.
