# HANDOFF 2026-10-02: the clean session

TIER: dated handoff (a diary, not a source of truth; the truth is code, receipts and TIER 0).
Covers 2026-09-29 17:15 (the previous handoff) to 2026-10-02 22:10 HKT. Written for a NEW session
that the owner will open with a longer brief. Read this file, then the roadmap, then act.

Sources, in the order they were read: `HANDOFF_2026-09-29_THE_DAY_THE_BACKTESTS_DIED.md`;
`research_notes/2026-09-29/*` (evening sections); `research_notes/2026-09-30/*`;
`research_notes/2026-10-02/*`; `CONTEST_RUNBOOK_2026-10.md`; four TRIALS files;
`reviews/REVIEW_2026-09-29_*`; `ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md`;
`backend/data/optimus/sim/night_operator_2026-09-29.md`.

---

## 1. RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** No receipt shows a strategy that beats the market after costs,
historically or forward. The three days produced more negatives, one big correction to how we
score rules (the twin drag is a cost convention), and plumbing fixes that put the graders back on
current bars.

| line | value | receipt |
|---|---|---|
| Best historical net strategy vs market | **None.** 301 of 312 library rules now run on survivor-free CRSP 1991-2024. 1 of 301 shows net minus market at t >= 2 in validation, on an undeclared read, and the declared read of the same rule is t 1.01. | `research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md`, `hypothesis_lab_2026-09-30.md` §1 |
| Best forward paper strategy | **None graded beyond 3 sessions.** Descriptive only: CRSP_BLEND_v0 +1.50% vs SPY at session 3 of 21. Contest rehearsal +4.66% relative over 2 sessions, 93% of it one name (ACN). | `llm_portfolio/leaderboard_2026-10-02.json`; `contest/rehearsal/grades/grade_20261002T063006Z.json` |
| Independent selector count | **5 fleet sources live** (hack1 themes, hack2 revision flow, hack4 engine funnel 1/sigma, hack6 news; hack5 is the SPY control) **+ 4 shadow books** (CRSP_BLEND_v0, SHADOW_BAYES_v0/v1, SHADOW_NEWS_v0). Zero have evidence yet. | `paper_accounts/fleet_manager/modes.json`; `llm_portfolio/books.jsonl` |
| Candidates tested / promoted | 76 analyst/insider rules, 85 bridged rules, 10 conditionals, 2 revision-tilt bases, 11 hypothesis cells, 35 investable / vol-managed / insider-event cells, 1 PT-reversal trial, the LLM battery. **0 promoted, 0 registered.** | the notes above |
| Search count (deflation) | **42,705**: 489 new search cells since the CRSP_BLEND review (42,216). | `hypothesis_lab_2026-09-30.md`, second shift scoreboard |
| New actionable finding | **The twin drag is a cost convention.** The matched twin was charged a full round trip every month; rules paid only their own turnover. Of 161 rules that "beat their twin at t >= 2", **18 do on gross selection**. The two "SURVIVES" rules of 09-30 rest on this artefact. | `hyp_lab/twin_board_SUMMARY_TB_2026-09-30_1.json` |
| External execution drag | Not measured on fills. Quoted straddle spreads are ~2x the lab's assumption (median 11.5% of mid on names that pass filters). | `straddle_forward_log_2026-09-29.md` |
| LLM spend | ~$2.55 by provider balance, 09-30 to 10-02 (mostly the world digest). The 09-29 night: $0.61 ledger / $1.51 at peak list price (hyp_lab). | `automation_audit_2026-10-02.md`; `hyp_lab/spend.jsonl` |
| Cost per gradeable output | **Undefined.** The digest's first 5-session rows mature 2026-10-09. 674 older forecasts were graded on 10-02 at $0 grading cost. | `night_factory_2026-10-02/grade_forecasts_2026-10-02.json` |
| Commits | **Nothing since `8ac64468` is committed.** ~1,136 changed paths on `wip/2026-09-29-day`: six night builds plus the 10-02 fixes. | `research_notes/2026-10-02/uncommitted_tree_audit_2026-10-02.md` |

---

## 2. WHAT IS TRUE NOW

### 2.1 Data

- **The vendor panel was selected on 2026 liquidity.** Its symbol list was "alive on 2026-09-01",
  so it is survivor-selected by construction. Never backtest a price rule on it again.
  (`momentum_on_crsp_2026-09-29.md`, `broken_price_histories_2026-09-29.md`)
- **The bar-defect screen** removed 174,417 non-trade bars. It runs at LOAD time
  (`xs_ranker.load_bars -> stitched_tickers.split_stitched -> bar_defects.screen`).
  (`stitched_tickers_2026-09-29.md`, `automation_fixes_2026-10-02.md` §1)
- **Bars are current again: newest 2026-10-01** (the last closed session at fix time). They were
  stuck on 2026-09-28 from 09-29 to 10-02 (see 2.8).

### 2.2 The library and conditionals on CRSP

| item | value | receipt |
|---|---|---|
| Rules run on CRSP | **301 of 312.** 11 blocked: 5 need news history (none before 2026-09-11), 6 need FINRA short volume (2009+, not on disk) | `bridges_and_conditionals_2026-09-30.md` |
| Rules that beat the market net, in validation (2009-2016), at t >= 2 | **0** on any declared read | same |
| Conditional cells (10 declared, read once) | 0 CANDIDATE, 2 CANNOT_DISTINGUISH (insider clusters after drawdowns; 13F concentrated initiations), 8 FAILED_VARIANT | same, §3 |
| Analyst/insider bridge (76 rules) | 0 of 76 meet the line; insider buying (Form 4) is nothing | `analyst_insider_on_crsp_2026-09-29.md` |
| Revision flow as a capped tilt | top-500: FAILED_VARIANT (-0.038%/mo, t -0.60); ranks 501-1500: CANNOT_DISTINGUISH (+0.11%/mo, t 0.54) | `revision_tilt_2026-09-29.md` |
| Restatement (first-reported vs latest fundamentals, 2009+) | does not move quality or cash_lowvol (paired -0.003 and -0.027%/mo); picks overlap 98-99% | `hyp_lab/restatement_RESULTS_RS_2026-09-30T0050Z.json` |
| ANALYST-SKILL-1 | ran 2026-09-26 as registered: ADOPT by its rule, effect ~1/12 of the declared size | `ANALYST_SKILL_1_VERDICT_2026-09-26.md` |

**What beats the twin, and why that is not enough.**
- First reading (09-30 evening): `quality_composite` and `cash_lowvol` beat their matched twin at
  t ~6 (DSR 0.98) and the market by only +0.07 / +0.03%/mo. The twin trailed the market by ~0.6%/mo.
- Corrected reading (09-30 night): the twin's portfolio tracks the market gross (within ~0.1%/mo).
  The whole 0.6%/mo drag is its cost charge. On **pure selection** (gross vs gross) quality is
  t 1.6 and cash_lowvol t 2.3: both re-read as **CANNOT_DISTINGUISH**.
- Still real as relative rankings (pure selection t >= 2.5): the revision family
  (`net_raises_trend` 3.8, `mom_flow_trend` 3.2, `ear_flow` 2.9). None pays against the market net.
- Investable versions (beta-hedged, short-the-twin, top-500 overlay): **0 of 22 survive.** Closest
  miss: `cash_lowvol` beta-hedged, full 1991-2024 +0.30%/mo t 2.65, validation 7 of 8 years positive,
  validation t 1.36. Not registered. (`investable_RESULTS_INV_2026-09-30T0020Z.json`)

### 2.3 Size is forecastable; direction is not

- **Earnings in the hold window** (from 8-K cadence, known beforehand) adds **+0.0067 rank IC** to
  the 5-session size forecast (t 5.76, 6 of 7 years). It is in the nn_lab nightly as `vol_earn` at
  weight 0. (`nn_lab_size_members_2026-09-30.md`)
- Earnings cells move +0.22 to +0.29 log units more than trailing vol predicts, every month of 2025
  and 2026. TF-IDF already carries it, so it adds no IC there. It is a risk fact, not alpha.
- Size does **not** help stock sizing, and a better vol forecast does **not** make a better
  vol-managed market book (FAILED_VARIANT for log utility; drawdown -33% vs -54% at equal wealth).
  (`sizing_on_move_size_2026-09-29.md`, `hyp_lab/volmanaged_RESULTS_VM_2026-09-30T0115Z.json`)
- Next-session read-through (earnings shock to linked names; oil/yield shocks to baskets): priced the
  same session. 8 hypothesis cells: 4 FAILED_VARIANT, 4 CANNOT_DISTINGUISH.

### 2.4 LLM results

| test | result | receipt |
|---|---|---|
| Blinded, post-cutoff news -> next move size (DeepSeek and local 7B) | **No arm beats the numbers.** Q3 ranking IC +0.042 alone; +0.004 over the numbers model (MDE 0.049) | `llm_theories_2026-09-30.md` |
| Forced single probability (Q1) | **Abstention.** DeepSeek sd 0.0056 around the base rate; the 7B said 0.45 on 237 of 240 | same |
| Local fine-tuned extractor vs DeepSeek, against a blind judge | event type right 90.7% vs 94.0%; material errors 17 vs 9. Wired OFF. Bulk conversion finished: 343,126 of 343,126 rows | `ft_lab_first_run_2026-09-29.md`; `ft_lab/receipts/bulk_events_progress.json` |
| TRIAL-PT-REVERSAL-1 (price-target fade, read once on 2025) | gross -0.14% (t -0.91): **FAILED_VARIANT**, retired | `ft_lab/receipts/pt_reversal_read.json` |
| Live forecast arms (last skill report, 09-29) | the free sigma_63 prior beats the LLM arms on size (h=1 +14.1% vs +10.6%); direction h=5 is **-7.9%** (anti-skill) | `learning_reports/report_2026-09-29.md` |

### 2.5 The fleet (broker read 2026-10-02, `paper_accounts/roi_2026-10-02.json`)

All five readable accounts run **v2 contracts, LIVE**, since 2026-09-29 16:02-16:06 UTC, on the
owner's instruction. Inception 2026-08-28; SPY over the same window +0.17%.

| account | alpha source (v2 hash) | equity | since 08-28 | worst case at stops (10-01) |
|---|---|---:|---:|---:|
| hack1 | human + AI themes (`bdae86290ea38481`) | $91,678 | -8.32% | $8,674 |
| hack2 | analyst revision flow (`2301fa30c7b851df`) | $101,138 | +1.14% | $11,133 |
| hack3 | none: key answers HTTP 401 since 09-22; 9 positions unmanaged | unreadable | - | unknown |
| hack4 | engine funnel, 1/sigma sizing (`a0c5313766c52c9a`) | $79,483 | -20.52% | $3,854 |
| hack5 | market CONTROL, ~95% SPY (`98f677b18293c710`) | $95,254 | -4.75% | stop at ~14.5 sigma |
| hack6 | world-digest news (`12fa05317df05ce1`) | $81,676 | -18.32% | $6,085 |
| PC-PAPER | research engine PROBE book, 10 positions (inception 09-22) | $1,001,358 | +0.14% (SPY -0.39%) | gross cap 20% |

- Most of each hack's loss predates v2 (the Railway loops). v2 has 3 sessions: fleet +0.22% over
  09-30 and 10-01 vs SPY ~flat. (`review_paper_accounts_2026-10-02.md`)
- hack5's BE 290/320 call spread closed on 09-29 as one order at a $9.00 credit (+~$1,680).
- Fleet manager: two passes a day, 0 reconciliation mismatches, 0 foreign orders in 4 runs.
- Tight stops: KTOS filled 09-30 (cost $5.45 vs holding); BIOA filled 10-01; EVLV and RZLV still rest.
- Website lanes (simulated, not broker): -3.56%; newest mark 10-01 (one day behind).

### 2.6 Shadow books (frozen; read on schedule, never early)

| book | id / twin | entry | session at 10-02 | first read |
|---|---|---|---|---|
| CRSP_BLEND_v0 | `b0a33a92c56fddb1` / `b35d287bdcbf00bb` | 09-29 open | 3 of 21 | session 21, about **2026-10-27**. Kill line amended to the measured gap (the idiosyncratic-only line false-killed ~21%). **Kept, not voided**; reviewed 34/100 as chosen after looking |
| SHADOW_BAYES_v1 | `0f038859b2ebea62` / `be5e940728613d94` | 09-29 open | 3 | sessions 21 and 63; kill if D < -8.32% |
| SHADOW_BAYES_v0 (sleeve) | `439fd84f869744e0` | - | - | as registered (+0.93% vs SPY to date, descriptive) |
| SHADOW_NEWS_v0 | `f3b149ea42311760` | per digest cycle | trust 0 in all 16 decision rows: the tilt has moved nothing | trust can first leave 0 after 3 graded decision dates (~2026-10-11) |
| Library vs twins (TRIAL-LIB-FWD-TWIN-1) | the sealed library books | 09-28 | 1 real session (re-served 4x while bars were stuck) | early kill 2026-10-26 (z_21 <= -2); decision at session 63 |

### 2.7 Contest, straddle, digest

- **Bloomberg Global Trading Challenge.** Registration closes **2026-10-04 23:59 HKT**. Contest
  Oct 12 - Nov 13; first contest sheet Oct 11 14:30 HKT; initial positions due Oct 16.
  Runbook: `docs/CONTEST_RUNBOOK_2026-10.md` (page 2 = 17-item rules checklist).
- **Recommended book: ROT5_TRAIL** (5 names x 20%, buy before the print, hold through it). It is a
  variance bet: zero direction skill is assumed.

  | reading (10 bps a side) | P(> +40% relative) | P(< -20%) |
  |---|---|---|
  | zero skill, Octobers 2019-25 | 2.5-4.9% | ~25% |
  | 2024-26 regime, zero skill | 6.4-7.9% | - |
  | season drift repeats (optimistic) | ~17% | ~30% |
  | realised history | 0-1 of 7 Octobers | 2 of 7 |

  Fallback **MAXTAIL_BH** (five highest-vol names, held): 2.2-3.9%, insensitive to costs. Use it if
  fills are next-open-after-close, commissions >= 25 bps, or proceeds settle T+1.
  (`contest_dress_rehearsal_2026-09-29.md`; 13 of 13 drills pass)
- Rehearsal: sheets every day 09-29 to 10-02. The 09-29 sheet was VOID_LATE (frozen 13 minutes after
  the open). Rehearsal buys through Oct 9, then sell-only.
- **Straddle forward log** (TRIAL-STRADDLE-FWD-1, contract `a0f7e02d84444332`): first entry
  **2026-10-16**, first grade 2026-11-20 expiry, first formal read at 12 expiries.
- **World digest:** every 6 h, ~$0.15 a run. First grades: 1-session rows 10-03, **5-session rows
  2026-10-09**, 20-session rows 10-31. The digest receipts record **$0.00** spend in all 16 files
  while the provider balance fell ~$2.55: an always-zero reader, owed a check.

### 2.8 The three-day blackout (09-29 22:30 UTC to 10-02)

- **Cause: one ticker.** `BRK-B` in the new forecast-only side panel. The vendor rejects the whole
  100-symbol request (`BRK.B` works). The refresher refused correctly ("nothing overwritten") on
  every attempt; nobody read the refusals.
- **Effect:** forecast grader frozen at 17,783 graded (676 past due), library leaderboard and bridge
  re-served one session four times, straddle refused in-window, alerts could not grade, nn_lab
  learned nothing.
- **Fix (10-02):** vendor notation, drop-and-name an invalid symbol, continue; new
  `backend/services/bars_health.py` puts a DEGRADED line at the top of the daily pass and alert
  receipts when any panel misses one closed session.
- **After the fix:** the hand-run daily pass graded **674 forecasts** (18,457 of 33,014 resolved),
  12 ok / 0 refused, `degraded: []`. (`night_factory_2026-10-02/daily_pass_2026-10-02_run02.json`)

---

## 3. WHAT RUNS BY ITSELF

Times are HKT (UTC+8). New York is 12 h behind until Sun 2026-11-01, 13 h after. STOP paths are
under `backend/data/optimus/`. A STOP file binds until a person deletes it.

| task | when (HKT / New York) | writes | STOP |
|---|---|---|---|
| AegisAlerts | every 30 min | `alerts/receipts/`, Telegram sends (2 LIVE on 10-02) | `alerts/STOP` |
| AegisWorldDigest | 00:30, 06:30, 12:30, 18:30 / 12:30, 18:30, 00:30, 06:30 | `digest/world_digest_*`, frozen ledger rows | `news_digest/STOP` |
| AegisStraddleForward | every 30 min; acts 10:45-15:30 ET only | `straddle_forward/` | `straddle_forward/STOP` |
| AegisContestRehearsal | 14:30 / 02:30, Sep 30 - Oct 15 | `contest/rehearsal/sheets`, `grades` | `contest/rehearsal/STOP` or `contest/STOP` |
| AegisContestDesk | 14:30 / 02:30 from Oct 9 (first contest sheet Oct 11) | `contest/live/sheets/` | `contest/STOP` |
| AegisDailyPass | 06:30 / 18:30 prev. day | `night_factory_<date>/daily_pass_*.json` (grades, books, broker-read ROI, health) | none of its own; each step honours its own |
| AegisFleetDailyCheck | 06:45 / 18:45 prev. day, read-only | `paper_accounts/fleet_daily/` | - |
| AegisFleetManagerOpen | Mon-Fri 22:45 / 10:45 (09:45 after Nov 1) | live orders, `fleet_manager/runs`, `grades.jsonl` | `paper_accounts/fleet_manager/STOP`; per-account `modes.json` |
| AegisFleetManagerPreclose | Tue-Sat 03:30 / 15:30 (14:30 after Nov 1) | stop replacements, reconciliation | same |
| AegisHypLabNightly | 09:30 / 21:30 prev. day | `hyp_lab/` ledger + cells (night cap $3, run cap $0.40) | `hyp_lab/STOP` (a STOP older than 48 h is now reported as "possibly forgotten") |
| AegisNNLabNightly | 08:30 / 20:30 prev. day | `nn_lab/receipts/` | `nn_lab/STOP`. **Refusing every night now** (`TableShrink`, see §5) |
| AegisAnalystPanelDaily | 05:30 / 17:30 prev. day (terminal repo) | analyst panel | - |
| AegisIIF1NightLauncher | 16:00 / 04:00 | starts a sim session if a safe window remains; refused on 10-02 | sim `request_stop` |
| AegisReaderSupervisor (new) | logon, unlock, resume, 07:00, every 2 h | relaunches the reader supervisor with `--until` 23 h ahead; never a second copy | `dowjones/SUPERVISOR_STOP` |
| AegisCatchUp (new) | same triggers | starts any daily job whose last run was missed (max age 20 h), and owed learning reports. Never the fleet passes | each task's own STOP |
| AegisTelegramAgent | at logon, supervised | answers the owner's chat | `telegram/STOP` |
| OpenClaw Gateway | at logon | the reader's browser gateway | - |

- **Catch-up and wake:** the ten daily jobs now start as soon as possible after a missed start and
  may wake the machine; whether it actually wakes depends on a local setting (recorded locally).
- **always_on_lab is OFF** by a persistent marker `always_on_lab_OFF`. A logon script dated
  2026-09-13 used to relaunch it at every boot. Deleting the marker turns it back on.
- **No sim session has run since `ad32603783de` (09-29, 8 h, 0 orders).** The zero orders were
  PROBE already full (20% cap) with EXPLOIT `MEASURED_NEGATIVE`, not the mandate.
- **Railway:** the four trading loops are down (services, volumes and backups kept; redeploy is
  possible). The website runs 24/7 with sleeping OFF so its close marks fire. seal-authority
  unchanged. The plan is $20/month including $20 of usage.
- **The reader:** 4,000 page loads a day, spent by lane and by UTC hour. Read-only, the dedicated
  MuratClaw Chrome only. The live list of allowed hosts is generated, never hand-edited:
  `backend/data/optimus/dowjones/WHAT_THE_READER_OPENS.md`
  (`python -m backend.services.reader_report --what-opens`).
  - Allowed in the browser: WSJ, Barron's, MarketWatch (owner's subscription); FT, Nikkei, SCMP
    fronts and free pieces; Reuters, AP, CNBC, Yahoo Finance, BBC; bls.gov, sec.gov, treasury.gov;
    X, Reddit, StockTwits (read only, no sign-in).
  - Feed/API only: central banks (Fed, ECB, BoJ, BoE, HKMA), SEC Form 4/8-K/13D-G/13F, House PTRs,
    CFTC COT, FINRA short interest, Federal Register.
  - Refused on every path: bank, broker, payment, checkout and mail hosts (`MONEY_HOSTS`,
    `CHECKOUT_HOSTS`, `CHECKOUT_PATH`); a checkout frame makes the page PAYWALL_STUB. Refused
    sources: Senate eFD (403 + agreement), PBoC and Nasdaq earnings API (robots.txt).
- **Telegram commands** (`scripts/telegram_agent.py`; the bot never orders or approves on its own):
  `/nav /books /forecasts /broker /book /brief` (receipts, no model) ·
  `/ask /research /deep` (model; `/research` and `/deep` wait for `/approve`) · `/compare` ·
  `/sim status|start N|smoke 30|stop|resume` · `/pending /approve <id> /deny <id>` ·
  `/status /system /help` · plain text: `stock T`, `news T`, `report`, `digest <text>`,
  `analyze <alert id>`, `ask <q>`, `queue`.

---

## 4. STANDING RULES (in force)

Owner's words, 2026-09-28: *"dont use any payments, dont send any messages or emails without asking
me, use muratclaw mainly"*, and on process: *"dont build anything, only use opus 5.5 to build and
also try to attack the project and review with it too, sonnet for research"*.

1. No payments, checkout, subscribe or billing actions, ever.
2. No messages, posts, replies or emails without asking the owner.
3. Browsing is read-only: navigate, scroll, read, open a link, close our own tab. No typing into forms.
4. The dedicated MuratClaw Chrome only. Never attach to the owner's main Chrome.
5. Brokerage, bank, payment and mail hosts are refused. The broker is reached only by API from
   deterministic code.
6. Free sign-ups only through the written design (`browser_signin_signup_design_2026-09-29.md`),
   and only after the owner approves it and names the sites. Not built.
7. DeepSeek is the only paid LLM provider.
8. No LLM authority over capital.
9. X, Reddit and StockTwits never originate an order.
10. Never kill by image name. Kill by a PID you recorded, after checking its command line, or not at all.
11. No machine details in git (memory, graphics card, PIDs, power settings, user-home paths). They
    live in `backend/data/optimus/local_pc/`.
12. Fable orchestrates and monitors only. Opus 5.5 builds and attacks. Sonnet researches.
13. Every build gets an adversarial investor review by a second Opus.
14. Every handoff opens with the RESULTS SCOREBOARD.
15. Commit only on a full-suite exit 0, read from the exit code, never from `tail`.
16. Find what exists before building (`brain_query`, `aegis_postmortems`, `docs/TRIALS/`).
17. **The three licences** (CLAUDE.md): `PRODUCT_EXPERIMENT` needs a frozen contract before the first
    decision; `CAPITAL_CANDIDATE` needs matured forward evidence and attended promotion;
    `RESEARCH_CLAIM` needs full preregistration. PIT discipline, realistic costs, frozen versions and
    no backfilled forward evidence never relax.

---

## 5. OWNER DECISIONS OUTSTANDING

| # | decision | why it matters | recommendation / receipt |
|---|---|---|---|
| 1 | **Bloomberg registration, by 2026-10-04 23:59 HKT** | nothing else about the contest matters without it | `CONTEST_RUNBOOK_2026-10.md` |
| 2 | Contest rules checklist: items 1 (fill convention), 2 (commissions), 3 (cap basis), 5 (same-session proceeds), 12 (relative P&L), 13 (trade limits); the WLS `MEMB` export | items 1, 2, 5 and 13 decide ROT5_TRAIL vs MAXTAIL_BH | runbook page 2 |
| 3 | hack3: regenerate the key or close the account in the broker UI | 9 positions unread and unmanaged since 09-22 | `ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md` |
| 4 | nn_lab: freeze stored grid membership on append (labels only), or accept re-adjusted membership | nn_lab refuses every night (`TableShrink`, EQBK/THFF) after 313 dividend re-adjustments | `automation_fixes_2026-10-02.md` §3 |
| 5 | PC-PAPER mandate: the contract is sized on **$40,000**, broker equity is **~$1,000,000** | the mandate stays UNRECONCILED; the sim places nothing new | same, §6 |
| 6 | The two remaining tight stops (EVLV ~0.9 sigma, RZLV ~0.9 sigma) | the manager never loosens a stop; widening raises the worst case | `fleet_daily_manager_2026-09-29.md` |
| 7 | Whether alerts, digest and straddle may run on battery | they repeat every 30 min / 6 h and are not set to wake the machine | local |
| 8 | Telegram LIVE alerts to the owner (2 sent on 10-02) | the 09-28 rule held such alerts until the owner confirmed they count as asked | `automation_audit_2026-10-02.md` |
| 9 | Sign-up design: yes / no / which three sites | not built | `browser_signin_signup_design_2026-09-29.md` |
| 10 | Rewrite public git history to remove old machine details | **Recommended no**: the details are not secrets; rewriting a public repo breaks every hash quoted in the docs | `uncommitted_tree_audit_2026-10-02.md` §2 |
| 11 | CRSP_BLEND_v0: void or keep | **Kept** as a free shadow; the forward record is the evidence; quote nothing from it as a lead | `AMENDMENT_CRSP_BLEND_v0_KILL_RULE_2026-09-29.json` |
| 12 | More hacks on v2 | **Already done** for all five readable accounts on 09-29. Only hack3 remains, and it needs #3 | `fleet_manager/modes.json` |
| 13 | hyp_lab ranking policy: shrink EV when a family's posterior is below 0.15 | macro lead-lags stay near the top after five failures | `hypothesis_lab_2026-09-30.md` §6 |

---

## 6. WHAT WAS LEARNED

| lesson | receipt |
|---|---|
| A twin charged a full round trip every month makes every low-turnover rule look real: 106 "wins" were 18. Compare gross vs gross, or a fair twin. | `hyp_lab/twin_board_SUMMARY_TB_2026-09-30_1.json` |
| A rule that beats its twin but not the market is not an edge. Print net minus market on every receipt. | `bridges_and_conditionals_2026-09-30.md` |
| One invalid symbol can stall every grader for days: the vendor rejects the whole request. | `prices_2025_26/bars_refresh/20261002T123000Z.json` |
| Failures were loud but unread: four refusal receipts and a DEGRADED grader sat for three days. A red line needs a reader. | `automation_audit_2026-10-02.md` |
| A job with no scheduled owner dies at its own cutoff: the reader was silent 57.5 hours. | same |
| A startup script from three weeks ago overrides a dated stop file: the lab relaunched at three boots. | `automation_fixes_2026-10-02.md` §5 |
| A 0-byte STOP file blocks forever and says nothing; a STOP now writes why, since when, and how old. | same, §4 |
| An LLM asked for one probability measures the prompt: it returns the base rate. | `llm_theories_2026-09-30.md` |
| A top pick from 40,920 blends is selection, not a lead. | `reviews/REVIEW_2026-09-29_CRSP_BLEND.md` (34/100) |
| Vendor panels select on today's liquidity; only CRSP (with deaths) can adjudicate a price rule. | `momentum_on_crsp_2026-09-29.md` |
| A kill line from idiosyncratic sd alone false-kills ~21%, not 5%. Size it from the measured gap. | `AMENDMENT_CRSP_BLEND_v0_KILL_RULE_2026-09-29.json` |
| One session re-served four times is one session. Check `sessions_since_entry` before reading a bridge. | `review_forecasts_and_books_2026-10-02.md` §1 |
| A `--no-broker` doc run silently erased the fleet from `PAPER_ACCOUNTS.md`; a rewrite that drops an account now refuses. | `automation_fixes_2026-10-02.md` §8 |
| A reviewer's cause is a hypothesis: the zero-order sim was a full PROBE book, not the mandate. | same, §6 |
| Insider cluster drift is real gross (t 6) and equals the spread; in cheap names it is absent. | `hyp_lab/insider_events_RESULTS_IE_2026-09-30T0135Z.json` |
| Selling before an earnings print removes the contest tail entirely: the variance bought is the print. | `contest/strategy_lab/lab_20260929T134312Z.json` |

---

## 7. WHAT THE ORCHESTRATOR GOT WRONG

1. It told the owner the nn_lab weights were earned from graded results. They were backtest ratios.
2. It restarted the reader at 08:52 on 09-29 without checking it had work; it idled 100 minutes.
3. It briefed shadow books inside its own roadmap's no-new-book window.
4. **It let four continuation agents die at the weekly limit (00:00 on 09-30) with live code
   uncommitted.** The audit found the work complete and green, but 1,136 paths sit outside git.
5. **It did not route receipts to anyone.** Bars refusals and a DEGRADED grader went unread for
   three days while every downstream number froze.
6. **It restarted the reader without a scheduled owner.** The supervisor stopped at its own cutoff
   on 09-30 and nothing relaunched it for 57.5 hours.

---

## 8. NEXT, IN ORDER

| # | step | gate | cost |
|---|---|---|---|
| 0 | **Commit the tree** in the seven groups of the tree audit. First: scrub the machine details still in two 09-30 notes (`hypothesis_lab`, `llm_theories`), leave out `.playwright-mcp/` and the six large untracked files, explain or fix the one failing test in `test_reader_opens_and_feeds.py` | full suite exit 0 (one is running now); then `python -m scripts.ci_watch --wait` | $0 |
| 1 | Read the first DEGRADED-free daily pass after a real sleep/wake (10-03 to 10-05) | `grade_forecasts` adds rows, 7 broker rows, `learn_rota` ALIVE | $0 |
| 2 | Owner: Bloomberg registration and the rules checklist | 2026-10-04 23:59 HKT | owner's hour |
| 3 | **Fix the twin's cost charge in shared code** (`library_on_crsp`, `bridges_on_crsp_run`): the fair twin; re-issue board verdicts; pure selection and net minus market on every receipt | none | ~1 h, $0 |
| 4 | Grade the world digest | 5-session rows from **2026-10-09**; trust may leave 0 after 3 graded dates (~10-11) | $0 |
| 5 | Contest, Oct 12 - Nov 13, by the runbook | registration + checklist + WLS export; first sheet Oct 11 14:30 HKT; positions by Oct 16 | owner types tickets |
| 6 | Straddle forward log | first entry 2026-10-16; first grade 11-20; formal read at 12 expiries | $0 |
| 7 | First shadow-book reads | LIB-FWD-TWIN-1 early kill 2026-10-26; CRSP_BLEND_v0 and SHADOW_BAYES_v1 at session 21 (~10-27) | $0 |
| 8 | The 11 blocked rules | FINRA short volume 2009+ on disk (6 rules); news rules cannot run before years of history exist (5) | data pull |
| 9 | Underpowered forward tests: keep accruing, do not read early | CONGRESS-PTR-FWD-1 (MDE 5.2 pp, decision 2028-04-01); C02 insider clusters (MDE 1.58%/mo); straddle (12 expiries) | $0 |
| 10 | Hypothesis ledger top ten (59 rows) | owner decision #13 on the EV rule first; top row is H-1270b5a351 (vol-managed market for the preservation personality, needs a declared drawdown utility) | <$0.40/night |
| 11 | `vol_compression` with skip, real spreads and lag (owed since 09-29) | none | ~1 h, $0 |

**Done since the last NEXT list:** the analyst/insider/filing bridge (76 + 85 rules); the
price-target reversal registered and read; the bulk extraction finished; the quality and cash_lowvol
rerun on first-reported fundamentals (restatement moves nothing, and the "survival" was the twin
artefact).

**Stop doing:**
- Price-rule backtests on the vendor panel.
- Quoting "beats its twin" from the turnover-scaled board.
- New books before 2026-10-26, except shadows that need no capital.
- New guards without an actual failure behind them.

**Roadmap status** (`ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md`; do not rewrite before 10-05):

| lane | status |
|---|---|
| O OpenClaw | O1 dedicated Chrome, O2 repair, O4 read-only tool scope, O5 yield check, O6 pace by budget: **done**. The reader now has a scheduled owner |
| A Alerts | A1 scheduled caller **done**; grading unblocked 10-02; the 100-alert-date gate **open** |
| M Measurement | M1 superseded by CRSP (the vendor leads died there); M5 broker-read daily pass **done** 10-02; M6 LIB-FWD-TWIN-1 **registered**; M2 "twin beside every number" **open** and now means the fair twin (step 3) |
| P Paper money path | P1 verified (PROBE acting, full at 20%); P2 GOOG/GOOGL **fixed** (share-class dedup); P3 and P4 **open** (mandate unreconciled) |
| B Bloomberg | owner; rehearsal built, 13 drills pass |
| X StockBench / Kronos | **not started**; low priority |
| W The paper | **open**: a two-page outline naming receipts |

Note: `docs/INDEX.md` TIER 1 still names the 09-25 roadmaps; it does not list the 09-28 roadmap.
The next session should make the 09-28 roadmap (or its successor) the TIER 1 line.

---

## 9. HOW TO START THE NEXT SESSION

1. `session_briefing()` and `aegis_verified_state()` (Optimus MCP), before reading code.
2. `brain_query` and `aegis_postmortems` before proposing any research. Check `docs/TRIALS/`.
3. Read this file, then `ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md`, then TIER 0 in `docs/INDEX.md`.
4. Before any sizing, stop or cap change: print the worst case in dollars for the largest admissible book.
5. Check health (read-only):

```bash
python -m scripts.health_probe                              # every subsystem; DEAD/STALE first
python -m scripts.task_keeper status                        # scheduled jobs, catch-up state
python -m scripts.night_reader_supervisor --probe           # reader dependency probe
python -m backend.services.reader_report --lanes-hours 24   # pages by lane, host, hour
python -c "from backend.services import bars_health as B; print(B.check()['line'])"
# from the aegis-alpha-terminal repo root, read-only:
python -m scripts.fleet_daily_check
```

6. Where receipts live (all under `backend/data/optimus/`): daily pass
   `night_factory_<date>/daily_pass_<date>*.json` (its `degraded` block is printed first); forecast
   grades `night_factory_<date>/grade_forecasts_<date>.json`; bars `prices_2025_26/bars_refresh/`;
   fleet `paper_accounts/fleet_manager/runs/` and `paper_accounts/roi_<date>.json`; books
   `llm_portfolio/leaderboard_<date>.json`; shadows `shadow_bayes/`; contest `contest/rehearsal/`;
   digest `digest/`; hypotheses `hyp_lab/LEDGER.md`; jobs `task_keeper/keeper.jsonl`.
7. Run the suite as `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`,
   plus `nn_lab/tests` and `ft_lab/tests` separately. Never move `.env`.

**Credits.** The Opus weekly limit reset at 2026-10-02 12:00 HKT; the last reset killed four
builders mid-work, so commit before long runs and give continuation agents a commit step. Use Fable
only for planning and monitoring; Opus 5.5 builds and reviews; Sonnet reads.

---

## WHAT WORKS

- Re-running every lead on survivor-free CRSP with declarations hashed before the run. It closed
  hundreds of rules cheaply and caught its own scoring artefact.
- Decomposing a comparison before believing it (the twin table).
- The fleet manager: unattended, reconciled, every order traced to a decision row.
- Refusals that write a reason: bars refresh, straddle, the night launcher, the doc writer.

## WHAT DOES NOT

- Any rule, conditional, tilt or LLM arm as an edge against the market after costs.
- Unread failures: three days of correct refusals that nobody acted on.
- Jobs without a scheduled owner, and stop files that cannot explain themselves.
- Live code that lives only in a working tree.

## HIGHEST-EV EXPERIMENT

**Fix the twin's cost charge in the shared board code and re-issue every verdict** (step 3). It costs
an hour and $0, and it removes the largest single source of false "relative edge" claims the
programme has produced. Every later read, including the 10-26 library-vs-twin trial, depends on the
benchmark being fair.
