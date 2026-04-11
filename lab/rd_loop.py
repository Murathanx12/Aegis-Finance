"""
Aegis Finance - Autonomous R&D Loop v4
Uses Claude Code SDK for proper multi-turn conversations.

Each cycle is a 4-phase conversation:
  Phase A: EXPLORE — Deep codebase investigation (read-only tools)
  Phase B: BUILD  — Implement highest-impact change (full tools)
  Phase C: TEST   — Write tests, validate, harden (full tools)
  Phase D: REVIEW — Self-critique, report, commit (full tools)

Usage:
  python lab/rd_loop.py                    # Run with defaults
  python lab/rd_loop.py --cycles 10        # Run 10 cycles
  python lab/rd_loop.py --model opus       # Use Opus for deeper reasoning
  python lab/rd_loop.py --start-cycle 18   # Resume from cycle 18
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from claude_code_sdk import ClaudeCodeOptions, ResultMessage, SystemMessage, query

REPO_DIR = Path(__file__).parent.parent
LAB_DIR = REPO_DIR / "lab"
EXPERIMENTS_DIR = LAB_DIR / "experiments"
LOGS_DIR = LAB_DIR / "logs"


# ---------------------------------------------------------------------------
# Prompt phases — these simulate the back-and-forth of a real conversation
# ---------------------------------------------------------------------------

def build_phase_a_prompt(cycle: int, cycle_dir: Path, baseline_failures: str) -> str:
    """Phase A: Explore. Read-heavy, no edits yet."""

    # Load data from data generator
    data_dir = cycle_dir / "data"
    data_sections = []
    if data_dir.is_dir():
        for f in sorted(data_dir.glob("*.json")):
            try:
                content = json.loads(f.read_text(encoding="utf-8"))
                data_str = json.dumps(content, indent=2, default=str)
                if len(data_str) > 5000:
                    data_str = data_str[:5000] + "\n... [truncated]"
                data_sections.append(f"### {f.stem}\n```json\n{data_str}\n```")
            except:
                pass

    data_block = "\n\n".join(data_sections) if data_sections else "No data collected."

    # Load past learnings (last 5 cycles)
    learnings = []
    for prev in range(max(1, cycle - 5), cycle):
        report_path = EXPERIMENTS_DIR / f"cycle_{prev:03d}" / "experiment_report.json"
        if report_path.exists():
            try:
                r = json.loads(report_path.read_text(encoding="utf-8"))
                improved = r.get("results", {}).get("improved", False)
                learnings.append(
                    f"Cycle {prev} ({'OK' if improved else 'FAIL'}): "
                    f"{r.get('hypothesis', '?')[:80]} — "
                    f"Files: {', '.join(r.get('files_modified', []))}"
                )
            except:
                pass

    past_block = "\n".join(learnings) if learnings else "No prior cycles."

    # Cumulative file tracking
    all_modified = set()
    for prev in range(1, cycle):
        report_path = EXPERIMENTS_DIR / f"cycle_{prev:03d}" / "experiment_report.json"
        if report_path.exists():
            try:
                r = json.loads(report_path.read_text(encoding="utf-8"))
                for f in r.get("files_modified", []):
                    all_modified.add(f)
            except:
                pass

    all_services = [
        "backend/services/monte_carlo.py", "backend/services/stock_analyzer.py",
        "backend/services/sector_analyzer.py", "backend/services/portfolio_engine.py",
        "backend/services/crash_model.py", "backend/services/signal_engine.py",
        "backend/services/regime_detector.py", "backend/services/risk_scorer.py",
        "backend/services/shap_explainer.py", "backend/services/news_intelligence.py",
        "backend/services/sentiment_analyzer.py", "backend/services/data_quality.py",
        "backend/services/net_liquidity.py", "backend/services/return_model.py",
        "backend/services/external_validator.py", "backend/services/regime_validator.py",
        "backend/services/drift_detector.py", "backend/services/llm_analyzer.py",
        "backend/services/savings_calculator.py",
        "engine/training/features.py", "engine/training/feature_selection.py",
        "engine/training/train_crash_model.py",
        "engine/validation/walk_forward.py", "engine/validation/purged_cv.py",
    ]
    untouched = [f for f in all_services if f not in all_modified]

    # Research track rotation (7 tracks)
    tracks = [
        ("ML & Feature Engineering", "Improve crash model, add features, retrain, improve AUC"),
        ("Statistical Engine & Monte Carlo", "Regime-switching MC, stochastic vol, copulas, backtesting"),
        ("Test Suite & Code Quality", "Write tests for uncovered services, fix smells, add edge cases"),
        ("New Features & Capabilities", "CVaR, factor exposure, drawdown signals, crypto support"),
        ("Frontend & Visualization", "Fix TS errors, add loading states, charts, dark mode"),
        ("Service Integration & Wiring", "Find dead code, wire disconnected services, verify endpoints"),
        ("Performance & Reliability", "Caching, retries, timeouts, logging, graceful degradation"),
    ]
    primary = tracks[(cycle - 1) % len(tracks)]
    secondary = tracks[cycle % len(tracks)]

    return f"""# Aegis Finance R&D Lab — Cycle {cycle}, Phase A: EXPLORE

You are a senior quant engineer with full autonomy over this codebase.
This is Phase A of 4. Right now: **explore deeply, don't implement yet.**

## Your Research Track

**Primary: {primary[0]}** — {primary[1]}
**Secondary: {secondary[0]}** — {secondary[1]}

You may work on either track or something more urgent you discover.

## Engine Output (from REAL backend services)

{data_block}

## Past Cycles (last 5)

{past_block}

## Files NEVER modified in any cycle (explore these!)

{chr(10).join('- ' + f for f in untouched)}

## Pre-existing test failures

```
{baseline_failures}
```

## Your Job in This Phase

Spend this entire phase EXPLORING. Read at minimum:
1. 5+ service files in backend/services/
2. 2+ router files in backend/routers/
3. backend/config.py
4. At least 2 files from the "never touched" list above
5. Run: python -m pytest backend/tests/ -v -m "not slow" --tb=short

Then report:
- What are the 3 biggest problems/opportunities you found?
- For each: what's wrong, where exactly (file:line), and how would you fix it?
- Which one has the highest impact if fixed?
- Any services that are completely disconnected (exist but never called)?

Be specific. File paths, line numbers, code snippets. I need enough detail
to evaluate your findings before we move to implementation.
"""


PHASE_B_PROMPT = """Good exploration. Now BUILD.

Pick the HIGHEST-IMPACT finding from your exploration and implement it fully.

Requirements:
1. Modify 3+ files minimum — this should be a real change, not a one-liner
2. If adding a feature: wire it service → router → endpoint (and frontend if applicable)
3. If fixing a bug: fix it AND think about similar bugs elsewhere
4. If improving ML: actually change the training pipeline or feature engineering
5. Move any new parameters to backend/config.py
6. Target 50-200 lines of meaningful code changes

After implementing, run tests:
  python -m pytest backend/tests/ -v -m "not slow" --tb=short

If tests fail because of your changes, fix them. If you broke something, debug it.

What are you implementing and why? Show me the changes as you make them.
"""


PHASE_C_PROMPT = """Now harden what you built. This phase is mandatory — don't skip it.

1. **Write NEW tests** for every change you made:
   - Add to existing test files in backend/tests/ or create new ones
   - Each new function/feature needs 2-3 test cases minimum
   - Test edge cases: empty data, extreme values, None inputs, single-element lists
   - Test invariants: monotonicity, non-negative prices, score ranges

2. **Run the full fast suite** and fix any failures:
   python -m pytest backend/tests/ -v -m "not slow" --tb=short

3. **Quality check** your own code:
   - Narrow any broad `except:` blocks to specific exceptions
   - Remove any `fillna(0)` (LightGBM handles NaN; use SimpleImputer for sklearn)
   - Move hardcoded values to config.py
   - Add type hints to new function signatures

4. **Look for regressions**: did your changes break any service that was working before?

Show me the tests you wrote and the full pytest output.
"""


PHASE_D_PROMPT = """Final phase. Self-critique and documentation.

1. **Self-review**: Read every file you modified. Ask yourself:
   - Is this actually better, or did I just move complexity around?
   - Would this survive code review from a senior engineer?
   - Did I introduce any edge cases I didn't test?
   - Is there a simpler approach I missed?

2. **Fix anything** you find in the review.

3. **Final test run**:
   python -m pytest backend/tests/ -v -m "not slow" --tb=short

4. **Write the experiment report** (REQUIRED):
   Create file: lab/experiments/cycle_XXX/experiment_report.json

   ```json
   {
     "cycle": <number>,
     "timestamp": "<ISO timestamp>",
     "research_track": "<which track>",
     "what_i_noticed": "<what caught your attention in exploration>",
     "hypothesis": "<what you thought could improve>",
     "what_i_did": "<detailed description of ALL changes>",
     "files_modified": ["<every file>"],
     "files_created": ["<new files>"],
     "tests_added": ["<test function names>"],
     "tests_fixed": ["<previously-failing tests fixed>"],
     "lines_changed_approx": <number>,
     "results": {
       "before": {"<metric>": "<value>"},
       "after": {"<metric>": "<value>"},
       "improved": true/false
     },
     "analysis": "<honest assessment>",
     "what_i_would_do_differently": "<self-critique>",
     "next_steps": "<what next cycle should build on>",
     "confidence": "<low/medium/high>",
     "should_keep": true/false,
     "depth_rating": "<TRIVIAL/LIGHT/MEDIUM/DEEP>"
   }
   ```

5. **Commit**:
   git add -A && git commit -m "Lab cycle_XXX: <what you built>"

Be brutally honest in the report. A failed experiment logged honestly
is more valuable than a fake success.
"""


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

async def _run_phase_cli_fallback(prompt: str, session_id: str | None,
                                  model: str, phase_name: str,
                                  cycle_dir: Path, output_lines: list,
                                  max_turns: int | None = None) -> str | None:
    """Fallback: run via CLI subprocess when SDK hits parsing issues."""
    import uuid

    if session_id is None:
        session_id = str(uuid.uuid4())

    cmd = ["claude", "--model", model, "--dangerously-skip-permissions"]

    # First phase uses --session-id, subsequent use --resume
    if not (cycle_dir / "phase_a_explore.txt").exists() or phase_name == "phase_a_explore":
        cmd.extend(["--session-id", session_id])
    else:
        cmd.extend(["--resume", session_id])

    result = subprocess.run(
        cmd,
        input=prompt,
        cwd=str(REPO_DIR),
        capture_output=True,
        text=True,
        timeout=900,  # 15 min per phase
    )

    output_lines.append(result.stdout)
    if result.stderr:
        output_lines.append(f"[stderr]: {result.stderr[:500]}")

    return session_id


async def run_phase(prompt: str, session_id: str | None, model: str,
                    phase_name: str, cycle_dir: Path,
                    allowed_tools: list[str] | None = None,
                    max_turns: int | None = None) -> str | None:
    """Run one phase of the conversation. Returns session_id for resume."""

    options = ClaudeCodeOptions(
        model=model,
        permission_mode="bypassPermissions",
        cwd=str(REPO_DIR),
        max_turns=max_turns,
    )

    if allowed_tools:
        options.allowed_tools = allowed_tools

    if session_id:
        options.resume = session_id

    output_lines = []
    result_text = ""
    found_session_id = session_id

    phase_start = time.time()

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, SystemMessage):
                # Capture session ID from init message
                if hasattr(message, 'session_id') and message.session_id:
                    found_session_id = message.session_id
            elif isinstance(message, ResultMessage):
                result_text = message.result if hasattr(message, 'result') else str(message)
                output_lines.append(result_text)
            else:
                # Capture any text output
                text = str(message)
                if text:
                    output_lines.append(text)

    except Exception as e:
        err_name = type(e).__name__
        # SDK may not handle all CLI message types (e.g. rate_limit_event)
        # Fall back to CLI subprocess if SDK fails
        if "MessageParseError" in err_name or "Unknown message type" in str(e):
            print(f"    [SDK FALLBACK] {e} — falling back to CLI subprocess")
            found_session_id = await _run_phase_cli_fallback(
                prompt, session_id, model, phase_name, cycle_dir, output_lines, max_turns
            )
        else:
            output_lines.append(f"\n[ERROR in {phase_name}]: {err_name}: {e}")

    phase_duration = time.time() - phase_start

    # Save phase output
    output_path = cycle_dir / f"{phase_name}.txt"
    full_output = "\n".join(output_lines)
    output_path.write_text(full_output, encoding="utf-8")

    print(f"    {phase_name}: {len(output_lines)} messages, "
          f"{len(full_output)} chars, {phase_duration:.0f}s")

    return found_session_id


async def run_cycle(cycle: int, model: str, baseline_failures: str):
    """Run one complete 4-phase R&D cycle."""

    cycle_id = f"cycle_{cycle:03d}"
    cycle_dir = EXPERIMENTS_DIR / cycle_id
    cycle_dir.mkdir(parents=True, exist_ok=True)

    cycle_start = time.time()
    print(f"\n{'='*60}")
    print(f"  CYCLE {cycle} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # --- Data generation ---
    print("\n  [0/4] Generating engine data...")
    subprocess.run(
        [sys.executable, str(LAB_DIR / "data_generator.py"),
         "--output-dir", str(cycle_dir / "data"),
         "--cycle", str(cycle)],
        cwd=str(REPO_DIR),
        timeout=300,
    )

    # --- Phase A: Explore ---
    print("\n  [1/4] Phase A: EXPLORE")
    phase_a_prompt = build_phase_a_prompt(cycle, cycle_dir, baseline_failures)
    (cycle_dir / "prompt_a.md").write_text(phase_a_prompt, encoding="utf-8")

    session_id = await run_phase(
        prompt=phase_a_prompt,
        session_id=None,
        model=model,
        phase_name="phase_a_explore",
        cycle_dir=cycle_dir,
        max_turns=30,
    )

    # --- Phase B: Build ---
    print("\n  [2/4] Phase B: BUILD")
    session_id = await run_phase(
        prompt=PHASE_B_PROMPT,
        session_id=session_id,
        model=model,
        phase_name="phase_b_build",
        cycle_dir=cycle_dir,
        max_turns=40,
    )

    # --- Phase C: Test ---
    print("\n  [3/4] Phase C: TEST & HARDEN")
    session_id = await run_phase(
        prompt=PHASE_C_PROMPT,
        session_id=session_id,
        model=model,
        phase_name="phase_c_test",
        cycle_dir=cycle_dir,
        max_turns=30,
    )

    # --- Phase D: Review & Report ---
    print("\n  [4/4] Phase D: REVIEW & REPORT")
    phase_d = PHASE_D_PROMPT.replace("cycle_XXX", cycle_id)
    session_id = await run_phase(
        prompt=phase_d,
        session_id=session_id,
        model=model,
        phase_name="phase_d_report",
        cycle_dir=cycle_dir,
        max_turns=20,
    )

    # --- External validation ---
    print("\n  [POST] External validation...")
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "-v",
         "-m", "not slow", "--tb=line"],
        cwd=str(REPO_DIR),
        capture_output=True, text=True, timeout=180,
    )

    test_output = test_result.stdout + test_result.stderr
    (cycle_dir / "test_results.txt").write_text(test_output, encoding="utf-8")

    # Check for new failures
    import re
    passed_match = re.search(r"(\d+) passed", test_output)
    failed_lines = [l for l in test_output.split("\n") if l.startswith("FAILED")]

    tests_passed = int(passed_match.group(1)) if passed_match else 0
    new_failures = []
    baseline_set = set(baseline_failures.strip().split("\n")) if baseline_failures.strip() else set()
    for fl in failed_lines:
        if fl.strip() not in baseline_set:
            new_failures.append(fl)

    if new_failures:
        print(f"  [REVERT] {len(new_failures)} NEW test failures!")
        for nf in new_failures:
            print(f"    {nf}")
        subprocess.run(["git", "checkout", "--", "backend/", "frontend/", "engine/"],
                       cwd=str(REPO_DIR))
    else:
        print(f"  [OK] Tests: {tests_passed} passed, 0 new failures")

    # Post-cycle data generation + comparison
    subprocess.run(
        [sys.executable, str(LAB_DIR / "data_generator.py"),
         "--output-dir", str(cycle_dir / "data_after"),
         "--cycle", str(cycle)],
        cwd=str(REPO_DIR), timeout=300,
        capture_output=True,
    )

    subprocess.run(
        [sys.executable, str(LAB_DIR / "compare_results.py"),
         "--before", str(cycle_dir / "data"),
         "--after", str(cycle_dir / "data_after"),
         "--output", str(cycle_dir / "comparison.json")],
        cwd=str(REPO_DIR), timeout=60,
        capture_output=True,
    )

    # Commit if Claude didn't already
    subprocess.run(["git", "add", "-A"], cwd=str(REPO_DIR))
    cycle_duration = int((time.time() - cycle_start) / 60)
    subprocess.run(
        ["git", "commit", "-m", f"Lab {cycle_id} ({cycle_duration}min)",
         "--allow-empty"],
        cwd=str(REPO_DIR), capture_output=True,
    )

    # --- Summary ---
    print(f"\n  Cycle {cycle} complete in {cycle_duration} min")

    report_path = cycle_dir / "experiment_report.json"
    if report_path.exists():
        try:
            r = json.loads(report_path.read_text(encoding="utf-8"))
            print(f"  Track: {r.get('research_track', '?')}")
            print(f"  Depth: {r.get('depth_rating', '?')}")
            print(f"  Result: {'IMPROVED' if r.get('results', {}).get('improved') else 'no improvement'}")
            print(f"  Files: {len(r.get('files_modified', []))} modified")
            print(f"  Tests added: {len(r.get('tests_added', []))}")
            print(f"  Lines: ~{r.get('lines_changed_approx', '?')}")
        except:
            pass
    else:
        print("  [MISS] No experiment report written")

    comp_path = cycle_dir / "comparison.json"
    if comp_path.exists():
        try:
            c = json.loads(comp_path.read_text(encoding="utf-8"))
            print(f"  Net: {c.get('net_result', '?')} "
                  f"({c.get('improvement_count', 0)} improvements)")
        except:
            pass


async def main():
    parser = argparse.ArgumentParser(description="Aegis Finance R&D Loop")
    parser.add_argument("--cycles", type=int, default=20, help="Number of cycles")
    parser.add_argument("--model", default="sonnet", help="Claude model (sonnet/opus)")
    parser.add_argument("--start-cycle", type=int, default=None,
                        help="Starting cycle number (auto-detects if omitted)")
    parser.add_argument("--branch", default="lab/autonomous-rd",
                        help="Git branch for research")
    args = parser.parse_args()

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Git setup
    subprocess.run(["git", "stash"], cwd=str(REPO_DIR),
                   capture_output=True)
    subprocess.run(["git", "checkout", args.branch], cwd=str(REPO_DIR),
                   capture_output=True)

    # Baseline test failures
    print("[BASELINE] Running test suite...")
    baseline_result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "-v",
         "-m", "not slow", "--tb=line"],
        cwd=str(REPO_DIR), capture_output=True, text=True, timeout=180,
    )
    baseline_failures = "\n".join(
        l for l in baseline_result.stdout.split("\n") if l.startswith("FAILED")
    )
    baseline_count = len(baseline_failures.strip().split("\n")) if baseline_failures.strip() else 0
    print(f"  Baseline: {baseline_count} pre-existing failures")

    # Auto-detect start cycle
    if args.start_cycle is not None:
        start = args.start_cycle
    else:
        existing = list(EXPERIMENTS_DIR.glob("cycle_*"))
        start = len(existing) + 1

    print(f"\n{'='*60}")
    print(f"  AEGIS R&D LAB v4 — Python SDK")
    print(f"  Cycles: {start} to {args.cycles}")
    print(f"  Model: {args.model}")
    print(f"  Branch: {args.branch}")
    print(f"{'='*60}")

    for cycle in range(start, args.cycles + 1):
        try:
            await run_cycle(cycle, args.model, baseline_failures)
        except Exception as e:
            print(f"\n  [FATAL] Cycle {cycle} crashed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        # Brief cooldown
        if cycle < args.cycles:
            print(f"\n  Cooldown 30s...")
            await asyncio.sleep(30)

    print(f"\n{'='*60}")
    print(f"  R&D LAB COMPLETE — {args.cycles - start + 1} cycles")
    print(f"  Review: git log --oneline {args.branch} -{args.cycles}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
