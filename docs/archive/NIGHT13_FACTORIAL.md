# NIGHT-13 — FACTORIAL-PM-1: picks × management, his claim as a matrix

**Prereg** Aegis module/TRIALS/PREREG_FACTORIAL_PM_1.md @ c5b81aa (frozen). **Window** 2025-11-07 → 2026-08-10 (188 trading days — NEVER annualized). Computed 2026-08-11T21:07:04. CANON §18/§19 bind.

**The claim under test (Murat, verbatim):** "my portfolio with good timing/management would be a great winner with the stock picks."

## The matrix — window return in pts per $1, EVERY cell with its MDE

| book | M1 EW-hold | M2 vol-target | M3 kill-conditions | M4 mirror rules | as-traded |
|---|---|---|---|---|---|
| B1 — his 13 picks | **+34.6 pts** (baseline; selection MDE 80 pts across books) | **+14.1 pts** (-20.51 vs M1; MDE 100.0 pts) | **REFUSED_NOT_MECHANIZABLE** (0/13 checkable) | **+13.6 pts** (-21.01 vs M1; MDE 150.0 pts) | **DATA_NEEDED** — range [-35.2, +4.9] pts (SYNTHETIC ensemble, label printed, never a point) |
| B2 — his 48 non-picks | **+33.0 pts** (baseline; selection MDE 80 pts across books) | **+16.5 pts** (-16.58 vs M1; MDE 50.0 pts) | **REFUSED_NOT_MECHANIZABLE** (0/48 checkable) | **+41.9 pts** (+8.81 vs M1; MDE 30.0 pts) | — |
| B3 — random-13 × 1000 draws (median [p05, p95]) | +30.7 [+2.2, +71.2] (baseline dist.) | +14.4 [+0.6, +30.9] (eff. vs M1 -16.06 pts; median MDE 75.0 pts) | **REFUSED_NOT_MECHANIZABLE** (0/61 pool names checkable) | +35.9 [+6.8, +71.1] (eff. vs M1 +3.52 pts; median MDE 50.0 pts) | — |
| B4 — funnel candidates | **NOT_EVALUABLE** (all cells) — the funnel ran in Aug-2026; replaying it from Nov-2025 is look-ahead by construction. Recording the refusal is the point (a check that cannot run honestly is not run) Forward cell registered, start 2026-08-11. | | | | |

Refusals are findings. B3 is a distribution and may not be collapsed to a point.

## M3 — the checkability audit (ran FIRST; the refusal is the result)

A condition is checkable only if it can be evaluated point-in-time from the frozen price CSV (there is no fundamentals feed for backdated quarters, no analyst-history feed, no event stream). Conditions that failed, and why:

- **ALMS** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **AMPX** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **AMZN** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **APLT** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **DKNG** — "consensus target falls below entry, or two quarters of negative revisions" → NOT checkable: requires analyst_consensus_history, fundamentals_quarterly — none exists point-in-time in the frozen data (price CSV only)
- **FSLR** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **MRVL** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **MSTR** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **NTLA** — "further clinical holds or serious adverse events" → NOT checkable: requires clinical_regulatory_events — none exists point-in-time in the frozen data (price CSV only)
- **RGTI** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **SLDP** — "a named OEM partnership lapses without replacement, or cash runway falls below 12 months" → NOT checkable: requires corporate_events, fundamentals_quarterly — none exists point-in-time in the frozen data (price CSV only)
- **TTWO** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **TVTX** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **AAPG** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **AARD** — "coverage drops below four analysts or the consensus cracks" → NOT checkable: requires analyst_consensus_history, narrative_qualitative — none exists point-in-time in the frozen data (price CSV only)
- **ABSI** — "cash runway falls below 12 months, or a lead programme is discontinued without a named successor" → NOT checkable: requires clinical_regulatory_events, corporate_events, fundamentals_quarterly — none exists point-in-time in the frozen data (price CSV only)
- **ACVA** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **ADBE** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **AMD** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **AMSC** — "two consecutive quarters of declining grid-segment backlog, or the largest customer concentration exceeds 40% of revenue" → NOT checkable: requires fundamentals_quarterly — none exists point-in-time in the frozen data (price CSV only)
- **ATYR** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **AVGO** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **BE** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **BEAM** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **BHVN** — "a second regulatory setback on the core pipeline" → NOT checkable: requires clinical_regulatory_events — none exists point-in-time in the frozen data (price CSV only)
- **BMRN** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **CHYM** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **COHU** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **CRSP** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **CYTK** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **DAVE** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **DHR** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **ELF** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **GLXY** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **HUBS** — "net revenue retention falls below 100% for two consecutive quarters" → NOT checkable: requires fundamentals_quarterly — none exists point-in-time in the frozen data (price CSV only)
- **IMNM** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **KLAR** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **KYMR** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **KYTX** — "a lead clinical programme misses its primary endpoint, or cash runway falls below 12 months" → NOT checkable: requires clinical_regulatory_events, fundamentals_quarterly — none exists point-in-time in the frozen data (price CSV only)
- **LLY** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **MP** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **MRNA** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **MU** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **NVDA** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **OLMA** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **ORCL** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **OUST** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **PLTR** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **PRCH** — "loss ratios deteriorate again" → NOT checkable: requires fundamentals_quarterly — none exists point-in-time in the frozen data (price CSV only)
- **QBTS** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **QS** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **QUBT** — "narrative rotation; dilution at these levels" → NOT checkable: requires corporate_events, narrative_qualitative — none exists point-in-time in the frozen data (price CSV only)
- **RVMD** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **SLNO** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **SOC** — "consensus breaks below the mark" → NOT checkable: requires analyst_consensus_history — none exists point-in-time in the frozen data (price CSV only)
- **SRRK** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **TGTX** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **TSM** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **TVRD** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **XNCR** — "(none on record)" → NOT checkable: no kill condition on record from any source
- **ZYME** — "(none on record)" → NOT checkable: no kill condition on record from any source

- B3 pool-level: pool-level audit: 0/61 names checkable -> the maximum checkable fraction any 13-name draw can reach is 0/13; every one of the 1,000 draws is below 50% and REFUSED

## H1 — his claim, direction (**DIRECTION_REJECTED**)

Comparator: REGISTERED_FALLBACK_B1xM1. *** SUBSTITUTION, PROMINENT: the as-traded column is DATA_NEEDED — H1 is evaluated against the registered fallback comparator B1×M1 (prereg's paired design). Re-run with --finalize if/when the ensemble's Q4 total_return is re-labelled from DATA_NEEDED (minimal ask: his broker CSV). ***

- **B1×M2**: diff_vs_fallback_M1_pts=-20.507, mde_pts=100.0, verdict=DIRECTION_REJECTED
- **B1×M4**: diff_vs_fallback_M1_pts=-21.015, mde_pts=150.0, verdict=DIRECTION_REJECTED

Caveat (frozen rule row 3, verbatim obligation): this window is ONE bull path, and both paired differences sit far below their measured MDEs — DIRECTION_REJECTED is a report of the SIGN on this window, not a detected negative effect (§19: below the MDE is a design statement, never a kill).

For the record: both managed cells sit above the ensemble's SYNTHETIC upper bound, but that bound is DATA_NEEDED, accrues ZERO, and cannot resolve H1 — recorded so nobody re-derives it as a finding; the registered fallback comparator governs (B1×M2 1.1414, B1×M4 1.1363, synthetic upper bound 1.0489).

## H2 — interaction (management effect, B1 vs B3 distribution)

- **M2−M1**: DoD -2.19 pts, SE 18.67 (z=-0.12), MDE 75.0 pts → NOT_DETECTABLE — as registered (§19: below the measured MDE is a design statement, never a kill)
- **M4−M1**: DoD -25.06 pts, SE 20.64 (z=-1.21), MDE: none on grid (§19: design-limits statement) → NOT_DETECTABLE — as registered (§19: below the measured MDE is a design statement, never a kill)

## H3 — the exposure story, war sub-window (descriptive, n=1)

- 2026-06-04 -> 2026-07-29: B1×M1 maxDD -17.98%, B1×M2 maxDD -8.48%, reduction +9.49 pp vs the registered bar of >= 5pp reduction → **MET (descriptive receipt, n=1 — no inference)**

## Decision rule (prereg §3, verbatim)

| outcome | verdict |
|---|---|
| H1 holds net of costs with the paired difference >= its own measured MDE | CONFIRMED_IN_DIRECTION — the product pitch ("bring your ideas, the engine manages them") gains its first licensed receipt; still NO alpha claim, NO skill claim |
| H1 sign positive but below MDE | UNRESOLVED |
| H1 sign negative | DIRECTION_REJECTED on this window — reported, with the window's one-bull-path caveat |
| any cell's inputs contaminated (per CONVICTION-REPLAY-1 defect class) | cell VOID, investigated before any number is reported |

## M4 disclosure

- the frozen gate (min_observations=252, paper_portfolios.yaml optimizer_params) can never pass on the 197-bar frozen panel; every rebalance ran the lane's frozen loud fallback (equal weight over still-trading names). This cell is therefore 'mirror rules under their fallback', labelled as such — NOT an HRP result.
- B1 rebalances: 10, total cost 0.08 pts. B2 rebalances: 9.
- Sector cap: NOT applied — no frozen PIT sector map; disclosed above

## What this may not do

- No annualization of a 9-month window into a headline.
- No cell promotes a strategy, seeds a lane, or arms anything.
- B3's distribution may not be collapsed to its mean alone (p05-p95 printed).
- The matrix may not be summarized without each cell's MDE beside it (§19).
- This does not and cannot grade Murat's skill (24-month rule; one window).
- M4 is 'mirror rules under their frozen equal-weight fallback' — the HRP gate (min 252 obs) cannot pass on the 197-bar frozen panel; nothing here is an HRP result.
- The as-traded comparator is an ensemble RANGE, never a point; if it is pending, H1 is evaluated against the registered fallback (B1×M1) and says so.
- Synthetic names (APLT, SLNO) enter period returns via entry+payout on a disclosed step path; within-window drawdown timing for those names is an assumption, and they are excluded from every daily-path statistic.

*Receipt: docs/conviction_replay/factorial_pm_1.json · runtime 65.4s*
