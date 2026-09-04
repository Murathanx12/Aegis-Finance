# HANDOFF — Fable 5.1 (brain) → Opus 5 (builder) — 2026-09-04

**Roles from here on.** Fable 5.1 reviews, adjudicates, plans, and attacks
what Opus builds. Opus 5 sessions build, one roadmap block (or part) per
session, with up to eight Opus subagents on non-overlapping surfaces and one
coordinator. Murat runs the sessions and pushes. Nothing in this file is
time-dependent; a session picks the first OPEN block in
`ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6 whose gate inputs exist.

---

## 1. READ FIRST, IN THIS ORDER (≈40 minutes, no skipping)

1. `session_briefing()` + `aegis_verified_state(section="summary")` (Optimus
   MCP; the summary parameter is new — `"warnings"`, `"fred"`,
   `"populations"`, `"all"` fetch the rest). Then `brain_query` +
   `aegis_postmortems` for the block you are about to touch.
2. `docs/AEGIS_STRATEGIC_INVARIANTS.md` (16 points) and
   `docs/AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`.
3. **`docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md`** — what is wrong and why.
   Do not rebuild on any receipt it marks void.
4. **`docs/ROADMAP_2026-09-04_PROFIT_ENGINE.md`** — your block, its tasks, its gate.
5. The receipt named beside any number you are about to act on.
6. Terminal repo: `aegis-alpha-terminal/docs/INDEX.md` then the top block of
   its `docs/HANDOFF.md` (diary, not authority).

---

## 2. THE SESSION CONTRACT (every Opus session, no exceptions)

**Start**
- Announce the block and the exact tasks from the roadmap you are taking.
- `git fetch` both repos; check `ListAgents` for a peer session on the same
  tree and coordinate via SendMessage before touching shared surfaces. Two
  sessions on one branch cost a night this week.
- Print the block's gate as a checklist before writing code.

**Build**
- A capability is not built until an entry point can reach it: name the
  consumer in the same commit or classify the module in
  `backend/services/signal_reachability.py`.
- Every headline number lands in a JSON receipt under
  `backend/data/optimus/<family>/` with `licence`, `question`, `scope`,
  `supersedes` (if any) and the code path that produced it. Prose quotes
  the receipt.
- Every receipt that claims an edge quotes the family size (cells looked
  at), the family-max p, and — once B4 exists — DSR and PBO. Before B4,
  quote the ≥64-draw model-null percentile *and* say the family correction
  is pending.
- New guards derive their inputs or REFUSE with the missing input named;
  a gate that cannot go green is a broken gate.
- Costs are never omitted; `Policy` refuses zero costs.
- Sealed receipts are immutable; corrections are new files with
  `SUPERSEDED_BY` sidecars.
- Tests: finance `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`;
  terminal `python run_tests.py`; Optimus `python -m pytest tests`. Never
  move `.env`.
- Nothing touches the venue in a test; nothing seals, orders, deploys or
  pushes without Murat.

**End (the handoff file `docs/BUILD_<block>_<YYYY-MM-DD>.md`, ≤ 2 pages)**
1. **RESULTS SCOREBOARD first**: best historical net strategy vs SPY TR ·
   best forward paper book · independent selectors · KPIs the block moved
   (§1 of the roadmap) · LLM spend · **RESULT IMPROVEMENT: <one line or
   NONE>**.
2. Gate checklist with evidence path per item; block status line for
   roadmap §6 (update the table in place).
3. What was refuted, what was confirmed, what is CANNOT DETERMINE and what
   would determine it.
4. **Claims for Fable to attack** — three to ten, each with its receipt and
   what would kill it. This is the review interface; a session that ships
   no attackable claim reports NONE.
5. Next session's first three tasks.
6. Update session memory (one file, one fact each) and `MEMORY.md`
   (one line, < 200 chars). Run `python tools/refresh_aegis.py` in the
   Optimus repo so the brain sees the session.

---

## 3. FIRST SESSION QUEUE — B1 (TRUTH) and B2 (HOLD) in parallel

Two coordinators are fine (one per repo) if two Murat sessions run; one
session may take B1 first and B2 second. Agents on non-overlapping files.

### B1 agents (finance repo)
| agent | surface | deliverable | acceptance |
|---|---|---|---|
| A1 benchmark | `learner/benchmark.py` (new), `backend/services/backtest.py`, `tools/readme_charts.py` | one module: `spy_total_return`, `qqq`, `ew_universe`, `cash`, `beta_matched`, `matched` with a pinned-history path (FF VW market) and a live path (yfinance adj SPY); tests; regenerate `backend/BACKTEST_RESULTS.md` with the non-overlapping code and replace the WITHDRAWN cells in README / NEGATIVE_RESULTS §1 / CANON with the new numbers + receipt path | a test fails if any `tracker_backtest/*.json` written after today carries a `market` not produced by the module; BACKTEST_RESULTS regenerated |
| A2 panel | `learner/dataset.py`, `scripts/tracker_ibes_backtest.py`, `learner/prior.py` | load `ibes__ptgsumu`; cross-check column `ratio_adj_check = meanptg_adj × cfacpr / prc` with disagreement rate printed; merge `crsp__dsedelist.dlret` + Shumway fill; verify/extend dsf coverage to all shrcd 10/11; `ratio ≥ 50` + split-year hygiene in the dataset; SIC 9999 → UNCLASSIFIED | `backend/tests/test_ibes_target_share_basis.py` passes with its xfail marker DELETED; a delisting-count receipt; schema hash bumped |
| A3 tape re-issue | `scripts/band_horizon_run.py`, `scripts/toxic_band_short_run.py`, `scripts/revision_6m_cohorts_run.py`, `scripts/holding_period_policy.py` | re-run on A2's panel with calendar-time overlapping cohorts + NW(h−1); revision over the FULL PIT hygiene universe with `target_rev_1m` and `net_rev_1m`; short reported as `−resid` with Reg-T capital | four receipts with `supersedes:`; sidecars on the old ones; a one-page `FINDING_<date>_THE_TAPE_REBUILT.md` with the before/after table (start from §2 of the verdicts doc) |
| A4 band prior | `learner/prior.py`, terminal `alpha/tracker.py` (read-only proposal) | re-derive BAND_PRIOR from A3; if nothing survives family-adjusted inference, hygiene-only; write the attended proposal for the live thresholds | proposal doc; nothing changes live |
| A5 manifest | `docs/DATA_MANIFEST.md` | a row per ignored WRDS family (OptionMetrics, TAQ, CRSP daily, Compustat, IBES, 13F annual, JKP, FF) with size, rows, pull date, script | manifest complete; a test that every `*.parquet` under `wrds/` matches a manifest row prefix |

### B2 agents (terminal repo)
| agent | surface | deliverable | acceptance |
|---|---|---|---|
| T1 contract | `alpha/brains/tracker_portfolio.py`, `scripts/prediction_book.py`, `state/contracts/` | hold fields on every sealed holding and contract; seal refuses without them | smoke test: a book without `min_normal_hold_sessions` cannot seal |
| T2 exits | `alpha/exits.py`, `alpha/engine/equity.py` | contract-aware exits; typed reasons enum; profile stop width (R3); PEAD target off tracker books; horizon from the book | test: a 21-session holding at −2% on day 0 is HELD; at −(profile width) it closes with HARD_RISK_LIMIT; `--expiry` no longer feeds `horizon_days` for tracker books |
| T3 re-entry | `alpha/runner.py:1134-1150`, `alpha/protect.py` | union of venue stops and today's ledger exits; refusal class `EXITED_TODAY` | test: closed-by-target name is refused re-entry the same session |
| T4 regret | `scripts/daily_learning_report.py`, `state/counterfactual.jsonl` marker | premature-exit / stop / re-entry / refusal regret with MAE/MFE; live-equity fallback; single SPY source; a receipt every night even when empty | ten sections, zero plumbing-caused CANNOT DETERMINE on a dry run |
| T5 drivers | `alpha/drivers.py`, `scripts/utilization.py`, seal | sector/SIC driver at seal time; UNCLASSIFIED for unknown; BINDING constraint printed per book | dry run of hack3's 10:01 pass on a recent seal admits ≥ 8 of 10 or names the binding guard |
| T6 fix train | `alpha/protect.py` (day salt), R8, R10, opg arms, mixed-currency cap, DEGRADED-book semantics | as listed in roadmap B2 §7-8 | each with a test; attended items listed, not done |

**Attended (Murat):** live band thresholds; enabling contract-aware exits on
the fleet; minting mirror/arena keys; the corpus-to-Railway decision.

---

## 4. BOUNDARIES THAT DO NOT MOVE

- No LLM authority over capital. LLMs propose, mutate, rewrite, rank; code
  prices, grades and orders.
- No search on the old panel. Any strategy result produced before B1's gate
  is a print.
- No claim without its family size. Generation is free; promotion is rationed.
- No reseal of a live day; the ledger tear stays; sealed receipts stay.
- Providers: DeepSeek is the finance backend's only chat provider; the
  terminal's gpt-5-nano bulk extraction, NVIDIA embeddings, council families
  and Featherless are licensed for research and the funnel; every paid call
  passes `alpha/spend.py`'s decision-justification gate.
- Nothing pushes, deploys, seals or orders without Murat. Murat pushes this
  commit after judging completes (11:00 ET 2026-09-04).

---

## 5. REVIEW-BACK PROTOCOL (how Fable reads a build session)

Fable receives `docs/BUILD_<block>_<date>.md` and re-derives at least one
receipt end to end, runs the block's gate checklist against the tree, and
attacks the listed claims. Verdicts land as
`docs/REVIEW_<date>_FABLE51_<block>.md` with CONFIRMED / REFUTED /
CANNOT_DETERMINE per claim and the roadmap's §6 table updated. A block whose
gate fails stays OPEN with the failing item named; nothing downstream opens.

---

## 6. STATE AT HANDOFF

- Finance repo: this commit on `main`, local, **not pushed**. Fast suite
  not re-run in full this session (documentation + one xfail test + one
  test file edited); run it at session start.
- Optimus repo: 4 fixes + 2 test files, `112 passed`, local, not pushed;
  the running MCP server picks up the changes on its next restart.
- Terminal repo: untouched this session (read-only audit).
- Fleet: six paper accounts liquidate 10:45 ET today (expiry guard); after
  judging, nothing re-enters until B2 §1-3 ship — an untyped same-day exit
  is the defect we are fixing, not a feature to keep running.
- Scratchpad receipts from the review (not committed; re-issue into
  `tracker_backtest/` from B1/B4): `persistent_null_result.json`,
  `ratio_fix_rederivation.txt`, `ptgsumu_rederivation.txt`,
  `hpp_rerun_fixed_admission.txt`, `hpp_rerun_ptgsumu_and_null.txt`,
  `toxic_short_rerun_fixed_band.txt`, `delisting_audit.txt`,
  `round_trips_hack_fleet.csv`, `ff_market_tr.py`.
