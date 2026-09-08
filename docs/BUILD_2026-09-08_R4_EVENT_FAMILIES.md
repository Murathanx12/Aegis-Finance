# BUILD 2026-09-08 — R4: the event families, and an honest coverage story

**Lane:** `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 block **E**, item **E3**.
**Repo:** `aegis-finance`. **Licence:** `PRODUCT_EXPERIMENT` — a screen. It
licenses *building* a book; nothing here is a `RESEARCH_CLAIM`.
**LLM spend: $0.00, 0 calls.** No order, no deploy, no seal, no push, no commit.
Two news pullers (PIDs 50240, 139180) were left alone throughout; one of them
finished on its own and its clean-exit evidence is in §1.5.

Code: `scripts/r4_event_families.py`.
Receipts: `backend/data/optimus/r4_event_families/R4_event_families.json`,
`R4_earnings_events.parquet` (the event tape, 339,858 rows),
`R4_tape_build.json`.

---

## 0. RESULT, first paragraph

**RESULT IMPROVEMENT: NONE.** No strategy moved, no book changed, no lane was
seeded. What moved is what is *known*:

1. **The E3 gate was never one gate.** It is four different coverage readings
   that differ by two orders of magnitude, and the roadmap does not say which
   one it means. §1 names all four and conditions every number below on one.
2. **The news leg is REFUSED, not null.** 2015-2024 has a price panel and ~1%
   news coverage; 2025-2026 has 43.7%/46.1% news coverage and **no price
   panel** — CRSP daily on disk ends 2024-12-31 and the graded monthly panel
   ends 2024-12. There is no year in which a news-conditioned event book can be
   both built *and* graded. That is a property of the tape.
3. **The earnings leg was never gated on the news pull and clears 90% easily.**
   IBES quarterly EPS announcements cover **95.1%–98.2% of the graded panel in
   every year 1999-2024**. Nobody had measured this; E3 has been reported as
   blocked on a number that does not bind the family that matters most.
4. **PEAD's headline number is an entry convention.** Entering at the
   announcement session's close (`event_response_v1`'s convention) prints a
   **+5.54% one-session** top-minus-bottom SUE-decile spread (market-excess
   basis). Moving the entry one session later — which is what PIT safety
   requires, because IBES carries no time of day and a large minority of firms
   report after the bell — leaves **+0.41%**. **92.5% of "one-day PEAD" here is
   the announcement reaction, bought at a close that precedes it.**
5. **The 8-K corpus is survivorship-conditioned by construction and its own
   manifest says so.** 1,061 of the 1,062 CIKs filing in 2015 also file in 2024;
   the CIK list is SEC `company_tickers.json` — *current* registrants — replayed
   backwards. It is graded here as a within-sample contrast and labelled SLICE.
6. **PEAD DECAYED, and one thing in its place did not.** Across three eras the
   surprise-decile spread runs t 8.40 / 4.99 / **0.21** at five sessions. But
   ranking on the **announcement REACTION** instead of the surprise gives
   t 6.13 / 2.97 / **3.67** at twenty-one sessions, carries almost no pre-event
   drift, breaks even at 39–45 bps a side, and **reverses sign on a placebo
   date 40 sessions later** (t −6.47) — so it is the *event*, not two-session
   momentum. That inverts the hypothesis this lane was sent to test: the
   mandate's cell was *large surprise, small reaction*; the tape says the
   reaction is the information and the surprise is the part that died. §9.
7. **And it dies in CONSTRUCTION.** Put through the same three constructions on
   the floored panel, the reaction signal gives **+2.98 %/yr at t 0.77** at
   `k=50|vw` and is **negative** at both broad constructions. Not a promotion:
   180 cells looked at, **zero** positive-t Holm survivors among all 78 book
   cells, DSR 0.209 against a 0.95 bar with the null's expected max Sharpe
   (0.584) *above* the observed best (0.4245). No book was armed, nothing was
   folded into `arena_composite`. §7.2 says which of the three reasons is the
   market's and which is mine.

---

## 1. THE COVERAGE STATEMENT — which reading, which years, which months excluded

### 1.1 Four readings, and they are not interchangeable

| | reading | what it counts | range |
|---|---|---|---|
| **A** | `month_fraction` | months of the year with any NEWS row | 66.7%–100% (75% in 2015, 100% 2016-24, 83.3% 2025, 66.7% 2026) |
| **B** | `universe_fraction` | distinct NEWS symbols / the 12,198-name tradable universe | **0.77%–1.22%** (2015-24), **43.70% / 46.05%** (2025 / 2026) |
| **C** | N4 event-table share | linked permnos in `event_table_v1` / CRSP common stock active that year, **all sources pooled** | 80.8%–86.3% (2015-24) |
| **D** | **panel share, THIS JOB** | names in the **graded monthly panel** with ≥1 event *of this family* that year / all panel names that year | see 1.2 |

A and B are read from the terminal repo's own receipt
(`state/corpus/corpus_coverage_by_year_2026-09-08.json`, stamped 04:54 UTC) and
are **not** re-derived here. Both are a **floor for 2025-2026**: the two pullers
were running when that snapshot was taken and both have written rows since — see
§1.5 for where each stands now. Neither was signalled.

A is pipeline health. B is the news data number. **C is not a news number** —
it is dominated by IBES and 8-K, and reading it as evidence about the news pull
is the error the table exists to stop. **D is the only reading that bounds what
a book can express**, because `learner.evaluate.book` selects from the panel.

*Every family number in this document is conditioned on reading D.*

### 1.2 Reading D, measured (`R4_event_families.json::STAGE_1_COVERAGE`)

| year | panel names | IBES qtrly EPS | 8-K items | year | panel names | IBES | 8-K |
|---|---|---|---|---|---|---|---|
| 1999 | 2,895 | **97.1%** | — | 2012 | 3,108 | 97.0% | — |
| 2000 | 3,461 | 96.4% | — | 2013 | 3,101 | 96.7% | 13.0% |
| 2001 | 3,299 | **95.1%** | — | 2014 | 3,278 | 96.3% | 17.3% |
| 2002 | 3,131 | 96.0% | — | 2015 | 3,335 | 96.6% | 21.8% |
| 2003 | 3,113 | 95.7% | — | 2016 | 3,259 | 97.0% | 27.1% |
| 2004 | 3,316 | 96.7% | — | 2017 | 3,163 | 96.9% | 32.7% |
| 2005 | 3,519 | 96.3% | — | 2018 | 3,190 | 97.3% | 37.9% |
| 2006 | 3,648 | 96.1% | — | 2019 | 3,192 | 97.5% | 42.4% |
| 2007 | 3,746 | 96.0% | — | 2020 | 3,212 | 97.0% | 47.4% |
| 2008 | 3,537 | 97.0% | — | 2021 | 3,624 | 96.0% | 48.0% |
| 2009 | 3,256 | 96.5% | — | 2022 | 3,690 | **98.2%** | 49.8% |
| 2010 | 3,210 | 97.6% | — | 2023 | 3,595 | 97.2% | 52.9% |
| 2011 | 3,195 | 96.5% | — | 2024 | 3,420 | 96.5% | 58.3% |

* **IBES earnings: the ≥ 90% gate is MET in every one of the 26 years.**
* **8-K: NOT MET in any year**, and the growth 13% → 58% is not a market
  changing shape; it is the collector's own CIK list filling in (§1.4).
* News: not in this table at all — see §1.3, it is refused.

### 1.3 The news leg — REFUSED, with a reason, not a null

| | 2015-2024 | 2025-2026 |
|---|---|---|
| CRSP daily price file on disk | **yes** (1990…2024) | **no** |
| graded monthly panel | **yes** (1999-03…2024-12) | **no** |
| news coverage, reading B | **0.8%–1.2%** | 43.7% / 46.1% |

A book needs both columns to be "yes". Neither year block supplies both. This
is not "the signal did not work" — it is *no experiment was possible*, which is
the difference between a refusal and a finding, and reporting the second when
you have the first is the failure mode this programme keeps paying for.

**What would lift the refusal:** the 2015-2024 whole-market Alpaca pull (~50 h,
resumable, command in `BUILD_2026-09-07b_E1_NEWS_PULLER.md` §8), **or** a
2025-2026 daily price file. The pull is much the cheaper of the two and is the
only one of the two this project can do by itself.

### 1.4 Months and years excluded, and why

* **Four news months are DONE but NOT FULL** — `alpaca 2025-01`, `alpaca
  2025-03`, `finnhub 2025-02`, `finnhub 2026-01` — from the 17-hour DNS outage
  on 2026-09-07/08 (`--list-degraded` in the terminal repo names them). They are
  **not averaged over here**: the news leg is refused outright, so no number in
  this document depends on any of them. Whoever finishes E2 must run
  `--redo-degraded` before quoting a coverage number.
* **Finnhub free history stops at 2025-09** — measured, not assumed
  (`BUILD_2026-09-07b_E1_NEWS_PULLER.md` §8). It is irrelevant to every result
  here for the same reason.
* **8-K years 2013-2016 are reported but never traded.** The collector's
  manifest gives `coverage_start_median: 2016-02-09`, and only
  `filings.recent` (~1,000 filings/CIK) was read — so an absent filing before
  that date is *truncation*, not a company that filed nothing. The 8-K family
  is graded from **2017** onward.
* **Two declared 8-K biases**, both from the corpus's own manifest and both
  confirmed by measurement here:
  * `survivor_caveat` — the universe is `company_tickers.json`, i.e. **current**
    registrants. Measured: **1,061 of 1,062** CIKs filing in 2015 also file in
    2024. A name delisted before the collector ran is absent from every earlier
    year, and the bias runs **upward** on any return computed from it.
  * `coverage_truncation_caveat` — as above.
  Consequence: the 8-K family is graded **against the other 8-K filings in the
  same event month**, never against the market. Only a within-sample contrast
  differences the survivorship out, and the question it can honestly answer is
  narrowed to *does THIS item behave differently from an average 8-K?*

### 1.5 State of the two pullers at hand-off (read-only check, no process signalled)

Read straight out of `aegis-alpha-terminal/state/pulls/*/cursor.json` — nothing
in that repo was written and no process was signalled:

| run | leg | status | evidence |
|---|---|---|---|
| `news_2025-01-01_2026-09-08_fleet` | finnhub | **complete, 21 / 21 months**, 102,002 items, **86,810 new rows** | `status: complete` **and the pid file is gone**, which is the clean-exit signal `pull_journal` was built to give. PID 139180 finished on its own during this session |
| `news_2025-01-01_2026-07-01_tradable` | alpaca | **RUNNING, 6 of 18 months done**, partial at 2025-07 batch 234, 149,500 new rows so far | pid file present, PID **50240 alive**, cursor updated 06:05 UTC |

Two consequences for whoever picks E2 up:

* **Reading B above is already stale upward** — it is the 04:54 snapshot and
  both legs have written rows since. Re-run `--corpus-coverage` before quoting
  it, and quote *which fraction*.
* **Re-run `--list-degraded`.** The finished Finnhub leg logged 44 × HTTP 429
  and 125 `other` across its 21 months, so the four degraded months named in
  §1.4 are a lower bound on what `--redo-degraded` now has to redo.

### 1.6 What this slice can and cannot answer

**Can:** whether earnings-event families (surprise, its history, the
surprise-vs-reaction gap, revision-on-event) carry information on a 26-year,
~96%-covered panel, after beta, costs, expected return, and family correction.

**Cannot:** anything conditioned on news text, sentiment, coverage
normalisation, or headline novelty. Cannot say anything about 2025 or 2026 at
all. Cannot make a universe-level claim from 8-K items.

---

## 2. WHAT WAS BUILT, AND THE TWO CONVENTIONS THAT DECIDE EVERYTHING

`scripts/r4_event_families.py`, 1,749 lines, offline, `$0`.

**The event tape** (`R4_earnings_events.parquet`): **339,858** announcements,
1999-01 → 2024-12, **312 event months** (the date blocks every t below is taken
on), 8,900+ permnos. IBES `surpsumu` (unadjusted quarterly US EPS) linked to
CRSP by WRDS's own `ibcrsphist` on an **interval** join (`score ≤ 2`), so a
recycled IBES ticker cannot pick up the wrong company: 445,470 of 552,096 US
quarterly EPS rows link (80.9%). Market model fitted on 93%+ of events over
sessions −260…−21 (min 100 sessions). Built in five-year cohorts (~350 MB
resident) because the full 1997-2024 CRSP daily file is 33.6 M rows.

**Convention 1 — the entry.** IBES carries **no announcement time of day**, and
a large minority of US firms report after the bell. Two entries are therefore
carried and both are reported:

* **`e2`, the PRIMARY** — enter at the close of session **+1**. PIT-safe under
  either announcement timing.
* **`e1`, the SECONDARY** — enter at the close of session 0
  (`event_response_v1`'s convention). Right for an intraday reporter, a
  **lookahead** for an after-close one.

**Convention 2 — the return basis.** Four, and they are not interchangeable:
`raw`; `mkt` (minus the EW market); **`bo`** (minus *β × market*, β from the
name's own pre-event window — the clean expected-return decomposition); **`ab`**
(minus *α + β × market* — the *full* fitted pre-event expectation).

`ab` is deliberately an **over-correction** and is labelled as one: a high-SUE
name's fitted α contains its own pre-announcement run-up, so `ab` charges the
drift for momentum the announcement did not cause. It is the upper bound of the
correction; `bo` is the correction. **Read them together or neither.**

**`n_effective` is 312 event months, not 339,858 events** (CANON §58). Earnings
cluster into four seasons; the spread is formed *inside* each month so the
month's own market move cancels before the t is taken.

---

## 3. F1 — PEAD ON FIVE CLOCKS. Three separate things kill it.

Top-minus-bottom SUE-decile spread, per event, one number per event month.
**Differential pre-event β of the two extreme deciles: −0.0154** — the long-short
is already ~β-neutral, which is why `raw`, `mkt` and `bo` barely differ.
**Differential pre-event daily α, compounded over 60 sessions: +4.44%.**

| clock | `mkt` e1 (lookahead) | **`mkt` e2 (PIT)** | **`bo` e2** | `ab` e2 (over-corrected) |
|---|---|---|---|---|
| 1 session | +5.542 % (t 41.8) | **+0.414 % (t 6.65)** | **+0.437 % (t 7.07)** | +0.363 % (t 5.86) |
| 5 sessions | +6.327 % (t 36.3) | **+0.790 % (t 6.56)** | **+0.876 % (t 7.09)** | +0.504 % (t 4.02) |
| 21 sessions | +7.026 % (t 24.3) | **+1.388 % (t 5.26)** | **+1.536 % (t 5.77)** | −0.015 % (t −0.05) |
| 60 sessions | +7.904 % (t 17.4) | **+2.149 % (t 4.57)** | **+2.155 % (t 4.93)** | −2.124 % (t −4.01) |
| to next announcement | +8.328 % (t 16.5) | **+2.538 % (t 4.96)** | **+2.488 % (t 5.50)** | −2.000 % (t −3.76) |

*n = 309–312 event months. Two-sided p. The full grid (4 bases × 5 clocks × 2
entries = 40 cells) is in `R4_event_families.json::STAGE_3_PEAD_MULTICLOCK`.*

### 3.1 The entry convention is most of the headline

At one session, `e1` prints **+5.54%** and `e2` prints **+0.41%**: **92.5% of
"one-day PEAD" here is the announcement reaction, bought at a close that
precedes it.** The `e1` column is not a result; it is the size of the lookahead,
printed so nobody re-derives it.

### 3.2 The 21–60 session drift is smaller than the names' own prior drift

The differential pre-event α of the two extreme deciles compounds to **+4.44%
over 60 sessions**. The entire 60-session PEAD spread is **+2.15%**. So the
high-SUE decile was *already* out-drifting the low-SUE decile, before the
announcement, at more than the rate the post-announcement window delivers.
Subtracting that prior drift (the `ab` column) turns 21-day PEAD to zero and
60-day PEAD **negative (t −4.01)**.

`ab` over-corrects, so the defensible statement is the weaker one, and it is
still decisive: **on the 21+ session clocks, PEAD is not separable from the
pre-existing expected-return differential between the deciles.** On the 1–5
session clocks it *is* — those survive even the over-correction (t 5.86, 4.02).
**PEAD on this tape is a one-week phenomenon wearing a three-month name.**

### 3.3 It decayed, and the era it died in is the one we would trade

`bo`, `e2`, by era (`learner.long_panel.ERAS`, never pooled):

| clock | 1999-2007 | 2008-2015 | **2016-2024** |
|---|---|---|---|
| 1 session | +0.734 % (t 6.85) | +0.445 % (t 4.66) | **+0.133 % (t 1.23)** |
| 5 sessions | +1.561 % (t 8.40) | +1.037 % (t 4.99) | **+0.047 % (t 0.21)** |
| 21 sessions | +2.180 % (t 4.01) | +1.871 % (t 4.65) | **+0.585 % (t 1.47)** |
| 60 sessions | +3.153 % (t 3.93) | +2.158 % (t 3.14) | **+1.126 % (t 1.50)** |

*108 / 96 / 105-108 date blocks. Same sign in 3 of 3 eras — and **not
distinguishable from zero on any clock in the newest era.***

### 3.4 The execution floor, applied before believing it

A decile long-short pays four sides. Breakeven cost per side = spread / 4:

| clock | full sample (`bo` e2) | **2016-2024 only** |
|---|---|---|
| 1 session | 10.9 bps | **3.3 bps** |
| 5 sessions | 21.9 bps | **1.2 bps** |
| 21 sessions | 38.4 bps | **14.6 bps** |
| 60 sessions | 53.9 bps | **28.1 bps** |

This repo's cost grid is 10 and 25 bps a side. In the newest era **every clock
is under 10 bps of breakeven except the 60-session one — which is the clock §3.2
just showed is not separable from prior drift.** There is no cell that is both
alive in the recent era and clear of the cost floor.

**And the event study is UNFLOORED.** It runs over every IBES-linked CRSP name
with no dollar-volume gate, which is the direction that flatters PEAD hardest
(published PEAD lives in small, illiquid names). The floored version is §7.

### 3.5 MDE and power, before the confirmation (CANON §64)

`bo|5|e2`: 312 blocks, sd 2.183 %/block, **MDE 0.346 %**, observed 0.876 % ⇒
**powered**; 49 blocks would have sufficed. So the newest era's +0.047 % is not
"we could not see it": with 108 blocks the era-3 MDE is ~0.59 %, and the point
estimate is an order of magnitude below it. The tape **resolved** this family.
`ab|21|e2` is the one cell in the grid flagged **not powered** (observed
−0.015 % is under its own MDE) — reported, not hidden.

---

## 4. F3 — SURPRISE × REACTION: the gap is nothing, and there is a reason

The mandate's interesting cell — **large fundamental surprise, small price
response** — measured two ways.

**(a) The gap as a ranked signal** (`sue_pct − reac_pct`, decile spread):

| clock | `mkt` e2 | `bo` e2 |
|---|---|---|
| 5 sessions | −0.159 % (t −1.20) | −0.022 % (t −0.17) |
| 21 sessions | −0.368 % (t −1.56) | −0.221 % (t −0.85) |
| 60 sessions | −0.010 % (t −0.02) | −0.218 % (t −0.49) |
| to next announcement | +0.214 % (t 0.53) | +0.084 % (t 0.21) |

**(b) The named cell** — |SUE| in its month's top quintile **and** |reaction| in
its bottom quintile (2.66 % of events), traded in the surprise's direction,
against the same signed trade on every other event that month:

| clock | `mkt` e2 | `bo` e2 |
|---|---|---|
| 5 sessions | +0.140 % (t 1.22) | +0.196 % (t 1.86) |
| 21 sessions | +0.128 % (t 0.59) | +0.247 % (t 1.04) |
| 60 sessions | −0.042 % (t −0.11) | −0.237 % (t −0.64) |

**Nothing reaches t = 2 anywhere**, before any family correction. In the newest
era the named cell is +0.028 % (t 0.16) at 5 sessions.

**Why the gap is null when the surprise is not.** The gap *subtracts* the
reaction rank from the surprise rank, and the reaction is itself a continuation
signal of about the same size — so the subtraction cancels the only term that
still works. **§9 measures that directly** (ρ = 0.32 between the two ranks;
reaction alone at t 6.20/7.37) rather than leaving it as a story. The
"expectation-reaction gap" as a rank difference is not "finding the diffusion
cell" — it is netting a live signal against a correlated dead one.
Status: `FAILED_VARIANT`, and §12 names the version that was not tried.

---

## 5. F5 — EARNINGS-SURPRISE HISTORY (twelve quarters, seven features)

All on `sue_pct` (the within-month rank), because a raw SUE with a near-zero
`surpstdev` produces values like −3,476 out of a penny. Family = **28 cells**.

| feature | clock | `bo` e2 | 1999-2007 | 2008-2015 | **2016-2024** | powered |
|---|---|---|---|---|---|---|
| **acceleration** (SUE*t* − SUE*t−1*) | 21 | **+1.256 % (t 5.90)** | t 5.99 | t 4.02 | **t 0.56** | yes |
| acceleration | next ann. | +1.372 % (t 3.85) | t 3.94 | t 1.06 | t 1.47 | yes |
| **trailing 8q mean** | next ann. | **+1.542 % (t 3.00)** | t −0.66 | t 2.72 | **t 3.86** | yes |
| persistence (signed run length) | next ann. | +1.113 % (t 2.56) | t −1.01 | t 2.81 | t 3.52 | no |
| few reversals | 21 | +0.351 % (t 1.72) | t 0.66 | t 2.61 | t −0.15 | no |
| low dispersion | next ann. | −0.495 % (t −1.42) | t 0.07 | t −1.22 | t −1.47 | no |
| magnitude (mean \|SUE\|) | next ann. | −0.329 % (t −0.88) | t −0.55 | t −2.60 | t 1.23 | no |
| trend (OLS slope, 8q) | next ann. | +0.297 % (t 0.74) | t 0.70 | t −0.07 | t 0.57 | no |

Two things worth saying plainly:

* **Acceleration is the strongest cell in the family and it is PEAD wearing a
  hat.** SUE*t* − SUE*t−1* contains SUE*t*; its era profile (5.99 / 4.02 /
  **0.56**) is PEAD's era profile. It adds nothing after 2016.
* **The trailing-8-quarter mean is the only cell in this whole document that is
  STRONGEST in the newest era** (t 3.86 in 2016-2024 vs t −0.66 in 1999-2007).
  It fails the export bar — raw p 0.0027, **Holm p 0.0647** over its 28-cell
  family — and it changes sign across eras, so "holds in 2 of 3" fails too. It
  is nonetheless the second-most interesting thing in this document after §9,
  and §12 says what to do with it.

---

## 6. F4 — 8-K ITEM FAMILIES: a slice, contrasted within itself, and empty

155,821 filings with a computable CAR, **96 date blocks** (2017-01 → 2024-12),
ten item codes with ≥ 2,000 filings. Each item's CAR is measured **against every
other 8-K filing in the same event month** — never against the market, because
the sample is survivor-conditioned (§1.4) and only a within-sample contrast
differences that out. Entry is the `e2` convention after EDGAR acceptance.
Family = **20 cells**.

| item | what it is | window | mean vs other 8-Ks | t | raw p |
|---|---|---|---|---|---|
| **5.02** | departure/election of directors or officers | 5 d | **−0.153 %** | **−2.62** | 0.0089 |
| 5.03 | amendments to articles / fiscal year change | 5 d | +0.292 % | 1.75 | 0.080 |
| 5.07 | submission of matters to a security-holder vote | 5 d | −0.198 % | −1.67 | 0.094 |
| 1.01 | entry into a material agreement | 21 d | +0.241 % | 1.13 | 0.259 |
| 2.02 | results of operations | 21 d | −0.184 % | −1.10 | 0.271 |
| *(the other 15 cells: \|t\| ≤ 1.07)* | | | | | |

**Nothing survives.** Holm over 20 cells puts the best at 20 × 0.0089 = **0.178**.
And 15 bp of within-8-K contrast is below the cost floor before any correction.
Item 2.02 (the earnings 8-K, the item that *should* carry PEAD if anything does)
reads **−0.006 % at 5 days, t −0.08** — which is the expected answer, since the
contrast is against other 8-K filings by the same survivor set rather than
against the market, and it is a useful internal consistency check.

---

## 7. F2 + the books — every family through N1's constructions, β first

Panel: the `$3m/day`-floored universe, **530,447 rows, 310 months, median 1,794
names/month**. PIT attach: `merge_asof` backward on `entry_date − 2 days`
(two days, not zero, for the same reason `e2` exists), by permno — **91.5% of
floored panel rows carry an announcement within 90 days**, median 48 days since.
Constructions: `k=50|vw|hold=none` (the incumbent control), `k=100|ew|hold=200`,
`k=300|ew|hold=600`; costs 10 and 25 bps a side. **13 selectors × 3 × 2 = 78
cells** — 72 as planned, plus six for `reaction`, added *after* §9 and charged
to the family here rather than reported as if it had always been planned
(EXPLORE DIRTY permits the post-hoc selector; invariant 16 charges it).
`gap_cell` was **SKIPPED** — only 14,104 non-null rows after the floor, below
the 20,000 threshold, and reported rather than quietly run.

Every row: **β first**, then the beta-matched excess (PRIMARY), then IC /
effective breadth / transfer coefficient / turnover / typed exits.

| cell (10 bps unless noted) | **β** | bm %/yr | t | IC | BR | **TC** | turn | hold (mo) | eras (t) |
|---|---|---|---|---|---|---|---|---|---|
| `rev_on_event\|k=50\|vw\|none` | **0.879** | **+4.57** | **2.15** | 0.0198 | 11.7 | **0.229** | 0.989 | 1.01 | 2.93 / 0.23 / 0.11 |
| `rev_all_CONTROL\|k=300\|ew\|600` | 1.086 | +2.96 | 1.79 | 0.0154 | 299.4 | 0.616 | 0.521 | 1.92 | 3.28 / −0.03 / −0.53 |
| `rev_all_CONTROL\|k=100\|ew\|200` | 1.056 | +3.62 | 1.71 | 0.0154 | 100.0 | 0.423 | 0.832 | 1.20 | 3.59 / −0.23 / −1.08 |
| `hist_persistence\|k=100\|ew\|200` | 1.206 | +2.16 | 1.62 | 0.0136 | 100.0 | 0.421 | 0.125 | 7.90 | 2.22 / 0.96 / −0.36 |
| `hist_mean\|k=300\|ew\|600` | 1.226 | +1.32 | 1.04 | 0.0196 | 298.3 | 0.647 | 0.078 | 12.95 | 1.79 / 0.61 / −0.63 |
| **`reaction\|k=50\|vw\|none`** | **1.442** | +2.98 | 0.77 | 0.0078 | 12.7 | **0.145** | 0.438 | 2.46 | 1.08 / −0.15 / 0.24 |
| `pead_sue\|k=100\|ew\|200` | 1.268 | +0.96 | 0.58 | 0.0107 | 100.0 | 0.424 | 0.284 | 3.54 | 1.64 / −1.04 / −0.31 |
| **`reaction\|k=300\|ew\|600`** | 1.314 | **−0.53** | −0.32 | 0.0078 | 299.4 | 0.646 | 0.270 | 3.73 | 1.44 / −0.57 / −1.48 |
| *(worst)* `hist_trend\|k=100\|ew\|200\|**25bps**` | 1.270 | **−4.92** | −3.18 | −0.0003 | 99.6 | 0.424 | 0.219 | 4.65 | — |

**Typed exits** (invariant 17). A monthly rank book has exactly two ways to lose
a name and both are derived from the book's own weight path: **RANK_DECAY**
(fell out of the hold band while still admissible) and **UNIVERSE_EXIT** (left
the floored cross-section). No stop, target or deadline is reported, because
none is armed — a typed exit that cannot fire is a broken gate. Across the
grid RANK_DECAY runs 72–96% of exits; the UNIVERSE_EXIT share rises with the
hold band (`hist_mean|k=300|hold=600`: 1,793 of 6,311 exits, 28.4%), which is
what a 13-month mean hold on a small-name book should look like.

### 7.1 The grid's winner is the cell invariant 17 says you may not read

`rev_on_event|k=50|vw|hold=none|10bps` — β 0.879, +4.57 %/yr beta-matched,
t 2.15 — has **TC 0.229** and **effective breadth 11.7 names**. Invariant 17:
*"a book with TC < 0.5 is a construction defect and its signal verdict is
unreadable from it."* Its own numbers say the same thing three more ways:

* **turnover 0.989/month, hold 1.01 months, cost line 2.37 %/yr at 10 bps.**
  At 25 bps the same book is **+1.01 %/yr, t 0.48** — the edge is inside the
  spread.
* **Its era table is one era**: +1.024 %/mo (t 2.93) in 1999-2007, **+0.061 %
  (t 0.23)** in 2008-2015, **+0.031 % (t 0.11)** in 2016-2024.
* **MDE:** not powered — the observed beta-matched excess is under its own MDE
  on 309 months.

And then the matched controls, which were built before the result was looked at,
say something sharper than "it does not work". At `k=50|vw|hold=none|10bps` the
event condition genuinely helps:

| construction (10 bps) | **TC** | `rev_on_event` | `rev_off_event` | `rev_all` (no event condition) |
|---|---|---|---|---|
| `k=50\|vw\|hold=none` | **0.229** | **+4.57 % (t 2.15)** | +1.37 % (t 0.55) | −0.00 % (t −0.00) |
| `k=100\|ew\|hold=200` | 0.636 | +1.40 % (t 0.75) | +0.65 % (t 0.31) | **+3.62 % (t 1.71)** |
| `k=300\|ew\|hold=600` | 0.649 | −1.21 % (t −0.72) | +0.44 % (t 0.26) | **+2.96 % (t 1.79)** |

**The only construction where "revision-on-event" beats its unconditioned
control is the one whose transfer coefficient says its signal verdict cannot be
read.** At both constructions where TC > 0.6 — where the book actually expresses
the ranking — the *unconditioned* revision column wins and the event condition
costs 2–4 pp/yr. This is invariant 17 doing exactly the job it was written for,
on the first family it was pointed at.

At **25 bps** the entire revision block collapses: the best of the nine cells is
`rev_all_CONTROL|k=300` at **+1.10 %/yr (t 0.66)** — the *control* again —
`rev_on_event|k=50` is **+1.01 % (t 0.48)**, and **8 of the 18 revision cells
are negative**, one at **−4.52 %/yr (t −2.71)**.

### 7.2 The reaction signal does NOT survive construction — and that is the finding

§9's event-study cell is the only era-stable thing in this document. Put through
the same three constructions on the **floored** panel it produces **nothing**:
**+2.98 %/yr at t 0.77** at `k=50|vw`, and **negative** at both broad
constructions (−0.86 % and −0.53 %; −2.08 % and −1.51 % at 25 bps). Not one of
the six cells is powered for its own observed effect.

Three measured reasons, and they are different reasons:

* **β 1.31–1.47.** The high-reaction decile is a high-β book at monthly
  frequency. Its raw-market excess looks better than its beta-matched excess,
  which is precisely why β is printed first.
* **The floor.** The event study is unfloored; the book is not. On the
  `$3m/day` panel the reaction rank's monthly IC is **0.0078** — below
  `pead_sue` (0.0107) and less than half `rev_on_event` (0.0198). The effect
  lives in names the book may not own.
* **A horizon mismatch, and it is mine, not the market's.** The signal is a
  21-session clock from an announcement; the book is a monthly rank book whose
  entry date has nothing to do with the announcement and whose freshness gate is
  90 days. **This grid is therefore not a faithful test of §9's signal** — it is
  a test of "does the reaction rank work as a monthly cross-sectional
  selector?", and the answer to that is no. The event-clocked, floored version
  is not answered here and is §12 item 1.

This is the roadmap's four-stage story with a name on the stage: the prediction
is real and placebo-controlled, and it dies in **construction**.

### 7.3 DSR over the whole 78-cell book family

Best beta-matched Sharpe **0.4245** annualised; sd of the family's 78 Sharpes
**0.2392**; **expected max Sharpe under the null 0.584** — *larger than the
observed best*. **DSR 0.209**, against a 0.95 bar. A grid this wide would
produce a better-looking winner than this one by luck alone.

---

## 8. MULTIPLICITY — family sizes, family-max p, Holm, BH-FDR

**180 cells looked at**, enumerated (invariant 16), including every control and
every basis that only existed to be a control.

| family | size | FAMILY-MAX p | smallest p (any sign) | smallest p, **positive t** | Holm survivors (+t) | BH rejects |
|---|---|---|---|---|---|---|
| F1 PEAD multi-clock | 40 | 0.9566 | `raw\|1\|e2` < 1e-12 (t 6.34) | same | **37** | 39 |
| F2 + books | **78** | 0.9987 | `hist_trend\|k=100\|ew\|200\|25bps` 0.00148 (**t −3.18**) | `rev_on_event\|k=50\|vw\|10bps` 0.0312 (t 2.15), Holm **1.00** | **0** | 0 |
| F3 surprise × reaction | 14 | 0.9814 | big-surprise-small-reaction `bo\|5` 0.0630 (t 1.86), Holm 0.881 | same | **0** | 0 |
| F4 8-K items | 20 | 0.9958 | `item_5.02\|5d` 0.0089 (**t −2.62**) | `item_5.03\|5d` 0.0804, Holm **1.00** | **0** | 0 |
| F5 earnings history | 28 | 0.8775 | `hist_accel\|bo\|21` < 1e-12 (t 5.90) | same | **4** | 6 |
| **all** | **180** | 0.9987 | `F1.raw\|1\|e2` | same | **41** | 52 |

Two things this table is saying, and they are not the same thing:

1. **F3, F4 and every book cell die at Holm.** The gap, the 8-K items and all 72
   book cells have **zero** positive-t Holm survivors. F3 and F4 have zero BH
   rejections either, so they do not even clear the *screening* standard.
2. **F1 and F5's Holm survival is a statement about 1999-2024, not about now.**
   Of F1's 37 survivors, **17 are the `e1` lookahead entry** and **4 are the
   `ab` over-correction** — both carried for contrast, both counted in the
   family because invariant 16 says every cell looked at is charged. Of what is
   left, §3.3 has already shown the newest era at t 0.21–1.50. **A Holm-clean p
   on a 26-year sample and a dead newest era is the signature of DECAY, and the
   era table outranks the pooled p.**
   Similarly F5's four survivors are all `hist_accel`, which §5 showed is PEAD
   with a hat and shares its era profile.

**The signed-p column exists because of a bug this run had.** The first version
reported "smallest p in the family" without its sign and printed
`hist_trend|…|25bps` (a book that lost **4.9 %/yr** at t −3.18) as the family's
best cell, and separately read `(p or 1.0) <= 0.05` — where a p of exactly 0.0
is *falsy*, so the single strongest cell in the document was reported as *not
surviving Holm*. Both are fixed, both are pinned by test, and both are recorded
here rather than quietly corrected.

---

## 9. THE ONE LIVE RESULT — and it inverts the hypothesis I was sent to test

The mandate says the interesting cell is *a large fundamental surprise with a
small price response*. §4 measured that cell and it is nothing. The autopsy
(`R4_gap_autopsy.json`) asked the obvious next question — *what happens if you
rank on the reaction alone?* — and the answer runs the other way.

Decile spreads, `bo` basis, PIT `e2` entry, 311–312 event months:

| ranked on | 5 sessions | 21 sessions | 1999-2007 (21d) | 2008-2015 (21d) | **2016-2024 (21d)** | pre-event α diff / 60 sessions |
|---|---|---|---|---|---|---|
| **SUE** (the surprise) | +0.876 % (t 7.09) | +1.536 % (t 5.77) | t 4.01 | t 4.65 | **t 1.47** | **+4.44 %** |
| **the announcement REACTION** | +0.926 % (t 6.20) | **+1.804 % (t 7.37)** | t 6.13 | t 2.97 | **t 3.67** | **+0.68 %** |
| the GAP (surprise − reaction) | −0.022 % (t −0.17) | −0.221 % (t −0.85) | t −0.69 | t −0.19 | t −0.48 | +3.67 % |

Three things at once:

1. **The gap null now has a mechanism, not a shrug.** The surprise rank and the
   reaction rank correlate ρ **0.32** over 280,945 events and *both* carry
   positive forward returns. Differencing them nets a dead signal against a live
   one. "Large surprise, small reaction" is not the diffusion cell — it is a
   subtraction that cancels the only term that still works.
2. **The reaction is the one thing here that does not decay.** t 6.13 / 2.97 /
   **3.67** across the three eras, against SUE's 4.01 / 4.65 / **1.47**.
3. **And it is not repackaged prior drift.** The two extreme reaction deciles
   differ in pre-event α by **+0.68 % over 60 sessions**; the two extreme SUE
   deciles differ by **+4.44 %**. §3.2's decomposition, which kills 21-day PEAD,
   barely touches the reaction signal. Breakeven cost: **45 bps a side** on the
   full sample, **39 bps** in 2016-2024 — clear of this repo's 25 bps grid.

This is the announcement-return version of the drift, not the surprise version,
and the literature has said the two are different since Chan-Jegadeesh-Lakonishok
(1996). It is stated here as a **screen result under a `PRODUCT_EXPERIMENT`
licence**, and nothing more.

> **Read §7.2 before doing anything with this.** The same signal, put through
> the three constructions on the `$3m/day`-floored panel, produces **+2.98 %/yr
> at t 0.77** and is negative at both broad constructions. The prediction is
> real and placebo-controlled; it does **not** currently become a book. §7.2
> separates the two reasons that are the market's (β 1.44, the liquidity floor)
> from the one that is mine (a monthly rank book is not a faithful test of a
> 21-session event clock), and §12 item 1 is the measurement that settles it.

### 9.1 The placebo-date control — the sign flips, and that settles it

A two-session move that predicts the next twenty-one is, on its face, indistinct
from short-horizon price momentum. So the whole machinery was re-run with **one
change: session 0 moved 40 trading sessions AFTER the announcement.** Same
companies, same months, same market model, same clocks, same ranking — no event.
`R4_placebo_control.json`, 335,226 pseudo-events, 309–310 date blocks.

| ranked on | **at the announcement** (5 d) | **placebo, +40 sessions** (5 d) | announcement (21 d) | placebo (21 d) |
|---|---|---|---|---|
| SUE | +0.876 % (t 7.09) | +0.113 % (t 1.07) | +1.536 % (t 5.77) | +0.374 % (t 1.28) |
| **the 2-session move** | **+0.926 % (t 6.20)** | **−0.908 % (t −6.47)** | **+1.804 % (t 7.37)** | **−0.563 % (t −2.04)** |
| gap | −0.022 % (t −0.17) | +0.506 % (t 4.72) | −0.221 % (t −0.85) | +0.571 % (t 2.07) |

**The sign flips.** Away from an announcement, a two-session move is followed by
**reversal** (t −6.47), which is the ordinary short-horizon reversal every
textbook carries, and it reverses in all three eras (t −4.75 / −3.20 / −3.33).
*At* an announcement the same two-session move is followed by **continuation**
(t +6.20). The two are 1.83 pp apart at five sessions.

So the §9 result is **not** repackaged price momentum, and it is not repackaged
reversal either: it is announcement-conditional continuation, and the event is
doing the work. The placebo also confirms the machinery is not manufacturing
spreads — SUE reads t ≈ 1.1 on a non-event date, which is the null it should be.

*(The placebo `gap` column is positive for the arithmetic reason: away from an
event `gap = sue − reaction` is dominated by *minus* a reversing term.)*

---

## 10. WHAT DID NOT WORK, AND WHAT I DID NOT DO

**Did not work (findings, each with its receipt):**

* **The surprise-reaction gap (F3).** Zero Holm survivors, zero BH rejections,
  nothing above |t| 1.86 in 14 cells. Mechanism in §9. Status:
  `FAILED_VARIANT` — *this construction of the gap*, not "expectation-reaction
  gaps do not exist". The obvious untried version is a **magnitude-matched**
  gap rather than a rank difference, and it is named in §12 rather than run.
* **8-K item families (F4).** Zero Holm survivors, zero BH rejections, best cell
  −15 bp, and the sample cannot support a universe claim anyway. Status:
  `DEPRIORITIZED` until a PIT 8-K universe exists (a full-index backfill, not
  `company_tickers.json`).
* **Six of the seven earnings-history features.** Dispersion, magnitude, trend,
  reversals, persistence and the trailing mean all fail Holm; five of the six
  are not powered for their own observed effect. Status: `FAILED_VARIANT`.
* **Every one of the 78 book cells**, the six `reaction` cells included. Zero
  positive-t Holm survivors, zero BH rejections, DSR 0.209 against 0.95, and the
  expected max Sharpe under the null (0.584) exceeds the observed best (0.4245).
* **`gap_cell` as a selector.** SKIPPED with a printed reason — 14,104 non-null
  rows after the floor, under the 20,000 threshold. A two-valued selector under
  top-k is a coin toss inside the cell; running it anyway would have produced a
  number that meant nothing.

**Not done, and why:**

* **No news-conditioned family was run at all.** §1.3 — refused, not null.
* **The event study is UNFLOORED.** It runs over every IBES-linked CRSP name; no
  `$3m/day` gate. That flatters every event-study number in §3-§5 and is stated
  wherever those numbers appear. Only §7's books are floored.
* **No intraday data.** IBES carries no announcement time, so both entry
  conventions are session-level. The single highest-value missing input for this
  family is an announcement *timestamp*: it would collapse `e1` and `e2` into
  one honest number instead of a range.
* **No 13D/13G, no Form 4.** Block I, not this lane. The event table's own
  manifest records both as absent, not fabricated.
* **No LLM call.** $0.00 spent, DeepSeek balance untouched.
* **No commit, no push, no deploy, no seal, no order.** Files written are listed
  in §13.
* **`arena_composite` untouched.** Nothing here was folded into it. Had a family
  survived it would have become its own `PRODUCT_EXPERIMENT` book, per
  CLAUDE.md's THE BOTTLENECK — a weight in a composite hides the only question
  worth asking, which is whether its errors are different errors.

---

## 11. TESTS

| | suite | result |
|---|---|---|
| **baseline**, this checkout, before any edit of mine | `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow" -q --timeout=300` | **7,409 passed, 1 failed, 20 skipped, 124 deselected** in 778 s |
| **the one failure** | `test_signal_reachability.py::test_every_orphan_is_classified` | **not mine** — it named `backend.strategy.{execution,leak,manifold,vendor,…}` at baseline and `backend.vendor.aat.alpha.human` an hour later, i.e. block S and block H landing in this shared tree while the suite ran. I did not classify another lane's modules |
| **new** | `backend/tests/test_r4_event_families.py` | **17 checks, all pass**, 1.7 s |

The new suite is offline and loads no panel. It pins the three things that can
be *plausible and wrong* here: the multiplicity helpers (including a
regression test that the DSR uses the Gaussian quantile, not the Gumbel one the
first draft shipped); that `_monthly_spread` returns one number per **event
month** and drops thin months rather than averaging them; that a pure-market
month reads as no spread while a planted effect is recovered with the right
sign; that `era_table` names all three eras and never pools; that typed exits
separate RANK_DECAY from UNIVERSE_EXIT; and that the receipt still names all
four coverage readings and that its "MET in every year" sentence agrees with its
own year table (the X9 lesson). `price_panel_bound` is tested to **derive** its
bound from the files on disk, so a 2025 daily file landing would move it instead
of being missed.

---

## 12. WHAT THE NEXT SESSION SHOULD DO WITH THIS

1. **An EVENT-CLOCKED, floored book for the reaction signal.** §7.2 tested it
   as a *monthly cross-sectional* selector and it failed; that grid does not
   test the signal §9 actually found, because its entry date has nothing to do
   with the announcement and its freshness gate is 90 days. The faithful test
   enters at session +1 after each announcement, holds 21 sessions, applies the
   `$3m/day` floor and pays 25 bps a side. It is the single highest-value next
   measurement in this lane and the machinery for it already exists
   (`R4_earnings_events.parquet` carries every clock; what is missing is a
   dollar-volume column on the tape).
2. **An announcement timestamp** collapses `e1`/`e2` from a range into a number
   and is worth more than any new model here. Earnings-call and press-release
   times are free from several sources; none is currently joined.
3. **The magnitude-matched gap.** §4 differenced two *ranks*. The version that
   was not tried is a gap in comparable units — surprise in σ against reaction
   in σ of the name's own pre-event vol — which does not require the two terms
   to have the same distribution. `FAILED_VARIANT`, not `MECHANISM_REJECTED`.
4. **E3's gate should be rewritten to name its reading.** As written it blocks a
   family (earnings) that clears 90 % in all 26 years on the only reading a book
   can use, and it does not block the family (news) that is actually
   ungradeable. Suggested wording is in §14.
5. **Do not run the 8-K family again until the universe is PIT.** A full-index
   EDGAR backfill, not `company_tickers.json`.
6. **`--redo-degraded` before anyone quotes a news coverage number again**
   (§1.4).
7. **The trailing-8-quarter mean surprise (§5) deserves one honest re-test, not
   a book.** Raw p 0.0027, Holm 0.065, sign-flipping across eras — that is a
   candidate, not a finding. The discriminating question is whether it is
   separable from quality/profitability, which the panel already carries
   (`growth_g2_generation0._load_roe`): if a book on `roe_pit` holds the same
   names, "consistent surprises" is quality wearing a different name.

---

## 13. FILES WRITTEN (nothing committed, nothing pushed)

```
scripts/r4_event_families.py                                    new (1,749 lines)
backend/tests/test_r4_event_families.py                         new (17 checks)
docs/BUILD_2026-09-08_R4_EVENT_FAMILIES.md                      this file
backend/data/optimus/r4_event_families/R4_event_families.json   the receipt (stages 1-8)
backend/data/optimus/r4_event_families/R4_earnings_events.parquet   the event tape, 339,858 rows
backend/data/optimus/r4_event_families/R4_tape_build.json       tape provenance per cohort
backend/data/optimus/r4_event_families/R4_gap_autopsy.json       §9's three-way comparison
backend/data/optimus/r4_event_families/R4_placebo_control.json   §9.1
backend/data/optimus/r4_event_families/R4_placebo_offset40.parquet   the placebo tape, 335,226 rows
```

The two `.parquet` files (139 MB each) are covered by `.gitignore`'s `*.parquet`
and will not enter a commit; the six JSON receipts total 610 KB. Two intermediate
receipts written during the run (`R4_books_v2.json`, `R4_pead_multiclock.json`)
were **merged into `R4_event_families.json` and deleted** rather than left on
disk to be quoted later — two receipts with different family sizes is how a
family size gets under-reported.

Nothing in `aegis-alpha-terminal` was touched. The two news-puller PIDs (50240,
139180) were never signalled. `.env` was never moved. No process was killed by
image name — no process was killed at all.

**Memory discipline.** The bar is ≥ 6 GB free before a heavy job. The event tape
is built in five-year cohorts (~350 MB) precisely so it is not one; the panel
stage was held back once when free RAM read **3.65 GB** and run when it
recovered. Stated rather than hidden.

---

## 14. PROPOSED AMENDMENT TO THE E3 GATE

The roadmap row reads: *"gated on E2 ≥ 90 % coverage per year"*. Replace with:

> **E3 is gated per FAMILY, on the share of the graded monthly panel carrying
> that family's events in a year (reading D), and no family may be graded in a
> year without a price panel.**
> * earnings families (IBES): **MET**, 95.1–98.2 %, 1999-2024 — run them.
> * 8-K item families: **NOT MET** and the universe is not PIT — SLICE only.
> * news families: **REFUSED** — the years with coverage have no price panel and
>   the years with a price panel have ~1 % coverage. Lift by finishing the
>   2015-2024 whole-market pull.

Suggested `§6` status row for `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md`
(the lead session owns the edit; I have not made it):

> | **E3 event books** | **RUN 2026-09-08 — the gate was ambiguous and is now four named readings: earnings families MET (95.1-98.2 % of the graded panel, 26 years), 8-K a survivor-conditioned SLICE, news REFUSED for want of a 2025-26 price panel. 180 cells. PEAD is a 1-5 session effect that DECAYED after 2015 (t 8.40/4.99/**0.21**) and whose 21-60 day part is smaller than the deciles' own pre-event drift (+4.44 % over 60 sessions); 92.5 % of "one-day PEAD" was an entry-convention lookahead. The surprise-reaction GAP is nothing and §9 says why. The announcement REACTION is era-stable (t 6.13/2.97/3.67), carries no prior drift, and REVERSES on a placebo date — a real prediction that then DIES IN CONSTRUCTION (+2.98 %/yr t 0.77 floored at k=50; negative broad). Zero positive-t Holm survivors in 78 book cells; DSR 0.209 with the null's expected max Sharpe above the observed best. Nothing armed, nothing folded into `arena_composite`.** | `BUILD_2026-09-08_R4_EVENT_FAMILIES.md`, `R4_event_families.json`, `R4_placebo_control.json` |


