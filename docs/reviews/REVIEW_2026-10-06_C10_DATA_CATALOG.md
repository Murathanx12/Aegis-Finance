# REVIEW: C10, the data catalog and closed-ledger archival (adversarial, 2026-10-07)

Reviewer: Opus 5.5, read-only. Scope: `backend/services/data_catalog.py`,
`backend/services/ledger_archive.py`, the writer and guard edits in
`backend/services/llm_telemetry.py`, `learner/evidence_memory.py`,
`scripts/evidence_memory_rotate.py` and `scripts/llm_calls_rotate.py`, the
`task_keeper catalog` job, `.gitignore`, the two committed manifests, and
`backend/tests/test_data_catalog_and_ledger_archive.py`. Build: WIP `f4dbd0c0` plus the tree.
Nothing was edited, committed, deleted or archived. Every experiment ran in a temp directory
or read data without changing it.

## VERDICT

**SHIP THE ARCHIVER AND THE CATALOG. REVERT THE GUARD CHANGE, OR MAKE IT HONEST.**

The lossless claim is true. I re-derived it on nine fixtures and on both real September
months, and the bytes are identical. The catalog is useful, and its duplicate list contains
the most important finding of this chunk, which the builder filed as "disk to reclaim":
**six weighting variants in C1's fair-twin run produced byte-identical series to their
equal-weight parents** (F1).

The sealed-month guard change does something different from what it claims. The guard
existed so that a closed month would not live on one laptop only. After this change, the
guard is green while **both September months still exist on one laptop only**: the jsonl is
gitignored and the Parquet is gitignored. The guard also accepts a four-field hand-written
manifest, and it accepts a same-size in-place edit (F2). That makes a red gate green without
fixing what it protected, which is the same failure this repo has written down several times.
The fix is small: commit the Parquet (13.2 MB and 1.1 MB, both well under GitHub's limit)
and check the sha256.

**Score: 64 / 100.**

---

## Findings

### F1. HIGH (cross-chunk). The "duplicates" include a broken C1 weighting path and four replays

The catalog lists 370 duplicate groups as redundant bytes. Some of these groups are not
wasted disk. They show that two runs which should have differed did not:

| group | what it means |
|---|---|
| `hyp_lab/fair_twin_series_FT_2026-10-06_1/`: `mom_12_1` = `mom_12_1_ivw` = `mom_12_1_liqw`; `gp_at` = `gp_at_ivw`; `quality_composite` = `_ivw`; `mom_flow` = `_ivw`; `net_raises` = `_ivw`; `mom_12_1_q` = `_q_jajo` | I loaded the frames. **`gross`, `cost`, `turnover` and every twin column are `DataFrame.equals` True.** `strategy_library.py:1827-1833` declares these as `inv_vol` / `inv_amihud` weightings. The fair-twin path graded them all as their equal-weight parent. So every ivw/liqw row on that board is a duplicate of its parent, the variant count is inflated, and any "ivw beats ew" reading from that run is void. (`_q` = `_q_jajo` may be a legitimate default alias. Check.) |
| `nn_lab/walkforward/oos_size_20260929T133547Z` = `..._133907Z` (63 MB) | two run IDs four minutes apart, identical OOS output: a replay (CLAUDE.md protocol item 9) |
| `night_factory_{09-10,09-30,10-01,10-02}/E1_event_head_h5_run01_daily.csv` | **four nights, one result.** Overlap is 1.000 and discovery is zero, as in the G3 replay |
| `night_factory_2026-09-13/E1_..._run02` = `_run03` | two "runs" the same night with no seed variation |
| `X_anon_gap_answers_run01` (09-30 = 10-02; 09-12 run03 = 09-19 run01) | LLM answers byte-identical across nights. That means a cache or a replay. If these were counted as new evidence, they were not new |
| `sizing_lab/sizing_crsp_monthly_2026-09-29T031017Z` = `T031402Z` = `T031829Z` | three runs, one answer |
| `strategy_library/holdings_parts_2026-09-27/*` = `..._2026-09-28/*` (30 parts) and both `twin_panel`s | an identical day-over-day rebuild. That is fine if it is a deterministic rebuild, but do not count it twice |
| `wrds/bulk/ibes__detusecd_sepint` = `ibes__ndetusecd_sepint` (plus the `tr_` aliases) | two **differently named** IBES tables are byte-identical, while their `xsepint` siblings differ. Either the pull returned the same table for both, or this is a known alias. It is a data question, not a disk question |

The builder's note does mention "nn_lab outputs byte-identical" under "worth a look". It
does not say that this is a replay, and it does not see the fair-twin collapse. **The catalog
should classify a duplicate**: a WRDS alias is a reclaim, and a same-family different-run-id
pair is a REPLAY finding that goes on the morning report.

Also, 6.84 GB of the 15.40 GB headline (12 groups) is "probable" (size + head/tail 1 MB),
not exact. The headline adds both together. Print exact and probable separately.

### F2. HIGH. The sealed-month guard was weakened: green without the protection, forgeable, blind to same-size edits

What the gate protected (its own docstring in `scripts/evidence_memory_rotate.py`):
*"the month is simply missing for everyone else and gone the day the laptop is reimaged."*
The remedy was to put the bytes in git.

What it accepts now is a manifest whose `jsonl.path` matches and whose `jsonl.bytes` equals
`st_size`. The manifest is committed, **but the bytes are not**:

- `git check-ignore`: `backend/data/optimus/ledger_archive/llm_calls_2026-09.parquet` is ignored by
  `.gitignore:331`. The jsonl is ignored by `llm_calls_[0-9]...jsonl`. `git ls-files` shows
  `llm_calls_2026-08.jsonl` tracked (the old design worked) and **no September file of either
  ledger tracked in any form**. The two September months are on one disk. The manifest
  records a sha256 of bytes that nobody else can obtain.
- **Forgeable.** I demonstrated it in a temp directory. A manifest of four fields,
  `{"archived": true, "jsonl": {"path": ..., "bytes": <size>}}`, with no Parquet, no sha256
  and no round-trip flag, moves a month from `months` (red) to `archived` (green).
- **Same-size tamper is invisible.** I flipped one byte in place in the "sealed" month. The
  guard still reported it `archived`. It compares the size, not the sha256 that the manifest
  already carries.
- **"This turned two red tests green."** That is the wrong success metric. The two tests
  (`test_llm_calls_rotation.py:328`, `test_evidence_memory_rotation.py:281`) went red because
  the month was not sealed. They are now green, and the month is still not sealed anywhere
  except locally.
- `evidence_memory_2026-09.jsonl` is **65 MB, under GitHub's 100 MB limit**. The original
  `git add -f` remedy was available for it. The "cannot be committed" reason applied only to
  `llm_calls`.

What would make the guard honest, in this order:
1. Commit the Parquet, both 13.2 MB and 1.1 MB. Add a negation such as
   `!backend/data/optimus/ledger_archive/*.parquet`, or `git add -f`.
2. Let the guard accept a manifest only when the Parquet is **tracked** and the Parquet's
   sha256 matches `parquet.sha256`. That is cheap: 13 MB, against hashing a 178 MB jsonl.
3. Optionally, when the jsonl is still on disk, check its sha256 against the manifest, with
   a size+mtime cache. That is acceptable for a cache (F5).

### F3. MEDIUM. Frozen-path defect: archived-month protection turns off silently outside the checkout

`ledger_archive.REPO = Path(__file__).resolve().parents[2]` ignores `AEGIS_REPO_ROOT`, and
`manifest_for` matches `man["jsonl"]["path"] == _rel(path)`. When `REPO` is not the checkout
(the frozen exe, or `AEGIS_DATA_DIR` relocations), `_rel` returns an absolute path and the
match fails. Measured in-process: `is_archived(llm_calls_2026-09.jsonl)` is `True` normally
and **`False` with `REPO` set to a frozen bundle path**. Then `llm_telemetry.append` writes a
late row straight into the archived month (no redirect), the rotation scripts stop refusing,
and the manifest's sha256 becomes false. C13 fixed `data_catalog.default_roots` for this
defect family, but not `ledger_archive`. `data_catalog.DOC_PATH`, `MANIFEST_DOC` and
`_safe_rel` still use the module-relative `REPO` too. Fix: one `_repo_root()` shared by both
modules, and match manifests on `(ledger, month)` plus the sha256, not on a path string.

### F4. MEDIUM. Unattended archival, and an "identical" short-circuit that does not check the Parquet

- `task_keeper catalog` calls `LA.archive_closed()` (apply=True) **every day at 05:30, unattended**.
  On the first run after a month closes, every month over 50 MB becomes immutable to its
  writers, by cron, and writes a manifest that no one commits. The bytes still are not
  committed (F2). Archival is a sealing decision: make the cron do `--scan` and report, and
  have a person run `--apply` and commit. At minimum, the daily job should refuse to report
  OK while a local manifest is uncommitted.
- `archive_month` returns `"identical"` when the prior manifest's jsonl sha256 matches,
  **without checking that the Parquet still exists or still hashes to `parquet.sha256`**.
  Delete the Parquet and the daily job keeps printing `identical` / `OK`. That is a green
  line over a missing archive.
- An empty month file refuses with a misleading reason: `b"".split(b"\n")` produces
  `trailing=True`, which rebuilds as `b"\n"` ("round trip did not reproduce"). The refusal is
  safe, but the message is wrong.

### F5. LOW. Lossless claim confirmed. Small wording corrections

My round trip (temp directory, `archive_month` then `restore_bytes`):

| fixture | result |
|---|---|
| LF with trailing newline / no trailing newline | identical |
| **CRLF** (`\r` stays inside the line bytes) | identical |
| torn lines `"1.0.0"}` and `"}` | identical; counted unparseable |
| blank lines, double trailing newline | identical |
| NUL bytes and invalid UTF-8 | identical (the column is `binary`) |
| empty file | REFUSED (F4) |
| **real `llm_calls_2026-09`** | restored 177,881,771 bytes, sha256 matches the manifest; the live jsonl still matches; the 5 torn lines are at line numbers 36844, 51531, 53481, 73978, 223178, verbatim |
| **real `evidence_memory_2026-09`** | 65,060,980 bytes, sha256 matches |

Corrections: the column is **`binary`, not string**, which is why NUL and bad UTF-8 survive.
The refusal does compare the sha256 of the **rebuilt** bytes read back from the temp Parquet
before `os.replace`. `jsonl.rows` counts lines, not records (blank lines included), and
`rows_unparseable` counts blank lines. Rename these to `lines` / `lines_unparseable`.

### F6. LOW. The `redirected_from_archived_<month>` mark does not misattribute spend

Every reader that does accounting goes by the row's own `ts`, not by the file:
`llm_cost_audit` (`_iso_day(row["ts"])`, `--since`), `openclaw_usage` (by_day from `ts`
across the newest N files), and `read_calls` (all files concatenated, amendments folded by
id). The redirect keeps the September `ts` and only adds `meta.month_source`, so the
DeepSeek balance reconciliation is unaffected. Two edge cases:
`scripts/fast_mover_forensics.llm_spend` reads only `llm_calls_<today:%Y-%m>.jsonl`, so it
counts a redirected September row as "this month". A reader that reads the September file
alone misses it. The volume is near zero: both writers stamp `_now()` (telemetry `ts` is
call time, evidence_memory `utc = _now()`), so `evidence_memory.append`'s new raise is
**unreachable in production**. A row with an old stamp in a cost ledger is itself unusual.
Count `redirected_from_archived_*` rows on `ledger_health` so the case is visible.
`_month_is_archived` fails open (returns False on exception), so a failure appends into the
archived month. That is the right trade-off for telemetry, and the size check would catch it.

### F7. MEDIUM. Orphan false positives on live data: the label is unsafe as a reclaim list

Paths built at runtime are invisible to the token index:
- `contest/bars/bars_{EU,CN,JP,IN,TW,HK,KR}.parquet` (~100 MB) are **orphans** in the receipt.
  They are read by `scripts/contest_calendar.py:453` (`BARS_DIR / f"bars_{market}.parquet"`),
  which is the contest's live non-US bars.
- All `wrds/bulk/<schema>__<table>.parquet` are orphans, but `wrds_pull_catchup.py:620` and
  `training_substrate_receipt.py:120` build exactly those names. "Nothing reads them" may
  still be true for analysis, but "no code names them" is false.
- `jkp/*_all_factors_monthly_vw_cap.csv` for non-USA countries is likely real (only `usa_` is named).

The note does say "an orphan is a question, not a deletion order". But 44.5 GB labelled
"orphan" in a tracked doc will be read as a deletion list. Add an `f-string prefix` level
(index tokens that end in `_` before `{`, which `TOKEN` already yields, such as `bars_`) and
a `RUNTIME_PATTERNS` allowlist. The family level already handles `library_board_{run_id}`.

### F8. LOW. A size+mtime cache key is acceptable; say what it cannot see

Using mtime only as a **cache key**, and never as a date, does not break protocol item 7.
git's index does the same. What it cannot see:
(a) a rewrite that keeps both the size and the mtime (`os.utime`, `robocopy /COPY:T`,
archive restores, a racy write in the same mtime tick as the cache save, which git handles
as "racily clean" and this code does not);
(b) files over 200 MB, which are hashed only on size + head/tail 1 MB, so a change in the
middle of a big Parquet is invisible regardless of the cache.

Both are fine for a catalog. Neither is fine for a **seal**, which is why F2 must not
borrow this cache. Write `hash_basis: "cached(size,mtime_ns)"` or `"fresh"` on each row,
and force a full re-hash weekly.

### F9. LOW. 5 MB a day of untracked receipts, and a tracked doc that changes daily

`backend/data/optimus/data_catalog/catalog_*.json` is **neither ignored nor tracked**
(`git check-ignore` rc=1, `??`). Three receipts (15 MB) were written within three minutes
during development, and there is no retention. That is 1.8 GB a year, one `git add -A` away
from going into the repo. Meanwhile `docs/DATA_CATALOG.md` (tracked) is rewritten by the
05:30 job every day, so the working tree is dirty every morning with a 221-line diff of byte
counts. Commit a small daily **summary** (`summary` + `duplicates` classified + top 50
orphans, ~50 KB) only when it changes. Gitignore the full receipt and keep the last 7 plus
the first of each month. Regenerate the tracked doc only when the summary hash changes.

### F10. INFO. Tests: 90 passed; builder said 141

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest \
  backend/tests/test_data_catalog_and_ledger_archive.py backend/tests/test_llm_calls_rotation.py \
  backend/tests/test_evidence_memory*.py -q
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 3.13s
```

(`test_llm_calls_rotate*.py` as written in the brief matches no file. The file is
`test_llm_calls_rotation.py`. The builder's "141" must have included other files.)

Mocks and injections: `subprocess.run` is monkeypatched to return empty `git ls-files`
stdout (guard test); `LA.MANIFEST_DIR` and `LA.ARCHIVE_DIR` are monkeypatched to tmp
(`dirs` fixture); the catalog gets injected `TokenIndex.from_texts`, `use_git=False` and
`workers=1`; `task_keeper.run_catalog` gets lambda `archive`/`catalog`. Fixture dates come
from `now`, which is good. **Missing tests:** a forged or partial manifest must NOT seal; a
same-size edit must NOT seal; a missing Parquet must not return `identical`; `is_archived`
under a relocated `REPO`/`AEGIS_REPO_ROOT`; CRLF and empty-file round trips; and a
"runtime-built path is not an orphan" case.

---

## Q8. `predictions.jsonl`: a tracked, growing, tamper-evident ledger

Facts first, because they change the answer:

- It is **not append-only**. `belief_state.resolve_all` **rewrites the whole file in place**
  (`path.write_text(...)`, not atomic, no temp-then-replace) every time a record resolves.
  Any byte-level seal of this file breaks at the next resolution. This is why
  `ledger_archive.NEVER` has to exclude it.
- It is **CRLF on disk and in the committed blob** (35,438 `\r\n` now; 33,059 at HEAD).
  `append` and `write_text` use Windows text mode with no `newline="\n"`, the same defect
  that telemetry and evidence_memory fixed in September. A Linux writer (Railway) would
  produce different bytes for the same rows.
- It is 51.9 MB with 35.4k rows, growing about 25 MB a month, so it reaches 100 MB around
  December.

The design I would build:

1. **Separate the frozen forecast from its grade.** Use two append-only streams:
   `predictions_<made_month>.jsonl` (the row as made, never touched again) and
   `resolutions_<resolve_month>.jsonl` (`prediction_id`, `outcome`, `brier`,
   `resolved_at`, `resolution_detail`, `resolver_version`). The reader folds a resolution
   onto its prediction by id, which is the same pattern `read_calls` already uses for
   amendments. Then no closed month ever changes: a late grade is a new event, filed in the
   month it happened, and the redirect problem in F6 does not exist.
2. **Partition by month of `made_at`, and seal by committing.** At about 25 MB a month,
   every closed month fits in git as jsonl, so no Parquet is needed. Pin LF on write. When a
   month closes, commit the file plus a manifest with the sha256 and row count.
3. **Chain the manifests, not the rows.** Each month's manifest carries
   `prev_manifest_sha256`. Git is already a hash chain over commits, so this adds an
   in-band link that survives an export. Per-row chaining in an appended file is what broke
   on 25 Aug and has stayed broken since.
4. **The broken chain is not repaired.** Start a new segment with an explicit
   `chain_break` record that cites the line where the chain was found broken, the sha256 of
   the prefix as found, and the date it was noticed (25 Aug). The old segment is sealed
   as-is, with its break documented. A tamper-evident ledger that silently "heals" is the
   one thing worse than a broken one.
5. **Migration is one attended commit:** split the current file by `made_at` month, write
   each month's resolution rows into the resolution stream as they are today, and record
   the monolith's sha256 in the first manifest, so that anyone can verify that the split
   preserved every row.

---

## Three things I would have done instead

1. **Committed the Parquet instead of rewriting the guard.** Run
   `git add -f backend/data/optimus/ledger_archive/llm_calls_2026-09.parquet` (13.2 MB) and
   `git add -f backend/data/optimus/learner/evidence_memory_2026-09.jsonl` (65 MB, allowed
   as is). Then the guard accepts a manifest only when its Parquet is tracked and its
   sha256 matches. The two tests go green because the month is actually in git.
2. **Classified duplicates before summing them.** Sort them into `ALIAS` (WRDS schema
   pairs; reclaim), `SNAPSHOT` (a dated copy beside a live file; keep), and **`REPLAY`**
   (same family, different run IDs or dates; a finding for the morning report, with
   protocol item 9 cited). F1's fair-twin collapse would have been the headline of the
   note instead of a line in a list of disk to reclaim.
3. **Made the 05:30 job a scan, not an apply.** Unattended runs report candidates, and
   uncommitted manifests and missing Parquets are reported as DEGRADED. Sealing a month is
   an attended `--apply` followed by a commit, as the old `git add -f` was. The catalog job
   writes a 50 KB summary only when it changes, and never rewrites a tracked doc by itself.

## Score: 64 / 100

Start from 100. The archiver (lossless, refuses before it keeps, atomic temp-then-replace),
the catalog (dates from the data, query, receipt named by run id) and the writers that
refuse or redirect without losing spend all earn their place. Deductions:

| finding | deduction |
|---|---:|
| F2: guard made green without the protection; forgeable; checks size only | −15 |
| F1: replays and the fair-twin collapse filed as disk savings; exact and probable summed | −7 |
| F3 + F4: frozen-path gap; unattended apply; `identical` without checking the Parquet | −7 |
| F7 + F9: orphan false positives on live contest data; receipt sprawl and a doc that changes daily | −5 |
| F10: the builder's test count does not reproduce (141 vs 90); the missing negative tests | −2 |
| **total** | **64** |
