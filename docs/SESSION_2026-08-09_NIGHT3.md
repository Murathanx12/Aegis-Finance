# SESSION 2026-08-09 (evening) — T1 merges + NIGHT-3 executed

Branch `factory/night-3` in the `Aegis module` repo, **cut from main after the
approved merges, and left unmerged** — the branch is the deliverable, pending
Murat's read. `aegis-finance` is on `main` and pushed.

No lane seeded, no flag flipped, `paper_nav` untouched, holdout unread and
**verified programmatically**.

---

## T1 — done, as instructed

- `factory/night-2` → **main** in Aegis module; `research/night-3-design` →
  **main** in aegis-finance. Both pushed.
- **`EXECUTION_STANDARD` second amendment of 2026-08-09: the PRODUCT TRACK.**
  Murat's answer to the regime-gate question, implemented as *split the claim,
  don't move the line*: engine-skill keeps G4a and ≥4/5 regime blocks as gating;
  the product track gates on the product bar (beats every pre-registered
  investable alternative on excess terminal wealth under the ruin constraint),
  reports regime breadth as **mandatory disclosure**, and may never carry an
  engine-skill label. Both tracks still require G2 holdout and G7 simulator
  before paper. Forward-only — `PF-ENGINE-ALPHA-2` stays FAILED.
- **`PF-ENGINE-ALPHA-PRODUCT-2` registered**, declaring itself
  **RETROSPECTIVE-class in the registration**: every product-bar number
  (15.58× vs 8.94× best alternative, ruin 0.0054) already sits on disk, so the
  bar is *informational, not evidential*. Its only untouched evidence is G2 and
  G7. Registered prediction **P-B says it FAILS the 2023-24 holdout**.
- **META L12T2 recorded as a design note, not a registration.** Its 24.72× is
  the best cell of a scanned grid and its neighbours collapse. The one credible
  generalization — top-1 → top-2 cuts ruin 0.604 → 0.062 at *every* lookback —
  is carried forward without a money claim.

## NIGHT-3 — the short version

**Registered verdicts: M1 REJECT, M2 REJECT.** The LLM does not earn a role in
stock selection on this evidence, which routes its attention to narration and
event triage. Predictions **5 of 7 resolved** (PF-1: 2/5, PF-2: 4½/8).

Full detail: `Aegis module/docs/NIGHT3_VERDICT_2026-08-09.md`.

### The finding that matters most, and no LLM was involved

Inside the engine's own top-40 profitability slate, the composite's ordering is
worth **+1.46 %/yr at t = 0.43**. A stratified slate spanning all five quintiles
is **worse** (t = 0.15).

> **The edge is MEMBERSHIP — which ~150 names out of ~2,000 — not ORDERING.**

Corroborated independently by the already-banked concentration grid: net excess
is flat from 10 names (+4.46 %) to 150 (+4.67 %) while the t-stat climbs
1.92 → 2.52. Breadth buys less noise around the same edge; it does not dilute a
ranking, because there is no ranking to dilute.

**Consequence for "bigger margins":** the levers are universe, depth and cost —
not better picking. Small caps pay **+4.67 %/yr**, all-cap **+2.29 %**,
large/mid **+1.56 %** on the identical signal.

**Consequence for the LLM:** it was asked to re-rank inside a set where ranking
carries no information. That is why the stratified follow-up environment was
**built and deliberately not run** — the power analysis is the receipt.

### Where the LLM did and didn't land

| arm | excess CAGR | NW t | recosted placebo p |
|---|---|---|---|
| ENGINE composite top-20 | +3.64 % | 1.34 | 0.15 |
| A — LLM, no memory | +4.67 % | 2.30 | 0.05 |
| E — LLM + episodic memory | +6.21 % | 2.58 | 0.01 |

Arm E is the best standalone number in the campaign — **and it does not count**.
Those t-stats are against the benchmark, and every arm including the placebo
carries the same small-cap profitability premium; the paired difference is what
isolates the LLM, and it prints **t 0.93** against a **3.62 %/yr MDE**. Quoting
the standalone number instead of the registered metric would be exactly the
substitution the registry exists to prevent.

A control that can only undercut arm E — **`DIAG-NIGHT3-MEMORY-PLACEBO-1`**,
same memory with the situation→outcome mapping scrambled — was registered before
compute and is running.

### Answers to Murat's questions, with numbers

- **"LLMs give different answers to the same question."** Measured: at
  temperature 0, **96.5 %** of per-name decisions repeat; at temperature 0.7,
  **21.6 % flip**. The immutable cache, not a "be consistent" instruction, is
  what makes the campaign reproducible. 3.5 % non-determinism survives even at
  temperature 0 and is a standing caveat.
- **"Can it learn from what happened vs what we imagined?"** It changes *how it
  reasons* — memory shifts its stated thesis mix from 68 % momentum toward
  profitability and value — without changing outcomes detectably.
- **Its self-report is not evidence.** Its stated belief update disagrees with
  its own measured conviction change **37 %** of the time.
- **Contamination ceiling:** unforced, it refuses (120/120 abstentions). Forced,
  identity-and-date alone scores AUC 0.571 — *above* every full-information arm
  — but with a CI of [0.481, 0.656]. Everything in that table is within noise of
  a coin flip.
- **Elicitation, an actionable fix:** asked in decimals the model ties 115/500
  perturbation pairs; asked in **basis points** ties fall to 35/500 and the
  coherence battery goes 3/5 → 5/5. **0 wrong directions in 500 pairs** — its
  logic was never broken, only its resolution. Adopted forward-only.

### Two defects in my own harness, found and corrected

1. The placebo was billed 100 % turnover monthly instead of its true ~58 %.
   Recosting moved every p-value (ENGINE 0.04 → **0.15**). The as-run numbers
   flattered the LLM arms.
2. Persistence was graded against priors the model was never shown — 3,450 of
   7,490 reviews. N8 is scored on the 4,040 shown only.

Also disclosed: the replay charges one-way costs while production charges
two-way; since the LLM churns more (4.8-5.9 vs 2.07), full costs cut M1 by
0.68 %/yr and M2 by 0.26 %/yr, and arm E's standalone falls to +4.75 %.

## Open for Murat

1. **Holdout stays unfired** per your sequencing decision — G7 must exist first.
   Unchanged.
2. **Merge `factory/night-3`?** Left unmerged deliberately; nothing else moved
   to main without your say-so.
3. **NIGHT-4 recommendation, changed by tonight's receipts.** T3 as issued is
   still right (build G7). But the LLM half of the roadmap should now target
   **raw text** — the one channel never tested and the only place AMNESIA says
   it could still win — rather than more decision replays over digested numbers.
   Selection is answered; text triage is not.
