# Four social-media trading ideas: reconstruction, mechanism, and what AEGIS can test today (2026-10-07)

Researcher pass (Sonnet, web access). No code run, no trial registered, no data pulled. The
transcription the owner sent is treated as the **only** source — every parameter not literally
in it is marked MISSING, never filled in by analogy to a "typical" version of the strategy, per
the owner's brief and Mission rule 2 (CLAUDE.md: "finding precursors observable beforehand is
the research problem" — and a filled-in gap is not an observed precursor, it is a guess wearing
one). The workflow asked for (source → theory → mechanism → exact spec → backtest → counterfactual
→ forward shadow → verdict) is itself the deliverable the owner flagged as possibly more valuable
than any one idea; §5 below treats it as a product.

Read before writing: `.claude/skills/pre-register-trial/SKILL.md` (BLOCKED/DUPLICATE/RESURRECTION/
PASS vocabulary, and the point that nothing here is registered — this is theory-building, not a
trial), `docs/research_notes/2026-10-06/snowball_and_theory_objects_2026-10-06.md` §3 (the
mechanism / precursor / data / universe / horizon / falsifier / already-tried / verdict table
shape, reused below), `docs/DATA_MANIFEST.md` + `docs/DATA_CATALOG.md` (what's on disk), and
`NEGATIVE_RESULTS.md` at the repo root (**not** `docs/NEGATIVE_RESULTS.md` — that path does not
exist; the file lives at the repo root, found only by grepping git history for its own section
titles, which is exactly the "absence of a local object is not evidence of absence" trap CLAUDE.md
names, paid for again in miniature during this pass).

---

## 0. What's on disk, stated once, so it doesn't have to be re-litigated per idea

- **No intraday bars exist on this machine, for anything.** `backend/services/book_cadence.py:39`
  states it directly in code: *"Minute bars do not exist on this machine. A `30m` book is
  therefore marked from..."* — and `paper_books.py:76` repeats it. `NEGATIVE_RESULTS.md` §59's own
  "not tested and still open" list names "intraday data" as a gap, not a thing we have.
  `backend/services/polygon_client.py` has an intraday-bars **client**, but a client is not data on
  disk — nothing found calling it to build a stored panel.
- **There IS daily FX on disk, and it is yfinance's `=X` tickers inside the contest panel, not a
  dedicated FX store.** `backend/data/optimus/contest/bars/bars_FX.parquet` (30,380 rows) carries
  **`JPY=X`** (Yahoo's symbol for USD/JPY) at **daily** resolution, 2019-06-03 → 2026-10-05, OHLCV,
  alongside `EUR=X`, `GBP=X`, `CNY=X`, and others, plus `SPY`/`ACWI`/`URTH` in the same file. This
  contradicts a flat "no FX data" claim and must be stated precisely: **daily close-level FX, yes;
  session-level (03:00-06:00, any broker-time window) FX, no.** The brief asked to say plainly if
  there's any FX on disk — there is, at the one granularity that cannot answer idea #1.
  `backend/data/optimus/wrds/bulk/wrdsapps__windices__*` and the WRDS FX-adjacent tables were not
  checked for a finer grain; nothing found in `DATA_MANIFEST.md` claims one exists there either.
- **Daily US equity/ETF bars are broad and deep.** `SPY`, `QQQ`, `IWM`, `DIA` all appear as named
  tickers across `backend/services/{conviction_prices,pc_broker,signal_structure,xs_ranker,
  hyp_cells}.py` (DIA and QQQ both recognized in `xs_ranker.INDEX_PROXIES`); `signal_structure/
  etf_monthly.parquet` carries `SPY, QQQ, IWM, SMH, USMV, MTUM, VLUE, QUAL` monthly. CRSP daily
  common-stock bars run 1990-2024 (`crsp_dsf_*.parquet`, 44.97M rows) plus the survivorship-free
  `prices_2025_26/bars.parquet` (1,275,452 bars, 3,060 symbols through 2026-09-21, flagged
  survivor-selected in `NEGATIVE_RESULTS.md`/MEMORY — see the caveat below). None of this carries
  `openprc` before 2013 (the overnight/intraday split in §3 below is 2013-2024 only, by the same
  limit `FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` already hit).
- **The survivorship caveat travels onto any US-universe test, not just this one.** MEMORY and
  `NEGATIVE_RESULTS.md` both flag that the live `prices_2025_26` panel is survivor-selected (zero
  of 3,060 symbols stopped trading >21 sessions before the panel's end). `SPY`/`QQQ`/`DIA` as single
  index ETFs sidestep this (an ETF doesn't get individually delisted the way a stock does), which is
  one more reason the index-level proxies below are the honest way to test ideas #2-4 today rather
  than a single-name analogue.
- **Costs on CFDs/spread-bet indices and FX are NOT the same cost model this repo's equity work
  uses**, and nothing on disk prices them. The engine's cost schedules (flat bps, the `factor_costs`
  ADV/participation model) are built for US equities; a CFD's spread + overnight financing (swap)
  rate on a leveraged index or FX position is a different instrument and a different fee schedule
  entirely, and would need its own, separately-sourced cost assumption before any of this could
  move past a backtest.

---

## 1. USDJPY morning-range breakout ("broker time" 03:00-06:00)

### (a) Reconstructed rule

| parameter | value as transcribed | status |
|---|---|---|
| instrument | USD/JPY | GIVEN |
| range window | 03:00-06:00 "broker time" | AMBIGUOUS — "broker time" is not a timezone. Candidates: UTC+2/+3 (common MT4/MT5 server convention, often EET or EET+1 with DST quirks), or the broker's own server clock, which varies by broker and by DST regime and is frequently NOT published as a fixed offset |
| entry | buy-stop at range high, sell-stop at range low, placed at 06:00 broker time | GIVEN (mechanism), but the absolute UTC time depends on resolving "broker time" above |
| stop | opposite side of the range | GIVEN |
| take profit | none (no fixed TP) | GIVEN |
| exit | flatten + cancel unfilled orders at 18:00 broker time | GIVEN |
| trade frequency | one trade/day | GIVEN |
| position sizing | not stated | MISSING |
| slippage/spread assumption | not stated | MISSING |
| which session this targets | not stated by name | AMBIGUOUS — see mechanism below |

### (b) Candidate mechanism

A **range breakout conditioned on a low-liquidity consolidation period followed by a liquidity
regime change**, the same "balance → imbalance, confirmed by volume" story the ORB literature gives
generically (practitioner sources only — FXOpen, Trade Ideas, BuildAlpha, grandalgo.com; this is
retail/prop-firm pedagogy, not peer-reviewed, and is cited as such). The specific claim for USD/JPY
depends entirely on which session 03:00-06:00 and 06:00-18:00 broker-time actually fall in:

- Standard forex session blocks (UTC): **Tokyo 00:00-09:00**, **London 07:00-16:00**, **New York
  12:00-21:00**; the Tokyo-London overlap is roughly **08:00-09:00 UTC**, the London-New York
  overlap **13:00-17:00 UTC** (12:00-17:00 across the DST-mismatch weeks). If "broker time" nets out
  near UTC+2/+3 (a common MT4 convention), **03:00-06:00 broker time ≈ 00:00-04:00 UTC — inside the
  Tokyo session, before London opens** — i.e. the range would be built during the quietest part of
  the day for a yen pair, and the "breakout" at 06:00 broker-time (≈03:00-04:00 UTC) would fire
  *before* Tokyo-London overlap, not at a session transition. If broker time is closer to the
  server's literal UTC+0 or a different offset, the window could instead straddle the **Tokyo→London
  handoff**, which is the economically sensible version of this idea (a quiet Asian range breaking as
  European flow arrives). **This is exactly why "broker time" cannot be left unresolved** — it
  changes the mechanism from "trades the session handoff" to "trades the quietest hour of the day,"
  which are different hypotheses with different honest priors.
- The exit at 18:00 broker time plausibly targets flattening before the New York close / into the
  next day's Asian session, consistent with "don't hold a breakout trade through the quiet Tokyo
  reopen," but this is inference, not something stated.

### (c) Known failure modes

- **Look-ahead in "broker time" itself**: if the researcher resolves the ambiguity by picking
  whichever offset makes the backtest work, that is the diagnostic-chosen-prior trap
  (CLAUDE.md protocol 11 / `feedback_a_prior_chosen_after_the_diagnostic_is_not_a_prior.md`). The
  offset must be fixed from the source's own stated convention (ask the owner, or use the literal
  reel/video timestamp if recoverable) BEFORE any number is computed.
- **Stop/entry slippage on a breakout**: buy-stop/sell-stop orders fill at the first available price
  past the trigger, which on a real gap-through can be materially worse than the stop level — this
  repo's own `night_exit_rules.py` convention (`FINDING`/`NEGATIVE_RESULTS` §62) prices exactly this
  ("a level below the open fills AT THE OPEN... the stop price was never available") and the same
  discipline applies here: model the fill at the next printed price past the level, not at the level.
- **CFD/spread-bet cost structure**: the spread on USD/JPY widens materially outside the London/NY
  overlap (i.e., possibly right when this strategy's range is built), and overnight financing accrues
  if a position is held past the broker's rollover — irrelevant here since the rule flattens daily,
  but the spread-at-range-time assumption is not free and nothing on disk prices it.
- **Survivorship of the reel itself**: a single social post showing a backtest or live P&L for one
  rule, one pair, over an unstated window is a selected result by construction — it is the surviving
  backtest out of however many the poster ran, not evidence the rule is tradable going forward. This
  is a *property of the source*, independent of whether the mechanism is real.

### (d) Data: NOT testable on anything currently on disk

`bars_FX.parquet`'s `JPY=X` is **daily**, one row per calendar day — it has no 03:00/06:00/18:00
intraday structure at all. Testing this rule requires session/sub-daily FX bars. Free sources,
verified this pass:

- **Dukascopy's free historical data export** (`www.dukascopy.com/swiss/english/marketwatch/
  historical/`) — tick-level forex/CFD/index history, free, CSV, no account needed for the
  historical-data-export tool; third-party wrappers (`dukascopy-node`, the `theorycraft-trading/
  dukascopy` GitHub library) automate bulk pulls. This is the best free source for USD/JPY at any
  intraday granularity.
- **Yahoo Finance intraday (`yfinance`)**: 1-minute bars are capped at **7 days per request** (30
  days reachable by chaining four 7-day requests); confirmed via multiple independent sources this
  pass. Far too short a window for a multi-year backtest, but sufficient to validate "broker time"
  resolution and spot-check Dukascopy data once pulled.
- **Alpaca**: confirmed this pass — **Alpaca does not offer forex at all** (stocks, ETFs, options,
  crypto only). Not a candidate source for this idea.

**No daily proxy exists for this idea.** A range-breakout-with-a-specific-intraday-window mechanism
has no meaningful daily-bar analogue; collapsing it to daily OHLC would test a different, cruder
rule ("does USD/JPY trend after a big daily range") that is not what was transcribed. This is
**NOT_A_HYPOTHESIS_YET** until (i) "broker time" is resolved to an explicit UTC offset and (ii)
intraday USD/JPY history is pulled (Dukascopy).

### (e) Falsifiable question and primary metric

Once (d) is resolved: *"Does a long-at-range-high/short-at-range-low breakout off the 03:00-06:00
[resolved timezone] USD/JPY range, stopped on the opposite side, flattened at 18:00
[resolved timezone] with no fixed take-profit, produce a positive mean daily P&L net of a modeled
spread/slippage cost, over a multi-year out-of-sample window, with one trade per day?"* Primary
metric: mean net daily return in pips (or bps) per the one trade the rule takes, t-stat on the daily
series (not a per-trade stat, which would overweight a single volatile day — same blocking logic as
CANON §58's "n_effective counts date blocks"), reported alongside gross-of-cost and a flat
spread-cost sensitivity grid (the Dukascopy data carries bid AND ask, so the realistic version uses
the actual quoted spread rather than an assumed flat number).

### (f) Verdict: **NOT_A_HYPOTHESIS_YET**

Two blocking gaps, both on the owner's side, neither closeable by inference: the "broker time"
timezone, and (once that's fixed) a willingness to pull Dukascopy intraday history, which is outside
this repo's current data pipeline. Moving to `READY_TO_CELL` needs: (1) the exact timezone named by
the owner or recovered from the source (a screenshot timestamp, a stated broker, anything), and
(2) a one-time Dukascopy pull of USD/JPY 1-minute (or tick) bars for the backtest window, built as a
new, explicitly-labeled dataset (a FX intraday store does not exist and would need a `DATA_MANIFEST.md`
row the moment it's pulled).

---

## 2. "Turnaround Tuesday" on US30

### (a) Reconstructed rule

| parameter | value as transcribed | status |
|---|---|---|
| instrument | US30 (Dow Jones Industrial Average, presumably via CFD/futures) | GIVEN |
| indicator | 25-day SMA | GIVEN (as a number), role in the rule not stated |
| timing anchor | Monday/Tuesday setup, a Tuesday 23:15 close | GIVEN (as stated), but incomplete |
| entry condition | not given | MISSING |
| exit condition | "a Tuesday 23:15 close" is named but its role (entry trigger? exit trigger? the week's reference close?) is not specified | AMBIGUOUS |
| direction | "long-only" | GIVEN |
| position sizing / stop | not stated | MISSING |

**This is explicitly flagged by the owner as incomplete/ambiguous, and the brief's instruction is
followed literally here: no entry condition is invented.** This matters because, per this pass's own
research, "Turnaround Tuesday" is **not one strategy** — it is a name applied in public retail/quant
content to at least three incompatible rule sets, found this pass:

1. Buy SPY at Monday's close if Monday's close < Monday's open; exit at Tuesday's close (no
   indicator at all).
2. Buy at Tuesday's open only if Monday's close < Friday's close < Thursday's close (a
   three-day-down filter), exit when the close exceeds the prior day's high.
3. A moving-average-filtered version (30-day MA cited in one source, not 25-day) where "below the MA"
   defines a downtrend precondition, combined with a Monday-weakness trigger.

None of the three match "25-day SMA + a Tuesday 23:15 close" precisely. **The 25-day SMA and the
23:15 close are specific enough that they likely identify ONE particular creator's exact rule
(23:15 looks like a server-time cash-index close convention used by a specific CFD broker, not a
generic market hour)** — which is exactly why the exact entry condition has to come from the
original source, not from the published literature's nearest neighbor.

### (b) Candidate mechanism: the Monday/weekend reversal literature, and whether it survived

- **Cross (1973), "The Behavior of Stock Prices on Fridays and Mondays," Financial Analysts Journal
  29, 67-69** — verified this pass: S&P closed up only 39.2% of Mondays vs. 62% of Fridays, 1953-1970,
  and a down Friday was followed by a down Monday roughly 3:1.
- **French (1980), "Stock Returns and the Weekend Effect," Journal of Financial Economics 8, 55-69**
  — verified this pass (confirmed via EconPapers/RePEc listing): documents negative average Monday
  returns distinct from a simple non-trading-day effect.
- **Lakonishok & Maberly (1990), "The Weekend Effect: Trading Patterns of Individual and
  Institutional Investors," Journal of Finance 45(1), 231-243, DOI 10.1111/j.1540-6261.1990.tb05089.x**
  — verified this pass (Wiley listing): individual investors trade disproportionately on Mondays and
  sell more than buy on Mondays, offered as a behavioral driver of the Monday effect (retail investors
  catching up on weekend reading/reflection and acting, net, as sellers).
- **Did it survive post-2000? The strongest, most specific finding recovered this pass argues it
  died much earlier than that.** Smith & Robins (Arizona State University, published research summarized
  by ASU News, verified this pass by direct fetch): using 1926-2014 US data, the weekend effect was
  statistically significant 1926-1974 (Mondays down an average 18.1 points) and **effectively vanished
  after 1975** (post-1975 average Monday move down only ~5 points, not significant) — meaning the
  major academic papers that established the effect (French 1980, Lakonishok & Maberly 1990) were
  published describing a phenomenon that, per this later and more comprehensive re-analysis, had
  already mostly disappeared by the time they appeared. Other sources surfaced this pass give a messier
  picture (a ScienceDirect paper, "The evolution of the weekend effect in US markets," could not be
  fetched past a paywall this pass — 403 — so its specific post-2000 numbers are **unverified** and
  not relied on here; international evidence is mixed by country and by decade). **The honest reading:
  the Monday/weekend effect in US broad-index returns is a real, historically-documented phenomenon
  whose own best modern re-estimate puts its death around 1975 — a full generation before this
  reel's claim could be observed live.** That is the single most important piece of context for
  idea #2: whatever "Turnaround Tuesday" content creators are showing today is either (i) a
  different, newer mechanism not covered by the classical weekend-effect literature, (ii) a
  curve-fit on a short recent window, or (iii) real but undocumented in the academic record reviewed
  here.

### (c) Known failure modes

- **Indicator role is unspecified.** A 25-day SMA could gate direction (only take the setup when
  price is above/below it), size the position, or do nothing in the actual rule and just be
  mentioned as context — three different strategies.
- **"23:15 close" is almost certainly a specific broker's index-CFD server-time convention** (common
  for brokers quoting a near-24h synthetic cash session with a server-time rollover, often in a
  UTC+2/+3 zone) — testing this on CRSP/IBES US-cash-market data would silently substitute the wrong
  close.
- **Reel survivorship**: same caveat as idea #1(c) — a single posted result for one named rule is a
  selected instance, not evidence the class of "day-of-week reversal strategies" works broadly.
- **Spread-bet/CFD overnight financing**: a position opened Monday/Tuesday and held to a Tuesday
  23:15 close accrues at most one or two overnight financing charges depending on the exact hold —
  not modeled anywhere in this repo and not free to ignore at CFD-typical leverage.

### (d) Data: testable TODAY on a US30 daily proxy, with caveats

**DIA** (SPDR Dow Jones Industrial Average ETF) is a recognized index proxy in this repo's own code
(`xs_ranker.INDEX_PROXIES` names it alongside SPY/QQQ/IWM/VTI/VOO), pulled by the same yfinance daily
mechanism as SPY/QQQ (confirmed those two are already on disk in `bars_FX.parquet` and
`signal_structure/etf_monthly.parquet`; DIA itself was not directly found in a data file this pass,
only as a recognized ticker in code — a one-time daily pull closes that gap at zero cost, same
mechanism as every other ETF already on disk). **What daily DIA bars CAN test:** any version of
the rule expressible as "a Monday/Tuesday price-location-vs-SMA condition, entered and exited at
daily closes." **What they CANNOT test:** anything keyed to a 23:15 intraday close specifically (DIA's
own cash-market close is 16:00 ET, a different instant from a CFD's own session close), or any
version of the rule that depends on an intraday trigger rather than a daily OHLC.

### (e) Falsifiable question and primary metric

Once the entry condition is recovered from the source: *"Does [the exact recovered Monday/Tuesday
rule, SMA-25 gated] on DIA produce a long-only return at the stated holding period that beats a
buy-and-hold DIA benchmark over the same dates, net of a flat round-trip cost, with a majority of
individual years positive?"* Primary metric: mean return per occurrence of the setup, t-stat
blocked by ISO week (the dependence unit a weekly-recurring rule implies — same logic CANON §58
and the 2026-09-24 t-stat lesson in CLAUDE.md apply to any calendar-conditioned rule), reported
by-year (CLAUDE.md protocol 11: print by year before believing a positive) and against a random-day
long-only control of the same frequency, not just against cash.

### (f) Verdict: **NOT_A_HYPOTHESIS_YET**

The entry condition is the blocking gap, and it is squarely on the owner's side (the source video/
post needs to be re-watched or re-read for the actual rule — the 25-day SMA's role and what,
specifically, triggers a Tuesday entry/exit). The mechanism research above is not wasted regardless
of which exact rule turns up: it establishes the honest prior (a real but likely-extinct 20th-century
anomaly) that any recovered rule should be benchmarked against before anyone is impressed by a short
backtest window. To reach `READY_TO_CELL`: (1) the exact entry/exit rule from the source, verbatim;
(2) a one-time DIA daily pull if not already cached; (3) explicit acknowledgment that "23:15 close"
cannot be replicated on cash-market daily bars and the test is therefore of a *related*, not
*identical*, rule.

---

## 3. Daily long bias on US Tech 100

### (a) Reconstructed rule

| parameter | value as transcribed | status |
|---|---|---|
| instrument | US Tech 100 (Nasdaq-100 index, presumably via CFD) | GIVEN |
| direction | long bias | GIVEN |
| frequency | "daily" | AMBIGUOUS — daily rebalance? Daily hold-and-reassess? One daily entry window? |
| entry rule | not given | MISSING |
| exit rule | not given | MISSING |
| sizing/risk | not stated | MISSING |

Per the brief: this is "incomplete theory until the source is available" — treated as such below.
No entry/exit is invented.

### (b) Candidate mechanism: the one idea in this set with a real, well-documented driver

This is the one idea where "daily long bias on an index" maps cleanly onto a specific, heavily-cited,
and internally-verified mechanism: **the equity overnight/intraday return decomposition.**

- **Lou, Polk & Skouras (2019), "A Tug of War: Overnight versus Intraday Expected Returns," Journal
  of Financial Economics 134(1), 192-213, DOI 10.1016/j.jfineco.2019.03.011** — verified this pass by
  direct fetch of the EconPapers abstract/listing page. Finding, quoted directly: *"We document
  strong overnight and intraday firm-level return continuation along with an offsetting cross-period
  reversal effect, all of which lasts for years."* Mechanism proposed: investor heterogeneity /
  competing clienteles with different time-of-day trading preferences (retail activity concentrating
  overnight/at the open, institutional flow concentrating intraday), which fragments rather than
  concentrates return — i.e. the paper's own framing argues AGAINST a simple "always long overnight"
  strategy being a free lunch, because the overnight and intraday legs offset each other at the
  firm/strategy level over time.
- **This exact mechanism has already been measured on this repo's own CRSP panel**
  (`docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`, verdict `ANOMALY_CONFIRMED / STRATEGY_REJECTED`,
  cites Lou/Polk/Skouras 2019 by name as one of four papers behind the mechanism, alongside Cooper/
  Cliff/Gulen 2008, Berkman et al. 2012, Bogousslavsky 2019). The finding, read in full for this
  note: the overnight return premium in US equities 2013-2024 is **real, large (10.73 bps/day
  universe-wide, 8.25 bps/day in the most-liquid quintile), not a bid-ask-bounce artifact (it is
  STRONGEST in the most liquid names, the opposite of what microstructure noise predicts), and not
  decaying** (2.45 bps 2013-2017 → 5.91 bps 2018-2024) — **but an overnight-only strategy still loses
  to plain buy-and-hold at every cost level above ~4 bps one-way**, because the intraday leg in
  liquid names is ALSO strongly positive (+6.30 bps, t=3.88), and an overnight-only book sits out
  exactly the leg it would need to beat holding. The earnings-conditioned slice confirms the
  mechanism (overnight jumps 2.3x larger and intraday flips to significantly negative specifically on
  earnings-gap days) but still produces no tradable edge once borrow and multiplicity are accounted
  for.
- **This is a corpse, not a guess about what would happen — it is the single most load-bearing fact
  for this idea.** A "daily long bias" book built around "be long overnight, flat or light intraday"
  on an index is the SAME mechanism already tested and rejected as a strategy (while the underlying
  anomaly was confirmed as real) on the broader US equity universe. The specific index framing (Tech
  100 vs. the CRSP universe) and the exact entry/exit this reel proposes could differ enough to matter
  — but the honest prior, absent the recovered rule, is "the mechanism is real and well-published, the
  naive implementation of it already failed here against buy-and-hold."

### (c) Known failure modes

- **The buy-and-hold benchmark problem** — any "long bias" book must beat the instrument's own
  buy-and-hold, not just show a positive mean return; §3(b) shows this is the exact way the related
  mechanism failed.
- **Volatility drag reads as a fake edge or a fake failure** — `FINDING_2026-08-23`'s §6 shows a
  statistically-zero-mean series can still show a large negative CUMULATIVE return purely from
  compounding (`exp(-sigma^2 T/2)`); any single-name or single-index cumulative-return screenshot
  from a reel needs this same decomposition before being read as evidence either way.
- **CFD overnight financing** on a leveraged long "Tech 100" position is a real, continuous cost this
  mechanism's benefit has to clear, and it is not the same number as US equity borrow/short-cost — not
  modeled anywhere in this repo.
- **Reel survivorship**, same as ideas #1 and #2.

### (d) Data: testable TODAY on a daily proxy

**QQQ** is on disk now (`bars_FX.parquet`, `signal_structure/etf_monthly.parquet`) as a Nasdaq-100
daily-bar proxy, 2019-06-03 onward in the file inspected this pass (a longer QQQ history is almost
certainly pullable the same way CRSP/other ETF daily series are — QQQ itself inception 1999). **What
this tests:** any version of "long bias" expressible as a daily open/close rule (overnight-hold,
daily-rebalance-long, SMA-filtered long, etc.). **What it cannot test:** anything keyed to an
intraday entry/exit distinct from the daily open or close.

### (e) Falsifiable question and primary metric

Pending the recovered rule, the generically falsifiable version, informed directly by the existing
corpse: *"Does [the recovered daily long-bias rule] on QQQ produce a return attributable to something
other than (i) the instrument's own buy-and-hold drift and (ii) the already-measured overnight
premium, net of realistic CFD-equivalent costs?"* Primary metric: excess return over QQQ buy-and-hold
over the same dates (not raw return — CLAUDE.md's own standing rule, "a benchmark-relative number in
an absolute structure" — print both), t-stat blocked by month, with the overnight/intraday split
reported as a diagnostic regardless of the rule's exact shape, because that split is now free to
compute and directly answers "is this just the known overnight premium again."

### (f) Verdict: **NOT_A_HYPOTHESIS_YET**

Blocked purely on the missing entry/exit rule — the mechanism research is further along than for any
other idea in this set (a named, verified, internally-tested academic mechanism exists), which makes
this the cheapest of the four to move to `READY_TO_CELL` the moment the source supplies an exact
rule: a QQQ daily pull (if not already cached at full history) and the existing
`overnight_intraday_study` script's method are both already built.

---

## 4. Opening-range breakout on US Tech 100 (New York time)

### (a) Reconstructed rule

| parameter | value as transcribed | status |
|---|---|---|
| instrument | US Tech 100 (Nasdaq-100, presumably CFD/futures) | GIVEN |
| range window | "roughly 09:00-10:00" New York time | GIVEN, but imprecise ("roughly") and offset from the actual cash-market convention — see (c) |
| entry trigger | not given (presumably break of the range high/low, by analogy to idea #1, but NOT stated here and not invented) | MISSING |
| stop | not given | MISSING |
| target/exit | not given | MISSING |
| sizing | not given | MISSING |

### (b) Candidate mechanism

Same generic ORB mechanism as idea #1(b): the opening minutes concentrate overnight order-flow
resolution and institutional execution of overnight decisions; a sustained break of that range,
confirmed by volume, signals the day's dominant side as the "balance → imbalance" transition
(practitioner sources: FXOpen, Trade Ideas, BuildAlpha, grandalgo.com, LuxAlgo — none peer-reviewed;
cited as the standard practitioner framing, not as adjudicated evidence). Index-specific framing
found this pass: **the standard convention for this exact strategy on this exact instrument uses the
first 15-30 minutes after the 09:30 ET cash open** (several sources this pass: "9:30-9:45 ET" as the
most common window; one source frames it as "9:30-10:00 ET" for a wider range), not "09:00-10:00."
Also found: roughly **35% of a trading day's full-session high or low is set within the first 30
minutes** (LuxAlgo, practitioner, unverified by a primary academic source this pass), and that
**"double breaks" — price tagging BOTH the opening-range high and low in the same session — occur on
roughly 67% of trading days** (Edgeful, practitioner, unverified), which is directly relevant to the
rule's known failure mode below.

### (c) Known failure modes

- **The stated window may not match the actual market open.** US cash equity/index markets (and
  Nasdaq-100 futures' most liquid session) open at **09:30 ET**, not 09:00 — "roughly 09:00-10:00 New
  York time" either (i) means something other than the cash open (e.g., a CFD broker's own synthetic
  session, or includes 30 minutes of pre-market), or (ii) is an imprecise transcription of the
  09:30-10:00 convention found in (b). This is exactly the kind of gap the brief says to mark, not
  guess past.
- **Double-breaks**: if ~67% of sessions touch both the range high and the range low, a naive
  "buy-stop-above / sell-stop-below, no filter" version of this rule (the one literally transcribed,
  by analogy with idea #1, since no filter is stated) will frequently get stopped on one side and
  then see price reverse through the other — the failure mode idea #1 already names generically
  (the repo's own exit-rule study, `NEGATIVE_RESULTS.md` §62, found every stop variant tested LOSES
  to simply holding on a related US cross-section, for a structurally similar reason: a tight level
  gets hit on volatility, not on direction).
- **Intraday trigger / fill conventions**: same as idea #1(c) — a buy-stop/sell-stop fill is not the
  trigger price on a real gap-through; this repo's own convention (`night_exit_rules.py`: "a level
  below the open fills AT THE OPEN") is the right discipline to reuse here once intraday data exists.
- **CFD spread/financing and reel survivorship**: same as all three prior ideas.

### (d) Data: NOT testable on anything currently on disk; same gap as idea #1

Daily QQQ bars cannot construct an opening range — this requires sub-daily data by construction, no
daily proxy exists for an opening-range rule (collapsing to "does QQQ tend to continue its first-30-
minute direction" cannot be answered without the first 30 minutes). Free sources, same menu as idea
#1(d):

- **Yahoo Finance 1-minute bars via yfinance**: capped at 7 days per request (confirmed this pass),
  chainable to ~30 days — enough to spot-check the rule's mechanics and the window-timing question in
  (c), not enough for a multi-year backtest.
- **Alpaca**: confirmed this pass — Alpaca's intraday minute bars (1/5/15/30/60-minute) cover **US
  stocks, ETFs, and crypto**, explicitly **not forex**, but **QQQ is a US ETF**, so **Alpaca IS a
  viable free (with a funded or even unfunded paper account, subject to its own data-plan limits)
  source for QQQ intraday history specifically** — unlike idea #1's USD/JPY, which Alpaca cannot
  serve at all. This is the one idea in the set where a source already integrated with this
  programme's execution stack (Alpaca is the paper-trading broker named throughout `aegis-alpha-
  terminal`) could supply the needed data without a new vendor relationship.
- Dukascopy also carries index CFD data (including Nasdaq-100-tracking instruments) and remains a
  fallback if Alpaca's QQQ history or plan limits are insufficient for the backtest window needed.

### (e) Falsifiable question and primary metric

Once an entry/exit is recovered or declared: *"Does breaking the 09:30-10:00 ET QQQ opening range,
in the direction of the break, stopped on the opposite side of the range, produce a positive mean
daily P&L net of realistic ETF-level spread/slippage, over a multi-year out-of-sample window?"*
Primary metric: mean net daily P&L in bps per the one trade/day the rule implies (if one-trade/day,
by analogy with idea #1 — NOT stated here and must be confirmed), t-stat on the daily series, reported
beside the double-break rate on this specific window (a cheap, directly falsifying diagnostic: if QQQ
double-breaks as often as the generic ORB literature suggests, an unfiltered breakout-both-ways rule
is close to structurally guaranteed to struggle).

### (f) Verdict: **NOT_A_HYPOTHESIS_YET**

Blocked on the entry/exit rule (never stated, not invented here) AND the window-definition ambiguity
(09:00 vs. the standard 09:30 ET open). Moving to `READY_TO_CELL` needs: (1) the exact trigger/stop/
target from the source; (2) confirmation of whether "09:00-10:00 NY time" means the standard 09:30 ET
session or something else; (3) a QQQ intraday pull via Alpaca (the cheapest path — already-integrated
vendor, right asset class) sized to the backtest window the rule needs.

---

## 5. The workflow as a product

The owner's instinct — that the repeatable pipeline may outlast any individual idea — matches how
this repo already treats every other mechanism (Mission rule 2: a mechanism is only a hypothesis once
it has a named, falsifiable precursor; `pre-register-trial`'s BLOCKED/DUPLICATE/RESURRECTION/PASS
vocabulary exists for exactly this kind of recurring intake). Proposed shape, reusing existing roles
rather than inventing new infrastructure:

| step | what happens | receipt it writes | who/what does it |
|---|---|---|---|
| 1. Intake | the owner (or whoever watches the reel) fills the template below, verbatim, no paraphrase | a new file under `docs/social_intake/<date>_<slug>.md` | human (owner) |
| 2. Reconstruct | turn the verbatim rule into a parameter table (GIVEN/AMBIGUOUS/MISSING), exactly as done in §1-4 above | appended to the same intake file | **Sonnet** (reconstruction is reading comprehension + domain knowledge, not bulk extraction or judgment-under-uncertainty) |
| 3. Mechanism research | find and VERIFY (fetch, don't just cite from memory) the academic/practitioner literature behind the proposed edge; check `NEGATIVE_RESULTS.md` + `brain_query`/`aegis_postmortems` for an existing corpse first | a research note under `docs/research_notes/<date>/` (this file is itself step-3 output for four ideas at once) | **Sonnet**, same reason — this is exactly today's task |
| 4. Formal spec | once every GIVEN/AMBIGUOUS/MISSING gap is closed (by the owner supplying the missing piece, never by invention), write the exact executable rule: entry, exit, stop, sizing, timezone, instrument, cost model | a frozen spec file, same shape as `docs/TRIALS/PREREG_*.md` | **deterministic code / a human-reviewed spec**, not an LLM — the rule must be literal and reproducible, which is a `pre-register-trial`-shaped step, not a reasoning one |
| 5. Backtest | run the spec against the cheapest data that can test it (daily proxy where honest, intraday pull where the rule demands it), with realistic costs | a JSON receipt under the relevant `backend/data/optimus/` subtree + a `DATA_MANIFEST.md` row if new data was pulled | **deterministic code** (the engine's existing backtest machinery; `scripts/night_exit_rules.py`'s fill/cost conventions are the right template to reuse for anything breakout-shaped) |
| 6. Counterfactual / controls | matched twin, random-day control, by-year breakdown, leave-one-year-out — same discipline as every other trial in this repo (CLAUDE.md protocol 11) | appended to the backtest receipt | **deterministic code** |
| 7. Forward shadow | if the backtest survives, run it forward on paper (PRODUCT_EXPERIMENT licence — no significance gate needed to START a shadow, per the Three Licences) before any claim is made | a forward-accrual ledger, same shape as every other shadow book | **the existing paper-book/ledger machinery**, not a new build |
| 8. Verdict | adjudicate against the theory-table vocabulary (READY_TO_CELL / NEEDS_DATA / ALREADY_CLOSED / NOT_A_HYPOTHESIS_YET, or post-backtest: ADOPT / FAILED_VARIANT / MECHANISM_REJECTED per the "stop over-closing ideas" rule) | the research note's final section, or a `NEGATIVE_RESULTS.md` / `TRIALS/` entry if it closes | **a human sign-off** (Murat) for anything that would touch real capital; Sonnet/Opus can draft the verdict language, never finalize a capital decision |

**Where DeepSeek and Opus fit, per the owner's own question:** DeepSeek (the sole configured LLM
provider, per CLAUDE.md) is the right tool for step 2 only at BULK — if ten reels arrive in a batch,
DeepSeek extracts the literal rule text/parameters cheaply before a Sonnet pass reasons about mechanism;
for the volume seen today (one at a time), a human or Sonnet reading the transcript directly is
cheaper than standing up an extraction pipeline. Opus is not needed for steps 1-4 (reconstruction and
literature research do not need the heaviest reasoning budget) — it is worth its cost specifically at
step 6/8 where **measurement design** choices (which control, which block unit, which multiplicity
correction) have already burned real time in this repo when done carelessly (the 2026-09-24 t-stat
and the exit-rule counterfactual, both in `NEGATIVE_RESULTS.md`, are exactly the shape of mistake an
Opus-level design review catches before code is written, not after a number is already being quoted
to Murat).

### Intake template, for the owner to fill per reel (fill nothing in that the source didn't say — leave it blank and mark MISSING)

```
## Social intake: <date>

- Source URL / platform: 
- Creator handle (if known): 
- Timestamp in the video/post where the rule is stated (so "broker time"/session claims can be
  re-checked against the actual clip, not memory): 
- Instrument(s) named, EXACTLY as said: 
- Timezone/session convention named, EXACTLY as said (if none stated, write "NOT STATED" — do
  not assume a default): 
- Rule text, VERBATIM (transcribe or paste the exact words used for entry, exit, stop,
  target, sizing — if the creator shows a screenshot of code/platform settings, transcribe
  every visible parameter): 
- Performance claim made, VERBATIM, with whatever window/sample size was shown: 
- Anything the creator themselves flagged as a caveat (costs, slippage, a specific broker,
  "past performance", etc.): 
```

---

## Verdicts, in one line each

1. **USDJPY morning-range breakout: `NOT_A_HYPOTHESIS_YET`.** "Broker time" is not a timezone;
   no intraday FX data exists on disk (only daily `JPY=X`); needs the owner to resolve the
   timezone and a Dukascopy pull before it is testable at all.
2. **"Turnaround Tuesday" on US30: `NOT_A_HYPOTHESIS_YET`.** Entry condition was never given and
   multiple incompatible public rules share this name; the classical Monday-effect literature this
   idea invokes (Cross 1973, French 1980, Lakonishok & Maberly 1990) is real but, per the most
   thorough re-estimate found this pass (Smith & Robins, ASU), **the US weekend effect had already
   mostly vanished by 1975** — a sobering prior for any modern claim of the same shape. Needs the
   exact rule from the source; DIA daily bars can test it once the rule names a daily-expressible
   condition.
3. **Daily long bias on US Tech 100: `NOT_A_HYPOTHESIS_YET`**, but the closest of the four to
   `READY_TO_CELL`. It invokes a real, well-published, and **already internally tested** mechanism
   (Lou/Polk/Skouras 2019 overnight-return continuation; this repo's own
   `FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` confirmed the anomaly on CRSP but rejected it as a
   standalone strategy against buy-and-hold). QQQ daily bars are already on disk. Needs only the
   exact entry/exit rule from the source.
4. **Opening-range breakout on US Tech 100: `NOT_A_HYPOTHESIS_YET`.** Entry/exit never given; the
   stated 09:00-10:00 ET window likely mismatches the standard 09:30 ET cash-open convention this
   exact strategy class normally uses on this exact instrument. No intraday data on disk, but QQQ is
   a US ETF, so **Alpaca** (already this programme's paper broker) is a free, already-integrated
   source for the needed intraday history — unlike idea #1, which Alpaca cannot serve at all.

**Data gaps, summarized:** no intraday/sub-daily data of any kind exists on disk for any instrument
(confirmed directly in code: `book_cadence.py`'s "Minute bars do not exist on this machine"); daily
FX exists only as yfinance `=X` tickers inside `contest/bars/bars_FX.parquet` (USD/JPY, EUR/USD, etc.,
2019-06-03 onward); daily SPY/QQQ/IWM exist in multiple places already; DIA is a recognized proxy in
code but its own daily bars were not directly located this pass (a trivial, zero-new-infrastructure
pull). Free intraday sources, by instrument: **Dukascopy** for FX/index CFDs (ideas 1, 2, 4 as a
fallback), **Alpaca** for QQQ/US-ETF intraday specifically (idea 4, preferred — already integrated),
**yfinance 1-minute** for short-window spot-checks only (7-day cap per request, all four ideas).
