# The Dow Jones bundle (WSJ / Barron's / MarketWatch) — access, feeds, archives, gradeable columns, licence, competition use

Research only. No orders placed. LLM spend against the $0.50 OpenClaw budget: **$0.00** —
every check below used either plain HTTP (`curl`) or direct `openclaw browser` primitives
(`open`/`snapshot`/`tabs`/`profiles`), none of which call `openclaw_client.agent()` /
DeepSeek. No live paywalled full-text read was pushed past the point Murat flagged the
process/profile problem below.

## 0. Correction folded in mid-task — READ THIS FIRST

Two live corrections arrived while this note was being built; both are now reflected
throughout, not just here.

**Process check, as instructed.** Before/during/after the four `openclaw browser open`
calls below, non-child `chrome.exe` processes were:

```
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -notmatch '--type=' }
```

- **PID 96488**, created **2026-09-25 11:54:17 AM**, plain `chrome.exe` with no
  `--remote-debugging-port` / `--user-data-dir` flags — this is **Murat's own,
  already-open Chrome**, the one that (per his screenshot) carries the **"MuratClaw
  (Work)" Chrome profile**, signed into WSJ/Barron's/MarketWatch, with the jump list he
  described (WSJ Onboarding / Barron's Onboarding / Newsletters | Marketwatch / wsj.com /
  Home / X). **This process was never touched by anything in this note.** It stayed at
  exactly this one PID/creation-time the entire session.
- **PID 80512**, created **2026-09-26 9:35:33 PM** (local), `--remote-debugging-port=18801
  --user-data-dir=C:\Users\mrthn\.openclaw\browser\muratclaw\user-data` — this is
  **OpenClaw's own `muratclaw` CDP-managed profile**, launched by my first
  `openclaw_client.browser("open", ...)` call (the profile's `state` was `"stopped"`
  both immediately before that call, per `health()`, and immediately after the sequence
  ended, per `profiles()` — confirmed again with `curl http://127.0.0.1:18801/json/version`
  returning no listener once idle). It self-tore-down between calls; by the time I ran the
  process check a second time only PID 96488 remained.

So: **no extra Chrome window was left running**, and Murat's own signed-in browser was
never driven by anything here. But the four pages I opened (WSJ home, one WSJ article,
Barron's home, one Barron's article) went through the **wrong browser** — OpenClaw's own
`muratclaw` automation profile, which Murat has now confirmed is **not** signed into
Google/WSJ/Barron's/MarketWatch (Google sign-in refuses it) and never was. It is a
separate Chrome instance with its own empty cookie jar, not "the window he signed into."
The access-test results in §1 below are recorded as **what the managed `muratclaw`
profile sees** — i.e. the PAYWALL/no-login case — not as a test of Murat's real,
signed-in session. Per his instruction, no further live paywalled reads were pushed on
this profile after that was established, and the dated-archive and gradeable-column
checks in §3–§4 were done **unauthenticated over plain HTTP only** (all 401), not through
either browser.

The actual path to Murat's real session is the **OpenClaw Chrome extension relay**, which
is already partially set up — see §7.

## 1. Access test — the managed `muratclaw` OpenClaw profile (not Murat's signed-in Chrome)

`openclaw_client.health()` at 2026-09-26T13:28:44Z: `"verdict": "READY"`
(`gateway_probe_ok`: true, `profile_pinned`: true, `profile_detail`: `"stopped"`,
`messaging_channels`: 0). Not red, so the live part proceeded — onto the wrong browser,
per §0.

| Site | URL opened | Verdict | Evidence |
|---|---|---|---|
| wsj.com | `https://www.wsj.com/business/inflation-costs-diesel-port-trucks-1062d089` | **PAYWALL** | Header shows a `Sign In` link (not an account icon). Byline visible: "By Esther Fung, Laura Cooper and Costas Paris \| Photography by Aaron Agosto for WSJ", dated "Sept. 25, 2026 9:00 pm ET". First ~200 chars visible: *"It's costing more and more to get stuff in the hands of American shoppers. Trucking expenses are at their highest level since the Covid pandemic snarled operations around the world. Diesel prices are up 77% in the past year..."* — then a modal: **"Choose your WSJ subscription to keep reading"** with WSJ Digital / WSJ Bundle pricing tiles and a "Continue to Checkout" button. Unambiguous paywall.
| barrons.com | `https://www.barrons.com/articles/buy-brookfield-stock-price-pick-alternative-assets-energy-real-estate-85c714c1` | **UNVERIFIED** (not confirmed either way) | The snapshot text captured had no `Sign In` string and no subscription-upsell string, but a follow-up snapshot call on the same tab returned 0 bytes (the profile had already torn itself down — see §0) before I could capture the byline/body block. Given Murat's confirmation that this profile's Google sign-in is refused, treat this as **PAYWALL by inference**, not as a clean second confirmation.
| marketwatch.com | `https://www.marketwatch.com/story/how-to-keep-profiting-from-ai-while-shielding-your-portfolio-against-the-risk-of-a-slowdown-a5801291` | **UNVERIFIED** (leaning PAYWALL) | Snapshot showed byline "By Philip van Doorn", "Updated Sept. 26, 2026, 9:35 a.m. ET", headline/subhead, a "Referenced Symbols" block (SICWX, NVDA, GOOGL, MSFT, AAPL) — but the body paragraphs never rendered in the captured text before the profile's next call refused with `REFUSED_BROWSER_PROFILE_UNAVAILABLE` (the profile had cycled again). No explicit paywall banner was captured, but no article body was captured either. Same inference as Barron's applies.

**Bottom line: 1 of 3 sites confirmed PAYWALL with clean evidence; the other two are
consistent with "not signed in" (Murat's diagnosis) but weren't cleanly re-confirmed
before the live-browser part was paused per his instruction.** No quest ($) was spent on
any of this — all four opens were direct `browser()` calls, $0.

## 2. Free, PIT-clean RSS feeds — no login, plain HTTP, all fetched 2026-09-26 ~13:40–13:43 UTC

All fetched with `curl -A "Mozilla/5.0"`, no OpenClaw, no browser.

| Feed | URL | HTTP | Items | pubDate | guid | description |
|---|---|---|---:|---|---|---|
| WSJ Markets | `https://feeds.a.dj.com/rss/RSSMarketsMain.xml` | 200 | 20 | yes | yes (non-permalink) | yes, 1 sentence |
| WSJ US Business | `https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml` | 200 | 20 | yes | yes | yes |
| WSJ World News | `https://feeds.a.dj.com/rss/RSSWorldNews.xml` | 200 | 20 | yes | yes | yes |
| WSJ Opinion | `https://feeds.a.dj.com/rss/RSSOpinion.xml` | 200 | 13 | yes | yes | yes |
| WSJ Tech (WSJD) | `https://feeds.a.dj.com/rss/RSSWSJD.xml` | 200 | 20 | yes | yes | yes |
| MarketWatch Top Stories | `https://feeds.content.dowjones.io/public/rss/mw_topstories` | 200 | 10 | yes | yes | yes, + `dc:creator` + `media:content` |
| MarketWatch MarketPulse | `https://feeds.content.dowjones.io/public/rss/mw_marketpulse` | 200 | 30 | yes | yes | yes |
| MarketWatch Real-time Headlines | `https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines` | 200 | 10 | yes | yes | yes |
| MarketWatch Bulletins | `https://feeds.content.dowjones.io/public/rss/mw_bulletins` | 200 | 10 | yes | yes | yes |
| Barron's Magazine (only Barron's id found) | `https://feeds.content.dowjones.io/public/rss/barronsmagazine` | 200 | 10 | yes | yes | yes, + `dc:creator` + `media:content` |

Tried and **404 "NotFoundError: Feed not found"**: `mw_personalfinance`,
`mw_marketwatch_topstories`, `barrons`, `barrons_topstories`, `barrons_features`,
`barrons_columns`, `barrons_streetwise`, `barrons_upandcoming`, `barrons_weekday`,
`barrons_marketwatch`, `barrons_recentnews`, `barrons_online`,
`RSSBarronsThisWeekMagazine`. `feeds.a.dj.com/rss/RSSBarronsThisWeekMagazine.xml` and
`.../RSSBarronsMostViewed.xml` return **403 AccessDenied** (a different failure mode —
these ids may exist behind IP/referrer allowlisting rather than not existing at all;
worth one retry from the extension-relay's IP once that's live, low priority).
`www.wsj.com/rss` and `www.marketwatch.com/rss` (looking for an index page) both 401 —
blocked by the same edge bot-check as every other unauthenticated page on these domains.

Sample row (MarketWatch Top Stories, real, current):
```xml
<item>
<guid isPermaLink="false">WP-MKTW-0005251796</guid>
<title>How to keep profiting from AI while shielding your portfolio against the risk of a slowdown</title>
<description>Jamie Wilhelm and Sunit Gogia of Fort Washington Investment Advisors expect
the AI wave to continue, but describe leading indicators of an eventual downturn.</description>
<link>https://www.marketwatch.com/story/...-a5801291?mod=mw_rss_topstories</link>
<pubDate>Sat, 26 Sep 2026 13:35:00 GMT</pubDate>
<dc:creator>Philip van Doorn</dc:creator>
</item>
```
Every item across all 10 working feeds: **headline + one-to-two-sentence summary, never
full body**, a stable `guid`, a real `pubDate`, and (MarketWatch/Barron's feeds only) an
author and a lead image. This is exactly what `news_registry` wants for
`pit_grade: native_stamp`, `label_source: true` (the item's own timestamp is Dow Jones's
own publish stamp, not our ingest clock) — see §7 for the registry rows.
`lastBuildDate`/`ttl: 60` on the MarketWatch feeds imply the source itself expects
re-polling roughly hourly; a 15-minute poll (as asked) is well inside that.

## 3. Dated archives for the "what they said vs what happened" backtest

**Tested unauthenticated only** (per §0, the live-browser part was paused before this
step; nothing here reflects a logged-in read):

| Site | URL pattern | Unauth HTTP | Notes |
|---|---|---|---|
| WSJ | `https://www.wsj.com/news/archive/YYYY/MM/DD` | **401** | Same edge block as every other unauth WSJ page (`Please enable JS and disable any ad blocker` — this is a bot-check page, not a real 401 from the archive itself). **Untested logged in.** From general knowledge of the WSJ site structure this URL pattern is real and paginated per day; needs live confirmation via §7's relay.
| Barron's | (no direct pattern found; Barron's does not appear to expose a plain `/archive/YYYY/MM/DD` route the way WSJ does) | n/a | Not found. Barron's picks/columns are more practically reached via **section/tag pages** (e.g. its "Streetwise", "Stock Picks" columns) than a date archive — see §4 for real URLs pulled straight off the homepage.
| MarketWatch | `marketwatch.com/archive?...` | **401** (same bot-check) | Untested logged in. MarketWatch's own site search/section pages (e.g. `/investing/stock/<ticker>`) are more likely to carry dated history reliably than a generic archive query string — needs live confirmation via §7.

**This whole section is the one that most needs the extension-relay fix in §7** — a plain
`curl` cannot get past Dow Jones's edge bot-check on any of these three domains (every
unauthenticated request returns 401 with the "enable JS" stub, confirmed above and in §1),
so the archive-by-date study can only be built from a **real signed-in browser session**,
not from HTTP alone.

## 4. The gradeable columns

### 4a. Barron's stock picks & pans — real, dated URLs found live (from the Barron's
homepage, via the un-signed-in `muratclaw` profile — the page itself is not paywalled to
browse the headline/slug, only to read past the first ~200 chars):

```
buy-applied-materials-stock-chart-of-the-day-1cf1a978
buy-brookfield-stock-price-pick-alternative-assets-energy-real-estate-85c714c1
buy-sps-commerce-stock-price-pick-ea269322
buy-echostar-stock-greater-than-sum-of-parts-with-spacex-kicker-9aabdf80
buy-armstrong-world-industries-stock-ceiling-tiles-7a1f6d11
buy-grainger-stock-recovery-us-manufacturing-0b591a70
our-universal-stock-pick-didnt-pan-out-were-pulling-the-recommendation-43125b37
```
The last one is itself a **retraction/scorecard piece** — Barron's publishing "we're
pulling this pick" is direct, first-party evidence they track and revisit their own
calls, which is exactly the check-against-their-own-scorecard Murat wants. Slug pattern:
`buy-<name>-stock-<qualifier>-<8-hex>`; the claim (direction = long, since it's literally
titled "Buy") and the ticker are usually inferable from the slug/headline alone, without
reading past the paywall. The **annual "10 Favorite Stocks for 2026/2027"** and the
**weekly cover-story pick** are the other two recurring, more heavily-covered formats
(not captured live this session — same "confirm via the relay" caveat as §3).

- **Claim**: direction (buy/sell), sometimes a price target, always a ticker.
- **Date**: the article's own dateline (WSJ RSS-style `pubDate` equivalent once fetched
  live; the URL/homepage position alone doesn't carry a timestamp).
- **Grading**: enter at the close of the first session strictly after the claim date
  (same convention as `source_registry.forward_relative_returns` /
  `attach_outcomes` already in this repo), name return minus SPY (and minus a
  sector/size-matched control, since Barron's picks skew toward specific themes) at
  21/63/126 sessions, against `prices_2025_26/bars.parquet`.

### 4b. WSJ Heard on the Street, ratings/target tables, MarketWatch analyst
estimates/earnings calendar — **URL patterns confirmed to exist (route to a real page,
not a 404), but content untested** (401 unauthenticated, same bot-check as §3):

| Column | URL pattern | Claim | Horizon | Grade against |
|---|---|---|---|---|
| WSJ Heard on the Street | `wsj.com/finance/...` (a regular dated column, not a fixed URL template — reached via the WSJ Markets/Business RSS or the site's own section page) | Directional call on one name, in prose | Author-stated or implicit (usually weeks-months) | Same as 4a: entry at next close, relative return at 21/63/126d |
| WSJ ratings/price targets | `wsj.com/market-data/quotes/<TICKER>/research-ratings` — **401 unauth, confirmed to route (not 404)** | Consensus rating + mean/high/low price target, dated | As-of date on the page | Target vs realized price at target's stated horizon or 252d, whichever the page gives |
| MarketWatch analyst estimates | `marketwatch.com/investing/stock/<TICKER>/analystestimates` — **401 unauth, confirmed to route** | Consensus EPS/revenue estimates | Next 1-4 quarters | Estimate vs actual reported (already has a natural resolution date — the earnings release) |
| MarketWatch earnings calendar | `marketwatch.com/investing/stock/<TICKER>` earnings tab, or a market-wide calendar page | Date + consensus of an event, not a directional claim per se | n/a | Used as a timing input to other claims' entry dates, not graded itself |

### 4c. Barron's Roundtable / Big Money poll — **not located this session.** These are
long-running Barron's institutions (Roundtable: January issue, three sessions of named
panelists each giving picks; Big Money poll: semi-annual survey of institutional
managers) but I did not find a stable, dated URL for either in the unauthenticated crawl
available to me. Flagging as **needs a targeted search once the relay/live session is
up** rather than guessing a URL.

## 5. Licence — Dow Jones subscriber agreement (fetched live,
`https://www.dowjones.com/terms-of-use/`, which is what `wsj.com/policy/subscriber-agreement`
redirects to; fetched 2026-09-26, plain HTTP, no auth)

The relevant clauses, quoted, section numbers as published:

> **9. Limitations on Access and/or Use** — Access to our Services, even webpages that
> appear to be publicly available, is in fact subject to security systems... We reserve
> the right to refuse access to anyone.
>
> **9.1** The Services are for your individual, personal and non-commercial use only.
> **Thus, you may not access or use the Content, including without limitation, any
> Content made available through one of our RSS feeds, in any commercial product or
> service, without our express written consent.**
>
> **9.3** ...you may not use, sell, publish, distribute, retransmit or otherwise provide
> access to the Content received through the Services to anyone... **You may occasionally
> download, print and/or store articles from a Service for your individual, personal, and
> non-commercial use**, provided you maintain all copyright notices... **you may not use
> articles you have downloaded, printed or stored to develop or operate an automated
> trading system, or for text or data mining any information or content (including
> associated metadata).**
>
> **9.4.1** You agree not to rearrange, modify, display, post, frame, scrape, aggregate,
> or otherwise use the Content... You shall not access, view, retrieve, refresh, reload,
> scrape, text or data mine, index, process, store, harvest, or otherwise ingest the
> Services or any Content, whether directly or through an intermediary, **using any
> automated means, webcrawler, spider, script, site search/retrieval application,
> extension, bot, browser automation tool, API client, AI agent or assistant**, or other
> manual or automated device, tool, process, software or other means, **without our prior
> written consent.**
>
> **9.4.2** ...you may not harvest, ingest, use or incorporate any Content available
> through a Service for any form of artificial intelligence ("AI"), including in any
> generative or other form of AI **for training or grounding purposes**, unless you
> receive our prior written permission... your rights are not expanded... by our use or
> configuration of exclusionary protocols (e.g., the Robots Exclusion Protocol as
> implemented through robots.txt files).
>
> **9.4.3** You may not operate or deploy any semi-autonomous or autonomous software that
> attempts to access... any portion of our Services without our prior written permission.
> If, after receiving our written permission, you operate or deploy such software, you
> must truthfully populate all HTTP request header fields... and clearly disclose the
> identity of your software in the User-Agent...
>
> **9.4.5** You are prohibited from performing text and data mining activities under Art.
> 4 of the EU Directive on Copyright in the Digital Single Market or similar statutes in
> other jurisdictions.

**This is a materially harder line than "be polite about it."** §9.4.1 names "browser
automation tool" and "AI agent or assistant" explicitly and bars them from touching any
Content **without prior written consent** — that is exactly what OpenClaw driving a
signed-in session to read WSJ/Barron's/MarketWatch pages is. §9.3 separately bars using
even legitimately-downloaded articles "to develop or operate an automated trading system,
or for text or data mining" — which is what a Barron's-picks-vs-SPY backtest is, full
stop, regardless of how the article was obtained. §9.1 explicitly extends the
personal/non-commercial restriction to **RSS content too** ("including without
limitation, any Content made available through one of our RSS feeds"), so RSS is not a
loophole around the commercial-use restriction, only around the *automated-access*
restriction (RSS is, by its nature and Dow Jones's own publication of `ttl`/polling
hints, meant to be consumed by machines — that is the one part of this ToS that a
15-minute automated poll is squarely inside).

**What is and isn't defensible, plainly:**

- **Defensible now, no change needed**: polling the 10 confirmed RSS feeds in §2 at a
  15-minute cadence for **personal, non-commercial research** (Murat's own portfolio
  decisions) — headline + short summary + link + timestamp only, stored as metadata in
  `news_corpus`, never redistributed as Dow Jones's text. This is what RSS is for, and
  the personal-use gate is satisfied as long as the resulting tool/paper book stays
  Murat's own use.
- **Not defensible as written, without Dow Jones's prior written consent**: any
  **automated** (OpenClaw quest, script, or otherwise) read of paywalled WSJ / Barron's /
  MarketWatch article pages, and — separately and more broadly — **any use of that
  content, however obtained, to build or operate a systematic backtest / trading
  signal** (§9.3, §9.4.1, §9.4.2, §9.4.5 all point at exactly this). This directly covers
  the "Barron's-picks-vs-SPY backtest" and "OpenClaw reads Heard on the Street" pieces of
  this task as specified.
- **The genuinely defensible middle, and the one I'd recommend**: **Murat himself** reads
  the picks/columns at human pace inside his own signed-in "MuratClaw (Work)" Chrome (a
  human subscriber reading content he's licensed to read, for his own personal
  investment research, is squarely inside §9.1/§9.3's carve-out) and **manually or
  semi-manually records** the extracted claim (ticker, direction, date) into the same
  `source_registry.claim_records` pipeline already in this repo — the claim, not the
  article text, is what gets graded and stored. This keeps the "text or data mining" and
  "automated means" lines on the right side by keeping the *reading* human and the
  *storage* limited to Murat's own extracted facts, at the cost of not being able to
  fully automate the ingestion.
- **Recommended cadence/cap given the above**: RSS polling every 15 minutes, uncapped (it
  costs nothing and is inside intended use). **Zero** automated OpenClaw quests against
  paywalled WSJ/Barron's/MarketWatch article or archive pages until Dow Jones grants
  written permission (e.g., if Murat's subscription tier or a future API arrangement
  includes one) — this is a harder recommendation than the task brief assumed, and I'm
  flagging it rather than building around it quietly.

## 6. Three ways the bundle feeds the Bloomberg competition book (Oct 12 – Nov 13,
relative P&L)

1. **A catalyst calendar, from MarketWatch's earnings calendar + WSJ ratings/target
   pages** — dated events (earnings dates, rating changes, target revisions) are exactly
   the kind of *pre-scheduled, publicly known* information the competition's relative
   P&L format rewards being positioned ahead of. **What separates it from beta**: a
   catalyst calendar only helps if the *reaction to a beat/miss/rating change* is
   forecast conditionally (e.g. via `source_registry`'s existing sell-side revision
   scoring, which already has ~393k dated, gradeable rows) rather than simply
   long-biasing names with an upcoming catalyst — the latter is just market beta with
   extra steps.
2. **A pre-open attention layer, from the RSS bulletin/real-time-headline feeds
   (`mw_bulletins`, `mw_realtimeheadlines`)** — these update fastest and are free,
   giving a same-morning read on what the market narrative already is before the open,
   which is useful for sizing/hedging existing competition-book positions around news
   that broke overnight. **What separates it from beta**: only if it's used to
   *distinguish* a name-specific news event from a market-wide one (the existing
   `web_events`/`source_registry` machinery already asks exactly this question via
   `corroboration_rate` and cluster detection) — reading every headline as "buy the
   name in it" is beta with a news wrapper.
3. **A Barron's-picks twin as a judge-recognizable benchmark** — since Barron's picks are
   a widely-known, citable public track record, running Aegis's own book *against* a
   parallel "if we'd followed Barron's picks" twin book (using the human-read claims from
   §5's defensible path, not an automated scrape) gives judges an intuitive, external
   comparison point for "did the system beat a well-known professional picker," which a
   generic SPY-relative number doesn't convey as concretely. **What separates it from
   beta**: the twin has to be built from Barron's *actual, dated* picks (not
   backfilled/cherry-picked) and graded with the same by-year / leave-one-year-out
   discipline as everything else in this repo (CLAUDE.md §64/§55) — otherwise it's just
   another survivor-selected story.

## 7. Chunk spec for the Opus builder

**Fix the browser-profile problem first (blocking everything that needs a real login):**

- `openclaw browser extension status` (run live this session) reports:
  ```
  Extension copy: installed
  Load unpacked:  C:\Users\mrthn\.openclaw\browser\chrome-extension
  Native hosts:   0 owned
  Setup:          manual action required
  ```
  This is the **deployed, ready-to-load copy** — point Chrome's `chrome://extensions` →
  "Load unpacked" at **`C:\Users\mrthn\.openclaw\browser\chrome-extension`** (the
  coordinator's cited path, `...\AppData\Roaming\npm\node_modules\openclaw\dist\extensions\browser\chrome-extension`,
  is the npm package's source copy — same extension, but the `.openclaw` one is the one
  OpenClaw's own tooling already staged and expects). Load it into Murat's real Chrome,
  in the **"MuratClaw (Work)" profile** specifically (not a new profile). Then pair it
  (`openclaw browser extension pair`, printed string entered in the extension's popup, or
  whatever `pair`'s output specifies — not run this session since it needs Murat's hands
  on the actual browser).
- `openclaw browser profiles` already lists a **`chrome` profile, tag `extension`** —
  this is the relay's name once paired. Confirmed live this session (state: `stopped`,
  same as `muratclaw` when idle — expected, since neither is running until used).
- **Code change, `backend/services/openclaw_client.py`**: `assert_profile()` /
  `profile()` currently resolve to exactly **one** name at a time (from
  `AEGIS_OPENCLAW_PROFILE`, default `"muratclaw"`), and nothing in the module
  distinguishes "the automation-launched, never-signed-in Chrome" from "the
  extension-relay attached to Murat's real signed-in Chrome" — a caller has no way to
  say *which one it needs* short of an env var swap for the whole process. Add a second
  named constant (e.g. `RELAY_PROFILE = "chrome"`) alongside `DEFAULT_PROFILE`, let
  `browser()`/`agent()` take an explicit `profile:` override argument, and have
  `health()` probe and report **both** profiles' `profile_pinned` state so a caller (or a
  human) can see at a glance which one is actually available before a quest runs against
  the wrong one — which is precisely what happened in §0/§1 of this note.
- **Code change, `backend/services/openclaw_client.py`**: `ALLOWED_VERBS` is missing
  `scrollintoview`, `wait`, and `batch` (confirmed present in the real CLI via
  `openclaw browser --help`, run live this session — full list: `batch`, `click`,
  `click-coords`, `close`, `console`, `cookie-sync`, `cookies`, `create-profile`,
  `dialog`, `download`, `drag`, `errors`, `evaluate`, `extension`, `fill`, `focus`,
  `highlight`, `hover`, `import-profile`, `navigate`, `open`, `pdf`, `press`, `profiles`,
  `requests`, `reset-profile`, `resize`, `responsebody`, `screenshot`, `scrollintoview`,
  `select`, `set`, `snapshot`, `start`, `status`, `stop`, `storage`, `system-profiles`,
  `tab`, `tabs`, `trace`, `type`, `upload`, `wait`, `waitfordownload`). Add
  `scrollintoview`, `wait`, `batch` (still refuse `evaluate`, `create-profile`,
  `delete-profile`, `reset-profile`, `cookies`, `cookie-sync`, `import-profile` — those
  stay human-attended, same reasoning as the module's existing docstring). This matters
  for a **deterministic, $0 Python collector** driving the archive/picks pages directly
  (see below) — it does *not* block the `agent()` LLM-quest path, whose OpenClaw agent
  already has the full verb surface regardless of our wrapper; that path's failure mode
  is a **prompt** gap, covered next.

**Why quests stall on a page (the `source_reads.py` 600s-timeout note already found half
of this):** an open-ended "go read this page and tell me what's on it" quest fails when
the target page needs scrolling/waiting to render more than the first screen (an archive
day's full list, an infinite-scroll picks index) *and the prompt never told the agent to
scroll or wait*. The fix is a scripted verb sequence in the prompt, not a bigger timeout:

- **WSJ archive day page** (`wsj.com/news/archive/YYYY/MM/DD`):
  1. `navigate <url>`
  2. `wait` for load state / a selector inside the article-list container
  3. `snapshot` — capture every headline ref + href + visible time
  4. if the list is paginated (not infinite-scroll, per WSJ's usual archive layout):
     `click` the "next page" ref, `wait`, `snapshot` again; repeat
  5. for each headline worth grading: `navigate` to its href (or `click` its ref), `wait`,
     `snapshot` to capture byline + dateline + first paragraph (paywall or not)
- **Barron's picks/index page** (lazy-loaded):
  1. `navigate <url>`
  2. `snapshot` — capture the currently-rendered batch
  3. `scrollintoview` the last visible item's ref
  4. `wait` (network-idle or a fixed ~1500ms) for the next batch to render
  5. `snapshot` again; diff new refs against the previous batch; repeat 3–5 until no new
     refs appear or the target count is reached
  6. for each picks article: `navigate`/`click`, `wait`, `snapshot` → the ticker/direction
     is usually in the headline itself ("Buy Brookfield Stock...")

**Files to create/modify:**

- `backend/data/news_sources.yaml` — 10 new rows, one per confirmed feed in §2 (WSJ
  Markets/Business/World/Opinion/WSJD, MarketWatch Top Stories/MarketPulse/Real-time
  Headlines/Bulletins, Barron's Magazine). `method: rss`, `pit_grade: native_stamp`,
  `stamp_field: pubDate`, `label_source: true` (a genuine Dow Jones publish stamp, not an
  index snapshot), `licence: "personal_non_commercial — DJ ToU §9.1"`, `implemented:
  true`. Every `REQUIRED_FIELDS` entry from `news_registry.py` must be present or the
  whole file refuses to load (existing invariant — do not skip a field).
- `backend/services/dowjones_feeds.py` — new collector, plain HTTP (`requests`, no
  OpenClaw), parses the 10 feeds above, dedupes on `guid`, writes
  `news_corpus/dowjones_<feed>/*.jsonl` rows with `first_seen_utc` stamped at fetch time
  and `published_utc` from `pubDate`. A 15-minute scheduler entry, same shape as the
  other `news_corpus` collectors already in this repo.
- `scripts/dowjones_backtest.py` — Barron's-picks-vs-SPY/matched-control backtest at
  21/63/126 sessions. **Claims come from the human-read pipeline in §5, never from an
  automated scrape of article text** — the script's input is a small, Murat-curated
  claims file (ticker, direction, date, source URL), not a crawler's output. Outputs
  `by_year`, `leave_one_year_out`, `loo_worst_mean_net`, `share_of_total_by_date` on every
  call (same contract `xs_ranker.top_k_backtest` already carries, per CLAUDE.md's
  standing rule from 2026-09-24) — read the worst year, not the average, before calling
  anything a result. **Expected n**: from one homepage snapshot, ~7 distinct
  buy/pick-style pieces were visible at once; at a rough 1–3/week cadence (cover story +
  "chart of the day" + occasional "buy X stock" pieces) a 12-month sample is likely on
  the order of **100–250 dated picks** — this is a guess, not a measurement; the first
  run of this script should print the *actual* count before anyone treats a result as
  more than a pilot.
- Tests: a `news_registry` validation test that the 10 new rows load (existing
  `REQUIRED_FIELDS`/`PIT_GRADES` machinery already refuses a bad row — just needs the
  new ids added to whatever test enumerates known sources); a `dowjones_feeds` test that
  a 404/malformed feed is logged, not silently swallowed (matches the "guards DERIVE
  their inputs or refuse" house rule); a `dowjones_backtest` shape test asserting the four
  required output keys are present on a tiny synthetic claims fixture (never a fixture
  keyed to today's date — CLAUDE.md protocol item 5).
- Receipts: `backend/data/optimus/dowjones/feeds_<date>.json` (per-feed item count,
  newest `pubDate`, age since last new item — same "print the age and size of the
  candidate set" discipline as the funnel-staleness fix from 2026-09-22); the backtest's
  own receipt with the by-year table front and center, before any headline number.

## Files/paths referenced

- `backend/services/openclaw_client.py` (read; verb-set and profile gaps found, listed above)
- `backend/services/news_registry.py`, `backend/services/source_registry.py`,
  `scripts/source_reads.py` (read, for the existing claim→forecast-row pipeline the
  human-read path in §5 should reuse)
- `docs/research_notes/2026-09-26/research_dowjones_bundle_wsj_barrons_marketwatch.md` (this file)
