# The research queue — ideas banked, with what would settle each

> Murat, 2026-09-24: *"save these conversations and things we want to do and test
> in case we want to test them in future again."*

This file is the backlog. An idea lives here with **the observation that would
settle it**, because an idea without one is not a hypothesis yet
(`AEGIS_STRATEGIC_INVARIANTS`: every intuition is owed one question — *what
observation would separate this from ordinary factor beta?*).

Ideas move **QUEUED → RUNNING → §n in NEGATIVE_RESULTS.md**. Nothing is deleted:
a refuted idea is a result and the next session needs to know it was tried.

---

## RUNNING NOW

| id | idea | settles when |
|---|---|---|
| **Q-ANALYST-1** | Nightly analyst pull, 3,214 tickers (`scripts/pull_analyst_targets.py`, wired as `sim_run.u_analyst`) | accrues; the snapshot series only becomes point-in-time from 2026-09-24 forward, so it is a clock, not a question. **392,201 dated revision rows already in hand (2011-2026) and those ARE backtestable.** |
| **Q-FORECAST-1** | `investigator:evidence_v2` — 40 forecasts frozen at h=1, shrunk 0.65, resolving **2026-09-28** | the sim's `u_grade` resolves them, then `night_specialist_scoreboard` scores the arm against climatology. **A positive Brier skill here is the first forward confirmation of §64 on an arm we built.** |

## ADDED 2026-09-25 (planning session; see `ROADMAP_2026-09-25_CONNECT_WHAT_EXISTS.md`)

| id | idea | settles when |
|---|---|---|
| **Q-9 ANALYST-SKILL-1** — **RAN 2026-09-26 on the registered WRDS instrument** (`docs/ANALYST_SKILL_1_VERDICT_2026-09-26.md`): ΔIC +0.00084, t 2.52 over 71 months → ADOPT by the registered rule, but 1/12 of the 0.010 the prereg called "worth building"; ΔIC tracks the consensus IC (t −4.98) and the residual is +0.00035 t 1.09; analyst-level weighting REJECT (t 1.32). **Adjudicated: ADOPT_AT_TRIVIAL_EFFECT — the branch is not funded; `analyst_skill_weight` lives on as one library feature judged by the sealed leaderboard.** | run the trial registered 2026-08-31 (IBES `ptgdetu`, 1,348 brokers, 33,043 analysts): does skill-weighting the consensus beat equal-weighting? **Never run; no verdict in `docs/`.** | ΔIC paired by month, NW-3, t ≥ 2 → ADOPT; else the analyst-identity branch is a corpse (build plan C1) |
| **Q-10 revision flow as a BOOK** — RAN 2026-09-25: flow improves every worst cell except H=5, both arms net-negative at 21/63d; month-end rule +0.32%/hold vs SPY (LOO +0.02, t 0.94); `revision_flow_v0` frozen `cb8d492bb8bf9ade` + random twin | `revision_flow(asof)` (net raises, n_firms, median change, days-since) on the 393,369 rows; sweep with by-year/LOO/worst-cell/small-vs-largemid printed first; `revision_flow_v0` frozen with a random twin regardless of sign. Prior: ANALYST-IBES-1 small +6.05% gross UNRESOLVED | 21 days of forward grade on the frozen book (build plan C2) |
| **Q-11 reputation layer** | per-arm Brier skill held out by date → shrink by n → **floor 0** → γ → log-odds pool → κ; refit each `u_grade`; p→return calibration for `investigator:*` at h=1/5 by year; **Profit-Mirage check** (post-cutoff tickers/dates only) | weights receipt exists and the restricted-sample skill is printed beside the full one (build plan R) |
| **Q-12 human + AI thematic v1** — FROZEN 2026-09-25 `a20a2b972988eec6` + 4 twins; 6+14 factory books beside it | `BOOK_2026-09-25_HUMAN_AI_THEMATIC_V0.md` — AI draft (26 names + cash) + Murat's edits, frozen with `ew` / `sector_etf` / `ai_only` / `spy` twins | 1/5/21/126-session grades; the twin ordering says whether themes, picks, sizing or the human edits paid (build plan H) |
| **Q-13 triggered investigator** — `u_forecast` RUNNING since 2026-09-25 (evidence_v3, h=1/5); triggers-on-change still owed | OpenClaw quests on shortlist entry / rank jump / revision cluster / filing / unexplained move; ten fixed questions → `web_events` → a forecast row at h=1 and h=5, DeepSeek paired with local Qwen; personas retired at weight 0 (Q-3 executed) | the accrual canary returns to `ok`; `investigator:evidence_v2` n grows nightly (build plan W) |
| **Q-14 Bloomberg challenge books** | five $1M books frozen Oct 9 under the confirmed rules (WLS incl. small caps, long only, ≤20%, fully invested by Oct 16, Relative P&L); objective declared (top-quartile vs grand-prize) | Nov 13 (build plan K) |

Banked this session, not to re-derive: a public upside screener fabricated upside 4-20×; an aggregator's PDUFA date (VERA) was already past; `ANRP`/`PHDC`/`DRUG` are not confirmed Terminal mnemonics; the AGA forecasts a FLAT 2026 legal NFL handle (the "everyone is betting" trend lives in prediction markets, i.e. HOOD, not DKNG).

---

## QUEUED — ranked by `P(changes the roadmap) × value − cost`

### Q-1 — The 20-year signal dissector *(Murat's main ask, 2026-09-24)*

> *"using the historical data of 20 years, web search find winning stocks of each
> year and winning industries, use openclaw to find news from these days using
> archive and try to find out what were the signals, what are the cues and how
> we can find them these days."*

**Shape.** For each year 2006-2026: identify the top-decile performers and the
industries that carried them; have OpenClaw pull contemporaneous coverage from
archives (`web.archive.org`, company IR, SEC 8-K) dated to **before** the move;
have DeepSeek extract into the typed schema; then ask what was observable
beforehand.

**What must be true or it is worthless.** The extraction window must END before
the move begins. An archive read dated after the run has already seen the
answer, and an LLC asked "what predicted this" will always find something. The
design therefore needs a **negative control**: the same extraction, same dates,
on matched names that did NOT move. Winner-only forensics is exactly the
"gallery of survivors" the mission forbids.

**Settles when.** A precursor found on 2006-2015 names predicts out-of-sample on
2016-2026 names with a base rate measured against matched controls.

**Cost.** Large. Hundreds of archive fetches, thousands of DeepSeek extractions.
Worth doing on **one decade and 40 winners + 40 matched controls first**, not
twenty years and everything.

**Prior art in this repo that must be read first:** §59-§64, and the
`investigator` result (§64) which says the structured-evidence process is the
one that forecasts.

---

### Q-2 — Fable portfolio allocation *(Murat will run next session)*

> *"feed an LLM preferably Fable 5.1 ... it skims everything and makes
> portfolios, few very aggressive focused at maximizing ROI ... others based on
> beating sp500 ... 1m for each paper account, no cap ... day-week-month-6months."*

**BUILT AND READY.** `backend/services/llm_portfolio.py` +
`scripts/llm_portfolio.py`:

    python -m scripts.llm_portfolio brief      # point-in-time briefing, all names
    python -m scripts.llm_portfolio template   # the shape a book must come back in
    python -m scripts.llm_portfolio freeze books.json
    python -m scripts.llm_portfolio grade      # NAV vs SPY at 1/5/21/126d

**Settles when.** Books frozen before outcomes exist are graded against SPY net
of entry cost. Several objectives at once is the point — aggressive and
beat-SPY are different objects and averaging them hides the answer.

**The honest gap Murat should know:** the briefing does NOT contain analyst
price targets or fair value (the vendor endpoint is 403 on this tier). It now
CAN, via Q-ANALYST-1 — wire `target_snapshots` into `build_briefing` once a few
nights have accrued.

---

### Q-3 — Recalibrate and prune the specialist bench *(from §64)*

**Cheapest positive-expected-value action available.** §64 measured, held out:
`investigator` +4.38% raw → **+8.97%** at shrink 0.65; thematic personas
**−27.98%**, optimal weight **0.00**.

**Do:** turn the nine thematic specialists off (a spending decision, not a
research one); apply the 0.65 shrink to investigator output at the point of use;
ask at h=1 where the skill is, not h=20 where it is gone.

**Settles when.** The next 2,000 graded forecasts show the same skill with the
bench pruned. Re-run `scripts/night_specialist_scoreboard.py`.

---

### Q-4 — Revision *flow*, not level

`target_revisions` has real dated events (443 rows MRVL, 883 MU, 3,658 across
12 names). `analyst_target_upside_xs` is CLOSED/PERVERSE as a **level** (t −3.6
large/mid, −7.2 small) — the revision series is a different object and untested
here.

**Settles when.** Net raises-minus-lowers over 90 days, and median target change,
are graded against forward relative return with the same time-matched
cross-sectional median benchmark §63 had to adopt. Needs the full pull to finish.

**Early observation (12 names, not a result):** STX +15 net / +14.8% median; VRT
**−4 net / −11.6%**; ALAB +8 net / **+57.3%** while gross margin falls 76.3→72%
and WIP triples. That last shape — targets racing fundamentals — is Murat's
"narrative/economic divergence" and is the most interesting cell to test first.

---

### Q-5 — Bottleneck migration, as a repeatable screen

Three independent methods agreed on 2026-09-24 that the AI bottleneck has moved
**past optics to power**:

| | SEC margin detector | 90-day revisions | OpenClaw evidence |
|---|---|---|---|
| STX / GEV / NVT | fires | net positive, no lowers | — |
| VRT | does not fire | **−4, −11.6%** | EMEA organic −14.8%, inventory 2× |
| ALAB / CRDO / LITE / MRVL | does not fire | mixed | ASPs falling, inventory build, "increasingly competitive" |

Lumentum's own 10-K: cloud transceivers "+173% due to an increase in shipment
**volume**, partially offset by" declining ASPs. Vertiv deferred revenue
**$1.81B → $3.63B** (customers pre-paying — the scarcity tell).

**Settles when.** The triangulation is run as of a PAST date and its call is
graded forward. Doing it only as of today produces a story, not a test.

**Caveat that must travel with it:** §63 found the margin detector has **no
dose-response** — a bigger signal does not produce a bigger return. The
triangulation may still be useful as a *filter* while being useless as a *score*,
and those are different claims.

---

### Q-6 — Conditional mean reversion after an index shock *(Murat's behavioural idea)*

> *"big up day → people take profits → next day falls"* is not unconditionally
> true (2026-09-21 was +1.49% and the next day the S&P was ~flat while Nasdaq
> rose).

**The testable version.** After a >1.5σ index move, under which state variables
does the next 1-3 day expected return turn negative? Candidate conditioners:
breadth, volume, close location within the day's range, options skew, VIX term
structure, ETF flows, sector dispersion, 10Y change, oil, overnight futures.

**Settles when.** The conditional beats the unconditional out of sample, with
the state variables chosen BEFORE looking (a prior chosen after the diagnostic
is not a prior — 2026-09-22).

**Cost.** Low for the price-derived conditioners, which are already in the bars.

---

### Q-7 — IPO prospectus as industry intelligence

> *"instead of treating IPOs merely as stocks to buy, read their prospectuses as
> industry intelligence documents"* — customer concentration, suppliers,
> purchase commitments, backlog, capacity constraints — then map onto
> already-public companies.

**Settles when.** A disclosure in an S-1 predicts a revision or an inflection in
a named public peer, graded forward, against a control of S-1s whose peers did
nothing.

---

### Q-8 — China capacity shadow

`patent acceleration + hiring + fab construction + equipment orders + subsidies
+ customer sampling` as a leading indicator of Western pricing power breaking.
CXMT entering NAND is the live case.

**Settles when.** The composite leads an ASP decline in a prior episode (there
are several: DRAM 2018, solar 2011-12, LED 2014). **Test it on the historical
episodes first** — it is the only way to get a sample size above one.

**Standing warning:** patent counts alone are a known-bad trading signal. The
claim is about the conjunction, and the conjunction must be pre-specified.

---

## BANKED — measured and closed, do not re-derive

| § | claim | verdict |
|---|---|---|
| §59 | price/volume ranks the cross-section at 21d | the edge IS the illiquidity and is smaller than the toll |
| §60 | six-ratio fundamentals replicate JKP's +39bps | came LAST of six, negative at every k |
| §61 | a longer holding period rescues §59 | entirely 2025; drop it and +2.62% → +0.12% |
| §62 | a −2% stop saves the fleet 75% | all 11 exit rules LOSE to holding; −2% is 0.93 daily sigma |
| §63 | inflection archetype (growth+margin) pays | **no dose-response**; the 70%+ bucket is negative at the median |
| §64 | fourteen LLM specialists forecast | −17% skill; investigator +8.97%, thematic weight 0.00 |

---

## CLOSED since the queue was written

* **Q-4's precondition** — the full analyst pull finished: 392,201 dated
  revision rows, 2,982 tickers, 0 failures. The *level* stays CLOSED/PERVERSE;
  the revision FLOW is now testable and still untested.
* **The stranded-forecast blocker** — 2,911 records that could never resolve are
  now 130 (`pull_forecast_bars` + a grader-only panel union). §64 re-ran on 19%
  more evidence and **strengthened**.

## Standing traps this queue keeps re-learning

1. **Print by year before believing any positive number** (twice: 2026-08-26, 2026-09-24).
2. **Check the benchmark when every arm agrees.** A daily-rebalanced equal-weight index compounded at +35%/yr and made three different populations look identical.
3. **A counterfactual computed from outcomes is a hypothesis.** The stop replay knew which positions lost before choosing the level.
4. **Read the WORST cell of a sweep, never the best.**
5. **Quote a stop in sigma, not percent.**
6. **Grade the ledger before running a backtest.** §64 cost one `groupby` and settled more than any panel this month.
7. **Never `git reset --hard` here.** `predictions.jsonl` is tracked and grows continuously, so uncommitted rows exist at all times; a reset to fix a commit MESSAGE destroyed ~1,200 of them on 2026-09-24.
8. **Presence is not validity.** `data_credential()` returned a key revoked two days earlier because it merely existed. Verify with one call.
