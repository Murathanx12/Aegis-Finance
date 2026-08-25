# Handoff — 2026-08-25, after the cross-section turn

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs market | **not recomputed this session** — every replay number on record is still at `k=10` and pre-rename |
| best forward paper strategy | unchanged. **No new forward book launched.** |
| independent selector count | **3 data sources joined** (price · accounting · **analyst, new**). Three selectors clear the cross-section check on 32 years. **Zero trading paper.** |
| farm candidates tested / promoted | **23 registered signals** (19 real + 4 explicit baselines) × 2 windows / **0 promoted** |
| new actionable finding | **YES ×3** — see §2 |
| external execution drag | not measured |
| LLM spend | **$0** — no LLM call made this session |
| **RESULT IMPROVEMENT** | **NONE.** Demonstrated edge is still 0%. |

The honest summary: this session did not launch a paper challenger either. What
it did do is remove the reason the previous nineteen candidates were
uninterpretable, and join the data source that makes a third selector possible.
Whether that counts as progress is Murat's call, and the scoreboard says
NONE so the question is at least askable.

---

## 1. What shipped

**`portfolio_farm/diagnostics.py` + `scripts/portfolio_farm_diagnose.py`** —
signal diagnostics before portfolio diagnostics. Rank IC over non-overlapping
dates, quantile curve with a monotonicity score, top-minus-bottom, turnover, and
a holdings census whose age/size percentiles are measured **against the eligible
set on each date**.

**Explicit baselines.** `equal` → `oldest_listing` (scored `-permno`) +
`newest_listing` (opposite-tail control). `Policy(signal="equal")` now REFUSES
and names its replacement.

**`portfolio_farm/revisions.py`** — the third data source. IBES consensus, both
eras, 5.2M rows, `permno` already joined. `rev_breadth` / `rev_magnitude` /
`rev_dispersion` + the `sell_side_state` composite, components registered
beside it.

**`characteristics.join_pit_series`** — the PIT join extracted so both non-price
sources share ONE `side="left"` line.

**`services/job_receipts.py`** — the generic scheduled-job receipt wrapper,
applied to 11 jobs.

**`scripts/wrds_repull_finratio_early.py`** — keyed on COLUMNS, not existence.

## 2. The three findings

**(a) I HYPOTHESISED AN AGE CONFOUND AT `k=100`. THE TEST REFUTED IT.**

`profit_roe` age% by book size: **51.1 at k=20, 49.5 at k=100**, against
`oldest_listing`'s 1.9 and 9.9. It does not become an age book as `k` rises —
the prediction I wrote down before running it said that outcome kills the
explanation, and it did. **Withdrawn.**

The 126 years is **power arithmetic on a small excess**, not a confound:
+1.53%/yr over the age book against a 6.11% paired tracking error, and
`(2.8 × 6.11 / 1.53)² = 125`.

**The real tension, which is sharper:** `profit_roe` has the strongest
cross-sectional evidence in the project's history (`ic_t 4.18`, monotone 0.90,
32 years) and a **weak book** (+1.53%/yr over a named alternative). Those are
compatible, and every previous farm result collapsed them into one number.
**The open question is CONSTRUCTION — a long-only top-k slice captures very
little of a signal that demonstrably orders the whole cross section.**

**(b) `value_bm` fails monotonically in the WRONG direction** (−0.90 over 32
years). Not weak — consistent, and pointing the other way. Extreme top-k value
in a mega-liquid universe selects distress. **The reversed signal is the one to
test.**

**(c) `liquid` is dead outside its decade** (`ic_t` 0.09, mono −0.60 on 32y,
against the best t on the 2013–2024 grid), and **`size_large` carries `ic_t`
2.35 on 3.6 distinct names per slot** — a static mega-cap list that only the
census can see.

Full tables: `docs/FINDING_2026-08-25_ASK_THE_CROSS_SECTION_FIRST.md`.

## 3. One defect I introduced and caught

`signals.zscore` returned **zeros** for a row with nothing to standardise, so on
any date with no IBES coverage `sell_side_state` tied every name and silently
became `oldest_listing`. That is the `equal` defect again, one level down,
introduced while fixing the first one. Now returns NaN; pinned by test.

Also caught: my own census measured age against the **panel** rather than the
eligible set, which reported a book of ancient mega-caps as "average age". Found
only because `oldest_listing` failed to read ~0 — **the baselines are the
instrument's own calibration and should be read first, every time.**

## 4. TWO CLOCK-GATED CHECKS STILL PENDING

Both were correct-but-not-yet-fired at 03:13 ET Tue, ~12–13 hours ahead of
their firing. They will have fired by the next session.

**One thing checked before pushing, because it would have been easy to ruin:**
`_last_mtm_timestamp` is a module global reset to `None` on restart, and the
suspect skip path is guarded by it. A deploy shortly BEFORE 16:30 ET would make
the first post-restart run mark unconditionally and produce a clean receipt —
masking the very defect it was built to catch. At 13 hours out, ~13 hourly runs
re-establish the state first, so this push is safe. **A deploy inside the hour
before 16:30 ET is not** — hold it if that is where the clock sits.

- **15:30 ET** — `options_pit days_held` must climb past **1**. It never has in
  this system's history. If it is still 1 after a capture, the `/data` fix did
  not take.
- **16:30 ET** — `GET /api/optimus/job_receipts` → `pi_hourly_mtm`. If it reads
  `skipped / cached market_data_timestamp ... <= last mark ...`, the NAV-gap
  suspect is **confirmed**, and the fix is to gate on whether a row already
  exists for `expected_nav_date`. **Must only ever mark today — never backfill a
  past date with today's prices.** Run `lane-integrity-check` for that change.

**`_hourly_mtm` was deliberately left on its bespoke receipt** and excluded from
the generic wrapper, because refactoring it before that firing would forfeit the
diagnosis to remove a duplication. Migrate it *after* the receipt is read;
`test_hourly_mtm_keeps_its_bespoke_receipt_for_now` is the reminder.

## 5. What is left, in order

0. **DONE — and it refuted my hypothesis.** `profit_roe` age% is 49.5 at
   `k=100`, not falling toward the age book. See finding (a). The follow-on
   question it opens is item 1b.

   **Also re-run the published tables**: `diagnostics` was corrected late in the
   session to build its trailing-dollar-volume series with the SAME `min_obs=5`
   as `replay` (it had used 10). The tables in the finding doc were computed at
   `min_obs=10`, i.e. on a slightly stricter eligible set than the book trades.
   The effect is probably small — it only touches names with 5-9 valid volume
   days in a trailing 21 — but *probably* is not *measured*, and the receipts
   should be regenerated before any number in them is quoted onward.

1. **Launch a forward book.** This is now the only thing that moves the
   scoreboard, and two sessions have ended without it. `rev_dispersion` (ic_t
   3.14, 41% turnover, age/size neutral, own data source) and `profit_roe` at
   `k=20` are the two candidates that clear the cross section on 32 years.
   Under `PRODUCT_EXPERIMENT` neither needs a significance gate — it needs a
   frozen strategy contract before the first decision. Promotion is
   **attended**: Murat flips the flags (`seed-a-lane`).
1b. **THE QUESTION FINDING (a) OPENS, and it is now the most interesting one
   on the board: why does a strong signal make a weak book?** `profit_roe`
   orders the cross section at `ic_t 4.18` over 32 years and its top-k long-only
   book clears a named alternative by only +1.53%/yr. Things to try, cheapest
   first: wider `k` (the census says turnover is only 12.5% at k=100, so cost
   is not the culprit); quantile-spread weighting instead of top-k; and
   neutralising the book's residual size tilt (54.3 at k=100). **This is a
   CONSTRUCTION search, not a signal search** — the signal is the best-evidenced
   thing the project has.

2. **Measure `sell_side_state` and `rev_breadth` NET OF COSTS.** ~95%/month
   turnover; their top-minus-bottom figures are gross and could be eaten
   entirely. This is the open question about them, not their IC.
3. **`QUALITY_RESIDUAL_v1`.** `scripts/wrds_repull_finratio_early.py` was
   running at handoff — check it landed (`--dry-run` reports missing columns).
   It widens the early era from 5 columns to ~100, including `gsector`/`ffi48`
   industry codes and `mktcap`, which is what makes age/size/industry
   neutralisation testable before 2013 at all.
4. **Re-run the holding-period and breadth grids at `k=20`** with the renamed
   baselines. Every replay number on record is at `k=10` and pre-rename.
5. **Reverse `value_bm` and diagnose it.** −0.90 monotonicity is a result.
6. Then `RESIDUAL_MOMENTUM_CRASH_GUARD_v1`, `ACTIVIST_13D_v1`,
   `ALPHA_STACK_EQUAL_RISK_v1` (fixed equal-risk stack BEFORE any learned
   router).

## 6. Standing cautions that bit again

- **The 12-year window has now reversed a farm verdict FOUR times** — holding
  period, breadth, the cross section, and `rev_dispersion` (mono 0.10 → 0.60).
  Do not close anything on 2013–2024.
- **A baseline must state what it selects.** Never let a tie-break decide one.
- **A constant score is a hidden delegation to the sort**, not a neutral book.
