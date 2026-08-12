# GRAND-ARENA-1 — AMENDMENT A

**Frozen 2026-08-12, after chunks 0–3, before any of chunks 4–12 runs.**

Chunks 0–3 are **not redone**. Their receipts stand exactly as committed
(`9ed42d2`, `2ce58f3`, `8429ab4`/`bb676e1`, `323eb25`). This amendment binds
everything after them. Any further change is **Amendment B, C, …**, numbered,
dated, and **incapable of retroactively reinterpreting a finished chunk**.

The reason for the freeze: we have now seen results. Rewriting primary metrics
or promotion rules after seeing them is the single easiest way to turn a
disciplined campaign into a well-documented rationalisation.

---

## A0 — A correction to the programme's own claim

I reported after EXIT-LAB-1 that *"the edge is in selection"* had **no evidence**
and that the honest claim was **exposure alone**. That over-reached, and the
correction matters because it decides whether the LLM opportunity-discovery
question is still open.

EXIT-LAB's replacement arms were **momentum/revision-ranked proxies**, and its
holders were **synthetic entry cohorts**. The report says so itself: the
momentum proxy is not claimed to be the best available candidate selector. A
null against *that* proxy is a null against *that* mechanism.

**The licensed conclusion is:**

> So far, **no tested stock-selection mechanism** has produced a large,
> reproducible, product-level advantage, while **exposure/risk has repeatedly
> produced large effects.**

**Not:** "stock selection does not matter."

The difference is not pedantry. The second version would close the LLM
opportunity-discovery question by assertion, when that question is precisely
what the remaining chunks exist to answer.

---

## A1 — Exposure/timing is the highest-priority experiment, with one mandatory control

WORLD-L already showed how this fails: the evolutionary learner produced an
apparent timing improvement (Sharpe 0.500 vs 0.478) in a world containing **no
timing edge**, purely by sitting at zero exposure 52% of the time. Only
matched-average-exposure comparison and the MDE refused it.

So every dynamic controller is compared against **all** of:
1. 100% exposure,
2. **a static policy matched on average exposure** ← non-negotiable,
3. static beta targeting,
4. static volatility targeting.

Report incremental performance **after equalising average beta/exposure**.

> **If a controller cannot beat its dumb matched-exposure cousin, it did not
> discover timing. It discovered de-risking.**

## A2 — HMM is a control, not a feature

Known-answer calibration put HMM state recovery at 58.8% against a 76.0% Bayes
ceiling, with every WORLD-C cell only PARTIAL. It does **not** enter chunk 5 as
a production instrument. Test simpler observable-state definitions, clustering
and change-point methods, and supervised strategy×state interactions beside it.
A regime model earns authority **only** by improving genuinely out-of-sample
decisions — never because its real-market labels read plausibly.

## A3 — Risk-match every portfolio and every ablation

Full Optimus vs no-LLM is meaningless if Full Optimus simply carries more beta,
concentration, gross exposure or turnover. Every comparison in chunks 7 and 9
reports **raw AND matched** on beta, volatility, gross exposure, concentration
and turnover.

Given that NIGHT-14 and EXIT-LAB both keep pointing at exposure, this is the
single most important requirement in the amendment.

## A4 — The LLM placebo ladder

"Random text" is necessary and insufficient. The full ladder, all six arms:
1. **shuffled-LLM** — preserves the exact distribution of scores/confidences,
   permuted across ticker/date. *This is the key arm:* it separates **semantic
   information** from *"adding another noisy numerical feature changed the
   portfolio."*
2. **time-shifted LLM** outputs,
3. **random-text**,
4. **one generic DeepSeek agent**,
5. **the specialist swarm**,
6. **Full Optimus**.

Arms 4 vs 5 also force the specialist architecture to justify itself, which it
must: the swarm measured the fourteen roles at a mean pairwise probability
spread of 0.059.

## A5 — No specialist reliability from unresolved records

The 20,073-record ledger is raw material, not evidence. Until outcomes resolve,
"semiconductor specialist = 0.8 reliability" is **invented authority**. Neutral
/ equal priors now; hierarchical partial-pooled updating **only** from resolved
forward records.

The contextual bandit earned the right to *route* (it recovered the
specialist-allocation worlds where 6 of 7 learners failed). That is a statement
about the instrument, not about having data to feed it yet.

## A6 — The ablation splits in two

- **ABLATION-HIST** — runs now, labelled **`ARCHITECTURE_RESULT_ONLY`**. The
  foundation model may know later history; this cannot certify anything.
- **ABLATION-FWD** — accumulates automatically as the swarm's 1d/2d/5d records
  resolve from **2026-08-16**. Only this can show DeepSeek is adding new
  information rather than reconstructing what it already knows.

Report the two as **separate evidence classes**. Do not delay the campaign
waiting for months of forward data.

## A7 — 2002–2024 is NOT a pristine holdout

This programme has interrogated CRSP 2002–2024 across many nights. It is no
longer pristine in the meaningful sense, whatever a particular model has or has
not seen. It may be used for architecture development, robustness, CPCV/CSCV and
secondary validation.

**Certification comes from genuinely untouched data/markets or the forward paper
tournament.** If no untouched historical set exists, say so plainly and make
forward paper performance the primary certification instrument.

## A8 — Evolution needs more than one walk-forward path

With hundreds or thousands of genomes × many generations, ordinary validation
becomes another optimisation target. Required: combinatorial/cross-sectional
overfitting diagnostics (CPCV), the **complete search denominator**, and
**PBO/DSR computed for the strategy FAMILY**, not only the winning genome. Keep
horizon-overlap dependence explicit — overlapping event windows distort
conventional significance tests.

## A9 — Freeze the objective before optimising

One wealth objective plus separate risk profiles, declared **before** any
optimisation. Do not choose the objective that makes the eventual winner look
best.

## A10 — The verdict must decompose the return

`GRAND_ARENA_1_VERDICT.md` separates, with each number beside its own MDE:
**selection · exposure · timing · sizing · execution · LLM · beta/style ·
costs.**

---

## A11 — What may be called a BREAKTHROUGH

Predeclared, so the word cannot be awarded retroactively. At least one of:

1. LLM incremental value surviving **risk matching AND the shuffled-LLM
   placebo**;
2. an exit/replacement policy surviving **multiple unseen periods**;
3. exposure timing beating **matched-average-exposure static sizing**;
4. a regime-conditioned improvement that **replicates**;
5. a selection mechanism surviving **independent data plus costs**.

**One spectacular backtest is explicitly not sufficient.**

---

## A12 — Budget ~~($150)~~ **SUPERSEDED same day — see A12-R**

Murat: *"dont worry about the cost go deep, use better prompts, more data."*
The research ceiling was raised to 60,000 calls / $150 on that instruction.

## A12-R — REVISED. The ceiling must bind before the vendor balance does.

The $150 figure was wrong, and **not because $150 is a lot to spend.** The
DeepSeek account holds about **$10**. A ceiling set above the balance is not a
ceiling: the vendor balance becomes the real limit, and the first symptom of
reaching it is a **402 on the PRODUCTION path**, which shares the key. That is
exactly the failure this governor was built to prevent, reintroduced by setting
the number too high.

**Rule: keep the dollar ceiling BELOW the actual balance, with headroom. Raise
it in the same motion as a top-up, never before one.** Now
**12,000 calls / $8.00** (`AEGIS_RESEARCH_LLM_MAX_USD` to change).

### Measured costs, for sizing any future decision

| item | measured |
|---|---|
| LLM-SWARM-1 | **8,014 calls → $12.04** |
| per call | **$0.0015** (~2,500 tokens in / 900 out) |
| per gradeable output | **$0.0015** |
| nightly WHY-MOVED | ~7 lens calls ≈ **$0.03/night**, under **$1/month** |

### What the rest of GRAND-ARENA-1 actually costs

**Approximately nothing.** Chunks 5–9 are CPU: the research scripts contain no
LLM call sites, and the ablation *permutes the stored 20,073 swarm records*
rather than generating new ones — the shuffled-LLM placebo (A4) works on the
existing score distribution by construction.

So the expensive part is already bought and paid for. $10 covers the remaining
campaign **and** roughly a year of nightly WHY-MOVED.

The zero-yield brake is **unchanged at 40%** — it protects the quality of the
answer, not the wallet, and no budget change touches it.

---

## Standing rules unchanged by this amendment

§19 (every arm prints its measured 80%-power MDE; below it is not detectable and
never a kill) · §20 (batches checked against themselves) · deflation is
cumulative across every trial ever registered · fabrication and outcome-shopping
remain refused · a check that did not run is not a check that passed · a refusal
is a finding.
