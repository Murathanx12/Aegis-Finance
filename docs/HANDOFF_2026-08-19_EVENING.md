# HANDOFF — 2026-08-19 evening (pre-Night-3)

## NEW INFORMATION ACQUIRED (in order of importance)

1. **CONVEXITY-PRESERVATION-1 RESOLVED — the program's first Holm-surviving
   positive result.** On 2019–2026 large caps, mechanically de-risking a
   +40% winner destroyed 60-day terminal wealth: trim_25 −1.3%, trim_50
   −2.6%, exit_full −5.2% per dollar (each ≥ its MDE, FWER 0.05, 22
   effective 84-day blocks). The DECIDING daily-close 20% trailing exit:
   −0.55% vs MDE 0.71% → NOT_ESTABLISHED; noninferiority was prospectively
   NOT_ANSWERABLE_AT_N. Scope: ADAPTIVE_HISTORICAL_VALIDATION (§61), not
   policy, not a skill claim. Receipt `trial_2026-08-19T070720Z.json`.
2. **The GPT audit's power objection was CORRECT and material:** the
   draft's "7×-powered" claim came from the wrong arm (trim_25) under
   month blocks. Exact-primary, mean-masked audit under 60-trading-day
   overlap blocks: MDE 0.0071 > 0.005 margin. Amendment 1 (5 repairs)
   landed BEFORE any aggregate read — commit `47762cd` proves ordering;
   the CRSP replication protocol was frozen pre-read in the same commit
   (`PREREG_CONVEXITY_CRSP_REPLICATION_1.md`).
3. **First registered run refused itself with NaN** — 1 of 6,198 primary
   pairs had a missing leg (ENPH 2026-05-14). Pair-integrity rule now:
   drop WITH count on receipt, refuse if >1%. Pinned in
   `test_convexity_amendment1.py`.
4. **WRDS entitlement is far richer than the reference memory assumed.**
   Probe receipt `wrds/entitlement_map_2026-08-19.json` (the ONLY citable
   authority; catalogue ≠ entitlement): SELECT-OK on CRSP dsf, comp.fundq,
   IBES, OptionMetrics, taqmsec (incl. `wrds_iid_YYYY` intraday
   indicators), **wrdsapps_finratio (70+ monthly ratios w/ public_date)**,
   **contrib_global_factor (JKP ~150 published per-stock signals)**, all
   CRSP linking tables, bondret, FISD, TRACE, BoardEx, Audit Analytics,
   Thomson/WRDS 13F, Eventus, patents, subsidiaries, world indices.
   DENIED: wrdssec (filings text), CIQ Key Developments, Trucost,
   wrds_insiders.
5. **Training-data substrate pulls are running** (`wrds_training_pull.py`,
   resumable, PIT column named in every meta; universe = 4,796
   ever-eligible PERMNOs, 2013–2024): links ✓, finratio/ibes/fundq/
   bondret/global_factor/dsf in flight as of 15:52 HKT.
6. **DECISION_MDE_80 solver built** (`verdict_battery.decision_mde_80`):
   bisects the true effect giving 80% COMPLEX_WINS through the FULL
   four-arm Holm + economic-bar judge. Receipt
   `verdict_battery_decision_mde_2026-08-19.json` when the background run
   lands. The z-based number is renamed conceptually: STATISTICAL_MDE_80.
   Every future prereg quotes BOTH.

## Standing orders adjudicated today

- GPT audit on convexity: 4/4 confirmed → Amendment 1. One-sided
  noninferiority adopted (helpful stop passes; matches runner).
  Execution semantics frozen (daily-CLOSE trailing rule, alias
  `close_trail_20`); verdict sentences must say "trailing exits evaluated
  on daily closes".
- Signature hygiene: NET prereg status line + Brier declaration blanks
  reconciled to their signed headers. No protocol text touched.
- Murat's blanket (recorded): "I approve anything we do, any new idea and
  approach, don't ask" + WRDS "pull everything and use as training data".

## NEXT MACHINE JOBS (priority order)

1. **Finish/verify the running pulls**; then `optionm` surface (vsurfd is
   PER-YEAR tables; pull 30d ±25/50 delta calls+puts via opcrsphist link),
   `taqmsec.wrds_iid_*` (needs symbol↔permno via wrdsapps_link_crsp_taqm),
   and WRDS/Thomson 13F (tr_13f.s34 by mgrno, quarterly).
2. **CONVEXITY-CRSP-REPLICATION-1**: materialize episodes on the PIT
   panel per the frozen protocol; masked power audit; present for
   signature. This answers the NOT_ESTABLISHED trailing-stop cell AND the
   +75/+100 thresholds large caps under-sample.
3. **UNIVERSE-SURVIVAL-STRESS-1**: rebuild the 7 NET features + targets on
   the CRSP PIT panel (dsf now local), re-run tournament heads with NO
   architecture changes; does ridge>NN ordering survive?
4. **NN feature ladder v2**: the tournament said information > architecture.
   New rungs now pullable: finratio (70+ ratios), JKP chars, IBES
   revisions (numup/numdown/stdev), options surface, iid liquidity.
   Each rung = registered sensitivity, not a new architecture hunt.
5. **EXPECTATION-BACKFILL** resume at FMP quota reset (UTC midnight);
   keep batches small — quota shared with prod.
6. Order 22 (world sensor network / WorldObservation contract /
   WORLDMONITOR audit) — the next arc after the WRDS substrate lands;
   nothing in it blocks tonight.

## Night 3 (TONIGHT, attended by Murat, 17:00 HKT)

- `--dry-run` first; tonight's scheduled firing is the FIRST test of the
  `< NUL` stdin fix; the 3/3 arming clock starts from a clean receipt.
- All local pulls are network-bound and resumable — if anything is still
  running at 16:55, kill it; `wrds_training_pull` skips finished datasets.
- NAV stamp fix (P-day-2026-08-19a) is APPROVED conceptually (GPT + Murat)
  but ships AFTER Night 3, never right before: add `price_bar_date`, no
  history rewrite, lane-integrity-check both sides, attended deploy.

## Open attended items

- Sign CONVEXITY-CRSP-REPLICATION-1 when its power audit is presented.
- 08-21 (Friday): first 396 IIF resolutions — mechanics only.
- Optimus brain_query recursive-filename fix lives in the optimus repo.
