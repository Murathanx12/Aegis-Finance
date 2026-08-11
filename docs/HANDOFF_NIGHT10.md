# NIGHT-10 HANDOFF — the instruments cannot see what they were built to find

**2026-08-11, ~8 hours, unattended. No trade, no lane seeded, no flag flipped,
no `paper_nav` row written, holdout unread. LLM spend $0.0067 of $30.**

---

## THE HEADLINE

Two audits, run for unrelated reasons, found the same thing:

> **Across 21 forbidden and published configurations, ZERO reported an effect
> above their own 80%-power detection threshold.** The standard adjudication
> shape this programme uses — EW top-50, monthly, 2002–2022 — resolves
> **6.3% to 19.9 %/yr**. Nothing anyone is realistically hunting is that large.

* **ANALYST-IBES-1**: 0 of 10 arms above their own MDE; 1 of 10 significant.
* **HERESY-1**: 11 of 11 forbidden configurations below their MDE, across 6
  distinct closed signals.

A kill from such a design is **absence of evidence**, and this programme's
graveyard has recorded it identically to **evidence of absence** for 195
experiments. That is the finding, and everything else tonight is downstream.

**Nothing is reopened.** Affected corpses get a `kill_power: INADEQUATE`
annotation and nothing else. Reopening one needs its own pre-registration, the
corpse as a control arm, and an instrument whose MDE clears the effect sought.

---

## THE EIGHT QUESTIONS

### 1. The 10 best opportunities Optimus sees now, and why

**It sees one, and it will not pad the list.** Of 5,324 US names screened and 40
carried to candidacy:

| # | ticker | $bn | score | verdict | conf | led by |
|---|---|---:|---:|---|---|---|
| 1 | **CVLG** (Covenant Logistics) | 0.84 | +0.882 | **BUY** | MEDIUM | profitability_small |
| 2 | INDV | 4.54 | +0.256 | WATCH | LOW | insider_opportunistic |
| 10= | 30+ names tied at −0.113 | | | HOLD | LOW | insider_opportunistic |

CVLG: gross profitability in the top of the small-cap cross-section, inside the
segment `profitability_small` was actually validated in, with a second licensed
signal agreeing. **Kill condition (PROPOSED):** gross profitability below the
small-cap median for two consecutive quarters.

Everything below rank 2 is **tied at the modal insider reading**. Ties share a
rank, carry `tied_with`, and can never be a BUY — a BUY is earned by evidence,
not by list position.

**Why not more?** Because the engine has two licensed pickers with data, one of
them small-cap-only, and it refuses to rank on anything else. The old page
would have shown 25 confident names ranked by analyst upside — a signal
measured at **−8 to −18 %/yr gross**.

### 2. The portfolio at $40k / $1m / $50m

**Identical at all three, and it could not be built.** All seven archetypes
refused: only 2 names carry a positive ranking score, and no archetype can fill
a book at its own concentration cap from 2 names. `OPTIMUS_MAX_GROWTH` refused
for a different reason — **Kelly needs a magnitude and the engine has only an
ordering.**

Capacity first binds between **$50m and $250m** (4 of 20 names, 20% of weight,
exceed a 5-day exit at 10% participation). Below $50m the binding constraint is
**evidence, not liquidity**. Every capacity number is a **delay-only lower
bound** — G7 prices the same 31.00 bps across six orders of magnitude of ADV, so
this programme cannot price impact at all.

### 3. What it would change in the MIRROR book (paper only)

11 of 12 held names now carry licensed evidence (they are not in the funnel, so
they were enriched through the same stage-3 path and scored in one
cross-section).

* **PRCH is the only BUY** (+0.179, MEDIUM).
* **BHVN has no licensed evidence at all.**
* Everything else is HOLD; KYTX (−1.685), AARD (−1.424), NTLA (−1.393) rank
  lowest.

**The caveat that matters more than the ranking:** most of this book is
pre-revenue biotech and speculative growth, and the signal ranking it is gross
profitability. A company with no product revenue scores badly by construction.
That is a **category mismatch, not a verdict on the theses** — the engine has no
signal that can evaluate a clinical-stage thesis and should not be read as
though it does.

Open universe: Optimus could not build a replacement book at all, so **"sell the
book and buy this instead" is not a proposal it can make tonight.**

### 4. Which strategies showed real evidence / no information / delivery failure

* **Real evidence:** none new. `profitability_small` and `insider_opportunistic`
  remain SUPPORTED and are what the product runs on.
* **No information:** nothing can now be assigned this label with confidence —
  that is the night's finding. Six signals previously recorded as dead are
  reclassified **UNKNOWN**.
* **Information but delivery failed:** analyst target **revision breadth** is
  still the best candidate (+6.05 %/yr gross, t 2.23, dies at 10.2× turnover,
  giving up 5.67 points to costs) — but it sits below its own 7.6 %/yr MDE, so
  even this is stated with less confidence than last night.

### 5. Did the LLM generate a genuinely new testable mechanism?

**No — it generated approximately one, ten times.** All 10 proposals passed the
corpse linter against 306 priors (strongest match ~0.23). Checked against *each
other*: **37 of 45 pairs at or above the linter's own 0.30 block threshold**,
all 45 above warn, collapsing to **one connected component**.

What the exercise produced instead is a **hole in the machinery**: `lint()` asks
"has this been tried before?" and can never ask "are these ten proposals ten
ideas?". A batch generated in one sitting passes one-by-one while being a single
bet, making every best-of-N bar computed from it wrong by the batch size.
`lint_batch()` is built and calibrated (8 real preregs → 6 distinct groups; the
only merge was the three genuine 13D/G variants).

### 6. Did anything survive VALIDATION? Best ER estimate?

**Nothing was validated, and nothing was frozen** — there was nothing distinct
to freeze. The holdout is unread. **No calibrated expected return exists for any
name**, which is why the page prints `NOT_CALIBRATED` and the Kelly archetype
refuses to build.

### 7. Most aggressive credible portfolio / highest-confidence portfolio

**Neither exists tonight.** Both refused for the same reason: two names with
positive scores. The most aggressive *credible* holding is CVLG at whatever
weight Murat's risk budget allows; the highest-*confidence* holding is the same
name, because it is the only one with two licensed signals agreeing.

### 8. What Optimus wants to test next / what is preventing it from being better

**Preventing it: its instruments cannot see effects of the size that actually
exist.** Every other constraint is downstream. The programme has been running a
search whose detection threshold is roughly double the largest credible equity
anomaly, recording the resulting ambiguity as knowledge, and building a registry
on top of it.

Next, in order:
1. **Raise instrument power before searching again** — longer windows, more
   names per leg, or a panel estimator with an SE smaller than the effects
   sought. Searching harder at a 12 %/yr MDE spends compute to produce
   ambiguity.
2. **Re-run the ARENA null calibration with many seeds.** Three seeds spanning
   2.7–7.4 %/yr is not a bar (see the correction below).
3. **Wire more licensed evidence.** Capacity binds at 4 names of 20 at $250m;
   the fix is a wider licensed universe, not a cleverer optimiser.
4. **Ten separate LLM calls, each forbidden the previous answers' vocabulary**,
   scored by `lint_batch` — a testable claim about prompting, not about markets.

---

## THE PRODUCT DEFECT THAT IS NOW CLOSED

BUILD-1.2 printed `EVIDENCE CONFLICT (HIGH)` on every brief and kept ranking
anyway. The chain `implied_upside → expected_return.mu → certainty_equivalent →
sort` is monotone at every link, so **the BUY list was ordered by
`analyst_target_upside_xs`** — PERVERSE/CLOSED, −8 to −18 %/yr gross — entering
under the name of its RISK_INPUT cousin.

`backend/services/recommendation.py` separates them by construction, and proves
it rather than asserting it: `rank_invariance()` re-ranks with a signal's values
reversed and requires Spearman ρ **exactly 1.0**. A signal that cannot reorder
the list cannot lead it. `assert_registry_discipline()` **refuses to publish**
rather than warning — and after tonight's fragility audit, it also refuses when
its own check *crashes*, because a check that did not run is not a check that
passed.

**A second conflict nobody had printed:** `profitability_small`, whose own
registry entry reads *"Net-dead in large/mid"*, was the leading contributor to
NVDA, AAPL and META. The registry has always recorded each signal's universe and
nothing enforced it.

---

## FOUR DATA DEFECTS FOUND WHILE BUILDING

Each looked fine on every dashboard:

1. **The insider signal was dead on arrival.** The fetcher read
   `transactionType`, which Finnhub returns as `null` on **100%** of rows. Every
   transaction arrived uncoded, the open-market filter discarded all of it, and
   the score returned a confident `0.0` for **every ticker in the universe**.
   Twelve tests passed throughout. Fixed → evidence coverage went **7/40 →
   33/40**, and VTS surfaced a real **$1.0m** open-market purchase.
2. **Market cap in the wrong currency.** IBN overstated **95×** (INR), TSM
   **28×** (a $61 *trillion* cap), FMX **6×**. Cap decides the band, which
   decides which signals are licensed.
3. **The funnel searched where its evidence wasn't.** Stage 1 truncated to the
   `keep` most liquid names — controlling no risk, since all had already cleared
   the retail gate — and silently decided the product could only ever recommend
   mega-caps. **0 of 25 candidates were in the licensed small band.** Stage 3
   already stratified by size, one stage too late. Now **7 small caps** reach
   candidacy.
4. **Ties printed as a ranking** — 30+ names in a confident order that was list
   order.

---

## CORRECTION TO A PUBLISHED NUMBER

The **"+4.87 %/yr false-discovery bar — best of 384 when nothing predicts
anything"** does not trace to the receipt it describes.
`synthetic_results.json → null_calibration` says **+2.73 %/yr** (one seed); the
power curve's three null seeds give **+2.73 / +4.16 / +7.43**. The published
+4.87 is numerically the **real-data equal-weight control** — which is also the
separately-published "4th of 384", so **two of the four headline numbers are one
measurement counted twice**.

**ARENA-1's null survives at every candidate bar** (at 2.73%, best t = 1.96,
Bonferroni p_adj = 1.000). Say instead: *best-of-384 under the null is +2.7 to
+7.4 %/yr across three seeds*, and no single-point bar is credible at n = 3.

Everything else in ARENA-1 validated: freeze predates scoring, 0 orphan genomes,
66 survivors reproduce exactly, the best genome is still excluded by the frozen
turnover gate (3.03 vs 3.00), the void pass is preserved, the holdout is unread.

---

## PROPOSED CANON AMENDMENTS

1. **A registered prediction that two constructions AGREE is a claim about their
   DIFFERENCE**, and must be adjudicated by testing that difference with its own
   standard error — never by comparing two point estimates and reading their
   signs. *Type specimen:* ANALYST-IBES-1 prediction 5 was recorded REFUTED on a
   sign comparison; the difference carries **t = 1.03**.
2. **Every trial reports, beside each arm, that arm's own 80%-power MDE.** An
   effect below it is "not reliably detectable by this design", never evidence
   for or against a mechanism.
3. **A batch of proposals is checked against itself**, and the honest
   denominator is `effective_distinct_ideas`, not the proposal count.

---

## WHAT MURAT STILL OWES

Unchanged from last night, and none of it blocked tonight's work:

* **the cash figure** — NAV is marked equity only until it arrives
* **QUBT 300 vs 200** — carried visibly at **$893** of NAV, neither adopted
* **rulings on 5 proposed kill conditions** (ABSI, AMSC, HUBS, KYTX, SLDP) —
  proposed tonight, labelled `PROPOSED_AWAITING_MURAT`, none invented
* **`confirmed: true`** on the book — until then every number is a simulation

New, and worth a ruling: **`ANTHROPIC_API_KEY` is present in `.env` but empty.**
The Claude path was unavailable all night, so every LLM result here is DeepSeek's
and the hypothesis-generation finding has not been tested against a frontier
model.

---

## RECEIPTS

| what | where |
|---|---|
| objective + division of labour | `docs/OPTIMUS_OBJECTIVE.md` |
| the search, the power audits | `docs/NIGHT10_ALPHA_FACTORY_REPORT.md` |
| LLM roles, ledger, the diversity finding | `docs/NIGHT10_LLM_RESEARCH_REPORT.md` |
| analyst revisions | `docs/NIGHT10_ANALYST_REVISION_DELIVERY.md` |
| the book, paper only | `docs/NIGHT10_MIRROR_CHALLENGE.md` |
| capacity at $10k–$250m | `docs/NIGHT10_CAPITAL_FRONTIER.md` |
| fragility audit, 3 findings | `docs/NIGHT10_FRAGILITY_AUDIT.md` |
| the decision page | `docs/BUILD1/investment_committee.{json,txt}` |
| machine-readable | `docs/BUILD1/{funnel_night10,mirror_challenge,capital_frontier,llm_hypotheses,llm_hypothesis_diversity,llm_adversarial_review}.json`, `llm_ledger.jsonl` |
| trials | `Aegis module/TRIALS/PREREG_{ANALYST_IDENT_1,HERESY_1}.md` |
| verdicts | `Aegis module/docs/ANALYST_IDENT_1_VERDICT_2026-08-11.md`, `runs/HERESY/heresy_1.json` |
