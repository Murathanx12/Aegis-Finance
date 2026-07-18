# The Investor Brain Plan (2026-07-18)

Murat's vision, made precise: not a trading algorithm — an engine that
thinks like a good long-term investor. His three claimed edges, from his own
history: (1) follow the big firms' conviction (strong buys, price targets,
FDA catalysts), (2) thematic supply-chain investing — buy what SUPPLIES the
coming demand (NVDA at $20, Micron/Marvell pre-AI-hype, EV/battery 2015,
quantum/nuclear/recycling next), (3) event awareness — FDA dates, product
launches, geopolitics. Plus: an NN brain, LLM news analysis, and — the hard
constraint — **he cannot wait 2 years for the first validation readout.**

## 1. The core unlock: the 24-month clock only gates SKILL CLAIMS

The time problem dissolves once the three validation speeds are separated:

| Speed | Instrument | Reads out | What it answers |
|---|---|---|---|
| **Days** | Direction-check backtests on the survivorship-free panel (deflation-gated, pre-registered, one run) | now | "Is this thesis historically plausible?" |
| **6-12 months** | Forward-IC trials (pit_score_collector — a signal does NOT need a lane or a seed; dozens can run in parallel for free) | first CIs mid-2027; earliest registered decisions 2027-01 | "Does this signal rank future winners on data nobody has seen?" |
| **24 months** | Lane NAV skill claims | 2028-06 | "Can we SAY publicly we have skill?" |

So the plan is an **IC multiplexer**: encode each of Murat's edges as a
scoring signal, register it (cheap), snapshot it forward daily/weekly, and
read ICs in months — while direction-checks on the panel tell us within days
which theses deserve a slot. The 2-year wait applies only to the final
public claim, and the engine learns continuously before that.

On "validation should validate us positively": a validator that can only
say yes is the mechanism behind every corpse in F-022 (GEM, VAA, Alpha
Streams). What CAN be promised: (a) tests designed around the STRONGEST
form of each thesis, (b) readouts every few months, not a 2-year void,
(c) negative results are publishable wins — for the research paper and the
product's credibility, a rigorous "no" beats a fake "yes" in every venue
that matters (HKU, employers, users).

## 2. Edge 1 — "Follow the big firms" (the pro-conviction channel)

**Literature verdict:** consensus LEVELS are nearly worthless; rec CHANGES
(upgrades/initiations) carry short-horizon information; price targets are
systematically ~15% over-optimistic. Murat's own screen produced NVDA and
also APLT (strong buy, +123% target → $0.09): high variance, not an edge —
unless the informative components are isolated.

**Already running (forward):** TRIAL-FORECAST-LEDGER #11 (our MC vs street
targets, matures 2027-07), revisions momentum inside multifactor, insider
(T9), congress (#7), ARK (#8) — five pro/insider-conviction channels accruing.
**Add (direction-check):** upgrade-event study on the panel IF a
point-in-time recommendations source passes a PIT audit (yfinance rec
history is not reliably PIT — audit before trusting; else forward-only).
**Add (forward-IC):** rec-CHANGE score (net upgrades 30d) as a registered
signal — mostly already captured by T10 revisions; extend, don't duplicate.

## 3. Edge 2 — Thematic supply-chain ("picks & shovels") — the crown thesis

This is Murat's most distinctive claim and it has a real, under-studied
testable core. The naive version is hindsight ("NVDA was obvious" — in 2015
solar, 3D printing, and fuel cells were equally obvious and died). The
honest test design kills the hindsight:

**PIT theme baskets via thematic-ETF holdings at their launch dates.**
A thematic ETF's launch filings are a tamper-proof record of what the
market believed the theme WAS at that moment (TAN solar '08, LIT lithium
'10, ROBO '13, HACK '14, BOTZ '16, ARKQ, QTUM '18...). No 2026 knowledge
can leak into a 2013 holdings list.
- **Study A (known literature, direction-check):** do theme baskets bought
  at ETF launch beat SPY? Prior: NO — the "birth of a fad" literature
  finds thematic ETFs launch near hype peaks and underperform ~-4%/yr.
- **Study B (the novel one — Murat's actual thesis):** WITHIN each theme,
  did the SUPPLIERS (upstream: components, materials, equipment) beat the
  APPLIERS (downstream: products, services)? Classification done from
  launch-date descriptions only, frozen before any return is computed.
  If Murat's instinct is right, B shows suppliers > appliers even where A
  shows themes < SPY. That would be a genuinely interesting result — and
  it's exactly what his NVDA/Micron/lithium picks claim.
- **Forward:** a theme-supplier basket score as a registered IC signal;
  feeds the existing V3 thematic-momentum workstream and TRIAL-SMARTGROWTH
  (#9, Murat's frozen thesis basket, already accruing).

## 4. Edge 3 — Events and news (the LLM's honest job)

Markets reprice scheduled events in minutes (the Iran-war oil trade was
gone before a human could act) — so the LLM's job is never "react faster";
it is **(a) event extraction** — build the forward calendar (FDA/PDUFA
dates, product launches, deal closes) from news + filings, and **(b)
pre-event forecasts into a scored ledger**: before each event, record a
falsifiable directional/vol expectation; after, score it. This extends the
forecast-ledger pattern (#11) into an **event ledger** — the honest way to
learn whether our news reading has any edge, with readouts per event, not
per decade. LLM stays off every trade path (canon); FinBERT/GDELT/DeepSeek
plumbing already exists.

## 5. The NN brain

Blueprint: Gu-Kelly-Xiu (2020) — the canonical result that ML on
cross-sectional features predicts returns OOS, with NNs best. Honest
expectations: monthly OOS R² ~0.4% — tiny per-name, meaningful in ranked
portfolios, fragile net of costs. Build AFTER the momentum baseline reads
out (the NN must beat the simple signal it contains, else it's expensive
noise): pre-registered architecture class + feature set + purged
walk-forward + DSR, trained on the panel (delisted + active, 2017+),
evaluated as a RANKER (top-decile vs bottom-decile spread + IC), one frozen
protocol. If it shows rank skill → forward-IC trial like every other signal.
WRDS/CRSP via HKU (Murat checks the library) would extend the panel to
decades and make the NN paper-grade.

## 6. Readout calendar (what Murat gets, when)

- **This week:** TRIAL-MOM-BACKTEST verdict (panel gate check 2 → one run);
  trend-as-insurance quantification; mandate replay already done (matches
  pre-commitment); QC third-party URLs (Murat's runs).
- **~1 month:** suppliers-vs-appliers study (needs PIT basket construction
  — careful work); event-ledger v1 running; Chen-Zimmermann shortlist
  registered as forward-IC trials.
- **6-12 months:** first IC confidence intervals on ALL registered signals
  (congress, ARK, insider, revisions, multifactor, smartgrowth, momentum,
  theme-suppliers...); forecast-ledger maturity begins 2027-07.
- **24 months (2028-06):** the first public skill claims — by then backed
  by dozens of honest intermediate readouts, whichever way they went.

## 7. Hard rules (unchanged, they are why this will be believed)
Pre-register before data; one run per hypothesis; DSR/PBO against the
cumulative count (now 13); parameter-cloud robustness on any backtest
headline; direction-checks never enter paper_nav; LLM never on a trade
path; negative results published. New forward-IC registrations are cheap
but each still gets the attended pre-register flow — Murat has endorsed
expanding hypothesis testing (2026-07-18); lanes/seeds remain his flag.
