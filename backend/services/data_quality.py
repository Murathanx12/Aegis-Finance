"""
Aegis Finance — Data Quality Validation
=========================================

Checks fetched data for staleness, range violations, completeness,
and consistency issues. Returns warnings but never blocks execution.

Adapted from V7 data/quality.py.

Usage:
    from backend.services.data_quality import DataQualityChecker

    checker = DataQualityChecker()
    warnings = checker.validate(data)
"""

import pandas as pd

from backend.config import config


class DataQualityChecker:
    """Validates market data quality with configurable thresholds."""

    def __init__(self):
        dq_cfg = config.get("data_quality", {})
        self.staleness_days = dq_cfg.get("staleness_threshold_days", 3)
        self.nan_threshold = dq_cfg.get("nan_threshold_pct", 0.20)
        self.sp500_max_daily_return = dq_cfg.get("sp500_max_daily_return", 0.10)
        self.sp500_max_daily_jump = dq_cfg.get("sp500_max_daily_jump", 0.30)
        self.vix_range = dq_cfg.get("vix_range", [5, 90])
        self.yield_range = dq_cfg.get("yield_range", [-1.0, 20.0])

    def validate(self, data: pd.DataFrame) -> list[dict]:
        """Run all quality checks on the data.

        Args:
            data: DataFrame with market data columns (SP500, VIX, T10Y, etc.)

        Returns:
            List of warning dicts with keys: check, column, message, severity
        """
        warnings = []
        warnings.extend(self._check_staleness(data))
        warnings.extend(self._check_range(data))
        warnings.extend(self._check_completeness(data))
        warnings.extend(self._check_consistency(data))
        return warnings

    def summary(self, data: pd.DataFrame) -> dict:
        """Return a compact quality summary for API responses."""
        warnings = self.validate(data)
        n_errors = sum(1 for w in warnings if w["severity"] == "error")
        n_warnings = sum(1 for w in warnings if w["severity"] == "warning")
        n_info = sum(1 for w in warnings if w["severity"] == "info")

        if n_errors > 0:
            status = "degraded"
        elif n_warnings > 0:
            status = "warning"
        else:
            status = "healthy"

        return {
            "status": status,
            "errors": n_errors,
            "warnings": n_warnings,
            "info": n_info,
            "details": warnings[:10],
        }

    def _check_staleness(self, data: pd.DataFrame) -> list[dict]:
        warnings = []
        if len(data) == 0:
            return warnings
        end_date = data.index[-1]
        for col in data.columns:
            last_valid = data[col].last_valid_index()
            if last_valid is None:
                continue
            gap = (end_date - last_valid).days
            if gap > self.staleness_days:
                warnings.append({
                    "check": "staleness",
                    "column": col,
                    "message": f"{col} last valid data is {gap} days before end of dataset",
                    "severity": "warning",
                })
        return warnings

    def _check_range(self, data: pd.DataFrame) -> list[dict]:
        warnings = []

        if "SP500" in data.columns:
            daily_ret = data["SP500"].pct_change().dropna()
            extreme = daily_ret[daily_ret.abs() > self.sp500_max_daily_return]
            if len(extreme) > 0:
                warnings.append({
                    "check": "range",
                    "column": "SP500",
                    "message": f"SP500 has {len(extreme)} daily returns exceeding |{self.sp500_max_daily_return:.0%}|",
                    "severity": "info",
                })

        if "VIX" in data.columns:
            vix = data["VIX"].dropna()
            vix_low, vix_high = self.vix_range
            out_of_range = vix[(vix < vix_low) | (vix > vix_high)]
            if len(out_of_range) > 0:
                warnings.append({
                    "check": "range",
                    "column": "VIX",
                    "message": f"VIX has {len(out_of_range)} values outside [{vix_low}, {vix_high}]",
                    "severity": "warning",
                })

        for col in ["T10Y", "T3M", "T30Y"]:
            if col in data.columns:
                vals = data[col].dropna()
                y_low, y_high = self.yield_range
                out_of_range = vals[(vals < y_low) | (vals > y_high)]
                if len(out_of_range) > 0:
                    warnings.append({
                        "check": "range",
                        "column": col,
                        "message": f"{col} has {len(out_of_range)} values outside [{y_low}, {y_high}]",
                        "severity": "warning",
                    })

        return warnings

    def _check_completeness(self, data: pd.DataFrame) -> list[dict]:
        warnings = []
        n = len(data)
        if n == 0:
            return warnings
        for col in data.columns:
            nan_pct = data[col].isna().sum() / n
            if nan_pct > self.nan_threshold:
                warnings.append({
                    "check": "completeness",
                    "column": col,
                    "message": f"{col} has {nan_pct:.1%} NaN values (threshold: {self.nan_threshold:.0%})",
                    "severity": "warning",
                })
        return warnings

    def _check_consistency(self, data: pd.DataFrame) -> list[dict]:
        warnings = []
        if "SP500" not in data.columns or len(data) < 2:
            return warnings

        daily_change = data["SP500"].pct_change().dropna().abs()
        jumps = daily_change[daily_change > self.sp500_max_daily_jump]
        if len(jumps) > 0:
            warnings.append({
                "check": "consistency",
                "column": "SP500",
                "message": f"SP500 has {len(jumps)} day-over-day changes exceeding {self.sp500_max_daily_jump:.0%}",
                "severity": "error",
            })

        return warnings
