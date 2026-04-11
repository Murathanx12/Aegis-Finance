"""
Aegis Finance - Lab Results Comparator v2
Compares engine output before and after Claude's changes.
Now tracks signal quality, test results, and more dimensions.
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


def compare_mc_quality(before_dir, after_dir):
    before_stocks = load_json_safe(os.path.join(before_dir, "stock_analysis.json")) or {}
    after_stocks = load_json_safe(os.path.join(after_dir, "stock_analysis.json")) or {}

    drift_before = {}
    drift_after = {}

    for t, d in before_stocks.items():
        if "mc_quality" in d:
            drift_before[t] = d["mc_quality"]["drift_error_pct"]

    for t, d in after_stocks.items():
        if "mc_quality" in d:
            drift_after[t] = d["mc_quality"]["drift_error_pct"]

    common = set(drift_before.keys()) & set(drift_after.keys())
    if not common:
        return {"status": "no_comparable_data"}

    avg_before = sum(drift_before[t] for t in common) / len(common)
    avg_after = sum(drift_after[t] for t in common) / len(common)

    return {
        "avg_drift_error_before": round(avg_before, 3),
        "avg_drift_error_after": round(avg_after, 3),
        "delta": round(avg_after - avg_before, 3),
        "improved": avg_after < avg_before - 0.01,  # need meaningful improvement
    }


def compare_sp500_mc(before_dir, after_dir):
    before_mc = load_json_safe(os.path.join(before_dir, "sp500_monte_carlo.json"))
    after_mc = load_json_safe(os.path.join(after_dir, "sp500_monte_carlo.json"))

    if not before_mc or not after_mc:
        return {"status": "no_comparable_data"}

    bq = before_mc.get("quality_check", {})
    aq = after_mc.get("quality_check", {})

    return {
        "drift_error_before": bq.get("drift_error_pct"),
        "drift_error_after": aq.get("drift_error_pct"),
        "drift_improved": (aq.get("drift_error_pct", 999) < bq.get("drift_error_pct", 999) - 0.01),
    }


def compare_backtest(before_dir, after_dir):
    before_bt = load_json_safe(os.path.join(before_dir, "backtest_accuracy.json"))
    after_bt = load_json_safe(os.path.join(after_dir, "backtest_accuracy.json"))

    if not before_bt or not after_bt:
        return {"status": "no_comparable_data"}

    bs = before_bt.get("summary", {})
    afs = after_bt.get("summary", {})

    return {
        "direction_accuracy_before": bs.get("direction_accuracy_pct"),
        "direction_accuracy_after": afs.get("direction_accuracy_pct"),
        "mae_before": bs.get("mean_absolute_error_pct"),
        "mae_after": afs.get("mean_absolute_error_pct"),
        "direction_improved": (afs.get("direction_accuracy_pct", 0) > bs.get("direction_accuracy_pct", 0) + 0.01),
        "mae_improved": (afs.get("mean_absolute_error_pct", 999) < bs.get("mean_absolute_error_pct", 999) - 0.01),
    }


def compare_signal_quality(before_dir, after_dir):
    """Compare signal engine validation metrics (new in v2)."""
    before_bt = load_json_safe(os.path.join(before_dir, "backtest_accuracy.json"))
    after_bt = load_json_safe(os.path.join(after_dir, "backtest_accuracy.json"))

    if not before_bt or not after_bt:
        return {"status": "no_comparable_data"}

    bsv = before_bt.get("signal_validation", {})
    asv = after_bt.get("signal_validation", {})

    if not bsv or not asv:
        return {"status": "no_signal_data"}

    b_dir_acc = bsv.get("signal_direction_accuracy_pct", 0)
    a_dir_acc = asv.get("signal_direction_accuracy_pct", 0)
    b_corr = bsv.get("signal_return_correlation", 0)
    a_corr = asv.get("signal_return_correlation", 0)

    # Count unique signal actions (Buy/Hold/Sell) — more diversity = better
    b_actions = set()
    a_actions = set()
    for t in bsv.get("signal_tests", []):
        b_actions.add(t.get("signal_action", "Hold"))
    for t in asv.get("signal_tests", []):
        a_actions.add(t.get("signal_action", "Hold"))

    return {
        "signal_dir_accuracy_before": b_dir_acc,
        "signal_dir_accuracy_after": a_dir_acc,
        "signal_correlation_before": b_corr,
        "signal_correlation_after": a_corr,
        "signal_actions_before": sorted(b_actions),
        "signal_actions_after": sorted(a_actions),
        "dir_accuracy_improved": a_dir_acc > b_dir_acc + 0.01,
        "correlation_improved": a_corr > b_corr + 0.001,
        "diversity_improved": len(a_actions) > len(b_actions),
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
            # Parse pytest summary line like "5 passed, 1 failed"
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
    # Infer cycle_dir from before_dir (before_dir = cycle_dir/data)
    cycle_dir = os.path.dirname(before_dir)

    comparison = {
        "mc_quality": compare_mc_quality(before_dir, after_dir),
        "sp500_mc": compare_sp500_mc(before_dir, after_dir),
        "backtest_accuracy": compare_backtest(before_dir, after_dir),
        "signal_quality": compare_signal_quality(before_dir, after_dir),
        "test_results": compare_test_results(cycle_dir),
    }

    improvements = []
    regressions = []
    neutral = []

    # MC drift
    mc = comparison["mc_quality"]
    if isinstance(mc, dict) and mc.get("improved") == True:
        improvements.append(f"MC drift error: {mc.get('avg_drift_error_before')}% -> {mc.get('avg_drift_error_after')}%")
    elif isinstance(mc, dict) and mc.get("improved") == False and mc.get("delta", 0) > 0.5:
        regressions.append(f"MC drift error: {mc.get('avg_drift_error_before')}% -> {mc.get('avg_drift_error_after')}%")
    else:
        neutral.append("MC drift: unchanged")

    # SP500 MC
    sp = comparison["sp500_mc"]
    if isinstance(sp, dict) and sp.get("drift_improved") == True:
        improvements.append("SP500 MC drift improved")
    elif isinstance(sp, dict) and sp.get("drift_improved") == False:
        if sp.get("drift_error_after", 0) > sp.get("drift_error_before", 0) + 0.5:
            regressions.append("SP500 MC drift regressed")
        else:
            neutral.append("SP500 MC drift: unchanged")

    # Backtest direction
    bt = comparison["backtest_accuracy"]
    if isinstance(bt, dict) and bt.get("direction_improved") == True:
        improvements.append(f"Direction accuracy: {bt.get('direction_accuracy_before')}% -> {bt.get('direction_accuracy_after')}%")
    elif isinstance(bt, dict) and bt.get("direction_improved") == False:
        if bt.get("direction_accuracy_after", 0) < bt.get("direction_accuracy_before", 0) - 0.5:
            regressions.append(f"Direction accuracy: {bt.get('direction_accuracy_before')}% -> {bt.get('direction_accuracy_after')}%")

    # Backtest MAE
    if isinstance(bt, dict) and bt.get("mae_improved") == True:
        improvements.append(f"MAE: {bt.get('mae_before')}% -> {bt.get('mae_after')}%")

    # Signal quality
    sq = comparison["signal_quality"]
    if isinstance(sq, dict):
        if sq.get("dir_accuracy_improved"):
            improvements.append(f"Signal accuracy: {sq.get('signal_dir_accuracy_before')}% -> {sq.get('signal_dir_accuracy_after')}%")
        if sq.get("correlation_improved"):
            improvements.append(f"Signal-return correlation: {sq.get('signal_correlation_before')} -> {sq.get('signal_correlation_after')}")
        if sq.get("diversity_improved"):
            improvements.append(f"Signal diversity: {sq.get('signal_actions_before')} -> {sq.get('signal_actions_after')}")

    # Test results
    tr = comparison["test_results"]
    if isinstance(tr, dict) and tr.get("new_failures", 0) > 0:
        regressions.append(f"NEW test failures: {tr.get('new_failures')}")

    comparison["improvements"] = improvements
    comparison["regressions"] = regressions
    comparison["neutral"] = neutral

    if regressions:
        comparison["net_result"] = "regressed"
    elif improvements:
        comparison["net_result"] = "improved"
    else:
        comparison["net_result"] = "neutral"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    print(f"\n  Comparison results:")
    print(f"    Improvements: {len(improvements)}")
    for i in improvements:
        print(f"      [OK] {i}")
    print(f"    Regressions: {len(regressions)}")
    for r in regressions:
        print(f"      [FAIL] {r}")
    print(f"    Neutral: {len(neutral)}")
    print(f"    Net result: {comparison['net_result']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    run_comparison(args.before, args.after, args.output)
