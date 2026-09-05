# docs/DATA_MANIFEST.md — the big local artefacts, and how to get them back

**Created 2026-09-03.** House rule: **receipts are committed, raw substrate is
not.** A derived JSON receipt with a headline number in it belongs in git. A
multi-gigabyte panel pulled from a vendor does not — it bloats the clone, it
churns `git status` mid-pull (which on 2026-08-20 flipped a launcher receipt's
`git_dirty` flag), and it is reproducible from its own script.

The failure mode this file exists to prevent is the other one: **an untracked
file that nobody can find again.** *Absence of a local object is not evidence of
absence* — but absence of a **record** of the object is how a session concludes
the data was never pulled and pulls it a second time. Every artefact below is
ignored on purpose, and named here so it stays findable.

**If you add an ignore rule for a data file, add its row here in the same
commit.** An ignore rule without a manifest row is the bug.

## Ignored by explicit rule

| Path | Size | Produced by | What it is | Rebuild |
|---|---:|---|---|---|
| `backend/data/optimus/wrds/crsp_monthly_panel_2013_2024.json` | ~31.9 MB | WRDS pull scripts (`scripts/wrds_*`) | CRSP monthly panel, 2013–2024. Substrate for the tracker/IBES backtests. | Re-pull from WRDS `crsp.msf` + `crsp.msenames` |
| `backend/data/optimus/wrds/tr13f_quarterly.json` | ~25.3 MB | WRDS pull scripts | Thomson Reuters 13F quarterly holdings. Substrate for the holder-provenance work (H2/H3). | Re-pull from WRDS `tr_13f.s34` |

| `backend/data/optimus/graph/companyworld_work/` | ~31 MB | `scripts/companyworld_extract.py` (2026-09-06) | Per-document extraction records the run resumes from, plus cached 10-K bodies for 1,486 filings. | Re-run the extractor; re-buying the DeepSeek calls costs about **$2.12** |
| `backend/data/optimus/graph/companyworld_inputs/` | ~57 MB | copied at run time | Two CRSP/Compustat link registries that ALREADY live under `backend/data/`. A second copy of a source is a second source. | Delete; the originals are the source |

The derived, committed evidence for both is in
`backend/data/optimus/tracker_backtest/` — `holder_h2_h3.json`,
`holder_fingerprint_summary.json`, `ibes_status_rules_2013_2024.json`,
`topn_concentration.json`. **Quote the receipt, not the panel.**

The companyworld PRODUCT is **committed**: `backend/data/optimus/graph/companyworld_v1.parquet` (18 KB, 2,020 edges, 945
permnos, 1999-2011, `graph_layer=FACT`, 94.65% quote-verified), with
`continuation_2026-09-06/W4b_companyworld_extract_run01.json`,
`W4b_companyworld_rerun_run01.json`, `W4b_cost_reconciliation_run01.json` and
`S5_companyworld_integrity_check_run01.json` beside it. **Quote the receipt,
not the working directory.**

## Ignored by the blanket `*.parquet` rule (.gitignore line 63)

These are the LEARNER v1 tables. They are large, they are regenerable, and their
schema + every headline number is committed.

| Path | Size | Produced by | Rebuild |
|---|---:|---|---|
| `backend/data/optimus/learner/train_table.parquet` | ~200 MB | `python -m scripts.learner_run` | rerun the script |
| `backend/data/optimus/learner/beta_panel.parquet` | ~104 MB | `python -m scripts.band_horizon_run --build-betas` | rerun the script (~18 s from the CRSP daily files) |
| `backend/data/optimus/learner/beta_panel.parquet` | ~104 MB | `python -m scripts.band_horizon_run` | rerun the script |
| `backend/data/optimus/learner/oos_predictions_1m.parquet` | ~21.9 MB | `python -m scripts.learner_run` | rerun the script |
| `backend/data/optimus/learner/states/company_states.parquet` | ~35.9 MB | `python -m scripts.learner_states_run` | rerun the script (~11 min) |
| `backend/data/optimus/learner/states/market_states.parquet` | ~7 KB | `python -m scripts.learner_states_run` | rerun the script |
| `backend/data/optimus/actor_corpus/ibes_graded.parquet` (row-level analyst target grades) | varies | `scripts/tracker_ibes_backtest.py` | rerun the script |

Many more `*.parquet` panels live under `backend/data/optimus/` (aegis_panel,
crsp_pit, convexity, datasets, event_response, …). They are all ignored by the
same blanket rule and all regenerable by their own scripts; list them with
`find backend/data/optimus -name '*.parquet'`.

Committed counterparts, which are what a session should read:

- `backend/data/optimus/learner/train_table_schema.json` — the schema, the
  feature list, the missingness table, the schema hash.
- `backend/data/optimus/tracker_backtest/unsupervised_states_20260903.json` — the
  STATES v1 receipt: state definitions, sizes, transitions, per-state conditional
  tables, the within-band control and the shuffled null. Written by
  `scripts/learner_states_run.py`; read it before quoting anything from
  `docs/STATES_2026-09-03_UNSUPERVISED_V1.md`.
- `backend/data/optimus/tracker_backtest/learner_v1.json` — the full
  pre-registration header, every arm's scoreboard, the verdicts.
- `backend/data/optimus/learner/shadow_book_2026-09-02.json` — the sealed
  shadow book.

Row-level parquet for `analyst_target_grades.json` and `time_machine_arena.json`
is **local-only** — read each receipt's `read_me_first` before quoting a number
that only exists in the rows.

## The WRDS substrate — every parquet family under `backend/data/optimus/wrds/`

**Added 2026-09-04 (roadmap B1 task 6).** Until this section existed, the file
above named exactly **two** objects under the WRDS tree — both JSON, 54.5 MiB
between them — while the tree held **1,378 parquet files / 58.52 GiB / 1.93
billion rows**. The manifest's own rule ("an ignore rule without a manifest row
is the bug") was violated by 99.9% of the bytes it was supposed to cover: the
blanket `*.parquet` rule on `.gitignore` line 63 ignores all of it, and one
sentence of prose (*"list them with `find`"*) is not a record.

**Format note.** This table extends the `| Path | Size | Produced by |` shape
above rather than replacing it: `Path` becomes a **family glob** (one row per
family, not per file — 84 rows for 1,378 files), and four columns are added so
that a session can answer *"do we already have this, over what window, pulled
when?"* without touching 59 GB. `*` matches within one path segment only.

**Read the numbers as follows.** *Rows* is `ParquetFile.metadata.num_rows`
summed over the family — footer metadata, no data loaded. *Date range* is the
min/max of the **first date-like column**, taken from row-group statistics; for
a `bulk/<library>__*` family that envelope spans dozens of unrelated tables and
is a coverage hint, not a claim about any one table. `[sentinel]` marks a range
whose endpoint is outside 1900–2030 — WRDS placeholder dates (`1900-01-01`,
`9000-01-01`, `2140-06-20`) that survive into the column statistics. A blank
range means no column matched the date heuristic, not that the table is undated.
*Pulled* is the file mtime (a `.meta.json` sidecar, where one exists, carries the
authoritative `pulled_at`; 198 sidecars exist and they agree with mtime).

| Family (glob) | Files | Size | Rows | Date range | Pulled | Produced by / rebuild |
|---|---:|---:|---:|---|---|---|
| `backend/data/optimus/wrds/bulk/contrib__*.parquet` | 20 (20 tables) | 6.50 GiB | 16,166,223 | 1834-03-29 .. 2025-12-31 [sentinel] | 2026-08-21..2026-08-22 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/wrdsapps__*.parquet` | 19 (19 tables) | 5.99 GiB | 27,428,459 | 1960-01-31 .. 2026-07-19 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/jkp_full/jkp_usa_*.parquet` | 32 | 5.26 GiB | 3,599,311 | 1926-01-30 .. 2012-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/bulk/comp__*.parquet` | 119 (119 tables) | 4.97 GiB | 99,174,831 | 1900-01-01 .. 2026-08-31 | 2026-08-20..2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/comp_na_daily_all__*.parquet` | 104 (104 tables) | 4.91 GiB | 89,875,914 | 1900-01-01 .. 2026-08-31 | 2026-08-20..2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/ibes__*.parquet` | 104 (104 tables) | 3.39 GiB | 239,972,895 | 1976-01-15 .. 2026-05-14 | 2026-08-20 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/tr_ibes__*.parquet` | 104 (104 tables) | 3.39 GiB | 239,972,895 | 1976-01-15 .. 2026-05-14 | 2026-08-20 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/optionm__*.parquet` | 68 (68 tables) | 2.94 GiB | 227,529,431 | 1900-01-01 .. 2031-08-06 [sentinel] | 2026-08-20 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/optionm_all__*.parquet` | 68 (68 tables) | 2.94 GiB | 227,529,431 | 1900-01-01 .. 2031-08-06 [sentinel] | 2026-08-20 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/comph__*.parquet` | 19 (19 tables) | 2.70 GiB | 17,788,293 | 1980-02-29 .. 2026-07-01 | 2026-08-20..2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/crsp__*.parquet` | 94 (94 tables) | 1.91 GiB | 88,242,809 | 1923-05-31 .. 2038-03-10 [sentinel] | 2026-08-20 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/crsp_a_stock__*.parquet` | 40 (40 tables) | 1.36 GiB | 40,683,511 | 1925-12-31 .. 2025-12-31 | 2026-08-20 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/_quarantine_truncated/optionm__*.parquet` | 18 (18 tables) | 1.19 GiB | 144,000,000 | 1998-01-02 .. 2019-12-31 | 2026-08-20 | `scripts/wrds_pull_everything.py` → quarantined by `scripts/wrds_quarantine_truncated.py` |
| `backend/data/optimus/wrds/jkp_global_factor_usa.parquet` | 1 | 1.00 GiB | 558,369 | 2013-01-31 .. 2024-12-31 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/crsp_dsf_*.parquet` | 35 | 926 MiB | 44,969,483 | 1990-01-02 .. 2024-12-31 | 2026-08-19..2026-08-24 | `scripts/wrds_training_pull.py dsf` (1990-2012 re-pulled by `scripts/wrds_repull_dsf_early.py`) |
| `backend/data/optimus/wrds/bulk/boardex__*.parquet` | 22 (22 tables) | 897 MiB | 33,293,316 | 1900-01-01 .. 9000-01-01 [sentinel] | 2026-08-20..2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/holder_transitions/q*.parquet` | 115 | 873 MiB | 30,822,316 | n/a | 2026-09-02 | `scripts/holder_fingerprint.py` |
| `backend/data/optimus/wrds/optionm_surface30d_*.parquet` | 29 | 853 MiB | 71,132,384 | 1996-01-04 .. 2024-12-31 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/stdopd_events/stdopd_events_*.parquet` | 14 | 794 MiB | 21,102,886 | 2006-01-03 .. 2019-12-31 | 2026-08-23 | `scripts/wrds_pull_stdopd_events.py` |
| `backend/data/optimus/wrds/tr13f_s34_*.parquet` | 29 | 739 MiB | 76,896,818 | 1996-03-31 .. 2024-12-31 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/bulk/wrdsapps_finratio_ibes__*.parquet` | 1 | 719 MiB | 2,527,384 | 1968-12-31 .. 2025-10-31 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/wrdsapps_finratio__*.parquet` | 1 | 694 MiB | 2,527,384 | 1968-12-31 .. 2025-10-31 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/optionm_etf_quotes/quotes_*.parquet` | 27 | 486 MiB | 11,859,415 | 1999-03-10 .. 2025-08-29 | 2026-08-27 | `scripts/wrds_pull_etf_option_quotes.py` |
| `backend/data/optimus/wrds/holder_events/q*.parquet` | 115 | 389 MiB | 23,317,112 | n/a | 2026-09-02 | `scripts/holder_h2_h3_test.py` |
| `backend/data/optimus/wrds/superseded/crsp_dsf_*.narrow-5col.parquet` | 23 | 321 MiB | 33,155,010 | 1990-01-02 .. 2012-12-31 | 2026-08-19 | `scripts/wrds_training_pull.py` → superseded by `scripts/wrds_repull_dsf_early.py` |
| `backend/data/optimus/wrds/taq_iid_*.parquet` | 12 | 309 MiB | 8,803,107 | 2013-01-02 .. 2024-12-31 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/bulk/wrdsapps_bondret__*.parquet` | 2 (2 tables) | 308 MiB | 4,520,442 | 2002-07-31 .. 2026-01-31 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/fisd__*.parquet` | 39 (39 tables) | 236 MiB | 23,590,799 | 1800-06-20 .. 2140-06-20 [sentinel] | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/compseg__*.parquet` | 11 (11 tables) | 204 MiB | 13,669,186 | 1976-06-30 .. 2026-06-30 | 2026-08-20..2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/_quarantine_truncated/comp__*.parquet` | 3 (3 tables) | 182 MiB | 24,000,000 | 1950-06-30 .. 2026-07-31 | 2026-08-20 | `scripts/wrds_pull_everything.py` → quarantined by `scripts/wrds_quarantine_truncated.py` |
| `backend/data/optimus/wrds/finratio_monthly.parquet` | 1 | 154 MiB | 534,110 | 2011-12-31 .. 2024-10-31 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_jpn_*.parquet` | 1 | 152 MiB | 547,221 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_kor_*.parquet` | 1 | 94 MiB | 309,425 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/bulk/audit__*.parquet` | 2 (2 tables) | 94 MiB | 483,136 | 1994-01-05 .. 2026-06-05 | 2026-08-20..2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_twn_*.parquet` | 1 | 84 MiB | 279,629 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/bulk/_quarantine_truncated/crsp__*.parquet` | 2 (2 tables) | 83 MiB | 16,000,000 | 1960-03-31 .. 2026-06-30 | 2026-08-20 | `scripts/wrds_pull_everything.py` → quarantined by `scripts/wrds_quarantine_truncated.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_aus_*.parquet` | 1 | 62 MiB | 244,276 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_gbr_*.parquet` | 1 | 56 MiB | 218,718 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/bondret_monthly.parquet` | 1 | 53 MiB | 2,151,468 | 2013-01-31 .. 2024-12-31 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_can_*.parquet` | 1 | 51 MiB | 342,695 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/analyst_target_grades.parquet` | 1 | 41 MiB | 1,333,683 | n/a | 2026-09-01 | `scripts/analyst_target_grades.py` |
| `backend/data/optimus/wrds/holder_fingerprints.parquet` | 1 | 35 MiB | 372,831 | n/a | 2026-09-02 | `scripts/holder_fingerprint.py` |
| `backend/data/optimus/wrds/bulk/tfn__*.parquet` | 3 (3 tables) | 34 MiB | 2,513,784 | 1978-12-31 .. 2025-12-31 | 2026-08-20 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/tr_13f__*.parquet` | 3 (3 tables) | 34 MiB | 2,513,784 | 1978-12-31 .. 2025-12-31 | 2026-08-20 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_swe_*.parquet` | 1 | 33 MiB | 99,595 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_deu_*.parquet` | 1 | 32 MiB | 112,168 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_fra_*.parquet` | 1 | 30 MiB | 103,907 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/ibes_consensus_monthly_early.parquet` | 1 | 26 MiB | 3,682,004 | n/a | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/bulk/contrib_general__*.parquet` | 5 (5 tables) | 25 MiB | 883,231 | 1991-06-30 .. 2024-09-30 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/compustat_fundq.parquet` | 1 | 23 MiB | 208,603 | 2013-01-31 .. 2024-12-31 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/time_machine_arena_rows.parquet` | 1 | 21 MiB | 365,390 | n/a | 2026-09-01 | `scripts/time_machine_arena.py` |
| `backend/data/optimus/wrds/bulk/wrdsapps_link_crsp_taq__*.parquet` | 1 | 20 MiB | 1,451,140 | 1993-01-31 .. 2014-12-31 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/holder_qsnap.parquet` | 1 | 18 MiB | 629,086 | n/a | 2026-09-02 | `scripts/holder_fingerprint.py` |
| `backend/data/optimus/wrds/ibes_consensus_monthly.parquet` | 1 | 17 MiB | 1,554,570 | n/a | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_ita_*.parquet` | 1 | 16 MiB | 49,342 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/feature_ext_analyst_panel.parquet` | 1 | 14 MiB | 444,167 | n/a | 2026-09-03 | `learner/features_ext.py` |
| `backend/data/optimus/wrds/bulk/wrdsapps_patents__*.parquet` | 1 | 14 MiB | 1,471,276 | 2011-01-04 .. 2019-12-31 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/feature_ext_holder_panel.parquet` | 1 | 13 MiB | 171,822 | 2012-05-15 .. 2025-02-14 | 2026-09-03 | `learner/features_ext.py` |
| `backend/data/optimus/wrds/finratio_monthly_early.parquet` | 1 | 12 MiB | 1,420,021 | 1990-01-31 .. 2012-12-31 | 2026-08-19 | `scripts/wrds_repull_finratio_early.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_che_*.parquet` | 1 | 11 MiB | 33,337 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_esp_*.parquet` | 1 | 7 MiB | 28,458 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/jkp_full/jkp_risk_nld_*.parquet` | 1 | 5 MiB | 15,490 | 2013-01-31 .. 2024-12-31 | 2026-08-22 | `scripts/wrds_pull_jkp_full.py` |
| `backend/data/optimus/wrds/link_bond_crsp.parquet` | 1 | 4 MiB | 358,312 | n/a | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/bulk/wrdsapps_link_crsp_bond__*.parquet` | 1 | 3 MiB | 212,416 | n/a | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/wrdsapps_eushort__*.parquet` | 1 | 3 MiB | 500,271 | 2003-03-26 .. 2026-07-19 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/wrdsapps_windices__*.parquet` | 1 | 2 MiB | 379,134 | 1990-06-29 .. 2026-06-26 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/frb_rates_daily.parquet` | 1 | 1 MiB | 25,924 | 1954-01-04 .. 2025-02-13 | 2026-08-20 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/link_optionm_crsp.parquet` | 1 | 1 MiB | 121,773 | 1994-09-01 .. 2025-12-30 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/bulk/eventus__*.parquet` | 1 | 1 MiB | 25,841 | n/a | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/optionm_etf_quotes/under_*.parquet` | 27 | 1 MiB | 23,163 | 1999-01-04 .. 2025-08-29 | 2026-08-27 | `scripts/wrds_pull_etf_option_quotes.py` |
| `backend/data/optimus/wrds/link_ibes_crsp.parquet` | 1 | 1 MiB | 37,662 | 1976-01-15 .. 2025-12-18 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/link_ccm.parquet` | 1 | 1 MiB | 33,324 | n/a | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/bulk/wrdsapps_link_crsp_ibes__*.parquet` | 1 | 1 MiB | 22,802 | 1976-01-15 .. 2025-12-18 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/bulk/wrdsapps_link_crsp_optionm__*.parquet` | 1 | 0 MiB | 16,897 | 1994-09-01 .. 2025-11-17 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |
| `backend/data/optimus/wrds/link_cusip_permno_early.parquet` | 1 | 0 MiB | 24,114 | n/a | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/ff_factors_daily.parquet` | 1 | 0 MiB | 26,274 | 1926-07-01 .. 2026-06-30 | 2026-08-20 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/link_taq_crsp.parquet` | 1 | 0 MiB | 685,811 | 1993-01-31 .. 2014-12-31 | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/ff_fivefactors_daily.parquet` | 1 | 0 MiB | 15,854 | 1963-07-01 .. 2026-06-30 | 2026-08-20 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/frb_rates_monthly.parquet` | 1 | 0 MiB | 1,274 | 1919-01-31 .. 2025-02-28 | 2026-08-20 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/link_cusip_permno.parquet` | 1 | 0 MiB | 11,603 | n/a | 2026-08-19 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/ff_factors_monthly.parquet` | 1 | 0 MiB | 1,200 | 1926-07-01 .. 2026-06-01 | 2026-08-20 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/ff_fivefactors_monthly.parquet` | 1 | 0 MiB | 756 | 1963-07-01 .. 2026-06-01 | 2026-08-20 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/ff_liq_ps.parquet` | 1 | 0 MiB | 761 | 1962-08-31 .. 2025-12-31 | 2026-08-20 | `scripts/wrds_training_pull.py` |
| `backend/data/optimus/wrds/bulk/fjc__*.parquet` | 1 | 0 MiB | 47 | 2007-03-14 .. 2024-11-20 | 2026-08-21 | `scripts/wrds_pull_everything.py` (+ `wrds_pull_catchup.py`, `wrds_requeue_broken.py`) |

**Totals: 1,378 parquet files, 58.52 GiB (62,832,261,633 bytes), 1,931,802,994
rows, 84 families.** Plus 230 JSON (198 of them `.meta.json` sidecars, which ARE
committed), 6 logs and 1 JSONL — 58.59 GiB for the whole tree. Regenerated by
walking the tree and reading parquet footers only; nothing here was loaded.

### 13.90 GiB of the tree is the same bytes twice, under a second library name

`scripts/wrds_pull_everything.py` writes `bulk/{schema}__{table}.parquet` from a
catalogue probe, and **WRDS exposes several libraries under two names**. The
puller's resumability key is the filename, so `comp` and `comp_na_daily_all` —
the same physical library — were both pulled in full, and neither run could see
the other. Verified by exact size match plus a head+tail SHA-256 over the
parquet footer, and spot-checked with full-file SHA-256 on seven pairs (all
byte-identical):

| Alias pair | Duplicated tables |
|---|---:|
| `ibes` = `tr_ibes` | 94 |
| `comp` = `comp_na_daily_all` | 76 |
| `optionm` = `optionm_all` | 68 |
| `crsp` = `crsp_a_stock` | 38 |
| `contrib` = `contrib_general` | 4 |
| `tfn` = `tr_13f` | 3 |
| `wrdsapps` = `wrdsapps_{finratio,finratio_ibes,bondret,eushort,patents,windices,link_crsp_*}` | 11 |

**294 redundant files, 13.90 GiB (23.7% of the tree).** A separate 0.35 GiB
across 8 groups is WRDS serving byte-identical content under two *different*
table names in the same library (`crsp__dsp500list` = `crsp__msp500list`,
`ibes__stop_epsint` = `ibes__stopu_epsint`, `crsp__dseshares` = `crsp__mseshares`,
…) — that one is upstream, not ours. Total redundancy **14.25 GiB / 312 files**.

**Nothing is deleted here.** A duplicate is reported, not removed: some caller
may reference either spelling, and reclaiming the disk is Murat's call. The
cheap forward fix is a library-alias table in `wrds_pull_everything.py` so a
third pass does not buy the same bytes a third time.

### What the manifest cannot tell you, and says so

- `bulk/_quarantine_truncated/` (23 files, 1.45 GiB) holds pulls that stopped at
  a round row count — `optionm__*` at exactly 144,000,000 rows across 18 files,
  `comp__*` at 24,000,000, `crsp__*` at 16,000,000. They were moved there by
  `scripts/wrds_quarantine_truncated.py` and are **not** valid substrate. The
  round numbers are the evidence: a real table does not end on a power of ten.
- `superseded/crsp_dsf_*.narrow-5col.parquet` (23 files, 321 MiB) is the
  5-column 1990–2012 CRSP daily pull that the 12-column re-pull replaced. Kept
  as provenance, read by nothing.
- No family here is a `RESEARCH_CLAIM` input by virtue of being listed. The
  manifest records what is on disk; a claim still needs its receipt.

## Ignored by the model rules (`*.joblib`, `*.pkl`)

| Path | Produced by | Provenance |
|---|---|---|
| `backend/data/optimus/learner/models/champion_full.joblib` | `scripts/learner_run.py` | vintage sha `3300a8550a4cc99e`, trained through 2024-11 — recorded in `learner_v1.json → sealed_models.full` |
| `backend/data/optimus/learner/models/champion_shadow.joblib` | `scripts/learner_shadow_seal.py` | vintage sha `1dcee45058e078aa` — `sealed_models.shadow` |
| `backend/models/crash_model.pkl` | `python -m engine.training.train_crash_model` | trained on deploy |

**A model binary is not evidence; its vintage hash in the receipt is.** If the
binary is missing, the receipt still tells you exactly which model produced the
numbers, and the script rebuilds it deterministically (`seed 20260902`).

## Secrets, which are ignored and stay put

`.env`, `.env.local`, `.env.production`, `.env.hidden`, `.env.*.hidden`, and (added
2026-09-03) `.env.bak` / `.env.bak.*`.

`.env.bak.2026-08-27` exists in the working tree and **contains live keys**. It
is ignored, it is deliberately **not deleted and not moved** by any session, and
it is not staged. If it should leave the tree, a human moves it. The reason for
the rule is on the record: on 2026-08-24 a CI-mimic recipe moved `.env` aside
inside a subshell whose EXIT trap never ran, and the machine lost every key on
it. Use `AEGIS_IGNORE_DOTENV=1` to reproduce CI; never move a key file.
