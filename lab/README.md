# Aegis Finance — Autonomous R&D Lab v2

## What changed from v1

v1 had a fixed 12-topic rotation that told Claude exactly what to research.
v2 gives Claude **raw engine output and full codebase access** — it decides
what to work on based on what it actually sees in the data and code.

The key difference: Claude reads real numbers, notices something off,
digs into the source code, figures out why, fixes it, and measures if it helped.
Like a real engineer, not a student following a rubric.

## Setup (5 minutes)

```bash
# 1. Open Git Bash (or WSL terminal)
# 2. Navigate to your repo
cd /c/Users/mrthn/aegis-finance

# 3. Create lab folder and copy files
mkdir -p lab

# 4. Copy the 4 files into lab/:
#    - run_lab.sh
#    - build_prompt.py
#    - data_generator.py
#    - compare_results.py

# 5. Install dependencies (if not already)
pip install yfinance numpy pandas pytest

# 6. Verify Claude Code works
claude --version

# 7. Run
bash lab/run_lab.sh
```

## What happens each cycle

```
[Phase 1] data_generator.py runs the engine
           → MC simulations, stock analysis, backtest accuracy, etc.
           → Saved as JSON files

[Phase 2] build_prompt.py assembles context
           → Current data + ALL past experiment reports
           → No fixed topic — Claude decides what to work on

[Phase 3] Claude Code gets full autonomy (~90 min)
           → Reads the data, reads the source code
           → Finds issues, implements fixes, measures results
           → Writes experiment_report.json

[Phase 4] Validation
           → Runs test suite
           → Re-runs data generator with Claude's changes
           → Compares before/after metrics
           → Git commits everything
```

## Configuration

Edit the top of `run_lab.sh`:

```bash
CYCLE_INTERVAL_SECONDS=7200  # 2 hours per cycle
MAX_CYCLES=10                # 10 cycles = ~20 hours
```

## Morning review

```bash
# What did Claude do?
git log --oneline lab/autonomous-rd -20

# Did things improve?
for f in lab/experiments/cycle_*/experiment_report.json; do
    echo "=== $(basename $(dirname $f)) ==="
    python3 -c "
import json
r = json.load(open('$f'))
print(f'Noticed: {r.get(\"what_i_noticed\", \"?\")[:100]}')
print(f'Did: {r.get(\"what_i_did\", \"?\")[:100]}')
print(f'Improved: {r.get(\"results\",{}).get(\"improved\", \"?\")}')
print(f'Confidence: {r.get(\"confidence\", \"?\")}')
print(f'Next: {r.get(\"next_steps\", \"?\")[:100]}')
"
    echo ""
done

# Merge the good stuff
git checkout main
git merge lab/autonomous-rd
```
