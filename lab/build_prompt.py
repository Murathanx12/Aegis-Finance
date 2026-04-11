"""
Aegis Finance - Lab Prompt Builder v3
Gives Claude ambitious, rotating research tracks with deep exploration mandates.
No more "find a small drift bug" loops — pushes for new features, tests,
model retraining, frontend work, and architectural improvements.
"""

import argparse
import json
import os
import glob
import hashlib
from pathlib import Path
from datetime import datetime


def load_json_safe(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


# ---------------------------------------------------------------------------
# Research tracks — rotated each cycle to force breadth
# ---------------------------------------------------------------------------
RESEARCH_TRACKS = [
    {
        "id": "ml_improvement",
        "name": "ML Model & Feature Engineering",
        "description": """Deep dive into the crash prediction model and feature pipeline.
Consider:
- Add new features to engine/training/features.py (macro indicators, sentiment, cross-asset)
- Improve feature selection (engine/training/feature_selection.py)
- Retrain the crash model with new features (engine/training/train_crash_model.py)
- Add conformal prediction intervals
- Improve walk-forward validation metrics (AUC-ROC target: >= 0.75)
- Add new ML models (XGBoost ensemble, neural net for comparison)
- Implement proper Brier score calibration and log it
- Add fractional differentiation to more features
- Improve sample uniqueness weighting""",
        "key_files": [
            "engine/training/features.py",
            "engine/training/feature_selection.py",
            "engine/training/train_crash_model.py",
            "backend/services/crash_model.py",
            "backend/services/return_model.py",
        ],
        "success_metrics": ["walk_forward_auc", "brier_score", "feature_count", "model_comparison"],
    },
    {
        "id": "statistical_engine",
        "name": "Statistical Engine & Monte Carlo",
        "description": """Push the MC simulation engine and GARCH modeling to the next level.
Consider:
- Implement regime-switching MC (MRS-MNTS-GARCH from the JRFM 2022 paper referenced in CLAUDE.md)
- Add stochastic volatility models beyond GJR-GARCH
- Implement proper jump-size estimation from historical crashes
- Add mean-reversion (OU process) for individual stock drift
- Improve the block bootstrap with circular block bootstrap
- Add proper backtesting: run MC from past dates, compare to actuals
- Implement copula-based multi-asset simulation for portfolio MC
- Add variance reduction: importance sampling, control variates
- Fix any remaining Ito correction inconsistencies""",
        "key_files": [
            "backend/services/monte_carlo.py",
            "backend/services/stock_analyzer.py",
            "backend/services/sector_analyzer.py",
            "backend/services/portfolio_engine.py",
            "backend/models/",
        ],
        "success_metrics": ["mc_backtest_accuracy", "variance_ratio", "garch_fit_quality"],
    },
    {
        "id": "testing_quality",
        "name": "Test Suite Expansion & Code Quality",
        "description": """The test suite has 152 tests but many services have zero coverage.
Consider:
- Write tests for EVERY service that lacks them (check backend/tests/)
- Add integration tests that call the actual API endpoints
- Add property-based tests with hypothesis for MC and portfolio
- Add regression tests for bugs found in past cycles
- Fix any code smells: broad except blocks, fillna(0), hardcoded values
- Add type checking with mypy on backend/services/
- Increase test count to 200+ with meaningful assertions
- Add tests for edge cases: empty data, single stock, extreme volatility
- Test crash model with synthetic data (known crash periods)""",
        "key_files": [
            "backend/tests/",
            "backend/services/",
            "backend/routers/",
        ],
        "success_metrics": ["test_count", "code_smells_fixed", "services_with_tests"],
    },
    {
        "id": "new_features",
        "name": "New Features & Capabilities",
        "description": """Add genuinely new capabilities to the platform.
Consider:
- Implement drawdown-based risk signals (current drawdown from ATH as signal component)
- Add correlation breakdown analysis (which assets are correlated in crashes vs normal?)
- Implement tail risk metrics: CVaR, Expected Shortfall for portfolios
- Add a volatility surface / term structure endpoint
- Implement pairs trading signal detection
- Add crypto asset support (BTC, ETH) with appropriate vol models
- Build a factor exposure analyzer (Fama-French 5-factor)
- Add options-implied volatility as a feature for crash prediction
- Implement dynamic portfolio rebalancing suggestions
- Add sector rotation signals based on business cycle""",
        "key_files": [
            "backend/services/",
            "backend/routers/",
            "backend/config.py",
            "frontend/src/",
        ],
        "success_metrics": ["new_endpoints", "new_services", "feature_completeness"],
    },
    {
        "id": "frontend_ux",
        "name": "Frontend & Visualization",
        "description": """The frontend has 12 pages but many may have stale data connections or UX issues.
Consider:
- Fix any TypeScript errors (run `cd frontend && npx tsc --noEmit`)
- Add loading states, error boundaries, and skeleton screens
- Improve chart visualizations (add confidence bands, regime overlays)
- Add interactive portfolio comparison (side-by-side profiles)
- Implement real-time data refresh with proper cache invalidation
- Add export functionality (PDF reports, CSV data)
- Fix responsive design issues
- Add keyboard shortcuts for power users
- Implement dark mode improvements
- Add SHAP waterfall charts for individual stock predictions""",
        "key_files": [
            "frontend/src/app/",
            "frontend/src/components/",
            "frontend/src/lib/",
            "frontend/src/hooks/",
        ],
        "success_metrics": ["ts_errors_fixed", "new_components", "build_success"],
    },
    {
        "id": "integration_wiring",
        "name": "Service Integration & Dead Code Elimination",
        "description": """Find services/features that exist but aren't connected end-to-end.
Consider:
- Trace every API endpoint: does it call real services or return mock data?
- Find backend services that exist but have no router endpoint
- Find frontend pages that call endpoints that don't exist or return stubs
- Wire up the drift detector (backend/services/drift_detector.py) — is it used?
- Wire up external_validator.py and regime_validator.py — do they feed into anything?
- Check if SHAP explanations actually appear on the frontend
- Verify news intelligence + FinBERT sentiment pipeline works end-to-end
- Check if portfolio projection uses the improved MC engine or a legacy path
- Remove dead code that will never be used""",
        "key_files": [
            "backend/routers/",
            "backend/services/",
            "frontend/src/lib/api.ts",
            "frontend/src/hooks/",
        ],
        "success_metrics": ["dead_code_removed", "endpoints_wired", "e2e_paths_verified"],
    },
    {
        "id": "performance_reliability",
        "name": "Performance & Reliability",
        "description": """Make the engine faster, more reliable, and more robust.
Consider:
- Profile slow endpoints (stock analysis, portfolio projection) — add timing
- Optimize MC simulation: vectorize remaining loops, reduce allocations
- Add proper caching strategy: what should be cached, what shouldn't?
- Implement graceful degradation: if FRED is down, use cached macro data
- Add retry logic for flaky external API calls (yfinance, FRED)
- Implement request-level timeouts to prevent hanging
- Add health check endpoint that validates all services are working
- Optimize GARCH fitting (currently fits per-request — should it be cached?)
- Add memory profiling to find leaks in long-running processes
- Implement proper logging (structured JSON logs) instead of print statements""",
        "key_files": [
            "backend/services/",
            "backend/cache.py",
            "backend/main.py",
            "backend/routers/",
        ],
        "success_metrics": ["response_time_p95", "cache_hit_rate", "error_rate"],
    },
]


def get_research_track(cycle):
    """Rotate through research tracks. Each cycle gets a primary + secondary."""
    n = len(RESEARCH_TRACKS)
    primary_idx = (cycle - 1) % n
    secondary_idx = (cycle) % n

    primary = RESEARCH_TRACKS[primary_idx]
    secondary = RESEARCH_TRACKS[secondary_idx]

    return primary, secondary


def collect_past_learnings(experiments_dir, current_cycle, max_recent=5):
    """Only include last N cycles to keep context manageable."""
    learnings = []

    start_cycle = max(1, current_cycle - max_recent)
    for cycle_num in range(start_cycle, current_cycle):
        cycle_id = f"cycle_{cycle_num:03d}"
        cycle_dir = os.path.join(experiments_dir, cycle_id)

        report = load_json_safe(os.path.join(cycle_dir, "experiment_report.json"))
        comparison = load_json_safe(os.path.join(cycle_dir, "comparison.json"))

        if report:
            improved = report.get("results", {}).get("improved", False)
            entry = f"""### Cycle {cycle_num} ({'IMPROVED' if improved else 'NO CHANGE'})
Hypothesis: {report.get('hypothesis', 'Unknown')}
What I did: {report.get('what_i_did', report.get('method', 'Unknown'))}
Files: {', '.join(report.get('files_modified', []))}
Next steps: {report.get('next_steps', 'None')}"""
            learnings.append(entry)

        elif comparison:
            net = comparison.get("net_result", "unknown")
            entry = f"""### Cycle {cycle_num} ({net})
(No detailed report — check comparison.json)"""
            learnings.append(entry)

    if not learnings:
        return "No past experiments available. This is a fresh start."

    return "\n\n".join(learnings)


def collect_cumulative_stats(experiments_dir, current_cycle):
    """Summarize what's been done across ALL cycles for high-level context."""
    all_files_modified = set()
    total_improved = 0
    total_neutral = 0
    total_regressed = 0
    track_history = []

    for cycle_num in range(1, current_cycle):
        cycle_id = f"cycle_{cycle_num:03d}"
        cycle_dir = os.path.join(experiments_dir, cycle_id)

        report = load_json_safe(os.path.join(cycle_dir, "experiment_report.json"))
        if report:
            for f in report.get("files_modified", []):
                all_files_modified.add(f)
            if report.get("results", {}).get("improved"):
                total_improved += 1
            else:
                total_neutral += 1
            track_history.append(report.get("hypothesis", "?")[:60])

        comparison = load_json_safe(os.path.join(cycle_dir, "comparison.json"))
        if comparison:
            net = comparison.get("net_result", "neutral")
            if net == "improved":
                total_improved += 1
            elif net == "regressed":
                total_regressed += 1

    # Files NEVER touched — these are underexplored
    all_services = [
        "backend/services/monte_carlo.py",
        "backend/services/stock_analyzer.py",
        "backend/services/sector_analyzer.py",
        "backend/services/portfolio_engine.py",
        "backend/services/crash_model.py",
        "backend/services/signal_engine.py",
        "backend/services/regime_detector.py",
        "backend/services/risk_scorer.py",
        "backend/services/shap_explainer.py",
        "backend/services/news_intelligence.py",
        "backend/services/sentiment_analyzer.py",
        "backend/services/data_quality.py",
        "backend/services/net_liquidity.py",
        "backend/services/return_model.py",
        "backend/services/external_validator.py",
        "backend/services/regime_validator.py",
        "backend/services/drift_detector.py",
        "backend/services/llm_analyzer.py",
        "backend/services/savings_calculator.py",
        "engine/training/features.py",
        "engine/training/feature_selection.py",
        "engine/training/train_crash_model.py",
        "engine/validation/walk_forward.py",
        "engine/validation/purged_cv.py",
        "engine/validation/metrics.py",
    ]

    untouched = [f for f in all_services if f not in all_files_modified]

    return {
        "total_cycles": current_cycle - 1,
        "improved": total_improved,
        "neutral": total_neutral,
        "regressed": total_regressed,
        "files_modified": sorted(all_files_modified),
        "files_never_touched": untouched,
        "track_history_summary": track_history[-10:],
    }


def load_baseline_failures(path):
    if not path or not os.path.exists(path):
        return "No baseline failure data available."
    try:
        with open(path, encoding="utf-8") as f:
            failures = f.read().strip()
        return failures or "All tests passing (no pre-existing failures)."
    except:
        return "Could not read baseline failures."


def build_prompt(cycle_dir, experiments_dir, cycle, output_path, baseline_failures_path=None):
    data_dir = os.path.join(cycle_dir, "data")

    # Load data files
    all_data = {}
    if os.path.isdir(data_dir):
        for f in glob.glob(os.path.join(data_dir, "*.json")):
            key = Path(f).stem
            all_data[key] = load_json_safe(f)

    data_sections = []
    for key, data in all_data.items():
        if data is None:
            continue
        data_str = json.dumps(data, indent=2)
        if len(data_str) > 5000:
            data_str = data_str[:5000] + "\n... [truncated]"
        data_sections.append(f"### {key}\n```json\n{data_str}\n```")

    data_block = "\n\n".join(data_sections) if data_sections else "No data available."

    # Get research tracks for this cycle
    primary_track, secondary_track = get_research_track(cycle)

    # Recent learnings (last 5 only)
    past_learnings = collect_past_learnings(experiments_dir, cycle, max_recent=5)

    # Cumulative stats
    cumulative = collect_cumulative_stats(experiments_dir, cycle)
    cumulative_str = json.dumps(cumulative, indent=2)

    baseline_failures = load_baseline_failures(baseline_failures_path)

    prompt = f"""# Aegis Finance - Autonomous R&D Lab - Cycle {cycle}
Time: {datetime.now().isoformat()}

---

## WHO YOU ARE

You are a senior quant engineer with FULL autonomy over the Aegis Finance codebase.
You have up to 45 minutes. USE THEM. Don't do a quick fix and stop.

You are expected to:
1. **Deeply explore** the codebase (read 10+ files, understand architecture)
2. **Design an ambitious experiment** (not a one-line fix — a real improvement)
3. **Implement it** across multiple files if needed
4. **Write new tests** for your changes
5. **Validate thoroughly** (run existing tests + your new ones)
6. **Measure the impact** with data
7. **Log everything** honestly in the experiment report

A cycle that touches 1 file and changes 5 lines is TOO SMALL.
A good cycle touches 3-8 files, adds 50-200 lines, and creates new capabilities.

---

## YOUR RESEARCH TRACK THIS CYCLE

### PRIMARY: {primary_track['name']}

{primary_track['description']}

Key files to explore:
{chr(10).join('- ' + f for f in primary_track['key_files'])}

### SECONDARY (if time remains): {secondary_track['name']}

{secondary_track['description']}

You may work on EITHER track, or combine elements from both.
You may also ignore both tracks if you find something more important.
The tracks are suggestions, not constraints.

---

## CRITICAL RULES

1. **ONLY modify files in `backend/`, `frontend/`, or `engine/`.**
   NEVER modify files in `lab/`.

2. **Do NOT break existing tests.**
   Run: `python -m pytest backend/tests/ -v -m "not slow" --tb=short`
   If your changes cause NEW test failures, they will be auto-reverted.

3. **Do NOT delete tests or weaken assertions.**

4. **Put parameters in `backend/config.py`**, not hardcoded in services.

5. **WRITE NEW TESTS** for your changes. If you add a feature, add a test.

6. **Commit your changes** at the end:
   `git add -A && git commit -m "Lab cycle_{cycle:03d}: <summary>"`

---

## CUMULATIVE PROGRESS (all {cumulative.get('total_cycles', 0)} cycles)

```json
{cumulative_str}
```

**Files NEVER touched** (explore these — they may have bugs or be disconnected):
{chr(10).join('- ' + f for f in cumulative.get('files_never_touched', []))}

---

## PRE-EXISTING TEST FAILURES

```
{baseline_failures}
```

---

## ENGINE OUTPUT (fresh data — from REAL backend services)

{data_block}

---

## RECENT EXPERIMENTS (last 5 cycles)

{past_learnings}

---

## WHAT MAKES A GREAT CYCLE

### Examples of GREAT cycles:
- "Added 8 new tests for portfolio_engine edge cases, found and fixed a negative-price bug in projection"
- "Implemented regime-switching MC (2 new functions, 150 lines), backtest shows 15% lower drift error"
- "Wired drift_detector into crash model as a feature, retrained model, AUC improved 0.72 -> 0.76"
- "Built CVaR endpoint, added frontend card, wrote 5 tests — full stack feature in one cycle"
- "Fixed 12 TypeScript errors in frontend, added loading states to 3 pages, build now clean"

### Examples of WEAK cycles (avoid these):
- "Changed one config value in config.py" (too small)
- "Fixed variable ordering in one function" (valid but aim higher)
- "Tweaked MC drift by adjusting sigma" (parameter tuning, not engineering)

---

## EXPLORATION MANDATE

Before coding anything, spend 10-15 minutes exploring:

1. Read at least 5 service files in `backend/services/`
2. Check `backend/routers/` — do endpoints call real services?
3. Look at `engine/training/` — is the training pipeline complete?
4. Check `frontend/src/app/` — do pages handle errors? Show real data?
5. Run `python -m pytest backend/tests/ -v -m "not slow"` — what passes/fails?
6. Look at the engine output data above — what's broken or suboptimal?

THEN form a hypothesis. THEN implement.

---

## EXPERIMENT REPORT (REQUIRED)

Create: `lab/experiments/cycle_{cycle:03d}/experiment_report.json`

```json
{{
    "cycle": {cycle},
    "timestamp": "<now>",
    "research_track": "<which track you worked on>",
    "what_i_noticed": "<what caught your attention during exploration>",
    "hypothesis": "<what you think could be improved>",
    "what_i_did": "<detailed description of ALL changes>",
    "files_modified": ["<every file touched>"],
    "files_created": ["<any new files>"],
    "tests_added": ["<new test names>"],
    "tests_fixed": ["<previously-failing tests fixed>"],
    "lines_changed_approx": <number>,
    "results": {{
        "before": {{"<metric>": "<value>"}},
        "after": {{"<metric>": "<value>"}},
        "improved": true/false
    }},
    "analysis": "<honest assessment>",
    "next_steps": "<what the next cycle should build on>",
    "confidence": "<low/medium/high>",
    "should_keep": true/false,
    "depth_rating": "<TRIVIAL/LIGHT/MEDIUM/DEEP>"
}}
```

---

## GO

Explore deeply. Think ambitiously. Build something real. Test it. Log it.
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    print(f"  Prompt built: {len(prompt)} chars, cycle {cycle}, "
          f"track={primary_track['id']}, {len(all_data)} data files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle-dir", required=True)
    parser.add_argument("--experiments-dir", required=True)
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline-failures", default=None)
    args = parser.parse_args()

    build_prompt(args.cycle_dir, args.experiments_dir, args.cycle, args.output,
                 baseline_failures_path=args.baseline_failures)
