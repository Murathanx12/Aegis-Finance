# STRATEGY CONTRACT — Revision-6M (monthly overlapping cohorts)

**STATUS: DRAFT / NOT YET FROZEN.** This document freezes only when the book
goes live (post-judging, attended, via the `seed-a-lane` discipline — Murat
flips the flag; sessions never improvise a seed). Until then every field is
amendable. The policy hash and timestamp fields below are deliberately blank:
a hash stamped before the final text is a forgery of a commitment.

| field | value |
|---|---|
| licence | `PRODUCT_EXPERIMENT` (three-licences doctrine, CLAUDE.md 2026-08-23) |
| book | hack2 (post-judging fleet remap, `docs/REVIEW_2026-09-03_GPT_VERDICTS_AND_CAPITAL_ALLOCATOR.md` PART B — **ATTENDED**, nothing redeploys before judging completes 2026-09-04) |
| policy hash | _to be stamped at freeze_ |
| frozen at | _to be stamped at freeze_ |
| evidence base | `backend/data/optimus/tracker_backtest/holding_period_policy_20260903.json` (parent) and `backend/data/optimus/tracker_backtest/revision_6m_cohorts_20260904.json` (this study) |
| backtest code | `scripts/revision_6m_cohorts_run.py` (engines tested in `backend/tests/test_revision_6m_cohorts.py`) |

## 1. Objective (declared, not implied)

Maximise **terminal wealth net of costs** against the **value-weighted
market** (paper benchmark instrument: SPY). The equal-weighted market is a
secondary diagnostic only — it is a size portfolio wearing a market's name.
Personality: balanced. No leverage; the leverage ladder (1× → 1.5× → 2×)
belongs to a later contract revision and each rung is graded on compound
wealth after drawdown before the next rung.

## 2. Admission rule (exact — replicated from the S36 `rev_top50` selector)

A name is admissible for the month-*m* cohort iff, at the formation vintage:

1. **Band prior v2 admissible region** (`learner/prior.py`,
   `band_prior_v2/2026-09-01`): consensus-target-to-price ratio in
   **[1.5, 5.0)**, close **≥ $2.00**, analyst coverage **≥ 2**. The ≥ 5.0
   band is toxic-excluded (the only FDR-surviving band rule); < $2 is
   no-opinion, never "historically bad".
2. **`target_rev_1m` is non-null**: the 1-month percent change of the IBES
   consensus mean price target, valid only when the two consecutive monthly
   vintages are 20–45 days apart (`learner/dataset.py` line ~467). A stale
   or gap-ridden consensus produces no signal, not a zero.
3. **Rank**: descending by `target_rev_1m`; take the **top 50**.

`upside`/ratio unit discipline: the ratio is target/price, NOT target/price−1
(S33b). The revision is a ratio of consecutive `meanptg` values and is
unit-safe across splits only because IBES adjusts; `split_prior_year` names
remain subject to the standing "upside unreadable" rule at the prior level.

## 3. Cohort mechanics (the review's design)

- The sleeve is **6 overlapping monthly cohorts** (Jegadeesh–Titman calendar
  time). Each month ~**1/6 of sleeve capital** reforms into that month's
  top-50; each cohort is **held 6 months**, buy-and-hold within the cohort
  (no intra-cohort rebalancing — the daily-rebalance arm priced "touching
  it" at ~5.1%/yr drag at 25 bps and it buys nothing).
- Formation is PIT: the IBES `statpers` is already lagged one day by
  `learner/dataset.py`; entry is the **first close strictly after** the
  vintage date.
- A delisted name's CRSP `ret` carries the delisting return where the daily
  file has one; proceeds sit in cash for the remainder of that cohort's
  holding period (dropping it would delete exactly the failures a 6-month
  hold is supposed to be punished by).
- A name may appear in several cohorts at once; that concentration is the
  signal's own persistence and is not deduplicated away.

## 4. Falsifier exits (typed triggers only — no discretionary exits)

Within the 6-month hold a position exits early **only** on:

| trigger | definition | check frequency |
|---|---|---|
| toxic-band entry | the name's newest vintage ratio ≥ 5.0 | at each monthly vintage |
| delisting | CRSP delisting return applied | as it occurs |

Proceeds **park in the market instrument (SPY), never cash** (S36 stop-side
rule; PART B: cash requires a thesis, benchmark is the default parking
orbit), and are recycled into the sleeve's next monthly reform — the slot is
freed, not left idle. Per-name stops are deliberately absent from v1: the S34
decomposition receipt showed the tracker's stops firing on **beta**, and the
parent study's stop arms bought nothing the toxic exit didn't. If forward
paper shows a stop is needed, that is a contract revision, not an override.
The backtest also measured a left-band (< 1.5) exit variant and a 20% stop
variant; their numbers are in the receipt so the freeze can pick with eyes
open.

## 5. Costs and fill convention

- Backtest: costs in **bps per side on measured traded notional** (turnover
  measured from the simulator's own weight changes, never assumed); arms
  reported at 0 / 10 / 25 / 50 bps, headline at 25. Gross (0 bps) is
  decomposition only, never the headline. `zero_cost_diagnostic` discipline
  applies.
- Paper execution: Alpaca paper, **shares-only, DAY limit-or-market at the
  regular-session open following the formation vintage**; never `tif=cls` on
  paper (S32: partial fills), never `opg` (S36: paper venue does not fill
  opg, 13/15). Fills recorded at actual paper fills; slippage vs the
  backtest's close-entry convention is itself a tracked number, not an
  excuse.
- Universe execution floor: **$3.0m/day** dollar volume (S29) — names below
  it are marked OBSERVE_ONLY/unbuyable, **not deleted** from the cohort
  record (S30: a constant doing two jobs deleted WBUY; we record the opinion
  and refuse the trade separately).

## 6. Sizing and risk (session-start protocol §4 numbers)

- Equal weight within a cohort: 50 names × (1/6 sleeve) ⇒ ~0.33% of sleeve
  NAV per name per cohort; a name in all six cohorts caps at ~2% of NAV.
- Gross ≤ 100% of sleeve equity. No shorting, no options, no margin.
- Worst case in dollars: with no per-name stop the bound is the gross cap ×
  realised drawdown. The measured substitute (parent receipt,
  `risk_bounds_at_100pct_gross.rev_top50_H6m_25bps`): max drawdown
  **−43.6%**, worst rolling 12m in receipt. On a $100k sleeve the modelled
  worst case is **≈ −$44k over a cycle**; that number is quoted at seeding,
  not discovered after.

## 7. Falsifiers for the BOOK (what kills the experiment, pre-declared)

1. Forward paper excess vs SPY, measured monthly, whose running mean falls
   below the backtest's 5th-percentile path for 6 consecutive months.
2. Realised annual turnover > 2× the backtest's measured turnover (would
   mean the mechanics were not implemented as specified).
3. Any PIT breach (a formation using a vintage not yet public) — immediate
   halt, not a data point.
4. The toxic-exit trigger firing on > 25% of the book in a single month —
   band prior regime break; halt and re-adjudicate (the band was already
   dead 2022–24 as an admission rule; this book leans on the revision, and
   the receipt's 2022–24 sub-window is the evidence to re-read).

## 8. Evidence summary (filled from the receipts; numbers, not adjectives)

Parent (S36, `rev_top50/fixed_H6m_25bps`, 2015-02→2024-12): terminal wealth
**3.743×** vs VW market **3.236×**; excess CAGR **+1.67pp**; paired monthly
t vs VW **0.69** (NW3 0.75); vs EW market t **1.48**; max drawdown
**−43.6%**; annual turnover **3.65×**; implied cost drag at 25 bps
**0.91%/yr**; breakeven vs the 12m hold **59.6 bps/side**. The t against the
VW market does NOT clear any significance bar — this is a
PRODUCT_EXPERIMENT, and the claim licensed is "worth paper-trading", not
"this is alpha".

This study (`revision_6m_cohorts_20260904.json`, all at 25 bps/side unless
noted; replication of the parent arm exact at every cost tier):

- **Cohort vs naive full-rebalance-every-6m**: the naive book is a lottery
  over its start month — terminal wealth **1.894× to 6.044×** across the six
  phases (paired t vs VW −0.276 to +1.479), phase mean 3.692×. The
  overlapping-cohort book delivers **3.743×** at essentially identical
  turnover (extra 0.019×/yr), i.e. the phase risk is removed for free. The
  phase cannot be chosen ex ante; the spread IS the argument for cohorts.
- **Falsifier variants**: toxic-only exit TW 3.721× (a wash vs no-falsifier:
  paired t 0.55; 476 exits, all toxic); **toxic + left-band exit TW 3.766×,
  max drawdown −39.0% vs −43.6%, t vs VW 0.73** — the best variant measured;
  adding a 20% stop HURTS (TW 3.474×, 3,798 stop firings) — stops fire on
  beta, again.
- **Null (64 draws, random top-50 from the same admissible pool, identical
  engine and costs)**: observed monthly excess +0.341%/mo sits above every
  draw (null p50 −0.114, max +0.123) — percentile 1.00, **p_one_sided
  0.0154** (the add-one floor at 64 draws). The revision RANKING is real
  relative to its pool; the pool-vs-market question remains the t 0.69.
- **Breakeven vs VW market: 74.5 bps/side** (gross excess +2.71pp / 3.64×
  turnover).
- **2022–2024 sub-window (the band's dead years): revision does NOT clear
  the market there either** — cohort excess CAGR **−4.3pp/yr**, t −0.25
  (absolute TW still +11.8%; market +26.3%). Falsifier variant −4.1pp. The
  edge is regime-conditional like everything else in this panel; falsifier
  #4 below exists for exactly this.

## 9. What freezing requires (checklist for the attended seeding)

- [ ] Judging complete (2026-09-04 11:00 ET) and fleet remap authorized.
- [ ] Murat picks the falsifier variant (draft default: **toxic + left-band,
      market-park** — the measured best on both terminal wealth and drawdown;
      toxic-only is the conservative alternative; the stop variant is
      measured and worse).
- [ ] Policy hash = SHA256 of this file's frozen text + the exact admission
      code paths; stamped with timestamp.
- [ ] `seed-a-lane` skill run; env-gated flag flipped by Murat.
- [ ] First decision recorded BEFORE any order (frozen contract precedes the
      first decision — the licence's one hard requirement).
- [ ] New Alpaca keys minted (S36: finance mirror/arena keys REVOKED).
