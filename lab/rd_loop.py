"""
Aegis Finance - Autonomous R&D Loop v10
=========================================
Sandbox methodology — each cycle has full freedom to audit, research,
build, fix, and integrate. No micro-managed phases.

Three cycle types rotate to prevent tunnel vision:
  - DEEP_AUDIT: Read code, find bugs, fix them, write regression tests
  - BUILD: Research competitors, install packages, build new features
  - INTEGRATE: Wire existing services together, update frontend, close gaps

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

# Cycle type rotation — prevents the lab from always doing the same thing
CYCLE_TYPES = ["DEEP_AUDIT", "BUILD", "INTEGRATE"]


def _get_cycle_type(cycle: int) -> str:
    """Rotate cycle types: audit → build → integrate → audit → ..."""
    return CYCLE_TYPES[cycle % 3]


# ---------------------------------------------------------------------------
# Build the prompt — sandbox mentality, full freedom
# ---------------------------------------------------------------------------

def build_prompt(cycle: int, cycle_dir: Path, baseline_failures: str) -> str:

    cycle_type = _get_cycle_type(cycle)

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

    # Last 5 cycle summaries
    learnings = []
    for prev in range(max(1, cycle - 5), cycle):
        rp = EXPERIMENTS_DIR / f"cycle_{prev:03d}" / "experiment_report.json"
        if rp.exists():
            try:
                r = json.loads(rp.read_text(encoding="utf-8"))
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

    # Type-specific instructions
    if cycle_type == "DEEP_AUDIT":
        type_instructions = """
## This is a DEEP AUDIT cycle

Your primary goal: find and fix bugs. Read code carefully before writing any.

1. Pick 3-5 service files and READ THEM LINE BY LINE
2. For each bug you find, write a regression test FIRST, then fix the bug
3. Look for: wrong math, off-by-one errors, NaN handling, stale code,
   inconsistencies between config values and actual usage, broad except blocks
4. Run the full fast test suite at the end: `python -m pytest backend/tests/ -v -m "not slow" --tb=line -q`
5. Fix any failures you caused

Quality bar: Find at least 3 real bugs (not style issues). Each fix should
have a test that would have caught it.
"""
    elif cycle_type == "BUILD":
        type_instructions = """
## This is a BUILD cycle

Your primary goal: add a substantial new capability. Think like a quant at a hedge fund.

1. Search the web for what Bloomberg, OpenBB, Koyfin, or QuantConnect offer
   that Aegis doesn't. Pick the highest-impact gap.
2. `pip install` any packages that would help (riskfolio-lib, ta, arch, etc.)
3. Build the feature properly — full service file, config entries, API endpoint,
   tests, and frontend API client function.
4. Wire it into existing endpoints where it makes sense (don't just create
   isolated endpoints nobody calls).

Quality bar: The feature should be something a user would actually notice.
Not internal plumbing — visible analytics that show up in API responses.

Competitive targets (what we're missing that they have):
- Bloomberg PORT: risk budgeting, tracking error analysis, fixed income analytics
- Koyfin: 500+ screening metrics, custom screening filters, relative valuation tools
- TradingView: chart pattern recognition (head/shoulders, triangles, flags), alerts system
- OpenBB: broad data source coverage (we have ~10 sources, they have 100+), crypto/forex
- QuantConnect: walk-forward strategy backtesting with transaction costs
- Morningstar: style box analysis, fund overlap detection, income projections

ALREADY DONE (don't rebuild): technical analysis (ta lib), risk number (1-100),
sector rotation, drawdown recovery, rolling Sharpe/Sortino, retirement MC,
safe withdrawal rate, Polygon.io real-time data, copula tail risk, factor models
"""
    else:  # INTEGRATE
        type_instructions = """
## This is an INTEGRATE cycle

Your primary goal: wire existing services into the main user-facing endpoints.
A service that exists but doesn't show up in API responses is wasted code.

Check these integration points:
1. Stock analysis (`/api/stock/{ticker}`) — does it show: factor exposure,
   liquidity score, insider signal, momentum rank, TA signal, trend attention?
2. Portfolio analysis (`/api/portfolio/analyze`) — does it include: attribution,
   MCTR, copula VaR, factor exposures, risk number (1-100)?
3. Market status (`/api/market-status`) — does it include: trends sentiment,
   VIX term structure state, changepoint detection, sector rotation?
4. Screener (`/api/stock/screener`) — do the stock signals use all 12 components?
   Does it include TA signal per stock?
5. Frontend (`frontend/src/lib/api.ts`) — are ALL backend endpoints callable?
6. Sector rotation (`/api/analytics/sector-rotation`) — is it wired into
   market status or sectors page?
7. Real-time data (`/api/realtime/{ticker}`) — is Polygon used for fresher
   prices in stock analysis when available?

Also:
- Build/improve frontend components that display new analytics
- Add caching to slow endpoints
- Wire new data into the signal engine (every new signal source should
  eventually feed the composite score)

Quality bar: At least 2 services that were standalone-only are now
integrated into a user-facing endpoint.
"""

    return f"""# Aegis Finance — R&D Cycle {cycle} ({cycle_type})

This project is YOUR SANDBOX. You have complete freedom. You are a senior quant
and fintech expert building an engine to compete with Bloomberg — but more
user-friendly and open-source.

{type_instructions}

## Your powers — USE THEM (the lab has historically underused these)

- **Install packages**: `pip install X` — do this! Past 54 cycles installed 0 packages.
  Useful: `ta` (technical analysis), `arch` (GARCH), `ruptures` (changepoint),
  `plotly` (charts), `pytrends` (Google Trends), `fredapi`, etc.
- **Web search**: Search for state-of-the-art approaches, competitor features,
  recent papers, new free data APIs. The lab has never done web research.
- **Download and study code**: Look at OpenBB, riskfolio-lib, skfolio source code
  for implementation patterns.
- **Access APIs**: yfinance, FRED, Finnhub, SEC EDGAR, Treasury.gov, BLS, GDELT
- **Modify ANY file**: backend/, frontend/, engine/, lab/, config, requirements.txt
- **Create new services**: Build entire new .py files with tests and endpoints

## Current engine (53 services, 45+ endpoints, 1350+ tests)

Backend services: monte_carlo, stock_analyzer, sector_analyzer, portfolio_engine,
crash_model, signal_engine (12 components), regime_detector, risk_scorer, shap_explainer,
news_intelligence, llm_analyzer (Claude+DeepSeek), sentiment_analyzer, data_fetcher,
data_quality, net_liquidity, return_model, external_validator, regime_validator,
drift_detector, tail_risk, tail_dependence, backtest, signal_optimizer,
options_intelligence, earnings_intelligence, systemic_risk, bubble_detector,
fundamentals, options_calibrator, prediction_confidence, signal_analytics,
factor_model (FF6+PCA), stress_testing (+hypothetical), cross_sectional_momentum,
economic_surprise, survival_model, anomaly_detector, crash_timeline,
liquidity_risk, copula_tail, covariance (RMT), portfolio_optimizer (CVaR/RP/MaxDiv/HRP),
insider_trading, trends_sentiment, attribution (Brinson+MCTR), conformal_predictor,
**technical_analysis** (RSI/MACD/BB/ADX/OBV via `ta` lib),
**polygon_client** (real-time quotes, intraday bars),
**risk_number** (Bloomberg PORT-style 1-100 risk score),
**sector_rotation** (multi-timeframe relative strength + business cycle),
**drawdown_analyzer** (drawdown recovery analysis + rolling returns/Sharpe),
**retirement_mc** (Monte Carlo retirement sim + safe withdrawal rate)

API keys available: FRED, Finnhub, FMP, DeepSeek, Alpha Vantage, Polygon.io, ANTHROPIC
Installed packages: ta, polygon-api-client, riskfolio-lib, copulas, ruptures, pytrends

Signal engine components: crash_prob, regime, valuation, momentum, mean_reversion,
external, macro_risk, drawdown, economic_surprise, momentum_breadth, insider_trading,
vix_term_structure

## Engine data snapshot

{data_block}

## Recent cycles (don't repeat)

{past_block}

## When done

1. Write experiment report to: lab/experiments/cycle_{cycle:03d}/experiment_report.json
   {{
     "cycle": {cycle},
     "cycle_type": "{cycle_type}",
     "timestamp": "<ISO timestamp>",
     "title": "<one-line summary of what you did>",
     "category": "<quantitative|data|frontend|reliability|integration>",
     "observation": {{
       "bugs_found": ["<list of bugs found>"],
       "gap_identified": "<the main gap you addressed>"
     }},
     "implementation": {{
       "bugs_fixed": ["<description of each fix>"],
       "feature_built": "<what you added>",
       "files_changed": ["<list>"],
       "files_created": ["<list>"],
       "packages_installed": ["<list of pip packages installed>"]
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

You own this. Make it better. Don't hold back.
"""


# ---------------------------------------------------------------------------
# Run one cycle
# ---------------------------------------------------------------------------

def run_cycle(cycle: int, model: str, baseline_failures: str):
    cycle_id = f"cycle_{cycle:03d}"
    cycle_dir = EXPERIMENTS_DIR / cycle_id
    cycle_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    cycle_start = time.time()
    cycle_type = _get_cycle_type(cycle)

    print(f"\n{'='*60}")
    print(f"  CYCLE {cycle} ({cycle_type}) - {datetime.now().strftime('%H:%M:%S')}")
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

    # Single deep session
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

    # Targeted validation
    print("\n  Validating (targeted)...")
    try:
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(REPO_DIR), capture_output=True, text=True, timeout=10,
        )
        changed_files = diff_result.stdout.strip().split("\n") if diff_result.stdout.strip() else []

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

        # Always include core smoke tests
        for core in ["test_monte_carlo.py", "test_signal_engine.py", "test_crash_calibration.py"]:
            core_path = REPO_DIR / "backend" / "tests" / core
            if core_path.exists():
                test_files_to_run.add(str(core_path))

        if test_files_to_run:
            test_cmd = [sys.executable, "-m", "pytest"] + list(test_files_to_run) + [
                "-v", "--tb=line", "-x"
            ]
            test_result = subprocess.run(
                test_cmd, cwd=str(REPO_DIR),
                capture_output=True, text=True, timeout=300,
            )
            test_out = test_result.stdout + test_result.stderr
        else:
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
    print(f"\n  Cycle {cycle} ({cycle_type}) done in {duration} min")

    report_path = cycle_dir / "experiment_report.json"
    if report_path.exists():
        try:
            r = json.loads(report_path.read_text(encoding="utf-8"))
            title = r.get("title") or r.get("what_i_did", "?")
            print(f"  What: {title[:120]}")
            depth = r.get("depth_rating") or r.get("assessment", {}).get("depth", "?")
            print(f"  Depth: {depth}")
            verdict = r.get("assessment", {}).get("verdict")
            if verdict:
                print(f"  Result: {verdict}")
            else:
                improved = r.get("results", {}).get("improved")
                print(f"  Result: {'improved' if improved else 'neutral'}")
            files_changed = r.get("files_modified") or r.get("implementation", {}).get("files_changed", [])
            files_created = r.get("files_created") or r.get("implementation", {}).get("files_created", [])
            pkgs = r.get("implementation", {}).get("packages_installed", [])
            print(f"  Files: {len(files_changed)} changed, {len(files_created)} created")
            if pkgs:
                print(f"  Packages: {', '.join(pkgs)}")
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
    parser = argparse.ArgumentParser(description="Aegis Finance R&D Loop v10")
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
    print(f"  AEGIS R&D LAB v10 - Sandbox Mode")
    print(f"  Model: {args.model} | Cycles: {start}-{args.cycles}")
    print(f"  Session: {SESSION_TIMEOUT // 60} min | Branch: {args.branch}")
    print(f"  Rotation: DEEP_AUDIT -> BUILD -> INTEGRATE")
    print(f"  Next cycle type: {_get_cycle_type(start)}")
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
    print(f"  DONE - cycles {start}-{args.cycles}")
    print(f"  git log --oneline {args.branch} -{args.cycles}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
