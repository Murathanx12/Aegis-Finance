# Chunk C — 24 interdisciplinary families as PIT columns (2026-09-26)

Session order `SESSION_ORDER_2026-09-26_SURVIVE_AND_PROFIT.md` rule 4: *"every
concept becomes a PIT column; a family that cannot name its observable, its
PIT rule and its source file is not registered."* This is that registration
pass for Murat's 24 concepts (`external_session_brief_2026-09-26.md` §C).
Extends `research_differentiation_and_interdisciplinary.md` Part B (24 papers
already found there — not repeated; cross-referenced by item number, `B.#`)
and cross-checks `research_strategy_library.md` (113-row catalogue — cross-
referenced by row id, e.g. `AREV-04`) so nothing here duplicates a row that
already exists.

**Method.** WebSearch was already at its 200/200 session cap on the first
call (confirmed live this session), so every live lookup below used
`mcp__exa__web_search_exa` / `web_fetch_exa`, per the task's fallback
instruction. Repo facts (file paths, columns, schemas) were read directly,
not searched: `backend/services/xs_ranker.py`, `revision_flow.py`,
`fundamental_features.py`, `pit_collectors.py`, `insider_form4.py`,
`thesis_card.py`, `news_registry.py`, `pm_catalysts.py`, `iif1_features.py`,
the parquet files under `backend/data/optimus/analyst/` and
`backend/data/optimus/actor_corpus/`, and
`C:\Users\mrthn\Aegis module\TRIALS\PREREG_ANALYST_SKILL_1.md` (a **separate,
local git repo** — see `CLAUDE.md`'s four-repositories table; it holds the
2026-07/08 investor-brain module and is ingested by Optimus, not by this
repo's git history).

**Evidence-strength tags**: `[V]` = fetched the paper's abstract/tables this
session (link given). `[B]` = well-known result, background knowledge, not
re-fetched — matches `research_strategy_library.md`'s own convention.
`[LIVE]` = a 2026 event found this session that is itself the case study
(CXMT/Micron/ASML), not an academic paper.

---

## 1. The 24 rows

### Innovation (concepts 1–3)

| # | Concept | Observable (one number, per ticker, per date) | PIT rule | Source |
|---|---|---|---|---|
| 1 | Innovative efficiency | `IE = patents_granted[t] / RD_capital[t-2]`, RD_capital = 5yr depreciated (20%/yr) cumulative R&D expense, 2yr application-grant lag built in | Join on **grant date**, never application date (grant is the first public event); RD_capital lagged 2 fiscal years per Hirshleifer-Hsu-Li's own construction | **(b) FREE AND FETCHABLE.** Patents: USPTO PatentsView API (`api.patentsview.org`, free, no key, ~45 req/min) for grant date + assignee; historical patent *value* (better than raw counts) from the KPSS extended dataset, free CSV on GitHub (`KPSS2017/...-Extended-Data`, permno-matched, patent-level, through 2024). R&D expense: **not yet a field** — `fundamental_features.py` computes `gp_at, ope_be, ni_be, at_gr1, cash_at, debt_at` but no `rd_at`; needs one new XBRL tag pull (`ResearchAndDevelopmentExpense`) added to `pull_sec_fundamentals.py`, joined on `filed` per that module's own rule |
| 2 | Patent acceleration | YoY % change in KPSS aggregate patent *value* (Σξ) per firm, distinct from the *efficiency* ratio above — this is growth in output, not output-per-R&D-dollar | Grant date, same as #1; KPSS's own value estimate uses the stock-market reaction in the days around grant, so a patent's *value* is only knowable after that reaction window closes (~2-5 trading days) — a stricter PIT bound than the grant date alone | **(b) FREE AND FETCHABLE.** Same KPSS GitHub CSV for history through 2024; PatentsView raw grant-count YoY as a cruder same-day proxy for 2025-2026 (KPSS lags because it needs the market-reaction estimation step) |
| 3 | R&D hiring | Count of open reqs at a company's Greenhouse/Lever/Ashby ATS board whose title/description matches an R&D taxonomy (`engineer`, `scientist`, `research`), 30d level and 90d Δ | `observed_at` = the day the scrape saw the posting; postings do not carry a public "posted" timestamp reliably, so **first-seen-by-us** is the PIT bound, matching `news_registry.PIT_GRADES`'s `first_seen_only` grade exactly | **(b) FREE AND FETCHABLE**, no key: Greenhouse (`boards-api.greenhouse.io/v1/boards/<slug>/jobs`), Lever (`api.lever.co/v0/postings/<slug>`), Ashby (`api.ashbyhq.com/posting-api/job-board/<slug>`) — all public JSON, no auth, per MEMORY.md S53 ("hiring signal via Greenhouse/Lever/Ashby (LinkedIn banned)"). The hard part is the ticker→slug map (manual, ~200 names) |

### Management (concepts 4–9)

| # | Concept | Observable | PIT rule | Source |
|---|---|---|---|---|
| 4 | Government contract awards | 90d trailing Σ(award amount) from USAspending, scaled by trailing-4q revenue | `startDate` (period-of-performance start), **not** the award's last-modified date — a contract "modification" record updates in place, so a raw re-pull can silently move history; anchor on `startDate` per the FinBrain schema note found this session | **(b) FREE AND FETCHABLE.** `api.usaspending.gov/api/v2/search/spending_by_award/` (POST, no key, no documented rate limit at Aegis's volume); recipient name → ticker/CIK mapping is the real cost (own build, or accept FinBrain's paid pre-mapped feed as a shortcut) |
| 5 | Management promise-vs-delivery | Rolling guidance error: `abs(actual_EPS − last_guided_EPS) / |price|`, trailing 8 quarters, **at the firm level** | Guidance value known at issuance date (from the catalyst calendar / 8-K); actual known at the *next* earnings release — never the other way | **(c) NOT AVAILABLE without a build.** `pm_catalysts.py` carries earnings *dates* (Finnhub) but not the guided EPS figure itself; would need an 8-K/press-release EPS-guidance extractor (LLM synthesis over `news_corpus`/EDGAR full-text, same pipeline `thesis_card.py` already runs for other fields) |
| 6 | CEO execution reliability | Same guidance-error statistic as #5, but a **manager fixed effect** — the part of the error that moves with the CEO/CFO and not with the firm (i.e., re-estimated when the CEO changes) | Same as #5, plus a CEO-tenure-dated roster (proxy statements, DEF 14A) so a guidance error is attributed to whoever signed it at the time | **(c) NOT AVAILABLE without a build.** Needs #5's guidance-error series *plus* an executive-tenure table (free from EDGAR DEF 14A full-text, but unparsed today) |
| 7 | Management-language changes | Already surveyed, do not re-derive: B.3 #13 (narcissism/self-referential language, Chatterjee & Hambrick 2011), #15 (deception classifiers, Larcker & Zakolyukina 2012), B.5 #24 (Siano 2025 LLM-derived "news" from earnings text). Observable: quarter-over-quarter change in a DeepSeek-scored tone/hedging/deception index on the earnings-call transcript | Transcript publication timestamp (same-day as the call; transcripts lag the call itself by hours, use the transcript's own timestamp, not the call date) | **(a) ALREADY IN THE REPO, partially.** `thesis_card.py`'s web side already runs one OpenClaw quest per name including "analyst actions in 90 days" and IR events; earnings-call *transcript ingestion* itself is not yet wired — this is the natural home once it is |
| 8 | Business-model pivots | *(see §3 — not registered as a numeric PIT column)* | — | — |
| 9 | PMF inflection | *(see §3 — not registered as a numeric PIT column)* | — | — |

### Market structure / competition (concepts 10–15)

| # | Concept | Observable | PIT rule | Source |
|---|---|---|---|---|
| 10 | Capacity constraints | Count of 10-K/10-Q/8-K sentences matching a "capacity-constrained" lexicon (`sold out`, `backlog`, `lead time extended`, `capacity limited`) per filing, scaled by the filing's own sentence count | SEC filing **acceptance timestamp** (EDGAR full-text search returns this natively) | **(b) FREE AND FETCHABLE.** `efts.sec.gov/LATEST/search-index?q=...` (SEC EDGAR full-text search API, free, no key, documented ~10 req/s fair-access limit — same fair-access convention `insider_form4.py` already honors). No academic return-predictor paper exists for this exact construction (see falsifier); the live 2026-07-27 Micron/ASML/CXMT episode below is the working case, not a factor |
| 11 | Pricing power | `margin_chg` (already a fundamentals field) conditioned on **input-cost inflation** — i.e., gross margin holding or expanding while a cost-of-goods proxy (PPI for the firm's NAICS, free from FRED) rises | Join on `filed`, same rule `fundamental_features.py` already enforces; PPI is published monthly with a ~2-week lag, itself PIT-clean | **(a) ALREADY IN THE REPO, mostly.** `gross_margin`/`margin_chg` exist (`QUAL-02`, `INFL-01` in `research_strategy_library.md`); only the PPI-conditioning join is new, and PPI itself is (b) free from `fred.stlouisfed.org` (already an Aegis data source per `macro_indicators.py`) |
| 12 | Network effects | *(see §3 — not registered)* | — | — |
| 13 | Switching costs | *(see §3 — not registered)* | — | — |
| 14 | China capacity entry | For each US-listed name with a named Chinese competitor, a binary/graded event: competitor capacity-expansion announcement (new fab, new capacity target, IPO proceeds earmarked for capacity) dated to first public disclosure | First public disclosure date (press/Reuters/company IPO filing), **not** the date capacity comes online — the market moves on the funding/capacity-target announcement, confirmed **live** by two 2026-07-27 events this session found: CXMT's Shanghai IPO (**Micron −4.3% to −6.9%, ~$45B of market cap**, same session) and a China-DUV-lithography report (**ASML −6.3%, ~$44B**), both same-day, both citing *future* capacity/capability, not present shipments `[LIVE]` | **(c) NOT AVAILABLE as a systematic feed** — no structured "competitor capacity announcement" calendar exists free; each event today is a manual OpenClaw/news read. A crude proxy: NAICS-matched China A-share/H-share IPO calendar (Shanghai/Shenzhen exchange filings, free) cross-referenced against the US name's 10-K "competition" risk-factor text (SEC EDGAR full-text search, same API as #10) |
| 15 | Supply-chain lead/lag | Firm-level import-disruption index (shipment-level bill-of-lading gaps/delays for a firm's known suppliers) | Bill-of-lading records post with a multi-week customs lag; PIT bound is the record's own filing date, not the shipment date | **(c) NOT AVAILABLE free at ticker granularity.** The one rigorous academic construction found (Yale/Cowles working paper, 2013-2023 seaborne shipment data) uses a paid bill-of-lading vendor (Panjiva-class). A degraded free substitute: ISM PMI "Supplier Deliveries Index" (free, FRED) — **market/sector-level only**, not a per-ticker column, so it can gate a macro overlay but not rank names |

### Attention / behavioral (concepts 16–21)

| # | Concept | Observable | PIT rule | Source |
|---|---|---|---|---|
| 16 | Attention shocks | z-score of a ticker's daily news-article count (`news_registry`) vs its own trailing-60d baseline | `first_seen_utc` per article, exactly as `news_registry.PIT_GRADES` already enforces (`native_stamp` preferred, `first_seen_only` fallback) | **(a) ALREADY IN THE REPO.** `backend/services/news_registry.py` — this is the cheapest row in the whole set: no new fetch, one groupby |
| 17 | Google-search acceleration | z-score of Google Trends search-interest index for the ticker/company name, 7d vs 90d baseline (Da-Engelberg-Gao SVI construction, B.1 #4) | Trends data itself has no fixed release lag (near-real-time index), but historical backfill via `pytrends` is rate-limited (unofficial API, ToS grey area, per the pattern `research_differentiation...md` Part C already flags for scraped sources) — mark every pulled value with `fetched_at` | **(b) FREE AND FETCHABLE**, real history back to 2004, but slow to bulk-backfill (rate limits) — practically a forward-heavy build even though not strictly `[FWD]` |
| 18 | Social crowding | Mention-volume spike on Reddit/X for a ticker vs its own baseline (B.5 #23, ATT-04 in the strategy library) | First-seen timestamp of the mention, same PIT convention as #16 | **[FWD]**, per the strategy library's own ATT-04 note ("mechanism close to self-negating once documented") and Part C's finding that WSB's real signal is concentrated in ~462 accounts and mania regimes — build a cheap monitoring feed, not a research budget line, exactly as Part C §C.4 already ranked it (#8 of 10) |
| 19 | Lottery preference | `MAX` = maximum single-day return over the trailing 21 sessions (Bali, Cakici & Whitelaw 2011, "Stocks as Lotteries," *JFE*) — **not currently a `xs_ranker.FEATURES` column**, but trivially derivable from the same daily-bar panel that already produces `skew_63`/`max_drawdown_63` | No lag needed beyond the trailing window itself — pure price-panel feature | **(a) ALREADY IN THE REPO** (same `bars.parquet` panel `xs_ranker.py` already reads); this is the second-cheapest row — one new column in `FEATURES`, zero new data |
| 20 | Disposition effect | Aggregate unrealized-gain/loss overhang per name (Frazzini 2006, B.1 #5; `revision_flow.py`'s docstring already calls this "the object that died" once — different construction, see falsifier) | Would need a reference-price/cost-basis reconstruction dated to each 13F/holder snapshot, then marked to market at every subsequent date — the reconstruction itself must never peek at a later price | **(c) NOT AVAILABLE without a 13F-based cost-basis build.** `pit_collectors.py` already has the 13F collector (`latest_13f_filing`, `as_of`=period of report, `observed_at`=filing date) but only for two tracked institutions and cadence only, no holdings-level infotable extraction yet ("a deliberate follow-on, Chunk 2b" per that module's own docstring) |
| 21 | FOMO / reversal | Short-horizon reversal after a `rev_1`/`rev_5` extreme move, conditioned on an attention spike (#16) co-occurring — i.e., REV-01/REV-02 (`research_strategy_library.md`) **interacted with** ATT-01, not a new base signal | Same PIT rule as `rev_1`/`rev_5` (price panel) plus #16's `first_seen_utc` | **(a) ALREADY IN THE REPO** — `rev_1`, `rev_5` are existing `FEATURES`; #16 is free; this row is a two-column interaction term, no new fetch |

### Analyst trio (concepts 22–24)

| # | Concept | Observable | PIT rule | Source |
|---|---|---|---|---|
| 22 | Analyst-skill persistence | Per-analyst (`amaskcd`) holdout-corr score from the already-computed ladder in `FINDING_2026-08-23_ANALYST_RELIABILITY.md` §4 (0.253 unrestricted, up to 0.513 at ≥30 holdout claims), applied as a **weight** on that analyst's live outstanding calls | Train/holdout split is temporal (2013-2020 train, 2021-2024 holdout, per the FINDING); a live weight for 2026 must be re-estimated walk-forward, never using the analyst's 2025-2026 calls to score their own 2025-2026 weight | **(a) ALREADY IN THE REPO.** `backend/data/optimus/actor_corpus/ibes_graded.parquet` (98,772 graded claims, 5,793 analysts, 2013-2024) + `score_receipt.json`'s `persistence.by_min_holdout_claims` ladder. **This is the cheapest row in the analyst trio** — the hard statistical work (§7 below) is done; only the walk-forward re-estimation and the wiring into a live weight remain |
| 23 | Analyst first-mover advantage | Per-broker (`estimid`, from `target_revisions.parquet`'s `firm` field) rank by **timeliness** of target/rating revisions relative to peers covering the same name — Cooper, Day & Lewis (2001, *JFE*, "Following the Leader") show lead analysts identified this way have **greater price impact** than followers, more informative than accuracy- or volume-based rankings `[V]` | `event_date` in `target_revisions.parquet` is already the dated revision event; "lead" vs "follow" is computed only from revisions with `event_date` ≤ the name's evaluation date — no look-ahead in the ranking itself | **(a) ALREADY IN THE REPO.** `backend/data/optimus/analyst/target_revisions.parquet` (393,581 rows, `ticker, event_date, firm, ...`) carries firm identity and dated events — everything Cooper-Day-Lewis's construction needs except a same-day intraday price-impact measure (daily bars are enough for a same/next-day proxy) |
| 24 | Estimate-revision cascades | Herding/cascade statistic: does analyst *j*'s revision direction correlate with the two immediately-preceding revisions by other analysts on the same name (Welch 2000, *JFE*, "Herding among Security Analysts") `[V]` — distinct from `AREV-04`/`AREV-09` (revision *momentum*/*acceleration* of the aggregate), this is herding **between individual analysts** | Only revisions with `event_date` strictly before the analyst's own revision count as "preceding" — same strict-inequality convention `revision_flow.py`'s docstring already states for `event_date < asof` | **(a) ALREADY IN THE REPO.** Same `target_revisions.parquet`, sequenced by `event_date` within `ticker`; Welch's own method needs discrete buy/sell/hold actions, which the `action`/`target_action` columns already carry |

---

## 2. Ranking by expected information per build-hour (given what's on disk)

Highest first. "Cost" is hours to a working PIT column reading only what
exists; `[FWD]`/thin marks carried over.

1. **#22 analyst-skill persistence** — the statistics are DONE
   (`FINDING_2026-08-23`), the corpus is graded, the walk-forward re-fit is the
   only new work. ~2-4h.
2. **#19 lottery preference (MAX)** — one new column over an existing panel,
   zero new data, a 40-year-replicated result (`[B]`, >1%/mo spread). ~1-2h.
3. **#16 attention shocks** — `news_registry` already has the timestamps; a
   groupby and a z-score. ~2-3h.
4. **#21 FOMO/reversal** — an interaction of two existing columns (#19's
   sibling `rev_1`/`rev_5` × #16). ~2h once #16 exists.
5. **#23 analyst first-mover** — data on disk, construction is a peer-rank
   over `target_revisions.parquet`, Cooper-Day-Lewis's own method is a
   published, replicable statistic. ~4-6h.
6. **#24 estimate-revision cascades** — same parquet, Welch's discrete-choice
   method is more involved to implement correctly than #23's rank. ~5-8h.
7. **#11 pricing power** — 90% built (`gross_margin`/`margin_chg` already
   exist); only the PPI join is new, and PPI is a one-call FRED fetch.
   ~3-4h.
8. **#3 R&D hiring** — free APIs, no key, but the ticker→ATS-slug map is
   real manual work (~200 names). ~10-15h.
9. **#1 innovative efficiency** — free KPSS + PatentsView data, but needs a
   new `rd_at` fundamentals field first (one more XBRL tag in
   `pull_sec_fundamentals.py`). ~8-12h.
10. **#2 patent acceleration** — rides on #1's pipeline once built; +2-3h.
11. **#4 government contract awards** — free API, well-documented, but the
    recipient-name→ticker map is the real cost, and the one independent
    event study found this session (`TanushReddy111/Defense_contracts_event_study`)
    already shows the naive number is an artifact of benchmark choice (see
    falsifier below) — build it anyway, but budget for the sector-matched
    benchmark from day one. ~10-15h.
12. **#10 capacity constraints** — free EDGAR full-text search, but a
    lexicon needs tuning and false-positive-checking; no academic
    return-predictor exists to validate against, only the live CXMT/Micron/
    ASML case. ~10-15h.
13. **#7 management-language changes** — the OpenClaw quest infrastructure
    exists (`thesis_card.py`); transcript ingestion itself does not. ~10-15h.
14. **#17 Google-search acceleration** — free but rate-limited; real
    history exists but bulk-backfill is slow. ~6-10h + wall-clock rate-limit
    time.
15. **#5 management promise-vs-delivery** — needs an LLM guidance-EPS
    extractor over 8-Ks/press releases; real build. ~15-20h.
16. **#6 CEO execution reliability** — needs #5 plus an executive-tenure
    table from DEF 14A. ~20-25h (depends on #5).
17. **#14 China capacity entry** — no systematic feed; each instance is a
    manual OpenClaw read today, though the mechanism is real and just
    happened twice this session's search window. ~15-20h for a crude
    NAICS-matched proxy, unbounded for a general feed.
18. **#18 social crowding** — cheap monitoring feed, `[FWD]`, low prior per
    Part C's own ranking (#8 of 10 sources). ~5-8h, low expected value.
19. **#15 supply-chain lead/lag** — only a macro/sector-level free proxy
    exists (ISM Supplier Deliveries via FRED); no per-ticker column without a
    paid vendor. ~4h for the sector overlay, then blocked.
20. **#20 disposition effect** — blocked on 13F holdings-level extraction,
    explicitly deferred in `pit_collectors.py`'s own docstring ("Chunk 2b").
    ~20-30h once that dependency ships.

## 3. Six to build first (exact rule)

1. **Analyst-skill persistence weight** (#22). Rule: for each `amaskcd` with
   ≥10 graded holdout claims in `ibes_graded.parquet`, weight = the
   walk-forward holdout correlation (re-estimated rolling, never using the
   scored period's own outcomes); apply as a multiplier on that analyst's
   currently-outstanding recommendation before it enters any composite.
2. **MAX lottery feature** (#19). Rule: `MAX_21 = max(daily_return)` over the
   trailing 21 sessions, added to `xs_ranker.FEATURES`; register `LOT-01`
   in the strategy library as bottom-decile-`MAX_21` long, matching
   Bali-Cakici-Whitelaw's own construction, monthly hold.
3. **Attention-shock z-score** (#16). Rule:
   `z = (articles_1d − mean(articles_60d)) / std(articles_60d)` per ticker
   per day from `news_registry`; feeds both a standalone `ATT-05` row and
   #21 below.
4. **FOMO/reversal interaction** (#21). Rule: `REV-01`/`REV-02` (existing)
   conditioned on `z(#16) > 2` at entry — i.e., does short-horizon reversal
   strengthen specifically when the move co-occurred with an attention
   spike, vs. an unconditional reversal.
5. **Analyst first-mover rank** (#23). Rule: for each `ticker × event_date`
   revision in `target_revisions.parquet`, rank the revising `firm` by how
   many other firms revise the *same direction* on the *same name* within
   the following 5 trading days (Cooper-Day-Lewis timeliness proxy); own
   names where a historically-lead firm just revised, avoid/fade where only
   historically-lag firms have moved.
6. **Pricing-power-under-cost-pressure** (#11). Rule: `margin_chg > 0` AND
   the matching NAICS PPI 12m change > its own trailing-3yr median — i.e.,
   margin holding *while input costs are rising sector-wide*, distinct from
   `QUAL-02`'s unconditional margin-expansion row.

## 4. Four that cannot become a PIT column with what we have — do not register

- **#8 Business-model pivots** and **#9 PMF inflection.** No observable
  survives contact with the definition: a "pivot" or an "inflection" is a
  narrative judgment about *why* revenue/margin moved, not a measurable
  number distinct from the revenue/margin move itself (`rev_qoq`,
  `margin_chg`, already registered as `INFL-01`–`INFL-04`). Forcing a number
  here would either (a) duplicate an existing fundamentals column under a new
  name, or (b) be an LLM's opinion with no PIT source file behind it. These
  belong in `thesis_card.py`'s free-text bull/bear synthesis, which already
  exists for exactly this kind of qualitative call, not as a numeric feature.
- **#12 Network effects** and **#13 Switching costs.** Real theory (Farrell
  & Klemperer 2006 on lock-in economics `[B]`), real firm-level measures exist
  in the literature (customer-base churn from household-transaction panels,
  HBS working paper `[V]`; switching-cost estimation from proprietary usage
  logs in online brokerage, Chen & Hitt 2002 `[V]`) — but every measure found
  this session needs data Aegis cannot get free: a household-transaction
  panel or a firm's internal usage logs. The nearest free proxy (margin
  stability, `LV-05`/`QUAL-01`) is **already a different registered row**
  under a different name and would double-count the same variance if
  relabeled "network effects." Not registered; if a free proxy is found
  later it is a new PREREG, not a relabeling of an existing one.

## 5. The analyst trio — tied to the frozen prereg and the standing finding

Concepts **#22 (analyst-skill persistence)**, **#23 (analyst first-mover
advantage)**, and **#24 (estimate-revision cascades)** are the cheapest three
of the whole 24 for one shared reason: **the data and the statistical
groundwork already exist, in this program, dated before today.**

- `docs/FINDING_2026-08-23_ANALYST_RELIABILITY.md` established
  **`RELIABILITY_PERSISTS`**: an analyst's train-period holdout correlation
  predicts their next-period accuracy, at every threshold tested (0.253
  unrestricted up to 0.513 at ≥30 holdout claims, every 95% CI excluding
  zero). That FINDING is concept #22's entire premise, already measured, on
  the corpus (`actor_corpus/ibes_graded.parquet`) that #22 reads directly.
  Its own §7 explicitly lists "walk-forward the persistence estimate" as the
  next honest step — which is exactly build item 1 in §3 above.
- `C:\Users\mrthn\Aegis module\TRIALS\PREREG_ANALYST_SKILL_1.md`
  (**registered 2026-08-31, never run**, per that file's own header: "no
  skill statistic has been calculated") pre-commits the decision rule for
  the *adjacent* question — does weighting the **consensus price target**
  by broker skill beat an equal-weighted consensus (ΔIC ≥ 0.010, paired
  t ≥ 2.0 over 72 evaluation months, Newey-West(3), full frozen parameter
  table in that file's §4). It is a **different mechanism** from #22
  (price-target weighting vs. recommendation-reliability weighting) and a
  **different repo** (the Aegis module, WRDS `tr_ibes.ptgdetu`, not this
  repo's `target_revisions.parquet`), but it is the same family, already
  pre-registered, and running it costs "one WRDS pull + local compute; $0
  external" per its own §7. If that pull is available this session, running
  the already-frozen ANALYST-SKILL-1 trial is strictly higher-value than
  designing a new prereg for #23/#24, because its decision rule, power
  calculation, and corpse-check are already written and dated — exactly the
  case the family's own protocol step 2 exists for ("a session spent an hour
  re-deriving [a finding] by grepping, while the brain held [it]").
- #23 and #24 are new observables (timeliness-rank, cascade-correlation)
  that the FINDING and the PREREG do not directly answer, but they read the
  **same** `target_revisions.parquet` already on disk and reuse the same PIT
  convention (`event_date` strict inequality) `revision_flow.py` already
  enforces — so the marginal cost of both is "write the statistic," not
  "acquire the data."

---

## Sources for this note

Repo files read directly (paths above). External sources fetched via
`mcp__exa__web_search_exa`/`web_fetch_exa` this session:

- Hirshleifer, Hsu & Li, "Innovative Efficiency and Stock Returns," *JFE* 2013 — https://doi.org/10.1016/j.jfineco.2012.09.011
- Kogan, Papanikolaou, Seru & Stoffman, "Technological Innovation, Resource Allocation, and Growth," *QJE* 2017, extended data — https://github.com/KPSS2017/Technological-Innovation-Resource-Allocation-and-Growth-Extended-Data
- USPTO PatentsView API — https://patentsview.org/apis/api-endpoints
- USAspending API docs — https://api.usaspending.gov/docs/endpoints ; independent event study — https://github.com/TanushReddy111/Defense_contracts_event_study
- Hutton & Stocken, "Prior Forecasting Accuracy and Investor Reaction to Management Earnings Forecasts," 2009 — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=817108
- Kala, Shailer & Wilson, "Are Individual Analysts' Responses to Management Forecasts Conditioned by Managers' Forecasting Track Records?," 2024 — https://doi.org/10.1080/09638180.2024.2413001
- Novy-Marx-adjacent margin work: "Corporate Innovation, Price Momentum, and Equity Returns" (gross-margin-change factor) — via Exa fetch
- Farrell & Klemperer, "Coordination and Lock-In: Competition with Switching Costs and Network Effects," 2006 — https://www.nuffield.ox.ac.uk/economics/papers/2006/w7/farrell_klempererwp.pdf
- Chen & Hitt, "Measuring Switching Costs... Online Brokerage Industry," *ISR* 2002 — https://pubsonline.informs.org/doi/10.1287/isre.13.3.255.78
- Welch, "Herding among security analysts," *JFE* 2000 — https://doi.org/10.1016/s0304-405x(00)00076-3
- Cooper, Day & Lewis, "Following the Leader: A Study of Individual Analysts' Earnings Forecasts," *JFE* 2001 — https://doi.org/10.1016/S0304-405X(01)00067-8
- Bali, Cakici & Whitelaw, "Stocks as Lotteries and the Cross-Section of Expected Returns," *JFE* 2011 / NBER 14804 — https://www.nber.org/papers/w14804
- Shevlin, Lourie, Gutierrez & Nekrasov, "Are Online Job Postings Informative to Investors?" — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3342669
- Belo, Lin & Bazdresch, "Labor Hiring, Investment, and Stock Return Predictability in the Cross Section," *JPE* 2014 — https://ideas.repec.org/p/ecl/ohidic/2012-17.html
- Yale/Cowles working paper on supply-chain disruptions and supplier capital — https://cowles.yale.edu/sites/default/files/2025-04/d2402r1.pdf
- Löfgren, "Have We Got News For You: ... Firms' Optimal Expected Capacity Utilization," Riksbank WP 466 — https://www.riksbank.se/globalassets/media/rapporter/working-papers/2026/no.-466-...pdf
- CXMT/Micron/ASML live episode (2026-07-26/27): Motley Fool, TS2.tech, Invezz, WKZO/Reuters — links in-line above; used as the live case for concept #14/#10, not as an academic citation
- `docs/FINDING_2026-08-23_ANALYST_RELIABILITY.md`, `C:\Users\mrthn\Aegis module\TRIALS\PREREG_ANALYST_SKILL_1.md` — read directly, not searched
