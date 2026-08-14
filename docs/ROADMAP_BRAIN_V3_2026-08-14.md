# ROADMAP — BRAIN V3 (post-GRAND-ARENA, 2026-08-14)

**Written 2026-08-14**, from the GRAND-ARENA-1 verdict, the NIGHT-14
architecture review, and Murat's direction of 2026-08-14. **Supersedes the
sequencing** (not the standards) of `ROADMAP_LEARNING_LOOP_2026-08-12.md` for
the LLM/learning arc, and **inherits its two load-bearing dependency edges**:
the bandit router waits for a resolved reliability tensor, and any RL gym waits
for known-answer worlds. The certification gates in
`AEGIS_EXECUTION_ROADMAP.md`, `CANON.md` §13–§20 and the Execution Standard
(6bafef2) all still bind.

The active build handoff derived from this roadmap is
`HANDOFF_OPUS5_2026-08-14.md`.

---

## The organising shift

GRAND-ARENA-1 did not find an LLM that picks stocks. It found the first place
where the LLM demonstrably carries information the numerical engine does not:
**economic relationships between companies** (MARKET-GRAPH-1 H1, ΔR²
+0.000968 vs MDE 0.000623, t = 4.35, placebos intact — a co-movement/risk
result, `ARCHITECTURE_RESULT_ONLY`).

So the pivot is:

> **Stop using the LLM as an analyst that scores stocks. Start using it as a
> perception system (what changed, who is connected to whom) and as a
> scientist (why did this happen, what precursor generalises) — and let
> numerical models learn from reality whether what it perceives matters.**

Aegis itself does not get rebuilt. Aegis is the referee, and the referee has
been the most valuable component all campaign. What gets rebuilt is the brain
around it.

---

## Scoreboard the roadmap is built on (receipts, not vibes)

| claim | verdict | receipt |
|---|---|---|
| LLM semantic relationships carry co-movement info beyond trailing correlation | **DETECTABLE** — the campaign's only clean positive | `MARKET_GRAPH_1.md` H1: ΔR² +0.000968 / MDE 0.000623, t=4.35; 10.8% of baseline squared error removed on edge pairs; shuffle placebo t=−0.22; survives cross-2-digit-SIC |
| Semantic edges are directional/causal | **NOT ADOPTED** | H2 reversed-direction control at 89% of its own MDE — open, not killed |
| LLM scores add portfolio alpha | **NOT DEMONSTRATED** | full−no_llm +3.37 %/yr but shuffled−no_llm +1.37; p 0.105→0.185; ~40% of the apparent contribution reproduced by permuted noise ⇒ `PRESENTATION_AND_RESEARCH_ASSISTANCE` |
| 14 personas > 1 generic agent | **NO** | swarm−generic −0.60 [MDE 9.69]; effective distinct ideas 0.49 vs 0.85 at 5.2× the calls; generic best Sharpe in family |
| Regime conditioning improves selection | **NO EVIDENCE** | 35/36 arms inside MDE; the one exception dissolved on beta-matching |
| Exposure is where information is economically largest | **YES** | timing oracle 10.4× its MDE (best observable controller captured 7.4%); **selection oracle 0.64× — not even the oracle is detectable** |
| Mechanical exits / learned trading policies | **NEGATIVE** | EXIT-LAB: every point estimate negative; best baseline `NEVER_SELL`; LightGBM controller pays 592 bps/yr turnover |
| Historical LLM leakage | **CONCENTRATED, not uniform** | masking 0/399, recall 0/419 ordinary rows; famous-event positive control 7/10 recalled, 7/7 directions correct |
| A conditioned rule can be evaluated against an unconditioned baseline | **NEVER AGAIN** | permuted-label placebo is NOT centred on zero: −7.024 pp/yr in the selection family (0/20 seeds positive) from window-shortening alone |
| deepseek-chat vs deepseek-reasoner is a model comparison | **VOID** | both are silent aliases for `deepseek-v4-flash`; real ids are `v4-flash` / `v4-pro`; served model now recorded per call |

---

## Instruments that now bind on every new trial

1. **The placebo trio for anything conditioned.** Real state vs permuted state
   (same persistence/frequency) vs unconditional. Without the permuted arm,
   window-shortening mechanics read as discovery.
2. **The famous-event flag.** Historical LLM experiments are usable as
   *architecture* experiments only: flag/exclude famous events (the recall
   canary proved memory is sparse but real there), keep masking + recall
   controls, and never promote historical LLM alpha.
3. **Served-model recording.** Every LLM call logs the model the API *served*,
   never the name asked for.
4. **The belief-change contract.** Replace the `p ≠ 0.50` refusal with
   `prior / posterior / belief_change`. "This information changed nothing" is a
   valid, gradeable output; the candidate signal is `posterior − prior`, not
   the level.
5. **Sparse triggers over universal coverage.** The LLM wakes on unusual states
   (abnormal residual, revision, skew shift, filing, semantic-graph change),
   not on 459 tickers daily. Manufactured opinions were the swarm's failure
   mode.
6. **Permuted-noise placebo for any LLM score family** (the identical-score-
   distribution shuffle from chunk 9) — mandatory before any ablation claim.
7. Everything already standing: pre-register + corpse check + `lint_prereg.py`
   before accrual; every arm prints its 80%-power MDE (§19); grading clock at
   horizons (1,2,5,20,60,120,252); LLM narrates, engine computes; no skill
   claims before 24 months of forward record.

---

## The tracks

A–D were written 2026-08-14 from the post-arena position; **E was added the same
day** on Murat's direction and is the only one whose subject is a new *data
class* rather than a new method.

### Track A — close out GRAND-ARENA (small, mostly waiting)

- Let forward records resolve (first resolutions **2026-08-16**) and append
  `ABLATION_FWD` automatically. The retrospective verdict does not change.
- Fix the model-diversity arm properly: genuine `deepseek-v4-flash` vs
  `deepseek-v4-pro`, served model verified per call.
- Keep the ledger resolving daily (`pi_ledger_resolve`).

### Track B — exploit MARKET-GRAPH-1 H1 (highest-priority research family)

The one surviving result is a *relationship* result, so its descendants are
relationship experiments:

- ~~**GRAPH-COVARIANCE-1**~~ — **CLOSED 2026-08-14, and it closes the family.**
  See `GRAPH_COVARIANCE_1.md`. H1 and H2 both `NOT_DETECTABLE` (semantic −
  numeric = −0.000369 annualised vol against MDE 0.000384, t = −2.69 — inside
  its own MDE and pointing the wrong way), with all three placebos clean
  (−0.06%, −0.02%, +0.03%). The pre-registered power gate failed, and chasing
  why produced the result that matters: **perfect foresight of the realised
  forward correlation matrix is statistically indistinguishable from the
  trailing sample matrix** — risk reduction of `oracle_full` over `sample` =
  **−0.000158** (perfect foresight realised marginally *higher* risk) against
  MDE 0.001916, **|t| = 0.23**, and not detectable at any eigenvalue floor
  tested — while the industry-standard diagonal specific-risk assumption is
  **86.6% worse at t = 12.60**. The metric is not blind; the headroom left for
  any correlation predictor is **bounded at ≤15.4%** of the gain the trailing
  matrix already delivers over the diagonal assumption. Stated as a bound, not
  an absence: `not detectable` is not `zero` (§19). **The closure is pool- and
  objective-specific** — minimum-variance realised volatility, N≈300 US
  large-cap, 126-day horizon, 2015–2024 — and reopening it requires a new
  pre-registration naming which of those four boundaries changed.
  Two reusable instrument rules were earned: entrywise
  correlation MSE and portfolio risk are different loss functions that here
  disagree by 45% in opposite directions; and an oracle must be built *inside*
  the architecture it is the ceiling for, or its own scale-inconsistency
  becomes the finding. **Do not build GRAPH-SHRINK-1 or any further
  "improve the covariance matrix" descendant.** $0 LLM spend.
  MARKET-GRAPH-1 H1 is untouched — only its route through a minimum-variance
  solve is closed.
- **REACTION-GAP-1** (GRAPH-SHOCK) — event surprise × semantic edge × expected
  propagation vs observed reaction; do under-reacting neighbours catch up in
  residual terms?
- **SEMANTIC-SYSTEMIC-RISK-1** — semantic graph density/concentration over
  time as a predictor of correlation spikes, factor crowding, drawdown.
- **MARKET-GRAPH-2** — the directed lead/lag question H2 left open, powered
  properly this time (more directed edges; the 89%-of-MDE null is a power
  problem, not a kill).
- **SEMANTIC-NUMERIC-DIVERGENCE-1** — the strong-semantic / weak-statistical
  cell: do statistical relationships emerge later where the LLM already sees an
  economic link?

### Track C — build the actual brain (replaces the persona swarm as frontier)

- **INTERNET-INVESTIGATOR-FWD-1** — **REGISTERED AND FROZEN 2026-08-14; status
  CONDITIONALLY GREEN-LIT, Night 1 not yet run.** Forward-only. The design as
  built differs from this roadmap's original sketch in three ways, each from a
  measurement made before any money was spent:

  - **Five arms, not four.** `A_snapshot` (engineered numbers only) /
    `B_tools` (snapshot + search, filings, IR, options, revisions, prices,
    market graph) / `C_tools_only` / `D_all` (engine + tools + graph) /
    `B_anon` (B with ticker identity masked — NEGATIVE_RESULTS §19's leakage
    receipt, run as an arm rather than argued about). `PRIMARY_CONTRAST` is
    `A_snapshot` vs `B_tools` and is named in the frozen config, so the
    best-looking pair cannot become "the" result afterwards.
  - **The primary observable is MAGNITUDE, not direction.** `iif1_sigma.py`
    measured σ_π at **0.0036–0.0061** on the direction observables against
    **0.1183** for 5%/5d absolute move — a 20–30× difference in how
    forecastable they are at all. Cross-referenced with `iif1_power.py`, a
    direction primary reaches 80% power at **no** trigger count and **no**
    effect size, i.e. it is a trial designed to be unable to speak (§19).
    Direction observables are still recorded, and are **pre-declared unable to
    resolve** — a null on them is neither kill nor win. This is the **third
    independent instrument** pushing the programme from direction to
    magnitude/risk, after the exposure-vs-selection oracle gap and GC1's
    diagonal result.
  - **A read SCHEDULE, not a read floor.** Three licensed looks at **40 / 80 /
    120 graded nights**. `iif1_boundaries.py` simulated what three looks at the
    flat house constant would cost: family-wise **0.1079** against a single
    look's 0.0501, **2.2× the declared rate**. So each look carries its own
    O'Brien-Fleming constant — **MDE_Z 4.312 / 3.295 / 2.845** — solved to a
    family-wise 0.0505. The final look pays almost nothing for the two peeks.
    Enforced in `iif1_read_gate.py`: a read at 41, 79 or 119 is refused as
    firmly as at 39, and 121 is `NEW_PREREG_REQUIRED`.

  **Verdict language is bound in advance** (`iif1_read_gate.CLAIM_LANGUAGE`): a
  positive H1 is the claim *"autonomous investigation improves
  magnitude/volatility forecast calibration"*. Never stock picking, never
  alpha, Sharpe, skill or tradability — the trial forecasts no return and
  trades nothing, so no such claim is available to it at any n, including a
  positive one at the final look. The gate refuses a verdict line containing
  them.

  **Terminal rule, frozen before Night 1:** 40/80 below the bar →
  `INTERIM_UNDERPOWERED`, carrying no H1 reading in either direction; 120 below
  the bar → the pre-registration **terminates** `NOT_DETECTABLE`; accrual past
  120 requires a new prospective pre-registration. Anything softer just moves
  optional stopping from 40 to 120.

  **Budget framing:** $37.12 ÷ 40 = **$0.928/night is the planning number.**
  The $10–15 ceiling is a safety stop, not a budget — a $4 night is not "under
  budget", it is nine fundable nights out of forty. `project_funding()` prints
  the gap on every receipt, and the funding decision is made before the accrual
  clock starts.
- **Microtask decomposition** — event extractor, relationship extractor,
  expectations analyst, forecaster, critic as separate small contracts, instead
  of one giant common schema. Division of cognition, not personas.
- **WHY-QUEUE** — the nightly self-questioning loop: largest unexplained
  residuals, biggest engine-vs-LLM disagreements, most-confidently-wrong
  predictions → researcher → skeptic → machine-testable precursor → verdict →
  memory.
- **Experience memory** — every serious resolved mistake stored as a structured
  Experience (state, belief, why, outcome, which assumption failed, lesson) and
  retrieved before analysing similar states. Continual learning without
  fine-tuning.
- **AUTOPSY-TO-ALPHA-1** — hindsight used *deliberately and legitimately*: the
  LLM studies known winners/losers WITH the outcome, proposes mechanisms and
  observable precursors; the subject is then removed and the precursor rules
  are tested on unrelated securities/periods it never saw. Famous-event flag
  and masking controls apply.
- **WINNER-vs-LOSER-TRAJECTORY-1** — tournament/professional winners vs
  matched same-risk losers as contrastive pairs; which behaviours (entry,
  adding, cutting, rotation, concentration) distinguish them, tested out of
  sample.
- **OUTCOME-REASONING-DISTILL-1** — once forward outcomes resolve, learn which
  *styles of reasoning* were reliable in which states (preference pairs over
  resolved reasoning chains). Blocked on resolutions; do not train on
  unresolved forecasts — that teaches DeepSeek-imitation, not markets.

### Track D — neural fusion (the NN, built the earnable way)

Not `all data → NN → BUY/SELL`. Return labels are the noisiest target in
finance and KNOWN-WORLD showed learners invent timing edges in worlds with none.

- **MARKET-WORLD-MODEL-1** — self-supervised latent representation of
  company-day / market-day states from prices, fundamentals, revisions,
  options, macro, semantic events and both graphs; then **supervised heads on
  dense reality targets first**: future correlation/co-movement (the one
  target with a proven semantic signal), future volatility, covariance,
  abnormal residual moves, contagion after shocks, revision direction. Raw
  return prediction comes last, if at all.
  **Binding constraint from GRAPH-COVARIANCE-1 (CANON §21):** every head is
  graded under the loss function its output will actually be used under, not
  a surrogate. The parent's semantic signal is real on entrywise co-movement
  and measurably does NOT transfer to a min-variance portfolio objective —
  a correlation head graded on entrywise error alone would reproduce that 45%
  gap. If a head's output feeds a portfolio decision, its validation metric is
  the portfolio-level loss.
- **The comparison that legitimises any GNN:** numeric-only LightGBM vs
  numeric+semantic features vs numeric graph vs semantic graph vs fused
  temporal GNN — same targets, same purged walk-forward folds, same MDEs.
  Simple ML is the baseline; a GNN must earn its complexity.
- **LLM as weak-label teacher, reality as judge:** DeepSeek labels event type /
  mechanism / novelty / beneficiaries at corpus scale (cheap on v4-flash);
  the market supplies the truth labels. The circular loop (NN says X → LLM
  likes X → NN says more X) is forbidden by construction.
- **AEGIS-EVOLVE-1** (later, after Track B/C produce features worth searching
  over) — LLM-proposed strategy programs in a constrained DSL, evaluated by
  Aegis, evolved with a robustness fitness (multi-period, cost-surviving,
  cross-regime, complexity- and search-penalised). The AlphaEvolve/RD-Agent
  pattern with our referee. Full genealogy; search deflation applies.
- **RD-AGENT-BENCH-1** — run Microsoft's RD-Agent-Quant (and one strong public
  financial-ML baseline) on OUR data, dates, costs, PIT rules and benchmark.
  Either it beats us under our ruler and we learn, or its edge dissolves under
  our controls and we learn that too.

---

### Track E — TEACHER-LIBRARY-1: public actors as a data class (added 2026-08-14, Murat's direction)

**The hypothesis is NOT "Pelosi/Cramer/insiders know things, copy them."** The
literature's prior is that the mean congressional portfolio is unremarkable
(STOCK Act studies, 2012–2023). The hypothesis is: **publicly observable
investment decisions contain conditional behavioural/informational structure —
learn which actors × actions × contexts × disclosure patterns carry
information, and whether it survives the transaction→publication delay.**

**Predecessors are LIVE, not dead — build around them, not over them:**
`TRIAL-CONGRESS-IC` (earliest decision 2027-01-11), `TRIAL-INSIDER-IC` /
`TRIAL-CMP-INSIDER-IC` (2027-07-21), `TRIAL-ARK-IC` — all forward-accruing.
Their clocks are untouched; TL-1 adds the **historical bulk layer** (SEC
insider transactions 2006–2026, official 13F 2013–2026, House/Senate PTRs —
all free) plus the behaviour taxonomy. The 13F-popularity corpse (top-3-holding
count: rank info in small caps t(IC)=2.70, **net-dead book**) is the mandatory
control for any 13F descendant.

Build order:
1. **Canonical public-action ledger** — `actor_id/type, security, action,
   transaction_date, public_at, filing_at, size band, ownership attribution,
   source, provenance`. **`public_at` is the only signal timestamp.** Tier 1 =
   SEC/House/Senate primary; trackers are Tier-2 enrichment, never ground
   truth. Sources with unreconstructable publication history are collected
   forward-only from now.
2. **Prerequisite fix before scaling Form 4:** the raw source contract must
   distinguish `OK_EMPTY` / `OK_DATA` / `UNAVAILABLE` — `fetch_open_market_buys`
   currently returns the same empty shape for "no purchases" and "SEC lookup
   failed" (the house silent-fragility mode, and this collector already has a
   prod-403 history).
3. **Behaviour extraction, not celebrity scores** — `NEW_POSITION`,
   `CONVICTION_ADD`, `TRIM`, `FULL_EXIT`, `CLUSTER_BUY`,
   `PRE_EVENT_POSITIONING`, `POST_DRAWDOWN_ADD`, `WINNER_HELD`, `LOSER_CUT` …
   → actor × domain × behaviour reliability, resolutions only.
4. **First hypotheses, each separately pre-registered with its corpse:**
   H1 insider cluster purchases (residual outcomes post-`public_at`); **H5
   teacher activity predicts MAGNITUDE/risk even where direction is absent** —
   run H1+H5 first (free data; aligned with the programme's thrice-measured
   direction→magnitude convergence). H2 congressional-contextual, H3
   specialist conviction-change (13F-popularity corpse as control), H4
   cross-teacher agreement (must be genuinely independent channels, not three
   republishers of one filing) follow.
5. **Hindsight behind the firewall** (AUTOPSY-TO-ALPHA pattern): actor's
   winner studied WITH outcome → mechanism → actor/security/event excluded →
   precursor tested on unrelated securities/periods. **Masking trio binds
   (§13 extended):** unmasked / ticker-masked / identity+calendar-masked; the
   arm difference IS the leakage measurement; famous-event flag applies.
6. **Teachers are features and weak labels, never training targets.**
   Supervised targets remain realised outcomes (residual return, vol,
   covariance, drawdown, event response).
7. **No RESEARCH shadow lanes on day 1.** Feature-level results earn research
   lanes; lanes go through `seed-a-lane` (attended, Murat flips flags). Paid
   normalizers (Quiver/Capitol Trades) are an attended purchase decision taken
   only after the free Tier-1 build measures the gap they'd close.
8. **One PRODUCT lane is authorised by Murat (2026-08-14): `TEACHER-COPY`** —
   a paper account that literally copies flagged public actors' disclosed
   portfolios (insider clusters and/or congressional disclosures). This is a
   product-side decision, explicitly NOT a research claim, and it is his to
   make. Conditions that keep it honest anyway: entries only at `public_at`
   (never `transaction_date`); a risk-matched benchmark plus SPY beside it
   from day one; labelled `PRODUCT_LANE` in the lane YAML so no verdict ever
   cites it as evidence; seeded through `seed-a-lane` (attended, env-gated).
   Run this way it costs nothing extra and doubles as a live measurement of
   the disclosure-delay problem the literature predicts.

**Sequencing:** TL-1 starts after IIF-1's Night 1 is running cleanly — the
pilot does not share attention with a new lane's build-out.

---

## Closed doors (do not reopen without new evidence)

- **SWARM-3 / persona-count scaling.** Answered twice (prompt statistics and
  portfolio outcomes). Retired.
- **End-to-end RL trader on one realised history.** KNOWN-WORLD: learners
  happily invent timing edges; cash looks safe under uncertainty penalties.
  Any RL waits for known-answer worlds, per the inherited dependency edge.
- **Semantic-teacher NN trained on unresolved forecasts.** ~20k forward records
  had zero outcomes at campaign close; training on them imitates the teacher.
- **Mechanical exits / trailing stops / regime-conditioned selection** — the
  negative results stand (EXIT-LAB, §15, REGIME-ARENA).
- Everything in `NEGATIVE_RESULTS.md`. Corpse check before every registration.

---

## LLM budget (as of 2026-08-14, Murat's console)

- Balance **$37.12**, lifetime spend **$22.87**, 51,670 requests,
  159.85M tokens. Real per-call cost ≈ $0.00039; cached input 50× cheaper.
- The **dollar ceiling binds, not the call ceiling** (commit 9f6c424).
  Night-scale work should budget **$10–15/night** and log spend from served
  responses, not estimates. $0 spent on an LLM night is a defect (NIGHT-10
  ruling); so is an unexplained overrun.

---

## What "breakthrough" would mean from here

Research-side, any one of: semantic priors reliably improving dynamic
financial-graph prediction; reaction gaps along learned edges predicting
subsequent abnormal returns; hindsight-guided precursor rules reproducing on
unseen securities/periods; an evaluator-driven evolutionary search finding
robust rules human search did not contain.

Product-side: an autonomous brain that investigates, explains what changed,
maintains a portfolio through the engine, learns from resolved mistakes — with
each intelligence layer's contribution *measured*, because that measurement
discipline is the thing this programme has that others do not.

No breakthrough is claimed until a descendant of MARKET-GRAPH-1 demonstrates
portfolio value under its own pre-registered bar. The GRAND-ARENA-1 "no
breakthrough" verdict stands until then.
