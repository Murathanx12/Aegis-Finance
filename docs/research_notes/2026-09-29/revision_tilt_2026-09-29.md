# Revision flow as a tilt on a top-500 base, on CRSP 1999-2024 (2026-09-29)

Licence `PRODUCT_EXPERIMENT`. $0.00, no LLM, no network, no broker call. No book, ledger row or earlier
receipt was changed. **Nothing was registered: the pre-chosen configuration failed the decision rule
declared before the validation run.** Every number below is in a receipt under
`backend/data/optimus/crsp_rebuild/`, run tag `RT_2026-09-29T1110Z`:

- declaration `revision_tilt_DECLARATION_RT_2026-09-29T1110Z.json`, hash **`0f0939b893b2754e`**, written
  before the design run
- design `revision_tilt_DESIGN_RT_2026-09-29T1110Z.json`: 18 variants on design dates only; the choice,
  selection hash **`30bfc46e287bcc83`**
- validation `revision_tilt_VALIDATE_RT_2026-09-29T1110Z.json`: the one chosen configuration, 1999-2024,
  cap base plus the equal-weight sensitivity
- monthly series `revision_tilt_series_RT_2026-09-29T1110Z_{cap,equal}.parquet`
- inputs `revision_tilt_inputs_RT_2026-09-29T1110Z.parquet`

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** A negative result, with evidence.

- **Verdict: FAILED_VARIANT.** In validation (2009-2016), the pre-chosen tilt returned **-0.038%/mo**
  against the market net of costs, at t -0.60 and MDE 0.18%/mo. It was positive in 4 of 8 years.
- **The tilt adds nothing measurable on a large-cap base.** Against its own untilted base it returned
  -0.002%/mo in validation (t -0.2, MDE 0.032) and -0.002%/mo in 2017-2024.
  - The design window showed +0.024%/mo (t 2.02). That is the most a 5% active share can carry.
- **The whole gap to the market is the base.** The top-500 cap-weighted base trails the CRSP
  value-weighted market by -0.124%/mo in design (t -2.09) and -0.035%/mo in validation, with 2.9-3.3%/yr
  tracking error. The tilt moves that number by less than its own noise.

| item | value |
|---|---|
| best historical net strategy vs the market | unchanged. This tilt is not one: -0.038%/mo in 2009-2016, t -0.60. |
| best forward paper strategy | unchanged; nothing matures before 2026-10-26. |
| independent selector count | unchanged. |
| farm candidates tested / promoted | 18 design variants plus 1 validation run; 0 promoted, 0 registered. |
| deflation count | **42,397** = 42,378 before + 18 design cells + 1 validation cell. The validation DSR is 0.00 against the market and against the base (z -4.6 / -4.4). |
| new actionable finding | Inside the 500 most liquid names, analyst revision flow is too weak to pay at any tilt small enough to stay inside a 15%/mo turnover budget. The relative edge measured against the twin lives in the book's name selection and turnover, not in a low-turnover large-cap overlay. |
| external execution drag | not measured |
| LLM spend | $0.00 |

## 1. What was declared before any run

Everything below is in the declaration receipt, hashed. The design and validate parts both refuse to run
if the hash in the file differs from the one the code produces.

**Split, keyed on the hold month:**

| window | hold months | role |
|---|---|---|
| design | 1999-10 to 2008-12 | the choice is made here |
| validate | 2009-01 to 2016-12 | read once |
| 2017-2024 | 2017-01 to 2024-12 | read last; NOT a clean holdout, because the library's rules were written on the 2016-2026 vendor calendar |

Revision flow starts at the decision date 1999-09-30, the bridge's declared start for this source. The
design run only ever simulates decisions whose hold month ends by 2008-12, so it never saw a validation
return.

**Fixed choices:**

- **Base.** The top 500 eligible names by trailing median daily dollar volume at each month end, ranked
  rather than cut at a dollar floor.
  - **Primary weighting:** cap weight (|price| x shares outstanding, from CRSP daily).
  - **Sensitivity:** equal weight.
- **Tilt.** Cross-sectional ranks of the signal, mapped to [-1, 1] and de-meaned within the PIT `gsector`,
  scaled by bisection to a target active share.
  - Every active weight is capped at **+/-0.5%**, and underweights stop at the base weight (long only).
  - Each sector's active sum is balanced to zero.
  - A name with no revision data gets no active weight.
- **No-trade band** on each name's active weight, then a **monthly active-turnover budget of 15%**,
  applied as a partial step toward the target.
- **Costs.**
  - **Primary:** per name per month, the larger of the Corwin-Schultz round-trip spread (capped at 20%)
    and the engine's flat band schedule (6/10/18/35 bps). The flat band applies where Corwin-Schultz is
    missing.
  - Costs are charged as |trade| x spread / 2 on the ACTUAL traded weight, for book and base alike.
  - **Sensitivity:** flat band only.
  - The market leg (FF mktrf + rf, compounded over each hold period) is costless.

**Design grid (18 cells):**

- signal: `net_raises`, `breadth` (net raises / distinct brokers), `ear_flow` (rank-average of the
  announcement return and net raises)
- active share: 10%, 20%, 30%
- band: 0.05%, 0.10%

**Selection rule.** Choose the highest design-window t (3-month blocks) of book net minus base net under
primary costs. On a tie, choose the smaller active share.

**Decision rule.** CANDIDATE iff validation book net minus market has mean > 0, t >= 2, and is positive in
at least 5 of 8 hold years. Otherwise CANNOT_DISTINGUISH if the mean is > 0, or FAILED_VARIANT if it is
<= 0. Register a forward shadow only on CANDIDATE.

**Honesty note on what was already known.** The earlier note had already printed validation-window numbers
for `net_raises` and `ear_flow` as stand-alone books against their twin. The signal family was therefore
not chosen blind to 2009-2016. The construction (base, caps, band, budget) and this grid were not tuned on
validation.

## 2. Design (1999-2008): the choice

The table shows active return against the base, net of primary costs, in %/mo.

| variant | active vs base | t | active turnover/mo | realised active share |
|---|---:|---:|---:|---:|
| **net_raises_as10_b10 (chosen)** | **+0.024** | **+2.02** | 1.3% | 5.1% |
| ear_flow_as10_b10 | +0.020 | +2.00 | 1.5% | 5.3% |
| breadth_as10_b10 | +0.025 | +1.75 | 1.6% | 5.9% |
| net_raises_as10_b5 | +0.022 | +1.02 | 3.6% | 9.1% |
| net_raises_as20_b10 | +0.035 | +0.96 | 6.8% | 18.3% |
| ... 13 more | -0.037 to +0.022 | -0.60 to +0.83 | | |
| net_raises_as30_b10 | -0.002 | -0.04 | 11.6% | 27.0% |

**What the design already said.**

- Larger tilts did not earn more. The 20-30% active-share variants are at about zero.
- The selection rule favoured the smallest, quietest tilt. The 0.10% band blocked most of the small
  moves, so the chosen cell realised only a **5% active share** against a 10% target.
- That is a legitimate declared choice. It also means the chosen cell can carry at most a few basis points
  a month. The earlier note's +0.27%/mo gap against the twin comes from a concentrated, high-turnover book.
  Scaled to a 5% active share in large caps, it would be about 0.03%/mo, and that is what design shows.

## 3. Validation (2009-2016), the one pre-chosen configuration

Configuration: `net_raises`, active share 10%, band 0.10%, cap +/-0.5%, budget 15%, sector-neutral,
cap-weighted top 500. Values are %/mo, keyed on the hold month, with t on 3-month blocks.

| series | design 1999-2008 | **validate 2009-2016** | 2017-2024 (not clean) |
|---|---|---|---|
| **book net - market** (decision) | -0.100 (t -1.71) | **-0.038 (t -0.60, MDE 0.18)** | +0.080 (t 1.02) |
| book net - base net (the tilt) | +0.024 (t 2.02) | -0.002 (t -0.20, MDE 0.032) | -0.002 (t -0.30) |
| base net - market | -0.124 (t -2.09) | -0.035 (t -0.58) | +0.082 (t 1.09) |
| base gross - market | -0.111 | -0.028 | +0.089 |
| book net - market, flat costs | -0.089 | -0.031 (t -0.50) | +0.087 |
| information ratio vs market (annual) | -0.43 | **-0.13** | +0.32 |
| information ratio vs base (annual) | +0.62 | -0.07 | -0.09 |
| tracking error vs market / vs base (annual) | 2.80% / 0.47% | 3.38% / 0.36% | 3.02% / 0.29% |
| max drawdown, active vs market | -14.7% | -6.5% | -3.2% |
| max drawdown, tilt vs base | -0.58% | -1.23% | -0.75% |
| years positive vs market | 3 of 10 | **4 of 8** | 6 of 8 |
| leave-one-year-out worst vs market | -0.126 (drop 2007) | -0.066 (drop 2014) | +0.036 (drop 2024) |
| turnover/mo: book / base / tilt | 1.7% / 1.6% / 1.3% | 1.3% / 1.2% / 1.1% | 1.3% / 1.0% / 1.1% |
| cost/mo: book / base (bps) | 1.31 / 1.30 | 0.80 / 0.76 | 0.80 / 0.67 |

**Validation by hold year**, as the yearly sum of monthly differences in %:

| | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| book - market | **-1.30** | -1.94 | +1.25 | +0.35 | -3.48 | +1.89 | -1.10 | +0.71 |
| book - base (tilt) | **-0.90** | -0.02 | +0.36 | -0.03 | +0.02 | +0.22 | +0.27 | -0.13 |

**2009, shown explicitly.** The tilt lost -0.90% against its base in the junk rally, and the book lost
-1.30% against the market. The base alone lost -0.41%. That is the shape expected of a revision-momentum
tilt in a momentum crash. Without 2009 the tilt's validation mean is about +0.01%/mo, still far inside its
0.032 MDE.

**Deflated Sharpe on validation, at n = 42,397:** 0.00 against the market (z -4.57) and 0.00 against the
base (z -4.43). The plain single-configuration statistic, which is the number that matters, is t -0.60.

**Capacity is not the constraint.** Participation is measured as |trade| x AUM / median daily dollar
volume, over hold months 2009-2024:

| AUM | median participation | p99 | max | trades over 1% ADV |
|---|---:|---:|---:|---:|
| $1M | 0.000005% | 0.0016% | 0.0045% | 0 |
| $100M | 0.0005% | 0.16% | 0.45% | 0 |

**Data counts.** Revision data covers 99.9% of base names. 980 held name-months over 25 years had no
forward return and were booked at 0. Book and base carry them alike.

### Sensitivity: equal-weighted top 500 (not the decision)

| series | design | validate | 2017-2024 |
|---|---|---|---|
| book net - market | +0.072 (t 0.33) | +0.091 (t 0.72, MDE 0.36) | -0.020 (t -0.10) |
| book net - base net (tilt) | +0.118 (t 1.90) | -0.010 (t -0.29) | +0.052 (t 1.63) |
| base net - market | -0.046 | +0.101 | -0.072 |
| tracking error vs market (annual) | 9.1% | 4.6% | 6.2% |

- On the equal-weight base the tilt carries a 9-10% active share and about 2.6% active turnover a month.
- It is again positive in design, flat in validation, and positive (not clean) in 2017-2024.
- The equal-weight book's positive validation number against the market is the base's size tilt
  (+0.101), not the signal.

## 4. Verdict

- **The tilt as specified is FAILED_VARIANT.** Under the rule declared before the run, validation book net
  minus market is -0.038%/mo, below zero.
- **The mechanism is not rejected.** It is **DEPRIORITIZED as a large-cap overlay**. This closes "revision
  flow as a low-turnover tilt on the 500 most liquid names". It does not close revision flow in the
  mid-cap names where the earlier book found its twin gap, and it does not close the signal combined with
  something else.
- **Why it failed.** A +/-0.5% cap, a long-only base and a 15% turnover budget together leave about 5-10%
  of active share. In the top 500, the signal's per-name edge times that active share is a few basis
  points a month (design +0.024, equal weight +0.12). That is below the MDE of eight years of data (0.03 to
  0.10), and it went to zero or negative in 2009-2016.
- **No registration.** No forward shadow was registered and no contract hash exists. For reference only:
  the tilt's validation sd is 0.10%/mo. A six-month kill line at -1.645 sd would sit at -0.41% cumulative,
  with a 5% false-kill rate. It would reach 50% power only against a true gap of -0.07%/mo. So even a
  registered shadow could not have told an edge from zero in 2026.

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS.**

- **The declared pipeline.**
  - The declaration hash is checked by both later parts.
  - The design never simulates a validation month.
  - One choice was run once, and the verdict falls out of a rule written before the data.
  - The tilt construction is pinned by 14 offline tests: weights sum to one, |active| <= cap, sector sums
    zero, turnover budget, forced exit outside the base, and scrambling future returns leaves earlier
    weights unchanged.
- **A market-like base is cheap to hold.** The cap-weighted top 500 turns over 1.2-1.6% a month at under
  1 bp/mo of spread cost, with 3% tracking error. It is a usable chassis for any future overlay.
- **Revision flow keeps its sign in design on every base.** It is +0.02 on the cap base (t 2.0) and +0.12
  on the equal-weight base (t 1.9).

**WHAT DOES NOT.**

- **Revision flow as a low-turnover large-cap tilt.**
  - Validation: -0.002%/mo on the base, -0.038 against the market.
  - Its per-name edge in the 500 most liquid names is too small to show at any tilt that respects the
    caps and the budget.
  - Bigger tilts (20-30% active share) were already about zero in design.
- **Reading "beats the twin" as "can tilt the index".** The twin gap came from a concentrated,
  high-turnover book that reaches into $30-200M/day names. At 5% active share in mega and large caps, the
  same signal is a rounding error.
- **2009.** A revision-momentum tilt loses in a junk rally. The tilt's worst year is the one the brief
  asked to see.

**HIGHEST-EV EXPERIMENT.** Move the base, not the tilt. Run the same declared pipeline on **ranks 501-1500
by dollar volume**, the names where `net_raises` found its twin gap. Use an equal-weight base, since no
cap-weighted index tracks there, and benchmark against both the market and that base.

- **The gate.** Write the declaration first, using this pipeline's `--part declare`. Use the same 18-cell
  grid, with the cap raised to +/-1% because names there carry about 0.1% base weight.
- **Cost and odds.** About 1 hour, $0.
- **P(changes the roadmap).** Low to moderate. The mid-cap tilt must beat realistic mid-cap spreads, where
  the earlier stand-alone book lost.
- **Why it ranks first.** It is the only place left where this signal's measured relative edge could be
  large enough per name to survive the construction that stops the twin drag.
- **Cheaper alternative (about 1 hour).** Build the lead/chase and first-mover bridge columns, as the
  previous note proposed. That is 12 unrun rules.

## CONTINUE FROM HERE

Nothing is committed (brief). Reproduce, about 40 seconds in total once the inputs exist:

```bash
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_revision_tilt.py -q     # 14 tests
python -m scripts.revision_tilt_on_crsp --part inputs   --tag <new tag>   # ~10 s
python -m scripts.revision_tilt_on_crsp --part declare  --tag <new tag>
python -m scripts.revision_tilt_on_crsp --part design   --tag <new tag>   # 18 cells, ~20 s
python -m scripts.revision_tilt_on_crsp --part validate --tag <new tag>   # one config, cap + equal
```

Every part refuses to overwrite a receipt. A new experiment (for example the mid-cap base) needs new grid or
base constants in the script, and therefore a new declaration hash and a new tag.

Files to commit together:

- `backend/services/revision_tilt.py`
- `scripts/revision_tilt_on_crsp.py`
- `backend/tests/test_revision_tilt.py`
- this note
- the three `revision_tilt_*_RT_2026-09-29T1110Z.json` receipts

The parquet files stay local. `revision_tilt` is reached through the script, and `test_signal_reachability`
passes (9/9) with no classification edit.


---

## 2026-09-29 (evening): the same pipeline on ranks 501-1500

Licence `PRODUCT_EXPERIMENT`. $0, no LLM, no network. No book, ledger row or earlier receipt was touched.
This runs the HIGHEST-EV step above: the base moves, and the tilt construction stays the same.

### RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.**

- The one validation number, for book net of primary costs minus the market over 2009-2016 (hold
  month): **+0.11%/mo, t 0.54, 4 of 8 years positive.**
- **Verdict: CANNOT_DISTINGUISH.** The mean is positive, but t is below 2 and the positive years are
  not a majority. **No forward shadow is registered.**
- In validation the tilt adds nothing over its own base: book minus base is **-0.016%/mo** (t -0.26).
  Everything the book earns against the market, the untilted equal-weight mid-cap base also earns
  (+0.13%/mo, t 0.54).

### What was declared, and how

- **Code.** `backend/services/revision_tilt.base_weights` has a new optional `rank_lo`. Its default
  (0) gives the old top-`n` base exactly. A test compares the new function against the old body
  verbatim for both schemes and three sizes.
- **Profile.** `scripts/revision_tilt_on_crsp.py --profile mid501_1500` covers ranks 501-1500 by
  trailing median dollar volume. It uses:
  - an equal-weight base, which is primary (cap weighting is the sensitivity run);
  - an active cap of +/-1% per name;
  - the same 18-cell grid, turnover budget, sector neutrality, costs, selection rule and decision
    rule.
- **Protecting the old receipts.** The default profile `top500` reproduces the original declaration
  hash `0f0939b893b2754e` (pinned by test), so the earlier receipts still validate.
- **Inputs.** They are reused from `revision_tilt_inputs_RT_2026-09-29T1110Z.parquet`: the same
  panel, fund, bridge and CS runs, holding every eligible name.
- **Declaration.** `crsp_rebuild/revision_tilt_DECLARATION_RTMID_2026-09-29T1125Z.json` was written
  before the design run.
  - Its hash is `35f520cd56bbbe89`.
  - The tag's time is a label only: the file was written at 11:13Z.
- **Design.** `revision_tilt_DESIGN_RTMID_2026-09-29T1125Z.json` covers 18 cells with hold months
  from 1999-10 to 2008-12.
  - Every cell's tilt minus base was positive, at t 1.1-1.75.
  - Chosen: **`ear_flow_as20_b10`**, which had the highest design t (1.75, +0.14%/mo). Selection hash
    `86a0cf6a53e445a8`.
- **Validation.** `revision_tilt_VALIDATE_RTMID_2026-09-29T1125Z.json` ran once, on 2009-2016.
- **Search count.** 42,397 before this experiment, plus 18 design cells and 1 validation, gives
  **42,416**. The validation DSR at that count is 0.0001.

### Numbers: equal-weight base, primary costs, %/mo (t on 3-month blocks)

| series | design 1999-2008 | **validate 2009-2016** | 2017-2024 (not a clean holdout) |
|---|---|---|---|
| book net - market | +0.37 (1.96) | **+0.11 (0.54), 4 of 8 yrs** | -0.21 (-0.62), 2 of 8 |
| book net - base net | +0.14 (1.75) | -0.02 (-0.26), 4 of 8 | +0.09 (1.93), 5 of 8 |
| base net - market | +0.23 (0.98) | +0.13 (0.54) | -0.30 (-0.82) |
| book gross - base gross | +0.10 (1.30) | -0.04 (-0.62) | +0.06 (1.31) |

Other validation-window numbers:

- **Flat costs only:** book - market +0.15 (t 0.73); book - base -0.03.
- **Cap-weighted sensitivity:** book - market +0.17 (t 1.07, 6 of 8 years); book - base -0.006.
- **2009:** book - base -6.4%. The tilt loses in the junk rally again, and it is its worst year.
- **Turnover:** book 6.1% a month, active 4%. Active share is 17%, and the largest active weight is
  0.18%.
- **Costs:** 5.6 bp a month on the book and 8.0 bp on the base.
- **Signal coverage in the base:** 99.7%.
- **Capacity:** at $100M, 6.7% of trades exceed 1% of ADV. Capacity is not the constraint.

### What it says

- **The mid-cap base does not rescue the tilt.** Its design sign was positive in every cell, as it was
  on the top-500 base, and the validation sign is not.
  - The per-name edge `net_raises` showed against a concentrated twin does not survive a construction
    that caps active risk. That holds in mid caps as it did in large caps.
  - The late window's +0.09 (t 1.93) comes after validation failed and is labelled NOT a clean
    holdout. It does not reverse the verdict, and it is not a new lead unless a fresh, declared window
    confirms it.
- **What the book earns against the market is the base's.** An equal-weight mid-cap basket beat the
  market by about 0.1-0.2%/mo over 1999-2016 and lost 0.3%/mo in 2017-2024. That is a size tilt, not
  revision flow.
- **The decision rule stands, so nothing is registered.** Revision flow as a capped tilt is now
  **CANNOT_DISTINGUISH on both bases**. It is DEPRIORITIZED as a tilt.

### Reproduce

```bash
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_revision_tilt.py -q   # 24 tests
python -m scripts.revision_tilt_on_crsp --part design   --profile mid501_1500 --tag <new tag>   # after --part declare
python -m scripts.revision_tilt_on_crsp --part validate --profile mid501_1500 --tag <new tag>
```

The three new `revision_tilt_*_RTMID_2026-09-29T1125Z.json` receipts should be committed with this note
and the code. The series parquets stay local.
