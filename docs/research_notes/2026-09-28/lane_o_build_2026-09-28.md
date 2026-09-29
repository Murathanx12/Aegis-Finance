# LANE O build, 2026-09-28: only MuratClaw, a supervisor that repairs, one guarded HTTP path

**RESULT IMPROVEMENT: engineering and live verification only.** No page was read for research, the
queue was not run, `HANDOFF_PC` was not created. What changed is what the browser *can* reach and
how a jammed gateway gets fixed.

## 0. Scoreboard for this lane

| item | state |
|---|---|
| Browsers OpenClaw can reach | **one**: the dedicated Chrome, its own dedicated profile folder, 127.0.0.1:18802 |
| `user` / `chrome` profiles | redefined as attachOnly on closed port 9 in `openclaw.json`; refused **by name** in Aegis (`REFUSED_MAIN_CHROME_PROFILE`) |
| Proof before every action | 6 steps (config, endpoint, Chrome's own PID, the OS command line, the port's listener, the tab's endpoint) |
| Main Chrome (PID and start time recorded locally) | same PID and start time before, during and after every live step |
| Kill test | **passed on run 2**: gateway killed 14:50:28, healthy 14:51:24 (repair 45.5 s). **Failed on run 1**: free memory far below the measured floor, the gateway did not bind for 19.6 min (section 3) |
| Seconds per verb, CLI vs HTTP (live) | CLI 10-14 s per verb; HTTP 0.06-2.1 s (open 2.06, tabs 0.45, press 0.36, evaluate 0.38, close 0.06); one page read sequence took 139.9 s on the CLI and 38.8 s over HTTP |
| Guard counts per action, CLI vs HTTP (live, same sequence) | identical: `verb_allow 4, denied_domains 2, policy_url 2, host_allow 1, instance 6, host_before 4, host_after 1, policy_press 1, own_tab 1` |
| Tests | prescribed command **exit 0, 1,026 passed**; new file `test_lane_o_muratclaw.py` has 87 tests |

## 1. What was built

| file | what |
|---|---|
| `~/.openclaw/openclaw.json` | `browser.attachOnly: true`; `profiles.muratclaw = {attachOnly, cdpUrl: http://127.0.0.1:18802}`; `user`, `chrome`, `openclaw` = `{attachOnly, cdpUrl: http://127.0.0.1:9}`. Applied with `openclaw config set --batch-file` after a `--dry-run`. **Hot-reloaded: no gateway restart was needed** (`openclaw browser profiles` showed the new ports at once, despite the CLI printing "Restart the gateway to apply"). |
| `backend/services/muratclaw_instance.py` (new) | `prove()`, `status()`, `launch_attach()`, `config_problems()`. Every side effect is injectable (`Probes`). |
| `backend/services/browser_policy.py` (new) | The owner's rules as pure refusals: payment text/URLs, message text/URLs, social write paths, scroll-only keys, click only on a seen link. Also one snapshot parser for both shapes. |
| `backend/services/openclaw_http.py` (new) | A transport: argv to `POST /tools/invoke`, reply to CLI-shaped stdout. Holds **no policy**. |
| `backend/services/gateway_repair.py` (new) | `classify_exit`, `probe`, `repair`, `RepairBudget`. |
| `backend/services/openclaw_client.py` | profile rules; `_instance_check` before every action; `open_tab` (dedicated only); owner rules; per-tab snapshot memory for the click rule; transport routing in `_run`; `_guard()` counters on the ledger; `health()` rows `browser_ready`, `instance`, `transport`. |
| `backend/services/web_reader.py` | `parse_snapshot` reads inline `[url=]` (**the new driver returned 0 links on every page otherwise**); social hosts; per-host daily caps; `pick_next_lane` / `host_aware_order`; `YieldCheck`; `read_social_page` / `store_social` (`source_kind = "social"`); raw CDP ids are stable handles; attach refuses `REFUSED_INSTANCE_DOWN` for the dedicated profile. |
| `scripts/dowjones_pull.py` | profile default `muratclaw`; `instance_gate()` after every attach, before any tab is resolved (archive, plan, launcher); the marker still binds on an operator profile that is not dedicated (none today); yield check in `run_plan`. |
| `scripts/night_reader_supervisor.py` | classify, probe, repair, `decide()`; no relaunch while the dependency is down; `--probe`, `--repair-once`. |
| `scripts/social_browser_pull.py` (new) | Social lanes: one tab per host, host-aware rotation, handoff-gated, rows tagged social. |
| `backend/config.py` | OpenClaw/reader constants only. **Pace values untouched** (O6, owner's decision: keep the current 6-20 s / 18 s / 180 per hour). |
| `backend/data/optimus/dowjones/queue_run.cmd` (untracked) | `--profile user` changed to `--profile muratclaw` (backup in the session scratch). |

Why the marker went: with OpenClaw attached only to the dedicated Chrome, every tab it lists is a
MuratClaw tab. The guard was replaced, not deleted: `instance_gate` refuses before any tab is resolved
unless the endpoint is proven to be that Chrome.

**How the proof works, measured live:** `Browser.getBrowserCommandLine` refuses without
`--enable-automation`, and `DevToolsActivePort` is not written for a fixed port. `SystemInfo.getProcessInfo`
does name the browser PID, and that PID's OS command line names the folder and the port.
First proof 3.5 s (PowerShell), cached per browser GUID after that (about 0.01 s plus 2 loopback GETs).

## 2. Live verification (what was run, in order)

1. Backed up `openclaw.json` to `openclaw.json.bak_lane_o_2026-09-28`, then applied the config (dry run first).
2. Closed the dedicated Chrome gracefully by its PID (`taskkill /PID` without `/F`, after re-confirming its
   command line). It exited in 1.1 s. Relaunched it with the attach launcher; port up in 0.6 s (new PID recorded locally).
   The Preferences file still lists **2 accounts** after the relaunch.
3. `openclaw browser --browser-profile muratclaw tabs` listed **one tab**, whose targetId equals CDP's own
   `/json/list` page id. `chrome` lists `[]`.
4. CLI route: opened the MarketWatch front page, snapshot (40 links), PageDown, read the title
   ("MarketWatch: Stock Market News..."), closed the tab. HTTP route: the same on the Barron's front page (53 links).
5. Ten refusals fired by name, none reaching OpenClaw: `REFUSED_MAIN_CHROME_PROFILE` (user, chrome),
   `REFUSED_PAYMENT_URL` (marketwatch /subscribe, store.wsj.com), `REFUSED_MESSAGE_URL` (Gmail),
   `REFUSED_DOMAIN` (app.alpaca.markets), `REFUSED_PRESS_KEY` (Enter), `REFUSED_OPERATOR_VERB` (type),
   `REFUSED_SOCIAL_WRITE_URL` (x.com/intent/tweet), `REFUSED_OPERATOR_HOST` (sec.gov).
6. Sign-in, front pages only:
   * **WSJ: signed in.** The account button reads "Murathan Abdullaev".
   * **Barron's: appears signed out.** The header shows "Sign In".
   * **MarketWatch: undetermined.** Neither marker appears.
7. HTTP `navigate` to marketwatch.com/markets: rc 0 in 15.9 s, landed URL read from the reply. One
   earlier HTTP navigate (a reload to the identical URL) returned **rc 1** after 21 s, cause
   unexplained. The landed-URL check fell back to a fresh listing correctly.

## 3. O2: which reset clears the latch, and the kill test

**The latch was present this morning.** After the config reload, `user` answered "Chrome MCP subprocess
tree cleanup could not be verified" (in-memory state from last night's Chrome-MCP session).

| candidate | result |
|---|---|
| `browser stop` on the profile | **did not clear it** ("lifecycle changed while work was pending") |
| end an orphaned `chrome-devtools-mcp` by PID | **nothing to end**: no such process existed. The latch was pure in-memory state. |
| gateway process restart | **cleared it**: after the restart `user` status answered normally |

The ladder keeps the two light resets first because they cost seconds. On this evidence, though,
only a process restart clears this latch. The new `muratclaw` profile uses the openclaw (Playwright)
driver, not Chrome-MCP. The component that jammed last night is therefore off the reader's path
entirely. Only the disabled `user` profile could still latch.

**Kill test, run 1 (FAILED, and it taught the ladder two rules).** I killed the listener by PID
at 14:30:01. The old ladder then ran `gateway start` (CLI timed out at 120 s), waited 90 s, ran
`gateway restart` (timed out at 180 s), and waited again. The port stayed closed. The cause was
**free memory far below the measured floor**: other builders' jobs were running, and the handoff had already recorded
that the gateway will not bind at such low free memory. Worse, `restart` ended the scheduled task's root
while the tree from `start` was still coming up, so **two gateway trees** competed for one port. I
ended my orphan tree by PID (confirmed as mine). The task's tree bound the port at 14:49:40,
once free memory recovered well above the floor: **19.6 minutes after the kill**.

Two rules came out of this, both in code and tests:
* no gateway (re)start below `OPENCLAW_REPAIR_MIN_FREE_GB` (the measured memory floor; it reports `LOW_MEMORY` and waits);
* never `gateway restart` while a gateway process is still starting (it reports
  `GATEWAY_STARTING_SLOW` and waits for the port instead).

**Kill test, run 2 (PASSED, ample free memory).** Killed the listener by PID at 14:50:28. Repair started
at 14:50:36: the probe took 2.6 s, then `gateway start` ("Started Scheduled Task") cleared it in
41.9 s. Healthy at 14:51:24, **about 56 s from kill to healthy**. One gateway tree was left.

Bounds: at most 3 repairs in any rolling hour, with backoff doubling from 60 s. The reader is never
relaunched while the probe is unhealthy; its own relaunch backoff also doubles (60 s up to 30 min). A
replay of last night (20 ticks against a latched gateway) produces 0 relaunches and at most 3 repairs
per hour (test). `NOT_MURATCLAW` is never auto-repaired.

## 4. O4: tool access. Proposed, NOT applied (the owner confirms)

**Urgent, and caused by this lane's O1 change.** OpenClaw's own LLM agent turns have a `browser`
tool. Its default profile is now the **signed-in** dedicated Chrome, and that tool bypasses every
Aegis guard: payments, messages, clicks, typing, `evaluate`. Before today the default was the
never-signed-in managed Chrome. Three agent prompts tell the model to use the browser on a logged-in
account:
* `scripts/source_reads.py` (X profiles);
* `backend/services/fast_mover_forensics.py`;
* a thesis-card prompt (`Use your browser / web tools, and the logged-in X (x.com) account`).

`AegisDailyPass` runs on a schedule.

Proposed change (one command, dry-run first):

```
openclaw config set --batch-json "[{\"path\":\"agents.entries.main.tools.deny\",\"value\":[\"browser\"]},{\"path\":\"tools.profile\",\"value\":\"coding\"}]" --dry-run
```

What each part does:
* `agents.entries.main.tools.deny: ["browser"]`: LLM agent turns lose the browser. X reading moves to
  the guarded social lane (`scripts/social_browser_pull.py`). This **also denies `browser` to
  `POST /tools/invoke`**, which evaluates the `main` agent's policy (`tools-invoke-shared`,
  `sessionKey` defaults to "main"). To keep the HTTP transport, also add an agent entry
  (`agents.entries.aegis-browser: {}`) and set `config.OPENCLAW_HTTP_AGENT_ID = "aegis-browser"`.
  The CLI transport (the gateway's `browser.request`) is not subject to tool policy.
* `tools.profile: "coding"` (today it is unset, which resolves to `full`): drops `computer`,
  `group:nodes` and the optional plugin tools. It keeps `group:fs`, `group:runtime`, `group:web`,
  `group:sessions`, `group:memory`, `cron`, and `gateway` (update only).

What must keep working, and why it still does:
* The Aegis Telegram agent does not use OpenClaw channels: `channels: {}`, and Aegis's own
  `telegram_bridge` talks to Telegram directly.
* The gateway itself is unaffected.
* Agent-only turns (thesis cards, investigator, price calibration) need no browser.
* `exec` stays behind exec approvals as today.

Rollback: `openclaw config unset agents.entries.main.tools.deny` and `openclaw config unset tools.profile`.

## 5. Owner decisions and notes (plain)

* **Brokers:** Murat asked that the agent "can login to alpaca anything". The orchestrator declined and
  he agreed ("u are right dont give alpaca or brokers to openclaw"). `alpaca.markets` and every
  brokerage, bank and payment host stay refused (`REFUSED_DOMAIN`). The broker is reached only
  through `pc_broker`'s API path.
* **Account risk:** X, Reddit and Dow Jones terms all restrict automated access. Reading with a
  signed-in account carries account risk on each. He has been told and has decided. Nothing here
  hides the automation.
* **Allowlist:** wsj / barrons / marketwatch plus x.com, reddit.com (incl. old.reddit.com) and
  stocktwits.com, the last three **read-only** (no click at all). Adding a free site such as sec.gov
  needs his decision per host. sec.gov is already read over its HTTP API, which is the better path.
* **Pace:** unchanged (his decision). Social hosts have a cap of 150 pages per day each.
* **Future "form task" (not built):** a named task file he approves; a field allowlist; no payment
  fields ever; no password invented or stored in the repo (he types it, or it comes from his own
  vault at run time); a screenshot before submit, sent to his phone; submit only after a Telegram tap
  that names the task file's hash; one form per approval, with a receipt.

## 6. Steps the owner must do

1. **Sign in to Barron's**, and check MarketWatch, in the dedicated window (it is open now, with its port).
2. **Decide O4** (section 4). Until then, do not run the agent lanes that use the browser (`source_reads`,
   the fast-mover forensics, thesis-card quests) if the signed-in browser must stay under Aegis's guards.
3. To run on the HTTP transport (3.6x faster in this test): `set AEGIS_OPENCLAW_TRANSPORT=http`. The
   default stays `cli` because of the one unexplained HTTP navigate rc 1.

## 7. Rollback

* OpenClaw config: restore `~/.openclaw/openclaw.json` from its `.bak_lane_o_2026-09-28` backup
  (profiles hot-reload; if not, `openclaw gateway restart`). This restores the managed `muratclaw`
  (port 18801) and the built-in `user` / `chrome`. Aegis would still refuse `user` by name until
  `OPENCLAW_ALLOWED_PROFILES` is reverted in code.
* `queue_run.cmd`: its original is in the session scratch (`lane_o/queue_run.cmd.bak`).

## 8. Owed, not done

* `system_health` probes (not my file): "instance proven" (`muratclaw_instance.prove()`), "gateway
  latched" (`gateway_repair.probe()["latched"]`), and "free RAM below the repair floor".
* The HTTP transport caps a tool result at 16,000 characters. Large snapshots fall back to the CLI
  (counted as `http_truncated_fallbacks`). Stock pages will usually take the CLI for their snapshot.
* The host-aware picker drives `social_browser_pull`. `run_plan` (Dow Jones) still rotates round-robin
  across its 3 hosts, which already alternates hosts. Merging both into one host-aware plan is owed.
* The gateway task is "Interactive only, at logon": it does not survive a logoff (research note §A).

## 9. Addendum 16:20-16:50 HKT: the reader could not open a tab (fixed)

* **Cause:** `open_from_tab` runs `window.open` in a parent tab; the dedicated Chrome's fresh
  profile blocks a pop-up without a user gesture, so 0 new tabs on every lane (16 throttle slots
  burnt, queue FAILED_WILL_RETRY, supervisor relaunching every 5 min).
* **Fix:** the dedicated profile opens lane tabs with `open_tab` (instance proof and URL/host
  guards inside the client) through `web_reader.open_lane_tab`; `open_from_tab` stays for any
  non-dedicated operator profile. `resolve_parent_tabs(direct=True)` needs no tab and never
  picks the owner's. Rotation re-opens directly too (`Reader.direct_open`).
* **Rule replaced (tests):** no existing test asserted "a parent tab is REQUIRED" for the dedicated
  profile; the refusal still binds for a non-dedicated profile (pinned in
  `test_reader_direct_open.py`). Three CLI-faking test fixtures now pin `AEGIS_OPENCLAW_TRANSPORT=cli`
  because the dedicated profile defaults to HTTP; one tool-args expectation gained `timeoutMs`.
* **Slots:** a failed open gives its slot back (`Throttle.refund`), unless the client recorded a
  tab first (a page loaded); that tab is closed.
* **Supervisor:** `READER_CANNOT_OPEN_TABS` (every lane failed to open) is classified and relaunched
  at most 3 times per rolling hour, backoff doubling from 300 s.
* **The HTTP rc 1 (section 2 item 7) is explained:** Playwright `page.goto` waits for `load` with a
  20 s default; MarketWatch fires it after 50-60 s (gateway log: `TimeoutError: page.goto: Timeout
  20000ms exceeded`; the HTTP reply says only "tool execution failed"). Reproduced twice, then passed
  twice with `timeoutMs` 60000. HTTP navigate/open now send `OPENCLAW_HTTP_NAVIGATE_TIMEOUT_MS` (75 s),
  and `OPENCLAW_BROWSER_TRANSPORT_DEDICATED = "http"` is the default for the dedicated profile.
* **Zero links on stock pages:** a CUT snapshot (>= 38,000 chars) is now re-read interactive-only
  even when it shows some nav links (Barron's PLTR: 38 nav links, 0 of 37 article links before).
* `web_reader.social_root()` and the supervisor's data root now come from `config.OPTIMUS_LEDGER_DIR`.

## 10. Addendum 17:00-18:00 HKT: never idle, never blank; O4 applied; sign-in specified

Machine settings changed: see the local record, not in git.

**A. Never idle, never blank (built, tested, running).**
* Every page load is classified before it is stored (`web_reader.classify_page`): OK, BLANK,
  NOT_FOUND, PAYWALL_STUB, SIGNED_OUT, CHALLENGE, REDIRECTED_OFF_HOST. Only OK is stored. A
  CHALLENGE stops that lane (`REFUSED_CHALLENGE`, lane-fatal); nothing is done to pass it. Search
  (stock) pages are classified from their snapshot title. Counts per class per host go on every
  plan receipt (`page_classes`) and one line per load into `dowjones/page_log.jsonl`.
* A ticker whose page is NOT_FOUND once goes into `dowjones/not_found_tickers.json` and is skipped
  (`skipped_not_found` on the receipt). Share-class tickers are spelled with a dot in site URLs
  (`BRK-B` -> `brk.b` / `BRK.B`). Other templates were not re-probed live today.
* The supervisor builds its own queue (`QUEUE_rolling_<day>.txt`: newest UNIVERSE file + the books,
  never-read / oldest-read names first; MarketWatch estimates + WSJ + Barron's stock pages) and
  rebuilds it when every plan line is DONE; when every name was read today it idles 30 min and
  rebuilds. A run that ends on the DAILY cap is retried 30 min later instead of ending the night.
  `--no-rolling` runs the given queue command as before. The social hosts are NOT in this rotation
  yet (they run from `scripts/social_browser_pull.py`); merging them is owed.
* `dowjones/reader_status.json` is rewritten every minute (tick 60 s): state, current url per
  worker, OK pages in 10 / 60 min, classes per host in 60 min, last bad page, last error, next action.
* The dedicated Chrome's port going down is already a `CHROME_DOWN` fault that the repair ladder
  answers with the attach launcher; the relaunched reader opens fresh tabs.

**B. O4 applied (owner: "2-yes").** Backup `~/.openclaw/openclaw.json.bak_o4_2026-09-28`, dry run
first, then `openclaw config patch` (hot reload, no gateway restart):
`tools.profile = "coding"`; `agents.entries.main.tools.deny = ["browser"]`; new agent
`aegis-browser` = `{tools: {profile: "minimal", alsoAllow: ["browser"]}}`; Aegis
`config.OPENCLAW_HTTP_AGENT_ID = "aegis-browser"`. Verified live: `POST /tools/invoke` browser as
`main` -> 404 "Tool not available: browser"; as `aegis-browser` -> 200. An agent turn through
`openclaw_client.agent` (the path `night_investigator_forecast` uses; its prompt is evidence on disk,
no browsing) answered "OK" in 11.8 s. The gateway kept running (no restart). Rollback: copy the
backup over `openclaw.json` and set `OPENCLAW_HTTP_AGENT_ID = None`.

**C. Sign-in / free sign-up: SPECIFIED, NOT BUILT today.** Why: the flow needs clicks outside the
article-link rule and pages outside the host allowlist (accounts.google.com's account chooser), and
typing, which the client refuses by name everywhere. Making that safe needs its own task type:
1. a task record written first (site, purpose, account = the MuratClaw Google account only for a NEW
   sign-up; the owner's account only for subscriptions he already pays for; fields it will fill);
2. hosts: the target site + accounts.google.com, for this task only;
3. actions: click only on elements whose text matches a fixed allowlist ("Sign in", "Sign in with
   Google", "Continue as ...", "Create free account", "Register"); type only into fields whose
   label is on the field allowlist (name, email); refuse any page showing card / billing / payment /
   "free trial" with a card field / a password field for a NEW password (stop and report);
4. a screenshot before submit, stored with the record; never send a message, email or post;
5. refusals by name, pinned by test, before any live use.
Barron's: the owner signed in himself; the live Barron's reads at 16:45 returned full articles.

## 11. Addendum 20:20-21:00 HKT (continuation builder): the blank pages

**Cause.** Nothing was blanked BEFORE it was read. The order in code and on the live trace was
already open, settle, scroll, read, classify, store, then blank. The blank WAS the design: after
every read, and after a listing or stock page had been snapshotted ("the listing waits blank
for its turn"), the reader navigated its tab to `about:blank` to drop the renderer's memory.
That is exactly what Murat saw: a page loads, goes blank, and "back" brings it back, because
the page is one history entry behind the blank. The receipts from 17:06-17:12 show every
load classified (12 OK, 1 NOT_FOUND) and `blanks` > 0 on every worker. A second, latent
fault came from the same rule. After a re-attach, `_Recovery` paired this run's blanked lanes
with the listing's `about:blank` tabs by count. With three worker processes on one Chrome,
another worker's blank tab could be adopted.

**Fix.** On the dedicated instance (`Reader.direct_open`) a read tab is now CLOSED
(`Reader.retire`), and the next page load opens a fresh tab AT its URL (`_reopen`, reason
`fresh_tab_per_page`). No `about:blank` navigation is sent; no history entry is left; there
are no blank tabs to tell apart. The social runner uses the same rule. A profile that is not
dedicated keeps blank-after-read (pinned). Receipts carry `closes_after_read` and
`blank_slot_refunds`.

**Item 3, completed.** A BLANK or empty page now gives its throttle slot back
(`Reader.refund_slot`; `Throttle.refund(line=...)` removes that lane's own line even after
another lane has acquired). Failed opens already refunded.

**Live trace, one page per site, dedicated Chrome, HTTP transport.** All tabs read before
they were closed, 0 blanks, 0 orphans:

| page | class | chars stored | links |
|---|---|---|---|
| MarketWatch NVDA analyst estimates | OK | 2,311 (raw 5,032) | - |
| WSJ NVDA quote page | OK | snapshot 10,326 | 4 on page, 4 taken |
| WSJ article (Nvidia buyback) | OK | 2,663 (raw 4,616), a short news story, full | - |
| Barron's NVDA stock page | OK | snapshot 22,506 | 19 on page, 5 taken |
| Barron's article (buy-nvidia pick) | OK | 9,023, full article | - |

**Tests.** New `test_reader_fresh_tab_per_page.py` (4). Two expectations changed from "one tab
per lane/host" to "one fresh tab per page, every one closed"
(`test_reader_direct_open`, `test_lane_o_muratclaw` social runner).

**30 minutes of supervised reading (20:31:54-21:03 HKT, 3 workers, rolling queue, HTTP).**
63 pages classified: marketwatch.com OK 23; barrons.com OK 31; wsj.com OK 8, NOT_FOUND 1 (an
article URL). No BLANK, CHALLENGE, SIGNED_OUT or PAYWALL_STUB. That is about **120 OK pages per
hour**; 49 articles stored (MW 21, Barron's 15, WSJ 13). The receipts show `blanks 0`,
`closes_after_read` 20 / 22 / 21, **0 orphaned tabs**, and no stop. One supervisor launch, no
relaunch, no repair. The supervisor was left running (until 08:00).

**Still owed:** the social hosts are not in the supervisor's rotation (they run from
`social_browser_pull`). Sign-in / free sign-up (item 12) is specified in section 10C and not
built. The 17:06 workers ended without a receipt or a stop reason (hard-terminated, cause not
found); today's run did not repeat it.

## 12. Addendum 21:50-23:20 HKT (pool builder): more tabs, the sites' own navigation, media and transcripts, the social hosts

Owner, 21:45: "can openclaw read more, can it launch another chrome tabs to read too, this one by
one is very slow, it needs to read wsj, barron, marketwatch per stock and the news from that too,
it should navigate them, not just the stocks, and also the media too." 22:00: "use the transcript
of the videos, its much better."

X, Reddit and Dow Jones terms restrict automated access; the owner has been told the account risk
twice and has decided.

**A. The measured bottleneck was the pacing, not the page load.** From the live receipts
(`plan_2026-09-28_123154_*`, 99 articles), per page: open 2-7 s (median 1.9 / 7.0 / 1.6 s for
MarketWatch / WSJ / Barron's), settle + scroll + read about 10 s, and **46-73 s idle** waiting for
the throttle. The throttle drew ONE global gap (6-20 s; 35% of draws sat at the 20 s clip) for all
three worker processes, held its file lock through the sleep, and added a same-host floor of 3x the
draw (up to 60 s). That capped each site near 60 pages an hour and the total near 180, whatever the
page load. More tabs under those rules would have added nothing.

**B. Design: one process, one thread per tab, pacing per host** (`scripts/reader_pool.py`).
* `Throttle(per_host_mode=True)`: each host has its own drawn gap (`READER_HOST_GAP_S`, a
  right-skewed draw inside the range, never within 1 s of that host's previous draw), plus a short
  drawn gap between any two opens (`READER_GLOBAL_GAP_S`). The slot is RESERVED under the file lock
  (a future-dated line) and slept outside it. The old global mode is unchanged for every other caller.
* Threads, not an asyncio loop and not more worker processes: every browser action stays the same
  synchronous, guarded `openclaw_client` call (one keep-alive HTTP session per thread), so no guard
  is re-implemented; and one process lets one memory governor set the tab count.
* Tabs: `READER_MAX_TABS` 6, `READER_TABS_PER_HOST` 2 per Dow Jones site and 1 per social host.
  Each page still gets a fresh tab that is closed after its read. Two tabs per site matter for list
  pages: a front or stock page takes 25-55 s of work (a large snapshot, which falls back to the CLI).
* The memory governor (`reader_scheduler.TabGovernor`, rule only): before a tab opens, free RAM is
  read; below `READER_MIN_FREE_GB` no new tab opens (the first tab always may) and the target falls
  by one per update, never below 1; it grows by one only above `READER_GROW_FREE_GB`. The status file
  prints the count and the reason. Tabs close after every read, so there is never an idle tab to close.

**C. Navigating the sites.** `reader_scheduler.SECTION_FRONTS`: 27 fronts (WSJ 8, Barron's 9,
MarketWatch 10, three of them data pages whose text and tables are stored). Front page and markets
every 30 min in US hours, others every 2 h. A section URL that is not found, or that LANDS on another
page, is recorded once in `dowjones/sections_not_found.json` and dropped; the next candidate URL is
tried. Links are chosen from the front's snapshot (existing chooser: host, pattern, no account or
money text, no sponsored unit), prominent first, then newest; up to 12 articles and 3 media episode
pages per front. Per stock: the MarketWatch analyst page (text), the MarketWatch stock page, the WSJ
quote page and the Barron's stock page (their news links). Related / read-next links are followed
to depth 1, same host, only from an article naming a universe ticker. Every stored article carries
`reached_by` (lane, section, parent url, position, depth) and `tickers_named`.

**D. What to read first** (`reader_scheduler.priority_key`, one pure function): due fronts; the news
a front showed; book and contest names; names with an alert (SEC filing) in the last 36 h; the rest,
oldest read first. Within a tier, links already found come before a new list page. A stock page is
not re-read inside 20 h, a social page inside 12 h, a stored article never. `choose()` prefers a
host that is free now over one the tab would wait for.

**E. Media and transcripts.** A second constant page function (`READ_MEDIA_FN`, via
`openclaw_client.read_media`, same guard path as `read_text`) READS what the page already holds:
media counts with titles and captions, video/audio durations, the page's JSON-LD media objects (with
their `transcript` when published), caption tracks and caption-file URLs, transcript sections, table
rows, related links. `media_transcripts.py` then stores one row per media item in
`news_corpus/media_transcripts/<host>/<day>.jsonl`: the site's structured transcript, else its
transcript section, else the ONE captions text file the player names (https, .vtt/.srt/.ttml/.dfxp,
text content type, 2 MB cap, never a social / mail / denied host; the host is recorded), else
`NONE_PUBLISHED`. No video or audio is downloaded; nothing is played or clicked; no speech-to-text.

**F. The social hosts in the rotation.** Per name: the X cashtag search, the StockTwits symbol page
and a Reddit search across seven investing subreddits, each reached by NAVIGATING to a URL. The X URL
no longer carries `src=typed_query` (nothing was typed and nothing should say so). Every social page
is classified (`classify_social`: OK, BLANK, LOGIN_WALL, INTERSTITIAL, RATE_LIMITED, CHALLENGE,
REDIRECTED_OFF_HOST); anything but OK / BLANK cools that host (`dowjones/host_cooling.json`,
`READER_HOST_COOL_S` 1 h) and is reported. `store_social` stamps `never = [alert_origin, order]` on
every row and refuses a row marked as an alert's or order's origin.

**G. Caps** (config, dated and quoted): 480/h total (3 x 120 per Dow Jones site + 3 x 40 per social
host), 4,000/day, 1,200/day per Dow Jones site; social hosts unchanged at 150/day. Derived from the
day's reading need (about 1,000 pages a site in a ~10 h night), not from the maximum the pacing allows.

**H. Status and report.** `dowjones/reader_pool_status.json` every 15 s (tab count and why, per host:
tabs, loads in 60 min against the hourly cap, loads in 24 h against the daily cap, classes, cooling,
pending; section verification). The supervisor copies it into `reader_status.json` (`pool`). The
owner-readable report `dowjones/reading_report_<day>.md` is refreshed hourly (by the pool and by
the supervisor's digest).

**I. Tests.** New `test_reader_pool.py` (40): per-host pacing on opens with several tabs; gaps drawn,
never constant; the lock not held through the sleep; hourly host caps; the governor with a fake
memory reader; front scheduling and a redirected / not-found section dropped once; the depth-1 rule;
the priority order; `choose`; captions parsing, the fetch rules, NONE_PUBLISHED; social classes; a
social row never an alert origin; end-to-end fake-driver runs (front -> news -> media -> related;
challenge cools the host; login wall cools only that host; stock page freshness); the instance
proven before every action; guard counts per action on the REAL client equal to each action's
guards measured alone. `social_browser_pull.run` now classifies and stops a host on a wall.

**J. Live (dedicated Chrome, HTTP transport).**
* Trial 22:16-22:31, beside the old reader: 3 fronts, NVDA and MU, 41 pages, all OK (WSJ 9,
  Barron's 11, MarketWatch 16, X 1, Reddit 2, StockTwits 2), 0 orphaned tabs. Per page: open ~1 s
  (fronts 1-9 s), work ~11-13 s for an article, 25-55 s for a front or stock page.
* The old supervisor was stopped with its STOP file (22:33, graceful; its reader had just died on a
  gateway ECONNREFUSED, the second in 20 min) and restarted in pool mode; the pool was restarted twice
  more by its own STOP file to load two fixes (the front verification; a free tab now goes first to
  the host with the fewest tabs in flight, because the Dow Jones sites had taken every slot and the
  social hosts waited).
* **Section fronts verified live: 24 of 24 link fronts loaded OK on their FIRST candidate URL and
  landed on that URL** (no redirect, none dropped); the 3 MarketWatch data pages stored as text.
* **30-minute watch, 22:52:47-23:23 HKT: 444 classified pages an hour** (Barron's 83, MarketWatch
  79, WSJ 75 incl. 4 NOT_FOUND article links, X 69, StockTwits 69, Reddit 67; the social hosts'
  first minutes ran ahead of their 40/h cap, which then bound), against **134 an hour** for the old
  three workers (20:40-21:40 HKT: Barron's 64, MarketWatch 39, WSJ 31 incl. 7 NOT_FOUND).
  No challenge, block, login wall or rate-limit page on any host; no host cooled.
* The governor held 6 tabs when memory was comfortable and fell to 1-2 during dips below the floor.
* Transcripts today: WSJ 4 (2 from the site's structured data, 2 from captions tracks), MarketWatch
  5 (captions tracks), Barron's 0 of 2 items. (WSJ's 14 items include 10 episode entries of a
  podcast index page read in the trial; media links now require an episode page.)

**K. Owed.** The social hosts will reach 150/day each around 03:00-04:00 HKT and then rest (by
design). A snapshot of a big front falls back to the CLI (10-14 s); a smaller interactive-only first
snapshot would cut front work roughly in half. The gateway dropped connections twice this evening
(22:08, ~22:24) under low free memory; the supervisor classifies and relaunches, the cause is not
fixed here. Speech-to-text for items with `NONE_PUBLISHED` is a separate decision, not built.

## 13. Addendum 2026-09-29 02:00-03:00 HKT (continuation builder): the reader said "reading" and read nothing

**What happened.** From 00:59 to 02:15 HKT (77 minutes) every page the pool opened came back BLANK
and every social page failed with `press rc 1: tool execution failed`, while `reader_status.json`
said `state: "reading"`. The gateway's own log (`%LOCALAPPDATA%\Temp\openclaw\openclaw-<day>.log`)
names the cause 343 times: `browserType.connectOverCDP: Timeout 9000ms exceeded`. Two page targets
of the dedicated Chrome (a WSJ tab and an X tab left open by an earlier thesis-card job) did not
answer a one-line `Runtime.evaluate` within 4 s; Playwright's connect waits for every page to
initialise, so one hung renderer fails every attach. The gateway process was alive and never
restarted, Chrome's `/json` answered, `probe()` was green, and nothing compared the status with
pages OK. Closing the two hung targets (`Target.closeTarget` on the browser websocket, after the
instance proof) brought reading back at 02:15:40. Pages lost: roughly one stall-length of the
pool's normal rate.

Three more defects found on the way, each of which left the reader idle on its own:

1. **Head-of-line blocking in the per-host throttle.** The global gap was computed from the LATEST
   reservation of ANY host, including future-dated ones. When a social host hit its 40/h cap its
   slot was reserved ~10 minutes ahead, and every other host (WSJ, Barron's, MarketWatch) queued
   behind it. Now `web_reader.fit_global_gap` keeps any two opens `g` apart and uses the free time
   before a future reservation (`Throttle._reserve`, `next_free_at`, `Pool.take`).
2. **A stale keep-alive socket read as "gateway down".** The 22:08 / 22:24 / 01:37 "drops" were
   `ConnectionResetError(10054)` on a pooled HTTP connection while the gateway process kept running;
   the transport labelled it `ECONNREFUSED`, `is_gateway_down` matched, and the pool stopped. Now
   every request sends `Connection: close`, a read-only verb is retried once after a reset, and a
   reset with the gateway port still open is reported as `gateway connection reset, port open`
   (not GATEWAY_DOWN; one page fails, the pool goes on). Memory was not the cause of these resets.
3. **A floor the repair could not clear.** `repair()` returned `LOW_MEMORY` below
   `OPENCLAW_REPAIR_MIN_FREE_GB`, with nothing that could free memory: a browser holding it blocked
   the gateway forever. Now it calls `reclaim_memory` (hung tabs, then idle tabs of the dedicated
   Chrome, then a graceful recycle of that Chrome) and proceeds, below the floor if it must, with
   the bounded port wait after it.

**The rules now (code, config constants in `backend/config.py`):**
* **State is derived, not assumed** (`night_reader_supervisor.derive_state`): READING (a page OK in
  10 min), WAITING_FOR_CAP (nothing attempted and the next reserved open is > 1 min ahead),
  STARTING (launched less than `READER_STALL_S` ago), STALLED (alive, no page OK for
  `READER_STALL_S`), REPAIRING, DOWN. The status file also carries `free_ram_gb` and
  `free_disk_gb` (the old `free_gb` was the DISK and read as memory).
* **A stall is a named fault with a ladder**, one step per `READER_STALL_STEP_S`: close hung tabs
  (and repair a faulted gateway) -> restart the pool (its STOP file, then by PID) -> recycle the
  dedicated Chrome and restart the pool; the recycle is budgeted
  (`READER_CHROME_RECYCLES_PER_HOUR`).
* **The dedicated Chrome is recycled on a schedule**: older than `READER_CHROME_RECYCLE_S`, or
  holding more than `READER_CHROME_MAX_GB` of private bytes, or more than `READER_CHROME_SOFT_GB`
  while free RAM is under `READER_CHROME_LOW_FREE_GB` (its processes found by the dedicated
  user-data-dir on the command line; the main Chrome is never measured or touched). The first
  version recycled on summed working set above a low bar and fired every quarter hour on a fresh
  browser with a full pool (working sets count shared pages once per process); size now counts
  only when the machine is short, or when it is extreme. Recycle = prove the instance,
  close the reader's own tabs first, then the rest, `Browser.close` (graceful, so sign-ins persist),
  wait for the proven browser PID to exit (`taskkill /PID` only after 30 s), `launch_attach`.
  Verified live: pool stopped gracefully in 19 s, Chrome exited in 3 s, port back in 0.5 s, pages
  OK again within a minute, WSJ still signed in.
* **Tabs are closed on every exit path**: the pool's status now lists `open_tab_ids`; a pool
  stopped by PID has exactly those tabs closed by the supervisor.
* **No page lives for the browser's life.** The attach launcher opened `https://www.wsj.com/` as
  its start page and that tab stayed open, idle, for the whole life of the browser; after a
  relaunch it was the largest renderer within a quarter of an hour (a live, ad-heavy home page
  left idle is exactly the kind of tab that grows and hangs). `attach_argv` now starts on
  `OPENCLAW_CHROME_START_URL` (about:blank), and every 5 minutes the supervisor closes pages of the
  dedicated Chrome not NAVIGATED (`performance.timeOrigin`) for `READER_STALE_TAB_S`, and hung
  pages, sparing the pool's own tabs and about:blank (`gateway_repair.close_stale_tabs`). Verified
  live: the launcher tab was closed at 33 minutes idle. (`scripts/open_muratclaw_chrome_attach.cmd`,
  the owner's manual launcher, still opens WSJ; the reaper covers it.)
* **When a cap binds, the state says so.** After the fixes the Dow Jones hosts ran at their hourly
  caps (`READER_MAX_PER_HOUR_BY_HOST`, 120/h each) and X / Reddit at their 150/day caps; that is
  WAITING_FOR_CAP / capped hosts, not a stall. Raising throughput further is a caps decision.
* **The tab maximum adapts** (`TabGovernor.effective_max`): tabs open now plus as many more as fit
  above `READER_MIN_FREE_GB` at `READER_TAB_GB` each, never above `READER_MAX_TABS`; a deep deficit
  sheds two tabs per update.
* This machine's memory, tab and Chrome-size readings are written every 5 minutes to
  `backend/data/optimus/local_pc/reader_machine.jsonl` (gitignored), not here.

**Tests.** `backend/tests/test_reader_stall_and_recycle.py` (fakes only): the state machine; the
stall ladder; the pool stopped by its STOP file then by PID with its tabs closed; hung tabs found
and closed only on a proven instance; reclaim stops at the first step that clears the floor and
never loops; the recycle closes our tabs first, ends only the proven PID, and refuses an unproven
browser; the adaptive maximum; no host queued behind another host's future slot; a reset retried
for a read verb, never for an open, and not GATEWAY_DOWN while the port is open.
`test_lane_o_muratclaw` now pins that the repair reclaims and proceeds under the floor.

**Owed.** `test_u_forecast_dependency::test_the_retries_per_day_are_bounded` fails when run after
~15:00 UTC: its fake clock starts at `now()` and eight retry windows (8 x ~4,050 s) cross UTC
midnight, so the per-day count resets (CLAUDE.md protocol 5: a fixture must not encode a calendar
moment). Not in this lane's files; not changed here.
