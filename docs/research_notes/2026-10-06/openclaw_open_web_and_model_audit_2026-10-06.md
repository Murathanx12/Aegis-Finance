# OpenClaw model audit, yield, and the open-web research personality (2026-10-06)

**Role: Sonnet researcher, read-only.** Nothing in this note was executed against a live
browser, no file was written outside this note, no secret is reproduced (the gateway auth
token and all API key values in `~/.openclaw/openclaw.json` and `.env` were read and are
withheld). Every Python snippet below was a local, offline read of jsonl/json receipts or a
pure function already in the repo (`reader_report.pages_read_since`/`lane_report`, both
documented "files only; no network, no LLM"). Two `WebSearch` calls were used, for the ToS/
robots.txt facts in §C only — OpenClaw itself was never invoked.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT (money) | **NONE.** This is an audit + a design, not a strategy result |
| OpenClaw's own LLM spend, Sept 25-29 | **$9.61** priced over 687 calls (646 OK), all `deepseek-flash` |
| OpenClaw's own LLM spend, Oct 1-6 | **$0.00 / 0 calls** — nothing has called `OC.agent()` since 2026-09-29 23:36 UTC |
| Reader (browser) activity, last 7 days | 9,368 page loads, 9,022 OK (96.3%) |
| Yield chain, last 7 days | 9,368 pages → **238 claims** → **3,587 forecast rows** |
| `dowjones_feeds` receipt | STALE — last generated 2026-09-27 14:01 UTC (**9.1 days**); root cause below is a missing scheduled caller, not a dead reader |
| Owner designs already on file, unbuilt | sign-in/sign-up (`browser_signin_signup_design_2026-09-29.md`), OpenClaw strategy-discovery queries (`research_openclaw_strategy_discovery.md`) |

---

## A. Model / provider / spend audit, with file:line evidence

OpenClaw touches Aegis through **three structurally separate doors**, each with a different
model and a different telemetry fate. Conflating them is what made "what model is OpenClaw
using" hard to answer before this audit.

| door | caller(s) | model | telemetry | file:line |
|---|---|---|---|---|
| **1. Browser-driving LLM turns** (`OC.agent()`, the only door that runs an actual model inside OpenClaw) | `scripts/night_investigator_forecast.py`, `scripts/source_reads.py`, `scripts/thesis_cards.py`, `scripts/openclaw_collector.py`, `backend/services/fast_mover_forensics.py` | `deepseek/deepseek-v4-pro` (the wrapper's default) or `deepseek/deepseek-flash` (every actual caller overrides to flash) — **never** the local `aegis-local` provider | Written as its own ledger row, `agent="openclaw"`, into the **same** `llm_calls_<month>.jsonl` `llm_telemetry` writes for every other caller | `backend/services/openclaw_client.py:1680` (`def agent(..., model: str = "deepseek/deepseek-v4-pro", ...)`); `backend/services/openclaw_client.py:1833` (`_record_telemetry`, `provider="deepseek"`); callers: `scripts/night_investigator_forecast.py:128` (`MODEL = "deepseek/deepseek-flash"`), `scripts/source_reads.py:150` (`model: str = SOURCE_READS_MODEL`), `backend/config.py:4215` (`THESIS_CARD_MODEL = "deepseek/deepseek-flash"`) |
| **2. Browser-driving deterministic verbs** (`OC.browser()`/`read_text()`, no model at all) | `backend/services/web_reader.py`, `scripts/dowjones_pull.py`, `scripts/reader_pool.py`, `scripts/social_browser_pull.py` | **none** — `web_reader.py:3-4`: *"Verb route only ... never `openclaw_client.agent`. No model decides where the browser goes"* | Not an LLM call; counted in `dowjones/budget_lanes.jsonl` page loads, $0 | `backend/services/web_reader.py:3` |
| **3. The extraction/digest model** (never touches OpenClaw at all — it is Aegis calling DeepSeek directly) | `backend/services/world_digest.py` via `llm_analyzer.call_named("deepseek", ...)` | `deepseek-chat`/`deepseek-flash` depending on stage | Written directly by `llm_analyzer`/`llm_telemetry`, `agent=None`, into the same ledger | `backend/services/world_digest.py:616-619` (`res = LA.call_named("deepseek", ...)`; `self._tl.model = "deepseek:" + served`) |

**The local provider exists but is dormant, confirmed two ways.** `~/.openclaw/openclaw.json`
declares `models.providers.aegis-local` — `baseUrl http://127.0.0.1:8080/v1`, launching
`llama-server.exe` on `Qwen2.5-7B-Instruct-Q4_K_M.gguf`. No caller anywhere in `backend/` or
`scripts/` passes a model string referencing `aegis-local` or `Qwen2.5` to `OC.agent()`
(`grep -rn "aegis-local" backend scripts` outside `__pycache__` returns zero hits). Separately,
`backend/config.py:4940` — `WORLD_DIGEST_LOCAL_EXTRACT = False` — is Aegis's **own** local-model
path (`backend/services/world_digest.py:654-727`, `local_event_stage`), which if ever turned on
would call a locally-hosted model through `BOOK_FACTORY_LOCAL_LLM_URL = "http://127.0.0.1:8080"`
(`backend/config.py:4200`) **directly**, bypassing OpenClaw's own `aegis-local` provider entry
entirely. The two "local Qwen on :8080" references are two different, independently-dormant
code paths, not one feature half-wired.

**`llm_usage()` does NOT see OpenClaw's spend.** `backend/services/llm_analyzer.py:187`
(`llm_usage()`) reports an **in-memory, per-process** counter (`_spend_state`) scoped to calls
that go through `llm_analyzer.call`/`call_named`. `openclaw_client.agent()` never calls
`llm_analyzer` — it writes straight to `llm_telemetry.build_call`/`append`
(`openclaw_client.py:1833-1861`). So:
- a caller asking `llm_analyzer.llm_usage()` for "how much has OpenClaw spent today" gets a
  number that **structurally excludes** every OpenClaw dollar, silently;
- the correct read is `llm_telemetry.read_calls()`/`summary()` filtered on `agent="openclaw"`,
  or `scripts/llm_cost_audit.py`'s full-ledger sweep, which **does** include it (same file, same
  row shape, verified below).

**Verified from the ledger itself** (`backend/data/optimus/llm_calls_2026-09.jsonl`,
`llm_calls_2026-10.jsonl`, read-only `grep`/`python -c`):
- September 25-29: **687** rows with `"agent": "openclaw"`. Status: 646 `OK`, 37 `RC_NONZERO`,
  3 `TIMEOUT`, 1 `EMPTY_LOG`. Model: 100% `deepseek-flash`. Priced sum over the 647 rows that
  carried real `usage` tokens: **$9.60552369**. Purposes: `u_forecast` (467), `thesis_card_quest`
  (163), `source_read`/`source_discovery` (23), five `research_openclaw_strategy_discovery:q*`
  quests (the 2026-09-26 QuantConnect/Reddit/X discovery session, see §C), `fast_mover_forensics`
  (12 ticker reads).
- October 1-6 (through 23:21 local): **zero** rows with `"agent": "openclaw"` in
  `llm_calls_2026-10.jsonl` (26,757 rows total, all other agents). This matches the handoff's
  own "No sim session has run since `ad32603783de` (09-29)" and the Railway trading-loop
  shutdown — the LLM-driven OpenClaw door has simply not been opened in six days, not because
  it is broken.

**The digest's `$0.00` balance-delta is explained in code, not a defect.** Every
`world_digest_<stamp>.json` receipt carries a `balance` block
(`backend/services/world_digest.py:1475-1477`): `before`/`after`/`delta_all_processes`, printed
with the comment *"the balance moves with every process on the key, not only this one."* Read
across 19 receipts from 2026-10-01 to 2026-10-06, `spend.spent_usd` ranges $0.013-$0.192 per run
(186 calls × ~$0.0004 each on 2026-10-06T11:16) while `balance.delta_all_processes` is `0.0` or
`None` in every single one — because the shared DeepSeek balance only moves in whole-cent steps
visible against the *account's* traffic, not one digest run's $0.07. The per-run ledger row
(`llm_calls_<month>.jsonl`) is the correct per-run figure; the balance block is a coarse
account-level sanity check, by design, and the code already says so. The 2026-09-22-era finding
that "digest receipts recorded $0.00 while the provider balance fell $2.55" is **not reproduced**
today in the sense that mattered: the ledger rows ARE non-zero and ARE the right number; the
balance-delta column being 0.0 is expected behavior given shared-key accounting, not a hidden
spend.

---

## B. The 7-day yield, and the `dowjones_feeds` root cause

**Reader activity** (`reader_report.lane_report`, pure file read, 2026-09-29T15:52 →
2026-10-06T15:52 UTC): **9,368 browser page loads, 9,022 OK (96.3%)**. By lane: markets_news
2,604, macro_world 1,590, book_names 1,493, social 1,030, universe_names 946, politics_policy
736, digest_asks 535, official_releases 385. By host: wsj.com 1,784, marketwatch.com 1,769,
barrons.com 1,408, cnbc.com 590, x.com 435, reddit.com 302, stocktwits.com 293, plus
nikkei/scmp/ft/bbc/yahoo/treasury.

**Claims and forecasts over the same window** (`backend/data/optimus/sources/claims.jsonl`,
`observed_utc`; `backend/data/optimus/predictions.jsonl`, `made_at`; both counted by a local
offline pass, no network): **238 new claims**, **3,587 new forecast (prediction) rows**. This
chain is alive and productive — the reader is not "a zero that is always zero" in the aggregate.
Most of today's `predictions.jsonl` rows are the deterministic `source_claim_v1` mechanism
(`model: "openclaw:source_read"`, but **not an LLM call** — `raw_probability` fixed at
0.5±0.10 by the claim's stated direction, `shrink_basis: "none: fixed ... by stated direction"`),
which is why it kept producing rows through the exact six days OpenClaw's own LLM door (§A) was
silent: claims → predictions here does not need an `agent()` turn at all.

**`dowjones_feeds` is genuinely stale, for a boring reason.** The receipt
(`backend/data/optimus/dowjones/feeds_2026-09-27.json`, `generated_utc`
`2026-09-27T14:01:31+00:00`) is written **only** by `python -m scripts.dowjones_pull --feeds`
(`backend/services/dowjones_feeds.py:111`, `pull_feeds`) — confirmed by `grep -rn "pull_feeds"`
across `backend/` and `scripts/`: the **only** call site is `scripts/dowjones_pull.py:2236`,
reached only from that script's own `--feeds` CLI branch. `scripts/night_reader_supervisor.py`
imports `dowjones_pull` for the reader pool and for `--claims`
(`scripts/night_reader_supervisor.py:412,439,547`) but never for `--feeds`; `grep` across
`night_reader_supervisor.py`, `daily_pass.py` and `always_on_lab` confirms no scheduled caller
exists for the `--feeds` branch. The command is manual-only and nobody has typed it since
2026-09-27 — nine days before this audit — so `system_health.p_dowjones_feeds`
(`backend/services/system_health.py:1455`, 1-day staleness window) correctly reports STALE. This
is the **"the remedy needs a scheduled caller"** pattern CLAUDE.md's funnel section already
names, recurring in a second place.

**This is not the same as "the reader is dead."** The ten feed IDs
(`wsj_markets`...`barrons_magazine`) are also ordinary `news_registry` rows pulled by the
generic `news_pull.pull_all()` cadence that *does* run continuously (the dowjones docstring says
so explicitly, `backend/services/dowjones_feeds.py:7-10`) — spot-checked: `mw_topstories` and
`barrons_magazine`'s raw corpus files (`backend/data/optimus/news_corpus/<id>/*.jsonl`) have
entries dated through **2026-10-06** (today), while `wsj_markets`'s file list jumps
`2026-09-26.jsonl` → `2026-10-05.jsonl` with a nine-day gap in between. So: the **summary
receipt** that feeds the health probe is stale because nobody re-runs `--feeds`; the
**underlying WSJ-specific corpus** also shows a real multi-day gap worth a second look (outside
this audit's scope); and `mw_topstories`/`barrons_magazine` are fine.

**A second, independent defect in the same receipt, worth flagging even though it predates the
9-day staleness:** both `feeds_2026-09-26.json` and `feeds_2026-09-27.json` report
`newest_age_h` of **~14,560-14,660 hours (≈607 days)** for `wsj_markets`, `wsj_business`,
`wsj_world`, `wsj_opinion`, `wsj_tech` — on the SAME day the pull reported `status: OK,
received: 20, new: 20`. Either WSJ's RSS genuinely re-serves evergreen/archive items with stale
`pubDate`s on those five feeds, or `_newest_published`'s date parsing
(`backend/services/dowjones_feeds.py:97-109`) is silently mis-reading one of the WSJ feeds'
`pubDate` formats. `mw_topstories`/`mw_bulletins`/`barrons_magazine` show plausible ages
(0.06-42 h) on the same runs, so the defect (if it is one) is specific to the WSJ-family parse,
not the DJ pipeline generally. Flag for whoever next regenerates the receipt — not fixed here
(read-only).

---

## C. Source-by-source assessment for "browses the whole internet"

Every row below either reuses a verdict this repo already reached (cited) or adds a fact found
this session (marked **new**).

| source | ToS/robots | login? | read-only feasible? | cost | expected yield | verdict |
|---|---|---|---|---|---|---|
| **Google News RSS** (`google_news_rss_en_us/en_hk/ja_jp/en_sg`) | publisher's own feed, plain HTTP | no | yes | $0 | already producing rows (`alerts_sources.py:54`, `world_digest.py:287`) | **ADOPT — already live**, not a new build |
| **DuckDuckGo HTML endpoint** (`html.duckduckgo.com`) | **new**: ToS prohibits automated/non-personal use; robots.txt disallows the `/html/?q=` scraping pattern; active anti-bot (403/202) | no | technically yes, lawfully no | $0 but ToS-violating | n/a | **REFUSE** as a direct scrape. (OpenClaw's own `web_search` tool, below, is the lawful substitute) |
| **Bing web search (HTML page)** | **new**: Microsoft Services Agreement bars automated querying/scraping of its services generally | no | technically yes, lawfully no | $0 but ToS-violating | n/a | **REFUSE** as a direct scrape — and already empirically dead-ended: the 2026-09-26 quest log recorded Bing serving a **Cloudflare CAPTCHA** on exactly this query shape (`research_openclaw_strategy_discovery.md` q5) |
| **OpenClaw's own `web_search`/`x_search` tools** | OpenClaw's own first-party feature, under its own agreement with its backing provider; not something Aegis scrapes | no | **yes, already policy-enforced** | counted inside the existing `agent()` call's DeepSeek token cost (no separate fee seen) | **0 quests run to date** — allowed but never invoked | **ADOPT — this is the lawful query-planner primitive**, not a new scraper (see §D) |
| **Brave Search API** | official API, ToS-clean | no (API key) | yes | **new, 2026-10-06**: free tier was removed Feb 2026; now $5/mo credit = 1,000 req/mo, card required, auto-bills past that | low volume unless paid | **DEFER** — needs a card on file, conflicts with "no payments, no billing actions" standing rule #1 unless the owner explicitly authorizes a $0-capped Brave account |
| **YouTube Data API v3 (metadata: search/videos)** | official API | no (API key, present in `.env` as `YOUTUBE_API_KEY`) | yes | free, 10,000 units/day | **already live**: `scripts/social_pull.py` `pull_youtube`, OK status, 12 new rows on last run (`backend/data/optimus/social/youtube_2026-10.jsonl`) | **ADOPT — already live** |
| **YouTube transcripts** | **new**: YouTube's robots.txt disallows `/watch` and `/timedtext*video` for all user-agents except declared search engines; ToS bars scraping outright; the official Data API's `captions.download` requires the video OWNER's OAuth grant, so it cannot fetch a third party's transcript lawfully at any price | would need the video owner's consent for the official route | **no**, by the project's own robots.txt-respecting precedent (same reasoning that already refused the Nasdaq earnings API and Senate eFD) | n/a | n/a | **REFUSE**, confirming the code that already exists: `scripts/social_pull.py` names this failure `TRANSCRIPT_SOURCE_NOT_LAWFUL_HERE` and `youtube-transcript-api` is logged as "grey... cloud-provider IPs actively blocked" (`docs/research_notes/2026-09-19/spec_social_video_pipeline.md:75`). `media_transcripts.py`'s page-native caption-track reader (`backend/services/media_transcripts.py:1-25`) is the more honest mechanism of the two, but it still requires loading `/watch`, which the same robots.txt disallows for an automated agent — the honest verdict stays REFUSE, pending an owner call, not an ADOPT dressed up as "more lawful" |
| **Reddit — official API (PRAW)** | needs owner-created app keys (`REDDIT_CLIENT_ID/SECRET/USER_AGENT`) | no (owner signs up once) | yes once keyed | free | `REDDIT_KEYS_ABSENT` today — **confirmed live**: `social/_receipt_20261002T100345Z.json` refuses with exactly this name | **DEFER — pending owner key creation** (two-minute task, see §E) |
| **Reddit — rendered browser read (old/new UI, no login)** | public page, no API; prior direct JSON/HTTP fetch to reddit.com was refused by Reddit's own network policy (403) | no | yes, via the browser verb route only | reader-budget page loads | **already live**: `web_reader.OPENCLAW_SOCIAL_HOSTS` includes `reddit.com`; 302 loads in the last 7 days (§B) | **ADOPT — already live.** `research_openclaw_strategy_discovery.md` §(c) already found direct HTTP to Reddit refused and only the rendered path working — current code already made the right call |
| **X (read-only)** | per standing rule, already an allowed host, never originates an order | no (OpenClaw's pinned `muratclaw` profile; a prior attempt via a *different* route — direct x.com navigation — hit a logged-out onboarding wall on 2026-09-26) | yes, within what the pinned profile's session permits | reader-budget page loads | **already live**: 435 `x.com` loads in the last 7 days (§B) | **ADOPT — already live**, with the caveat already on file: the `x_search` *tool* (inside an `agent()` turn) has never actually been tried and may succeed where direct x.com navigation failed before (see §D) |
| **Instagram** | **no lawful path for this use case** — login wall + ToS, already assessed | yes required | no | n/a | n/a | **REFUSE — already decided** (`scripts/social_pull.py:52,795`, `"instagram": "no lawful path for this use case (spec §1) — do not..."`) |
| **Consumer AI chat sites in a browser tab** (Perplexity, Consensus, ChatGPT, Claude.ai) | each site's ToS generally bars automated/non-personal use of its own chat UI; none of these is "the open web," it is another vendor's product surface | yes for most | no | n/a | n/a | **REFUSE** scraping the UI. If Perplexity/Consensus-style synthesis is wanted, the lawful path is their own paid API or an MCP connector the owner explicitly adds (several finance-research MCP connectors, e.g. Bigdata.com, are already available in this environment) — never a browser tab logged into a personal account |

---

## D. Build spec for an Opus builder

**Grounding fact that changes the shape of this build:** `~/.openclaw/openclaw.json`'s `main`
agent (the one every `OC.agent()` call runs on) already has `web_search`, `web_fetch`, and
`x_search` in its `alsoAllow` list, and `backend/services/openclaw_tool_scope.py` already
*enforces and audits* exactly this set as the read-only tool boundary (`GROUPS["group:web"]`,
`READ_TOOLS`, checked against each agent's SQLite transcript by `violations()`, run daily by
`system_health.p_openclaw_tool_scope`). **No quest log anywhere in this repo shows `web_search`
or `x_search` ever actually being invoked** (`grep -rln "x_search\|web_search"` over
`backend/data/optimus/*.jsonl` returns zero rows; the matches are all in research-note prose).
So the first build item is cheaper than "write a search engine": **ask the existing tool to
search**, inside a prompt, and read the tool-call transcript to confirm it fired.

1. **`query_planner` (new module, e.g. `backend/services/research_query_planner.py`)**
   - Input: today's `world_digest` themes/implications (`backend/data/optimus/digest/
     world_digest_<stamp>.json`, `themes`/`implications` keys — already written, pure read) +
     the current held-names list (`paper_accounts`/`fleet_manager` positions).
   - Step 1: deterministically template 3-8 search queries per cycle from (theme, held name)
     pairs — no LLM needed for the query text itself, to keep this auditable and cheap.
   - Step 2: one `OC.agent()` turn per query batch (reuse `openclaw_client.agent`, purpose
     `"query_planner:<theme>"`), with a prompt that explicitly instructs *"use the web_search
     tool, then report every URL found as a JSON list; do not browse"* — i.e. ask for the
     **tool**, not the page-opening skill that `research_openclaw_to_its_finest_scraper...md`
     §2.1 already diagnosed as the reason quests "sit idle" (the full snapshot→act→resnapshot
     loop is a *separate* skill the model may not pull in on a short, cheap prompt; asking only
     for a search-and-list avoids needing that skill at all).
   - Step 3: candidate URLs go through the **existing** source classifier
     (`backend/services/source_registry.py::score`, which already grades registered sources by
     forward-return skill/`forecast_reputation`) before being added to the reader queue — this
     reuses the house's own trust mechanism rather than inventing a second one.
   - Step 4: accepted URLs are handed to `web_reader.py`'s existing verb-route pipeline (door 2
     in §A) for the actual page read — never `agent()` again for the fetch itself, per the
     agent-vs-verb split §2.2 of the 2026-09-26 note already states.
   - **Yield receipt, every run, so a zero is visible** (the house rule this whole audit is
     built around): `{"queries_run": n, "tool_calls_web_search": n, "tool_calls_x_search": n,
     "candidate_urls": n, "accepted_by_classifier": n, "pages_read": n, "claims_written": n,
     "forecast_rows": n, "cost_usd": n}`. If `candidate_urls > 0` and `pages_read == 0`, or if
     `tool_calls_web_search == 0` on every run for N days, the receipt must say so loudly (same
     shape as `p_dowjones_feeds`'s staleness check in §B) — this is exactly the failure mode
     this audit found twice already (OpenClaw's agent door silent for 6 days; the feeds receipt
     silent for 9) and a third silent-zero should not need a fourth audit to surface it.
   - **First test, cheap and diagnostic, before building the rest:** one `OC.agent()` call with
     a prompt asking only "use web_search for `<a held name> news this week`, list the URLs you
     found" and read back the tool-call transcript. This answers, for ~$0.01, whether the
     `web_search`/`x_search` tools actually work from this config today — something no prior
     session has checked.

2. **YouTube transcript ingestion: REFUSE, per §C**, with the receipt already in code
   (`TRANSCRIPT_SOURCE_NOT_LAWFUL_HERE`). Nothing to build here beyond leaving the existing
   refusal alone. The metadata half (titles, channels, publish time, ticker mentions) is already
   adopted and running; a builder's only legitimate addition is widening `YOUTUBE_QUERIES`
   (`scripts/social_pull.py:137`) if the owner wants more topic coverage, which costs quota
   units, not a new capability.

3. **Consent-dismiss rule** (answers owner ask #4). Today `web_reader.py` has **no** cookie/GDPR
   consent handling at all (`grep -n -i "consent" backend/services/web_reader.py` returns one
   unrelated hit about Dow Jones data-licensing consent). The 2026-09-26 note already documents
   the verb shape that would do it: `snapshot --format ai --query "accept cookies consent"` →
   if a ref is returned, `click <ref>`. **Proposed rule, narrower than that note's generic
   pattern, so it cannot be mistaken for form-filling:**
   - A click is a "consent dismiss," not a form action, only when **all** of: (a) the ref was
     discovered by a `snapshot` call on the **current** page (never a fresh navigation to find
     one); (b) the ref's accessible text matches a fixed allowlist — "accept all", "accept
     cookies", "i agree", "agree and continue", "got it", "dismiss", "close" — case-insensitively,
     whole-phrase, not a substring match on a dangerous word; (c) the click does not navigate to
     a different host; (d) at most one consent click per page load, ever (a second "accept"
     button appearing after the first click is suspicious, not a nested banner, and should
     STOP). This is a strict subset of the sign-up design's own click-allowlist pattern
     (`browser_signin_signup_design_2026-09-29.md` §2.3) and should be pinned by an offline test
     the same way, before any live use.
   - Explicitly **not** a form field: a consent click never types, never focuses a text input,
     never touches a toggle/checkbox for "marketing preferences" (leave those un-clicked, per the
     sign-up design's own guard list §3).
   - Yield receipt: count of pages where a consent ref was found vs. clicked vs. a page that
     stayed blocked after the click attempt — a Yahoo page that is *still* unreadable after the
     "accept all" click is a new failure mode, not a success.

---

## E. Owner questions that must be answered before any sign-up or watchlist work

Everything here is **already designed, not built** (`browser_signin_signup_design_2026-09-29.md`,
status "NOT BUILT"). Per standing rule 6 (CLAUDE.md / handoff §4), nothing in this area moves
without the owner naming the sites. The exact questions:

1. **Which sites, by name, for a free newsletter/alert sign-up right now?** (Yahoo Finance
   alerts, MarketWatch watchlist alerts, Benzinga newsletter are the three the task names —
   the owner must confirm these three, or name different ones; "sign up for newsletters" alone
   is not a task record per the design's §2.1.)
2. **Confirm the account**: the MuratClaw Google account only, never the owner's personal one —
   does the owner want a *second* dedicated email/Google identity for research sign-ups, or
   reuse the MuratClaw one already used for Chrome?
3. **"Prepare, not submit" or full auto-submit?** The design's own recommendation (§5) is
   prepare-only: the agent fills name+email, screenshots, and hands the owner the tab for the
   final click. Does the owner want that, or full auto-submit within the guard list (§3)?
4. **Is a free sign-up ever worth it over the lawful alternatives already available without
   one** — RSS (already used for Google News, Dow Jones), official calendars (FRED/SEC/Fed/
   Federal Register, already wired per `WHAT_THE_READER_OPENS.md`), and Aegis-native watchlists
   the owner already has (localStorage portfolio + `alerts/` receipts)? For most of
   `vendor_tools_assessed_2026-09-29.md`'s free sources, a key comes from a one-time email form
   a human fills in two minutes — is the owner willing to spend those two minutes per site
   instead of building the sign-up agent at all, at least for the first few?
5. **Reddit**: will the owner create the free Reddit script-app keys
   (`www.reddit.com/prefs/apps`, two minutes, no payment) to unlock the official API path, given
   the rendered-browser path already works read-only today and the API would mainly add
   *comments* (not currently pulled) rather than new posts?
6. **Brave Search API**: now card-gated ($5/mo credit, 1,000 req/mo) since Feb 2026 — is this
   worth a card on file given standing rule 1 ("no payments... ever"), or should the research
   personality rely solely on OpenClaw's own `web_search`/`x_search` tools (§C/§D), which need
   no new account or card?

---

## Files read this session (for the record, no secrets quoted)

`CLAUDE.md`; `docs/HANDOFF_2026-10-02_CLEAN_SESSION.md` §§1,3,4; `docs/research_notes/2026-09-28/
openclaw_runtime_done_right_2026-09-28.md`; `docs/research_notes/2026-09-29/
browser_signin_signup_design_2026-09-29.md`; `docs/research_notes/2026-09-26/
research_openclaw_strategy_discovery.md`; `docs/research_notes/2026-09-26/
research_openclaw_to_its_finest_scraper_desktop_agent_and_optimus.md`; `docs/research_notes/
2026-09-19/spec_social_video_pipeline.md`; `backend/services/openclaw_client.py`;
`backend/services/openclaw_tool_scope.py`; `backend/services/openclaw_http.py`;
`backend/services/web_reader.py`; `backend/services/reader_report.py`;
`backend/services/dowjones_feeds.py`; `backend/services/world_digest.py`;
`backend/services/llm_analyzer.py`; `backend/services/media_transcripts.py`;
`backend/services/source_registry.py`; `scripts/social_pull.py`; `scripts/dowjones_pull.py`
(grep only); `scripts/night_reader_supervisor.py` (grep only); `backend/config.py` (grep only);
`~/.openclaw/openclaw.json` (read-only; token and API keys withheld); `.env` (grep for key
*names* only, values redacted); `backend/data/optimus/deepseek_balance.jsonl`;
`backend/data/optimus/digest/world_digest_*.json` (19 receipts, 2026-10-01 → 10-06);
`backend/data/optimus/llm_calls_2026-09.jsonl`, `llm_calls_2026-10.jsonl`;
`backend/data/optimus/dowjones/feeds_2026-09-26.json`, `feeds_2026-09-27.json`;
`backend/data/optimus/sources/claims.jsonl`; `backend/data/optimus/predictions.jsonl`;
`backend/data/optimus/social/_receipt_20261002T100345Z.json`,
`backend/data/optimus/social/youtube_2026-10.jsonl`. Two `WebSearch` calls (DuckDuckGo/Bing
ToS+robots.txt; YouTube robots.txt/ToS; Brave Search API pricing) are the only non-repo sources,
cited inline in §C.
