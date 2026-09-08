# BUILD 2026-09-07b — S1/S2: THE STRATEGY INTERFACE

**Lane:** `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 block **S**, rows S1 and S2.
**Licence:** PRODUCT_EXPERIMENT. **LLM spend: $0.00, 0 calls.** No orders, no
deploys, no seals opened, no pushes, no git state changed.

## RESULTS SCOREBOARD

| | |
|---|---|
| **Result improvement** | **NONE** — this block ships an interface, not an edge. Nothing about any book's returns changed; two existing books were re-expressed and reproduced. |
| Best historical net strategy vs the market | unchanged (`ensemble_ew\|k=100\|ew\|hold=200\|10bps`, β 1.195, +5.65%/yr t 2.42, era-concentrated) |
| Best forward paper strategy | unchanged |
| Independent selector count | unchanged (still 1: 99.5% of arena names carry 12-1 momentum only) |
| New actionable finding | the growth-book development cells reproduce **byte-for-byte** through a general interface; the vendored multiple-testing library agrees with every sealed DSR/PBO on record |
| External execution drag | not touched |
| LLM spend / cost per gradeable output | $0.00 / n.a. |

---

## 1. WHAT WAS BUILT

### `backend/strategy/` — the contract (S1)

| file | lines | what |
|---|---|---|
| `contract.py` | 478 | the `Strategy` record and its parts |
| `run.py` | 376 | `run_one` + the engine registry + receipt assembly |
| `chain.py` | 227 | invariant 17, the four-stage information chain |
| `verdict.py` | 321 | the Aegis side of the vendored stats library (Holm, n_effective, agreement) |
| `multipletesting.py` | 604 | **vendored verbatim** (568) + the MIT header (36) — S2 |
| `adapters.py` | 468 | the two existing books, expressed |
| `__init__.py` | 38 | exports; importing it registers the engines |

Tests: `backend/tests/test_strategy_contract.py` (209), `test_strategy_run_one.py`
(404), `test_multipletesting_port.py` (328). Note two PRE-EXISTING and unrelated
files, `test_strategy_library.py` / `test_strategy_library_rates.py`, are not
mine and were not touched.

New files outside the lane, both NEW (nothing existing was edited):
`scripts/run_one.py` (the CLI — also the reachability seed, see §5) and
`backend/data/optimus/strategy_interface/{S1_reproduction,S2_agreement}.json`
(the two receipts).

### The `Strategy` field list

```python
@dataclass(frozen=True)
class Strategy:
    strategy_id:   str
    title:         str
    universe:      Universe      # name, source, floor_dollar_vol_usd, min_price_usd,
                                 # max_names, fingerprint, note
    signal:        Signal        # name, column, direction(+1/-1), source,
                                 # warmup_periods, note
    construction:  Construction  # rule ∈ {top_k, composite_top_k, rank_weight,
                                 # passthrough}, k, weighting ∈ {ew, vw, inverse_vol,
                                 # rank, ce_kelly}, max_single_name, hysteresis_rank,
                                 # gross_cap
    hold:          HoldRule      # horizon_periods, min_hold_periods,
                                 # roi_ladder {periods_held: min_profit},
                                 # stop_loss, trailing_stop, exit_priority (typed,
                                 # RANKED), scheduled_review_periods
    sizing:        Sizing        # rule, gross_cap, notional_usd, overlays, params
    costs:         CostModel     # transaction_cost_bps (per side), slippage_bps,
                                 # financing_bps_over_rf, borrow_bps,
                                 # zero_cost_diagnostic
    benchmark:     Benchmark     # name, series_key, beta_matched, levered_at_budget,
                                 # is_own_universe_average
    objective:     Objective     # name ∈ {alpha_intercept,
                                 # terminal_wealth_at_drawdown_budget, sharpe,
                                 # rank_ic}, periods_per_year, drawdown_budget, utility
    loss_budget:   LossBudget    # positions_judged, expected_losers  (invariant 19)
    licence:       Licence       # PRODUCT_EXPERIMENT | CAPITAL_CANDIDATE | RESEARCH_CLAIM
    engine:        str           # which existing machine runs it
    engine_params: Mapping
    parents:       tuple[str, ...]
    note:          str

    .fingerprint -> sha256(as_dict())[:16]      # a drifted parameter is a new strategy
    .with_(**kw) -> Strategy                    # a mutation is a NEW strategy, not an edit
```

### `run_one` signature

```python
def run_one(strategy: Strategy,
            universe: Universe | None = None,     # defaults to strategy.universe
            window:   Window   | None = None,     # REQUIRED (refuses without one)
            objective: Objective | None = None,   # defaults to strategy.objective
            *,
            data: Mapping[str, Any] | None = None,
            sealed_authorisation: str | None = None,
            argv: list[str] | None = None,
            out_path: str | Path | None = None,
            tracker: RP.InputTracker | None = None,
            verbose: bool = False) -> dict        # the receipt
```

Registered engines: `series`, `arena_composite`, `growth_lab`. An unregistered
engine is a refusal listing the registered ones — `run_one` computes no returns
itself, so a fallback would be a second engine wearing an interface.

### The receipt (`schema: "strategy-receipt-1"`)

`beta` is **literally the first key**, pinned by
`test_BETA_IS_THE_FIRST_KEY_of_every_receipt`. Then: `beta_note`, `schema`,
`strategy_id`, `licence`, `strategy_fingerprint`, `strategy_row`, `strategy`,
`universe`, `window`, `objective`, `costs` (with `zero_cost_diagnostic`
travelling), `information_chain` (the four stages), `construction_defect`,
`signal_verdict`, `benchmark`, `book`, `grade`, `loss_budget`, `engine`,
`engine_block`, `llm_spend_usd`, `llm_calls`, `wall_seconds`, `generated_utc`,
`headline`, `_provenance` (`receipt_provenance.attach`: `sys_argv`,
`resolved_config`, `_inputs_opened` with a SHA-256 per file, `git_commit`).

**Invariant 17** is implemented in `chain.py`, wrapping `learner.fundamental_law`
(IC, effective breadth, TC already existed and are already tested — a second
derivation would be a second number for the same quantity) and adding what it
lacked: **hold statistics** (spells, one-sided turnover, censored open spells
reported separately) and **exit attribution by typed reason** (an exit with no
reason is counted `UNTYPED`, never dropped; a reason absent from the contract's
declared priority is reported). `TC < 0.5` sets `construction_defect: true` and
`signal_verdict: UNREADABLE_CONSTRUCTION_DEFECT`. **An unmeasured TC is
`CANNOT DETERMINE`, never a pass.**

**Costs** are refused by *delegation*: `CostModel.__post_init__` constructs a
`portfolio_farm.Policy`, so the repository has exactly one zero-cost refusal and
`PolicyError` appears in the traceback (pinned by test).

---

## 2. THE ACCEPTANCE GATE — RESULT

Command: `python -m scripts.run_one --reproduce`
Receipt: `backend/data/optimus/strategy_interface/S1_reproduction.json`

### (b) the growth-book champion — **BYTE-FOR-BYTE, PASS**

`growth_champion_strategy()` reads the frozen `G4_CHAMPION_DECLARATION.json`
(genome `m12_quality_mom|dd`, `champion_sha256 39ab3224…`), `run_one` dispatches
to engine `growth_lab`, which calls `growth_g3_mutations._build_child` and
`learner.growth.evaluate_growth` — the same two functions the sealed receipt was
written with — and the result is compared against
`G4_seal.json["development"][…]`.

| cell | fields compared | value-for-value | key order | sha256(run) | sha256(sealed) | **byte-identical** |
|---|---|---|---|---|---|---|
| `10bps` | 88 leaves | 88/88 identical | identical | `c1663dde546196d9…` | `c1663dde546196d9…` | **YES** |
| `25bps` | 88 leaves | 88/88 identical | identical | `e976d531892a2150…` | `e976d531892a2150…` | **YES** |

Byte comparison is through the serialiser the sealed receipt was written with
(`json.dumps(obj, indent=1, default=str)`), so **key order is part of the claim**
— strictly stronger than a field-by-field diff. β reproduces exactly: 0.7673
(10 bps) and 0.7650 (25 bps). **Zero differing fields.**

The **sealed half is REFUSED, by design.** `G4_seal.json["sealed"]` covers
2016-01..2024-12, which `SEALED_ERA_OPENINGS.jsonl` records as opened once for
this champion, and `run_one` raises `SealedWindowRefused` on a sealed window
without an explicit `sealed_authorisation` (which nothing in this lane passes).

> **A sealed receipt that could be re-run on demand would not be sealed.** This
> is the one place where "reproduce the sealed receipt byte-for-byte" cannot be
> satisfied, and satisfying it would have destroyed the property being tested.
> Reported as `REFUSED_BY_DESIGN` on the receipt and pinned by
> `test_the_sealed_era_of_the_growth_book_is_REFUSED_by_run_one`.

Two further fields on `G4_seal.json` are *not* reproducible by any code:
`generated_utc`, `wall_seconds` (and `frozen_utc` on the declaration). They are
named in `compare_to_sealed(...)["ignored_keys"]` rather than skipped silently —
"we did not compare it" and "it agreed" must never read the same.

### (a) the composite arena book — **PASS on what it actually has; one honest gap**

`arena_book_strategy("ENGINE_BASELINE_v1")` reads the real YAML through the real
loader (`spec.load_specs()`, not a hand-built dict — a dict-built test is exactly
what missed the 2026-08-24 selector defect). `run_one` dispatches to engine
`arena_composite`.

| artefact | sealed value | reproduced | match |
|---|---|---|---|
| `config_hash` | `641adafc38703b5c3c898103639cd9e7c1f3608275757b2c93ac74f5f71ef7db` | same | **YES** |
| `policy_fingerprint` | `576ea6240d3525cd95f89d3326c480049272b7268979e1c56289a530d80eac47` | same | **YES** |
| `book_fingerprint` | `39c7177b5d6e517c8f6795fc3d879132503a24501385ae4c20e57392ec714005` | same | **YES** |
| `config_version` | `arena-v1` | same | **YES** |
| selection (12 names, ranks, scores) | `policies.select` | identical object | **YES** |
| weights | `policies.size` | identical dict, gross 1.0 | **YES** |

4/4 identity fields and the full selection reproduce. The reproduced identity
block is a **superset** (it also carries `selector_identity`
`arena_composite@3-universe_quality` and `composite_weight_fingerprint`
`41b4bbfa5d3df8c8`), so the accurate claim is *byte-for-byte over every field the
sealed artefact declares*, not "the two files are the same bytes".

> **THE GAP, STATED PLAINLY: there is no sealed BACKTEST receipt for the
> composite arena book in this repository.** The arena is a **forward paper
> engine** — its NAV rows come from live marks, and its tamper-evident artefact
> is its identity under scheme `book-v1` plus the deterministic policy layer.
> Searching `backend/data/` for `641adafc…` returns exactly one file, and it is
> a test. So "reproduce its sealed receipt" was executed as "reproduce its
> identity and its selection", and the receipt says so in
> `why_no_backtest_diff` rather than manufacturing a replay to diff against.

Correspondingly the arena engine returns **`beta: None`**. A forward paper book
has no offline series to regress, and the lane NAV table that could supply one is
separately marked STALE (roadmap X2). `CANNOT DETERMINE` is the finding; quoting
a stale table's β would not be.

---

## 3. S2 — THE MULTIPLE-TESTING LIBRARY, AND THE AGREEMENT TABLE

Vendored **verbatim** from
`C:\Users\mrthn\reference\Vibe-Trading\agent\src\quantlib\multipletesting.py`
(HEAD `a4f06a29`, 2026-09-07, **MIT**) to `backend/strategy/multipletesting.py`.
The upstream file carries no per-file header, so the project's `LICENSE` is
reproduced verbatim as a prepended comment block; the body is unedited and
`test_the_vendored_body_is_not_edited` byte-compares it against the clone.
Aegis-side additions live in `verdict.py` and import from it.

Supplied: `probabilistic_sharpe_ratio`, `deflated_sharpe_ratio`,
`expected_maximum_sharpe`, `benjamini_hochberg`,
`probability_of_backtest_overfitting` (CSCV), `sharpe_ratio`.

Command: `python -m scripts.run_one --s2-agreement`
Receipt: `backend/data/optimus/strategy_interface/S2_agreement.json`

### PBO — against the sealed growth family

| | value |
|---|---|
| sealed receipt (`G2_generation0.json::pbo_over_the_whole_family.pbo`) | **0.6429** |
| vendored library, unrounded | **0.6428571428571429** |
| `learner.inference.pbo` (what wrote the receipt), rounded | 0.6429 |
| delta vendored vs receipt | 4.286e-05 |
| shape | 88 arms × 144 months, 70 partitions (C(8,4)), 0 rows dropped |
| verdict | `SELECTION_IS_OVERFIT` on both |

### DSR — every leaderboard cell that carries one

86 cells checked at `n_trials = 88` (the declared family size).
**0 disagreements at the receipt's own precision. Max |vendored − receipt| = 4.98e-05.**

| cell | sealed DSR | vendored (unrounded) | delta |
|---|---|---|---|
| `nn_pre_causal\|dd\|10bps` | 0.1199 | 0.1198501758755014 | 4.982e-05 |
| `mom_12_1_ew\|dd\|10bps` | 0.0008 | 0.0008493776410822 | 4.938e-05 |
| `quality_mom\|dd\|10bps` | 0.2535 | 0.2535486291254626 | 4.863e-05 |
| `mom_12_1_ew\|dd\|25bps` | 0.0004 | 0.0003537653992425 | 4.623e-05 |
| `lgbm_clf\|25bps` | 0.0730 | 0.0730459554036455 | 4.596e-05 |
| … 81 more, all below 4.6e-05 | | | |

### The 1e-9 gate, and the honest reading of it

**The gate as written ("equal to the sealed receipts to 1e-9") is not
satisfiable against a receipt, and that is arithmetic, not a defect.**
`learner.inference` rounds DSR and PBO **to 4 decimal places on the way into a
receipt** (`round(float(dsr), 4)`, `round(p, 4)`), so the receipt cannot carry
more than 4 dp of information and every delta above is between 0 and 5e-05 by
construction. Every one of the 87 deltas is strictly below 5e-05, i.e. **every
value round-trips to the sealed number exactly**.

The 1e-9 claim is therefore made where it *is* meaningful — between the two
implementations, before either rounds:

| quantity | agreement | test |
|---|---|---|
| `expected_maximum_sharpe(N, sd)` vs `learner.inference`'s closed form, N ∈ {2, 8, 88, 462} | **< 1e-9** | `test_expected_maximum_sharpe_matches_the_closed_form_in_learner_inference` |
| DSR = Φ(z), full expression rebuilt from `inference`'s own helpers, N ∈ {2, 8, 88, 462} | **< 1e-9** | `test_the_two_DSR_implementations_agree_to_1e_9_BEFORE_any_rounding` |
| PBO on a common matrix | identical to `inference`'s 4-dp output | `test_vendored_PBO_equals_learner_inference_PBO` |

**Which implementation is right?** Both, on the numbers that matter — there is no
disagreement to adjudicate. Four *behavioural* differences exist and are
deliberate choices, not errors, recorded here so nobody re-discovers them:

1. **Block construction.** `learner.inference.pbo` uses `np.linspace` blocks and
   consumes every row; the vendored CSCV uses `n // n_splits` and **trims and
   reports** the remainder. On T divisible by `n_splits` (144/8, the sealed case)
   they are identical. On T = 145 they differ by one row, and only the vendored
   one tells you.
2. **Default `n_splits`.** Upstream defaults to 16; `verdict.pbo` deliberately
   defaults to **8**, because 8 is what every existing Aegis receipt was computed
   at, and a shared library that silently changed the default would make two
   sessions' numbers incomparable — the exact problem it was adopted to fix.
   Pinned by `test_pbo_default_splits_is_8_not_the_upstream_16`.
3. **Tie handling in the OOS rank.** Upstream uses average ranks; `inference`
   uses a strict `<` count. Identical without ties.
4. **Minimum sample.** Upstream refuses below 30 observations (the skew/kurtosis
   estimates are hopeless there); `inference` refuses below 8.

**Conclusion: the vendored library is adopted as the CALCULATOR for new verdicts;
`learner.inference` stays the historical record and is not modified — changing it
would invalidate every sealed receipt that quotes it.**

### The two documented gotchas, encoded as tests

* **Per-observation vs annualised Sharpe.** Undetectable in code by construction;
  `test_gotcha_one_…` shows the size of the error instead — a per-observation
  Sharpe of 0.15 over 144 months gives PSR < 0.99, its ×√12 annualised twin gives
  > 0.99. A coin flip turned into a certainty.
* **Non-excess kurtosis.** `scipy.stats.kurtosis` and `pandas.Series.kurt` both
  return the excess form. Passing 0.0 **raises** (`"Excess kurtosis was probably
  passed"`), pinned by `test_gotcha_two_…`.

### The three house rules (`verdict.py`)

* **SCREEN = BH-FDR, EXPORT = Holm** (CANON §63). `screen_then_export` returns
  both plus `screened_not_exported` — the gap between "worth another look" and
  "defensible". Holm is not in the vendored file; it is written here, with a
  monotonicity test and a hand-computed check.
* **`n_effective` counts DATE BLOCKS** (CANON §58) — `n_effective_date_blocks`,
  tested on 1500 name-days over 3 months → 3.
* **A non-finite p is dropped AND COUNTED**, never treated as one.

---

## 4. TEST COUNTS — BASELINE vs FINAL

Command: `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow" -q --timeout=300`

| | baseline (before this lane) | final |
|---|---|---|
| passed | 7138 | **7364** |
| failed | **1** | **7** |
| skipped | 20 | 20 |
| deselected | 123 | 124 |
| wall | 761.6 s | 673.9 s |

New tests added by this lane: **66** (`test_strategy_contract.py` 21,
`test_strategy_run_one.py` 25 incl. 1 `slow`, `test_multipletesting_port.py` 20)
— all pass, including the `slow` byte-for-byte growth reproduction.

**Every failure in both columns belongs to another agent's lane. None is mine.**
The tree was dirty with six other agents' concurrent work throughout.

| failure | cause | mine? |
|---|---|---|
| `test_signal_reachability::test_every_orphan_is_classified` (baseline) | `backend.services.sec_insider_bulk`, then `backend.services.free_inference` — new unclassified services. My own two modules appeared here mid-run and were fixed by giving them a caller (`scripts/run_one.py`). **Now passes.** | no |
| `test_guard_missing_input_contract::test_every_guard_is_enrolled` | `backend/services/scrape_store.py` — a new service with its own exception, not enrolled in `guard_contract.CASES`. `backend/strategy/` is outside that scanner's scope by construction. | no |
| `test_arena_brain.py` ×6 | the tests stub `backend.services.llm_research` with a 3-attribute fake; another agent's lane expanded `llm_research.py` (+54) and `model_provider.py` (+73) this session. `initiations` comes back 0 instead of 1. Nothing in `backend/strategy/` is imported by `beliefs.py` (`grep backend.strategy backend/services/ learner/` → no hits). | no |

---

## 5. FILES TOUCHED OUTSIDE `backend/strategy/` AND `backend/tests/`

All **NEW**; no existing file was edited anywhere in the repository.

| path | why |
|---|---|
| `scripts/run_one.py` | the CLI (`--list / --arena / --growth / --reproduce / --s2-agreement`). **Also load-bearing:** `signal_reachability` seeds its closure from `backend/routers/` and `scripts/`, so a `backend/**` module with no script or router caller is a red suite. This gives the whole package one. |
| `backend/data/optimus/strategy_interface/S1_reproduction.json` | the acceptance receipt |
| `backend/data/optimus/strategy_interface/S2_agreement.json` | the DSR/PBO agreement receipt |

---

## 6. WHAT DID NOT WORK / WHAT IS NOT DONE

1. **A sealed receipt cannot be reproduced end-to-end and must not be.** The
   growth book's `sealed` block is `REFUSED_BY_DESIGN`. Only the `development`
   half is reproduced (byte-for-byte). Anyone reading the gate as "all of
   `G4_seal.json`" should read this paragraph first.
2. **The arena has no sealed backtest to diff against.** Identity + selection
   only. Giving the arena an offline replay path is real work and is not in this
   lane; until it exists, the composite book's β is `CANNOT DETERMINE` from the
   interface.
3. **The `series` engine's `sharpe` objective extractor is a stub.**
   `_objective_value` returns `CANNOT DETERMINE` for it rather than a wrong
   number; `alpha_intercept` and `terminal_wealth_at_drawdown_budget` are real.
4. **No `portfolio_farm` engine yet.** The farm's `Policy` is *used* (it is what
   refuses zero costs) but `run_many` is not wrapped, so a farm preset is not yet
   expressible as a `Strategy`. That is the obvious next file and is why the
   engine registry is a decorator.
5. **The four-stage chain is only fully populated when the caller supplies a
   panel + weights.** Both adapters currently supply weights for at most one
   period (arena) or none (growth — `growth_lab` returns a portfolio series, not
   per-name weights), so stages 1-3 come back `CANNOT DETERMINE` on both real
   books. **The invariant-17 block is built and tested; it is not yet fed.**
   Feeding it needs `growth_lab.build_panel_base` to return its holdings, which
   is an edit to an existing module and therefore out of this lane.
6. **S3-S8 are not started** (leak detectors, `do_predict` manifold flag,
   `breakeven_fee_bps`, exit ladder in `alpha/contract.py`, protections-as-data,
   Numerai habits). S6's ladder *shape* exists in `HoldRule.roi_ladder` and is
   tested; the terminal repo's `alpha/contract.py` was not touched.
7. **The gitignored parquet.** `G2_genome_series.parquet` is `*.parquet`-ignored,
   so `test_vendored_PBO_reproduces_the_sealed_growth_family_PBO` **skips on CI
   with a reason that names the file**. It ran here and passed. The
   implementation-vs-implementation tests run everywhere on seeded synthetic
   data, so CI is not left with nothing.
8. **`ruff` is not installed in this environment** (`No module named ruff`), so
   the lint ratchet was checked by hand: no line over 100 chars outside the
   vendored file, no unused imports, `py_compile` clean.

---

## 7. HOW A NEW MECHANISM ARRIVES NOW

```python
from backend.strategy import (Strategy, Universe, Signal, Construction, HoldRule,
                              Sizing, CostModel, Benchmark, Objective, LossBudget,
                              Window, run_one)

s = Strategy(strategy_id="insider:opportunistic_buy",
             title="opportunistic insider buying, 3-month hold",
             universe=Universe(name="tradable", floor_dollar_vol_usd=3e6),
             signal=Signal(name="opportunistic_buy", column="opp_buy_z"),
             construction=Construction(rule="top_k", k=50, weighting="ew"),
             hold=HoldRule(horizon_periods=63, min_hold_periods=21,
                           roi_ladder={0: 0.15, 21: 0.06, 42: 0.0},
                           stop_loss=-0.12,
                           exit_priority=("THESIS_INVALIDATED", "STOP",
                                          "ROI_LADDER", "DEADLINE")),
             sizing=Sizing(rule="equal_weight", gross_cap=1.0),
             costs=CostModel(transaction_cost_bps=25.0, slippage_bps=0.0),
             benchmark=Benchmark(name="SPY TR"),
             objective=Objective(name="alpha_intercept"),
             loss_budget=LossBudget(positions_judged=20, expected_losers=8),
             engine="series")

receipt = run_one(s, window=Window("2006-01", "2015-12"), data={...})
```

One file, one call, one receipt — beta first, costs never zero, four stages
reported, provenance attached, and a fingerprint that changes the moment any
parameter drifts. **Never fold a surviving family into `arena_composite` as a
weight:** a new mechanism is a new `Strategy` with its own `strategy_id`, and the
contract has no field in which to hide one inside another.
