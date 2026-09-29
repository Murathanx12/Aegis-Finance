# Review: the contest desk (adversarial investor, 2026-09-29)

**Reviewed at commit `c0ac5310`:**

- Code: `scripts/contest_desk.py`, `scripts/contest_calendar.py`, `scripts/contest_rotation_sim.py`
  and `scripts/contest_book_odds.py` (the last came in with `b106cb58`).
- Documents: `docs/TRIALS/TRIAL-CONTEST-MAG-1-earnings-magnitude-beyond-implied.md` and
  `docs/research_notes/2026-09-29/contest_desk_2026-09-29.md`.
- Receipts under `backend/data/optimus/contest/`: `sim/sim_20260928T182048Z.{json,md}`,
  `calendar/calendar_2026-09-29*`, `dry_run/dry_run_2026-09-14_2026-09-25.json`,
  `earnings_history_global.parquet` and `prereg_prior_*`.

**Stance:** someone who wants this team in the top 10 of about 2,700, and who does not care how
good the plumbing looks.

**Already said in `REVIEW_2026-09-28_CONTEST_BOOK.md`, so not repeated here:**

- the top-10 line is soft (+20% to +55%);
- commissions and the fill convention are first-order;
- theme variance is shared with the field;
- MAX TAIL's trailing σ decays;
- register by Oct 4 at 11:59 am New York.

No production code was changed, and no LLM was used.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT | **NONE.** No edge was demonstrated. The desk is a well-built delivery vehicle for the previous review's EMR rule |
| best historical rule (zero-skill null) | ROT_ALL, next_open: P(> +40% rel) is **9.1%** averaged over the 11 seasons of 2024–26, and **4.8%** over the Oct seasons of 2019–25 (`sim_20260928T182048Z.md`) |
| the same rule, **actual signs** (never shown in the research note) | median realised relative result **+11.1%**. 20 of 31 seasons were positive and **5 of 31 were above +40%** (my read of `sim_20260928T182048Z.json`, `realised` field) |
| best forward paper | dry run Sep 14–25: −4.2 pp vs ACWI at next_open. This is one thin fortnight and shows nothing |
| confirmed dates | 64. All are JPX, all in Japan, all Oct 13–23, and 15 of them are liquid. The top ones are retailers (7453.T, 8267.T, 3086.T). **No US date is confirmed** |
| new defect found | **Asian report times are mostly placeholders read as real times.** 62% of Japanese stamps (13,298 of 21,458) sit at 00:00 UTC, which is 09:00 JST, and are classified INTRA. The desk therefore measures and trades the day *before* the reaction |
| independent selector count | unchanged; this book is a family of one |
| LLM spend | $0 |

**Score: 58 / 100.** The calendar honesty, the reused-ticker cut, the look-ahead fix and the tests
are good work. But the whole non-US leg rests on a timing bug. The owner-facing note also reports
the zero-skill null's negative median as if it were the rule's history, while its own receipt says
otherwise, and it never separates that gap from survivorship.

---

## Findings, ranked by money impact

### 1. Asian (mostly Japanese) earnings stamps at 00:00 UTC are treated as real times, so the desk holds the wrong sessions — HIGH

- **Claim** (`contest_desk_2026-09-29.md:146-149`): "An Asia-only rotation is not the route here…
  Only ~3% of Asian report stamps lack a time, so two-session holds do not explain it."
- **Evidence:**
  - `contest_calendar.event_sessions` (`contest_calendar.py:704`) calls a stamp UNKNOWN only when
    it falls at midnight in *local* time. `usual_timing` does the same (`:772`), and
    `dedupe_stamps` checks midnight in *New York* (`contest_desk.py:128`).
  - Yahoo writes "time not supplied" as **00:00 UTC**. The share of stamps at exactly 00:00 UTC is:

    | market | share at 00:00 UTC |
    |---|---|
    | JP | 62.0% |
    | ID | 17.4% |
    | CN | 9.4% |
    | TW | 9.4% |
    | EU | 8.8% |
    | KR | 4.8% |
    | HK | 4.1% |

    (`earnings_history_global.parquet`, 80,922 rows.)
  - Converted to local time these read as 09:00 JST / KST, or 08:00 in CN, TW and HK. In a sample
    of 3,000 UTC-midnight stamps the classifier labelled **all 2,324 Japanese ones INTRA** and all
    CN, TW, HK and ID ones BMO. **None became UNKNOWN.**
  - For INTRA or BMO the code sets pre = the session before the date and react = the date itself.
    Japanese companies report at or after 15:00 JST. Before Nov 2024 that was after the 15:00
    close, and it is still often at or after the 15:30 close. So for most Japanese events the
    "reaction" `r_c2c` is the day *before* the print plus the print day's close, and the move that
    actually matters (the next session) is never measured.
- **Consequence:**
  - (a) The sim's ROT_ASIA (0.2% at +40%) and the "Asia is not the route" conclusion rest on
    windows that miss the event, so they are unsupported rather than refuted. This matters because
    the owner trades Asia in his daytime, and the winners of 2023 and 2025 traded Asia.
  - (b) The Asian ranking column `trail_abs` averages the wrong windows.
  - (c) **Live money path.** `run_live` turns calendar timings into synthetic stamps
    (`contest_desk.py:669`), and a calendar timing of "INTRA" comes from `usual_timing` over these
    placeholders. Six of the 64 *confirmed* JPX rows already carry INTRA (7453.T, 6532.T, 3994.T,
    3349.T, 7599.T, 1407.T). The sheet would buy them the day before and, under `close` or
    `next_open` fills, sell them **before the print**. That is 20% of the book per slot paying
    costs for no event.
  - (d) The secondary measurement registered in TRIAL-CONTEST-MAG-1 grades non-US names with the
    same `event_sessions`, so its Asia leg would grade the wrong window.
- **Fix:**
  - Treat any stamp at exactly 00:00:00 UTC outside the US (and 00:00 in any zone) as UNKNOWN.
  - For JP, default an untimed print to AMC.
  - Re-run `build_events`, the sim and `prereg_prior_global_by_market.json`. If the Asian verdict
    changes, change the research note.
  - Add a test with a 00:00 UTC Tokyo stamp.
  - Because the trial is committed, add a dated amendment before Oct 12 that says the non-US
    timing was corrected before any data arrived.
- **Who decides:** the builder, before Oct 9, when the scheduled task starts writing sheets.

### 2. The owner sees "median negative for every rule". The rule's own history, with actual signs, has a median of +11% — HIGH (for the choice of book)

- **Claim** (`contest_desk_2026-09-29.md`, header and WHAT DOES NOT): "Every rule loses more often
  than it wins… direction is a coin flip. Every rule's median is negative."
- **Evidence:**
  - That median comes from the null: one random sign a day, applied to the book and to the
    benchmark (`contest_rotation_sim.py:118-123`).
  - The same receipt stores `realised`, the actual-sign path, for all 31 seasons. For ROT_ALL at
    next_open:
    - median **+11.1%**, mean +12.7%;
    - **20 of 31** seasons positive;
    - **5 of 31 above +40%**: 2020-Apr +44%, 2020-Jul +57%, 2025-Jul +89%, 2025-Oct +47%,
      2026-Jul +76%.
  - ROT_US at next_open has a median of +4.6%, with 5 of 31 above +40%. ROT_RANDOM at next_open
    has a median of −0.7%.
  - The same rule at `close` fills has a median of only +1.1%. So about 10 pp of the history sits
    between the pre-session open and the reaction-session open.
  - The research note's tables never print the realised column. The sim's `.md` prints only
    "realised > +20%".
- **Two readings, and the desk separated neither:**
  - (i) **An earnings-announcement premium plus a pre-print run-up.** Both are documented in the
    literature: stocks earn abnormal returns in announcement weeks, concentrated in high-attention
    names. That is a genuine positive drift, and it would favour this rule and the O2O fill
    beyond what the null says.
  - (ii) **Survivorship.** The US event pool comes from 8-K rows for **2,557 of 3,060 living names
    but only 47 of 1,784 delisted ones** (measured today from `edgar_8k/eightk_items.parquet` and
    `prices_deep`). The note's caveat puts the survivorship "outside the US" only
    (`contest_desk_2026-09-29.md:156`; `contest_rotation_sim.py:250`). That is wrong. The US pool
    is survivor-selected too, and high-|reaction| names are the ones most likely to die later.
- **Consequence:** the decision between EMR, MAX TAIL and doing nothing turns on this. If (i) is
  real, the rotation's top-10 odds are nearer 15% than 9%, its median is positive, and the O2O
  fill is worth fighting for. If (ii) explains it, the null is right. Right now the owner is told
  neither.
- **Fix:** see HIGHEST-EV EXPERIMENT. Re-score the realised path for 2024–26 from a
  non-survivor event source, and print realised beside the null in every table.
- **Who decides:** the builder runs it; the owner reads it before signing the utility line.

### 3. The live book will hold mostly vendor dates, while the sim held only actual print dates — MEDIUM

- **Evidence:**
  - Every simulated slot holds a real print (US dates are 8-K acceptance times, which are the
    release by construction).
  - The live calendar has **0 confirmed US dates**. It has 2,848 US VENDOR_ANNOUNCED, of which 2,143
    carry UNKNOWN timing across all markets (`calendar_2026-09-29.parquet`, status × timing).
  - An unknown time becomes an assumed AMC at the local close (`contest_desk.py:671`). If the print
    is really BMO, the desk buys at the reaction session and misses it.
  - The dry run used actual dates, and the note concedes it is "kinder than live".
- **Consequence:** each slot whose date or time is wrong is a normal 2–3% day instead of a 10–13%
  day. Variance per slot falls, and so does P(> +40%). The loss is unmeasured and it is one-sided.
- **Fix:** before Oct 12, measure it on Q3 2026. Take the Nasdaq calendar as fetched 7 days before
  each date (`nasdaq_days` cache), compare it with 8-K acceptance, and print the share of wrong
  date or wrong BMO/AMC. Apply that miss rate in the sim as slots that carry no event. The owner's
  `EVTS` check (checklist item 5) is the live remedy and is labour, not code.
- **Who decides:** the builder.

### 4. The rule ranks by trailing |reaction| while the option market's implied move sits one column over, unused — MEDIUM

- **Evidence:** `implied_move` is fetched only for the top 10 after ranking, and only for display
  (`contest_desk.py:460`). The trial is registered precisely because trailing |reaction| may add
  **nothing** beyond the implied move.
- **Consequence:**
  - For a variance-buying book the implied move is the best forecast of |reaction| available to
    anyone. It is also current: it knows about this quarter's guidance risk, a pending deal and so
    on.
  - Ranking on an 8-print trailing mean means holding names whose move the market expects to be
    small.
- **Fix:**
  - For US names, rank by implied move ÷ price, with `trail_abs` as the fallback.
  - Keep `trail_abs` ranked in a shadow column so TRIAL-CONTEST-MAG-1 can still be graded.
  - This changes the book and not the trial: the trial grades every eligible report whether held
    or not.
- **Who decides:** the owner, because it changes the frozen rule. It must be decided before Oct 12.

### 5. The headline pools the wrong seasons — LOW to MEDIUM

- **Evidence:**
  - The commit message and the scoreboard say "about 9–10%". That is the mean of **all four
    seasons** of 2024–26 (9.1%), and it includes Jul 2026 at 16.8%. Without Jul 2026 it is 8.3%.
  - The contest's own season (Oct, 2019–25) reads **4.8%**, and Oct 2024 and Oct 2025 read
    10.0% and 7.7%.
  - The "4.4% with commission" is 25 bps a side, which is an assumption (a paper contest has no
    market impact: the only cost is whatever TMSG charges).
- **Consequence:** the owner anchors on the top of the range.
- **Fix:** quote "5–9% (Oct 2019–25 to the 2024–26 regime); ±2× for the threshold".
- **Who decides:** the builder.

### 6. The sim's accounting inflates variance slightly — LOW

- **Evidence:**
  - A two-session hold (UNKNOWN timing) is booked as one step, and the next day's five new names
    are booked too (`contest_rotation_sim.py:102-121`, caveat at `:252`). Gross exposure on those
    days can reach 200%.
  - The non-US bars are unadjusted. A forward split in a held name is a ±50% "day" in HIVOL_BH,
    which inflates the comparator rather than the rotation.
  - The 20% cap is booked as 20% of *current* NAV. If Bloomberg means 20% of the $1M notional,
    the book cannot stay fully invested in 5 names once NAV rises, and that damps the path to
    +100%.
- **Fix:** cap the gross exposure at 100% in the sim. Model the $200k reading as a second column
  until TMSG Help answers the question.
- **Who decides:** the builder.

### 7. The sim never models the failure fill — LOW (already known, now missing from the tool)

- **Evidence:**
  - The previous review's NEXTOPEN case (decide at the close, fill the next open, lose the gap)
    gave 1.6%.
  - The new sim's `next_open` is the previous review's O2O (`contest_rotation_sim.py:12`).
  - Checklist item 4 maps "fills at the next open" to the `next_open` column, but the gap-lost case
    has no column.
- **Fix:** add the column. The Oct 12 test ticket must record whether a sell sent at 21:00 HKT
    fills at that session's open.
- **Who decides:** the builder.

---

## What book I would enter (maximise P(top 10) of ~2,700; relative to WLS; long-only; 5 × 20%)

**The rule:** EMR-US with O2O timing, ranked by the implied move.

1. **Daily.** Hold the five WLS names with the largest *option-implied* earnings move (above
   `trail_abs` where there is no chain) whose print falls between this session and the next open.
   Buy at the open of the session before the print and sell at the next open.
2. **Dates and times.** Use only dates cross-checked on `EVTS` that day. An untimed print is held
   two sessions.
3. **No empty slots.** On days with fewer than 5 prints, fill with the highest-implied-vol WLS
   names, not cash. Cash is lost variance.
4. **Weekly.** Read the leaderboard. Inside about the top 15: move to the five largest WLS weights
   and hold. Outside it: keep rotating to the end. A team in 300th place with a week left has
   nothing to protect.
5. **Asia.** Leave Asia out until finding 1 is fixed and the Asian sim is re-run. Then decide on
   the corrected number rather than on today's 0.2%.

**Why this book:**

- **Variance comes from events, not a theme.** Rank payoffs reward variance the field does not
  share, and five independent earnings gaps a day give a portfolio σ of roughly 5%/day without a
  theme's common factor. That common factor is what the field's AI, memory and miner books all
  hold.
- **The documented announcement drift is harvested only by the O2O timing.** The realised
  history puts ~10 pp between the O2O and close fills, and that is the one direction-positive
  effect on the table.
- **The implied move is a better and fresher estimate of the variance being bought** than an
  8-quarter average.
- **The fallback if TMSG fills the gap-lost way or charges commissions:** MAX TAIL with the
  fixes of the 2026-09-28 review (§7).

---

## WHAT WORKS

- **Calendar honesty.**
  - Only three statuses can render as confirmed.
  - `assert_calendar_honest` refuses violations.
  - A manual confirmation needs a URL.
- **Reused-ticker cuts before any feature**, and the look-ahead fix for future reports dated
  after a name's last bar.
- **The tooling.**
  - The per-season table, with no pooling.
  - The scheduled sheet with a STOP file.
  - `--preview` never read back as holdings.
- **The trial.** TRIAL-CONTEST-MAG-1 was committed before the window. It has an honest MDE and an
  UNDERPOWERED branch, and it grades every eligible report rather than the held ones.
- **The zero-skill null.** It is the right conservative tool for the *shape* comparison: the
  magnitude ranking against random ranking is 9.1% against 0.4%.

## WHAT DOES NOT

- **Non-US event timing is wrong for most Japanese and many other Asian prints** (finding 1). The
  Asian conclusions and the INTRA-labelled live rows inherit the error.
- **The owner sees only the null's negative median.** The realised history (+11% median, 5 of 31
  above +40%) is on disk and unreported, and its survivorship is mis-stated as non-US only.
- **The sim assumes perfect dates; live has zero confirmed US dates.** The miss rate is
  unmeasured.
- **The ranking ignores the implied move it already fetches.**

## HIGHEST-EV EXPERIMENT

**Re-score the realised (actual-sign) EMR path for the 12 seasons of 2024–26 from a
non-survivor event source.**

1. Take the Nasdaq daily calendar as it was published. `fetch_nasdaq_day` already works for past
   dates and caches to `calendar/nasdaq_days`. It lists companies that later died.
2. Take bars from `prices_deep` plus `bars_delisted`.
3. Compare three things:
   - the realised median and P(> +40%) against the survivor-pool realised numbers above;
   - the pre-session open→close and reaction-session open→close legs separately;
   - the implied-move ranking wherever a chain history exists.
4. As a by-product, measure the vendor-date miss rate (finding 3).

**Cost:** a few hours of builder time, $0, and no network beyond the Nasdaq calendar pulls
already allowed.

**What it decides:**

- whether the rotation is a zero-drift lottery (~5–9%) or a positive-drift one (~15%);
- whether O2O timing is worth a dispute with Bloomberg over fills;
- whether the owner should accept the rotation's ~−40% p05.

It must finish before Oct 9, when the scheduled task starts writing sheets.
