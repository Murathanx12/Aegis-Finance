# Review: signal structure, paper rules round 2, and the cluster-aware bridge (2026-09-27)

> Reviewer: the adversarial investor ("you are wrong; I would have done this").
> This review is read-only: $0 LLM spend, no code, data or process changes. It is written
> for the adjudicator.
>
> **Under review:**
> - `03376f6a` (signal structure, run `T150811Z`)
> - `615256bd` (round 2, run `T182110Z`)
> - `d93f6029` (bridge)
>
> **Receipt of record:** `leaderboard_2026-09-26T164302Z.json`.
>
> **How every number here was computed:** from the committed receipts only —
> `signal_structure/monthly_returns_2026-09-26T150811Z.parquet` (115 months × 880 cells),
> `monthly_returns_2026-09-26T182110Z.parquet`, `etf_monthly.parquet`, the two `signal_structure_*.json`,
> `round2_readout_2026-09-26T182110Z.json` and `wrds/bulk/comp__security.parquet`.
> I used the builders' own `signal_structure.ols`, `factor_spreads`, `window_masks`, `corr_matrix`
> and `cluster`, so every difference from the builders' numbers is a difference of question,
> not of arithmetic. Active return = net minus SPY, as in the builders' code. "Dev" means the 83
> entry-dated blocks before 2024; "24-26" means the 32 entry-dated blocks from 2024 onward.

**RESULT IMPROVEMENT: NONE.** All three chunks moved gradeability. None moved terminal wealth.
Two of the three wrote a conclusion stronger than their data can support.

---

## 0. Verdict per chunk

| chunk | verdict | why |
|---|---|---|
| `03376f6a` signal structure | **GRADEABILITY** (with a defective reading) | The cluster map and the DSR-at-clusters are real denominators, and every later claim can use them. But the headline "the 2024-26 momentum win is SMH beta; no alpha t ≥ 2 in both windows" reads **no power** as **no alpha** (§1). It also blames on the RULES an IWM tilt that belongs to the PANEL (§2). |
| `615256bd` round 2 | **GRADEABILITY** for VAL-01; **NEITHER** for distance-to-default | The VAL-01 fix is genuine infrastructure: 0.23-0.84% median error vs CRSP, against 3-13.5% for the refused construction. But the distance-to-default verdict mislabels a single month. "2020 only" is really **January 2021 only**, the meme-squeeze month (§4b). The company-identity join also has an untested hole (§4a). |
| `d93f6029` bridge | **GRADEABILITY** (the best of the three) | FACTOR_BETA in the taxonomy, factor twins, and one observation per cluster are all correct instincts. But the cluster mean throws away the within-cluster spread. That spread is the only test the bridge has of whether construction matters, and inside the momentum cluster it is **56 pp** (§5). |

---

## 1. The ETF decomposition: "alpha t < 1" is mostly evidence of no power

### Power, from the builders' own regression (282 primary cells, 24-26 window, 6 spreads + intercept)

| quantity | value |
|---|---|
| SE(alpha), median | **0.88%/month** (p25 0.65%, p75 1.31%, max 3.37%) |
| MDE at 80% power (2.8 × SE), median | **2.46%/month** (p10 1.33%, p90 4.92%) — that is **29%/yr** |
| P(t ≥ 2 in 24-26) if the TRUE alpha is 1%/month (12%/yr) | median **19%**, p90 54% |
| P(t ≥ 2 in 24-26) if the true alpha is 0.5%/month | median **7.6%** |
| P(t ≥ 2 in dev) at a true 1%/month | median 56% (dev SE 0.46%) |
| **P(t ≥ 2 in BOTH windows) at a true 1%/month** | **median 10%** |

So "no survivor in both windows" is what happens **nine times in ten** even if every rule carried
a real 12%/yr alpha.

The survivor search also ran over the wrong set. The receipt decomposes **52 cells** (the dev and
24-26 top-30s), not 282. Over all 282 primary cells:

- **25** clear t ≥ 2 in dev. The document says 15.
- **19** clear t ≥ 2 on the full 115 months.
- **3** clear it in 24-26. That is fewer than the ~7 expected by chance at 2.5% one-sided, which
  is also what low power looks like.

### The point estimates do not say what the headline says

| series | dev alpha (t) | 24-26 alpha (t, SE) | z of the change |
|---|---|---|---|
| `mom_12_1_q@k20` | +2.11% (2.49) | **+2.11%** (1.13, SE 1.86%) | **+0.00** |
| `mom_12_1@k20` | +2.22% (2.47) | −0.18% (−0.09, SE 1.95%) | −1.12 |
| `disp_short_avoid@k20` | +2.1% (2.52) | +1.5% (0.94) | −0.34 |
| 25 dev survivors, mean | +1.52% | +0.19% | only **2 of 25** have abs(z) ≥ 2 |

- The document calls `mom_12_1_q` "79% SMH/MTUM". Its alpha **point estimate in 24-26 is
  identical to dev**. Only the standard error changed, from 0.85% to 1.86%.
- The "SMH+MTUM share" column is a ratio of in-sample contributions on collinear regressors. It
  prints +97% for `qc470` and −21% for `illiquid`. It is not a verdict.

### Beta stability: the betas are a regime, not an exposure

Correlation of each rule's beta, dev vs 24-26, across the 282 cells:

- IWM: **0.62**
- SMH: **0.40**
- MTUM: **0.31**

The momentum survivors' loadings swap between windows. MTUM beta goes from ≈ 1.4 in dev to ≈ 0
in 24-26; SMH beta goes from ≈ 0.4 to ≈ 1.0 (e.g. `mom_12_1`: MTUM 1.42 → −0.33, SMH 0.46 → 1.07).

That is not a fixed style. **Momentum bought semis because semis were trending**, so regressing it
on the ETF of what it bought, chosen AFTER the window, credits the signal's output to the ETF. The
two spreads are also collinear in 24-26: SMH vs MTUM ρ 0.69, SMH vs USMV −0.69.

### The test that would separate beta from alpha: an ex-ante hedge

Take the betas fitted in dev, apply them to the 24-26 spreads, and see what is left:

| series | 24-26 mean active | alpha with in-window betas (t) | **after the ex-ante dev-beta hedge (t)** |
|---|---|---|---|
| momentum cluster 122, 17-member mean | +0.85%/mo | −0.04% (−0.02) | **−1.83%/mo (−1.02)** |
| `mom_12_1_q@k20` | +2.87% | +2.11% (1.13) | +0.21% (0.10) |
| `mom_12_1@k20` | +1.04% | −0.18% (−0.09) | −2.03% (−0.94) |
| `quality_composite@k20` | −0.67% | +0.64% (1.30) | −0.33% (−0.55) |
| random k50 mean | −0.47% | −0.02% | −0.55% (−1.42) |

**The honest sentence:** *"In 2024-26 the momentum cluster's return is fully accounted for by
the SMH, IWM and MTUM spreads, and its point estimate fell below its dev factor model (−1.8%/month
after the ex-ante hedge, t −1.0). Thirty-two blocks cannot distinguish 'the pre-2024 alpha died'
from 'it is intact at 2%/month'. The MDE is 2.5%/month."* Not "is beta".

---

## 2. IWM β ≈ 1 is the PANEL's tilt, not the rules'

The random controls load on IWM − SPY almost as much as the rules do:

| cell | IWM β dev (1-factor) | IWM β 24-26 | IWM β full (6-ETF) | t |
|---|---|---|---|---|
| random_1 @k10/20/50 | 0.84 / 0.94 / 0.76 | 0.35 / 0.48 / 0.56 | 0.78 / 0.82 / 0.76 | 5.0 / 7.0 / 9.5 |
| random_2 @k10/20/50 | 0.77 / 0.85 / 0.85 | 0.36 / 0.45 / 0.57 | 0.72 / 0.71 / 0.73 | 5.4 / 8.1 / 9.7 |
| random_3 @k10/20/50 | 0.96 / 0.90 / 0.91 | 0.81 / 0.83 / 0.72 | 0.85 / 0.79 / 0.84 | 5.9 / 6.8 / 9.7 |
| random_large @k10/20/50 | 0.55 / 0.50 / 0.58 | 0.37 / 0.33 / 0.29 | 0.38 / 0.37 / 0.44 | 2.4-6.6 |
| **282 primary rules, median** | — | 0.58 | **0.78** | — |

- The document's "median +1.03" is the **24-26 top-30**. The whole library sits at the panel's
  own ~0.8. The rules add perhaps 0.2-0.3 of size on top.
- **Net CAGR of the random k50 mean vs IWM:** dev **7.3% vs 7.3%**, identical; 24-26 14.2% vs
  16.6%; full 9.2% vs 9.8%. SPY: 13.2% / 21.0% / 15.3%. The panel IS IWM.

**What changes: SPY is the right hurdle for "should Murat own this", and the wrong one for "does
the signal select".** Every "vs SPY" figure charges each rule about **6 pp/yr in dev and 7 pp/yr in
24-26** for panel composition.

| primary rules beating the benchmark in BOTH windows | vs SPY | vs IWM | vs random-EW (net, same panel) |
|---|---|---|---|
| of 282 | **66** | **112** | **135** |

| rule | dev: vs SPY / vs randEW | 24-26: vs SPY / vs randEW |
|---|---|---|
| `mom_12_1@k20` | +22.7 / +28.5 | +4.8 / +11.7 |
| `quality_composite@k20` | +3.7 / +9.6 | −9.5 / −2.6 |
| `net_raises@k20` | +9.7 / +15.5 | +5.9 / +12.7 |
| `low_asset_growth@k20` | +3.5 / +9.3 | +26.0 / +32.8 |

The README needs three columns, not one. **Settling observation:** the forward bridge grades each
book against its random-EW twin beside SPY. "The signal selects" is the twin spread; "Murat should
own it" is the SPY spread. They are different claims.

---

## 3. Clustering on residuals: I expected the count to FALL. It RISES.

Clusters over the 282 primary cells, full window, at each ρ cut:

| series clustered | ρ 0.8 | ρ 0.7 | ρ 0.6 | median pair ρ | share of pairs ≥ 0.8 |
|---|---|---|---|---|---|
| raw net | 83 | 31 | 15 | 0.63 | 7.2% |
| **active (the builders')** | **187** | 131 | 79 | 0.30 | 0.98% |
| residual after SMH / IWM / MTUM | **212** | 171 | 135 | 0.14 | 0.50% |
| residual after all 6 ETFs | **216** | 183 | 147 | 0.15 | 0.51% |

The shared factor does inflate correlation: the median pair ρ halves once it is removed. So pairs
split and the bet count **rises** by ~15%. Two consequences follow:

1. **For multiplicity of ALPHA claims, the denominator is ~215, not ~180.** DSR falls slightly;
   nothing reaches 0.95 either way.
2. **For RISK (what loses together), the active or even the raw clusters are the right ones.** A
   book of "different" residual bets that share IWM β ≈ 0.8 loses together in a small-cap drawdown.

**The number is set by the cut, not the data.** It ranges from 79 to 216 depending on ρ and on
residualisation. Print the curve, not "282 ≈ 180".

---

## 4. Round 2

### 4a. VAL-01 is PIT-sound in its timing, with a company-identity hole

**What is sound:**

- `prccq` is known at `datadate`.
- `cshoq` is known at `rdq`; the anchor is used at `rdq + 2d`, strictly before the decision date.
- The adj-close ratio cancels future splits.
- Restatement risk on `cshoq` is low; Compustat rarely restates share counts.

The CRSP check is real.

**The hole is the gvkey → ticker map, `compustat_ticker_map`.** It uses comp.security's **current**
`tic`, and Compustat renames a dead security's ticker when the ticker is reused:

- **983 of 10,474** USA primary issues inactive since 2016 carry a suffixed tic
  (`AXTC.1`, `NCI.3`, `ENTK.2`, …).
- On a survivorship-free panel, the dead `AXTC` rows can never match their own gvkey. They either
  get no market value, or the market value of whichever company holds `AXTC` now.
- I measured zero ticker collisions, because Compustat's tic is unique by construction. So the
  "a ticker claimed by two gvkeys is dropped" guard never fires, and the defect is silent.
- The CRSP validation matched by ticker too, so it could not see this.

This lands on dead, small, distressed names, which is what value and distance-to-default rules
buy. It is the survivorship bias the panel was built to remove, re-entering through the join.

**Cheap fix, $0, all on disk:**

- `crsp__stocknames` gives a DATED ticker → permno map.
- `crsp__ccmxpf_lnkhist` gives a DATED permno → gvkey map.

**Settling observation:** re-run the three value rules on the CCM-linked market value. Print the
number of panel rows whose gvkey changes, and each rule's dev excess before and after.

**The NaN cliff is real, and there is a quieter cousin.**

- `mkt_value` covers **5,783 rows in 2026**, against ~22-24k per year for 2017-2025.
- From 2026-04-06 the note says every market-value column is NaN. Yet `qc409@k20` keeps returning
  non-cash months in April-July 2026 (−0.57%, +3.08%, 0.00%, +10.36%; no exactly-zero months). The
  rule is either selecting from a residual set or reading another column. **Print `n_eligible` per
  decision date** before the 24-26 value column is read at all.
- The quieter cousin: all through 2025, any name that listed after 2024-12 has no market value. So
  the value rules' 24-26 window is scored on an **ageing, shrinking universe**, and dev and 24-26
  are not the same experiment.

### 4b. Distance-to-default: "2020 only" is January 2021 only, and neither label is the mechanism

**The by-year table is keyed on DECISION year, while the window split uses ENTRY year.**
Recomputed from the parquet (compounded, net minus SPY):

| year | decision-keyed (as printed) | entry-keyed (when the money was at risk) |
|---|---|---|
| 2020 | **+61.0%** | **−3.2%** |
| 2021 | −7.3% | **+75.5%** |

- The decision row 2020-12-31 is January 2021's return: **+52.7 pp excess at k20**. That is the
  GameStop / meme-squeeze month.
- Total log excess over 115 months is **+0.006**, so that one row is ~77× the rule's net lifetime
  excess. **Without that month the mean excess is −0.27%/month.**
- In the actual crash month (March 2020 entry), the rule lost −19.5% against SPY −12.5%. A risk
  premium is supposed to do that.

**Is "2020 only" a refutation, or the mechanism?** Neither.

- A distress premium should lose in the crash and earn over the recovery. Here the whole payoff
  sits in one short-squeeze month, which is not a credit mechanism.
- The stress gate used market vol, not a credit spread, so §4-H1 did not test Friewald-Wagner-Zechner
  either.

**Controls that separate crisis alpha, small-cap rebound beta and squeeze:**

1. **Characteristic-matched twin.** Random names drawn within the book's own size × 252d-vol ×
   12m-return cells. This separates "distress selects" from "high-vol losers rebound".
2. **Short-interest exclusion.** The same rule with the top short-interest decile removed; the
   days-to-cover input is already on disk via the `low_dtc` rules. If the January 2021 month
   vanishes, it was a squeeze.
3. **A credit-spread gate.** FRED BAA10Y is free, and it replaces the market-vol proxy for H1.

**Verdict:** the rule stays `DEPRIORITIZED`, but the reason changes. "One squeeze month" is the
reason, not "2020". The by-year keying bug is a **factory-wide** finding: every "drop 2025" and
LOO-year diagnostic is offset by one month. Protocol item 11's lesson is enforced on a mis-keyed
year.

---

## 5. The bridge: one observation per cluster hides the construction test

Within-cluster spread, full-window clusters, 24-26 excess CAGR vs SPY:

| cluster | n | mean ρ | member range | sd | within-cluster tracking error (ann., median) | dev → 24-26 rank corr inside the cluster |
|---|---|---|---|---|---|---|
| 122 momentum | 17 | 0.85 | **−18.6% … +37.9%** | 17.8 pp | 13.2% | **0.06** |
| 96 revision flow | 10 | 0.89 | −3.9% … +17.4% | 6.3 pp | 4.6% | 0.07 |
| 107 6-1 momentum / trend | 7 | 0.87 | −28.1% … +19.9% | 19.7 pp | 17.8% | **0.86** |
| 105 momentum × quality | 7 | 0.87 | −9.3% … +14.0% | 9.3 pp | 22.7% | **0.82** |

"Same bet" at ρ 0.85 can differ by **56 pp over 32 months**. The two clusters where member ranks
persist from dev to 24-26 are the ones whose members differ in **universe size** (the `_large`
variants win in both windows). The two where ranks do not persist differ in **label filters**:
no-downgrade, no-insider-selling, raised.

That is a finding about construction, and a cluster mean deletes it.

**The two-level read:**

- **Level 1, mechanism.** The cluster's equal-weight forward return minus its random-EW twin (and
  minus the dominant ETF), graded as ONE observation. It answers "does momentum work", and n is
  clusters.
- **Level 2, construction.** Each member minus its cluster mean, as a **paired** series, tagged by
  the axis on which the member differs from the cluster's anchor: k, weighting, universe, hold
  offset or filter. It answers "does this construction choice matter", and n is pairs along that
  axis.
  - Its SE is small only because the pair shares the factor. At 13%/yr tracking error, one month's
    paired SE is ~3.8%.
  - So a construction effect under ~10 pp/yr is invisible for a year. Say so on the row.
  - The already-frozen quarterly-offset triplet (JAJO / FMAN / MJSD) is exactly a Level-2 test,
    and it is the one the bridge currently averages away.

---

## 6. Five "you are wrong" items, each with the observation that settles it

| # | the claim | why it is wrong | settling observation |
|---|---|---|---|
| 1 | "The 2024-26 momentum win is SMH beta; the pre-2024 alpha did not carry over" (`03376f6a`) | The MDE is 2.46%/month, and a true 12%/yr alpha shows t ≥ 2 only 19% of the time. `mom_12_1_q`'s 24-26 alpha EQUALS its dev alpha (2.11%). Only 2 of 25 dev survivors show a significant drop. | The **ex-ante dev-beta-hedged** return of cluster 122, forward from 2026-10, with its SE. Read it only when the SE is under 1%/month, which takes ~30 more monthly blocks, or pooled (idea 3). |
| 2 | "The books are small-cap tilted; IWM β ≈ 1 is part of each printed alpha" (`03376f6a`) | The random controls load 0.7-0.85, and the random-EW panel's dev CAGR equals IWM's to 0.1 pp. The tilt is the universe. Against the panel, 135 of 282 rules beat it in both windows, not 66. | A random-EW twin column beside SPY on the README and the bridge. The sentence "N rules beat SPY" is replaced by the pair (vs SPY, vs panel). |
| 3 | "282 rules ≈ 180 bets" (`03376f6a`) — and the brief's own expectation that residual clustering lowers it | Residual clustering RAISES the count to 212-216. The count also moves from 79 to 216 with the ρ cut. | Print the cut curve and use the residual count for DSR multiplicity. The DSR of `mom_12_1_q@k20` at n = 216 goes on the receipt. |
| 4 | "Distance-to-default: dev number is 2020 alone" (`615256bd`) | The by-year is decision-keyed. Entry-keyed, 2020 is −3.2% and 2021 is +75.5%. One month, January 2021, is 77× the lifetime log excess. | Entry-keyed `by_year` on every receipt. Then the d2d rule without the top short-interest decile, beside a characteristic-matched twin. If the January 2021 month survives both, it is a mechanism; if not, it is a squeeze. |
| 5 | "VAL-01 is fixed and validated against CRSP" (`615256bd`) | The timing is fixed. The identity is not: a current-ticker map mis-joins or drops 983 dead-since-2016 securities, and a ticker-matched CRSP check cannot see that. | The CCM-linked (`stocknames` + `ccmxpf_lnkhist`) market value. Count the rows whose gvkey changes, and print `qc409` / `qc241` / `qc761` dev excess before and after. |

---

## 7. One thing to delete

**The verdict string "MOSTLY SMH/MTUM BETA" and the `SMH+MTUM share` column**, in
`signal_structure.py`, the tables file and the document. It is a ratio of in-sample contributions
on regressors correlated at 0.69. It prints +97% and −21%, and it gets read as a finding.

Replace it with two numbers per row:

- alpha after the **ex-ante** (dev-fitted) hedge, with its SE;
- the MDE.

A label that cannot tell "beta" from "no power" should not exist.

---

## 8. Three ideas, each with its cost and the observation that separates beta from signal

1. **Ex-ante factor hedge as the standard decomposition.** $0, about 1 hour in `signal_structure`
   and `bridge_report`.
   - Betas come from a trailing 36-month or dev fit and are applied out of window. This is "the
     alpha left after the betas you could have known".
   - **Observation:** the hedged forward monthly return of each cluster, with SE and MDE. A hedged
     return that is positive over time, where the in-window one is zero, is signal that the
     in-window fit had absorbed.
2. **Characteristic-matched random twins,** DGTW-style. $0; the panel already has size, vol_252
   and mom_252.
   - Each book gets a twin drawn from the same size × vol × 12m-return tercile cells as its holdings.
   - **Observation:** book minus matched twin, entry-year keyed, leave-one-year-out. It separates
     "the rule selects" from "the rule buys a style", which neither SPY nor the uniform random
     twin can do.
3. **Pooled family test for power.** $0, one script.
   - Stack the ex-ante-hedged residual returns of the cluster representatives within a family
     (fundamentals, price/volume, analyst). Test the family mean with a month-block bootstrap.
   - Pooling ~15 cluster reps cuts the SE by roughly √(effective n). If effective n is ~4, the
     MDE goes from ~2.5%/month to ~1.2%/month.
   - **Observation:** fundamentals-family hedged alpha minus price/volume-family hedged alpha. This
     is the direct test of the S54 claim that fundamentals rank at +39 bps and price/volume cannot,
     on the library rather than the ranker.

---

## 9. The one-page strategy ("we lack a clear strategy")

### What was measured this week, as an investor reads it

- **The one skill we have is MAGNITUDE:** σ63 beats the LLM at forecasting the size of a move.
  Direction is dead.
- **Brokers are coin flips.** The analyst-skill filter was 2025 alone.
- **Price/volume cannot rank at 21 days.** Fundamentals rank at **+39 bps/month** at k = 20, the
  only positive directional estimate, with an IR of about 0.24 (4.7%/yr on a ~19%/yr tracking
  error). That needs ~70 years to reach 2 SE. It is a tilt, not an edge.
- **Momentum 2024-26 is indistinguishable from the semis regime** (§1). The panel is IWM (§2).
- **Nothing in the library is quotable as alpha.** The forward books are the only record, and the
  first read is 2026-10-26.

### Book A: the Bloomberg Global Trading Challenge (Oct 12 – Nov 13)

**Objective, declared.** Maximise P(top decile) in a **rank tournament**, scored on relative P&L vs
WLS. With no directional edge, the rational bet is **idiosyncratic variance placed where we can
forecast magnitude**, not the crowd's factor bet.

**Construction:**

- **Universe:** WLS small and mid caps with a Q3 print inside the window. The window is Q3 earnings
  season.
- **Rank:** by σ63-predicted absolute event move. Keep the top half by the fundamentals
  composite, which is the only positive directional tilt.
- **Size:** 10 names × 10% each (the brief says ≤ 10%; the verified rule cap is 20%). Fully
  invested in the first business week.
- **Rotation:** once a name has printed, rotate it into the next un-printed name, so the book
  always holds event variance.
- **Crowd cap:** at most 2 semiconductor names. The field is long AI and semis; owning the crowd's
  bet buys the crowd's rank.

**Factor exposure, declared:**

| exposure | declared value |
|---|---|
| β to WLS | ≈ 1.3-1.5 |
| IWM − SPY β | ≈ +1 |
| SMH − SPY β | ≤ 0.3 |
| MTUM | ≈ 0 |

**Expected σ:**

- Name daily σ is ~4%. With an average pairwise ρ of 0.3, book daily σ ≈ 4% × √(0.3 + 0.7/10)
  ≈ **2.4%**.
- Over 24 sessions that is **~12% absolute**, and ~10-11% relative to WLS.
- E[relative] ≈ +0.5% from the tilt, minus ~0.3% in costs, so **≈ 0 ± 11%**. That is honest, and
  the right shape for a fat-tailed tournament.

**Worst case in dollars, protocol item 4:**

- Gross = 10 × 10% = 100%; long only, no leverage.
- One name to zero = −$100k on $1M.
- A 3σ book day ≈ −7%.
- No percent stops (−2% is ~0.5 daily σ here).

**What makes me stop.** At the 10-26 dress-rehearsal read below, if both of these hold:

1. the Spearman rank correlation of predicted vs realised absolute move over the rehearsal's
   printed names is ≤ 0, **and**
2. realised book σ is under 0.5 × predicted, meaning the variance bet did not deliver variance;

then the contest book falls back to a top-quartile construction: 20 × 5% fundamentals-ranked, WLS
β ≈ 1.

### Book B: Murat's own money

**Objective, declared:** terminal wealth, "balanced" personality. There is no demonstrated edge, so
the tilt is paid for as an experiment, not trusted.

| sleeve | holding | what it does |
|---|---|---|
| core 80% | broad index (VT / SPY) | the market; it never stops |
| satellite 20% | the fundamentals-ranked book, k = 25, equal weight, monthly, ≤ 1% of total equity per name | a paid experiment |

**Factor exposure, declared:** total β ≈ 1.0; IWM − SPY ≈ +0.2 (satellite β ≈ 1 × 20%); SMH ≈ 0.

**Expected σ and worst case:**

- Expected σ ≈ 15-16%/yr, the index.
- Tracking error vs the index ≈ 20% × ~19% ≈ **4%/yr**.
- Largest single-name loss at zero = −1% of equity.

**What makes me stop the satellite** (the core never stops): the satellite minus its matched twin
falls below −2 × TE × √(t/12) at any 6-month check; or implementation fidelity breaks (fills,
drift, names ≠ plan). Never on 21 days.

### The observation on 2026-10-26 that tells us it is working

Start Book A as a **paper dress rehearsal on 2026-09-28**, with the exact contest rules, so it has
21 sessions on 10-26, two weeks before the contest opens. On that date the evidence is NOT the
return (a 21-day return is noise at 12% σ). It is three things:

1. **Magnitude calibration.** Spearman(σ63-predicted absolute move, realised absolute move) over
   the rehearsal's and its twin's printed names is ≥ 0.3. This is the one skill the book claims,
   and risk resolves ~30× faster than return (§59).
2. **Declared = realised exposure.** Realised β to IWM and SMH over the 21 sessions is within ±0.3
   of the declared values.
3. **Implementation.** Holdings and fills match the plan.

For Book B, 10-26 checks only (2) and (3).

**Relative P&L gets printed as a z-score and acted on only if z < −2.**

---

## Adjudicator checklist, in the order I would do it

1. Entry-key the factory's `by_year`, `leave_one_year_out` and `loo_worst_*`, and re-print the
   "drop 2025" family of verdicts. This changes past conclusions.
2. Delete the BETA verdict label; add ex-ante-hedge alpha, SE and MDE per row.
3. Add a random-EW twin column beside SPY in the README and the bridge.
4. CCM-link VAL-01; print `n_eligible` per decision date for the value rules.
5. Add the bridge's Level 2 read, starting with the quarterly-offset triplet.
6. Start the Book A rehearsal on 09-28.
