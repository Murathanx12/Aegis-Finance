# OpenClaw runtime done right, 2026-09-28

Research only. No browser verbs run, no `gateway restart/stop/start`, no config
edits, no process kills. Everything below is read from the installed package
(`C:\Users\mrthn\AppData\Roaming\npm\node_modules\openclaw`, version `2026.9.5`,
docs bundled under its `docs/`), from `docs.openclaw.ai` (fetched live, quoted
below), from `C:\Users\mrthn\.openclaw\openclaw.json` (redacted), from
`~/.openclaw/logs/gateway-restart.log`, from `schtasks /Query`, and from this
repo. Secrets are never printed; where a value would be a token/key/secret the
note says `REDACTED`.

Two things this note deliberately excludes, per the assignment: bot-detection
evasion / fingerprint spoofing / CAPTCHA solving / proxy rotation (not
researched, not recommended), and any plan that reads a paid Dow Jones property
by automated means. **Dow Jones ToU §9.4.1** (quoted in
`docs/OPENCLAW_2026-09-26_READING_MURATS_CHROME.md` §5, verified against
`https://www.dowjones.com/terms-of-use/` on 2026-09-26) bars "automated means,
webcrawler, spider, script, ... browser automation tool, API client, AI agent or
assistant" outright. Nothing in this note works around that; WSJ/Barron's/
MarketWatch stay on the existing paste-inbox-first, human-handoff design.

## Verdict table

| # | Claim | Verdict | Decided by |
|---|---|---|---|
| 1 | Gateway is meant to be one always-on process, installable as a Windows Scheduled Task | **CONFIRMED** | `docs.openclaw.ai/gateway`: *"One always-on process for routing, control plane, and channel connections."* `docs.openclaw.ai/platforms/windows`: *"Managed startup uses Windows Scheduled Tasks when available."* Empirically: `schtasks /Query` on this machine shows task `\OpenClaw Gateway`, `Task To Run: C:\Users\mrthn\.openclaw\gateway.vbs`, `Status: Running`. |
| 2 | Loopback Browser Control HTTP API (tabs, navigate, act, snapshot, profiles) callable without spawning the CLI | **CONFIRMED, opt-in** | `dist/.../docs/tools/browser-control.md` §"Control API (optional)": *"the Gateway exposes a small loopback HTTP API... opt-in — set `OPENCLAW_EAGER_BROWSER_CONTROL_SERVER=1` in the gateway service environment and restart the gateway"*. Live-fetched from `docs.openclaw.ai/tools/browser-control` — identical text. Without the env var, nothing listens on that port; the CLI/agent-tool path still works. |
| 3 | A persistent WebSocket Gateway protocol for external applications | **CONFIRMED** | `dist/.../docs/gateway/protocol/transport.md`: frame shapes `req`/`res`/`event`, `connect`→`hello-ok` handshake, npm packages `@openclaw/gateway-protocol` and `@openclaw/gateway-client`. Live `docs.openclaw.ai/gateway`: *"WebSocket control/RPC"*, *"First client frame must be `connect`. Gateway returns a `hello-ok` frame..."* |
| 4 | Scheduler (cron), heartbeat, event-triggered wake, Telegram delivery | **CONFIRMED** | `openclaw cron --help` / `docs/automation/cron-jobs.md` (scheduler, persisted jobs, webhook/Gmail triggers); `docs/gateway/heartbeat.md` (periodic turns, `heartbeat_respond notify=true`, target `owner`); `docs/nodes` "system event" (`openclaw system event` enqueues + can trigger a heartbeat); `docs/cli/message.md` (`message send --channel telegram`) and `docs/channels/telegram.md` (production-ready Telegram bot). |
| 5 | Docs recommend a dedicated agent browser profile and manual login for authenticated sites | **CONFIRMED** | `docs/tools/browser-login.md`: *"When a site requires login, sign in manually in the host browser's `openclaw` profile. Automated logins often trigger anti-bot defenses and can lock the account."* `docs/tools/browser/profiles.md`: separate `openclaw` (isolated), `user` (real signed-in Chrome, attend prompt), `chrome` (extension relay). |

---

## A. ALWAYS ON

### How it runs today, measured

`openclaw.json` → `gateway.mode = "local"`, auth `token` (redacted). The
Scheduled Task, read with `schtasks /Query /FO LIST /V`:

```
TaskName:            \OpenClaw Gateway
Task To Run:         C:\Users\mrthn\.openclaw\gateway.vbs
Status:              Running
Logon Mode:          Interactive only
Schedule Type:       At logon time
Run As User:         mrthn
Last Result:         267009   (SCHED_S_TASK_RUNNING — not an error code)
```

This matches `docs/platforms/windows.md`: *"Managed startup uses Windows
Scheduled Tasks... launches it through a generated `gateway.vbs` WScript
wrapper, so the background Gateway does not open a visible console window."*
Created by `openclaw gateway install` (`openclaw daemon install` is a legacy
alias for the same command).

**Important limitation, not stated as a warning anywhere in the docs I read:**
`Logon Mode: Interactive only` + `Schedule Type: At logon` means this task
fires when `mrthn` logs on interactively and dies with that session — it is
**not** a "runs whether user is logged on or not" service. If Murat ever logs
off (distinct from locking the screen) rather than leaving the session open,
the gateway stops until the next interactive logon. For a machine that also
runs unattended overnight batch jobs (`night_reader_supervisor`, the always-on
lab), this is a real gap: native Windows scheduled-task installs do not give
true 24/7 survival across logoff. `docs/platforms/windows.md`'s own answer for
that case is **WSL2** ("the most Linux-compatible Gateway runtime"), which uses
systemd and `loginctl enable-linger` to survive logout — a heavier migration
than is warranted today, but worth naming since "let it be open all the time"
is the owner's literal ask.

`~/.openclaw/logs/gateway-restart.log` shows the task has churned: dozens of
`restart` events on 09-22, 09-26, 09-27 (e.g. seven restarts in three hours on
09-27 morning). Frequent restarts, not a single long-lived process, is the
actual current shape of "always on."

### What causes "Chrome MCP subprocess tree cleanup could not be verified"

Found the exact string in `dist/chrome-mcp-DZMaKINm.mjs:211` and `:218`, inside
`refreshChromeMcpCleanupProcess`. The mechanism:

- Each Chrome DevTools MCP session (the `npx chrome-devtools-mcp@1.8.0
  --autoConnect` subprocess spawned for `user`/`muratclaw`-as-existing-session)
  tracks its own process tree (`session.processCleanup`), with states `open` →
  `tracked` → `closed`, or `uncertain` on failure.
- On close, `closeChromeMcpSessionHandle` calls `refreshChromeMcpCleanupProcess`
  again to re-snapshot the OS process list (`ps`/`wmic`-style, via
  `listChromeMcpPlatformProcesses`) and confirm the tracked root PID **and its
  recorded identity** (`{pid, identity}` — a start-time/command-line fingerprint,
  not just the PID) still match, or that the tree is actually gone.
- If that re-snapshot throws (the platform process-list call itself fails,
  the root PID's identity has changed — e.g. the OS recycled the PID onto an
  unrelated process — or the previous kill attempt's own exit could not be
  confirmed), the session's state is set to `"uncertain"` and
  `refreshChromeMcpCleanupProcess` throws exactly the string quoted in the
  handoffs, **every time it is called again**, because an `"uncertain"` root
  with no resolvable PID always re-throws at the top of the function
  (`chrome-mcp-DZMaKINm.mjs:211`).
- Aegis's own `openclaw_client.py` (`_run`, lines ~540 and the `ensure_attached`
  logic quoted in `docs/OPENCLAW_2026-09-26_READING_MURATS_CHROME.md` §12.1)
  already special-cases this exact string as `GATEWAY_NEEDS_RESTART` and
  refuses to retry `start` against it — which matches the code: retrying
  `start` re-enters the same owner object with the same stuck `"uncertain"`
  state, it does not re-attempt a fresh kill.

**Can it be cleared without restarting the whole gateway?** The in-memory state
lives in a module-level `owners` Map inside the Gateway's Node process
(`extensions/browser/src/browser/chrome-mcp-session.ts`, compiled into
`chrome-mcp-DZMaKINm.mjs`), keyed per profile. Restarting the *gateway process*
resets that Map, which is the only path the reader's own handoffs record as
working. From reading the code (not executed — no browser verbs were run per
the hard rule):
  - `openclaw browser stop` for the stuck profile calls `closeChromeMcpSession`
    → `stopOwners(profileName)` → each owner's `stop()`, which itself calls
    `refreshChromeMcpCleanupProcess` again — if the underlying OS process is
    genuinely gone (not just unconfirmable), this *could* succeed and clear the
    state without touching the gateway process. This is untested here and
    should be tried once, off-hours, before assuming only a full restart works.
  - If the underlying `node`/`chrome-devtools-mcp` child is still alive but
    orphaned, killing it **by PID** (found via
    `Get-CimInstance Win32_Process | Where CommandLine -match 'chrome-devtools-mcp'`
    — never `taskkill /IM`, per this repo's own standing rule) and then
    retrying `browser stop`/`start` might let the re-snapshot succeed. This is
    a hypothesis from the code, not a verified fix — flag it to the operator to
    try, do not treat it as confirmed.
  - Absent either working, a full `openclaw gateway restart` remains the only
    confirmed remedy (per this repo's own two hand-fixes the same night, and
    per the fact that only the 08:02 supervisor exit and a manual restart ever
    cleared it in the 09-27→09-28 log).

## B. ONLY MURATCLAW

`openclaw.json` today: `browser.defaultProfile = "muratclaw"`,
`browser.profiles.muratclaw = { cdpPort: 18801 }` — **no `driver`, no
`attachOnly`, no `cdpUrl`**. That means `muratclaw` is currently an
**OpenClaw-managed** profile: OpenClaw itself launches
`C:\Program Files\Google\Chrome\Application\chrome.exe` with its own
user-data-dir (`~/.openclaw/browser/muratclaw/user-data`, from
`resolveOpenClawUserDataDir` in `dist/chrome-DP31s2Db.mjs`) and drives it
directly over CDP/Playwright. **This is a different Chrome instance and a
different user-data-dir from the repo's own
`C:\Users\mrthn\ChromeMuratClaw`** (created by
`scripts/open_muratclaw_chrome.cmd`, port 18802 via
`scripts/open_muratclaw_chrome_attach.cmd`) — the two "MuratClaw" things share
a name by coincidence, not a wired connection. This is worth flagging on its
own: the repo's docs (`OPENCLAW_2026-09-26_READING_MURATS_CHROME.md`) describe
`muratclaw` as "OpenClaw's managed automation Chrome... never signed in to
Google," which is consistent with this being the fully-managed profile, not the
repo's separately-launched `ChromeMuratClaw` folder.

### The three supported ways to define a profile

From `docs/tools/browser/existing-session.md` and `docs/tools/browser/remote.md`:

1. **OpenClaw-managed, own user-data-dir**: no `driver` (or `driver` omitted),
   set `cdpPort` (and optionally `executablePath`). OpenClaw launches and owns
   the Chrome process; its user-data-dir lives under
   `~/.openclaw/browser/<name>/user-data` unless overridden. This is what
   `muratclaw` is today. Google can and does refuse sign-in here (see below).
2. **Explicit `cdpUrl`/`attachOnly` pointing at an already-running Chrome**:
   ```json5
   { attachOnly: true, cdpUrl: "http://10.0.0.42:9222" }
   ```
   confirmed in `docs/tools/browser/configuration.md`'s `remote` example and
   `docs/tools/browser/remote.md`: *"For externally managed CDP services on
   loopback... also set `attachOnly: true`. Loopback CDP without `attachOnly`
   is treated as a local OpenClaw-managed browser profile."* OpenClaw never
   launches this Chrome; it only attaches via raw CDP (Playwright-backed, so
   it gets the **full** feature set — `networkidle` waits, `batch`, downloads,
   PDF — none of which existing-session profiles get).
3. **`existing-session` driver restricted to one user-data-dir**: `driver:
   "existing-session"`, `attachOnly: true`, and either `userDataDir` (for
   Chrome-MCP `--autoConnect` against a specific profile directory) or
   `cdpUrl` (to skip `--autoConnect` and target one DevTools endpoint
   directly). This is the Chrome DevTools MCP path — what `user` uses — and is
   explicitly more constrained (`docs/tools/browser/existing-session.md`
   "Existing-session feature limitations": no `batch`, no `networkidle` wait,
   ref-only actions, no `requests`/`errors`/`text`/`emulate`, no PDF).

### Recommended JSON for MuratClaw

Chrome is already plain-launched by `scripts/open_muratclaw_chrome_attach.cmd`
with its own profile directory and `--remote-debugging-port=18802
--remote-debugging-address=127.0.0.1` (loopback-only, confirmed by reading that
`.cmd` file). Option 2 (explicit `cdpUrl` + `attachOnly`) is the best fit: it
is a genuinely separate OS process (own user-data-dir, own port, launched by
Murat's own script, not by OpenClaw), it gets full Playwright capability
(unlike `existing-session`), and it does not carry the "OpenClaw launched this
Chrome" fingerprint that the managed-profile path (`muratclaw` today) has.

```json5
{
  browser: {
    defaultProfile: "muratclaw",
    profiles: {
      muratclaw: {
        attachOnly: true,
        cdpUrl: "http://127.0.0.1:18802"
      }
    }
  }
}
```

Set as default: `browser.defaultProfile: "muratclaw"` (already set). Verify
with `openclaw browser --browser-profile muratclaw status --json` → expect
`driver` absent/attach, `attachOnly: true`, `cdpUrl` echoed, `running: true`
only while `open_muratclaw_chrome_attach.cmd`'s Chrome is up.

### Disabling `user` / `chrome` so nothing can reach the main Chrome

No single config flag documented (or found in `dist/`) removes the built-in
`user`/`chrome` profiles outright — they are always offered as profile names,
not entries that must exist in `browser.profiles`. What actually gates them,
per the docs read:

- `user` (Chrome DevTools MCP existing-session) requires Chrome's own
  `chrome://inspect/#remote-debugging` toggle to be **on** in the target
  window, and the first attach shows a blocking "Allow remote debugging?"
  consent prompt (`docs/tools/browser/profiles.md`, `docs/tools/browser/
  existing-session.md`). With that toggle off in Murat's main Chrome, `user`
  cannot attach to it at all — this is the existing repo guidance
  (`open_muratclaw_chrome.cmd`'s own comment: *"In the MAIN Chrome, untick that
  same box so nothing can attach to it"*) and is the real control, not a JSON
  key.
- `chrome` (extension relay) requires the OpenClaw Chrome extension to be
  loaded and paired into a specific Chrome profile
  (`docs/gateway/security/browser-control.md`: pairing access mode is stored
  in extension-owned Chrome storage). Never load/pair that extension into
  Murat's main profile, and it stays unreachable.
- Belt-and-suspenders, already coded in this repo:
  `backend/services/openclaw_client.py`'s `profile()` refuses any name not in
  `config.OPENCLAW_ALLOWED_PROFILES` and never falls back
  (`REFUSED_BROWSER_PROFILE_NOT_ALLOWED`). That is an *application-layer*
  guarantee, independent of anything in `openclaw.json`, and is the strongest
  actual protection today — it is what already stops any Aegis code path from
  ever naming `user`/`chrome` by accident.

Net: **PARTLY** — there is no `openclaw.json` switch that deletes/disables the
built-ins outright, but the combination of (a) the remote-debugging toggle
staying off on the main Chrome, (b) never pairing the extension into the main
profile, and (c) Aegis's own allowlist refusal is a real, working boundary,
just not a single config key.

### Can a human sign in to Google inside MuratClaw?

`buildOpenClawChromeLaunchArgs` (`dist/chrome-DP31s2Db.mjs:1988`) — the exact
args OpenClaw passes when it launches a **managed** profile — is:

```
--remote-debugging-port=<port> --user-data-dir=<dir> --no-first-run
--no-default-browser-check --disable-sync --disable-background-networking
--disable-component-update --disable-features=Translate,MediaRouter
--disable-session-crashed-bubble --hide-crash-restore-bubble
--password-store=basic [--no-sandbox if configured] [--disable-dev-shm-usage on linux]
--no-proxy-server [+ any browser.extraArgs]
```

Notably **absent**: `--enable-automation`,
`--disable-blink-features=AutomationControlled`, or any explicit "controlled by
automated test software" flag — OpenClaw does not add the classic Selenium/
Puppeteer default-arg automation banner itself. The repo's own note that
Google refuses `muratclaw`'s sign-in is therefore not explained by an obvious
launch-flag signature in this code; Google's sign-in block is a broader,
industry-wide response to *any* CDP-controlled (Playwright/Chrome-MCP-driven)
browser session, independent of which specific flags launched it. That
mechanism is outside this note's scope to investigate further (it borders on
bot-detection evasion, which is explicitly out of scope).

What the docs **do** recommend, and what is consistent with not touching that
scope boundary: `docs/tools/browser-login.md` — *"When a site requires login,
sign in manually in the host browser's `openclaw` profile."* Applied to the
`attachOnly`/`cdpUrl` design in this section: Chrome is opened by
`open_muratclaw_chrome_attach.cmd` (a **plain** launch with only
`--remote-debugging-port`/`--remote-debugging-address`, no OpenClaw automation
args at all) — sign in to Google by hand in that window **before** OpenClaw's
`browser --browser-profile muratclaw` ever attaches and starts issuing CDP
actions. Once signed in, OpenClaw's later reads are ordinary CDP navigation and
snapshot calls against an already-authenticated profile; it never has to touch
credentials. Whether Google's session-risk model later still flags the CDP
attachment itself once OpenClaw starts driving it is a real open question this
note cannot answer without researching evasion, which is out of scope — treat
sign-in success as something to verify empirically, not something this
research resolves.

## C. NO PROCESS PER VERB

Two supported persistent-connection paths, in order of how much of Aegis's own
safety layer they preserve:

### C1 — `POST /tools/invoke` (recommended; always enabled, no opt-in env var)

`docs/gateway/tools-invoke-http-api.md`: *"OpenClaw's Gateway exposes an HTTP
endpoint for invoking a single tool directly. It is always enabled and uses
Gateway auth plus tool policy."* Same port as the gateway (default `18789`),
one HTTP POST per action, ordinary `requests.Session()` keep-alive — no
`openclaw.mjs` process spawned per verb. `browser` is **not** on the endpoint's
default hard-deny list (`exec`, `spawn`, `shell`, `fs_write`, `fs_delete`,
`fs_move`, `apply_patch`, `sessions_spawn`, `sessions_send`, `cron`, `gateway`,
`nodes` are; `browser` is absent from that list in
`docs/gateway/tools-invoke-http-api.md`).

Request/response shape:

```
POST http://127.0.0.1:18789/tools/invoke
Authorization: Bearer <gateway token>          # gateway.auth.token / OPENCLAW_GATEWAY_TOKEN
Content-Type: application/json

{"tool": "browser", "args": {"action": "navigate", "profile": "muratclaw", "url": "https://www.wsj.com/..."}}

-> 200 {"ok": true, "result": { ... same shape as `openclaw browser navigate --json` ... }}
-> 400 {"ok": false, "error": {"type": "...", "message": "..."}}
-> 403 {"ok": false, "error": {"type": "...", "message": "...", "requiresApproval": true}}
-> 404 tool not allowlisted
```

The agent-facing `browser` tool's actions (`docs/tools/browser/agent-tools.md`)
are `doctor|status|start|stop|tabs|open|focus|close|snapshot|screenshot|
navigate|act|requests|errors|text|emulate`, addressed by `targetId` (reuse the
value `tabs`/`open` returned). Clicking/pressing/scrolling all go through
`action: "act"` with a nested `kind` (`click`, `clickCoords`, `press`, `hover`,
`scrollIntoView`, `drag`, `select`, `fill`, `wait`, `evaluate`, `close`,
`batch` — the same closed union documented for the standalone `/act` route in
`docs/tools/browser-control.md`).

Minimal Python example (not added to the repo — this is illustrative only):

```python
import requests

GW = "http://127.0.0.1:18789"
TOKEN = "<gateway token, from a local secret store, never hardcoded>"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def invoke(tool: str, args: dict) -> dict:
    r = requests.post(f"{GW}/tools/invoke", headers=HEADERS,
                       json={"tool": tool, "args": args}, timeout=30)
    r.raise_for_status()
    return r.json()

tabs = invoke("browser", {"action": "tabs", "profile": "muratclaw"})
opened = invoke("browser", {"action": "navigate", "profile": "muratclaw",
                             "url": "https://www.wsj.com/", "targetId": tabs["result"]["tabs"][0]["tabId"]})
snap = invoke("browser", {"action": "snapshot", "profile": "muratclaw",
                           "targetId": opened["result"]["targetId"], "format": "ai"})
click = invoke("browser", {"action": "act", "profile": "muratclaw",
                            "targetId": opened["result"]["targetId"],
                            "kind": "click", "ref": "f1e12"})
press = invoke("browser", {"action": "act", "profile": "muratclaw",
                            "targetId": opened["result"]["targetId"],
                            "kind": "press", "key": "PageDown"})
```

### C2 — the standalone Browser Control HTTP API (opt-in)

`OPENCLAW_EAGER_BROWSER_CONTROL_SERVER=1` in the gateway service environment,
gateway restart, then `GET/POST` a wider REST surface
(`/tabs`, `/tabs/open`, `/navigate`, `/act`, `/snapshot`, `/screenshot`,
`/cookies`, `/storage/:kind`, ... — full list in
`docs/tools/browser-control.md`, confirmed live). Same auth
(`Authorization: Bearer <token>` or `x-openclaw-password`). This is a bigger
surface (profile create/delete, screencast, cookie/storage read-write) but
needs the env var + restart, and per
`docs/gateway/security/browser-control.md` it is a **full operator-access**
surface with SSRF and profile risk the same as C1 — no narrower.

### C3 — raw WebSocket RPC (lowest level, not recommended for this use case)

`docs/gateway/protocol/transport.md`: text frames, JSON, first frame must be
`{type:"connect", ...}`, gateway replies `hello-ok`; then
`{type:"req", id, method, params}` → `{type:"res", id, ok, payload|error}`.
The `browser.request` method exists (mentioned in
`docs/tools/browser-control.md`: *"The Control UI's `browser.request` Gateway
method accepts `target: 'host'`..."*). This is the mechanism the CLI and the
Control UI themselves use underneath; C1 is a thin, documented HTTP wrapper
over effectively the same capability and is simpler to drive from Python.

### What is lost compared with the CLI (i.e., compared with `openclaw_client.py` today)

Everything Aegis added is enforced **in `backend/services/openclaw_client.py`
itself, on top of the CLI**, not inside OpenClaw. Calling `/tools/invoke`
directly bypasses ALL of it unless it is reimplemented on the Python caller's
side:

- `DENIED_DOMAINS` (brokerage/bank/payment substring refusal) — OpenClaw itself
  has no equivalent list; its SSRF policy blocks private/internal network
  destinations, not named public financial domains.
- `ALLOWED_VERBS`/`OPERATOR_VERBS`/`OPERATOR_TAB_VERBS` restriction, the
  `evaluate`-is-never-allowed rule (Aegis refuses it at the wrapper; OpenClaw's
  `browser act kind=evaluate` is available by default via `/tools/invoke`
  unless `browser.evaluateEnabled=false` is set globally).
- The operator-tab host allowlist (`wsj.com`/`barrons.com`/`marketwatch.com`)
  and the re-check after every navigate/click/press — OpenClaw's SSRF policy
  does not know about Aegis's specific "must currently be on one of these three
  hosts" rule.
- `open_from_tab`'s "new tabs only ever land inside an existing MuratClaw tab,
  never a bare `open`" discipline, the marker-tab (`?aegis=muratclaw`) check,
  and the "never `open` on an operator profile" refusal.
- The CLI-route work (no-shell `&`-safe argv, UTF-8 decoding fix, ANSI strip)
  is moot for HTTP JSON, but the profile/tabs caching, CLI-seconds telemetry,
  and `cli_ledger()` cost accounting all disappear — a direct HTTP caller has
  no equivalent cost/footprint receipt unless it builds one.
- Human-pace throttling (`Throttle`, the 20-90s jittered gap, per-host caps,
  scroll-before-read) lives in `web_reader.py`/`scripts/dowjones_pull.py`, not
  in OpenClaw — a raw HTTP caller could hammer a page at full speed with
  nothing in OpenClaw itself stopping it.

None of this is a defect in OpenClaw; it is exactly what a thin CLI wrapper is
for. The practical conclusion: **if C1/C2 is ever used, re-host the same
policy layer (`openclaw_client.py`'s checks) in front of the HTTP calls** —
do not call `/tools/invoke` directly from a new code path without it.

## D. MESSAGES TO THE OWNER

### What already exists on this machine

Telegram is running today, but it is **Aegis's own bot**, not an OpenClaw
channel: `backend/services/telegram_bridge.py` polls `api.telegram.org`
directly with `TELEGRAM_BOT_TOKEN`/`TELEGRAM_OWNER_CHAT_ID` from `.env` (names
only confirmed; values never read/printed). `openclaw.json`'s `channels: {}` is
**empty** — OpenClaw itself has no chat channel configured at all, and
`commands.ownerAllowFrom: []` is empty too. This matches
`backend/services/openclaw_client.py`'s own `_channel_count()` health check
(*"OpenClaw must have NO chat channel. Aegis owns the messaging."*) and the
repo's stated chain: `OpenClaw -> Aegis -> Telegram`, never `OpenClaw ->
human` — the structural fix adopted after the WhatsApp incident
(`docs/OPENCLAW_2026-09-22_SETUP.md`'s superseding note points at
`docs/OPERATOR_SURFACE_2026-09-22_TELEGRAM_SIMS_AND_THE_WHATSAPP_INCIDENT.md`).

### The supported way, if OpenClaw were ever given its own channel

- `openclaw channels add --channel telegram --token <token>` registers a
  **separate** Telegram bot (a second bot, not reusing Aegis's own
  `TELEGRAM_BOT_TOKEN`) — `docs/channels/telegram.md` confirms long polling is
  the default transport, production-ready for bot DMs.
- An owner allowlist exists: `commands.ownerAllowFrom: ["telegram:<numeric
  id>"]` (`docs/gateway/heartbeat.md`). Only entries in this list are treated
  as the "operator DM" target for heartbeat alerts and automation delivery.
- Three concrete delivery mechanisms once a channel + owner exist:
  1. **`openclaw message send --channel telegram --target <chatId> --message
     "..."`** (`docs/cli/message.md`) — a direct, one-shot send, callable from
     any script/automation payload.
  2. **Heartbeat with `notify: true`** — a scheduled or event-triggered agent
     turn calls `heartbeat_respond(notify=true, notificationText=...)`, which
     delivers to `commands.ownerAllowFrom`'s first resolvable DM
     (`docs/gateway/heartbeat.md` "Response contract" / "Defaults").
  3. **An automation job with `--announce --channel telegram --to <id>
     --message "..."`** (`docs/automation/standing-orders.md`'s example uses
     iMessage for the same pattern; `docs/automation/cron-jobs.md`'s payload
     docs cover the Telegram equivalent) — a cron job's own delivery, not tied
     to heartbeat cadence.
- **System-event triggered wake**: `openclaw system event` (from
  `docs/gateway/background-process.md`'s completion-notification path and the
  top-level `system *` CLI) enqueues a system event and can trigger a
  heartbeat immediately rather than waiting for the next scheduled tick — this
  is the mechanism for "the moment we find something good," not the 30-minute
  heartbeat cadence.

### Recommendation

Given the repo's own deliberate post-incident architecture, **do not** give
OpenClaw its own Telegram channel without Murat explicitly re-opening that
decision — it re-introduces the `OpenClaw -> human` direct path the WhatsApp
incident specifically closed. The safe version of "message me when we find
something good" is: OpenClaw's `agent()` calls already return text into Aegis
(`backend/services/openclaw_client.py::agent()`), Aegis is already the thing
that grades/decides, and `telegram_bridge.py` already exists as the one
outbound channel — the missing piece is a trigger inside Aegis (not OpenClaw)
that watches for a "good enough" signal and calls the existing bridge. That
is a repo change, not an OpenClaw config change, and out of this note's
research-only scope to design further.

## E. "AS IF IT IS CONTROLLING MY PC"

### What OpenClaw offers beyond the browser

- **`exec`/`process`** (`docs/gateway/background-process.md`): arbitrary shell
  commands on the Gateway host, foreground or backgrounded, with a `process`
  tool to poll/kill. `tools.exec.host` can target `gateway`, `sandbox`, or a
  paired `node`.
- **`computer`** (`docs/nodes/computer-use.md`): full desktop control —
  screenshots, clicks, keyboard, window/app enumeration
  (`list_apps`/`list_windows`/`launch_app`/`kill_app`), on Windows via the
  optional `cua-computer` plugin.
- **File tools**: `read`/`write`/`edit`/`apply_patch` (`group:fs`) — ordinary
  filesystem read/write on whatever host the tool runs on.
- **Node commands** (`docs/nodes/command-policy.md`): camera, location,
  contacts, calendar, SMS, screen recording, etc. on paired devices, gated by
  a three-part check (node declares it, node's approved surface includes it,
  Gateway's platform allowlist includes it) plus a persistent opt-in
  (`gateway.nodes.commands.allow`) for the dangerous ones (`camera.snap`,
  `desktop.stream`, `screen.record`, `sms.send`, ...).
- **Exec approvals** (`docs/tools/exec-approvals.md`): a companion
  guardrail — `deny`/`allowlist`/`ask`/`auto`/`full` modes, per-host, with
  command-and-argument binding so an approved run can't be swapped for a
  different binary before it executes.

### What is enabled today on this machine

From the redacted `openclaw.json`: `plugins.entries.browser.enabled: true`,
`plugins.entries.whatsapp.enabled: false` (disabled per the incident),
`plugins.entries.anthropic`/`codex` present with `sessionCatalog.enabled:
false`. **No `cua-computer` plugin entry** — desktop/computer-use is not
enabled. **No explicit `tools.profile`** is set anywhere in the config, which
per `docs/gateway/config-tools/tool-policy.md` means: *"Local onboarding sets
`tools.profile: 'full'` when no profile is configured... `full` selects
tools; it does not grant Full Access execution permissions [but] the chat
Execution permissions menu controls what available tools may do."* In
practice this machine is running with the `full` tool-selection profile by
default, meaning `exec`, `read`/`write`/`edit`, and (if a computer plugin were
ever enabled) `computer` would all be *selectable* — actual execution still
runs through exec approvals, but there is no `tools.profile: "coding"` or
narrower cap in place today limiting the *catalog* itself.

### Sandbox / approval model

Layered, per the docs read: tool policy (`tools.profile`/`allow`/`deny`) picks
what is offered at all → sandbox mode (`agents.defaults.sandbox.mode`) decides
whether a session runs in an isolated sandbox vs. the host → exec approvals
(`deny`/`allowlist`/`ask`/`auto`/`full`) gate actual command execution on
whichever host is selected, with per-command allowlisting and (for
interpreter/script commands) content-hash binding so an approved run can't be
substituted after approval.

### Safe minimum for an investing research assistant, given brokerage paper-account keys in `.env` on this machine

1. **Set `tools.profile: "coding"` or a narrower custom profile**, not the
   implicit `full` default — `coding` already excludes `computer`/`group:nodes`
   and only needs `group:fs`, `group:runtime`, `group:web`, `group:sessions`,
   `group:memory` for research work. Do not enable `cua-computer` at all;
   there is no research task described here that needs desktop control.
2. **Keep `exec` on `allowlist`, never `full`/`auto`**, and never point
   `tools.exec.host` at anything that has line-of-sight to `.env` unless the
   allowlist is scoped per-command. `docs/tools/exec-approvals.md`'s own
   warning applies directly: *"Once approved, a command can mutate files
   according to the selected host or sandbox filesystem permissions"* — an
   over-broad exec allowlist on this machine is a path to the same directory
   that holds live Alpaca paper keys.
3. **Never add `.env`, the repo's key material, or the brokerage credential
   path to any node/exec allowlist entry.** The existing Aegis-side rule
   (`openclaw_client.DENIED_DOMAINS`) already blocks the *browser* from
   reaching brokerage/bank/payment URLs; there is no equivalent for `exec`/
   `computer` reaching the *filesystem* where those same credentials live, so
   that boundary has to be drawn in `tools.exec`/sandbox config, not assumed.
4. **`gateway.nodes.commands.allow` should stay empty** — none of
   `camera.snap`, `desktop.stream`, `screen.record`, `sms.send`, etc. serve an
   investing-research purpose, and each is an explicit, persistent opt-in the
   docs already gate for exactly this reason.
5. **Leave `browser.evaluateEnabled` as configured (Aegis refuses `evaluate`
   at its own wrapper already);** if C1/C2 (direct HTTP) is ever used, set
   `browser.evaluateEnabled: false` globally so OpenClaw itself also refuses
   arbitrary JavaScript, since a direct HTTP caller does not get Aegis's
   wrapper-level refusal for free.

## F. Best practice for a long-lived research agent (memory, skills, cron, sessions)

Sourced from the bundled/live docs, since this falls under "official
documentation" rather than community lore:

- **Memory**: `memory.search.rememberAcrossConversations` (per-agent) is the
  documented default for "a trusted personal agent recalling its own past
  conversations" (`docs/reference/memory-config.md`). For a research agent
  that should accumulate findings over months, this is the first knob, ahead
  of anything bespoke — it is built-in SQLite-backed hybrid search, not a
  separate memory system to build.
- **Skills**: `SKILL.md` files loaded from a precedence chain (`docs/tools/
  skills.md`): workspace skills first, then project/personal agent skills,
  then managed/bundled. For OpenClaw itself, the equivalent of "teach it how
  Aegis wants it used" is a skill under `<workspace>/skills/` — not a system
  prompt edit — since skills are the documented, versioned way to encode
  "how and when to use tools."
- **Cron / standing orders**: `docs/automation/standing-orders.md` draws the
  documented line explicitly: standing orders (in `AGENTS.md`, auto-injected
  every session) define **what** the agent is authorized to do
  autonomously and its escalation rules; `openclaw automations`/`cron` define
  **when**. The worked example is exactly this shape: a cron job's prompt
  *references* the standing order rather than re-describing the task, so the
  authority boundary lives in one place. This maps directly onto "let OpenClaw
  read the sites and tell me when something's good": the standing order says
  what counts as "good" and what requires escalation vs. autonomous action;
  the cron/heartbeat trigger just fires the check.
- **Sessions**: `docs/gateway/heartbeat.md` and `docs/automation/cron-jobs.md`
  both recommend `isolatedSession: true` / a fresh session per scheduled run
  when the job does not need full conversation history — this keeps a
  long-running research loop from re-sending months of accumulated transcript
  on every tick, which is a direct cost/latency lever for a program that (per
  this repo's own cost-discipline habit) should be measuring $/gradeable
  output.

Sources: `docs.openclaw.ai/gateway`, `docs.openclaw.ai/tools/browser-control`,
`docs.openclaw.ai/platforms/windows` (live-fetched 2026-09-28); bundled
`docs/gateway/heartbeat.md`, `docs/automation/cron-jobs.md`,
`docs/automation/standing-orders.md`, `docs/reference/memory-config.md`,
`docs/tools/skills.md` (installed package, version `2026.9.5`).

---

## RECOMMENDED TARGET CONFIGURATION

Ordered by dependency (each step's verification uses only read-only commands
already run above; none of these were executed as part of this note).

1. **Confirm the always-on gateway survives logoff, or accept it does not.**
   Change: none required if Murat is fine with "runs while logged on,
   Scheduled-Task-supervised, auto-restarts on crash" (today's actual state).
   If true 24/7-across-logoff is wanted, the documented path is a WSL2 Gateway
   with `loginctl enable-linger` (`docs/platforms/windows.md`), which is a
   larger migration, not a config tweak.
   Verify: `schtasks /Query /FO LIST /V /TN "OpenClaw Gateway"` shows
   `Logon Mode: Interactive only` today; a WSL2 systemd unit would show
   `enabled`/`active` via `systemctl status` instead.
   Rollback: n/a (no change made by this step alone).
   Needs Murat present: only if migrating to WSL2 (a one-time setup choice).

2. **Point `browser.profiles.muratclaw` at the already-running, plain-launched
   Chrome instead of letting OpenClaw manage its own.**
   Change: in `openclaw.json`, replace
   `"muratclaw": { "cdpPort": 18801 }` with
   `"muratclaw": { "attachOnly": true, "cdpUrl": "http://127.0.0.1:18802" }`,
   after starting Chrome with
   `scripts\open_muratclaw_chrome_attach.cmd`.
   Verify: `openclaw browser --browser-profile muratclaw status --json` shows
   `attachOnly: true`, `cdpUrl` matching, and `running: true` only while that
   `.cmd`'s Chrome window is open; `openclaw browser --browser-profile
   muratclaw tabs` lists only tabs from that Chrome, never Murat's main one.
   Rollback: restore `"muratclaw": { "cdpPort": 18801 }` and restart the
   gateway; OpenClaw resumes managing its own Chrome under
   `~/.openclaw/browser/muratclaw/user-data`.
   Needs Murat present: **yes**, once, to run `open_muratclaw_chrome.cmd`,
   sign in to Google/WSJ/Barron's/MarketWatch by hand, close it, then run
   `open_muratclaw_chrome_attach.cmd` before OpenClaw's next attach.

3. **Turn off `chrome://inspect/#remote-debugging` in Murat's main Chrome**
   (if it is ever turned on for `user`-profile handoffs) as soon as a handoff
   session ends, so `user` cannot attach outside of an explicit, attended
   window.
   Verify: `openclaw browser --browser-profile user status` reports
   `stopped`/not attachable when the toggle is off.
   Rollback: turn the toggle back on for the next explicit handoff.
   Needs Murat present: **yes** — this is a manual Chrome UI action, by
   design (the whole point is that it requires him).

4. **Never load/pair the OpenClaw Chrome extension into Murat's main Chrome
   profile.** No config change — an omission to preserve. If the `chrome`
   profile is ever wanted, pair the extension into a dedicated Chrome profile
   only.
   Verify: `openclaw browser --browser-profile chrome status` should report
   unpaired/unavailable unless deliberately set up.
   Rollback: n/a.
   Needs Murat present: only if the `chrome` profile is deliberately set up
   later.

5. **If a raw-HTTP path (C1/C2) is ever built, re-host `openclaw_client.py`'s
   policy layer in front of it** (denied domains, allowed verbs, operator-tab
   host checks, human-pace throttling) before any caller uses `/tools/invoke`
   or the eager Browser Control API directly. This is a code change in this
   repo, not an OpenClaw config change, and is out of scope for this note to
   implement.
   Verify: a policy test mirroring `test_openclaw_client.py`'s existing
   refusal tests, run against the new HTTP-calling code path.
   Rollback: do not ship the raw-HTTP caller until the policy layer exists.
   Needs Murat present: no.

6. **Do not give OpenClaw its own Telegram channel** without Murat explicitly
   revisiting the post-WhatsApp-incident decision. If "message me when we find
   something good" is wanted sooner, wire the trigger into Aegis's existing
   `telegram_bridge.py`, not into `openclaw.json`'s `channels`.
   Verify: `openclaw.json` `channels` stays `{}` and `commands.ownerAllowFrom`
   stays `[]` unless this decision is explicitly revisited.
   Rollback: n/a — this step is "keep the current state," not a change.
   Needs Murat present: **yes**, if/when he decides to revisit it.

7. **Set an explicit `tools.profile` (e.g. `coding`) instead of relying on the
   implicit `full` default**, and keep `cua-computer` disabled, given
   brokerage paper-account keys live in `.env` on this machine.
   Verify: `openclaw config get tools.profile` returns the explicit value
   (today it is unset, which resolves to `full`); `openclaw plugins list`
   shows `cua-computer` absent/disabled.
   Rollback: `openclaw config unset tools.profile` restores the implicit
   default.
   Needs Murat present: no, but he should sign off on which tools a
   research agent gets before it changes, per this repo's own "no new guard
   without an actual failure, but also no silent capability expansion"
   posture.

8. **Do not attempt to clear a `GATEWAY_NEEDS_RESTART`/"subprocess tree
   cleanup could not be verified" jam by looping `browser start`** — the code
   shows this re-enters the same stuck state. Try, at most once and off-hours,
   `openclaw browser stop --browser-profile <name>` before falling back to a
   full `openclaw gateway restart`; if a stray `chrome-devtools-mcp` node
   process is found by PID (`Get-CimInstance Win32_Process`, filtered on
   command line, never `taskkill /IM`), that is a second thing to try before
   the full restart, not a substitute investigation for why it recurs.
   Verify: `openclaw browser --browser-profile <name> status` returns a clean
   `stopped`/`running` state, not the cleanup error.
   Rollback: n/a — this is a repair action, not a persistent change.
   Needs Murat present: no, but a full gateway restart briefly drops any
   in-flight reader work, so it should not be automated inside the night
   supervisor without the bounded-retry design R1/R2 already called for in
   `docs/HANDOFF_2026-09-28_THE_READER_NIGHT.md`.
