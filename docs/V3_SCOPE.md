# Aegis Finance — V3 Scope (the v2→v3 pivot boundary)

_Dated 2026-06-14. Written at the v2→v3 transition: v2's buildable scope is complete
except the one remaining write-path item (P1 #6 lane seeding, plan ready, fresh
session). This doc draws the boundary v3 must respect._

## What Aegis is (the thesis, restated)

An honest, open-source, retail-protective market-analysis engine with a
**forward-measured** track record, a **guarded** self-improvement loop, a private
**process-memory** brain (Optimus), and an **experiment registry**. The bet:
*proven honesty beats claimed performance.* Differentiator confirmed by the
2026-06-14 research — nobody else publishes a forward track record alongside a
rejected-trial registry.

## What's built and solid (end of v2)

Observability + canaries (freshness/overlay/lppls, all honest-when-dark) ·
leakage-safe optimization (HRP, config v2) · fragility composite (descriptive,
never-arms) + macro lane (SOS+Sahm) · the guarded evolution loop with a deflation
guard that **provably bites** (+ null-candidate guard) · Optimus MCP · conviction
decision capture (immutable log + endpoint + CLI) · **un-hangable offline test
suite** (network-blocked, hard timeout — the 2.5h-hang class is dead).

## The governing boundary for v3 (non-negotiable)

**The engine learns continuously NOW** (the loop evolves rules; lanes accrue forward
NAV; Optimus ingests process). **But no skill claim ships before the forward clock
matures (24 months).** v3 builds *capability and surface*; it does **not** compress
the proof. Everything new ships measured-or-labeled-descriptive, same as v2.

## V3 backlog

### (a) The as-of data layer — Phase B  ← single highest-leverage unlock
Point-in-time, leakage-safe data so the evolution loop can evolve **stock-level**
rules, not just broad-ETF/macro params:
- **Insider Form-4 opportunistic** (the one durable edge the research found:
  ~82 bps/mo; routine filings ~0 — must filter opportunistic vs routine).
- **Point-in-time fundamentals** (as-of filing dates, no restatement leakage).
- **As-of S&P constituents + delisted-ticker prices** (kills survivorship bias —
  the constraint that currently caps the loop at portfolio-level params).
- *Honest gate:* SEC EDGAR (13F/Form-4) has real filing timestamps back to ~2001
  (free, the gold); news/GDELT only ~2015+. Build to what the data supports.
- *Discipline:* wider training surface inflates the trial count → **T2's
  effective-N is what keeps it honest. Train wider, deflate harder.**

### (b) The product surface for the "little guy"  ← turns engine into a tool people use
The end-state: *a user enters a portfolio, Aegis guides it.* Portfolio import
(CSV/manual) → plain-language risk / crash-exposure read → labeled signals (per the
capability matrix) → suggested rebalance. Ships only on top of the visible track
record (done) and the capability matrix (below). UI-heavy phase — do the deferred
**full-stack visual/browser integrity audit** here (code+API verified 2026-06-14;
pixel render deferred).

### (c) Capability audit — Goal 3  ← "smaller and sharper", subtract before adding
`docs/CAPABILITY_MATRIX.md`: classify all ~85 services validated / descriptive /
cruft with one-line evidence each; hide or cut cruft. The V2 promise of "smaller and
sharper" is unfinished; do this *before* (b) adds surface.

### (d) Fragility inputs the research flagged as immediate-build
VIX term structure (backwardation) as an active composite input (HY/IG OAS already
active); options put-skew; IPO-issuance once a free point-in-time source is sourced
(Murat's post-IPO-glut hypothesis feature — enters as a *tested* candidate, never asserted).

### Optimus deepening (stretch)
Today Optimus *stores* process. The research surfaced hindsight-firewall-respecting
agent-memory architectures (Hindsight's fact-vs-belief split, traceable Reflect) that
could let it *actively propose* from past postmortems, not just retrieve — within the
firewall (process only, never backtest P&L).

## V3 P0 hygiene (the standing proposals — clear these first)
1. **Chunk 2 batch orchestrator** (evolution loop over *binding* Phase-A params; the
   loop core is ready; pick binding params, add nested-param deep-merge).
2. **rules.py pct_change config-migration** — a deliberate config-versioned session
   (it changes HRP weights → segment boundary). Parked; never a drive-by fix.
3. **pytest-xdist** — parallelize the ~14-min offline suite toward a true ~4-min gate.

## Carried over from v2 (the last buildable v2 item)
**P1 #6 lane seeding** — mirror (TRIAL-002) + conviction (TRIAL-003) lanes from
Murat's confirmed 12-name book, inception TODAY at current prices. Plan + trials
pre-registered (`docs/P1-6-LANE-FRAMEWORK-PLAN.md`, `docs/TRIALS/TRIAL-00{2,3}*`).
Fresh focused session, Step-#2 write-path care.
