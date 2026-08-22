# ADJUDICATION 2026-08-22 — External review (GPT) → ORDER 27

An external review is **adjudicated, never imported**. This doc records what the
2026-08-22 GPT review of `c5e8ad6` gets right, what it gets wrong, and what
Aegis actually does about each point. Verdicts: **ACCEPT** (build now),
**ACCEPT-DEFERRED** (right, but gated/sequenced), **MODIFY** (right direction,
wrong mechanism), **REJECT** (with reasons).

## Facts the review got wrong or stale

- "The Arena's first seeded pass was killed and Friday is lost" — **stale**.
  The 18:45 ET catch-up retry (shipped the same night, `171e758`) completed the
  pass at 22:45:43 UTC: 10/10 books have their first NAV row (2026-08-21),
  151 experiences accrued. Friday was NOT lost.
- "I would not claim the pull is presently alive" — correct caution, resolved
  by measurement: pass 3 finished (837 tables, 46.2 GB), pass 4 launched
  2026-08-22 ~11:05 HKT against the ~112 NETWORK_DNS failures.
- "prereg conveniently allowed ≤12.5%" — the FP bar was declared **before**
  the battery ran (pre-register-trial discipline). It was not fit to the
  result. Tightening it is legitimate — forward-only, for the next router
  version (see G1 hardening below).

## Verdicts

### P0 — Production survival (memory) — **ACCEPT, build now**
The 3,663 MB prewarm spike at uptime ~8 min is measured, reproducible, and the
best explanation of the 4-restart loop. Retries are insurance, not the fix —
agreed. Actions tonight: FinBERT lazy-load out of prewarm; serialize the
prewarm sequence; single heavy-work semaphore so a scheduler job and a heavy
load cannot stack; memory high-water receipt in `/api/health/full`.
The full api/worker **process split is ACCEPT-DEFERRED**: on Railway that means
a second service (cost + ops), which is Murat's call; a design note names the
split as the architectural fix if the in-process mitigation is insufficient.

### Signature/receipt integrity for every scheduled job — **ACCEPT, build now**
Generalizes the `why_moved` lesson: every `EXPECTED_JOB_ID` wrapper gets a
signature-binding invocation test. Receipts (last_attempt/last_success/rows)
partially exist via job-status surfaces; gaps get filled as they're touched.

### P1 — WRDS — **ACCEPT** (matches existing stance)
No global `MAX_ROWS` raise. Rule adopted verbatim because it is correct and
matches the catalogue-is-not-entitlement canon: **large tables earn partitioned
ingestion through a named consumer; they do not earn ingestion by existing.**
`wrds_verify_substrate` remains the gate before any training.

### P2 — G1 hardening — **ACCEPT-DEFERRED (gate, not tonight)**
All four criticisms are right: 40/20/20 worlds is thin (0/20 harmful leaks
bounds the true rate only to ≲15% at 95% by rule of three — quote the cost
rate or don't quote the count); cross-name/same-day correlation is untreated;
economic damage (capital exposed in null worlds) is the metric the user pays
for, not verdict rate. **Gate declared:** RELIABILITY_ROUTER gains no capital
authority beyond v1's aggression knob until a correlated-worlds battery
(hundreds of worlds, clustered by decision date, correlated names, regime
blocks) passes at ≤5% null recommendation AND reports null-world capital
exposure. Battery v2 is next-session work; the declared v1 bars stand for v1.

### P3 — PROFIT_ALLOCATOR_v2 — **ACCEPT-DEFERRED (blocked on substrate)**
Every listed flaw of v1 is real: fixed IC_PRIOR=0.05 is aggressive against our
own evidence (return nonstationary, risk stationary); no covariance, no joint
optimization, no cost term, no marginal opportunity-cost. v1 stays FROZEN as
the clean baseline. v2 requires shrunk OOS expected-return estimates — which
requires the WRDS-verified substrate → return/risk forecast layer first. The
"competing uses of capital" framing (cash/SPY/incumbents as named opponents)
is adopted as v2's design spine. Covariance baseline: shrinkage/factor, not
fancy (graph-covariance corpse agrees).

### P4 — Executable-edge shadow engine — **MODIFY: split in two**
The critique is correct: `|mid_K − mid_P| > 5¢` is price disagreement, not
arbitrage. TRIAL-PREDMARKET-2 is FROZEN and unchanged — its mid-divergence
metric remains the deciding metric of that trial. **Tonight** we add a
*reported-never-deciding* executable-edge computation beside it: bid/ask-based
locked-profit after venue fees (Kalshi `0.07·C·P·(1−P)` general taker formula;
Polymarket category taker rates; makers 0), plus capital-lock-aware annualized
ROIC using time-to-resolution. **Streaming** (WebSocket depth on selected
contracts) is ACCEPT-DEFERRED — it is a persistent-process infrastructure
commitment that needs a home (Railway worker vs local daemon) and a design
note, not a Saturday-night bolt-on.
**Ground-4 correction adopted:** R1's 6/6 LLM losses are evidence about
LLM *directional forecasting* on Kalshi, not about structural arbitrage. The
2026-08-21 adjudication's rejection of *live execution* stands on the other
three grounds (no execution path; fee economics; daily cadence) — amended in
place as an annotation, not a rewrite.

### P5 — EVENT_PROBABILITY_SURFACE_v1 — **ACCEPT, seed tonight**
Model-free coherence checks (complement, mutually-exclusive basket sum,
threshold monotonicity, calendar monotonicity, cross-venue consistency) on the
daily snapshots. Cheap, uses data we already collect, and doubles as a clean
market-implied distribution extractor. Statistical-unit rule adopted: **one
underlying event = one unit** (a Fed meeting is one multinomial, not five
binaries) — this is the same class of error G1 just caught on horizons.

### P6/P7 — EVENT_PROBABILITY_ENGINE / EVENT_IMPACT_MATRIX — **ACCEPT-DEFERRED**
The bridge `Σ P(outcome)·E[R|outcome, regime]` is the right path by which
prediction markets reach capital, and the correct order is surface → impact
matrix → posterior engine. Each enters through pre-register-trial (corpse
check first). Needs ALFRED vintages for the macro legs. Not tonight.

### P8 — Information diffusion — **ACCEPT-DEFERRED, correction adopted**
Daily snapshots cannot see diffusion; intraday timestamps are the substrate.
Event-study/lead-lag/Hawkes baselines BEFORE any GNN — adopted. Explicitly
noted: the graph-covariance corpse does not bar a *directed temporal
propagation* graph (different question). Corpse-check DIFFUSION-LEADLAG-1
before registering. Sequenced behind WRDS Q1 + streaming design.

### P9 — Alpha diversity — **ACCEPT (the strongest point)**
`distinct_selection_signals: 1` is on our own status surface. Ten treatments
of one selector is the bottleneck now that grading works. New books (EVENT,
REVISIONS after IBES lands, QUALITY/COMPOUNDER via Piotroski/fundamentals,
RELATIVE_VALUE) are the top build priority after substrate verify. Each is a
new frozen YAML book, never an edit of an existing one.

### P10 — Data expansion — **ACCEPT the rule, not the shopping list**
"No source becomes production data merely because an API exists; every source
needs timestamp semantics and a named consumer" — adopted verbatim (it *is*
our silent-fragility rule). Sources get pulled in the order their named
consumers (P9 books, P7 matrix) come up, not en masse.

### P11 — Branch protection + product audit — **ACCEPT**
Main unprotected is inconsistent with push-deploys-a-product. Action: require
the CI test check on main (attempt via `gh api`; if the plan forbids it, it
goes on Murat's attended queue). Daily product audit largely exists across
health/full + digest; gaps (restart counter, memory high-water) added with P0.

### Personality naming (CRRA=1 = log utility) — **MODIFY**
The observation is correct: rho=1 *is* log/Kelly, and "extreme growth" is a
misnomer for it. But the declared rhos are FROZEN (declared at zero NAV rows,
pinned by test) — renaming now would be retroactive tampering. Action:
**annotation** in the personality read output ("rho=1.0 = log utility, the
Kelly growth-optimal objective"), and any MAX_EXPECTED_TERMINAL_WEALTH
objective (with ruin constraints) enters as a NEW declared personality,
forward-only.

## Order 27 (adjudicated form)

Tonight: P0 memory + job-signature tests + executable-edge (reported) +
surface coherence v0 + branch protection attempt.
Next sessions, in order: G1 correlated battery → substrate verify → return/risk
layer → new alpha books (P9) → PROFIT_ALLOCATOR_v2 → impact matrix →
streaming design note → diffusion baselines.
