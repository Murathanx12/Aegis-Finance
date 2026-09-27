# Rehearsal 2026-09-28 — Monday entry of ~300 frozen books, on copies

**RESULT IMPROVEMENT: NONE** (this is plumbing: it changes what Monday *says*,
not what any book earns). Licence `PRODUCT_EXPERIMENT`, $0 LLM, no network, no
orders, no browser, no factory run. No frozen book, ledger, or grading rule was
changed.

## What was rehearsed

A scratch world under `backend/data/optimus/_rehearsal_2026-09-28/` (gitignored)
holds COPIES of `prices_deep/bars.parquet`, `bars_delisted.parquet`,
`prices_2025_26/bars.parquet`, `bars_forecast_only.parquet`,
`llm_portfolio/global_bars.parquet`, `llm_portfolio/books.jsonl`,
`predictions.jsonl` and `bridge/`. The code was pointed at it with
`AEGIS_DATA_DIR=<scratch>/data` (the drivers refuse to run otherwise);
`paper_accounts_roi` and `bridge_report` root their output paths on the repo
(they ignore `AEGIS_DATA_DIR`), so the drivers re-pointed those module
constants in-process and wrote to `<scratch>/out/`.

Only `<scratch>/out/` (receipts: leaderboards A/B for both days, the
roi/bridge/forecast/health results, rendered `PAPER_ACCOUNTS.md`, `BRIDGE.md`,
README section) is left on disk. The world copies and the three driver scripts
were removed from the repo tree after the run: while they sat under
`backend/data/optimus/` (gitignored or not) they turned three repo-scanning
guards red on the local suite — `test_frozen_path_family` (driver `.py` files
rooted on `__file__`), `test_signal_reachability` (unclassified modules) and
`test_forecast_populations` (an unregistered `predictions.jsonl`). A scratch
world for a rehearsal belongs outside the repo; the builder is ~130 lines
(seeded synthetic bars on copies) and rebuilds the world in 10 s.

Two synthetic sessions (2026-09-28, 2026-09-29; seed 20260928) were appended
for every symbol with a bar in the last three days of each panel (3,055 US
symbols, 25 global): open = last close × (1 + N(0, 0.5%)), close = open ×
(1 + N(0, 1.5%)), volume = last volume. Four awkward names, each held by real
frozen books:

| case | name | holders | what was written |
|---|---|---:|---|
| halted | AXTI | 24 | no 09-28 bar; normal 09-29 bar |
| NaN open | CLYM | 26 | 09-28 open = NaN, close valid |
| split, adjusted | WOLF | 19 | 2-for-1 on 09-28, history re-based ×0.5 (what `pull_bars_refresh` writes with `adjustment=all`) |
| split, UNADJUSTED | DELL | 28 | 09-29 bar halved, history untouched (a missed re-adjust, or the global cache: `auto_adjust=False`) |

Then, on the copies: `LP.leaderboard` for every book with `today=09-28` and
`today=09-29` (bars loaded exactly as `scripts.llm_portfolio grade --no-pull`
loads them); `paper_accounts_roi.collect_llm_books` + `attach_spy` +
`render_markdown`; `bridge_report.report` + `readme_section`;
`forecast_grader.grade_due` for 09-28 then 09-29; `system_health.run` on the
scratch dir. Variant B added a synthetic URTH (09-28/29) to the global cache, as
`grade` with its yfinance pull would have it.

## Counts

Ledger: 308 lines = 307 books + 1 void row. 62 parents (47 personal, 11
competition, 4 `__control`) + 245 twins. **No duplicate ids or names; every book's
weights sum to 1 ± 0.01; no orphan twin; every book enters at 2026-09-28**
(asof 09-25: 122, 09-26: 120, 09-27: 65). Voided: 1
(`lib_mom_12_1_liqw_sealed_2026-09-26`) — skipped by the grader, listed under
`voided_before_entry` by the leaderboard, `paper_accounts_roi` (VOIDED) and
`bridge_report`; its 4 twins are graded (by design: "its twins stay").

| | `--no-pull` (A) | with URTH (B) |
|---|---:|---:|
| graded objects | 306 | 306 |
| OK | 293 | 303 |
| REFUSED | 13 (10 `urth` twins, 3 all-ETF `sector_etf` twins) | 3 (all-ETF `sector_etf`) |
| PENDING | 0 | 0 |
| OK with **no benchmark** | 44 (11 competition parents + 33 twins; URTH absent) | 0 |
| OK but graded on < 50% of their weight | 18 (sector_etf twins: BETZ BOTZ GRID IGV ITA LIT QTUM URA XBI XLB absent) | 18 |
| `deferred_entry` (09-29 grade) | 24 (AXTI) | 24 |
| `unpriceable_why` | NO_BARS 99 · ENTRY_OPEN_NOT_FINITE 26 · NO_BAR_ON_OR_AFTER_ENTRY 2 (NUVL) | same |
| `suspect_splits` (09-29 grade) | 28 (DELL, 2-for-1) — WOLF adjusted: 0 | same |
| entry at a price other than the 09-28 open | 0 unnamed (AXTI: named deferred; CLYM: named, excluded) | |

By kind at 09-29 (A): personal 46/46 graded vs SPY, control 4/4, competition
**0/11** (no URTH). `paper_accounts_roi` (after fixes): 293 LIVE, 13 UNPRICED,
1 VOIDED, 0 PENDING. `bridge_report`: 31 lib/probe rows, 31 forward-graded, the
voided book listed, 5 leads with their `matched_random`/`ranks_k1_2k`/`iwm`
twins compared. `forecast_grader`: 40 resolved on 09-28 (investigator
evidence_v2), 259 on 09-29, 0 `NO_BAR_FOR_RESOLUTION_DATE`, 0 errors.
`health`: the `book_grader` probe reads the paper_books scoreboard and
`strategy_library` leaderboards — it cannot see these 300 books at all.

**Runtime and memory** (one process, Windows working set):

| step | before | after |
|---|---:|---:|
| load bars as `grade` does (deep + delisted, 8.6M rows → 2.1M) | 5 s, **peak 3.7 GB** | same (not my file) |
| leaderboard, 306 grades | **126 s** | **2.2 s** |
| `bridge_report.report` (31 books, 2 sessions) | **69 s** (grows × sessions) | **6.5 s** |
| forecast grader | 6 s | 6 s |

## Defects

Fixed in this commit (tests: `backend/tests/test_llm_portfolio_grade.py`, 9
new, all fail on the old grader; `backend/tests/test_paper_accounts_roi.py`, 4 new):

1. **Halted name entered at its next open with nothing said.** `grade` now
   writes `deferred_entry` (ticker, entry session, the session it actually
   entered, why) and `leaderboard.deferred_entry`. `today` also bounds the
   name's own bars, so a grade "as of X" equals the grade on a panel ending at X
   (it used to find a post-X bar for the deferred entry).
2. **NaN open / no bars were one undifferentiated `unpriceable` list.** Now
   `unpriceable_why` = `NO_BARS` | `NO_BAR_ON_OR_AFTER_ENTRY <d>` |
   `ENTRY_OPEN_NOT_FINITE on <d>`. Never priced at 0 or the prior close (it
   never was; now it says why).
3. **An unadjusted split after entry graded as −50% silently.**
   `suspect_splits` names every overnight gap within 2% of a split ratio (2…10,
   1/2…1/10, 3:2, 2:3) on a held name; the number is NOT rewritten (a real
   −50% biotech gap looks the same). Global-cache names are unadjusted by
   design, so this is where it would bite.
4. **Benchmark absent (URTH under `--no-pull`) left `vs_benchmark` None on an
   `OK` grade with no word.** Now `benchmark_missing` + `why` on the grade,
   `n_benchmark_missing` / `benchmark_missing_symbols` on the leaderboard.
5. **A book whose every name was unpriceable but carried a CASH line graded as
   a cash book.** Now REFUSED like "nothing priced" (a book frozen as all cash
   is still graded).
6. **126 s per leaderboard**: every `grade()` re-grouped ~2M rows. Memoised on
   the frame's identity (weakref; dropped with the frame). 126 s → 2.2 s;
   `bridge_report` (which calls `grade` per book per session) 69 s → 6.5 s.
7. **`leaderboard(today=X).bars_through` printed the panel's newest date**, not
   X. Plus `status_counts` and a `refused` list on every leaderboard.
8. **`paper_accounts_roi`: a REFUSED book printed "PENDING (entry
   2026-09-28)" after entry** (13 rows). Now `UNPRICED` with the grader's why.
9. **`paper_accounts_roi`: every llm book's Monday was compared with SPY =
   0.0.** Its SPY base was `inception_close` with inception = the entry date,
   which drops the entry session the book was bought into at the open. The SPY
   leg is now the grader's own open-to-close leg (`spy_base:
   grade_entry_open`); a URTH-benchmarked book gets no SPY leg on an unmeasured
   window (`benchmark_not_spy`, note carries its `vs_benchmark`).
10. **`paper_accounts_roi`: with a stale leaderboard every book stays "PENDING"
    forever** — and nothing schedules the grader (below). After the entry date,
    a book absent from a board that does not reach its entry is now `UNGRADED`
    with the command to run. `build(llm_today=...)` pins it in tests.

Not fixed in that commit (not mine to change, or a rule) -- **each item now
carries its status; the fixes are in the next section**:

- **[FIXED 09-27, below]** **NOTHING SCHEDULES THE BOOK GRADE.** `daily_pass` has no book-grading step
  (its grading step is the forecast grader); `scripts.llm_portfolio grade`,
  `paper_accounts_roi` and `bridge_report` have no caller besides a human. A new
  daily-pass step needs a `DAILY_PASS_STEP_BOX_S` entry in `backend/config.py`
  (import-time assert), outside this change. Owed: a `llm_books` step after
  `grade_forecasts`, out of process (the 3.7 GB peak returns to the OS), box ~300 s.
- **[FIXED 09-27: pulled, not assumed]** **`--no-pull` cannot grade competition books or all-ETF twins**: URTH and 10
  sector ETFs are in no local panel (`paper_accounts_roi` tells the reader to
  run `--no-pull`). Pull mode fetches them from yfinance (unadjusted, and a
  symbol whose yfinance series reaches a later date than Alpaca switches vendor
  for its whole history). Owed: add URTH + the 10 ETFs to `pull_forecast_bars`
  or the refreshed US panel.
- **[DECIDED 09-27: rule v2 from 2026-09-28]** **Rule question, written down, not changed:** the comment in `grade` says an
  unpriceable name is "NOT silently re-weighted", but `gross = tot / priced_w`
  does exactly that — 18 `sector_etf` twins are graded on 7–48% of their weight
  scaled up to 100% (e.g. `pers_revision_flow_leaders_2026-09-25__sector_etf`
  on 7.4%). `weight_priced` names it. And a halted name is deferred to its first
  open while a NaN-open name is excluded for good; one of the two is the rule.
- **[FIXED 09-27]** `scripts/llm_portfolio._us_bars` reads both deep panels whole (8.6M rows, peak
  3.7 GB) and filters after; `bridge_report.load_bars` pushes the filter into
  the read.
- **[FIXED 09-27 for the data paths]** `paper_accounts_roi` and `bridge_report` root paths on the repo, not
  `config.OPTIMUS_LEDGER_DIR` (defect family #14 shape). `FAMILY_ORDER` has no
  `llm_portfolio:control`; today every control is a `lib_` name, so none is lost.
- **[OPEN]** The leaderboard's `vs_<twin>` columns cover `ew / sector_etf /
  random_same_band / ai_only` only; the leads' `matched_random`, `ranks_k1_2k`,
  `iwm` comparisons live in `bridge_report` alone.
- **[MARKED 09-27, neither voided]** Two parents hold identical positions: `lib_mom_12_1_q_2026-09-26` and
  `lib_mom_12_1_2026-09-26` (one bet, two rows).
- **[OPEN]** `forecast_grader` has no split guard; it relies on `pull_bars_refresh`
  re-adjusting (it does, by design). No due forecast in the rehearsal crossed
  the DELL split.
- **[FIXED 09-27]** The `book_grader` health probe cannot see llm_portfolio grading.

## Fixed after the rehearsal (2026-09-27) -- Fable's adjudication, all seven items

Licence `PRODUCT_EXPERIMENT`, $0 LLM, no orders, no browser. Tests offline and
synthetic (listed at the end of this section).

1. **The grade has a scheduled caller.** `scripts/daily_pass.py` gains three
   steps AFTER `bars_refresh` and the forecast/promise graders and BEFORE
   `coverage` / `scoreboard` / `health`: `grade_books`
   (`python -m scripts.llm_portfolio grade --json`, PULL mode), then
   `paper_accounts` (`python -m scripts.paper_accounts_roi --no-broker --json`),
   then `bridge_report` (`python -m scripts.bridge_report report --json`). Each
   runs OUT of process (the child is killed by its own handle at its box - 60 s),
   has a box in `config.DAILY_PASS_STEP_BOX_S` (900 / 600 / 600 s; the sum of
   all boxes is now 14,400 s, under the 6 h stale-sibling bound and the lab's
   21,600 s driver box, both pinned by tests), writes its receipt path on its
   row (`receipt_path`), and NEVER fails the pass: a crash is an `error` row, a
   failed child a `refused` row naming the rc and stderr tail, and either makes
   the `book_grader` health row STALE in the same pass (the pass hands its rows
   to the probes, whose own receipt is written before the pass's).
2. **Benchmarks and ETFs are pulled, not assumed.** `grade` PULLS
   `config.LLM_BOOK_REQUIRED_SERIES` (URTH, BETZ BOTZ GRID IGV ITA LIT QTUM URA
   XBI XLB, SPY IWM SMH MTUM) plus every book's benchmark and ticker through
   `global_prices.ensure`, from 120 days before the earliest book's as-of. A
   series with no bars after the pull, or whose newest bar is behind SPY's, is a
   NAMED refusal on the leaderboard (`series_refusals`) and on the pass row
   (`SERIES URTH: ...`). **And the pull's `today` is the day after the last
   CLOSED XNYS session** (`scripts.llm_portfolio.pull_today`): `ensure` keeps
   only bars dated before its `today`, and with the UTC date the 22:30 UTC pass
   would have dropped the session that closed at 20:00 UTC -- every
   URTH-benchmarked book and every ETF-only twin would have been one session
   behind the SPY books, and the competition books PENDING on Tuesday morning.
   `paper_accounts_roi` no longer tells a reader to use `--no-pull` (its source
   line names the pass's `grade_books` step; `--no-pull`'s help says it is for
   offline rehearsals only).
3. **One missing-name rule, versioned** (`config.LLM_BOOK_GRADE_RULE_V2_FROM =
   "2026-09-28"`, decided by the ENTRY SESSION, stamped as `grade_rule_version`
   on every grade and leaderboard row, counted in `grade_rule_versions`).
   Version 2: a halted name and a NaN open are the SAME case -- the name enters
   at its first valid open on or after the entry session (never after the
   grade's `today`), and until then its weight is cash at 0%; the NAV divides by
   the book's whole declared weight, never by the priced part, so nothing is
   re-weighted. `weight_priced` = (declared cash + names that have entered) /
   declared weight (declared cash counts as priced: a book frozen 60% cash is
   not under-priced), beside `weight_in_market` and `weight_waiting_in_cash`,
   and per horizon cell. On or after its 5th session a book with
   `weight_priced < 0.5` is `REFUSED_UNDER_PRICED` (no `to_date`, no NAV), and
   `paper_accounts_roi` shows it as UNPRICED with its `weight_priced`. A book
   whose every named position is still waiting is REFUSED as before (fix 5).
   Entry cost is charged per name from the cell in which it enters. **Version 1
   (entry before 09-28) is unchanged, byte for byte in its arithmetic**; its
   code comment now says what it does ("v1 DOES re-weight: gross = tot /
   priced_w"). All 306 current graded objects enter 2026-09-28, so every one of
   them is v2 (`grade_rule_versions: {"2": 306}` on the offline check below);
   no published v1 number exists among them.
4. **Health sees the books.** `system_health.p_book_grader` now reads, besides
   the paper-book scoreboard: the newest `llm_portfolio/leaderboard_<day>.json`
   -- STALE when `bars_through` is MORE than 1 session behind the last closed
   session (one missed pass tolerated), and STALE when a book past its entry is
   on no board (UNGRADED); its detail always names `PENDING n, UNGRADED n,
   REFUSED n, OK n` -- and the pass's `grade_books` / `paper_accounts` /
   `bridge_report` rows (refused / error / timeout -> STALE, by name). Live read
   today: `leaderboard_2026-09-26.json bars through 2026-09-24, 1 session behind
   2026-09-25; PENDING 182` -> ALIVE.
5. **Bars load.** `scripts/llm_portfolio._us_bars(symbols)` pushes the
   held-symbol filter into the parquet read (pyarrow `filters=`), then applies
   `xs_ranker.load_bars`'s own first-occurrence dedupe and sort. Measured on the
   real panels, one process: **full load then filter: 3.5 s, peak working set
   3.94 GB; filtered read: 1.1 s, peak 1.38 GB**; both 2,119,049 rows. A
   synthetic test pins frame equality with the full load for the held symbols.
6. **Duplicates.** `bridge_report.identical_holdings` groups non-twin,
   non-void books with the same names at the same weights; the only group in
   the ledger is `lib_mom_12_1_2026-09-26` = `lib_mom_12_1_q_2026-09-26`. The
   bridge receipt carries `identical_holdings` and each row
   `identical_holdings_with`; `docs/BRIDGE.md` (report and re-render) marks the
   row "identical holdings to `...`, one observation" and prints a line saying
   both stay and count once. Neither is voided.
7. **Paths from config.** `paper_accounts_roi` (`OUT_DIR`, `LLM_DIR`,
   `DECISIONS_DIR` from `config.OPTIMUS_LEDGER_DIR`; `MURAT_BOOK` from
   `config.DATA_DIR`) and `bridge_report` (`LIB_DIR`, `BRIDGE_DIR`, `PLAN_DIR`,
   `STRUCT_DIR` from `config.OPTIMUS_LEDGER_DIR`) now follow `AEGIS_DATA_DIR`
   like the grader. The rendered documents stay in the repo's `docs/` unless
   `paper_accounts_roi --docs-dir <dir>` / `bridge_report report --out-md
   <file>` is given, so a rehearsal needs no in-process redirection.

Tests: `test_daily_pass.py` (the three steps run in order after
`bars_refresh`, before `health`; each can raise or refuse and the pass goes on
and exits 0; series/book refusals named; the child runner parses the summary
and names a non-zero rc, a timeout and a missing summary; PULL mode, never
`--no-pull`), `test_llm_portfolio_grade.py` (v2: halt and NaN open deferred to
the same open; cash not re-weighted where v1 scales the remnant;
`weight_priced`; `REFUSED_UNDER_PRICED` on session 5 and not on session 4; a
60%-cash book never under-priced; v1 unchanged on a 09-18 entry; every row
carries its version), `test_llm_portfolio_cli.py` (new: filtered load equals
the full load; required series pulled and a failed one named; `pull_today`;
a stale series named), `test_system_health.py` (STALE at 2 sessions behind,
ALIVE at 1 and 0, UNGRADED books, a failed book step), `test_paper_accounts_roi.py`
(`REFUSED_UNDER_PRICED` -> UNPRICED; no `--no-pull` advice; config paths),
`test_bridge_report.py` (identical holdings marked in report and re-render;
config paths).

**Not done here:** `ensure` still pulls every book ticker from yfinance once
per UTC day (unadjusted; a symbol whose yfinance series reaches a later date
than the US panel switches vendor for its whole history, as before). The
`vs_<twin>` columns and the `forecast_grader` split guard are still open.
`paper_accounts_roi` and `bridge_report` write tracked files
(`docs/PAPER_ACCOUNTS.md`, `docs/assets/paper_accounts_roi_<day>.png`,
`docs/BRIDGE.md`) every morning; the pass does not commit them.

## When Monday's first grade is written, and by whom

**Caller.** The daily pass fires at **06:30 HKT** from two places: the
Windows scheduled task **`AegisDailyPass`** (DAILY 06:30; `schtasks` shows Last
Run 27/9/2026 06:30:01, Last Result 0, Next Run 28/9 06:30; the 09-26 and
09-27 receipts both started at 22:30:13 UTC) and the always-on
lab's `daily_pass_dispatch` loop (`LAB_DAILY_PASS_LOCAL_TIME = "06:30"`, which
logged `ALREADY_RAN_TODAY` and stood down on 09-27). Whichever starts first
writes the receipt; the other reads it and stands down. On the last two days
that was the scheduled task. 06:30 HKT is **22:30 UTC / 18:30 ET the previous
calendar day**, i.e. 2.5 h after the 16:00 ET close.

**Monday 2026-09-28, 06:30 HKT** (Sunday 18:30 ET): bars through Fri 09-25;
`grade_books` writes `leaderboard_2026-09-27.json` (UTC day) with every book
PENDING -- a `nothing_to_do` row, which is correct.

**The first real grade: Tuesday 2026-09-29, ~07:50 HKT (Monday 09-28 ~23:50
UTC, 19:50 ET), file `backend/data/optimus/llm_portfolio/leaderboard_2026-09-28.json`**
(named by the UTC day). Arithmetic from the 09-27 receipt: the pass started
22:30:13 UTC, `bars_refresh` pulls Monday's bar first (84 s on a no-new-data
day; longer with a day to add), `news_pull` took 23.5 min, `analyst_snapshot`
55 min (its budget), the rest seconds -- `grade_promises` finished at 23:50:34
UTC. `grade_books` starts there and has a 900 s box, so the file lands between
**~07:51 and 08:05 HKT Tue 09-29** at the latest; `paper_accounts` and
`bridge_report` follow within their 600 s boxes. Expected content: bars through
2026-09-28, h=1 priced (entry open -> close), 306 graded objects, 0 PENDING,
URTH and the ten ETFs priced through 09-28 by the pull (no `series_refusals`),
`grade_rule_versions {"2": 306}`.

If the machine is off or asleep at 06:30, the lab dispatches the pass when it
next runs (no upper bound on the window), and the grade follows ~80 min later.

## Expected Monday numbers

(Real bars: no AXTI/CLYM/DELL artefacts. Books frozen with `asof` ≤ 09-27 enter
at the 09-28 open; a book frozen with asof 09-28 would enter 09-29.)

- **After the 09-28 close** (bars through 09-28, e.g. HKT Tue 06:30 pass +
  a grade): 306 graded objects. With `grade` (pull): expect **306 OK, 0
  REFUSED, 0 benchmark-missing**, h=1 priced for all (h=1 is the entry
  session's open→close; it does NOT need 09-29). With `--no-pull`: **293 OK, 13
  REFUSED, 44 without a benchmark**, `NUVL` unpriceable in 2 books.
- **After 09-29**: the same set, `to_date.sessions = 2`; h=5 first prices after
  the 2026-10-02 close. Forecasts: 40 due 09-28, 259 due 09-29, 159 due 09-30
  (MU prints 09-30; those resolve from the 09-30 bar).

## The three checks for Monday evening (after the 16:00 ET close = 04:00 HKT Tue)

(Since 09-27 the pass RUNS all three at ~07:50 HKT Tue; these are what to READ
on its receipt and outputs. Running them by hand earlier is still fine: the
grade is idempotent per UTC day.)

1. The pass's `grade_books` row (or `python -m scripts.llm_portfolio grade`, pull, NOT `--no-pull`), then read
   `llm_portfolio/leaderboard_2026-09-28.json`: `bars_through == 2026-09-28`, `series_refusals == []`,
   `status_counts` has no PENDING, `refused == []`, `n_benchmark_missing == 0`,
   and read every `deferred_entry` / `suspect_splits` / `unpriceable_why` row by
   name.
2. `python -m scripts.paper_accounts_roi --no-broker`: 0 PENDING and 0 UNGRADED
   among llm rows; `spy_base` is `grade_entry_open` on SPY books, so "vs SPY"
   is the same window as the book (not SPY = 0.0).
3. The daily pass `grade_forecasts` row: `newly_resolved` ≈ 40 on the pass after
   09-28 and ≈ 259 after 09-29, with `NO_BAR_FOR_RESOLUTION_DATE: 0` — and
   `python -m scripts.bridge_report report` showing 31 forward-graded rows.
