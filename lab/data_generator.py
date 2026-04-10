"""
Aegis Finance - Lab Data Generator
Runs the engine and collects real data for Claude to analyze.
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


def generate_random_portfolios(n_portfolios=5):
    STOCK_UNIVERSE = [
        {"ticker": "AAPL", "sector": "Technology", "name": "Apple"},
        {"ticker": "MSFT", "sector": "Technology", "name": "Microsoft"},
        {"ticker": "NVDA", "sector": "Technology", "name": "NVIDIA"},
        {"ticker": "GOOGL", "sector": "Technology", "name": "Alphabet"},
        {"ticker": "META", "sector": "Technology", "name": "Meta"},
        {"ticker": "AMZN", "sector": "Technology", "name": "Amazon"},
        {"ticker": "JPM", "sector": "Financials", "name": "JPMorgan"},
        {"ticker": "BAC", "sector": "Financials", "name": "Bank of America"},
        {"ticker": "XOM", "sector": "Energy", "name": "ExxonMobil"},
        {"ticker": "CVX", "sector": "Energy", "name": "Chevron"},
        {"ticker": "JNJ", "sector": "Healthcare", "name": "J&J"},
        {"ticker": "UNH", "sector": "Healthcare", "name": "UnitedHealth"},
        {"ticker": "WMT", "sector": "Consumer Staples", "name": "Walmart"},
        {"ticker": "TSLA", "sector": "Consumer Discretionary", "name": "Tesla"},
        {"ticker": "BA", "sector": "Industrials", "name": "Boeing"},
        {"ticker": "CAT", "sector": "Industrials", "name": "Caterpillar"},
    ]

    portfolios = []
    for i in range(n_portfolios):
        n_holdings = np.random.randint(3, 9)
        selected = np.random.choice(len(STOCK_UNIVERSE), n_holdings, replace=False)
        weights = np.random.dirichlet(np.ones(n_holdings))
        total_value = np.random.uniform(10000, 500000)

        holdings = []
        for j, idx in enumerate(selected):
            stock = STOCK_UNIVERSE[idx]
            weight = float(weights[j])
            cost_basis_factor = np.random.uniform(0.5, 1.5)
            shares = max(1, int(total_value * weight / (100 * cost_basis_factor)))

            holdings.append({
                "ticker": stock["ticker"],
                "name": stock["name"],
                "sector": stock["sector"],
                "shares": shares,
                "weight": round(weight, 4),
                "cost_basis": round(100 * cost_basis_factor, 2),
                "purchase_date": (datetime.now() - timedelta(days=np.random.randint(30, 730))).strftime("%Y-%m-%d"),
            })

        portfolios.append({
            "id": f"portfolio_{i+1}",
            "risk_profile": np.random.choice(["conservative", "moderate", "aggressive", "growth"]),
            "total_value_approx": round(total_value, 2),
            "n_holdings": n_holdings,
            "holdings": holdings,
        })

    return portfolios


def run_engine_data_collection(output_dir, cycle):
    results = {
        "cycle": cycle,
        "timestamp": datetime.now().isoformat(),
        "data_sources": [],
        "errors": [],
    }

    os.makedirs(output_dir, exist_ok=True)

    # 1. Market Data
    print("  [1/8] Fetching market data snapshot...")
    try:
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
                results["errors"].append(f"Market {name}: {str(e)}")

        with open(os.path.join(output_dir, "market_snapshot.json"), "w", encoding="utf-8") as f:
            json.dump(market_snapshot, f, indent=2)
        results["data_sources"].append("market_snapshot")
        print(f"    [OK] {len(market_snapshot)} indices fetched")

    except Exception as e:
        results["errors"].append(f"Market snapshot: {str(e)}")
        print(f"    [FAIL] {e}")

    # 2. Stock Analysis
    print("  [2/8] Running stock analysis...")
    SAMPLE_TICKERS = ["AAPL", "NVDA", "XOM", "JPM", "TSLA", "JNJ", "AMZN", "BA"]
    stock_data = {}

    for ticker_str in SAMPLE_TICKERS:
        try:
            import yfinance as yf
            ticker = yf.Ticker(ticker_str)
            hist = ticker.history(period="2y")
            info = ticker.info or {}

            if len(hist) < 50:
                continue

            returns = hist["Close"].pct_change().dropna()
            log_returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()

            annual_return = float((1 + returns.mean()) ** 252 - 1) * 100
            annual_vol = float(returns.std() * np.sqrt(252)) * 100
            sharpe = annual_return / annual_vol if annual_vol > 0 else 0

            cummax = hist["Close"].cummax()
            drawdown = ((hist["Close"] - cummax) / cummax)
            max_drawdown = float(drawdown.min()) * 100
            current_drawdown = float(drawdown.iloc[-1]) * 100

            price_now = float(hist["Close"].iloc[-1])
            price_1m = float(hist["Close"].iloc[-22]) if len(hist) > 22 else price_now
            price_3m = float(hist["Close"].iloc[-63]) if len(hist) > 63 else price_now
            price_6m = float(hist["Close"].iloc[-126]) if len(hist) > 126 else price_now
            price_1y = float(hist["Close"].iloc[-252]) if len(hist) > 252 else price_now

            # Analyst targets
            target_mean = target_low = target_high = None
            try:
                targets = ticker.analyst_price_targets
                if targets is not None:
                    if hasattr(targets, "get"):
                        target_mean = targets.get("mean") or targets.get("current")
                        target_low = targets.get("low")
                        target_high = targets.get("high")
                    else:
                        target_mean = getattr(targets, "mean", None) or getattr(targets, "current", None)
                        target_low = getattr(targets, "low", None)
                        target_high = getattr(targets, "high", None)
            except:
                pass

            # Monte Carlo
            n_sims = 1000
            n_steps = 252
            mu = float(log_returns.mean())
            sigma = float(log_returns.std())

            paths = np.zeros((n_sims, n_steps))
            paths[:, 0] = price_now
            for t in range(1, n_steps):
                z = np.random.standard_normal(n_sims)
                paths[:, t] = paths[:, t-1] * np.exp((mu - 0.5 * sigma**2) + sigma * z)

            terminal = paths[:, -1]

            mc_results = {
                "n_simulations": n_sims,
                "horizon_days": n_steps,
                "start_price": round(price_now, 2),
                "median_price": round(float(np.median(terminal)), 2),
                "mean_price": round(float(np.mean(terminal)), 2),
                "p5": round(float(np.percentile(terminal, 5)), 2),
                "p25": round(float(np.percentile(terminal, 25)), 2),
                "p75": round(float(np.percentile(terminal, 75)), 2),
                "p95": round(float(np.percentile(terminal, 95)), 2),
                "prob_above_current": round(float(np.mean(terminal > price_now)) * 100, 1),
                "prob_20pct_drawdown": round(float(np.mean(terminal < price_now * 0.8)) * 100, 1),
                "expected_return_pct": round(float((np.mean(terminal) / price_now - 1) * 100), 2),
                "median_return_pct": round(float((np.median(terminal) / price_now - 1) * 100), 2),
            }

            theoretical_drift = mu * n_steps
            actual_mean_log_return = float(np.mean(np.log(terminal / price_now)))
            drift_error_pct = abs(actual_mean_log_return - theoretical_drift) / abs(theoretical_drift) * 100 if theoretical_drift != 0 else 0

            stock_data[ticker_str] = {
                "ticker": ticker_str,
                "sector": info.get("sector", "Unknown"),
                "current_price": round(price_now, 2),
                "market_cap_b": round(info.get("marketCap", 0) / 1e9, 1),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "returns": {
                    "1m_pct": round((price_now / price_1m - 1) * 100, 2),
                    "3m_pct": round((price_now / price_3m - 1) * 100, 2),
                    "6m_pct": round((price_now / price_6m - 1) * 100, 2),
                    "1y_pct": round((price_now / price_1y - 1) * 100, 2),
                    "annualized_pct": round(annual_return, 2),
                },
                "risk": {
                    "annual_volatility_pct": round(annual_vol, 2),
                    "sharpe_ratio": round(sharpe, 3),
                    "max_drawdown_pct": round(max_drawdown, 2),
                    "current_drawdown_pct": round(current_drawdown, 2),
                },
                "analyst_targets": {
                    "mean": round(float(target_mean), 2) if target_mean else None,
                    "low": round(float(target_low), 2) if target_low else None,
                    "high": round(float(target_high), 2) if target_high else None,
                    "upside_to_mean_pct": round((float(target_mean) / price_now - 1) * 100, 2) if target_mean else None,
                },
                "monte_carlo": mc_results,
                "mc_quality": {
                    "drift_error_pct": round(drift_error_pct, 2),
                    "drift_accurate": drift_error_pct < 5,
                },
                "statistics": {
                    "daily_mean_return": round(mu * 100, 5),
                    "daily_volatility": round(sigma * 100, 4),
                    "skewness": round(float(returns.skew()), 3),
                    "kurtosis": round(float(returns.kurtosis()), 3),
                },
            }
            print(f"    [OK] {ticker_str}: ${price_now:.0f}, MC drift err={drift_error_pct:.1f}%")

        except Exception as e:
            results["errors"].append(f"Stock {ticker_str}: {str(e)}")
            print(f"    [FAIL] {ticker_str}: {e}")

    with open(os.path.join(output_dir, "stock_analysis.json"), "w", encoding="utf-8") as f:
        json.dump(stock_data, f, indent=2)
    results["data_sources"].append("stock_analysis")

    # 3. S&P 500 Monte Carlo
    print("  [3/8] Running S&P 500 Monte Carlo...")
    try:
        import yfinance as yf
        sp = yf.Ticker("^GSPC")
        sp_hist = sp.history(period="5y")
        sp_returns = np.log(sp_hist["Close"] / sp_hist["Close"].shift(1)).dropna()

        sp_price = float(sp_hist["Close"].iloc[-1])
        sp_mu = float(sp_returns.mean())
        sp_sigma = float(sp_returns.std())

        n_sims = 5000
        horizons = {"1y": 252, "3y": 756, "5y": 1260}
        sp500_mc = {"start_price": round(sp_price, 2)}

        for label, steps in horizons.items():
            paths = np.zeros((n_sims, steps))
            paths[:, 0] = sp_price
            for t in range(1, steps):
                z = np.random.standard_normal(n_sims)
                paths[:, t] = paths[:, t-1] * np.exp((sp_mu - 0.5 * sp_sigma**2) + sp_sigma * z)

            term = paths[:, -1]
            sp500_mc[label] = {
                "median_price": round(float(np.median(term)), 2),
                "mean_price": round(float(np.mean(term)), 2),
                "p5": round(float(np.percentile(term, 5)), 2),
                "p95": round(float(np.percentile(term, 95)), 2),
                "prob_positive": round(float(np.mean(term > sp_price)) * 100, 1),
                "prob_20pct_crash": round(float(np.mean(term < sp_price * 0.8)) * 100, 1),
                "expected_annual_return_pct": round(float((np.mean(term) / sp_price) ** (252/steps) - 1) * 100, 2),
            }

        # Quality check
        paths_1y = np.zeros((5000, 252))
        paths_1y[:, 0] = sp_price
        for t in range(1, 252):
            z = np.random.standard_normal(5000)
            paths_1y[:, t] = paths_1y[:, t-1] * np.exp((sp_mu - 0.5 * sp_sigma**2) + sp_sigma * z)

        theoretical = sp_mu * 252
        actual = float(np.mean(np.log(paths_1y[:, -1] / sp_price)))
        sp500_mc["quality_check"] = {
            "theoretical_1y_drift": round(theoretical, 5),
            "actual_1y_mean_log_return": round(actual, 5),
            "drift_error_pct": round(abs(actual - theoretical) / abs(theoretical) * 100 if theoretical != 0 else 0, 2),
            "variance_ratio": round(float(np.var(np.log(paths_1y[:, -1] / sp_price))) / (sp_sigma**2 * 252), 3),
        }

        with open(os.path.join(output_dir, "sp500_monte_carlo.json"), "w", encoding="utf-8") as f:
            json.dump(sp500_mc, f, indent=2)
        results["data_sources"].append("sp500_monte_carlo")
        print(f"    [OK] S&P 500 MC: drift err={sp500_mc['quality_check']['drift_error_pct']:.1f}%")

    except Exception as e:
        results["errors"].append(f"SP500 MC: {str(e)}")
        print(f"    [FAIL] {e}")

    # 4. Random Portfolios
    print("  [4/8] Generating random portfolios...")
    try:
        portfolios = generate_random_portfolios(5)
        with open(os.path.join(output_dir, "random_portfolios.json"), "w", encoding="utf-8") as f:
            json.dump(portfolios, f, indent=2)
        results["data_sources"].append("random_portfolios")
        print(f"    [OK] {len(portfolios)} portfolios generated")
    except Exception as e:
        results["errors"].append(f"Portfolios: {str(e)}")

    # 5. Engine services
    print("  [5/8] Attempting engine service calls...")
    engine_services = []

    service_imports = [
        ("crash_model", "backend.services.crash_model", "CrashModel"),
        ("regime_detector", "backend.services.regime_detector", "RegimeDetector"),
        ("risk_scorer", "backend.services.risk_scorer", "RiskScorer"),
        ("signal_engine", "backend.services.signal_engine", "SignalEngine"),
    ]

    for name, module_path, class_name in service_imports:
        try:
            mod = __import__(module_path, fromlist=[class_name])
            engine_services.append(name)
            print(f"    [OK] {name}: available")
        except Exception as e:
            print(f"    [SKIP] {name}: {type(e).__name__}")

    results["engine_services_available"] = engine_services

    # 6. Cross-asset correlations
    print("  [6/8] Computing cross-asset correlations...")
    try:
        import yfinance as yf
        import pandas as pd

        assets = ["^GSPC", "^VIX", "^TNX", "GC=F", "CL=F", "DX-Y.NYB"]
        asset_names = ["SP500", "VIX", "10Y_Yield", "Gold", "Oil", "USD"]

        dfs = {}
        for asset, aname in zip(assets, asset_names):
            try:
                h = yf.Ticker(asset).history(period="1y")
                if len(h) > 0:
                    dfs[aname] = h["Close"].pct_change().dropna()
            except:
                pass

        if len(dfs) >= 3:
            combined = pd.DataFrame(dfs).dropna()
            corr_matrix = combined.corr()

            correlations = {
                "matrix": {k: {k2: round(v2, 3) for k2, v2 in v.items()} for k, v in corr_matrix.to_dict().items()},
                "period": "1Y daily returns",
                "n_observations": len(combined),
            }

            with open(os.path.join(output_dir, "cross_asset_correlations.json"), "w", encoding="utf-8") as f:
                json.dump(correlations, f, indent=2)
            results["data_sources"].append("cross_asset_correlations")
            print(f"    [OK] {len(dfs)} assets, {len(combined)} observations")

    except Exception as e:
        results["errors"].append(f"Correlations: {str(e)}")
        print(f"    [FAIL] {e}")

    # 7. Backtest
    print("  [7/8] Running historical accuracy backtest...")
    try:
        import yfinance as yf
        sp = yf.Ticker("^GSPC")
        sp_hist = sp.history(period="2y")

        if len(sp_hist) > 252 + 63:
            accuracy_tests = []
            test_points = [252, 189, 126]

            for start_idx in test_points:
                if start_idx + 63 > len(sp_hist):
                    continue

                test_start_price = float(sp_hist["Close"].iloc[-(start_idx)])
                actual_price = float(sp_hist["Close"].iloc[-(start_idx - 63)])
                actual_return = (actual_price / test_start_price - 1) * 100

                pre_test = sp_hist.iloc[:-(start_idx)]
                pre_returns = np.log(pre_test["Close"] / pre_test["Close"].shift(1)).dropna()

                if len(pre_returns) < 60:
                    continue

                pred_mu = float(pre_returns.mean())
                pred_sigma = float(pre_returns.std())

                sims = np.zeros((2000, 63))
                sims[:, 0] = test_start_price
                for t in range(1, 63):
                    z = np.random.standard_normal(2000)
                    sims[:, t] = sims[:, t-1] * np.exp((pred_mu - 0.5 * pred_sigma**2) + pred_sigma * z)

                mc_terminal = sims[:, -1]
                mc_median_return = float((np.median(mc_terminal) / test_start_price - 1) * 100)

                accuracy_tests.append({
                    "test_start": str(sp_hist.index[-(start_idx)].date()),
                    "horizon_days": 63,
                    "actual_return_pct": round(actual_return, 2),
                    "mc_median_return_pct": round(mc_median_return, 2),
                    "direction_correct": (actual_return > 0) == (mc_median_return > 0),
                    "absolute_error_pct": round(abs(actual_return - mc_median_return), 2),
                })

            direction_acc = sum(1 for t in accuracy_tests if t["direction_correct"]) / len(accuracy_tests) * 100 if accuracy_tests else 0
            mean_ae = np.mean([t["absolute_error_pct"] for t in accuracy_tests]) if accuracy_tests else 0

            backtest_results = {
                "tests": accuracy_tests,
                "summary": {
                    "n_tests": len(accuracy_tests),
                    "direction_accuracy_pct": round(direction_acc, 1),
                    "mean_absolute_error_pct": round(float(mean_ae), 2),
                },
            }

            with open(os.path.join(output_dir, "backtest_accuracy.json"), "w", encoding="utf-8") as f:
                json.dump(backtest_results, f, indent=2)
            results["data_sources"].append("backtest_accuracy")
            print(f"    [OK] Direction accuracy: {direction_acc:.0f}%, MAE: {mean_ae:.1f}%")

    except Exception as e:
        results["errors"].append(f"Backtest: {str(e)}")
        print(f"    [FAIL] {e}")

    # 8. Quality summary
    print("  [8/8] Computing quality metrics...")

    quality_metrics = {
        "mc_drift_errors": {},
        "data_completeness": len(results["data_sources"]),
        "errors_count": len(results["errors"]),
        "engine_services_active": len(engine_services),
    }

    for ticker_str, data in stock_data.items():
        if "mc_quality" in data:
            quality_metrics["mc_drift_errors"][ticker_str] = data["mc_quality"]["drift_error_pct"]

    results["quality_metrics"] = quality_metrics

    with open(os.path.join(output_dir, "run_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n  Data generation complete: {len(results['data_sources'])} sources, {len(results['errors'])} errors")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cycle", type=int, default=1)
    args = parser.parse_args()

    run_engine_data_collection(args.output_dir, args.cycle)
