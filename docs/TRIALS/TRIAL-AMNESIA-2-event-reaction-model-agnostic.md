# TRIAL-AMNESIA-2 — can a model read an earnings set-up it cannot recognise? Any model, same test

**Pre-registered:** 2026-09-28 (Hong Kong evening), before any forecast call ·
**Licence:** `PRODUCT_EXPERIMENT` (no claim; nothing here is a `RESEARCH_CLAIM`) ·
**Class:** measurement of the INSTRUMENT and of each MODEL, never an arm or a book ·
**Code:** `scripts/fiction_backtest.py` · **Tamper evidence:** this file's sha256 is
stamped into `backend/data/optimus/fiction_backtest/<run>/sealed/plan_clean.json`
before the first call (commits are the owner's to make; the hash stands in until then).

## Predecessors (read, not re-derived)

- **TRIAL-LLM-AMNESIA-1 / 1B** (`C:\Users\mrthn\Aegis module\TRIALS\PREREG_LLM_AMNESIA_1.md`,
  verdict `docs/AMNESIA_VERDICT_2026-08-08.md`): an instruction to forget does nothing
  (recall 15.8% vs 15.8%); masking holds (0 of 240 identified); synthetic = masked within
  0.0004 Brier; the 12-month task was unlearnable for the LLM AND a logistic baseline
  (Brier 0.25). Its verdict names this trial: "AMNESIA-2 moves to short-horizon event
  reactions (5-day abnormal return around earnings / FDA decisions) where the baseline bank
  has measurable signal, with famous-case stratification and the positive control built in
  from the start." No run of it was found on disk.
- **TRIAL-LEAK-1** (`docs/TRIALS/TRIAL-LEAK-1-identified-vs-masked.md`): the era
  difference-in-differences on a fixed slate; canary wave ran, no verdict on disk. Not
  duplicated: that trial asks about memory across eras on price snapshots; this one asks
  about skill on dated EVENTS, per MODEL.
- **X2** (`docs/research_notes/2026-09-28/lane_x_experiments_2026-09-28.md`): DeepSeek
  (`deepseek-flash`) 48-49% on 5-session direction after its measured 2025-12 cutoff,
  80% ranges worse than the trailing sd. FAILED_VARIANT.

Resurrects: AMNESIA-1's retired task — new instrument: a dated event with a baseline that
has signal (the stock's own past earnings reactions), a scenario answer graded for
calibration, and a model-agnostic arm interface including a file arm for models without an
API key here.

## Hypotheses (honest priors)

- **H1 (the owner's).** A stronger model, shown a masked or fictionalised version of a real
  pre-earnings situation, calls the 5-session move versus the median stock better than a
  coin and better than 12-1 momentum. **Prior: no** for `deepseek-flash` (X2: 48%); open
  for stronger models, which is why the arm interface exists.
- **H2 (magnitude).** The model's 80% range for the 5-session return beats the trailing
  63-session volatility prior on the interval score. **Prior: yes against the vol prior**
  (the case says an earnings report is due, which the vol prior ignores) and **no against
  the stock's own past-earnings-reaction prior** — i.e. `BETA_EXPLAINS` is the expected
  magnitude verdict.
- **H3 (text as numbers).** The four scored features (novelty, emotional intensity,
  management confidence, crowdedness) carry rank information about |5-session move| after
  controlling for trailing volatility. **Prior: weak or none**, reported, never deciding.
- **H4 (the fiction holds).** On 30 famous pre-2025-06 earnings moves, A3 synthetic
  identification ≤ 10% and A3 hit rate < 0.70.

## Design (frozen)

- **Event:** an 8-K with item 2.02 (`backend/data/optimus/edgar_8k/eightk_items.parquet`).
  Decision session t = the last session strictly before the filing date, so the window
  t → t+5 contains the reaction whatever the release time. The case says a report is
  expected within two sessions (earnings dates are announced in advance; stated as an
  assumption).
- **Packet, everything dated strictly before t's calendar date** (prices to t's close):
  price/volume summary, past four 5-session earnings reactions, fundamentals by FILING
  date, analyst actions by their own dates, typed events and headlines (14 days, 8 max, 3
  snippets of 220 characters), coarse GICS sector, size bucket.
- **Levels (AMNESIA arms):** A0_NAMED (real name, dates, levels); A2_MASKED (no name, days
  before 'day 0', last close rebased to 100, no money amounts, years removed from text);
  A3_SYNTHETIC (AMNESIA's fabricated name/ticker/year 2100+, every price rescaled by one
  random factor and every size by another, so every ratio and percentage is unchanged;
  years in text shifted by the same constant). A1 (instruction) is not re-run.
- **Canary on every case and level, before the forecast, AMNESIA-1's wording:** recall
  canary on A0, identification canary on A2/A3. A leaking A2/A3 prompt (per
  `leakage_probe.masking_violations` + alias scan) is REFUSED before any call.
- **Samples, never pooled:** CLEAN = 600 events with t in 2026-07-01 … 2026-09-03 (after
  every stated cutoff: deepseek-flash 2025-12 measured; Opus June 2026 stated), stratified
  3 size × 3 volatility terciles, delisted names kept. FAMOUS = 30 largest mega-liquid
  earnings moves 2018-01 … 2025-06, one per name (the leak test). BACKTEST = 1,200 events
  in 20 weekly blocks 2018-2025, CONTAMINATED by construction unless H4 holds; planned,
  not run tonight.
- **Answer:** three scenarios (prob, return range), P(beat median stock) at 5 and 21
  sessions, central + 80% range at 5 sessions, what would change the view, four features
  0-1. STRICT parse; a reply that does not parse is refused and counted, never repaired.
- **Models:** DeepSeek via `llm_analyzer.call_named` (served `deepseek-flash`), NVIDIA NIM
  free tier if the key serves, local only if already up (never started), FILE arm for any
  model run by the orchestrator (e.g. Claude Opus sub-agents) that sees only case files.

## Primary metric and decision rule (per cell = arm × level × part)

Primary: **5-session hit rate of `p_beat_median_5d` vs the realised beat of the median
stock**, Wilson 95% and week-block t. Magnitude primary: **interval score of the 80% range**
vs both priors, week-block t.

- Direction: `ALPHA_DETECTED` if Wilson low > 0.5 AND week-block t ≥ 2 AND hit > the 12-1
  momentum call's hit on the same rows; `BETA_EXPLAINS` if the first two hold but momentum
  does as well; `FAILED_VARIANT` if not and Wilson high < 0.55; else `CANNOT_DISTINGUISH`.
- Magnitude: `ALPHA_DETECTED` if the interval-score difference is < 0 with t ≤ -2 against
  BOTH the vol prior and the past-earnings prior; `BETA_EXPLAINS` if only against the vol
  prior; `FAILED_VARIANT` if worse than the vol prior with t ≥ 2; else `CANNOT_DISTINGUISH`.
- Leak (FAMOUS): the fiction LEAKS if A3 identifies the company on > 10% of canaries or the A3
  famous hit rate is ≥ 0.70. A leaking fiction voids every BACKTEST reading for that model.
- Reported, never deciding: 21-session direction (8 of ~9 clean weeks mature by 2026-09-25;
  the rest mature by ~2026-10-06 and are read then), Brier vs base rate, ECE
  (`protocol_p16.ece`), reliability tables, scenario calibration, feature partial Spearman.

**MDE.** 600 rows per level: row-level 80%-power MDE ≈ 5.7 pp of hit rate; with ~9 weekly
blocks the honest week-block MDE is wider (printed on the receipt). The clean window cannot
see an edge below ~6 pp and says so.

## Power fields (R13)

- declared_effect_size: 6pp
- event_frequency_per_year: 10000
- outcome_dispersion: 50%
- outcome_horizon_days: 5
- dependence_unit: one earnings week (events in the same week share the market's move)
- corpus_years: 1
- slice_purpose: EXPLORE
- cross_sectional_k: 60
- cross_sectional_rho: 0.05

(cross_sectional_rho is ASSERTED, not measured: the outcome is beat-the-median, which removes
the market's move, so the residual same-week correlation should be small; the receipt prints
the week-block t beside the row-level Wilson so the reader sees both readings. The linter's
first verdict without k/rho was UNPOWERED_AT_REGISTRATION: ~50 independent 5-day windows a
year if every same-week event is one observation, smallest resolvable effect 20 pp.)

(6 pp of 5-session hit rate, 0.56 vs 0.50, is the smallest edge the clean sample can see.
~10,000 item-2.02 filings a year in the 8-K file; the clean draw is 600 events from one
season, 2026-07 … 09. The hit is binary, sd 0.5 = 50%; the 5-session return around earnings
has a cross-sectional sd of roughly 8-10%, printed on the receipt.)

**Corpse check** (`Aegis module/scripts/lint_prereg.py`, 2026-09-28): MISSING_POWER_FIELDS ->
UNPOWERED_AT_REGISTRATION (no k/rho) -> UNDECLARED_SLICE_PURPOSE -> **PASS** (n_required 545,
n_available 766 under the asserted rho, smallest resolvable effect 5.1 pp). Nearest prior:
PREREG_LLM_AMNESIA_1 (0.28).

## Frozen parameters

Horizon 5 (21 reported); the prompt `FORECAST_SYSTEM` (its sha256 on the plan); sample seed
20260928; the three levels; universe filters (close ≥ $3, 63-session median dollar volume
≥ $5M, ticker ≥ 3 letters, a known issuer name); DeepSeek temperature 0.3 (the route's
default), max_tokens 900; the dollar cap $2.00 for everything run under this trial tonight.

## What this may NOT do

No row reaches `predictions.jsonl`, a book, an order or a sizing rule. No LLM has authority
over capital. A result on the BACKTEST part is not a result unless H4 holds for that model.
A second prompt variant is a new trial.
