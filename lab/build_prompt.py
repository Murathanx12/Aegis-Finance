"""
Aegis Finance - Lab Prompt Builder v2
Gives Claude raw data + past learnings + full creative freedom.
Steers toward backend/frontend improvements, not lab tool fixes.
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

    for cycle_num in range(1, current_cycle):
        cycle_id = f"cycle_{cycle_num:03d}"
        cycle_dir = os.path.join(experiments_dir, cycle_id)

        report = load_json_safe(os.path.join(cycle_dir, "experiment_report.json"))
        comparison = load_json_safe(os.path.join(cycle_dir, "comparison.json"))

        if report:
            improved = report.get("results", {}).get("improved", False)
            entry = f"""### Cycle {cycle_num}
What I tried: {report.get('hypothesis', 'Unknown')}
Method: {report.get('method', 'Unknown')}
Result: {'IMPROVED' if improved else 'NO IMPROVEMENT'}
Before: {json.dumps(report.get('results', {}).get('before', {}))}
After: {json.dumps(report.get('results', {}).get('after', {}))}
What I learned: {report.get('analysis', 'No analysis')}
Next steps: {report.get('next_steps', 'None')}
Files changed: {', '.join(report.get('files_modified', []))}"""
            learnings.append(entry)

        elif comparison:
            improvements = comparison.get("improvements", [])
            regressions = comparison.get("regressions", [])
            net = comparison.get("net_result", "unknown")
            entry = f"""### Cycle {cycle_num}
(No experiment report written)
Net result: {net}
Improvements: {', '.join(improvements) if improvements else 'None'}
Regressions: {', '.join(regressions) if regressions else 'None'}"""
            learnings.append(entry)

    if not learnings:
        return "This is the FIRST cycle. No past experiments yet."

    return "\n\n".join(learnings)


def load_baseline_failures(path):
    """Load pre-existing test failures so Claude knows what's already broken."""
    if not path or not os.path.exists(path):
        return "No baseline failure data available."
    try:
        with open(path, encoding="utf-8") as f:
            failures = f.read().strip()
        if not failures:
            return "All tests passing (no pre-existing failures)."
        return failures
    except:
        return "Could not read baseline failures."


def build_prompt(cycle_dir, experiments_dir, cycle, output_path, baseline_failures_path=None):
    data_dir = os.path.join(cycle_dir, "data")

    all_data = {}
    if os.path.isdir(data_dir):
        for f in glob.glob(os.path.join(data_dir, "*.json")):
            key = Path(f).stem
            all_data[key] = load_json_safe(f)

    data_sections = []
    for key, data in all_data.items():
        if data is None:
            continue
        data_str = json.dumps(data, indent=2)
        if len(data_str) > 4000:
            data_str = data_str[:4000] + "\n... [truncated]"
        data_sections.append(f"### {key}\n```json\n{data_str}\n```")

    data_block = "\n\n".join(data_sections) if data_sections else "No data available."

    past_learnings = collect_past_learnings(experiments_dir, cycle)

    baseline_failures = load_baseline_failures(baseline_failures_path)

    prompt = f"""# Aegis Finance - Autonomous R&D Lab - Cycle {cycle}
Time: {datetime.now().isoformat()}

---

## WHO YOU ARE

You are an autonomous quant engineer with full access to the Aegis Finance codebase.
Your job: make the PRODUCTION ENGINE better. Measurably better.

You are NOT following a checklist. You are a researcher who:
1. Looks at real engine output (below)
2. Reads the actual source code (use bash and file tools)
3. Finds problems, bugs, inefficiencies in the BACKEND or FRONTEND
4. Designs an experiment to fix something
5. Implements it
6. Measures if it helped
7. Logs everything honestly

You have FULL creative control. You decide what to work on.

---

## CRITICAL RULES

1. **ONLY modify files in `backend/`, `frontend/`, or `engine/`.**
   - NEVER modify files in `lab/` (data_generator.py, build_prompt.py, compare_results.py, run_lab.sh).
   - The lab tools are READ-ONLY measurement instruments. If the data looks wrong, the fix belongs in the backend service code, not the measurement tool.

2. **Do NOT break existing tests.**
   - Run: `python -m pytest backend/tests/ -v -m "not slow" --tb=short`
   - If your changes cause NEW test failures, they will be auto-reverted.
   - You MAY fix pre-existing test failures (see below) — that counts as an improvement.

3. **Do NOT delete tests or weaken assertions.**

4. **Put parameters in `backend/config.py`**, not hardcoded in services.

5. **Commit your changes** at the end:
   `git add -A && git commit -m "Lab cycle_{cycle:03d}: <summary>"`

---

## PRE-EXISTING TEST FAILURES

These tests were already failing BEFORE your cycle started.
Fixing any of these is a valid and valuable improvement.

```
{baseline_failures}
```

---

## WHAT TO LOOK FOR

Priority order:
1. **Fix failing tests** — broken tests are the highest-value target
2. **Accuracy bugs** — wrong formulas, missing corrections, bad defaults in backend services
3. **Missing connections** — services that exist but aren't wired into endpoints
4. **Signal quality** — buy/sell signals that are always the same, crash probs that don't differentiate
5. **Statistical issues** — wrong distributions, look-ahead bias, overfitting
6. **Code quality** — hardcoded values that belong in config.py, missing edge cases

---

## WHAT TO DO

### Step 1: Understand the current state
- Read the engine output data below carefully
- Read past experiment logs below
- Explore the BACKEND codebase yourself:
  - `cat backend/services/monte_carlo.py | head -100`
  - `cat backend/config.py`
  - `cat backend/services/signal_engine.py`
  - `python -m pytest backend/tests/ -v -m "not slow" --tb=short`

### Step 2: Find something worth improving
Focus on backend/services/, backend/routers/, backend/config.py, or engine/.
Do NOT modify lab/ files.

### Step 3: Implement and test
- Make your changes to backend/ or frontend/ or engine/ files
- Run: `python -m pytest backend/tests/ -v -m "not slow" --tb=short`
- If tests break due to your changes, fix them or revert
- Re-run the data generator to see if output improved:
  `python lab/data_generator.py --output-dir lab/experiments/cycle_{cycle:03d}/data_test --cycle {cycle}`

### Step 4: Write the experiment report

CRITICAL - You MUST create this file before finishing:
lab/experiments/cycle_{cycle:03d}/experiment_report.json

Contents:
{{
    "cycle": {cycle},
    "timestamp": "<now>",
    "what_i_noticed": "<what caught your attention in the data>",
    "hypothesis": "<what you think the problem is>",
    "what_i_did": "<what code you changed and why>",
    "files_modified": ["<list every file you touched — should be in backend/ or engine/>"],
    "results": {{
        "before": {{"<metric>": "<value>"}},
        "after": {{"<metric>": "<value>"}},
        "improved": true or false
    }},
    "tests_fixed": ["<list any previously-failing tests you fixed>"],
    "analysis": "<honest assessment - did it work?>",
    "next_steps": "<what should the next cycle focus on>",
    "confidence": "<low/medium/high>",
    "should_keep": true or false
}}

Failed experiments are fine. Log them honestly so the next cycle learns.

### Step 5: Commit
git add -A
git commit -m "Lab cycle_{cycle:03d}: <summary>"

---

## ENGINE OUTPUT (fresh data from this cycle)

{data_block}

---

## PAST EXPERIMENTS (your accumulated knowledge)

{past_learnings}

---

## CODEBASE LAYOUT

Key directories (explore yourself, dont just trust this list):

backend/
  services/       # Core engine — THIS IS WHERE IMPROVEMENTS GO
  routers/        # API endpoints
  config.py       # All thresholds, weights, parameters
  tests/          # Test suite — fix failures here
engine/
  training/       # ML model training
  validation/     # Backtesting
frontend/
  src/app/        # Next.js pages
  src/components/ # React components
  src/lib/        # API client, utilities
lab/              # READ-ONLY — do NOT modify these files
  data_generator.py   # Measurement tool (hands off)
  build_prompt.py     # Prompt builder (hands off)
  compare_results.py  # Comparator (hands off)

---

## GO

Read the data. Explore the backend code. Find something to improve.
Make it better. Run tests. Write the experiment report. Commit.
Remember: only modify backend/, frontend/, or engine/ files.
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
    parser.add_argument("--baseline-failures", default=None,
                        help="Path to file with pre-existing test failure lines")
    args = parser.parse_args()

    build_prompt(args.cycle_dir, args.experiments_dir, args.cycle, args.output,
                 baseline_failures_path=args.baseline_failures)
