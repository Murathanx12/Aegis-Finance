# Funding evidence pack (2026-10-07)

**Status: the filing version.** Promoted from `FUNDING_EVIDENCE_PACK_2026-10-07_DRAFT.md` (a Sonnet
research draft) by the C23 documentation pass. Every number below was checked against the receipt it
names: the file was opened and the number found there. Where it was not, the line says **NOT MEASURED**
and names the receipt that would hold it. Corrections against the draft are listed in
`docs/research_notes/2026-10-07/documentation_pass_2026-10-07.md`. Receipt paths are relative to
`backend/data/optimus/` unless they start with `docs/` or name a top-level file.

Every number carries an evidence label: `OBSERVED(n)` (measured over n sessions; a fact, not skill) ·
`EARLY_EVIDENCE` · `REPLICATED` · `VALIDATED_EDGE` · `BACKTEST-ONLY` · `ARMED` (built, nothing accrued) ·
`NOT MEASURED`. The ladder is defined in `docs/AEGIS_V1_BETA_2026-10-07.md` §4.

**RESULT IMPROVEMENT: NONE.** Nothing in this repository beats the market after costs on a declared
read, historically or forward. This pack asks for support for an instrument, not for a return.

---

## 1. Problem and product (one page)

**Positioning:**

> Aegis is **auditable AI investment intelligence**: a system that records which information changed a
> decision, freezes the alternatives it rejected, grades itself against what actually happened, and
> learns only from graded outcomes.

This is not "an AI that predicts crashes" (the March 2026 CUPP pitch, which the project's own later
result contradicts: the signal-engine timing strategy returned +28.3% against SPY's +114.8%
over 2020-01 to 2025-06; `backend/BACKTEST_RESULTS.md`, `NEGATIVE_RESULTS.md` §1). It is not "autonomous
returns" either.

**The problem.** AI investing products ask the user to trust a black box. Of about 21 products the
project surveyed, none publishes independently audited, cost-inclusive forward evidence against SPY;
only Danelfin and Numerai grade their own calls at all (`docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md`
§8-§9). Aegis writes down what it believes before the outcome exists, freezes that belief, and grades it
later, by construction: it is the thing paper capital is sized against, not a feature that could be
switched off (strategy doc §1).

**What the product is today:** a forecast → paper decision → outcome → attribution → re-weighting loop on
real market data, every stage logged and gradeable; a public, append-only forward record since
2026-06-08; a public record of what did not work (`NEGATIVE_RESULTS.md`, 3,855 lines); and a web page
that shows direction, magnitude and the evidence label side by side (`/opportunities`).

**What it is not, on current evidence:** a system that beats the market.

---

## 2. What exists and runs today

Label for this section: `OBSERVED`, read from the machine state on 2026-10-06/07.

### 2.1 Sensors

| sensor | number | as of | receipt |
|---|---|---|---|
| news corpus (`news_pull`) | 75,889 rows, 18 sources | 2026-09-26 | `docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` §2 |
| news collectors, recent | 628 new rows over 29 sources in the probe window; 30 of 32 sources wrote within 3 days | 2026-10-06T17:53Z | `health/health_20261006T175305Z.json` (row `news_collectors`) |
| dated analyst revisions (`pull_analyst_targets`) | about 393k | 2026-09-26 | strategy doc §2 |
| analyst pull, daily | 3,091 snapshots of 3,210, 0 failed | 2026-10-06 | `health/health_20261006T175305Z.json` (row `task:AegisAnalystPull`) |
| SEC fundamentals + `derive_q4` | 59,296 quarterly rows that XBRL never tags | 2026-09-24 | `docs/HANDOFF_2026-09-24_THE_LEDGER_WAS_THE_ANSWER.md` |
| `thesis_cards` / catalyst YAML | 84 cards / 31 rows | 2026-09-26 | strategy doc §2 |
| public-flow sensors (C16, new) | USAspending 2,059 contract transactions (10 recipients, 90 days), median 41 days from action to first sight; Senate LDA REFUSED (403); crypto risk sensor 1 snapshot | 2026-10-06T21:50Z | `public_flow/receipts/usaspending_20261006T215032Z.json`; `public_flow/receipts/senate_lda_20261006T215232Z.json` |
| OpenClaw reader | read-only browser profile, 18 denied domains; 10 tool calls in 24 h, 0 outside the read set | 2026-10-06 | strategy doc §5 table; `health/health_20261006T175305Z.json` (row `openclaw_tool_scope`) |
| data catalog (C10) | 4,742 datasets, 61 replay groups | 2026-10-06T18:06Z | `data_catalog/catalog_20261006T180640Z.json` (`summary`) |

### 2.2 The reader's yield

- **7 days to 2026-10-06:** 9,368 page loads (9,022 OK) → **238 claims** → **3,587 forecast rows**.
  `OBSERVED(7 days)`. Receipt: `docs/research_notes/2026-10-06/openclaw_open_web_and_model_audit_2026-10-06.md`
  (results table, read from `dowjones/budget_lanes.jsonl` and the claims ledger).
- **Forecast ledger since 2026-08-11:** 25,329 rows, 17,650 graded (as of 2026-09-26; strategy doc §3).
- **On 2026-10-06:** 766 new forecast rows in 10.5 hours, 137 due and unresolved (roadmap §0, row
  "Graders", citing `night_factory_2026-10-06/daily_pass_2026-10-06.json`).
- **Disclosed, not smoothed over:** before the 10-06 session the **live decision loop** had not run a sim
  session for 6.7 days (since 2026-09-29), and the `dowjones_feeds` receipt was 9.1 days stale because it
  had no scheduled caller. The reader itself was running. Both are fixed or owned now (roadmap §0;
  `docs/research_notes/2026-10-06/pc_paper_mandate_and_sim_owner_2026-10-06.md`).

### 2.3 The paper estate, with its honest count

Receipt for this section: `paper_accounts/roi_2026-10-06T163850Z.json` (generated 2026-10-06T16:38:50Z)
and `paper_accounts/book_dna_2026-10-06T163850Z.json`.

- **362 priced paper books**; of 307 with an own-window SPY leg, **147 ahead of SPY, 160 behind**.
  (The earlier receipt of the same day, `roi_2026-10-06T045934Z.json`, which the roadmap quotes, read
  148 / 159.)
- **The honest count:** 147 ahead = 108 control twins + 3 controls + 36 strategy books; the strategy
  books are about **2.6 ex-ante bets** (4.6 net of SPY). **One book with at least 21 sessions is ahead of
  SPY:** hack2, +1.14 pp over 26 sessions. MU appears in 17 of 33 strategy-winner books (`summary.tilt`).
- **Every one of the 362 books is labelled `OBSERVED(n)`; none reaches `EARLY_EVIDENCE`.** hack2 cannot,
  yet: its daily series covers 6 of its 26 sessions, so its sub-windows are not computable
  (`books[account=hack2].evidence`).
- By family: website lanes −2.74%; Alpaca fleet −9.17% (5 priced); PC-PAPER +0.27%; night books +3.03%,
  their twins −1.11%; excluding control twins (91 books) +1.585% (`aggregate.by_family`).

### 2.4 The live loop, its owner and its worst-case gate

- A scheduled owner (`AegisSimOwner`) starts a paper session on US trading days; on 2026-10-06 session
  `b7b5981048e5` was RUNNING (`health/health_20261006T175305Z.json`, row `sim_session`).
- The contract's capital is read from broker equity: **$1,002,662** (`pc_mandate/reconcile_2026-10-06_147824639837.json`,
  `capital_reconciliation.capital_status: OK`).
- **Worst case in dollars**, priced on the names the sleeve would buy: **14.08% of equity (−$141,178)**
  against a 10% limit, so EXPLOIT is capped at **54.38%** gross every cycle (same receipt,
  `worst_case_gate`). Priced at the universe median it would have read 7.53% and passed; the reviewer of
  this chunk caught that.
- **Still UNRECONCILED:** the contract resolves 99.75% to a benchmark core, while the broker holds 79.85%
  cash and 20.15% in 10 names; three agency sleeves are sized at $40,000 rather than their share of $1M
  (same receipt, `positions_reconciliation`). This week the account does almost nothing, by design.

### 2.5 The twin controls

Every result is read against a matched twin, not a bare benchmark. On 2026-10-06/07 the monthly "basket"
twin was joined by a **sticky twin** that shares its rule's turnover by construction and pays the same
cost model. On CRSP 1991-2024 (`hyp_lab/twin_board_SUMMARY_STK_2026-10-07_2.json`, `summary`): 301 rules,
277 scored, 24 refused by name; **44** reach fair-twin t >= 2; **40** of those also pass pure selection;
**1** (`qc761_ebit_ev_ebit_ic_large_annual`) also beats the market in validation (2009-2016), and its
pure-selection t there is 1.16 with 2009 carrying its market line
(`docs/research_notes/2026-10-06/sticky_twin_2026-10-06.md`). **Historical alpha on CRSP: not
demonstrated.** Label: `BACKTEST-ONLY`.

### 2.6 The decision story and regret ledger

Every decision is frozen with its rejected alternatives (buy default, buy half, buy double capped, enter
next open, exit now, next-ranked name, leave one source out) before the outcome is known, keyed to the
session it could first trade, sealed with a sha256, and graded later with signed regret by type against a
null (`docs/research_notes/2026-10-06/decision_story_and_regret_2026-10-06.md`). Its reviewer scored it
56/100 and found three of six regret types biased positive by construction; they were rebuilt as signed
differences (`docs/reviews/REVIEW_2026-10-06_C11_DECISION_STORY_REGRET.md`). **Status: `ARMED`.** No live
story exists: the 10-06 session loaded the old `u_plan`.

### 2.7 Health

Health reads each scheduled job's own receipt, not the wrapper's exit code: unknown `task:*` rows went
from 17 to 0 (`docs/research_notes/2026-10-06/progress_aware_health_2026-10-06.md`). At
2026-10-06T17:53Z the probe read 0 DEAD, 8 STALE, 3 DEGRADED, 4 UNKNOWN, 13 stopped by the operator, 42
alive (`health/health_20261006T175305Z.json`, `state_counts`). A stale output reads STALE even while its
process is alive: that is the fix for the failure that let the candidate funnel run 44 days stale while
reporting "ok" in September (`CLAUDE.md`, "THE REAL BOTTLENECK WAS A STATIC FILE").

### 2.8 Architecture

The pipeline diagram, with every box's live module and receipt, is in `docs/AEGIS_V1_BETA_2026-10-07.md`
§2. In short: sensors → evidence → forecasts → decision → paper execution → outcomes → attribution →
learning, and the learning stage may only change preferences and weights; gates only shrink.

---

## 3. A reproducible Decision Story (dry run)

One real dry example, as of 2026-10-06, observe mode, order submission disabled
(`docs/research_notes/2026-10-06/decision_story_and_regret_2026-10-06.md`, "One real dry example"). It is
the mechanism exercised end to end; it is not yet an order-connected story.

- **Timing:** session 2026-10-06, entry at the close (decided during the session). 51 candidates, 51
  stories, 746 frozen alternatives (14.6 per decision). Replay **MATCHES** (a drifted replay prints
  `replay MISMATCH`, a tested failure mode). Order-gate scale 1.0.
- **Cohorts:** ranker_pool 22 · shortlist_not_taken 13 · held_resize 10 · picked_blocked 6.
- **Example, NVDA (PROBE, HOLD, cohort held_resize).** The figures are the **position weight under each
  alternative**, frozen before any outcome exists; their outcomes are graded later:
  - actual / no trade / hold: 2.108%
  - plan as written (buy default): 2.00%
  - buy half / buy double (capped): 1.05% / 4.22%
  - enter next open: 2.108%
  - exit now: 0
  - next-ranked name: HNI at 2.108%
  - plan plus the shadow-news tilt at its earned trust: 2.0026% (at full trust: 2.362%)
  - leave one source out: news IDENTICAL_NOT_READ; analyst, regime, LLM 2.00%; price momentum
    NOT_SEPARABLE (the funnel filter is not re-run in the dry replay)
- **Every chain record carries** event ids → evidence ids → forecast ids → decision id → order or
  abstention id → outcome ids → attribution ids, a sha256 seal and six latency stamps.
- **When a live story from 2026-10-06 would grade:** h5 2026-10-13, h21 2026-11-04, h63 2027-01-06. The
  real first grade is five sessions after the first session on the new `u_plan`.

For a reviewer, the point is that these ids are the chain itself, which can be pulled and replayed against
the frozen alternatives; the replay check is a guard against silent drift.

---

## 4. Track record, honestly

Receipt for every row unless stated: `paper_accounts/roi_2026-10-06T163850Z.json` (`rows`). None of
these is a claim that Aegis beats the market; nothing here holds the `RESEARCH_CLAIM` licence.

| line | number | label | what it can claim | what it cannot claim |
|---|---|---|---|---|
| Website lanes (10, since June) | vs SPY over own window: tsmom-overlay −1.39 pp (+3.71%), conservative-atr −1.76 pp (+3.34%), aggressive −3.35 pp (+1.99%), balanced −5.03 pp, conservative −5.17 pp, balanced-ew-control −7.16 pp, tsmom-6040-control −5.16 pp, smallmid-quality −7.40 pp, conviction −12.86 pp, mirror −28.26 pp (−24.48%) | `OBSERVED(n)` | the record exists, is append-only, configs are hash-pinned | skill; **all ten are behind SPY** |
| Alpaca fleet (since 2026-08-28) | hack2 +2.57% (+1.14 pp vs SPY), hack5 −3.61%, hack1 −6.58%, hack6 −18.46%, hack4 −19.76%; hack3 CREDENTIAL_INVALID | `OBSERVED(26)` for hack2 | hack2 is the only book in the 362 old enough and ahead enough to approach a higher label | it is not `EARLY_EVIDENCE` (sub-windows not computable) and is one observation |
| PC-PAPER ($1M paper, since 2026-09-22) | +0.27% vs SPY +0.86% (−0.60 pp), 79.85% cash | `OBSERVED(n)` | the mandate and the worst-case gate run as designed | selection: with 80% cash the sign follows SPY |
| CRSP historical (sticky twin) | 1 of 277 rules beats the market in validation and fails pure selection there | `BACKTEST-ONLY` | the method (turnover-matched twin, declared before the read) is research discipline | **historical alpha on CRSP is not demonstrated** |
| nn_lab tournament | the network does not beat ridge or LightGBM at any horizon (`nn_lab/receipts/wf_20261007T_c5_review.json`; `docs/research_notes/2026-10-06/nn_lab_membership_freeze_2026-10-06.md`) | `OBSERVED` | a leakage-controlled tournament with a membership freeze | no model holds forward weight |
| book_dna collapse | 147 "ahead" → about 2.6 ex-ante bets | `OBSERVED` | the project measures and discloses its own double counting | the bets are too young (most winners have 5 to 16 sessions) to be evidence |

**The sentence a funder should leave with:** this project has built the instrument that would catch it
lying to itself about an edge, has used it on its own best candidates, and reported "not demonstrated".

---

## 5. Competitions

### 5.1 Alpaca hackathon (execution repo `aegis-alpha-terminal`, public as `investing-bot-test-`)

Six paper books ran on Alpaca from 2026-08-28. **What went wrong:** hack3's key stopped answering (HTTP
401) and the account was retired on 2026-09-22; it is reported as `CREDENTIAL_INVALID`, never as $0
(README track-record notes). That was an unmanaged credential, not a strategy verdict. Of the five live
accounts only hack2 is ahead of SPY (§4). The hackathon's winners kept capital authority in deterministic
code, as Aegis does (roadmap §2 item 11; `docs/research_notes/2026-10-06/borrow_from_outside_2026-10-06.md`).

### 5.2 Bloomberg Global Trading Challenge 2026

**Registration closed at 11:59 pm on 2026-10-04 New York time (11:59 am 2026-10-05 HKT). Whether the team
registered is unknown to the machine** (`docs/research_notes/2026-10-06/funding_and_contest_status_2026-10-06.md`
§B; owner decision D1). The challenge runs 2026-10-12 to 2026-11-13 (New York time).

Three rehearsal books are frozen with hashes covering code and rule: ROT5_TRAIL, ROT5_DIR v2, MAXTAIL_BH v2
(MAXTAIL_EVT v1 declared) (`contest/rehearsal/freeze_log.jsonl`). The runbook recommends ROT5_TRAIL at low
commissions and MAXTAIL_BH at higher ones; **ROT5_DIR is not recommended**: in the reviewer's event replay
its direction filter drops 28.1% of top-5 slots and trades right tail for left-tail protection. That replay
lives in the review only and has not been re-derived into a receipt
(`docs/research_notes/2026-10-06/contest_direction_sheet_2026-10-06.md`). The live desk refuses to trade
without both a `contest/REGISTERED` marker and a WLS `MEMB` export.

---

## 6. Costs

- **The owner's figure of ~$1,500 over six months: NOT MEASURED.** No receipt reconciles to it. The
  receipts that would hold it: the DeepSeek top-up history (the provider's billing page, not in the repo),
  the Railway invoices (not in the repo), and any other subscriptions.
- **DeepSeek (the only LLM provider), provider-measured:** balance **$17.87** at 2026-10-06T22:44:42Z,
  read by `python -m scripts.llm_cost_audit --snapshot` on 2026-10-07 and appended to
  `deepseek_balance.jsonl` (label `cost_audit`). From 2026-09-27T06:45Z ($33.90) to that read the balance
  fell **$16.03** with no top-up inside the window (the series is non-increasing), about $1.65 per day.
  `OBSERVED`.
- **DeepSeek, telemetry-measured, October ledger:** $3.4973 over 2,991 priced calls since 2026-10-06, of
  which INTERNET-INVESTIGATOR-FWD-1 $2.45 and the world digest about $0.73 (same command, ledger
  `llm_calls_2026-10.jsonl`). The script's own provider-vs-telemetry line reads DISAGREE because it compares
  telemetry since the start of 10-06 with the balance since a snapshot 13 minutes earlier; that window
  mismatch is a known defect, not a top-up (see the documentation-pass note).
- **Railway:** Pro plan, $20 per month including $20 of usage (`docs/REVIEW_2026-09-26_RAILWAY_COST.md`). Usage of **$48.05 for 2026-08-26 → 09-20**
  (about 25 days; memory $25.20, CPU $20.52) is quoted from the owner's bill in
  `docs/REVIEW_2026-09-26_RAILWAY_COST.md`; the bill is not a repo receipt. One paper loop was stopped and
  the website's start command trimmed on 2026-09-28 (`docs/NOTE_2026-09-28_RAILWAY_COST.md`). Current
  monthly bill: **NOT MEASURED** in the repo.
- **Local models:** the desktop build can run a local model through llama-server at $0 marginal LLM cost
  (measured 2026-09-10, `docs/HANDOFF_2026-09-10_THE_REPLAY_AND_THE_EXE.md`). Which desktop features run
  offline without any key is chunk C24's acceptance and is not yet receipted.

---

## 7. Compliance and safety stance

- **Paper only.** Every book trades under `PRODUCT_EXPERIMENT`: internal simulation or an external paper
  brokerage. `CAPITAL_CANDIDATE` would permit candidacy for real money, with promotion attended by a
  human; nothing holds it today.
- **No LLM authority over real capital**, a standing rule (README, "Three licences"). LLM-proposed books
  trade only in paper under frozen contracts (roadmap §2 item 11).
- **An LLM proposes; deterministic code sizes, stops and exits; gates only shrink** (roadmap §7). Any code
  change a model proposes goes branch → tests → adversarial review → owner gate. The worst-case gate in
  §2.4 is an example running in the live loop.
- **Read-only browsing** in a dedicated browser profile with 18 denied domains; no transactions, sign-ups
  or form submissions without an explicit owner decision (open: D7 sign-ups, D15 a paid search provider).
- **No payments, no messages or emails without asking** (operating model, roadmap header).
- **Lawfully public information only**, with first-public and first-detected timestamps recorded so latency
  is measured and disclosed (roadmap §2 item 9). Identity groups are never a variable (roadmap §7).

---

## 8. Customers (three hypotheses) and a 6-12 month roadmap

### 8.1 Three candidate customers

All three are hypotheses. **There are zero paying users today** (strategy doc §9).

1. **The sophisticated investor who wants a machine to beat SPY hands-off, and will trust only one that
   shows its work** (persona P2). On the project's own scoring (21 competitors, ten criteria, 0-3 each)
   Aegis leads on paper (12) over Danelfin (11) and Numerai (9), but scores 1/3 on the one criterion this
   customer pays for, forward cost-inclusive evidence vs SPY (strategy doc §9).
   **Falsifier:** if, once the decision story and regret ledger have run live for a full quarter, this
   customer still will not pay without a demonstrated edge (which cannot exist before the 24-month forward
   floor, June 2028 at the earliest for the oldest lanes), auditability alone does not convert this
   segment, and the product should move toward hypothesis 3.
2. **The person who does not know how to invest and wants something that explains itself in plain
   language before it asks for money** (persona P1). Aegis ties incumbents on substance and scores 0/3 on
   accessibility (strategy doc §9); the Telegram cockpit (C6) is a first plain-language surface.
   **Falsifier:** if a usable novice interface is built and a small cohort of non-expert users does not
   return after the first week, or cannot say what the system told them and why, the information is not
   the blocker; UX and trust are a separate, harder problem than this project funds.
3. **A compliance-minded quant desk, research group or RIA that needs an auditable decision trail**, buying
   the method (frozen beliefs, frozen alternatives, signed regret, evidence labels) rather than a signal.
   This segment is this pack's own hypothesis: **NOT MEASURED** (no competitor comparison, pricing research
   or outreach exists in the repo). **Falsifier:** if none of 3-5 such desks or groups engages after this
   pack is shared directly, the segment is too small to build for, and the infrastructure stays open-source
   (MIT, the current default) for its reputation and recruiting value.

### 8.2 The next 6-12 months (gated on evidence, not on engineering)

| item | gate | earliest date |
|---|---|---|
| digest forecast rows graded | 5-session window | 2026-10-09 |
| SHADOW_NEWS trust may leave 0 | 3 graded dates | ~2026-10-11 |
| straddle forward lane, first entry | scheduled | 2026-10-16 |
| first live decision story graded at h5 | 5 sessions after the first session on the new `u_plan` | after the merge |
| LIB-FWD-TWIN-1 early-kill check | 21 sessions | 2026-10-26 |
| CRSP_BLEND_v0 / SHADOW_BAYES_v1 first read | session 21 | ~2026-10-27 |
| regime-classification trust | graded digest dates | after 2026-10-09 |
| contextual bandit over source and policy weights | 63 sessions of regret rows | early 2027 at the earliest |
| BLPAPI read-only bridge | owner's terminal access + licence | owner-gated |
| LEAN replication of one finalist | a finalist + free survivor-aware data | deferred (no finalist) |
| six-role fleet reset | owner's broker-UI act (D2) | owner-gated |
| **first claim-eligible forward record** | 24-month floor | **not before June 2028** |

Money buys more sensors, more compute and more builder hours. It cannot move the 24-month clock, and this
pack does not pretend otherwise.

---

## 9. Which programmes, and when

Fetched live on 2026-10-06 (`docs/research_notes/2026-10-06/funding_and_contest_status_2026-10-06.md` §A).
**Every confirmed near-term cash-grant intake checked is already closed.**

| programme | status (2026-10-06) | action |
|---|---|---|
| Cyberport Creative Micro Fund (CCMF), HK$100,000 | Mar 2026 intake closed 2 Jan 2026; Jun 2026 intake closed 1 Apr 2026; next intake **UNVERIFIED** | **Write to the Cyberport programme office** this quarter: when does the next round open, and is a late or rolling application possible? |
| Cyberport University Partnership Programme (CUPP), via HKU | 2026 HKU nomination closed 2 Mar 2026; CUPP 2027 not posted (expect ~Mar 2027, **UNVERIFIED**) | Watch the HKU TEC CUPP page; **write to the HKU TEC office** to ask for the 2027 timeline |
| HKSTP Ideation Programme, up to HK$100,000 | Cohort 26-23 window closed 14 Sep 2026; next window ~Jan 2027, **UNVERIFIED** | **Write to the HKSTP programme office**; confirm on the programme page before the next push |
| **HKU Demo Day x Innovation Week 2026** | **2026-10-14**; a showcase slot, not a grant; submission process **UNVERIFIED** | Use it as the showcase: the V1 Beta document, the Opportunity Explorer and a Decision Story chain. Do not present the March crash-prediction pitch |
| HKU International Techno-Entrepreneurship Challenge | 2026 edition closed 21 Jun 2026 | Watch the 2027 edition |

**Recommendation:** do not wait for an intake to be announced. Write to the Cyberport and HKSTP programme
offices now, and use HKU Demo Day on 2026-10-14 to build relationships for the next window.

---

## 10. Public and internal material

**Public (link, do not rewrite):** `README.md`; `docs/AEGIS_V1_BETA_2026-10-07.md` (the story, the pipeline,
the acceptance table); `docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md`; roadmap §9 (quote it: it says
plainly that beating SPY is not the bar); `NEGATIVE_RESULTS.md`; this pack.

**Internal (stays off a funder's desk):** dated handoffs and research notes (a funder gets the synthesis
here); the owner-decision tables until resolved; raw receipt JSON (link it, do not paste it); anything
under `backend/data/optimus/local_pc/` (machine details, excluded from git).

**Visuals still owed** (none exists yet; each is a fresh screenshot on the filing date, never a mockup):
the Opportunity Explorer (`/opportunities`, built); the Paper Arena (`/arena`, chunk C19, not yet in the
app); the Decision Story chain (the §3 example, or a live one once it exists, drawn as event → evidence →
forecast → decision → order or abstention → outcome → attribution with the frozen alternatives beside it);
the health board (ALIVE / STALE / DEAD across sensors, graders, the live loop and nn_lab).

---

## What could not be sourced

- The owner's "~$1,500 over six months": **NOT MEASURED** (§6).
- The current monthly Railway bill: **NOT MEASURED**; the last figure in the repo covers 08-26 → 09-20 (§6).
- Bloomberg registration: owner-only information (D1).
- Market sizing, pricing or outreach for customer hypothesis 3: **NOT MEASURED**.
- The ROT5_DIR event replay: in a review, not in a receipt (§5.2).
- Desktop offline behaviour without keys: chunk C24, not yet receipted (§6).
