# Data catalog + ledger archival (chunk C10), 2026-10-06

**RESULT IMPROVEMENT: NONE (infrastructure).** It answers the owner's "we pull the same data
again / lost media in folders / large-ledger archival" complaints. It does not change any
forecast or book.

Receipt: `backend/data/optimus/data_catalog/catalog_20261006T162615Z.json` (run clock
2026-10-06T16:26:15Z). Generated summary: `docs/DATA_CATALOG.md`. Ledger manifests:
`backend/data/optimus/ledger_manifests/llm_calls_2026-09.json`,
`backend/data/optimus/ledger_manifests/evidence_memory_2026-09.json`.

## Totals (from the receipt)

| | |
|---|---:|
| datasets (rows) | **4,420**: 3,853 files plus 567 directories of small files |
| files walked | 39,888 |
| bytes | **105.79 GB**. That is 82.09 GB under `backend/data/`, 0.47 GB under `ft_lab/data/`, and 23.24 GB in `<llama models>` (5 files, outside the repo) |
| duplicate groups (same content at 2+ paths) | **370** (358 exact sha256, 12 probable by size + head/tail). **15.40 GB redundant** |
| of which WRDS alias pairs (`comp`=`comp_na_daily_all`, `wrdsapps`=`wrdsapps_finratio*`, ...) | 302 groups, 15.3 GB. This matches DATA_MANIFEST.md's own 2026-09-04 finding |
| orphans (no code file names them) | **1,254 rows / 44.5 GB** (1,134 files / 44.4 GB). Mostly WRDS bulk tables that nothing reads |
| `UNKNOWN_PROVENANCE` | **2,784 rows / 35.5 GB** |
| inspection errors | 0 |

The five biggest files:

1. `<llama models>/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf`: 18.56 GB
2. `backend/data/optimus/wrds/bulk/contrib__global_factor.parquet`: 5.35 GB (orphan)
3. `<llama models>/Qwen2.5-7B-Instruct-Q4_K_M.gguf`: 4.68 GB
4. `backend/data/optimus/aegis_panel/aegis_panel_v2.parquet`: 4.49 GB
5. `backend/data/optimus/learner/features_price.parquet`: 1.67 GB

Duplicates outside WRDS worth a look:
- two nn_lab walk-forward outputs from 09-29 that are byte-identical (63 MB);
- `sec_facts_history.parquet` = `sec_facts_history_2026-09-27.parquet`;
- two strategy-library twin panels from different days that are identical;
- the same night-factory CSV under four dated folders.

Reading the numbers:
- **Orphan** is a heuristic. A dataset counts as consumed when a tracked or untracked code file names
  it by basename, stem, name family (`llm_calls_2026-09` -> `llm_calls`) or a specific parent
  directory. A path built entirely at run time can be missed. An orphan is a question, not a
  deletion order.
- **Provenance** comes from DATA_MANIFEST.md table rows (path glob plus "Produced by"), a committed
  ledger manifest, a `.meta.json` sidecar, or an exact file named in DATA_MANIFEST prose. A
  directory mentioned in prose does not count: one sentence naming `backend/data/optimus/` had
  claimed 2,653 rows on the first run, and that was fixed before this receipt.

## "Do we have X?" in one command

    python -m backend.services.data_catalog --query bars_EU
    python -m backend.services.data_catalog --query permno      # matches column names too

The newest receipt is chosen by the run id in its name, never by mtime.

## The ledger manifests written tonight

| month file | jsonl | rows (unparseable) | parquet | sha256 jsonl / parquet |
|---|---:|---:|---:|---|
| `backend/data/optimus/llm_calls_2026-09.jsonl` | 177.9 MB, ignored | 287,041 (5 torn lines, kept verbatim) | 13.2 MB | `d799576a...` / `a45f9f38...` |
| `backend/data/optimus/learner/evidence_memory_2026-09.jsonl` | 65.1 MB, ignored | 102,030 | 1.1 MB | in the manifest |

How the archive works:
- **Lossless.** Each jsonl line is stored verbatim (binary) with its line number and stamp. The
  archive refuses unless rebuilding from the Parquet reproduces the jsonl's sha256.
- **Nothing deleted.** The jsonl files stay where they are.

Effects on the existing rotation gates:
- The two month-rotation gates that were red since 10-02
  (`test_a_closed_month_of_the_llm_ledger_must_be_tracked`,
  `test_a_closed_month_on_disk_must_be_tracked`) are now green.
- The guard accepts a manifest whose recorded size matches the file in place of `git add -f`.
- The month writers refuse an archived month:
  - `llm_telemetry.append` sends the row to the live month, marked
    `redirected_from_archived_<month>`, so no spend is lost;
  - `evidence_memory.append` raises;
  - both rotation scripts refuse to re-write that month.

## What "the long-term archival design for very large monthly ledgers is unresolved" meant

Two ledgers grow with every LLM call and every night of research. In September they were split into
one file per month. The plan was: the current month stays out of git, and on the 1st the finished
month is committed. September's LLM spend ledger finished at 178 MB. GitHub refuses any file over
100 MB, so the planned step could not be done. The month existed only on this laptop, and two
tests stayed red. "Unresolved" meant we had no answer for storing a finished month that is too big
for git.

The answer now:
- A finished month is copied into a compressed Parquet file outside git (178 MB became 13 MB).
- A small committed manifest records exactly what the month contained: rows, dates, and
  fingerprints of both files.
- Writers can no longer change a finished month, so the fingerprints stay true.
- A daily job (`AegisDataCatalog`, via `python -m scripts.task_keeper catalog`) does this for every
  future month automatically.

**What the owner needs to do to get the 178 MB file out of git history: nothing.** It was never
committed. It is gitignored by the `llm_calls_[0-9]...jsonl` rule, and `git log --all` has no entry
for it. Git history does still hold the pre-rotation monoliths, about 65 MB each
(`llm_calls.jsonl`, many `evidence_memory.jsonl` versions). They are under the 100 MB limit and only
cost clone size. Removing them would mean rewriting history, which is roadmap decision D10 = no.
Going forward it is one `.gitignore` block (added: `backend/data/optimus/ledger_archive/`) plus one
committed manifest per closed month.

Still open:
- **Backup.** The Parquet copies and the jsonl files are on one disk. The manifest proves what they
  contained, but it does not restore them. An off-machine copy of `ledger_archive/` is the owner's
  choice of where.
- **`predictions.jsonl`** is tracked, 50.8 MB and growing. It was deliberately not touched. It will
  hit the same wall and needs the same monthly split before ~100 MB.
