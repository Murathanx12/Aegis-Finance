# Angle 2: Patents (Portfolio Construction & Execution Mechanisms)

Research date: 2026-09-11. Source of record: Google Patents `xhr/query` API (the JS UI
does not render to a fetcher; the XHR endpoint returns `family_metadata.country_status.
best_patent_stage.state` per jurisdiction, which is what "ACTIVE / NOT_ACTIVE" below is
read from). Cross-checked against general web search where a family needed context.

**Status vocabulary used here**
- `EXPIRED` — term ran out (20y from earliest non-provisional filing for post-1995 filings;
  max(17y from grant, 20y from filing) for pre-1995-06-08 filings). Freely practisable.
- `ABANDONED / NEVER GRANTED` — published application that died without issuing. Its
  *disclosure* is prior art and nobody owns the claims. Freely practisable.
- `ACTIVE` — in force or presumed in force. **NOT usable.**
- `STATUS UNVERIFIED` — Google's family flag is ambiguous (continuations alive in the same
  family, or the flag is aggregated across the family rather than the individual patent).
  Do not rely on my reading; check USPTO PatentCenter / Patent Term Calculator by hand.

---

## 0. THE HEADLINE NEGATIVE, AND IT IS A USEFUL ONE

**There is no LOR (Leland O'Brien Rubinstein) portfolio-insurance patent. There is no
CPPI patent by Black/Jones or Perold. They do not exist and were never filed.**

I searched Google Patents for `Leland O'Brien Rubinstein` (assignee + full text), for
`SuperShares`, for `SuperTrust`, and for `"portfolio insurance"` limited to priority
before 1996. The only pre-1996 US hits are Dembo's two optimisation patents and Lupien's
crossing-network patent (all below). LOR appears *nowhere* as an assignee.

The reason is structural, and it matters for the whole of this angle: **US business-method
patents were effectively unavailable until *State Street Bank v. Signature Financial*
(Fed. Cir. 1998)**. Everything invented in the golden age of portfolio construction —
CPPI (Black–Jones 1987, Perold 1986), option-replication portfolio insurance
(Leland–Rubinstein 1976-1981), Markowitz, Black–Litterman (1990-92), Grinold–Kahn,
Mitchell–Pulvino merger-arb — was published in journals, never patented, and sits in the
public domain permanently. Then *Alice v. CLS Bank* (2014) shut the window again for
abstract financial methods, so the patentable era for this subject matter is roughly
**1998–2014**, and nearly everything filed in the first half of that window has now
expired on its own.

**Practical consequence for Aegis:** the classic mechanisms Murat most wants (CPPI,
synthetic-put overlays, mean-variance, CVaR) carry **zero patent risk at all** — not
because a patent expired, but because none was ever granted. The patents worth reading are
the 1998–2008 *implementation* patents, which are now expired and which describe, in
unusual operational detail, how to actually wire these things into a running system.

---

## 1. US5148365A — "Scenario optimization"

| Field | Value |
|---|---|
| **Number** | US5148365A |
| **Assignee / inventor** | Ron S. Dembo (individual; later founder of Algorithmics Inc.) |
| **Dates** | Filed 1989-08-15 · Granted 1992-09-15 |
| **Status** | **EXPIRED** — pre-GATT filing, term = max(17y from grant, 20y from filing) → expired 2009-09-15 at the latest. Google family flag: `US:NOT_ACTIVE`. |
| **Usable now?** | **YES.** Freely usable. |

**Mechanism in plain English.** Instead of optimising a portfolio against a single expected
return vector and covariance matrix, you enumerate a discrete set of *scenarios* (each a
full joint realisation of every asset's price, with a probability attached), then solve for
the holdings that minimise a probability-weighted penalty on the *gap between your
portfolio's payoff and a target payoff*, scenario by scenario. Upside and downside gaps get
separate penalty weights, so the objective is asymmetric by construction. The patent notes
explicitly that this is how you manufacture "synthetic long-dated options required for
portfolio insurance" out of cash instruments and futures.

**Why it matters for Aegis.** This is the direct ancestor of CVaR/expected-shortfall
portfolio optimisation (Rockafellar–Uryasev 2000 is the same object with a specific penalty
choice), and the formulation is a linear program if the penalties are piecewise-linear —
i.e. solvable with scipy on a laptop, no commercial optimiser. It is also the cleanest
published description of *"optimise against an asymmetric loss function over sampled
futures"*, which is exactly what a declared-utility engine with four personalities
(preservation / balanced / aggressive / extreme growth) needs: the personality *is* the
choice of up-gap vs down-gap penalty ratio.

---

## 2. US5799287A — "Method and apparatus for optimal portfolio replication"

| Field | Value |
|---|---|
| **Number** | US5799287A |
| **Assignee / inventor** | Ron S. Dembo (individual) |
| **Dates** | Priority 1994-05-24 · Filed (this continuation) 1997-05-30 · Granted 1998-08-25 |
| **Status** | **EXPIRED** — 20y from the 1994 parent filing → expired 2014-05-24 at the latest. Google family flag: `US:NOT_ACTIVE`, `EP:NOT_ACTIVE`. |
| **Usable now?** | **YES.** Freely usable. |

**Mechanism in plain English.** You have a *target* portfolio or payoff you cannot hold
directly — an index you cannot buy all of, an illiquid book you must hedge, or an option
payoff you must manufacture. You have a *universe* of instruments you can actually trade.
The method picks weights on the tradable universe that minimise the expected replication
error against the target across a scenario set, subject to real constraints (position
limits, transaction costs, integer lot sizes). The patent's own framing names portfolio
insurance, dynamic hedging, and option replication as the target payoffs.

**Why it matters for Aegis.** This is the *tracking-basket* problem, and Aegis has the
exact data shape it wants: CRSP daily returns to build the scenario set, and a small
Alpaca-tradable universe as the replication basket. Concretely it gives (a) a defensible
way to run a 774-name research universe through a 10-name executable book without
hand-waving, and (b) a synthetic-put overlay built from shares alone, which matters because
the paper books have repeatedly been emptied by option-chain availability (the hack1
`no chain at 2027-12-31` failure). Replicating the put payoff with a share/cash schedule
sidesteps the chain entirely.

---

## 3. US5101353A — "Automated system for providing liquidity to securities markets"

| Field | Value |
|---|---|
| **Number** | US5101353A |
| **Assignee / inventor** | Lattice Investments, Inc. / William A. Lupien (later the Optimark and ITG lineage) |
| **Dates** | Filed 1989-05-31 · Granted 1992-03-31 |
| **Status** | **EXPIRED** (US) — pre-GATT, lapsed by 2009. Google flags `US:NOT_ACTIVE`, `EP:NOT_ACTIVE`, `CA:NOT_ACTIVE`; a Japanese member still shows `JP:ACTIVE`, which is irrelevant to a US/HK personal tool but is noted for honesty. |
| **Usable now?** | **YES** in the US/EP. |

**Mechanism in plain English.** A participant submits not a price but a *satisfaction
profile* — a surface saying how much of a name they will trade at each price/size
combination. The system matches profiles against each other away from the lit book and
prints the cross. The patent's own background blames portfolio insurance for the
1987 cascade and positions profile-matching as the fix: express *willingness*, not a limit.

**Why it matters for Aegis.** The reusable idea is not the crossing network (Aegis routes
to Alpaca and cannot cross anything). It is the **satisfaction-profile representation of an
order**: a size-vs-price curve rather than a scalar target weight. That is a better data
structure for the "what do I actually want to own at what price" layer than the current
`notional%` scalar, and it makes the worst-case-in-dollars calculation the session protocol
demands (`n names × notional% × stop%`) a property of the profile rather than a separate check.

---

*(document in progress — more patents below as they are verified)*

---

## 4. US6687681B1 — "Method and apparatus for tax efficient investment management" (**the direct-indexing patent**)

| Field | Value |
|---|---|
| **Number** | US6687681B1 (family: US7031937B2, US8688550B1) |
| **Assignee / inventor** | Marshall & Ilsley Corporation (Milwaukee bank holding co., later absorbed by BMO) — inventors David W. Schulz, John M. Blaser, Daniel Patrick Brown, Todd Hanson |
| **Dates** | Filed 1999-05-28 · Granted 2004-02-03 |
| **Status** | **EXPIRED, twice over.** Google legal status: `Expired - Fee Related`; anticipated expiration **2019-05-28**. It lapsed early for non-payment of maintenance fees *and* has since passed its full 20-year term. The two continuations claim the same 1999 priority, so the whole family is dead. |
| **Usable now?** | **YES.** Unambiguously free. This is the strongest and cleanest hit in this whole search. |

**Mechanism in plain English.** This is direct indexing, written down in 1999, a decade
before anyone called it that. The method: (1) open a separate account per investor holding
the *individual securities* rather than a fund; (2) hold a **reduced subset** of the index
constituents chosen so a small account can still own whole shares of everything it holds
while tracking the index; (3) run a recurring optimisation that simultaneously rebalances
toward the index *and* selects which tax lots to sell for loss harvesting; (4) **space the
successive optimisation runs so the interval itself keeps you outside the IRS wash-sale
window** — the timing is part of the claimed mechanism, not an afterthought; (5) net every
account's resulting orders into one block trade and allocate fills and commissions pro rata.

**Why it matters for Aegis.** Every design constraint in this patent is Aegis's design
constraint. It is explicitly aimed at "small-to-medium net worth investors" for whom full
index replication "requires a minimum investment of over a million dollars" — Murat's
stated target is the under-$1M investor. The four reusable pieces:

- **Subset replication with a whole-share constraint.** Aegis already fights the gap between
  a 774-name research universe and a 10-name executable book. This is the published,
  free-to-use formulation of exactly that reduction, with tracking error as the objective.
- **Joint rebalance-and-harvest optimisation.** Not "rebalance, then harvest". One objective
  with both terms, which is materially better and is what Parametric charges for.
- **Wash-sale avoidance as a scheduling property.** Encode the 31-day window in the
  rebalance cadence so no separate compliance check can be forgotten. This is the same
  shape as the project's own rule that a guard must derive its inputs or refuse.
- **Trade netting across books.** Aegis runs six paper books that will frequently want the
  same name. Netting before routing is free execution improvement.

**Caveat, stated plainly:** the mechanism is free, but it is only *useful* to a US taxable
investor. It is worth nothing to a Hong Kong resident with no capital-gains tax, and nothing
inside a retirement account. Build it as an optional overlay keyed on a declared tax
jurisdiction, not as a core assumption.

---

## 5. US7337137B2 — "Investment portfolio optimization system, method and computer program product"

| Field | Value |
|---|---|
| **Number** | US7337137B2 (family: US7853510B2, US8635141B2, US20080183638A1, US20140188762A1) |
| **Assignee / inventor** | ITG Inc. → ITG Software Solutions → **Virtu ITG Software Solutions LLC**. Inventors Leonid A. Zosin and **Ananth Madhavan** (the market-microstructure economist, later BlackRock). |
| **Dates** | Priority 2003-02-20 · Filed 2003-08-14 · Granted 2008-02-26 |
| **Status** | **EXPIRED.** Google legal status: `Expired - Lifetime`, **adjusted expiration 2024-04-07** (base 20y from the 2003 filing plus patent-term adjustment). Comfortably past. |
| **Usable now?** | **YES** for this patent. ⚠️ But see the caveat: the family has later members (US8635141B2 granted 2014, and a 2014 continuation). Those claim 2003 priority so they should share the 2003+20 expiry, but **if you plan to ship the multi-portfolio claims commercially, verify US8635141B2's own term by hand** — I am confident about `137`, less so about every child. |

**Mechanism in plain English.** Three separable ideas, all now free:

1. **Confidence region instead of a point on the efficient frontier.** The mean-variance
   frontier is estimated from noisy inputs, so the patent computes a *statistical confidence
   region around the efficient set* and optimises with respect to that region rather than
   trusting one estimated frontier point. This is the honest answer to "your optimiser is an
   error-maximiser".
2. **A corrected Sharpe-ratio computation** for ranking portfolios under that uncertainty.
3. **Multi-portfolio optimisation.** Several accounts, optimised *jointly* rather than
   one at a time, so their trades interact — shared market-impact cost, netted crossing
   opportunities, and a fair allocation of the resulting impact across accounts. Portfolios
   live in an attribute hierarchy where lower levels inherit and can override constraints.

**Why it matters for Aegis.** Point 3 is the one Aegis does not have and needs: **six paper
books that currently optimise in isolation and then all send orders to the same venue.** The
project's own worst-case rule (`n names × notional% × stop%`, `Σ|notional| / equity`) is a
crude scalar version of the constraint hierarchy this patent formalises. Point 1 is directly
relevant to the programme's repeated finding that a champion's edge was five months of noise:
a confidence region over the frontier makes "this ranking is not distinguishable from that
one" a *first-class output of the optimiser* instead of a post-hoc t-test.


---

## 6. US20080288386A1 — "Method of Systematic Trend-Following" (the delta-spliced lookback straddle)

| Field | Value |
|---|---|
| **Number** | US20080288386A1 |
| **Assignee / inventor** | **Aspect Capital Limited** (London systematic macro / managed-futures firm, ~$9bn) — inventor Gavin Robert Ferris |
| **Dates** | Priority 2005-10-21 · Filed 2006-10-20 · Published 2008-11-20 |
| **Status** | **ABANDONED** — Google legal status: `Abandoned`. Never issued as a US patent; the application died in prosecution. Its disclosure is published prior art and nobody holds claims to it. |
| **Usable now?** | **YES.** An abandoned application grants no exclusive rights to anyone. |

**Mechanism in plain English.** The premise (from Fung & Hsieh) is that a trend-following
fund's return profile *is* a long lookback straddle — it makes money on big moves either
way and bleeds in quiet markets. So instead of writing entry/exit rules, you **manufacture
the straddle synthetically by delta-replication**: hold a position in the underlying equal
to the straddle's delta, recomputed as price and vol move. The inventive twist is
**delta splicing**: a normal synthetic straddle's time-to-expiry runs down to zero and
forces you out of a still-running trend at a wholly arbitrary date. When the synthetic
straddle's delta reaches ±1 (i.e. you are fully in the trend), you *swap it for a younger
straddle with a similar delta and more time to run*, so the position continues without a
liquidation-and-reopen round trip. The nominal straddle duration is not picked by fiat but
set to the horizon at which that market's implied vol has historically been the most
reliable predictor of realised vol.

**Why it matters for Aegis.** This is the single most directly transplantable mechanism in
the search, for three specific reasons tied to failures already in this project's log:

- **It is a share-only construction.** No option chain is required — the straddle is
  replicated with the underlying. The books that were emptied by
  `no chain at 2027-12-31` would not have been emptied by this.
- **It removes the arbitrary exit date.** The programme's own finding was that hack6's 3%
  stop was 0.98 daily sd and **56.3% of positions stopped out before session 10 of a
  21-session thesis**. Delta splicing is precisely a rule for *not* terminating a position
  because a clock ran out, while keeping a defined and computable risk profile.
- **The duration is derived, not declared.** Picking the horizon by "where does implied vol
  best predict realised vol for this name" is a derived parameter with a receipt, which is
  the house standard (a guard derives its inputs or refuses).

The honest caveat: Aspect abandoned it, and abandonment is weak evidence that prosecution
got hard, not that the strategy failed. But it also means you can implement it, and the
published document contains the full construction.

---

## 7. US20070288342A1 — "Method and system for algorithmic crossing to minimize risk-adjusted costs of trading securities"

| Field | Value |
|---|---|
| **Number** | US20070288342A1 |
| **Assignee / inventor** | Individual — Leon Maclin, David Mechner (the Instinet / Pragma Trading lineage) |
| **Dates** | Priority & filed 2006-05-13 · Published 2007-12-13 |
| **Status** | **ABANDONED** — never granted. |
| **Usable now?** | **YES.** |

**Mechanism in plain English.** Build the whole order around an **Almgren–Chriss optimal
trajectory**: minimise `E + λV`, where `E` is expected cost (market impact plus opportunity
cost) and `V` is the variance of the execution price, with `λ` the trader's stated risk
aversion. The novelty is that the trajectory is computed *including the probability of
crossing* — you may wait in a dark pool because a cross saves the spread, but waiting costs
price risk and alpha decay, so the optimiser trades those against each other and
continuously withdraws the un-crossed "reserve" to the lit market on schedule.

The application also states, cleanly, a result Aegis should adopt outright: **optimising to
VWAP and optimising to implementation shortfall are a *frustrated* pair** — you cannot do
both, and a desk incentivised on VWAP is being paid to do the thing that hurts the fund.

**Why it matters for Aegis.** Aegis grades itself against a fixed cost assumption — and the
C2 lane's "net −237%/yr" turned out to be a flat-100-bps/day cost artefact, i.e. the cost
model, not the strategy, produced the headline. The reusable piece here is the
**`E + λV` cost-and-risk objective with `λ` tied to the declared personality**: preservation
pays impact to get certainty, extreme growth accepts execution variance. That converts
transaction cost from a constant you assume into a decision the utility function makes,
which is what the "one brain, several personalities" design actually requires.

---

## 8. US8688558B2 — "System and method for analyzing data associated with statistical arbitrage"

| Field | Value |
|---|---|
| **Number** | US8688558B2 (parent publication US20110178958A1) |
| **Assignee / inventor** | **Credit Suisse Securities (USA) LLC** — inventor Stephen Chadwick |
| **Dates** | Priority 2006-10-30 · Filed 2011-04-04 · Granted 2014-04-01 |
| **Status** | **EXPIRED — Fee Related.** Google: `Expired - Fee Related, expires 2028-06-18`. Its *term* would have run to 2028, but it **lapsed early for non-payment of maintenance fees** and is not in force. The revival window is long past (granted 2014, first maintenance fee was due 2017-18). |
| **Usable now?** | **YES, with one honest asterisk.** Fee-lapsed patents are not enforceable, but unlike term expiry a lapse is in principle revivable on a showing of unintentional delay. Given twelve years and Credit Suisse's absorption into UBS, the practical risk to a personal OSS tool is negligible — but this is "lapsed", not "term-expired", so I flag it rather than claim it is as clean as #4. |

**Mechanism in plain English.** For a stock pair, compute the *current* relative
performance, then **search history for the times that pair stood at the same relative
level**, and look at what happened next from each of those historical moments. The trade
signal is not "the spread is 2 sigma wide" but "conditional on this pair having been here
before, the empirical distribution of the next N days' convergence looks like *this*". The
claim is explicit that the inference "comes from historical price data only" — and the
specification distinguishes this from a fundamentals-driven long/short pair and from a
merger-arb pair, where an upcoming *event*, not history, is what moves the spread.

**Why it matters for Aegis.** This is the analogue-matching formulation, and it fits the
project's stated epistemology far better than a z-score threshold: *"given what was knowable
at t, what happened from states that looked like this one?"* It is also directly runnable on
CRSP 1925-2024 plus Alpaca 2025-26, and it produces a **distribution, not a point** — which
is what a Brier-scored forecast ledger consumes. Note the patent's own three-way taxonomy
(historical-only / fundamental / event-driven) is a useful separation for Aegis's separate
`PRODUCT_EXPERIMENT` books: these are three *different alpha sources*, not three weights.

---

## 9. US20060271452A1 — "System and method for relative-volatility linked portfolio adjustment" (the CPPI successor)

| Field | Value |
|---|---|
| **Number** | US20060271452A1 (WO2006127541A2) |
| **Assignee / inventor** | Individual — Panayotis T. Sparaggis |
| **Dates** | Priority & filed 2005-05-25 · Published 2006-11-30 |
| **Status** | **ABANDONED** — never granted (US and WO members both dead). |
| **Usable now?** | **YES.** |

**Mechanism in plain English.** This application is the best plain-language exposition of CPPI
I found on Google Patents, *and* it proposes a fix for CPPI's defining flaw. Standard CPPI
splits capital between a zero-coupon bond (the floor) and a risky asset, with risky exposure
= multiplier x (portfolio value - floor); when the cushion shrinks the exposure shrinks, and
in a gap-down the strategy "cash-locks" — permanently pinned to the bond with no upside left.
The proposal: size the risky leg off the **relative volatility of the risky asset against a
reference index**, not off the cushion alone. When the managed asset is behaving more
violently than its reference, exposure is cut *before* the cushion is consumed, rather than
after.

**Why it matters for Aegis.** Aegis has a drawdown-budget ruler (the second of the "two
rulers" — terminal wealth at a declared drawdown budget) and no principled machine for
enforcing it. CPPI is that machine, and this document contains both the standard algorithm
and a named failure mode with a proposed fix. Note the project already learned this exact
lesson from the other direction: **a flat 0.35 drawdown budget refused 188 of 207 genomes
because the VW market itself drew down 47.2%** on the same window. A *relative*-volatility
floor is the same correction — the budget is measured against a reference, not against an
absolute number the benchmark itself cannot meet.

---

## 10. US20060100949A1 — "Financial indexes and instruments based thereon" (the BXM buy-write index)

| Field | Value |
|---|---|
| **Number** | US20060100949A1 (CIP of US20030225658A1; later US20100005032A1) |
| **Assignee / inventor** | Listed as "Individual" — inventors **Robert Whaley** (the VIX author), **Catherine Shalen**, **William Speth**; Shalen and Speth were CBOE research staff, so this is the CBOE BXM index in patent form. |
| **Dates** | Priority 2003-01-10 · Filed 2005-09-29 · Published 2006-05-11 |
| **Status** | **ABANDONED** — never granted. |
| **Usable now?** | **YES.** |

**Mechanism in plain English.** A fully mechanical, investable covered-call rule: hold the
index portfolio; each month, at a stated time on the third Friday, write the nearby
just-out-of-the-money call with ~one month to expiry; hold to expiry; cash settle; rewrite.
The document's second embodiment is the interesting one: **write the call at least 30 days
before its expiry and do not cash-settle, so the position qualifies as a "qualified covered
call" under IRC section 1092(c)(4)** and escapes the straddle rules — a tax-driven change to
the mechanics of a strategy, expressed as a rule an engine can execute.

**Why it matters for Aegis.** Two reusable things. First, it is a fully specified *income
overlay* with no discretion anywhere — exactly the frozen strategy contract a
`PRODUCT_EXPERIMENT` requires (policy hash, timestamp, inputs, fill convention, objective),
and the paper trail for it is the CBOE's own published BXM history back to 1988. Second, and
more valuable: it demonstrates **tax treatment as a mechanism parameter**. A 30-day write
and a 29-day write are the same strategy gross and different strategies net. That is the
same class of insight as the wash-sale cadence in #4, and Aegis's cost model currently has
no slot for it at all.

---

## 11. US7873530B2 — "Method and system for solving stochastic linear programs with conditional value at risk constraints"

| Field | Value |
|---|---|
| **Number** | US7873530B2 (publication US20090271230A1) |
| **Assignee / inventor** | **International Business Machines Corporation** — Pu Huang, Dharmashankar Subramanian |
| **Dates** | Priority & filed 2008-04-28 · Granted 2011-01-18 |
| **Status** | **EXPIRED — Fee Related.** Google: `Expired - Fee Related, expires 2029-07-09`. Term would have run to 2029; it lapsed early for non-payment. Same asterisk as #8: lapsed, not term-expired. IBM lets large numbers of patents lapse deliberately; practical risk to a personal OSS tool is very low. |
| **Usable now?** | **YES**, with the lapse caveat stated. |

**Mechanism in plain English.** The naive way to put a CVaR constraint into a linear program
is the Rockafellar-Uryasev reformulation, which introduces **one auxiliary variable per
scenario** — so a 10,000-scenario problem becomes a 10,000-extra-variable LP that is slow
and memory-hungry. This patent replaces that with a **sequence of small linear programs whose
solutions provably converge** to the same optimum, and extends the same trick to
mixed-integer problems (which is what you need when holdings must be whole shares or a name
is in-or-out).

**Why it matters for Aegis.** This is the computational enabler for #1 at Aegis's actual
scale. CRSP gives ~925,757 name-months and the farm runs hundreds of strategy variants per
night on one machine; a scenario-per-variable CVaR LP will not fit in that budget, and a
cutting-plane sequence of compact LPs will. The mixed-integer extension is what makes
"whole shares, at most k names, minimum position size" expressible as a constraint instead
of a post-hoc rounding step that silently changes the portfolio you actually tested.

---

## 12. US8374951B2 — "System, method, and computer program product for managing a virtual portfolio of financial objects" (**Fundamental Indexation / RAFI**)

| Field | Value |
|---|---|
| **Number** | US8374951B2 — one member of a large family including US7117175B2, US7620577B2, US7747502B2, US7587352B2, US7792719B2, US8005740B2 |
| **Assignee / inventor** | **Research Affiliates, LLC** — **Robert D. Arnott**, Paul C. Wood |
| **Dates** | Priority 2002-04-10 · Filed 2009-09-07 · Granted 2013-02-12 |
| **Status** | **EXPIRED.** Google: `Expired - Fee Related, expires 2023-04-10` — 20 years from the 2002 priority, *and* fee-lapsed. ⚠️ **But this is a big family**: every member claiming 2002-2004 priority shares that expiry, and I verified only this one individually. If you intend to publish a RAFI-labelled product, check each member you rely on. |
| **Usable now?** | **YES** for this patent and for anything claiming 2002-2004 priority. |

**Mechanism in plain English.** Build an index whose constituents are selected and weighted
by **accounting measures of company size** — sales, cash flow, book value, dividends —
instead of by market capitalisation. Because the weights do not move with price, the index
mechanically trims names whose price has run ahead of their fundamentals and adds to names
whose price has fallen behind, and it must be rebalanced on a schedule to restore the
fundamental weights.

**Why it matters for Aegis.** First, a worked lesson in a caution this file must repeat: the
**Google family-level flag said `US:ACTIVE` for this patent while the individual patent page
says `Expired - Fee Related, expires 2023-04-10`**. The aggregated country status covers the
whole family, not the document you are looking at. Every "usable" claim resting on a family
flag alone is weaker than one resting on an individual page — which is why the individual
pages were fetched for the entries that matter.

On substance: RAFI is a **non-price weighting scheme**, and Aegis's diagnosed bottleneck is
that ten arena books all select on one signal (12-1 momentum for 99.5% of names). A
fundamental-weight book is a genuinely independent selector whose errors are different
errors — precisely the test the project says a new mechanism must pass — and it arrives as
its own `PRODUCT_EXPERIMENT` book rather than as a weight in `arena_composite`.

---

## 13. US20050262010A1 — "Systems and methods for converting closed-end funds to actively managed exchange traded funds"

| Field | Value |
|---|---|
| **Number** | US20050262010A1 |
| **Assignee / inventor** | **American Stock Exchange LLC** → merged into NYSE Alternext / NYSE American LLC — inventors Robert S. Tull Jr., Thomas Rzepski |
| **Dates** | Priority 2004-05-21 · Filed 2005-05-20 · Published 2005-11-24 |
| **Status** | **ABANDONED** — never granted. |
| **Usable now?** | **YES** (and largely moot as a *product* — it needs a fund sponsor; the *analytics* are the reusable part). |

**Mechanism in plain English.** A closed-end fund's price drifts from NAV because there is no
creation/redemption arbitrage and the portfolio is only disclosed quarterly, 60 days stale.
The proposal writes a trigger into the fund's own governing documents — *if shares trade
more than X% from NAV, or stay at a discount for N days, the CEF converts into an actively
managed ETF* — and, to make that ETF tradable without full portfolio disclosure, publishes
a **hedging portfolio and an intraday NAV estimate** built from a disclosed subset of
holdings.

**Why it matters for Aegis.** Aegis cannot convert a fund. What it can lift is the
**estimated-NAV-plus-hedging-basket** construction: from partial, stale holdings disclosure,
build a tradable proxy basket and a live fair-value estimate, then trade the gap between
observed price and estimated value. Aegis has exactly the inputs this needs — **13F panels**
(quarterly, stale, partial: the same information problem, one asset class over) plus daily
bars. That yields a testable `PRODUCT_EXPERIMENT`: estimate a fund's or a manager's current
NAV from stale 13F holdings plus a fitted hedging basket, and trade the discount. And it is a
genuinely different alpha source from momentum, which is the bottleneck the project named.

---

## 14-17. FOUND BUT **NOT USABLE** — active patents, listed so nobody hopefully re-finds them

| # | Number | Assignee | Status | Mechanism | Why not usable |
|---|---|---|---|---|---|
| 14 | **US11195232B2** | **Axioma Inc.** (now SimCorp / Deutsche Börse) | **ACTIVE**, anticipated expiration **2036-09-29** | Hierarchical scenario-based CVaR: minimise CVaR at *several* confidence levels at once, via a regularised Rockafellar-Uryasev formulation restricted to an **elliptical uncertainty set** around the return estimates; one embodiment hedges an equity book with options. | In force for another decade, held by a commercial risk vendor whose business this is. **Do not implement the hierarchical multi-confidence-level + elliptical-uncertainty-set combination.** Plain single-level CVaR (#1, #11) is free; this specific stack is not. |
| 15 | **US10373254B2** | **New York Life Insurance Company** | **ACTIVE** (granted 2019-08-06, priority 2011-03-10) | Transfers money between two "investment sleeves" during a waiting period on a **CPPI or modified-CPPI schedule** to support guaranteed income payments. | In force. Note the *underlying* CPPI is free (see section 0); what is claimed is the sleeve-transfer-for-income-guarantee application. Aegis does not issue guarantees, so this is easy to stay clear of. |
| 16 | **US20190066208A1** | **JPMorgan Chase Bank, N.A.** | **ACTIVE** family (published 2019, priority 2017-08-24) | Dynamic ETF implementation that adjusts the per-unit creation basket **using tax-lot information to push the highest-basis lots out on redemption and keep the lowest**, i.e. weaponising the in-kind redemption channel for tax. | Recent and in force. This is the *ETF-sponsor* version of tax-lot optimisation. The *separate-account* version (#4) is expired and free — use that one. |
| 17 | **US8533098B2** / US20140244474A1 | Remington John Sutton (individual) | **Likely ACTIVE** — granted 2013-09-10, priority 2007-11-06, family flag `US:ACTIVE`. **STATUS UNVERIFIED — check manually.** A 2007-priority term would run to ~2027-28 if fees are paid. | Real-time statistical-pairs arbitrage: correlated instrument pairs with buy/sell triggers from indicators refreshed on a **5-second** cycle. | I did not fetch the individual page, and the claimed term has not obviously run. Treat as live. The expired analogue-matching alternative (#8) covers the same ground with a better formulation anyway. |

---

## NEGATIVE RESULTS — searched for, not found. Said plainly rather than invented.

- **Index-reconstitution / anticipatory trading systems.** No patent found. The subject is
  well developed in the *academic* literature (e.g. the HBS working paper *"Optimal
  Index-Linked Rebalancing with Anticipatory Trading"*, which models trackers trading off
  execution cost against tracking error while speculators pre-position, and concludes that
  apparent front-running is competitive liquidity provision that *benefits* index investors)
  — but nobody appears to have patented the trading system. Patent hits on
  "index reconstitution" are all *index-construction* patents (IPOX US7698197B1, dynamic
  indexing US20100070427A1, serialized index US20130046677A1), not anticipation strategies.
  **Freely implementable; nothing to license and nothing to fear.**
- **Merger-arbitrage spread modelling systems.** No dedicated patent found. Every hit
  mentions merger arbitrage only inside a *list of hedge-fund style categories* (the Bdellium
  US8296211B2 and Vioni US9070165B2 patents). Mitchell-Pulvino's "merger-arb returns look
  like short index puts" is journal literature and permanently public.
- **Earnings-announcement option strategies (straddle/strangle around scheduled events).**
  No patent found that claims the *event* strategy. The closest hits are the Aspect
  trend-following straddle (#6, abandoned, and not event-driven) and a UNL academic
  disclosure of derivative-strategy composition. The straddle-around-earnings literature
  (Goyal-Saretto, Gao et al., Milian 2023 on weekly options) is entirely public.
  **Freely implementable.**
- **Bridgewater, AQR, D. E. Shaw, Renaissance, Two Sigma as assignees.** Nothing relevant
  surfaced. These firms protect by trade secret, not patent — which is itself the finding:
  **there is no patent thicket over systematic macro or statistical arbitrage.** The patents
  that exist in this space come from *vendors and brokers* (ITG, Credit Suisse, Axioma, IBM,
  CBOE) who had to disclose in order to sell, not from the funds who had to hide in order to
  earn.
- **Leland O'Brien Rubinstein.** See section 0. No patents, ever.

---

## TOP 3 FOR AEGIS

1. **US6687681B1 — Marshall & Ilsley, direct indexing (EXPIRED 2019, also fee-lapsed).**
   The cleanest status in the file and the closest fit to the mission: it was written *for*
   the sub-$1M investor who cannot replicate an index, and it hands over subset replication
   under a whole-share constraint, a joint rebalance-and-harvest objective, wash-sale
   avoidance encoded in the rebalance cadence, and cross-account trade netting — the last of
   which Aegis's six books need today regardless of tax.

2. **US20080288386A1 — Aspect Capital, delta-spliced lookback straddle (ABANDONED).**
   A trend-following position built entirely from the underlying, with no option chain to go
   missing and **no arbitrary expiry date forcing an exit from a live thesis** — the exact
   failure that emptied hack1 and stopped out 56.3% of hack6's positions before session 10 of
   a 21-session thesis. Its straddle duration is derived from where implied vol best predicts
   realised vol, so the parameter arrives with a receipt instead of a preference.

3. **US5148365A + US7873530B2 as a pair — Dembo's scenario optimisation (EXPIRED 2009) run
   by IBM's compact-LP CVaR solver (fee-expired).** One is the objective Aegis actually
   wants — optimise terminal wealth against an **asymmetric, personality-specific** penalty
   over sampled futures, which is what "four declared personalities, one brain" means
   mathematically — and the other is what makes it run on one machine at CRSP scale with
   whole-share integer constraints. Neither is enforceable. Axioma's #14 is the paid version
   of the same idea and is in force until 2036; these two are the free path to most of it.

---

## METHOD AND ITS LIMITS (read before relying on any status above)

- Statuses marked **EXPIRED** or **ABANDONED** on an *individual Google Patents page* (#4,
  #5, #6, #7, #8, #9, #10, #11, #12, #13, #14) were read from that page's own legal-status
  line. Statuses for #1, #2, #3 were derived from filing/grant dates under pre-GATT term
  rules plus the family flag; the arithmetic is not close (all lapsed 10+ years ago).
- Google's own disclaimer applies and I repeat it: *"The legal status is an assumption and is
  not a legal conclusion. Google has not performed a legal analysis."* For anything Aegis
  would **publish or commercialise**, confirm on USPTO Patent Center and the Patent
  Maintenance Fee file before relying on it.
- "Expired — Fee Related" (#8, #11, #12) means *lapsed for non-payment*, which is a different
  legal object from *term expiry*: lapses can in principle be revived on a showing of
  unintentional delay. For #12 the term has *also* run (2023), so it is doubly dead. For #8
  and #11 only the fee lapse applies; both are many years past the revival window and held by
  entities (Credit Suisse→UBS, IBM) that lapse patents by policy, but that is judgement, not
  certainty.
- Google Patents' `xhr/query` endpoint rate-limited this session part-way through, so the
  later half of the search ran through a third-party search index against the same
  patents.google.com pages. No status in this file rests on a third-party aggregator's own
  summary — every one was read off a patents.google.com page or derived from dates.
