# SESSION 2026-08-09 — NIGHT-2 (PF-2) executed, NIGHT-3 deltas adopted

Branch `factory/night-2` in the `Aegis module` repo (cut from `factory/night-1`).
No lane seeded, no flag flipped, `paper_nav` untouched, holdout unread.

## What happened

**1. PF-1 closed out honestly.** The last two placebo bands landed; the
denominator is **648**, not 448, and both late bands **FAILED** their placebo
gate — which flips pre-registered prediction #2 from MISS to HIT, so PF-1
scored **2 of 5**, not 1 of 5. Recorded as a dated addendum rather than an edit
in place (`docs/PF1_CAMPAIGN_VERDICT_2026-08-08.md` §7).

**2. The standard was amended, forward-only** (`001fa4d`, aegis-finance main):
G4a factor gate (engine-skill claims need FF5+UMD α ≥ +2 %/yr at t ≥ 2.0), the
FACTOR-HARVEST PRODUCT label, the NEAR-MISS(gate) verdict class, and the
measured note that turnover-matched placebos test construction artifacts rather
than factor exposure. PF-1 was **not** re-scored.

**3. PF-2 pre-registered before compute** (`06a0cf7`) and run: 342 experiments.
Verdict `docs/PF2_CAMPAIGN_VERDICT_2026-08-09.md`, registry row
`VERDICT-PF-2-BATCH`.

### The headline

**PF-PROF-COMPOSITE-150 cleared all eight gates — the first strategy in this
project's history to do so.** Three profitability signals, 150 small-cap names,
monthly, 25 bps, 40.2 years: **+4.67 %/yr net excess** (t 2.85 / NW 2.52),
**5/5 regime blocks**, ruin 0.102, 8/8 grid configs positive, halves
+5.00 / +4.33, beats the equal-weight universe by +5.36 %/yr (t 5.06), and the
placebo band is the strongest control result yet — **all 100 random books were
negative** (max −0.77 %/yr) at matched turnover.

It passes the new factor gate at **FF5+UMD α +5.01 %/yr, t 3.39**, and the
mechanism is visible in the betas: `rmw = 0.135`. A portfolio built entirely
from profitability signals barely loads on the published profitability factor,
because RMW is value-weighted and large-cap-dominated while this book is
equal-weighted small caps. The small-cap profitability premium is not spanned
by RMW.

**It is labelled RETROSPECTIVE and does not graduate.** The deciding
factor-alpha number already sat on disk in a PF-1 grid card
(`PF-PROF-COMPOSITE__N150`: `ann_alpha 0.0501, t_alpha 3.39`), so this is not a
blind test. The only evidence that I did not peek is that registered prediction
P5 said it would **fail** G4a. G2 (holdout) and G7 (daily simulator) have not
run. A holdout firing plan is **written, not executed** (verdict §7) — one
attended read, pass bar frozen in advance, failure final.

### The structural finding

**PF-ENGINE-ALPHA-2 FAILED, and the registered fix could never have worked.**
All eight configurations — including three core-satellite blends — sit at 3/5
regime blocks. Because

> blended excess = X·mkt + (1−X)·r_s − mkt = **(1−X) · (strategy excess)**

a constant blend **scales every block's excess and preserves its sign**.
Measured at X = 0.50, every block ratio ≈ 0.50 and nothing flips. Regime
breadth is **invariant to allocation**; only selection can move it. One line of
algebra would have replaced eight backtests, and that is recorded against
myself, not buried.

Its product bar nevertheless passed (15.58× benchmark vs best investable
alternative 8.94×, ruin 0.005) — but a candidate failing two gates cannot take
the product label under the rule as frozen.

### Murat's "11th account", answered

`PF-META-1` treats the six PF-1 strategies as assets and buys whichever has
been winning. On the common window all books share, the **registered rule loses
to simply holding all six equally**: 6.63× vs **7.18×**, at *six times* the
ruin probability (0.604 vs 0.097) and 164 strategy switches vs 3. Switching
costs alone take 1.6 %/yr. **P7 HIT** — strategy-level timing behaves exactly
like stock-level timing.

One grid cell (12-month lookback, hold top-**2**) printed +6.32 %/yr and 24.72×,
beating even the hindsight-chosen best single strategy. It is **not** promoted:
its neighbours collapse (+3.41 % at lookback 6, +0.84 % at 24), which is what a
lucky cell looks like. The credible part is top-1 → top-2 cutting ruin from
0.604 to 0.062 across every lookback — that is diversification, not discovery.

**If Murat wants the 11th account, the honest form is "equal-weight all the
lanes" (the control that won), not "copy the winner" (the idea that lost).**

### Other outcomes

- **Insider family CLOSED** per the frozen rule. The tie defect was real and is
  fixed — the old count signal had **14 distinct values in its top 100** (86 of
  100 names chosen by arbitrary tie-break), the new dollar-weighted,
  recency-decayed, size-scaled intensity has 100/100 — but returns are still
  −5.16 %/yr with 0/8 positive and a placebo FAIL (71 of 100 random books won).
- Predictions scored **4½ of 8** (PF-1 scored 2 of 5).
- Harness re-validation: reproduced PF-1's ENGINE-ALPHA at **delta 0.000000**.

## NIGHT-3 deltas adopted (Murat's home-session review)

Branch `research/night-3-design` in aegis-finance (`a3c5a91`), per his
"research branch only, never main" instruction — say the word and it
fast-forwards to main. Full spec:
`docs/DESIGN_MEMORY_TAXONOMY_2026-08-09.md`; NIGHT-3 prompt revised in place.

Adopted: EXPERIENCE as the canonical unit of learning (one record per graded
decision, ~20 required fields, deterministic writer, loud-fail); episodic
(kNN over fingerprints, arm E) vs semantic (ABN posteriors, arm D) as
separately ablatable memories, with generalizations **rejected at write time**
unless they cite the n experiences behind them; decision persistence with the
forced OLD BELIEF → NEW EVIDENCE → UPDATE → NEW BELIEF schema graded for both
over- and under-reaction; the policy-coherence battery as a cheap monotonicity
gate before any economics; the NAME-ONLY arm as the contamination ceiling; and
the anti-reward-hacking guard on every arm.

Registry rows committed **before** their compute: `TRIAL-COHERENCE-BATTERY-1`,
`TRIAL-NAME-ONLY-1`.

Rejected/deferred and recorded so they are not re-proposed: multi-agent
personas, ten new paper accounts, neural representations (milestone: >100k
graded experiences), P&L-learning arms (own trial).

*(The anti-reward-hacking guard is already satisfied for PF-2: every meta book
runs at 0.0 % mean cash, so the meta result is not a cash-hiding artifact.)*

## Recorded process failure

Two campaign processes ran concurrently for ~10 minutes (an orphaned `nohup`
launch plus the tracked one) before detection. Write-once artifacts and
deterministic computation mean no result was affected. **This is the second
occurrence of this incident class** (PF-1 had the same), so it is now a pattern
rather than an accident.

## Open questions for Murat

1. **Is the regime-breadth gate right for long-only factor books?** Requiring
   positive excess in ≥4 of 5 blocks asks a value/quality book to beat the
   market during mega-cap melt-ups — close to demanding dominance rather than
   edge. ENGINE-ALPHA-2 delivers 15.58× the market's terminal wealth at
   two-thirds its drawdown and cannot graduate. **Deliberately not changed** —
   loosening a gate to admit the strategy that just failed it is the exact sin
   the standard prevents. Any change is dated and applies to PF-3 onward.
2. **Fire the holdout on PROF-COMPOSITE-150?** Attended, one read, bar frozen,
   failure final.
3. **Merge `research/night-3-design` to main?**

## Next

NIGHT-3 as revised — the masked decision replay, the EXPERIENCE store, and the
A/C/D/E memory ablation. PF-3 candidates: PROF-COMPOSITE-150 confirmation,
META-1's top-2 cell as its own registration, and the equal-weight-of-lanes
construction that beat the winner-chaser.
