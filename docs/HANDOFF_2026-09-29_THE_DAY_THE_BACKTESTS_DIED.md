# HANDOFF 2026-09-29: the day the backtests died

TIER: dated handoff (a diary, not a source of truth; the truth is code, receipts and TIER 0).
Sources: `docs/research_notes/2026-09-29/*.md` and `docs/reviews/REVIEW_2026-09-29_*.md`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** Every historical lead we carried into the day was re-run on a
survivorship-free panel (CRSP 1991-2024) and none survived as a strategy that beats the market
after costs. Three forward candidates were frozen. None has a graded day yet.

| line | today |
|---|---|
| Best historical net strategy vs market | **None.** Library on CRSP: 133 rules tested, **0 pass the deflated Sharpe**. The momentum lead is **+0.10%/mo over its twin, t 0.33**. `co03` with frictions reaches t 1.91 and is **negative vs the market**. |
| Best forward paper strategy | **None graded.** Frozen and waiting: SHADOW_BAYES_v1 `0f038859b2ebea62`, SHADOW_NEWS_v0 `f3b149ea42311760` (first grades 2026-10-09), CRSP_BLEND_v0 (commit 80ae2c80, review 34/100). Straddle forward log `a0f7e02d84444332`, first entry 2026-10-16. |
| Independent selector count | Unchanged in evidence. Three new shadow books are registered; none has a result. |
| Candidates tested / promoted | 133 CRSP rules + the momentum lead + the blend + size-for-sizing tested. **0 promoted.** |
| New actionable finding | Negative ones: the vendor panel was selected on 2026 liquidity; 174,417 non-trade bars removed; the forecast of move size does not help stock sizing; the local fine-tuned model loses to TF-IDF. |
| External execution drag | Not measured today. |
| LLM spend | World digest $0.35; ft_lab $0.27 + $0.03 (DeepSeek ledger); the night before $1.47 by provider balance. |
| Cost per gradeable output | Undefined: no output graded yet. First digest grades 2026-10-09. |

## Commits on main

- **9b362a5b**: registrations before the 2026-09-29 open. SHADOW_BAYES_v1, SHADOW_NEWS_v0, the dated
  v0 amendment, trial amendments.
- **21aa8ffd**: the day's code. Full suite **12,496 passed**. CI green.
- **80ae2c80**: CRSP_BLEND_v0 registration. A four-rule blend chosen after looking at the CRSP board.
  Forward candidate only.

## What the day found

**The backtests.**
- Momentum on CRSP 1991-2024: **+0.10%/mo over the matched twin, t 0.33.** The vendor-panel edge was
  mostly the panel. (`momentum_on_crsp_2026-09-29.md`)
- The vendor panel was selected on 2026 liquidity. That is survivor selection by construction.
  **174,417 non-trade bars** were removed. (`broken_price_histories_2026-09-29.md`,
  `stitched_tickers_2026-09-29.md`)
- Library on CRSP: 133 rules run (plus 7 controls). **0 pass the deflated Sharpe.** 172 rules were not
  run, because their point-in-time inputs do not exist in the CRSP era on disk.
  (`library_on_crsp_2026-09-29.md`)
- The blend CRSP_BLEND_v0 was reviewed at **34/100**. Its selection procedure fails forward.
  (`REVIEW_2026-09-29_CRSP_BLEND.md`)
- `co03` with frictions: t 1.91, and negative vs the market.
- Sizing: the size forecast does not help stock sizing. It moved to a forward straddle log instead,
  contract `a0f7e02d84444332`, first entry 2026-10-16. (`sizing_on_move_size_2026-09-29.md`,
  `straddle_forward_log_2026-09-29.md`, `TRIAL-STRADDLE-FWD-1`)

**The forward books.**
- World digest built. SHADOW_NEWS_v0 `f3b149ea42311760` reads it. First grades 2026-10-09.
  (`world_digest_2026-09-29.md`)
- nn_lab trust weights are now **forward-only, and all zero**. The earlier weights were backtest
  ratios. (`REVIEW_2026-09-29_NN_LAB.md`, `REVIEW_2026-09-29_SHADOW_BOOK_AND_TRUST_WEIGHTS.md`)
- SHADOW_BAYES_v1 `0f038859b2ebea62` frozen.

**The machine and the reader.**
- OpenClaw LLM turns could use the shell: **127 calls on 09-28**. They are now read-only.
  (`openclaw_tool_scope_2026-09-29.md`, `REVIEW_2026-09-29_READER_POOL.md`)
- The gateway memory floor was restored to the measured rule (no start below the floor).
  (`REVIEW_2026-09-29_MORNING_TEST_FIXES.md`)
- The reader browses general news at about **404 OK pages/hour**. It keeps an anchor tab and can
  relaunch Chrome. (`reader_browse_lane_2026-09-29.md`)
- ft_lab: the fine-tuned model loses to TF-IDF. The local extractor scores **90.7%** vs DeepSeek
  **94.0%** against a blind judge. It is wired OFF. (`ft_lab_first_run_2026-09-29.md`)
- Contest: keep the current rule. The odds table is in `contest_desk_2026-09-29.md`.

## WHAT THE ORCHESTRATOR GOT WRONG

1. It told the owner that nn_lab weights were earned from graded results. They were backtest ratios.
2. It restarted the reader at 08:52 without checking it had work. The reader idled for 100 minutes.
3. It briefed a shadow book inside its own roadmap's no-new-book window.

## Owner decisions outstanding

- **Bloomberg challenge registration** before 2026-10-04 23:59 HKT.
- **hack5**: the BE 290/320 call spread expires 2026-10-16. Hold or close.
- **Website**: sleep (cheap, lanes stale since 18 Sep) vs a boot-time catch-up.
  (`REVIEW_2026-09-29_RAILWAY_COST.md`)
- **Sign-up design** for the browser agent: approve or not. (`browser_signin_signup_design_2026-09-29.md`)
- **Whether to void CRSP_BLEND_v0.** It was chosen after looking.
- **conftest should block local ports 18802/18789.** A test-code change; needs a builder.

## NEXT, IN ORDER

1. Bridge point-in-time analyst, insider and filing inputs to CRSP, for the 172 rules not run.
2. Pre-register the price-target reversal.
3. Finish the bulk extraction (~5.5 GPU hours, $0).
4. Grade digest rows from 2026-10-09.
5. `vol_compression` friction test.

## WHAT WORKS

- Re-running every lead on a survivorship-free panel. It killed them cheaply and early.
- Freezing forward books before the open, with twins.
- The reader on general news, with its own recovery.
- Adversarial reviews: they caught the trust weights, the blend's selection and the shell access.

## WHAT DOES NOT

- Any historical rule we hold, as a strategy that beats the market after costs.
- The size forecast as a stock-sizing input.
- The local fine-tuned model as a replacement for TF-IDF or DeepSeek.
- Weights labelled as earned when no forward grade exists.

## HIGHEST-EV EXPERIMENT

Bridge the point-in-time analyst, insider and filing inputs to CRSP, and run the 172 untested rules
on the same survivorship-free board. It is the only large pool of untested ideas left, it costs no
LLM dollars, and a clean negative closes most of the library for good.
