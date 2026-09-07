# REVIEW — 2026-09-07 — Fable 5.1 on GPT's three-day summary, Murat's two-mode prompt, five external repos, and the landscape

**Reader:** Murat first, then the Opus 5 builder session that runs
`HANDOFF_2026-09-07_FABLE51_TO_OPUS5_TWO_MODES.md`. The roadmap this review
feeds is `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` (an amendment to the
active `ROADMAP_2026-09-04_PROFIT_ENGINE.md`, not a replacement).

**Method.** Three read-only verification agents (Opus 5) checked every number
in GPT's summary against the receipts, grounded every idea in Murat's prompt
in the code that exists, and surveyed the website; one agent cloned the five
repos into `C:\Users\mrthn\reference\` and read them; one searched the
external landscape. Their full reports are committed beside this file:

| report | file |
|---|---|
| GPT's 20 claims vs receipts | `VALIDATION_2026-09-07_GPT_SUMMARY_VS_RECEIPTS.md` |
| the website today + what each idea rests on + replay cost | `GROUNDING_2026-09-07_WEBSITE_AND_IDEAS.md` |
| the five repos, with paths and a port list | `EXTERNAL_2026-09-07_FIVE_REPOS.md` |
| hackathons, frameworks, look-ahead, investors, funds, data, construction, psychology | `EXTERNAL_2026-09-07_LANDSCAPE_WHAT_WE_MISSED.md` |

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** This was a review and planning session; no book,
seal, order, deploy or Railway variable was touched. LLM spend: **$0.00**
DeepSeek (the agents were Claude sessions, not API calls).

| | |
|---|---|
| Best historical net strategy | unchanged: `ensemble_ew\|k=100\|ew\|hold=200\|10bps`, β 1.195, β-matched +5.651%/yr t 2.424 over 309 months, edge concentrated 1999-2007; **as a claim, NOISE** |
| Best forward paper strategy | none readable; conservative-atr +0.14pp at β 0.04 sat out a rising window |
| Independent selector count | unchanged |
| New actionable finding | **yes, four**, all from verification: (1) the construction-tax table mixes cost rates; (2) the event table is 2015-2026, not 2015-2024; (3) the NVIDIA embedder is reachable and the roadmap says it is not; (4) the news backfill died at 83.6% of the Alpaca leg with no log and no resume cursor |
| External execution drag | not measured |

## 1. GPT's summary: 13 of 20 verified, 2 wrong, 5 conflated, and 8 places where our own docs are wrong

GPT's narrative is sound. The story it tells, that the machine got honest and
the alpha did not appear, is the story the receipts tell. The corrections
that matter, in order of consequence:

1. **The construction-tax headline compares a 25 bps book with a 10 bps
   book.** The night lab's flagship table puts "top-50 VW, 25 bps, 3.66×"
   beside "top-300 EW, 10 bps, 29.27×" and calls it one column, two
   constructions. Same-cost pairs are **3.66 → 18.14 at 25 bps** and
   **8.96 → 29.27 at 10 bps**. The mechanism stands (fivefold at equal cost,
   TC 0.13 → 0.49, delta positive in all three eras), but 29.27 must never
   again be quoted beside 3.66. GPT also called the 29.27 row rank-weighted;
   it is the equal-weight cell. The +4.670pp headline's own broad leg is
   `k=300|rank|hold=600|25bps` at **17.755×**.
2. **The event table spans 2015-2026, not 2015-2024.** Of 993,005 rows,
   **789,277** are 2015-2024. The 81-86% coverage band is a 2015-2024
   statistic and is right. GPT inherited this from our build doc and roadmap.
3. **The NVIDIA embedder is reachable.** `N5_event_compression.json`'s
   `nemotron_probe` records `status OK, 3 embeddings, dim 2048`. The roadmap
   §6 line "NVIDIA embedder ABSENT, no key in this repo" contradicts the
   receipt it cites. GPT was right; we were wrong.
4. **Event compression is 137,190 → 105,494 (ratio 1.3005)** on the receipt at
   HEAD; the doc, the roadmap and the commit message carry a stale
   127,157 → 97,949.
5. **"About four cents"** for the fantasy-exam effect is off by ten: mean
   |Δp_up| is **0.3695** (round 1) and **0.301** (round 2); the canary is
   0.125 in round 1, **0/8 on the END arm but 1/8 on the FRONT arm** in
   round 2 (the doc says 0/8 flat).
6. **"6,942 passed" exists nowhere.** The ladder since 09-05 is 6377 → 6545 →
   6655 → 6766 → 6869 → 6984 → **7142** (17 skipped, 123 deselected), current
   on HEAD `d60795f`.
7. **"+5.75pp" and "12/12" are two different baselines.** +5.751pp is monthly
   vs frozen-once (A2); 12/12 is monthly vs annual (N1.4, median +1.204pp,
   best Holm 1.0). The receipt forbids quoting them as one quantity.
8. **hack2's min-hold 0 was not caused by the inert `AAT_MANAGE_ONLY` line.**
   Two independent findings: `contract.defaults_for` gives every non-tracker
   book the EVENT defaults (min hold 0), and the runbook's hold-back variable
   is read by nothing. hack2 is manage-only today by `Mandate.manage_only=True`
   in `alpha/fleet.py:109` (commit `5875483`). hack1, hack2 and hack5 still
   carry min hold 0; manage-only makes hack2's vacuity unreachable, not fixed.
9. **The Dimson loadings** GPT repeated ("0.66 today, 1.50 yesterday") are the
   doc's; the receipt says 0.6072 and 1.399. The finding (a stale mark hides
   β) stands and **nothing has been fixed**: the only services/routers commit
   since 09-06 is the CI repair.
10. **Long-short "realised β 0.00-0.05"** is false for four cells (encoder
    0.4254). The verdict (19 of 20 lose) stands.
11. **hack4's two ruin numbers are different objects**: 0.442 / p95 −72.8% is
    the *proxy genome* Monte Carlo; 0.232 / −46.88% is the champion's disclosed
    contract row; G4's sealed p_ruin is a third, 0.212. Compare, never average.
12. Minor: the liquidity-floor "−9.6pp" is a level (the delta vs institutional
    is −12.4pp); the ensemble's "8-arm months" filter is "≥ 6 arms"; hold-150 is
    `nn_pre_causal`'s optimum only (lgbm_clf's is 400); the growth champion is
    *below* SPY both unlevered (3.6684 < 3.6707) and leverage-neutral (3.6044).

**What GPT got right that we had not written down anywhere:** the four-stage
decomposition `prediction → selection → construction → holding/execution`,
with the observation that we spent five months on stage one. That sentence
belongs in the strategic invariants and it is added to the roadmap amendment.

**Fix status of the open items GPT listed:** clock skew NOT FIXED (every ET
gate reads `datetime.now`; the suite pins the absence of a guard); stale lane
NAV NOT FIXED; Sunday `considered=0` suites NOT FIXED (four suites, no fixture);
`verdict_from` NOT FIXED (`scripts/weekend_lab_jobs.py:225` still has no word
between NOVEL and NOISE); `evaluate.ERAS` HALF FIXED (derive-or-refuse landed,
two callers still pass no `eras=` and now refuse on a long panel);
`VENUE_REJECTED` refusal class NOT ADDED.

## 2. Things the verification found that nobody asked about

- **The news backfill died, it did not finish.** Started 00:58, last write
  03:18, Alpaca leg **112 of 134 months (83.6%)** with 2024-12 partial; the
  Finnhub leg never started; no coverage receipt was written; no log, no PID
  file, no cursor. The "~27% through" in the night-lab doc is prose with no
  computation behind it. The script (terminal repo, `scripts/news_backfill.py`)
  has **no `--resume`**; re-running is idempotent by uid dedupe but re-walks
  the network. It also has no `tradable` universe: `fleet` is ~156 names, and
  `window_universe.json` does not exist so that contributor returns nothing.
- **`llm_research.PRICE_PER_MTOK` still carries the old 0.27 / 1.10 rates**
  and never imports `config.LLM_PRICE_PER_MTOK` (0.169413 / 1.284835,
  balance-derived 2026-09-05). The $30 campaign gate prices output tokens at a
  number known to be wrong. Balance on the newest receipt: **$9.28**.
- **`potential_universe.STATE_SEMANTICS`** still quotes null 1 as if the four
  states were validated, and that text is stamped into every vintage header.
  The night lab demoted the states to CANNOT_DETERMINE.
- **`alpha/fleet.py:113` cites `docs/CONTRACT_DRAFT_2026-09-06_REVISION_BOOK.md`
  in the terminal repo; that file lives in this repo**, not there. The runbook
  rows 352-361 and `D3_tuesday_rearm_audit.json:85` still say hack2 is ARMED.
- **The prediction-book seal chain is a hash log, not a linked chain**: there
  is no `prev_hash`. Tamper-evidence is self-hash plus append-only reseals.
  Fine, but the docs call it a chain.
- **There are two Genome dataclasses** (`Aegis module/aegis_brain/arena/genome.py::PortfolioGenome`
  with `distinct_from`, and `learner/growth_lab.py::Genome` with
  `parent_ids`/`mutation_history`), and `assert_distinct_from_corpses` only
  checks that a claim is ≥ 5 words. The real mechanistic comparator is
  `research_gym/scope.py::corpse_check`, which G3 does not call.
- **Both nightly vintages (tracker, potential universe) are stale at
  2026-09-02.** Any candidate-list page needs the nightly job, not just an
  endpoint.

## 3. Murat's prompt: the two approaches are one system at two authority levels

Murat frames a choice: (A) the human decides and the agent collaborates, or
(B) the agent is fully autonomous. They are not alternatives; **(A) is how (B)
gets its labels.** Every decision Murat records in (A), typed hypothesis,
entry, exit, reason, is a row the machine grades against four
counterfactuals: held to its declared horizon, held to the next scheduled
review, the engine's own pick, and SPY. That grading is the learning loop the
roadmap already calls B3 regret attribution, and it produces the one dataset
no competitor has: one investor's decisions with their reasons at decision
time. On day one (A) is "an advanced search app"; on day 200 it is a labelled
decision corpus and a calibration curve of one human against one machine.

What (A) cannot do is train a model on Murat's trades: tens of decisions per
quarter support no statistics for a year. What it can do from week one is
grade **process**: hold discipline, recall of the day's movers, calibration of
stated confidence, regret against the four counterfactuals. That is what
`alpha/recall.py` and the daily autopsy already compute for the machine.

| # | Murat's idea | Verdict | What exists / what changes |
|---|---|---|---|
| 1 | "For me it IS financial advice; I will manage my own funds with it" | RIGHT, under the standing constraint | The public README disclaimer stays. The personal path is the CAPITAL_CANDIDATE licence: attended promotion, worst case in dollars printed first, no LLM authority over real capital. Nothing relaxes. |
| 2 | Human decides, agent collaborates, and learns from my actions | RIGHT as the first product | Exists: an immutable typed decision journal (`POST /api/pi/conviction/decision`, rationale ≥ 50 chars, conviction 1-5, thesis tags, target, stop, planned exit trigger, catalyst dates, append-only corrections), a `Thesis` row with a falsifier that refuses a thesis recorded after its own catalyst (`alpha/human.py`), a sealed pre-open prediction book. Missing: **the candidate list has no web surface at all** (3,056 scorecards in a JSONL), the terminal repo has zero HTTP layer, the autopsy/recall/learning report are CLI-only. New: a HUMAN BOOK on one of the six accounts that executes Murat's journal rows, graded nightly against the four counterfactuals. |
| 3 | Learn from public tracked accounts | RIGHT, and it closes a named hole | The SEC publishes free quarterly bulk **Insider Transactions (Forms 3/4/5) since 2006 Q1** and **13F info tables since 2013 Q2**. The roadmap's "no Form 4 historical source" was wrong. The tested versions: Cohen-Malloy-Pomorski routine-vs-opportunistic insider split (82 bp/month VW in the paper); Cohen-Polk-Silli "best ideas" (each manager's max-tilt position, ~2.8-4.5%/yr). Clone ETFs (GURU, ALFA) and congress ETFs are beta; skip. eToro/Collective2 are not data we can get historically. |
| 4 | Autonomous: world news → trends → sectors → companies; analyst targets + own fair value; ~10 decisions per item; news becomes market data | RIGHT; it is VISION §4.1, and the top-down layer is the missing half | The event table and event compression are the bottom-up half. Top-down needs whole-market news (GDELT, free, 15-minute, 100+ languages, Asia-first) and CompanyWorld (B5). "Ten decisions per item" is the fantasy-exam machinery pointed at real items, each yielding a typed hypothesis with direction, horizon and precursor. |
| 5 | Backtest the same agent process from 2000 in 3-month / 6-month steps; learn the best hold and timing | RIGHT; it is B7 nearly verbatim, with one number already known | Era replay v2 exists (`scripts/era_replay_v2.py`, 2×2 naming × diary, three code-side nulls, canary; verdict NOISE on 2016-2019, blind held 768/768, $0.0025 per window). Cadence {1m, 3m, 6m} across three eras is B7 §1. The hold answer is partly in hand: hysteresis beat monthly churn in 19 of 20 rungs and halves the cost line; **as ALPHA nothing survives Holm; as a HOLDING RULE it is the cheapest improvement we own.** |
| 6 | "Made-up news" so the LLM cannot use memorised outcomes | RIGHT, and the leak test is the whole game | AMNESIA-1 (2026-08-08, 4/6 predictions) showed the instruction to forget does *nothing* (15.8% vs 15.8%) and masking held (0 of 240 identified). The literature agrees: name-masking and date-shifting alone leak; "forget after X" prompts do nothing; the clean fixes are (a) chronologically consistent models (ChronoBERT/ChronoGPT yearly checkpoints on Hugging Face, free), (b) the Gao-Jiang-Yan pre/post-cutoff accuracy test as a gate, (c) counterfactual perturbation (our fantasy exams), (d) frozen dated tool snapshots. Rule: a rewritten item is admissible only if a separate call cannot name the company or the year; the real-anon arm measures memory rather than assuming it away. |
| 7 | Accept failure; balance risk, profit and confidence; never "more confident because we have more data" | RIGHT, and it is two rules | (a) Coverage normalisation: confidence shrinks toward the base rate by evidence *quality*, never inflates with news *volume* (Benzinga 390:1). (b) The objective is expected utility at a drawdown budget: a 20%-probability, 5:1 idea outranks a 60%, 1:1 idea. The anti-over-closing device is a pre-registered **loss budget per book** ("judged at 20 positions, 8 expected to lose"); an idea is retired by the book's scoreboard, never by its own first loss. |
| 8 | Neuroscience / psychology; "presentation" matters | RIGHT as a hypothesis family, wrong as a feature | Each becomes a typed hypothesis with an observable precursor: attention (Barber-Odean abnormal volume), Robinhood/WSB herding (−4.7% over 20 days for the top-bought names), management tone (Loughran-McDonald on 8-K ex-99.1 and transcripts), scripted or evasive Q&A (Lee 2016; "Straight Talkers"), analyst boldness, capital-gains overhang. "Presents itself well" is testable as tone and Q&A spontaneity vs subsequent guidance-beat rate. Free transcripts exist from 2020. |
| 9 | Train the NN on news to find repeating patterns; unsupervised to uncover connections; the agent judges the NN's findings | HALF RIGHT | Unsupervised is representation and hypothesis *generation* (event archetypes, novelty, clusters), never a signal: the four states were demoted after failing a null, novelty is WITHIN_MODEL_NULL. The missing piece is the **route**: an unsupervised finding must be emitted as a typed hypothesis with a precursor and enter the evolution lab as a genome, where code computes every return and the corpse check runs. That route is new work; the NN is not. |
| 10 | The agent kills ideas too well; take more risk; day trading, 3-month and 6-month holds on the six accounts | RIGHT on structure | Remap the six books by **horizon and authority**, not by mechanism alone: SPY control; event/day book; 3-month hold; 6-month hold; the HUMAN book; the growth/ensemble book. Every book is PRODUCT_EXPERIMENT with a frozen contract and a loss budget. |
| 11 | Holding is what makes money; hold winners, cut companies with no future | RIGHT, with the caveat that the tape says the alpha is not there yet | Turnover 0.904 → 0.527 under hysteresis; exits become THESIS_INVALIDATED or a scheduled review, never a rank wobble. "No future" needs a machine-readable definition: revision velocity negative, guidance miss, and the admitting precursor reversed. The literature says exits are where even skilled institutions leak (Akepanidtaworn et al. 2023): the exit rule becomes a separately tested model. |
| 12 | Build the website for (A); Docker locally, not Railway; Railway for more paper accounts | RIGHT with one correction | `docker-compose.yml` already runs backend (8000) + frontend (3000) with no Railway dependency. Paper *accounts* are six by Alpaca's limit; paper *books* are not: extra experiments run as internal shadow books (zero capital, same contracts). Railway runs one loop per account. |

## 4. GPT's 17-item priority list, mapped onto the roadmap

Most of it already exists as a block; the value of the list is the order.

| GPT item | status in the roadmap |
|---|---|
| 1 finish news backfill | N4; the pull DIED, see §2; needs a resumable puller with a tradable universe |
| 2 fix clock skew and stale NAV | B2/B3 hygiene; both NOT FIXED |
| 3 Sunday fixtures | terminal hygiene; NOT FIXED |
| 4-5 decline hack4 growth; re-arm hack3/5/6 under contracts; hack1/2 manage-only | Tuesday runbook, attended |
| 6 construction + hysteresis across families | N1 DONE for ten selectors; the floor × construction cross is the named next cell |
| 7 hold-vs-sell counterfactual attribution | B3 §2 regret; needs the four-counterfactual grader (new: H-lane) |
| 8 event-driven books once news is complete | N4 books, blocked on the pull |
| 9 multi-thousand-company event ingestion | new: the puller has no tradable universe |
| 10 Form 4 and 13D/G backfill | new source found: SEC bulk sets (free) |
| 11 winner/loser autopsy | B6 |
| 12 CompanyWorld graph | B5 |
| 13 unsupervised for representation | N5 DONE as infrastructure; the hypothesis route is new |
| 14 supervised on event × company × graph × state | B10, gated on B1 + B4 + B5 |
| 15 LLM strategy lab | B8; G3 mutation proposer exists |
| 16 untouched-era + forward tests | B8 §3, standing |
| 17 capital allocator across strategies, stocks, SPY, cash | B9; v0 is SHADOW ONLY and SPY is already the parking orbit |

## 5. The five repos

The full read is in `EXTERNAL_2026-09-07_FIVE_REPOS.md`. The part that
matters for Murat's instruction to copy TradingAgents' approach:

**TradingAgents is a decision scaffold, not a strategy.** One ticker, one
date, eleven LLM calls in a fixed order (four analysts → bull/bear debate →
research manager → trader → three risk personas → portfolio manager), a
five-tier rating out. It has **no backtester, no portfolio, no sizing, no
cost model** (`backtrader` is declared and imported nowhere). Its paper's
numbers are three tickers, one quarter of 2024, one run, no costs, Sharpe
5.6-8.2 that the authors themselves flag, computed with code whose look-ahead
guards were written 15-20 months later; the README now says treat it as a
scaffold. Its "learning" is a markdown log of the last five same-ticker
episodes graded at a fixed 5-day horizon.

**What to port (Apache-2.0, runs on DeepSeek out of the box):** the verified
market snapshot that the prompt must treat as the source of truth; typed
Pydantic decision rows with a REVIEW sentinel instead of a silent Hold; the
pending → resolved decision log with an `as_of` gate on lessons; the 2-4
sentence reflection prompt; the half-open PIT date window and its six
regression tests; the stale-data refusal sentinel; instrument-identity
anchoring; message clearing between roles; the DeepSeek capability table.
And **bull/bear + research manager as a hypothesis stress-test on the ≤ 5
names the deterministic screen already chose**, run debate-off vs debate-on
as an A/B under PRODUCT_EXPERIMENT, because nothing in the repo or paper tests
whether the debate changes accuracy.

**What not to port:** the three risk personas (prose, no numbers; our worst
case in dollars is strictly better), the trader's free-text sizing, the
12-indicator menu, the fixed 5-day grading horizon, yfinance `.info`
fundamentals (not point-in-time), the Polymarket tool for historical dates
(uses today's clock), LangGraph as a dependency (ten nodes and two counters),
and the results table.

**The other four, in one line each.** `ecc` is not a trading repo; it is
Claude Code tooling, and its one useful object is a hook that refuses the
first edit of a file until concrete facts are stated. **freqtrade** (GPL-3,
reimplement from spec) has zero out-of-sample control in hyperopt, but three
things we lack: FreqAI's `do_predict` in-manifold trust flag (a row the model
scored *and* whose feature vector lies inside the training manifold), two
model-free leak detectors (`lookahead-analysis`, `recursive-analysis`) that
never read the strategy source, and the `minimal_roi` time-decayed exit curve
with a ranked exit ladder. **Vibe-Trading** (HKU, MIT, copy freely) has an
excellent multiple-testing library (DSR, PSR, BH-FDR, PBO via CSCV) and
purged/combinatorial CV wired into the *wrong* subsystem: its LLM
strategy-generation loop has no trial counter and no multiplicity correction;
its only OOS result is that 87% of 191 published alphas decayed. It also ships
a 59-line shell guard that blocks `taskkill /IM python*`, which is the code
form of CLAUDE.md rule 6. **OpenAlice** (AGPL-3, reimplement only) contains no
quant content in this checkout and its guard list defaults to empty with a
size guard that fails open; its value is plumbing: a freshness contract on
every data read, external-event-aware ledger operations, server-stamped
provenance.

**What all five have that we lack** (the appendix's §7, and the most
important sentence of the external work): a single named, versioned,
executable contract for what a strategy *is*, and one command that runs it
end to end in front of someone who was not in the session. Ours is spread
across a book YAML, a frozen contract, a farm preset, a composite weight
table and a selector function. That absence is the likeliest mechanical
reason every book still selects on 12-1 momentum. The roadmap amendment adds
a `Strategy` interface and a `run_one(strategy, universe, window, objective)
→ receipt` entry point as its own block, and ports the rest into that.

## 6. The landscape: what we most likely missed, in my order

The landscape report ranks twenty items. My ranking, by expected value per
dollar for a one-person system with our data, differs in places:

1. **SEC bulk insider data (2006-) with the routine-vs-opportunistic split.**
   Free, quarterly, ten lines of code, the most-cited insider signal, and it
   fills the Form 4 hole the roadmap thought was closed. First.
2. **The exit rule as its own tested model.** Every book inherits exits from
   its entry signal. The literature says that is where skilled institutions
   leak, and our own paper books re-entered and churned. Meta-label the sell.
3. **Buy/hold spread plus partial trading toward the aim** (Novy-Marx-Velikov,
   Garleanu-Pedersen) as the default construction, not full monthly re-sort.
   We measured the tax; this is the standard fix, and hysteresis is half of it.
4. **ChronoBERT/ChronoGPT yearly checkpoints** for any historical news scoring,
   and the pre/post-cutoff accuracy test as a CI gate on every DeepSeek-scored
   feature. This turns AMNESIA into a standing guard.
5. **MMC-style marginal contribution** of every new book against the ensemble,
   with feature neutralisation and era-boosting in the learner. It formalises
   "are its errors different errors?", which is the bottleneck sentence in
   CLAUDE.md.
6. **13F best ideas** as a separate PRODUCT_EXPERIMENT book (free data 2013-,
   45-day lag; expect small-cap momentum beta, and print it).
7. **Earnings-call Q&A scripting and evasiveness** from free transcripts
   (2020-): precursors by construction, and the exact form of Murat's
   "presentation" hypothesis.
8. **GDELT** as the whole-market, Asia-first denominator the VISION file asks
   for. Coverage normalisation needs a denominator; Benzinga is not one.
9. **Qlib Alpha158** as a breadth baseline against the one-factor composite,
   and **FINRA short interest** (free, bi-monthly) as a missing feature.
10. **A public read-only cockpit with one worked decision and its rejected
    alternatives** at the top of every write-up. Every well-received hackathon
    entry had it; the judges marked entries without it as "idea level".

Deprioritise: zero-shot time-series foundation models for returns (beat a
random walk in 2 of 10 tests), RL as an alpha source, clone and congress ETFs,
paid alternative data, and multi-agent LLM stacks as alpha (LiveTradeBench's
finding: agent *architecture* moved results more than swapping the model,
which supports the DeepSeek-only stance).

## 7. What changes in the roadmap (summary; the amendment has the blocks)

1. **The four-stage decomposition** becomes a strategic invariant, and every
   book receipt reports where information died (IC, TC, breadth, hold, exit).
2. **Mode A ships first** (H-lane): candidate list, journal, human book,
   four-counterfactual regret, local Docker. It is the labelled data for Mode B.
3. **The six books are remapped by horizon and authority** with loss budgets.
4. **Investor data lane (I)**: SEC insider bulk, 13F best ideas, 13D/G via
   EDGAR index, all free.
5. **B7 era replay v2 runs Murat's design** at {1m, 3m, 6m} across three eras
   with ChronoBERT as a second decider family and the leak test as a gate.
6. **The unsupervised → hypothesis → genome route** is built (N5 → B8).
7. **TradingAgents' decision scaffold** is ported as typed rows, a decision
   log and a debate A/B; nothing from it touches sizing.
8. **Hygiene with owners and tests**: clock skew, stale NAV, Sunday fixtures,
   `verdict_from`, ERAS callers, the price table in `llm_research`,
   `STATE_SEMANTICS`, the stale doc numbers in §1 and §2, the dead backfill.

## 8. Claims in this review for the builder to attack

1. That Mode A produces labels Mode B can use within a quarter. It may only
   produce process metrics; the roadmap says so, but check the row schema
   actually supports the four counterfactuals before building the page.
2. That the SEC insider split reproduces on our CRSP tape at all. The paper
   is 1989-2007; the roadmap treats it as a PRODUCT_EXPERIMENT, not a claim.
3. That ChronoBERT's yearly checkpoints are usable as a *decider* rather than
   an embedder on our hardware. If not, it is the memory control only.
4. That the buy/hold spread is not just hysteresis renamed. It is hysteresis
   plus partial trading; the second half is untested here.
5. That the debate A/B is worth $3. If the deterministic screen's top five
   are the same five with and without debate, the answer is no, and cheaply.
