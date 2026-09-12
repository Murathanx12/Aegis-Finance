# SPEC — the TAQ-derived empirical cost curve (roadmap §11c idea #1)

Status: DRAFT for a builder. Licence: this spec itself makes no claim; the
curve it describes is infrastructure a `PRODUCT_EXPERIMENT` book may use
immediately (no significance gate) and a `RESEARCH_CLAIM` must re-derive
sensitivity against (§3 below).

## 0. What already exists (read this before building anything)

Grounding, so the builder does not re-discover what is already on disk.

**The panels, already measured:**
- `backend/data/optimus/taq_quoted_spreads_calibration.csv` +
  `.meta.json` — QUOTED NBBO spread, 184/185 names retired their Order-18
  declared band (`docs/TAQ_COST_CALIBRATION.md`). This is the OLDER, cruder
  panel: `backend/services/taq_calibration.py` consumes it and produces
  `MEASURED_TAQ_QUOTED` `OneWayBps` values (half the quoted full spread).
  Median retired name 2.726bp one-way.
- `backend/data/optimus/taq_effective_spreads_v1.jsonl` (**4,224 rows**,
  184 names × 23 days) + `.meta.json` — the EFFECTIVE spread panel from
  `taqm_2026.wct_*` (WRDS-computed trades, prevailing NBBO already matched
  server-side). This is the panel the roadmap item names. Per-row fields:
  `date, ticker, n_trades, effective_full_bps_median,
  effective_full_bps_dollar_weighted, quoted_at_trade_full_bps_median`.
  Meta's `headline_sensitivities`: `effective_over_quoted_median_of_names:
  0.369`, `effective_one_way_bps_median: 1.076`, vs the declared 1-5bp band
  84 below / 98 inside / 2 above.
  **verdict_status is `DEFERRED`** — v1 has NO trade-condition/odd-lot
  filtering, and the conventions probe (`effective_conventions_probe_
  20260814.json`, 9 names × 3 tiers × 10 conventions) found strict HJ
  conventions RAISE the ratio toward 1 (e.g. NVDA composed-HJ ratio 0.50 vs
  v1-all 0.72), so v1's 0.369/1.076bp headline UNDER-states the true
  effective-to-quoted ratio. **This curve must not claim v1's number as
  final** — see §3.
- **Nothing in this repo consumes the effective-spread panel yet.**
  `taq_calibration.py` only reads the quoted CSV. This spec is what wires
  the effective panel into a cost model a `Policy`/`CostModel` can use.
- `backend/data/optimus/wrds/entitlement_map_2026-08-19.json` — the citable
  WRDS entitlement authority (do not cite the WRDS catalogue page).

**The code that already prices impact, unwired:**
- `backend/strategy/vendor/impact.py` (vendored MIT, byte-pinned by
  `test_strategy_execution.py`) already has `sqrt_impact(price, direction,
  volume_traded, adv, volatility, eta=DEFAULT_SQRT_IMPACT_ETA=0.5)` =
  `eta * volatility * sqrt(volume_traded / adv)` — the Almgren-Chriss
  square-root impact TERM (explicitly NOT full A-C optimal execution: no
  trajectory, no permanent/temporary split, no risk-aversion parameter —
  the module docstring says so and this spec repeats it rather than
  overclaiming). Also `linear_impact` (order 0.5-5% ADV) and
  `fixed_slippage`.
- `backend/strategy/vendor/factor_costs.py` (vendored MIT) wraps these with
  an ADV participation cap that carries the shortfall forward
  (`apply_adv_capacity`), `rebalance_cost`, `borrow_cost`. Built for
  factor-bench weight-space costing, NOT wired to `portfolio_farm.Policy`
  or `backend.strategy.contract.CostModel`.
- `backend/strategy/execution.py` calls the vendor modules for a different
  code path (`adv_capped_path`, `execution_row`) — also not wired to
  `Policy`/`CostModel`.

**The cost application that must not regress:**
- `backend/services/portfolio_farm/policy.py::Policy` — `transaction_cost_
  bps` (one-way, default 5.0) + `slippage_bps` (default 1.0); constructor
  REFUSES `cost <= 0` unless `zero_cost_diagnostic=True` (and refuses the
  flag with nonzero cost); `round_trip_bps = 2*(tx+slip)`; both flow into
  `policy_id` (the SHA-256 over the whole frozen record).
- `backend/services/portfolio_farm/replay.py` — `cost_rate = (tx_bps +
  slip_bps)/10_000` is a SCALAR applied to `notional` traded (`fee =
  notional * cost_rate`), i.e. already correctly charged on REALISED
  traded notional, not total book notional. This is the reference for how
  a per-name curve must integrate: replace the scalar `cost_rate` with a
  per-name, per-fill rate, keeping the same `notional`-weighted
  application.
- `backend/strategy/contract.py::CostModel` — `transaction_cost_bps=5.0`
  (one-way), `slippage_bps=1.0`, `financing_bps_over_rf`, `borrow_bps`,
  `zero_cost_diagnostic`. `__post_init__` constructs a `Policy` purely so
  the ONE zero-cost refusal fires there (delegated, not re-implemented).
  `as_row()` puts `zero_cost_diagnostic` on every row so a frictionless
  number can never be quoted as net.
- `learner/evaluate.py::TRADABLE_DOLLAR_VOL = 3_000_000.0` — the execution
  floor (`Universe.floor_dollar_vol_usd` in `contract.py`); pinned equal
  across `N3`, neural-long, P7 by cross-module tests
  (`test_n3_size_aware_floors.py`, `test_neural_long.py`,
  `test_p7_pit_universe_vintage.py`).

**The C2 artefact this spec must not repeat a version of:**
`docs/HANDOFF_2026-09-10_THE_REPLAY_AND_THE_EXE.md` §4 and
`docs/HANDOFF_2026-09-10_OPUS_BUILDER_MAP.md` §2.2: a `scripts/night_*.py`
job charged **25bp × 2 sides × 2 legs × 252** — i.e. flat bps assuming
100% daily turnover regardless of REALISED turnover — turning
+30.6/+19.5/+15.0%/yr gross into −221/−233/−237%/yr net. The fix filed
there was "charge `Σ|Δw| × bps` on realised turnover, print turnover/day
beside net" — a DIFFERENT bug from "the rate is flat" (this one is "the
base is wrong"). `portfolio_farm.replay.py` already charges on realised
`notional`, so that specific bug is not present in the farm's own engine —
but the audit ("grep `cost_note`/`cost_bps` across `scripts/night_*.py`")
was filed and its status should be checked before this curve is wired
into any night script, or the new curve will be multiplied onto the same
wrong base and produce a second, differently-shaped, artefact.

**Existing cost-model uncertainty this curve must be honest about**
(`NEGATIVE_RESULTS.md` §25, INSTR-CS-SPREAD): Corwin-Schultz (AGK's
cousin) vs Kyle-Obizhaeva impact model disagree by **3.4-9.1x** on LEVEL
in the very same large/mid and small segments (Spearman rank agreement
0.66 — they agree on ORDER, not magnitude). Frozen verdict there: "KO
UNDERSTATES COSTS." The new TAQ effective-spread panel's median (1.076bp
one-way, large/mid liquid names) sits BELOW even KO's large/mid range
(3.4-4.2bp) — i.e. three cost rulers now disagree by an order of
magnitude at the liquid end, and this spec's curve is a fourth. Every
receipt this curve produces states which ruler it used and does not
imply the others are wrong.

---

## 1. THE COST CURVE

### 1.1 Per name-day, one-way cost

```
one_way_bps(name, date, order) =
    half_effective_spread_bps(name, date)          # §1.2 / §1.3
  + impact_bps(name, date, order.participation)     # §1.4
```

Both terms are one-way; a round trip is `2 * one_way_bps` (unchanged
convention from `CostModel.round_trip_bps` and `Policy.round_trip_bps`).
Reported separately on every receipt (§2) — collapsing them into one
number is how "spread" and "impact" get confused three call sites later,
the exact failure `cost_model.py`'s docstring already warns about for
`COST_BPS_ONE_WAY`.

### 1.2 The spread term where TAQ measured it

`half_effective_spread_bps(name, date)` = `effective_full_bps_median / 2`
from `taq_effective_spreads_v1.jsonl`, keyed on `(ticker, date)` — the
SAME per-name-day granularity `taq_calibration.reading_for` already
aggregates for the quoted panel, so this reuses that module's aggregation
pattern (median-of-daily-medians, `MIN_DAYS=15`, `MIN_QUOTES_PER_DAY`
equivalent gate on `n_trades`) rather than inventing a second one.
Provenance: a NEW constant, `MEASURED_TAQ_EFFECTIVE`, distinct from
`MEASURED_TAQ_QUOTED` — do not reuse the quoted-panel provenance string,
per `cost_model.py`'s own rule that a quoted spread and an effective
spread are different quantities and share no name past the first call
site that stores one.

**This provenance carries the DEFERRED flag forward.** Because v1's
`verdict_status` is `DEFERRED — trade-condition conventions decide the
refined computation`, `MEASURED_TAQ_EFFECTIVE` rows carry
`conventions="v1_unfiltered"` in their basis string, and a
`survives_convention_sensitivity()` function (mirroring
`taq_calibration.survives_bias_sensitivity`) checks a downstream verdict
against the conventions-probe range already measured on 9 names × 10
conventions (composed-HJ ratios ran 0.50-1.0 vs v1-all's 0.72 on NVDA,
i.e. up to ~40% higher effective spread under stricter conventions). A
verdict that only holds under v1's unfiltered convention is
`COST_MODEL_SENSITIVE` by the existing `cost_model.CostBand` mechanism,
not a silent pass.

### 1.3 The spread term where TAQ did NOT measure (extrapolation)

For the ~2,900 names in `TRADABLE_DOLLAR_VOL`-eligible universes but
outside the 184-name TAQ panel (the panel is S&P/liquid-mega-cap-heavy —
check via `taq_calibration.load_panel()` ticker set vs
`learner.evaluate`'s universe), fit:

```
log(half_effective_spread_bps) = b0 + b1*log(dollar_volume_usd)
                                     + b2*log(price_usd)
                                     + b3*volatility_ann
                                     + eps
```

**Why this exact form and these three regressors:**
- `log(dollar_volume)` is the liquidity axis every precedent in this repo
  already uses for spread: `FINDING_2026-08-31_SPREAD_BY_LIQUIDITY_BAND.md`
  found quoted spread falling monotonically from 148.9bp ($100k-1m/day
  band) to 6.7bp ($50m+/day) across 5 dollar-volume bands on 30-name
  samples per band — five points already on this curve's shape, usable as
  an OUT-OF-SAMPLE check on `b1`'s sign and rough magnitude (quoted, not
  effective — convert via the panel's own quoted/effective ratio, §1.2's
  `MEASURED_TAQ_QUOTED` join, before comparing levels).
  `scripts/taq_spread_by_liquidity_band.py` is the code; the corrected
  round-trip convention there (ONE spread, not two — `(ask-mid)+(mid-bid)
  = ask-bid`, not double it) is the same halving convention `OneWayBps`
  already encodes, so no re-derivation is needed, just reuse.
- `log(price)` because the tick-floor mechanism in `taq_calibration.py`
  (`tick_floor_bps = 1e4 * 0.01 / mid_price`) means a $2 stock's spread is
  bounded below by a much larger bps figure than a $500 stock's for
  identical dollar liquidity — price is not redundant with dollar volume
  once tick-quantisation matters (28 of 184 TAQ-panel names are already
  AT the tick floor per `TAQ_COST_CALIBRATION.md`).
  Feed from local columns: CRSP `dsf` close, or the panel's own `mid`
  field.
- `volatility_ann` because spread and volatility co-move mechanically
  (inventory-risk component of every microstructure spread model since
  Roll/Glosten-Milgrom) and because it is the SAME regressor the vendored
  `sqrt_impact` needs for the impact term (§1.4) — fitting it once and
  reusing the fitted value for both the spread-extrapolation and the
  impact call keeps the two terms internally consistent. Feed: the panel
  already has per-name-day data; volatility comes from local
  `backend/services/spread_estimators.py` or CRSP daily returns
  (whichever `taq_calibration`'s caller already has loaded — do not add a
  new fetch for a number the repo already computes elsewhere, per the
  silent-fragility-audit discipline).

**Fit on the 184 TAQ-covered names** (right-hand-side variables from
CRSP/local data, left-hand-side from `taq_effective_spreads_v1.jsonl`
aggregated to one row per name via `effective_full_bps_median` /2),
report R², coefficient signs and CIs, and validate out-of-sample against
the AAPL/DXCM/NVDA/FSLR/etc. conventions-probe tiers (`liquid_sub1bp`,
`mid_5bp`, and whatever the wide tier is named) since those already carry
independently-computed tier labels.

**A name below both**: no TAQ row AND missing one of the three
regressors (e.g. no volatility because <60 days of history) falls back to
`cost_model.declared_liquid_band()` (`DECLARED_CONSERVATIVE`, 1-5bp
one-way) — the SAME refusal-to-guess discipline `taq_calibration.py`
already enforces for AGK/TAQ segmentation. This function must not
silently return the regression's population mean; an absent name is not
an average name (mirrors `taq_calibration.reading_for`'s own refusal
language verbatim in spirit).

### 1.4 The impact term

`impact_bps(name, date, participation) = 1e4 * sqrt_impact(1.0, +1,
participation, 1.0, volatility_ann) - 1e4` reduces to `eta * volatility *
sqrt(participation)` in bps once `price=1, direction=+1, adv=1` collapse
the vendored function to its bare impact fraction — call the vendored
`backend.strategy.vendor.impact.sqrt_impact` directly rather than
re-deriving the formula (byte-pinned MIT vendor file; do not fork it).
`participation = order.notional_usd / (dollar_volume_usd_that_day)`, the
same participation-rate definition `_participation_rate` already uses.

**Coefficient (`eta`), calibrated from the literature, not the vendor's
generic 0.3-0.8 default range:**
- Almgren, Thum, Hauptmann, Li (2005), "Direct Estimation of Equity
  Market Impact" — the original empirical square-root calibration on US
  equities; cite for the FUNCTIONAL FORM (`eta * sigma * sqrt(POV)`) and
  its order-of-magnitude `eta`.
- Frazzini, Israel, Moskowitz (2018), "Trading Costs" (AQR) — measures
  ~30-50bp OF ONE-WAY COST (not impact alone; blends spread+impact) at
  **1% of ADV** across a large live-trade dataset; use this as a
  CALIBRATION TARGET for `eta` at `participation=0.01`, net of the
  spread term already charged separately in §1.2/1.3 (do not double-count
  spread inside `eta`) — i.e. solve `eta` from `impact_bps(participation=
  0.01) ≈ 30-50bp − half_spread_bps` at a representative liquid-name
  volatility, and state the solved `eta` and its assumed spread subtraction
  explicitly on the receipt, since this is the one number in this whole
  spec that is DERIVED rather than measured.
- Novy-Marx & Velikov (2016), "A Taxonomy of Anomalies and their Trading
  Costs" (RFS) — cite for cost-per-trade BY SIZE BUCKET (their
  decile-of-market-cap cost schedule), used as a second calibration check
  on the FITTED CURVE's total one-way cost (spread + impact) across size
  buckets, independent of the `eta` solve above; this is the
  cross-validation the spec's §3 formalises.

**Where participation comes from at the point of use:** `Policy`/
`CostModel` do not currently carry an order-size concept beyond
`notional_usd` and `top_k` — `participation` must be computed by the
caller (the farm's `replay.py` loop, at the point it already computes
`notional` per fill, §0) and passed into the curve function; the curve
itself is stateless and takes `(ticker, date, participation, volatility)`
as arguments, never reaching into a global panel object per call (matches
the existing style: `taq_calibration.reading_for(panel, ticker)` takes an
explicit panel).

### 1.5 The retail regime — a SECOND, separate curve

Institutional TAQ costs (§1.2-1.4) describe execution nobody in this
program has: Aegis trades through Alpaca paper, IEX quotes (~2.5% of
consolidated volume, `research_daytrading.md` §"Data/cost infra"), with
documented fill quirks (partial fills 10% of the time at random size,
size not checked against NBBO depth, `tif=opg` 13/15 EXPIRED UNFILLED on
2026-09-02). A single curve conflating these would silently apply
institutional costs to retail fills or vice versa, so the retail regime
is its OWN curve, `retail_paper_bps(ticker, date, order)`, fed by:

- **The D2 fill-quality receipt** (roadmap chunk 5b, `docs/ROADMAP_2026-
  09-11...md` line 492) — "every paper fill vs the IEX quote and vs the
  SIP NBBO where available; the realised spread per name per session is
  the cost model's input from day one." **This does not exist on disk
  yet** (`find . -iname "*fill_quality*"` returns nothing) — it is chunk
  5b's own deliverable. The retail curve in THIS spec is therefore a
  STUB until 5b lands: `retail_paper_bps` reads
  `backend/data/optimus/fill_quality/*.jsonl` (path to be fixed by 5b's
  builder) if present, else raises the same `TaqRefused`-shaped refusal
  ("no fill-quality receipt; a retail book may not claim
  `curve="retail_paper"` until one exists") rather than silently falling
  back to the institutional curve, which would understate retail cost by
  construction (Alpaca's IEX-only visibility is a narrower, worse book
  than the SIP-wide TAQ tape).
- Until D2 lands, a `curve="retail_paper"` `Policy`/`CostModel` uses a
  DECLARED band derived from `research_daytrading.md`'s own numbers:
  retail one-way ≈ 25bp (the number every night receipt currently flat-
  charges) as the ceiling, institutional TAQ effective one-way (§1.2,
  ~1.08bp liquid) as the floor it can never be BELOW (Alpaca cannot beat
  the NBBO), stated as a `CostBand` via `cost_model.CostBand`, not a
  point estimate — the same "declare a band, do not pick an end" pattern
  already enforced for the AGK segment.

### 1.6 The choice rule

A `Strategy`/`Policy` declares its regime once, at construction, never
both: add `curve: str` to `CostModel` (and mirror it in
`portfolio_farm.Policy`, §2) restricted to `{"flat", "taq_empirical",
"retail_paper"}`, defaulting to `"flat"` so every existing frozen
`policy_id` is unaffected (§2.2 on why this MUST default to `flat`). A
`Strategy.costs.curve == "taq_empirical"` book run against Alpaca paper
fills, or a `curve == "retail_paper"` book graded against a CRSP
institutional replay, is a `StrategyError`/`PolicyError` at construction
— the mismatch is exactly the kind of silent regime confusion §1.5 opens
with, so it is refused at the type boundary rather than caught in a
receipt review three weeks later.

---

## 2. HOW IT REPLACES THE FLAT BPS

### 2.1 `CostModel` and `Policy` gain `curve`

`backend/strategy/contract.py::CostModel`:
```python
curve: str = "flat"                    # {"flat", "taq_empirical", "retail_paper"}
flat_bps: float | None = None          # only meaningful when curve == "flat";
                                        # kept so old receipts stay reproducible
```
`transaction_cost_bps`/`slippage_bps` remain the field names used by
`curve="flat"` (no rename — every existing caller and every archived
receipt keys on them); when `curve != "flat"` these two fields are
IGNORED for pricing but still validated non-negative (kept in the
dataclass for the `zero_cost_diagnostic` refusal delegation in §0, which
must keep firing regardless of curve — a `curve="taq_empirical"` book
must still not be constructible with an implicit zero cost).

`backend/services/portfolio_farm/policy.py::Policy` gains the same
`curve` field, `PolicyError` if not in the known set, and
`__post_init__`'s existing `cost <= 0 and not zero_cost_diagnostic`
refusal is extended: under a non-`flat` curve, "cost" for the refusal
check is `resolve_curve(...).round_trip_bps` evaluated once at a
canonical liquid name/date (or the curve's declared floor, e.g. TAQ's
measured minimum) rather than `transaction_cost_bps + slippage_bps` —
because those two fields are unused under a curve, and a curve whose
every measured rate happens to be exactly 0 (the true zero-cost bug this
refusal exists to catch) must still be caught.

### 2.2 `curve` becomes part of `policy_id` / `Strategy.fingerprint`

Both `Policy.policy_id` (SHA-256 over the whole dataclass, `asdict`) and
`Strategy.fingerprint` already hash the WHOLE record, so adding a field
with default `"flat"` automatically:
- changes the hash of nothing that does not set it (default preserved,
  §1.6) — EXCEPT that adding a field to a frozen dataclass changes every
  existing `policy_id` unless the new field is added with the SAME
  default every prior policy implicitly had. Confirm this against
  `test_portfolio_farm_policy.py`'s existing fixed-hash pins before
  merging — if any test pins a literal `policy_id` string, that pin must
  be re-generated ONCE, deliberately, in the same commit, with the reason
  recorded (a hash hidden between commits is the exact "drifted parameter,
  same identity" failure `Policy`'s own docstring warns about).
- makes every curve variant of an otherwise-identical policy its own
  frozen, separately-graduable record — a `curve="taq_empirical"` re-run
  of a promoted `curve="flat"` book is a NEW policy, never a silent
  edit of the promoted one, per "explore dirty, promote clean."

### 2.3 `Policy` applies the curve per fill, not per book

In `replay.py`'s rebalance loop (§0, around `fee = float(notional) *
cost_rate`): when `policy.curve != "flat"`, `cost_rate` is no longer a
scalar computed once outside the loop — it becomes a per-name rate
looked up (or regression-extrapolated, §1.3) for `(ticker, date)` at the
`chosen`/`delta` step, and `fee` is computed per name as `abs(delta[i] *
px[i]) * curve_rate(ticker[i], date, participation[i])` then summed, in
place of the current `notional.sum() * cost_rate`. This is a strictly
LOCAL change to the fee computation inside the existing loop — the
allocatable/cash/shares bookkeeping around it (§0's stuck-capital and
delisting logic) is untouched, because those are turnover-base concerns
and the C2 audit (§0) already establishes that `replay.py`'s turnover
base is correct; only the RATE per fill changes.

Diagnostics gain `mean_realised_cost_bps` (notional-weighted average of
the per-fill rate actually charged, for the receipt) beside the existing
`total_cost_usd`/`traded_notional_usd`, so `total_cost_usd /
traded_notional_usd * 10_000` (derivable today) and the notional-weighted
mean (a distinct, and typically different, number whenever the curve is
non-flat) are BOTH on the receipt — reporting only one invites exactly
the kind of averaging-methodology confusion `taq_calibration.py` already
had to write two full sections about (median-of-daily-medians vs pooled
mean).

### 2.4 Every receipt prints the curve id and the realised cost

Any function that currently emits `transaction_cost_bps_per_side` /
`round_trip_bps` on a row (`CostModel.as_row()`, `Policy.as_row()`,
`FarmResult.as_row()`) additionally prints:
- `cost_curve` (the `curve` field, verbatim — `"flat"`/`"taq_empirical"`/
  `"retail_paper"`),
- `cost_curve_provenance` (`MEASURED_TAQ_EFFECTIVE` /
  `EXTRAPOLATED_REGRESSION` / `DECLARED_CONSERVATIVE` / `MEASURED_
  RETAIL_PAPER` / `"flat_declared"`, per the mix of names actually
  charged that book — a book that is 80% measured and 20% regression-
  fallback prints BOTH counts, mirroring `cost_model.summarise_
  segmentation`'s existing "the split IS the reportable fact" rule),
- `mean_realised_cost_bps` one-way (§2.3), beside the existing
  `gross`/`net` pair — gross and net without the realised rate between
  them is exactly the C2 shape (§0): a level with no way to check what
  produced it.

### 2.5 The re-grading migration script

`scripts/regrade_night_receipts_taq_empirical.py` (name to match the
`scripts/night_*.py` / `scripts/portfolio_farm_*.py` convention already
in use):
1. Enumerates every receipt under `backend/data/optimus/{research_daemon,
   portfolio_farm,arena}/**.json` (and wherever `scripts/night_*.py`
   writes) whose payload contains a "net" field and a flat-bps cost
   assumption (grep `cost_note`/`cost_bps`, reusing the exact audit
   already filed in `docs/HANDOFF_2026-09-10_OPUS_BUILDER_MAP.md` §2.2 —
   do not re-derive that file list from scratch).
2. For each, RE-RUNS the same policy/strategy with `curve="taq_empirical"`
   substituted for `curve="flat"` and everything else byte-identical
   (same universe, same dates, same signal) — never edits the archived
   receipt in place (append-only; `docs/TRACK_RECORD_POLICY.md`-shaped
   discipline extended to research receipts).
3. Writes a NEW receipt, `<original_name>.regraded_taq_empirical.json`,
   containing: the original net, the re-graded net, the delta in
   percentage points, the delta in RANK (if the receipt was part of a
   leaderboard, does this policy's rank among its peers change — expected
   answer per the roadmap line: "the ranking of nothing may change and
   the LEVEL of everything will"), and `mean_realised_cost_bps` for both
   runs side by side.
4. Refuses (does not silently skip) any receipt whose flat-cost
   assumption cannot be identified from its own payload (no `cost_note`/
   `transaction_cost_bps` field) — same "a check that did not run is not
   a check that passed" discipline as everywhere else in this repo.
5. Produces one summary table: `n_receipts_regraded`,
   `n_rank_changed`, `median_level_delta_pp`, `n_refused_unidentifiable`.

---

## 3. THE VALIDATION

### 3.1 Predicted vs measured half-spread, on the 4,224 measured name-days

Split the 184 TAQ names into liquidity terciles by trailing dollar
volume (reuse the band cuts from `taq_spread_by_liquidity_band.py` or a
fresh tercile cut — either is fine as long as it is DECLARED before
computing the error, not chosen after seeing which cut flatters the fit).
For each tercile: MAE and median absolute error of
`half_effective_spread_bps` predicted by the §1.3 regression (fit
LEAVE-ONE-OUT or on a held-out half of the 184 names — fitting and
validating on the same 184 rows and calling it "validated" is exactly
the in-sample mistake `Policy`'s own docstring calls out) vs the actual
`taq_effective_spreads_v1.jsonl` measurement. Report the same table
shape `TAQ_COST_CALIBRATION.md` already uses (per-tercile MAE, worst
name, best name) so a reader familiar with that doc recognises the
format.

**Expected shape, stated before running it (falsifiable):** MAE should be
worst in the illiquid tercile (fewer names to fit against, tick-floor
quantisation biases the regression's target variable itself — §1.3) and
best in the liquid tercile — if the reverse holds, the regression is
fitting noise in dollar-volume rather than the liquidity relationship,
and that is itself a finding to report, not a result to suppress.

### 3.2 Sensitivity of the top night result's DSR to curve choice

Using `backend.strategy.multipletesting.deflated_sharpe_ratio` (already
in the repo — do not reimplement), take the current best-Sharpe night
receipt (whatever `docs/HANDOFF_2026-09-10...md` or the latest arena
leaderboard names as the top result at spec-implementation time) and
report its DSR under: `curve="flat"` at the receipt's original
assumption, `curve="flat"` at the C2-style over-charge (25bp × full
notional, as a worst-case sanity floor), `curve="taq_empirical"`. Three
numbers on one row. This is the sensitivity the roadmap line demands
("the ranking of nothing may change and the LEVEL of everything will") —
stated as a measurement, not assumed: if the DSR ORDERING across the
leaderboard changes under `taq_empirical` for even one pair, that
contradicts the roadmap's own prediction and must be reported as
correcting it, not quietly matched to it.

### 3.3 What the curve cannot know (stated, not hidden)

- **Fills.** TAQ's effective spread is what OTHER trades reportedly
  paid; it says nothing about whether Aegis's own hypothetical order
  would have been filled at that price, partially filled, or filled
  worse under queue position it does not model. The retail curve's D2
  dependency (§1.5) is the only piece of this program that measures
  actual fills, and it does not exist yet.
- **Adverse selection at the open.** The TAQ panel is explicitly
  09:45-15:45 (`taq_calibration.py`'s bias ledger, UNDER-states bias #2)
  — the open and close, the two most expensive and most information-
  laden windows, are structurally absent from both the quoted and
  effective panels. Any book that trades at or near the open (Lane D,
  `tif=opg` already shown unreliable on paper) is using a curve
  calibrated on a DIFFERENT, calmer part of the session, and the receipt
  must say so rather than implying open-auction costs are covered.
- **The 2020 March regime.** The panel is 23 days in 2026 (a single,
  calm-vol regime). Spread widens mechanically in stress (the vendored
  `sqrt_impact`'s `volatility` term partially captures this for the
  impact leg, but §1.2's measured spread term does not — it is a fixed
  historical read, not a live one). A book run through a volatility
  regime the panel never saw is extrapolating the spread term outside
  its measured domain in the SAME way `taq_calibration.apply_calibration`
  already refuses to do for the AGK/TAQ ratio — this curve does not yet
  have an equivalent refusal for a regime shift, and that absence is
  itself worth naming rather than silently inheriting.

---

## 4. TESTS WITH KNOWN ANSWERS

Mirror the style of `backend/tests/test_taq_calibration.py` and
`backend/tests/test_portfolio_farm_policy.py` (fixed panels, exact
arithmetic asserted, refusals asserted by `pytest.raises`) -- no
network, no live data, per the fast-suite discipline in `CLAUDE.md`.

1. **A name with measured half-spread 1.0bp and 0.5% participation
   yields the documented total.** Construct a tiny synthetic
   `taq_effective_spreads_v1`-shaped fixture where
   `effective_full_bps_median = 2.0` for one ticker/date (half-spread
   1.0bp). Call the curve with `participation=0.005` and a declared
   `volatility_ann` (e.g. 0.30, stated in the test). Assert
   `one_way_bps == 1.0 + eta * 0.30 * sqrt(0.005)` to float tolerance,
   with `eta` the frozen calibrated constant from S1.4 -- the test PINS
   `eta`'s value, so a future re-calibration is a deliberate, reviewed
   change to a named test, not a silent drift.
2. **A name with no TAQ row falls back to the regression and says so.**
   A ticker absent from the fixture panel, with dollar-volume/price/
   volatility inputs supplied: assert the returned cost object's
   provenance is `EXTRAPOLATED_REGRESSION` (never `MEASURED_TAQ_
   EFFECTIVE`), and assert the regression's OWN R2/CI metadata travels
   on the object (mirrors `TaqReading.notes` carrying context on the
   quoted panel).
3. **A name with no TAQ row AND missing a regression input falls back to
   the declared band, and says so.** No volatility supplied (or fewer
   than the regression's minimum history): assert the return is a
   `CostBand` with `provenance == DECLARED_CONSERVATIVE`, NOT a silent
   population-mean guess (asserted by checking the returned value is a
   `CostBand`, which per S0/`cost_model.py` has no `.value`/`__float__`
   -- a test that could call `float()` on the result and get a number
   would itself prove the refusal had been defeated).
4. **Zero cost still refuses under every curve.** Parametrize
   `test_zero_cost_diagnostic_required` (extending the existing
   `test_portfolio_farm_policy.py` case, if one exists, else adding it)
   over `curve in {"flat", "taq_empirical", "retail_paper"}`: constructing
   a `Policy`/`CostModel` whose EFFECTIVE cost resolves to 0 for the
   given curve without `zero_cost_diagnostic=True` raises `PolicyError`/
   `StrategyError` in all three cases -- this is the test that would have
   caught a curve whose regression accidentally floors at exactly 0 for
   some input.
5. **An old receipt re-graded under `flat` reproduces its number to the
   cent.** Feed the migration script (S2.5) a real archived receipt (or a
   frozen fixture copy of one) with `curve="flat"` explicitly declared,
   run it through `regrade_night_receipts_taq_empirical.py`'s SAME
   pipeline but with the target curve set back to `"flat"` (a no-op
   re-grade): assert the re-graded net equals the archived net to
   floating-point tolerance ($0.01 on a $10,000 book, i.e. relative
   tolerance ~1e-6) -- this is the regression test that proves the new
   code path is a superset of the old one, not a rewrite that happens to
   agree by construction.
6. **`curve` is part of `policy_id`.** Two `Policy` instances identical
   in every field except `curve` produce DIFFERENT `policy_id`s -- the
   direct test of S2.2's fingerprint claim, and the one that would catch
   a `curve` field accidentally excluded from the hash (e.g. added after
   `asdict()` rather than as a dataclass field).

---

## 5. WHERE EACH PIECE LIVES, AND WHICH CHUNK

| piece | module / script | receipt path |
|---|---|---|
| Effective-spread reader (S1.2), mirrors `taq_calibration.reading_for` | NEW: `backend/services/taq_effective_calibration.py` (parallel to, imports types from, `taq_calibration.py`/`cost_model.py`; does not edit either) | reads `backend/data/optimus/taq_effective_spreads_v1.jsonl` |
| `MEASURED_TAQ_EFFECTIVE` provenance constant | `backend/services/cost_model.py` (add beside `MEASURED_TAQ`/`MEASURED_TAQ_QUOTED`, S1.2) | -- |
| Extrapolation regression (S1.3) | NEW: `backend/services/spread_extrapolation.py`, or a function in `taq_effective_calibration.py` if small enough to avoid a fourth module | fitted coefficients + R2/CI written to `backend/data/optimus/taq_spread_regression_v1.json` |
| Impact term (S1.4) | call-site only -- `backend.strategy.vendor.impact.sqrt_impact`, UNCHANGED (byte-pinned); the `eta` calibration constant lives in the new `taq_effective_calibration.py`, not in the vendor file | the `eta` solve's working (target bps at 1% ADV, spread subtracted) written to the same regression receipt above, as its own section |
| Retail curve stub (S1.5) | NEW: `backend/services/retail_cost_curve.py`, refuses until D2 lands | reads `backend/data/optimus/fill_quality/*.jsonl` once chunk 5b writes it |
| `curve` field | `backend/strategy/contract.py::CostModel`, `backend/services/portfolio_farm/policy.py::Policy` | -- |
| Per-fill application (S2.3) | `backend/services/portfolio_farm/replay.py` (the `cost_rate`/`fee` computation, ~line 220-330) | diagnostics gain `mean_realised_cost_bps` |
| Receipt fields (S2.4) | `CostModel.as_row()`, `Policy.as_row()`, `FarmResult.as_row()` | every existing receipt path gains `cost_curve`/`cost_curve_provenance`/`mean_realised_cost_bps` |
| Migration/re-grade script (S2.5) | NEW: `scripts/regrade_night_receipts_taq_empirical.py` | writes `<original>.regraded_taq_empirical.json` beside each source receipt |
| Validation (S3) | NEW: `scripts/validate_taq_cost_curve.py` (one script, both S3.1 and S3.2, since they share the fitted curve object) | `backend/data/optimus/taq_cost_curve_validation.json` |
| Tests (S4) | `backend/tests/test_taq_effective_calibration.py`, `backend/tests/test_spread_extrapolation.py`, additions to `backend/tests/test_portfolio_farm_policy.py` and `backend/tests/test_cost_model.py` (if that file exists; else `test_strategy_contract.py`) | -- |

### Which chunk builds it

The roadmap's own idea-to-chunk mapping (`ROADMAP_2026-09-11...md` S11c
closing line) places idea #1 "in chunk 4 (data)" -- but chunk 4's actual
task table (S12) lists only the news-corpus items (N-A/B/C/D) with no
cost-model line item, so that placement is a first-pass label, not a
scoped task. This spec recommends **a new small chunk `5c`**, immediately
after `5b` (Lane D: D1-D2, the fill-quality receipt), rather than folding
it into chunk 4 or waiting for chunk 7:

- **The institutional half (S1.1-1.4, S2, most of S3, S4 items 1-3,5-6)
  needs nothing chunk 4 or 5b produce** -- the 4,224-row panel, `taq_
  calibration.py`, `cost_model.py`, `sqrt_impact`, and the CRSP columns
  for the regression all already exist on disk today. It could start
  immediately, in parallel with chunk 4/5/5b, with no dependency.
  Blocking it behind chunk 4's unrelated news-corpus work costs weeks
  for no reason.
- **The retail half (S1.5, test item 2's stub-refusal case) genuinely
  depends on 5b's D2 receipt landing first** -- this is the one piece
  that must wait, and waiting for it is a real dependency, not a
  scheduling convenience, per "gates outrank dates."
- **Chunk 7** (X1-X4, L3 Lookahead-Propensity, the anonymisation gap) is
  about LLM-in-backtest hygiene, a different axis entirely; putting a
  cost-curve spec there would bury it in an unrelated review.

So: **`5c` = S1.1-1.4 + S2 (the institutional curve, wired into `Policy`/
`CostModel`, migration script run once) + S3.1/S4 (the parts that need no
new data) -- gated only on chunk 4/5/5b's completion for CI ordering, not
on their content** -- followed by a small, separately-committable
addendum once 5b's D2 receipt exists, finishing S1.5 and test item 2's
stub-to-real transition. The gate to the next chunk (per the roadmap's
own table format): *every night receipt that says "net" has been
re-graded once under `taq_empirical`, and the re-grade's rank-change
count is on record -- not that the re-grade agrees with the flat number,
since S3.2 is explicit that it may not.*
