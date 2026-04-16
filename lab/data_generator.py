"""
Aegis Finance - Lab Data Generator v4
Calls ACTUAL backend services with correct signatures.
Gracefully handles services that need DataFrame inputs by fetching data first.
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _save(output_dir, filename, data):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _random_tickers(n_mega=4, n_mid=4, seed=None):
    """Pick a mix of mega-cap + mid/small-cap tickers each run."""
    import random
    rng = random.Random(seed)

    mega = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B",
            "JPM", "V", "UNH", "JNJ", "XOM", "MA", "PG", "HD", "COST", "ABBV"]
    mid_small = [
        "CRWD", "DDOG", "NET", "SNOW", "PLTR", "ABNB", "DASH", "COIN",
        "RBLX", "U", "SOFI", "HOOD", "RIVN", "LCID", "MARA", "RIOT",
        "ENPH", "SEDG", "FSLR", "RUN",  # Energy
        "DKNG", "PENN", "MGM", "LVS",  # Gaming
        "ROKU", "TTD", "ZS", "OKTA",  # Tech mid
        "SMCI", "ARM", "MRVL", "ON",  # Semis
        "SQ", "AFRM", "UPST", "NU",  # Fintech
        "CELH", "MNST", "ELF", "BIRK",  # Consumer
        "HIMS", "OSCR", "DOCS", "TDOC",  # Health
        "UAL", "DAL", "LUV", "CCL",  # Travel
        "CLF", "FCX", "NEM", "GOLD",  # Materials/Mining
    ]

    picked_mega = rng.sample(mega, min(n_mega, len(mega)))
    picked_mid = rng.sample(mid_small, min(n_mid, len(mid_small)))
    return picked_mega + picked_mid


def _get_sp500_data(period="5y"):
    """Shared helper: fetch SP500 history (cached within a run)."""
    import yfinance as yf
    sp = yf.Ticker("^GSPC")
    return sp.history(period=period)


# Cache the market signal within a single run (used by both stock_analysis
# and signal_quality collectors to avoid redundant data fetches).
_cached_market_signal = None


def _compute_market_signal_for_lab() -> dict:
    """Compute market signal with REAL context — mirrors routers/stock.py logic.

    Wires: regime, risk score, crash model, momentum, drawdown, VIX,
    yield curve, external consensus, and HMM data for MC conditioning.
    """
    global _cached_market_signal
    if _cached_market_signal is not None:
        return _cached_market_signal

    import logging
    from backend.services.signal_engine import get_market_signal, compute_drawdown_pct
    from backend.services.data_fetcher import DataFetcher
    from backend.services.risk_scorer import build_risk_score
    from backend.services.regime_detector import detect_regimes, fit_hmm_for_mc

    logger = logging.getLogger(__name__)

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    data["Risk_Score"] = build_risk_score(data)
    _, regime = detect_regimes(data)

    vix = float(data["VIX"].iloc[-1]) if "VIX" in data.columns else 20.0
    sp500_1m = float(data["SP500"].pct_change(21).iloc[-1]) * 100
    sp500_3m = float(data["SP500"].pct_change(63).iloc[-1]) * 100

    # YTD return
    sp500_ytd = 0.0
    try:
        sp500_series = data["SP500"].dropna()
        now = sp500_series.index[-1]
        year_start = pd.Timestamp(year=now.year, month=1, day=1)
        prev_year_prices = sp500_series[sp500_series.index < year_start]
        if len(prev_year_prices) > 0:
            sp500_ytd = float((sp500_series.iloc[-1] / prev_year_prices.iloc[-1] - 1) * 100)
    except (KeyError, IndexError, ValueError, TypeError):
        pass

    yield_curve = None
    if "T10Y" in data.columns and "T3M" in data.columns:
        yield_curve = float(data["T10Y"].iloc[-1] - data["T3M"].iloc[-1])

    # Drawdown from 52-week high
    sp500_drawdown = None
    if "SP500" in data.columns:
        sp500_drawdown = compute_drawdown_pct(data["SP500"])

    # Crash model predictions + drift severity (share feature matrix)
    crash_3m = None
    crash_12m = None
    _drift_severity = None
    try:
        from backend.services.crash_model import CrashPredictor
        from backend.config import MODEL_DIR
        model_path = MODEL_DIR / "crash_model.pkl"
        if model_path.exists():
            from engine.training.features import build_feature_matrix
            predictor = CrashPredictor()
            predictor.load_model(str(model_path))
            fred_data = fetcher.fetch_fred_data()
            _feature_matrix = build_feature_matrix(data, fred_data=fred_data)
            available = [f for f in predictor.feature_names if f in _feature_matrix.columns]
            latest = _feature_matrix[available].iloc[[-1]]
            for h in predictor.lgb_models:
                prob = float(predictor.predict_proba(latest, h)[0]) * 100
                if h == "3m":
                    crash_3m = prob
                elif h == "12m":
                    crash_12m = prob
            # Drift detection (reuses feature matrix)
            try:
                from backend.services.drift_detector import DriftDetector
                _drift_report = DriftDetector.from_multi_scale(_feature_matrix)
                _drift_severity = _drift_report.get("severity")
            except Exception as e:
                logger.debug("Drift detection unavailable in lab: %s", e)
    except (ImportError, FileNotFoundError, ValueError, KeyError) as e:
        logger.debug("Crash model unavailable in lab signal: %s", e)

    # External consensus
    external = None
    try:
        from backend.services.external_validator import validate_external
        fred_data_ext = fetcher.fetch_fred_data()
        ext = validate_external(fred_data_ext, crash_12m / 100 if crash_12m else None, regime)
        external = ext.consensus_direction
    except (ImportError, KeyError, TypeError, ValueError) as e:
        logger.debug("External validation unavailable in lab: %s", e)

    # Systemic risk signal (turbulence + absorption ratio)
    _systemic_score = None
    try:
        from backend.services.systemic_risk import get_systemic_risk_signal
        _systemic_score = get_systemic_risk_signal(data)
    except Exception as e:
        logger.debug("Systemic risk signal unavailable in lab: %s", e)

    # VIX term structure signal
    _vts_signal = None
    try:
        from backend.services.regime_detector import get_vix_term_structure_state
        vts = get_vix_term_structure_state(data)
        if vts.get("available"):
            _vts_signal = vts.get("signal")
    except Exception as e:
        logger.debug("VIX term structure unavailable in lab: %s", e)

    sig = get_market_signal(
        crash_prob_3m=crash_3m,
        crash_prob_12m=crash_12m,
        regime=regime,
        risk_score=float(data["Risk_Score"].iloc[-1]),
        sp500_1m_return=sp500_1m,
        sp500_3m_return=sp500_3m,
        sp500_ytd_return=sp500_ytd,
        vix=vix,
        yield_curve=yield_curve,
        external_consensus=external,
        drawdown_pct=sp500_drawdown,
        drift_severity=_drift_severity,
        systemic_risk_score=_systemic_score,
        vix_term_structure_signal=_vts_signal,
    )
    # Attach raw values for downstream use by stock analysis / MC
    sig["_crash_3m_pct"] = crash_3m

    # Fit HMM for per-stock MC conditioning
    hmm_data = fit_hmm_for_mc(data)
    sig["_hmm_state_means"] = hmm_data["state_means"]
    sig["_hmm_regime_probs"] = hmm_data["regime_probs"]
    sig["_hmm_state_vols"] = hmm_data["state_vols"]

    _cached_market_signal = sig
    return sig


# ---------------------------------------------------------------------------
# 1. Market snapshot
# ---------------------------------------------------------------------------
def collect_market_snapshot(output_dir):
    import yfinance as yf

    indices = {
        "sp500": "^GSPC", "nasdaq": "^IXIC", "dow": "^DJI",
        "vix": "^VIX", "treasury_10y": "^TNX", "gold": "GC=F",
        "oil": "CL=F", "usd_index": "DX-Y.NYB",
    }

    snapshot = {}
    for name, symbol in indices.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if len(hist) > 0:
                current = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                snapshot[name] = {
                    "symbol": symbol,
                    "price": round(current, 2),
                    "change_1d_pct": round(((current - prev) / prev) * 100, 3),
                }
        except Exception as e:
            snapshot[name] = {"error": str(e)}

    _save(output_dir, "market_snapshot.json", snapshot)
    ok = len([v for v in snapshot.values() if "error" not in v])
    print(f"    [OK] {ok} indices fetched")
    return snapshot


# ---------------------------------------------------------------------------
# 2. Stock analysis — calls REAL analyze_stock(ticker) + signal wiring
# ---------------------------------------------------------------------------
def collect_stock_analysis(output_dir, cycle=1):
    TICKERS = _random_tickers(n_mega=4, n_mid=4, seed=cycle)
    results = {}
    errors = []

    try:
        from backend.services.stock_analyzer import analyze_stock
        from backend.services.signal_engine import get_stock_signal
    except ImportError as e:
        print(f"    [FAIL] Cannot import analyze_stock: {e}")
        return {}, [str(e)]

    # Compute market signal once (shared across all stock signals)
    market_sig = _compute_market_signal_for_lab()

    # Extract crash prob for MC modulation
    crash_3m_pct = market_sig.get("_crash_3m_pct")
    crash_prob_for_mc = crash_3m_pct / 100.0 if crash_3m_pct is not None else None

    for ticker in TICKERS:
        try:
            data = analyze_stock(
                ticker,
                ml_crash_prob=crash_prob_for_mc,
                hmm_state_means=market_sig.get("_hmm_state_means"),
                hmm_regime_probs=market_sig.get("_hmm_regime_probs"),
                hmm_state_vols=market_sig.get("_hmm_state_vols"),
            )
            if data is None:
                errors.append(f"{ticker}: returned None")
                print(f"    [FAIL] {ticker}: returned None")
                continue

            # Compute per-stock signal (mirrors routers/stock.py logic)
            fwd_pe = None
            key_stats = data.get("key_stats")
            if key_stats and "pe_forward" in key_stats:
                fwd_pe = key_stats["pe_forward"]

            # Per-stock risk factors for crash prob adjustment and signal
            stock_vol = data.get("volatility", 20.0) / 100.0
            stock_dd = None
            stock_mom_1m = None
            stock_mom_3m = None
            price_hist = data.get("price_history")
            if price_hist and len(price_hist) > 10:
                prices_arr = [p["price"] for p in price_hist]
                peak = max(prices_arr)
                current = prices_arr[-1]
                stock_dd = (current / peak - 1) * 100 if peak > 0 else 0.0
                if len(prices_arr) >= 22 and prices_arr[-22] > 0:
                    stock_mom_1m = (current / prices_arr[-22] - 1) * 100
                if len(prices_arr) >= 64 and prices_arr[-64] > 0:
                    stock_mom_3m = (current / prices_arr[-64] - 1) * 100

            # Per-stock crash probability
            from backend.services.signal_engine import adjust_crash_prob_for_stock
            stock_crash_prob = None
            if crash_prob_for_mc is not None:
                stock_crash_prob = adjust_crash_prob_for_stock(
                    crash_prob_for_mc, data.get("beta", 1.0), stock_vol,
                    stock_dd if stock_dd is not None else 0.0,
                )

            stock_sig = get_stock_signal(
                market_signal=market_sig,
                beta=data.get("beta", 1.0),
                analyst_target=data.get("analyst_target"),
                current_price=data.get("current_price", 0),
                pe_ratio=data.get("pe_ratio"),
                forward_pe=fwd_pe,
                stock_vol=stock_vol,
                drawdown_from_peak=stock_dd,
                stock_momentum_1m=stock_mom_1m,
                stock_momentum_3m=stock_mom_3m,
            )

            results[ticker] = {
                "ticker": ticker,
                "current_price": data.get("current_price"),
                "mc_median_5y": data.get("mc_median_5y_return"),
                "mc_p10_5y": data.get("mc_p10_5y_return"),
                "mc_p90_5y": data.get("mc_p90_5y_return"),
                "garch_vol": data.get("garch_annual_vol"),
                "garch_nu": data.get("garch_nu"),
                "crash_prob_3m": round(stock_crash_prob * 100, 2) if stock_crash_prob else crash_3m_pct,
                "signal_action": stock_sig["action"],
                "signal_score": stock_sig["composite_score"],
                "beta": data.get("beta"),
                "sector": data.get("sector"),
                "all_keys": list(data.keys()),
            }
            print(f"    [OK] {ticker}: ${data.get('current_price', '?')}, "
                  f"median_5y={data.get('mc_median_5y_return', '?')}%, "
                  f"signal={stock_sig['action']}")

        except Exception as e:
            errors.append(f"{ticker}: {type(e).__name__}: {e}")
            print(f"    [FAIL] {ticker}: {e}")

    _save(output_dir, "stock_analysis.json", results)
    return results, errors


# ---------------------------------------------------------------------------
# 3. SP500 Monte Carlo — calls run_monte_carlo with required args
# ---------------------------------------------------------------------------
def collect_sp500_mc(output_dir):
    try:
        import yfinance as yf
        from backend.services.monte_carlo import run_monte_carlo

        # Gather required inputs
        sp_hist = _get_sp500_data("5y")
        current_price = float(sp_hist["Close"].iloc[-1])

        # Get VIX
        vix_val = 20.0
        try:
            vix = yf.Ticker("^VIX").history(period="5d")
            if len(vix) > 0:
                vix_val = float(vix["Close"].iloc[-1])
        except (KeyError, IndexError, ValueError, TypeError):
            pass

        # Get yield curve (10Y-3M spread)
        yield_curve = 0.0
        try:
            tnx = yf.Ticker("^TNX").history(period="5d")
            irx = yf.Ticker("^IRX").history(period="5d")
            if len(tnx) > 0 and len(irx) > 0:
                yield_curve = float(tnx["Close"].iloc[-1]) - float(irx["Close"].iloc[-1])
        except (KeyError, IndexError, ValueError, TypeError):
            pass

        result = run_monte_carlo(
            current_price=current_price,
            current_regime="Neutral",
            risk_score=0.0,
            crash_freq=0.07,
            current_vix=vix_val,
            yield_curve=yield_curve,
            val_penalty=0.0,
        )

        if result is None:
            print("    [FAIL] run_monte_carlo returned None")
            return {"status": "failed"}

        summary = {
            "status": "ok",
            "result_keys": list(result.keys()),
            "current_price": current_price,
        }
        # Copy all numeric results
        for k, v in result.items():
            if isinstance(v, (int, float)):
                summary[k] = v

        _save(output_dir, "sp500_monte_carlo.json", summary)
        print(f"    [OK] SP500 MC: {len(result)} keys returned")
        return summary

    except Exception as e:
        print(f"    [FAIL] SP500 MC: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 4. Crash model — CrashPredictor.predict_all_horizons(features_df)
# ---------------------------------------------------------------------------
def collect_crash_calibration(output_dir):
    try:
        from backend.services.crash_model import CrashPredictor
        from engine.training.features import build_feature_matrix

        predictor = CrashPredictor()

        # Build current features
        try:
            features = build_feature_matrix()
            if features is not None and len(features) > 0:
                latest = features.iloc[[-1]]
                preds = predictor.predict_all_horizons(latest)
            else:
                print("    [SKIP] Could not build features for crash model")
                return {"status": "no_features"}
        except Exception as feat_err:
            # Fallback: try to get predictions via the router's approach
            print(f"    [WARN] Feature build failed ({feat_err}), trying simpler approach")
            return {"status": "feature_build_failed", "error": str(feat_err)}

        if preds is None:
            print("    [FAIL] predict_all_horizons returned None")
            return {"status": "predict_failed"}

        result = {
            "prob_3m": preds.get("crash_prob_3m"),
            "prob_6m": preds.get("crash_prob_6m"),
            "prob_12m": preds.get("crash_prob_12m"),
            "monotonic": (
                (preds.get("crash_prob_3m") or 0) <=
                (preds.get("crash_prob_6m") or 0) <=
                (preds.get("crash_prob_12m") or 1)
            ),
            "all_keys": list(preds.keys()),
        }

        _save(output_dir, "crash_calibration.json", result)
        p3 = preds.get("crash_prob_3m")
        p6 = preds.get("crash_prob_6m")
        p12 = preds.get("crash_prob_12m")
        if all(x is not None for x in [p3, p6, p12]):
            print(f"    [OK] Crash probs: 3m={p3:.1%}, 6m={p6:.1%}, 12m={p12:.1%}")
        else:
            print(f"    [OK] Crash preds returned (some horizons may be missing)")
        return result

    except Exception as e:
        print(f"    [FAIL] Crash calibration: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 5. Signal engine — full market context, then per-stock signals
# ---------------------------------------------------------------------------
def collect_signal_quality(output_dir, cycle=1):
    try:
        from backend.services.signal_engine import get_stock_signal
        import yfinance as yf

        # Market-level signal with REAL market context (not defaults)
        market_signal = _compute_market_signal_for_lab()

        # Per-stock signals need market_signal + stock-specific params
        TICKERS = _random_tickers(n_mega=6, n_mid=6, seed=cycle if 'cycle' in dir() else 1)
        stock_signals = {}
        actions = []
        scores = []

        for ticker_str in TICKERS:
            try:
                t = yf.Ticker(ticker_str)
                info = t.info or {}
                hist = t.history(period="1y")

                current_price = float(hist["Close"].iloc[-1]) if len(hist) > 0 else 0

                # Compute stock-level technical signals from price history
                _stock_dd = None
                _stock_mom_1m = None
                _stock_mom_3m = None
                if len(hist) > 10:
                    closes = hist["Close"].values
                    _peak = float(closes.max())
                    _curr = float(closes[-1])
                    _stock_dd = (_curr / _peak - 1) * 100 if _peak > 0 else 0.0
                    if len(closes) >= 22 and closes[-22] > 0:
                        _stock_mom_1m = (_curr / float(closes[-22]) - 1) * 100
                    if len(closes) >= 64 and closes[-64] > 0:
                        _stock_mom_3m = (_curr / float(closes[-64]) - 1) * 100

                sig = get_stock_signal(
                    market_signal=market_signal,
                    beta=float(info.get("beta", 1.0) or 1.0),
                    analyst_target=info.get("targetMeanPrice"),
                    current_price=current_price,
                    pe_ratio=info.get("trailingPE"),
                    forward_pe=info.get("forwardPE"),
                    drawdown_from_peak=_stock_dd,
                    stock_momentum_1m=_stock_mom_1m,
                    stock_momentum_3m=_stock_mom_3m,
                )
                if sig:
                    stock_signals[ticker_str] = {
                        "action": sig.get("action"),
                        "composite_score": sig.get("composite_score"),
                        "confidence": sig.get("confidence"),
                    }
                    actions.append(sig.get("action", "Hold"))
                    if sig.get("composite_score") is not None:
                        scores.append(sig["composite_score"])
            except Exception as e:
                stock_signals[ticker_str] = {"error": str(e)}

        action_counts = {}
        for a in actions:
            action_counts[a] = action_counts.get(a, 0) + 1

        score_spread = max(scores) - min(scores) if len(scores) >= 2 else 0

        # Strip internal keys before saving (not serializable / not useful)
        saveable_signal = {
            k: v for k, v in market_signal.items()
            if not k.startswith("_")
        }

        result = {
            "market_signal": saveable_signal,
            "stock_signals": stock_signals,
            "diversity": {
                "action_distribution": action_counts,
                "n_unique_actions": len(set(actions)),
                "score_spread": round(score_spread, 3),
                "score_std": round(float(np.std(scores)), 3) if scores else 0,
                "all_same_action": len(set(actions)) <= 1,
            },
            "n_tickers_with_signal": len([s for s in stock_signals.values() if "action" in s]),
            "n_tickers_failed": len([s for s in stock_signals.values() if "error" in s]),
        }

        _save(output_dir, "signal_quality.json", result)
        print(f"    [OK] Signals: {action_counts}, spread={score_spread:.2f}, "
              f"{result['n_tickers_with_signal']}/{len(TICKERS)} tickers")
        return result

    except Exception as e:
        print(f"    [FAIL] Signal quality: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 6. Regime + risk score — need SP500 DataFrame
# ---------------------------------------------------------------------------
def collect_regime_risk(output_dir):
    results = {}

    try:
        sp_hist = _get_sp500_data("5y")
        # Services expect a DataFrame with 'SP500' column (not 'Close')
        sp_df = pd.DataFrame({"SP500": sp_hist["Close"]})
        # Add VIX if available
        try:
            import yfinance as yf
            vix_hist = yf.Ticker("^VIX").history(period="5y")
            sp_df["VIX"] = vix_hist["Close"].reindex(sp_df.index, method="ffill")
        except (KeyError, IndexError, ValueError, TypeError):
            pass
    except Exception as e:
        print(f"    [FAIL] Cannot fetch SP500 data: {e}")
        _save(output_dir, "regime_risk.json", {"error": str(e)})
        return {"error": str(e)}

    try:
        from backend.services.regime_detector import detect_regimes
        regime_result = detect_regimes(sp_df)
        # Returns (pd.Series, str) tuple
        if isinstance(regime_result, tuple):
            regime_series, current_regime = regime_result
            results["regime"] = {
                "current": current_regime,
                "type": "tuple(Series, str)",
            }
            print(f"    [OK] Regime: {current_regime}")
        elif isinstance(regime_result, dict):
            results["regime"] = regime_result
            print(f"    [OK] Regime: {regime_result.get('regime', '?')}")
        else:
            results["regime"] = {"value": str(regime_result)[:200]}
            print(f"    [OK] Regime returned: {type(regime_result).__name__}")
    except Exception as e:
        results["regime"] = {"error": str(e)}
        print(f"    [FAIL] Regime: {e}")

    try:
        from backend.services.risk_scorer import build_risk_score
        risk_result = build_risk_score(sp_df)
        if isinstance(risk_result, pd.Series):
            latest = float(risk_result.iloc[-1])
            results["risk_score"] = {
                "current": round(latest, 3),
                "mean": round(float(risk_result.mean()), 3),
                "max": round(float(risk_result.max()), 3),
                "type": "Series",
            }
            print(f"    [OK] Risk score: {latest:.3f}")
        elif isinstance(risk_result, dict):
            results["risk_score"] = risk_result
            print(f"    [OK] Risk score: {risk_result}")
        else:
            results["risk_score"] = {"value": str(risk_result)[:200]}
            print(f"    [OK] Risk score returned: {type(risk_result).__name__}")
    except Exception as e:
        results["risk_score"] = {"error": str(e)}
        print(f"    [FAIL] Risk score: {e}")

    _save(output_dir, "regime_risk.json", results)
    return results


# ---------------------------------------------------------------------------
# 7. Sector analysis
# ---------------------------------------------------------------------------
def collect_sector_analysis(output_dir):
    try:
        import yfinance as yf
        from backend.services.sector_analyzer import analyze_sectors
        from backend import config

        raw_hist = _get_sp500_data("5y")
        # analyze_sectors expects DataFrame with 'SP500' column
        sp_hist = pd.DataFrame({"SP500": raw_hist["Close"]})

        # Get sector ETFs from config
        sector_etfs = config.config.get("data", {}).get("sectors", {
            "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
            "Energy": "XLE", "Industrials": "XLI", "Consumer Staples": "XLP",
            "Utilities": "XLU", "Materials": "XLB",
        })

        sector_data = {}
        for sector_name, etf_ticker in sector_etfs.items():
            try:
                h = yf.Ticker(etf_ticker).history(period="5y")
                if len(h) > 100:
                    sector_data[sector_name] = h["Close"]
            except (KeyError, IndexError, ValueError, TypeError):
                pass

        sectors = analyze_sectors(
            data=sp_hist, sector_data=sector_data, forecast_days=1260
        )

        if not sectors:
            print("    [FAIL] analyze_sectors returned empty")
            return {"status": "empty"}

        result = {
            "return_type": type(sectors).__name__,
            "n_sectors": len(sector_data),
        }

        # Extract summary depending on return type
        if isinstance(sectors, dict):
            result["keys"] = list(sectors.keys())[:20]
            # Try to find return values
            for key in ["sectors", "results", "data"]:
                if key in sectors and isinstance(sectors[key], (list, dict)):
                    result["inner_type"] = type(sectors[key]).__name__
                    break

        _save(output_dir, "sector_analysis.json", result)
        print(f"    [OK] Sector analysis: {type(sectors).__name__}, {len(sector_data)} sectors")
        return result

    except Exception as e:
        print(f"    [FAIL] Sector analysis: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 8. Portfolio engine
# ---------------------------------------------------------------------------
def collect_portfolio_test(output_dir):
    try:
        from backend.services.portfolio_engine import PortfolioEngine
        engine = PortfolioEngine()
        results = {}

        # Test build (no holdings needed)
        for profile in ["conservative", "moderate", "aggressive"]:
            try:
                r = engine.build_portfolio(risk_tolerance=profile)
                results[f"build_{profile}"] = {
                    "success": r is not None,
                    "keys": list(r.keys()) if isinstance(r, dict) else [],
                }
                print(f"    [OK] Build {profile}")
            except Exception as e:
                results[f"build_{profile}"] = {"error": str(e)}
                print(f"    [FAIL] Build {profile}: {e}")

        _save(output_dir, "portfolio_test.json", results)
        return results

    except Exception as e:
        print(f"    [FAIL] Portfolio engine: {e}")
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 9. Service health — import checks + safe callable checks
# ---------------------------------------------------------------------------
def collect_api_health(output_dir):
    health = {}

    # Import checks (safe — no execution)
    imports = [
        "backend.services.monte_carlo",
        "backend.services.stock_analyzer",
        "backend.services.sector_analyzer",
        "backend.services.portfolio_engine",
        "backend.services.crash_model",
        "backend.services.signal_engine",
        "backend.services.regime_detector",
        "backend.services.risk_scorer",
        "backend.services.shap_explainer",
        "backend.services.news_intelligence",
        "backend.services.sentiment_analyzer",
        "backend.services.data_quality",
        "backend.services.net_liquidity",
        "backend.services.return_model",
        "backend.services.external_validator",
        "backend.services.regime_validator",
        "backend.services.drift_detector",
        "backend.services.llm_analyzer",
        "backend.services.savings_calculator",
        "backend.services.factor_model",
        "backend.services.stress_testing",
        "backend.services.cross_sectional_momentum",
        "backend.services.economic_surprise",
        # v9 services
        "backend.services.liquidity_risk",
        "backend.services.copula_tail",
        "backend.services.covariance",
        "backend.services.portfolio_optimizer",
        "backend.services.insider_trading",
        "backend.services.trends_sentiment",
        "backend.services.survival_model",
        "backend.services.anomaly_detector",
        "backend.services.crash_timeline",
        "backend.services.attribution",
    ]

    for mod_path in imports:
        name = mod_path.split(".")[-1]
        try:
            __import__(mod_path)
            health[name] = {"status": "ok"}
        except Exception as e:
            health[name] = {"status": "error", "error": str(e)}

    ok = len([v for v in health.values() if v["status"] == "ok"])
    fail = len([v for v in health.values() if v["status"] == "error"])

    _save(output_dir, "api_health.json", health)
    print(f"    [OK] {ok} importable, {fail} failing")
    return health


# ---------------------------------------------------------------------------
# 10. Model validation metadata
# ---------------------------------------------------------------------------
def collect_validation_metrics(output_dir):
    model_path = REPO_ROOT / "backend" / "models" / "crash_model.pkl"
    if not model_path.exists():
        print("    [SKIP] No crash_model.pkl")
        return {"status": "no_model"}

    try:
        import pickle
        with open(model_path, "rb") as f:
            model_data = pickle.load(f)

        result = {
            "model_exists": True,
            "model_type": type(model_data).__name__,
        }
        if isinstance(model_data, dict):
            result["keys"] = list(model_data.keys())
            result["train_date"] = model_data.get("train_date")
            result["walk_forward_auc"] = model_data.get("walk_forward_auc")

        _save(output_dir, "validation_metrics.json", result)
        print(f"    [OK] Model metadata collected")
        return result
    except Exception as e:
        print(f"    [SKIP] {e}")
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 11. Drift detection — checks feature distribution shift since training
# ---------------------------------------------------------------------------
def collect_drift_check(output_dir):
    try:
        from backend.services.drift_detector import DriftDetector
        from backend.services.data_fetcher import DataFetcher
        from engine.training.features import build_feature_matrix

        fetcher = DataFetcher()
        data, _ = fetcher.fetch_market_data()
        fred_data = fetcher.fetch_fred_data()
        features = build_feature_matrix(data, fred_data=fred_data)

        if features is None or len(features) < 504:
            print("    [SKIP] Not enough data for drift check")
            return {"status": "insufficient_data"}

        # Rolling window: compare last 252 days against prior 504 days.
        # This detects *recent* distribution shifts, not "2000 vs 2020" drift
        # which is guaranteed on financial time series.
        report = DriftDetector.from_multi_scale(features)

        result = {
            "drift_detected": report["drift_detected"],
            "n_features_checked": report["n_features_checked"],
            "n_drifted": report["n_drifted"],
            "drift_pct": report["drift_pct"],
            "severity": report.get("effective_severity", report.get("severity", "unknown")),
            "reference_window": report.get("reference_window"),
            "inference_window": report.get("inference_window"),
            "drifted_features": report["drifted_features"][:10],
            "recent_stability": report.get("recent_stability"),
            "scale_used": report.get("scale_used"),
        }
        if "multi_scale" in report:
            result["multi_scale"] = report["multi_scale"]

        _save(output_dir, "drift_check.json", result)
        severity = report.get("severity", "unknown")
        status = severity.upper() if report["drift_detected"] else "OK"
        print(f"    [{status}] {report['n_drifted']}/{report['n_features_checked']} "
              f"features drifted ({report['drift_pct']:.0f}%) — severity: {severity}")
        return result

    except Exception as e:
        print(f"    [FAIL] Drift check: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 12. Options intelligence snapshot
# ---------------------------------------------------------------------------
def collect_options_intelligence(output_dir, cycle):
    """Collect options-implied signals for a few tickers to benchmark the new service."""
    try:
        from backend.services.options_intelligence import get_vix_term_structure

        result = {}

        # VIX term structure
        vix_ts = get_vix_term_structure()
        result["vix_term_structure"] = vix_ts
        if "error" not in vix_ts:
            print(f"    [OK] VIX term: {vix_ts.get('structure', '?')}")
        else:
            print(f"    [WARN] VIX term: {vix_ts.get('error')}")

        # Options summary for a couple of tickers (lightweight)
        tickers_to_check = ["SPY", "AAPL"]
        from backend.services.options_intelligence import get_options_summary
        for ticker in tickers_to_check:
            try:
                summary = get_options_summary(ticker)
                sig = summary.get("signal", {})
                result[f"options_{ticker}"] = {
                    "iv_skew": summary.get("iv_skew"),
                    "put_call_ratio": summary.get("put_call_volume_ratio"),
                    "iv_rank": summary.get("iv_rank"),
                    "signal_score": sig.get("score"),
                    "signal_sentiment": sig.get("sentiment"),
                }
                print(f"    [OK] {ticker} options: skew={summary.get('iv_skew', '?')}, "
                      f"P/C={summary.get('put_call_volume_ratio', '?')}, "
                      f"signal={sig.get('sentiment', '?')}")
            except Exception as e:
                result[f"options_{ticker}"] = {"error": str(e)}
                print(f"    [WARN] {ticker} options: {e}")

        _save(output_dir, "options_intelligence.json", result)
        return result

    except Exception as e:
        print(f"    [FAIL] Options intelligence: {e}")
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 13. Code quality metrics
# ---------------------------------------------------------------------------
def collect_systemic_risk(output_dir):
    """Collect turbulence index and absorption ratio."""
    try:
        from backend.services.data_fetcher import DataFetcher
        from backend.services.systemic_risk import compute_systemic_risk

        fetcher = DataFetcher()
        data, _ = fetcher.fetch_market_data()
        result = compute_systemic_risk(data)
        _save(output_dir, "systemic_risk.json", result)
        turb = result.get("turbulence_current")
        ar = result.get("absorption_ratio_current")
        stress = result.get("systemic_stress")
        print(f"    [OK] turbulence={turb}, AR={ar}, stress={stress}")
        return result
    except Exception as e:
        _save(output_dir, "systemic_risk.json", {"error": str(e)})
        print(f"    [ERR] {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# 14. Factor model snapshot
# ---------------------------------------------------------------------------
def collect_factor_model(output_dir):
    """Collect factor decomposition for a few key tickers."""
    try:
        from backend.services.factor_model import decompose_stock
        results = {}
        for ticker in ["AAPL", "JPM", "XOM"]:
            try:
                decomp = decompose_stock(ticker, lookback_days=504)
                if decomp:
                    results[ticker] = {
                        "r_squared": decomp["r_squared"],
                        "alpha_annual": decomp["alpha_annual"],
                        "market_beta": decomp["factors"]["Mkt-RF"]["loading"],
                        "style": decomp["style"],
                    }
                    print(f"    [OK] {ticker}: R2={decomp['r_squared']:.2f}, "
                          f"beta={decomp['factors']['Mkt-RF']['loading']:.2f}, "
                          f"alpha={decomp['alpha_annual']:.1%}")
                else:
                    results[ticker] = {"status": "no_data"}
            except Exception as e:
                results[ticker] = {"error": str(e)}
                print(f"    [WARN] {ticker} factors: {e}")

        _save(output_dir, "factor_model.json", results)
        return results
    except Exception as e:
        print(f"    [FAIL] Factor model: {e}")
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 15. Economic surprise index
# ---------------------------------------------------------------------------
def collect_economic_surprise(output_dir):
    """Collect economic surprise index."""
    try:
        from backend.services.economic_surprise import compute_surprise_index
        result = compute_surprise_index()
        if result:
            _save(output_dir, "economic_surprise.json", result)
            print(f"    [OK] Eco surprise: {result['composite_score']:.3f} ({result['signal']}), "
                  f"trend={result['trend']}")
            return result
        else:
            print("    [SKIP] Economic surprise returned None")
            return {"status": "no_data"}
    except Exception as e:
        print(f"    [FAIL] Economic surprise: {e}")
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 16. Liquidity risk snapshot
# ---------------------------------------------------------------------------
def collect_liquidity_snapshot(output_dir):
    """Collect liquidity metrics for a few key tickers."""
    try:
        from backend.services.liquidity_risk import compute_liquidity_metrics
        results = {}
        for ticker in ["AAPL", "NVDA", "COIN"]:
            try:
                metrics = compute_liquidity_metrics(ticker)
                if metrics:
                    results[ticker] = {
                        "score": metrics["score"]["composite"],
                        "tier": metrics["score"]["tier"],
                        "amihud": metrics["metrics"]["amihud_illiquidity"],
                        "avg_dv_mm": metrics["metrics"]["avg_dollar_volume_mm"],
                    }
                    print(f"    [OK] {ticker}: score={metrics['score']['composite']:.0f} "
                          f"({metrics['score']['tier']})")
            except Exception as e:
                results[ticker] = {"error": str(e)}
                print(f"    [WARN] {ticker}: {e}")

        _save(output_dir, "liquidity_snapshot.json", results)
        return results
    except Exception as e:
        print(f"    [FAIL] Liquidity: {e}")
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 17. Copula tail dependence
# ---------------------------------------------------------------------------
def collect_copula_snapshot(output_dir):
    """Fit copulas to key asset pairs."""
    try:
        from backend.services.copula_tail import analyze_pair_copula
        pairs = [("AAPL", "MSFT"), ("SPY", "GLD")]
        results = {}
        for a, b in pairs:
            try:
                result = analyze_pair_copula(a, b, lookback_days=504)
                if result:
                    td = result.get("tail_dependence", {})
                    results[f"{a}_{b}"] = {
                        "best_copula": result["copula"]["selection"],
                        "tail_lower": td.get("lower"),
                        "pearson": result["correlation"]["pearson"],
                    }
                    print(f"    [OK] {a}/{b}: {result['copula']['selection']}, "
                          f"tail_L={td.get('lower', '?'):.3f}")
            except Exception as e:
                results[f"{a}_{b}"] = {"error": str(e)}
                print(f"    [WARN] {a}/{b}: {e}")

        _save(output_dir, "copula_snapshot.json", results)
        return results
    except Exception as e:
        print(f"    [FAIL] Copula: {e}")
        return {"status": "error", "error": str(e)}


def collect_code_metrics(output_dir):
    import subprocess as sp
    result = {}

    # Count tests
    try:
        test_dir = REPO_ROOT / "backend" / "tests"
        test_files = list(test_dir.glob("test_*.py"))
        total = sum(f.read_text(encoding="utf-8").count("def test_") for f in test_files)
        result["test_count"] = {"files": len(test_files), "functions": total}
    except Exception as e:
        result["test_count"] = {"error": str(e)}

    # Code smells
    smells = []
    for py_file in (REPO_ROOT / "backend" / "services").glob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")
            n_broad = sum(1 for l in lines if "except:" in l or "except Exception:" in l)
            if n_broad > 3:
                smells.append(f"{py_file.name}: {n_broad} broad excepts")
            n_fillna = sum(1 for l in lines if "fillna(0)" in l)
            if n_fillna > 0:
                smells.append(f"{py_file.name}: {n_fillna} fillna(0) (banned)")
            n_seed = sum(1 for l in lines if "np.random.seed" in l)
            if n_seed > 0:
                smells.append(f"{py_file.name}: {n_seed} legacy np.random.seed()")
        except (OSError, UnicodeDecodeError):
            pass

    result["code_smells"] = smells
    result["n_smells"] = len(smells)

    _save(output_dir, "code_metrics.json", result)
    tests = result.get("test_count", {}).get("functions", "?")
    print(f"    [OK] {tests} tests, {len(smells)} code smells")
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_engine_data_collection(output_dir, cycle):
    global _cached_market_signal
    _cached_market_signal = None  # Fresh signal each cycle

    results = {
        "cycle": cycle,
        "timestamp": datetime.now().isoformat(),
        "data_sources": [],
        "errors": [],
    }
    os.makedirs(output_dir, exist_ok=True)

    collectors = [
        ("market_snapshot", "Fetching market data", lambda d: collect_market_snapshot(d)),
        ("stock_analysis", "Running REAL stock analysis", lambda d: collect_stock_analysis(d, cycle)),
        ("sp500_mc", "Running REAL SP500 Monte Carlo", lambda d: collect_sp500_mc(d)),
        ("crash_calibration", "Measuring crash model calibration", lambda d: collect_crash_calibration(d)),
        ("signal_quality", "Measuring signal differentiation", lambda d: collect_signal_quality(d, cycle)),
        ("regime_risk", "Checking regime + risk score", lambda d: collect_regime_risk(d)),
        ("sector_analysis", "Running REAL sector analysis", lambda d: collect_sector_analysis(d)),
        ("portfolio_test", "Testing portfolio engine", lambda d: collect_portfolio_test(d)),
        ("api_health", "Checking service health", lambda d: collect_api_health(d)),
        ("validation_metrics", "Collecting model metadata", lambda d: collect_validation_metrics(d)),
        ("drift_check", "Checking feature drift", lambda d: collect_drift_check(d)),
        ("options_intelligence", "Checking options signals", lambda d: collect_options_intelligence(d, cycle)),
        ("systemic_risk", "Computing systemic risk indicators", lambda d: collect_systemic_risk(d)),
        ("factor_model", "Running factor decomposition", lambda d: collect_factor_model(d)),
        ("economic_surprise", "Computing economic surprise index", lambda d: collect_economic_surprise(d)),
        ("liquidity_snapshot", "Measuring liquidity risk", lambda d: collect_liquidity_snapshot(d)),
        ("copula_snapshot", "Fitting copula tail models", lambda d: collect_copula_snapshot(d)),
        ("code_metrics", "Measuring code quality", lambda d: collect_code_metrics(d)),
    ]

    for i, (name, label, collector) in enumerate(collectors, 1):
        print(f"  [{i}/{len(collectors)}] {label}...")
        try:
            result = collector(output_dir)
            if isinstance(result, tuple):
                data, errs = result
                results["errors"].extend(errs)
            results["data_sources"].append(name)
        except Exception as e:
            results["errors"].append(f"{name}: {type(e).__name__}: {e}")
            print(f"    [FAIL] {name}: {e}")

    with open(os.path.join(output_dir, "run_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n  Data generation complete: {len(results['data_sources'])} sources, "
          f"{len(results['errors'])} errors")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cycle", type=int, default=1)
    args = parser.parse_args()
    run_engine_data_collection(args.output_dir, args.cycle)
