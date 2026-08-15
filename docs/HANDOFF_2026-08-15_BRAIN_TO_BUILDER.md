# ORDER — brain → builder, 2026-08-15 04:50 UTC

Supersedes the "next session" list in `HANDOFF_2026-08-15_OPUS5_TO_NEXT.md` §6.
Binding. Verified against live production and the artifacts, not against any
session's own report.

---

## 0. Verified state (checked, not accepted)

| Fact | Evidence |
|---|---|
| `aegis-finance` @ `7e77820`, `Aegis module` @ `f5367f0`, both clean | `git log`/`status` |
| Deploy live on `7e77820` | `/aegis_verified_state` |
| Scheduler **7 jobs**, `pi_ownership_collect` present, next run **2026-08-15 06:00 ET** | scheduler block |
| All 10 lanes NAV-fresh through 2026-08-14 | nav.all_fresh |
| Resolver **fired 2026-08-14T20:30:12Z and REFUSED** — "every one of 112 LIVE_FORWARD record(s) is content-identical to a CAMPAIGN_FORWARD record" | `/api/optimus/job_receipts`, production |
| `pi_ownership_collect` receipts `exists: false` — **no production run yet** | same |
| Prediction ledger 112 records, **0 resolved** | ledger block |
| Gym policy menu = **17** policies; base-rate table has **5** buckets | source |

**The single best thing in this session's record is that the resolver guard was
verified by production refusing on its first scheduled run after deploy** — not
by a test, not by review. That is the house standard met exactly.

Two clocks are still ahead as of this writing (04:50 UTC): the collector at
**10:00 UTC** (~5h) and the pre-open night at roughly **11:50 UTC** (~7h).
**Do not idle against either.**

## 1. Verdict

Accepted. Orders 1/3/4/5/6 shipped and Order 2 stopped one step short *because a
guard written in the same session refused it* — that is the "prepare everything,
stop one keystroke short" rule holding under its own weight.

The three findings that matter, all confirmed independently:

1. **`MAX_TOKENS=1600` was not a uniform tax — it silenced the treatment arm of
   the primary contrast 4× more than its control.** A constant appearing in no
   registered document was about to bias A-vs-B. The information guard did not
   save $0.40; it stopped a biased trial from accruing.
2. **`LIVE_FORWARD`'s true size is ZERO** and the nightly resolver was **two
   days** from writing outcomes onto campaign rows and manufacturing "the
   deployed product's forward record" out of history.
3. **The stress→return map is non-monotone.** Full five-bucket table (the
   three-row excerpt circulating elsewhere omits the left arm and does not
   support the U-shape claim; the five-row table does):

   | VIX<15 | 15–20 | 20–25 | 25–35 | ≥35 |
   |---:|---:|---:|---:|---:|
   | +2.15% | +1.76% | **+1.56%** | +4.60% | **+6.97%** |

   Trough in the middle, best at the extreme. The engine sells above 25.

## 2. TWO DEFECTS FOUND IN THIS REVIEW — fix before anything is built on the Gym

These were found by **running the numbers**, not by reading the code. Everything
downstream of `RESEARCH-GYM-1` inherits them.

### G1 — regret is denominated against the ex-post best of 17 policies, and the null is not zero

`CounterfactualSurface.regret_pct()` = *"Best available minus what was done.
Never negative by construction."* The max of 17 noisy 63-day outcomes is an
upward-biased estimator; a decision-maker with zero skill shows large positive
regret under this denominator. I measured the null on real SPY 1993–2026,
n=4000 random 63-day windows, same menu, same 5bps cost:

| baseline decision | mean regret vs ex-post best | median |
|---|---:|---:|
| always-HOLD | **+4.99pp** | 3.98 |
| random policy | **+5.86pp** | 4.52 |
| always-SELL_100 | **+8.09pp** | 6.98 |
| always-HOLD, conditioned VIX≥25 | **+7.32pp** | — |
| **always-SELL_100, conditioned VIX≥25** | **+12.65pp** | — |

Dataset zero's headline is **+26.5pp** mean regret on 5 de-risking decisions.
The state-and-action-matched null for exactly that decision is **≈12.65pp**. So
the honest excess is **≈13.9pp, not 26.5pp — the headline is roughly 2×
inflated by its denominator**, and it carries no SE on n=5.

The finding *survives directionally* (26.5 > 12.65). Its magnitude does not.

**Worse, the classification gate is broken by the same cause.**
`MATERIAL_EDGE_PCT = 1.0` returns `NO_FAILURE` when regret < 1pp. Measured:
**P(always-HOLD regret > 1.0pp) = 0.931.** A neutral, blameless hold classifies
as *some kind of failure* 93% of the time. That is why 27 of 28 HOLDs got a
failure label. **The taxonomy's failure rate is an artifact of the threshold,
not a measurement of the engine.**

Order:
- Report regret against **three declared denominators**, never one: (a) the
  ex-post best (keep it, label it as an upper bound), (b) a fixed default
  (HOLD), (c) the **state-and-action-matched null** computed as above.
- Recalibrate `MATERIAL_EDGE_PCT` against the measured null distribution
  rather than a round number — or replace the scalar with a percentile of the
  matched null. Canon: *gates must be calibrated before their kills are
  trusted* (NEGATIVE_RESULTS #34). This gate was never calibrated.
- Re-run dataset zero and **restate every number in `RESEARCH_GYM_1.md`**. The
  classifier's *discrimination* (base-rate-decided) is separately defensible
  and probably survives; the failure *rate* does not.

### G2 — the base-rate table reports n where it owes n_effective, and prints no MDE

`n=353` for VIX≥35 is 353 **overlapping** daily observations of a 63-day
forward window. Measured on real VIX:

- **349 daily obs, 17 distinct episodes (>21d apart), overlap-adjusted n ≈ 5.5.**

The right arm of the U — the +6.97% that the whole re-entry hypothesis rests on
— stands on **single-digit-to-low-teens independent events**, essentially
1998 / 2001–02 / 2008–09 / 2010 / 2011 / 2015 / 2018 / 2020 / 2022.

Order:
- Every base-rate row prints **n_effective** (overlap-adjusted AND
  episode-clustered) and its **80%-power MDE** (§19). A row without an MDE is
  not publishable, including inside the Gym.
- Name the **corpse as control**: "buy when VIX spikes" is among the most
  published and most traded rules in existence. Any Aegis re-entry mechanism is
  measured *against the naive published rule*, not against a strawman.
- State the mechanical confound explicitly: VIX≥35 only occurs after a large
  drawdown, so part of +6.97% is rebound-from-depressed-price, not information.

**Neither defect is a reason to slow down. Both are reasons the Gym is worth
having: it produced a number good enough to be worth auditing, and the audit
found the denominator. Fix, restate, continue.**

## 3. Budget — FUNDED, proceed

$37.12 + Murat's **$20 top-up = $57.12**. Forty nights projected **$41.61**
(≈$1.04/night). Fully funded with ~$15.5 headroom.

- Break-even is **$1.43/night**. Report the measured all-in cost of the first
  VALID night against that number.
- **Tell Murat a top-up is needed only if measured cost > $1.43/night**, or when
  the balance falls below the cost of the nights still owed. Do not ask
  otherwise; do not stop research for money.
- The $12/night ceiling stays armed. Quality is never traded for cost.

## 4. What to do, in priority order

Eighteen workstreams were proposed. A session that starts eighteen finishes
none. This is the ranked list; **everything below the line is explicitly
deferred and must not be started.**

### MUST — this session

**M1. Clock: `pi_ownership_collect` first production run (10:00 UTC).**
Verify by **durable receipt through the API**, never by a local run — the
insider collector once passed twelve tests while 403-ing on 100% of prod
fetches. Report: index rows · unique accessions · documents fetched · coverage
· parse errors · BUY/SELL/mechanics counts · actors · tickers · latency ·
failure classes · whether TeacherEvents were actually appended · whether a
second identical run is idempotent. If prod fails, fix the *production-specific*
defect, redeploy, verify the next real invocation.

**M2. Clock: one corrected paid night, pre-open (~11:50 UTC). Hard stop.**
Preconditions all enforced in code already: fresh snapshot ≤45min, five arms on
registered config, `MAX_TOKENS` registered, cell-major, ceiling armed, sandbox
namespace isolated, served-model provenance captured. Run
`--readiness` first (spends nothing). **One attempt.** If it voids, the void
reason is the deliverable — no third attempt without Murat. If VALID: report
operational results and cost only. **Do not read H1.** Do not auto-start the
remaining 39.

**M3. G1 + G2 — the two defects above.** Recalibrate the gate, add the three
denominators, add n_effective and MDE, restate `RESEARCH_GYM_1.md`. This blocks
M4 and M5, because a mechanism extracted from a mis-denominated surface is a
mechanism extracted from noise.

**M4. AUTOPSY-TO-RULE-1.** The substrate exists; this is the ordered brain
build. Structured output only: contemporaneous evidence · post-outcome evidence
(kept separate) · failed assumption · proposed mechanism · executable precursor
· expected affected states · expected *un*affected states · falsifier ·
alternative explanation · minimum transfer tests. Optimus may see the outcome
during autopsy. **The episode that generated a rule may never prove it** —
that wall already exists in `request_export`; wire the autopsy through it
mechanically rather than by convention. A rule that only explains its parent
dies, and the death is ledgered.

**M5. Gym phase 2 — corpus + REGRET_TENSOR.** Expand well beyond 66 SPY
decisions: many securities, indices, regimes, crises, ordinary periods,
sectors, cap buckets, vol states. Full action surface × horizons
{1,5,20,60,120,252}. Store the **entire** surface, never the winner. Build
`state × action × horizon → regret distribution` — with all three denominators
from M3 baked in from the start. The question is *"which actions are bad in
which states"*, never *"which parameters maximised 2010–2025"*.

### THEN — if the above are genuinely finished

**T1. Actor Surprise** (Teacher Library). `P(action | actor history, issuer
state, market state)`, PIT-safe. First discretionary buy in N years · size vs
the actor's own history · role · independent-insider clusters · first cluster
after drawdown · opposite actions · 10b5-1 status · event proximity. **Keep
BUY/SELL/TRIM/EXIT/COMPENSATION/NON-DISCRETIONARY/UNKNOWN separate.** No single
universal insider score. Study losers with the same machinery — otherwise this
becomes reverse-engineered hagiography.

**T2. Wire teacher events into COPY-LAB** — only after M1 proves the collector
live. Forward only, no historical fills. First lane
`CORPORATE_INSIDER_CLUSTER`, plus a `FORM4_RANDOM_MATCHED` shadow control.
`ACTIVIST_13D` stays blocked until real 13D ingestion exists.

**T3. Matched teacher controls** (sector, cap, beta, momentum, vol, drawdown,
liquidity, event proximity, regime) before any insider winner is interpreted.

**T4. Stress-shape investigation (P4).** Level *and* change *and* acceleration;
term structure, vol-of-vol, breadth, credit, liquidity, drawdown depth/speed,
revisions, dispersion, correlation spike, reversals. Candidate latent states
(CALM/DETERIORATING/PANIC/CAPITULATION/STABILISING/RECOVERY) are **candidate
representations, not labels asserted as truth**. Compare thresholds vs
splines/GAM vs trees vs HMM. Do not force monotonicity where the empirical
shape is non-monotone — and do not force a U either.

### DEFERRED — do not start

- **Policy stability topography** (P6) — right idea, comes with the search.
- **Known-answer worlds** (P7) — the entrance exam. High value, next session.
- **AEGIS-EVOLVE-GYM-1** (P8) — gated behind P7.
- **WORLD-MODEL-v1** (P14) — **now authorised in principle by Murat**, reversing
  my R7, but gated behind: known-answer worlds exist · episode/regret substrate
  usable and *correctly denominated* · simple baselines defined. Never
  all-data→NN→BUY/SELL. Self-supervised encoder, independent supervised heads,
  direction is *a* head not the objective. It earns complexity only by beating
  naive/linear/GAM/LightGBM out of sample. LLM judgement is never the target.
- **OOD / "I don't know" model** (P15) — genuinely novel, keep it; queue it.
- **Absence signals** (P16) — keep `OK_EMPTY` and `UNAVAILABLE` distinct; never
  encode source-unavailable as absence. Queue it.
- **Mechanism Graph** (P12) — the most novel idea on the list and the right
  long-term shape. It needs mechanisms to exist first; M4 produces them.
- **REACTION-GAP-1** (P13) — measurement study first, no trading rule. Queue.
- Reopening GRAPH-COVARIANCE. Pooling forward populations. Reading accruing
  trials.

## 5. Standing

All adaptive search stays inside `RESEARCH-GYM-1`. No Gym result is an alpha
claim, and `GymResult.as_claim()` must keep raising. Every new registered trial:
corpse check · frozen primary endpoint · MDE · placebo family · read schedule ·
provenance · no hidden parameter search. Aggressive exploration, strict
promotion. **The more adaptive the brain becomes, the more load the referee
carries — do not weaken it because the brain is getting good.**

The 112 LIVE_FORWARD rows still sit on the volume. The guard prevents the false
claim, so it is not urgent; quarantine them under a dated migration receipt
**attended, after the 08-16 resolutions**, so the two events cannot be confused.

## 6. Report back in this order

1. Production clocks — collector receipt, paid night, job receipts
2. G1/G2 — recalibrated gate, restated Gym numbers, n_effective + MDE
3. Gym — episodes, counterfactual rows, regret tensor, classifications, **no claim language**
4. Autopsy — mechanisms generated, executable, transfer slices, refutations
5. Teacher Library — production events, actor surprise, COPY-LAB eligibility, no fake history
6. Defects found **by running checks rather than by review**
7. Tests / SHAs / deploy verification
8. Next bottleneck

Do not stop because a clock is not yet eligible. Move to the next independent
order and return when it opens.

— brain, 2026-08-15
