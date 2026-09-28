# REVIEW 2026-09-28 — Lane M (measurement honesty), by an adversarial investor

Reviewer: Opus 5.5, acting as a sceptical quantitative investor. Written 2026-09-28, about 06:45Z,
**before the 13:30Z US open**. Scope: the uncommitted lane-M build described in
`docs/research_notes/2026-09-28/lane_m_build_2026-09-28.md`, the registration
`docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md` (committed in `b1010061`,
14:35:09 +0800), and every receipt they cite.

What I did:
- Read the code and the receipts.
- Re-derived numbers with read-only pandas over the committed and on-disk receipts.
- Ran the three allowed test files.

What I did not do: change any existing file, touch git state, call a broker or an LLM, or run the
factory.

**Result improvement: NONE.** This lane removes flattering readings; it adds no edge.

---

## Verdict in three sentences

1. The build is honest in its arithmetic. It reproduces the reference board to the last digit,
   and it correctly finds that "39 priced / −1.34%" is the broker-included scope, not a stale
   number. But its verdict rule is kinder than the brief's, and its one forward trial's error bar
   is about 1.7 times too narrow.
2. Every one of the four "leads" is the same momentum bet: their monthly returns correlate
   0.83-0.97, and `disp_short_avoid` correlates 0.97 with `mom_12_1_q`. On the calendar-neutral
   book, none of the four beats its matched twin distinguishably in 2024-26 (t 0.61-1.34,
   MDE ≈ 2.3-2.4%/mo).
3. Two things must happen before 13:30Z today:
   - Commit the trial's frozen inputs, which are currently untracked.
   - Commit a dated amendment that estimates the pooled correlation on the same twin type the
     trial reads.

   Otherwise the pre-registration does not bind what it claims to bind.

## The ONE number the project should quote for its best rule

> **`mom_12_1_q`, calendar-neutral (one third on each quarterly calendar): +1.20% a month over its
> matched twin across 2017-26.** Its t is 2.49 on 38 quarterly blocks. In 2024-26 it is +1.00%/mo,
> t 1.18, MDE 2.37%/mo, which is not distinguishable from zero. As a return: **+661% since 2020**
> (SPY +162%), **not +1,323%**.

Source: `strategy_library/calendar_offsets_2026-09-28T055923Z.json` →
`results.mom_12_1_q.tranche_average`.

Why this number and not the others:

- **+1,323% is one of three calendars.** It is the calendar whose rebalance dates happened to land
  just before large moves. The three calendars' results cannot be told apart from each other
  (spread 1.18%/mo inside an MDE of 1.37-2.07%/mo). When the draws cannot be told apart, the
  estimate is their average, and averaging them is exactly what the tranche book does.
- **The excess over the twin is the claim-relevant quantity, not the excess over SPY.**
  - The panel's own random portfolio compounds at only ~9.1%/yr against SPY's 15.1%. It tilts
    small.
  - The tranche book's +30.9%/yr against SPY therefore mixes the rule with the panel's style.
  - Against the random panel it is roughly +21.8%/yr. That is my subtraction of CAGRs over
    slightly different spans, UNVERIFIED as a computed field; the builder did not compute it.
- **Even the twin number is mostly "momentum works".** The twin is matched on the 12-1 TERCILE, so
  a top-20 12-1 sort beats it on extremity within the tercile. +1.2%/mo vs this twin is a
  published factor showing up, not a discovery.
- **It is hindsight-selected.** The rule was registered 2026-09-26, after every month here. DSR at
  its best calendar is 0.197 against the 0.95 bar.
- **2020 is a large share.**
  - The worst leave-one-year-out drops 2020, which takes rule − twin from 1.20 to 0.91%/mo.
    Grouping here is by decision year (my read of the parquet), so it is approximate against the
    hold-month keying.
  - 2020 contributes 32% of the summed rule − twin.
  - Against SPY, the tranche book's 2020 is +152 pp, and dropping 2020 halves its mean active
    return (1.62 → 0.79%/mo).
  - Without its best 5 months the tranche book compounds at 13.5% against SPY-without-its-best-5
    at 9.6%.

---

## Findings, most severe first

### F1 — CRITICAL. The pre-registration's frozen inputs are not under version control

- **Where.** `b1010061` committed the trial DOC only. Still untracked (`??` in `git status`):
  - `backend/data/optimus/trials/lib_forward_trial_2026-09-28T062024Z.json`, which holds the
    30 pairs, 17 clusters, 30 × 2 sigmas and both ρ;
  - `backend/services/lib_forward_trial.py`, which holds `decide` and `pooled_sd`;
  - `scripts/lib_forward_trial.py`, which holds `estimate`;
  - the cluster source `backend/data/optimus/bridge/bridge_2026-09-28.json`.
- **What the doc claims.** Its §"Frozen parameters" says every sigma and pair is "in" that receipt
  and that module. The doc itself carries only the pooled sd, the two ρ and the thresholds.
- **Failure scenario.** On 2026-10-26 a reader regenerates the receipt after `books.jsonl` or the
  bridge has changed (a VOID, a re-cluster). The per-book sigmas and the pair list differ, and
  nothing tamper-evident says which version was frozen. The doc's own clause ("committed before
  the open, else inception moves") was met for the text and not for the numbers.
- **What I would have done.** Commit the receipt, both modules, the bridge file and the
  calendar-offset receipts in the same commit as the doc, with the receipt's sha256 printed in
  the doc. Still possible: it is ~06:45Z and the open is 13:30Z.

### F2 — CRITICAL. The trial's sd(D) is estimated on one twin type and applied to another

- **Where.** `scripts/lib_forward_trial.py`, `estimate`, about lines 52-96.
  - σ for the 25 band-only pairs is widened to max(matched, rule − `random_1@k50`) at lines 66-74.
    That part is right.
  - But ρ_within (0.66) and ρ_between (0.09) are computed from `series[...] = d`, the
    **matched-twin** differences (`rule_minus_twin0`), for every pair.
- **What the forward read uses.** It pairs 25 of 30 books with a size-band-only twin. Those
  differences share the momentum/vol/size style that the matched twin removes, and 8 or more of
  the 17 clusters are momentum variants (170, 186, 179, 167, 181, 149, 84, 138).
- **Re-estimate, using the difference type the trial actually reads** (band-only proxy
  rule − `random_1@k50`, matched for the 5 matched pairs; frozen sigmas unchanged):

  | | frozen | recomputed |
  |---|---:|---:|
  | ρ_within | 0.66 | **0.78** |
  | ρ_between | 0.09 | **0.40** |
  | sd(D), 21 sessions | 2.76% | **4.79%** |
  | sd(D), 63 sessions | 4.90% | **8.47%** |

  The empirical sd of an equal-weight pool of those 28 series agrees: 5.05% a month and 9.6% per
  3 months.

  The proxy is not size-matched, so 0.40 is an upper-side estimate. The truth lies between the two
  columns (UNVERIFIED exactly).
- **Consequence.**
  - Every z the trial prints is inflated by up to ~1.7×.
  - Under zero skill, P(EARLY_KILL at z_21 ≤ −2) is ≈ Φ(−1.15) ≈ **12%**, not the documented
    2.3%. P(z_63 ≥ 2) is likewise ≈ 12%.
  - One momentum quarter can therefore produce a "SURVIVES", and one momentum crash an
    "EARLY_KILL", on style alone.
  - The "17 clusters" behave like 17 / (1 + 16 × 0.40) ≈ **2.4** independent bets.
- **What I would have done.** Estimate every ρ from the same difference type as the sigma, per
  pair. Commit a dated amendment BEFORE 13:30Z (no data has accrued), printing both z's at every
  read, with the corrected one deciding. Alternatively, read only the style-neutral subset.

### F3 — HIGH. The verdict rule is asymmetric, so it can almost only say CANNOT_DISTINGUISH

- **Where.** `backend/services/calendar_offsets.py:19-32` (the declaration) and `:308-315`
  (`beats_twin` / `loses_to_twin`).
- **The asymmetry.**
  - BEATS needs mean > 0 AND t ≥ 2.
  - LOSES needs only mean ≤ 0.
  - ARTEFACT needs one BEATS and another LOSES.
- **Why LOSES is almost unreachable.** The twin is matched on the 12-1 tercile, so every momentum
  sort's point estimate against it is positive by construction (extremity inside the tercile).
  "No offset loses to its twin" is therefore uninformative. I would expect all 12 cells positive
  whether or not the calendar matters, and all 12 are (0.21 to 1.95%/mo).
- **The brief's rule.** The roadmap (LANE M1, committed in `b1010061`) says: "a lead whose other two
  calendars do not beat their matched twins is relabelled a calendar artefact." Under that rule:
  - `disp_short_avoid` is a **CALENDAR_ARTEFACT** (FMAN t 0.96, MJSD t 0.46).
  - It is +1,207% on one calendar and +233% on another, and its FMAN 2024-26 rule − twin is
    negative.
  - The honest word is **artefact**. The builder says so in prose, then files CANNOT_DISTINGUISH.
- **"Declared in code before running" is unverifiable.**
  - The module is untracked.
  - Two runs exist today: `T055728Z`, and `T055923Z` two minutes later.
  - I diffed them. The verdicts and `verdict_rule` are identical, the numbers differ only at the
    6th decimal, and the second run adds `tranche_average` and the monthly parquet.
  - So the calendar-neutral book was added after the first verdicts were seen. It is labelled
    "not a verdict input", which is the right protection, but it should be said.
- **What I would have done.**
  - Keep the brief's rule for the label.
  - Replace the per-offset rule with a symmetric one that reads the verdict on the tranche book:
    - the calendars are "indistinguishable" when the spread is under one MDE (true for all four);
    - then the verdict is read on the tranche book's rule − twin, in BOTH windows.
  - Under that rule all four are **NOT DEMONSTRATED in 2024-26** (sealed t 1.18 / 0.61 / 1.34 /
    1.27).
  - Print both labels on the receipt's `summary`.

### F4 — HIGH. One seed set of the twin; the per-draw spread is not stored

- **Where.** `calendar_offsets.py:196-218` (`twin21`) keeps only draw 0 and the 21-draw mean.
- **Evidence of single-draw noise, from the receipt.**
  - For `qc470_mom252_quarterly_riskparity` at FMAN, draw 0 gives rule − twin **+0.275%/mo** and
    the 21-draw mean gives **+1.265%/mo**. That is a 1.0 pp/mo gap from one draw, either an outlier
    draw or a bad price in one twin holding (UNVERIFIED which). That cell is filed BEATS at t 2.51;
    on draw 0 alone it would not be.
  - Across the other 11 cells, draw 0 − twin21 is 0.02-0.30 pp/mo.
- **The error bar I can derive.** Per-draw sd of the mean is ≈ 0.15-0.3 pp/mo. The SE of the
  21-draw mean is then ≈ 0.03-0.07 pp/mo, against a monthly SE of 0.7-0.8 pp. That puts
  **±0.1-0.2 on each twin21 t, and ±0.4-1.3 on a single-draw t**.
- **Three of the seven BEATS are inside that band of 2.0:**
  - `mom_12_1_q` MJSD, t 2.04;
  - `mom_12_1_q_trend` MJSD, t 2.12;
  - `qc470` JAJO, t 2.12.

  The builder's "the pass moved with the twin's random seed" is correct, and it applies to those
  labels too.
- **What I would have done.**
  - Store each draw's mean.
  - Rerun on a second, disjoint set of 21 seeds and report both t's.
  - Treat a label as settled only when both seed sets agree.
  - Inspect the qc470 FMAN draw-0 holdings for a price error.

### F5 — HIGH. The BESIDE column does not print the calendar-neutral number

- **Where.** `backend/services/strategy_library.py`, `calendar_context` (new).
- **What it prints.** The three calendars' cum since 2020 and the verdict. It prints nothing from
  `tranche_average`.
- **The twin field.** `twin_context` prints the MONTHLY t, with a warning that it overstates a
  hold-3 rule, even though this lane computed the rebalance-blocked t.
- **Failure scenario.** The next LEADERBOARD.md still leads with +1,323% and hangs the correction
  beside it, instead of printing the number that should be quoted.
- **What I would have done.**
  - Print the tranche line in `calendar_context`: cum since 2020, rule − twin with t in both
    windows.
  - Use `offsets.results[rule].offsets[tag].twin.{dev,sealed}.t_blocks` in `twin_context` for
    hold-3 rules.
- **Scope gap.** 7 of the board's 11 hold-3 rules were never offset-checked and still sit on JAJO
  only: `flow_rule_q`, `gp_at_q`, `hi52_q`, `inst_breadth_up`, `lowvol_63_q`, `mom_6_1_q`,
  `quality_momentum_gate`. They print NOT COMPUTED, which is honest. The run takes about one
  minute.

### F6 — HIGH. The paper-account number: the builder is right, but the working tree will undo it

**What the receipts say (verified):**

| file | what it is | numbers |
|---|---|---|
| `HEAD:roi_2026-09-27.json` (= `3204eb4d`) | generated 06:44:32Z, BROKER-INCLUDED; families include `alpaca_fleet` 6 + `pc_paper` 1 | 39 / 7 / 32 / −1.315% |
| working-tree `roi_2026-09-27.json` | generated 23:51:21Z, the `--no-broker` scope; no broker families | 33 / 6 / 27 / −0.273% |
| `roi_2026-09-28.json` and `roi_2026-09-28T060842Z.json` | broker-included | 39 / 7 / 32 / −1.34%; ex-control twins: 25 accounts, **−1.81%** |

The earlier fact check was wrong to call "39" stale. The two numbers have different scopes.

**Findings:**

- **Committing the working tree destroys the evidence.** If the orchestrator commits the working
  tree as it stands, HEAD's broker-included `roi_2026-09-27.json` is replaced by the narrower
  file. The committed evidence for "3204eb4d did not supersede 39" then lives only in history.
- **The roadmap still carries the wrong line.** `ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md` §0
  (TIER 1, committed) still prints the narrower "33 priced … −0.27%" as the scoreboard's paper line
  and was not annotated. It is the most-read line in the repo.
- **The run-id fix is partial** (`scripts/paper_accounts_roi.py`, the write loop about 20 lines
  above the new return):
  - `for target in ([] if rr.exists() else [rr]) + [rj]` silently skips on a same-second
    collision;
  - the date-named copy is still overwritten;
  - tonight's 22:30Z `--no-broker` pass will turn `roi_2026-09-28.json` into the 33-scope again.
- **"7 ahead / 32 behind" counts 14 control twins as accounts.**
- **The pre-open read mixes clocks.** The 06:08Z Monday read marks PC positions on overnight
  prints (AAPL 341.07 → 340.62) while the recorded SPY benchmark is Friday's 771.21. The effect is
  small (~0.1% on PC).
- **Money-path side effect: NONE (verified).**
  - `pc_broker.snapshot(tag="paper_accounts_roi", out_dir=paper_accounts/pc_snapshot)` appends to
    the ROI tool's own ledger. Its previous rows (09-26, 09-27) carry the same tag.
  - The live loop writes `STATE_DIR`.
  - The only other reader of `pc_snapshot` is `scripts/source_reads.py` (reporting).
  - The row is tracked data and should be committed as data.
- **What the daily pass should do:**
  - read the brokers (the owed one-line change in `daily_pass.py`);
  - put the scope in the date-named file's name (`roi_<day>.broker.json` / `.nobroker.json`), or
    refuse to overwrite a broker-included file with a narrower scope;
  - headline two numbers every time: all priced, and ex-control-twins;
  - print a line that goes red when the broker legs are missing.

### F7 — MEDIUM. M4's pitch annotation (TIER 0 §8) is selective in one place

**What holds.**

- History is preserved. All four diffs are additions only, dated, "nothing above is erased".
- Every corrected number names a receipt. One of those receipts, `roi_2026-09-28T060842Z.json`,
  is untracked (F1's fix covers it).

**The problem.**

- The annotation prints the free volatility formula beating the LLM at h = 1: +10.0% vs +5.5%,
  and +5.7% for the LLM on the prior's own rows.
- At h = 5 it prints +5.9% vs +2.6% and omits the like-for-like figure. The same receipt
  (`learning_reports/report_2026-09-27.json` → `closing.vol_prior["5"].skill_llm_own_prior`) says
  the LLM on the prior's own rows scores **+7.5%**, which beats the prior.
- The held-out window is also 4 calendar days (2026-08-24 → 08-27, 775 rows).

**The +8.97% finding.** The builder's finding stands. I found no 0.0897 / −0.2798 in
`specialists/scoreboard_2026-09-24.json`.

**What the pitch should say.**

> "On one held-out week of August, a free volatility formula forecast the SIZE of next-day moves
> better than our LLM arms (+10.0% vs +5.7% Brier skill, like for like); at 5 days the LLM was
> ahead (+7.5% vs +5.9%). Our earlier +8.97% vs −27.98% comparison mixed a recalibrated number with
> a raw one and is withdrawn until a committed receipt reproduces it."

No process-vs-persona claim belongs in a TIER 0 pitch on this evidence.

### F8 — MEDIUM. The forward trial's scope and calendar are not stated

**The calendar.**

- The four hold-3 books were frozen on 2026-09-25 bars. A September decision is the **MJSD
  calendar**, which was `disp_short_avoid`'s weakest backtest calendar (t 0.46) and `qc470`'s
  (t 1.31).
- So the forward books do not include the lucky JAJO calendar. That cuts against luck, which is
  good, but the registration never says which calendar they are on.
- Nothing in the registration was decided after forward data. It is before the first session; the
  EXPLORE relabel came from `lint_prereg`, not from outcomes.

**The clustering.**

- It is the bridge's pre-existing ρ 0.8 cut, not chosen for this trial.
- Cluster 170 holds 9 books, including two `qc470` "__control" copies of one rule. They count once
  through the cluster weighting.

**Power.**

- At the realistic calendar-neutral backtest edge (~1.2%/mo vs twin, which is ~3.6%/quarter for
  momentum books and less pooled), P(KILL) at 63 sessions is ~75-80% even if the edge is real.
- The doc says "a KILL means no large edge", which is honest. The label **KILL** oversells it: call
  it `DEPRIORITIZED`, which is also what its consequence says.

**Is it worth running?** Yes, because it is free: the books are already frozen and the grader
marks them. It is worth running as a monitor with a pre-committed interpretation, not as a
decision. After F2 it cannot confirm anything under ~15-25% per quarter.

### F9 — LOW. "Not measured" and "measured, inconclusive" share one label

- **Where.** `calendar_offsets.py:118-149` and `:308-330`.
- **The failure.** `block_stats` on an empty or all-NaN difference returns `mean_monthly None`.
  `beats_twin` and `loses_to_twin` are then both False, and `classify` returns
  CANNOT_DISTINGUISH.
- **Failure scenario.** A twin series that failed to build reads as a measured null.
- **What I would have done.** Return `NOT_COMPUTED` / REFUSED when any offset has `n_blocks < 3`.

### F10 — LOW. The staleness probe dates the run, not the data (`backtest_staleness.py:52-87`)

The probe reads a fresh run over stale bars as ALIVE, even though the bars went stale on 09-21 with
no refresher, and nobody noticed. Two further gaps:

- a body with no `run_id` is accepted (line 73: `body_run is not None and …`);
- a PARTIAL board counts as ALIVE.

**What I would have done.** Date the board by `min(run time, panel last date + 1 session)`, and
treat PARTIAL as STALE.

### F11 — LOW. The tranche t slightly overstates

- **Where.** `calendar_offsets.py:359` blocks the tranche book in fixed 3-month blocks. Each block
  boundary cuts through two of the three books' holdings, so adjacent blocks are correlated and
  the SE is modestly understated.
- **Missing fields.** For the tranche book, vs the random panel, DSR, and by-year / LOO are not
  computed ("--" in the table).
- **Fix.** Use a HAC (Newey-West, 2 lags) SE and compute the three missing fields.

---

## Tests

Command, as briefed: **25 passed, exit 0** (7.9 s).

| file | fails if the feature is removed? | date rot | real data tree | passes on empty? |
|---|---|---|---|---|
| `test_calendar_offsets.py` | yes: the planted-signal ROBUST test, the classify branches and the block maths | no; `_month_ends` is derived from today | no; synthetic panel | not tested: `classify` on empty twin stats returns CANNOT_DISTINGUISH (F9) and no test pins a refusal |
| `test_backtest_staleness.py` | yes: goes red, goes green, UNKNOWN, mtime ignored | `2026-13-45T999999Z` is an invalid date on purpose, so it cannot rot | no; tmp_path | no-board → UNKNOWN is tested |
| `test_lib_forward_trial.py` | yes: pairing, pooled_sd closed form, every `decide` branch, luck closed form, idempotent registry | none | no; tmp DB | no test that `estimate`'s ρ uses the same difference type as its σ, which is the F2 defect |
| `test_paper_accounts_broker_read.py` (read, not run) | appears yes; injected broker legs | `TODAY` is UTC-derived; the `created_at` literal is inert | no | — |
| `test_headline_context.py` (read, not run) | appears yes | run-id literals in tmp dirs only | no | — |

Two tests are missing:

- A test that `calendar_context` prints the tranche line (F5).
- A test that a style-positive twin comparison (momentum extremity) is not read as evidence.

---

## MUST FIX BEFORE COMMIT

1. **Before 13:30Z today, one commit** containing:
   - the trial receipt `trials/lib_forward_trial_2026-09-28T062024Z.json`;
   - `backend/services/lib_forward_trial.py` and `scripts/lib_forward_trial.py`;
   - `bridge/bridge_2026-09-28.json`;
   - both `calendar_offsets_*` receipts and the monthly parquet;
   - `roi_2026-09-28T060842Z.json`;
   - the receipt's sha256 added to the trial doc. (F1)
2. **Before 13:30Z**, a dated amendment to TRIAL-LIB-FWD-TWIN-1 that estimates ρ from the same
   difference type as σ. That gives sd(D) of about 4.8% / 8.5%. Both z's are printed at every read
   and the corrected one decides. (F2)
3. **Do not commit the working-tree `roi_2026-09-27.json` over HEAD's broker-included file.** Save
   the 23:51Z content under its run id instead. The orchestrator does this without
   reset/checkout/stash (copy aside, then restore the content from `git show HEAD:`). Also
   annotate the TIER 1 roadmap §0 paper line with the 39 / −1.34% broker-included scope and the
   25-account ex-control figure (−1.81%). (F6)
4. **Relabel `disp_short_avoid` CALENDAR_ARTEFACT** under the brief's rule, or print both rules'
   labels in the receipt summary and the build note. Do not file CANNOT_DISTINGUISH alone. (F3)
5. **Withdraw "+8.97% vs −27.98%" from the TIER 0 pitch** and print the like-for-like h = 5 result
   beside the h = 1 one. (F7)

## OWED LATER

- Store per-draw twin means; run a second disjoint seed set; inspect the qc470 FMAN draw 0. (F4)
- Put the tranche line into BESIDE; use the blocked t for hold-3 rules; run the triplet on the
  7 unchecked hold-3 rules. (F5)
- Daily pass reads the brokers; scope-named date files; ex-control headline; a red line when the
  broker legs are missing. (F6)
- State the forward calendar (MJSD) in the trial; rename KILL → DEPRIORITIZE. (F8)
- `classify` refuses on empty twin stats (F9). Staleness dated by panel end; PARTIAL counts as
  STALE (F10).
- HAC SE and the missing fields on the tranche book. (F11)
- A twin matched on the 12-1 DECILE, or a UMD regression, before any momentum rule is called
  anything but momentum.
- The owed `backend/main.py` startup registration and a scheduled caller for the two reads, plus
  the factory's weekly caller with `--no-freeze` as proposed.

---

## For Murat: "are you sure the backtests are valid, is this replicable, anything we can learn?"

**Is it replicable? Yes.** This run reproduced last week's board to the last digit on the same
370k-row panel, costs included, and the code refuses to run if the data shrinks.

**Are the backtests valid? Mechanically yes. As evidence of a special edge, no.** There are four
reasons:

- **The famous +1,323% is one of three calendars.** It is the same rule rebalanced in
  January/April/July/October. Rebalance it one month later and you get +424%, one month later again
  +433%. The honest figure is the average of the three, **+661% since 2020 against SPY's +162%.**
- **Almost all of that is plain momentum plus our universe's small-cap tilt.** Momentum is a
  factor known since 1993. Against a random stock with the same size, volatility and momentum
  bucket, the rule gains about **1.2% a month**. That figure clears the noise over 2017-26 but not
  over 2024-26, and 2020 alone supplies about a third of it.
- **The four "leads" are one bet wearing four names.** Their returns move together at 0.83-0.97.
- **The forward test starting today is worth running but cannot prove anything soon.** Its error bar
  was drawn about 1.7 times too narrow, so as written it could declare a winner or a loser from one
  momentum swing. That is fixable this morning, before the market opens.

**What to learn:**

- Any quarterly strategy should be quoted as the average of its three calendars.
- Any "beats the market" should be quoted against a matched random twin, not SPY.
- For our paper accounts the honest number is **39 accounts, −1.34%** (−1.81% without the control
  twins), not the flatter −0.27% that dropped the six broker accounts.
