# Negative Results — what Aegis measured and it didn't work

> This file exists on purpose, at the top level, where a skeptic finds it first.
> A project that runs anti-overfitting discipline *and* tells the truth about its
> negative results is rarer — and more trustworthy — than one that hides them.
> Surfacing this is consistent with [`docs/TRACK_RECORD_POLICY.md`](./docs/TRACK_RECORD_POLICY.md)
> and the fragility-not-timing reframe in `docs/V2_GOALS.md` (A5).

## 1. The timing strategy underperforms buy-and-hold

Source: [`backend/BACKTEST_RESULTS.md`](./backend/BACKTEST_RESULTS.md), signal
engine over 2020-01 → 2025-06 (66 monthly signals).

| Metric | Strategy | Buy-and-hold |
|---|---|---|
| Total return | **+250.9%** | **+740.0%** |
| Sharpe | **0.675** | **0.921** |
| Sell-signal 3M hit-rate | **28.6%** | (target was >55%) |

**Plainly: as a market-*timing* tool, the signal engine loses to doing nothing —
on both absolute and risk-adjusted return.** It is not buried, spun, or framed
away. It is the finding.

### Why this happens (and why it's not a bug)
The sell signals fire during high-VIX, sharp-drawdown periods — which in
2020–2025 were the *best* buying opportunities (mean reversion). All 7 sell
signals landed at VIX > 25; forward-3M returns after them were
`{+2.6, +26.1, +15.4, −0.04, −3.8, +2.8…+7.1}%` — wide and mostly positive. The
engine is **correct about current risk and wrong about forward return**. That is
the well-known, hard truth of short-horizon equity timing, not a defect unique to
this code.

### What we concluded
1. **Aegis is a risk-awareness tool, not a timing tool.** It tells you how exposed
   you are and why (SHAP), not when to jump out.
2. This is exactly why the **crash overlay is deliberately disabled** and why the
   north-star was reframed from *time the crash* to *measure fragility and scale
   exposure as systemic stress rises* (V2_GOALS A5). The research backs it: short-
   horizon crash timing has ≈0 information coefficient.
3. The honest test of whether *acting on Aegis* beats *ignoring it* is not this
   backtest — it is the **forward, leak-free, event-driven paper lane** (BACKLOG
   V4), whose NAV accrues only with elapsed time and cannot be cherry-picked.

## 2. 12-month crash prediction has no skill
The crash model's 3-month Brier (0.046) beats the base rate, but the **12-month
horizon ≈ climatological base rate** — no edge. Lagging indicators dominate its
SHAP at long horizons. The headline 3M number is also computed on a single
walk-forward path over only ~7 stress events. It is **now reported with a
block-bootstrap 95% CI + the positive-event count and a low-event warning**
(`engine.validation.metrics.brier_with_ci`, shipped 2026-06-14) — regenerating
the headline figure *with* its interval is a (slow) walk-forward re-run.

## 3. LPPLS (log-periodic bubble) predictive skill: refuted
Adversarially tested twice in the 2026-06-14 research phase; predictive skill was
refuted both times. LPPLS therefore ships as a **descriptive bubble-structure
flag only** — it never arms a lane and never emits a timing call.

## 4. A survivorship-free backtest universe is not buildable on free data
Source: [`engine/research/survivorship_audit.py`](./engine/research/survivorship_audit.py)
→ `docs/research/SURVIVORSHIP_AUDIT_2026-06-16.md` (run: `python -m engine.research.survivorship_audit`).

Every selection backtest draws its universe from `config.stock_universe` =
*today's* large-caps — survivors only. To de-bias it we'd need the delisted names
back in. We tested whether the free data layer (yfinance) can supply them: of 20
real S&P 500 names that later went bankrupt / were acquired / failed, **15 return
nothing, 4 return a *different* company on the recycled symbol, and only 1 is
genuinely usable (5%).** Controls (AAPL/MSFT/XOM) all clean; stooq was unreachable.

**Plainly: no backtested absolute-alpha number on our data is trustworthy** — it
is inflated by survivorship by an uncorrectable amount, and the DSR/PBO gate
cannot see it (it guards multiple-testing, not a biased universe — this is exactly
how vol-managed momentum printed a false "PASS"). The consequence is not despair:
the **PIT store accrues forward-only with an anti-leak `observed_at` field**, so
selection signals (insider buys, estimate revisions, 13F, multi-factor rank) are
validated by **forward information coefficient + paper-lane NAV**, never by a
historical backtest. Risk overlays (vol-management, ATR exits) are
universe-independent and unaffected.

## 5. The insider collector "ran" but fetched nothing in prod (silent-fragility catch)
Not a strategy result — a process result, and the most important kind. The T9
insider forward-IC collector passed all 12 offline tests and worked on the dev
machine, so the wrap-up reported it live. A **live prod check** (the discipline,
not the tests) found it failing **100% of its SEC fetches** — 50 warnings, every
one a 403 on `www.sec.gov/Archives/`. The IC clock looked alive and was accruing
nothing but fetch failures.

Root cause: `insider_form4` issued **raw, unpaced** `requests.get` calls instead of
routing through the process-wide SEC rate limiter that `edgar_events` enforces
(its own comment: *"ALL EDGAR HTTP must go through it"*). One collector run fires
~360–1000 fetches at `www.sec.gov`; on Railway's fast egress that trips SEC's
10 req/s threshold instantly, and SEC answers with **403, not 429**. Local dev's
handful of calls never tripped it — the classic "tested ≠ works in prod" gap.

The tell that pinpointed it: prod warned **only** on the high-volume Archives host,
never on the low-volume `data.sec.gov` submissions call — same User-Agent, so it
wasn't a UA/IP block; the only difference was request *count*. Fix (2026-06-17):
every SEC call now goes through one `_sec_get` choke-point — shared limiter pacing
(≤8/s), declared UA (env-overridable `SEC_USER_AGENT`), one 403-retry with backoff.
Verified live end-to-end. **The lesson: a collector that runs but fetches nothing
reads as "covered" on every green dashboard — only a live prod check sees the
silence.** T10 (revisions) and T8 (multi-factor) were audited the same way and are
healthy (yfinance paths, no SEC dependency).

## 6. The crash-model retrain "works" and still proves nothing (label sparsity)

The M3 retrain (2026-07-11) rebuilt `crash_model.pkl` end-to-end on the exact
live feature path (86 built → 20 selected; only **5 features survived LASSO**),
loads cleanly through the sidecar contract, predicts on live features without
raising, and passes 214 tests — and it is still **not deployable as a
prediction source**. Walk-forward AUC is *unmeasurable* (the purged validation
window contains zero ≥20%-drawdown events at every horizon), the outputs are
near-constant (the 6m head emits literally one value; trailing-2y std 0.00pp),
and the 12m headline (43%) is ~3× the unconditional base rate with no
demonstrated discrimination. Root cause is the **label**: daily crash-label
rates of 3.2/7.8/15.7% collapse to a handful of independent crash episodes —
a binary ≥20%-drawdown target cannot support learning on one market's history.
Decision: **hold the deploy** (an honest `model_not_deployed` beats a
skill-less number lighting up the overlay), keep TRIAL-CRASH's fragility
composite as the crisis read, and redesign the target per
`docs/research/CRASH_AND_OSS_RESEARCH_2026-07-11.md` (forward max-drawdown
severity via quantile trees, read out as multi-threshold exceedance
probabilities; benchmarked against STLFSI4-as-predictor before any promotion).
The CLAUDE.md "walk-forward AUC ≥ 0.70" health gate is unmeasurable for this
label and moves to PR-AUC/event-window metrics in the redesign.

## 7. The severity-model successor ALSO fails its pre-registered gate (TRIAL-CRASH-2)

The §6 redesign was executed 2026-07-14 under a protocol frozen BEFORE the
first fit (TRIAL-CRASH-2, commit `fe6edf3`): per-cell LightGBM exceedance on
forward SPY max-drawdown, {5,10,15,20}% × {30,60,90d}, expanding walk-forward
5 folds over 2016-2026 (purge 63td + embargo 21td), gate = positive held-out
Brier skill vs BOTH climatology and an STLFSI4-only logistic on all six dense
cells. **Verdict: REJECT — 0/6 dense cells passed.** Every dense cell shows
*negative* skill vs climatology (5% cells as bad as −0.32 to −0.54; the model
confidently over-predicts drawdowns out-of-distribution), and STLFSI4 itself
barely beats climatology. The honest nuance: the 10%-threshold cells show
real *ranking* signal (PR-AUC 0.13-0.16 vs prevalence 0.04-0.12 — up to ~3.6×
lift at 30d), but calibration is bad enough that the probabilities are
worthless as probabilities. A hypothetical TRIAL-CRASH-3 could test
train-fold-fitted calibration on top of the ranker — that is a NEW
registration, not a rerun. Third consecutive confirmation of canon A5
(short-horizon crash-timing skill ≈ 0 on free market/macro features); the
fragility composite remains the crisis read; the overlay stays
`model_not_deployed`. Full metrics:
`engine/training/output/crash2_eval_2026-07-14.json`.

## 8. EODHD fails its own pre-registered acceptance gate (14/20 vs bar 16)

Source: `engine/research/eodhd_acceptance.py`, gate frozen 2026-07-16 in
`docs/research/DATA_SOURCES_AND_BASELINES_2026-07-16.md`; run 2026-07-18 on
the paid All World plan.

**Phase 2 result: 13/20 delisted audit names usable, +1 rescued via the
`JAVA_old` alternate code = 14/20. Bar was >=16. FAIL — subscription
canceled, per the pre-committed rule.**

Failure anatomy (all seven, verified by hand):
- **Recycled-symbol contamination:** `CFC` (Countrywide, died 2008) trades to
  2019 in the EOD series; `BSC` in the delisted list is an *ETN*, not Bear
  Stearns; `MON` is a SPAC, not Monsanto. The naive symbol is a lie.
- **Genuinely absent:** EMC (died 2016), Everest Re's `RE` history (renamed
  EG), SBNY common stock (only preferreds/warrants present).
- **Rescued:** Sun Microsystems exists as `JAVA_old` (3,036 rows ending
  2010-01-26, the Oracle close) — the *script's* query was wrong, not the data.

Second-order finding: **Phase 1's 16/20 "PASS" was itself inflated** — its
membership check matched ticker codes, and two of those matches (BSC, MON)
were recycled symbols owned by different companies. A name-aware phase 1
would have scored ~14/20 and said *don't subscribe*. The gate design, not
just the data, had a false-positive path. (Money impact: one $19.99 month,
bounded by design — the two-phase gate did its job at the second fence.)

What survives: EODHD's coverage of **2017+ deaths is solid** (Yahoo, Time
Warner, Celgene, Allergan, Xilinx, Activision, Twitter, First Republic,
SVB, Pioneer, Seagen, Abiomed all usable). It is the pre-2016 record and
symbol-identity hygiene that fail. For a 2015->today replay that is not
good enough.

Consequence: the honest historical replay moves to **QuantConnect** (free,
survivorship-free, third-party-hosted) as the primary venue; **Sharadar
SEP** remains the local-data option if a quote comes back sane.

## 9. Long-only momentum beats SPY's return and STILL fails (TRIAL-MOM-BACKTEST #13)

Source: `engine/research/mom_backtest.py` on the survivorship-free panel
(50,462 names incl. 32,334 delisted), spec frozen BEFORE the panel existed
(`docs/TRIALS/TRIAL-MOM-BACKTEST-12-1-momentum.md`), one evaluation,
2017-01 -> 2026-06.

| | CAGR | Sharpe (rf=0) | Max DD |
|---|---|---|---|
| 12-1 momentum top-50 (net of 20bps/side) | **17.9%** | 0.629 | **-54.7%** |
| SPY | 15.3% | **0.871** | -33.7% |
| RSP (equal-weight control) | 11.8% | 0.693 | -39.0% |

**The verdict is FAIL on the pre-registered deciding metric** (Sharpe >= SPY
AND maxDD <= 1.25x SPY): Sharpe trails by 0.24 and the drawdown blows the
-42.2% bound by 12 points. The parameter-cloud annex (8 perturbations of
top-N/band/costs) puts every variant at Sharpe 0.53-0.64 — the failure is
structural (a momentum crash lives in the window), not a parameter corner.

**What makes this negative result valuable:** the strategy DID out-return
SPY by +2.7pp/yr and out-returned equal-weight by +6.2pp/yr — genuine
selection, at the top of the literature's realistic band. The failure is
the RISK: nobody holds a -55% drawdown, so the extra CAGR is not
collectible by a human investor. This is the honest, survivorship-free
version of "just pick winning momentum stocks" — it makes more money on
paper and is uninvestable in practice. Successor registered
(TRIAL-MOM-TREND #14): the same spec + the 10-month trend filter — the one
mechanism with surviving OOS evidence for truncating exactly this crash.

## 10. The trend-filter rescue makes momentum WORSE — inquiry closed (TRIAL-MOM-TREND #14)

Source: `engine/research/mom_backtest.py --trend`, spec frozen and committed
BEFORE evaluation (`c9a31ad`), one run, 2017-01 -> 2026-06.

| | CAGR | Sharpe | Max DD |
|---|---|---|---|
| #13 momentum, unfiltered | 17.9% | 0.629 | -54.7% |
| **#14 momentum + SPY 10-mo SMA cash filter** | **4.8%** | **0.307** | **-61.3%** |
| SPY | 15.3% | 0.871 | -33.7% |

**FAIL — and dramatically worse than the thing it was supposed to fix.**
The filter fired on exactly the right months (verified by hand: 2018Q4,
COVID Mar-May 2020, eight months of 2022, Jan 2023, Nov 2023, Apr 2025,
Apr 2026 — no sign bug). The mechanism of failure is the known one, at
full violence: a monthly-cadence trend rule TAKES the first leg of every
crash (exit lags by up to a month) and then MISSES the V-shaped rebound
(re-entry lags too). 2017-2026 contained five V-shaped recoveries and zero
1973/2008-style long grinding bears — the single regime where trend rules
earn their keep never occurred. Deeper maxDD than unfiltered is the
sell-the-bottom arithmetic: lock the loss, sit out the recovery, re-enter
at a lower base, take the next leg down.

**Per the pre-registered stopping rule: the momentum-lane inquiry is
CLOSED for this window.** No third variant. What survives: momentum stays
a component of the forward multi-factor IC trial; the +2.7pp/yr selection
evidence from #13 stands as descriptive context with its uninvestable
risk profile stated alongside. The honest conclusion of the pair: on
survivorship-free data, the two best-documented beat-SPY mechanisms in
the public literature both fail their risk-adjusted gates in this window
- which is precisely what the live-fund scoreboard (F-023) predicted.

## 11. FDA approval drift is dead net of costs at monthly resolution (TRIAL-BRAIN-006)

**Date:** 2026-07-24. **Registered:** module registry row 16 + doc committed
BEFORE the run (`investing-test-module` 30b7032; results cd1a7ba).

Pre-registered one-shot calendar-time test of post-approval drift on 671
matched, in-panel (shrcd 10/11) NDA/BLA original approvals 2002-2024, entered
the month AFTER approval (announcement pop excluded), 3-month hold, honest
costs, pharma-universe benchmark. Result: **REJECT** — Arm B large/mid
−30.1 bps/mo net excess (t = −0.89; gross t −0.68, so not even a cost story);
PRIORITY-review sub-arm t = 0.13; timing-permutation noise arm clean (gross
t = 0.06). If anything the sign points to approval-day full-pricing +
sell-the-news.

Two disclosures that bound the claim: (1) the micro-cap segment — where the
hypothesis actually lived — had 2 live months and is UNTESTABLE at monthly
resolution in this universe; a daily-CAR revisit on `crsp.dsf` would be a NEW
registration, not a rerun. (2) The crosswalk build caught an IBES-class data
trap first: openFDA `sponsor_name` is the CURRENT application holder, so PE
roll-ups "sponsor" approvals that predate their founding — 154 such events
excluded as unattributable rather than mismapped (the +91 bps/t=7.1 lesson:
book inspection before the run, not after).

## 12. The supplier thesis is fully adjudicated — no holding period works (TRIAL-THEME-SUPPLY)

**Date:** 2026-07-24. **Registered:** module registry row 18, committed before
implementation (`investing-test-module` fe067d5; results 55c83d8).

The slow basket arm of Murat's "buy the suppliers of the winners" thesis —
salecs-weighted 12-1 customer momentum, annual June formation, 12-month hold,
per-segment deciles, honest costs, explore window 2004-2018 only. This was
the arm batch 3b's cust_mom rejection explicitly left open, with the turnover
objection removed by design.

Result: **REJECT on both pre-registered kill conditions.** The B−A decile
spread is t = 0.10 (+3.2 bps/mo) — at annual cadence there is NO
cross-sectional information left in customer links; top and bottom deciles
are indistinguishable gross and both lose net (micro top decile −80.8 bps/mo,
t = −4.27). Noise arm clean.

The complete picture across both arms: monthly customer-link information is
real but too weak for its own 70% churn (3b); by the time a slow book could
hold it, it has already diffused (this trial). The thesis's receipt is now
two-sided — there is no holding period at which supply-chain links pay
retail-accessible costs on 2004-2018 CRSP. Revival requires a different
mechanism class (event-conditioned links on daily data), registered fresh.

## 13. A double-legged explore graduate dies at confirm — the wall works (TRIAL-BRAIN-010)

**Date:** 2026-07-25. **Chain:** `investing-test-module` 4480fd3 (batch-7
pre-reg) → e00f9e0 (graduation + confirm pre-reg BEFORE touching 2019+) →
edfdae8 (confirm result).

conc_low (diversified-customer suppliers — the mirror of batch 6's
book-inspected concentration reversal) became the first candidate since
gp-small to pass BOTH explore graduation legs (largemid net t 2.28, IC t
4.46, 7%/mo turnover). Return-blind book inspection passed. The single
pre-registered confirm run on held-out 2019-2024 at 50 bps stress costs:
**net −5.5 bps/mo (t = −0.20), DSR 0.0003 at N_TRIALS=140, FF6 alpha
negative.** KILL. The rank information persists out-of-window (IC t 2.6) —
the tradeable premium does not.

Why this entry matters more than another dead signal: it is the first
live-fire validation of the explore/confirm wall on a full-strength
graduate. A signal good enough to clear a two-legged in-window bar — with a
disclosed sequential-mirror provenance and a clean book — still evaporated
out-of-window. "Explore numbers are hypothesis generation, never evidence"
is now an empirical statement about this factory, not a slogan. Also
recorded: Ball et al.'s RE/ME (the strongest-prior candidate of the day)
failed the explore bar in 2004-2018 — value's lost decade shows up honestly
rather than being rescued.

## 14. The self-deception ceiling, measured (INSTR-OVERFIT-CEILING) + monthly PEAD is inverted

**Date:** 2026-07-25. **Chain:** `investing-test-module` 0297101 (pre-reg,
contamination clause) → run same day (one shot). Companion: batch 8 (146
cumulative), zero graduates.

We measured what pure post-hoc selection can manufacture on our own data:
full-window (2004-2024) scans of the 53-signal CLOSED-family library
(insider family excluded as live), then mining arms with no information
content whatsoever.

- **Pick-the-best honest-direction signal: t 2.94. Top-5 composite: t 3.27.**
  The zero-skill expected maximum for a library this size is **t ≈ 3.6-4.0**
  (Bailey/López de Prado) — i.e. the best full-sample results our entire
  closed library can show are INDISTINGUISHABLE from selection noise.
- **Allow sign-flips (the realistic mining move — we have 4 of our own on
  record) and you get t 6.16 single / 6.58 top-5, Sharpe 1.44** — a fake
  track record most funds would envy, built by flipping dtc_low. It even
  survives a split-half check (t > 3 in both halves) because the dtc book
  effect is a real full-window mean effect WITHOUT rank IC — exactly the
  batch-6 AND-rule catch. Fragility checks do not stop this class; only the
  two-legged rule (book AND rank) plus cost honesty do.
- **t≈7 "bug alarm" is now calibrated:** mining tops out ≈6.6 here, so
  anything ≥7 on this data is a book/data defect, not alpha.
- **The wall's decay curve, on all 53:** explore→confirm t rank-correlation
  0.49; the top of the explore table shrinks 60-100% (dtc_qual 3.39→1.30,
  conc_low 2.28→−0.05 — §13 reproduced). Disclosed with both hands: the
  value class IMPROVED out-of-window (re_me 0.28→1.30, payout 0.80→1.63) —
  the wall has a false-negative cost, those families stay closed anyway
  (contamination clause), and the lesson routes to the ALLOCATION layer
  (regime dependence), not to resurrecting dead pickers.

Same day, batch 8: **pead_agree came out INVERTED** (IC t −2.6 both
segments) — agreement-gated PEAD, the literature's flagship refinement
(Livnat-Mendenhall), is wrong-signed at monthly cadence in 2004-2018. Fifth
sign reversal on record; monthly-cadence PEAD is closed, and the only
admissible successor class is a daily-resolution event harness.

## 15. Regime rotation dies at confirm; the correlation "master switch" fails first contact (INSTR-MACRO-BATCH4)

**Date:** 2026-07-25. **Chain:** `investing-test-module` cb494ed (freeze) →
0c758c7 (explore results + confirm pre-reg BEFORE 2019+ touched) → confirm
same day, one shot.

The statistical jump model (the panel's recommended replacement for HMMs —
and mechanically it delivered: 0.4-1.0 switches/yr, no whipsaw) passed ALL
three pre-committed explore bars on 2004-2018: 11.2% CAGR vs SPY 7.7%,
maxDD −26.6% vs −55.2%. The held-out confirm window rejected it: **2022 cost
−21.6%** (the model went risk-off into TLT during the dual stock-bond
crash — the "safe" asset was the crashing asset) and 2020 dodged the crash
but missed the rebound (+4.8% vs SPY +18%). Both frozen bars missed.
The explore pass was one crisis (2008) wearing three bars as a disguise.
Regime timing with a single safe asset is CLOSED; successors (multi-asset
risk-off basket, VIX features) need new registrations carrying this receipt.

Same run, descriptive: the reviews' most confident macro claim — "disable
dip-buying when stock-bond correlation flips positive" — is refuted
in-window: dips during POSITIVE correlation bounced harder (+2.9% fwd-21d,
n=50) than dips in negative-correlation regimes (+0.6%, n=705). Thin n and
no 2022-style regime in-window, disclosed — but the gate is not adoptable
on this evidence. GPR spikes are also not a sell signal (SPY CAR(0,+30)
+0.61%, 64% positive; oil FADES −2.5% excess).

The other side of the same day: **INSTR-TSMOM-XA is the first macro
instrument to SURVIVE the wall** — crisis alpha in both unseen crises
(2020 +9.2%, 2022 flat), overlay maxDD −18.8% vs SPY −33.7% — at a real,
disclosed price (overlay return drag t −1.86 vs SPY). It is a defensive
diversifier for the product's protect-the-investor goal, not a beat-SPY
engine, and it goes to a forward paper lane (attended) before any claim.

## 16. FDA approval drift is dead at daily resolution too (TRIAL-BRAIN-011)

**Date:** 2026-07-25. **Chain:** `investing-test-module` f6d1648 (pre-reg,
crosswalk v2 signed off by Murat + programmatic validation) → run same day,
one shot. Explore events only; the confirm gate never opened.

The pre-declared daily successor to BRAIN-006: market-model CAR on 500
usable NDA/BLA approvals 2002-2018 (drops counted: 153 dedupe, 247 outside
the pharma-SIC daily slice). CAR(+1,+20) = +2.1% but **t = 1.45** against a
frozen bar of 2.0 — REJECT. What the corpse teaches: the drift, to the
extent it exists, lives entirely in days 1-5, entirely in the small half
(+4.0% vs +0.2%), and in HIGH-attention events (+3.6% vs +0.6%) — the
opposite of the "low-attention drift" gate two AI panels proposed. Day-0
reaction is real (t 2.04) but not tradeable close-to-close. Priority
approvals show LESS drift than standard ones (better pre-priced).

FDA approval drift is now closed at BOTH resolutions with receipts. The
forward-only PDUFA ledger (a different event class with a different clock)
remains the house's only live FDA instrument.

## 17. Analyst price targets are anti-signal — the un-voided family is worse than dead (TRIAL-TGT-REBUILD)

The target-price family was VOID for a year (the original run used IBES
split-adjusted values, a look-ahead). WRDS batch 4 delivered nominal ptgdet
plus the ibes_adj split calendar, so the rebuild used NO adjustment
arithmetic at all: nominal median 12m target vs nominal CRSP price, with any
target straddling a split event simply dropped. Two pre-registered arms
(#154-155), priors declared: raw upside flat-to-negative, low-dispersion
conditioning (PSZ, Mgmt Sci 2025) positive.

Result: **raw implied upside is strongly perverse** — largemid −90 bps/mo
net (t −3.62, IC t −3.47), small −199 bps/mo (t −7.21). The names analysts
say will rise 40% are precisely the names that bleed. Da-Schaumburg
optimism bias, reproduced on clean data at honest costs. The PSZ
conditioning halves the bleed (−90 → −43.5) — the published DIRECTION is
real — but never reaches a positive sign (IC t −3.77): on our universe the
conditional effect does not exist as a tradeable long signal.

Lessons banked: (1) analyst-source pickers are now 0-for-3 (rev_conf,
tgt_upside, tgt_ld) — the sell-side consensus is either priced or
perverse; (2) a mirror (long LOW-expectation names) is admissible as a
future candidate but carries 22–45% turnover — the house law predicts net
death, so it is not queued; (3) the un-voiding protocol worked: a voided
family now has an adjudicated grave instead of an asterisk.

## 18. The post-hoc repair failed to fix the crash it was built for (INSTR-REGIME-JM2)

**Date:** 2026-07-26. **Chain:** `investing-test-module` 470ed0f (freeze,
provenance declared, BEFORE data fetch) → one execution, both windows.

JM1 died at confirm because TLT crashed alongside stocks in 2022. JM2 was
the sanctioned successor: an inflation gate (T10YIE 126-day momentum >
+0.10pp) routing risk-off capital to GLD instead of TLT when breakevens
rise. The registration declared post-hoc-repair provenance up front:
explore ≈ zero evidential weight, confirm weakened (the motivating event
sits inside it), forward the only clean test.

Explore 2004-2018 FLATTERED the repair — CAGR 12.2% vs SPY 7.7%, maxDD
−20.4%, calendar-2008 +32.4%, better than JM1 on every line. Had explore
carried weight, JM2 graduates.

Confirm 2019-2024: **REJECT, and the gate made 2022 WORSE than the design
it repaired** (calendar-2022 −23.9% vs JM1's −21.6%; t JM2-vs-JM1 −1.18).
Mechanism: 2022's bond crash was REAL-RATE-driven — breakevens peaked in
April 2022 and fell through the worst of the TLT collapse, so an
inflation-momentum gate switched risk-off capital back INTO TLT precisely
when the repair was supposed to route it out (only 9.5% of confirm
risk-off days were gated away from TLT). No gate lookback (63/126/252)
rescues it — the failure is the gate's information, not its speed.

Lessons banked: (1) the zero-weight declaration for post-hoc repairs was
EARNED — the explore pass measured exactly nothing; (2) repairing a design
against an observed crash does not even guarantee fixing THAT crash — the
repair encodes your story about the event, not the event itself; (3)
single-trigger regime rotation (state machine + one macro gate) is CLOSED
with two receipts; successors need a different information class and
inherit both.

## 19. LLM/agent trading alpha is comprehensively dead — external receipts (family stays closed)

Not our run — banked external evidence, 2026-07-27 sweep (adjudicated
AI_PANEL_2026-07-27F), closing a family we would otherwise be lobbied to
revisit. INSTR-VOC already found the complexity class adds nothing on our
data; the outside record now says the same thing with receipts:

1. **The flagship paper was withdrawn.** Kim, Muhn & Nikolaev (arXiv
   2407.17866, "GPT-4 beats analysts at earnings direction") — withdrawn
   2025-02-20 after a co-author's own replication of the paper's analyses
   found inconsistencies. Internal replication failure within ~7 months.
2. **Independent multi-system evaluation kills the agent literature.**
   FINSABER (arXiv 2505.07078, KDD 2026): FinMem / FinAgent / FINCON /
   Lopez-Lira-style prompting alpha disappears over 2004-2024 across 100+
   symbols after commissions; buy-and-hold beats the agents on most headline
   names. The favourable literature rests on a ~6-month 2022-23 window and
   hand-picked large caps. Failure is regime-asymmetric (risk-on in bulls,
   risk-off in bears) — not fixable by framework complexity.
3. **The one honest replication self-describes as infeasible.** Glasserman &
   Lin (arXiv 2309.17322): the GPT headline-sentiment long-short is
   profitable only gross, daily-rebalanced, short-heavy — "not a feasible
   strategy" per the authors. Bonus finding: anonymizing tickers IMPROVED
   returns (the model's company knowledge is a negative distraction), and
   the edge concentrates in LARGE caps.

Standing rule reaffirmed: the LLM narrates, the deterministic engine
computes, nothing LLM-derived allocates. Any future LLM-signal proposal must
rebut ALL THREE receipts in its registration, not just cite a new paper.

## 20. Distress-8-K "drift" is selection, not information (TRIAL-EVENT-8K-FILTER)

Batch 10 ran the Lerman-Livnat reframe: names filing a distress 8-K (items
1.03 bankruptcy, 2.04 obligation acceleration, 5.01 control change) should
earn significantly negative forward returns, usable as a long-only EXCLUSION
screen. Acquisition was clean — 4,860 EDGAR daily indexes 2004-2024, zero
failed days, 1,530,116 8-K originals, 3,949 flagged events inside explore.

The headline passed its pre-registered bar and is still worthless:

| arm | 3m market-adjusted | t | n |
|---|---|---|---|
| B — flagged (the claim) | -5.95% | -7.06 | 1,264 |
| A — same names, dates -12mo (expected ~0) | **-6.79%** | **-11.33** | 2,528 |

**The control beat the treatment.** The pre-registered pseudo-event arm, whose
declared job was pipeline validation, produced a larger negative effect than
the hypothesis it was there to null out.

The attrition audit says why, and it is not subtle. Of the same 3,949 events,
Arm B keeps 1,264 (32%) while Arm A keeps 2,528 (64%); the gap is almost
entirely one filter — **2,574 events (65%) are dropped from Arm B because the
name is no longer in the liquid universe** (dollar-volume rank <=3000) at the
filing month, versus 1,408 (36%) a year earlier. Segment eligibility is
evaluated at formation, so by the time a firm files for bankruptcy it has
usually already fallen out. Arm B silently excludes the worst distress cases;
Arm A retains them. The arms measure different cohorts, and the measurement
conditions on survival-to-event.

The calendar-time arm agrees from the other direction: the flagged cohort runs
-79.7 bps/mo (t -1.50, below the bar) against the pseudo-cohort's -229.4
bps/mo (t -11.10).

**What this means generally:** a naive event study on distress items recovers
firm-level distress persistence plus universe-eligibility selection, and will
report ~-6% per quarter with a t-stat near -7 while measuring nothing about
the filing. These firms were doing worse a year BEFORE the event. Any
event-study design on a distressed cohort must fix eligibility at a pre-event
date and must carry a same-firm displaced-time control -- without the control
this would have graduated to confirm as a clean pass.

Not filed as a family closure: the frozen kill clause requires a non-negative
cohort, which is not what happened. The family is UNADJUDICATED and any
successor needs a new registration with a valid control. The confirm window
(2019-2024) was NOT opened -- spending the held-out window on an
uninterpretable explore result is exactly what the wall exists to prevent.

## 21. Conditional volatility targeting is dead too — the 2020 crash outran the signal (TRIAL-COND-VT)

**Date:** 2026-07-29. **Chain:** `Aegis module` TRIALS/TRIAL-COND-VT.md +
registry row (frozen 06:30 UTC) -> `scripts/trial_cond_vt.py` written after ->
explore run -> confirm run, one shot each. Registered under the freeze's S3
de-risking door, cumulative candidate 159.

Continuous/unconditional volatility targeting was already on the dead list
(Liu-Tang-Zhou 2019; Cederburg et al. 2020 Jobson-Korkie **p = 0.30**;
DeMiguel et al. 2024 OOS-net-of-costs **p = 0.979**; Angelidis-Tessaromatis
2023). The one survivor was Bongaerts, Kang & van Dijk (FAJ 2020)
**conditional** VT — adjust exposure only in the extreme-vol state, unscaled
otherwise, leverage capped: US dSharpe **+0.16**, dMaxDD **-8.3%**, turnover
**1.6x/yr**, significant in only **2 of 10** markets, **no post-2010 split.**
This trial supplied the missing split: long-only, cap 1.0, SPY, month-end,
2 bps, held-out 2019-2024.

| | explore COND_VT | explore SPY | confirm COND_VT | confirm SPY |
|---|---|---|---|---|
| Sharpe | **0.615** | 0.497 | **0.836** | 0.897 |
| max drawdown | **-40.19%** | -55.19% | **-33.72%** | **-33.72%** |
| CAGR | 8.57% | 7.69% | 14.55% | 17.12% |
| turnover | 0.41x/yr | - | 0.85x/yr | - |

Explore passed all three pre-registered bars (Sharpe >= SPY-0.05, maxDD
shallower by >=5pp, turnover <=50%/mo). **Confirm missed two.** The drawdown
bar did not miss narrowly — the overlay's max drawdown is **identical to SPY's
to four decimal places, on the same trough date (2020-03-23)**. Bootstrap 90%
CI on the Sharpe difference vs SPY: **[-0.164, +0.055]** — indistinguishable
from doing nothing, while giving up 2.6pp of CAGR.

**The mechanism of failure, from the frozen weight path.** At month-end
2020-02-28, trailing 63-day realized vol was **0.162 against a causal
80th-percentile breakpoint of 0.2018** — because 60 of those 63 days were the
calmest market in years — so the rule entered March at **w = 1.00** with SPY
already ~12% off its high. It then cut to 0.373 / 0.345 / 0.350 for
March/April/May: the rebound. Result: 2020 **+3.28% vs SPY +18.33%**, with the
full drawdown taken anyway. 2022, the rule's home turf, worked exactly as
designed (gradual de-risk 1.00 -> 0.73 by June) and bought **+2.3pp of return
and 1.8pp of drawdown** — correctly signed, an order of magnitude short of the
bar.

**A backward-looking 63-day vol window crossed with an expanding-window
quantile is a SLOW threshold: it cannot fire before a fast crash and barely
fires during a slow one.** Those are the same defect seen from two sides, and
no lookback or threshold value fixes it — none was tried (frozen kill clause).

**The contrast exhibit came out backwards and is reported that way.** The
descriptive UNCONDITIONAL arm (w = min(1, causal-median-vol/current vol),
registered as expected-to-fail) beat the conditional arm on **both** Sharpe and
max drawdown in **both** windows (explore 0.687 / -27.11%; confirm 0.871 /
-29.40%). This does not revive it — it also fails the confirm drawdown bar
(4.3pp vs the 5pp requirement) for the same 2020 reason, and four published
refutations are not overturned by one instrument on one 21-year sample. What it
does mean is that the Bongaerts extremes-only refinement, which *was* the
hypothesis, bought nothing over the plainer rule.

**Costs were never the executioner:** 0.8-1.7 bp/yr of drag, and every bar is
unchanged at the 10 bps stress. Consistent with the freeze finding that our
rejections are informational, not cost-driven.

**Third allocation instrument killed by the wall** (after INSTR-REGIME-JM and
INSTR-REGIME-JM2), and the same pattern each time: an explore pass carried
almost entirely by 2008 (dMaxDD +15.0pp) collapses on 2020+2022
(dMaxDD **0.00pp**). Family CLOSED; no paper lane; any successor addressing the
resolution failure (intra-month trigger, faster estimator) is a new
registration against the deflation count.

## 22. The small-cap shelf: the graduation door was shut on a backwards cost premise, and opening it changes nothing (INSTR-SMALL-SHELF)

**Date:** 2026-07-30. **Chain:** `Aegis module` c95a97b (registration frozen
BEFORE any run code existed) → `scripts/run_instr_small_shelf.py` written after
→ one run. Cumulative candidate 160.

### The defect that motivated the trial

`docs/STRATEGY_FACTORY.md`, frozen 2026-07-22, defines the graduation rule on
**largemid only**, and justifies excluding the small segment like this:

> `small` — ranks 1001..3000. Reported, but **25 bps understates true small-cap
> costs**; treat small-only results as directional.

For the whole 159-candidate search, the small segment was therefore
structurally ineligible to graduate. Later registrations hardened it further
("small documented 50 bps"). **INSTR-COST-MODEL then measured the thing and the
premise is backwards:** Kyle-Obizhaeva half-spreads in small are **13.1 / 12.1 /
11.6 bps** by era, against a flat wall of 25 (scans) to 50 (documentation) — a
2-4× *over*-penalty, not an under-penalty. The largemid propagation of that
measurement ran in round 10 (INSTR-COST-REMEASURE-REJECTS, cohort EMPTY, shelf
closed). **Small never received it.** This trial performs it, once, under the
identical frozen cohort rule with only the segment changed.

### Result: cohort NON-EMPTY (5 members), **ZERO graduates**

| signal | source | t_ic | t_gross | t_net flat-25 | turnover |
|---|---|---|---|---|---|
| rec_mom | batch3a | 3.32 | **2.64** | 0.48 | 0.368 |
| industry_mom | batch9 | 2.06 | 2.03 | 1.39 | 0.244 |
| fscore_lite | batch2 | 6.63 | 2.01 | 1.46 | 0.129 |
| cash_prof | batch2 | 7.90 | 1.73 | 1.26 | 0.095 |
| re_me | batch7 | 5.30 | 1.56 | 1.37 | 0.074 |

Re-scanned on explore 2004-2018, small, under three cost arms (KO half-spread
primary, KO full-spread stress, zero-cost bound). **The flat-25 regression guard
reproduced every banked number exactly** (rec_mom 0.48, industry_mom 1.39,
fscore_lite 1.46, cash_prof 1.26, re_me 1.37) — the rebuilds are byte-identical.

| signal | KO-half t_net | KO-full t_net | zero-cost bound |
|---|---|---|---|
| rec_mom | 1.42 | **0.20** | 2.64 |
| industry_mom | 1.63 | 1.22 | 2.03 |
| fscore_lite | **1.72** | 1.44 | 2.01 |
| cash_prof | 1.45 | 1.17 | 1.73 |
| re_me | 1.39 | 1.23 | 1.56 |

Two signals (fscore_lite 1.72, industry_mom 1.63) clear the 1.5 net bar under
the primary arm — and **both fail the stress arm**, which the registration
required them to clear as well. The confirm window was never opened.

### What the corpse teaches — a sharper result than "empty"

The **zero-cost bound is the decisive column**, and it is the same terminating
logic that closed largemid. It answers "could this graduate if trading were
*free*?", and by construction it equals t_gross:

- In **large/mid**, the best rank-real reject reached **1.48 gross** — below the
  1.5 bar, so *nothing there could graduate even at zero cost*. That is why the
  cohort was empty.
- In **small**, exactly one candidate — `rec_mom` — clears both legs for free
  (net 2.64, IC 3.32). It is **the only signal in 160 candidates that is
  genuinely killed by trading costs and nothing else.** Its executioner is
  turnover: 36.8%/month one-way, which is why it falls from 2.64 (free) to 1.42
  (KO half) to 0.20 (KO full).

So the honest statement is not "the shelf is empty everywhere." It is: **the
retail-accessible shelf contains exactly one genuinely cost-killed signal, and
it is cost-killed because it trades 37% of the book every month — a property no
cost model correction can repair.** The paper's lead exhibit survives the
extension and gets a named exception instead of a blanket claim.

**Bookkeeping consequence, stated plainly:** the factory's small-segment cost
premise was wrong for the entire search, and correcting it moved **zero
verdicts**. The design defect was real and immaterial — both halves of that
sentence belong on the record. Small-cap cost shelf **CLOSED**; per the frozen
kill clause, **no further cost-model appeals exist for either segment.**

## 23. Residual momentum buys the risk reduction and loses the signal (INSTR-RESID-MOM)

**Date:** 2026-07-30. **Chain:** `Aegis module` c95a97b (registration frozen
BEFORE any signal code) → implementation → **spec test caught an off-by-one,
first execution VOIDED** (below) → corrected → one run. Cumulative candidates
161-162.

Residual (idiosyncratic) momentum is one of the short list of anomalies with an
explicit post-publication out-of-sample survival claim (Blitz-Huij-Martens
JEmpFin 2011; Blitz-Hanauer-Vidojevic IRFA 2020: comparable returns at ~half the
volatility, no long-term reversal). It was admitted against the CLOSED momentum
family as a **new mechanism class**: trials #13/#14 both ranked *total* return
and varied only the holding rule — the timing mechanism that failed twice —
whereas residualisation changes *what is ranked*, and targets the exact recorded
cause of death (§9's −54.7% momentum crash, which §10's trend filter made worse).

Spec frozen verbatim from BHM: FF3 OLS over months m-35..m (all 36 required),
signal = mean residual over m-11..m-1 divided by its sd over the same window,
direction +1. Bars declared at registration: largemid @ flat 25, small @ KO
half-spread, both `t_net >= 1.5 AND t_ic >= 2.0`.

### ⚠️ The first execution was VOID — disclosed with its numbers

The implementation put the signal window at estimation-window positions 24..**35**.
Position 35 is the **formation month itself**, so the first run folded one-month
reversal into a momentum signal and violated the frozen 12-1 skip. It was caught
not by inspection but by a spec test written after the run
(`tests/test_resid_mom.py::test_frozen_spec_constants`), and the defective run's
numbers are recorded here rather than discarded quietly: small IC t **−0.58**,
largemid IC t −0.06, small net −12.7 bps. Those are **not** the trial. A run that
does not implement the registered spec is not an execution of it; the fix and
re-run are repair, not a second bite — but the reader is entitled to both sets of
numbers and to notice that the void run made the signal look *worse*, not better.

### Result: **REJECT, no graduate in either segment. Family CLOSED.**

Explore 2004-2018, 180 months, paired against `mom_12_1` re-run on identical
windows and cost arms:

| | segment | net bps/mo | t_net | t_gross | **t_ic** | turnover | **maxDD** |
|---|---|---|---|---|---|---|---|
| resid_mom | largemid @ flat25 | −20.6 | −1.29 | −0.67 | **0.33** | 0.201 | −0.585 |
| mom_12_1 | largemid @ flat25 | −28.6 | −1.17 | −0.82 | 0.63 | 0.170 | −0.641 |
| resid_mom | small @ KO-half | −16.9 | −1.34 | −0.83 | **0.81** | 0.207 | **−0.543** |
| mom_12_1 | small @ KO-half | −37.5 | −1.83 | −1.50 | **3.05** | 0.181 | −0.657 |

**The construction did exactly what it claims, and that is why it failed.**
FF3 loadings of the top-decile book confirm the mechanism worked mechanically
(see the trial doc for the full table): residualisation pulls market beta back
toward 1 and strips the size/value tilts that the total-momentum book carries.
It also delivers the advertised risk reduction — **maxDD −65.7% → −54.3% in
small, 11.4 points shallower**, and it halves the net bleed (−37.5 → −16.9
bps/mo).

And it **destroys the rank information**: small-cap IC t falls **3.05 → 0.81**.

That is the finding, and it is more interesting than the rejection. In our
window, **the cross-sectional information in small-cap total-return momentum was
its factor tilt, not idiosyncratic continuation.** Residualising removes the tilt
and the information leaves with it. What remains is a better-behaved book with
nothing in it — lower drawdown, lower beta, no alpha, no rank. The one
anomaly-with-an-OOS-survival-claim we could test on this panel does not survive
here, and it fails in a way that explains the failure of its parent.

Per the frozen kill clause: **residual-momentum family CLOSED; the momentum
family is now closed at BOTH total-return and residual resolution.** No third
variant — a successor requires a mechanism class distinct from both timing and
residualisation, registered fresh against the deflation count.

---
---
*These are not reasons to distrust the project. They are the reason to trust it.*
