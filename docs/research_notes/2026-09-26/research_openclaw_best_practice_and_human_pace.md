# OpenClaw at human pace: what flags a session, what Aegis already does right, and what to fix

Research note, 2026-09-26. Budget: $0.50 via OpenClaw agent calls (spent: **$0.00** —
this note needed no `openclaw agent` turn) + unlimited browser verbs (spent: **0** —
WebFetch to public docs/repos covered everything; the OpenClaw browser was never
opened). No `muratclaw` session was touched.

## Scope boundary (per the assignment)

This note is about **human-pace, well-behaved automation inside a real signed-in
session** — randomised dwell times, one tab, reading only what a person would read,
daily caps, staying in the `muratclaw` managed profile or Murat's own attached
Chrome. It explicitly does **not** cover, and does not recommend, fingerprint
spoofing (patched `navigator.webdriver`, mocked `chrome.runtime`/plugins/WebGL
vendor), CAPTCHA solving, residential proxy rotation, or CDP-detection evasion
(e.g. Camoufox skipping CDP entirely). Those techniques are cited below only to
show what they look like, so Aegis's own code and prompts can be checked against
none of it ever appearing.

---

## 1. What gets sessions flagged, and the legitimate counter-practice

| Signal defenses use | Source | Aegis's legitimate counter-practice |
|---|---|---|
| **Headless/automation flags**: `navigator.webdriver`, injected CDP markers (`Runtime.enable` fires a detectable trace), `toString()` on patched functions no longer returning `"[native code]"` | Camoufox author's writeup on why OpenClaw browser sessions kept getting CAPTCHA'd — CDP itself, not just headless mode, leaves traces ([bennhuang.com](https://bennhuang.com/posts/why-your-openclaws-browser-keeps-getting-captchas/)) | Don't patch anything. Attach to a **real, already-signed-in Chrome** (`muratclaw` managed profile, or Murat's own Chrome via `profile="user"`/existing-session) instead of a bare freshly-launched automation profile. Chrome DevTools MCP's own docs give the same reason from the tooling side: sites "block WebDriver-controlled browsers," so its advanced-usage guide recommends **attaching to an already-running Chrome** over launching a fresh one when login state matters ([chrome-devtools-mcp advanced-usage.md](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/advanced-usage.md)). This is exactly `backend/services/openclaw_client.py`'s three-profile design already (`muratclaw` / `user` / `chrome`). |
| **Headless vs headful rendering differences** (used to still matter for GPU/canvas fingerprints) | Since Chrome 112, headless and headful share one code path — "creates, but doesn't display, any platform windows... all other functions... available with no limitations" ([developer.chrome.com/docs/chromium/headless](https://developer.chrome.com/docs/chromium/headless)) | Less load-bearing than it used to be, but `openclaw browser start --headless` should still be avoided for any read that matters — run headful on the managed profile so the graphics/canvas fingerprint matches a real desktop, which `openclaw browser status`/`doctor` already reports (hardware/software renderer classification). |
| **Request rate and burstiness / identical inter-action timing** | Cloudflare's bot-management writeup: detection scores on "more than 250 request attributes from different protocol levels," categorical and numerical features over **inter-request timing**, not single requests ([blog.cloudflare.com](https://blog.cloudflare.com/cloudflare-bot-management-machine-learning-and-more/)) | `backend/services/web_reader.py`'s `Throttle` already enforces this shape: `WEB_READER_MIN_DELAY_S=20.0` floor between page loads, `WEB_READER_MAX_PER_HOUR=30`, `WEB_READER_MAX_PER_DAY=120`, persisted to a file so **two separate processes can't add up to a burst**. Gap: the floor is a fixed minimum, not a randomised range — every wait is either 0 or exactly `20.0 - gap`, which is itself a suspiciously regular pattern once a distribution is measured (see §4). |
| **Missing mouse/scroll telemetry, or scroll telemetry that never happens** | Behavioral-analysis is one of Cloudflare's five listed detection mechanisms alongside ML scoring, heuristics, verified-bots, and JS/canvas fingerprinting (same Cloudflare source) | `Reader.navigate`/`read_article` in `web_reader.py` do a fixed `wait --time 3500ms` after navigate/click and then read `innerText` directly — **no scroll ever happens** on the deterministic verb route. A person opening a WSJ article scrolls through it. This is the clearest actionable gap (spec in §5). |
| **Fetching assets/APIs directly instead of rendering pages like a person** | Same Cloudflare source (protocol-level attributes); also why `web_reader.py`'s own docstring quotes the Dow Jones ToU banning "automated means... browser automation tool[s]... without prior written consent" | Aegis already does the *opposite* of the bad pattern here on purpose — it renders full pages with a real browser rather than calling undocumented JSON endpoints, and treats that as the licence-compliant path (personal reading, not text/data mining) rather than a stealth technique. |
| **Parallel tabs / concurrent sessions on the same site** | Implicit in Cloudflare's per-session behavioral model; explicit in OpenClaw's own skill guidance ("Tab Hygiene": reuse one labeled tab per task) ([`browser-automation/SKILL.md`](file://C:/Users/mrthn/AppData/Roaming/npm/node_modules/openclaw/dist/extensions/browser/skills/browser-automation/SKILL.md)) | `Reader` is a `@dataclass` keyed on `(profile, tab)` — one reading session, one tab. `open_from_tab` (`openclaw_client.py`) opens exactly one new tab per call and records it in `_OPENED_TABS`, closing only tabs the process itself opened. No parallel-tab pattern exists in the current code. |
| **Time-of-day pattern** (reading only during a bot's schedule, e.g. exactly on the hour, or 24/7 with no human sleep gap) | Not directly documented in the sources above, but is the natural extension of Cloudflare's "inter-request data" behavioral scoring | Not currently modeled anywhere in `web_reader.py` or `source_reads.py`. Gap: no time-of-day gate exists; the throttle caps *volume* but not *when*. Spec in §5. |
| **Canvas / WebGL / hardware fingerprint mismatch** | Cloudflare's JS fingerprinting mechanism cross-checks "request's user agent... against other telemetry gathered through browser canvas API" (same Cloudflare source); `puppeteer-extra-plugin-stealth` patches exactly this (`webgl.vendor` "otherwise set to 'Google' in headless") — cited here **only as the out-of-scope look-alike** ([puppeteer-extra-plugin-stealth](https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth)) | Aegis never touches this layer at all — no `evaluate`, no canvas/WebGL overrides. `ALLOWED_VERBS` in `openclaw_client.py` deliberately excludes `evaluate` for a different reason (prompt-injection surface), which has the side effect of making fingerprint spoofing structurally impossible from this codebase. Worth stating explicitly as a feature, not just a security control. |

### CDP attach and the automation banner — what `--autoConnect` actually changes

The Chrome DevTools MCP docs (the closest documented analogue to OpenClaw's own
CDP-attach path) are explicit: `--autoConnect` (Chrome 144+) requires the
*user* to enable remote debugging via `chrome://inspect/#remote-debugging` in
their **own already-running Chrome, from its real user-data directory**, and
then the MCP server attaches to that live instance rather than launching a new
one ([configuration.md](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/configuration.md),
[advanced-usage.md](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/advanced-usage.md)).
Their docs do not claim this suppresses `navigator.webdriver` or the "controlled
by automated test software" info-bar — those are set by the CDP `Runtime.enable`
/ automation-flag handshake regardless of *which* Chrome you attach to — but they
do give the actual reason attach-to-existing beats launch-fresh: **the existing
session already carries real login state and a real browsing history**, which a
freshly spawned automation profile can never have on day one. That is the
argument for `muratclaw` (never signed into anything OpenClaw shouldn't touch,
but a persistent profile with its own history) over a throwaway profile, and for
`user`/existing-session (Murat's actual profile) when the site specifically
blocks WebDriver-controlled sessions — exactly the two-tier design already in
`openclaw_client.py`'s `allowed_profiles()` / `operator_profiles()`.

---

## 2. OpenClaw usage patterns, from the bundled docs

Read from `C:\Users\mrthn\AppData\Roaming\npm\node_modules\openclaw\docs\` and
`dist\extensions\browser\skills\browser-automation\SKILL.md`.

- **`browser-automation` skill** (`skills/browser-automation/SKILL.md`): the
  canonical operating loop is *check state → prefer stable tab handles
  (`suggestedTargetId`, not raw `targetId`) → snapshot before clicking → act
  narrowly with a ref from the latest snapshot → report real blockers instead
  of looping on stale refs*. It explicitly says: for "read the page and answer
  X," use `action="text"` (or `snapshot` on existing-session profiles, since
  "efficient snapshots omit most prose"); for virtualized/infinite lists,
  *scroll through each segment, capture only the relevant rows, then merge* —
  this is the documented pattern for the X-timeline read Aegis already runs.
- **`wait` conditions**: `--url "**/dash"` (glob), `--load networkidle`
  (managed/raw-CDP profiles only — **existing-session profiles including
  `user` reject `networkidle`**, so `muratclaw`'s waits must use `--text`, a
  selector, or `--fn`), `--fn "window.ready===true"`, or a selector-visible
  wait; all combinable (`browser-control.md` "Wait power-ups").
- **`snapshot --format ai` vs `--format aria`**: `ai` (the default) gives refs
  like `f1e12` resolved through Playwright's `aria-ref` — this is what
  `web_reader.py`'s `parse_snapshot`/`select_links` parse. `--format aria`
  gives `axN` refs from the raw accessibility tree; useful for inspection but
  **not always actionable** — re-snapshot with `--format ai` before clicking.
  `--interactive`/`--compact` gives role refs (`e12`) via `getByRole`. Refs are
  **never stable across navigation**; a batch stops at the first committed
  main-frame navigation.
- **`evaluate --fn`**: accepts a function, expression, or statement body
  (statement bodies auto-wrapped as async, need `return`). This is the single
  most dangerous verb by OpenClaw's own security notes — "Prompt injection can
  steer this" (`browser-control.md` "Security and privacy") — which is exactly
  why `openclaw_client.py` keeps it out of `ALLOWED_VERBS` and instead exposes
  one fixed, module-constant function (`READ_TEXT_FN`) through `read_text()`.
- **`screenshot`**: `--full-page`, `--ref`, `--labels` (overlays refs +
  `annotations[]` bounding boxes on Playwright-backed profiles; existing-session
  profiles render an overlay but no `annotations`). Good for verifying a click
  landed where intended, cheap, doesn't touch the page's JS at all — a candidate
  for a lightweight "did the read actually land on the article, not a paywall
  modal" check.
- **`cookies` / `storage`**: `cookies`, `cookies set/clear`, `storage
  local|session get/set/clear` — state/emulation knobs; not currently used by
  Aegis and not needed for read-only human-pace reading.
- **`requests` / `responsebody`**: network-log debugging, **managed profile or
  raw CDP only** — "Use a managed profile; existing-session profiles do not
  support this log" (`browser-automation/SKILL.md` §5). Same restriction on
  `errors`.
- **`pdf` / `download`**: **also managed-browser-or-raw-CDP only** —
  `browser.md`: "`responsebody`, download interception, PDF export, and batch
  actions still require a managed browser or raw CDP profile." Managed Chrome
  profiles save click-triggered downloads to `/tmp/openclaw/downloads`;
  `waitfordownload`/`download <ref> <path>` are the explicit waiters.
- **`trace start`/`trace stop --out trace.zip`**: Playwright trace capture for
  deep debugging of a failing action sequence — not something a routine read
  needs, but useful once if a site's flow keeps failing in a way that isn't a
  blocker OpenClaw can name.
- **The agent route (`openclaw agent` / `openclaw_client.agent()`)**: a full
  Gateway-backed agent turn where **the LLM itself drives the browser tool**
  from natural-language instructions, as opposed to the verb route where Aegis
  code drives every `browser()` call directly. `--expect-final` (documented at
  the shared Gateway-RPC layer, `cli/gateway/query.md`, and listed as a common
  browser-CLI flag) waits for the agent's final reply instead of an interim
  Gateway ack — `openclaw_client.agent()` doesn't pass it explicitly but gets
  the same effect by blocking on the subprocess. Model: `source_reads.py`
  defaults to `SOURCE_READS_MODEL = "deepseek/deepseek-flash"`; cost is priced
  from `LLM_PRICE_PER_MTOK["deepseek-flash"]` against the returned usage, with
  `openclaw_client.agent()`'s own docstring noting a measured first call at
  **30,262 input + 6,784 cached + 2,034 output tokens for a 2.7k-char prompt**
  — i.e. ~90% of every agent-route call is the agent's own system prompt and
  tool schemas, not the task. That fixed overhead is the real argument for
  keeping the **verb route** (`web_reader.py`) as the default for anything
  that can be scripted deterministically, and reserving the **agent route**
  (`source_reads.py`) for tasks that genuinely need judgment (which posts are
  about which ticker) rather than mechanical navigation.
- **Skills / writing a custom skill**: `openclaw skills workshop
  propose-create --name ... --proposal ./PROPOSAL.md` → `list` → `inspect` →
  `apply`/`reject`/`quarantine` (`cli/skills.md`). A repeated Aegis quest (e.g.
  "read a WSJ markets-column listing page") is exactly the shape of a
  workshop-proposable skill, but Aegis's own `web_reader.py` docstring already
  argues for the opposite where determinism matters: a fixed Python function
  beats a skill-guided LLM loop for anything that must never "use wrong links"
  (Murat's own complaint that produced `read_listing`'s snapshot-then-select
  design).
- **Cron/automation** (`openclaw automations` aka `openclaw cron`): schedule +
  `pacing.min`/`pacing.max` duration bounds per job (`--pacing-min`/
  `--pacing-max`), one-shot retry on transient errors, permanent-error jobs
  disabled immediately. Not currently wired to any web-reading job; Aegis's
  own `night_run_until.py`/`u_funnel`-style callers are the scheduling layer
  instead. `pacing.min`/`pacing.max` is worth reusing conceptually for any
  future OpenClaw-cron-driven read job, since it's the same shape as
  `Throttle` but expressed at the job-scheduling layer rather than inside the
  page-load loop.
- **Nodes** (`openclaw nodes` / the browser **node host proxy**): when the
  Gateway runs on a different machine than Chrome, a **node host** on the
  Chrome machine lets the Gateway proxy browser actions to it — relevant only
  if Aegis's OpenClaw Gateway ever moves off the machine that owns `muratclaw`;
  not applicable to the current single-machine setup.
- **Control UI**: the browser dashboard's MCP settings page
  (`/settings/mcp`) is for editing MCP server config, separate from the
  browser-profile management which stays CLI-only (`openclaw browser
  profiles`). No Control UI surface currently duplicates anything
  `openclaw_client.py`/`web_reader.py` do.
- **`openclaw doctor`**: health checks across gateway/channels/plugins/skills/
  model routing; `openclaw browser doctor` (and `doctor --deep`, which adds a
  live snapshot probe) is the pre-flight `health()` in `openclaw_client.py`
  should arguably call before every session rather than only checking gateway
  status + profile pinning — `doctor --deep`'s snapshot probe would catch a
  profile that's "pinned" but stuck on a blank tab, which the current
  `health()` cannot see.

### Checklist: verb sequence per task shape

| Task | Verb sequence |
|---|---|
| **Listing page → N articles** | `navigate` listing URL → `wait --time <jittered ms>` → `snapshot --format ai --urls` → select links from **that snapshot only** (never compose a URL) → per article: `click <ref>` (or `navigate` if not clickable) → `wait` for load → **scroll through 2-4 times with a jittered pause** → `read_text` (fixed `innerText` fn) → back to listing only if more articles needed, respecting the throttle between every page load. This is `web_reader.Reader.read_listing`/`read_article`, missing only the scroll step (§5). |
| **Quote/ratings page** | `navigate` → `wait --load networkidle` (managed profile) or `wait --text "<known label>"` (existing-session) → `snapshot --format ai` (structured numbers are usually in the AI snapshot's node text, no need for `--interactive`) → read directly, no click needed. One page, no scroll needed unless the ratings table is virtualized. |
| **Search-results page** | `navigate` search URL → `wait` → `snapshot --format ai --urls` → **do not click blind**; select only results whose link text and URL both match the query terms (mirrors `select_links`'s dual `link_pattern`/`text_pattern` filter) → proceed per-result like a listing page. |
| **Infinite-scroll timeline (X handle)** | `navigate` profile/search URL → `wait --time <jittered>` → `snapshot --format ai --urls` (baseline; later snapshots on the same tab flag `[new]` ref-bearing lines, so a second snapshot after scrolling tells you exactly what's new without re-reading the whole page) → **scroll → jittered pause → snapshot** repeated 2-3 times (the "scroll through each segment, capture only the relevant rows, merge" pattern the skill doc names for virtualized lists) → stop once no `[new]` lines appear or the post count/window is satisfied. This is what `source_reads.py`'s `timeline_prompt`/`read_prompt` already ask the agent to do in natural language ("scroll the timeline two or three times... skip reposts") — the gap is that nothing in the prompt asks for a *paced* scroll, so the agent-driven route has no floor on how fast it does it (§5). |
| **PDF download** | Managed profile or raw CDP only (existing-session cannot). `click <ref>` on the download link (or `navigate` if it's a direct PDF URL and the site streams it) → `waitfordownload` or `download <ref> <path>` to get the saved file path → verify with a byte-size/`file` check before trusting it, since a paywall-redirect can save an HTML error page with a `.pdf` extension. |

---

## 3. Community guides and repos (2025-26)

One line each; **flagged** entries are exactly the fingerprint-spoofing/CDP-evasion/anti-bot-defeat category this note is scoped away from.

1. [OpenClaw main repo](https://github.com/openclaw/openclaw) — the project itself; the bundled `browser-automation` skill and `openclaw browser` CLI are the primary source for §2 above.
2. [bennhuang.com — "Why Your OpenClaw's Browser Keeps Getting CAPTCHAs"](https://bennhuang.com/posts/why-your-openclaws-browser-keeps-getting-captchas/) — diagnoses CDP `Runtime.enable` traces and hardware-fingerprint mismatches as the cause; **flagged**: the fix it lands on is Camoufox, a Firefox fork that "skips CDP and patches fingerprint values down in the C++ layer" — exactly the evasion category out of scope here.
3. [Unayung/openclaw-browser-relay](https://github.com/Unayung/openclaw-browser-relay) — a hardened fork of OpenClaw's Chrome extension relay adding auto-reconnect/state persistence/keepalive across WebSocket drops and MV3 service-worker restarts; legitimate reliability work on the same existing-session-attach path Aegis already uses.
4. [pinchtab/pinchtab](https://github.com/pinchtab/pinchtab) — a small Go binary offering an alternative browser-control surface for OpenClaw agents; evaluate only for reliability/footprint, not fetched in depth for this note.
5. [lekt9/unbrowse-openclaw](https://github.com/lekt9/unbrowse-openclaw) — **flagged (adjacent, not evasion, but a different licence risk)**: bypasses browser automation entirely by calling a site's internal APIs directly, which is closer to unauthorized API scraping than "reading a page like a person" and would need its own ToU review before Aegis touched it.
6. [zzzgydi/verge-browser](https://github.com/zzzgydi/verge-browser) — a self-hosted isolated browser sandbox pitched for AI agents; an isolation/ops tool, not a detection-evasion one.
7. `openbrowserclaw.com` / `rentmybrowser.dev` — **flagged**: both surfaced in the same search as marketplace-style "run agents through someone else's browser" services; renting or routing through a browser you don't control (and whose ToU-standing with the target site you can't verify) is out of scope for the same reason residential-proxy rotation is.
8. [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) — not OpenClaw, but the closest documented analogue for CDP-attach semantics; its `--autoConnect`/`--browserUrl`/`--isolated` design is the direct precedent for OpenClaw's `muratclaw` vs `user` vs fresh-profile split (§1).
9. [berstend/puppeteer-extra-plugin-stealth](https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth) — **flagged, cited only as the definitive "what fingerprint spoofing looks like" reference**: patches `navigator.webdriver`, `chrome.runtime`, plugins/mimetypes, WebGL vendor, media codecs, iframe `contentWindow`, window outer dimensions. Nothing in Aegis's OpenClaw client does any of this, and `evaluate` being outside `ALLOWED_VERBS` makes it structurally impossible from this codebase.
10. Browserbase / Notte (from OpenClaw's own bundled remote-CDP docs, `tools/browser/remote.md`) — **flagged**: both are OpenClaw-supported CDP providers whose own marketing is "built-in CAPTCHA solving, stealth mode, residential proxies" — exactly the category this note excludes, even though OpenClaw documents connecting to them as an ordinary CDP profile.
11. Firecrawl's `web_fetch` fallback (`tools/firecrawl.md`) — **flagged for its `proxy: "stealth"`/`"auto"` mode**, which retries scrape/fetch requests through stealth proxies; noted only because it's bundled alongside OpenClaw's own tool docs and could be reached for by someone solving the same "site refuses us" problem the wrong way.

---

## 4. A test plan for measuring Aegis's own footprint

**Data source**: `web_reader.Reader.log` (per-page `{page, what, url, waited_s,
at}` rows, already collected in-memory per session) plus `Throttle`'s persisted
`_throttle.log` (one ISO timestamp per page load, shared across processes) and,
once added, `store_article()`'s per-article `read_s` field.

1. **Inter-request interval distribution.** From `_throttle.log`, compute the
   gap between consecutive timestamps for a session/day. Plot/tabulate the
   histogram. **Current expectation given the code as written**: because
   `Throttle.acquire` waits exactly `max(0, min_delay_s - gap)`, the *realized*
   gap distribution should cluster very close to a hard floor at
   `WEB_READER_MIN_DELAY_S` (20.0s) whenever reads happen back-to-back, with a
   long right tail whenever the LLM/agent step between pages takes longer than
   20s anyway. A histogram that shows a **spike exactly at 20.0s** (rather than
   a spread) is itself a signature worth alarming on — see item 4 below.
2. **Pages/hour and pages/day.** Count rows in `_throttle.log` per rolling hour
   and per rolling day; compare against `WEB_READER_MAX_PER_HOUR` (30) and
   `WEB_READER_MAX_PER_DAY` (120). These are ceilings, not targets — report the
   *actual* rate achieved on real runs, which is almost certainly far below the
   cap (Dow Jones reading only happens when Murat hands the PC over via
   `DOWJONES_HANDOFF_FILE`).
3. **Human baseline.** Ask Murat to read N articles at his own pace with the
   session's start/end timestamps noted (or instrument his manual `openclaw
   browser open` + normal Chrome reading with the same `_throttle.log` format
   for one sitting). Compare his inter-article gap distribution and pages/hour
   against Aegis's. The claim to test is *"Aegis's distribution looks like a
   plausible tail of Murat's distribution,"* not merely "under the cap."
4. **Alarm: distribution collapse to a constant.** Add a check —
   `web_reader.footprint_receipt()` (see §5) — that computes the
   coefficient of variation (stdev/mean) of inter-request gaps over the last
   N reads. A CoV near 0 (i.e., every gap is within a few hundred ms of the
   same value) means the pacing has degenerated into "wait exactly T then go,"
   which is precisely the "identical inter-action timing" signal named in §1.
   Refuse (or at minimum flag `DEGRADED`) a session whose last 20+ gaps have
   CoV below a threshold (e.g. 0.15), the same way `Throttle.acquire` already
   refuses on cap breach.
5. **Cross-check against `Throttle.waits`.** `Throttle` already records
   `self.waits` (seconds waited, not seconds elapsed) per call within a
   process. Comparing `waits` (intentional pause) against the *observed* gap
   in `_throttle.log` (actual elapsed time including whatever OpenClaw/agent
   work happened in between) tells you how much of the pacing is "structural"
   throttle vs. incidental work time — useful for tuning the jitter range in
   §5 without over- or under-shooting the real human baseline from item 3.

---

## 5. Spec lines for the builder

### `backend/services/web_reader.py`

1. **Jittered pacing, not a hard floor.** `Throttle.acquire` currently waits
   `max(0, min_delay_s - gap)` — a floor, deterministic given the gap. Add a
   randomised range: `WEB_READER_MIN_DELAY_S` becomes the low end of a
   `[low, high]` jitter window (new config `WEB_READER_MAX_DELAY_S`, e.g.
   `90.0`, matching the assignment's "randomised 20-90s reads"), drawn via
   `np.random.default_rng` per house convention (never `np.random.seed`), and
   the *realized* wait is `max(0, rng.uniform(low, high) - gap)` rather than a
   fixed `min_delay_s - gap`. Persist the drawn value alongside the timestamp
   in `_throttle.log` (or a parallel field) so §4's CoV check has ground truth
   to compare against.
2. **Scroll-through before reading.** `Reader.read_article` currently does
   `navigate`/`click` → one fixed `wait --time 3500ms` → `read_text`. Add 2-4
   `browser("evaluate"...)`-free scroll steps — since `evaluate` stays banned,
   use the already-allowed `scrollintoview` verb against a ref near the end of
   the snapshot's link/text nodes, or (simpler, and matching what the
   `browser-automation` skill calls "wait for visible UI state") a sequence of
   `wait --time <jittered 800-2500ms>` calls interspersed with `press
   "PageDown"` (already in `ALLOWED_VERBS` via `press`) — a person scrolls a
   long article in several bursts, not one instant jump. Cap total scroll time
   so a single article read still fits inside the per-page throttle budget.
3. **One tab, enforced, not just conventional.** `Reader` is already
   single-tab by construction (one `tab` field), but nothing refuses a second
   `Reader` instance being constructed against the same `(profile, tab)` or a
   different tab concurrently. Add a module-level lock file (same pattern as
   `_throttle.log`) that a second `Reader.__post_init__` on the same profile
   refuses to acquire — "one reading session, one tab" becomes enforced, not
   merely how the dataclass happens to be used today.
4. **Per-site daily caps, not just a global one.** `WEB_READER_MAX_PER_DAY`
   (120) is global across `hosts()` (wsj/barrons/marketwatch combined). Add
   `WEB_READER_MAX_PER_DAY_PER_HOST` (e.g. 40) and have `Throttle.acquire`
   accept the target host and check both the global and per-host rolling-24h
   count from `_throttle.log` (which would need to start recording the URL's
   host, not just a bare timestamp — a small, backward-compatible line-format
   change: `"<iso> <host>"`, falling back to "no host" for pre-existing lines).
5. **A `footprint_receipt()` function.** Mirrors the repo's `X_receipt()`
   convention (`store_article`'s `NR.effective_pit_grade`,
   `source_reads.py`'s `_write_receipt`). Reads `_throttle.log`, computes:
   pages/hour, pages/day (global and per-host), the inter-request gap
   histogram/CoV from §4 item 4, and the fraction of reads that included a
   scroll step (once item 2 lands). Verdict field `"HUMAN_PACE_OK"` /
   `"DEGRADED: <reason>"` (never a bare boolean — per house rule, a check that
   cannot go red is a broken check). Called once per `Reader` session on
   teardown and written next to the existing corpus root
   (`corpus_root().parent / "footprint" / "<date>.json"`).

### `scripts/source_reads.py`

The agent route here is fundamentally different from `web_reader.py`: **the
LLM itself drives the browser tool** from a natural-language prompt (see §2),
so there is no `Throttle` object to extend — the pacing has to be an
instruction *in the prompt text*, not code Aegis runs directly.

6. **Add an explicit pacing instruction to `discovery_prompt`, `read_prompt`,
   and `timeline_prompt`.** All three currently say only "scroll once or
   twice" / "scroll the timeline two or three times" with no timing
   instruction at all — the agent is free to snapshot-scroll-snapshot as fast
   as the model can emit tool calls. Add a line such as: *"Pause a few seconds
   between scrolls and between opening successive pages — read at the pace a
   person would, not as fast as the tool allows."* This can't be *enforced*
   the way `Throttle` enforces `web_reader.py` (the agent route has no
   verb-level hook Aegis controls), so it is a **soft** control; log it as
   such in the receipt (`quests[-1]["pacing_instructed"] = True`) rather than
   claiming it as a guarantee.
7. **Snapshot→scroll→snapshot instead of "read the results" as one step.**
   `timeline_prompt` already does the right shape (navigate → scroll 2-3
   times → read); `discovery_prompt` and `read_prompt` say "read the results
   (scroll once or twice)" as a single clause, which under-specifies the
   sequence the `browser-automation` skill documents for virtualized lists
   ("scroll through each segment, capture only the relevant rows, then
   merge"). Rewrite both to the explicit sequence: navigate → snapshot →
   scroll → snapshot (compare `[new]`-flagged lines) → repeat until no new
   ref-bearing lines appear or the post cap is hit → then extract.
8. **A footprint field in the receipt, matching `web_reader.py`'s.** `_write_receipt`
   already writes `elapsed_s`, `cost_usd`, `cost_openclaw_usd` per quest. Add
   `n_scrolls_reported` (parsed from the reply, or defaulted to `None` when
   the model doesn't say) so a night's `discovery_*.json`/`reads_*.json`
   receipts are auditable against §4's human-baseline comparison the same way
   `web_reader.py`'s sessions will be.

### `scripts/thesis_cards.py`

9. **No browser-pacing change applies here.** Read closely:
   `thesis_cards.py`'s `openclaw_quest`/`TC.engine_side` path sends the model
   pre-loaded bars/revisions/news/catalysts/predictions/fundamentals for
   *reasoning*, and never invokes the `browser` tool at all — there is no
   `navigate`/`snapshot`/`scroll` sequence in this file to convert. The
   assignment's "snapshot→click→scroll instead of single-page reads" applies
   to `source_reads.py` only; note this explicitly in the handoff so the next
   session doesn't go looking for a browser call that isn't there.

---

## Sources

- [Cloudflare — Bot management: machine learning and more](https://blog.cloudflare.com/cloudflare-bot-management-machine-learning-and-more/)
- [developer.chrome.com — Headless Chromium (unified headless/headful since Chrome 112)](https://developer.chrome.com/docs/chromium/headless)
- [Chrome DevTools MCP — README](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [Chrome DevTools MCP — configuration.md (`--autoConnect`, `--browserUrl`)](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/configuration.md)
- [Chrome DevTools MCP — advanced-usage.md (existing-instance attach, "some sites block WebDriver-controlled browsers")](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/advanced-usage.md)
- [bennhuang.com — Why Your OpenClaw's Browser Keeps Getting CAPTCHAs](https://bennhuang.com/posts/why-your-openclaws-browser-keeps-getting-captchas/) (flagged: recommends CDP-evasion, out of scope)
- [Unayung/openclaw-browser-relay](https://github.com/Unayung/openclaw-browser-relay)
- [pinchtab/pinchtab](https://github.com/pinchtab/pinchtab)
- [lekt9/unbrowse-openclaw](https://github.com/lekt9/unbrowse-openclaw) (flagged: internal-API bypass, different licence risk)
- [zzzgydi/verge-browser](https://github.com/zzzgydi/verge-browser)
- [openclaw/openclaw](https://github.com/openclaw/openclaw)
- [berstend/puppeteer-extra-plugin-stealth](https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth) (flagged: fingerprint spoofing, out of scope, cited as reference only)
- Local OpenClaw bundled docs (not web-hosted, read from
  `C:\Users\mrthn\AppData\Roaming\npm\node_modules\openclaw\docs\` and
  `dist\extensions\browser\skills\browser-automation\SKILL.md`): `cli/browser.md`,
  `tools/browser-control.md`, `tools/browser-login.md`, `tools/browser/remote.md`
  (flagged: Browserbase/Notte stealth-proxy CDP providers), `tools/firecrawl.md`
  (flagged: stealth proxy mode), `cli/agent.md`, `cli/skills.md`, `cli/cron.md`,
  `cli/nodes.md`, `cli/doctor.md`, `cli/mcp/control-ui.md`.
- Aegis code read for this note: `backend/services/openclaw_client.py`,
  `backend/services/web_reader.py`, `backend/config.py` (`OPENCLAW_*`,
  `WEB_READER_*`, `LLM_PRICE_PER_MTOK`), `scripts/source_reads.py`,
  `scripts/thesis_cards.py`.
