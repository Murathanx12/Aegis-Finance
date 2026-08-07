# AI Review Synthesis — recalibration arc (2026-08-07, round 2)

Four external AI reviews of `EXTERNAL_REVIEW_BRIEF_2026-08-07.md` (GPT,
DeepSeek, Consensus, Gemini), each verified against the artifacts before
anything was adopted. Prior round: `AI_REVIEWS_SYNTHESIS_2026-08-03.md`.

**Conflict-of-interest disclosure:** this synthesis is written by the same
agent (Claude) that built the recalibration machinery under review. The
per-claim verification below is checkable against the ledger; the ratings
in §5 should be read with that bias in mind. GPT's correlated-agent-error
warning (its §18) applies to this document too.

## 1. My own diagnosis first (independent of the four reviews)

Answering Murat's prompt directly:

- **What was done right:** pre-registration, the explore/confirm wall,
  placebo controls, forward-only track record, and — above everything —
  publishing the failures. The single best act of the project was turning
  the 0-for-179 suspicion into a measurement (GATE-M1) instead of a
  narrative.
- **What was done wrong:** we ran a decision instrument for a year without
  ever measuring its power. Every component was borrowed from good papers
  (DSR, PBO, t-bars) and assembled into a ladder whose joint operating
  characteristics nobody had computed. The result was a machine with a
  measured ~0% true-positive rate whose output we were reading as
  evidence about markets. Secondary wrongs: the small segment was
  excluded by a cost premise later measured backwards (§22) and never
  re-admitted; the harness that finally measured all this itself shipped
  two silent failures (run-1 no-op, run-2 NameError) — the house failure
  mode reproduced inside the instrument built to catch it.
- **How ideas come back:** not by re-liking them. Mechanism-classified
  resurrection (kill audit §1, statuses in Amendment 2), a one-shot
  replay under a frozen ladder, a family-null veto so IC artifacts cannot
  masquerade as resurrections, a resurrection tax on repeat attempts, and
  independent recomputation of the verdicts.
- **How it never happens again:** the simulator becomes a permanent
  certification suite (worlds with known truth), and no gate change ships
  without its measured power/FDR curve. "Calibrate the ruler" is now
  NEGATIVE_RESULTS §34 and llms.txt — it is the project's most reusable
  finding.

## 2. Per-review verification

### GPT — VERIFIED, the strongest review of the four

Spot-checks against artifacts, all EXACT:
- Momentum numbers (its §16): 17.9%/15.3% CAGR, Sharpe 0.629/0.871,
  maxDD −54.7%/−33.7% — matches NEGATIVE_RESULTS §9 to the decimal.
- PurgedKFold silent-fallback claim (its §30): confirmed defect C7 in
  the 2026-08-03 synthesis, quoted accurately.
- Its I2 decay arithmetic reproduces ours.
- Citations (Bailey-LdP DSR, Bailey et al. PBO, Harvey-Liu 2020) are real
  and correctly characterized.

Its sharpest genuinely-new points: (a) post-hoc discoveries should become
*named frozen successors* (→ BRAIN-010, registered blind, see §3); (b) the
decay kill conflates "does the effect exist" with "does it persist into
2019-24" — a TEMPORALLY-MISMATCHED kill class we had missed; (c) the
family taxonomy is itself a researcher degree of freedom unless the
mapping is deterministic-from-spec; (d) five-AI agreement is not five
validations when all read the same dossier.

### DeepSeek — VERIFIED with one rejected recommendation

Accurate throughout on the artifacts (its citation markers are sloppy
placeholders, but the numbers behind them check out). Its distinctive
recommendation — run the replay under BOTH the contaminated threshold and
a separate-split threshold — is **REJECTED**: two adjudications of the
same 179 invites verdict-shopping and breaks the one-shot commitment. The
accepted form: the single replay output *prints* candidate statistics
against both thresholds as columns, but the verdict column comes from the
one ratified ladder only.

### Consensus — VERIFIED, literature-anchored, one artifact flagged

Correctly frames the tradeoff via Harvey-Liu (false AND missed
discoveries) and supports the k-fold rejection. Its "Evidence Gaps" table
with RCT/dose-response/clinical columns is a medical-review template
artifact — ignored as boilerplate. Useful confirmation that
simulator-calibrated *whole-ladder* governance is thin in the literature,
i.e. the part worth writing up.

### Gemini — INVALID: reviewed the wrong project

Its review describes "Aegis Finance" as a blockchain hedging platform on
the Internet Computer (Rust canisters, NextJS, Deribit/ZetaChain,
"a quantitative team operating out of Jakarta, Indonesia"). That is a
**different project sharing our name** (its own citations point to a
TreeHacks 2023 repo and a DFINITY forum showcase). Every project-specific
claim is quarantined. Its generic statistics content (DSR/PSR formulas,
Benjamini-Yekutieli, effective-N via clustering, CSCV) is textbook-correct
but was not fitted to our design; nothing adopted that GPT/DeepSeek did
not already cover better. **Process lesson for future review farming:
hand agents the exact repo URL + brief and require them to quote our
artifacts back; a reviewer that never quotes you never read you.**

## 3. Adopted — and already executed today

| # | Change | Status |
|---|---|---|
| 1 | **BRAIN-010 registered blind** (both-seg/top-10 as a named frozen successor with evidence rule E1-E3 on the 1000 fresh nulls + pre-registered prediction FDR ∈ [0.015, 0.035]) | committed & pushed at wave-3 rep ~420/1000, before any fresh-null result existed |
| 2 | **TEMPORALLY-MISMATCHED** added to the resurrection taxonomy (5 statuses) | Kill audit Amendment 2 |
| 3 | **Frozen family ontology file** (`TRIALS/family_ontology.json`, deterministic-from-construction, written before replay statistics are read; two null levels for now) | Amendment 2, binding |
| 4 | **Resurrection tax** (normal bar → family bar + money receipt → new pre-registered trial with own control) | Amendment 2, binding |
| 5 | **Independent recomputation** of replay verdicts by a second implementation; ship only agreements | Amendment 2, binding |
| 6 | **Conditional language** ("under DGP-A v6 and the registered rule"); "evidence-conditioned sizing" replaces "posterior sizing" | brief + audit updated |
| 7 | **Two explicit error budgets** (FDR ≤ 5% AND false-kill targets A2-A5) — already implicit in RECAL acceptance targets; now named as the Harvey-Liu joint-error frame in the paper outline | narrative adoption |

Adopted as roadmap (not executed): the **permanent world suite**
(esp. WORLD-8 "IC-real/book-dead" and WORLD-9 "gross-real/cost-dead" —
decoupled IC/alpha injection, the simulator's known blind spot), hypothesis
genealogy as the deflation unit, and the evidence/economic/portfolio score
separation.

## 4. Rejected, with reasons

- **Dual-threshold replay** (DeepSeek): breaks one-shot; see §2.
- **BY-FDR + effective-N machinery** (Gemini): built for p-value pipelines
  with arbitrary dependence; our control is an empirically measured FDR
  under a registered selection rule, and our DSR is diagnostic — grafting
  BY onto it solves a problem we no longer have. Effective-N clustering
  noted as a possible future *diagnostic* input to reported DSR only.
- **Deep hierarchical nulls now** (GPT §8 extension): with 21 simulator
  signals we can support two levels honestly; more would be taxonomy
  theater. Revisit when the world suite widens the signal set.
- **"Adaptive confirm windows" as a general mechanism** (DeepSeek/GPT):
  accepted as *diagnosis* (TEMPORALLY-MISMATCHED class) but not as a
  floating window rule — a per-candidate window chosen post-hoc is a
  degree of freedom. Decay-registered candidates get re-registered with a
  horizon-matched design instead (H1-H4 split), one trial each.

## 5. Ratings (with the §0 conflict disclosed)

| | GPT | DeepSeek | Consensus | **mine** |
|---|---|---|---|---|
| Project overall | 8.4 | 8.5 | 8.5 | **8** |
| Original gate process | 5.8 | — | 3 | **4** |
| Recalibrated process | 8.1 | — | 8 | **7.5** |
| Evidence of investment skill | 2 | — | — | **2** |

My deductions vs the panel: the two harness bugs and the threshold
contamination are mine, and the simulator's IC-alpha coupling means the
family-null veto — the load-bearing new defence — rests on ledger receipts
rather than simulated certification. 7.5 is what an instrument with a
known uncertified blind spot deserves. The panel's convergence at ~8.5
should be discounted for shared-input correlation (all four read the same
brief; one of them demonstrably reviewed a different project and still
produced a confident score).

## 6. Standing instruction for future review rounds

Give reviewers: the brief + `NEGATIVE_RESULTS.md` + this synthesis. Ask
them to (a) quote at least three artifact numbers back verbatim as proof
of reading, (b) attack §8 of the brief, not summarize it, and (c) attempt
an independent recomputation of one checkable number. A review with no
quoted artifacts is discarded without reading its conclusions (the Gemini
rule).
