# Survivorship-Availability Audit — 2026-06-16 (T7 feasibility, REJECT-on-free-data)

> Murat's roadmap put **T7 (point-in-time / delisted-inclusive universe) FIRST**,
> correctly: without it every selection backtest is fool's gold — it's why
> vol-managed momentum printed a false "PASS" (survivorship the DSR/PBO gate can't
> see). Before building a PIT-universe layer, this audit answers the prerequisite
> question with real values: **can our free data layer even supply the delisted
> names?** Artifact: `engine/research/survivorship_audit.py` →
> `survivorship_audit_results.json`. Reproducible: `python -m engine.research.survivorship_audit`.

## The test

Take 20 names that **were** in the S&P 500 and later left it (bankruptcy,
acquisition, failure), each with its known exit year. Fetch each via yfinance
(our actual price layer) and classify:

- **GONE** — no usable history (delisted → empty).
- **REUSED** — history exists but is inconsistent with the known exit: the symbol
  now belongs to a *different* company. **Injecting these is worse than dropping
  them** — it silently feeds an unrelated company's prices into the backtest under
  the dead name.
- **OK** — genuine delisted-entity history present.

Controls (AAPL/MSFT/XOM) must return clean, else the probe itself is broken.

## Result (2005→2026, yfinance)

| Verdict | Count | Meaning |
|---|---|---|
| **GONE** | **15 / 20** | LEH, BSC, YHOO, MON, CELG, AGN, XLNX, ATVI, TWTR, FRC, SIVB, PXD, SGEN, ABMD, RE — return nothing |
| **REUSED** | **4 / 20** | CFC, JAVA, EMC, SBNY — a *different* company now trades the symbol (e.g. "JAVA" history is 2021→2026, but Sun Micro was acquired in 2010) |
| **OK** | **1 / 20** | TWX only |

**Usable clean delisted history: 1/20 (5%). Controls: all clean.**

A second free source (stooq CSV) was probed and was unreachable in our environment
(even the AAPL control returned HTML, not data) — so it is not a usable fallback
here regardless. A genuinely survivorship-free universe requires paid vendor data
(CRSP / Norgate / Sharadar), which the project does not have.

## Conclusion (the part that reframes the roadmap)

**T7 as literally specified — a delisted-inclusive backtest universe — is NOT
achievable on free data.** yfinance doesn't just *miss* delisted names; for 20% it
silently substitutes an unrelated company. Therefore:

1. **No backtested absolute-alpha claim on our data is trustworthy.** Every
   `config.stock_universe` backtest (thematic, vol-momentum, the planned
   multi-factor model) is run on a basket of *known survivors*. The number is
   inflated by an unknown, uncorrectable amount.
2. **The DSR/PBO gate cannot rescue this.** It guards multiple-testing, not a
   biased universe. It will keep printing "PASS" on survivor-inflated Sharpes.
   This audit is the standing proof of *why* a backtest "PASS" is necessary but
   not sufficient.
3. **Selection signals must therefore be validated FORWARD, not by backtest.**
   The PIT store (`pit_observations`, schema v7) accrues data forward-only with an
   `observed_at` anti-leak field — it is survivorship- and look-ahead-safe *by
   construction*. The honest test of insider buys / estimate-revisions / 13F /
   multi-factor rank is **forward information coefficient on point-in-time data we
   collect from today**, and forward paper-lane NAV — never a historical backtest.

## What this means for items 3–6 of the roadmap

The user's items 3–5 were framed as "backtests through the DSR/PBO gate." This
audit says that framing cannot produce a defensible alpha claim. The corrected
form of each:

- **Insider opportunistic-buy (item 3), estimate-revisions flip (item 4),
  multi-factor rank (item 5):** register each as a **forward IC trial** in the
  experiment registry, scored on PIT data collected from today forward. A backtest
  may still be run as a *sanity / direction check*, but its result is explicitly
  stamped survivorship-contaminated and **cannot** arm a lane or be reported as
  edge. (`run_backtest` results should carry a `survivorship_warning`.)
- **Risk layer (item 6 — vol-management + ATR exits):** UNAFFECTED. These are
  universe-independent risk transforms (Sharpe-invariant leverage / trailing
  stops); their drawdown-control benefit is real regardless of survivorship, and
  they go forward as overlays as already planned.

## Status

- **TRIAL-T7 (delisted-inclusive universe on free data): REJECT.** Recorded in
  `NEGATIVE_RESULTS.md` §4. The audit script stays as a permanent guard: any future
  session tempted to trust a `stock_universe` backtest must run it first.
- Path forward is unchanged from the vol-momentum finding, now *proven* not
  asserted: **risk-control overlays + forward validation are the only honest
  edge; backtests on free data are direction-checks at most.**
