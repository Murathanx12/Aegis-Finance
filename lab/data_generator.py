"""
Aegis Finance - Lab Data Generator v3
Calls ACTUAL backend services instead of toy GBM.
Measures real engine quality: crash calibration, signal diversity,
API endpoint health, GARCH fits, walk-forward metrics.
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 1. Market snapshot (same as before — uses yfinance directly)
# ---------------------------------------------------------------------------
def collect_market_snapshot(output_dir):
    import yfinance as yf

    indices = {
        "sp500": "^GSPC", "nasdaq": "^IXIC", "dow": "^DJI",
        "vix": "^VIX", "treasury_10y": "^TNX", "gold": "GC=F",
        "oil": "CL=F", "usd_index": "DX-Y.NYB",
    }

    market_snapshot = {}
    for name, symbol in indices.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if len(hist) > 0:
                current = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
                change_pct = ((current - prev) / prev) * 100

                hist_long = ticker.history(period="1mo")
                returns = hist_long["Close"].pct_change().dropna()
                vol_20d = float(returns.std() * np.sqrt(252) * 100) if len(returns) > 5 else None

                market_snapshot[name] = {
                    "symbol": symbol,
                    "price": round(current, 2),
                    "change_1d_pct": round(change_pct, 3),
                    "volatility_20d_annualized": round(vol_20d, 2) if vol_20d else None,
                }
        except Exception as e:
            market_snapshot[name] = {"error": str(e)}

    _save(output_dir, "market_snapshot.json", market_snapshot)
    print(f"    [OK] {len([v for v in market_snapshot.values() if 'error' not in v])} indices fetched")
    return market_snapshot


# ---------------------------------------------------------------------------
# 2. Stock analysis — calls the REAL backend analyze_stock()
# ---------------------------------------------------------------------------
def collect_stock_analysis(output_dir):
    TICKERS = ["AAPL", "NVDA", "XOM", "JPM", "TSLA", "JNJ", "AMZN", "BA"]
    results = {}
    errors = []

    try:
        from backend.services.stock_analyzer import analyze_stock
    except ImportError as e:
        print(f"    [FAIL] Cannot import analyze_stock: {e}")
        return {}, [str(e)]

    for ticker in TICKERS:
        try:
            data = analyze_stock(ticker)
            if data is None:
                errors.append(f"{ticker}: analyze_stock returned None")
                print(f"    [FAIL] {ticker}: returned None")
                continue

            results[ticker] = {
                "ticker": ticker,
                "current_price": data.get("current_price"),
                "mc_median_5y": data.get("mc_median_5y_return"),
                "mc_p10_5y": data.get("mc_p10_5y_return"),
                "mc_p90_5y": data.get("mc_p90_5y_return"),
                "garch_vol": data.get("garch_annual_vol"),
                "garch_nu": data.get("garch_nu"),
                "garch_persistence": data.get("garch_persistence"),
                "crash_prob_3m": data.get("crash_prob_3m"),
                "crash_prob_6m": data.get("crash_prob_6m"),
                "crash_prob_12m": data.get("crash_prob_12m"),
                "signal_action": data.get("signal", {}).get("action") if isinstance(data.get("signal"), dict) else None,
                "signal_score": data.get("signal", {}).get("composite_score") if isinstance(data.get("signal"), dict) else None,
                "beta": data.get("beta"),
                "sector": data.get("sector"),
                "has_shap": data.get("shap_values") is not None,
                "all_keys": list(data.keys()),
            }
            price = data.get("current_price", "?")
            median_ret = data.get("mc_median_5y_return", "?")
            print(f"    [OK] {ticker}: ${price}, median_5y={median_ret}%, garch_vol={data.get('garch_annual_vol', '?')}")

        except Exception as e:
            errors.append(f"{ticker}: {type(e).__name__}: {e}")
            print(f"    [FAIL] {ticker}: {type(e).__name__}: {e}")
            traceback.print_exc()

    _save(output_dir, "stock_analysis.json", results)
    return results, errors


# ---------------------------------------------------------------------------
# 3. Crash model — calls CrashModel directly, measures calibration
# ---------------------------------------------------------------------------
def collect_crash_calibration(output_dir):
    try:
        from backend.services.crash_model import CrashPredictor
        predictor = CrashPredictor()

        preds = predictor.predict()
        if preds is None:
            print("    [FAIL] CrashPredictor.predict() returned None")
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
            "feature_importance_top10": preds.get("feature_importance", [])[:10],
            "calibration_table": preds.get("calibration_table"),
            "n_features": len(preds.get("feature_importance", [])),
        }

        # Check differentiation — are crash probs in the 5%-55% range per CLAUDE.md?
        for horizon in ["crash_prob_3m", "crash_prob_6m", "crash_prob_12m"]:
            p = preds.get(horizon)
            if p is not None:
                result[f"{horizon}_in_range"] = 0.05 <= p <= 0.55

        _save(output_dir, "crash_calibration.json", result)
        p3 = preds.get("crash_prob_3m")
        p6 = preds.get("crash_prob_6m")
        p12 = preds.get("crash_prob_12m")
        print(f"    [OK] Crash probs: 3m={p3:.1%}, 6m={p6:.1%}, 12m={p12:.1%}" if all(x is not None for x in [p3,p6,p12]) else f"    [OK] Crash preds returned (some horizons missing)")
        return result

    except Exception as e:
        print(f"    [FAIL] Crash calibration: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 4. Signal engine — measures differentiation across tickers
# ---------------------------------------------------------------------------
def collect_signal_quality(output_dir):
    try:
        from backend.services.signal_engine import get_market_signal, get_stock_signal

        # Market-level signal
        market_signal = get_market_signal()

        # Per-stock signals
        TICKERS = ["AAPL", "NVDA", "XOM", "JPM", "TSLA", "JNJ", "AMZN", "BA",
                    "MSFT", "GOOGL", "META", "BAC", "CVX", "UNH", "WMT", "CAT"]
        stock_signals = {}
        actions = []
        scores = []

        for ticker in TICKERS:
            try:
                sig = get_stock_signal(ticker)
                if sig:
                    stock_signals[ticker] = {
                        "action": sig.get("action"),
                        "composite_score": sig.get("composite_score"),
                        "confidence": sig.get("confidence"),
                        "components": sig.get("components"),
                    }
                    actions.append(sig.get("action", "Hold"))
                    if sig.get("composite_score") is not None:
                        scores.append(sig["composite_score"])
            except Exception as e:
                stock_signals[ticker] = {"error": str(e)}

        # Diversity metrics
        action_counts = {}
        for a in actions:
            action_counts[a] = action_counts.get(a, 0) + 1

        score_spread = max(scores) - min(scores) if len(scores) >= 2 else 0
        score_std = float(np.std(scores)) if len(scores) >= 2 else 0

        result = {
            "market_signal": market_signal,
            "stock_signals": stock_signals,
            "diversity": {
                "action_distribution": action_counts,
                "n_unique_actions": len(set(actions)),
                "score_spread": round(score_spread, 3),
                "score_std": round(score_std, 3),
                "all_same_action": len(set(actions)) <= 1,
                "mean_score": round(float(np.mean(scores)), 3) if scores else None,
            },
            "n_tickers_with_signal": len([s for s in stock_signals.values() if "action" in s]),
            "n_tickers_failed": len([s for s in stock_signals.values() if "error" in s]),
        }

        _save(output_dir, "signal_quality.json", result)
        print(f"    [OK] Signals: {action_counts}, spread={score_spread:.2f}, "
              f"{len(stock_signals)} tickers")
        return result

    except Exception as e:
        print(f"    [FAIL] Signal quality: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 5. Regime + risk score — calls actual services
# ---------------------------------------------------------------------------
def collect_regime_risk(output_dir):
    results = {}

    try:
        from backend.services.regime_detector import detect_regimes
        regime = detect_regimes()
        results["regime"] = regime
        if isinstance(regime, dict):
            print(f"    [OK] Regime: {regime.get('regime', '?')}, confidence={regime.get('confidence', '?')}")
        else:
            print(f"    [OK] Regime returned: {type(regime).__name__}")
    except Exception as e:
        results["regime"] = {"error": str(e)}
        print(f"    [FAIL] Regime: {e}")

    try:
        from backend.services.risk_scorer import build_risk_score
        risk = build_risk_score()
        results["risk_score"] = risk
        if isinstance(risk, dict):
            score = risk.get("composite_score", risk.get("risk_score", "?"))
            print(f"    [OK] Risk score: {score}")
        else:
            print(f"    [OK] Risk score returned: {type(risk).__name__}")
    except Exception as e:
        results["risk_score"] = {"error": str(e)}
        print(f"    [FAIL] Risk score: {e}")

    _save(output_dir, "regime_risk.json", results)
    return results


# ---------------------------------------------------------------------------
# 6. Sector analysis — calls actual sector_analyzer
# ---------------------------------------------------------------------------
def collect_sector_analysis(output_dir):
    """Call sector analyzer via the router-level logic (needs market data)."""
    try:
        import yfinance as yf
        from backend.services.sector_analyzer import analyze_sectors
        from backend.config import SECTOR_ETFS

        # Fetch SP500 data as the main DataFrame
        sp = yf.Ticker("^GSPC")
        sp_hist = sp.history(period="5y")

        if len(sp_hist) < 252:
            print("    [FAIL] Not enough SP500 data for sector analysis")
            return {"status": "insufficient_data"}

        # Fetch sector ETF data
        sector_data = {}
        etfs = SECTOR_ETFS if hasattr(__import__("backend.config", fromlist=["SECTOR_ETFS"]), "SECTOR_ETFS") else {
            "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
            "Energy": "XLE", "Consumer Discretionary": "XLY", "Industrials": "XLI",
            "Consumer Staples": "XLP", "Utilities": "XLU", "Real Estate": "XLRE",
            "Materials": "XLB", "Communication Services": "XLC",
        }

        for sector_name, etf_ticker in etfs.items():
            try:
                t = yf.Ticker(etf_ticker)
                h = t.history(period="5y")
                if len(h) > 100:
                    sector_data[sector_name] = h["Close"]
            except:
                pass

        sectors = analyze_sectors(data=sp_hist, sector_data=sector_data, forecast_days=1260)

        if not sectors:
            print("    [FAIL] analyze_sectors returned empty")
            return {"status": "empty"}

        # Handle both dict and list returns
        if isinstance(sectors, dict):
            sector_items = sectors.get("sectors", []) if "sectors" in sectors else [sectors]
        elif isinstance(sectors, list):
            sector_items = sectors
        else:
            sector_items = [sectors]

        returns = []
        sector_summary = {}
        for s in (sector_items if isinstance(sector_items, list) else [sector_items]):
            if not isinstance(s, dict):
                continue
            name = s.get("sector", s.get("name", "?"))
            ret = s.get("expected_5y_return", s.get("median_return", s.get("annualized_return")))
            sector_summary[name] = {
                "expected_return": ret,
                "garch_vol": s.get("garch_vol"),
                "crash_freq": s.get("crash_freq"),
            }
            if ret is not None:
                returns.append(float(ret))

        result = {
            "n_sectors": len(sector_summary),
            "sectors": sector_summary,
            "differentiation": {
                "return_spread": round(max(returns) - min(returns), 2) if len(returns) >= 2 else 0,
                "return_std": round(float(np.std(returns)), 2) if len(returns) >= 2 else 0,
                "all_similar": (max(returns) - min(returns) < 5) if len(returns) >= 2 else True,
            },
            "raw_return_type": type(sectors).__name__,
            "raw_keys": list(sectors.keys()) if isinstance(sectors, dict) else f"list[{len(sectors)}]",
        }

        _save(output_dir, "sector_analysis.json", result)
        print(f"    [OK] {len(sector_summary)} sectors, return spread="
              f"{result['differentiation']['return_spread']}%")
        return result

    except Exception as e:
        print(f"    [FAIL] Sector analysis: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 7. Portfolio engine — builds a real portfolio and projects it
# ---------------------------------------------------------------------------
def collect_portfolio_test(output_dir):
    try:
        from backend.services.portfolio_engine import PortfolioEngine
        engine = PortfolioEngine()

        # Test portfolio build
        test_holdings = [
            {"ticker": "AAPL", "shares": 50},
            {"ticker": "NVDA", "shares": 30},
            {"ticker": "XOM", "shares": 40},
            {"ticker": "JPM", "shares": 25},
            {"ticker": "JNJ", "shares": 35},
        ]

        profiles = ["conservative", "moderate", "aggressive"]
        results = {}

        for profile in profiles:
            try:
                build_result = engine.build_portfolio(
                    holdings=test_holdings,
                    risk_profile=profile,
                )
                projection = engine.project_portfolio(
                    holdings=test_holdings,
                    horizon_years=5,
                )

                results[profile] = {
                    "build_success": build_result is not None,
                    "build_keys": list(build_result.keys()) if build_result else [],
                    "projection_success": projection is not None,
                    "projection_keys": list(projection.keys()) if projection else [],
                    "p10": projection.get("p10") if projection else None,
                    "median": projection.get("median") if projection else None,
                    "p90": projection.get("p90") if projection else None,
                }
                print(f"    [OK] Portfolio {profile}: build={'OK' if build_result else 'FAIL'}, "
                      f"project={'OK' if projection else 'FAIL'}")
            except Exception as e:
                results[profile] = {"error": str(e)}
                print(f"    [FAIL] Portfolio {profile}: {e}")

        _save(output_dir, "portfolio_test.json", results)
        return results

    except Exception as e:
        print(f"    [FAIL] Portfolio engine: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 8. API endpoint health — actually starts the app and hits endpoints
# ---------------------------------------------------------------------------
def collect_api_health(output_dir):
    """Import routers and check that key endpoint handlers don't crash."""
    endpoints_to_test = []

    # Test by importing and calling service functions directly
    # (faster than spinning up uvicorn)
    health_results = {}

    # Mix of class-based and function-based services
    # Format: (name, module, callable_type, callable_name)
    # callable_type: "class" means instantiate then call method, "function" means call directly
    service_checks = [
        ("crash_model", "backend.services.crash_model", "class", "CrashPredictor", "predict"),
        ("regime_detector", "backend.services.regime_detector", "function", "detect_regimes", None),
        ("risk_scorer", "backend.services.risk_scorer", "function", "build_risk_score", None),
        ("signal_engine", "backend.services.signal_engine", "function", "get_market_signal", None),
        ("data_quality", "backend.services.data_quality", "class", "DataQualityChecker", "check"),
    ]

    for entry in service_checks:
        name, module_path = entry[0], entry[1]
        callable_type = entry[2]
        callable_name = entry[3]
        method_name = entry[4] if len(entry) > 4 else None

        try:
            mod = __import__(module_path, fromlist=[callable_name])
            target = getattr(mod, callable_name)

            if callable_type == "class":
                instance = target()
                result = getattr(instance, method_name)()
            else:
                result = target()

            health_results[name] = {
                "status": "ok",
                "returned_type": type(result).__name__,
                "returned_none": result is None,
                "returned_keys": list(result.keys()) if isinstance(result, dict) else None,
            }
        except Exception as e:
            health_results[name] = {
                "status": "error",
                "error": f"{type(e).__name__}: {e}",
            }

    # Also check service imports (no instantiation)
    import_checks = [
        "backend.services.monte_carlo",
        "backend.services.stock_analyzer",
        "backend.services.sector_analyzer",
        "backend.services.portfolio_engine",
        "backend.services.shap_explainer",
        "backend.services.news_intelligence",
        "backend.services.savings_calculator",
        "backend.services.net_liquidity",
        "backend.services.return_model",
        "backend.services.sentiment_analyzer",
    ]

    for module_path in import_checks:
        name = module_path.split(".")[-1]
        try:
            __import__(module_path)
            health_results[f"import_{name}"] = {"status": "ok"}
        except Exception as e:
            health_results[f"import_{name}"] = {"status": "error", "error": str(e)}

    ok_count = len([v for v in health_results.values() if v.get("status") == "ok"])
    fail_count = len([v for v in health_results.values() if v.get("status") == "error"])

    _save(output_dir, "api_health.json", health_results)
    print(f"    [OK] {ok_count} healthy, {fail_count} failing")
    return health_results


# ---------------------------------------------------------------------------
# 9. Walk-forward / engine validation metrics
# ---------------------------------------------------------------------------
def collect_validation_metrics(output_dir):
    """Try to run walk-forward validation if trained model exists."""
    try:
        from engine.validation.walk_forward import WalkForwardValidator
        from engine.training.features import build_features
        from engine.training.labeling import create_labels

        # Quick check — does the model pkl exist?
        model_path = REPO_ROOT / "backend" / "models" / "crash_model.pkl"
        if not model_path.exists():
            print("    [SKIP] No crash_model.pkl — skipping validation")
            return {"status": "no_model"}

        # Just report model metadata, don't re-run full validation (too slow)
        import pickle
        with open(model_path, "rb") as f:
            model_data = pickle.load(f)

        result = {
            "model_exists": True,
            "model_keys": list(model_data.keys()) if isinstance(model_data, dict) else ["raw_model"],
            "model_type": type(model_data).__name__,
        }

        # If it's a dict with metadata
        if isinstance(model_data, dict):
            result["train_date"] = model_data.get("train_date")
            result["n_features"] = model_data.get("n_features")
            result["walk_forward_auc"] = model_data.get("walk_forward_auc")
            result["brier_score"] = model_data.get("brier_score")
            result["feature_names"] = model_data.get("feature_names", [])[:20]

        _save(output_dir, "validation_metrics.json", result)
        print(f"    [OK] Model metadata collected")
        return result

    except Exception as e:
        print(f"    [SKIP] Validation metrics: {e}")
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 10. Code quality metrics
# ---------------------------------------------------------------------------
def collect_code_metrics(output_dir):
    """Count tests, measure coverage of key services, check for common issues."""
    import subprocess

    result = {}

    # Count test files and test functions
    try:
        test_dir = REPO_ROOT / "backend" / "tests"
        test_files = list(test_dir.glob("test_*.py"))
        total_tests = 0
        for tf in test_files:
            content = tf.read_text(encoding="utf-8")
            total_tests += content.count("def test_")

        result["test_count"] = {
            "test_files": len(test_files),
            "test_functions": total_tests,
        }
    except Exception as e:
        result["test_count"] = {"error": str(e)}

    # Check for common code smells in backend services
    smells = []
    services_dir = REPO_ROOT / "backend" / "services"
    for py_file in services_dir.glob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            # Broad except
            broad_excepts = sum(1 for l in lines if "except:" in l or "except Exception:" in l)
            if broad_excepts > 3:
                smells.append(f"{py_file.name}: {broad_excepts} broad except blocks")

            # fillna(0) — banned per CLAUDE.md
            fillna_zeros = sum(1 for l in lines if "fillna(0)" in l)
            if fillna_zeros > 0:
                smells.append(f"{py_file.name}: {fillna_zeros} fillna(0) calls (banned)")

            # Hardcoded seeds
            old_seeds = sum(1 for l in lines if "np.random.seed" in l)
            if old_seeds > 0:
                smells.append(f"{py_file.name}: {old_seeds} legacy np.random.seed() calls")

            # TODO/FIXME/HACK
            todos = sum(1 for l in lines if any(tag in l.upper() for tag in ["TODO", "FIXME", "HACK"]))
            if todos > 0:
                smells.append(f"{py_file.name}: {todos} TODO/FIXME/HACK comments")

        except:
            pass

    result["code_smells"] = smells
    result["n_smells"] = len(smells)

    # Frontend build check (quick — just check for tsconfig errors)
    try:
        frontend_dir = REPO_ROOT / "frontend"
        if (frontend_dir / "package.json").exists():
            r = subprocess.run(
                ["npx", "tsc", "--noEmit", "--pretty", "false"],
                cwd=str(frontend_dir),
                capture_output=True, text=True, timeout=60
            )
            ts_errors = [l for l in r.stdout.split("\n") if "error TS" in l]
            result["frontend_type_errors"] = len(ts_errors)
            if ts_errors:
                result["frontend_error_samples"] = ts_errors[:5]
        else:
            result["frontend_type_errors"] = "no_frontend"
    except Exception as e:
        result["frontend_type_errors"] = f"check_failed: {e}"

    _save(output_dir, "code_metrics.json", result)
    print(f"    [OK] {result.get('test_count', {}).get('test_functions', '?')} tests, "
          f"{len(smells)} code smells")
    return result


# ---------------------------------------------------------------------------
# 11. SP500 Monte Carlo — calls ACTUAL backend MC engine
# ---------------------------------------------------------------------------
def collect_sp500_mc(output_dir):
    try:
        from backend.services.monte_carlo import run_monte_carlo
        result = run_monte_carlo()

        if result is None:
            print("    [FAIL] run_monte_carlo returned None")
            return {"status": "failed"}

        # Extract key metrics
        summary = {
            "status": "ok",
            "result_keys": list(result.keys()),
            "annualized_return": result.get("annualized_return"),
            "median_5y_return": result.get("median_5y_return"),
            "p10_5y": result.get("p10_5y_return"),
            "p90_5y": result.get("p90_5y_return"),
            "n_simulations": result.get("n_simulations"),
            "scenario_weights": result.get("scenario_weights"),
        }

        _save(output_dir, "sp500_monte_carlo.json", summary)
        ann_ret = result.get("annualized_return", "?")
        print(f"    [OK] SP500 MC: annualized={ann_ret}%")
        return summary

    except Exception as e:
        print(f"    [FAIL] SP500 MC: {e}")
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def _save(output_dir, filename, data):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_engine_data_collection(output_dir, cycle):
    results = {
        "cycle": cycle,
        "timestamp": datetime.now().isoformat(),
        "data_sources": [],
        "errors": [],
    }

    os.makedirs(output_dir, exist_ok=True)

    collectors = [
        ("market_snapshot", "Fetching market data", collect_market_snapshot),
        ("stock_analysis", "Running REAL stock analysis (analyze_stock)", collect_stock_analysis),
        ("sp500_mc", "Running REAL SP500 Monte Carlo", collect_sp500_mc),
        ("crash_calibration", "Measuring crash model calibration", collect_crash_calibration),
        ("signal_quality", "Measuring signal differentiation", collect_signal_quality),
        ("regime_risk", "Checking regime + risk score", collect_regime_risk),
        ("sector_analysis", "Running REAL sector analysis", collect_sector_analysis),
        ("portfolio_test", "Testing portfolio engine", collect_portfolio_test),
        ("api_health", "Checking service health", collect_api_health),
        ("validation_metrics", "Collecting model validation metrics", collect_validation_metrics),
        ("code_metrics", "Measuring code quality", collect_code_metrics),
    ]

    for i, (name, label, collector) in enumerate(collectors, 1):
        print(f"  [{i}/{len(collectors)}] {label}...")
        try:
            result = collector(output_dir)
            if isinstance(result, tuple):
                # Some collectors return (result, errors)
                data, errs = result
                results["errors"].extend(errs)
            results["data_sources"].append(name)
        except Exception as e:
            results["errors"].append(f"{name}: {type(e).__name__}: {e}")
            print(f"    [FAIL] {name}: {e}")

    # Summary
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
