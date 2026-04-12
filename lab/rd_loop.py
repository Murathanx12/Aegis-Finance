"""
Aegis Finance - Autonomous R&D Loop v5
Uses subprocess + stdin piping for multi-turn conversations.
Proven reliable on Windows (no SDK dependency).

Each cycle is a 4-phase CONVERSATION with the same session:
  Phase A: EXPLORE — Deep codebase investigation
  Phase B: BUILD  — Implement highest-impact change
  Phase C: TEST   — Write tests, validate, harden
  Phase D: REVIEW — Self-critique, report, commit

Usage:
  python lab/rd_loop.py                         # Defaults (opus, 20 cycles)
  python lab/rd_loop.py --cycles 5              # Quick run
  python lab/rd_loop.py --model sonnet          # Cheaper model
  python lab/rd_loop.py --start-cycle 19        # Resume
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

PHASE_TIMEOUT = 1200  # 20 min per phase

# On Windows, npm-installed CLIs need .cmd extension for subprocess
import shutil
CLAUDE_CMD = shutil.which("claude") or shutil.which("claude.cmd") or "claude"


# ---------------------------------------------------------------------------
# Phase prompts
# ---------------------------------------------------------------------------

def build_phase_a_prompt(cycle: int, cycle_dir: Path, baseline_failures: str) -> str:
    """Phase A: Deep exploration."""

    # Load data
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

    # Past learnings (last 5)
    learnings = []
    for prev in range(max(1, cycle - 5), cycle):
        rp = EXPERIMENTS_DIR / f"cycle_{prev:03d}" / "experiment_report.json"
        if rp.exists():
            try:
                r = json.loads(rp.read_text(encoding="utf-8"))
                learnings.append(
                    f"Cycle {prev}: {r.get('hypothesis', '?')[:80]} "
                    f"({'OK' if r.get('results', {}).get('improved') else 'FAIL'})"
                )
            except:
                pass
    past_block = "\n".join(learnings) if learnings else "No prior cycles."

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
    ]
    untouched = [f for f in all_files if f not in modified]

    # Research track rotation
    tracks = [
        ("ML & Feature Engineering", "Improve crash model features, retrain, improve AUC-ROC"),
        ("Statistical Engine & Monte Carlo", "Regime-switching MC, copulas, stochastic vol, backtesting"),
        ("Test Suite & Code Quality", "Write tests for uncovered services, fix smells, 200+ test target"),
        ("New Features & Capabilities", "CVaR, factor exposure, drawdown signals, new endpoints"),
        ("Frontend & Visualization", "Fix TS errors, loading states, charts, SHAP visualizations"),
        ("Service Integration & Wiring", "Find dead code, wire disconnected services, verify E2E"),
        ("Performance & Reliability", "Caching, retries, timeouts, structured logging"),
    ]
    primary = tracks[(cycle - 1) % len(tracks)]
    secondary = tracks[cycle % len(tracks)]

    return f"""# Aegis Finance R&D Lab — Cycle {cycle}, Phase A: EXPLORE

You are a senior quant engineer and the DE FACTO OWNER of this codebase.
You have FULL autonomy. You can:
- Modify ANY file in backend/, frontend/, engine/
- Install new packages (pip install, npm install)
- Clone reference repos or download datasets
- Access any public API (yfinance, FRED, etc.)
- Create new services, endpoints, tests, components
- Restructure code, refactor architectures
- If an API key is needed and you think it's vital, note it in the report

This is YOUR sandbox. Build what the project needs.

## Research Track

**Primary: {primary[0]}** — {primary[1]}
**Secondary: {secondary[0]}** — {secondary[1]}

## Engine Output (from real backend services)

{data_block}

## Past Cycles
{past_block}

## Files never modified (explore these!)
{chr(10).join('- ' + f for f in untouched[:15])}

## Pre-existing test failures
```
{baseline_failures or "None"}
```

## Phase A Instructions

This is Phase 1 of 4. Right now: EXPLORE ONLY.
1. Read 8+ source files across backend/services/, routers/, engine/
2. Run tests: python -m pytest backend/tests/ -v -m "not slow" --tb=short
3. Look at the engine output data above — what's broken or suboptimal?
4. Check at least 3 files from the "never modified" list
5. Report your top 3 findings with file paths and line numbers

Don't implement yet — explore thoroughly. The deeper you go now, the better Phase B will be.
"""


PHASE_B_PROMPT = """Good exploration. Now BUILD.

Pick your HIGHEST-IMPACT finding and implement it fully.

You have full autonomy:
- Install packages if needed (pip install X)
- Create new files, services, endpoints
- Modify 3+ files minimum
- Target 50-200 lines of meaningful changes
- If you need external data or libraries, get them

After implementing, run:
  python -m pytest backend/tests/ -v -m "not slow" --tb=short

What are you implementing and why?
"""

PHASE_C_PROMPT = """Now harden what you built.

1. Write NEW tests for every change (2-3 test cases per function minimum)
2. Test edge cases: empty data, extreme values, None inputs
3. Run full fast suite: python -m pytest backend/tests/ -v -m "not slow" --tb=short
4. Fix any failures your changes caused
5. Narrow broad except blocks, remove fillna(0), move hardcoded values to config.py

Show me the tests and pytest output.
"""


def get_phase_d_prompt(cycle_id: str, cycle: int) -> str:
    return f"""Final phase. Self-critique and documentation.

1. Re-read every file you modified — is this actually better?
2. Fix anything you find
3. Final test: python -m pytest backend/tests/ -v -m "not slow" --tb=short

4. Write experiment report (REQUIRED):
   Create: lab/experiments/{cycle_id}/experiment_report.json

   {{
     "cycle": {cycle},
     "timestamp": "{datetime.now().isoformat()}",
     "research_track": "<track>",
     "what_i_noticed": "<findings from exploration>",
     "hypothesis": "<what you improved>",
     "what_i_did": "<detailed changes>",
     "files_modified": ["<every file>"],
     "files_created": ["<new files>"],
     "tests_added": ["<test names>"],
     "lines_changed_approx": 0,
     "results": {{
       "before": {{}},
       "after": {{}},
       "improved": true
     }},
     "analysis": "<honest assessment>",
     "what_i_would_do_differently": "<self-critique>",
     "next_steps": "<for next cycle>",
     "confidence": "low/medium/high",
     "depth_rating": "TRIVIAL/LIGHT/MEDIUM/DEEP"
   }}

5. Commit: git add -A && git commit -m "Lab {cycle_id}: <summary>"

Be brutally honest. Failed experiments logged honestly > fake successes.
"""


# ---------------------------------------------------------------------------
# Core: run one phase via subprocess
# ---------------------------------------------------------------------------

def run_phase(prompt: str, session_id: str, model: str,
              phase_name: str, cycle_dir: Path, is_first: bool) -> bool:
    """Run one conversation phase. Returns True if successful."""

    start = time.time()

    # First phase: --session-id to create session
    # Subsequent phases: --resume to continue same conversation
    if is_first:
        cmd = [CLAUDE_CMD, "--model", model, "--session-id", session_id,
               "--dangerously-skip-permissions"]
    else:
        cmd = [CLAUDE_CMD, "--model", model, "--resume", session_id,
               "--dangerously-skip-permissions"]

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=PHASE_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )

        output = result.stdout or ""
        stderr = result.stderr or ""

        # Detect rate limit
        if "hit your limit" in output.lower() or "hit your limit" in stderr.lower():
            print(f"    {phase_name}: RATE LIMITED — waiting 10 min")
            (cycle_dir / f"{phase_name}.txt").write_text(
                "[RATE LIMITED]", encoding="utf-8")
            time.sleep(600)  # Wait 10 min before continuing
            return False

        # Save output
        output_path = cycle_dir / f"{phase_name}.txt"
        output_path.write_text(output + "\n---STDERR---\n" + stderr, encoding="utf-8")

        elapsed = int(time.time() - start)
        lines = len(output.strip().split("\n")) if output.strip() else 0
        print(f"    {phase_name}: {lines} lines, {len(output)} chars, {elapsed}s")

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print(f"    {phase_name}: TIMEOUT after {PHASE_TIMEOUT}s")
        (cycle_dir / f"{phase_name}.txt").write_text(
            f"[TIMEOUT after {PHASE_TIMEOUT}s]", encoding="utf-8")
        return False

    except Exception as e:
        print(f"    {phase_name}: ERROR {e}")
        (cycle_dir / f"{phase_name}.txt").write_text(
            f"[ERROR: {e}]", encoding="utf-8")
        return False


# ---------------------------------------------------------------------------
# Run one cycle
# ---------------------------------------------------------------------------

def run_cycle(cycle: int, model: str, baseline_failures: str):
    cycle_id = f"cycle_{cycle:03d}"
    cycle_dir = EXPERIMENTS_DIR / cycle_id
    cycle_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    cycle_start = time.time()

    print(f"\n{'='*60}")
    print(f"  CYCLE {cycle} — {datetime.now().strftime('%H:%M:%S')} — session {session_id[:8]}")
    print(f"{'='*60}")

    # Data generation
    print("\n  [0/4] Generating engine data...")
    subprocess.run(
        [sys.executable, str(LAB_DIR / "data_generator.py"),
         "--output-dir", str(cycle_dir / "data"), "--cycle", str(cycle)],
        cwd=str(REPO_DIR), timeout=300,
    )

    # Phase A: Explore
    print("\n  [1/4] Phase A: EXPLORE")
    prompt_a = build_phase_a_prompt(cycle, cycle_dir, baseline_failures)
    (cycle_dir / "prompt_a.md").write_text(prompt_a, encoding="utf-8")
    phase_a_ok = run_phase(prompt_a, session_id, model, "phase_a_explore", cycle_dir, is_first=True)

    if not phase_a_ok:
        # Check if rate limited — skip remaining phases
        phase_a_out = (cycle_dir / "phase_a_explore.txt").read_text(encoding="utf-8", errors="replace")
        if "RATE LIMITED" in phase_a_out:
            print("  [SKIP] Rate limited — skipping remaining phases")
            return

    # Phase B: Build
    print("\n  [2/4] Phase B: BUILD")
    run_phase(PHASE_B_PROMPT, session_id, model, "phase_b_build", cycle_dir, is_first=False)

    # Phase C: Test
    print("\n  [3/4] Phase C: TEST")
    run_phase(PHASE_C_PROMPT, session_id, model, "phase_c_test", cycle_dir, is_first=False)

    # Phase D: Review
    print("\n  [4/4] Phase D: REVIEW")
    run_phase(get_phase_d_prompt(cycle_id, cycle), session_id, model,
              "phase_d_report", cycle_dir, is_first=False)

    # External validation
    print("\n  [POST] Validating...")
    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "-v",
         "-m", "not slow", "--tb=line"],
        cwd=str(REPO_DIR), capture_output=True, text=True, timeout=600,
    )
    test_out = test_result.stdout + test_result.stderr
    (cycle_dir / "test_results.txt").write_text(test_out, encoding="utf-8")

    passed_m = re.search(r"(\d+) passed", test_out)
    tests_passed = int(passed_m.group(1)) if passed_m else 0
    failed_lines = [l for l in test_out.split("\n") if l.startswith("FAILED")]
    baseline_set = set(baseline_failures.strip().split("\n")) if baseline_failures.strip() else set()
    new_failures = [l for l in failed_lines if l.strip() not in baseline_set]

    if new_failures:
        print(f"  [REVERT] {len(new_failures)} NEW failures!")
        for nf in new_failures[:5]:
            print(f"    {nf}")
        subprocess.run(["git", "checkout", "--", "backend/", "frontend/", "engine/"],
                       cwd=str(REPO_DIR))
    else:
        print(f"  [OK] {tests_passed} passed, 0 new failures")

    # Post-cycle comparison
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

    # Commit
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
            print(f"  Track: {r.get('research_track', '?')}")
            print(f"  Depth: {r.get('depth_rating', '?')}")
            print(f"  Result: {'OK' if r.get('results', {}).get('improved') else 'NO CHANGE'}")
            print(f"  Files: {len(r.get('files_modified', []))} modified")
            print(f"  Tests added: {len(r.get('tests_added', []))}")
        except:
            pass
    else:
        print("  [MISS] No experiment report")

    comp_path = cycle_dir / "comparison.json"
    if comp_path.exists():
        try:
            c = json.loads(comp_path.read_text(encoding="utf-8"))
            print(f"  Net: {c.get('net_result', '?')} "
                  f"({c.get('improvement_count', 0)} improvements)")
        except:
            pass

    # Phase output sizes
    for pf in ["phase_a_explore", "phase_b_build", "phase_c_test", "phase_d_report"]:
        fp = cycle_dir / f"{pf}.txt"
        if fp.exists():
            sz = fp.stat().st_size
            print(f"  {pf}: {sz:,} bytes")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Aegis Finance R&D Loop v5")
    parser.add_argument("--cycles", type=int, default=20)
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
    print("[BASELINE] Running tests...")
    bl = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "-v",
         "-m", "not slow", "--tb=line"],
        cwd=str(REPO_DIR), capture_output=True, text=True, timeout=600,
    )
    baseline_failures = "\n".join(
        l for l in bl.stdout.split("\n") if l.startswith("FAILED")
    )
    bl_count = len(baseline_failures.strip().split("\n")) if baseline_failures.strip() else 0
    print(f"  {bl_count} pre-existing failures")

    # Auto-detect start
    if args.start_cycle:
        start = args.start_cycle
    else:
        existing = sorted(EXPERIMENTS_DIR.glob("cycle_*"))
        start = len(existing) + 1

    print(f"\n{'='*60}")
    print(f"  AEGIS R&D LAB v5")
    print(f"  Model: {args.model} | Cycles: {start}-{args.cycles}")
    print(f"  Branch: {args.branch}")
    print(f"  Architecture: 4-phase multi-turn conversation")
    print(f"  Autonomy: FULL (pip install, git clone, API access)")
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
