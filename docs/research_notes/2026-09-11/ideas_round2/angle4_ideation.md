# Angle 4: Structured Ideation — Protection + Growth Under $1M

**Problem framed.** An investor with < $1M, no time, no information edge, wants a
portfolio that is **PROTECTED and GROWS**. The engine on hand: monthly LLM reads of an
**anonymised news digest**; **typed news events** (categorised event types, not raw
sentiment); **six Alpaca paper books each with a control twin**; a **Brier-score ledger**
tracking the calibration of its own forecasts.

**Method.** SCAMPER (Substitute / Combine / Adapt / Modify / Put-to-other-use / Eliminate /
Reverse) × "what would have to be true" × inversion × "who loses when we win", applied to
that one problem. Ranked by **expected value × cheapness**, highest first. Cheapness is
1 (near-free with existing infra) to 5 (needs new paid data or a new venue).

**The standing constraint that shapes every idea below.** Every apparent edge Aegis has
tested so far turned out to be beta in disguise, one era, a look-ahead, or below the
tradability floor. So the ideas that rank highest here are the ones whose value does **not
depend on finding alpha** — they improve terminal wealth through cost, risk, tax, sizing,
or abstention, and would still be worth shipping if the LLM lane's +16%/yr gross is
eventually revealed to be a regime.

**Literature anchors used** (full sources at the end): Odean (1998) and Barber & Odean on
the disposition effect and the cost of trading; Frazzini (2006) on the disposition effect's
*exploitable* residue (capital-gains overhang × news sign, ~200 bps/month alpha); Muravyev,
Pearson & Pollet (2025, JF) — short-sale costs **eliminate** the average anomaly's
long-short return (0.14%/mo → −0.01%/mo once borrow fees are charged); Engelberg, Reed &
Ringgenberg on the loan-fee anomaly (the one short-side signal that survives fees);
Whaley (2002), Feldman & Roy / Ibbotson (2005), Callan (2006) on BXM buy-write —
~S&P-equal return at ~2/3 the volatility, but the return is a **volatility-risk-premium
harvest, not stock selection**; El-Yaniv & Wiener / Geifman & El-Yaniv on selective
prediction and the risk–coverage curve; Chalkidis & Savani (2021), *Trading via Selective
Classification* — selective (abstaining) classifiers beat always-in classifiers on
risk-adjusted terms **and the gap widens as slippage rises**; Daniel & Moskowitz (2016) on
momentum crashes and the option-like payoff of the loser leg; Dubinsky, Johannes, Kaeck &
Seeger (2019) on the predictable IV run-up and post-announcement IV collapse; the
"best days / worst days" literature (Wells Fargo, Seyhun) — and its symmetric half, that
best and worst days **cluster in the same high-VIX, below-200-day-MA regime**.

---

## 1. THE ABSTENTION BOOK — cash/index by default, deviate only on a strong typed event

- **Idea.** Run a book whose default position is 100% broad index (or T-bills in a declared
  risk-off state) and which deviates into a name only when a typed event clears a
  pre-registered confidence threshold; its **control twin is the always-invested book**
  running the identical selector at 100% coverage.
- **Mechanism.** This is selective prediction (learning with a reject option) transplanted
  into portfolio form: the selector reports a coverage fraction and a selective risk, and the
  book trades only inside the covered region. Chalkidis & Savani found exactly this —
  selective classifiers beat their always-in twins on risk-adjusted performance at coverage
  as low as 17–55%, **and the advantage grew with slippage**, because abstention is the only
  action whose cost is exactly zero. For Aegis this inverts the current design: all six books
  are always invested, so "no signal" is silently encoded as "hold the composite", and the
  engine has never been able to say *I do not know this month*.
- **FALSIFYING OBSERVATION.** Build the risk–coverage curve from the paper books: bucket
  months by the selector's confidence decile and compute realised excess-vs-twin in each. The
  idea is **wrong** if that curve is flat or inverted — if excess return in the top-confidence
  decile is not above the bottom decile over ≥24 monthly blocks, or if the abstention book's
  terminal wealth after costs is below the always-invested twin's at equal drawdown.
  Sharpest single test: *if abstained months have the same mean excess return as acted months,
  the confidence signal carries no information and this is a cash-drag machine.*
- **Cheapness: 1.** No new data. A threshold, a cash sleeve, one extra book beside the five
  already armed. The control-twin pattern already exists.
- **Expected value.** For a sub-$1M investor the dominant risk is not missing alpha, it is
  paying costs and taxes for churn with no edge — Barber & Odean measured it: high-turnover
  households earned 11.4%/yr net vs 18.5% for low-turnover households, with **no difference
  in gross returns**. An engine that can decline to trade converts Aegis's most robust finding
  (nothing works most of the time) from an embarrassment into a policy.

## 2. BRIER-WEIGHTED CONVICTION SIZING — let the calibration ledger set position size

- **Idea.** Stop sizing by signal rank; size by the **historical calibration of the forecast
  class the position belongs to** — a fractional-Kelly weight driven by the Brier ledger's
  realised reliability for that event type, at that horizon, in that volatility regime.
- **Mechanism.** The ledger already stores (forecast probability, outcome) pairs. Decompose it
  into reliability and resolution per event type: a class whose realised frequency matches its
  stated probability earns full fractional-Kelly size; a systematically overconfident class is
  shrunk toward zero *without being switched off*. This is the graceful-degradation analogue of
  idea 1 — a discovery of miscalibration reduces risk automatically instead of waiting for a
  human to notice.
- **FALSIFYING OBSERVATION.** Run the Brier-sized book against a flat-sized twin on identical
  signals, dates and costs. **Wrong** if terminal wealth at matched drawdown is not higher —
  and more sharply, if out-of-sample reliability is unstable: fit the calibration map on months
  1–24, apply to months 25–48, and if the class ranking by reliability does not persist (rank
  correlation ≈ 0 across the split), the ledger is measuring noise and the sizing is a random
  re-weighting. Canon trap to respect: **never fit the calibrator and score it on the same
  data.**
- **Cheapness: 1.** The ledger exists. This is a sizing function plus a walk-forward split.
- **Expected value.** Sizing is the one lever guaranteed to matter: the same signal at half
  size halves the drawdown. For an investor whose real constraint is "do not lose 40% of my
  $300k", converting an existing self-measurement into an automatic risk throttle is worth
  more than another selector.

## 3. CORE-SATELLITE WITH A DECLARED DRAWDOWN BUDGET — index core, small conviction sleeve

- **Idea.** Make the *product* an index core plus a small, explicitly budgeted conviction
  sleeve; the sleeve holds whichever book currently carries forward evidence, and the budget
  is stated in dollars of worst case before the first trade.
- **Mechanism.** Inversion: instead of "can the engine beat the market?", ask "what fraction
  of this person's wealth are we entitled to put behind an unproven mechanism?" The answer
  derives from the house sizing rule — print `n × notional% × stop%` and `Σ|notional|/equity`
  first. A 10% sleeve with a 25% internal stop risks 2.5% of the portfolio; the core does the
  compounding. It also structurally neutralises Aegis's recurring failure mode: if the sleeve
  turns out to be beta, the investor has merely bought slightly more index — a survivable
  outcome rather than a refuted product.
- **FALSIFYING OBSERVATION.** **Wrong** if, over the live paper record, the blend's return is
  statistically indistinguishable from its core alone (sleeve contribution t < 1 over ≥24
  monthly blocks) *while* the sleeve adds measurable tracking error and turnover cost.
  Concretely: regress blend excess on core excess; an intercept ≈ 0 with raised residual
  variance means the sleeve is pure cost and should be cut to zero.
- **Cheapness: 1.** Pure allocation policy over books that already run.
- **Expected value.** This is the honest shape of the deliverable for someone with no time and
  no edge, and the shape that makes the programme *shippable while still uncertain*: the
  investor is protected by construction, and every research result changes only the sleeve.

## 4. THE ANTI-DISPOSITION OVERLAY — run the documented mistake backwards, inside the account

- **Idea.** Before hunting the disposition effect's counterparty in the market, capture the
  part that is free and certain: a rule that **realises losses and defers gains** inside the
  investor's own account, on a schedule, with wash-sale-safe replacement.
- **Mechanism.** Odean (1998) measured that individuals realise winners at ~1.5× the rate of
  losers, that this survives controls for rebalancing, price level and information, and that
  the winners they sold went on to *outperform* the losers they kept — "for taxable
  investments it is suboptimal and leads to lower after-tax returns." The inverse policy is a
  rare signed, after-cost, non-alpha gain. The typed-event feed adds one twist: harvest
  preferentially into names where the digest reads *no pending event*, so the round trip does
  not sell the day before a catalyst.
- **FALSIFYING OBSERVATION.** **Wrong** if the harvest-and-replace round trips cost more in
  spread + tracking error than the deferred tax is worth — specifically if the replacement
  basket's realised tracking error to the sold name exceeds ~2%/yr, or if harvested names'
  subsequent returns beat their replacements by more than the tax benefit (which would mean we
  re-created the disposition mistake with extra steps). Also falsified if a paper-book audit
  shows harvest dates clustering into the week *before* typed events — that is the
  catalyst-selling failure, and it is directly observable in the trade log.
- **Cheapness: 1** in paper (needs positions, cost basis, the event feed). The real-money
  version is jurisdiction-specific and is a *product* decision, not a research claim.
- **Expected value.** A guaranteed after-tax improvement for a taxable sub-$1M account,
  independent of whether any Aegis mechanism ever works — and the cleanest demonstration of
  the programme's own philosophy: study the loser side as hard as the winner.

## 5. THE DISPOSITION COUNTERPARTY BOOK — typed event × capital-gains overhang

- **Idea.** Build a book on the *interaction* Frazzini (2006) identified: take the typed
  event, then condition on whether current holders sit on paper **gains or losses** — long
  good-news names with large unrealised gains; avoid (or short, subject to idea 13) bad-news
  names with large unrealised losses.
- **Mechanism.** "Who loses when we win?" answered literally: the counterparty is the
  disposition-prone holder, who is reluctant to sell at a loss (throttling seller supply, so
  bad news travels slowly through stocks trading at a loss) and eager to take profits
  (throttling the response to good news in stocks trading at a gain). Frazzini's overhang
  spread earned 2.43%/month risk-adjusted. The structurally important part for Aegis is that
  the effect is **conditional**, which is the shape the mandate asks for ("situational, not
  universal"). Aegis has typed events and full bars, so a Grinblatt–Han style turnover-weighted
  reference price can be built from price history alone — no holdings vendor needed.
- **FALSIFYING OBSERVATION.** Sort every typed event into a 2×2: {event sign} × {overhang
  sign}. **Wrong** if same-sign cells do not out-drift opposite-sign cells — if the
  (good news, large gain) minus (good news, large loss) spread is indistinguishable from zero
  over ≥24 monthly blocks *with its own matched control twin subtracted*, or if the whole
  spread lives in one era (compute per era; this repo has been burned three times by an effect
  that was really 1999–2007). Second falsifier, specific to this codebase: if the overhang
  variable's explanatory power vanishes once 12-1 momentum enters as a control, it was
  momentum in a behavioural costume — overhang and past return are mechanically correlated.
- **Cheapness: 2.** A reference-price construction and an unrealised-gain proxy from existing
  bars, plus a re-slice of the existing event panel. No new vendor.
- **Expected value.** The one contrarian seed with a large, published, *conditional* effect
  behind it, and it promotes typed events from a standalone signal (which has repeatedly
  failed here) to a conditioning variable (where the literature says the information lives).
  If it survives the momentum control, it is the most plausible RESEARCH_CLAIM candidate here.

## 6. THE CONTROL TWIN AS THE PRODUCT — ship every recommendation next to its placebo

- **Idea.** Put-to-other-use: stop treating the control twin as internal methodology and make
  it the **user-facing feature**. Every position the engine suggests is displayed beside what
  its matched placebo did — same construction, same costs, shuffled (uninformative) signal — and
  the headline number the user sees is *arm minus twin*, never the arm alone.
- **Mechanism.** The single most expensive thing a retail investor buys is a confident number
  with no counterfactual. Aegis has, unusually, already paid for the counterfactual: six books
  each with a twin. Surfacing it inverts the industry's incentive — the product's marketing
  claim becomes falsifiable in public, in real time, which is both the honest thing and a
  genuine differentiator no incumbent will copy (see "who loses when we win": the loser is the
  vendor whose track record only looks good because nobody computed its placebo).
- **FALSIFYING OBSERVATION.** This is a product hypothesis, so it falsifies on behaviour, not
  returns: **wrong** if, over the paper record, the arm-minus-twin series is so noisy that the
  displayed number flips sign more than ~40% of months — a metric that changes its mind every
  month is not a trust instrument, it is anxiety, and a user acting on it will churn. Second
  falsifier: if users (or Murat, on his own capital) systematically override the display in the
  direction of the arm's raw number, the feature is decorative and the honesty is not reaching
  the decision.
- **Cheapness: 1.** The twins already run. This is a rendering and a definition of the headline
  metric.
- **Expected value.** For a sub-$1M investor with no way to evaluate a manager, "here is what
  the same machinery did with no information" is the most valuable single number anyone could
  show them — and it is the only defensible marketing claim a programme with a 0% demonstrated
  edge can make.

## 7. THE SELF-CALIBRATION GATE — the Brier ledger decides whether the engine may trade at all

- **Idea.** Modify idea 2 from sizing to *authority*: a rolling Brier/ECE statistic on the
  last N forecasts gates whether the LLM lane has permission to deviate from the core this
  month at all. Calibration degrades → authority is withdrawn → the book reverts to the index
  until calibration recovers.
- **Mechanism.** This is abstention applied to the **engine** rather than to the market. Aegis's
  live lane is a 7B model reading a monthly digest; the failure mode that matters is not "the
  edge is small" but "the edge quietly died and the machine kept trading". A regime shift shows
  up in calibration *before* it shows up in a t-statistic, because calibration is measured on
  every forecast while return significance needs years (the house rule: risk resolves ~30×
  faster than return). The gate is the institutional version of the canon line *a check that
  did not run is not a check that passed.*
- **FALSIFYING OBSERVATION.** **Wrong** if gate-closed months and gate-open months have
  indistinguishable realised excess returns over ≥24 monthly blocks — i.e. rolling calibration
  has no forward relationship to the lane's profitability. Test it directly: regress month-ahead
  arm-minus-twin excess on trailing 6-month ECE; a slope indistinguishable from zero kills the
  gate. Also **wrong** (in the opposite, sneakier way) if the gate never closes in the sample —
  a gate that cannot fire is a broken gate, not a strict one, and must report CANNOT DETERMINE
  rather than PASS.
- **Cheapness: 1.** Ledger + a rolling statistic + a flag on the existing books.
- **Expected value.** It bounds the worst case of an unattended self-improving system, which
  is the failure the whole programme is most exposed to and the one a retail user is least able
  to detect for themselves.

## 8. COVERAGE-NORMALISED EVENT SURPRISE — an event is only news relative to the name's baseline

- **Idea.** Substitute raw event counts with **coverage-normalised** ones: for each name,
  express this month's typed-event vector as a deviation from that name's own trailing baseline
  news intensity, not against the cross-section.
- **Mechanism.** A mega-cap generates hundreds of headlines a month; a mid-cap generates three.
  Any selector reading raw event counts is therefore reading market cap and analyst coverage —
  which is precisely how "an edge" becomes "beta in disguise" for the fourth time in this repo.
  Normalising per name asks the only question that can be informative: *is this unusual for
  this company?* This is also the explicit instruction in the VISION file (whole-market news,
  coverage normalisation) that has been lost between sessions.
- **FALSIFYING OBSERVATION.** **Wrong** if the normalised signal's cross-sectional rank
  correlates > ~0.8 with the raw signal's rank (then normalisation changed nothing and the two
  books will be the same book), OR if, after normalisation, the book's excess return loads just
  as heavily on size/market beta as before — run the loading regression, not the return
  comparison. The repo's own history says this is the test that matters: *an excess that is a
  loading is not an excess.*
- **Cheapness: 2.** A rolling per-name baseline over the existing event panel; no new data, but
  it does need the joined text-and-return panel that E1 finally built (339,657 cells / 3,031
  names, 2025-01..2026-09).
- **Expected value.** It is a cheap structural fix to the most-repeated failure mode in the
  programme's entire corpus, and it applies to *every* downstream typed-event idea in this
  list, including ideas 5, 9 and 12.

## 9. THE PROTECTION LANE — use typed events to cut exposure, never to pick names

- **Idea.** Eliminate the selection problem entirely: point the typed-event machinery at
  **exposure** rather than at names. When the digest reads a cluster of a specific typed event
  class across the portfolio (or the market), reduce equity exposure toward the declared
  drawdown budget; otherwise stay fully invested.
- **Mechanism.** Two facts combine. First, the house canon: *risk resolves ~30× faster than
  return* — volatility and correlation are estimable from months of data, whereas a return edge
  needs years, so an exposure rule reaches statistical adequacy while a stock-picking rule is
  still noise. Second, the symmetric half of the best-days literature: best and worst days
  cluster in the same identifiable regime (in one analysis, 7 of the 10 worst and 8 of the 10
  best S&P days since 1993 occurred below the 200-day MA; average VIX on the 20 worst days was
  42.3 vs 16.1 elsewhere). So avoiding the regime forfeits upside *and* downside — which is a
  bad trade for a return-maximiser and a **good** trade for a protection mandate with a stated
  drawdown budget.
- **FALSIFYING OBSERVATION.** **Wrong** if, at matched terminal wealth, the exposure-managed
  book's maximum drawdown is not materially lower than the always-invested twin's — that is the
  only thing it is buying, so if drawdown does not fall, it has bought nothing. Second, specific
  falsifier: count the whipsaws. If the rule de-risks and re-risks more than ~4× per year, the
  turnover cost will exceed the drawdown benefit (the 200-day-MA comparators produce 3–4 false
  whipsaws/yr in sideways markets, and that is the documented cost of this family).
  Third: if the typed-event trigger adds nothing over a plain trailing-volatility trigger, the
  events are decorative — run both arms.
- **Cheapness: 2.** One new book, existing feeds, plus an honest cost model on the switches.
- **Expected value.** "Protected" is half the user's stated objective and is the half nobody in
  this repo has attacked directly. It is also the only half that the available statistics can
  actually support within one investor's lifetime of data.

## 10. EVENT-DRIVEN REBALANCING — rebalance on catalysts, not on the calendar

- **Idea.** Eliminate the monthly rebalance. Hold the core indefinitely and let turnover be
  *triggered* by typed events on held names — no event, no trade, regardless of drift.
- **Mechanism.** Calendar rebalancing spends spread and tax on a date chosen by the calendar
  rather than by information; the typed-event feed offers a cheap alternative clock. This is the
  Eliminate move in SCAMPER and it composes with idea 1 (abstention) and idea 4 (harvesting) —
  together they turn "when do we trade?" from an assumption into a tested parameter. Barber &
  Odean again supply the prior: the gross returns of high- and low-turnover households were
  indistinguishable, so any turnover that is not information-driven is a pure transfer to the
  broker.
- **FALSIFYING OBSERVATION.** **Wrong** if the event-clocked book's net terminal wealth is not
  above the calendar-clocked twin's at matched drawdown *and* its realised turnover is not
  materially lower. Two distinct failure signatures to watch for: (a) turnover falls but
  drawdown rises, meaning the portfolio drifted into concentration — check `Σ|notional|/equity`
  and per-name weight at every month end; (b) turnover does **not** fall, meaning typed events
  fire on nearly every held name every month, which would prove the event feed has no
  selectivity and silently invalidates ideas 1, 5, 9 and 12 as well. Measure the event firing
  rate per name-month *before* running the book — that is a five-minute check that can kill
  four ideas at once.
- **Cheapness: 1.** A trigger condition on an existing book.
- **Expected value.** Cost reduction is the only alpha that is certain, and for a taxable
  sub-$1M account a reduction in realised turnover is worth more per unit of effort than almost
  any selector improvement. It also produces a diagnostic (the firing rate) that the rest of
  the programme needs.

## 11. THE INVERSE-BRIER META-ALLOCATOR — combine the six books by calibration, not by return

- **Idea.** Allocate across the six existing books by each book's **recent calibration**
  (inverse Brier / inverse ECE), not by recent return — with a seventh "equal-weight the six"
  control twin.
- **Mechanism.** Combine: the six books plus the ledger. Allocating on recent *return* is the
  classic performance-chasing trap and, with 4-session-old books, is pure noise-fitting; recent
  *calibration* is a statistically far cheaper quantity because every forecast contributes a
  datum, not every month. It also composes correctly with the repo's own diagnosis of the
  bottleneck — the books differ in portfolio treatment, not in alpha source, so a return-based
  allocator would be choosing between six flavours of the same 12-1 momentum. Calibration at
  least measures something the books do not share.
- **FALSIFYING OBSERVATION.** **Wrong** if the meta-allocated portfolio does not beat the
  equal-weight-of-six twin, net, over ≥24 monthly blocks. The diagnostic that explains a
  failure: compute the pairwise correlation of the six books' monthly excess returns — if the
  median pairwise correlation is above ~0.8, there is nothing to allocate *between* and the
  meta-layer is a decoration on one book. Run that correlation first; it is a one-hour check
  that can retire the idea before any book is built.
- **Cheapness: 2.** Existing books, existing ledger, one allocator and one twin.
- **Expected value.** Moderate and honest: it will not create an edge, but if any of the six
  ever develops one, this is the machinery that routes capital to it without a human in the
  loop — and the correlation diagnostic is worth the exercise on its own.

## 12. TYPED-EVENT DIVERSIFICATION CAPS — cap exposure per event *type*, not per sector

- **Idea.** Modify portfolio construction so the constraint set is expressed in **event-type
  space**: at most k names driven by any one typed event class, and a hard cap on total
  notional attributable to a single class.
- **Mechanism.** The repo's own postmortem — *check whether the noise is shared* — found that a
  one-sector portfolio concentrates that factor and the control belongs in the regression. The
  same is true one level up: ten names all selected because they fired "guidance raise" is one
  bet held ten times, and its drawdown is the drawdown of the guidance-raise mechanism, not of a
  diversified book. Sector caps do not catch this, because event classes cut across sectors.
  This is the construction-level answer to the arena bottleneck (99.5% of names carrying exactly
  one factor).
- **FALSIFYING OBSERVATION.** **Wrong** if the capped book's realised drawdown is not lower than
  the uncapped twin's while its return is materially lower — i.e. the cap threw away
  concentration that was earning its risk. The cleaner prior test: compute the realised
  correlation of same-event-class positions' monthly returns in the existing paper books. If
  names sharing an event class are no more correlated than random pairs from the same universe,
  the event class is not a risk factor and the cap is solving an imaginary problem.
- **Cheapness: 2.** A constraint in the existing construction code; the diagnostic runs on the
  existing position history.
- **Expected value.** Protection again, and of the kind that is measurable now rather than in
  three years — a sub-$1M investor's ruin risk comes from holding one bet ten times far more
  often than from picking badly.

## 13. THE LOSER SIDE — short the bottom typed-event decile at a borrow-cost-survivable hold

- **Idea.** Short the bottom typed-event decile, but with the hold rule, universe filter and
  sizing chosen **so the position survives realistic borrow cost** — and with the borrow fee
  charged inside the book, not netted afterwards.
- **Mechanism.** The literature is brutally specific here and should be read as a design
  constraint rather than a discouragement. Muravyev, Pearson & Pollet (2025, JF) find the
  average of 162 anomalies earns 0.14%/month long-short before short-sale costs and **−0.01%
  after** borrow fees; and once the 12% of stock-dates with fees > 1%/yr are excluded, the
  anomalies are not profitable *even gross*. The entire short-side return lives in the
  expensive-to-borrow names. But Engelberg, Reed & Ringgenberg show the **loan fee itself** is
  the single best cross-sectional predictor and still returns ~0.48%/month *after* subtracting
  its own fee. The design implication is exact: a typed-event short book is only worth running
  if it is (a) restricted to names it can actually borrow at a known rate, (b) charged that rate
  daily, and (c) benchmarked against a loan-fee-only short book, which is the real competitor.
  Daniel & Moskowitz supply the risk warning: the loser leg behaves like a written call on the
  market in bear regimes (loser-decile up-market beta ~2.16), so the short side's tail risk is
  concentrated exactly in the rebound the protection mandate cares about.
- **FALSIFYING OBSERVATION.** **Wrong** — and this is the likeliest outcome — if the book's
  net-of-borrow excess over its control twin is indistinguishable from zero once names with a
  borrow fee above ~1%/yr are excluded. Run it the discriminating way: split the short leg into
  {fee ≤ 1%} and {fee > 1%} sub-books. If all the return is in the high-fee sub-book, the
  mechanism is the shorting premium (a documented risk premium for concentrated short risk),
  **not** the typed event, and the idea is rejected as a typed-event claim regardless of its
  P&L. Second falsifier: if the book's up-market beta in bear months is materially negative,
  the return is a short-volatility payoff and will be repaid in one rebound.
- **Cheapness: 4.** Needs borrow-fee data (per-name, daily) which the repo does not have, plus
  short locate handling in the paper venue. Everything else exists.
- **Expected value.** Low as a return source and **high as a decisive negative**: this is the
  cheapest way to close the entire short-side question with evidence rather than intuition, and
  the literature predicts the answer, which makes it a good pre-registration. For a sub-$1M
  investor the honest finding "you cannot monetise the loser side after borrow" is worth as much
  as a working strategy, because it stops them trying.

## 14. SELL THE NOISE — covered calls only on names the digest reads as "no event this month"

- **Idea.** Write one-month, slightly out-of-the-money covered calls **only** on held names
  where the monthly LLM digest reads *no typed event pending*; names with a pending event stay
  un-overwritten. Control twin: the same overwriting applied indiscriminately to every held
  name (i.e. a BXM-style rule with no event filter).
- **Mechanism.** Two literatures meet. The BXM evidence says a mechanical monthly buy-write has
  produced roughly S&P-equal compound return at ~two-thirds the volatility over 18 years
  (11.77% vs 11.67%, σ 9.29% vs 13.89%, drawdown −32.5% vs −47.4% in 2000–2002), with the
  return decomposing into a fair call premium plus a volatility risk premium *minus a large
  exercise cost* — so it is a risk-transfer harvest, not selection, and it caps the upside. The
  event literature says the exercise cost is exactly where the typed-event feed could help:
  implied volatility runs up predictably into an announcement and **collapses immediately
  after**, and EAD return variance is ~6× non-EAD variance (in 2015, >19% of a name's annual
  return variance landed on its four earnings days). Writing calls on a name with a pending
  catalyst is selling the fat tail cheaply; writing on a genuinely quiet name is selling
  ordinary variance. The digest's "no event" read is the filter that separates them —
  and it is, notably, a use of the LLM that does **not** require it to predict direction.
- **FALSIFYING OBSERVATION.** **Wrong** if the filtered overwrite's excess over the
  indiscriminate twin is indistinguishable from zero — that is, if "no event" months do not
  show a lower realised exercise cost (assignment rate × moneyness at assignment) than "event"
  months. That is the single number to compute, and it can be computed on **historical bars
  without any option data at all**: for each name-month, was the realised absolute return above
  the strike distance? If the no-event bucket's exceedance rate is not materially below the
  event bucket's over ≥24 monthly blocks, the filter carries no information and the idea dies
  before options are ever priced. Second falsifier: if the filtered book's terminal wealth
  trails plain buy-and-hold over a strong-market stretch by more than the drawdown reduction is
  worth under the declared utility — the BXM record shows multi-year stretches of >5pp/yr
  underperformance in bull markets, and that must be pre-declared as acceptable, not discovered.
- **Cheapness: 4** for the live version (needs an options chain, assignment handling, and the
  paper venue's option support — and note the 09-09 lesson that an expiry past the last listed
  chain silently empties a book). **Cheapness 1 for the falsifier**, which is a bar-only
  exceedance study and should be run first.
- **Expected value.** This is the only idea in the list that directly produces **income plus
  downside cushion** — the literal shape of "protected and grows" — and it does so without
  requiring the engine to be right about direction, which is the capability Aegis has repeatedly
  failed to demonstrate. If the exceedance test passes, it is the strongest product candidate
  here; if it fails, it fails for 1 unit of cost.

## 15. THE MONTHLY DIGEST AS THE DELIVERABLE — sell the read, not the trade

- **Idea.** Reverse the product: the thing the sub-$1M investor receives is the **anonymised
  monthly read on the names they already hold** — what changed, which typed events fired, what
  the engine's calibrated probability is, and what its control twin says — with an explicit
  default recommendation of *do nothing*.
- **Mechanism.** The user's stated constraints are "no time, no information edge" — neither of
  which is solved by a trade list, and both of which are solved by a compressed, honest monthly
  briefing. It also sidesteps the entire regulatory and fiduciary surface of managing money,
  which for an HKU student shipping an open-source tool is not a minor consideration. And it is
  the only configuration where the LLM lane's demonstrated capability (reading an anonymised
  digest better than a shuffled control) is deployed at exactly its measured strength rather
  than being levered into a directional claim it has not earned.
- **FALSIFYING OBSERVATION.** **Wrong** if the digest's content has no relationship to what
  subsequently mattered: take the engine's monthly "what changed" items and check whether the
  named items predict the *dispersion* (not direction) of the following month's returns for
  those names. If flagged names are no more volatile than unflagged ones in the following month,
  the digest is describing noise fluently and is an entertainment product. Second falsifier,
  behavioural: if recipients trade *more* after receiving it, the product has inverted its own
  thesis and is doing harm — measure turnover of digest recipients against the do-nothing
  baseline.
- **Cheapness: 1.** The lane already runs and already produces the read; this is packaging plus
  one dispersion study.
- **Expected value.** Modest as a return mechanism, high as the realistic path to the
  open-source deliverable in the mission statement — and it is the configuration in which a
  negative research result (no alpha) does not destroy the product.

---

## Cross-cutting notes

**Cheapest kill-shots, run these first.** Three of the falsifiers above are diagnostics that
can retire several ideas at once, cost under a day, and need no new book:

1. **Typed-event firing rate per name-month** (idea 10). If events fire on nearly every name
   every month, ideas 1, 5, 9, 10 and 12 all lose their selectivity premise simultaneously.
2. **Median pairwise correlation of the six books' monthly excess** (idea 11). Above ~0.8 and
   the meta-allocator, and most "combine the books" thinking, is decoration on one book.
3. **Bar-only exceedance test for the overwrite filter** (idea 14). Answers the covered-call
   question for 1 unit of cost before any option chain is touched.

**What would have to be true, stated once for the whole list.** Every idea ranked 1–4 and
6–12 is worth doing *even if no Aegis mechanism has alpha*, because it buys cost, tax, risk
or trust. Ideas 5, 13, 14 and 15 are the only ones whose value is contingent on the engine
knowing something — and of those, 14 and 15 need it to know only about **variance and
attention**, not direction, which is the weaker and more defensible claim.

**Who loses when we win.** Idea 4's counterparty is the tax authority's timing, not another
investor. Idea 5's counterparty is the disposition-prone individual holder — a real, measured,
large and persistent population, which is why that one is the most credible alpha candidate.
Idea 13's counterparty turns out, on the evidence, to be **the securities lender**, who
captures roughly half of pre-fee anomaly profits through the borrow fee — which is precisely
why the loser side does not pay. Idea 14's counterparty is whoever wants convexity into a
catalyst, and they are paying a documented premium for it. Where an idea has no identifiable
loser (ideas 8, 11, 12), it is a construction improvement, not an edge, and should be
described that way in any handoff.

---

## Sources

- Odean, T. (1998). *Are Investors Reluctant to Realize Their Losses?* Journal of Finance.
  https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/areinvestorsreluctant.pdf
- Barber, B. & Odean, T. *The Courage of Misguided Convictions* / *Trading Is Hazardous to Your
  Wealth.* https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/Individual_Investor_Performance_Final.pdf
- Frazzini, A. (2006). *The Disposition Effect and Underreaction to News.* Journal of Finance
  61(4). https://pages.stern.nyu.edu/~afrazzin/pdf/The%20Disposition%20Effect%20and%20Underreaction%20to%20news%20-%20Frazzini.pdf
- Barberis, N. & Xiong, W. *What Drives the Disposition Effect?* NBER w12397.
  https://www.nber.org/system/files/working_papers/w12397/w12397.pdf
- Muravyev, D., Pearson, N. & Pollet, J. (2025). *Anomalies and Their Short-Sale Costs.*
  Journal of Finance. https://doi.org/10.1111/jofi.13501 · working paper:
  https://www.hec.ca/finance/Fichier/Pearson2022.pdf
- Engelberg, J., Reed, A. & Ringgenberg, M. *The Loan Fee Anomaly: A Short Seller's Best Ideas.*
  Management Science. https://pubsonline.informs.org/doi/10.1287/mnsc.2023.00152
- Drechsler, I. & Drechsler, Q. *The Shorting Premium and Asset Pricing Anomalies.*
  https://www.aeaweb.org/conference/2016/retrieve.php?pdfid=20742
- Whaley, R. (2002). *Return and Risk of CBOE Buy Write Monthly Index.* Journal of Derivatives.
  https://www.pm-research.com/content/iijderiv/10/2/35.full.pdf
- Feldman, B. & Roy, D. / Ibbotson Associates (2005). *Passive Options-Based Investment
  Strategies: The Case of the CBOE S&P 500 BuyWrite Index.*
  https://cdn.cboe.com/resources/education/research_publications/IbbotsonAug30final.pdf
- Callan Associates (2006). *An Evaluation of the CBOE S&P 500 BuyWrite Index.*
  https://cdn.cboe.com/resources/education/research_publications/Callan_CBOE.pdf
- Hill, J., Balasubramanian, V., Gregory, K. & Tierens, I. *Finding Alpha via Covered Index
  Writing.* Financial Analysts Journal.
  https://www.borntosell.com/assets/pdf/finding-alpha-via-covered-index-writing.pdf
- Chalkidis, N. & Savani, R. (2021). *Trading via Selective Classification.* arXiv:2110.14914.
  https://ar5iv.labs.arxiv.org/html/2110.14914
- Pidan, D. & El-Yaniv, R. (2011). *Selective Prediction of Financial Trends with Hidden Markov
  Models.* NeurIPS.
  https://proceedings.neurips.cc/paper/2011/file/dd458505749b2941217ddd59394240e8-Paper.pdf
- Daniel, K. & Moskowitz, T. (2016). *Momentum Crashes.* Journal of Financial Economics.
  https://www.nber.org/system/files/working_papers/w20439/w20439.pdf
- Dubinsky, A., Johannes, M., Kaeck, A. & Seeger, N. (2019). *Option Pricing of Earnings
  Announcement Risks.* Review of Financial Studies.
  https://research.vu.nl/ws/files/108247883/Option_Pricing_of_Earnings_Announcement_Risks.pdf
- Zhan, X., Han, B., Cao, J. & Tong, Q. (2021). *Option Return Predictability.* RFS.
  https://doi.org/10.1093/rfs/hhab067
- Wells Fargo Advisors. *The Perils of Trying to Time Volatile Markets.*
  https://www.wellsfargoadvisors.com/research-analysis/reports/policy/volatile-markets.htm
- Seyhun, N. (Towneley summary). *Market timing study, 1926–2024.*
  https://www.towneley.com/insights/market-timing-study-dont-blink
- Nasdaq Dorsey Wright. *Volatility Clusters and the Effect of Missing the Best and Worst Market
  Days* (2026-02-05).
  https://dorseywright.nasdaq.com/research/bigwire/2026/02/05/02-05-2026/ndw-prospecting-volatility-clusters-and-the-effect-of-missing-the-best-and-worst-market-days
