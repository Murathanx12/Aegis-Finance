# Angle 3: Documented After-Cost Strategies Not Yet Tested

*Research pass 2026-09-11. Every effect size below was checked against a primary
source retrieved this session unless explicitly marked UNVERIFIED. Where the
literature documents DECAY, the decay is stated before the headline number,
because for Aegis the decayed number is the only one that is investable.*

**Reading note for a programme that has found every edge to be beta, one era, a
look-ahead, or below the tradability floor:** three of the four failure modes in
that list are *diagnosable in advance* for the families below, and I have marked
each idea with which failure mode is its most likely death. The families that
survive a first pass are (c) options-implied, (d) short-fee, (e) insider
clusters, (g) FOMC/turn-of-month — and each for a different reason. Families
(a) and (b) are mostly **documented as already dead or as capacity-zero for a
sub-$1M retail book**; I report them anyway because *knowing they are dead is
worth a session not spent on them*.

---

## (a) Index / ETF reconstitution and rebalance flows

### a1. S&P 500 index inclusion effect — DOCUMENTED DEAD, do not test
- **Effect size (original):** +3.4%/event in the 1980s, **+7.4% in the 1990s**
  (published version) / 7.6% (WP), +5.1-5.2% in 2000-2009. Deletions
  −4.6% (80s), −16.1% (90s), −12.4% (2000s).
- **Decay:** this is the single best-documented decay in the flow literature.
  **2010-2020 addition effect = +0.8%, statistically indistinguishable from
  zero**; deletion effect = −0.6% (WP) / +0.1% (published). Excluding Tesla's
  Nov-2020 addition, the 2020 average addition effect was **−3 basis points.**
  The authors' estimated demand multiplier M fell **from 6.76 (late 1990s) to
  0.36 (2010s)** — a 20x collapse — i.e. implied demand elasticity −2.76.
  Causes they identify: (i) ~63% of 2010-2020 additions are *migrations* from
  the S&P MidCap, which carry an offsetting demand shock (migration inclusion
  effect went **+6.4% late-90s → +2.7% 2000s → −1.8% 2010s**); (ii) a genuine
  increase in the market's liquidity provision. "Direct" (non-migration)
  additions still earned +5.3% in the 2010s, but that number is driven by Tesla.
- **Capacity:** irrelevant — the post-2010 mean is zero. Even the direct-add
  residual is ~20-25 events/yr, so a retail book gets ~1-2 events/month.
- **Cheapest test on Aegis data:** CRSP through 2024 + an S&P 500 membership
  change list. But **do not run it as a discovery test** — run it as a
  *machine calibration test*: Aegis's event-study harness should reproduce
  Greenwood-Sammon's decade table (+7.4% → +0.8%) on CRSP. If it cannot
  reproduce a known published decay, the harness is what is broken. This is the
  highest-value use of this family: a **planted-world test with a real planted
  effect** rather than a synthetic one.
- **Citation:** Greenwood, R. & Sammon, M., "The Disappearing Index Effect,"
  *Journal of Finance* 80(2): 657-698 (2025); NBER WP 30748 (Dec 2022).
  VERIFIED (NBER abstract + author PDF + Wiley DOI 10.1111/jofi.13410).
  Corroborating decline: Bennett, Stulz & Wang (2020/2022). Contrarian
  companion: Vijh & Wang, *Financial Management* 51:1127-1164 (2022), "Negative
  returns on addition to the S&P 500 index and positive returns on deletion?"

### a2. Russell reconstitution effect — decayed, and the clean identification is gone
- **Effect size (original):** Russell 2000 direct additions earned an average
  **+2.2% (1990s) rising to +8.3% (2000s)** cumulative market-adjusted return
  from the day before the May ranking date to the day after June implementation
  (Greenwood-Sammon Table 8, extending Madhavan 2003 and Petajisto 2011).
  Madhavan (2003) is the canonical reference.
- **Decay:** Greenwood & Sammon apply the same methodology to Russell 1000/2000
  and find "addition and deletion returns have declined over the past decade,"
  but state explicitly: **"For the Russell Index additions, the change is not
  statistically significant."** So: decay is *directionally* documented and
  *statistically unproven* for Russell — an honest "probably decayed, not
  demonstrated." Separately, the **2007 banding rule** cut index switching from
  ~10%/yr (R1000→R2000) and ~6%/yr (R2000→R1000) to ~3% and ~2%, shrinking the
  event count by ~2/3 and — per Ben-David, Franzoni & Moussawi (2019) —
  "precludes the possibility of implementing a fuzzy regression discontinuity
  design because it eliminates any meaningful variation around the cutoff."
- **Capacity:** annual, single-date, ~100-200 tradable names. Reconstitution-day
  volume is among the largest of the year, so *capacity is genuinely large* —
  this is the one flow trade where a $1M book is a rounding error. The binding
  constraint is edge, not capacity.
- **Cheapest test on Aegis data:** you do **not** have Russell membership lists
  (they are a FTSE Russell licensed product), so the direct test is blocked.
  The cheap proxy: CRSP through 2024, reconstruct the **float-adjusted May-31
  market-cap rank** using the Ben-David-Franzoni-Moussawi (2019) ranking recipe
  (PERMCO-aggregated CRSP cap, Compustat fallback — they report a **99.7%**
  assignment-prediction success rate pre-banding), then event-study the
  predicted-addition cohort. Cost: one CRSP pull, no new data. **Flag: this is a
  reconstruction, so a null is ambiguous between "no effect" and "bad ranks."**
- **Citation:** Madhavan, A., "The Russell Reconstitution Effect," *Financial
  Analysts Journal* 59(4): 51-64 (2003), DOI 10.2469/faj.v59.n4.2545. VERIFIED.
  Chang, Hong & Liskovich, "Regression Discontinuity and the Price Effects of
  Stock Market Indexing," *Review of Financial Studies* (2015), DOI
  10.1093/rfs/hhu041 (NBER WP 19290). VERIFIED. Ben-David, Franzoni &
  Moussawi, "An Improved Method to Predict Assignment of Stocks into Russell
  Indexes," *Journal of Investing* (2019), DOI 10.37214/jofweb.1. VERIFIED.

### a3. Month-end "dash for cash" reversal — the strongest flow candidate in family (a)
- **Effect size:** the mechanism is the monthly payment cycle (pensions,
  dividends, fund distributions cluster at month-end; settlement forces the
  liquidating sales to finish 3 business days before). Measured on the CRSP
  value-weighted index since the 1995 adoption of T+3:
  - **T−8 → T−4 (selling pressure): −17 bps raw, −37 bps abnormal**, significant
  - **T−3 → T−1 (reversal): +25 bps abnormal**, significant
  - **T−3 → T+3: +77 bps raw / +48 bps abnormal** per month ≈ **~5.8%/yr raw**
    on ~7 trading days a month of exposure.
  - Conditional amplifier, and this is the part worth having: **the reversal is
    2-3x larger when the last trading day of the month is a Friday** (the
    monthly pension cycle coincides with the weekly salary cycle).
  - Cross-sectional tilt: stocks with high **mutual-fund ownership** show
    monotonically more negative T−8→T−4 and more positive T−3→T−1.
  - 23 international equity markets surveyed; reversals significant in 20.
- **Decay:** **the opposite of decay is documented** — the authors state the
  patterns "have become more pronounced over time" and have "intensified as
  mutual funds' AUM as a proportion of the overall stock market has increased."
  Over 2003-2013 the cumulative excess return in the reversal windows was
  **+103%, i.e. 73% of the entire US market's excess return over the decade**,
  against −31% in the selling-pressure windows. **CAUTION, and this is the
  single most important note in this whole document for family (a): the US
  moved from T+2 to T+1 settlement on 28 May 2024.** The paper's entire date
  geometry (T−3 as "the last settlement day that guarantees month-end cash") is
  derived from the settlement convention, and the authors *prove causality*
  with a difference-in-differences around a European settlement rule change.
  So the 2024 T+1 move should have **shifted the pressure window by ~2 days**
  (T−3 → T−1/T−2), and any naive replay of the published dates on 2024-2026
  data will look like decay when it is actually a *dated* window. Aegis's
  Alpaca 2025-2026 bars are exactly the out-of-sample period where this matters.
  (T+1 date VERIFIED as SEC rule effective 2024-05-28 — but I did not
  re-retrieve a paper measuring the effect post-T+1; **treat the shifted-window
  hypothesis as untested and pre-register it.**)
- **Capacity:** effectively unlimited for a $1M book — it is an index-level
  timing signal implementable in SPY or futures. This is one of very few ideas
  here where a sub-$1M investor has a *structural advantage*: the paper's whole
  point is that the losers are institutions who cannot avoid trading. Round-trip
  cost on SPY is ~1-2 bps, against a 48 bps abnormal window.
- **Cheapest test on Aegis data:** CRSP daily value-weighted index return series
  (already in hand, 1999-2024) → tag each day by business-day-offset from
  month-end → mean abnormal return by offset, split by era AND by
  last-day-is-Friday. **Zero new data, one afternoon.** Then the only new work
  is re-running the offsets under T+1 geometry on the Alpaca 2025-2026 SPY bars.
  **Its most likely death: "one era."** The pre-registration must therefore
  split 1995-2003 / 2003-2013 / 2014-2024 / 2025-2026(T+1) *before* looking.
- **Citation:** Etula, E., Rinne, K., Suominen, M. & Vaittinen, L., "Dash for
  Cash: Monthly Market Impact of Institutional Liquidity Needs," *Review of
  Financial Studies* 33(1) (2020), DOI 10.1093/rfs/hhz054 (SSRN 2528692, first
  posted 2014). VERIFIED (RFS DOI + Aalto full text). Antecedents: Ogden (1990);
  Lakonishok & Smidt (1988); McConnell & Xu (2008).

### a4. Options-expiration pinning (OPEX / "max pain") — real, but too small to trade
- **Effect size:** on each monthly expiration date, optionable stocks' closing
  prices cluster at strike prices; returns are altered by **at least 16.5 bps on
  average per expiration date** (a *lower bound* on |return| deviation, not a
  directional alpha), shifting ≥$9.1bn of market cap per expiration. At least 2%
  of optionable stocks are affected on a typical expiration date; if only that
  2% is affected, the per-affected-name deviation is ~828 bps. Clustering is
  ~2 percentage points above baseline, and *doubles* when market makers hold a
  **net purchased** position in the near-strike expiring options (net written →
  *de-clustering*, price pushed away).
- **Decay:** I could **not verify a post-publication replication or decay
  study** in this pass. FLAG AS UNVERIFIED. The economics argue for decay in the
  manipulation channel (Poteshman-era proprietary-trader data predates
  Reg-NMS-era surveillance) and for *growth* in the hedging channel (0DTE and
  retail option volume have exploded since 2020) — but I have no measurement of
  either. Do not assume the 16.5 bps still holds.
- **Capacity:** the trade is intrinsically small and short-dated; a $1M book
  could execute it, but the edge is a *bound on absolute deviation*, not a
  signed return. **The directional version requires knowing the sign of market
  makers' net position**, which needs CBOE open-interest-by-origin data Aegis
  does not have. The tradable version is more naturally an options trade
  (short straddle at the pinning strike), which drags in the whole options
  execution stack.
- **Cheapest test on Aegis data:** OptionMetrics through 2024 gives strikes and
  open interest; CRSP gives expiration-Friday closes. Compute the fraction of
  optionable names closing within 0.25% of the nearest strike on expiration
  Fridays vs. the four surrounding Fridays, **by year 1996-2024** — that single
  chart answers "has pinning decayed?" and costs one OptionMetrics + CRSP join.
  **It is a good machine-calibration target and a bad trade.**
- **Citation:** Ni, S.X., Pearson, N.D. & Poteshman, A.M., "Stock price
  clustering on option expiration dates," *Journal of Financial Economics*
  78(1): 49-87 (2005), DOI 10.1016/j.jfineco.2004.08.005. VERIFIED. Mechanism
  model: Avellaneda, M. & Lipkin, M., "A market-induced mechanism for stock
  pinning," *Quantitative Finance* 3(6): 417-425 (2003). VERIFIED (cited in JFE
  reference list).

**Family (a) verdict:** one idea worth a session — **a3, the month-end reversal
with the T+1-shifted window** — and it is worth it because the mechanism is a
*payment calendar*, not a risk premium, and because the 2024 settlement change
gives a genuine out-of-sample natural experiment that nobody has published on
yet. a1 and a4 are worth running **as harness calibration**, not as alpha. a2 is
blocked on licensed data.

---

## (g) Seasonal / calendar effects — taken out of order, because (g) is where the *decay* evidence is cleanest

### g1. Pre-FOMC announcement drift — DOCUMENTED DEAD SINCE ~2015/2016
- **Effect size (original):** **+49 bps in the 24 hours before a scheduled FOMC
  announcement**, Sep 1994 – Mar 2011, on the S&P 500. The authors state this
  accounts for **~80% of the annual equity realised return** over the sample.
  No comparable effect in Treasuries, money-market futures, or around other
  major US macro announcements — which is what made it a puzzle rather than a
  risk premium.
- **Decay — three independent confirmations, and this is the single clearest
  "published-then-arbitraged" case in the whole document:**
  1. **Boguth, Gregoire & Martineau (2019):** post-April-2011 the drift exists
     **only** before announcements *with* a Chair press conference; zero for
     announcements without.
  2. **Kurov, Wolfe & Gilbert, "The disappearing pre-FOMC announcement drift"**
     (extending to Dec 2019): even the press-conference drift collapsed —
     **+44.5 bps (Apr 2011–Dec 2015) → +9.2 bps (Jan 2016–Dec 2019)**, and a
     Wilcoxon rank-sum test rejects equal central tendency at 1%. Against
     non-announcement days (+5.4 bps) the post-2016 drift is **statistically
     indistinguishable from an ordinary day.** They attribute it to reduced
     uncertainty (the effect loads on VIX, and the post-ZLB dummy loses
     significance once VIX is in the regression).
  3. **Ben Dor & Rosa (2019):** no pre-FOMC drift at all Apr 2011 – Dec 2017.
  4. An independent student replication (Kugelberg & Hjärne, SSE 2019) finds
     SPX pre-FOMC excess return **0.323% (1994-2015) → 0.055% (2015-2019)** and
     OMX30 **0.536% → 0.023%** — i.e. the erosion is not US-specific and is
     dated to the publication.
- **Capacity:** would have been enormous (index-level, 8 events/yr, SPY). Moot.
- **Cheapest test on Aegis data:** **do not test it as alpha.** Test it as the
  programme's *canonical decay case study*: CRSP daily + a scheduled-FOMC-date
  list (free, federalreserve.gov) → the 1994-2011 / 2011-2015 / 2016-2024 split.
  If Aegis's era-splitting machinery cannot reproduce "+49 bps → ~0 with the
  break at the publication date," the machinery is not yet trustworthy. It is a
  **free, publicly-documented ground truth for the exact failure mode Aegis
  keeps hitting** ("one era"), and it costs one date list.
  **There is a live conditional question the literature leaves open and Aegis
  could actually ask:** Kurov et al. show the drift loads on **VIX**, and their
  closing sentence explicitly asks whether COVID-era uncertainty revived it.
  Nobody in what I retrieved has answered that for 2020-2024. Aegis has CRSP to
  2024 and Alpaca to 2026. **Conditional hypothesis: the pre-FOMC drift is a
  function of ex-ante uncertainty, not of the calendar — it should reappear in
  high-VIX FOMC meetings (2020, 2022) and be absent in low-VIX ones.** That is
  a *scope-aware* question of exactly the shape the project charter asks for,
  and a global negative (g1 is dead) does not answer it.
- **Citation:** Lucca, D.O. & Moench, E., "The Pre-FOMC Announcement Drift,"
  *Journal of Finance* 70(1): 329-371 (2015), DOI 10.1111/jofi.12196. VERIFIED.
  Decay: Kurov, A., Wolfe, M. & Gilbert, T., "The disappearing pre-FOMC
  announcement drift," *Finance Research Letters* (2021 — PMC7525326), VERIFIED
  (full text retrieved). Boguth, Gregoire & Martineau (2019). Ben Dor & Rosa
  (2019).

### g2. Turn-of-the-month effect — see a3; it is the same mechanism
The classic turn-of-month literature (Ogden 1990; Lakonishok & Smidt 1988;
Cadsby & Ratner 1992; McConnell & Xu 2008) documents abnormally high returns
from the last business day through T+3. Etula et al. (2020) **supersede** it by
identifying the payment-cycle mechanism and the *reversal* structure around it,
which is both larger and conditional (Friday month-ends, high-mutual-fund-
ownership names). Treat a3 as the modern form; do not test the 1988 version.
**Decay: documented as strengthening, not decaying, through 2013.** Untested
post-T+1-settlement (2024).

### g3. Pre-holiday effect — LOW PRIORITY, decay not verified
I did not retrieve a primary source or a decay study for the pre-holiday effect
in this pass. **UNVERIFIED — do not act on memory.** Prior expectation: it is a
1980s-vintage calendar anomaly of the same family as the weekend effect and the
January effect, most of which have been shown to shrink post-publication
(the canonical general treatment is McLean & Pontiff 2016, below). Cheapest
test if it is ever wanted: CRSP daily index return, one dummy, split by decade —
but the prior is low enough that it is not worth a pre-registration slot ahead
of a3 or g1's conditional form.

**Family (g) verdict:** the FOMC drift is dead as alpha and **extremely
valuable as a harness calibration + one live conditional (VIX-conditional
revival).** Turn-of-month (= a3) is the family's only live trade.

---

## (c) Options-implied information — the family with the most evidence AND the most documented decay

**Read c1-c4 as one story.** The literature has converged on an uncomfortable
joint finding: (i) the classic option-implied signals decayed hard after ~2008,
(ii) a large part of the *pre*-2008 performance was a **non-synchronous
timestamp look-ahead**, and (iii) most of what remains is the **stock borrow
fee** in disguise — which a long-only retail investor cannot monetise but *can*
use as an avoidance rule. This is the exact triple (decay + look-ahead + hidden
factor) that Aegis has hit repeatedly on its own signals; here it is already
documented by other people, which makes it cheap to learn from.

### c1. Implied-volatility skew / "smirk" (Xing-Zhang-Zhao) — DECAYED, and partly a look-ahead
- **Effect size (original):** SKEW = IV(OTM put) − IV(ATM call). Steepest-smirk
  stocks underperform flattest by **10.90%/yr risk-adjusted (FF3 alpha)**,
  1996-2005. Over 90% of optionable firm-observations show a positive smirk,
  median OTM-put-minus-ATM-call ≈ **5 vol points**. Predictability persists ≥6
  months; steepest-smirk firms have the worst next-quarter earnings shocks.
  **Read the fine print the abstract omits:** the 10.90% is a **decile spread at
  a ONE-WEEK holding period**; extend the holding period to 4 weeks and it falls
  to **6.52%**. The Fama-MacBeth interquartile-range implication is only
  **−4.41%/yr**. So the honest pre-cost number for a monthly-rebalanced book is
  ~6.5%/yr on a top-minus-bottom decile, not 10.9%.
- **Decay:** severe and documented twice over.
  1. **"Better Opt Out? Revisiting the Predictive Power of Options-Implied
     Signals"** (*Journal of Portfolio Management*, Nov 2025; SSRN 4766424)
     runs a suite of options-implied signals 1996-2021. Combined long-short
     strategy: **Sharpe 1.18 (1996-2008) → 0.16 (2009-2021)**; annualised alpha
     **11.40% → 1.56%, losing statistical significance.** Individual signals:
     dP−dC Sharpe **1.07 → 0.06**; CPIV, IVSKEW, VOLOFVOL show the same collapse.
     Robust to value- vs equal-weighting (1.39 → 0.17), rebalancing frequency,
     six different IV-surface aggregation methods, and market-cap screens.
  2. **The look-ahead.** The same paper identifies a **measurement bias: options
     prices are recorded up to 10 minutes AFTER the stock market close.** Sorting
     on same-day option data therefore uses information not available at the
     stock close. Adding a **one-day implementation lag** cuts the 1996-2008
     COMB Sharpe from **1.18 → 0.69**, and turns POMA, QSKEW and **IVSKEW
     negative**. Post-2008 the lag barely matters (the timestamp problem is
     gone). **This is a textbook instance of Aegis's own recurring failure mode,
     found in the published literature, and it is directly relevant because
     OptionMetrics is exactly the dataset in which the bias lives.**
- **Capacity:** moot for the decayed version. Note it was always a *high-turnover
  decile long-short on optionable stocks*, so realistic capacity is modest and
  transaction costs bite hard — the JPM paper's "breakeven transaction cost"
  metric is the right lens (>30 bps pre-2008; far lower after).
- **Cheapest test on Aegis data:** **OptionMetrics through 2024 is exactly the
  right dataset and the test is nearly free**: build IVSKEW monthly, run the
  decile spread with (a) no lag and (b) a one-day lag, split 1996-2008 /
  2009-2021 / **2022-2024 (the years the JPM paper does not cover)**. Two of the
  four cells are already published, so Aegis gets a **replication check on its
  own harness for free**, and the 2022-2024 cell is genuinely new information.
  **Most likely death: already dead.** Expected value is in the harness
  calibration and the 2022-2024 extension, not in finding alpha.
- **Citation:** Xing, Y., Zhang, X. & Zhao, R., "What Does the Individual Option
  Volatility Smirk Tell Us About Future Equity Returns?" *Journal of Financial
  and Quantitative Analysis* 45(3): 641-662 (2010), DOI
  10.1017/S0022109010000220. VERIFIED. Decay + look-ahead: "Better Opt Out?
  Revisiting the Predictive Power of Options-Implied Signals," *Journal of
  Portfolio Management* 52(1) (Nov 2025), SSRN 4766424. VERIFIED (full text
  retrieved; **author names were not in the retrieved PDF header — I could not
  confirm authorship this pass. FLAG.**)

### c2. Implied-volatility innovations (An-Ang-Bali-Cakici) — same family, same decay
- **Effect size:** decile portfolios on the previous month's **change in call
  implied vol (dCVOL)** produce a **1.09%/month raw spread (t 3.45)**; the FF3
  alpha spread is **1.36%/month (t 5.22)**; annualised Sharpe of the long-short
  ≈ **0.90**. Put side: dPVOL spread >1%/month between extreme deciles,
  ~60 bps after controlling for calls. Persists up to 6 months (calls) /
  4 months (puts). Reverse direction also holds: a 1% CAPM alpha raises
  next-month call IV by ~3-4%.
  Notably the authors emphasise it **survived the 2008-09 crisis** when many
  cross-sectional strategies reversed — which is precisely the claim the 2025
  JPM paper overturns on later data.
- **Decay:** covered by the same "Better Opt Out?" result — An et al. (2014) is
  explicitly in its reference set, and its dP−dC-family signals are the ones
  whose Sharpe goes 1.07 → 0.06. **The 2014 "it survived the crisis" claim did
  not survive the decade after publication.**
- **Capacity:** monthly-rebalanced decile long-short on optionable names; the
  short leg concentrates in hard-to-borrow small caps (see c3/d1), which is
  exactly where a sub-$1M account cannot get a locate at a sane rate.
- **Cheapest test:** identical OptionMetrics pull to c1 — build dCVOL/dPVOL from
  the same surface file and add them as two more columns in the same
  era × lag grid. **Marginal cost of testing c2 given c1 is ~zero**, which is the
  argument for running them as one pre-registration rather than two.
- **Citation:** An, B.-J., Ang, A., Bali, T.G. & Cakici, N., "The Joint Cross
  Section of Stocks and Options," *Journal of Finance* 69(5): 2279-2337 (2014),
  DOI 10.1111/jofi.12181 (NBER WP 19590). VERIFIED.

### c3. THE ONE THAT MATTERS: the option-implied borrow fee — a FREE synthetic short-fee panel
- **Effect size / the result:** Muravyev, Pearson & Pollet show the option
  implied-volatility spread is, to first order, **proportional to the stock
  borrow fee h**, because the borrow fee enters put-call parity exactly as a
  continuous dividend does. Inverting their Taylor expansion gives an estimator
  (their Eq. 7) for h from the **30-day, ±0.50-delta call and put implied vols
  on the OptionMetrics smoothed IV surface** (the kernel smoother is what makes
  it usable — raw bid-ask-midpoint IVs are too noisy). In their worked example
  the 5-day moving average of the implied fee **tracks the Markit borrow fee
  very closely** for Tesla. The headline: **abnormal return predictability from
  option signals falls by about two-thirds once returns are adjusted for borrow
  fees**, and by a similar amount if high-fee stocks are simply excluded — even
  though only **~7% of observations are high-fee**. The residual "does not
  survive adjusting for reasonable estimates of institutional transactions
  costs." Their portfolio-10 (highest fee) abnormal return is **−0.80%/month
  (t −4.3)**, while portfolio 9 is **−0.02%/month (t −0.6)** — i.e. the entire
  effect is in the top decile, and mostly in the top *half* of that decile.
- **Decay:** wrong frame — this is a structural accounting identity, not an
  anomaly, so the *measurement* does not decay. But the paper is deflationary:
  it explains c1/c2 away rather than adding an edge. Their 2022 JF paper
  separately finds the borrow-fee **risk premium** is small and that borrow-fee
  risk does **not** predict fee-adjusted returns — so do not build a "shorting
  risk premium" story on top of it.
- **Capacity:** as a *signal source*, unlimited (it is data, not a trade). As a
  *trade*, it is the shorting premium (d1), which is capacity-bounded by the
  lending market and, for the top decile, by borrow availability.
- **Cheapest test on Aegis data — MY SINGLE HIGHEST-CONVICTION RECOMMENDATION
  IN THIS DOCUMENT:** Aegis has **OptionMetrics through 2024**, so it can build
  a **free 1996-2024 synthetic stock-borrow-fee panel** from Eq. (7) on the
  30-day ±0.50-delta surface. This directly satisfies the user's stated
  constraint for family (d) — "FREE data sources only, no paid short-locate
  feeds" — because **the borrow fee has been sitting inside a dataset Aegis
  already licenses, for 28 years, and no part of the programme has used it.**
  Validation is cheap and falsifiable: the implied fee should be ~0 for ~93% of
  names and large for a ~7% special-collateral tail; cross-check the tail
  against the *free* FINRA / exchange **semi-monthly short-interest** series and
  against known squeeze episodes. **Most likely death: the tail is small,
  illiquid and un-borrowable** — so pre-register the existing `TRADABLE_DOLLAR_VOL`
  floor and a borrow-availability assumption BEFORE looking at returns.
- **Citation:** Muravyev, D., Pearson, N.D. & Pollet, J.M., "Is There a Risk
  Premium in the Stock Lending Market? Evidence from Equity Options," *Journal
  of Finance* 77(3): 1787-1828 (June 2022), DOI 10.1111/jofi.13129. VERIFIED.
  The "option predictability IS the borrow fee" result is the same authors'
  companion paper (working version retrieved via FMAI Derivatives 2022;
  **published venue not confirmed this pass — FLAG**). Index-level analogue:
  "Do Option Prices Forecast Aggregate Stock Returns?" SSRN 3009490 — the
  aggregate implied-vol spread forecasts market returns at 1-6 months with ~5%
  monthly in- and out-of-sample R², and the authors also conclude it is
  **stock-lending-fee expectations**, explicitly rejecting informed-option-trading,
  time-varying-risk-premia and illiquidity explanations. VERIFIED (abstract).

### c4. Option order flow died on a DATE — a design lesson, not a trade
- **Effect size:** the put-call ratio and related option order-flow aggregates
  "used to strongly predict future stock returns."
- **Decay:** the predictability **"suddenly and permanently ceased after October
  2009,"** coinciding with the arrest of Raj Rajaratnam and the ensuing
  insider-trading enforcement campaign. The authors' reading: the predictability
  *was* insider trading in the options market.
- **Capacity / test:** Aegis has no option volume-by-origin data, so the direct
  test is blocked. **The value is methodological:** an edge can die on a
  calendar date for an *enforcement* reason with no gradual decay to warn you.
  Any Aegis pre-registration touching options or insider flow should include a
  **structural-break test at known enforcement / regulation dates**, not only
  even era splits. (This matters for family (e) too — see e2.)
- **Citation:** "What information do informed traders use?" SSRN 4150768.
  **UNVERIFIED — abstract only; authorship and venue not confirmed. FLAG.**

### c5. Earnings-day straddle overpricing / IV crush — NOT ADEQUATELY VERIFIED
I did not retrieve a primary source measuring **after-cost** returns to selling
straddles into earnings. The adjacent verified result is Govindaraj, Li & Zhao,
*Journal of Business Finance & Accounting* 47(5-6): 615-644 (2020): strategies
on option-implied predictors around earnings earn **1.39%-1.91% monthly abnormal
returns**, and the paper's central finding is that the predictability is
"significantly stronger for firms with **lower option relative bid-ask
spreads**" and absent on randomly chosen non-event dates. That conditionality
*is* the capacity answer: the edge lives where option spreads are narrow.
**Treat "earnings straddles are systematically overpriced net of costs" as
UNVERIFIED.** If Aegis pursues it, the cost model must use the **quoted option
bid-ask spread per contract**, never a flat bps assumption — otherwise it will
reproduce the 2026-09-10 C2 flat-100-bps artefact in a market where spreads are
an order of magnitude wider than equities.
- **Citation:** Govindaraj, S., Li, Y. & Zhao, C., "The effect of option
  transaction costs on informed trading in the options market around earnings
  announcements," *Journal of Business Finance & Accounting* 47(5-6): 615-644
  (2020). VERIFIED (abstract).

**Family (c) verdict:** do **one** OptionMetrics project, not five. Build the
**implied-borrow-fee panel (c3)** — it creates a *new free dataset* rather than
re-testing a dead signal — and take c1/c2's era × lag grid as a by-product of
the same data pull. Expect c1/c2 to be dead; their value is harness calibration
plus the un-published 2022-2024 cell.

---

## (d) Short-interest and securities-lending signals — FREE DATA, and the best long-only fit in this document

**Correction to the brief:** the paper the task names as "Drechsler & Drechsler
2014" is **"The Shorting Premium and Asset Pricing Anomalies"** by *Itamar
Drechsler and Qingyi Freda (Song) Drechsler*, NBER WP 20282 (July 2014), later
*Review of Financial Studies*. VERIFIED. It is about the **short-rebate fee**,
not short interest, and it requires a paid lending-fee feed — which is exactly
why c3 (deriving the fee from OptionMetrics) matters.

### d1. The shorting premium (Drechsler & Drechsler) — real, large, and NOT accessible to this book
- **Effect size:** sorting on short-rebate fee, the **cheap-minus-expensive
  (CME)** portfolio earns **+1.43%/month gross, +0.91%/month net of fees**, and a
  **four-factor alpha of +1.53%/month (t 7.06)**. Returns are **flat across the
  eight cheap-to-short deciles** and collapse only in deciles 9-10; decile 10
  earns **−0.68%/month** and its FF4 alpha is **−1.42%/month**. The upper half
  of decile 10 ("10b"): cheap-minus-10b = **+2.14%/month, alpha +2.28%.**
  The second, more important finding: **eight of the largest known anomalies
  effectively disappear inside the 80% of stocks with low short fees and are
  greatly amplified among high-fee stocks**; an FF4+CME factor model kills
  seven of the eight (idiosyncratic vol goes from a 1.21%/mo FF4 alpha to an
  insignificant 0.07%).
- **Decay:** I did **not** retrieve a post-publication replication measuring the
  shorting premium after ~2014. **FLAG AS UNVERIFIED DECAY.** Two structural
  reasons to expect attenuation on the short leg specifically: (i) the 2021
  retail-squeeze episodes raised the cost and risk of crowded shorts; (ii) the
  Muravyev-Pearson-Pollet result that the residual "does not survive adjusting
  for reasonable estimates of institutional transactions costs."
- **Capacity:** **the honest answer is that for Aegis this is near zero.** The
  entire premium lives in the top decile of borrow fee — small, illiquid,
  hard-to-locate names where a retail Alpaca account either cannot borrow at all
  or pays a rate far above the institutional fee the paper nets out. The *long*
  leg (cheap-to-short deciles 1-8) is **flat**, so there is no long-only version
  of d1. **Its real use is as a FILTER, not a trade.**
- **Cheapest test on Aegis data:** the version that costs nothing and answers a
  live question — take the **implied borrow fee from c3** (OptionMetrics
  1996-2024), form the high-fee decile, and check whether **excluding it changes
  Aegis's own historical results.** The Drechsler finding predicts that seven of
  eight classic anomalies should weaken inside Aegis's low-fee 80% and strengthen
  in the high-fee tail. If any Aegis signal's historical edge concentrates in the
  un-borrowable tail, **that is a new named failure mode for the corpses list**
  alongside "beta, one era, look-ahead, below the floor" — call it
  **"it was the borrow fee."**
- **Citation:** Drechsler, I. & Drechsler, Q.F.S., "The Shorting Premium and
  Asset Pricing Anomalies," NBER WP 20282 (2014), DOI 10.3386/w20282 / SSRN
  2387099. VERIFIED (NBER + SSRN; note the SSRN and NBER abstracts quote
  slightly different numbers — 1.31%/0.78%/1.44% vs 1.43%/0.91%/1.53% — across
  draft vintages, so **quote the version you actually replicate against**).

### d2. **Low short interest, high turnover — the long-only signal, on FREE data. Best fit in this document.**
- **Effect size:** Boehmer, Huszár & Jordan find that the informative side of
  short interest is the side nobody trades: **relatively heavily traded stocks
  with LOW short interest earn statistically and economically significant
  POSITIVE abnormal returns, often larger in absolute value than the negative
  returns on heavily shorted stocks.** Practitioner summary of their tables:
  alpha ≈ **+1%/month for the low-short-interest leg** vs ≈ **−0.50%/month** for
  the high leg; long-only portfolio raw return ~2%/month with ~1.3%/month alpha;
  long-short ~1.5%/month raw, ~1.6%/month alpha, 1988-2005. Robust to portfolio
  weighting, formation timing, risk-adjustment, listing venue, new-listing
  exclusion, and dropping 1998-2000. **The alpha survives a holding period of up
  to six months** — i.e. it is a *low-turnover* signal, which is the single most
  important property for a small book paying retail spreads.
  (**Caveat: the 1%/month decomposition and the long-only 1.3% figure come from
  a practitioner write-up of the tables (Alpha Architect, 2011), not from the
  abstract. Verify against the JFE tables before pre-registering a number.**)
- **Decay:** **UNVERIFIED — I found no replication extending past 2005.** This is
  the biggest open question on the best idea in this document, and it is also
  the cheapest one for Aegis to answer, because the data are free and CRSP runs
  to 2024. Prior: McLean & Pontiff (2016) find published anomalies decay ~58%
  post-publication on average; the paper published in 2010, so assume material
  decay and let the data speak.
- **Capacity:** **large, and uniquely suited to a sub-$1M long-only book.**
  It is a long-only tilt among *heavily traded* (i.e. liquid) names, held up to
  six months. There is no borrow, no locate, no options leg, no daily turnover.
  A $1M book is invisible. **This is the only idea in this document where the
  retail constraint set is not a handicap.**
- **The ONE cheapest test on Aegis's actual data:** **FINRA + NYSE/Nasdaq
  semi-monthly short-interest files are FREE and public**, and CRSP gives
  shares outstanding, turnover and returns through 2024. Form monthly
  double-sorted portfolios on (short interest / shares outstanding) × turnover;
  take the **low-SI / high-turnover** cell long-only; measure FF3/FF4 alpha AND
  raw return vs SPY, **split 1988-2005 (in-sample of the paper) / 2006-2010
  (pre-publication OOS) / 2011-2024 (post-publication)**. The three-cell split
  is the whole experiment: it separates "it was real and decayed" from "it was
  never real" from "it still works." Costs one free download and a CRSP join.
  **Most likely death: post-publication decay** — which is why the era split
  must be pre-registered and the 2011-2024 cell must be the primary metric.
- **Citation:** Boehmer, E., Huszár, Z.R. & Jordan, B.D., "The good news in
  short interest," *Journal of Financial Economics* 96(1): 80-97 (2010).
  VERIFIED (JFE / RePEc / SMU repository; SSRN 971044).

### d3. Days-to-cover (short interest ÷ turnover) — better than short interest, but it is the SHORT leg again
- **Effect size:** DTC = short ratio / average daily share turnover ≈ the
  marginal cost of the arbitrageur's short, so it proxies overvaluation better
  than the raw short ratio. **Equal-weighted long-low-DTC / short-high-DTC earns
  1.19%/month (t 6.67)** vs **0.71%/month (t 2.57)** for the same strategy on
  short ratio. **Value-weighted: DTC 0.67%/month and significant; short ratio
  0.29%/month and insignificant** — the SR effect is a small-cap effect, the DTC
  effect is not. Fama-MacBeth: DTC t −9.55 vs SR t −5.77; in a head-to-head the
  SR coefficient halves and drops to 10% significance while DTC is unchanged.
  One-sd spread: DTC 0.25%/month vs SR 0.16%/month. Sub-sample note the authors
  make explicitly: **SR loses all significance post-2000 while the DTC
  coefficient is identical in both sub-samples** — an early, author-supplied
  decay result on the older measure. The authors also state the **DTC effect is
  distinct from the stock-lending-fee effect** with comparable forecasting power
  — which matters because it means DTC is *not* just d1 in disguise.
- **Decay:** sample runs 1988-2012. **No post-2012 replication retrieved —
  UNVERIFIED.** The authors' own pre/post-2000 split is the only decay evidence
  in hand and it favours DTC.
- **Capacity:** the long leg (low DTC) is liquid and long-only implementable;
  the short leg is crowded by construction — DTC *is* a crowdedness measure, and
  the paper frames it as the cost of exiting a crowded trade. **So take the long
  leg and the avoidance rule; skip the short leg.**
- **Cheapest test on Aegis data:** **free — it is d2's test plus one column.**
  DTC needs only the same free short-interest file divided by CRSP turnover.
  Run d2 and d3 in the same pre-registration with the same era split; the
  incremental cost of d3 given d2 is one line of code, and the head-to-head
  (does DTC beat SR out-of-sample post-2012?) is a genuinely open question.
- **Citation:** Hong, H., Li, F.W., Ni, S.X., Scheinkman, J.A. & Yan, P., "Days
  to Cover and Stock Returns," NBER WP 21166 (2015), DOI 10.3386/w21166 / SSRN
  2568768. VERIFIED. (The SSRN version is retitled around *crowded trades* and
  uses staggered decimalization reforms as an instrument — same 1.2%/month.)

### d4. Utilization rate — BLOCKED, and say so rather than proxying badly
Utilization (shares on loan ÷ lendable supply) requires a securities-lending
feed (Markit/IHS, S3, Ortex) — all paid, none free. **There is no free proxy
that preserves the denominator**, and the numerator alone is just short
interest (d2/d3). The *only* free-ish route is the **option-implied fee (c3)**,
which estimates the *price* of borrow rather than the *quantity*. Report this as
blocked; do not build a fake utilization column.

**Family (d) verdict — and this is the practical bottom line of the whole
document:** **d2 + d3 in one pre-registration is the highest expected-value
next experiment available.** Free data, long-only, low turnover, liquid names,
capacity far above $1M, a published effect larger than most, and a cleanly
specified decay question that nobody in the retrieved literature has answered
past 2012. d1 is a **filter** ("was my edge the borrow fee?"), not a trade.
d4 is blocked.

---

## (e) Insider cluster buys with size / role weighting — Aegis already owns the data

Aegis has **11.5M SEC Form-4 rows**. Every number below is computable from that
table plus CRSP, with **no new data acquisition at all**. That makes (e) the
cheapest family in this document to test and the one where Aegis's existing
asset is closest to the research frontier.

### e1. Cluster purchases (multiple insiders, same direction, consecutive days)
- **Effect size:** Kang, Kim & Wang, on **1986-2016 US Form-4 data**, find **over
  40% of insider trades are clustered**. Purchases:
  - 5-day horizon: **cluster +2.06% vs non-cluster +1.09%** abnormal
  - **21-day: cluster +3.80% vs non-cluster +1.95%** (roughly double)
  - **90-day: cluster +6.41% vs non-cluster +3.95%** (gap widens to ~2.5pp)
  - Transaction-date price impact: cluster **+0.51%** vs non-cluster **+0.25%**
  - Firm-fixed-effects regression: cluster purchases predict **+1.67%** more
    than non-cluster.
  - **Role weighting is measured**: cluster purchases placed exclusively by
    **executives** predict **+1.11%** over non-cluster executive purchases;
    director-only clusters are weaker. Executives' trades are more informative.
  - **The cluster LENGTH is the strongest conditioner, and it is the part worth
    building:** post-SOX, clusters spread over **4-5 consecutive days** are
    followed by **>5% higher BHAR(22,90)** than non-cluster purchases — i.e.
    return that accrues *after* public disclosure — whereas **same-day clusters
    yield 0.72% LOWER** BHAR(22,90) than non-cluster. Same-day clusters get
    priced immediately; slow multi-day clusters do not.
  - **Cluster SALES are uninformative** (the authors attribute it to blackout
    windows and common vesting dates). Do not build a short leg.
  - Orthogonality: cluster purchases carry **novel information relative to
    Cohen-Malloy-Pomorski "opportunistic" trades** — clusters containing
    opportunistic trades beat non-cluster opportunistic purchases by +1.11%, and
    with firm fixed effects the opportunistic-vs-routine advantage *washes out*
    while the cluster effect strengthens. **So cluster ≠ opportunistic; they
    are complementary identifiers.**
- **Decay:** sample ends 2016. **NO post-2016 replication retrieved —
  UNVERIFIED.** The paper's own pre/post-**SOX** split is the only structural
  break tested, and SOX (2-business-day Form-4 filing) *strengthened* the
  disclosure-date reaction while leaving the long-horizon drift on slow clusters
  intact. Corroboration on an overlapping sample: Alldredge & Blank, *Journal of
  Financial Research* 42(2): 331-360 (2019), 1986-2014 daily Form-4 data —
  **clustered insider purchases followed by abnormal returns in excess of 2%
  over the subsequent month**, clustering strongest during **low investor
  attention, high uncertainty, high information asymmetry.**
- **Capacity:** good for a small book and bad for a large one, which is the right
  direction for Murat. Insider purchases concentrate in small and mid caps; a
  $1M book can take a full position in nearly every signal, a $1bn book cannot.
  Horizon is 21-90 days → **low turnover**. Constraint is the tradability floor
  (already in the codebase), not market impact.
- **The ONE cheapest test on Aegis's actual data:** Aegis's **11.5M Form-4 rows
  + CRSP returns through 2024**, nothing else. Define a cluster as ≥2 distinct
  insiders, same firm, same direction, within N consecutive trading days
  (N = 1..5); **restrict to open-market PURCHASES** (transaction code P — this
  is the single most common implementation error, since option exercises and
  vesting dominate the raw row count); compute BHAR(22,90) from the **filing
  date**, not the transaction date; and **split by cluster length**, because
  the published result says same-day and 4-5-day clusters have *opposite* signs.
  Then the only genuinely new cell — the one nobody has published — is
  **2017-2024**, plus a 2025-2026 forward check against Alpaca bars.
  **Most likely death: "below the tradability floor"** (insider buys cluster in
  micro-caps), so apply `TRADABLE_DOLLAR_VOL` **before** computing any return,
  and report the pre- and post-floor name counts in the receipt.
- **Citation:** Kang, C.-M., Kim, D. & Wang, Q., "Cluster Trading of Corporate
  Insiders," working paper (Nov 2018; UNSW / UW-Milwaukee / UCF; presented CAFM
  2018). **VERIFIED as to authorship and content (full PDF retrieved), but it
  appears to remain an UNPUBLISHED working paper — FLAG: no peer review.**
  Alldredge, D.M. & Blank, B., "Do Insiders Cluster Trades With Colleagues?
  Evidence From Daily Insider Trading," *Journal of Financial Research* 42(2):
  331-360 (2019). VERIFIED (peer-reviewed; use this one for any RESEARCH_CLAIM).

### e2. Opportunistic vs routine insiders (the control you must run alongside e1)
- **Effect size:** Cohen, Malloy & Pomorski strip out "routine" insiders (those
  who traded in the same calendar month for ≥3 consecutive years — **over half
  the entire universe of insider trades**). The remaining "opportunistic" trades
  carry **all** the predictive power: long-short opportunistic buys-minus-sells
  earns **82 bps/month value-weighted (9.8%/yr, t 2.15)** and **180 bps/month
  equal-weighted (21.6%/yr, t 6.07)**; the routine mimic earns **−20 bps/month
  VW (t −0.57)**. A 1-sd increase in log opportunistic buys → **+35 bps/month
  (t 4.56)**; opportunistic sells → **−29 bps (t 4.97)**; routine trades ≈ 0.
  Most informed: **local, non-executive insiders at geographically concentrated,
  poorly governed firms.**
- **Decay — and this is a *mechanism* for decay, not just a measurement:** the
  authors themselves report that **opportunistic traders are significantly more
  likely to face SEC enforcement action and REDUCE their trading following waves
  of SEC insider-trading enforcement.** Combined with c4 (option-flow
  predictability ceasing permanently in October 2009 with the Rajaratnam
  campaign), there is a coherent, testable story: **enforcement intensity is a
  regime variable for every insider-information signal.** No post-2012
  replication retrieved — **decay UNVERIFIED**, but the *direction* is
  predictable and Aegis can measure it.
- **Capacity:** as e1; VW 82 bps vs EW 180 bps is itself the capacity statement —
  **more than half the effect is in small names.** Quote the VW number when
  sizing, the EW number never.
- **Cheapest test:** it is one extra column on e1's pull. Classify each insider
  routine/opportunistic from the prior 3 years of the same Form-4 table, then
  run the **2×2 of {cluster, non-cluster} × {opportunistic, routine}** — Kang et
  al. predict the cluster dimension survives firm fixed effects and the
  opportunistic dimension does not. **Testing the 2×2 rather than either signal
  alone is what makes this a mechanism test rather than another factor.**
  Add an explicit structural-break test at **SOX (Aug 2002)** and at
  **Oct 2009 (Rajaratnam)**.
- **Citation:** Cohen, L., Malloy, C. & Pomorski, L., "Decoding Inside
  Information," *Journal of Finance* 67(3): 1009-1043 (2012), DOI
  10.1111/j.1540-6261.2012.01740.x (NBER WP 16454). VERIFIED.
  Baseline: Jeng, L., Metrick, A. & Zeckhauser, R., "Estimating the Returns to
  Insider Trading: A Performance-Evaluation Perspective," *Review of Economics
  and Statistics* 85(2): 453-471 (2003), DOI 10.1162/003465303765299936 —
  **insider PURCHASES earn abnormal returns of more than 6%/yr; insider SALES
  earn nothing significant.** VERIFIED. That asymmetry (buys informative, sells
  not) is confirmed independently by Kang et al. and is the one thing in this
  family that every paper agrees on.

**On the brief's "2025 3.7M-transaction composite":** I found no public
large-scale insider-cluster study matching that description, and I could not
verify it. Either it is an internal Aegis artefact or a vendor claim. **Do not
cite it as literature.** The retrievable public frontier on cluster buying is
Kang-Kim-Wang (1986-2016, unpublished) and Alldredge-Blank (1986-2014, JFR).

**Family (e) verdict:** **the second-highest expected-value family, and the
cheapest.** Aegis owns the data; the frontier result (cluster length flips the
sign of post-disclosure drift) is specific, falsifiable, and unpublished past
2016; and the 2×2 against opportunistic/routine is a genuine mechanism test
rather than another composite weight. Run it as its own `PRODUCT_EXPERIMENT`
book, per the repo's standing rule that new mechanisms never arrive as a weight
in `arena_composite`.

---

## (f) Quality / low-volatility / betting-against-beta — with the honest capacity answer

### f1. BAB (Frazzini-Pedersen) — the capacity answer is the finding
- **Effect size (original):** BAB is long leveraged low-beta and short
  de-levered high-beta, held beta-neutral (roughly $1.40 long / $0.70 short).
  US equities: **Fama-French 3-factor alpha 0.73%/month (t 7.39)**; adding
  momentum, **0.55%/month (t 5.59)**; adding Pastor-Stambaugh liquidity,
  **0.55%/month (t 4.09)**. Annualised Sharpe ≈ **0.7-0.8** on US equities.
  Replicated across 20 international equity markets, Treasuries, corporate
  bonds and futures.
- **Decay / critique — this is the capacity estimate the brief asks for, and it
  is devastating and specific:** Novy-Marx & Velikov, "Betting against betting
  against beta," *Journal of Financial Economics* (2022; DOI
  10.1016/j.jfineco.2021.05.023):
  - BAB's inverse-beta rank weighting is **near-indistinguishable from equal
    weighting**, so **for each $1 invested, BAB commits on average $1.05 to
    stocks in the bottom 1% of total market capitalisation**, and net positions
    exceeding **$1.20 in the bottom 1.7% of the market**.
  - **Transaction costs cut BAB's profitability by almost 60%.** Trading cost is
    **58 bps/month** as constructed; excluding the bottom NYSE decile drops it
    to **22 bps/month (and only 9 bps/month over the last ten years)** — but
    gross performance falls commensurately, so the net is unchanged.
  - What survives is **not alpha**: BAB "does not have a significant net alpha
    relative to the Fama-French five-factor model." Net returns excluding
    nanocaps: **46 bps/month (t 3.38)**, five-factor generalized alpha
    **15 bps/month (t 1.31)**. It is a **backdoor tilt toward profitability and
    investment**, fairly compensated.
  - Bonus methodological point that should be read aloud in this programme:
    the FP beta estimator is **biased in a time-series pattern predictable by
    market volatility**, so BAB is **mis-hedged predictably and is NOT
    conditionally market-neutral** — market vol predicts BAB's market tilt.
    **A strategy that claims market-neutrality and is actually a volatility-
    conditional beta bet is precisely the failure Aegis has already hit four
    times.** Here it is, in a factor with 3,000+ citations.
- **Capacity (rough order of magnitude, honest):** the *published* BAB is
  **not investable at any size** — its return lives in the bottom 1-2% of market
  cap. The *investable* version (drop the bottom NYSE decile, cap-weight) has
  capacity in the tens of billions and **no net alpha**. For a sub-$1M
  long-only investor the usable residue is: **a low-beta / high-quality tilt is
  a defensible way to hold equity risk, not a source of alpha.** That is worth
  saying plainly in a public tool aimed at ordinary investors.
- **Cheapest test on Aegis data:** **CRSP through 2024, nothing else.** Build
  BAB two ways — (a) FP rank-weighting as published, (b) cap-weighted excluding
  the bottom NYSE decile — and print **gross and net side by side with the
  existing cost model**, plus the **realised market beta conditional on
  trailing market volatility** (the Novy-Marx mis-hedging test). This is a
  three-hour job that produces a *publishable-quality negative* and, more
  usefully, a **reusable diagnostic**: "how much of this strategy's return comes
  from the bottom market-cap decile?" should be a standard column on every Aegis
  farm result, because it is the question that killed BAB.
- **Citation:** Frazzini, A. & Pedersen, L.H., "Betting Against Beta," *Journal
  of Financial Economics* 111(1): 1-25 (2014) (NBER WP 16601, 2010). VERIFIED.
  Critique: Novy-Marx, R. & Velikov, M., "Betting against betting against beta,"
  *Journal of Financial Economics* 143(1) (2022), DOI
  10.1016/j.jfineco.2021.05.023 / SSRN 3300965. VERIFIED.

### f2. Quality / defensive equity more broadly — NOT SEPARATELY VERIFIED
I did not retrieve primary after-cost evidence for quality-minus-junk or generic
low-volatility investing in this pass, beyond the Novy-Marx result that BAB's
surviving net return **is** a profitability-and-investment tilt. **Treat "QMJ
works after costs" as UNVERIFIED here.** The defensible statement Aegis can make
today, from f1 alone, is narrower and more useful: *the low-beta effect is real
but its published magnitude is a construction artefact; the investable version
is compensated exposure to profitability and investment, not alpha.*

---

## (b) Corporate-action arbitrage — thin, and the two best-documented members have PUBLISHED failed out-of-sample tests

Per the brief's instruction to prioritise by strength of after-cost evidence and
not force one idea per family, I report **three** here. Two have explicit
ex-ante replication failures, which is more useful to Aegis than five
half-verified leads. SPAC redemption-yield trades, rights offerings, tender
offers, post-bankruptcy emergence equities and dual-class spreads: **I found no
primary after-cost academic evidence in this pass and am not going to invent
effect sizes for them. UNVERIFIED / NOT ASSESSED.** Note also that Aegis's data
stops at CRSP-2024 + Alpaca-2025/26 and has no corporate-action event database,
so most of family (b) is **blocked on data before it is blocked on evidence.**

### b1. Spin-offs (Cusatis-Miles-Woolridge) — the ex-ante test was run in 2001 and FAILED
- **Effect size (original):** 1965-1988, 146 spin-offs. Significantly positive
  matched-firm abnormal returns (MFARs) for spin-offs, parents and
  spin-off+parent combinations for **up to three years**.
- **The decomposition that kills it, and it is IN THE ORIGINAL PAPER:** the
  abnormal performance is **limited to firms involved in takeover activity.**
  - The **21** spin-offs taken over within 3 years: MFAR **+61.3% (months 1-24)**
    and **+99.3% (1-36)**, both significant at 1%.
  - The other **125** spin-offs: **+18.9% (1-24)** and **+22.5% (1-36)**,
    **neither significant.**
  - Strip the six months before takeover from the 21: +26.7% / +35.6%, **neither
    significant at 10%.**
  So "buy spin-offs" was never the finding. "Buy the 14% of spin-offs that get
  acquired" was, and that is only knowable afterwards. **This is a published,
  40-year-old instance of the exact error the Aegis charter names in Rule 2 —
  explaining the winner afterwards versus finding a precursor beforehand.**
- **Decay / replication:** McConnell, Özbilgin & Wahal ran the honest ex-ante
  test: take the Cusatis strategy as specified and trade it **1989-1995**.
  Result: **against the Cusatis matched-firm benchmark and against the
  Fama-French 3-factor model, the strategy does NOT beat the benchmark.** It
  beats only size-and-book-to-market-matched portfolios. Their conclusion:
  "On an ex ante basis, post-spin-off returns provide a shaky basis for
  rejecting the efficient market hypothesis."
- **Capacity:** ~20-40 US spin-offs/yr; a $1M book could hold them all. Capacity
  is not the constraint; **the absence of an ex-ante edge is.**
- **Cheapest test on Aegis data:** CRSP distribution codes identify spin-off
  share distributions, so a CRSP-only replication 1989-2024 is feasible **if**
  Aegis wants the extension past 1995. But the honest prior is that this lane is
  already closed by a published ex-ante failure, and **the repo's own rule
  applies — a `MECHANISM_REJECTED` verdict already exists in the literature.**
  Spend the session on (d) or (e) instead.
- **Citation:** Cusatis, P.J., Miles, J.A. & Woolridge, J.R., "Restructuring
  through spinoffs: The stock market evidence," *Journal of Financial Economics*
  33(3): 293-311 (1993), DOI 10.1016/0304-405X(93)90009-Z. VERIFIED.
  Ex-ante failure: McConnell, J.J., Özbilgin, M. & Wahal, S., "Spin-offs, Ex
  Ante," *Journal of Business* 74(2) (April 2001), DOI 10.1086/209672. VERIFIED.

### b2. Closed-end fund discount-to-NAV — mean reversion is real, the ARBITRAGE is not
- **Effect size:** the foundational results are Pontiff (1995), *Journal of
  Financial Economics* 37(3): 341-370 — abnormal returns on deep-discount funds
  come from **mean reversion in the DISCOUNT, not in portfolio values** — and
  Pontiff (1996), *Quarterly Journal of Economics* 111(4): 1135-1151, which
  shows deviations are larger for funds that are hard to replicate, pay small
  dividends, are small, and when interest rates are high, explaining **a quarter
  of cross-sectional mispricing variation.**
- **Decay — two independent negatives:**
  1. **Arbitrage in Closed-end Funds: New Evidence** (Vassar College working
     paper) runs Fama-French regressions on 20 discount/premium-bin arbitrage
     portfolios: **alpha is significantly NEGATIVE in three bins, insignificant
     in twelve, insignificantly positive in six, and significantly positive in
     exactly ONE** — the +25% to +30% premium bin, which holds **less than
     one-third of one percent** of all observations. And that is *before*
     trading costs and short-collateral costs; only bid-ask spreads were
     charged. Same paper: Pontiff's (1996) interest-rate/arbitrage-bound
     relation, "economically large and highly statistically significant" over
     1965-1985, is **"much smaller in magnitude and not at all statistically
     significant" over 1985-2001.** A textbook post-publication collapse.
  2. The short leg is separately impossible: a daily-NAV study finds **every**
     short-side strategy on positive discount changes loses money after costs
     (best case +0.06%, not different from zero), because closed-end fund
     borrow comes from custody banks acting for institutions and is scarce.
- **What survives, and it is small but real and long-only:** buying fund shares
  after a **large negative change in the discount** yields a mean **five-day
  profit of 0.39% (~20.3%/yr) net of estimated commissions and bid-ask
  spread**, rising to **>36.4% annualised when the fund trades ≥10% below NAV.**
  The authors are careful to say they **do not recommend that small investors
  day-trade this**; they recommend that investors who buy CEFs anyway **time
  their purchases** against the discount. (**FLAG: 2005-vintage study, daily NAV
  disclosure, no post-publication replication retrieved. Treat the 20%/yr as
  in-sample and stale.**)
- **Capacity:** tiny. CEFs are small and thinly traded; the deep-discount tail
  is smaller still. A $1M book is probably *inside* capacity for the long-only
  timing version and outside it for anything systematic.
- **Cheapest test on Aegis data:** **partially blocked** — Aegis has no CEF NAV
  series (CRSP gives CEF *prices*, not NAV). NAVs would need a new free source.
  Given b2's published negatives, **classify as `DEPRIORITIZED`, not rejected**,
  per the repo's over-closing rule: what is closed is *discount arbitrage*, not
  *discount-aware execution timing*, and the latter is a genuinely useful
  product feature for a retail tool even though it is not alpha.
- **Citation:** Pontiff, J., "Closed-end fund premia and returns: Implications
  for financial market equilibrium," *JFE* 37(3): 341-370 (1995). VERIFIED.
  Pontiff, J., "Costly Arbitrage: Evidence from Closed-End Funds," *QJE* 111(4):
  1135-1151 (1996), DOI 10.2307/2946710. VERIFIED. Negative replication:
  "Arbitrage in Closed-end Funds: New Evidence," Vassar College Economics
  Working Paper 57 — **author not captured in the retrieved PDF; FLAG.**
  Related and positive: Patro, Piccotti & Wu, "Exploiting Closed-End Fund
  Discounts: A Systematic Examination of Alphas," *Journal of Financial
  Research* 40(2): 223-248 (2017), SSRN 2468061 — **NOW VERIFIED, and it does
  partly reopen b2.** They estimate CEF expected returns from the **HISTORY** of
  premiums rather than the current premium alone, buy the top quintile and sell
  the bottom: **annualised return 18.2%**, and they argue prior studies
  "understated the value of the information in premiums." **Caveats before
  acting: it is a long-SHORT quintile strategy and the short leg in CEFs is the
  leg every other paper shows to be unshortable in practice; no net-of-cost
  figure appears in the abstract; and it needs a NAV history Aegis does not
  have.** Revised verdict on b2: *discount arbitrage in its classic form is
  closed; the premium-HISTORY variant is open, small-capacity, and blocked on
  NAV data.* Worth one paragraph in a future roadmap, not a session.

### b3. The rest of family (b) — NOT ASSESSED, and say so
SPAC liquidation/redemption-yield trades, rights offerings, tender offers,
post-bankruptcy emergence equities, dual-class share spreads: **no primary
source retrieved, no effect size, no decay evidence, no capacity estimate.**
Two of them (SPAC redemption yield, post-bankruptcy equities) are plausibly
live and under-researched; both require a corporate-action event database Aegis
does not have. **Recording them as un-assessed is the correct output here — a
fabricated effect size would be worse than a gap.**

---

## (h) Uniquely enabled by TAQ — order-flow imbalance at a DAILY decision horizon

### h1. Daily order-flow imbalance (Lee-Ready signed TAQ trades)
- **Effect size:** Chordia & Subrahmanyam establish the canonical result on
  NYSE stocks 1988-1998 with ISSM + TAQ, signing trades by **Lee-Ready (1991)**:
  daily imbalances are **strongly positively autocorrelated** (traders split
  orders), **lagged imbalance positively predicts the next day's open-to-close
  return** (~77% of first-lag coefficients positive), and the sign **reverses
  once you control for the contemporaneous imbalance**. Lags 6-10 turn
  significantly negative — the price pressure reverses slowly over several days.
  Crucially for capacity: **the average first-lag coefficient is statistically
  significant only for the three SMALLEST size groups** — "markets for large
  firms accommodate persistent imbalances more expeditiously."
  A later TAQ study (Ravi, *International Journal of Economics and Finance*)
  builds decile portfolios on day t−1 imbalance and trades **open-to-close on
  day t**: portfolio 1 (most bought) earns **~+33.9%/yr**, portfolio 6 (most
  sold) **~−36%/yr**, and the long-short earns **48 to 42 bps per DAY in
  1993-1998** — and then, in the author's own words, **"post 1998 the returns
  decline steadily."** Bid-ask-midpoint returns give virtually identical results
  to trade-price returns, so it is not bid-ask bounce.
- **Decay:** **documented and severe within the source itself** (48 bps/day in
  the mid-90s declining steadily after 1998), and the mechanism — market-maker
  inventory accommodation — is precisely what decimalisation, electronic market
  making and sub-penny queueing have competed away since 2001. **No modern
  (post-2015) after-cost replication retrieved. UNVERIFIED for the current era,
  with a strong prior of near-total decay in liquid names.**
- **Capacity:** **the effect concentrates in the smallest size groups and
  requires trading at the open and closing at the close, every day.** Round-trip
  retail cost on a small-cap is easily 20-50 bps; the surviving edge is almost
  certainly smaller. **This is a market-maker's edge, not a $1M retail account's
  edge.** Honest capacity estimate: as a standalone strategy, effectively zero
  for Aegis.
- **The ONE cheapest test that is actually worth running — and it is NOT the
  strategy:** use **TAQ through 2024 to build a daily signed order-imbalance
  panel as a COVARIATE, not a signal.** Aegis's recurring problem is that its
  edges turn out to be beta, an era, or a look-ahead. A daily order-imbalance
  column gives a fourth diagnostic it does not currently have: **"was my signal
  just buying stocks that were already under buying pressure?"** Add
  `OIB(t−1)` to the right-hand side of any Fama-MacBeth Aegis already runs and
  see whether the candidate's coefficient survives. That is a **control
  variable**, which the repo's own canon says is the informative unit, and it
  costs one TAQ pull that Aegis's licence already covers.
- **Citation:** Chordia, T. & Subrahmanyam, A., "Order Imbalance and Individual
  Stock Returns: Theory and Evidence," *Journal of Financial Economics* 72(3)
  (2004) (working versions: SSRN 336060; eScholarship 34k8f3pv). VERIFIED as to
  content (full text retrieved); **exact published volume/pages not re-verified
  this pass — FLAG.** Trade signing: Lee, C.M.C. & Ready, M.J. (1991).
  Portfolio implementation + decay: Ravi, R., "Autocorrelated Order Imbalance
  and Short-Term Momentum," *International Journal of Economics and Finance*
  (CCSENET) — **journal is low-tier; use it for the decay direction, not for a
  headline number.**

### h2. VPIN / flow toxicity — NOT ASSESSED
No primary source retrieved this pass. VPIN's public reputation rests on
flash-crash *detection* rather than cross-sectional return prediction, and it
has a contested replication literature. **UNVERIFIED — do not build on memory.**
If it is ever pursued, the question to pre-register is not "does VPIN predict
returns" but "does VPIN predict **realised execution shortfall**", which is the
use where Aegis would actually save money and where a small book is not
disadvantaged.

### h3. The best TAQ idea in this document is not a signal — it is a COST MODEL
The 2026-09-10 C2 finding (net −237%/yr was a flat-100-bps/day cost artefact)
and the 2026-09-09 TRIAL-H5 finding (a control's level moves with the
dollar-volume floor) both say the same thing: **Aegis's cost assumptions are
currently doing more damage to its conclusions than its signals are.** TAQ
through 2024 contains the **actual effective spread and depth** for every name
and day. Building an empirical `cost(name, date, size)` function from TAQ —
effective half-spread plus a depth-scaled impact term — would replace a flat bps
constant everywhere in the farm, and would retroactively change the verdict on
every strategy already tested. **Measured against the charter's own scoring rule
(`P(changes the roadmap) × value of decision improved − cost`), this scores
higher than any single signal in this document**, because it changes the answer
for all of them at once and uses a licensed dataset that is currently unused.

---

# Summary: what to actually do

Ranked by expected value for a sub-$1M long-only-capable book, using the
charter's scoring rule. Everything above the line uses data Aegis **already
has** and needs no new acquisition.

| # | Idea | Family | Data needed | Why it ranks here |
|---|---|---|---|---|
| 1 | **Low short interest × high turnover, long-only** | d2 (+d3 DTC) | FREE FINRA/exchange short-interest + CRSP | Published ~+1%/mo long-leg alpha, 6-month holding period, liquid names, capacity ≫ $1M, retail constraints are not a handicap. Decay past 2005 is **unmeasured by anyone** and costs one download to measure. |
| 2 | **Insider cluster buys, split by CLUSTER LENGTH** | e1 (+e2 2×2) | Aegis's own 11.5M Form-4 rows + CRSP | Zero new data. Frontier result (4-5-day clusters → +5% post-disclosure BHAR; same-day clusters → −0.72%) is specific, falsifiable, unpublished past 2016, and orthogonal to the opportunistic/routine classifier. |
| 3 | **TAQ-derived empirical cost model** | h3 | TAQ (licensed, unused) | Not a signal. Changes the verdict on every strategy already tested, including the ones already closed. Highest `P(changes the roadmap)`. |
| 4 | **Option-implied borrow-fee panel** | c3 (→ d1 filter) | OptionMetrics (licensed) | Creates a **new free 1996-2024 dataset** from a licence already paid for; then answers "was my edge the borrow fee?" — a fifth named failure mode to add to beta / one era / look-ahead / below the floor. |
| 5 | **Month-end reversal under T+1 settlement** | a3 | CRSP + Alpaca 2025-26 | Mechanism is a payment calendar, not a premium; documented as *strengthening* through 2013; the May-2024 T+1 change shifts the window and **nobody has published on the post-T+1 geometry.** |
| 6 | **FOMC drift, VIX-conditional** | g1 | CRSP + free FOMC date list | Dead as a global effect (three replications). Alive as a **scope-aware conditional** the literature explicitly leaves open, and as the cheapest available **ground-truth calibration** for Aegis's era-splitting machinery. |

**Do not spend a session on:** S&P 500 inclusion (a1, dead, mean ≈ 0 since 2010),
Russell reconstitution (a2, blocked on licensed membership data), OPEX pinning
(a4, an absolute-deviation bound, not a signed return), spin-offs (b1, ex-ante
test published and failed in 2001), CEF discount arbitrage in its classic
current-premium form (b2, alpha positive in 1 of 20 bins covering 0.33% of
observations — though see the Patro-Piccotti-Wu premium-HISTORY variant, which
is open but blocked on NAV data), IV skew / IV innovations as
alpha (c1/c2, Sharpe 1.18 → 0.16 and partly a timestamp look-ahead), BAB as
alpha (f1, $1.05 per $1 in the bottom 1% of market cap, no net five-factor
alpha), daily order-imbalance as a strategy (h1, a market-maker's edge that was
already decaying by 1998).

**Three cross-cutting lessons this literature hands Aegis for free:**
1. **The non-synchronous timestamp look-ahead (c1)** is a real, published,
   named defect in OptionMetrics-based research. Aegis should assume it applies
   to any options work it does and build the one-day lag in from the start.
2. **An edge can die on a DATE for an enforcement reason (c4, e2)**, with no
   gradual decay. Era splits at even intervals will miss this. Split at SOX
   (Aug 2002), Rajaratnam (Oct 2009), decimalisation (2001), and T+1 (May 2024).
3. **"How much of this return comes from the bottom market-cap decile?" (f1)**
   is the single question that destroyed a 3,000-citation factor. It should be a
   standing column on every Aegis farm result, not a question asked afterwards.

**Verification status:** every effect size above was read from a retrieved
primary or near-primary source this session. The items I could **not** verify
and have flagged inline are: authorship of the 2025 JPM options paper; the
published venue of the Muravyev-Pearson-Pollet companion paper; SSRN 4150768
(authors/venue); post-publication decay for Drechsler×2, Boehmer-Huszár-Jordan,
Hong et al. DTC, Kang-Kim-Wang, and Cohen-Malloy-Pomorski; the pre-holiday
effect entirely (g3); earnings straddle overpricing net of costs (c5); QMJ
after costs (f2); OPEX pinning post-2005 (a4); the Vassar CEF paper's author;
VPIN (h2); and all of b3. (Patro-Piccotti-Wu 2017 was subsequently verified —
see b2.) The
"2025 3.7M-transaction insider composite" named in the brief **could not be
located in the public literature at all.**
