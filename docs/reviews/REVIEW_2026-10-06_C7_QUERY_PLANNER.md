# REVIEW 2026-10-06: C7, the query planner (adversarial, Opus 5.5)

Build under review: WIP commit `f4dbd0c0` (branch `wip/2026-10-06-v1-beta`), chunk C7.
Files: `backend/services/{query_planner,reader_scheduler,dowjones_feeds,llm_analyzer,web_reader}.py`,
`backend/data/news_sources.yaml`, `scripts/{reader_pool,night_reader_supervisor,daily_pass}.py`,
`backend/config.py`, `backend/tests/test_query_planner.py`.
Method: read-only code reading; read-only Python over the receipts and ledgers; two
throw-away simulations in a temp directory (no real file written); one live HTTP GET per
Dow Jones feed URL. The planner was not run, and neither was the reader or the gateway.

## RESULT IMPROVEMENT: NONE

The planner has produced 0 URLs, 0 pages, 0 claims and 0 forecast rows. OpenClaw's
`web_search` has no provider behind it, and `x_search` is not exposed. The feed URL fix is
the only change in C7 that produces anything: five WSJ feeds go from 607-day-old items to
live ones.

## VERDICT: MERGE WITH FIXES

The safety design holds up. Search-result URLs pass through the same `NEVER_HOSTS` /
`money_url_refusal` / allowlist path as everything else. They are checked again at pool
adoption. Quarantine has no code consumer, so nothing auto-admits. The landed-URL check
still covers redirects. The budget lane sits inside the 4,000 loads and is
work-conserving, so an idle planner costs the fixed reader nothing.

The "operating under no provider" logic and the yield receipt are another matter. The
degrade gate, as written, never fires on the real query mix. And the receipt can print
`YIELDING` for a page the planner never caused. Fix F1, F2, F3 and F4 before merge. F5 to
F9 can follow.

| # | Required before merge |
|---|---|
| F1 | Degrade gate counts an un-offered `x_search` turn as unavailable (or drops x_search until it is offered); better, REFUSE while no provider is declared |
| F2 | Yield attribution only by `lane == qp:<id>` AND page time >= query time; never by URL join over every lane |
| F3 | `pid_alive` for the planner must match the planner's own command line |
| F4 | Any tool call other than the query's own tool (incl. `web_fetch`) is a violation for a planner turn |

## Findings

### F1. HIGH: the "no provider, probe once per 24 h" gate never fires on the real templates

`run()` degrades only when the newest `QUERY_PLANNER_TOOL_UNAVAILABLE_STREAK` (3) ledger
rows all carry `tool_unavailable`. That flag is `tool_unavailable(errors)`, which is
`bool(errors) and all(...)`. An `x_search` turn where the tool is not offered fires no
tool and returns no tool result, so `errors == []` and the flag is **False**. Every
eighth query is an x_search: `templates()` sends every third held name there, and lanes
are interleaved. So every run's newest three rows hold an x_search row.

I simulated four runs of a day with `plan_queries` (all web_search rows unavailable, all
x_search rows not fired):

```
run 0 n 8 [h:w t:w o:w h:w t:w o:w h:x t:w]  tail [(web,True),(x,False),(web,True)]  degrade False
run 1 n 8 [h:w t:w o:w h:w t:w o:w h:x t:w]  tail [(web,True),(x,False),(web,True)]  degrade False
run 2 n 8 [h:w t:w h:w t:w h:x h:w h:w h:x]  tail [(web,True),(web,True),(x,False)]  degrade False
```

The gate stays off, and the planner spends all 24 agent turns a day on a known zero. The
dollars are trivial: about $0.0003 per turn at cache-hit rates, $0.007 a day. But each
run still makes 8 gateway turns, 8 session archives and 2 scope audits on a machine where
gateway RAM has already stalled the reader once (S58). The test
`test_a_known_unavailable_tool_is_probed_once_a_day_not_spent_on` passes only because its
fixture holds three hand-written `tool_unavailable: True` rows with no x_search among
them. It encodes the assumption, not the behaviour.

Also: only the 11th of the 11 live ledger rows carries `tool_unavailable: True`. The first
ten predate the error reader and are `None`. So the next `--due` run spends a full 8-query
run regardless.

**Fix.** The question a gate should ask is "is a provider configured?", not "did the last
three turns say no?". Add `QUERY_PLANNER_SEARCH_PROVIDER` (default `None`). With it unset,
the planner REFUSES with `NO_SEARCH_PROVIDER_DECLARED` before any agent turn and writes
one receipt per day, not one per launch. Configuring a search provider is an owner
decision: Brave is card-gated, and "no payments" binds. A paid API should not be probed
for into existence. If the probe is kept anyway, count an un-offered tool (tool not
fired, no tool result, reply says it is unavailable) as unavailable, and stop templating
`x_search` while it is absent from the agent's tool list.

### F2. HIGH: the yield receipt can print YIELDING for a page the planner never caused

`yield_report` attributes a page-log row to the planner when **either** its lane is
`qp:<id>` **or** its normalised URL appears anywhere in `query_planner_queue.jsonl`. The
URL join is over **every** lane, has **no time ordering**, and the planner only admits
allowlisted hosts. Those are the hosts the fixed reader already reads.

`run()`'s duplicate check covers only the planner's own queue, not the reader's stored
articles. The pool's `_adopt_planner` then rightly skips an already-stored URL. But the
receipt still credits the fixed lane's earlier read to the planner.

Demonstrated in a temp directory. A Barron's article was read on `front:barrons:markets`
**9 hours before** the query existed, and the same article later came back as a search
result:

```
YIELDING
query_planner 24h: YIELDING -- 1 queries ..., 1 admitted ...; planner pages 1 -> claims 1
-> forecasts 3; non-planner pages 0 -> claims 0 -> forecasts 0
```

The first time a provider exists, the most likely search hits are held names' WSJ /
Barron's / MarketWatch stories, and the fixed reader has usually read those already. So
the receipt's first "success" will be largely the fixed reader's work, relabelled.
Attribution is **inferred at report time by URL join**. It is not enforced at claim-write
time: `claims.jsonl` rows carry only `post_url`, with no lane and no `query_id`.

**Fix.**
- Planner page = page-log row with `lane.startswith("qp:")` and `t >= first_seen_utc` of
  that query. Drop the URL-only join.
- At admission, mark a URL the reader already stored (`WR.stored_urls`) as
  `already_read` rather than `admitted`, and count it separately. That is the novelty
  number (see Q7).
- Longer term, carry `reached_by.lane` / `query_id` from the stored article onto the
  claim row when the claim is written.

### F3. MEDIUM: the supervisor's "no earlier run still alive" guard is dead code

`planner_due(..., child_alive=pid_alive(planner_pid))` reuses `pid_alive`, which returns
True only when the process's command line contains `scripts.official_sources`. For the
planner's PID it always returns False.

The planner's own `--due` gate covers the common case, because rows are written per query.
It does not cover a planner that hangs before its first row is written: in
`scope_preflight`'s audit, in the gateway port probe, or in a first agent turn up to the
240 s timeout and beyond. In that case a second (and a third...) planner launches every
30 minutes, each one able to pass `--due` and read the same day cap before either writes.

**Fix.** `pid_alive(pid, needle)` with `"backend.services.query_planner"` for this call
site, plus a test that a live planner PID reads as alive.

### F4. MEDIUM: `web_fetch` is a "read" tool, so the run never stops on it, and the host classifier is bypassed agent-side

`OTS.READ_TOOLS` contains `web_fetch`. The planner stops a run only on a call outside the
read set (`OTS.is_read_call`). A planner turn told "call web_search once, open nothing"
that instead `web_fetch`es a URL is recorded as a normal read call. This is most likely
when search returns "no provider" and the model tries to be helpful by fetching a search
engine's HTML page. The prompt is then not enforced, and the fetched host never meets
`classify_url`. That is the ToS-refused scraping path the module docstring says is
refused (DuckDuckGo / Bing HTML).

This is an HTTP fetch from the gateway, not a logged-in browser tab, so it cannot transact.
But "refused stays refused on every path" is false for this path. The live run fired only
`web_search` (9 calls), so this has not happened yet.

**Fix.** For a planner turn, any tool other than `q["tool"]` is a violation (stop the
run). Better, run the planner turn under an agent profile that holds only the search tool.

### F5. MEDIUM: the two "removed" MarketWatch feeds are still pulled by the generic news path

`mw_marketpulse` and `mw_realtimeheadlines` were removed only from
`dowjones_feeds.FEED_IDS`. In `news_sources.yaml` both still read `implemented: true`, so
`news_registry.pullable()` returns them. `scripts/news_pull.py` and
`scripts/always_on_lab.py` keep polling them, and nothing there applies the new
`FROZEN_UPSTREAM` verdict.

No removal is recorded in the registry itself (no `implemented: false` + note, no retired
date). That is the registered way: `news_registry._validate_row` already requires an
`implemented_note` when `implemented` is false.

**Fix.** Set `implemented: false` with `implemented_note: "FROZEN_UPSTREAM since <date>,
measured 2026-10-06; feeds.content.dowjones.io and feeds.marketwatch.com serve the same
frozen file"`. Keep `RETIRED_FEED_IDS` as the receipt's naming.

**Feed verification (live GET, one each, read-only):**

| feed | HTTP | items | newest item (UTC) | age |
|---|---|---|---|---|
| wsj_markets `feeds.content.dowjones.io/public/rss/RSSMarketsMain` | 200 | 61 | 2026-10-06 16:45 | 1.0 h |
| wsj_business `.../WSJcomUSBusiness` | 200 | 85 | 2026-10-06 17:28 | 0.3 h |
| wsj_world `.../RSSWorldNews` | 200 | 70 | 2026-10-06 17:28 | 0.3 h |
| wsj_opinion `.../RSSOpinion` | 200 | 100 | 2026-10-06 16:11 | 1.6 h |
| wsj_tech `.../RSSWSJD` | 200 | 40 | 2026-10-06 17:28 | 0.3 h |
| mw_marketpulse (both URL families) | 200 | 30 | **2025-07-03** | ~11,000 h |
| mw_realtimeheadlines (both URL families) | 200 | 10 | **2025-06-11** | ~11,600 h |

- All five new WSJ URLs are current; the fix is right.
- Both MW feeds are dead upstream, not a parser issue: the raw `<pubDate>`s are 15+
  months old, and the old `feeds.marketwatch.com` URL serves a byte-identical file.
- The "since" dates in `RETIRED_FEED_IDS` (2025-02-13 / 2025-05-06) are wrong. The feed's
  own newest items are 2025-07-03 / 2025-06-11. The dates came from `_newest_published`,
  which reads the local **store**, not the feed. So `feed_verdict`'s age measures what we
  stored, not what the feed serves. Low severity, but the docstring should say so: a feed
  serving fresh items that fail to store would read FROZEN_UPSTREAM.

### F6. MEDIUM: the non-planner per-host claim column is always zero

In `yield_report`, non-planner claims are bucketed by `ot_host[_host(u)]` with
`u = _norm(post_url)`. `WR.norm_url` is scheme-less (`marketwatch.com/story/...`), so
`urlsplit(u).hostname` is None and every claim falls into the `""` host, which is not in
the top 12.

Measured on the live files: `non_planner.claims = 52` while every `by_host_top` row shows
`claims: 0` (wsj 441 pages / 0, barrons 337 / 0, marketwatch 388 / 0). The 52 claims
really sit on barrons 148 / wsj 31 / marketwatch 30 over the week. That breaks exactly the
per-host comparison the planner needs (Q7). The planner side is unaffected, because it
takes its host from the page log.

**Fix.** Bucket by `_host(c["post_url"])` (the raw URL), and add a test with a real
`https://www.` post_url.

### F7. LOW: a receipt per launch, and a full predictions scan per launch

`done()` writes `query_planner_<run_id>.json` on every outcome, NOT_DUE and REFUSED
included. Each one runs `yield_report`, which scans the 52 MB `predictions.jsonl`. With
the supervisor launching every 30 minutes, that is 48 receipts a day. They are untracked,
never pruned and not ignored, in a directory already holding several hundred untracked
receipts.

**Fix.** Do not write a receipt for NOT_DUE (append one line to the ledger's sidecar log
instead), and keep the yield computation for real runs and the daily pass.

### F8. LOW: the cap is the same arithmetic, not the same ledger

`spent` sums `priced_cost_usd` from `openclaw_client.agent`. That uses the same tokens,
model string and `LT.price_call` that `_record_telemetry` writes; I verified that 11
`query_planner` rows are in `llm_calls_2026-10.jsonl` with `agent: "openclaw"`. That is
acceptable. It is in-memory per run, though, with no daily USD cap that reads the
ledger. The day budget is bounded only by the query count, which is persisted in
`query_planner_ledger.jsonl` and so survives supervisor relaunches. Fine at today's
prices.

The cap cannot bind in practice: 8 turns × $0.03 unknown-cost ≤ $0.24 < $0.30. It is a
declared ceiling, not a working control.

`llm_analyzer.openclaw_usage`'s docstring says `usd` is "priced at current list prices",
but the code sums the row's stored `cost_usd` and reports repricing separately. Fix the
docstring.

### F9. LOW: the tests

- Mock-asserting test: `test_daily_pass.py::test_every_declared_step_runs_in_order`. The
  new `dowjones_feeds` / `query_planner_yield` entries are appended by the monkeypatched
  fakes `_feeds` / `_yield` (`seen.append(...)`), so the assertion is that the stubs were
  called in order. It proves wiring, not behaviour. It is acceptable for an order test,
  but it is the only daily-pass coverage of the two new steps' refusal branches.
- `test_a_known_unavailable_tool_is_probed_once_a_day_not_spent_on`: its fixture cannot
  contain the case that breaks the gate (F1).
- `test_the_yield_attributes_pages_claims_and_forecasts_to_the_query`: it never puts a
  queued URL on a non-`qp:` lane read before the query (F2).

Suite result (the requested `test_llm_guards*.py` glob matches no file; I substituted the
LLM guard / telemetry / provider files and the reader-feeds file):

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest
  backend/tests/test_query_planner.py backend/tests/test_daily_pass.py
  backend/tests/test_automation_fixes_2026_10_02.py backend/tests/test_dowjones_chunk_j.py
  backend/tests/test_dowjones_parent_marker.py backend/tests/test_llm_language_guard.py
  backend/tests/test_llm_provider_declaration.py backend/tests/test_llm_telemetry.py
  backend/tests/test_reader_opens_and_feeds.py -q
323 passed in 9.94s   (exit=0)
test_signal_reachability.py + test_reader_budget.py: 38 passed
```

The C3/C12 mid-way daily-pass failures do not reproduce. The step box carries
`query_planner_yield: 120` in `config.py`.

## Axis answers

1. **Read-only and host safety.** Holds for the browser path.
   - `classify_url` applies `NEVER_HOSTS` (MONEY/CHECKOUT/MESSAGE, subdomains via suffix
     match), `url_refusal`/`money_url_refusal` (checkout paths on any host), the planner's
     refused list and then the allowlist.
   - Shorteners (`t.co`, `bit.ly`) and every unreviewed host are QUARANTINED. They are
     written to a file that **no code reads**: no auto-admit path exists, and "review"
     means a human editing the allowlist.
   - The pool re-checks `WR.host_ok` at adoption.
   - A redirect off-host after navigation is caught by `left_allowed_hosts` →
     `REFUSED_LEFT_HOSTS`. That check is post-load, as for every reader page. The planner
     adds no new class here, only more URLs on the same hosts.
   - Planner pages go through the same pool / `open_lane_tab` path, so the
     `aegis=muratclaw` marker-tab confinement is unchanged.
   - The gap is agent-side `web_fetch` (F4).
2. **Budget binding.** Same arithmetic, not a ledger read (F8). The 24/day count is
   persisted in the planner ledger and survives relaunches. The 3% lane is inside the 4,000
   (taken from markets_news 0.20→0.18 and digest_asks 0.06→0.05), and it is
   work-conserving.
3. **"No provider" degradation.** It does not engage (F1). The state lives only in ledger
   rows and receipts. It is not on any health surface; the daily pass carries only the
   `query_planner_yield` line, as `nothing_to_do`. It should REFUSE until an operator
   declares a provider.
4. **Feeds.** Verified live (table under F5). The removal skipped the registry (F5).
5. **Yield receipt.** Yes, it can produce a plausible non-zero without a planner read
   (F2). Attribution is inferred later, not enforced at claim-write time.
6. **Daily-pass collateral.** Green (F9).
7. **Operator's question** (below).

## Q7: what would make the planner worth its 3%

The one measurement is **claims per page read on planner-caused, not-already-read URLs,
against claims per page on fixed-lane pages of the same hosts in the same window**. Put
simply: the planner's marginal claim rate, compared with what the fixed reader would have
earned on those 120 loads.

- Today the fixed reader runs at 52 claims / 2,447 pages ≈ **2.1 %** in 24 h, with
  barrons pages carrying most of it.
- At 120 planner loads a day, a week is ~840 pages. Matching the baseline means ~18
  claims. Telling 2× from 1× at that size needs about two weeks of data.
- The receipt prints planner and non-planner pages and claims, so a pooled ratio can be
  derived by hand.
- It does **not** compute the ratio, the same-host comparison (broken, F6) or novelty
  (`already_read` share, F2).

Until it does, a positive planner number cannot be told apart from the fixed reader's
work. The secondary number that matters for the mission is lead time: minutes between a
planner page's `first_seen_utc` and the first time the fixed reader reached the same
article. "Search finds it first" is the planner's whole argument.

## Three things I would have done instead

1. **No LLM turn for a templated query.** The query text is fixed by template, so the agent
   is only a transport to a search tool that does not exist. A keyless plain-HTTP query
   feed is $0, deterministic and has no agent scope to audit: per query, a published RSS
   search endpoint for news, or EDGAR full-text search for filings. The builder's own note
   names Google News RSS as the closest lawful option. It returns URLs directly. The
   OpenClaw path can wait until a provider is authorised.
2. **Gate on a declared provider, not a streak.** One config key, REFUSE until set, one
   receipt a day. Do not ship `x_search` templates for a tool the agent does not have.
3. **Build the novelty-and-lead-time join first, then the search.** Before any search runs,
   ask of the existing digest asks and section fronts: what fraction of the articles a
   search would plausibly return has the fixed reader already read, and how late? If that
   fraction is above ~80%, the planner's ceiling is low and the 3% belongs elsewhere.

## Score: 64 / 100

- Safety architecture and refusal naming: strong (+).
- Feed fix: correct and verified (+).
- Spend telemetry: honest (+).
- Lost points for a degrade gate that cannot fire on the real query mix, a yield receipt
  that can credit the fixed reader's work to the planner, a dead child-alive guard, a
  `web_fetch` hole in "refused stays refused", a feed removal that did not reach the
  registry, and a broken per-host comparison column.
