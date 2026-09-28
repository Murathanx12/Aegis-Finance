# REVIEW 2026-09-28 — an adversarial investor on the project, and on the outside reviewer who scored it 72

Reviewer role: a sceptical allocator asked whether to put real money behind Aegis. Default answer: NO.
Read-only session. Nothing was built, run, committed or changed except this file. No factory, sim,
daily pass or suite was run. Every number below comes from a file named beside it, or from a
read-only Python load of a receipt already on disk. Anything I could not verify is marked
**UNVERIFIED**. This document carries no licence: it is a review, not a claim.

## RESULTS SCOREBOARD

| line | state on 2026-09-28 | source |
|---|---|---|
| best historical net strategy vs market | **None survives.** Best DSR is 0.198 nominal / 0.62 effective (0.95 needed). The dev-selected top-10 lose to their matched twins in 2024-26 (median **−1.45 pp/yr**). The two rows that win share one lucky quarterly calendar (§1). | `strategy_library/leaderboard_2026-09-27T082553Z.json`, `signal_structure/matched_twins_2026-09-27T082553Z.json` |
| best forward paper strategy | None gradeable. 0 of 57 frozen books graded. Of 33 priced accounts, **6 are ahead of SPY and 27 behind**; pooled **−0.27%** | `docs/PAPER_ACCOUNTS.md`, `learning_reports/report_2026-09-27.json` |
| the fleet (other repo) | **−9.8% / −$39k realised, 27.7% hit rate** | `docs/reviews/ADJUDICATION_2026-09-26_AUDIT_SINCE_AUGUST.md` row 6 |
| what trades today | PC-PAPER holds 10 × 2% PROBE names: NVDA, INCY, AAPL, SNDR, META, AVPT, AMZN, GOOGL, **GOOG**, JAZZ. 78% is cash. EXPLOIT is refused (ranker MEASURED_NEGATIVE). | `pc_book/2026-09-27/intended_book.json`, `sim/session.json` |
| expected-return layer | **0 graded dates for all 6 components at every horizon** | `expected_return/refit_2026-09-28.json` |
| independent selectors | 288 rules ≈ 79–216 bets, depending on the cut. The forward lib books = **18 bets** | `docs/BRIDGE.md` header |
| new actionable findings (this review) | (1) `disp_short_avoid`, one of the two "leads", rebalances on the same Jan/Apr/Jul/Oct calendar as the +1,323% row, and nobody ran an offset control on it. (2) The rehearsal and core-satellite books tilt on "fundamentals". On the data that trades, §60 measured that signal at **−1.34% per 21 sessions, t −2.55, last of six**. (3) The mandate's "REFUSED" status is printed but never enforced. | §1, §2, §5 below |
| LLM spend (this review) | $0 | — |

**RESULT IMPROVEMENT: NONE.**

**Verdict.**
- After six months, 1,889 commits and ~530,000 lines of Python, nothing on disk shows that Aegis has a positive expected return after costs. The strongest candidate is a published factor, 12-1 momentum, seen in hindsight. Its headline +1,323% is the luckiest of three calendar offsets of that factor.
- The real asset is a forecast ledger written before outcomes, graded with unusual honesty. But the ledger's one positive result is beaten by a trailing-volatility formula. The live money path is 20% mega-cap beta, picked from a list sorted on a signal the project itself closed.
- The outside reviewer's 72/100 grades effort and self-description, not evidence. Its roadmap would add six more machines to a project whose problem is too many machines.

---

## 1. IS THERE ANY EDGE AT ALL?

**The strongest evidence on disk** is `dev_selected_sealed_evaluated` in
`leaderboard_2026-09-27T082553Z.json`. Rules were chosen on pre-2024 results alone and read on 2024-26:

- top-10 mean **+8.8 pp/yr** vs SPY;
- median **+2.6 pp**;
- 6 of 10 beat SPY.

It is the only number in the library that was not chosen on the window it is read on. Everything else, including "+1,323% since 2020", is hindsight on rules registered 2026-09-26. The same receipt's `read_me_first` says so.

**How I destroy it, one test at a time.** All figures come from read-only loads of the receipts named.

| test | result | verdict |
|---|---|---|
| What are the ten? | `insider_mom, mom_no_downgrades, mom_no_rating_downgrade, mom_12_1, px_vs_ma200_large, disp_short_avoid, mom_no_downgrades_small, mom_6_1_large, mom_12_1_small, mom_12_1_q`. **Every one has a momentum or trend leg.** The bridge puts the momentum books in one cluster (cluster 170). | ONE bet counted ten times |
| vs matched twins (size × vol × 12-1 tercile), 2024-26 | rule − twin: −11.1, −3.4, −14.1, +4.0, −2.9, **+22.1**, −3.3, −0.0, +5.9, **+44.2** pp/yr. **Median −1.45 pp**, mean +4.1 pp. | two rows carry the mean |
| which two? | `mom_12_1_q` and `disp_short_avoid`. In `holdings_2026-09-27T082553Z.parquet`, **both change names only in months 1/4/7/10**. The panel starts 2017-01-31, and every hold-3 rule inherits that calendar. | **one calendar offset** |
| the offset control (`mom_12_1_q_{jajo,fman,mjsd}`, controls block) | 2024-26 vs SPY: JAJO **+37.9 pp**, FMAN **−5.0 pp**, MJSD **+8.4 pp**. Cumulative since 2020: **+1,323% / +424% / +433%**. | the headline is the best of three draws |
| the other eight, vs their twins | mean **−3.1 pp/yr** | negative |
| by year keyed on the HOLD month (`by_year_hold`) | `mom_12_1_q` 2020 excess **+87 pp**. `mom_12_1`: 2020 **+98 pp**, 2024 **−19 pp**. | one year carries the story |
| worst leave-one-year-out (hold-keyed) | `mom_12_1_q` +1.8%/mo, `mom_12_1` +1.3%/mo | survives: the one test it passes |
| without the best 5 months | `mom_12_1` CAGR **14.6%** vs SPY 15.3%: below SPY. `mom_12_1_q` 22.0%: still above an unstripped SPY. | monthly momentum dies; the lucky offset survives |
| vs the panel's random portfolio | `random_1` and `random_2` lose **10.6 pp/yr** to SPY in 2024-26. Every "vs random panel" figure (the README's "137 rules") is therefore ~7–11 pp more generous than vs SPY. | flattering if used as the headline |
| 2024-26 matched-twin t, all 288 cells | **9** cells at t ≥ 2, **8** at t ≤ −2 | symmetric: exactly what noise produces |
| DSR | best nominal 0.198 (`mom_12_1_q`), effective 0.62; nothing reaches 0.95 | fails the multiple-testing bar |
| survivorship | The factory reads the survivorship-free bars (`xs_ranker.survivorship_audit`: 32.8% of symbols stop trading early). Each momentum rule has 9–18 delisting fills at a 30% fill. | adequate; not the problem here |
| the one "GO" outside momentum | Fundamentals made +39 bps/mo on the JKP panel (`xs_ranker/fundamental_amplitude_2026-09-22.json`). On our own tradeable panel: **−1.34% net per 21 sessions, t −2.55, last of six, negative at every k** (`xs_ranker/bakeoff_fundamentals.json`, commit `3255206b` "§60"). | closed by the project itself |

**In one sentence:** nothing survives. What remains is textbook 12-1 momentum, which you can buy for
15 bps a year in MTUM. The only rows that beat their twins in both windows share one quarterly
calendar that nobody chose in advance.

**Where the outside review flatters (item 1).** It attributes "+1,323% since 2020 vs SPY +162%" to
12-1 momentum.

- Monthly 12-1 momentum is **+692%** (`hindsight_cum_since_2020` 6.92).
- +1,323% is `mom_12_1_q` = `mom_12_1_q_jajo`, the best of three offsets. The three-offset average is **+727%**.

Its line "you now have the kind of 1,000% vs 162% backtest you wanted" is the most dangerous sentence
in its report. It hands the owner a hindsight number that the repo's own `read_me_first` forbids
quoting, three weeks before a contest.

---

## 2. THE LIVE MONEY PATH

Traced from `scripts/sim_run.py:943` (`u_plan`) to `pc_broker.submit()` (`backend/services/pc_broker.py:501`):

1. **Bars gate** (`sim_run.py:1031`, `bars_gate`): `BARS_FRESH`, newest bar 2026-09-25, limit 2 sessions. OK.
2. **EXPLOIT** reads `ranking.json` (`top20_net_rel_21d`). The verdict is **MEASURED_NEGATIVE**, so `may_trade=False`
   (`sim_run.py:1055–1061`). EXPLOIT is dead. Its E[r] alternative (`sim_run.py:1153`) prices nothing (step 6).
3. **PROBE** calls `investment_committee.shortlist()` (`investment_committee.py:195`), which reads
   `backend/data/funnel_night10.json`.
   - **Age and size:** generated 2026-09-24T02:48Z, 3.9 days old, **25 candidates** (`sim/session.json` funnel unit; file loaded read-only).
   - The file says `evidence_basis.ranked_by = ["profitability_small"]`. Yet its top nine are NVDA, INCY, AAPL, SNDR, META, AVPT, AMZN, GOOGL and GOOG.
   - Every candidate's `why` list only says "liquid … cleared the retail liquidity gate".
   - Scores are an evenly spaced rank ladder (1.000, 0.982, 0.964 …).
   - **The ranking input is a profitability sort that §60 measured negative on the tradeable panel, and its output is mega-cap tech.**
4. **Contract exclusions:** the day's decision contract removed 2 names (`contract_refused_excluded: 2`).
5. **policy_state** (`sim_run.py:1115`) is read and **used for nothing**: `order_source: "shortlist order
   (no shortlist name carries a contributing component)"`, weighting `equal`.
6. **E[r]:** in `expected_return/refit_2026-09-28.json`, all six components (`ranker, revision_flow,
   investigator_dir, thesis_card, catalyst, source_reliability`) show `n_dates: 0, graded: false,
   rep_weight: 0.0` at h5 and h21. The TIER-0 pipeline box "REPUTATION → E[r]" carries zero information.
7. **PROBE grade:** `probe_verdict: UNMEASURED_TRADE_SMALL`, `probe_acting: true`. PROBE trades
   *because* it is unmeasured, and keeps trading until 21 sessions exist.
8. **Sizing:** `PS.probe_weights` is equal weight, 10 × 2% = 20% gross (`config.PROBE_MAX_WEIGHT 0.02`,
   `PROBE_MAX_NAMES 10`, `PROBE_GROSS_CAP 0.20`). **GOOG and GOOGL are both held, so one company is 4%.**
9. **Broker:** `pc_broker.plan_orders` → `submit`, with limits `MAX_INVESTED_FRAC 1.00`, `MAX_NAME_FRAC 0.12`,
   `MAX_ADV_PARTICIPATION 0.02`. Account `PA37CSAUFCQR`: equity $999,054, 11 positions, 21.8% invested
   (`sim/session.json` reconcile).

**Inputs that are stale, empty or ignored:**
- The funnel is 3.9 days old. That is fresh by its own 10-day rule, but it is ranked on a closed signal.
- E[r] is empty on all 6 components.
- policy_state is ignored.
- The forecast unit reports `REFUSED_CAP, n_rows_written 0, DEGRADED`.
- The learn unit reports `DEGRADED rc 3 — no new graded rows since 2026-09-26`.
- The ranker measured negative.

**So what actually decides an order today is the top of a 25-name, profitability-sorted liquidity list, equal-weighted.**

**The mandate refusal does not refuse.**
- `decision_contract.account_mandate` returns `status: "REFUSED"` on `decisions/2026-09-28.json`. It finds three capital bases ($40,000 / $1,000,000 / $999,054), four per-name caps (2% / 3% / 10% / 12%) and several gross caps (0.10 / 0.20 / …).
- Its own docstring (`decision_contract.py:673`) says: "No limit is changed here."
- `u_plan` never reads it: `grep mandate scripts/sim_run.py` finds one comment line.

A REFUSED mandate printed beside `probe_acting: true` is a red line that teaches the reader to skim red
lines. It is CLAUDE.md's "gate that cannot go green" family, inverted.

**Worst case in dollars (protocol item 4), for the largest book this account admits:**

| book | n × notional × move | Σ\|notional\|/equity | dollars on $999,054 |
|---|---|---|---|
| PROBE as configured | 10 × 2% × 8.23% (3σ of 2.74%/day) | 0.20 | **−$16,436** in a 3σ day. **No stop declared**, so the ceiling is −$199,811 (plan receipt). |
| PROBE + EXPLOIT, as the code permits | 10 × 2% + 18 names sharing 80% at ≤ 10% each | **1.00** | 3σ day at the 2.16% reference σ: **−$64,700**. At the book's 2.74%: **−$82,100**. One 10% name to zero: −$99,905. No stop, so the ceiling is −$999,054. |
| broker hard limit | `MAX_INVESTED_FRAC` 1.0 × `MAX_NAME_FRAC` 12% | 1.00 | largest single name to zero: **−$119,886** |

No code path allows leverage (`assert MAX_INVESTED_FRAC <= 1.0`, `pc_broker.py:124`). The account
shows $3.76M of buying power, so that assertion is the only thing between it and 3.8× gross.

---

## 3. COMPLEXITY AS A COST

| count | value | source |
|---|---|---|
| files under `docs/` | **791** (324 top-level) | `find docs -type f` |
| roadmaps / handoffs / reviews (all of `docs/`) | 25 / 68 / 16 | `find docs -name ...` |
| services | **284** `.py` in `backend/services/` (175,393 lines) | `ls`, `wc` |
| scripts | **405** `.py` (186,012 lines) | same |
| tests | **614** files, 169,282 lines, **11,729** tests passing | handoff 09-28 §0 |
| commits | 1,889 since 2026-03-28; **248 since 09-20** | `git log` |
| distinct paper books | **308** `llm_portfolio` rows (62 parents, 245 twins, 1 void), plus 33 priced accounts (website lanes, night books, murat_live), plus 3 agency proposals. They sit in **six separate book ledgers**: `paper_books`, `llm_portfolio`, `pc_book`, website lanes, `agency`, and the other repo's arena. | `llm_portfolio/books.jsonl`, `docs/PAPER_ACCOUNTS.md` |
| twin types | 9 (`ew, sector_etf, spy, iwm, urth, random_same_band, matched_random, ranks_k1_2k, next_k`) | `docs/PAPER_ACCOUNTS.md` |
| health probes | 44 (0 DEAD / 13 STALE / 6 UNKNOWN / 25 ALIVE on first run) | wave-2 handoff §8 |

**Is it producing knowledge or artefacts?** Artefacts. The last month's knowledge fits in ten lines:

1. Personas have negative skill.
2. The investigator's skill is magnitude only, and trailing σ63 does better.
3. Price/volume cannot rank at 21 days.
4. Fundamental ratios did not replicate.
5. Broker identity is a coin flip.
6. First-mover raises are look-ahead.
7. The analyst-skill filter works only in 2025.
8. Momentum is a regime.
9. One quarterly calendar carries the best rows.
10. The Dow Jones sources cannot be judged on 9 dates.

Every one of these is a *closure*, and closures are valuable. But roughly 20 modules produced them.
The other ~260 services produced receipts about themselves.

**Ten modules I would DELETE (or freeze read-only), and what would be lost:**

| # | module | lost |
|---|---|---|
| 1 | The browser reading lane: `scripts/dowjones_pull.py` (2,228 lines), `backend/services/web_reader.py` (1,380), `scripts/night_reader_supervisor.py`, `scripts/chrome_consent_watcher.ps1`, `scripts/three_source_compare.py` | 158 articles and 0 gradeable sources (0 of 60 scorecard cells). The lane also puts a Dow Jones account at ToU §9.4.1 risk, and its agent auto-approved remote debugging on Murat's **main** Chrome and signed WSJ in through his Google account (wave-2 handoff §18, §21). Replace it with the paste inbox that already exists. |
| 2 | `backend/services/openclaw_client.py` (1,512) as a nightly dependency | an unattended night that read for 44 minutes out of 6.5 hours (handoff 09-28 §2.10) |
| 3 | the persona arms in `backend/services/llm_swarm.py` | 15 arms with held-out skill between −0.21 and −0.70 and weight 0 (`reputation/reputation_2026-09-27.json`). They are already worth nothing. |
| 4 | `scripts/thesis_cards.py` (1,157) | cards at p = 0.50 on 112 of 166 rows (`ADJUDICATION_2026-09-26_AUDIT_SINCE_AUGUST.md` row 4); LLM direction skill is −7.9% |
| 5 | `backend/services/pm_engine.py` (961) | books "nobody grades", in TIER 0's own words (`AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` §6) |
| 6 | the `investment_committee.compose_book` path | same as #5 |
| 7 | `backend/services/paper_books.py` (924), the night books | 9 parents with 3 marks each; several never invested (+0.00% since 09-11); `llm_portfolio` duplicates them |
| 8 | `backend/services/agency.py` (2,664) | three "AGENCY_BOOK" proposals marked `expected_payoff NOT CALIBRATED`, with no NAV path |
| 9 | `scripts/always_on_lab.py` (3,014) | a lab that spent ~$2.6/day unwatched; its L2 job waited 8.5 h for a model nothing started (wave-2 §14–15) |
| 10 | `scripts/portfolio_farm_*.py` (11 scripts) | nothing: `night_backtest_factory` + `strategy_library` superseded them |

**Work done three times or more:**

- **Fundamentals:**
  - 09-22: GO at +39 bps.
  - 09-24: §60 closed it at −1.34% (`3255206b`).
  - 09-27: resurrected as "the only positive directional tilt" in the Bloomberg rehearsal and as the core-satellite sleeve (`REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md` lines 370, 409, 420).
  - Neither book doc mentions §60, and `MEMORY.md` still says "Fundamentals = GO (39 bps/month, stable across k)".
- **Investigator direction vs magnitude:** found by the reviewer, then by the audit ("the second time this week the same fact surfaced", audit adjudication row 2), then again by the vol-prior reviewer.
- **Stale inputs:** the funnel (42 days old, found 09-22), the bars (09-21 → 09-26), the ranking on 09-21 bars (09-26), and the library books on 09-21 bars (`freeze_gate`: 0 of 20 pass).
- **The browser attach:** fixed by hand twice on 09-27, then left to a supervisor that could not fix it.
- **Receipts that became false:** one overwritten in place (09-26), 13 zero-byte files after the disk filled (09-27), and a 25-name facts table that produced +149% (09-26).
- **TIER 1 roadmaps:** 09-04, 09-07 (×2), 09-08, 09-10, 09-11, 09-25 (×2). That is seven "current plans" in three weeks.

---

## 4. FORWARD MULTIPLE TESTING

- **Forward books:** 62 parents (47 personal including lib, 11 competition, 4 `__control`) and 245 twins
  (`books.jsonl`), plus the 33 priced accounts already running.
- **Families / distinct bets:** the 31 lib books are **18 bets** (`docs/BRIDGE.md`). The 20 personal and
  11 competition books are ten themes written twice, plus v1/v2, cards, reviewer, three PROBE weightings
  and core-satellite. My estimate is **~35–40 distinct bets** across all parents. This is UNVERIFIED as a
  clustered count: nobody has clustered the non-lib books.
- **Registered before entry:** all 62 were frozen before the 09-28 open (asof 09-25..27), so no book was
  back-dated. But **only 7** carry a declared pass/fail forward test: the 5 family-pool leads, the
  rehearsal and core-satellite. `books.jsonl` has no declared-test field on any row.
- **Luck, computed.** The median monthly active σ of a k = 20 library book vs SPY is **5.35%**, and the median
  pairwise correlation of active returns is **0.30** (`monthly_returns_2026-09-27T082553Z.parquet` vs
  `etf_monthly.parquet`). Simulating zero-skill books at that σ and ρ over one month (21 sessions):

| number of bets | E[best book − SPY] | P(best ≥ +5 pp) | P(best ≥ +2σ ≈ +10.7 pp) |
|---|---|---|---|
| 7 (the outside reviewer's new accounts) | +6.1 pp | 60% | **13%** |
| 18 (lib bets) | +8.1 pp | 80% | **24%** |
| 62 (all parents, if independent-ish) | +10.4 pp | 94% | **46%** |

So on 2026-10-26, the best book will almost certainly beat SPY by 5+ pp **with zero skill**, and it has
roughly a coin-flip chance of looking like a 2σ result.

The bridge's own rule is the only defence: a lead must beat its matched twin at 21 and 63 sessions with
z₆₃ ≥ 1. It must be applied to every parent, not just seven, and the first reading must be printed with
the table above beside it.

---

## 5. THE GRADING ITSELF: where the graders flatter

1. **The random-panel ruler.** Random controls lose 10.6 pp/yr to SPY in 2024-26 (`random_1` and `random_2`
   in the controls block). "Beats the panel's random portfolio" (README: 137 rules) is the easiest of
   three benchmarks by 7–11 pp. It is correct as a *control* and flattering as a *headline*.
2. **Calendar alignment is not controlled.** Every hold-3 rule starts on the panel's first month
   (2017-01-31, which puts it on the JAJO calendar). Only `mom_12_1_q` got the offset triplet.
   `disp_short_avoid`, `qc470_mom252_quarterly_riskparity` and (mostly) `mom_12_1_q_trend` did not, and
   two of those are "leads" now on the forward clock (`docs/BOOK_2026-09-27_LEADS_FROM_THE_FAMILY_POOL.md`).
3. **The process-beats-persona pitch leaves out the comparator that beats the process.**
   - TIER 0 (`AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` §8) quotes +8.97% vs −27.98%.
   - The investigator's skill is magnitude only; on direction it is −8.7%.
   - On the same questions, a free trailing-63-day-vol formula scores **+10.2% vs +5.7%** and wins 7 of 8 days (`ADJUDICATION_2026-09-26_WAVE1.md` row 3).
   - The pitch has not been corrected.
4. **Few independent observations sold as many rows.** The 468 investigator rows are 5 arms answering the same
   questions on **8 dates**. Arm correlation is 0.70–0.93, i.e. about 1.5 independent forecasters (audit
   adjudication row 3). "17,484 graded" is the ledger's row count, not its information content.
5. **Horizons that have not elapsed.** 9,011 of 26,631 forecasts are not yet due (`report_2026-09-27`).
   Skill is therefore dominated by h = 1, exactly where volatility clustering makes magnitude easy.
6. **LLM-extracted claims graded as the source's words.** The source scorecard's Dow Jones leg grades
   DeepSeek's reading of a column, and no human-labelled sample exists (handoff 09-28 §5 R6). "WSJ hit 0.56"
   is partly a grade of DeepSeek.
7. **Controls that are not alive.**
   - Four night books ("Insider SAME-DAY clusters – the falsifier", "Low short interest…", "Good-news names…", "UNCONDITIONED reaction book") read **+0.00% since 09-11**. They never invested, yet they count among the "27 behind SPY" as if they were strategies.
   - "Cash/index by default" and its "Always invested" comparator both read exactly **+7.04%** after 3 marks. Either the book deviated fully into the comparator or the join is wrong (**UNVERIFIED**). A cash-or-index book beating SPY by 5.9 pp in two weeks needs checking before anyone quotes it.
8. **The wrong ruler for the contest rehearsal.** The rehearsal (US small/mid) is graded against URTH
   (developed large/mid). In a small-cap rally it "wins" on size beta alone. The IWM twin is the honest
   comparator and must be read first.
9. **The rehearsal's own test cannot inform.**
   - Its 10-26 check is "move-size rank ρ ≥ 0.3" over **ten names**. At n = 10, the standard error of a rank correlation is ≈ 0.33.
   - Its second check is "realised exposure within ±0.3" for a 21-session beta that, by the doc's own account, carries ±0.5 error (`BOOK_2026-09-27_BLOOMBERG_DRESS_REHEARSAL.md`, wave-2 §12).
   - Either outcome of either check is compatible with anything.

---

## 6. THE BLOOMBERG TRADING CHALLENGE

Rules: Oct 12 – Nov 13; register by Oct 5; scored on relative P&L vs WLS; ≤ 20% per name; long-only;
fully invested within the first week.

**The utility I assume:** U = 1{finish in the top 3% of the field}.
- A placing is what goes on a CV, and it is what the owner said he wants.
- Losses cost nothing real: this is $1M of notional in a game.
- Under that utility, drawdown control, stops and diversification are worth **zero**.
- Variance is worth something whenever the expected relative return is below the placing threshold. The project's own estimate of that return is "≈ 0 ± 11%" (`ADJUDICATION_2026-09-27_…` row 8).

**Placing thresholds on record** (`ROADMAP_2026-09-25_CONNECT_WHAT_EXISTS.md` §1.5): top 3% at
**+5.3%** (USF 2025) and **+20.5%** (Iona 2024); winners at +67.7%, +168% and +400%.

**Is the rehearsal book a sensible entry?** No, and its own design note shows why. It declares
"maximise P(top decile)", and then:
- (a) **halves the allowed concentration**: 10 × 10% "because the brief says ≤ 10%; the verified rule cap is 20%" (review line 372);
- (b) tilts on a fundamentals score that §60 closed as negative;
- (c) carries an unplanned **MTUM β of −0.73**;
- (d) is US-only against a global benchmark.

Its σ over the window is ~8–12%. Under a zero-mean normal approximation, P(relative return > threshold):

| book σ over the window | P(> +5.3%) | P(> +20.5%) |
|---|---|---|
| 8% (rehearsal, as frozen) | 25% | **0.5%** |
| 11% (rehearsal, as designed) | 32% | **3%** |
| 20% (5 × 20%, high-σ names, ρ ≈ 0.3) | 40% | **15%** |
| 30% (5 × 20%, one correlated theme) | 43% | **25%** |

Normal tails understate single-name right skew, which only strengthens the case.

**What I would enter instead:**
- Five WLS-verified small caps at **20% each**.
- Each has a scheduled binary event inside Oct 12 – Nov 13 (a Q3 print or a PDUFA date).
- Pick the **highest idiosyncratic σ63**, deliberately **in one theme**, so the outcomes do not diversify each other away. Examples: five small-cap biotechs with dated catalysts, or five high-short-interest small caps reporting in the same week.
- Rotate each name into the next un-printed catalyst the day after it prints.
- **No stops.** A stop sells variance at the worst price.

Expected relative return is ≈ 0 or slightly negative (the lottery-stock premium). P(top 3%) is roughly
5× the rehearsal's. It also loses more often, and under the stated utility that is correct.

**If the owner's utility is instead "don't embarrass myself: top quartile",** the answer is still more
variance than the rehearsal, because the quartile threshold is also above a zero-edge expectation. A
moderate book (8 × 12.5%) is defensible.

**Choose one utility in writing before Oct 5.** The roadmap already says both cannot be one book (Lane K).

Two things are still open:
- The WLS membership of every candidate is unchecked (handoff 09-28 §7.8).
- Registration status is ambiguous between the two handoffs: "signed up 09-26" in wave-2 §5 vs "register by Oct 5" in 09-28 §7. **UNVERIFIED**; resolve it first.

---

## 7. THE OUTSIDE REVIEWER'S ROADMAP

| item | moves demonstrated edge? | cheapest experiment that decides it before building |
|---|---|---|
| **P0 OpenClaw always-on, persistent client** | **No.** What limits grading a source is the number of publication DATES (WSJ needs ~110 and has 9; handoff 09-28 F1), not reading hours. Always-on also means an agent with remote-debugging access to the owner's main Chrome; it has already signed WSJ in through his Google account (wave-2 §18). `HANDOFF_PC`, the gate file the consent watcher reads, is still on disk (mtime 2026-09-27 22:54). Whether the watcher is still running is **UNVERIFIED**. | Paste 100 July–August archive articles (outcomes already known) into the existing digest inbox by hand. Run the existing scorecard once, with the drift control. If no cell leaves `TOO_FEW`/`BETA_EXPLAINS`, the lane is closed and nothing gets built. ~1 day, $0. |
| **P1 real-time Telegram alerts on ~12 components** | **No.** None of the six E[r] components has a graded date (`refit_2026-09-28.json`), so an alert on an ungraded score is just noise delivered faster. The Telegram agent was also dead for four days while `stack_health` said ready (wave-2 §8). | Score the last 30 days of what the alert *would* have fired on against outcomes. If the top-decile alert set does not beat its matched twin, do not build. ~0.5 day. |
| **P2 Marginal Decision Contribution as TIER 0** | **No, and it cannot be estimated.** It is a forecast-encompassing / partial-regression test (Chong–Hendry 1986; Harvey–Leybourne–Newbold 1998) under a new name. At the sample sizes on disk: E[r] components have **0** graded dates; the investigator arms are ≈ 1.5 independent forecasters on 8 dates; library rules have an MDE of **2.46%/mo** on 32 blocks. Conditioning on correlated incumbents inflates that MDE by √VIF: at ρ 0.8 / 0.9 / 0.95 it becomes **4.1 / 5.6 / 7.9 %/mo**, and momentum members sit at ρ 0.83–0.97. MDC would return "cannot distinguish" for every row for years. | Compute it once on the existing library, for the momentum cluster only. If every member's incremental alpha is CANNOT_DISTINGUISH (it will be), add it as a column in `BRIDGE.md` once ≥ 60 graded dates exist, not as a tier. ~0.5 day. |
| **P3 replicate five finalists in QuantConnect LEAN** | **No.** The defects found in this library were hindsight selection, calendar offset, keying years on the decision month instead of the hold month, and a shrunken input table. None is arithmetic. A second engine on the same spec reproduces all four; the vectorbt "replication" already did ("the same arithmetic run twice", wave-2 §1). LEAN's coverage of delisted small caps vs our panel is **UNVERIFIED**. | Run the offset triplet on every hold-3 rule, and a clean-room `mom_12_1` from the written spec (both already owed). If the finalists survive those, a LEAN port is a portability exercise, not evidence. ~1 day. |
| **P4 freeze legacy accounts as "controls", launch seven clean accounts** | **No: seven more lottery tickets.** 62 parents and 245 twins are already entering. The best of seven zero-skill books beats SPY by 5 pp with 60% probability and looks like 2σ with 13% probability (§4). Relabelling accounts as controls **after** they lost does not make them controls; a control is chosen before the outcome. `AEGIS_MDC` would trade something that does not exist (MDC), and `AEGIS_BACKTEST_CHAMPION` would trade the JAJO offset. | Pre-register ONE primary forward comparison (e.g. the 18 lib bets vs their matched twins, pooled, z₆₃) with a kill rule. If it fails at 63 sessions, open no new account. $0. |
| **P5 "future intelligence" (CEO promises, patents, hiring, contracts)** | **Maybe, later.** It is the one source class not yet closed and the only one aligned with the Micron test, but it grades in quarters, not weeks. The promise grader (`source_reads.py --grade-promises`) exists, and so does a hiring trial (TRIAL-HIRING-PIVOT-1, 09-11 roadmap). The trial's status is **UNVERIFIED**: no file under `docs/TRIALS` matched. | Pick one: an 8-K promise-vs-delivery event study on the history already parsed. Pre-register it and run it once. ~2 days. |

**Is MDC estimable?** No (row P2). **Are seven new accounts a fix?** No. A fix would reduce the number of
comparisons, and this adds seven (row P4).

---

## 8. WHAT THE OWNER IS NOT BEING TOLD

The owner is a first-year student who wants three things: (a) money, (b) a contest placing, (c) maybe a paper.

**(a) Making money from this system is not realistic on the evidence, on any horizon inside his degree.**
- To *demonstrate* an alpha of 3%/yr at 10% tracking error (IR 0.3) at t = 2 takes (2 / 0.3)² ≈ **44 years** of monthly data. At 5%/yr and 8% TE it takes ≈ 10 years.
- Nothing on disk suggests even that much alpha.
- The best use of his own money is the core-satellite book *without* the fundamentals satellite: an index fund, with paper books for learning.

**(b) A contest placing is realistic, if he stops treating the contest like his own capital.**
- A deliberately concentrated variance book has roughly a 15–25% chance of top 3% (normal approximation, §6).
- The frozen rehearsal has roughly 0.5–3%.
- This is the one goal the system can materially move in five weeks, and the project's risk-discipline culture currently works *against* it.

**(c) A paper is realistic in 2–3 months, but not the paper he imagines.**
- What is publishable today: 26,631 pre-outcome LLM forecasts, graded out of sample. They show that persona prompting has negative skill, that a structured process has small positive skill on magnitude only, and that a trailing-volatility formula beats both. That is a clean, honest negative/methods result.
- Add the rebalance-timing-luck finding: +1,323% vs +424% vs +433% from calendar offset alone. Cite the existing "rebalance timing luck" literature (e.g. Hoffstein et al., Newfound Research).
- A supervisor at HKU can shape that into a paper. There is no "we beat the market" paper here.

**What he should STOP doing:**
1. Driving an AI agent through a paid news account in his main Chrome. By his own research note it violates the provider's terms (ToU §9.4.1). It has already acted inside his Google session, and it has produced zero gradeable evidence.
2. Minting books. 308 already exist, and each new one lowers the value of the best one.
3. Building a new module, guard or probe for every failure. 11,729 tests and 44 probes did not stop the fundamentals tilt coming back three days after it was closed.
4. Rewriting the plan every 48 hours. Seven TIER-1 roadmaps in three weeks is not velocity; it is the absence of a plan.
5. Quoting hindsight backtests to anyone, including the outside reviewer's "+1,323%", and above all to himself before the contest.
6. Running overnight "sims" whose units mostly skip, and counting the cycles as work. In `sim/session.json`, analyst was skipped, forecast hit REFUSED_CAP, review skipped for the weekend, and learn reported DEGRADED.

---

## SCORES: mine vs the outside reviewer's

| line | outside | mine | the one fact that justifies mine |
|---|---:|---:|---|
| overall | 72 | **30** | Six months in, no net-of-cost edge exists anywhere on disk, and the live book is 20% mega-cap beta picked by a closed signal (§1, §2). |
| vision | 93 | **55** | The vision is lost and re-written every week (CLAUDE.md: "said four times in a week and lost each time"). 791 docs and seven current plans in three weeks means it prioritises nothing. |
| forecast ledger | 95 | **62** | It is the best asset in the repo. But accrual was dead 08-27 → 09-24 behind a green scoreboard, today's forecast unit wrote 0 rows (`REFUSED_CAP`), and its one positive result loses to trailing σ63 (+5.7% vs +10.2%). |
| backtest engine | 84 | **66** | It prints LOO, best-5-months, DSR, hold-keyed years and matched twins, which is genuinely rare. But in the last 72 hours it keyed years on the wrong date (29 LOO verdicts flipped), overwrote its receipt of record, ran on a 25-name facts table, and it still aligns every quarterly rule to one calendar offset. |
| backtest evidence | 47 | **12** | Dev-selected top-10 vs matched twins in 2024-26: median −1.45 pp; −3.1 pp without the two JAJO rows. 9 cells at t ≥ 2 vs 8 at t ≤ −2. |
| paper performance | 27 | **8** | 6 of 33 priced accounts are ahead of SPY, pooled −0.27%; the fleet realised −9.8%; 0 of 57 frozen books are graded. |
| real-money readiness | 24 | **5** | 0 graded dates on every E[r] component. The mandate is REFUSED on paper and orders flow anyway. No stop is declared. |

**Where the outside reviewer flatters.**
- It scores what the documents *say* the system does (vision, ledger, engine) in the 80s–90s, and what the system *earned* in the 20s–40s, then averages them to 72. An investor weights the second set almost entirely.
- It misattributes +1,323% to 12-1 momentum and calls that "the backtest you wanted".
- It proposes TIER-0 status for a concept (MDC) that cannot be estimated at the sample sizes on disk.
- It had not run the code, and every one of its high scores dissolves at the first receipt.

## ROADMAP ITEMS, scored

Priority = P(changes a decision) × value if it does ÷ cost. Value is on a rough 1–10 scale of
weeks of owner attention saved or contest odds gained.

| item | P(changes a decision) | value if it does (1–10) | cost (days) | priority |
|---|---:|---:|---:|---|
| outside P0 OpenClaw always-on | 0.05 | 3 | 5–10, plus ToU risk | **drop** |
| outside P1 alerts on 12 components | 0.02 | 2 | 3–5 | **drop** |
| outside P2 MDC as TIER 0 | 0.10 | 3 | 2 (as a column) – 15 (as a tier) | low: a column once ≥ 60 graded dates exist |
| outside P3 LEAN replication of 5 finalists | 0.05 | 4 | 5–8 | low: only after the offset triplet |
| outside P4 seven clean accounts | 0.03 | 1 (negative: more comparisons) | 2–3 | **drop** |
| outside P5 future intelligence | 0.15 | 6 | 2 (one study) – 20 (a lane) | medium: one pre-registered study |
| mine: Bloomberg objective + WLS check + registration | 0.90 | 8 | 1 | **1st** |
| mine: offset triplet on every hold-3 rule | 0.60 | 5 | 0.5 | **2nd** |
| mine: correct the TIER-0 pitch, memory and book docs (§60, vol prior) | 0.80 | 4 | 0.2 | **3rd** |
| mine: make the mandate gate `u_plan` (or confirm one) | 0.70 | 4 | 0.5 | **4th** |
| mine: one pre-registered forward comparison with a kill rule | 0.50 | 6 | 0.5 | **5th** |
| mine: paper outline on the forecast ledger | 0.40 | 7 | 3 | **6th** |

---

## IF I HAD ONE WEEK (in order, each with its stop condition)

1. **Settle the contest.** Write down the contest utility, verify registration, export WLS membership, and build the
   entry: five WLS names × 20% with dated binary catalysts in one theme, no stops, and a written rotation rule.
   Freeze it by Oct 9.
   *Stop when:* the book is frozen with its WLS check and the owner has signed the one-line utility. If
   registration cannot be confirmed by Oct 4, stop everything else until it is.
2. **Run the quarterly offset triplet on `disp_short_avoid`, `qc470_mom252_quarterly_riskparity` and
   `mom_12_1_q_trend`.** The `QUARTER_OFFSETS` machinery already exists (`strategy_library.py:1323`).
   *Stop when:* each rule has all three offsets printed. Any lead whose FMAN/MJSD offsets do not beat their
   matched twins is relabelled a calendar artefact in `BRIDGE.md`, and nothing new is built.
3. **Correct the record.**
   - The TIER-0 pitch (§8 of the ONE_PIPELINE file) gets the vol prior beside +8.97%.
   - The rehearsal and core-satellite docs cite §60.
   - `MEMORY.md`'s "Fundamentals = GO" line is corrected.

   *Stop when:* a grep for "39 bps" and "8.97" finds no sentence without its contradicting receipt.
4. **Make the mandate bind, or retire it.** Either `u_plan` refuses to send orders while
   `account_mandate.status == "REFUSED"`, or the owner confirms one capital base and one cap set and the
   refusal clears. Also drop GOOG or GOOGL from the shortlist (they are one company).
   *Stop when:* the plan receipt and the contract print the same status, and the orders obey it.
5. **Shut the browser lane.** Delete `HANDOFF_PC`, confirm the consent watcher and gateway are down, and
   untick remote debugging in the main Chrome. If the Dow Jones scorecard is still wanted, paste 100
   archive articles by hand and run it once.
   *Stop when:* no agent process can attach to the owner's main browser, or the scorecard has run once
   on ≥ 100 publication dates.
6. **Pre-register the one forward comparison that matters:** the 18 lib bets vs their matched twins,
   pooled by cluster, z at 21 and 63 sessions, with the §4 luck table printed beside it and a written kill
   rule. Build no new book, account, module or probe for 21 sessions.
   *Stop when:* the registration is committed. Then do nothing more on this line until 2026-10-26.
7. **Outline the paper** with a supervisor: the forecast ledger (persona vs process vs trailing σ), the
   calendar-offset case study, and the closures table.
   *Stop when:* a two-page outline naming its receipts exists and one faculty member has read it. If the
   owner decides he does not want a negative-results paper, stop there instead.
