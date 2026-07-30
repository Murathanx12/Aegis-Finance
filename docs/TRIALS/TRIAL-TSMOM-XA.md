# TRIAL-TSMOM-XA — defensive cross-asset trend overlay vs 60/40 control

**Pre-registered:** 2026-07-26 (this doc committed BEFORE any forward data
accrues; registry rows created at the attended seed, per house pattern).
**Lanes:** `tsmom-overlay` (treatment) + `tsmom-6040-control` (control),
both $100k, same inception (seed day), same isolated config hash
(`backend/data/tsmom_xa_lanes.yaml`, `db.get_tsmom_config_hash`).
**Seeding:** attended + env-gated (`AEGIS_SEED_TSMOM_XA=1`), AFTER the
2026-07-26 re-book fix (`36c8ece`) is verified live.

## Provenance

INSTR-TSMOM-XA is the first macro instrument to survive the module's
explore/confirm wall (module `TRIALS/INSTR-MACRO-BATCH4.md`): crisis alpha
in both held-out crises (2020 +9.2%, 2022 ≈flat), overlay maxDD −18.8% vs
SPY −33.7% — at a real, disclosed price (return drag t −1.86 vs SPY;
2019-24 overlay CAGR 10.2% vs SPY 17.1%). Century-scale literature prior
(Moskowitz-Ooi-Pedersen; Hurst-Ooi-Pedersen). This lane is the pre-committed
next step from the confirm PASS: a forward paper record under the same
frozen spec. **Goal-B framing: defensive diversifier (drawdown/sequence-risk
protection), NOT beat-SPY — the claim is against a 60/40 control.**

## ⚠️ Never-shorts exemption (declared)

The confirmed spec takes SHORT positions inside the sleeve (sign of the
12-1 return; the 2022-flat receipt comes largely from short TLT/USO legs).
House law is "never shorts"; **Murat authorized a paper-only exemption for
this lane on 2026-07-26** (attended session). Shorts exist ONLY inside the
$100k paper sleeve (booked as negative shares; proceeds sit in the CASH
row); nothing product-facing inherits them. A long-flat variant would be a
materially different, unconfirmed instrument and is NOT what this trial
tests.

## Frozen spec (verbatim from the confirmed instrument; NO tuning)

- Assets: SPY, TLT, GLD, USO (all must have ≥273 trading days of history —
  they do).
- Signal, at the last trading day of each month (month-end *me*, trading-day
  offsets): `sign(close[me−21] / close[me−252] − 1)` per asset.
- Sizing: `sign × min(0.10 / σ_ann60, 1.5) / n_active`, where σ_ann60 =
  60-day daily-return std × √252 at *me*, n_active = assets with valid
  signal + vol.
- Overlay book: 50% SPY core + 50% × sleeve weights (SPY legs net);
  CASH = 1 − Σ asset weights (short proceeds raise cash; an all-long
  low-vol month can push cash slightly negative = margin — allowed,
  disclosed).
- Rebalance: first daily check of each new calendar month, priced at that
  day's prices (signal from the prior month-end — the module's
  signal-at-close → trade-next-day convention at lane cadence).
- Control: 60/40 SPY/TLT, same monthly calendar rebalance, same costs.
- Costs: 5 bps transaction + 1 bp slippage on traded value (both lanes).
- Seeding mid-month uses the prevailing (most recent month-end) signal —
  the book the strategy would already be holding.
- A missing live price for any target leg REFUSES the rebalance (hold +
  loud audit) — no placeholder prices under a signed book.

## Decision rule (frozen)

- **Primary:** overlay max drawdown must be SHALLOWER than control max
  drawdown by ≥3 pp over the evaluation window (the defensive claim).
- **Co-primary:** overlay net Sharpe within −0.15 of control net Sharpe.
- **Min window:** 24 months. Earliest decision: 24 months after inception.
- **Crisis-conditionality (declared):** the instrument's value shows in
  stress. If in-window SPY maxDD < 15%, the primary is UNRESOLVABLE →
  decision defers 12 months (ONE deferral max); at the deferred date decide
  on co-primary + descriptive DD comparison.
- **Adopt-consideration:** both bars met → evaluate_candidate gate (never
  auto-adoption).
- **Reject:** overlay net Sharpe trails control by ≥0.25, OR (in-window SPY
  maxDD ≥15% AND overlay maxDD not shallower than control) → lane closes,
  NEGATIVE_RESULTS entry.
- **Crash override:** SPY drawdown ≥20% in-window defers any decision until
  ≥6 months past the trough (house standard).
- **Degraded clause:** any month the signal cannot be computed from live
  data (panel failure) HOLDS the prior book and logs loudly; ≥3 consecutive
  failed months flags the lane degraded.
- Params frozen as above; any variant (sizing v2, long-flat, different
  assets) is a NEW lane + NEW registration.

## Hard constraints

Arms nothing; never touches reference/book/ATR/SMQ lanes (own config hash);
no reconstructed past (inception = seed day); shorts never leave the paper
sleeve; the session builds and verifies — Murat flips the flag.

---

## Declared adverse prior (added 2026-07-30, BEFORE the 24-month decision window closes)

Banked in round 13 (`docs/research/AI_PANEL_2026-07-30.md`). Recorded now,
while the lane is 52 days old and the doubt costs nothing.

The registration's prior rests on INSTR-TSMOM-XA's confirm pass — crisis alpha
in both held-out crises (2020 +9.2%, 2022 flat; overlay maxDD −18.8% vs SPY
−33.7%) with a disclosed return drag (t −1.86). The adverse side of the
time-series-momentum literature was **not** represented in that registration and
is now:

- Huang et al., *Time series momentum: is it there?* — pooled regressions
  **overstate** the predictive ability of the trailing 12-month return; the
  statistical evidence for TSM weakens materially on extended samples.
- Out-of-sample evaluations on ETF implementations report **negative test-period
  Sharpe ratios for nearly all parameterisations**.
- Roughly **40%** of TSM returns are attributable to time-varying exposure to
  business-cycle macro variables rather than to a standalone trend premium, and
  TSM performs *worse* than average following crises and cycle turns.

**Consequence for how this trial should be read at decision time:** the lane's
pre-registered claim is already the defensible one — **shallower drawdowns at a
bounded return cost (Goal B), explicitly not beat-SPY** — and nothing here
changes a bar or the crisis clause. What it changes is the reading of a *null*:
if the overlay fails to deliver a ≥3pp drawdown advantage, that is consistent
with the broader literature and should be reported as such, not as an
implementation problem to be tuned away. The spec stays frozen either way.

Standing on the record already: the overlay trails its own 60/40 control by
0.68pp over the first 52 days, on a window containing no drawdown for it to
protect against — which is exactly the crisis clause's territory and decides
nothing.
