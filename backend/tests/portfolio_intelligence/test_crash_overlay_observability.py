"""
Crash-overlay observability invariants.

Context: the live reference engine called `CrashPredictor.predict_proba()` with
NO arguments since the first PI commit, raising every cycle inside a swallowed
try/except. Combined with the crash model .pkl being gitignored (never shipped
to prod), the crash overlay has been structurally DARK on every reference lane
since inception — on both config v1 and v2 — and the failure hid for days under
a per-cycle WARNING. See docs/TRIALS/TRIAL-001 contamination note.

These tests pin the fix:
  1. the call site uses the correct signature `predict_proba(features, "3m")`,
  2. a missing model returns a STATUS (model_not_deployed), never an exception,
  3. every daily check persists a crash_overlay_eval audit row,
  4. /api/health/full's overlay block reports all_operational=False when dark
     — so a dark overlay can never again run unseen.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np

from backend import db as db_module
from backend.services.portfolio_intelligence import reference_engine as engine
from backend.services.portfolio_intelligence import scheduler as sched


# ── _evaluate_crash_overlay ─────────────────────────────────────────────────


class TestEvaluateCrashOverlay:
    def test_no_model_returns_status_not_exception(self):
        """Prod steady state: no trained model -> (None, 'model_not_deployed')."""
        with patch(
            "backend.services.portfolio_intelligence.replay._get_shared_predictor",
            return_value=None,
        ):
            prob, status = engine._evaluate_crash_overlay()
        assert prob is None
        assert status == "model_not_deployed"

    def test_untrained_model_is_dark(self):
        predictor = MagicMock()
        predictor.is_trained = False
        with patch(
            "backend.services.portfolio_intelligence.replay._get_shared_predictor",
            return_value=predictor,
        ):
            prob, status = engine._evaluate_crash_overlay()
        assert prob is None
        assert status == "model_not_deployed"

    def test_call_signature_passes_features(self):
        """The regression guard: predict_proba MUST be called with a features
        DataFrame (the old bug called it with no args)."""
        import pandas as pd

        predictor = MagicMock()
        predictor.is_trained = True
        predictor.feature_names = ["f1", "f2"]
        predictor.predict_proba = MagicMock(return_value=np.array([0.37]))

        feat_df = pd.DataFrame(
            {"f1": [1.0, 2.0], "f2": [3.0, 4.0]},
            index=pd.to_datetime(["2026-06-11", "2026-06-12"]),
        )

        with patch(
            "backend.services.portfolio_intelligence.replay._get_shared_predictor",
            return_value=predictor,
        ), patch(
            "backend.services.data_fetcher.DataFetcher",
        ) as MockFetcher, patch(
            "engine.training.features.build_feature_matrix",
            return_value=feat_df,
        ):
            MockFetcher.return_value.fetch_market_data.return_value = (MagicMock(), {})
            MockFetcher.return_value.fetch_fred_data.return_value = {}
            prob, status = engine._evaluate_crash_overlay()

        assert status == "evaluated"
        assert prob == 0.37
        # predict_proba called with a non-empty DataFrame positional arg + "3m"
        assert predictor.predict_proba.called
        args, kwargs = predictor.predict_proba.call_args
        passed_features = args[0]
        assert hasattr(passed_features, "columns"), "must pass a features DataFrame"
        assert len(passed_features) == 1, "passes the latest single row"
        horizon = args[1] if len(args) > 1 else kwargs.get("horizon")
        assert horizon == "3m"


# ── overlay_status() canary ─────────────────────────────────────────────────


class TestOverlayStatusCanary:
    def _fresh_db(self, tmp_path, monkeypatch):
        fresh = tmp_path / "overlay.db"
        monkeypatch.setattr(db_module, "DB_PATH", fresh)
        db_module.init_db(fresh)
        return fresh

    def _write_eval(self, db, lane, status, armed=False, prob=None):
        conn = db_module.get_connection(db)
        try:
            db_module.insert_audit_log(
                conn, f"2026-06-13T20:30:00", lane, "crash_overlay_eval",
                {"status": status, "armed": armed, "crash_prob_3m": prob,
                 "threshold": 0.25},
            )
        finally:
            conn.close()

    def test_dark_overlay_trips_all_operational(self, tmp_path, monkeypatch):
        db = self._fresh_db(tmp_path, monkeypatch)
        for lane in sched_reference_lanes():
            self._write_eval(db, lane, "model_not_deployed")

        out = sched.overlay_status()
        assert out["all_operational"] is False
        for lane in sched_reference_lanes():
            assert out["lanes"][lane]["operational"] is False
            assert out["lanes"][lane]["status"] == "model_not_deployed"

    def test_operational_when_all_evaluated(self, tmp_path, monkeypatch):
        db = self._fresh_db(tmp_path, monkeypatch)
        for lane in sched_reference_lanes():
            self._write_eval(db, lane, "evaluated", armed=False, prob=0.08)

        out = sched.overlay_status()
        assert out["all_operational"] is True
        assert all(v["operational"] for v in out["lanes"].values())

    def test_never_evaluated_is_not_operational(self, tmp_path, monkeypatch):
        db = self._fresh_db(tmp_path, monkeypatch)
        # write eval for only one lane; the rest have no rows
        first = sched_reference_lanes()[0]
        self._write_eval(db, first, "evaluated", prob=0.08)

        out = sched.overlay_status()
        assert out["all_operational"] is False
        assert out["lanes"][first]["operational"] is True
        for lane in sched_reference_lanes()[1:]:
            assert out["lanes"][lane]["status"] == "never_evaluated"
            assert out["lanes"][lane]["operational"] is False


# ── integration: daily check persists the eval row ──────────────────────────


class TestDailyCheckPersistsOverlayEval:
    def test_run_reference_check_writes_overlay_eval_row(self, tmp_path, monkeypatch):
        fresh = tmp_path / "run.db"
        monkeypatch.setattr(db_module, "DB_PATH", fresh)
        db_module.init_db(fresh)

        # Offline + dark: no model, no live prices (panel disabled by conftest).
        with patch(
            "backend.services.portfolio_intelligence.replay._get_shared_predictor",
            return_value=None,
        ), patch.object(engine, "_get_current_prices", return_value={}), \
                patch.object(engine, "_get_sector_map", return_value={}):
            engine.initialize_lane("conservative", db_path=fresh)
            engine.run_reference_check(
                "conservative", db_path=fresh, as_of_date=date(2026, 6, 13),
            )

        conn = db_module.get_connection(fresh)
        try:
            row = conn.execute(
                "SELECT payload FROM audit_log "
                "WHERE portfolio_id = ? AND event_type = 'crash_overlay_eval' "
                "ORDER BY id DESC LIMIT 1",
                ("conservative",),
            ).fetchone()
        finally:
            conn.close()

        assert row is not None, "daily check must record a crash_overlay_eval row"
        import json
        payload = json.loads(row["payload"])
        assert payload["status"] == "model_not_deployed"
        assert payload["armed"] is False


def sched_reference_lanes():
    from backend.services.portfolio_intelligence.rules import REFERENCE_LANES
    return list(REFERENCE_LANES)
