"""
Shared idempotent trial registration — ONE implementation of the registry
INSERT whose cumulative count the DSR/PBO adoption gate deflates against.

Why: ensure_lppls_trial / ensure_crash_trial / ensure_congress_trial /
ensure_ark_trial each carried a verbatim copy of the existing-row check +
count_cumulative_trials()+1 + 10-column INSERT. The counting semantics are
gate-critical; they must live in one place. (The two fragility ensures predate
this helper and migrate opportunistically.)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def ensure_trial_registered(param: str, notes: dict, db_path=None,
                            config_version: str = "descriptive",
                            lane_id: str | None = None) -> int:
    """Idempotently insert a pre-registered trial row. Returns the row id
    (existing or new). Registering enters the cumulative trial count — the
    conservative direction (stricter DSR/PBO)."""
    from backend.db import count_cumulative_trials, get_connection, init_db

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM rule_experiments WHERE param = ? ORDER BY id LIMIT 1",
            (param,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])
        cumulative = count_cumulative_trials(conn) + 1
        cur = conn.execute(
            "INSERT INTO rule_experiments "
            "(created_at, config_version, lane_id, param, old_value, new_value, "
            " batch_trials, cumulative_trials, verdict, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), config_version, lane_id, param,
             None, "registered", 1, cumulative, "adopted", json.dumps(notes)),
        )
        conn.commit()
        logger.info("Pre-registered trial %s (cumulative trials now %d)",
                    param, cumulative)
        return int(cur.lastrowid)
    finally:
        conn.close()


MOM_BACKTEST_TRIAL_PARAM = "mom-backtest-12-1"


def ensure_mom_backtest_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-MOM-BACKTEST — the OFFLINE 12-1
    momentum direction-check on the survivorship-free 2017+ panel. Counted
    here so the DSR/PBO guards deflate against it even though it is not a
    forward clock. Canonical commitment (hypothesis, frozen params, decision
    rule): docs/TRIALS/TRIAL-MOM-BACKTEST-12-1-momentum.md, committed BEFORE
    the first backtest run."""
    notes = {
        "hypothesis": ("net-of-cost long-only 12-1 momentum on the "
                       "survivorship-free 2017+ panel achieves Sharpe >= SPY "
                       "over the identical window (honest prior: weak; PASS "
                       "means consistent-with-literature, never alpha)"),
        "purpose": "offline direction-check - NOT a forward clock",
        "primary_metric": "net Sharpe (rf=0) minus SPY net Sharpe, one frozen run",
        "decision_rule": {
            "pass": "Sharpe >= SPY AND maxDD <= 1.25x SPY -> lane PROPOSAL only (attended)",
            "fail": "else -> NEGATIVE_RESULTS, no proposal",
            "void": "panel-quality gate failure voids trial unrun",
            "reruns": "forbidden under this ID; variants are new trials",
        },
        "doc": "docs/TRIALS/TRIAL-MOM-BACKTEST-12-1-momentum.md",
    }
    return ensure_trial_registered(MOM_BACKTEST_TRIAL_PARAM, notes,
                                   db_path=db_path)


MOM_TREND_TRIAL_PARAM = "mom-trend-backtest-12-1"


def ensure_mom_trend_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-MOM-TREND — the successor to the
    FAILED mom-backtest-12-1 (#13): identical frozen spec + SPY 10-month SMA
    risk-off-to-cash filter. Offline direction-check, not a forward clock.
    Doc: docs/TRIALS/TRIAL-MOM-TREND-momentum-with-trend-filter.md."""
    notes = {
        "hypothesis": ("SPY 10-month-SMA cash filter on the exact #13 spec "
                       "lifts net Sharpe to >= SPY and maxDD inside 1.25x "
                       "SPY (prior: moderate; COVID-2020 whipsaw may kill it)"),
        "purpose": "offline direction-check successor to FAILED #13 - NOT a forward clock",
        "primary_metric": "net Sharpe (rf=0) minus SPY net Sharpe, one frozen run",
        "decision_rule": {
            "pass": "Sharpe >= SPY AND maxDD <= 1.25x SPY -> lane PROPOSAL only (attended)",
            "fail": "else -> NEGATIVE_RESULTS; momentum-lane inquiry CLOSES for this window",
            "reruns": "forbidden; no third variant without a new mechanism class",
        },
        "predecessor": "mom-backtest-12-1 (#13) FAILED: Sharpe 0.629 vs SPY 0.871, maxDD -54.7%",
        "doc": "docs/TRIALS/TRIAL-MOM-TREND-momentum-with-trend-filter.md",
    }
    return ensure_trial_registered(MOM_TREND_TRIAL_PARAM, notes, db_path=db_path)


CMP_INSIDER_TRIAL_PARAM = "cmp-insider-ic"


def ensure_cmp_insider_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-CMP-INSIDER-IC — the forward IC clock for
    the CMP-classified opportunistic-insider signal promoted from the brain
    module (BRAIN-003, first kill-condition survivor; weak positive prior, deploy
    gate NOT met on backtest). Runs beside T9 insider_opp: (different signal —
    routine + unclassifiable buyers dropped via the 2006-2026Q1 bulk history
    artifact). Doc: docs/TRIALS/TRIAL-CMP-INSIDER-IC.md, committed BEFORE the
    first forward observation."""
    notes = {
        "hypothesis": ("stocks with more DISTINCT opportunistic (CMP 2012) "
                       "insider buyers over trailing 12mo earn higher forward "
                       "returns in large/mid caps (prior from BRAIN-003: "
                       "FF5+UMD alpha +102 bps/mo t=1.89 - weak positive, "
                       "NOT a discovery; null in microcap)"),
        "purpose": "forward IC clock - descriptive only, never arms",
        "primary_metric": "126d forward rank IC with 90% block-bootstrap CI",
        "decision_rule": {
            "earliest_decision": "2027-07-21",
            "adopt_consideration": ("126d IC > 0 with 90% CI excluding 0 AND "
                                    "21/63d ICs not significantly negative -> "
                                    "evaluate_candidate gate"),
            "kill": "126d IC <= 0 at decision date -> NEGATIVE_RESULTS",
            "contamination": ("artifact defect or >=25% degraded snapshots -> "
                              "affected snapshots excluded, inception moves forward"),
            "crash_override": "SPY -20% defers decision to >=6mo past trough",
        },
        "frozen": ("365d window; 200d live fetch / 60 filings; 210d staleness "
                   "guard; book universe; weekly throttle; CMP rule verbatim"),
        "provenance": "brain module TRIAL-BRAIN-003 (export/opportunistic_insider bundle)",
        "doc": "docs/TRIALS/TRIAL-CMP-INSIDER-IC.md",
    }
    return ensure_trial_registered(CMP_INSIDER_TRIAL_PARAM, notes, db_path=db_path)
