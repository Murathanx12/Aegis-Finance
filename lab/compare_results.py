"""
Aegis Finance - Lab Results Comparator v4
Compares real backend output + stress tests + consistency checks.
"""

import argparse
import json
import os
import re


def load_json_safe(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


def run_comparison(before_dir, after_dir, output_path):
    cycle_dir = os.path.dirname(before_dir)

    improvements = []
    regressions = []
    comparison = {}

    # Stress tests: compare pass counts
    b_stress = load_json_safe(os.path.join(before_dir, "stress_tests.json")) or []
    a_stress = load_json_safe(os.path.join(after_dir, "stress_tests.json")) or []
    b_pass = sum(1 for t in b_stress if t.get("pass"))
    a_pass = sum(1 for t in a_stress if t.get("pass"))
    comparison["stress_tests"] = {
        "before": f"{b_pass}/{len(b_stress)}", "after": f"{a_pass}/{len(a_stress)}",
    }
    if a_pass > b_pass:
        improvements.append(f"Stress tests: {b_pass}/{len(b_stress)} -> {a_pass}/{len(a_stress)}")
    elif a_pass < b_pass:
        regressions.append(f"Stress tests: {b_pass}/{len(b_stress)} -> {a_pass}/{len(a_stress)}")

    # Consistency checks
    b_consist = load_json_safe(os.path.join(before_dir, "consistency_checks.json")) or []
    a_consist = load_json_safe(os.path.join(after_dir, "consistency_checks.json")) or []
    b_cp = sum(1 for c in b_consist if c.get("pass"))
    a_cp = sum(1 for c in a_consist if c.get("pass"))
    comparison["consistency"] = {"before": f"{b_cp}/{len(b_consist)}", "after": f"{a_cp}/{len(a_consist)}"}
    if a_cp > b_cp:
        improvements.append(f"Consistency: {b_cp}/{len(b_consist)} -> {a_cp}/{len(a_consist)}")
    elif a_cp < b_cp:
        regressions.append(f"Consistency regressed")

    # Backtest
    b_bt = load_json_safe(os.path.join(before_dir, "backtest_accuracy.json")) or {}
    a_bt = load_json_safe(os.path.join(after_dir, "backtest_accuracy.json")) or {}
    b_acc = b_bt.get("direction_accuracy_pct", 0)
    a_acc = a_bt.get("direction_accuracy_pct", 0)
    b_corr = b_bt.get("signal_return_correlation", 0)
    a_corr = a_bt.get("signal_return_correlation", 0)
    comparison["backtest"] = {
        "accuracy_before": b_acc, "accuracy_after": a_acc,
        "correlation_before": b_corr, "correlation_after": a_corr,
    }
    if a_acc > b_acc + 1:
        improvements.append(f"Backtest accuracy: {b_acc}% -> {a_acc}%")
    if a_corr > b_corr + 0.02:
        improvements.append(f"Signal correlation: {b_corr} -> {a_corr}")

    # Signal diversity
    b_sig = load_json_safe(os.path.join(before_dir, "signal_results.json")) or {}
    a_sig = load_json_safe(os.path.join(after_dir, "signal_results.json")) or {}
    b_actions = set(s.get("action") for s in b_sig.get("stock_signals", {}).values())
    a_actions = set(s.get("action") for s in a_sig.get("stock_signals", {}).values())
    comparison["signals"] = {"actions_before": sorted(b_actions), "actions_after": sorted(a_actions)}
    if len(a_actions) > len(b_actions):
        improvements.append(f"Signal diversity: {sorted(b_actions)} -> {sorted(a_actions)}")

    # Test results
    test_file = os.path.join(cycle_dir, "test_results.txt")
    new_fail_file = os.path.join(cycle_dir, "new_failures.txt")
    if os.path.exists(test_file):
        with open(test_file, encoding="utf-8") as f:
            content = f.read()
        passed = re.search(r"(\d+) passed", content)
        failed = re.search(r"(\d+) failed", content)
        comparison["tests"] = {
            "passed": int(passed.group(1)) if passed else 0,
            "failed": int(failed.group(1)) if failed else 0,
        }
    if os.path.exists(new_fail_file):
        with open(new_fail_file, encoding="utf-8") as f:
            new_fails = [l.strip() for l in f if l.strip()]
        if new_fails:
            regressions.append(f"NEW test failures: {len(new_fails)}")

    comparison["improvements"] = improvements
    comparison["regressions"] = regressions
    comparison["net_result"] = "regressed" if regressions else ("improved" if improvements else "neutral")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    print(f"\n  Comparison:")
    print(f"    Improvements: {len(improvements)}")
    for i in improvements:
        print(f"      [OK] {i}")
    print(f"    Regressions: {len(regressions)}")
    for r in regressions:
        print(f"      [FAIL] {r}")
    print(f"    Net: {comparison['net_result']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run_comparison(args.before, args.after, args.output)
