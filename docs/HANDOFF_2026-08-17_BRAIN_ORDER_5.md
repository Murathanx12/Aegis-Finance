# ORDER 5 — reconciled. Supersedes both order-4 documents.

Binding. Every claim below was checked against code at the SHA named, not
against a report.

**State, verified 2026-08-16:** `aegis-finance` @ `725f5e8` (clean tree),
`Aegis module` @ `8b93610`, CI green, prod on `2ba9fb3`, $0.00 spent last
session.

**Why this document exists.** Two order-4s were written independently against
different tips: the principal's review (written against `2ba9fb3`) and the
builder's `docs/HANDOFF_2026-08-17_BRAIN_ORDER_4.md` (`725f5e8`). They agree on
almost everything and converge on the same P1. They disagree on *why*, and on
one point **the arithmetic settles it against the builder.** Read this document
instead of either; where they are not contradicted here, both stand.

---

## 1. RULING — partial sizing does NOT lower the break-even lift. δ cancels.

Order 4 §3 (builder) says the 1.69 bar is a property of the action, and that a
signal moving exposure 1.0 → 0.7 "forgoes 30% of `μ_rest`, not 100%", so
`L_min` falls, possibly below N9's confirmed 1.271.

**The first half is right. The conclusion is wrong.** Reducing exposure by δ
forgoes δ·`μ_rest` *and* captures only δ·|`μ_tail`|. With turnover cost
proportional to δ — which it is; `COST = 0.0010` at
`scripts/n4b_coverage_equivalence.py:59` is declared as the round-trip cost of a
*full* exposure change — δ factors out of both sides of the inequality exactly:

```
δ·L·q·|μ_tail|  >  δ·(1−L·q)·μ_rest + δ·c₀
⇒ L_min = (μ_rest + c₀) / (q·(|μ_tail| + μ_rest))     — unchanged in δ
```

Checked numerically against the live ledger
(`backend/data/optimus/research_gym/n4b_coverage_equivalence.json`):

| H | μ_tail | μ_rest | L_min δ=1.0 | δ=0.3 | δ=0.1 |
|---|---|---|---|---|---|
| 20d | −11.20% | +2.158% | **1.6907** | **1.6907** | **1.6907** |
| 60d | −18.24% | +4.742% | **2.1065** | **2.1065** | **2.1065** |

A partial-sizing prereg written on the builder's stated reasoning would have
been refuted by algebra before it touched data. **Do not open it.**

### What actually moves the bar — and this is the principal's objection, and it is visible in the code

`μ_rest` is computed at `n4b_coverage_equivalence.py:205` as
`f[~mask].mean()` — the mean over **all non-tail observations in the sample**,
unconditional. The payoff mapping then charges a firing precursor the
*unconditional* non-tail drift. The principal's point is exactly this: a
precursor that fires before −6%, −4%, −3% moves and slow drawdowns that never
enter the bottom decile has `μ_rest | fire` **below** the unconditional
`μ_rest`, and nothing in N4B measured that.

It is the whole result. Sensitivity at H=20d, μ_tail = −11.197%:

| `μ_rest \| fire` | `L_min` |
|---|---|
| 2.158% (unconditional, what N4B used) | 1.691 |
| 1.80% | 1.462 |
| **1.516%** | **1.271 — N9's confirmed lift** |
| 1.20% | 1.049 |
| 1.00% | 0.902 |
| 0.50% | 0.513 |

**N9's frozen rules clear break-even iff `μ_rest | fire` < 1.516% per 20 days
(unconditional 2.158%, gap 0.642pp) or < 2.542% per 60 days (unconditional
4.742%, gap 2.200pp).** The 20d gap is small enough that it could fall either
way. That single conditional mean is the most decision-relevant unmeasured
number in the programme, and it is one line on data already on disk.

The three things that genuinely change `L_min`, none of which is partial sizing:

1. **Conditional `μ_rest | fire`** — above. Measure it first.
2. **The objective.** `L_min` is derived under arithmetic mean return. Under
   expected log growth, avoiding a −11% move is worth more than its arithmetic
   contribution (variance drag). This is very likely why N12's vol targeting
   wins at matched vol with no return edge, and it means the break-even must be
   recomputed under the *declared* objective, not under total return.
3. **A convex payoff.** A put hedge pays a premium on every firing day and a
   non-linear payoff on tail days, so neither term scales in δ. This is a
   different inequality, not a rescaling of this one — and since options are
   priced fairly on average, it is where Opportunity Gap earns or dies.

### Order

The principal's direct test **supersedes the algebra** and is what to run:

```
utility(frozen policy | fire) − utility(HOLD | same episodes)
```

on untouched observations, over the full return path, with real exposure change
and cost. Report terminal wealth, expected-log contribution, drawdown, ruin,
turnover. `PolicyResult.wealth_path` and `utility.path_stats` already carry
every one of those. Keep the algebra anyway: it names what to measure and makes
a falsifiable prediction (the 1.516% / 2.542% thresholds) that the direct test
can confirm or embarrass.

**Restate N4B now, before the test runs:** the library is `REFUTED_IN_SCOPE` as
a *full de-risking trigger evaluated under unconditional `μ_rest` and an
arithmetic-return objective*. Sizing, hedging, and any log-utility objective are
`UNTESTED`. New action ⇒ new prereg ⇒ new slice (§4).

---

## 2. RULING — the OptionMetrics contradiction is resolved. It is NOT blocked.

The principal asked whether the blocker is entitlement, availability,
credentials, or a script that never connected. **Answer: none of them. The data
is on disk and has been since 2026-08-01.**

`C:\Users\mrthn\Aegis module\data\wrds_raw\`:

| Artifact | Content |
|---|---|
| `optionm_vsurf_me/` | **23 files, `vsurf_me_2002.parquet` … `vsurf_me_2024.parquet`, 183 MB** |
| `optionm_opvol_daily/` | daily option volume, 2002– |
| `optionm_secnmd.parquet` | 272,255 rows / 120,578 secids |
| `optionm_crsp_link.parquet` | `wrdsapps.opcrsphist`, 121,773 rows — secid↔permno with sdate/edate |
| `manifest_optionm.json` | `fetched_at_utc: 2026-08-01T12:27:44Z`, purpose "P0b — OptionMetrics surface + option volume" |

**`backend/data/signal_registry.yaml:681` says
`data_grade: OptionMetrics entitlement was never established`. That line is
false. Correct it in this session** — it is the reason a whole session recorded
"no licence" as fact, and a stale registry line that closes a data family is the
same defect class as a false kill compiled into source.

Two caveats to verify before building on it, **not** reasons to defer:

- Row counts (~226k rows / ~2,588 secids in 2002) are ~87 rows per secid-year,
  which is **not** daily. Determine the actual snapshot frequency before
  declaring the rung PIT-daily; a month-end surface still supports a monthly
  rung and still supports the ladder.
- Coverage ends **2024**. IvyDB updates annually, so this is a research
  instrument, not a live feed. Any conclusion is scoped to ≤2024 and the live
  product still needs `options_intelligence.py` / VIX for the forward path.

Then add the rung, and restate the vol verdict as `NOT_DETECTABLE_IN_SCOPE`,
scope = *forecasters constructed from realised-volatility history*; implied vol
`UNTESTED`. Both order-4s agree on this restatement and it costs nothing.

---

## 3. RULING — grade the vol ladder on loss, not only on IC

The principal is right and it is the same error twice. The ladder is scope-
incomplete (no forward-looking rung, §2) **and** metric-incomplete: sizing
consumes the *level* of volatility, and IC only ranks it. Two forecasters can be
IC-identical and produce materially different exposures.

Add, on the existing rungs before adding the new one: **QLIKE, MSE / log-MSE,
Mincer–Zarnowitz calibration slope and intercept, tail forecast error, and
downstream vol-targeting utility** (the last is the one that matters — it is the
only metric denominated in the declared objective). "Indistinguishable at paired
MDE 0.005–0.010" is a powered null **about IC**, and must be labelled as such
until the loss metrics run.

The product conclusion is unaffected either way and stands: do not spend the
first NN on ordinary realised-vol forecasting; take the cheap baseline.

---

## 4. RULING — N12's matched-vol scaling is ex-post. Code-verified.

`scripts/n12_vol_targeted_sizing.py:126` — `scale = ref_vol / pv`, where `pv` is
the policy's **full-sample** realised volatility. The principal's caveat is
correct: this is a legitimate scientific comparator and **must never appear in a
deployable rule.** Live exposure is set from information available at `t` only.

Add the guard rather than the note: any policy consumed by the paper book or the
shadow book must fail loudly if its exposure path depends on a statistic
computed over its own future. The programme's house failure mode is code that
runs green and silently does the wrong thing; a comment is not a guard.

Second, the principal's other point stands: four long asset histories are four
paths. The next sizing experiment is a sequential walk-forward portfolio over
many decision periods compared on realised compound wealth.

---

## 5. Gate statuses — corrected, with the evidence

| Gate | Order-4 status | **Ruling** | Evidence |
|---|---|---|---|
| G1 referee | PASSED | **OPERATIONAL / PROVISIONALLY STRONG** | A compiled false kill was found *this session* (`n4_precursor_coverage.py:207`, now fixed). A referee is never "unfoolable"; it is passed when the known-answer worlds recover known truths at declared FP **and FK** rates. That battery does not exist — `grep` for `known_answer\|synthetic_world` returns nothing. |
| G2 regime→event | PASSED | **PASSED for high-frequency event families**, not for every question | 25 crisis episodes ever vs 1,746 insider filings/day; N8's curve resolves ≥10pp only. |
| G3 objective | NOT STARTED | **PARTIAL** — principal is right | `utility.py` has `PathStats`, drawdown, time-under-water, ES, ruin, CRRA, `break_even_gamma`, `EXPECTED_LOG_GROWTH`, `LOG_GROWTH_WITH_RUIN`, and refuses the per-path-log mistake. `PolicyResult.wealth_path` landed (`policies.py:67`). |
| G4 expectation | NOT STARTED | **NOT STARTED — confirmed** | zero hits for `expectation_layer`. Both orders agree it is the most important missing abstraction. |
| G5 world model | NOT STARTED | **NOT STARTED — confirmed** | zero hits for `world_model`. |
| G6 sizing learner | — | **PARTIAL** | N12 is a baseline sizing policy; no learned policy. |
| G7 forward cert. | NOT PASSED | **infrastructure ready; zero resolved campaign evidence** | a `--commit` dry run is not forward evidence. |

**G3's remaining gap, named precisely so it can be closed:**

- `counterfactual.py:91` — `ranked(objective=None)` silently sorts on
  `net_return_pct`. The docstring justifies the default (not restating
  published numbers) and that reasoning was sound at the time, but the
  principal's rule is stricter and correct: **no path may fall back to raw
  return without naming `total_return` explicitly.** Make `objective` required,
  or make `None` resolve to the literal `TOTAL_RETURN` object so
  `objective_used()` cannot return the word "implicit".
- `counterfactual.py:126` — `regret_pct()` calls `self.best()` with no
  objective. Same fix.
- `OBJECTIVES` currently holds `total_return`, `sortino`,
  `drawdown_penalised` (×2), `expected_log_growth`,
  `log_growth_with_ruin_constraint`, `aggressive_growth`. **Three of the four
  declared personalities do not exist:** capital preservation, balanced,
  extreme growth. Add them as explicit utility/risk constraints, not as strategy
  names.

---

## 6. Priorities

**Attended — Murat's, all unblocked, surface all three with their numbers:**
campaign `--commit` (110 due / 110 resolvable / 0 unpriceable, ledger SHA
`ff458c77…` unchanged under dry run) · the `LIVE_FORWARD` quarantine (this is
what clears DEGRADED; the mount question is closed and the 112 records are
identified) · the paid night ≤12:20 UTC.

**P1 — the direct action test (§1).** `utility(frozen policy) − utility(HOLD)`
on untouched observations. Measure `μ_rest | fire` on the way and report it
against 1.516% / 2.542%. Do the same for N9's frozen rules: preserve the
coverage finding exactly, and score the rules as policies rather than inferring
economics from a lift.

**P2 — the two corrections that cost nothing:** fix
`signal_registry.yaml:681`, add the implied-vol rung, restate the vol verdict
with its scope, and add the loss/calibration metrics (§2, §3).

**P3 — `WINNER_MATCHED_LOSER_FACTORY_V1`.** The largest gap, and N9B made it
larger by removing the cheaper explanation. Build it; do not diagnose it again.
Large daily cross-section, not six hand-picked episodes. PIT-only matching on
sector, size, momentum, realised vol, drawdown, liquidity, valuation where
available, revision state, regime — matched closely in calendar time so both
lived in the same macro world. Blind identity where feasible. Every LLM
explanation compiles to a structured measurable candidate or is rejected as a
story. Deduplicate into **mechanism families** so 10,000 threshold variants are
not 10,000 ideas. Train → foreign security → temporal holdout; the generating
episode never certifies. Primary metric: **distinct serious mechanism families
per dollar**, then transfer rate, then coverage.

**P4 — the slice register.** Verified absent: `slice_register`/`spent slice`
appear nowhere in the codebase except the order-4 document. Six securities were
declared, consumed by N9, then consumed again by N9B — the second use is not an
independent confirmation, and it survived only because someone remembered.
Record securities, period, consuming trial, use count. **Consuming a spent slice
is a refusal, not a warning — the exit code is the guard.** Declare the next
untouched slice *before* the next confirmation.

**P5 — G3 wiring (§5).** Small, mechanical, and it stops the objective silently
reverting under every downstream result.

**P6 — `EXPECTATION_LAYER_V1` (G4).** Not one number — an **Expectation
Vector** per event: event ts, first-public ts, source country/language, affected
entities, event type, numeric consensus, revision state, options-implied move,
pre-event abnormal return, IV/skew state, historical base rate, LLM semantic
expected state, actual content, semantic surprise, numeric surprise,
already-priced estimate, evidence timestamps. **The LLM estimating fundamental
significance is blinded to post-event price movement** — the impact estimate
must never learn from the reaction it is later compared against. Build on data
already held (IBES `revision_panel.parquet`, `sue_events.parquet`, the
OptionMetrics surface); do not wait for every event family.

**P7 — `WORLD_MODEL_V0`: code and a first training run, not a design document.**
The principal overrides the builder's deferral here and I agree: G3 mostly
exists and G4 can be built alongside. Self-supervised temporal encoder over the
numeric state already available; graph/event inputs only where PIT-safe. Heads:
tail probability, future max drawdown, co-movement change, state transition,
magnitude, uncertainty — **realised vol as an auxiliary target only, and beating
rv20 is explicitly not the mission.** Every head carries its own cheap baseline
ladder. The NN earns credit only for incremental out-of-sample information
beyond that baseline. Latent clusters are not investment signals yet.

**Then, in order and not before:** known-answer worlds (NULL, CONDITIONAL,
EXPOSURE, SELECTION, GRAPH, EXPECTATION — measuring false discoveries **and**
false kills; G1 flips only on this) → `LATENT-DISCOVERY_V0` → `OPPORTUNITY-GAP_V1`
(Aegis fundamental-impact distribution vs market-implied impact, both
directions, propagated through MARKET-GRAPH-1 against sector /
historical-correlation / known supplier-customer graph controls — the question
is *incremental* information over those baselines) → `SHADOW_BOOK` (decision ts,
information cutoff, mechanism version, expected return distribution, proposed
exposure, objective/personality, alternatives, confidence, rationale, outcome;
**never retroactively alter a historical book — version it**).

**Continuing:** COPY-LAB accumulates filings (N1 did not kill it; time-depth is
the bottleneck and it improves every day). Decompose actor skill into selection,
entry timing, exit timing, sizing, sector specialisation, drawdown behaviour,
post-disclosure copyability. **Never rank an insider on raw returns.**

**Stop spending research cycles on** the ledger/FRED/mount work. Both halves of
§56 have been observed in production. It is closed unless it breaks again.

---

## 7. Tests — amended

**N18 — make the sizing slogan falsifiable.** Stands as written in order 4, with
one addition: run it under the **declared objective**, not total return (§1.2).
`constant_half` *is* `buy_hold` at matched vol, exactly — so NIGHT-13's result
was about the risk level, not the policy, and *"sizing not timing"* has never
been tested as a claim about **state-dependent** sizing. A null collapses the
four-way convergence into "target constant volatility": a real product, not a
discovery, and the programme should say so plainly rather than keep citing four
findings that reduce to one.

**N19 — one untested information class, on a fresh slice.** Stands. N9B ruled
out vocabulary width *within price/vol only*. Event, revision, fundamental and
text are untouched. Choose by sample (R13); `revision_panel.parquet` and
`sue_events.parquet` are already on disk. Declare
`event_frequency_per_year` and `declared_effect_size` first and let
`lint_prereg` refuse it if the sample cannot resolve the claim.

**N20 — new. Measure `μ_rest | fire`.** Folded into P1, but it is a separate
registrable claim with its own prediction (1.516% / 2.542%) and it should be
recorded as one so the direct test can be graded against it rather than
rationalised after.

---

## 8. Report format — lead with results, not plumbing

1. First actual NN run and its baseline comparison
2. Winner / matched-loser episodes constructed
3. Genuinely distinct mechanism families generated
4. Direct held-out **economic** result for N9 / N9B, and `μ_rest | fire`
5. Expectation-layer status
6. Opportunity Gap status if reachable
7. Shadow books opened
8. Forward-resolution status
9. Dollars spent
10. Defects found
11. Exact SHAs
12. **§14 — the seven claims most likely to be wrong.** Keep it. It caught the
    thing this order is built on.

**Zero investment candidates is acceptable. Zero serious attempts at generating
them is not.**

---

## 9. Standing

A null owes both numbers: `mde_mean` (could we have seen it) and
`can_rule_out_at_least` (have we excluded what mattered). Only `REFUTED_IN_SCOPE`
and `STRUCTURALLY_CLOSED` close anything, **and `REFUTED_IN_SCOPE` closes only
the scope it names — including the action, the objective, and the conditioning
it was computed under.** A check that did not run is not a check that passed. A
refusal is a finding. The exit code is the guard. `verify_before_push` stays a
pre-push step.

**New, from this reconciliation:** *when two reviewers agree on a conclusion and
give different reasons, check the reasons — the conclusion can be right for a
reason that is arithmetically false, and the next prereg will be written from
the reason, not from the conclusion.*

### What I did not verify

CI green and prod-on-`2ba9fb3` are taken from the builder's report, not
re-observed. The OptionMetrics snapshot **frequency** is inferred from row
counts, not from reading a parquet schema. `μ_rest | fire` has not been
computed — the 1.516% / 2.542% thresholds are predictions derived from the
ledger's `μ_tail`, not measurements.

— brain, 2026-08-16
