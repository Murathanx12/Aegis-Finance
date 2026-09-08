# BUILD 2026-09-08 — R2: WHAT IS ACTUALLY IN THE INSIDER TAPE

**Lane:** R2, the first measurement on the I1 substrate
(`docs/BUILD_2026-09-07b_I1_SEC_INSIDER.md`, block I of
`ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md`).
**Licence:** `PRODUCT_EXPERIMENT`. Explore dirty, promote clean. **No alpha is
claimed.** What follows is a measurement with its beta printed first, its costs
charged, its family corrected and its power stated.
**LLM spend: $0.00** — no model was called in this lane.

## 0. RESULTS SCOREBOARD

| | |
|---|---|
| Best historical net strategy vs the market | **none promoted.** Best net-of-cost long-short: `opp − routine`, h=63 sessions, EW, tradable-only, **+68.8 bp/month at 10 bps a side, t 2.69, Holm p 1.000, BH q 0.033, DSR 0.008** — a screen, not an export |
| Best forward paper strategy | **none.** Nothing was seeded, ordered, or promoted |
| Independent selector count | **unchanged.** No new book was created |
| Farm candidates tested / promoted | 236 cells graded / **0 promoted** |
| New actionable finding | **the opportunistic-minus-routine spread is an illiquidity / micro-cap POPULATION effect, not an edge.** It is +12.3 bp (t 0.34) value-weighted; +21.4 bp equal-weighted with an SMB loading of +0.227 (t 1.98); **+2.7 bp (t 0.15)** once controls are matched on size quintile; and **−18.8 bp** above the $3m/day floor. 71% of opportunistic-buy cells are micro or nano cap and the median one trades **$0.65m/day**, one fifth of the house floor |
| External execution drag | h=1 books turn over **54.5× notional a month**; at the house's own 10 bps a side that is **−545 bp/month of cost against a +154 bp gross alpha**, i.e. net −394 bp (t −11.7) |
| LLM spend / cost per gradeable output | **$0.00 / $0.00** |

**RESULT IMPROVEMENT: NONE.** Nothing here raises the demonstrated edge. What it
does is close two questions with evidence and hand back a 20-year substrate with
its base rates measured.

**The one-sentence version.** Over 2009-2024, 3.13M Form 4 events, 192 months
and 236 graded specifications: **the Cohen-Malloy-Pomorski opportunistic-minus-
routine long-short earns +12.3 bp/month value-weighted (t 0.34) against its
82 bp prior, and every cell that survives the family correction either turns over
54× a month or lives below the $3m/day execution floor.**

**And the finding that leads, because it is the one that generalises:** the spread
is **a loading on where insiders buy, not on what they know.** Value-weight it and
it is +12.3 bp with t 0.34. Equal-weight it and it is +21.4 bp with an **SMB
loading of +0.227 (t 1.98)** — a size factor with a Form 4 label. Match the
controls on size quintile and the opportunistic class is **+2.7 bp with t 0.15**.
Apply the house's own $3m/day execution floor and it is **−18.8 bp**. Every step
that removes the small-cap population removes the number. §7.5 is the section
that matters.

---

## 1. WHAT WAS BUILT, AND HOW TO RE-RUN IT

`scripts/r2_insider_lab.py`, seven stages, each with its own receipt in
`backend/data/optimus/insider_lab/`:

```bash
python -m scripts.r2_insider_lab base        # base rates              -> r2_base_rates{,_holdings}.json
python -m scripts.r2_insider_lab spine       # (permno, month) panel   -> r2_spine.parquet + receipt
python -m scripts.r2_insider_lab cmp         # the CMP replication     -> r2_cmp.json
python -m scripts.r2_insider_lab daily       # declared entry, daily   -> r2_daily.json + turnover
python -m scripts.r2_insider_lab matched     # winner vs matched loser -> r2_matched.json
python -m scripts.r2_insider_lab traps       # size/illiq/PEAD/floor   -> r2_traps.json
python -m scripts.r2_insider_lab adjudicate  # the family correction   -> r2_adjudication.json
```

**Inputs, all offline and already on disk.** `insider_events_v1.parquet` (I1) ·
the 82 parsed quarters (for `shares_owned_following`, which the event table
drops) · `aegis_panel_v2.parquet` (JKP US monthly, 1926-2024, `me`, `dolvol_126d`,
`ff49`, `ret_exc_lead1m`) · `crsp_dsf_2009..2024.parquet` (daily, with
`openprc`) · `comp__fundq.rdq` + `crsp__ccmxpf_lnkhist` (the earnings calendar) ·
`learner.benchmark._load_pinned_ff` for FF5+Mom+RF.

**`learner.benchmark` is THE ONE RULER and was not bypassed.** The monthly
factors are the hash-gated pinned daily vintage compounded month by month; no
refetch, no substitution.

### Caveats inherited from I1, not rediscovered

* `observed_at_utc` is the **filing date, end of day**. There is no acceptance
  timestamp in `SUBMISSION.tsv`. Entry is the **next session's open**, and §4
  implements exactly that (open-to-close on the entry session).
* **2006-2008 is a warm-up window** — the three-strictly-prior-years CMP rule
  cannot classify there. Every CMP number in this document is **2009+**.
* **CRSP's entitled vintage ends 2024-12-31.** The book window is **2009-2024**,
  192 months. 2025-26 rows are `REFUSED_OUTSIDE_CRSP_VINTAGE`, not unlinked.
* `plan_10b5_1 == UNKNOWN` on 8.36M rows. Treated as **missing**, never as "no".
* 161,106 code-`P` rows are not discretionary open-market stock buys; the five
  clauses of `is_open_market_purchase` were used as I1 defined them.

---

## 2. BASE RATES FIRST

Receipts: `r2_base_rates.json`, `r2_base_rates_holdings.json`,
`r2_spine_receipt.json`.

### 2.1 How many, and where

| | |
|---|---|
| Event rows | 3,127,624 (2006-01-04 → 2026-07-01) |
| Buy rows in the 2009-2024 book window | **761,453** (opportunistic 160,674 · routine 72,492 · unclassifiable 528,287) |
| Sell rows, same window | 1,147,164 |
| Distinct permnos with a buy, per month | median **377**, p10 178, p90 582 |
| Distinct symbols with a buy, per month | median 558 |
| Buys per issuer per year | median **4**, p75 11, p90 27, p99 180 |
| Issuers with any buy, per year | median **2,974** |
| Cluster (≥3 insiders, one filing day) buy rows | 348,733 |
| Roles on buy rows | 10% holder 52.9% · director 44.7% · officer 26.1% |

### 2.2 The link rate is NOT the one in the I1 doc, and the difference is the finding

| family, 2009-2024 | rows | permno link |
|---|---:|---:|
| `insider_open_market_sell` | 1,147,164 | **86.0%** |
| `insider_open_market_buy` | 528,287 | **68.4%** |
| `insider_opportunistic_buy` | 160,674 | 70.1% |
| `insider_routine_buy` | 72,492 | 69.4% |

I1 reports 82-88% link per year; that figure is over **all transaction rows**,
which are dominated by sells at large listed issuers. **Buys link 18 points
worse than sells inside the same window** — insider buying happens
disproportionately at issuers CRSP does not carry (OTC, foreign private issuers,
funds). Nothing is broken; the two numbers answer different questions, and a book
that quotes 85% coverage for a BUY signal would be overstating it by a fifth.

### 2.3 Size — in dollars, and as a share of the insider's own stake

| family (2009-2024) | p25 | **median** | p75 | p90 | p99 |
|---|---:|---:|---:|---:|---:|
| open-market buy (unclassifiable) | $3,495 | **$20,000** | $129,329 | $994,835 | $25.0m |
| opportunistic buy | $3,400 | **$19,680** | $170,319 | $1.42m | $23.6m |
| routine buy | $1,860 | **$8,040** | $33,567 | $191,250 | $5.0m |
| open-market sell | $15,154 | **$106,125** | $667,128 | $4.03m | $228m |

**The median insider buy is $20,000 and moves the insider's own stake by 0.96%**
(`shares / shares_owned_following`: p25 0.13%, median **0.96%**, p75 7.6%,
p90 39.6%, p95 100%). Half of all open-market purchases change the buyer's
position by less than one percent. That is the base rate a conviction story has
to clear, and it is the reason the "insiders bet big" prior needs to be a
*filter* before it is a signal.

**A data defect that would have poisoned any value-weighted book.**
`insider_dollar_value` carries a filer-error tail: **2,734 of 761,453 buy rows
exceed $100m and 448 exceed $100bn**, because filers put the total consideration
in the price field (`ASTI`, 2021-08-05: 666,666,672 shares at "$10,000,000";
`GOBI`: 20,000,000 shares at "$200,000,000"). The mean buy value is **$123
billion** against a p99 of $25m. The spine caps at the issuer's own market
capitalisation — an insider cannot buy more of a company than the company is
worth — and **counts** the 265 (permno, month) cells that fail rather than
clipping them silently. Anyone screening on the raw column is screening on a
dozen typos.

### 2.4 The filing lag

Median **3 days**, p75 5, p90 6 — Section 16 works. The tail does not: **p99 is
427 days** across all events and **750 days for buys** (Form 5 catch-ups and late
amendments). 2024's p99 is 3,205 days. 592 rows carry a negative lag (the 670
future-dated rows I1 already documented, restricted to this window).

**This is why keying on the filing date matters and why it is not enough.** A
"buy" whose transaction was two years earlier is public information about a
two-year-old decision. It is PIT-legal and informationally stale, and it sits in
the same family as a three-day-old trade. No stage here separates them; a book
built on this tape should, and that is a named piece of future work.

### 2.5 The spine

`r2_spine.parquet`: **956,972 (permno, month) rows**, 229 months, 10,025
permnos, US common primary main-listed. 95,311 rows carry a buy, 158,441 a sell,
16,508 an opportunistic buy, 5,142 a routine buy, 15,735 a cluster buy.
177,356 panel rows were dropped for a missing permno (counted, not silent).

**48.6% of the universe clears the house execution floor ($3m/day average dollar
volume + $5 price). Only 34.9% of buy-months do.** That single line predicts
most of what follows.

---

## 3. THE CMP REPLICATION — BETA FIRST

Receipt: `r2_cmp.json`. Convention: a filing observed inside month *t* forms the
portfolio at eom(*t*) and earns month *t+1* (`ret_exc_lead1m`, JKP
delisting-aware). That is **strictly more conservative** than the next session's
open. `n_effective` = **192 months**, date blocks, never name-months.

**Read the market first: over 2009-2024 the value-weighted market excess return
averaged +116 bp/month (14.85%/yr, sd 4.50%).** Any long leg with beta ≈ 1 and a
raw excess below 116 bp has *negative* alpha, and most of them do.

### 3.1 The long legs, value-weighted

| arm | **beta** | CAPM α (bp/mo) | t (NW6) | FF6 α | t | raw excess | t | names/mo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| opportunistic buy | **+0.979** | **−40.1** | −1.20 | −13.7 | −0.42 | +79.1 | +1.88 | 80 |
| routine buy | **+0.681** | −16.1 | −0.66 | −19.6 | −0.91 | +66.8 | +1.94 | — |
| any buy | **+1.095** | −14.3 | −0.95 | −1.8 | −0.14 | +119.0 | +3.16 | — |
| any sell | **+0.959** | +11.1 | +1.40 | +4.7 | +0.64 | +127.9 | +4.01 | — |
| **no insider activity at all** | **+1.032** | −5.8 | −1.35 | −2.5 | −0.64 | **+119.8** | +3.59 | 3,013 |

**The bottom row is the whole section.** A value-weighted portfolio of names *no
insider touched that month* earned +119.8 bp/month; a portfolio of names insiders
bought earned +119.0. **Being bought by an insider is, at monthly frequency and
value weights, indistinguishable from being ignored.** The +79 bp on opportunistic
buys is not a reward for following insiders; it is 0.98 units of equity beta
earning less than the equity premium.

### 3.2 The long-shorts, and the 82 bp prior

| long-short | beta | CAPM α | t | raw | t | MDE @80% | powered vs the 82 bp prior? |
|---|---:|---:|---:|---:|---:|---:|:--:|
| **opp − routine, VW** | +0.298 | −24.0 | −0.73 | **+12.3** | **+0.34** | 101.9 bp | **NO** — the design cannot see an 82 bp effect |
| opp − routine, EW | +0.211 | −4.3 | −0.24 | +21.4 | +0.89 | 67.3 bp | **yes** |
| buy − sell, VW | +0.136 | −25.5 | −1.27 | −8.9 | −0.49 | 51.0 bp | yes |
| buy − sell, EW | +0.057 | +7.3 | +0.43 | +14.3 | +0.89 | 44.9 bp | yes |
| opp − no-activity, VW | −0.052 | −34.3 | −1.01 | −40.7 | −1.44 | 79.1 bp | yes |
| buy − no-activity, EW | +0.004 | +14.6 | +1.26 | +15.1 | +1.39 | 30.4 bp | yes |

**The power check, before the confirmation (canon §64), and stated against the
PRIOR rather than the observed effect** — a power flag built on the observed
effect is the t-test again
([[feedback-a-power-flag-built-on-the-observed-effect-is-the-t-test]]).

* The **value-weighted** test — the one CMP actually ran — has an MDE of
  **101.9 bp/month against an 82 bp prior**. It is **UNDERPOWERED to detect
  CMP's own effect.** Its +12.3 bp / t 0.34 is `CANNOT_DETERMINE`, not a refutation.
* The **equal-weighted** test has an MDE of 67.3 bp and *is* powered against
  82 bp. It sees **+21.4 bp, t 0.89.** That is a real negative: on this tape and
  window, an equal-weighted opportunistic-minus-routine book **does not carry an
  82 bp/month effect.**

### 3.3 Three eras, reported separately and never pooled

The house grid (`evaluate.long_eras()`: 1999-2007 / 2008-2015 / 2016-2024) cannot
be applied — nothing before 2009 is classifiable. The window is cut into three
near-equal blocks and **the deviation is declared** rather than a grid quietly
re-used that does not describe the data (the `evaluate.ERAS` failure of
2026-09-07 wearing a different hat).

| opp − routine, VW | 2009-2014 (n 71) | 2015-2019 (n 60) | 2020-2024 (n 60) |
|---|---:|---:|---:|
| beta | +0.16 | +0.51 | +0.33 |
| CAPM α | −9.6 (t −0.22) | −40.1 (t −0.76) | +3.5 (t +0.05) |
| raw excess | +15.2 | +5.3 | +38.3 |

**Signs do not agree across eras** (`eras_same_sign: false`). The verdict rule's
"sign holds in ≥2 of 3 eras" is not met for the CMP long-short in either
weighting.

### 3.4 With the execution floor on

| opp − routine, VW, tradable only | value |
|---|---:|
| beta | +0.270 |
| CAPM α | **−51.6 bp** (t −1.27) |
| raw excess | **−18.8 bp** (t −0.45) |
| months | **154** — 38 months had fewer than 5 tradable routine names and are a **counted refusal**, not a one-name portfolio |

The routine leg thins out badly above the floor; that refusal is itself a
finding, and it is why the tradable long-short is graded on 154 months rather
than 192.

---

## 4. THE DECLARED ENTRY CONVENTION — DAILY, AND WHY IT CHANGES THE ANSWER

Receipt: `r2_daily.json`. The monthly convention delays entry by up to 30 days,
which is not what I1's `next_tradable_session_bound()` says. §4 implements the
real rule: **on session *s* a name is held if a qualifying filing landed on a
session in [s−h, s−1]; the entry session is priced OPEN-to-CLOSE** (2.74% of
opens are missing and fall back to close-to-close, counted). 15,307,996 daily
rows over 7,259 permnos; daily returns are compounded to **months** before
grading, so `n_effective` is still date blocks.

**Costs are never omitted.** One-way turnover is **measured exactly** — the sum
over sessions of Σ|w_s(i) − w_{s−1}(i)| — not assumed from a closed form, and
charged at 10 bps (the house rate) and 25 bps a side.

### 4.1 The gross signal is real at short horizons and the cost is larger

| book | h | beta | gross α | t | **turnover/mo** | **net@10** | t | **net@25** | t |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| buy − sell, EW, tradable | 1 | +0.02 | **+154** | +4.76 | **54.5×** | **−394** | −11.7 | −1216 | −33.3 |
| buy − sell, EW, tradable | 5 | +0.16 | +82 | +3.50 | 16.9× | −87 | −3.70 | −341 | −14.3 |
| buy − sell, EW, tradable | 21 | +0.20 | +42 | +2.37 | 5.7× | −15 | −0.85 | −100 | −5.71 |
| buy − sell, EW, tradable | 63 | +0.17 | +33 | +2.71 | 1.4× | **+19** | +1.59 | −3 | −0.25 |
| opp − routine, EW, tradable | 21 | +0.48 | +22 | +0.59 | 5.6× | −34 | −0.92 | −119 | −3.18 |
| opp − routine, EW, tradable | 63 | +0.11 | **+73** | +2.83 | 1.8× | **+55** | **+2.16** | +28 | +1.12 |
| opp − routine, VW, tradable | 63 | +0.31 | +31 | +0.95 | 1.7× | +14 | +0.43 | −12 | −0.38 |

**The strongest gross result in the whole lane — `buy − sell` at h=1, EW,
+238 bp/month with t 7.42 — is the least real thing in it.** It requires trading
the entire book 55 times a month; at the house's own 10 bps a side it loses
−359 bp/month with t −11.0. It is a microstructure return, not an insider
return.

### 4.2 The long legs prove the CAPM is the wrong control here

| book (h=63, VW, tradable) | beta | CAPM α | t | net@10 α | t |
|---|---:|---:|---:|---:|---:|
| any **buy** | +1.02 | +56 | +3.88 | +46 | +3.26 |
| any **sell** | +0.89 | **+68** | **+6.43** | +63 | +6.18 |
| buy − sell | +0.13 | −12 | −0.86 | −27 | −1.91 |

**Insider *selling* carries a larger CAPM alpha than insider buying.** Nobody
believes insider sales predict outperformance; what this says is that a
*filtered, tradable, value-weighted* slice of 2009-2024 beat the FF market
regardless of which insider event selected it. That is
[[feedback-an-ew-average-against-a-vw-market-is-the-regime]] in a new costume,
and it is the reason §5 exists: **the honest control is drawn from the same
universe and the same month, not from Ken French's market.**

### 4.3 Clusters: is a cluster different from the sum of its parts?

| | gross α | t | net@10 | t | net@25 | t |
|---|---:|---:|---:|---:|---:|---:|
| `cluster_buy` h=63 VW tradable | +81 | +3.16 | +70 | +2.73 | +53 | +2.07 |
| `solo_buy` h=63 VW tradable | +63 | +3.28 | +53 | +2.82 | +38 | +2.09 |
| **`cluster − solo`** h=63 VW tradable | **+19** | **+0.74** | **+3** | +0.11 | −35 | −1.34 |
| `cluster − solo` h=21 VW tradable | +50 | +1.61 | −11 | −0.34 | −102 | −3.22 |
| `cluster − solo` h=5 EW tradable | +93 | +1.86 | −61 | −1.22 | −293 | −5.89 |

**Answer: no.** A cluster buy and a solo buy earn the same thing. The cluster's
apparently strong long leg is the same thing the solo leg has, and the difference
— which is the only estimate that isolates "clusterness" — is +19 bp with
t 0.74 gross and +3 bp net. The matched design in §5 agrees: `cluster_buy` vs
matched controls is **−12.8 bp/month, t −0.50**.

---

## 5. WINNER vs MATCHED LOSER

Receipt: `r2_matched.json`. Coarsened exact matching on
**month × FF49 sector × size quintile × volatility quintile × momentum quintile**
(`rvol_252d` and `ret_12_1`, both measured at formation). The estimate is the
treated-minus-control mean computed **cell by cell** and pooled with
treated-count weights, giving one number per month; `n_effective` = **192
months**, never name-months
([[feedback-name-days-are-not-periods]]).

**Nothing realised after the event is in the match.** Picking a control on the
outcome is a documented past failure here
([[feedback-a-matched-control-must-not-be-picked-on-the-outcome]]), so the design
carries a **leak canary**: re-run the same match with the outcome quintile added
as a match key. It collapses to **−5.0 bp, t −0.47** on 24,916 cells — the
matching binds.

### 5.1 One month forward

| treatment | mean diff | t | cells | 2009-14 | 2015-19 | 2020-24 |
|---|---:|---:|---:|---:|---:|---:|
| any buy | +14.3 bp | +1.35 | 33,198 | +11.2 (0.81) | +36.1 (2.05) | −3.9 (−0.16) |
| **opportunistic buy** | **+2.7 bp** | **+0.15** | 9,617 | +34.7 (1.68) | +10.1 (0.29) | −43.3 (−1.18) |
| routine buy | −19.2 bp | −0.95 | 3,561 | −15.4 | +31.3 | −74.3 |
| cluster buy | −12.8 bp | −0.50 | 7,134 | −18.2 | +67.6 | −86.9 |
| solo buy | +20.1 bp | +1.79 | 29,502 | +19.1 | +26.0 | +15.4 |
| **any sell** | **−16.5 bp** | **−2.43** | 53,365 | −28.0 (−3.27) | −11.3 | −7.9 |
| any buy, **tradable only** | **+1.8 bp** | **+0.11** | 13,506 | | | |
| any sell, **tradable only** | **−0.0 bp** | **−0.00** | 35,562 | | | |

Two things:

1. **The only nominally significant one-month matched result is the SELL side**
   (−16.5 bp, t −2.43) — and it is **exactly zero above the execution floor**
   (−0.0 bp, t 0.00). It is an illiquidity effect wearing a Form 4 badge.
2. **`opportunistic_buy` against a matched control is +2.7 bp with t 0.15.** The
   CMP mechanism's whole claim is that *this* class is the informed one. Against
   size, sector, volatility and momentum, on this tape, it is not.

### 5.2 Three and twelve months — and the overlap correction that halves the t

`fwd_exc_3m` and `fwd_exc_12m` are **cumulative** returns sampled monthly, so
consecutive rows share 2 and 11 months of the same tape. A plain t across months
is inflated by roughly √h. Both are reported; **the Newey-West t at h−1 lags is
the one that counts** — this is the same arithmetic that turned +740% into
+96.7% (`learner/benchmark.py`).

| treatment, horizon | cumulative diff | per-month equiv | t naive | **t NW(h−1)** |
|---|---:|---:|---:|---:|
| any buy, 3m, full | +63.3 bp | +21.1 | +3.46 | **+3.43** |
| any buy, 3m, **tradable** | +6.6 bp | +2.2 | +0.31 | **+0.32** |
| cluster buy, 3m, full | +133.5 bp | +44.5 | +3.14 | **+2.90** |
| cluster buy, 3m, **tradable** | +48.5 bp | +16.2 | +0.68 | **+0.60** |
| any buy, 12m, full | +150.3 bp | +12.5 | +3.55 | **+2.76** |
| any buy, 12m, **tradable** | +129.1 bp | +10.8 | +2.27 | **+1.88** |
| solo buy, 12m, full | +139.3 bp | +11.6 | +2.97 | **+2.61** |
| opportunistic buy, 12m, full | +16.0 bp | +1.3 | +0.22 | **+0.18** |
| routine buy, 12m, tradable | −219.5 bp | −18.3 | −1.75 | **−1.21** |

**The one surviving shape in the whole lane:** *any* insider buy is followed by
~+150 bp of matched-control-adjusted excess return over the next twelve months
(t 2.76), and it is **not** the opportunistic class (+16 bp, t 0.18) — it is the
broad, mostly-unclassifiable population of buyers. Above the execution floor it
is +129 bp with **t 1.88**, and it does not survive the family
correction — BH q **0.167**, DSR 0.002, and its top-5 months carry **58%** of the
total (§6). 12.5 bp/month before costs is also below any plausible round-trip on a
median-$266m-cap name.

---

## 6. THE ADJUDICATION

Receipt: `r2_adjudication.json`.

**The family is 236 cells.** It is not the cell that won: it is every long-short
book and every matched difference this lane graded — two conventions (monthly
formation, daily next-open), four horizons, two weightings, two floors, gross and
net at two cost rates. Family max p **0.9985**, min p **0 to double precision** (the h=1 net-of-cost losers).

| rule | | |
|---|---|---|
| SCREEN | BH-FDR q ≤ 0.10 | canon §63 |
| EXPORT | Holm p ≤ 0.05 | canon §63 |
| POWER | checked **before** confirmation, against the 82 bp prior | canon §64 |
| DSR trial set | **148 distinct specifications** (`net10`/`net25` are the SAME specification re-priced, not new searches), sr variance 0.0181 | declared |

| | count |
|---|---:|
| Survives Holm | 38 |
| Screen-only (BH) | 18 |
| `CANNOT_DETERMINE_UNDERPOWERED` | 153 |

**Of the 38 Holm survivors, 31 are net-of-cost books with LARGE NEGATIVE means**
— `buy − sell` at h=1 and 25 bps loses −1,239 bp/month with t −40.7. Those are
not discoveries; they are the cost arithmetic being extremely significant. The
positive survivors are:

| cell | mean bp/mo | t | Holm | BH | **DSR** | verdict |
|---|---:|---:|---:|---:|---:|---|
| `daily::gross::buy_minus_sell__h1__ew` | +253.1 | +8.52 | 0.0000 | 0.0000 | **0.9999** | SURVIVES_HOLM |
| `daily::gross::buy_minus_sell__h5__ew` | +186.8 | +7.86 | 0.0000 | 0.0000 | **0.9983** | SURVIVES_HOLM |
| `daily::gross::buy_minus_sell__h1__ew__tradable` | +156.1 | +4.97 | 0.0003 | 0.0000 | 0.5157 | SURVIVES_HOLM |
| `daily::gross::buy_minus_sell__h21__ew` | +75.1 | +4.76 | 0.0008 | 0.0000 | 0.4280 | SURVIVES_HOLM |
| `daily::gross::buy_minus_sell__h63__ew__tradable` | +52.7 | +4.12 | 0.0112 | 0.0004 | 0.1808 | SURVIVES_HOLM |
| `daily::gross::cluster_minus_solo__h5__ew` | +165.4 | +3.91 | 0.0259 | 0.0008 | 0.1115 | SURVIVES_HOLM |
| `daily::gross::buy_minus_sell__h5__ew__tradable` | +100.1 | +3.76 | 0.0442 | 0.0014 | 0.1311 | SURVIVES_HOLM |
| `matched::any_buy__fwd_exc_3m__full` | +63.3 | +3.43 | 0.1470 | 0.0042 | ~0 | SCREEN_ONLY_BH |
| `daily::gross::opp_minus_routine__h63__ew__tradable` | +86.5 | +3.38 | 0.1736 | 0.0049 | ~0 | SCREEN_ONLY_BH |
| `daily::net10::buy_minus_sell__h63__ew__tradable` | **+39.1** | +3.05 | 0.4840 | 0.0122 | ~0 | SCREEN_ONLY_BH |
| `matched::any_buy__fwd_exc_12m__full` | +150.3 | +2.76 | 1.0000 | 0.0270 | 0.1122 | SCREEN_ONLY_BH |

**The two facts that close the lane.**

1. **Everything with a DSR above 0.5 is a gross book that turns over 25-55× a
   month.** `buy_minus_sell__h1__ew` has DSR 0.9999 and loses **−344 bp/month**
   at 10 bps a side. Deflation and costs point at disjoint sets of cells.
2. **Only two net-of-cost cells reach BH q ≤ 0.05 and neither reaches Holm:**
   `buy − sell` h=63 EW tradable (+39.1 bp, t 3.05, Holm 0.484) and
   `opp − routine` h=63 EW tradable (+68.8 bp, t 2.69, Holm 1.000, BH 0.033,
   **DSR 0.008**).
   Both are equal-weighted; their value-weighted twins are +14 bp (t 0.43) and
   −27 bp. **An effect that exists only equal-weighted, only above 63 sessions,
   and only at 10 bps a side is a small-cap loading with a hopeful name.**

**Rebound-month concentration.** The two net survivors take **39% and 43% of
their total excess from their best 5 of 192 months** — better than the two
documented disasters (96.2% and 83.6%) but far from flat. The concentration
statistic REFUSES on series whose total is near zero: a top-5 share of a
long-short that sums to ≈0 produced values of −508 and +11 in the first run, and
the guard now returns `TOTAL_NEAR_ZERO` instead of a number that means nothing.

---

## 7. THE FOUR TRAPS, TESTED

Receipt: `r2_traps.json`.

### 7.1 Is it size? Is it illiquidity? — **yes, mostly**

| group | cells | median cap | median $vol/day | ≥$3m/d | ≥$20m/d | ≥$100m/d |
|---|---:|---:|---:|---:|---:|---:|
| **universe** | 769,293 | $535m | **$3.99m** | 52.9% | 28.1% | 10.6% |
| any buy | 73,213 | $266m | **$1.43m** | 39.0% | 18.5% | 6.8% |
| opportunistic buy | 16,015 | $195m | **$0.65m** | **28.9%** | 12.5% | 4.1% |
| routine buy | 5,063 | $278m | $0.67m | 26.1% | 12.7% | 4.0% |
| cluster buy | 12,155 | $234m | $1.03m | 30.7% | 13.0% | 3.4% |
| any sell | 128,044 | **$1,840m** | **$15.5m** | 74.1% | 45.1% | 19.1% |

Size groups: **71% of opportunistic-buy cells are micro or nano cap**
(micro 53.7%, nano 17.5%) against 50% of the universe; only 3.9% are mega. The
sell side is the mirror image (mega 17.4%, nano 3.5%). **The median opportunistic
buy happens in a name trading $646,644 a day — one fifth of the house's
tradability floor.**

`opp − routine` by size group (EW): micro **+25.9 bp (t 0.99)**, small −30.1
(t −0.78), nano −23.7 (t −0.21), large **6 months of data → CANNOT_DETERMINE**.
The effect, such as it is, is a micro-cap effect and the large-cap cell cannot be
computed at all because there are not enough large-cap routine buyers.

### 7.2 Does it survive at institutional size? — **no, and it cannot be tested**

| floor | universe cells | opp − routine VW: raw | t | months |
|---|---:|---:|---:|---:|
| none | 769,293 | +12.3 | +0.34 | 192 |
| **$3m/day (house)** | 381,353 | **−18.8** | −0.45 | **154** |
| $20m/day | 212,424 | +88.1 | +1.21 | **29** |
| $100m/day | 80,796 | routine leg **empty** | — | — |

**The ladder terminates.** At $20m/day the routine leg exists in only 29 of 192
months; at $100m/day it does not exist at all. This is not a null result — it is
`CANNOT_DETERMINE`. **The CMP long-short is not a testable object at
institutional size on this tape, because institutional-size routine insider
buyers are not a population.** Reporting the +88.1 bp / t 1.21 at $20m/day as a
finding would be reporting 29 hand-picked months.

### 7.3 Is it post-earnings drift wearing a Form 4 badge? — **partly, and in the direction that hurts**

63.2% of universe cells are within one month of an earnings announcement; **78.5%
of buy cells and 78.3% of sell cells are.** Insiders trade in the earnings window
far more than the base rate — the window opens after the print.

| opp − routine, VW | CAPM α | t | months |
|---|---:|---:|---:|
| **near earnings** | **−76.8** | −1.89 | 189 |
| **away from earnings** | **+83.4** | +1.88 | 124 |

The sign flips completely on the earnings calendar, and the "away" cell is graded
on 124 months because there are not always five names. Adding `near_earnings` as
a sixth match key in §5 moves `any_buy` from +14.3 to +14.0 bp — so the *matched*
estimate is not a PEAD artefact. The *portfolio* estimate is dominated by which
side of the earnings calendar the month fell on, which is another way of saying
the portfolio estimate is not measuring insiders.

### 7.4 Is it just the market? — the beta table above

Every long leg carries beta 0.95-1.13. The `no_insider_activity` control leg
carries beta 1.03 and the same raw return. **Beta was printed first in every
table in this document precisely because raw returns of +79 to +128 bp/month
look like results and are the equity premium.**

### 7.5 Is it a small-cap LOADING, or a small-cap POPULATION? — both, in different cells

These are different claims and the receipts separate them
(`r2_daily.json` → `ff6_loadings`, `r2_cmp.json` → `ff6_loadings`).

| cell | beta | **SMB** | t | HML | Mom | CAPM α | **FF6 α** |
|---|---:|---:|---:|---:|---:|---:|---:|
| `opportunistic_buy` h63 EW tradable (long leg) | +1.30 | **+0.831** | **+14.3** | −0.06 | −0.21 | +31.4 | +72.0 |
| `routine_buy` h63 EW tradable (long leg) | +1.18 | **+0.900** | **+7.2** | +0.14 | −0.05 | −38.6 | −9.0 |
| `opp − routine` **EW, monthly** | +0.21 | **+0.227** | **+1.98** | −0.23 | — | −4.3 | +14.5 |
| `opp − routine` **VW, monthly** | +0.30 | +0.043 | +0.22 | −0.03 | — | −24.0 | +5.9 |
| `opp − routine` h63 EW tradable | +0.11 | −0.074 | −0.58 | −0.20 | −0.17 | +73.0 | +82.2 |
| `opp − routine` h63 **VW** tradable | +0.31 | −0.041 | −0.24 | −0.10 | −0.30 | +31.3 | +45.1 |

**The long legs are a small-cap book and nothing else.** SMB **+0.83** and
**+0.90** with t 14.3 and 7.2. Anyone reading `opportunistic_buy`'s +31 bp CAPM
alpha as insider skill is reading 0.83 units of the size factor.

**In the difference the size loading cancels** (SMB −0.074, t −0.58 at h=63), so
the residual +73 bp is not an *SMB loading*. It is still a **small-cap
population** effect, and three independent cuts say so:

1. its **value-weighted twin is +31.3 bp with t 0.95** — weighting the same names
   by capitalisation removes two thirds of it;
2. **matching on size quintile removes it entirely** — §5's opportunistic class
   is **+2.7 bp, t 0.15** at one month and **+16 bp, t 0.18** cumulative at
   twelve;
3. **the size-group table (§7.1) has no large-cap cell at all** — six months of
   data, `CANNOT_DETERMINE` — and the only positive cell is micro (+25.9 bp,
   t 0.99).

**"Not an SMB loading" and "an edge" are not the same statement, and only the
first one is supported.**

### 7.6 The IWM benchmark this lane did NOT run, and why that matters

The cross-lane measurement of 2026-09-08 is that this universe is dominated by a
small-cap factor: two sealed books sharing only 14% of their names still
correlate at **rho 0.719**, and both load more on **IWM (0.75-0.77)** than on
SPY (0.61-0.68). **Every book in this document is benchmarked against the pinned
Fama-French value-weighted market and FF5+Mom, never against IWM.**
`learner.benchmark` carries `spy_total_return` and `qqq` and no IWM id, and both
require network, so no IWM comparison was available offline and **none was
faked**.

What stands in for it, and what does not:

* **SMB is the offline proxy and it is in every table above.** A book with SMB
  +0.83 is a small-cap book whether or not IWM was downloaded.
* **The matched design in §5 is STRONGER than an IWM benchmark for this
  question.** IWM asks "did you beat small caps on average?"; the matched design
  asks "did you beat *the same month, the same sector, the same size quintile,
  the same volatility quintile and the same prior-return quintile*?" — the
  panel's own admissible universe rather than an index. That comparator is
  already the harsher one, and it returns **+2.7 bp, t 0.15**.
* **The gap that remains is real and is named:** the two net-of-cost screen
  survivors (§6) are equal-weighted small-cap books, and **no claim about them
  may be exported until they are graded against IWM.** That is a
  `CANNOT_DETERMINE` on the benchmark, not a pass.

---

## 8. WHAT DID NOT WORK

* **The monthly formation convention.** Forming at month-end throws away up to
  30 days of a signal whose median filing lag is 3 days. It is PIT-safe and
  nearly information-free. §4 exists because §3's null could have been an
  artefact of the calendar; it was not, but that had to be shown, not asserted.
* **`insider_dollar_value` as a weight.** Killed by a filer-error tail with a
  $123bn mean. A market-cap cap fixed it; 265 cells were refused.
* **Clusters as a distinct mechanism.** `cluster − solo` is +19 bp (t 0.74)
  gross and +3 bp net at h=63; matched, `cluster_buy` is −12.8 bp (t −0.50).
  Three insiders on one day is three insiders, not a signal.
* **The opportunistic/routine split as a *ranking*.** Against matched controls
  the opportunistic class is +2.7 bp (t 0.15) at one month and +16 bp (t 0.18)
  cumulative at twelve. The class that *does* show something is the broad
  unclassifiable population — the 78% CMP throws away.
* **Every short-horizon book.** h=1 and h=5 have the largest gross t-statistics
  in the lane and the largest negative net returns. Turnover 54.5×/month.
* **The DSR on the full family.** Including the same specification at two cost
  rates inflated the trial variance to 0.204 and set the expected-max-Sharpe
  hurdle so high that every cell reported DSR 0.000 — a statement about the
  denominator, not about any book. The trial set is now 148 distinct
  specifications and is declared in the receipt.
* **A naive t on overlapping horizons.** `any_buy` at 12m read t 3.55 before the
  Newey-West correction and t 2.76 after. Three of the twelve-month cells crossed
  a conventional threshold on the naive t and none of them is claimed.

---

## 9. WHAT THIS LANE DELIBERATELY DID NOT DO

No book was created. **A surviving family would have become its OWN
`PRODUCT_EXPERIMENT` book, never a weight in `arena_composite`** — nothing
survived, so nothing was created. No order, no seal, no deploy, no promotion, no
push. `event_table_v1` was not touched; the insider events live in their own
parquet as I1 wrote them. **$0.00 of LLM spend.**

**Named future work, in the order it would pay:**

1. **Split the stale filings out.** p99 filing lag is 750 days for buys. A
   "days since transaction ≤ 5" filter is one column and it is the single most
   obvious unmeasured cut.
2. **Trade size relative to the insider's own stake**, not dollars. The median
   buy moves the buyer's position 0.96%; the p90 moves it 39.6%. That ratio is on
   disk (`shares_owned_following`, parsed quarters) and was measured here but
   never used as a signal.
3. **Officer-vs-director-vs-10%-holder.** 52.9% of buy rows are 10% holders,
   whose information is different in kind. Not split here.
4. **The 2025-26 slice needs a CRSP vintage refresh** or the window stays
   2009-2024.
5. **The `near_earnings` interaction** — the sign of the portfolio estimate flips
   on it, which is either a confound to remove or a conditioning variable to use.

---

## 10. TESTS AND HYGIENE

**Baseline recorded BEFORE any work in this lane:**

```
AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow" -q --timeout=300
1 failed, 7409 passed, 20 skipped, 124 deselected in 771s
FAILED backend/tests/test_signal_reachability.py::test_every_orphan_is_classified
```

The single failure is **pre-existing and not this lane's**: nine
`backend.strategy.*` modules (`execution`, `ladder`, `leak`, `manifold`,
`protections`, `vendor`, `vendor.breakeven`, `vendor.factor_costs`,
`vendor.impact`) are unreachable and unclassified — another agent's
strategy-interface lane, mid-flight. This lane adds **one file under `scripts/`**
and no `backend/services` module, so it creates no orphan and needs no
`CLASSIFIED` entry.

**After this lane's changes** (one new script, no `backend/services` module):

```
AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_signal_reachability.py     backend/tests/test_guard_missing_input_contract.py     backend/tests/test_benchmark_canonical.py -q --timeout=300
99 passed in 36.41s
```

The reachability guard is green on re-run — the `backend.strategy.*` orphans were
enrolled by their own lane while this one was computing. **Trust the targeted
re-run over a 13-minute full-suite run across a tree six agents are writing to**;
that run measures a moving average of the tree, not the tree.

**Process hygiene.** One long-running job of this lane was stopped because its
first implementation of the matching would not have finished (1.2M `groupby.apply`
callbacks). It was killed **by PID 133260, read from
`Get-CimInstance Win32_Process` and written down first** — never by image name.
Six other agents' python processes were running in the same tree at the time and
none was touched (CLAUDE.md session rule 6).

---

## 11. THE ENTRY CONVENTION, AUDITED WITH THE SAME SUSPICION

The event-family lane measured today that **entry convention carried 92.5% of a
headline PEAD number** — +5.54% at one session on a day-0 close entry against
+0.41% PIT-safe. That is the correct suspicion to bring here, because §4's
largest gross number (+253 bp/month, t 8.52) is a one-session book.

**What this lane's convention actually is, in code:**

```
entry_si = searchsorted(sessions, filing_date, side="right")   # STRICTLY after
r(leg 0) = ret_entry = close(entry_si) / OPEN(entry_si) - 1    # open-to-close
r(leg k) = ret(entry_si + k)                                   # close-to-close
```

* `side="right"` means a filing dated *d* enters on the **first session strictly
  after *d***. A filing on a Friday enters Monday.
* The entry session is priced **open-to-close**, so the overnight move between
  the filing day's close and the entry day's open is **never earned**. That gap
  is exactly where a Form 4's reaction lands, and this lane forgoes it.
* **No variant in this lane buys on the filing day**, at its close or at any
  other price. There is no day-0 arm to be tempted by, and none was computed.
  I1's `next_tradable_session_bound()` is the rule and it was not relaxed.

**The one leak, disclosed and bounded.** When `openprc` is missing the entry
session falls back to that session's CRSP close-to-close return, which begins at
the **filing day's close** and therefore includes the overnight reaction. That is
a genuine, if small, look-ahead in the optimistic direction. **It affects 2.74%
of daily rows** (`r2_daily.json → daily_provenance.open_missing_share`) and is
concentrated in the least liquid names — the same names the execution floor
already removes. It is not corrected here; it is counted, and it is a named
defect rather than a footnote.

**Why the h=1 result is still not a PEAD-shaped artefact, and still not a book.**
The +253 bp at h=1 is earned entirely inside sessions that begin at an open the
market has already had a chance to reprice. It is large because open-to-close
returns on micro-caps mean-revert, not because the filing day was bought — and
whatever its source, it turns over 54.5× a month and loses **−394 bp/month net**
at the house's own 10 bps a side. **A convention artefact and a cost artefact
point at the same cell, and it is discarded on both counts.**

**What would change the answer, and is not claimed:** if a true
`acceptanceDateTime` were pulled per accession (one HTTP request per issuer,
`data.sec.gov/submissions/CIK##########.json`, as I1 documents), filings accepted
before 16:00 ET could legitimately enter the **same** session's close rather than
the next open. That is a *later* entry than day-0 close but *earlier* than this
lane's, and it is the single change most likely to move these numbers. It was
not done and nothing here assumes it.

---

## 12. FILES

| path | what |
|---|---|
| `scripts/r2_insider_lab.py` | the seven stages (new) |
| `backend/data/optimus/insider_lab/r2_base_rates.json` | §2.1-2.4 |
| `backend/data/optimus/insider_lab/r2_base_rates_holdings.json` | §2.3 percent-of-stake |
| `backend/data/optimus/insider_lab/r2_spine{.parquet,_receipt.json}` | §2.5 the panel |
| `backend/data/optimus/insider_lab/r2_cmp.json` | §3 the CMP replication |
| `backend/data/optimus/insider_lab/r2_daily{.json,_series.parquet,_turnover.parquet}` | §4 daily convention + measured turnover |
| `backend/data/optimus/insider_lab/r2_matched{.json,_series.parquet}` | §5 matched controls + leak canary |
| `backend/data/optimus/insider_lab/r2_traps.json` | §7 the four traps |
| `backend/data/optimus/insider_lab/r2_adjudication.json` | §6 the 236-cell family |
| `backend/data/optimus/insider_lab/r2_daily.json` → `ff6_loadings` | §7.5 the SMB loadings |

Every headline number in this document is in one of those receipts. None of them
lives in prose only.
