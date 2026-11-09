# ASKED vs DELIVERED — the full audit of 2026-11-09

> Read-only audit by 12 reader agents + 4 adversarial verifiers + a completeness critic over all 423 owner messages (Claude era 09-04 → 10-07, Codex era 10-08 → 11-08), the Codex handoff package (`Downloads/codex handoff/`, 11-06), git (`--all`), receipts, scheduled tasks, infra and storage. Corrections from the critic are applied inline and marked **[corrected]**. Every number is a snapshot of 2026-11-08/09; re-measure before acting.

For: Murat (owner). Sources: 12 reader reports, each checked by a verifier. Where a verifier corrected a status, the corrected status is used and marked *(V)*. All work was read-only. Numbers move during the day, so this is a snapshot (origin/main = `cd0b1d59`, 2026-11-09 00:05).

---

## 0. Summary

1. **Since early October, one uninitialised budget file has silently stopped most of the learning system.** `backend/services/provider_budget.py` is **untracked**, dated 2026-10-15 19:38, and from the Codex era. It refuses every DeepSeek call unless `session_budget/deepseek_local.json` exists. That file was never created; only a 0-byte `.lock` dated 2026-10-15 is there. As a result:
   - World Digest news typing has produced **0 typed rows since 10-15** (49,911 of 49,911 calls failed; 1,179 of 1,179 on 11-03).
   - IIF-1 has been **VOID for 13 nights** (stuck at 19/40).
   - hyp_lab has been **BUDGET_REFUSED since 10-16**.
   - The rule learner has written **0 rules since 10-18**. That is partly also because the local llama server is down while always_on_lab is OFF.
   - Most of those scheduled tasks still report rc 0 (exceptions: AegisWorldDigest was Disabled 11-06; FleetDailyCheck rc 1), and **$34.28 of DeepSeek credit sits unused** (11-03: granted $9.66, which can expire, + topped-up $24.61). **[corrected]**
   - **[corrected] The guard is not only a local untracked file: it is on origin/main** (`7f8869a8` 11-03 "Guard PC digest spending", `6b75aee6` 11-04). Main's version is stricter: `host_envelope_required()` ("Windows always participates"), `initialize()` accepts ONE envelope of <= $20 and refuses to replace an existing one "(even an exhausted file)", and books reservations at peak list price. **Unblocking needs a code change on main, not a config step.**
2. **The PC runs code that is not in any commit.** The scheduled tasks run from `C:\Users\mrthn\aegis-finance` on `wip/2026-10-07-day @4e192199` (2026-10-09). That checkout is 255 commits behind main and has 3,432 dirty paths. It imports untracked modules such as `native_admission.py`, `beta_v2_telegram_chat.py` and `frozen_constituent_prices.py`. It **lacks main's decision-grader fix `e737423b`**: the old grader recorded +20% excess where the true figure was −10%.
3. **Your sense that the Codex month was churn is supported by the evidence, with two caveats.**
   - What the evidence shows: about 205 non-merge commits on main and about 60k lines of code and tests. **Zero commit subjects** mention backtest, alpha, factor or ranker, and 89 of 163 non-receipt commits are guard or provenance work. Another 141 commits (about 46.7k lines, including the whole Beta V2 programme) are **stranded off main**. There are 121 worktrees. Every measured statistical result dates from 10-10 to 10-12, and all are null or negative.
   - Caveat one: the Claude era also never produced a demonstrated edge (momentum died on CRSP; no library rule reached DSR ≥ 0.95).
   - Caveat two: several decays began **before** the switch. The night factory collapsed on 10-03, typed_events stopped on 10-02, and always_on_lab has been OFF since 10-02. **[corrected]** It was not the owner's decision to switch it off for weeks: on 09-27 13:27 the owner asked to "stop all work for **30 mins** I need ram"; the 10-02 automation wrote a persistent `always_on_lab_OFF` marker recording that as "owner switched the lab OFF". A 30-minute pause became a five-week shutdown.
4. **No news reaches a universe or portfolio decision today.** The only news-to-holdings path, hack6's 1% news sleeve, went blind on 10-15 while printing `fresh: true`. The Meta, midterm and Iran calls were turned into saved cases, an inactive "stations" document and hand-written reports, not into system behaviour.
5. **What still works:** results_voice/ROI/book_dna, the daily decision contract, the nightly strategy library (the same 312 rules), nn_lab grading, the analyst-revision pull, outbound Telegram, the PC-PAPER book (99.6% invested, about 50% SPY, capital UNRECONCILED), and green CI on main (the repo is public again, so Actions minutes are free).

---

## 1. ASKED vs DELIVERED: master ledger

Status key: DONE · PARTIAL · NOT_DONE · SUPERSEDED · ABANDONED · UNKNOWN. *(V)* = the verifier changed the reader's status. "×n" = number of times you asked. Era = era of the **first** ask (C = Claude, X = Codex).

### 1.1 Profit, strategy and decision engine

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| S01 | 09-04 | 9+ | C | A backtest or engine that honestly beats SPY and is "capable of making profits"; raise CAGR/DSR | **NOT_DONE** | Growth Book 3.6684x vs SPY 3.6707x. 209 CRSP rules, none survives. Library `n_beat_both` went 70→62 (10-06→11-06) on the same 312 rules. No DSR ≥ 0.95. Rules 5ee19214/e30e5bc2/03376f6a/bc6fe2ce do not involve the LLM or NN |
| S02 | 09-04 | 1 | C | Fix the "250% vs 740%" benchmark claim | DONE | 4ae55a95, 5ecc6146; the 740% was ^GSPC with 66 overlapping windows |
| S03 | 09-04 | 5 | C | Don't kill ideas on one instance; not everything is noise; test rejected projects | PARTIAL | Typed statuses and 71a086a6 exist, but lanes kept closing. X2 elasticity PRODUCT_PROMISING and 8 hyp_lab CONDITIONAL_POSITIVE results were never carried into a book. Latest learned rules NO_SKILL |
| S04 | 09-19 | 6 | C | The engine must actually **decide**: take risk, short, act on probability rather than certainty, "punish not deciding", provisional decisions | **PARTIAL** (V) | 47 contracts 09-20..11-07: **0 EXPLOIT, 0 SELL**. Each day: 3 AGENCY sleeves, 1 EXPLORE name, 92–152 PROBEs. PC-PAPER 99.6% invested, but about 50% SPY and the rest frozen sleeves. Provisional-decision code dd9f312c is off main |
| S05 | 09-20 | 1 | C | EXPLOIT/EXPLORE split with Thompson sampling | **PARTIAL** (V) | Thompson code exists (decision_authority.py:37-94); the EXPLOIT side has never had a row |
| S06 | 09-13 | 3 | C | Kill losers, give winners capital, RL allocator, Book-of-Books | PARTIAL | One manual promotion (revision_flow sleeve into PC-PAPER, 10-07). No allocator, no RL, no book_of_books code. Spec only (spec_allocator_kill_promote.md) |
| S07 | 09-20 | 1 | C | Calibrate signal score to per-name E[r] | DONE | calibrate_signal_return.py / signal_calibration.py; result: nothing calibrated |
| S08 | 09-19 | 3 | C | Join the "logic brain" (LLM/context) to the "math brain" | PARTIAL | E[r] refit advantage 0.0 and unlicensed (refit_2026-11-06). Source weights are "PROPOSAL ONLY". Learner dead since 10-18 |
| S09 | 09-20 | 1 | C | A module is "finished" only when it moves capital or kills a hypothesis | NOT_DONE | No rule or test enforces this. signal_reachability only checks that a caller exists |
| S10 | 09-21 | 2 | C | Precursor detection (the Micron test, find it before the public does) | **PARTIAL** (V) | hyp_lab: 191 read-through hypotheses, 97 cells, 8 CONDITIONAL_POSITIVE (to 10-26); fast_movers forensics ran once. No live detector |
| S11 | 09-11 | 2 | C | Probabilities and scenarios instead of confidence; Bayesian evidence states; online FDR | PARTIAL | E3 conformal as a night script only. shadow_bayes and evidence labels in use. Online FDR not built |
| S12 | 09-08 | 4 | C | A day-trading or constantly-active book (lane D, 1%/day) | PARTIAL | Lane D seeded internally (book f64e8d99), never traded. hack2's reaction book was closed by its own tests |
| S13 | 09-11 | 1 | C | Analyst-style 52-week price targets | DONE | price_target.py, IBES backtest on 390k cells; receipts not refreshed since 09-12 |
| S14 | 09-25 | 2 | C | Weight analyst upside and backtest it | DONE (negative) | t −3.6/−7.2 (funnel evidence_basis); ANALYST_SKILL_1_VERDICT |
| S15 | 09-23 | 1 | C | Join SEC fundamentals to the ranker | DONE (negative) | Fundamentals tilt −1.34%/21d, t −2.55 |
| S16 | 09-11 | 3 | C | LinkedIn/hiring signals and an AI-pivot thesis (Adobe, Autodesk, GoPro) | PARTIAL | One hiring snapshot on 09-13, never re-pulled; no trial |
| S17 | 09-04 | 1 | C | CompanyWorld graph: sector, competitors, commodities, crypto, geopolitics | PARTIAL | 2,020 edges (customer 854, competitor 761, supplier 284…); no commodity, crypto or geopolitical edges |
| S18 | 09-07 | 4 | C | Psychology/behaviour signals, unsupervised discovery, self-attention, patents, interdisciplinary families | PARTIAL | TransformerEncoder lost to TF-IDF (09-08). nn_lab is an MLP. Patent and psychology work is docs only |
| S19 | 09-10 | 1 | C | A cheap encoder/decoder event network | PARTIAL | Tabular typed-event head E1/E2, closed at h=1 |
| S20 | 09-19 | 2 | C | China capacity entry / memory oversupply (CXMT/YMTC vs MU/NVDA/TSM) turned into long/short calls | PARTIAL | Draft trial TRIAL-DRAFT-FOREIGN-ENTRANT-IC-v0 only. The 10-11 assessment was never produced. 0 SELL rows ever |
| S21 | 09-20 | 2 | C | Highest-ROI engine using analyst targets, politicians, Polymarket, Trump policy, demand | PARTIAL | roi_rank/decision_authority: 0 EXPLOIT. Polymarket receipts stop 2026-08-21 |
| S22 | 09-20 | 1 | C | Gut-feeling calls tested with good and bad fiction scenarios | DONE | night_scenario_gym S2 ran once (42% directional) |
| S23 | 09-21 | 1 | C | LLM forecasts with demand/substitution context, plus adversarial agents | PARTIAL | Thesis cards ran 09-25..09-29 then stopped. Investigator skill is magnitude, not direction |
| S24 | 09-07 | 1 | C | Coverage normalisation | PARTIAL | Arena selection is normalised (pre-ask); sizing and confidence elsewhere are not |
| S25 | 09-07 | 2 | C | Mode A: you decide, the system learns from your decisions, and it tracks public investors | PARTIAL | Journal bridge built with 0 graded rows. No model trains on your actions |
| S26 | 09-11 | 1 | C | Create a portfolio from a sentence and hold it | PARTIAL | IPS questionnaire, one IPS (46e3c4f3); no NL-to-contract, and the review has no run trace |
| S27 | 09-25 | 2 | C | One clear, connected strategy | PARTIAL | ONE_PIPELINE is TIER 0; its E[r] step is unlicensed |
| S28 | 09-28 | 1 | C | Test Opus (frontier LLM) as the forecaster | NOT_DONE | DeepSeek only |
| S29 | 09-28 | 2 | C | Lean on LLM fine-tuning, scenarios and blinding | PARTIAL | ft_lab loses to TF-IDF; blinding ran once (x2) |
| S30 | 09-20 | 1 | C | MiroFish-style world simulator | NOT_DONE | Docs only |
| S31 | 09-07 | 3 | C | Study and adopt external repos (TradingAgents, freqtrade, Kronos, Nautilus…) | PARTIAL | freqtrade/Vibe ideas ported (S3-S8); Kronos FAILED_VARIANT; scrapling used; TradingAgents graph not ported |
| S32 | 09-07 | 1 | C | Landscape survey | DONE | EXTERNAL_2026-09-07_LANDSCAPE (it led to the Form 4 corpus) |
| S33 | 09-19 | 1 | C | Adjudicate your ideas, write failure theses, a context dossier | DONE | research_murat_ideas_adjudicated.md and others; few ideas tested afterwards |
| S34 | 09-25 | 1 | C | Add pharma | DONE | pers_pharma_binary_basket is the leader at +7.58pp; mechanism not recorded |
| S35 | 10-06 | 1 | C | Demonstrated edge plus an autopsy of every action and abstention | PARTIAL | Regret ledger runs daily (1,278 decisions). The edge got worse: revision_flow +9.27pp went to −1.61pp while its random twin was +3.88pp |
| S36 | 10-10 | 4 | X | ATLAS v3 / fresh Beta V1 portfolio / fix the cash-heavy prior-only plan / horizon weights | PARTIAL | ATLAS v3 was a 2pp tweak. Beta V1 was 10 names picked alphabetically with 70% cash. The H21 fit learned weight 0. The 23-stock plan was never adopted |
| S37 | 10-11 | 1 | X | RF/NR/Hack2 as Bloomberg baselines | NOT_DONE | Live gate refused; RF −1.61pp, NR −4.73pp |
| S38 | 10-11 | 2 | X | Investor brain: independent views on NKE/RBLX/ADBE/SONY/TTWO from business economics | PARTIAL | Backlog recorded (DONE as a record) and implementation deferred: DEFERRED_INDEPENDENT_INVESTMENT_REASONING_2026-10-11 |
| S39 | 10-12 | 2 | X | A new Human+AI portfolio from your views | NOT_DONE | None frozen after 09-27 |
| S40 | 10-07 | 1 | C | Social-media trading ideas turned into theory objects | PARTIAL | Cards only, no test |
| S41 | 10-14 | 2 | X | Analyst reports (UBS Okta, FFAI) reverse-engineered into a skill | PARTIAL | ~/.agents/skills/aegis-analyst-operating-bridge, used by hand only; FFAI not covered |
| S42 | 10-25 | 2 | X | News/political/fear tone before crises, and per-stock/customer tone, plus backtests | PARTIAL | Literature plus one FRBSF chart; "no backtest… performed" |
| S43 | 09-24 | 2 | C | Social cues; SanDisk/optics bottleneck | PARTIAL | Archetype refuted by dose-response; social sources score TOO_FEW |

### 1.2 Backtests, labs and the NN

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| B01 | 09-04 | 10+ | C | Unattended $0 night lab / weekend lab / overnight sims, all night | DONE in Sept, **now STALE** | night_factory had 27–30 receipts/night until 10-02, then 0–3 from **10-03** (before Codex). 11-02 and 11-07 empty |
| B02 | 09-10 | 1 | C | Fix night-sim maths and methodology (resume, costs, replay) | DONE | night_checkpoint.py, cost_curve.py (c673180a) |
| B03 | 09-07 | 1 | C | Mode B: autonomous agent backtest from 2000 with made-up news | PARTIAL | C1 curriculum hurt; R2 2015-24 rejected out of sample (9f1c65dd) |
| B04 | 09-08 | 6 | C | Continuous fiction / made-up-news backtests that **train** the NN | PARTIAL | fb_20260928 ran once (DeepSeek 44.6%); no training consumer |
| B05 | 09-11 | 2 | C | Infinite self-learning backtests | PARTIAL | Stopping rules and distillation exist; latest rules NO_SKILL; factory withered |
| B06 | 09-05 | 4 | C | NN lab that matures every night | DONE (infrastructure) | nn_lab nightly; nn in charge since 10-29; h5 rank IC +0.043, but top-k minus median −2.5%, and only 2 independent blocks |
| B07 | 09-25 | 1 | C | 100+ backtests, top 10 vs SPY, forward bridge | DONE | 312 rules; the bridge shows backtests failing forward (lib_mom_12_1 −11.11%) |
| B08 | 09-28 | 1 | C | Validate the "600% momentum" result | DONE | Died on CRSP (+0.10%/mo, t 0.33) |
| B09 | 09-19 | 2 | C | External platforms (LEAN/QuantConnect); stop the 5-name equal-weight construction | PARTIAL | vectorbt only; contest sheets still 5×20% |
| B10 | 09-05 | 1 | C | Why do simple paper lanes beat SPY while backtests fail? | PARTIAL | Answered as "it sat in cash", but conservative-atr is now +6.68pp over 99 sessions and was never re-answered |
| B11 | 10-10 | 1 | X | Reconcile and grade every output family, idempotently | PARTIAL | Manifest complete=false; grading runs daily |
| B12 | 10-11 | 1 | X | Six-month replay of RF/NR/blends with ablations | PARTIAL | Variants came out numerically identical |
| B13 | 10-11 | 1 | X | Benchmark engine vs firms, analysts and reality | PARTIAL | Descriptive doc only |
| B14 | 10-25 | 4 | X | Download WRDS and **use** it | PARTIAL | About 2.4M IBES rows pulled into recovery-evidence; 0 evaluations (C09) |
| B15 | 09-24 | 1 | C | Sim that produces forecasts and **learns** from them | **PARTIAL** (V) | Grading to 11-08 (70,007 rows); learning LEARN_DEGRADED in 76 of 77 runs |
| B16 | 09-23 | 1 | C | Plan step; fast and slow clocks | PARTIAL | u_plan exists; the fast clock is only u_review |
| B17 | 09-22 | 3 | C | 8/10/12-hour sims vs SPY | DONE | Ran, with 0 positions (EVALUATION_2026-09-23) |
| B18 | 09-21 | 1 | C | Closed-loop champion/challenger night | DONE | in_charge switches; ADWIN stopped 09-22 |
| B19 | 10-28 | 4 | X | Overnight research, backtests, branching, using all APIs | NOT_DONE | 0 commits touch TRIALS, NEGATIVE_RESULTS or strategy since 10-21 |

### 1.3 Paper accounts (Alpaca fleet and local books)

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| P01 | 09-04 | 1 | C | Stop same-day round trips; real holding periods | DONE | min_normal_hold_sessions (terminal repo) |
| P02 | 09-07 | 8+ | C | Keep all six Alpaca accounts **full, invested, using buying power, never empty** | PARTIAL → regressed | Fully invested once on 09-09 (c8cfe48b). Today hack1, hack2 and hack4 are 100% cash, hack3 returns 401, hack6 holds CALX **unprotected**, GRADES_MISMATCH on all 5 |
| P03 | 09-11 | 7 | C | "Thousands of paper accounts" as a data engine | PARTIAL | 72 strategy accounts plus 245 twins; POPULATION-1000 has 886 static books |
| P04 | 09-13 | 8 | C | Reset the fleet: six fresh $100K mandates for the best six (ATLAS, RF, NR, Hack2, Human+AI, news challenger), keep PC-PAPER | **NOT_DONE** | fleet_v3 PREPARED_NOT_SEEDED (0d6fa492). Same legacy fleet on 11-05. 0 terminal-repo commits since 10-06 |
| P05 | 09-13 | 1 | C | Deploy the fleet once the roadmap is done | NOT_DONE | 65f0d0d6: never deployed after 09-09 |
| P06 | 09-06 | 1 | C | Clock skew, stale NAV prices, hack4 decision | PARTIAL | Two of three done; stale NAV was measured, not fixed |
| P07 | 09-09 | 1 | C | Step-by-step for the hack4 flip | DONE | c96d146 |
| P08 | 09-04 | 1 | C | Plain-language explanation of open decisions | DONE | DECISIONS_2026-09-05 |
| P09 | 09-07 | 1 | C | Premarket runs (interpreted as "turn off") | DONE, intent missed | PREMARKET_PASSES_ENABLED=False; the "we keep losing features" complaint was never addressed |
| P10 | 09-13 | 1 | C | Give lane D an Alpaca account | NOT_DONE | hack2 now mirrors revision_flow |
| P11 | 09-19 | 1 | C | Review paper accounts vs S&P | DONE | results_voice daily (30+ files) |
| P12 | 09-20 | 1 | C | Fix Alpaca without asking; hack3 deleted | DONE | ACCOUNTS_2026-09-22 |
| P13 | 09-22 | 1 | C | Explain the good day | DONE | FINDINGS_2026-09-24 (win rate 27.7%, losses −7% vs gains +1.9%) |
| P14 | 09-23 | 1 | C | Position aging / thesis expiry | PARTIAL | Only in the terminal repo; not in pc_broker or the sim |
| P15 | 09-25 | 1 | C | 10 personal plus 10 Bloomberg local books | DONE | Frozen 09-25; 9 of 10 comp books negative |
| P16 | 09-28 | 1 | C | Local books checked daily, no Railway | DONE | leaderboard_2026-11-08 (329 books) |
| P17 | 09-29 | 1 | C | Act on hack5 now | DONE | 56509b7 |
| P18 | 09-29 | 1 | C | Rebalance the hack accounts daily on results and news | PARTIAL | Daily audit is read-only; only hack2 followed a book, and it went to cash on 11-02 |
| P19 | 10-06 | 4 | C | **No cheap SPY-heavy or cash-heavy books**; penalise abstention | NOT_DONE | PC-PAPER SPY $465k of $930k on 11-08 |
| P20 | 10-14 | 1 | X | Dynamic position management for the six mandates | NOT_DONE | Dynamic pair preregistered, unactivated and stranded |

### 1.4 Branching system

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| BR1 | 10-14 | 7 | X | Hundreds to thousands of diverse news-only and hybrid books that **branch, join, promote winners**, with RL/NN | PARTIAL | PR #53 (39f31f69): 886 books marked every 2h, median +0.21pp. news_only +3.40pp is about 51% cash (the cash control is +4.91pp). new_frozen_books=0 since 10-15, no descendants, no learned joins, activation NONE. Runtime grows about 0.5 GB/day inside recovery-evidence |

### 1.5 Universe

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| U01 | 09-11 | 1 | C | Analyse the whole market, not 56 names | DONE | e5af37b3 (3,056 scorecards) |
| U02 | 09-22 | 3 | C | Broaden the decision universe; WLS universe | PARTIAL | Funnel still 5,323→1,500 (sample)→25; WLS export empty |
| U03 | 10-06 | 1 | C | China and emerging markets | NOT_DONE | 23 non-US tickers, none .SS/.SZ/.HK; no book |
| U04 | 10-06 | 1 | C | Frozen vs vendor membership | DONE | membership_vintage.jsonl |
| U05 | 11-01 | 1 | X | Progress universe and merging work | PARTIAL | PRs #78/#79/#80; decision universe not expanded |
| U06 | 11-05 | 2 | X | Macro "stations" (Iran/oil, AI earnings, Asia, China AI bubble, crypto) that agents use; past events as context | PARTIAL | macro_stations_inactive.md; KNOWLEDGE/historical-events with no reader |
| U07 | 11-06 | 3 | X | Research desk with per-stock links, targets, watchlist, top 20, **universe neural map** | PARTIAL | RESEARCH_DESK_v2 delivered and liked; "neural" appears 0 times |

### 1.6 News digestion

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| N01 | 09-10 | **12+** | C | **News interpreted by cheap models into many forecasts that reach universe and portfolio decisions**: LLM-free pull plus separate analysis; Qwen interprets; "the engine does it itself"; "hundreds of news forecasts"; "why aren't we using the news we collect"; event→forecast→decision→warning; dynamic portfolios reacting (Meta/midterms/Iran) | **NOT_DONE** | Digest 0 typed rows since 10-15 (budget envelope). AegisWorldDigest Disabled 11-06. NEWS_TILT_IN_PLAN=False. E[r] marks news NOT_READ_BY_DESIGN. Funnel has no news input. Qwen only summarises logs |
| N02 | 09-04 | 7 | C | Use NVIDIA, Featherless and other providers | NOT_DONE | Featherless $0.0033, both responses rejected; NVIDIA timeout; 0 NVIDIA rows in routing |
| N03 | 09-04 | 1 | C | Daily news storage, trackers, adaptive candidate list, analyst vs ours, expectation vs reality | PARTIAL | potential_universe still 09-02; decision_vs_reality stops 10-02; yfinance ticker news 0 since 10-01 |
| N04 | 09-08 | 1 | C | E0 text-to-return panel plus FNSPID | PARTIAL | E0 alive (339k cells, appending 11-08); FNSPID has 0 code refs |
| N05 | 09-09 | 1 | C | Full historical news backfill plus catalyst calendar | PARTIAL | Calendar exists; no backfill; P6 replay REFUSED |
| N06 | 09-11 | 1 | C | Whole-market news, Asia first (World Monitor, God's Eye) | **PARTIAL** (V) | Asia RSS alive; the **Yahoo leg has been 0 since 10-01**; GDELT is zero on 423 of 589 receipts |
| N07 | 09-18 | 1 | C | Type the 163k panel headlines with the local model | **NOT_DONE** (V) | Panel cursor last run 09-13 (DeepSeek, 12% subset) |
| N08 | 09-19 | 3 | C | Social/video pipeline with **transcripts** | NOT_DONE | 286 YouTube rows, 0 transcripts; stopped 10-02 |
| N09 | 09-24 | 1 | C | Fresh news and price-target tracking | DONE | analyst pulls to 11-08 |
| N10 | 09-25 | 1 | C | Grade each source empirically | DONE | 552 scorecard receipts; weights not applied |
| N11 | 09-26 | 1 | C | Digest WSJ/Barron's/MarketWatch and grade them | PARTIAL | Mostly TOO_FEW; reader down |
| N12 | 09-29 | 2 | C | Human-like general browsing; insider/politics reads | PARTIAL | Official collector stale since 11-05; nothing drives a book |
| N13 | 10-10 | 1 | X | Trace news to a paper plan with ablations | DONE (negative) | DECISION_TRACE / PAIRED_RESULTS: Brier 0.2718 vs 0.25 constant |
| N14 | 10-31 | 2 | X | Investigate the Meta selloff and learn from it | PARTIAL | Offline assessment off main (54b30c8b/4d6b7396) |
| N15 | 11-04 | 1 | X | Election results, news review and mapping | PARTIAL | Recovery-evidence docs; inactive |

### 1.7 Reader / OpenClaw / Telegram

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| R01 | 09-22 | **25+** | C | Reader **always on, fast, many tabs, survives reboot, auto-starts, never idle** | PARTIAL → **down now** | Worked 10-15 to about 11-04 (2.2–3.7k pages/day). Stopped 11-05 at the disk floor; now CONTROLLER_FAULT SOURCE_PREFLIGHT; supervisor rc 2. The live reader runs from a recovery-evidence folder |
| R02 | 09-22 | 10 | C | Chrome, MuratClaw profile only, never the main account, no banks | PARTIAL (banks DONE) | NEVER_HOSTS added; earlier profile slips |
| R03 | 09-20 | 1 | C | Open login pages for you | DONE | openclaw_login.py |
| R04 | 09-22 | 1 | C | Model updates preferences, not code | **PARTIAL** (V) | policy_state exists; updates stopped 10-18 |
| R05 | 09-22 | 1 | C | Use web ChatGPT/DeepSeek for free research | **NOT_DONE** (V) | Explicitly refused hosts (config.py:5512) |
| R06 | 10-12 | 2 | X | Make reader output reach decisions | **PARTIAL** (V) | Lineage PRs #76/#80/#81/#83 built, zero operational effect |
| R07 | 10-06 | 1 | C | Investor personality browsing the whole web | PARTIAL | Query planner; fixed 133-ticker seed |
| R08 | 10-06 | 1 | C | Sign up for emails and watchlists | NOT_DONE | — |
| R09 | 09-28 | 3 | C | OpenClaw bounded autonomy (logins, sign-ups, check-ins) with approval | NOT_DONE | — |
| R10 | 10-09 | 1 | X | Logs local; local model digests them | **PARTIAL** (V) | Status counts only; refused since 11-01 |
| R11 | 10-09 | 2 | X | Stop browser cycling | DONE | READER_CHROME_RECYCLE_S=0 |
| R12 | 10-14 | 1 | X | Root-cause the reader breakage after the handoff | DONE | 10-15 restore (Codex wrappers vs the lock); broke again 11-05 |
| R13 | 09-26 | 1 | C | Paste inbox / reading list | DONE | READING_LIST_2026-09-28 |
| R14 | 09-25 | 1 | C | Per-stock research cards | PARTIAL | Stopped 09-29 |
| R15 | 09-22 | 1 | C | Telegram daily briefing and alerts, drop WhatsApp | DONE | 37 daily, 104 alerts; heartbeat 11-08 |
| R16 | 09-22 | 5 | C | **Two-way Telegram**: you ask, the agent researches or executes | PARTIAL (not working) | 2,881 "conversation held (Refused)" lines; last owner message 10-31; executor frozen |
| R17 | 10-11 | 1 | X | Pause reader and Qwen for the night | DONE | BETA_RESTORATION_2026-10-12 |
| R18 | 09-22 | 1 | C | Use Reddit | SUPERSEDED | You judged Reddit bad |

### 1.8 Infra, desktop and APIs

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| I01 | 09-10 | 8 | C | One-click EXE: local only, llama stop, guide once, no popups, opens, read-only Ask, one instance, start/stop sim | DONE | 79acc3ac…3f0dcd46 |
| I02 | 09-11 | 3 | C | EXE: NN showcase, OpenClaw option, reader on/off, friendlier after beta | PARTIAL / NOT_DONE | No NN or OpenClaw on /desktop; R147 is a roadmap entry only; no desktop commits since 09-26 |
| I03 | 09-04 | 3 | C | Fast suite; Labor Day attack; API checks | DONE | Last connection_check 09-07 |
| I04 | 09-07 | 2 | C | Free local model; prefer local over paid | DONE | Qwen 7B (now not running) |
| I05 | 09-10 | 2 | C | Evaluate a larger Qwen | PARTIAL | Speed measured, decision quality never |
| I06 | 09-13 | 2 | C | Always-on lab whenever the PC is on | **NOT_DONE (regressed by an agent)** [corrected] | Owner asked for a 30-min pause 09-27; marker written 10-02 made it permanent |
| I07 | 09-20 | 5 | C | Railway ≤ $20/month | PARTIAL | Loops retired 09-29; **no bill measured since September** |
| I08 | 09-20 | 2 | C | One .env; which one is main | PARTIAL / answered | aegis-finance/.env is main; aegis-alpha-terminal/.env is still live for the hack keys |
| I09 | 09-20 | 2 | C | No paid tokens overnight | PARTIAL | always_on_lab spent about $2.6/day until 10-02 |
| I10 | 09-22 | 1 | C | PC as a live market node | DONE | pc_broker, PC-PAPER |
| I11 | 09-26 | 3 | C | Health lights: frozen means red ("reactor panel") | **PARTIAL** (V) | Lights did go red (digest RED 10-15→10-26), but nothing acted on them; panel 28 STALE, exit 1; reader GREEN with 0 instances |
| I12 | 09-28 | 1 | C | Use the NPU and both GPUs | UNKNOWN | — |
| I13 | 10-15 | 3 | X | Remove the RAM guard and "old hard limits that fail the project" | PARTIAL / NOT_DONE | One 6 GiB gate removed; budget envelope and live-gate refusals added |
| I14 | 10-15 | 2 | X | Unattended until 10-21; auto-restart after reboot | PARTIAL | Reader ran; digest, new books and branches did not |
| I15 | 10-25 | 1 | X | Railway fix plus key rotation | PARTIAL | DeepSeek rotated; FRED/Finnhub/FMP/Alpaca not; prod 57 commits behind |
| I16 | 10-08 | 3 | X | Codex hooks and config warnings; reusable PC-control tool | DONE | Hook disabled, not fixed |
| I17 | 09-21 | 5 | C | Free RAM/VRAM on request | UNKNOWN | Operational |

### 1.9 GitHub

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| G01 | 09-06 | 2 | C | Fix red CI | DONE | 7efec7f0, 16af8efe |
| G02 | 09-26 | 2 | C | All paper ROI on site and GitHub; weekly asset refresh | PARTIAL | Asset refreshes stop 10-10/10-13; daily PNGs unpublished |
| G03 | 10-25 | **5** | X | GitHub usage block: why, fix, pay, new account? | DONE as of 11-09 (fragile) | Cause: Actions minutes on a private repo (83.8% burned 10-07..10-15 by Codex PR churn). Repo is public again with an All-Rights-Reserved licence (cd0b1d59) |
| G04 | 10-09 | 2 | X | Branch cleanup; one roadmap, fewer worktrees | NOT_DONE (reversed) | Branches 11→71 remote; 121 worktrees |
| G05 | 11-08 | 1 | C | Reconcile local vs GitHub; fix push conflicts | NOT_DONE | See §7 |
| G06 | 10-07 | 2 | C | Cloud Claude brief; PR #45 inspection | DONE | PR #11; PRs #49-#53 |
| G07 | 10-18 | 1 | X | Public showcase repo and sites | DONE | AEGIS-FINANCE-SHOWCASE etc.; you said "I love this" |

### 1.10 Optimus / MCP / process

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| O01 | 09-04 | 1 | C | Improve the Optimus MCP | DONE (small) | b0c0330 |
| O02 | 10-07 | 4 | C | Optimus knows you (voice, style) and serves every client; ingests ChatGPT history; stops forgetting | PARTIAL | Codex MCP wired; ChatGPT import script but no project; context mismatches 10-18 and 10-20 |
| O03 | 10-18 | 2 | X | Shared research tool and skill; Codex toolchain | DONE | optimus-research MCP; CODEX_TOOLCHAIN (untracked) |
| PR1 | 09-04 | 10 | C | Review, validate, launch agents; Opus builds, Sonnet researches, adversarial reviewer | DONE then SUPERSEDED | Chunks 1-27; the Codex switch replaced the process |
| PR2 | 09-07 | 4 | C | **"Things get lost"; save goals so agents don't drift; one roadmap** | PARTIAL | INDEX tiers exist, but TIER 1 still points at the expired 10-11 sprint; the Beta V2 registry is unmerged; the 11-06 roadmap is in Downloads |
| PR3 | 10-07 | 5 | C | Token economy; "2 weeks of tokens in 2 days"; stop wasting credits | NOT_DONE | 121 worktrees, about 200 review folders |
| PR4 | 10-09 | 9 | X | Finish V1/V1.1 Beta "before Monday" | PARTIAL | Never accepted (NOT READY) |
| PR5 | 10-24 | 1 | X | Save reviews, one roadmap, chunk it, agents build | PARTIAL | Registry has 146 requests, **0 done**; on an unmerged branch with 17 unpushed commits |
| PR6 | 10-26 | 2 | X | Sol builds / Astra plans / Atlas reviews | DONE | Ran; mostly infra output |
| PR7 | 10-31 | 4 | X | "Worried we haven't done much"; report in chat | NOT_DONE | No research followed |
| PR8 | 11-01 | 2 | X | **Stop rebuilding from the ground up; restore what worked** | NOT_DONE | Reader rebuilt r1-r4 on 11-06; duplicate commits |
| PR9 | 10-20 | 1 | X | Fix the context-mismatch workflow | NOT_DONE | — |
| PR10 | 09-13 | 2 | C | "Do the owner tasks yourself / step by step"; status of the 14 shells | UNKNOWN | Owner-only items (WLS) lingered |

### 1.11 Contest (Bloomberg)

| ID | First | ×n | Era | Ask | Final status | Evidence |
|---|---|---|---|---|---|---|
| C01 | 09-22 | 6 | C | A next-month winner ranker; top 10 / +50% (10% name cap) | **PARTIAL** (V) for the ranker, NOT_DONE for the goal | 108 sheets ("zero-skill lottery"); rehearsal −0.8% to −3.9% vs ACWI; **`contest/live/runs.jsonl` 28 runs: 26 REFUSED, 2 no sheet [corrected]** |
| C02 | 10-10 | 3 | X | WLS MEMB/TMSG explained and used ("use the doc I just got", 10-13) | PARTIAL | You supplied wlsemb.pdf 10-13; **`contest/wls/` is still empty**. This is a one-file fix nobody made |

### 1.12 Docs, storage, personal, other

| ID | First | ×n | Era | Ask | Final status |
|---|---|---|---|---|---|
| D01 | 09-09 | 12+ | C/X | Handoffs, roadmaps, session summaries, ratings out of 100 (09-09, 09-11, 09-24, 09-28, 10-02, 10-09, 11-01, 11-06, 11-08) | DONE (too many of them) |
| D02 | 09-19 | 1 | C | Learn from Coursera finance/decision theory | NOT_DONE |
| D03 | 09-20 | 2 | C | Interdisciplinary project/paper search | PARTIAL (docs) |
| D04 | 09-25 | 1 | C | Differentiation and hackathon pitch | DONE |
| D05 | 10-06 | 1 | C | Stock lists as a website, not PDF | PARTIAL (you switched to PDF) |
| D06 | 10-07 | 2 | C | Optimus graph fix; design library | DONE |
| D07 | 10-11 | 1 | X | Money results first | DONE |
| D08 | 10-12 | 2 | X | Post-migration review, SVGs, printable PDFs | DONE |
| D09 | 10-25 | 1 | X | Paper-worthy findings | **DONE** (V), answer "none", outside the repo |
| D10 | 10-25 | 1 | X | Competitor analysis | **PARTIAL** (V), five-row table, outside the repo |
| D11 | 10-25 | 1 | X | Where you are factually wrong | **DONE** (V), FINDINGS_AND_COMPETITORS §Assumptions, outside the repo |
| D12 | 10-25 | 2 | X | Blackline handbook; your design language | DONE (approved 10-27) |
| D13 | 10-26 | 1 | X | Absorb AEGIS REVIEWS.txt | PARTIAL (mapping is not delivery; 138/146 unverified) |
| D14 | 10-27 | 1 | X | Research questions for an external chat | DONE |
| D15 | 11-04 | 1 | X | Seven notes (diagrams, BMC, word2vec, Optimus as RAG) | PARTIAL (docs only) |
| ST1 | 09-27 | 4 | C/X | Free disk (09-27, 10-15, 11-05) | DONE ×2, root cause (worktrees) unfixed |
| ST2 | 10-13 | 2 | X | Organise AEGIS_DOCUMENTS; archive Downloads | DONE |
| ST3 | 10-15 | 1 | X | SSD backup | ABANDONED (drive beeped) |
| ST4 | 11-08 | 1 | C | Move unneeded data to the NordLocker vault | NOT_DONE (see §6; the vault is itself on C:) |
| ST5 | 10-11 | 1 | X | Reusable event/feature/outcome artifacts | UNKNOWN |
| PM1 | 09-07 | 2 | C | Aegis as **your** investing tool; personal mode | PARTIAL (personal mode DONE; murat_book −8.62pp, pc_paper −2.06pp) |
| PM2 | 09-25 | 2 | C | Personal six-month book | PARTIAL (murat_core_satellite +4.94pp; no ongoing check) |
| PM3 | 09-25 | 1 | C | Pre-market review with a patience rule | PARTIAL (paper only) |
| PM4 | 09-25 | 2 | C | Stock-list PDFs v1/v3 | DONE |
| PM5 | 11-06 | 3 | X | Personal market-re-entry and six-month plan reports | DONE (author opinion, not engine output; kept outside the repo) |
| OT1 | 09-19 | 2 | C | Personal mode; Telegram alerts on good signals | DONE |
| OT2 | 10-06 | 2 | C | Funding routes (CUPP, HKSTP, Cyberport…) | DONE (no new application found) |
| OT3 | 09-11 | 2 | C | Headline Arena: evaluate, then remove | SUPERSEDED / DONE |
| OT4 | 10-13 | 1 | X | Ingest UBS Okta, wlsemb.pdf, FA xlsx | PARTIAL |


### 1.13a Asks the first pass missed **[corrected: added by the completeness critic]**

| Ask | First | Status |
|---|---|---|
| The 59-row owner matrix in `ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md` (last Claude TIER 1): ASK-07 BLPAPI bridge, ASK-09 lawfully-public info, ASK-12 52-week/range features, ASK-13 MC+LLM+analyst blend, ASK-22 LLM regime calls, ASK-23 2027/2030 scenarios, ASK-26 too many momentum variants, ASK-28 snowball/broker identity, ASK-29 USAspending FY-end, ASK-30 FINRA short volume, ASK-31 "AI drives the car", ASK-49 night sim live-invests, ASK-54 specific names (QUBT/KYTX/SLDP/SOC), **ASK-56 PC paper must be $1M, also show $40k** (the real question behind "PC-PAPER UNRECONCILED") | 10-06 | mostly NOT_DONE |
| Provisional decisions + owner-portfolio event-risk review before earnings/macro clusters ("an unavailable report is not a valid reason to stay silent") | 10-27, 11-03 | NOT_DONE |
| Review five Alpaca hackathon award projects (autobelay, Should-AI-Buy, killswitch, deflow options desk, prism) and adapt mechanisms | 10-11 | UNKNOWN |
| "Check mirror, I lost a lot... maybe sell" (MIRROR lane -32.9% since inception) | 11-06 | NOT_DONE |
| Per-stock tone and customer-review shift before a decline (Amazon example), tone-vs-market visuals | 10-26 | NOT_DONE |
| Set up the Consensus plugin; "AI-generated environments for LLMs" | 10-25 | NOT_DONE |
| **Shorting**: "we could have even shorted to make money" (also MU, 09-19) | 11-06 | NOT_DONE; no short/hedge leg exists |
| Book F calendar seasonality (+0.43%/mo, t about 3.12) "deserves forward testing" | 09-20 | lib_book_f_seasonality book exists, EARLY_EVIDENCE |
| Codex's own 11-06 open issues: all 25 investigator names outside PIT pricing inputs; Next 14 vs 16.2.1 doc drift | 11-06 | NOT_DONE |
| **Contest ends 2026-11-13** (`scripts/contest_calendar.py:66-67`). `wlsemb.pdf` (275 pages, about 10.4k members incl. TT/KP/TI listings) is at `Downloads/AEGIS_ARCHIVE_2026-10-26/files2/`; `load_wls_export()` reads only csv/xlsx, so it needs a PDF to CSV conversion, **not** a Terminal visit. The gate cites owner decision D1. | 10-13 | NOT_DONE, time-critical |

### 1.13 Said 2+ times, still not delivered

1. **News actually used in universe and portfolio decisions** (N01): 12+ times, 09-10 → 11-08. Dead since 10-15.
2. **Beat SPY / an engine that can make profits** (S01): 9+ times. No demonstrated edge.
3. **Six Alpaca accounts full, invested and productive / six fresh mandates** (P02, P04): 16+ times combined. Three of five live accounts are 100% cash.
4. **The engine decides and takes risk on probability** (S04): 6 times. 0 EXPLOIT and 0 SELL in 47 contracts.
5. **Reader always on, fast, many tabs, auto-start** (R01): 25+ times. Down right now.
6. **Thousands of branching, learning paper accounts** (P03, BR1): 14 times. 886 static books, no descendants.
7. **No SPY-heavy or cash-heavy "cheap" books** (P19): 4 times. PC-PAPER is about 50% SPY.
8. **Kill losers, promote winners, RL** (S06): 3 times. One manual sleeve.
9. **Bloomberg top 10 / live sheet** (C01, C02): 9 times. 28/28 refused because one PDF was never placed.
10. **Use NVIDIA, Featherless, DeepSeek** (N02): 7 times. Featherless $0.0033; DeepSeek self-blocked.
11. **Two-way Telegram / remote control** (R16, R09): 8 times. Refusing.
12. **Fiction / made-up-news backtests that train the NN** (B04): 6 times. Run once.
13. **Video transcripts** (N08): 3 times. 0 transcripts.
14. **Stop rebuilding from scratch; stop wasting credits; fewer worktrees; one roadmap** (PR2, PR3, PR8, G04): 13 times.
15. **Universe neural-map visual / NN showcase** (U07, I02): 4 times.
16. **Human+AI and independent investor-brain portfolios** (S38, S39): 4 times.
17. **Railway ≤ $20 verified** (I07): 5 times. No bill since September.
18. **Day-trading / constantly active book** (S12): 4 times.
19. **LinkedIn/hiring and AI-pivot** (S16): 3 times. One snapshot.
20. **Remove the hard limits that make the project fail** (I13): 3 times. More refusals were added.

---

## 2. Claude era vs Codex era

| | Claude (≈09-01 → 10-07, ~5.3 wk) | Codex (10-08 → 11-08, ~4.5 wk) |
|---|---|---|
| Non-merge commits on main | 797 | ~205 (≈27 are data-only receipts), plus 62 merges |
| Code and test lines added on main | ~542k (services 115.8k, scripts 175.7k, tests 191.7k; docs 132.7k) | ~60k (services 19.3k, scripts 11.3k, tests 28.4k; docs 7.7k) |
| Stranded off main | ≈0 | **141 commits / ~46.7k lines**; 83 of 187 codex/* refs unmerged; beta-v2 branch 37 commits (17 unpushed) |
| Trial files added | 24 | 6 (shadow, news capture, ASML measurement, POPULATION-1000 *unpowered*, plus a stranded exit5 pair) |
| Subjects about backtest/alpha/factor/ranker | 48 | **0** |
| Commits to xs_ranker, book_dna, investment_committee, llm_portfolio, night_factory, opportunity_funnel, engine | 3–7 each | **0** |
| Code mix | ~24% strategy/backtest research, ~10% news/reader | 29% news ingestion, 13% owner alerts/Telegram, 9% CI/ops, ~11% strategy-path files (mostly inactive Beta V1 shadow) |
| Self-labelled "offline / inactive / candidate / shadow" new modules | rare | **45 of 81** product files added |
| Roadmaps | 16 dated ROADMAP files 08-23 → 10-06 (one every ~3 days) | No new TIER 1 file; plans split across a 10-11 sprint, an unmerged registry, and HTML in Downloads |
| Reader/OpenClaw file touches | 65 | 18 on main plus 14 stranded |

**What the Claude era actually delivered**
- The honest benchmark fix.
- The $0 night factory with checkpoint/resume and replay detection.
- Local Qwen.
- The E0 text-return panel (still appending).
- The Asia RSS corpus.
- The desktop EXE.
- Price targets backtested on 390k IBES cells.
- Graded 14,703 forecasts (investigator +8.97% held out, later shown to be magnitude skill, not direction).
- The PC paper node.
- The Decision Contract.
- results_voice.
- The 312-rule library with a forward bridge.
- nn_lab.
- Telegram outbound.
- The V1 Beta (twins, Book DNA, regret ledger; 92f147f6, green gate with 13,693 tests).

On statistics it ran many real tests, and almost all were honestly negative: momentum died on CRSP, R2 was rejected out of sample, stop rules lose to holding, the fundamentals tilt was negative, and the fine-tuned LLM lost to TF-IDF. Every late commit carried "RESULT IMPROVEMENT: NONE". Execution and scale asks (fleet full, thousands of accounts, kill/promote) were mostly not met.

**What the Codex era actually delivered**
- Real but few statistics items, all from 10-10 to 10-12:
  - the decision-grader window erratum (`e737423b`);
  - source forecasts Brier 0.2718 vs 0.25 for a constant forecast;
  - H21 basket mean +0.64pt, median −4.88pt, 5 of 8 windows losing;
  - news H1/H5 forecasts worse than a constant.

  All null or negative. **[corrected]** The E[r] refit and nn_lab grading kept running daily; what stopped is that **no new experiment was designed after 10-12**.
- Operations:
  - reader restored on 10-15 and working for about 3 weeks;
  - POPULATION-1000 (886 books marked every 2h);
  - CI cost controls;
  - the Codex toolchain;
  - the hook fix.
- Presentation:
  - six printable PDFs;
  - the Blackline handbook (approved);
  - public showcases;
  - the AEGIS_DOCUMENTS index and Downloads archive;
  - the 11-06 personal reports you liked.
- **Harm it introduced:**
  - the untracked `provider_budget.py` envelope silently disabled the digest, IIF-1, hyp_lab and much of the learner for 24 days;
  - 121 worktrees, plus production tasks running out of `aegis-recovery-evidence`;
  - the CI-minute burn that triggered the GitHub block;
  - the reader breakage of 10-11 to 10-14 (its own wrappers fighting an exclusive lock).

**Verdict.** Your complaint is right about the Codex month. It went into guards, provenance, inventories (four in one month) and parallel "candidate" modules beside working systems. It produced no new strategy or statistics after 10-12, and while it worked, the one stage that mattered (news typing) was silently dead. But the absence of an edge is not Codex's doing. The Claude era tested a great deal and found nothing that survives, and it also wrote roadmaps faster than results. The real loss in October was **momentum**: the machine that ran tests every night (night factory, hyp_lab, IIF-1, learner) stopped running, and the month went into building scaffolding around it instead of restarting it.

---

## 3. Current system health (2026-11-08/09, US weekend)

| Subsystem | State | Evidence / note |
|---|---|---|
| results_voice / ROI / book_dna | **ALIVE** | 2026-11-08T011204Z; 18 of 72 ahead of SPY (13 distinct bets); every family's ROI negative |
| Decision contract (daily_pass) | **ALIVE** | 2026-11-07.json (97 rows: 4 BUY, 92 PROBE); 0 EXPLOIT; capital **UNRECONCILED** |
| Strategy library | **ALIVE** | Nightly to 11-05/06, same 312 rules; missed 11-07/08 |
| nn_lab | **ALIVE** (one session behind) | rc 0; bars stop 11-05; h5 IC +0.043, top-k −2.5%, 2 independent blocks |
| Analyst revision pull | **ALIVE** | 11-08, 404,945 rows |
| Arena forward grading | **ALIVE** | "25 past due" is a weekend false alarm; clears after Monday's slot |
| Funnel (local) | **ALIVE** | 11-05, 5,323→1,500 *sample*→25; rebuilt only at the 10-day limit |
| Funnel (prod / Railway) | **STALE** | 10-26, 13 days; "ic funnel unavailable" |
| Railway website backend | **ALIVE, DEGRADED** | Deploy 1d2319a8, 57 commits behind main |
| Vercel site | **STALE** | Last deploy about 27 days ago |
| GitHub CI | **ALIVE** | Green on cd0b1d59; public again, so minutes are free |
| PC-PAPER | **ALIVE** | $930–934k, 31 names, 99.6% invested, ~50% SPY, UNRECONCILED since about 10-06 |
| Alpaca fleet | **STALE / idle** | hack1, hack2, hack4 100% cash; hack3 HTTP 401; hack5 SPY; hack6 CALX **unstopped**; GRADES_MISMATCH ×5; FleetDailyCheck rc 1 |
| Revision-flow book (hack2) | **DEAD** | v2 horizon reached; exited to cash 11-02; no v3 frozen |
| News corpus collection | **PARTIAL** | Asia RSS alive; Yahoo ticker leg 0 since 10-01; GDELT mostly zero; reader folders 0 since 11-06; blackout 10-29/30 |
| World Digest (news typing) | **DEAD** | 0 typed rows since 10-15; task Disabled 11-06 |
| IIF-1 night trial | **DEAD** | VOID 13 nights since 10-16 |
| hyp_lab | **DEAD** | BUDGET_REFUSED since 10-16; ledger last 10-26 |
| Learner (learned rules / policy_state) | **DEAD** | 0 rules since 10-18; 76 of 77 LEARN_DEGRADED |
| Reputation | **STALE** | 10-27, so sim logs "policy_state IGNORED" on every cycle |
| Decision story (stories) | **STALE** | 10-28 (regret ledger itself ALIVE 11-08) |
| Reader / OpenClaw | **DEAD** | CONTROLLER_FAULT; supervisor rc 2; gateway up with 0 calls in 7 days |
| Telegram outbound | **ALIVE** | Daily brief and alerts |
| Telegram two-way | **DEAD** | "conversation held (Refused)", still growing |
| Owner event warnings | **ALIVE but does nothing** | 663 runs, 0 automatic sends (one manual, AAPL 11-03) |
| Sim (AegisSimOwner) | **STALE** | Last full session 11-05; session.json says RUNNING with dead PID 54448 (unclean reboot 11-07 13:56) |
| Night factory | **STALE** | 0–3 receipts per night since 10-03 |
| Predictions ledger | **ALIVE, mostly filler** | 79% of rows since 10-16 are review:v0 p=0.50 "UNFORECAST" placeholders; real producer is investigator:evidence_v3 (~270/day, to 11-05). **[corrected]** Also a rule-based stream since 09-29: `news_digest:insider_v0` 756, `positioning_v0` 510, `congress_v0` 122 rows; 837 graded, mean Brier 0.2522 / 0.2501 / 0.2461, about the 0.25 constant: measured, no skill |
| Contest live | **ALIVE but refusing** | `contest/wls/` empty |
| POPULATION-1000 grading | **ALIVE, static** | Runs from recovery-evidence; +0.13–0.58 GB/day, no retention |
| Official/SEC collector | **STALE** | 11-05; FINRA 101 of 101 failed |
| local_runtime_digest | **DEAD** | Refused since 11-01 |
| typed_events, social/YouTube, hiring, thesis cards, decision_vs_reality | **DEAD** | 10-02 / 10-02 / 09-13 / 09-29 / 10-02 |
| always_on_lab | **OFF** (30-min pause made permanent by an agent, see I06) | Marker 10-02; so llama-server is never up |
| Optimus brain refresh | **ALIVE** | 1,864 pages; does not ingest Codex memory; Claude memory frozen at S62 |
| Health panel | **ALIVE, uninformative** | 28 STALE, 2 DEAD, 16 UNKNOWN, exit 1; red lights trigger nothing |
| Machine | — | RAM 5.5/31.4 GB free; C: ~55–63 GB free (95%); no sim, lab or llama process running |

**P0s (in order)**
1. **Budget envelope.** `provider_budget.py` is untracked and its envelope was never initialised. It is the silent cause of the dead digest, IIF-1, hyp_lab and part of the learner, and every affected task reports rc 0. You need to decide one thing: initialise it with a cap, or remove the guard.
2. **The runtime is not a commit.** The live checkout is 255 commits behind main, has 51 modified and 37 untracked `.py` files, imports untracked modules, and lacks the grader fix. That means grades written locally since 10-10 are unverified.
3. **`predictions.jsonl` is 121.4 MB and rewritten in place.** A commit would be hard-rejected by GitHub. Any reset, checkout or stash would destroy rows.
4. **The news→decision path is dead**, and hack6's freshness check lied (`fresh: true` on empty digests).
5. **The reader is down.** It stopped at the disk floor, and then a source-pin hash mismatch kept it down.
6. **Risk hygiene.** hack6 CALX has no stop, GRADES_MISMATCH appears on every account, and PC-PAPER capital is UNRECONCILED.

**P1s**
- The prod funnel is stale (13 days).
- The sim shows RUNNING with a dead PID before Monday's window.
- Stranded Codex work (beta-v2, exit5) is at risk.
- 16 scheduled tasks run code from recovery-evidence folders.
- There is no TIER 1 roadmap in force.

---

## 4. News → universe → dynamic portfolio

**The pipeline as it is built today:**

```
collect (41 sources, ~1–2k rows/day)  ──►  type (DeepSeek, world_digest)  ✗ DEAD since 10-15 (budget envelope)
                                              │
            world_state (frozen: "ai_demand up 0.53")   SHADOW_NEWS_v0 (trust 0, max change 0.19%)
                                              │
universe/funnel ✗ no news input       E[r] ✗ NOT_READ_BY_DESIGN      plan tilt ✗ NEWS_TILT_IN_PLAN=False
                                              │                       (even on: cannot add names or change gross)
                       hack6 news sleeve (1%/name, long only) — 83 buys 09-29..10-15, then blind, "fresh:true"
                       owner warnings — 663 runs, 0 automatic sends
```

**Where it breaks:**
- Interpretation is dead.
- The universe never sees news.
- The single consumer that trades on news is long-only, sized at 1% per name, and cannot reduce risk.
- No decision row records which digest or implication caused it.

As built, the system cannot make the kind of call you made: market-level de-risking around an event.

**The smallest changes that would close the gap (in order):**
1. **Turn typing back on.** You decide: initialise the envelope with a cap (the digest already caps itself at $0.90 per run, about $3/day), or exempt world_digest from it. Re-enable AegisWorldDigest. Acceptance: the next run writes typed rows > 0.
2. **Check content, not file age.** Mark a digest DEGRADED when typed rows or `n_implications` are 0 for 2 runs, and make `fleet_manager_run` treat `n_implications==0` as stale. That is one condition in each of two places.
3. **Provenance.** Write `digest_id` and the implication ids/d/s values on every hack6 decision row. Then grade the 83 historical news buys against matched non-news names at 5 sessions. The data already exists.
4. **News as a funnel candidate source.** Append issuer-mapped `top_tickers` from fresh themes to the funnel's candidate list (tagged `source='news'`). Print the news share of the final 25. This only adds names; ranking and gates are unchanged.
5. **A news risk overlay book** (PRODUCT_EXPERIMENT). Typed themes (AI-capex stress, Iran/oil escalation, election shock) produce a gross-exposure scalar of 0.5–1.0, applied to a copy of an existing book (hack5 SPY or the PC-PAPER plan) and graded daily against the untilted copy. Freeze the contract before the first decision. This is the only route by which your Meta/Iran/midterm calls could ever act.
6. **Register precursor cases on the existing corpus:**
   - Do "mega-cap raises capex / AI-spend stress" headlines precede 3–5-session QQQ/semis drawdowns, compared with matched earnings weeks?
   - Do Iran-escalation headlines precede moves in Brent and QQQ over about 2 months?

   Both are measurements to run, not claims. Your rule holds: lessons feed the universe as context, and backtests stay out of sample.

**What the Meta / midterms / Iran conversations show**
- **The precursors were in the raw corpus, and the system was structurally unable to use them.** Examples:
  - Oct 21: "Meta raises spending forecast… AI spending spree reviving a financial-crisis playbook".
  - Oct 22: "Global stocks fall… Meta dents tech optimism".
  - Oct 27: "Meta $27B data-center bond slumping".
  - Iran headlines ran at 10–22 a day and midterm headlines at 8–15 a day.

  Over Oct 27→30, QQQ fell 4.26% and SPY 1.81%. At that time world_state still read "ai_demand up" because typing was dead.
- **Your instinct was right in this one case.** That is one observation, not a validated edge. The ChatGPT review (10-27) said both "AEGIS should already have warned you" and that broad shorting "is not supported by a demonstrated edge". Both statements are true.
- **Each conversation ended as a document rather than a mechanism:**
  - Meta: a saved case (offline, off main).
  - Iran/midterms: an inactive station map; the protocol stayed in draft over 4 registration gaps.
  - Re-entry: a report written by hand from web sources. Codex admitted the forecast packet "does not pass the election, Iran or crypto articles".
- **The lesson for the roadmap:** your hypotheses need a typed, pre-registered path (thesis → falsifier → grading date → a book that can change gross). Without it, every "I called it" stays an anecdote. The next test is the cluster around NVDA earnings in mid/late November.

---

## 5. Infra

### 5.1 GitHub: cause and fix
- **Cause.** The block was Actions minutes, not LFS and not repo size. The repo was made private around 10-11/12. October used about 4,000 minutes, 88% of it the backend pytest job (about 21 minutes per run), and **83.8% of the minutes fell on 10-07..10-15**, mostly the Codex PR storm (10-07 itself was a Claude day) **[corrected]** (128 runs, 75 of them PRs). Once the free 2,000 was gone, jobs failed at 0 seconds from 10-25 to 10-31. November is running at about 6,500 minutes a month.
- **Current state.** The repo is **public** again, with an All-Rights-Reserved licence (cd0b1d59). Billable minutes are 0 and CI is green.
- **Recommendation:**
  - Keep the repo public. A new account does **not** help: a private repo there gets the same 2,000 minutes and would run out in about 9 days.
  - If it ever goes private again: run backend pytest only on merge to main, skip docs/receipt-only PRs (the classifier already exists), and batch PRs.
  - Do **not** add a self-hosted runner while the repo is public. A fork PR could then run code on a machine that holds every key.
  - Fix the 100 MB time bomb (`predictions.jsonl`) and stop committing runtime data (see §7).
  - Update CLAUDE.md and GITHUB_USAGE_2026-10-27.md, which disagree about visibility.

### 5.2 APIs (names only)

| Provider | Status | Note |
|---|---|---|
| DeepSeek | **Paid, self-blocked** | About $33.84 unused; digest, hyp_lab and IIF-1 refused by the envelope; investigator:evidence_v3 still called it until 11-05/06 (it bypasses the envelope) |
| FRED | **Used** | Website: 23 series, last fetch 11-07; whether it reaches PC decisions is unverified |
| Finnhub, FMP | Used | Funnel universe (Finnhub); keys exposed 10-21 and **not rotated** |
| Alpaca (main, ARENA, LANE_D, KEY_2; AAT_HACK1-6 in the terminal .env) | Partly used | hack3 401 is explained **[corrected]**: owner 10-26 "hack3 has been reseted and the key has been transferred to pc paper", and offered to sign in and put fresh keys for all six accounts into `.env`; the agent never took that up. `pc_broker.py:97` accepts `PC-PAPER_key`, which is present. KEY_2 has 0 code refs; HACK keys tied to Railway loops retired 09-29; ALPACA_PC_KEY_ID absent |
| yfinance | Used | Revisions alive; ticker-news leg 0 since 10-01 |
| NVIDIA NIM | **Unused** | Bakeoff 09-26; timed out 11-06 |
| Featherless (about $70) | **Unused** | $0.0033 spent; both responses rejected |
| OpenAI (GTP_TOKEN, AAT_OPENAI) | Unused | Contradicts CLAUDE.md's "DeepSeek is the only provider"; CLAUDE.md needs updating |
| HF_TOKEN | Labs | Local models (FinBERT, Kronos, bge) |
| Polygon, AlphaVantage, EODHD | Idle | connection_check only (last 09-07) |
| YouTube | Idle since 10-02 | 0 transcripts |
| Telegram | Used | Outbound only |
| WRDS | Paid via HKU | 58.6 GB on disk; 43.8 GB never referenced by code |
| Railway | Paid | Pro $20 plus usage; **no bill measured since September** (last $48.05 usage for 08-26..09-20); retired hack volumes still kept |
| Vercel | Free tier | 6 projects; the Aegis site is stale |

### 5.3 MCP / plugins / skills: Claude vs Codex

| | Claude | Codex |
|---|---|---|
| Optimus MCP | yes | yes, plus **optimus-research** (17 tools) |
| GitHub | plugin **broken**: `GITHUB_PERSONAL_ACCESS_TOKEN` unset → "Bearer " → 400; gh CLI works | gh-CLI bridge MCP (works) |
| Railway | none | railway MCP (plugin unauthorised; CLI works) |
| Playwright, context7 | yes | yes |
| exa | yes | — |
| OpenAI docs; document/pdf/spreadsheet/presentation plugins | — | yes |
| Skills | 6 project + 3 user (Aug–Sep era) | `.agents/skills` (9) + user skills (analyst bridge, murat-visual-language, project-pc-control, optimus-research); 245 skills disabled to fit the context budget |

**Gaps to close:**
- Fix Claude's GitHub MCP. Either set the PAT with `setx` without printing it, or drop the plugin and use the gh CLI.
- Optionally add railway and optimus-research to Claude's `.mcp.json`.
- Port the Codex user skills that encode your voice and design (murat-visual-language, analyst bridge) into a shared location both agents read.

### 5.4 Optimus state
- 1,864 pages, refreshed daily (last 11-08 00:17Z).
- It ingests Codex-era **repo docs**, but **not** `~/.codex/memories` (725 KB) or the Codex sessions (1.1 GB).
- Claude memory stops at S62 (10-06), so `session_briefing` describes a world from early October.
- Its health page reads the stale WIP HEAD.
- Fix: add the Codex memory and handoff folders as sources in `tools/refresh_aegis.py`, and report origin/main's HEAD instead of the WIP checkout.

---

## 6. Storage (C: 953 GB, ~55–63 GB free, 95% used; no D: attached)

### 6.1 Ranked reclaim plan

| # | Item | GB | Safety class | Action |
|---|---|---|---|---|
| 1 | 50 PRUNE_SAFE worktrees (clean, 0 local-only commits, unscheduled) | ~60 | **SAFE** | `git worktree remove <path>` one at a time, never `--force`; then `git worktree prune` |
| 2 | NVIDIA DXCache | 18.2 | REGENERABLE | Disk Cleanup → DirectX Shader Cache |
| 3 | pip/npm/uv/playwright/puppeteer/codex-runtimes caches plus Temp | ~13 | REGENERABLE | `pip cache purge`, `npm cache clean --force`, `uv cache clean` |
| 4 | Stray clone `aegis-worktrees\frontend-font-ci-20261104` | 2.8 | REGENERABLE | Delete (clean, at merged PR #68) |
| — | **Subtotal, no risk** | **~94–98** | | Free space goes from about 56 to about 150 GB |
| 5 | 48 PRUNE_OK_BRANCH_KEPT worktrees | ~62 | SAFE after bundling | `git bundle create aegis-local-branches-20261109.bundle --branches` → `git bundle verify` → store in the vault → remove the worktrees (branch refs stay) |
| 6 | NordLocker folder `NordLocker_11273162` ("blend projelerim" 59.8, "game" 10.5) | 70.3 | YOUR CALL | All 8,808 files are stored locally. Confirm the upload finished, then "Free up space" (online-only). **Moving files into this folder frees nothing until they are set to online-only.** |
| 7 | Docker `docker_data.vhdx` (unused since 09-10) | 65.3 | REGENERABLE (check named volumes) | Docker Desktop "Clean / Purge data", or uninstall; Railway does not need it |
| 8 | WRDS bulk: 821 unreferenced files | 43.8 | ARCHIVE (licence check first) | grep for f-string/glob paths → move to the vault → set online-only; keep the 36 referenced files (3.7 GB) |
| 9 | Qwen3-30B GGUF | 18.6 | ARCHIVE (can be re-downloaded) | Keep the 7B (4.7 GB, live) |
| 10 | Aegis module/data (newest file 08-17) | 15.7 | ARCHIVE | Same licence caveat for wrds_raw |
| 11 | Extra repo venvs (.venv_kronos, ft_lab, nn_lab) | 13.9 | REGENERABLE | Rebuild when needed |
| 12 | 18 REVIEW_DIRTY + 3 TAG_FIRST worktrees | ~25 | REVIEW FIRST | Tag the detached commits first (below); review each dirty one |
| 13 | Non-Aegis (anaconda3 10.3, SOLIDWORKS 17.9, games ~22, Downloads installers ~2) | ~50 | YOUR CALL | — |
| 14 | hiberfil 12.6 / restore points ~70 (unmeasured) | — | ADMIN | `vssadmin list shadowstorage`; `powercfg /h off` only if nights don't rely on hibernate |
| ✗ | `aegis-recovery-evidence` as a whole (42.5 GB) | — | **DO NOT MOVE** | 5 live tasks run from it (reader-carry-runtime-r7, oct15-sec-cursor-runtime-r6, t04-monitor-runtime-r6, beta-v2 continuation-20261103, branching-population-1000-r1 runtime +0.5 GB/day). Add retention to the branching snapshots first |

**Root cause of the sprawl:** the repo tracks **1.64 GB of data**, so every worktree is a full 1.5 GB copy. Stop tracking runtime data (§7). Use sparse worktrees. Remove a worktree when its PR merges.

### 6.2 Worktree prune list (from `wt_classified.tsv`)

**KEEP (live):** `aegis-finance` (runtime), `aegis-finance-publication` (on `main`; AegisPublicAssetsWeekly / AegisDataCatalog run from it).

**PRUNE_SAFE (50):** aegis-central-replay-lineage-20261105, aegis-ci-cost-sidecar, aegis-docs-source-main, aegis-event-path-integrated, aegis-finance-assets, aegis-finance-beta-audit-memory, aegis-finance-beta-audit-producer, aegis-finance-beta-news-provenance, aegis-finance-beta-reader-continuity, aegis-finance-fleet-recovery, aegis-finance-followthrough, aegis-finance-night-public, aegis-finance-night-relationship, aegis-finance-night-transport, aegis-finance-oct15-hold, aegis-finance-oct15-sec, aegis-finance-overnight, aegis-finance-pr19-ci-repair, aegis-finance-recovery, aegis-finance/.claude/worktrees/ecstatic-chaplygin-58eb88, aegis-finance/.claude/worktrees/objective-curie-5a7bf1, aegis-funnel-sync-integrated, aegis-funnel-transfer-candidate, aegis-ic-funnel-builder, aegis-iif1-frozen, aegis-integration-sparse-20261104, aegis-oct14-forecast-model-refusal, aegis-oct14-hosted-evidence, aegis-oct14-news-boundary, aegis-oct14-openclaw-profiles-pr, aegis-owner-warning-runner, aegis-pre-event-integrated, aegis-recovery-evidence/{e3-owner-decision-view-20261105, historical-universe-lessons-20261105, news-universe-map-build-20261105, provisional-exposure-review-e2-20261105, sec-identity-map-build-20261105}, aegis-telegram-admission-20261104, aegis-universe-diff-20261105, aegis-worktrees/{ci-operations-20261101, ci-usage-20261029, docs-source-reviewed-20261106, e4-rss-followup-20261105, earnings-json-source-20261101, earnings-source-20261101, news-stations-20261106, owner-warning-exit-truth-20261104, provider-budget-port-20261103, reader-source-20261101, world-digest-subject-e1-20261105}.
*(Before removing, confirm no scheduled task's path points into the `aegis-recovery-evidence/*` entries. The storage reader found none.)*

**PRUNE_OK_BRANCH_KEPT (48; bundle first):** all `aegis-finance-*` 2026-10-09/10 branches (pc-guard 19 local commits, pc-release 18, news-p4-repair 12, decision-grader-integrated 12, news-p4 11, news-p3 10, news-cascade(-fix), fleet-*, sweep-monitor-*, r15-catalyst-*, pc-epoch-*, openclaw-persistent/quiet, learning-parser, evidence-audit, audit-ledger, assets-image, public-assets-fix, hack4-effective, news-pilot), plus the 11-04/06 candidates (owner-lineage-caller, owner-warning-frozen, pre-event-input/warning, saved-event-lineage, saved-sec-input, clocked-pc-paper, e6-provisional-owner, news-owner-edge-trace, news-sec-atom-station, news-station-rss, owner-source-gate-legacy, e4-multigroup-owner-bridge), **and `branching-dynamic-pair-canonical-r1/repo-wt` (codex/oct15-dynamic-exit5-prereg, the only Codex strategy pre-registration; do not lose it).**

**TAG_FIRST (3):** `git branch keep/a60f27c6 a60f27c6` (local-branching repo-wt, 6 commits), `git branch keep/35e7d747 35e7d747` (publication-clean-gate and -clone).

**REVIEW_DIRTY (18), important ones:** `aegis-worktrees/beta-v2-owner-20261025` (37 ahead, **17 unpushed**, 12 modified, 15 untracked: the whole Beta V2 registry), `aegis-oct14-current-results` (10 modified/26 untracked), `world-digest-fail-loud-20261103` (possibly relevant to the digest fix), `funnel-sync-once-candidate`, plus 14 small ones (1–9 files each).

---

## 7. Local vs GitHub reconciliation (non-destructive)

Facts:
- The live checkout is 8 ahead and 255 behind. Its 8 local commits contain **no unique code**, only Oct 7–9 data and regenerated docs.
- There are 4,423 dirty paths (862 MB):
  - 4,104 untracked data files, 615 MB;
  - 42 tracked growing data files, 181 MB;
  - 53 tracked and 45 untracked code files.
- About **57 code/doc files exist in no commit anywhere**, and the runtime imports some of them.
- The merge is clean at commit level (merge-tree rc 0). In the working tree it would abort on 84 paths: 51 already equal the merged result, and **33 are real conflicts**.
- `predictions.jsonl`: 121.4 MB, 70,007 ids (no losses), 11,121 lines rewritten in place.

Steps:
0. **Prep (read-only).** `git fetch`; re-run the classification scripts; pick a quiet window outside US hours and outside the IIF window. List every task whose working directory is `aegis-finance` and **record PIDs** (never kill by image name). Check free disk first, and do §6 step 1 before this.
1. **Backup outside git.** robocopy the 4,423 dirty paths to a dated folder outside the repo, with a SHA-256 manifest. **No stash, reset, checkout -- or clean.**
2. **Code snapshot without touching the index.** Using a temporary `GIT_INDEX_FILE`: `read-tree HEAD`, add only the ~153 code/doc paths, `write-tree` + `commit-tree -p HEAD`, then create the local branch `snapshot/main-checkout-code-20261109`. Never push it, and never include data in it.
3. **Rescue branch.** Make a fresh worktree `rescue/main-checkout-20261109` from origin/main.
   - Bring in the 56 files that are not on origin, especially the ones the runtime imports: native_admission, the 5 beta_v2_* modules, frozen_constituent_prices, earnings_deadline, retry_failed_digest_items.
   - For the 33 conflicts, use `git merge-file`. Where 90% or more of a file's added lines are already on origin, take origin's version (task_receipts, reader_pool, web_reader, world_digest, provider_budget, llm_telemetry).
   - Review each truly unique hunk by hand: decision_contract provisional_contracts, daily_pass, llm_analyzer budget wrapper, task_keeper, telegram_agent, opportunities_build, pull_bars_refresh, news_pull, config `READER_CHROME_RECYCLE_S=0.0`.
   - Run targeted tests, open a PR, then `python -m scripts.ci_watch --wait`.
4. **Data out of git, on a branch (no history rewrite).**
   - Add ignore rules for: strategy_library checkpoints, review/, straddle_forward/, pc_book/20*/, official robots and requests, sim/, contest/rehearsal per-day folders, decision_story/*.jsonl, predictions.jsonl, snowball_shadow, decisions/ledger.jsonl.
   - Run `git rm --cached` on the tracked ones. The files stay on disk.
   - Commit a manifest (path, sha256, rows, last stamp).
5. **Structural.** Point `AEGIS_DATA_DIR` outside the repo (for example `C:\Users\mrthn\aegis-data\optimus`). Run production from a dedicated **runtime worktree pinned to a reviewed tag**, not the dev checkout.
6. **Switch production (attended, quiet window).**
   - Disable the listed tasks by name and stop telegram_agent by its recorded PID.
   - Copy the data directory and verify the hashes.
   - Repoint the task working directories to the runtime worktree, and move the ~16 recovery-evidence tasks into versioned scripts or retire them.
   - Re-enable the tasks, then verify that receipts, broker reconciliation and outputs advance, not just that PIDs exist.
7. **Beta V2 and exit5 branches.** Push `codex/beta-v2-owner-20261025` (17 unpushed commits) and `codex/oct15-dynamic-exit5-prereg`, then either review and merge them or retire them on the record.
8. **`wip/2026-10-07-day`.** Keep it as an archive ref; don't push its data commits.
9. **Your decision, separately:** filter-repo to drop about 1.5 GB of historical data blobs. That needs a force-push and is destructive, so decide it alone.
10. **Then** prune worktrees (§6) and the branches confirmed by `git branch --merged origin/main`.

---

---

The roadmap that acts on this audit is `ROADMAP_2026-11-09_RESTORE_THEN_COMPOUND.md` (TIER 1).
