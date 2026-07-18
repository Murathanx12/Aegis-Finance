# TRIAL-MOM-BACKTEST — long-only 12-1 momentum vs SPY (offline direction-check)

**Registered:** 2026-07-18 (git commit timestamp = tamper evidence), BEFORE
any backtest run on the panel. **Type:** offline research trial — NOT a
forward clock (the six-forward-clock cap is untouched). **Status:** frozen,
awaiting panel completion + panel-quality gate.

## Why this signal (evidence basis, 2026-07-18 research sweep)
Cross-sectional 12-1 momentum is the ONLY stock-selection factor found with
both (a) surviving post-publication academic evidence (Chen-Zimmermann; decay
exists but the factor replicates) and (b) a live multi-billion-dollar
long-only fund beating SPY over 13 years (MTUM +1.5pp/yr since 2013). Every
other famous factor ETF examined (QVAL −5pp/yr, QMOM −3pp/yr, SYLD, VLUE,
USMV) LOST to SPY live. Full evidence:
`docs/research/BEAT_SPY_EVIDENCE_2026-07-18.md`, findings F-022/F-023.

## Hypothesis (falsifiable, honest prior stated)
Net-of-cost long-only 12-1 momentum on a survivorship-free US panel
2017→2026 achieves a Sharpe ≥ SPY's over the identical window. **Honest
prior: weak.** Realistic literature edge is +0.5–2pp/yr with 5–10% tracking
error; a 9-year window cannot statistically certify an edge that size, and
2017-2026 was a mega-cap-concentration regime hostile to any non-cap-weight
scheme (RSP trailed SPY ~3pp/yr). A PASS means "consistent with the
surviving literature," never "we found alpha."

## Primary metric (the ONE deciding number)
Net Sharpe (rf=0, daily, annualized) of the strategy minus net Sharpe of
SPY total-return over the identical window. Everything else — CAGR, maxDD,
turnover, RSP comparison — is reported, never deciding.

## Decision rule
- **PASS (direction-check):** strategy net Sharpe ≥ SPY Sharpe − 0.00 AND
  strategy maxDD ≤ 1.25 × SPY maxDD. Consequence: a momentum paper lane may
  be PROPOSED to Murat as a candidate forward trial (attended; requires his
  explicit decision to lift or reallocate the six-clock cap). Nothing arms
  automatically.
- **FAIL:** anything else. Consequence: logged in NEGATIVE_RESULTS.md, no
  lane proposal, momentum stays a component of the existing multi-factor
  forward IC trial only.
- **Evaluation:** ONE run of the frozen spec below. No re-runs with adjusted
  parameters; any second variant is a NEW registered trial that increments
  the cumulative count.
- **Panel-quality gate (contamination clause):** before evaluation, the
  panel must pass: (1) ≥80% of CRSP-style expected delisted coverage on a
  10-name 2017+ spot-check, (2) cross-check of 10 active tickers vs yfinance
  adjusted closes within 1%. Panel failure voids the trial UNRUN (recorded
  as void, not FAIL).

## Frozen parameters (may not be tuned)
- Panel: EODHD archive (active US common stocks + delisted, harvested
  2026-07-18) restricted to 2017-01-01 → 2026-06-30.
- Eligibility: top 1000 by trailing-63-day median dollar volume (price ×
  volume; size proxy computable from EOD data), price ≥ $5.
- Signal: total return from t−252 to t−21 trading days (12-1).
- Portfolio: top 50 by signal, equal weight, monthly rebalance (first
  trading day). Banding: a held name is kept while it remains in the top
  100; exits replaced by the highest-ranked non-held names.
- Costs: 20 bps per side on all turnover. Dividends: included via adjusted
  closes.
- Delisting handling: a held name that delists exits at its last available
  adjusted close minus 30% haircut if the delist reason is unknown
  (conservative default; bankruptcies often recover far less than last
  print).
- Benchmarks: SPY (deciding), RSP (reported context for concentration
  regime).

## What this rule may NOT do
- May not claim alpha, skill, or "beats the market" regardless of outcome.
- May not write anything into paper_nav or any forward record.
- May not arm, trade, or surface as a buy/sell signal.
- May not be re-run with different parameters under this trial ID.
- A PASS may not by itself create a forward lane — that is Murat's attended
  decision under the cap discipline.
