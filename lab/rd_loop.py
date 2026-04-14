"""
Aegis Finance - Autonomous R&D Loop v8
Audit → Research → Fix → Build → Test methodology per cycle.

Each cycle follows the pattern that produced the best results:
1. Read and audit code for bugs / quality issues
2. Research competitors and state-of-the-art approaches
3. Fix bugs found in audit
4. Add new features / improvements
5. Write tests and run full regression suite

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

SESSION_TIMEOUT = 2700  # 45 min max per session

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

    # Last 5 cycle summaries (brief — don't anchor Claude to old approaches)
    learnings = []
    for prev in range(max(1, cycle - 5), cycle):
        rp = EXPERIMENTS_DIR / f"cycle_{prev:03d}" / "experiment_report.json"
        if rp.exists():
            try:
                r = json.loads(rp.read_text(encoding="utf-8"))
                # Handle both old format (what_i_did, results.improved) and
                # new format (title, assessment.verdict)
                title = (
                    r.get("title")
                    or r.get("what_i_did")
                    or r.get("observation", {}).get("gap_identified")
                    or "?"
                )[:120]
                verdict = (
                    r.get("assessment", {}).get("verdict")
                    or ("improved" if r.get("results", {}).get("improved") else "neutral")
                )
                learnings.append(f"Cycle {prev}: {title} ({verdict})")
            except Exception:
                pass
    past_block = "\n".join(learnings) if learnings else "No recent history."

    # Untouched files
    modified = set()
    for prev in range(1, cycle):
        rp = EXPERIMENTS_DIR / f"cycle_{prev:03d}" / "experiment_report.json"
        if rp.exists():
            try:
                r = json.loads(rp.read_text(encoding="utf-8"))
                # Support both formats
                files = (
                    r.get("files_modified", [])
                    or r.get("implementation", {}).get("files_changed", [])
                )
                modified.update(files)
            except Exception:
                pass

    all_files = [
        # Core services
        "backend/services/monte_carlo.py", "backend/services/stock_analyzer.py",
        "backend/services/sector_analyzer.py", "backend/services/portfolio_engine.py",
        "backend/services/crash_model.py", "backend/services/signal_engine.py",
        "backend/services/regime_detector.py", "backend/services/risk_scorer.py",
        "backend/services/shap_explainer.py", "backend/services/news_intelligence.py",
        "backend/services/sentiment_analyzer.py", "backend/services/data_quality.py",
        "backend/services/net_liquidity.py", "backend/services/return_model.py",
        "backend/services/external_validator.py", "backend/services/regime_validator.py",
        "backend/services/drift_detector.py", "backend/services/llm_analyzer.py",
        "backend/services/options_intelligence.py", "backend/services/earnings_intelligence.py",
        "backend/services/tail_risk.py", "backend/services/tail_dependence.py",
        "backend/services/backtest.py", "backend/services/systemic_risk.py",
        "backend/services/bubble_detector.py", "backend/services/fundamentals.py",
        "backend/services/options_calibrator.py", "backend/services/prediction_confidence.py",
        "backend/services/signal_analytics.py",
        # v8 services
        "backend/services/factor_model.py", "backend/services/stress_testing.py",
        "backend/services/cross_sectional_momentum.py", "backend/services/economic_surprise.py",
        "backend/services/survival_model.py", "backend/services/anomaly_detector.py",
        "backend/services/crash_timeline.py",
        # v9 services (institutional-grade)
        "backend/services/liquidity_risk.py", "backend/services/copula_tail.py",
        "backend/services/covariance.py", "backend/services/portfolio_optimizer.py",
        "backend/services/insider_trading.py", "backend/services/trends_sentiment.py",
        "backend/services/attribution.py",
        # Routers
        "backend/routers/market.py", "backend/routers/stock.py",
        "backend/routers/crash.py", "backend/routers/simulation.py",
        "backend/routers/portfolio.py", "backend/routers/sector.py",
        "backend/routers/analytics.py",
        # Config
        "backend/config.py",
        # Engine
        "engine/training/features.py", "engine/training/train_crash_model.py",
        "engine/validation/walk_forward.py", "engine/validation/metrics.py",
        # Frontend
        "frontend/src/app/", "frontend/src/components/", "frontend/src/lib/",
    ]
    untouched = [f for f in all_files if f not in modified]

    return f"""# Aegis Finance — R&D Cycle {cycle}

You OWN this codebase. This is your sandbox. Improve the engine.

## Methodology — follow this workflow (it produces the best results)

### Phase 1: AUDIT (15 min)
Read service files thoroughly. Look for:
- Bugs (wrong calculations, off-by-one, type errors, logic flaws)
- Stale code (unused variables, dead branches)
- Missing edge case handling
- Inconsistencies between config values and actual usage
- Performance bottlenecks (redundant computations, missing caching)

### Phase 2: RESEARCH (5 min)
Search the web for state-of-the-art approaches relevant to what you found.
Look at OpenBB, Riskfolio-Lib, skfolio, QuantLib, recent papers.
`pip install` any useful packages you find.

### Phase 3: FIX (10 min)
Fix every bug you found in Phase 1. Each fix should be surgical — don't
refactor surrounding code unless the bug requires it.

### Phase 4: BUILD (10 min)
Add ONE substantial new feature or improvement. Pick from the priority list
below, or from what your audit/research revealed. Quality over quantity.

### Phase 5: TEST (5 min)
- Write tests for your bug fixes (regression tests)
- Write tests for your new feature
- Run ONLY the affected test files: `python -m pytest backend/tests/test_<service>.py -v --tb=short`
- Run 3 core smoke tests: `python -m pytest backend/tests/test_monte_carlo.py backend/tests/test_signal_engine.py backend/tests/test_crash_calibration.py -v --tb=short`

## Your powers — use them

- Modify ANY file: backend/, frontend/, engine/, AND lab/
- Install packages: `pip install X`, `npm install X`
- Web search for state-of-the-art approaches and libraries
- Access APIs: yfinance, FRED, Finnhub, GDELT, SEC EDGAR, any public finance API
- Download reference implementations for study

## Priority areas (don't repeat what past cycles did)

### Already built and integrated (v9) — now improve quality
- Signal engine now includes: economic surprise + momentum breadth signals (v9.1)
- Stock analysis now shows: insider signal, liquidity score, momentum rank (v9.1)
- Portfolio engine now uses denoised covariance (RMT) by default (v9.1)
- Frontend API client has 20+ new endpoint functions (v9.1)

### Still needs deeper integration
- Copula tail dependence: integrate copula VaR into portfolio analysis response
- Liquidity risk: add liquidity-adjusted position sizing in portfolio optimizer
- Insider trading: integrate as additional stock signal factor (additive weight)
- Google Trends: integrate fear/greed into macro risk dashboard endpoint
- Factor model (FF6): show factor exposures on stock analysis page
- Attribution: wire into portfolio analyze endpoint (auto-compute vs SPY)

### Quantitative (highest remaining impact)
- Conformal prediction intervals for crash probabilities
- Regime-switching GARCH or MSVAR (statsmodels.tsa.regime_switching)
- Volatility surface interpolation for options intelligence
- Augmented Black-Litterman with entropy pooling (riskfolio has augmented_black_litterman)
- Walk-forward signal optimization (temporal parameter tuning)
- Factor-tilted portfolio construction (overweight quality/value factors)
- Turnover-constrained optimization (max rebalancing cost)
- Cross-sectional momentum → signal engine integration
- Economic surprise → signal engine integration
- Multi-period optimization (dynamic programming approach)

### Data & integration
- SEC EDGAR quarterly financials pipeline improvements (edgartools)
- VIX term structure → regime detection integration
- Short interest data aggregation (Finnhub short interest endpoint)
- Alpha Vantage integration for technical indicators (free tier)
- Congressional trading data (Capitol Trades / Quiver Quant)
- BLS employment data integration (payrolls, claims detail)
- Treasury auction data (bid-to-cover ratios, indirect bidding)
- Sector rotation signals (relative strength + breadth + RSI)

### Frontend / UX (high user impact)
- Liquidity risk display on stock pages
- Copula tail dependence heatmap
- Portfolio optimizer comparison table (Bloomberg PORT style)
- Factor decomposition visualization (bar chart + style box)
- Insider trading timeline display
- Stress test scenario comparison waterfall chart
- Economic surprise dashboard
- Momentum heatmap (sector × stock grid)
- Covariance diagnostics display (eigenvalue spectrum)
- Export functionality (CSV/PDF reports)
- Mobile responsive improvements

### Reliability & performance
- Options calibrator edge cases (no options data, illiquid chains)
- Screener performance with expanded 80+ ticker universe
- Cache warming strategy for new v9 endpoints
- Rate limiting for external API calls
- Parallel data fetching for liquidity/copula analysis
- Error recovery in portfolio optimizer (fallback to simpler method)

### Competitive gaps to close (vs OpenBB, Koyfin, TradingView)
- Alerts/notifications system (threshold-based email or webhook)
- Custom watchlist management (frontend)
- Chart pattern recognition (TA library is installed: `import ta`)
- Multi-asset coverage (ETFs, crypto, commodities via yfinance)
- Backtesting portfolio optimizer decisions (did CVaR outperform?)

## Current engine state

{data_block}

## Recent cycles (don't repeat these)

{past_block}

## Unexplored areas

{chr(10).join('- ' + f for f in untouched[:20])}

## When done

1. Experiment report: lab/experiments/cycle_{cycle:03d}/experiment_report.json
   {{
     "cycle": {cycle},
     "timestamp": "<ISO timestamp>",
     "title": "<one-line summary>",
     "category": "<quantitative|data|frontend|reliability>",
     "observation": {{
       "bugs_found": ["<list of bugs found in audit>"],
       "gap_identified": "<the gap you're fixing>"
     }},
     "implementation": {{
       "bugs_fixed": ["<list of bug descriptions>"],
       "feature_built": "<what you added>",
       "files_changed": ["<list>"],
       "files_created": ["<list>"],
       "packages_installed": ["<list>"]
     }},
     "validation": {{
       "tests_written": 0,
       "tests_passing": 0,
       "regressions": 0
     }},
     "assessment": {{
       "verdict": "improved|neutral|regressed",
       "confidence": "low|medium|high",
       "depth": 1-5,
       "limitations": ["<honest list>"],
       "self_critique": "<what you'd do differently>"
     }},
     "next_steps": ["<actionable items for next cycle>"]
   }}

2. Commit: `git add -A && git commit -m "Lab cycle_{cycle:03d}: <summary>"`

Think like a quant researcher who reads code carefully before writing it.
Audit first, then fix, then build. Quality over quantity.
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
             "--dangerously-skip-permissions", "--max-turns", "200"],
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
            # Support both old format (what_i_did) and new format (title)
            title = r.get("title") or r.get("what_i_did", "?")
            print(f"  What: {title[:120]}")
            # Support both old (depth_rating) and new (assessment.depth)
            depth = r.get("depth_rating") or r.get("assessment", {}).get("depth", "?")
            print(f"  Depth: {depth}")
            # Support both old (results.improved) and new (assessment.verdict)
            verdict = r.get("assessment", {}).get("verdict")
            if verdict:
                print(f"  Result: {verdict}")
            else:
                improved = r.get("results", {}).get("improved")
                print(f"  Result: {'improved' if improved else 'neutral'}")
            # Support both old (files_modified) and new (implementation.files_changed)
            files_changed = r.get("files_modified") or r.get("implementation", {}).get("files_changed", [])
            files_created = r.get("files_created") or r.get("implementation", {}).get("files_created", [])
            print(f"  Files: {len(files_changed)} changed, {len(files_created)} created")
        except Exception:
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
    parser = argparse.ArgumentParser(description="Aegis Finance R&D Loop v8")
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
    print(f"  AEGIS R&D LAB v8 — Audit→Research→Fix→Build→Test")
    print(f"  Model: {args.model} | Cycles: {start}-{args.cycles}")
    print(f"  Session: {SESSION_TIMEOUT // 60} min | Branch: {args.branch}")
    print(f"  Methodology: read code, find bugs, fix, then build")
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
