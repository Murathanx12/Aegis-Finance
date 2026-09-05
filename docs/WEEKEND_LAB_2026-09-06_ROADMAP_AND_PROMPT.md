# WEEKEND LAB — 2026-09-06/07 — non-stop training on the clean tape (roadmap + the prompt for Opus 5)

**Paste this whole file to Opus.** Fable 5.1 wrote it after reading
`BUILD_NIGHT_LAB_2026-09-05.md`, the leaderboard, `learner/inference.py` and
`scripts/night_lab.py`. Murat sleeps and works around it; the lab must run
without him. Everything is pushed: finance `ef41b87`, terminal `c190351`
(main), optimus `b0c0330`.

## 0. Why the plan looks like this

The night lab's honest result: the best learner arm is +14%/yr ahead of the
market on 90 months and **does not survive being one of 32 cells** (DSR 0.197
below the 0.2305 a zero-edge search produces; SPA p 0.29; PBO 0.29). At that
Sharpe, t = 2 needs **16.1 years of out-of-sample months; the panel has 7.**

So "train the NN more" on 2013-2024 cannot change the verdict — the
statistics are the ceiling, not the model. The weekend buys the two things
that move the ceiling:

1. **Time.** `ibes__ptgsumu` on disk starts **1999-03-18**; CRSP daily is on
   disk from **1990**. A 1999-2024 panel gives ~19 out-of-sample years instead
   of 7. That is the single largest lever available, and it is free.
2. **Information the panel does not have yet:** supply-chain edges we already
   own (MARKET-GRAPH-1), OptionMetrics implied vol/skew (on disk 1996-2024),
   8-K event counts (tape on disk), delisting context, behavioural proxies.

And one enabler: **CUDA torch** so neural nulls stop costing 80 s a draw.

Everything runs through the existing `scripts/night_lab.py` runner (STOP
file, receipt per run, leaderboard) and grades through `learner/inference.py`
(DSR, SPA, PBO, family-max). No Claude API. LLM spend cap **$5** (DeepSeek /
gpt-5-nano only, through the spend gate). No push, seal, order or Railway
change by the lab; Murat pushes when he checks in.

## 1. Rules (unchanged from Friday, plus two)

- Clean panel only (`learner-train-table-2` schema or its successor). Every
  market number from `learner/benchmark.py`.
- Every job writes a receipt even when it finds nothing; a traceback IS the
  receipt; loud refusals, never silent zeros; family size and family-max p on
  every edge claim; DSR beside every Sharpe.
- **New:** every receipt names `n_oos_months` and `years_needed_for_t2` next
  to its t. A verdict is NOISE / CANNOT DETERMINE / NOVEL, and NOVEL requires
  DSR > 0 after the family, SPA p < 0.10, PBO < 0.5, **and** the sign holding
  in ≥ 2 of 3 eras (1999-2007, 2008-2015, 2016-2024).
- **New:** two agents per repo max; the coordinator commits per job on
  `lab/weekend-2026-09-06` and merges to main when the suite is green; the
  runner loops until STOP; a job that fails twice is skipped, not retried
  forever.
- Fast suite at the start and the end (`AEGIS_IGNORE_DOTENV=1 python -m
  pytest backend/tests/ -m "not slow"`); terminal `python run_tests.py`.

## 2. The queue (priority order; `scripts/night_lab.py` `QUEUE` for
`RUN_DATE="2026-09-06"`; minutes are per-job timeouts)

**W0 — CUDA torch (20 min).** `pip install torch --index-url
https://download.pytorch.org/whl/cu128` in the repo venv; receipt records
`torch.cuda.is_available()`, the device name, and one timed forward/backward
of the v2 encoder on GPU vs CPU. If it fails, record why and continue on CPU.

**W1 — The long panel, 1999-2024 (180 min).** Extend `learner/dataset.py`
(or a `build_long_panel` sibling) to `ibes__ptgsumu` + `recdsum` from
1999-03 with CRSP daily 1998-2024 (need one lookback year), `dlret` merged
(Shumway fill), the same hygiene. Gate tests: the AAPL 2013-06 share-basis
test AND a 1999-era case (pick a name with a known 2:1 split in 2000 — e.g.
verify `meanptg_u / prc` is within 0.5-3 on both sides of the split). Write
`train_table_long.parquet`, schema `learner-train-table-3`, receipt with
name-months, months, permnos, coverage by year (IBES coverage is thinner
pre-2004 — print it; do not fake it). Manifest row.

**W2 — Learner loop on the long panel (repeat; 240 min per pass).** The L1
cells (ridge / lgbm × raw / residual × 1/3/6/12m × 10/25 bps), walk-forward
from 2004 (five-year warm-up), calendar-aligned families (the alignment bug
Opus caught on Friday is now a test), ≥256 model-null seeds for the champion
cell (lgbm on CPU is fine; run it as its own job W2n so it does not block),
DSR / SPA / PBO / family-max, three-era sign table. **Variant list for the
loop:** (a) baseline; (b) prior refit per split; (c) feature-family ablation
one family at a time; (d) quantile heads q05/q50/q95 (pinball) for a tail
estimate; (e) turnover hysteresis (buy top-50, hold until rank > 100) at 10/25
bps — the cheapest way to make a real edge survive costs. Leaderboard row per
variant; the runner advances to the next variant on each pass.

**W3 — Neural, on GPU (repeat; 120 min per pass).** The v2 encoder on the
long panel with prior refit per split, ±5 sd clip, calibration head; seeds
×16 per pass (GPU makes this cheap); **self-supervised pre-training pass**
(masked-feature reconstruction on the whole 1999-2024 feature table with no
target visible — this is the legitimate "unsupervised training" use), then
fine-tune heads; compare against `lgbm_clf` on after-cost TW with DSR. Keep
only what beats lgbm after the family. Variant list: encoder width, pretrain
on/off, quantile heads, horizon set.

**W4 — Customer / competitor momentum from MARKET-GRAPH-1 (90 min).** Read
`../Aegis module/runs/MARKET-GRAPH-1/edge_instances.parquet`; build
customer→supplier and competitor tables with `valid_from` = filing date;
features = lagged 1-month returns of customers / competitors / shared-tech
peers; join to the long panel (edges exist 2015-2024 only — the receipt says
so); IC and top-decile VW books at 1/3m with inference; write
`backend/data/optimus/graph/companyworld_v1.parquet` (`graph_layer=FACT`,
`valid_from`, `valid_to`, `source`, `confidence`). Then feed the feature into
W2/W3's next pass.

**W5 — Options → stock (120 min).** OptionMetrics `vsurfd` via
`link_optionm_crsp`: 1-month ATM IV change, call-put IV spread, skew;
cross-sectional IC and top-decile VW at 1/3m on the long panel with
inference; peer lead-lag through W4's competitor table. Feed into W2/W3.

**W6 — Behavioural proxies (45 min).** 52-week-high proximity, 60-day VWAP
anchor, volume z-score attention; IC with size/momentum controls; feed in.

**W7 — Winner / matched-loser factory v1 (180 min).** Per year 1999-2024 on
the long panel: top/bottom 50 twelve-month movers residual to beta×size×
sector; 5 matched controls each; PIT feature deltas at 1/5/21/63/126/252
sessions before the move (analyst, price-shape, 8-K counts from the tape,
W4/W5/W6 features where they exist). Archetype candidates = differences that
clear inference in ≥ 2 eras. Plus the opportunity-recall baseline: what
share of each year's top-50 did (a) analyst upside, (b) 12-1 momentum, (c)
revisions, (d) the W2 champion surface beforehand.

**W8 — States with three nulls (60 min).** L2 as written Friday, on the long
panel; CANNOT DETERMINE is allowed.

**W9 — Band prior on its own live object (30 min).** L9 as written Friday.

**W10 — Era replay v2 data build (60 min, $0).** L10 as written Friday
(windows for 2016-19 from corpus + 8-K ex-99.1; diary scaffolding; nulls 2/3).
Run the decide step on ≤ 100 windows only if the $5 cap has room.

**W11 — Evidence memory write-back (30 min, after each pass).** Every
leaderboard row lands in the registry as `(strategy family, era, state) →
{n_months, sharpe, dsr, spa_p, pbo, verdict}` using the estimator in
`backend/services/arena/trust_router.py` re-keyed to strategy; states IDEA /
CONDITIONAL / SUPPORTED / REGIME_SPECIFIC / COST_KILLED / REFUTED; a single
pass can neither promote nor kill.

**Loop.** After W11 the runner goes back to W2 with the next variant, then
W3, then W11, until STOP. W4/W5/W6 features, once built, are in every later
pass. Each pass appends to `LEADERBOARD.md`; the top of the file carries a
five-line "best so far, with DSR" block the runner rewrites each pass.

## 3. Monday morning (HK evening Sunday / pre-open Monday ET) — Murat, 15 minutes

`aegis-alpha-terminal/docs/RUNBOOK_2026-09-08_REARM.md`: push (done) →
`fleet --deploy <role> --up` for hack3/4/6 → remove `--manage-only` on those
three → confirm `utilization` prints ARMED and the binding constraint →
first seal under hygiene-only → 10:01 ET entries → the minimum hold is 10
sessions and only typed reasons close early. hack1 stays manage-only; hack2/
hack5 stay as they are until B9. The decisions in
`DECISIONS_2026-09-05_PLAIN_LANGUAGE.md` §B.1 (band hygiene-only) apply at
that first seal.

## 4. Sunday-night deliverable

`docs/BUILD_WEEKEND_LAB_2026-09-06.md`, ≤ 2 pages, scoreboard first: the
long-panel size; the best cell on 1999-2024 with n_oos_months, DSR, SPA, PBO
and the three-era table; what the neural arm did vs lgbm on GPU; which new
information (graph / options / behavioural) moved DSR and by how much; the
archetypes and the recall baseline; claims for Fable to attack; LLM spend to
the cent. Roadmap §6 gets a `W weekend lab` row and B10's status if the
neural arm earned one.

*The success criterion is not a Sharpe. It is that on Monday we know, with a
number beside it, whether nineteen years say something seven could not.*
