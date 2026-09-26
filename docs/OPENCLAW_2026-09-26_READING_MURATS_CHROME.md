# OpenClaw, 2026-09-26: reading Dow Jones through Murat's own Chrome, and the paste inbox

Chunk J. The code: `backend/services/openclaw_client.py` (named profiles, operator rules),
`backend/services/web_reader.py` (deterministic reader), `backend/services/dowjones_feeds.py`
(10 RSS feeds), `backend/services/dowjones_claims.py` (claims -> `source:<column>` forecasts),
`backend/services/digest_inbox.py` + `scripts/digest_ingest.py` (the paste inbox, **the primary
path**), `scripts/dowjones_pull.py` (the CLI), `scripts/openclaw_api_bridge.py` (Aegis API as
read-only MCP tools). Tests: `backend/tests/test_dowjones_chunk_j.py`.

## 1. Which profile is which

| profile | what it is | signed in to Dow Jones? | who may use it |
|---|---|---|---|
| `muratclaw` | OpenClaw's managed automation Chrome, own cookie jar (port 18801) | **no**, and Google refuses its sign-in | every existing caller; still the env default (`AEGIS_OPENCLAW_PROFILE`) |
| `user` | **Murat's own running Chrome**, attached over chrome-mcp (existing-session) | yes, in the "MuratClaw (Work)" window | only `web_reader` / `dowjones_pull`, only with `--handoff` |
| `chrome` | extension relay into the same Chrome (`relayPort 18799`) | same browser | not set up yet (needs Load-unpacked + pairing, research note §1.4) |

A caller names the profile (`profile_name="user"`); a name outside
`config.OPENCLAW_ALLOWED_PROFILES` refuses with `REFUSED_BROWSER_PROFILE_NOT_ALLOWED`, and nothing
ever falls back to another profile.

## 2. The one-time Chrome step (Murat)

In the Chrome window that has **MuratClaw (Work)** open: go to `chrome://inspect/#remote-debugging`,
turn the toggle on, accept the "allow remote debugging" prompt, and keep the window open. Treat
the toggle as per-session (it may need redoing after a full Chrome restart).
`openclaw browser profiles` then shows `user: running (N tabs) [existing-session]`.

## 3. The rules on `user` (it IS Murat's browser)

Enforced in `openclaw_client`, not by the model:

* **`open` is refused.** On 2026-09-26 an `open` from this chunk's builder put a SEC page as a
  new tab in Murat's MAIN Chrome profile, in front of him. A new tab now comes only from
  `open_from_tab(parent, url)`: `window.open(<url>)` runs inside an existing MuratClaw tab, so the
  new tab inherits that profile. The URL is host-checked and JSON-encoded into a fixed template.
  The new tab is found by diffing `tabs` before and after, and its host is re-checked.
* Every action names its tab, and that tab's **current** host must be `wsj.com`, `barrons.com`
  or `marketwatch.com` (`config.OPENCLAW_USER_TAB_HOSTS`). This is checked before every verb and
  re-read after a navigate, click or press. sec.gov, x.com, reddit and Yahoo **never** go through
  this browser; they use their HTTP APIs.
* Allowed verbs: `tabs status profiles focus navigate snapshot click scrollintoview press wait
  screenshot`. `type`, `fill`, `download`, `upload` and `batch` are refused. `close` works only
  on a tab this process opened.
* `evaluate` is still **not** a free verb. `read_text()` sends one module-constant function
  (`document.body.innerText`) and refuses if the JSON reply's `targetId` is not the tab it asked for.
* The reader clicks only `link` roles. It never clicks a button, textbox or form, and never a
  link whose text reads like an account or money action (sign in/out, subscribe, checkout,
  account, gift, ...). `mail.google.com`, `app.alpaca.markets`, `railway.com` and
  `web.whatsapp.com` are refused even if the allowlist is ever edited to include them.

## 4. The verb sequence (`dowjones_pull --handoff --parent-tab tNN ...`)

```
tabs                                   # the parent is on wsj/barrons/marketwatch
evaluate --target-id <parent> --fn "() => { window.open(\"<listing url>\", '_blank'); return 1; }"
tabs                                   # diff -> the new tab id; host re-checked
wait --target-id <new> --time 4000
snapshot --target-id <new> --format ai --urls --limit 900
    -> links chosen FROM the snapshot: URL regex per section + text rules (never a guessed URL)
per article (>= 20 s apart):
    click <ref> (first one, when the snapshot shows it as a link) | navigate <snapshot URL>
    wait --time 3500
    evaluate --target-id <new> --fn <READ_TEXT_FN>      # targetId verified
    clean (nav/header/footer/account name) -> store
close <new>
```

`networkidle` does not work on existing-session, so the waits are fixed times.

**Human pace** (`docs/research_notes/2026-09-26/research_openclaw_best_practice_and_human_pace.md` §5):

* **Jittered, not a floor.** Each gap target is drawn from a lognormal clipped to
  `[WEB_READER_MIN_DELAY_S, WEB_READER_MAX_DELAY_S]` = [20, 90] s (`np.random.default_rng`),
  and never lands within 1 s of the previous target. The realised wait is `target - elapsed`.
  Caps: 30/h, 120/day, **40/day per site** (`WEB_READER_MAX_PER_DAY_PER_HOST`), all persisted
  in `news_corpus/dowjones/_throttle.log` (`<iso> <host> <target>`) so runs share one budget.
* **Scroll before reading.** Each article gets 2-3 `press PageDown` steps with 1-3 s jittered
  `wait`s before the text is read. A read with no scroll telemetry is the tell.
* **One tab, one reader.** `_reader.lock` (PID-checked, and taken over if that PID is dead)
  refuses a second concurrent session.
* **Footprint receipt per session:**
  `backend/data/optimus/web_reader/footprint_<ts>.json` holds the gap histogram,
  pages/hour, CV of gaps and scroll share. The verdict is `HUMAN_PACE_OK`, or
  `ALARM: CV < 0.15` (pacing collapsed to a constant), or `ALARM` for a gap under the floor,
  or `CANNOT DETERMINE` (< 3 gaps).

`--max-pages` caps a session (tonight: 20 pages across all runs). The receipt is rewritten after
**every** page (`backend/data/optimus/dowjones/reads_<date>_<source>_<section>_<hhmmss>.json`).

Sections: `wsj/heard_on_the_street`, `barrons/stock_picks`, `barrons/big_money_poll` (listing
URL unverified: a listing that shows no matching link is reported as `NO_LINKS_ON_LISTING`),
`marketwatch/analyst_estimates` (one page per ticker from the fixed
`/investing/stock/<t>/analystestimates` template, the same page Murat keeps open in t32).
`--archive YYYY-MM-DD` refuses while `config.DOWJONES_ARCHIVE_ENABLED = False` (Murat: the
archive-by-date crawl stays OFF). The archive days are links in the reading list instead.

## 5. Licence: the Dow Jones subscriber agreement, and the bounded policy

From `https://www.dowjones.com/terms-of-use/` (fetched 2026-09-26; full quotes in
`docs/research_notes/2026-09-26/research_dowjones_bundle_wsj_barrons_marketwatch.md` §5):

> **9.1** The Services are for your individual, personal and non-commercial use only. Thus, you
> may not access or use the Content, including without limitation, any Content made available
> through one of our RSS feeds, in any commercial product or service, without our express
> written consent.
>
> **9.3** ... You may occasionally download, print and/or store articles from a Service for your
> individual, personal, and non-commercial use ... you may not use articles you have downloaded,
> printed or stored to develop or operate an automated trading system, or for text or data
> mining any information or content (including associated metadata).
>
> **9.4.1** ... You shall not access, view, retrieve, refresh, reload, scrape, text or data mine,
> index, process, store, harvest, or otherwise ingest the Services or any Content, whether
> directly or through an intermediary, using any automated means, webcrawler, spider, script,
> site search/retrieval application, extension, bot, browser automation tool, API client, AI
> agent or assistant ... without our prior written consent.

Said plainly: the browser reader is what 9.4.1 describes, and sending article text to an LLM
touches 9.4.2 (AI grounding). The policy that follows from that:

1. **The primary path is the paste inbox.** Murat reads, and the code only files what he pasted.
2. The browser reader runs **only** with `--handoff` **and** `backend/data/optimus/HANDOFF_PC`,
   a file Murat creates when he hands the PC over. Creating it is his decision, on his own
   subscription. Nothing in the repo creates it. It is gitignored.
3. Human pace, a hard page cap, no archive crawl, and no URL the page did not show.
4. **Nothing is republished; the repo is public.** Full text lives in the gitignored
   `news_corpus/dowjones/` and `digest_inbox/`. What reaches git: receipts (counts, URLs,
   titles, stamps), and in the forecast ledger the model's **own one-sentence paraphrase** of a
   claim (`[<column>] ...`). The verbatim quote is kept only locally
   (`news_corpus/dowjones/_claims/`), so a human can check the model did not invent it. A quote
   that is not in the article is refused.
5. RSS: 10 feeds, plain HTTP, headline + one-sentence summary. That is what the feeds are for;
   9.1's personal-use limit still binds.

## 6. The paste inbox (the weekend's main path)

`backend/data/optimus/digest_inbox/`: `README.md` (the format), `WEEKEND_READING_LIST.md`
(generated from the books: 8 weeks of WSJ archive days, Barron's picks/scorecard/Big
Money/Roundtable/"10 favorite stocks" searches, HOTS searches, MarketWatch estimates + overview,
and WSJ research ratings for every personal, competition and PROBE name). You paste into
`DIGEST.md` under `=== url | date | source`, or save any `.txt`. Then:

```
python -m scripts.digest_ingest --once --claims
```

`first_seen_utc` = ingest time, never the article date or the file mtime. The article date is
`published_utc`, and a gap over 30 days grades the row `archive`: its claims are recorded but
**no forecast row** is written, because a forecast dated today about a month-old call is
backfilled evidence. Ingest is idempotent by content hash. `python -m scripts.digest_ingest
--reading-list` regenerates the list.

## 7. Claims -> forecast rows

`dowjones_claims.extract_claims`: one DeepSeek call per article (`llm_analyzer._call_llm`,
purpose `dowjones_claims`) returns `{ticker, direction, horizon_days, magnitude_bucket, quote,
paraphrase}`. `write_forecasts` calls `source_registry.write_claims`, which writes
`source:<column>` rows at the house grid of 1/5/20 sessions vs SPY, p = 0.60/0.40 by stated
direction. Those rows are graded by the same grader as every `source:` row. Columns:
`wsj_heard_on_the_street`, `barrons_stock_picks`, `barrons_big_money_poll`,
`mw_analyst_estimates`, else `<publisher>_other`. Cap: `DOWJONES_CLAIMS_CAP_USD = 0.30`, read
from the writer's own ledger (`llm_telemetry.spend(purpose=...)` since the run started). If the
ledger cannot be read, the run refuses.

## 8. Optimus and the Aegis API as OpenClaw MCP tools

Registered in `C:\Users\mrthn\.openclaw\openclaw.json` (OpenClaw config, not this repo):

```
openclaw mcp add optimus --command C:\Users\mrthn\optimus\.venv\Scripts\python.exe \
  --arg C:\Users\mrthn\optimus\mcp\server.py --env AEGIS_REPO=C:\Users\mrthn\aegis-finance \
  --include brain_query,session_briefing,aegis_verified_state,aegis_registry,aegis_canon,aegis_postmortems,aegis_skills \
  --approval approve --timeout 120
openclaw mcp add aegis_api --command C:\Users\mrthn\optimus\.venv\Scripts\python.exe \
  --arg C:\Users\mrthn\aegis-finance\scripts\openclaw_api_bridge.py \
  --include aegis_health_full,aegis_pi_get --approval prompt --timeout 60
openclaw mcp probe   # aegis_api: 2 tools (approval prompt) · optimus: 7 tools (approval approve)
```

`optimus`'s seven tools are all reads, so they are set to `approve`. `aegis_api` is GET-only over
an allowlist of `/api/pi/*` read routes plus `/api/health/full`. It is set to `prompt` for its
first rollout, so an unattended turn that calls it will wait for approval. No key is set in
either config. The chain stays `OpenClaw -> Aegis -> Telegram`, and no messaging channel was
added.

## 9. Owed hooks

* **Feeds, already wired, no patch needed.** The 10 rows are `parser: rss2` registry sources,
  so `scripts/news_pull.pull_all` pulls them wherever it already runs: `daily_pass`
  (`news_pull` step) and `always_on_lab` (`loop_news_pull`). The Dow Jones-specific non-XML
  refusal runs only through `dowjones_pull --feeds`. On the generic path an HTML reply fails
  the `rss2` parser and is logged as a failure. To make the generic path refuse by name as well,
  the owed patch is in `scripts/news_pull.py::fetch_feed`, before `parser(raw)`:
  ```python
  if src.provider.startswith("Dow Jones"):
      from backend.services.dowjones_feeds import looks_like_xml
      if not looks_like_xml(raw):
          raise FetchError(f"REFUSED_NON_XML: {src.endpoint_or_feed}")
  ```
* **Paste inbox cadence.** Nothing schedules `digest_ingest` yet. The owed hook is one step
  in `scripts/daily_pass.py` STEPS: `("digest_ingest", "operator-pasted Dow Jones articles ->
  claims")` calling `scripts.digest_ingest.once(claims=True)`. It is cheap: $0 when the inbox
  holds nothing new.
* **The `chrome` extension relay** (research note §1.4): Load-unpacked
  `C:\Users\mrthn\.openclaw\browser\chrome-extension` into MuratClaw (Work), then
  `openclaw browser extension pair`. After that, `batch` exists and the per-session
  `chrome://inspect` toggle is no longer needed.
* **`barrons/big_money_poll`**: the listing URL is unverified. Confirm it from the live page
  before trusting a zero.
* **`scripts/source_reads.py` human pace (owed, not my file tonight).** In `discovery_prompt`,
  `read_prompt` and `timeline_prompt`, replace the "scroll once or twice" clause with:
  ```
  Read at a person's pace: pause 3-10 seconds between scrolls and between pages, never
  as fast as the tool allows. Sequence: open the page -> snapshot -> scroll (PageDown) ->
  pause -> snapshot again -> compare with the previous snapshot -> repeat until no new
  posts appear or you have 20 posts -> then extract.
  ```
  and set `quests[-1]["pacing_instructed"] = True` in the receipt (a SOFT control: the agent
  route has no verb-level hook Aegis can enforce). `scripts/thesis_cards.py` needs **no** change:
  it never calls the browser (it reasons over pre-loaded data).

## 10. Failures from the first live night, fixed and pinned

* **The main-profile tab** (above): `open` is refused on `user`, and new tabs come only via
  `open_from_tab`.
* **cp1252.** `openclaw_client._run` decoded the CLI's stdout with the Windows code page. A
  curly quote in an article (UTF-8 `E2 80 9D`; `0x9D` is unmapped in cp1252) killed the
  reader thread, stdout became `None`, and every read after the first came back **empty**.
  The first article happened to decode, as mojibake. `_run` now decodes UTF-8 with
  `errors="replace"`, and an empty read is `REFUSED_EMPTY_READ`, never a page with no text.
* **The claim extractor over-counted and mis-tickered.** The first pass on 5 HOTS articles
  wrote 24 rows from 8 claims: one article's view became 4 "independent" LEU forecasts, "HP"
  was emitted for HP Inc (HPQ; HP is Helmerich & Payne), and "Dell has risen sharply this year"
  was treated as a forecast. All of those rows were removed before commit. `validate_claims`
  now keeps **one view per (ticker, direction)** per article. The ticker must be **named in
  the article**: resolved by `news_entities` (limit 200), written as `(TICK)`/`$TICK`, or the
  distinctive first word of its registered name appears ("Micron", because the resolver only
  matches "Micron Technology"). A claim whose paraphrase only describes a past move is
  `REFUSED_BACKWARD_LOOKING`. Extraction also **varies run to run**: the peptide article
  gave three claims on one pass and none on the next. Treat one pass as a sample, not a
  census.
* **The attachment dropped mid-session.** The Barron's run opened t39 from t33. By the first
  `wait`, t39 was gone and `user` read `stopped` (pageReady false). The gateway stayed up.
  Re-attaching needs a human at Chrome's consent prompt, so the session ended there: Barron's
  0 articles, MarketWatch not run.

## 11. What the first night produced (2026-09-26)

| what | count | where |
|---|---|---|
| RSS items (10 feeds, run to completion) | 162 new, 0 refused/RED | `dowjones/feeds_2026-09-26.json` |
| free DJ surfaces probed by plain HTTP | 13: only the ToU page 200; 10 walled 401/403 | `dowjones/free_surfaces_2026-09-26.json` |
| HOTS articles read (Murat's Chrome, t38 opened from t20, closed) | 5, 26,893 chars, 91-203 s apart | `dowjones/reads_..._145059.json`, `web_reader/footprint_20260926T151024Z.json` (HUMAN_PACE_OK, CV 0.24) |
| Barron's stock picks | 0 (attachment lost) | `dowjones/reads_..._barrons_stock_picks_151017.json` |
| MarketWatch analyst estimates | not run | -- |
| claims -> forecast rows | 3 claims -> 6 rows, `source:wsj_heard_on_the_street` (LEU up, AAPL up; HOOD no direction) | `dowjones/claims_2026-09-26_152059.json` |
| LLM spend | $0.0082 claims (three passes) + $0.0124 Optimus MCP check | `llm_calls` ledger |

## 12. Chunk J2 (2026-09-26 night): rotation, the archive, the queue

Murat asked: "is it only reading Barron's? it can also read WSJ and MarketWatch while it's
waiting on delays", and then "let openclaw loose". Tabs loading in parallel are the bot
signature. So the answer is **rotation**: one page at a time, cycling through the sources, so
all three make progress and no single host sees a burst.

**`--plan`** (`scripts/dowjones_pull.py::run_plan`)

```
python -m scripts.dowjones_pull --handoff --plan \
  "barrons:stock_picks:5,wsj:heard_on_the_street:5,marketwatch:analyst_estimates:MU|DKNG|QUBT"
```

* **Parent tabs are resolved on every run and never hardcoded.** Tab ids change whenever the
  gateway restarts. `resolve_parent_tabs` reads `tabs` and picks the **oldest** tab (lowest
  id) on each source's host. The oldest tab is Murat's own; a newer one was probably opened
  by a run. A tab this process opened is never used as a parent. A source with no open tab
  borrows the oldest allowed tab, and the receipt says `borrowed`. `--parent-tabs
  "barrons=t13,wsj=t20"` overrides; the named tab must exist and be on an allowed host. The
  chosen tabs are printed and written to the receipt. `tabs` does not expose the Chrome
  profile, so "oldest tab on the host" is the proxy for "the MuratClaw (Work) tab".
* Each lane gets one tab, opened from its parent, and its listing is loaded once. Links come
  from that snapshot. Then **one item per lane per turn**, in plan order, all under the one
  shared `Throttle`: the 20-90 s jittered gap holds across sources, not just within one.
  A lane that runs out of items drops out.
* When something fails, the damage is contained at the right level. A dead tab, or a tab
  that left the allowed hosts, drops only its own lane. The per-host daily cap drops every
  lane on that host. The day cap, the session cap or a busy reader lock stops the whole run.
  Every tab the run opened is closed in `finally`.
* A URL already in the corpus (`web_reader.stored_urls`) is **not loaded again**. The text
  hash already deduplicated storage, but this also skips the page load, which is what the
  site sees. A MarketWatch ticker already stored today is skipped the same way.
* Receipt: `dowjones/plan_<date>_<hhmmss>.json`, rewritten after every page. It holds
  per-lane and per-source counts, the interleaved `order` with timestamps (`page_load:
  false` marks the first MarketWatch ticker, which is read in place because `open_from_tab`
  already loaded it), `seconds_between_page_loads` taken from every reader's log, the tabs
  closed, one merged footprint and `hour_cap_waits_s`.
* Long runs wait out the **hourly** cap instead of stopping (`Throttle.wait_on_hour_cap`).
  The wait lasts until the oldest load in the window is an hour old, plus a jittered 5-60 s.
  The day and per-host caps still refuse.

**`--archive A..B`** (`run_archive`): runs on WSJ `https://www.wsj.com/news/archive/YYYY/MM/DD`
for each NYSE trading day in the range, newest first (`archive_days` skips weekends and
`digest_inbox.nyse_holidays`, and refuses any day that has not finished). The whole run uses
**one** tab: the day page loads, links are chosen from its snapshot (the HOTS article pattern,
which excludes `news/`), and each day reads up to `DOWJONES_ARCHIVE_MAX_PER_DAY` articles.
It can resume: a stored URL is skipped **and counts toward that day's cap**. **Barron's and
MarketWatch are not archived**, because this code has never seen a dated archive URL on a live
page of either site, and the rule is "no URL the page did not show". The receipt carries this
as `not_built`. Budget: 4 days × 40 articles is more than WSJ's 120/day per-host cap, so a
four-day archive runs across two nights. Resuming picks it up.

**`--queue FILE`** (`run_queue`): each line is one `dowjones_pull` command, and the lines run
in order. A line that returns 0 gets a marker in `<stem>.done/line<NNN>_<sha>.done`. The key
includes the line's text hash, so an **edited** line runs again. A failed line is recorded
and the queue moves on. `--handoff` and `--profile` are inherited by every line.
`--queue-first-only` runs one line. `--write-queue PATH` regenerates the night's file from
the books (`digest_inbox.book_names`: personal, then competition from `llm_portfolio/books.jsonl`,
then PROBE; 56 distinct today, capped at 40, so the last 16 PROBE names are cut). Tonight's
file is `backend/data/optimus/dowjones/QUEUE_2026-09-26.txt`:

```
--plan "barrons:stock_picks:10,wsj:heard_on_the_street:10,barrons:big_money_poll:3,marketwatch:analyst_estimates:<40 names>"
--archive 2026-09-22..2026-09-25
--claims --claims-since 2026-09-26
```

**Claims for every column** (`dowjones_claims`):

* `mw_analyst_estimates` pages produce **no LLM call**. `parse_mw_analyst` writes one
  `mw_analyst_snapshot` row: consensus rating, mean/high/low/median target, number of analysts,
  next earnings date, current price, FY report date, current-quarter and current-year EPS
  estimate. It is stamped with `first_seen_utc` and is idempotent by (ticker, sha). The parser
  was checked against the live MU page stored tonight: 7 of 8 fields on that page. The
  earnings date appears on the live page as "MU WILL REPORT ... EARNINGS ON 09/30/2026", and
  the parser reads that form now. A THIN parse (fewer than 2 fields) is reported and never
  written.
* `barrons_stock_picks`: the user message now carries a column note asking for one claim per
  `(ticker: XX)` name. `article_tickers` also accepts Barron's `(ticker: XX)` form, so these
  names pass the "named in the article" check.
* `barrons_big_money_poll`: `parse_big_money` gives bullish/bearish/neutral %, a majority
  direction, and every S&P 500 level in a sentence with a forward cue. Each level owns the
  text between itself and its neighbouring levels, so "finish the year at 6,900 and reach
  7,250 by the middle of 2027" becomes two rows. These are **index-level rows**, not
  `source:` forecast rows, because the relative-to-SPY grader cannot grade an index against
  itself. **The level grader is still owed.** The article still gets its LLM pass for any
  named stock picks.
* Both structured files live in the **gitignored** `news_corpus/dowjones/_structured/`,
  because consensus targets and poll levels are Dow Jones/FactSet content. A receipt carries
  only counts and tickers.

**A defect found tonight, with the fix owed in `openclaw_client`.** Both Big Money reads at
15:52 failed with `'mod' is not recognized as an internal or external command`. The cause:
`_run` calls the `openclaw` .cmd shim with `shell=True`, so an unquoted `&` in the
snapshot's `?refsec=big-money-poll&mod=...` ended cmd.exe's command line. `web_reader.Reader.
navigate` now removes a query that contains a cmd metacharacter (Dow Jones article paths are
complete without their referral tags) and records the original as `url_shown`. **The root fix
(quote the arguments or avoid the shell in `_run`) belongs in `openclaw_client`, which is not
this chunk's file.**
