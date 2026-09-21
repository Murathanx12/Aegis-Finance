# Sequential evidence, contextual bandits, VOI, and forecast-error correlation — for 23c/23e/24

Read: roadmap §16 (16.3 rows 22c, 23a, 23c-f, 24; 16.4 item 3); Part 2 of the
2026-09-21 morning feedback (items 2, 5, 7, 8, 12); `decision_authority.py`
(`posterior_read`, `_uncertainty_bonus`, `seed_for`, `assign`),
`decision_ledger.py` (states `DECIDED → DELIVERED → SEEN_BY_EXECUTOR →
REFUSED | ORDER_SUBMITTED → REVISED → FILLED → SCORED`, monotone-in-rank not
strict-predecessor), `forecast_grader.py` (`score_due` joins a row's own
expiry to close-to-close return), `signal_calibration.py` (`CalibratedRead`:
verdict CALIBRATED/WEAK/INVERTED/NO_PANEL/REFUSED, `mu_pct`/`se_pct` from a
block-bootstrap CI over `n_date_blocks`, Holm on the family). No `PROBE`
authority, `PROBE_MIN_GRADED`, or selection-probability field exist yet — 23a
is a clean addition. `brain_query` on e-values/Thompson-VW/online-FDR returned
only our own prior specs (chunk 13 allocator note, R4 online-belief survey) —
no external corpus on these methods is ingested; this note cites literature
directly. Standing rules: §63 (SCREEN=BH-FDR/m=tests run, EXPORT=Holm/m=
declared budget), §58 (`n_effective` counts DATE BLOCKS, not rows;
`k/(1+(k-1)ρ̄)`).

## 1. Sequential evidence on dependent, heavy-tailed, overlapping returns

**What exists:** e-values/e-processes (Vovk & Wang 2021; Ramdas, Ruf, Larsson,
Koolen — "game-theoretic statistics"); confidence sequences (Howard, Ramdas,
McAuliffe, Sekhon, *Annals of Statistics* 2021 — time-uniform boundaries from
sub-ψ tail bounds); betting-based tests (Shafer & Vovk's test martingales;
Waudby-Smith & Ramdas 2024 JRSS-B — bet on bounded/sub-Gaussian means via
online gradient/mixture bettors, invert into a confidence sequence for free);
online FDR (Foster & Stine alpha-investing; Javanmard & Montanari LORD;
Ramdas et al SAFFRON, ADDIS — spend and earn "alpha wealth" across a stream of
tests instead of one fixed Holm family). **Licence:** all of this is
statistical method, not code with a licence — the reference implementation
(`confseq` R/Python, Ramdas group) is BSD/MIT-class; nothing here needs a
dependency.

**What breaks under our data:** the core validity claim — E[e-value |
past] ≤ 1 under the null, hence the running product is a supermartingale — 
holds under *arbitrary* dependence, which is the whole appeal for a
non-i.i.d., autocorrelated return series. What breaks is not the martingale
property but the **unit of "one more look."** Our ledger rows overlap: a
21-day-horizon row opened Monday and one opened Tuesday share 20 trading days
of realized path, so their two e-values are not independent evidence even
though the martingale math tolerates the dependence — treating each row as
one bet against the same running product silently *inflates the effective
sample size*, the return-panel version of the §58 defect ("n_effective counts
DATE BLOCKS, never rows"). Standard online-FDR (LORD/SAFFRON) is worse here:
its FDR guarantee assumes independent or PRDS p-values across the *hypothesis*
stream, and overlapping horizons break PRDS the same way. **The fix, twice:**
(a) one e-value per DATE BLOCK, not per row — collapse every row whose horizon
window touches a given block into one bet before multiplying across blocks,
exactly the block-bootstrap unit `signal_calibration` already uses
(`n_date_blocks`); (b) for cross-hypothesis multiplicity, use **e-BH**
(Wang & Ramdas 2022), which controls FDR under *arbitrary* dependence between
e-values — the one place e-values are strictly easier to compose correctly
than p-values, so it is the natural online-FDR replacement here rather than
LORD/SAFFRON as published. A mixture martingale (bet with a prior over effect
sizes, e.g. a Gaussian or GRO mixture, rather than one fixed alternative)
avoids pre-committing to an effect size chunk 22's own WEAK/CALIBRATED reads
already vary by decile and horizon.

**Refuse:** treating the confidence sequence as a replacement for Holm/BH on
a `RESEARCH_CLAIM` — §63 stands, sequential evidence is for *monitoring*
ongoing PROBE/EXPLORE research, never for an exported claim. Refuse per-row
e-values as the unit; refuse LORD/SAFFRON's FDR guarantee as stated (not
proven under our overlap) — use e-BH instead if cross-hypothesis multiplicity
matters at PROBE/EXPLORE stage at all (it may not: 16.1's `BELIEF_CHANGED`
already requires printing the number, not a corrected p-value).

**First $0 test:** a per-`hypothesis_id` e-process over `decisions/
ledger.jsonl` rows in state `SCORED`, one e-value per date block (block =
the row's `expiry_date` bucketed at the horizon's own cadence — 21-day rows
into non-overlapping 21-trading-day blocks, reusing `signal_calibration`'s
block machinery rather than inventing a second one), betting on H0: mean net
return ≤ 0 with a simple bounded-mixture bettor (Waudby-Smith & Ramdas
`ONS`/`mixture` bettor, since row-level returns are heavy-tailed but the
*net-of-cost* return after `EXPLORE_COST_ROUND_TRIP_BPS` is bounded by the
position's own cap). **Receipt fields:** `hypothesis_id`, `n_scored_rows`,
`n_date_blocks` (the number that matters, §58), `e_value_running` (the
product so far), `confidence_sequence_lo/hi` at the current time (anytime
valid, no look penalty — the scoreboard may read it daily), `first_block_ts`,
`last_block_ts`, `bettor` (name + params), and a `BELIEF_CHANGED:` line only
when the running e-value crosses a declared threshold (e.g. 20, "strong
evidence" by Vovk/Wang convention — an operational choice `config.py` should
own, not this note). **Gate:** the roadmap already states it — ≥ 200 scored
PROBE/EXPLORE rows before this is computable at all; below that, print
`CANNOT DETERMINE: n_scored_rows < 200` rather than a wide, meaningless
interval.

## 2. Contextual bandits with a changing action set (Vowpal Wabbit)

**Licence:** BSD-3-Clause (VowpalWabbit/vowpal_wabbit on GitHub) — compatible,
no obligation beyond attribution. **Windows install:** `pip install
vowpalwabbit` ships prebuilt wheels for common CPython/Windows combinations
via PyPI; if the wheel is unavailable for the local Python version, `conda
install -c conda-forge vowpalwabbit` is the documented fallback, and building
from source needs Boost + CMake — worth checking `python -c "import
vowpalwabbit"` locally before promising it in a chunk's done-when, per this
repo's own "a gate that cannot go green is broken" rule.

**What to take:** the `--cb_explore_adf` (contextual bandit, explore, 
action-dependent features) format is built for exactly "today's admissible
hypothesis set changes daily" — each candidate name/hypothesis is one ADF
line under a shared context line, so the action set is not fixed model
architecture, it is data. Exploration strategies to benchmark against
Thompson: `--cover` (Online Cover, diverse policy ensemble), `--softmax`
(temperature-scaled, closest in spirit to Thompson's posterior draw),
`--regcb`/`--squarecb` (regret-optimal, tighter theoretical bounds, more
sensitive to model misspecification). Off-policy evaluation: `--cb_type
ips|dm|dr` — inverse propensity scoring (unbiased, high variance when the
logged propensity is small), direct method (fit a reward model, biased if
misspecified, low variance), doubly robust (combines both, the standard
recommendation when propensities are noisy — ours will be, at n≈200).

**What to refuse:** VW's own online-updated policy as a capital authority —
it is a **benchmark against Thompson**, per chunk 24's own framing, not a
second thing with capital until an off-policy comparison says it beats
Thompson on the same logged data. Refuse trusting IPS variance estimates
computed as if rows were independent — the same overlapping-horizon problem
as §1 applies to OPE variance, not only to the sequential test.

**What the logged row must carry (so 23a writes the right row today):**
context features (regime, ticker vol, coverage, the leading signal's value,
horizon), the full **action set considered** that day (VW's ADF format wants
every candidate, not only the chosen one), the **chosen action**, the
**probability the logging policy (Thompson) assigned to the chosen action**
— never 0, VW's IPS divides by it — and, once graded, the **realized reward**
(net return after cost). This is precisely item 12 of Murat's review and
exactly what 23a already specs; §16.3's row already names
`hypothesis_id`, `capital_usd=0`, `virtual=true`, the expiries, and "the
probability with which Thompson selected the action" — nothing in VW's
requirements adds a new field, it only requires that the **full considered
set**, not only the winner, be on the row (or reconstructible from same-day
rows sharing `asof`).

**Off-policy evaluation of Thompson at ~200 rows:** expect wide DR
confidence intervals — 200 rows split across several hypotheses and four
horizons is a thin log for any OPE estimator. The right frame is **anytime-
valid off-policy inference for adaptively collected data** (Waudby-Smith,
Ramdas et al.; Karampatziakis, Langford et al. on confidence sequences for
contextual bandit OPE) — it lets the DR estimate be monitored continuously
as rows accrue (matching §1's philosophy) rather than committing to a fixed-n
evaluation date the roadmap has no reason to pick. **Gate:** OPE of any kind
is not decision-grade below roughly 200 scored rows with a non-degenerate
spread of logged probabilities (if Thompson has been near-deterministic,
IPS/DR degenerate regardless of row count) — print the propensity spread
(`min`, `median` `selection_probability` across scored rows) beside any OPE
number so a near-zero minimum is visible before it is trusted.

## 3. Value of information as an exploration-score term

Today's `_uncertainty_bonus` is `coef * se` (`config.EXPLORE_
UNCERTAINTY_BONUS_COEF`, 0.25) — a monotone-in-uncertainty proxy, not a
value-of-information term: it rewards a wide posterior regardless of whether
resolving it would move anything else. Full knowledge-gradient (Frazier,
Powell, Dayanik 2008) integrates over the *next* observation's effect on a
downstream max — correct, but needs a lookahead integral this codebase has
no machinery for yet. **The simplest defensible formula that is still VOI,
not just uncertainty:** with a Normal-Normal posterior (`posterior_read`
already returns mean/se), the expected reduction in posterior *variance*
from one more graded row, holding per-row noise σ₀² fixed, has a closed
form —

    ΔVar(n) = σ₀² · (1/n − 1/(n+1)) = σ₀² / (n·(n+1))

(n = the hypothesis's own graded-row count under one `hypothesis_id`, σ₀²
read off the block-bootstrap CI same as `se_pct` is today). This needs no
simulation and is monotone with full KG for a Normal-Normal model, which is
enough to rank candidates even if it understates the exact decision-theoretic
value. **The family-sharing term the review asks for**
("a name whose grade would move a whole family's read outranks one that
would only move itself") is a multiplier, not a different formula: count
`n_names_sharing_hypothesis_id` — every OTHER admissible name currently
gated on the same posterior — and score

    voi_bonus = ΔVar(n) · capital_at_risk_if_resolved · (1 + n_names_sharing_hypothesis_id)

replacing `coef * se` in `exploration_score`. A name-only hypothesis
(`n_names_sharing = 0`) keeps exactly today's shape (ΔVar substituted for
se, still monotone in "how unmeasured is this"); a family hypothesis (e.g.
`profitability_small`'s decile) gets a larger score for the same σ₀² and n
precisely because resolving it changes every name that decile leads. **First
$0 test:** recompute `exploration_score` for the last EXPLORE contract with
`voi_bonus` substituted, diff the resulting rank order against the shipped
one, print both — a receipt, not a code change (this note does not ship
code). **Gate:** needs `n` (graded rows under the hypothesis) ≥ 2 for ΔVar
to be finite and meaningful; below that, σ₀² itself is unmeasured and the
formula degenerates to the unknown-t width already in `posterior_read`.

## 4. Forecast-error correlation and correlated votes (10 lines)

Bates & Granger (1969): the variance-minimizing combination of N forecasts
weights by the *inverse error-covariance matrix*, `w ∝ Σ⁻¹ 1`; uncorrelated
errors collapse this to inverse-variance weighting (today's implicit
assumption whenever votes are just averaged). Correlated errors make `Σ⁻¹`
unstable to estimate from few observations — the "forecast combination
puzzle" (simple averages often beat estimated-optimal weights out of sample)
— so the safe default is shrinkage toward equal weight, never a raw
inverse-covariance solve on a thin panel. For **counting correlated votes**,
reuse §58's own formula: `k` sources agreeing with average pairwise error
correlation ρ̄ count as `k_eff = k/(1+(k−1)ρ̄)` independent votes, ρ̄
MEASURED from scored-row forecast errors by source pair or
DECLARED_CONSERVATIVE (forced to 0) — never assumed. A **disagreement flag**
(Part 2's idea) is the complement: near-zero or negative same-name
same-day correlation is the "hidden variable differentiates the models"
signal — route it to PROBE rather than averaging it away. **First $0 test:**
a same-source-pair error correlation matrix over `SCORED` rows (signal vs.
reader-arm vs. agency vs. world-model, wherever ≥ 2 sources graded the same
name/date). **Gate:** < 30 paired scored rows per source pair is noise;
print `n_pairs` beside every ρ̄ cell, refuse to discount below 30.

## Gates, in one place

| item | first computable at |
|---|---|
| 23c e-process / confidence sequence | ≥ 200 scored PROBE/EXPLORE rows (roadmap's own number) |
| 23a → 24 off-policy evaluation of Thompson vs. VW | ≥ 200 rows AND a non-degenerate propensity spread |
| 23e VOI bonus | ≥ 2 graded rows per `hypothesis_id` (degrades gracefully below) |
| 23f forecast-error correlation | ≥ 30 paired scored rows per source pair |

## Row schema 23a should write (extends today's ledger row; no field renamed)

```json
{
  "decision_id": "...",
  "hypothesis_id": "profitability_small_decile10",
  "asof": "2026-09-21",
  "ticker": "CVLG",
  "authority": "PROBE",
  "capital_usd": 0,
  "virtual": true,
  "context_features": {"regime": "...", "vol_annual": 0.0, "signal_value": 0.0,
                        "coverage": 0, "horizon_days": 21},
  "action_set": ["CVLG", "INDV", "cash", "..."],
  "action": "CVLG",
  "selection_probability": 0.0,
  "horizon_days": 21,
  "expiry_date": "2026-10-19",
  "seed": 0,
  "n_date_block": "2026-09-block-42",
  "reward": null,
  "state": "DECIDED"
}
```

`reward` and `state` (through `SCORED`) are the grader's write, unchanged
from today's ledger. `selection_probability` is never 0 (VW's IPS divides by
it); `action_set` is the one new list — without it, an EXPLORE/PROBE row
cannot later be scored by VW's ADF-format off-policy estimators, only by
Thompson's own math.
