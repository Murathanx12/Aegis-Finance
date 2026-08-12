# PREREG — PORTFOLIO-ARENA-1: fifteen complete systems on one dollar, one clock, one cost model, and five risk matchings

**Registered 2026-08-12, GRAND-ARENA-1 chunk 7, BEFORE a single portfolio path
exists.** **Family:** portfolio construction / whole-system comparison.
**Grade:** simulated direction check on CRSP daily 2002-2024, plus an
`ARCHITECTURE_RESULT_ONLY` LLM overlay whose historical status is fixed by
Amendment A6. **ACCRUES ZERO ARMS** — nothing here may seed, arm, size,
default or re-weight any lane, shadow book or product surface.

**Binding law:** `docs/GRAND_ARENA_1_AMENDMENT_A.md`, frozen 2026-08-12.
A3 (risk matching), A5 (neutral priors), A7 (2002-2024 is not a pristine
holdout), A9 (freeze the objective first), A10 (decompose the return) and A11
(what may be called a breakthrough) all bind this file.

---

## 0. Corpse check

Run before §1 was written and re-run before commit:
`python scripts/lint_prereg.py TRIALS/PREREG_PORTFOLIO_ARENA_1.md`

The graveyard holds many single-signal corpses whose vocabulary this file must
necessarily reuse, because a system arena is built OUT of signals that have
already been graded. Each is declared, and in every case the corpse enters as a
**component of a competing complete system**, never as a resurrected standalone
claim.

- Resurrects: TRIAL-MOM-BACKTEST-12-1-momentum — new instrument: the unit is a complete monthly-rebalanced portfolio path with a G7 cost charge and five risk matchings, not a single-signal decile spread; momentum enters only as one competitor (P11) and the arena is explicitly permitted to rank it below a random draw.
- Resurrects: TRIAL-REVISIONS-IC — new instrument: revision score enters as one whole system (P12) evaluated on terminal wealth net of costs against a volatility-matched random control, which no IC trial has ever had; NIGHT-11's small-cap licence is carried as a stated scope, not re-tested as an IC.
- Resurrects: PF5 rebalance frontier / PF6 product-real — new instrument: those trials searched a genome family for the best product; this one FREEZES fifteen systems declared in advance, adds four never-before-run competitors (volatility-matched random, positive-skew, risk-targeted positive-skew, LLM-fed), and its primary comparison is against controls rather than against the best member.
- Resurrects: TRIAL-COND-VT / EXPOSURE-CONTROL-1 — new instrument: those asked whether a timing rule improves ONE realised path (n=1 book, n=1 war). Nothing here is a timing rule. Volatility targeting appears ONLY as a risk-MATCHING transform applied identically to every system, which is a measurement device, not a strategy arm, and it cannot reopen the conditional-vol-target family.

**What this trial is NOT allowed to do.** It may not declare a winner and it may
not promote anything. Under A7 the 2002-2024 span is development and secondary
validation only. Certification comes from genuinely untouched data or the
forward paper tournament, and no result here changes that.

---

## 1. THE FROZEN OBJECTIVE (Amendment A9 — declared before any optimisation)

**One wealth objective, frozen here, chosen before any system has been run and
never re-chosen:**

> **PRIMARY:** the **net annualised excess CAGR of terminal wealth over the
> CRSP value-weighted market**, from a single dollar invested at the first
> decision date, compounded through monthly rebalancing, charged the G7 cost
> model on realised turnover.

Terminal wealth, not Sharpe, not information ratio, not hit rate. A saver ends
with a number of dollars; that is the number.

**Risk profiles do not change the objective and they do not change the evidence
standard.** They change only the position/risk budget:

| profile | position budget K | max weight | leverage cap |
|---|---:|---:|---:|
| conservative | 40 | 5% | 1.0 |
| **base (primary)** | **20** | **10%** | **1.0** |
| concentrated | 10 | 20% | 1.0 |

Every verdict below is read off the **base** profile. The other two are
reported as sensitivity and may not be used to select a winner.

**SECONDARY, reported but never decisive:** annualised volatility, max
drawdown, realised beta, turnover, effective number of names, and the
cross-sectional rank IC of each system's score against the forward one-month
return.

---

## 2. Hypotheses

**H1 — the arena's null.** No system's net excess CAGR over the CRSP VW market
exceeds its own 80%-power MDE, at the base profile, under **raw** evaluation.

**H2 — the matching null (the deciding one, A3).** For any system that clears
H1 raw, its advantage does **not** survive matching on beta, volatility, gross
exposure, concentration and turnover. *Directional prior: HIGH that at least
one raw winner is a pure exposure artefact, because WORLD-L, NIGHT-14 and
EXIT-LAB have each produced exactly that.*

**H3 — the random control.** No selection system beats its **volatility-matched
random** cousin (P4) drawn from the identical eligible set at the identical
position budget by more than that difference's own MDE. This is the clause that
separates "the ranking is informative" from "being invested in K names is
informative", and it is the direct descendant of EXIT-LAB's
`REPLACE_RND` finding.

**H4 — the LLM clause.** Systems fed LLM scores (P6, P7, P8) do not beat their
identically-constructed no-LLM counterparts by more than the MDE of that paired
difference. *This hypothesis is `ARCHITECTURE_RESULT_ONLY` by A6 whichever way
it comes out, and its full placebo ladder lives in `PREREG_ABLATION_1.md`.*

**H5 — the capacity clause.** The ranking of systems by the primary objective is
invariant to notional across $10k / $40k / $100k / $1m. *Prior: violated at
$1m for the highest-turnover, smallest-cap systems, because impact scales with
participation and those systems trade the least liquid names hardest.*

---

## 3. Unit of observation, sampling unit, and the ruler

- **Decision date** = the last trading day of each month with ≥252 trading days
  of prior history. 2003-01-31 → 2024-12-31, n ≈ 264.
- **The sampling unit for every inferential statement is the MONTH.** Names
  inside a month share a market factor; counting positions as independent
  manufactures significance.
- **MDE = 2.80 × max(Newey-West, IID) SE** of the monthly series being tested,
  annualised by ×12, per CANON §19. Newey-West lag `L = floor(4(n/100)^(2/9))`.
  **A number below its own MDE is NOT DETECTABLE and is never reported as a
  kill.**
- Every paired comparison is computed on the **paired monthly difference**, not
  on the difference of two independently-estimated means.
- **§18 applies:** any claim that one system beats another BY MORE THAN a third
  does is tested as a difference-of-differences with its own SE and its own MDE.
- **Regime blocks (declared now):** 2002-03, 2004-06, 2007-09, 2010-12,
  2013-15, 2016-18, 2019-21, 2022-24. Sign agreement across blocks and across
  sample halves is reported for every headline number and is never a substitute
  for the MDE.

---

## 4. The eligible set — identical for every system, every date

Frozen, and identical to WINNER-GENOME-1 and EXIT-LAB-1 so the three
instruments share a universe:

- CRSP common US stock (`shrcd` 10/11) on NYSE/AMEX/NASDAQ (`exchcd` 1/2/3),
- price ≥ $5, ≥252 trading days of history, 63-day median dollar volume ≥ $1m,
- top 1,500 by 63-day median dollar volume.

**Death is modelled.** The CRSP delisting return is written into the return
matrix on the first trading day after the last quote (Shumway −0.30 for
performance delists with no `dlret`), after which the position sits in cash at
`rf`. A run in which the delisting path never fires is refused.

**Every system sees exactly the same names and exactly the same information at
every date, and nothing computed from a date after the decision date.**

---

## 5. The fifteen systems (frozen; no member may be added after any result)

| # | system | rule |
|---|---|---|
| P0 | SPY | the buyable index fund, EODHD adjusted close |
| P1 | QQQ | the buyable growth index fund, EODHD adjusted close |
| P2 | equal weight | 1/N over the ENTIRE eligible set |
| P3 | random | K names drawn uniformly, `default_rng` seeded per date |
| P4 | **volatility-matched random** | K random names re-drawn so trailing portfolio vol matches the reference system's, then levered with cash to the exact target |
| P5 | Aegis deterministic | the repo's config-declared composite of PIT quant features, weights taken from `backend/config.py` and **not fitted here** |
| P6 | LLM only | rank by the swarm's aggregated directional score |
| P7 | LLM + Aegis equal | z(P5 score) + z(P6 score), equal weight on the two legs |
| P8 | reliability-weighted LLM + Aegis | **A5: specialist reliability priors are NEUTRAL/EQUAL.** The only reliability input permitted today is the model's own stated confidence, which is an output, not an earned weight. Hierarchical partial-pooled updating begins when forward records resolve, first on **2026-08-16**. |
| P9 | learned meta-model | LightGBM on quant + LLM features, purged embargoed walk-forward, out-of-fold only |
| P10 | evolutionary survivor | **DECLARED NON-RUN** — chunk 8 has not run; there is no survivor. Fabricating one would be inventing a competitor. |
| P11 | momentum / event execution | 12-1 momentum with a post-announcement drift tilt (SUE > 0 within 5 trading days of `rdq`) |
| P12 | revision-based | NIGHT-11 revision score, with NIGHT-11's small-cap scope stated |
| P13 | high positive skew | trailing 252-day return skewness + max-daily-return rank. *Declared directional prior: NEGATIVE, per the lottery-demand literature. A system predicted to lose is still a competitor.* |
| P14 | risk-targeted high positive skew | P13 levered/de-levered with cash to the market's trailing volatility |

Weighting inside a selection is **equal**, always. A weighting scheme is another
free parameter and this arena is not permitted to search one.

---

## 6. Risk matching — Amendment A3, the single most important requirement

**Every comparison reports RAW and MATCHED.** Five matchings, each applied
identically to every system, each computed from information at or before the
decision date:

1. **beta-matched** — the sleeve is blended with cash so trailing 252-day
   portfolio beta against the CRSP VW market equals 1.00.
2. **volatility-matched** — blended with cash so trailing 252-day portfolio
   volatility equals the market's trailing 252-day volatility.
3. **gross-exposure-matched** — gross notional forced to 100% at every date.
4. **concentration-matched** — every selection system runs at the identical
   position budget K, and effective-N is reported beside every result.
5. **turnover-matched** — partial rebalancing toward the target weights,
   capped at a common monthly one-way turnover budget equal to the median
   realised turnover across the selection systems.

> **If a system's edge vanishes under matching, the report says so in one plain
> sentence and the raw number is never quoted again without it.**

---

## 7. Costs, and the notional sweep

**G7, reused not reinvented:** Corwin-Schultz high-low half-spread (21-day
rolling median, capped 300 bps, floored at the half-tick), + 5 bps slippage
+ 1 bp commission, charged on one-way traded notional. Index legs are charged a
declared 5 bps all-in.

**Impact, declared and flagged.** NIGHT-8 recorded that G7 **cannot** price
impact, so a square-root participation term is added for the notional sweep
only: `impact_bps = C · σ_daily · sqrt(Q / ADV) · 1e4` with **C = 1.0 declared,
never fitted**. It is labelled a DECLARED MODEL everywhere it appears. At $10k
the term is negligible by construction; if it changes a ranking at $1m, that is
the finding H5 asked for.

Notionals evaluated: **$10k / $40k / $100k / $1m.** Whole-share rounding is
applied at $10k and $40k and the resulting cash drag is reported, because a
$500 target position in a $300 stock is one share and a fifth.

---

## 8. Decision rules — frozen before any number exists

| outcome | condition |
|---|---|
| `DETECTABLE_POSITIVE` | net excess CAGR > its own MDE, sign consistent in ≥5 of 8 regime blocks AND both sample halves, **and it survives all five matchings** |
| `EXPOSURE_ARTEFACT` | detectable raw, NOT detectable after beta- or vol-matching |
| `NOT_DETECTABLE` | |point estimate| ≤ its own MDE — reported, never a kill |
| `DETECTABLE_NEGATIVE` | net excess CAGR < −MDE with the same consistency conditions |
| `DECLARED_NON_RUN` | the system's inputs do not exist; recorded with the reason |

**No promotion of any kind follows from any cell of this table.**

---

## 9. What must be reported whatever it says

- The **complete search denominator**, including every configuration that
  failed, crashed, or was voided.
- The per-system raw AND matched tables on all five dimensions.
- Every MDE beside every point estimate.
- The A10 decomposition: selection · exposure · timing · sizing · execution ·
  LLM · beta/style · costs.
- An explicit **"what this cannot tell us"** section.
- Any defect found in the harness, including ones found after a result was
  computed.

## 10. Declared limitations, written before the answers

1. Monthly decisions only. Nothing here can see intraday execution, and a null
   on selection is not a null on execution.
2. The eligible set is liquid by construction. None of these numbers transfers
   to a micro-cap or illiquid book.
3. The LLM overlay is `ARCHITECTURE_RESULT_ONLY` (A6) — the foundation model
   may know later history, so no LLM-fed system can be certified here whatever
   it earns.
4. 2002-2024 has been interrogated by this programme across many nights (A7).
   It is not a pristine holdout and nothing here is certification.
5. P10 does not exist and is recorded as a declared non-run, not omitted.
