"""
Deployment-gate checks (separate from code correctness).

  - the v2→v3 migration runs on an EXISTING v2 DB (Railway persistent volume),
    creating paper_nav + rule_experiments — else live MTM writes fail silently;
  - inception is idempotent: a redeploy does NOT reset or double-init lanes;
  - the scheduler health snapshot exposes the fields the canary needs.
"""

import os
import subprocess
import sqlite3
import sys
from datetime import date

from backend.config import paper_portfolios
from backend.db import _SCHEMA_V1, get_connection, init_db
from backend.services.portfolio_intelligence.reference_engine import (
    initialize_lane,
    mark_lane_to_market,
)
from backend.services.portfolio_intelligence.rules import _get_sleeve_tickers


def _has_table(db, name) -> bool:
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _universe_prices(value: float) -> dict:
    sleeves = _get_sleeve_tickers(paper_portfolios["universe"])
    return {t: value for t in sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]}


def test_v2_to_v3_migration_creates_new_tables(tmp_path):
    """Simulate a v2 DB on a persistent volume; init_db must migrate to v3."""
    db = tmp_path / "v2.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_SCHEMA_V1)  # base tables
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS replay_cache (
               lane_id TEXT NOT NULL, universe_hash TEXT NOT NULL,
               rules_hash TEXT NOT NULL, market_data_date TEXT NOT NULL,
               computed_at TEXT NOT NULL, result_json TEXT NOT NULL,
               PRIMARY KEY (lane_id, universe_hash, rules_hash, market_data_date));"""
    )
    conn.execute("INSERT INTO _schema_version (version) VALUES (2)")
    conn.commit()
    conn.close()

    # Pre-migration: the v3 tables do not exist.
    assert not _has_table(db, "paper_nav")
    assert not _has_table(db, "rule_experiments")

    init_db(db)  # this is what runs on Railway boot

    assert _has_table(db, "paper_nav"), "paper_nav missing — live MTM would fail silently"
    assert _has_table(db, "rule_experiments")
    conn = sqlite3.connect(str(db))
    try:
        ver = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
    finally:
        conn.close()
    assert ver == 3


def test_inception_idempotent_across_redeploy(tmp_path):
    db = tmp_path / "pi.db"
    init_db(db)
    prices = _universe_prices(100.0)

    initialize_lane("conservative", db_path=db, prices=prices)
    conn = get_connection(db)
    incep1 = conn.execute(
        "SELECT inception_date, inception_value, config_version "
        "FROM paper_portfolios WHERE id='conservative'"
    ).fetchone()
    n_pos1 = conn.execute(
        "SELECT COUNT(*) FROM paper_positions WHERE portfolio_id='conservative'"
    ).fetchone()[0]
    conn.close()

    # Accumulate a NAV row, then simulate a redeploy (re-init + re-run init_db).
    mark_lane_to_market("conservative", prices=prices, as_of_date=date(2026, 6, 1), db_path=db)
    init_db(db)
    initialize_lane("conservative", db_path=db, prices=prices)

    conn = get_connection(db)
    incep2 = conn.execute(
        "SELECT inception_date, inception_value, config_version "
        "FROM paper_portfolios WHERE id='conservative'"
    ).fetchone()
    n_pos2 = conn.execute(
        "SELECT COUNT(*) FROM paper_positions WHERE portfolio_id='conservative'"
    ).fetchone()[0]
    nav_rows = conn.execute(
        "SELECT COUNT(*) FROM paper_nav WHERE portfolio_id='conservative'"
    ).fetchone()[0]
    conn.close()

    assert tuple(incep2) == tuple(incep1)        # inception anchor unchanged
    assert incep2["inception_value"] == 100_000.0
    assert n_pos2 == n_pos1                       # positions NOT doubled
    assert nav_rows == 1                          # track record NOT wiped


def test_scheduler_health_exposes_canary_fields():
    from backend.services.portfolio_intelligence.scheduler import scheduler_health
    h = scheduler_health()
    for key in ("running", "n_jobs", "job_ids", "last_mtm"):
        assert key in h


def test_data_dir_honors_env_var_without_shadowing_config(tmp_path):
    """The Railway volume-shadow contract.

    A persistent volume must hold ONLY mutable state (aegis_pi.db, the
    APScheduler job store). The immutable paper_portfolios.yaml that the PI
    subsystem reads at boot MUST stay baked in the image — otherwise mounting
    the volume over backend/data shadows the YAML and lanes can't initialize.

    DATA_DIR is resolved at import time from AEGIS_DATA_DIR, so this asserts the
    contract in a fresh interpreter: both DBs relocate to the volume; the config
    YAML path does NOT.
    """
    vol = tmp_path / "volume"
    probe = (
        "from backend.config import DATA_DIR, BACKEND_DIR;"
        "from backend.db import DB_PATH;"
        "from backend.services.portfolio_intelligence.scheduler import _DB_DIR;"
        "vol = DATA_DIR;"
        # mutable state follows the volume
        "assert str(DB_PATH).startswith(str(vol)), DB_PATH;"
        "assert str(_DB_DIR).startswith(str(vol)), _DB_DIR;"
        # immutable config stays in the image, NEVER under the volume
        "yaml = BACKEND_DIR / 'data' / 'paper_portfolios.yaml';"
        "assert not str(yaml).startswith(str(vol)), yaml;"
        "print('OK')"
    )
    env = {**os.environ, "AEGIS_DATA_DIR": str(vol)}
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"shadow-trap contract broken:\n{r.stdout}\n{r.stderr}"


def test_data_dir_defaults_to_backend_data_locally():
    """With no AEGIS_DATA_DIR set, paths default to backend/data (local dev)."""
    probe = (
        "from backend.config import DATA_DIR, BACKEND_DIR;"
        "assert DATA_DIR == BACKEND_DIR / 'data', DATA_DIR;"
        "print('OK')"
    )
    env = {k: v for k, v in os.environ.items() if k != "AEGIS_DATA_DIR"}
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env)
    assert r.returncode == 0, f"local default broken:\n{r.stdout}\n{r.stderr}"
