"""Whole-summary JSON boundary with synthetic provider frames; no provider IO."""
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'backend/services/earnings_intelligence.py'


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), value.__dict__)
    return value


class EarningsJSONBoundary(unittest.TestCase):
    def setUp(self):
        self.current = module(SOURCE, 'earnings_json_candidate')

    def summary(self, service, dtype=np.float64):
        history = pd.DataFrame({'epsActual': np.array([2, 1, 1, 3], dtype=dtype),
                               'epsEstimate': np.array([1, 2, 1, 2], dtype=dtype)},
                              index=pd.to_datetime(['2025-12-31', '2026-03-31', '2026-06-30', '2026-09-30']))
        stock = types.SimpleNamespace(
            calendar={'Earnings Date': [date(2026, 11, 2)],
                      'Revenue Average': 12345678901, 'Earnings Average': 1.25},
            earnings_history=history,
            quarterly_financials=pd.DataFrame({'2025-09-30': [100, 10], '2025-12-31': [110, 11],
                '2026-03-31': [120, 12], '2026-06-30': [125, 15], '2026-09-30': [150, 20]},
                index=['Total Revenue', 'Net Income']).set_axis(pd.to_datetime(
                    ['2025-09-30', '2025-12-31', '2026-03-31', '2026-06-30', '2026-09-30']), axis=1),
            analyst_price_targets={'current': 100.25, 'low': 90, 'high': 130.5, 'mean': 115.125, 'median': 116},
            recommendations=pd.DataFrame([{'To Grade': 'Buy'}, {'To Grade': 'Hold'}]),
            info={'trailingPE': 25.125, 'freeCashflow': 12345678901, 'dividendYield': 0.0})
        fake = types.ModuleType('yfinance'); calls = []
        def ticker(value): calls.append(value); return stock
        fake.Ticker = ticker
        with patch.dict(sys.modules, {'yfinance': fake}): result = service.get_earnings_summary('SYNTHETIC')
        self.assertEqual(calls, ['SYNTHETIC']); self.assertNotIn('error', result)
        return result

    def test_whole_summary_FastAPI_and_strict_JSON_and_Response_boundary(self):
        result = self.summary(self.current)
        encoded = jsonable_encoder(result)
        self.assertEqual(json.loads(json.dumps(encoded, allow_nan=False)), encoded)
        self.assertEqual(json.loads(JSONResponse(content=encoded).body), encoded)

    def test_all_beat_flags_are_native_booleans_with_original_comparison_values(self):
        result = self.summary(self.current)
        flags = [r['beat'] for r in result['earnings_surprises']]
        self.assertTrue(all(type(v) is bool for v in flags))
        self.assertEqual(flags, [True, False, False, True])

    def test_realistic_integer_float32_float64_history_dtypes_all_serialize(self):
        for dtype in [np.int64, np.float32, np.float64]:
            result = self.summary(self.current, dtype)
            json.dumps(jsonable_encoder(result), allow_nan=False)
            self.assertTrue(all(type(r['beat']) is bool for r in result['earnings_surprises']))

    def test_normal_calendar_target_and_fundamental_native_JSON_values_are_unchanged(self):
        result = self.summary(self.current)
        self.assertEqual(result['analyst_targets']['current'], 100.25)
        self.assertEqual(result['analyst_targets']['mean'], 115.125)
        self.assertEqual(result['fundamentals']['freeCashflow'], 12345678901.0)
        self.assertEqual(result['fundamentals']['dividendYield'], 0.0)
        self.assertEqual(result['revenue_yoy_growth'], 50.0)
        self.assertEqual(result['earnings_yoy_growth'], 100.0)


if __name__ == '__main__': unittest.main(verbosity=2)
