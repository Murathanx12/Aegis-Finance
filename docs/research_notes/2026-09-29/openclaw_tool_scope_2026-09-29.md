# OpenClaw tool scope and the gateway memory floor, 2026-09-29

Fixes two reviewed findings:
- F1 in `docs/reviews/REVIEW_2026-09-29_READER_POOL.md`: LLM agent turns could drive the signed-in Chrome through `exec`.
- F1 in `docs/reviews/REVIEW_2026-09-29_MORNING_TEST_FIXES.md`: the memory floor was inverted, and the reclaim step could close any tab. The orchestrator numbered this one Finding 10.

## RESULTS SCOREBOARD

| line | value |
|---|---|
| RESULT IMPROVEMENT | **NONE** (safety and repair behaviour; no change to the money path) |
| LLM agents that can reach shell / write / message / browser | **0**. It was 1 before: `main`, reaching `exec process code_execution write edit apply_patch sessions_send conversations_send cron gateway ...` |
| Tool calls outside the read set, from the start of the post-fix card run to its audit | **0 of 35** (`web_search` 4, `web_fetch` 31) |
| Tool calls outside the read set, previous 24 h | 127: `exec` 92, `process` 13, `read` 13, `plugins` 7, `write` 2. All fall between 2026-09-28 14:07 and 14:24 UTC, inside thesis-card quests |
| End-to-end thesis card, AAOI, post-fix | verdict neutral / conf med; 15 sources, 17 claims, 10 analyst actions, 6 promises. The prior medians were 15-17.5 sources and 19.5-20 claims |
| Card cost | quest $0.0231 + synth $0.0009 = **$0.024** |
| Gateway restart | **not needed**: tools/agents keys hot-apply (CLI: "Change will apply without restarting the gateway"); gateway pid unchanged |
| Memory floor | restored to the measured rule: **no gateway start below the measured memory floor** after a reclaim of the reader's own memory |
| Tests | 319 passed across the touched files (new: 23 in `test_openclaw_tool_scope.py`) |

## 1. What an LLM turn may do now

The config was backed up to `~/.openclaw/openclaw.json.bak_tool_scope_20260929T030902Z`. The change was applied with `openclaw config set --batch-file` after a `--dry-run`, and `openclaw config validate` reports it valid. The key names come from the installed 2026.9.5 docs (`docs/gateway/config-tools/tool-policy.md`):

- `tools.profile`: `coding` → `minimal`.
- `tools.deny` (new, global) blocks these groups and tools:
  - groups: `group:runtime`, `group:fs`, `group:messaging`, `group:nodes`;
  - UI tools: `terminal`, `screen`, `computer`, `canvas`, `portal`, `dashboard`, `show_widget`;
  - messaging and session tools: `conversations_send`, `conversations_turn`, `sessions_send`, `sessions_spawn`, `subagents`, `suggest_task`;
  - automation tools: `cron`, `automations`, `gateway`, `plugins`, `openclaw`, `skill_workshop`;
  - other tools: `*_generate`, `secrets`, `github_publish`.
  
  `browser` is not in the global list, so the transport agent keeps it.
- `agents.entries.main.tools` = `{profile: minimal, alsoAllow: [web_search, web_fetch, x_search, memory_search, memory_get, bundle-mcp], deny: <the same list> + browser}`.
  - `main` handles every `openclaw_client.agent()` turn, the Telegram binding, heartbeat and talk.
  - `bundle-mcp` covers only the two configured read-only servers (optimus, and aegis_api, which is GET-only).
- `aegis-browser` is unchanged (`minimal` + `browser`). It is the guarded `/tools/invoke` transport and runs no LLM turns.

A deny in any layer wins over an allow, so a new agent inherits the global deny.

## 2. How the thesis-card quest gets pages now

- **Before:** the prompt said "Use your browser / web tools, and the logged-in X (x.com) account".
- **Now:** the prompt says "NO browser, NO shell, NO logged-in account".
  - Signed-in pages (X, Reddit, StockTwits) arrive only as text that the guarded reader already stored. The pool stores them via `web_reader.read_social_page` in `news_corpus/social/<host>/<day>.jsonl`.
  - `thesis_card.guarded_social_reads` selects the newest page per host for the ticker. Pages must be at most 72 h old and dated no later than asof (PIT).
  - The pages are wrapped as UNTRUSTED data blocks in the prompt.
  - The X lists are filled only from those pages.
- Public pages still come from `web_search` / `web_fetch`. That is the gateway's HTTP fetcher: it sends no cookies, uses no browser, and blocks private and loopback hosts (`docs/tools/web-fetch.md`).
- The card now records `guarded_social_reads` (hosts, URLs, read times). This was added after the AAOI run, so that card does not carry the field.

## 3. The memory floor (`gateway_repair.py`)

**The measurement.** `lane_o_build_2026-09-28.md` section 3 records the kill test:
- Run 1: free memory far below the floor. The gateway did not bind its port for **19.6 min**.
- Run 2: ample free memory. The gateway bound in **42 s**.

**What c0ac5310 did.** It replaced the `LOW_MEMORY` return with "reclaim, then start anyway", and left the docstring stating the old rule.

**What changed now:**
- **Repair order.** Below the floor the repair first reclaims the reader's own memory, then re-reads free memory. If it is still below the floor, it returns `LOW_MEMORY` and starts nothing. The repair budget retries later.
- **Docstring and tests match the code.** The rewritten docstring names the measurement. New tests pin it:
  - `test_a_reclaim_that_cannot_clear_the_floor_starts_no_gateway`;
  - a latched gateway under the floor gets no restart;
  - a docstring/code agreement test.
- **Reclaim closes only the reader's own tabs.** It closes the hung and idle tabs listed in the pool's `open_tab_ids` (`pool_open_tab_ids()` reads `reader_pool_status.json`). A tab it did not open is reported as `spared` and left alone.
- **Reclaim recycle.** The Chrome recycle inside reclaim runs only when every page is the reader's own or `about:blank`. Otherwise it refuses with `OWNER_OR_OTHER_TABS`.
- **Every recycle, including the supervisor's age/memory recycle.** `recycle_dedicated_chrome` refuses with `OWNER_MAY_BE_USING` when a tab the reader did not open is the active tab of a shown window. It checks `document.visibilityState`, a constant CDP expression like the existing responsiveness probe.

## 4. The audit

- `backend/services/openclaw_tool_scope.py` resolves each agent's effective tools offline and checks them.
  - A layer it cannot resolve (`byProvider`, `toolsBySender`, `elevated`, an unknown profile) counts as a problem, never a pass.
  - An unfiltered profile also counts as a problem.
- It also reads every agent's transcript store read-only and lists tool calls outside the read set.
- A transcript under the transport agent is itself a violation.
- Arguments are shortened to a redacted head, so no secret is printed.
- CLI: `python -m scripts.openclaw_tool_audit [--hours N | --since-utc T]`.
  - Receipts go to `backend/data/optimus/openclaw/tool_audit_<run id>.json`.
  - Exit codes: 0 OK, 1 UNSAFE, 2 CANNOT_DETERMINE.
- **Scheduled caller:** the new `system_health` probe `openclaw_tool_scope`. It runs in every health pass, including the daily pass's `health` step.
- **The 24 h probe will read DEAD until about 2026-09-29 14:25 UTC,** when the 09-28 calls age out. That is correct: those calls happened.

## WHAT WORKS

- No LLM agent can reach shell, write, messaging or browser tools; the pre-fix config is flagged by the same test.
- A real quest after the fix made 35 calls, all read tools. Card quality held (15 sources, 17 claims).
- The gateway repair again follows the measurement, and its reclaim cannot close a tab it did not open.

## WHAT DOES NOT

- `scripts/source_reads.py` and `backend/services/fast_mover_forensics.py` still tell the agent "Use the browser tool with the logged-in X account". They now fail safely (no tool). They should be rebuilt on the guarded reader's store, as the thesis card was.
- The X lists on cards will usually be empty. The pool reads `x.com/search?q=$T`, not company or CEO timelines, and it has no social rows dated after 09-28.
- `web_fetch` is still an unbounded outbound read to any public host chosen by a model that reads untrusted text. Without shell, read or messaging there is nothing sensitive to put in a URL except the prompt itself.
- The transport agent `aegis-browser` could still run an LLM turn if someone ran `openclaw agent --agent aegis-browser`. Nothing does that, and the audit flags any transcript under it.

## HIGHEST-EV EXPERIMENT

Point `source_reads` at the guarded store: X profile timelines read by the pool, not by an agent. Then compare one night of source-read yield against the 09-25/09-27 runs. Pass criterion: `openclaw_tool_audit` at 0 violations over the night, and dated posts per source no worse than before. This recovers the only signed-in X signal the shutdown removed.
