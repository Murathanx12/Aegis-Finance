# TRIAL-CMP-INSIDER-IC — CMP-classified opportunistic insider buying (forward IC)

> **Pre-registered 2026-07-21, BEFORE any forward data is collected.** This is the
> successor TRIAL-INSIDER-IC's own doc pre-announced as a "future upgrade": true
> routine-vs-opportunistic classification (Cohen-Malloy-Pomorski 2012) using
> per-insider multi-year trade history. That history now exists: the brain module
> (`C:\Users\mrthn\Aegis module`, github.com/Murathanx12/investing-test-module)
> built the full SEC bulk insider panel 2006→2026Q1 and validated the classifier
> in TRIAL-BRAIN-003 — the research arc's first kill-condition survivor.
> Promotion follows INTEGRATION.md: brain exports a reviewed bundle; a human
> commits it here; the forward clocks earn (or refuse) conviction.

## Provenance — the backtest prior (set in the brain module, never re-run here)

BRAIN-003 (pre-registered, deflated, leak-checked; CRSP 2006-2024, one run):

- **Large/mid caps:** +17 bps/mo vs cap-segment EW (net t=1.40); **FF5+UMD alpha
  +102 bps/mo (t=1.89)**; post-2015 t=1.30 (not decayed). Net Sharpe 0.52.
- **Microcap: null** (net t=-0.20) — the edge does NOT live in microcaps.
- Noise-control gross |t| < 3 (no pipeline leak); routine placebo negative (no confound).
- **Deploy gate NOT met** (DSR 0.26 vs cumulative n=24, PBO 0.41) — as expected for
  this effect size on 199 months. **Weak positive prior, not a discovery.**

The backtest sets the prior; THIS forward trial is where conviction is earned.

## Hypothesis

Cross-sectionally, stocks whose trailing-12-month open-market purchases include
more DISTINCT **opportunistic** insiders (CMP rule) earn higher forward returns
than stocks with fewer/none, in large/mid caps. Routine buyers (same calendar
month in each of the 3 prior years) carry no information and are dropped;
insiders without a 3-year history are unclassifiable and dropped (never
defaulted to opportunistic).

## Signal definition (frozen)

`backend/services/cmp_insider.py::compute_cmp_insider_score`:

    score = # distinct opportunistic buyer CIKs, trailing 365 days

- Open-market purchases only (Form 4 code `P`, acquired); PIT on **filing date**.
- Classification is trans-date-keyed, strictly-prior years only (point-in-time
  by construction) — byte-for-byte the rule BRAIN-003 validated
  (`aegis_brain.events.insider.classify_routine_opportunistic`).
- **Coverage = panel ∪ live:** the brain's routine-history artifact
  (`backend/data/cmp_routine_history.json.gz`, panel_end 2026-03-31) supplies
  per-insider history + the panel's own classified buys near panel end; the live
  SEC Form-4 feed (200d lookback, ≤60 filings/name, paced via `_sec_get`) covers
  only the post-panel gap. No double counting (live buys ≤ panel_end excluded).
- **Anti-false-zero guard:** if the artifact's panel_end falls >210 days behind,
  every score is flagged `degraded` in its payload and logged — a stale artifact
  can never silently zero the clock (NEGATIVE_RESULTS §5 lesson).

## Relationship to TRIAL-INSIDER-IC (T9 — runs unchanged, beside this)

| | T9 `insider_opp:` | This trial `insider_cmp:` |
|---|---|---|
| Buyers counted | ALL open-market buyers | opportunistic only (routine + unclassifiable dropped) |
| History used | none (P-code proxy) | 2006→2026Q1 per-insider bulk history |
| Window | 180d | 365d |

Both clocks accrue on the same universe and cadence; if CMP classification adds
information, `insider_cmp:` forward IC should exceed `insider_opp:` forward IC.
That comparison is reported, never deciding.

## Estimator (frozen, pre-registered)

Forward **rank IC** = Spearman correlation between the cross-sectional score at
snapshot t and forward total return over the next **21 / 63 / 126 trading days**,
with block-bootstrap CI and cross-section size N reported each period. Sparse-
signal handling identical to T9: periods below the minimum non-zero count are
recorded, not silently dropped. Primary metric: **126d rank IC with 90% CI**
(the backtest edge is a 12-month-hold effect; the longest horizon is primary).

## Decision rule

- **Descriptive until proven.** Never arms a lane, never sizes a position, never
  enters `paper_nav`. No "signal"/"predicts"/buy-sell framing on any surface.
- **Earliest decision date: 2027-07-21** (≥12 months of accrual).
- **Adopt-consideration** only if 126d forward rank IC > 0 with 90% CI excluding
  0 AND the 21/63d ICs are not significantly negative — then through
  `evaluate_candidate` (DSR/effective-N vs cumulative count) before any status
  change, per the standard gate.
- **Kill:** 126d IC ≤ 0 at the decision date → published negative
  (NEGATIVE_RESULTS), clock may keep running for the record but the signal is
  not promotable.
- **Contamination clause:** artifact defect (wrong history, double counting) or
  ≥25% of snapshots degraded/stale → affected snapshots excluded, inception
  moves forward; a rebuilt artifact restarts coverage, never backfills.
- **Crash override:** SPY −20% defers any decision to ≥6mo past trough.

## Frozen parameters

365d score window · 200d live fetch / 60 filings cap · 210d staleness threshold ·
book universe · weekly throttle (5d) · CMP rule as stated. Changing any of these
mid-trial invalidates it (abandon + successor, per the amendment rule).

## What this rule may NOT do

- May not claim the BRAIN-003 backtest as alpha evidence (it is a prior; T7
  stands: only forward validation certifies selection signals).
- May not substitute horizons/metrics, re-run the backtest under this ID, or
  widen the universe mid-trial (universe changes = successor trial).
- May not arm anything, ever, under this registration.

## Maintenance (documented dependency, not a tuning knob)

Quarterly, when SEC publishes a new bulk quarter: brain module re-runs
`scripts/download_insider.py` (extended range) → `build_insider_panel` →
`export_routine_history`; a human reviews and commits the refreshed artifact
here. The artifact refresh updates COVERAGE only — the rule itself is frozen.

## Annotation 2026-07-27 — the 2023 Rule 10b5-1 structural break (documented hazard, no spec change)

The 2022 10b5-1 amendment (effective early 2023) destroyed the predictive
content of 10b5-1 insider SALES (short-window plan trading collapsed 31.1% →
1.7%; post-amendment sales are followed by flat-to-positive returns) and
closed the gift-timing anomaly. Our signal is opportunistic open-market BUYS
(code P), which the amendment does not address — the trial is NOT invalidated
and nothing in the frozen rule changes. Banked hazard: the panel straddles
the break, and pooling pre/post-2023 insider data is now known-unsafe in
general. **Standing audit item for the quarterly artifact refresh (~Oct
2026): check whether the CMP routine/opportunistic split and the buy base
rate shift across 2023, and report the IC with a pre/post-2023 split as a
REPORTED-never-deciding cut.** (Source: 2026-07-27 sweep §5.3, adjudicated
AI_PANEL_2026-07-27F #8.)

## Status

- ✅ Artifact built + committed (panel_end 2026-03-31; 25,020 insiders; 3,648
  recent opportunistic buys; 0.22 MB).
- ✅ Collector `cmp_insider_collector.py` wired into `scheduler._daily_check`,
  weekly-throttled, wrapped (a SEC outage can't break lane processing).
- ⬜ Forward accrual — clock starts on the next deploy's daily check.

---

## Declared adverse prior (added 2026-07-30, BEFORE the 2027-07-21 decision date)

Banked in round 13 (`docs/research/AI_PANEL_2026-07-30.md`). Recorded now, while
it is free: after the decision date it would be rationalisation.

The registration's prior cites BRAIN-003's FF5+UMD alpha of **+102 bps/mo
(t 1.89)**, itself anchored on Cohen-Malloy-Pomorski (*Decoding Inside
Information*, JF 2012), whose headline was **82 bps/mo** value-weighted for
opportunistic insiders. The post-2010 literature reports that this has decayed
by roughly **60-70%**, to on the order of **30-40 bps/mo**, attributed to the
growth of algorithmic trading and 10b5-1 usage compressing the public-
information window — both of which post-date the CMP sample.

**Consequence for how this trial should be read at decision time:** a forward
126d rank IC that is *positive but small* is the outcome the current literature
predicts, not a pleasant surprise, and should not be narrated as a discovery.
The pre-registered decision rule is unchanged (it was never magnitude-based —
it asks whether the 90% CI excludes zero), and this note does **not** alter any
bar. It exists so that the size of whatever we find is judged against 30-40
bps/mo rather than against 82 or 102.

Compounding note already on file: the 2023 10b5-1 amendments destroyed the
*sales*-side signal. Our signal is buys-side and unaffected in principle, but
pre/post-2023 pooling remains flagged for the October refresh audit.
