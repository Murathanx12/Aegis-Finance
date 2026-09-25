# Audit — forecasts, decisions and learning since 2026-08-11

**Written 2026-09-26, read-only, $0.00 LLM spend.** No repo source or data was modified; the running sim
(`backend/data/optimus/sim/`, session `746074adc086`) was not touched. Every number below was computed from
a snapshot of `backend/data/optimus/predictions.jsonl` taken at the start of the audit (**26,148 rows**) or
read from the named receipt. Scripts used: throw-away pandas over the snapshot, and the repo's own
`forecast_reputation.arm_skill` (held-out = the later half of each arm by `made_at`).

Murat's questions: *"See how the decisions, the forecasts made since August have been working. Were they
affected? Were there any green ideas? How did it learn, digest from them?"* and *"we have so many
independent things that are not connecting to each other, or the strategies are clashing."*

---

## 0. The ten-line version

1. **What worked:** one forecasting *process* — the five `investigator:*` arms — beats the base rate held
   out: **+4.0% Brier skill (n 2,340)**, and **+8–10% after shrinking toward the base rate**. **All of it is
   MAGNITUDE skill** ("will it move more than X%"). On DIRECTION (`return_sign` h=5) the same arms score
   **−8.7% held out**, and the best shrink weight fitted on the training half is **0**. §64's +8.97% is a
   volatility forecaster, not a stock picker.
2. **What did not:** the nine-plus thematic personas (**−26.8% held out, n 6,391**, discrimination ≈ 0);
   the ranker (IC +0.016, t +5.3, but top-20 **−1.09%/21d net**); the Railway fleet (**−9.8%**, 358 trips,
   hit rate 27.7%, **−$39,384** realised); every price/volume, fundamentals, horizon and exit-rule rescue
   (§59–§62).
3. **Green ideas exist but none is established.** The strongest are historical replays:
   `forecast_dispersion` (+1.02%/month, t 5.65, 419 blocks, positive in 4/4 eras) and Book F
   seasonality ($10M +0.43%/month, t 3.12). **Neither is running forward anywhere.**
4. **What the machine changed because of a grade:** personas floored at weight 0; a 0.65 shrink on new
   investigator rows; reputation keyed by (arm, observable, horizon); no stop in PC-PAPER after §62; the
   funnel is rebuilt on a schedule; the autopsy re-benchmarked to the universe median; PROBE gated on the
   shortlist's own grade. That is about seven real loops, and **six of them were closed by hand in a
   session**, not by the machine.
5. **The machine's own "learning" layer has learned nothing:** `brain/LEARNED_2026-09.md` distilled **0
   rules** (its local model was not answering); `learned_rules.jsonl` does not exist; every one of the
   **126** daily `LEARNED_*` lines is a status heartbeat ("L2 typed 0 rows"); `policy_state.json` does not
   exist, so the night has **never moved a single preference**.
6. **Forecast accrual stopped for four weeks** (2026-08-28 → 2026-09-24: 11 rows in 28 days). The ledger's
   `resolved_at` stamps show only two grading runs, **2026-09-20 (14,703 rows) and 2026-09-24 (2,781)**.
   **No new forecast has been graded since §64.** The 2,781 extra rows are August forecasts at longer
   horizons.
7. **Open loop 1, the most urgent:** the investigator's real skill is magnitude, and **nothing that sizes a
   position reads it**. The new rows written since 09-24 (`evidence_v2/v3`) are direction rows with the
   magnitude-earned shrink applied, which is the wrong skill with the wrong correction.
8. **Open loop 2:** graded decision outcomes exist and nothing acts on them. The autopsy measured
   **PROBE − REFUSED = −0.68%/day (t −0.83, 3 date blocks)**, and the PROBE gate reads **none** of those 114
   graded rows because it keys only on the `C3_committee_shortlist_probe_v0` hypothesis id.
9. **Open loop 3:** the Railway fleet's autopsy (−418 bps per position, winners cut at +1.91%) produced no
   change. The execution repo has **no commit since 2026-09-20**.
10. **Clashes:** 14 found (§5). **Five are designed experiments; nine are accidents.** The sharpest
    accident: on 2026-09-25 `decisions/2026-09-25.json` **REFUSED ALLE**, and PC-PAPER **bought 131 ALLE**
    the same day under PROBE.

---

## 1. The forecast ledger since 2026-08-11

### 1.1 Rows made and graded, per week

| week (made) | family | made | graded |
|---|---|---:|---:|
| 08-10 → 08-16 | personas (legacy thematic bench) | 20,048 | 12,781 |
| | `why_moved:*` | 25 | 23 |
| 08-17 → 08-23 | investigator v1 (5 arms) | 2,370 | 2,310 |
| 08-24 → 08-30 | investigator v1 (5 arms) | 2,385 | 2,370 |
| 08-31 → 09-06 | — | **0** | — |
| 09-07 → 09-13 | `book:*`, `base_rate`, `headline_arena` | 11 | 0 |
| 09-14 → 09-20 | — | **0** | — |
| 09-21 → 09-27 | investigator v1 re-run (600), `evidence_v2` (40), `evidence_v3` (118), `review:v0` (385), `thesis_card:v1` (166) | 1,309 | 0 |

- **By day**, the graded evidence is thin. The personas were written in one batch: **19,961 rows on
  2026-08-12**, inside about four minutes. The investigator arms wrote on **eight days** (08-17 … 08-27),
  about 39 tickers a day. **Every graded row was made between 08-11 and 08-27.**
- **When it was graded:** 14,703 rows on 2026-09-20 and 2,781 on 2026-09-24. There are no other
  `resolved_at` dates. An h=1 forecast from 08-17 therefore waited about five weeks for its grade, and the
  first time anything read the grades was §64 on 09-24.
- **Still pending:** 7,267 persona rows at h=60/120/252. They resolve from November 2026 to August 2027 and
  will keep grading a bench that is already retired. 130 past-due rows remain unresolvable (5 per
  investigator arm per observable, plus scattered persona rows).
- **Were they affected?** Yes, in four ways:
  1. **The four-week accrual gap.** The forward ledger's clock stopped from 08-28 to 09-24, and no health
     row went red until `forecast_accrual` was added on 09-25.
  2. **Lost rows.** §64 quotes a **25,439-row** ledger. The final `specialists/scoreboard_2026-09-24.json`
     (written 15:35Z) records **24,839**, and `reputation_2026-09-25.json` records 24,879. The ~600-row
     shortfall matches the 2026-09-24 `git reset --hard` that destroyed uncommitted rows. That note says
     ~1,200 rows were lost, and some rows were written again after it. There are no duplicate
     `prediction_id`s now.
  3. **Model drift.** Every graded row is `deepseek-v4-flash` (August). All September rows are
     `deepseek-flash`, the model the provider has returned since 09-14. The reputation earned in August is
     being applied to a different model string.
  4. **The overwritten scoreboard.** The 09-24 scoreboard file was overwritten later that day. It now reads
     **n_scored 17,484, overall −19.35%**, not the **14,703 / −17.01%** that §64 quotes. §64's numbers are
     reproducible only from the text.

### 1.2 Per family, all graded rows (in-sample climatology = base rate of the scored rows)

| family | n graded | base | Brier | clim | **skill** | calib gap | **discrimination** |
|---|---:|---:|---:|---:|---:|---:|---:|
| ALL | 17,484 | 0.340 | 0.2678 | 0.2244 | **−19.35%** | +17.9pp | +4.7pp |
| investigator v1 (5 arms) | 4,680 | 0.262 | 0.1830 | 0.1932 | **+5.32%** | +8.2 | **+15.6** |
| personas (legacy, 14 names + 5 sector) | 12,781 | 0.368 | 0.2989 | 0.2327 | **−28.43%** | +21.5 | −1.5 |
| `why_moved:*` | 23 | — | — | — | −16.4% (THIN) | — | — |
| `investigator:evidence_v2` | 40 made, **0 graded** (h=1, resolve 09-28) | | | | | | |
| `investigator:evidence_v3` | 118 made, **0 graded** (h=1/h=5, resolve 09-29 → 10-05) | | | | | | |
| `review:v0` | 385 made, 0 graded | | | | | | |
| `thesis_card:v1` | 166 made, 0 graded (h=20/h=120) | | | | | | |

### 1.3 Split by observable and horizon — the split that matters

**Investigator v1, all rows / held out (later half, test window 08-24 → 08-27):**

| observable | h | n | base | skill (all) | disc | **skill held out** (n) | disc held out | recalibrated held out |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `abs_move_exceeds` | 1 | 1,560 | 0.147 | **+10.90%** | +18.1 | **+5.56%** (780) | +17.8 | **+10.4%** at w 0.65 / +7.7% at train-fit w 0.90 |
| `abs_move_exceeds` | 5 | 1,560 | 0.224 | −0.64% | +12.0 | +2.61% (780) | +17.1 | **+8.4%** at w 0.65 / +8.0% at train-fit w 0.40 |
| `return_sign` | 5 | 1,560 | 0.413 | **−7.94%** | **−0.2** | **−8.72%** (780) | +0.5 | −4.6% at w 0.65; **train-fit w = 0.00** → −0.75% |

The investigator arms wrote **no `beats_benchmark` rows in August**. The only direction question they
answered is `return_sign` h=5, and they have **no skill on it**. Their held-out discrimination there is
+0.5pp. The reviewer's calibration read agrees: the most bullish bin (stated p 0.664) rose 35.5% of the
time (`reputation_2026-09-25.json → calibration.h5`).

**Stability, investigator `abs_move` h=1 by day:** positive on 6 of 8 days (+4.6% to +21.8%). One
catastrophic day, **08-25 at −175%**, had a base rate of 2.6%, so a single day with almost no big moves
punishes any forecast of movement. Effective sample: **8 date blocks, 133 tickers**. The five arms answered
the **same 312 (ticker, day) questions** and their probabilities correlate **0.70–0.93**. The "five arms"
are about 1.5 independent forecasters, and the reputation weights (D_all 0.42, A 0.25, C 0.24, B_tools
0.06, B_anon 0.03) are dividing weight among near-clones.

**Personas, all rows / held out:**

| observable | h | n | skill (all) | disc | skill held out | disc held out |
|---|---:|---:|---:|---:|---:|---:|
| `abs_move_exceeds` | 5 | 2,346 | −72.5% | +1.3 | −71.0% | +1.7 |
| `abs_move_exceeds` | 20 | 3,165 | −75.6% | +1.0 | −74.1% | +1.2 |
| `beats_benchmark` | 20 | 2,098 | −6.3% | +0.5 | −5.8% | +0.9 |
| `beats_benchmark` | 5 | 135 | −14.6% | −0.9 | −13.8% | +2.7 |
| `return_sign` | 5 | 1,986 | −4.5% | −0.3 | −4.0% | 0.0 |
| `return_sign` | 20 | 2,479 | −19.6% | −0.3 | −19.6% | −0.6 |
| `drawdown_exceeds` | 20 | 343 | −0.9% | +2.3 | −1.7% | +2.4 |

The persona failure is **calibration** (a +37pp overstatement of big moves), not anti-signal.
Discrimination is ≈0 everywhere. The reviewer was right to correct MEMORY's "negative discrimination =
anti-signal": inverting the personas recovers nothing, and the correct weight is zero because they carry no
information.

### 1.4 Reproducing §64 and what changed since

| | §64 (text, 09-24) | this audit (26,148-row snapshot) |
|---|---|---|
| graded | 14,703 | **17,484** (+2,781, all August forecasts at longer h, graded 09-24) |
| overall skill | −17.01% | **−19.35%** |
| investigator held out, raw | +4.38% (n 2,325) | **+4.04%** (n 2,340) |
| investigator recalibrated | +8.97% at w 0.65 | **+10.4% (h1 magnitude), +8.4% (h5 magnitude), −4.6% (direction)** |
| thematic held out | −27.98%, weight 0 | **−26.8%**, weight 0 (`reputation_2026-09-25.json`) |
| per-arm held out | — | D_all +6.02, A +5.04, C +4.99, B_tools +3.08, B_anon +2.55; personas −20.7 (macro_rates) … −70.0 (biotech_pharma) |
| tuned pool, CV skill vs climatology | — | **+0.79%** (`reputation_2026-09-25.json → tuned.cv_skill_vs_climatology`, k_prior unidentified) |

**Verdict:** §64's split stands. Its interpretation needs one correction: **the positive number is
magnitude skill at h=1–5, and direction skill is zero.** The pooled ensemble, tuned out of sample, adds
**0.8%** over always saying the base rate. **Nothing new has been graded since §64.** The first new grades
land on 2026-09-28 (`evidence_v2`, 40 rows).

**The new arms are built to have little power:**
- `review:v0`: **383 of 385 rows sit at p = 0.50**. A constant 0.5 can never beat climatology, so this arm
  can only score ≤ 0 skill.
- `thesis_card:v1`: **112 of 166 rows at 0.50** (the "neutral" verdicts). The informative part is 54 rows.
- `evidence_v2`: p ranges 0.461–0.552 (sd 0.022) after the 0.65 shrink. Even a real direction signal this
  small needs thousands of rows to show up.

---

## 2. Green ideas since August (anything with a positive held-out or forward number)

| idea | number | n / blocks | status today | what would settle it |
|---|---|---|---|---|
| **Investigator process, magnitude** (§64) | held out +5.6% (h1), +2.6% (h5); recalibrated +8–10% | 780+780 test rows; **8 date blocks**, 133 tickers | **RUNNING** (v1 re-ran 600 rows 09-25; the grades are due) | same skill on ≥ 6 new date blocks from the 09-25 rows; the direction component stays at w=0 until disc > 0 on ≥ 6 blocks (reviewer 2.1) |
| Investigator process, direction | **−8.7%** held out | 780 | **DEAD** as a direction signal (train-fit w = 0) | `evidence_v3` `beats_benchmark` h1/h5 with n ≥ 1,500 |
| **forecast_dispersion_v1** (low analyst-EPS dispersion, long-only-avoid) | **+1.02%/month, t 5.65**; $10M +1.19%/month, t 6.07; 4/4 eras | 419 month blocks, 1990–2024 (replay) | **BANKED, orphaned**: PRODUCT_PROMISING on 09-13, **no forward book, no mention in INDEX or the current roadmap**. v0: +0.89%/month, t 4.82 | a forward paper book with twins, plus a 2025–26 IBES read. The prior's own draft warns there is no post-2010 replication and that the result could be low-short-interest in disguise |
| **Book F seasonality_11_20_v0** | +0.47%/month, t 3.05; **$10M +0.43%, t 3.12** ("the one positive $10M cell") | 419 blocks | **BANKED, CONDITIONAL** (below the declared 0.65%/month); not forward | a forward book; the declared MDE |
| QMJ quality tilt v0 | +0.41%/month, t 2.56; **$10M +0.11%, t 0.70** | 419 blocks | **BANKED, CONDITIONAL**; dies at the tradable floor | the $10M cell turning significant, which it has not |
| Disposition overhang conditioner (Book C) | excess vs twin **+0.40%/month, t 2.13**; at the registered 60-month construction, **+0.24%/month** (MEMORY 09-13); momentum falsifier "passed" with nothing alive to subsume | 395 blocks | **RUNNING forward but inert**: `book:a82e6e453c14c241` NAV **$100,000.00** on 09-21 because it has never decided | its first monthly decision and a live momentum control |
| mom_12_1 k=12 monthly (night-job book) | NAV **$103,978** vs beta-matched twin $100,741, random twin $98,681 | **1 decision, 09-12 → 09-21** | **RUNNING** (`book_cadence`) | ≥ 6 monthly decisions. §59 says momentum is dead at 21d, so this is one draw |
| abstention_book_v0 | NAV **$110,099**, identical to its always-invested twin | 1 decision | **RUNNING, uninformative**: the gate never deviated | the gate firing once |
| Revision-flow month-end rule (Q-10) | **+0.32%/hold vs SPY, t 0.94**; LOO-worst **+0.02%**; k=50 +0.04% | 121 holds, 2016–26 | **RUNNING as a book** (`revision_flow_v0` `cb8d492bb8bf9ade` + random twin; 13/20 software names; twin not sector-matched) | the 21-session grade against a **sector-matched** twin. The lead-vs-chase split (reviewer idea B) is $0 and untested |
| §61 composite_prior at H=126 | +2.62%/hold → **+0.12% with 2025 dropped** | 4 strictly independent blocks | **DEAD** | — |
| profitability_small (the funnel's picker) | D10−D1 net **+0.64%/21d, t 1.59**, Holm p 1 → **WEAK**; earlier +5.11% at 126 sessions, t 2.78, Holm 0.065 | 191 month blocks | **RUNNING as the PROBE shortlist's main picker (weight 0.7)** | the PROBE gate's 21 scored days at h=5 (earliest verdict ≈ early November) |
| insider_opportunistic | D10−D1 net **−0.05%, t −0.35** → WEAK | 191 blocks | **RUNNING as the shortlist's second picker (weight 0.5)** despite a negative net spread | same |
| xs_ranker ordering | IC **+0.0162, t +5.30** (09-21); top-20 **−1.09%/21d net** | 2,929 names | **DEAD for EXPLOIT** (§59); still computed nightly | an input with more amplitude (§59, §60) |
| MARKET-GRAPH-1 H1 (LLM-extracted edges predict co-movement) | ΔR² **+0.000968 vs MDE 0.000623, t 4.35**; placebos carry nothing | historical, `Aegis module` | **BANKED, orphaned**: a risk-model result, and no covariance or sizing code consumes it | a min-variance or risk-parity book using the graph covariance vs trailing covariance |
| N6 second-moment regularity | 5d \|return\| IC **0.294** (MDE 0.087) vs sign AUC 0.4967 | 12 securities, 1999–2026 | **BANKED**; the same fact as the investigator's magnitude skill | vol-scaled sizing in a live book |
| Analyst reliability (`RELIABILITY_PERSISTS`) | reliability persists out of sample | 98,772 recs, 5,793 analysts | **BANKED, orphaned** (`actor_corpus/ibes_graded.parquet`; nothing consumes it); ANALYST-SKILL-1 registered 08-31 and **never run** | run ANALYST-SKILL-1 (Q-9) |
| TRIAL-H5 event learner | search +32.2%/yr, t 2.92 → at the registered $10M corner **+20.8%/yr, t 1.14** | 156 blocks | **DEAD** by its own rule | — |
| 13D first filings (TRIAL-EVENT-13DG, 08-02) | +1..+20 **+164 bps, t 4.07**; 13G placebo −35 bps | n 5,542 | **BANKED, stopped before the portfolio step**; the confirm window was never read | the attended confirm read |
| Growth book (09-07) | leverage-neutral TW 4.79 vs SPY 2.09 (development) | 144 months | **DEAD as alpha** (DSR 0.0046, PBO 0.64) | — |
| LEARNER_V2 (09-03) | +9.6%/yr vs v1 champion, **t 1.24** | — | **BANKED, unresolved** | — |
| PC-PAPER (first trades 09-25) | equity **$999,143 (−0.09%)** after day 1 | 10 names, 1 day | **RUNNING** | 21 scored PROBE days |

**The through-line:** every positive number with a real sample is either a **second-moment** result
(investigator magnitude, N6, MARKET-GRAPH-1 H1) or a **replay** that never reached a forward book
(forecast_dispersion, seasonality F, 13D). The things that *trade* are the weakest-evidenced selectors:
the WEAK-calibrated shortlist pickers and the mom_12_1 agency books.

---

## 3. Decisions since August, per surface

| surface | what it decided | what happened after | one-line verdict |
|---|---|---|---|
| **Railway fleet** (hack1/2/4/5/6; `fleet_audit_2026-09-24.json`, `trade_autopsy_2026-09-24.json`) | terminal-repo mandates; 358 closed round trips | equity **$450,994 of $500,000 (−9.8%)**; hack4 **−17.4%**, hack6 −16.3% (81.6% gross), hack1 −7.5%, hack5 −6.7%, hack2 −1.2% (100% cash, **401 since 09-20**); realised **−$39,384**, hit **27.7%**, **−418 bps per position**; 11 of 18 positions older than 14 days | **Losing money on entries and on exits, and it has not changed since the diagnosis** (no terminal-repo commit after 09-20) |
| hack3 / PA3JYEG4DF9G | nothing since the loop was removed 09-22 | −19.2% on 09-22; still open with 9 positions (~$69k) | ownerless; drifts |
| **Decision contract** (`decisions/2026-09-20…25.json`) | 09-20: 4 BUY (CVLG + 3 agency books), 38 REFUSED. 09-21 → 09-24: the **same 38 names × 4 horizons = 152 PROBE** every day. 09-25: 92 PROBE (23 names from the refreshed funnel), 2 REFUSED (ALLE, SON). `roi_ranking.n_considered = 2` on **all six days**; OPTIMUS_BALANCED/AGGRESSIVE/HIGH_CONVICTION **REFUSED every day** | autopsy (h=1 only, vs the universe median): BUY n=4 −0.26%; PROBE n=114 −0.10%; REFUSED n=41 **+0.58%**; **PROBE−REFUSED −0.68%/day, t −0.83 over 3 date blocks**. Refused names that rose: META +9.2% vs median, ANIP +4.7%; NVDA, NFLX and LLY beat the median by 2–9% | **The refusals were better than the probes at 1 day.** Tiny sample, but it is the only decision grade so far, and it points the wrong way |
| **CVLG** (profitability_small BUY 09-20 → 09-24) | BUY 5 days running | 1-day rel: −1.9%, +1.2%, +0.8%, −3.0% | 2 up, 2 down; dropped from the 09-25 contract |
| **Agency personality books** (`AGENCY_BOOK:balanced/aggressive/extreme_growth`, signal **mom_12_1**) | BUY every day, 09-20 → 09-25 (18 rows) | **never graded**: `decision_ledger.score_due` marks agency BOOK rows unpriceable ("priced by its own NAV"), and the autopsy lists `book:BUY 18` as not graded | a daily decision on a signal §59 closed, which nothing grades |
| **PC-PAPER** (`decisions/pc_plan/2026-09-25.json`, `pc_book/`) | PROBE: 10 names × 2% (NVDA, INCY, AAPL, SNDR, META, AVPT, AMZN, GOOGL, GOOG, ALLE); every row carries `ranking_verdict: MEASURED_NEGATIVE` and `probe_verdict: UNMEASURED_TRADE_SMALL, 0 of 21 days` | equity **$999,143** (−$857); a one-share GOOGL churn fixed by `REBALANCE_DRIFT_FRAC` | first trades in the account's life; ungraded until 10-02 (h=5) and ~early November for the gate |
| **LLM books** (`llm_portfolio/books.jsonl`: 16 personal, 10 competition, 96 twins; frozen 09-25) | entry Monday 09-28 open | nothing graded. The reviewer found mean pairwise overlap 0.25 (≈ 4 bets); MRK, ASML, GEV and TSM each sit in 15 of 26 books | a clock, not a result. The competition books are the wrong objective (adjudication row 6) |
| **First books** (paper_books, seeded 09-12, `book_cadence`) | mom_12_1, si_low_turnover_high_v1, two insider clusters, overhang, unconditioned reaction, abstention (+ twins), first_hour_event_intraday | 6 of 8 primaries at **exactly $100,000** on 09-21 (never decided: no permno map, no cluster in window); mom_12_1 **+3.98%** vs beta twin +0.74%; abstention = its twin (+10.1%) | mostly inert. The seeded set includes **si_low_turnover_high_v1, whose own replay is negative (−0.54%/month vs twin, t −2.26)**, while the PRODUCT_PROMISING books were never seeded |
| **Review labels** (`review/review_2026-09-25.json`) | 488 rows: 383 hold, 88 UNPRICED, 15 WATCH, 2 buy_more | ungraded (h=5) | informationless by construction (p = 0.50) |

---

## 4. How the system learned: closed loops vs outcomes nothing reads

### 4.1 Closed loops (a graded outcome changed behaviour)

| # | graded outcome | what changed | where | caveat |
|---|---|---|---|---|
| L1 | §64 personas held-out −28%, disc ≈ 0 | reputation floor → **weight 0.0** for every persona; `RETIRED_WEIGHT_ZERO` list | `forecast_reputation.weights` (floor 0), `scripts/night_investigator_forecast.py:185` | **Saves $0 going forward.** The personas had not written a row since **08-12**. Their 7,267 pending rows keep resolving until 2027 |
| L2 | §64 investigator overconfident (best shrink 0.65) | new rows shrunk: `SHRINK = 0.65` applied at write time | `night_investigator_forecast.py:87, 604, 692` | **Mis-aimed.** The shrink was earned on `abs_move`, and it is applied to `evidence_v2/v3` **`beats_benchmark`** rows, where held-out skill is ≤ 0 and the correct weight is 0 |
| L3 | reviewer 2.1: investigator's 0.42 is magnitude skill | reputation keyed `(arm, observable, horizon)`; `direction_skill`/`magnitude_skill`; E[r]'s direction term reads `beats_benchmark` only | `forecast_reputation.py:191–260`, `expected_return.py` | the 09-25 reputation receipt still publishes **arm-only** weights (D_all 0.42 mixes both) |
| L4 | funnel 44 days stale | `u_funnel` scheduled before `u_rank`; `FUNNEL_STALE_DAYS = 10` | `sim_run.u_funnel`, `investment_committee` | the funnel is fresh (09-24, 25 candidates), but `roi_ranking.n_considered` is **still 2** on 09-25 |
| L5 | §62: all 11 exit rules lose; −2% = 0.93σ | PC-PAPER declares **no stop** (`stop_declared: false`); worst case quoted in sigma | `sim_run.probe_worst_case` | the fleet, which produced the finding, was not changed |
| L6 | §59/§61 ranker net-negative | `u_plan` EXPLOIT refuses; the PROBE gate keys on the **shortlist's own** grade (21 scored days at h=5) | `sim_run._probe_grade`, `_blend_grade` | correct by design; the verdict arrives ~early November |
| L7 | reviewer row 9: SPY benchmark measured size | autopsy benchmark = the time-matched universe median | `scripts/decision_autopsy.py` | flipped PROBE−REFUSED from +0.18% to −0.68% |
| L8 | reviewer row 7: forecast cap cut the core names | cap 60 → 160, priority by book weight | `config.FORECAST_MAX_NAMES_PER_DAY` | — |
| L9 | reviewer row 8: card verdicts ungradeable | 166 `thesis_card:v1` rows | `scripts/thesis_cards.py` | 112 of 166 at p = 0.50 |
| L10 | one-share churn (live) | `REBALANCE_DRIFT_FRAC = 0.10` | `pc_broker` | engineering, not learning |

**Nine of the ten were closed by a human-led session, not by the machine.** L6 is the only rule written to
change itself, and it has not fired yet.

### 4.2 A graded outcome exists and nothing reads it (the concrete "not connecting" list)

| # | the outcome, and the file that holds it | what should consume it | what actually happens |
|---|---|---|---|
| N1 | investigator **magnitude** skill (+5.6% held out h1; recalibrated +8–10%): `predictions.jsonl`, `reputation/reputation_2026-09-25.json → calibration` | position sizing / vol scaling: `pc_broker` sizing, `sim_run.u_plan` `position_budget` (flat 2%), `expected_return` magnitude term | **nothing.** Sizing is flat 2% per name. Reviewer idea A was accepted for "chunk 5" and is unbuilt |
| N2 | 114 graded contract PROBE rows (PROBE−REFUSED −0.68%/day): `decisions/autopsy_2026-09-25.json` | `sim_run._probe_grade` | reads only SCORED rows with `hypothesis_id == C3_committee_shortlist_probe_v0`; `decisions/ledger.jsonl` has **694 DECIDED, 0 SCORED**. Nothing reads `autopsy_*.json` (only its writer references it) |
| N3 | 18 agency-book BUY rows | `decision_ledger.score_due` | marked **unpriceable** on every run: a decision surface that can never be graded |
| N4 | reputation weights and tuned constants: `reputation/reputation_2026-09-25.json` | a pooled forecast that anything reads | `expected_return` computes its own component weights; `investigator_dir` is **asleep** (0 graded `beats_benchmark` blocks). The pooled forecast has **no consumer** |
| N5 | fleet autopsy (−418 bps/position, winners cut at +1.91%, amihud t +2.1 and px_vs_52w t −2.1 as entry discriminators): `fleet_audit/trade_autopsy_2026-09-24.json` | the terminal repo's exit and entry rules | **no commit in `aegis-alpha-terminal` since 2026-09-20.** hack2's counterfactual still censors losses at 1.05× (MEMORY, open for Murat) |
| N6 | forecast_dispersion PRODUCT_PROMISING, seasonality F CONDITIONAL: `first_books/replay/*.json` | `seed_first_books` → paper_books | **never seeded**; the seeded set includes a book whose replay was negative |
| N7 | the ExpeL monthly distillation: `brain/LEARNED_2026-09.md` | `ledger_retrieval.LEARNED_RULES` = `brain/learned_rules.jsonl` | **0 rules, PENDING_MODEL** (local model refused the connection); `learned_rules.jsonl` **does not exist**, so retrieval returns `[]`. The 126 daily `LEARNED_*` lines are heartbeats that repeat the same "NN lab 5 of 12 heads beat on held-out 2026-08" from 09-20 to 09-26 |
| N8 | every nightly measurement | `policy_state` (the declared "night may change preferences" contract) | `pc_book/policy_state.json` and `policy_journal.jsonl` **do not exist**: zero preference changes, ever |
| N9 | thesis-card AGAINST verdicts (AARD, BHVN, CAPR, QUBT, SLDP, SRAD): `thesis_cards/**` | `u_review` labels, the forecast universe, book construction | `review_2026-09-25.json` labels Murat's **BHVN, QUBT, SLDP "hold"** and AARD UNPRICED; CAPR stays in 5 frozen books at 1–4% |
| N10 | calibration verdicts **WEAK** for both shortlist pickers: `calibration/*_2026-09-22.json` | the shortlist's picker labels and weights | the shortlist still prints `insider_opportunistic: SUPPORTED/PICKER, weight 0.5` and `profitability_small: SUPPORTED/PICKER, weight 0.7` on every PC-PAPER row |
| N11 | MARKET-GRAPH-1 H1, N6 second moments | a covariance / risk model | none |
| N12 | `RELIABILITY_PERSISTS` (`actor_corpus/ibes_graded.parquet`); 393,369 revisions | analyst-skill weighting (Q-9) | never run (ROADMAP_2026-09-25 §1.2) |
| N13 | h=1 forecasts due from 08-18 | `forecast_grader.grade_due` on a daily clock + the scoreboard | first graded on **09-20**, first read on **09-24** |
| N14 | the forecast ledger itself | a "forecasts stopped" alarm | accrual stopped 08-28 → 09-24 with no red row; `forecast_accrual` was added only on 09-25 |

---

## 5. Clashing strategies

| # | clash | evidence | designed or accident? |
|---|---|---|---|
| C1 | **Ranker refuses, shortlist probes.** Every PC-PAPER row carries `ranking_verdict MEASURED_NEGATIVE (−1.09%/21d)` and trades anyway | `decisions/pc_plan/2026-09-25.json` | **Designed** (PROBE licence, separate gate) — but it has **no control arm** of its own. The only comparison, PROBE vs REFUSED, is negative so far (−0.68%/day, 3 blocks) |
| C2 | **Contract REFUSED ALLE, PC-PAPER bought 131 ALLE** the same day | `decisions/2026-09-25.json` (ALLE REFUSED, EDGE_BELOW_BAR, insider t 1.40 < 2.0) vs `pc_book/state_latest.json` | **Accident**: two writers read one shortlist under two rules, and neither sees the other |
| C3 | **Calibration says WEAK; the shortlist says SUPPORTED/PICKER** for the same two signals | `calibration/insider_opportunistic_2026-09-22.json` (net −0.05%, t −0.35) vs shortlist reasons | **Accident**: the labels predate the calibration |
| C4 | **Agency personalities BUY a mom_12_1 book daily; committee personalities REFUSE daily; §59 says momentum is dead** | `decisions/*.json` BUY `AGENCY_BOOK:*` (signal mom_12_1) vs `OPTIMUS_* REFUSED` vs NEGATIVE_RESULTS §59 finding 3 | **Accident**: two "personality" implementations, and the agency rows can never be graded (N3) |
| C5 | **Thesis card AGAINST vs held**: CAPR in v1 and 4 factory books; QUBT in v1; BHVN, QUBT, SLDP, AARD in Murat's book labelled hold | cards; `books.jsonl`; `review_2026-09-25.json` | v1 holding CAPR/QUBT is **designed** (v1 is the un-reviewed control). The review label ignoring the card is an **accident**, and so are the factory books |
| C6 | **VRT 12% in v1 and v2** vs our own data (mom_63 −30%, net raises −4 of 5, three target cuts 07-30) and the reviewer book, which excludes VRT and MU | REVIEW §2.2; `books.jsonl` | **Designed** as arms (reviewer book frozen with twins). The v2-minus-VRT twin the review proposed was **not built** |
| C7 | **v1 vs v2**: v2 drops ALB, CAPR, ENS, GILD, QUBT, RGTI, SLI, TER; adds AVGO, CLS, BE (no card); reweights TSM +2, NOVT −3, COGT +2 | `books.jsonl` | **Designed** (v1 keeps running as the control). The added names have no card, so the "human edits" arm tests a GPT review, not Murat |
| C8 | **Investigator magnitude skill vs direction use.** The shrink earned on magnitude is applied to direction rows; E[r] had planned to read it as direction | §1.3; `night_investigator_forecast.py:604` | **Half-fixed**: E[r] separated them (L3), but the forecast writer did not |
| C9 | **Competition vs personal books on the same tickers**: pairwise overlap 0.37–0.80 per strategy pair; MRK, ASML, GEV, TSM in 15 of 26 | REVIEW §2.3; `books.jsonl` | **Accident** (one `evidence_pack.json`, one model); accepted in the adjudication (relabel `rehearsal_wrong_objective`) |
| C10 | **ESG gambling exclusion vs DKNG** (v1/v2 3%, Murat's 150 shares) | `agency.py` ESG_CATEGORIES | **Not live**: an opt-in vocabulary, and no book declares `ESG_EXCLUDE:gambling`. DKNG's 3% is holding bias contaminating the "human edit" grade (reviewer 2.2) |
| C11 | **`pm_engine` vs `investment_committee.compose_book` vs `u_plan`**: three allocators | ROADMAP_2026-09-25 §1.1 | **Accident / dead code**: only `u_plan` reaches `pc_broker.submit()`. The other two are router- or CLI-only, and nothing grades them against each other |
| C12 | **Fleet (Railway) vs PC-PAPER**: different selectors, different repos, different capital, no common grade | ACCOUNTS doc; fleet audit | **Accident**: no shared benchmark or start date, so "which executor is better" cannot be answered. No ticker overlap today except BE (hack5 call spread; v2 at 4%) |
| C13 | **First-books seeding vs replay verdicts**: seeded si_low_turnover_high_v1 (replay t −2.26), left out forecast_dispersion (t 5.65) | `first_books/seed_receipt.json` vs `first_books/replay/` | **Accident** (seeded 09-12; the PROMISING reads came 09-13, and nothing re-seeded) |
| C14 | **Abstention book vs its always-invested twin**: identical NAV $110,099 | `book_cadence/2026-09-24T234923Z_monthly.json` | **Designed**, and so far uninformative: the gate has not fired |

**Count: 5 designed (C1, C6, C7, C14; C5 in part), 9 accidental (C2, C3, C4, C9, C11, C12, C13, and the
parts of C5 and C8 that no one decided).** The designed ones are graded against each other through twins
from Monday 09-28 on. The accidents have no grading between their two sides, and that is what makes them
feel like "strategies clashing": nothing ever decides which side was right.

---

## 6. What would close the three most important open loops (proposals, not executed)

1. **Aim the skill we have at the decision that can use it.** Size PROBE names by the investigator's
   `abs_move_exceeds` probability (inverse predicted |move|), and stop shrinking direction rows by a
   magnitude-earned 0.65 (write `beats_benchmark` rows at p = base until they earn a weight). Settles on
   the h=1/5 grades of the 09-25 rows.
2. **One decision grade for every surface.** Let `_probe_grade` read the autopsy's contract PROBE rows (or
   write them SCORED), give agency BOOK rows a NAV grade, and add one daily line: PROBE vs REFUSED vs
   agency vs fleet vs PC-PAPER, all against the same universe median.
3. **Seed what the replays promoted.** Put forecast_dispersion_v1 and seasonality_11_20_v0 in paper_books
   with twins, take si_low_turnover_high_v1 out of the "promising" list, and hand the fleet autopsy to the
   terminal repo as a proposal (winners are cut at +1.91%; stops are refuted).

Receipts read: `predictions.jsonl` (snapshot, 26,148 rows), `reputation/reputation_2026-09-25.json`,
`specialists/scoreboard_2026-09-24.json`, `decisions/2026-09-20…25.json`, `decisions/pc_plan/2026-09-25.json`,
`decisions/autopsy_2026-09-25.json`, `decisions/ledger.jsonl`, `fleet_audit/fleet_audit_2026-09-24.json`,
`fleet_audit/trade_autopsy_2026-09-24.json`, `first_books/{seed_receipt.json,replay/*.json}`,
`book_cadence/2026-09-24T234923Z_monthly.json`, `backend/data/aegis_pi.db:paper_books` (read-only),
`calibration/*_2026-09-22.json`, `llm_portfolio/books.jsonl`, `thesis_cards/**`, `review/review_2026-09-25.json`,
`pc_book/{state_latest.json,nav.jsonl}`, `brain/LEARNED_*.md`, `funnel_night10.json`;
NEGATIVE_RESULTS §59–§64; RESEARCH_QUEUE; the 09-25 handoffs, review and adjudication;
ROADMAP_2026-09-25_CONNECT_WHAT_EXISTS; ACCOUNTS_2026-09-22; RESULTS SCOREBOARD / RESULT IMPROVEMENT lines
from dated docs 08-25 → 09-25 (every one reads NONE, except §64 and the 09-25 "gradeable decisions" line).
