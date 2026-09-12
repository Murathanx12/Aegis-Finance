# Spec: the first four `origin=night_job` PaperBooks (chunk 5, lane B)

Scope: roadmap `docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
§3 lane B (B1-B5) and §11c ideas #2, #3, #4, #7. Sources read in full: that
roadmap's lane B/lane E tables and §11c table; `docs/research_notes/2026-09-11/
ideas_round2/angle1_theory.md` §1 (disposition overhang) and §0 (LPPLS, not
used here); `angle3_evidence.md` §d2 (short interest) and §e1/e2 (insider
clusters); `angle4_ideation.md` §1 (abstention) and §5 (disposition
counterparty book); `backend/strategy/contract.py` (every dataclass);
`backend/strategy/run.py` (the `series` engine, the only one registered);
`backend/services/belief_state.py` (`PredictionRecord`, `make_prediction`,
`Observable`, `HORIZONS`); `learner/dataset.py` (feature/target columns);
`docs/BUILD_2026-09-07b_I1_SEC_INSIDER.md` (the 11.5M-row Form-4 bulk table);
`backend/services/short_interest.py`, `backend/services/insider_form4.py`,
`backend/services/cmp_insider.py`; `NEGATIVE_RESULTS.md` §1, §14, §24, §25,
§46 and the TRIAL-H5/RW2 closure; `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`;
`docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md` (the pre-registration
shape). WebSearch used only to pin the Grinblatt-Han reference-price formula
verbatim (Book C, §2) since the research notes describe it in prose only.

---

## 0. Cross-cutting notes that apply to all four books (read before any one book)

**A. `PaperBook` and its producer do not exist yet.** `backend/strategy/
contract.py` (`Strategy`, `Universe`, `Signal`, `Construction`, `HoldRule`,
`Sizing`, `CostModel`, `Benchmark`, `Objective`, `LossBudget`, `Window`) is
frozen and complete — B1 wraps it, does not replace it. `backend/strategy/
run.py` registers exactly **one** engine, `"series"`
(`_engine_series`, line 489): it grades a period-return series someone else
already built (`data={"book": <pd.Series>, "benchmark": <pd.Series>, "rf":
<pd.Series>}`) via `learner.growth.evaluate_growth`. **None of the four books
below has a signal-construction engine yet.** Each book needs a builder-written
function that (a) computes its signal/eligibility columns from the sources
named in each book's §2, (b) forms period weights via
`backend.services.portfolio_farm` machinery (the existing cross-sectional
sort/weight/rebalance code — `panel.py`, `signals.py`, `characteristics.py`),
and (c) hands the resulting series to `Strategy` + `engine="series"`. This is
new code for all four books; nothing here reduces to "just call an existing
book."

**B. `belief_state.py` already exists — B5 wraps it, does not invent it.**
`backend/services/belief_state.py` has `PredictionRecord` (fields:
`prediction_id, ticker, specialist, observable, horizon_days, probability,
threshold, benchmark, made_at, resolves_after, thesis, counter_thesis,
next_observable, model, model_version, prompt_hash, input_snapshot_hash,
prior, posterior, belief_change, arm, session_as_of, evidence_population,
ledger_id, resolved_at, void_reason, outcome, brier, resolution_detail`) and
`make_prediction(*, ticker, specialist, observable: Observable, horizon_days,
probability, thesis, counter_thesis, next_observable, model, model_version,
prompt, input_snapshot, threshold=None, benchmark=None, made_at=None,
prior=None, posterior=None, arm=None, session_as_of=None)`.
`HORIZONS = (1, 2, 5, 20, 60, 120, 252)` (trading days) — **only these seven
values are legal**; a horizon not in the tuple raises `ValueError`.
`Observable` has `RETURN_SIGN`, `BEATS_BENCHMARK`, `ABS_MOVE_EXCEEDS`,
`DRAWDOWN_EXCEEDS`. **What is genuinely new for chunk 5**: nobody currently
calls `make_prediction` for a rules-based (non-LLM) engine book, so there is no
existing convention for what `probability` should be when no LLM produced a
confidence number. This spec's convention (used in every book below unless
stated otherwise): **`probability = Φ(IR_trailing)`**, i.e. the normal CDF of
the book's own trailing realised information ratio vs its control twin,
recomputed each period from real history only (no leakage) — a deterministic,
auditable stand-in for "confidence" on a book with no LLM in it.  `model=
"engine_rule"`, `model_version="<book_id>_v1"`, `prompt=<sha256 of the frozen
construction spec text>`, `input_snapshot=<the period's input hash>`.
**The control twin gets its own `PredictionRecord`** at fixed
`probability=0.5` every period (B5's "Brier vs the twin's forecast (p=0.5)"),
so the twin is itself a graded, resolvable row and not just a subtracted
series.

**C. Cadence enum gap.** B1 declares `cadence ∈ {30m, daily, weekly,
quarterly}`. Three of the four books below (A, C, D) are native to a
**monthly** decision cycle (short-interest files are semi-monthly, IBES
revisions are monthly, R2's digest is monthly); Book B's own published
horizon (BHAR 22-90 trading days) is closer to quarterly. Recommend adding
`"monthly"` to the enum before any of these four books is held by Murat;
until then, use `cadence="quarterly"` for all four and note in each `origin_text`
that the underlying rebalance is monthly, so the mismatch is visible on the
row rather than silently absorbed.

**D. The one shared multiplicity family.** Per §11c, "each with its twin,"
and per the task: **all four books share one family budget.** The family is
named `NIGHT_JOB_BOOKS_2026_09` and has exactly **4 primary-metric tests** —
one per book, as named in each book's §6 below. Every other number each book
computes (era splits, sign-flip placebos, momentum-orthogonalisation,
decile-monotonicity, the same-day-cluster diagnostic) is `SCREEN`-only under
`PRODUCT_EXPERIMENT` licence (no correction needed to explore — CLAUDE.md
"Explore Dirty, Promote Clean") and is **reported, never deciding**, exactly
as `read_minus_shuffled_control` is the only deciding number in TRIAL-R2 §3.
**Promotion to `CAPITAL_CANDIDATE` or `RESEARCH_CLAIM` for any one book
requires re-running the family's 4 primary metrics under Holm** (canon §63:
SCREEN = BH-FDR, EXPORT = Holm) — a book cannot be promoted by looking only at
its own number and ignoring that three siblings were tested alongside it.

**E. Verdict vocabulary used below**, exactly as specified in the task, and
distinct from CLAUDE.md's `STOP` retirement ladder (which still applies to
implementations, not mechanisms):
- `PRODUCT_PROMISING` — clears its adopt clause; seeds/continues the forward
  paper leg, unadopted as capital.
- `CONDITIONAL` — between reject and adopt; reported, paper-tracked,
  unadopted, revisited at the next scheduled read.
- `DEPRIORITIZED` — fails on this construction but the mechanism is not
  refuted; may resurface with a different construction.
- `FAILED_VARIANT` — this specific implementation is closed; the mechanism
  family may still be open per CLAUDE.md's ladder.

**F. The worst-case-dollars print (protocol §4) is required before any book
is held**, for the largest admissible construction of each book
(`backend.strategy.contract.loss_budget_worst_case`). Numbers are given per
book in §3 below (gross, stop, worst case); recompute at hold time against
the actual `n_names` realised that period, not the design maximum, if they
differ.

**G. Honesty about numbers not yet computable.** Several §6 sections below
name an exact **formula** for the MDE (canon §64: power before confirmation)
but not a numeric threshold, because the underlying joined panel (short
interest × CRSP, or the overhang panel) does not exist on disk yet — inventing
a number here would be exactly the "headline number without a receipt" defect
CLAUDE.md prohibits. Each such case says explicitly: **compute this from the
built panel's own dispersion before the first read: no number here is a
substitute for that arithmetic.**

---

## BOOK A — low short interest × high turnover, long-only (§11c idea #3)

### A.1 The mechanism

Boehmer, Huszár & Jordan, "The Good News in Short Interest," *Journal of
Financial Economics* 96(1): 80-97 (2010) — verified JFE/RePEc/SMU. The
informative side of short interest is the side nobody trades: relatively
heavily traded (liquid) stocks with **low** short interest earn large,
significant positive abnormal returns — often larger in absolute value than
the negative returns on heavily-shorted stocks. Published magnitudes
(practitioner decomposition of the JFE tables, Alpha Architect 2011 — **verify
against the JFE tables directly before pre-registering a number**): low-SI leg
≈ **+1%/month** alpha (long-only raw ≈ 2%/month, ≈1.3%/month alpha);
long-short ≈ **1.5-1.6%/month**; sample 1988-2005, NYSE/AMEX/Nasdaq. Robust to
portfolio weighting, formation timing, risk adjustment, listing venue,
new-listing exclusion, dropping 1998-2000. The alpha survives holding up to
**six months** — this is a low-turnover signal, the property that matters most
for a small book paying retail spreads.

**Decay: UNVERIFIED past 2005.** No replication retrieved past the sample end.
McLean & Pontiff (2016) find published anomalies decay ~58% post-publication
on average; assume material decay as the prior, not the null. This is the
single biggest open question on the strongest idea in the research notes, and
Aegis has never tested it — CANON, keep the corpse precise: NEGATIVE_RESULTS
§24 tested a **short-interest CHANGE** signal (`si_chg_low`, 3-month Δ, IC t
6.09 raw, DSR 0.457, one-way turnover 0.457/month — net-dead from turnover) and
a **level** pair (`dtc_low`/`dtc_high`, days-to-cover level). **Neither is
this signal.** BHJ's variable is a **short-interest LEVEL × turnover LEVEL**
double sort, held up to 6 months — the flow-vs-level distinction of §24 is
exactly why the level was never actually tested here, and this book is that
test, not a repeat of one already run.

### A.2 The data

**Exists today, in `learner/dataset.py`'s underlying build blocks (not yet a
feature column):** `load_prices_ext` (line 476) pulls CRSP `prc`, `shrout`
(thousands of shares); `daily_panel` (line 501) computes `dollar_vol = vol *
prc` (line 528) — so raw daily share **`vol`** is on disk even though it is
not exposed as a `learner` feature. `log_dollar_vol_20d` (in
`FEATURES_CONTINUOUS`) is a 20-day **dollar**-volume feature and is NOT
turnover; do not substitute it.

**Must be computed, new:**
- **Turnover**: `turnover_t = vol_t / shrout_t` (both already loaded upstream
  of `learner/dataset.py`, in `crsp.dsf`-sourced parquet); use a **20-trading-day
  trailing mean** to match `log_dollar_vol_20d`'s own window convention, known
  entirely as of `t` (no leakage — it is trailing).
- **Short interest**: **does not exist anywhere in this repo as a historical
  panel.** `backend/services/short_interest.py::get_short_interest` is a
  **live, single-ticker, current-snapshot** call through `yfinance` (itself
  proxying FINRA's bi-monthly figure) — it has no history and cannot backtest.
  Must be newly ingested: **FINRA + NYSE/Nasdaq semi-monthly short-interest
  files are free and public** (settlement dates mid-month and month-end,
  published with an ~8-business-day reporting lag). PIT rule: use the file's
  **public release date**, never the settlement date, as `observed_at`. Join
  to CRSP by ticker/CUSIP with the same `dsenames`-interval-join discipline
  `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` used for exchange/share-code
  eligibility (as-of-date, not permno-level).
- **`si_pct_t = shares_short_t / shrout_t`**, known as of the file's release
  date, forward-filled to the next release (no interpolation across gaps).

### A.3 The `Strategy` contract

```python
Strategy(
    strategy_id="si_low_turnover_high_v1",
    title="Low short interest, high turnover, long-only (Boehmer-Huszar-Jordan 2010)",
    universe=Universe(
        name="si_low_turnover_high_universe",
        source="CRSP common stock + FINRA/NYSE/Nasdaq semi-monthly short interest + computed turnover",
        floor_dollar_vol_usd=3_000_000.0,     # repo TRADABLE_DOLLAR_VOL
        min_price_usd=5.0,
        max_names=None,                        # whole eligible cross-section, ranked
        note="report pre- and post-floor name counts every period; re-measure "
             "the SAME double sort at a $10M floor too (TRIAL-H5 lesson: a "
             "corner-dependent control must be re-measured at every corner)",
    ),
    signal=Signal(
        name="si_turnover_composite",
        column="si_turnover_z",   # z(turnover_20d) - z(si_pct), within-month cross-section
        direction=1,               # buy the HIGH end: high turnover, low SI
        source="computed: CRSP vol/shrout + FINRA/exchange short interest files",
        warmup_periods=20,
        note="double sort collapsed to one composite z so Construction.top_k applies; "
             "report the raw double-sort quintile x quintile table beside the composite",
    ),
    construction=Construction(
        rule="top_k", k=50, weighting="ew", max_single_name=0.05, gross_cap=1.0,
        note="k=50 approximates BHJ's top double-sort cell; report sensitivity at k=30,100",
    ),
    hold=HoldRule(
        horizon_periods=6,          # MONTHS (Window/Objective periods_per_year=12 convention)
        min_hold_periods=1,
        scheduled_review_periods=1, # monthly re-rank; rotate out of the eligible band
        stop_loss=-0.20,            # placeholder — confirm against house standard before hold
        roi_ladder={},
        note="BHJ's own robustness runs to a 6-month hold with no documented decay inside it",
    ),
    sizing=Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0),
    costs=CostModel(transaction_cost_bps=5.0, slippage_bps=1.0),  # low turnover; repo defaults
    benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=True),
    objective=Objective(name="alpha_intercept", periods_per_year=12, utility="risk_adjusted"),
    loss_budget=LossBudget(positions_judged=50, expected_losers=24,
                           note="modest documented tilt, not a high-conviction picker; "
                                "~55% historical name-level hit rate assumed"),
    licence=Licence.PRODUCT_EXPERIMENT,
    engine="series",
    note="respects NEGATIVE_RESULTS §24: si_chg_low is a CHANGE signal with dead net "
         "turnover; dtc_low/high is a LEVEL of days-to-cover, the SHORT leg. This book "
         "is the SI-LEVEL x TURNOVER-LEVEL long-only cell, never tested here before.",
)
```

### A.4 The twins

1. **Random-universe twin**: same `floor_dollar_vol_usd`, same `k=50`, names
   drawn uniformly at random each period from the SAME eligible band
   (RW1-style random-genome null), rebalanced on the identical schedule.
2. **Beta-matched twin**: 50 names drawn at random from the same band subject
   to matching the realised book's trailing-60-day beta to SPY within ±0.1 —
   required because `Benchmark.beta_matched=True`.
Both twins are created at book creation (B3), before any return is observed.

### A.5 The forecast row

Monthly, at each scheduled review: `make_prediction(ticker="BOOK:
si_low_turnover_high_v1", specialist="si_low_turnover_high_v1",
observable=Observable.BEATS_BENCHMARK, horizon_days=120, probability=
Phi(IR_trailing), thesis="low-SI/high-turnover tilt should beat its random and "
"beta-matched twins over 6 months (BHJ 2010)", counter_thesis="post-2005 "
"publication decay, or the twin's random draw already captures the "
"liquidity/size tilt", model="engine_rule", model_version="si_low_turnover_v1",
prompt=<sha256 of this construction spec>, input_snapshot=<hash of the
period's SI+turnover panel>, benchmark="control_twin:si_low_turnover_high_random")`.
A second record at `benchmark="control_twin:si_low_turnover_high_beta_matched"`.
Each twin carries its own fixed-`probability=0.5` record.

### A.6 The first read

**This book's decision is two-stage, because the decay question dominates
everything else.** Stage 1 is a **historical replication**, not a paper
accrual — the literature's own data (CRSP + FINRA/exchange short interest
through 2024) already covers 1988-2024 and answers the open question cheaply.

- **Primary metric (deciding, family test #1):** net (after realised-turnover
  costs) monthly excess return of the top double-sort cell over its
  random-universe twin, block-mean over **monthly date blocks 2011-2024**
  (post-publication era — the primary slice, per angle3's own three-way split),
  Newey-West lag-2 t.
- **Reported, never deciding:** the 1988-2005 (in-sample) and 2006-2010
  (pre-publication OOS) cells, the raw double-sort table, the $10M-floor
  re-measurement, turnover realised.
- **MDE (§64, power before confirmation):** `n_effective` = number of
  independent monthly date blocks in 2011-2024 (168 months, ~168 unless
  autocorrelation reduces it — measure, do not assume 1.0 rho). MDE at 80%
  power, α 0.05 = `2.8 × cross_sectional_monthly_excess_sd / sqrt(n_effective)`
  (same recipe as TRIAL-R2 §4). **The cross-sectional sd must be measured from
  the built panel before the read — do not proceed to a decision without this
  arithmetic.** Declare the effect size one notch above the computed MDE, per
  TRIAL-R2's convention, not at the published +1.3%/month figure (that number
  is the design's *prior*, not its threshold).
- **Earliest decision date:** as soon as the FINRA/exchange historical files
  and the CRSP join are built — this needs no forward waiting, unlike the
  other three books.
- **Decision rule:** `PRODUCT_PROMISING` → seed the forward `PaperBook`
  (2011-2024 cell clears MDE and NW t ≥ 2.0, sign positive, 2011-2024 clears
  the SAME test at the $10M floor). `FAILED_VARIANT` → 2011-2024 net ≤ 0 or
  the $10M-floor cell fails while the $3M-floor cell passes (tradability
  killed it, per TRIAL-H5's own lesson). `CONDITIONAL` → passes one floor, not
  the other, or NW t in [1.0, 2.0). Once seeded, the **forward paper leg**
  reruns the same primary metric quarterly against the same twins, minimum 12
  months before any capital conversation, per the standing 24-month skill
  floor for `RESEARCH_CLAIM` (this book stays `PRODUCT_EXPERIMENT` throughout).

---

## BOOK B — insider cluster buys, split by cluster length (§11c idea #4)

### B.1 The mechanism

Kang, Kim & Wang, "Cluster Trading of Corporate Insiders" (working paper, Nov
2018 — **verified as to content, UNPUBLISHED, flag: no peer review**), on
1986-2016 Form-4 data: >40% of insider trades cluster. Purchases: 5-day
horizon cluster +2.06% vs non-cluster +1.09%; 21-day +3.80% vs +1.95%; 90-day
+6.41% vs +3.95%. **The frontier, falsifiable result**: clusters spread over
**4-5 consecutive days** are followed by **>5% higher BHAR(22,90)** than
non-cluster purchases (return that accrues *after* public disclosure);
**same-day clusters yield 0.72% LOWER** BHAR(22,90) — same-day gets priced
immediately, slow multi-day clusters do not. Cluster **sales are
uninformative** — no short leg. Executive-only clusters +1.11% over
non-cluster executive purchases (role weighting). Corroboration, **peer
reviewed, use this citation for any future `RESEARCH_CLAIM`**: Alldredge &
Blank, *Journal of Financial Research* 42(2): 331-360 (2019), 1986-2014 —
clustered insider purchases followed by >2%/month abnormal return, strongest
under low attention/high uncertainty/high information asymmetry.

**Decay: UNVERIFIED past 2016 (KKW) / 2014 (Alldredge-Blank).** No post-2016
replication retrieved. This book's own 2017-2024 read is the first genuinely
new cell in the literature, and 2025-26 (Alpaca-bars BHAR, since CRSP ends
2024-12-31) is newer still.

### B.2 The data

**Exists today, no new acquisition:** `backend/data/optimus/sec_insider/
insider_events_v1.parquet` (3,127,624 classified event rows; the raw bulk
table behind it is **11,522,229** transaction rows, 2006q1-2026q2, 82/82
quarters, built by `scripts/sec_insider_bulk_load.py`, documented in
`docs/BUILD_2026-09-07b_I1_SEC_INSIDER.md`). Relevant classes: `
insider_open_market_buy` (940,379 rows, code `P`, non-derivative, acquired,
plan status unresolved), of which `insider_opportunistic_buy` (185,555) and
`insider_routine_buy` (78,444) are CMP-classified (Cohen-Malloy-Pomorski, via
`backend.services.cmp_insider.classify_buy`) — usable from 2009 onward only
(the CMP rule needs 3 strictly-prior years). **PIT column:
`observed_at_utc` = FILING_DATE end-of-day (America/New_York 22:00, converted
UTC) — never `TRANS_DATE`.** permno link via `backend/data/optimus/wrds/bulk/
crsp__stocknames.parquet` (interval join on `namedt<=filing_date<=nameenddt`),
82-88% linked 2006-2024, **0% for 2025-26 by construction**
(`REFUSED_OUTSIDE_CRSP_VINTAGE`, CRSP vintage ends 2024-12-31 — a counted
refusal, not a defect).

**Must be computed, new:**
- **Cluster length**: group `insider_open_market_buy` rows by (issuer permno,
  a rolling window of **transaction dates**, not filing dates — clustering is
  a fact about *when insiders actually bought*, which the raw
  `NONDERIV_TRANS` table's `TRANS_DATE` column carries even though the PIT
  stamp for RETURN purposes is the filing date). A cluster = **≥2 distinct
  insiders (by CIK)**, same issuer, same direction (buy), transaction dates
  within `N` consecutive trading days. Bucket `N=0` (same day) separately from
  `N∈{4,5}` (the frontier result); `N∈{1,2,3}` reported but not traded (KKW
  does not give them a clean sign).
- **The PIT entry date for a cluster is the LATEST filing_date among the
  cluster's constituent Form-4s** — before that filing, the market cannot see
  the full cluster, only a subset.
- **Role weighting (verify before building):** SEC's raw `REPORTINGOWNER.tsv`
  bulk file (already parsed into the 443MB parquet behind
  `insider_events_v1.parquet`, per the build doc) carries `isOfficer`,
  `isDirector`, `isTenPercentOwner`. **Confirm these columns survived into
  `insider_events_v1.parquet`** before building the executive-only cut — if
  not, it is one additional join against the already-parsed raw table, not a
  new data pull.
- **BHAR(22,90)**: buy-and-hold abnormal return over trading days [22,90]
  post-filing, market-adjusted against CRSP value-weighted (through 2024) /
  SPY (2025-26, same declared deviation TRIAL-R2 made when CRSP ran out).

### B.3 The `Strategy` contract

```python
Strategy(
    strategy_id="insider_cluster_length_v1",
    title="Insider cluster buys, 4-5 day clusters, long-only (Kang-Kim-Wang / Alldredge-Blank)",
    universe=Universe(
        name="insider_cluster_universe",
        source="SEC Form-4 bulk (insider_events_v1.parquet) + CRSP link",
        floor_dollar_vol_usd=3_000_000.0,
        min_price_usd=5.0,
        max_names=None,
        note="insider buys concentrate in small/micro caps — report pre- and "
             "post-floor name counts every period; expect heavy attrition",
    ),
    signal=Signal(
        name="insider_cluster_length_4_5",
        column="cluster_length_days",   # computed, see B.2
        direction=1,
        source="computed: insider_events_v1.parquet transaction-date clustering",
        warmup_periods=0,
        note="eligibility gate, not a continuous rank: a name enters only in the "
             "month its 4-5-day cluster's LATEST filing_date lands",
    ),
    construction=Construction(
        rule="passthrough",   # own every name that qualifies this period, not a fixed-k rank
        weighting="ew", max_single_name=0.10, gross_cap=1.0,
        note="event count varies month to month; passthrough (not top_k) is correct here",
    ),
    hold=HoldRule(
        horizon_periods=4,            # ~90 trading days from filing, in months
        min_hold_periods=1,
        scheduled_review_periods=1,
        stop_loss=-0.25,              # micro-cap volatility; placeholder, confirm before hold
        roi_ladder={},
        note="BHAR(22,90) is measured from day 22, not day 0, but the book enters at "
             "filing (T+1 open) since waiting 22 days to enter forfeits the disclosure-day pop",
    ),
    sizing=Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0),
    costs=CostModel(transaction_cost_bps=20.0, slippage_bps=5.0,
                    note="micro-cap spreads: NEGATIVE_RESULTS §25 measured 41.7-49.2bps "
                         "one-way (Corwin-Schultz) vs 11.6-13.1bps (Kyle-linear) in exactly "
                         "this segment, a 3.4-4.2x disagreement; use the harsher estimate as "
                         "primary and report the 5bps repo default as an optimistic bound"),
    benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=True),
    objective=Objective(name="alpha_intercept", periods_per_year=12, utility="risk_adjusted"),
    loss_budget=LossBudget(positions_judged=40, expected_losers=18,
                           note="rarer events than Book A; smaller expected sample"),
    licence=Licence.PRODUCT_EXPERIMENT,
    engine="series",
    note="respects NEGATIVE_RESULTS §46/N1: the insider return does NOT accrue "
         "before disclosure on 5 filing days, so filing-date PIT entry is not "
         "pre-empted. The 13D/13G family stays NO CONCLUSION and is untouched. "
         "Cluster SALES are not shorted (KKW: uninformative).",
)
```

A **diagnostic-only** twin strategy (not a real book, not held, not sized)
replays the identical construction on **same-day clusters** — theory predicts
this arm loses to non-cluster purchases; if it instead wins, the
length-conditioning claim is falsified before the family read.

### B.4 The twins

1. **Random-universe twin**: EW basket of the same size, drawn each period
   from names with **any** Form-4 open-market-purchase activity that period
   (controls for "insider-active firms differ systematically"), same hold.
2. **Beta-matched twin**, per B3, matched on trailing-60-day beta.
3. The same-day-cluster diagnostic arm above (falsifier, not a null).

### B.5 The forecast row

`make_prediction(ticker="BOOK:insider_cluster_length_v1",
specialist="insider_cluster_length_v1", observable=Observable.
BEATS_BENCHMARK, horizon_days=60, probability=Phi(IR_trailing), thesis=
"4-5 day insider clusters predict post-disclosure drift (KKW; Alldredge-Blank)",
counter_thesis="the effect is a 1986-2016/2014 artefact with no post-publication
replication, or lives entirely below the tradability floor",
model="engine_rule", model_version="insider_cluster_v1",
benchmark="control_twin:insider_cluster_random_universe")`. Note:
`horizon_days=60` resolves at `60*1.45+3 = 90` trading-day-equivalent
calendar days — a near-exact match to the published BHAR(22,90) window.

### B.6 The first read

- **Primary metric (deciding, family test #2):** mean net BHAR(22,90) of the
  4-5-day-cluster book vs its random-universe twin, block-mean over
  **filing-month date blocks, 2017-01 to 2024-12** (the first genuinely
  post-KKW-sample slice), correlation-corrected `n_effective` exactly as
  `docs/NEGATIVE_RESULTS.md` §46/N1 did for its own event correlation (rho
  measured, not assumed; N1 measured rho=0.044 across event names' daily
  returns — re-measure on this panel, do not reuse N1's number unchanged).
- **Reported, never deciding:** the same-day-cluster diagnostic, the
  executive-only role cut, the 2×2 against opportunistic/routine (per §e2),
  the 2025-26 Alpaca-bars extension, plan-10b5-1 breakdown.
- **MDE**: `2.8 × cross_sectional_BHAR_sd / sqrt(n_effective events)` — **compute
  from the built cluster panel's own event count and dispersion; do not
  substitute the published +5% figure as a threshold.**
- **Earliest decision date**: as soon as the cluster-construction and role
  join are built against the existing `insider_events_v1.parquet` — no new
  data pull needed, unlike Book A.
- **Decision rule**: `PRODUCT_PROMISING` → 2017-2024 net BHAR positive, NW/
  block t ≥ 2.0, same-day diagnostic arm does NOT beat non-cluster (falsifier
  survives), post-floor name count ≥ 20/year. `FAILED_VARIANT` → net ≤ 0, or
  the same-day arm outperforms (mechanism falsified), or post-floor attrition
  leaves <10 names/year (tradability killed it — the research note's own
  predicted "most likely death"). `CONDITIONAL` → otherwise.

---

## BOOK C — the disposition-overhang conditioner (§11c idea #2)

### C.1 The mechanism

Andrea Frazzini, "The Disposition Effect and Underreaction to News," *Journal
of Finance* 61(4): 2017-2046 (2006) — reference price built from **mutual
fund holdings**; post-event drift is most severe when capital gains and news
share a sign; overhang spread ≈ **2.43%/month, t = 6.60**; the sign-flipped
placebo (good-news-large-loss minus bad-news-large-gain) ≈ 0. Theory: Mark
Grinblatt & Bing Han, "Prospect Theory, Mental Accounting, and Momentum,"
*Journal of Financial Economics* 78(2): 311-339 (2005) — **when capital-gains
overhang is included as a regressor, the intermediate-horizon momentum effect
disappears**; overhang is not a new coat of paint on momentum, the literature's
claim is the reverse. **Both papers use pre-2000 data — "still alive after
2010" is the open question, not a given.**

**Why this is a CONDITIONER and not a standalone signal, per the corpse it
must respect**: Aegis's pooled reaction lane is closed in every form tested.
`NEGATIVE_RESULTS.md`'s "The event-level learner at a five-session hold
(TRIAL-H5)" is REJECTED by its own registered rule: t 1.14 < 1.5 at the $10M
floor, control's own seed-median +17.64%/yr against a +4.0 ceiling, sign
unstable by era (+23.3/−7.7/+42.0%/yr), drawdown −78% vs a −45% budget, and
the **RW2 random-window null** (`RW2_event_windows_run01.json`, 240 seeded
windows) shows the learner beats its own control in only 44% (1999-2007) and
46% (2016-2024) of starts. `H5|all` is closed, no successor was registered.
Per CLAUDE.md's scope-aware-verdicts rule, **that closure answers "does the
reaction drift, pooled over all holders?" — it never asked "does it drift
conditional on the holder base's unrealised gain/loss?"** This book asks
exactly the second question, on the same closed population, as a re-slice —
it may not re-litigate the pooled claim.

### C.2 The data

**No 13F/holdings data exists in this repo**, so Frazzini's own
holdings-based reference price cannot be built. Use instead the
**Grinblatt-Han price-and-turnover-only construction**, which needs no
holdings vendor:

```
RP_t = (1/k) * sum_{n=1}^{T} [ V_{t-n} * prod_{tau=1}^{n-1}(1 - V_{t-n+tau}) * P_{t-n} ]
CGO_t = (P_{t-1} - RP_t) / P_{t-1}
```

where `P` is price, `V_t` is period `t`'s turnover (`vol_t / shrout_t`, the
same computed column as Book A §2), `k` normalises the weights to sum to 1,
and `T` is the lookback (Grinblatt-Han use `T=260` weeks / 5 years at weekly
cadence; adapt to Aegis's daily/monthly panel as `T=1260` trading days). **PIT
by construction** — every input is the name's own past price and volume,
known entirely as of `t-1`; there is no vendor lag and no leakage risk.

**Typed event / surprise sign**: L2 (typed news events) is not built yet in
this roadmap (gate order: N-C → N-D → N-F → L2 → E1) — **do not wait for it.**
Spec two versions:
- **v0 (usable today, no dependency)**: use the IBES revision columns already
  in `learner/dataset.py`'s feature table — `net_rev_1m`, `target_rev_1m`,
  `consensus_rev_1m` — sign of the monthly consensus revision as the "news
  sign" proxy.
- **v1 (gated on L2)**: swap in L2's typed-event sign once it lands; this is a
  strict upgrade, not a redefinition, and does not require re-registering the
  overhang construction, only the event-sign input.

Momentum control (mandatory, per C.4): `mom_12_1` already exists as a
`learner/dataset.py` feature column — no new computation needed for the
orthogonalisation check.

### C.3 The `Strategy` contract

```python
Strategy(
    strategy_id="disposition_overhang_conditioner_v0",
    title="Good-news names in the top overhang tercile, long-only (Frazzini 2006 / Grinblatt-Han 2005)",
    universe=Universe(
        name="disposition_overhang_universe",
        source="CRSP price/volume (computed CGO) + IBES revision sign (v0) / L2 typed events (v1)",
        floor_dollar_vol_usd=3_000_000.0,
        min_price_usd=5.0,
        max_names=None,
        note="re-measure at the $10M corner too — S49/TRIAL-H5: the documented "
             "effect concentrates in exactly the illiquid names most likely to fail a floor",
    ),
    signal=Signal(
        name="overhang_conditioned_on_good_news",
        column="overhang_rank_within_good_news",  # rank of CGO_t, restricted to
                                                    # names with a positive v0/v1 event this period
        direction=1,
        source="computed CGO (Grinblatt-Han) x IBES revision sign (v0) or L2 event sign (v1)",
        warmup_periods=252,   # CGO needs price/volume history to build RP_t
        note="the eligible set is gated on event sign FIRST, then ranked on overhang "
             "within it — this is the conditioner, not a two-factor blend",
    ),
    construction=Construction(rule="top_k", k=30, weighting="ew",
                              max_single_name=0.08, gross_cap=1.0),
    hold=HoldRule(horizon_periods=3, min_hold_periods=1, scheduled_review_periods=1,
                 stop_loss=-0.20, roi_ladder={},
                 note="post-event drift horizon per Frazzini; re-check against the "
                      "closed H5 book's own horizon (5 sessions) for comparability"),
    sizing=Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0),
    costs=CostModel(transaction_cost_bps=5.0, slippage_bps=1.0),
    benchmark=Benchmark(name="SPY", series_key="spy_tr", beta_matched=True),
    objective=Objective(name="alpha_intercept", periods_per_year=12, utility="risk_adjusted"),
    loss_budget=LossBudget(positions_judged=36, expected_losers=17),
    licence=Licence.PRODUCT_EXPERIMENT,
    engine="series",
    note="respects TRIAL-H5/RW2: the pooled reaction lane is CLOSED (t 1.14, RW2 "
         "44-46% window pass rate); this book re-slices that SAME closed population "
         "by overhang tercile and may not restate the pooled claim as its own",
)
```

### C.4 The twin(s) — scope-aware, per the task's special instruction

**Primary control: the UNCONDITIONED reaction book itself** — the identical
v0/v1 event-sign universe, held the identical way, WITHOUT the overhang
conditioning (i.e., the closed H5-shaped book, or its IBES-revision analogue,
run fresh on the same window as a live comparator rather than cited from its
own closed receipt). This is the only comparator that makes "does the
conditional question the closed verdict never asked" a falsifiable statement
rather than a rhetorical one. **In addition**, per B3's house standard, every
book still gets: a **random-universe twin** (same band, random draw) and a
**beta-matched twin**. Two further controls are mandatory before any
promotion, per angle1's own falsifiers:
1. **Sign-flip placebo**: long good-news/large-loss, short bad-news/large-gain
   — Frazzini reports this leg ≈ 0; if Aegis finds both legs paying, the
   result is drift (momentum again), not disposition.
2. **Momentum-orthogonalisation**: regress with both `mom_12_1` and overhang
   on the right-hand side; overhang's t must survive and momentum's must die,
   or `FAILED_VARIANT`.

### C.5 The forecast row

`make_prediction(ticker="BOOK:disposition_overhang_conditioner_v0",
specialist="disposition_overhang_conditioner_v0", observable=Observable.
BEATS_BENCHMARK, horizon_days=60, probability=Phi(IR_trailing), thesis=
"good-news names with the largest unrealised gains underreact more (Frazzini "
"2006); overhang subsumes momentum (Grinblatt-Han 2005)", counter_thesis=
"the pooled reaction lane is already closed (TRIAL-H5/RW2) and this is the "
"same failure wearing a conditioning variable", model="engine_rule",
model_version="disposition_overhang_v0", benchmark=
"control_twin:unconditioned_reaction_book")`. A second record against
`control_twin:disposition_overhang_random_universe`.

### C.6 The first read

- **Primary metric (deciding, family test #3):** (top-overhang-tercile
  good-news long book) **minus** (unconditioned reaction book, run fresh on
  the identical window), block-mean over monthly date blocks, NW lag-2 t.
- **Reported, never deciding:** the sign-flip placebo (expect ≈0), the
  momentum-orthogonalisation regression, the era split (this repo has been
  burned three times by an effect that was really 1999-2007 — report per era
  with a decay t, per CLAUDE.md's "same sign in every era" rule), the v0-vs-v1
  event-sign comparison once L2 lands.
- **MDE**: `2.8 × cross_sectional_monthly_excess_sd / sqrt(n_effective date
  blocks)` — **compute from the built overhang panel's own dispersion; this
  spec gives the formula, not the number, because the panel does not exist
  yet.**
- **Earliest decision date**: v0 (IBES revision sign) can run as soon as the
  CGO computation is built against existing price/volume data — no external
  wait. v1 (L2 typed events) is gated on L2 landing (chunk 4/7).
- **Decision rule**: `PRODUCT_PROMISING` → primary metric clears its computed
  MDE, NW t ≥ 2.0, sign-flip placebo indistinguishable from 0, momentum dies
  under orthogonalisation, sign stable across at least 2 of 3 eras tested.
  `FAILED_VARIANT` → sign-flip placebo also pays (it's drift, not disposition)
  OR momentum survives orthogonalisation (it was momentum in costume) — either
  clause alone closes it. `CONDITIONAL` → clears the primary metric but fails
  one era-stability or floor check.

---

## BOOK D — the abstention book (§11c idea #7)

### D.1 The mechanism

Selective prediction / learning-with-a-reject-option, transplanted to
portfolio form (Chalkidis & Savani): a selector that reports a coverage
fraction and trades only inside the covered region beats its always-in twin
on risk-adjusted terms at coverage as low as 17-55%, and the advantage **grows
with slippage** — abstention's cost is exactly zero. **Must respect
NEGATIVE_RESULTS §1, verbatim**: the existing timing strategy already LOST to
buy-and-hold on both axes — total return **+28.3% vs +114.8%**, Sharpe
**0.432 vs 0.837** (2020-01 to 2025-06, 66 monthly signals, 32bps round trip).
Abstention is timing with a stricter trigger and **must beat that receipt
directly, not merely exist as a different idea.** Barber & Odean: high-turnover
retail households earned 11.4%/yr net vs 18.5%/yr for low-turnover, **with no
difference in gross returns** — the entire value proposition here is that
abstention converts "nothing works most of the time" (Aegis's own most robust
finding) into a policy, at zero mean cost, not that it adds alpha.

### D.2 The data

**No new data acquisition.** The default holding is the existing `spy_tr`
series (`Benchmark.series_key`). The trigger — "a strong typed event" — is
gated on L2 (not built in chunk 5); **do not wait for it.** Two usable
triggers exist today:
- **v0**: R2's own `CONFIDENCE` field (0.0-1.0), the only already-produced,
  already-calibrated confidence number in the system with a receipt
  (`docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`) — R2 is the one lane
  the roadmap calls "alive."
- **v1**: the existing arena composite score's own cross-sectional extremity
  (`|composite_z|`) as a confidence proxy, usable on names R2 does not cover.
Both are reported; whichever the builder wires up first, do not block on L2.

### D.3 The `Strategy` contract

`Construction`'s `KNOWN_CONSTRUCTION` tuple (`top_k`, `composite_top_k`,
`rank_weight`, `passthrough`) has **no threshold-coverage/abstain rule.**
Recommend adding one (`"threshold_coverage"`) before this book is built
cleanly; **until then**, the existing machinery can represent abstention with
no contract change: add a synthetic always-eligible "no-event" asset
(`CASH_OR_SPY`) to the universe with a fixed neutral signal value, so that in
any period where no name's confidence clears the threshold, `top_k` naturally
selects the synthetic asset and the book is, in effect, in cash/index. Flag
the clean fix as a builder TODO; ship the workaround now.

```python
Strategy(
    strategy_id="abstention_book_v0",
    title="Cash/index by default; deviate only above a confidence threshold",
    universe=Universe(
        name="abstention_universe",
        source="R2 digest confidence (v0) or arena composite extremity (v1), plus a "
               "synthetic CASH_OR_SPY fallback asset",
        floor_dollar_vol_usd=3_000_000.0, min_price_usd=5.0, max_names=None,
    ),
    signal=Signal(name="event_confidence", column="r2_digest_confidence",  # or composite_z_abs
                 direction=1, source="R2 monthly digest / arena composite",
                 note="the CASH_OR_SPY synthetic asset always carries confidence=0.5"),
    construction=Construction(rule="top_k", k=5, weighting="ew", max_single_name=0.30,
                              gross_cap=1.0,
                              note="WORKAROUND for the missing threshold_coverage rule "
                                   "(see D.3); k=5 falls back to the synthetic asset "
                                   "whenever no real name clears the threshold"),
    hold=HoldRule(horizon_periods=1, min_hold_periods=1, scheduled_review_periods=1,
                 stop_loss=None, roi_ladder={},
                 note="monthly, matching R2's own cadence"),
    sizing=Sizing(rule="equal_weight", gross_cap=1.0, notional_usd=10_000.0,
                 overlays=("abstention_gate",),
                 params={"confidence_threshold": None,  # TO BE CALIBRATED, see D.6
                        "default_asset": "SPY"}),
    costs=CostModel(transaction_cost_bps=5.0, slippage_bps=1.0,
                    note="turnover occurs only on regime switches; expected low"),
    benchmark=Benchmark(name="always_invested_twin", series_key="",
                        beta_matched=False, is_own_universe_average=False,
                        note="the PRIMARY comparator per this book's own design; "
                             "SPY/random/beta twins are ALSO carried per B3's house standard"),
    objective=Objective(name="terminal_wealth_at_drawdown_budget",
                        periods_per_year=12, drawdown_budget=-0.20,
                        utility="risk_adjusted"),
    loss_budget=LossBudget(positions_judged=24, expected_losers=10,
                           note="must be BELOW the always-invested twin's own historical "
                                "loser-month rate to be worth anything"),
    licence=Licence.PRODUCT_EXPERIMENT,
    engine="series",
    note="respects NEGATIVE_RESULTS §1: the existing timing strategy lost to buy-and-hold "
         "(+28.3% vs +114.8%, Sharpe 0.432 vs 0.837); this book must beat that receipt "
         "directly, printed on the same axes, not merely exist as a different construction",
)
```

### D.4 The twin — the always-invested twin IS the control (per the task)

Identical selector, identical universe, identical hold rule, **coverage
forced to 100%** (the abstention gate disabled, so it always holds its
top-`k` real names, never falling back to `CASH_OR_SPY`). This is the
book's primary comparator, created at the same time as the book (B3). A
random-universe twin and a beta-matched twin are ALSO carried per the house
standard, but they are secondary here — the always-invested twin is the one
the idea's own falsifying observation names.

### D.5 The forecast row

`make_prediction(ticker="BOOK:abstention_book_v0",
specialist="abstention_book_v0", observable=Observable.BEATS_BENCHMARK,
horizon_days=20, probability=<the confidence score itself, already in [0,1]>,
thesis="deviating into a name only above a confidence threshold beats being "
"always invested, net of costs (Chalkidis & Savani; Barber-Odean)",
counter_thesis="abstained months have the same mean excess as acted months, "
"so the confidence signal carries no information and this is a cash-drag "
"machine", model="engine_rule", model_version="abstention_v0",
benchmark="always_invested_twin")`. The always-invested twin carries its own
fixed `probability=0.5` record every period.

### D.6 The first read

- **Primary metric (deciding, family test #4)**: terminal wealth of the
  abstention book vs the always-invested twin **at equal realised maximum
  drawdown** (the declared PRODUCT ruler — `terminal_wealth_at_drawdown_budget`
  — is exactly suited here, since the pitch is cost/drawdown avoidance, not a
  return edge).
- **Sharpest single falsifier, reported alongside**: bucket months by
  confidence decile; compute realised excess-vs-twin per decile. **The idea is
  wrong if that risk-coverage curve is flat or inverted** — if the
  top-confidence decile's excess is not above the bottom decile's over ≥24
  monthly blocks — this is the idea's own stated kill condition and must be
  checked before the headline number is trusted.
- **MDE**: with terminal wealth as the primary metric, use the same monthly
  block-mean-excess MDE formula as the other three books for the underlying
  decile test; **compute the actual dispersion once the confidence series
  exists — no number is substituted here either.**
- **Earliest decision date**: 24 monthly blocks after seeding, per the idea's
  own falsifier requirement (`angle4_ideation.md` §1) — this book cannot be
  read early even if it looks good at month 6.
- **Decision rule**: `PRODUCT_PROMISING` → terminal wealth beats the
  always-invested twin at equal or better realised drawdown, AND the
  risk-coverage curve is monotone (Spearman > 0, its own significance
  checked), AND the book's own headline numbers (printed on NEGATIVE_RESULTS
  §1's exact axes: total return, Sharpe) beat +28.3%/0.432 — beating the twin
  is necessary but not sufficient; beating the closed receipt is the
  additional, explicit bar this idea must clear. `FAILED_VARIANT` → the
  risk-coverage curve is flat/inverted (confidence carries no information) OR
  terminal wealth is below the twin's at equal drawdown. `CONDITIONAL` →
  beats the twin but the curve is not clearly monotone, or coverage is outside
  the literature's 17-55% band by a wide margin (suggesting mis-calibration).

---

## Appendix — pre-registration drafts (UNSIGNED), in the shape of TRIAL-R2

Each draft below follows `docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`'s
sections (Corpse check → Hypothesis → the two panels/eras → Primary metric →
Power §64 → Decision rule → Frozen parameters → Corpse-check result → What
this rule may NOT do → Registry), abbreviated to what is new relative to the
shared conventions in §0 above. **All four share Family =
`NIGHT_JOB_BOOKS_2026_09`, Licence = `PRODUCT_EXPERIMENT`, and accrue zero
capital, per CLAUDE.md's three licences.**

### TRIAL-DRAFT-A — si-low-turnover-high-v1

- **Corpse check**: resurrects nothing refuted (NEGATIVE_RESULTS §24 tested
  the CHANGE signal and a days-to-cover LEVEL, not this SI-level x
  turnover-level double sort). Run `scripts/lint_prereg.py` before commit.
- **Hypothesis**: names in the top SI-low/turnover-high double-sort cell,
  $3M-floor eligible, beat a random-universe twin of the same size and band by
  more than the MDE computed from the built panel's 2011-2024 dispersion.
- **Two eras that decide differently**: 1988-2010 reported never deciding;
  2011-2024 is the sole confirm slice (post-publication).
- **Primary metric**: net block-mean monthly excess, NW lag-2 t, per A.6.
- **Power**: computed from the panel's own dispersion once built (A.6); not
  invented here.
- **Decision rule**: per A.6.
- **Frozen parameters**: the `Strategy` object in A.3, hashed at registration
  commit; no field moves mid-trial without a new `strategy_id`.
- **What this rule may NOT do**: no prompt/parameter search after the first
  read; no restating the $3M-floor number as net if the $10M-floor cell
  disagrees; no claiming `RESEARCH_CLAIM` from this registration alone.
- **Registry**: `rule_experiments` row `si-low-turnover-high-v1`.

### TRIAL-DRAFT-B — insider-cluster-length-v1

- **Corpse check**: resurrects nothing (the 13D/13G family stays untouched;
  §46/N1 licensed rather than blocked filing-date PIT entry).
- **Hypothesis**: 4-5-day insider-purchase clusters, entered at the cluster's
  latest filing date, beat a random Form-4-active-universe twin over
  BHAR(22,90), 2017-2024, AND the same-day-cluster diagnostic arm does not.
- **Primary metric**: per B.6.
- **Power**: per B.6, computed from the built cluster panel.
- **Decision rule**: per B.6.
- **Frozen parameters**: the `Strategy` object in B.3; the cluster-length
  bucket boundaries (`N=0` vs `N∈{4,5}`) are frozen at registration.
- **What this rule may NOT do**: no re-bucketing cluster length after seeing
  results; no shorting cluster sales (KKW: uninformative, and this would be a
  new arm); no claiming the executive-only cut without registering it
  separately.
- **Registry**: `rule_experiments` row `insider-cluster-length-v1`.

### TRIAL-DRAFT-C — disposition-overhang-conditioner-v0

- **Corpse check**: **must cite TRIAL-H5 and RW2 explicitly as the parent
  closure it re-slices**, not resurrects — the linter should be checked for a
  `SELECTION_WINDOW_CONTRADICTS_PARENT`-style flag given H5 is a named parent.
- **Hypothesis**: within H5's closed population, the top-overhang-tercile
  good-news subset beats the unconditioned book (H5-shaped or its IBES
  analogue) run fresh on the same window, by more than the panel's own MDE.
- **Primary metric**: per C.6.
- **Power**: per C.6, computed from the built overhang panel.
- **Decision rule**: per C.6, including the two mandatory falsifiers
  (sign-flip placebo, momentum-orthogonalisation) as `FAILED_VARIANT`
  triggers, not merely reported diagnostics.
- **Frozen parameters**: the `Strategy` object in C.3; the Grinblatt-Han
  formula and `T=1260`-day lookback; the v0 IBES-revision-sign definition
  (v1's L2 swap is a separate registration amendment, not a redefinition).
- **What this rule may NOT do**: no claiming the pooled H5 result was
  "really" this conditional result; no dropping the sign-flip or momentum
  control because the primary metric alone looks good.
- **Registry**: `rule_experiments` row `disposition-overhang-conditioner-v0`.

### TRIAL-DRAFT-D — abstention-book-v0

- **Corpse check**: **must cite NEGATIVE_RESULTS §1 explicitly as the receipt
  it must beat**, with its exact numbers reproduced in the registration text
  (+28.3%/+114.8%, Sharpe 0.432/0.837) so a later reader cannot quietly forget
  the bar.
- **Hypothesis**: an abstention gate on top of an existing selector beats the
  same selector always-invested, at equal or better realised drawdown, over
  ≥24 monthly blocks, with a monotone risk-coverage curve.
- **Primary metric**: terminal wealth vs the always-invested twin at equal
  drawdown; per D.6.
- **Power**: per D.6; the ≥24-month minimum is itself the design's floor, not
  a computed MDE substitute.
- **Decision rule**: per D.6, including the explicit requirement to beat
  NEGATIVE_RESULTS §1's own numbers, not only the twin.
- **Frozen parameters**: the `Strategy` object in D.3; whichever confidence
  trigger (v0 R2 / v1 composite) is wired up first is named and frozen; a
  later swap is a new registration, not an amendment.
- **What this rule may NOT do**: no reading the risk-coverage curve before 24
  blocks; no declaring victory on terminal wealth alone if the curve is flat;
  no comparing against a strategy weaker than NEGATIVE_RESULTS §1's own timing
  receipt.
- **Registry**: `rule_experiments` row `abstention-book-v0`.

---

STATUS: COMPLETE.
