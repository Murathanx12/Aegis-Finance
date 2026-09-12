# Chunk 8 Spec: M2 Distillation, E5 Stopping Rules, §11 Cheap Joins

Source roadmap: `docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
§9 (M2), §3 (E5), §11 (joins), §12 chunk 8. Read-only spec — no repo files modified
by this task.

Repo files this spec builds on (read in full or in relevant part):
- `backend/services/belief_state.py` — `PredictionRecord` (schema_version field
  present; M1's 19-field extension is listed in roadmap §9 table, not yet all present
  on the dataclass as read 2026-09-12 — chunk 8 assumes M1 has landed by chunk 5 gate).
  `make_prediction(...)` factory at line ~387, `calibration()` at line 928.
- `backend/services/calibration.py` — Murphy decomposition (`brier_decomposition`),
  `MIN_PER_BIN=15`, `MIN_N_FOR_DECOMPOSITION=45`, `base_rate_row()` (PIT base rate),
  `persistence()` (Tetlock quarter-pair correlation), `report(rows, by=...)`.
- `backend/services/ledger_retrieval.py` — M3's hindsight-safe predicate:
  `resolution_date < t AND resolved_at is not None AND resolved_at <= t AND outcome
  is not None`. `visible_at(record, t)`, `rules_visible_at(t, ledger=None, path=None,
  scope=None)`, `retrieval_report(...)`. `LEARNED_RULES` constant already points at
  `backend/data/optimus/brain/learned_rules.jsonl` (read-only from this module; M2
  is the writer).
- `learner/evidence_memory.py` — monthly-rotated JSONL (`evidence_memory_<YYYY-MM>.jsonl`,
  filed by the ROW'S OWN `utc` stamp, never file mtime), append-only, `supersede()`
  for retraction, `observe(family_id, cell, ...)` row shape, `live_rows()` as the
  ONE place supersessions apply, `to_registry()` export bridge.
- `scripts/night_checkpoint.py` — `Checkpoint` (per-run crash state, config-drift
  refusal) and `SearchState` (`bank_seeds_selected_on`, `elites`, `fresh_bank_seeds()`
  draws only from outside the seen-seed union, `update_elites()` keeps the
  more-banks-met genome not the higher-fitness one).
- `scripts/night_g3_evolve_v2.py` — `G3_evaluations.jsonl` row shape (see §2 below).
- `backend/strategy/multipletesting.py` — vendored (Vibe-Trading/HKUDS, MIT,
  UNEDITED body) `deflated_sharpe_ratio()`, `probability_of_backtest_overfitting()`
  (CSCV), `benjamini_hochberg()`. PBO already exists — E5 wires it to G3, does not
  build it.
- `docs/TRIALS/*.md` format (PREREG_* naming, hypothesis / primary metric / decision
  rule / frozen parameters / hard constraints) and `.claude/skills/pre-register-trial/SKILL.md`
  (`lint_prereg.py` corpse-check gate) — reused verbatim for the anomaly cadence.

Status: COMPLETE.

---

## 1. M2 DISTILLATION — `learner/rule_distillation.py` (new module)

### 1.0 Literature grounding (from `docs/research_notes/2026-09-11/research_learning_loop.md`)

- **ExpeL** (Zhao et al., AAAI 2024, arXiv:2308.10144) is the structural match:
  diffs SUCCESS vs FAILURE trajectory PAIRS to extract cross-task natural-language
  "insights". M2's "winner vs matched loser" is this pattern applied to graded
  ledger rows instead of agent trajectories.
- **FactorMiner** (Feb 2026, arXiv:2602.14670) stores BOTH "successful patterns"
  AND "failure constraints" — matches CLAUDE.md rule 4 ("study losers as hard as
  winners") and is why the distillation pipeline below never discards the losing
  half of a pair.
- **Reflexion** (Shinn et al., NeurIPS 2023, arXiv:2303.11366) supplies the
  small-buffer / no-vector-retrieval baseline; the "verbal feedback needs a
  verifiable success signal" caveat is exactly why a rule is scored on its OWN
  Brier rather than trusted on say-so.
- **Over-trust of retrieved experience**: Wang/Zhou "Agent Workflow Memory"
  (arXiv:2409.07429) and, load-bearing here, **arXiv:2505.16067** ("How Memory
  Management Impacts LLM Agents: An Empirical Study of Experience-Following
  Behavior", Xiong, Lin, Xie, He, Tang, Lakkaraju, Xiang; submitted 2025-05-21,
  revised 2025-10-10). Its finding: LLM agents show an "experience-following"
  property — high similarity between a task input and a retrieved memory record
  produces highly similar agent OUTPUT, regardless of whether the retrieved
  memory was correct — causing error propagation (a bad past experience
  compounds) and misaligned experience replay (a superficially similar memory
  applied to a materially different situation). M2's over-trust guard (§1.6)
  operationalises this: the model is never allowed to treat a retrieved rule's
  text as ground truth in proportion to how similar it looks; its influence is
  capped by a MEASURED skill number (Brier skill score vs base rate), not by
  the retriever's similarity score.
- No design in the surveyed literature scores a distilled verbal rule with a
  proper scoring rule (Brier) the way M2 requires — this is Aegis's own addition.
  Tetlock's Good Judgment Project (persistence r approx 0.65 year-to-year) is the
  justification that a calibration/resolution skill is a real, stable trait
  rather than noise, i.e. scoring a RULE this way is not a category error.

### 1.1 The pairing rule — three pair types, one interface

A "pair" is `(winner_row, loser_row, pair_kind, pairing_key)` drawn from the
ledger (`belief_state.read_predictions()`) and/or `evidence_memory.read_all()`.
All three kinds share one filter: both rows must be resolved
(`resolved_rows()` from `calibration.py`: `void_reason` empty, `outcome` not
None) and both formed from data available at distillation time (a construction
step, not a live forecast retrieval — M3's gate applies later, to the
RESULTING rule, per §1.5/§1.7).

| pair_kind | winner | loser | pairing_key | source |
|---|---|---|---|---|
| `book_vs_twin` | book row with `vs_control > 0` and outcome=1 (beat its twin) | same mechanism_id's row where `vs_control <= 0` | `(mechanism_id, control_construction)` | `belief_state` ledger, `control_twin_id` field |
| `era_split` | same `arm`/`family_id`, era A resolves in favor (`net_beats_market=True` or outcome=1) | same arm, era B resolves against | `(family_id or mechanism_id, arm)` | `evidence_memory` rows (has `eras`, `net_beats_market`) or ledger rows grouped by `era_tag` |
| `arm_vs_control` | a night job's arm clears its bar (`observe(..., verdict="NOVEL"/"SUPPORTED")`) | the same job's stated control (random-genome null RW1, shuffled digest, GBM, base-rate forecaster) on the same cell | `(job, run, cell)` | `evidence_memory` rows + `G3_evaluations.jsonl` |

Every (winner, loser) pair sharing a key where one side cleared its bar and the
other did not is eligible, capped at `MAX_PAIRS_PER_KEY = 12` (sample without
replacement, seeded, receipted as `pairs_sampled / pairs_possible` — a
mechanism_id with 40 favorable and 3 unfavorable resolutions is not 120
independent pairs). A pair where winner and loser are the SAME row (a
degenerate self-pair from a sloppy key) is dropped and counted in
`dropped_degenerate`.

### 1.2 The diff -> candidate-rule pipeline (local 7B, prompt contract)

One call per pair, never batched across pairs — batching lets the model average
across mechanisms and produce a rule that fits none of them.

Input to the model: both rows serialized through a fixed field allowlist
(never a raw dict dump — a stray `probability` or `outcome` field leaking into
the "applies_when" side would let the rule memorize the answer key):

```
ALLOWED_INPUT_FIELDS = (
    "mechanism_id", "ticker", "specialist", "observable", "horizon_days",
    "thesis", "counter_thesis", "next_observable", "arm", "cell",
    "era_tag", "control_construction", "job", "run", "variant",
    "made_at", "resolves_after",
)
```

The outcome side (whether it won or lost, its Brier, its vs_control) is
supplied SEPARATELY, labeled `WINNER_OUTCOME` / `LOSER_OUTCOME`, so the model
sees which one is which but the "applies_when" it writes cannot absorb
future-only fields. Enforced by a post-hoc check: any token from
`{outcome, resolved_at, brier, vs_benchmark, vs_control}` appearing inside the
returned `applies_when` clause voids the candidate (`REJECTED_LEAKED_OUTCOME_FIELD`,
counted in the receipt, never silently dropped).

Prompt contract, JSON schema validated before anything downstream touches it:

```json
{
  "type": "object",
  "required": ["rule_text", "applies_when", "predicts", "evidence_pairs", "confidence"],
  "properties": {
    "rule_text": {"type": "string", "maxLength": 400},
    "applies_when": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["field", "op", "value"],
        "properties": {
          "field": {"type": "string", "enum": ["mechanism_id", "ticker_sector",
                     "specialist", "observable", "horizon_days_bucket", "arm",
                     "era_tag", "control_construction", "regime_tag"]},
          "op": {"type": "string", "enum": ["eq", "in", "gte", "lte", "between"]},
          "value": {}
        }
      },
      "minItems": 1, "maxItems": 5
    },
    "predicts": {
      "type": "object",
      "required": ["observable", "direction"],
      "properties": {
        "observable": {"type": "string"},
        "direction": {"type": "string", "enum": ["higher", "lower", "unchanged_vs_control"]}
      }
    },
    "evidence_pairs": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
  }
}
```

`evidence_pairs` holds the `pairing_key` + row-id strings the rule was
distilled FROM — a receipt trail, not evidence the rule is right (a rule is
only as good as its OWN forward Brier, §1.3). A response failing schema
validation is retried once (temperature 0 -> 0.3) then discarded as
`SCHEMA_INVALID`, counted, never silently dropped.

`applies_when` is a typed condition list, not free text, so the retrieval-time
engine (§1.6) can evaluate it mechanically against a live ledger row without a
second LLM call — an LLM-evaluated "does this rule apply" check would
reintroduce the over-trust failure mode this module exists to avoid.

### 1.3 The rule's OWN Brier — a rule is a forecast about future forecasts

A distilled rule makes a directional claim (`predicts.observable`,
`predicts.direction`) conditioned on `applies_when`, scored exactly like
`PredictionRecord`:

1. At distillation time (end of month M) the rule is written `state=CANDIDATE`,
   `brier=null`, `n_fired=0`.
2. Every subsequent month, the retrieval engine scans the ledger for rows the
   rule WOULD have fired on (`applies_when` evaluates true against the row's
   fields, `made_at` in that month). For each firing, `p_rule = confidence`
   when the row's realized outcome matches `predicts.direction`, else
   `1 - confidence` — the rule is treated as a forecaster whose stated
   probability is `confidence` and whose claim is binary (direction matched or
   not).
3. `rule_brier(month) = brier_decomposition([p_rule]*n, [outcome]*n)`, reusing
   `backend/services/calibration.py` verbatim: `calibration.report()`'s
   `key_of()` gains one branch, `if by == "rule_id": return
   str(r.get("fired_rule_id") or "none")`.
4. Fewer than `MIN_N_FOR_DECOMPOSITION=45` firings: stays `CANDIDATE`, flat
   Brier only, no decomposition — the existing insufficient-n refusal, unchanged.
5. `GRADUATED` requires the rule's rolling Brier (last 90 days OR last 200
   firings, existing `ROLLING_N`/`ROLLING_DAYS` constants) to beat the base
   rate's Brier on the SAME fired rows (`beats_climatology`, already computed
   by `brier_decomposition`) for two consecutive non-overlapping evaluation
   windows — reusing evidence_memory's own "a single observation can neither
   promote nor kill" (`MIN_PASSES_TO_PROMOTE = 2`), applied to rule-months.
6. A rule that never fires ages out after `RULE_STALE_MONTHS = 6` -> `STALE`,
   never deleted (append-only; a STALE rule is a receipt that a condition
   stopped mattering).

### 1.4 The generalisation gate — held-out mechanism family

1. `evidence_pairs` are grouped by `mechanism_family` (the coarse family a
   `mechanism_id` belongs to — reuse whatever grouping `signal_registry.py`
   already uses; if none exists, the documented fallback is the first two
   underscore-delimited tokens of `mechanism_id`, e.g. `momentum_12_1` ->
   family `momentum`).
2. `n_families_in_evidence = len(set(families))`. Fewer than 2 ->
   `generalisation = UNTESTED` (not `NOT_GENERALISED` — it has not yet been
   given the chance).
3. Once the rule starts firing on LIVE ledger rows, each firing's
   `mechanism_family` is compared against the families it was distilled from.
   `held_out_hit_rate` = fraction of firings on a family NOT in the original
   evidence set. After `MIN_HELDOUT_FIRINGS = 15` such firings: Brier on the
   held-out subset beating climatology -> `GENERALISED`; otherwise ->
   `NOT_GENERALISED`. `NOT_GENERALISED` is a state, not a deletion — the rule
   keeps firing and keeps being scored in-family, and is surfaced in
   `LEARNED_<month>.md` exactly as prominently as `GENERALISED` (CLAUDE.md
   "study losers as hard as winners").
4. Before `MIN_HELDOUT_FIRINGS`: `generalisation = INSUFFICIENT_HELDOUT_N` —
   a gate that CAN go green, it just needs firings first, stated rather than
   defaulted either way.

### 1.5 The noise floor — shuffled-pair distillation

Run monthly, alongside the real distillation, over the SAME pool: pairs are
constructed with `pairing_key` permuted across rows (a winner from mechanism A
paired with a loser from unrelated mechanism B), seeded from the month
(`AEGIS_RULE_SHUFFLE_SEED`, reproducible, not hand-picked). The pipeline (§1.2)
runs identically on shuffled pairs, producing `shuffled_rules`; their aggregate
Brier across all firings, `noise_floor_brier`, is expected to equal climatology
within sampling noise. Every real rule's Brier is read against BOTH numbers —
climatology and `noise_floor_brier` — via a paired block-bootstrap CI overlap
(same machinery as `AMENDMENT_N20_NONINFERIORITY.md`). A rule statistically
indistinguishable from the noise floor is `NOT_BETTER_THAN_NOISE`, distinct
from `NOT_GENERALISED` (one says the rule doesn't transfer; the other says the
pipeline extracted nothing a random pairing wouldn't). `noise_floor_brier` is
printed in every month's `LEARNED_<month>.md` header.

### 1.6 The over-trust guard (arXiv:2505.16067)

A rule's weight in a live forecasting prompt is capped by its Brier skill score
vs the base rate, never by retrieval similarity or recency:

```
bss = 1 - rule_brier / climatology_brier
prompt_weight = max(0.0, min(bss, MAX_RULE_WEIGHT))     # MAX_RULE_WEIGHT = 0.6
```

`CANDIDATE` (insufficient n) -> `prompt_weight = 0`; may be SHOWN, labeled
unproven, never contributes to stated confidence. `NOT_BETTER_THAN_NOISE` is
never injected regardless of surface similarity to the current situation — the
direct fix for experience-following: similarity to a retrieved memory must
never substitute for that memory's measured correctness. The retrieval report
(extending `ledger_retrieval.retrieval_report`) adds a `prompt_weight` column
per surfaced rule.

### 1.7 Retrieval constraint (M3) applied to rules

`learned_rules.jsonl` rows echo `PredictionRecord` field names (`resolution_date`,
`resolved_at`, `outcome`) so `ledger_retrieval.visible_at()` works UNCHANGED
against a rule row. `resolution_date` = end of the evaluation window the rule
was last scored on; `resolved_at` = when that scoring ran; `outcome` stays
`null` (a rule has no single binary outcome — `state`/`brier` carry what
`outcome` would). Because `visible_at()`'s `outcome is None -> void` branch
would incorrectly gate out every rule, `rules_visible_at` gets ONE documented
exception: for rows where `schema_version` starts with `"learned-rule-"`,
`state in ("GENERALISED", "NOT_GENERALISED")` substitutes for
`outcome is not None`. Filed as `test_ledger_retrieval_admits_scored_rules`.

### 1.8 `LEARNED_<YYYY-MM>.md` format (Optimus-ingestible)

Written to `backend/data/optimus/brain/LEARNED_<YYYY-MM>.md`, one file per
month, sealed once the month closes (same rotation discipline as
`evidence_memory_<YYYY-MM>.jsonl` — filed by the month the DISTILLATION ran,
one month after the evidence it used). Plain markdown, no new Optimus parser
needed:

```
# LEARNED_2026-10.md -- distilled rules from October's graded ledger

Noise floor (shuffled-pair distillation, seed <seed>): Brier <x> (climatology <y>)
Pairs: <n_real> real, <n_shuffled> shuffled, <n_dropped_degenerate> dropped
Distillation model: <model_id>@<version>, prompt_hash <hash>

## GENERALISED (n=<k>)

### RULE-2026-10-0007
- Text: "<rule_text>"
- Applies when: mechanism_id in {...}, horizon_days_bucket=21d
- Predicts: insider_cluster_buy_intensity -> higher forward 21d excess
- Brier: 0.187 (n=61, climatology 0.231, noise floor 0.229) -- BEATS both
- Held-out families: 3/5 tested, held-out Brier 0.201 (beats climatology)
- Confidence cap (prompt_weight): 0.19
- Era: 2025-01..2026-09
- Evidence pairs: <pairing_key> x N (receipt: evidence_memory_2026-09.jsonl rows <ids>)
- Receipt: learned_rules.jsonl line <n>

## NOT_GENERALISED (n=<k>)
(same block shape -- kept, not deleted)

## NOT_BETTER_THAN_NOISE (n=<k>)
(same block shape)

## STALE (n=<k>)
(rule text + last-fired date + months since)
```

`learned_rules.jsonl` row:

```json
{"rule_id": "RULE-2026-10-0007", "created_utc": "...", "rule_text": "...",
 "applies_when": [], "predicts": {}, "confidence": 0.62,
 "state": "GENERALISED", "brier": 0.187, "n_fired": 61,
 "resolution_date": "2026-10-31", "resolved_at": "2026-11-03",
 "outcome": null, "generalisation": "GENERALISED",
 "held_out_hit_rate": 0.41, "prompt_weight": 0.19,
 "evidence_pairs": ["book_vs_twin::insider_cluster::ctrl_a::12"],
 "schema_version": "learned-rule-1.0.0"}
```

### 1.9 Known-answer tests (`learner/tests/test_rule_distillation.py`)

1. **Planted rule recovery**: 200 synthetic pairs where `mechanism_id=synth_A`
   AND `era_tag=bull` winners have p=0.8 toward the planted direction and
   everything else is coin-flip; the LLM call is stubbed to return the KNOWN
   planted JSON for the fast offline suite, plus a separate slow-marked test
   that runs the real 7B and checks the extracted condition matches within
   edit distance. Assert the surviving `applies_when` matches
   `{mechanism_id: synth_A, era_tag: bull}` and `bss > 0.3` on 100 held-out
   synthetic firings.
2. **Shuffled distillation ~= base rate**: shuffle the pairing key on the same
   200 pairs; assert `noise_floor_brier` falls inside the bootstrap CI of
   `climatology_brier` (indistinguishable, not "worse than").
3. **NOT_GENERALISED**: plant a rule real only within one synthetic mechanism
   family; confirm held-out firings from a different family show
   `resolution ~= 0` and the rule files `NOT_GENERALISED` after
   `MIN_HELDOUT_FIRINGS`.
4. **Leaked-outcome-field rejection**: a stubbed response whose `applies_when`
   contains `{"field": "outcome", ...}` is rejected
   (`REJECTED_LEAKED_OUTCOME_FIELD`), never reaching `learned_rules.jsonl`.
5. **M3 interop**: a `GENERALISED` rule with `resolved_at` in month M+1 is not
   visible to `rules_visible_at(t)` for any `t` inside month M
   (`visible_at` returns `(False, "graded_after_t")`, unchanged code path).

---

## 2. E5 STOPPING RULES — `scripts/night_stopping_rules.py` (new module)

### 2.0 What already exists vs what E5 wires

`backend/strategy/multipletesting.py` (vendored, UNEDITED body, Vibe-Trading/
HKUDS MIT) already ships `deflated_sharpe_ratio()`,
`probability_of_backtest_overfitting()` (CSCV/PBO), and `benjamini_hochberg()`.
**E5 is integration, not invention**: read `G3_evaluations.jsonl` and
`SearchState`, build the two required inputs (effective trial count, per-window
fitness matrix), call the existing functions, and write the `DEPRIORITIZED`
verdict plus a receipt. Nothing in `multipletesting.py` is modified (it is
vendored verbatim per its own header comment).

### 2.1 `G3_evaluations.jsonl` row schema (from `scripts/night_g3_evolve_v2.py`
lines ~492-497, ~546-552)

```json
{"key": "<genome sha1[:16]>", "lineage": "<founder genome key>",
 "parents": ["<key>", "..."], "bank_seed": 123456789, "gen": 42,
 "pass": "confirmation",            // present only on confirmation-pass rows
 "genome": {"w": ..., "k": ..., "weight": ..., "hold_mult": ..., "floor": ...},
 "full_dev_max_dd": -0.183,          // absent on confirmation-pass rows
 "result": {
   "verdict": "OK", "n_windows": 24, "fitness": 3.512,
   "win_rate_bm": 0.62, "median_beta": 0.94,
   "worst_window_max_dd": -0.21, "median_window_max_dd": -0.09,
   "cells": [{"window": "2005-03..2011-08", "length_m": 66, ...}, "..."]
 },
 "utc": "2026-09-12T03:14:07"}
```

`fitness` is the genome's median beta-matched EXCESS over the window bank's
random-genome null (RW1) — already net of the null, per the module's own
design note ("the score is an excess over a random-genome null on the SAME
windows"). `lineage` groups genomes by ancestry (crossover children share their
first parent's root). `bank_seed` identifies the window bank (drawn from
`SearchState.fresh_bank_seeds`, never reused across selection per the seed
guard already built in `night_checkpoint.py`).

### 2.2 Effective number of trials — ONC clustering, with a stated simpler proxy

**Citation**: Bailey & López de Prado, "The Deflated Sharpe Ratio: Correcting
for Selection Bias, Backtest Overfitting and Non-Normality" (2014, SSRN
2460551); the effective-trial-count refinement via Optimal Number of Clusters
(ONC) unsupervised clustering is from López de Prado & Lewis, "Detection of
False Investment Strategies Using Unsupervised Learning Methods" (2018/2019).
ONC clusters trials by the CORRELATION of their return series and counts
differentiated clusters as the effective trial count, rather than the raw
number of trials run — because two genomes sharing most of their trades (e.g.
siblings differing in one parameter) are not two independent draws against the
DSR null.

**Two proxies, both computed, one designated primary per lineage cohort:**

1. **`n_trials_raw`** — count of DISTINCT genome keys evaluated in the search
   (already tracked: `len(genomes)` in `night_g3_evolve_v2.py`). Always
   reported as the floor (DSR against `n_trials_raw` is the MOST conservative
   number since raw count only ever inflates `expected_maximum_sharpe`).
2. **`n_trials_effective` via ONC** — requires the per-genome return SERIES,
   not just the scalar fitness. G3 does not currently persist per-genome daily
   returns (only the scalar `fitness` and per-window `cells` summary) — this is
   a **gap E5 must close**: `WindowBank.evaluate()` (night_g3_evolve_v2.py
   ~line 269) needs to optionally return the per-window excess return VECTOR
   (one float per window in the bank, not just its median) for genomes that
   reach the confirmation pass or the final archive (NOT every genome in every
   generation — that would blow up the log; scoped to the archive's
   `banks_met >= min_banks` finalists, typically dozens, not tens of thousands).
   With that vector available per finalist, `probability_of_backtest_overfitting`'s
   input (a `performance` matrix, rows=windows, columns=genomes) already exists
   in the right shape, and ONC clustering (a `scipy.cluster.hierarchy` +
   correlation-distance recipe, ~40 lines, no new dependency — `scipy` is
   already a project dependency) reduces the columns to clusters before DSR's
   `n_trials` is set to `len(clusters)`.
3. **STATED SIMPLER PROXY (default until ONC ships)**: `n_trials_effective_proxy
   = n_lineages` — the number of distinct `lineage` roots in the evaluations
   log. This is already the unit the archive de-duplicates on (per the module's
   own comment: "a lineage root; the final table reports one row per lineage").
   It systematically OVER-counts effective trials relative to true ONC
   (siblings within a lineage can still be correlated with siblings of a
   DIFFERENT lineage via shared parentage two generations back, and a single
   large lineage with many members explores more of the space than the naive
   count implies is independent) — so it is conservative in the WRONG
   direction relative to raw genome count but the RIGHT direction relative to
   "count only 1" and is documented as a proxy, not a substitute, with the gap
   named. `n_trials_effective_proxy` is reported ALONGSIDE `n_trials_raw` in
   every receipt, never instead of it, mirroring the existing "rolling
   reported beside all-time, never instead of" discipline in `calibration.py`.

### 2.3 PBO (CSCV) over G3's per-window fitness matrix

Once finalists carry a per-window excess-return vector (§2.2.2), build
`performance` as a DataFrame: rows = the UNION of all window keys any finalist
was evaluated on (missing cells = NaN, since not every finalist met every
bank), columns = finalist genome keys (one column per LINEAGE representative,
per the existing "best measured, not best scoring" rule already in the module
— reuse `by_lineage` as computed at line ~593 unchanged). Call
`probability_of_backtest_overfitting(performance, n_splits=16)` UNCHANGED (its
`n_splits < 4` and `subset_size < 2` refusals already handle "not enough
windows" by raising `ValueError`, which the wrapper catches and reports as
`PBO_INSUFFICIENT_WINDOWS` rather than crashing the night job — the standing
"a gate that cannot go green is broken" rule: fewer than 32 window
observations across the finalist set is realistic early in a search, and PBO
must say CANNOT_DETERMINE rather than silently not run).

### 2.4 The DEPRIORITIZED rule

For each lineage `L` with `banks_met >= min_banks` (already the archive's own
admission bar):

```
dsr_result = deflated_sharpe_ratio(
    observed_sharpe   = per_window_sharpe(L.representative),
    n_trials          = n_trials_effective_proxy,   # or ONC count once available
    n_observations    = L.representative.n_windows_measured,
    trial_sharpe_std  = std(fitness across all lineage representatives this run),
    skew, kurtosis    = computed from L.representative's per-window excess vector,
    confidence        = 0.95,   # matches evidence_memory.DSR_BAR
)
pbo_result = probability_of_backtest_overfitting(performance_matrix)

if not dsr_result.survives:                      # dsr <= 0.95
    verdict = "DEPRIORITIZED"
    reason  = f"DSR {dsr_result.deflated_sharpe_ratio:.3f} <= 0.95 bar at " \
              f"n_trials={n_trials_effective_proxy} (raw {n_trials_raw})"
elif pbo_result.pbo > evidence_memory.PBO_BAR:    # > 0.5
    verdict = "DEPRIORITIZED"
    reason  = f"PBO {pbo_result.pbo:.3f} > {evidence_memory.PBO_BAR} bar"
else:
    verdict = "ACTIVE"
```

`DEPRIORITIZED`, never `deleted` or a bare `STOP` — per the roadmap's own
vocabulary (`FAILED_VARIANT -> DEPRIORITIZED -> RETIRED_FROM_CURRENT_SEARCH`,
CLAUDE.md "EXPLORE DIRTY, PROMOTE CLEAN"). A `DEPRIORITIZED` lineage:
- is EXCLUDED from `SearchState.update_elites()` (never carried forward as a
  parent into the next night) — a one-line filter added where
  `night_g3_evolve_v2.py` calls `state.update_elites(rows, keep=24)`, gated on
  a `deprioritized_lineages` set computed by this module and passed in;
- keeps its full evaluation history in `G3_evaluations.jsonl` (append-only,
  nothing deleted);
- is written to a new `G3_lineage_verdicts.jsonl` receipt (§2.6) so a later
  night, or a human, can see WHY without recomputing DSR/PBO from scratch;
- **may be re-tested** under the existing `RETIRED_FROM_CURRENT_SEARCH` ->
  `pre-register-trial`'s corpse-check + "resurrects: X, new instrument: Y"
  pattern if a future generation's window bank or genome-space change gives it
  a genuinely new instrument — never re-run with the identical bank/seed
  regime that produced the DEPRIORITIZED verdict, which would just reproduce
  the same overfitting the deflation caught.

### 2.5 The random-genome null on the same windows (RW1) as the control

RW1 already runs INSIDE `WindowBank.__init__` (night_g3_evolve_v2.py ~line
239: `nulls = [random_genome(rng) for _ in range(n_null)]`) and its median
becomes `null_bar` — every genome's `fitness` is ALREADY net of this null by
construction (§2.1). E5 does not re-run RW1; it consumes the fact that fitness
is already null-adjusted and adds ONE additional receipt field per finalist:
`null_refused_rate` = the fraction of windows in this finalist's bank where
`n_null_refused` was nonzero (i.e., the null itself sometimes fails the
drawdown gate — already tracked as `n_null_refused` in the main loop) — a
finalist whose null bar was computed from a THIN null population (few nulls
survived admissibility) has a noisier zero-point than the summary fitness
number alone would suggest, and DSR's `trial_sharpe_std` should be understood
in that light. This is reported, not gated on — a documented caveat rather
than a second refusal.

### 2.6 Receipt fields — `G3_lineage_verdicts.jsonl`

One row per lineage per night the stopping-rule pass runs (append-only, same
discipline as every other JSONL in this repo):

```json
{"utc": "...", "run": "<run_id>", "night_index": 12,
 "lineage": "<lineage root key>", "representative_key": "<genome key>",
 "banks_met": 5, "n_windows_measured": 118,
 "fitness_median": 3.51, "fitness_best_bank": 4.02,
 "n_trials_raw": 8421, "n_trials_effective_proxy": 251,
 "n_trials_effective_onc": null,           // null until ONC ships (§2.2.2)
 "trial_sharpe_std": 1.12, "observed_sharpe": 2.94,
 "dsr": 0.87, "dsr_bar": 0.95, "dsr_survives": false,
 "pbo": 0.41, "pbo_bar": 0.5, "pbo_status": "ok",  // or "insufficient_windows"
 "null_refused_rate": 0.08,
 "verdict": "DEPRIORITIZED",
 "reason": "DSR 0.870 <= 0.95 bar at n_trials=251 (raw 8421)",
 "receipt_evaluations_log": "state/night/G3_evaluations.jsonl",
 "receipt_search_state": "state/night/night_search_state.json"}
```

### 2.7 Known-answer tests (`scripts/tests/test_night_stopping_rules.py`)

1. **Planted noise lineage fails DSR**: synthesize a fitness distribution for
   200 "lineages" drawn i.i.d. from the SAME null (mean 0, realistic
   window-count variance matching G3's observed `n_windows` per finalist);
   the best of 200 draws is expected to clear a naive `t>0` bar but
   `deflated_sharpe_ratio` with `n_trials=200` must report `survives=False`
   for the maximum — this is exactly `multipletesting.py`'s own worked
   example, re-run through E5's wrapper to confirm the wiring (not the math)
   is correct.
2. **Planted real edge survives**: inject ONE lineage with a genuinely
   elevated mean excess (e.g. +2 SD above the null lineages' distribution,
   with return-series autocorrelation structure matching a real genome's) among
   the same 200 null lineages; assert `dsr_survives=True` for that lineage at
   the SAME `n_trials=200` that correctly failed every null lineage in test 1
   — proving the gate discriminates rather than just being strict.
3. **PBO on a known-overfit matrix**: construct a performance matrix from
   `multipletesting.py`'s own test fixtures (or an equivalent synthetic set)
   where the in-sample winner is known to rank randomly out-of-sample; assert
   `pbo > 0.5` and the DEPRIORITIZED path fires via the PBO branch even when
   DSR alone would have passed (proves the two gates are not redundant).
4. **`n_trials_effective_proxy` sanity**: a search with 500 genomes across 12
   lineages reports `n_trials_raw=500`, `n_trials_effective_proxy=12`; DSR
   computed under each differs in the expected direction (harder bar under the
   larger count).
5. **PBO_INSUFFICIENT_WINDOWS never crashes**: a lineage with only 6 measured
   windows (below CSCV's `n_splits=16` minimum-rows-per-subset requirement)
   produces `pbo_status="insufficient_windows"`, `verdict` decided on DSR
   alone, and the night job continues rather than raising.

---

## 3. THE THREE CHEAP JOINS (roadmap §11)

### 3a. Weekly published-anomaly cadence

Modeled directly on Fidetolabs Notes (`docs/research_notes/2026-09-11/
research_qanat.md`: "pick one published quant finance paper, test on real
market data from scratch, preregister the plan BEFORE loading data, publish
code+charts+results including negative findings"). Reuses `docs/TRIALS/`
format verbatim (`PREREG_<NAME>.md`, hypothesis / primary metric / decision
rule / frozen parameters / hard constraints, the `pre-register-trial` skill's
`lint_prereg.py` corpse-check gate BEFORE registration) — no new prereg format
invented.

**First eight anomalies to adjudicate, in cadence order** (one per week,
cheapest data requirement first so early weeks do not block on a data build):

| week | anomaly | primary citation | data need |
|---|---|---|---|
| 1 | Short-term reversal | Jegadeesh (1990), "Evidence of Predictable Behavior of Security Returns", JF | monthly returns only, already have |
| 2 | Earnings momentum (PEAD) | Ball & Brown (1968); Bernard & Thomas (1989/1990) | SUE from quarterly EPS, already ingested for insider/revisions work |
| 3 | 52-week high | George & Hwang (2004), "The 52-Week High and Momentum Investing", JF | 252-session rolling high, trivial from price panel |
| 4 | Gross profitability | Novy-Marx (2013), "The Other Side of Value: The Gross Profitability Premium", JFE | (revenue - COGS) / assets, fundamentals panel |
| 5 | Asset growth | Cooper, Gulen & Schill (2008), "Asset Growth and the Cross-Section of Stock Returns", JF | total assets YoY, fundamentals panel |
| 6 | Net stock issuance | Pontiff & Woodgate (2008), "Share Issuance and Cross-Sectional Returns", JF; Daniel & Titman (2006) | shares outstanding change, fundamentals panel |
| 7 | Accruals | Sloan (1996), "Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings?", Accounting Review | (net income - operating cash flow) / assets |
| 8 | Low volatility | Ang, Hodrick, Xing & Zhang (2006), "The Cross-Section of Volatility and Expected Returns", JF; Baker, Bradley & Wurgler (2011) | trailing realized vol, already computed for sizing |

Each week's prereg is `docs/TRIALS/PREREG_ANOMALY_<NAME>_1.md`, following the
existing template: hypothesis stated as the published direction (e.g. "low
gross-profitability minus high gross-profitability is negative, net of costs,
on our universe and era"); primary metric = net Sharpe vs the market OR
forward rank-IC (whichever the template standardizes on for a screen);
decision rule = DSR + PBO + 2-of-3 eras (reusing `evidence_memory.py`'s
existing bar, `DSR_BAR=0.95`, `PBO_BAR=0.5`); frozen parameters = the exact
published portfolio construction (quintile/decile sort, rebalance frequency)
taken from the cited paper rather than re-optimized; hard constraint =
**NEGATIVE RESULTS ARE PUBLISHED, not filed away** — a week where the
published anomaly does NOT replicate net of costs on this universe/era writes
to `NEGATIVE_RESULTS.md` (per canon) with the SAME prominence as a positive
week, matching Fidetolabs Notes' own framing and CLAUDE.md's "study losers as
hard as winners."

**Night job shape**: `scripts/anomaly_cadence_run.py --week <n> --anomaly
<name>`, one per week (cron or manual), which (1) checks `lint_prereg.py`
passes for that week's `PREREG_ANOMALY_*.md` before touching data (registered
BEFORE the first decision, per canon), (2) builds the factor from the frozen
construction, (3) runs it through the existing farm/registry pipeline
(`portfolio_farm` preset or equivalent), (4) writes an
`evidence_memory.observe(family_id=f"anomaly_{name}", ...)` row exactly like
every other night job's output — the anomaly cadence is NOT a separate
evidence store, it is eight more `family_id`s in the same append-only memory,
so M2's distillation pipeline (§1) can pair an anomaly week's winner-vs-loser
era split exactly like any other mechanism.

### 3b. Read-only MCP surface

Extends the Optimus MCP (per CLAUDE.md's four-repo table: "ingests both repos'
`docs/` + session memory") with a **structural** read-only gate modeled on
Qanat's `--read-only` mode (research note: "27 MCP tools: 20 read-only ... 7
write ... `--read-only` mode restricts agent to the 20 read tools"). Aegis's
version has **no write tool in this surface at all** — not a flag that can be
toggled, a server that was never given a write handler, extending the same
read-only posture the `optimus` MCP server's own instructions already state
for `aegis_verified_state`/`aegis_registry`/`brain_query`.

**Tool signatures:**

```python
def panel_query(
    fields: list[str],                 # e.g. ["ticker", "date", "mechanism_id", "fitness"]
    filters: dict[str, Any] | None = None,   # {"field": {"op": "eq"|"in"|"gte"|"lte", "value": ...}}
    limit: int = 500,                  # hard cap, no unbounded scan
    as_of: str | None = None,          # PIT cutoff -- rows after this excluded
) -> dict:                             # {"rows": [...], "n": int, "truncated": bool, "as_of_applied": str|None}
    """Read the joined panel (farm evaluations + evidence memory + G3 lineage
    verdicts), field-filtered rather than raw SQL -- a filter DSL is the
    structural read-only gate: no code path accepts an arbitrary query
    string, so there is nothing to inject and nothing to write through."""

def farm_query(
    preset: str | None = None, family_id: str | None = None,
    state: str | None = None,   # IDEA/CONDITIONAL/SUPPORTED/REGIME_SPECIFIC/COST_KILLED/REFUTED
    limit: int = 500,
) -> dict:
    """Read evidence_memory.state_of()/registry_rows() output -- the SAME
    function the registry export already calls, so this tool cannot diverge
    from what the allocator itself sees."""

def receipt(job: str, run: str | None = None) -> dict:
    """One job's receipt (evaluations log summary, night_search_state.json
    excerpt, or G3_lineage_verdicts.jsonl rows) by job name and optional run
    id. Returns 'CANNOT DETERMINE, no receipt at <path>' rather than raising,
    per the standing 'guards derive their inputs or refuse' rule."""

def leaderboard() -> dict:
    """The current registry export -- backend/data/signal_registry.yaml's
    conditional_evidence: block, read-only, exactly what to_registry() wrote."""
```

`--read-only` as a structural gate: these four functions live in their own MCP
tool module with NO import of any `append`/`observe`/write function from
`evidence_memory`, `ledger_retrieval`, or the farm — a test
(`test_mcp_surface_has_no_write_path.py`) walks the module's AST and fails if
any call target's name matches `{append, observe, write, save, set, update,
delete, supersede}` against a state-mutating module, the same "read the AST,
don't grep" discipline CLAUDE.md item 10 already demands for a different guard.

**Where it lives**: the `optimus` repo, alongside the existing
`aegis_verified_state`/`aegis_registry`/`brain_query` tools — those already
read Aegis Finance's state read-only from the `optimus` MCP server, and the
four new tools are the same shape. Building it in `aegis-finance` would
duplicate the MCP server Optimus already runs; the roadmap's own phrasing
("O6's tool set becomes the same surface") ties it to the `optimus` MCP
explicitly. The DATA these tools read (panel, farm receipts,
`G3_lineage_verdicts.jsonl`, `learned_rules.jsonl`) stays in `aegis-finance` as
committed/gitignored artefacts per existing convention; only the query LAYER
lives in `optimus`.

### 3c. Decay-blended target weights

`w_t = lambda * w_{t-1} + (1 - lambda) * target_t` — Qanat's own backtest
supports "decay blending (blends last N portfolios)"; Aegis's version becomes
a first-class `Policy` PARAMETER, not a separate code path:

```python
# portfolio_farm.Policy gains:
decay: float = 0.0     # lambda in [0, 1); 0.0 = no blending (today's default, unchanged)
```

Applied at the point `Policy` already sets weights each rebalance: `w_t =
decay * w_{t-1} + (1 - decay) * target_t`, renormalized to the book's gross
exposure after blending (the safety net for when `target_t`'s universe
changed since `t-1`, e.g. a name dropped out).

**Swept jointly with cost**, per the roadmap ("a first-class cost-control
parameter swept with `fee_bps`"): the farm preset that already sweeps
`fee_bps` gains `decay` as a second swept axis, `decay in {0.0, 0.2, 0.4, 0.6,
0.8}` crossed with the existing `fee_bps` grid. **Control: `lambda = 0`** —
every decayed result is reported BESIDE its `decay=0` twin at the same
`fee_bps`, same discipline as `calibration.py`'s "rolling reported beside
all-time, never instead of." The existing `Policy` zero-cost refusal
(`zero_cost_diagnostic=True` required to bypass) is untouched — `decay` and
`fee_bps` are orthogonal and the refusal fires regardless of `decay`.

**Known-answer test**: `decay=0` reproduces today's weights bit-for-bit on a
fixture — the parameter is additive at its default, not a behavior change,
turning the roadmap's stated control into a literal regression test.

---

## 4. BUILD ORDER FOR CHUNK 8 (cheapest test first) and receipts

| step | item | why this order | receipt written |
|---|---|---|---|
| 1 | **3c decay parameter + `decay=0` regression test** | pure-function change, zero new dependencies, zero new schema, the test IS the spec ("bit-for-bit at default") — cheapest possible thing that can go green | none new; existing farm receipt gains a `decay` column |
| 2 | **E5 §2.2-2.4 wiring** (`n_trials_raw`, `n_trials_effective_proxy`, DSR/PBO calls, DEPRIORITIZED verdict) using ONLY the scalar `fitness` already in `G3_evaluations.jsonl` — defer the ONC per-genome-return-vector work (§2.2.2) to a follow-up chunk | `multipletesting.py` functions already exist and are tested upstream; this step is integration against data that already exists on disk today, no G3 code change required yet | `G3_lineage_verdicts.jsonl` |
| 3 | **E5 known-answer tests** (§2.7, all five) | tests 1-2 need only synthetic data (no dependency on step 2's real-data wiring being perfect) and can run before step 2 is fully plumbed into the night job's main loop — write them alongside step 2, run them first | test file itself is the receipt |
| 4 | **3b read-only MCP surface**, `panel_query`/`farm_query`/`receipt`/`leaderboard` reading `G3_lineage_verdicts.jsonl` (now populated by step 2) + existing `evidence_memory`/registry outputs | depends on step 2's receipt existing so `panel_query` has something real to join; the AST no-write-path test is itself cheap and independent | `test_mcp_surface_has_no_write_path.py` output; a manual `panel_query` call against real data in the chunk-close verification |
| 5 | **3a anomaly cadence — week 1 only** (short-term reversal, needs no new data) | proves the whole cadence shape (prereg -> `lint_prereg.py` -> factor -> farm -> `evidence_memory.observe`) on the cheapest anomaly before committing to seven more weeks of build; weeks 2-8 are then a repeat of week 1's shape with different factor code, not new infrastructure | `docs/TRIALS/PREREG_ANOMALY_SHORT_TERM_REVERSAL_1.md`, one `evidence_memory` row, `NEGATIVE_RESULTS.md` entry if it fails |
| 6 | **M2 §1.1-1.2 pairing + prompt pipeline**, offline-stubbed only (fast suite) | the largest new surface (new LLM prompt contract, new schema); built after E5 exists so `arm_vs_control` pairs (§1.1) have `G3_lineage_verdicts.jsonl`'s DEPRIORITIZED/ACTIVE verdicts to pair against, giving M2 a second pair source beyond the ledger from day one | `learned_rules.jsonl` (empty/synthetic-only until real pairs exist) |
| 7 | **M2 §1.9 known-answer tests 1-2, 4** (planted rule, shuffled noise floor, leaked-field rejection) — all synthetic, no dependency on a real ledger having enough resolved rows yet | proves the STATISTICAL machinery (Brier scoring, shuffled-pair floor, schema validation) before the FIRST real month of ledger data exists to run it on for real — this is deliberately ahead of when M2 could produce its first real rule, because the gate must exist before the first rule is written (same argument `ledger_retrieval.py`'s own docstring makes for M3 pre-existing M2) | test file itself is the receipt |
| 8 | **M2 §1.3-1.8** (rule Brier scoring against live ledger rows, generalisation gate, `LEARNED_<month>.md` writer, M3 interop exception for rule rows) + **M2 §1.9 test 5** | needs at least one resolved month of ledger data to produce a non-synthetic firing; realistically the FIRST real `LEARNED_<month>.md` is empty or synthetic-only until the ledger has enough resolved rows post-M1 (chunk 5) — this step ships the MACHINERY, "the first rule with its own Brier" (the roadmap's own chunk-8 gate) may land in a LATER month's run once real data accrues, and the chunk-close report should say so explicitly rather than backfill a number | `backend/data/optimus/brain/LEARNED_<YYYY-MM>.md`, `learned_rules.jsonl` |
| 9 (deferred, named not built) | **ONC clustering for `n_trials_effective`** (§2.2.2) and **weeks 2-8 of the anomaly cadence** (§3a) | both are "more of the same shape already proven" rather than new mechanism — explicitly OK to run past chunk 8's boundary into chunk 9+ as a scheduled cadence rather than a one-time build; naming them here so they are not silently dropped | subsequent weeks' `PREREG_ANOMALY_*.md` + `evidence_memory` rows; a follow-up receipt once ONC ships showing `n_trials_effective_onc` populated where it was `null` in step 2's rows |

**The chunk-8 gate as stated in the roadmap** ("the first rule with its own
Brier") is satisfied at step 8 ONLY IF the live ledger already has >=45 resolved
rows for at least one `(mechanism_id_pair)` cell by the time chunk 8 runs
(`MIN_N_FOR_DECOMPOSITION`, reused unchanged from `calibration.py`). If it does
not — plausible, since M1 (chunk 5) may have landed too recently for a month
of resolutions to exist — the honest chunk-8 close is "the machinery exists,
tested against synthetic data; the first REAL rule is pending N more resolved
rows," not a fabricated first rule. This is the same "a check that did not run
is not a check that passed" discipline CLAUDE.md already states, applied to a
build gate rather than a statistical one.
