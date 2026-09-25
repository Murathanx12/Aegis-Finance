# Aegis-Finance Service Utilization Audit (read-only trace, 2026-09-25)

## Method

Traced actual call paths (imports + call sites), not file existence, using
Grep/Read/`python -c` only. No process started, nothing written to the repo.

The **live decision path** confirmed:

```
scripts/sim_run.py  Cycle:
  u_reconcile -> pc_broker.snapshot                (broker truth)
  u_funnel    -> opportunity_funnel.main()          (refreshes funnel_night10.json, gated on staleness)
  u_analyst   -> pull_analyst_targets.main()        (once/day, writes target_snapshots/target_revisions)
  u_rank      -> xs_ranker.build_panel/walk_forward/fit_production/rank_asof  -> ranking.json
  u_plan      -> pc_broker.plan_orders/submit, gated on live_market_loop._ranking_verdict
  u_grade     -> forecast_grader.grade_due, decision_ledger.score_due
  u_learn     -> rota ("survivorship_audit","breadth_check","idle") every 3rd cycle
```

**THE CENTRAL FINDING: there are (at least) three separate "decision" surfaces
in this repo, and only one of them ever reaches `pc_broker.submit()`:**

1. **`u_plan` (scripts/sim_run.py:444-533)** — the only path that places paper
   orders. It reads **only** `ranking.json`, which is `xs_ranker.rank_asof()`
   over the **whole survivorship-free panel** using the pure price/volume
   `FEATURES` tuple (xs_ranker.py:146-155). It does **not** call
   `investment_committee.committee()` / `compose_book()` at all — grep of
   `scripts/sim_run.py`, `scripts/live_market_loop.py`, `backend/services/pc_broker.py`
   for `committee|compose_book` returns nothing. `u_funnel`/`investment_committee`
   are touched only for `funnel_staleness()` / `_funnel_age_days()` (metadata),
   never for the actual candidate list or the composed weights.
2. **`investment_committee.committee()` / `compose_book()`** (backend/services/investment_committee.py:385,720)
   — reads `funnel_night10.json` (the 40-candidate, fundamentals+insider+PM-catalyst
   filtered set built by `opportunity_funnel.py`), applies `_kill_condition`,
   `_risk_factors`, `_tilt_size`. Exposed **only** via `backend/routers/investment_committee.py`
   (a FastAPI router) and `scripts/investment_committee.py` (an attended CLI that
   writes a `.txt`/`.json` report). **No caller in `sim_run.py`/`pc_broker.py`/
   `live_market_loop.py`.** This is a website/report surface, not the trading loop.
3. **`pm_engine.py`** ("Optimus Portfolio Manager" — its own docstring: *"a
   different product from the research lab, deliberately not subordinate to
   it... allowed to use information the lab has not validated"*) — a **third**
   allocator, reachable via `backend/routers/pm.py` (registered in `main.py`),
   consumed by `pm_actions.py`, `transaction_ensemble.py`, `why_moved.py`, and
   attended scripts (`always_on_lab.py`, `mirror_challenge.py`, `morning_brief.py`).
   Not called by `sim_run.py` either.

So: fundamentals, insider opportunistic-buy scores, analyst target levels,
PM-catalyst calendar entries all reach candidate **selection** for the funnel
(40 names) and the **`investment_committee`/`pm_engine` display/report
surfaces — but the actual **paper order sizing and submission** (`u_plan` ->
`pc_broker.submit`) uses **none of them**: it ranks the *entire* universe on
12 momentum/volume/technical feature families and buys the top `BOOK_SIZE`.
This is the same "one signal, several dressings" bottleneck CLAUDE.md already
names for the arena books, reproduced one layer up in the new PC/paper-profit
loop.

A **fourth, larger accrual layer** exists and doesn't reach any of the three
above: `backend/services/portfolio_intelligence/scheduler.py`'s `pi_daily_check`
job (lines ~902-1191) runs ~18 sequential "descriptive... never a signal...
never arms a lane" collectors every day (congress, ARK, 13F, insider ×2,
revisions, PEAD, quality, multifactor, fragility-candidates, smartgrowth,
forecast-ledger) that write PIT snapshots to SQLite (`pit_observations`,
`audit_log` in `backend/data/aegis_pi.db`) for a **forward-IC measurement
programme only**, explicitly walled off from every lane's live weights by
comment and by code.

---

## 1. `xs_ranker` FEATURES (backend/services/xs_ranker.py:146-155)

```python
FEATURES: tuple[str, ...] = (
    "mom_21", "mom_63", "mom_126", "mom_252_21",
    "rev_1", "rev_5",
    "vol_21", "vol_63", "vol_ratio",
    "dollar_vol_log", "turnover_surge", "trade_surge",
    "px_vs_52w_high", "px_vs_52w_low", "px_vs_ma50", "px_vs_ma200",
    "amihud", "gap_share", "vwap_pressure",
    "resid_mom_63", "beta_63",
    "up_days_21", "max_drawdown_63", "skew_63",
)
```

**All 23 features are derived purely from OHLCV bars** (`build_features`,
xs_ranker.py:261-400ish: momentum, reversal, realized vol, dollar-volume,
turnover/trade surge, distance-to-52w/MA, Amihud illiquidity, gap share, VWAP
pressure, residual momentum/beta vs SPY, up-day count, drawdown, skew).
**Zero** features are derived from analyst revisions/targets
(`target_revisions`, `analyst_*`), fundamentals, events, or text. Confirmed by
reading `build_features()` in full — no reference to `INF.`, `fund`,
`revisions`, `insider`, `event`, or any LLM output anywhere in the function.

## 2. `u_learn`'s rota (scripts/sim_run.py:570)

```python
rota = ("survivorship_audit", "breadth_check", "idle")
pick = rota[cycle_n % len(rota)]
```

Every 3rd cycle does nothing (`idle`, "the market loop owns the session").
The other two are QC / research checks on the pure price panel
(`_LEARN_SRC`, sim_run.py:596-618): `survivorship_audit` counts how many
symbols in the panel stopped trading (bias check); `breadth_check` re-runs
`walk_forward` + `top_k_backtest` at k=20/100/300. **Neither ingests
analyst/insider/fundamental/event/text data, and neither writes anything that
`u_plan` or `xs_ranker.fit_production` reads back** — they are diagnostics
written to `learn_<pick>.json`, read by nobody downstream.

## 3. `u_plan`'s inputs and `MEASURED_NEGATIVE` (scripts/sim_run.py:444-533)

Consumes: `ranking.json` (top `BOOK_SIZE` names + `top20_net_rel_21d`), the
broker's current holdings (`pc_broker.snapshot`), live prices
(`pc_broker.last_prices`). Produces an equal-weight target book via
`pc_broker.plan_orders` (mandate limits: no leverage, no shorts, 12%/name, 2%
of ADV, $250 min ticket). `MEASURED_NEGATIVE` / `acting=False` comes from:

```python
net = r.get("top20_net_rel_21d")
verdict = ("MEASURED_NEGATIVE" if (net is not None and net <= 0)
           else "MEASURED_POSITIVE" if net is not None
           else "UNMEASURED_TRADE_SMALL")
may_trade = verdict != "MEASURED_NEGATIVE"
acting = (mode == "paper_profit") and may_trade
```
i.e. it is a pure function of the top-20 backtest's own `mean_net_rel_21d`
number carried on `ranking.json` — same gate `live_market_loop._ranking_verdict`
applies (sim_run.py:470, imported directly from `live_market_loop`).

## 4. `llm_portfolio.build_briefing` (backend/services/llm_portfolio.py:120-210)

**Includes**: symbol, price, liquidity band, empirical cost bps, dollar-vol,
`mom_21/63/252_21`, `vol_63`, `beta_63`, `vs_52w_high`, `vs_ma200`,
`drawdown_63`, `skew_63`, `amihud` (all straight from `xs_ranker.build_panel`),
plus fundamentals joined PIT-safe by SEC filing date (`rev_qoq`, `rev_yoy`,
`gross_margin`, `gross_margin_chg`, `inflection_flag`) via `inflection.py`.

**Explicitly excludes** (its own `what_is_NOT_here` field, llm_portfolio.py:193-199):
> "analyst price targets and consensus estimates — the vendor endpoint is 403
> on this tier, verified again 2026-09-24. Do not infer them." / "fair-value /
> DCF estimates" / **"news, filings text, transcripts, insider transactions,
> options data."** / "sector and industry labels for the full universe."

So **`target_snapshots`/`target_revisions` are NOT wired into `llm_portfolio`**
despite the 393k-row revisions pull existing on disk — confirmed by both the
docstring and a repo-wide grep (`target_revisions`/`target_snapshots` consumers
are only `analyst_ledger.py`, `pm_engine.py`, `pm.py` router, and two attended
night scripts — never `llm_portfolio.py`). `scripts/llm_portfolio.py` itself is
an attended CLI (`brief`/`freeze`/`grade`), not scheduled anywhere (no hit in
`portfolio_intelligence/scheduler.py` or `sim_run.py`) — this is the "Fable
portfolio harness" from the 09-24 session, not a running loop.

## 5. Analyst revision pull on disk

`scripts/pull_analyst_targets.py` -> `backend/data/optimus/analyst/`:

- `target_revisions.parquet`: **393,369 rows** (memory said 392,201 on 09-24;
  it has grown), columns `ticker, pulled_at, event_date, firm, from_grade,
  to_grade, action, target_action, prior_target, current_target,
  target_change, pit_safe`. `event_date` spans **2011-12-08 → 2026-10-05**
  (note: the upper bound is *after* today, 2026-09-25 — worth a look, likely a
  vendor "forward" grade-date artifact, not verified further here).
  `pit_safe=True` (own event date per row).
- `target_snapshots.parquet`: **6,198 rows**, columns `ticker, observed_at,
  price, target_mean, target_median, target_high, target_low,
  implied_upside, pit_safe`. `observed_at` 2026-09-24 only (today's snapshot;
  `pit_safe=False` by design — it's a level, not a history).
- Consumers found repo-wide: `analyst_ledger.py`, `pm_engine.py`,
  `backend/routers/pm.py`, `scripts/night_investigator_forecast.py`,
  `scripts/night_missed_opportunity.py`. **Not** `xs_ranker.py`, **not**
  `llm_portfolio.py`, **not** `investment_committee.py`'s live path into
  `u_plan`.
- `signal_registry` already carries `analyst_target_upside_xs` as
  **CLOSED/PERVERSE** (t -3.6 large/mid, -7.2 small) — per
  `pull_analyst_targets.py`'s own docstring — which is *why* `opportunity_funnel`
  records the target level for sizing/display only and refuses to rank on it.

## 6. FDA / PDUFA / clinical-trial / catalyst-calendar code

Exists as **taxonomy and manual-entry plumbing, not an automated feed**:

- `event_vocabulary.py:400-415` — typed event ids `clinical_trial_result`,
  `regulatory_approval`, `regulatory_investigation_or_action` with FDA examples
  in the extraction schema (used for text-event classification, not calendar).
- `event_intel.py:173` — keyword classifier treats `"fda"/"regulator"/
  "antitrust"/"sec "/"doj"` as one bucket (`regulatory`).
- `pm_catalysts.py:14,44,184-185,286` — **explicitly documents the gap**:
  `"FDA / PDUFA action dates | no entitled source | ✗"`; *"The only route by
  which a PDUFA date reaches this engine today [is] a YAML entry a human
  writes by hand"* (`{date: 2026-11-14, kind: pdufa, what: "..."}`).
  `macro_calendar.py:10,26` names the same gap (`UNCOVERED` tuple: "PDUFA
  dates, secondaries, 13D/G ... human write catalysts: by hand for FDA
  dates").
- No collector, scheduler job, or script fetches an FDA/PDUFA calendar
  automatically. `test_pm_build11.py::test_18c_...` pins the manual-YAML-only
  contract.

## 7. Gambling / betting tickers already in the repo

`backend/services/agency.py:326-334` — an **ESG-exclusion** basket (not a
thematic buy list):
```python
"gambling": ("BYD", "CZR", "DKNG", "FLUT", "LVS", "MGM", "PENN", "RSI", "WYNN"),
```
with the comment *"`gambling` really does exclude DKNG, which is a live
holding in `book_lanes.yaml`"* — i.e. the exclusion vocabulary exists but is
not applied to the book that actually holds DKNG. `DKNG` itself is a real,
tracked holding: `backend/config.py:1162,2248,2584` (sector "Consumer
Discretionary", known position "DKNG 150" at a fixed date),
`ticker_resolver.py:108` ("DRAFTKINGS" -> DKNG), `transaction_ensemble.py`
(reconstructs DKNG/NTLA share history), and it appears fresh (2026-09-24) in
`pit_observations` under `multifactor_score:DKNG`, `revisions_score:DKNG`,
`pead_score:DKNG`, `quality_score:DKNG`, `insider_cmp:DKNG`,
`smartgrowth_pick:DKNG` — DKNG is one of the ~12-13 names in whatever book
those descriptive collectors are scoped to. No `FLUT`/other gambling names
appear as *live* holdings; the theme list otherwise only shows up in
`strategy_library.py` for the unrelated academic factor "BAB — betting
against beta" (a name collision, not a gambling signal).

---

## Scheduler jobs (backend/services/portfolio_intelligence/scheduler.py)

`EXPECTED_JOB_IDS` (line 67-80) registered via `add_job()`:

| job id | fires | calls | feeds the trading decision? |
|---|---|---|---|
| `pi_hourly_mtm` | close, mon-fri 16:30-19:30 ET | `reference_engine.mark_all_lanes` + book/ATR/SMQ/TSMOM lane marks | Yes — marks NAV of existing lanes (not a signal path) |
| `pi_daily_check` | 16:30 ET | `run_all_lanes` + book_management + exit_lane + tsmom_lane + fragility×2 + alert_engine + **insider_collector, cmp_insider_collector, revisions_collector, alpaca_mirror, forecast_ledger, pead_collector, quality_collector, multifactor, congress_collector, fragility_candidates, ark_collector, pit_collectors.collect_all_13f, smartgrowth** (~18 sub-calls) | Rebalances existing lanes on their own rules; **every one of the ~13 "descriptive" collectors is explicitly commented "never arms a lane"** and writes only to `pit_observations`/`audit_log` for a forward-IC measurement, never into lane weights or `xs_ranker` |
| `pi_options_pit` | 15:30 ET mon-fri | `options_pit_store.capture` | No — PIT storage for a separate event-response research trial |
| `pi_weekly_aggressive` | Mon 09:00 ET | `reference_engine.run_reference_check("aggressive")` | Yes, for that one lane |
| `pi_congress_collect` | 00:40 UTC tue-sat | `congress_collector.collect_congress_scores` (wraps `congress_trades.py`) | No — descriptive PIT only |
| `pi_ledger_resolve` | 16:30-19:30 ET | `ledger_resolver.resolve_due` | Grades forecasts, doesn't decide |
| `pi_ownership_collect` | 06:00 ET | `teacher_library.adapters_ownership.collect_and_append` (Forms 3/4/5) | No live consumer found beyond the teacher-library corpus itself |
| `pi_copy_lab_run` | 10:00 ET mon-fri | `copy_lab.runner.run_active_lanes` | Yes, for COPY-LAB's own seeded lanes (separate PRODUCT_EXPERIMENT track) |
| `pi_arena_daily` | 17:45-19:45 ET mon-fri | `arena.engine.run_daily` + `_submit_arena_broker_intent` | Yes, for the arena's own composite-momentum books (a third trading track, see CLAUDE.md "THE BOTTLENECK") |
| `pi_daily_digest` | 18:15 ET | `daily_digest.run_daily_digest` | No — documentation only |
| `pi_prediction_markets` | 17:55-19:55 ET | `prediction_markets.snapshot_daily` (Kalshi/Polymarket) | No — "NEVER a signal; nothing in a scoring path reads it" (comment, line 396) |
| `pi_book_cadence` (optional) | 16:45/17:45 ET | `book_cadence.run_all` | Yes, for holding-book lanes |

**Local SQLite evidence of actual output** (`backend/data/aegis_pi.db`, today's
live DB, checked directly):

- `pit_observations`: 1,709 rows. Fresh (2026-09-24) rows exist for
  `multifactor_score`, `revisions_score`, `pead_score`, `quality_score`,
  `insider_cmp`, `smartgrowth_pick`, `fragility_candidate` — but **only over
  ~12-13 tickers** (`AARD ABSI AMSC BHVN DKNG HUBS KYTX NTLA PRCH QUBT SLDP
  SOC`), i.e. one book's holdings, not a cross-sectional universe.
  `insider_opp` (the older insider collector) stopped at **2026-08-10** — 46
  days stale, superseded by `insider_cmp`.
  **`13f` has exactly ONE row, dated 2026-06-30** (`13f:1067983:filing`) — the
  13F collector has produced essentially nothing.
  **No `congress`/`ark` prefixed rows exist at all** in this local DB despite
  both being registered daily jobs — either they run only on the deployed
  Railway instance (separate DB, not in this checkout) or they are
  silently failing to write locally; not resolved further here.
- `audit_log`: 995 rows, mostly `alert_state` (977, fresh to 2026-09-24);
  `crash_overlay_eval`/`rebalance_executed`/`lane_initialized` are all
  **stale since 2026-09-07/09-11** — 2+ weeks without a fresh lane rebalance
  event locally.

---

## Module-by-module table

Freshness = newest file mtime under `backend/data/optimus/<x>` or the
relevant on-disk artifact found by direct search; "n/a" = no dedicated data
file found (writes to shared DB, or produces nothing durable found).

| module | what it does | data on disk & freshness | called by | reaches `xs_ranker` FEATURES? | reaches `u_plan`/live decision? | forward-graded? | verdict |
|---|---|---|---|---|---|---|---|
| `actor_intelligence` | scores "actors" (analysts, insiders, commentators) as forecasters, PIT `public_at`/`observed_at` split | no dedicated data dir; corpus built by `scripts/actor_corpus_ibes.py` (IBES 3.26M recs) | tests + `actor_corpus_ibes.py` only | No | No | Unclear — no wiring to `decision_ledger`/`forecast_grader` found | **DORMANT** (built, no live caller; research-corpus script only) |
| `analyst_intelligence` | analyst coverage/estimate summaries for a ticker | n/a (computed on demand) | `backend/routers/stock.py`, `pm_engine.py`, `scripts/analyst_cocoverage_graph.py` | No | No (feeds `pm_engine`/router display only) | No | **COLLECTED-NOT-USED** for trading; USED for website/`pm_engine` display |
| `analyst_ledger` | ledger of analyst-target forecasts/outcomes | reads `target_revisions.parquet` (393k rows, fresh 09-24) | `backend/routers/pm.py`, `pm_actions.py`, `pm_engine.py`, `shadow_portfolios.py`, `scripts/morning_brief.py`, `scripts/night_missed_opportunity.py` | No | No — feeds `pm_engine`, a separate allocator never called by `sim_run.py` | Partially — used in offline night scripts | **COLLECTED-NOT-USED** by the trading loop; used by the parallel `pm_engine` track |
| `ark_holdings` | parses ARK daily fund CSVs into flow scores | n/a locally; scheduler's `ark_collector.collect_ark_holdings` finds **zero rows in local `pit_observations`** despite a daily job | `ark_collector.py` (pi_daily_check), tests | No | No | No | **COLLECTED-NOT-USED** (and possibly broken — zero local output despite a scheduled daily job) |
| `congress_trades` | STOCK Act disclosure fetch+score (FMP) | n/a locally; **zero rows** in local `pit_observations` for `congress*` despite a dedicated daily job (`pi_congress_collect`) | `congress_collector.py` (2 scheduler jobs), tests, `scripts/research_congress_leadership_split.py` | No | No | No | **COLLECTED-NOT-USED** (possibly broken locally — see scheduler table note) |
| `holder_fingerprint` | no such live module; only WRDS-derived artifacts | `backend/data/optimus/wrds/holder_fingerprints.parquet`, `tracker_backtest/holder_fingerprint_summary.json` | none in current backend/scripts import graph | No | No | No | **DORMANT** (offline WRDS research artifact only, no owning module found) |
| `short_interest` | short-interest level/pressure per ticker | `backend/data/optimus/short_interest/` — 36 files, newest **2026-09-12** | `backend/routers/stock.py`, `book_signals.py`, `copilot.py`, `recommendation.py`, `scripts/short_interest_panel.py` | No | No (router/recommendation display, not `xs_ranker`/`u_plan`) | No | **COLLECTED-NOT-USED** for the paper-trading decision; used for website display/`recommendation.py` |
| `prediction_markets` (svc) | Kalshi/Polymarket PIT snapshot | `backend/data/optimus/prediction_markets/` — 5 files, newest **2026-08-21 (35 days stale)** | `backend/routers/prediction_markets.py`, scheduler `pi_prediction_markets` (daily) | No | No — comment: "NEVER a signal; nothing in a scoring path reads it" | No | **COLLECTED-NOT-USED** by design, and the local snapshot is itself 35 days stale |
| `prediction_market_matching` | matches PM contracts to internal event taxonomy | n/a dedicated | `routers/prediction_markets.py`, `daily_digest.py` (scheduled `pi_daily_digest`), `event_probability_surface.py` | No | No | No (feeds a digest, not a ledger) | **COLLECTED-NOT-USED** (feeds documentation only) |
| `event_extraction` | typed-event extraction from text (39-id vocabulary) | n/a dedicated (output goes wherever the caller writes) | `event_vocabulary.py`, night scripts `night_l2_retype_v3.py`/`night_l2_typed_events.py`/`night_social_features.py`, many tests | No | No — not called from `sim_run.py`/`investment_committee.py` | Partially — `scenario_forecasts.py` (per `signal_reachability.CLASSIFIED`) is AWAITS this + a base-rate table, not yet consumed | **COLLECTED FOR A FUTURE CONSUMER** (AWAITS, per `signal_reachability.py:145-152`) |
| `event_intel` | keyword+typed event classification for a ticker/day | n/a dedicated | `backend/routers/event_intel.py`, `main.py`, `earnings_intelligence.py`, `explain_move.py`, `investigator_tools.py`, `news_intelligence.py` | No | No | No | **COLLECTED-NOT-USED** for trading; used for website/why-moved narrative |
| `event_store` | typed-event persistence | n/a dedicated | `main.py`, `arena/events.py`, tests | No | Indirectly via `arena/events.py` (the arena's own composite track, not `u_plan`) | Unclear | **COLLECTED-NOT-USED** by the paper-trading loop; used inside the arena track |
| `earnings_intelligence` | earnings-related event/estimate summaries | n/a dedicated | `routers/options.py`, `routers/stock.py`, `event_intel.py`, `explain_move.py`, `factor_grades.py`, `iif1_features.py`, `investigator_tools.py` | No | No | Via `iif1_features.py` -> IIF1 investigator forecasts (forward-graded, see below), not `xs_ranker` | **COLLECTED-NOT-USED** by `u_plan`; feeds website + the IIF1 research track |
| `edgar_events` | EDGAR filing-derived events (8-K etc.) | `backend/data/optimus/web_events/` overlaps (see `web_events`) | `routers/events.py`, `event_intel.py`, `explain_move.py`, `insider_form4.py`, `iif1_features.py`, `pit_collectors.py`, `teacher_library/adapters_13dg.py` | No | No | Via IIF1 (same as above) | **COLLECTED-NOT-USED** by `u_plan`; feeds website + IIF1 |
| `graph_propagation` | shared-broker/analyst co-coverage graph propagation | `backend/data/optimus/graph_propagation/` — 6 files, newest **2026-09-12** | `scripts/graph_backbone_measure.py`, `scripts/graph_midcap_screen.py`, tests | No | No | No | **DORMANT/AWAITS** — `signal_reachability.CLASSIFIED` (line 210-218) marks this explicitly AWAITS its consumer `GRAPH_PROPAGATION_v1`/`ANALYST-COCOVERAGE-GRAPH-1`, blocked on a book-identity migration. Per CLAUDE.md, GRAPH-MIDCAP itself is also `MECHANISM_REJECTED` (closed shared-broker co-coverage) |
| `world_model` | fitted latent "world state" for many research sweeps | n/a dedicated (each sweep script owns its own output) | ~20 offline `scripts/*` research sweeps (convexity, denoised_representation, mega_sweep, net_ladder_rungs, risk_price_*, wm0_train/inference, etc.), tests | No | No | Research-only, per-script | **RESEARCH TOOL** — reachable only from attended one-off sweep scripts, never from `sim_run.py`/`xs_ranker.py`. Correctly self-describes as offline. |
| `investigator_agent` | IIF1 microtask investigator: gather/event/expectations/forecast/counter | `backend/data/optimus/investigator/` — 3 files, newest **2026-09-24** (`run40.log`) | `iif1_prereg.py`, `iif1_run.py`, `investigator_night.py`, `night_launcher.py` (-> `always_on_lab.py`/`daily_pass.py`) | No | No — separate from `sim_run.py`'s `u_learn` rota entirely | **Yes** — IIF1 forecasts are the ones memory (§64, S55) reports as **+8.97% OOS** for the `investigator` *process*, graded via `forecast_grader`/`decision_ledger` | **USED — but for a parallel research/forecast loop (`always_on_lab`), not for `u_plan`'s order construction** |
| `investigator_night` | nightly orchestration of the IIF1 arms | as above | `night_launcher.py`, `iif1_grader.py`, `iif1_prereg.py`, `iif1_run.py`, `deepseek_balance.py`, extensive tests | No | No | Yes (same as above) | same as `investigator_agent` |
| `investigator_triggers` | decides which observables the investigator should chase | as above | `iif1_features.py`, `iif1_prereg.py`, `iif1_run.py`, `investigator_night.py`, `night_launcher.py` | No | No | Yes (same loop) | same as `investigator_agent` |
| `openclaw_client` | browser-automation client (OpenClaw) for IR pages/transcripts | `backend/data/optimus/openclaw/` — 9 files, newest **2026-09-24** (`q2_run.err`) | `scripts/openclaw_collector.py`, `scripts/openclaw_login.py`, `scripts/stack_health.py`, tests | No | No | Feeds `investigator`/night research reads | **Per memory (S55 09-24): `openclaw.health()` had ALWAYS been red on an ANSI-parsing bug — "the night runner was never once allowed to browse" until fixed 09-24.** So for most of its life: **DORMANT (silently broken)**; now freshly fixed and exercised |
| `web_events` | generic web/filing event collector (feeds `fundamental_features.py`) | `backend/data/optimus/web_events/` — 2 files, newest **2026-09-22** | `fundamental_features.py`, `gap_audit.py`, `openclaw_collector.py`, `pull_sec_fundamentals.py` | No (fundamentals aren't in `FEATURES`) | No | No | **COLLECTED-NOT-USED** by `xs_ranker`/`u_plan` |
| `news_intelligence` | news classification/sector tagging | n/a dedicated | `routers/news.py`, `daily_brief.py`, `event_intel.py`, `investigator_tools.py`, `morning.py`, `fragility_candidates.py` (scheduled), `sentiment_analyzer.py` | No | No | Partial via `fragility_candidates` (descriptive-only, see scheduler table) | **COLLECTED-NOT-USED** by trading decision; used for website news + descriptive fragility |
| `trends_sentiment` | Google-Trends-style sentiment signal | n/a dedicated | `routers/analytics.py`, `routers/market.py`, `routers/stock.py`, `market_dashboard.py`, `signal_engine.py`, `scripts/night_missed_opportunity.py` | No | No | No | **COLLECTED-NOT-USED** by `u_plan`; router/dashboard display only |
| `llm_portfolio` | LLM-proposed book, briefed/frozen/graded, vs SPY | `backend/data/optimus/llm_portfolio/` — briefing files, newest **2026-09-24** listing, latest briefing content dated 2026-09-21 | `scripts/llm_portfolio.py` CLI only (`brief`/`freeze`/`grade`/`template`) | Reads `xs_ranker.build_panel` fields directly (not the trained model) | No — attended CLI, never scheduled, never called by `sim_run.py` | Yes — `grade()` NAVs frozen books vs SPY | **TEST/ATTENDED-ONLY** — real forward-graded experiment, but manual and not in any loop |
| `pm_catalysts` | prediction-market catalyst calendar (macro + manual FDA/PDUFA entries) | n/a dedicated (YAML-driven) | `routers/pm.py`, `macro_calendar.py`, `pm_actions.py`; `opportunity_funnel.py` imports only its `_finnhub`/`FETCH_FAILURES` helper (utility reuse, not the catalyst logic) | No | No — feeds `pm_engine`/router, not `u_plan` | No | **COLLECTED-NOT-USED** by trading decision; feeds the separate `pm` product |
| `winner_loser_factory` | matched-control winner/loser construction (CANON rule 4) | n/a dedicated | tests only, `convexity_episodes.py` | No | No | No | **GAP**, per `signal_reachability.CLASSIFIED` (line 198-200) verbatim: *"matched controls are CANON rule 4 ('study losers as hard as winners'). The factory exists; no analysis path calls it."* |
| `market_sensor` | SPY 21d trend + VIX regime sensor (frozen thresholds) | n/a dedicated | `macro_calendar.py`, `scripts/night_x4_regime_route.py`, tests | No | No — not imported by `sim_run.py`/`xs_ranker.py`/`investment_committee.py` | No | **COLLECTED-NOT-USED** by the live decision path; used by an offline regime-routing research script |
| `signal_reachability` | meta-audit: which modules are reachable from real entry points | itself | tests (`test_signal_reachability.py`), self | n/a | n/a | n/a | **OK** (by its own classification) — but its `CLASSIFIED` dict does **not** cover most of the modules above, meaning they ARE technically reachable (via routers/tests it doesn't flag) — reachable-but-idle-for-trading is exactly the gap this audit measured that `signal_reachability` itself says it cannot: *"Reachable does NOT mean used"* (its own docstring) |

---

## Top 15 COLLECTED-NOT-USED modules, ranked by plausible information content

1. **`analyst_ledger` / the 393,369-row `target_revisions.parquet`** — dated,
   PIT-safe, per-analyst grade/target changes back to 2011; explicitly
   excluded from `llm_portfolio` and never reaches `xs_ranker`/`u_plan`.
2. **`investment_committee.compose_book()` / the whole `opportunity_funnel`
   pipeline** (fundamentals + insider + PM-catalyst filtered 40-name shortlist)
   — richer than the plain momentum ranker, feeds only a website page/CLI
   report, never `u_plan`.
3. **`pm_engine.py`** ("what should I do today", allowed to use unvalidated
   info) — a whole second allocator, reachable only via `pm.router`, never
   wired to `pc_broker.submit`.
4. **IIF1 investigator forecasts** (`investigator_agent/night/triggers`) —
   memory's own **+8.97% OOS** positive process-level result, forward-graded,
   running nightly via `always_on_lab`, but structurally outside `sim_run.py`'s
   `u_learn` rota and `xs_ranker.FEATURES` — a measured edge sitting one
   integration step away from the trading loop.
5. **`edgar_events` / `earnings_intelligence` / `event_intel` / `event_extraction`
   / `event_store`** (the 39-id typed-event vocabulary + extraction stack) —
   built for `scenario_forecasts.py`'s pricing model, explicitly AWAITS wiring
   (`signal_reachability.CLASSIFIED`), currently only narrates "why it moved"
   for the website.
6. **`short_interest`** — 36 files of level/pressure data (through 2026-09-12),
   feeds `recommendation.py`/website only.
7. **`graph_propagation`** (analyst/broker co-coverage) — AWAITS a book-identity
   migration; its sibling mechanism GRAPH-MIDCAP is already `MECHANISM_REJECTED`,
   so this is a genuinely tested-and-shelved information source, not neglected.
8. **`ark_holdings`** — fund-flow signal via ARK's daily CSVs; scheduled daily
   but **zero rows found in the local live DB**, so possibly broken as well
   as unused.
9. **`congress_trades`** — STOCK Act disclosures; scheduled twice daily
   (morning + catch-up), **zero rows found locally** — same "possibly broken"
   flag as ARK.
10. **`pit_collectors.collect_all_13f`** — one row total in local
    `pit_observations`, dated 2026-06-30; effectively producing nothing.
11. **`web_events` / `fundamental_features`** — SEC filing/fundamental features
    computed and PIT-joined for `llm_portfolio`'s briefing display, but never
    among `xs_ranker.FEATURES`, so never reach the actual ranking model.
12. **`news_intelligence` / `trends_sentiment`** — website display/sentiment
    signals with no path into `xs_ranker` or `u_plan`.
13. **`prediction_markets` (Kalshi/Polymarket)** — daily snapshot, explicitly
    "NEVER a signal" by design, and the local copy is 35 days stale regardless.
14. **`winner_loser_factory`** — CANON rule 4's matched-control machinery,
    built and never called from any analysis path (per `signal_reachability`).
15. **`market_sensor`** — the one SPY/VIX regime module CLAUDE.md's strategic
    invariants explicitly call for ("the mega-cap is a SENSOR"), sitting
    unused outside a single offline regime-routing script.

## Two "possibly broken, not just unused" flags worth a follow-up session

- `congress_collector`/`ark_collector`/`pit_collectors.collect_all_13f` show
  **zero-to-one rows** in the local live `aegis_pi.db` despite being registered
  daily scheduler jobs — this could mean (a) they only ever run on the
  deployed Railway instance and this checkout's DB is simply not that one, or
  (b) they are failing silently the way the insider collector and the
  ANSI-broken OpenClaw health check did before. Not resolved here — would need
  a receipt read on the live deployment (`railway logs`), not this checkout.
- `openclaw_client`'s health check was **red on an ANSI-parsing bug for its
  entire life** until fixed 2026-09-24 (per session memory) — a direct
  instance of the "collector that runs green and does nothing" failure mode
  CLAUDE.md names repeatedly.
