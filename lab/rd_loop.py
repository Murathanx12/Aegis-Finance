"""
Aegis Finance - Autonomous R&D Loop v6
Single deep session per cycle. Claude decides its own workflow.

No rigid phases. No prescriptive steps. Claude is the owner.
It decides what to explore, what to build, what to test, and how.

Usage:
  python lab/rd_loop.py                    # opus, auto-detect cycle
  python lab/rd_loop.py --cycles 50        # run up to cycle 50
  python lab/rd_loop.py --model sonnet     # cheaper
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).parent.parent
LAB_DIR = REPO_DIR / "lab"
EXPERIMENTS_DIR = LAB_DIR / "experiments"
LOGS_DIR = LAB_DIR / "logs"

SESSION_TIMEOUT = 2400  # 40 min max per session

import shutil
CLAUDE_CMD = shutil.which("claude") or shutil.which("claude.cmd") or "claude"


# ---------------------------------------------------------------------------
# Build the prompt — one shot, full context, full freedom
# ---------------------------------------------------------------------------

def build_prompt(cycle: int, cycle_dir: Path, baseline_failures: str) -> str:

    # Load engine data
    data_dir = cycle_dir / "data"
    data_sections = []
    if data_dir.is_dir():
        for f in sorted(data_dir.glob("*.json")):
            try:
                content = json.loads(f.read_text(encoding="utf-8"))
                data_str = json.dumps(content, indent=2, default=str)
                if len(data_str) > 4000:
                    data_str = data_str[:4000] + "\n... [truncated]"
                data_sections.append(f"### {f.stem}\n```json\n{data_str}\n```")
            except:
                pass
    data_block = "\n\n".join(data_sections) if data_sections else "No data."

    # Last 3 cycle summaries (brief — don't anchor Claude to old approaches)
    learnings = []
    for prev in range(max(1, cycle - 3), cycle):
        rp = EXPERIMENTS_DIR / f"cycle_{prev:03d}" / "experiment_report.json"
        if rp.exists():
            try:
                r = json.loads(rp.read_text(encoding="utf-8"))
                learnings.append(
                    f"Cycle {prev}: {r.get('what_i_did', '?')[:120]} "
                    f"({'improved' if r.get('results', {}).get('improved') else 'neutral'})"
                )
            except:
                pass
    past_block = "\n".join(learnings) if learnings else "No recent history."

    # Untouched files
    modified = set()
    for prev in range(1, cycle):
        rp = EXPERIMENTS_DIR / f"cycle_{prev:03d}" / "experiment_report.json"
        if rp.exists():
            try:
                r = json.loads(rp.read_text(encoding="utf-8"))
                modified.update(r.get("files_modified", []))
            except:
                pass

    all_files = [
        "backend/services/monte_carlo.py", "backend/services/stock_analyzer.py",
        "backend/services/sector_analyzer.py", "backend/services/portfolio_engine.py",
        "backend/services/crash_model.py", "backend/services/signal_engine.py",
        "backend/services/regime_detector.py", "backend/services/risk_scorer.py",
        "backend/services/shap_explainer.py", "backend/services/news_intelligence.py",
        "backend/services/sentiment_analyzer.py", "backend/services/data_quality.py",
        "backend/services/net_liquidity.py", "backend/services/return_model.py",
        "backend/services/external_validator.py", "backend/services/regime_validator.py",
        "backend/services/drift_detector.py", "backend/services/llm_analyzer.py",
        "engine/training/features.py", "engine/training/train_crash_model.py",
        "engine/validation/walk_forward.py", "engine/validation/metrics.py",
        "frontend/src/app/", "frontend/src/components/", "frontend/src/lib/",
    ]
    untouched = [f for f in all_files if f not in modified]

    return f"""# Aegis Finance — R&D Cycle {cycle}

You are the owner of this codebase. This is your sandbox.

You have 40 minutes. You have COMPLETE freedom:
- Read, write, create, delete any file in backend/, frontend/, engine/
- Install any package (pip install, npm install)
- Clone any open-source repo for reference
- Access any public API (yfinance, FRED, Alpha Vantage, etc.)
- Download datasets, models, or tools
- Restructure code, refactor architecture, add new services
- If you need an API key that costs money, note it in your report — don't block on it

You decide:
- What to work on (no assigned track — find the highest-impact thing)
- How to work (your own workflow — explore, build, test in whatever order makes sense)
- What to test (run targeted tests, not the full 675-test suite — be smart about it)
- When you're done

## Current engine state (from real backend services)

{data_block}

## Recent cycles (for context, not to constrain you)

{past_block}

## Files that have NEVER been modified by the lab

{chr(10).join('- ' + f for f in untouched[:15])}

## Pre-existing test failures

```
{baseline_failures or "None — all tests passing"}
```

## One rule

Don't break existing tests. Run `python -m pytest backend/tests/<relevant_file> -v --tb=short`
on the specific tests related to your changes — NOT the full suite (it has 675 tests and
takes 9 minutes). Only run the full suite if you're unsure what you might have affected.

## When you're done

1. Write your experiment report:
   lab/experiments/cycle_{cycle:03d}/experiment_report.json

   Include: what you noticed, what you did, files modified, files created,
   tests added, results (before/after), honest analysis, self-critique,
   next steps, confidence, depth rating.

2. Commit: git add -A && git commit -m "Lab cycle_{cycle:03d}: <summary>"

Think fresh. Don't follow patterns from past cycles just because they worked.
Find what this codebase actually needs right now and build it.
"""


# ---------------------------------------------------------------------------
# Run one cycle — single deep session
# ---------------------------------------------------------------------------

def run_cycle(cycle: int, model: str, baseline_failures: str):
    cycle_id = f"cycle_{cycle:03d}"
    cycle_dir = EXPERIMENTS_DIR / cycle_id
    cycle_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    cycle_start = time.time()

    print(f"\n{'='*60}")
    print(f"  CYCLE {cycle} — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")

    # Data generation
    print("\n  Generating engine data...")
    subprocess.run(
        [sys.executable, str(LAB_DIR / "data_generator.py"),
         "--output-dir", str(cycle_dir / "data"), "--cycle", str(cycle)],
        cwd=str(REPO_DIR), timeout=300,
    )

    # Build prompt
    prompt = build_prompt(cycle, cycle_dir, baseline_failures)
    (cycle_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    # Single deep session — Claude owns its workflow
    print(f"\n  Claude session starting (up to {SESSION_TIMEOUT // 60} min, model={model})...")

    try:
        result = subprocess.run(
            [CLAUDE_CMD, "--model", model, "--session-id", session_id,
             "--dangerously-skip-permissions"],
            input=prompt,
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=SESSION_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        output = result.stdout or ""
        stderr = result.stderr or ""

        # Detect rate limit
        if "hit your limit" in output.lower() or "hit your limit" in stderr.lower():
            print("  [RATE LIMITED] Waiting 10 min...")
            (cycle_dir / "session_output.txt").write_text("[RATE LIMITED]", encoding="utf-8")
            time.sleep(600)
            return

        (cycle_dir / "session_output.txt").write_text(
            output + "\n---STDERR---\n" + stderr, encoding="utf-8")

        elapsed = int(time.time() - cycle_start)
        lines = len(output.strip().split("\n")) if output.strip() else 0
        print(f"  Session done: {lines} lines, {len(output):,} chars, {elapsed}s")

    except subprocess.TimeoutExpired:
        print(f"  Session TIMEOUT after {SESSION_TIMEOUT}s")
        (cycle_dir / "session_output.txt").write_text(
            f"[TIMEOUT after {SESSION_TIMEOUT}s]", encoding="utf-8")

    except Exception as e:
        print(f"  Session ERROR: {e}")
        (cycle_dir / "session_output.txt").write_text(f"[ERROR: {e}]", encoding="utf-8")

    # Light validation — only run changed test files, not full suite
    print("\n  Validating (targeted)...")
    try:
        # Find which test files might be affected
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(REPO_DIR), capture_output=True, text=True, timeout=10,
        )
        changed_files = diff_result.stdout.strip().split("\n") if diff_result.stdout.strip() else []

        # Map changed service files to their test files
        test_files_to_run = set()
        for f in changed_files:
            if f.startswith("backend/tests/"):
                test_files_to_run.add(str(REPO_DIR / f))
            elif f.startswith("backend/services/"):
                service_name = Path(f).stem
                test_path = REPO_DIR / "backend" / "tests" / f"test_{service_name}.py"
                if test_path.exists():
                    test_files_to_run.add(str(test_path))
            elif f.startswith("backend/routers/"):
                test_path = REPO_DIR / "backend" / "tests" / "test_routers.py"
                if test_path.exists():
                    test_files_to_run.add(str(test_path))

        # Always include core tests as smoke check
        for core in ["test_monte_carlo.py", "test_signal_engine.py", "test_crash_calibration.py"]:
            core_path = REPO_DIR / "backend" / "tests" / core
            if core_path.exists():
                test_files_to_run.add(str(core_path))

        if test_files_to_run:
            test_cmd = [sys.executable, "-m", "pytest"] + list(test_files_to_run) + [
                "-v", "--tb=line", "-x"  # stop on first failure
            ]
            test_result = subprocess.run(
                test_cmd, cwd=str(REPO_DIR),
                capture_output=True, text=True, timeout=300,
            )
            test_out = test_result.stdout + test_result.stderr
        else:
            # No test files identified — run core smoke tests only
            test_result = subprocess.run(
                [sys.executable, "-m", "pytest", "backend/tests/test_monte_carlo.py",
                 "backend/tests/test_signal_engine.py", "-v", "--tb=line"],
                cwd=str(REPO_DIR), capture_output=True, text=True, timeout=120,
            )
            test_out = test_result.stdout + test_result.stderr

        (cycle_dir / "test_results.txt").write_text(test_out, encoding="utf-8")

        passed_m = re.search(r"(\d+) passed", test_out)
        failed_m = re.search(r"(\d+) failed", test_out)
        tests_passed = int(passed_m.group(1)) if passed_m else 0
        tests_failed = int(failed_m.group(1)) if failed_m else 0

        if tests_failed > 0:
            print(f"  [WARN] {tests_failed} test failures in targeted run")
            # Don't auto-revert — Claude may have intentionally changed test expectations
            # Just log it
        else:
            print(f"  [OK] {tests_passed} targeted tests passed")

    except subprocess.TimeoutExpired:
        print("  [WARN] Targeted tests timed out")
    except Exception as e:
        print(f"  [WARN] Validation error: {e}")

    # Post-cycle comparison
    try:
        subprocess.run(
            [sys.executable, str(LAB_DIR / "data_generator.py"),
             "--output-dir", str(cycle_dir / "data_after"), "--cycle", str(cycle)],
            cwd=str(REPO_DIR), timeout=300, capture_output=True,
        )
        subprocess.run(
            [sys.executable, str(LAB_DIR / "compare_results.py"),
             "--before", str(cycle_dir / "data"),
             "--after", str(cycle_dir / "data_after"),
             "--output", str(cycle_dir / "comparison.json")],
            cwd=str(REPO_DIR), timeout=60, capture_output=True,
        )
    except:
        pass

    # Commit if Claude didn't already
    duration = int((time.time() - cycle_start) / 60)
    subprocess.run(["git", "add", "-A"], cwd=str(REPO_DIR))
    subprocess.run(
        ["git", "commit", "-m", f"Lab {cycle_id} ({duration}min)", "--allow-empty"],
        cwd=str(REPO_DIR), capture_output=True,
    )

    # Summary
    print(f"\n  Cycle {cycle} done in {duration} min")

    report_path = cycle_dir / "experiment_report.json"
    if report_path.exists():
        try:
            r = json.loads(report_path.read_text(encoding="utf-8"))
            print(f"  What: {r.get('what_i_did', '?')[:120]}")
            print(f"  Depth: {r.get('depth_rating', '?')}")
            print(f"  Result: {'improved' if r.get('results', {}).get('improved') else 'neutral'}")
            print(f"  Files: {len(r.get('files_modified', []))} modified, "
                  f"{len(r.get('files_created', []))} created")
            print(f"  Tests: +{len(r.get('tests_added', []))}")
        except:
            pass
    else:
        print("  [MISS] No experiment report")

    session_path = cycle_dir / "session_output.txt"
    if session_path.exists():
        print(f"  Session: {session_path.stat().st_size:,} bytes")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Aegis Finance R&D Loop v6")
    parser.add_argument("--cycles", type=int, default=50)
    parser.add_argument("--model", default="opus")
    parser.add_argument("--start-cycle", type=int, default=None)
    parser.add_argument("--branch", default="lab/autonomous-rd")
    args = parser.parse_args()

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Git setup
    subprocess.run(["git", "checkout", args.branch], cwd=str(REPO_DIR),
                   capture_output=True)

    # Baseline
    print("[BASELINE] Running core smoke tests...")
    bl = subprocess.run(
        [sys.executable, "-m", "pytest",
         "backend/tests/test_monte_carlo.py",
         "backend/tests/test_signal_engine.py",
         "backend/tests/test_crash_calibration.py",
         "-v", "--tb=line"],
        cwd=str(REPO_DIR), capture_output=True, text=True, timeout=120,
    )
    baseline_failures = "\n".join(
        l for l in bl.stdout.split("\n") if l.startswith("FAILED")
    )
    passed_m = re.search(r"(\d+) passed", bl.stdout)
    print(f"  Core tests: {passed_m.group(1) if passed_m else '?'} passed")

    # Auto-detect start
    if args.start_cycle:
        start = args.start_cycle
    else:
        existing = sorted(EXPERIMENTS_DIR.glob("cycle_*"))
        start = len(existing) + 1

    print(f"\n{'='*60}")
    print(f"  AEGIS R&D LAB v6 — Sandbox Mode")
    print(f"  Model: {args.model} | Cycles: {start}-{args.cycles}")
    print(f"  Session: {SESSION_TIMEOUT // 60} min | Branch: {args.branch}")
    print(f"  Claude decides its own workflow")
    print(f"{'='*60}")

    for cycle in range(start, args.cycles + 1):
        try:
            run_cycle(cycle, args.model, baseline_failures)
        except Exception as e:
            print(f"\n  [FATAL] Cycle {cycle}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        if cycle < args.cycles:
            print(f"\n  Cooldown 30s...")
            time.sleep(30)

    print(f"\n{'='*60}")
    print(f"  DONE — cycles {start}-{args.cycles}")
    print(f"  git log --oneline {args.branch} -{args.cycles}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
