# Leaks, politicians, insiders, and patents as PIT sources

Compiled 2026-09-26. Method: WebSearch (exhausted its 200-call session budget
almost immediately — every WebSearch call in this note actually ran through
`mcp__exa__web_search_exa` / `mcp__exa__web_fetch_exa` instead, which is why
sources below are exa results, not WebSearch results) + reading
`docs/research_notes/2026-09-25/research_fda_catalysts.md` Part 2,
`docs/research_notes/2026-09-25/research_repos.md` §1,
`docs/research_notes/2026-09-20/audit_congress_collector.md`,
`backend/services/congress_trades.py`,
`backend/services/portfolio_intelligence/congress_collector.py`,
`docs/TRIALS/TRIAL-CONGRESS-IC.md`, `docs/TRIALS/TRIAL-INSIDER-IC.md`, and
`backend/services/event_vocabulary.py` / `scenario_forecasts.py`. **No
OpenClaw/X reads were used** — every claim below was independently confirmed
by at least one mainstream outlet (BBC, Reuters, Fortune, Time, Wikipedia) or
a primary academic/data source, so the 4-read budget was not needed; if a
claim below is later disputed, X search of the named accounts/outlets is the
natural next step, not yet spent.

Evidence-strength key used throughout: **VERIFIED** (fetched primary
document/filing or a named mainstream outlet with on-the-record sourcing),
**REPORTED** (named outlet, sourced to "people familiar" / officials, not a
primary document), **RUMOURED/UNCLEAR** (blogs, unverified social claims, or
this session could not independently confirm).

---

## 1. The two leaks Murat named

### 1a. "Trump's insider trading thing" — NOT one leaked document; a
pattern-of-trading investigation plus his own MANDATORY disclosures

There is no single leaked file here. What actually happened, precisely:

- **VERIFIED** — Trump is legally required (as President) to file a public
  financial disclosure. His 2026 disclosure (filed ~May 2026, a 113-page
  document) revealed **3,400+ individual stock trades in Q1 2026 alone**,
  hundreds of millions of dollars in volume — these are **public documents we
  can lawfully read**, not leaks. Senator Elizabeth Warren cited specific
  trades at a June 2026 Senate Finance Committee hearing: Trump bought up to
  $1M of NVDA on **Jan 6, 2026**; one week later the administration loosened
  export-control rules letting NVDA sell chips to China; he also bought
  Robinhood (HOOD) and BNY Mellon stock before Treasury named both as agents
  for the "Trump accounts" program on **April 6, 2026**
  ([Warren Senate press release](https://www.warren.senate.gov/news/press-releases/at-hearing-secretary-bessent-defends-president-trumps-stock-trades-dodges-warrens-push-for-investigation-on-potential-insider-trading/)).
  Treasury Secretary Bessent did not deny the pattern; he deflected to "an
  outside manager was doing that."
- **VERIFIED** — a BBC investigation (20 Apr 2026,
  [bbc.com/news/articles/cge0grppe3po](https://www.bbc.com/news/articles/cge0grppe3po))
  matched trade-volume spikes in oil futures and S&P 500 E-mini contracts to
  the *minutes* before Trump's market-moving statements on five occasions
  (9 Mar, 23 Mar, 9 Apr 2025 "Liberation Day" pause, 3 Jan 2026 Maduro
  seizure, 28 Feb 2026 Iran strikes), using prediction-market (Polymarket)
  account data and Bloomberg futures-volume data. This is a **pattern
  detected via trade-timing forensics**, not a leaked list — the "leak" is
  the suspected (never confirmed) channel by which non-public information
  about the *timing* of announcements reached specific trading accounts.
- **VERIFIED** — a named individual case exists: Gabriel Perez, Trump's
  teleprompter operator, was **fined $172,000 by the CFTC in August 2026**
  for trading on Kalshi using non-public information about presidential
  speech timing (per Wikipedia's
  [Insider trading allegations during the second Trump administration](https://en.wikipedia.org/wiki/Insider_trading_allegations_during_the_second_Trump_administration),
  cross-checked against contemporaneous news coverage). This is the one
  adjudicated insider-trading case in the whole saga.
- **VERIFIED (current, most relevant to "leak")** — as of **24 Sep 2026**
  (two days before this note), 53 former federal prosecutors filed an amicus
  brief ([Fortune](https://fortune.com/2026/09/24/over-50-federal-prosecutors-trump-100000-month-insider-trading/))
  arguing that Trump Media's **"Truth API"** — a **$100,000/month
  subscription selling trading firms EARLY ACCESS to Trump's Truth Social
  posts before the public sees them** — is "insider trading by definition"
  (quote from an NYU Stern economist). This is the closest thing to an actual
  information-advantage-for-sale mechanism, and it is **paid, disclosed,
  litigated in open court (SDNY)** — a legitimate public record, not a leak.
- **REPORTED/UNCLEAR** — no evidence found of a specific *leaked document*
  (e.g., a memo or trade list) being the source of Murat's phrase. The
  colloquial "leak" almost certainly refers to the broader suspicion that
  *someone* is leaking Trump's pending announcements to anonymous
  prediction-market accounts (Bubblemaps blockchain analysis found clusters of
  freshly-created Polymarket wallets with implausibly high hit rates around
  Iran-war and Maduro events) — this is **reported and analytically
  suggestive, never proven**, and no named leaker has been identified.

**What happened to the named stocks afterward**: oil dropped 14% (9 Mar) and
~10% (23 Mar) within minutes of the statements; the S&P 500 rose 9.5% on the
day of the tariff pause (9 Apr 2025); NVDA, HOOD and BNY all rose after the
respective policy actions Trump had traded ahead of (Warren's letter). These
are **verified market reactions**, but causal attribution to leaked
information (vs. skilled anticipation) remains **unproven** per the BBC's own
framing and a quoted French law professor's view that "no-one will be
prosecuted" absent an identified source. **Usable, PIT-safe artefacts here**:
Trump's own financial disclosure filings (public record, filed on a lag —
this is exactly a politician-disclosure PIT source, see §2) and the CFTC's
public enforcement actions (Perez). Prediction-market wallet activity is
public and machine-readable in real time (see `research_fda_catalysts.md`
Part 2 §5 on Polymarket's Gamma API) but attributing any specific wallet to
"a leak" is not something Aegis can or should claim — it can only score
*co-movement between anonymous wallet activity and subsequent official
announcements*, which is a different, weaker, and still-interesting signal.

Sources: [BBC](https://www.bbc.com/news/articles/cge0grppe3po) ·
[Yahoo Finance recap](https://finance.yahoo.com/markets/options/articles/luck-skill-leak-bbc-probes-061917475.html)
· [Time](https://time.com/article/2026/04/10/white-house-oil-prediction-markets-polymarket-bets-insider-trading-war/)
· [Fortune, 2026-09-24](https://fortune.com/2026/09/24/over-50-federal-prosecutors-trump-100000-month-insider-trading/)
· [Wikipedia](https://en.wikipedia.org/wiki/Insider_trading_allegations_during_the_second_Trump_administration)
· [Warren Senate hearing](https://www.warren.senate.gov/news/press-releases/at-hearing-secretary-bessent-defends-president-trumps-stock-trades-dodges-warrens-push-for-investigation-on-potential-insider-trading/).

### 1b. "The Goldman Sachs list leak" — most likely the (routinely
published, NOT leaked) US Conviction List / hedge-fund VIP list; no distinct
2025-26 leak scandal matching a stock-picks document was found

This one did **not** resolve to a single incident the way the Trump item did.
Two candidate referents, both checked, neither is a "leak" in the
document-theft sense:

- **Goldman Sachs US Conviction List ("Directors' Cut")** — a real,
  **officially published monthly research product** (23 Buy-rated names as of
  Sept 2026: added Vertex Pharmaceuticals, removed Interactive Brokers; median
  27% upside to 12-month targets). It is covered, near-verbatim, by financial
  media every month (Finvaulta, 24/7 Wall St, Insider Monkey, Bitget, RoicAI —
  all **VERIFIED**, all citing the same GS research note). This is
  **published to clients on purpose, then re-reported by press** — colloquially
  people call sell-side research that leaks to journalists before/around
  official client distribution a "leak," but there is no confirmed breach here;
  it is closer to normal financial journalism. If this is what Murat means,
  **the actionable artefact is the Conviction List itself, published monthly,
  and machine-readable via press aggregation** — not through any stolen
  document.
- **The Fried Frank data breach (Oct 2025, disclosed Dec 2025-Feb 2026)** — a
  **VERIFIED, real leak**: 46,602 individuals' PII (SSNs, passport data,
  financial account info) belonging to Goldman Sachs AND JPMorgan private
  equity / alternative-fund investors was exposed when Goldman's outside law
  firm, Fried Frank, was breached. This is a genuine leak with class-action
  litigation, but it leaked **investor PII, not a stock list or trading
  positions** — not useful as a market signal.
- **NOT FOUND**: no report matching "Goldman Sachs leaked its list of
  [stocks/shorts/clients] and the stocks then moved" for 2025-2026. The
  closest historical analogue Murat may be recalling is the well-known
  **"Goldman Sachs Hedge Fund Trend Monitor" / "Hedge Fund VIP list"** — a
  legitimate quarterly GS report of the stocks most commonly held by hedge
  funds' top-10 positions, which the financial press covers as if leaked
  because it is meant for institutional clients first. That report was not
  independently re-verified in this session (not found in the search results
  above) and should be treated as **RUMOURED/UNCLEAR** as the referent until
  Murat confirms.

**Recommendation**: ask Murat for the specific outlet/date he saw the
"Goldman list leak" story in, or treat the Conviction List as the working
referent — it is legitimately usable (public, dated, machine-scrapable from
press aggregators) regardless of whether "leak" is the right word for it.

Sources: [Finvaulta Sept 2026](https://finvaulta.com/research/goldman-sachs/us-conviction-list-directors-cut-september-2026-update-2026-09-01)
· [24/7 Wall St](https://247wallst.com/investing/2026/06/08/goldman-sachs-adds-4-companies-to-u-s-conviction-list-with-huge-double-digit-upside-potential/)
· [Fried Frank breach analysis](https://breached.company/fried-frank-data-breach-exposes-46-000-including-jpmorgan-and-goldman-sachs-private-equity-investors-elite-wall-street-law-firm-becomes-liability-for-big-bank-clients/).

---

## 2. Politicians and insiders as a PIT feature

### The free feeds (per `research_fda_catalysts.md` Part 2 §4, cross-checked)

| Source | What | PIT stamp | Lag |
|---|---|---|---|
| House Clerk PTR bulk ZIP | `disclosures-clerk.house.gov/public_disc/financial-pdfs/{YYYY}FD.zip` | filing date, embedded/reliable | ≤45 days from transaction |
| Senate eFD | `efdsearch.senate.gov` — HTML/POST, no bulk JSON, ToS-gated | filing date | ≤45 days |
| SEC Form 4 (EDGAR) | XML per filing, `data.sec.gov/submissions/...` | acceptance datetime | ≤2 business days |
| SEC 13F | Quarterly ZIPs, `sec.gov/data-research/.../form-13f-data-sets` | accepted-filing date | ~45 days post-quarter |
| FMP `senate-latest`/`house-latest` | what Aegis actually uses (`congress_trades.py`) | `disclosureDate` field | same STOCK Act lag |

The repo's own collector (`backend/services/congress_trades.py`) already
implements the correct discipline: it keys on `disclosureDate`, never
`transactionDate` — "the day the public could know" — and has a fail-loud
contract (raises rather than emitting false-zero scores on a broken feed).

### Repos worth stealing from (per `research_repos.md` §1, not independently
re-verified in this session — carry that repo's own confidence caveat)

- **austin-starks/sec-ownership-disclosures** and
  **austin-starks/congressional-disclosures** — explicitly store "when each
  filing could first have been known" as a first-class PIT column (a design
  Aegis's `congress_trades.py` already has, informally); the companion HF
  dataset `austin-starks/congressional-stock-trades` is tagged
  point-in-time.
- **Builder106/capitol-alpha** — a citable, replicable prior: politician
  purchases beat SPY by **+2.58% over 90 days (p<0.05)**, 16,203 trades
  2020-2024 — PIT-safety on transaction- vs. disclosure-date is UNCLEAR,
  re-verify before trusting the number, but it's a good target to replicate
  on Aegis's own feed as a sanity check.

### The literature (verified this session via exa, not from memory —
confidence: high, multiple independent papers agree on the qualitative shape)

- **Ziobrowski et al. 2004/2011** (pre-STOCK-Act): Senators' buy-minus-sell
  portfolios outperformed by ~12%/yr; House members by ~6%/yr.
- **Eggers & Hainmueller 2013**: re-examined 1985-2001 and 2004-2008 data,
  found the opposite (no outperformance) — the pre-STOCK-Act "edge" literature
  is itself contested, not just post-Act.
- **STOCK Act (2012)** requires disclosure within 45 days — designed
  specifically to kill the pre-Act edge via transparency, not prohibition.
- **Huang & Xuan (GWU working paper)**: pre-Act buy-minus-sell portfolio
  Carhart four-factor alpha = **9.5%/yr** (significant); post-Act = **0.9%/yr**
  (insignificant). Firms with politician ownership *lost* 1.4% in value
  around the Act's passage (news of losing that edge was itself priced).
- **Belmont, Sacerdote, Sehgal & Van Hoek 2022** ("Do senators and house
  members beat the stock market?", *Journal of Public Economics*):
  2012-2020 data, **no evidence of outperformance** in aggregate or for
  senators specifically accused of informed trading; House purchases
  *underperform* by 26bp over 6 months. **This is the TEACHER-LIBRARY-1
  prior the repo already codes to** — confirmed as the dominant post-Act
  finding.
- **Ansolabehere (Financial Review)**: powerful Republicans' buy-minus-sell
  portfolios earned >35%/yr annualized over a 1-week hold in 2004-2010 —
  concentrated in *less-experienced* powerful Republicans; **disappears
  post-STOCK-Act**, same pattern as Huang & Xuan.
- **Abdurakhmonov et al. 2023** (*Strategic Management Journal*,
  2012-2020 senators): the DISCLOSURE-DATE market reaction itself is
  significant — CAAR of +0.11-0.18% in the (0,+1)/(0,+2) window around
  disclosure, **larger when the senator sits on a committee with
  jurisdiction over the firm's industry**, and amplified by lobbying/PAC
  ties between the firm and the senator. But purchased stocks have
  **negative** 6-12 month abnormal returns — the market's positive reaction
  to disclosure is not validated by subsequent performance.
- **Karadas & Schlosky 2024, Hanousek et al. 2023, Ma & Moe 2023**: mixed,
  some post-Act positive findings (Senators ~5% abnormal in one study),
  contradicting Belmont et al. — **the post-Act literature has not
  converged**, which is exactly why TRIAL-CONGRESS-IC measures rather than
  assumes.
- **Eklind (2025 thesis, 2020-2025 PTRs)**: no significant outperformance,
  consistent with semi-strong EMH; congress-sold stocks that were already
  underperforming continue to underperform (behavioral, not informational).

### The one rule worth adding to the strategy library, with its falsifier

**Rule**: on disclosure (`disclosureDate`, never `transactionDate`) of an
open-market purchase by a member sitting on the committee with jurisdiction
over the purchased firm's sector (e.g., a Senate Banking Committee member
buying a bank stock, an Energy & Commerce member buying an energy/health
name), go long that name for N days.
**Matched control** (mandatory, per the "winner vs matched loser" mission
rule): the same sector's non-disclosed names over the identical window, AND
the same committee-member's purchases OUTSIDE their jurisdiction (removes the
member-specific stock-picking-skill confound from the jurisdiction-specific
information-advantage confound).
**Falsifier**: Abdurakhmonov's own paper is the falsifier in miniature — the
disclosure-day pop is real but purchased stocks show negative 6-12mo abnormal
returns, so if Aegis's jurisdiction-matched rule shows a positive
*disclosure-day* pop but a flat-to-negative *forward* return at 63/126d, the
correct read is "market overreacts to the signal, no real edge" — reject the
rule as an alpha source even though the announcement effect is real. This is
precisely what TRIAL-CONGRESS-IC's existing decision rule already checks
(forward IC at 21/63/126d, not the disclosure-day pop) — it should stay that
way; do not let a same-day CAR result substitute for the registered forward-IC
metric.

### Is the repo's congress collector actually broken? Yes — confirmed, not
fixed (per instructions)

Per `docs/research_notes/2026-09-20/audit_congress_collector.md` and
`docs/research_notes/2026-09-25/audit_services.md`: **zero rows** ever
written to local `pit_observations` for `congress_score:*` despite a daily
scheduled job (`pi_congress_collect`, 07:30 ET weekdays). Root causes found
by that prior audit (F1-F4, not fixed by this note per its scope):

- **F1**: `scheduler.py:1187-1205`'s `_congress_morning_collect` wraps the
  collector's own correctly-raising code in a `try/except Exception:
  logger.error(...)` with **no re-raise** — a hard FMP failure and a clean
  success both produce `status: "ran", exception: null` on the job receipt.
  Confirmed live: 15/15 production receipts show this identical shape.
- **F2**: `job_receipts.note(writes=...)` is never called anywhere in
  `scheduler.py` (zero matches for `note(` in the whole file) — so
  `writes: null` on the receipt means "nobody annotated it," not "zero
  rows," though the two audits agree the practical effect (no confirmable
  writes) is the same.
- **F3**: the 07:30 ET collection slot is justified as "when the shared FMP
  quota is fresh," but `fmp_budget.py`'s day boundary is **UTC**, and 07:30 ET
  is 11:30-12:30 UTC — roughly HALF WAY through the UTC budget day, so
  fallback/warm-loop FMP traffic since UTC midnight (≈19:00-20:00 ET the
  prior evening) can and does exhaust the shared ledger before congress's
  "fresh" slot fires.
- **F4**: member identity (`buyers`/`sellers` sets) is discarded before the
  PIT write — only counts (`n_buy_members`, `n_sell_members`) survive. This
  is a documented, frozen design choice (no per-member weighting was
  registered), not a bug, but it forecloses the committee-jurisdiction rule
  above without a schema change, since jurisdiction requires knowing WHICH
  member, not just how many.

**What a fix needs** (not performed here — audit only, per task scope): (1)
remove the swallowing try/except in `_congress_morning_collect` so
`@receipted()` sees real failures; (2) call `JR.note(writes=cg)` so the
receipt reports something real; (3) either move the collection slot to
right after UTC midnight or gate it on `fmp_budget.snapshot()["exhausted"]`
with a retry, and fold `fmp_budget` exhaustion into `main.py`'s
`_degraded_reasons` (currently absent); (4) if the jurisdiction rule above is
pre-registered, the schema needs to carry per-member identity + committee
membership, which is a **new trial**, not a patch to TRIAL-CONGRESS-IC's
frozen `params_frozen`.

### Insider trading (Form 4) — already correctly designed, not yet
scheduled

`docs/TRIALS/TRIAL-INSIDER-IC.md` already encodes the right prior source
choice: raw SEC Form 4 XML (`backend/services/insider_form4.py`), after
correctly REJECTING Finnhub free tier (empty `transactionCode`/`price`) and
`edgartools` (hung ~50min on 24 filings). Its frozen scoring
(`n_distinct_open_market_buyers + tanh(buy_value/$1M)`, code `P` only) is a
reasonable proxy for **Cohen-Malloy-Pomorski (2012)**'s "opportunistic"
insider concept but is NOT the same thing — CMP's actual finding, verified
this session:

- Opportunistic-only long-short (buys minus sells) portfolio: **82bp/month
  value-weight (9.8%/yr, t=2.15), 180bp/month equal-weight (21.6%/yr,
  t=6.07)**.
- Routine-trader portfolio: **essentially zero / insignificant** (-20bp to
  +43bp/month, t≤1.73).
- The split is based on each insider's **own trading-calendar history**
  (routine = same calendar month for years running), not on transaction code
  alone. TRIAL-INSIDER-IC's v1 limitation is candidly documented: "true
  routine-vs-opportunistic classification needs per-insider multi-year trade
  history we don't store; the P-code-only filter is the opportunistic
  proxy." This means Aegis's current proxy is **necessarily weaker** than
  CMP's actual effect size — expect something between the ~0bp routine
  number and the ~82-180bp/month opportunistic number, not the full effect,
  until per-insider trade-history classification is built.

---

## 3. Patents and research papers as leading indicators

### Data sources, feasibility this week vs. needs a subscription

| Source | Free? | Feasible in a week? | Notes |
|---|---|---|---|
| **USPTO PatentsView API** (`search.patentsview.org`, migrating to `data.uspto.gov` ODP) | Yes, no API key required historically (may now need a key post-ODP-migration — re-verify) | **Yes** | 27 endpoints (patent, assignee, inventor, cpc_class, us_patent_citation, etc.). Fields: `patent_id`, `patent_date` (grant date), `patent_title`, `assignee_organization`, `cpc_group`, citation counts. Grant date is the PIT-safe field (filing_date is earlier but application content/allowance isn't public knowledge until grant/publication). |
| **KPSS (Kogan-Papanikolaou-Seru-Stoffman) patent value dataset** | Yes — public GitHub repo `KPSS2017/Technological-Innovation-Resource-Allocation-and-Growth-Extended-Data` | **Yes, immediately** — this is the exact crosswalk needed | `KPSS_2024.csv`: patent-level panel 1926-2024 with `patent_num`, `permno`, `issue_date`, `filing_date`, `xi_nominal`/`xi_real` (dollar value of the patent from the stock-market reaction to its GRANT), `cites`. `Match_patent_permco_permno_2024.csv` is the **exact ticker-mapping crosswalk** the task asked about. `Match_patent_cpc_2024.csv` maps to CPC technology class. Updated through 2024 (author: Dimitris Papanikolaou, data library page confirms "Extended Data" is a living update). **This single dataset solves the ticker-mapping problem that is usually the hard part of using patent data.** |
| **Google Patents Public Data (BigQuery)** | Free tier (BigQuery sandbox) | Feasible but heavier lift — SQL over a multi-TB public dataset, useful for full-text search / citation graphs beyond what PatentsView exposes cheaply | Better for text/embedding features (patent claims text) than for the value/crosswalk problem, which KPSS already solves. |
| **arXiv API / OpenAlex** | Free, no key | Yes | Good for "research output by firm" (industry-affiliated co-authors, corporate research labs) — weaker firm-linkage than patents since arXiv has no assignee field; OpenAlex's institution disambiguation would need to be trusted or independently checked. |
| **Lerner-Seru-Short-Sun financial-patent dataset** (`KPSS2017/Financial_Patent_Data_public`) | Free | Yes, if the strategy is finance-sector specific | Post-2000 financial patents only, includes both KPSS market-value and Kelly-Papanikolaou-Seru-Taddy (2020) textual patent-value estimates. |
| **Benzinga/Bloomberg patent-alert products, IPqwery, PatSnap** | Paid | No | Not needed given KPSS + PatentsView cover the free path. |

### The literature (effect sizes verified this session)

- **Hirshleifer, Hsu & Li (2013, JFE)** "Innovative Efficiency and Stock
  Returns": IE = patents (or citations) / R&D capital. High-minus-low IE
  portfolio: value-weight **38-45bp/month** above low-IE, Carhart-alpha
  **45-46bp/month**; the effect is attributed partly to genuine risk and
  partly to **limited investor attention** (stronger where attention/
  uncertainty proxies are higher). Uses **grant date**, not application
  date, "to prevent any potential look-ahead bias" — the authors themselves
  flag the exact PIT discipline Aegis's `AEGIS_STRATEGIC_INVARIANTS.md`
  demands.
- **Cohen, Diether & Malloy (2013, RFS)** "Misvaluing Innovation": firms
  with high *R&D ability* (predictable persistence in turning R&D into
  patents/products) that continue high R&D spend are systematically
  undervalued; a long-short strategy on past R&D-ability earns **~11%/yr**
  abnormal return — reported as **~3x larger in magnitude** than
  Hirshleifer et al.'s IE effect on the same replicated sample. High-ability
  firms produce **+33% more future patents** and **+23% more patent
  citations** per one-SD increase in R&D (Fama-MacBeth, t=7.20 and t=6.65
  respectively) — i.e. the "ability" measure is itself validated against
  future patenting, which is the KPSS/PatentsView data this note surveys.
- **KPSS (2017, QJE)** itself: the underlying method — patent-level dollar
  value ξ inferred from the stock market's reaction to the patent's GRANT —
  is the dataset's whole point; Aegis would consume its OUTPUT (the
  `xi_real` column), not re-derive it.

### Concrete first feature and its expected effect size

**Feature**: `patent_grants_12m / rd_capital_5yr`, computed PIT-safe by
**grant date** (never filing/application date, which is public earlier but
carries no market-value signal until the claims are known at grant/
publication), joined firm-to-permno via the KPSS
`Match_patent_permco_permno_2024.csv` crosswalk, cross-sectionally ranked.
This is literally Hirshleifer-Hsu-Li's IE measure, buildable this week from
two free downloads (PatentsView for patent counts if KPSS's own 2024 cutoff
lags the current date, KPSS crosswalk for the permno join, Compustat/
whatever Aegis already has for R&D expense). **Expected effect size, per the
literature above: ~40bp/month value-weight, ~broadly in the range Aegis's own
`xs_ranker` result for fundamentals (+39bp/month, per S54 in memory) already
found** — i.e., this is a plausible, literature-grounded complement to
existing fundamentals ranking, not a speculative reach. A second, larger-
effect-size feature (Cohen-Diether-Malloy's R&D-ability measure, ~3x larger)
is a natural follow-on but requires building the "ability" construct (a
regression of current R&D on past sales growth) rather than a single ratio —
more work, bigger prior payoff.

**PIT rule, explicit**: score date = patent GRANT date (or, if using
KPSS's own value estimate ξ, the date the market could react to the grant,
which is what ξ is calibrated on) — never application/filing date. This
mirrors the repo's own `first_seen_utc` / `disclosureDate` discipline already
enforced in `congress_trades.py` and `event_vocabulary.py`.

---

## 4. News as evidence — a leaked list or political disclosure as a typed event

The repo already has the right skeleton (`backend/services/event_vocabulary.py`,
`backend/services/scenario_forecasts.py`) — a leak/disclosure story does not
need a new subsystem, it needs to be **typed into the existing 39-id
vocabulary and stamped through the existing forecast-row schema**.

**Event typing**: `event_vocabulary.EventType` already carries `id`,
`definition`, `sec_items` (8-K item mapping), `direction_prior`,
`magnitude_bucket`, `example`, `counter_example`. A congressional-disclosure
or leaked-document story is a *sourcing* fact about how an existing event
(e.g., `insider_trading_disclosed`, `regulatory_investigation`,
`m_and_a_related` — whichever of the 39 ids the underlying claim maps to) was
learned, not a new taxonomy dimension. The event's PIT stamp is `first_seen_utc`
of the PUBLICATION (the BBC article, the SEC EDGAR accession, the House
Clerk PTR filing) — never the transaction/trade date the story is ABOUT. This
is exactly `source_registry.py:571`'s existing convention (`t = earliest of
published_utc / first_seen_utc`) and `congress_trades.py`'s
`disclosureDate`-never-`transactionDate` rule generalized to news sources.

**The forecast row it must generate** (`scenario_forecasts.prediction_rows`,
schema 1.4.0 `PredictionRecord`): a leaked-list/disclosure story must produce
a row with — `ticker` (the affected symbol), `observable` (a falsifiable
statement, e.g. "the dominant typed event for TICKER on the session after
{as_of} is {event_type}"), `probability`, `made_at` = the row's own creation
time, `resolves_after` = `as_of` (the publication's `first_seen_utc`, not the
leak's alleged origin date), `thesis`/`counter_thesis`, `mechanism_id`,
`licence` (`PRODUCT_EXPERIMENT` until proven), `control_twin_id` pointing to
a **base-rate scenario** for the same (symbol, as_of) built from the era's
unconditional event-type frequencies — "graded identically; the LLM/news-
derived set is compared against this, never against zero." `inputs_used`
must carry `event_type`, `direction`, `magnitude_bucket`, and
`priced_by` = the deterministic (event_type, era) base-rate lookup, never a
number the extractor invented. **This is what lets the source earn a
grade**: `realised_from_typed_rows` later joins on `scope` (never on a raw
`tickers` list) to see whether the extracted `(event_type, direction)` pair
matched what actually happened, and the forecast is graded against its own
`control_twin_id`, not in isolation — precisely the "winner vs matched
loser" mission rule applied to a single news event instead of a factor
portfolio.

**Concretely, for the two leaks in §1**: the Trump/Truth-API story would
type as something like a governance/conflict-of-interest event on TMTG
(DJT) itself (magnitude and direction genuinely ambiguous — litigation
outcome undetermined) with `first_seen_utc` = the Fortune article's
publication time (2026-09-24), and a SEPARATE row per affected name if a
specific ticker's trading pattern is the claim (e.g., NVDA around the Jan 6
purchase) stamped to when *that* pattern was reported (BBC/NYT), not when
the trade occurred. The Goldman Conviction List addition/removal is a
cleaner case: type as a sell-side-rating-change-adjacent event, `first_seen_utc`
= the date the Conviction List update became public (GS's own publication
date, or the first press pickup if GS's exact release timestamp isn't
capturable), `scope` = the added/removed ticker (VRTX added / IBKR removed
in Sept 2026), and the base-rate control twin = the era's average forward
return for Conviction-List additions generally, not zero — letting Aegis
measure whether *this specific* addition carried information beyond "GS
adds ~1 name/month and it's usually already priced in."
