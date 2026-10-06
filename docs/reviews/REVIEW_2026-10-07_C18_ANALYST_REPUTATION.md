# REVIEW 2026-10-07 — C18 Analyst reputation + snowball shadow (adversarial, Opus 5.5)

Scope: `backend/services/analyst_reputation.py`, `backend/services/snowball_shadow.py`,
the C18 diff in `scripts/opportunities_build.py` and the Explorer frontend, and the receipts
`analyst/reputation_weights_2026-10.json`, `analyst/snowball_shadow.jsonl`,
`analyst/snowball_rho_20261006T214926Z.json`, `opportunities/opportunities_2026-10-06_20261006T214339Z.json`.
Read-only. Every number below was recomputed from the files on disk.

## VERDICT

**MERGEABLE AS PLUMBING, NOT AS A SIGNAL. On its own data the reputation weight does not persist:
the module's first-half weights rank the second half's firm edges at Spearman -0.31 (48 firms,
>= 50 claims each). It shows a number the system has not earned the right to show.** The engineering is careful: the base
rate is strictly PIT (it reproduces exactly on three rows I checked), REPLAY and FORWARD are labelled,
and the v3.2 lists are byte-identical. But the thing being weighted has no demonstrated persistence.
`n_effective` cannot measure what the UI says it measures, and `weighted_upside` brings back a level
the registry already closed as perverse. Nothing here should change tomorrow's buy, and it does not.
The danger is that the tooltip invites the owner to act on it anyway.

**Score: 52 / 100.**

## Findings

### F1 — HIGH. The reputation does not persist on its own data. The weights are noise, and the point estimate says they are inverted.

Claims rebuilt with the module's own `build_claims` (72,108 claims; the receipt has 71,843 because
the file has grown since). I split them at the median event date (2025-10-17) and correlated each
firm's edge (hit rate minus the direction base rate) across the two halves:

| min claims per half | firms | Spearman (pooled base, as the module) | Spearman (month x direction demeaned) |
|---|---|---|---|
| 20 | 52 | -0.228 | -0.062 |
| 50 | 46 | -0.349 | -0.184 |
| 100 | 41 | -0.299 | -0.173 |

`reputation_tables` on the first half alone, scored against the second half's raw firm edge (48 firms,
>= 50 claims): **Spearman -0.311.** For comparison, ANALYST-SKILL-1 on IBES found +0.76 persistence
between 2013-15 and 2016-18, but that was a different skill measure over 3-year windows. On this
yfinance hit-rate measure there is no evidence of persistence, and the point estimate is reversal.

The likely mechanism is regime, not skill. The raise hit rate moves from **0.20 to 0.58 by month**
(2025-04: 0.26, 2025-10: 0.58, 2026-07: 0.20), while the base rate is pooled over the whole window.
A firm whose raises happen to fall in Oct-Nov 2025 therefore "earns" an edge. Demeaning by month
removes most of the signal and leaves roughly zero. In addition, claims share outcomes: there are
**2.87 claims per ticker-month**, and several firms raising the same name in the same week are one
outcome, not three, so the n behind K1/K_SUB is overstated.

Nothing in the chunk tests out-of-sample persistence. The test named
`test_one_reliable_firm_outweighs_each_unreliable_one...` is synthetic. **A weight with no
persistence test should not appear in a "weight-bearing firms" list.**

### F2 — HIGH. The PIT filter is a tautology at the current as-of and adversely selected at any past as-of. This is the same failure shape as C9-F1.

- `pulled_at` dates: **394,848 of 395,127 rows (99.93%) carry 2026-10-06 16:50-17:09.** The receipt
  says `rows_known_before_asof: 395,115 == rows_total: 395,115`, so the filter removed nothing.
  Cutting the as-of "to the minute" (21:39) changed nothing except that the filter now passes
  everything instead of almost nothing.
- **99.6% of the claims in the weights were first observed by us after their own resolution date**
  (first_seen > public_at + 92d). For the October receipt this is not a leak, because as-of is now
  and all of them resolved before now *by the vendor's event_date*. But PIT therefore rests entirely
  on the vendor's `event_date`, and the "first-seen gate" contributes nothing. The docstring's
  "Two clocks, both enforced" overstates this.
- The deleted first receipt is the proof. It admitted 279 rows, and **279 is exactly the number of rows
  whose `pulled_at` is not 10-06**: the rows the latest pull did *not* return. They come from 15 tickers
  (DOMO 138, TBPH 77, ATAI 31) that left the request list, and two (DPZ 2013, HTLD 2013) the vendor
  re-timestamped by hours. So at any as-of before the last pull, the filter admits only the rows the
  vendor stopped confirming. That is adversely selected, not conservative. Do not use it for a backtest.
- Answer to the brief: the share of resolved claims first seen after the as-of is **0% by
  construction**. The share first seen after their own resolution is **99.6%**. The data on disk can
  prove neither the absence nor the presence of vendor backfill. It does show that the vendor mutates
  timestamps (DPZ, HTLD).

### F3 — HIGH. `n_effective` cannot fall because firms are unreliable. It falls only when they disagree in reliability. The UI copy implies otherwise.

Kish n is scale-invariant: five firms at w=0.5 give **5.0**, five at w=1.5 give **5.0**, and one 1.5
with four 0.5s gives **3.77**. A name covered entirely by the worst firms shows full coverage. The
tooltip ("It equals the firm count only when every firm is equally reliable") is literally true but
is read as "lower = worse analysts". The quantity that answers "how much is this consensus worth"
is the sum of weights (or the mean weight beside n), not Kish.

### F4 — MEDIUM-HIGH. "n_eff X of Y" compares two populations. 61 names show n_eff above the analyst count.

`n_targets` is yfinance `numberOfAnalystOpinions` (snapshot). `n_covering_firms` / `n_effective` come
from firms with a dated revision row in the previous 365 days. On the receipt, **61 tickers have
n_effective > n_targets** (ANAB 8 -> 11.8, ALIT 3 -> 5.83, APPS 2 -> 3.86). The builder's own example
"SOC 4 -> 4.63" is one of them, presented as if it were a down-weighting. `weighted_median_target`
uses each firm's last revision-file target, up to 365 days old, while `median` is today's snapshot.
They differ by more than 25pp on **24% of the 877 names** that carry both.

### F5 — MEDIUM. 45 names show a weighted upside built from one firm (n_eff = 1.0).

**45 tickers** have `n_effective < 1.5` and a non-null `weighted_upside` (e.g. CUE +241%, IMSR +300% vs
snapshot +220%, DGXX +34% vs +128%). `NOVT` (cliff_replaced) is n_eff 1.00 from one covering firm.
These are muted in the tooltip, not green or sorted (see F7), but a one-firm "weighted" number is
just that firm's target. Print null below n_eff 2, or label it "single firm".

### F6 — MEDIUM. `weighted_upside` re-weights a signal the registry already closed as PERVERSE.

The pull receipts carry `analyst_target_upside_xs CLOSED/PERVERSE: t -3.6 large/mid, -7.2 small. Do
not rank on the LEVEL.` ANALYST-SKILL-1 on IBES found consensus IC_ew **-0.068**, and skill weighting
moved it by **+0.00084**. The report-only attenuation diagnostic (corr -0.46, intercept t 1.09) says
the gain came from shrinking a negative signal, not from finding skilled firms. Weighting an
anti-signal by noise (F1) yields a slightly differently scaled anti-signal. The Explorer now shows
"weighted median-target upside +242%" (VKTX) under a reputation banner, which lends credibility to
exactly the level the registry says not to rank on.

### F7 — LOW (good news). Explorer eligibility is unchanged and nothing is gated or coloured.

Every list in the 17:42Z and 21:43Z receipts matches on (ticker, rank, eligibility, list_score):
roi_v3 65 (58 RANKED / 7 EXCLUDED), analyst_upside_v3 700, thesis_cards_v3 69, and the seven HELD
books. No name the v3 list excluded now appears as eligible. The five `cliff_replaced` rows (HELE,
NOVT, PSNL, SLDP, SOC) stay `EXCLUDED_BY_v3.2_RULE`. The frontend renders `n_eff` in
`text-muted-foreground`, inside a tooltip, unsorted and not green. This is correct.

### F8 — MEDIUM. Weight saturation: the slope was frozen in advance, but it was frozen for a different distribution.

`SKILL_SLOPE = 10`, `SKILL_CLIP = (0.5, 1.5)` were set in `pit_features` on 2026-09-26 (dbb683d0)
before this chunk, so this is not a choice made after looking. However:

- In `pit_features` the slope multiplies an edge shrunk toward **zero**. Here it multiplies an edge
  shrunk toward the firm, and the firm toward its sector, so the effective prior spreads further and
  more mass reaches the clip. "Unchanged map" does not mean an unchanged weight distribution.
- The +/-0.05 saturation is **below one standard error** of a hit rate at a typical cell (n=40 ->
  SE ~0.079). Noise alone is enough to drive a cell to the clip.
- The distribution: **235 cells at 0.50 (12.6%), 231 at 1.50 (12.0%)**, and the remaining 75% are
  continuous (no other value exceeds 27 cells). Overall it is not a three-valued variable. But
  **37.6% of the weights displayed** as "weight-bearing firms" sit at a clip, because the display
  sorts by |w x stance|, so the visible surface looks close to binary.

### F9 — MEDIUM. Snowball: replay and forward rows are labelled, and the base rate is strictly PIT. The base rate is also structurally stale, and `summary()` will mix forward and replay rows.

- Labels: `evidence` is REPLAY for 23,362 rows (22,733 graded, 629 open) and FORWARD for 8 (t0
  10-05/06, open, each with `t0_firm_reputation_weight`; 4 of the 8 sit at a clip). That is good.
- Base rate check on one row each from 2017, 2023 and 2026, recomputed from the ledger using only
  rows with `resolves_after < made_at`: ALLE 2017-07-20 0.228918 (n 4842), MANU 2023-06-27
  0.261637 (n 14588), CELC 2026-03-10 0.29188 (n 21297). **All three match exactly.** It is strictly PIT.
- It is still a bad forecaster. The outcome rate drifts upward with vendor coverage (0.16 in 2015,
  0.38 in 2024, 0.41 in 2026), and the expanding mean lags (2026: p 0.294 vs realised 0.412). Brier
  0.2110 is **worse than the look-ahead constant** (0.2098). The forward rows will be miscalibrated
  by roughly 10pp from the first day. A trailing 24-month window was the obvious frozen choice.
- `summary()` computes `brier_replay` over every graded row. Once the first forward rows resolve
  (2027-01-05/06), forward and replay rows are blended under a key that says "replay". Split it by
  `evidence` now.
- The coverage-start rule has two readings (23,370 vs 24,076 events). Taking the literal reading and
  printing the discrepancy is the right call.

### F10 — MEDIUM. rho = 0.0199 -> "11,241 usable" is arithmetic on the wrong corpus. "Re-lintable" is too generous.

- Re-derived: 26 x 12 x 125 / (1 + 124 x 0.0199) = **11,247** (receipt 11,241; rounding). At the
  upper end of the CI (0.0274) it is 8,868.
- `n_required`: at the measured winsorised sd (**12.12pp**, which matches the 12pp preset) it is
  **7,199**, so the 7,064 input holds.
- **The 26 corpus-years belong to CRSP/IBES. rho was measured on yfinance raises, and the yfinance
  file covers 14.8 years.** At 14.8 years: **6,402** (rho 0.0199) and **5,048** (rho 0.0274), both
  **below** the required 7,199. The leg becomes resolvable only if the IBES t0 count is >= 1,500/yr,
  and the draft itself says that count is "owed before signing".
- rho is biased low as measured. It is a month-level ICC on 21-session windows that overlap the next
  month (acknowledged), it winsorises at 1/99, which shrinks between-month variance, and it ignores
  same-sector clustering within a month, which is where dependence concentrates.
- Even if the leg were resolvable, the economics fail. The declared 0.4pp per 21 sessions is about
  the size of the ~35 bps 21-day toll measured for this universe (section 59), so roughly zero net.
  The surrogate's own mean is **-0.67%** per 21 sessions vs SPY across all raises. The honest wording
  is "RESOLVABLE ONLY IF the IBES event count supports 26 years; economically marginal even then".
  It is a RESEARCH_CLAIM that would still fail the economic bar.

### F11 — LOW. Receipt immutability broke on day one.

The first `reputation_weights_2026-10.json` (279 rows) was deleted by hand so that a better one could
take its date-named slot. `--dry-run` writes the month's receipt if it is absent. Both undercut the
"first run writes, never overwrite" contract the code asserts. A run id in the filename would avoid
this, per the 09-26 rule on date-named receipts.

### F12 — Tests (pasted).

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_analyst_reputation.py \
  backend/tests/test_opportunities_build.py backend/tests/test_opportunities_router.py -q
.......................................                                  [100%]
39 passed, 1 warning in 2.91s
```

This run is 39 tests, not the 211 in the report; the 211 must include other files. Mocks and stand-ins:
- `test_task_keeper_snowball_job_logs_ok_and_refused` injects `job=lambda` / `boom`.
- `test_build_row_carries_reputation_fields` uses `monkeypatch` on the build context, with a fixture rep context and price.
- The reputation tests use a synthetic `_corpus()`.
- The Explorer test reads a pinned fixture (`fixtures/analyst_reputation/explorer_owner_rows.json`), not the live receipt.
- `test_thin_coverage_lowers_n_effective_and_never_drops_the_name` asserts only `1 <= n_eff <= 2`,
  which would pass with equal weights.

No test checks persistence or out-of-sample value, and none checks n_eff <= n_targets.

## (8) The quant's question — does this change tomorrow's buy, and should it?

**It does not**, because eligibility and ranking are untouched (F7). **It should not**: the weights
fail split-half persistence (F1), the quantity they weight is a closed, perverse level (F6), and
n_eff measures how unequal the weights are, not how good the coverage is (F3). The risk is behavioural.
"HC Wainwright w 1.50 (430 graded in sector)" beside "+242%" on VKTX reads as an endorsement, and it
is noise attached to an anti-signal.

## Three things I would have done instead

1. **Persistence first, plumbing second.** Before shipping any weight, run split-half and rolling
   (weights at t from claims resolved by t, scored on claims made after t) rank persistence, with the
   base rate matched by month x direction and claims clustered by ticker-window. Ship the weights only
   if out-of-sample Spearman > 0 with a block-bootstrap CI excluding zero. On today's data it fails,
   so the chunk would have ended as a research note and no UI change.
2. **Show the sum of weights and coverage from one population, and drop `weighted_upside`.** Report
   `n_covering_firms` (revision-file firms in 180d) and `mean_weight` from the same set, never beside
   yfinance's `numberOfAnalystOpinions` as a ratio. Do not publish a reweighted target level at all.
   If anything is reweighted, it should be the *revision flow* (net raises), the one analyst object
   that is not closed as perverse.
3. **Snowball: a trailing-window base rate and an honest power line.** Freeze a 24-month trailing base
   rate (the coverage drift is visible in the ledger itself), split `summary()` by `evidence`, and put
   rho on the receipt beside the yfinance corpus length (14.8 y -> 6,402 < 7,199). The line should
   read "UNPOWERED on yfinance; resolvable only with a printed IBES t0 count", not "looks re-lintable".

— Opus 5.5 adversarial reviewer, 2026-10-07
