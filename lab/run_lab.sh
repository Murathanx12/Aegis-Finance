#!/bin/bash
# AEGIS FINANCE - AUTONOMOUS R&D LAB v3
# Run: bash lab/run_lab.sh
#
# v3 changes over v2:
# - Uses Opus model for deeper reasoning
# - Longer sessions (45 min timeout) with --max-turns to prevent early stops
# - No wasted sleep between cycles — starts next immediately
# - Comprehensive data generation (calls real backend services)
# - Richer comparison across 7 dimensions
# - Research track rotation logged

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAB_DIR="$REPO_DIR/lab"
EXPERIMENTS_DIR="$LAB_DIR/experiments"
LOGS_DIR="$LAB_DIR/logs"

# --- Configuration ---
MAX_CYCLES=20
CLAUDE_TIMEOUT=2700          # 45 min per Claude session
CLAUDE_MODEL="sonnet"        # opus for deep reasoning (change to sonnet to save cost)
CLAUDE_MAX_TURNS=75          # Force Claude to keep going, not stop after 1 fix
COOLDOWN_SECONDS=60          # Brief cooldown between cycles (API rate limits)
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

# Count existing cycles to resume from where we left off
EXISTING_CYCLES=$(ls -d "$EXPERIMENTS_DIR"/cycle_* 2>/dev/null | wc -l)
START_CYCLE=$((EXISTING_CYCLES))

CYCLE=$START_CYCLE
START_TIME=$(date +%s)

echo ""
echo "==========================================================="
echo "  AEGIS R&D LAB v3 - DEEP AUTONOMY MODE"
echo "  Cycles: $MAX_CYCLES (starting from $((START_CYCLE + 1)))"
echo "  Model: $CLAUDE_MODEL | Max turns: $CLAUDE_MAX_TURNS"
echo "  Session timeout: $((CLAUDE_TIMEOUT / 60)) min"
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

    # --- PHASE 1: Generate engine data (calls REAL backend services) ---
    echo "[1/5] Data generation + stress tests..." | tee -a "$CYCLE_LOG"

    python "$LAB_DIR/data_generator.py" \
        --output-dir "$CYCLE_DIR/data" \
        --cycle "$CYCLE" \
        2>&1 | tee -a "$CYCLE_LOG" || {
        echo "  WARNING: Data generation had errors" | tee -a "$CYCLE_LOG"
    }

    # --- PHASE 2: Build prompt (with research track rotation) ---
    echo "[2/5] Building prompt..." | tee -a "$CYCLE_LOG"

    python "$LAB_DIR/build_prompt.py" \
        --cycle-dir "$CYCLE_DIR" \
        --experiments-dir "$EXPERIMENTS_DIR" \
        --cycle "$CYCLE" \
        --output "$CYCLE_DIR/prompt.md" \
        --baseline-failures "$BASELINE_FAILURES_FILE" \
        2>&1 | tee -a "$CYCLE_LOG"

    # --- PHASE 3: Run Claude Code with DEEP session ---
    echo "[3/5] Claude Code session (up to $((CLAUDE_TIMEOUT / 60)) min, model=$CLAUDE_MODEL)..." | tee -a "$CYCLE_LOG"

    cat "$CYCLE_DIR/prompt.md" | timeout $CLAUDE_TIMEOUT claude \
        --model "$CLAUDE_MODEL" \
        --max-turns "$CLAUDE_MAX_TURNS" \
        --dangerously-skip-permissions \
        2>&1 | tee "$CYCLE_DIR/claude_output.txt" || true

    echo "[3/5] Session ended." | tee -a "$CYCLE_LOG"

    # Capture session size for diagnostics
    CLAUDE_OUTPUT_SIZE=$(wc -c < "$CYCLE_DIR/claude_output.txt" 2>/dev/null || echo "0")
    CLAUDE_OUTPUT_LINES=$(wc -l < "$CYCLE_DIR/claude_output.txt" 2>/dev/null || echo "0")
    echo "  Session output: $CLAUDE_OUTPUT_LINES lines, $CLAUDE_OUTPUT_SIZE bytes" | tee -a "$CYCLE_LOG"

    # --- PHASE 4: Validate ---
    echo "[4/5] Validation..." | tee -a "$CYCLE_LOG"

    cd "$REPO_DIR"

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

    # Extract test count
    TESTS_PASSED=$(grep -oP '\d+(?= passed)' "$CYCLE_DIR/test_results.txt" 2>/dev/null || echo "0")

    if [ "$NEW_FAIL_COUNT" -gt 0 ]; then
        echo "  [REVERT] $NEW_FAIL_COUNT NEW test failures introduced!" | tee -a "$CYCLE_LOG"
        cat "$NEW_FAILURES_FILE" | tee -a "$CYCLE_LOG"
        echo "  Reverting changes..." | tee -a "$CYCLE_LOG"
        git checkout -- backend/ frontend/ engine/ 2>/dev/null || true
    else
        echo "  [OK] Tests: $TESTS_PASSED passed (was $BASELINE_FAIL_COUNT pre-existing failures), $NEW_FAIL_COUNT new failures" | tee -a "$CYCLE_LOG"

        # If tests fixed some pre-existing failures, update baseline
        if [ "$CURRENT_FAIL_COUNT" -lt "$BASELINE_FAIL_COUNT" ]; then
            FIXED=$((BASELINE_FAIL_COUNT - CURRENT_FAIL_COUNT))
            echo "  [BONUS] Fixed $FIXED pre-existing test failures!" | tee -a "$CYCLE_LOG"
        fi
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

    # --- PHASE 5: Commit ---
    CYCLE_END=$(date +%s)
    CYCLE_DURATION=$(( (CYCLE_END - CYCLE_START) / 60 ))

    cd "$REPO_DIR"
    git add -A
    git commit -m "Lab $CYCLE_ID (${CYCLE_DURATION}min)" --allow-empty 2>/dev/null || true

    echo ""
    echo "  Cycle $CYCLE done in ${CYCLE_DURATION} min."

    if [ -f "$CYCLE_DIR/experiment_report.json" ]; then
        echo "  [OK] Report written"
        python -c "
import json
r = json.load(open('$CYCLE_DIR/experiment_report.json'))
print(f\"  Track: {r.get('research_track', 'N/A')}\")
print(f\"  Topic: {r.get('what_i_noticed', 'N/A')[:100]}\")
print(f\"  Result: {'IMPROVED' if r.get('results',{}).get('improved') else 'no improvement'}\")
print(f\"  Depth: {r.get('depth_rating', 'N/A')}\")
print(f\"  Files: {', '.join(r.get('files_modified', []))}\")
print(f\"  Tests added: {len(r.get('tests_added', []))}\")
print(f\"  Lines changed: ~{r.get('lines_changed_approx', 'N/A')}\")
" 2>/dev/null || true
    else
        echo "  [MISS] No experiment report"
    fi

    if [ -f "$CYCLE_DIR/comparison.json" ]; then
        python -c "
import json
c = json.load(open('$CYCLE_DIR/comparison.json'))
print(f\"  Net: {c.get('net_result', 'unknown')} ({c.get('improvement_count', 0)} improvements, {c.get('regression_count', 0)} regressions)\")
" 2>/dev/null || true
    fi

    if [ "$NEW_FAIL_COUNT" -gt 0 ]; then
        echo "  [REVERTED] Code changes reverted due to new test failures"
    fi

    echo ""

    # Brief cooldown (API rate limits), then continue immediately
    if [ $CYCLE -lt $MAX_CYCLES ]; then
        echo "  Cooldown ${COOLDOWN_SECONDS}s before next cycle..."
        sleep $COOLDOWN_SECONDS
        echo "  Starting next cycle."
        echo ""
    fi
done

TOTAL_HOURS=$(( ($(date +%s) - START_TIME) / 3600 ))
echo ""
echo "==========================================================="
echo "  R&D LAB COMPLETE -- $CYCLE cycles in ~${TOTAL_HOURS}h"
echo "==========================================================="
echo ""
echo "Review:  git log --oneline $RESEARCH_BRANCH -$MAX_CYCLES"
echo "Merge:   git checkout main && git merge $RESEARCH_BRANCH"
