# Research instruments: can OpenClaw reach outside systems for academic/patent evidence? (2026-10-07)

**Role: Sonnet researcher, read-only.** No installs, no browser automation, no writes outside
this note. Every instrument below was checked by fetching its own docs page or pricing page
this session (`WebFetch`/`WebSearch`/`mcp__exa__*`); where a fetch failed, that failure is
reported as data, not papered over. One `mcp__claude_ai_Bigdata_com__bigdata_help` call was made
(read-only; reports subscription/balance status, no data retrieved, no cost incurred — PAYG
balance is $0). Nothing here is a `RESEARCH_CLAIM`; this is the written half of the owner's
2026-10-07 brief on outside research systems, same `PRODUCT_EXPERIMENT` shape as
`docs/OUTSIDE_TOOLS_2026-10-07.md`.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT (money) | **NONE.** This is an instrument audit and a design, not a strategy result. |
| Free academic APIs confirmed working today, keyless | **OpenAlex, CrossRef** — both returned the correct paper on the first query, $0, no key. |
| Free academic APIs that failed today, keyless | **Semantic Scholar, arXiv** — both returned HTTP 429 on every attempt (2 tries each via `WebFetch`, 2 more via `mcp__exa__web_fetch_exa`, 4 total failures across two independent fetch paths). |
| Probe coverage of the one seed card (Lou-Polk-Skouras 2019) | OpenAlex 1/1 primary paper (346 citations, 81 total matches); CrossRef 1/1 primary paper (DOI confirmed, 319 citations) — the two providers' own citation counts disagree by ~8%. |
| Novelty found that the card did not have | **CrossRef surfaced two 2025 SSRN working papers** directly extending the "tug-of-war" framing ("Day and Night Expected Returns Under Overnight Information Shocks: New Tug-of-War Pattern," DOIs `10.2139/ssrn.5240716` / `10.2139/ssrn.5247123`) that neither the card nor OpenAlex's result set named. |
| Paid instruments needing an owner decision | **Perplexity API** (second paid LLM provider, conflicts with "DeepSeek is the only provider"), **Brave Search API** (card required even for the free credit), **Bigdata.com** (PAYG balance $0, needs a top-up), **Consensus API** (paid tiers; its free 30 calls/month tier still needs a named signup), **patent systems requiring an account** (USPTO ODP needs ID.me identity verification; EPO OPS needs a developer-portal registration; Google Patents BigQuery needs a GCP account). |
| Three to wire first | **OpenAlex, CrossRef, NBER working-papers RSS** — all $0, keyless, no card, two of three proven working this session, the third fetched and field-verified. |

---

## 1. Instrument register

Each row was verified by fetching the instrument's own docs/pricing page this session, unless
marked otherwise. "OpenClaw callable" distinguishes a **deterministic HTTP fetcher** (door 2 in
the 2026-10-06 audit's taxonomy — no model, no agent turn, same shape as the Google News RSS /
EDGAR lane already live in `backend/services/query_planner.py`) from a call that would need an
**agent turn** (door 1 — costs a DeepSeek call) or is **not reachable by OpenClaw at all** (a
Claude Code / Claude.ai-side tool with no bridge into OpenClaw's own tool scope,
`backend/services/openclaw_tool_scope.py`).

### Academic literature

| instrument | auth | cost | rate limit (as verified) | returns | storage terms | OpenClaw callable |
|---|---|---|---|---|---|---|
| **OpenAlex** | none required; free key raises daily budget 10x (`help.openalex.org`, fetched) | $0 under the free quota; `cost_usd` field appears for pay-as-you-go beyond it | not quoted on the fetched overview page; **empirically: one query succeeded immediately, no 429** | Works/Authors/Sources/Institutions/Topics graph; nested entities come back "dehydrated" (need a follow-up call for full fields); citation counts (`cited_by_count`) | **CC0** — "no license worries, ever" (fetched, verbatim) | **Yes — deterministic fetcher.** Same shape as the existing RSS/EDGAR lane; no agent turn needed. |
| **CrossRef** | none; optional `mailto=` param for the "polite pool" (faster service) | $0, "no sign-up is required... almost none of the metadata is subject to copyright" (fetched, verbatim) | not quoted on the fetched page; **empirically: one query succeeded immediately, no 429** | DOI-canonical bibliographic metadata, `is-referenced-by-count` (a citation-count proxy), some abstracts (publisher-copyright caveat noted on the page itself); **no full text** | page says metadata "may be used for any purpose," with publisher-copyright caveat on some abstracts | **Yes — deterministic fetcher.** Same shape. |
| **Semantic Scholar (Academic Graph API)** | key optional, free; the docs page (fetched) names three products (Graph, Recommendations, Datasets) without quoting limits | $0 | **not independently confirmed from docs this session** (the fetched page gave no numbers); **empirically: HTTP 429 on 2 of 2 attempts** via `WebFetch`, and the same two URLs also failed via `mcp__exa__web_fetch_exa` (`CRAWL_UNKNOWN_ERROR`, `CRAWL_LIVECRAWL_TIMEOUT`) — 4 failures across 2 independent fetch paths, 0 successes | citations, references, fields of study, abstracts, external IDs (DOI/arXiv/PubMed); **no full text** | not independently verified this session | **Conditionally.** Keyless reliability measured today is poor; a free API key (2-minute signup) is the cheap fix, same shape as the NN-lab's own pattern of "a free key raises the ceiling." |
| **arXiv API** | none | $0 | not quoted on the fetched docs page (`info.arxiv.org/help/api/basics.html`); **empirically: HTTP 429 on 2 of 2 `WebFetch` attempts** | abstracts, metadata, categories, links to PDFs (full text is a linked PDF, not inline) | page points to a separate "Terms of Use for arXiv APIs" document, not fetched this session | **Yes, but narrow-scope.** $0, keyless, same deterministic shape — but Lou-Polk-Skouras (a 2019 *JFE* paper) was never deposited on arXiv; OpenAlex/CrossRef's own venue fields confirm its only venue is the journal plus 2025-26 SSRN/arXiv *follow-on* papers, not the original. arXiv's real value is the quant/ML/LLM-finance preprint topic class, not classical asset-pricing journal mechanisms. |
| **NBER working papers RSS** | none | $0 | not applicable (RSS pull) | title (authors embedded in the title string), abstract (`description`), link, `guid` — **no separate date field**, metadata only, no full text | none stated; this is a publisher's own syndication feed | **Yes — deterministic fetcher.** `nber.org/papers/rss` → 301 → `www2.nber.org/papers/rss` → 404 (dead redirect target); `nber.org/rss/new.xml` → 301 → `back.nber.org/rss/new.xml` → **200, confirmed**, fields verified by reading two live items ("Inference for Regression with Clustered or Spatially Correlated Data I/II," Cameron & Miller). Same shape as the Google News RSS lane already adopted. |
| **Perplexity API** | API key, paid | **Sonar** $1/$1 per 1M input/output tokens + $5-12 per 1,000 requests (search-context-size dependent); **Sonar Pro** $3/$15 per 1M + $6-14/1,000; **Sonar Reasoning Pro** / **Sonar Deep Research** priced similarly, Deep Research separately bills citation tokens $2/1M, reasoning tokens $3/1M, search queries $5/1,000. **No free tier** (fetched, `docs.perplexity.ai/getting-started/pricing`). | n/a (no free tier) | AI-synthesized answer with citations (web-grounded), not a raw citation database | not fetched this session | **Needs an owner decision before any code.** A second paid LLM provider directly conflicts with CLAUDE.md's "DeepSeek is the ONLY LLM provider, and it is the only one." |
| **Consensus API** | API key; self-serve, "available to everyone" per `consensus.app/home/api/` (fetched) | Free plan: **30 API/MCP calls per month** (per cross-source search, not independently fetched from Consensus's own pricing doc — `docs.consensus.app/api-get-started` was named but not fetched this session); paid plans 500 (Pro/Team/Enterprise) or 2,000 (Deep) credits/month; overage **$0.05/call + 1 credit per 100 papers**; one search source separately quotes "$0.10 per API call + platform fee" — **the two figures disagree and neither was independently reconciled this session** | per above | paper metadata: citation count, publish date, study design, journal rank, relevance-ranked top 20 results/query; **as of 2026-09-18, full text** beyond the abstract (methods/results/doses) per a search snippet, **not independently confirmed from a primary Consensus page this session** | not fetched this session | **ADOPT after owner decision**, even for the free 30-calls/month tier — it is a named signup (standing rule: no sign-ups without the owner naming the site), and the free quota is small enough that burning it accidentally is a real cost. |

### Patents / IP

| instrument | auth | cost | coverage | returns | OpenClaw callable |
|---|---|---|---|---|---|
| **USPTO PatentsView legacy API** (`search.patentsview.org`) | — | — | **RETIRED.** Per cross-corroborated search results (USPTO subscription-center bulletin, rOpenSci, r-bloggers — not independently fetched from uspto.gov directly this session, same "cross-source corroboration, direct fetch not completed" convention the research cards already use), the legacy API **(`api.patentsview.org`) died May 2025** and **`search.patentsview.org` itself shut down 2026-03-20**, migrated to the USPTO Open Data Portal. Previously-issued keys do not work on the new system. | — | **Dead — do not build against this URL.** |
| **USPTO Open Data Portal (ODP)** — the PatentsView replacement | API key; requires a **USPTO.gov account + a validated, linked ID.me identity-verification account** (`data.uspto.gov/apis/getting-started`, per search) | free | US patents: patent file wrapper, bulk data directory, full-text search | JSON via Swagger-documented endpoints | **ADOPT after owner decision.** Free, but ID.me is a real identity-verification step — a heavier ask than a plain email signup, and the standing rule on sign-ups (name the site, owner decides) applies with extra weight here. |
| **EPO Open Patent Services (OPS)** | OAuth2 consumer key/secret; free "Non-paying" registration at the EPO developer portal (per cross-corroborated search — EPO's own OPS page, fetched, returned nav-only with no body content, so this is **search-corroborated, not directly fetched**) | free tier: **~3.5-4 GB/week** fair-use traffic (two close figures across sources); paid "unlimited" tier is **€2,800/year** | global (INPADOC/EPODOC) — broader than USPTO ODP's US-only scope | bibliographic, legal-status, and full-text patent data | **ADOPT after owner decision.** Lighter signup than ID.me (a developer-portal account), still a named account the owner must approve. |
| **Google Patents** (patents.google.com) | — | — | — | — | **REFUSE** direct scraping — no official API exists for the public site; same ToS-scraping reasoning already applied to DuckDuckGo/Bing. |
| **Google Patents Public Datasets (BigQuery)** | GCP account | BigQuery's standard free monthly query tier applies (not independently re-verified this session — **both direct fetch attempts failed**: `cloud.google.com/bigquery/public-data/google-patents` → 301 → `docs.cloud.google.com/...` → 404; a second attempt threw a header-overflow parse error) | full text, citations, legal status, Google Patents Research Data (per the dataset's well-documented existence; **not independently confirmed this session** — flagged `UNVERIFIED`, same convention `docs/OUTSIDE_TOOLS_2026-10-07.md` uses for the Bloomberg licensing page) | — | **ADOPT after owner decision, UNVERIFIED.** A GCP project/billing account is itself a signup; the specific free-tier numbers need a working fetch before anyone commits to this path. |

### Open web / consumer AI / already-present tools

| instrument | verdict | reason |
|---|---|---|
| **SSRN** | **REFUSE.** No official API (confirmed by the absence of one anywhere in this search). `ssrn.com/robots.txt` **was fetched successfully** and is narrower than expected: it disallows `GPTBot`, `ChatGPT-User`, `Google-Extended` outright, and for all other user-agents only imposes `Crawl-Delay: 5` plus three disallowed paths (`/admin/`, `/tasks/`, `/config/`) — it does **not** disallow abstract/search pages for a generic crawler. But `ssrn.com/index.cfm/en/terms-of-use/` **returned HTTP 403** to a direct, read-only fetch — the ToS text itself could not be read this session. The REFUSE verdict rests on "no API + an unreadable ToS page + the project's standing posture toward publisher sites with no official access path," not on robots.txt, and that distinction should not be collapsed next time someone re-checks this. |
| **DuckDuckGo / Bing (direct scraping)** | **REFUSE**, reconfirmed, not re-tested. Already closed 2026-10-06 (`openclaw_open_web_and_model_audit_2026-10-06.md` §C: ToS/robots.txt violation, Bing serving a Cloudflare CAPTCHA on the exact query shape tried) and hardcoded into `backend/config.py`'s `QUERY_PLANNER_REFUSED_HOSTS` (`duckduckgo.com`, `bing.com`, `google.com`). |
| **Consumer AI chat UIs browsed as a page** (ChatGPT, Claude.ai, Gemini, Perplexity's own site, Consensus's own site) | **REFUSE**, reconfirmed. Already in `QUERY_PLANNER_REFUSED_HOSTS` (`chatgpt.com`, `openai.com`, `perplexity.ai`, `claude.ai`, `consensus.app`, `gemini.google.com`). This refuses *browsing to the page*; it does **not** refuse an official API/MCP integration with the same vendor — Perplexity's and Consensus's own APIs are separate rows above, with their own separate verdicts. |
| **Brave Search API** | **ADOPT after owner decision.** Reconfirmed this session (`brave.com/search/api/`, fetched): $5/month free credit auto-applied, **but a credit card is required even for the free tier**, "as an anti-fraud measure." This still conflicts with standing rule 1 ("no payments... ever") absent explicit authorization. Unchanged from the 2026-10-06 audit. |
| **Exa** (`mcp__exa__web_search_exa`, `mcp__exa__web_fetch_exa`) | **Already available to Claude Code/this session, not to OpenClaw.** OpenClaw's tool scope (`openclaw_tool_scope.py`, `GROUPS["group:web"]`) does not include an Exa entry; bridging it would be new engineering, not a config flip. Not probed for its own pricing this session (out of scope — the owner's brief asked only to note its availability-to-whom). Used today as a second, independent fetch path for the Semantic Scholar/arXiv probe retries — it failed too (`CRAWL_UNKNOWN_ERROR`, `CRAWL_LIVECRAWL_TIMEOUT`), for different reasons than `WebFetch`'s 429s, which is itself a small data point: both of today's fetch paths struggled with those two specific endpoints. |
| **Bigdata.com** (`mcp__claude_ai_Bigdata_com__*`) | **ADOPT after owner decision; wrong content class for "academic evidence."** Already connected in this Claude.ai account (confirmed via `bigdata_help`, a read-only call: no trial, **PAYG balance $0**). Content packages are financial/business (company sentiment, corporate calendar/communications/fundamentals, earnings transcripts, economic calendar, ESG scores, expert interviews, fund holdings, jobs, a knowledge graph, podcasts, premium news, regulatory filings, venture hub) plus an open-web search lane — this is RavenPack-sourced market/news/filings content, not an academic-citation database. It could support a *different* research-intake question ("has this mechanism been discussed in recent filings/transcripts/news") but not "find the literature." Any real call needs a top-up — a payment — which needs the same owner authorization as Brave. A separate, unauthenticated `plugin:bigdata-com` connector also exists in this environment and was not touched. |

---

## 2. Measurement design

### 2.1 The benchmark

For each of the five cards in `docs/research_intake/cards/`, the **seed citation set** is the
card's own verified `## Citation` list plus any paper explicitly named in its `## Known failure
modes` section (e.g., McLean & Pontiff 2016 as the standing decay reference). This is the "set of
citations a good literature review should find" the owner's brief asks for — it is deliberately
small and already fact-checked (each card states how its own citation was verified, including
403s and corroboration-not-direct-fetch where that happened), so an instrument's coverage against
it is a clean, cheap pass/fail rather than a new literature search in its own right.

| card | seed set (n) |
|---|---|
| `lou-polk-skouras-2019-overnight-intraday` | Lou, Polk & Skouras 2019 (JFE); McLean & Pontiff 2016 (JF) — cited as the standing decay reference, not independently re-verified for this mechanism |
| `post-earnings-announcement-drift` | Ball & Brown 1968 (JAR); Bernard & Thomas 1989 (JAR) |
| `analyst-revision-momentum` | Jegadeesh, Kim, Krische & Lee 2004 (JF); Gleason & Lee 2003 (*The Accounting Review*) |
| `monday-turnaround-effect` | Cross 1973 (FAJ); French 1980 (JFE); Lakonishok & Maberly 1990 (JF); Smith & Robins, "No More Weekend Effect" (*Critical Finance Review*, year unconfirmed) |
| `markowitz-1952-portfolio-selection` | Markowitz 1952 (JF); DeMiguel, Garlappi & Uppal 2009 (RFS) |

### 2.2 Metrics, per instrument per card

- **Coverage** = (seed citations the instrument's search surfaces in its top-5 results, matched
  by title/DOI) / (seed set size).
- **Novelty** = citations the instrument returns that are **not** in the seed set but are
  independently verifiable as directly on-mechanism (not merely co-occurring keywords) — the
  genuinely new thing a literature-search tool is supposed to find.
- **Quality** = each returned hit classified peer-reviewed-journal / working-paper-preprint
  (NBER, SSRN, arXiv) / blog-or-aggregator, from the instrument's own venue field.
- **Latency** = wall-clock per query; **report a hard failure (429, timeout, DNS error) as
  latency = N/A + the failure code**, never as 0 or omitted — a tool that cannot be reached is
  not "fast."
- **Cost** = $0 for the four free instruments probed; for paid ones, the published per-call rate
  from §1, never run live (per the task's own rule — no paid probes).

### 2.3 Receipt schema

```json
{
  "run_id": "<uuid or timestamp-slug>",
  "card_slug": "lou-polk-skouras-2019-overnight-intraday",
  "instrument": "openalex | crossref | semantic_scholar | arxiv | perplexity | consensus | ...",
  "query_text": "A Tug of War: Overnight versus Intraday Expected Returns",
  "seed_citations": ["10.1016/j.jfineco.2019.03.011", "..."],
  "found_dois": ["10.1016/j.jfineco.2019.03.011"],
  "coverage": 1.0,
  "novel_dois": ["10.2139/ssrn.5240716", "10.2139/ssrn.5247123"],
  "quality_breakdown": {"peer_reviewed": 1, "preprint": 2, "other": 0},
  "latency_s": 1.4,
  "http_status": 200,
  "cost_usd": 0.0,
  "timestamp_utc": "2026-10-07T..."
}
```

Path: `backend/data/optimus/research_instruments/probe_<run_id>.json` (not written this session
— this is a schema proposal, per the task's "define the benchmark," not a data pull).

### 2.4 The first row — Lou-Polk-Skouras 2019, run today, real numbers

| instrument | query sent | result | coverage (n=1, primary paper; McLean-Pontiff not queried) | novelty | quality | latency | cost |
|---|---|---|---|---|---|---|---|
| **OpenAlex** | `A Tug of War: Overnight versus Intraday Expected Returns` | **Found, rank 1 of 81.** `W2797315895`, *Journal of Financial Economics*, 2019, **346 citations** | **1/1** | 5 other hits returned, none in the seed set: a 2026 arXiv GARCH paper (0 cites), a 2017 *IJEF* paper (6 cites), a 2022 *Frontiers in Environmental Science* ESG paper (5 cites), a 2025 *Asian Finance Review* paper (0 cites), a 2024 *Frontiers* paper (0 cites) — plausible citing-literature, unvetted individually | primary = peer-reviewed; the 5 novel hits are mixed (1 preprint, 4 lower-tier journals) | fast, single fetch, no retry needed | $0 |
| **CrossRef** | `A Tug of War: Overnight versus Intraday Expected Returns` (bibliographic query) | **Found, rank 1** (of 1,260,094 loosely-matched results — the query was unconstrained free text, a precision caveat). DOI `10.1016/j.jfineco.2019.03.011` confirmed. `is-referenced-by-count` **319** — 27 fewer than OpenAlex's 346, an ~8% cross-index disagreement on the same metric | **1/1** | **Two 2025 SSRN preprints directly extending the tug-of-war framing** ("Day and Night Expected Returns Under Overnight Information Shocks: New Tug-of-War Pattern," `10.2139/ssrn.5240716` and `10.2139/ssrn.5247123`) — **the clearest novel find of this whole probe**, present in neither the card nor OpenAlex's result set | primary = peer-reviewed; both novel hits = SSRN working papers (preprint tier) | fast, single fetch, no retry needed | $0 |
| **Semantic Scholar** | same title, via `/graph/v1/paper/search` | **No result — HTTP 429 on both attempts** (one plain, one with explicit `fields=` param), several minutes apart | N/A | N/A | N/A | **failure, not latency**: 429 both times | $0 (nothing returned) |
| **arXiv** | `all:"overnight versus intraday"` and a broader variant | **No result — HTTP 429 via `WebFetch` on both attempts**; also failed via `mcp__exa__web_fetch_exa` on the same two URLs (`CRAWL_UNKNOWN_ERROR`, `CRAWL_LIVECRAWL_TIMEOUT`) — 4 failures, 2 independent fetch paths, 0 successes. Structurally, expected coverage would likely be 0 regardless: the paper's only venues per OpenAlex/CrossRef are the *JFE* and 2025-26 SSRN/arXiv follow-ons, not the 2019 original | N/A | N/A | N/A | **failure** | $0 |

**Reading it:** 2 of 4 free instruments answered on the first try, both found the exact paper, and
disagreed with each other on its own citation count by 8%. The two that failed did so identically
(429) across two unrelated fetch infrastructures, which is itself the finding — a keyless
Semantic Scholar/arXiv integration **cannot be trusted as a sole source** without either a free
API key (Semantic Scholar) or acceptance that arXiv's finance-journal coverage is thin by
construction. The single most useful result of the whole probe — two 2025 SSRN papers extending
the exact mechanism — came from CrossRef, the instrument with the least glamorous docs page.

---

## 3. The tool-selection rule for OpenClaw: "I am missing academic evidence"

### 3.1 Where it lives

Inside `backend/services/query_planner.py` (not a new top-level module), as a new lane next to
the existing `held_names` / `themes` / `opportunities` lanes — reusing the exact
**declared-provider gate** pattern C7/F1 already built for `QUERY_PLANNER_SEARCH_PROVIDER`:

- `QUERY_PLANNER_ACADEMIC_PROVIDERS = ("openalex", "crossref")` by default — **both are $0,
  keyless, and proven working this session**, so (unlike the general web-search lane) this one
  does not need to wait on an owner decision to do something.
- `QUERY_PLANNER_ACADEMIC_PROVIDERS_EXTENDED = ("semantic_scholar", "arxiv", "nber_rss")` —
  attempted only as a second pass, and only if the first pass's coverage is below the stop
  threshold (§3.3). Semantic Scholar's calls degrade gracefully (treat 429 as
  `TOOL_FIRED_BUT_UNAVAILABLE`, exactly the existing zero-kind vocabulary in
  `query_planner.py`'s yield block, never as a hard error).
- Paid instruments (Perplexity, Consensus beyond its free quota, Brave, Bigdata.com, any patent
  API requiring a signup) are **never auto-called**. Each is gated the same way
  `QUERY_PLANNER_SEARCH_PROVIDER = None` already gates the general web-search lane: a `None`/absent
  config value means the receipt says `NO_PROVIDER_DECLARED: owner decision`, and the planner
  falls back to the $0 tier instead of silently doing nothing.

The **caller** is the research-intake routine (`docs/research_intake/README.md`), not the planner
itself — same separation query_planner already has from the agent that decides *when* to search.
A card reaches verdict `NEEDS_EVIDENCE` (a new verdict value, alongside `READY_TO_CELL` /
`NEEDS_DATA` / `ALREADY_CLOSED` / `NOT_A_HYPOTHESIS_YET`) when the Sonnet writer cannot verify a
citation by direct fetch and corroboration alone within the card template's own rules. The routine
then calls the query-planner's academic lane with the paper's title as the query — never the
other way around.

### 3.2 Decision table: card verdict + topic class → instrument order

| topic class | 1st | 2nd | 3rd (owner-gated) |
|---|---|---|---|
| classical asset-pricing / accounting-finance journal mechanism (PEAD, momentum, weekend effect, revisions — i.e. 4 of this morning's 5 cards) | OpenAlex | CrossRef | Semantic Scholar (if a free key exists), else NBER RSS for a working-paper precursor check |
| quant/ML/LLM-finance preprint mechanism | arXiv | OpenAlex | Semantic Scholar |
| patent/IP-adjacent question ("is this execution mechanism patented") | USPTO ODP (US) | EPO OPS (global) | Google Patents BigQuery |
| "synthesize this for me, I don't want to read five papers" — triggered only when the deterministic tier above found >0 but conflicting or sparse results | — | — | Consensus (if free-quota remains this month) → Perplexity (only after an explicit owner decision to add a second paid LLM provider) |
| open-web/business corroboration (not academic) | — | — | Bigdata.com's `content-web` lane, only after an owner-approved top-up |

### 3.3 Budget per card and the stop rule

- **Default budget per card: 2 queries, $0** — one OpenAlex call, one CrossRef call. This mirrors
  the existing `QUERY_PLANNER_RUN_USD_CAP` shape (a hard ceiling that is cheap to set generously
  when the unit cost is zero).
- **Escalation to the extended tier (Semantic Scholar / arXiv / NBER RSS):** only if coverage
  (§2.2) from the default tier is below **0.8** of the card's seed set, capped at **+3 queries**.
- **Stop rule:** stop as soon as coverage reaches 1.0, OR two consecutive instruments return zero
  new citations (seed or novel), OR the extended-tier cap is hit — whichever comes first. The
  receipt (`research_instruments/probe_<run_id>.json`, §2.3) records which condition fired, same
  as `query_planner`'s own `zero_kind` vocabulary names which zero it hit.
- **A paid instrument is never reached by this stop rule.** It requires a separate, explicit
  owner-approved config flip (same `None`-means-no-call pattern as
  `QUERY_PLANNER_SEARCH_PROVIDER`), never an automatic escalation past the free tier.

---

## 4. Verdicts

| instrument | verdict | one-line reason |
|---|---|---|
| OpenAlex | **ADOPT now** | $0, keyless, CC0, confirmed working, broadest coverage |
| CrossRef | **ADOPT now** | $0, keyless, confirmed working, found the one novel result this session |
| NBER working-papers RSS | **ADOPT now** | $0, keyless, confirmed working (fetched and field-verified), same RSS shape already live |
| arXiv | **ADOPT now, narrow-scope** | $0, keyless, but real coverage is the quant/ML preprint class only — flagged, not a blanket win |
| Semantic Scholar | **ADOPT now, degrade gracefully** | $0 but unreliable keyless today (429 twice via two fetch paths); a free key is a cheap owner upgrade, not required to start |
| Perplexity API | **ADOPT after owner decision** | paid; a second LLM provider conflicts with "DeepSeek is the only provider" |
| Consensus API | **ADOPT after owner decision** | even the free 30/month tier is a named signup; paid pricing figures from two sources disagree and need reconciling before any commitment |
| Brave Search API | **ADOPT after owner decision** | card required even for the free credit; conflicts with "no payments... ever" absent authorization |
| Bigdata.com | **ADOPT after owner decision** | PAYG balance $0 (a top-up is a payment); also wrong content class (financial/business, not academic) for this specific question |
| USPTO Open Data Portal | **ADOPT after owner decision** | free, but needs a USPTO.gov + ID.me identity-verified account — heavier than a plain signup |
| EPO OPS | **ADOPT after owner decision** | free tier (~4 GB/week), but still a named developer-account signup |
| Google Patents BigQuery | **ADOPT after owner decision, UNVERIFIED** | needs a GCP account; this session's direct-fetch attempts both failed, so even the free-tier facts are unconfirmed |
| USPTO PatentsView legacy API | **REFUSE / DEAD** | shut down 2026-03-20; do not build against `search.patentsview.org` |
| Google Patents (direct scrape) | **REFUSE** | no official API; same ToS-scraping reasoning as DuckDuckGo/Bing |
| SSRN | **REFUSE** | no official API; ToS page itself 403'd to a read-only fetch this session |
| DuckDuckGo / Bing (direct scrape) | **REFUSE** | reconfirmed 2026-10-06; ToS/robots.txt + empirical CAPTCHA |
| Consumer AI chat UIs (browsed as a page) | **REFUSE** | reconfirmed; already hardcoded in `QUERY_PLANNER_REFUSED_HOSTS` — does not block a separate official API/MCP route |
| Exa | **note only — available to Claude Code, not OpenClaw** | bridging it into OpenClaw's tool scope would be new engineering, not evaluated here |

**The three to wire first: OpenAlex, CrossRef, NBER working-papers RSS.** All three are $0, need
no key, no card, and no owner sign-off to start. Two of three were proven working this session
with the exact query the owner's brief asked about; the third was fetched and its fields
confirmed live. Everything else on this page is gated on an owner decision (a payment, a named
signup, or an identity-verification step), not on engineering time — the same shape
`docs/OUTSIDE_TOOLS_2026-10-07.md` already reached for OpenBB, LEAN and BLPAPI the day before.

---

## Files and sources read or fetched this session

Repo: `docs/HANDOFF_2026-10-02_CLEAN_SESSION.md` §§1,3,4; `docs/research_notes/2026-10-06/
openclaw_open_web_and_model_audit_2026-10-06.md`; `docs/research_notes/2026-10-06/
query_planner_2026-10-06.md` §7; `docs/research_intake/README.md`; `docs/research_intake/cards/
lou-polk-skouras-2019-overnight-intraday.md` (full); `analyst-revision-momentum.md`,
`markowitz-1952-portfolio-selection.md`, `monday-turnaround-effect.md`,
`post-earnings-announcement-drift.md` (citations sections); `docs/OUTSIDE_TOOLS_2026-10-07.md`;
`docs/AEGIS_V1_BETA_2026-10-07.md` (D15); `backend/config.py` (`HYP_LAB_FAMILIES`, the
`QUERY_PLANNER_*` block); `backend/services/query_planner.py` (`classify_url`, the
declared-provider gate, the zero-kind vocabulary).

External, fetched this session: `api.semanticscholar.org/api-docs/` (docs, limited content);
`api.semanticscholar.org/graph/v1/paper/search` (probe, 429 x2); `help.openalex.org/how-to-use-
the-api/api-overview` (docs); `api.openalex.org/works?search=...` (probe, success);
`crossref.org/documentation/retrieve-metadata/rest-api/` (docs); `api.crossref.org/
works?query.bibliographic=...` (probe, success); `info.arxiv.org/help/api/basics.html` (docs);
`export.arxiv.org/api/query` (probe, 429 x2, + 2 Exa failures); `docs.perplexity.ai/getting-
started/pricing` (docs); `brave.com/search/api/` (docs); `nber.org/papers/rss` →
`www2.nber.org/papers/rss` (404) and `nber.org/rss/new.xml` → `back.nber.org/rss/new.xml`
(success); `search.patentsview.org/docs/` (DNS failure); `epo.org/en/searching-for-patents/data/
web-services/ops` (nav-only, no body); `ssrn.com/index.cfm/en/terms-of-use/` (403);
`ssrn.com/robots.txt` (success); `console.cloud.google.com/marketplace/...` (header-overflow
error) and `cloud.google.com/bigquery/public-data/google-patents` → `docs.cloud.google.com/...`
(404); `consensus.app/home/api/` (success). WebSearch: Consensus API pricing/availability;
PatentsView API key/rate-limit docs and shutdown status; SSRN ToS/robots.txt legal framing; EPO
OPS registration and fair-use limits; USPTO Open Data Portal getting-started. MCP: one read-only
`mcp__claude_ai_Bigdata_com__bigdata_help` call (subscription/balance status only).
