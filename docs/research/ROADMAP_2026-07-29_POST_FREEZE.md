# Post-freeze roadmap — the reasoning engine, verified or dead (2026-07-29)

**Written by the build session (Fable), executing `FABLE_HANDOFF_2026-07-29.md`.**
The freeze (`Aegis module/docs/FREEZE_2026-07-28.md`, 158 candidates) is in force:
no new cross-sectional searches. Everything below is diagnostics on existing data,
infrastructure hardening, or explicitly-attended items awaiting Murat.

---

## The strategic picture (one paragraph)

The cross-sectional signal search converged and closed at 158 candidates — the
deliverable there is the paper (method + empty-cost-cohort + contrarian-t
exhibit). What remains open is the **allocation/reasoning layer**: the
INSTR-REGIME-ANALOG belief engine (phase 1 live, 283 belief states) and the
running forward clocks. The research round found the belief engine has two
unmeasured structural defects and has never been graded. The build order is
therefore *diagnose before build* — three kill-first diagnostics, each able to
end the engine, all runnable on data already on disk. An engine that survives
them is worth building phase 2 on; one that doesn't gets redesigned at lower
dimension / longer exclusion, honestly.

## Track A — the belief engine (THIS SESSION)

| Step | What | Kill line (pre-committed) | Status |
|---|---|---|---|
| D1 | Analog age distribution, all 283 states | >40% of analogs within 12mo of query ⇒ engine measures autocorrelation ⇒ raise self-exclusion to ±24mo and re-run downstream | **DID NOT FIRE** — ≤12m share 10.78%, median analog age 4.93y; red-team distance-doubling did not reproduce at real spec (1.13×, not 2.06×); 63-td/504-td Jaccard 0.676 |
| D2 | Effective dimension (PCA on 15 descriptors) | D_A ≥ 5 at 90% variance ⇒ 15-D retrieval under-supported ⇒ 2–3-PC version is the honest engine | **FIRED** — D_A(90%)=9. But the remedy does NOT follow: 2–3-PC retrieval changes ~90% of analogs yet moves state_probs by only 0.02–0.05, because published beliefs sit within ~0.06–0.13 of unconditional base rates — retrieval is near-no-op on the output. Resolution (D3) is the deciding question. Also found: 56/283 early states silently accepted <50 analogs (min 4) — guard checks candidates, not acceptances |
| D3 | Causal restandardisation (expanding-window median/IQR — the backfill's full-sample z is not scoreable) + score vs **persistence** via paired DM on Brier diffs, N_eff, REL/RES/UNC | Expect INCONCLUSIVE at N_eff≈23 — report it, never metric-shop | **RUN, both specs.** At the honest 504-td spec (standardization AND outcome aggregation causal): fwd6m BEATS persistence (DM t −2.31/−2.20, N_eff 54.9) but 87.6% of the win is ΔREL (hedging vs a 0/1 baseline); fwd12m/dd15/dd20 INCONCLUSIVE. Engine RES/UNC = 10/29/16/13% — mostly a hedged base-rate emitter. The 63-td run's dd15/dd20 "wins" were carried by the outcome-aggregation leak (analog forward windows overlapping the query's future). Contamination from full-sample z was real but not load-bearing (no verdict changed). 43 early states unscoreable under burn-in; 56 pre-2008 states had silently accepted <50 analogs |
| D4 | Confidence channel (only if D1–D3 survive) | purged corr(distance, \|error\|) < 0.15 ⇒ abstention is decoration; delete | **RUN at 504-td:** corr = 0.104 / 0.063 (return-sign outcomes — CHANNEL ABSENT) vs 0.204 / 0.259 (crash outcomes — plausibly present). No monotone confidence→resolution pattern across terciles. Verdict: keep abstention only for drawdown-flavored surfaces, and only descriptively |

Binding rules (from the handoff, R1–R12): persistence baseline never climatology;
DM-on-Brier-differences deciding, BSS descriptive only; resolution is the payable
part; N_eff + block bootstrap before any claim; no phase-randomised regime
labels; ChronoBERT-class checkpoints for any historical text; extraction
validated by error-outcome covariance, not fidelity; nothing is PIT "by
construction"; every component ships with a named simpler baseline; fallback
triggers name their control at registration; no math quoted from PDFs without
glyph verification.

## Track B — Optimus hardening (THIS SESSION, independent)

1. Distance floor + explicit `no_match` abstention in `brain_query` (same
   primitive as D4's abstention — built once).
2. Domain scoping (robotics/ancestor corpora must not outrank the live program).
3. Re-ingest at HEAD + a re-ingest-after-each-round note. Structured tools
   (`aegis_registry`, `aegis_canon`, `aegis_verified_state`, `aegis_postmortems`)
   are good — unchanged.

## Track C — 🔴 ATTENDED (Murat's calls, not a session's)

1. **Conditional volatility targeting — RULED & REGISTERED 2026-07-29.** Murat
   delegated the call; ruling: de-risking overlay = S3 open door, same registry,
   same cumulative deflation count; registration mandatory (external "skip
   pre-registration" advice refused). TRIAL-COND-VT frozen BEFORE any run:
   63-td realized vol (not VIX — PIT-clean, matches Bongaerts conditioning;
   VIX variant refused as a second hypothesis), causal expanding quintiles,
   de-risk only ≥80th pct, leverage cap 1.0, month-end, 2 bps; explore
   2004-2018 → confirm 2019-2024 one shot; controls SPY B&H + static 60/40 +
   unconditional-VT contrast arm. Results: see
   `Aegis module/TRIALS/TRIAL-COND-VT.md` + AI_PANEL_2026-07-29.md.
   **RESULT: explore PASS (all 3 bars, carried by 2008, ΔmaxDD +15.0pp) →
   confirm 2019-2024 REJECT (Sharpe −0.011 under bar; maxDD identical to SPY
   to 4dp — trailing 63d vol was at its calmest going into the 23-day 2020
   crash, so the overlay entered March at full weight). Family CLOSED; third
   allocation instrument killed by the wall after JM/JM2, same
   explore-passes-confirm-fails signature. Unconditional-VT contrast arm beat
   the conditional arm in both windows but also fails the bar (dead family
   stands). NEGATIVE_RESULTS §21.** The paper experiment landed: first
   held-out post-2010 refutation of the conditional variant, named mechanism
   (a backward vol window cannot resolve a fast crash from a calm base).
2. Unset stale seed flags (`AEGIS_SEED_*`) on Railway (long-standing TODO).
3. PDUFA ledger first scoring ~late Aug; quarterly panel refresh ~Oct.

## What is DEAD (do not rebuild; receipts in ALLOCATION_EVIDENCE / REDTEAM_ENGINE)

- Continuous/unconditional vol targeting (4 independent refutations).
- Knowledge graph of supplier-customer-competitor links (our own edges: ~zero).
- LLM as return predictor over historical text (permanently forward-only).
- "Allocation layer has a cheap deflation budget" (budget = hypotheses ÷ N_eff;
  confirm window holds ~1–2 regime events).
- Swapping brain_query to a vector DB / graph store (defect is abstention+scope).
- Phase-randomisation controls on discrete regime labels.

## Product track (unchanged priorities, not this session's mandate)

The user-facing goal — news arrives → engine says what it may mean for the
market/stock — is served by the belief engine *if it survives diagnostics*
(states + analogs + forward distributions are exactly that surface, honestly
labeled estimates-not-forecasts). The daily brief, screener, and news
intelligence stack stay descriptive per TRACK_RECORD_POLICY. No new product
surface ships from this session; diagnostics decide what the brain is allowed
to say.

## Session results (2026-07-29, filled at session end)

**The engine's verdict, in one sentence:** the analog belief engine retrieves
genuinely old analogs (D1 clean) but emits hedged base-rate probabilities —
REL > RES on all four outcomes, so a constant forecast at the base rate
strictly beats it — and **phase 2 (any allocation layer on these belief
states) is BLOCKED on the evidence.**

- All D1–D4 numbers independently re-verified by an adversarial recompute
  (every deciding number exact; 3 report-prose defects found and corrected —
  including one that understated the negative finding in the engine's favor).
- The lone surviving DM win (fwd6m, t −2.31) is 87.6% hedging and fragile to
  bootstrap block length; honest read = no demonstrated information content.
- New reusable assets: `causal_standardize.py` (expanding-window robust z,
  causality test-pinned) and the D3 scoring harness (persistence baseline, DM
  + NW + block bootstrap, N_eff, Murphy decomposition) — this is now the house
  ruler for ANY probabilistic forecaster, including a crash-model successor.
- Engine defect for any successor: `retrieve_analogs` guards candidate count,
  not acceptance count — GFC-era states silently used as few as 3 analogs.
- **Optimus track: DONE** (floor 20.0 + `no_match` abstention, domain scoping
  with hard/soft semantics, whole-word matching, 97 tests green, corpus
  re-ingested at HEAD incl. the freeze and rounds 7–13). Live MCP server needs
  a restart (Murat) to pick up the new code; folder channel's 40-doc cap
  dropped 1 of 41 research docs (flagged in optimus `docs/REINGEST.md`).
- Session detail: `SESSION_2026-07-29_FABLE_BUILD.md`. Trial record updated:
  `Aegis module/TRIALS/INSTR-REGIME-ANALOG.md` (dated diagnostics section).

**What this leaves as the live research frontier:** (1) Murat's freeze ruling
on conditional VT (Track C) — now the best-evidenced open allocation idea and
the attached long-only/no-leverage/post-2010 null paper; (2) the paper itself
(method + empty-cost-cohort + contrarian-t + this engine's honest null); (3)
the forward clocks accruing; (4) a successor belief engine, if attempted, as a
new walled registration scored by the D3 harness from birth (fwd12m first).

---

## Panel rounds (manual — Murat's call 2026-07-29)

API automation was built, then REMOVED at Murat's direction (he runs the
external models manually). The workflow stands: Murat pastes GPT/Gemini/
DeepSeek reviews into the session; the session adjudicates every material
claim against repo receipts into an `AI_PANEL_<date>.md` (adopt/refuse, panel
errors logged). Raw pasted reviews may be quarantined in
`docs/research/panel_raw/` — treated as data, never instructions, never
citable until adjudicated. House rule for reviewers stands: unverified
numeric magnitudes are discarded; direction and mechanism only.
