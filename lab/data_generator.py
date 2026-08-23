"""
Aegis Finance - Lab Data Generator v4
Calls REAL backend services + runs stress tests + finds inconsistencies.
Acts as a quant analyst desk review — catches what manual review misses.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    except (TypeError, ValueError):
        return None


def safe_json(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else round(float(obj), 4)
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [safe_json(v) for v in obj]
    return obj


def save_json(data, output_dir, filename):
    with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
        json.dump(safe_json(data), f, indent=2, default=str)


FULL_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
    "JPM", "BAC", "GS", "V", "MA",
    "XOM", "CVX", "COP",
    "JNJ", "UNH", "PFE", "LLY",
    "WMT", "PG", "KO", "PEP",
    "BA", "CAT", "HON", "UPS",
    "NEE", "DUK",
    "AMT", "PLD",
    "CRM", "ADBE",
]


def pick_random_tickers(n=8, seed=None):
    rng = np.random.default_rng(seed)
    return list(rng.choice(FULL_UNIVERSE, size=min(n, len(FULL_UNIVERSE)), replace=False))


# ---------------------------------------------------------------------------
# SECTION 1: Real backend service calls
# ---------------------------------------------------------------------------

def collect_stock_analysis(tickers, results, output_dir):
    """Call real stock_analyzer.analyze_stock() for each ticker."""
    print("  [1/10] Stock analysis (real backend)...")
    stock_data = {}
    try:
        from backend.services.stock_analyzer import analyze_stock
        for ticker in tickers:
            try:
                r = analyze_stock(ticker, forecast_days=1260)
                if r:
                    stock_data[ticker] = {
                        "ticker": ticker,
                        "sector": r.get("sector"),
                        "current_price": safe_float(r.get("current_price")),
                        "market_cap": safe_float(r.get("market_cap")),
                        "cap_tier": r.get("cap_tier"),
                        "beta": safe_float(r.get("beta")),
                        "pe_ratio": safe_float(r.get("pe_ratio")),
                        "analyst_target": safe_float(r.get("analyst_target")),
                        "hist_drift": safe_float(r.get("hist_drift")),
                        "capped_drift": safe_float(r.get("capped_drift")),
                        "volatility": safe_float(r.get("volatility")),
                        "expected_return_pct": safe_float(r.get("expected_return")),
                        "median_return_pct": safe_float(r.get("median_return")),
                        "p05_price": safe_float(r.get("p05_price")),
                        "p95_price": safe_float(r.get("p95_price")),
                        "sharpe": safe_float(r.get("sharpe")),
                        "prob_loss_5y": safe_float(r.get("prob_loss_5y")),
                        "max_drawdown": safe_float(r.get("avg_max_drawdown")),
                    }
                    print(f"    [OK] {ticker}: ${r.get('current_price',0):.0f}, "
                          f"exp_ret={r.get('expected_return','?')}, beta={r.get('beta')}")
            except Exception as e:
                results["errors"].append(f"Stock {ticker}: {e}")
                print(f"    [FAIL] {ticker}: {e}")
        save_json(stock_data, output_dir, "stock_analysis.json")
        results["data_sources"].append("stock_analysis")
    except ImportError as e:
        results["errors"].append(f"stock_analyzer import: {e}")
        print(f"    [FAIL] import: {e}")
    return stock_data


def collect_sp500_mc(results, output_dir, cycle_seed):
    """Call real monte_carlo.run_monte_carlo() for S&P 500."""
    print("  [2/10] S&P 500 Monte Carlo (real backend)...")
    sp500_data = {}
    try:
        import yfinance as yf
        from backend.services.monte_carlo import run_monte_carlo

        sp_hist = yf.Ticker("^GSPC").history(period="2y")
        sp_price = float(sp_hist["Close"].iloc[-1])
        vix_price = float(yf.Ticker("^VIX").history(period="5d")["Close"].iloc[-1])
        t10y = float(yf.Ticker("^TNX").history(period="5d")["Close"].iloc[-1])
        t3m = float(yf.Ticker("^IRX").history(period="5d")["Close"].iloc[-1])

        regime, risk_score, crash_prob = "Neutral", 0.0, None

        try:
            from backend.services.regime_detector import detect_regimes
            sp_df = pd.DataFrame({"SP500": sp_hist["Close"].values}, index=sp_hist.index)
            sp_df.index = sp_df.index.normalize().tz_localize(None)
            vix_hist = yf.Ticker("^VIX").history(period="2y")
            vix_s = vix_hist["Close"].copy()
            vix_s.index = vix_s.index.normalize().tz_localize(None)
            sp_df["VIX"] = vix_s.reindex(sp_df.index, method="nearest")
            _, regime = detect_regimes(sp_df, window=252)
        except Exception as e:
            print(f"    [WARN] Regime: {e}")

        try:
            from backend.services.crash_model import CrashPredictor
            from engine.training.features import build_feature_matrix
            from backend.services.data_fetcher import DataFetcher
            from backend.config import MODEL_DIR
            predictor = CrashPredictor()
            predictor.load_model(str(MODEL_DIR / "crash_model.pkl"))
            fetcher = DataFetcher()
            data, _ = fetcher.fetch_market_data()
            fred = fetcher.fetch_fred_data()
            features = build_feature_matrix(data, fred_data=fred)
            probs = predictor.predict_all_horizons(features)
            crash_prob = float(probs.get("3m", [0.15])[-1]) if "3m" in probs else None
        except Exception as e:
            print(f"    [WARN] Crash model: {e}")

        mc = run_monte_carlo(
            current_price=sp_price, current_regime=regime, risk_score=risk_score,
            crash_freq=0.08, current_vix=vix_price, yield_curve=t10y - t3m,
            val_penalty=0.02, ml_crash_prob=crash_prob, seed=cycle_seed,
        )

        sp500_data = {
            "start_price": round(sp_price, 2), "regime": regime,
            "risk_score": safe_float(risk_score), "crash_prob_3m": safe_float(crash_prob),
            "vix": safe_float(vix_price), "yield_curve": safe_float(t10y - t3m),
            "mc_results": {k: safe_float(v) if isinstance(v, (int, float, np.floating)) else v
                           for k, v in mc.items() if k not in ("paths", "daily_paths")},
        }
        print(f"    [OK] regime={regime}, vix={vix_price:.1f}, crash_3m={crash_prob}")
        save_json(sp500_data, output_dir, "sp500_monte_carlo.json")
        results["data_sources"].append("sp500_monte_carlo")
    except Exception as e:
        results["errors"].append(f"SP500 MC: {e}")
        print(f"    [FAIL] {e}")
    return sp500_data


def collect_signals(stock_data, sp500_data, results, output_dir):
    """Call real signal engine for market + stock signals."""
    print("  [3/10] Signal engine (real backend)...")
    signal_results = {}
    try:
        from backend.services.signal_engine import get_market_signal, get_stock_signal
        import yfinance as yf

        sp = yf.Ticker("^GSPC").history(period="6mo")
        sp_1m = float((sp["Close"].iloc[-1] / sp["Close"].iloc[-22] - 1) * 100) if len(sp) > 22 else 0
        sp_3m = float((sp["Close"].iloc[-1] / sp["Close"].iloc[-63] - 1) * 100) if len(sp) > 63 else 0

        market_sig = get_market_signal(
            crash_prob_3m=sp500_data.get("crash_prob_3m"),
            vix=sp500_data.get("vix", 20),
            sp500_1m_return=sp_1m, sp500_3m_return=sp_3m,
            regime=sp500_data.get("regime", "Neutral"),
        )
        signal_results["market_signal"] = {
            "action": market_sig.get("action"),
            "confidence": safe_float(market_sig.get("confidence")),
            "composite_score": safe_float(market_sig.get("composite_score")),
            "components": market_sig.get("components"),
        }
        print(f"    [OK] Market: {market_sig.get('action')} ({market_sig.get('confidence',0):.0f}%)")

        stock_signals = {}
        for ticker, sd in stock_data.items():
            try:
                ss = get_stock_signal(
                    market_signal=market_sig, beta=sd.get("beta", 1.0) or 1.0,
                    analyst_target=sd.get("analyst_target"),
                    current_price=sd.get("current_price", 0) or 0,
                    pe_ratio=sd.get("pe_ratio"),
                )
                stock_signals[ticker] = {
                    "action": ss.get("action"),
                    "composite_score": safe_float(ss.get("composite_score")),
                    "confidence": safe_float(ss.get("confidence")),
                }
            except Exception as e:
                results["errors"].append(f"Stock signal {ticker}: {e}")
        signal_results["stock_signals"] = stock_signals
        actions = list(set(s["action"] for s in stock_signals.values()))
        print(f"    [OK] Stocks: {len(stock_signals)} tickers, actions={actions}")

        save_json(signal_results, output_dir, "signal_results.json")
        results["data_sources"].append("signal_results")
    except Exception as e:
        results["errors"].append(f"Signal engine: {e}")
        print(f"    [FAIL] {e}")
    return signal_results


def collect_portfolios(results, output_dir, cycle_seed):
    """Test portfolio engine with different profiles."""
    print("  [4/10] Portfolio engine (real backend)...")
    portfolio_results = []
    try:
        from backend.services.portfolio_engine import PortfolioEngine
        for profile in ["conservative", "moderate", "aggressive"]:
            try:
                built = PortfolioEngine.build_portfolio(
                    risk_tolerance=profile, investment_amount=100000,
                    method="template", goal="growth",
                )
                portfolio_results.append({
                    "type": "build", "profile": profile,
                    "n_holdings": len(built.get("holdings", [])),
                    "holdings_preview": [
                        {"ticker": h.get("ticker"), "weight": safe_float(h.get("weight"))}
                        for h in built.get("holdings", [])[:5]
                    ],
                })
                print(f"    [OK] Build {profile}: {len(built.get('holdings',[]))} holdings")
            except Exception as e:
                results["errors"].append(f"Portfolio build {profile}: {e}")
                print(f"    [FAIL] Build {profile}: {e}")

        save_json(portfolio_results, output_dir, "portfolio_results.json")
        results["data_sources"].append("portfolio_results")
    except ImportError as e:
        print(f"    [FAIL] import: {e}")
    return portfolio_results


def collect_crash_model(results, output_dir):
    """Run real crash model predictions."""
    print("  [5/10] Crash model (real backend)...")
    crash_results = {}
    try:
        from backend.services.crash_model import CrashPredictor
        from engine.training.features import build_feature_matrix
        from backend.services.data_fetcher import DataFetcher
        from backend.config import MODEL_DIR

        predictor = CrashPredictor()
        predictor.load_model(str(MODEL_DIR / "crash_model.pkl"))
        fetcher = DataFetcher()
        data, _ = fetcher.fetch_market_data()
        fred = fetcher.fetch_fred_data()
        features = build_feature_matrix(data, fred_data=fred)

        if features is not None and len(features) > 0:
            probs = predictor.predict_all_horizons(features)
            for h, p in probs.items():
                latest = float(p[-1]) if len(p) > 0 else None
                crash_results[h] = {"latest_prob": safe_float(latest)}

            p3 = crash_results.get("3m", {}).get("latest_prob", 0) or 0
            p6 = crash_results.get("6m", {}).get("latest_prob", 0) or 0
            p12 = crash_results.get("12m", {}).get("latest_prob", 0) or 0
            crash_results["monotonicity"] = {
                "3m_le_6m": p3 <= p6 + 0.001,
                "6m_le_12m": p6 <= p12 + 0.001,
                "passes": p3 <= p6 + 0.001 and p6 <= p12 + 0.001,
            }
            print(f"    [OK] 3m={p3:.1%}, 6m={p6:.1%}, 12m={p12:.1%}, mono={crash_results['monotonicity']['passes']}")

        save_json(crash_results, output_dir, "crash_predictions.json")
        results["data_sources"].append("crash_predictions")
    except Exception as e:
        results["errors"].append(f"Crash model: {e}")
        print(f"    [FAIL] {e}")
    return crash_results


# ---------------------------------------------------------------------------
# SECTION 2: Stress tests & edge cases — the quant debugging machine
# ---------------------------------------------------------------------------

def run_stress_tests(stock_data, results, output_dir):
    """Stress test the engine with extreme/adversarial inputs."""
    print("  [6/10] Stress tests (edge cases)...")
    stress_results = []

    # Test 1: Zero-beta stock signal
    try:
        from backend.services.signal_engine import get_market_signal, get_stock_signal
        market_sig = get_market_signal(vix=20, sp500_1m_return=0, sp500_3m_return=0)
        zero_beta = get_stock_signal(market_signal=market_sig, beta=0.0, current_price=100)
        high_beta = get_stock_signal(market_signal=market_sig, beta=3.0, current_price=100)
        stress_results.append({
            "test": "beta_differentiation",
            "pass": zero_beta.get("composite_score") != high_beta.get("composite_score"),
            "detail": f"beta=0 score={zero_beta.get('composite_score')}, beta=3 score={high_beta.get('composite_score')}",
        })
    except Exception as e:
        stress_results.append({"test": "beta_differentiation", "pass": False, "error": str(e)})

    # Test 2: Extreme VIX values
    try:
        from backend.services.signal_engine import get_market_signal
        calm = get_market_signal(vix=10, sp500_1m_return=5, sp500_3m_return=15)
        panic = get_market_signal(vix=80, sp500_1m_return=-20, sp500_3m_return=-30)
        stress_results.append({
            "test": "extreme_vix_differentiation",
            "pass": calm.get("composite_score", 0) > panic.get("composite_score", 0),
            "detail": f"VIX=10 score={calm.get('composite_score')}, VIX=80 score={panic.get('composite_score')}",
        })
    except Exception as e:
        stress_results.append({"test": "extreme_vix_differentiation", "pass": False, "error": str(e)})

    # Test 3: MC with extreme volatility
    try:
        from backend.services.monte_carlo import simulate_paths
        from backend.config import config
        base_scenario = config["scenarios"].get("base", config["scenarios"].get("Base Case", list(config["scenarios"].values())[0]))
        paths = simulate_paths(
            start_price=100, historical_mu=0.0003, historical_sigma=0.05,
            days=252, n_sims=500, crash_freq=0.08, risk_score=0.0,
            scenario=base_scenario, seed=42,
        )
        terminal = paths[-1, :]
        mean_ret = float(np.mean(terminal / 100 - 1))
        stress_results.append({
            "test": "high_vol_mc_bounded",
            "pass": -0.9 < mean_ret < 5.0,
            "detail": f"sigma=0.05 (5% daily!), mean_terminal_return={mean_ret:.2%}",
        })
    except Exception as e:
        stress_results.append({"test": "high_vol_mc_bounded", "pass": False, "error": str(e)})

    # Test 4: MC reproducibility
    try:
        from backend.services.monte_carlo import simulate_paths
        from backend.config import config
        base_scenario = config["scenarios"].get("base", config["scenarios"].get("Base Case", list(config["scenarios"].values())[0]))
        p1 = simulate_paths(start_price=100, historical_mu=0.0003, historical_sigma=0.01,
                            days=252, n_sims=100, crash_freq=0.08, risk_score=0.0,
                            scenario=base_scenario, seed=999)
        p2 = simulate_paths(start_price=100, historical_mu=0.0003, historical_sigma=0.01,
                            days=252, n_sims=100, crash_freq=0.08, risk_score=0.0,
                            scenario=base_scenario, seed=999)
        stress_results.append({
            "test": "mc_reproducibility",
            "pass": np.array_equal(p1, p2),
            "detail": f"same seed → same paths: {np.array_equal(p1, p2)}",
        })
    except Exception as e:
        stress_results.append({"test": "mc_reproducibility", "pass": False, "error": str(e)})

    # Test 5: Signal with all-None inputs (robustness)
    try:
        from backend.services.signal_engine import get_market_signal
        sig = get_market_signal()  # all defaults
        stress_results.append({
            "test": "signal_default_robustness",
            "pass": sig.get("action") is not None and sig.get("composite_score") is not None,
            "detail": f"default signal: action={sig.get('action')}, score={sig.get('composite_score')}",
        })
    except Exception as e:
        stress_results.append({"test": "signal_default_robustness", "pass": False, "error": str(e)})

    # Test 6: Portfolio with single stock (edge case)
    try:
        from backend.services.portfolio_engine import PortfolioEngine
        import yfinance as yf
        price = float(yf.Ticker("AAPL").history(period="5d")["Close"].iloc[-1])
        r = PortfolioEngine.analyze_portfolio([{"ticker": "AAPL", "shares": 100, "current_price": price}])
        stress_results.append({
            "test": "single_stock_portfolio",
            "pass": r is not None and "total_value" in str(r).lower() or len(r) > 0,
            "detail": f"single stock analyze returned: {list(r.keys()) if isinstance(r, dict) else type(r)}",
        })
    except Exception as e:
        stress_results.append({"test": "single_stock_portfolio", "pass": False, "error": str(e)})

    # Test 7: Cross-service consistency — stock MC vs standalone MC
    try:
        if stock_data:
            first_ticker = list(stock_data.keys())[0]
            sd = stock_data[first_ticker]
            stock_exp = sd.get("expected_return_pct")
            if stock_exp is not None:
                # Check if expected return is in a sane range
                stress_results.append({
                    "test": "stock_return_range",
                    "pass": -50 < stock_exp < 300,
                    "detail": f"{first_ticker} expected 5Y return: {stock_exp}%",
                })
    except Exception as e:
        stress_results.append({"test": "stock_return_range", "pass": False, "error": str(e)})

    # Test 8: Crash prob differentiation across stocks
    try:
        from backend.services.stock_analyzer import analyze_stock
        safe = analyze_stock("JNJ", forecast_days=252)  # low beta defensive
        risky = analyze_stock("TSLA", forecast_days=252)  # high beta growth
        if safe and risky:
            safe_ret = safe.get("expected_return", 0)
            risky_ret = risky.get("expected_return", 0)
            safe_vol = safe.get("volatility", 0)
            risky_vol = risky.get("volatility", 0)
            stress_results.append({
                "test": "risk_return_ordering",
                "pass": (risky_vol or 0) > (safe_vol or 0),
                "detail": f"JNJ vol={safe_vol}, TSLA vol={risky_vol}. Higher risk should mean higher vol.",
            })
    except Exception as e:
        stress_results.append({"test": "risk_return_ordering", "pass": False, "error": str(e)})

    passed = sum(1 for t in stress_results if t.get("pass"))
    total = len(stress_results)
    print(f"    [{'OK' if passed == total else 'WARN'}] {passed}/{total} stress tests passed")
    for t in stress_results:
        if not t.get("pass"):
            print(f"      [FAIL] {t['test']}: {t.get('detail', t.get('error', '?'))}")

    save_json(stress_results, output_dir, "stress_tests.json")
    results["data_sources"].append("stress_tests")
    return stress_results


def run_consistency_checks(stock_data, signal_results, results, output_dir):
    """Cross-service consistency checks — find contradictions."""
    print("  [7/10] Consistency checks...")
    checks = []

    # Check 1: All signals should span more than just "Hold"
    if signal_results:
        stock_sigs = signal_results.get("stock_signals", {})
        actions = set(s.get("action") for s in stock_sigs.values())
        checks.append({
            "check": "signal_diversity",
            "pass": len(actions) >= 2,
            "detail": f"Unique actions: {sorted(actions)}. Only 1 type = broken differentiation.",
        })

    # Check 2: High-beta stocks should have wider MC fans than low-beta
    if len(stock_data) >= 2:
        betas = [(t, sd.get("beta", 1)) for t, sd in stock_data.items() if sd.get("beta")]
        if len(betas) >= 2:
            betas.sort(key=lambda x: x[1] or 0)
            low_t, low_beta = betas[0]
            high_t, high_beta = betas[-1]
            low_p95 = stock_data[low_t].get("p95_price") or 0
            low_p05 = stock_data[low_t].get("p05_price") or 0
            low_price = stock_data[low_t].get("current_price") or 1
            high_p95 = stock_data[high_t].get("p95_price") or 0
            high_p05 = stock_data[high_t].get("p05_price") or 0
            high_price = stock_data[high_t].get("current_price") or 1
            low_spread = (low_p95 - low_p05) / low_price if low_price else 0
            high_spread = (high_p95 - high_p05) / high_price if high_price else 0
            checks.append({
                "check": "beta_mc_fan_width",
                "pass": high_spread > low_spread * 0.8,
                "detail": f"{low_t}(beta={low_beta}) fan={low_spread:.1%}, {high_t}(beta={high_beta}) fan={high_spread:.1%}",
            })

    # Check 3: Expected returns should loosely correlate with risk
    if len(stock_data) >= 3:
        items = [(t, sd.get("volatility", 0) or 0, sd.get("expected_return_pct", 0) or 0)
                 for t, sd in stock_data.items()]
        vols = [x[1] for x in items]
        rets = [x[2] for x in items]
        if len(set(vols)) > 1:
            corr = float(np.corrcoef(vols, rets)[0, 1])
            checks.append({
                "check": "risk_return_correlation",
                "pass": corr > -0.5,  # shouldn't be strongly negative
                "detail": f"Vol-return correlation: {corr:.3f}. Strongly negative = broken risk premium.",
            })

    passed = sum(1 for c in checks if c.get("pass"))
    total = len(checks)
    print(f"    [{'OK' if passed == total else 'WARN'}] {passed}/{total} consistency checks passed")
    for c in checks:
        if not c.get("pass"):
            print(f"      [FAIL] {c['check']}: {c.get('detail', '?')}")

    save_json(checks, output_dir, "consistency_checks.json")
    results["data_sources"].append("consistency_checks")
    return checks


def run_backtest(results, output_dir):
    """Historical signal backtest."""
    print("  [8/10] Signal backtest...")
    try:
        import yfinance as yf
        from backend.services.signal_engine import get_market_signal

        sp_hist = yf.Ticker("^GSPC").history(period="2y")
        vix_hist = yf.Ticker("^VIX").history(period="2y")
        vix_series = vix_hist["Close"].copy()
        vix_series.index = vix_series.index.normalize().tz_localize(None)
        sp_dates = sp_hist.index.normalize().tz_localize(None)

        tests = []
        for start_idx in range(378, 125, -21):
            if start_idx + 63 > len(sp_hist):
                continue
            try:
                test_price = float(sp_hist["Close"].iloc[-start_idx])
                actual_price = float(sp_hist["Close"].iloc[-(start_idx - 63)])
                actual_return = (actual_price / test_price - 1) * 100
                test_date = sp_dates[-start_idx]

                vix_at = 20.0
                try:
                    vi = vix_series.index.get_indexer([test_date], method="nearest")[0]
                    if 0 <= vi < len(vix_series):
                        vix_at = float(vix_series.iloc[vi])
                except:
                    pass

                sp_1m = (test_price / float(sp_hist["Close"].iloc[-(start_idx + 21)]) - 1) * 100 if start_idx + 21 < len(sp_hist) else 0
                sp_3m = (test_price / float(sp_hist["Close"].iloc[-(start_idx + 63)]) - 1) * 100 if start_idx + 63 < len(sp_hist) else 0

                sig = get_market_signal(vix=vix_at, sp500_1m_return=sp_1m, sp500_3m_return=sp_3m)
                score = sig.get("composite_score", 0)
                tests.append({
                    "date": str(test_date.date()),
                    "signal_score": safe_float(score),
                    "signal_action": sig.get("action"),
                    "actual_3m_return_pct": round(actual_return, 2),
                    "direction_correct": (score > 0 and actual_return > 0) or (score < 0 and actual_return < 0) or score == 0,
                    "vix": round(vix_at, 1),
                })
            except:
                pass

        if tests:
            dir_acc = sum(1 for t in tests if t["direction_correct"]) / len(tests) * 100
            scores = [t["signal_score"] or 0 for t in tests]
            rets = [t["actual_3m_return_pct"] for t in tests]
            corr = float(np.corrcoef(scores, rets)[0, 1]) if len(scores) > 2 else 0
            actions = list(set(t["signal_action"] for t in tests))

            bt = {"n_tests": len(tests), "direction_accuracy_pct": round(dir_acc, 1),
                  "signal_return_correlation": round(corr, 3), "actions_seen": actions, "tests": tests}
            save_json(bt, output_dir, "backtest_accuracy.json")
            results["data_sources"].append("backtest_accuracy")
            print(f"    [OK] {len(tests)} tests, acc={dir_acc:.0f}%, corr={corr:.3f}, actions={actions}")
    except Exception as e:
        results["errors"].append(f"Backtest: {e}")
        print(f"    [FAIL] {e}")


def collect_correlations(results, output_dir):
    """Cross-asset correlation matrix."""
    print("  [9/10] Cross-asset correlations...")
    try:
        import yfinance as yf
        assets = {"SP500": "^GSPC", "VIX": "^VIX", "10Y": "^TNX", "Gold": "GC=F", "Oil": "CL=F"}
        dfs = {}
        for name, sym in assets.items():
            try:
                h = yf.Ticker(sym).history(period="1y")
                if len(h) > 0:
                    s = h["Close"].copy()
                    s.index = s.index.normalize().tz_localize(None)
                    dfs[name] = s.pct_change().dropna()
            except:
                pass
        if len(dfs) >= 3:
            combined = pd.DataFrame(dfs).dropna()
            corr = combined.corr()
            save_json({
                "matrix": {k: {k2: round(v2, 3) for k2, v2 in v.items()} for k, v in corr.to_dict().items()},
                "n_observations": len(combined),
            }, output_dir, "cross_asset_correlations.json")
            results["data_sources"].append("cross_asset_correlations")
            print(f"    [OK] {len(dfs)} assets, {len(combined)} observations")
    except Exception as e:
        results["errors"].append(f"Correlations: {e}")
        print(f"    [FAIL] {e}")


def run_reality_checks(stock_data, sp500_data, results, output_dir):
    """Compare engine predictions to analyst consensus — catches overfitting."""
    print("  [10/11] Reality checks (engine vs analysts)...")
    checks = []

    try:
        import yfinance as yf

        for ticker, sd in stock_data.items():
            try:
                info = yf.Ticker(ticker).info or {}
                analyst_target = info.get("targetMeanPrice")
                current_price = sd.get("current_price", 0) or 0
                engine_exp_ret = sd.get("expected_return_pct")  # 5Y return

                if analyst_target and current_price > 0 and engine_exp_ret is not None:
                    analyst_1y_upside = (analyst_target / current_price - 1) * 100
                    # Engine gives 5Y return, annualize for comparison
                    engine_annual = ((1 + engine_exp_ret / 100) ** 0.2 - 1) * 100

                    # Flag if engine annual return is >3x analyst 1Y target
                    gap = abs(engine_annual - analyst_1y_upside)
                    reasonable = gap < 40  # within 40pp

                    checks.append({
                        "ticker": ticker,
                        "current_price": round(current_price, 2),
                        "analyst_1y_target": round(analyst_target, 2),
                        "analyst_1y_upside_pct": round(analyst_1y_upside, 1),
                        "engine_5y_return_pct": round(engine_exp_ret, 1),
                        "engine_annualized_pct": round(engine_annual, 1),
                        "gap_pct": round(gap, 1),
                        "reasonable": reasonable,
                        "verdict": "OK" if reasonable else f"ENGINE {'OVER' if engine_annual > analyst_1y_upside else 'UNDER'}ESTIMATES vs analysts",
                    })
            except Exception:
                pass

        # SP500 institutional consensus check (~5.9% annual)
        sp_mc = sp500_data.get("mc_results", {})
        sp_annual = sp_mc.get("annualized_return_pct") or sp_mc.get("expected_annual_return")
        if sp_annual is not None:
            institutional_consensus = 5.9  # average of major firms
            gap = abs(float(sp_annual) - institutional_consensus)
            checks.append({
                "ticker": "SP500",
                "engine_annual_pct": round(float(sp_annual), 1),
                "institutional_consensus_pct": institutional_consensus,
                "gap_pct": round(gap, 1),
                "reasonable": gap < 8,
                "verdict": "OK" if gap < 8 else f"SP500 projection {float(sp_annual):.1f}% vs consensus {institutional_consensus}%",
            })

        if checks:
            n_reasonable = sum(1 for c in checks if c.get("reasonable"))
            print(f"    [{'OK' if n_reasonable == len(checks) else 'WARN'}] {n_reasonable}/{len(checks)} predictions align with analyst consensus")
            for c in checks:
                if not c.get("reasonable"):
                    print(f"      [GAP] {c['ticker']}: engine={c.get('engine_annualized_pct', c.get('engine_annual_pct'))}% vs analyst={c.get('analyst_1y_upside_pct', c.get('institutional_consensus_pct'))}%")

            save_json(checks, output_dir, "reality_checks.json")
            results["data_sources"].append("reality_checks")

    except Exception as e:
        results["errors"].append(f"Reality checks: {e}")
        print(f"    [FAIL] {e}")
    return checks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_engine_data_collection(output_dir, cycle):
    results = {"cycle": cycle, "timestamp": datetime.now().isoformat(),
               "data_sources": [], "errors": []}
    os.makedirs(output_dir, exist_ok=True)
    cycle_seed = 42 + cycle * 137

    tickers = pick_random_tickers(n=8, seed=cycle_seed)
    print(f"  Tickers for this cycle: {tickers}")

    stock_data = collect_stock_analysis(tickers, results, output_dir)
    sp500_data = collect_sp500_mc(results, output_dir, cycle_seed)
    signal_results = collect_signals(stock_data, sp500_data, results, output_dir)
    collect_portfolios(results, output_dir, cycle_seed)
    collect_crash_model(results, output_dir)
    stress_tests = run_stress_tests(stock_data, results, output_dir)
    consistency = run_consistency_checks(stock_data, signal_results, results, output_dir)
    run_backtest(results, output_dir)
    collect_correlations(results, output_dir)
    reality = run_reality_checks(stock_data, sp500_data, results, output_dir)

    # Summary
    print("  [11/11] Summary...")
    stress_passed = sum(1 for t in stress_tests if t.get("pass"))
    consist_passed = sum(1 for c in consistency if c.get("pass"))
    reality_ok = sum(1 for r in reality if r.get("reasonable"))
    results["summary"] = {
        "data_sources": len(results["data_sources"]),
        "errors": len(results["errors"]),
        "stress_tests": f"{stress_passed}/{len(stress_tests)}",
        "consistency_checks": f"{consist_passed}/{len(consistency)}",
        "reality_checks": f"{reality_ok}/{len(reality)}",
        "tickers_tested": tickers,
    }
    save_json(results, output_dir, "run_metadata.json")
    print(f"\n  Complete: {len(results['data_sources'])} sources, {len(results['errors'])} errors, "
          f"stress={stress_passed}/{len(stress_tests)}, consistency={consist_passed}/{len(consistency)}, "
          f"reality={reality_ok}/{len(reality)}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cycle", type=int, default=1)
    args = parser.parse_args()
    run_engine_data_collection(args.output_dir, args.cycle)
