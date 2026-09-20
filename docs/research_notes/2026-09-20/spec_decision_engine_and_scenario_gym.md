# Spec: the decision engine's ROI rule, and the scenario gym for "gut feeling"

Murat's brief (2026-09-20, verbatim in the assigning message): fix the decision
engine so it never makes a *bad* decision but also doesn't force one when it
isn't sure; among decisions it *is* confident about, take the highest-ROI one;
test the "gut feeling" piece against good/bad fictionalised scenarios built
from our own data, the way Fin-Force does, and feed that into the engine —
never as an override.

Licence: research/spec only. Any implementation is `PRODUCT_EXPERIMENT`
(CLAUDE.md three licences) — a frozen contract before the first decision, no
significance gate to *build* it, but never relaxed: no lookahead, no leakage,
costs always charged, version frozen once a candidate paper-trades.

## A. DIAGNOSIS — why the engine currently makes no ROI-ranked decision

The engine does not, today, refuse "when it isn't sure." It refuses (or sizes
generically) at several *earlier* gates, and even the survivors are never
ranked by return. Two separate facts, both load-bearing:

**1. A hard eligibility gate turns most candidates into `REFUSED`.**
`investment_committee.compose_book` (`backend/services/investment_committee.py:319-330`)
admits a name into `eligible` only if:

```python
if (getattr(r, "recommendation", "") in config.IC_TILT_VERDICT_SCALE
        and getattr(r, "evidence_grade", "NO_EVIDENCE") != "NO_EVIDENCE"
        and getattr(r, "ranking_score", 0.0) > 0):
```

i.e. verdict BUY/WATCH, licensed evidence, positive rank score — then caps
each survivor's weight (`IC_TOTAL_TILT_BUDGET`, capacity, one-share-minimum,
`compose_book:343-357`). When nothing survives, line 372-376 writes the
catch-all: `"no candidate clears the tilt gate (BUY/WATCH verdict + licensed
evidence + tradeable at this capital) — the book is 100% benchmark core"`.
`decision_contract._refusal_sentence` (`decision_contract.py:627-649`) walks
the *same* checks in the *same* order to name the first gate that stopped a
name, and the REFUSED row is built at `decision_contract.py:606-620`.

**2. Even a name that clears the gate is never ranked by ROI — because no ROI
field exists.** Every row `decision_contract.py` writes carries, unconditionally:

```python
"expected_payoff": NOT_CALIBRATED,          # decision_contract.py:568
"expected_payoff_basis": ("the committee reports an ORDERING and refuses to
    print a per-name return it cannot defend; the licensed pickers are
    SUPPORTED, not VALIDATED"),              # :569-572
"estimated_probability": None,               # :573
"estimated_probability_reason": ("no agency Option covers this name, and the
    committee publishes no calibrated P(win) for a tilt"),   # :574-576
```

Sizing (`investment_committee._tilt_size`, `investment_committee.py:288-292`)
is `cap × IC_TILT_VERDICT_SCALE[verdict] × IC_TILT_CONFIDENCE_SCALE[confidence]`
(`config.py:1709,1722-1724`: cap 3%, BUY=1.0/WATCH=0.5, confidence steps
0/⅓/⅔/1). This is a **verdict-and-confidence heuristic**, not a return- or
downside-scaled rule — a WATCH at HIGH confidence and a BUY at MEDIUM
confidence both size to 2%, regardless of which one a rational Kelly rule
would prefer. **"Highest ROI among admissible" cannot be implemented today
because the two fields it needs — a calibrated expected return and a downside
— are named absences by design, not missing data.** The fix is not "loosen a
gate"; it is to add the two fields (§B) and replace the fixed heuristic with
a rule that reads them.

## B. THE DECISION RULE

> Among candidates that clear the hard gates (PIT discipline, cost model
> named, liquidity/capacity, worst-case computable), rank by
> `expected_return_net / downside` at the declared horizon; take the top K;
> size each by fractional Kelly, capped by the profile.

### Required candidate fields, and where each one is or is not today

| field | meaning | source today | gap |
|---|---|---|---|
| `expected_return` | net, point estimate, at `horizon` | **does not exist.** `expected_payoff` is a fixed string (`decision_contract.py:568`) | new: a calibrated map from (verdict, evidence_grade, signal) → return, OR the agency `Option`'s own forward path once one exists |
| `downside` | a drawdown/loss magnitude at the same horizon, not just "worst case at 100% notional" | partial: `worst_case_no_stop` (`decision_contract.py:291-319`) gives the whole-notional loss, not a *distributional* downside | new: a per-name vol- or drawdown-based downside (`cand.get("vol_annual")`, already read at `investment_committee.py:88-90`, is the nearest existing input) |
| `confidence` | calibrated P(the return sign/direction is right) | `rec.confidence` is a 4-level LABEL (`NONE/LOW/MEDIUM/HIGH` — count of licensed signals, `investment_committee.py:95-98`), not a probability | `estimated_probability` is explicitly `None` today (`decision_contract.py:573-576`) — this is exactly the field §C's gym is meant to calibrate a contribution to |
| `horizon` | months/days the estimate is stated over | exists: `config.IC_WEALTH_HORIZON_MONTHS` (24), reused per-row (`decision_contract.py:566-567`) | none |
| `evidence` | why, in the gate's own words | exists: `reason_for_rank`, `_risk_factors` (`investment_committee.py:86-103`) | none |
| `falsifier` | what would make this wrong | exists: `kill_condition` / `_kill_condition` (`investment_committee.py:60-83`), with an expiry derived at `decision_contract.falsifier_expiry` (`:468-503`) | none |
| `source` | which engine/signal produced it | exists: `signal` (leader `signal_id`) and `source: "investment_committee"` / `"agency"` (`decision_contract.py:558-565,673`) | none |

### The rule, precisely (for `investment_committee.compose_book` / a new `rank_by_roi` step called from `decision_contract._ic_rows`)

1. **Hard gates first, unchanged.** PIT (funnel snapshot already time-stamped),
   cost model named or refused (`cost_model_row`, `decision_contract.py:249-283`
   — already enforces "never a silent zero"), liquidity/capacity
   (`CF.capacity_for`, already called at `investment_committee.py:343-345`),
   worst case computable (`worst_case_no_stop`). A candidate that fails any of
   these is `REFUSED`, exactly as today — this is the "don't force a bad
   decision" half of the brief and needs no change.
2. **Score = `expected_return / downside`** (a Sharpe-shaped ratio, not a
   raw return, so a high-return/high-vol name does not automatically beat a
   modest-return/low-vol one — this is "sure enough" made operational: a
   candidate with `expected_return` unset or `confidence` below a floor (say
   `estimated_probability is None` or `< 0.55`) does not get a score at all
   and stays `WATCH`/`REFUSED`, never gets force-ranked on a guess).
3. **Take the top K** (`config.IC_MAX_TILT_NAMES`, already 10) by that score,
   best first — replacing today's `eligible.sort(key=lambda r: (r.rank,
   -r.ranking_score))` (`investment_committee.py:329`), which sorts by the
   *ordering* rank, not by ROI.
4. **Size by fractional Kelly, capped by the profile.** `size_ce_kelly` already
   exists (`arena/policies.py`, cited in the roadmap dossier §5 table: "runs
   in 1 of 10 books") — reuse it rather than inventing a second Kelly
   implementation. Cap by `IC_SINGLE_NAME_TILT_CAP` (3%) and
   `IC_TOTAL_TILT_BUDGET` (10%) exactly as today (`compose_book:362-370`); the
   four personalities (preservation/balanced/aggressive/extreme growth,
   `OPTIMUS_OBJECTIVE.md` §0) become Kelly-fraction multipliers, not separate
   ranking rules.
5. **Named absence beats a fabricated number.** Any candidate for which
   `expected_return` or `downside` cannot be computed keeps
   `NOT_CALIBRATED`/`None` and is **not** ranked by ROI — it stays at today's
   verdict/confidence sizing (or REFUSED) until the field exists for it. This
   is the whole answer to "it can't be sure so it doesn't make one": the rule
   is a strict partial function, and the domain it is undefined on is
   printed, never guessed.

Estimated: a new `roi_rank.py` (~130 lines: score, top-K, Kelly-cap call) plus
a ~30-line change to `compose_book`'s eligible/tilt-size block to call it when
both new fields exist, falling back to today's heuristic otherwise — ≤200 lines.

## C. THE SCENARIO GYM — the "gut feeling" test

**Reuse, don't re-invent.** This repo already has: (a) the exact anonymisation
+ shuffled-control + paired-gap-with-NW-t machinery
(`scripts/night_x_anonymisation_gap.py`, `x_lane_data.stratified_cells`,
`mask_company`), (b) a frozen scenario-set contract with a Brier grader and a
base-rate control (`backend/services/scenario_forecasts.py` — X3), (c) a
Murphy-decomposition calibration module (`backend/services/calibration.py`),
and (d) the P1-P6 receipt block (`backend/services/protocol_p16.block`). The
gym is new *wiring* over these, not a new statistical engine.

**Read the caution first.** `scripts/night_x_anonymisation_gap.py`'s own
9-19 run (`backend/data/optimus/night_factory_2026-09-19/X_anon_gap_run01.json`)
found **both arms lose money net of costs on PANEL-B**: raw digest→direction
**-18.89%/yr net**, masked **-16.87%/yr net** (gap -2.02pp, t -0.54, adopted
MASKED by default), and the 2026-09-20 review says plainly: *"Stop spending
GPU on digest reads at 7B... X_anon_gap says both arms lose 17-19%/yr net."*
The scenario gym must **not** be a third arm of that same failed mechanism
(news digest → next-month direction, traded as a book). It differs in three
load-bearing ways: it grades a **committed decision object** (direction, size,
confidence, falsifier) rather than only a direction label; it explicitly
tests **movement under counterfactual perturbation** (the good/bad twins),
which R2/X_anon_gap never asked; and its adoption rule (below) forbids it ever
becoming a trading arm on its own — it can only ever enter as one *field* with
a *measured reliability weight* in §B's rule.

### Setup

- **Model:** `llama-server` on `127.0.0.1:8080`, Qwen2.5-7B-Instruct-Q4_K_M
  (the sha256-pinned build TRIAL-R2 already froze). DeepSeek optional, gated
  behind `--max-usd`, off by default (CLAUDE.md: the local-only policy is
  current default per the 09-20 review's "Needs Murat" item 3).
- **Time box:** one 90-minute run (`gpu_guard` idle precondition, same
  pattern as `night_l4_qwen3_measure.py`), writing `PENDING_MODEL` and a
  frozen cell list if the reader is not answering — never starting the server
  itself.
- **N historical decision points:** drawn from the E1 text-return panel
  (`backend/data/optimus/text_return_panel/news_returns_2025_26.parquet`,
  339,657 cells, 3,031 symbols, 2025-01-02..2026-09-08, `E1_receipt.json`)
  joined to L2 typed events (`typed_events/MANIFEST.json`: 36,463 typed rows,
  `vocabulary_hash` pinned) where both exist for a `(symbol, month)` cell, the
  same join `x_lane_data.widened_cells_and_docs` already performs. Use E1's
  `x_oo` (SPY-excess, open-to-open) as the realised 20-trading-day-ish return;
  it is already PIT (E1's anchor rule: first open strictly after publication,
  `E1_receipt.json` funnel).
- **Anonymisation, verbatim from `night_x_anonymisation_gap`:** the same
  `mask_company`-over-`tokenise` masking (ticker + distinctive issuer-name
  tokens → `[co]`), the same `x_lane_data.stratified_cells(seed=...)` draw
  stratified by month block, the same content-hash freeze
  (`x_lane_data.cells_fingerprint`) written before any model call, so the
  frozen list survives a `PENDING_MODEL` day exactly as X_anon_gap's does.
  Dates are shifted by a fixed per-cell offset (seeded), numbers (returns,
  volumes, prices) are kept verbatim — this is new relative to
  `night_x_anonymisation_gap`, which masks entity only.

### The two counterfactual twins (Fin-Force style)

For each real, anonymised scenario, generate **exactly one** good-twin and
**exactly one** bad-twin by template-appending one sentence to the digest —
never regenerating the whole digest, so the base setup is held byte-identical
across the pair and only the appended development varies:

- good-twin: `"{development}"` drawn from a small frozen library of
  favourable developments keyed by the cell's dominant typed event
  (`event_vocabulary` id — e.g. an `earnings_beat` cell's good twin appends an
  analyst upgrade; a `regulatory_action` cell's good twin appends a
  settlement).
- bad-twin: the paired adverse development from the same library (a downgrade,
  an escalation).

  **Naming collision:** `agency.py:1065` already uses "twins" for portfolio
  control books (`random_genome_null`, `beta_matched_index_sleeve`,
  `overnight_only`) — a different object. Name these `good_twin`/`bad_twin`
  in code, never bare `twins`.

### The ask, and the schema

One call per (real, good-twin, bad-twin) — three calls per decision point —
each returns a **committed decision**, schema-validated the way
`scenario_forecasts.validate_scenario_set` validates X3's schema:

```json
{"direction": "BUY|SHORT|HOLD|CASH",
 "size_pct": 0.0,            // 0-10
 "expected_return_20d": 0.0, // signed float
 "confidence": 0.0,          // 0-1
 "falsifier": "string"}
```

Refusals are named, not silently dropped, using the SAME closed
`REFUSAL_CLASSES`/`TERMINAL_STATES` `decision_contract.py` already re-derives
(`decision_contract.py:132-156`) plus `UNCLASSIFIED` for a reply that fails
schema — reuse `decision_contract.classify_refusal`, do not write a third
taxonomy.

### Grading

- **Real scenario vs realised `x_oo`:** sign accuracy; Brier on
  `P(direction correct)` derived from `confidence` (via
  `calibration.brier_decomposition`, which already refuses a decomposition
  below `MIN_N_FOR_DECOMPOSITION=45` and needs `MIN_PER_BIN=15` — see power
  note below); calibration by confidence decile (the same function, `by`
  grouping on confidence bucket); net long-short at 25 bps/side, the same
  `COST_BPS_PER_SIDE` R2 uses, computed the same paired/NW-lag-2 way
  `night_x_anonymisation_gap.paired_gap` already computes a gap; **and a
  shuffled control** (`base_rate_control`-style: same cells, a digest from a
  different month, `x_lane_data` rng) — never compared against zero.
- **Twins:** graded on **movement**, not on being right. For each real/twin
  pair: `Δsize = size_pct(twin) - size_pct(real)`,
  `Δconfidence = confidence(twin) - confidence(real)`,
  `Δexpected_return = expected_return_20d(twin) - expected_return_20d(real)`.
  Pass condition: good-twin moves `Δ ≥ 0` (more bullish or unchanged-and-
  flagged) and bad-twin moves `Δ ≤ 0`, on a majority of the three deltas, with
  the **sign flip rate** reported the same way P3 (direction-flip,
  `protocol_p16.py:15`) already asks for in the P1-P6 block. "A gut that
  doesn't move on the bad twin is not a gut" (brief, verbatim) — a model whose
  good/bad deltas are statistically indistinguishable from the shuffled
  control's own delta on a random unrelated appended sentence has FAILED the
  gym regardless of its real-scenario Brier.

### Receipt JSON schema (one file per run, `night_factory_<date>/scenario_gym_run<NN>.json`)

```json
{
 "job": "scenario_gym", "lane": "GUT",
 "PREREGISTRATION": "...",
 "cells_frozen": {"cells_sha256": "...", "n": 300, "seed": 20260920,
                   "stratified_by": "month block"},
 "counterfactual_library_hash": "...",
 "decisions": [{"cell": ["AAPL","2025-06"], "arm": "real|good_twin|bad_twin",
                "decision": {"direction": "...", "size_pct": 0.0,
                             "expected_return_20d": 0.0, "confidence": 0.0,
                             "falsifier": "..."},
                "refusal_class": null, "terminal_state": null}],
 "grading": {"sign_accuracy": 0.0, "brier": {}, "calibration_by_decile": {},
             "net_long_short_25bps": {}, "vs_shuffled_control": {},
             "twin_movement": {"good_twin_pass_rate": 0.0,
                                "bad_twin_pass_rate": 0.0,
                                "vs_control_movement": 0.0}},
 "P1_P6": {"P1": "...", "P2": "...", "P3": "twin sign-flip rate",
           "P4": "ECE/Brier/Murphy split", "P5": "25bps realised",
           "P6": "one model, one prompt — disaggregation trivial"},
 "adoption": {"reliability_weight": 0.0, "entered_as": "candidate field only",
              "never": "veto or override"}
}
```

### N, power, and the MDE

The panel's cross-sectional monthly return sd is **17.39%** (TRIAL-R2 §4,
already measured on this exact panel). Treating each decision point as
roughly independent for a one-sample mean-difference MDE (80% power, α=0.05,
two-sided: `MDE ≈ 2.8·σ/√N`):

| N | MDE on mean 20d return | sign-accuracy MDE (`1.4/√N` off a 50% base rate) |
|---|---|---|
| 300 | **±2.81 pp** | **±8.1 pp** |
| 1,000 | **±1.54 pp** | **±4.4 pp** |

**This overstates what either N actually resolves.** Canon §58 (`n_effective
counts DATE BLOCKS`, MEMORY canon) applies here exactly as it applied to
TRIAL-R2: 300 or 1,000 decisions drawn from ~19 available month blocks
collapse to an effective n near 19-60, not 300-1,000, for anything that
shares a month's market move. The **primary** grading number must therefore
be the block-paired NW-lag-2 gap (as R2/X_anon_gap already compute), with the
per-decision sign/Brier/calibration numbers reported as **secondary**,
exactly the split TRIAL-R2's §3 already enforces ("Everything else is
reported, never deciding"). N=1,000 is worth the extra 700 calls only for the
calibration-decile read (`calibration.py` needs `MIN_N_FOR_DECOMPOSITION=45`
resolved per group and `MIN_PER_BIN=15` — a clean 10-decile Murphy
decomposition wants ≥600-1,000, not 300) — not for the block-level ROI gap,
which N=300's 19 blocks already saturate.

### Adoption rule (binding, per the brief's "never a veto or an override")

1. The gym's output enters `decision_contract` **only** as one additional
   candidate field, `gut_signal: {direction, confidence, reliability_weight}`,
   where `reliability_weight` is the gym's OWN measured calibration
   (`calibration.brier_decomposition`'s `resolution` term, or 0 if
   insufficient N) — never a fixed constant chosen by hand.
2. It may contribute to §B's `expected_return` / `confidence` only as one
   weighted input among the licensed signals already scored by
   `recommendation.score_candidates` — added to `signal_contributions`
   exactly the way an existing picker is, not summed on top after the fact.
3. It can **never** flip a `REFUSED` to `BUY`, **never** override a hard gate,
   and **never** act alone: a candidate with a gut signal and zero licensed
   evidence stays `NO_EVIDENCE`/`REFUSED` (§A's evidence-grade gate is
   unchanged).
4. `reliability_weight` starts at (near) 0 and is re-measured on a rolling
   window (`calibration.py`'s `ROLLING_N=200`/`ROLLING_DAYS=90`, already
   built) — the gym must accrue its own forward record before its weight can
   rise above what N=300's MDE can actually distinguish from noise.

**References.** Fin-Force (EMNLP 2025 Findings, `github.com/keanepotato/
fin_force`) — counterfactual twin scenario generation graded on directional
movement under perturbation, the method §C's good/bad twins apply to this
repo's own anonymisation pipeline. Calibration: Murphy (1973), *"A New Vector
Partition of the Probability Score"* — the Reliability/Resolution/Uncertainty
split `calibration.py:1-38` already implements.

## D. EVENT UPDATE — revising a decision on new typed events

**Minimal ledger addition, not a new file.** `decision_ledger.py`'s state
machine is rank-ordered, not chain-strict (`decision_ledger.py:40-47,82-91`):
`DECIDED(0) → DELIVERED(1) → SEEN_BY_EXECUTOR(2) → {REFUSED,
ORDER_SUBMITTED}(3, siblings) → FILLED(4) → SCORED(5)`, enforced by
`record()`'s monotone-rank check (`decision_ledger.py:206-214`) and its
sibling-exclusivity check (`:201-205`).

Add **one new state, `REVISED`, at rank 3.5** (between `SEEN_BY_EXECUTOR` and
`FILLED`/`SCORED`), and **one new row shape**: a revision is a **new**
decision-contract row with its own `decision_id` (via
`decision_contract.decision_id`, unchanged) carrying a `parent_decision_id`
field pointing at the row it supersedes — never an in-place mutation of the
original row, because the original must stay gradeable exactly as it was
decided (`write_contracts`'s atomic-write discipline, `decision_contract.py:
886-897`, already protects against a half-written file; a mutated row would
be a *silently* rewritten one, the worse failure). `decision_ledger.record`
writes `REVISED` on the **parent's** `decision_id` (linking forward) the same
call that writes `DECIDED` on the child's.

**When an event class flips a decision — the rule, never a free-text
override:** a typed event arriving after `DECIDED` (from L2's per-`(scope,
date)` typed rows, `scenario_forecasts.realised_from_typed_rows`) is
translated into an update to exactly the candidate fields §B's rule reads —
`expected_return`, `downside`, `confidence`, `evidence` — through the SAME
signal-scoring path (`recommendation.score_candidates`) a fresh candidate goes
through, then §B's rank-by-ROI rule is **re-run in full** over the affected
capital level. If the re-run's top-K changes the row's direction or drops it
below the cut, a new row is written with `parent_decision_id` set and state
`REVISED` recorded on the parent. **No LLM output writes a revision directly**
— the typed event is a *candidate-field input*, identical in kind to a price
update, and the ranking rule is the only thing that can move `direction`.
This is the same firewall `belief_state.py`'s module docstring already states
for `PredictionRecord` ("the LLM proposes and forecasts; the engine computes
and allocates," `belief_state.py:42-46`) applied to the ledger.

## E. Risks and what would make this a waste

- §B's `expected_return`/`downside`, if filled by a hand-tuned mapping rather
  than something itself calibrated, just relabels today's heuristic as "ROI" —
  it must be graded against `decision_ledger`'s `SCORED` rows before it is
  trusted.
- The gym repeating R2/X_anon_gap's shape (news→direction, book return)
  without twin-movement grading is a third arm of an already 0-for-2
  mechanism; §C's never-standalone rule must be a code-enforced weight cap,
  not an intention.
- N=300 at 19 month blocks resolves a block-level MDE most readers will skip
  past for the more precise-looking per-decision number underneath it; the
  receipt prints both, but quoting only the per-decision one is the exact
  "check the tail before the mean" failure MEMORY already logs.
- `reliability_weight` computed once and never re-measured is a thumb on the
  scale wearing a calibration label; it must ride `calibration.py`'s rolling
  window, not a ship-time constant.
- A good/bad twin library built from the model's own priors, rather than
  E1's measured `(event_type, era)` base rates (`scenario_forecasts.pricer`
  already refuses to fabricate a missing one, `scenario_forecasts.py:228-250`),
  tests whether the model agrees with itself, not whether it reads.
- A `REVISED` state with no `grade_forecasts` step (review_night item 5:
  17,614 records never graded) just adds to the same unscored backlog — the
  state machine is necessary, not sufficient, for "learn from events."
- Any of this run against DeepSeek without `--max-usd` violates the
  local-only default the 09-20 review states is current policy pending
  Murat's per-run lift.
