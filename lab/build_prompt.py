"""
Aegis Finance - Lab Prompt Builder
Gives Claude raw data + past learnings + full creative freedom.
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


def build_prompt(cycle_dir, experiments_dir, cycle, output_path):
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

    prompt = f"""# Aegis Finance - Autonomous R&D Lab - Cycle {cycle}
Time: {datetime.now().isoformat()}

---

## WHO YOU ARE

You are an autonomous quant engineer with full access to the Aegis Finance codebase.
Your job: make this engine BETTER. Measurably better.

You are NOT following a checklist. You are a researcher who:
1. Looks at real engine output (below)
2. Reads the actual source code (use bash and file tools)
3. Finds problems, bugs, inefficiencies
4. Designs an experiment to fix something
5. Implements it
6. Measures if it helped
7. Logs everything honestly

You have FULL creative control. You decide what to work on.
Only rules: dont break API contracts, dont delete tests.

---

## WHAT TO DO

### Step 1: Understand the current state
- Read the engine output data below carefully
- Read past experiment logs below
- Explore the codebase yourself:
  - List files: find backend/ -name "*.py" | head -30
  - Read key files: cat backend/services/monte_carlo.py | head -100
  - Read config: cat backend/config.py
  - Run python yourself if needed

### Step 2: Find something worth improving
Look for ANY of these (or anything else):
- Numbers that look wrong (MC drift errors >5%, bad crash probs)
- Code that could be better (hardcoded values, missing edge cases)
- Missing connections (services that exist but arent wired together)
- Accuracy gaps (backtest shows poor prediction, signals dont correlate)
- Statistical issues (wrong distributions, look-ahead bias, overfitting)
- Performance (slow code, unnecessary API calls)
- Anything else you notice

### Step 3: Implement and test
- Make your changes to the actual codebase files
- Run: python -m pytest backend/tests/ -x -q
- If tests break, fix them or revert
- Re-run the data generator to see if output improved:
  python lab/data_generator.py --output-dir lab/experiments/cycle_{cycle:03d}/data_test --cycle {cycle}

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
    "files_modified": ["<list every file you touched>"],
    "results": {{
        "before": {{"<metric>": "<value>"}},
        "after": {{"<metric>": "<value>"}},
        "improved": true or false
    }},
    "analysis": "<honest assessment - did it work?>",
    "next_steps": "<what should the next cycle focus on>",
    "confidence": "<low/medium/high>",
    "should_keep": true or false
}}

Failed experiments are fine. Log them honestly so the next cycle learns.

### Step 5: Commit
git add -A
git commit -m "Lab cycle {cycle}: <summary>"

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
  services/       # Core engine (monte_carlo.py, crash_model.py, etc.)
  routers/        # API endpoints
  config.py       # All thresholds, weights, parameters
  tests/          # Test suite
engine/
  training/       # ML model training
  validation/     # Backtesting
frontend/
  src/app/        # Next.js pages
  src/components/ # React components
  src/lib/        # API client, utilities
lab/
  experiments/    # Your experiment data and reports
  data_generator.py

Start by reading code. Dont assume - verify.

---

## GO

Read the data. Explore the code. Find something to improve. Make it better.
Write the experiment report. Commit.
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
    args = parser.parse_args()

    build_prompt(args.cycle_dir, args.experiments_dir, args.cycle, args.output)
