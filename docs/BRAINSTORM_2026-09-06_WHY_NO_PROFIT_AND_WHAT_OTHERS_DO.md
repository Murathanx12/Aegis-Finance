# BRAINSTORM — 2026-09-06 — why a sophisticated engine with huge data still does not convert observations into superior returns

For Murat, from Fable. Not a roadmap; the material a roadmap gets cut from.
Every "we" number below is from a receipt in this repo; every "they" claim is
public knowledge about how the named firms/projects operate, not something
we measured, and is marked as such.

---

## 1. The ten reasons, ranked by how much money each one cost

1. **We measured with the wrong ruler and then optimised for it.** The alpha
   ruler (excess over a beta-matched benchmark, family-corrected) is the
   right bar for a *claim*. It is not a portfolio objective. A program that
   only asks "is this alpha?" learns to say no; it never asks "what should
   $100k own at a 30% drawdown budget?" Fixed on 2026-09-07 (the Growth
   Book), one day old.

2. **Rank-real, book-dead: our construction destroyed the information it
   was given.** The Fundamental Law of Active Management (Grinold-Kahn):
   `IR ≈ IC × √breadth × transfer coefficient`. Our IC is real (0.06-0.10 on
   the clean panel). Our breadth is tiny: a top-50 *value-weighted* book has
   **7 effective names** (S36 receipt), so √breadth ≈ 9 per year instead of
   ≈ 25 for a 300-name equal-weight book. Our transfer coefficient is worse:
   the 40% UNCLASSIFIED cap, the −3% stop, the +2.5% target, full monthly
   rebalancing, the $3m floor and long-only construction when NEGATIVE_RESULTS
   §28 already showed **the information is in the short/bottom decile**. A
   0.08 IC with breadth 7 and TC 0.3 is IR ≈ 0.06 — invisible. The same IC
   with breadth 300, hysteresis and a hedged bottom leg is IR ≈ 1. **We
   have never built that book.**

3. **Costs at the wrong horizon.** Every selector was graded at 1 month with
   50-90% turnover; 10-25 bps/side is 1.5-4%/yr of drag on signals worth
   3-8%/yr. A4 found hysteresis (hold until rank 150) beats full rebalancing
   in 19 of 20 rungs, and lgbm's "+5pp at 25 bps" was *turnover saved*, not
   signal. Qlib's default strategy is exactly this (TopkDropout: hold k,
   drop n per period) — the open-source field converged on it years ago.

4. **The floors deleted the cells where the edge lives.** The small-cap
   5-session reversal cell (+0.58%/5d at 10 bps), the unfloored neural arm
   (698× → 65× under the floor), the $100k-$1m band from S28: every edge
   we found sits below a $3m/day floor set for an institution. **A $100k
   book at 1% ADV participation can trade a $500k/day name.** Our
   `execution_authority` tiers already know this (OBSERVE_ONLY) and were
   never populated. Capacity is the one dimension where a small book has an
   *advantage*, and we threw it away.

5. **Cash without a thesis and beta without a label.** The old engine sat in
   cash (+28% in five bull years); the forward lanes carried beta 0.7-1.3
   and were praised or blamed for it; three of six hack books liquidated
   09-04 and were re-armed at zero. Both errors come from not printing β
   first. Fixed in the amendment; not yet lived.

6. **Our data is public, slow and consensus-level; the differentiated data
   is two months old.** IBES consensus, 13F, 8-K item codes, CRSP: every
   institution has had them for decades, and the corpus that could be
   different (230k PIT news rows, LLM readings, fantasy exams) starts
   2026-06. There is no labeled event-time history to learn from: the
   Benzinga backfill to 2015 was never pulled; the 8-K tape starts 2013 and
   truncates heavy filers at 2016.

7. **Search without a sealed test, then over-correction.** Until this
   weekend no strategy had a sealed era, so headlines were false positives;
   once the family corrections arrived, everything died, and the program
   read "not significant at 7 years" as "nothing works". The MDE says a
   top-50 book needs ~7%/yr of true edge to show t=2 in 20 years. Most real
   edges are 2-4%/yr. **We cannot see them with this instrument; that is a
   breadth problem (2), not a market fact.**

8. **The forward fleet never ran its strategy.** 40% deployment ceiling from
   a taxonomy gap; corpus absent on Railway (hack4 sealed empty); PEAD exit
   constants on 21-session books; a re-entry guard blind to three of four
   exit routes; four risk guards that could not fire; then liquidation and
   disarm. Forward n is **4 sessions**. There is no forward evidence about
   anything except plumbing, and the plumbing was what failed.

9. **Complexity before baselines.** NN sizing lost to trailing-vol, which
   lost to flat 1×. The v2 encoder's advantage over LightGBM does not
   survive its family. Monthly refit of a *simple* model bought +5.75pp.
   The lesson the field learned (Numerai, Kaggle finance comps, Qlib):
   ensembles of many weak, decorrelated, cheap models beat one clever one,
   and gradient boosting is the baseline to beat, not the thing to beat
   with a transformer.

10. **One person, sessions that re-derived, memory that could be
    out-voted.** Fixed this week (Optimus, evidence memory, supersession),
    but four months of intent leaked before it was.

---

## 2. How others do it, honestly compared

| who | what they actually do (public knowledge) | what we do | gap |
|---|---|---|---|
| **Systematic quant funds** (Renaissance, Two Sigma, D.E. Shaw, Millennium pods) | thousands of tiny signals, market-neutral, breadth in the thousands of names and intraday, IC of 0.01-0.03 monetised by breadth and execution, strict risk budgets, capacity-aware; "right 50.75% of the time" | one signal per book, 7 effective names, long-only, monthly, IC 0.06-0.10 | we have *better* IC and *no* breadth; the exact inverse of the money |
| **Factor managers** (AQR, DFA, Research Affiliates) | harvest momentum/value/quality/low-beta in diversified long-short or tilted long-only books, low turnover, decades of patience, judge on Sharpe not "beat SPY" | tested the same premia at 1-month, 50 names, called them dead under Holm | our Growth Book champion (quality-momentum + drawdown control, β 0.67) IS their product; we just refuse to call it one |
| **Concentrated discretionary** (Buffett, Tiger cubs, activists) | 10-25 positions, held for years, deep work per name, sell on thesis break | Murat's instinct exactly (MU, MRVL, ALMS held to 10 then sold) — and the fleet sold in hours | the contracts fix the hold; the *work per name* (autopsy, graph, expectations) is B5/B6 and is barely started |
| **Numerai** | crowd-sourced models on obfuscated features; each model's correlation ~0.02; the meta-model pays through thousands of stocks × hundreds of models | one champion selected per family (DSR punishes exactly this) | an ensemble of every arm we have already trained, weighted by out-of-sample reliability, has never been built |
| **Qlib (Microsoft)** | LightGBM/ensembles on Alpha158 features, IC ~0.04-0.06, **TopkDropout** strategy (hold, drop n) | A4 rediscovered TopkDropout on 09-06 | adopt it as the default book constructor |
| **Alpaca hackathon 2026** (427 projects) | LLM proposes / deterministic gate disposes; Kelly off the bot's own track record; hard circuit breakers; **not one submission published a number** | we publish numbers, including negative ones; we already have the gate | nothing to learn on alpha; one borrow: size off *realized* book skill once it exists |
| **Retail bots with numbers** (e.g. the +34.5% vs SPY +16% bot with −27% DD) | beta amplifiers mistaken for alpha | the same thing, correctly labelled | label it, budget it, and it becomes a product (Growth Book) |
| **RL trading demos** (FinRL etc.) | overfit to one path; no sealed test | we have CPCV/PBO/DSR | keep ours; do not import theirs |

The one-line comparison: **the funds monetise a small IC through enormous
breadth and near-zero beta; the great discretionary investors monetise deep
work through concentration and years of holding. We have been doing
neither: medium IC, no breadth, hours of holding, and beta we did not
print.**

---

## 3. What we need (the list)

### A. Construction, not prediction (cheapest, largest)
1. **Fundamental-law receipt on every book**: IC, effective breadth, transfer
   coefficient, β. A book whose TC < 0.5 is a construction defect, not a
   signal verdict.
2. **Broad rank-weighted books**: top decile / top 300 equal- or
   rank-weighted over the tradable universe, **hysteresis** (Qlib
   TopkDropout: hold until rank > 2k), monthly refit, 3-6 month effective
   holding. Re-grade every existing selector this way before any new model.
3. **Monetise the bottom decile**: an index-hedged long-short (long top
   decile, short SPY or short bottom decile where borrow exists) so β ≈ 0
   and the ranking is the only thing paid; and exclusion books (benchmark
   minus the bottom decile) for the long-only product.
4. **Ensemble of all trained arms** (lgbm, encoder, ridge, revisions,
   momentum, quality, options, behavioural) weighted by out-of-sample
   reliability from the evidence memory — Numerai's meta-model, on our tape.
   Selection-free, so DSR stops punishing it.
5. **Size-aware floors**: the floor is a function of book size and
   participation (1% ADV), not $3m. Populate OBSERVE_ONLY. Then re-open the
   $100k-$1m band with measured spreads (we own TAQ).

### B. Data that is not already in every institution's model
6. **Event-time history**: pull Alpaca/Benzinga news 2015→ (free on our
   entitlement), join IBES actuals (on disk) for surprises, the 8-K tape,
   13D/G, Form 4 → one labeled event table, ten years, whole tradable
   universe. Then PEAD/event books across the universe, not the mega-11.
7. **Expectations, not levels**: revision velocity, dispersion, guidance
   vs consensus, options-implied move vs realized (we own OptionMetrics).
   Invariant 13 says surprise = actual − expected; our features are mostly
   levels.
8. **Corpus on Railway** so the live books see what the research sees.
9. **Borrow/short interest** for the short leg (Compustat short interest is
   pullable), real fees only if a short book survives paper.

### C. Learning that can actually learn
10. **Forward process metrics before forward P&L**: 20+ sessions of held
    books with nightly attribution (β × market, intercept, sizing, costs,
    cash, exits, refusals) and opportunity recall. Judge the fleet on hold
    discipline, regret and recall for a quarter; judge P&L after.
11. **Monthly retraining as the default** (+5.75pp beta-matched), with the
    champion frozen only at the seal, never across months.
12. **NN where it can win**: representation learning for *event
    compression* (dedupe thousands of syndicated stories into one canonical
    event; entity linking; novelty) and pre-training on the whole panel
    (`nn_pre_causal` was the one neural arm with a positive sign under the
    floor). Not sizing, not stock picking, until it beats the baselines.
13. **LLM where it is coherent**: 40/40 fantasy pairs moved the right way
    → use it for hypothesis generation, event extraction, expectation
    reading and red-teaming; not for ranking (era replay: at random).
14. **Kelly off realized book skill** once ≥ 60 book-days exist.

### D. Objective and product
15. **Two rulers, both printed**, β first (amendment). The Growth Book at
    1× on hack4 is the first product-grade book; run it for a quarter.
16. **Personalities as drawdown budgets**, not as prose: preservation 15%,
    balanced 25%, aggressive 35%, extreme 50%; the allocator picks the
    highest leverage-neutral TW that fits the budget.

---

## 4. What the new methods can still unfold (honest odds)

| method | what it has shown | what it could unfold | odds it pays |
|---|---|---|---|
| unsupervised states | void under the persistent null | as an *event-clustering* tool, not a return signal | medium (as infrastructure), low (as alpha) |
| self-supervised pre-training | the only neural arm positive under the floor | a better cross-sectional ranker when fed event features, in an ensemble | medium |
| fantasy transposition | coherent causal direction 40/40 | a cheap red-team for theses; a way to grade an LLM's reading without memorisation; HKU paper material | high (method), low (alpha alone) |
| era replay | at random for ranking | with the labeled event table (B6) and rank-only grading, a test of *reading*, not picking | low-medium |
| CompanyWorld graph | customer momentum dead on our extraction; graph biased large | driver taxonomy for the risk cap; commodity/country exposure for XOM/MSTR-class names; 8-K propagation | medium (risk), low (alpha) |
| options surface | IV/skew died under controls | physical-vs-implied on *events* (State-0 tail mispricing) once event history exists | medium |
| behavioural proxies | 52-week high = momentum | disposition/anchoring on the LLM itself (diary arm) | low |
| evidence memory + registry | works; cannot be out-voted | the ensemble weights (C.4) | high |

---

## 5. If I had to pick three things to do next, in order

1. **Rebuild every selector as a broad hysteresis book with a fundamental-law
   receipt** (A.1-A.3). One session. This is where the IC we already have
   turns into money or is proven unable to.
2. **The event-time table 2015→** (B.6) and re-run PEAD/revision/options
   books on it. Two sessions, $0.
3. **Run hack4 at 1× on the Growth Book champion for a quarter** with the
   nightly attribution, and stop touching it. Forward evidence needs time
   we cannot compress.
