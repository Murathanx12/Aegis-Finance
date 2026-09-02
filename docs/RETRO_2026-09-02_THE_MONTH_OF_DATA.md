# RETRO 2026-09-02 — The month of data

**Licence:** `PRODUCT_EXPERIMENT` (retrospective; no significance gate claimed)
**Numbers receipt:** `backend/data/optimus/tracker_backtest/month_retro_20260902.json`
**Question asked (Murat, 2026-09-02):** *"run a backtest with the data we acquired over the past
month — how we should have used it, were there any underlying causes — expected vs reality, and
improve with every run."*

---

## TL;DR — fifteen lines

1. **RESULT IMPROVEMENT: MEASURABLE BUT UNRESOLVED.** Two forward sessions exist. On one the live
   book beat the market by +1.29pp; on the next it lost 5.76pp. n=2 decides nothing.
2. **The month acquired ~6.0 GB across 31 dataset families. Only 12,233 rows of it are
   PIT-clean forward observations** — four tracker day-files, `state/tracker/2026-08-3*.jsonl`.
   Everything else is substrate or hindsight.
3. **The tracker starts 2026-08-30, not 2026-08-27.** The brief's premise was wrong, and 08-30 was
   a Sunday whose close column duplicates 08-31's (2,997/3,059 identical). Two tradable sessions.
4. **The single biggest loss came from a name our own rule REFUSED.** RZLV, −17.30% on 2026-09-01,
   `claims: false`, rank 576 of 766, failed `b_rating` (4.083 vs 4.1) and `e_drawdown`. hack4 held
   it at 10% anyway.
5. **On 2026-09-02 that disagreement is total: 25 of 30 holdings across hack3+hack6 are names the
   per-name generator declined.** Two selectors, one book, no recorded adjudication.
6. **RZLV was 89.4% company-specific** (−15.47pp of −17.30pp, `state/decomposition/2026-09-01.json`).
   It is the *only* holding that day that was. The other twelve were leverage: **mean market beta
   2.10** into a −0.687% SPY.
7. **BAND_PRIOR v2 is the month's best decision, and it is measurable.** Run from the first tracker
   day it widens the admitted set 5 → 55–58 names (11×) and cuts overnight turnover 33.3% → 8.5%.
8. **v2 beat v1 on both graded sessions** (+1.04pp, +2.53pp) and v1 had **zero** admitted names above
   a $25m/day liquidity floor — v1's opportunity set was structurally unbuyable at size.
9. **Neither prior would have stopped RZLV.** It sat in the 3–5 band under both. The band prior is
   an opportunity-set fix, not a loss-prevention fix, and must stop being sold as one.
10. **149 of 150 extreme movers over 08-25…08-28 had no engine view (99.3%).** The one exception
    pointed the wrong way. `candidates_right_way = 0` on all four days.
11. **127 of 127 of those names are in today's tracker. Zero are outside it.** This is a **100%
    admission failure and a 0% observation failure** — among names the tracker carries.
12. **The attention watchlist answers a different question:** it re-flags 5 of the 127 (3.9%). Its
    real contribution is **107 names the tracker never observes at all** — GPRO among them — and
    that contribution is entirely unmeasured, because the ownership data was backfilled today.
13. **The "80k PIT news corpus" is 230,661 rows and it is 81% SEC filings.** Only 18.8% of August
    rows are wire news. 8,523 rows are future-dated calendar entries, not news.
14. **`state/decision_outcomes/` is EMPTY locally.** The sealed-intent → fill → graded-return
    write-back lives on the Railway volume. We cannot grade our own execution from this machine.
15. **The 09-02 seal was NOT missed.** It exists, sealed 07:05 UTC, sha `6e69c0af`, 806 considered,
    the first book built under v2. The open item from session 33 closed this morning.

---

## 1. Inventory — what the month actually put on disk

PIT-clean means the artefact could only have been built from information available at its stamped
time. HINDSIGHT means it was built afterwards: valid for learning, invalid as a signal input
without an as-of join. The distinction is the whole reason this table exists.

| Dataset | Files | Size | Rows | Span | PIT status |
|---|---|---|---|---|---|
| Tracker whole-market day files (`state/tracker/2026-*.jsonl`) | 4 | 9.25 MB | **12,233** | 2026-08-30 … 09-02 | **PIT-CLEAN** — observed pre-open; `close` = *prior* session's close |
| Tracker transitions (`state/tracker/transitions.jsonl`) | 1 | 9.91 MB | 27,537 | through 09-02 | PIT-CLEAN, append-only |
| Tracker `latest.json` / `profiles.json` | 2 | 1.58 MB | — | current only | **HINDSIGHT** — overwritten in place, not replayable |
| Sealed prediction books (`state/predictions/2026-*.json`) | 9 | 10.01 MB | 5,740 preds | 4 distinct days | **PIT-CLEAN + TAMPER-EVIDENT** (`content_sha256`) |
| Seal ledger (`state/predictions/seals.jsonl`) | 1 | — | 9 | 08-30 … 09-02 | PIT-CLEAN — incl. **6 reseals** of 08-30/08-31 |
| Published seed books (`docs/seed/predictions/`) | 4 | 4.64 MB | — | 08-30 … 09-02 | PIT-CLEAN mirror — the artery |
| Daily autopsies (`state/autopsy/2026-08-2*.json`) | 4 | 0.19 MB | 150 movers | 08-25 … 08-28 | **HINDSIGHT by construction** |
| Discovery autopsies (`state/autopsy/discovery_*.json`) | **1** | 427 B | **1 mover** | 08-28 only | HINDSIGHT — *ran once, ever* |
| Return decomposition (`state/decomposition/`) | 2 | 0.02 MB | 42 names | 08-31, 09-01 | HINDSIGHT — 120-session fit, today excluded |
| `state/decision_outcomes/` | **0** | 0 | **0** | — | **NOT OBSERVABLE LOCALLY** — lives on Railway `/app/state` |
| EDGAR ownership (`state/research/ownership/2026-08-*.jsonl`) | 6 | 2.06 MB | 2,509 | filed 08-13 … 08-20 | PIT-clean *by filing date*, **backfilled 2026-09-02** |
| Attention watchlist | 1 | 0.06 MB | 200 (of 1,585) | built 09-02 | DERIVED from backfill — never run prospectively |
| News/filing corpus (`state/corpus/observations/*.jsonl`) | 21 | 152.14 MB | **230,661** | 2025-08 … 2027-02 | PIT-CLEAN |
| Corpus features / relevance / digests | 346 | 146.67 MB | — | — | PIT-clean inputs, LLM labels post-hoc |
| Era replay (`state/era_replay/`) | 11 | 2.85 MB | 5 decision streams | built 08-30 | PIT-CLEAN by construction (anonymised frozen windows) |
| Decisions ledger (`state/decisions.jsonl`) | 1 | 17.81 MB | 9,457 | — | PIT-CLEAN, append-only |
| Fills ledger (`state/fills.jsonl`) | 1 | 2.19 MB | 1,378 | — | PIT-CLEAN, append-only |
| Counterfactual ledger (`state/counterfactual.jsonl`) | 1 | **1,118.87 MB** | **1,062,527** | — | PIT inputs, **HINDSIGHT marks** |
| Protective stops / belief series / spend ledgers | 6 | 7.55 MB | 21,219 | — | PIT-CLEAN, append-only |
| `tracker_backtest` receipts (finance) | 8 | 0.22 MB | — | 2013-2024 panels | **HINDSIGHT** — these are the *priors* |
| WRDS panels (finance) | 130 | **4,470 MB** | — | 1990-2024 | HINDSIGHT-capable; PIT only via `join_pit_series` |
| `analyst_target_grades.parquet` (new this month) | 1 | 43.19 MB | 1.33 m targets | built 09-01 | HINDSIGHT panel |
| Holder provenance (new this month) | 232 | **1,378 MB** | — | built 09-02 | HINDSIGHT — 13F is 45 days late *by construction* |

### Three things the inventory says that nobody wrote down

**The corpus is a filings corpus.** August 2026: 27,778 rows — 14,677 `filing`, 7,841 `corporate`,
**5,236 `news` (18.8%)**, 24 `earnings`. By source, 22,518 of 27,778 (81%) are `sec_edgar`. Every
claim of the form "our news coverage shows X" is a claim about EDGAR unless it filters
`kind == "news"`. (`state/corpus/observations/2026-08.jsonl`)

**8,523 corpus rows are dated in the future** (2026-09 through 2027-02). Those are forward calendar
entries — dated catalysts — not news. Two clocks, two bounds; conflating them is
[[feedback-two-clocks-need-two-bounds]] again.

**The ratio of hindsight to forward evidence is roughly 490,000 : 1 by bytes.** 5.9 GB of
substrate and priors; 9.25 MB of forward observation. That is not a criticism of the substrate —
it is the reason every conclusion in §2 carries an n=2 warning.

---

## 2. Expected vs reality — the decisions we actually took

### Method, and why there are only two gradeable days

The tracker day-file stamped `D` is observed pre-open on `D` and its `close` column is the **prior**
session's close. So `close(file D+1) / close(file D) − 1` is the return of **session D** — exactly
the forward return a book sealed on the morning of `D` was betting on.

2026-08-30 was a **Sunday**. Its file and 08-31's carry the same close (2,997 of 3,059 identical),
so the 08-30 and 08-31 books share one first tradable session. That leaves:

| Book sealed | Graded over | Market context (3,059-name universe) |
|---|---|---|
| 2026-08-30 (0 claims) + 2026-08-31 | Mon 2026-08-31 session | EW **−0.51%**, cap-wtd **+1.16%**, median −0.60% |
| 2026-09-01 | Tue 2026-09-01 session | EW **−1.20%**, cap-wtd −0.77%, median −1.08% |
| 2026-09-02 (806 considered, 11 claims) | **ungraded — no forward session yet** | — |

Note the Aug-31 split: cap-weighted **+1.16%** against equal-weighted **−0.51%**. That was a
mega-cap day and a small-cap red day, which is the tape our books trade into.

### The scoreboard

| Session | Book | n | Realised (EW) | Universe EW | **Excess** | Hit rate | Exp (pro-rata 1d) |
|---|---|---|---|---|---|---|---|
| 2026-08-31 | hack4 | 5 | **+0.78%** | −0.51% | **+1.29pp** | 3/5 | *none shipped* |
| 2026-08-31 | murat_rule claims | 10 | **+0.80%** | −0.51% | **+1.31pp** | 7/10 | — |
| 2026-09-01 | hack3 | 9 | −1.55% | −1.20% | −0.35pp | 4/9 | +0.058% |
| 2026-09-01 | hack4 | 5 | **−6.96%** | −1.20% | **−5.76pp** | **0/5** | +0.026% |
| 2026-09-01 | murat_rule claims | 11 | −3.97% | −1.20% | −2.77pp | **0/11** | — |

**The books are directionally live and completely unresolved.** One session up big, one session
down bigger. Nothing here is a result.

### Miss #1 — the biggest loss was a name the rule refused

`RZLV`, 2026-09-01, **−17.30%**, held by hack4 at 10% notional.

In the same sealed file, `state/predictions/2026-09-01.json`, RZLV's own row reads:

```
"claims": false,
"failed_clauses": ["b_rating", "e_drawdown"],
"clause_inputs": {"rating_counts_mean": 4.083, "drawdown_from_60d_high": -0.1373},
"rank": 576,
"rank_basis": "NOT CLAIMING: ranked least-bad ... an ordering of names the rule declined"
```

It failed `b_rating` by **0.017** (4.083 against a 4.1 bar) and `e_drawdown` by 1.3pp. hack4 does not
read `claims` — it ranks on `upside_x_consensus` — so the name the generator placed 576th of 766
went in at full weight. The same disagreement appears on 08-31, where RZLV was again the only
rule-declined hack4 holding and again the worst (−2.69% against +1.65% for the four claimed names).

**Today this is not an edge case, it is the norm.** In the 2026-09-02 seal:

| Book | Held | Rule **declined** | Rule **claimed** |
|---|---|---|---|
| hack3 | 10 | **10** | 0 |
| hack4 | 5 | 0 | 5 |
| hack6 | 15 | **15** | 0 |

25 of 30 hack3+hack6 holdings are names the per-name generator explicitly declined. This is a
*known* design choice — `34f08ca`, "the runner expresses a sealed weight, it does not re-adjudicate
the seal; model dissent is recorded, not enforced." The retro's job is not to overturn it but to
**price** it, and right now nobody is pricing it.

**And the honest counter-evidence:** on 2026-09-01 hack3's six rule-declined names averaged
**−0.55%** while its three rule-claimed names averaged **−3.54%**. On that day the rule's refusals
were *better* than its claims. Two sessions, two opposite answers. That is exactly what an
experiment is for, and it is Experiment 1 below.

### Miss #2 — twelve of thirteen losses were leverage, not stock picking

`state/decomposition/2026-09-01.json` splits each held name's day into market + sector + company on
a trailing 120-session fit with today excluded.

| Name | Return | Market leg | Sector leg | **Company leg** | β(market) |
|---|---|---|---|---|---|
| RZLV | −17.30% | −1.13% | −0.71% | **−15.47%** | 1.64 |
| ASPI | −5.97% | **−2.93%** | −0.18% | −2.86% | **4.27** |
| ORCL | −5.23% | −1.04% | −0.74% | −3.45% | 1.52 |
| ALMU | −4.89% | −1.02% | −1.60% | −2.26% | 1.49 |
| NB | −4.53% | −1.87% | −1.60% | −1.07% | **2.72** |

- **SPY was −0.687%. The book was −6.96%.** Mean β(market) across the 13 held names: **2.10**;
  median 1.75; **6 of 13 above 2.0**; max 4.27 (ASPI).
- `mean_market_share_of_move = 1.49` — on average the market leg explained **more than the whole
  move**. That is the signature of a levered long book on a red tape, not of bad selection.
- **RZLV is the one genuine stock-specific loss**: 89.4% company component, its own print.

The reading: on 2026-09-01 we lost 5.76pp to the universe, and roughly one name of it was a
company event we could have had a view on. The rest we bought by holding β 2.1 with no β budget.
Session 33's handoff already recorded the mechanism live — *"hack3 and hack4 had stops fire on the
red macro open (positions 4→2 and 3→1)"* — a stop keyed on total return liquidates a market move
at the bottom of it.

### Miss #3 — a sealed book with no expectation attached

The 2026-08-31 seal shipped hack4's five holdings with `exp_return: null` and `downside_5pct: null`.
That book is **ungradeable against its own expectation by construction**. It was fixed by 09-01.
Worth naming because "expected vs reality" silently becomes "reality" when the expectation column
is absent, and nothing failed.

### On calibration, stated carefully

Sealed `exp_return` is a **21-session** expectation of roughly +0.17% to +1.7%; pro-rata that is
+0.008% to +0.08% *per session*. Realised single-session moves were 40× to 200× that in both
directions. So the honest verdict is not "the expectations were wrong" — it is that **a 21-day
claim cannot be graded on a 1-day outcome**, and the fact that 1-day outcomes are the only forward
evidence that exists is itself this month's central finding. The first real grade of the 09-01 book
lands 2026-09-30.

### Book risk, for the record

Per the session-start protocol, worst case in dollars-equivalent for the largest admissible book:

| Seal | Book | n | Gross | Worst case if every name hits its own 5% downside |
|---|---|---|---|---|
| 09-01 | hack3 / hack4 / hack6 | 9 / 5 / 0 | 74.7% / 50.0% / 0% | −17.76% / −18.03% / — |
| 09-02 | hack3 / hack4 / hack6 | 10 / 5 / 15 | 83.0% / 50.0% / 90.0% | −14.16% / −14.98% / −13.23% |

Separate accounts, so these do not sum. **Every book is under 100% gross on both days** — the
300%-gross / −24%-worst-case failure of 2026-08-28 has not recurred.

---

## 3. How we should have used the month's data

Three replays. Each is small, each is honest about what it cannot show.

### 3a. If BAND_PRIOR v2 had been live from the first tracker day

`BAND_PRIOR` v2 (`alpha/murat_rule.py`, terminal `f83bd14`, receipt `EXP-RETURN-XS-1` =
`backend/data/optimus/tracker_backtest/exp_return_cross_section.json`) bands the **whole** ratio
line; v1 (`UPSIDE-BAND-DECON-1`, `6aeeeef`) banded only ratio ≥ 3. Both gate on `min_price 2.0`;
v2 adds `min_coverage 2`.

Method: re-derive the clause inputs from each tracker day-file and apply both overlays. The
re-derivation does not reproduce the seal's feature builder exactly, **so read the v1-vs-v2 delta,
not the absolute counts.**

| Day | Names with a **priced opinion** | | Rule fires **AND** prior positive | |
|---|---|---|---|---|
| | **v1** | **v2** | **v1** | **v2** |
| 2026-08-30 | 44 | **2,838** | 5 | **55** |
| 2026-08-31 | 44 | **2,835** | 5 | **55** |
| 2026-09-01 | 42 | **2,837** | 5 | **58** |
| 2026-09-02 | 46 | **2,834** | 6 | **56** |

**v1 had an opinion on 1.4% of the market. v2 has one on 92.7%.** The tradable opportunity set is
**11× wider on every single day.**

Overnight turnover of the admitted set:

| Transition | v1 turnover | v2 turnover |
|---|---|---|
| 08-30 → 08-31 | 0.0% | 0.0% |
| 08-31 → 09-01 | **33.3%** (1 of 5 dropped) | **8.5%** |
| 09-01 → 09-02 | 16.7% | 13.1% |

v2 does the thing it was built to do: *admission stops flipping overnight.* And **zero sign flips**
in 12,233 name-days — v2 never reverses v1, it only extends it.

**Forward returns of each admitted set (n=2 sessions):**

| Session | v1 (n=5) | v2 (n=55–58) | v2 with mdv ≥ $25m | Universe EW |
|---|---|---|---|---|
| 2026-08-31 | −0.93% | **+0.11%** | **+0.81%** (n=21, hit 76%) | −0.51% |
| 2026-09-01 | −3.79% | **−1.26%** | −1.77% (n=24) | −1.20% |

v2 beat v1 on **both** sessions (+1.04pp, +2.53pp). And the structural point:

> **v1 had ZERO admitted names above a $25m/day liquidity floor on either session.** Its
> five-name opportunity set was not merely narrow, it was unbuyable at size.

**The counter-evidence, stated plainly.** `RZLV` sat in the `ratio 3..5` band under **both**
priors (ratio 3.633, close $2.89, coverage 5). *Neither version of the band prior would have
prevented the month's largest loss.* The band prior is an **opportunity-set** fix. It must stop
being described as a risk fix.

**And the in-sample warning.** `exp_return_cross_section.json` says it itself: *"band thresholds
were chosen from receipts measured on this panel; Q2 is a decomposition, not out-of-sample
validation."* The two sessions above are the only out-of-sample evidence v2 has.

### 3b. The discovery misses — observation or admission?

`state/autopsy/2026-08-{25,26,27,28}.json`, 150 extreme movers, 127 distinct symbols.

- **149 of 150 (99.3%) have `engine.candidate = null`** — no view was formed.
- The one exception, `STRT` on 08-28 (+6.76%), the engine said **DOWN**.
  `candidates_right_way = 0` on all four days.
- The LLM's own `knowable_before` verdict on the 150: **yes 10 (6.7%)**, partly 49, **no 91 (60.7%)**.
  `precursor == "none"` on 91 of 150.

Now the question the brief asked:

| | count |
|---|---|
| No-view movers **in** today's tracker universe (observed, not admitted) | **127 / 127 (100%)** |
| No-view movers **not** in any tracker day (never observed) | **0** |

> **100% admission failure. 0% observation failure** — among the names the tracker carries.
> Caveat, stated because it matters: the tracker did not exist on 08-25…08-28. This is
> *"would be observed today"*, not *"was observed then."*

Largest of them, all in the tracker now: SMJF −87.03%, VISN +60.32%, ANF +35.63%, DKS −30.68%,
OKTA +28.63%, TENX +25.41%, CRM +22.58%, RZLV +21.81%, CRWD +20.50%.

**The discovery autopsy ran exactly once, ever.** `discovery_2026-08-28.json` is 427 bytes and
contains one row: `{"NOT_GENERATED": 1}`, VISN, −45.06%, 2 pre-open headlines, has options. The
instrument built to count the Microns we never looked at emitted one row on one day and was never
run again — its `--min-price 3.0` filtered a top-50 screener down to a single row and nothing
flagged that. This is the house failure mode: green, silent, doing nothing.

> **UNRECONCILED — do not use either file as evidence until this is settled.**
> `discovery_2026-08-28.json` records VISN as a **loser at −45.06%**.
> `autopsy/2026-08-28.json` records the same symbol, the same day, as a **win at +60.32%**.
> Both cite the same headline. One is wrong and no check caught it.

**Would the attention watchlist have observed any of them?**
(`state/research/ownership/attention_watchlist.json`, built 2026-09-02.)

- 200 symbols, **capped from 1,585** — 87.4% of the candidate set discarded by the cap.
- 165 of 200 are passive `SC 13G`/`13G/A`; only 35 are 13D.
- Declared `window_days: 45`; **actual filing coverage is 6 days, 08-13 → 08-20**, and 88% of the
  2,509 filings come from just two of them. `n_filings_out_of_window: 0` is therefore **a gate that
  cannot fire** — nothing outside the collected range was ever fetched. 129 filings with an
  unresolved subject were dropped.
- **Of the 127 no-view movers it would have flagged 5 (3.9%):** TENX +25.41%, CAPR +21.91%,
  RBRK −13.05%, BETR +9.11%, RXST +6.66%.

So on the question as asked, the answer is **barely**. But that is the wrong question:

> **107 of the watchlist's 200 names are not in the tracker universe at all.** `GPRO` is one of
> them — in the watchlist, absent from all 3,056 tracker rows. The watchlist's value is a
> **107-name observation extension**, not a re-flagging of names we already carry. That value is
> **entirely unmeasured**, because the ownership data was backfilled this morning and has never
> once run prospectively.

Only 38 of the 200 reach the 09-02 seal universe of 806.

### 3c. Refusals, counterfactuals and execution

**First, the arithmetic trap.** Two of the four big ledgers are **re-mark loops, not event streams**:

| File | Rows | Distinct objects | Duplication | Naive sum | De-duplicated |
|---|---|---|---|---|---|
| `state/counterfactual.jsonl` | 1,062,527 | **10,083** decision_ids | **105.4×** | −$292,924,821 | **−$2,181,104** |
| `state/fills.jsonl` | 1,378 | **22** order ids | **62.6×** | −$35,222 | **−$757.20** |

Any figure quoted off row counts is wrong by two orders of magnitude. `scripts/refusal_regret.py`
de-duplicates correctly; ad-hoc analysis does not.

**What the refusals cost and saved** (last mark per decision, 6,667 refused decisions, sign
convention from `alpha/counterfactual.py`: *saved* = refused worlds that lost, *cost* = refused
worlds that won):

| Guard class | n | graded | Saved | Cost | **Net** |
|---|---|---|---|---|---|
| TOURNAMENT (`book_limits`) | 3,958 | 2,305 | $4,826,747 | $2,592,699 | **+$2,234,047** |
| EMPIRICAL (`mdm_floor`) | 2,676 | 2,458 | $1,842,628 | $2,688,877 | **−$846,249** |
| UNCLASSIFIED | 33 | 27 | $41,292 | $112,254 | −$70,962 |
| **Total** | **6,667** | **4,790** | **$6,710,667** | **$5,393,830** | **+$1,316,837** |

Read literally: the guards paid for themselves. Four reasons not to read it literally.

1. **The result is one ticker.** PANW alone is **−$1,182,417**. Net without it: **+$2,499,254**.
   And PANW's own refusal reasons say its round-trip spread is *26–37% of max loss*.
2. **45% of decisions are ungradeable and are counted anyway.** `mark_source` is `chain` on 54.6%
   of decisions; `unmarkable` on 22.0%; `null` (the hold-cash world) on 23.4%. Both non-chain
   classes carry `pnl_usd = 0.0` **and still count toward `n` and `win%`**. The `daily_latch` guard
   reports **312 wins out of 312 on $0.00 saved and $0.00 cost** — a 100% win rate that measures
   nothing. Every `already positioned`, `none cleared the gates` and `daily latch` family is 0/N graded.
3. **The one guard with near-complete grading is the one losing money.** `mdm_floor`, 2,458 of
   2,676 graded, **−$846,249 (−$344/decision)**. The convex-risk ceiling family alone is
   −$918,930 over 1,006 decisions.
4. **The sample is four calendar days and seventeen symbols** (2026-08-25 → 08-28). Canon §58:
   effective n counts date blocks. This is n≈4.

**The spread caveat, discharged rather than waved.** The brief warned that fresh marks are spread,
not skill. Measured: exits are marked at the **crossed** side (`alpha/counterfactual.py:147` —
longs leave at the bid, shorts are bought back at the ask), and decision→final-mark elapsed on the
4,790 chain-marked refusals is **min 21.5h, median 57.1h, 0% under 4h**. These are real 1–3 day
marks, and the universe is 17 mega-caps/ETFs ($2.06bn–$40.1bn per day), not thin names. *The
caveat does not bite here.* What does bite is that the **option chains** are wide: median quoted
round-trip **171.8 bps**, p75 **405.6 bps**.

**Execution quality — quote the number.**

- **22 of 22 orders filled at or inside their limit.** Total slippage vs limit: **−$757.20**, which
  is **3.2%** of the −$23,306 realised loss it sits inside. Against the standing threshold of
  *"act if fill slippage exceeds ~15% of expected edge"*, this is a fifth of the trigger.
- Against the decision mid, per leg (n=44): median **+18.1 bps**, mean +70.0; 23 adverse / 20
  favourable. **Slippage / half-spread: median 0.20×.**
- Put-call parity held to **7 bps (NVDA) and 2 bps (TSLA)** on 3.4-second-old quotes
  (`state/parity_probe_open.json`) — the chain is trustworthy at the moment of decision.
- One artefact to discard: a TSLA row reporting $4,005 slippage, caused by `decision_ask = 0` on a
  **15.1-hour stale** quote. 3 of 1,378 rows; the final audit corrects it to $0.

> **Execution was never the story.** The spread is the cost, not the fill.

**What the decisions ledger says about the shape of the month** (`state/decisions.jsonl`, 9,457
lines, **9,455 parsed, 2 torn** — concurrent appends without locking on a hash-chained file):

| | 08-25 | 08-26 | 08-27 | 08-28 | 08-29 | 08-30 | 08-31 | 09-01 | 09-02 | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|
| refused | 4,061 | 3,103 | 143 | 286 | 6 | 0 | 99 | 0 | 0 | **7,698** |
| submitted | **22** | 0 | **1** | 0 | 0 | 0 | 0 | 0 | 0 | **23** |
| closed / close_failed | 0/0 | 65/56 | 82/66 | 16/16 | 26/26 | 25/25 | 31/31 | 6/6 | 6/6 | 257/232 |

**Refusal rate 81.4%. Twenty-three submissions in nine days, all on two dates.** From 08-29 the
ledger is almost entirely close/close_failed *pairs* — 230 of the 232 failures are
`protective stop cancel failed ... HTTP 500: venue`. That is a venue error wearing a decision's
clothes, and it has been printing daily for five days.

**The arbiter has produced zero graded observations.** `state/arbiter_last_*.txt` are 10-byte epoch
markers, not ledgers. Its 213 real rows live in `decisions.jsonl` (184 hold / 17 close / 12 hedge)
and **all 213 are `unmarkable`**.

**Era replay** (`state/era_replay/grade.json`, 150 decisions/arm over **11 monthly dates**):

| Arm | Terminal wealth | t | Calibration vs climatology |
|---|---|---|---|
| `real` | 1.670 | 2.333 | **−0.0084** |
| `real_anon` | **1.756** | 2.074 | −0.0105 |
| `fantasy` | 1.567 | 2.116 | −0.0088 |
| `numbers_only` | **0.924** | −0.156 | −0.0014 |
| null basket | 1.149 | 0.971 | — |

Prose beats numbers by **+0.64** of terminal wealth, and `numbers_only` is the only arm that loses
money and the only one below the null. But **real prose beats *fabricated* prose by only +0.10**,
and anonymising the true entities **improved** the result (1.756 vs 1.670). The gain is narrative
*structure*, not the events having happened. Calibration is negative in **all four** arms — the
model orders better than it prices — it is a ridge at k=5 that collapses at k=10 (1.076, t 0.54),
and the shuffled null is flagged informative in every arm, returning 1.423 for `real` against the
arm's 1.670. Most of `real`'s wealth survives shuffling.

---

## 4. Underlying causes — the month's failure taxonomy

Seven classes, with counts. "Changed" means a commit exists; "open" means it does not.

| # | Class | Count / evidence | Already changed | Still open |
|---|---|---|---|---|
| 1 | **Observation misses** (GPRO class) | **0 of 127** no-view movers were unobservable; **107 of 200** watchlist names sit outside the 3,056-name tracker | tracker widened to 3,059; EDGAR 13D/13G watcher + attention watchlist (`9aec2ad`, `69bba25`) | watchlist **never run prospectively**; 200-cap discards **87.4%** of 1,585 candidates; `n_filings_out_of_window: 0` is a gate that cannot fire |
| 2 | **Admission-gate errors** (coherence-floor era) | `exp_return` non-positive on **722 of 766** (94.3%); hack6 sealed **empty with 766 reasons**; **5 of 3,059** names admitted under v1 | BAND_PRIOR v2 (`f83bd14`): priced opinions 44 → ~2,836; admitted 5 → 55–58; hack3 `rank_distinct_values` **17 → 414**, hack6 **0 → 185** | v2 thresholds are **in-sample**; the refusal ledger that would price the old floor is 4 date-blocks deep |
| 3 | **Selector disagreement** (found by this retro) | RZLV **−17.30%** held at 10% while `claims: false`, rank **576 of 766**, failed `b_rating` by **0.017**; **25 of 30** hack3+hack6 holdings on 09-02 are rule-declined | deliberate — `34f08ca`, "dissent recorded, not enforced" | **never priced.** 2 sessions give 2 opposite answers (RZLV −17.3% for the rule; hack3 declined −0.55% vs claimed −3.54% against it) |
| 4 | **Timing / horizon contamination** (beta stop-outs) | mean β **2.10**, median 1.75, **6 of 13 above 2.0**, max 4.27, into a **−0.687%** SPY; market leg explained **1.49×** the whole move; stops fired on the red open (4→2, 3→1) | 09:30–09:45 no-share-entry guard; `move_decomposition.py` built (`b1254e0`, `4a96dd5`) | **stops still key on total return, not the company component.** No β budget exists at all |
| 5 | **Execution issues** — *few, and quote the rate* | **22 of 22** filled at or inside limit; slippage **−$757.20 = 3.2%** of a −$23,306 loss; median **0.20×** half-spread; parity holds to **2–7 bps** | CLS-on-paper banned; phantom `$0` decision quote fixed (`539569d`) | option round-trip spread median **171.8 bps** (p75 405.6) is the real cost and is unbudgeted; 230 `HTTP 500: venue` stop-cancel failures in 5 days |
| 6 | **Delivery / artery** | books never reached the runner; the obvious repair was also wrong; published seed stale (302/1 vs 749/10) | artery `26faa7b`; seal carries holdings in `content_sha256`; **the 09-02 seal EXISTS** — 07:05 UTC, sha `6e69c0af`, 806 considered, first book under v2. *The brief's "seal missing 09-02" is closed.* | P0.5 sealed symbols not yet in `run_pass`'s universe; P0.6 sizing reads `risk_fraction`, not `sealed_notional` |
| 7 | **Instrumentation absent / silently green** | 08-31 hack4 shipped **5 of 5** holdings with `exp_return: null`; discovery autopsy ran **once ever** (1 row, 427 B); **45.4%** of counterfactual decisions ungradeable yet counted; `daily_latch` **312/312 wins on $0.00**; **2 torn lines** in a hash-chained ledger; VISN **+60.32% vs −45.06%** on the same day | expectations present from 09-01 onward | discovery autopsy unscheduled; VISN unreconciled; `decision_outcomes/` **empty locally**; unmarkable worlds still counted in `win%` |

**The shape of the month in one line:** 7,698 refusals against **23 submissions** (81.4% refusal
rate), 1.06 m counterfactual rows resolving to **10,083** decisions over **4 date blocks**, and
2 gradeable forward sessions. We built a great deal of apparatus and bought very little.

**Execution was never the story.** −$757 of a −$23,306 loss is 3.2%. Both bad sessions are
explained by **admission** (class 2/3) and **beta** (class 4), not by fills.

---

## 5. Improve with every run — the next three experiments

Ranked by `P(changes the roadmap) × value of the decision improved − cost`. Each is motivated by a
receipt above, each has a decision rule written before it runs, and none of them changes what
trades on day one.

### E1 — Price the selector disagreement

**Motivated by:** §2 Miss #1. RZLV lost **−17.30%** at 10% notional while its own row in the same
sealed file read `claims: false`, `rank: 576` of 766, failing `b_rating` by **0.017**. On
2026-09-02, **25 of 30** hack3+hack6 holdings are names the per-name generator declined. And the
contradicting datum: on 09-01 hack3's six declined names averaged **−0.55%** against **−3.54%** for
its three claimed names. Two sessions, two opposite verdicts.

**Do:** stamp every sealed holding with the generator's `claims` verdict and `failed_clauses` —
both already exist in the same JSON, this is a join, not a model — then accrue two forward series,
*held-and-claimed* vs *held-and-declined*. **Nothing changes about what trades.**

**Decision rule, pre-registered:** after 21 sessions, if declined holdings underperform claimed
holdings by more than the round-trip spread, dissent is promoted from *recorded* to a **size
haircut** — not a veto, because `34f08ca` decided deliberately that the runner expresses a sealed
weight rather than re-adjudicating it, and this experiment is not licensed to overturn that.

**Receipts:** `state/predictions/2026-09-01.json` (RZLV row), `state/predictions/2026-09-02.json`;
`month_retro_20260902.json §2.selector_disagreement`.
**Cost:** one field on the seal writer. **P(changes the roadmap): HIGH** — it decides whether we
are running one selector or two, which is currently unanswered while both spend money.

### E2 — Decompose the stop

**Motivated by:** §2 Miss #2. Mean market β **2.10** (median 1.75, **6 of 13** above 2.0, max 4.27)
carried into a **−0.687%** SPY day produced a −6.96% book. `mean_market_share_of_move = 1.49` — on
average the market leg explained **more than the whole move**. Stops fired on the red open (4→2,
3→1). Meanwhile the one loss that was genuinely company-specific — RZLV, **89.4%** company
component — is precisely the one a stop *should* have caught.

**Do:** `move_decomposition.py` already produces the market/sector/company split (`b1254e0`,
`4a96dd5`). Run it **at the stop check** rather than overnight, and shadow-log two policies against
every live position: (a) today's total-return stop, (b) a stop on the **company component only**,
with the market leg widened by the name's own β. **Shadow only — (b) places nothing.**

**Decision rule, pre-registered:** over 21 sessions, promote (b) only if it avoids more
beta-driven exits than it misses company-driven ones **and** terminal wealth is equal or better.
Ranking on terminal wealth, not on the mean, is the standing rule.

**Guardrail:** the worst case must be printed before any promotion. Today each book is under 100%
gross with a −13% to −18% worst case; a wider stop on uncapped gross is a bigger loss, and that
lesson was paid for on 2026-08-28.

**Receipts:** `state/decomposition/2026-09-01.json`; `month_retro_20260902.json §2.decomposition`.
**P(changes the roadmap): HIGH** — it separates a β budget from a stock-selection loss, which is
the entire difference between our two graded sessions.

### E3 — Make a refusal gradeable, then re-price the guards

**Motivated by:** §3c. The one guard with near-complete grading is the one **losing money** —
`mdm_floor`, **2,458 of 2,676** decisions graded, **−$846,249** net, **−$344 per decision**, with
the convex-risk ceiling family alone at −$918,930 over 1,006 decisions. Meanwhile **45.4%** of
counterfactual decisions carry `pnl_usd = 0.0` because they are `unmarkable` or hold-cash worlds —
**and are still counted in `n` and `win%`**. `daily_latch` therefore reports **312 wins out of 312
on $0.00 saved and $0.00 cost**: a 100% win rate that measures nothing. We refused **7,698** times
and submitted **23**, and we cannot say what most of those refusals were worth.

**Do:** three small changes. (i) Give every refusal a markable counterfactual — where no option
chain exists, mark the underlying stock quote, which `539569d` already started doing. (ii) Split
`win%` into *graded* and *ungraded* so an unmarkable world can never contribute a win. (iii) Re-run
`refusal_regret` on the corrected ledger and put `mdm_floor` on trial explicitly.

**Decision rule, pre-registered:** if `mdm_floor` stays net-negative once grading coverage exceeds
80% **and the sample spans more than four date blocks**, the floor is re-tuned rather than
defended. Canon §58: n counts date blocks, and today this whole ledger is n≈4.

**Receipts:** `state/counterfactual.jsonl` (1,062,527 rows → **10,083** decisions),
`state/refusal_regret.json`; `month_retro_20260902.json §3c`.
**P(changes the roadmap): HIGH** — it is the largest measured number in the retrospective, it sits
on data we already own, and it decides whether our guards are protecting capital or starving it.

### Ranked fourth — and start its clock anyway

**Run the attention watchlist forward.** It scored below the three above because its value is
currently *unmeasurable*: the ownership data was backfilled on 2026-09-02, it would have re-flagged
only **5 of 127** extreme movers (3.9%), and its real contribution — the **107 of 200** names
outside the tracker entirely, GPRO among them — has exactly zero prospective observations.

But **prospective time is one of only two things that cannot be parallelised.** Every day this
does not run is a day of evidence that cannot be recovered later, and the cost is a scheduler entry
for a watcher that already exists (`9aec2ad`). So: schedule it today, inject its non-tracker names
as `OBSERVE_ONLY`, and **pre-register the falsifier before the first observation** — *"a material
holder event predicts an extreme move within 21 sessions above the tracker base rate"* — otherwise
this is data collection wearing an experiment's clothes.

Two silent defects to fix in the same pass, both found above: the 200-name cap discarding **87.4%**
of 1,585 candidates, and `n_filings_out_of_window: 0`, which is a gate that cannot fire because
nothing outside the collected range was ever fetched.

### Two things to repair before they are cited as evidence

- **The VISN contradiction.** `discovery_2026-08-28.json` says **−45.06%**; `autopsy/2026-08-28.json`
  says **+60.32%** — same symbol, same day, same headline. Neither file is usable until this is
  settled, and no check caught it.
- **The torn ledger.** `state/decisions.jsonl` has **2 unparseable lines** from concurrent appends
  without locking, on a file that is supposed to be hash-chained. Do not silently repair it —
  repairing a tamper-evident chain is itself the tampering. Record it, then fix the writer.


### What this retro deliberately does not claim

- No result is significant. Two forward sessions.
- BAND_PRIOR v2's superiority over v1 is measured on those same two sessions, and v2's thresholds
  were fitted in-sample on the 2013-2024 panel.
- No statement is made about realised fill quality on the two live days, because
  `state/decision_outcomes/` is empty on this machine and the write-back lives on Railway. That is
  a gap, and a gap is not a zero.
