# Review of the night 2026-09-19 → 09-20 (Fable, written 2026-09-20 08:30 HKT)

Murat's instruction this morning, verbatim: *"close the lab i didnt wanted to
spent tokens, local simulation ewas wht i asked"*. The lab was stopped by its
STOP file at 23:51:51Z (exit reason recorded in the lock), the daily pass it had
dispatched was killed by PID, and **from here on no cloud call is made without a
per-run instruction from Murat.** DeepSeek is off. The local model server is the
only thing that may burn compute, and it burns no dollars.

## RESULTS SCOREBOARD (rule: this comes before anything else)

| what | number | source |
|---|---|---|
| paper equity, five readable books | hack1 93,673 · hack3 80,947 · hack4 89,362 · hack5 92,238 · hack6 84,686 = **$440,907** | `/v2/account`, 2026-09-20 00:10Z |
| paper equity, hack2 | **unreadable: HTTP 401** from Alpaca with the key Railway and `.env` both hold | same probe |
| decisions on disk (Decision Contract, chunk 18) | **0. `backend/data/optimus/decisions/ledger.jsonl` does not exist** | the step has never executed (below) |
| forecasts graded in the trailing 24 h | **0 of 24,839** records; 17,614 never graded, 7,219 inside their window | `decision_vs_reality_2026-09-20.json` |
| DeepSeek spent since the $50 top-up | **$2.08** by the provider (57.18 → 55.10); N9 alone $1.67 | `llm_cost_audit --snapshot` |
| N9 library autopsy | 3,050 candidate rows (3,048 CANDIDATE, 2 REFUSED), **0 measured** | `research_gym/library_candidates.jsonl` |
| L2 typing, local 7B | 3,689 rows in the night, 7,863 for the day, 1,436 refused (15.4%, REFUSED_SCHEMA); backlog 18,794 | `typed_events/2026-09-19*.jsonl`, `_cursor.json` |
| NN lab | ran ONCE, 09-19 06:01Z; 12 heads on held-out 2026-08, best IC 0.022; did NOT run overnight | `NN_lab_2026-09-19.json` |
| X_anon_gap (local) | raw −18.9%/yr net, masked −16.9%/yr net, gap −2.0 pp t −0.54 → ADOPTED MASKED; **both arms lose** | `X_anon_gap_run01.json` |
| fleet | hack3/4/6 **crash-looping since the 09-20 deploy**; hack2 never on the wrapper; hack1/5 fine | `railway logs` |

RESULT IMPROVEMENT: NONE. Nothing that ran last night changed a book, a
decision, or a claim.

## What ran (UTC, 09-19 → 09-20)

- 06:44–08:15 and 16:51–18:21: N9 on DeepSeek, two 90-minute boxes, 3,086
  calls, 2.78 M tokens in / 2.45 M out. Each box ended in TIMEOUT, which is the
  design (the candidates file and cursor persist; ~8,300 unwarned moves remain).
- 18:13: the lab's idle queue dispatched `L2_typed_events` (job box 120 min).
  The loop's own box is 60 s, so the loop thread was abandoned at 18:14 and the
  lab refused to re-issue it for the rest of its life. The job was killed at
  20:22 with its rows already on disk. **The GPU then sat loaded and idle from
  20:22 to 23:51.** Six queued jobs never ran (X2, E1, X4, L4, S1, retype v3).
- 21:35: social pull. YouTube 113 rows (the key works), Reddit refused by name.
- 22:16: news pull, 30 rows over 19 sources.
- 23:36: the daily pass dispatched, 66 minutes after its 06:30 local time
  (ticks were regular, 65 in 6.6 h; unexplained). Killed at 23:50 in the
  analyst-snapshot step on Murat's instruction.
- 23:51: lab exit, reason `STOP_file`.

## What broke, ranked by what it costs

1. **Three of six loops were dead containers, not sleeping shells.** hack3,
   hack4 and hack6 printed `market_window.sh: 37: set: Illegal option -` on
   every start. Every committed blob is LF; the Windows working tree was CRLF
   (`core.autocrlf=true`) and `railway up` ships the working tree, so dash saw
   `set -u<CR>`. Fixed in the execution repo (`0878516`: `.gitattributes`
   `*.sh text eol=lf`); hack2/3/4/6 redeployed and each printed
   `MARKET WINDOW supervisor: role=...` at 1–2 MB. **The 0 MB in
   `railway metrics` that yesterday's message called proof of sleep was proof
   of death. The proof of a live supervisor is its own first log line.**
2. **hack2's Alpaca key is dead on Alpaca's side** (401 on `/v2/account`;
   Railway and `.env` agree). Needs Murat: regenerate the hack2 paper key in the
   Alpaca dashboard, put it in `.env` and Railway as `AAT_HACK2_KEY_ID` /
   `AAT_HACK2_SECRET_KEY`.
3. **The idle GPU queue can run one job per lab instance.** Fix: dispatch the
   job as a detached child with a receipt-keyed gate (the shape `launch_driver`
   already has for the pass) and return from the loop at once.
4. **The Decision Contract has never fired.** The 09-19 pass process started
   at 04:08Z, before the step's commit at 05:25Z, and reported five steps; the
   09-20 pass was killed before reaching it. Until it runs, "the engine
   decides" is a sentence, not a row.
5. **Nothing is being graded.** 17,614 records never graded across the seven
   declared mechanisms; the feedback leg of the learning loop is absent, so
   nothing can learn.
6. **The cloud price table is wrong twice.** Our `deepseek-flash` price
   (0.169 / 1.285 $/M) is neither the peak (0.30 / 1.20) nor the off-peak
   (0.15 / 0.60) rate, and ignores the schedule: peak is 01–04 and 06–10 UTC
   on weekdays (09–12 and 14–18 HKT); everything else, and all weekend, is
   half price. The ledger said $3.12 for what the provider billed $1.67. Four
   ledger lines are unreadable (truncated concurrent appends), which makes
   every telemetry line say "LOWER BOUNDS".
7. **N9 pays for prose.** 87% of its cost is output tokens (~790 per
   candidate); the only fields the admission path reads are the two rule lists
   and one mechanism line. The admission path is local and free, so the value
   is in measuring the 3,050 candidates, not in buying more.
8. **A long-lived lab straddled a commit.** The 04:53Z instance imported the
   new `news_pull` against the old `news_registry` after chunk 20 T1 landed
   and raised on every news tick until it was replaced. The lab should record
   HEAD at start and exit `SOURCE_CHANGED` when it moves.
9. **The analyst snapshot is 2 h 35 m of the pass** (2,362 tickers, serial).
10. **L2 refuses 1 row in 7 on schema** at the 7B reader, the 09-13 pattern.
    Read the first flush before the next run.

## More efficient (in this order)

1. Monday 13:00Z: confirm `agent_loop` starts inside the window on every
   loop, and at 16:30 ET that the authority prints
   `SEAL AUTHORITY ALLOCATED day=2026-09-21`.
2. Idle queue → detached children (item 3). One evening of GPU is then six
   jobs, not one.
3. Reorder the pass so the contract runs before the 2.5-hour snapshot if its
   inputs allow, else box the snapshot at 60 minutes; either way the contract
   runs today.
4. A `grade_forecasts` step in the pass with a count receipt (item 5).
5. Price the ledger by UTC hour with the real peak/off-peak table; write it
   under a file lock. If cloud is ever authorised again, off-peak only. The
   HKT night is entirely off-peak.
6. Cut N9's schema to the rules; measure the 3,050 candidates locally with
   `library_measure_2006_2019.py` + `library_placebo_null.py` before any new
   candidate is bought.

## More profitable (what would actually move terminal wealth)

- The loop closing: a decision row every day, delivered to the executor,
  graded against reality. Everything above serves that; nothing last night
  did it.
- Monday's allocator run. Since 09-11 no weekday allocation exists, so every
  loop runs on budget 1.0 with `claimed=None`. If Monday prints REFUSED, the
  artery is the day's only job.
- The Kelly v2 book is live and accruing; it needs sessions, not code.
- Stop spending GPU on digest reads at 7B. X_anon_gap says both arms lose
  17–19%/yr net; put the GPU on the typing backlog and the E1 typed-event
  head, which is the design of record.
- hack2 restored, or declared retired; a book that answers 401 is neither.

## Needs Murat

1. hack2's Alpaca paper key (item 2).
2. Reddit script-app keys, when wanted.
3. The local-only policy is now the default; say "cloud ok for job X, $Y" per
   run to lift it.
