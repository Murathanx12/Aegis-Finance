# ROADMAP 2026-10-06 — V1 BETA: THE LOOP THAT LEARNS

> **Active queue: §5c (Oct 9).** Earlier model assignments, queues, and status labels are historical; use §5c and its R01–R52 map for current ownership and acceptance.

TIER 1. Supersedes `ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md` as the current lane list
(its rule "measure before you add" survives as §7 here). Gates outrank dates. Licence of every
item is `PRODUCT_EXPERIMENT` unless stated. Written by Fable 5.1 on the night of 2026-10-06 from
three inputs, in this order of authority:

1. The verified machine state (health probe, receipts, broker reads, git), §1.
2. The owner's review, verbatim: `C:\Users\mrthn\Downloads\AEGIS PRE BETA REVIEW.txt`
   (also Appendix A of the next file).
3. The outside guide: `C:\Users\mrthn\Downloads\AEGIS_V1_BETA_FABLE_HANDOFF_2026-10-06.md`
   (ChatGPT, 2,453 lines; its §47 ten-phase roadmap was checked, not adopted; §2 says why).

Operating model for this roadmap (owner, 2026-09-28 and 2026-10-06): **Fable orchestrates and
monitors. Opus 5.5 builds and attacks. Sonnet researches. DeepSeek is the only paid LLM.
OpenClaw browses read-only in the MuratClaw Chrome. No payments, no messages or emails without
asking. Commit only on a full-suite exit 0.**

---

## 0. RESULTS SCOREBOARD (verified 2026-10-06 23:40 HKT)

**RESULT IMPROVEMENT: NONE.** Nothing on disk beats the market after costs on a declared read,
historically or forward. Code has not changed since `46d6efa4` (local branch = `main`; the 613
changed paths are all receipts and data). What has changed is the state of the machine.

| line | value | receipt |
|---|---|---|
| Best historical net strategy vs market | **None.** 301 of 312 rules on CRSP 1991-2024; 1 of 301 shows net-minus-market t >= 2 in validation on an undeclared read. **The fair-twin fix (handoff step 3) is still NOT in shared code**: the board still charges the twin a full round trip every month. | `hyp_lab/twin_board_SUMMARY_TB_2026-09-30_1.json` (`board_t_ge_2_and_fair_t_ge_2: 18`, `net_minus_market_validate_t_ge_2: 1`) |
| Best forward paper strategy | **None graded past 5 sessions.** Descriptive: contest rehearsal NAV $1,023,073 (+2.2% rel. ACWI over 2 sessions, 93% of it ACN +21%). CRSP_BLEND_v0 at session ~7 of 21, first read ~10-27. | `contest/rehearsal/SCOREBOARD.md`; `llm_portfolio/leaderboard_2026-10-06.json` |
| Paper estate | **362 priced, 148 ahead of SPY / 159 behind.** Excluding control twins 91 priced, +1.58%. Website lanes −2.74%; Alpaca fleet −9.81% (legacy loops); PC-PAPER +0.19% with **80% cash**; night books +3.03%, their twins −1.11%. | `paper_accounts/roi_2026-10-06.json` `aggregate` |
| Website lanes since 06-08 | conservative-atr +3.34, tsmom-overlay +3.71, aggressive +1.99, balanced +0.31, conviction −9.07, mirror −24.5, smallmid −3.47 | `aegis_verified_state` track_record |
| Independent selector count | 5 fleet sources live (hack1 themes, hack2 revision flow, hack4 funnel 1/σ, hack6 news; hack5 control) + 4 shadow books. **0 with evidence.** hack3 dead (401; owner: retired). | `fleet_manager/modes.json` |
| Live decision loop | **DEAD 6.7 days.** No sim session since 09-29; funnel snapshot 13 days old (limit 10); ranking 5 sessions behind; u_plan / u_review / u_forecast / policy_state stale. Contract still sized on $40,000 vs ~$1,001,903 equity (`UNRECONCILED`). | `health/health_20261006T153238Z.json` |
| Graders | ALIVE. Bars current (2026-10-05). 766 new forecast rows in 10.5 h; 137 due-unresolved. Daily pass 12 ok / 2 nothing-to-do / 0 refused, `degraded: []`. | `night_factory_2026-10-06/daily_pass_2026-10-06.json` |
| nn_lab | **Refusing every night** (`TableShrink`) since ~10-01; `nn_lab/receipts/` has no new receipt. | `automation_fixes_2026-10-02.md` §3 |
| Reader / OpenClaw | supervisor alive (until 09:50), gateway alive, 0 tool calls outside the read set in 24 h. `dowjones_feeds`: **0 new items in 9.1 d** (STALE). llama-server down 9.1 d. | health probe |
| LLM spend | DeepSeek balance **$18.49** (10-06 11:17 UTC). Digest ~$0.15/run. IIF1 night 10-06 $2.45. | `deepseek_balance.jsonl`; `iif1_nights/2026-10-06.json` |
| Contest | Registration window CLOSED (10-04 23:59 NY). **Whether Murat registered is unknown to the machine**; `contest/wls/` is empty (no MEMB export). Rehearsal sheets daily since 09-30. | `CONTEST_RUNBOOK_2026-10.md` |
| Resources | 251 GB disk free. RAM tight (a third of it free with Chrome + reader up). GPU idle. | health probe |

---

## 1. WHAT IS TRUE TONIGHT, AND WHAT IS NOT

- **The code baseline is exactly `46d6efa4`.** Every number in the 10-02 handoff still describes the
  code; only receipts have moved. The seven "NEXT" steps of that handoff are all still open except
  step 1 (the DEGRADED-free daily pass after a sleep/wake happened: 10-03 to 10-06 are clean).
- **The CLAUDE.md "static file" fix is only half a fix.** `sim_run.u_funnel` refreshes the funnel
  once per sim session; no sim session has run, so the funnel is 13 days stale again and every
  contract prints a static `n_considered`. A remedy that lives inside a job that is not running is
  not a remedy. (Chunk C2.)
- **PC-PAPER is 80% cash** at ~$1.0M with 10 names. It is "ahead of SPY" by +0.19% mostly because
  it was out of the market while SPY fell. That is not selection. (R4 prints the raw line.)
- **Half the estate ahead of SPY is a count, not a finding.** 362 books share dates, names and
  ancestry; 17 of the 26 night books are twins of 9 books. The question is how many independent
  exposures the 148 collapse to. (R4 answers it tonight at $0.)
- **The forward reads that matter are dated:** digest 5-session grades 10-09; SHADOW_NEWS trust
  may leave 0 ~10-11; LIB-FWD-TWIN-1 early kill 10-26; CRSP_BLEND_v0 and SHADOW_BAYES_v1 at session
  21 ~10-27; straddle first entry 10-16. Every one of them depends on the twin being fair (C1).

---

## 2. MY ASSESSMENT (Fable, with the owner's review in one hand and the receipts in the other)

**Where the owner is right and the programme has been slow:**

1. *"We are afraid of making mistakes; the loop should act and learn."* The receipts agree in a
   way nobody has said plainly: the decision loop is **dead**, not cautious. The sim has not run
   for a week, the candidate set is stale, the mandate is unreconciled, and the one account that
   was meant to show "$1M managed by the engine" is sitting in cash. Before any new metric, the
   loop must run every US session or write a refusal with a reason that health turns red. (C2.)
2. *"Fix the twin; I like the twin idea."* Correct. The twin is the single most valuable control
   we have and its cost convention is the single largest source of false relative-edge claims.
   The fix is an hour of code and ~30 min of compute and has been "next" since 09-30. (C1.)
3. *"If a paper account is ahead of SPY, say so, then learn from it."* Correct, with one word
   changed: say it with its evidence label. `OBSERVED (6 sessions)` is a true sentence;
   "proven" is not. The dashboard should carry the label, not hide the number. (C3, C4.)
4. *"Ranking by sigma63 put analyst Sells at the top of the Bloomberg list."* Correct. sigma63 is
   a magnitude; the rehearsal ranks expected absolute move because the contest pays for variance.
   For any LONG list, magnitude must be a separate column from direction, never the sort key. (C4, C9.)
5. *"Freeze membership once a forecast exists."* Correct, and it is what point-in-time means. (C5.)
6. *"I want to talk to it, not type slash commands."* Cheap and useful. (C6.)
7. *"We re-pull data we already have; roadmaps mix; frozen services look alive."* Mostly true.
   `DATA_MANIFEST.md` exists but no agent is forced through it; health has ALIVE/STALE/DEAD but 17
   scheduled tasks report UNKNOWN because the probe reads `cmd`'s exit code, not the job's. (C8, C10.)

**Where I disagree, and will not build it the way it was asked:**

8. *"Punish not deciding."* A learner rewarded for acting will act on noise. The right instrument is
   **abstention regret**: every HOLD/REFUSE freezes a BUY counterfactual and is graded against it,
   so not-deciding has a measured cost without forcing a trade. (C11.) The mechanical reason the
   sim "does not decide" is C2, not psychology.
9. *"Leaked data, if public, even better."* Lawfully public information only, with first-public
   and first-detected timestamps recorded (latency is edge). Nothing from a non-public source. One
   line, no sermon.
10. *"Companies connected to [a religious/ethnic group's] lobbies."* Not a feature, in any form.
    The economic variables underneath it are public and measurable: lobbying expenditure
    (OpenSecrets), federal contracts and awards (USAspending), subsidies, PAC activity. Those go in
    the theory table (R5). Identity does not.
11. *"Test LLM authority over real capital."* Standing rule 8 stays. LLM-proposed books trade in
    PAPER under frozen contracts (hack1 and hack6 already do). The Alpaca winners all kept capital
    authority in deterministic code; so do we.
12. *"Why is DSR so low; are we backtesting badly?"* We are backtesting **honestly** against a bar
    designed for public claims. At 42,705 searched cells a 0.95 deflated Sharpe is unreachable by
    anything short of a genuine anomaly, and that is the correct answer for a RESEARCH_CLAIM. The
    error was letting that bar govern what we *display* and what we *paper-trade*. The three
    licences already separate those; this roadmap makes the separation visible on every surface
    (evidence labels, exploration vs validation runs).

**On the outside guide (ChatGPT's ten phases):** it is a good catalogue and I adopt its vocabulary
(Decision Story lineage, Edge Vector fields, evidence ladder, progress contracts, theory states,
abstention regret). I do **not** adopt its order. It builds a ten-field Edge Vector, a world graph
and a scenario engine before anything consumes them; CLAUDE.md's rule is *every module has a
caller or the suite fails*. So: Edge fields appear only where a consumer exists tonight (the
Opportunity Explorer shows D/M/Q/F/X from services that already run), MDC/regret counterfactuals
are **captured** from the first restored sim session and **trusted** only at 63 sessions, and the
world graph waits until the digest has graded rows (10-09) to attach to.

---

## 3. OWNER-REVIEW COVERAGE MATRIX — HISTORICAL 2026-10-06 SNAPSHOT

This 59-item matrix preserves the October 6 review and its original verdicts. Those verdicts
are historical, not current completion claims. The active October 9 acceptance and owner-review
map for handoff asks R01–R52 is in §5c below; use that map for this execution window.

Every ask in the review, one row. `ACCEPT` = built or scheduled below; `MODIFIED` = built with the
stated change; `OWNER` = needs a decision only Murat can make; `REJECTED` = not built, reason given.

| # | the ask (owner's words, compressed) | verdict | where |
|---|---|---|---|
| 1 | demonstrated edge is the weakest part; showcase results better | ACCEPT | C3 DNA, C4 Explorer, evidence labels |
| 2 | focus on LIVE trading, act fast, analyse actions AND inactions | ACCEPT | C2 (loop alive), C11 (regret ledger) |
| 3 | MMC / MDC are good ideas, keep working on them | MODIFIED: capture now, trust at 63 sessions | C11 |
| 4 | OpenClaw as an investor personality browsing the whole internet, YouTube, Instagram, other AIs | MODIFIED: search-led planner + YouTube transcripts + consent-dismiss; Instagram and consumer-AI sites REFUSED (login wall / ToS); other AIs via API or MCP only | R3 → C7 |
| 5 | improve CAGR and DSR; find/test candidates faster | MODIFIED: DSR governs claims only; speed comes from the loop running every session and hyp_lab cells at $0 | §2 item 12; C2; C12 |
| 6 | six best strategies on six paper accounts; reset Alpaca; hack3 is dead | OWNER: the reset is a broker-UI act; proposal of six roles below (§6 D2); hack3 retired | §6 |
| 7 | Bloomberg terminal integration, automate from the terminal PC | OWNER + DEFER: BLPAPI read-only bridge spec in the guide §35; needs the terminal PC and licence; nothing to build here until the owner confirms registration and terminal access | §6 D1 |
| 8 | ML/NN progress; fine-tune, reinforce | MODIFIED: nn_lab unfrozen with membership freeze + ridge/LightGBM baselines on the same folds; RL only as a contextual bandit over source/policy weights after forward evidence | C5; §5 later |
| 9 | "why not" act on leaked-but-public info | MODIFIED: lawfully public only, timestamps recorded | §2 item 9 |
| 10 | test LLM authority over capital | REJECTED for capital; paper arms continue | §2 item 11 |
| 11 | insiders, politicians, Bloomberg live data, X posts, government buying, crypto/prediction markets as data | ACCEPT as sensors with provenance and latency; CONGRESS-PTR-FWD-1 and insider C02 already accrue (do not read early) | R5 theory table |
| 12 | read charts / 52-week and day range | ACCEPT as numeric features (52w percentile, drawdown from high, gap, ATR position) as hyp_lab cells, not screenshots | R5 → C12 |
| 13 | is the forecast Monte Carlo? combine MC + LLM + analysts with weights | MODIFIED: the committee's MC propagates a distribution; it does not discover the mean. Blend weights shrink toward equal until forward evidence (small-sample optimisers fit noise) | §4 |
| 14 | lost media, re-pulling data, roadmaps mixing, frozen services | ACCEPT | C8 health, C10 catalog, this file as the ONE TIER 1 |
| 15 | daily pass does not decide; punish not deciding | MODIFIED → abstention regret | C11 |
| 16 | 80% SPY core-satellite is not beating anything | ACCEPT: label `BENCHMARK_OVERLAY`, never flagship | C4 |
| 17 | explain the expected-return layer simply | ACCEPT | §4 |
| 18 | LLM persona, context, fine-tuning matter more than raw use | MODIFIED: structured output (fact/cause/mechanism/horizon/falsifier) and the local-first/DeepSeek-escalation cascade; fine-tune on decision-relevant labels only | C7, later |
| 19 | why was the attractive book/sheet "voided"? | ACCEPT (answer) | §4 |
| 20 | turn backtest winners (12-1 momentum, insider momentum) into live context | MODIFIED: they live as frozen library books vs twins (LIB-FWD-TWIN-1) and are read 10-26; they are not promoted on hindsight | §1 |
| 21 | why is DSR low; are backtests done badly? | ACCEPT (answer) | §2 item 12, §4 |
| 22 | LLM for broad regime calls, not single stocks | ACCEPT as a graded forecast row (regime classification → numeric model), after digest grades exist | C7 phase 2 |
| 23 | scenario backcasting 2027/2030 | MODIFIED: probability-weighted named scenarios with falsifiers, used for thematic tilts; not a deterministic future | later; R5 lists the theme lanes |
| 24 | why blocks, why 32 months, why wait 24 months | ACCEPT (answer); sequential evidence for display, 24-month floor for claims | §4 |
| 25 | both twins winners: how to compare | ACCEPT (answer) | §4 |
| 26 | too many momentum variants; need original independent ideas | ACCEPT: theory objects, independence counted by cluster not by rule | R5, C12 |
| 27 | what are trading costs, aren't they cheap? | ACCEPT (answer) | §4 |
| 28 | broker identity, first-mover snowball, analyst skill filter, replace n>=5 | ACCEPT: snowball prereg draft without look-ahead; reputation-weighted consensus | R5 → C12 |
| 29 | fiscal-year-end spending, government contractors | ACCEPT as a theory cell with USAspending data | R5 |
| 30 | FINRA short volume, fundamental ratio tracker | DEFER: 6 rules need FINRA 2009+ on disk (data pull); tracker exists as cells | handoff step 8 |
| 31 | an LLM that updates weights and code live ("AI drives the car") | MODIFIED: night factory proposes on a branch → tests → adversarial review → owner gate for capital code; never live | §7 |
| 32 | what model does OpenClaw use; local vs DeepSeek extraction quality | ACCEPT (R3 audits; ft_lab answer in §4) | R3 |
| 33 | consent pop-ups, newsletter sign-ups, watchlists | MODIFIED: consent-dismiss rule yes; sign-ups/watchlists OWNER (decision #9 still open) | R3, §6 |
| 34 | truth lane vs discovery lane; our own measurement system | MODIFIED: field-level provenance (FACT / CLAIM / INTERPRETATION / FORECAST) and the Edge fields, not one score | C4 schema, C11 |
| 35 | immediate signal alerts, bots rule the market | ACCEPT: alerts exist and are LIVE; latency timestamps added to the decision story | C11 |
| 36 | which winners are luck vs replicable; conservative-ATR vs aggressive; PC paper | ACCEPT | R4 → C3 |
| 37 | reviewer attacks: which persist | ACCEPT: each build gets a second-Opus attack | §8 |
| 38 | borrow external systems (Alpaca winners, GitHub, LEAN, etc.) | ACCEPT | R1 |
| 39 | funding: Cyberport, HKSTP, ideathon | ACCEPT (research) | R2 |
| 40 | operating model: hold period, buy/sell timing | ACCEPT: every decision row carries horizon and exit rule; regret ledger grades timing and exit separately | C11 |
| 41 | NN lab: randomise chunks/times to avoid overfit | MODIFIED: purged walk-forward with embargo; randomise training-window selection only from pre-validation data; never random k-fold | C5 |
| 42 | what is ft_lab; 90% yet worse than TF-IDF | ACCEPT (answer) | §4 |
| 43 | news arm must be connected and weighed into decisions | ACCEPT: SHADOW_NEWS trust leaves 0 after 3 graded dates (~10-11), by rule, not by hand | §1 |
| 44 | LEAN as a second engine | MODIFIED: for ONE finalist when one exists; R1 checks whether free survivor-aware data makes it possible at all | R1 |
| 45 | data science must give meaning to numbers, not brute-force | ACCEPT: theory objects with mechanism and precursor | R5 |
| 46 | claim paper wins, downgrade later if they fail | ACCEPT with labels (OBSERVED → EARLY_EVIDENCE → REPLICATED → VALIDATED_EDGE) | C3, C4 |
| 47 | frozen services must be red | ACCEPT | C8 |
| 48 | forecast at every event, then grade | ACCEPT: forecast rows already accrue (766 in 10 h); the loop (C2) adds decision rows | C2, C11 |
| 49 | nightly sim should also live-invest; use the open PC | ACCEPT: market-hours learner (sim/live loop) and night factory are separate, connected jobs | C2 |
| 50 | Telegram: conversation, clickable bubbles, is OpenClaw always on | ACCEPT | C6 |
| 51 | TableShrink: freeze membership | ACCEPT | C5 |
| 52 | hypothesis lab has no magic answer; improve it | ACCEPT: EV shrink for families with posterior < 0.15 (decision #13: I apply it by default, see §6) | C12 |
| 53 | large-ledger archival: what does it mean | ACCEPT (answer) + small build | §4, C10 |
| 54 | V2 list review: NVEC/MAN/RHI/IRDM Sells at the top; FIZZ/EXEL/BBW/MANH/EXPO low upside; QUBT/KYTX/SLDP/SOC/NOVT excluded by n>=5; RGEN CEO sold; what is CRL | ACCEPT: the Explorer shows direction and upside beside magnitude, drops the n>=5 filter, shows insiders; CRL answered in §4; a High-Risk Innovation lane carries thin-coverage names with their risk flags | C4 |
| 55 | China / EM / rare earths / oil / peptides / robotics / batteries | MODIFIED: theory lanes and shadow books against LOCAL benchmarks; no names added because a theme is exciting | R5; no new book before 10-26 |
| 56 | PC paper must be $1M; also show $40k | ACCEPT | C2 |
| 57 | more books, more tests; percentage ahead matters | MODIFIED: more INDEPENDENT theories, not more books; no new book before 10-26 (09-28 rule) except free shadows | §7 |
| 58 | website: brain showcase broken, NN showcase bugging, make it visual (Opus task) | ACCEPT | C4 |
| 59 | post results publicly; apply for seed funding; call this V1 Beta | ACCEPT: V1 Beta acceptance in §9; funding pack outline from R2 | §9 |

---

## 4. THE ANSWERS THE OWNER ASKED FOR (short; receipts named)

- **sigma63 / "2σ 126 sessions".** `sigma63` is the trailing 63-session daily volatility. "sigma63
  move 21s" is the expected ABSOLUTE move over 21 sessions (≈ sigma63 × √21). It says how far a
  name may travel, not which way. The contest rehearsal sorts by it because the contest pays for
  variance; a long list must never sort by it. NVEC at the top with a Sell consensus is exactly that
  column doing its job and being read as another.
- **Why blocks, why monthly, why "32 blocks".** Daily returns of one strategy are not independent
  observations; a month of them is closer to one. Blocking by month (or by the swept horizon, per
  the 09-24 lesson) is how we avoid counting one bet 21 times. 32 monthly blocks is simply the
  length of the 2024-26 window, which is why nothing can be confirmed in it. The 24-month floor
  applies to **claims**. Display and paper decisions update every session with their label.
- **Both twins winners.** Then the common exposure made the money. Print gross vs gross (pure
  selection), net vs net under one cost model, and rule-minus-market; the edge is the part the twin
  does not share. If strategy +15, fair twin +12, SPY +7: beta/size gave 5, construction 3.
- **Trading costs.** Not taxes, not commissions. Spread (half the bid-ask on each side), slippage,
  impact, and turnover multiplying all three. Zero-commission equities still cost 5-30 bps a round
  trip in liquid names and far more in small ones; options quotes we measured were ~11.5% of mid
  (`straddle_forward_log_2026-09-29.md`). A +0.3%/month gross edge with monthly turnover dies to
  costs; the twin fix (C1) is about charging BOTH sides the same way.
- **Why DSR is low.** The deflated Sharpe asks: after 42,705 tries, how surprising is this best
  Sharpe? Not very. It is the correct bar for a public claim and the wrong governor for a paper
  book. §2 item 12.
- **Expected return layer, simply.** For each name the committee writes several scenarios with
  probabilities (up a lot, up a little, down) and takes the probability-weighted average, then
  subtracts costs and compares to the benchmark. Monte Carlo only draws many paths from that
  distribution so we can read drawdown and tail numbers; it cannot know the mean better than its
  inputs. Blends of several forecasters shrink toward equal weights because with few forward
  observations an optimiser fits noise and calls it a coefficient.
- **"Voided though attractive".** The 09-29 contest sheet was `VOID_LATE`: frozen 13 minutes after
  the open. A sheet frozen after prices move cannot prove it did not use them, however good its
  names look. Voiding is about when, not about quality. (CRSP_BLEND_v0, by contrast, was KEPT as a
  free shadow and reviewed 34/100 because it was chosen after looking at 40,920 blends.)
- **ft_lab, and 90% yet worse than TF-IDF.** `ft_lab` fine-tunes the local 7B to extract typed
  events from news. It labels the event type correctly 90.7% of the time (DeepSeek 94.0%, fewer
  material errors). A correct label is not a better forecast: as an input to the size model, the
  extracted fields added less than the sparse word counts TF-IDF already carries. Accuracy on the
  label and value for the forecast are two different measurements; it stays OFF as a sole extractor
  and becomes the cheap first pass with DeepSeek escalation (R3, C7).
- **The 3rd point on the analyst skill filter** (ANALYST-SKILL-1, `ANALYST_SKILL_1_VERDICT_2026-09-26.md`):
  persistence lives in an analyst's **bias** (systematically high or low targets) more than in
  accuracy; so weight analysts by bias-corrected, sector-specific, horizon-specific reputation with
  shrinkage for thin histories, and drop `n >= 5`. R5 writes the spec.
- **CRL** = FDA Complete Response Letter: the application cannot be approved as filed. A binary
  regulatory event; biotechs carrying one are shown as such, apart from ordinary names.
- **The 178 MB ledger.** A closed monthly `jsonl` ledger exceeded GitHub's 100 MB file limit: we were
  using git as a data warehouse. Fix: monthly ledgers rotate into Parquet outside git with a
  committed manifest (schema, rows, date range, sha256, path). (C10.)
- **Investigator skill is on magnitude, not direction.** σ_π for direction is 0.0036 vs 0.1183 for
  size (`IIF1_PRE_NIGHT_1_CHECKLIST.md`): a direction primary never resolves at any n we can afford.
  Hence "LLM says it will move; something else says which way" is the registered design, not a hope.

---

## 5. THE CHUNKS

Each chunk: one Opus builder, one adversarial Opus review, Fable adjudicates, one full-suite run
per merge batch, commit on exit 0, `ci_watch --wait` after every push. Research chunks (R) are
Sonnet, $0 unless stated. Costs are LLM dollars; compute is the PC.

| id | chunk | gate to start | acceptance (receipt) | owner | cost |
|---|---|---|---|---|---|
| **C1** | **Fair twin in shared code**; re-run library + bridges boards; verdict diff | none | four columns on every row (gross/gross, net/net, net−market, old round-trip as upper bound); `fair_twin_reissue_2026-10-06.md`; tests pin the convention | Opus | $0 |
| **C2** | **PC-PAPER $1M mandate + sim owner + funnel refresh** | worst case in dollars printed and ≤ 10% equity/day | contract `capital_usd` = broker equity; `scaled_views` at $40k; a US-session owner for the sim; `funnel_night10.json.generated_at` moved; health shows a REFUSE reason, never DEAD | Opus | $0 |
| **C3** | **Winner/Loser DNA** as a nightly receipt (`book_dna`), from R4 | R4 note | clusters of the 148 winners; beta/cash/selection split per lane; evidence label per book; in the daily pass | Opus | $0 |
| **C4** | **Opportunity Explorer** web page + `/api/opportunities`; brain and NN showcases fixed | none | owner's column order; direction ≠ magnitude; company names for foreign tickers; links; `frontend_check` three exit codes 0 | Opus | $0 |
| **C5** | **nn_lab membership freeze**; nightly runs again; baselines beside the NN | none | receipt per night with before/after rows; a re-adjustment appends a revision, never shrinks; ridge/LightGBM/NN on the same folds | Opus | $0 |
| **C6** | **Telegram cockpit**: intent router, inline buttons, follow-up context, "is OpenClaw on" | none | ~15 utterances resolve deterministically; LLM fallback ≤ 20/day, refuses out-of-enum; no new authority | Opus | <$0.10/day |
| **C7** | **OpenClaw open web**: search-led query planner, YouTube transcripts, consent-dismiss, yield receipt | R3 note | pages → claims → forecast rows per day printed; a zero is visible; read-only; refused hosts unchanged | Opus | $0 |
| **C8** | **Progress-aware health**: schtasks read the job's receipt not `cmd`'s rc; brain refresh gets a daily caller; openclaw bridge heartbeat; "same hash too long" = STALE | after C2 (shares `health_probe.py`) | UNKNOWN count for `task:*` → 0; `optimus_brain` ALIVE | Opus | $0 |
| **C9** | **Contest desk, direction-aware**: a second rehearsal sheet = magnitude × direction sign (revision flow + consensus), graded beside ROT5_TRAIL | owner confirms registration (D1) for the LIVE desk; rehearsal needs no gate | two sheets graded daily to 10-15; the runbook names which goes live | Opus | $0 |
| **C10** | **Data catalog + ledger archival**: `data_catalog` receipt (every dataset: path, rows, dates, sha, consumers), Parquet rotation + manifest for closed ledgers | none | an agent can answer "do we have X" in one command; the 178 MB file is out of git with a manifest | Opus (Sonnet draft) | $0 |
| **C11** | **Decision Story + regret ledger**: lineage ids event→evidence→forecast→decision→order/abstention→outcome; frozen leave-one-source-out and BUY-counterfactual per HOLD; graded at 5/21/63 | after C2 (needs a running `u_plan`) | every decision row has its counterfactual rows; regret by type (direction/sizing/timing/selection/exit/abstention) in the daily pass; MDC printed with `n_sessions` and `TRUST_AT_63` | Opus | $0 |
| **C12** | **Theory cells at $0** from R5: price-location features, fiscal-year spending, snowball prereg (registered by Fable, not the builder), EV shrink for families < 0.15 | R5 note | cells in `hyp_lab` LEDGER with declared reads; prereg in `docs/TRIALS/` | Opus | <$0.40/night |
| R1 | borrow from outside (Alpaca winners, RD-Agent, OpenBB, LEAN, FinRL) | — | `borrow_from_outside_2026-10-06.md` | Sonnet | $0 |
| R2 | funding + contest facts | — | `funding_and_contest_status_2026-10-06.md` | Sonnet | $0 |
| R3 | OpenClaw model audit + open-web feasibility + 7-day yield | — | `openclaw_open_web_and_model_audit_2026-10-06.md` | Sonnet | $0 |
| R4 | Winner/Loser DNA analysis | — | `winner_loser_dna_2026-10-06.md` | Sonnet | $0 |
| R5 | snowball prereg draft + theory objects | — | `snowball_and_theory_objects_2026-10-06.md` | Sonnet | $0 |

**Order tonight:** C1, C2, C4, C5, C6 and R1-R5 run in parallel (distinct files). C3, C7, C12 start
when their research note lands. C8 and C11 start when C2 lands. C9 and C10 fill gaps. Each merge
batch: full suite → commit → push → `ci_watch --wait`.

**Later (not tonight, gated):** contextual bandit over source/policy weights (after C11 has 63
sessions of regret rows); regime-classification forecast rows from the digest (after 10-09 grades);
scenario lanes; BLPAPI bridge (owner's terminal PC); LEAN replication of ONE finalist (if R1 finds
survivor-aware free data); six-role fleet reset (owner's broker-UI act, §6 D2).

---

### 5a. STATUS AFTER NIGHT ONE (2026-10-07 05:30 HKT) AND THE SECOND WAVE

Night one: C1-C12 BUILT, each reviewed by a second Opus and fixed (`docs/reviews/REVIEW_2026-10-06_*.md`); C13 (two suite
failures) and C14 (gateway process leak) added. Merge gate: full suite rerun on the morning of 10-07.

Second wave (owner, 2026-10-07 05:15: "take up the roadmap, divide it into manageable chunks, build with agents,
address everything my prompt said and the GPT report offered"). At most five builders at once (memory lesson).

| id | chunk | from | gate | acceptance |
|---|---|---|---|---|
| C15 | Review follow-ups owed: sticky-twin per-draw turnover check v2; `book_dna` lane-beta lag check; ROT5_DIR event replay as our receipt with a momentum control; contest horizon worst case (print gap percentile, 23-session hold); `opportunities_build` scheduled; nn_lab revisions log tracked; first live planner run on the $0 sources | reviews C1/C3/C9/C4/C5/C7 | suite green on night one | each item has a receipt or a dated refusal |
| C16 | Public-flow SENSORS: USAspending awards + DoD contracts, Senate LDA lobbying $, FEC PAC $, prediction-market and crypto state as market-state inputs, fiscal-year-end spending theory cell | R6 note | R6 | pulls with provenance + latency fields; cells declared and hashed; no trade signal from a sensor alone |
| C17 | WORLD STATE + REGIME ROWS: structured belief table updated per digest cycle; regime-classification forecast row graded like every arm; fact/claim/interpretation/forecast provenance fields; scenario objects (2027/2030) as Explorer LABELS; the graded news→decision connection and its trust rule | R7 note | R7; grades from 10-09 for trust | beliefs persist and decay; regime rows in the ledger; scenario labels on the Explorer; trust can only grow by rule |
| C18 | ANALYST REPUTATION: replace `n>=5` with reputation-weighted consensus (firm → sector × horizon → global shrinkage from ANALYST-SKILL-1) in the Explorer and ROT5_DIR; the snowball FOLLOW-THROUGH leg as a free shadow series (return leg stays unregistered: unpowered) | R5 §2, R8 | none | consensus field carries weights and n_effective; shadow series writes rows |
| C19 | PAPER ARENA + FORECAST LAB + THEORY LAB + SYSTEM HEALTH website pages (evidence ladder on every book; Winner/Loser DNA; calibration and magnitude-vs-direction; theory states; progress-aware health), and the README refreshed with labels | C3/C8/C11/C12 receipts | none | `frontend_check` 0/0/0; every number on a page names its receipt |
| C20 | SIX-ROLE FLEET as frozen v3 contracts (not launched: no new book before 10-26; owner's broker-UI act), PC-PAPER benchmark-core option built behind a flag OFF (D14), the Telegram serve child restarted on the merged code | roadmap §6 D2/D14 | D2/D14 owner | contracts hashed; flag OFF; cockpit live |
| C21 | EXTRACTION CASCADE: local 7B first pass → DeepSeek escalation on low confidence/material events, yield and quality receipts; the OpenClaw consent-dismiss click enabled with a receipt (read-only safe); `sessionIdleTtlMs` is the owner's config line | ft_lab receipts; R3 | none | cost per typed event and error rate per arm on one receipt |
| C22 | OUTSIDE TOOLS: OpenBB platform as a research tool (local probe, licence check, one MCP query); LEAN DEFERRED (no finalist, no free survivor-aware data); BLPAPI OWNER (terminal PC) | R1 | none | a probe receipt; a written refusal for the deferred two |
| C23 | FUNDING + DOCUMENTATION: evidence pack draft from receipts (labels, costs, decision story), the V1 Beta doc with an architecture diagram, the public README | R2, R9 | none | one doc the owner can file from; no "proven" anywhere |
| C24 | DESKTOP .exe: the new pages in the static export; offline behaviour of `/opportunities` and `/brain` without keys | C4 | none | desktop export exit 0; a receipt from a launch via Start-Process |

Still gated on time, not on work: contextual bandit over source/policy weights (63 regret sessions); regime trust (10-09
grades); forward reads 10-26/10-27; the contest (10-12). Still the owner's: D1, D2, D5, D7, D13, D14, D15, D16, D17.

### 5b. OPERATING MODEL RESET AND THE THIRD QUEUE (owner brief 2026-10-07 10:20 HKT)

Owner's order: Fable manages, strategises and orchestrates only; Sonnet for research, reading, specs, docs, simple
debugging, low-risk frontend; Opus 5.5 only for financial decision architecture, measurement/backtest correctness,
portfolio/execution logic, concurrency/data-integrity bugs, major architecture, and adversarial review of changes that can
move research conclusions or paper capital; DeepSeek/local for bulk extraction; deterministic tests review UI/docs/plumbing.
Concurrency modest (the ten-builder wave caused the memory pressure and the MCP leak). Commit checkpoints on the WIP branch.
Weekly strong-model allowance is a budget: ~half used by 10-07.

**Status after the morning wave (chunk → state):** COMPLETE & reviewed: C1/C1b, C2, C3, C4, C5, C6, C7, C8, C9, C10,
C11, C12, C13, C14, C16, C17, C18, C19, C23, C25. PREPARED, INACTIVE: C20 (v3 contracts, benchmark core flag OFF).
PLUMBING ONLY until forward evidence: C11 regret (first grades 10-13 at the earliest; 0 live stories until tonight's
session), C17 regime rows (10-10/10-16), C18 snowball (2027-01), C12 cells (all unpowered). WAITING ON OWNER: D1, D2,
D13-D22. UNVERIFIED: the frozen-tree suite (two memory kills; the 10-07 10:05 run: 13,649 passed, 6 README-block
failures from the docs pass, being restored by Sonnet). BROKEN: none known. New, unreviewed: C26 fleet gates + EOD audit
(Opus; the two new gates default to SHADOW until the owner decides the 40% sector cap: hack2 is 67% Technology).

**Connection to the learning loop (honest):** Decision Story + regret, world state, regime rows, snowball shadow,
public-flow sensors and the analyst weights are all wired to WRITE rows; none has changed a decision yet, by design
(trust rules), and the sensors have no consumer cell yet. The pages make that visible rather than hide it.

**Third queue (small batches; worker chosen as the cheapest sufficient):**

| id | task | worker | why | gate |
|---|---|---|---|---|
| Q1 | restore the README's generated bridge block (6 tests) + put C26's two new gates in SHADOW mode | Sonnet | mechanical, test-pinned | now |
| Q2 DONE 15:10 | merged `92f147f6` → CI hotfix `e041ec14` → prod receipts fix `ad7ddbf6`; CI green; Railway live; six endpoints 200 from published copies; pages render | deterministic + Fable | the gate | — |
| Q3 | design reference library (p5.js, p5.brush, reasoning orbs, motion for data; GitHub identity plan) → `docs/design/` | Sonnet | research/docs | now |
| Q4 | the four social-media ideas as theory objects (exact rule, mechanism, literature, data gaps, falsifiable question) + the intake template | Sonnet | research | now |
| Q5 | Brain page v2: state-driven layout (no force simulation), motion only on state change, every orb traces to a receipt field | Sonnet (frontend) | low-risk UI; deterministic tests review | after Q3 + Q2 |
| Q6 | finance-research intake for Theory Lab: a Sonnet routine that, for a named topic, returns mechanism / assumptions / variables / failure modes / period / our-data test; first topics: Markowitz 1952, overnight-vs-intraday (Lou-Polk-Skouras), Monday/turnaround effect, PEAD, analyst revisions | Sonnet | research; DeepSeek for bulk | after Q4 |
| Q7 | review of C26 (fleet gates touch live paper orders) | Opus 5.5 | execution logic; capital-adjacent | after Q2 |
| Q8 | external AI as research instruments (Perplexity/Consensus/Semantic Scholar/arXiv APIs): coverage, latency, cost, novelty vs our stack; OpenClaw "I am missing academic evidence" tool selection | Sonnet | research first | after Q6 |
| Q9 | heavy deferred items, one at a time: sticky-twin per-draw check v2, ROT5_DIR replay receipt, contest horizon worst case, extraction cascade (GPU), desktop export check | Opus for the twin/contest measurement; deterministic for exports | measurement | after Q2, memory ≥ 4 GB |
| Q10 | token-budget view: a small receipt per session (Opus/Sonnet calls, tasks, EV) read by the handoff | Sonnet | plumbing | with Q2's handoff |

**Status 2026-10-07 17:35 HKT:** DONE — Q1, Q2, Q3, Q4, Q5 (`/brain` v2), Q6, Q7 (C26 review), Q8, Q9a (sticky v2 + ROT5_DIR
replay), Q10, Q12 (academic lane), Q14 (diagnosis; D23 owner), Q15 (two NAV-adjacent spots owed), Q16, Q17, Q18 (D24 owner),
C26-fix, C27 (live at 22:45 HKT tonight), C24 (builds green; live `.exe` probe owed). IN THE CLOUD SESSION'S BRANCH
(`claude/beautiful-meitner-hq5614`, PR pending): Q11 ledger split, Q13 brain showcase (optimus repo), GitHub identity,
research cards + validator, prior-art map, Optimus connection map / MCP tools / author profile, provenance audit.
WAITING ON TIME: first decision stories and regime grades (10-10), digest 5-session grades (10-09), news trust rule,
forward reads 10-26/27, contest 10-12. WAITING ON OWNER: D1, D2, D5, D7, D13, D14 (+D21/D22), D15, D18, D19, D20, D23, D24.

**Queue amendments 2026-10-07 12:40 HKT (after the merge of `92f147f6`):**

| id | task | worker | why | gate |
|---|---|---|---|---|
| C26-fix | the C26 review's fixes before 22:45 HKT: catch any exception on the fill read; print the `C26:` delta line; RESTORE refuse (not shrink) on cash/gross/name/turnover; exits count toward the order cap; replacement stop sized after the gates; enforce mode refused on a stale/unknown sector map; replay test of the 10-06 receipt | Opus 5.5 | live paper orders | now |
| C27 | **wash-trade rejections**: since 10-01, 49 of 75 live fleet buys came back HTTP 403 "potential wash trade" (a top-up of a name with a resting stop). The executed books drift from their frozen contracts more from this than from anything C26 changed. Fix in the manager: cancel/replace the resting stop atomically with the top-up, or skip the top-up and record `REFUSED_WASH_TRADE_RULE`; count rejections in the EOD audit (today it does not) | Opus 5.5 | execution correctness, priority 1 | after C26-fix |
| Q11 | `predictions.jsonl` is 52 MB tracked (GitHub warns at 50, refuses at 100): monthly append-only streams (forecasts by month made, resolutions by month graded), LF only, sealed months with a manifest chained to each other, and an explicit CHAIN-BREAK record for the hash chain broken since 25 Aug (never a silent repair) | Opus 5.5 design + deterministic | data integrity, priority 2 | after Q9a (memory) |
| Q12 | academic lane in the query planner: OpenAlex + CrossRef + NBER RSS at $0 behind the declared-provider gate; the research-intake card's NEEDS_EVIDENCE verdict is the trigger; yield receipt (citations found / novel / verified) | Sonnet | research plumbing | after C26-fix |
| Q13 | the sibling `optimus` repo's brain showcase (`showcase/build.py`): static state-board layout from the `/api/legibility/v1/brain` payload, legend never overlaps, data refreshed by the publish job | Sonnet | low-risk UI | after Q5 is live |
| Q14 DONE (diagnosis) | the Railway `FRED_API_KEY` is present but FRED answers "api_key is not registered" (reproduced locally: wrong-key shape matches production exactly). **D23 (owner): set a valid key on Railway** — `railway link --project selfless-courage --service Aegis-Finance --environment production` then `railway variables --set FRED_API_KEY=<key> --service Aegis-Finance`; verify `n_loaded` → 23. New health row `fred_macro_inputs` reads DEAD on today's production body. Second finding → Q15: three consumers impute silently (`fixed_income` reports stress "normal" on empty spreads and bypasses fred_health; `fx_curves.fetch_short_rate` substitutes 0.04 while claiming FRED; `data_fetcher.get_recession_probability` returns a bare 0.15, dead code) | Sonnet (silent-fragility-audit) | priority 3 | after the hotfix |
| Q16 | `scripts/ci_watch --wait` reported "no run found for that sha within the wait window" for `e041ec14` while the GitHub API showed `CI completed success` for the same SHA 20 minutes earlier — a watcher that misses a finished run is a gate that cannot go green; fix the lookup (full SHA, `event=push`, pagination) and add a test on a saved API fixture | Sonnet | priority 3 (the push gate) | now |
| Q17 | three Opportunity Explorer receipts (5-8 MB each) are TRACKED under `backend/data/optimus/opportunities/` — the published copy in `public_receipts/opportunities/latest.json` (≤ 2.4 MB, sanitised) is what the site needs; gitignore the raw receipts going forward (no history rewrite; D10), keep the newest in the catalog, and make `opportunities_build` write only the run-id file + the published copy | Sonnet | priority 6 (repo size) | after the prod-404 fix |
| Q18 | the live site still inlines the `[SENSITIVE]` placeholder as `NEXT_PUBLIC_API_URL` (Vercel's CLI redacts pulled values; `vercel build` in the workflow consumed the pulled file) — the code fallback keeps the site working but every page logs "Fix the build environment"; set the public URL explicitly in the workflow's build env and add a post-build guard that fails on the placeholder; Vercel's bot checkpoint (403) blocks automated browser verification, so verification is by chunk grep + console | Sonnet | priority 6 | now |

### 5c. ACTIVE EXECUTION QUEUE — 2026-10-09 (supersedes prior queues)

This dated amendment replaces the active execution order above; earlier queues and their receipts
remain historical. Recovery comes first, then the shortest evidence-producing work proceeds in
parallel. A blocked external input pauses only its own lane. No new roadmap is created. The
October 9 handoff is guidance, not evidence that work has run. PC-PAPER's new no-index policy
epoch is explicitly owner-authorized: preserve the old ledger and SPY control, and never rewrite
prior NAV. At most three workers run alongside the coordinator; no nested agents, one writer per
artifact, one PC runtime operator and one OpenClaw browser operator.

| ID / workstream | Owner and dependencies | Observable acceptance and current state |
|---|---|---|
| W1 Recovery, scheduled checks + PR #13 | Coordinator owns recovery closeout. Repair builder owns PR #13; independent reviewer reproduces after the fix. One PC runtime owner handles scheduled receipts; one browser owner retains OpenClaw. | **IN PROGRESS / NOT READY.** Valid-window sim ran two full cycles (268 rows; 134 done, 25 unpriced, 1 refused; $0.177312; zero orders); mandate remains stale/unreconciled. Earlier combined suite recorded 14,246 passed, 74 skipped, 126 deselected, plus one audit-ledger enrollment failure; source hashes unchanged. Fix `6c6b62d7` is root-approved after 17 focused tests. At 00:27 SGT, 342 focused tests across 14 changed test files passed with source hashes unchanged; CI and final full verification remain pending. PR13 `adb6a009` passed independent 80 focused tests plus 31 clean-clone checks. Docker `b435700a` passed 10 root tests and simulated-image-path verification. Neither is pushed, deployed, or task-installed. Learning-parser `b20abcf8` passed root closure (66 tests + 16 independent adversarial checks); runtime refresh pending. OpenClaw fix `f2af56fe` is active: default age 0 removes the two-hour Chrome recycle; graceful supervisor/reader handoff 00:14–00:16 SGT had no kills, stable gateway/browser births, and an advancing new reader. Quiet CLI fix is also active. StraddleForward's Oct 9 valid-window task exited 0 with 346 usable quotes and OBSERVE_ONLY because no standard monthly expiry fell in the 21–35 DTE window; observation complete. Public-assets Saturday Oct 10 10:30 SGT is proposed/configured but not installed; DataCatalog remains daily 09:00. Next NN run Oct 10 08:30 SGT; AnalystPull Sunday 10:00; IIF Monday 16:00 (standing 16:45–17:05 exclusion applies). Fleet contract/hack5 status, actual Brain/NN page acceptance and Telegram delivery proof remain open. |
| W2 PC-PAPER new policy epoch | Capable builder and paper-account owner; a stronger independent reviewer is REQUIRED for policy, sizing and transition; coordinator integrates. Depends on verified existing paper endpoint/account and fleet contracts. | **IN PROGRESS — repair required.** Candidate `ff14efa2` remains inactive; independent review rejected it for three actual consumer/lifecycle bugs. Repair is underway, not accepted. Existing owner policy authorization persists; contract bars activation before Monday 13:30 UTC. Keep old policy, fills and NAV immutable. |
| W3 Revision-flow attribution | Bounded research worker; coordinator independently checks joins, timing and comparison definitions. Depends on dated source receipts and a common evaluation window. | **PARTIAL.** Audit `d049538d` independently reviewed the 367→362→307 census and exact 51/51 claim construction; this is not article-parser validation or causal attribution. Fee/fill and causal contributions remain unknown. Preserve original classifications. |
| W4 News interpretation + escalation pilot | Local-model/news worker; coordinator reviews provenance and a small quality/cost sample. Depends on the existing pipeline and one browser owner for any permitted source work. | **IN PROGRESS.** Earlier `ac5ac4e9` p1/p2 runs returned INVALID_OUTPUT on two development examples each. Blind-source-gold audit is complete on 40 rows (31 proposals, 9 ambiguities); final adjudication/benchmark errata remain pending, and no new frozen manifest exists. Cascade `40030617` passed 103 integrated tests. At 16:23 UTC, a two-example schema-only development pilot made two paid-route requests; both returned OK with unique valid telemetry. Local estimated cost was $0.00045633; vendor-balance precision and shared-account charge attribution are UNKNOWN. Cached validation replayed with zero API calls and unchanged hashes. No quality score, new benchmark, held-out result, or promotion follows; the schema-only result proves transport/telemetry only. Keep `NEWS_TILT_IN_PLAN` under its existing trust gate; a separately frozen, bounded `PRODUCT_EXPERIMENT` challenger is permitted but cannot bypass or promote through that gate. |
| W5 Original-decision audit + labeled replay | Strong research worker with an independent skeptical review; no paper-writer overlap. | **PARTIAL.** Read-only audit construction passed independent review for exact 51/51 matching; this does not establish causal attribution, complete fills/actions, or skill. Reconcile original forecasts, actions, abstentions, winners and losers against dated inputs. Keep any new retrospective replay separately named, with coverage, timing/leakage controls, baseline and costs; never call replay forward performance. |
| W6 Local cutover + backup/restore | Local infrastructure owner; coordinator reviews restore evidence. Depends on dependency/billing inventory and a recoverable snapshot. | **PARTIAL.** Independent review passed transfer/restore checks for SQLite and forecast ledger only. This is not a whole-volume backup or cutover; inventory remaining dependencies and billing, rollback and ledger boundaries before any cutover or savings claim. |
| W7 Monday evidence pack | Coordinator integrates; owner supplies authentic Terminal inputs where needed. | **IN PROGRESS / NOT READY.** Include consumer and scheduled-task evidence, audit limits, scoped restore, and release receipts. AnalystPull Sunday and IIF Monday remain pending; authentic Bloomberg inputs remain **EXTERNAL_INPUT**. Continue independent work while those gates are pending. |

#### Current owner-review map for handoff asks R01–R52

The ask names below abbreviate the source requirements in the supplied handoff's §12. Status is
per ask, not inherited from a neighboring row: `QUEUED`, `IN_PROGRESS`, `PARTIAL`,
`EVIDENCE_MATURING`, `DEFERRED_WITH_REASON`, or `EXTERNAL_INPUT`. Earlier `ACCEPT` labels are
not current evidence. Every completion needs its named consumer and dated receipt.

| ID | Ask (short label) | Workstream | Current status and acceptance |
|---|---|---|---|
| R01 | Profitability and live learning | W2 | IN_PROGRESS — valid-window sim produced zero orders; mandate remains stale/unreconciled, so no profitability claim. |
| R02 | Winners and losers | W3 | PARTIAL — audit reports original winners/losers; full fee/fill and causal attribution remains open. |
| R03 | Books versus accounts; 363/307 and 11/12 | W3 | PARTIAL — reviewed 73-source census construction (367→362→307); reconcile account/book denominators against matched receipts. |
| R04 | No SPY-dominated flagship | W2 | IN_PROGRESS — inactive candidate review found three consumer/lifecycle bugs; repair and re-review pending, no transition accepted. |
| R05 | $1M paper and $40k view | W2 | QUEUED — show actual equity and separately executable scaled view. |
| R06 | Six fleet roles and retired hack3 | W1 | IN_PROGRESS — reconcile existing contracts; no reset/revival without a distinct decision. |
| R07 | Stale/frozen process health | W1 | PARTIAL — OpenClaw handoff and quiet CLI fixes active; no-kill reader handoff verified; hack5 remains unknown. |
| R08 | Sim/funnel/forecast chain | W1 | IN_PROGRESS — two full cycles advanced all units; no orders, stale mandate and 2026-10-16 first grades remain open. |
| R09 | OpenClaw researcher | W1 | PARTIAL — one browser owner; search-led task must return cited missing evidence. |
| R10 | Local model reads real news | W4 | PARTIAL — p1 and p2 each returned invalid output on two development examples; no valid extraction or held-out evidence. |
| R11 | Cheap DeepSeek escalation | W4 | PARTIAL — two schema-only requests verified paid-route transport and unique telemetry; local estimate only, vendor-balance attribution and quality/cost validation remain open. |
| R12 | Newsletters, watchlists and IR | W4 | QUEUED — approved free-source access and real ingestion receipt; no paid trial. |
| R13 | Social/video sources | W4 | DEFERRED_WITH_REASON — defer until permitted transcript/API and timestamped confirmation path is selected. |
| R14 | World context and regime | W4 | QUEUED — dated structured beliefs, contradictions and affected sectors. |
| R15 | Catalyst calendar | W4 | QUEUED — confirmed/estimated/conflicted events with timezone and revisions. |
| R16 | Direction versus magnitude | W3 | QUEUED — distinct fields and direction-aware long construction. |
| R17 | Monte Carlo/expected return | W5 | QUEUED — scenarios propagate calibrated assumptions; no invented mean. |
| R18 | Words-to-numbers bridge | W4 | PARTIAL — two schema-only responses passed transport/schema telemetry; no quality score, frozen benchmark, held-out result, or decision-consumer acceptance. |
| R19 | Unique contribution/MDC | W5 | QUEUED — frozen ablations, sample size and bounded causal language. |
| R20 | Missed actions and regret | W5 | QUEUED — retain abstention counterfactual; no forced random trades. |
| R21 | GPRO, PSNL and TEM chronology | W5 | PARTIAL — chronology is included in the audit; missing cases and outcome attribution remain open. |
| R22 | Original short-window test and replay | W5 | PARTIAL — 51/51 original claim-to-forecast construction approved; labeled retrospective replay and outcome attribution remain separate and pending. |
| R23 | First-mover revisions | W3 | QUEUED — as-of breadth/acceleration excludes future followers. |
| R24 | Analyst skill versus n≥5 | W3 | QUEUED — history by quality, bias, sector/horizon and uncertainty. |
| R25 | Target upside | W3 | QUEUED — separate price declines, target revisions, dates, dispersion and horizon. |
| R26 | Fair twin controls | W3 | PARTIAL — exact original twin lineage is matched; full fee/fill and causal attribution remain open. |
| R27 | DSR/PBO versus paper exploration | W5 | QUEUED — certification gates claims, not every experimental paper decision. |
| R28 | Distinct original theories | W5 | QUEUED — catalog/search and count mechanism clusters before bounded tests. |
| R29 | NN/TableShrink | W1 | EVIDENCE_MATURING — next scheduled run Oct 10 08:30 SGT; receipt and forward-roster grades pending. |
| R30 | ft_lab extraction versus prediction | W4 | PARTIAL — p1/p2 development extractions failed validation; separate extraction quality from prediction and rerun only after reviewed changes. |
| R31 | RL/continual learning | W5 | DEFERRED_WITH_REASON — first verify current source/policy updates are consumed; no new direct DRL lane now. |
| R32 | Self-improving code safety | W1 | PARTIAL — reviewed branch/test/review/owner path; no live self-modifying code. |
| R33 | Repeated downloads/data loss | W6 | PARTIAL — two-store backup/restore independently passed; full-volume and remaining consumer inventory pending. |
| R34 | Ledger and Git bloat | W6 | PARTIAL — preserve prior index-only cleanup; verify safe archive/backup boundaries. |
| R35 | Insider/politician/procurement/flow sensors | W4 | QUEUED — verify timestamped source consumption and disclosure latency. |
| R36 | Political influence features | W5 | DEFERRED_WITH_REASON — economic variables only; protected traits and unsupported allegations excluded. |
| R37 | Charts/ranges/seasonality | W5 | DEFERRED_WITH_REASON — review existing numeric cells only; no screenshot oracle or brute-force expansion. |
| R38 | AI/power/materials causal chain | W7 | QUEUED — precursor, horizon and falsifier in evidence pack. |
| R39 | China/international opportunity | W4 | QUEUED — context/shadows first; venue, FX and data permissions before execution. |
| R40 | High-risk names | W2 | QUEUED — uncertainty/catalyst/runway/dilution review; no forced inclusion. |
| R41 | Mirror account performance | W3 | QUEUED — historical error attribution only; no real-money change or recovery gamble. |
| R42 | Stable/local architecture | W6 | PARTIAL — two-store restore passed; cutover, remaining dependencies and billing remain open. |
| R43 | Bloomberg Terminal | W7 | EXTERNAL_INPUT — authentic WLS MEMB, rules and verified fills; rehearsal is not a substitute. |
| R44 | Contest-relative performance | W7 | QUEUED — named utility, valid rules, controlled adaptation and exact P&L. |
| R45 | Clear dated stock-list preview | W7 | DEFERRED_WITH_REASON — wait for data and decision contracts to pass. |
| R46 | Foreign tickers/biotech language | W7 | QUEUED — full company/venue/currency, short definitions and binary-risk markers. |
| R47 | Optimus/brain/NN showcase bugs | W1 | PARTIAL — Brain is FRESH (16 beliefs, 8 scenarios, 40 updates); IC remains 404 until a sim event; ForecastLab report stale since Oct 6, next run due to finish 21:10 UTC. Actual consumer acceptance remains open. |
| R48 | Telegram conversation/buttons | W1 | PARTIAL — offline query/auth/TTL fixtures pass; no actual tap-delivery proof. |
| R49 | LEAN/Qlib/TradingAgents/OpenBB/MCP reuse | W6 | DEFERRED_WITH_REASON — targeted pattern or finalist check only; no framework migration. |
| R50 | Research/patents/funding pack | W7 | DEFERRED_WITH_REASON — long-cycle research follows critical integration; preserve auditable sources. |
| R51 | Token/worker efficiency | W1 | PARTIAL — bounded smoke task passed; actual model/effort metadata unavailable, so cheaper routing and savings remain unverified. |
| R52 | Finish roadmap and preserve intent | W7 | IN_PROGRESS — §5c is the active acceptance map; completion requires evidence, not wording. |

A bounded cheaper-worker smoke task passed, but actual model/effort metadata was unavailable;
the requested route and any savings are therefore unverified. The nonsecret capability receipt,
with local environment details, is retained outside the public repository. Two full sim cycles
are verified; the stale mandate and any profitability claim remain open. Scheduled, browser-owned
and external checks are not complete until their respective consumers or receipts verify them.

## 6. OWNER DECISIONS (what I did by default, and what only Murat can do)

| # | decision | default applied tonight | what Murat does |
|---|---|---|---|
| D1 | **Bloomberg registration**: did it happen before 10-04 23:59 NY? | contest LIVE desk stays scheduled from Oct 9 but will REFUSE without `contest/wls/MEMB` export; rehearsal continues | say yes/no; if yes, export `MEMB` from WLS to `contest/wls/` and answer the 17-item checklist (R2 fills what public rules settle) |
| D2 | **Six fleet roles / Alpaca reset** | nothing reset; hack3 marked retired; proposal: (1) human+AI thematic (hack1), (2) analyst revision flow + snowball (hack2), (3) world/news causal (hack6), (4) quant ensemble = fair-twin library winners (hack4 re-purposed), (5) high-risk innovation lane (new or hack3's slot), (6) SPY control (hack5); PC-PAPER = the combined $1M policy | reset accounts in the broker UI if wanted (history is archived first by the fleet manager's snapshot); regenerate or close hack3 |
| D3 | PC-PAPER mandate $1M + $40k view | APPLIED (C2), per the review | nothing |
| D4 | nn_lab membership freeze | APPLIED (C5), per the review | nothing |
| D5 | EVLV / RZLV tight stops (~0.9σ) | unchanged (the manager never loosens) | say "let them run" or "close" |
| D6 | hyp_lab EV shrink for families with posterior < 0.15 (old #13) | APPLIED in C12 as a ranking preference (policy_state), not a kill | veto if wanted |
| D7 | sign-ups / watchlists on Yahoo, MarketWatch, Benzinga (old #9) | NOT built; R3 writes the exact approval wording | name the sites and say "approved" |
| D8 | Telegram LIVE alerts count as "asked" (old #8) | they continue (2 sent 10-02; replies-only otherwise) | confirm or stop with `alerts/STOP` |
| D9 | battery operation of alerts/digest/straddle (old #7) | unchanged | local setting |
| D10 | rewrite public git history (old #10) | **no** | — |
| D11 | Bloomberg terminal PC + BLPAPI read-only bridge | not started | confirm terminal access and licence terms |
| D12 | funding applications (Cyberport CCMF by 2026-12-01; CUPP via HKU) | R2 gathers facts and the evidence-pack outline | decide which to file |

---

## 7. RULES THAT BIND THIS ROADMAP

- **Measure before you add** (09-28) survives: no new paper book before 2026-10-26 except free
  shadows; a module that can only print "cannot distinguish" is not roadmap work.
- **Every number carries its evidence label**: `OBSERVED(n sessions)` → `EARLY_EVIDENCE` →
  `REPLICATED` → `VALIDATED_EDGE`. "Proven" appears nowhere.
- **Exploration and validation are different runs with different labels**: `DISCOVERY_ONLY` may
  overfit on purpose; a validator runs once on data the idea never saw.
- **A theory has a mechanism, a precursor observable before the move, and a falsifier**, or it is
  not a hypothesis yet. Identity groups are never a variable.
- **An LLM proposes; deterministic code sizes, stops and exits; gates only shrink.** Any code change
  proposed by a model goes branch → tests → adversarial review → owner gate.
- **A stale output is red even if the process is alive.** Same hash too long without a declared
  idle reason is STALE.
- **Before any data pull or new service: catalog, trials, postmortems, then build.**
- **No machine details in git.** `backend/data/optimus/local_pc/` holds them.

---

## 8. HOW THE NIGHT RUNS (and how a morning reader checks it)

1. Builders work in the main tree on disjoint files; they never commit. Fable runs the suite
   (`AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`,
   plus `nn_lab/tests` and `ft_lab/tests` separately), commits on exit 0 read from the exit code,
   pushes, and watches CI (`python -m scripts.ci_watch --wait`).
2. Each build is attacked by a second Opus as an investor ("you are wrong; I would have done this")
   before it is merged; the review lives in `docs/reviews/REVIEW_2026-10-06_<chunk>.md`.
3. Morning check, in order: `python -m scripts.health_probe` (sim_session must not be DEAD; nn_lab
   must have a receipt), `git log --oneline -10`, `docs/HANDOFF_2026-10-07_*.md` (written at the
   end of the night with the scoreboard first), then this file's §5 table with status marks.
4. Running processes that are NOT ours and must not be touched: the reader supervisor, the Telegram
   agent, the OpenClaw gateway, Chrome (MuratClaw). Kill only by a recorded PID.

---

## 9. V1 BETA: WHAT "DONE" MEANS

V1 Beta is reached when, for one full US session, the machine: refreshes its candidate set; ranks
with direction and magnitude shown separately; makes paper decisions sized on the $1M mandate with
a $40k view; records every HOLD with its BUY counterfactual; executes and reconciles at the broker;
grades at 1/5/21 sessions; prints regret by type and marginal contribution with its sample size;
labels every book's standing honestly on one web page; and has no subsystem that is alive but not
progressing. It does **not** require beating SPY; it requires that when something does, we can
prove which input did it and when we first knew.
