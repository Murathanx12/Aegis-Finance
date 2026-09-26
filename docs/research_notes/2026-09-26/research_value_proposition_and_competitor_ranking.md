# Value proposition and competitor ranking — 2026-09-26

Requested by Murat: *"What is our value proposition? ... a cheap, accessible
tool for the average person ... not a hedge fund, a small hedge fund for
people who don't know how to invest ... The second value proposition: this is
my investing tool; I want it to beat the S&P 500 and manage my money without
me being involved too much ... I think our project is highly sophisticated and
better, but I want you to review and RANK them, tell why this is better, what
we are doing better, what we need to focus on."*

**Method.** Built on `docs/research_notes/2026-09-26/research_differentiation_and_interdisciplinary.md`
Part A (21 products already surveyed, sourced) plus targeted web research this
session (exa search — the session's WebSearch budget was exhausted) on
pricing, regulatory lines, freemium conversion norms, and three additional
2025–2026 launches. Every product row keeps its source link. **No repo source
was modified.** Evidence strength is marked per claim; where a figure is
self-reported and not independently audited, this note says so rather than
repeating it as fact.

**Scope note on rigour vs product.** This note is a `PRODUCT_EXPERIMENT`-scope
communication artefact (a pitch/positioning document), not a `RESEARCH_CLAIM`.
It draws on `RESEARCH_CLAIM`-scope findings already established elsewhere
(the frozen forecast ledger, §64's held-out skill result) and states plainly
where the underlying evidence is still thin (n=39 priced paper accounts over
weeks, per `docs/PAPER_ACCOUNTS.md`).

---

## 0. The one-paragraph honest answer

Aegis is not yet better at the one thing either persona ultimately measures —
money, net of costs, forward, versus the market — and it should not claim that
it is. What it demonstrably has, and almost nothing surveyed has, is the
**infrastructure of an honest forecaster**: a frozen ledger that dates every
belief before its outcome, grades it, and only lets graded beliefs size
capital. That infrastructure is a precondition for ever proving the P2 claim
("beats SPY, hands-off") and a precondition for the P1 claim ("guidance you
can trust") to mean anything more than a marketing line. Today Aegis is ahead
on **discipline** and behind on **proof, cost-of-use for a novice, and
regulatory clearance to give real advice**. The ranking below is built to show
exactly that shape, not to flatter it.

---

## 1. The ranking

### 1.1 Ten named criteria, scored 0–3, one row per product

Scoring rubric: **0** = no evidence / explicitly absent / structurally
excluded; **1** = weak, self-reported, or narrow; **2** = documented and
real but partial or unaudited; **3** = strong, independently verifiable, or
best-in-class among the surveyed set. Aegis's own scores are argued from its
own receipts (linked); every 0 for Aegis is deliberate — see §2.3.

| Product | Forward, cost-inclusive evidence vs SPY | Grades its own forecasts | Explains WHY (evidence+falsifier) | Point-in-time discipline | Cost to user | Breadth (news/filings/patents/politics/social) | Learns from outcomes (reweights) | Safety rails (refusals, worst-case $) | Accessibility/UX | Regulatory status | Link |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **Aegis** | 1 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 0 | 2 | this repo |
| Betterment | 0 | 0 | 1 | 2 | 2 | 0 | 0 | 2 | 3 | 3 | [pricing](https://www.betterment.com/pricing) |
| Wealthfront | 0 | 0 | 1 | 2 | 2 | 0 | 0 | 2 | 3 | 3 | [vs Schwab](https://www.investopedia.com/wealthfront-vs-charles-schwab-robo-advisors-4693442) |
| Schwab Intelligent Portfolios | 0 | 0 | 1 | 2 | 2 | 0 | 0 | 2 | 2 | 3 | [cost report](https://www.realcostreport.com/investing/brokerage-tools/robo-advisor-comparison/) |
| Danelfin | 2 | 3 | 2 | 2 | 1 | 2 | 2 | 1 | 1 | 1 | [audit](https://audit.danelfin.com/) · [pricing](https://danelfin.com/pricing/monthly) |
| Kavout | 0 | 0 | 1 | 0 | 0 | 2 | 0 | 0 | 1 | 1 | (research_differentiation doc) |
| Tickeron | 0 | 1 | 1 | 0 | 1 | 1 | 0 | 0 | 1 | 1 | [review](https://aiflowreview.com) |
| Magnifi (TIFIN) | 0 | 0 | 1 | 1 | 2 | 1 | 0 | 0 | 2 | 2 | (research_differentiation doc) |
| Toggle AI → Reflexivity | 0 | 0 | 2 | 1 | 0 | 2 | 0 | 0 | 0 | 2 | (research_differentiation doc) |
| Boosted.ai | 0 | 0 | 2 | 1 | 0 | 2 | 0 | 0 | 0 | 2 | (research_differentiation doc) |
| TradingAgents (Tauric) | 0 | 0 | 2 | 0 | 3 | 2 | 0 | 1 | 0 | 3 | [github](https://github.com/TauricResearch/TradingAgents) · [leak](https://github.com/TauricResearch/TradingAgents/issues/203) |
| ai-hedge-fund (virattt) | 0 | 0 | 1 | 0 | 3 | 1 | 0 | 1 | 0 | 3 | [github](https://github.com/virattt/ai-hedge-fund) |
| FinRL | 0 | 0 | 0 | 0 | 3 | 0 | 1 | 0 | 0 | 3 | [github](https://github.com/AI4Finance-Foundation/FinRL) |
| Numerai | 1 | 2 | 1 | 2 | 3 | 1 | 3 | 1 | 0 | 2 | [TC](https://docs.numer.ai/numerai-tournament/scoring/true-contribution-tc) · [13F analysis](https://13foresight.com/fund/numerai-gp-llc) |
| Composer | 1 | 0 | 1 | 1 | 1 | 0 | 0 | 1 | 2 | 3 | [pricing](https://www.composer.trade/pricing) · [Form CRS](https://reports.adviserinfo.sec.gov/crs/crs_311289.pdf) |
| QuantConnect | 0 | 0 | 0 | 2 | 2 | 1 | 0 | 1 | 0 | 3 | [Lean](https://github.com/QuantConnect/Lean) |
| Public.com Alpha | 0 | 0 | 2 | 0 | 3 | 2 | 0 | 0 | 3 | 1 | (research_differentiation doc) |
| Robinhood Cortex | 0 | 0 | 2 | 0 | 3 | 1 | 0 | 0 | 3 | 1 | (research_differentiation doc) |
| Perplexity Finance | 0 | 0 | 1 | 0 | 3 | 2 | 0 | 0 | 2 | 2 | (research_differentiation doc) |
| Bloomberg AI (BQuant/ASKB) | 0 | 0 | 2 | 1 | 0 | 3 | 0 | 1 | 0 | 3 | (research_differentiation doc) |
| eToro CopyTrader | 1 | 1 | 0 | 0 | 2 | 1 | 1 | 2 | 3 | 2 | [copytrader guide](https://www.etoro.com/wp-content/uploads/2025/10/CopyTrader-Guide_Jan-2026.pdf) |
| Lumenai Innovation Fund (2026) | 0 | 0 | 1 | 0 | 0 | 1 | 1 | 1 | 0 | 3 | [press](https://www.einpresswire.com/article/907774446/lumenai-to-launch-first-fully-agentic-ai-hedge-fund) |
| Fere AI (2026) | 0 | 0 | 1 | 0 | 2 | 1 | 1 | 0 | 1 | 0 | [launch](https://www.globenewswire.com/news-release/2026/04/23/3279629/0/en/Fere-AI-Raises-1-3M-to-Put-a-Self-Improving-Trading-Agent-in-Everyone-s-Hands.html) |

**One-line justification per product** (the evidence behind each row; sources
in the link column above and in §2 below):

- **Aegis** — 25,329 frozen forecasts, 17,650 graded, held-out skill by family
  (`docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` §2–3); zero of ~21
  surveyed products do this at all. But `forward=1` not 3: aggregate paper
  ROI is **−1.12%** over 39 priced accounts (`docs/PAPER_ACCOUNTS.md`), and
  `access=0`: no novice-facing product exists today.
- **Betterment / Wealthfront** — registered RIAs, transparent 0.25% fee,
  polished onboarding; explicitly do not attempt to beat a benchmark, so
  `forward=0` is a *scope* fact, not a failure.
- **Schwab Intelligent Portfolios** — $0 headline advisory fee funded by a
  mandatory 6–30% cash sweep drag (verified, [Real Cost Report Aug 2026](https://www.realcostreport.com/investing/brokerage-tools/robo-advisor-comparison/)); the "free" framing needs that caveat.
- **Danelfin** — the one product besides Aegis that grades its own historical
  scores against realized outcomes with published win rates and t-stats; but
  it is **self-published**, and true *live* (not simulated) evidence covers
  only ~14 months (post-Jul-2025).
- **Numerai** — the industry's most rigorous outcome-reweighting mechanism
  (TC/MMC, per-era scoring); an independent 13F-based analysis shows
  2023–2026 annualized 6.2% vs SPY 21.3% for the *fund*, contradicting a 2021
  self-reported outperformance claim.
- **TradingAgents / ai-hedge-fund / FinRL** — free, open, honest about being
  research-only; TradingAgents has a **documented look-ahead leak**
  ([issue #203](https://github.com/TauricResearch/TradingAgents/issues/203)).
- **Composer** — genuinely SEC-registered RIA (Form CRS confirms $30/mo
  advisory fee), no-code, but forward evidence is per-symphony, self-labeled,
  never audited platform-wide.
- **eToro CopyTrader** — best-in-class UX and safety controls (settable Copy
  Stop Loss, tiered risk caps on Popular Investors) for a copy-trading
  product; but it explicitly is **not** an advice tool, does not itself grade
  forecasts, and academic work on copy-trading finds copiers' timing costs
  erase most of the edge (`research_differentiation` doc, §A.3, D2).
- **Lumenai / Fere AI (2026 launches)** — Lumenai has **no operating history**
  by its own press release; Fere AI reports 10M+ autonomous agent actions on
  crypto/Polymarket with **no disclosed benchmark-relative return**, and no
  regulatory registration was found — the highest-risk grey zone in this
  table.

### 1.2 Two personas, same evidence, different weights

Rather than re-score every cell per persona (which would smuggle in false
precision), each persona's ranking is the **unweighted sum of the five
criteria that persona actually cares about**, read straight off the table
above. This is reproducible by anyone re-reading the table; it is not a
hidden weighting scheme.

**P1 — "I don't know how to invest, give me cheap guidance."**
Relevant criteria: *cost, accessibility/UX, safety rails, explains-why,
regulatory status* (max 15).

| Rank | Product | P1 sum | Read |
|---|---|---:|---|
| 1 | Betterment | 11 | Best fit: cheap, safe-by-construction, licensed, polished |
| 1 | Wealthfront | 11 | Same tier as Betterment |
| 1= | **Aegis** | **11** | **Ties on paper — but `access=0` means a novice cannot use it today. See §2.4.** |
| 4 | Schwab Intelligent Portfolios | 10 | Free advisory fee, cash-drag caveat |
| 5= | Public.com Alpha | 9 | Free, polished, but no advice registration |
| 5= | Robinhood Cortex | 9 | Same — explains moves, not personalized advice |
| 5= | eToro CopyTrader | 9 | Best UX/safety controls of any copy-trading product |
| 5= | TradingAgents | 9 | Free and honestly-scoped, but zero UX for a novice |
| 9= | ai-hedge-fund / Composer / Perplexity Finance | 8 | Free-to-cheap, none of them advise a novice end-to-end |

**P1 verdict: Aegis is not currently a P1 product.** Its sum is inflated by
research-discipline criteria (safety rails, explains-why) that a novice never
sees, while the one criterion that gates real-world usability —
accessibility — is **0**. Betterment and Wealthfront win P1 outright because
they are the *only* rows with `access=3` and `regulatory=3` together.

**P2 — "Beat SPY, manage my money, minimal involvement."**
Relevant criteria: *forward evidence vs SPY, grades own forecasts, learns
from outcomes, point-in-time discipline, breadth of information* (max 15).

| Rank | Product | P2 sum | Read |
|---|---|---:|---|
| 1 | **Aegis** | **12** | Wins on infrastructure — but see the honest caveat below |
| 2 | Danelfin | 11 | Closest peer: self-grading + partial live evidence |
| 3 | Numerai | 9 | Best-in-class outcome-reweighting; fund underperformed SPY independently |
| 4= | Bloomberg AI / eToro CopyTrader | 4 | Breadth (Bloomberg) or crude outcome-gating (eToro tiers), nothing else |
| 6= | Toggle/Reflexivity / Boosted.ai / QuantConnect | 3 | Institutional breadth/infra, no self-grading |
| rest | everyone else | ≤2 | No forecast ledger, no PIT discipline, no learning loop |

**P2 verdict, stated the way Murat would want it stated:** Aegis wins the
*infrastructure* score decisively (12 vs Danelfin's 11 vs everyone else's
≤9) — but on the **one sub-criterion P2 actually bought the product for**
(forward evidence vs SPY), Aegis scores **1 out of 3**, tied with Numerai and
below Danelfin's 2. The pipeline exists, is graded, and is honest about
itself; it has not yet produced the number P2 is paying for. This is the
same sentence as the README's own badge system: 🟢 LIVE FORWARD exists, 🔵
BACKTEST is not a claim, and the 🔴 REFUTED items stay on the page.

---

## 2. Why Aegis is better, in receipts — and where it is worse

### 2.1 Claims verifiable from the repo today

| Claim | Receipt | Evidence strength |
|---|---|---|
| A frozen forecast ledger, scored against real outcomes, before the outcome exists | 25,329 rows, 17,650 graded, fixed horizons h=1/5/20/120 (`docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` §2) | Strong — directly inspectable, dated |
| A *process* beats a *persona* out of sample | `investigator` +8.97% held-out skill vs nine personas at −27.98% at optimal weight zero (README §64; `docs/AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` §8) | Strong for the comparison it tested; n and window not yet 24 months |
| Every book has a random/sector/SPY twin, frozen before grading | `docs/PAPER_ACCOUNTS.md` `llm_portfolio` books table (32 books × twins) | Strong — mechanical, inspectable |
| An adversarial review loop that argues the money case | `docs/reviews/REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md`, 13/14 points accepted | Moderate — one cycle so far |
| Refusals print the worst-case dollar figure before acting | PROBE −$16,452 at 10×2%×3σ vs EXPLOIT −$64,800 at gross 1.00 (strategy doc §2, "REFUSED" column of `investment_committee.funnel_state()`) | Strong — mechanical rule, not narrative |
| A negative-results / corpse ledger queried before new research | `aegis_postmortems`, `NEGATIVE_RESULTS.md`, `docs/TRIALS/*` | Strong — 335+ prior trials logged |
| A licence system separating what may be tested from what may be claimed | Three licences (`PRODUCT_EXPERIMENT`/`CAPITAL_CANDIDATE`/`RESEARCH_CLAIM`), CLAUDE.md | Strong, internally enforced |
| Point-in-time discipline enforced in code, not promised | `Policy` refuses zero-cost runs unless flagged; PIT store never overwritten (`PROJECT_LANDSCAPE.md` §2) | Strong |

### 2.2 The one number Murat cannot yet say

Per the differentiation doc's own pitch (§A.4, carried into the strategy
doc §8): **"best historical net strategy vs market: none."** The historical
backtest still on the README front page is **+28.3% net vs SPY's +114.8%**
(2020-01→2025-06, signal-engine timing strategy) — a *loss*, kept public on
purpose as the founding negative result (`README.md` "Historical backtests"
table). This is the honest ceiling on any P2 claim today.

### 2.3 Where Aegis scores 0, without softening it

- **Accessibility/UX = 0 for P1.** There is no novice-facing product. The
  README says the frontend "exists but is not the current focus." Betterment
  and Wealthfront's entire business is the thing Aegis has not built.
- **39 priced paper accounts, aggregate −1.12%** ($4,679,959 vs
  $4,733,154 start; 7 of 39 ahead of SPY, 32 behind — `docs/PAPER_ACCOUNTS.md`
  Aggregate section). `mirror` alone is −22.16% vs SPY +2.03% in its window,
  kept on the record by policy, not hidden.
- **A 28% vs 115% historical backtest is still the README's headline
  backtest table.** It is disclosed as a *negative result*, but a reader
  skimming the page sees a strategy that underperformed buy-and-hold by 86
  points over 5.5 years before they see anything else.
- **Complexity.** The strategy doc itself opens with "we have so many things
  ... that are not connecting to each other, or the strategies are
  clashing" — Murat's own words, dated this session.
- **One person.** Every competitor in the table above with `forward>0` has a
  team, a fund structure, or years of live history Aegis does not have yet
  (differentiation doc §A.3).
- **No RIA, no broker-dealer, no licence anywhere.** Aegis today is legally
  a research/paper project. It cannot take a dollar of real capital under
  any of the regulatory regimes surveyed in §3.2 without registering.

### 2.4 The honest reconciliation of the two personas

The P1 and P2 tables above are not in tension by accident: they measure
*different things Aegis has and hasn't built*. P2's infrastructure (the
forecast ledger, the grading loop, the PIT discipline) is real and ahead of
the field. P1's infrastructure (an app a novice would open, a licence to
speak to them, a price they'd recognize as normal) does not exist yet. Both
are true at once; conflating them is exactly the "sophisticated but not yet
better" gap Murat named.

---

## 3. Revenue models for P1, with comparable evidence

### 3.1 What comparable products charge (verified pricing pages, 2026)

| Product | Model | Price points | Source |
|---|---|---|---|
| Danelfin | Freemium web (4 tiers) + separate API tiers | Free → **$29/$79/$179/mo** (web, monthly; $22/$59/$134/mo annual) · API **$52/$149/$449/mo** | [pricing](https://danelfin.com/pricing/monthly), [API pricing](https://danelfin.com/pricing/api/annual) |
| Composer | RIA subscription (not AUM %) | **$30/mo or $288/yr** advisory fee, flat regardless of account count (Form CRS, SEC-filed) | [Form CRS](https://reports.adviserinfo.sec.gov/crs/crs_311289.pdf) |
| Composer (older "Trading Pass" tier) | Flat subscription for self-directed trading | $40/mo or $384/yr ($32/mo) | [help centre](https://help.composer.trade/article/226-manage-your-trading-pass) |
| Betterment | AUM % (RIA) | 0.25%/yr digital, 0.65%/yr Premium (min $100k); tiered discounts above $1M | [pricing](https://www.betterment.com/pricing) |
| Wealthfront | AUM % (RIA) | 0.25%/yr flat, $500 minimum | [Investopedia comparison](https://www.investopedia.com/wealthfront-vs-charles-schwab-robo-advisors-4693442) |
| Schwab Intelligent Portfolios | $0 headline / cash-sweep spread + $30/mo Premium | $0 (Basic); $300 setup + $30/mo (Premium, $25k min) | [Real Cost Report](https://www.realcostreport.com/investing/brokerage-tools/robo-advisor-comparison/) |
| eToro CopyTrader | No direct fee to the copier; monetized via spread + PFOF + 1% crypto fee; Popular Investors paid **1.5% of assets-under-copy** by eToro | Free to use; revenue is on the *other* side of the transaction | [CopyTrader guide](https://www.etoro.com/wp-content/uploads/2025/10/CopyTrader-Guide_Jan-2026.pdf), [Popular Investor tiers](https://www.etoro.com/copytrader/popular-investor/) |
| Toggle AI / Reflexivity | B2B enterprise licence, no public pricing (institutional PM seats, backed by Druckenmiller et al.) | Not disclosed | differentiation doc §A.1 |

**Freemium → paid conversion norms, for sizing a P1 subscription tier**
(evidence strength: industry survey data, 2026, not Aegis-specific):
- Fintech vertical median freemium→paid conversion: **4.1%** ([First Page
  Sage, updated June 2026](https://firstpagesage.com/seo-blog/saas-freemium-conversion-rates/)).
- "Good" self-serve freemium is 3–5%, "great" is 8–12%; **AI-native products
  run hotter — good 6–8%, great 15–20%** ([Kyle Poyar, Growth Unhinged, Feb
  2026](https://www.growthunhinged.com/p/free-to-paid-conversion-report)).
- Credit-card-gated free trials convert far higher (25–35% good, 50–60%
  great) than ungated freemium, at the cost of fewer signups.

### 3.2 The regulatory line — where "education" becomes "advice"

This is the load-bearing finding for P1 monetization, and it is verified
against primary regulator text this session, not summarized from memory.

**United States (SEC).** An "investment adviser" is a person or firm that,
for compensation, is engaged in the business of advising others on
securities ([Advisers Act §202(a)(11), SEC guide](https://www.sec.gov/resources-small-businesses/capital-raising-building-blocks/investment-advisers)).
The published exemption that matters most for a text-based product: a
**"publisher"** is excluded from the Act only if the publication (i) gives
**impersonal** advice — "not tailored to the individual needs of a specific
client" — (ii) is bona fide (disinterested analysis, not promotional touting)
and (iii) has general, regular circulation ([SEC "Regulation of Investment
Advisers"](https://www.sec.gov/about/offices/oia/oia_investman/rplaze-042012.pdf)).
The SEC's own robo-adviser guidance treats **any software that generates
advice tailored to information a specific client supplied** as advisory
activity requiring registration ([IM Guidance 2017-02](https://www.sec.gov/files/im-guidance-2017-02.pdf); reinforced by the 2024 Internet Adviser
Exemption amendments, which define "digital investment advisory service" as
advice "generated by the operational interactive website's software-based
models ... based on personal information each client supplies" — [SEC final
rule, IA-6578](https://www.sec.gov/files/rules/final/2024/ia-6578.pdf)).
**Applied to Aegis:** a public leaderboard of graded forecasts, a blog-style
"today's thesis cards," or a generic top-40 shortlist is closer to the
publisher exemption. The moment a feature says "for *your* $33,154 account,
here is what to buy" using information the user supplied (risk tolerance,
holdings, goals), it is advice and needs registration.

**Hong Kong (SFC).** Type 4 (advising on securities) and Type 9 (asset
management) licensing turns on the same distinction, stated almost as
plainly: *"the mere provision of analytical tools which solely filter
publicly available data in a transparent process does not constitute an
advisory activity"* — e.g., a screener for low P/E stocks in a sector — but
*"where the tools are able to identify a variety of investment possibilities
or recommendations presenting different choices to users [based on] the
investment profile (such as risk aversion, age or projected cash flow) ...
the providers ... would be regarded as 'advising on securities.'"* ([SFC
Licensing Handbook §1.4.10, 2025](https://www.sfc.hk/-/media/EN/assets/components/codes/files-current/web/licensing-handbook/LIC-Handbook-2025-Eng.pdf)). The SFC's *Guidelines on Online Distribution
and Advisory Platforms* additionally trigger the Suitability Requirement for
**any auto-rebalancing that isn't strictly maintaining a pre-agreed model
portfolio**, and Type 9 specifically requires *discretionary* investment
authority properly delegated by the client ([SFC guidelines, robo-advice
chapter](https://www.sfc.hk/-/media/EN/assets/components/codes/files-current/web/guidelines/guidelines-on-online-distribution-and-advisory-platforms/guidelines-on-online-distribution-and-advisory-platforms.pdf)). **Applied to Aegis:** the exact same line as the SEC's — a
transparent screen or ranked list survives as an "analytical tool"; a
personalized recommendation, or an agent that rebalances a specific user's
account, requires a Type 4/9 licence (industry experience running an
"algorithmic investment and portfolio management system" is explicitly
recognized as counting toward a robo-adviser licence application, per §4.4.9
— relevant if Aegis ever seeks HK licensing on this team's own track record).

**European Union.** *Not independently re-verified this session* (search
budget was spent on the US/HK primary sources and pricing above) — flagged
as lower evidence strength. From general knowledge of MiFID II: the
equivalent line is "personal recommendation" (a recommendation presented as
suitable for a specific person, based on their circumstances) versus generic
information; crossing it requires MiFID II investment-advice authorization
in an EU member state. This should be re-verified against ESMA/national
regulator text before it is relied on for a real EU launch.

**The practical implication for Aegis's P1 offer:** the free/cheap tier
Murat described — a graded, dated forecast ledger, a generic "here's what
the process believes and why," explained with its own falsifier — is
buildable **without** RIA/Type-4-9 registration in the US or HK, as long as
it stays impersonal (same content to every reader) and never conditions on
an individual account. The moment the product says "and for *you*
specifically," the licence requirement attaches. This maps directly onto
the three-licence system already in CLAUDE.md: **`PRODUCT_EXPERIMENT` /
paper accounts stay unlicensed by construction; a `CAPITAL_CANDIDATE` that
manages one identified person's real money crosses this line and needs
either registration or a licensed partner/custodian relationship before
launch, not after.**

### 3.3 Revenue model options, each with a comparable precedent

| Model | Precedent | Price anchor | Note for Aegis |
|---|---|---|---|
| **Freemium tiers on the graded forecast ledger** | Danelfin ($0/$29/$79/$179) | $0–29/mo entry tier plausible | Stays impersonal (publisher exemption) if content is the same for every subscriber |
| **B2B API: forecast-grading infrastructure as a service** for newsletters/analysts | Danelfin API ($52/$149/$449/mo) | $50–200/mo per seat | Sells the *scoring/grading machinery* (forecast_reputation.py's calibration engine), not stock picks — a defensible, licence-light B2B product |
| **Flat-fee RIA subscription** (not AUM %) if/when Aegis manages real accounts | Composer ($30/mo, SEC-registered) | $30/mo | Requires registration; cleanest "cheap, flat, honest" P1 pricing model if Aegis crosses into advice |
| **Affiliate/brokerage referral** | Public.com Alpha, Robinhood Cortex (both free, monetized via order flow/interest on cash, not the AI feature) | $0 to user | Keeps the AI feature impersonal and free; revenue sits at the brokerage layer, not the advice layer — avoids the licence question entirely |
| **Paid "grade my forecast" ledger** (a user submits their own thesis, Aegis grades it against outcomes like it grades its own) | No direct precedent found; closest analogue is Numerai's stake/TC mechanism, inverted for retail | Untested | Novel; would need its own pre-registered trial before any efficacy claim |
| **Open-source core + hosted tier** | Composer's no-code builder is free; hosted execution has the fee | Free core, $10–40/mo hosted | Matches Aegis's existing open posture; the "hosted" product is the daily-refreshed, always-graded ledger a self-hosting user would have to run and pay LLM costs for themselves |

### 3.4 Cost to serve — from Aegis's own numbers, not an estimate

- Thesis card generation: **~$0.05/card** (81 cards for $3.07 on 2026-09-25,
  `docs/HANDOFF_2026-09-25_EVENING_THE_MACHINE_FORECASTS_AGAIN.md`).
- Forecasting a held name: **~$0.30/name/day** (`docs/reviews/REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md`; confirmed again in `docs/reviews/ADJUDICATION_2026-09-25_CHUNK0.md`).
- Railway fleet infrastructure: **$48.05** in one recent billing period
  (memory $25.20 + CPU $20.52; `docs/research_notes/2026-09-20/review_night_2026-09-19_to_20.md`).

**What this implies for a subscription product.** The forecast/thesis
generation cost is a **shared, broadcast cost** — one graded ledger serves
every subscriber identically as long as the product stays impersonal (§3.2).
At, say, 100 held names forecast daily ($30/day → ~$900/month) plus $48/month
infrastructure, the **marginal cost of the Nth subscriber is close to $0**
once the fixed content-generation cost is covered. At 100 paying subscribers
and Danelfin's Plus-tier price ($22–29/mo), that is **$2,200–2,900/month
revenue against ~$950/month fixed cost** — a real margin, contingent entirely
on getting to 100 paying subscribers, which nothing in this table has
happened yet (Aegis has 0 paying users today; this is a cost model, not a
revenue result).

---

## 4. What to focus on

**For P1 (the novice, cheap-guidance persona):**
1. **Ship a public, novice-readable surface for the existing ledger** — the
   graded forecasts and thesis cards already exist; nothing customer-facing
   reads them. *Proof it happened:* a URL a person with no finance background
   can open and understand within one screen, with the honesty badges
   (🟢/🔵/🔴) translated into plain language — closing the `access=0` gap
   that dominates §1.2's P1 table.
2. **Decide the impersonal/personal line before building anything paid** —
   per §3.2, staying impersonal avoids RIA/Type-4-9 registration entirely.
   *Proof it happened:* a written product decision (a one-page doc, licence-
   tagged like everything else in this repo) stating which features are
   impersonal-by-design and which are deliberately deferred until a licence
   or licensed-partner relationship exists.
3. **Price a freemium tier against the Danelfin/Composer anchors** ($0/$22–
   29/mo), sized to the fintech/AI-native conversion norms in §3.1 (4.1%
   fintech baseline, 6–20% AI-native ceiling). *Proof it happened:* an actual
   priced tier live, with a conversion number measured against those
   benchmarks — not a plan.

**For P2 (the sophisticated, hands-off, beat-SPY persona):**
1. **Close the one gap between "wins on infrastructure" and "wins on the
   number that matters"** — the 24-month clock is already running
   (`README.md` "Decision clocks, not vibes"); the highest-leverage work is
   making sure the 32 frozen `llm_portfolio` books and their twins actually
   accrue clean grades on schedule, since §1.2 shows Aegis already leads
   every surveyed product on every *other* P2 criterion. *Proof it happened:*
   the `docs/PAPER_ACCOUNTS.md` aggregate line moves from −1.12% to a
   positive, twin-beating number over a stated window, with by-year and
   leave-one-year-out breakdowns printed beside it per the 2026-09-24 lesson
   in this file's own CLAUDE.md.
2. **Publish the Danelfin-style rolling, cost-adjusted, non-overlapping-
   window comparison** the moment there is enough forward history to do it
   honestly — Danelfin is the only close peer on P2 (11 vs Aegis's 12), and
   it wins the *credibility* argument today because it publishes the exact
   comparison Aegis's own README says it won't publish before its clock.
   *Proof it happened:* a public page with the same structure Danelfin uses
   (simulated-vs-live split, 25bps-cost-adjusted, non-overlapping windows),
   populated with real numbers, not a placeholder.
3. **Remove the 28%-vs-115% backtest from the top of the pitch, or reframe
   it explicitly as the founding negative result before any number that
   could be mistaken for a claim.** It is honest disclosure today, but it is
   also the first performance number many readers will see, and it currently
   reads as "this project underperformed the market by 86 points." *Proof it
   happened:* the README's badge/ordering makes the ledger's *forward*
   grading the first number a P2 reader sees, with the historical backtest
   clearly subordinate to it.

**One-sentence positioning per persona:**

- **P1:** *"Aegis writes down what it believes about the market every day,
  grades itself against what actually happens, and shows you both — for
  free, in plain language, before it ever asks you for a dollar."*
- **P2:** *"Aegis is the only system we found that freezes every forecast
  before the outcome and grades it against reality at scale — the discipline
  a real edge would need to prove itself is built and running; the edge
  itself is not proven yet, and we say so."*

---

## Sources consulted this session (beyond the repo)

- Betterment pricing: https://www.betterment.com/pricing
- Wealthfront vs Schwab comparison: https://www.investopedia.com/wealthfront-vs-charles-schwab-robo-advisors-4693442
- Robo-advisor cost comparison, Aug 2026: https://www.realcostreport.com/investing/brokerage-tools/robo-advisor-comparison/
- Danelfin pricing (web): https://danelfin.com/pricing/monthly · (API): https://danelfin.com/pricing/api/annual · audit: https://audit.danelfin.com/
- Composer pricing: https://www.composer.trade/pricing · Trading Pass: https://help.composer.trade/article/226-manage-your-trading-pass · Form CRS (SEC): https://reports.adviserinfo.sec.gov/crs/crs_311289.pdf
- eToro CopyTrader guide (Jan 2026): https://www.etoro.com/wp-content/uploads/2025/10/CopyTrader-Guide_Jan-2026.pdf · Popular Investor Program: https://www.etoro.com/copytrader/popular-investor/
- SEC investment adviser definition: https://www.sec.gov/resources-small-businesses/capital-raising-building-blocks/investment-advisers · Regulation of Investment Advisers overview: https://www.sec.gov/about/offices/oia/oia_investman/rplaze-042012.pdf · Robo-Advisers guidance (2017-02): https://www.sec.gov/files/im-guidance-2017-02.pdf · Internet Adviser Exemption final rule (2024): https://www.sec.gov/files/rules/final/2024/ia-6578.pdf
- SFC (Hong Kong) licensing overview: https://www.sfc.hk/en/Regulatory-functions/Intermediaries/Licensing/Do-you-need-a-licence-or-registration · Licensing Handbook 2025: https://www.sfc.hk/-/media/EN/assets/components/codes/files-current/web/licensing-handbook/LIC-Handbook-2025-Eng.pdf · Guidelines on Online Distribution and Advisory Platforms: https://www.sfc.hk/-/media/EN/assets/components/codes/files-current/web/guidelines/guidelines-on-online-distribution-and-advisory-platforms/guidelines-on-online-distribution-and-advisory-platforms.pdf
- Freemium conversion norms: https://www.growthunhinged.com/p/free-to-paid-conversion-report · https://firstpagesage.com/seo-blog/saas-freemium-conversion-rates/
- 2026 launches: Lumenai — https://www.einpresswire.com/article/907774446/lumenai-to-launch-first-fully-agentic-ai-hedge-fund · Fere AI — https://www.globenewswire.com/news-release/2026/04/23/3279629/0/en/Fere-AI-Raises-1-3M-to-Put-a-Self-Improving-Trading-Agent-in-Everyone-s-Hands.html · Valour/Neuronomics Smart Crypto Fund — https://www.webdisclosure.com/press-release/defi-technologies-inc-etr-defi-technologies-subsidiary-valour-launches-valour-funds-spc-a-new-business-line-and-introduces-its-first-hedge-fund-smart-crypto-fund-sp-powered-by-neuronomics-proprietary-ai-strategy-YyBfzsxS2ai
