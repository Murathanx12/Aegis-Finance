"""Synthetic actual-caller replay; no scheduler, pytest/conftest or runtime data."""
import copy
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
os.environ['AEGIS_IGNORE_DOTENV'] = '1'
os.environ['AEGIS_REPO_ROOT'] = str(ROOT)
FORBIDDEN = []


def guard(event, args):
    blocked = (event.startswith(('socket.', 'sqlite3.', 'subprocess.')) or event in
               {'os.system', 'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir',
                'os.truncate', 'os.chmod', 'os.link', 'os.symlink', 'os.startfile', 'os.spawn'})
    if event == 'open':
        path, mode, flags = args
        parts = str(path).lower().replace('/', '\\').split('\\')
        blocked = (any(c in str(mode) for c in 'wax+') or
                   bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)) or
                   ('aegis-finance' in parts and '.venv' not in parts))
    if blocked:
        FORBIDDEN.append(event)
        raise AssertionError('read-only caller replay rejected ' + event)


sys.addaudithook(guard)
from backend.services import decision_contract as DC
from scripts import daily_pass as DP

NOW = datetime(2030, 1, 4, 1, 2, 3, tzinfo=timezone.utc)
CTX = {'date': '2030-01-02', 'date_obj': date(2030, 1, 2)}
CAUSE = 'missing explicit round-trip costs; refused rather than price at zero'


class RefusalOutputTests(unittest.TestCase):
    def setUp(self):
        self.fake_delivery = ModuleType('backend.services.telegram_bridge')
        self.fake_delivery.send_owner_once = Mock(side_effect=AssertionError('delivery'))
        self.fake_delivery.send_owner = Mock(side_effect=AssertionError('delivery'))
        self.enterContext(patch.dict(sys.modules, {'backend.services.telegram_bridge': self.fake_delivery}))
        self.enterContext(patch.object(DC, '_capital_from_broker', side_effect=AssertionError('broker')))
        self.enterContext(patch.object(DC, 'write_contracts', side_effect=AssertionError('contract write')))
        self.enterContext(patch.object(DC, 'summarise_for_reader', side_effect=AssertionError('wrong offline renderer')))
        self.latest = self.enterContext(patch.object(DC, 'latest', side_effect=AssertionError('latest')))
        self.ledger = self.enterContext(patch.object(DP, 'record_decided', side_effect=AssertionError('ledger')))
        self.build = self.enterContext(patch.object(DP, 'build_decision_contracts', side_effect=DC.CostModelRefused(CAUSE)))
        self.enterContext(patch.object(DP.time, 'time', return_value=100.0))
        self.enterContext(patch.object(DP, '_now', return_value=NOW.isoformat()))

    def tearDown(self):
        self.fake_delivery.send_owner_once.assert_not_called()
        self.fake_delivery.send_owner.assert_not_called()
        self.assertEqual(FORBIDDEN, [])

    def refusal(self, ctx=None, clock=lambda: NOW):
        result = DP.step_decision_contract(copy.deepcopy(CTX if ctx is None else ctx), observed_clock=clock)
        self.ledger.assert_not_called()
        self.latest.assert_not_called()
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(result['rows'], 0)  # No fabricated successfully built candidate count.
        self.assertEqual(result['refusals'], ['CostModelRefused: ' + CAUSE])
        self.assertIsNone(result['receipt'])
        self.assertFalse(result['runtime_requirement_fulfilled'])
        return result

    def test_typed_refusal_has_useful_structured_assessment_and_original_failure(self):
        result = self.refusal()
        row = result['provisional_decision']
        self.build.assert_called_once_with(asof=CTX['date_obj'])
        self.assertEqual(row['decision_status'], 'PROVISIONAL')
        self.assertEqual(row['original_failure']['type'], 'CostModelRefused')
        self.assertIn(CAUSE, row['original_failure']['cause'])
        self.assertEqual(row['action'], 'NO_NEW_BET')
        self.assertEqual(row['operational_action'], 'NO_AUTOMATED_CHANGE')
        self.assertEqual(row['investment_action'], 'UNRESOLVED')
        self.assertFalse(row['orders_authorized'])
        for field in ('horizon', 'available_evidence', 'missing_evidence', 'conditional_risk',
                      'rationale', 'uncertainty', 'invalidating_evidence', 'update_trigger'):
            self.assertTrue(row[field])
        for text in ('CostModelRefused', 'NO_NEW_BET', 'NO_AUTOMATED_CHANGE', 'Update:', 'Delivery not attempted'):
            self.assertIn(text, result['answer'])
        json.dumps(result, allow_nan=False)

    def test_clock_is_injected_once_and_context_date_never_becomes_historical_asof(self):
        clock = Mock(return_value=NOW)
        row = self.refusal(clock=clock)['provisional_decision']
        clock.assert_called_once_with()
        self.assertEqual(row['asof'], NOW.isoformat())
        self.assertEqual(row['context_cutoff']['date'], CTX['date'])
        self.assertIsNone(row['context_cutoff']['instant'])
        self.assertNotIn(CTX['date'], row['asof'])

    def test_default_observation_is_actual_aware_clock(self):
        before = datetime.now(timezone.utc)
        row = self.refusal(clock=None)['provisional_decision']
        after = datetime.now(timezone.utc)
        self.assertLessEqual(before, datetime.fromisoformat(row['asof']))
        self.assertLessEqual(datetime.fromisoformat(row['asof']), after)

    def test_offset_clock_normalizes_to_utc(self):
        observed = datetime.fromisoformat('2030-01-04T09:02:03+08:00')
        self.assertEqual(self.refusal(clock=lambda: observed)['provisional_decision']['asof'], NOW.isoformat())

    def test_invalid_observation_cannot_erase_original_refusal_or_fabricate_time(self):
        for value in (date(2030, 1, 4), '2030-01-04', datetime(2030, 1, 4), None):
            with self.subTest(value=value):
                row = self.refusal(clock=lambda: value)['provisional_decision']
                self.assertIsNone(row['asof'])
                self.assertEqual(row['asof_basis'], 'UNKNOWN_INVALID_OBSERVATION_CLOCK')
                self.assertEqual(row['decision_status'], 'PROVISIONAL_UNTIMED')
                self.assertTrue(row['data_quality_warnings'])
        row = self.refusal(clock=Mock(side_effect=RuntimeError('clock unavailable')))['provisional_decision']
        self.assertIsNone(row['asof'])

    def test_no_fabricated_market_exposure_probability_or_unit_risk(self):
        row = self.refusal()['provisional_decision']
        for field in ('price_usd', 'exposure_usd', 'equity_usd', 'estimated_probability'):
            self.assertIsNone(row[field])
        self.assertEqual(row['probability_type'], 'NOT_ESTIMATED')
        for field in ('assumption', 'loss_per_unit_exposure', 'loss_usd'):
            self.assertIsNone(row['conditional_risk'][field])
        self.assertEqual(row['conditional_risk']['scenarios'], [])
        self.assertEqual(row['available_evidence'][0]['kind'], 'OPERATIONAL_FAILURE_ONLY')

    def test_supplied_mandate_preserved_without_compliance_certification(self):
        ctx = {**CTX, 'mandate': {'policy_id': 'synthetic-existing', 'limits': {'owner_rule': 'preserve'}, 'status': 'caller assertion'}}
        before = copy.deepcopy(ctx)
        result = DP.step_decision_contract(ctx, observed_clock=lambda: NOW)
        row = result['provisional_decision']
        self.assertEqual(ctx, before)
        self.assertEqual(row['mandate'], ctx['mandate'])
        self.assertIsNot(row['mandate'], ctx['mandate'])
        self.assertEqual(row['mandate_status'], 'SUPPLIED_UNVERIFIED')
        self.assertEqual(row['mandate_compliance'], 'NOT_ASSESSED')
        row['mandate']['limits']['owner_rule'] = 'changed output'
        self.assertEqual(ctx, before)
        self.ledger.assert_not_called()
        self.latest.assert_not_called()

    def test_absent_or_malformed_mandate_gets_no_default_certification(self):
        self.assertIsNone(self.refusal()['provisional_decision']['mandate'])
        for invalid in (None, [], 'text', {'limit': float('nan')}):
            row = self.refusal({**CTX, 'mandate': invalid})['provisional_decision']
            self.assertIsNone(row['mandate'])
            self.assertEqual(row['mandate_status'], 'INVALID')

    def test_delivery_receipt_is_explicitly_absent(self):
        self.assertEqual(self.refusal()['provisional_decision']['delivery_status'],
                         {'status': 'NOT_ATTEMPTED', 'receipt': None})

    def test_context_claims_cannot_inject_fake_market_or_historical_time(self):
        row = self.refusal({**CTX, 'asof': '2000-01-01T00:00:00Z', 'equity_usd': 1e9,
                            'price_usd': 100, 'conditional_loss_fraction': 0.0})['provisional_decision']
        self.assertEqual(row['asof'], NOW.isoformat())
        self.assertIsNone(row['equity_usd'])
        self.assertIsNone(row['price_usd'])
        self.assertIsNone(row['conditional_risk']['loss_per_unit_exposure'])

    def test_iso_date_cutoff_argument_is_preserved_for_builder(self):
        self.refusal({**CTX, 'date_obj': CTX['date']})
        self.build.assert_called_once_with(asof=CTX['date'])

    def test_malformed_default_context_is_explicit_error_without_builder_or_writes(self):
        for ctx in ({}, {'date': CTX['date']}, {**CTX, 'date': 'bad'},
                    {**CTX, 'date_obj': date(2030, 1, 3)}, {**CTX, 'date_obj': NOW}):
            with self.subTest(ctx=ctx):
                result = DP.step_decision_contract(ctx)
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['decision_status'], 'UNAVAILABLE')
                self.assertIn('INVALID_DECISION_CONTEXT', result['refusals'][0])
        self.build.assert_not_called()
        self.ledger.assert_not_called()
        self.latest.assert_not_called()
        for ctx in (None, [], 'text'):
            with self.assertRaisesRegex(ValueError, 'context must be an object'):
                DP.step_decision_contract(ctx)

    def test_unrelated_builder_error_is_not_relabeled_as_cost_refusal(self):
        self.build.side_effect = RuntimeError('synthetic other error')
        with self.assertRaisesRegex(RuntimeError, 'synthetic other error'):
            DP.step_decision_contract(CTX)
        self.latest.assert_not_called()
        self.ledger.assert_not_called()

    def test_successful_outputs_remain_exact_for_all_direction_cases(self):
        blob = {'notes': ['existing note'], 'path': 'synthetic:existing-receipt',
                'count_by_refusal_class': {'existing': 3},
                'count_by_terminal_state': {'existing': 4},
                'worst_case_largest_admissible_book': {'existing': 'unchanged'},
                'mandate': {'line': 'existing mandate line'},
                'candidate_set': {'line': 'existing candidates line'}}
        ledger_result = {'existing': 'ledger result'}
        self.build.side_effect = None
        self.latest.side_effect = None
        self.latest.return_value = blob
        self.ledger.side_effect = None
        self.ledger.return_value = ledger_result
        for directions in ([], ['BUY'], ['WATCH'], ['REFUSED'], ['PROBE'], ['BUY', 'WATCH', 'REFUSED', 'PROBE']):
            rows = [{'direction': d, 'decision_id': str(i)} for i,d in enumerate(directions)]
            self.build.return_value = rows
            with self.subTest(directions=directions):
                clock = Mock(side_effect=AssertionError('success must not observe fallback clock'))
                result = DP.step_decision_contract(CTX, observed_clock=clock)
                expected_counts = dict.fromkeys(DC.DIRECTIONS, 0)
                for direction in directions:
                    expected_counts[direction] += 1
                expected = {'step': 'decision_contract', 'status': 'ok' if set(directions)&{'BUY','WATCH'} else 'nothing_to_do',
                    'utc': NOW.isoformat(), 'rows': len(rows), 'seconds': 0.0,
                    'refusals': ['existing note'], 'count_by_direction': expected_counts,
                    'count_by_refusal_class': blob['count_by_refusal_class'],
                    'count_by_terminal_state': blob['count_by_terminal_state'],
                    'worst_case_largest_admissible_book': blob['worst_case_largest_admissible_book'],
                    'mandate_line': 'existing mandate line', 'candidate_set_line': 'existing candidates line',
                    'licence': DC.LICENCE, 'ledger': ledger_result, 'receipt': 'synthetic:existing-receipt'}
                self.assertEqual(result, expected)
                clock.assert_not_called()
                self.ledger.assert_called_with(rows, CTX['date'])
                self.latest.assert_called_with(CTX['date'])

    def test_success_with_absent_latest_retains_prior_empty_blob_output(self):
        self.build.side_effect = None
        self.build.return_value = []
        self.latest.side_effect = None
        self.latest.return_value = None
        self.ledger.side_effect = None
        self.ledger.return_value = {}
        result = DP.step_decision_contract(CTX)
        self.assertEqual(result['status'], 'nothing_to_do')
        self.assertEqual(result['refusals'], [])
        for key in ('receipt', 'mandate_line', 'candidate_set_line', 'count_by_terminal_state'):
            self.assertIsNone(result[key])
        self.assertNotIn('provisional_decision', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
