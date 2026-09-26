# OpenClaw to its finest: scraper, desktop agent, and Optimus — research note

**Date:** 2026-09-26 · **Scope:** research only, no LLM spend, no browser calls, code read-only.
**Sources:** OpenClaw docs bundled locally at
`C:\Users\mrthn\AppData\Roaming\npm\node_modules\openclaw\docs\` (version 2026.9.5, all
paths below are relative to that root unless given as a URL) · `backend/services/openclaw_client.py`
· `scripts/source_reads.py` · `scripts/thesis_cards.py` · a handful of directly-fetched
external pages (listed with URLs in §5). **`WebSearch` was already at its session-wide
budget (200/200) before this task started, session-wide, not something this task
consumed — so §5 is thinner than asked and says so rather than inventing links.**

---

## 0. One-line answer to "what do I do in my Chrome, once"

Murat: in the already-open Chrome window that has **MuratClaw (Work)** loaded, go to
`chrome://inspect/#remote-debugging`, turn the toggle on, and accept the "allow remote
debugging" prompt Chrome shows you — keep that window open. That, plus Chrome being
build **144+** (`chrome://version`; if it isn't 144 yet, Google's own guidance is to
run Chrome on the `beta` channel until 144 reaches stable), is the one manual step the
`user` profile route needs every time you want OpenClaw to drive that exact window
(`tools/browser/existing-session.md`; Chrome for Developers blog, fetched below).

---

## 1. Attach to the user's own Chrome, definitively

### 1.1 What the two routes actually are

OpenClaw ships **three** browser drivers, not two (`tools/browser/existing-session.md`,
`gateway/config-browser-ui-desktop.md`):

| Profile (driver)                       | What it does                                                                                       |
|-----------------------------------------|------------------------------------------------------------------------------------------------------|
| `openclaw` (managed)                    | A separate, isolated Chromium OpenClaw launches and owns. This is the profile Murat correctly identified as "always opening a new browser" — it is **never** his signed-in Chrome (`tools/browser.md`: "the `openclaw` profile never touches your personal browser profile"). |
| `user` (existing-session / Chrome DevTools MCP) | Attaches to an **already-running** Chromium-based browser via the official Chrome DevTools MCP server, using Chrome's own remote-debugging protocol. Built in; no install step beyond enabling remote debugging. |
| `chrome` (extension relay)              | The OpenClaw Chrome extension, installed into that same signed-in Chrome, driven via `chrome.debugger` — no remote-debugging consent prompt per session, but real install/pairing work up front (`tools/chrome-extension.md`). |

Both `user` and `chrome` are capable of "controlling the browser I'm actually looking
at." Neither one gives OpenClaw a profile-picker UI the way Chrome's own avatar menu
does — profile targeting is a **config-time binding** (which Chrome installation /
which `userDataDir` / which profile the extension is approved inside), not a runtime
verb. This is the nuance behind Murat's "it doesn't show other Chrome profiles":
that picker doesn't exist in OpenClaw; you point a *named profile* at one specific
Chrome profile directory instead.

### 1.2 `user` (existing-session) — exact Windows steps

1. **Chrome version ≥ 144.** `chrome://version`. Until 144 ships to the stable
   channel, Google's guidance is to run the `--channel=beta` build
   (Chrome for Developers blog, fetched 2026-09-26: "This feature requires Chrome
   M144 or later... until M144 reaches the stable channel, users must specify
   `--channel=beta`").
2. In the **MuratClaw (Work)** window itself, open `chrome://inspect/#remote-debugging`
   and follow the dialog to permit incoming debugging connections
   (`tools/browser/existing-session.md`, "Common inspect pages"; Chrome blog,
   same fetch: "navigate to `chrome://inspect/#remote-debugging` and follow the
   dialog prompts to permit incoming debugging connections").
3. **Keep the browser running** and **approve the connection prompt** when OpenClaw
   attaches — Chrome shows a consent dialog, then a persistent
   "**Chrome is being controlled by automated test software**" banner once
   accepted (`tools/browser/existing-session.md`: "Keep the browser running and
   approve the connection prompt when OpenClaw attaches"; Chrome blog: same banner
   text).
4. Smoke test (`tools/browser/existing-session.md`, "Live attach smoke test"):
   ```bash
   openclaw browser --browser-profile user start
   openclaw browser --browser-profile user status
   openclaw browser --browser-profile user tabs
   openclaw browser --browser-profile user snapshot --format ai
   ```
5. **What success looks like**, verbatim from the doc: `status` shows
   `driver: existing-session`, `transport: chrome-mcp`, `running: true`; `tabs`
   lists your already-open tabs; `snapshot` returns refs from the selected live
   tab.
6. **Route limits** (`tools/browser/existing-session.md` Accordion; `cli/browser.md`
   "Current existing-session limits"), confirmed against your list:
   - **No `batch`** — "batch is not supported on `profile="user"` / existing-session
     profiles" (both docs, verbatim).
   - **No `responsebody`, no PDF export, no download interception** — Playwright-only
     features; `existing-session` doesn't have Playwright behind it.
   - Actions use snapshot **refs only**, never CSS selectors; `click` is left-button
     only; `type` has no `slowly=true`; `select` takes one value; uploads need a
     `ref`/`inputRef`, not CSS `element`; `wait --load networkidle` is unsupported
     (works on managed/raw-CDP profiles); dialog hooks have no timeout override.
   - Screenshots: page and `--ref` captures work; CSS `--element` captures don't.

### 1.3 The `DevToolsActivePort` error you hit

**Not documented in OpenClaw's own docs** (grepped the whole tree for
"DevToolsActivePort" — zero hits). This is a well-known Puppeteer/`chrome-launcher`
error string, not an OpenClaw-specific one, so treat the next paragraph as informed
diagnosis, not a doc citation.

Chrome writes the `DevToolsActivePort` file only after it finishes **launching**
successfully. The error means chrome-devtools-mcp's `--autoConnect` did not find an
already-listening CDP endpoint (because step 2 above hadn't actually taken effect
yet — wrong Chrome build, or the toggle was clicked but the consent dialog never got
approved) and fell back to **launching a brand-new Chrome process** using the same
default profile directory your already-running Chrome (pid 96488) already owns.
That second launch fails immediately because the profile is locked, so Chrome exits
before it ever writes the port file. **Fix: confirm 144+, confirm the toggle is
actually on (Chrome should already be showing the automation banner or at least the
inspect page should list a discoverable target) before running `browser --browser-profile
user start`.** If it still fails, the doc's own escape hatch is to quit and relaunch
Chrome once with an explicit port and point OpenClaw at that instead of autoConnect:
```
chrome.exe --remote-debugging-port=9222 --user-data-dir="..."
```
then set `browser.profiles.user.cdpUrl` to `http://127.0.0.1:9222`
(`tools/browser/existing-session.md`: "if Chrome was started with an explicit
`--remote-debugging-port`, set `browser.profiles.<name>.cdpUrl` to that DevTools
endpoint instead of relying on Chrome MCP auto-connect"). This does mean a full
Chrome restart, losing the currently-open tabs in that window — a real cost, which
is the main argument for getting the toggle-based flow working instead.

**Multiple profile windows open at once:** the docs don't say explicitly how
autoConnect discriminates between two simultaneously-open Chrome profile windows
under one installation. Chrome MCP auto-connect targets "the default local Google
Chrome profile" by default (`tools/browser/existing-session.md`); for a *named*
non-default profile you create your own existing-session profile with an explicit
`userDataDir` pointing at that profile's own directory (find it via
`chrome://version` → "Profile Path" while inside that profile window) — documented
for Brave/Edge but the same `userDataDir` mechanism generalizes:
```bash
openclaw browser create-profile --name muratclaw-work --driver existing-session \
  --user-data-dir "C:\Users\mrthn\AppData\Local\Google\Chrome\User Data\<ProfileDir>"
```
(`tools/browser/existing-session.md`, "Use `userDataDir` for Brave, Edge, Chromium,
or a non-default Chrome profile"; `cli/browser.md` create-profile examples). Given
"MuratClaw (Work)" is a profile **inside** the default Chrome install rather than a
separate browser, this is the right lever if the built-in `user` profile ever
attaches to the wrong window.

### 1.4 `chrome` (extension relay) — exact steps

1. Requirements: Chrome/Chrome for Testing/Chromium, launched at least once so its
   user-data directory exists; OpenClaw on the same machine
   (`tools/chrome-extension.md`).
2. **Windows keeps manual pairing** — there is no automatic native bootstrap on
   Windows ("Windows keeps manual pairing. Current Chromium launches native hosts
   directly only when the registered host is a Windows executable," same doc).
   Steps:
   - `openclaw browser extension install --no-store` — registers the native host and
     copies the extension to a stable OpenClaw-owned directory; prints the path for
     **Load unpacked**. Run `openclaw browser extension path` to get the exact,
     current path rather than assuming `C:\Users\mrthn\.openclaw\browser\chrome-extension`
     — the doc says only that it "prints the stable installed copy when present and
     the bundled source directory otherwise," so the literal path is dynamic; your
     guessed path is plausible but should be confirmed by the command itself.
   - `chrome://extensions` → **Developer mode** → **Load unpacked** → select the
     printed path.
   - Add the Store version too if you want the non-dev flow later:
     [chromewebstore.google.com/detail/openclaw/kcdjddhmeafeomebliikmbpblkmkfoig](https://chromewebstore.google.com/detail/openclaw/kcdjddhmeafeomebliikmbpblkmkfoig).
   - **Manual pairing string**: `openclaw browser extension pair` (host-local) or
     `openclaw browser extension pair --gateway-url wss://...` for a remote Gateway.
     Paste the printed string into the extension's **Settings → Advanced manual
     pairing**. "Treat the complete pairing string as a password"
     (`tools/chrome-extension.md`).
3. **Per-profile approval**: "The request applies to all profiles in that Chrome
   user-data directory. Chrome controls approval in each profile" — meaning Murat
   must separately enable/approve the OpenClaw extension **inside the MuratClaw
   (Work) profile itself**, not just his default profile, even though both live
   under one Chrome install (`tools/chrome-extension.md`).
4. **Access mode**: fresh pairings default to **All tabs** — "exposes every eligible
   ordinary tab in that Chrome profile, except tabs paused for the current browser
   session." The alternative, **Selected tabs**, scopes access to an explicit
   "OpenClaw" tab group. For "just drive whatever I have open," **All tabs** is the
   one that matches Murat's ask (same doc, "Choose tab access").
5. Make it default:
   ```bash
   openclaw config set browser.defaultProfile chrome
   ```
   or in config: `browser.profiles.chrome = { driver: "extension" }`.

### 1.5 Which one should be Aegis's default, and why

**Recommendation: `user` (existing-session) as the near-term default, with `chrome`
(extension) as the target once its one-time Windows setup is done.**

- The extension relay is architecturally the better long-term fit for exactly the
  complaint Murat raised — "it should be using an already open one" — because it
  reuses `chrome.debugger` inside the actual browser process with **no
  remote-debugging consent prompt per session** (`tools/chrome-extension.md`
  summary: "lets the browser tool automate eligible tabs in your signed-in Chrome
  profile... does not require Chrome's blocking remote-debugging consent prompt").
- But on Windows it needs the one-time Load-unpacked + manual pairing-string dance
  in §1.4, and per-profile approval inside MuratClaw (Work) specifically — real,
  one-time setup cost.
- `user`/existing-session needs **no install**, but its `chrome://inspect` toggle is
  the part most likely to need re-doing after a full Chrome quit/relaunch (the docs
  don't state whether the toggle survives a full restart; treat it as session-scoped
  until proven otherwise) and it is missing `batch`, downloads-via-interception,
  and PDF export — all things `scripts/dowjones_pull.py` (§6) will eventually want.
- Practical order: get `user` working today (§1.2–1.3) to unblock the scraper chunk
  immediately; do the `chrome` extension setup as a follow-up chunk once the
  read-only pipeline is proven, then flip `AEGIS_OPENCLAW_PROFILE` (or its
  successor config key, §6a) to `chrome`.

Either way, `backend/services/openclaw_client.assert_profile` today hard-refuses
anything but `"muratclaw"` (`DEFAULT_PROFILE = "muratclaw"`, `PROFILE_ENV =
"AEGIS_OPENCLAW_PROFILE"`) — that assumption must change before either `user` or
`chrome` can be used from Aegis code at all (see chunk (a), §6).

### 1.6 Tab and profile-window selection commands

From `cli/browser.md` "Tabs":
```bash
openclaw browser tabs                          # list; suggestedTargetId first, then stable tabId
openclaw browser tab new --label docs
openclaw browser tab label t1 docs
openclaw browser tab select 2
openclaw browser tab close 2
openclaw browser open https://docs.openclaw.ai --label docs
openclaw browser focus docs
openclaw browser close t1
```
`tabs` returns `suggestedTargetId` first, then the stable `tabId`, an optional
label, and the raw `targetId`; pass any of these into `focus`, `close`, snapshots
and actions. **If several Chrome profiles are open in one Chrome instance**, `tabs`
against the `user` profile returns whatever the attached Chrome MCP subprocess can
see for its one target set — the doc does not promise cross-profile visibility in a
single call; if the wrong profile's tabs show up (or none do), bind a dedicated
existing-session profile with an explicit `userDataDir` for that profile, as in
§1.3.

---

## 2. Why a quest "sits idle" and how to make it act

### 2.1 Root cause, grounded in how Aegis actually calls OpenClaw today

`backend/services/openclaw_client.agent()` shells out to `openclaw agent --message-file
... --model deepseek/deepseek-v4-pro --json --session-id ...` — this is the **LLM-agent
route**: OpenClaw hands the prompt to DeepSeek, and DeepSeek decides which browser tool
calls to make, if any (`backend/services/openclaw_client.py:217-281`). Both
`scripts/source_reads.py` (`discovery_prompt`, `read_prompt`, `timeline_prompt`) and
`scripts/thesis_cards.py` (via `TC.quest_prompt`, called at
`scripts/thesis_cards.py:441` and `:486`) go through exactly this route — a
natural-language prompt asking the model to "use the browser tool... open URL... read
the results... reply with ONLY one JSON object."

Two documented facts explain "opens a tab and sits idle":

1. **The full operating loop is a skill, not the tool description.** Per
   `tools/browser/setup.md` ("Agent guidance"): the `browser` tool's built-in
   description carries only "the compact always-on contract" (pick the right
   profile, keep refs on the same tab, use `tabId`/labels, *load the browser skill
   for multi-step work*). The actual snapshot → act → resnapshot loop — "check
   status/tabs first, label task tabs, snapshot before acting, resnapshot after UI
   changes, recover stale refs once, report login/2FA/captcha/camera blockers as
   manual action instead of guessing" — lives in the bundled
   **`browser-automation` skill**, and "the full skill instructions load on demand,
   so routine turns do not pay the full token cost." If a given turn's model never
   pulls that skill in — a plausible failure mode for a model driven purely by a
   short one-shot prompt with a tight token/cost budget (`THESIS_CARD_EST_QUEST_USD
   = 0.08` per quest, `backend/config.py:3982`) — it has no instruction to do
   anything past `open`.
2. **The existing prompts are written for static read pages, not multi-step
   navigation.** `discovery_prompt`/`read_prompt`/`timeline_prompt` in
   `scripts/source_reads.py` ask the model to open one URL, "scroll once or twice,"
   and report JSON — there is no explicit click/paginate/download instruction, which
   is fine for an X search results page but is the wrong shape for "open an archive
   page, click into N articles, extract each one's text." A WSJ archive-by-date
   scrape needs an explicit multi-step contract; the current prompts don't attempt
   one.

### 2.2 The two routes: agent (judgement) vs verbs (deterministic download)

This is the load-bearing distinction the chunk spec in §6 depends on:

- **Agent route** (`openclaw agent ...`) — for *judgement*: "is this article about
  ticker X," "does this claim carry a date," synthesis. Costs LLM tokens, non-
  deterministic tool-call sequencing, subject to the "sits idle" failure above.
- **Verb route** (`openclaw browser <verb> ...`, one call per verb, via
  `openclaw_client.browser()`) — for *downloading*: deterministic, $0, scriptable,
  and exactly what a "download my WSJ/Barron's/MarketWatch subscription so I can
  analyze it" task wants. This is the route `web_reader.py` (§6b) should use — never
  the agent route — for the scraper itself.

### 2.3 Verb sequence and API notes

From `cli/browser.md` and `tools/browser/agent-tools.md`:

- `open`/`navigate` — `navigate` "also returns the loaded page's snapshot inline...
  so the agent does not need a follow-up snapshot call" (`agent-tools.md`).
- `wait --load networkidle` / `wait --text "..."` / `wait --url ...` — let dynamic
  content settle. **`networkidle` is unsupported on existing-session/`user`
  profiles** (works on managed/raw-CDP only) — use `wait --text`/`wait --url`
  instead when driving `user`.
- `snapshot --format ai [--urls] [--query "..."]` — stable UI tree with refs.
  `--urls` "appends discovered link destinations to AI snapshots so agents can
  choose direct navigation targets instead of guessing from link text alone" —
  exactly the right primitive for an archive/listing page: pull every article href
  from one snapshot, then `navigate` straight to each, skipping a `click` per link.
- `click <ref>` — for anything that must be clicked (consent banners, "load more").
- `scrollintoview <ref>` / `press End` — for infinite-scroll listing pages
  (Barron's picks).
- `text [--selector ...] [--max-chars N]` — "extracts visible prose using the first
  explicit `selector` match, otherwise the first `article`, `main`, or `body`...
  defaults to and cannot exceed 40,000 characters" (`agent-tools.md`). **This is the
  verb to use for article body extraction** — not `evaluate`, which
  `openclaw_client.py`'s own `ALLOWED_VERBS` deliberately excludes ("running
  arbitrary JavaScript in a page the agent did not write turns that page into a
  place to put instructions for the agent," `openclaw_client.py:43-46`). Keep that
  exclusion; `text` covers the scraper's real need.
- `screenshot [--full-page]` — optional provenance/audit artifact.
- `batch` — **managed/raw-CDP profiles only, not `user`/existing-session**
  (`cli/browser.md`, `tools/browser/existing-session.md`). If §1.5's near-term
  default (`user`) is in force, issue verbs one at a time; `batch` becomes available
  once the extension relay (`chrome`) is the default.
- `dialog --accept`/`--dismiss --dialog-id <id>` — for **native modal dialogs**
  (JS `confirm`/`alert`/`beforeunload`) only. Ordinary in-page cookie/GDPR banners
  and paywall "meter" overlays are DOM elements, not native dialogs — handle them
  with an ordinary `snapshot` → `click <ref>`, same as any other button.
- **Hard paywalls** (WSJ is mostly hard-metered): no verb sequence gets past one
  without real entitlement cookies. This is the whole reason to use `user`/`chrome`
  (Murat's own logged-in session) rather than the isolated `openclaw` profile —
  existing-session mode "reuses the tabs and login state already open in that
  browser profile" (`tools/browser/existing-session.md` intro), and
  `tools/browser-login.md` says explicitly: "Use `profile="user"` only when existing
  logged-in sessions matter."

### 2.4 Worked verb sequences

**A. WSJ archive-by-date → each article → text**
```bash
openclaw browser --browser-profile user open "https://www.wsj.com/news/archive/2026/09/25"
openclaw browser --browser-profile user wait --text "News Archive"      # networkidle unsupported here
openclaw browser --browser-profile user snapshot --format ai --urls
# for each article href found in the snapshot's discovered links:
openclaw browser --browser-profile user navigate "<article_url>"
openclaw browser --browser-profile user snapshot --format ai --query "accept cookies consent"
openclaw browser --browser-profile user click <ref>          # only if a consent banner ref appears
openclaw browser --browser-profile user text --selector article --max-chars 40000
openclaw browser --browser-profile user screenshot --full-page   # optional provenance
# sleep N seconds (human pace) before the next article
```

**B. Barron's "Barron's Picks" page (infinite scroll)**
```bash
openclaw browser --browser-profile user open "https://www.barrons.com/topics/barrons-picks"
openclaw browser --browser-profile user snapshot --format ai --urls
openclaw browser --browser-profile user press End             # or scrollintoview <ref of last card>
openclaw browser --browser-profile user snapshot --format ai --urls   # repeat 2-3x to load more cards
# then per-article as in (A)
```

**C. MarketWatch analyst-estimates page**
```bash
openclaw browser --browser-profile user open "https://www.marketwatch.com/investing/stock/<TICKER>/analystestimates"
openclaw browser --browser-profile user snapshot --format ai --query "consent accept"
openclaw browser --browser-profile user click <ref>            # cookie/consent banner if present
openclaw browser --browser-profile user snapshot --format ai
openclaw browser --browser-profile user text --selector main --max-chars 40000
```
Caveat: analyst-estimates is a structured table; `text` flattens it to prose and
loses column structure. Prefer parsing the **`snapshot --format ai`** tree (which
retains row/cell text as a UI tree) in `web_reader.py` rather than requesting
`evaluate` be re-enabled for this — a legitimate design tradeoff to flag for the
builder, not a doc-documented recipe.

### 2.5 "Human pace"

**Not a number OpenClaw's docs give.** The closest documented pacing guidance is
about anti-bot risk to Murat's own accounts, not request rate:
`tools/browser-login.md` — "Automated logins often trigger anti-bot defenses and can
lock the account... Use the host browser (manual login)... Sandboxed browser
sessions are more likely to trigger bot detection." Treat the "go slow" instinct the
same way: propose (in §6) a configurable delay (`WEB_READER_MIN_DELAY_S`, default in
the 8–15s range) between page loads rather than citing a doc-mandated figure that
doesn't exist.

---

## 3. OpenClaw as a desktop agent — what exists, and the honest gap

### 3.1 What exists in 2026.9.5

- **Nodes**: paired macOS/Windows/Linux hosts advertising capabilities
  (`computer.act`, `screen.snapshot`, `terminal.upload`, audio/camera, etc.) —
  `nodes/index.md`, `nodes/computer-use.md`, `nodes/file-transfers.md`.
- **Desktop/VNC (Labs, off by default)**: `desktop.host` — an RFB/VNC **view** into
  the Gateway's own desktop (attach to an existing loopback listener, or a
  Gateway-managed TigerVNC/XFCE session on Linux) or a paired node's desktop. This
  is **viewing**, not driving, by itself — driving is the separate `computer` tool
  (`gateway/config-browser-ui-desktop.md`, "Desktop").
- **`computer` tool / `computer.act`**: real mouse/keyboard/screenshot control.
  - macOS: **Peekaboo** (default, in-process CoreGraphics, needs Accessibility +
    Screen Recording + Event Posting) or **CUA** (an app-owned daemon bundled inside
    `OpenClaw.app`; unavailable in dev builds — "driver not bundled").
  - **Windows/Linux: explicitly labeled "experimental, direct SDK"** in the doc's
    own section heading (`nodes/computer-use.md`). Requires
    `openclaw plugins enable cua-computer`, a focused doctor/lint check
    (`openclaw doctor --lint --only cua-computer/driver-artifacts`), and
    `openclaw node run` started **from an interactive desktop session** — it cannot
    drive a locked or headless Windows box.
  - Actions: screenshot, click variants, scroll, type, key, wait. **`hold_key`,
    `left_mouse_down`, `left_mouse_up` are unavailable on the Windows/Linux
    fulfiller** — "the CUA Driver SDK has no desktop-scope held-input contract."
    Modifier-held clicks/scroll/drag are rejected outright, and digit/punctuation
    keys are rejected in the `key` action (layout-dependent shift state isn't
    supported) — send that text through `type` instead.
  - **Stated limitation, verbatim: "This fulfiller currently controls only the
    primary display."**
  - Window/app-level actions (`list_apps`, `get_window_state`, `launch_app`, etc.)
    exist only on providers with the "v2 window/element family" — not guaranteed on
    every fulfiller.
- **Downloads**: `download`/`waitfordownload` are **browser-tool** actions, not
  general desktop file operations — managed Chrome profiles save click-triggered
  downloads into `/tmp/openclaw/downloads` by default, or the configured temp root
  (`cli/browser.md`, "File + dialog helpers"). Separately, a paired node's
  **File Transfer plugin** (`dir_list`/`dir_fetch`/node writes,
  `nodes/file-transfers.md`) and **`terminal.upload`** (drag a file into a node
  terminal, 16 MiB cap) move bytes between the Gateway and a node's filesystem —
  neither is "OpenClaw manages my files the way I would."
- **Cron/automation**: `openclaw automations` (alias **`openclaw cron`**) is a real,
  general-purpose scheduler — persists jobs, wakes an agent-turn/command/script
  payload on a schedule or event trigger, delivers to a channel/webhook/nowhere
  (`automation/cron-jobs.md`, `automation/cron-jobs/{schedules,payloads,delivery}.md`).
  This is genuinely usable to schedule a nightly `dowjones_pull.py` run.

### 3.2 The honest gap

OpenClaw is **not** a "remote-controls-my-whole-PC-like-I'm-sitting-there" tool in
the way a commercial RPA or remote-desktop product is marketed. The evidence is in
the docs' own hedging language, not just an absence of features:

- The Windows/Linux desktop-control path is self-labeled **experimental**, single-
  primary-display only, missing basic input primitives (held keys, modifier
  combos, digit/punctuation via `key`), and requires an already-logged-in
  interactive session to even start.
- Browser automation (§1–2) is a separate, far more mature surface, and it is what
  essentially all of Murat's actual stated want maps to — reading paywalled news
  sites, clicking through pages, downloading text — **not** whole-desktop control.
  For "download WSJ/Barron's/MarketWatch so I can analyze them," the `browser` tool
  (existing-session or extension) is the correct layer; `computer`/desktop control
  is the wrong tool for that job even though it technically exists.
- There is no unified "acts as Murat across every app on the machine" agent; there
  is a mature single-browser-surface tool plus an experimental, narrow, primary-
  display-only input-injection tool for the rest of the desktop.

---

## 4. Connecting Optimus and the APIs

### 4.1 How OpenClaw registers MCP servers

Server definitions live under `mcp.servers` in OpenClaw config
(`tools/mcp.md`, `cli/mcp/registry.md`). Two shapes:

```bash
# stdio (a local process — this is the shape Optimus's mcp__optimus__* server is)
openclaw mcp add optimus \
  --command <same binary/script Claude Code launches Optimus with> \
  --arg <its args> \
  --cwd <its working directory>
openclaw mcp doctor optimus --probe

# HTTP (if a server is ever exposed as streamable-http/SSE instead)
openclaw mcp add docs --url https://mcp.example.com/mcp --transport streamable-http
```

`openclaw mcp doctor <name> --probe` is the verification step — "saving a definition
proves nothing about reachability — the probe does" (`tools/mcp.md`). Tools then
flow through the normal tool-profile/tool-policy machinery
(`tools.profile`, `tools.alsoAllow`, `tools.deny`), and **per-server
`toolFilter.include`/`toolFilter.exclude`** narrows exactly which tool names reach
the agent (`cli/mcp/registry.md`) — this is the mechanism to use for "only the safe
read tools, never the order tools" (§4.3).

**Gap I could not close from these docs alone**: the exact `--command`/`--arg` (or
URL) Optimus's own MCP server is launched with lives in the **Optimus repo's** own
config, not in OpenClaw's docs (per this repo's own "FOUR REPOSITORIES" table in
`CLAUDE.md` — Optimus is a separate repo with its own `CLAUDE.md`). The Opus builder
should read that repo's MCP server definition (whatever Claude Code's own
`mcp_servers` config points at for `optimus`) and reuse the identical invocation.

### 4.2 Aegis's own FastAPI as OpenClaw tools

`/api/pi/*` (`backend/routers/portfolio_intelligence.py`) and `/api/health/full`
(`backend/main.py:879`) are plain REST endpoints today, not MCP tools. Two paths,
in order of simplicity:

1. **`web_fetch` directly** — `tools/browser/setup.md` notes `tools.profile: "coding"`
   already includes `web_search` and `web_fetch`. Loopback/private destinations are
   blocked by the browser/web-fetch SSRF policy unless explicitly allow-listed
   (`gateway/security/browser-control.md`, `gateway/config-browser-ui-desktop.md`
   `ssrfPolicy`), so this needs one config change —
   `tools.web.fetch.ssrfPolicy.allowedHostnames: ["localhost", "127.0.0.1"]` — plus
   giving the agent `web_fetch`. No new code. Good enough for
   `GET /api/health/full` and simple read calls; the agent gets raw JSON back and
   has to parse it itself.
2. **A thin stdio MCP wrapper** (`scripts/openclaw_api_bridge.py`, new) exposing
   typed tools (`aegis_health_full()`, `aegis_pi_lane_positions(lane)`) that
   internally `GET` those same routes. Matches the documented "Local script" recipe
   in `cli/mcp/registry.md` exactly (`openclaw mcp add local-tools --command node
   --arg ./dist/mcp-server.js --cwd ...` — same shape, Python instead of node).
   Cleaner for anything beyond "fetch and read JSON."

### 4.3 Telegram → OpenClaw agent → tools, and why the existing chain must not change

`backend/services/openclaw_client.agent()` **never** passes `--deliver` — "OpenClaw
messages nobody... Whether Murat hears about it is Aegis's decision and
`telegram_bridge`'s job" (`openclaw_client.py:217-224`). `health()` treats a
**nonzero** `messaging_channels` count as a straight failure ("OpenClaw must have NO
chat channel. Aegis owns the messaging," `openclaw_client.py:421-427`, enforced in
`health()`'s `ok` computation). This is a deliberate, already-coded architectural
choice: `OpenClaw -> Aegis -> Telegram`, never `OpenClaw -> human` directly (module
docstring, `openclaw_client.py:52-56`), built as "the structural fix for the WhatsApp
incident."

**Registering Optimus/API tools must not add a Telegram channel on OpenClaw's own
side.** The correct chain, preserving today's architecture:

```
Telegram → Aegis's telegram_bridge (already listens)
        → Aegis code calls OC.agent(prompt) — prompt now allows the model to
          call Optimus/API tools during that one turn
        → OpenClaw replies as text (no --deliver)
        → Aegis relays the reply back via telegram_bridge
```

### 4.4 Security notes

- **Never wrap an order-placing route.** `openclaw_client.DENIED_DOMAINS` already
  refuses brokerage/bank/payment **URLs** at the browser layer
  (`openclaw_client.py:79-84`); the MCP layer needs the same discipline at the
  **tool** level — only wrap Alpaca's read endpoints (`GET /v2/account`,
  `/v2/positions`), never `POST /v2/orders`, and use `toolFilter.include` to name
  only those tools (`cli/mcp/registry.md`).
- **Approval mode**: `openclaw mcp configure <server> --approval prompt` for a first
  rollout (asks the operator every call); reserve `approve` for servers proven
  read-only after review (`cli/mcp/registry.md`, "Codex tool approvals").
- **No key values in prompts or config literals**: `tools/mcp.md` states this
  directly — "Keep credentials out of config literals — store sensitive headers and
  environment values through the supported secret mechanisms" — and `doctor` already
  lints for "literal sensitive header/env values" as a static check
  (`cli/mcp/registry.md`).
- **Read-only Alpaca specifically**: Aegis's existing `pc_broker` module is the one
  place allowed to place paper orders (client_order_id, mandate check, receipt); an
  Optimus/API bridge must only ever proxy reads, never re-implement order placement
  — consistent with `CLAUDE.md`'s "no LLM authority over real capital."
- One item flagged but **unverified**: `nvd.nist.gov/vuln/detail/CVE-2026-33579`
  ("OpenClaw privilege escalation vulnerability") surfaced in a Hacker News search
  (§5) but I could not retrieve its actual detail page content (WebFetch returned
  only the NVD homepage shell). Worth a follow-up look before wiring anything
  privilege-sensitive, but I am not asserting a mechanism I couldn't verify.

---

## 5. Tutorials and community guides — degraded, said plainly

**`WebSearch` was already exhausted (200/200 session budget) before this task began**,
so I could not run the "8–12 tutorial links" search this section asks for. What
follows is what I could verify by fetching specific known URLs directly with
`WebFetch` (a separate budget), plus the primary OpenClaw docs already cited
throughout §1–4. I did **not** fabricate blog-post or Reddit-thread titles to fill
the quota — recommend re-running a real search (e.g. `openclaw browser automation
existing-session tutorial 2026`) once the session's `WebSearch` budget resets.

1. **`tools/browser.md` + its 9 child pages** (local docs, this bundle) — the
   authoritative source for everything in §1–2; not "community" but the
   single most complete reference that exists for this exact question.
2. [Chrome DevTools MCP — GitHub README](https://github.com/ChromeDevTools/chrome-devtools-mcp)
   — the official Google MCP server OpenClaw's `user`/existing-session driver wraps;
   confirms Chrome/Chrome-for-Testing-only official support, navigate/snapshot/
   click/network/performance-trace tools, and that it "exposes browser content to
   MCP clients, allowing inspection and modification of any data" (a real security
   note for the extension/existing-session route generally).
3. [Chrome for Developers — "Use Chrome DevTools MCP with your browser session"](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session)
   — the authoritative walkthrough for `chrome://inspect/#remote-debugging`, the
   Chrome M144 requirement, `--channel=beta` before M144 is stable, and the consent
   dialog / "controlled by automated test software" banner. This is the doc behind
   §1.2 steps 1–3.
4. Hacker News, via Algolia's public search API (`hn.algolia.com/api/v1/search?query=openclaw`)
   — surfaced several **provider-access/ToS controversy** threads (Anthropic and
   Google restricting subscription use of OpenClaw, April/February 2026) and the
   CVE noted in §4.4. These are **not** browser-automation tutorials — flagging them
   only as community/security signal, and flagging the obvious risk that "OpenClaw"
   is a generic enough name that an unfiltered search can surface unrelated
   products; confirm any external hit is about the AI-agent tool at `docs.openclaw.ai`,
   version 2026.x, before trusting it.
5. `www.reddit.com` — blocked outright for this session's `WebFetch` ("Claude Code
   is unable to fetch from www.reddit.com"), so no Reddit coverage at all this pass.

**What's missing and should be re-run**: YouTube walkthroughs, dev.to/Medium posts,
and Reddit threads specifically on the extension-relay pairing flow and
existing-session troubleshooting on Windows — none of that could be retrieved this
session.

---

## 6. Chunk spec for the Opus builder

### (a) `backend/services/openclaw_client.py` — allow `user`/`chrome` by explicit name

- Move the profile default and allow-list into `backend/config.py` (house rule:
  "Put all parameters in `backend/config.py` — never hardcode in service files").
  New config: `AEGIS_OPENCLAW_PROFILE_DEFAULT = "muratclaw"`,
  `AEGIS_OPENCLAW_ALLOWED_PROFILES = ("muratclaw", "user", "chrome")`.
- Change signatures to accept an explicit profile, falling back to today's
  env/config default — never silently substitute one profile for another:
  - `profile(name: str | None = None) -> str`
  - `assert_profile(strict: bool = True, *, name: str | None = None) -> dict`
  - `browser(verb, *args, url=None, timeout=180.0, profile_name: str | None = None) -> dict`
  - Validate the resolved name against `AEGIS_OPENCLAW_ALLOWED_PROFILES`; an
    unlisted name refuses with a new `REFUSED_BROWSER_PROFILE_NOT_ALLOWED`,
    distinct from today's `REFUSED_BROWSER_PROFILE_UNAVAILABLE` (profile listed but
    not actually present in `openclaw browser profiles`).
- Add `attached_to(*, profile_name: str | None = None) -> dict`: shells
  `openclaw browser --browser-profile <name> status --json`, parses `driver`,
  `transport`, `running` (and, for existing-session, whatever browser-identity
  fields Chrome MCP reports) so a caller/receipt can print "which browser process it
  attached to" (this task's explicit ask).
- Keep every existing invariant: no silent fallback ever, `DENIED_DOMAINS`/
  `check_url` unchanged, `evaluate` still absent from `ALLOWED_VERBS`.
- Tests (`backend/tests/services/test_openclaw_client.py`, new or extended): mock
  `subprocess.run` with canned `openclaw browser profiles` / `status --json` text
  (reuse the existing ANSI-stripping fixture pattern already implied by `_strip`);
  assert (1) an explicit `profile_name="user"` is honored and never substitutes
  `muratclaw`; (2) an unlisted name refuses with the new error; (3) `attached_to()`
  surfaces `driver`/`transport` from a canned JSON blob.

### (b) `backend/services/web_reader.py` — new, deterministic reader

- **Verb route only** — calls `openclaw_client.browser()` directly, never
  `openclaw_client.agent()`. No LLM turn, $0.
- `read_page(url, *, profile, wait_for=None, consent_query="accept cookies consent",
  selector=None, max_chars=40000, sleep_fn=time.sleep) -> dict` implementing the
  §2.3–2.4 sequence (navigate → wait → snapshot(ai, urls) → click-if-consent-ref →
  text → optional screenshot); returns
  `{"url", "final_url", "text", "links": [...], "first_seen_utc", "status"}`.
- `read_archive(list_url, *, profile, per_item_delay_s, ...) -> list[dict]`: one
  listing-page snapshot with `--urls`, then `read_page` per discovered link,
  sleeping `per_item_delay_s` between calls via an injectable `sleep_fn` (never a
  bare `time.sleep` the tests can't mock — "OFFLINE + un-hangable" fast-suite rule).
- New config knob (not hardcoded): `WEB_READER_MIN_DELAY_S` (default in the 8–15s
  range per §2.5's honest "no doc-mandated number" caveat).
- `first_seen_utc` always stamped at read time, never derived from any page-supplied
  date (house rule: "date a receipt by its own stamp").
- Storage: one JSONL row per article under
  `backend/data/optimus/news_corpus/dowjones/<date>.jsonl` — matches the existing
  `news_corpus/<source>/<date>.jsonl` convention already read by
  `scripts/thesis_cards.py::_load_news`. Full article text goes to a companion file
  under `backend/data/optimus/news_corpus/dowjones/text/<hash>.txt`, each file
  carrying a licence header: property of Murat's own Dow Jones subscription,
  fetched under his personal login, never republished.
- Reuse `openclaw_client.check_url` — this new caller must still respect
  `DENIED_DOMAINS`.
- Tests (`backend/tests/services/test_web_reader.py`): monkeypatch
  `openclaw_client.browser` to return canned `open`/`snapshot`/`text` dicts (JSON
  fixtures under `backend/tests/fixtures/web_reader/`, recorded once from a real
  run); assert text/link extraction, `max_chars` truncation, `first_seen_utc`
  stamping, and that `read_archive` calls `sleep_fn` between items — zero real
  sleeps, zero subprocess calls, in the fast suite.

### (c) `scripts/dowjones_pull.py` — new CLI

- `python -m scripts.dowjones_pull --archive YYYY-MM-DD --source wsj|barrons|marketwatch
  [--profile user|chrome] [--max-articles N] [--dry-run]`.
- WSJ has a real dated archive URL; Barron's picks and MarketWatch analyst-estimates
  don't take a date param the same way — document that `--archive` is
  advisory/logging-only for those two sources rather than silently ignoring it.
- Refuse cleanly (never silently clamp) if `--archive` is in the future, derived
  from `today`, per house rule 5 (no literal-date fixtures, no requesting a date
  that hasn't happened).
- Calls `web_reader.read_archive`, writes via (b)'s storage convention, prints a
  receipt: `{"receipt": "dowjones_pull", "source", "archive_date", "n_found",
  "n_read", "n_refused", "cost_usd": 0.0, "profile_used", "attached_to":
  openclaw_client.attached_to()}` — `cost_usd: 0.0` labeled explicitly since this is
  the deterministic reader, not an `agent()` call.
- `main()` returns nonzero on any `REFUSED_*`, mirroring `scripts/thesis_cards.py`'s
  own convention.

### (d) Optimus/API tool registration

- OpenClaw-side config only (`mcp.servers` in OpenClaw's own config, not Aegis code)
  — see §4.1 for the exact `openclaw mcp add` shape, and flag the Optimus launch-
  command lookup as the one open question for the builder (§4.1's "gap").
- One new Aegis-side script if the bridge path is chosen: `scripts/openclaw_api_bridge.py`
  — minimal stdio MCP server, exactly two read-only tools (`aegis_health_full`,
  `aegis_pi_lane_positions`), GET-only, never a broker/order route. Confirm the real
  `/api/pi/*` read paths in `backend/routers/portfolio_intelligence.py` before
  implementing (only `/api/health/full` and the module's existence were confirmed
  this session, not every route name).
- Register with `--approval prompt` initially and `toolFilter.include` naming only
  those two tool names (§4.4).

### (e) Tests without a browser

- (a) and (b)'s tests above, plus `backend/tests/services/test_dowjones_pull.py`:
  monkeypatch `web_reader.read_archive` entirely (never touches
  `openclaw_client.browser`), asserts the future-date refusal, the receipt shape,
  and the nonzero exit path — fixture-driven, zero network, zero subprocess, per
  `backend/tests/conftest.py`'s network block and `pytest.ini`'s per-test timeout.
- Register every new module (`web_reader.py`, `openclaw_api_bridge.py`) in
  `backend/services/signal_reachability.py`'s classification — house rule: "Give
  every new module a caller, or classify it... the suite fails on an unreachable,
  unclassified module."

---

## Files read this session (for the record)

- `backend/services/openclaw_client.py` (full)
- `scripts/source_reads.py` (full)
- `scripts/thesis_cards.py` (full)
- `backend/routers/portfolio_intelligence.py`, `backend/main.py` (grep only, for
  `/api/pi/*` and `/api/health/full`)
- `backend/config.py` (grep only, for `THESIS_CARD_*` / OpenClaw-related keys)
- OpenClaw docs bundle, `tools/browser*.md` (9 pages), `tools/chrome-extension.md`,
  `cli/browser.md`, `cli/mcp.md` + `cli/mcp/registry.md`, `tools/mcp.md`,
  `tools/skills.md`, `nodes/computer-use.md`, `nodes/file-transfers.md`,
  `gateway/config-browser-ui-desktop.md`, `gateway/security/browser-control.md`,
  `tools/browser-login.md`, `automation/cron-jobs.md` (index)
