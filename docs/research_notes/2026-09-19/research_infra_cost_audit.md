# Cost and Uptime Ledger — Aegis Infrastructure Audit

Written 2026-09-19, read-only. Murat's ask, verbatim: "Aegis has spent more
than one thousand dollars. There are two Railway connections; I don't know
what they are doing. They are spending so much money. For that amount of
money that has been spent, the project needs to bring back value. Go back to
the roots of the project, the infrastructure, to make sure everything has
been built correctly."

No commits made. No `railway up/down/variables` run. No process killed. No
API key value read or printed — only key **names**.

---

## 0. RESULTS SCOREBOARD (CANON convention — read this before anything else)

- **Best historical net strategy vs market:** not re-measured this audit —
  out of scope (infra only). See `docs/GRAND_ARENA_1_VERDICT.md` / arena docs
  for the standing number.
- **Best forward paper strategy:** not re-measured — the fleet's own
  `fleet --check` receipts (below) show live paper P&L marks, not a ranked
  verdict.
- **Independent selector count:** unchanged by this audit.
- **Infra found:** 2 Railway projects, **9 services total** (1 website + 6
  live paper-trading loops + 1 failed loop + 1 abandoned staging service +
  1 seal-authority), all currently **Online except two** (`aat-loop-hack2`:
  Failed/intentionally down; `aat-loop-staging`: Failed, orphaned, no
  associated build).
- **New actionable finding:** `seal-authority` is receiving a stream of
  malformed `GET /2026-09-19.json` requests (404, repeating every log line
  captured) from some client hitting the wrong path — not the documented
  `/allocator/<day>.json` or `/engines/...` routes. Low cost impact (404s
  are cheap) but it means **something is not reading the allocator record
  correctly** and should be traced to the caller. Not investigated further —
  read-only mandate.
- **External execution drag:** none measurable from here (no dashboard $
  access — see §1.4).
- **LLM spend, this session's read:** DeepSeek balance rose from **$7.18 to
  $56.98** between 2026-09-13 and now — i.e., **the $50 top-up Murat just
  made is confirmed landed**, and it is the entire "provider delta" this
  window; **local telemetry (`llm_calls.jsonl`) is absent on this host**, so
  the per-job breakdown below is reconstructed from receipts, not the raw
  ledger. Cost per gradeable output: **not computable from this machine** —
  the ledger that would answer it lives on Railway's volume.
- **RESULT IMPROVEMENT THIS SESSION: NONE** — this is an audit, not a fix.
  One spec is proposed (§4) but nothing is built.

---

## 1. RAILWAY — two projects, nine services

Read via `railway status` / `railway service <name>` / `railway logs
--service <name>` only (all read-only per the mandate). **Railway's dashboard
is the only place actual billed dollars live** — the CLI does not expose a
`$` figure anywhere. Exact path to read it:

> **railway.app → Murathan's Projects → (select project) → Usage tab**, or
> account-level **railway.app → Account Settings → Usage & Billing** for the
> combined bill across both projects. Nothing below substitutes for opening
> that page — it is the one number this audit could not read.

### 1.1 Project `selfless-courage` — this repo's website backend

| service | what it runs | restart policy | health surface | status (live read) | last deploy |
|---|---|---|---|---|---|
| `Aegis-Finance` | FastAPI (`backend/main.py`) via `backend/Dockerfile`, built from `railway.json` at repo root | `ON_FAILURE`, max 3 retries | `GET /api/health`, 30s timeout, wired in `railway.json` — confirmed live: `{"status":"ok","version":"0.2.0","cache_ready":true}` (curled 2026-09-19) | ● Online | deployment ID `764e4927…`; volume `aegis-finance-volume` 0.3 GB / 4.9 GB used |

This is the one service on this project. It places no orders (per CLAUDE.md,
confirmed — it is a read-only FastAPI research/website backend with a
`MALLOC_ARENA_MAX=2` note in the Dockerfile specifically because "Railway
bills that plateau as RAM-hours" for the 8-worker numpy screener — i.e. a
past session already diagnosed and fixed one Railway cost driver here). One
service, `ON_FAILURE` restart (not `ALWAYS`), a real health check — this is
the **better-instrumented** of the two Railway projects.

**Cost class:** a FastAPI service with a screener under `ON_FAILURE` restart
and a small persistent volume. Consistent with the memory reference "a
warm-cache loop burns ~$7/mo for 13 requests/12h" — this service is a
request-driven API (not a tight poll loop), so its bill should track request
volume plus RAM-hours from any resident cache, not a constant background
loop. **Estimate, not receipt**: low-to-mid single digits $/month unless the
screener's numpy Monte Carlo is being hit often; the 0.3 GB volume is
trivial.

### 1.2 Project `loving-elegance` — the paper-trading fleet + seal authority

Confirmed live (`railway status`, `railway service <name>`, all read-only):

| service | account role | status | volume | Dockerfile / restart policy |
|---|---|---|---|---|
| `aat-loop-hack1` | hack1 (theme_basket + shadow) | ● Online | `aat-loop-hack1-volume` | shared `Dockerfile` + `railway.toml`, `restartPolicyType=ALWAYS`, max 10 retries |
| `aat-loop-hack2` | hack2 | **● Failed** | `aat-loop-hack2-volume` | **intentionally down** — per `docs/DEPLOY_PLAN_2026-09-14.md` §0/§8: "hack2 is NOT deployed. Its loop stays down; its account is lane D's" (2026-09-13 12:05 HKT decision). This is a *known*, *documented* down state, not an unexplained failure. |
| `aat-loop-hack3` | hack3 (seasonality engine, Book F) | ● Online | `aat-loop-hack3-volume` | same |
| `aat-loop-hack4` | hack4 (tracker_portfolio) | ● Online | `aat-loop-hack4-volume` | same |
| `aat-loop-hack5` | hack5 (themes + options) | ● Online | `aat-loop-hack5-volume` | same |
| `aat-loop-hack6` | hack6 (tracker_portfolio + shadows) | ● Online | `aat-loop-hack6-volume` | same |
| `aat-loop-staging` | — | **● Failed** | `aat-loop-staging-volume` | `railway logs` returns **"Deployment does not have an associated build"** — this looks like an orphaned/abandoned service from an earlier experiment, never cleaned up. It is not mentioned anywhere in `docs/DEPLOY_PLAN_2026-09-14.md`. |
| `seal-authority` | — (no role; serves the sealed prediction book + daily allocator record over HTTP) | ● Online | **no volume** (deliberate — re-derives equity curves from the venue daily, per design in §4 of the deploy plan) | same base image; confirmed live at `seal-authority-production.up.railway.app`, actively logging `SEAL AUTHORITY allocator ready day=2026-09-18` cycles and `weekend, no trading seal required` for today (2026-09-19 is a Saturday) |

**Restart policy is `ALWAYS`, max 10 retries, on every loop service** — the
`railway.toml` comment explains why: "the loop IS the process; there is no
HTTP surface to health-check. A crash restarts it and the next cycle re-reads
the venue." This is a deliberate design (a crashed loop should resume, not
stay down), but it also means a loop in a crash-restart cycle would show
"Online" in `railway status` for most of a poll interval even while burning
CPU on repeated crashes — worth watching, though nothing observed here looks
like that (hack1's and seal-authority's logs show ordinary steady-state
activity, not crash loops).

**Health surface:** none of the six loop services has an HTTP health check
(by design — "there is no HTTP surface"). `seal-authority` DOES have one (it
serves HTTP routes) but no `healthcheckPath` is declared in the shared
`railway.toml`/`Dockerfile` — **this means Railway cannot auto-detect a wedged
`seal-authority` process the way it can a crashed one**, since a hung-but-still
-listening process never crashes and never gets restarted. Not fixed here
(read-only); flagged as the one gap in an otherwise well-designed restart
story.

**Last deploy dates:** `railway status` reports only a deployment ID, not a
timestamp, for the currently linked service (`seal-authority` in this
session's link). `docs/DEPLOY_PLAN_2026-09-14.md` is the authoritative deploy
receipt: all six loops + `seal-authority` were (re)deployed 2026-09-14 for the
"chunk 13b + 13c" push (Book F engine switch + allocator-in-the-authority).
No deploy receipt newer than 2026-09-14 was found in `docs/` for this repo's
execution side. Nine services deploying from one shared image/Dockerfile is
efficient from a build-cost perspective (one build, many services), but it
also means **`aat-loop-staging`'s broken build and the still-provisioned
volumes behind it and `aat-loop-hack2`** are two services that are plausibly
still billed for their volumes even while "Failed."

**New finding this session:** `seal-authority`'s logs show repeating
`GET /2026-09-19.json` → 404 requests, not the documented
`/allocator/<day>.json` shape. This is a live signal that some caller (a
loop's `allocator_sync.py`? a stale test hitting prod?) is malformed and is
polling a URL that will never succeed — cheap in dollars (404s are near-free)
but a correctness gap worth Murat's five minutes to trace, since a role
silently never receiving its allocator gross-scale falls back to its last
good (or deploy-time) budget without anyone noticing, per the deploy plan's
own "the silence to watch for: a green deploy, healthy loops, and an
allocator that is not allocating" warning.

### 1.3 "Two Railway connections" — what they actually are

Murat's framing ("there are two Railway connections; I don't know what they
are doing") maps exactly to the two projects: **`selfless-courage`** is the
research website (one FastAPI service, places no orders, low-traffic-driven
cost) and **`loving-elegance`** is the six-role paper-trading fleet plus the
allocator/seal authority (seven active-or-should-be-active services, one
orphan, `ALWAYS`-restart Python loops). Both are **paper only** — Alpaca
paper accounts (`PA3...` account IDs throughout the deploy plan), not real
capital; CLAUDE.md's "no LLM authority over real capital" invariant is
unrelated to whether Railway itself costs money, and it does: 6-7 always-on
Python processes cost real dollars even when the trades they place are
imaginary.

### 1.4 What could and could not be read

**Could read (this audit, live, read-only):** service topology, status
(Online/Failed), restart policies, health-check config, volume sizes,
Dockerfiles, recent log tails, the website's live `/api/health` response.

**Could NOT read:** the actual dollar amount either project has billed, this
month or cumulatively. `railway status`/`railway service`/`railway logs` do
not surface billing figures — Railway's usage metering (CPU-seconds,
RAM-hours, network egress, volume-GB-months) is dashboard-only. **This is the
single most important number missing from this audit and the fastest one for
Murat to get himself**: open the two Usage pages named in §1 above. Until
that number exists, every dollar figure in this document for Railway is a
qualitative cost-class estimate, not a receipt.

---

## 2. LLM SPEND (DeepSeek — the only provider, per CLAUDE.md)

### 2.1 What the code does

- `backend/config.py:1941` (`LLM_PRICE_PER_MTOK`) carries per-model
  in/cached-in/out rates, sourced from measured balance deltas — with an
  explicit, documented **precedent for exactly the kind of mispricing risk
  Murat is worried about**: the comment at `config.py:2004` states "the
  2026-08-12 correction was a careful, documented edit that got the output
  leg wrong by **4.6x** and nothing failed for 24 days." That is the closest
  documented figure to "the known ~5x overstatement" — it is real, it
  happened once, it was on the OUTPUT leg specifically, and it is now pinned
  by `test_llm_price_from_balance.py` so it cannot silently recur. I could
  not find a separate, currently-live "~5x cached-prefix overstatement"
  claim in the repo beyond this one; if Murat has a more specific number in
  mind it may be in a session he did not commit to `docs/`.
- `backend/services/llm_telemetry.py` correctly separates `tokens_in` (full
  rate) from `cached_tokens` (discounted cache-read rate) and documents that
  **DeepSeek's `prompt_tokens` INCLUDES cache hits** while Anthropic's format
  excludes them — i.e., the code already accounts for the cached-prefix
  distinction that would otherwise double-count cost. This looks like the
  fix for the overstatement class of bug, already landed.
- `scripts/llm_cost_audit.py` is the reconciliation tool: `provider_balance_
  delta − telemetry_total = unaccounted`. It explicitly refuses to treat a
  missing balance endpoint as $0, and refuses to pool ledgers across hosts.

### 2.2 What running it (without `--snapshot`, read-only) showed

```
LLM COST AUDIT  (since 2026-09-13)
  balance now      : $56.98
  balance at start : $7.18   [snapshot 2026-09-13T15:01:56Z (cost_audit)]
  provider says     : $-49.8000 spent          <- negative = balance ROSE
  telemetry says    : $0.0000
  UNACCOUNTED       : $-49.8000   <- top-up inside the window (balance rose)

  ledger C:\Users\mrthn\aegis-finance\backend\data\optimus\llm_calls.jsonl   (absent on this host)
```

**This confirms Murat's $50 top-up landed** ($7.18 → $56.98, delta $49.80,
matching "just topped up $50" almost exactly — the ~20¢ gap is plausibly a
small amount of spend inside the same window, or a top-up bonus/rounding).
It also confirms the important structural gap: **the local telemetry ledger
does not exist on this machine.** Production writes its own `llm_calls.jsonl`
on the Railway volume (per the script's own printed caveat: "Production
writes its own file on Railway's volume; run this there too, or read it
through the API, before calling any number the program-wide spend"). **This
audit cannot produce a verified by-job, by-month $ breakdown from this
machine** — only from the balance-snapshot history, which is coarser.

### 2.3 Balance history (receipt: `backend/data/optimus/deepseek_balance.jsonl`, 10 rows total)

| read_at (UTC) | balance $ | inferred spend since prior read |
|---|---|---|
| 2026-08-24 12:10 | $23.99 | (earliest snapshot on file — spend before this date is **not on record locally**) |
| 2026-09-05 11:58 | $13.36 | ~$10.63 over ~12 days |
| 2026-09-05 12:23 | $9.38 | ~$3.98 in 25 minutes (a burst — plausibly a batch job) |
| 2026-09-08 11:43 | $9.11 | ~$0.27 over 3 days |
| 2026-09-08 11:43 | $9.11 | (duplicate read, same minute) |
| 2026-09-09 02:42 | $9.07 | ~$0.04 |
| 2026-09-13 10:54 | $8.35 | ~$0.72 over 4 days |
| 2026-09-13 11:35 | $7.22 | ~$1.13 in 41 minutes |
| 2026-09-13 12:26 | $7.18 | ~$0.04 |
| 2026-09-13 15:02 | $7.18 | $0.00 |
| **2026-09-19 (this audit)** | **$56.98** | **+$49.80 (the $50 top-up)** |

**Net measured burn, 2026-08-24 → 2026-09-13 (20 days, the only fully-covered
window on record locally):** $23.99 − $7.18 = **$16.81**, i.e. roughly
**$0.84/day** average over that stretch, unevenly distributed (two visible
bursts around 09-05 and 09-13 consistent with batch LLM-typing jobs, not a
steady drip). **This is a RECEIPT for that 20-day window and nothing
earlier** — DeepSeek spend before 2026-08-24 is not reconstructable from
local files; if there is production-side history it lives on the Railway
volume, unread by this audit.

### 2.4 The lab's own dollar cap

`backend/config.py:2728`: `LAB_DAILY_SPEND_CAP_USD = 3.00` (env override
`AEGIS_LAB_DAILY_SPEND_CAP_USD`). Every `LEARNED_2026-09-18.md` /
`LEARNED_2026-09-19.md` supervisor line printed by `scripts/always_on_lab.py`
shows **`spend $0.00/$3.00 cap`** — the always-on lab's LLM typing loop is
using the **local** model (llama-server on the desktop GPU, unmetered by
this cap) exclusively; the cloud reader hook (`CloudReader`) is designed but
explicitly **not implemented** (spec §3.2, §9) — so the lab itself has spent
$0 in cloud LLM dollars to date. **The $16.81+ measured DeepSeek burn above
is coming from somewhere else** — production API calls (the deployed
website's LLM analysis endpoints), the L2 typed-events cloud path if it was
ever manually exercised, or other scripted jobs — not the always-on lab.
This is worth Murat's attention: the spend is real and the cap that would
bound it (`LAB_DAILY_SPEND_CAP_USD`) does not apply to whatever is actually
spending it.

---

## 3. OTHER PAID THINGS

| item | evidence | cost |
|---|---|---|
| **WRDS** | `.env.example`/`config.py` do not carry a WRDS key (it uses `~/.pgpass` via `wrds_pull_all.py`/`wrds_pull_linkage.py`/`wrds_recon_legacy.py`/`wrds_repull_finratio_early.py`); `docs/V5_CLOSEOUT.md`: "Chase the HKU WRDS approval." | **$0 — HKU university licence**, per CLAUDE.md context (Murat is an HKU student). Estimate, matches Murat's own framing in the prompt. |
| **Vercel** | `frontend/vercel.json` and `frontend/.vercel` **both exist** in this repo (found this session) — so the frontend HAS been linked/deployed to Vercel at some point, separately from the Railway-served static export the website backend also serves. Could not read Vercel's own dashboard (no CLI access invoked; out of the two explicitly-scoped Railway tools). | **Estimate: likely $0 (free tier)** for a Next.js frontend at this traffic level, but **unverified** — this is a THIRD hosting surface (Railway backend + Railway frontend/static export + Vercel) that nobody in this audit's source docs mentions reconciling. Worth a five-minute dashboard check. |
| **FMP (Financial Modeling Prep)** | `FMP_API_KEY` in `.env.example`, read at `backend/config.py:235`. | Vendor key present by name; tier/cost not stated in any doc found. **Not a receipt** — flag for Murat to confirm tier. |
| **Finnhub** | `FINNHUB_API_KEY` in `.env.example` (both repos — also `AAT_FINNHUB_API_KEY` in the execution repo's Dockerfile comment), read at `backend/config.py:233`. Used for `pm_catalysts.py`'s earnings calendar, explicitly **"free tier"** per the always-on-lab spec (§3.4: "Finnhub, free tier, cached 6h"). | **$0 — confirmed free tier**, receipt-grade (cited in spec, not just assumed). |
| **FRED** | `FRED_API_KEY`, `config.py:232`. | Free (US government data API, no paid tier exists). |
| **Alpha Vantage / Polygon** | `os.getenv("ALPHA_VANTAGE_API_KEY", "")` / `os.getenv("POLYGON_API_KEY", "")` at `config.py:235-236` — present as **code paths**, but **NOT in `.env.example`** for either repo (only `FRED`, `FINNHUB`, `FMP`, `DEEPSEEK` are in `.env.example`). Likely unused/unconfigured. | Estimate: $0 (not provisioned). |
| **EODHD** | Rejected. `docs/V5_CLOSEOUT.md:9`: "EODHD two-phase acceptance gate — Phase 1 'pass' exposed as inflated; **Phase 2 FAIL 14/20** → don't renew (NEGATIVE_RESULTS §8, F-021)." Also `docs/BACKLOG.md:59`: NN backtests stay "T7-blocked until EODHD phase 2 / WRDS." | **Was paid, was tested, failed its own acceptance gate, and the documented decision is "don't renew."** Could not locate a file literally named `NEGATIVE_RESULTS.md`/`§8` in `docs/` — the citation may point to a section inside a larger doc (e.g. `V5_CLOSEOUT.md` itself, or an archived doc) not resolved in this pass. The **decision** ("don't renew") is receipt-grade regardless of where §8 physically lives. |
| **Alpaca** | Paper trading only, all six `PA3...` accounts. Free (Alpaca's paper API has no cost). | $0, confirmed by design (CLAUDE.md: "no LLM authority over real capital"). |
| **DeepSeek** | See §2. | ~$16.81 receipt-grade (20-day window) + $50 top-up just applied; total historical spend **before 2026-08-24 is not locally reconstructable**. |
| **Railway** | See §1. | Dashboard-only; not read this audit. |

### 3.1 The "$1,000 so far" reconstruction — best effort, marked by confidence

| component | amount | confidence |
|---|---|---|
| DeepSeek, 2026-08-24 → 2026-09-13 | $16.81 | **RECEIPT** (balance snapshots) |
| DeepSeek top-up just applied (not yet spent) | $50.00 | **RECEIPT** (this session's own read) |
| DeepSeek, before 2026-08-24 | unknown — plausibly the largest single component, since $23.99 was already the balance on 2026-08-24 (i.e. topped up before that, and spent down from some earlier, larger top-up) | **ESTIMATE, wide error bars** |
| EODHD subscription (paid, then not renewed) | unknown $ amount; the decision not to renew is documented, the price paid is not, in anything read this session | **ESTIMATE — likely $10s-$100s given it's a data vendor two-phase-gated eval** |
| Railway, `selfless-courage` (website) | unknown; qualitatively low (single service, request-driven, `ON_FAILURE` restart) | **ESTIMATE** |
| Railway, `loving-elegance` (fleet) | unknown; qualitatively the largest Railway line — **7 always-on Python processes, `ALWAYS` restart, running continuously since at least 2026-09-14**, is the shape of cost the project's own memory file already names ("a warm-cache loop burns ~$7/mo for 13 requests/12h" — and these are NOT 13-requests/12h loops, they are always-on trading loops making 60-130 orders per account per the DEPLOY_PLAN's own count, so the true rate is almost certainly several times that reference figure per service) | **ESTIMATE, and the single most likely place the "$1,000" mostly went**, pending the dashboard read in §1.4 |
| WRDS, FMP, Finnhub, FRED, Alpaca, Vercel | $0 or near-$0 (licence/free tier) | mostly RECEIPT-grade per row above |

**Bottom line: this audit can verify roughly $67 of DeepSeek-side dollar
movement with receipts (the $50 top-up plus the $16.81 20-day burn), and can
identify — but not price — 7+ always-on Railway processes and one EODHD
vendor subscription as the plausible bulk of the remaining ~$930+. The single
fastest way to close that gap is the two Railway Usage dashboard pages named
in §1.4, plus asking whoever holds the EODHD account for its invoice total.**

---

## 4. UPTIME CHAIN ON THE PC — SPEC for one change

### 4.1 What is broken, confirmed live this session

- **`AegisDailyPass`** (schtasks, `ONLOGON`... actually registered daily
  06:30, `Logon Mode: Interactive only`): `Last Result: -2147020576`
  (`0x80070520`, "a specified logon session does not exist"), **confirmed by
  a live `schtasks /Query /V` read** just now. `Last Run Time: 19/9/2026
  11:20:47 am` (not even 06:30 — it may have been manually re-triggered).
- **`AegisIIF1NightLauncher`** (`Logon Mode: Interactive only`, scheduled
  16:00 weekdays): same `Last Result: -2147020576`, **confirmed live**.
  `Last Run Time: 18/9/2026 5:28:31 pm`.
- Both tasks are `Interactive only` — they require a logged-in interactive
  session, and Murat's session apparently signed out overnight, which is
  exactly the failure mode `0x80070520` describes: Windows Task Scheduler
  cannot start an "Interactive only" task with no interactive logon session
  present. **The fix is not "retry the task" — it is "stop requiring an
  interactive session for something that needs to run unattended."**
- **The always-on lab has died and restarted 3 times since 2026-09-18**,
  confirmed from `always_on_lab_lock.json`'s own overwrite chain:
  `pid 10128` (started 2026-09-18 05:41 UTC) → overwritten by `pid 33736`
  (started 2026-09-18 09:23 UTC, "10128 is not alive") → overwritten by
  `pid 14192` (started 2026-09-19 03:15 UTC, "33736 is not alive", still
  running as of this audit). **No `exit_reason` is recorded anywhere in this
  chain** — the log (`always_on_lab.log`) shows the *next* instance's
  `WARNING always_on_lab: overwrote a stale lock: pid N is not alive` line,
  but never a line from the dying instance saying *why* it died. This
  matches the task's framing exactly: "no STOP file... the lab records its
  own exit reason" is not yet true.

### 4.2 Why this matters for the money already spent

Every scheduled-task failure and every unlogged lab restart is a night where
the always-on lab's own eight loops (news pull, L2 typing, decision-vs-
reality grading, the NN nightly refit, the idle-GPU queue) may have run
**less** than intended, while the Railway fleet (§1.2) kept running and
kept costing money regardless — **uptime on the PC and uptime on Railway
are decoupled**, so a broken PC scheduler does not save any Railway dollars;
it only reduces the research value being extracted per dollar already being
spent on the always-on GPU box. Fixing this is a "value per dollar already
spent" fix, not a "stop spending" fix.

### 4.3 THE SPEC — one change: the lab owns its own clock

**Read for this spec:** `scripts/always_on_lab.py` (1,809 lines, current),
`backend/data/optimus/always_on_lab.cmd`, the Startup-folder launcher
`AegisAlwaysOnLab.vbs` (confirmed present at
`C:\Users\mrthn\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\AegisAlwaysOnLab.vbs`,
launches the `.cmd` hidden via `WScript.Shell.Run(..., 0, False)`), and the
spec this chunk was originally built from — **found at
`docs/research_notes/2026-09-13/spec_always_on_lab.md`**, not
`research_notes/2026-09-12/` as the task brief guessed (the file moved / was
authored a day later than expected — noted per CLAUDE.md's "absence of a
local object is not evidence of absence," the file exists, just at the
2026-09-13 dated folder).

**Current state, confirmed by reading the code:**
`scripts.always_on_lab.SCHEDULED_DRIVERS = {"daily_pass": "scripts.daily_pass",
"night_factory": "scripts.night_factory", "monday_night": "scripts.monday_night"}`
(line ~279). The lab currently only **yields to** these three drivers
(`yields_to()`, used by `loop_news_pull` and `loop_idle_gpu_queue`) — it does
not run them itself, and **`run_night_launcher.py` / `AegisIIF1NightLauncher`
is not in `SCHEDULED_DRIVERS` at all**, so the lab does not even know that
scheduled task exists to yield to it, let alone dispatch it.

**The change, stated as the task asked — the lab owns the daily pass and the
night launcher on its own clock:**

1. **New config constants**, `backend/config.py` (per "put parameters in
   config, never hardcode"):
   ```python
   LAB_OWNS_DAILY_PASS_LOCAL_TIME = "06:30"     # local (machine) time, HH:MM
   LAB_OWNS_NIGHT_LAUNCHER_LOCAL_TIME = "16:00"  # local, weekdays only
   LAB_DISPATCH_GRACE_MINUTES = 15               # a tick due at 06:30 that
       # wakes at 06:33 (5-min heartbeat) still fires; one that wakes at
       # 07:10 because the machine was off does NOT "catch up" — same
       # "unset means today, not five days of backlog" rule the spec
       # already states for NIGHT_RUN_DATE (spec §2)
   ```

2. **New functions in `scripts/always_on_lab.py`**, following the existing
   `loop_*(state: LabState) -> dict` shape used by every other loop
   (`loop_news_pull`, `loop_l2_typing`, `loop_decision_vs_reality`,
   `loop_catalyst_calendar`, `loop_nn_lab`, `loop_idle_gpu_queue` — all
   already in the file):

   - `loop_daily_pass_dispatch(state: LabState) -> dict` — every tick,
     check: is local time within `[LAB_OWNS_DAILY_PASS_LOCAL_TIME,
     LAB_OWNS_DAILY_PASS_LOCAL_TIME + LAB_DISPATCH_GRACE_MINUTES]`? Is
     today's `daily_pass` receipt (`night_factory_<date>/` — reuse
     `_receipt_today("daily_pass", today)`, the helper that already exists
     at line ~1115 for the idle-GPU queue) **absent**? If both, dispatch
     `scripts.daily_pass` through the same `dispatch_job`/`call_boxed`
     pattern §3.6 already uses (timeout-boxed, one attempt, receipt recorded
     regardless of outcome — "a refusal is a finding"). If the receipt
     already exists for today (the scheduled task DID fire, or the lab
     already ran it earlier this tick-cycle), **skip and say
     `already_ran_today`** — this is the "already-ran-today gate keyed on
     the receipt file" the task asked for, reusing the exact mechanism
     `loop_idle_gpu_queue` already has for its own jobs rather than
     inventing a second one.
   - `loop_night_launcher_dispatch(state: LabState) -> dict` — same shape,
     gated on `LAB_OWNS_NIGHT_LAUNCHER_LOCAL_TIME`, weekday check
     (`datetime.now().weekday() < 5`), and the IIF-1 launcher's own receipt
     convention (`run_night_launcher.py --acceptance`'s existing
     acceptance-receipt shape, or the plainer per-day launch record already
     seen at `backend/data/optimus/iif1_launches/<date>.json` in this
     session's `git status` — confirmed to exist and be actively written).
     **Must call `run_night_launcher` with `--scheduled`** (the flag the
     module's own `--schtasks` print block already names at line ~414/422)
     so the module's own arming/timing refusals (the `PAST_LATEST_SAFE_
     LAUNCH` refusal seen live in `iif1_launches/2026-09-17.json` this
     session) still apply — the lab dispatches it, it does not bypass its
     own safety gates.
   - Both new loops go into `LOOPS`/`PERIODS`/`HANDLERS` (the existing
     dicts the file's `run_forever`/`tick` machinery already iterates —
     confirmed present via `__all__`), at a **5-minute cadence** (the
     supervisor's existing heartbeat), so `LAB_DISPATCH_GRACE_MINUTES=15`
     gives 2-3 chances to catch the window even if one tick is slow.
   - `SCHEDULED_DRIVERS` gains a fourth entry,
     `"night_launcher": "scripts.run_night_launcher"`, so the arbitration
     rule already in place (never run a driver the lab itself just
     dispatched, and never race a manually-started one) covers it
     symmetrically with `daily_pass`.

3. **The scheduled tasks become a documented fallback, not deleted outright
   this session** (deletion is an attended, human action per the project's
   own "seed-a-lane"/attended-change culture — this audit does not delete
   anything). The spec's recommendation: **re-register both tasks
   `/RL LIMITED /SC ONLOGON`** (the same fix `always_on_lab`'s own
   registration already uses, per its spec §1.1) instead of a fixed daily
   time under "Interactive only" — this removes the exact failure mode that
   fired today (`0x80070520`), because `ONLOGON` only needs to fire once per
   logon and the supervisor's own loop then owns the actual 06:30/16:00
   dispatch from inside a process that is already running unattended.
   **Once the lab's own dispatch loops (above) are built and have accrued
   the same three-consecutive-date acceptance bar §7 of the original spec
   already defines for the lab overall, the two scheduled tasks are
   redundant and should be deleted by Murat's own hand** — not automated,
   per the project's standing rule that seeding/retiring scheduled
   infrastructure is attended.

4. **Exit reason — the lock carries it, via `atexit`:**
   ```python
   # near acquire_lock()/release_lock(), scripts/always_on_lab.py
   import atexit

   def _record_exit(reason: str) -> None:
       lock = read_lock()
       if lock.get("pid") == os.getpid():
           lock["exit_reason"] = reason
           lock["exited_utc"] = _now()
           _write_atomic(lock_path(), lock)

   atexit.register(lambda: _record_exit("process_exit_unclassified"))
   ```
   and every KNOWN clean-exit path (`STOP` file seen, `--ticks` exhausted,
   `AlreadyRunning` refusal) calls `_record_exit("<specific reason>")`
   **before** `atexit` would fire generically, so the generic
   `"process_exit_unclassified"` value only ever appears for a crash/kill —
   which makes it a genuinely diagnostic signal (today, an instance dying
   leaves NOTHING behind except the next instance's "overwrote a stale lock"
   line; after this change, the dead instance's OWN last-written lock
   carries why). This does not catch `TerminateProcess`/crash-with-no-
   unwind (per the project's own documented lesson,
   "a promise kept only on the tidy path is not the promise") — a future
   session could add a Windows Job Object if that matters more than it does
   today; not in scope for this spec.

### 4.4 Tests — `backend/tests/test_always_on_lab.py` style (fixtures redirect
paths, stub every loop — the file already exists and already follows this
pattern for the other eight loops; these are the two/three new cases to add)

1. `test_daily_pass_dispatches_once_inside_the_window_and_gate` — monkeypatch
   `datetime.now()` to 06:31 local, no `daily_pass` receipt for today; assert
   `loop_daily_pass_dispatch` calls `dispatch_job`/`call_boxed` exactly once
   (spy, not a real subprocess).
2. `test_daily_pass_already_ran_today_skips` — same time, but a
   `daily_pass` receipt for today already exists (write a fixture file under
   `tmp_path`'s `night_factory_<date>/`); assert the loop returns
   `status: "already_ran_today"` and the dispatch spy's call count is 0.
3. `test_daily_pass_outside_window_does_nothing` — 10:00 local; assert
   `status: "not_due"`, dispatch spy not called.
4. `test_night_launcher_dispatch_respects_weekday_gate` — Saturday,
   16:01 local; assert `status: "weekend_not_due"`, no dispatch — mirrors the
   live `seal-authority` behavior already observed this session
   ("2026-09-19: weekend, no trading seal required").
5. `test_night_launcher_dispatch_passes_scheduled_flag` — assert the
   dispatch call includes `--scheduled` (spy on the argv passed to
   `run_night_launcher.main`/subprocess invocation), so the module's own
   arming and timing refusals stay in force.
6. `test_exit_reason_recorded_on_stop_file` — write a `STOP` file mid-loop;
   assert the lock file's `exit_reason` is a specific string (e.g.
   `"stop_file"`), not the generic `atexit` fallback.
7. `test_exit_reason_generic_atexit_fires_on_unhandled_death` — simulate an
   unhandled exception path reaching `main()`'s top level (not a crash/kill,
   which this cannot reach in a unit test — name that limitation in the
   test's own docstring, per the project's "a gate that cannot go green is
   broken" discipline: this test proves the registered handler exists and
   fires for an in-process exit, and explicitly does NOT claim coverage of
   `TerminateProcess`).
   All dates via a frozen-`today` fixture (`test_always_on_lab.py`'s
   existing pattern), never a literal date — CLAUDE.md rule 5.

---

## 5. VERDICT

**What the ~$1,000 bought, as best reconstructed:** a research corpus (268+
docs, 69+ roadmaps/handoffs, an Optimus brain MCP over 395+ indexed pages), a
test suite that has grown from 8,694 (2026-09-12) to **9,998 tests collected**
as of this audit (2026-09-19, `pytest --collect-only`, offline), and a
six-role Alpaca **paper** fleet with an allocator and a seal authority that
are architecturally sound (hash-verified engine delivery, fail-closed
refusals, worst-case-in-dollars printed before every sizing change) but have
placed **zero dollars of real trades**, by design (CLAUDE.md: "no LLM
authority over real capital"). The infrastructure itself — Railway restart
policies, health checks on the website, PID-owned process lifecycles, the
allocator's cross-service key references — is built with unusual care for a
project this size; the gap is not engineering quality, it is **that none of
it has produced a verified real-money result yet, and the always-on
research/learning loop meant to accelerate toward one has been running with
an average uptime interrupted by three restarts in under 30 hours and two
silently-failing scheduled tasks.**

**The ONE cost to cut this week:** **`aat-loop-staging`** (Railway,
`loving-elegance` project) — a Failed service with no associated build and
no mention in the current deploy plan, still holding a provisioned volume.
It is producing zero research value and is the single line item in this
audit that looks like pure waste rather than a design tradeoff. Second look,
same week: confirm via the dashboard (§1.4) whether `aat-loop-hack2`'s
volume is still being billed while its loop is intentionally down — if
Railway bills idle volumes, that is a second, larger, and equally
zero-value line.

**The ONE reliability fix that unlocks forward evidence:** **§4's
spec — give the always-on lab its own clock for the daily pass and the
night launcher, and register both scheduled tasks `ONLOGON` instead of a
fixed "Interactive only" time.** This is the fix that stops today's exact
failure (`0x80070520`, both tasks dead because the interactive session
dropped overnight) from recurring, and it is the fix that turns "the machine
was on but the scheduled research didn't run" from a silent gap into either
a completed run or a named, receipted refusal — which is the precondition
CLAUDE.md's own session-start protocol and CANON's "if it isn't
pre-registered, it didn't happen" both depend on: forward evidence that
never accrued because the launcher silently failed to fire is not evidence
of a negative result, it is evidence of nothing, and the project cannot tell
the difference from where it stands today.

---

## Appendix: exact commands run this session (for reproducibility)

```
railway status                                    # (in both repos)
railway service <name>                            # (interactive prompt only; not run non-interactively)
railway logs --service aat-loop-hack2 | head
railway logs --service aat-loop-staging | head
railway logs --service seal-authority | tail
railway logs --service aat-loop-hack1 | tail
curl https://aegis-finance-production.up.railway.app/api/health
python -m scripts.llm_cost_audit                  # no --snapshot; read-only
python -m pytest backend/tests/ -q --collect-only  # offline, count only
schtasks /Query /TN "AegisDailyPass" /V /FO LIST   # (PowerShell, read-only)
schtasks /Query /TN "AegisIIF1NightLauncher" /V /FO LIST
```

No file outside `research_notes/2026-09-19/` was written. No git commit was
made. No API key value was read or printed.
