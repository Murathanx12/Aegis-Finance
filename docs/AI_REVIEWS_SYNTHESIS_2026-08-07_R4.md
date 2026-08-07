# AI Review Synthesis — round 4 (2026-08-07/08: GPT challenge response + Opus execution session)

Inputs: (a) GPT's full RESEARCH_CHALLENGE response; (b) the parallel Opus
session with repo execution access (OSAP external anchor, EXT-NULL-1/EXT-POWER-1,
REAL-NULL-1 K=4000 extension). Both verified against artifacts before anything
was adopted, per the hardened proof-of-reading gate (R3 §3).

## 1. GPT — VERIFIED; passes the hardened gate

Every greppable receipt checked out exactly: rec_mom gross t 2.64 / net 0.48 /
turnover 0.368 (NEGATIVE_RESULTS:636,671), io_level +145.8 bps t 5.92 (:1207),
options 23/23 years 99.7% coverage and DSR null-max 0.3816 (:1035,1064), the
2/125 Wilson recomputation, CANON's 24-month rule. One anomaly: GPT quotes the
brief's pre-correction interval [0.44%, 5.65%] (n=125) — it read a stale
commit; the corrected figure is 1.6% [0.62, 4.04] at n=250. Not disqualifying.

### Attack-by-attack adjudication

**§1.1 Terminal delisting-payoff linkage — CLOSED BY HISTORY, receipt found.**
GPT's most dangerous attack, hedged with "unless v6 removed that operation."
It did: `panel_gen.py` version history records v1 REJECTED for exactly this
channel ("delist-stamp death channel"; F8 caught the death signature:
price_level +0.014, dd_from_12m_high −0.011, amihud −0.012). v2+ keeps the
real truncation DATE only; the final month is an ordinary synthetic return.
`gen_null_panel` docstring: "No delist stamp; real prices and dollar volumes
carried." GPT's proposed three-arm measurement was, in effect, already run as
the v1→v2 iteration. No action needed; recorded here as the receipt.

**§1.2 Cross-sectional shock clusters destroyed in the null — REAL, ALREADY
QUANTIFIED, batch consequence goes to REPLAY-2.** True by construction: DGP-A's
within-month sigma-stratified permutation dissolves industry/liquidity shock
clusters. This is precisely the fidelity gap REAL-NULL-1 measured from the
other side (real-panel null 2.3× wider than simulator), because signal-
randomization on the REAL panel preserves all cross-sectional covariance.
Adopted refinement: REPLAY-2's error-control evaluation must include a
correlated-candidate-batch arm (many signals loading on the same real
residual structure), which REAL-NULL-1's machinery supports at near-zero cost.
A new simulator arm is NOT needed — the real-panel null dominates it.

**§1.3 Semantically generic but distributionally σ-family — ADOPTED.** The
frozen semantic ontology stays frozen; the veto threshold becomes
max(semantic-family p95, empirical-neighbor p95), with the neighbor assigned
by the pre-registered correlation surface (the R² ≥ 0.7 diagnostic already
queued). Folded into the REPLAY-2 veto spec.

**§1.4 Repair jurisdiction — ADOPTED, the cheapest rule.** "A repair after
reveal always creates a new trial ID and resets the one-shot clock." Plus the
freeze list (source snapshot hashes, dependency hash, eligibility/polarity,
missingness/ties/winsorization rules, abort-vs-score state machine, benchmark
and cost fallbacks) goes into REPLAY-2's registration requirements.

**§1.5 Episode support vs temporal mismatch — ADOPTED.** New terminal state
`SUPPORT-INADEQUATE` when the confirm window holds fewer than a pre-registered
number of independent episodes/clusters. Distinct from TEMPORALLY-MISMATCHED
(Amendment 2). Episode-clustered inference enters as a diagnostic, not a new
gate, until its operating characteristics are measured.

**§1.6 NAV identity across config changes — PARTIALLY EXISTING, gap adopted.**
Config-hash isolation and inception resets already exist (CANON §5; lane YAML
hashes). New and adopted: counterfactual shadow NAV for the superseded
version, an ex-ante materiality rule, and published pre-trade intent hashes
(target weights + execution window hashed before first eligible fill).

**§1.7 Circularity of the null ontology — ADOPTED in cheap form.** Blind human
adjudication packet (10 candidate definitions, 10 failure transcripts, scoring
rubric, one HKU finance faculty/grad student who hasn't seen outcomes;
disagreement defaults conservative). NIST/drand public-randomness pulse for
post-commit audit sampling. Complements, does not replace, the external
anchors (OSAP, REAL-NULL-1) that closed part of this leg empirically.

### Rebuild ideas

| idea | verdict |
|---|---|
| §2.1 e-process/e-BH challenger (Wang-Ramdas 2022) | ADOPTED as a competing REPLAY-2 error-control design, evaluated on the existing bank against BH-on-empirical-p; Pareto rule as GPT specified |
| §2.2 future-seeded canary certification | ADOPTED — the general form of the `assert_coverage` lesson ("an assertion with no callable entry point has no test"); build with WORLD-8/9 |
| §2.3 rec_mom buy/hold-band resurrection | ADOPTED as a resurrection candidate — the ledger's one clean cost-kill; Novy-Marx & Velikov (2016) mechanism; resurrection tax + pre-registration apply; small-segment caveat: rec_mom is a small-segment candidate |
| §2.4 cross-lane netting | QUEUED low — likely small overlap across 10 differentiated lanes; revisit when lanes trade the same names |
| §2.5 options-confirmed 13D | QUEUED post-replay — family closed by §29-§31, so this pays the resurrection tax; OptionMetrics coverage already banked (23/23yr) |
| §2.6 randomized ledger experiment | MERGED with the Ruler Benchmark into the single paper track — the "citable experiment" |

### §5 resident-agent answers

- **WORLD-8 two-point construction: VERIFIED and adopted as the concrete
  spec.** Recomputed: E[e|q]=0 and E[e²|q]=1 exactly for the stated two-point
  distribution, P(e>0|q)=p(q) monotone. GPT pre-registered and ran a
  proof-of-concept (3000×180, seed 20260807): t_ic 4.652 at λ=0.5 with payoff
  t −1.400, shuffled-q placebo clean — pass condition declared in advance and
  hit. Certification path stands as GPT states: insert into DGP-A v6, require
  F1-F8 within tolerance, calibrate λ to IC targets not adoption outcomes.
  This supersedes the DeepSeek sketch and competes with the jackpot-
  compensation design; whichever passes F1-F8 ships.
- **§5.2 cheap confirm-stage certification (block-wild resampling of cached
  confirm months): ADOPTED.** This removes the assumed need for another full
  grid night for confirm-side error control — 1-3 core-hours, validated
  against 25 full panels.
- §5.3 capacity formula: correct that any current dollar answer would be
  invented; adopted as the post-replay capacity protocol (with MIDAS/605).
- §5.4 milestone language: adopted verbatim into the lane-reporting standard
  (the 1−0.05^(1/n) upper failure bound; the permissible/impermissible
  sentence pair).

## 2. Opus execution session — VERIFIED

All artifacts located and read: `TRIALS/PREREG_EXT_NULL_1.md` (written before
any scan; honest priors declared including "most likely way I am wrong" — which
is what happened), `runs/EXT-NULL-1/VERDICT_placebo_arm.md` (kill clause n<40
fired: 0 of 114 OSAP placebos exist at firm level, confirmed by two routes),
`docs/HANDOFF_EXTERNAL_ANCHOR_2026-08-07.md`, `aegis_brain/factory/osap.py`,
`data/osap/firm_char.parquet` (5.4M rows × 211 cols). Guard reproduced banked
vol_12m_low 1.89 / price_level 2.12 exactly. Contamination bookkeeping is
correct: placebos permanently confirm-contaminated, predictors' confirm window
unread, candidate count still 179.

Key holdings from that session, now house positions:

1. **REAL-NULL-1 (K=4000): the simulator's generic null is ~2.3× optimistic
   for persistent candidates** — 0.082 [0.0735, 0.0905] vs 0.036 — and 0.082
   is a lower bound (real candidates are more persistent than the most
   persistent arm tested). Confirm-pass-given-graduation 118/328 = 0.360.
2. **osap_GP small (t_ic 7.31, t_net +2.42) is a cross-validation receipt,
   not a discovery** — an independent implementation, direction fixed by
   Novy-Marx (2013), reproduces the project's own gp-small explore graduate.
3. **The external placebo arm is a data-availability negative result** with
   two live paths (portfolio-level returns → money-leg calibration only;
   clean-room rebuild from papers, GPL constraint on the code).
4. **EXT-POWER-1 (209 predictors, explore only, M4 prior 30-50%)** was found
   dead at 36/209 (no process alive) and resumed by this session; scoring
   against the declared prior when it lands.
5. External-literature convergence (Chen-Velikov 2023, Chen-Welch 2024,
   Israel-Moskowitz 2013): the live square is gross/cash profitability, long
   leg, small segment, turnover-controlled — where gp-small already sits.

## 3. Net effect of round 4

No new blocking defect. The replay stays blocked on Amendment 3 exactly as
before; round 4 *added* to REPLAY-2's requirements (repair jurisdiction,
SUPPORT-INADEQUATE, max(semantic, empirical) veto, e-BH as challenger design)
and *removed* one assumed cost (confirm certification needs core-hours, not
grid nights). One attack died against a receipt that already existed
(§1.1 ↔ panel_gen v1 rejection). The strongest single artifact of the round
is GPT's executed WORLD-8 construction — a reviewer pre-registered a
falsifiable design, ran it, and reported the placebo. The review process is
now producing work to house standards.
