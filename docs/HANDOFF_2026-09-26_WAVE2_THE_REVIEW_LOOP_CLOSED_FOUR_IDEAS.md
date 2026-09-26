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
