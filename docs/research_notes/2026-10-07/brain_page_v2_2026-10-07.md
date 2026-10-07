# Brain page v2: the belief state board (2026-10-07)

Licence: not applicable (a read-only presentation layer over existing
`PRODUCT_EXPERIMENT` receipts; nothing here sizes, orders or claims alpha).

Spec: `docs/design/OPTIMUS_CREATIVE_TOOL_LIBRARY_2026-10-07.md` §2 (owner brief:
"the network graph is constantly moving because nodes push each other... make them
visually appealing moving websites with motions" -- motion that MEANS something).

## What shipped

1. `backend/services/legibility.py`: `brain_payload()` -- reads
   `world_state/beliefs.json`, `world_state/scenarios.json`,
   `world_state/belief_updates_<month>.jsonl` and the newest
   `digest/world_state_<stamp>.json`, and builds the belief rows, the scenario strip
   (probability read ONLY through `world_state.scenario_probability(s, 'display')`),
   the regime block (pooled trust vs. the two baselines, plus a per-variable
   `fields` breakdown), `belief_stability`, and the newest `belief_updates` rows.
   None when no `beliefs.json` exists.
2. `backend/services/legibility_sanitise.py`: `SPEC["brain"]` -- a deny-by-default
   allow-list for the new payload, same pattern as the other four pages.
3. `backend/routers/legibility_v1.py`: `GET /api/legibility/v1/brain` (404 when no
   beliefs file; sanitised; falls back to the published copy via
   `backend/services/publish_receipts.py`, which now also publishes a `brain` kind).
4. `backend/config.py`: `LEGIBILITY_STALE_HOURS["world_state_beliefs" | "world_state_scenarios"
   | "belief_updates"]` -- each receipt is dated by its own stamp and STALE past its
   configured limit, never by file mtime.
5. `frontend/src/lib/api.ts`: `getBrainState()` + `BrainResponse`/`BeliefRow`/
   `ScenarioRow`/`BeliefUpdateRow`/`RegimeFieldRow` types.
6. `frontend/src/app/brain/StateBoard.tsx`: the SVG state board (Option A from the
   spec: plain SVG/CSS in React, zero new dependency).
7. `frontend/src/app/brain/BrainStrips.tsx`: the scenario strip, regime-row strip
   and "what changed since the last cycle" list.
8. `frontend/src/app/brain/page.tsx`: the board is now the first card below the
   hero; the health / decision-ledger / learning-digest cards are unchanged, just
   moved down, as the owner's brief and the spec §0 require.
9. Tests: `backend/tests/test_legibility_routers.py` (`_beliefs` fixture,
   `test_brain_shape_sanitiser_and_scenario_display`,
   `test_brain_missing_scenarios_and_updates_are_named_not_zeroed`, the 404 list
   extended) and `backend/tests/test_publish_receipts_c15.py` (the `world` fixture
   now builds the brain fixture too; `brain` joins the published set).

## Why not a force graph (one sentence each, per spec §2.1 / §4)

`beliefs.json` carries no "distance" between two beliefs, only a signed, lagged,
*supported* edge (`co_mention_edges`); a force layout discards the sign and the lag
and invents an unanchored settling position, and because that position has no
fixed point, every re-layout drifts -- which is the owner's complaint, correctly
produced by the simulation, applied to data that never asked for an x/y position.
The board instead computes three **fixed rings** (declared in `TOPIC_RINGS`,
`frontend/src/app/brain/StateBoard.tsx`) and a **stable hash of the topic id** for
the angle inside its ring, so the canvas is a pure function of `beliefs.json` --
deterministic across renders, across days, across users.

## Channel -> field map

| Visual channel | Field read | Where |
|---|---|---|
| Orb = one belief | `beliefs[].topic` | `BrainResponse.beliefs[]` |
| Ring (fixed) | `TOPIC_RINGS` (declared taxonomy; an unlisted topic -> outer "other" ring, never dropped) | `StateBoard.tsx` |
| Angle in ring | `hashAngleDeg(topic)` -- stable hash, not a layout pass | `StateBoard.tsx` |
| Size | `confidence` (0..1), floored so a 0-confidence belief stays clickable | `_belief_row` |
| Fill colour | `direction` (`up`/`down`/`mixed`/`none`) -> amber / blue / violet / grey (colour-blind-safe; `mixed` is its own hue, never grey) | `DIRECTION_TONE` |
| Brightness (opacity) | `mass_up + mass_down`, log-scaled | `brightnessOpacity()` |
| Hollow outline | `has_evidence === false` (`mass_up + mass_down == 0`) -- "no evidence" in the tooltip, never a placeholder dot | `_belief_row.has_evidence` |
| Dashed red ring | `contradicted` (`contradictions.length > 0`) | `_belief_row.contradicted` |
| Pulse (one-shot) | `recent_change` = `hours_since_update <= pulse_window_hours` OR `flipped_this_cycle`; gated off entirely under `prefers-reduced-motion: reduce` by a plain CSS media query | `_belief_row.recent_change`, `.aegis-brain-pulse` |
| Static "changed" badge | same `recent_change` flag, rendered unconditionally (survives motion off AND survives the one-shot animation finishing) | `StateBoard.tsx` `BeliefOrb` |
| Edge | `co_mention_edges[]` (`to`, `sign`, `lag_sessions`, `support`, `example_theme`) | `_belief_row.co_mention_edges` |
| Edge thickness | `co_mention_edges[].support` -- labelled **"co-mention support (not marginal contribution)"**; no belief-level marginal-contribution number exists yet (nearest: book-level `TRUST_AT_63` in `regret_ledger.py`, or portfolio-level MCTR in `attribution.py` -- neither is a belief-co-mention number) | `CO_MENTION_LABEL` |
| Dashed edge | `co_mention_edges[].sign === "-"` | `StateBoard.tsx` |
| Scenario bar | `scenarios[].probability_display`, read ONLY via `world_state.scenario_probability(s, 'display')` -- never the raw `prior_record.prior` or an internal smoothing state | `_scenario_row` |
| Scenario caption | `prior_version` / `prior_author` / `prior_declared_at` (`prior_record.version` / `.declared_by` / `.declared_at`) | `_scenario_row` |
| Regime marks (3 per variable) | `regime.fields[].brier_model_raw` vs `.brier_persistence` vs `.brier_base_rate` | `_regime_field_row` |
| "What changed" list | `belief_updates` (newest first), each row's `direction`/`prior_direction`/`belief_change`/`hours_since_prior`/`flipped` | `_belief_update_row` |
| Legend | static text, state-driven (only colours/markers actually present in the current snapshot are listed) | `StateBoard.tsx` aside |

## What is null today (2026-10-07, against the live `beliefs.json` / digest on disk)

- **`contradictions` is empty on all 16 live beliefs.** The dashed-ring code path
  exists and is covered by a test fixture, but has never rendered against real
  data -- the state is real in the schema, just unobserved so far.
- **`belief_stability` is `null` on the newest digest receipt.** `run_cycle` sets
  `rc["belief_stability"] = b_rc.get("stability")`, but the `UPDATED` branch of
  `update_beliefs` does not currently populate a `"stability"` key on its own
  receipt (only the early-return `ALREADY_APPLIED` branch does) -- so the field the
  code intends to carry is absent on the file actually on disk today. `brain_payload`
  reports this honestly via `missing_because.belief_stability` rather than
  inventing a number; worth a follow-up fix to `world_state.update_beliefs` in a
  separate chunk (out of scope here -- this page only reads receipts, it never
  builds one).
- **`regime.fields` is empty** on the live digest: zero regime predictions have a
  resolved outcome yet (`regime_grade.fields` only exists once rows have matured),
  so the "three marks per variable" strip currently renders its explanatory
  fallback line instead of marks. Per `CLAUDE.md`'s own rule, this "is not a
  finding before the first h5 grades."
- **The per-variable regime strip shows the GRADE, not the raw `P(event)`.** The
  spec asked for "the newest regime rows' probabilities with their two baselines."
  The actual unresolved probability for today's regime_v1 row lives only in
  `predictions.jsonl` (per-prediction rows), which is not threaded through any
  served receipt yet. What *is* already public and receipt-backed is
  `regime_grade.fields[].brier_model_raw` beside the two null Briers
  (`brier_persistence`, `brier_base_rate`) -- the model's own skill against its
  baselines on resolved rows. This board serves that honest substitute, labelled
  as a grade, not a probability; threading the raw per-row `P(event)` through a
  sanitised receipt is a follow-up, not done here.
- **`scenarios.json`'s own `probability_sealed.value` can lag the digest's
  freshly-computed scenario `current` probability by one cycle** (observed on the
  live files: `ai_capex_supercycle_2027` carried `0.4` in `scenarios.json` while
  the same-digest's `scenarios[].current` showed `0.5236`). The board reads only
  `scenarios.json` via the approved accessor, so it is honest about what it shows,
  but a reader comparing the board to the digest's own log lines may see a
  one-cycle lag; not fixed here (out of scope: this is `world_state.run_cycle`'s
  write-order, not the read side).

## Motion rules (implemented, not just declared)

- The pulse plays **once per mount**, never on a timer or a continuous loop (no
  idle "breathing" animation anywhere on the board -- that loop is exactly the
  "constantly moving" complaint restated, per spec §2.3).
- It fires **only** when the server says the belief changed this cycle
  (`recent_change`), never decoratively.
- `prefers-reduced-motion: reduce` turns the animation off via a plain CSS
  `@media` query (`StateBoard.tsx`) -- no JavaScript feature detection, so "no
  pulse" is a CSS fact that cannot drift out of sync with the browser setting.
- The *same fact* survives motion off: a small static amber ring badge marks
  `recent_change` regardless of the animation, and persists after the one-shot
  animation finishes (Fluent 2's rule, §1.4 of the spec: the reduced-motion
  fallback must carry the same information, not a slowed-down version of the
  same motion).
- The rings themselves, the orb positions and the edges never animate and never
  re-lay-out: the canvas is a pure function of the receipt, by construction.

## The sibling repo (`optimus`, `showcase/build.py`) -- NOT touched here

A ten-line spec for a later task, per the brief's instruction not to edit that
repo in this chunk:

1. Keep the same state-board RULES as this page (fixed rings, stable-hash angle,
   one-shot motion only), not a force simulation -- the complaint and the fix are
   identical in both repos.
2. Build a static layout at `showcase/build.py` time (it is a static Vercel
   export, no live backend): bake the ring/angle/size/colour computation into the
   build script in plain JS/Python, matching `StateBoard.tsx`'s formulas exactly so
   the two surfaces never visually disagree.
3. Data source: either fetch this repo's published
   `backend/data/public_receipts/brain/latest.json` at build time (same sanitised,
   already-public copy Railway serves), or call
   `GET https://aegis-finance-production.up.railway.app/api/legibility/v1/brain`
   directly -- never a second, divergent reader of `beliefs.json`.
4. Fix the two cosmetic bugs already logged against that page (legend overlapping
   the drag/zoom hint; bubbles clipped at the canvas edge) as part of the same
   pass, since the owner named both.
5. No new receipts, no new sanitiser: it reads the ALREADY-sanitised public
   copy, so nothing further needs scrubbing on that side.
6. Keep the "co-mention support (not marginal contribution)" edge label verbatim;
   it is the one place a careless rebuild would silently upgrade a count into a
   causal claim.
7. Scenario probability: display only `probability_display` -- never `prior` or
   any internal smoothing state, same rule as this page.
8. Regime strip: either omit it entirely (simplest, honest) or carry the same
   "this is a grade, not a probability" caption if reused.
9. Pulse: one-shot on `recent_change`, `prefers-reduced-motion` respected the same
   way (a static page can still read the media feature at build-irrelevant,
   client-side CSS time).
10. Re-run `opportunity_explorer_2026-10-06.md`'s showcase checklist after the
    rebuild (168-vs-~16-belief count mismatch was about a DIFFERENT, older
    all-pages graph; confirm this page's node count matches live beliefs before
    calling it fixed).

## Tests

- `backend/tests/test_legibility_routers.py`:
  `test_brain_shape_sanitiser_and_scenario_display`,
  `test_brain_missing_scenarios_and_updates_are_named_not_zeroed`, plus the 404
  loop and the poisoned `_beliefs` fixture (account-id-free, path-free, PID-free
  strings threaded through `evidence_basis`, `example_theme` and
  `regime_grade.note` to prove the sanitiser still scrubs them on this new kind).
- `backend/tests/test_publish_receipts_c15.py`: the `world` fixture now builds the
  brain fixture; `brain` joins the published set end to end (sanitised, fixed
  point of the sanitiser, leak-scanned).
- `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest
  backend/tests/test_legibility_routers.py backend/tests/test_publish_receipts_c15.py -q`
  -- 38 passed.
- `cd frontend && npx tsc --noEmit` -- clean.
- `cd frontend && npx eslint src/app/brain/page.tsx src/app/brain/StateBoard.tsx
  src/app/brain/BrainStrips.tsx src/lib/api.ts` -- clean.
