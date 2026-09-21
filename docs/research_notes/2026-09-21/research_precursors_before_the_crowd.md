# Precursors before the crowd — MU and NVDA, what was observable and what we hold

Sonnet read owed by roadmap §16.4 item 1 (`docs/ROADMAP_2026-09-11_..._LEARNING_LOOP.md`).
Source of the question: Murat's Part 1, `feedback_murat_review_2026-09-21_morning.md`
("a stock gives signals before growing such as micron nvda etc. but most of
the news and public gets aware of its after its gains value... try to find
workarounds like these"). Governing invariants: mission rule 2 (precursors
observable BEFOREHAND are the research problem, not post-hoc explanation),
`AEGIS_STRATEGIC_INVARIANTS.md` #4 (anchor != expression — the mega-cap is a
sensor, the trade may be its supplier) and #16 (generation is free, promotion
is rationed). Licence: research read, $0, no code, no paid LLM call.

**Brain check (before proposing anything):** `brain_query` for precursor /
attention / coverage / Micron / NVIDIA / STATE_CHANGE_ELASTICITY and
`aegis_postmortems` returned no existing corpse on this exact question. The
closest neighbours: ANALYST-IBES-1 (raw analyst **upside level** is
PERVERSE/CLOSED, `TRIAL-CALIBRATED-TARGET-UPSIDE-1.md` — does not touch
breadth or dispersion); the supply-chain corpse Murat's review names by name
("customer-return propagation into suppliers, unconditional, monthly
rebalance" is closed; "event-revealed shortage → supplier map → low-attention
beneficiary" is explicitly **not** the same mechanism, §16.2b); and the
GPRO/holder-attention case (`CASE_2026-09-02_GPRO_HOLDER_ATTENTION.md`, a 13G
"plausibly contributed nothing to the fundamental outcome" — a matched-loser
precedent for telling attention from cause). Nothing here re-proposes a corpse.

## 1. MU and NVDA's last three large moves (dated, cited)

| ticker | date | move | trigger |
|---|---|---:|---|
| MU | 2024-12-19 | **−16%** (worst day since Mar 2020) | FQ2 FY25 guidance far below consensus ($7.9B±0.2B vs $8.96B est.) despite an 84.3% YoY revenue beat the day before ([CNBC](https://www.cnbc.com/2024/12/19/micron-headed-for-worst-day-since-2020-after-disappointing-guidance.html), [Fool](https://www.fool.com/investing/2024/12/19/why-micron-stock-crashed-16-today/)) |
| MU | 2026-03-19/20 | **−7.8%** (two-day slide) | FQ2 FY26 beat (EPS $12.20, rev $23.86B, HBM > $1B, +50% seq.) overshadowed by gross-margin guidance falling 37.9%→36.5% ([CNBC](https://www.cnbc.com/2026/03/19/micron-falls-blockbuster-earnings-chips-ai.html), [iTiger](https://www.itiger.com/news/1123703401)) |
| MU | 2026-06-24/25 | **+14.6%** | FQ3 FY26 beat (rev $41.46B, +345.7% YoY, EPS $25.11 vs $20.20 est.) ([Investing.com](https://www.investing.com/news/transcripts/earnings-call-transcript-micron-tops-q3-2026-estimates-shares-jump-146-93CH-4759504)) |
| NVDA | 2025-01-27 | **−17%** (largest single-day market-cap loss in history, −$589B) | DeepSeek R1 model release raised doubts about AI-capex intensity ([Forbes](https://www.forbes.com/sites/dereksaul/2025/01/27/biggest-market-loss-in-history-nvidia-stock-sheds-nearly-600-billion-as-deepseek-shakes-ai-darling/), [Yahoo Finance](https://finance.yahoo.com/news/nvidia-stock-plummets-loses-record-589-billion-as-deepseek-prompts-questions-over-ai-spending-135105824.html)) |
| NVDA | 2025-04-16 | **−6.9%** | disclosed new US license requirement on H20 exports to China, $5.5B quarterly charge ([CNBC](https://www.cnbc.com/2025/04/15/nvidia-says-it-will-record-5point5-billion-quarterly-charge-tied-to-h20-processors-exported-to-china.html), [NPR](https://www.npr.org/2025/04/16/nx-s1-5366665/nvidia-china-h20-chips-exports)) |
| NVDA | 2026-08-27 | **+8.74%** (+$442B, 2nd-largest one-day $ gain ever) | Q2 FY27 earnings + FY28 revenue guide ~70% growth vs ~45% expected ([Yahoo Finance](https://finance.yahoo.com/markets/stocks/articles/nvidia-adds-442-billion-second-202830771.html)) |

**Note on kind, not just size:** three of these six (MU 12-19, NVDA 1-27,
NVDA 4-16) are same-day **information shocks** — a number or a policy
disclosed that morning — not a slow crowd-catches-up move. A precursor
"observable 1–6 months before" cannot exist for the *content* of a shock
that had not happened yet; what *can* exist beforehand is exposure — who
was positioned for the shock to matter (§2, per name). The other three
(MU 3-19, MU 6-24, NVDA 8-27) are earnings prints where the fundamentals
had been building for a quarter, and the question is whether that quarter's
data flagged the surprise's direction before the print. Conflating both
kinds into one "precursor" search overstates what is knowable for the
shock-type moves.

## 2. Precursor candidates — observable, held, matched loser, first test

For each: was it observable in the relevant pre-window (dated where
possible), do we hold the collector (file:path), a candidate matched loser
(same precursor value, no comparable move — **illustrative, not tested**),
and the first $0 test with its foreign slice.

**Analyst revision breadth / dispersion.** Not observable retroactively in
this repo: `analyst_ledger.py` is append-only and **started 2026-09-13**
(`backend/data/analyst_snapshots.jsonl`) — "if the ledger has not seen this
ticker twice, the delta fields come back `None`" by its own contract, so
there is no 2024-2026 history to query. Real PIT IBES 2010-2024 exists in
the sibling Aegis module (`ANALYST-IBES-1`, WRDS-licensed) but coverage into
2025-26 is unverified — a lookup, not a $0 build. Held: PARTIAL (forward-only
here). Corpse: raw upside **level** is PERVERSE/CLOSED; breadth/dispersion is
untouched by that verdict (16.2b).
Matched loser: a same-sector name whose estimate dispersion also widened
pre-print but whose print missed (e.g. a memory peer during MU's Dec-2024
guide-down). First test: check IBES coverage extends to 2025-26 in the
Aegis module; if yes, pull dispersion (std of FY1 EPS estimates) in the
60 trading days before each of the six dates for MU/NVDA and one matched
peer; if no, this becomes a forward-only PROBE under `hypothesis_id`
(§16.2, chunk 23a) — zero retroactive read is possible today.

**Coverage change (new initiations).** Not observable retroactively: no
initiations collector exists; Finnhub's free tier "keeps only four months"
(roadmap §2.1), so no window covers any of the six dates. Held: NO. First
test: none possible on these six events; a PROBE row opened now accrues
toward MU/NVDA's *next* move only.

**Options skew / implied volatility / volume.** Provably not recoverable.
`backend/services/options_pit_store.py`'s own docstring: "yfinance option
chains are a **snapshot**. There is no history and no backfill: an implied
move that was not captured before the event is gone permanently." None of
the six dates has a captured pre-event chain. Held: the *store* exists
(built for `EVENT-RESPONSE-2`, IC +0.0315 t 3.19, the programme's one
adequately-powered result) but its data starts whenever it began logging,
after all six dates. First test: **none for these events** — only forward,
comparing `gap_vs_implied` to a matched loser's same-day figure.

**Insider clusters (Form 4, code P).** Observable retroactively, and held.
`insider_form4.py` parses raw SEC Form 4 XML directly off EDGAR — a public,
point-in-time archive back to whenever a filer registered — so a pull for
MU/NVDA executives in the 1–6 month windows before each of the six dates
runs **today at $0**, no waiting. Held: YES (`backend/services/
insider_form4.py`, `insider_trading.py`). Corpse: `insider_opportunistic`
graded WEAK-negative **cross-sectionally** (chunk 22, gross +0.125% <
turnover cost 0.171%) — a portfolio-construction verdict on monthly
rebalance, not a scoped verdict on idiosyncratic pre-mega-move clustering at
one name (16.2b: different construction, different question). Matched
loser: a same-sector peer whose insiders did NOT cluster-buy in the matching
window and did not move. First test: pull Form 4 P-code filings for MU/NVDA
officers/directors in the 126 trading days before
each of the six dates; count clusters (≥2 insiders, 30-day window); compare
cluster incidence against 3 sector peers over the same windows. n=6 events
is underpowered for a verdict but costs nothing and is a legitimate PROBE
row per name/date.

**Hiring (Greenhouse/Lever/Ashby only — LinkedIn banned).** Held as a
collector (`backend/data/optimus/hiring/`, cursor + board map, first run
2026-09-13) but **structurally not observable for past dates**: public ATS
endpoints return *current* open roles only, so nothing was snapshotting
MU/NVDA's boards in 2024-early-2025 — untestable on any of the six dates,
the same gap as the options store's. `TRIAL-HIRING-PIVOT-1` (roadmap N-G)
is already pre-registered for the sector-pivot version (ADBE/ADSK/GPRO) and
would need extension to a memory/GPU hiring-intensity hypothesis. First
test: none for the six past dates; a fresh PROBE opened now on MU/NVDA's
engineering-role share pays off only on their *next* move.

**Supplier / customer read-throughs (earnings-call and filing text).** Not
held: no transcript collector exists anywhere in `backend/services` (grepped
— none). But this is the mechanism Murat's own review names as the
reopening example for the supply-chain corpse: "an earnings event reveals a
GPU shortage → map suppliers → identify low-attention beneficiary" is
explicitly **not** closed by the customer-propagation corpse. It is
buildable at $0: SEC EDGAR full-text search over 8-K/10-Q MD&A (no key,
public) substitutes for a transcript feed. Matched loser: a name in the same
disclosed supply chain (e.g. an HBM-equipment or CoWoS-capacity supplier
named in MU/NVDA's own MD&A) that did **not** re-rate in the 1–6 months
after the disclosure despite the same exposure sentence. First test: pull
MU's and NVDA's 8-K/10-Q text for the two quarters before each earnings-type
move (3 of the 6), grep for supplier/customer names via existing entity
resolution (N-D), then test *those* names' 21/63-session returns in the
window **after** the disclosure but **before** MU/NVDA's own move — this is
the read-through lag Cohen-Frazzini measures (below), and it is the one
candidate that lines up with invariant #4 (the trade is the supplier, not
the sensor).

**Search interest (Google Trends).** Observable retroactively — the one
clean case. `trends_sentiment.py` already cites Da-Engelberg-Gao and computes
an SVI z-score; Google Trends' own API serves historical `interest_over_time`
back years at weekly granularity, so a pull for "Micron stock" / "Nvidia
stock" (and generic "AI chip shortage" / "HBM") covering all six pre-windows
runs today at $0. Held: YES. Matched loser: a peer ticker whose search
interest also spiked in the same window without a comparable subsequent
move (a cheap falsifier — attention without a move is exactly the GPRO
case's shape). First test: SVI z-score (63-day trailing) for MU/NVDA in the
1–6 months before each date vs. the peer's same-window z-score; the Da et al.
result predicts at most a 2-week lead, so the test's real value is showing
whether *this* signal is a 1–6 month precursor at all or only ever a
days-ahead confirmation — a sharp, cheap falsifier either way.

**Social attention slope (StockTwits/Reddit/X-shaped).** Only partially
held. `sentiment_analyzer.py` runs FinBERT over **our own news corpus**,
which per R3 lives in a 21-month window (2025-26) — it does not reach MU's
Dec-2024 event and only marginally reaches NVDA's Jan-2025 one. X is
pay-per-read since Feb 2026 and Reddit bars ML use without permission
(roadmap §7) — both out on licence grounds, not just cost. First test: run
the FinBERT slope only on the two 2026 MU dates that fall inside the corpus
window; the earlier three stay untestable here.

**Short interest.** Not held historically: `short_interest.py` reads
yfinance `.info`, "the latest bi-monthly FINRA snapshot" — current only, no
stored series. FINRA publishes the same bi-monthly settlement files
historically and free back to 2003 — pullable at $0, not built. Matched
loser: a peer with comparably high short-interest/days-to-cover that did not
squeeze. First test: pull FINRA historical files for MU/NVDA and one peer
around the six dates; most informative for the two down-moves (short
interest predicts crash risk, not rally timing — §3).

**13F changes.** Not held: no broad institutional-13F collector exists (only
ARK's daily disclosure and Congressional STOCK-Act trades are collected).
SEC EDGAR 13F-HR is public, point-in-time, pullable at $0, 45-day lag baked
in. Held: NO. Low priority — the lag eats most of the 1-6mo window, and
Cohen-Polk-Silli (roadmap §7) already found managers' "best ideas" don't
overlap enough for copying to be reliable.

**Capex / guidance language.** Not held (same transcript gap as the supplier
read-through above); `earnings_intelligence.py`'s "estimate revision
momentum" reads yfinance's *current* analyst object only, same forward-only
shape as the ledger. First test: once 8-K/10-Q text is pulled for the
supplier test above, the same text answers this — one collector, two
hypotheses, not two builds.

## 3. What the published evidence says, and what it implies for timing

- **Hong & Stein (1999), gradual information diffusion:** information
  travels slowly across heterogeneous, imperfectly-connected traders,
  producing underreaction that later resolves as momentum. Implies a real
  precursor should show up as a *slow-building*, weeks-to-months signal that
  predicts a **later** move, not one coincident with it — the shape §1's
  three earnings-type dates could plausibly have, and the shape the three
  shock-type dates structurally cannot.
- **Cohen & Frazzini (2008), customer-supplier momentum:** linked-firm
  returns don't reflect the linkage promptly; customer returns predict
  supplier returns with up to a **one-month** lag. Directly supports the one
  candidate above (supplier/customer read-through) that Murat's own review
  keeps open by name; implies that test belongs at a monthly, not daily,
  horizon — consistent with the review's "horizon should be learned" point
  and chunk 23d's 126-session finding on `profitability_small`.
- **Da, Engelberg & Gao (2011), "In Search of Attention":** Google SVI
  predicts returns over roughly the following **two weeks**, followed by
  partial reversal. Implies search interest is a days-to-weeks leading
  indicator at best — useful for confirming a move already starting, a
  weaker candidate for a genuine 1–6-month-ahead precursor than the review
  hopes, and this is knowable from the paper alone before running the test.
- **Barber & Odean (2008), attention-grabbing stocks:** retail investors are
  net *buyers* of attention-grabbing stocks, because they can only sell what
  they already own — attention **draws the crowd in**, it does not precede
  it. This is the mechanism behind Murat's own complaint ("most of the news
  and public gets aware of it after its gains value") and argues that
  measured public attention (search, social) is closer to a coincident or
  lagging indicator than a precursor by construction.
- **Hong, Lim & Stein (2000), coverage and momentum:** low-analyst-coverage
  stocks show slower price adjustment and stronger momentum than
  high-coverage ones. MU/NVDA are near-maximal-coverage names — this
  predicts precursors are *least* observable on the mega-cap itself and
  *most* observable on its low-coverage suppliers: `AEGIS_STRATEGIC_
  INVARIANTS.md` #4 (anchor != expression) restated as an empirical claim,
  and the strongest argument for the supplier/customer candidate over any
  signal computed on MU or NVDA directly.

## 4. Ranked table

| precursor | held? | earliest observable lead (these 6 events) | corpse status | first $0 test | P(changes roadmap) |
|---|---|---|---|---|---:|
| Supplier/customer read-through | NO (buildable, EDGAR full-text) | 1–2 quarters (3 earnings-type dates only) | OPEN — explicitly not closed by supply-chain corpse (16.2b, Murat's own example) | pull MU/NVDA MD&A text → named suppliers → their returns before MU/NVDA's move, vs a same-chain non-mover | **HIGH** |
| Insider Form 4 clusters | YES (`insider_form4.py`) | any window, today | insider_opportunistic WEAK-negative cross-sectionally; this construction unscoped by that verdict | Form-4 P-code pull, 126d pre-window, MU/NVDA execs vs 3 sector peers | MEDIUM |
| Search interest (Google Trends) | YES (`trends_sentiment.py`) | multi-year, today | none — never tested at this horizon | 63d SVI z-score pre-window vs a spiked-but-flat peer | MEDIUM (cheap, likely disproves the 1–6mo claim per Da et al.) |
| Analyst revision breadth/dispersion | PARTIAL (forward-only here; maybe in Aegis-module IBES) | 0 in this repo; unknown in sibling repo | level CLOSED, breadth/dispersion OPEN | check IBES coverage into 2025-26; else PROBE forward | MEDIUM |
| Capex/guidance language | NO (buildable, same EDGAR pull as supplier test) | 1–2 quarters | untouched | joint build with supplier-read-through test | MEDIUM |
| Short interest | NO (collector exists, no history; FINRA history is free) | bi-monthly, historical, buildable | untouched | FINRA historical files, MU/NVDA + peer, pre-drop windows only | LOW-MEDIUM |
| Coverage change (initiations) | NO (4-month Finnhub window only) | 0 for these 6 dates | untouched | none retroactive; PROBE forward only | LOW-MEDIUM |
| Hiring (Greenhouse/Lever/Ashby) | Collector exists, structurally NOT retroactive | 0 for these 6 dates | TRIAL-HIRING-PIVOT-1 pre-registered (pivot framing only) | none retroactive; PROBE forward only | LOW |
| 13F changes | NO (buildable, 45d lag baked in) | ≤4.5 months, lag-limited | untouched | EDGAR 13F-HR pull, low priority | LOW |
| Social attention slope | PARTIAL (our corpus, 21mo window; X/Reddit barred by licence) | reaches only 2 of 6 dates | untouched | FinBERT slope on the 2 in-window dates only | LOW |
| Options skew / implied vol | Store exists, data NOT retroactive by the module's own admission | **0 — provably unrecoverable** for all 6 dates | `EVENT-RESPONSE-2` is the programme's one adequately-powered result (IC +0.0315 t 3.19), but post-dates every one of these 6 events | none retroactive; forward only, next move | ZERO (these events) / MEDIUM (forward) |

## 5. Bottom line

Two candidates (search interest, insider clusters) can be tested against
these specific past moves **today**, at $0, with real historical data
already in this repo's own collectors. One more (supplier/customer
read-through) is the highest-value candidate by the literature and by
Murat's own reopening language, but needs a small, cheap EDGAR-text pull
that does not exist yet. Four (options skew, hiring, coverage-change, 13F)
are structurally incapable of answering this question about MU/NVDA's
*past* moves — their data starts after all six dates — so the honest
disposition is a forward-only PROBE row (§16.2), not a retroactive test,
not a REFUSED. A precursor untestable on the past three moves is not the
same as a precursor that is false — rule 39 (a refusal to fund is not a
refusal to learn).
