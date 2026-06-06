# State of the Repo — Verified Inventory (2026-06-06)

Snapshot taken at re-entry after a ~1-month pause, from a full code-level audit
(not docs). Purpose: stop future sessions from re-discovering what already exists
and from rebuilding things that are already done.

## Branch state (reconciled 2026-06-06)

- **Canonical branch: `main`.** As of this date `main == lab/autonomous-rd == origin/main == origin/lab/autonomous-rd` (all at `4792d90`).
- `main` was a strict *ancestor* of `lab/autonomous-rd` (not a diverged fork). All the v12 / v13 / Portfolio-Intelligence work was on `lab`; `main` was fast-forwarded to it and pushed. Nothing was lost.
- **Deploy target: `main`.** The autonomous R&D loop (`lab/rd_loop.py`) auto-commits to `lab/autonomous-rd`; reset that branch to `main` before overnight runs so they share a base.

## What is REAL and built (verified)

Aegis is a production-grade quant platform, **not** a prototype. The following are
real, tested, and router-wired — do **not** rebuild them:

| Capability | File | Notes |
|---|---|---|
| Fundamentals | `services/fundamentals.py` | SEC EDGAR 10-K XBRL + Piotroski F-Score + ratios → `/api/stock/{t}/fundamentals` |
| A–F factor grades | `services/factor_grades.py` | Value/Growth/Profitability/Momentum/Revisions, sector-relative (Seeking-Alpha-Quant style) |
| Insider signal | `services/insider_trading.py` | Finnhub Form 4, 3+ insider cluster-buy, routine-vs-opportunistic filter |
| Fama-French | `services/factor_model.py` | FF5 + momentum, OLS t-stats, style labels |
| Earnings intel | `services/earnings_intelligence.py` | Beat rate, surprise trend, next-earnings countdown |
| Valuation | `services/valuation.py` | CAPE, ERP, Buffett indicator, composite 1–100 |
| Style box / peers | `services/style_box.py`, `relative_valuation.py` | Morningstar 3×3, peer percentiles |
| Screener | `routers/stock.py` | Ranks ~80 stocks on 40+ inputs (incl. fundamentals/insider/technicals/factor style), not just MC return |
| Provider registry | `services/providers/registry.py` | 6 providers (yfinance, Finnhub, FMP, Polygon, Alpha Vantage, FRED) with fallback chains |
| Portfolio Intelligence | `services/portfolio_intelligence/`, `routers/portfolio_intelligence.py` | 3 reference lanes ($100K each), walk-forward replay w/ look-ahead protection, comparator vs SPY/AGG/60-40, real-portfolio FF5 analyzer, SQLite, decision journal |

Validation that exists (`engine/validation/`): walk-forward expanding window,
5-fold purged CV with embargo (21/63/126d), conformal prediction, bootstrap CI,
Brier/BSS/AUC, lead-time & false-alarm metrics.

Tests: ~2,232 test functions across 113 files.

## Verified GAPS (the real work)

1. **Overfitting guards — ABSENT.** No PBO (Probability of Backtest Overfitting),
   no Deflated/Probabilistic Sharpe, no CPCV, no Harvey/Liu t-stat 3.0 hurdle.
   The autonomous R&D loop's quality gate checks only *code health*
   (tests/smells/imports/build, ratchet 0.55/0.70) — it has **no model-overfitting
   guard**, so it can surface overfit configs silently. Top priority given the
   "honest measurement" thesis. → Chunk 1.
2. **Factor grades not yet validated for predictive skill** (no Alphalens pass). → Chunk 2.
3. **PI not deployed** — reference lanes aren't running forward yet (no live track record). → Chunk 3.
4. **No per-stock LLM news layer** — DeepSeek is wired (`llm_analyzer.py`) and GDELT
   news exists, but the per-stock news→movement *flag* layer (measured against an
   OOS Brier baseline) is not built. → Chunk 4.

## On the old "Competitive Position & Build Plan" research brief

It is **outdated**. ~80% of its build plan (fundamentals, A–F grade, insider
detection, factor model, fundamentals-aware screener, provider integration) is
**already done**. Use it only for competitive *framing* (vs Seeking Alpha /
Simply Wall St / TipRanks; "transparency is the wedge"). Its one accurate gap was
the overfitting guards (its Phase 6).

## Optimus (separate repo, `C:\Users\mrthn\optimus`)

~40% complete. ingest/query/deprecate/audit are real + tested; already ingested
Aegis as a corpus. **MCP server not built** (empty `/mcp/`), so it cannot yet feed
context to Claude Code. Keep Aegis and Optimus **separate products** (Railway vs
laptop, public vs personal); Optimus reads Aegis, never fuses with it.

## Roadmap (chunked)

0. ✅ Reconcile + push + this doc.
1. Overfitting guards (PBO/DSR/CPCV) wired into the R&D acceptance gate.
2. Alphalens-validate existing `factor_grades`.
3. Deploy PI to Railway; start forward track record; survivorship-bias diagnostic.
4. DeepSeek per-stock news as a surprise *flag* (gate: improves OOS Brier?).
5. Optimus MCP server.
