# The published wheel pays nothing tradable on 2006–2019

**2026-08-17.** Order 8 routed the pull, then the library, then the factory —
*"a factory result is unanchored until we know what momentum delivers on the
same panel, net."* The pull turned out to be already on disk. This is what
momentum delivers.

The answer is that it delivers nothing, and neither does almost anything else.

---

## The bar, stated first

**206 published cross-sectional predictors**, measured on our own CRSP panel,
long-short decile spreads, equal weighted, net of 10bp per crossing,
2006-01 … 2019-12.

```
  median net annual return           -0.12%
  mean net annual return             +0.17%
  share with net > 0                    48%
  share clearing +3%/yr                 19%   before any multiplicity control
  survive BH-FDR at q=0.10, m=206         11
  would have been claimed uncontrolled    42
  expected false among the 11           ~1.1   BY DESIGN
  of the 11, detectable NET in the
    liquid tercile                         1   at 1.01x its own MDE
```

**The factory's bar is not 3%/yr from momentum. There is no established
published benchmark in the tradable tercile at all.** The single survivor
(`ShareIss5Y`, +8.64% net in the liquid tercile) sits at 1.01× its own MDE
after 206 tests were screened at an FDR that expects ~1.1 of the 11 to be
false. §37 is explicit about how to read a number in that position: a first
positive that sits exactly at the detection threshold is the one that looks
like it working.

This cuts both ways and both matter. The factory is not competing against a
strong incumbent — and the standard that has been killing the factory's output
has now been applied to the incumbents, so the comparison is honest.

## The ten seeded strategies

```
  strategy                                    gross      net      z      break-even
  Profitability (gross profits / assets)     +6.91%   +6.50%   +2.2    167.3bp
  Low-volatility / defensive equity          +7.31%   +4.37%   +1.6     24.8bp
  TSMOM — time-series momentum (equity)      +4.23%   +3.80%   +1.8     97.8bp
  UMD — cross-sectional momentum (12-1)      +0.40%   -1.11%   +0.1      2.6bp
  Short-term reversal (1-month)              +1.24%   -2.90%   +0.3      3.0bp
  BAB — betting against beta                 -2.34%   -3.03%   -0.4    -33.6bp
  HML — book-to-market value                 -2.69%   -3.20%   -1.0    -53.0bp
  PEAD — post-earnings-announcement drift    -2.27%   -3.74%   -0.8    -15.4bp
  QMJ — quality minus junk                 REFUSED — no faithful implementation
  Volatility targeting                     REFUSED — no faithful implementation
```

**None of the eight measured survives the FDR screen.** Five of them are
negative net. Momentum's gross spread is +0.40%/yr — it pays 1.5%/yr in costs
at 10bp and its break-even is **2.6 basis points per crossing**, which is not a
strategy, it is a rounding error with a Nobel-adjacent citation.

Two refusals rather than proxies: QMJ needs the profitability/growth/safety
composite as AFP construct it, and assembling our own from OSAP components
would be measuring a strategy of ours under their name. Volatility targeting is
a sizing rule with no cross-section to sort — it belongs in the §59 sizing
layer, where the outcome is risk.

## Where the eleven survivors actually live

Every survivor re-measured inside each dollar-volume tercile, cut within each
month:

```
  predictor                  all   illiquid       mid    liquid   verdict
  CPVolSpread             +6.16%   +11.68%    +5.65%    +2.91%   larger in the illiquid tercile
  SmileSlope              +7.25%   +11.15%    +5.29%    +4.49%   larger in the illiquid tercile
  PriceDelayRsq           -7.72%    -8.86%   -10.78%    -5.58%   SIGN INVERTED vs publication
  std_turn               +18.28%   +13.73%   +45.63%       n/a   NOT MEASURABLE in the liquid tercile
  MomSeason16YrPlus       +0.68%    -3.47%    +2.70%    +3.08%   below its own MDE in the liquid tercile
  VolumeTrend             +4.86%    +2.68%    +2.38%    +7.06%   below its own MDE in the liquid tercile
  OptionVolume1           +4.65%    +6.27%    +2.26%    +2.54%   larger in the illiquid tercile
  Tax                     +4.71%    +6.04%    +3.95%    +2.70%   larger in the illiquid tercile
  ShareIss5Y              +6.89%    +4.82%    +4.86%    +8.64%   detectable and positive where it CAN be traded
  ShareIss1Y              +5.02%    +1.26%    +3.57%    +4.45%   below its own MDE in the liquid tercile
  dCPVolSpread            +1.20%    +2.27%    -0.51%    -1.56%   larger in the illiquid tercile
```

**The G4 cost finding reproduces on a completely different family.** Five of
eleven are larger in the illiquid tercile; one is sign-inverted; one is not
measurable among tradable stocks at all. That is the same pattern the earnings
work found — *drift lives where the costs are* — arrived at independently,
which is worth more than the single instance was.

**`std_turn` is the sharpest case.** The largest number in the entire
206-predictor table, +18.28% net, has a **median of 2 valid names per month in
the liquid tercile against 546 overall**. It is not a strategy that fails in
large caps; it is a strategy that does not exist there. A table reporting only
the "all" column would have made it the headline.

## Four defects found in this measurement, by me, before it stood up

Recorded because the corrections are the content:

1. **`sign(past return)` pushed through a decile sorter is not TSMOM.** A
   three-valued signal has no interior deciles, so the sort was ordering ties
   by permno and the "top decile" was an arbitrary tenth of the positive-trend
   names. It reported the flagship trend strategy at **−1.15%** net. Rebuilt as
   the time-series rule it actually is — hold every name, long or short by its
   own sign, inverse-vol sized — it is **+3.80%**.
2. **`detectable` compared *gross* to the MDE while every table printed *net*.**
   Costs shift the estimate without changing its SE, so the flag was certifying
   one number while the reader read another. Three of four "tradable survivors"
   turned out to sit at 0.61–0.77× their own MDE. The count went from 4 to 1.
3. **A `nan` cell was given a verdict.** The liquid tercile of `std_turn`
   printed `+nan%` and was labelled "concentrated where it cannot be traded" —
   an unmeasured cell mistaken for a measured zero, which is the unscoreable-rows
   defect one column to the left.
4. **"Not detectable in liquid" was printed as "concentrated in illiquid"**,
   including for `VolumeTrend`, whose liquid tercile is *larger* than its
   illiquid one. Four states now, not two.

## The alignment fact, measured rather than assumed

Chen & Zimmermann's convention note says signals are lagged so month *t*
predicts *t+1*. Notes are not data. Checked against our own return panel:

```
  Mom12m at label month m  ==  cumulative return over m-11 .. m-1
  Mom6m  at label month m  ==  cumulative return over m-5  .. m-1
```

correlation **1.0**, max absolute difference **0.0**, on three widely separated
months. So a signal labelled *m* is built from data through *m−1* for the two
predictors we can re-derive from first principles.

That verifies two, not 209. The primary measurement therefore pairs the signal
labelled *m* with the return of month ***m+1*** — PIT-safe for every predictor
under any convention, because *m+1* is strictly after the label month whatever
went into it. It costs momentum a month of freshness (our UMD is effectively
12-2), and that is a **declared** cost of one defensible rule instead of 209
conventions taken on trust.

## What this is not

* **Not a confirmation.** 2006–2019 is registered EXPLORE
  (`slc_c3246e5093c41c25`, M4-SELECTOR) because if we later choose which
  strategies to deploy from these numbers, this window selected them. M4's
  confirmation window is reserved disjoint on 2020-06-01 … 2026-07-17.
* **Not a reproduction of the authors' results.** Their windows mostly end
  before 2002; our pre-2002 panel is registered-use-only. For nearly every
  predictor here 2006–2019 is entirely **post-publication**, which is why no
  decay *ratio* is computed — we hold the decayed half and not the other one.
  What can be said is that McLean & Pontiff's ~58% average post-publication
  decline is, on this window and this construction, an understatement.
* **Not a cost model.** 10bp per crossing is illustrative; the break-even
  column is the fact and the reader substitutes their own number.
* **Equal-weighted, and that flatters everything.** No shares-outstanding
  series is in the panel, so value weighting was not available. EW tilts toward
  small names, which is precisely where the tercile table shows the returns
  live. A value-weighted rerun would be expected to make the headline worse,
  not better.
* **The dollar-volume series ranks, it does not measure.** Its absolute scale
  did not reconcile against a known mega-cap, so it is used only for
  within-month ordering — a use invariant to any monotone within-month
  rescaling, which is the only property needed. No dollar levels are quoted.

## Why the screen was FDR and not Holm (§63)

206 predictors on one window is 206 chances. Holm at m=206 puts the first
threshold at 0.00024 and leaves a handful of microstructure signals — the kill
machinery becoming the programme. A screen owes control of the *proportion* of
its output that is false, and it owes saying how many that is: **~1.1 of the
11, by design.** The decision went through the same `decide()` entry point
everything else uses, so the criterion could not be chosen after the p-values
were visible. A SCREEN result may never be quoted as a confirmation.
