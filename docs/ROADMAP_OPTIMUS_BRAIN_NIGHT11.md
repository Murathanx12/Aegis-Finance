# ROADMAP — from a truth machine to an investment brain

> **NIGHT-12 UPDATE (2026-08-11).** Five of the queue items below are now done
> or answered; see `SESSION_2026-08-11_NIGHT12.md`. The dependency chain held,
> and one link in it broke in the programme's favour:
>
> * **The short-leg decomposition RAN and the revision family SURVIVED it** —
>   short-leg share 41.8–52.1% against Round 16's 88–99.9%, long leg clears its
>   own MDE in 6 of 7 arms. The "first licensed signals" step is no longer
>   blocked. **`eps_rev_breadth` small at Layer 2, carrying G7 turnover in the
>   same trial, is now the single highest-value open item in the programme.**
> * **BeliefState + PredictionRecord are frozen and the calibration clock is
>   running** — 87 live forecasts. This was named the prerequisite for a
>   two-way Optimus and it is now in place; the remaining work is resolution
>   and scoring, which only time can supply.
> * **The counterfactual replay engine is built** — the leakage-free half of
>   the "market laboratory" proposal, no LLM involved.
> * **The graveyard rescue queue is rescoped down, not up.** CONVICTION-REPLAY-1
>   measured an 80-point MDE on a 13-name book; the counterfactual exit study
>   returned no separating observable. Small-n instruments stay small-n.
> * **The exposure controller exists and never fired**, which reframed the third
>   failure as a sizing problem rather than a timing one.
>
> Everything below is retained as written for the record.

**Written 2026-08-11, NIGHT-11.** Supersedes nothing; it is the first roadmap
this programme has written about the *player* rather than the *referee*.

---

## The diagnosis, in one paragraph

Three independent reviews converged on the same shape, and it matches what the
last four nights measured. The research machinery is excellent — it catches its
own published numbers, it refuses to publish a ranking led by a closed signal, it
records what it cannot see. The investment brain is not. The programme can tell
you with great precision that it does not know something. It cannot yet tell you
what to buy, and the reason is not timidity: **the instruments could not resolve
the effects being hunted, so nothing ever earned a licence.**

The dependency chain is strict and every item below sits on the one before it:

```
powered instrument
  -> graveyard rescue queue
    -> first licensed signals
      -> calibrated expected returns
        -> sized portfolios
          -> forward calibration compounding
```

The trap is spending another night on the 9/10 dimension. Every hour the
machinery spends auditing itself is an hour the 5/10 dimension stays at 5.

---

## What NIGHT-11 actually did (status: see the session doc)

| # | Item | State | What it measured |
|---|---|---|---|
| P0-A | HAC-consistent MDE. `newey_west_tstat()` returns its SE; the power block reports IID and HAC and says which binds | **DONE** | incumbent MDE range 6.3–19.9 → **6.47–24.82 %/yr**; 0/10 above MDE either way |
| P0-B | The stale +4.87 false-discovery bar, corrected to the measured +6.90 and tied to its receipt by test | **DONE** | 0 of 384 genomes clear; guard verified to FAIL on the old value |
| P1 | `aegis_brain/pf/information.py` — the Layer-1 cross-sectional instrument | **DONE** | gain **0.98–2.11x, median 1.63x**, not the ~10x argued for |
| P1b | Injected-alpha calibration, plant verified present as a paired difference | **DONE** | unbiased at every level; 0% false positives on the null |
| P2 | REVINFO-1: analyst-revision information, pre-registered | **DONE** | revisions carry information in **small caps to ~6 months**; large caps empty |

Two corrections this session made to **its own new instrument**, both caught by
measurement rather than review, both kept in the tests:

* a test asserting the power gain `> 2.0` **failed at 1.31** — the premise was
  overstated and the real number is 1.63x median;
* `NO_INFORMATION` was not an equivalence claim and labelled arms at **t = 2.21**
  and **t = 2.72** "evidence of absence". Now a one-sided equivalence bound;
  re-running the grid changed **7 of 32 verdicts**, in both directions.

The rest of this document is the queue.

---

## The three-layer research hierarchy (the central methodological change)

This programme has one instrument for every question: build an EW top-50 book,
rebalance monthly, subtract the market, test 252 numbers. That instrument
resolves **6.5 to 24.8 %/yr** at 80% power. No credible equity anomaly is that
large. It is not that the bar was too high; the ruler was too coarse.

**Layer 1 — does the information exist?**
Estimate on the cross-section, not on one portfolio's returns. ~900,000
stock-months instead of 252 portfolio-months. Fama-MacBeth, one slope per month,
Newey-West over the slopes; date-clustering done the oldest way. Verdicts are
three-valued and `NO_INFORMATION` requires the design to demonstrate its own
adequacy first.

**Layer 2 — does it help at the decision boundary?**
The economically relevant question for a 12-name book is not "does rank 1 beat
rank 3000" but "does rank 11 beat rank 13". Test the ranks around the actual cut,
and the replacement edge `E[r_entrant − r_incumbent]`, not global IC.

**Layer 3 — can it be delivered?**
Turnover, spreads, delay, liquidity, capacity. Only here does a money claim
become possible.

**The distinction this buys:** `DELIVERY_FAILED` becomes sayable. A signal with
information whose first implementation loses to costs is not the same object as a
signal with no information, and this programme has been recording them
identically. That confusion is a large part of the graveyard.

> **Standing rule, adopted this session.** A Layer-1 result licenses a Layer-2
> test and NOTHING else. The spread it measures is dollar-neutral and
> unconstrained, and Round 16 measured 88–99.9% of a comparable spread living in
> the short leg a long-only book cannot hold.

---

## Queue, in dependency order

### 1. Graveyard rescue queue (needs: P1, P2) — **rescoped by what REVINFO-1 measured**
Do not re-run 195 corpses. Rank them and take the top 10–20:

```
RescueScore = PriorPlausibility x |ObservedEffect|/MDE x DataQuality
              x EconomicValue x ImplementationFeasibility
```

Every rescue needs its own pre-registration, the corpse as a control arm, and an
instrument whose MDE clears the effect sought. A multi-instrument kill is not
overturned by one underpowered arm.

**Two constraints REVINFO-1 discovered, which the queue must be designed around
rather than hit later:**

* **The power upgrade is ~1.6x, not ~10x, and only in small caps.** Measured
  0.98x–2.11x on the real panel (`docs/REVINFO_1_VERDICT_2026-08-11.md` §4);
  twice BELOW 1.0 in large/mid, because there a top-50 book already is most of
  the investable cross-section. An 8 %/yr MDE becomes ~5 %/yr. That reopens some
  UNRESOLVED corpses and does not make the standard design adequate. The rest of
  the power must come from elsewhere — the 1962– era spine, factor-neutralised
  test portfolios, or event-level rather than monthly-panel estimation.

* **A tail-killed corpse needs a tail-shaped instrument.** `tgt_upside` is
  −16.70 %/yr through a top-50 book (the top ~3% of names) and **−0.16 %/yr,
  t −0.03** on the breadth-weighted cross-section; at the decile level it is
  +1.18. Its perversity is real and lives in the extreme tail, where a
  cross-sectional average cannot see it. A queue built only on the
  cross-sectional instrument would quietly exonerate every tail-perverse corpse.
  **Each rescue carries both a cross-sectional and a tail-concentrated arm.**

Queue position one is unchanged and now has a Layer-1 result behind it:
`tgt_rev_breadth` small, INFORMATION_PRESENT at h=1/3/6 (+9.36/+7.32/+5.45 %/yr,
t 4.87/4.31/3.31). What it needs next is Layer 2, not another Layer 1.

### 2. Make CANON §19 blocking rather than reporting
The scorecard prints `NOT RELIABLY DETECTABLE`. Printing is not preventing. A
trial whose *realised* MDE exceeds a frozen largest-credible-effect ceiling
should be `POWER_FAILED` before scoring, automatically — ANALYST-IDENT-1
registered 4.0 and realised 10.8, so registered MDEs are not enough.
`information.py` already does this at the verdict; the scorecard does not.

### 3. The standing data-sanity layer
Three of NIGHT-10's four data defects were catchable by the same three checks:
- **max-plausible-value bounds** — a $61tn market cap must be *unstorable*, not
  discoverable in an audit six months later;
- **null-rate monitors on every consumed API field** — the insider signal was
  dead on arrival, reading a field the API returns null on 100% of rows, with
  twelve green tests the whole time;
- **golden-value tests against known external facts.**

The house failure mode is silent fragility. These are its specific antidotes.

### 4. `OptimusBeliefState` — the missing central object
Today the system jumps from signal to score to rank. That is why it judged
pre-revenue biotech by gross profitability: the registry was right and
*profitability is the wrong language for that company*.

One living object per name, carrying fundamentals, street expectations, events,
price, options, ownership, regime, **contradictions**, the market-implied belief
beside our own, a multi-horizon return distribution, confidence, next observable,
thesis and kill condition.

**The concept that makes it worth building is expectation discrepancy.** Edge is
not "which company is best" but `E_optimus[outcome] − E_market[outcome]`. A
worse business with a larger expectation error is the better trade. Quality is
not alpha.

### 5. Category routing / specialists
A biotech is evaluated on clinical phase, endpoint, PoS, cash runway, dilution,
FDA path; a semi on cycle, inventory, bookings, ASP; software on ARR, NRR,
margin progression. Until routing exists, print **`OUT_OF_SCOPE` per name rather
than a number** — a score that means "I cannot see this company" currently looks
identical to a verdict, and most of Murat's actual money is in names the engine
cannot see.

### 6. Multi-horizon prediction ledger (needs: 4)
Waiting 24 months to learn from one NAV is the slowest possible feedback. Freeze
thousands of stock-level forecasts instead: 5/20/60/120/252-day probabilities and
expected returns, with the belief-state hash and signal contributions. Within 60
days that is thousands of resolved predictions.

It also fixes a real defect in the current learning path: reliability is updated
by asking whether a signal's sign agreed with the **portfolio's** excess return,
so four signals in one book that made +10% can all be credited for the same
return. Learning must come from individual forecast contributions, shrunk
hierarchically by signal x horizon x domain x regime.

### 7. Seed the forward books (needs: 3, and an attended decision)
The register is corrected but nothing is seeded. Controls (`SPY`,
`EQUAL_WEIGHT`, `RANDOM`) plus Optimus challengers, same day, same notional,
same cost model, no backfill. **Print the forward MDE on the track-record page**
— at 64 days the lanes can distinguish nothing from nothing, and without that
number someone will read aggressive's +4.6% as skill and the mirror's −18.6% as
failure. Neither reading is licensed.

### 8. Graceful degradation instead of refusal
All seven archetypes refusing is honest research and a useless product. When
evidence cannot fill a book the answer is a low-cost market-weight core with
small evidence-scaled tilts, and the refusal printed as the reason the tilts are
small — never an empty page. For a general investor, market exposure plus cost
discipline already beats most investors net; the product should say that sentence
rather than decline to speak. **This is a design change and it is Murat's call.**

### 9. LLM: independent specialists, measured (needs: 4)
NIGHT-10 got ten hypotheses that were one idea in ten costumes — one connected
component at the block threshold. The cause is architectural: one model, one
large prompt, asked for multiple distinct mechanisms.

Run independent researchers in isolated contexts — forensic accountant, biotech,
sell-side revisions, event-driven, options, ownership, microstructure, and an
adversarial skeptic whose job is to kill the other seven — then synthesise. And
change *what* is asked: not "will NVDA go up" but intermediate **observables**
(revenue surprise, margin direction, guidance change, trial success, dilution
likelihood) which are measurable, scoreable, and therefore able to earn
reliability. Score every specialist by Brier, calibration, and incremental value
over a deterministic baseline.

The firewall does not move: the LLM narrates and proposes; the engine computes
and allocates.

### 10. Calibrated expected returns (needs: 6)
Kelly correctly refuses to operate on an ordering. Shrunk factor-implied ERs plus
forward-resolution calibration is a months-long accumulation, and every month it
is not started is a month the product cannot size anything.

---

## What NIGHT-11 will not do

- Not another 384-genome search on the same registry and the same scorer. That
  instrument has already told us what it says.
- Not more generic signals.
- Not another audit of the audit machinery beyond the P0 items above.

---

## Open items owed by Murat

| item | why it is his |
|---|---|
| cash balance | the book cannot be marked without it |
| QUBT 300 (decision log) vs 200 (config) | $893 of NAV, both carried |
| rulings on five proposed kill conditions | five names have none and none may be invented |
| `confirmed: true` on the book | the record is provisional until then |
| a real `ANTHROPIC_API_KEY` | the env var exists and is EMPTY; every LLM finding to date is a finding about DeepSeek |
| seeding the shadow books | seeding changes what the record means; it is not a code change |
| the graceful-degradation ruling (item 8) | it changes what the product says when it has nothing |
