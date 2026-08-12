# NIGHT-13 — EXPOSURE-CONTROL-1: the book-keyed ladder, judged on the war it was built for

**Trial:** EXPOSURE-CONTROL-1, pre-registered `Aegis module/TRIALS/PREREG_EXPOSURE_CONTROL_1.md`
at commit `c5b81aa`, BEFORE any managed path was computed. One accruing arm.
**Runner:** `Aegis module/scripts/run_exposure_control_1.py`.
**Artifacts:** `Aegis module/data/factory/exposure_control_1_calibration.json`
(grid committed to disk before the holdout was opened) and
`exposure_control_1_holdout.json`.

---

## VERDICT (frozen rule, §4): **UNRESOLVED — policy shelved, NOT defaulted**

Compared unrounded, exactly as frozen:

| §4 condition | value | bar | outcome |
|---|---|---|---|
| Calibration coverage (dd avoided ≥5pp in ≥4/6 episodes) | **6/6** (all 9 candidates) | 4/6 | PASS |
| Any calibration episode TW ratio < 0.60 (REJECT tripwire) | min 0.764 ('20) | 0.60 | not tripped |
| War episode maxDD shallower by ≥5pp, net of 10bps | **+13.92pp** (−8.94% vs −22.87%) | 5pp | PASS |
| Terminal wealth ratio ≥ 0.85 over the full holdout window | **0.849863** | 0.85 | **FAIL by 1.4bps of wealth** |

The ADOPT conjunction fails on the wealth leg alone. The frozen table has no
row for "war leg passed, wealth bar missed"; its residual — shelve, do not
default, do not kill — is the honest landing. One window cannot rescue a rule
any more than one episode can kill it (§19), and the miss is 0.000137 of
terminal wealth against a bootstrap SE of 0.165 on that very ratio: the bar
decision is real under the frozen rule, but the difference between 0.8499 and
0.85 is far inside noise, and re-litigating it after seeing the number is
exactly what pre-registration forbids.

**The §16-adjacent finding that matters more than the bar:** the ladder's own
mean exposure held statically (w̄ = 0.484, the third control) had a
*shallower* full-window drawdown (−11.50% vs −12.55%) *and* more wealth
(TWR 0.914 vs 0.850). The ladder's timing content over "just hold less" is
negative on the holdout (paired log-wealth −0.073, SE 0.072, 80%-power MDE
0.180 log) — **not detectable, and pointing the wrong way**. What survived
tonight is not a ladder; it is the statement that a beta-2.15 book held at
roughly half exposure is a materially different risk object at modest wealth
cost — which anyone can buy without a rule.

---

## 1. The instrument

Frozen in the prereg §1: `w_t = min(w_vol, w_beta, w_dd_cap)`, leverage cap
1.0, cash earns 0, daily clock, **one-day lag**. `w_vol = min(1, σ*/σ_book,63d)`;
`w_beta = min(1, 1.5/β_63d)` (β* = 1.5 a stated prior, never tuned);
drawdown ladder: dd < −D* → cap 0.5 until dd recovers above −(D*−5pp),
minimum dwell 10td. Re-entry strictly inside exit, enforced at construction.

**Causality proofs (both beds, perturbation, abort-on-failure):**
proxy 2007-09, probe 2008-10-15, w = 0.189876 bit-identical after perturbing
all later data; holdout book, probe 2026-06-18, w = 0.338159 bit-identical.

## 2. Calibration (proxy, 10bps decides)

Bed: `r_book = 2.15·mktrf + rf` (FF daily, 1926→2026-05). Episode boundaries
derived from the proxy path's own peak/trough, not hand-set:

| episode | burn-in | peak | trough | recovery end | proxy peak→trough |
|---|---|---|---|---|---|
| 1973-74 | 1972-01-11 | 1973-01-11 | 1974-10-03 | 1975-10-02 | −80.3% |
| 1987 | 1986-08-26 | 1987-08-25 | 1987-12-04 | 1988-12-02 | −62.6% |
| 2000-02 | 1999-03-26 | 2000-03-24 | 2002-10-09 | 2003-10-09 | −82.7% |
| 2007-09 | 2006-10-06 | 2007-10-09 | 2009-03-09 | 2010-03-09 | −86.1% |
| 2020 | 2019-02-19 | 2020-02-19 | 2020-03-23 | 2021-03-23 | −62.8% |
| 2022 | 2020-11-06 | 2021-11-08 | 2022-10-14 | 2023-10-17 | −50.9% |

On the proxy the realized 63d beta is ~2.15 by construction, so **w_beta binds
trivially at ~0.698 everywhere** — there it is a constant de-lever, not a
signal (stated in the prereg; the rung tables confirm the vol term, not beta,
does nearly all the binding).

Grid (σ* × D*, 9 candidates — every one covered 6/6, so selection fell
entirely to mean episode terminal wealth ratio, per §3):

| candidate | covered | mean TWR | min TWR | mean TO cost (bps) |
|---|---|---|---|---|
| **σ\*=0.15, D\*=10 — CHOSEN** | 6/6 | **1.531** | 0.764 | 20.5 |
| σ\*=0.15, D\*=15 | 6/6 | 1.528 | 0.760 | 20.4 |
| σ\*=0.15, D\*=20 | 6/6 | 1.525 | 0.759 | 20.4 |
| σ\*=0.20, D\*=15 | 6/6 | 1.477 | 0.790 | 16.0 |
| σ\*=0.20, D\*=10 | 6/6 | 1.477 | 0.794 | 17.5 |
| σ\*=0.20, D\*=20 | 6/6 | 1.464 | 0.777 | 16.7 |
| σ\*=0.25, D\*=10 | 6/6 | 1.462 | 0.795 | 14.1 |
| σ\*=0.25, D\*=15 | 6/6 | 1.460 | 0.806 | 12.0 |
| σ\*=0.25, D\*=20 | 6/6 | 1.440 | 0.811 | 13.3 |

Per-episode receipts for the chosen candidate — **each row is one episode,
n=1, descriptive (§19)**. dd-avoided MDEs are planted-shave MDEs against the
5pp bar (21td circular block bootstrap, N=2000); CIs are paired on the same
block indices (§18).

| episode | dd unmanaged | dd managed | avoided (pp) [90% CI] {MDE₈₀} | TWR [90% CI] | up-capt | down-capt | TO cost | days vol/dd/beta rung | mean w |
|---|---|---|---|---|---|---|---|---|---|
| 1973-74 | −80.3% | −50.2% | +30.1 [19.8, 33.7] {5.8} | 1.63 [0.77, 3.72] | 0.40 | 0.42 | 20.8bps | 462/212/15 | 0.425 |
| 1987 | −62.6% | −30.4% | +32.2 [9.9, 36.5] {8.6} | 1.34 [0.70, 3.17] | 0.32 | 0.36 | 14.6bps | 193/125/6 | 0.395 |
| 2000-02 | −82.7% | −44.2% | +38.5 [28.6, 44.5] {6.2} | 2.09 [0.81, 5.75] | 0.31 | 0.32 | 34.4bps | 877/13/0 | 0.330 |
| 2007-09 | −86.1% | −32.7% | +53.4 [31.9, 61.5] {5.7} | 2.08 [0.66, 7.62] | 0.25 | 0.25 | 22.2bps | 608/0/0 | 0.298 |
| 2020 | −62.8% | −24.8% | +38.0 [10.2, 45.4] {8.8} | 0.76 [0.34, 2.22] | 0.26 | 0.29 | 15.6bps | 269/3/4 | 0.318 |
| 2022 | −50.9% | −21.4% | +29.5 [18.2, 41.1] {6.3} | 1.28 [0.71, 2.44] | 0.34 | 0.35 | 15.5bps | 396/92/0 | 0.371 |

All six up/down capture pairs sit within 0.04 of each other — **symmetric
captures = no timing skill claimed, only less risk** (V0's own docstring
rule). Every TWR CI straddles 1: even six drawdown episodes cannot certify a
wealth gain from de-levering the levered proxy; wealth-diff MDEs run 2.6–6.7×
in ratio terms. The 5pp dd-coverage is powered (all avoided values sit 3–9×
above their measured MDEs); the wealth side is not.

## 3. Holdout — the real book, opened once

Equal-weighted daily book of the 12 CONVICTION-REPLAY-1 picks (APLT/SLNO
synthetic, excluded from daily stats), 2025-11-07 → 2026-08-10; reproduces
the frozen parent numbers exactly (vol 40.4%, β 2.153, maxDD −22.87%).
Warmup: 54 in-window days carried full risk before the 63d vol/beta signals
existed — counted, V0's own convention. The war episode was touched by
nothing during calibration; the grid choice was on disk first.

**Full window (base 10bps):**

| | unmanaged | ladder (σ\*=0.15, D\*=10) | constant w̄=0.484 control |
|---|---|---|---|
| maxDD | −22.87% | **−12.55%** (avoided +10.32pp [0.7, 20.6], MDE₈₀ 6.1pp) | **−11.50%** |
| terminal wealth | 1.2245 | 1.0407 → TWR **0.8499** [0.63, 1.16], SE 0.165 | TWR **0.914** |
| up-capture / down-capture | — | 0.445 / 0.481 | 0.484 / 0.484 by construction |
| turnover cost | 0 | 32.1bps (stress 50bps: 160.4bps, TWR 0.839, dd −12.9%) | ~0.5bps |
| exposure (mean, min) | 1.0 | 0.484, 0.335; rungs: 29 full / 133 vol / 26 dd / 0 beta | 0.484 flat |

**War episode 2026-06-04 → 2026-07-29 (n=38td, one episode, descriptive):**

| | unmanaged | ladder | constant control |
|---|---|---|---|
| maxDD | −22.87% | **−8.94%** — avoided +13.92pp [9.5, 19.4], MDE₈₀ 6.1pp | −11.50% |
| episode wealth | 0.7906 | 0.9194 → TWR 1.163 [1.06, 1.28] | — |
| turnover cost | 0 | 1.6bps (the ladder was ALREADY at w≈0.34–0.36 when the war began — vol-bound all 38 days, dd-cap never needed) | 0 |

The war receipt is the mechanism working as designed: the book's own 63d vol
had the exposure at a third *before* the drawdown started, which is why the
war-window turnover is 1.6bps — it did not react to the crash, it was already
small. Note the 21td-block bootstrap on a 38td window has ~2 blocks; the CI
is printed because §19 requires it, not because n=1 got less descriptive.

## 4. Controls (§6)

- **Unmanaged book** — every number above is paired against it.
- **Index-keyed corpse (EXPOSURE-CONTROLLER-V0, ported policy):** on the
  real-book holdout its own artifact is the receipt — SPY never broke trend
  or vol triggers, exposure 1.0 all 188 days, **the corpse never fires while
  the book-keyed ladder de-risked 159 of 188 days**. The book-keying is the
  entire difference on the holdout, exactly the gap NIGHT-12 measured. On the
  proxy episodes V0 does fire (22.8–69.1% of days de-risked) — but there the
  index IS the book path ×2.15, so index- and book-keying coincide by
  construction; the proxy cannot separate them, the holdout does.
- **Constant-exposure at the managed mean (the "just hold less" test):** the
  ladder does NOT beat its own average held statically. Full holdout: static
  control shallower dd (−11.50% vs −12.55%) and more wealth (0.914 vs 0.850).
  On the proxy, ladder-minus-constant dd differences are negative (ladder
  deeper) in 5/6 episodes with every 90% CI straddling zero; paired wealth
  differences all sit below their 80%-power MDEs (1.13–1.30 ratio terms).
  **The timing content of the ladder is not detectable anywhere; the war
  episode's better dd (−8.94% vs −11.50%) is the one receipt in its favour,
  and it is n=1.**

## 5. Limitations — read before quoting any number

- **The proxy has no idiosyncratic gap risk.** `2.15·mktrf + rf` carries the
  right vol and beta but a diversified market path scaled up is not a
  12-name biotech-heavy book: a binary readout gaps THROUGH a daily ladder
  with a one-day lag. The calibration numbers are ceilings on smoothness,
  not forecasts.
- **One holdout window, one war, n=1.** The full-window TWR of 0.8499 has an
  SE of 0.165; the bar decision is frozen but the number itself cannot
  distinguish 0.85 from 0.70 or 1.15.
- Cash earns 0 by frozen assumption; at ~4% bill yields, mean cash weight
  ~0.52 over ~0.75y understates the managed path's wealth by roughly 1.5pp —
  more than the 1.4bps the wealth bar was missed by. Noted, not applied: the
  prereg froze it, and unfreezing it after seeing the margin would be
  outcome-shopping.
- 54 warmup days carried full risk inside the holdout window (signals need
  63 obs). The war was long past warmup.

## 6. What may NOT be concluded

- **No crash prediction, no alpha, no Sharpe claim** (prereg §5). The claim
  tested was path-risk shaping priced in forgone wealth, and the wealth
  price came in at the bar's edge.
- **Not** "the ladder times drawdowns": the constant-exposure control beat
  it on the full holdout and matched it on the proxy; symmetric up/down
  captures everywhere say *less risk*, not *timed risk*.
- **Not** "the rule failed": the war leg cleared its bar 2.3× above its
  measured MDE. UNRESOLVED means shelved on the frozen wealth criterion, one
  window, no kill (§19).
- **Not** a shadow-book default, not a lane, no order path. Any future
  promotion re-registers with this corpse as control. TRIAL-COND-VT
  (index-keyed, month-end) stays closed; nothing here reopens it.
- The strongest licensed sentence tonight: **for this book, at this beta,
  roughly half exposure — however arrived at — cuts the war drawdown by
  half or better; the ladder's machinery adds nothing detectable over the
  constant, and the index-keyed alternative adds literally nothing.**
