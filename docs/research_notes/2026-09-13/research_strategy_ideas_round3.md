# Round 3 strategy ideas — 2026-09-13

Context: Murat, verbatim, 2026-09-13 — *"aegis has spent 1000usd at this moment
on infrastructure. if we dont make a profitable business we will have to shut
down... do anything you can to find profit making strategies, combination of
strategies etc. test them. linkedin theory, business pivot to ai, motivation,
holders, the business, the future anything."* Checked against
`research_registry.md` before writing anything below — every idea here is
either genuinely new or explicitly flagged as an extension/combination of an
already-adjudicated piece, never a re-proposal of a closed family.

Data available (per `research_next_books_published_rulers.md` and
`DATA_MANIFEST.md`): CRSP daily/monthly 1926-2024, IBES summary+actuals
1990-2024, JKP 340-col panel 1926-2024, short interest (WRDS, 1973-2026),
Form-4 insider (11.5M rows, 2006-2026), EDGAR full-text (2001+), a 2025-26 news
corpus (17 sources), Alpaca minute bars 2025-26, options via OptionMetrics
(historical, closed per §27) and Alpaca paper (live).

## Scoring key
`Score = P(changes the roadmap) × value of the decision improved − cost`,
qualitative High/Med/Low. Data availability: **HAVE** (already on disk) /
**FREE PULL** (a new but costless collector) / **PAID**.

---

## Ranked ideas

### 1. AI-pivot / "AI-washing" language in filings — Murat's Adobe/Autodesk/GoPro thesis, given a mechanism (Score: HIGH)

**Not the same test as the closed one.** `NEGATIVE_RESULTS.md` §24 already
scanned generic YoY 10-K text change (`text_jac`/`text_cos`, Jaccard/cosine
whole-document similarity) — high IC (t 7.47) but net-dead (t 0.87, turnover
0.096-0.103). That is a **different construction**: whole-document drift, not
AI-specific language. The literature that has emerged since is content-typed,
not similarity-typed: Boyuan Li, *AI Washing* (Univ. Florida, 2025) finds the
market responds differently to AI "talk" (speculative disclosure) vs AI "walk"
(measured against workforce/patent investment) — talk-driven enthusiasm
reverses over 1-2 years, walk sustains; a related 2026 study (*Journal of
Behavioral and Experimental Finance*) finds AI-washing **elevates stock-price
crash risk** via inflated optimism and information asymmetry. Buildable from
EDGAR full-text search (10-K/10-Q, "artificial intelligence"/"AI" mention
density and its year-over-year change) joined to CRSP/JKP for a talk-minus-walk
divergence score (mention growth vs R&D/capex growth or hiring — link to idea
#2 below). **Twin**: same-sector names with no AI-mention change. **Falsifiers**:
(i) the effect should be a SHORT (talk without walk), not a long — test both
signs separately, since our house prior (LLM/agent alpha family, §19; option
O/S ratio, §27) is that naive "more of X talk" signals invert; (ii) orthogonalize
against `text_jac`/`text_cos` (already-measured, near-dead) to confirm this is
NOT the same effect relabeled. **Ruler**: no raw monthly-spread number published
yet (both papers are 2025-26, event-study/crash-risk shaped, not portfolio
back-tests) — flag as **not found**, register as `PRODUCT_EXPERIMENT`, no
significance gate needed. Cost: LOW (EDGAR full-text search is free; the text
pipeline for `text_jac` already exists to fork from).

### 2. Executive option-grant opportunistic timing (Score: HIGH — the only credible attack on "management motivation," a theme with zero prior research here)

The registry confirms **no research exists** on compensation/option-grant
timing. Literature: Daines et al. (scheduled grants eliminate backdating but
create an incentive to depress the stock price on the known grant date — "may
be worse than backdating" because it distorts real decisions, not just pay);
a 2015 *J. Corporate Finance* study finds 80% of CEO option grants are timed
on/before stock-split announcements, worth an average $451,748/grant at the
3.1% average announcement pop. **Buildable from data we already have**:
Form-4 transaction code `A` (Award/grant) — currently EXCLUDED by design from
both `TRIAL-INSIDER-IC` (code `P` only) and `TRIAL-CMP-INSIDER-IC` (same), so
this is genuinely unexplored territory, not a re-cut of either trial. Construct:
for each grant-code-`A` filing, measure the pre-grant 20-day return (is the
grant timed at a local trough?) and the post-grant 20-day return (does the
stock subsequently outperform, consistent with either favorable-information
timing or price depression around the date); cross-sectionally rank firms by
grant-timing "skill" (persistent negative pre-grant CAR + positive post-grant
CAR) as a governance-quality proxy, long the well-governed / short or avoid the
opportunistic. **Twin**: random-date placebo (CLAUDE.md's own "verified before
believed" habit, per §29-31's lesson that a placebo on the SAME cohort is the
only trustworthy control). **Falsifiers**: (i) the routine-vs-opportunistic
CMP classifier (already built for the buy-side trial) applied to grants — if
"routine" scheduled-grant firms show the same pattern as "opportunistic" ones,
this is calendar noise, not governance; (ii) size/liquidity control, since
option grants cluster in larger, more liquid firms than open-market buys.
**Ruler**: no aggregate monthly-spread number found in the fetched sources
(the papers are event-study CARs around a grant date, not portfolio
backtests) — flag **not found**; use the $451,748/grant-average figure only as
a sanity check on economic magnitude, not a return target. Cost: LOW (Form-4
data on disk; the CMP classifier code already exists).

### 3. Hiring-rate factor, universe-wide (extends TRIAL-HIRING-PIVOT-1, does not duplicate it) (Score: MED-HIGH)

TRIAL-HIRING-PIVOT-1 (pre-registered, `ROADMAP...11c` N-G, unread) is scoped to
**named instances** (ADBE, ADSK, GPRO) testing the pivot-to-AI hypothesis
specifically. The published literature is broader and stronger as a
**general** cross-sectional factor, not just a pivot detector: Kothari &
O'Doherty (2023, *J. Financial Markets*) — postings/employment ratio predicts
the equity premium, 1sd → +6.60%/mo annualised excess; Kuehn, Simutin & Wang
(2017, *J. Finance* 72(5)) — labor-market-tightness loadings, 6%/yr decile
spread, t≈3.66; Belo, Lin & Bazdresch (2014, *JPE*) — hiring rate as a
cross-sectional predictor. All three are peer-reviewed, pre-2020 samples (no
2020+ replication found — flag **not found**, apply the standard McLean-Pontiff
~50% haircut as a working prior). Once the Greenhouse/Lever/Ashby collector
(already spec'd for N-G) exists, the SAME collector gives a universe-wide
hiring-rate-change feature at near-zero marginal cost — a genuinely different
error type from momentum/quality/overhang (it is a **labor-input** signal, not
price- or estimate-derived). **Twin**: random-universe at the same coverage
floor (ATS-page existence itself correlates with company size/sophistication,
so the twin must be drawn from ATS-covered names only, not the full universe —
a coverage-selection falsifier). **Falsifiers**: (i) size/momentum
orthogonalization (hiring firms may just be momentum winners); (ii) the
sector-neutral cut (tech hiring correlates with tech-sector beta). **Ruler**:
Kuehn et al.'s 6%/yr decile spread (0.5%/mo order of magnitude) is the
citable number. Cost: MED (waits on N-G's collector; the incremental ask is
"don't restrict the parser to three tickers").

### 4. Buyback-vs-insider-selling divergence (Score: MED)

Combines two data sources already on disk (Compustat `prstkc`/repurchase
data + Form-4 code `S` sales) into a single divergence signal: firms
repurchasing shares WHILE insiders sell heavily (bearish — management may be
supporting the stock price against their own private information) vs firms
repurchasing WHILE insiders also hold/buy (bullish confirmation). A 2025 study
(3.7M insider transactions, 34 countries) finds **composite** buy/sell insider
measures outperform any single-signal cut, ≥1%/mo equal-weighted alpha; a
separate finding notes buyback-signal quality improves when insider ownership
is LOW (i.e., the divergence framing, not the buyback alone, carries the
information). **This is explicitly NOT the same test as `TRIAL-INSIDER-IC`/
`TRIAL-CMP-INSIDER-IC`**, which use only open-market buys (code `P`) and
deliberately exclude sales as "noisy." The divergence construction uses sales
+ buybacks together as a corporate-vs-insider consistency check, a different
mechanism (agency-conflict signal, not a conviction signal). **Twin**:
buyback-announcing firms with no unusual insider activity. **Falsifiers**: (i)
large-sale-only vs small-sale-only split (per the FAJ 2004 finding that only
large %-of-holdings sales carry negative information — small sales are
noise/diversification and should NOT be counted); (ii) 10b5-1 plan flag
exclusion (pre-scheduled sales carry no signal by construction — SEC data
distinguishes this). **Ruler**: ≥1%/mo composite alpha (2025 cross-country
study) as the ceiling prior, haircut to ~0.5%/mo working expectation given our
narrower single-market/costed construction. Cost: MED (needs a buyback-flag
join to Compustat, not yet built for this purpose).

### 5. Multi-sleeve combination of the programme's OWN survivors: TSMOM overlay + disposition-overhang conditioner (Book C) + insider-N1 premise (Score: MED-HIGH — directly answers Murat's "combination of strategies")

Not literature-sourced — an internal combination, exactly what the roadmap's
"different errors, not more weights" rule (`CLAUDE.md` bottleneck section) asks
for once several independently-surviving pieces exist. Three candidates in the
registry have each cleared SOME bar without dying:
(a) **INSTR-TSMOM-XA** — the only macro instrument to survive the explore/confirm
wall (2020 +9.2%, 2022 flat, overlay maxDD −18.8% vs SPY −33.7%); mechanism =
trend-following on macro futures/rates, a monthly-or-slower crisis-timing signal.
(b) **Book C, disposition-overhang conditioner** — CONDITIONAL, +0.24%/mo t 1.38
at the registered construction; mechanism = cross-sectional earnings-reaction +
behavioral overhang, 3-month hold.
(c) **Insider N1 premise** (§46) — post-disclosure insider-buy return
detectable at 0-1 day lag (+2.30%/+1.80%); mechanism = point-event, idiosyncratic,
davs-scale.
These three are mechanically about as orthogonal as this programme has
produced: macro-trend vs cross-sectional-behavioral vs idiosyncratic-event, at
three different horizons (monthly-plus, 3-month, days). **Published evidence
that combination beats any single sleeve** (not our own construction, general
literature): a two-independent-smart-beta combination (momentum long-short +
min-vol) achieved Sharpe 0.96 vs components' 0.61/0.90 individually (practitioner
source, not peer-reviewed — flag as **weaker evidence**, not a academic
citation). **Construction**: risk-parity-weighted sleeve allocation (not equal
notional — the three have very different vol), each sleeve keeping its own
frozen contract and control twin, combined book graded against a THIRD twin
(equal-risk-weighted RANDOM sleeve selection from the same candidate pool) so
the combination itself is falsifiable, not just assumed additive. **Falsifier**:
pairwise realized correlation of the three sleeves' monthly excess returns —
if any pair exceeds ~0.3, the "different errors" premise itself needs
re-examination before combining. **Ruler**: none published (this is a
within-house combination question) — the twin IS the ruler. Cost: LOW (uses
only pieces that already exist or are already spec'd; the insider sleeve needs
Book B's FAILED cluster-length construction REPLACED with the simpler,
survived N1 buy-day construction — a new, narrower book, not a resurrection of
Book B).

---

## Additional ideas scored, not in the top five

### 6. IPO lockup-expiration short-selling predictability (Score: LOW-MED)
Genuine, cited, recent evidence: short-seller activity around lockup expiry is
predictive of the post-expiry price decline (overvaluation-driven, not just a
selling-constraint story). **Data gap**: we do not have an IPO lockup calendar
on disk; building one requires parsing S-1/424B4 prospectuses for lockup terms
(FREE PULL from EDGAR, but nontrivial NLP/regex work — no existing collector).
Score held down by build cost relative to the other four, not by weak evidence.

### 7. Index reconstitution effect (S&P 500 adds/deletes) (Score: LOW — confirmed decayed, do not build)
Greenwood & Sammon, "The Disappearing Index Effect" (NBER w30748): the add
effect fell from 3.4% (1980s) / 7.6% (1990s) to **0.8%** in the 2010s; the
delete effect fell to **−0.6%**. This is the rare case where the literature
itself answers "is this worth building" — no. Listed so nobody re-discovers it
by web search and proposes it fresh.

### 8. Option-expiry pinning (Score: LOW — old evidence, no 2015+ replication found, and already flagged in `research_daytrading.md` as "hypothesis generator, not standalone")
The foundational number (16.5bp average distortion, ~$9B aggregate) is from a
2004 study; search for 2015-2020 confirmation found only a weekly-options
extension paper confirming the phenomenon persists, not a post-2015 tradable
spread. **Does not meet criterion (a)** (published OOS evidence after 2015) —
listed as a gap, not a candidate.

---

## Themes with NO credible published evidence — test as `PRODUCT_EXPERIMENT` only, never `RESEARCH_CLAIM`

- **Retail social media (StockTwits/Reddit/X sentiment)**: Cookson & Niessner —
  StockTwits disagreement has marginal/no incremental predictive power once
  controlled; WSB attention-peak entries realize **−8.5%** average forward
  return (a fade, not an edge); X's free API is discontinued (pay-per-use since
  Feb 2026) and Reddit now requires pre-approval + ~$12k/mo commercial minimums.
  **No published, costed, post-2015 edge survives this literature search.**
  This is the weakest of Murat's named themes on the evidence; if tested at
  all, it is a cheap `PRODUCT_EXPERIMENT` on whatever free StockTwits access
  remains, not a research direction.
- **Small quant shops / retail systematic funds profitable under $1M AUM**:
  searched directly — **not found**. What the search surfaced instead: typical
  hedge-fund launch AUM is $50-100M (infrastructure cost alone runs into the
  millions), and the standard fee model (2-and-20) assumes an institutional
  scale that a sub-$1M book cannot reach. This is *consistent with*, not
  contradicted by, our own retail-day-trading literature (§44 in the registry:
  1-2% of day traders durably profitable) and our own Lane D arithmetic
  (finding a real 1%/day gross mechanism is "the entire problem," not the
  statistical bar). **Plain reading: no evidence exists that a sub-$1M
  systematic operation is a viable BUSINESS model** — the business case for
  Aegis has to be either (i) a tool sold to many small accounts (aggregating
  AUM across users, not one account), or (ii) graduating specific mechanisms
  to real capital at a scale where infrastructure cost amortizes, not a
  single small account trading many strategies. This is a business-model
  finding, not a strategy one, and belongs in front of Murat plainly: the
  literature gives no comfort that "one person, under $1M, systematic" is a
  solved problem anywhere.
- **Option-expiry pinning, index reconstitution**: see #7-8 above — evidence
  exists but is stale or already decayed to sub-tradeable size.

## What would change the roadmap

The single highest-leverage new fact this pass: **"management motivation/
incentives" and "business pivot to AI" are not merely unbuilt — they are
UNRESEARCHED in this repo**, unlike almost every other theme Murat named
(hiring has a pre-registered trial; holders have three closed families;
day-trading has a full literature review). Ideas #1 and #2 above close that
gap with constructions that reuse data and code already paid for (Form-4,
EDGAR text pipeline, the CMP classifier) rather than requiring a new pull.
Idea #5 is the direct, cheap answer to "combination of strategies" using only
pieces that have already individually survived a corpse-check — no new
literature risk, only an internal falsifier (sleeve correlation) to run.
