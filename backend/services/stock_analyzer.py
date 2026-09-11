"""
Aegis Finance — Individual Stock Analysis
============================================

Per-ticker projections using fundamental-aware Monte Carlo:
  1. Fetch price history + fundamentals from Yahoo Finance
  2. Shrink the historical drift toward the equity-premium prior
  3. Blend with the consensus target, mapped through the calibration table
     (2026-09-11: this step used to CAP the consensus at the cap tier's
     ceiling — see the long note below)
  4. Run jump-diffusion Monte Carlo, and report BOTH the 12-month and the
     5-year cross-sections of the same paths
  5. Attach the 52-week price target (`services/price_target.py`)

Usage:
    from backend.services.stock_analyzer import analyze_stock, analyze_stocks
"""

import logging
from typing import Optional

import numpy as np
import yfinance as yf

from backend.config import config
from backend.services.monte_carlo import simulate_paths
from backend.services.tail_risk import compute_tail_risk_metrics
from backend.services.prediction_confidence import score_prediction_confidence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# THE CAPS ARE GONE (roadmap O11, 2026-09-11). CORRECTIONS REPLACED THEM.
# ---------------------------------------------------------------------------
#
# `STOCK_CAGR_CAPS` was a per-cap-tier `(min_cagr, max_cagr)` pair — mega
# (0.04, 0.30), large (0.05, 0.35), mid (0.06, 0.40), small (0.08, 0.45) — and
# it was applied THREE times: to the shrunk historical drift, to the consensus
# 1-year upside BEFORE the 60/40 blend, and to the blend afterwards. The middle
# one was the defect Murat noticed:
#
#     analyst_annual = np.clip(analyst_1y_return, -0.30, max_cagr)
#
# A +49.8% consensus on NVDA and a +31% consensus entered the blend as the SAME
# +30%. That is not our model disagreeing with Wall Street; it is Wall Street's
# own number being truncated before it is used, and no amount of downstream
# machinery can recover information a clip has already thrown away.
#
# Murat, the same day: *"not caps or limits, but corrections on every mistake."*
# So the clip becomes a MAPPING: the raw upside goes through
# `price_target.apply_calibration`, a monthly-refit isotonic table of raw upside
# -> realised 12-month return by sector x vol x cap bucket, fit PIT on IBES
# history. With no fitted table the mapping is the IDENTITY and the payload says
# `identity_unfitted` — an identity that announces itself, never a silent clip.
#
# ONE ceiling survives, and only inside the path simulation:
# `monte_carlo.simulate_paths` clips every simulated PRICE at
# `config["simulation"]["max_5y_return"]` (+300%). That is a bound on a random
# walk's excursion, not on a forecast, and it is labelled as such in the payload
# (`mc_path_ceiling_pct`). The second copy of it — a `np.minimum` on the
# terminal prices in this module — was removed: it clipped an already-clipped
# array and existed only to make the cap look load-bearing twice.
#
# `config["stocks"]["cagr_caps"]` is deliberately left in config.py and read by
# nothing. Deleting it would make an old receipt's `capped_drift` unreadable;
# `test_price_target.py` asserts this module never reads it again.

# Stock universe — loaded from config.py (centralized)
_universe = config.get("stock_universe", {})
DEFAULT_WATCHLIST = _universe.get("default_watchlist", [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META",
    "TSLA", "JPM", "JNJ", "V", "UNH", "XOM",
])
SECTOR_STOCK_MAP = _universe.get("sector_stocks", {
    "Technology":       ["AAPL", "MSFT", "NVDA", "AVGO", "CRM"],
    "Healthcare":       ["UNH", "LLY", "JNJ", "ISRG", "VRTX"],
    "Financials":       ["JPM", "V", "MA", "GS", "BLK"],
    "Energy":           ["XOM", "CVX", "SLB", "OKE", "FSLR"],
    "Consumer Disc.":   ["AMZN", "TSLA", "HD", "NKE", "BKNG"],
    "Industrials":      ["CAT", "GE", "RTX", "UBER", "AXON"],
    "Communications":   ["META", "GOOGL", "NFLX", "DIS", "RBLX"],
    "Consumer Staples": ["COST", "PG", "KO", "WMT", "MNST"],
    "Materials":        ["LIN", "FCX", "NEM", "VMC"],
    "Utilities":        ["NEE", "VST", "CEG", "SO"],
    "Real Estate":      ["PLD", "AMT", "EQIX", "O"],
})


def _get_cap_tier(market_cap) -> str:
    if market_cap is None or market_cap <= 0:
        return "large"
    b = market_cap / 1e9
    if b > 200:
        return "mega"
    elif b > 10:
        return "large"
    elif b > 2:
        return "mid"
    else:
        return "small"


def select_stocks_from_sectors(sector_results: dict, n_stocks: int = 20) -> list[str]:
    """Data-driven stock selection from top-performing sectors."""
    if not sector_results:
        return DEFAULT_WATCHLIST[:n_stocks]

    ranked = sorted(
        sector_results.items(),
        key=lambda x: x[1].get("expected_total", x[1].get("expected_return", 0)),
        reverse=True,
    )
    selected = []

    for i, (sector_name, _) in enumerate(ranked):
        if sector_name not in SECTOR_STOCK_MAP:
            continue
        pool = SECTOR_STOCK_MAP[sector_name]
        picks = min(3, len(pool)) if i < 3 else min(2, len(pool)) if i < 7 else 1
        selected.extend(pool[:picks])
        if len(selected) >= n_stocks:
            break

    seen = set()
    return [t for t in selected if not (t in seen or seen.add(t))][:n_stocks]


def analyze_stock(
    ticker: str,
    forecast_days: int = 1260,
    risk_free_rate: float = config.get("risk_free_rate", 0.04),
    ml_crash_prob: float | None = None,
    hmm_state_means: Optional[np.ndarray] = None,
    hmm_regime_probs: Optional[np.ndarray] = None,
    hmm_state_vols: Optional[np.ndarray] = None,
    drift_severity: Optional[str] = None,
) -> Optional[dict]:
    """Analyze a single stock with fundamental-aware Monte Carlo."""
    max_5y_return = config["simulation"]["max_5y_return"]

    # ── Data fetch (expected to fail for bad tickers / network issues) ──
    from backend.services.data_fetcher import (
        RateLimited, fetch_ticker_history, fetch_ticker_info,
    )
    try:
        hist = fetch_ticker_history(ticker, period="5y")
        info = fetch_ticker_info(ticker)
    except RateLimited:
        raise  # provider throttling — callers must not read this as a bad ticker
    except Exception as e:
        logger.warning("%s: Data fetch failed — %s", ticker, e)
        return None

    if hist is None or hist.empty or len(hist) < 252:
        logger.warning("%s: Insufficient price history", ticker)
        return None

    # dropna: a NaN final Close row (yfinance under rate pressure / partial
    # sessions) made current_price + momentum_1m/3m NaN for EVERY ticker in
    # prod on 2026-07-26 — first killing the screener at int(confidence),
    # then 500ing the endpoint at JSON serialization. NaN rows carry no
    # information; price math runs on real closes only.
    prices = hist["Close"].dropna()
    if len(prices) < 252:
        logger.warning("%s: Insufficient non-NaN price history", ticker)
        return None
    current_price = float(prices.iloc[-1])
    if not np.isfinite(current_price) or current_price <= 0:
        logger.warning("%s: unpriceable (last close %r)", ticker, current_price)
        return None

    market_cap = info.get("marketCap", None)
    cap_tier = _get_cap_tier(market_cap)
    beta = info.get("beta", 1.0)
    if beta is None or beta <= 0:
        beta = 1.0
    analyst_target = info.get("targetMeanPrice", None)
    company_name = info.get("shortName", ticker)
    sector = info.get("sector", "Unknown")
    pe_ratio = info.get("trailingPE", None)

    returns = prices.pct_change().dropna()
    log_returns = np.log(1 + returns)
    hist_log_drift = float(log_returns.mean() * 252)  # log drift ≈ μ - 0.5σ²
    hist_sigma = float(returns.std() * np.sqrt(252))

    # Convert log drift to arithmetic expected return for consistent blending.
    # All blend components (prior, analyst targets) are arithmetic returns;
    # hist_log_drift is a log drift. Mixing them causes systematic drift bias.
    hist_arithmetic = float(np.exp(hist_log_drift + 0.5 * hist_sigma**2) - 1)

    # Bayesian shrinkage: blend historical drift toward long-run prior
    # More data → trust history more; less data → shrink toward prior
    # All values are now in arithmetic return space.
    shrinkage_cfg = config.get("stocks", {}).get("drift_shrinkage", {})
    prior = shrinkage_cfg.get("prior_equity_premium", 0.07)
    min_shrink = shrinkage_cfg.get("min_shrinkage", 0.25)
    max_shrink = shrinkage_cfg.get("max_shrinkage", 0.60)
    years_for_min = shrinkage_cfg.get("data_years_for_min", 5.0)

    data_years = len(returns) / 252.0
    # Linear interpolation: more years → less shrinkage
    shrinkage_weight = max_shrink - (max_shrink - min_shrink) * min(data_years / years_for_min, 1.0)
    shrunk_arithmetic = float(shrinkage_weight * prior + (1.0 - shrinkage_weight) * hist_arithmetic)

    # ── The consensus enters UNCLIPPED, through the calibration map ─────────
    from backend.services import price_target as PT

    _cal = PT.latest_calibration()
    _bucket = PT.bucket_key(sector, cap_tier, float(np.clip(hist_sigma, 0.0, 5.0)))
    _cohort = ((_cal or {}).get("buckets") or {}).get(_bucket)
    calibration_note = {"bucket": _bucket, "fitted": _cohort is not None}
    if analyst_target is not None and analyst_target > 0:
        analyst_1y_return = float(analyst_target / current_price - 1.0)
        mapped = PT.apply_calibration(analyst_1y_return, _cohort)
        analyst_annual = float(mapped["calibrated_upside"])
        calibration_note.update({"raw_consensus_upside": analyst_1y_return,
                                 "calibrated_consensus_upside": analyst_annual,
                                 "calibration": mapped["calibration"]})
        blended_arithmetic = 0.60 * shrunk_arithmetic + 0.40 * analyst_annual
    else:
        blended_arithmetic = shrunk_arithmetic
        calibration_note["calibration"] = "no_consensus_target"

    final_arithmetic = float(blended_arithmetic)
    if not np.isfinite(final_arithmetic):
        # A refusal, not a silent substitution: an infinite drift means one of
        # the inputs is broken and a MC run on it would look like a forecast.
        logger.warning("%s: blended drift is not finite (%r) — refusing", ticker,
                       blended_arithmetic)
        return None
    final_sigma = float(np.clip(hist_sigma, 0.15, 0.80))

    # Fit GARCH for better vol estimate and tail thickness
    # NOTE: must be computed BEFORE Ito correction so garch_vol is available
    garch_vol = None
    garch_nu = None
    garch_persistence = None
    try:
        from backend.models.garch import fit_garch
        garch_result = fit_garch(returns)
        if garch_result.success:
            garch_vol = garch_result.current_vol
            garch_nu = garch_result.nu
            garch_persistence = garch_result.alpha + garch_result.gamma * np.sqrt(2 / np.pi) + garch_result.beta
    except Exception as e:
        logger.debug("%s: GARCH fit skipped — %s", ticker, e)

    # Historical residuals for block bootstrap (preserves vol clustering)
    # Prefer GARCH-standardized residuals: returns / conditional_vol are ~iid
    # with uniform variance, so block bootstrap captures genuine tail events
    # rather than mixing high-vol and low-vol period returns.
    hist_residuals = None
    if garch_vol is not None:
        try:
            from backend.models.garch import get_standardized_residuals
            std_resid = get_standardized_residuals(garch_result, returns)
            if std_resid is not None and len(std_resid) > 50:
                hist_residuals = std_resid
        except Exception as e:
            logger.debug("%s: GARCH residuals failed — %s", ticker, e)
    if hist_residuals is None:
        hist_residuals = returns.values if len(returns) > 50 else None

    # Ito correction: convert arithmetic return to log drift for simulate_paths.
    # simulate_paths uses log_return = drift*dt + sigma*dW, so the drift must be
    # the log drift = ln(1+r) - 0.5*sigma^2 to produce correct E[S(T)].
    # CRITICAL: use the vol that simulate_paths will actually use as base_vol
    # (garch_vol if available, otherwise final_sigma). When garch_vol differs
    # from final_sigma, using final_sigma creates drift bias of
    # 0.5*(garch_vol^2 - final_sigma^2) per year — e.g., ~5.9% for NVDA.
    ito_sigma = garch_vol if garch_vol is not None else final_sigma
    final_mu = float(np.log(1 + final_arithmetic) - 0.5 * ito_sigma**2)

    # Beta-adjusted crash frequency: high-beta stocks crash more often
    base_crash_freq = config["simulation"]["jump_diffusion"]["annual_rate"]
    beta_adj_crash_freq = float(np.clip(base_crash_freq * beta, 0.02, 0.25))
    num_sims = config["simulation"]["num_simulations"]

    # Options-implied calibration: blend forward-looking options data into MC params
    # This is non-blocking — if options data is unavailable, MC runs unchanged
    mc_vol_override = garch_vol
    mc_crash_freq = beta_adj_crash_freq
    options_calibration = None
    try:
        from backend.services.options_calibrator import calibrate_mc_from_options, apply_calibration_to_mc_params
        from backend.services.options_intelligence import get_options_summary
        opts = get_options_summary(ticker)
        if opts and "error" not in opts:
            calibration = calibrate_mc_from_options(opts, garch_vol=garch_vol, ticker=ticker)
            if calibration.get("confidence", 0) > 0.2:
                applied = apply_calibration_to_mc_params(
                    calibration,
                    garch_vol=garch_vol,
                    base_crash_freq=beta_adj_crash_freq,
                )
                mc_vol_override = applied["garch_vol"]
                mc_crash_freq = applied["crash_freq"]
                options_calibration = calibration
                logger.info(
                    "%s: Options calibration applied (confidence=%.2f, vol=%.3f→%.3f, freq=%.3f→%.3f)",
                    ticker, calibration["confidence"],
                    garch_vol or 0, mc_vol_override or 0,
                    beta_adj_crash_freq, mc_crash_freq,
                )
    except (ImportError, KeyError, TypeError, ValueError, AttributeError) as e:
        logger.debug("%s: Options calibration skipped — %s", ticker, e)

    # Recompute Ito correction if options calibration changed the vol.
    # Without this, final_mu was computed with garch_vol but simulate_paths
    # receives mc_vol_override — causing drift bias of 0.5*(old² - new²)/yr.
    if mc_vol_override is not None and mc_vol_override != ito_sigma:
        final_mu = float(np.log(1 + final_arithmetic) - 0.5 * mc_vol_override**2)
        logger.debug(
            "%s: Ito correction recomputed for options-calibrated vol (%.3f→%.3f)",
            ticker, ito_sigma, mc_vol_override,
        )

    base_scenario = {"drift_adj": 0, "vol_mult": 1.0, "crash_mult": 1.0}
    paths = simulate_paths(
        current_price, final_mu, final_sigma,
        forecast_days, num_sims, mc_crash_freq, 0.0, base_scenario,
        ml_crash_prob=ml_crash_prob,
        garch_vol=mc_vol_override,
        garch_nu=garch_nu,
        garch_persistence=garch_persistence,
        historical_residuals=hist_residuals,
        hmm_state_means=hmm_state_means,
        hmm_regime_probs=hmm_regime_probs,
        hmm_state_vols=hmm_state_vols,
    )

    # The TERMINAL cross-section. `simulate_paths` has already clipped every
    # simulated price at `max_5y_return` (+300%), so the second `np.minimum`
    # that used to be here clipped an already-clipped array; it was removed
    # rather than kept, because a cap applied twice reads as two decisions.
    final_prices = paths[-1]
    exp_return = float(np.mean(final_prices) / current_price - 1) * 100
    med_return = float(np.median(final_prices) / current_price - 1) * 100

    # ── THE 12-MONTH CROSS-SECTION, FROM THE SAME PATHS ────────────────────
    #
    # DEFECT #1 of the price-target spec, closed here. The page used to print
    # the MEAN of the FIVE-YEAR terminal distribution beside a TWELVE-MONTH
    # consensus figure, and the frontend then took its fifth root to produce a
    # "1Y est." -- a 12-month number backed out of a 5-year path, which is
    # exactly what Murat rejected.
    #
    # The honest 12-month figure costs NOTHING: `paths[252]` IS the one-year
    # cross-section of the very same simulation. No root, no power, no division
    # by a horizon. When the run is shorter than a year the row says so rather
    # than annualising something else.
    _one_year = min(252, int(forecast_days))
    _y1 = paths[_one_year]
    exp_return_12m = float(np.mean(_y1) / current_price - 1) * 100
    med_return_12m = float(np.median(_y1) / current_price - 1) * 100
    p10_12m = float(np.percentile(_y1, 10) / current_price - 1) * 100
    p90_12m = float(np.percentile(_y1, 90) / current_price - 1) * 100
    p05 = float(np.percentile(final_prices, 5))
    p95 = float(np.percentile(final_prices, 95))
    prob_loss = float(np.mean(final_prices < current_price)) * 100

    running_peak = np.maximum.accumulate(paths, axis=0)
    drawdowns = (paths - running_peak) / running_peak
    avg_max_dd = float(np.mean(drawdowns.min(axis=0))) * 100

    sharpe = (final_arithmetic - risk_free_rate) / final_sigma if final_sigma > 0 else 0

    # Enriched data from yfinance (non-critical — failures return None per field).
    # Lazy handle: yf.Ticker() does no network I/O until an attribute is read.
    stock = yf.Ticker(ticker)
    analyst_targets = _get_analyst_targets(stock)
    recommendations = _get_recommendations(stock)
    holders = _get_holders(stock)
    news = _get_news(stock)
    earnings = _get_earnings(stock)
    price_history = _get_price_history(prices)
    key_stats = _get_key_stats(info, returns, current_price)
    peers = _get_sector_peers(sector, ticker)

    # Compute p10/p90 returns for data quality visibility
    p10_price = float(np.percentile(final_prices, 10))
    p90_price = float(np.percentile(final_prices, 90))
    p10_return = float(p10_price / current_price - 1) * 100
    p90_return = float(p90_price / current_price - 1) * 100

    # Tail risk analytics from historical returns
    tail_metrics = compute_tail_risk_metrics(returns.values, risk_free_rate)

    # Prediction confidence scoring (drift-aware uncertainty quantification)
    data_years = len(returns) / 252.0
    confidence = score_prediction_confidence(
        mc_p10_return=p10_return,
        mc_p90_return=p90_return,
        mc_median_return=med_return,
        garch_nu=garch_nu,
        garch_persistence=garch_persistence,
        data_years=data_years,
        drift_severity=drift_severity,
        beta=beta,
    )

    # Fama-French factor decomposition — reuse already-fetched prices to avoid
    # redundant yfinance call.  Non-blocking: failure returns None.
    factor_exposure = _get_factor_exposure(ticker, prices)

    result = {
        "ticker": ticker, "name": company_name, "sector": sector,
        "current_price": current_price,
        "market_cap": market_cap, "cap_tier": cap_tier,
        "beta": beta, "pe_ratio": pe_ratio,
        "analyst_target": analyst_target,
        "hist_drift": hist_arithmetic * 100,
        "shrinkage_weight": float(shrinkage_weight),
        # `capped_drift` keeps its NAME (old receipts and three callers read it)
        # and has lost its meaning: nothing caps it any more. `drift_calibration`
        # beside it says what happened to the consensus leg instead.
        "capped_drift": final_arithmetic * 100,
        "drift_calibration": calibration_note,
        "volatility": final_sigma * 100,
        # The 5-year terminal distribution, under BOTH names. `expected_return`
        # stays for every existing caller; the `_5y` alias exists so a page can
        # print a horizon it did not have to infer from a variable name.
        "expected_return": exp_return, "median_return": med_return,
        "expected_return_5y": exp_return, "median_return_5y": med_return,
        # The 12-month cross-section of the SAME paths. Comparable to a
        # consensus target on both dimensions: horizon AND statistic.
        "expected_return_12m": exp_return_12m,
        "median_return_12m": med_return_12m,
        "p10_return_12m": p10_12m, "p90_return_12m": p90_12m,
        "mc_horizon_years": round(int(forecast_days) / 252.0, 2),
        "mc_one_year_bar": _one_year,
        "mc_path_ceiling_pct": float(max_5y_return) * 100,
        "mc_path_ceiling_note": ("a bound on a simulated random walk's excursion, "
                                 "applied inside simulate_paths to every PRICE. It "
                                 "is not a cap on the forecast: the 52-week target "
                                 "lives in price_target_12m and passes through no "
                                 "clip at all."),
        "p05_price": p05, "p95_price": p95,
        "prob_loss_5y": prob_loss, "avg_max_drawdown": avg_max_dd,
        "sharpe": sharpe,
        # Fields expected by data_generator for MC quality measurement
        "mc_median_5y_return": med_return,
        "mc_p10_5y_return": p10_return,
        "mc_p90_5y_return": p90_return,
        # GARCH params for observability
        "garch_annual_vol": float(garch_vol * 100) if garch_vol is not None else None,
        "garch_nu": float(garch_nu) if garch_nu is not None else None,
        "garch_persistence": float(garch_persistence) if garch_persistence is not None else None,
        # ML crash prob used in this MC run (None if not provided)
        "ml_crash_prob": ml_crash_prob,
        # Tail risk analytics (Sortino, Omega, Calmar, etc.)
        "tail_risk": tail_metrics,
        # Prediction confidence (drift-aware uncertainty quantification)
        "prediction_confidence": confidence,
        "analyst_targets": analyst_targets,
        "recommendations": recommendations,
        "holders": holders,
        "news": news,
        "earnings": earnings,
        "price_history": price_history,
        # Daily-resolution momentum (avoids bug where weekly-sampled price_history
        # indices were treated as daily offsets — 22 weekly samples = 110 days)
        "momentum_1m": float((current_price / prices.iloc[-22] - 1) * 100) if len(prices) >= 22 else None,
        "momentum_3m": float((current_price / prices.iloc[-64] - 1) * 100) if len(prices) >= 64 else None,
        "key_stats": key_stats,
        "peers": peers,
        # Options-implied calibration (None if unavailable or low confidence)
        "options_calibration": {
            "confidence": options_calibration["confidence"],
            "implied_vol": options_calibration.get("implied_vol"),
            "jump_freq_mult": options_calibration.get("jump_freq_mult"),
            "jump_mag_adj": options_calibration.get("jump_mag_adj"),
        } if options_calibration else None,
        # Fama-French factor exposure (alpha, betas, style classification)
        "factor_exposure": factor_exposure,
    }

    # ── THE 52-WEEK TARGET (O11) ───────────────────────────────────────────
    #
    # Attached here so the screener gets it for free on 3,056 names: the
    # computation is PURE arithmetic over fields already fetched, with no extra
    # request. Leg A (the justified multiple) needs peer multiples, which this
    # path does not fetch -- it says so BY NAME rather than going quiet, and the
    # stock router recomputes with peers once `relative_valuation` has run.
    try:
        result["price_target_12m"] = PT.target_for_analysis(
            result, valuation=None, risk_free_rate=risk_free_rate, calibration=_cal)
    except Exception as e:  # noqa: BLE001 - a target is a feature, not a prerequisite
        logger.debug("%s: 52-week target skipped — %s", ticker, e)
        result["price_target_12m"] = {"available": False,
                                      "reason": f"{type(e).__name__}: {e}"}
    return result


def _get_analyst_targets(stock) -> Optional[dict]:
    """Extract analyst price targets from yfinance Ticker."""
    try:
        targets = stock.analyst_price_targets
        if targets is None:
            return None
        # Could be a DataFrame or dict-like
        if hasattr(targets, "to_dict"):
            t = targets.to_dict() if hasattr(targets, "to_dict") else {}
        elif isinstance(targets, dict):
            t = targets
        else:
            return None
        return {
            "current": t.get("current"),
            "low": t.get("low"),
            "mean": t.get("mean"),
            "median": t.get("median"),
            "high": t.get("high"),
        }
    except Exception as e:  # optional field — network/parse failures degrade to None
        logger.debug("%s: analyst targets extraction failed — %s", getattr(stock, 'ticker', '?'), e)
        return None


def _get_recommendations(stock) -> Optional[dict]:
    """Extract analyst recommendations summary."""
    try:
        rec = stock.recommendations
        if rec is None or (hasattr(rec, "empty") and rec.empty):
            return None
        # Get the most recent row
        if hasattr(rec, "iloc"):
            latest = rec.iloc[-1] if len(rec) > 0 else None
            if latest is None:
                return None
            return {
                "strongBuy": int(latest.get("strongBuy", 0)),
                "buy": int(latest.get("buy", 0)),
                "hold": int(latest.get("hold", 0)),
                "sell": int(latest.get("sell", 0)),
                "strongSell": int(latest.get("strongSell", 0)),
            }
        return None
    except Exception as e:  # optional field — network/parse failures degrade to None
        logger.debug("Recommendations extraction failed — %s", e)
        return None


def _get_holders(stock) -> Optional[dict]:
    """Extract major holders + top institutional holders."""
    try:
        result = {}

        # Major holders (% insider, % institution)
        major = stock.major_holders
        if major is not None and hasattr(major, "iloc"):
            for idx in range(len(major)):
                val = str(major.iloc[idx, 0]) if major.shape[1] > 0 else ""
                label = str(major.iloc[idx, 1]) if major.shape[1] > 1 else ""
                label_lower = label.lower()
                if "insider" in label_lower:
                    result["insider_pct"] = val
                elif "institution" in label_lower:
                    result["institution_pct"] = val

        # Top institutional holders
        inst = stock.institutional_holders
        if inst is not None and hasattr(inst, "iterrows") and not inst.empty:
            top = []
            for _, row in inst.head(10).iterrows():
                shares_raw = row.get("Shares")
                pct_raw = row.get("% Out")
                holder = {
                    "name": str(row.get("Holder", "")),
                    "shares": int(shares_raw) if shares_raw is not None and not (isinstance(shares_raw, float) and np.isnan(shares_raw)) and shares_raw > 0 else None,
                    "pct": float(pct_raw) if pct_raw is not None and not (isinstance(pct_raw, float) and np.isnan(pct_raw)) and pct_raw > 0 else None,
                }
                top.append(holder)
            result["top_holders"] = top

        return result if result else None
    except Exception as e:  # optional field — network/parse failures degrade to None
        logger.debug("Holders extraction failed — %s", e)
        return None


def _get_news(stock, max_items: int = 8) -> Optional[list]:
    """Extract recent news from yfinance."""
    try:
        raw = stock.news
        if not raw:
            return None
        items = []
        for item in raw[:max_items]:
            content = item.get("content", item)
            items.append({
                "title": content.get("title", item.get("title", "")),
                "publisher": content.get("provider", {}).get("displayName", "") if isinstance(content.get("provider"), dict) else item.get("publisher", ""),
                "link": content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else item.get("link", ""),
                "date": content.get("pubDate", item.get("providerPublishTime", "")),
            })
        return items if items else None
    except Exception as e:  # optional field — network/parse failures degrade to None
        logger.debug("News extraction failed — %s", e)
        return None


def _get_earnings(stock) -> Optional[dict]:
    """Extract upcoming earnings info."""
    try:
        import pandas as pd
        dates = stock.earnings_dates
        if dates is None or (hasattr(dates, "empty") and dates.empty):
            return None

        now = pd.Timestamp.now(tz="UTC") if dates.index.tz else pd.Timestamp.now()
        future = dates[dates.index >= now]
        next_date = str(future.index[0].date()) if len(future) > 0 else None

        estimate = None
        if len(future) > 0 and "EPS Estimate" in future.columns:
            est = future.iloc[0].get("EPS Estimate")
            if est is not None and not (isinstance(est, float) and np.isnan(est)):
                estimate = float(est)

        # Surprise history (last 4 quarters)
        past = dates[dates.index < now].head(4)
        surprises = []
        if "Surprise(%)" in past.columns:
            for _, row in past.iterrows():
                s = row.get("Surprise(%)")
                if s is not None and not (isinstance(s, float) and np.isnan(s)):
                    surprises.append(float(s))

        return {
            "next_date": next_date,
            "estimate": estimate,
            "surprise_history": surprises,
        }
    except Exception as e:  # optional field — network/parse failures degrade to None
        logger.debug("Earnings extraction failed — %s", e)
        return None


def _get_price_history(prices, sample_every: int = 5) -> Optional[list]:
    """Return sampled price history for charting (weekly resolution)."""
    try:
        if prices is None or len(prices) == 0:
            return None
        sampled = prices.iloc[::sample_every]
        return [
            {"date": str(d.date()) if hasattr(d, "date") else str(d), "price": round(float(v), 2)}
            for d, v in sampled.items()
        ]
    except (AttributeError, TypeError, ValueError) as e:
        logger.debug("Price history extraction failed — %s", e)
        return None


def _get_key_stats(info: dict, returns, current_price: float) -> Optional[dict]:
    """Extract key financial statistics from yfinance info dict."""
    try:
        stats = {}
        fields = {
            "trailingPE": "pe_trailing",
            "forwardPE": "pe_forward",
            "priceToBook": "price_to_book",
            "priceToSalesTrailing12Months": "price_to_sales",
            "enterpriseToEbitda": "ev_to_ebitda",
            "dividendYield": "dividend_yield",
            "payoutRatio": "payout_ratio",
            "debtToEquity": "debt_to_equity",
            "returnOnEquity": "roe",
            "returnOnAssets": "roa",
            "revenueGrowth": "revenue_growth",
            "earningsGrowth": "earnings_growth",
            "profitMargins": "profit_margin",
            "operatingMargins": "operating_margin",
            "freeCashflow": "free_cash_flow",
            "totalRevenue": "revenue",
            "totalDebt": "total_debt",
            "totalCash": "total_cash",
            "fiftyTwoWeekHigh": "high_52w",
            "fiftyTwoWeekLow": "low_52w",
            "fiftyDayAverage": "sma_50",
            "twoHundredDayAverage": "sma_200",
            # Added 2026-09-11 for the 52-week target's three legs. All of them
            # are already in the SAME `info` dict this function reads, so the
            # cost is zero requests: the old code simply never asked for them.
            "forwardEps": "forward_eps",
            "trailingEps": "trailing_eps",
            "sharesOutstanding": "shares_outstanding",
            "enterpriseValue": "enterprise_value",
            "bookValue": "book_value_per_share",
        }
        for yf_key, our_key in fields.items():
            val = info.get(yf_key)
            if val is not None:
                stats[our_key] = float(val) if isinstance(val, (int, float)) else val

        # Per-share figures the legs need. Computed, never guessed: a missing
        # share count leaves the field ABSENT rather than dividing by a default.
        shares = stats.get("shares_outstanding")
        if isinstance(shares, (int, float)) and shares > 0:
            for src, dst in (("revenue", "revenue_per_share"),
                             ("free_cash_flow", "fcf_per_share")):
                v = stats.get(src)
                if isinstance(v, (int, float)):
                    stats[dst] = float(v) / float(shares)

        # Add computed stats
        if len(returns) > 0:
            stats["return_1m"] = float(((1 + returns.iloc[-21:]).prod() - 1) * 100) if len(returns) >= 21 else None
            stats["return_3m"] = float(((1 + returns.iloc[-63:]).prod() - 1) * 100) if len(returns) >= 63 else None
            stats["return_6m"] = float(((1 + returns.iloc[-126:]).prod() - 1) * 100) if len(returns) >= 126 else None
            stats["return_1y"] = float(((1 + returns.iloc[-252:]).prod() - 1) * 100) if len(returns) >= 252 else None

        return stats if stats else None
    except (AttributeError, KeyError, TypeError, ValueError) as e:
        logger.debug("Key stats extraction failed — %s", e)
        return None


def _get_factor_exposure(ticker: str, prices) -> Optional[dict]:
    """Compute Fama-French factor decomposition reusing already-fetched prices.

    Returns a compact summary: alpha, factor loadings, style, R².
    Returns None on failure (non-blocking).
    """
    try:
        from backend.services.factor_model import decompose_stock
        result = decompose_stock(ticker, price_series=prices)
        if result is None:
            return None
        # Return compact version (drop per-factor p-values/t-stats for brevity)
        loadings = {}
        for name, detail in result.get("factors", {}).items():
            loadings[name] = detail["loading"]
        return {
            "alpha_annual": result["alpha_annual"],
            "alpha_significant": result.get("alpha_significant", False),
            "r_squared": result["r_squared"],
            "loadings": loadings,
            "style": result.get("style", {}),
            "residual_vol": result.get("residual_vol"),
        }
    except Exception as e:
        logger.debug("%s: factor exposure failed — %s", ticker, e)
        return None


def _get_sector_peers(sector: str, ticker: str) -> Optional[list]:
    """Return peer tickers in the same sector."""
    peers = SECTOR_STOCK_MAP.get(sector, [])
    return [p for p in peers if p != ticker][:6] or None


def analyze_stocks(
    tickers: Optional[list[str]] = None,
    forecast_days: int = 1260,
    risk_free_rate: float = config.get("risk_free_rate", 0.04),
) -> dict:
    """Analyze a portfolio of individual stocks."""
    if tickers is None:
        tickers = DEFAULT_WATCHLIST

    logger.info("Analyzing %d stocks...", len(tickers))
    results = {}

    for ticker in tickers:
        result = analyze_stock(ticker, forecast_days, risk_free_rate)
        if result is not None:
            results[ticker] = result

    logger.info("%d/%d stocks analyzed", len(results), len(tickers))
    return results
