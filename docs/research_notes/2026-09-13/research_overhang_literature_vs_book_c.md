# Research note — disposition-overhang conditioner (Book C) vs the published literature

Status: COMPLETE first pass. Primary-source PDFs for Grinblatt-Han and Frazzini were
fetched and parsed directly (text extracted via PyMuPDF from the NBER working-paper
and NYU Stern preprint copies — the published JFE/JF typeset versions are paywalled,
so page/table numbers below are the working-paper/preprint numbering, which matches
the published tables in content). An (2016) is sourced from its RFS abstract (multiple
independent citations converged on identical wording) — full text not fetched, flagged
below. Riley-Summers-Duxbury (2020) is a genuine post-2016 US-equity replication, full
text fetched.

## 0. Our result (source: `backend/data/optimus/first_books/replay/disposition_overhang_conditioner_v0_2026-09-12T215811Z.json`)

- `mean_book_net_monthly` 1.1877%/mo, `mean_twin_net_monthly` 0.7899%/mo,
  **`mean_excess_net_monthly` = 0.3978%/mo ≈ +0.40%/mo net**, NW lag-2 t =
  **2.1283**, p (two-sided) 0.03331, n_blocks 395, k=30/side, flat cost 25 bps/side
  (`cost_curve: flat_25bps_pending_5c` — the empirical cost curve from chunk 5c has
  not yet been applied).
- By era: 1990-99 +0.112%/mo t 0.286 (95 blocks); 2000-09 +0.667%/mo t 1.636
  (120 blocks); 2010-16 +0.411%/mo t 1.528 (84 blocks); 2017-24 +0.333%/mo t 1.069
  (96 blocks).
- **Construction note worth flagging to whoever reads this book next**: the
  registered `slice_period` (TRIAL-DRAFT-C §4) declares a 1995-01-01 start
  specifically because "the CGO lookback is 1,260 sessions and the CRSP daily files
  begin 1990, so the first five years are warmup." The receipt's `by_era` table
  nonetheless reports a full 1990-1999 bucket (95 blocks) built on **only 24 months**
  of price/turnover history (`scripts/night_first_books_replay.py` line ~608:
  `if len(h[0]) >= 24: ... capital_gains_overhang(..., lookback=60)`), not the
  60-month lookback the recursion itself uses once warm. The weakest era (1990s,
  t 0.29) is exactly the era running on truncated CGO history — a plausible
  **mechanical** explanation for that era's weakness, distinct from anything the
  literature would predict (see §2).
- Construction (source: `backend/services/book_signals.py` lines 316-378,
  `docs/TRIALS/TRIAL-DRAFT-C-disposition-overhang-conditioner-v0.md` §2): Grinblatt-
  Han price/turnover-only reference price, `RP_t = (1/k) Σ V_{t-n} Π(1-V)_{t-n+τ}
  P_{t-n}`, `CGO_t = (P_{t-1}-RP_t)/P_{t-1}`; contract lookback T=1260 trading days
  (~5y); the monthly replay uses `lookback=60` months (an equivalent ~5y at monthly
  cadence — faithful to the contract's intent when warm). News sign v0 =
  `sign(numup-numdown)` from the IBES EPS fpi=1 consensus panel at `statpers`,
  monthly. Top **tercile** of CGO within the good-news-only eligible set
  (`overhang_conditioned_ranks`, gate-then-rank). Twin = identical good-news
  universe, unconditioned, first 30 permnos sorted (`select_unconditioned`) — **not
  turnover-matched**, per the receipt's own `twin_turnover_matched: false`.

## 1. The published magnitudes

**Grinblatt & Han** — the numbers below come from NBER Working Paper 8734, "The
Disposition Effect and Momentum" (Jan 2002), Mark Grinblatt and Bing Han, which is
the direct predecessor draft of the published Grinblatt & Han (2005), "Prospect
Theory, Mental Accounting, and Momentum," *Journal of Financial Economics* 78(2):
311-339 — same data, same regression specifications, same tables (confirmed by
cross-checking table numbers and text against secondary descriptions of the
published version). Source:
https://www.nber.org/system/files/working_papers/w8734/w8734.pdf (fetched and
parsed directly, text saved locally).

- **Sample**: NYSE + AMEX common stock (mini-CRSP), weekly, **July 1967 – December
  1996**, 1,539 weekly cross-sections, requiring 5 years of trading history per name
  before inclusion.
- **The `g` (capital-gains-overhang) regressor's own distribution** (Table I Panel
  A): mean 0.0560, median 0.1062, SD 0.2508, 10th percentile −0.2810, 90th
  percentile 0.3122.
- **Table II Panel C** (Fama-MacBeth, `r = a0 + a1·r₋₄:₋₁ + a2·r₋₅₂:₋₅ +
  a3·r₋₁₅₆:₋₅₃ + a4·V̄ + a5·s + a6·g`, all months): coefficient on `g`, **a6 =
  0.0040/week, t = 7.79**. This is a RAW weekly-return regression coefficient (size-
  and past-return-controlled, not a factor-model alpha), from an unweighted
  (effectively equal-weighted) cross-sectional OLS, gross of any transaction cost.
  Back-of-envelope economic magnitude: moving `g` from its 10th to 90th percentile
  (spread 0.593) implies **0.0040 × 0.593 ≈ 0.237%/week ≈ ~1.0%/month**, raw, gross,
  roughly equal-weighted. This is an approximation from the continuous-regressor
  coefficient, not a reported decile-portfolio spread — the paper (this version)
  does not report a separate decile long-short table for `g` alone.
- **Momentum literally disappears when g is added** — the headline claim, with
  exact numbers: without `g` (Table II Panel B, "All"), the intermediate-horizon
  past-return coefficient **a2 = 0.0014, t = 3.57** (significant, the classic
  momentum effect). With `g` added (Table II Panel C, "All"), **a2 = −0.0002, t =
  −0.68** (insignificant, sign flips negative). The `g` coefficient itself is
  essentially unaffected by which controls are included (a6 stable at ~0.0040-0.0050
  across specifications in Table III). This decay in a2 IS the paper's "momentum
  effect disappears" result, precisely quoted.
- **Seasonality caveat the paper reports itself**: in the January-only row of Table
  II Panel C, a6 goes **negative** (−0.0117, t=−4.95) — Grinblatt-Han attribute this
  reversal to December tax-loss-selling unwinding in January. This is a documented
  falsifier candidate (§4).

**Frazzini (2006)**, "The Disposition Effect and Underreaction to News," *Journal of
Finance* 61(4):2017-2046. Source: NYU Stern preprint,
https://pages.stern.nyu.edu/~afrazzin/pdf/The%20Disposition%20Effect%20and%20Underreaction%20to%20news%20-%20Frazzini.pdf
(fetched and parsed directly).

- **Sample**: mutual-fund holdings 1980-2002 (his reference price is built from
  actual fund-level cost bases, NOT a turnover proxy — see §3), equally-weighted
  quintile portfolios, Fama-French (1993) three-factor alphas throughout Tables
  IV-VIII (i.e., these are RISK-ADJUSTED returns, not raw).
- **Baseline (unconditioned) PEAD, Table IV**: long top-20% good-news stocks, short
  bottom-20% bad-news stocks (news = 4-day CAR around the earnings announcement,
  −2 to +1 days), 3-month rolling hold: **FF3 alpha 1.242%/month, t = 10.78**. The
  single "good news only" quintile leg (long-only, unconditioned by overhang), 3-month
  hold: **0.618%/month, t = 4.45** — this is the closest published analogue to our
  `unconditioned_reaction_book_v0` twin leg (0.79%/mo net, in the same ballpark of
  order of magnitude, though units differ: his is a risk-adjusted alpha on an
  actual top-quintile-of-thousands book, ours is a 30-name net-of-cost book).
- **The overhang-conditioned spread, Table V/VI** — "raw overhang" here means the
  overhang variable used for sorting is NOT first orthogonalized against past
  returns (as opposed to "residual overhang," see below) — **NOT raw returns**;
  both numbers below are still FF3 alphas: a strategy long top-20% good-news names
  in the **top overhang quintile** and short bottom-20% bad-news names in the
  **bottom overhang quintile** delivers **2.433%/month, t = 6.60** (using the raw
  overhang variable) or **2.201%/month, t = 6.56** (using overhang orthogonalized
  against past returns — "residual overhang," his own analogue of our falsifier #2).
  Both are GROSS of transaction costs, equal-weighted, risk-adjusted (FF3 alpha).
- **The sign-flip placebo** (his "negative overhang spread": long good-news/bottom-
  overhang i.e. large LOSS, short bad-news/top-overhang i.e. large GAIN): "**post-
  event returns of the negative overhang spread are not significantly different
  from zero**." Table VI: the overhang-spread portfolio (#5) is statistically
  different from the negative-overhang-spread portfolio (#1), **t = 3.64**, and
  "the induced difference is economically large, being over 200 basis points per
  month" — i.e. portfolio #1 (the placebo) sits at or below roughly 2.433% − 2.00%
  ≈ 0.4% or less and is not significant, consistent with ≈0.
- **Net of realistic trading costs, Table VIII, "All" stocks**: gross FF3 alpha
  2.447%/month (3-month) / 1.922%/month (6-month); modeled round-trip cost
  (TAQ-based effective spread + commissions, discount-brokerage schedule, 1993-2002
  estimated back to 1980) ≈ 4.55%/4.58% per round trip against ~34%/19% average
  monthly turnover; **net alpha 0.885%/month (3-month) / 1.062%/month (6-month)**.
  Costs are far higher for small caps (quintile-1 effective spread+commission
  7.67%) than large caps (quintile-5, 1.44%), and the strategy's own gross alpha is
  larger for small caps too (2.777% vs 1.308%, 3-month) — the effect **does**
  concentrate in less-liquid names, as our own contract's §C.3 note anticipated
  ("re-measure at the $10M corner too").

**An (2016)**, "Asset Pricing When Traders Sell Extreme Winners and Losers," *Review
of Financial Studies* 29(3):823-861. **Not independently verified against full text**
— sourced from the abstract, cross-confirmed identically worded across three
independent citing sources (SSRN listing, CFA Institute digest, Columbia working-
paper page): "Stocks with both large unrealized gains and large unrealized losses,
aggregated across investors, outperform others in the following month (trading
strategy monthly alpha = **0.5-1%, Sharpe ratio = 1.5**). This effect cannot be
explained by momentum, reversal, volatility, or other known return predictors, and
**it also subsumes the previously documented capital gains overhang effect**." This
is the "V-shaped" variant: both tails (large gain AND large loss) predict higher
future returns, not just the sign-aligned tail Frazzini and our Book C use. Sample
period, universe and exact table numbers: **not found** in the fetchable sources —
mark any further reliance on this number as abstract-only.

**Post-2016 replication — Riley, Summers & Duxbury (2020)**, "Capital Gains
Overhang with a Dynamic Reference Point," *Management Science* 66(10):4726-4745.
Source: open-access working-paper PDF,
https://eprints.whiterose.ac.uk/id/eprint/146448/1/Riley%20Summers%20Duxbury%20Capital%20Gains%20Overhang.pdf
(fetched and parsed directly). This is a genuine, independent, post-2016 US-equity
test — **the single most decision-relevant thing found in this pass** (see §5).

- **Sample**: US common stock (CRSP share codes 10 & 11), January 1958 – December
  2016 for the market-data tests (a separate 1963-2016 dataset is used for the
  event-window/robustness section).
- **Table 4 (Fama-MacBeth, raw CGO, not decile-ranked)**: `CGO` coefficient
  **0.00511, t = 4.429** — the classic sign and significance of the disposition-
  overhang effect **survives** to a sample ending in Dec 2016.
- **Critically, `Mom` (12-month momentum, skip-month) stays significant in the SAME
  regression**: **0.00491, t = 2.934** — momentum does **not** die when CGO is
  added, contradicting Grinblatt-Han's 1967-1996 finding almost exactly (§1 above:
  a2 goes from t=3.57 to t=−0.68 in G&H; here Mom stays at t=2.93 with CGO
  present). This is the paper's own Table 4, no decile-ranking transform applied.
- The paper's own contribution (composite reference points built from multiple
  salient historical prices, not just the purchase-price cost basis) **dominates**
  the traditional CGO in double-sorted portfolios: the composite-variable quintile
  spread, conditional on CGO quintile, is **0.24%–0.79%/month**, significant in 4 of
  5 CGO quintiles, while the reverse conditioning (CGO spread conditional on the
  composite variable) is mostly insignificant or negative — i.e. by 2016, a
  cost-basis-only reference price (which is exactly what Book C and Grinblatt-Han
  both use) looks like the **weaker** of the two constructions on the table.

## 2. Comparison to our +0.40%/mo

Nobody in the literature reports exactly our comparator ("top-overhang-tercile
good-news book minus the SAME good-news universe unconditioned, long-only, same
window") — every published number above is either a pure-CGO regression coefficient
(Grinblatt-Han) or a doubly-conditioned long-short spread across both news signs
(Frazzini). Two proxies bound the comparison:

- **Grinblatt-Han's own implied spread** (§1, back-of-envelope from a6 × the 10-90
  percentile range of `g`): **~1.0%/month, raw, gross, roughly EW** — about **2.5×**
  our net +0.40%/mo. But this number conditions on NOTHING about news sign; it is
  the pure overhang effect on the whole cross-section, not "overhang's incremental
  value within a good-news subset," so it is not a tight comparator.
- **Frazzini's incremental-conditioning proxy**: doubly-conditioned spread
  (2.433%/mo) minus the unconditioned news spread (1.242%/mo) = **1.191%/mo**
  of "value added by conditioning on overhang," split across both legs (~0.6%/mo
  per leg if symmetric) — **roughly 1.5× our net +0.40%/mo** on this cruder
  halving assumption. Both proxies land our result **below**, not above, what the
  classic literature would predict — even before subtracting the ~50% generic
  post-publication decay that McLean & Pontiff (2016) and Chen & Zimmermann (2020)
  document across a broad cross-section of published anomalies (a 50% haircut on
  either proxy above would put the literature's implied number very close to, or
  even below, our own +0.40%/mo). **Net verdict: +0.40%/mo is in the plausible
  range, arguably on the LOW side of what an undecayed literature estimate would
  predict, and squarely inside what a 50%-decayed estimate would predict.** This is
  a case for "not suspicious," not a case for "confirmed" — the comparator design
  differs too much for a precise read.
- **The 1990s-weakest-era question, stated plainly**: our era pattern is
  weak (1990s, t 0.29) → strongest (2000s, t 1.64) → decaying (2010-16, t 1.53;
  2017-24, t 1.07). Grinblatt-Han's sample ends 1996 and Frazzini's ends 2002 —
  **both classic papers are drawn almost entirely from exactly the era our replay
  finds weakest.** That is the opposite of what "the effect was strong pre-2000
  and has decayed since" would predict, and it should be treated as **suspicious
  by the letter of CLAUDE.md's own standing warning** ("this repository has been
  burned three times by an effect that was really 1999-2007" — here it is the
  reverse shape, but the same family of era-dependent artifact). The most likely
  explanation on our own evidence is mechanical, not economic: the 1990s bucket
  runs on a truncated (24-month minimum vs. the intended 60-month) CGO lookback
  (§0), which would generate a noisier, less representative reference price and
  mechanically weaken the measured effect in exactly that decade — a construction
  artifact that happens to point the same direction as "no real effect in the
  1990s," which is exactly the kind of confound that needs to be ruled out (rerun
  the 1990s bucket with the full 60-month lookback, dropping any month that cannot
  meet it, before trusting the era table's shape) before treating the era pattern
  as either confirmation or disconfirmation of anything in the literature.

## 3. What our construction differs in from the published ones

| Dimension | Published (G&H / Frazzini) | Book C v0 | Direction of bias |
|---|---|---|---|
| Reference price | G&H: turnover-weighted past price, T=260 weeks (~5y), IDENTICAL formula to ours. Frazzini: **actual mutual-fund cost bases** (holdings data), not a turnover proxy at all. | G&H formula, T=1260 sessions / 60 months when warm, **but only 24 months required in the 1990s bucket** (§0). | Faithful to G&H in construction; the truncated-warmup deviation likely **understates** the 1990s effect specifically. No 13F/holdings data exists in this repo (per TRIAL-DRAFT-C §2), so we cannot approach Frazzini's cleaner instrument at all — this is a structural gap, not a parameter choice. |
| News/surprise proxy | Frazzini: 4-day CAR around the actual earnings-announcement date — sharp, event-based, high-frequency. G&H: no news proxy at all (pure overhang, unconditioned by any signal). | `sign(numup − numdown)`, monthly IBES consensus-revision count at `statpers` — a much lower-frequency, noisier "surprise" instrument (a whole month of revisions collapsed to one sign bit). | **Pushes our estimate DOWN** relative to Frazzini's news-conditioned numbers — a noisier news proxy dilutes exactly the conditioning that is Book C's whole mechanism. |
| Sort breakpoint | Quintiles (top/bottom 20%) in both papers. | **Tercile** (top third) of overhang within the good-news set. | **Pushes our estimate DOWN** relative to a quintile cut — a tercile includes more marginal, less-extreme-overhang names than a quintile would, and G&H's own decile evidence (Table II Panel C) shows the effect is monotonic in overhang extremity. |
| Universe / k | Top/bottom 20% of the *entire* NYSE+AMEX (or NYSE+AMEX+NASDAQ) cross-section each period — hundreds to thousands of names. | Fixed **k=30** a side, $3M dollar-volume floor. | Ambiguous sign — a fixed, floor-screened universe removes some of the illiquid-name concentration Frazzini shows drives a chunk of his gross alpha (Table VIII), which could push our estimate down, but 30 names is also far more concentrated (idiosyncratic-risk-heavy) than a full quintile book, which inflates the NW-t's sampling noise in either direction rather than the point estimate. |
| Twin / comparator | Frazzini's own comparator is the SAME news quintile, no overhang conditioning (Table IV col 5, "Good") — a proper apples-to-apples control. | `unconditioned_reaction_book_v0` = first 30 permnos **sorted by permno**, not turnover- or size-matched (receipt: `twin_turnover_matched: false`). | Adds noise to the comparator (permno-sort is not economically meaningful), which should mostly **inflate variance / dilute the t-stat** rather than bias the point estimate in a predictable direction — but an unmatched twin cannot be ruled out as a source of a spurious level difference. |
| Costs | Frazzini: realistic TAQ-based effective spread + commission, ~4.5%+ round-trip for the "All" bucket in the 1980-2002 sample (Table VIII) — his NET alpha (0.885-1.062%/mo) already reflects this. G&H: no cost model (raw/gross throughout). | Flat 25 bps/side (`cost_bps_per_side: 25.0`), explicitly "pending 5c" (the empirical cost curve chunk 5c has not been applied to this book yet). | **Pushes our estimate UP** relative to a realistic period-appropriate cost model, especially for the pre-2000 eras where real effective spreads were far above 25 bps/side for anything but the most liquid names — i.e. part of why our net number looks "reasonable" next to Frazzini's net number may be that both understate costs in different ways for different reasons (his TAQ estimate for 1980-92 is itself an extrapolation from 1993-2002 data, ours is a flat modern assumption applied retroactively to 1990-2024). |

## 4. Falsifiers the literature ran that our two registered ones do not cover

Two are recommended, both directly supported by data we actually have (CRSP-like
monthly prices/volumes/shares, IBES consensus panel, calendar dates):

1. **The January / tax-loss-selling reversal test.** Grinblatt-Han's own Table II
   Panel C shows the overhang coefficient **flips sign in January** (a6 = −0.0117,
   t=−4.95, vs. positive and highly significant Feb-Nov and Dec), which they
   attribute to the unwinding of December tax-loss-selling pressure identified in
   Grinblatt & Keloharju (2001). **Why it matters here**: if Book C's +0.40%/mo is
   really disposition-driven rather than some other January-correlated effect
   (small-cap turn-of-year, etc.), the same reversal should appear in our data.
   **Pre-registered rule**: split the 395 monthly blocks into January vs. February-
   December; compute `mean_excess_net_monthly` and its NW-t separately for each.
   **PASS** (consistent with the literature) if the January excess is
   indistinguishable from zero or negative while Feb-Dec retains a positive,
   significant excess close to the pooled +0.40%/mo. **FAIL** (does not behave like
   the documented mechanism, though it does not by itself invalidate the primary
   metric — report, do not auto-close) if January shows the SAME sign and
   magnitude as the rest of the year, since that would mean the mechanism this book
   claims (a disposition-driven overhang effect with its own well-documented
   seasonal signature) is not actually present, whatever the pooled number says.

2. **The size / dollar-volume subsample test, at the already-flagged $10M floor.**
   Frazzini's Table VIII shows the gross overhang-spread alpha is roughly 2×
   larger in the smallest NYSE size quintile than the largest (2.777% vs. 1.308%,
   3-month), and TRIAL-DRAFT-C's own universe note already flags this exact
   concern ("re-measure at the $10M corner too — the documented effect
   concentrates in exactly the illiquid names most likely to fail a floor"). **Why
   it matters here**: our primary $3M floor is looser than what a tradable
   `PRODUCT_EXPERIMENT` book would eventually need, and it matters whether the
   +0.40%/mo lives entirely in names near that floor. **Pre-registered rule**:
   re-run the identical book and twin restricted to names clearing a $10M median
   dollar-volume floor (the secondary floor the contract itself already declares).
   **PASS** if `mean_excess_net_monthly` at the $10M floor retains at least half of
   the $3M-floor point estimate (≥0.20%/mo) with NW-t ≥ 1.5. **FAIL** if the excess
   collapses toward zero or loses significance at the $10M floor — that would mean
   the effect is a micro-cap-liquidity phenomenon the way Frazzini's own data shows
   it partially is, and any promotion path would need to say so rather than quote
   the $3M-floor number as the tradable one.

Not recommended (out of scope for two, or not supported by our data): the
post-2005 decay test is **already effectively running** in our own by-era table
(2000-09 → 2017-24 is roughly a 50% decline, 0.667%→0.333%, which is in line with
McLean-Pontiff's generic post-publication-decay magnitude and does not need a
separate falsifier); a size-subsample test using An's V-shaped variant would
require building a second (loss-side) overhang leg we have not registered and is a
different book, not a falsifier of this one.

## 5. What would change the roadmap

**The single most decision-relevant finding**: Riley, Summers & Duxbury (2020,
*Management Science*, US common stock through Dec 2016) found that **12-1 momentum
stays significant (t=2.93) in the same Fama-MacBeth regression as capital-gains
overhang**, directly contradicting Grinblatt-Han's original 1967-1996 result that
momentum's coefficient becomes insignificant (t=3.57 → t=−0.68) once overhang is
controlled for. This is exactly the shape of Book C's own pre-registered falsifier
#2 ("momentum orthogonalisation: `mom_12_1` must DIE with overhang on the
right-hand side... **FAILED_VARIANT** — momentum survives orthogonalisation (it was
momentum in costume)"). A published, independent, full-length modern replication
has already found the failure mode this book's own decision rule was written to
catch. That does not mean Book C's falsifier will fail — our construction differs
in several ways from Riley et al.'s (§3), any of which could push the result either
way — but it means the falsifier run is not a formality to be waved through if the
primary metric looks good: there is now a specific, citable, modern precedent for
"momentum survives, and the disposition story doesn't hold the way the 1990s papers
said it did." The roadmap's next action on Book C should be to run the two
registered falsifiers (sign-flip placebo, momentum orthogonalisation) with the same
seriousness the primary metric got, treat a `FAILED_VARIANT` outcome as the modally
expected result rather than a surprise, and — regardless of which way it comes out —
fix the 1990s-era truncated-CGO-lookback construction bug (§0/§2) before reading
the era table as evidence about anything, since right now it cannot distinguish "no
real effect before 2000" from "we didn't give the recursion enough history before
2000."
