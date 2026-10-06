# Data catalog + ledger archival (chunk C10), 2026-10-06 (revised 10-07 after review)

**RESULT IMPROVEMENT: NONE (infrastructure).** It answers the owner's "we pull the same data
again / lost media in folders / large-ledger archival" complaints. It does not change any
forecast or book. The duplicate list does produce findings (REPLAYs and identical weighting
variants, below); those findings belong on the morning report, not in a disk-reclaim list.

Revised after the adversarial review `docs/reviews/REVIEW_2026-10-06_C10_DATA_CATALOG.md` (64/100).
The archiver was confirmed lossless. The sealed-month guard was hardened (F2), and the scheduled
job is now scan-only (F4). Duplicates are classified (F1), and paths built at run time are no
longer reported as unreferenced (F7).

Receipt: `backend/data/optimus/data_catalog/catalog_20261006T180640Z.json` (run clock
2026-10-06T18:06:40Z). It is gitignored; the job keeps the newest 7 plus the first of each month.
Tracked summary: `docs/DATA_CATALOG.md`. Ledger manifests:
`backend/data/optimus/ledger_manifests/llm_calls_2026-09.json` and
`backend/data/optimus/ledger_manifests/evidence_memory_2026-09.json`.

## Totals (from the receipt)

| | |
|---|---:|
| datasets (rows) | **4,742** (up from 4,420 at 16:26Z: other builders wrote ~320 new files in between) |
| bytes | **105.83 GB**: about 82 GB under `backend/data/`, 0.47 GB under `ft_lab/data/`, 23.24 GB in `<llama models>` (5 files, outside the repo) |
| duplicate groups | **370**: 358 exact sha256 (**8.56 GB** redundant) + 12 probable by size+head/tail 1 MB (**6.84 GB**). Exact and probable are reported separately |
| by class | ALIAS 294 groups / 14.92 GB (WRDS library aliases; the only class that is disk to reclaim) · **REPLAY 61** · DATA_CHECK 8 / 0.38 GB · **VARIANT_IDENTICAL 6** · SNAPSHOT 1 |
| runtime-built (declared `RUNTIME_PATTERNS`) | **837 rows / 44.17 GB**: WRDS `bulk/<schema>__<table>.parquet` (built by `scripts/wrds_pull_catchup.py:620`) and `contest/bars/bars_<market>.parquet` (built by `scripts/contest_calendar.py:453`) |
| **no static reference** (no code file names them, and no runtime pattern builds them) | **419 rows / 0.36 GB** (297 files) |
| `UNKNOWN_PROVENANCE` | **3,106 rows / 35.5 GB** |
| inspection errors | 0 |

On "no static reference": the first draft's headline was "44.5 GB orphaned". Almost all of
that (44.17 GB) is runtime-built: code assembles those paths from variables. Of the WRDS bulk
tables, we can say no analysis reads them; we cannot say no code names them. The 0.36 GB that
remains is a list of questions, not a deletion list.

The five biggest files:

1. `<llama models>/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf`: 18.56 GB
2. `backend/data/optimus/wrds/bulk/contrib__global_factor.parquet`: 5.35 GB (runtime-built)
3. `<llama models>/Qwen2.5-7B-Instruct-Q4_K_M.gguf`: 4.68 GB
4. `backend/data/optimus/aegis_panel/aegis_panel_v2.parquet`: 4.49 GB
5. `backend/data/optimus/learner/features_price.parquet`: 1.67 GB

## Findings hidden in the duplicates (review F1)

Each group below is two "runs" that should have differed and did not. All 61 REPLAY groups are
listed on the receipt under `findings.replays`.

- **REPLAY** (CLAUDE.md protocol 9): same run family, different run ids, identical bytes.
  - `nn_lab/walkforward/oos_size_20260929T133547Z` = `..._133907Z` (63 MB): two runs 4 minutes apart.
  - `night_factory_{09-10,09-30,10-01,10-02}/E1_event_head_h5_run01_daily.csv`: four nights, one result.
  - `night_factory_2026-09-13/E1_..._run02` = `_run03`: two runs the same night.
  - `X_anon_gap_answers_run01` (09-30 = 10-02) and 09-12 run03 = 09-19 run01: identical LLM
    answers across nights. That means a cache or a replay, not new evidence.
  - `sizing_lab/sizing_crsp_monthly_2026-09-29T031017Z` = `T031402Z` = `T031829Z`: three runs,
    one answer.
  - `x_lane/elasticity_2026-09-12_run01` = `2026-09-22_run01`.
  - `strategy_library/holdings_parts_2026-09-27/*` = `..._2026-09-28/*` (30 parts) and both
    `twin_panel`s. This is fine if the day-over-day rebuild is deterministic, but it must not be
    counted twice.
- **VARIANT_IDENTICAL**: in `hyp_lab/fair_twin_series_FT_2026-10-06_1/`, six weighting variants
  are byte-identical to their parents:
  - `mom_12_1` = `_ivw` = `_liqw`
  - `gp_at` = `_ivw`
  - `quality_composite` = `_ivw`
  - `mom_flow` = `_ivw`
  - `net_raises` = `_ivw`
  - `mom_12_1_q` = `_q_jajo`

  The weighting path did nothing. This is being fixed in C1b and is only listed here.
- **DATA_CHECK**: differently named source tables that are byte-identical. These are a data
  question, not a disk question.
  - `ibes__detusecd_sepint` = `ibes__ndetusecd_sepint`, and also `excusecd`/`nexcusecd`, while
    their `xsepint` siblings differ.
  - `ibes__stop_epsint` = `stopu_epsint`, and `stop_epsus` = `stopu_epsus`.
  - CRSP daily = monthly for `senasdin`, `seshares` and `sp500list`.
- **SNAPSHOT**: `sec_facts_history.parquet` = `sec_facts_history_2026-09-27.parquet` (keep).

## "Do we have X?" in one command

    python -m backend.services.data_catalog --query bars_EU
    python -m backend.services.data_catalog --query permno      # matches column names too

## The ledger archives

| month file | jsonl | lines (unparseable) | parquet | sealed? |
|---|---:|---:|---:|---|
| `backend/data/optimus/llm_calls_2026-09.jsonl` | 177.9 MB, ignored | 287,041 (5 torn, kept verbatim) | 13.2 MB | **not yet**: parquet untracked |
| `backend/data/optimus/learner/evidence_memory_2026-09.jsonl` | 65.1 MB, ignored | 102,030 | 1.1 MB | **not yet**: parquet untracked |

- **Lossless.** The reviewer re-derived this on nine fixtures and on both real months: every line
  is stored verbatim as `binary` with its line number and stamp, and the bytes rebuild exactly.
- **Nothing deleted.**
- **The sealed-month guard's rule (after F2).** A closed month that git does not track counts as
  sealed only when four things hold:
  - its manifest carries sha256s for both files;
  - the Parquet exists and hashes to the manifest;
  - **git tracks the Parquet**;
  - the jsonl still hashes to the manifest.

  Otherwise the gate stays red and names the reason. A forged four-field manifest, a same-size
  one-byte edit, a missing Parquet and a tampered Parquet are each refused, and each has a test.
  `.gitignore` now un-ignores `backend/data/optimus/ledger_archive/*.parquet`.
- **What turns the two gates green is the commit, not this code.** The gates are
  `test_a_closed_month_of_the_llm_ledger_must_be_tracked` and
  `test_a_closed_month_on_disk_must_be_tracked`. They are RED tonight with the reason
  "parquet ... is not tracked by git; run: git add ...". With the two Parquet files and the two
  manifests committed, they pass. I checked this by substituting `is_tracked` on the real files,
  with the sha checks run on the real bytes.
- **The daily job only scans** (`python -m scripts.task_keeper catalog` →
  `ledger_archive.scan_report`). It reports each closed month over 50 MB that is not sealed,
  with the reason and the exact command. Sealing is an attended `--apply` followed by a commit.
- **The writers.**
  - `llm_telemetry.append` redirects a row that is stamped into an archived month to the live
    month (spend is never lost).
  - `evidence_memory.append` raises.
  - The rotation scripts refuse.
  - Manifest matching honours `AEGIS_REPO_ROOT`, so this also holds in the frozen exe (F3).

## What "the long-term archival design for very large monthly ledgers is unresolved" meant

Two ledgers grow with every LLM call and every night of research. In September they were split into
one file per month. The plan was: the current month stays out of git, and on the 1st the finished
month is committed. September's LLM spend ledger finished at 178 MB. GitHub refuses any file over
100 MB, so the planned step could not be done, and the month existed only on this laptop.
"Unresolved" meant we had no answer for a finished month that is too big for git.

The answer now:
- A finished month is copied into a compressed, byte-for-byte reversible Parquet file (178 MB
  became 13 MB). The Parquet file is **committed**, together with a small manifest recording
  rows, dates and fingerprints of both files.
- Writers can no longer change a finished month.
- A daily job tells you when a month needs sealing. The sealing itself stays a deliberate step.

**What the owner needs to do to get the 178 MB file out of git history: nothing.** It was never
committed: it is gitignored, and `git log --all` has no entry for it. Git history does hold
several pre-rotation ~65 MB monoliths. They are under the limit and only cost clone size;
removing them would mean rewriting history, which is roadmap decision D10 = no. Going forward:
commit the two Parquet files and two manifests (14.3 MB in total), and seal each future big
month the same way.

Still open:
- **`predictions.jsonl`** is tracked, ~52 MB, growing ~25 MB a month, and is rewritten in place
  on every resolution. The review's §Q8 gives a design: split frozen forecasts from their grades
  as two append-only monthly streams, and chain the manifests rather than the rows. It needs an
  attended migration.
- The size+mtime cache key is fine for a catalog and is not used for a seal (review F8).
