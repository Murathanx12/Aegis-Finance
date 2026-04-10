"""
Aegis Finance - Lab Results Comparator
Compares engine output before and after Claude's changes.
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
        "improved": avg_after < avg_before,
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
        "drift_improved": (aq.get("drift_error_pct", 999) < bq.get("drift_error_pct", 999)),
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
        "direction_improved": (afs.get("direction_accuracy_pct", 0) > bs.get("direction_accuracy_pct", 0)),
        "mae_improved": (afs.get("mean_absolute_error_pct", 999) < bs.get("mean_absolute_error_pct", 999)),
    }


def run_comparison(before_dir, after_dir, output_path):
    comparison = {
        "mc_quality": compare_mc_quality(before_dir, after_dir),
        "sp500_mc": compare_sp500_mc(before_dir, after_dir),
        "backtest_accuracy": compare_backtest(before_dir, after_dir),
    }

    improvements = []
    regressions = []

    mc = comparison["mc_quality"]
    if isinstance(mc, dict) and mc.get("improved") == True:
        improvements.append(f"MC drift error: {mc.get('avg_drift_error_before')}% -> {mc.get('avg_drift_error_after')}%")
    elif isinstance(mc, dict) and mc.get("improved") == False:
        regressions.append(f"MC drift error: {mc.get('avg_drift_error_before')}% -> {mc.get('avg_drift_error_after')}%")

    sp = comparison["sp500_mc"]
    if isinstance(sp, dict) and sp.get("drift_improved") == True:
        improvements.append("SP500 MC drift improved")
    elif isinstance(sp, dict) and sp.get("drift_improved") == False:
        regressions.append("SP500 MC drift regressed")

    bt = comparison["backtest_accuracy"]
    if isinstance(bt, dict) and bt.get("direction_improved") == True:
        improvements.append(f"Direction accuracy: {bt.get('direction_accuracy_before')}% -> {bt.get('direction_accuracy_after')}%")
    elif isinstance(bt, dict) and bt.get("direction_improved") == False:
        regressions.append(f"Direction accuracy: {bt.get('direction_accuracy_before')}% -> {bt.get('direction_accuracy_after')}%")

    comparison["improvements"] = improvements
    comparison["regressions"] = regressions
    comparison["net_result"] = "improved" if len(improvements) > len(regressions) else ("regressed" if regressions else "neutral")

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
