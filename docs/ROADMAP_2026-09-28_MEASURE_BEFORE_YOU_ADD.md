# ROADMAP 2026-09-28 — MEASURE BEFORE YOU ADD

TIER 1. Supersedes `ROADMAP_2026-09-25_CONNECT_WHAT_EXISTS.md` as the current lane list.
Gates outrank dates. Licence of every item: `PRODUCT_EXPERIMENT` unless it says otherwise.

Built from five reads on 2026-09-28, each with its own file:

| Read | Model | File |
|---|---|---|
| OpenClaw runtime | Sonnet | `docs/research_notes/2026-09-28/openclaw_runtime_done_right_2026-09-28.md` |
| Fact check of backtests and paper accounts | Sonnet | `docs/research_notes/2026-09-28/fact_check_backtests_and_paper_accounts_2026-09-28.md` |
| Outside methods compared | Sonnet | `docs/research_notes/2026-09-28/outside_methods_compared_2026-09-28.md` |
| Signal alerts design | Sonnet | `docs/research_notes/2026-09-28/signal_alerts_design_2026-09-28.md` |
| Adversarial investor | Opus 5.5 | `docs/reviews/REVIEW_2026-09-28_ADVERSARIAL_INVESTOR_ON_THE_PROJECT_AND_ITS_REVIEWER.md` |

An outside model's review (pasted by Murat) was the trigger. Its claims were checked, not adopted.

## 0. RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** Demonstrated net edge on disk: **none**.

| Line | Value | Receipt |
|---|---|---|
| Best historical rule | `mom_12_1_q` +1,323% since 2020 vs SPY +162% — and it is ONE of three quarterly calendars (+37.9 vs −5.0 vs +8.4 pp); monthly 12-1 is +692% | leaderboard `T164302Z`, `SIGNAL_STRUCTURE_2026-09-26.md` |
| Rules surviving all six checks | **0** | fact check §A |
| Top deflated Sharpe | 0.198 (bar 0.95); best family `weighted` 0.83 | same |
| Median rule vs its matched twin, 2024-26 | −0.2% | same |
| Ten dev-selected rules vs matched twins, 2024-26 | median −1.45 pp/yr; 2 of 10 ahead, both on the lucky calendar | adversarial review |
| Paper accounts | 33 priced, 6 ahead of SPY, 27 behind, aggregate −0.27% | `roi_2026-09-27.json` (23:51Z) |
| Frozen forward books | 62; with zero skill the best one looks like a 2σ result in a month with probability 46% | adversarial review §4 |
| Forward books graded | 0 (first grade Tue 2026-09-29) | — |
| Dow Jones sources | every cell `TOO_FEW` (9 publication dates of ~110) | `source_scorecard_2026-09-28_000228.json` |
| Investigator vs a free volatility formula | +5.7% vs +10.2% on magnitude | adversarial review |
| Scores out of 100 | outside reviewer 72 overall; adversarial reviewer 30 | both files |

The two scores differ because one graded the machinery and the other graded the evidence.
Both are opinions. The table above is the evidence.

## 1. The rule this roadmap is built on

> **No new signal, source, book or account until an existing one has been measured against
> its matched control on data it did not choose.** A module that can only print
> "cannot distinguish" for six months is not roadmap work.

Consequences, each decided by a read above:

- **Marginal Decision Contribution is NOT tier 0.** It costs 3–5 days to build and is
  estimable only for analyst revisions and, at large-effect resolution, strategy rules.
  Conditioning on correlated rules RAISES the detectable effect from 2.46%/mo to
  4.1–7.9%/mo. Status: `DEPRIORITIZED` until the forward books have 63 sessions.
- **Seven new paper accounts are NOT launched.** With 62 books already frozen, seven more
  are seven more lottery tickets. No new book for 21 sessions (to 2026-10-26).
- **TradingAgents, Qlib / RD-Agent, a paid mlfinlab licence: not adopted.** Reasons in the
  methods note (a confirmed look-ahead leak; no free US data; tools already built here).

## 2. Lanes

### LANE O — OpenClaw runs properly (BUILD NOW)
Gate to start: none. Gate to finish: a kill test passes and no profile can reach the main Chrome.

| Step | What | Needs Murat |
|---|---|---|
| O1 | OpenClaw's only browser = the separate Chrome at `C:\Users\mrthn\ChromeMuratClaw`, attach-only on a 127.0.0.1 port. The `user` and `chrome` profiles are disabled. | sign in once in that window |
| O2 | The supervisor can detect a jammed gateway and repair it (probe → lighter reset → restart → wait for the port → one attach), at most 3 per hour, with backoff, distinguishing "reader crashed" from "dependency down" | no |
| O3 | Browser verbs over the gateway's HTTP route, one persistent client, with EVERY guard of `openclaw_client` re-applied on that path (site allowlist, denied domains, own-tab rule, host check before and after, pacing) | no |
| O4 | OpenClaw's tool profile restricted (it is `full` today on a machine that holds paper-account keys): restricted profile, shell on an allowlist | confirm |
| O5 | A yield check on every reader run: after ten pages print links per page and characters per page; an all-zero lane refuses | no |
| O6 | Reading pace restored to 20–90 s / 60 s same host unless Murat says otherwise | decide |

**Paid sites** (WSJ, Barron's, MarketWatch): read only on Murat's explicit hand-over or by
paste. Dow Jones terms §9.4.1 bar automated access. "Always on" means the gateway and the
free lanes, not a crawler on a paid account.

### LANE A — Alerts to Telegram, smallest version (BUILD NOW)
Gate to start: none. The bot is live and has sent nothing since 2026-09-23 because its send
job has no scheduled caller.

- A1: a scheduled caller for the existing send path.
- A2: INFO-level alerts only, rendered from fields already computed. No new LLM cost.
- A3: every alert is a frozen, timestamped row with the price at that moment, written
  BEFORE it is sent. Rewrites of one fact make one alert. Daily cap. Quiet hours.
- A4: each alert states what is new, the primary source, whether the price already moved
  (in sigma), what contradicts it, and what is not known.
- **Gate for THESIS_CHANGE / SIGNAL_CANDIDATE levels:** ≥ 100 independent alert dates graded.
- **Kill rule:** at 100 alert dates, if graded alerts do not beat their matched control, the
  stream becomes a daily digest.
- X, Reddit and StockTwits never generate an order. No LLM has authority over capital.

### LANE M — Measurement honesty (BUILD NOW)
- M1: quarterly-offset triplet on `disp_short_avoid`, `qc470_mom252_quarterly_riskparity`,
  `mom_12_1_q_trend`. A lead whose other two calendars do not beat their matched twins is
  relabelled a calendar artefact.
- M2: the leaderboard prints the matched-twin and family verdict BESIDE every headline
  number. A large figure is never shown alone.
- M3: a staleness probe on the backtest leaderboard; the factory gets a scheduled caller.
- M4: correct the record: the stale "39 priced / −1.31%" in three docs; the rehearsal and
  core-satellite book docs cite the closure of the fundamentals tilt (−1.34% per 21
  sessions, t −2.55, commit `3255206b`); the TIER 0 pitch prints the volatility prior
  beside +8.97%.
- M5: the scheduled daily pass prices the legacy Alpaca and PC paper accounts into a
  receipt (it runs `--no-broker` today, so those numbers exist only in prose).
- M6: pre-register the ONE forward comparison: the library bets vs their matched twins,
  pooled by cluster, z at 21 and 63 sessions, with the luck table beside it and a kill rule.

### LANE P — The paper money path (VERIFY FIRST, THEN BUILD)
Claims from the adversarial review, each to be verified before any change:
- P1: every decision contract prints mandate `REFUSED` and PROBE orders go out anyway.
  (PROBE was promoted at contract level on 2026-09-21; this may be by design. Verify.)
- P2: the shortlist holds both GOOG and GOOGL.
- P3: the expected-return layer has 0 graded dates on all inputs, so the `policy_state`
  read changes nothing.
- P4: worst case on the largest admissible book, printed in dollars before any change
  (session protocol item 4).

### LANE B — Bloomberg challenge (MURAT DECIDES)
Register by **Oct 5**. Oct 12 – Nov 13. One draw, relative P&L, 20% position cap.
- The adversarial reviewer: the rehearsal book (10 × 10%, fundamentals tilt, US only) has
  roughly 0.5–3% chance of a top placing; five names × 20%, one theme, dated catalysts, no
  stops has roughly 15–25%. These are normal-approximation estimates, UNVERIFIED.
- This is a choice of UTILITY, not of skill: a contest pays for variance. It is Murat's
  declared preference to make, in one written line, before any book is built.
- Owed whatever he chooses: confirm registration; export WLS membership.

### LANE X — Two cheap experiments, each with a stop (AFTER O, A, M)
- X1 StockBench rerun on our DeepSeek setup. Stop: one run, one table.
- X2 Kronos (free price-history model). Prior: we measured that price and volume cannot
  rank at 21 sessions after costs. Stop: if it does not beat the trailing-volatility prior
  on held-out dates, `FAILED_VARIANT`, no second variant.
- X3 LEAN replication of finalists: `DEPRIORITIZED` until a rule survives M1.

### LANE W — The paper (MURAT + SUPERVISOR)
A methods and negative-results paper is the most realistic of the three deliverables in
2–3 months: the forecast ledger (persona vs process vs trailing σ), the calendar-offset
case, the closures table. Owed: a two-page outline naming its receipts.

## 3. What stops

- New books, accounts, modules and probes for 21 sessions, except those named above.
- Quoting a hindsight backtest without its matched-twin verdict beside it.
- Automated reading of paid sites without a hand-over.
- Rewriting this roadmap before 2026-10-05 unless a gate above is met or fails.

## 4. Process

Sonnet researches. Opus 5.5 builds. A second Opus 5.5 attacks each build as an investor.
The orchestrator writes no code, verifies every claim against a receipt, runs the suite
once, and commits only on exit 0.

## 5. Three sentences

**WHAT WORKS:** the measurement machinery, which has now closed more than a dozen ideas
including its own best backtest, and the forecast ledger as a dataset.

**WHAT DOES NOT:** any strategy, source or book as a demonstrated edge, unattended browser
reading, and the habit of adding a module for every failure.

**HIGHEST-EV EXPERIMENT:** the quarterly-offset triplet on the two leads entering forward
testing (M1): one afternoon, and it decides whether the project's only surviving lead is a
calendar artefact.
