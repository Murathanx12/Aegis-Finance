#!/bin/bash
# AEGIS FINANCE - AUTONOMOUS R&D LAB v2
# Run: bash lab/run_lab.sh
#
# Fixes over v1:
# - Runs full test suite (no -x), captures baseline failures
# - Blocks commit if NEW test failures introduced
# - Prompt steers Claude toward backend/frontend, not lab tools
# - Richer comparison metrics (signals, crash probs, portfolios)
# - Better Claude invocation (--print flag for structured output)

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAB_DIR="$REPO_DIR/lab"
EXPERIMENTS_DIR="$LAB_DIR/experiments"
LOGS_DIR="$LAB_DIR/logs"

CYCLE_INTERVAL_SECONDS=3600
MAX_CYCLES=10
RESEARCH_BRANCH="lab/autonomous-rd"

mkdir -p "$EXPERIMENTS_DIR" "$LOGS_DIR"

cd "$REPO_DIR"
git stash 2>/dev/null || true
git checkout -B "$RESEARCH_BRANCH" main 2>/dev/null || git checkout "$RESEARCH_BRANCH"

# Capture baseline test failures BEFORE any cycles
echo "[BASELINE] Running test suite to capture pre-existing failures..."
BASELINE_FAILURES_FILE="$LAB_DIR/baseline_failures.txt"
python -m pytest backend/tests/ -v -m "not slow" --tb=line 2>&1 | \
    grep "^FAILED" | sort > "$BASELINE_FAILURES_FILE" 2>/dev/null || true
BASELINE_FAIL_COUNT=$(wc -l < "$BASELINE_FAILURES_FILE" 2>/dev/null || echo "0")
echo "  Baseline: $BASELINE_FAIL_COUNT pre-existing test failures"
echo ""

CYCLE=0
START_TIME=$(date +%s)

echo ""
echo "==========================================================="
echo "  AEGIS R&D LAB v2 - FULL AUTONOMY MODE"
echo "  Cycles: $MAX_CYCLES x 60 min"
echo "  Branch: $RESEARCH_BRANCH"
echo "  Start:  $(date)"
echo "  Baseline failures: $BASELINE_FAIL_COUNT"
echo "==========================================================="
echo ""

while [ $CYCLE -lt $MAX_CYCLES ]; do
    CYCLE=$((CYCLE + 1))
    CYCLE_ID=$(printf "cycle_%03d" $CYCLE)
    CYCLE_DIR="$EXPERIMENTS_DIR/$CYCLE_ID"
    CYCLE_LOG="$LOGS_DIR/${CYCLE_ID}.log"
    CYCLE_START=$(date +%s)

    mkdir -p "$CYCLE_DIR"

    echo "==========================================================="
    echo "  CYCLE $CYCLE/$MAX_CYCLES -- $(date)"
    echo "==========================================================="

    # PHASE 1: Generate engine data
    echo "[1/5] Generating engine data..." | tee -a "$CYCLE_LOG"

    python "$LAB_DIR/data_generator.py" \
        --output-dir "$CYCLE_DIR/data" \
        --cycle "$CYCLE" \
        2>&1 | tee -a "$CYCLE_LOG" || {
        echo "  WARNING: Data generation had errors" | tee -a "$CYCLE_LOG"
    }

    # PHASE 2: Build prompt (passes baseline failures so Claude knows what's pre-existing)
    echo "[2/5] Building prompt..." | tee -a "$CYCLE_LOG"

    python "$LAB_DIR/build_prompt.py" \
        --cycle-dir "$CYCLE_DIR" \
        --experiments-dir "$EXPERIMENTS_DIR" \
        --cycle "$CYCLE" \
        --output "$CYCLE_DIR/prompt.md" \
        --baseline-failures "$BASELINE_FAILURES_FILE" \
        2>&1 | tee -a "$CYCLE_LOG"

    # PHASE 3: Run Claude Code with FULL interactive access
    echo "[3/5] Claude Code starting (up to 50 min)..." | tee -a "$CYCLE_LOG"

    cat "$CYCLE_DIR/prompt.md" | timeout 3000 claude --dangerously-skip-permissions \
        2>&1 | tee "$CYCLE_DIR/claude_output.txt" || true

    echo "[3/5] Claude Code session ended." | tee -a "$CYCLE_LOG"

    # PHASE 4: Validate — run FULL test suite (no -x), check for NEW failures
    echo "[4/5] Post-session validation..." | tee -a "$CYCLE_LOG"

    cd "$REPO_DIR"

    # Run full test suite (not just fast — skip slow network tests still)
    python -m pytest backend/tests/ -v -m "not slow" --tb=line \
        2>&1 | tee "$CYCLE_DIR/test_results.txt" || true

    # Extract current failures
    CURRENT_FAILURES_FILE="$CYCLE_DIR/current_failures.txt"
    grep "^FAILED" "$CYCLE_DIR/test_results.txt" | sort > "$CURRENT_FAILURES_FILE" 2>/dev/null || true
    CURRENT_FAIL_COUNT=$(wc -l < "$CURRENT_FAILURES_FILE" 2>/dev/null || echo "0")

    # Find NEW failures (in current but not in baseline)
    NEW_FAILURES_FILE="$CYCLE_DIR/new_failures.txt"
    comm -23 "$CURRENT_FAILURES_FILE" "$BASELINE_FAILURES_FILE" > "$NEW_FAILURES_FILE" 2>/dev/null || true
    NEW_FAIL_COUNT=$(wc -l < "$NEW_FAILURES_FILE" 2>/dev/null || echo "0")

    if [ "$NEW_FAIL_COUNT" -gt 0 ]; then
        echo "  [REVERT] $NEW_FAIL_COUNT NEW test failures introduced!" | tee -a "$CYCLE_LOG"
        cat "$NEW_FAILURES_FILE" | tee -a "$CYCLE_LOG"
        echo "  Reverting changes..." | tee -a "$CYCLE_LOG"
        git checkout -- backend/ frontend/ engine/ 2>/dev/null || true
        # Keep lab/ changes (reports, data) but revert code
    else
        echo "  [OK] No new test failures ($CURRENT_FAIL_COUNT total, $BASELINE_FAIL_COUNT pre-existing)" | tee -a "$CYCLE_LOG"
    fi

    # Re-run data generator with (possibly reverted) code
    python "$LAB_DIR/data_generator.py" \
        --output-dir "$CYCLE_DIR/data_after" \
        --cycle "$CYCLE" \
        2>&1 | tee -a "$CYCLE_LOG" || true

    python "$LAB_DIR/compare_results.py" \
        --before "$CYCLE_DIR/data" \
        --after "$CYCLE_DIR/data_after" \
        --output "$CYCLE_DIR/comparison.json" \
        2>&1 | tee -a "$CYCLE_LOG" || true

    # PHASE 5: Commit
    CYCLE_END=$(date +%s)
    CYCLE_DURATION=$(( (CYCLE_END - CYCLE_START) / 60 ))

    cd "$REPO_DIR"
    git add -A
    git commit -m "Lab $CYCLE_ID (${CYCLE_DURATION}min)" --allow-empty 2>/dev/null || true

    echo ""
    echo "  Cycle $CYCLE done in ${CYCLE_DURATION} min."

    if [ -f "$CYCLE_DIR/experiment_report.json" ]; then
        echo "  [OK] Experiment report written"
        python -c "
import json
r = json.load(open('$CYCLE_DIR/experiment_report.json'))
print(f\"  Topic: {r.get('what_i_noticed', 'N/A')[:80]}\")
print(f\"  Result: {'IMPROVED' if r.get('results',{}).get('improved') else 'no improvement'}\")
print(f\"  Files: {', '.join(r.get('files_modified', []))}\")
" 2>/dev/null || true
    else
        echo "  [MISS] No experiment report"
    fi

    if [ -f "$CYCLE_DIR/comparison.json" ]; then
        python -c "
import json
c = json.load(open('$CYCLE_DIR/comparison.json'))
print(f\"  Net: {c.get('net_result', 'unknown')}\")
" 2>/dev/null || true
    fi

    if [ "$NEW_FAIL_COUNT" -gt 0 ]; then
        echo "  [REVERTED] Code changes reverted due to new test failures"
    fi

    echo ""

    # Wait for next cycle
    if [ $CYCLE -lt $MAX_CYCLES ]; then
        ELAPSED=$(( $(date +%s) - CYCLE_START ))
        WAIT_TIME=$(( CYCLE_INTERVAL_SECONDS - ELAPSED ))

        if [ $WAIT_TIME -gt 0 ]; then
            echo "  Next cycle in $(($WAIT_TIME / 60)) min. Ctrl+C to stop."
            sleep $WAIT_TIME
        else
            echo "  Starting next cycle immediately."
        fi
    fi
done

TOTAL_HOURS=$(( ($(date +%s) - START_TIME) / 3600 ))
echo ""
echo "==========================================================="
echo "  R&D LAB COMPLETE -- $CYCLE cycles in ~${TOTAL_HOURS}h"
echo "==========================================================="
echo ""
echo "Review:  git log --oneline $RESEARCH_BRANCH -20"
echo "Merge:   git checkout main && git merge $RESEARCH_BRANCH"
