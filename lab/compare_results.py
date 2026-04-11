"""
Aegis Finance - Lab Results Comparator v3
Comprehensive comparison across ALL engine dimensions:
- Stock analysis quality (real service output)
- Crash model calibration
- Signal differentiation
- Sector analysis quality
- Service health
- Code quality metrics
- Test suite changes
"""

import argparse
import json
import os


def load_json_safe(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


def compare_stock_analysis(before_dir, after_dir):
    """Compare REAL analyze_stock() output."""
    before = load_json_safe(os.path.join(before_dir, "stock_analysis.json")) or {}
    after = load_json_safe(os.path.join(after_dir, "stock_analysis.json")) or {}

    if not before or not after:
        return {"status": "no_data"}

    b_working = len([v for v in before.values() if isinstance(v, dict) and v.get("current_price")])
    a_working = len([v for v in after.values() if isinstance(v, dict) and v.get("current_price")])

    # GARCH quality
    b_garch = len([v for v in before.values() if isinstance(v, dict) and v.get("garch_vol")])
    a_garch = len([v for v in after.values() if isinstance(v, dict) and v.get("garch_vol")])

    # Signal coverage
    b_signals = len([v for v in before.values() if isinstance(v, dict) and v.get("signal_action")])
    a_signals = len([v for v in after.values() if isinstance(v, dict) and v.get("signal_action")])

    # Return differentiation
    b_returns = [v.get("mc_median_5y") for v in before.values() if isinstance(v, dict) and v.get("mc_median_5y") is not None]
    a_returns = [v.get("mc_median_5y") for v in after.values() if isinstance(v, dict) and v.get("mc_median_5y") is not None]

    b_spread = max(b_returns) - min(b_returns) if len(b_returns) >= 2 else 0
    a_spread = max(a_returns) - min(a_returns) if len(a_returns) >= 2 else 0

    return {
        "tickers_working_before": b_working,
        "tickers_working_after": a_working,
        "garch_fits_before": b_garch,
        "garch_fits_after": a_garch,
        "signals_before": b_signals,
        "signals_after": a_signals,
        "return_spread_before": round(b_spread, 2),
        "return_spread_after": round(a_spread, 2),
        "more_tickers_working": a_working > b_working,
        "better_garch_coverage": a_garch > b_garch,
        "better_differentiation": a_spread > b_spread + 1,
    }


def compare_crash_calibration(before_dir, after_dir):
    """Compare crash model quality."""
    before = load_json_safe(os.path.join(before_dir, "crash_calibration.json")) or {}
    after = load_json_safe(os.path.join(after_dir, "crash_calibration.json")) or {}

    if before.get("status") or after.get("status"):
        return {"status": "no_comparable_data"}

    result = {}

    # Monotonicity
    result["monotonic_before"] = before.get("monotonic", False)
    result["monotonic_after"] = after.get("monotonic", False)

    # Range compliance (5%-55%)
    for horizon in ["crash_prob_3m", "crash_prob_6m", "crash_prob_12m"]:
        b_ok = before.get(f"{horizon}_in_range", False)
        a_ok = after.get(f"{horizon}_in_range", False)
        result[f"{horizon}_in_range_before"] = b_ok
        result[f"{horizon}_in_range_after"] = a_ok

    # Feature count
    result["n_features_before"] = before.get("n_features", 0)
    result["n_features_after"] = after.get("n_features", 0)

    return result


def compare_signal_quality(before_dir, after_dir):
    """Compare signal engine differentiation."""
    before = load_json_safe(os.path.join(before_dir, "signal_quality.json")) or {}
    after = load_json_safe(os.path.join(after_dir, "signal_quality.json")) or {}

    if before.get("status") or after.get("status"):
        return {"status": "no_comparable_data"}

    b_div = before.get("diversity", {})
    a_div = after.get("diversity", {})

    return {
        "n_unique_actions_before": b_div.get("n_unique_actions", 0),
        "n_unique_actions_after": a_div.get("n_unique_actions", 0),
        "score_spread_before": b_div.get("score_spread", 0),
        "score_spread_after": a_div.get("score_spread", 0),
        "all_same_before": b_div.get("all_same_action", True),
        "all_same_after": a_div.get("all_same_action", True),
        "tickers_with_signal_before": before.get("n_tickers_with_signal", 0),
        "tickers_with_signal_after": after.get("n_tickers_with_signal", 0),
        "better_diversity": a_div.get("n_unique_actions", 0) > b_div.get("n_unique_actions", 0),
        "better_spread": a_div.get("score_spread", 0) > b_div.get("score_spread", 0) + 0.01,
        "more_signals": after.get("n_tickers_with_signal", 0) > before.get("n_tickers_with_signal", 0),
    }


def compare_sector_analysis(before_dir, after_dir):
    """Compare sector analysis quality."""
    before = load_json_safe(os.path.join(before_dir, "sector_analysis.json")) or {}
    after = load_json_safe(os.path.join(after_dir, "sector_analysis.json")) or {}

    if before.get("status") or after.get("status"):
        return {"status": "no_comparable_data"}

    b_diff = before.get("differentiation", {})
    a_diff = after.get("differentiation", {})

    return {
        "n_sectors_before": before.get("n_sectors", 0),
        "n_sectors_after": after.get("n_sectors", 0),
        "return_spread_before": b_diff.get("return_spread", 0),
        "return_spread_after": a_diff.get("return_spread", 0),
        "better_differentiation": a_diff.get("return_spread", 0) > b_diff.get("return_spread", 0) + 1,
    }


def compare_api_health(before_dir, after_dir):
    """Compare service health."""
    before = load_json_safe(os.path.join(before_dir, "api_health.json")) or {}
    after = load_json_safe(os.path.join(after_dir, "api_health.json")) or {}

    b_ok = len([v for v in before.values() if isinstance(v, dict) and v.get("status") == "ok"])
    a_ok = len([v for v in after.values() if isinstance(v, dict) and v.get("status") == "ok"])
    b_err = len([v for v in before.values() if isinstance(v, dict) and v.get("status") == "error"])
    a_err = len([v for v in after.values() if isinstance(v, dict) and v.get("status") == "error"])

    return {
        "healthy_before": b_ok,
        "healthy_after": a_ok,
        "errors_before": b_err,
        "errors_after": a_err,
        "more_healthy": a_ok > b_ok,
        "fewer_errors": a_err < b_err,
    }


def compare_code_metrics(before_dir, after_dir):
    """Compare code quality."""
    before = load_json_safe(os.path.join(before_dir, "code_metrics.json")) or {}
    after = load_json_safe(os.path.join(after_dir, "code_metrics.json")) or {}

    b_tests = before.get("test_count", {}).get("test_functions", 0)
    a_tests = after.get("test_count", {}).get("test_functions", 0)
    b_smells = before.get("n_smells", 0)
    a_smells = after.get("n_smells", 0)

    b_ts = before.get("frontend_type_errors", 0)
    a_ts = after.get("frontend_type_errors", 0)
    b_ts = b_ts if isinstance(b_ts, int) else 0
    a_ts = a_ts if isinstance(a_ts, int) else 0

    return {
        "test_count_before": b_tests,
        "test_count_after": a_tests,
        "tests_added": a_tests - b_tests,
        "code_smells_before": b_smells,
        "code_smells_after": a_smells,
        "smells_fixed": b_smells - a_smells,
        "ts_errors_before": b_ts,
        "ts_errors_after": a_ts,
        "more_tests": a_tests > b_tests,
        "fewer_smells": a_smells < b_smells,
        "fewer_ts_errors": a_ts < b_ts,
    }


def compare_test_results(cycle_dir):
    """Compare test pass/fail from the cycle's test run."""
    test_file = os.path.join(cycle_dir, "test_results.txt")
    new_failures_file = os.path.join(cycle_dir, "new_failures.txt")

    result = {"status": "no_test_data"}

    if os.path.exists(test_file):
        try:
            with open(test_file, encoding="utf-8") as f:
                content = f.read()
            import re
            passed = re.search(r"(\d+) passed", content)
            failed = re.search(r"(\d+) failed", content)
            result = {
                "passed": int(passed.group(1)) if passed else 0,
                "failed": int(failed.group(1)) if failed else 0,
                "new_failures": 0,
            }
        except:
            pass

    if os.path.exists(new_failures_file):
        try:
            with open(new_failures_file, encoding="utf-8") as f:
                new_fails = [l.strip() for l in f if l.strip()]
            result["new_failures"] = len(new_fails)
            if new_fails:
                result["new_failure_names"] = new_fails
        except:
            pass

    return result


def run_comparison(before_dir, after_dir, output_path):
    cycle_dir = os.path.dirname(before_dir)

    comparison = {
        "stock_analysis": compare_stock_analysis(before_dir, after_dir),
        "crash_calibration": compare_crash_calibration(before_dir, after_dir),
        "signal_quality": compare_signal_quality(before_dir, after_dir),
        "sector_analysis": compare_sector_analysis(before_dir, after_dir),
        "api_health": compare_api_health(before_dir, after_dir),
        "code_metrics": compare_code_metrics(before_dir, after_dir),
        "test_results": compare_test_results(cycle_dir),
    }

    # Collect improvements and regressions
    improvements = []
    regressions = []
    neutral = []

    # Stock analysis
    sa = comparison["stock_analysis"]
    if isinstance(sa, dict) and sa.get("status") != "no_data":
        if sa.get("more_tickers_working"):
            improvements.append(f"More stocks working: {sa['tickers_working_before']} -> {sa['tickers_working_after']}")
        if sa.get("better_garch_coverage"):
            improvements.append(f"Better GARCH coverage: {sa['garch_fits_before']} -> {sa['garch_fits_after']}")
        if sa.get("better_differentiation"):
            improvements.append(f"Better return differentiation: spread {sa['return_spread_before']}% -> {sa['return_spread_after']}%")

    # Signal quality
    sq = comparison["signal_quality"]
    if isinstance(sq, dict) and sq.get("status") != "no_comparable_data":
        if sq.get("better_diversity"):
            improvements.append(f"Better signal diversity: {sq['n_unique_actions_before']} -> {sq['n_unique_actions_after']} actions")
        if sq.get("better_spread"):
            improvements.append(f"Better signal spread: {sq['score_spread_before']} -> {sq['score_spread_after']}")
        if sq.get("more_signals"):
            improvements.append(f"More tickers with signals: {sq['tickers_with_signal_before']} -> {sq['tickers_with_signal_after']}")

    # Sector analysis
    sec = comparison["sector_analysis"]
    if isinstance(sec, dict) and sec.get("status") != "no_comparable_data":
        if sec.get("better_differentiation"):
            improvements.append(f"Better sector differentiation: spread {sec['return_spread_before']}% -> {sec['return_spread_after']}%")

    # API health
    ah = comparison["api_health"]
    if isinstance(ah, dict):
        if ah.get("more_healthy"):
            improvements.append(f"More healthy services: {ah['healthy_before']} -> {ah['healthy_after']}")
        if ah.get("fewer_errors"):
            improvements.append(f"Fewer service errors: {ah['errors_before']} -> {ah['errors_after']}")

    # Code metrics
    cm = comparison["code_metrics"]
    if isinstance(cm, dict):
        if cm.get("more_tests"):
            improvements.append(f"Tests added: {cm['tests_added']} new ({cm['test_count_before']} -> {cm['test_count_after']})")
        if cm.get("fewer_smells"):
            improvements.append(f"Code smells fixed: {cm['smells_fixed']} ({cm['code_smells_before']} -> {cm['code_smells_after']})")
        if cm.get("fewer_ts_errors"):
            improvements.append(f"TS errors fixed: {cm['ts_errors_before']} -> {cm['ts_errors_after']}")

    # Test results
    tr = comparison["test_results"]
    if isinstance(tr, dict) and tr.get("new_failures", 0) > 0:
        regressions.append(f"NEW test failures: {tr['new_failures']}")

    comparison["improvements"] = improvements
    comparison["regressions"] = regressions
    comparison["neutral"] = neutral

    if regressions:
        comparison["net_result"] = "regressed"
    elif improvements:
        comparison["net_result"] = "improved"
    else:
        comparison["net_result"] = "neutral"

    comparison["improvement_count"] = len(improvements)
    comparison["regression_count"] = len(regressions)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    print(f"\n  Comparison results:")
    print(f"    Improvements: {len(improvements)}")
    for i in improvements:
        print(f"      [OK] {i}")
    print(f"    Regressions: {len(regressions)}")
    for r in regressions:
        print(f"      [FAIL] {r}")
    print(f"    Net result: {comparison['net_result']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    run_comparison(args.before, args.after, args.output)
