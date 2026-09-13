# Chunk 13 — the allocator: kill losers, promote winners, without inventing a bandit that can't see

STATUS: builder spec, 2026-09-13, written for an Opus agent starting within the
hour and for Murat. Licence: **PRODUCT_EXPERIMENT** (a frozen contract before
the first decision; no significance gate to START it — but §2 and §5 below are
the honesty machinery that stop it from lying to itself). Repos: research/spec
lives here (`aegis-finance`); the mandates it edits live in
`aegis-alpha-terminal` (`alpha/fleet.py`, `scripts/fleet.py --deploy`).

## FOR MURAT — top block

You asked for four things: reset the six accounts, put a winning engine in
each, kill losers / crown winners, and do it with reinforcement learning. Here
is what each honestly becomes, and why the honest version is still what you
asked for, just not reckless about it:

1. **Reset — yes, but all six together, and only after the new mandates are
   staged**, because Alpaca's dashboard reset is actually **delete-and-recreate**
   (new account number, new API keys) — six accounts reset on six different
   days would silently splice two venues' histories under one role name. Do it
   once, Sunday night before Monday's open, after §3's mandate changes are
   committed and ready to deploy on the fresh accounts (§4).
2. **Winning engine per account — yes**, but "winning" today means *best
   evidence*, not *best backtest Sharpe*: nothing in this repo has beaten its
   own twin at t ≥ 2 on a construction registered before the data was seen
   (roadmap §11c). The best four candidates (disposition-overhang conditioner,
   the one surviving G3 lineage, the de-biased 52-week target, and three new
   JKP-panel books) go into hack1/3/4/6; hack5 stays the options book; hack2 is
   already reassigned to lane D by your own 12:05 HKT decision today. Six
   accounts become **six different error types**, not three copies of one
   tracker (§3).
3. **Kill losers, crown winners — yes, exactly what every pod shop does, and
   the mechanism is the same one they use**: mechanical, fast drawdown cuts
   (kill on RISK, cheap to detect) and slow, capped promotion (grow on
   RETURN, expensive to detect) — never the reverse, and never all-in on one
   book. Millennium's own reported numbers: −5% halves a pod's capital, −7.5%
   winds it down; **there is no symmetric ratchet-up** — winners keep their
   allocation and are reviewed for MORE over time, they are never handed the
   loser's freed capital in one jump (§1). "Give it dominance" becomes
   *"the book with the best posterior gets the largest share of a capped
   pool, and the cap itself widens slowly as its track record lengthens"* —
   not *"funnel everything into hack4 this week."* At ~10-20 marks a day, a
   week of good P&L cannot statistically be told apart from luck (§2) — a
   rule that hands over the whole book because of one green week would be
   promoting noise, which is the exact failure this file exists to prevent.
4. **Reinforcement learning — yes, correctly scoped**: a Thompson-sampling
   allocator over the six books, with drawdown kill-rules that need almost no
   data sitting underneath it as a floor, and its own equal-weight and
   random-allocation twins so the allocator's own claim to add value is
   checked the same way every other book here is checked (§2, §5). A
   return-based bandit alone, with 10-20 daily marks per book, cannot tell a
   winner from noise — the arithmetic is in §2 and it is not close.

**Worst case, fleet-wide, unchanged by this spec:** the six books already carry
a printed worst case (`docs/HANDOFF.md` §1, `aegis-alpha-terminal`) of about
**−$64,000 of ~$573,000** (stop-based) with a gap case near double that; this
spec's mandate swaps (§3) are designed to leave the SAME sizing/stop numbers in
place per account (only the ranking/selection brain changes), so the printed
worst case does not silently move. Anything that changes k, notional%, or stop
must reprint the worst case with `loss_budget_worst_case()`
(`backend/strategy/contract.py:501`, this repo) or `alpha/contract.worst_case`
/ `alpha/tracker.worst_case` (terminal repo) **before** it deploys.

**RESULTS SCOREBOARD (CLAUDE.md discipline, before any code):** best historical
net strategy vs. twin: Book C, +0.24%/mo, t 1.38, 359 blocks, CONDITIONAL — not
Holm-significant, not a claim. Best forward paper strategy: none — fleet is
−8.1% ($551,653 of $600,000, read 2026-09-13 12:10 HKT). Independent selector
count in the fleet today: effectively **one** (sealed upside × consensus, three
copies). Farm/night candidates tested this week: 4 (A/B/C/D), 0 promoted, 3
new sketches (E/F/G) not yet registered. New actionable finding: none clears a
promotion bar. LLM spend / cost per gradeable output: not tracked in this
research pass (not found — the allocator's own receipt should carry it, §5).
**RESULT IMPROVEMENT: NONE.** This spec is process, not alpha.

---

## 1. The industry form of "kill losers, give winners dominance"

**Sources.** Two independent write-ups converge on the same numbers for
Millennium Management, both citing Marc Rubinstein's *Net Interest* newsletter
report "Peak Pod" (September 2023) as the origin of the figures, with the
caveat (stated in both) that these are *widely reported, not officially
published by the platform*:

- ["What Risk Managers at Pod Shops Actually Do All Day"](https://youngandcalculated.substack.com/p/what-risk-managers-at-pod-shops-actually) and ["How Multi-Manager Hedge Funds Actually Work Internally"](https://youngandcalculated.substack.com/p/how-multi-manager-hedge-funds-actually) (Young & Calculated / Substack)
- ["Pod Shop Risk Limits: Drawdown Stop-Outs Explained"](https://hedgefundinterview.com/pod-shop-risk-limits) (hedgefundinterview.com, explicitly attributing the numbers to Rubinstein's "Peak Pod")
- ["How Millennium, Citadel & Point72 Structure Pods"](https://navnoorbawa.substack.com/p/how-millennium-citadel-and-point72) (Navnoor Bawa / Substack) — Citadel/Point72 negotiate thresholds per-PM rather than a uniform rule; Citadel is reported more discretionary (did not cut PMs in the March 2025 sell-off).

**The rule, as reported:**

| drawdown from peak (Millennium) | action |
|---|---|
| ~2.5-3% | informal "on watch"; capital reductions begin ahead of the formal line |
| **−5%** | risk allocation **roughly halved** |
| **−7.5%** | **complete wind-down** of the pod's portfolio |

**The asymmetry that matters most for this spec:** cutting a book in half after
a 5% loss means it needs **double the return on the smaller base** to recover
the same dollar loss (a $100m book cut to $50m needs 10% to recover a $5m
loss that would have needed 5% on the original size) — cuts compound against
the loser, which is the point: a losing book is DELIBERATELY made harder to
recover from full-size, not given a fair rematch. And — the fact load-bearing
for "give it dominance" — **hedgefundinterview.com states explicitly that
there is no symmetric high-water-mark carry for the risk budget**: winners do
not get an automatic capital increase proportional to their gains; capital
increases for outperformers are a **discretionary, periodic review**, not a
mechanical ratchet. **NOT FOUND: a published numeric ratchet-up schedule** for
any of the four firms named in Murat's instruction (Millennium, Citadel,
Point72, Balyasny) — every source that discusses cuts is silent on the mirror
image for promotion, and this spec does not invent one.

**Vol targeting**, the other pod-shop lever named in the task: pods and
platforms size to a **target volatility** of the STRATEGY, not a fixed dollar
notional, so a strategy's realised vol scales its allocation down automatically
as it gets choppier — this is well documented in multi-strat literature
generally (the Substack pieces above describe "risk budget" in vol/VaR terms)
but no specific numeric vol target for a named platform was found in this pass
(**NOT FOUND** — flag rather than invent, per this repo's own rule).

**Why cut on RISK fast and promote on RETURN slow — the statistical reason,
not just the institutional habit:** a drawdown is observed directly, in
dollars, the same day it happens — no significance test is needed to know a
pod is down 7.5%. A **return edge**, by contrast, needs enough independent
observations to separate signal from the strategy's own volatility (§2). So
the asymmetry pod shops apply institutionally is *also* the statistically
correct asymmetry: **risk resolves in one bad day; return resolves over dozens
of good ones** (this repo's own §59, "risk resolves ~30x faster than return" —
the same number the literature's own asymmetry embodies, independently
arrived at).

**Mapped to six paper books (the frozen rule for chunk 13):**

| pod-shop rule | Aegis fleet analogue |
|---|---|
| −5% from peak equity → halve allocation | per-book weight in the allocator's pool is cut to 50% of its current weight when that book's own NAV drawdown from its own peak (since the LAST reset or the last weight change, whichever is later) reaches **−5%** |
| −7.5% from peak → wind down | weight cut to the allocator's floor (a de-minimis "still measured, not funded" weight — proposed **2%** of the pool, never literal zero: a killed book keeps marking so its recovery, if any, is observable, per "explore dirty, promote clean" — no `STOP`, only `DEPRIORITIZED`) at **−7.5%**, and re-examined only after a fixed cooldown (proposed 20 trading sessions) with a fresh contract, never a silent re-arm |
| no symmetric ratchet; promotion is a periodic, capped, discretionary review | promotion is **posterior-driven, not P&L-driven**: a book's allocator weight moves toward its Thompson-sampled posterior share (§2), capped so no single book exceeds a **declared concentration ceiling** (proposed 35% of the pool — chosen because the existing fleet's per-underlying/per-driver caps in `alpha/guards.py` and `alpha/book_limits` already treat >30-40% concentration as the thing that needs a name, not because 35% was fit to any outcome here), and the cap widens only after the book clears an explicit forward evidence bar (§2's promotion rule), reviewed weekly, never same-day |
| vol targeting | out of scope for chunk 13 v0 — the six books already have FIXED gross/stop by mandate (`alpha/fleet.py`); a vol-targeted allocator that also resizes the underlying books is two learned things at once and this repo's own lesson (S38g: an NN sizer lost to trailing vol, which lost to flat 1x) says start simpler. v1 candidate, not now. |

---

## 2. What "reinforcement learning" can honestly mean here

**The arithmetic that rules out a naive return bandit.** Daily book-level
return sd across this fleet is on the order of 1-2% (the caveat text in
`alpha/fleet.py` itself: the theme basket was "measured DOWN 20-50% over the
prior 20 sessions at 60-170% annualised vol" — call the working number **1.5%
daily sd**, the task's own stated figure). A two-sample t-stat on `n` daily
excess-return marks with that sd:

```
t = mean_daily_excess / (1.5% / sqrt(n))
```

| n (trading days) | sd of the mean | mean daily excess needed for t = 2 | annualised, if sustained |
|---|---|---|---|
| 5 (one week) | 0.67% | 1.34%/day | absurd (~630%/yr) |
| **10 (two weeks)** | **0.474%** | **0.95%/day** | **~340%/yr — no real book does this** |
| 20 (one month) | 0.335% | 0.67%/day | ~230%/yr |
| 60 (one quarter) | 0.194% | 0.39%/day | ~130%/yr |
| 252 (one year) | 0.095% | 0.19%/day | ~55%/yr |

At the n=10 the task names, a bandit reading only daily returns needs an
implausible **340% annualised** edge before it can distinguish "this book is
winning" from "this book got a lucky two weeks" at even a loose t=2 bar. This
repo's own book-cadence marks run at 1 (daily), 5 (weekly), 20 (monthly) and 60
(quarterly) sessions per decision (`backend/services/paper_books.py
CADENCE_SESSIONS`) — the fleet's six accounts mark **daily**, so a return-only
allocator watching them is exactly in the n=10-60 trap above for the first two
to three months of any reset. **A return-based bandit cannot honestly promote
or kill on 2-6 weeks of paper P&L alone.** This is not a reason to skip RL —
it is the reason the RL has to lean on cheaper-to-detect signals (drawdown,
§1) while the return signal accumulates, exactly as pod shops do.

**The defensible allocator, named precisely:**

**(a) Drawdown kill rules (§1's table) run FIRST and need almost no data** —
a peak-to-trough calculation on daily NAV is valid from day 2. This is the
floor under everything else: no bandit override can re-fund a book below its
kill weight without the cooldown clearing.

**(b) A Thompson-sampling allocator over the SURVIVING books**, one Beta (or
Normal-Gamma, since returns are continuous) posterior per book, updated daily,
with two departures from the textbook version that are load-bearing here:

   - **The prior is not flat — it starts at the historical replay's own t-stat**,
     not at ignorance. Book C's prior is centred on **+0.24%/mo, t 1.38, 359
     blocks** (its own registered-construction number, §11c); the surviving G3
     lineage's prior is centred on its **per-bank Sharpe 6.27 vs. an
     expected-max bar of 3.15 at 595 trials** (deflated, not raw); the tracker
     mandates (if any remain, §3) get the fleet's own live −8.1% as their
     prior, which is a bearish prior and should shrink their initial posterior
     share accordingly rather than starting them level with a book that has a
     positive historical prior. Starting from ignorance would throw away every
     dollar this repo has already spent discovering these priors.
   - **Promotion needs an explicit `n_effective`, counted the way this repo
     already counts it** — DATE BLOCKS, not raw daily marks (`§58 n_effective
     counts DATE BLOCKS`), because daily marks within a book are
     autocorrelated (a position held for a week produces five correlated daily
     P&L numbers, not five independent ones). The promotion test is a paired
     comparison of each book's daily excess over its own twin (§(d) below),
     block-averaged at the book's OWN cadence (a book that only decides
     weekly should be tested on weekly blocks even though it marks daily),
     with Holm correction across the six books tested simultaneously (`§63
     SCREEN=BH-FDR / EXPORT=Holm` — six books being screened weekly is a
     screen, so BH-FDR at that cadence; the receipt that ever claims "book X
     is promoted" externally uses Holm).

**(c) Regime features from `backend/services/market_sensor.py` as CONTEXT, not
as a separate lever.** The sensor gives exactly two frozen, unfitted inputs —
21-session SPY trend sign and VIX-vs-20 — producing `risk_on` / `risk_off` /
`unknown` (never a guess when an input is missing, per its own `SensorRefused`
contract). A contextual-bandit read: the allocator's posterior is kept
**separately per regime cell** (four cells: trend×vix, plus `unknown` when the
VIX leg is unobserved) so a book measured only in `risk_on` does not silently
lend its posterior to a `risk_off` day. This is cheap to add (the module
already exists and refuses honestly) and directly answers the task's
"regime features from `market_sensor.py` as context" ask — but it also
**quarters an already-thin sample four ways**, which makes §(a)'s point sharper,
not weaker: with four regime cells the effective n per cell shrinks below the
table above, so regime-conditioned promotion needs proportionally longer
before it can fire, and the receipt must print the per-cell n_effective
separately, never a pooled one dressed as if it were regime-aware.

**(d) The allocator's OWN twins — because an allocator is a strategy too, and
this repo's rule is "a book is never shown without its twin"):**

   - **Twin 1 — equal-weight across the surviving (non-killed) books.** If the
     Thompson allocator cannot beat 1/N over the surviving set at the SAME
     n_effective, the learned weighting is not earning its complexity — the
     textbook finding this generalises from is DeMiguel, Garlappi & Uppal
     (*Review of Financial Studies*, 2009, "Optimal Versus Naive
     Diversification"): naive 1/N frequently beats optimised mean-variance
     weights out of sample because estimation error in the optimised weights
     costs more than the optimisation gains — the exact failure mode a
     thin-data bandit is exposed to here.
   - **Twin 2 — a random allocation**, weights drawn from a Dirichlet each
     rebalance (respecting the same kill floor and concentration cap as the
     live allocator, so the comparison isolates the LEARNING, not the
     constraint set). If the Thompson allocator cannot beat a properly
     constrained random draw at the same n_effective, its apparent skill is
     the constraints doing the work, not the learning.
   - Both twins are created WITH the allocator (`paper_books.py`'s own rule:
     "a twin constructed after a number is known is a twin chosen to
     flatter it") and graded on the SAME clock, from day one, in
     `state/allocator/`.

**Bandit/OPS literature, briefly, each mapped to a design choice above:**

- **Thompson sampling for portfolio/strategy blending**: Wang, Li et al.,
  ["Adaptive Portfolio by Solving Multi-Armed Bandit via Thompson Sampling"](https://arxiv.org/abs/1911.05309) (arXiv 1911.05309) — a Beta-per-strategy
  posterior blending multiple heuristic portfolios by sampling, closest
  published shape to §(b).
  ["Multiple Portfolio Blending Strategy with Thompson Sampling"](https://ieeexplore.ieee.org/document/9894518/) (IEEE) — same
  family, risk-adjusted (Sharpe-shaped) reward rather than raw return, which
  is the version to prefer here given §2's own arithmetic (a Sharpe-shaped
  reward is closer to what a thin-sample bandit can actually resolve than a
  raw-return reward is).
- **Successive halving / Hyperband**: Li, Jamieson, DeSalvo, Rostamizadeh &
  Talwalkar, *"Hyperband: A Novel Bandit-Based Approach to Hyperparameter
  Optimization"* (JMLR 2018; built on Jamieson & Talwalkar's 2016 Successive
  Halving) — the general pattern (start N candidates broad, eliminate a
  fraction on cheap evidence, let survivors run longer) is the SAME shape as
  §1's drawdown-first kill rule: cheap, low-fidelity evidence (a drawdown
  threshold) eliminates candidates fast, so only survivors consume the
  expensive resource (weeks of return data needed for §(b)'s promotion test).
  Not literally applicable (SH assumes a fixed, escalating training budget per
  round; a live paper book has none of that structure) but the PRINCIPLE —
  spend the cheap signal first, ration the expensive one — is exactly what
  §1+§2(a) already does.
- **Online portfolio selection, generally**: the field (surveyed under this
  name since Cover's Universal Portfolios, 1991) is the right keyword for any
  future v1 that wants provable regret bounds rather than a heuristic
  Thompson allocator; **not adopted for v0** because most OPS regret bounds
  assume bounded, IID-ish per-period returns and a much larger number of
  periods than six books over weeks will provide — the honest read is that
  the literature's asymptotic guarantees do not bind at this repo's actual
  sample size, so citing them as justification here would be exactly the kind
  of borrowed authority this repo's own rules exist to catch.

**What would make the allocator's OWN claim ("this allocation scheme adds
value") a defensible RESEARCH_CLAIM rather than a PRODUCT_EXPERIMENT: off-policy
evaluation.** The live allocator only observes the P&L of the weights it
actually chose; it never observes what the EQUAL-WEIGHT or RANDOM twin would
have earned on days it chose differently. Because every book's own daily NAV
is fully observed regardless of the allocator's weight on it (all six books
mark every day, weighted or not), the twins can be evaluated **exactly**, not
via importance-weighted OPE — this is the one piece of good news in this
section: the allocator's counterfactual is FREE (both twins can be computed by
just re-weighting the same six daily series after the fact), so no doubly-robust
or IPS estimator is needed for v0. It is needed only if a future version
changes which books EXIST based on the allocator's own choices (e.g., a killed
book stops being marked) — which is exactly why §1's kill rule above **never
sets a book's weight to literal zero**, keeping every counterfactual computable
forever.

---

## 3. The engine switch — six accounts, six different error types

**Buildable now vs. needs a night job first, from reading both repos:**

- **Buildable now**: `alpha/fleet.py`'s `Mandate` is a frozen dataclass read by
  `loop_args()`/`env_for()` — swapping `brains=(...)` and leaving
  `profile`/`structure_kinds`/sizing untouched is a one-line-per-mandate change
  plus a new `alpha/brains/<name>.py` module that returns a ranking the loop's
  existing selector/sizing code already knows how to consume. This is how
  hack3/hack4/hack6 already work (`tracker_portfolio`), so the SHAPE of the
  work is proven; only the ranking function inside the brain changes.
- **Needs a night job / new module first**: any mandate whose ranking needs
  data this repo computes in a night job that the terminal repo cannot run
  itself (Book C's disposition-overhang requires the 60-month warm-up CRSP
  panel computed here, §11c; the G3 lineage's genome needs its frozen
  parameters extracted from `night_factory_*/G3_evaluations.jsonl` into a
  static decision rule the terminal repo can execute without re-running the
  evolutionary search). **The night job's OUTPUT — a small, frozen JSON of
  weights/rules per name per rebalance date — is what ships to the terminal
  repo, never the search itself**, exactly the seal-authority pattern
  `scripts/seal_authority.py` already uses for the tracker books.

| account | keep / retire / replace | new brain | worst case (if sizing unchanged from current mandate) | buildable now? |
|---|---|---|---|---|
| **hack1** (theme basket, currently $93,863) | **replace ranking, keep construction.** Theme basket's live counterfactual is stated positive in its own caveat (+$3,564 on 7, hit 0.43) but is a human-curated theme LIST, not an independent mechanism vs. the tracker family. Swap in **quality-minus-junk (Book E sketch, §3 of `research_next_books_published_rulers.md`)** on the SAME 39-name theme universe (`qmj` tercile within it), OR keep theme_basket as shadow beside it for one cycle to compare directly. | `qmj_quality_tilt_v0` reading `jkp_global_factor_usa.parquet`'s `qmj` column — **needs a night job** to turn the JKP characteristic into a monthly rebalance list matched to hack1's theme universe; not yet registered (`pre-register-trial` owed before this book accrues ANY data, including paper). | Unchanged: 8 × 12.5% = 100% gross, 10% stop → **−10% (~−$9.4-9.9k)**, same formula as today since k/notional/stop are not proposed to change. | Needs the JKP-to-theme-universe join done as a night job first; the fleet-side swap itself (new `brains/qmj_tilt.py` + mandate edit) is buildable same day once that join exists. |
| **hack2** (drift, $98,821) | **Already reassigned** by Murat's 12:05 HKT decision today: moves to lane D's paper role (`ALPACA_LANE_D_API_KEY_ID`/`SECRET_KEY`); `aat-loop-hack2` retired when the keys move. Out of scope for chunk 13's six-book allocator — lane D has its own cadence and contract. | n/a | n/a — lane D's own worst case applies, not this spec's. | Already decided; chunk 13 does not touch it. |
| **hack3** (tracker balanced, $83,342, worst -12%/-23.3% gap) | **replace ranking, keep construction (k=10 × 8.3%, stop 12%).** This is the artery losing the most; swap `tracker_portfolio` for **the disposition-overhang conditioner (Book C)**, the ONLY mechanism in the fleet's candidate pool that is positive in every era measured (+0.24%/mo, t 1.38, CONDITIONAL — not yet PRODUCT_PROMISING; deploy as PRODUCT_EXPERIMENT, not as a claim). | `brains/overhang_conditioner.py` reading the night job's sealed monthly overhang-tercile list — the SAME night-job-to-seal pattern as tracker_portfolio. | Unchanged sizing → **−12% stop-based (~−$10.0k on current equity), ~−23.3% gap case**, IDENTICAL to today's printed number because `universe_for()`'s own comment already proves a broader/different name list does not change the bound — only k, notional% or stop would, and none change here. | Needs Book C's falsifiers to finish first (the momentum-orthogonalisation and sign-flip placebo, §11c) before this is more than a PRODUCT_EXPERIMENT swap — buildable and deployable NOW under that licence, just not claimable as alpha yet. |
| **hack4** (tracker profit-max, $92,941, worst -12%/-18.4% gap, no max_downside by construction) | **replace ranking, keep construction (k=5 × 10%, but see caution below).** Swap `tracker_portfolio` for **the one surviving G3 lineage** (per-bank Sharpe 6.27 vs. expected-max bar 3.15 at 595 trials, deflated — the single most statistically defensible mechanism in the whole candidate pool, because it is the only one that has already cleared a multiplicity-corrected bar rather than a raw t-stat). | `brains/g3_lineage.py` reading a FROZEN genome extracted from `night_factory_*/G3_evaluations.jsonl` — this genome has never traded a real fill; its replay fitness is a beta-matched excess over a random-genome null, not a live P&L series, so its FIRST live pass should not inherit profit-max's "no max_downside" property. **Recommend adding an explicit stop this mandate currently lacks by declared property** rather than porting the gap-case ambiguity onto an untested engine — a new engine's first live exposure is exactly the wrong place to also relax the downside bound. | If sizing is kept identical: **−12% stop-based, ~−$11.2k** on current equity; if (recommended) hack4 gains an explicit max_downside matching hack3/hack6's shape, the worst case IMPROVES to roughly the same −12%/no-gap-case bound rather than staying open-ended — reprint with `loss_budget_worst_case()` before deploy either way. | Needs the genome-to-static-rule extraction as a night job (the search itself never runs live); the fleet-side wrapper is then buildable same day. |
| **hack5** (convexity/options, $95,095, worst -15% premium bound) | **Keep as-is.** It is the fleet's only options book and the only one whose mandate already states its own honest purpose ("this account exists to measure the tail, not to be the safe one"). No candidate in this pool is options-shaped; do not force one in for the sake of six-out-of-six novelty. | unchanged (`theme_basket`, `post_event_drift`) | unchanged: −15% premium bound (~−$14.3k) | n/a — no change proposed |
| **hack6** (tracker diversified, $87,591, worst -10%/-13.0% gap) | **replace ranking, keep construction (k=15 × 6.67%, stop ~10%).** Swap `tracker_portfolio` for **the de-biased consensus 52-week target** (`scripts/price_target_backtest.py`, O11) — the only candidate here that already has a FULL multi-era backtest receipt (below), not merely a single-pass replay. | `brains/debiased_target.py` — the `ours` arm already implemented and backtested (`price_target_backtest_2026-09-12.json`): sector×cap×vol-bucket expanding-window bias correction on raw consensus upside, beats raw consensus's hit-rate and bias in EVERY era measured (2013-16, 2016-20, 2020-24, pre-2013 — see receipt below) and beats the naive drift control on hit-rate in 3 of 4 eras. **The task's framing names this book explicitly with "the 30% cap removed" — do NOT remove it without re-printing worst case**: the receipt below is a POINT-FORECAST accuracy backtest (MAE, bias, hit-rate), not a portfolio backtest with costs, so there is no measured worst case for a levered or uncapped version of this book yet; removing a concentration cap before that measurement exists would be sizing on vibes, which item 4 of the session protocol exists to stop. | Unchanged sizing → **−10% stop-based (~−$8.8k), ~−13.0% gap case**, same reasoning as hack3 (ranking change alone does not move the bound). If the 30% single-name cap is genuinely removed, STOP and recompute worst case with the new n_names/notional before deploying — do not deploy the removal and the ranking swap in the same commit. | **Buildable now** — this is the only swap in the table with a full receipt already on disk; no night job needed beyond what O11 already produced. |

**De-biased target receipt, cited exactly** (`backend/data/optimus/tracker_backtest/price_target_backtest_2026-09-12.json`,
generated 2026-09-12T06:40:26Z, window 2005-01..2023-12, 390,368 cells, 7,439
names, 228 months): pooled hit-rate `ours` 48.35% vs. `consensus` 39.20% vs.
`drift` 44.68%; pooled bias `ours` +3.41pp vs. `consensus` +17.71pp; by era,
`ours` beats `consensus` on hit-rate in all four sub-periods (2013-16: 54.79%
vs 44.49%; 2016-20: 51.64% vs 44.46%; 2020-24: 35.83% vs 27.33%; pre-2013:
48.73% vs. figures truncated in this read — re-pull the full file before
quoting the pre-2013 consensus cell). This is a forecast-accuracy backtest,
**not yet a portfolio backtest with trading costs and turnover** — the gap
between "the target is less biased" and "a book built on ranking by
debiased-upside beats its twin after costs" is exactly the gap Book A/B/C/D's
own registered constructions exist to close, and hack6's swap should be
pre-registered the same way before it accrues forward P&L, per this repo's
own `pre-register-trial` skill.

**Worst case in dollars, fleet-wide, unchanged by design:** every swap above
is proposed as a RANKING change inside an EXISTING mandate's construction
(`profile`, `structure_kinds`, `k`, `notional%`, `stop`), not a sizing change —
so the fleet's printed worst case (~−$64k stop-based / ~−$128k gap-case-ish
before this spec, per `docs/HANDOFF.md` §1) is **designed not to move** as a
side effect of this chunk. The one exception flagged above (hack4's missing
`max_downside`) should be TIGHTENED, not loosened, when a brand-new untested
engine takes over that mandate. **Reprint every book's worst case with
`loss_budget_worst_case()` (this repo) / `alpha/contract.worst_case` (terminal
repo) immediately before `scripts/fleet.py --deploy`, and paste the printed
verdict string into the deploy receipt** — a swap that is deployed without a
freshly printed worst case is a swap the session protocol's rule 4 already
forbids.

---

## 4. Reset

**Alpaca's own current mechanism, confirmed from `docs.alpaca.markets/us/docs/paper-trading`
(fetched 2026-09-13):** the dashboard **no longer resets an account in place**.
It says explicitly: *"We've updated the dashboard to allow you to create and
delete paper accounts, rather than resetting them"* — reset is now
**delete-the-old, create-a-new-one**, done from the paper account selector in
the dashboard's upper-left corner ("Open New Paper Account"), with an arbitrary
configurable starting balance (default $100,000). **New API keys are required**
for the new account — the docs state the old key "is not valid any longer
after you reset it." No reset path exists via the trading API itself
(confirmed by the GitHub issue thread `alpacahq/Alpaca-API#167`, "Resetting
paper account results in no paper account," and the forum threads
`forum.alpaca.markets/t/no-button-to-reset-paper-account/15933` and
`/t/not-able-to-reset-my-alpaca-paper-account/16434` — several users report the
UI button itself intermittently missing, which is an operational risk to flag
to whoever executes this, not just a documentation note).

**What this means for `alpha/genesis.py`'s LEGACY logic:** `genesis.py`'s
`DENIED_ACCOUNTS`/`verify()` machinery is scoped to the **`competition`/judged
role only** (`Guard("genesis_verified", ..., scope="competition role, --live")`
in `alpha/guards.py`) — it is NOT invoked for hack1-6 today, so a reset of the
six fleet accounts does not trip genesis's own refusal logic directly. But the
NEW account created by "delete and recreate" has a **new `account_number`**,
and `scripts/fleet.py check()` classifies an account as `FRESH` purely from
`(no orders, no positions, equity==$100k)` — so a freshly recreated account
reports `FRESH` correctly for fleet purposes. The risk is elsewhere: any local
state keyed by **role name** (not account number) — ledgers, receipts,
deploy history under `state/` — will silently carry the OLD account's history
forward under the same role label unless it is explicitly rolled over, exactly
the shape `alpha/genesis.py`'s own docstring warns about ("a role pointed at
the wrong account passes all of the ROLE-keyed guards"). **Recommend a
`genesis`-style birth-certificate stamp for reset fleet accounts too** — not
`competition`'s exact code path, but the same idea: on the day of reset, run
`python -m scripts.fleet --check-all` and archive the fresh `(role,
account_number, equity=$100000, orders=0)` tuple as the new starting point,
committed, before any loop redeploys — so a future reader can tell "hack3's
history since 2026-09-15" from "hack3's history since 2026-08-28" without
having to ask which underlying venue account produced which row.

**What this means for the ledger hash chain:** `docs/HANDOFF.md`'s own
standing warning — *"the ledger hash chain has been BROKEN since 25 Aug ...
never silently repaired"* — is unaffected in kind by a reset (a new account's
ledger starts a NEW chain from genesis, it does not repair the old one), but a
reset is the right MOMENT to also decide, explicitly and in the open, whether
the six old chains are archived as closed evidence or left dangling — closing
them (writing a final "CLOSED at reset, N orders, final equity $X" row to each)
costs one receipt per book and prevents a future reader from wondering whether
the chain is broken or merely stopped.

**Recommendation: reset all six or none, and time it Sunday night before
Monday's open, after §3's mandate edits are committed (not deployed) —**

1. Land and commit (not yet deploy) the six mandate edits from §3.
2. Freeze §5's allocator contract.
3. Reset all six accounts from the dashboard in one sitting (minimises the
   window where role labels and account numbers could get crossed between
   accounts under time pressure).
4. Regenerate and store the six new key pairs; run `scripts.fleet --check-all`
   and commit the fresh birth-certificate receipt.
5. `scripts.fleet --deploy all --up` with the new mandates AND the new keys in
   the same deploy pass, so no account ever runs the OLD ranking on the NEW
   equity or the NEW ranking on stale state.

Reset-one-at-a-time is explicitly discouraged: the fleet's own cross-book
overlap tooling (`scripts/fleet.py overlap()`) and the allocator's twins (§2d)
both assume all six books share one clock; resetting on different days would
make every book's "since reset" day-count different, which quietly breaks the
n_effective accounting §2 depends on.

---

## 5. The frozen contract and the daily receipt

**Directory:** `state/allocator/` (terminal repo, alongside `state/predictions/`
and the other per-role state families already there — per `docs/HANDOFF.md`
§4's own accounting of tracked vs. untracked `state/` families, this one is
**TRACKED from day one**, not left to accumulate untracked the way
`state/predictions/` was found to be).

**Daily receipt (`state/allocator/<day>.json`), one file per trading day,
written even when nothing changes (invariant 15: silence is never success):**

```
{
  "day": "YYYY-MM-DD",
  "licence": "PRODUCT_EXPERIMENT",
  "contract_hash": "<sha256 of the frozen contract below>",
  "per_book": {
    "<role>": {
      "peak_equity_since_reset": <float>,
      "current_equity": <float>,
      "drawdown_from_peak_pct": <float>,
      "kill_state": "ACTIVE | HALVED | FLOOR | COOLDOWN_UNTIL:<date>",
      "posterior_mean_daily_excess_vs_twin": <float>,
      "posterior_sd": <float>,
      "n_effective_date_blocks": <int>,
      "regime_cell": "risk_on | risk_off | unknown",
      "allocator_weight": <float>,
      "equal_weight_twin_weight": <float>,
      "random_twin_weight": <float>,
      "binding_constraint": "<the cap or gate that actually bound this book's weight, or 'none'>"
    }
  },
  "rule_fired": ["<e.g. 'hack3 crossed -5% drawdown from peak; weight halved 0.20->0.10'>"],
  "worst_case_usd_fleet": <float, from loss_budget_worst_case() per book, summed>,
  "worst_case_pct_equity_fleet": <float>,
  "allocator_vs_equal_weight_twin_cum_excess": <float>,
  "allocator_vs_random_twin_cum_excess": <float>,
  "promotion_log": [{"role": ..., "from_weight": ..., "to_weight": ..., "reason": ..., "n_effective_at_decision": ...}],
  "kill_log": [{"role": ..., "drawdown_pct": ..., "action": ..., "date": ...}]
}
```

Every numeric field either cites its source computation or is `null` with a
`"CANNOT_DETERMINE"` reason string beside it — no field is ever silently
zero (this repo's own `_dig`/`refused` pattern in `learner/allocator.py` is the
existing precedent to reuse literally, not reinvent).

**Pre-registration text (to file via the `pre-register-trial` skill before the
allocator reads a single live weight):**

> **Hypothesis:** a Thompson-sampling allocator over six paper books, with a
> mechanical drawdown-based kill floor (−5% halves weight, −7.5% floors it at
> 2% with a 20-session cooldown) and posteriors seeded from each book's own
> historical replay prior, produces higher risk-adjusted terminal wealth over
> 60 trading days than (a) an equal-weight twin over the same surviving books
> and (b) a constrained-random-Dirichlet twin, at the same n_effective and
> under the same kill floor and concentration cap.
>
> **Primary metric:** cumulative excess NAV of the allocator's realised
> weighted portfolio vs. Twin 1 (equal-weight), in dollars and in percent of
> starting fleet equity, over 60 trading sessions from the reset date.
> **Secondary metric:** the same, vs. Twin 2 (random-Dirichlet).
>
> **Decision rule, stated now, not after 60 days are seen:** the allocator is
> `FAILED_VARIANT` (not merely deprioritized — this is the allocator's OWN
> claim of skill being tested, and CLAUDE.md's amended-scope rule is explicit
> that a null still needs a null before it counts) if, after 60 trading
> sessions, its cumulative excess over Twin 1 is **≤ 0 with a paired t < 2.0**
> on the daily-excess series (block-corrected per §58/§2b's own convention).
> **The one number that ends it:** if the allocator's 60-session cumulative
> excess over the equal-weight twin is **≤ $0** — i.e., a learned weighting
> scheme that cannot even beat naive 1/N over its own surviving set after two
> months, at which point the honest conclusion is that estimation error in the
> posteriors (DeMiguel-Garlappi-Uppal's own finding, §2) is costing more than
> the learning is worth, and the fleet should run equal-weighted with the kill
> floor alone until either more data or a better prior exists.
> **Earliest decision date:** 60 trading sessions after the reset (§4)
> deploys, not before — the arithmetic in §2 says anything earlier is reading
> noise.
> **What does NOT relax:** the kill floor itself is a HARD-classified guard
> (per `alpha/guards.py`'s own `GUARD_CLASS_v1` taxonomy) from day one — it is
> not part of what this trial is testing and does not wait for the 60-day
> verdict to bind.

**A null owes two tests, per this repo's own standing rule:** if the 60-day
verdict comes back FAILED_VARIANT, the SECOND test it owes is against Twin 2
(random-Dirichlet) specifically, because a Thompson allocator that loses to
equal-weight but BEATS random tells a different story (the learning has some
signal, the prior/posterior shape is wrong) than one that loses to both
(the six books' return series simply don't carry enough signal at this n for
any allocation scheme to matter yet, in which case the fix is more time, not a
better allocator).
