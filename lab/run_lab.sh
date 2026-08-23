#!/bin/bash
# AEGIS FINANCE - AUTONOMOUS R&D LAB v5
# Run: bash lab/run_lab.sh
#
# No fixed intervals — each cycle starts immediately after the last.
# Claude gets full autonomy: web search, codebase access, test creation.

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAB_DIR="$REPO_DIR/lab"
EXPERIMENTS_DIR="$LAB_DIR/experiments"
LOGS_DIR="$LAB_DIR/logs"

MAX_CYCLES=20
CLAUDE_TIMEOUT=1500  # 25 min max per Claude session
RESEARCH_BRANCH="lab/autonomous-rd"

mkdir -p "$EXPERIMENTS_DIR" "$LOGS_DIR"

cd "$REPO_DIR"
git stash 2>/dev/null || true
git checkout -B "$RESEARCH_BRANCH" main 2>/dev/null || git checkout "$RESEARCH_BRANCH"

# Capture baseline
echo "[BASELINE] Running test suite..."
BASELINE_FAILURES_FILE="$LAB_DIR/baseline_failures.txt"
python -m pytest backend/tests/ -v -m "not slow" --tb=line 2>&1 | \
    grep "^FAILED" | sort > "$BASELINE_FAILURES_FILE" 2>/dev/null || true
BASELINE_FAIL_COUNT=$(wc -l < "$BASELINE_FAILURES_FILE" 2>/dev/null || echo "0")
BASELINE_PASS_COUNT=$(python -m pytest backend/tests/ -v -m "not slow" --tb=no 2>&1 | \
    grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
echo "  Baseline: $BASELINE_PASS_COUNT passed, $BASELINE_FAIL_COUNT failed"

CYCLE=0
START_TIME=$(date +%s)

echo ""
echo "==========================================================="
echo "  AEGIS R&D LAB v5 - FULL AUTONOMY"
echo "  Max cycles: $MAX_CYCLES (no wait between cycles)"
echo "  Claude timeout: ${CLAUDE_TIMEOUT}s per cycle"
echo "  Branch: $RESEARCH_BRANCH"
echo "  Start:  $(date)"
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

    # PHASE 1: Generate engine data + stress tests + reality checks
    echo "[1/5] Data generation + stress tests..." | tee -a "$CYCLE_LOG"

    python "$LAB_DIR/data_generator.py" \
        --output-dir "$CYCLE_DIR/data" \
        --cycle "$CYCLE" \
        2>&1 | tee -a "$CYCLE_LOG" || {
        echo "  WARNING: Data generation had errors" | tee -a "$CYCLE_LOG"
    }

    # PHASE 2: Build prompt
    echo "[2/5] Building prompt..." | tee -a "$CYCLE_LOG"

    python "$LAB_DIR/build_prompt.py" \
        --cycle-dir "$CYCLE_DIR" \
        --experiments-dir "$EXPERIMENTS_DIR" \
        --cycle "$CYCLE" \
        --output "$CYCLE_DIR/prompt.md" \
        --baseline-failures "$BASELINE_FAILURES_FILE" \
        2>&1 | tee -a "$CYCLE_LOG"

    # PHASE 3: Claude Code — full autonomy
    echo "[3/5] Claude Code session (up to $((CLAUDE_TIMEOUT/60)) min)..." | tee -a "$CYCLE_LOG"

    cat "$CYCLE_DIR/prompt.md" | timeout $CLAUDE_TIMEOUT claude --dangerously-skip-permissions \
        2>&1 | tee "$CYCLE_DIR/claude_output.txt" || true

    echo "[3/5] Session ended." | tee -a "$CYCLE_LOG"

    # PHASE 4: Validate
    echo "[4/5] Validation..." | tee -a "$CYCLE_LOG"
    cd "$REPO_DIR"

    python -m pytest backend/tests/ -v -m "not slow" --tb=line \
        2>&1 | tee "$CYCLE_DIR/test_results.txt" || true

    CURRENT_FAILURES_FILE="$CYCLE_DIR/current_failures.txt"
    grep "^FAILED" "$CYCLE_DIR/test_results.txt" | sort > "$CURRENT_FAILURES_FILE" 2>/dev/null || true
    CURRENT_FAIL_COUNT=$(wc -l < "$CURRENT_FAILURES_FILE" 2>/dev/null || echo "0")

    NEW_FAILURES_FILE="$CYCLE_DIR/new_failures.txt"
    comm -23 "$CURRENT_FAILURES_FILE" "$BASELINE_FAILURES_FILE" > "$NEW_FAILURES_FILE" 2>/dev/null || true
    NEW_FAIL_COUNT=$(wc -l < "$NEW_FAILURES_FILE" 2>/dev/null || echo "0")

    # Count how many tests pass now (including new ones Claude wrote)
    CURRENT_PASS_COUNT=$(grep -oP '\d+ passed' "$CYCLE_DIR/test_results.txt" | grep -oP '\d+' || echo "0")

    if [ "$NEW_FAIL_COUNT" -gt 0 ]; then
        echo "  [REVERT] $NEW_FAIL_COUNT NEW failures!" | tee -a "$CYCLE_LOG"
        cat "$NEW_FAILURES_FILE" | tee -a "$CYCLE_LOG"
        git checkout -- backend/ frontend/ engine/ 2>/dev/null || true
    else
        echo "  [OK] Tests: $CURRENT_PASS_COUNT passed (was $BASELINE_PASS_COUNT), $CURRENT_FAIL_COUNT failed" | tee -a "$CYCLE_LOG"
        # Update baseline if Claude fixed tests or added new ones
        if [ "$CURRENT_PASS_COUNT" -gt "$BASELINE_PASS_COUNT" ] 2>/dev/null; then
            echo "  [+] $((CURRENT_PASS_COUNT - BASELINE_PASS_COUNT)) new/fixed tests!" | tee -a "$CYCLE_LOG"
            BASELINE_PASS_COUNT=$CURRENT_PASS_COUNT
        fi
        # Update baseline failures if Claude fixed some
        if [ "$CURRENT_FAIL_COUNT" -lt "$BASELINE_FAIL_COUNT" ] 2>/dev/null; then
            echo "  [+] Fixed $((BASELINE_FAIL_COUNT - CURRENT_FAIL_COUNT)) pre-existing failures!" | tee -a "$CYCLE_LOG"
            cp "$CURRENT_FAILURES_FILE" "$BASELINE_FAILURES_FILE"
            BASELINE_FAIL_COUNT=$CURRENT_FAIL_COUNT
        fi
    fi

    # Post-validation data run
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
        echo "  [OK] Report written"
        python -c "
import json
r = json.load(open('$CYCLE_DIR/experiment_report.json'))
print(f\"  Topic: {r.get('what_i_noticed', 'N/A')[:80]}\")
print(f\"  Result: {'IMPROVED' if r.get('results',{}).get('improved') else 'no improvement'}\")
print(f\"  Files: {', '.join(r.get('files_modified', []))}\")
tests = r.get('tests_written', [])
if tests: print(f'  New tests: {tests}')
" 2>/dev/null || true
    else
        echo "  [MISS] No experiment report"
    fi

    if [ "$NEW_FAIL_COUNT" -gt 0 ]; then
        echo "  [REVERTED]"
    fi

    echo ""
    echo "  Starting next cycle immediately..."
    echo ""
done

TOTAL_HOURS=$(( ($(date +%s) - START_TIME) / 3600 ))
TOTAL_MINS=$(( (($(date +%s) - START_TIME) % 3600) / 60 ))
echo ""
echo "==========================================================="
echo "  R&D LAB COMPLETE -- $CYCLE cycles in ${TOTAL_HOURS}h ${TOTAL_MINS}m"
echo "==========================================================="
echo ""
echo "Review:  git log --oneline $RESEARCH_BRANCH -30"
echo "Merge:   git checkout main && git merge $RESEARCH_BRANCH"
