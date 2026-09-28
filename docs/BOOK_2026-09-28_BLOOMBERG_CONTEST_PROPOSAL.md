# Book proposal: the Bloomberg Global Trading Challenge (proposal 2026-09-28; NOT frozen)

**PRODUCT_EXPERIMENT. Nothing here is a claim. The owner freezes it, not this document.**

## 0. Read this first: the utility being signed

The owner declared the utility on 2026-09-28: *"we already registered for bloomberg, goal is to
maximize profits, we are aiming for first place or top 10, not a respectable 5%."*

What that utility means:

- **Aiming for a top-10 finish is not the same as maximising expected return.** It means
  maximising the chance of an extreme right-tail outcome in one five-week draw.
- That calls for concentration and variance. **It also makes a poor finish more likely.**
- The recommended book has a **median relative result of about −3% to −7%**. Its **5th
  percentile is about −35% to −45%** against the benchmark.
- It reaches the plausible top-10 threshold (about +40% relative) in **roughly 7–11%** of
  simulated outcomes. Section 1 has the numbers.
- First place (+68% to +400% in past years) happens in **at most about 1%** of outcomes for any
  buy-and-hold shape modelled here.
- **Losing is the most likely outcome of this book, and under the declared utility that is
  acceptable.** The money is paper and only rank pays. If a large visible loss is not acceptable
  to the team, the owner should sign §5's FLOOR instead, or state a different utility.

The project has **no demonstrated stock-selection edge**. The 2026-09-28 roadmap scoreboard reads:

- "RESULT IMPROVEMENT: NONE";
- 0 rules survive all six checks;
- top deflated Sharpe 0.198 against a bar of 0.95.

Source: `docs/ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md` §0.

**So every name below is chosen for variance and dated catalysts, not for expected return.** All
probabilities are computed with each name's past drift removed (zero edge).

## 1. The contest, verified and unverified

| rule | status | source |
|---|---|---|
| Challenge Oct 12 – Nov 13 2026; registration closes Oct 5 (the aggregator says Oct 4, 23:59 EDT) | CONFIRMED 2026-09-25 in `docs/research_notes/2026-09-25/research_bloomberg.md`; the aggregator's Oct 4 was re-fetched today | portal.bloombergforeducation.com/trading_challenges (JS page; today's fetch returned only its header), quantchallenges.com/challenges/2026-bloomberg-global-trading-challenge-qc-2899 |
| Owner is registered | **UNVERIFIED**: stated by the owner and not checked | — |
| $1M virtual notional; universe = any stock in **WLS** (Bloomberg World Large, Mid & Small Cap Price Return Index); single names only, no ETFs; **long only**; **no leverage**; **no position > 20% of the notional amount** | CONFIRMED for 2024 from the official PDF, fetched today. Stable 2021–2025 per the research note. **2026 text not yet published** | ug.hkubs.hku.hk/f/competition/254985/262466/2024_GTC_Introduction.pdf |
| Winner = highest **Relative P&L vs the WLS index**. The aggregator says "time-weighted return relative to WLS" | CONFIRMED in the 2024 PDF. The exact formula lives in `TMSG<GO>` Help, which is **UNVERIFIED** | same PDF; quantchallenges (fetched today) |
| Tie-break: highest absolute return | Recorded from the 2025 T&C in the research note. **Not re-fetched** (the page did not render today) | research_bloomberg.md |
| Initial positions due in the first week (2024: Oct 11, 09:00 ET; 2025: Oct 17, 09:00 ET) | 2024 CONFIRMED (PDF). 2026 **UNVERIFIED** | PDF; research note |
| Closing trades during the challenge: "teams will be able to close winning trades and stop losing trades" | CONFIRMED (2024 PDF). Rotation is allowed | PDF |
| Minimum number of positions | **None stated** in the 2024 PDF. **UNVERIFIED** | — |
| Trade count or turnover limit | **None stated**. **UNVERIFIED** | — |
| Cash allowed after the entry deadline | **UNVERIFIED** (the 2025 wording "invested in full" is from the research note) | — |
| **Does the 20% cap apply to cost or to market value?** The text reads "greater than 20% of the notional amount", and the notional is $1M | **UNVERIFIED and decisive**. A market-value cap would force trimming a winner above $200k, which cuts the right tail. Ask `bbgtradecomp@bloomberg.net` | PDF |
| Weekly leaderboard inside the portal | CONFIRMED (2024 PDF) | PDF |
| Number of teams | 2,453 in 2024 (rit.edu, fetched today); 2,700 in 2025 (usf.edu, fetched today) | rit.edu/news/rit-trio-triumphs-global-trading-challenge; usf.edu/business/news/2025/12-10-bloomberg-trading-challenge-usf.aspx |
| Sessions in the window | Oct 12 – Nov 13 2026 is 25 NYSE sessions. After a first-week entry about **23 daily returns** remain, which is the horizon used below | calendar |

### Historical results (each pair is from the team's own page)

| year | rank | relative result | source |
|---|---|---|---|
| 2025 | #1 (CUHK) | "more than 400%", to $4.1M | glef.cuhk.edu.hk/news-events/grand-prize-winner-bloomberg-global-trading-challenge-2025/ (fetched today) |
| 2025 | #69 of 2,700 (USF) | $53,194 = **+5.3%** | usf.edu (fetched today) |
| 2024 | #1 of 2,453 (RIT) | $1,676,618 relative = **+168%** | rit.edu (fetched today) |
| 2024 | top 3% (Iona) | $204,564 = +20.5%; relative or absolute not stated | research note (not re-fetched) |
| 2023 | #1 (HKU) | +67.7% ($637,399) | research note, via FinanceFeeds (secondary) |

Bloomberg publishes no distribution or rank cut-offs.

## 2. The target

**No top-10 return has ever been published.** The estimate below is interpolated, and it is an
**ASSUMPTION**.

The method is a Pareto (power-law) interpolation of rank against relative return, between each
year's #1 and its one mid-rank point:

| year | fitted α | implied #10 |
|---|---|---|
| 2025 (#1 +400%, #69 +5.3%) | ≈ 0.98 | **≈ +38%** |
| 2024 (#1 +168%, ~#73 +20.5%) | ≈ 2.0 | ≈ +54% |
| 2023 (#1 +67.7%, α assumed 1.5) | — | ≈ +15% |

**Targets used below:**

| target | meaning |
|---|---|
| +5.3% | the 2025 top-3% anchor |
| +20% | top 10 in a weak year |
| **+40%** | **top 10, central estimate** |
| +100% / +150% | first place, low end |

**A cross-check from the field.** Suppose ~500 of ~2,600 teams run zero-edge books as volatile as
ours. Then any one of them makes the top 10 about 10/500 = 2% of the time. The +40% column below
(7–11%) is higher than that, which suggests either +40% is on the low side as a threshold or fewer
teams take this much variance. **Treat the absolute top-10 odds as ±2×.** The ranking of the
shapes is the robust part.

## 3. Probability tables

**Receipts:**

- Shapes: `backend/data/optimus/contest/odds_20260928T061655Z_shapes_v2.json`
- Final proposals: `odds_20260928T061801Z_proposals.json`
- Candidates: `candidates_20260928T061733Z.json`
- `odds_20260928T061553Z_shapes.json` is **SUPERSEDED**: it zeroed single-print earnings jumps
  (fixed by symmetrising them).
- Script: `scripts/contest_book_odds.py`. Bars end 2026-09-25.

**Benchmark proxy.**

- 63-session lookback: URTH.
- 252-session lookback: SPY (URTH has only 84 bars on disk).
- WLS itself is not on disk. The book's variance dominates the benchmark's, so the proxy matters
  at second order.

**Estimators.** Horizon 23 sessions, buy-and-hold, zero-edge:

- **N** — normal approximation;
- **W** — every actual overlapping 23-session window (230 at 252 sessions and 41 at 63; only ~10
  and ~2 of them independent);
- **B** — 5-day block bootstrap, 20,000 draws;
- **B+E2** — the block bootstrap with each name's own 8-K 2.02 reactions resampled twice per slot,
  which approximates one post-print rotation.

### P(relative return > +40%): the top-10 column

| shape | names | σ_rel (N, 63/252) | N 63 / 252 | W 63 / 252 | B 63 / 252 | B+E2 63 / 252 |
|---|---|---|---|---|---|---|
| rehearsal 10 × 10% (frozen 09-27) | NVEC MAN RHI ACI PEGA IRDM HELE SMPL PRGS AGYS | 9.0% / 7.9% | 0.0% / 0.0% | 0.0 / 0.0 | 0.0 / 0.0 | 0.0 / 0.1 |
| 5 × 20% diversified, events (ρ ≤ 0.25, distinct GICS) | AXTI BLZE APPS VELO IOVA | 21.6 / 20.0 | 3.2 / 2.3 | 0.0 / 1.3 | 9.2 / 5.8 | 8.2 / 8.4 |
| 5 × 20% one theme: photonics / small semis | AXTI MXL AAOI FORM ICHR | 31.4 / 25.3 | 10.1 / 5.7 | 0.0 / 7.4 | 8.2 / 5.9 | 8.9 / 7.5 |
| 5 × 20% one theme: BTC miners / AI hosting | CIFR HUT RIOT WULF CORZ | 28.0 / 23.9 | 7.6 / 4.7 | 0.0 / 1.7 | 8.6 / 6.0 | 9.6 / 6.1 |
| **5 × 20% highest robust σ, in-window print** | **AXTI CIFR SNDK VELO MXL** | **30.4 / 25.9** | **9.4 / 6.1** | **0.0 / 7.4** | **9.2 / 6.7** | **10.9 / 9.0** |
| barbell: 3 high + 2 mega-cap | AXTI CIFR BLZE MSFT AAPL | 16.8 / 14.8 | 0.9 / 0.4 | 0.0 / 0.0 | 3.5 / 2.1 | 6.4 / 4.4 |
| 8 × 12.5% diversified, events | AXTI BLZE FSLY APPS VELO IOVA CRCL EVC | 15.6 / 16.1 | 0.5 / 0.7 | 0.0 / 0.9 | 4.6 / 2.9 | 3.3 / 4.8 |
| random 5 × 20% from the 1,662-name event pool (1,000 draws, median) | — | 6.7 (p10–p90 5.3–9.2) | 0.0 / — | | | |

### The whole distribution, 252-session lookback, block bootstrap (B)

| shape | P > +5.3% | P > +20% | P > +40% | P > +100% | median | p05 | p95 |
|---|---|---|---|---|---|---|---|
| rehearsal 10 × 10% | 21.3% | 0.8% | 0.0% | 0.0% | −0.5% | −11.2% | +12.6% |
| diversified 5 × 20% | 34.5 | 16.5 | 5.8 | 0.2 | −3.0 | −27.5 | +42.9 |
| theme photonics | 36.9 | 18.6 | 5.9 | 0.1 | −2.3 | −34.3 | +42.6 |
| theme miners | 38.0 | 18.6 | 6.0 | 0.1 | −2.3 | −33.0 | +42.8 |
| **highest-σ 5 × 20%** | **37.0** | **19.4** | **6.7** | **0.2** | **−3.0** | **−35.0** | **+44.9** |
| barbell 3 + 2 mega | 32.0 | 10.2 | 2.1 | 0.0 | −1.7 | −19.1 | +28.6 |
| 8 × 12.5% | 34.5 | 13.0 | 2.9 | 0.0 | −1.7 | −22.7 | +33.0 |

(The 63-session lookback and all four estimators are in the receipt.)

### What the tables say

1. **The reviewer's "15–25% versus 0.5–3%" holds, for the thresholds it used.** It computed
   P(> +20.5%), the top-3% line:
   - the rehearsal is 0.6–1.3% under the normal approximation and 0–3.4% under the bootstraps;
   - 5 × 20% high-σ books are 16–26% (normal) and 15–24% (block bootstraps; the few-window W
     estimator ranges 0–24%).
   - **For the owner's target it is much starker.** At +40%, the rehearsal is ≈ 0% under every
     estimator; the best 5 × 20% shapes are 6–11%.
2. **Shape matters more than names.** Every 5 × 20% book of 5–10%/day names lands at 6–11% at +40%.
   Among them, the differences are inside estimator noise. Moving from 10 × 10% to 5 × 20% is the
   one decision that counts.
3. **The normal approximation misreads fat tails in both directions.**
   - At +40% it understates the barbell and the 8-name book (0.4–0.9% normal vs 2–5% bootstrap):
     their tails come from single-name earnings jumps.
   - At +5.3% it overstates the rehearsal (25–28% normal vs 7–29% across the bootstraps).
   - The actual-window bootstrap (W) at 63 sessions has only ~2 independent windows. Its zeros mean
     "not in this quarter", not "impossible".
4. **Rotation (E2) adds about 1–3 pp at +40%.** It is worth doing. It does not change the order of
   magnitude.
5. **First place is not reachable by shape.** P(> +100%) is ≤ 1% for every buy-and-hold book; it is
   0.1–1.0% for the best.
   - Past winners (+168%, +400%) needed either one name up several-fold inside the month, or
     compounding by moving the whole book into what was already moving.
   - RIT 2024 described "betting on volatility", concentrated in Asian equities (rit.edu).
   - Neither route can be modelled from 252 sessions of history. Both are lottery mechanics, not
     skill.
6. **Beware the raw-drift rows in the receipt.** With past drift kept, the highest-σ book shows
   27–31% at +40%. That is AXTI's +1,534% and SNDK's +1,681% over 252 sessions replaying themselves.
   This is the selection effect of picking volatile names that ran, and it is **not a forecast**.

## 4. Candidates

The candidate table is `candidates_20260928T061733Z.json` (the top 40 by event score, plus every
proposal name).

**How it was built:**

- **Universe:** `rehearsal_book.universe` (xs_ranker eligibility), 2,889 US names.
- **Earnings estimates:** EDGAR 8-K item 2.02, taken two ways — the last 2.02 + 91 days (cadence),
  and last year's Oct/Nov 2.02 + 364 days. The 8-K file ends 2026-09-03.
  - 2,019 names are IN_WINDOW on both estimates.
  - 75 are in window on cadence only.
  - 493 are UNKNOWN.
- **Event pool:** 1,662 names. The filters are:
  - both estimates inside the window, and the later one ≤ Nov 12 (the reaction must land by Nov 13);
  - ≥ 3 past reactions;
  - no daily move above 100% in 252 sessions (split suspects out: MRNA, DFNS, SDOT, CAPR, REPL and
    SRZN are removed);
  - median 63-session dollar volume ≥ $10M.
- **Event score:** √(robust σ63² × 22 + median |2-session 8-K 2.02 reaction|²).
- **Implied volatility:** none is on disk. Not used.

| name | cap $B | robust σ63/day | σ252/day | past reactions (n, median \|move\|) | Q3 estimate (cadence / last year) | 252-session return |
|---|---|---|---|---|---|---|
| AXTI | 5.2 | 10.4% | 9.7% | 6, 19.1% | 10-29 / 10-29 | +1,534% |
| CIFR | 7.4 | 8.4 | 7.3 | 4, 19.5 | 11-03 / 11-02 | +25% |
| SNDK | 260 | 7.4 | 7.3 | 4, 10.5 | 11-04 / 11-05 | +1,681% |
| VELO | 0.36 | 7.4 | 11.7 | 4, 22.4 | 11-10 / 11-09 | +256% |
| MXL | 8.5 | 7.4 | 7.8 | 4, 14.5 | 10-22 / 10-22 | +484% |
| FSLY | 4.0 | 4.5 | 7.8 | 4, 41.4 | 11-04 / 11-04 | +195% |
| BLZE | 0.82 | 5.5 | 6.9 | 4, 42.1 | 11-02 / 11-05 | +26% |
| AAOI (alternate) | 8.6 | 7.1 | 9.1 | 4, 14.0 | 11-05 / 11-05 | +280% |
| APPS (alternate) | 1.3 | 4.6 | 6.3 | 5, 38.1 | 11-04 / 11-03 | +108% |
| HUT (alternate) | 11.9 | 6.6 | 6.8 | 4, 17.3 | 11-03 / 11-03 | +156% |

**Rules for using this table:**

- **Every date is an ESTIMATE.** Confirm each one on `EVTS<GO>` or the company's own IR release
  before freezing. Aggregator dates are not accepted: this project was burned by a PDUFA date that
  had already passed.
- **FDA and other binary events:** none is used, because no primary-source date is on disk.
- **Correlation:** ρ252 within the MAX TAIL book is 0.21–0.46. It is mostly one AI-hardware /
  compute factor, which suits the utility.

## 5. The two proposals

Each proposal is five slots × 20% = 100% gross, long only, no leverage, no cash after entry.

### MAX TAIL (recommended)

| slot | stage 1 (enter by the first-week deadline) | hold through | stage 2 (enter the session after the print) |
|---|---|---|---|
| 1 | **MXL** 20% | print ~10-22 | **FSLY** 20% (print ~11-04) |
| 2 | **AXTI** 20% | print ~10-29 | **BLZE** 20% (print ~11-02/05) |
| 3 | **CIFR** 20% | print ~11-02/03, then hold to the end | — |
| 4 | **SNDK** 20% | print ~11-04/05, then hold to the end | — |
| 5 | **VELO** 20% | print ~11-09/10, then hold to the end | — |

**Odds** (252-session lookback, B+E2; stage 1):

| measure | value |
|---|---|
| P(> +40%) | 9.0% (10.9% on 63 sessions) |
| P(> +20%) | 21.3% |
| P(> +100%) | 0.6% |
| median | −4.6% |
| p05 | **−39.4%** |
| p95 | +53.1% |

Stage 2 (FSLY CIFR SNDK VELO BLZE) is similar: 8.4% at +40%, p05 −37.6%.

### TAIL WITH A FLOOR

| slot | stage 1 | stage 2 |
|---|---|---|
| 1 | **AXTI** 20% → after its print ~10-29 | **FSLY** 20% |
| 2 | **CIFR** 20%, hold | |
| 3 | **BLZE** 20%, hold | |
| 4 | **MSFT** 20%, hold (low tracking error to the benchmark) | |
| 5 | **AAPL** 20%, hold | |

**Odds** (252-session lookback, B+E2):

| measure | value |
|---|---|
| P(> +40%) | 4.4% (6.4% on 63 sessions) |
| P(> +20%) | 15.5% |
| median | −3.1% |
| p05 | **−26.3%** |
| p95 | +38.1% |

### Recommendation: MAX TAIL

The FLOOR roughly **halves the top-10 probability** (about 9% → about 4–6%). In exchange it
improves the 5th percentile by about 13 pp (−39% → −26%).

Under "first place or top 10, not a respectable 5%", a 5th percentile is worth nothing. Both books
finish outside the top 10 more than 89% of the time, and the ordering of the non-top-10 finishes
does not pay.

Sign FLOOR only if the team puts real weight on not finishing visibly bottom-decile. That is a
different utility and should be written down as such.

## 6. Rotation rule (written, not automated)

1. **Enter all five stage-1 names at 20% by the first-week deadline.** Enter them on the first day
   if the rules allow, since every session held is variance bought.
2. **Hold each name through its confirmed print.** On the session after the print, sell it and buy
   the slot's stage-2 name at 20% of the notional.
   - A stage-2 name must not have printed yet.
   - If the stage-2 name is already past its print, or its date is unconfirmed, use the next
     unprinted name by event score from the candidates receipt (alternates: AAOI, APPS, HUT).
3. **No stops.** A stop sells variance at the worst price (review §6).
4. **The only discretionary exception:** a name halted or delisted, or a confirmed print date that
   moves outside Nov 12. Replace it with the next unprinted alternate.
5. **If the 20% cap binds on market value, trim to 20% and put the excess into the next unprinted
   alternate.** Do not hold cash. This is **UNVERIFIED: confirm the cap semantics first** (§1).
6. **Turnover.** 100% at entry, plus 2 rotations × (20% sell + 20% buy) = **180% of the notional
   traded**, 12 tickets in all. No contest trade limit is known (UNVERIFIED).

**Worst case in dollars** (session protocol 4):

- gross 5 × 20% = 100% of $1M, Σ|notional| / equity = 1.00;
- one name to zero = **−$200,000**;
- the modelled p05 = about −$394,000 relative;
- an all-five −50% month = −$500,000.

It is paper money. It is printed here because the protocol requires it.

## 7. What this book is NOT, and its registration

- **It is not evidence about the project's skill, whatever it returns.** It must never be quoted as
  such, and that includes a top-10 finish.
  - Its expected relative return is zero or negative by construction.
  - It is one draw.
- It is registered as **its own family of ONE book** under licence `PRODUCT_EXPERIMENT`, with
  utility `contest_rank_right_tail` and objective "Relative P&L vs WLS, 2026-10-12 → 2026-11-13".
- It is not added to any library family or leaderboard, and it is not counted in the "books ahead
  of SPY" scoreboard.

### Matched controls (written now, read after Nov 13)

1. **Equal-weight permitted list.** Every WLS member in the owner's export, equal weight, held from
   the actual entry date. If no export exists, use the 1,662-name event pool as a US-only proxy, and
   label it as such.
2. **The luck distribution.** Draw 1,000 random 5 × 20% books from the event pool, entered on the
   same dates with the same one-rotation rule (the rotation goes into a random unprinted pool name).
   - Seed 20261012.
   - The first 20 draws and the `books_sha256` `f5475b615547c565` of the 1,000 draws are in
     `odds_20260928T061655Z_shapes_v2.json`.
   - **The report is the percentile of the book's realised relative return within these 1,000.**
     That percentile is the only honest reading.
3. **The sibling shapes as shadows:**
   - the FLOOR book;
   - the frozen rehearsal (book `4d0cebfeb8867fb8`);
   - IWM, which is the honest comparator for a US small/mid book (review §5.8).
4. **Read these first:**
   - the book's actual final rank out of N;
   - where the realised result falls in the Monte Carlo distribution above: was a +40% outcome a
     ≈ 9% event or not?
   - the realised σ against the declared σ_rel of 26–30%.

## 8. What the owner must supply before freezing

1. **The WLS membership export.** None is on disk (`find backend/data -iname "*wls*"` returns
   nothing). Run `MEMB` on `WLS Index` and export it, or check each name. Save it as
   `backend/data/optimus/competition/wls_members_2026-10.yaml` with `checked_on` and `source`.
   - **VELO ($0.36B) and BLZE ($0.82B) are the names most likely to fall below a small-cap
     cut-off.**
   - All ten names are US listings, while WLS is global. Asian names (the RIT route) were not
     modelled because only 25 global symbols have bars on disk.
2. **The 2026 T&C and `TMSG<GO>` Help,** to confirm:
   - how the 20% cap is measured (cost or market value);
   - the definition of Relative P&L and whether it is time-weighted;
   - the initial-position deadline;
   - whether cash is allowed;
   - trade limits;
   - the tie-break.
3. **Registration confirmation.** The owner stated it; it has not been seen.
4. **Confirmed print dates** from `EVTS<GO>` or company IR for the ten names (five stage-1, two
   stage-2, three alternates).
5. **The signed one-line utility:** "contest rank, right tail: MAX TAIL" or "FLOOR".

## 9. Reproduce

```
python -m scripts.contest_book_odds --book "MAX_TAIL=AXTI:0.2,CIFR:0.2,SNDK:0.2,VELO:0.2,MXL:0.2" \
    --targets 0.053,0.20,0.40,1.00,1.50 --with-earnings --events-per-slot 1,2 --keep-drift
```

The script:

- refuses (exit 2) a ticker with no bars, a weight above 20%, a negative weight, or a sum above 1;
- writes `backend/data/optimus/contest/odds_<run_id>.json`.

The tests are in `backend/tests/test_contest_book_odds.py` and use synthetic bars with dates
derived from today.

PRODUCT_EXPERIMENT; nothing here is a claim. $0 LLM, no network in the computation, no orders.
