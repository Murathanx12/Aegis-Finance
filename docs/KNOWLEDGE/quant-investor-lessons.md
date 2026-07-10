# Quant & Investor Lessons — the brain's learning module

> **Purpose:** this is how the Optimus brain "learns to be a quant and an
> investor" — honestly. Every lesson here was either MEASURED by this project,
> adversarially VERIFIED in a research pass, or paid for with a production
> incident. Nothing aspirational, nothing from a blog. Sessions APPEND new
> lessons (with date + evidence); they never delete (superseded lessons get a
> strike-through + pointer). The brain ingests this file on every re-ingest,
> so `brain_query` can answer quant questions from the project's own earned
> knowledge. Not a substitute for canon — CANON.md governs; this teaches.

## I. What actually predicts returns (evidence-ranked)

1. **Analyst revision FLOW beats implied-upside levels** — IC 0.23, t=4.9 in
   the verified literature; our T10 flip confirmed discrimination
   (NVDA +23 / DKNG −4). Rank by raises−lowers+upgrades−downgrades, never by
   "target price says +40%." *(2026-06-20, verified; running as TRIAL-REVISIONS-IC)*
2. **Insider cluster-buying (open-market P codes, multiple distinct buyers)**
   is a moderate signal, strongest in small caps. Count distinct buyers, not
   dollar totals alone. *(TRIAL-INSIDER-IC, running)*
3. **Momentum (12-1 cross-sectional)** is the premier published anomaly and
   survives replication — but expect US post-publication decay (the US is the
   ONLY market with reliable post-publication decline; 241 anomalies / 39
   markets). *(2026-07-09, verified 3-0)*
4. **Quality = gross profitability (GP/A)** is the cleanest single quality
   measure (Novy-Marx); most published factors DO replicate out-of-sample
   across 93 countries (JKP). *(2026-07-09, verified; TRIAL-QUALITY-IC running)*
5. **PEAD (earnings drift)** is real but decaying, small-cap-concentrated, and
   disputed net-of-cost in large caps. Define the surprise vs ANALYST
   forecasts, not time-series; two-way (surprise × announcement reaction) is
   stronger. It does NOT subsume momentum (that claim refuted 0-3).
   *(2026-07-09, verified; TRIAL-PEAD-IC running)*
6. **13F / congressional positioning** = descriptive context on a 45-day legal
   lag. Confirmer, never a timing signal.

## II. What does NOT work (measured/refuted — do not relearn)

1. **Short-horizon market timing loses to buy-and-hold** — our own signal
   engine: +251% vs +740% over 2020-25; all 7 sell signals fired at VIX>25 and
   forward-3m returns after them were mostly POSITIVE. Risk-awareness ≠ return
   forecasting. *(NEGATIVE_RESULTS §1)*
2. **Crash timing has ≈0 IC**; false-positive de-risking exits compounding
   bull markets and costs more than the crashes. The answerable form is
   FRAGILITY measurement (continuous, descriptive). LPPLS predictive skill:
   refuted twice. *(canon A5)*
3. **Volatility-managed portfolios are NOT an alpha machine** — Moreira-Muir's
   big-alpha claim refuted 0-3 in adversarial verification; across 103
   strategies, managed beat unmanaged 53/103 with only 8 significant. Vol
   overlays are DRAWDOWN CONTROL at ~flat Sharpe — still worth having, honestly
   labeled. *(2026-07-09 verification + our own TRIAL-VMM finding 2026-06-15)*
4. **Backtests on survivor-only data cannot certify alpha** — yfinance
   recovers 1/20 delisted names; DSR/PBO guard multiple-testing, NOT a biased
   universe (vol-managed momentum printed a false PASS this way). Free-data
   engines validate selection FORWARD (PIT IC + paper NAV). *(T7, measured)*
5. **LLM stock-picking validated by backtest is hindsight** — lookahead
   inflates apparent skill ~37%; blinded, 9/10 models show NEGATIVE selection
   alpha. Forward-only lanes are the only honest test. *(profit mirage, canon A2)*
6. **Thematic "buy the future early" baskets** can't be backtested into
   validity — theme selection edge measured at −0.08 Sharpe vs controls;
   EW-themes "beating SPY" was hindsight + survivorship. *(TRIAL-THEME reject)*
7. **Day-trading lanes**: costs swamp any edge on free hourly data. Multiple
   horizons of pre-registered lanes instead.

## III. How to run money like a quant (process lessons)

1. **Pre-register or it didn't happen**: hypothesis, ONE deciding metric,
   thresholds, earliest decision date — committed before data. Interim numbers
   are reported, never acted on.
2. **Count every trial** — DSR/PBO deflate against the CUMULATIVE count; a
   registry with only adoptions is self-deception. Publish negative results;
   they are the credibility.
3. **Exits are risk control, not alpha**: ATR trailing stops cut max drawdown
   (−30.6% vs −33.7% in our runs) at small return cost. The disposition effect
   (~3.4pp/yr, Odean) is the single most measured retail error — pre-committed
   stop levels + naming the pattern ("winner rolling over", "loser past stop")
   is the fix that survives evidence.
4. **Equal-weight what you can't validate**: fitting composite weights to past
   crises is hindsight. Our fragility composite stays equal-weighted by canon.
5. **Regime/fragility scales exposure; it never times exits to zero.**
6. **A young track record proves nothing either way** — 30 days of
   conviction +5.5% vs mirror −8.4% is noise by construction. 24 months.

## IV. Production/engineering lessons an investing system must obey

1. **Silence is the killer, not wrong math**: collectors that run-but-fetch-
   nothing (T9 SEC 403s), models dark behind swallowed exceptions (crash
   overlay), FALSE-PLAUSIBLE ZEROS (ipo_issuance read the wrong JSON depth →
   "0 IPOs in 90d" when reality was ~3700). Guards: fail loud, status rows +
   health canaries, implausibility checks on zeros, live prod verification
   after every deploy — green tests are not a live verification.
2. **Point-in-time or it leaks**: every datum stores as_of + observed_at;
   reads filter observed_at ≤ decision time. Latest-vintage macro data quietly
   rewrites history.
3. **Determinism is a platform claim**: byte-reproducible training held on
   Windows and failed on Linux (threaded eval-metric ULP wobble pickled into
   the artifact, TWO copies). Component-wise hashing + byte-offset dumps
   debug what you can't shell into.
4. **The config hash is segment identity**: never edit a live lane's YAML;
   strategies change by NEW pre-registered lanes.
5. **One rate-limiter choke-point per external host** — SEC 403s (not 429s)
   at volume that dev machines never reach.

## V. Live market readings worth remembering (dated snapshots)

- **2026-07-09 first candidate collection:** structural fragility LOW (0.23);
  breadth HEALTHY (equal-weight RSP beating cap-weight SPY over 126d —
  mega-cap concentration reading negative); the two elevated tails: CCC
  credit spreads at the 87th percentile of their history and policy
  uncertainty at the 84th. IPO issuance ~3.7k S-1s/90d (normal). The engine's
  crash read: quiet, with stress visible only in the junkiest credit and
  policy noise — not confirming a crash narrative.

---
*Append below with date + evidence. Never assert what wasn't measured.*
