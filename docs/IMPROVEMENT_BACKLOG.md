# IMPROVEMENT_BACKLOG — proposals from the 2026-06-20 AFK audit

Everything here is a **change** (refactor / new dependency / new data source / schema or
interface change), NOT a fix — per the AFK rule, changes are proposed, not implemented. Ranked
by leverage × safety. Sources: adversarial review (FINDINGS.md), lookahead audit
(LOOKAHEAD_AUDIT.md), and the research deliverables (SOURCES_USED / DATA_OPTIONS / FACTOR_MENU).

Nothing here was implemented this session. The two fixes that WERE made (F1, F2) and the
allowed test additions are in the git log, not here.

---

## HIGH leverage

### B1 — Harden `compute_fragility_index` against NaN composite (root cause of F1)
If any input normalizes to NaN, `np.mean(norms)` returns NaN because `_clip01(NaN)=NaN` and the
`available` flag treats NaN as available. F1 hardened the *consumer* (`exposure_multiplier`); the
*producer* should drop NaN norms (or treat them as unavailable) so the composite is never NaN.
Small, high-value. **Why a change not a fix:** `compute_fragility_index` predates Chunks 1–6.

### B2 — Propagate `data_grade` into the candidate verdict
`evaluate_candidate` / `rule_evolution` DSR/PBO verdicts carry no `data_grade`, so a verdict from
a directional (free-data) backtest reads as gradeless (FINDINGS F8 / LOOKAHEAD §4). Add the stamp
to the verdict dict and surface it wherever verdicts are displayed/recorded, so no DSR/PBO number
is ever read without knowing it's directional-only. Interface change → propose.

### B3 — Cross-asset rotator: equal-risk-contribution (ERC) vs naive inverse-vol
**The brief's explicit question — what does inverse-vol give up?** Inverse-volatility weighting
equalizes each asset's **standalone** risk but **ignores correlations**. It equals true risk
parity *only when assets are uncorrelated*. In our sleeve (SPY / TLT / IEF / LQD / GLD / SHY) the
duration+credit bloc (TLT, IEF, LQD) is highly correlated (all rate-sensitive), so inverse-vol
**over-allocates risk to that correlated cluster** — the portfolio's actual risk concentrates in
duration even though each leg looks individually small. True **ERC** (equal risk contribution)
uses the covariance matrix so each asset contributes equally to *portfolio* variance, which would
down-weight the duration bloc and lift the diversifiers (gold, equity). riskfolio-lib already
provides `rp`/RiskParity. **Proposal:** offer ERC (riskfolio) as the rotator's base alongside
inverse-vol, backtest both directional under DSR, and prefer ERC if it improves risk-adjusted
drawdown. **Cost:** needs a covariance estimate (denoised covariance.py exists) and is
correlation-sensitive to the lookback. Inverse-vol stays the dependency-light default until ERC
is shown better forward. **Why a change:** new method + dependency surface on the rotator.

### B4 — Crash-model strict provenance mode (FINDINGS F3)
The feature-hash guard is bypassed if the sidecar is deleted (legacy back-compat loads an
unverified model). Add an opt-in `strict=True` (or an env flag) that REFUSES to load without a
valid sidecar — required before EVER arming an overlay (a precondition that composes with the
TRIAL discipline). Keep the permissive default for back-compat. Behavior change → propose.

## MEDIUM leverage

### B5 — As-of slice the fragility composite before any backtest use
`compute_fragility_index` ranks the current value against the **full series**
(`_pct_rank`). Fine for the live descriptive reading; a **lookahead if the composite is ever
backtested** at a past `as_of` (LOOKAHEAD §2). Before any TRIAL-CRASH-style backtest of the
composite, route its inputs through `MarketDataAtTimestamp` (as replay does). Latent, not
currently triggered.

### B6 — `require_sizing_grade` defense-in-depth (FINDINGS F4 + F5)
(a) Coerce a `None`/non-str source to directional so it raises `DataIntegrityError` instead of
`AttributeError`. (b) Make the registry gate also assert source *availability* (or require the
`survivorship_probe` to have passed), so `require_sizing_grade("sharadar")` can't pass before a
real Sharadar adapter exists. Or, minimally, document the mandatory two-gate contract in the
function docstring. Interface tightening → propose.

### B7 — Wire quantstats tearsheets for the lanes (SOURCES_USED gap)
quantstats is installed but unused. Wire a read-only tearsheet (Sharpe/drawdown/rolling) for the
forward lanes + replay results. Pure reporting, no decision path. Low risk, real UX value.

### B8 — Borrow Qlib's PIT-DB schema for the data layer (SOURCES_USED "highest latent gap")
Qlib's point-in-time database design is the cleanest reference for storing as-reported data
leak-free. We already have `pit_observations`; borrowing Qlib's schema ideas (vintage handling,
field-level revisions) would harden the data layer ahead of any fundamentals work. Reference-only
adoption.

### B9 — Extra free leading FRED series as TESTED fragility candidates (DATA_OPTIONS)
Add (as forward-IC candidates, never asserted): BBB OAS `BAMLC0A4CBBB`, CCC OAS, EM OAS
`BAMLEMCBPIOAS`, `T10Y2Y`, breakevens `T10YIE`/`T5YIFR`, financial-conditions `ANFCI`/`STLFSI4`,
and `USEPUINDXD` (FRED-hosted EPU, replacing the removed `gpr_world`). Each must clear the
forward-IC bench (t>3.0, DSR/effective-N) before entering the composite. New data inputs → propose.

## LOW leverage / informational

### B10 — `survivorship_probe` robustness (FINDINGS F6)
Move the `len(s)` check inside the try / validate the fetch return is sized, so a malformed
fetcher return is a graceful "missing" rather than a `TypeError`.

### B11 — EDGAR full-text / guidance mining (DATA_OPTIONS, genuinely PIT)
8-K / risk-factor-diff / guidance-language mining keyed on filing date — the substrate for the
capex/backlog causal edge. Carry the edgartools hang-safety wrapper + the SEC rate-limiter lesson.

### B12 — alphalens dead-weight dependency
Installed but `factor_ic.py` is the real IC bench (project deliberately avoids alphalens). Either
use alphalens for richer tearsheets (turnover/decay) or drop it from requirements to avoid a
dormant dep.

### B13 — Stooq as a data-quality cross-check (DATA_OPTIONS)
Second free price source useful ONLY to cross-check yfinance values; does NOT fix survivorship
(would register directional). Avoid misusing it as "another universe."

### B14 — FRED latest-revised vintage caveat (DATA_OPTIONS, informational)
The standard FRED API serves latest-revised values — a mild PIT issue for revised macro series
(LEI, recession_prob, INDPRO). Negligible for market-priced spreads. Use ALFRED first-release
vintages only if a macro series ever becomes a sizing-grade input.

---

## Deferred (attended / out-of-band — not bugs)
- **Cross-asset rotation lane seed** (Chunk 6): the decision core is built + tested; seeding a NEW
  pre-registered lane is env-gated + attended (like conservative-atr). Owner: Murat.
- **Crash-overlay discrimination** (follow-up #7): the artifact is fixed/provenanced but the model
  does not discriminate (val AUC=nan, sparse events). Keep the overlay DARK; arming needs a
  discriminating model on a pre-registered lane.
- **Sharadar purchase** (sizing-grade data): documented drop-in; not recommended now given the
  2026-06-20 free/directional decision.
