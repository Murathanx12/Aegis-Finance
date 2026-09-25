# ROADMAP 2026-09-25 — Connect what exists, the human + AI book, and the challenge

**Status: ACTIVE TIER 1 (adopted 2026-09-25, Fable 5.1 planning session, $0 LLM
spend, nothing built).** Supersedes
`ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
as the current plan; that file's §14-§16 amendments (the loop, the five states,
PROBE) remain binding and are not restated here. Builder contract:
`HANDOFF_2026-09-25_FABLE_TO_OPUS_BUILD_PLAN.md`. Book spec:
`BOOK_2026-09-25_HUMAN_AI_THEMATIC_V0.md`. Evidence for every claim below:
`research_notes/2026-09-25/` (seven Sonnet reads, each a file; the external
GPT queue Murat pasted is there too, marked external).

Murat's brief, 2026-09-25 (condensed, his words in quotes): analyse everything
found; "find services that we have built but not utilizing"; "how can a large
language model be used ... with the engine we have ... side by side"; "the
product ... the team ... monopoly ... we can only find this on internet"; "we
know what doesn't work ... we need to also figure out what works"; one
portfolio "human + AI combined" on his themes; the Bloomberg challenge; search
for "small project undiscovered ones".

---

## 0. RESULTS SCOREBOARD (2026-09-25, from `audit_ops_7d.md`)

| line | state |
|---|---|
| best historical net strategy vs market | **none** (§59-§63 closed) |
| best forward paper strategy | PC-PAPER flat **$1,000,000**, 0 positions, `acting: false` on all 99 cycles of the 8-hour run; fleet last measured 09-22 at **$443,737 / $500,000 (−11.3%, hack3 retired)**; Railway loops hack1/2/4/5/6 **Online** through 09-24 close |
| independent selector count | 1 (price/volume ranker, measured negative at 21d) |
| new actionable finding | **§64 stands and strengthened** (investigator +5.32% raw / +8.97% recalibrated on n=4,680; 14 personas −28.41% on n=12,804). **New this session: the forecast ledger has accrued almost nothing since 08-27** — 11 rows on 09-11, 40 on 09-24, zero on every other audited day. The scoreboard has re-graded the same 17,484 rows for four weeks. |
| LLM spend, 7 days | **$19.03 lower bound** (14,677 DeepSeek calls; 59,233 local). **OpenClaw's DeepSeek spend is invisible to the ledger** (its CLI path never writes telemetry). |
| the 40 `investigator:evidence_v2` forecasts | resolve **2026-09-28** — still the only forward test on the board |

**RESULT IMPROVEMENT: NONE.** Nothing traded. The week produced a method result
(§64) and a machine that refuses correctly, and the thing that would let the
method earn — a fresh forecast every night on a candidate set the loop can act
on — is not running.

---

## 1. WHAT THE SEVEN READS FOUND (each with its receipt)

### 1.1 The decision path is one function, and it reads 23 price features
`audit_services.md` §1-§3. `u_plan` (`scripts/sim_run.py:444-533`) is the
**only** code path that calls `pc_broker.submit()`. It reads `ranking.json`
from `xs_ranker.rank_asof()`, whose `FEATURES` (`xs_ranker.py:146-155`) are 23
price/volume/liquidity features — **no analyst, fundamental, event or text
input**. `acting` is a pure function of the ranker's own `top20_net_rel_21d`,
which §59 measured negative, so the loop will refuse forever by construction.

Three other allocators exist and reach nothing: `investment_committee.
compose_book()` (router + attended CLI), `pm_engine.py` (router only), and
`portfolio_intelligence/scheduler.py`'s 18 daily collectors, every one
commented "descriptive... never arms a lane". `u_learn`'s rota is
`survivorship_audit → breadth_check → idle`; neither writes anything
`fit_production` reads back.

### 1.2 Collected, never used — the top of the list
| what | where | why it matters |
|---|---|---|
| **393,369 dated analyst revisions** (2011→2026, `pit_safe=True`) | `backend/data/optimus/analyst/target_revisions.parquet` | excluded from `llm_portfolio.build_briefing()` by its own `what_is_NOT_here`; not in `xs_ranker`; not in `u_plan` |
| **ANALYST-SKILL-1** — analyst *identity* on IBES `ptgdetu` (4.66M targets, 1,348 brokers, **33,043 analysts** via `amaskcd`) | `Aegis module/TRIALS/PREREG_ANALYST_SKILL_1.md`, registered 2026-08-31 | **never run.** No verdict anywhere in `docs/`. The external queue's "analyst leader" experiment is this trial. |
| **Analyst reliability corpus** — 98,772 graded IBES recommendations, 5,793 analysts, SIC2-benchmarked, `RELIABILITY_PERSISTS` | `FINDING_2026-08-23_ANALYST_RELIABILITY.md`, `backend/data/optimus/actor_corpus/ibes_graded.parquet` | the precondition for an actor ledger was measured a month ago; nothing consumes it |
| **ANALYST-IBES-1**: revision breadth in small caps **+6.05%/yr gross** vs Δ-consensus −0.73 → UNRESOLVED; largemid net-dead | `Aegis module/docs/ANALYST_IBES_1_VERDICT_2026-08-11.md` | Q-4 is not a blank slate; the successor (ANALYST-IDENT-1) died at POWER (MDE 10.8 vs 4.0) |
| IIF1 investigator forecasts (`investigator_agent/night/triggers`) | run by `always_on_lab`, outside `sim_run` | the one positive process sits one integration step from the loop |
| typed-event stack (`edgar_events`, `earnings_intelligence`, `event_intel`, `event_extraction`, `event_store`) | classified AWAITS in `signal_reachability` | narrates the website; never a feature |
| `short_interest` (36 files to 09-12), `graph_propagation`, `ark_holdings`, `congress_trades`, 13F, `news_intelligence`, `trends_sentiment`, `prediction_markets`, `winner_loser_factory`, `market_sensor` | see table | **congress/ARK: zero rows in the local `aegis_pi.db`; 13F: one row dated 06-30** despite being registered daily jobs — possibly broken, not merely unused (`audit_services.md` last section) |

FDA/PDUFA exists only as **taxonomy + a manual YAML** (`pm_catalysts.py:184`).
A gambling basket exists as an **ESG exclusion** (`agency.py:326-334`) and the
book holding DKNG does not apply it.

### 1.3 Eight things that read healthy and cannot go red (`audit_ops_7d.md`)
1. Forecast accrual stopped 08-27; the scoreboard runs daily and says nothing.
2. `q2_power_bottleneck` OpenClaw quest: empty log, empty error file —
   indistinguishable from never ran.
3. OpenClaw spend absent from `llm_calls_*.jsonl`.
4. `roi_ranking.n_considered: 2` on six consecutive days while the funnel's own
   `n_candidates` is 25.
5. Three days with zero LLM telemetry and no staleness alarm.
6. Two crashed sim sessions absent from `sessions.jsonl`; cycle 14's output
   file missing from the "0 errors" run.
7. PC-PAPER `nav.jsonl` writes a plausible curve from an account whose key is
   absent from env (`HALTED.json` 09-22) while alt-named creds exist in `.env`.
   **Murat: is PC-PAPER connected or synthetic?**
8. Fleet equity doc 3 days stale while the loops run fine.

### 1.4 The literature agrees with §64 and disagrees with the framing (`research_llm_engine.md`)
End-to-end LLM trading alpha collapses out of the base model's training window
(**Profit Mirage** 2510.07920; **The Alpha Illusion** 2605.16895: FinMem /
QuantAgent −72% return OOS, TradingAgents Sharpe 0.43→0.22 under costs; SoK
2609.19705: 80% of 15 schemes fail robustness). The prescribed architecture is
the one we measured into: **LLM as auditable evidence extractor → deterministic
calibration → aggregation → numeric sizing.** RL-from-P&L (Trade-R1) degenerates
into "momentum machines hallucinating justifications" without an
evidence-consistency verifier. ForecastBench: LLMs approach superforecasters
only through aggregation + extremization, never raw single-call probabilities.
Analyst-level skill persistence is real and lives at **days to two quarters**
(Mikhail/Walther/Willis; Cooper/Day/Lewis; Loh & Stulz: ~12% of recommendation
changes move price, concentrated in non-consensus, estimate-attached
revisions; Jegadeesh & Kim: revision, not level). That matches our own h=1
skill gone by h=5.

**Consequence:** no fine-tune, no new persona prompts. Build the aggregator
(§3 Lane R) with a **negative-skill floor** — no published pooling scheme
assumes a forecaster worse than a coin flip, and we have measured nine.

### 1.5 The Bloomberg Global Trading Challenge, verified (`research_bloomberg.md`)
CONFIRMED from `portal.bloombergforeducation.com`: registration **Aug 31 – Oct 5,
2026** (one secondary source says Oct 4 23:59 EDT — pin the hour from the
portal); challenge **Oct 12 – Nov 13, 2026**; winners Nov 20. Rules, verbatim
and stable 2021-2025: $1M notional, **fully invested within the first business
week**, universe **WLS = Bloomberg World Large, Mid AND Small Cap** (not
large/mid only), single-name equities, long only, no leverage, **max 20%
per position**; scored on **"Relative P&L"** (defined in `TMSG<GO>`), tiebreak
absolute return. Benchmark is WLS itself. Data-export rules: **unconfirmed**.
`ANR`, `EE`/`EM`/`EEG`, `ERN`, `SURP`, `SPLC`, `ECO`, `EVTS`, `CACS`, BI
catalyst calendar confirmed; **`ANRP`, `PHDC`, `DRUG`, `ECDR` could not be
confirmed** — the external queue's mnemonics are partly invented.

Winners: RIT 2024 **+168%** ("make as much money as possible without being
concerned about risk", Asian-hours volatility); CUHK 2025 **+400%+** (blurb
only); HKU 2023 +67.7% (blurb only); USF 2025 **top 3% at +5.3%** (the most
useful real anchor: a competent 97th-percentile team posts single digits);
Iona 2024 top 3% at +20.5% (small caps into earnings). **Shape: a fat-right-tail
rank tournament.** Winning outright requires deliberate variance; a
top-quartile finish is single-to-low-double digits. Both are legitimate
objectives and they are different books.

### 1.6 The themes, researched (`research_themes.md`, 34-row table)
- **Power bottleneck confirmed by dated events**: Vertiv's $2.6B Utility
  Innovations deal (09-03), GE Vernova 116 GW turbine backlog, nVent guide
  raise to 37-39%, DOE "Speed to Power" $5.25B (09-24). This is Q-5 with the
  September evidence.
- **Lithium**: Section 232 critical-minerals proclamation is negotiation-only
  and overdue; FEOC exempts graphite through 2026; ELVR is the old PLL (a stale
  screen misses it); ENS has a lithium data-center-backup line that decouples
  from the EV cycle.
- **Quantum**: IONQ real-time decoder + NVIDIA (09-23); **RGTI $100M Commerce
  equity stake (09-04)**; QUBT target dispersion $10 vs $32 is the tell.
- **Robotics**: no clean US pure play. Harmonic Drive / Nabtesco only as thin
  OTC ADRs. **NOVT** has a disclosed, backlog-verifiable humanoid servo order
  (Aug 6 call). SERV's guidance cut is a clean falsifier.
- **Nuclear/SMR**: OKLO has three firms disagreeing in one week; SMR (NuScale)
  stacked downgrades; **LEU** $900M DOE HALEU order; CEG Crane restart 2027.
- **Policy stakes**: INTC, MP, **TMQ** (10% stake closed 09-14).
- **FDA**: 11 primary-verified PDUFA dates Oct 30 – Dec 27 (`research_fda_
  catalysts.md`), 17 aggregator-only ones needing IR cross-check; one
  aggregator date (VERA) was flat wrong. NME first-cycle approval base rate
  ~87%; run-up-then-fade is documented for **trial readouts, not PDUFA**.
- **Gambling**: AGA forecasts a **flat** 2026 NFL handle and blames Kalshi /
  Polymarket; **HOOD's event-contract revenue ($156M Q2) exceeds its crypto
  revenue** — the one listed name on the winning side of the leak. DKNG/FLUT
  are on the losing side of it. Loss-deduction fix advanced 38-5 on 09-17.
- **McDonald's**: 09-23 Investor Day, $8.5B remodel requiring ~$800K per
  franchisee, same-store sales +0.8%, five target cuts on 09-24 → evidence
  against near-term.
- **"Analyst ROI 50-300%"**: a public upside screener was caught **fabricating
  upside by 4-20×**; only ZG (+63%, 25 analysts) and NMRK genuinely clear the
  bar, and our own §17 says target-level upside is perverse. **It is a veto
  list.**

### 1.7 Free data that is real, and the one thing that is not free (`research_fda_catalysts.md` Part 2)
Free, no key: Federal Register API, SEC EDGAR (10 req/s), House Clerk PTR bulk
ZIP, Polymarket Gamma, openFDA (key lifts 1k→120k/day — the best free upgrade).
Kalshi public reads returned 401 (re-verify). **Individual analyst NAMES are
only in Benzinga's paid Ratings API**; TipRanks/MarketBeat ToS bar scraping. We
already hold analyst identity in IBES (`amaskcd`) for 2013-2026 — the
competition-window gap is what `ANR<GO>` fills, if export is permitted.

### 1.8 Small repos worth taking ideas from (`research_repos.md`, 28 repos + 8 HF datasets, 94-query cue)
`austin-starks/sec-ownership-disclosures` (1★, MIT, pushed 09-24: Form 3/4/5 +
13F lake with a **"when could this have been known"** column and the
grant-vs-open-market split), `Builder106/capitol-alpha` (matched-control
Congress result), `Pdong19/edgar-scanner` (285 tests, cross-checks 10-K claims
against USAspending), `jaablon/buried-events-parser` (8-K item-code mismatch),
`juanmicl/quant-market-data-forensics` (killed its own 9-556× alpha bug),
`groundtruthtools/ats-jobs-mcp` (7,479 ATS boards — the VISION file's hiring
signal), `wafergraph-mcp` (semiconductor supply graph). Gaps that are real:
patent→ticker, contract→ticker, app downloads, betting handle — nobody has
built them in the open.

---

## 2. THE THREE RULES OF THIS PHASE

1. **Connect before build.** No new collector, model or persona until the
   analyst revisions, the investigator forecasts and the committee shortlist
   are on the path that reaches `u_plan` — as **separate books or explicit
   gates**, never as weights in the composite (`ROADMAP_2026-08-24`).
2. **A forecast that is not made cannot be graded.** Accrual is a canary now:
   a night with zero new forecast rows is DEGRADED, and every OpenClaw quest
   ends in a forecast row or a refusal row.
3. **The human + AI book is a `PRODUCT_EXPERIMENT`**: AI drafts with the
   evidence verdicts attached, Murat edits, the book is frozen with its twins
   before any outcome exists, and it is graded against SPY, an equal-weight
   twin and a sector-ETF twin so a good number can be attributed to picks
   rather than theme beta.

---

## 3. THE LANES — gate-ordered, each with its evidence and its control

### Lane C — CONNECT (blocks everything; cheap; first)
- **C0 receipts that can go red**: forecast-accrual canary; OpenClaw spend
  into `llm_telemetry`; crashed sessions into `sessions.jsonl`; collector
  liveness (congress/ARK/13F zero rows → red); `n_considered` stuck detector.
- **C1 run ANALYST-SKILL-1 as registered** (ΔIC of skill-weighted vs
  equal-weighted consensus, paired by month, NW-3). Adopt/reject decides
  whether the analyst-identity branch is built at all. **Report-only.**
- **C2 revision FLOW as a feature and a book**: `analyst_ledger.revision_flow
  (asof)` from the yfinance rows (net raises−lowers 90d, median target change,
  independent-firm cluster count, days since last, price move before the
  revision); PIT-joined as *optional* features; `walk_forward` with/without;
  by-year, leave-one-year-out, worst breadth cell **before** any t. Then a
  frozen `revision_flow_v0` book. Prior: ANALYST-IBES-1 small-cap +6.05% gross
  UNRESOLVED; largemid net-dead. **Print the small/largemid split.**
- **C3 the committee shortlist reaches `u_plan`** as the candidate set under
  the PROBE state (§16), with `n_considered` derived from the funnel's own
  count.

### Lane R — REPUTATION (the ledger becomes weights)
- `forecast_reputation.py`: per-arm rolling Brier skill vs climatology, shrink
  by n (`n/(n+k)`), **floor at 0**, power γ, log-odds pooling, extremization κ —
  all tuned on held-out halves by date, refit every `u_grade`, receipt with
  the weights and the by-arm skill. Formulae: `research_llm_engine.md` Q3.
- A **p → realised-return calibration** for `investigator:*` at h=1 and h=5
  (decile table, by year). Without it a probability is not a size (§61).
- Actors after arms: the IBES corpus already has per-analyst reliability;
  insiders/13F/ARK/Congress keep accruing under their registered trials
  (`TRIAL-*-IC`, `TEACHER-LIBRARY-1`) and are read at their read dates, not
  now. Congress disclosures lag up to 45 days — a delayed signal by design.
- **Profit-Mirage check on our own winner**: does investigator skill survive on
  tickers/dates the base model cannot have seen, and under costs? This is the
  single audit the literature says invalidated everyone else's headline.

### Lane H — THE HUMAN + AI BOOK (`BOOK_2026-09-25_HUMAN_AI_THEMATIC_V0.md`)
- Draft in this session (AI side, with verdicts and falsifiers); Murat vetoes,
  adds, resizes; freeze via `scripts/llm_portfolio.py freeze` **with four
  twins**: equal-weight same names; sector-ETF proxy; AI-only (no human
  overrides); SPY. Graded 1/5/21/126d net of entry cost, nightly.
- Catalyst calendar as the manual YAML `pm_catalysts` already accepts: the 11
  primary-verified PDUFA dates, the confirmed earnings dates (TSM Oct 15, TER
  Oct 27, HOOD Nov 4, MCD ~Nov 4, NOVT ~Nov 10, FLUT ~Nov 10).
- Binary events sized small and **quoted in sigma**; a PDUFA name is a coin
  flip with an 87% base rate on approval and an unknown on the price.

### Lane W — WEB SEARCH → DECISIONS (OpenClaw as a triggered investigator)
- `investigator_triggers` already exists. Wire five triggers: shortlist entry,
  rank jump, revision cluster (≥3 independent firms in 10d), 8-K/earnings
  within 5 sessions, unexplained move (>2σ with no typed event). Each quest
  runs the ten fixed questions (what changed / not known yesterday / demand vs
  price vs volume vs mix / suppliers / customers / who loses / contradicting
  evidence / if management right / if wrong / 2nd-3rd order beneficiaries),
  returns strict JSON to `web_events`, and **ends in a forecast row** at h=1
  and h=5 via the investigator process. An empty quest log is a FAIL.
- DeepSeek only paired: same packet to local Qwen, both answers frozen, cost
  and latency recorded, graded later. This is the only way to learn where
  DeepSeek is worth paying for.
- Product Thesis Card (product / economics / competition / team / technology
  intent / forward catalyst + falsifier) for the ~25 names in the shortlist ∪
  the book. Not 3,000 names.

### Lane K — THE CHALLENGE (Oct 12 – Nov 13)
- **Before Oct 5**: register (Murat). Before Oct 9: WLS membership check of
  every candidate (Terminal export → `wls_members.yaml`); the competition
  contract (long-only, ≤20%, fully invested by Oct 16, Relative P&L vs WLS).
- Five frozen $1M books on **Oct 9**: event/earnings, analyst revision
  (C2), product/bottleneck (Q-5), LLM investigator (Lane W), ensemble (Lane
  R weights). Plus the human + AI book under competition constraints.
- Tournament policy: BASE ranks on the median; ATTACK (behind late) ranks on EV
  — already in `aegis-alpha-terminal/alpha/tournament.py`. The objective is
  declared before the first fill: **top-quartile** (single digits, diversified
  over catalysts) or **grand prize** (variance on purpose). Murat chooses;
  both cannot be one book.
- During the window: `ANR<GO>` exports for the shortlist if the rules permit
  (unconfirmed) — analyst identity for the names we hold, joined to the IBES
  skill table from C1.

### Lane D — DATA (after C, R, H have consumers for it)
House PTR bulk ZIP → `congress_trades` (and fix the zero-row collector);
Polymarket Gamma → `prediction_markets` (event probabilities for the PDUFA
names); Federal Register API + DOE/USTR → a `policy_events` typed feed; openFDA
with a key; evaluate `sec-ownership-disclosures` for the PIT column and the
grant/open-market split. Each feed ships with a consumer or is not shipped.

---

## 4. GATE ORDER

```
C0 receipts ─┬─ C1 ANALYST-SKILL-1 (report) ──┐
             ├─ C2 revision flow → book ───────┼─ R aggregator + calibration ─┐
             └─ C3 shortlist → u_plan ─────────┘                              │
H book freeze (Murat's veto first) ── nightly grade ──────────────────────────┤
W triggered investigator → forecast rows (accrual restarts) ──────────────────┤
K Oct 5 register → Oct 9 five books + WLS check → Oct 12 start ───────────────┘
D feeds — only once a lane above consumes them
```

Exactly two things cannot be parallelised: the 09-28 resolution of the 40
forecasts, and the days it takes a freshly frozen book to have a 21-day grade.

---

## 5. WHAT MURAT DOES (only what Claude Code cannot)
1. **Register for the challenge before Oct 5** and read the exact deadline
   hour and the data-export rule off the portal.
2. **Veto / edit the human + AI draft** (`BOOK_2026-09-25_HUMAN_AI_THEMATIC_
   V0.md` §4) and say which objective the competition book runs under.
3. ~~Say whether PC-PAPER is connected~~ **RESOLVED 2026-09-25 (Fable, one
   read-only `GET /v2/account`)**: the `PC-PAPER_key` pair in `.env` works;
   `pc_broker.credentials()` resolves the alt names (line 146-148); the account
   is `ACTIVE`, equity $1,000,000, cash $1,000,000, created 2026-09-22T03:39Z.
   It is connected and idle because `u_plan` refuses, not because of keys.
4. Decide on voiding the six non-equity forecasts (`CL=F` etc.); it edits a
   tamper-evident ledger. **Recommendation: do nothing** — they are already
   reported `PERMANENTLY_UNPRICEABLE` and excluded from every skill number.
5. ~~Confirm CYTK's PDUFA status~~ **RESOLVED 2026-09-25**: MYQORZO was
   approved (NDA PDUFA Dec 26, 2025); the "Nov 14, 2026" date was an
   aggregator artefact. Struck from the calendar and the book.
6. Terminal work during the window: `ANR` export for held names if permitted.

---

## 6. MUST NOT REGRESS (added 2026-09-25)
- No new mechanism enters `arena_composite` or `xs_ranker.FEATURES` as a
  default; it enters as a **book with a twin**.
- A forecast arm with measured negative skill has weight **0.0**, not "small".
- A screener number from an aggregator is **not evidence** until reproduced from
  a primary source (the 4-20× fabrication).
- A PDUFA date from an aggregator is a claim; the company's own release or 8-K
  is the fact (VERA was wrong).
- A quest, a night, a collector and a scoreboard each emit a row that can be
  **zero**, and zero is red.
- `predictions.jsonl` is never touched by `git reset/checkout/stash/clean`.
- The competition book and the personal book have **different objectives** and
  are graded under their own; "best among losing strategies" deploys nothing.

---

## 7. QUEUE ADDITIONS
Written into `RESEARCH_QUEUE.md` as Q-9 … Q-14 (this session). The reusable
94-query search cue for future Sonnet sessions is
`research_notes/2026-09-25/research_repos.md` § RESEARCH CUE.
