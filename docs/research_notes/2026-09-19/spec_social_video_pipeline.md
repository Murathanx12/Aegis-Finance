# BUILD SPEC — Social/Video/Earnings-Call Pipeline (2026-09-19)

Licence: **PRODUCT_EXPERIMENT** for everything below until a variable clears
its own pre-registration (§3). Read-only research note; no code shipped here.

## 0. What already exists — do not rebuild it

- `docs/research_notes/2026-09-11/research_social.md` — a 2026-09-11 web-search
  survey of retail-trading-strategy content (Reddit threads, Substacks, Discord
  sizes, hackathon posts, BTD literature, alt-data pricing). It is **evidence
  gathering about what other people claim**, not infrastructure. This spec does
  not repeat it; §5 below cites its BTD/WSB findings once, by reference.
- `backend/data/news_sources.yaml` **already has a `social_hypothesis` tier**
  (invariant 27, added the same day): `reddit_algotrading_rss`,
  `reddit_securityanalysis_rss`, `quantocracy_rss` — Reddit **post** RSS only
  (`.rss` = Atom, no key, `pit_grade: index_state`, `label_source: false`).
  Comments are NOT pulled by any existing source. YouTube, X, StockTwits,
  Instagram, Google Trends, and earnings-call transcripts have **zero** rows
  in the registry today.
- `scripts/news_pull.py` is the puller: registry-driven (`UnknownSource`
  refusal at parse), `RunContext` (budget_s, max_rows, resume, pacing),
  `FETCHERS: dict[parser_name -> fn]`, one JSONL/source/day under
  `backend/data/optimus/news_corpus/<source>/<date>.jsonl`, cursor +
  per-run receipt. **This is the pattern every new source below reuses** —
  either as a new registry row + new `fetch_*`/parser pair inside
  `news_pull.py` (RSS/Atom/simple JSON, no OAuth token refresh), or as a
  sibling script `scripts/social_pull.py` for sources whose auth shape
  (OAuth2 token refresh, paid metered calls) doesn't fit `RunContext.http_get`.
- `scripts/hiring_pull.py` (N-G) is the template for the **second** shape:
  a collector outside `news_pull.py` that still writes the same row contract
  and the same receipt/cursor discipline, built because Greenhouse/Lever/Ashby
  don't fit the RSS/Atom model. Its `--probe --dry-run` pattern (verify the
  live shape with ONE request before writing a parser) is mandatory for every
  new source below — three of `news_pull`'s five registry corrections
  (EDGAR's `getcurrent`, Nikkei's RDF, GDELT's real rate) came from doing
  exactly that on 2026-09-11.
- `backend/services/event_vocabulary.py` — the frozen 43-id typed-event
  vocabulary (39 substantive + `no_event` in V1, +3 analyst-action ids in
  V2). **There is no `supply_constraint` or `growth_constraint` id today.**
  Murat's ask ("find what's holding back their growth") needs a new id — see
  §3.4.
- `backend/services/event_extraction.py` — the LLM typing service.
  `wire_system()` reconstructs the literal system message sent to the model;
  the fix from **[a prompt that refers to a schema it never sends]**
  (`~/.claude/…/memory/feedback_a_prompt_that_refers_to_a_schema_it_never_sends.md`,
  2026-09-13) is already live here: DeepSeek refused 54% of a 1,200-row paid
  run because `SYSTEM_PROMPT` said "matching the schema you have been given"
  while the 43-id enum lived only in the validator, never on the wire. Every
  new prompt this spec proposes (§3.2) **must** put the literal enum string in
  the text the model receives and assert that in the fake reader before a paid
  run, exactly as `event_extraction` now does.
- `NEGATIVE_RESULTS.md` §12 (customer-momentum / supplier thesis: REJECTED at
  every holding period tested on 2004-2018 CRSP annual/monthly cadence;
  "revival requires event-conditioned links on daily data, registered fresh")
  and §19 (LLM/agent trading alpha comprehensively dead — Kim/Muhn/Nikolaev
  withdrawn, FINSABER kills the agent literature net of costs, Glasserman-Lin
  profitable only gross/daily-rebalanced/short-heavy and **anonymising
  tickers improved returns**). Both bind everything below: §3's supplier link
  is explicitly the daily, event-conditioned successor §12 asked for, and no
  variable in this spec may claim "the LLM found alpha" without rebutting all
  three §19 receipts by name (canon requirement, restated in CLAUDE.md's
  bottleneck section).

---

## 1. Source table

Legend: **Lawful** = ToS-compliant path exists without special partnership.
**PIT** = a `first_seen_utc` we can defend (we write it ourselves, at fetch
time, never trust a provider field — `news_pull.py`'s Rule 1).

| Source | Lawful? | Cost | Rate / quota | What text we get | PIT anchor |
|---|---|---|---|---|---|
| **YouTube Data API v3** — `search.list` + `videos.list` + `commentThreads.list` | Yes, official | Free: 10,000 quota units/day, no monetary charge. `search.list` = **100 units/call** (100 searches/day max on that call alone); `videos.list`/`commentThreads.list` ≈ 1-5 units/call. Paid tier does not exist — only a manual quota-extension form (weeks). | 10,000 units/day hard cap, resets midnight Pacific | video metadata (title, description, channel, publish time, view/like counts), top-level + reply comments (`commentThreads.list`, up to 100/page, paginated) | Yes — `publishedAt` on the video and on each comment is provider-set but is itself a first-class PIT anchor for THAT platform; we additionally stamp our own `first_seen_utc` at fetch time per Rule 1 |
| **youtube-transcript-api** (unofficial, PyPI `youtube-transcript-api`) | Grey — no ToS grant, works because YouTube's caption endpoint is unauthenticated | Free, but proxy required at any real volume | No official quota; **cloud-provider IPs (AWS/GCP/Azure) are actively blocked in 2026**, `RequestBlocked`/`IpBlocked` common; workaround is a rotating-residential-proxy service, $20-50/mo (Webshare cited as most reliable) | Auto-generated or uploaded caption text, timestamped per segment | No independent timestamp — transcript arrives with the video; `first_seen_utc` = our fetch time only, and the transcript itself carries no separate provenance |
| **Reddit API (OAuth, PRAW)** — posts AND comments | Yes, official, non-commercial free tier | Free for non-commercial; commercial use $0.24/1,000 calls, contract required | **100 queries/min per OAuth client** (official), ~60 qpm realistic ceiling reported for PRAW at scale, rolling 10-min window, `X-Ratelimit-Remaining` header | Full comment trees (`praw.models.Submission.comments.replace_more()`), post + comment text, score, author (pseudonymous), created_utc | Reddit's `created_utc` is provider-set and index_state (editable/deletable after posting — same reasoning as the existing registry rows), so `label_source` must stay `false`; our own `first_seen_utc` is the only defensible anchor, same as the three RSS rows already in the registry |
| **X/Twitter API** | Yes, official, but **no free self-serve tier survives 2026** | Pay-per-use is now the default for new developers (X retired Basic/Pro self-serve Feb 2026, forced remaining Basic subs onto pay-per-use Jun 2026, deprecated Pro Aug 2026): **$0.015/post written, $0.005/post read, capped 2M reads/mo**. Legacy Basic ($200/mo) / Pro ($5,000/mo) closed to new signups. Enterprise ~$42,000/mo. | metered, not rate-limited in the old sense — every read is billed | tweet text, author, timestamp, public metrics; replies fetchable but each reply is a billed read | provider `created_at` is index_state; same caveat as Reddit |
| **StockTwits public API** | Ambiguous — a public developer portal exists (`api.stocktwits.com/developers`) but the search found **no 2026 pricing/quota page**, several third-party wrappers are stale (last commits 2019-2021) | Unknown/likely free for the public symbol-stream endpoint historically, but current terms are not verifiable without registering an app — **flag as UNVERIFIED, verify with a live `--probe --dry-run` before building on it** | Unknown | Ticker-tagged posts, bull/bear sentiment tag set by the poster themselves (a usable stance label with NO local-model cost) | Unknown without a probe |
| **Instagram** | **No lawful path for this use case.** Graph API only reads accounts the app owns/manages (Business/Creator, Meta app review required); Basic Display API (read of a user's OWN content) reached end-of-life 2024-12-04; third-party scraping explicitly violates Instagram's ToS and carries GDPR/CCPA exposure on comment authors' personal data. | N/A | N/A | N/A | N/A — **state plainly: do not build an Instagram collector.** If Murat wants Instagram coverage, the only lawful route is a paid third-party aggregator (Phyllo, HikerAPI, etc.) whose own ToS and cost would need separate review; this spec does not recommend one. |
| **Google Trends via `pytrends`** | Grey, and **degraded**: `pytrends` was archived by its maintainer 2025-04-17 and 429s reliably on stale session handling; Google's OWN Trends API is a gated alpha (applied 2025-07-24, most applicants still waitlisted) | Free if it works | Undocumented, unpredictable 429s even at modest volume; needs cookie-session rotation + backoff to be usable at all | Relative search-interest index (0-100) per query per region/day — **not text**, a numeric series | N/A (it's already a number, not a document — see §2 mention-velocity note) |
| **SEC 8-K Exhibit 99.1 / 99.2** (earnings press release + prepared remarks, sometimes the full call script) | Yes, fully public, EDGAR fair-access limits only (~10 req/s) | Free | EDGAR fair-access rate, no daily cap | Full press-release text, sometimes prepared-remarks script; **not the Q&A** | `news_pull.py` already has `sec_edgar_8k_current_atom` (parser `edgar_atom`) in the registry at tier 1 — the feed exists, the exhibit BODY fetch does not yet (feed gives filing metadata + link, not exhibit text) |
| **Company IR pages** (per-company investor-relations transcript PDFs) | Yes, publisher's own site, page ToS varies (usually silent on scraping of public IR pages) | Free | No universal rate; per-domain, must be paced per `news_pull` discipline (`min_interval_s`) | Full transcript, sometimes Q&A, format varies wildly (PDF, HTML, embedded player) | We stamp `first_seen_utc`; published date usually stated on the page (native_stamp candidate IF the page shows a filing-grade date, case-by-case) |
| **Motley Fool `fool.com/earnings/call-transcripts/`** | **Grey.** Search found no explicit ToS clause on scraping; MULTIPLE existing scrapers and a public Kaggle dataset (18,755 transcripts) exist, which is evidence of practice, not of permission. Fool's own robots.txt / ToS must be read directly (this note did not fetch and read Fool's ToS text — do that before building, don't infer from "other people scrape it") | Free if scraped; Apify-hosted scraper ~$X/1000 pages if paid | Self-imposed pacing only | Full transcript text (prepared remarks + Q&A), by ticker/quarter, back to 2007 | Fool publishes its own article date; still `index_state` (editable after publish) unless we stamp our own `first_seen_utc` |
| **`earningscall` Python package / EarningsCall API** | Yes, commercial API with a Python SDK | Free tier exists for `earningscalls.dev` browser reads (no signup); **programmatic API access requires a paid subscription**, tier pricing not found in this pass — verify at `earningscall.biz` before committing budget | Per plan | Full transcript text + audio, 5,000+ companies, slide decks | Provider-stamped call date; treat as `index_state` unless the provider's own ToS commits to immutability (unverified) |
| **Alpha Vantage earnings-call-transcript endpoint** | Yes, official | **Free-tier and the 75 req/min tier return placeholder/demo data on this endpoint** — full transcripts require the 600 or 1,200 req/min PREMIUM plans (paid, price not itemized in this pass) | plan-dependent | Full transcript, AI-generated sentiment already attached (their own, not ours) | provider-stamped |
| **Financial Modeling Prep (FMP) transcript endpoints** | Yes, official | Free plan = 250 requests/day across ALL FMP endpoints, but **transcript endpoints are paid-plan-only** per FMP's own docs; exact transcript-tier price not itemized in this pass — verify at `site.financialmodelingprep.com/pricing-plans` | plan-dependent | Full transcript text, searchable by symbol+quarter | provider-stamped |

**Net read on earnings-call transcripts:** the only genuinely FREE, no-key,
no-ToS-ambiguity route is **SEC 8-K Exhibit 99.1/99.2**, and it gives the
press release / prepared remarks, not the Q&A — which is exactly where
Murat's "what's holding back growth" answers usually live (analysts ask the
constraint question directly). Getting the Q&A free-and-lawful likely means
company IR pages, checked one domain at a time, or accepting Motley Fool's
grey area after actually reading its ToS (not inferring from the existence of
scrapers). This is a real gap, not a solved one — flag it to Murat rather
than silently picking the grey option.

---

## 2. The measurable variables

Every variable below is a **precursor**, per `AEGIS_STRATEGIC_INVARIANTS.md`
point 2 — it must be computable from information available strictly before
the return window it is tested against, and it owes the "what would separate
this from ordinary factor beta" question before it counts as a hypothesis.

### 2.1 Mention velocity
**Definition:** for ticker *t*, day *d*: `count(mentions[t, d]) / rolling_mean(count(mentions[t, d-60:d-1]))`, computed separately per source (Reddit comments, YouTube comments, X posts) because pooling sources before this ratio is computed hides which platform moved. A mention is a row where `entities.resolve()` (the existing `news_entities` module, already used by `news_pull._row`) attaches ticker *t*.
**Null it must beat:** shuffled-ticker control — recompute the same ratio after randomly reassigning each mention's ticker label within the same day's mention pool (preserves aggregate volume, destroys the ticker-specific signal). If mention-velocity's forward-return IC is not distinguishable from the shuffled control's IC, velocity carries no ticker-specific information, only market-wide chatter volume.
**Second null (Glasserman-Lin form):** anonymise the ticker text itself before any LLM-touching step in the pipeline sees it (the §19 finding that de-anonymising IMPROVED the Glasserman-Lin strategy is a warning that named-company priors can be a *negative* distraction for a local model too) — this null is specifically for any variable that routes through §3.2's local-model summarizer, not for the pure-count velocity itself, which touches no LLM.

### 2.2 Comment stance dispersion ("debate" vs "consensus")
**Definition:** for ticker *t*, day *d*, over the comment set under all mentioning posts: score each comment's stance on {-1, 0, +1} (bearish/neutral/bullish) via the LOCAL model (§3.2 schema), then compute Shannon entropy of the stance distribution `H = -Σ p_i log(p_i)` over the three bins, OR the variance of a continuous stance score if the model returns one — **both must be computed and compared**, because entropy over 3 bins saturates fast (a 40/30/30 split reads as "high debate" the same as 34/33/33) while variance is sensitive to the actual spread of conviction. Report both on the receipt; the pre-reg names ONE as primary before data accrues (CANON §6 — cannot pick after seeing which one looks better).
Murat's framing translates directly: **high mention-velocity + LOW dispersion (stance consensus) = late** (everyone already agrees, "hype"); **high mention-velocity + HIGH dispersion = the debate is still open**, testable against forward return.
**Null it must beat:** the same entropy/variance computed on a comment set from a RANDOM day for the same ticker with matched mention-count (controls for "more comments mechanically raises apparent entropy" — a pure sample-size artifact must be ruled out before dispersion is read as information, the exact shape of [[check-whether-the-noise-is-shared]] in memory).

### 2.3 Hype-lateness
**Definition:** `percentile_rank(mention_velocity[t,d], cross_sectional_universe_on_d)` vs the trailing 20-day return of *t* as of *d*. The hypothesis (Murat's own words) is that mention velocity and TRAILING return are positively correlated at high percentiles ("if everyone's hyping it, you might already be late") — i.e. mention velocity is a lagging, not leading, indicator once it's already extreme, and forward return conditional on {high velocity, high trailing return, LOW dispersion} should be the worst cell, not the best.
**Null it must beat:** the WSB "dumb money" finding already in the 09-11 note (ScienceDirect: positions opened at peak WSB attention realize -8.5% HPR vs positive average HPR) is the LITERATURE's version of exactly this null — our own mention-velocity signal must be shown to differ from a generic "high attention = late" effect that's already published, or it adds nothing (the "what would separate this from ordinary factor beta" test from the invariants file, applied literally: peak-attention underperformance IS the ordinary-beta explanation here).

### 2.4 CEO-constraint mentions from earnings calls
**Definition:** a NEW typed-event id (working name `growth_constraint_cited`, see §3.4 — does not exist in the 43-id vocabulary today) fired when a transcript passage names a specific input, capacity, or resource limiting near-term growth (labor, chips, power, a named supplier, regulatory approval, capital). The typed row carries `named_input` (free text, e.g. "HBM supply", "grid interconnection capacity", "H100 allocation") in addition to the standard `event_type, direction, magnitude_bucket, confidence, evidence_span`.
**Null it must beat:** a constraint mention correlated with the SAME earnings call's overall tone (i.e., every earnings call that already beat/missed talks about SOMETHING as a constraint — the null is that `growth_constraint_cited` predicts nothing beyond what `earnings_report` direction/magnitude already predicts for the SAME company). Test: does the constrained-input's SUPPLIER (§2.5) move on a day the constraint is FIRST mentioned, controlling for the reporting company's own earnings-day return? If the supplier move is fully explained by co-movement with the reporting company, there's no separable signal.

### 2.5 Supplier link (from 10-K Item 1 / earnings transcripts)
**Definition:** given a `growth_constraint_cited` event naming input *X* for company *A* on day *d*, and a graph edge `A -> supplier(X)` sourced from 10-K Item 1 "principal suppliers" disclosure or transcript text ("we source X from B"), compute the SAME-DAY or next-session abnormal return of `supplier(X)` relative to its sector, at DAILY resolution.
**This is explicitly the successor NEGATIVE_RESULTS.md §12 asked for.** §12's verdict: "there is no holding period at which supply-chain links pay retail-accessible costs on 2004-2018 CRSP [monthly/annual cadence]... revival requires event-conditioned links on daily data, registered fresh." This variable IS that — event-conditioned (fires only on a `growth_constraint_cited` event, not a static annual link), daily resolution. It must be registered as a NEW trial under `docs/TRIALS/`, not treated as a re-run of §12 (the `pre-register-trial` skill's corpse-check would classify a same-mechanism-different-instrument attempt as `RESURRECTION`, which is allowed but must name the changed instrument explicitly — daily event-conditioning is that instrument).
**Null it must beat:** same-sector, non-supplier-linked matched control (a company in the SAME industry as the named supplier, with no disclosed link to *A*) — isolates whether the effect is "supplier-specific information" or "the whole sector moves when a mega-cap customer talks about the sector's inputs" (the mega-cap-as-sensor framing from `AEGIS_STRATEGIC_INVARIANTS.md`: the constraint mention is a SENSOR reading, the tradeable question is whether the SPECIFIC named supplier is mispriced relative to sector-mates that would benefit equally from the same macro read).

---

## 3. Pipeline

### 3.1 Fetch
| New source | Where it lives | Why |
|---|---|---|
| YouTube search + comments, StockTwits (after probe), Reddit COMMENTS (posts already covered) | new registry rows in `backend/data/news_sources.yaml`, tier `social_hypothesis`, new `parser`/`fetch_*` pair added to `news_pull.py`'s `FETCHERS` dict | Same auth shape as existing `alpaca_news`/`yfinance_news` rows — API key or none, single HTTP call per page, fits `RunContext` |
| SEC 8-K exhibit BODY fetch (the feed already exists; the exhibit text does not) | extend `fetch_edgar` in `news_pull.py`, OR a new parser keyed off `edgar_atom`'s existing links | Reuses the already-registered `sec_edgar_8k_current_atom` row; only the body-fetch step is new |
| X/Twitter (metered), earnings-call transcript vendors (FMP/AlphaVantage/earningscall, paid) | **new `scripts/social_pull.py`**, hiring_pull.py's shape (probe-first, `--dry-run`, own cursor/receipt), NOT inside `news_pull.py` | OAuth2/metered-billing auth doesn't fit `RunContext.http_get`'s bearer-token-or-none model cleanly, and per-call cost means every run must print $ spent on the receipt — `news_pull`'s receipt has no cost field today because every existing source is free |
| youtube-transcript-api | called FROM the YouTube fetch step (video discovered via `search.list`, transcript pulled via the unofficial lib) — needs its own failure class (`TranscriptUnavailable`/`IpBlocked`) distinct from a dead feed, or two-in-a-row zero rows (news_pull's dead-feed rule) will wrongly flag YouTube as down when it's actually the transcript step that's blocked | |
| Instagram | **not built** — see §1 | |

Every new source row MUST pass `news_registry`'s validation (all `REQUIRED_FIELDS`, `pit_grade` correctly set — **comments and posts are `index_state`, `label_source: false`, exactly like the three existing Reddit/Quantocracy rows**, because a platform can delete/edit a comment after posting and we have no way to detect a backfill).

### 3.2 Store
Append-only JSONL under `backend/data/optimus/social/<source>/<YYYY-MM-DD>.jsonl`, same row shape as `news_pull`'s corpus row PLUS social-specific fields:
```
{source, first_seen_utc, published_utc, tz_source, url, title, body, lang,
 tickers[], entity_tags[], raw_id, pit_grade,
 # social-specific:
 platform_id, author_pseudonym, parent_id (thread structure for comments),
 engagement {likes, replies, upvotes} as-of first_seen_utc ONLY (never
 re-fetched and overwritten — engagement AT FIRST SEEN is the PIT-honest
 number; a later-fetched engagement count is itself a look-ahead)}
```
Cursor + receipt per source per run, identical contract to `news_pull.py`.

### 3.3 Summarize with the local model
Per `backend/services/llama_server.py` (already the lab's local-model server: `start()`/`stop()`/`health_ok()`/`status()`, port-owned via PID, VRAM-tracked). The summarization step is a NEW consumer of this same server, run inside `always_on_lab.py`'s loop machinery (§4), NOT a new always-running process.

**JSON schema (stance + dispersion inputs), mirroring `event_extraction`'s pattern exactly:**
```json
{
  "$id": "aegis://schemas/social_stance_row.json",
  "type": "object",
  "properties": {
    "stance": {"type": "integer", "enum": [-1, 0, 1]},
    "stance_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "constraint_mentioned": {"type": "string"},
    "evidence_span": {"type": "string"}
  },
  "required": ["stance", "stance_confidence"]
}
```
**The enum MUST be in the literal system-prompt text sent to the model**, not only in this schema object — this is the exact lesson from
`feedback_a_prompt_that_refers_to_a_schema_it_never_sends.md` (2026-09-13):
`event_extraction.SYSTEM_PROMPT` once said "matching the schema you have been
given" with the 43-id enum living only in `SCHEMA`, and DeepSeek refused 54%
of a paid run answering with an invented id never shown to it. `event_extraction.wire_system()` is the pattern to copy: a function that
reconstructs and returns the EXACT string sent, so a test (and a human,
before the first paid run) can assert the enum is IN it. Before any paid run
on this pipeline: read the first flush, print `model`, stop on any refusal
class above a few percent — the same procedure the memory note prescribes.

For `growth_constraint_cited` (§2.4/§3.4), reuse `event_extraction.py`'s
existing machinery directly (it already has `wire_system()`, `_hand_errors`
validation, `validator_in_use()`) rather than writing a parallel typing
service — the new id just needs adding to `event_vocabulary.VOCABULARY_V2`
(or a new `_V3_ADDED`, since V1 is explicitly frozen and V2 already exists)
and the hash bumps, which is by design (§3.4).

### 3.4 New vocabulary id
`event_vocabulary.py` is explicit that V1 is FROZEN and new types go in a
later `_V2_ADDED`-style tuple (V2 already added 3 analyst-action ids). This
spec proposes a **V3 addition**: `growth_constraint_cited` — "Management
names a specific input, capacity, or resource limiting near-term growth
(labor, a component, power, regulatory approval, a named supplier)," with a
new `named_input` free-text field alongside the standard row. This is a
CODE CHANGE, not something this read-only note may make — flagged here as
the concrete next step, with the exact insertion point named
(`backend/services/event_vocabulary.py`, after `VOCABULARY_V2`'s definition,
mirroring `_V2_ADDED`'s pattern) so whoever picks this up doesn't have to
re-derive where it goes.

### 3.5 Join to `text_return_panel`
`scripts/night_e1_news_return_panel.py` is the existing joiner and its PIT
rule is the one to copy exactly: label off `published_utc` (here:
`first_seen_utc`, since social `pit_grade` is `index_state` and we do not
trust any provider timestamp), convert to America/New_York, enter at the
first regular-session open STRICTLY after the timestamp — publish one minute
into the session waits for the NEXT session's open. Two labels per row
(`r_oc`, `r_oo`), each net of SPY over the identical window (an equal-weight
average of mentioning names against nothing is a reading of market
direction, not of the signal — E1's own stated reason for the SPY-relative
labels). A new joiner script (`night_e1b_social_return_panel.py`, or extend
E1 to accept a `--corpus-dir` flag pointing at `social/` instead of
`news_corpus/`) is the natural next step; this note does not write it.

### 3.6 Pre-registration
Each of the five §2 variables needs its OWN `docs/TRIALS/` entry before it
accrues evaluated data (CANON §6, the `pre-register-trial` skill). Run
`python scripts/lint_prereg.py TRIALS/PREREG_<NAME>.md` from `Aegis module`
first for each — §2.5 (supplier link) will very likely score `RESURRECTION`
against §12's closed thesis, which is allowed but the draft MUST name "daily
event-conditioned links" as the changed instrument per the skill's own
requirement, or the linter will not accept it as new.

---

## 4. The human steps

### 4.1 API keys Murat must create
| Key | Console URL | Notes |
|---|---|---|
| YouTube Data API v3 | `console.cloud.google.com/apis/library/youtube.googleapis.com` (enable on a GCP project, then `console.cloud.google.com/apis/credentials` for the API key) | Free, no card required for the 10,000-unit/day default |
| Reddit OAuth app (script type) | `www.reddit.com/prefs/apps` | Create a "script" app; yields `client_id`/`client_secret`; needs a descriptive `User-Agent` string per app policy |
| X/Twitter developer account + pay-per-use billing | `developer.x.com/en/portal/dashboard` | **Requires a billing method on file even for pay-per-use** — this is a real dollar commitment, not a free signup; recommend Murat set a hard monthly cap in the X billing console before any key is issued to a collector |
| StockTwits developer app | `api.stocktwits.com/developers` | Verify current terms live via `--probe --dry-run` before building anything on it — this spec could not confirm 2026 pricing/quota |
| FMP / Alpha Vantage / earningscall (only if the free SEC/IR-page route proves insufficient) | `site.financialmodelingprep.com`, `alphavantage.co/support/#api-key`, `earningscall.biz` | All paid for the transcript endpoint specifically; hold off until §1's free route (SEC 8-K + IR pages) is measured and found lacking |

### 4.2 Browser-profile logins
None of the above REQUIRE a logged-in browser profile for the API paths.
A logged-in profile would only be needed for: (a) StockTwits if its API
turns out to require session auth rather than a pure app key (unverified,
check on probe), (b) any Motley Fool scraping approach if the ToS review in
§1 concludes it's acceptable and rate-limited-enough to need session cookies
to avoid bot-detection — not recommended as a first build.

### 4.3 What runs in `always_on_lab.py`, at what cadence, at what cost
Current `LOOPS` tuple (`scripts/always_on_lab.py:86`) and its
`config.LAB_LOOP_PERIODS_MINUTES` / `LAB_LOOP_TIMEOUT_S`:

| existing loop | period | timeout |
|---|---|---|
| `news_pull` | 15 min | 900 s |
| `l2_typing` | 15 min | 900 s |
| `decision_vs_reality` | 60 min | 300 s |
| `catalyst_calendar` | 6 h | 300 s |
| `nn_lab` | 24 h | 4 h |
| `idle_gpu_queue` | 5 min (gated by `LAB_IDLE_MINUTES=20`) | 60 s |
| `thematic_streams` | 24 h | 600 s |
| `status` | 5 min | 60 s |

**Proposed new loop: `social_pull`.** Same slot as `news_pull` architecturally
— a 15-30 min cadence is defensible for free sources (YouTube search quota
alone caps daily searches at 100 anyway, so a tighter cadence just spends the
budget faster, not more usefully); the metered X/Twitter and paid-transcript
calls should NOT run on the lab's automatic cadence at all — gate them behind
an explicit CLI flag or a `MODEL_SERVER_HOLD`-style operator file, the same
pattern §CLAUDE.md's chunk-16a lesson used for the model-server: unattended
automatic spend on a metered API is the same failure class as the $448,555
unattended-fleet exposure already logged for 2026-09-18.

**`social_typing` loop** (comment stance scoring via the local model) belongs
in `LAB_MODEL_LOOPS` alongside `l2_typing`/`nn_lab`/`idle_gpu_queue` — it
needs the model server up, and `ensure_model_server()` already handles that
lifecycle.

**Dollar cost, honestly:** YouTube ($0), Reddit ($0 non-commercial), SEC/IR
pages ($0), StockTwits (verify), **X/Twitter is the one line item that costs
real money on every run** — at $0.005/read capped 2M reads/month, a lab loop
polling even a modest ticker-comment stream daily needs an explicit per-run
budget field on the receipt (the gap `news_pull`'s receipt has today, per
§3.1) so a runaway loop is visible in dollars, not just in row counts.

---

## 5. Honest section — what the literature says, and what would make ours different

**Net-of-cost social-media alpha is not an established result; several
well-cited papers explicitly find the opposite of "just follow the crowd."**

1. **Cookson & Niessner, "Why Don't We Agree? Evidence from a Social Network
   of Investors"** (*Journal of Finance* 75(1), 2020, StockTwits data):
   disagreement is roughly evenly split between different information sets
   vs different investing philosophies, and WITHIN-group (same-philosophy)
   disagreement drives 2.5-4x the trading volume that CROSS-group
   disagreement does. This is the closest existing academic instrument to
   Murat's "debate = opportunity" intuition, and it measures disagreement's
   relationship to VOLUME, not directly to forward RETURN — our §2.2 variable
   must close that gap itself, not assume Cookson-Niessner already did.
2. **The WSB "dumb money" finding** (ScienceDirect, cited in the 09-11 note):
   positions opened at PEAK WSB attention realize -8.5% holding-period
   return vs a positive average — direct literature-level evidence for §2.3's
   null (peak attention often mean-reverts, doesn't continue).
3. **Glasserman & Lin** (arXiv 2309.17322, already in NEGATIVE_RESULTS §19):
   a GPT headline-sentiment long-short was profitable ONLY gross,
   daily-rebalanced, short-heavy, and self-described by the authors as "not
   a feasible strategy" — and anonymising the ticker text IMPROVED returns,
   meaning the model's own company-name knowledge was a NEGATIVE distraction.
   Directly relevant to §3.2/3.3: our local-model stance scorer should be
   tested BOTH with and without the ticker/company name visible to the model,
   as its own ablation, before trusting a stance score that names the company.
4. **FINSABER** (arXiv 2505.07078, KDD 2026, also in §19): multi-agent LLM
   trading frameworks (FinMem, FinAgent, FINCON) lose their edge over
   2004-2024 across 100+ symbols after commissions; the favorable prior
   literature rests on a ~6-month 2022-23 window and hand-picked large caps.
   Directly warns against building this pipeline's evaluation on a short,
   favorable-regime window.
5. **The withdrawn Kim/Muhn/Nikolaev paper** ("GPT-4 beats analysts at
   earnings direction," arXiv 2407.17866, withdrawn 2025-02-20 after the
   authors' own replication found inconsistencies) — the cautionary example
   for §2.4/§2.5: a plausible-sounding LLM-reads-earnings-calls result failed
   INTERNAL replication within 7 months. Any headline number this pipeline
   produces needs the same self-replication discipline before it is trusted.

**What would make ours different, concretely (not just asserted):**
- **PIT timestamps we write ourselves** (`first_seen_utc`), never a
  provider's editable field — none of the cited papers' data pipelines are
  described with this discipline, and it's the single most common way a
  social-media backtest quietly leaks the future (a WSB post's visible
  upvote count TODAY is not what it was at post time).
- **Comment DISPERSION, not just mention count or aggregate sentiment** —
  Cookson-Niessner measures disagreement vs volume; nobody cited here tests
  dispersion vs FORWARD RETURN directly, which is exactly §2.2/§2.3's
  contribution if it survives its nulls.
- **Twin controls at every step** (shuffled-ticker, matched-day,
  same-sector-non-supplier, Glasserman-Lin-style anonymisation) rather than a
  single headline correlation — per CLAUDE.md's "study losers as hard as
  winners" and "a null owes two tests" standing rules.
- **Event-conditioned supplier links at daily resolution**, the specific gap
  NEGATIVE_RESULTS §12 named as the only route back to a supplier thesis,
  rather than the static-graph-at-annual-cadence approach that's already
  dead.

None of this is evidence the pipeline WILL find something — it is evidence
the design, if built, would fail differently than the five citations above,
which is the bar this repo's licence structure (§ PRODUCT_EXPERIMENT) asks
for before a single decision leans on it.
