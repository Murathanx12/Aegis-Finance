# HANDOFF 2026-08-22 → next builder session (Opus)

Written at the end of Saturday 2026-08-22 (two parallel sessions + the
paused pull). Read order for a cold start: this file →
`docs/ROADMAP_POSITION_2026-08-22.md` (position + addendum + pause state) →
`docs/DESIGN_REVIEW_2026-08-22_NEWS_ENGINE_AND_RULES.md` (rules audit +
ORDER 29 candidate, awaiting Murat's read). Start the session with
`session_briefing()` + `aegis_verified_state()`; **`brain_query` is broken
server-side** (path-repetition bug in the aegis-health page name — fix
lives in the optimus repo; fall back to `aegis_canon` /
`aegis_postmortems` / `aegis_registry`).

## STATE SNAPSHOT (verified, not assumed)

- **HEAD `b401b1e`** (main, pushed). Prod deployed and live-verified at
  `bdf02fc` (commit flip confirmed, `nav.all_fresh: true`,
  `pi_why_moved` next-run moved 08-22T17:15 → 08-24T17:15 ET — the
  day-guard demonstrably took effect; b401b1e/8fa6b57 are docs+puller
  only and deploy no new surface).
- **Fast suite 5,322 passed / 0 failed** (2026-08-22 evening, +19 over
  the morning's 5,303). `pytest_timeout` verified importable.
- **JKP pulls PAUSED BY MURAT at 16/45 chunks** (USA complete through
  1980-81; foreign subset not started). Resume ONLY on his word — he said
  "when I go back I will ask you to continue". Resume commands and pace
  are in the position doc's IN FLIGHT section (foreign ~1 h, USA ~6 h;
  chunk filenames are the resume key; nothing partial survives a kill).
- **`aegis_panel2_build.py` REFUSES until every declared chunk is on
  disk** — nothing can accidentally build over the hole.
- Standing DEGRADED on health: prediction-ledger quarantine (25 overdue
  campaign copies, attended). Pre-existing, not tonight's problem.
- The working tree is shared between concurrent sessions on this machine.
  `lab/*.py` carries months-old UNCOMMITTED v5 modifications — leave them
  uncommitted pending the rd_loop retirement decision (design review §2);
  check `git status` before any stash.

## WHAT TODAY PRODUCED (receipts committed; compressed)

**Day session (`ab30b8e`..`0412e12`, `72cd95c`):** ORDER 28 adjudicated ·
TRAINING_SUBSTRATE_V1 receipt (857 files clean, 129 consumed files
hashed) · AEGIS-PANEL-1 (230,640 × 419, PIT-audited, corr 0.99987 vs JKP
lead) · RETURN-PANEL-TOURNAMENT-1 **NOT_ESTABLISHED** (dIC −0.0025, MDE
0.021) · sensitivity worlds: **instrument BLIND below planted IC 0.03** ·
RISK-PRICE-EARLY-1: early era tight zero, modern cell +0.0299 — the ERA
is the difference, same-era foreign confirm licensed · 3 silent-wrong
fixes · panel-2 builder shipped.

**Evening session (`bdf02fc`):** planted-world **detectability gate
enforced as code** (`backend/services/detectability_gate.py`) ·
`pi_why_moved` mon-fri + 17:15/18:15/19:15 catch-up slots, idempotent via
`skip_if_minted` · **belief-state schema 1.3.0** adds `session_as_of`
(the session a record is ABOUT vs `made_at` = when written) · design
review + rules audit written · deploy live-verified.

**Pull session (`8fa6b57`, `b401b1e`):** `--foreign-only`/`--usa-only`
split so the cheap 13-country subset can land first · pause state
recorded.

## BUILD QUEUE (ordered; each step's gate stated)

**0. Resume the pulls — on Murat's word only.** Two detached loops (see
position doc). Foreign lands in ~1 h and unblocks step 5 independently of
the overnight USA history.

**1. Verify the chunks as they land.** Row sanity per chunk, no at-cap
fills, meta audit (each meta carries its named consumer). Then extend the
substrate receipt to **v1.1** with the new families — the claim stays
scoped to consumed inputs, never "all WRDS data".

**2. Build AEGIS-PANEL-2.** `python -m scripts.aegis_panel2_build`
(audit-print) then `--write`. Expect ~3M stock-months, all-cap,
1926/1963–2024, delistings compounded; duplicates refuse. Floor features
recomputed full-history. **Dimson-adjusted betas are REQUIRED before any
all-cap use of the own-construction risk family** — attenuation is
measured (fully-traded median 0.845 vs 0.118 with ≥10 zero-trade days),
not hypothetical.

**3. Detectability FIRST, registration SECOND. — DONE 2026-08-23,
`docs/PANEL2_DETECTABILITY_2026-08-23.md` (`e1bf6cb`).** All three worlds
run at panel-2 scale; receipts in
`backend/data/optimus/aegis_panel/panel2_detectability/`, panel hash
`2812090a3ecbd1f5`, instrument hash `d58b6d0310008713`.

**Every panel-1 world's best arm contained zero; every panel-2 world's
excludes it.** Sparse recovers 45.4%, dense and hetero 12.6%. **The gate
reduces to one declared number: PASS iff `min_recovery ≤ 0.126`** — and
that number must NOT be picked because it passes. Declare it from what a
null must rule out (bound ≈ MDE/recovery): a sparse null bounds the truth
at 0.011 (the economic bar), a diffuse null at 0.042 (4× the bar).

**The z-label finding, which panel-1 could not reach:** per-date
z-scoring maps the hetero world EXACTLY onto the dense one (bit-identical
across all 18 fold series — the hetero label's `sd_month` divides out), so
all of the hetero world's extra difficulty is the TRAINING OBJECTIVE, not
the data. Recovery 4.8% → 12.6%, interval off zero. Panel-1 measured
+0.00008 here; its 2013+ window was too short.

**Before registering, do (a):** panel-1's best arm in BOTH dense worlds
was `full_ridge`, and no ridge fits beside a 6.9 GB panel in float64 on
this machine — so panel-2's best-of-arms is a CONSERVATIVE FLOOR in
exactly the diffuse worlds that matter. A memory-feasible linear arm
(ridge via a 412×412 Gram matrix accumulated in chunks) is the
highest-value work before TOURNAMENT-2. Also note the panel-2 price floor
is now declared and frozen (`backend/services/aegis_panel2_spec.py`) —
**the prereg must CITE `spec_hash d58b6d0310008713`, not restate the set.**

The gate call, unchanged:

```python
from backend.services.detectability_gate import assert_detectable
assert_detectable(receipt_dir, panel_hash=<panel-2 hash>,
                  declared_ic=<prereg's number>,
                  min_recovery=<prereg's number>)
```

`declared_ic`/`min_recovery` have **no defaults by design** — the
TOURNAMENT-2 prereg declares them. The gate refuses on missing receipts,
foreign panel_hash (panel-1 evidence licenses nothing about panel-2),
planted > declared, or failed recovery (best full_* arm mean ≥
min_recovery × planted AND ci_lo > 0, per world). A live pin test asserts
the panel-1 receipts FAIL at their own hash — **do not "fix" that test;
if it ever passes, the gate has inverted.**

**4. RETURN-PANEL-TOURNAMENT-2.** Only after the gate passes: prereg
linted against the registry, null world run FIRST, §64 power audit on the
exact declared cell under the trial's own dependence structure
(block unit derived from panel spacing, §58 date blocks), every verdict
literal asserted reachable, SIGNED, then the registered run — whose
runner calls `assert_detectable` as its opening act.

**5. RISK-PRICE-FOREIGN-CONFIRM-1.** After foreign chunks verify: prereg
for the 13-market, same-era (2013–2024) cross-sectional confirm of the
modern RISK_PRICE lead. §64 from the MEASURED foreign n, never assumed.
Corpse-check lineage first: RISK-PRICE-EARLY-1 (era-transfer refuted),
ORDER 24 era-transfer receipts. This is the licensed follow-up — never
another US backtest.

**6. ORDER 27 carry-overs still open:** ~~G1 correlated-worlds battery~~
**DONE 2026-08-23 — `docs/ORDER_27_P2_ROUTER_CAPITAL_GATE_2026-08-23.md`.**
The gate is built and enforced; the live router **FAILS** it (29% null
recommendation, 100% capital exposure behind it) and is not licensed. The
corrected v1.1 estimator holds 3.0% out-of-sample but has no power at the
arena's current breadth (recovery 0.19 at 16 decision days; the 70% crossing
is 32–64 days ≈ six months of live arena). **ATTENDED: flip
`trust_router.CLUSTER_ADJUST_DEFAULT` to True** — recommended; it moves a
live book's sizing, which is why a session did not take it.
· EVENT_IMPACT bridge ·
PROFIT_ALLOCATOR_v2 (gated on true OOS forecasts) · P9 alpha-diversity
books (gated on a surviving signal — none yet). The why_moved item is
**DONE** (this evening).

**7. ORDER 29 (news engine) — do NOT start unattended.** The design
review is the candidate order; collectors touching prod scheduling and
LLM spend need Murat's adjudication. When adjudicated, the build order
(a)→(f) in design review §3 ships one step at a time, event store first,
LLM spend entering only at step (e).

## ATTENDED QUEUE (Murat's keyboard, unchanged + new)

Resume-the-pulls word · prediction-ledger quarantine disposition ·
crash-overlay retrain-vs-disarm (recommendation: retrain as a named
panel consumer) · design-review rules amendments (CLAUDE.md scope of
"no database", staleness pass, lab/rd_loop retirement, product-surface
labels) · ORDER 29 verdict · 08-27 resolve run · G2 signatures before
09-08 · the older queue in the position doc §7.

## TRAPS THE NEXT SESSION WILL HIT (paid-for, this week)

- Background shells die at ~10 min: any long pull/compute must be a
  detached loop of ≤480 s invocations that is resumable by filename.
- PS 5.1 mangles embedded quotes in native args → `git commit -F file`.
- A new `*Error`/`*Refused` in `backend/services/` must be enrolled or
  exempted in `backend/tests/guard_contract.py` the same commit, or CI
  goes red (the contract caught its own author twice this week).
- Receipts stamped `SENSITIVITY_WORLD` are never market evidence; the
  null-world gate and the signature gate on the tournament runner are
  separate from the new detectability gate — all three must hold.
- STATISTICAL_MDE_80 ≠ DECISION_MDE_80; preregs quote both.
- CI repro = clean worktree + CI's env (`AEGIS_IIF1_PREREG_ABSENT_OK=1`);
  the live checkout masks failures in both directions.
- Verify prod after every deploying push (skill exists); green tests are
  not a live verification.
- 2026-08-22 is a SATURDAY; NAV expected date on weekends is Friday's.
  Weekend firings that walk back to Friday must be idempotent — that is
  what `session_as_of` (schema 1.3.0) now exists to answer.


---

## SUNDAY 2026-08-23 UPDATE (appended by the pull-completion session)

**The pull finished and both consumers are fed.** Census
(`jkp_full/pull_census_2026-08-23.json`): USA 32 chunks / 3,599,311 rows
(1926-2012) + foreign 13 chunks / 2,384,261 rows = 6.3 GB, zero at-cap
fills, loops exited cleanly.

**RISK-PRICE-FOREIGN-1 ran REGISTERED and returned the programme's first
positive family result: `NOT_US_ONLY`** (+0.0215 cross-country dIC vs
MDE 0.0183 and the 0.01 bar; 12/13 markets, 7/9 years; measured rho 0.27
=> 3.07 effective markets). Context cell: the price FLOOR alone carries
+0.023 IC abroad in the era where the US floor is zero - modern US
large-caps are the crowded anomaly. The linter downgraded the trial from
CONFIRM to FOREIGN grade pre-run (N9: same-era foreign co-moves; an
era-bound claim confirms FORWARD only). **It licenses exactly ONE
forward registration** - recommended: a new-ID arena book on the
risk-price family (also P9's second distinct selection signal). That
registration is the next session's first decision.

**AEGIS-PANEL-2 is BUILT**: `aegis_panel/aegis_panel_v2.parquet` -
4,157,680 stock-months, 1,188 months (1926-01..2024-12), 28,159 permnos,
4,053,138 labeled (JKP ret_exc_lead1m), 4.18 GB, all columns
family-mapped, family coverage 63-89%. Label is float64, features
float32 (memory: the build peaked ~16 GB). **TOURNAMENT-2 remains behind
the enforced detectability gate** (`detectability_gate.assert_detectable`
- the T2 runner must show planted-world recovery at panel-2 hash and its
declared effect BEFORE any registered read counts).

**Next session order (updated):** (1) risk-price forward registration
decision (the licensed one); (2) planted worlds on panel-2 + declare
detectability bars; (3) TOURNAMENT-2 prereg + run; (4) session-(b)
attended item stands: flip `trust_router.CLUSTER_ADJUST_DEFAULT` -> True
(the capital gate refuses the v1.1 receipt while off); (5) ORDER 29
(event engine) awaits Murat's read of the design review.
