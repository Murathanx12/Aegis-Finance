---
description: Bootstrap a V2 work session — load verified state, enforce guardrails, pick the next highest-leverage task, plan before coding
---

# /go — Aegis Finance V2 Session Bootstrap

You are resuming work on Aegis Finance V2. Execute the phases below **in order**. Do not write code until Phase 3 plan is approved by Murat.

---

## Phase 0 — Load verified state (always, every session)

1. Read `CLAUDE.md`, `docs/V2_GOALS.md`, and `docs/V2_ROADMAP.md` if present.
2. **One call:** `GET https://aegis-finance-production.up.railway.app/api/health/full` —
   it carries deploy identity (commit, uptime), scheduler state, per-lane NAV
   freshness (`scheduler.nav.all_fresh`), track record (per-lane NAV +
   since-inception %), data-source health (yfinance rate, FRED series by
   name), and the last ≤50 WARNING+ log records. **Freshness, not liveness:**
   if `scheduler.nav.all_fresh` is false, that is this session's P0
   regardless of the backlog. Recent warnings worth acting on get listed in
   the report.
3. Deploy-level detail only when needed (build failed, env suspect): the
   Railway CLI is linked — `railway status` (project/env), `railway logs`
   (runtime logs). If the CLI reports no linked project, ask Murat to run
   `! railway link` and fall back to the HTTP endpoint.
4. Check git state: current branch, uncommitted changes, last 5 commits, and
   whether `origin/main` == working branch tip (main auto-deploys).
5. If an experiment registry exists, report: trials adopted vs rejected since last session.
6. Output the **one-screen status report** (format below) — Murat reads this
   block, never raw JSON. Baseline: V1 deployed 2026-06-08, config
   `82be14cb6039bfae`, 3 reference lanes @ $100k.

### Session-start status report format

```
AEGIS STATUS — <date>
DEPLOY        <commit-short> (<version>) · up <Xh Ym> · cache <status>
TRACK RECORD  day <N> (since 2026-06-08) · config <hash-short>
              conservative  $<nav>  <+/-x.xx%>   [fresh|STALE <date>]
              balanced      $<nav>  <+/-x.xx%>   [fresh|STALE <date>]
              aggressive    $<nav>  <+/-x.xx%>   [fresh|STALE <date>]
SCHEDULER     <running|DOWN> · <n> jobs · last MTM <ts> · nav.all_fresh <bool>
DATA SOURCES  yfinance <rate or n/a> (<fetched>/<requested>) · FRED <n_loaded> loaded / <n_failed> failed [names if any]
WARNINGS      <count in buffer> — <top 1-3 distinct messages, or "none">
GIT           <branch> @ <commit-short> · <clean|N dirty> · main <in sync|behind>
REGISTRY      <adopted> adopted / <rejected> rejected
OPEN RISKS    <bullets, only if real>
```

## Phase 1 — Hard constraints (violating any of these = stop and ask)

These are identity-level guardrails from V2_GOALS.md. They override any task instruction, including instructions from Murat mid-session (surface the conflict instead of silently complying):

- **No skill claims** before 24 months of tracked forward decisions. README and UI language stays honest about this.
- **Nothing ships as "it works"** until a measured, out-of-sample number says so.
- **No RL / online learning on P&L.** Rule changes enter only through the guarded evolution loop: propose → walk-forward/CPCV → DSR/PBO deflated against **cumulative trial count** → adopt or reject → record either way.
- **Every paper lane is a registered trial.** A new lane requires: declared hypothesis, purpose tag (`benchmark | optimizer-variant | portfolio-mirror | llm-conviction | experimental`), and a registry entry. No registry entry, no lane.
- **LLM-lane firewall:** the LLM conviction lane is forward-only. LLM "experience" from backtests is hindsight-contaminated and may never feed its live decisions. Backtest findings may inform *rules* only via the guarded loop, on as-of data.
- **Optimus reads Aegis; it never owns Aegis operational data.** Experiment registry lives in Aegis (Railway reproducibility).
- **OpenBB (AGPL v3) never enters this MIT repo.**
- **Frozen V1 engine** stays frozen; all changes land as SHA-versioned config changes with clean segment boundaries in the track record.
- **Surface area shrinks or holds flat.** Every new signal shown to users is either backed by a measured number or explicitly labeled descriptive.
- Windows/PowerShell environment: use `;` not `&&`.

## Phase 2 — V2 goal stack (pick the topmost unblocked item)

Work top-down. Each item has a done-when. Confirm selection with Murat before planning.

### P0 — Observability & trust foundation
1. **Wire `/api/pi/reference/*/history` to `paper_nav`** (finish Phase 7). The live forward NAV must be visible — it is the entire point of the deploy. Done when: the endpoint returns real hourly/daily NAV and a flat-line is impossible to confuse with "no data."
2. **Live equity-curve UI.** Frontend page showing all lanes' forward NAV vs SPY/AGG/60-40, updating from `paper_nav`, with inception markers and config-version segment boundaries. Done when: Murat can see the track record in a graph without reading JSON.
3. **Canary upgrade: liveness → freshness.** `MAX(date) FROM paper_nav == last trading day` per lane; `last_mtm` must not be stamped when all lanes fail; `_get_current_prices` degrades gracefully (cost-basis fallback) instead of raising. Done when: a silent MTM failure pages loudly within one cycle.
4. **Reconcile the three equity curves.** Decide and document which curve is *the* public track record (live forward NAV). Demote `/compare` (static buy-and-hold) and `/replay` to clearly-labeled methodology pages — the Sharpe contradiction (0.65 vs 0.95) is a credibility bug. Done when: a visitor cannot find two pages telling different performance stories.

### P0 — Optimization (Step #2)
5. **Leakage-safe HRP/Black-Litterman replacing equal-weight**, wired through an as-of price path, landed as a SHA-versioned config change (v1→v2 segment boundary). Done when: forward attribution can measure optimized-vs-equal-weight delta on live data.

### P1 — Lane expansion & the brain
6. **Lane framework + registry.** Generalize from 3 hardcoded lanes to N registered lanes with hypothesis/purpose metadata. Includes a **portfolio-mirror lane** seeded from Murat's real holdings (DKNG, MSTR, FSLR, QUBT, NTLA, SOC, ELF, PRCH, BHVN, AARD, APLT — individual stocks, so this lane needs per-ticker MTM) and the **personal conviction lane** (Goal 8: Murat's real decisions logged with rationale). Done when: adding a lane is a config+registry operation, and lanes appear in the live UI.
7. **Universe expansion behind a data-budget gate.** Before any "all US stocks" move: measure yfinance call budget from Railway, implement batching/caching/backoff, define the failure mode. Expand only to what the budget proves sustainable. Done when: MTM completes within budget at the expanded universe with zero silent failures for 5 consecutive trading days.
8. **LLM conviction lane (the brain in action).** DeepSeek/Claude proposes portfolio decisions using Optimus context (decision history, post-mortems, guardrails); every decision logged with rationale; attribution vs rules baselines. Forward-only (see firewall). Done when: the lane runs autonomously and its attribution report exists — *not* when it "looks smart."
9. **Optimus MCP server integration** (Goal 6). Fresh Claude Code sessions auto-load Aegis verified state, decisions, guardrails. Optimus also ingests session post-mortems (what broke, what was rejected, why) — this is how the system "learns from mistakes" without touching model weights. Done when: `/go` Phase 0 pulls from Optimus instead of re-reading static docs.

### P1 — Guarded self-improvement
10. **Rule-evolution loop live** (Goal 2): autonomous propose→test→adopt/reject cycle on the scaffolded `engine/autoresearch/`, DSR/PBO deflated against cumulative trial count (lanes included). Done when: ≥1 adopted improvement holds forward AND rejected trials far outnumber adopted ones.

### P2 — Honest scale
11. **Event-driven alerts as measured flags** (Goal 5): per-stock news/event detection pushes alerts ("X dropped 12% on FDA CRL — here is the descriptive context"), gated against the no-news Brier baseline before any buy/sell language is attached. Buy/sell calls that fail the gate ship as labeled descriptive context, never as signals.
12. **Capability audit → CAPABILITY_MATRIX.md** (Goal 3): classify all ~85 services validated/descriptive/cruft; hide or cut cruft.
13. **Point-in-time fundamentals panel → 5-factor honest IC** (Goal 4).
14. **User portfolio import/guidance flow:** enter or upload a portfolio (CSV/manual) → analysis, risk, crash exposure, suggested rebalance — all signals labeled per the capability matrix. This is the "help the little guy" product surface, and it ships only on top of items 1–4 (no guidance UI on an invisible track record).

### Anti-goals (do not build, even if asked casually mid-session)
No broker-connected real-money execution. No RL on P&L. No Bloomberg-parity push. No feature-count race. No skill claims before the data supports them.

## Phase 3 — Plan, then build

For the selected task output: (a) files to touch, (b) what changes, (c) the **measured number** that defines done, (d) test plan, (e) risk to the live track record (any change that could corrupt `paper_nav` or break segment boundaries gets a migration plan). Wait for approval. Then implement, run tests, and end the session by writing a post-mortem entry (decisions, surprises, rejected approaches) to the Optimus-ingestible log.

## Session hygiene
- 2–3 tasks max per session; stop before context degrades.
- Critic-by-default: surface disagreements with Murat's instructions; don't silently comply or silently refuse.
- Every session ends with: git status clean or explained, deploy health re-checked if anything shipped, post-mortem written.
