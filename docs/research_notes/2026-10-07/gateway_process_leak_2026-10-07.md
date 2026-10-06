# The gateway process leak (C14, 2026-10-07)

**RESULT IMPROVEMENT: NONE.** This is an operational fix: it stops a memory leak that killed a suite run and two agents' waits. It adds no evidence about returns.

## 1. What was alive

At about 03:30 HKT, 590 python processes were running:

- 294 copies of the Optimus MCP server (`optimus/mcp/server.py`).
- 296 copies of `scripts/openclaw_api_bridge.py`.
- Together they used about 2.5 GB, which left about 2 GB of RAM free.

The orchestrator killed them by recorded PID at 03:23. The PID list is in `backend/data/optimus/local_pc/leak_killed_pids_2026-10-07.txt`.

## 2. What spawned them (evidence)

**The spawner is the OpenClaw gateway.** Its config (`~/.openclaw/openclaw.json`, read-only, secrets not printed) declares two stdio MCP servers:

- `mcp.servers.optimus`: the venv `python.exe` running `optimus/mcp/server.py`.
- `mcp.servers.aegis_api`: the venv `python.exe` running `scripts/openclaw_api_bridge.py`.

The gateway's bundle-MCP manager starts one *runtime* per agent **session**, which means one optimus + one bridge pair. On Windows each one is a venv launcher shim plus its interpreter child, so each session costs 4 OS processes. 146 sessions × 4 = 584. Add the one Optimus server owned by the Claude Code session (2 processes) and 4 other bridge-matching processes, and you get exactly 294 + 296.

The two scripts do not spawn each other. The bridge (`scripts/openclaw_api_bridge.py`) is a plain FastMCP stdio server with no subprocess calls. `optimus/mcp/server.py` has no subprocess calls either. **Nothing in the sibling Optimus repo needed to change.**

### Who opens a session

`backend/services/openclaw_client.py::agent()` opens a session. It runs `openclaw agent --session-id aegis-<purpose>-<uuid>`, a fresh session per call by design.

The evidence that ties the leaked processes to these calls:

| evidence | count |
|---|---|
| OpenClaw turns in `llm_calls_2026-10.jsonl` since 2026-10-06 (all between 00:20 and 01:59 HKT): `u_forecast` 135 + `query_planner` 11 | **146** |
| gateway log `openclaw-2026-10-07.log`, `agents/agent-command` "run … ended" | **146** |
| gateway log at 03:23 (the kill), `bundle-mcp` `server "optimus" closed` / `server "aegis_api" closed` | **146 / 146** |
| gateway log 2026-10-06 (whole day), agent runs / bundle-mcp lines | 0 / 0 |

**Correction to the brief.**

- **Cadence:** the processes did not accumulate "steadily from 14:28, one pair every 2.5 min". They were created in a burst of 146 turns (one about every 40 s) during the `u_forecast` unit's run, 00:20–01:59 HKT. Averaged over 13 h, a burst like that looks like about one pair every 5 min.
- **The 14:28 start time:** this is the creation time of the one Optimus server owned by the Claude Code session. The census shows its parent as `claude.exe`, not the gateway.
- **Observation window:** in a 10-minute read-only window after the kill (03:24 → 03:40), no agent turn ran. The `api_bridge` family stayed at 0, which is consistent with the burst explanation.

### Why the processes were never reaped (the root cause)

`openclaw_client.release_session()` had a 2026-09-30 fix that runs **`openclaw sessions archive`** after every turn. It returned True every time.

In OpenClaw 2026.9.5, archive is just `sessions.patch {archived: true}`:

- **`archive` does not retire the runtime.** `dist/sessions-lifecycle-*.mjs` maps archive to `sessions.patch`. `dist/sessions-mutations-*.mjs` contains no call to `retireSessionMcpRuntime`.
- **`delete` does retire it.** `sessions.delete` goes through `cleanupSessionBeforeMutation` → `ensureSessionRuntimeCleanup` → `retireSessionMcpRuntime` (`dist/session-reset-service-*.mjs`). `sessions.abort` also retires it.
- **The idle sweep is off by default.** It is opt-in through `mcp.sessionIdleTtlMs`, and the default is 0, which keeps a runtime for the session's whole lifetime (`dist/agent-bundle-mcp-runtime-shared-*.mjs`). This config does not set it.
- **There is a hard limit.** The gateway refuses a 257th live runtime ("live runtime limit (256)"). That limit is the 2026-09-30 failure. It stopped firing only because the gateway was restarted, not because archiving released anything.

So the release reported success and changed nothing.

## 3. The fix (our code)

**`backend/services/openclaw_client.py::release_session`** now **deletes** the one-shot session. The command is `openclaw sessions delete <key> --yes --json`, which retires the gateway's MCP runtime and its stdio children. The transcript is archived, not destroyed.

- **It returns True only when the gateway confirms `status: deleted`.** An rc of 0 without that status counts as not released.
- **It snapshots the session first.** A delete removes the session's transcript rows from the agent store that the read-only tool-scope audit reads. So before deleting, it copies that session's tool calls (read-only) into `backend/data/optimus/openclaw_sessions/released_tool_calls.jsonl`.
- **The audit reads the snapshot back.** `openclaw_tool_scope.audit` / `p_openclaw_tool_scope` merge those calls, so the 24 h audit is not blinded.
- **If the snapshot cannot be taken, the session is archived instead** (the old path) and the function returns False. The audit evidence outranks the memory, and the census below turns the resulting leak red.
- **It never raises.**

**`agent()`** now calls the release in a `finally` around the telemetry write. A telemetry failure can no longer skip the release. Timeouts were already released.

**`config.OPENCLAW_SESSION_RELEASE_MODE = "delete"`** is the switch. Setting it to `"archive"` restores the pre-C14 behaviour, which leaks.

`query_planner.issue` calls the same `release_session`, so it inherits the fix.

Both callers run out of process. `sim_run` runs `u_forecast` in a subprocess, and the reader supervisor launches `python -m backend.services.query_planner`. So **the fix applies from the next run with no restart.**

### The config change the owner should also make (not made here: `openclaw.json` was read-only)

This is defence in depth for any session our code does not release (for example, one opened by a human in the Control UI). Add this under the existing `mcp` object:

```json
"mcp": {
  "sessionIdleTtlMs": 600000,
  "servers": { ...unchanged... }
}
```

It turns on the gateway's own idle sweep, which runs every 60 s and disposes any runtime idle for more than 10 minutes. The gateway re-reads `idleTtlMs` on config reload (`reloadSessionMcpRuntimes`). If the reload does not pick it up, it takes effect at the next gateway start.

## 4. The census guard

**`backend/services/process_census.py`** is a new module, registered in `system_health.PROBES` as `process_census` (needs_proc, cadence 10 min). It reads `Win32_Process` once, read-only, and **never terminates anything**. A test pins that.

- **What it counts:** it counts **logical instances** per command-line family. A family member whose parent is in the same family (the venv shim → interpreter pair, or a supervisor → child tree) counts once. The raw OS-process count is printed beside it.
- **Caps:** caps are in `config.PROCESS_CENSUS_FAMILIES`:

  | family | cap |
  |---|---|
  | optimus_mcp | 8 |
  | api_bridge | 4 |
  | sim_run | 2 |
  | reader | 3 |
  | telegram | 2 |

- **Verdicts:** above the cap it reports **DEGRADED** (verdict STALE, exit 2). Above `PROCESS_CENSUS_DEAD_MULT` (2.0) × the cap it reports **DEAD** (exit 1).
- **What each row prints:** the parent breakdown (parent PID and what it is, for example "openclaw gateway") and the oldest creation time.
- **Unreadable table:** if the process table cannot be read, the row is UNKNOWN, never ALIVE.

Tonight's leak would have read `api_bridge: 146 live instance(s) (292 OS process(es)), cap 4` → **DEAD** within the first 10 minutes of the burst.

Census at 03:40 HKT, after the kill:

| family | instances | verdict |
|---|---|---|
| api_bridge | 0 | ALIVE |
| optimus_mcp | 1 (the Claude Code session) | ALIVE |
| reader | 2 | ALIVE |
| sim_run | 1 | ALIVE |
| telegram | 1 | ALIVE |

## 5. Restart procedure (only if needed; nothing was restarted or killed by this chunk)

**No restart is needed for the code fix.**

**One residue may remain.** The gateway may still hold up to 146 *runtime slots* for the killed sessions, because killing a child does not dispose its runtime record. That leaves about 110 of the 256-runtime limit. With the fix, each new session frees its own slot, so the next nightly `u_forecast` (about 135 turns) should stay under the limit. If you want the slots back anyway, choose one option:

**Option A (no restart): delete tonight's archived one-shot sessions.**

1. List them: `openclaw sessions --json --limit all`. Pick the keys `agent:main:explicit:aegis-*` with `archivedAt` set.
2. Wait until they are older than 24 h, so the tool-scope audit has already read them.
3. Run `openclaw sessions delete <key ...> --yes --json`. This retires their runtimes.

**Option B (restart the gateway by PID, never by image name):**

1. Write down the gateway tree: `Get-CimInstance Win32_Process -Filter "Name='node.exe'" | ? { $_.CommandLine -match 'openclaw' -and $_.CommandLine -match 'gateway --port' } | Select ProcessId,ParentProcessId,CreationDate`. There is a `--task-supervisor` root and a `--task-supervisor-child=` child.
2. Confirm that no reader is mid-read: check `reader_machine.jsonl` and the reader pool's PID file. The reader supervisor restarts readers, not the gateway (S58).
3. Use the house path: `backend/services/gateway_repair.repair("GATEWAY_STUCK")` stops by recorded PID and never runs two trees. Alternatively, run `openclaw gateway stop`, wait for the port to close, then `openclaw gateway start`. Then probe `openclaw gateway status`; a listening port is not readiness.

## 6. Morning check (one line)

```
python -m scripts.health_probe --only process_census,openclaw_tool_scope --no-write
```

Every `process_census:*` row should be ALIVE, and `api_bridge` should be at most 4, even after the night's `u_forecast` burst. `openclaw_tool_scope` should be ALIVE. If `api_bridge` is above 4, read `session_released` in the forecast receipts: False means the delete was refused, and the archive fallback leaked.

## Files

- `backend/services/openclaw_client.py`: `release_session` deletes after a snapshot; `agent()` releases in `finally`.
- `backend/services/openclaw_tool_scope.py`: `released_calls`, `default_released_path`; `audit(released_path=)`; the probe merges the snapshot.
- `backend/services/process_census.py`: new; the census and the probe.
- `backend/services/system_health.py`: `ProbeCtx.process_rows`; `make_ctx` supplies the reader; the probe is registered.
- `backend/config.py`: `PROCESS_CENSUS_FAMILIES`, `PROCESS_CENSUS_DEAD_MULT`, `PROCESS_CENSUS_TIMEOUT_S`, `OPENCLAW_SESSION_RELEASE_MODE`.
- `backend/tests/test_process_census.py`: new.
- `backend/tests/test_accrual_canary.py`: the archive test now asserts delete; the fixture is hermetic.
