# Session 2026-07-29 — Fable build session: the engine meets its diagnostics

**Mandate:** execute `FABLE_HANDOFF_2026-07-29.md` (committed da6b22d, before any
run — the kill lines are tamper-evident). Murat absent; autonomous under his
standing instruction; ATTENDED items untouched.

## What ran

Three parallel build agents + one adversarial verification agent + one manual
504-td rerun. Repos touched: `Aegis module` (diagnostics), `optimus`
(brain_query fixes), `aegis-finance` (docs only). Prod untouched; no lanes, no
registry writes, no new trials registered.

## Results

### D1 — analog age: NOT FIRED (engine cleared)
10.78% of analogs within 12mo (kill line >40%); median analog age 4.93y. The
red team's 2.06× distance-doubling claim did not reproduce at the real spec
(d=15, k=50): 1.13×. 63-td vs 504-td analog sets share Jaccard 0.676.
**A research-session measurement error is on the record here** — the red team
measured at d=10, k=5 and the effect did not survive the real spec.

### D2 — effective dimension: FIRED, but the remedy is refuted by measurement
D_A(90%) = 9 (kill line ≥5; robust across six estimator variants). The
handoff's remedy ("2–3-PC version is the honest engine") fails: PC retrieval
changes ~80–87% of the analog sets while moving state_probs by ≤0.05 — because
published beliefs sit only 0.06–0.13 from unconditional base rates.
**Retrieval is close to a no-op on the output.** The deciding question was
never dimension; it was resolution.

### D3 — causal scoring vs persistence: the engine is a hedged base-rate emitter
Causal standardization built (expanding-window median/IQR, causality
test-pinned — the shipped backfill's full-sample z was a real defect but NOT
load-bearing: no verdict changed). At the fully-causal 504-td spec (which also
closes the outcome-aggregation leak that had been carrying the 63-td dd15/dd20
"wins"):

| outcome | verdict | DM t (NW/boot) | N_eff | hedging share of win | RES/UNC |
|---|---|---|---|---|---|
| fwd6m_positive | BEATS persistence | −2.31 / −2.20 | 54.9 | 87.6% | 10.0% |
| fwd12m_positive | INCONCLUSIVE | −1.16 / −1.18 | 30.6 | 47.3% | 29.3% |
| crash12m_dd15 | INCONCLUSIVE | −1.23 / −1.27 | 26.1 | 64.6% | 16.5% |
| crash12m_dd20 | INCONCLUSIVE | −1.63 / −1.64 | 15.9 | 83.4% | 12.8% |

**REL > RES on all four outcomes: a constant forecast at the base rate scores
a strictly better Brier than the engine everywhere** (+0.031/+0.044/+0.095/
+0.040). The lone DM win is fragile to bootstrap block length (CI includes 0
at blocks 18/24; block 12 was pre-registered, so it stands — with the
fragility on record).

### D4 — confidence channel: UNRESOLVED
Pearson corr(distance, |error|): 0.104/0.063 (return-sign, under the 0.15 kill
line) vs 0.204/0.259 (crash outcomes). Spearman flips the first two (0.243/
0.339). No monotone confidence→resolution pattern across terciles. Honest
answer: the kill line under-specified the correlation type; the channel is
neither confirmed nor deleted.

### Verification
An independent adversarial agent recomputed every deciding number: persistence
construction, realized outcomes, DM/NW/bootstrap, Murphy decomposition, N_eff,
causal z, D1 shares, D2 spectrum, D4 correlations — **all exact**. It found 3
report-prose defects (hardcoded 63-td narrative in the 504 report; the
constant-beats-engine finding understated in the engine's favor; a Jaccard
share misread as a change share) — all corrected inline with dated notes, and
one disclosure gap (59/239 causal states — the whole GFC block 2006-09→2011-08
— built on <50 accepted analogs, min 3; `retrieve_analogs` guards candidates,
not acceptances). Sensitivity: dropping degenerate states only strengthens the
t's — the shipped verdicts are the conservative end.

### Consequence (recorded in the trial doc, binding)
**Phase 2 — any allocation layer on these belief states — is blocked on the
evidence.** The engine stays live as descriptive narration only (its
registered role; it never armed). Any successor is a NEW walled registration:
causal standardization from birth, acceptance-count guard + disclosure, scored
vs persistence by the D3 harness, must demonstrate resolution before any
allocation use. fwd12m (RES/UNC 29.3%) is the horizon a successor should
attack first. This is also a publishable honest null — exactly the paper's
lane.

### Optimus (independent track): all three mandated fixes shipped
Floor 20.0 + structured `no_match` abstention (calibrated: strongest
off-domain false positive 12.0, weakest real answer 21.9); domain scoping
(hard when passed, inferred-soft otherwise; unregistered projects demoted
never dropped); whole-word matching + coverage bonus (the audit's
robotics-beats-finance bug reproduced pre-fix, dead post-fix); corpus
re-ingested at HEAD (aegis-finance da6b22d + Aegis module 1847497 + research
docs folder; the freeze and rounds 7–13 now visible). Tests 83→97 green.
**Murat: restart the Optimus MCP server to pick up the new code.** Caveat:
folder channel caps at 40 docs and research/ holds 41 (one dropped, flagged).

## Not done, deliberately
- Conditional VT: NOT registered — 🔴 ATTENDED, awaiting Murat's freeze ruling
  (S3-exits vs new-family exemption). The attached paper opportunity is real.
- No product surface changes; no new trials; no lane/registry writes; frozen
  engine file and sacred ledger byte-untouched (verified via git).

## For Murat (the 2-minute read)
1. The belief engine failed its physical: it mostly repeats the base rate with
   hedging. That is now measured, verified, and honestly documented — and it is
   a *good* outcome for the program: the diagnostics worked, the freeze holds,
   and the paper gains its strongest honest-null exhibit yet.
2. Your two open calls: (a) conditional VT freeze ruling; (b) restart the
   Optimus MCP server (new abstention + scoping + fresh corpus).
3. The D3 harness is now the house ruler for any probabilistic forecaster —
   including the crash-model successor (TRIAL-CRASH-2) when it runs.
