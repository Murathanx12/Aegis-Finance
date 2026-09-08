# BUILD 2026-09-07b — E1: the resumable news puller, and what E2 actually pulled

**Repo:** `aegis-alpha-terminal` (the terminal repo). The doc lives in
`aegis-finance` because the roadmap block does
(`ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 E). Written 2026-09-07, updated
2026-09-08 04:55 UTC after ~18 h of pulling. **No commit was made in either
repo** — six other agents' work is in these trees and the lead session owns
commits.

**Licence:** none — this is data movement. No LLM call, **$0 spent**. Nothing
deployed, sealed, ordered or pushed.

---

## 0. RESULT, first paragraph

**RESULT IMPROVEMENT: NONE** — no strategy moved, no book changed. What moved:

* a 134-month network pull can now be **killed and resumed** instead of lost,
  and the resume was exercised, not asserted;
* the number nobody could derive on 2026-09-07 is now derivable from files on
  disk, per month, while the job is still running;
* **158,614 new news rows** entered the corpus over 18 months of pulling, and
  2025/2026 coverage of the tradable universe went from **2.5% / 8.0% to
  43.7% / 46.1%**.

Two findings the receipts produced that no document held before:

1. **The 2015-2024 corpus covers 0.8%–1.2% of the tradable universe per year.**
   The pull that died at 03:18 was pulling the ~156-name `fleet` universe, so
   "83.6% done" described 83.6% of a job covering roughly one percent of the
   market. E3's ≥ 90% gate is not close and was never close; nothing had
   measured it.
2. **Finnhub's free `company-news` history stops at 2025-09.** Months
   2025-01…2025-08 returned `items_fetched: 0` with **zero** HTTP errors and
   zero refusals — the API answered and had nothing — and 2025-09 onward returns
   96–97% coverage of the 156 names. That boundary was assumed for a year and
   is now measured.

---

## 1. The four artefacts — formats and paths

New module `scripts/pull_journal.py`. Every long pull owns one directory under
`state/pulls/`:

```
state/pulls/<run_id>/cursor.json                     what is DONE and what is PARTIAL
state/pulls/<run_id>/run.log                         every line, timestamped, fsync'd
state/pulls/<run_id>/run.pid                         who owns the run right now
state/pulls/<run_id>/months/<YYYY-MM>.<leg>.json     a receipt PER MONTH
state/pulls/<run_id>/months/<YYYY-MM>.<leg>.superseded-N.json   a re-pulled month's old receipt
```

`run_id` is **derived from the job**, never remembered:
`run_id_for("news", start=…, end=…, universe=…)` →
`news_2025-01-01_2026-07-01_tradable`. A different window or universe is a
different id, so a resume is *run the same command again* — no flag, no id to
lose — and a 2015-2026 cursor can never be mistaken for a 2025-2026 one.

### `cursor.json`

```json
{
 "schema": "pull_journal/1",
 "run_id": "news_2026-07-01_2026-09-01_tradable",
 "created_at": "2026-09-07T10:31:08+00:00",
 "updated_at": "2026-09-07T11:23:50+00:00",
 "meta": {"start": "2026-07-01", "end": "2026-09-01", "universe": "tradable",
          "n_symbols": 12198, "legs": ["alpaca"], "months": 2, "max_pages": 40},
 "done":    {"alpaca": ["2026-07", "2026-08"]},
 "partial": {},
 "totals":  {"items": 60508, "stored": 55648, "duplicate": 4860, "http_errors": {"transport": 2}},
 "resumed": 1,
 "status": "complete"
}
```

* `done[leg]` gains a month **only when that month's receipt is on disk**, so
  "done" and "receipted" cannot drift apart.
* `partial[leg]` is the intra-month checkpoint — batch index for Alpaca, symbol
  index for Finnhub — written after **every batch** (Alpaca) and every ten
  symbols (Finnhub). The brief asked for at-most-one-month loss on a kill; the
  measured loss is **one batch**, i.e. 20 symbols × 1 month.
* Written `tmp` → `replace()`, so a kill mid-write cannot truncate it.
* An unreadable cursor **refuses**; it does not silently restart at month 0.
* A cursor whose `meta.start` disagrees with the command **refuses**.

### `run.log`

One timestamped line per event, `flush()` + `fsync()` on each — a killed
process must still have written the line that explains it. Also to stdout.

### `run.pid`

```json
{"pid": 134428, "started_at": "2026-09-07T10:31:08+00:00",
 "run_id": "…", "argv": [...], "log": "…", "cursor": "…"}
```

Removed **only on a clean exit**, so *its presence is the evidence a run was
killed*. On open, a pid file naming a **live** process is a refusal that names
the PID and says *"Kill THAT pid if you mean to take over — never by image
name."* A stale one is logged (`stale pid file from pid N … previous run did not
exit cleanly`), never silently overwritten. Liveness uses
`OpenProcess`/`GetExitCodeProcess` on win32 — **not** `os.kill(pid, 0)`, which
on Windows is `TerminateProcess` and would kill the process it is probing.

`python -m scripts.pull_journal` lists every run, PID and liveness, so *"what is
running"* is answerable from the filesystem, not from a lost scrollback.

### `months/<YYYY-MM>.<leg>.json`

A real one, the first month of the gate run:

```json
{"schema": "month_receipt/1", "leg": "alpaca", "month": "2026-07",
 "run_id": "news_2026-07-01_2026-09-01_tradable", "at": "2026-09-07T10:57:45+00:00",
 "window": ["2026-07-01", "2026-08-01"],
 "symbols_requested": 12198, "units": 610, "resumed_at_unit": 38,
 "items_fetched": 28738, "rows_stored_new": 26803, "rows_duplicate": 1935,
 "distinct_symbols": 4105, "symbols_with_any": 4105, "coverage_fraction": 0.3365,
 "first_observed_at": "2026-06-22T09:46:09Z", "last_observed_at": "2026-07-31T23:50:00Z",
 "pages_read": 846, "http_errors": {"transport": 2}, "n_refusals": 2,
 "refusal_sample": ["alpaca GLA..GLG 2026-07-01: GET /v1beta1/news -> transport failure: <urlopen error _ssl.c:993: The handshake operation timed out>", ...],
 "elapsed_s": 1476.1, "seen": {"AAPL": 41, ...}}
```

`http_errors` is bucketed **by status** (`429`, `403`, `500`, `transport`,
`timeout`, `other`) out of the refusal strings the broker/source layers raise.

---

## 2. The kill-and-resume gate — exercised, and the proof is in the receipt

Command, twice, unchanged — that is the point:

```
python -m scripts.news_backfill --start 2026-07-01 --end 2026-09-01 \
       --universe tradable --no-finnhub --no-rebuild-index
```

**Run 1** (`state/pulls/news_2026-07-01_2026-09-01_tradable/run.log`):

```
2026-09-07T10:31:08+00:00 OPEN pid=134428 run=news_2026-07-01_2026-09-01_tradable resumed=0 months already done=0 partial=none
2026-09-07T10:31:08+00:00 backfill 12198 names, 2026-07-01 -> 2026-09-01 (2 months), legs=['alpaca']
2026-09-07T10:31:08+00:00 alpaca leg: 12198 names, 2 months, 610 batches/month, role='hack1' (data endpoint, places nothing)
```

**The kill**, by the PID read out of `run.pid` — never by image name:

```powershell
$p = Get-Content '…\news_2026-07-01_2026-09-01_tradable\run.pid' -Raw | ConvertFrom-Json
Stop-Process -Id $p.pid -Force
```
```
PID from the pid file: 134428
KILLED pid 134428
cursor partial: {"alpaca":{"month":"2026-07","index":38,"at":"2026-09-07T10:32:58+00:00"}}
```

**Run 2** — identical command:

```
2026-09-07T10:33:09+00:00 stale pid file from pid 134428 (started 2026-09-07T10:31:08+00:00) -- previous run did not exit cleanly
2026-09-07T10:33:09+00:00 OPEN pid=133216 run=news_2026-07-01_2026-09-01_tradable resumed=1 months already done=0 partial={'alpaca': {'month': '2026-07', 'index': 38, 'at': '2026-09-07T10:32:58+00:00'}}
2026-09-07T10:33:09+00:00 alpaca 2026-07: RESUMING at batch 38
2026-09-07T10:57:45+00:00 alpaca 2026-07 [1/2]:  28738 items (+26803 new, 1935 known) 4105/12198 names  errors={'transport': 2}  1476.1s
2026-09-07T11:23:25+00:00 alpaca 2026-08 [2/2]:  31770 items (+28845 new, 2925 known) 4749/12198 names  errors={}  1540.1s
2026-09-07T11:23:50+00:00 CLOSE status=complete
```

**The receipt lines that prove it resumed at the cursor rather than from zero:**

| receipt | `resumed_at_unit` | meaning |
|---|---|---|
| `months/2026-07.alpaca.json` | **38** | finished by pid 133216, started by pid 134428 |
| `months/2026-08.alpaca.json` | **0** | started and finished by the same process |

The run then closed `complete` and **deleted its pid file** — the clean-exit
signal. `python -m scripts.pull_journal` reports it as `complete pid=None
alive=False done={'alpaca': 2}`.

Three further resume behaviours are pinned by test, not by this run: a finished
month stays finished across a reopen; a **live** owner is refused (exercised
against a real spawned child process, then terminated by its own PID); a dead
owner does not lock the run out.

---

## 3. `--universe tradable`: what it is and how big

New module `scripts/tradable_universe.py` → `state/tradable_universe.json`.

| leg | filter | names |
|---|---|---|
| CRSP `dsenames` (read-only from `aegis-finance/backend/data/optimus/wrds/bulk/crsp__dsenames.parquet`) | `shrcd in (10,11)`, `exchcd in (1,2,3)`, name interval overlaps 2015-01-01…2026-12-31 | **7,253** tickers / 6,477 permnos |
| Alpaca `/v2/assets` active `us_equity` | `tradable`, `exchange in {NYSE, NASDAQ, AMEX}`, dotted suffixes (`.WS`/`.U`/`.PR*`) dropped | 4,945 **additional** |
| **union** | | **12,198** |

Two honesty notes, both on the receipt:

1. **The local CRSP names table ends 2024-12-31.** A 2025-2026 window covered by
   CRSP alone is missing every company listed since — a hole in the direction
   that flatters coverage, because a missing name cannot be reported as
   uncovered. That is why the venue leg exists.
2. Alpaca's raw active list is 14,277 assets; unioning it whole added 9,936
   names, mostly ARCA/BATS ETFs and OTC symbols. That would have doubled the
   pull's cost while calling ETFs "common stock", so the venue leg is filtered
   to the venue-side analogue of `exchcd in (1,2,3)`.

`--universe tradable` **refuses** when the export is absent, naming the command
that builds it. There is no silent fallback to the 156-name `fleet` — that
fallback is how a whole-market claim gets made from a slice.

**Correction to the roadmap text:** `state/window_universe.json` **is present**
(`fleet` resolves to 156 names today). The 09-07 pull's problem was not a
missing window file; it was that `fleet` is 156 names.

---

## 4. Coverage-by-year ACHIEVED — the number E3 must be judged on

`python -m scripts.news_backfill --corpus-coverage` → receipt at
`state/corpus/corpus_coverage_by_year_2026-09-08.json`. Whole corpus,
`kind == "news"`, against the 12,198-name tradable universe. **Two jobs are
still running, so 2025 will keep rising.**

| year | news rows | months w/ rows | distinct symbols | in universe | **universe %** | Δ vs 2026-09-07 start |
|---|---|---|---|---|---|---|
| 2015 | 3,943 | 9/12 | 96 | 94 | **0.8%** | — |
| 2016 | 10,766 | 12/12 | 100 | 98 | **0.8%** | — |
| 2017 | 10,814 | 12/12 | 106 | 104 | **0.9%** | — |
| 2018 | 13,832 | 12/12 | 110 | 108 | **0.9%** | — |
| 2019 | 18,230 | 12/12 | 114 | 112 | **0.9%** | — |
| 2020 | 25,603 | 12/12 | 123 | 121 | **1.0%** | — |
| 2021 | 27,265 | 12/12 | 135 | 133 | **1.1%** | — |
| 2022 | 30,217 | 12/12 | 144 | 142 | **1.2%** | — |
| 2023 | 32,566 | 12/12 | 143 | 141 | **1.2%** | — |
| 2024 | 33,493 | 12/12 | 151 | 149 | **1.2%** | — |
| 2025 | 132,144 | 10/12 | 5,333 | 5,331 | **43.7%** | was 2.5% (24,221 rows, 7 mo) |
| 2026 | 100,619 | 8/12 | 5,619 | 5,617 | **46.1%** | was 8.0% (43,539 rows) |

**The gate must say which fraction it means.** Two readings differ by two orders
of magnitude and the tool reports both:

* `month_fraction` — months of the year with any row. A **pipeline-health**
  number; it is what catches the 03:18 death. 2015 is 75%; 2016-2024 are 100%.
* `universe_fraction` — names with ≥ 1 row that year. The **data** number, and
  the one a book needs, because a name with no news cannot be ranked by news.
  **0.8% – 46.1%.**

**Verdict for E3: NOT MET, on either reading, for any year.** Best is 46.1%
(2026). If the gate means `universe_fraction`, E3 stays blocked until a
tradable-universe Alpaca pull has run over **2015-2024**: 120 months at the
measured ~25 min/month ≈ **50 hours of wall clock**. That is a weekend job, not
a session job — and it is now resumable, which is what makes it possible at all.

---

## 5. Jobs — status at hand-off (2026-09-08 04:55 UTC)

`python -m scripts.pull_journal` re-derives this from disk at any time.

| run_id | leg | universe | window | PID | status |
|---|---|---|---|---|---|
| `news_2026-07-01_2026-09-01_tradable` | alpaca | 12,198 | 2026-07→2026-09 (2 mo) | — | **complete**, 2 of 2 months, pid file removed |
| `news_2025-01-01_2026-07-01_tradable` | alpaca | 12,198 | 2025-01→2026-07 (18 mo) | **50240** | **RUNNING, month 4 of 18** (2025-04, batch 344/610) |
| `news_2025-01-01_2026-09-08_fleet` | finnhub | 156 | 2025-01→2026-09 (21 mo) | **139180** | **RUNNING, month 14 of 21** (2026-02, symbol 70/156) |

Both running jobs were launched detached and **will outlive this session**.
Neither leg is finished and neither is reported as finished.

Totals written by the month receipts so far:

| leg | months receipted | items fetched | rows stored NEW | refusals |
|---|---|---|---|---|
| alpaca | 5 | 133,738 | **128,440** | 128 |
| finnhub | 13 | 35,577 | **30,174** | 126 |

Measured rates: Alpaca ≈ 0.42 batch/s ⇒ **~25 min/month over 12,198 names**;
Finnhub 1.1 s/call ⇒ ~5.5 min/month over 156 names. Remaining: Alpaca ~14
months ≈ 6 h; Finnhub ~7 months ≈ 40 min.

### The 17-hour DNS outage, and what the design did about it

Between **2026-09-07 11:45 and 2026-09-08 04:48 UTC this box lost DNS**
(`[Errno 11001] getaddrinfo failed`). Neither job died. Both logged the failure,
counted it by bucket, and carried on. The old puller would have produced
nothing — no log, no cursor, no partial receipt — and the morning would have
shown an empty terminal again.

What it cost, visible only because the receipts exist:

| receipt | refusals | result |
|---|---|---|
| `alpaca 2025-03` | 124 transport | 19,313 items / 3,181 names (vs ~27k / ~3,970 either side) |
| `finnhub 2026-01` | 123 `other` + 1 timeout + 1 `429` | 1,381 items / **29 of 156 names**, `elapsed_s: 61626.7` |

This exposed a real gap that the brief did not anticipate: **a month can be DONE
and NOT FULL**, and `is_done` would skip it forever. Added:

```
python -m scripts.news_backfill --start … --end … --universe … --list-degraded
python -m scripts.news_backfill --start … --end … --universe … --redo-degraded [MIN_REFUSALS]
```

`--list-degraded` prints, right now:

```
alpaca  2025-01:   2 refusals -- DONE but NOT full
alpaca  2025-03: 124 refusals -- DONE but NOT full
finnhub 2025-02:   1 refusals -- DONE but NOT full
finnhub 2026-01: 125 refusals -- DONE but NOT full
```

`--redo-degraded` un-marks those months so the next resume re-pulls them, and
**keeps the old receipt** as `<month>.<leg>.superseded-N.json` — a receipt that
is overwritten is a receipt that cannot be compared. It is opt-in, so an
ordinary resume never loops. **Whoever picks this lane up should run
`--redo-degraded` on both jobs after they finish**, then re-run
`--corpus-coverage`.

### Memory guard

The bar is ≥ 6 GB free before a heavy job. Free RAM was **4.6–5.2 GB** (three
other agents' python processes held 2.4 / 2.0 / 1.0 GB). I proceeded because
the puller is not a heavy job: **measured RSS 75 MB per process** — it streams
one batch at a time and never loads a shard. Stating the deviation rather than
hiding it. If the box tightens, kill the PIDs above, by PID.

### Two collectors at once — the index hazard, handled

`corpus._INDEX` is per-process and `flush_index()` writes the whole set, so
concurrent collectors end last-writer-wins: the loser's uids vanish from
`uid_index.json` while its rows stay on disk (documented in
`alpha/sources/corpus.rebuild_index`). The puller now rebuilds the index from
the shards at the end of every run — `rebuild_index_streaming()`, line-by-line,
seconds and megabytes rather than the ~437k dicts `corpus.read()` would
materialise — so whichever job finishes **last** leaves a correct index behind.
The two gate runs used `--no-rebuild-index`; both production jobs do not.

---

## 6. Tests — `python run_tests.py` only

| | suites | checks | result |
|---|---|---|---|
| **baseline**, before any edit (2026-09-07 18:29) | **80** | **3,697** | ALL PASS |
| **final** (2026-09-08) | **84** | **3,875** | **ALL PASS** |

Mine is **one** suite: `tests_smoke_news_pull.py`, **71 checks**. The other
three (`tests_smoke_horizon_remap`, `tests_smoke_premarket_off`,
`tests_smoke_session_fixture`, ≈ 108 checks) appeared in the tree during the
session from another writer and are not mine to claim.

**On `tests_smoke_test_isolation.py`.** Its assertion `no other suite touches
the guard` named my file, and the coordinator was right to stop me. I read it
first. The assertion is a *textual* one — it flags any `tests_smoke*.py` whose
source contains the guard's env-var name at all, because a test once spawned a
CHILD that reached the live venue and wrote 338 real rows, and only an env var
reaches a child. My suite **does not touch the guard**: it never sets, unsets or
reads it, and it makes no network call. The only occurrence was the variable's
**name in a docstring sentence**. So the correct fix was neither an allow-list
nor a silencing: the docstring was reworded to describe the guard without naming
it, and the assertion stands unmodified and unweakened. The guard was right; my
prose was the offender.

---

## 7. Handing the finance repo the re-join (described, NOT run — another repo's lane)

`aegis-finance/scripts/n4_event_table.py` already reads the terminal corpus
directly:

```python
TERMINAL_REPO  = Path(r"C:\Users\mrthn\aegis-alpha-terminal")   # READ ONLY
CORPUS_OBS_DIR = TERMINAL_REPO / "state" / "corpus" / "observations"
```

so **no export step is needed** — the 158,614 new rows landed in the same
`state/corpus/observations/<YYYY-MM>.jsonl` shards the build already reads, same
schema, same `kind == "news" AND tense == "past"` filter. The re-join is:

```bash
# in aegis-finance, AFTER the PIDs in §5 have exited
python -m scripts.n4_event_table --build --start-year 2015 --end-year 2026
```

Four things to check before believing the output:

1. **Wait for the pulls.** `python -m scripts.pull_journal` (terminal repo)
   prints `RUNNING` / `INTERRUPTED` / `complete` per run. A build started while
   the gap job is at month 4 of 18 reads four months of whole-market news and
   fourteen months of 156-name news, and **nothing in the table will say so**.
2. **Run `--redo-degraded` first** (§5) — four months are DONE but not full
   because of the DNS outage.
3. **Re-run `python -m scripts.news_backfill --corpus-coverage`** and quote the
   result *with which fraction it is* (§4). That is the E3 number.
4. **The symbol→permno join gets ~35× wider.** The news side carried ~150
   distinct symbols per year; it now carries 5,300–5,600 for 2025-2026,
   including delisted names and tickers reused by different companies.
   `n4_event_table` links through `crsp__stocknames.parquet` on an interval
   basis, which is the right instrument — but the `permno_link_method` census
   per year is now worth printing, because a ticker that fails to link is a row
   that silently leaves the table. Note also that CRSP names stop at 2024-12-31,
   so the 4,945 Alpaca-only names have **no permno at all** for 2025-2026.

---

## 8. What did not work / what I did not do

* **E2 is not finished and I do not claim it is.** Alpaca gap job: **month 4 of
  18, PID 50240**. Finnhub leg: **month 14 of 21, PID 139180**. Both running,
  both detached, both resumable if killed.
* **The 2015-2024 whole-market Alpaca pull was NOT launched.** ~50 h at the
  measured rate. Launching it beside three other jobs on a box with 4.6 GB free,
  unattended, at the end of a session is how the 03:18 failure happened. The
  command is `python -m scripts.news_backfill --start 2015-01-01 --end
  2025-01-01 --universe tradable --no-finnhub`; it resumes; it wants a
  deliberate attended start.
* **Finnhub's free history stops at 2025-09 — measured.** 2025-01…2025-08:
  `items_fetched: 0`, `http_errors: {}`, `n_refusals: 0` over all 156 names.
  2025-09: 5,688 items, 151/156 names (96.8%). `0 items with no errors` is *"the
  API answered and had nothing"*, a different sentence from a 429 — telling
  those apart is why the 429 retry and the per-status bucket exist. Establishing
  the boundary cost ~45 min of wall clock and nobody had ever written it down.
* **The Finnhub leg runs on `fleet` (156), not `tradable` (12,198).** At
  1.1 s/call the tradable universe costs **3.7 hours per month**. Finnhub cannot
  be the whole-market source; batched Alpaca/Benzinga is. Finnhub stays what it
  was built for: the small names Benzinga skips.
* **Four months are DONE but not full** (§5) and need `--redo-degraded`.
* **No commit, in either repo.** Every file touched is listed below.
* **`--months` is now a refusal, not a deprecation.** Exit 2 plus the
  explicit-date form. `blind_tournament.py`, `catalyst_horizon.py`,
  `corpus_digest.py`, `corpus_features.py`, `edgar_backfill.py` and
  `ir_backfill.py` import only `MURAT_NAMES` / `wide_universe` from this module
  and are unaffected — checked, and the suite agrees.
* **`alpha/` was not edited** (another agent owns it), so the streaming index
  rebuild lives in `scripts/news_backfill.py`. If `alpha/sources/corpus.py` ever
  gains a streaming rebuild, delete mine in favour of it.
* **An off-by-one I introduced and fixed before it shipped:** `iter_months`
  yields whole calendar months and stops on the end date's own month, so
  `--end 2026-09-01` originally produced a third month whose clamped window was
  zero-length. It would have spent 610 calls and written a receipt reading
  "0 items, 0 symbols" for 2026-09 — a coverage hole invented by an off-by-one.
  Months are now filtered on `m0 < end` and the last month's window is clamped.

### Files touched (all in `aegis-alpha-terminal`, none committed)

```
scripts/news_backfill.py                              rewritten
scripts/pull_journal.py                               new
scripts/tradable_universe.py                          new
tests_smoke_news_pull.py                              new (71 checks)
tests_smoke_test_isolation.py                         NOT modified (docstring in my suite was)
state/tradable_universe.json                          new export (12,198 names)
state/pulls/**                                        three run dirs: cursors, logs, pid files, 18 month receipts
state/corpus/observations/*.jsonl                     +158,614 news rows
state/corpus/corpus_coverage_by_year_2026-09-0{7,8}.json   new receipts
```

`scripts/window_universe.py` was **not** changed: the file it writes exists and
its 156-name output was never the bug — pointing the pull at it was.
