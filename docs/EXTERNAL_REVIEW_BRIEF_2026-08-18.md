# EXTERNAL REVIEW BRIEF — 2026-08-18 (for GPT / Gemini / any reviewer)

You are reviewing two days of work on **Aegis Finance**: a pre-registered,
guard-railed investment research programme (one operator, LLM builders, paper
capital only). You have no assigned role. Attack anything — but every claim
you make must be checkable, and every proposal must be killable. Praise is
discarded; findings and better designs are kept.

## Context in six sentences

A 40-night forward LLM-forecasting campaign (IIF-1) is accruing: Nights 1–2
complete (585 + 600 records), first outcomes resolve 2026-08-21, the licensed
read is at 40 graded nights, primary loss is Brier on
`P(|return| > threshold)`. The research engine is being industrialized:
a job daemon with pre-committed priorities, a canonical ML dataset
(targets: rank/quantiles/magnitude/drawdown/barriers — NOT next-day sign,
which measured AUC≈0.50 vs MDE 0.034 while magnitude/vol are learnable), and
a cost model just calibrated against real millisecond-TAQ NBBO spreads
(182 tickers: median 2.73bp one-way; the declared 1–5bp band held with
16/137/29 below/inside/above; UPDATE 08-18 late: two renamed names
re-pulled under their current symbols — MMC→MRSH, SQ→XYZ — panel now
16/139/29 of 184, only one genuinely dead name unresolved). Our own negative results bind us: 206
published predictors have median −0.12%/yr net; a learned conditional SHAPE
added nothing in three registered tests (G5); 87–95% of the earnings effect
arrives while the market is shut; terminal-return claims price at ~95 years
while risk/relative claims resolve ~30× faster. Ten paper lanes run forward
(inception 2026-06-08, no skill claims before 24 months); the most striking
number is the mirror lane (rules-managed copy of the operator's real book)
at −16.8% vs the operator's own management at −2.6%, and the first autopsy
cut says the gap is EQUAL WEIGHTING, not the optimizer. Everything below is
in the repo: orders `docs/HANDOFF_2026-08-18_BRAIN_ORDER_{15..19}.md`,
session docs `docs/SESSION_2026-08-18_*.md`, retrospective
`docs/HANDOFF_2026-08-19_SESSION_START.md`.

## Your goal

Find (a) design errors that would make a result wrong or unreadable, (b)
better standard methods we should be using, (c) what we have not thought to
test. Rank findings by expected impact on decisions, not by elegance.

## Research questions (answer any subset, cite sources)

1. **IIF-1 statistics.** We grade a paired Brier difference with the NIGHT as
   the unit (SE = max(IID, HAC) across ~40 nights), measured intra-night
   outcome correlation ρ≈0.06–0.07 (design effect ~3.5 at 40 names/night),
   MDE@40 ≈ 0.010–0.015, BSS vs PIT climatology + Murphy decomposition as
   diagnostics. Is night-as-unit with HAC the right variance estimator for
   paired probabilistic forecasts on overlapping horizons (h=5 overlaps
   nights)? Is there a standard better design (cluster bootstrap? Diebold–
   Mariano variants for Brier?) and what does the literature say about
   power for rare-event Brier differences at base rates 0.10–0.20?
2. **Pairwise relative-value learning.** We plan an incumbent-vs-candidate
   model: P(replacing A with B improves the portfolio net of costs, horizon
   H), trained on historical A/B pairs (pairwise logistic vs LambdaMART vs
   shared-weight MLP). Known pitfalls of pairwise financial ranking —
   label dependence when pairs share dates/securities, calibration of
   pairwise probabilities, and whether learning-to-rank beats pointwise
   scoring out-of-sample in low-signal cross-sections?
3. **Quoted → effective spreads.** We hold NBBO quoted spreads; effective
   spreads need the Holden–Jacobsen trade-quote alignment. What is current
   best practice (Interval/timestamp conventions post-2016 SIP; odd-lot
   handling; the Lee–Ready successor for sign inference), and what
   quoted-to-effective ratios are documented by liquidity segment so we can
   sanity-check our join before trusting it?
4. **Winner continuation.** After a stock is up +40%/+75%, what conditional
   variables have documented (out-of-sample, post-publication) power to
   separate continuation from exhaustion — analyst revision acceleration,
   profitability, financing/dilution, options-implied expectations? We know
   the trailing-stop evaluation trap; cite designs that avoid conditioning
   on the path being evaluated.
5. **Event resolution curves.** For earnings/FDA/M&A/guidance: measured
   splits of the announcement move across after-hours vs open vs days 1–20
   (post-2015 data preferred). We measured 87–95% of the earnings effect
   arriving while the market is shut — what does the literature say about
   the *remaining* tradable fraction and its decay (PEAD in the modern,
   post-publication era)?
6. **Equal weight vs optimized weighting in small concentrated books.** Our
   14-point gap attributes to weighting scheme, not selection. Documented
   magnitude of EW-vs-optimizer differences in 10–30 name books, and known
   artifacts (rebalance timing luck, small-sample HRP instability) that
   could produce a gap this size in 70 days without any real inferiority?
7. **Fact check:** Bloomberg Global Trading Challenge 2026 — has a
   registration window been announced? (Do not infer from prior years.)

## Rules for your output

Cite the specific doc/claim you are attacking. Distinguish "wrong" from
"underpowered" from "not yet tested" — they get opposite remedies here. If
you propose an experiment, include the data it needs, its n, and what result
would kill it. Subgroup findings imported from literature are tagged
`hypothesis_source` and capped at adaptive-historical-validation — say so
when you import one.
