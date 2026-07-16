"""
Aegis Finance - Autonomous R&D Loop v13
=========================================
Sandbox methodology with a quality gate, hypothesis memory, theme-driven
cycle selection, and post-cycle robustness probes.

v13 additions (over v12):
  1. Multi-asset surface — bond_analytics, fx_curves, commodity_curves,
     crypto_market, defi_metrics, edgar_events, esg, portfolio_currency
     are all wired into data_generator.py as new collectors so each
     cycle's prompt sees the real engine output of those services
  2. Six new robustness probes covering bond YTM regression, duration
     shock prediction, CIP arbitrage identity, futures-curve slope
     classifier, currency-suffix mapper, EDGAR taxonomy completeness
  3. build-theme prompt now lists v13 services as "extend, don't rewrite"
     and points to adjacent capabilities (TIPS, COT, FinBERT-on-8K,
     hedged backtest, on-chain factor) to stop Claude duplicating them
  4. Pre-existing flat-vol MC probe fixed (signature drift in monte_carlo)

v12 additions (over v11):
  1. Theme-driven cycle selection — picks the theme that addresses the
     weakest quality component (stabilise / quality / integrate / build
     / audit / robustness / performance) instead of rigid 3-way rotation
  2. Hypothesis registry (`lab/hypotheses.json`) — every cycle logs its
     hypothesis + verdict + why, and past successes/failures are
     injected into the next prompt so Claude stops repeating dead ends
  3. Robustness probes — 5 edge-case probes run after each cycle
     (flat-vol MC, extreme drawdown anomaly flag, single-asset optimizer,
     monotone crash timeline, tiny-portfolio analyze) contribute to the
     composite score
  4. Scorecard extensions — cycles carry a robustness sub-score so the
     loop sees more than just tests/smells/health

v11 behaviour (preserved):
  1. Pre-cycle data-source health probe — abort when yfinance is down
  2. Full fast-test suite after the session (not just 3 smoke tests)
  3. Quality scorecard + auto-rollback
  4. Rolling 60-cycle ledger + trend-aware prompt injection

Usage:
  python lab/rd_loop.py                      # opus, auto-detect cycle
  python lab/rd_loop.py --cycles 50          # run up to cycle 50
  python lab/rd_loop.py --model sonnet       # cheaper
  python lab/rd_loop.py --no-rollback        # keep commits even on regression
  python lab/rd_loop.py --skip-full-tests    # skip the full fast suite (faster)
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
HISTORY_PATH = LAB_DIR / "quality_history.json"

# Make sibling modules importable without a package layout
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))
from quality import (  # noqa: E402
    collect_metrics, score_cycle, write_scorecard,
    read_history, append_history, trend_summary,
    ROLLBACK_THRESHOLD, PASS_THRESHOLD,
)
from health_probe import probe_all  # noqa: E402
import hypotheses  # noqa: E402
import themes  # noqa: E402
import robustness  # noqa: E402

HYPOTHESES_PATH = LAB_DIR / "hypotheses.json"

SESSION_TIMEOUT = 2700  # 45 min max per session

import shutil
CLAUDE_CMD = shutil.which("claude") or shutil.which("claude.cmd") or "claude"

# v12: cycle theme is chosen by themes.select_theme() based on current
# scorecard + trend. The rotation constants are kept for legacy callers
# only; new code paths read themes.THEMES.
CYCLE_TYPES = ["DEEP_AUDIT", "BUILD", "INTEGRATE"]


def _get_cycle_type(cycle: int) -> str:
    """Legacy shim — prefer `_choose_theme(...)` for v12 behaviour."""
    return CYCLE_TYPES[cycle % 3]


def _choose_theme(cycle: int) -> themes.ThemeDecision:
    """Pick this cycle's theme from the rolling ledger + last scorecard."""
    history = read_history(HISTORY_PATH, last_n=10)
    trend = trend_summary(history)
    last_scorecard = None
    if history:
        # History entries are the thinned summary; we don't keep the full
        # scorecard there, so reconstruct a minimal shape from trend data
        # and the most recent entry's flags.
        latest = history[-1]
        last_scorecard = {
            "components": {
                "tests": 1.0 if latest.get("verdict") != "rollback" else 0.5,
                "health": 1.0,
                "smells": 1.0,
            },
            "after": {
                "frontend_build_ok": "frontend build broke" not in (latest.get("flags") or []),
                "tests_failed": sum(
                    1 for f in latest.get("flags") or []
                    if "test failure" in f.lower()
                ),
            },
            "flags": latest.get("flags") or [],
        }
    last_themes = [h.get("cycle_type") for h in history if h.get("cycle_type")]
    return themes.select_theme(
        cycle=cycle, scorecard=last_scorecard, trend=trend, last_themes=last_themes,
    )


# ---------------------------------------------------------------------------
# Build the prompt — sandbox mentality, full freedom
# ---------------------------------------------------------------------------

def build_prompt(cycle: int, cycle_dir: Path, baseline_failures: str,
                 trend: dict | None = None,
                 theme_decision: themes.ThemeDecision | None = None,
                 hypothesis_block: str | None = None) -> str:

    # Legacy: when called without a theme_decision, fall back to rotation
    cycle_type = theme_decision.theme.upper() if theme_decision else _get_cycle_type(cycle)

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

    # Trend block from the quality ledger — makes Claude aware if the loop is
    # drifting downhill across multiple cycles
    trend_lines: list[str] = []
    if trend and trend.get("available"):
        trend_lines.append(
            f"Rolling quality avg: {trend['avg_score']:.3f}  "
            f"(last 3 cycles: {trend['recent_avg']:.3f})"
        )
        if trend.get("declining_trend"):
            trend_lines.append(
                "WARNING: the loop's composite score has been declining for "
                "3+ cycles. Prioritize quality over novelty this cycle."
            )
        last = trend.get("last_verdicts") or []
        if last:
            trend_lines.append("Last verdicts: " + " → ".join(last))
    trend_block = "\n".join(trend_lines) if trend_lines else "No ledger yet."

    # Theme-driven instructions (v12). Fall back to the legacy 3-way
    # instructions when no theme was selected.
    type_instructions = ""
    theme_reason = ""
    if theme_decision is not None:
        type_instructions = themes.instructions_for(theme_decision.theme)
        theme_reason = theme_decision.reason

    # Legacy block — retained for compatibility when no theme is provided
    if type_instructions:
        pass
    elif cycle_type == "DEEP_AUDIT":
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
safe withdrawal rate, Polygon.io real-time data, copula tail risk, factor models,
v13 (bond_analytics, edgar_events, esg, fx_curves, commodity_curves,
crypto_market, defi_metrics, portfolio_currency) — extend, don't rewrite.
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

## Current engine (90+ services, 140+ endpoints, 1700+ tests) — v13

Backend services (highlights — see backend/services/ for the full set):
crash_model, signal_engine (12 components), regime_detector, risk_scorer,
factor_model (FF6+PCA), stress_testing (+hypothetical), copula_tail,
covariance (RMT), liquidity_risk, attribution (Brinson+MCTR),
cross_sectional_momentum, conformal_predictor, mpc_optimizer,
portfolio_optimizer (CVaR/RP/MaxDiv/HRP), tearsheet (HTML+xlsx),
allocation_backtester, providers (yf/fmp/finnhub/polygon/av/fred),
ownership, world_markets, factor_grades, market_treemap, copilot.

**v13 NEW (Bloomberg-gap closers — extend or surface in frontend/SDK):**
  - bond_analytics — YTM/dur/conv/key-rate/ladder + Treasury curve
  - edgar_events  — SEC 8-K item classifier + materiality stream
  - esg           — Finnhub+FMP ESG blend per ticker
  - fx_curves     — G10 spot + CIP-implied forward curve + carry
  - commodity_curves — futures curves + contango/backwardation + roll yield
  - crypto_market — CoinGecko top-cap snapshots + history
  - defi_metrics  — DefiLlama TVL by chain / protocol
  - portfolio_currency — multi-currency accounting + hedged/unhedged decomp

API keys available: FRED, Finnhub, FMP, DeepSeek, Alpha Vantage, Polygon.io, ANTHROPIC
Installed packages: ta, polygon-api-client, riskfolio-lib, copulas, ruptures, pytrends

Signal engine components: crash_prob, regime, valuation, momentum, mean_reversion,
external, macro_risk, drawdown, economic_surprise, momentum_breadth, insider_trading,
vix_term_structure

## Engine data snapshot

{data_block}

## Recent cycles (don't repeat)

{past_block}

## Quality trend (rolling ledger)

{trend_block}

## Theme selection (v12)

{theme_reason if theme_reason else "Theme selected by rotation (legacy mode)."}

## Hypothesis memory

{hypothesis_block or "No hypothesis ledger available yet."}

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

def run_cycle(cycle: int, model: str, baseline_failures: str, *,
              rollback_on_regression: bool = True,
              skip_full_tests: bool = False) -> dict:
    cycle_id = f"cycle_{cycle:03d}"
    cycle_dir = EXPERIMENTS_DIR / cycle_id
    cycle_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    cycle_start = time.time()

    # v12: theme-driven cycle selection replaces rotation
    theme_decision = _choose_theme(cycle)
    cycle_type = theme_decision.theme.upper()

    print(f"\n{'='*60}")
    print(f"  CYCLE {cycle} ({cycle_type}) - {datetime.now().strftime('%H:%M:%S')}")
    print(f"  Theme chosen: {theme_decision.theme}  ({theme_decision.reason})")
    print(f"{'='*60}")

    # 1. Health probe — abort if critical data sources are down
    print("\n  Probing data sources...")
    health = probe_all()
    (cycle_dir / "health_probe.json").write_text(
        json.dumps(health, indent=2, default=str), encoding="utf-8"
    )
    if not health["healthy"]:
        yf_err = health["results"].get("yfinance", {}).get("error", "unknown")
        print(f"  [ABORT] yfinance is down ({yf_err}) — skipping cycle")
        return {"status": "aborted_unhealthy", "health": health}
    print(f"  Data sources: {health['live_sources']}/{health['total_sources']} live")

    # 2. Capture the pre-session commit so we can roll back if needed
    pre_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_DIR),
        capture_output=True, text=True,
    ).stdout.strip()

    # 3. Baseline metric snapshot — skip tests/frontend here to save time
    #    (we run the full suite post-session; pre-session only needs smells
    #    and import health so we can compute a delta)
    print("  Snapshotting baseline metrics...")
    before = collect_metrics(REPO_DIR, skip_tests=True, skip_frontend=True)
    # Carry over the baseline fast-suite counts that main() computed
    if baseline_failures is not None:
        failed_m = re.search(r"(\d+) failed", baseline_failures)
        before.tests_failed = int(failed_m.group(1)) if failed_m else 0

    # Data generation
    print("\n  Generating engine data...")
    subprocess.run(
        [sys.executable, str(LAB_DIR / "data_generator.py"),
         "--output-dir", str(cycle_dir / "data"), "--cycle", str(cycle)],
        cwd=str(REPO_DIR), timeout=300,
    )

    # Build prompt (with trend-awareness + hypothesis memory + canonical findings)
    trend = trend_summary(read_history(HISTORY_PATH, last_n=10))
    hypothesis_block = hypotheses.summarise_for_prompt(HYPOTHESES_PATH)
    try:
        import findings
        findings_block = findings.summarise_for_prompt()
        if findings_block:
            hypothesis_block = findings_block + "\n\n" + hypothesis_block
    except Exception as e:
        print(f"  [WARN] findings ledger unavailable: {e}")
    prompt = build_prompt(
        cycle, cycle_dir, baseline_failures,
        trend=trend,
        theme_decision=theme_decision,
        hypothesis_block=hypothesis_block,
    )
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

    # Commit if Claude didn't already (session may have committed mid-run; this
    # is the safety net for anything left unstaged)
    duration = int((time.time() - cycle_start) / 60)
    subprocess.run(["git", "add", "-A"], cwd=str(REPO_DIR))
    commit_res = subprocess.run(
        ["git", "commit", "-m", f"Lab {cycle_id} ({duration}min)"],
        cwd=str(REPO_DIR), capture_output=True, text=True,
    )
    # If that failed because nothing was staged, still create the empty marker
    if commit_res.returncode != 0:
        subprocess.run(
            ["git", "commit", "-m", f"Lab {cycle_id} ({duration}min)", "--allow-empty"],
            cwd=str(REPO_DIR), capture_output=True,
        )
    post_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_DIR),
        capture_output=True, text=True,
    ).stdout.strip()

    # Quality scorecard + rollback decision
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{pre_commit}..{post_commit}"],
        cwd=str(REPO_DIR), capture_output=True, text=True,
    ).stdout
    frontend_touched = "frontend/" in changed
    print("\n  Collecting post-cycle metrics...")
    after = collect_metrics(
        REPO_DIR,
        skip_tests=skip_full_tests,
        skip_frontend=not frontend_touched,
    )
    scorecard = score_cycle(before, after)
    scorecard["cycle"] = cycle
    scorecard["cycle_type"] = cycle_type
    scorecard["theme"] = theme_decision.theme
    scorecard["theme_reason"] = theme_decision.reason
    scorecard["duration_min"] = duration
    scorecard["pre_commit"] = pre_commit
    scorecard["post_commit"] = post_commit

    # v12: robustness probes — edge-case sanity after every cycle
    try:
        probe_report = robustness.run_all()
        scorecard["robustness"] = probe_report
        print(f"  {robustness.summary_line(probe_report)}")
    except Exception as e:
        scorecard["robustness"] = {"error": str(e)}
        print(f"  [WARN] robustness probes failed: {e}")

    write_scorecard(cycle_dir / "scorecard.json", scorecard)

    score = scorecard["composite_score"]
    verdict = scorecard["verdict"]
    print(f"  Quality score: {score:.3f}  →  verdict={verdict}")
    if scorecard["flags"]:
        for flag in scorecard["flags"]:
            print(f"    · {flag}")

    if verdict == "rollback" and rollback_on_regression and post_commit != pre_commit:
        print(f"  [ROLLBACK] Score below {ROLLBACK_THRESHOLD:.2f}. Reverting to {pre_commit[:8]}.")
        subprocess.run(
            ["git", "reset", "--hard", pre_commit],
            cwd=str(REPO_DIR), capture_output=True,
        )
        scorecard["rolled_back"] = True
    else:
        scorecard["rolled_back"] = False

    append_history(HISTORY_PATH, {
        "cycle": cycle,
        "cycle_type": cycle_type,
        "theme": theme_decision.theme,
        "composite_score": score,
        "verdict": verdict,
        "flags": scorecard["flags"],
        "rolled_back": scorecard["rolled_back"],
        "robustness_score": (scorecard.get("robustness") or {}).get("score"),
        "timestamp": datetime.utcnow().isoformat(),
    })

    # v12: distill this cycle into a hypothesis memo for the next cycle
    try:
        report_path = cycle_dir / "experiment_report.json"
        report_data = None
        if report_path.exists():
            try:
                report_data = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                report_data = None
        # baseline for score-delta: use previous ledger entry
        prev_entries = read_history(HISTORY_PATH, last_n=2)
        baseline_score = None
        if len(prev_entries) >= 2:
            baseline_score = prev_entries[-2].get("composite_score")
        hypotheses.record_from_report(
            HYPOTHESES_PATH,
            cycle=cycle,
            theme=theme_decision.theme,
            report=report_data,
            scorecard=scorecard,
            baseline_score=baseline_score,
        )
    except Exception as e:
        print(f"  [WARN] could not record hypothesis: {e}")

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

    return {"status": "ok", "scorecard": scorecard}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Aegis Finance R&D Loop v11")
    parser.add_argument("--cycles", type=int, default=50)
    parser.add_argument("--model", default="opus")
    parser.add_argument("--start-cycle", type=int, default=None)
    parser.add_argument("--branch", default="lab/autonomous-rd")
    parser.add_argument("--no-rollback", action="store_true",
                        help="Keep every commit even if the cycle regresses")
    parser.add_argument("--skip-full-tests", action="store_true",
                        help="Skip the post-cycle full fast-test suite (faster)")
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
    print(f"  AEGIS R&D LAB v13 - Hypothesis-aware sandbox + multi-asset surface")
    print(f"  Model: {args.model} | Cycles: {start}-{args.cycles}")
    print(f"  Session: {SESSION_TIMEOUT // 60} min | Branch: {args.branch}")
    print(f"  Themes: {', '.join(themes.THEMES)}")
    next_theme = _choose_theme(start).theme
    print(f"  Next cycle theme: {next_theme}")
    print(f"  Rollback: {'disabled' if args.no_rollback else f'auto < {ROLLBACK_THRESHOLD:.2f}'} "
          f"(pass >= {PASS_THRESHOLD:.2f})")
    print(f"  Hypotheses logged: {len(hypotheses.load(HYPOTHESES_PATH))}")
    print(f"{'='*60}")

    summary_counts = {"ok": 0, "rollback": 0, "warn": 0, "aborted_unhealthy": 0}
    for cycle in range(start, args.cycles + 1):
        try:
            result = run_cycle(
                cycle, args.model, baseline_failures,
                rollback_on_regression=not args.no_rollback,
                skip_full_tests=args.skip_full_tests,
            )
            if isinstance(result, dict):
                status = result.get("status")
                if status == "aborted_unhealthy":
                    summary_counts["aborted_unhealthy"] += 1
                else:
                    v = (result.get("scorecard") or {}).get("verdict", "warn")
                    summary_counts[v] = summary_counts.get(v, 0) + 1
        except Exception as e:
            print(f"\n  [FATAL] Cycle {cycle}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        if cycle < args.cycles:
            print(f"\n  Cooldown 30s...")
            time.sleep(30)

    print(f"\n{'='*60}")
    print(f"  DONE - cycles {start}-{args.cycles}")
    print(f"  Verdicts: pass={summary_counts.get('pass', 0)}  "
          f"warn={summary_counts.get('warn', 0)}  "
          f"rollback={summary_counts.get('rollback', 0)}  "
          f"aborted={summary_counts.get('aborted_unhealthy', 0)}")
    print(f"  git log --oneline {args.branch} -{args.cycles}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
