"""
Aegis Finance - Lab Prompt Builder v5
Unleashes Claude as an autonomous quant researcher.
"""

import argparse
import json
import os
import glob
from pathlib import Path
from datetime import datetime


def load_json_safe(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


def collect_past_learnings(experiments_dir, current_cycle):
    learnings = []
    for cycle_num in range(max(1, current_cycle - 8), current_cycle):  # last 8 cycles only
        cycle_id = f"cycle_{cycle_num:03d}"
        report = load_json_safe(os.path.join(experiments_dir, cycle_id, "experiment_report.json"))
        if report:
            improved = report.get("results", {}).get("improved", False)
            tests_written = report.get("tests_written", [])
            learnings.append(f"""### Cycle {cycle_num} — {'IMPROVED' if improved else 'NO IMPROVEMENT'}
Noticed: {report.get('what_i_noticed', '?')[:200]}
Did: {report.get('what_i_did', '?')[:200]}
Tests written: {tests_written if tests_written else 'none'}
Next: {report.get('next_steps', '?')[:150]}
Files: {', '.join(report.get('files_modified', []))}""")
    return "\n\n".join(learnings) if learnings else "First cycle. No history."


def load_baseline_failures(path):
    if not path or not os.path.exists(path):
        return "No baseline data."
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or "All tests passing."
    except:
        return "Could not read."


def build_prompt(cycle_dir, experiments_dir, cycle, output_path, baseline_failures_path=None):
    data_dir = os.path.join(cycle_dir, "data")
    all_data = {}
    if os.path.isdir(data_dir):
        for f in glob.glob(os.path.join(data_dir, "*.json")):
            all_data[Path(f).stem] = load_json_safe(f)

    # Show full data for critical sections, truncate the rest
    data_sections = []
    priority_keys = ["stress_tests", "consistency_checks", "crash_predictions",
                     "signal_results", "backtest_accuracy", "reality_checks"]
    for key in priority_keys:
        if key in all_data and all_data[key]:
            data_str = json.dumps(all_data[key], indent=2)
            if len(data_str) > 6000:
                data_str = data_str[:6000] + "\n... [truncated]"
            data_sections.append(f"### {key}\n```json\n{data_str}\n```")

    for key, data in all_data.items():
        if key in priority_keys or data is None:
            continue
        data_str = json.dumps(data, indent=2)
        if len(data_str) > 3000:
            data_str = data_str[:3000] + "\n... [truncated]"
        data_sections.append(f"### {key}\n```json\n{data_str}\n```")

    data_block = "\n\n".join(data_sections) or "No data available."
    past_learnings = collect_past_learnings(experiments_dir, cycle)
    baseline_failures = load_baseline_failures(baseline_failures_path)

    prompt = f"""# Aegis Finance - R&D Cycle {cycle}

You are a senior quant researcher with full access to this codebase, the terminal, and the web.
You are running the overnight desk. Nobody is watching. You have full creative control.

Your job is simple: make this engine better. Find bugs humans missed. Build features
investors actually need. Write tests that catch real problems. Validate predictions
against reality.

You are not following a checklist. You are thinking.

---

## YOUR TOOLS

You have everything:
- **Full codebase access** — read any file, edit any file in backend/frontend/engine
- **Terminal** — run python, pytest, any command
- **Web search** — look up analyst price targets, market consensus, compare predictions to reality
- **Test creation** — write new pytest tests in backend/tests/

Use them all. A quant who only reads code without checking the numbers against reality is useless.

---

## RULES (only 3)

1. Only modify files in `backend/`, `frontend/`, `engine/`. Never touch `lab/`.
2. Don't break existing tests. If you do, your changes get auto-reverted.
3. Commit at the end: `git add -A && git commit -m "Lab cycle_{cycle:03d}: <summary>"`

---

## FAILING TESTS

```
{baseline_failures}
```

---

## ENGINE OUTPUT

The data below is from running the REAL backend services — stock_analyzer, monte_carlo,
signal_engine, portfolio_engine, crash_model. Stress tests and consistency checks ran
automatically. This is what your production code actually produces right now.

{data_block}

---

## WHAT A GREAT CYCLE LOOKS LIKE

The best cycles do ONE of these really well:

**Find a real bug** — Look at the stress tests and consistency checks above. Any failure
is a bug in production. Trace it to the exact line of code, fix it, then write a pytest
that would have caught it. Don't just fix the symptom — understand why it happened.

**Validate against reality** — Pick 2-3 stocks from the analysis above. Web search their
analyst price targets, consensus estimates, recent news. Compare to what our engine predicts.
If our MC says TSLA will be +120% in 5 years but every analyst says +20%, something is wrong
in the code. Find it. Fix it. This is how real quant desks work — they validate models
against external data.

**Write tests that matter** — The test suite has 60 tests but misses critical things:
  - Does the signal engine produce different outputs for bull vs bear markets?
  - Does portfolio build actually give different allocations for conservative vs aggressive?
  - Do MC percentiles satisfy P5 < P25 < P50 < P75 < P95?
  - Are crash probabilities actually calibrated? (base rate ~12% for 3m drawdown)
  - Do config parameters stay in sane ranges after code changes?
Write tests in `backend/tests/` that catch real problems, not trivial stuff.

**Build something investors need** — Think about what's missing:
  - Risk-adjusted return comparison (Sharpe, Sortino, Calmar across stocks)
  - Drawdown analysis (current drawdown, recovery time, worst drawdowns)
  - Correlation matrix for portfolio diversification
  - Sector rotation signals
  - Earnings calendar / upcoming catalysts
  - Volatility term structure (implied vs realized)
  Don't build everything — pick one thing and build it properly.

---

## HOW TO THINK

Before you write any code, spend time reading:

```bash
# Read the core engine
cat backend/services/monte_carlo.py
cat backend/services/signal_engine.py
cat backend/services/stock_analyzer.py
cat backend/services/crash_model.py
cat backend/config.py

# Read the test suite — find what's NOT tested
ls backend/tests/
cat backend/tests/test_signal_engine.py

# Run tests
python -m pytest backend/tests/ -v -m "not slow" --tb=short

# Check predictions against reality
# Web search: "AAPL analyst price target 2026" or "S&P 500 forecast 2026"
# Compare to what the engine produces
```

Then think: "If I were managing $10M based on this engine, what would scare me?"
That's your bug. Fix it.

---

## EXPERIMENT REPORT (REQUIRED)

Create: `lab/experiments/cycle_{cycle:03d}/experiment_report.json`

```json
{{
    "cycle": {cycle},
    "timestamp": "<now>",
    "what_i_noticed": "<specific numbers/failures from the data above>",
    "hypothesis": "<root cause — what's wrong in the code and why>",
    "what_i_did": "<changes + reasoning — why this fix is correct>",
    "files_modified": ["<backend/ or engine/ files>"],
    "tests_written": ["<new test functions you created>"],
    "tests_fixed": ["<pre-existing failures you fixed>"],
    "reality_check": "<did you compare predictions to external data? what did you find?>",
    "results": {{
        "before": {{}},
        "after": {{}},
        "improved": true
    }},
    "analysis": "<honest: would you trust this engine with real money after your change?>",
    "next_steps": "<what the next cycle should attack>",
    "confidence": "high",
    "should_keep": true
}}
```

---

## PAST CYCLES

{past_learnings}

---

Go. Read the data. Read the code. Find the worst problem. Fix it. Test it. Ship it.
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt)
    print(f"  Prompt built: {len(prompt)} chars, cycle {cycle}, {len(all_data)} data files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle-dir", required=True)
    parser.add_argument("--experiments-dir", required=True)
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline-failures", default=None)
    args = parser.parse_args()
    build_prompt(args.cycle_dir, args.experiments_dir, args.cycle, args.output,
                 baseline_failures_path=args.baseline_failures)
