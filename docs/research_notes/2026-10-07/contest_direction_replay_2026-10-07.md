# ROT5_DIR event-level replay, as our receipt, 2026-10-07 (Q9a item 2; REVIEW C9 F2)

Licence `PRODUCT_EXPERIMENT`. $0, no network, no order. This is an exploration receipt, not a claim.

## RESULTS

| | top 5 (ROT5's book) | top 20 |
|---|---|---|
| events (buy days) | 6,860 (1,716) | 16,481 (1,716) |
| drop share | **34.5%** (1,892 by net lowering, 475 by net Sell) | 33.1% |
| mean r_o2o, dropped / kept (gross) | −0.08% / +0.39% | +0.02% / +0.36% |
| net at 10 bps a side, dropped / kept | −0.28% / +0.19% | −0.18% / +0.16% |
| net at 25 bps a side, dropped / kept | −0.58% / −0.11% | −0.48% / −0.14% |
| **dropped − kept**, pp/event (t day-clustered; t month-clustered) | **−0.48 (−1.69; −1.73)** | **−0.34 (−2.07; −2.34)** |
| dropped − ADMIT only (t day) | −0.55 (−1.93) | −0.35 (−2.11) |
| within-day paired (days with both groups) | −0.51 (t −1.55, 1,148 days) | **−0.09 (t −0.44, 1,299 days)** |
| **with the 63d momentum control** (tercile FE + linear mom63, t day) | **−0.44 (−1.51)** | **−0.27 (−1.61)** |
| P(> +20%), dropped / kept | **3.5% / 3.5%** | 2.5% / 2.2% |
| P(< −20%), dropped / kept | **4.4% / 2.8%** | 3.2% / 1.9% |
| p01, dropped / kept | −31.4% / −27.1% | −30.0% / −24.5% |
| sd, dropped / kept | 11.9% / 9.9% | 10.2% / 8.6% |
| years with dropped − kept < 0 | 5 of 8 (2020 −1.42 pp, 2024 **+1.83** pp) | 5 of 8 |
| leave one year out | −0.30 to −0.81 pp | −0.25 to −0.44 pp |

**Reading.**

- **The mean gap reproduces.** It is roughly −0.3 to −0.5 pp per event, and dropped names do worse at both book sizes.
  - It is **not distinguishable from noise at top 5** (t −1.69), and only at about t 2 at top 20.
  - Leave-one-year-out never flips its sign.
- **Momentum explains about a fifth of it.**
  - The filter drops **52-54% of the low-momentum tercile** and 18-19% of the high one: target cuts follow price falls.
  - Inside each tercile, dropped names still do worse. At top 5 the gaps are −0.24, −0.30 and −0.90 pp; at top 20 they are −0.22, −0.19 and −0.45 pp. All are negative and none is significant.
  - The controlled coefficient is −0.27 pp at top 20 (t −1.61).
- **The declared trigger did not fire.** At top 20 the controlled gap neither kept |t| >= 2 nor fell to |t| < 1. So the receipt does not say "the filter is more than momentum", and it does not say "the filter is momentum".
- **The within-day reading weakens top 20.** Comparing dropped and kept names on the same buy day gives −0.09 pp (t −0.44) at top 20. Much of the pooled top-20 gap is days with many drops being bad days, so the gap is between days, not within them.
  - The review's "both groups share the day's market move" is true per event, but not of the pooled mean.
  - At top 5 the within-day gap holds (−0.51 pp, t −1.55).
- **The right-tail argument does not reproduce at top 5.**
  - The review had P(> +20%) 4.8% for dropped names vs 4.0% for kept ones. Here it is **3.5% vs 3.5%**.
  - The left tail does reproduce: 4.4% vs 2.8%.
  - So at ROT5's breadth the filter is a **left-tail cut that does not give up right tail**, with a mean gain that cannot be told apart from noise.
  - At top 20 the dropped names carry slightly more right tail (2.5% vs 2.2%).

**What it changes.** The runbook's ROT5_DIR line ("NOT recommended ... the dropped names had the FATTER right tail") cites a tail asymmetry this receipt does not find at top 5. A **dated note** now sits beside that line in `docs/CONTEST_RUNBOOK_2026-10.md`. The frozen recommendation is not edited: the declared trigger did not fire, and the book choice is the owner's.

## Why our numbers differ from the review's

- **Drop share: 34.5% here vs 28.1% in the review.**
  - Universe: the lab's ROT5_TRAIL eligibility (liquid at the buy open, on cadence) gives 6,860 top-5 events. The review had 8,461.
  - Source: the analyst file is the 10-06 pull (395,127 rows), not the one the review read.
- **Tails.** The review's top-5 tails were 4.8% / 4.0% and 4.4% / 2.9%. Here the dropped names have 84 events above +20% out of 2,367. The right-tail asymmetry is a small count, and a different event set moves it; the left-tail asymmetry survives both.
- **Unchanged from the review:** the stamps (SEC 8-K 2.02 primary) and the return definition (`r_o2o`).

## Construction (declared and hashed before the run)

- **Stamps.** `contest_desk.raw_event_stamps()`, restricted to US: 97,545 SEC 8-K 2.02 stamps and 152 from `contest/earnings_history_us_recent.parquet`.
  - That file holds only 2,429 stamps. It is the tail after the SEC file ends, so on its own it cannot serve as the history.
- **Events.** 85,410 US events built by `contest_desk.build_events` on the contest bars panel (2016-01-04 → 2026-10-06, 5,675 symbols).
  - 36,417 eligible candidates have a buy day from 2019-01-02 to 2026-10-05.
- **Ranking.** `trail_abs` descending per buy day: the key the rehearsal and the lab use.
- **Direction.** `contest_direction.analyst_direction`, imported read-only, at asof = each event's buy day.
  - `contest_direction.py` and `contest_rehearsal.py` are unchanged; their contract hash covers their code until the contest ends.
  - `now_utc` is each day's own last pull. This makes the first-seen guard non-binding, and it must be, because no `first_seen_utc` exists before 10-06. Point in time rests on the vendor's `event_date` (REVIEW C9 F1).
  - Source: `target_revisions.parquet`, sha256 `de10c593106f4ccc…`, 395,127 rows.
- **Momentum.** `mom63` = close(t−1) / close(t−64) − 1, known before the buy open.
  - Tercile cut points come from each subset's pooled events (top 5: −5.7% / +12.0%). They describe the sample; they are not a rule.
  - The split sums to the total (`split_sums_to_total: true`; every event has `mom63`).
- **Costs.** 10 and 25 bps a side, charged to both groups, so the difference is cost-free.
- **Survivorship.** SURVIVOR-SELECTED.
  - Only **2 of 1,803** event symbols stopped trading more than 30 days before the panel's end. The pool is the contest universe alive today.
  - The ratings vendor serves live tickers only.
  - The bias lands on both groups, but not necessarily equally.

## Receipts

- Declaration (written before the run): `docs/research_notes/2026-10-07/DECLARATION_ROT5_DIR_REPLAY_v1.json`.
  - body sha256 `c02cd933a7e5cded…`
  - It pins the analysis code's sha256. A mutated declaration or changed code refuses (tested).
- Receipt: `backend/data/optimus/contest/strategy_lab/direction_replay_DRR_2026-10-07_1.json`. It holds by year, leave-one-year-out, terciles, ADMIT-only and the within-day paired reading. Runtime 95 s.
- Code: `scripts/contest_direction_replay.py`. Tests: `backend/tests/test_contest_direction_replay.py`.

## Reproduce

```
python -m scripts.contest_direction_replay --run-id <new id>    # >= 3 GB free; ~2 min
```
