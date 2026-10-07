# OUTSIDE TOOLS — 2026-10-07

**Licence: `PRODUCT_EXPERIMENT` research note — the written half of chunk C22**
(`docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md` §5a). Nothing here
is a `RESEARCH_CLAIM`. This page answers, for each outside system: has Aegis
already taken something from it, is there one more thing worth taking, and
what — precisely — would the next step cost. **No installs were run to write
this page** (the machine is memory-constrained today, per the task brief);
every OpenBB fact below is either already in `borrow_from_outside_2026-10-06.md`
(dated 2026-10-06) or freshly verified from PyPI/GitHub metadata this session
(2026-10-07) without installing anything. Marked `UNVERIFIED` where a primary
source could not be reached.

**What this file does NOT do.** C22's acceptance line asks for "a probe
receipt; a written refusal for the deferred two." This page delivers the
written refusals for LEAN and BLPAPI in full, and for OpenBB delivers the
exact probe to run plus the licence/footprint facts needed to approve
running it — but does **not itself run the probe**. That is the next
session's action item, in a separate venv, when memory allows. Treat "C22:
written" as done and "C22: probed" as still open.

---

## 1. Verdict table (one line each)

| System | Verdict | Dated reason / receipt |
|---|---|---|
| **OpenBB platform + MCP server** | `ADOPT-AS-RESEARCH-TOOL` (not installed) | 2026-10-06, `borrow_from_outside_2026-10-06.md` row 3: its new piece is the uniform MCP interface, not data Aegis lacks; "never a second parallel path for a provider Aegis already hand-pulls." |
| **QuantConnect LEAN** | `DEFERRED` | 2026-10-06, same file row 4: LEAN's own survivor-aware US equity data (AlgoSeek, US Equity Security Master) is paid-only; the free workaround (feed Aegis's own panel in) is scoped (`research_library_expansion_and_lean.md` §2.5) but unbuilt, and C22's own gate is "no finalist" — there is no single decided strategy yet to replicate. |
| **BLPAPI / xbbg (Bloomberg terminal)** | `OWNER` | 2026-10-06 roadmap §6 D11/D1: needs the terminal PC, an authorized session, and licence confirmation only Murat can give; nothing for a builder to do until then. |
| **FinRL** | `DEFERRED` (guardrail recorded, not revisit-gated on anything but router existence) | 2026-10-06, `borrow_from_outside_2026-10-06.md` row 6: irrelevant until a learned router exists (THE BOTTLENECK, CLAUDE.md), which needs ≥2-3 independent `PRODUCT_EXPERIMENT` selector books first. |
| **TradingAgents** | `MECHANISM_REJECTED` for its core act; debate PATTERN already absorbed | 2025-08-17 (closed), independently re-verified 2026-09-28, `outside_methods_compared_2026-09-28.md` lines 303-313: flagship Sharpe 6.4-8.2 traces to a confirmed look-ahead leak, GitHub issue #203. |
| **Microsoft Qlib** | `DEFERRED` as a platform; one chart shape already extracted | 2026-09-26/09-28: ships no free US data, validated on OpenAI-tier models (DeepSeek-only shop); `outside_methods_compared_2026-09-28.md` row "Microsoft RD-Agent(Q)" scores adoptability 10/100. |
| **Microsoft RD-Agent(Q)** — the bandit-over-families mechanism | `ADOPTED` | 2026-10-06, built directly in `backend/services/hyp_lab.py` (no RD-Agent code, no Qlib dependency) — see §2 below. |
| **Alpaca hackathon winners' patterns** | `ADOPT-AS-PATTERN` (principle adopted; two concrete pieces still to build) | 2026-10-06, `borrow_from_outside_2026-10-06.md` row 1 + §"The Alpaca hackathon section." |

**One line for the owner:** none of the seven rows above changes a result
this week — the only items with code attached (RD-Agent's bandit feedback,
decision-lineage IDs) already shipped before this page was written, and
the three undone items (OpenBB probe, named fleet gates + EOD audit, LEAN/
BLPAPI) are each gated on something other than engineering time (owner
decision, memory headroom, or a finalist that does not exist yet).

---

## 2. What was already borrowed into THIS repo — module by module

- **RD-Agent(Q)'s bandit-feeds-generation mechanism → `backend/services/hyp_lab.py`.**
  `family_record(state)` (line 351) computes a Beta(a,b) posterior per
  hypothesis family; `generation_prompt()` (line 667) now calls
  `family_record(state)` directly (line 669) and prints a `FAMILY TRACK
  RECORD` line into the LLM's own generation prompt (line 687), plus a
  `FAMILY LABELS` line (lines 680-685) that tells the model "families whose
  cells keep failing get fewer slots per round" — the posterior feeds
  *backward* into what gets proposed, not just forward into ranking. The
  code comment at line 680 cites `Review 2026-10-06 F7` as the reason the
  prompt names the taxonomy but not the live shrink numbers (to avoid
  inviting relabelling). This is roadmap decision D6 / chunk C12 ("EV shrink
  for families with posterior < 0.15") applied as a generation-time quota,
  not an after-the-fact discount — exactly the RD-Agent(Q) piece the
  borrow note flagged as the one thing `hyp_lab` was missing. **No Qlib or
  RD-Agent code was imported; only the feedback wiring was missing, and it
  is now there.**

- **PRISM / Autobelay's "traceable Decision Story" → `backend/services/decision_story.py`.**
  Line 18's own module docstring states the lineage chain verbatim:
  `event_ids -> evidence_ids -> forecast_ids -> decision_id`, continuing
  through `abstention_id` (182), `outcome_id` (186) and `attribution_id`
  (190). This is the handoff's §37 "What AEGIS should borrow, item 1:
  Decision Story from evidence to execution" and the roadmap's adopted
  vocabulary ("Decision Story lineage... MDC/regret counterfactuals,"
  §2 of the roadmap) — built as our own object graph, not a port of
  PRISM's code (PRISM's own implementation was never inspected; the pattern
  was).

- **Killswitch/Autobelay's "gates only shrink, never enlarge" → `backend/services/fleet_manager.py::check_limits`** (line 657-693).
  This is the **principle** already in production: every branch of
  `check_limits` either returns a refusal string or `None` — it has no path
  that increases `qty` or `notional`. **What is NOT yet borrowed**: the
  three winners' gates are individually named and logged (Killswitch: 15
  named gates); Aegis's is one function with ~6 implicit checks (ticker
  pattern, qty positive, order type, short-refusal, cash/leverage, gross
  cap, name cap) and has no `cooldown` or `sector_concentration` check, and
  no scheduled per-account end-of-day critique call distinct from a human
  review session (confirmed absent by grep this session — no
  `cooldown`/`sector_concentration`/`eod_audit` symbol exists anywhere
  under `backend/services/`). This is the ADOPT-as-pattern row's "ONE new
  piece to borrow" column, unbuilt as of 2026-10-07 — not to be confused
  with the RD-Agent and Decision Story items above, which ARE built.

---

## 3. Next step and cost, system by system

### OpenBB platform + MCP server — `ADOPT-AS-RESEARCH-TOOL`, not installed today

**Install command (when memory allows — a SEPARATE venv, never the project's own):**

```
python -m venv .venv-openbb
.venv-openbb/Scripts/pip install openbb-mcp-server
```

Deliberately **not** `pip install openbb` (the full meta-package depends on
36 sub-packages per PyPI metadata, pulled 2026-10-07); install
`openbb-mcp-server` plus only the free-no-key provider extras the probe
needs (yfinance, sec, cftc, tmx, ecb — per `borrow_from_outside_2026-10-06.md`
row 3's own build spec, item 1).

**The one probe query to run** (per the borrow note's own 3-line build
spec, item 2): point the MCP server's `available_tools` discovery at **one
concrete gap** — a non-US or Asia-session ticker the yfinance pipeline
handles poorly (VISION file: "Asia first, whole-market") — and compare its
answer against the existing collector for one week before anything
production depends on it. No query was run this session.

**Licence line.** The task brief asked to verify whether the platform is
AGPL. It is not: `gh api repos/OpenBB-finance/OpenBB/contents/LICENSE`,
fetched and decoded this session (2026-10-07), returns the Apache License,
Version 2.0 text with "Copyright (c) 2021-2026 OpenBB Inc. All files in this
repository are licensed under the Apache License, Version 2.0." GitHub's
own auto-detected `license.spdx_id` field reads `NOASSERTION`
(`license.name: "Other"`) — almost certainly because the custom copyright
preamble line breaks GitHub's SPDX auto-matcher, not because the licence
text differs from Apache-2.0. The `openbb-mcp-server` PyPI package
(v2.0.1, fetched 2026-10-07) independently declares `license: Apache-2.0`
in its own metadata. Both are free to use and modify; Apache-2.0 requires
attribution and a NOTICE pass-through, nothing stronger (no AGPL-style
network-copyleft obligation).

**Free-without-a-key data providers**, per `borrow_from_outside_2026-10-06.md`
row 3 and `docs.openbb.co/odp/python/extensions/providers` (cited there,
not re-fetched this session): yfinance, SEC, CFTC, TMX (Canada), ECB, OECD
— and per that note, these "mostly overlap what Aegis already hand-pulls"
(`finra_short_volume.py`, `official_sources.py`, `world_digest.py`); the
genuinely new piece is the uniform interface over 70+ providers, not new
facts.

**Memory/disk footprint — ESTIMATED, not measured.** `openbb-mcp-server`'s
own wheel is 108 KB (PyPI, 2026-10-07) and the `openbb` meta-package wheel
is 3.9 KB — both are thin wrappers. The weight is in the dependency chain:
`openbb-core` plus provider extras pull in `pandas`, `numpy`, `fastapi`,
`pydantic`, `uvicorn` and per-provider HTTP clients. A fresh venv with
`openbb-mcp-server` + 5 free provider extras is estimated at roughly
**150-400 MB of installed site-packages**, almost entirely from the
pandas/numpy/fastapi chain (this repo's own venv already carries most of
that chain, so a SEPARATE venv double-pays it rather than sharing it — by
design, to keep the probe from touching the project's dependency set).
This estimate was not run or verified today; the honest footprint is
"check it after the next session installs it," not this page's number.
**Explicitly deferred — this machine is memory-constrained today.**

### QuantConnect LEAN — `DEFERRED`

**The data question, answered precisely** (not generally): LEAN's own free
US daily data does **not** include survivor-aware history. Its paid
AlgoSeek US Equities feed and US Equity Security Master (delistings,
~27,500 names since 1998) both require a paid org tier through the LEAN
CLI — confirmed 2026-10-06 in `borrow_from_outside_2026-10-06.md` row 4.
A free 1991-2024 CRSP-grade replication through LEAN's native data does
not exist.

**Our own panel could feed it instead.** Two files already hold the
survivorship-free bars Aegis built by hand:
`backend/data/optimus/prices_2025_26/bars.parquet` (3,060 symbols, the
survivor-selected panel flagged in CLAUDE.md's survivorship-audit section)
and `backend/data/optimus/prices_deep/bars_delisted.parquet` (written by
`scripts/pull_delisted_bars.py`, the 2,433 delisted names the survivor
panel is missing). The adapter design to feed these into LEAN is already
fully scoped — `docs/research_notes/2026-09-26/research_library_expansion_and_lean.md`
§2.5 — as a `PythonData` subclass reading
`backend/data/optimus/strategy_library/top10_for_replication_<date>.json`
(the top-10-by-DSR snapshot `strategy_library.py` already writes), with
`get_source` pointed at a per-symbol CSV export of the two parquet files
above via `SubscriptionTransportMedium.LOCAL_FILE` (QuantConnect's own
documented local-custom-data recipe — no paid Dataset Market subscription
needed for this path). Estimated engineering cost per that note: ~10-14
hours (Docker pull, the `PythonData` class, the parquet→CSV export job,
the top-k + cost-model algorithm, debug).

**Why it waits.** Two independent gates, both unmet: (1) C22's own gate —
"no finalist" — there is currently no single DECIDED strategy to run a
second, independent engine against (CLAUDE.md's "explore dirty, promote
clean": a second-engine replication is a promotion-time check, not an
exploration-time one); (2) building the adapter before a finalist exists
means maintaining a ~10-14 hour integration against a strategy that may
change tomorrow. Revisit when `LIB-FWD-TWIN-1` or a `CAPITAL_CANDIDATE`
produces one.

### BLPAPI / xbbg (Bloomberg terminal PC) — `OWNER`

**Owner-only steps, in order** (roadmap §6 D11, handoff §35):
1. Confirm the Bloomberg Terminal PC has an authorized, logged-in Bloomberg
   session (not a builder action).
2. Confirm the Desktop API / BLPAPI entitlement is included in that
   licence (owner/terminal-admin question, not inferable from this repo).
3. Install the `blpapi` Python wheel **from Bloomberg's own distribution**
   (`pip install --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ blpapi`
   — Bloomberg's documented source; not PyPI's generic mirror) on the
   terminal PC itself, not this machine.
4. Decide `xbbg` (a higher-level BDP/BDH/BDS wrapper over BLPAPI) vs raw
   `blpapi` calls — `xbbg` is lower engineering cost if the entitlement
   covers its usage pattern.
5. Only after 1-4: write the read-only bridge (below).

**Desktop API licence terms on persisting data.** `UNVERIFIED` — Bloomberg's
public API/licensing pages
(`bloomberg.com/professional/support/api-library/`,
`bloomberg.com/professional/product/market-data/`) returned HTTP 403 to
both a direct fetch and the WebFetch tool when checked this session
(2026-10-07); the pages are not reachable without an authenticated
Bloomberg-side session. **Do not infer a persistence/redistribution rule
from this page** — the honest answer is "ask the terminal's licence
administrator, or pull the clause from the signed licence agreement
itself," not a web page. This is exactly why step 2 above is an owner
action, not a builder one.

**Read-only bridge design, five lines:**
1. On the terminal PC only: a small Python process holds the one `blpapi`
   session and exposes a local HTTP (or file-drop) endpoint — never
   Bloomberg credentials, never raw entitlement data, off that machine.
2. It accepts a fixed, typed request (ticker + field list from §35's
   "recommended initial data": analyst consensus/revisions, estimates,
   corporate actions, earnings calendar, news metadata) and returns a
   typed snapshot — never a raw entitlement dump.
3. Aegis (this repo, on the other machine) polls that local endpoint on a
   schedule and writes the typed snapshot into its own data directory with
   a timestamp and source tag, exactly like every other collector.
4. The bridge is READ-ONLY in both directions: no order, no write-back to
   Bloomberg, ever — it is a sensor, not a venue.
5. Nothing is persisted or redistributed beyond what step 2's licence
   review (owner action, still open) says is allowed; until that review
   happens, the bridge does not run even in prototype.

### FinRL — the reward-function guardrail

**The rule, verbatim, for any future router:** FinRL's own portfolio-
allocation environment rewards `r = Δ(portfolio value)` — raw P&L, no
benchmark subtraction, no risk adjustment — over state
`{covariance matrix, MACD, RSI, CCI, ADX}` with a softmax-weight action.
An unconditioned raw-P&L reward, trained on a mostly-rising sample, is
maximized by tilting toward the highest-beta/momentum names. That is not a
hypothetical: it is a textbook re-derivation of THE BOTTLENECK's own
diagnosis (CLAUDE.md: "all ten arena books declare `composite_top_k` over
ONE signal... 12-1 momentum") as an RL failure mode rather than a fix for
it. **The rule for the day a router gets built:** state =
`{per-book edge vector, regime flag, current portfolio weights}` exactly
as FinRL does it, but reward on **excess return over the live composite
(or equal-weight-of-books)**, never raw `Δportfolio value`. Nothing to
build today — THE BOTTLENECK itself gates a router on ≥2-3 independent
`PRODUCT_EXPERIMENT` selectors existing first, and Aegis currently has
5 fleet sources with 0 carrying forward evidence (roadmap §0 scoreboard,
"Independent selector count" row).

### TradingAgents — the leak, and what still survives it

**The confirmed look-ahead leak**, cited precisely:
`outside_methods_compared_2026-09-28.md` lines 303-313. TradingAgents'
paper reports single-name Sharpe ratios of 6.4-8.2 over a 5-month 2024
window. GitHub issue #203, "Clear look ahead bias" (opened 2025-08-17,
closed), independently verified that session, reports that replicating
the paper's own recommended backtest surfaced the agent's tool calls
pulling live/future-dated data during the "historical" simulation — a
direct, confirmed mechanism producing a BUY signal on every single day of
the test window. The issue's closure reason (fixed vs. won't-fix vs.
stale) could not be confirmed from the rendered page — flagged, not
assumed either way. This is why the verdict above is `MECHANISM_REJECTED`
for TradingAgents' core act (an LLM agent placing/approving the trade
inside the backtest loop) specifically, not a blanket dismissal of
multi-agent debate.

**Why the debate structure is still worth copying.** The leak is in
TradingAgents' DATA ACCESS during backtesting, not in the bull/bear/
risk-manager DEBATE PATTERN itself as an idea. Aegis already runs the
pattern's legitimate half: `docs/CLAUDE_LESSONS_2026-08.md`/the memory
canon's "THE REVIEW LOOP: every chunk gets an adversarial investor"
(2026-09-25, `feedback_the_review_loop_every_chunk_gets_an_adversarial_investor.md`)
and this roadmap's own §8 process ("each build is attacked by a second
Opus as an investor... before it is merged") are the same debate/veto
shape TradingAgents proposes for trade decisions, applied instead to
BUILDS and candidate signals, where an LLM's output can never itself move
money — sidestepping exactly the mechanism that produced TradingAgents'
inflated number. `outside_methods_compared_2026-09-28.md`'s own scoring
table (row "TradingAgents 82 [requested] → TOO HIGH") reaches the same
conclusion: "The debate PATTERN is worth a cheap prototype; the framework
is not."

### Microsoft Qlib / RD-Agent(Q) — one piece adopted, platform deferred

Covered in full in §2 above (RD-Agent's bandit-feeds-generation mechanism,
adopted into `hyp_lab.py`). The platform-level verdict stays `DEFERRED`:
Qlib ships no free US data and RD-Agent(Q) was validated only on
OpenAI-tier reasoning models, not DeepSeek (`outside_methods_compared_2026-09-28.md`
row scoring Qlib/RD-Agent 95-requested → "TOO HIGH," 10/100 on its own
evidence axis). Nothing further to build; the one extractable mechanism is
already in code.

### Alpaca hackathon winners' patterns — two pieces still to build

**Already adopted** (§2 above): the single hard-gate principle
(`check_limits`, refuse-or-shrink-never-enlarge).

**Still to build**, per `borrow_from_outside_2026-10-06.md` row 1's 3-line
Opus build spec — not done today, listed for the next builder session:
1. Split `check_limits()` into named gate functions in a list, each
   returning `(name, pass/refuse/shrink, reason)`, logged per-order.
2. Add `cooldown` (no re-entry on a symbol within N sessions of an exit)
   and `sector_concentration` (cap `Σ notional` per GICS sector) — gaps
   the single current gate does not check.
3. Add a scheduled `fleet_eod_audit()` DeepSeek call per account that reads
   the day's decisions + gate log and writes a critique row to the ledger,
   run automatically — not only in a human review session.

Cost: $0 licence (pattern only, no code copied — confirmed, per the borrow
note, that Autobelay's own GitHub repo 404'd on both `gh api` and WebFetch
as of 2026-10-06, so nothing was or could be copied verbatim). Engineering
cost not separately estimated in the borrow note; it is ordinary
refactor-plus-two-new-checks work inside an existing, tested module.

---

## 4. Ranking: P(changes the roadmap) × value − cost

| rank | item | P(changes roadmap) | value if it fires | cost | note |
|---|---|---|---|---|---|
| 1 | Fleet named gates + cooldown + sector cap + EOD audit | low-moderate | moderate — closes the one operational gap the hackathon loss (hack3, revoked key, unmonitored loop) actually exposed | low ($0, ~a session's refactor) | the only item here that touches live paper risk management directly |
| 2 | OpenBB MCP probe (one query, one week, throwaway venv) | low | low-moderate — may shave collector-build time for ONE Asia/non-US gap; does not add a new fact class | low ($0 licence; est. 150-400 MB disk in a separate venv, not run today) | gated only by memory headroom, not by decision difficulty |
| 3 | TradingAgents debate pattern as a cheap prototype | very low (already absorbed as the review-loop process) | none additional — the pattern is already running on builds, not trades | $0 | listed for completeness; nothing left to adopt here |
| 4 | BLPAPI read-only bridge | unknown — depends entirely on an owner decision not yet made | potentially high (consensus/revisions/estimates data Aegis cannot otherwise get) IF the licence allows persistence | unknown (terminal PC + licence; `UNVERIFIED` terms) | cannot be scored further until D11/D1 are answered |
| 5 | LEAN second-engine replication | near-zero until a finalist exists | high IF it ever disagrees with the pandas engine on a promoted strategy (catches a real bug) | ~10-14 hrs, fully scoped, $0 licence | correctly gated on "no finalist," per C22's own acceptance line |
| 6 | FinRL-shaped router | zero today | n/a | n/a | gated on ≥2-3 independent selectors existing; not a task, a guardrail for later |

**The one line that matters:** nothing on this page changes a demonstrated
result this week — RD-Agent's mechanism and the Decision Story lineage are
already-shipped code with no new forward evidence attached to them yet,
and every remaining item is gated on an owner decision, a missing
finalist, or memory headroom, not on research or engineering time.
