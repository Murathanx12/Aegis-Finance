# Murat's video/post trading ideas — adjudicated against the corpse ledger, the literature, and held data

**Date:** 2026-09-19. **Scope:** read-only research note. No commits, no lane
changes, no paid API calls, no `.env` reads. Sources: `NEGATIVE_RESULTS.md`,
`docs/TRIALS/`, `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`,
`docs/research_notes/2026-09-12/research_daytrading.md`, repo code
(`backend/services/event_vocabulary.py`, `backend/services/portfolio_optimizer.py`,
`backend/services/portfolio_engine.py`, `backend/services/arena/policies.py`,
`backend/strategy/{contract,adapters}.py`, `backend/data/arena/arena_books_v1.yaml`),
`C:\Users\mrthn\Aegis module\` TRIALS/README, and open web search (see per-idea
sources).

## Verdict table

| # | Idea | Verdict | Ledger citation | Cheapest next test | Cost |
|---|---|---|---|---|---|
| 1 | CXMT DRAM vs Micron — incumbent short / entrant long | **OPEN_AND_CHEAP** (as a general event class) + **NOT_A_HYPOTHESIS** (as the literal MU trade) | No prior trial; closest analogues §12 (supply-chain thesis, closed) and §26/§27 (rank-real, book-dead pattern) | Register `TRIAL-FOREIGN-ENTRANT-IC`: forward rank-IC of a new `foreign_competitor_entry`/`capacity_threat` typed-event id (does not exist in `event_vocabulary.py`'s ~40-id list) against incumbents in memory/panel/foundry names, PIT on disclosure date | $0 — reuses the typed-event pipeline already built; needs one new vocabulary id + registration |
| 2 | Read CEO earnings calls, buy suppliers early | **ALREADY_TESTED (closed) with a named reopening path** | NEGATIVE_RESULTS §12 (TRIAL-THEME-SUPPLY) — "revival requires event-conditioned links on daily data" | Register the event-conditioned successor: daily-resolution customer-momentum reaction keyed to a specific typed event (e.g. `guidance_change` or `earnings_preannouncement` citing supply constraints) in the CEO's own filing, not annual/monthly diffusion | $0 data (all on disk); ~1 registration + 1 build cycle |
| 3 | CEO insider buying signals conviction | **ALREADY_TESTED (open, forward-accruing) — do not re-register** | `TRIAL-INSIDER-IC` (insider_opp), `TRIAL-CMP-INSIDER-IC` (insider_cmp, decision 2027-07-21), NEGATIVE_RESULTS §46 (N1: post-disclosure move IS detectable at 0-1 day lag; pre-disclosure move is not) | None — the clocks are already running. Only new work: widen `insider_opp`/`insider_cmp` universe past the 12-name book if capacity allows | $0 (already wired); universe widening is the only marginal cost |
| 4 | Hedge funds / politicians buying new positions | **ALREADY_TESTED (open, forward-accruing) — do not re-register** | `TRIAL-CONGRESS-IC` (decision ≥2027-01-11), `TRIAL-ARK-IC` (decision ≈2027-02-10), NEGATIVE_RESULTS §26 (13F abnormal-ownership family: rank-real, book-dead, family closed at level/flow/residual) | None for Congress/ARK — clocks running. A literal "hedge fund 13F" variant is subsumed and closed by §26; do not reopen without a new mechanism (e.g. event-conditioned 13F, not level/flow/residual) | $0 |
| 5 | Options flow: institutional call volume vs price gap | **ALREADY_TESTED at institutional/OptionMetrics resolution (closed)**; retail "unusual options activity" is **OPEN_BUT_NEEDS_DATA** | NEGATIVE_RESULTS §27 (TRIAL-OPT-COHORT — all 7 mechanism classes incl. `os_ratio`/`pc_volume` flow rejected, DSR 0.0000 at n=173) | A daily, event-conditioned retail-UOA arm (large call sweep vs pre-event price drift) needs live options chain data we do not hold | Alpaca "Algo Trader Plus" $99/mo (adds OPRA options) or Polygon Advanced $199/mo — per `research_daytrading.md` |
| 6 | ICT ritual (Asia/London sweep → FVG reversal, 1:2 RR) | **NOT_A_HYPOTHESIS** as stated; **OPEN_BUT_NEEDS_DATA** as a registered test | No academic literature (only practitioner/blog claims); `docs/research_notes/2026-09-12/research_daytrading.md` arithmetic (11-71 sessions to power a t=2.8 test; none of the cited day-trading literature shows a population edge near 1%/day) | Register a mechanical FVG-reversal rule on Alpaca 1-min bars (Lane D contract), scored against its beta-matched control twin, retail-cost model | $0 data (Alpaca 1-min bars on disk / free tier); the honest prior is null given Barber-Lee-Liu-Odean and Chague-De-Losso-Giovannetti base rates |
| 7 | Buy close / sell open ("overnight anomaly") | **ALREADY_TESTED — verdict stamped, do not re-run** | `docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`: `ANOMALY_CONFIRMED / STRATEGY_REJECTED` | §8's named reopeners: (i) 1990-2012 CRSP open-price pull, (ii) intraday first-30-min timestamps on earnings gaps (needs TAQ) | 1990-2012: one WRDS pull; TAQ intraday timestamps: on disk already per the finding, needs a new build, not new purchase |
| 8 | Social mentions rising → read comments for debate vs hype | **OPEN_BUT_NEEDS_DATA** (one paragraph; pipeline spec owned by a parallel agent) | — | See below | — |
| 9 | Coursera list / portfolio construction critique | **OPEN_AND_CHEAP** — the infrastructure (fractional Kelly `ce_kelly`, HRP, mean-CVaR, Black-Litterman) already exists in code but is used in ~1 of 10 live paper books | THE BOTTLENECK section (composite_top_k, 99.5% one-factor); `backend/data/arena/arena_books_v1.yaml` (7 `equal_weight`, 2 `inverse_trailing_vol`, 1 `ce_kelly`) | Promote a second arena arm: same composite score, `ce_kelly` sizing (already coded in `backend/services/arena/policies.py::size_ce_kelly`) vs the EW control twin, worst case printed per CLAUDE.md protocol 4 | $0 — no new code, only a new book registration + a Kelly-fraction/IC-prior decision |

---

## 1. CXMT vs Micron — foreign-competitor-entry event class

**The literal trade.** CXMT (ChangXin Memory Technologies) IPO'd in Shanghai in
July 2026 at a ~$487-500B market cap (466% first-day pop), and by September
2026 held ~10% global DRAM revenue share. Two distinct CXMT-linked Micron
drawdowns are visible in the public record:

- **2026-07-27: MU −5%**, same-day reaction to CXMT's IPO debut / valuation —
  the cleanest idiosyncratic CXMT event.
- **2026-09-14: MU −5.2%**, closing at $923.97, ahead of the Sept 30 FQ4
  print — but this sits inside a **sector-wide** semiconductor selloff (SOXX
  down 3.6% for the month to Sept 10; leveraged SOXL-type funds down >14%).
  This day is **not** cleanly attributable to CXMT; it is confounded with
  broad chip-sector beta, which is exactly the "is this a mechanism or factor
  beta" question CLAUDE.md requires asking.

**The "compatible with AMD/Nvidia systems" framing is partly right and partly
conflated.** What is actually documented through September 2026 is CXMT DDR5
**desktop/consumer memory** gaining BIOS/motherboard qualification on AMD AM5
and Intel platforms (Gigabyte, MSI validating CXMT DIMMs up to 8,200 MT/s).
That is real and growing. It is **not** the same claim as CXMT DRAM/HBM being
qualified inside Nvidia/AMD **AI accelerators** — CXMT's HBM production was
reported to begin only "at the end of 2026," and no accelerator-level
qualification is documented in the sources found. Murat's framing collapses
two different supply chains (consumer DDR5 vs. datacenter HBM) into one; the
short thesis on Micron is strongest for the commodity-DRAM/consumer segment
and much weaker/unresolved for the HBM segment that actually drives Micron's
AI-cycle valuation.

**Point-in-time problem.** CXMT's capacity ramp and motherboard-qualification
news has been public and incremental for months (Gigabyte/MSI BIOS releases,
IPO roadshow disclosures, capacity research reports) — this is not a single
surprise catalyst knowable only after the fact, which is good for a
pre-registered forward test (no leakage risk) but bad for "trade the news":
by the time a retail viewer sees a video about it, the information has been
public and priced incrementally for months.

**Typed-event vocabulary check.** `backend/services/event_vocabulary.py`
defines ~40 ids (`earnings_report`, `guidance_change`, `mergers_acquisitions`,
`tariff_or_trade_policy`, `product_launch_or_innovation`,
`contract_loss_or_termination`, `regulatory_approval`, `sanction`, etc.).
**None of them is a foreign-competitor-entry / capacity-threat class.** The
closest neighbors are `tariff_or_trade_policy` (export-control angle) and
`product_launch_or_innovation` (fires on the entrant's own announcements, not
on the incumbent-relevant reading of them). This is a genuine gap, not a
disguised existing test.

**Generalized hypothesis and what would separate it from beta:** "when a
credible foreign entrant achieves qualified compatibility/capacity parity in
an incumbent's product category, the incumbent underperforms its own
sector/factor benchmark over the following N days, and the entrant (if
tradeable) outperforms its market." What would separate this from ordinary
sector or momentum beta: the incumbent's move should be **larger than its
beta-matched sector control on the specific day(s) the qualification news
lands**, net of the sector-wide component (the Sept 14 example fails this
test as stated; the Jul 27 example needs the same check run formally). §12's
supply-chain corpse and §26/§27's "rank information real, long-only book
dead" pattern are the standing priors to carry in: even if a rank signal
exists, a long-only top-decile book has repeatedly failed to harvest it in
this programme (three independent construction classes, per §26/§27).

**Verdict:** as a literal single-name MU short/CXMT long idea, this is
**NOT_A_HYPOTHESIS** yet — no observation separates the Sept 14 move from
ordinary chip-sector beta, and the "AMD/Nvidia compatible" framing conflates
two different memory markets. As a generalized **foreign-competitor-entry
event class**, it is **OPEN_AND_CHEAP**: the typed-event extraction pipeline,
the PIT store, and the forward-IC estimator pattern (identical machinery to
`TRIAL-CONGRESS-IC`/`TRIAL-ARK-IC`) already exist; only a new vocabulary id
and a fresh pre-registration are missing.

---

## 2. Read CEO earnings calls → buy suppliers early

NEGATIVE_RESULTS §12, **TRIAL-THEME-SUPPLY**, is fully adjudicated: the slow
arm (annual formation, 12-month hold, customer-momentum links) rejects on
both pre-registered kill conditions — B−A decile spread t=0.10 at annual
cadence, and the fast arm (batch 3b) showed real monthly information that
dies to its own 70% churn. The closing line is explicit: **"Revival requires
a different mechanism class (event-conditioned links on daily data),
registered fresh."**

What an event-conditioned version would be: instead of a slow, diffuse
customer-momentum panel refreshed annually, key the supplier trade to a
**specific typed event** in the customer's own disclosure — a CEO
earnings-call statement flagged as `guidance_change` or
`earnings_preannouncement` that names a supply/component constraint (the
exact "what's holding back growth" language Murat describes) — and measure
the supplier's forward return over a **daily** window starting at that
event's disclosure timestamp, not at a monthly/annual rebalance. This reuses
the L2 typed-event extraction already built (`backend/data/optimus/*/L2_typed_events_*`)
and the PIT discipline already proven on `TRIAL-CONGRESS-IC`/`TRIAL-ARK-IC`. It
does **not** reuse TRIAL-THEME-SUPPLY's registration — this is a genuinely
different mechanism class per the closing note, so it needs its own
pre-registration, not a reopening of the closed trial.

**Verdict: ALREADY_TESTED** (the diffuse/annual version), with the
event-conditioned successor **OPEN_AND_CHEAP**: data (customer-supplier links
+ typed events + daily prices) is already on disk; the work is a fresh
`pre-register-trial` + build.

---

## 3. CEOs buying shares with their own cash signals conviction

This is **already running as two live forward trials — do not re-register.**

- `docs/TRIALS/TRIAL-INSIDER-IC.md` — all open-market buyer count
  (`insider_opp:`), forward collector wired since 2026-06-16, decision after
  ≥1 forward window once accrual is sufficient.
- `docs/TRIALS/TRIAL-CMP-INSIDER-IC.md` — Cohen-Malloy-Pomorski-classified
  **opportunistic** (non-routine) buyers only (`insider_cmp:`), decision date
  **2027-07-21**, with a backtest prior from the Aegis module
  (BRAIN-003: large/mid +17 bps/mo net, t=1.40; FF5+UMD alpha +102 bps/mo,
  t=1.89; microcap null) and a self-declared adverse prior that the
  Cohen-Malloy-Pomorski headline (82 bps/mo) has likely decayed 60-70% since
  2012 to ~30-40 bps/mo (algorithmic trading, 10b5-1 growth).

**What must not be re-registered:** NEGATIVE_RESULTS §46 (N1) already
answered the precondition question — *does the abnormal return accrue before
disclosure, which would make the signal real but uncopyable?* Measured on 608
Form 4 events: **pre-disclosure moves are not detectable** at 0-2 day lag;
**post-disclosure moves ARE detectable and positive** at 0-1 day lag
(+2.30%, MDE 1.48 at 0d; +1.80%, MDE 1.76 at 1d). This licenses COPY-LAB to
continue — it does **not** itself constitute an edge (the corpus is 5 filing
days deep, mostly one filing day). The caveat that must travel with any reuse
of this number: it is a licence to continue, not evidence of an edge.

The Aegis module also has `TRIAL-BRAIN-009-insider-cluster` (≥2-3 distinct
buyers beat the ≥1-buyer universe) and `TRIAL-TEACHER-LIBRARY-1` (forward
CONFIRM of BRAIN-003, +1.5%/21d expected, reservation-gated). Both are
already registered; re-deriving "CEO insider buying" from scratch would
rebuild machinery that exists and re-spend a pre-registration slot for
nothing.

**Verdict: ALREADY_TESTED (forward-accruing).** The one legitimate marginal
action is widening `insider_opp`/`insider_cmp` past the current 12-name book
universe if paper-book capacity allows — not a new hypothesis.

---

## 4. Hedge funds / politicians (Trump) buying new positions

Also **already running — do not re-register.**

- `docs/TRIALS/TRIAL-CONGRESS-IC.md` — STOCK Act disclosures, PIT on
  `disclosureDate` (never `transactionDate`, since trades disclose up to 45
  days late), score = distinct buying members − distinct selling members over
  a 90d window. Honest prior stated at registration: **weak-to-null**
  (pre-2012 studies like Ziobrowski found abnormal returns; post-STOCK-Act
  studies like Belmont et al. 2022 found the edge faded, and the ≤45-day
  disclosure lag further stales it). Earliest decision 2027-01-11.
- `docs/TRIALS/TRIAL-ARK-IC.md` — same-day ARK holdings-diff flow, honest
  prior **weak-to-null and possibly negative** (post-2021 literature on
  copying ARK flows is unflattering: crowding, price impact). Earliest
  decision ≈2027-02-10.
- NEGATIVE_RESULTS §26 (TRIAL-ABIO-KIRK) — the 13F "hedge fund buying"
  family (level, flow, AND Kirk-style abnormal/residualized ownership) is
  **closed on all three constructions**: `io_level` small-cap carries a t=11.29
  rank-IC and books ZERO gross excess return (t=+0.02) — the eighth 13F
  variant to show this rank-real/book-dead pattern. `io_chg` (the literal
  "institutions buying what they didn't own before" signal) is the
  **lowest**-IC arm, not highest, and its sign is **contrarian**
  (Dasgupta-Prat-Verardo 2011 direction, not momentum).

A literal "hedge fund just opened a new position" signal is a version of
`io_chg`/13F flow, already measured and rejected at pooled t_ic −2.37. The
politician-specific version is genuinely different data (STOCK Act, not 13F)
and is separately and correctly still open per `TRIAL-CONGRESS-IC`.

**Verdict: ALREADY_TESTED (forward-accruing for Congress/ARK; closed for
generic 13F hedge-fund flow).** No new registration warranted; the honest
prior for both open trials is explicitly weak-to-null, set before any data
existed.

---

## 5. Options flow: institutional call-volume/price gap

NEGATIVE_RESULTS §27, **TRIAL-OPT-COHORT**, closes the option-implied
cross-sectional family on **all seven mechanism classes** the literature
offers — level (`iv_atm`), realized-vs-implied spread, skew, term structure,
**and flow** (`os_ratio` = option/stock volume ratio, `pc_volume` = put-call
volume). This is registered as ONE cohort specifically so a rejection could
not be worked around by re-slicing: all seven arms reject; DSR = 0.0000 at
n_trials=173 (best observed monthly Sharpe +0.0396 vs an expected max-under-null
of 0.3816). `os_ratio` is a **significant anti-signal** (net −92.3 bps/mo,
t=−6.68 in small caps) — Johnson-So (2012) predicted the opposite sign, and
the direction was frozen before the run.

**Is retail-visible "unusual options activity" the same variable as the
rejected flow arm?** Partially, not identically. `os_ratio`/`pc_volume` were
measured on **OptionMetrics** full-market daily aggregates at **monthly**
cross-sectional resolution — the same construction class as most retail UOA
screeners (elevated volume vs. open interest or average volume), so the
rejection is directly relevant prior evidence, not just an analogy. What it
is **not**: an event-conditioned, intraday/daily-resolution signal on a
single large sweep near a specific catalyst, which is the form most retail
UOA tools and this idea actually describe ("gap between institutional call
volume and price" reads as a same-day or next-day divergence, not a
monthly-rebalanced rank).

**What a daily, event-conditioned version needs:** live options-chain data
this repo does not currently hold — no OPRA/CBOE feed, no Alpaca options
data is wired anywhere in `backend/` (confirmed by grep: only `^VIX`/`^SKEW`
index tickers and `CBOE:` ticker-regex parsing exist, no options-chain
ingestion). Per `docs/research_notes/2026-09-12/research_daytrading.md`,
priced options: Alpaca "Algo Trader Plus" $99/mo (adds OPRA options data to
the existing Alpaca account), or Polygon.io Advanced $199/mo (real-time,
20yr history). Given the standing prior — three independent flow arms
already rejected on better (WRDS OptionMetrics) data — the honest prior for
a retail-resolution version is also weak-to-null, and it should be priced as
an $99-199/mo recurring cost against that prior before purchase.

**Verdict:** the institutional/monthly flow mechanism is **ALREADY_TESTED**
(closed, §27). The event-conditioned retail-visible daily version is
**OPEN_BUT_NEEDS_DATA**, and the correct framing for anyone proposing it is
"why would daily/event resolution overturn three closed flow arms" — not a
fresh assumption of edge.

---

## 6. ICT day-trading ritual (session sweep → FVG reversal, 1:2 RR)

**No academic literature exists for this specific ritual.** Web search turned
up only practitioner/blog sources (TradeZella, LuxAlgo, BuildAlpha, Backtrex,
Pineify) making unverified claims ("70-80% win rate," "20-30 pips per
session") with no peer review, no out-of-sample discipline, and — per one of
the more careful practitioner posts found (StatOasis) — an explicit warning
that a single ICT/FVG backtest with this many discretionary
parameters ("each one is a knob... turned every one of them before you saw
the result") proves close to nothing even in pure noise. This is the textbook
shape of a technique with no falsifiable, pre-registered evidence behind it.

**What a registered test on Alpaca 1-minute bars would look like:** this repo
already has the scaffolding. `backend/strategy/contract.py`'s `Strategy`
dataclass and Lane D's 30-minute book (per
`docs/research_notes/2026-09-12/research_daytrading.md`) establish the
pattern — universe, signal, construction, hold rule, sizing, cost model,
benchmark, objective, all frozen before the first decision, PRODUCT_EXPERIMENT
licence (no significance gate needed to *try* it). A mechanical, non-discretionary
encoding of the ritual (session-high/low computed from Asia 20:00-00:00 ET and
London 03:00-05:00 ET windows on Alpaca 1-min bars; "sweep" = wick through the
level; FVG = a 3-candle imbalance on the entry timeframe; target = 2R, stop = 1R)
scored against its **beta-matched control twin** (B3 in the roadmap: every
book gets a twin at creation) is cheap to build and cheap to run — the data
(Alpaca 1-min bars, 1.25M rows / 3,060 symbols already on disk) is free.

**Cost model for a 1-min hold:** the research note's own arithmetic is
decisive here even before a line of ICT-specific code is written. At retail
one-way cost (25bps, per repo convention) and even a *conservative* 1x daily
turnover, round-trip cost alone is 50bps/day — half of any plausible daily
target — and 2x turnover (each sweep-then-reversal round trip, several times
a session) consumes the entire 1%/day target on cost alone. Barber-Lee-Liu-Odean
(Taiwan) find <1% of day traders reliably profitable net of fees; Chague-De-
Losso-Giovannetti (Brazil, 2020) find 97% of persistent day traders lose
money; Jordan & Diltz (2003, US) tie day-trader profitability to Nasdaq beta,
not skill.

**Honest prior:** null, and specifically null in the same way as
NEGATIVE_RESULTS §1 (the timing strategy loses to buy-and-hold) — a
discretionary-looking ritual dressed as mechanical rules, no peer-reviewed
evidence, and a retail cost structure that consumes the entire plausible edge
before any statistical test is run.

**Verdict:** the ritual as described (a discretionary human process — "wake
up," "mark," "wait," "drop to 1-minute") is **NOT_A_HYPOTHESIS**: nothing
about it, stated this way, would separate a winning trade from a trader who
simply got lucky on a coin-flip-shaped setup, because entry/target/stop
selection has enough discretionary freedom to fit almost any outcome after
the fact. A **mechanized, parameter-frozen version** registered as a
PRODUCT_EXPERIMENT book is **OPEN_BUT_NEEDS_DATA** — not new data (Alpaca
1-min bars are free/on-disk), but a properly frozen, non-discretionary
specification of "sweep" and "FVG," which does not exist yet.

---

## 7. Buy at close, sell at open ("overnight anomaly")

**Already fully adjudicated. Do not re-run.**
`docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` — **verdict stamped:
`ANOMALY_CONFIRMED / STRATEGY_REJECTED`, no licence requested.**

Summary of what was measured (CRSP daily, 2013-2024, 11.3M stock-days,
0.0015% reconciliation failure rate against `retx`):
- The overnight premium is **real** (universe +10.73 bps/day, t=8.71; MU
  +13.24 bps/day, t=4.15) and **not** a bid-ask-bounce artifact — it is
  *strongest* in the most-liquid quintile (overnight +8.25 bps t=5.94,
  intraday **also** +6.30 bps t=3.88), the opposite of what microstructure
  noise predicts.
- The strategy still **loses to buy-and-hold at zero cost** (22.17%/yr Sharpe
  1.69 vs. 41.61%/yr Sharpe 1.86), because the liquid names you could
  actually trade have a positive intraday leg too — exactly the leg an
  overnight-only book sits out. Breakeven one-way cost is 4.13bps, and even
  winning that race still loses to holding.
- "Down 99.2%" is a **volatility-drag artifact**: MU's intraday mean is
  statistically indistinguishable from zero (t=−0.21); a zero-mean 222bps/day
  series loses ~52% purely from `exp(−σ²T/2)` compounding, not from a real
  negative edge.
- Earnings-conditioned slice (§7b): the mechanism is **confirmed** (overnight
  jump 2.3x larger and intraday flips significantly negative on earnings
  gaps), but conditioning finds a **bigger** bet, not a **better** one — the
  Sharpe on the earnings-gap overnight leg (0.94) is statistically the same
  as the unconditional Sharpe (0.96), and the tradable-looking intraday short
  on earnings gaps (t=−1.98) does not survive the session's own multiplicity
  correction (~20 slice comparisons, CANON §63 BH-FDR).

**What would change the verdict — §8, verbatim scope:**
1. The 1990-2012 CRSP window (currently untestable — no `openprc` column on
   disk pre-2013) — "if the effect is much larger pre-2013 the decay story
   changes, though the cost arithmetic does not."
2. **Already partly answered by §7b**: the earnings-conditioned slice. What
   remains open per §8/§7b's own close is **intraday timestamps** — "was the
   reversal in the first 30 minutes?" — which needs TAQ, and TAQ "is on
   disk," so this is a build task, not a purchase.
3. Real execution data at the opening/closing auction, which could move the
   breakeven cost — but it would have to move past buy-and-hold's zero-cost
   lead, "which is the harder problem."

**Lou-Polk-Skouras and Knuteson, as requested.** Lou, Polk & Skouras (2019,
JFE 134(1):192-213), "A Tug of War: Overnight vs. Intraday Expected Returns,"
is directly cited in `research_daytrading.md`'s web-findings summary: overnight
and intraday return components persist and **reverse against each other for
years**, with institutional ownership tracking the intraday component more
than the overnight one (a retail-flow explanation for the overnight premium
this repo independently measured). No Knuteson citation was found in-repo or
via search in the time available for this note; if Murat means a specific
paper/talk, it should be named so it can be checked — nothing under that name
surfaced in `docs/` or a general web search tied to this overnight/intraday
literature.

**Verdict: ALREADY_TESTED.** Citing this finding's headline numbers again
without its §5 (strategy loses to holding), §6 (vol-drag), or §7b (mechanism
confirmed, trade still doesn't survive) sections would repeat the exact
error the finding exists to prevent.

---

## 8. Social media mentions rising → read comments for debate vs. hype

One paragraph, per instructions (a separate agent owns the pipeline spec).
This is **OPEN_BUT_NEEDS_DATA**, not a tested-or-closed item: no ledger entry
adjudicates it directly, and the repo holds no social-mentions or comment-text
ingestion today (`LunarCrush` MCP tooling exists in this environment's tool
list but is not wired into any collector under `backend/services/`). The
sharper, falsifiable version of Murat's instinct — per CLAUDE.md's "every
intuition is owed one question" — is not "mentions are rising" (a volume
proxy, likely just re-measuring attention/momentum beta, already a crowded
construction class in this ledger's rank-real/book-dead pattern) but
specifically **debate-vs-consensus in the comment thread as its own variable**,
independent of mention count: a typed read of whether replies are contesting
or amplifying the post. That is a genuinely different, event-conditioned
signal from raw volume, and whoever writes the pipeline spec should register
it against that distinction rather than against "buzz."

---

## 9. Coursera list / portfolio construction critique

Murat's diagnosis is correct as stated: THE BOTTLENECK section of
`CLAUDE.md` already names it at the **selection** layer (`composite_top_k`
over one 12-1-momentum-dominated signal). What he is separately noticing is
the **construction** layer — position sizing given a selected list — and here
the repo is in a different, better place than "five equal-weight names"
suggests, but the good code is not where the money is.

**What decision theory under a declared utility prescribes, briefly:**
- **Kelly / fractional Kelly** — maximize expected log-wealth (equivalently,
  long-run compound growth) rather than one-period mean-variance; full Kelly
  is provably growth-optimal but has ruinous variance in practice, so
  practitioners use a fraction (`kelly_fraction`) of the full bet.
- **Mean-variance with estimation error** — classical Markowitz optimization
  is extremely sensitive to estimated means, and DeMiguel, Garlappi & Uppal
  (2009, *Review of Financial Studies* 22(5)) is the standard citation for
  why: across 7 empirical datasets and 14 optimization models, **naive 1/N**
  diversification is not reliably beaten out-of-sample by any of the
  "optimal" models, because estimation error in the mean-return vector
  swamps the theoretical gains of optimization. This is the honest reason
  1/N (equal weight) is a defensible **default**, not merely a lazy one — but
  it is a default for the *allocation-under-uncertainty* problem, not a
  license to ignore a signal you already trust enough to select on.
- **Risk parity** — allocate by equal marginal risk contribution rather than
  equal dollars, sidestepping the mean-estimation problem mean-variance has
  (only volatility/covariance needs estimating, which is more stable) at the
  cost of ignoring expected-return information entirely.
- **Black-Litterman** — the standard way to inject a *view* (Murat's own
  conviction, or a model's) into an equilibrium-anchored portfolio without
  the corner-solution instability of raw mean-variance: blend a market-implied
  prior with declared views and their confidence, Bayesian-style.

**What the repo already implements — this is the finding worth printing:**
- **Fractional Kelly exists and is coded correctly.**
  `backend/services/arena/policies.py::size_ce_kelly` implements exactly
  Grinold's rule (`w = kelly_fraction * IC * z / sigma`, IC a **declared**
  prior never fit to the book's own history, per-name capped without
  redistribution, gross scaled down not up). It is registered as one of the
  arena's own sizing arms and tested against an equal-weight control twin —
  this is the right methodology, already built. But
  `backend/data/arena/arena_books_v1.yaml` shows it used in **exactly 1 of
  10** live books; the other 9 are `equal_weight` (7) or
  `inverse_trailing_vol` (2).
- **HRP (Hierarchical Risk Parity) is implemented and wired**, not just a
  library demo: `backend/services/factorial_pm.py` and
  `backend/services/portfolio_intelligence/rules.py` both call
  `portfolio_optimizer.optimize_hrp` with an explicit equal-weight fallback
  when as-of history is insufficient (never silently defaulting).
- **Mean-CVaR and Max-Diversification exist** in
  `backend/services/portfolio_optimizer.py` but are reachable only through
  `backend/routers/portfolio.py`'s `/optimize` and `/compare` endpoints — a
  user-facing "Bloomberg PORT style" calculator for the website's
  browser-localStorage portfolio tool (per CLAUDE.md: "portfolio lives in
  browser localStorage"), **not** wired into any live paper book's
  construction.
- **Black-Litterman is implemented** (`backend/services/portfolio_engine.py`,
  using `pypfopt.BlackLittermanModel` with a market-implied prior), also
  reached only via the website's `PortfolioEngine` router — again the
  user-facing calculator, not the arena/paper-book pipeline. (Note:
  `portfolio_optimizer.py`'s own module docstring claims "Augmented
  Black-Litterman: Entropy pooling" as one of its five methods, but no
  entropy-pooling or Black-Litterman code exists in that file — the real
  implementation lives in the differently-named `portfolio_engine.py`. This
  is a doc/code mismatch worth a one-line fix, not a missing capability.)

**The recommended ONE construction change:** promote a **second live arena
book** — same composite selection (so this is a construction test, not a
selection test, per THE BOTTLENECK's own rule that a new mechanism must
arrive as its own book) — using the **already-coded `ce_kelly` sizing**
against the existing equal-weight control twin. This requires no new code,
only (a) a declared `ic_prior` and `kelly_fraction` (never fit post hoc), and
(b) a book registration. It directly tests DeMiguel-Garlappi-Uppal's question
in-house: does capital-weighting by conviction beat 1/N net of costs, on
*our* signal, with *our* estimation error — rather than assuming either
textbook answer.

**Worst case in dollars (CLAUDE.md protocol 4), for the existing `ce_kelly`
book (line 227 of `arena_books_v1.yaml`) as a template for a second one:**
`size_ce_kelly` is a **capital-holding** sizing rule by construction — capped
conviction becomes cash, not a forced bet, and gross is scaled down (never up)
to `max_gross` (1.0 in the current book). So its worst case is bounded the
same way an equal-weight k=12 book's is: `n names × max_single_name% × stop%`
for the largest admissible single-name loss, and `Σ|notional| ≤ max_gross ×
equity` for gross — it **cannot** exceed the equal-weight control's gross
exposure, because `max_gross` is enforced identically across both sizing
rules. The place Kelly sizing changes the worst case is **concentration**,
not gross: with `max_single_name=0.15` (the book's registered cap) and k=12,
the theoretical worst single-name loss at a 3% stop is `0.15 × 0.03 = 0.45%`
of equity per name — identical to what an equal-weight book capped at the
same `max_single_name` would allow — but Kelly sizing can *put more names
near that cap simultaneously* when conviction is broadly high, which equal
weight structurally cannot (it always spreads to `1/12 ≈ 8.3%` regardless of
conviction). A second `ce_kelly` book should print, before going live, the
worst-case scenario where every selected name clears `max_single_name` at
once: at k=12, `max_single_name=0.15`, `max_gross=1.0`, that is capped at
gross 100% by construction (the `scale = max_gross / gross` renormalization
in `size_ce_kelly` when `gross > max_gross`), so the dollar worst case at a
3% stop is **3% of book equity** in the pathological all-capped case — the
same figure a fully-invested equal-weight k=12 book at the same stop would
show, which is the correct baseline comparison to print alongside it.

---

## Notes on scope and honesty

Several of these ideas (3, 4, 7) are not really open questions at all — they
are already-running experiments or fully-closed findings, and the highest-value
action available to Murat is reading the existing receipts rather than
re-spending a pre-registration slot. Idea 9 is the one place this note found
genuine repo *capability* sitting unused rather than untested code: the
fractional-Kelly and HRP machinery exist, are correctly built, and are simply
not the default. That is a cheaper fix than it looks, and its cost is one
book registration, not new research.
