# The reader's BROWSE lane, 2026-09-29: general news, a list that refills itself, states that tell the truth

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT (money) | **NONE**. No reader output feeds a sized decision yet. |
| Reader throughput before the fix | **0 OK pages for 100+ minutes** (09:0x-10:48 HKT) with every Dow Jones cap free and `pending: 0` |
| Reader throughput after the fix (live, measured from `page_log.jsonl`) | **50 OK pages in the 10 minutes to 03:40 UTC across 11 hosts**; 189 OK pages in the hour to 03:40 UTC. That hour includes one restart and a burst of front reads, so it is **not** a sustained rate. The sustained rate is in the pool status (`throughput.sustained_ok_per_hour`) and needs a run of at least 30 minutes without a restart |
| Hosts read | 3 Dow Jones + **12 general-news / official hosts** on the allowlist (Reuters is on the list but its robots.txt disallows every section front: recorded, never opened). 10 minutes to 04:02 UTC: OK pages on 11 hosts (bbc 9, wsj 8, nikkei 8, yahoo 8, scmp 7, apnews 6, barrons 5, fed 5, marketwatch 3, bls 3, sec 3); `reader_status.json` READING, 58 OK in 10 min, no error |
| Fronts in the rotation | 27 → **77** (8 more Dow Jones sections: politics, opinion, commodities, video, podcasts, personal finance; 42 general-news and official-release fronts) |
| Pages stored with the fields a digest needs | every page read, fronts included, readable in one call: `reader_report.pages_read_since(hours)` |
| Digest asks adopted | 50 `read_next.jsonl` rows → site-search navigations (2 sites each), ranked with the fronts. Search pages read live from 04:02 UTC (WSJ, Barron's, MarketWatch, SCMP), each stored with its question. CNBC's and FT's robots.txt disallow their search paths: recorded, not opened |
| Stall restarts of a healthy idle pool | ~20 that morning → the state is now QUEUE_EMPTY / WAITING_FOR_CAP, not STALLED; stall restarts are bounded to 3 an hour |
| Tests | new `backend/tests/test_reader_browse_lane.py` (35 tests); the reader test files: **493 passed** |
| LLM spend | $0 added. Fronts and general-news pages are excluded from the paid claim extraction |

## 1. The fault

`reader_pool_status.json` at 10:46 HKT: wsj / barrons / marketwatch `pending: 0` at 437-628 of 1,200 pages
for the day; x / reddit / stocktwits at 150/150. Every stock page had been read inside its 20 h
freshness window, every front link was stored, and outside US hours the fronts came due only every 2 h.
Nothing refilled the list. The supervisor's `derive_state` had no state for "alive, nothing due", so it
called the pool STARTING for 600 s after each launch and STALLED after that, and restarted it every
~15 minutes. A restart cannot create work (the new pool reloads the same freshness files).
`reader_status.json` read `STARTING` beside a `last_error` of `STALLED ... 6023 s`.

## 2. What was built

| piece | where |
|---|---|
| General-news fronts on free public sites: Reuters, AP, CNBC, Yahoo Finance, BBC, FT (fronts and free pieces), Nikkei Asia, SCMP, federalreserve.gov, bls.gov, sec.gov, home.treasury.gov. Per host: 1 tab, a drawn 20-80 s gap between opens, 30 pages an hour, 300 a day. The Dow Jones and social caps are **unchanged** | `reader_scheduler.NEWS_SITES`, `NEWS_FRONTS`; `config.OPENCLAW_NEWS_HOSTS` (appended; `OPENCLAW_BROWSER_HOSTS` widened) |
| **The refill rule**: a host whose pending list is at or below `READER_QUEUE_LOW_WATER` (3) revisits its fronts once they are `READER_FRONT_MIN_REVISIT_S` (20 min) old, instead of waiting for the 30-min / 2-h schedule | `reader_scheduler.front_due_now`, `next_front_due_s` |
| Browse like a reader: each front is stored as a page record (its headlines in page order and its outbound links). From an article reached from a front, up to 3 outbound links are followed one hop: the related block on the same host, then in-article links on any allowed news host that have that host's article shape. No ticker needed, never a social host, never depth 2 | `reader_pool._store_front`, `_follow_browse`, `outbound_links` |
| Dedupe: a page is read once, by canonical URL (host + path, no query), against every stored record | `WR.norm_url`, `Pool.stored` |
| Ranking: tier, then found-before-listed, then **recency of the link's visible date**, then position on the page | `reader_scheduler.priority_key`, `recency_rank` |
| Age rule: links whose visible date is older than 4 days are not queued (fronts 3 days; stock pages had allowed 30). A stored page whose own dateline is older than 4 days is flagged `archive` and its links are not followed. Undated links are still read | `READER_MAX_ARTICLE_AGE_DAYS`, `RS.is_archive`, `WR._store_article` |
| robots.txt: each general-news host's robots.txt is read once a day through the same browser and judges every later URL there; a disallowed page is never opened (class `ROBOTS_DISALLOWED` in `page_log.jsonl`). Dow Jones hosts are not judged here: the owner's earlier decision on them stands | `RS.robots_allows`, `Pool.robots_state`, `dowjones/robots/<host>.json` |
| A bot check / block / paywall: a CHALLENGE cools the host (unchanged). New: 4 BLANK pages in a row cool the host; a run of 3 paywall stubs leaves a host on its headlines only for 6 h; a page whose title is the paywall ("Subscribe to read") is a PAYWALL_STUB whatever its length | `Pool._blank_outcome`, `_paywall`, `WR._PAYWALL_TITLE` |
| Queue states, per host and for the pool: READING, REFILLING, QUEUE_EMPTY, WAITING_FOR_CAP, COOLING. The pool's `state` is derived from them, not from "the process is alive" | `RS.host_queue_state`, `pool_queue_state`, `Pool._status` |
| The supervisor reads the pool's state (if the status file is under 3 min old). QUEUE_EMPTY and WAITING_FOR_CAP are healthy, not a stall. The stall ladder survives a pool restart (`dowjones/stall_ladder.json`) and resets only after an OK page. Stall restarts and recycles: at most 3 an hour, doubling backoff. `last_error` is cleared once the reader is healthy. `next_action` never says "keep reading" beside a stall | `night_reader_supervisor.derive_state`, `pool_state_of`, `next_action_for`, `load_ladder` |
| Caps count every load that reached the site: the pool no longer refunds the slot of a BLANK page (review F3); only an open that produced no tab is refunded | `Pool.process` |
| A recurring item whose open failed comes back after 10 min (review F6: it was lost for the life of the process) | `Pool.retry_after` |
| Pending found links survive a pool restart (`dowjones/pool_pending_carry.json`, read once, 6 h shelf life). Verified live: 139 items carried | `Pool.save_carry`, `_load_carry` |
| The digest's asks (`news_digest/read_next.jsonl`): a URL on an allowed, non-social host is read; a question becomes a NAVIGATION to the site's own search URL on two sites (one general-news, one Dow Jones, rotating). Nothing is typed. Each ask is adopted once (`dowjones/read_next_adopted.jsonl`); found links carry `question`, `digest_id`, `theme` in `reached_by` | `Pool._adopt_read_next`, `RS.SEARCH_URLS`, `search_sites_for` |
| **The digest read**: `reader_report.pages_read_since(hours=6.0, *, now=None, root=None, include_text=True, include_social=True, include_transcripts=True, kinds=None, hosts=None, include_archive=True) -> list[dict]`, newest first. Fields: `url, host, publisher, section, title, published_utc, fetched_utc, text, outbound_links, page_class, page_kind (front/article/media/search/stock_text/front_text/social), source_kind (dowjones/general_news/social), column, reached_by, tickers_named, media, tables, byline, sha, chars, archive, path`, plus `transcripts` for media pages | `backend/services/reader_report.py` |
| Fronts and general-news pages are skipped by the paid claim extraction and by the Dow Jones source scorecard | `dowjones_pull.run_claims`, `source_scorecard.load_corpus` |

The full page text stays in the existing gitignored store (`news_corpus/dowjones/<publisher>/<day>/<sha>.json`;
the general-news publishers get their own folder there). General-news pages carry
`licence = "public web page, read for personal research; not republished"` and write no `dj_reader_*`
registry row.

## 3. Live proof (10 minutes to 03:40:48 UTC, from `page_log.jsonl`)

OK pages per host: wsj 10, cnbc 7, barrons 5, finance.yahoo 5, bbc 5, ft 5, federalreserve 4,
asia.nikkei 3, scmp 3, marketwatch 2, apnews 1 (**50**). Not OK: reuters 6 × ROBOTS_DISALLOWED (fronts
refused by its robots.txt, never loaded). Examples of what was stored:

- federalreserve.gov: "Speech by Governor Cook on an update on AI and the economy"
- asia.nikkei.com: "Vietnam's 10% growth drive runs into economic realities"
- scmp.com: "Exclusive | JPMorgan's Jamie Dimon on how growth can untangle US-China ..."
- finance.yahoo.com: "Bond Veteran Jim Bianco Turns Bullish for First Time Since 2020"
- ft.com: "Anthropic warns of 'existential risks to humanity' in IPO prospectus"
- cnbc.com (media): "A lot under the market headline directly related to rates, says Solus' Dan ..."
- barrons.com: "Copper Prices Are Tumbling Along With Freeport, Other Mining Stocks"
- bbc.com: "Christa Pike execution: Tennessee governor rejects plea for clemency"

`reader_status.json` at the same time: `state: READING`, `next_action: keep reading`,
`last_error: null`, `pages_ok_10m: 44`.

## 4. Changed files

`backend/config.py` (appended), `backend/services/reader_scheduler.py`, `backend/services/web_reader.py`
(store fields, archive flag, licence override, paywall-title class), `backend/services/reader_report.py`,
`backend/services/source_scorecard.py`, `scripts/reader_pool.py`, `scripts/night_reader_supervisor.py`,
`scripts/dowjones_pull.py` (claims skip), tests: new `test_reader_browse_lane.py`, adjusted
`test_reader_pool.py` (its article count ignores the new front records), `test_lane_o_muratclaw.py`
(the social caps pinned host by host), `test_dowjones_chunk_j.py` and `test_pc_live_stack.py`
(sec.gov had been their example of an off-list host; now example.org).

## WHAT WORKS

- The list refills itself. An exhausted host goes back to its fronts after 20 min, and an empty list with caps free reads QUEUE_EMPTY with the seconds to the next revisit. It no longer triggers a restart.
- Breadth. 77 fronts on 15 hosts, with one-hop follows across hosts (for example a CNBC article to a Fed release). Official releases (Fed, BLS, SEC, Treasury) are read in the same loop as the papers.
- Every page read, fronts included, is one call away for the digest, with section, dateline, fetch time, outbound links, class and how it was reached.
- Refusals are recorded, not worked around. Reuters' robots.txt refused all six fronts and nothing was opened. Paywalls and blank runs are classified and cooled.

## WHAT DOES NOT

- **The memory-pressure recycle restarts the pool every ~15-20 minutes** (the existing memory-pressure rule in the supervisor; numbers in `backend/data/optimus/local_pc/`). The recycle itself is then refused (`OWNER_MAY_BE_USING: a tab the reader did not open is active`), but the pool has already been stopped. The pending links are now carried across, so the cost is about a minute per restart, not the list. The supervisor should decide about the recycle before it stops the pool. That code sits beside `gateway_repair.py`, which another agent was editing, so it was not changed here.
- The digest's first 50 asks were lost once: the pool that adopted them was restarted before the carry fix existed. Their adoption record was moved aside (`read_next_adopted_lost_before_carry_2026-09-29.jsonl`), they were re-adopted, and they now rank with the fronts. The first search pages were read at 04:02 UTC. Only 5 of the 8 search sites can serve them, because the CNBC and FT robots.txt files disallow search and Reuters disallows everything.
- Paywalled FT and Nikkei article pages stored before the paywall-title fix are in the store as OK. `page_class` cannot tell them apart; filter on the title "Subscribe to read".
- The age rule can only pre-filter links whose date is visible. An undated link is still read, and 24 of 77 recently stored articles were flagged `archive`.
- Reuters gives nothing (robots). BLS and SEC pages are mostly tables and short releases.
- The sustained pages-per-hour rate is not measured yet: no run has lasted 30 minutes without a restart.

## HIGHEST-EV EXPERIMENT

Measure whether the breadth pays before adding more of it. Over the next 5 trading days, take every
`pages_read_since` row whose `source_kind == "general_news"` or whose `reached_by.via` is `browse` or
`search`. Ask whether the digest's themes built from them named a sector or macro variable **before** its
largest move of the day more often than themes built from Dow Jones fronts alone. Use matched days and a
purely calendar-based control: themes from the same fronts one day stale. Cost: $0 in reads (they happen
anyway) plus the digest's own LLM spend. If general news adds no lead over Dow Jones fronts, cut the
news hosts to the official-release sites and spend the caps on depth instead.

---

## APPENDIX, 2026-09-29 afternoon: "always work" — why the dedicated Chrome went down, and what now recovers it

Machine-level evidence is under
`backend/data/optimus/local_pc/reader_drops_2026-09-29.md`, not here.

### Scoreboard

| line | value |
|---|---|
| RESULT IMPROVEMENT (money) | **NONE**. No reader output feeds a sized decision yet |
| Sustained run, no pool restart | **41.2 min** (pool launched by the supervisor, then left alone): **277 OK pages = 404 OK/hour**; full 10-minute buckets 59 / 83 / 76 OK pages (354-498/h). Not OK in the run: 6 ROBOTS_DISALLOWED (never loaded), 3 PAYWALL_STUB, 2 BLANK, 2 NOT_FOUND |
| OK/hour by host in that run | barrons 68.5, wsj 55.4, cnbc 43.7, asia.nikkei 43.7, scmp 43.7, marketwatch 39.3, apnews 35.0, bbc 29.1, finance.yahoo 13.1, ft 11.7, bls 8.7, federalreserve 5.8, home.treasury 2.9, sec 2.9. x / reddit / stocktwits: 0 (each at its 150-in-24-h cap, rolling; unchanged) |
| Kind of page (OK) | **general news 59.6%** (165), Dow Jones news and fronts 31.4% (87), **stock pages 9.0%** (25). Stock pages are few by design in the afternoon: every name was read inside its 20 h freshness window |
| X handle timelines | 37 registry handles now queued as `x.com/<handle>` profile pages (pool start line: "37 X handles"); none read yet because x.com is at 150/150 in the rolling 24 h (frees this evening) |
| Tests | new `backend/tests/test_reader_always_up.py` (20 tests); reader, browser and guard files re-run: 640 + 434 passed |
| LLM spend | $0 added |

### 1. The causes, with evidence

**The morning / midday drops were clean exits, not crashes: Chrome ends when its last tab closes.**
The dedicated Chrome's own session log records every start and exit. Its exits at 11:51, 12:56
and 15:31 local all read `EXIT tab_count 0`, and the next start says `crashed: false`; there is no
crash dump and no Windows error for them. The pool closes each tab after its read (the 09-28
"close, never blank" rule). Once the launch's about:blank start page was gone, the pool closing
its last open tab ended the browser. 12:56:05 was mid-reading (the gateway's last good request was
0.5 s earlier). 11:51 and 15:31 happened while the supervisor stopped the pool for a scheduled
recycle: the pool's own tab closes ended the browser before the recycle ran, which is why those
recycles logged "did not answer". Which step removed the start page is **not identified**. It was
seen vanishing live at 16:00:03-16:00:33 while the full test suite ran; the pool never recorded that
tab as its own. The "12:58:47" event is the supervisor relaunching the pool after it had relaunched
Chrome at 12:57:44. It was not a second drop.

**The ~15:23 event was a sleep, not a Chrome drop.** The machine was asleep for about two hours
(the event-log lines are in the local_pc record).
The dedicated Chrome and the pool both survived the sleep. On its first tick after resume the
supervisor's PID query came back empty, so it reported the live pool as down and read CHROME_DOWN from
an old log line. Its probe said PROFILE_DETACHED, and one attach fixed that. Then the overdue hourly
digest ran inside the loop. Nothing in the machine's settings was changed. Keeping the machine awake while away
is the owner's setting.

**Two further drops at 16:07:34 and 16:21:37 were real browser crashes**: crash dumps, and the next
start says `crashed: true`. The dumps show two different in-browser check failures. Both came at moments when this session added DevTools traffic (a test
run, then a diagnostic watcher). Causation is not shown. The diagnostic watcher was stopped. The
supervisor relaunched Chrome within about 70 s both times.

**Found on the way (not fixed, owner or builder decides):** the fast test suite's network guard allows
loopback, so a unit test can reach the LIVE dedicated Chrome and gateway. A diagnostic plugin that
refused ports 18802/18789 showed `test_pc_live_stack::TestOpenClawHealthCanActuallyGoGreen` (2 tests)
connecting to the live 127.0.0.1:18802. No other reader test did.

### 2. What changed

| change | where |
|---|---|
| **Anchor page.** One about:blank page is kept open in the proven dedicated Chrome. It is opened only when none is left. The supervisor checks every tick while the pool reads, and the pool checks before closing its **last** open tab | `gateway_repair.ensure_anchor_tab`; `reader_pool.Pool._keep_window` (`keep_window=` hook, None in tests); supervisor main loop |
| **Chrome down under a live pool** is caught on the next tick by a loopback port check, and repaired through the existing bounded `repair`. That repair launches ONLY the dedicated folder, only when no process holds it, with exactly `attach_argv()`. Before, the supervisor waited for the pool to fail and exit | `night_reader_supervisor.chrome_port_open`, main loop (`chrome_down_while_reading`) |
| **Launch verified by PID and command line.** The started PID must be a Chrome browser process whose OS command line has the dedicated `--user-data-dir`, `--remote-debugging-port=18802` and a loopback `--remote-debugging-address`. The other Chrome browser PIDs are listed before and after (`main_chrome_before/after`). A mismatch is reported (`verified: false`) and nothing is killed. Live at 16:22:47: `verified: true` | `muratclaw_instance.verify_launch`, `launch_attach` |
| **Sleep / resume.** A 60 s tick sleep that overruns by more than 120 s counts as a suspend. The next tick first probes and repairs (bounded), logs `resumed` with the seconds slept, reports STARTING instead of STALLED for 10 minutes, and holds the hourly digest for 15 minutes | `slept_through`, `resume_state`, `defer_digest_after_resume`, main loop |
| **A failed or empty PID query is not "the reader is down".** It falls back to the pool's own PID from its status file. That PID must be alive, be python, and have been created before the status was written, so a reused PID does not count. A failed query with no proof waits for up to 3 ticks and never relaunches a second pool beside a live one | `reader_pids_checked`, `live_reader_pids`, `pid_started_before` |
| **X handle timelines.** The registry's X handles are queued as `https://x.com/<handle>` profile pages: well-formed handles only, X's own route names refused, tier 2, once per `READER_X_HANDLE_FRESH_H` = 24 h, remembered per handle in `_social_seen.jsonl`. They are read-only like every social page: navigated, never typed, no click, follow or post. **Caps unchanged**: 37 handles spend at most 37 of x.com's 150 daily loads. `source_reads.guarded_pages` already prefers these profile pages | `social_browser_pull.x_handle_url / x_handle_items / registry_x_handles`; `reader_pool.Pool._refill_handles`, `_mark_read`, `social_last_reads`; `config.READER_X_HANDLE_FRESH_H` |
| Sign-in / free sign-up: **design only, not built** | `docs/research_notes/2026-09-29/browser_signin_signup_design_2026-09-29.md` |

### WHAT DOES NOT (still)

- The anchor makes the clean exit a non-event, but what removed the start page is unknown, and the two afternoon crashes are unexplained.
- Recovery after a crash still takes about 2 minutes. The pool exits on its failed re-attach, and the supervisor relaunches it one tick after repairing Chrome.
- The pool's `sustained_ok_per_hour` counts a sleep as run time. That is why it read 69.9/h after the two-hour sleep.
- Handle pages are untested live today (x.com is capped). The first reads will come when the rolling 24 h window frees.
- Resume handling is unit-tested only. The machine was not put to sleep on purpose.
