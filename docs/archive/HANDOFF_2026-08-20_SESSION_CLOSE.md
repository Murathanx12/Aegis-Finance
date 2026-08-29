# HANDOFF — 2026-08-20 session close

Everything below is local. **26 commits on `main`, nothing pushed** (Order
24 forbids deploying during a discovery run). Full results:
`docs/HANDOFF_2026-08-20_ORDER_24.md`. Order text:
`docs/ORDER_24_DISCOVERY_RUN_REVISED.md`.

---

## 1. WHAT THIS SESSION DID

Order 23 was **not** executed as written. Two independent reviews arrived
first, both making the same objection — eight hours of compute could
produce an impressive dataset without producing eight hours of evidence.
The run was restructured as Order 24 and executed against that.

**23 trials with receipts · 26 commits · 29 files of new code · 5,097
tests green.**

### The four results worth carrying

**Risk is stationary where return is not.** A risk model trained on
1990–2006 ranks 2020–2024 volatility as well as one trained on 2013–2020
(era-transfer ratio **1.001**; reverse 0.992). Over the same decades the
price-only return signal flips *sign*. Strongest structural argument the
programme has for the RISK product, and it is a claim about markets, not
about a fitted model.

**We beat the options market on risk — but only on ordering, and only
with options.** `lgbm_options` beats IV-scaled on the symmetric loss in
both eras (+0.144 modern / +0.064 early, both CLEAR). Two corrections
fell out: **HAR-RV is not the baseline** (it loses to IV), and **without
options features the model does not clear IV at all**. Raw IV wins QLIKE
only by over-forecasting — the variance risk premium exploiting QLIKE's
asymmetry, not skill.

**A real risk signal we cannot spend.** Five routes from that model to a
portfolio decision, all failing against a trailing 63-day standard
deviation: cross-sectional sizing, shrinkage-corrected sizing,
covariance-aware min-variance, regime conditioning, exposure targeting.
Mechanism measured — the model is **shrunk** (cross-sectional dispersion
0.67–0.82× trailing), and inverse-vol weights are driven by an
estimator's *spread*, not its ordering.

**Everything we own measures the same 3–7 latent factors.** No source
owns a factor; every one is a blend. Stable across periods (subspace
alignment **0.962** vs 0.249 for random subspaces) and it **replicates in
1990–2012**. This *explains* every "does this feed add anything" negative:
the sources are not independent channels.

### Closed cheaply (the real value)

| closed | how |
|---|---|
| regime-conditional factor selection | perfect foresight nets +0.24%/yr vs a 3%/yr bar |
| the blind 3,000-book sweep | cancelled on effective dimension ≈ 3.5 |
| the MLP as risk head | loses both losses, worst under lag, one stock-month = 70% of its QLIKE |
| denoising features | hurts by a powered margin; correlation-noise floor ≠ prediction-relevance floor |
| the level ceiling, 3 ways | price state, macro features, date-level scaling — all significantly worse |
| conditional trimming | all 84 declared cells negative — no state makes trimming right |

### Integrity work

- **All 119 WRDS metas were mislabelled** (constant window 2013–2024,
  including every 1990–2012 slice). LABELS_ONLY — 0/119 row mismatches.
  Now derived from data.
- **`CHRONOLOGY-AUDIT-1`**, 9 checks. The options risk head is
  chronologically **clean** (307,924 joins, zero negative lags) — the
  review's top suspicion refuted by measurement. Two FAILs found:
  13F `fdate` is a vintage stamp (not a filing date), and the manager
  library's declared PIT column was never propagated into the artifact.
- **I killed two of my own results**: an interpretation refuted by
  testing it (`CONSTRUCTION-CUT-1`), and a positive that survived in
  exactly 1 of 8 cells (`INFORMATION-DIMENSION-RECONCILE`).

---

## 2. WHAT IS LEFT — WRDS PULL

**Running now.** Single process, 5 workers, PID visible via
`Get-Process python`.

| | |
|---|---|
| planned (joinable tables) | **1,327** |
| pulled | **155** (161 files on disk incl. earlier run) |
| failed | 417 (mostly `permission denied` on sub-schemas — fast, harmless) |
| size | 314 MB in `backend/data/optimus/wrds/bulk/` |
| throughput | ~4.2 tables/min processed |
| **ETA** | **~3 more hours (≈21:50 tonight)** |

**Definition of "everything", because it matters for the handoff.** The
entitled catalogue is **42,167 tables, ~2×10¹⁵ rows** across 46 SELECT-OK
schemas — one day of TAQ quotes exceeds the disk. "Everything" is defined
as *every table with a linkable entity ID **and** a date*, since nothing
else can join our panel. The other **40,787 are logged with sizes and the
reason each was skipped** (`pull_everything_manifest.json`).

**Already landed and immediately useful:** the real **Fama-French
factors** (FF5 daily/monthly, momentum, Pastor-Stambaugh liquidity) — the
residual-alpha gate had been running on JKP *proxies* — and **83 Fed rate
series** (used same-day in `STATE-OBSERVABLE-1`).

**Operational facts the next session needs** (in
`reference_wrds_access` memory):
- WRDS connection cap is **exactly 7**. One PROCESS at a time, ≤5 workers
  inside it. Never start a second puller to check on the first — it
  competes for the cap and makes the first look broken.
- `ps aux` in bash **cannot see detached Windows processes**. Verify with
  PowerShell `Get-Process` or by watching file mtimes.
- The plan cache (`pull_everything_plan.json`) makes restarts cheap;
  without it every chunk re-queries `information_schema` for minutes.

**When it finishes:** commit a stable manifest snapshot. The manifest and
plan cache are now **gitignored** — they were tracked and being rewritten
every few tables, which dirtied the tree and contaminated tonight's
launcher receipt.

---

## 3. WHAT IS LEFT — TESTS / TRIALS

**Not started:**
- `REENTRY-OPTION-VALUE-1` — hold / trim / exit / exit+confirmation
  re-entry. The one genuinely unstarted item from the review. Needs
  price-path replay; the episode library has terminal wealth but no
  re-entry arms.
- **Frozen CRSP replication of CONVEXITY** — substrate is ready, the
  design is frozen, it has not been run. This is the population that
  could *confirm* rather than screen.
- `STREAK-MECHANISM-1` — is 5-up-day reversal concentrated in abnormal
  volume / skew / lottery state / illiquidity?

**Open questions this session created and could not close:**
- The residual **level** headroom. IV carries part of the market level
  (oracle's absolute gain 1.4–1.8× larger without it), but a
  proportionally similar slice survives and nothing tested reaches it.
  Only untried route: a genuinely better market-variance forecast (index
  options / VIX term structure, not macro proxies).
- Whether a construction layer exists that raises effective dimension.
  Removing the top-N cut makes it **worse** (3.72 → 1.31). Untested:
  concentration between 50 and full cross-section, long-short,
  sector/factor neutralisation.

---

## 4. WHAT IS LEFT — IMPLEMENTATION

1. **Manager library v2** — gate on `rdate + 45d`, split-adjust via
   `cfacshr`. **Unblocks four MANAGER-\* trials**, all currently blocked
   because 13F carries no knowledge-date column.
2. **Persist per-book holdings + turnover paths** in any future sweep.
   Two of the five similarity views are currently unanswerable without
   them.
3. **NAV stamp fix (P-day-2026-08-19a)** — decided and test-backed:
   **ship the lane fix, do NOT touch the benchmark.** SPY is fetched by
   true bar date and no benchmark is stored in `paper_nav`, so
   lane-vs-SPY is *already* misaligned and the fix repairs it. Pinned by
   4 known-answer tests. Needs an attended go (sacred write path).
4. **G2 lane preregs** for the 09-08 window — use the **cheap trailing
   estimator**; the receipt must not claim the model is why it works.
5. **Risk-head artifacts** are built and pinned:
   `risk_head_vol_lgbm_options@2.0.0@31b9b8d62c777e97` (+ an early-era
   twin). Both flag their calibration window as a volatility outlier —
   the level offset is provisional.

---

## 5. THE NIGHT — STATE AND ONE OPEN DECISION

**Armed.** `AEGIS_IIF1_LAUNCHER_ARMED=1` at User scope, **verified via a
throwaway scheduled task that Task Scheduler itself sees it** (a
subprocess of the running shell does not — stale environment block; never
verify arming that way). The launcher task was not touched: `Ready`,
trigger still `2026-08-18T17:00:00`, next run **Fri 08-21 17:00**.

**First self-launch is tomorrow 17:00.** Disclosed deviation: armed after
**1** clean scheduled receipt, not the declared 3/3. The 4-point
pre-flight passed (uncontradicted · Ready/not-re-registered ·
`git_dirty False` · `stdin_isatty False`).

**Tonight did not run.** At 17:00 the launcher had ~+2 min margin and
every derived check passed — it refused for exactly one reason,
`NOT_ARMED`. By the time we tried manually (17:42) the run's own guard
refused with `NightWouldSpanTheOpen`: the tool-bearing arms would have
read live intraday data while being graded from a pre-open timestamp —
**hindsight handed to the treatment arms of the primary contrast**. That
night would have completed, reported `ok`, and been void. Not run.

**Accrual: 3 of 40 graded nights.** Nights 08-17/18/19 ran attended
(585/600/585 records). 08-14 void.

**Open decisions for the next person:**
- The launch window is ~**2 minutes** (fires 17:00, latest safe launch
  ~17:02). A loaded machine refuses rather than launching late — correct,
  but not robust. Widening it means moving the trigger earlier, which
  changes snapshot freshness — a design parameter of the frozen trial,
  deliberately not changed unilaterally.
- The duration bound uses a **2.0× safety factor** on a worst measured
  night of 115.4 min → 231 min. Three nights ran 109.7–115.4. It did not
  cost us today, but it will eventually refuse a night that starts at
  17:05.
- Whether tonight's receipt counts toward the 3/3 clock: it carries
  `git_dirty: True`, caused by my WRDS pull writing a tracked file. Fixed
  and verified `False` since.

---

## 6. ONE-LINE STATE

We have a real, replicated, era-invariant **risk** signal; five tested
routes from it to a portfolio decision all lose to a trailing standard
deviation; and everything we own measures the same 3–7 stable factors —
which is why buying another feed has never added a dimension. The next
dollar should buy an information class that is **not** a re-measurement
of those factors, and we can now test that claim before spending it.
