"""Standalone offline regressions; direct file import avoids all repo conftest/hooks."""
import importlib.util
import sys
import types
import unittest
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SOURCE = Path(__file__).resolve().parents[2]/'backend/services/earnings_intelligence.py'
spec = importlib.util.spec_from_file_location('isolated_earnings', SOURCE)
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)

class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        base = cls(2026, 10, 27, 12, tzinfo=timezone.utc)
        return base.astimezone(tz) if tz else base.replace(tzinfo=None)

class Regressions(unittest.TestCase):
    def summary(self, event=None, dates=(), revenue=(), income=None):
        rows = {'Total Revenue': revenue}
        if income is not None:
            rows['Net Income'] = income
        financials = pd.DataFrame(rows, index=pd.to_datetime(list(dates))).T
        stock = types.SimpleNamespace(calendar={'Earnings Date': event},
            earnings_history=pd.DataFrame(), quarterly_financials=financials,
            analyst_price_targets=None, recommendations=pd.DataFrame(), info={})
        fake = types.ModuleType('yfinance')
        fake.Ticker = lambda ticker: stock
        with patch.dict(sys.modules, {'yfinance': fake}), patch.object(service, 'datetime', Clock):
            result = service.get_earnings_summary('FAKE')
        self.assertNotIn('error', result)
        return result

    def test_scalar_and_list_date_only(self):
        for event in (date(2026, 10, 28), [date(2026, 10, 28)]):
            with self.subTest(event=event):
                r = self.summary(event)
                self.assertEqual(r['days_until_earnings'], 1)
                self.assertEqual(r['earnings_timing_status'], 'DATE_ONLY')
                self.assertIsNone(r['earnings_timezone'])
                self.assertIsNone(r['next_earnings_timestamp'])
                self.assertTrue(r['earnings_imminent'])
                self.assertIn('CALENDAR_DAYS', r['earnings_countdown_basis'])

    def test_aware_timestamp_preserved_and_calendar_day_not_floor(self):
        event = pd.Timestamp('2026-10-28T00:30:00+08:00')
        r = self.summary([event])
        self.assertEqual(r['days_until_earnings'], 1)
        self.assertEqual(r['next_earnings_timestamp'], event.isoformat())
        self.assertEqual(r['earnings_date_type'], 'Timestamp')
        self.assertEqual(r['earnings_countdown_basis'], 'CALENDAR_DAYS_EVENT_TIMEZONE')
        self.assertTrue(r['earnings_imminent'])

    def test_aware_datetime_and_past_same_day(self):
        for hour, imminent in ((11, False), (13, True)):
            r = self.summary(Clock(2026, 10, 27, hour, tzinfo=timezone.utc))
            self.assertEqual(r['days_until_earnings'], 0)
            self.assertEqual(r['earnings_imminent'], imminent)

    def test_naive_datetime_and_timestamp_no_timezone_invention(self):
        for event in (Clock(2026, 10, 28, 14), pd.Timestamp('2026-10-28T14:00')):
            r = self.summary(event)
            self.assertEqual(r['earnings_timing_status'], 'TIMEZONE_UNSPECIFIED')
            self.assertIsNone(r['earnings_timezone'])
            self.assertFalse(r['earnings_imminent'])
            self.assertEqual(r['next_earnings_timestamp'], event.isoformat())

    def test_past_and_outside_window(self):
        for event, days in ((date(2026, 10, 26), -1), (date(2026, 11, 11), 15)):
            r = self.summary(event)
            self.assertEqual(r['days_until_earnings'], days)
            self.assertFalse(r['earnings_imminent'])
        self.assertTrue(self.summary(date(2026, 11, 10))['earnings_imminent'])

    def test_invalid_missing_and_range(self):
        for event, status in ((None, 'MISSING'), (pd.NaT, 'MISSING'), ([], 'MISSING'),
                ('2026-10-28', 'UNSUPPORTED_TYPE'),
                ([date(2026, 10, 28), date(2026, 10, 29)], 'AMBIGUOUS_RANGE')):
            r = self.summary(event)
            self.assertEqual(r['earnings_timing_status'], status)
            self.assertFalse(r['earnings_imminent'])
            self.assertNotIn('days_until_earnings', r)

    def test_full_five_quarters_yoy_and_qoq(self):
        r = self.summary(dates=['2025-09-30','2025-12-31','2026-03-31','2026-06-30','2026-09-30'],
                         revenue=[100,110,120,125,150], income=[10,11,12,15,20])
        self.assertEqual(r['revenue_yoy_growth'], 50)
        self.assertEqual(r['revenue_qoq_growth'], 20)
        self.assertEqual(r['earnings_yoy_growth'], 100)

    def test_four_quarters_never_false_yoy(self):
        r = self.summary(dates=['2025-12-31','2026-03-31','2026-06-30','2026-09-30'], revenue=[100,110,125,150])
        self.assertNotIn('revenue_yoy_growth', r)
        self.assertEqual(r['revenue_qoq_growth'], 20)

    def test_missing_intermediate_quarters_allow_exact_yoy(self):
        r = self.summary(dates=['2026-09-30','2025-09-30','2025-12-31'], revenue=[150,100,110])
        self.assertEqual(r['revenue_yoy_growth'], 50)
        self.assertNotIn('revenue_qoq_growth', r)

    def test_missing_corresponding_period_with_many_rows(self):
        r = self.summary(dates=['2025-03-31','2025-06-30','2025-12-31','2026-03-31','2026-06-30','2026-09-30'], revenue=[70,80,110,120,125,150])
        self.assertNotIn('revenue_yoy_growth', r)

    def test_zero_nan_infinite_and_missing_latest_no_fallback(self):
        for values in ([0,150], [float('nan'),150], [100,float('nan')], [100,float('inf')]):
            r = self.summary(dates=['2025-09-30','2026-09-30'], revenue=values)
            self.assertNotIn('revenue_yoy_growth', r)
            self.assertIn(r['growth_comparisons']['revenue_yoy']['status'], ('ZERO_BASE','NONFINITE_VALUE'))

    def test_52_week_shift_and_duplicate_dates_refused(self):
        for dates in (['2025-09-27','2026-09-26'], ['2025-09-30','2025-09-30','2026-09-30']):
            r = self.summary(dates=dates, revenue=[100] * (len(dates)-1) + [150])
            self.assertNotIn('revenue_yoy_growth', r)
            self.assertEqual(r['growth_comparisons']['revenue_yoy']['status'], 'MISSING_OR_AMBIGUOUS_PERIOD')

    def test_month_end_leap_alignment(self):
        r = self.summary(dates=['2023-02-28','2023-11-30','2024-02-29'], revenue=[100,125,150])
        self.assertEqual(r['revenue_yoy_growth'], 50)
        self.assertEqual(r['revenue_qoq_growth'], 20)

    def test_income_turnaround_and_negative_base(self):
        for income, status in (([-10,20], 'TURNAROUND'), ([-10,-5], 'NONPOSITIVE_BASE'), ([0,20], 'ZERO_BASE')):
            r = self.summary(dates=['2025-09-30','2026-09-30'], revenue=[100,150], income=income)
            self.assertIsNone(r.get('earnings_yoy_growth'))
            self.assertEqual(r['growth_comparisons']['earnings_yoy']['status'], status)
            self.assertEqual(r.get('earnings_turnaround',False), status == 'TURNAROUND')

    def test_legacy_confidence_and_explicit_coverage(self):
        for data, expected in (({},0), ({'beat_rate':75},15),
            ({'beat_rate':100,'avg_surprise_pct':12,'surprise_trend':'improving','revenue_yoy_growth':25,'earnings_yoy_growth':30},75)):
            r = service._generate_earnings_signal(data)
            self.assertEqual(r['confidence'], expected)
            self.assertIsInstance(r['confidence'], int)
            self.assertEqual(r['evidence_coverage'], {'label':'HEURISTIC_SIGNAL_COVERAGE','score':expected})
            self.assertEqual(r['probability_status'], 'NOT_CALIBRATED')

if __name__ == '__main__':
    unittest.main(verbosity=2)
