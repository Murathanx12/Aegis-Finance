# Decision Story + regret ledger (C11, 2026-10-06, rebuilt after review)

**RESULT IMPROVEMENT: NONE.** This is measurement plumbing. No grade exists yet, and no order changes because of it.
The question it answers once horizons mature: *what did not deciding cost, measured honestly?*
The design was rebuilt the same night after the adversarial review (`docs/reviews/REVIEW_2026-10-06_C11_DECISION_STORY_REGRET.md`, 56/100). The review findings F1-F8 are addressed below.

## What runs where

| piece | file | caller |
|---|---|---|
| stories + frozen alternatives | `backend/services/decision_story.py` (`freeze_plan`) | `scripts/sim_run.py` `u_plan`, every cycle (`_freeze_decision_story`) |
| grading | `backend/services/regret_ledger.py` (`grade_due`, CLI `--json`) | **`scripts/daily_pass.py` step `regret`**, after `grade_forecasts`, out of process, box 600 s; also `task_keeper regret` |
| preference read | `policy_state.regret_view()` | `night_morning_report.block_regret` (§6); read only, never a risk limit |
| bars | `xs_ranker.load_bars(..., symbols=...)` plus a date-window universe | about 1.4 s measured |

Files (monthly, keyed on the session's month):
`backend/data/optimus/decision_story/stories_<YYYY-MM>.jsonl`, `alternatives_<YYYY-MM>.jsonl`, `regret/regret_<run_id>.json`.
A sandbox `u_plan` writes under `<out>/decision_story` and does not read this machine's shadow-news ledger.

**No live story exists yet.** Session b7b5981048e5 loaded the old `u_plan` and must be restarted, or the next session must start, before anything is written (review F4).
Every receipt line now prints `live stories on disk: N, oldest session D` beside the first-grade date.

## Keys and timing (review F3)

A decision is keyed on the **XNYS session whose price it can first trade at**, never on the ET calendar date:

- before 09:30 ET on a session day: that session's **open**;
- 09:30-16:00 ET: that session's **close** (market-on-close is feasible);
- after 16:00 ET, or on a weekend or holiday: the **next session's open**.

So Friday evening, Saturday and Sunday are one decision about Monday's open. The id is `dec_` + sha(session, ticker, policy, action, weight, acting), so a repeat is not written. The grader keeps one observation per (session, ticker), and n counts sessions (date blocks).

## Schema

**Story** (`kind: "decision"`):

- Timing: `asof`, `session`, `entry_basis`, `entry_rule`.
- Decision: `state`, `action` (BUY / SELL / EXIT / HOLD / REFUSE), and **`cohort`** (`acted` / `picked_blocked` / `shortlist_not_taken` / `ranker_pool` / `held_resize`).
- Weights: `target_weight` (after the order gate), `plan_full_weight` (before both gates), `held_weight`, `effective_weight`.
- Prices and cost: `reference_price` (the quote at decision), `median_dollar_vol`, `cost_round_trip_bps`, `order_gate_scale_exploit`.
- `chain`: event_ids, evidence_ids (now including the shadow-news row), forecast_ids, decision_id, order_or_abstention_id, outcome_ids, attribution_ids.
- `latency`: the six stamps, with prices where they exist.
- Seals: `sha256`. An order sent in a later cycle is an appended `order_link` row; no row is ever rewritten.

**Alternatives** (`places_orders: false`; the PIT test mutates post-asof bars and gets byte-identical rows):

- `actual`
- `plan_full`
- `no_trade`
- `buy_default` (2%)
- `buy_half`, `buy_double_capped` (12% cap)
- `enter_next_open`. **There is no earlier-entry alternative: the plan could not have taken one.**
- `exit_now` and `hold` (held names only)
- `selection_next_ranked` (carries its own `median_dollar_vol`)
- `plan_plus_shadow_news` (SHADOW_NEWS_v0's tilt over `plan_full` at the contract's earned trust, PIT row) and `plan_plus_shadow_news_full` (trust 1/1, diagnostic)
- `loo_news`, `loo_analyst`, `loo_price_momentum`, `loo_regime`, `loo_llm`

**Replay (review F5).** The replay reproduces the **pre-order-gate** book (u_plan captures `pre_gate_w` just before `_order_path_gate`). When the gate scaled EXPLOIT (`scale_exploit` < 1), leave-one-out rows for every name that is EXPLOIT in either book read `NOT_SEPARABLE because the order gate bound`. A drifted replay prints `replay MISMATCH` on the line, and every leave-one-out becomes NOT_SEPARABLE (tested by monkeypatching `replan`).

## Grading (review F1, F2, F6, F8)

**Entry and P&L.** Entry is at the reference session's open or close, and exit is at the close after h sessions of exposure, from ONE series. P&L = `w*r - (|w - w0| + |w|) * rt/2`, and a zero cost is refused. Cost uses the frozen volume; when none was frozen, the panel's 60-bar median before the session is used, so a held mega-cap pays 6 bps, not 35.

**Per-name signed diagnostics.** Each is outcome(alternative) − outcome(actual); there is no `max`:

- `direction` (BUY/SELL): no_trade − actual
- `sizing` (BUY/SELL): **buy_default − actual**. This is the review's "actual − default" with the house sign (positive means the alternative was better).
- `timing` (BUY/SELL): the traded delta entered at the next open − entered at the reference, same exit
- `exit` (held names): hold − exit, or exit_now − hold
- `abstention`: `plan_full` − actual for picked_blocked; `buy_default` − actual for shortlist_not_taken and ranker_pool. held_resize is **not** an abstention.

Each comes as `_bps` (net), `_gross_bps` and `_excess_bps` (over SPY). Summaries take one number per session, then t and MDE across sessions.

**Null test, 1,000 martingale draws at σ = 2.16%/day, h = 5, one draw set per case.** Every type is mean zero:

| regret (case) | mean, bps | t |
|---|---|---|
| direction | −0.12 | −0.27 |
| sizing | −0.04 | −0.27 |
| timing | +0.05 | +0.47 |
| abstention ×2 | +0.08 | +0.27 |
| exit (EXIT) | +0.08 | +0.27 |
| exit (HOLD) | −0.08 | −0.27 |
| selection | +0.15 | +0.35 |

The old best-of-two read +5.6 bps for sizing on 100% of draws.

**Selection** is one row per (session, selector): the taken book's mean P&L vs the next-ranked name at the mean taken weight, each at its own cost band.

**Cohort books (the abstention answer).** Per (session, cohort, h):

- Counterfactual weights: picked_blocked and held_resize use `plan_full`; shortlist_not_taken and ranker_pool use `buy_default`; acted uses its effective weight.
- Each book is **scaled to `PROBE_GROSS_CAP` (20%)**.
- Each is reported as **net excess over SPY** (costs charged) and **excess over a same-liquidity-band control**. The control is the equal-weight panel mean of every name in the same band over the same window, i.e. the expectation of a random same-band portfolio.

The headline line reads only the picked_blocked book. A raw dollar sum is never printed.

**Basis breaks.**

- A step inside the window larger than max(0.25 log, 8σ) is **REFUSED**, never graded OK. This catches raw splits and two-basis splices (tested).
- A later back-adjustment that rewrites past bars grades unchanged, because the window is on one basis. The gap to the frozen quote is printed as `basis_factor` / `basis_note` (tested).
- Remaining gap: raw dividends (a few percent) are not detectable without a raw daily panel. Only `bars_raw_monthly.parquet` exists today.

**MDC.**

- `mdc_<source>` = utility(plan_full) − utility(without source), per session.
- `mdc_news_tilt` = utility(plan + news tilt) − utility(plan). This makes news a real number from the first graded day, with no order.
- Each carries `n_sessions` and `TRUST_AT_63 (n/63)`.
- `mdc_news` (leave-one-out) stays zero by construction and says so.

## The h5 table the grader will emit (`regret_ledger.h_table(receipt, 5)`, also printed by `format_summary`)

One row per cohort present at h = 5:

| field | meaning |
|---|---|
| `cohort` | picked_blocked · shortlist_not_taken · ranker_pool · held_resize · acted |
| `mean_names` | names per session in the cohort |
| `book_scaled_gross` | the cohort book's gross after scaling to the 20% cap |
| `mean_net_excess_vs_spy_bps` | mean over sessions of Σ s·w·(r − r_SPY) − costs, in bps of equity |
| `vs_band_control_bps` | mean over sessions of Σ s·w·(r − r_same-band panel mean) |
| `t_vs_spy` | t over date blocks (None until 2 sessions) |
| `n_date_blocks` | sessions graded |
| `mde_bps` | 2.8 · sd / √n (80% power, 5% two-sided; None below 2 sessions) |

Beside it the receipt carries:

- `summary.by_horizon.h5.regret.<type>` (signed diagnostics: n_sessions, mean, sd, t, MDE);
- `selection_rows`, `cohort_rows`, `refused_rows` (with the reason);
- `summary.mdc.*.h5` (MDC with labels);
- `by_week`.

## One real dry example (asof 2026-10-06, observe mode, scratch folder, order submission disabled)

The run read the live shadow-news ledger read-only and the PC-PAPER broker snapshot through a read-only GET.

- Decision timing: session 2026-10-06, entry at the **close** (decided during the session).
- Volume: 51 candidates, 51 stories and 746 frozen alternatives (14.6 per decision). Replay MATCHES; order-gate scale 1.0.
- Cohorts: ranker_pool 22, shortlist_not_taken 13, held_resize 10, picked_blocked 6.
- Shadow news: row 2026-10-06T16:32Z, contract f3b149ea42311760, trust_dir 0.0069, trust_size 0.

**NVDA** (PROBE, HOLD, held_resize, 6 bps):

- actual / no_trade / hold: 2.108%
- plan_full / buy_default: 2.00%
- half / double: 1.05% / 4.22%
- enter_next_open: 2.108%
- exit_now: 0
- selection: HNI at 2.108%
- plan_plus_shadow_news: 2.0026%; at full trust: 2.362%
- loo_news: IDENTICAL_NOT_READ
- loo_analyst / loo_regime / loo_llm: 2.00%
- loo_price_momentum: NOT_SEPARABLE

## When the first grades land

For a live story on session 2026-10-06, the horizons mature as follows. Each grade arrives on the first daily pass after the bars cover that date.

| horizon | matures |
|---|---|
| h5 | 2026-10-13 |
| h21 | 2026-11-04 |
| h63 | 2027-01-06 |

**Today there is no live story** (see above). The real first grade is five sessions after the first session the restarted `u_plan` runs. MDC is labelled TRUST_AT_63 until 63 graded sessions exist.

## What is NOT_SEPARABLE today, and why

- **price_momentum, for every shortlist name (23 of 51).** The funnel filters on `low_volatility` and liquidity, and it is not re-run here. EXPLOIT-only names have weight 0 without the ranker.
- **Any source, for EXPLOIT names, when the order-path gate scaled EXPLOIT.** The gate's scale for a different book is not modelled.
- **llm, for names whose catalyst component is active.** Card events and calendar events are mixed in that component.
- **news is IDENTICAL_NOT_READ.** Its real question is answered by `mdc_news_tilt`.
- **Held fixed under every leave-one-out:** contract refusals and funnel membership.
- **Not modelled:** insiders and NN/ML (they need a funnel re-run).

## Not done

- Fill time and fill price: the grader prices at the reference open or close, not at the broker fill.
- A raw daily panel for dividend-break detection.
- Restarting the sim session onto the new `u_plan`: that is owner/orchestrator work, and the running session was not touched.
