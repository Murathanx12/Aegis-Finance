# Adjudication — prediction-market arbitrage, probability models, information diffusion (2026-08-21)

Murat: *"I have been told they are great for quant finance, a lot of projects
use them — make sure if we are rejecting it's for good reasons, and what else
we can use. Profit maximization / max ROI is the goal."*

He is right that these are real quant tools. This document separates what is
genuinely rejected (with reasons that survive that fact), what was never
rejected, and what is now being USED — because the correct response to "firms
profit from this" is measurement, not assertion in either direction.

## 1. Prediction-market arbitrage / mispricing

**The claim is true.** Cross-venue arbitrage (Kalshi vs Polymarket) and
market-making on event contracts made real money for real firms, publicly
reported through the 2024 US election cycle. Susquehanna market-makes on
Kalshi. This is not a fake idea.

**Why the EXECUTION engine is still rejected for us, specifically:**

1. **We do not execute.** The platform's oldest design line ("not a trading
   bot — no execution, no live orders") is not squeamishness; it is what
   keeps every ledger in this programme honest paper. An arbitrage engine
   without execution is a contradiction in terms.
2. **The economics are venue-taker economics.** Measured fee schedules
   (2026-08-21, live APIs): Polymarket taker fee rate 0.04; Kalshi
   ~0.07·p·(1−p) round trip; plus both spreads. The gap must clear ~5¢ of
   probability before a cent is real.
3. **Speed.** The players who close these gaps run streaming feeds and
   capital parked on both venues. Our observation frequency is one daily
   snapshot. Racing them is not our comparative advantage; being right about
   slower things is.
4. **The house receipt.** R1 (2026-08-08): 6/6 LLM forecasters lost real
   capital on Kalshi even with crowd-matching Brier scores, and
   Economics/Business is the widest published LLM-vs-crowd calibration gap.

**What replaced assertion with measurement — TRIAL-PREDMARKET-2 (registered
today, linter PASS):** both venues are now snapshotted daily to a PIT corpus.
The registered metric: the share of matched contract-days with cross-venue
mid divergence above the 5¢ cost bar that PERSISTS to the next daily
snapshot. If ≥5% over ≥150 matched contract-days → the ESCALATE branch
produces a **written execution proposal for Murat's decision** (never
execution itself). If <5% → the rejection stands on receipts instead of
opinion. Either outcome is worth having.

## 2. Probability models

**Never rejected — this is the house's densest asset**: crash LightGBM +
logistic with conformal intervals, Cox proportional hazards, Bayesian
changepoint (BOCPD), 3-state HMM regime, jump-diffusion MC. What was missing
was an OPPONENT: every calibration claim was graded against climatology,
which is the weakest opponent there is. TRIAL-PREDMARKET-1 (registered
yesterday evening) fixes that: Kalshi's macro contracts are the crowd's
probability for the same observables, resolving in weeks — a fast-graded
benchmark ~30× quicker than lane-years. Honest prior: the market wins; the
value is the graded ledger and the discipline of losing to a named opponent.

## 3. Information diffusion models

**Deferred with a build path, not rejected.** The literature is real:
post-earnings drift as slow diffusion, economic-links momentum
(Cohen–Frazzini customer–supplier lead-lag), media-coverage spillover. Two
honest cautions: (a) the published-anomaly base rate here is brutal — our own
206-predictor replication found net median −0.12%/yr; (b) a diffusion model
needs a link graph (supply chains, co-coverage) with PIT discipline, which we
do not yet have. The path: the WRDS substrate (closing tonight) + the arena's
typed event corpus make a lead-lag precursor TESTABLE at scale. Candidate
trial DIFFUSION-LEADLAG-1 goes to the queue behind the Q1 universe-wide
features — with the corpse check run before a line of code.

## 4. What we can use now (the "what else" answer)

| Use | Status |
|---|---|
| Market-implied probabilities as calibration opponent for house models | TRIAL-PREDMARKET-1, corpus live from tonight 17:55 ET |
| Cross-venue divergence measurement → evidence-based verdict on arb | TRIAL-PREDMARKET-2, both venues live from tonight |
| Fed/CPI/payrolls contracts as fast-resolving macro event probabilities | in the corpus (KXFEDDECISION strikes captured on both venues in the live smokes) |
| Event-risk context for arena books (macro state variables) | queued — entering any scoring path requires its own registered trial |
| Lead-lag / economic-links diffusion precursor | queued behind WRDS Q1 features, corpse-check first |

**The standing sentence applies:** none of this counts as part of the profit
engine until it traces new information → changed forecast → changed capital →
executed paper decision → graded outcome. The trials above are how each
piece earns (or is refused) that path.
