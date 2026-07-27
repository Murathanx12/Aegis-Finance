# RESEARCH SWEEP 2026-07-27 — round 12 external evidence (two harnesses, 42 sources)

**Status:** research only. Nothing registered, nothing run, no commits made by this
document. Batch 10 is NOT frozen — this sweep materially changes what its
registration should say (see §3).

## 0. Provenance and reliability — read before citing anything here

Two deep-research harnesses ran 2026-07-27:

| Run | Scope | Sources | Claims extracted | Agents done / errored |
|---|---|---|---|---|
| `wf_73c48e5b-ad4` (FRONTIER) | 8-K family, remaining edge, defensive layer, paper positioning, retail mission | 20 | 100 | 45 / 57 |
| `wf_57c345d2-99f` (NOVEL) | new data classes, LLM alpha, construction/tax alpha, market structure, practitioner frontier | 22 | 109 | 48 / 56 |

**Three integrity caveats, all of which bind on how you read the numbers below:**

1. **The adversarial verification layer did not run.** Both runs hit the monthly
   spend limit during the 3-vote stage. 50 of 209 claims entered voting; **8 were
   genuinely confirmed** (real 3-0 / 2-0 tallies) and **5 were marked "refuted"
   with `evidence: null` and `counterSource: null`** — the signature of a killed
   agent being tallied as a refute, not of an actual refutation. **All refutation
   verdicts in the raw output are VOID and are ignored here.** Notably this means
   the Lerman-Livnat event-date-vs-filing-date asymmetry and the "8-K carries no
   signed return" claims were NOT actually refuted; they stand as source-quoted.
2. **Source URLs were shuffled relative to claim groups in both runs.** The
   harness paired group *i* with URL *i*, but the orderings differ — e.g. the
   McLean-Pontiff claim block was paired with an INFORMS URL, and the
   Lerman-Livnat 8-K block with an NBER URL. `claimCount` matched by coincidence.
   **I re-matched all 42 sources to their correct URLs by bibliographic content**
   (paper title, journal, volume, DOI, sample period stated inside each claim).
   The citations in §8 are the re-matched set. This is also the most likely cause
   of the null-evidence "refutations": verifiers were sent to check claims
   against the wrong pages.
3. Every claim below is a **single-source extraction with a verbatim quote from
   the source**, not a cross-examined finding. Magnitudes are as the papers state
   them. Where a paper was paywalled and only an abstract was read, it is marked
   UNVERIFIED and the magnitude is not used.

Raw corpus preserved at
`…/scratchpad/{corpus,claims}_{FRONTIER,NOVEL}.{json,md}`.

---

## 1. The headline: three findings that change the plan

### 1.1 🔴 The paper's lead exhibit has prior art. Reposition it.

**McLean & Pontiff (2016, JF 71(1):5-32) already established that decay increases
in the strength of the original statistical evidence — including in the in-sample
t-statistic specifically.** They regress decay on in-sample t (mean t = 3.55,
SD = 2.39) and find a one-SD-higher t implies an incremental decline of **−0.146
post-sample and −0.151 post-publication**, and they **plot in-sample t-statistic
against post-publication decline directly (Figure 1.B, 70-predictor subsample).**

That is the closest published antecedent to CZ-CALIB's −0.544. It does not
duplicate it — theirs is decay-vs-t within their own construction; ours is
published-t vs *independently replicated* t across 13 SignalDoc-matched signals —
but a referee who knows Figure 1.B will not accept "published t-stat is a
contrarian indicator" as a new phenomenon.

Three more sources tighten the vise:

- **Chen, Lopez-Lira & Zimmermann** (arXiv 2212.10317) establish **parity, not
  inversion**: ~50% of original-sample long-short return survives post-sample for
  both published predictors *and* 29,000 mechanically mined accounting ratios
  filtered on in-sample |t|>2. Fame is *uninformative*. Two of three canonical
  findings tie or lose to mined twins post-sample (B/M 0.61 vs 0.65; momentum
  0.72 vs 0.52; **size 0.15 vs 0.42 — fame actively hurts**). Gross.
- **Jensen, Kelly & Pedersen** (JF 78(5), 2023) are the strongest rebuttal: the
  in-sample→OOS alpha relation is **positive and highly significant** (GLS slope
  0.57 pre / 0.26 post / 0.35 combined, t 3.5–5.3; 82.4% US replication vs HXZ's
  35%). **But their own slope of 0.26 sits far below the 0.9 Bayesian benchmark
  their hyperparameters imply, and the scatter is concave — the largest published
  alphas decay most.** That concavity is precisely the mechanism that produces a
  negative rank correlation in the tail. The strongest anti-crisis paper concedes
  the mechanism inside itself.
- **Chen & Zimmermann's own survey** — the authors of the SignalDoc corpus you
  calibrated against — conclude **publication bias is NOT dominant**: Empirical
  Bayes shrinkage removes only **10–15%** of in-sample mean returns, FDR <10%,
  almost all published findings replicate. And they pre-emptively disarm your
  method: returns being **30–50% weaker in ALTERNATIVE portfolio tests** and
  multiple-testing hurdles above 3.0 are "easily misinterpreted as evidence of
  publication bias effects." **Your harness re-implements 13 SignalDoc signals
  with your own construction — that is textbook "alternative portfolio test."** A
  referee will attribute part of −0.544 to construction differences.

**What is actually still novel — and it is not the −0.544:**

| Exhibit | Novelty verdict |
|---|---|
| CZ-CALIB rank corr −0.544 | **Weak.** Variant of McLean-Pontiff Fig 1.B. n=13, p=0.055. Construction-difference objection unanswered. Demote to supporting. |
| **Empty cost-killed cohort under a frozen pre-application rule across 155 candidates** | **Strong.** Chen-Velikov measures cost-adjusted returns; nobody has published "we froze a mechanical would-have-graduated-but-for-costs rule *before* applying it and it returned literally zero." Clean pre-registered negative. **This should lead.** |
| The factory method itself — pre-registered one-shot explore/confirm, public trial registry, DSR deflated against cumulative count, 10+ documented refused re-litigations | **Strong.** Effectively nobody in asset pricing does this. The methodology is the contribution. |

**Recommended repositioning:** lead with the method + the empty cost cohort;
report −0.544 as a supporting exhibit *explicitly positioned against*
McLean-Pontiff Fig 1.B and JKP's concavity. **Add one robustness arm that
directly answers Chen-Zimmermann: re-run the 13 matched signals using SignalDoc's
own construction, and report both.** If −0.544 survives your-construction *and*
their-construction, it is defensible; if it collapses under theirs, you have
learned that and saved yourself a referee's demolition.

**Venue:** FAJ demonstrably publishes replications that overturn industry
statistics — it ran the Morningstar behavior-gap rebuttal in May 2026 (§6).
Critical Finance Review explicitly publishes replications. Realistic for a solo
author.

### 1.2 🔴 Batch 10 as currently conceived is aimed at the short leg. You are long-only.

**Lerman & Livnat, "The New Form 8-K Disclosures"** (Review of Accounting Studies
15(4):752-778, 2010; sample 2005-2006, 123,890 filing-date observations,
size/BM-matched BHARs, gross, no cost analysis, no proposed strategy):

- **Post-filing drift is concentrated in distress/negative items and is small
  outside bankruptcy.** Bankruptcy or Receivership drifts **−15%, −13%, −19%** at
  30/60/90 days. Changes in Control and Increase/Acceleration of a Direct or
  Off-Balance-Sheet Financial Obligation drift **−1.5% to −3.7%**. **Very few
  items show positive significant drift.**
- **Good news reacts at the EVENT date; bad news reacts at the FILING date.** Ten
  items show significant positive mean returns and eight significant negative.
  Good news is already leaked or press-released by the time it hits EDGAR — so
  the fraction of 8-K information that is *tradable at the filing timestamp* is
  predominantly **negative**.
- **Unconditionally an 8-K carries essentially no signed return** (3-day AR 0.1%
  event, 0.2% event-to-filing, ~0 at filing) while abnormal **volume is 62/56/60%**
  and volatility **2.8/2.5/2.7×**. The information is mostly **unsigned**.
- Item-level effects were significant at 22 items across ~125,000 filings — i.e.
  heavily multiple-tested. Your DSR deflation must charge for that.
- Item-count is a cheap conditioning variable (3-day event AR rises monotonically
  0.1 / 0.2 / 0.8 / 1.0 / **3.8%** for 1/2/3/4/5+ items) **but does not carry into
  the drift window.**
- Filing-lag facts: ~95% filed within the 4-business-day deadline; a third of
  timely filings land on the last allowed day; **Item 2.02 is fastest (61% within
  one business day)**. Within-deadline lag variation does NOT predict different
  3-day returns.

**Second source, confirmed 3-0 by the surviving verifiers:** an item code is not
an event type. **Item 8.01 ("Other Events"), the voluntary catch-all, is the modal
item code for 9 of the 15 most price-reactive event types** (clinical trial
results, merger completions, regulatory decisions). And within one item code the
reaction is wildly heterogeneous: in Item 5.02, **CEO departures average 1.32
standardized abnormal return with 17.2% of filings moving >2× normal (3.5% >4×),
versus 1.06 / 9.7% / 0.8% for routine officer appointments** (Kruskal-Wallis
p=3e-8; 182,174 collision-free events, 2022-2026, unsigned magnitude only). That
same source **explicitly disclaims any return-direction or drift finding** — it is
taxonomy plumbing, not prior strength for alpha (confirmed 3-0), and its corpus is
only 2022-2026 via a commercial vendor, so it cannot support your 2004-2018 /
2019-2024 split.

**Consequence for the registration.** A long-only, filing-timestamp-triggered,
item-level 8-K *picker* has a **weak-to-negative honest prior**. Writing it as a
PICKER pools heterogeneous events under coarse codes and points at drift that
lives on the short leg you don't trade. Two admissible reframings:

- **8-K as FILTER / risk screen** (taxonomy Role=FILTER): flag and *avoid or
  underweight* names filing distress items (bankruptcy, control change,
  obligation acceleration). Long-only-compatible, uses the documented sign, and
  fits the family's real shape. This is the registration I would write.
- **Item 2.02 as the one PICKER candidate** — fastest filer, cleanest timestamp —
  but note this is **PEAD by another name**, and PEAD is CLOSED in your ledger
  with an *inverted* in-window sign (pead_agree IC t −2.6). Prior-check should
  probably kill it. If registered at all, it must be as a daily-resolution event
  study, which your own taxonomy already names as the only admissible retry class
  for fast-decay families.

### 1.3 🟢 The one genuinely novel, long-only, free, monthly-implementable edge found: randomize your rebalance date

**NBER WP 33554** (issued March 2025, revised January 2026; daily futures,
1997-09-10 to 2023-03-17):

> Rebalancing once per month on a **randomly chosen day** (same 12 events/year)
> cuts average rebalancing price-impact cost from **>8 bps/yr to 0.6 bps average /
> 0.5 bps median across 10,000 simulations**, at the price of ~35 bps average
> tracking error (~3% of a 60/40 portfolio's 12% annualized vol).

This is the only finding in 42 sources that is simultaneously: **long-only,
no shorting, no leverage, monthly cadence, free data, zero new signal, and
directly applicable to lanes you already run.** Your reference/book/TSMOM-XA lanes
rebalance on calendar cadence — the paper's own finding is that calendar-signal
predictability is **strong at month-end and absent at other times, strengthening
into quarter-end.** You are currently the predictable party.

The paper's headline strategy — front-run the rebalancers, long S&P futures /
short 10Y note futures — earns **10.20% annualized excess, 9.17% vol, Sharpe
1.11, alphas 9.43-9.64%/yr vs CAPM/Carhart-4/FF5/HXZ q (t>4), Sharpe still ~1
after conservative Harvey-2018 costs and 0.90 excluding Sep2008-Mar2009 and
Mar2020.** **Not implementable for you**: requires shorting Treasury futures and
daily position changes. Do not chase it. Take the free half.

Also: a 1-SD rise in the Threshold (Calendar) signal predicts **−16 bps (−17 bps)**
next-day equity return and +4 (+2) bps bond return, reverting within two weeks;
applies to large- and small-caps but **not to value or growth** portfolios.

---

## 2. Where remaining edge actually is — the honest ceiling

**Chen & Welch, "What Useful Alphas?"** (arXiv 2607.06502 — already banked):
median monthly zero-investment return across ~200 published anomalies falls from
**48 bps/mo** (through Dec 2005, all stocks) to **7 bps/mo** (Jan 2006 onward,
non-micro only) — ~85% decline. **The residual 7 bps is destroyed by luck
adjustment OR transaction costs.** Roughly half the historical premium is a
micro-cap phenomenon: the top-3,000/top-90%-cap restriction alone cuts 48 → 26
bps holding the period fixed. Their conclusion is explicit: published anomalies
were of no use to any manager outside micro caps in the 21st century.

**This independently corroborates your empty cost cohort**: the gross effect was
already ~zero *before* costs were applied. Costs were never the executioner.

**Chen, Lopez-Lira & Zimmermann** give the sharpest number for your situation.
Post-2004, in value-weighted (large-cap-tilted) portfolios accounting-based
predictability is **dead** — VW extreme bins decay **88.7%** (−37.3 → −4.2 bps/mo)
and **97.8%** (+25.8 → +0.6) — while equal-weighted (small-tilted) bins retain
−24.9 and **+16.3 bps/mo**. Gross.

> **The honest post-2004 ceiling is ~+16 bps/month gross on an equal-weighted
> long-short. Your long leg only, net of Kyle-Obizhaeva, is a fraction of that.**
> Your gp-small confirm t of 1.11 is not an underachievement — it is roughly what
> the ceiling permits.

Two more that bear directly on your survivor:

- **🟢 HXZ (RFS 33(5), 2020): the denominator is load-bearing.** Within
  profitability, **cash-based operating profits-to-assets (Cop) is the strongest
  survivor: 0.63%/mo gross, t=3.44, q-alpha 0.69%/mo t=4.77** — one of only three
  profitability anomalies with q-alpha t≥3. Meanwhile **Fama-French RMW's sorting
  variable, operating profits-to-BOOK-equity (Ope), does not replicate at all:
  0.25%/mo, t=1.2.** Profitability is also the best-surviving family overall (42%
  replicate, highest of six categories), which confirms your closures of
  intangibles (26/103) and trading frictions (7/102). **Actionable: specify
  gp-small's construction as Cop-style (cash-based, assets denominator) and
  register the Ope variant as the pre-declared control.** This is the one finding
  that could *strengthen* your single survivor rather than threaten it.
  Counterweight: HXZ's whole thesis is that small/micro-concentrated effects are
  "more apparent than real" once liquidity is respected — microcaps are 61% of
  firm count but **3.28%** of market cap — which is consistent with your survivor
  scoring only 1.11 net.
- **🔴 JKP: profitability is displaced.** In an ex-post tangency portfolio over
  their 13 theme clusters, only 10 get significantly positive weights, and **the
  three displaced are profitability, investment and size.** Profitability adds
  nothing once other themes are controlled. Directly adverse to your sole
  survivor. Counterweight: JKP are gross, long-short, and capped-value-weighted
  with no turnover or spread adjustment anywhere in the paper — they cannot speak
  to a long-only cost-paying implementation.

**🔴 One instruction for your pre-registration priors.** Chen-Lopez-Lira-Zimmermann
find **theoretical support does not predict post-sample robustness**: agnostic
research retains an extra 31 pp of original performance in FF3+mom alpha terms
but only **9 pp** in raw long-short returns (and 31 pp is the largest of 33
estimates); only 15% of published predictors are supported by any equilibrium
model; risk-attributed predictors decay too; **in half the tests theory-backed
research underperforms pure data mining.** Your taxonomy currently up-weights
candidates with strong literature priors (re_me was registered as a "STRONG
prior" and failed). **Stop treating a mechanism story as evidence of durability.**

---

## 3. The defensive / allocation layer — your TSMOM read is independently confirmed

This is the strongest corroboration in the sweep, and it also tells you what
*not* to do next.

**Independent replication of your own magnitudes.** A portable-alpha overlay
(trend-following + 10-delta SPX put tail hedges) on global equity, 4 Jan 1996 –
30 Jun 2025: CAGR **11.02% vs 8.06%** for ACWI, vol **13.23% vs 15.57%**, Sharpe
**0.37 → 0.66**, monthly alpha 0.25% (~3%/yr, 5% sig) — all **after** a 0.95%
CAGR trading-cost drag and a 1.29% CAGR tail-hedge drag. Worst 3-month
**−19.09% vs −34.34%**.

> Your TSMOM-XA: maxDD **−18.8% vs SPY −33.7%**. Their worst-3-month: **−19.09%
> vs −34.34%**. That is the same number found by different people on a different
> universe. The defensive magnitude is real and replicated.

And the same paper independently reproduces your caveat: **the early-sample
outperformance did NOT persist into recent years — the overlay only kept pace
with equities outside crisis episodes.** Your return-drag t of −1.86 and
"defensive diversifier, not beat-SPY" read is the correct one. Standalone tail
hedging is a persistent **−1.29%/yr** negative carry whose entire payoff is in
crisis windows.

**🔴 Do NOT put a vol-targeting overlay on the gross-profitability book.**
Bongaerts et al. (FAJ 76(4), 2020), US factors 1973-2019, net of costs:
conventional vol targeting changes Sharpe by size **−0.15**, value **−0.13**,
**profitability −0.08**, investment **−0.22**, and only momentum **+0.16**; the
conditional variant is likewise negative for profitability (**−0.09**) and
positive only for momentum (+0.17).

The broader vol-targeting literature has largely collapsed:

- **The headline Moreira-Muir / Harvey results are contaminated by look-ahead** —
  the scaling factor is chosen ex post to hit the vol target over the full
  sample, making the strategies unimplementable.
- Implementable (no look-ahead) vol targeting on 10 equity markets, 1982-2019,
  net: **Sharpe +0.04 only**, and it **increases maximum drawdown in 4 of 10
  markets** (HK +34.4%, UK +9.8%, Canada +4.0%, Australia +4.0%), overshoots the
  target (realized/target 1.18) at ~210% annual one-way turnover.
- Cederburg et al. (JFE 138(1), 2020), 103 US strategies: inverse-variance
  scaling improves Sharpe about as often as it hurts (53 positive / 50 negative;
  8 significantly positive, 4 significantly negative). **In real-time with a
  10-year expanding window, adding the vol-managed version LOWERS
  certainty-equivalent return in 72 of 103 cases.** For the **market factor**
  specifically — your SPY-benchmarked case — real-time management gives OOS
  Sharpe **0.42 vs 0.46 unmanaged** and CER 1.56%/yr vs 1.75%, despite a 4.63%/yr
  in-sample spanning alpha. Requires unretail-able leverage: 99th-percentile
  required leverage exceeds 400% for all nine factors, 864% for momentum.
- Across 45 international markets, **only managed market and momentum are even
  partially robust to transaction costs**; the other seven managed factors
  (including value and profitability) do not survive.

**Two admissible refinements, both registerable:**
1. **Downside volatility rather than total volatility as the scaling variable**
   improves managed market and value performance (gross finding).
2. **State-conditional vol targeting** (scale down only in the top realized-vol
   quintile, lever up only in the bottom, unscaled otherwise, leverage ≤200%)
   beats conventional on every axis: Sharpe **+0.07** vs +0.04, maxDD reduction
   **6.6%**, ES reduction 1.3%, realized/target **0.98**, turnover **1.4×/yr** vs
   2.1× — but significant Sharpe improvement in only **2 of 10 markets**.

---

## 4. LLM / agent alpha — comprehensively dead. Your VOC closure is affirmed with receipts.

This is the cleanest negative result in the sweep, and it is worth a NEG_RESULTS
entry because it closes a family you would otherwise be pressured to revisit.

- **🔴 The flagship paper was WITHDRAWN.** Kim, Muhn & Nikolaev (arXiv 2407.17866),
  the "GPT-4 predicts earnings direction better than human analysts" paper, was
  **withdrawn 2025-02-20 (v3) after a co-author attempting to replicate the
  paper's own prior analyses found inconsistencies in the data and analyses** —
  an internal replication failure within ~7 months of release (confirmed 3-0).
  Its own abstract also conceded GPT-4 merely *matched* a narrowly trained ML
  model, i.e. no accuracy gain over a conventional classifier.
- **🔴 Independent third-party evaluation kills the agent literature.** FINSABER
  (arXiv 2505.07078, KDD 2026 Datasets & Benchmarks, oral; authors independent of
  the systems tested): the reported alpha of **FinMem, FinAgent, FINCON and
  Lopez-Lira-style prompting disappears** when evaluated over **2004-2024 across
  100+ symbols** with survivorship- and snooping-mitigated selection. Over the
  full window, **buy-and-hold Sharpe beats FinMem on 3 of 4 headline names and
  FinAgent on all 4** (B&H TSLA/NFLX/AMZN/MSFT 0.630/0.622/0.551/0.461 vs FinMem
  0.641/0.293/0.188/0.203 and FinAgent 0.546/−0.511/0.389/0.301) — **after
  explicit commissions.** The prior favourable literature rests on a ~6-month
  window (Oct 2022–Apr 2023) and hand-picked large caps. Failure mode is
  **regime-asymmetric** — agents underweight risk in bull markets and overweight
  it in bear markets — so **it is not fixable by adding framework complexity.**
- **Independent replication of Lopez-Lira is explicitly infeasible.** Glasserman &
  Lin (arXiv 2309.17322) reproduce the GPT-3.5 headline-sentiment long-short and
  confirm it is profitable **gross** — with no transaction costs, no short-sale
  constraints, daily open/close rebalancing, equal-weighted, and lower returns
  than originally reported. **The authors say themselves it is not a feasible
  strategy.** Two surprises worth keeping: **look-ahead is not the dominant
  contaminant** — a "distraction effect" from general company knowledge is larger
  and negative, so **anonymizing tickers IMPROVED** gross returns (25.08 → 30.97
  bps/day scraped, p=0.066; 10.74 → 13.84 TR, p=0.017; Jan 2015–Sep 2021) — and
  **LLM edges concentrate in LARGE caps, not small** (long-portfolio mean cap
  $35.4B vs $17.9B, p<0.01; short side larger still). Honest OOS is starved:
  GPT-3.5's Sept-2021 cutoff leaves only **314 trading days**, and the
  original-vs-anonymized difference flips sign and loses significance there.
- **Lookahead is measurable and material where it does bite.** arXiv 2512.23847
  (91,357 headlines, 2012-2023): a 1-SD rise in "Lookahead Propensity" raises the
  LLM signal's marginal effect by **0.067 pp next-day return ≈ 32% of the
  standalone effect** (interaction 0.162, t=3.64) — and **the interaction is
  statistically zero on the post-cutoff 2024 sample (t=1.06)**. The raw signal is
  0.209% next-day (t=12.18), gross, daily-horizon. Same pattern in LLM capex
  forecasts (106,994 firm-quarters, δ=0.512 t=2.01, collapsing post-cutoff).
- **A cheap diagnostic exists** if you ever revisit: Didisheim, Fraschini & Somoza
  (Economics Letters 256, 2025, DOI 10.1016/j.econlet.2025.112602) — prompt the
  model to recall historical returns with no context and use recall accuracy as a
  memorization proxy. Contamination rises with model size and coarser/aggregated
  data; smaller models on finer data show negligible bias. (Paywalled; no
  magnitudes verified.)
- Practitioner-side, for completeness: a self-run FinBERT-vs-Claude test found
  **FinBERT's positive labels produced an INVERTED next-day signal** (positive
  days −0.37%, pos-minus-neg spread −0.03%) despite 86-97% classification
  accuracy — but n = 30 days / 12 semiconductor tickers, so it is anecdote, not
  evidence. Its one durable point matches Tetlock (2007): the signal **peaks at
  lag +1 and vanishes by lag +2**, i.e. structurally incompatible with monthly
  rebalancing.

> **Verdict: no LLM or agent approach has survived an honest, independent,
> cost-aware out-of-sample test. INSTR-VOC's closure stands, now with the
> retraction of the flagship paper and an independent multi-system refutation as
> receipts.** Keep the LLM where you already have it — narrating, never allocating.

---

## 5. Data classes, market structure, and construction — what is and isn't there

### 5.1 🟡 Lazy Prices (10-K/10-Q textual change) — the best-fitting new cross-sectional candidate, with a long-only haircut

Cohen, Malloy & Nguyen (JF 75(3), 2020; 1995-2014):

- Headline **long-short 34-58 bps/mo value-weighted (~7%/yr, t=3.59)** and 18-45
  bps/mo equal-weighted, gross (confirmed 2-0). **Not** the "188 bps/mo / 22%/yr"
  figure sometimes quoted — that is an upper-bound section-level subsample.
- **🔴 The alpha is concentrated in the SHORT leg.** The long ("non-changer") leg's
  positive alpha reverts to zero quickly, while the negative alpha on changers
  persists and grows out to 6 months. **A long-only program captures a small
  fraction of the spread.**
- Not a small-cap/illiquidity artifact by the authors' account: turnover is low
  (annual/quarterly filing dates only — **fits your LOW-turnover house law**),
  VW returns exceed EW, and changers average $3.5B cap vs $2.5B on the long side.
  All returns gross; no net-of-cost backtest.
- **Buildable entirely from free EDGAR full text + your existing panel**
  (confirmed 2-0): strip tables/HTML/XBRL, compute cosine / Jaccard / min-edit
  distance / simple similarity on same-quarter YoY text, quintile monthly on the
  prior month's distribution.
- **Sample ends 2014 and the paper contains no post-publication test.** Strongest
  sub-signals are section-level (risk factors, litigation, CEO/CFO language),
  e.g. 71 bps/mo (t=3.29) Jaccard L/S in the high-litigiousness subsample.

**Why register it anyway:** it is genuinely absent from your 155, uses free data,
is LOW-turnover, and its 2015-2024 window is entirely un-tested in the
literature. Given CZ-CALIB, **a clean post-publication test of a famous
text-based anomaly is itself a publishable result whichever way it lands** — and
your explore/confirm split maps onto it naturally. Honest prior for the long leg:
weak. Register as PICKER with a pre-declared FILTER fallback.

### 5.2 🔴 The index effect is dead — with one live sub-case

Greenwood & Sammon (JF 80(2), 2025, pp. 657-698; 1980-2020, gross):
S&P 500 **addition** abnormal returns **3.4% (1980s) → 7.4% (1990s) → 5.2%
(2000-09) → 1.0% (2010-20, indistinguishable from zero)**; **deletions −4.6% →
−16.1% → −12.4% → −0.6%**.

- **Live sub-case, monthly-implementable:** in the 2010s **direct additions still
  earned +5.4% while migrations from S&P MidCap earned −1.8%** — and migrations
  rose from ~50% of additions in the 1990s to **over 70%**. Conditioning on
  non-migration additions is a concrete, still-nonzero, long-only filter, though
  a shrinking subset and reported as an unconditional event-study mean.
- **🔴 This also undercuts naive inelastic-markets trades.** After adjusting the
  demand shock for migrations, the estimated multiplier fell **by roughly a factor
  of 20** for additions (more for deletions) because active institutions now
  supply the liquidity: trackers buy 7-8% of shares on addition yet total
  institutional ownership barely moves.
- Decay generalizes to Russell 1000/2000, Nasdaq 100 and S&P mid/small — but
  weakly, and **for Russell additions the change is not statistically
  significant**, so Russell reconstitution is not cleanly certified dead.

**On Gabaix-Koijen itself** (NBER WP 28967, June 2021, still an unrevised working
paper as of retrieval): the famous **multiplier of ~5** ($1 of net investment
raises aggregate market value ~$5) is an **aggregate index-level elasticity, not a
cross-sectional signal**, and the paper reports **no strategy, backtest, Sharpe
or net return anywhere**. It bears on market timing at most. Any "inelastic
markets is tradeable" claim must come from successor work. A public data appendix
exists (`nber.org/data-appendix/w28967`) if you ever want to check the flow
measure on free data.

### 5.3 🔴 The 10b5-1 rule change is a structural break in a signal you are LIVE on

The 2022 Rule 10b5-1 amendment (effective early 2023): the share of 10b5-1 sales
occurring **within 90 days of plan adoption collapsed from 31.1% to 1.7%**. **The
predictive content of 10b5-1 insider SALES has been destroyed** — pre-amendment
such sales were followed by significantly negative abnormal returns; post-
amendment by flat or slightly positive returns. Insiders did *not* abandon plans
(usage 52.5% → 50.3% of all insider sales), so the discretionary pool did not
materially grow. The behavioural change concentrates in the previously-abusive
subgroup (−8.6 pp usage among those who had traded within 90 days of adoption),
which identifies **ex-abusers' discretionary trades** as where informed selling
could still live. Separately, two-business-day gift reporting **eliminated the
"reverse V" gift-timing anomaly.** (Secondary source: Columbia Blue Sky blog; no
magnitudes for the pre-period abnormal returns, no gross/net figures.)

**Why this matters to you specifically:** BRAIN-003 is promoted and
TRIAL-CMP-INSIDER-IC is accruing, on an insider panel **extended to 2026Q1** —
i.e. it straddles the break. Your signal is opportunistic *buys*, which this
source does not directly address, so it is not invalidated. But **pooling pre- and
post-2023 insider data in any construction is now known to be unsafe**, and the
routine/opportunistic classifier's treatment of 10b5-1 flags should be audited
against the new regime. Worth a note in the trial doc, not a new registration.

### 5.4 🔴 Free securities-lending data does not exist on your roadmap horizon

FINRA's SLATE — the facility operationalizing SEC Rule 10c-1a loan reporting and
public dissemination — has had its implementation date **pushed to September 28,
2028** (confirmed 3-0). Firm onboarding and customer-test-environment dates are
both TBD, FINRA has not committed to final documentation, and which fields will
be publicly disseminated (rate/fee, quantity, identifier) and at what lag is not
defined on the public page. **Borrow-fee / short-demand signals from free
regulator data are off the table for this program.** Do not put them in the
queue.

### 5.5 🔴 0DTE and dealer-gamma: the practitioner story is falsified

From the 0DTE paper (SSRN 4692190; SPXW, Jan 2012 – Jun 2023):
- The 0DTE variance risk premium is huge annualized (~5× the 11-22 DTE bucket) but
  **collapses to ~0.01% per day, which the authors state is not profitable once
  delta-hedging intensity and realistic costs are accounted for.** The headline
  edge is an annualization artifact.
- **🔴 Aggregate 0DTE open-interest dollar gamma does NOT propagate past
  volatility or raise realized volatility**; for options with more than one day to
  expiry, OI gamma is associated with **LOWER** same-day realized vol. Average
  daily OI gamma **did not grow after 2016.** This falsifies the popular
  dealer-gamma / gamma-squeeze timing signal.
- Intraday shocks to 0DTE volume do not amplify recent index returns; the
  late-vs-early-sample increase in volatility response is **0.15 SD**, which the
  authors call economically negligible.
- The market-structure change is nonetheless real (0DTE went from 5% of SPX
  option volume in 2016 to 50% in Aug 2023; intraday volume correlation with the
  underlying 0.25-0.30 pre-2021 → 0.59 in 2023), and there is a genuine FOMC
  pattern (0DTE/1DTE volume falls before the announcement, rebounds after) — but
  at 30-minute resolution, so **not implementable monthly.**

### 5.6 Construction and after-tax alpha — real, smaller than advertised, and mostly not yours

| Technique | Honest magnitude | Verdict |
|---|---|---|
| **Systematic tax-loss harvesting** | **108 bps/yr** avg after-tax alpha, 500 largest US stocks, **Jul 1926–Jun 2018**, 35% ST / 15% LT. Wash-sale rule cuts to **0.82%**; costs a further ~13 bps. **Regime-dependent: 2.13%/yr (1926-49), 0.51% (1949-72), 1.08% (1972-95), 0.81% (1995-2018).** Largest when returns are low, vol high, dispersion wide. Simulation on CRSP-style data, not a live account. | Real but conditional, and **not an alpha — a tax-timing transfer.** |
| **Direct indexing transition** | **🔴 Usually value-DESTROYING.** Best realistic case (top bracket, only 20% embedded gains, 6% growth, 30bp fee, 10yr, $100k) nets **$3,433 post-tax ≈ 30-50 bps/yr**. Uneconomic above **~10% embedded gains at a 22% marginal rate** and above **~40% top-bracket**. At 70% embedded gains it **destroys $17,976 pre-tax / $4,526 post-tax**. Vendor figures inflated by assuming ordinary-income offset (capped at $3,000/yr) and ignoring the 35-40bp vs ~3bp fee gap. | **Do not build or recommend a transition tool.** |
| **130/30 tax-managed** (BlackRock, JAM 25(5), 2024; Russell 1000, Jun 1995–Jun 2023, 73 overlapping 10-yr paths) | Best scenario tax alpha **+4.39%/yr** (LS) / +1.81% (LO) — but **🔴 pre-tax active return was NEGATIVE net of costs and fees: −0.26% (LS), −0.31% (LO). Tax alpha is the ENTIRE source of outperformance.** Worst of 8 scenarios: after-tax active **−0.08% (LS) / −0.01% (LO)** — fully consumed by costs. LO tax alpha decays **2.87%/yr (worst market quintile) → 0.70% (best)** and with portfolio age. | Requires shorting. Not yours. The honest lesson is the negative pre-tax line. |
| **Rebalancing premium** | **<50 bps/yr** gross under realistic parameters, and **conditional on serial correlation in returns** — a bet on mean reversion, not a mechanical free lunch. Analytical + Monte Carlo, not an empirical net-of-cost backtest. | Small; do not market it as free. |
| **Covered calls** (Israelov & Nielsen, FAJ 71(6), 2015; ~Mar 1996–Dec 2014) | The short-vol leg that actually harvests the premium has Sharpe ~1.0 but is **<10% of total strategy risk**; **~one quarter of risk is an uncompensated embedded equity-reversal (market-timing) bet.** Risk-managed variant improves Sharpe by *removing* that exposure, gross of the daily delta-hedging costs it requires. Sample predates volmageddon, COVID and the JEPI/QYLD era. | **An inefficient wrapper around the one premium it contains.** |
| **Factor timing** | Asness, "The Siren Song of Factor Timing" (JPM 2016): timing on factor valuation spreads is **historically very weak**; the commercial incentive to oversell it is why it is marketed. | Static tilts. |
| **"Structural alpha" via construction** (Berkin & Wang, J. Beta Investment Strategies, Spring 2026) | Claims incremental alpha from four construction levers **without any new factor discovery**, on a 5×5 size/value grid, **Jul 1963–Jun 2023**. **🟡 Quantitative content UNVERIFIED** — the Substack is a teaser; figures (e.g. smallest-deep-value alpha 1.97% → 4.53%) appear only in a Morningstar mirror with no gross/net statement. Journal version: pm-research.com/content/iijindinv/17/1/36. | **Most on-thesis paper in the sweep. Fetch the actual PDF before acting.** |

**Scoping note:** tax-loss harvesting is worth approximately nothing to you
personally — Hong Kong levies no capital gains tax — and nothing in a
tax-advantaged account. It is relevant only to US taxable-account users of the
product, and then mainly to *new cash-funded* accounts in volatile markets.

### 5.7 Unverified practitioner claims — flagged, not adopted

From a secondary aggregator (QuantSeeker weekly recap), none independently
confirmed; **I could not verify the underlying papers exist** and they must be
prior-checked before any registration:

- **"Reviving Anomalies"** (Beckmeyer, Berg, Wiedemann, Wortmann): claims ML
  expected-return + cost filtering raises implementable anomalies **from 10 to
  100**, with a 1/N portfolio delivering **12-16%/yr and Sharpe up to 1.0**.
  **🔴 If real, this is directly adverse to your empty-cost-cohort finding** and
  must be engaged in the paper. Sample period and whether returns are net of the
  modeled costs were not stated. **Highest-priority verification target.**
- IV call-put gap: 25-30 bps/week alpha, 1996-2024; options **volume** signals
  weaken and reverse after 2020 due to retail flow, surviving mainly in
  hard-to-short names. Weekly horizon.
- "Factor Uncertainty Index": OOS R² ~10-13%, Sharpe 1.25 → 1.53 via risk
  scaling. Factor timing via vol scaling, not a new factor.
- Zakamulin, "Rethinking Trend Following": regime-dependent position sizing lifts
  trend Sharpe 0.41-0.57 → 0.56-0.73 (US), 0.05 → 0.30 (international), 0.21 →
  0.51 (diversified). Sizing refinement — **relevant to TSMOM-XA if it verifies.**
- "Deep Momentum" (Han & Qin): claims 41%/yr and Sharpe ~2.5 vs 21%/1.0.
  **Complexity class you already rejected; magnitude implausible for long-only.
  Ignore.**
- A paywalled practitioner post claims trend-following Sharpes degraded after
  2008 and that chart patterns are fully arbitraged — assertions with no data,
  sample, or cost accounting. Its actual "where edge exists" section is behind the
  paywall. No evidential weight.

One real but off-scope datum: the **January effect in municipal-bond closed-end
funds has strengthened post-publication** and remains consistent with tax-loss
selling, while the same effect in muni **ETFs** is smaller and not explained by
tax-loss selling — i.e. the **fund wrapper drives the seasonal, not the asset
class** (Carrion & Zhang, J. Financial Research 47(4):1207-1227, 2024). Magnitude
UNVERIFIED (paywalled). Wrong asset class for a long-only US equity program;
indirect evidence at best for equity December seasonality.

---

## 6. 🔴 The retail mission — the evidence contradicts the product thesis

This is the most decision-relevant section in the sweep and it cuts against
"make the engine an expert and then give advice."

**Financial education does essentially nothing.** A meta-analysis of **168 papers
/ 201 prior studies** finds financial-education interventions explain **0.1% of
the variance** in downstream financial behaviors. Effects **decay with time since
instruction** — even high-dosage, many-hour interventions show negligible
behavioral effect at **20+ months**. The familiar "literate investors do better"
correlation **shrinks dramatically** once omitted psychological traits are
controlled. Effects are **weaker, not stronger, in low-income samples.** The
authors' prescription: education must be **narrow and just-in-time**, tied to the
specific behavior it is meant to change, with choice architecture carrying the
rest.

**The behavior gap that justifies "coaching" is largely a methodological
artifact.** Re-analyzing Morningstar's own dataset, a 2026 FAJ paper finds poor
timing costs fund investors **only 0.10%/yr — a ~92% reduction from the 1.2%/yr
headline.** The discrepancy is methodological, in how purchase/sale timing and
magnitude are computed, not a different sample. And **Morningstar itself
disclaims the "dumb money" reading**: the gap is a pooled portfolio-level IRR,
explicitly *not* the average investor's return, and is mechanically generated
even by perfectly disciplined behavior (paycheck contributions, rebalancing).

Morningstar's 2025 figures, for what they are worth (~25,848 funds, 10 yrs to
Dec 31 2024, net of fund expenses, before investor taxes/commissions): dollar-
weighted 7.0%/yr vs asset-weighted 8.2% = **−1.2 pp**, stable not growing
(−1.7/−1.7/−1.7/−1.1/−1.2 in rolling windows 2020-24). What the cross-section
says matters:

- **Trading activity is the strongest correlate.** Cash-flow-volatility quintiles
  gap **−0.8% (least) to −1.8% (most)**; the average dollar in the least-traded
  quintile earned **8.2%/yr vs 4.7%** in the most-traded.
- **Structure that automates allocation nearly eliminates the gap.** Allocation /
  target-date funds gap **−0.1 pp** (~97% captured) and large-blend **+0.1 pp**,
  versus sector equity **−1.5 pp** and large growth −1.0 pp. High-tracking-error
  funds gapped −1.6 pp vs −0.9 pp for the lowest quintile.
- **🔴 Fee reduction and indexing do NOT close it.** Index funds gapped −1.3 pp/yr
  vs active −1.5 pp, and passive gaps were **wider** than active in international
  equity (−2.0% vs −0.6%) and sector equity. **ETFs gapped wider (−1.7 pp) than
  open-end funds (−1.2 pp)** despite higher raw returns.

**Automated advice helps — but only the currently-undiversified, and only through
allocation.**

- RFS 32(5), 2019 (Indian brokerage Markowitz tool, 2015-2017): ex-ante
  undiversified investors (1-2 stocks) **roughly doubled** holdings; investors
  holding >10 stocks **reduced** holdings. Market-adjusted volatility fell
  **2.07%/yr** overall, monotonically concentrated in the least diversified.
  **🔴 For already-diversified investors: no performance gain, but higher costs
  and activity** — fees +155 rupees/mo (~15% of base), logins +~10%. Debiasing is
  partial: disposition effect −~30%, rank effect −~26%, **trend chasing only
  −1.2%**; none eliminated. Portfolio performance improved significantly **only**
  for the ex-ante underdiversified; per-trade performance improvement was not
  significant even on average.
- JFE 155 (2024), Wealthfront, structural life-cycle model: robo access is worth
  **0.8% of lifetime consumption** to new less-wealthy participants. **The gain
  comes almost entirely from allocation mechanics — diversification and bond
  risk-factor exposure. Removing either cuts the gain by 70%; removing the
  equity-market-exposure difference changes welfare almost not at all.**
  Benefits skew **old**: 1.7% for 55+, 0.6% for under-35 (~3×). Democratization
  is access-constrained: cutting the minimum $5,000 → $500 raised 2nd/3rd
  wealth-quintile participation **107% (16 pp)** while the bottom quintile did
  not move at all.

> **What the evidence says the highest-value deliverable actually is:** automated
> allocation, automatic rebalancing, diversification for the currently-
> undiversified, and *less trading* — delivered as product structure and
> defaults, targeted at older, low-investable-wealth households. **Forecasting
> and prediction content is the least-supported thing you could ship**, and
> sophisticated analytics delivered up-front to less-resourced users has a
> measured effect indistinguishable from zero.
>
> This does not mean the engine is wasted. It means the engine's job is to set
> the allocation and then get out of the way — not to produce views for users to
> act on. Your crash/regime machinery is already labeled descriptive-never-arms;
> that is the correct posture, and the retail evidence says it should extend to
> the whole product surface.

---

## 7. Ranked recommendations

Ranked by (honest expected edge) × (feasibility under your constraints) ×
(novelty vs the 155).

| # | Action | Why it ranks here |
|---|---|---|
| **1** | **Register rebalance-date randomization** for all live lanes (INSTR class, ALLOCATOR/implementation role). | Only finding that is long-only, no-short, no-leverage, monthly, free, needs no new data, and applies to lanes you already run. **>8 bps/yr → 0.6 bps** measured price-impact saving at ~35 bps tracking error. Certain, small, free. Also removes you as the predictable counterparty at month/quarter-end. |
| **2** | **Re-specify gp-small as Cop-style** (cash-based operating profits / assets) with Ope as the pre-declared control arm. | Directly strengthens your only survivor on independent evidence: **Cop 0.63%/mo t=3.44, q-alpha t=4.77; Ope 0.25%/mo t=1.2.** Cheap — same data, same turnover. |
| **3** | **Reposition the paper**: lead with the method + empty cost cohort; demote −0.544 to supporting; add a SignalDoc-own-construction robustness arm. | McLean-Pontiff Fig 1.B is prior art; Chen-Zimmermann pre-arms the construction objection; JKP's positive slope is the rebuttal you must answer. Protects the paper's actual novelty. |
| **4** | **Rewrite batch 10 as a FILTER, not a picker** — distress-item avoidance screen (bankruptcy, control change, obligation acceleration), on **daily-index** snapshots. | Documented drift is real but **negative and on the short leg**; good news reacts at the event date, not the filing. Registering a long-only item-level picker points at a prior you now know is weak-to-negative. |
| **5** | **Register Lazy Prices (10-K textual change)** as PICKER with a FILTER fallback, explore 2004-2018 / confirm 2019-2024. | Genuinely absent from your 155, free EDGAR data, **LOW turnover (fits house law)**, and the post-2014 window is untested in the literature — publishable either way given CZ-CALIB. Haircut: alpha is short-leg-concentrated. |
| **6** | **Verify "Reviving Anomalies"** before the paper freezes. | If real (10 → 100 implementable anomalies, 12-16%/yr, Sharpe ~1.0) it is **directly adverse to your headline finding**. Cheap to check; expensive to be blindsided by at review. |
| **7** | **Fetch the Berkin-Wang "Structural Alpha" PDF.** | Most on-thesis source found — construction levers instead of factor discovery, on a 5×5 grid 1963-2023. Currently UNVERIFIED (teaser only). Could reframe where you spend the next 20 trials. |
| **8** | **Audit the insider classifier against the 2023 10b5-1 break**; note it in the trial doc. | Your panel straddles a break that **destroyed the predictive content of 10b5-1 sales** (31.1% → 1.7% short-window trading). Your signal is buys, so probably unaffected — but pooling pre/post-2023 is now known-unsafe. |
| **9** | Register **state-conditional** and/or **downside-vol** scaling as TSMOM-XA refinements. | +0.07 vs +0.04 Sharpe, maxDD −6.6%, turnover 1.4× vs 2.1×, realized/target 0.98 — but significant in only 2 of 10 markets. Modest, honest, and it is the *right* variant if you do this at all. |
| **10** | **Add a NEG_RESULTS entry closing the LLM/agent-alpha family** with the new receipts. | Flagship paper withdrawn after internal replication failure; independent multi-system evaluation finds the alpha disappears 2004-2024 after commissions; the one honest replication is self-described as infeasible. Closes a family you'd otherwise be lobbied to revisit. |
| — | **Do NOT** vol-target the profitability book; **do NOT** build a direct-indexing transition tool; **do NOT** queue borrow-fee signals before 2028; **do NOT** pursue dealer-gamma or 0DTE timing; **do NOT** up-weight candidates for having a mechanism story. | Each has an explicit receipt above. |

---

## 8. Sources (42, re-matched to correct URLs by bibliographic content)

Verification key: **[C]** = confirmed by surviving adversarial votes (real
tally); **[S]** = single-source extraction with verbatim quote, un-cross-examined;
**[U]** = abstract-only or paywalled, magnitudes UNVERIFIED. All refutation
verdicts from the harness are void (§0).

**8-K / EDGAR plumbing**
1. [S] Lerman & Livnat, "The New Form 8-K Disclosures," *Review of Accounting Studies* 15(4):752-778, 2010 (SSRN 1126816). Sample 2005-2006. https://pages.stern.nyu.edu/~jlivnat/f8k%20current.pdf
2. [C] 8-K item-taxonomy / event-heterogeneity study, 182,174 events 2022-2026 (LLM-tagged corpus, vendor-distributed; explicitly disclaims return prediction). https://arxiv.org/abs/2607.08346
3. [C] SEC, "Accessing EDGAR Data" + Developer Resources (10 req/s aggregated; full/quarterly indexes retroactively rebuilt Saturdays; daily indexes are the PIT-safe source; 5-field index, no item tags; after-5:30pm ET filings disseminate next business day). https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
4. [S] EDGAR full-text-search API practitioner guide (100-result cap, `from` pagination, form+date filters, **no item-level filter**; bulk products as the scalable path). *Blog.* https://tldrfiling.com/blog/sec-edgar-full-text-search-api

**Replication crisis / where edge remains**
5. [S] Chen & Welch, "What Useful Alphas?" arXiv 2607.06502 (48 → 7 bps/mo; residual killed by luck *or* costs). https://arxiv.org/abs/2607.06502
6. [S] Chen, Lopez-Lira & Zimmermann (peer review vs 29,000 mined ratios; post-2004 VW predictability dead, EW retains +16.3 bps/mo; theory does not predict robustness). https://arxiv.org/abs/2212.10317
7. [S] Chen & Zimmermann, publication-bias survey (EB shrinkage removes only 10-15%; FDR <10%; "alternative portfolio tests" caveat). https://arxiv.org/abs/2209.13623
8. [S] Jensen, Kelly & Pedersen, "Is There a Replication Crisis in Finance?" *JF* 78(5), 2023 — NBER WP version. https://www.nber.org/papers/w28432
9. [S] — published version (82.4% replication; positive IS→OOS slope; profitability displaced in tangency). https://onlinelibrary.wiley.com/doi/full/10.1111/jofi.13249
10. [S] Hou, Xue & Zhang, "Replicating Anomalies," *RFS* 33(5):2019-2133, 2020 (65% fail |t|≥1.96, 82% fail 2.78; **Cop 0.63%/mo t=3.44 vs Ope 0.25%/mo t=1.2**). https://academic.oup.com/rfs/article-abstract/33/5/2019/5236964
11. [S] McLean & Pontiff, "Does Academic Research Destroy Stock Return Predictability?" *JF* 71(1):5-32, 2016 (58.2 → 40.2 → 26.4 bps/mo; **decay increasing in in-sample t: −0.146 / −0.151 per SD; Fig 1.B**). Cite 26%/58% from the JF version, **not** the 10%/35% 2012 working paper. https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365

**Defensive / allocation layer**
12. [S] Bongaerts, Kang & van Dijk, volatility targeting, *FAJ* 76(4):54-71, 2020 (look-ahead in Moreira-Muir scaling; implementable Sharpe +0.04; **profitability −0.08**; state-conditional +0.07). https://www.tandfonline.com/doi/full/10.1080/0015198X.2020.1790853
13. [S] Cederburg, O'Doherty, Wang & Yan, "On the performance of volatility-managed portfolios," *JFE* 138(1):95-117, 2020 (103 strategies; real-time CER lower in 72/103; market factor OOS Sharpe 0.42 vs 0.46). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3357038
14. [S] Volatility-managed factors across 45 markets, *J. Empirical Finance* 80, 2025, DOI 10.1016/j.jempfin.2024.101560 (only market and momentum partially cost-robust; downside vol a better scaler). https://www.sciencedirect.com/science/article/pii/S092753982400094X
15. [S] Portable-alpha overlay (trend + 10-delta SPX puts) on ACWI, *Investment Analysts Journal*, 2025, DOI 10.1080/10293523.2025.2553254 (Sharpe 0.37→0.66 after 0.95% cost and 1.29% hedge drag; worst 3-mo −19.09% vs −34.34%; **outperformance did not persist recently**). https://www.tandfonline.com/doi/full/10.1080/10293523.2025.2553254

**LLM / agent alpha**
16. [C] Kim, Muhn & Nikolaev — **WITHDRAWN 2025-02-20** after internal replication failure. https://arxiv.org/abs/2407.17866
17. [S] FINSABER — independent evaluation, 2004-2024, 100+ symbols; LLM-agent alpha disappears after commissions; regime-asymmetric failure. KDD 2026 D&B, oral. https://arxiv.org/abs/2505.07078
18. [S] Glasserman & Lin — independent replication of GPT news sentiment; profitable gross, **authors state it is infeasible**; anonymization *improves* returns; edge concentrates in **large** caps. https://arxiv.org/abs/2309.17322
19. [S] Lookahead Propensity study (~32% of the LLM signal's marginal effect is memorization; interaction zero post-cutoff). https://arxiv.org/abs/2512.23847
20. [U] Didisheim, Fraschini & Somoza, *Economics Letters* 256, 2025, DOI 10.1016/j.econlet.2025.112602 (recall-accuracy diagnostic; paywalled). https://ideas.repec.org/a/eee/ecolet/v256y2025ics0165176525004392.html
21. [S] FinBERT-vs-LLM practitioner test (n=30 days, 12 tickers — anecdote; signal peaks lag+1, gone by lag+2). *Blog.* https://tommijohnsen.substack.com/p/can-llms-beat-finbert-for-stock-sentiment

**Data classes / market structure**
22. [C] Cohen, Malloy & Nguyen, "Lazy Prices," *JF* 75(3):1371-1415, 2020 (34-58 bps/mo VW gross, 1995-2014; **short-leg concentrated**; buildable from free EDGAR). https://onlinelibrary.wiley.com/doi/10.1111/jofi.12885
23. [S] Greenwood & Sammon, "The Disappearing Index Effect," *JF* 80(2):657-698, 2025 (additions 7.4% → 1.0%; direct +5.4% vs migrations −1.8%; multiplier fell ~20×). https://onlinelibrary.wiley.com/doi/10.1111/jofi.13410
24. [S] Gabaix & Koijen, "In Search of the Origins of Financial Fluctuations," NBER WP 28967, June 2021 (multiplier ~5, **aggregate only, no strategy or backtest**). https://www.nber.org/papers/w28967
25. [S] Rebalancing-pressure / front-running study, NBER WP 33554, Mar 2025 rev. Jan 2026 (**randomized rebalance date: >8 bps/yr → 0.6 bps**; front-running Sharpe 1.11 but requires shorting + daily trading). https://www.nber.org/papers/w33554
26. [S] 0DTE options study, SSRN 4692190 (VRP ~0.01%/day, not profitable after hedging + costs; **OI gamma does not propagate volatility**). https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4692190
27. [C] FINRA SLATE — securities-lending transparency **delayed to Sept 28, 2028**; onboarding TBD. https://www.finra.org/filing-reporting/slate
28. [S] Insider trading after the 2022 Rule 10b5-1 amendment (31.1% → 1.7%; 10b5-1 **sales** signal destroyed; gift "reverse V" closed). *Secondary/blog.* https://clsbluesky.law.columbia.edu/2025/07/31/insider-trading-after-the-2022-rule-10b5-1-amendment/
29. [U] Carrion & Zhang, muni CEF/ETF January effect, *J. Financial Research* 47(4):1207-1227, 2024, DOI 10.1111/jfir.12384 (effect strengthened post-publication; **magnitudes unverified, paywalled**). https://onlinelibrary.wiley.com/doi/abs/10.1111/jfir.12384

**Construction / after-tax**
30. [S] Chaudhuri, Burnham & Lo, tax-loss-harvesting alpha, *FAJ* 2020 (108 bps/yr 1926-2018; 0.82% after wash-sale; regime range 2.13% → 0.51%). https://rpc.cfainstitute.org/research/financial-analysts-journal/2020/empirical-evaluation-tax-loss-harvesting-alpha
31. [S] Direct-indexing transition analysis (best case ~30-50 bps/yr; **negative above ~10-40% embedded gains**). *Blog.* https://alphaarchitect.com/transitioning-from-an-etf-to-direct-indexing-bad-idea/
32. [S] BlackRock tax-managed long-only vs 130/30, *J. Asset Management* 25(5):445-459, 2024 (**pre-tax active return negative net of costs**; after-tax edge → ~0 in worst scenario). https://link.springer.com/article/10.1057/s41260-024-00374-z
33. [S] Rebalancing premium, *Quantitative Finance* 25(12):2021-2034, 2025 (**<50 bps/yr**, conditional on serial correlation). https://www.tandfonline.com/doi/abs/10.1080/14697688.2025.2577822
34. [U] Israelov & Nielsen, "Covered Calls Uncovered," *FAJ* 71(6), 2015 (short-vol leg <10% of risk; ~¼ of risk uncompensated reversal) — sample dates from a secondary summary, PDF not rendered; page served Asness, "The Siren Song of Factor Timing," *JPM* 2016. https://www.aqr.com/Insights/Research/Journal-Article/The-Siren-Song-of-Factor-Timing
35. [U] Berkin & Wang, "The Incredible Structural Alpha," *J. Beta Investment Strategies*, Spring 2026 — **quantitative content unverified**; journal version at pm-research.com/content/iijindinv/17/1/36. https://larryswedroe.substack.com/p/the-incredible-structural-alpha

**Retail mission**
36. [S] Fernandes, Lynch & Netemeyer, financial-literacy meta-analysis, *Management Science*, 2014 (**0.1% of variance**; decay past 20 months; weaker in low-income samples). https://pubsonline.informs.org/doi/10.1287/mnsc.2013.1849
37. [S] "Bad Timing Does Not Cost Investors Much," *FAJ* 82(3), 2026, DOI 10.1080/0015198X.2026.2657253 (**0.10%/yr, not 1.2%**). https://rpc.cfainstitute.org/research/financial-analysts-journal/2026/bad-timing-does-not-cost-investors-funds-returns
38. [S] Morningstar, *Mind the Gap 2025* (−1.2 pp; allocation funds −0.1 pp; **index −1.3 vs active −1.5**; ETFs wider; Morningstar's own disclaimers). https://www.morningstar.com/content/cs-assets/v3/assets/blt9415ea4cc4157833/blt2c5c4d9171638c42/689b424311f3880edc4b4813/US_Mind_the_Gap_2025.pdf
39. [S] "The Promises and Pitfalls of Robo-Advising," *RFS* 32(5):1983-2020, 2019 (gains only for the ex-ante undiversified; costs rise for the rest). https://academic.oup.com/rfs/article-abstract/32/5/1983/5427774
40. [S] Robo-advice welfare, *JFE* 155, art. 103829, 2024 (**0.8% of lifetime consumption; ~all from allocation mechanics**; skews old; access-constrained). https://www.sciencedirect.com/science/article/abs/pii/S0304405X24000527

**Unverified aggregator**
41. [U] QuantSeeker weekly recap — "Reviving Anomalies," IV call-put gap, Factor Uncertainty Index, Zakamulin trend sizing, Deep Momentum. **Underlying papers not verified to exist.** https://www.quantseeker.com/p/weekly-research-recap-ee0
42. [U] Practitioner "where edge exists" post — forward-looking claims paywalled; no evidential weight. https://ryanswright.substack.com/p/edge-isnt-yours-what-actually-works

---

## 9. Open items before batch 10 freezes

1. `prior_check` the reframed 8-K FILTER design and the Lazy Prices family (word-split + stems, per the round-7 hardening).
2. Verify "Reviving Anomalies" exists and read it — it is the one live threat to the paper's headline.
3. Fetch the Berkin-Wang PDF for real magnitudes.
4. Decide the 8-K PICKER-vs-FILTER question. My recommendation is FILTER, with Item 2.02 declined on prior-check grounds (PEAD closed, sign inverted).
5. Ceiling re-registration at ~196 is unaffected by this sweep — cumulative count stays 155 until batch 10 registers.
6. Attended, unchanged: TSMOM-XA flags to unset, PDUFA SCPH scoring ~late Aug, conviction-lane decisions, quarterly CMP/SMQ refresh ~Oct, `xint` on the next WRDS want-list.
