# Aegis Finance — Autonomous R&D Lab v2

## What changed from v1

v1 had a fixed 12-topic rotation that told Claude exactly what to research.
v2 gives Claude **raw engine output and full codebase access** — it decides
what to work on based on what it actually sees in the data and code.

### v2 fixes (after first 10-cycle run post-mortem)

The first run had 5 problems:
1. Claude spent 6/10 cycles fixing `data_generator.py` instead of backend code
2. Same test failed all 10 cycles — never fixed, never even noticed
3. Comparison metrics plateaued after cycle 1 (always showed 0.4)
4. No guardrails prevented modifying lab measurement tools
5. Tests ran with `-x` (stop on first failure), masking the full picture

**Fixes:**
- Prompt now explicitly forbids modifying `lab/` files
- Baseline test failures captured before cycles start, so Claude knows what's pre-existing
- Full test suite runs (no `-x`), new failures trigger automatic revert
- Prompt prioritizes fixing broken tests as highest-value work
- `files_modified` in reports now expected to be in `backend/`/`engine/`/`frontend/`

## Setup (5 minutes)

```bash
# 1. Open Git Bash (or WSL terminal)
cd /c/Users/mrthn/aegis-finance

# 2. Install dependencies (if not already)
pip install yfinance numpy pandas pytest

# 3. Verify Claude Code works
claude --version

# 4. Run
bash lab/run_lab.sh
```

## What happens each cycle

```
[Baseline] Run test suite once, record pre-existing failures

[Phase 1] data_generator.py runs the engine
           -> MC simulations, stock analysis, backtest accuracy, etc.
           -> Saved as JSON files

[Phase 2] build_prompt.py assembles context
           -> Current data + ALL past experiment reports
           -> Pre-existing test failures included
           -> No fixed topic — Claude decides what to work on
           -> Explicit: only modify backend/frontend/engine, NOT lab/

[Phase 3] Claude Code gets full autonomy (~50 min)
           -> Reads the data, reads the source code
           -> Finds issues, implements fixes, measures results
           -> Writes experiment_report.json

[Phase 4] Validation
           -> Runs FULL test suite (not just first failure)
           -> Compares current failures to baseline
           -> If NEW failures introduced -> auto-reverts code changes
           -> Re-runs data generator with (possibly reverted) changes
           -> Compares before/after metrics

[Phase 5] Git commits everything
```

## Configuration

Edit the top of `run_lab.sh`:

```bash
CYCLE_INTERVAL_SECONDS=3600  # 1 hour per cycle
MAX_CYCLES=10                # 10 cycles = ~10 hours
```

## Morning review

```bash
# What did Claude do?
git log --oneline lab/autonomous-rd -20

# Did things improve?
for f in lab/experiments/cycle_*/experiment_report.json; do
    echo "=== $(basename $(dirname $f)) ==="
    python -c "
import json
r = json.load(open('$f'))
print(f'Noticed: {r.get(\"what_i_noticed\", \"?\")[:100]}')
print(f'Did: {r.get(\"what_i_did\", \"?\")[:100]}')
print(f'Files: {r.get(\"files_modified\", [])}')
print(f'Improved: {r.get(\"results\",{}).get(\"improved\", \"?\")}')
print(f'Tests fixed: {r.get(\"tests_fixed\", [])}')
print(f'Confidence: {r.get(\"confidence\", \"?\")}')
"
    echo ""
done

# Were any cycles reverted?
grep -r "REVERT" lab/logs/

# Merge the good stuff
git checkout main
git merge lab/autonomous-rd
```
