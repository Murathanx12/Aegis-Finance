# Review: the Bloomberg contest book (adversarial, 2026-09-28)

**Reviewed:** `docs/BOOK_2026-09-28_BLOOMBERG_CONTEST_PROPOSAL.md`, `scripts/contest_book_odds.py`, the four
receipts in `backend/data/optimus/contest/`, LANE B of `docs/ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md`.
**Reviewer stance:** someone who has placed in trading contests. **PRODUCT_EXPERIMENT; nothing here is a claim.**
$0 LLM, no browser automation, no broker, no orders. No existing file was changed.

## 0. Verdict (three sentences)

The proposal plans a static five-stock lottery ticket. But every documented winner of this contest
(2022 #2, 2023, 2024, 2025) traded actively, every day, mostly in non-US high-beta names. None of them
bought and held. On the same zero-skill footing, a daily earnings-magnitude rotation roughly triples
the buy-and-hold chance of a top-10 result (about 10.5% against 3.1% at +40% relative, 2024–26
seasons), while MAX TAIL's own 9% rests on a trailing volatility that historically decays to about
0.7× within a month. Sign the rotation only once three Terminal facts are confirmed (fill price
convention, commissions, cap semantics), and fix the registration deadline today: the 2026 PDF says
**Oct 4, 11:59 am New York** in Key Dates, not Oct 5.

## 1. How winners actually won (documented vs speculation)

| year | result | what the team itself wrote | source |
|---|---|---|---|
| 2022 | #2 relative (+31% rel, +41% abs); highest absolute P&L | "did not trade in US equities"; "stocks with the least weightage in the WLS"; "avg beta of my holdings was 3+"; "held max 7 at one time"; "max 3 countries"; "4 stocks returned more than +100% in four weeks"; stop losses; "kept chipping out profits"; rank #677 in week 1 → #1 by week 4 | linkedin.com/posts/sarthb_bloombergtradingchallenge… (2023-10-02) |
| 2023 | #1 (HKU, "Banteng Investment Fund") | "executed **hundreds of trades**"; "over **67% of Absolute P&L**"; traded "the U.S., **Indian, and Indonesian** stock markets"; "actively managed our portfolio on a daily basis" | linkedin.com/posts/gavinsayogo_… (2023-11-28); ug.hkubs.hku.hk/student-sharing/2023-bloomberg-global-trading-challenge-… |
| 2024 | #1 (RIT), relative profit $1,676,618 | "betting on volatility"; "focused mostly on **foreign stocks**"; traded Asian hours "versus teams in Europe or in the Americas who would be … asleep"; "make as much money as possible without being concerned about the risks of losing"; led 5 of 6 weeks | rit.edu/news/rit-trio-triumphs-global-trading-challenge |
| 2025 | #1 (CUHK "Bear Bull"), "over 400%", $4.1M | "active, disciplined strategy with **daily** portfolio monitoring … across **global** equity markets"; "names with clear momentum, strong volume … actively managing entries and exits based on price reactions, news flow, and **intraday** behavior" | ug.bschool.cuhk.edu.hk/cuhk-business-school-team-wins-2025-…; linkedin.com/posts/shierinasayogo_… (2026-01-28) |
| 2024 | Imperial, top 10% | "The challenge structure inherently rewarded **undiversified portfolios of low-caps** paired with a dose of luck"; closed all positions a week before the end while in the top 2% | linkedin.com/posts/miles2_bloomberg-2024-… |
| 2024 | DCU, top quartile | "moving funds to capitalize on **post-earnings release** price movements before reallocating to anticipate the next set of reports"; "20% of our allowed capital, **the minimum needed to remain active**" | business.dcu.ie/navigating-the-waves-… |

**Documented:**

- Four of four top finishers traded actively, some of them daily or intraday.
- Three of four said they traded non-US markets, and 2025 says "global".
- Concentration and high beta are named explicitly.
- Nobody describes buy-and-hold.
- A +168% or +400% result is arithmetically impossible for a 5 × 20% buy-and-hold book unless one
  name rises several-fold. It is ordinary for a book that compounds several +20–30% legs.

**Speculation (UNVERIFIED, labelled as such):**

1. **Asian limit-move markets.** The 2023 winners traded Indonesia. IDX small caps move up to
   ±20–35% a day (auto-rejection bands) and often run limit-up for several days. India, Korea and
   Taiwan have similar bands. Compounding through a few such streaks produces +100% to +400%.
   The 2025 captain shares a surname with the 2023 winning captain (Sayogo), and both teams appear
   to have Indonesian members. That is a hint, not evidence.
2. **Time zone.** RIT names it as an edge. Murat is in Hong Kong, so Asian sessions fall in his daytime.
3. **Marking.** If TMSG fills a closed Asian market at its stale last price during US hours, news
   from the US session becomes a free look-ahead. This is **not verified** and could be treated as
   non-compliance ("Bloomberg reserves the right to disqualify"). Ask; do not exploit.

**Consequence for the proposal:** it answered "which five names to hold" when the winners answered
"what to hold each day". The proposal's own §3 item 5 concedes that first place needs "compounding
by moving the whole book into what was already moving", and then does not model that.

## 2. The rotation simulation, beside buy-and-hold

**Scratch receipt (not in the repo):**

- Script: `%TEMP%\claude\…\scratchpad\review_contest\rotation_sim.py`
- Output: `rotation_sim_receipt.json` in the same folder
- Summary: `summarize.py` in the same folder

**Data:**

- Price bars: `prices_deep/bars.parquet` + `bars_delisted.parquet`, covering 2016-01-04 → 2026-09-25.
- Report timing: EDGAR 8-K item 2.02 acceptance timestamps, 87,103 prints.
  - A print accepted at or after 16:00 ET counts as after the close (AMC), so it reacts the next session.
  - Otherwise the print reacts on that same session.
- Only on-cadence prints are kept (the previous 2.02 was 50–80 sessions earlier), so that
  unscheduled pre-announcements are not treated as dates known in advance.

**Windows:**

- 38 contest-shaped windows of 25 sessions, starting Jan 19, Apr 12, Jul 12 and Oct 12 each year,
  2017 → 2026-Q2.
- Nine of them are Oct–Nov windows, 2017–2025.

**The rotation rule:**

- At day *t*, the candidates are companies whose reaction session is *t+1*.
- Each candidate needs: ≥ $10M median dollar volume, price ≥ $2, and ≥ 3 prior prints.
- Rank the candidates by **trailing mean |2-session reaction| over the last 8 prints**. This is a
  pre-event observable.
- Hold the top 5 at 20% each for one reaction.
- Unfilled slots are held in cash.

**The zero direction skill convention:**

- Draw one random sign per day (4,000 draws) and apply it to **every** held name **and** the benchmark.
- Direction becomes a coin flip, while magnitudes, same-day dispersion and cross-correlation are kept.

**Benchmark:** SPY. WLS is not on disk.

**Fill conventions (the contest's is UNVERIFIED):**

- `close`: buy at the close of *t*, sell at the close of *t+1*.
- `O2O`: buy at the **open** of *t*, sell at the open of *t+1*. This captures the gap and can be done
  in Hong Kong evening hours (see §4).
- `NEXTOPEN`: the decision is made at the close of *t* and fills at the next open, so the gap is lost.
  This is the failure mode.

**Costs:** 0, 10 or 25 bps per side. Contest commissions are UNVERIFIED; TMSG networks *can* set them.

### Oct–Nov windows only (9 seasons, 2017–2025), mean across seasons

| strategy | P > +20% | **P > +40%** (range by year) | P > +100% | median | p05 | realised, actual direction (seasons > +20%) |
|---|---|---|---|---|---|---|
| **ROT, close fills, 0 cost** | 20.1% | **7.6%** (2.7–16.6) | 0.6% | −3.8% | −36.7% | 3 of 9 (+29% 2020, +22% 2024, +33% 2025) |
| **ROT, O2O, 0 cost** | 16.5 | **4.8** (1.3–11.1) | 0.2 | −2.8 | −30.7 | 1 of 9 |
| ROT, O2O, 10 bps/side | 12.2 | 3.2 (0.4–8.4) | 0.1 | −7.1 | −34.1 | 1 of 9 |
| ROT, close, 25 bps/side | 10.1 | 3.4 | 0.2 | −13.8 | −43.5 | 0 of 9 |
| ROT, NEXTOPEN (gap lost) | 9.4 | 1.6 | 0.0 | −1.1 | −21.8 | 1 of 9 |
| ROT, random rank (no magnitude signal) | 12.5 | 1.8 | 0.0 | −1.5 | −25.3 | 2 of 9 |
| **Buy-and-hold: 5 highest-σ63 names with an in-window print** (proposal's rule) | 10.6 | **1.4** (0–10.0) | 0.0 | −1.9 | −22.8 | 1 of 9 |
| buy-and-hold: 5 random names from the same pool | 4.4 | 0.1 | 0.0 | +0.9 | −12.9 | 0 of 9 |

Notes on the buy-and-hold rows:

- The 5-day block sign-flip version is shown. The daily-flip version is similar (2.9%).
- The random-names row was drawn on a different day from the random-rank rotation row.

### By era, all four seasons (ROT = close, 0 cost)

| era | ROT P > +40% | ROT O2O P > +40% | Buy-and-hold high-σ P > +40% | ROT median / p05 |
|---|---|---|---|---|
| 2017–20 (15 windows) | 4.0% | — | 1.2% | −2.2% / −30% |
| 2021–23 (12) | 7.7 | — | 4.8 | −3.8 / −36 |
| **2024–26 (11)** | **10.7** | **10.5** | **3.1** | **−4.9 / −43** |

**Read it carefully:**

- **Do not pool.** The rotation's odds tripled from the 2017–20 era to 2024–26, because earnings
  moves grew. Mean |reaction| was 4.6% in 2017 and 6.8% in 2025.
- The 2024 Oct season (16.6%) is the best single season.
- **The first place line is still out of reach.** P(> +100%) is at most 3% in the best season and
  about 1% in 2025.
- **Maximising the top-10 probability also raises the chance of a large loss.** The rotation's p05
  runs −41% to −56% in the recent seasons. Its median is negative in every season, because
  volatility drag grows with the variance bought.
- **Costs and fill convention are first-order.** 25 bps a side takes 12–15 pp off the median and
  halves the tail. Filling the next open after the decision destroys it.
- **What makes it work is a real, stable magnitude signal.** Spearman(trailing |reaction|, next
  |reaction|) was 0.33–0.44 in **every** year 2016–2026, with n = 481–5,838 per year. The
  top-decile names move 12–13% against a 6.6% average. Their **signed** mean is ≈ 0 (−0.9% to
  +1.5%), so the direction is not predicted.
  - In a rank regression of |move| on both observables, the coefficient is 0.36 for the trailing
    reaction against 0.10 for σ63.
  - Ranking randomly instead cuts P(> +40%) from 7.6% to 1.8%.
- **Survivor caveat.** Only 47 of 1,784 delisted symbols have 8-K rows, so the event pool is
  survivor-selected. With a zero-skill sign flip this biases the magnitudes (probably downward),
  not the direction. The "realised" column is biased upward.

## 3. The estimate itself (the odds script)

1. **Overlap and regime.**
   - `windows` (W) uses every overlapping 23-session window: 230 windows but ~10 independent at the
     252-session lookback, and 41 windows but **2** independent at 63.
   - `block` (B) resamples 5-day blocks of a **single year, 2025-09 → 2026-09**. In that year AXTI
     returned +1,534%, SNDK +1,681% and MXL +484%.
   - De-meaning removes that drift but **keeps the mania's volatility**, and assumes it persists.
     It historically does not. Across 39 windows, names with trailing σ63 > 6%/day realised a
     **median 0.67× that σ** over the next 24 sessions. The ratio was 0.9–1.0× in the 2025–26
     regime, and **0.37×** for the top 5 by σ.
   - At 0.7× σ, MAX TAIL's normal-approximation P(> +40%) falls from 6.1% to about 1.4%. At 0.9× it
     falls to about 4%.
   - My buy-and-hold rows above use realised forward returns, so they include this decay. That is
     why they read 1–3%, not 6–9%.
2. **Correlation.** The script does use the joint return rows (block) and the full covariance
   (normal), so co-movement is priced. Credit where due.
   - But §4 quotes ρ252 = 0.21–0.46. Over the last 63 sessions the five names correlate
     **0.36–0.73 (mean ≈ 0.58)**, which is ≈ 1.5 effective independent bets.
3. **Does one theme raise the tail?**
   - The proposal's own table says no: at the 252-session lookback, block estimator, the
     diversified book scores 5.8%, the two themed books 5.9% and 6.0%, and the high-σ book 6.7%.
     Per-name σ does the work.
   - Mechanically, a higher ρ raises the book's σ, and with it the tail and the p05 loss equally.
   - In a *rank* contest there is a cost the script cannot see. AI hardware, memory, photonics and
     HPC miners are the obvious 2025–26 theme, so the variance-seeking field will crowd into it.
     When the theme rallies, the top-10 line rallies with you. **Variance that is idiosyncratic to
     the field is worth more than variance shared with it.** Earnings-print variance is
     idiosyncratic; theme variance is not.
4. **The headline 9.0% is the most favourable estimator on the page.**
   - For MAX TAIL at 252 sessions: normal 6.1%, W 7.4%, B 6.7%, B+E1 7.4%, **B+E2 9.0%**.
   - E2 adds two resampled prints to **every** slot, but CIFR, SNDK and VELO see one print in the
     plan.
   - Stage 2 ("similar: 8.4%") is priced on a full 23-session horizon although it is entered around
     Oct 23–30, with 10–15 sessions left. Its B+E1 is 5.5% and its B is 3.9%.

## 4. My recommended entry: a RULE, not five names

**RULE "EARNINGS-MAGNITUDE ROTATION" (EMR)**

- 5 slots × 20%, long only, fully invested, rebalanced every session from Oct 12 to Nov 13.
- The initial deadline of Oct 16 is met automatically.

**Daily procedure (Hong Kong time; US DST ends Sun Nov 1):**

The US open is 21:30 HKT through Oct 30 and 22:30 HKT from Nov 2. Start at the open + 5 minutes.

1. **Sell** every name held. Its print landed overnight or before the open.
2. From the pre-built list, take companies reporting **after today's close or before tomorrow's
   open**. Each must be:
   - a WLS member (from the `MEMB` export);
   - on a date **confirmed** on `EVTS`/`EE` or company IR;
   - ≥ $10M median dollar volume and ≥ $2 price;
   - carrying ≥ 3 prior prints.
3. Rank those candidates by trailing mean |2-session reaction| over the last 8 prints.
4. **Buy the top 5** at 20% of current NAV each, or $200k each if the cap is on the $1M notional.
5. If fewer than 5 qualify (mostly in the Oct 12–16 week), fill the empty slots with the
   highest-σ63 WLS names. The simulation shows this changes nothing (7.5% vs 7.6%).
6. **Week-4 leaderboard rule** (UNQUANTIFIED: the field's distribution is unknown). If the weekly
   ranking published around Nov 6–9 shows the team inside about the top 15, hold the last week in
   a low-tracking-error book: the five largest WLS weights. Otherwise keep rotating. The leader
   sells variance and the trailer buys it. Imperial's 2024 captain did the first half of this.

**Cost of running it:**

- 15–25 minutes a day, done in the evening while awake, not at 04:00.
- About 10 tickets a day, about 240 in the contest.
- The one thing worth building before Oct 12 is a script that prints the ranked list per date from
  the 8-K file, refreshed as dates are confirmed. It is not built, so this rule is written, not
  automated.

**Odds (zero direction skill; O2O fills, the procedure above; UNVERIFIED contest conventions):**

| reading | P(top 10) ≈ P(> +40% rel) | median | p05 |
|---|---|---|---|
| Oct–Nov seasons 2017–25, average | 4.8% (close fills: 7.6%) | −2.8% | −31% |
| **Recent regime 2024–26, all seasons** | **10.5%** (close: 10.7%) | −4.9% | −41% |
| Oct 2024 / Oct 2025 | 11.1% / 10.9% | −5.2% / −5.3% | −42% / −41% |
| P(> +100%), first place territory | ≤ 1% (O2O), ≤ 3% (close, best season) | | |

**Scale these ±2×.** The +40% top-10 line is itself an assumption. §6 shows it plausibly sits
anywhere from +20% to +55% across years.

**Against MAX TAIL:** on the same footing, buy-and-hold of the highest-σ names reaches 3.1% in
2024–26. On its own inflated footing it reaches 9%. EMR is at least as good in every reading and
about 3× better on the like-for-like one.

**When EMR loses its edge:**

- **the contest charges commissions:** at 10 bps a side, the 2024–25 Oct seasons fall to 8.4%;
- **or fills are "Next Open" at decision time and the sell cannot be sent before the print:** the
  gap is lost, and the rotation falls to 1–6%.

In either case **fall back to MAX TAIL**, with the fixes in §7.

**What EMR does NOT do:** it does not model the documented Asian limit-move route (§1), because
only 25 global symbols have bars on disk. If the team has anyone who knows IDX, NSE or KRX small
caps, that is the route the winners describe, and a US earnings rotation is the second-best
available here.

## 5. The candidates, checked against primary sources

**Dates.** Last year's prints are from SEC 8-K item 2.02 acceptance times on disk. **No 2026 Q3
date has been announced by any of the seven** as of 2026-09-28. Velo3D announced its Q2 date only
14 days ahead (ir.velo3d.com, 2026-07-28), so most confirmations will arrive **after** the Oct 16
initial-position deadline. The proposal's "confirm before freezing" cannot be done for stage 1.

| name | last year's print (8-K acceptance, ET) | reaction session | proposal's estimate | median $vol 63d | σ63/day | ρ63 with the rest | WLS? | 252d return | selected on outcome? |
|---|---|---|---|---|---|---|---|---|---|
| MXL | 2025-10-23 16:05 (after close) | Oct 24 | 10-22 | $202M | 8.4% | 0.55–0.73 | plausible ($8.5B), UNVERIFIED | +484% | yes |
| AXTI | 2025-10-30 16:17 (after close) | Oct 31 | 10-29 | $527M | 9.9% | 0.53–0.66 | plausible ($5.2B), UNVERIFIED | +1,534% | yes; 2 of its 6 "reactions" are off-cadence (2026-01-09, 2026-04-20: pre-announcements) |
| CIFR | 2025-11-03 07:12 (pre-open) | Nov 3 | 11-02/03 | $577M | 8.0% | 0.36–0.63 | plausible, UNVERIFIED | +25% | partly. **Now "Cipher Digital"**, an HPC data-centre company (investors.cipherdigital.com); confirm the Bloomberg ticker |
| SNDK | 2025-11-06 16:13 (after close) | Nov 7 | 11-04/05 | $20.6B | 7.6% | 0.52–0.73 | yes (≈$260B) | +1,681% | yes; estimate is 1–2 days early vs last year |
| VELO | 2025-11-10 16:02 (after close) | Nov 11 | 11-10 | $15.6M | 6.9% | 0.36–0.65 | **doubtful**: $0.36B, re-listed on Nasdaq only in Aug 2025 | +256% | yes; a two-day slip loses the print |
| FSLY | 2025-11-05 16:11 (after close) | Nov 6 | 11-04 | $110M | 5.9% | — | plausible ($4.0B), UNVERIFIED | +195% | yes |
| BLZE | 2025-11-06 07:03 (pre-open); **switched to after close in 2026** | Nov 6 or 7 | 11-02/05 | $32M | 5.9% | — | doubtful ($0.82B) | +26% | no |

**Liquidity:** a $200k paper ticket is ≤ 1.3% of a day's dollar volume for every name, including
VELO. Liquidity is not a problem. Membership and dates are.

## 6. The target line is softer than §2 of the proposal says

- **2023.** The HKU winner's own post says "over 67% of **Absolute** P&L". The proposal's table
  lists "+67.7%" under *relative*.
- **2022.** The #2 team was at **+31% relative**, which puts the top-10 line around +20% that year.
  The Pareto fit never used this point.
- **The trend.** Winners went from +67% (2023) to +168% (2024) to +400% (2025), and the field
  is learning to buy variance. For 2026, +40% is a reasonable central line and +55% a reasonable
  high one.
- **What to do with it.** Read the real line off the weekly leaderboard. That leaderboard is the
  only information in this contest worth adapting to.

## 7. Rule risks, and the owner's checklist before Oct 4

**Verified today:** the 2026 GTC Introduction PDF (uni-corvinus.hu/downloads/dgep.1gmsb7s/2026-gtc-introduction.pdf).

**Dates in the PDF:**

| event | time (New York) |
|---|---|
| **Registration closes** | Oct 04, 2026, 11:59 **am** (Key Dates); the FAQ says 11:59 pm |
| Challenge starts | Oct 12, 2026, 09:00 |
| **Starting positions entered no later than** | **Oct 16, 11:59 am** |
| Challenge ends / results frozen | Nov 13, 2026, 17:00 |

**Rules restated from the PDF:**

- $1M notional;
- any WLS stock;
- no ETFs, long only, no leverage;
- "no single position … greater than 20% of the notional amount";
- "teams will be able to close winning trades and stop losing trades".

**Checklist:**

1. **Today, before Oct 4 11:59 am New York (23:59 HKT).** Confirm the registration is visible on
   portal.bloombergforeducation.com. The proposal and the roadmap both say "Oct 5"; take the
   earlier time.
2. **Read in the Terminal: `TMSG` Help (Calculations and Definitions) and the T&C.** Write down
   these facts:
   - **the cost basis** for this network: Next Tick, VWAP to close, Next Close, Next Open or PWAP
     (TMSG supports all five, per Bloomberg's TMSG user guide);
   - **commissions**, if any are set;
   - **the 20% cap**: is it checked on the order at entry, or on market value? Does it force a trim?
   - any **minimum invested** amount (DCU 2024 reported 20% "the minimum needed to remain active";
     UNVERIFIED);
   - whether **re-entering the same ticker** is allowed ("Only Allow One Idea per Symbol" is a
     TMSG network option);
   - any **maximum holding period** or trade-count limit;
   - how **non-US listings** are priced during US hours: live quote, stale close, or refused;
   - the **FX** conversion;
   - the exact **"time-weighted Relative P&L"** formula.
3. **Email bbgtradecomp@bloomberg.net** with the cap-semantics, cost-basis, commission and
   stale-price questions. The reply is the only primary source for these.
4. **Export `MEMB` for `WLS Index`** and save it with `checked_on`. Then filter every candidate by
   it, and check VELO and BLZE by name.
5. **On Oct 12, place one small ticket in a US name and one in an Asian name.** Record the fill
   price against the quote and the time. This settles the fill convention empirically, in time to
   choose EMR or MAX TAIL before the Oct 16 deadline.
6. **Sign the utility in one line:** "EMR" or "MAX TAIL (fallback)". Also write the week-4 lock
   rule down **before** the contest, so it is not decided under pressure.

## 8. Findings on the proposal, ranked by severity

| # | severity | finding |
|---|---|---|
| 1 | **HIGH** | Answers the wrong question. Every documented winner traded actively and daily, and none bought and held. A buy-and-hold book is capped at ≤ 1% for first place, and the proposal accepts that instead of modelling rotation. It also ignores the one piece of in-contest information, the weekly leaderboard (§4 step 6). |
| 2 | **HIGH** | Volatility persistence is assumed. Trailing σ from a one-year mania is replayed as forward σ. Historically, names above 6%/day realise 0.67× (median) over the next month. The top-10 odds are overstated by up to ~4× (§3.1). |
| 3 | **HIGH** | Deadline wrong. Registration closes **Oct 4 11:59 am New York** per the 2026 PDF's Key Dates, not Oct 5. The initial-position deadline, Oct 16 11:59 am, is now verified; the proposal had it as UNVERIFIED. |
| 4 | MEDIUM | "One theme suits the utility" is contradicted by the proposal's own table: theme adds 0.1–0.2 pp. It also ignores crowding against the field. The 63-session ρ is 0.36–0.73, not 0.21–0.46. |
| 5 | MEDIUM | The headline 9.0% is the most favourable of five estimators. B+E2 gives every slot two prints when three slots see one. Stage 2 is priced on a horizon it does not have. |
| 6 | MEDIUM | Selection on outcome. Five of seven names returned +195% to +1,681% over the lookback, and the ranking statistic was measured over that run-up. |
| 7 | MEDIUM | VELO is probably outside WLS (a $0.36B re-listing), and its print lands 1–2 sessions before the end. AXTI's "6 reactions" include two off-cadence pre-announcements. SNDK's date estimate is early vs last year's Nov 6 (after close). CIFR is now Cipher Digital. |
| 8 | LOW | 2023's +67.7% is absolute, not relative. 2022's #2 at +31% relative is omitted from the threshold fit. |
| 9 | LOW | The benchmark mixes URTH (63-session lookback) and SPY (252-session lookback). Second-order, as the proposal says, but the two columns are not comparable. |

**What the proposal got right:**

- Zero edge is assumed.
- A 5th percentile is irrelevant under the declared utility.
- Stops are wrong in a contest.
- The luck-distribution control.
- "This is not evidence of skill".

All of that stands, and it applies equally to EMR.

## 9. What the project learns: one measurement to register before Oct 12

A contest ranking is one draw and proves nothing. But the window contains about 1,500 scheduled US
prints, which makes it a natural experiment in **predicting the SIZE of an earnings move.** Register
this with `pre-register-trial` before the window opens:

**Question.** Does the trailing mean |2-session reaction| (8-K based, last 8 prints, ≥ 3) predict
|realised open-to-open reaction| **beyond the options market's implied earnings move**?

- The implied move is available on the Terminal from `EE`/`EVTS`/`OVDV`. The owner exports it at
  the prior close for every WLS US reporter in the window.
- The universe is every WLS US company with a confirmed print from Oct 12 to Nov 13, 2026, whether
  or not it was traded.

**Primary metric.** The partial rank coefficient of the trailing |reaction| on the realised
|reaction|, controlling for the implied move and for σ63. The confidence interval is clustered by
report date.

**Prior, from 2016–2026 on disk (without the implied move):**

- Spearman 0.33–0.44 in every year;
- rank-regression coefficient 0.36 for the trailing |reaction| against 0.10 for σ63.

**Decision rule.**

- A partial coefficient ≥ 0.05 with the CI excluding 0 means the trailing magnitude carries
  information the options market does not price. The owed follow-up is then a straddle-cost test
  (`PRODUCT_EXPERIMENT`).
- Otherwise it is `FAILED_VARIANT`: the implied move already contains it.

**Why this and not the book's P&L:** it is graded on about 1,500 events, not 1, and it is the exact
observable EMR trades on. Five weeks of contest trading then produce a dataset whichever way the
rank falls.

---

**Sources used (all fetched 2026-09-28):**

- The 2026 GTC Introduction PDF (uni-corvinus.hu)
- The 2024 GTC Introduction PDF (ug.hkubs.hku.hk)
- rit.edu news
- ug.bschool.cuhk.edu.hk and glef.cuhk.edu.hk
- ug.hkubs.hku.hk student sharing
- LinkedIn posts by the 2023 and 2025 captains and the 2022 #2
- business.dcu.ie
- Imperial LinkedIn
- ir.velo3d.com
- investors.cipherdigital.com
- UCD's TMSG user guide (buselrn.ucd.ie)

The official T&C page (portal.bloombergforeducation.com/trading_challenges/terms) renders with
JavaScript and returned no text: **UNVERIFIED**.
