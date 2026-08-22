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

**3. Detectability FIRST, registration SECOND.** Run the planted worlds
at panel-2 scale (port the `--planted-world` machinery from
`scripts/return_panel_tournament_run.py`; the `linear_hetero` world is
required by name — it is the world that refuted the z-label variant).
Then the gate:

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

**6. ORDER 27 carry-overs still open:** G1 correlated-worlds battery
(before any router capital authority) · EVENT_IMPACT bridge ·
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
