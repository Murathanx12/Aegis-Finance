# C7: the search-led query planner, the Dow Jones feeds owner, OpenClaw spend (2026-10-06)

**Role:** Opus builder, from `openclaw_open_web_and_model_audit_2026-10-06.md` §D and roadmap
`ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md` §5 row C7. No commit. The gateway and the
reader supervisor were not restarted. `~/.openclaw/openclaw.json` and `.env` were not touched.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT (money) | **NONE.** This is plumbing and a measurement. |
| First live planner run | `dowjones/query_planner_20261006T162334Z-988931.json`: **10 queries, 9 `web_search` calls fired, 0 URLs**, 0 admitted / 0 quarantined / 0 refused, **$0.0033** |
| Why zero (measured, not guessed) | OpenClaw answers every `web_search` with **`web_search is disabled or no provider is available.`** `x_search` is **not exposed** to the agent at all; the model said so and did not invent URLs. |
| Second run (1 query, with the tool-error read) | `query_planner_20261006T162716Z-28f059.json`: `tool_unavailable: 1`, the error text is on the ledger row |
| Read-only scope, after both runs | `verdict OK`, 10 tool calls in 24 h, all `web_search`, **0 outside the read set** |
| `dowjones_feeds` health row | **ALIVE**: `feeds_2026-10-06.json`, 8 feeds, 379 items |
| WSJ "607-day" defect | **not a parser bug.** The five `feeds.a.dj.com/rss/*.xml` URLs were retired and are frozen at 2025-01-27. They were moved to `feeds.content.dowjones.io/public/rss/<same name>`, and the newest items are now 0.2-0.9 h old. |
| Found by the new frozen verdict | `mw_marketpulse` (frozen since 2025-02-13) and `mw_realtimeheadlines` (since 2025-05-06). No live copy was found, so both are retired and named on every receipt. |
| OpenClaw spend on `llm_usage()` | new `openclaw` block: **687 calls, $9.61 at call-time prices** ($6.17 repriced at today's prices), 40 unpriced, so the total is a lower bound. Last call 2026-09-29T23:36Z; 0 in the last 7 days. |

## 1. Design

```
seeds (files)                     queries (templated)        one agent turn per query
 held: pc_snapshot + fleet state ─┐                           openclaw_client.agent(session_id=ours)
 themes: newest world_digest     ─┼─> plan_queries ─> prompt ─> "call <tool> once, list URLs, open nothing"
 opportunities: roi_v3            ┘   (day/lane/run caps)        │
                                                                 ├─ transcript: tool calls (read set?) + tool errors
                                                                 v
                          classify_url: REFUSED | ADMITTED | QUARANTINED
                                         │            │           └─> dowjones/query_planner_quarantine.jsonl (human review)
                                         │            └─> dowjones/query_planner_queue.jsonl {first_seen_utc, query_id, discovered_via}
                                         └─> nowhere      │
                                                          v
                     reader_pool._adopt_planner -> lane qp:<query_id>, budget lane `query_planner`
                                                          v
                     page_log (lane qp:<id>) -> claims.post_url -> predictions.inputs_used.claim_hash
```

- **Module:** `backend/services/query_planner.py` (`--plan`, `--run [--max N] [--due]`, `--yield`).
- **Caller:** `scripts/night_reader_supervisor.py` launches `query_planner --run --due` out of
  process every 30 min (recorded PID, one log per run under `dowjones/query_planner_logs/`). The
  planner decides from its own ledger whether it is due (`QUERY_PLANNER_EVERY_H = 6`), so a
  supervisor restart cannot double a day's queries. The change takes effect when the task keeper
  next relaunches the supervisor (the rolling `--until`). The running supervisor was not touched.
- **Queries are templated, never model-written.** Held name: `<T> stock news this week`, and every
  third held name gets `x_search "$<T>"`. Theme: `<title> <2 keywords> market impact`. Opportunity:
  `<T> stock catalyst news`. Least-recently-searched seed first. The lanes are interleaved, so one
  run covers every lane before it repeats one.
- **Budgets** (`backend/config.py`, QUERY PLANNER block): 24 queries/day, 8 per run, per lane
  held 12 / themes 8 / opportunities 4, 6 URLs per query, 120 admitted URLs/day, $0.30 per run
  (an unpriced turn is charged $0.03, never zero). Reader budget: a new `query_planner` lane takes
  **0.03 of the same 4,000 loads** (markets_news 0.20 to 0.18, digest_asks 0.06 to 0.05). The lane
  is work-conserving, so an idle planner lane lends its share to the other lanes.
- **Safety gates, in order:** STOP file `dowjones/QUERY_PLANNER_STOP`, then the enabled flag, then
  `--due`, then the read-only tool-scope audit (`openclaw_tool_scope.audit`: any config problem or
  any out-of-set call in 24 h means REFUSED), then the gateway port. Inside the run:
  - a tool call outside the read set **stops the run**;
  - URLs from a turn whose search tool never fired are **REFUSED as `NO_TOOL_CALL`**, because a
    model listing URLs from memory is not a search result;
  - once 3 consecutive queries say "no provider", the planner **probes once per 24 h** instead of
    spending its budget on a known zero.
- **Classifier:** refused hosts stay refused on every path. That covers `web_reader.NEVER_HOSTS`
  (bank, broker, payment, mail, message, checkout providers), `browser_policy.url_refusal` /
  `money_url_refusal` (checkout and payment paths on any host), and `QUERY_PLANNER_REFUSED_HOSTS`:
  YouTube, Instagram, Facebook, TikTok, LinkedIn, consumer-AI chat UIs, the DuckDuckGo / Bing /
  Google pages, Senate eFD, PBoC and the Nasdaq API (the audit's §C verdicts). Admitted means
  `web_reader.host_ok`, the reader's own allowlist, social hosts included. **Anything else is
  QUARANTINED: it is never queued and never auto-allowed.** The reader pool re-checks `host_ok`
  when it adopts a URL. `source_registry.score` is **not** the gate: it grades a `source_id` by
  its forward skill, and a search hit has no source id until a claim is read from it. The
  reputation join happens downstream, unchanged.

## 2. Why the first run yielded zero, and what would change it

Every `web_search` turn's tool result (read-only from `agents/main/agent/openclaw-agent.sqlite`)
was:

> `web_search is disabled or no provider is available.`

So the audit's line "allowed but never invoked" was true and incomplete. The tool is **allowed by
policy and has no provider behind it**. `x_search` does not even appear in the agent's tool list.
The model's own reasoning was: *"I have no such tool. I should not invent URLs."* That honest
answer is a good thing, and the `NO_TOOL_CALL` refusal would have caught it if it had gone the
other way.

Making the planner yield needs an **owner decision**, because each option needs either an
`openclaw.json` change (which builders do not make) or an account:

1. a search provider configured in OpenClaw (the audit §C/§E: Brave Search API is card-gated
   since Feb 2026, which conflicts with standing rule 1 unless the owner authorises it);
2. or a different lawful search primitive. Of what is already allowed and keyless, Google News RSS
   per query is the closest.

The planner's seeds, budget, classifier, queue, pool adoption, attribution and receipts are all
live now. Once a provider exists, the next `--due` run produces URLs with no further code change.

## 3. The Dow Jones feeds fix

- **Owner:** a `dowjones_feeds` step in `scripts/daily_pass.py`, right after `news_pull`. It does
  the same pull, writes the same `dowjones/feeds_<day>.json` and never touches the browser.
  The daily pass is already in `task_keeper`'s catch-up list, so a missed morning is caught up.
- **The 607-day age, reproduced.** A plain GET of `https://feeds.a.dj.com/rss/RSSMarketsMain.xml`
  returned 200 with 20 items; `lastBuildDate` and every `pubDate` were `Mon, 27 Jan 2025 ... -0500`.
  The RFC 822 parse is right (14:26 -0500 parses to 19:26 UTC), so **the URL was retired**. The
  same names under `feeds.content.dowjones.io/public/rss/` are live. The five endpoints in
  `backend/data/news_sources.yaml` were updated. Fixtures (guid and pubDate kept as captured;
  headlines, summaries and links redacted under DJ ToU 9.1) are
  `backend/tests/fixtures/news/wsj_markets_{retired,live}_url_2026-10-06.xml`.
- **So a dead feed can never read as healthy again:** `dowjones_feeds.feed_verdict` marks a feed
  whose newest item is older than `DOWJONES_FEED_FROZEN_AGE_H` (14 days) as `FROZEN_UPSTREAM`. It
  goes into `refused_or_red`, which turns the health row STALE. On its first run this verdict
  found `mw_marketpulse` and `mw_realtimeheadlines` frozen as well (newest items 2025-02-13 and
  2025-05-06; their `feeds.content.dowjones.io` URLs are the frozen ones, and no live copy was
  found). Both are moved to `dowjones_feeds.RETIRED_FEED_IDS` and printed on every receipt. A row
  that can only ever be red is not a check.
- **Health after one run:** `p_dowjones_feeds` reports `ALIVE ... 8 feeds`.

## 4. OpenClaw spend on the health surface

`llm_analyzer.llm_usage()` now carries an `openclaw` block from `llm_analyzer.openclaw_usage()`.
It reads the `agent="openclaw"` rows in the newest two monthly telemetry files incrementally
(append-only, so only new bytes are read; cold read about 0.8 s, warm about 1 ms). The block
reports calls, ok, `usd` at call-time prices, `usd_repriced_today_prices`, `unpriced_calls`,
`usd_is_lower_bound`, `last_call_utc`, today and 7-day totals. How OpenClaw writes was not
changed. Under pytest it reads nothing and says `NOT_READ`.

## 5. Consent pop-ups

The audit rule was specific, so it is built as a **pure, tested function and not wired in**:
`web_reader.consent_dismiss_ref(snapshot, clicks_this_page=)`. The rule:

- exact whole-phrase allowlist (`CONSENT_PHRASES`);
- button or link role only, and a link must not leave the page;
- a deny regex for sign / subscribe / email / account / pay / trial / offer / marketing;
- exactly one candidate (it prefers "Reject all" / dismiss when several different ones show);
- at most one click per page load; a second banner means STOP.

It is **not connected to any click**. The `openclaw_client` click guard still refuses every
button, and `READER_CONSENT_DISMISS_ENABLED` is absent (a test pins it off). Standing rule 3
lists the read-only verbs, and a button click is not one of them. Switching it on is the owner's
call.

## 6. How to read the yield tomorrow

- **Daily pass:** the `query_planner_yield` row prints one line, for example:
  `query_planner 24h: <ZERO_KIND> -- N queries (F tool fired, U tool unavailable), K URLs, a admitted / q quarantined / r refused; planner pages P -> claims C -> forecasts R; non-planner pages ... ; spend $...`
- **`zero_kind`** names which zero it is:
  - `NO_QUERIES_RAN`: nothing was issued (refusal, budget, not due);
  - `QUERIES_RAN_NO_TOOL_CALL`;
  - `TOOL_FIRED_BUT_UNAVAILABLE`: today's state;
  - `QUERIES_RAN_NO_URLS`;
  - `URLS_FOUND_NONE_ADMITTED`: look at the quarantine file;
  - `ADMITTED_NOT_YET_READ`: the pool has not adopted them yet;
  - `PAGES_READ_NO_CLAIMS`;
  - `CLAIMS_NO_FORECASTS`;
  - `YIELDING`.
- **Note on the next 24 h:** the 24 h window still holds the 10 ledger rows written before the
  tool-error read existed. The line will say `QUERIES_RAN_NO_URLS` until those rows age out or
  the gate's probes accumulate. The error itself is recorded on every later row.
- **Per run:** `dowjones/query_planner_<run_id>.json` carries per-query tool calls, tool errors,
  URLs with verdict and reason, cost, scope before and after, and the same yield block.
- **Quarantine review:** `dowjones/query_planner_quarantine.jsonl`. A host is allowed only by
  adding it to the reader allowlist by hand. Nothing promotes one automatically.
- **Commands:** `python -m backend.services.query_planner --yield` (files only) and `--plan`
  (prints, runs nothing).
