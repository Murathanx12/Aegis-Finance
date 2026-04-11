#!/bin/bash
# AEGIS FINANCE - AUTONOMOUS R&D LAB v4
# Run: bash lab/run_lab.sh
#
# v4: Multi-turn conversation architecture
# Instead of "one prompt, one response", each cycle is a 4-phase CONVERSATION:
#   Phase A: Explore (Claude reads codebase, reports what it finds)
#   Phase B: Implement (Push Claude to act on findings — build, not just observe)
#   Phase C: Test & Harden (Force test writing, validation, edge cases)
#   Phase D: Review & Report (Self-critique, cleanup, experiment report)
#
# This simulates the human-in-the-loop dynamic that makes interactive
# Claude sessions productive — challenge, redirect, push deeper.

export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAB_DIR="$REPO_DIR/lab"
EXPERIMENTS_DIR="$LAB_DIR/experiments"
LOGS_DIR="$LAB_DIR/logs"

# --- Configuration ---
MAX_CYCLES=20
PHASE_TIMEOUT=900             # 15 min per phase (4 phases = 60 min max per cycle)
CLAUDE_MODEL="sonnet"         # Change to opus for deeper reasoning
COOLDOWN_SECONDS=30           # Brief cooldown between cycles
RESEARCH_BRANCH="lab/autonomous-rd"

mkdir -p "$EXPERIMENTS_DIR" "$LOGS_DIR"

cd "$REPO_DIR"
git stash 2>/dev/null || true
git checkout -B "$RESEARCH_BRANCH" main 2>/dev/null || git checkout "$RESEARCH_BRANCH"

# Capture baseline test failures
echo "[BASELINE] Running test suite..."
BASELINE_FAILURES_FILE="$LAB_DIR/baseline_failures.txt"
python -m pytest backend/tests/ -v -m "not slow" --tb=line 2>&1 | \
    grep "^FAILED" | sort > "$BASELINE_FAILURES_FILE" 2>/dev/null || true
BASELINE_FAIL_COUNT=$(wc -l < "$BASELINE_FAILURES_FILE" 2>/dev/null || echo "0")
BASELINE_PASS_COUNT=$(python -m pytest backend/tests/ -v -m "not slow" --tb=no 2>&1 | grep -oP '\d+(?= passed)' || echo "0")
echo "  Baseline: $BASELINE_PASS_COUNT passed, $BASELINE_FAIL_COUNT pre-existing failures"

# Count existing cycles to resume
EXISTING_CYCLES=$(ls -d "$EXPERIMENTS_DIR"/cycle_* 2>/dev/null | wc -l)
START_CYCLE=$((EXISTING_CYCLES))

CYCLE=$START_CYCLE
START_TIME=$(date +%s)

echo ""
echo "==========================================================="
echo "  AEGIS R&D LAB v4 - MULTI-TURN CONVERSATION MODE"
echo "  Cycles: $MAX_CYCLES (starting from $((START_CYCLE + 1)))"
echo "  Model: $CLAUDE_MODEL | Phase timeout: $((PHASE_TIMEOUT / 60)) min"
echo "  Architecture: 4-phase conversation per cycle"
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

    # --- DATA GENERATION (calls real backend services) ---
    echo "[0/4] Generating engine data..." | tee -a "$CYCLE_LOG"

    python "$LAB_DIR/data_generator.py" \
        --output-dir "$CYCLE_DIR/data" \
        --cycle "$CYCLE" \
        2>&1 | tee -a "$CYCLE_LOG" || true

    # --- BUILD THE 4-PHASE PROMPTS ---
    echo "[PREP] Building prompts..." | tee -a "$CYCLE_LOG"

    python "$LAB_DIR/build_prompt.py" \
        --cycle-dir "$CYCLE_DIR" \
        --experiments-dir "$EXPERIMENTS_DIR" \
        --cycle "$CYCLE" \
        --output "$CYCLE_DIR/prompt.md" \
        --baseline-failures "$BASELINE_FAILURES_FILE" \
        2>&1 | tee -a "$CYCLE_LOG"

    # Generate a unique session ID for this cycle
    SESSION_ID=$(python -c "import uuid; print(uuid.uuid4())")
    echo "  Session ID: $SESSION_ID" | tee -a "$CYCLE_LOG"

    # =====================================================
    # PHASE A: EXPLORE — Deep codebase investigation
    # =====================================================
    echo "" | tee -a "$CYCLE_LOG"
    echo "[1/4] PHASE A: EXPLORE (up to $((PHASE_TIMEOUT / 60)) min)..." | tee -a "$CYCLE_LOG"

    cat "$CYCLE_DIR/prompt.md" | timeout $PHASE_TIMEOUT claude \
        --session-id "$SESSION_ID" \
        --model "$CLAUDE_MODEL" \
        --dangerously-skip-permissions \
        2>&1 | tee "$CYCLE_DIR/phase_a_explore.txt" || true

    echo "  Phase A done: $(wc -l < "$CYCLE_DIR/phase_a_explore.txt" 2>/dev/null) lines" | tee -a "$CYCLE_LOG"

    # =====================================================
    # PHASE B: BUILD — Push Claude to implement
    # =====================================================
    echo "" | tee -a "$CYCLE_LOG"
    echo "[2/4] PHASE B: BUILD (up to $((PHASE_TIMEOUT / 60)) min)..." | tee -a "$CYCLE_LOG"

    PHASE_B_PROMPT="Good exploration. Now I need you to actually BUILD something substantial. Don't just observe — implement.

Looking at what you explored:
1. Pick the HIGHEST-IMPACT change you identified
2. Implement it fully — create or modify multiple files if needed
3. If you're adding a feature, wire it end-to-end (service -> router -> frontend if applicable)
4. If you're fixing a bug, fix it AND add a regression test
5. If you're improving ML, actually modify the training pipeline or feature set

Target: 50-200 lines of meaningful new/modified code across 3+ files.

Don't be conservative. Make a real change. If something breaks, fix it.
Run tests after: python -m pytest backend/tests/ -v -m \"not slow\" --tb=short

What are you implementing, and why is it the highest-impact choice?"

    echo "$PHASE_B_PROMPT" | timeout $PHASE_TIMEOUT claude \
        --resume "$SESSION_ID" \
        --model "$CLAUDE_MODEL" \
        --dangerously-skip-permissions \
        2>&1 | tee "$CYCLE_DIR/phase_b_build.txt" || true

    echo "  Phase B done: $(wc -l < "$CYCLE_DIR/phase_b_build.txt" 2>/dev/null) lines" | tee -a "$CYCLE_LOG"

    # =====================================================
    # PHASE C: TEST & HARDEN — Force test writing
    # =====================================================
    echo "" | tee -a "$CYCLE_LOG"
    echo "[3/4] PHASE C: TEST & HARDEN (up to $((PHASE_TIMEOUT / 60)) min)..." | tee -a "$CYCLE_LOG"

    PHASE_C_PROMPT="Now harden what you built. This phase is mandatory.

1. Write NEW tests for every change you made. Not just 'does it not crash' — test correctness, edge cases, and invariants.
   - Add tests in backend/tests/ following the existing test file patterns
   - Each new function/feature needs at least 2-3 test cases
   - Test edge cases: empty data, extreme values, missing fields

2. Run the full fast test suite and fix any failures your changes caused:
   python -m pytest backend/tests/ -v -m \"not slow\" --tb=short

3. Look for code quality issues in what you wrote:
   - Any broad except blocks? Narrow them.
   - Any hardcoded values? Move to config.py.
   - Any fillna(0)? Remove it (LightGBM handles NaN natively).

4. Check that existing tests still pass. If you broke something, fix it NOW.

Show me the test file(s) you created/modified and the test results."

    echo "$PHASE_C_PROMPT" | timeout $PHASE_TIMEOUT claude \
        --resume "$SESSION_ID" \
        --model "$CLAUDE_MODEL" \
        --dangerously-skip-permissions \
        2>&1 | tee "$CYCLE_DIR/phase_c_test.txt" || true

    echo "  Phase C done: $(wc -l < "$CYCLE_DIR/phase_c_test.txt" 2>/dev/null) lines" | tee -a "$CYCLE_LOG"

    # =====================================================
    # PHASE D: REVIEW & REPORT — Self-critique + docs
    # =====================================================
    echo "" | tee -a "$CYCLE_LOG"
    echo "[4/4] PHASE D: REVIEW & REPORT (up to $((PHASE_TIMEOUT / 60)) min)..." | tee -a "$CYCLE_LOG"

    PHASE_D_PROMPT="Final phase. Be your own harshest critic.

1. SELF-REVIEW: Read through every file you modified. Ask yourself:
   - Is this actually an improvement, or did I just move complexity around?
   - Did I miss any edge cases?
   - Would this survive a code review from a senior engineer?
   - Is there a simpler way to achieve the same result?

2. If you find issues in your review, FIX THEM NOW.

3. Run tests one final time:
   python -m pytest backend/tests/ -v -m \"not slow\" --tb=short

4. Write the experiment report — be BRUTALLY HONEST:
   Create: lab/experiments/${CYCLE_ID}/experiment_report.json
   {
     \"cycle\": $CYCLE,
     \"timestamp\": \"$(date -Iseconds)\",
     \"research_track\": \"<which track>\",
     \"what_i_noticed\": \"<what caught your attention>\",
     \"hypothesis\": \"<what you thought could improve>\",
     \"what_i_did\": \"<detailed description of ALL changes>\",
     \"files_modified\": [\"list every file\"],
     \"files_created\": [\"any new files\"],
     \"tests_added\": [\"new test names\"],
     \"tests_fixed\": [\"previously-failing tests you fixed\"],
     \"lines_changed_approx\": <number>,
     \"results\": {
       \"before\": {\"metric\": \"value\"},
       \"after\": {\"metric\": \"value\"},
       \"improved\": true/false
     },
     \"analysis\": \"<honest assessment — did it actually work?>\",
     \"what_i_would_do_differently\": \"<self-critique>\",
     \"next_steps\": \"<what the next cycle should build on>\",
     \"confidence\": \"low/medium/high\",
     \"should_keep\": true/false,
     \"depth_rating\": \"TRIVIAL/LIGHT/MEDIUM/DEEP\"
   }

5. Commit everything:
   git add -A && git commit -m \"Lab ${CYCLE_ID}: <summary of what you built>\"

Be honest. A failed experiment logged honestly is more valuable than a fake success."

    echo "$PHASE_D_PROMPT" | timeout $PHASE_TIMEOUT claude \
        --resume "$SESSION_ID" \
        --model "$CLAUDE_MODEL" \
        --dangerously-skip-permissions \
        2>&1 | tee "$CYCLE_DIR/phase_d_report.txt" || true

    echo "  Phase D done: $(wc -l < "$CYCLE_DIR/phase_d_report.txt" 2>/dev/null) lines" | tee -a "$CYCLE_LOG"

    # =====================================================
    # VALIDATION (external — not trusting Claude's self-report)
    # =====================================================
    echo "" | tee -a "$CYCLE_LOG"
    echo "[POST] External validation..." | tee -a "$CYCLE_LOG"

    cd "$REPO_DIR"

    python -m pytest backend/tests/ -v -m "not slow" --tb=line \
        2>&1 | tee "$CYCLE_DIR/test_results.txt" || true

    CURRENT_FAILURES_FILE="$CYCLE_DIR/current_failures.txt"
    grep "^FAILED" "$CYCLE_DIR/test_results.txt" | sort > "$CURRENT_FAILURES_FILE" 2>/dev/null || true
    CURRENT_FAIL_COUNT=$(wc -l < "$CURRENT_FAILURES_FILE" 2>/dev/null || echo "0")

    NEW_FAILURES_FILE="$CYCLE_DIR/new_failures.txt"
    comm -23 "$CURRENT_FAILURES_FILE" "$BASELINE_FAILURES_FILE" > "$NEW_FAILURES_FILE" 2>/dev/null || true
    NEW_FAIL_COUNT=$(wc -l < "$NEW_FAILURES_FILE" 2>/dev/null || echo "0")

    TESTS_PASSED=$(grep -oP '\d+(?= passed)' "$CYCLE_DIR/test_results.txt" 2>/dev/null || echo "0")

    if [ "$NEW_FAIL_COUNT" -gt 0 ]; then
        echo "  [REVERT] $NEW_FAIL_COUNT NEW test failures!" | tee -a "$CYCLE_LOG"
        cat "$NEW_FAILURES_FILE" | tee -a "$CYCLE_LOG"
        git checkout -- backend/ frontend/ engine/ 2>/dev/null || true
    else
        echo "  [OK] Tests: $TESTS_PASSED passed, $NEW_FAIL_COUNT new failures" | tee -a "$CYCLE_LOG"
        if [ "$CURRENT_FAIL_COUNT" -lt "$BASELINE_FAIL_COUNT" ]; then
            FIXED=$((BASELINE_FAIL_COUNT - CURRENT_FAIL_COUNT))
            echo "  [BONUS] Fixed $FIXED pre-existing failures!" | tee -a "$CYCLE_LOG"
        fi
    fi

    # Re-run data generator for comparison
    python "$LAB_DIR/data_generator.py" \
        --output-dir "$CYCLE_DIR/data_after" \
        --cycle "$CYCLE" \
        2>&1 | tee -a "$CYCLE_LOG" || true

    python "$LAB_DIR/compare_results.py" \
        --before "$CYCLE_DIR/data" \
        --after "$CYCLE_DIR/data_after" \
        --output "$CYCLE_DIR/comparison.json" \
        2>&1 | tee -a "$CYCLE_LOG" || true

    # Commit (if Claude didn't already)
    CYCLE_END=$(date +%s)
    CYCLE_DURATION=$(( (CYCLE_END - CYCLE_START) / 60 ))

    cd "$REPO_DIR"
    git add -A
    git diff --cached --quiet 2>/dev/null || \
        git commit -m "Lab $CYCLE_ID (${CYCLE_DURATION}min)" --allow-empty 2>/dev/null || true

    # --- Cycle Summary ---
    echo "" | tee -a "$CYCLE_LOG"
    echo "  ===== Cycle $CYCLE Summary =====" | tee -a "$CYCLE_LOG"
    echo "  Duration: ${CYCLE_DURATION} min" | tee -a "$CYCLE_LOG"

    # Phase output sizes (proxy for depth of work)
    for phase_file in phase_a_explore phase_b_build phase_c_test phase_d_report; do
        if [ -f "$CYCLE_DIR/${phase_file}.txt" ]; then
            LINES=$(wc -l < "$CYCLE_DIR/${phase_file}.txt" 2>/dev/null)
            BYTES=$(wc -c < "$CYCLE_DIR/${phase_file}.txt" 2>/dev/null)
            echo "  ${phase_file}: ${LINES} lines, ${BYTES} bytes" | tee -a "$CYCLE_LOG"
        fi
    done

    if [ -f "$CYCLE_DIR/experiment_report.json" ]; then
        python -c "
import json
r = json.load(open('$CYCLE_DIR/experiment_report.json'))
print(f\"  Track: {r.get('research_track', 'N/A')}\")
print(f\"  Depth: {r.get('depth_rating', 'N/A')}\")
print(f\"  Result: {'IMPROVED' if r.get('results',{}).get('improved') else 'no improvement'}\")
print(f\"  Files: {len(r.get('files_modified', []))} modified, {len(r.get('files_created', []))} created\")
print(f\"  Tests added: {len(r.get('tests_added', []))}\")
print(f\"  Lines: ~{r.get('lines_changed_approx', '?')}\")
print(f\"  Self-critique: {r.get('what_i_would_do_differently', 'N/A')[:100]}\")
" 2>/dev/null || true
    else
        echo "  [MISS] No experiment report" | tee -a "$CYCLE_LOG"
    fi

    if [ -f "$CYCLE_DIR/comparison.json" ]; then
        python -c "
import json
c = json.load(open('$CYCLE_DIR/comparison.json'))
print(f\"  Net: {c.get('net_result', '?')} ({c.get('improvement_count', 0)} improvements)\")
" 2>/dev/null || true
    fi

    if [ "$NEW_FAIL_COUNT" -gt 0 ]; then
        echo "  [REVERTED] Changes reverted due to test failures" | tee -a "$CYCLE_LOG"
    fi

    echo "" | tee -a "$CYCLE_LOG"

    # Brief cooldown then continue
    if [ $CYCLE -lt $MAX_CYCLES ]; then
        sleep $COOLDOWN_SECONDS
    fi
done

TOTAL_HOURS=$(( ($(date +%s) - START_TIME) / 3600 ))
TOTAL_MIN=$(( ($(date +%s) - START_TIME) / 60 ))
echo ""
echo "==========================================================="
echo "  R&D LAB COMPLETE"
echo "  $CYCLE cycles in ${TOTAL_MIN} min (~${TOTAL_HOURS}h)"
echo "  Review: git log --oneline $RESEARCH_BRANCH -$MAX_CYCLES"
echo "  Merge:  git checkout main && git merge $RESEARCH_BRANCH"
echo "==========================================================="
