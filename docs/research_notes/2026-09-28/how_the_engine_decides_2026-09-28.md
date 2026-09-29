# How the engine decides: inputs, weights, one night's orders, and a probabilistic alternative (2026-09-28)

Written by the night operator on 2026-09-28 from code and tonight's receipts (sim session
`f496cf18b433`, mode `paper_profit`). Licence of everything here: `PRODUCT_EXPERIMENT`, paper money
only. Nothing in this note changed a cap, a stop, a size or the live plan path.

**The one-line answer.** Tonight, a paper order is decided by **the candidate funnel's score order
and hand-set caps, and by nothing else**. Every learned or news-driven component on the path is
asleep, because each waits for graded outcomes that do not exist yet. The earliest date one of them
can change a PROBE order is **2026-11-11**.

## 0. The path in one picture

```
funnel_night10.json (25 names, 2026-09-24, score = hand-weighted profitability + low vol)
   -> investment_committee.shortlist (fresh <= 10 d, one line per issuer)       22 names
   -> decision contract: drop names REFUSED as negative-EV (ALLE, SON)
   -> E[r] layer er_<asof>.json (6 components)       -> ALL asleep at h=5
   -> policy_state.plan_view -> probe_order (h=5)     -> "shortlist order (no component)"
   -> probe_weights: equal, 10 x 2% = 20% gross
   -> pc_broker.plan_orders (12% name cap, 1.00x gross, 2% ADV, 10% drift band, $250 min)
   -> pc_broker.submit (market DAY order, paper account PA37CSAUFCQR)

ranking.json (LightGBM on 24 price features) -> EXPLOIT: top20_net_rel_21d = -1.07% -> MEASURED_NEGATIVE, no orders
```

File and line references for every step are in `sim_run.u_plan` (`scripts/sim_run.py`, steps at
~:1091-1431). The PROBE book trades because its gate is `UNMEASURED_TRADE_SMALL` (0 of 21 scored
days). The EXPLOIT book does not trade because the ranker measured negative.

## (a) Every input that could reach a decision, tonight

| input | file | rows | age tonight | did a decision READ it tonight? |
|---|---|---|---|---|
| candidate funnel | `backend/data/funnel_night10.json` | 25 candidates (of 5,339 screened) | 4.4 d (generated 2026-09-24 02:48Z) | **YES**. It is the whole PROBE set and its order |
| price bars (survivorship-free) | `optimus/prices_deep/bars.parquet` | 6,799,858 | newest bar 2026-09-25 (0 sessions behind the last closed session) | **YES**, by the ranker (EXPLOIT, refused) and the sizing sigma |
| ranker output | `pc_book/2026-09-28/ranking.json` | 2,907 eligible names, top 25 stored | built 21:28 HKT on 09-25 bars | read. EXPLOIT refused, so it moved no order |
| analyst revisions | `optimus/analyst/target_revisions.parquet` | 393,602 (pulled tonight, 60 min) | fresh | read into E[r] `revision_flow` at h21/h63. **Moves no PROBE order** (no rule table at h5) |
| SEC fundamentals | `optimus/fundamentals_sec/sec_facts_history.parquet` | not counted | 2026-09-27 | **NO path** to `u_plan`. The funnel's profitability comes from Finnhub/yfinance, not SEC |
| investigator forecasts | `optimus/predictions.jsonl`, `investigator:evidence_v3` | **270 new tonight** (135 names x h1/h5); ledger 28,647 records | written 13:30-14:04Z today | read into E[r] `investigator_dir` as p = 0.51-0.52, **asleep**: "no graded calibration at h=5" |
| thesis cards | `optimus/thesis_cards/<date>/` | 158 card files across dates; tonight's run in progress | 1 d | read (card p = 0.56-0.60 carried), **asleep**: "0 graded of 30" |
| catalyst dates (from cards + `pm_catalysts`) | same | 31 catalysts | 1 d | read. **Awake only when a PDUFA falls inside the horizon**; tonight none did |
| typed events | `optimus/typed_events/2026-09-27.jsonl` | 7,437 (none for 09-28: the local model is off) | 1 d | **NO path** to `u_plan`. Typed events feed thesis cards only |
| news corpus | `optimus/news_corpus/**` | 86,442 rows (798 new in 3 d, 29 sources) | < 1 d | **NO direct path**. Reaches a decision only through a card's text |
| social attention | `optimus/social/*` (YouTube; StockTwits via HTTP) | small | 1 d | **NO path** |
| Dow Jones / Barron's claims | `optimus/sources/claims.jsonl` + `source:*` forecast rows | 57 claims; 36 `source:` rows today | < 1 d | **NO path**. `expected_return` reads only arms beginning `investigator:` or `thesis_card:` (expected_return.py:74-75, 717-718) |
| decision contract | `optimus/decisions/2026-09-28.json` | `n_considered` = 2 on six straight days | 15 h | read, but only to REMOVE names (ALLE, SON). Health flags it STALE (static candidate input) |
| policy_state | `pc_book/policy_state.json` | 5 investigator arms carry weight | refreshed each cycle | read (`policy_state_used`), **changed nothing**: no shortlist name carries a contributing component |

## (b) Every weight on the path

FIXED = a constant set by hand. LEARNED = computed from graded outcomes. ASLEEP = defined but
multiplied by nothing tonight.

| weight | value | where | class |
|---|---|---|---|
| funnel stage 2 (low vol) | 0.6 x clip(2 - vol/median vol, 0, 1) | `opportunity_funnel.py:394-396`, registry weight `signal_registry.yaml:476` | FIXED |
| funnel stage 4 (profitability + stage 2) | 0.7 x percentile(gross profitability) + 0.5 x stage-2 score | `opportunity_funnel.py:667-669`, 0.7 at yaml:332 | FIXED |
| funnel insider score (0.5) | printed in `why`, never added | `opportunity_funnel.py:485-488` | ASLEEP (effectively 0) |
| funnel momentum_12_1 | 0: "CLOSED/REJECTED, shown for description" | registry | FIXED at zero |
| funnel stage sizes | 1500 / 250 / 40 / 25, 5 size bands | `opportunity_funnel.py:59-62, 88` | FIXED |
| ranker | LightGBM, 24 price features (lr 0.04, 350 trees) | `xs_ranker.py:146-169` | learned from past returns, not from the ledger; its output is refused (MEASURED_NEGATIVE) |
| `COMPOSITE_WEIGHTS` (arena) | momentum 1.0, multifactor 1.0, four 0.5s | `arena/discovery.py:371` | **not on this path** |
| E[r] component weights (6) | "equal" at every horizon; n_dates = 0 for all 6 components | `expected_return.py:257-287`, `refit_2026-09-28.json` | LEARNED, ASLEEP until `ER_MIN_GRADED` = 30 graded date blocks |
| E[r] prior share, k, floor | 0.5, 30, 0.0 | `config.py:1969-1975` | FIXED |
| regime scale | risk_on 1.0 / risk_off 0.5 (tonight risk_on, VIX 14.21) | `config.py:1992` | FIXED |
| reputation weights | investigator:D_all 0.4226, A_snapshot 0.2483, C_tools_only 0.2406, B_tools 0.0566, B_anon 0.0320; all 9 personas, `event_news`, `analyst_revisions`, `why_moved:*` 0.0 | `policy_state.json` | LEARNED (from the graded ledger; this is MAGNITUDE skill, per the 09-25 review). **`investigator:evidence_v3`, the arm written tonight, has no entry** |
| `investigator_mag` sizing | lambda 0.0055 (skill 0.026, 8 days) | `expected_return.py:847-866` | LEARNED, near zero, sizing only |
| PROBE weight / gross / names | 0.02 / 0.20 / 10 | `config.py:1898-1903` | FIXED |
| `probe_weighting` | "equal" | `policy_state.json` | LEARNED from three weighting-twin books, ASLEEP: "twins immature (0 sessions; each needs 21)" |
| PROBE grade gate | 21 scored days (0 so far) | `config.PROBE_GRADE_MIN_SESSIONS` | FIXED |
| EXPLOIT gate | top20_net_rel_21d > 0 (tonight -1.07%) and 21 scored blend days (0) | `sim_run.py:1125-1135`, `config.py:1983` | FIXED |
| `ER_EXPLOIT_MAX_WEIGHT` | 0.10 | `config.py:1986` | FIXED |
| `MAX_INVESTED_FRAC` / `MAX_NAME_FRAC` | 1.00 / 0.12 | `pc_broker.py:103-105` | FIXED |
| `MAX_ADV_PARTICIPATION` / `MIN_ORDER_USD` / drift band | 0.02 / $250 / 0.10 | `pc_broker.py:107-112` | FIXED |
| `policy_state` book_size 18, replan_drift 0.05, exploration_temperature 0.1, source_trust {} | as listed | `policy_state.json` | **read by nothing in `u_plan`** (it uses its own `BOOK_SIZE` and the broker's 0.10 drift) |

## (c) Tonight's plan, worked for three names

Cycle 1 plan, 13:47Z (21:47 HKT, the US session open at 13:30Z). Equity $997,913. EXPLOIT refused.
PROBE acting. `n_considered` 45, shortlist 22 after the share-class collapse and two contract
refusals. Every name got `er_reputation: null` at h5, so the order is the funnel's.

| | NVDA | TSM | GOOG |
|---|---|---|---|
| funnel inputs | $25.4bn median dollar volume; vol 38%/yr (universe median 44%); gross profitability pct 0.95; insider 0 | $4.76bn; vol 40%; profitability 0.35; insider 7.68 (not scored) | $5.83bn; vol 31%; profitability 0.39 |
| funnel score | 1.000 | 0.803 | 0.856 (same as GOOGL) |
| h5 E[r] (what orders PROBE) | none: all six components asleep; investigator p = 0.520 carried, not used | none; investigator p = 0.520 carried | n/a (dropped) |
| h21 E[r] (EXPLOIT, refused) | +0.047% = 0.5 x revision_flow 0.00094 (rule rank 34 of 1,681; 21 firms, net +16 raises) + 0.5 x source_reliability 0.0000044 | 0.0 (revision rule rank 376; 7 firms) | n/a |
| rank in PROBE order | 1 | 10 (entered because GOOG left) | removed: second line of Alphabet (CIK 1652044), GOOGL kept on dollar volume |
| target weight | 0.02 | 0.02 | 0 |
| order | none: drift $463 < band $1,996 (already held at target) | **BUY 44 sh, $19,664, submitted** | **SELL 58 sh, $19,681, submitted** (`POLICY CHANGE (share-class collapse) ... Not a change of view`) |

Also sent in cycle 1: **SELL 129 ALLE ($19,832, PROBE_EXIT, contract-refused as negative-EV)**.
Cycles 2 and 3 sent nothing (every drift under the band). Book after: 10 names x ~2%, cash 80.2%,
invested 19.8%. Worst case of the largest admissible PROBE book: 10 x 2% x 8.23% (3 sigma of
2.74%/day) = **-$16,417**; Σ|notional|/equity 0.20; no stop is declared, so the ceiling is
-$199,583.

## (d) What wakes each sleeping component, and when at the earliest

| component | what must become true | earliest date |
|---|---|---|
| `investigator_dir` at h5 (the first that can reorder PROBE) | its h5 rows graded to a calibration (first `resolves_after` 2026-10-05), then **30 graded date blocks** with held-out IC > 0; plus a `policy_state.reputation_weights` entry for `investigator:evidence_v3` | calibration from **2026-10-05**; weight > 0 no earlier than **2026-11-11** if rows are written every session from 09-28 (lane P §1) |
| `thesis_card` | 30 graded card rows (151 h20 rows, 0 graded) | first h20 grades ~2026-10-23; 30 date blocks late November at the earliest |
| `catalyst` | a dated PDUFA inside 5 sessions of a shortlist name | **any day**; no grading gate. Tonight there was none |
| `ranker` at h5 | calibration at h5 (it is calibrated at 21 only); EXPLOIT also needs top20_net_rel_21d > 0 | no date: needs a code change or a better ranker |
| `revision_flow`, `source_reliability` at h5 | a measured rule table at h5 | no date: needs a sweep at h5 |
| E[r] weights leaving "equal" | 30 graded DECIDED rows with an E[r] decomposition; the first h21 score is 2026-10-26 | **2026-12-07** at h21 |
| `probe_weighting` leaving "equal" | the three weighting twin books reach 21 sessions | ~2026-10-27 |
| EXPLOIT | the ranker's measured top-20 net > 0 and 21 scored blend days | no date |
| PROBE's own grade | 21 scored decision days at h5 | ~2026-10-26 |

## (e) How does news change a decision today?

**It does not, except through one narrow door that was shut tonight.** News is collected (798 new
rows in three days across 29 sources), typed into events when the local model runs, and read into
thesis cards, which are then written down as forecasts. None of that reaches an order, for three
reasons. First, a card's own probability (0.56-0.60 tonight) is multiplied by zero until 30 of its
rows are graded. Second, Dow Jones and Barron's claims and social attention have no code path at
all: `expected_return` accepts only arms that begin `investigator:` or `thesis_card:`
(expected_return.py:74-75, 717-718), and `policy_state` has no `source:` family. Third, the PROBE
order reads only the h5 E[r], and every h5 component is asleep. The one door is the `catalyst`
component: when a card or `pm_catalysts` dates a PDUFA within five sessions of a shortlist name, it
wakes with no grading gate and can re-sort which ten names are bought (never how much). Tonight no
such date existed. **The missing link is a graded weight for any text-derived component at h5 (the
horizon PROBE reads), plus an arm prefix that admits `source:` rows.**

## (f) The probabilistic rule the owner asked for

Murat is right that waiting for significance means never acting. The project already separates what
it may TEST in paper (no gate) from what it may CLAIM. The current plan's gates are claim-grade
gates applied to a paper book: a component with 29 graded dates contributes exactly as much as one
with none. The alternative below acts on the best estimate every day and lets the evidence set the
size.

### The rule (specified; implemented as a shadow in `scripts/shadow_bayes_rule.py`)

1. **Every signal j has a measured edge m_j with a standard error se_j**: the mean monthly return
   of its top-20 book over a matched twin (size x vol x momentum tercile), from
   `signal_structure/matched_twins_2026-09-27T082553Z.json`. Evidence from the window the library
   was chosen on (`dev`, pre-2024) has its SE doubled; the sealed 2024-26 window counts at face value.
   Windows are pooled by precision.
2. **Prior centred on zero edge**: true edge ~ N(0, tau^2), tau = 0.5%/month (the size of the largest
   published anomalies, long-short, before costs). Posterior mean = m x tau^2/(tau^2 + se^2). There
   is no pass/fail. A noisy positive gets a small positive weight, an unmeasured signal keeps its
   prior of 0 (by arithmetic, not by decree), a negative one gets a small negative weight.
3. **A name's expected 21-session excess over SPY**: alpha_i = sum_j post_mean_j x e_ij, with
   e_ij = clip((percentile_ij - 0.5)/0.5, -1, 1) over the whole eligible universe (2,702 names
   tonight). Unknown exposure means e = 0.
4. **Uncertainty and a stated probability**: s_i^2 = sigma_resid,i^2 + sum_j e_ij^2 post_sd_j^2, with
   sigma_resid the 63-session residual volatility against SPY, scaled to 21 sessions.
   P(name beats SPY over 21 sessions) = Phi(alpha_i / s_i). This probability is frozen on the book and
   graded for calibration.
5. **Size by fractional Kelly**: w_i = 0.25 x alpha_i / s_i^2 for alpha_i > 0 (long only), each
   w_i <= 0.10 (the existing `ER_EXPLOIT_MAX_WEIGHT`). The **sleeve** total is capped at
   0.25 x alpha_sleeve / TE^2, where TE is the measured monthly tracking error of the momentum top-20
   book against its twin (7.6%). The names in one factor sleeve are one correlated bet, not ten. The
   rest of the capital is SPY. The sleeve cap scales every name by the same factor (0.144 tonight); names that end under 0.5% are dropped.
6. **Priors from tonight's experiments**: Kronos (worse than trailing volatility on 26 of 26 dates)
   and our own DeepSeek (48-49% direction hit after its cutoff, confidence uninformative) enter with no
   measured edge, so their posterior is 0 and their sd is the prior's. The investigator's measured skill
   is on MAGNITUDE, and the rule uses the trailing-volatility formula that beat it for magnitude.

### What the evidence on disk says, component by component

| component | measured (monthly, vs twin) | shrink | posterior | source |
|---|---|---|---|---|
| 12-1 momentum | +1.50% pooled (dev +2.17% t 2.59, SE doubled; sealed +0.79% t 0.46) | 0.15 | **+0.222%/mo** | `mom_12_1@k20` |
| gross profitability | -0.15% pooled (dev +0.42% t 0.85; sealed -0.62% t -0.69) | 0.36 | **-0.052%/mo** | `gp_at@k20`; agrees in sign with the bake-off's -1.34%/21 sessions (t -2.55) |
| LightGBM ranker | -0.07% (§59: gross +0.28% vs a 35 bps toll; t taken as -0.7, declared) | 0.96 | **-0.067%/mo** | xs_ranker bake-off |
| investigator direction, analyst revisions, thesis cards, catalyst, Kronos | none usable | 0 | **0** | lane X, S57b, refit |

Two things follow, and neither is a lecture about certainty. **First, the funnel sorts the PROBE book
on the one signal whose posterior is slightly negative** (profitability), and ignores the one whose
posterior is positive (momentum, which the registry marks CLOSED on large/mid costs from August).
**Second, the best call on the evidence is close to the index**: the largest posterior edge is
+0.22%/month against a 7.6%/month tracking error, so quarter-Kelly puts about 4% of capital in the
tilt. The current plan's largest single bet is not a stock. It is the **80% cash**, a beta of ~0.2
against SPY, which no signal on disk recommends.

### Tonight, the same 45 candidates under each rule

| rank | current plan (PROBE) | weight | probabilistic rule | alpha_21 | P(beat SPY, 21s) | weight in the live-size book |
|---|---|---|---|---|---|---|
| 1 | NVDA | 2% | JAZZ | +0.196% | 0.510 | 1.20% |
| 2 | INCY | 2% | TS | +0.176% | 0.509 | 1.14% |
| 3 | AAPL | 2% | LITE | +0.152% | 0.502 | <0.5% after the sleeve cap, dropped (s 26%) |
| 4 | SNDR | 2% | SNDR | +0.149% | 0.507 | 0.71% |
| 5 | META | 2% | PDS | +0.149% | 0.505 | <0.5% after the sleeve cap, dropped |
| 6 | AVPT | 2% | STX | +0.149% | 0.503 | <0.5% after the sleeve cap, dropped |
| 7 | AMZN | 2% | TSM | +0.138% | 0.506 | 0.62% |
| 8 | GOOGL | 2% | BW | +0.134% | 0.502 | <0.5% after the sleeve cap, dropped |
| 9 | JAZZ | 2% | TE | +0.121% | 0.502 | <0.5% after the sleeve cap, dropped |
| 10 | TSM | 2% | LAR | +0.116% | 0.503 | <0.5% after the sleeve cap, dropped |
| rest | cash 80% | | SPY | | | **96.3%** |

The rule's bottom of the list is DUOL (-0.28%), ACVA, XRX, META (-0.16%) and PLTR: META is a current
PROBE holding the rule would not hold. Receipt:
`backend/data/optimus/shadow_bayes/rule_2026-09-28_20260928T140452Z.json` (hash `4ec3bc19f0166ab7`).
The stated probabilities sit between 0.494 and 0.510. That is the honest width of our knowledge
tonight, and it says the calibration grade will have little resolution until a component earns a
larger posterior.

### The shadow book (frozen tonight; no broker orders)

- **Book `439fd84f869744e0`** "SHADOW_BAYES_v0 sleeve 2026-09-28", asof 2026-09-28, **enters at the
  2026-09-29 open**, graded daily by the existing `llm_portfolio grade`. Holdings: the sleeve,
  normalised (JAZZ 32.8%, TS 31.1%, SNDR 19.3%, TSM 16.8%). The live-size book is
  0.037 x sleeve + 0.963 x SPY.
- **Matched control, frozen with it**: `random_same_band` `ec29c635db8ac686`, plus `spy`
  `d00f3ab5451adc9e` and `ew` `3e0a91bed8759db0`.
- **Primary read**: sleeve minus its random twin at 21 sessions (2026-10-27) and 63 sessions
  (2026-12-24). Secondary: live-size book vs PC-PAPER's NAV over the same window, and the Brier
  score of the stated probabilities.
- **Kill rule**: at 63 sessions, a sleeve behind its random twin makes v0's priors FAILED_VARIANT.
  No v0 parameter changes before then.
- Registration: `backend/data/optimus/shadow_bayes/REGISTRATION_SHADOW_BAYES_v0_2026-09-28.json`.
- **Conflict, stated**: the TIER 1 roadmap says no new book until 2026-10-26. This book was frozen on
  the orchestrator's explicit instruction. It can be voided before entry
  (`llm_portfolio.void(book_id, reason, who=...)`) and will then never grade.
- **Known weakness**: 4 names and one random draw. A null will read CANNOT_DISTINGUISH. The book's
  real job is to start a calibration record for a rule that acts without a gate.

### For a builder (not wired tonight)

Wire it as a third state beside PROBE and EXPLOIT, not as a weight inside either: (1) read the
posteriors from a receipt refreshed nightly from the matched-twin and forecast-ledger grades, so a
component wakes by degree as its SE falls instead of at 30 dates; (2) apply `plan_orders` and every
existing cap unchanged; (3) write one forecast row per name, `shadow_bayes:v0 / beats_benchmark /
h21` with the stated p, so reputation can grade it like any arm; (4) print the worst case in dollars
before the first order. The only new decision it needs from the owner is whether the non-tilt
capital sits in SPY or in cash, because that choice is a larger bet than any signal here.

---

## 2026-09-29 (overnight, written ~02:30 HKT by the continuing night operator): what changed since 22:10

Nothing above is edited. Three things changed around the decision path overnight. **None of them
changed an order tonight**, and the one-line answer at the top still holds: the paper orders are the
funnel's score order and hand-set caps.

### 1. Stitched tickers are now cut before the ranker reads prices

A price-history defect was found: for **62 tickers** the survivorship-free bar panel joins two
different companies under one reused symbol (JAN was a $2.21 stock until 2024 and a $23.34 IPO in
2026; MLPI a dead 2020 fund and a 2025 listing). Any trailing feature that reached across the gap
compared a new company with a dead one, so 12-1 momentum read them as huge winners, and the
2026-09-28 live ranking (`pc_book/2026-09-28/ranking.json`, built 21:28 HKT) put **JAN #2 and
MLPI #4**. `backend/services/stitched_tickers.py` detects the joins from the data (gap + SEC
registrant + price jump) and `xs_ranker.load_bars` now splits them by default (working tree,
uncommitted). Receipt: `backend/data/optimus/stitched_tickers/stitched_20260928T153245Z.json`.

What it touched: **no paper order**. The ranker's EXPLOIT book was refused (MEASURED_NEGATIVE), and
the PROBE book is the funnel's 25 names, none stitched. The sim's only orders tonight (SELL ALLE,
SELL GOOG, BUY TSM at 13:47Z) are not stitched names; the shadow book (JAZZ, TS, SNDR, TSM) and its
random twin (CM, LMAT, VNT, ALAB) hold none. What it did touch: **45 of 312 frozen books**, including
**20 of the 30 pairs of TRIAL-LIB-FWD-TWIN-1**, mostly the momentum books that bought JAN, LIFE and
AKTS because of the splice. The grader still marks those names from their own bars, so the forward
measurement is real; what is contaminated is the reason they were bought (dated note in the trial
file). The first ranking built with the cut will be the one after the 06:30 HKT bar refresh.

### 2. The network lab now publishes a trust-weighted ensemble and a size-of-move forecast

`nn_lab` froze, for decision date 2026-09-25 (entry at the 2026-09-29 open), predictions from its
models for 2,964 names (`backend/data/optimus/nn_lab/frozen/2026-09-25/`), a trust score per model
and horizon (`nn_lab/trust.jsonl`) and a size forecast (`nn_lab/size_forecast/size_2026-09-25.*`).

- **Trust is a shrunk estimate of each model's rank IC**, from walk-forward history only (0 forward
  grades yet). At 21 sessions: LightGBM 0.0075, ridge 0.0060, 12-1 momentum 0.0053, the neural net
  0.0004, the "zero" model 0. **In charge: LightGBM.** The ensemble weights at h21 are LightGBM 0.39,
  ridge 0.31, momentum 0.28, NN 0.02. All of these are tiny: an IC of 0.0075 means the ranking
  explains well under 1% of the spread between stocks.
- **The size forecast is the one component with demonstrated skill**: the network's interval width
  ranks next month's absolute move at IC 0.357 against trailing volatility's 0.336. The published
  size model is the simplest one that captures that gain (`ridge_abs`, h5 and h21). It says how
  BIG a move is likely to be, never which way.
- **None of it reaches an order.** No file under `nn_lab/` is read by `sim_run.u_plan`,
  `expected_return`, `policy_state` or `investment_committee`. First forward grades of the h5
  predictions arrive about 2026-10-06; the scheduled nightly run starts 08:30 HKT today.

### 3. Tonight's fiction backtest says LLM direction calls deserve a weight near zero

`docs/research_notes/2026-09-28/fiction_backtest_2026-09-28.md`: on 569 real earnings events dated
after DeepSeek's cutoff, DeepSeek called the 5-day direction right **44.6%** of the time named,
**43.1%** masked and **43.9%** as fiction; Claude Opus answered the fiction version of 120 cases at
**44.6%**. A coin is 50% and plain 12-1 momentum on the same rows was 46.7%. So an LLM's up/down call
enters any probabilistic rule with a posterior weight of about zero (the rule's prior of 0 stands),
while the size-of-move forecast is the input that earns a role, and that role is SIZING (how much),
not direction (which way).

### How does news change a decision today? (restated for 2026-09-29, plain words)

It still does not. News is collected (the browser reader loaded 953 pages, 858 of them readable, and stored 379 articles on
2026-09-28 before it stalled: last readable page 00:58 HKT; 279 `source:` claim rows and 28 thesis-card rows
were written as forecasts), but a forecast only moves money after it has been graded, and none of
these has been graded yet. Thesis cards get weight zero until 30 of their rows are scored; claims
read from Dow Jones, Barron's and MarketWatch (`source:` rows) have no code path into the plan at all,
because the expected-return layer accepts only `investigator:` and `thesis_card:` rows
(`backend/services/expected_return.py:74-75`); and the PROBE book reads only the 5-session estimate,
where every component is asleep. The one exception is a dated drug-approval (PDUFA) catalyst inside
five sessions of a shortlisted name, which can change which names are bought but not how much; there
was none tonight. The earliest date a news-derived forecast can change an order is 2026-11-11, and
only if its graded record is positive.
