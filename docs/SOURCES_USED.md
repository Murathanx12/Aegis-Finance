# SOURCES_USED — Open-Source Repos vs. What Aegis Actually Uses

**Date:** 2026-06-20
**Status:** Reference / decision-aid only. No code, dependencies, or wiring changed by this document.
**Method:** Grounded in `backend/requirements.txt` (pins), grep of imports across `backend/` + `engine/`,
the verdicts in `docs/V3_RESEARCH_SYNTHESIS_2026_06_20.md` (§4), and the header of
`engine/validation/factor_ic.py` (which explicitly avoids alphalens).

**Verdict legend:**
- **adopted** — the library is installed *and* imported on a real code path.
- **borrowed-concept** — not installed; the *technique/pattern* was reimplemented locally.
- **skipped** — neither installed nor reimplemented (or installed-but-dormant; noted explicitly).

---

## Summary table

| Repo | Verdict | What was taken (or would be) | Skip correct? / Gap |
|---|---|---|---|
| **OpenBB** | skipped | Nothing. Considered only as an optional ad-hoc data adapter; never a backtester/optimizer. | **Correct.** It is a data layer with no PIT control; backtesting through its live calls would inject lookahead. Our own FRED/yfinance/Polygon fetchers cover needs. |
| **Microsoft Qlib** | skipped | Nothing yet. *Would* borrow Alpha158/Alpha360 factor formulas + PIT-DB schema design. | **Correct to skip the framework** (A-share origin, `.bin` format, rebuild-the-pipeline cost). **GAP (latent):** the PIT-DB schema is the recommended reference for V3's data-integrity gate and is not yet borrowed. |
| **zipline-reloaded** | borrowed-concept | The Pipeline pattern (rank a universe → percentile) reimplemented in `cross_sectional_momentum.py`. Bundle/event system NOT taken. | **Correct.** Concept reuse beats adopting the bundle machinery; our own PIT-safe loop stays source of truth. |
| **alphalens(-reloaded)** | adopted-but-dormant | Installed (`alphalens-reloaded>=0.4.5`). The actual IC bench is hand-rolled in `engine/validation/factor_ic.py`, which deliberately carries no alphalens dependency. | **Defensible.** factor_ic.py is the real critical path; alphalens is an optional formalizer. **Minor GAP:** an installed dep with zero importers is dead weight until wired. |
| **Riskfolio-Lib** | adopted | `portfolio_optimizer.py` + `mpc_optimizer.py`: Mean-CVaR, HRP, Risk Parity, Max Diversification. | n/a — used. |
| **mlfinlab** | borrowed-concept | PSR/DSR/PBO-CSCV/CombinatorialPurgedCV/Harvey-Liu-Zhu hurdle reimplemented in `engine/validation/overfitting.py`; purged CV, fracdiff, labeling, sample-uniqueness in `engine/training/`. Reference copy at `C:\Users\mrthn\reference-codes\mlfinlab`. | **Correct.** License/maintenance make direct dependence unattractive; the methods are reimplemented from the LdP papers directly. |
| **edgartools** | adopted | Installed (`edgartools>=5.28.0`, imports as `edgar`). Used in `fundamentals.py` (`from edgar import Company, set_identity`) for SEC financials/13F. | n/a — used. **Caveat:** the high-volume Form-4/Archives path in `edgar_events.py` deliberately uses raw rate-limited `requests` (not edgartools) after the prod-403 fix. |
| **hmmlearn** | adopted | `backend/models/hmm.py` — HMM regime classification (bull/bear/volatile/neutral). | n/a — used. |
| **bt** | skipped | Nothing. | **Correct.** Our own PIT-safe event loop is the source of truth; `bt` only acceptable for throwaway multi-asset monthly-rebalance prototyping, which we don't need. |
| **quantstats** | adopted-but-dormant | Installed (`quantstats>=0.0.79`) for lane equity-curve/Sharpe/drawdown tearsheets. No importer found in `backend/` or `engine/`. | **REAL GAP (small).** Pinned but unwired — the forward lanes have NAV but no quantstats tearsheet output. Cheap win left on the table. |

---

## Per-repo detail

### OpenBB — *skipped (correct)*
OpenBB is a "connect once, consume everywhere" data platform, not a backtester or optimizer. The V3
synthesis (§4) classifies it as an *optional data adapter* with the explicit warning never to backtest
through its live calls (no point-in-time control; most of its "40+ providers" require their own,
often paid, keys). Aegis already has purpose-built fetchers (FRED, yfinance, Polygon, SEC). Skipping
it is the right call; there is no gap.

### Microsoft Qlib — *skipped framework / latent gap on the schema*
Not installed; no `import qlib` anywhere. The synthesis rates it **learn-from (high value)** for two
things: (1) the Alpha158/Alpha360 factor formula library as a feature menu, and (2) its built-in
point-in-time database schema (released Mar 2022), called out as the best open-source reference design
for storing PIT data leak-free. Skipping the *framework* is correct (A-share origin, `.bin` format,
adopting it means rebuilding our pipeline around its abstractions; US data needs user feeds anyway).
The **latent gap** is that V3's hardest open problem is data integrity for single-stock backtests, and
Qlib's PIT-DB design is the named reference for that gate — borrowing the schema is on the roadmap
(Session B) but not yet done.

### zipline-reloaded — *borrowed-concept (correct)*
Not installed (`import zipline` not found). The Pipeline API pattern — rank a universe, take top-N — is
reimplemented inside our own loop in `backend/services/cross_sectional_momentum.py` (percentile rank
within the universe; the module honestly notes weak/insignificant forward IC on the current universe).
The bundle/data system was correctly NOT taken. This is exactly the right kind of reuse: the pattern,
not the machinery, so our PIT-safe event loop remains the source of truth. Note V3 still wants a fuller
cross-sectional ranker (Session C) — the *pattern* is borrowed, but the production-grade ranker is not
yet built out.

### alphalens(-reloaded) — *installed but dormant; defensible, minor gap*
Installed as `alphalens-reloaded>=0.4.5` (imports as `alphalens`). Critically, the in-repo IC bench is
`engine/validation/factor_ic.py`, whose header states it computes Alphalens-style IC "directly so we
carry no fragile third-party dependency." That module is the real critical path: cross-sectional
Spearman IC, IC IR, t-stat, hit rate, quantile spread — everything used to grade T8/T9/T10 forward
signals. So alphalens is installed but **NOT on the critical path**. This is defensible (own
implementation is lighter and avoids a heavy dep), but an installed library with zero importers is dead
weight until it's actually wired as the formal bench the synthesis envisions. Minor gap, low priority
given factor_ic.py already does the job.

### Riskfolio-Lib — *adopted (correct)*
Installed (`riskfolio-lib>=7.0.0`) and imported on a real path: `backend/services/portfolio_optimizer.py`
and `backend/services/mpc_optimizer.py` use it for Mean-CVaR, HRP, Risk Parity, and Max Diversification.
The synthesis rates it stronger than PyPortfolioOpt for cross-asset CVaR / risk-parity / hierarchical
budgeting and earmarks it for the planned regime rotator. Genuinely used; no gap.

### mlfinlab — *borrowed-concept (correct)*
Not installed (`import mlfinlab` not found); a read-only reference copy lives at
`C:\Users\mrthn\reference-codes\mlfinlab`. The methods are reimplemented locally from the López de Prado
papers: `engine/validation/overfitting.py` implements PSR, expected-max-Sharpe, DSR, MinTRL, PBO via
CSCV, CombinatorialPurgedCV, and the Harvey-Liu-Zhu t≥3.0 hurdle; `engine/training/` carries fracdiff,
labeling, sample-uniqueness, and `engine/validation/purged_cv.py` carries purged/embargoed CV. Avoiding a
direct dependence (license + maintenance concerns) while reimplementing from primary sources is the
correct posture and matches V3's "our guards are already correct" conclusion.

### edgartools — *adopted (correct, with a deliberate carve-out)*
Installed (`edgartools>=5.28.0`, package imports as `edgar`). Used in
`backend/services/fundamentals.py` via `from edgar import Company, set_identity` for SEC financials and
13F. The synthesis rates it the cleanest EDGAR library. Important nuance: the high-volume insider
Form-4 / Archives collection path in `backend/services/edgar_events.py` (and `pit_collectors.py`)
deliberately does NOT use edgartools — it routes raw `requests.get` through a shared ≤8/s rate limiter
after the prod-403 fix (commit `cb01d8b`), because the volume on `www.sec.gov/Archives/` tripped SEC's
10/s cap. So edgartools is adopted for the low-volume structured path; the high-volume path is
intentionally hand-rolled for rate control. Both are correct.

### hmmlearn — *adopted (correct)*
Installed (`hmmlearn>=0.3.2`) and imported in `backend/models/hmm.py` for the 3/4-state HMM regime
classifier. Genuinely used; no gap.

### bt — *skipped (correct)*
Not installed (`import bt` not found). The synthesis groups it with backtrader/vectorbt/LEAN as
acceptable references but explicitly keeps "our own PIT-safe event loop as the source of truth — that
discipline *is* the moat." `bt` is allowed only for quick multi-asset monthly-rebalance prototyping,
which Aegis has no current need for. Correct skip; no gap.

### quantstats — *installed but unwired; small real gap*
Installed (`quantstats>=0.0.79`) and documented in requirements as the equity-curve/Sharpe/drawdown
tearsheet generator for the paper lanes. But there is **no importer** in `backend/` or `engine/` — it is
pinned and dormant. The forward lanes already record NAV; what's missing is the tearsheet rendering
layer quantstats was added to provide. This is a genuine (if small and low-risk) gap: the dependency was
brought in 2026-06-20 for reporting and has not been wired, so the lanes still lack standardized
tearsheet output.

---

## Net gaps to revisit

1. **quantstats tearsheets are unwired (real, small).** Pinned 2026-06-20 for lane reporting but never
   imported. The lanes have NAV; they lack the standardized equity-curve/Sharpe/drawdown tearsheet
   quantstats was meant to render. Cheap win.
2. **Qlib PIT-DB schema not yet borrowed (latent, important).** V3's hardest gate is data integrity for
   single-stock backtests; Qlib's PIT database design is the named reference and is on the roadmap
   (Session B) but not yet started. This is the highest-leverage of the gaps.
3. **alphalens installed but dormant (minor).** factor_ic.py already covers the IC bench, so this is
   dead weight rather than a missing capability. Either wire it as the formal bench or drop the pin.
4. **Cross-sectional ranker is pattern-only (medium).** The zipline Pipeline *pattern* exists in
   `cross_sectional_momentum.py`, but the production-grade ranker → top-N → constructor → Riskfolio flow
   (V3 Session C) is not built. The module itself flags weak forward IC on the current universe.

**Not gaps (correctly skipped):** OpenBB, bt — both intentionally out of scope; adopting either would
add lookahead risk or duplicate the PIT-safe event loop that is the moat. mlfinlab and zipline are
correctly borrowed-as-concept rather than depended-on.
