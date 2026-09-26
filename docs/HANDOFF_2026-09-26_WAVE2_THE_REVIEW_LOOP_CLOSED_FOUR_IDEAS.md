# Handoff — 2026-09-26 (11:00 → 21:30 HKT) — wave 2: the review loop closed four ideas by measurement

Read `AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` (TIER 0) first, then
`reviews/ADJUDICATION_2026-09-26_WAVE1.md` and `reviews/ADJUDICATION_2026-09-26_WAVE2_D_E.md`.
Continues `HANDOFF_2026-09-26_THE_LIBRARY_THE_AUDIT_AND_THE_PITCH.md`. Murat's brief for the
day is verbatim in `research_notes/2026-09-26/external_session_brief_2026-09-26.md`.

## RESULTS SCOREBOARD

| line | state |
|---|---|
| best historical net strategy vs market | **none survives multiplicity** (277 rules, 834 cells, best DSR 0.21 vs 0.95). The honest out-of-sample number: **the top-10 chosen on pre-2024 results alone beat SPY in 2024-26 by +4.5 pp/yr mean, −1.6 pp median, 5 of 10** (`strategy_library/leaderboard_2026-09-26T093458Z.json`, `dev_selected_sealed_evaluated`). 62 rules beat SPY in both windows. |
| best forward paper strategy | 33 priced accounts: **6 ahead of SPY, 27 behind** (4/15 excluding twins); 241 books PENDING entry Mon 09-28 (`docs/PAPER_ACCOUNTS.md`). 1 book VOIDED before entry (`lib_mom_12_1_liqw_sealed_2026-09-26`: 97.5% in MU+SNDK). |
| independent selectors | unchanged in kind; +18 registered from the web discovery (4 in the 2024-26 top-10, none clearing multiplicity) |
| farm candidates tested / promoted | 3 $0 controls run tonight (see §2); promoted 0 |
| new actionable finding | **four ideas closed by measurement** (§2): broker identity (50.1% hit rate), first-mover raises (look-ahead), the analyst-skill filter (2025 only), `mom_12_1_q` (one calendar offset) |
| external execution drag | not measured today |
| LLM spend, the day | X timelines $0.53 · forensics adjudication ≤ $0.50 · G bake-off ≤ $0.15 · cards/forecasts on their daily caps · library/bridge/controls $0 |
| suite / CI | CI green at `e15b5456`; `d7f3aaf5` (wave-2 data) watched at hand-off; local full suite NOT run (memory ≤ 7 GB with three builders) — CI is the gate |

**RESULT IMPROVEMENT: NONE.** Terminal wealth did not move. What moved is what can be
claimed: the README's backtest section now says a true thing with its receipt beside it.

## 1. What the review loop did today (chunks A–I, two reviewers, three adjudications)
- **Reviewer H+I** (morning): a free 63-day-vol prior beats the LLM investigator on magnitude
  (+10.0% vs +5.5% at h=1). The learning report names the prior, not the LLM.
- **Reviewer A+B+F**: X handle timelines are readable logged out (search is not); the +10%
  books' names were selectable by rules we own; 36,720 Benzinga rows are a pre-2015 archive
  stamped 2026; the 456 brokerages were gradeable from the parquet.
- **Reviewer D+E**: the receipt the README cited had been overwritten in place by a second
  factory run; "sealed" was a selection window; the `liqw` book was a coin flip on MU's 09-30
  print; the vectorbt "replication" was the same arithmetic run twice; a 15-point freeze rule.
- All three adjudicated and built (`ADJUDICATION_2026-09-26_WAVE1.md` rows 1–15,
  `ADJUDICATION_2026-09-26_WAVE2_D_E.md` rows 1–11 + addendum A–H).

## 2. The four ideas closed by measurement (all $0 except X)
| idea | measurement | verdict |
|---|---|---|
| broker identity as a signal | 320,809 directional claims: 50.1% hit at 5d, 50.2% at 21d; firm skill first-half vs second-half ρ −0.11 | `DEPRIORITIZED`; registry weights printed as noise |
| first-mover raises | point-in-time first-minus-follower −0.06% at 21d (t −0.26); the +1.34% (t 8.7) version is look-ahead | closed; the cluster is known only when the followers arrive |
| analyst-skill filter (`skill_mom`) | `skill_mom − unskilled_mom` ex-2025 = −18.1 pp; the whole gap is 2025 (+32.7 pp) | ANALYST-SKILL-1 stays ADOPT_AT_TRIVIAL_EFFECT; branch unfunded; `mom_flow` is the honest parent |
| `mom_12_1_q` best-DSR row | offsets vs SPY 2024-26: Jan/Apr/Jul/Oct +37.9 pp, Feb/May/Aug/Nov −5.0 pp, Mar/Jun/Sep/Dec +8.4 pp | one calendar offset; not quotable without the other two |

## 3. What is built and where
- **Receipts carry a run id** (`leaderboard_<date>T<HHMMSS>Z.json`); the factory refuses to
  overwrite one; README/BRIDGE cite path + commit hash. Memory:
  `feedback_a_date_named_receipt_a_second_run_can_overwrite_is_not_a_receipt`.
- **`freeze_gate()`** (`scripts/night_backtest_factory.py`): selection (dev>SPY, 2024-26>SPY,
  top-5 share<0.6, DD>−40%, LOO-worst>0, ≤2/family), construction (max w ≤10%, effN ≥8, no
  ρ>0.8 cluster >40%, no >10% name with earnings in the first 5 sessions, largest-to-zero ≤
  $150k), timing (bars ≤1 session old). A failing row freezes as `__control`. **On today's 20
  library books: none pass** — every one used 09-21 bars for a 09-26 decision. They trade
  Monday as declared and are labelled CONTROL in `docs/BRIDGE.md` until re-frozen on fresh
  bars at each rule's own rebalance date (owed: chained re-freeze, item 14).
- **`llm_portfolio.void()`** appends a `llm_portfolio/void` row; grading, leaderboard,
  `paper_accounts_roi`, `bridge_report` skip voided books. Readers that do not yet know
  voids (tolerate the row, do not skip): `daily_review`, `thesis_cards`,
  `daily_learning_report`, `night_investigator_forecast`.
- **Corpus PIT grade** (`news_registry.grade_row`): `published_utc` > 30 days before
  `first_seen_utc` ⇒ `archive` (39,768 of 81,085 rows). Used by `book_signals.load_news_rows`
  and the forensics reader. **Owed**: `night_e1_news_return_panel`, `night_l2_typed_events`,
  `n5_event_compression`, `morning.py` still read archive rows.
- **Forensics** (`forensics/FAST_MOVERS.md`): class `SELECTABLE_BY_RULE` with rule ids
  (82 of 318; 20 on random-null twins = base rate); moves in book σ (+12.4% at h=6 = 0.85σ).
- **Source registry**: 456 brokers scored from the parquet (`sources/SOURCES.md`); 37 X
  handles, 24 verified, 21 forecast rows from timelines; promise grading by 8-K parser
  (`scripts/source_reads.py --grade-promises`; MU FQ4 targets declared).
- **Discovery rules**: 18 registered in `strategy_library_ext.py` with `claimed_number`
  and source; 29 `EXT_NOT_REACHABLE` name their missing column; 9 `EXT_COVERED_BY`.
- **Chunk G fix** (in flight at hand-off; see the addendum below when it lands): `/research`
  evidence reply, `/compare` as extraction bake-off E-G1, a standalone llama reaper, a
  non-reasoning NVIDIA adjudicator with 429 handling, Telegram redaction, the nightly
  `--grade-promises` caller.

## 4. Processes at hand-off
- `always_on_lab` relaunched 21:02 HKT (pid 100684) on `MODEL_ROUTING_START_AT_BOOT=False`;
  llama-server DOWN (VRAM free) and only started on demand.
- Sim session finished on request (86 cycles); the lab carries the night.
- Railway untouched (review only: `REVIEW_2026-09-26_RAILWAY_COST.md`).

## 5. Owed to Murat / by Murat
- **Murat**: log into X inside OpenClaw's `muratclaw` browser profile (search is walled;
  timelines work); Bloomberg registration by Oct 5 + WLS export (**signed up 09-26**); the
  terminal repo's Railway fixes (attended); overrules.
- **WSJ decision made 09-26 evening: Murat bought the Dow Jones bundle (WSJ + Barron's +
  MarketWatch), signed in inside `muratclaw`.** New chunk J: access test → PIT feeds in
  `news_registry` → dated archives → "what they said vs what happened" (Barron's picks,
  Heard on the Street, Big Money poll) graded on bars vs SPY and matched controls → the
  competition book's attention layer. Research note:
  `research_notes/2026-09-26/research_dowjones_bundle_wsj_barrons_marketwatch.md`.
  Licence: personal research reads at human pace, headlines/metadata/our claims stored,
  no full-text redistribution, no bulk crawl.
- **Next session, in order**: (1) chained re-freeze on fresh bars so the library books pass
  the timing gate; (2) the four corpus readers onto `grade_row`; (3) the clean-room
  `mom_12_1` re-selection with drifting weights (the independent replication); (4) SMH into
  the panel for the semis/UMD decomposition; (5) `k+1…2k` twins as the default control;
  (6) Monday 09-28: entry of 241 books, first grades 09-29; first 21-session reading of the
  bridge **2026-10-26**.

## 6. The three sentences (chunk I)
**WHAT WORKS**: the free 63-day-vol prior on magnitude (+10.0% held out at h=1; the LLM
+5.5%); rule ordering (`skill_mom` vs its own ranks 21-40, +63.6 pp ex-2025).
**WHAT DOES NOT**: LLM direction (−7.9%, n=780); broker identity (50.1%); first-mover
raises; the analyst-skill filter outside 2025; 27 of 33 priced accounts behind SPY.
**HIGHEST-EV EXPERIMENT**: the three PROBE-weighting twins already frozen (equal /
inverse-vol / big-move tilt, ~$17k EV at $1M), read against USMV on 2026-10-26.

## 7. 22:30 HKT — chunk J rules set by Murat after the first live read
- OpenClaw attaches to Murat's OWN Chrome via `--browser-profile user` (remote debugging
  enabled by him 22:05). It sees every profile's tabs. **Only the "MuratClaw (Work)" window's
  tabs may be touched** (t20 wsj / t32 marketwatch / t33 barrons); never `open` a new tab
  (it lands in his main profile — a SEC page did, once); never any other domain through the
  browser. `sec.gov` is HTTP-API only.
- **Paywalled reads only when he hands the PC over** (`backend/data/optimus/HANDOFF_PC` file
  gates `dowjones_pull.py --handoff`). His stated worry: the account gets flagged as a bot
  even for read-and-summarise. The ToU (research note §licence) agrees.
- **Primary path = the paste digest inbox**: he copies article text into
  `backend/data/optimus/digest_inbox/`; `scripts/digest_ingest.py` turns it into corpus rows
  (`first_seen_utc` = ingest time, `published` from the text, `origin: pasted_by_operator`)
  and claims → forecast rows. Free data (10 RSS feeds, every item) is fetched by HTTP now.

## 8. 22:40 → 23:50 HKT — wave 3, the hour Murat handed the PC over ("full freedom")
Commits: chunk J `3ae60413` · paper rules `d51d0050` · systems fixes `85d96044` · health probes
`cd21ac3f` · reviews/research `bc867065` `f20d4586` `16b8fb20` `c0a967ef` · `.env.bak*` ignored
`e7281aa5` · stale reachability lines `4f241d03`.

| track | measured | what changed |
|---|---|---|
| **Systems review** (`reviews/REVIEW_2026-09-26_SYSTEMS_ATTACK_AND_HEALTH_PROBES.md`) | 29 systems, 10 bad rules, 19 false-code findings. Worst three: bars stale since 09-21 with no refresher; the website backend sleeps when idle (lane NAVs stopped 09-18); Telegram agent dead since 09-23 while `stack_health` said ready. | bars refreshed to **09-25** (+12,216 rows), `scripts/pull_bars_refresh.py` first in `daily_pass`, `BARS_MAX_AGE_SESSIONS=2` gate in `u_plan`; Telegram agent under a Scheduled Task supervisor (restart proven by a PID kill); 130 unresolvable forecasts VOIDed (AVB 96, EA 27, 7 futures/index); the mandate's three disagreements (capital $40k vs $1M; caps 2/3/10/12%; gross 80%) now REFUSE on the receipt until Murat confirms one; `n_considered: 2` explained (25 funnel names → 16 HOLD-negative + 7 no-evidence → 2 after the committee gate; rule decision owed) |
| **Health probes** (`system_health.py`, `scripts/health_probe.py`, `/api/health/full.subsystems`, `docs/HEALTH_PROBES_2026-09-26.md`) | first live table: 0 DEAD / **13 STALE** / 6 UNKNOWN / 25 ALIVE. Ranking on 09-21 bars while the panel is on 09-25 (re-rank launched); `live_market_loop` never ran end to end; Optimus health page 13 d stale; `lab_loop:idle_gpu_queue` GPU_BUSY; Railway backend uptime 896 s = asleep. | 73 tests; every probe has a missing-evidence → not-ALIVE case; AST test that nothing reads mtime. **Owed**: a 30-min `health` tick in `always_on_lab`, a final step in `daily_pass`, `stack_health` as a wrapper. |
| **Paper rules** (`research_ssrn_arxiv_signals_and_oss_comparison.md`) | 6 registered with pre-declared controls; **all six had a falsifier fire**: Friday-drift lost to its Monday control both windows (top-5 share 4.54); `quality_momentum_gate` deepened the crash tail (−44.6% vs −35.9%); `cascade_entry_timing` beat first-mover in dev only; `disp_short_avoid` ≈ `mom_12_1_q`; `inst_breadth_up` (13F breadth, rdate+45d) beats its own ranks 21-40 but not random_1 in dev and 2025 is +58 pp of it. | XBRL re-extraction run: `rd` 1,991 rows, `sga` 1,295 → `rd_intensity` / `org_capital` become reachable on the next factory run (launched). 13F: `fdate == rdate` on every row, so the lag is `rdate + 45 d`. |
| **Chunk J** (`docs/OPENCLAW_2026-09-26_READING_MURATS_CHROME.md`) | 10 DJ feeds live (162 items); 13 other free surfaces probed, 10 → 401/403; HOTS ×5 at 91–203 s gaps (HUMAN_PACE_OK); 3 claims → 6 forecast rows (`wsj_heard_on_the_street`); Optimus (7 read-only tools) + `aegis_api` (GET only) registered as OpenClaw MCP tools, one `brain_query` call $0.012; `digest_inbox/WEEKEND_READING_LIST.md` 214 links / 56 names. | Two bugs fixed: cp1252 decode made every read empty; the first claims pass invented 24 rows from 8 claims. Barron's/MarketWatch reads re-launched after the attach dropped (gateway restart re-attached). |
| **OpenClaw best practice** (`research_openclaw_best_practice_and_human_pace.md`) | what flags a session; verb sequences per task shape; footprint plan (CV of gaps < 0.15 = ALARM). Evasion tooling declared out of scope. | jittered pacing, scroll-through and `footprint_receipt` in `web_reader`. |

**Attended items for Murat (none executable from here):** Railway website backend "sleep when idle" OFF; remove the start command pointing at `scripts/arena_paper_repair_once.py` (not in the image); relink this repo's Railway CLI (`railway unlink` / `link`); confirm ONE mandate (capital base, per-name cap, gross cap); decide whether committee-negative names count in `n_considered`; delete `HANDOFF_PC` when back; the weekend paste inbox.

## 9. 00:20 HKT 09-27 — signal structure (`03376f6a`, `docs/SIGNAL_STRUCTURE_2026-09-26.md`)
- **282 rules ≈ 180 distinct bets** at ρ 0.8 (dev 178 / 2024-26 181); the largest cluster is momentum
  (17 rules from 10 nominal families). Of 19 frozen forward books with a backtest row, 15 distinct
  bets: `lib_mom_12_1` / `lib_mom_12_1_q` / `lib_mom_no_downgrades` / `lib_mom_12_1_secrel_sealed`
  are ONE bet (ρ 0.83–0.97); `lib_mom_flow` / `lib_skill_mom_sealed` are one (ρ 0.92).
- **DSR at the honest denominator** (n = clusters, not cells): best cell 0.441 → 0.577; `mom_12_1_q`
  0.20 → 0.31. Nothing reaches 0.95 either way — the null is not over-counting.
- **Decomposition on SMH/IWM/MTUM/USMV/QUAL/VLUE spreads, 32 blocks:** of the 2024-26 top-30, 21 have
  alpha t < 1 after the ETFs and 17 are mostly SMH or MTUM beta; SMH − SPY averaged +2.47%/mo in
  2024-26; the unnamed loading is **IWM β ≈ 1.0** (a small-cap tilt that lost money). **Survivors with
  alpha t ≥ 2 in BOTH windows: none.** 15 rules clear it in dev only (momentum, t 2.0–3.4) and none
  of them carry it into 2024-26. The recent momentum win is ETF beta.
- Lead-lag: 1,496 tests, 2 hits at |ρ| ≥ 0.3 (`mom_12_1` → `gp_low_ag`, `mom_gp` at +2 months) — both
  die when 2020 is dropped (COVID). HYPOTHESIS closed.
- 61 rules `DEPRIORITIZED` as cluster duplicates. **Owed:** the bridge grades each cluster as one
  observation and compares momentum books against SMH/MTUM before SPY; a HAC t for quarterly books.

## 10. 01:02 HKT 09-27 — session cut by the usage limit; what runs on without me
- Sim `24b89eb2f80a` (pid 137904, planned end 08:18) in its first cycle's analyst pull; lab pid 100684;
  crash-model retrain pid 128152 (`train_crash_model_2026-09-27.log`); J3 builder fixing the
  queue's tab-id bug and relaunching `dowjones_pull --queue` (pid in `dowjones/queue_run.pid`);
  the SSRN abstract read on the managed OpenClaw profile (writes `research_ssrn_via_openclaw_browser_signal_candidates.md`).
- CI: green at `8f9ec417`; `b4b89c8a` + `164312c5` pushed, verdict unread. Later commits by J3
  are NOT pushed. Factory receipt of record: `leaderboard_2026-09-26T164302Z.json` (README/BRIDGE
  render from it; replication 10/10 AGREE). `T153843Z` is INVALID (25-name facts table).
- Next session: read `dowjones/queue_run_2026-09-27b.log`, the SSRN note (register its top-5 with
  controls), the retrain log, `health_probe`; delete `HANDOFF_PC` if Murat is back; push.

## 11. 02:10 HKT 09-27 — the night after the limit note
- Crash model retrained (`train_crash_model_2026-09-27.log.err`): LASSO kept 6/60, 20 features
  selected (`fred_lei_chg_3m`, `vol_x_mom_12m`, `fred_sloos_cc_chg_12m`, …); conformal 3m/6m/12m
  recalibrated on 1,852 samples; three CV folds had ONE class (no crash) so AUC is undefined
  there — the rare-event limitation, not a defect. Model + sidecar are local (`*.pkl` ignored).
- Queue relaunched on the J3 fix (`0ca3b7fa`, stable Chrome-MCP handles): parent tabs resolved
  by host, Barron's picks tab opened (`chrome-mcp:8ab5bfd86096:23`), reading at human pace.
- Round-2 paper rules (SSRN via OpenClaw's own browser) being registered: `news_tone_reversal_5d`,
  `filing_similarity_change`, `distance_to_default_rising`, `call_tone_drift`, `opex_week_large_hold`;
  enablers `news_tone_z` (FinBERT column) and the `VAL-01` market-value fix.
- Sim `24b89eb2f80a` cycle 11 at 02:03 (first cycle was the slow daily analyst pull).
