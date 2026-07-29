# Handoff to Fable — the reasoning engine, what to build and in what order

**Written 2026-07-29 by the research agent. Fable is the build agent.**
Everything here is grounded in `ALLOCATION_EVIDENCE_2026-07-29.md` (verified
evidence) and `REDTEAM_ENGINE_2026-07-29.md` (six design claims attacked, 2 DEAD).
Read both before building. Where they disagree with intuition, they win.

**The freeze (`Aegis module docs/FREEZE_2026-07-28.md`) is in force.** Nothing
below opens a new cross-sectional search. Two items need Murat's explicit call
before they may be registered — they are marked 🔴 **ATTENDED**.

---

## 0. The one-paragraph situation

The reasoning engine's **phase 1 already exists and is live**:
`Aegis module/aegis_brain/macro/macro_analog.py`, 7 tests green, **6,053 daily
descriptor vectors 2002-07 → 2026-07**, **283 belief states** in
`ledger/belief_states.jsonl`. Its face validity is genuinely good (queried at
2020-03-31 it retrieved the GFC; at 2021-12-31 it retrieved the melt-up *and*
Oct-2007). **But it has two independent structural defects that were found this
session, and neither has been measured.** The first job is not building. It is
three diagnostics that can each kill the engine, run on data already on disk.

**Do not build phase 2 before D1–D3 report.** If D1 or D2 fails, phase 2 as
designed is worthless and the correct action is to redesign, not to proceed.

---

## 1. 🔬 DIAGNOSTICS FIRST — three tests, all on existing data, any of which can kill the engine

### D1 — Analog age distribution *(highest priority; can kill the engine)*

**The defect.** Our engine excludes only **63 trading days (~3 months)** around
the query. Red-team measurement: at d=10, k=5, **52.6% of nearest neighbours fall
within ±3 months** of the query and **73.1% within ±12 months**. Purging ±24
months **doubles** the nearest-analog distance (0.654 → 1.347). An engine with a
3-month exclusion is at risk of measuring **the local smoothness of its own state
path**, not historical precedent.

**Build:** for every one of the 283 belief states, dump the accepted analog dates
and compute the distribution of `query_date − analog_date`. Report the share
within 3, 6, 12, 24 months, and the median analog age.

**Kill line (pre-commit before running):** if **>40% of accepted analogs are
within 12 months** of the query, the engine is measuring autocorrelation. Fix is
to raise the self-exclusion to **±24 months** and re-run everything downstream.

### D2 — Effective dimension *(can kill the engine)*

**The defect.** van den Dool (1994) *Tellus A*: matching a high-dimensional state
would need a library *"of order 10³⁰ years"*, and analogs are viable *"only… in
just 2 or 3 degrees of freedom."* Cecconi et al.: required library length is
**M ∼ (L/ε)^{D_A}** — **exponential in effective dimension**. **Our descriptor
vector is 15-dimensional with ~24 years of history.**

Note the red team separately *refuted* the curse-of-dimensionality objection
(Durrant & Kabán 2009: correlated latent-factor data does not concentrate). These
are different problems. Distances remain *meaningful*; the *library* is still far
too short. Both can be true, and both are.

**Build:** PCA the 15 standardised descriptors. Report the eigenvalue spectrum
and the number of components explaining 90% of variance — the effective dimension
D_A. Then re-run retrieval on the **top 2–3 principal components only** and
compare analog sets and forward distributions against the 15-D version.

**Expectation to pre-commit:** if D_A ≥ 5, the 15-D retrieval is
under-supported by our library length and the **2–3 PC version is the honest
engine**. The literature's escape hatch is explicit and unanimous: *collapse the
dimension or do not bother.*

### D3 — Scoring the 283 belief states properly

Nothing has ever graded the engine's forecasts. Four corrections make this
non-obvious, and all four are binding:

**(a) The baseline is PERSISTENCE, not climatology.** ⚠️ *This reverses what this
session proposed earlier on 2026-07-29.* Red-team simulation: persistence alone
scores **BSS 0.713 vs climatology**. 71% of the "skill" is free. A forecaster
significant at **t = 5.2 vs climatology** was **t = −3.3, 0.0% power vs
persistence** — decisively worse than "next month looks like this month". Scoring
against climatology manufactures a publication-grade statistic on a worthless
forecast.

**(b) The deciding metric is a paired Diebold-Mariano test on Brier
*differences* vs persistence** — with a Newey-West / block-bootstrap variance.
**Not BSS.** The Brier *score* is proper; the Brier *skill score* is **not**
(Gneiting & Raftery on Mason 2004), and worse, Mason shows BSS is *"less than 0
if nonclimatological forecast probabilities are issued"* and that **"greater
variance in the forecast probabilities will have a lower expected BSS"** — i.e.
**BSS penalises the sharpness you are trying to produce.** Report BSS as
descriptive only.

**(c) Report RESOLUTION, not calibration.** `Br = REL − RES + UNC`. A forecast
that always emits the base rate is **perfectly calibrated and worth nothing**
(REL = 0, RES = 0). This is an identity, not an empirical claim — it cannot decay
out of sample. **Resolution is the only part that can pay.** Report REL/RES/UNC
separately for every state probability.

**(d) Compute N_eff before believing anything.** Bradley et al. (2008) *Wea.
Forecasting* 23(5): *"for sample sizes up to about 300, one cannot reject the
hypothesis that the true skill score is 0"* for infrequent events; N=50 gives a
95% CI of **[−0.26, +0.57]** with actual coverage **77.3%**. We have 283 belief
states — but they are month-end observations of **6- and 12-month forward
horizons**, so they overlap heavily. **283 monthly obs of a 12m horizon is on the
order of ~23 independent observations.** Use `N_eff ≈ n(1−r₁)/(1+r₁)` (Santer et
al. 2000 *JGR* Eq. 6) **plus** a block bootstrap.

**⚠️ Blocking precondition — the ledger is not scoreable as it stands.** The
backfilled states used **full-sample robust z** (median/IQR) for standardisation.
Retrieval is causal (t ≤ q−63), but the *standardisation* is not: a 2005 state
used 2005–2026 medians. **Recompute descriptors with expanding-window median/IQR
and regenerate the backfill before any score is computed.** The
`INSTR-REGIME-ANALOG` spec already anticipates this: *"any walled successor must
recompute causally."*

**Honest expectation:** with N_eff ≈ 23 the test will very likely be
**inconclusive**. That is a legitimate and publishable result — "we built it and
could not demonstrate skill at our sample size" is exactly the kind of honest null
this program exists to produce. **Report the inconclusive result; do not go
looking for a metric that gives a verdict.**

### D4 (only if D1–D3 survive) — is the confidence channel real?

The engine's confidence (analog sign-agreement × (1 − mean distance percentile))
*looks* informative: **0.43–0.60 in stress vs 0.76–0.81 in calm**. That is
suggestive and untested.

**Build:** after applying the ±24-month purge from D1, compute
`corr(analog distance, |forecast error|)`, and bin forecasts by stated confidence
to test whether high-confidence bins show better **resolution**.

**Kill line:** red team's measurement — if the purged correlation is **under
~0.15**, the confidence channel does not exist in our data and **abstention is
decoration; delete it**. Be warned the bin test reached only **t = 2.00 at a large
true effect** on 252 months, so power is marginal either way.

---

## 2. 🔴 ATTENDED — the one genuinely promising build, needs Murat's call first

### Conditional volatility targeting

**This is the single best-evidenced allocation idea in the entire review**, and
it is the *opposite* of what is usually proposed.

**Continuous vol targeting is dead.** Four independent peer-reviewed refutations:
Liu-Tang-Zhou (look-ahead corrected → **68–93% max drawdown**, works only in the
GFC); Cederburg et al. **p = 0.30**, real-time OOS **0.42 vs 0.46 unmanaged**,
lower CER in **72 of 103** cases; DeMiguel et al. OOS net of costs **0.519 →
0.325, p = 0.979**; Angelidis & Tessaromatis — profitability *"disappeared"* in
the early 2000s. Moreira & Muir's scaling constant is fitted on the full sample.

**Conditional VT survives.** Bongaerts, Kang & van Dijk (2020) *FAJ* 76(4), open
access, no ex-post scaling. Adjust exposure **only in the extreme high- and
low-volatility quintiles**, unscaled otherwise, leverage capped. US market:
**ΔSharpe +0.16, ΔMaxDD −8.3%, ΔES −1.7%, realized/target vol 0.97, turnover
1.6×/yr** — versus conventional VT which **increases expected shortfall in 8 of
10 markets including the US**.

It fits this house unusually well: long-only compatible, leverage-capped, and
**1.6× annual turnover** sits inside Novy-Marx & Velikov's <50%-one-sided-monthly
boundary with our measured 3–4 bps largemid spreads.

**But it is 2-of-10 significant and has no post-2010 subsample split — precisely
the profile that has burned us before** (the jump model passed every explore bar
and died at confirm).

🔴 **Murat's call, not a session's:** the freeze's open doors are S4
capital-flows, S3 exits/SELL, R12-B CZ-CALIB, the REGIME-ANALOG allocation layer,
and the running forward clocks. Conditional VT is a **de-risking overlay**, which
is arguably S3 (exits are first-class *inside the same registry and the same
cumulative deflation count*) — or arguably a new family needing an explicit
exemption. **Do not register it until Murat rules.** If it proceeds: `prior_check`
→ `pre-register-trial` → explore 2004-2018 → confirm 2019-2024, one shot.

### The paper opportunity hiding in this

Genuine null, searched properly: **no peer-reviewed study exists of a long-only,
no-leverage volatility target on the S&P 500, out-of-sample, net of costs, with a
post-2010 subsample.** Bongaerts et al. is the closest (1982–2019, no recency
split). **We are equipped to run exactly that experiment.** It is a real
contribution and it is squarely in the paper's methods-and-negative-results lane.

---

## 3. Design rules that are now BINDING on anything built here

| # | Rule | Why |
|---|---|---|
| **R1** | Baseline is **persistence** (+ a Markov surrogate), **never climatology** | Persistence alone = BSS 0.713 free |
| **R2** | Deciding metric = paired **DM test on Brier differences**; BSS descriptive only | BSS is improper and penalises sharpness |
| **R3** | Report **REL/RES/UNC** separately; **resolution** is the payable part | Calibration-implies-nothing is an identity |
| **R4** | Compute **N_eff** + block bootstrap before any claim | 283 obs ≈ 23 independent |
| **R5** | Run **BOTH** controls: **Markov surrogate** (turnover-matched, isolates the channel) **AND** buy-and-hold / static 60-40 (the economic yardstick, **binding**) | i.i.d. shuffling trades **7.24×** more, gifting the treatment 0.10–0.41%/yr. Ang & Bekaert: regime machinery worth **~4× less** than plain diversification |
| **R6** | **Never** phase-randomise a discrete regime label | Fourier surrogates test a Gaussian null the data cannot satisfy |
| **R7** | Any LLM touching historical text uses a **chronologically-consistent checkpoint** | ChronoBERT/ChronoGPT, `manelalab/chrono-bert-v1-*`, **yearly checkpoints 2000–2024, free, covers our whole window**. Caveat: up to 12mo within-year leakage |
| **R8** | LLM extraction is validated by the **covariance of extraction error with the outcome** on a validation sample — **never by fidelity alone** | Ludwig-Mullainathan-Rambachan. A model that memorised scores *higher* on fidelity: it is partially **anti-diagnostic** |
| **R9** | **Neither** market nor macro data is PIT "by construction" — build our own vintage archive with observation timestamps | GSW yield curve is restated exactly like NFCI, *"without advance notice"*. ALFRED actually favours macro |
| **R10** | Every new component ships with a **named simpler baseline** and a PIT comparison, or it does not ship (**S6**) | Adopted round 13 |
| **R11** | Every pre-declared **fallback trigger** names its own control arm and overlap correction **at registration time** | TEXT-LAZY's fallback fired at t=−15.03 and was noise |
| **R12** | Quote no mathematics from a PDF without glyph-level verification | AMS PDFs drop `−`/`=` to U+FFFD; old AGU PDFs remap `=`→5, `−`→2, `+`→1 |

## 4. What is DEAD — do not build these

- **Continuous / unconditional volatility targeting** (§2).
- **Knowledge graph of supplier-customer-competitor links.** Refused on **our own
  measured edges**: THEME-SUPPLY B−A spread **t = 0.10**, `cust_mom` REJECT,
  `conn_mom` net **t = −0.78** on 67% turnover, `cust_conc` sign reversal.
  Second-order effects multiply four coefficients we measured at ~zero while
  adding degrees of freedom our ceiling prices at **t = 6.58 from zero skill**.
- **LLM as return predictor over historical text.** Permanently forward-only.
- **Any claim that the allocation layer has a cheap deflation budget.** The budget
  is hypotheses **÷ N_eff**, and confirm 2019-2024 holds **~1–2 regime events**.
- **Swapping Optimus's `brain_query` to a vector DB or graph store.** The defect is
  **missing abstention and missing scope**, not BM25-vs-embeddings — an embedding
  retriever with no distance floor returns the nearest robotics document instead
  of the nearest robotics document. See `OPTIMUS_AUDIT_2026-07-29.md`.

## 5. Optimus — three fixes, in order

1. **Distance floor + explicit abstention.** Below the floor return `no_match`.
   **This is the same primitive as D4's abstention — build it once, share it.**
2. **Domain scoping** — robotics and the V5/V7 ancestor corpora must not out-score
   the live program. (Measured: an FRC robotics file scored **4.0** on a finance
   methodology query, above `aegis-finance` at **2.0**.)
3. **Re-ingest at HEAD, on a schedule.** Currently stale to 2026-06-17; rounds
   7–12 and the entire freeze are invisible to it.

The structured tools (`aegis_registry`, `aegis_canon`, `aegis_verified_state`,
`aegis_postmortems`) are **good — change nothing.**

## 6. Do-not-cite list (inherited + new)

- Goyal-Welch-Zafirov **"0 of 17"** — **CONTESTED and barred** until verified
  against the primary table. The abstract says a small number *do* survive both
  in- and out-of-sample. Cite attrition, never annihilation.
- **"140 years"** attributed to Lorenz (1969) — not in the paper.
- **"17 years / 40 years to significance"** attributed to Lo (2002) — our
  derivation; Lo says nothing about years-to-significance.
- Sharpe (1975) **"74%"** to beat buy-and-hold — it is **83%**; 74% is the
  threshold vs *constant mix*. "Seven times out of ten" is unverified.
- Barroso & Detzel (2021), Ang & Bekaert (2002/2004), Guidolin & Timmermann,
  Dacco & Satchell (1999), Leitch & Tanner (1991) — carried only via other
  authors' characterisations; not fetched.

## 7. Build order

```
D1 analog age ──┐
D2 effective dim ─┼─→ if either fails: REDESIGN, do not proceed
                  │
D3 causal restandardise → score vs persistence → expect INCONCLUSIVE, report it
                  │
                  └─→ D4 confidence channel (only if D1–D3 survive)

🔴 conditional VT ── blocked on Murat's freeze ruling
Optimus fixes ───── independent, do any time, #1 shares code with D4
```

**The honest prior on all of this: D1 and D2 are more likely to kill the engine
than to clear it.** That is the correct outcome to want. An engine that survives
those two tests is worth something; one that was never subjected to them is
worth nothing, and this program's entire record says the difference is control
arms.
