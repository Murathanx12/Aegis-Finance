"""Portable cursor-contract tests against the actual AST-extracted stream_rows.

No acquisition-module, psycopg, pyarrow, credential, database or network imports.
"""
import ast
import itertools
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

SOURCE = Path(__file__).resolve().parents[2] / 'scripts' / 'wrds_c05_incremental.py'
NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
definition = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'stream_rows')
namespace = {'uuid4': uuid4, 'utc': lambda: NOW}
exec(compile(ast.Module(body=[definition], type_ignores=[]), str(SOURCE), 'exec'), namespace)
stream_rows = namespace['stream_rows']


class Denied(Exception):
    pgcode = '42501'


class FakeControl:
    def __init__(self, connection):
        self.conn = connection

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.conn.events.append('control_closed')

    def execute(self, query):
        self.conn.events.append(query)
        assert query in ('SET TRANSACTION READ ONLY', "SELECT current_setting('transaction_read_only')")

    def fetchone(self):
        return ('on' if self.conn.readonly else 'off',)


class FakeData:
    def __init__(self, connection):
        self.conn = connection
        self.iterator = iter(connection.rows)
        self.description = None  # Real named cursor: description follows FETCH.
        self.closed = False
        self.requests = []
        self.produced = 0

    def execute(self, query, params):
        self.conn.events.append('declare')
        self.query, self.params = query, params
        assert not self.conn.autocommit
        assert self.conn.settings == {'readonly': True, 'autocommit': False}
        assert self.produced == 0
        if self.conn.execute_error:
            raise self.conn.execute_error

    def fetchmany(self, amount):
        self.conn.events.append('fetch')
        self.requests.append(amount)
        if self.conn.fetch_error:
            raise self.conn.fetch_error
        self.description = [SimpleNamespace(name='value', type_code=25)]
        result = list(itertools.islice(self.iterator, amount))
        self.produced += len(result)
        return result

    def close(self):
        self.closed = True
        self.conn.events.append('data_closed')
        if self.conn.close_error:
            raise self.conn.close_error


class FakeConnection:
    def __init__(self, rows=(), *, readonly=True, execute_error=None,
                 fetch_error=None, close_error=None, rollback_error=None):
        self.rows, self.readonly = rows, readonly
        self.execute_error, self.fetch_error = execute_error, fetch_error
        self.close_error, self.rollback_error = close_error, rollback_error
        self.autocommit = True
        self.events, self.named_options = [], []
        self.data = None
        self.closed = False

    def set_session(self, **kwargs):
        self.settings = kwargs
        self.autocommit = kwargs['autocommit']
        self.events.append('session_readonly_transaction')

    def cursor(self, **kwargs):
        if not kwargs:
            return FakeControl(self)
        self.named_options.append(kwargs)
        assert kwargs['name'].startswith('c05_')
        assert kwargs['scrollable'] is False and kwargs['withhold'] is False
        self.data = FakeData(self)
        return self.data

    def rollback(self):
        self.events.append('rollback')
        if self.rollback_error:
            raise self.rollback_error

    def close(self):
        self.closed = True
        self.events.append('connection_closed')


class StreamingTests(unittest.TestCase):
    def run_select(self, connection, **kwargs):
        return stream_rows(connection, 'SELECT value FROM explicit_cohort WHERE id = %s',
                           (7,), deadline=NOW + timedelta(seconds=1), **kwargs)

    def assert_clean(self, conn):
        self.assertIn('rollback', conn.events)
        self.assertTrue(conn.autocommit)
        if conn.data:
            self.assertTrue(conn.data.closed)
            self.assertLess(conn.events.index('data_closed'), conn.events.index('rollback'))

    def test_named_declare_does_not_materialize_lazy_source(self):
        consumed = []
        def rows():
            for x in range(9):
                consumed.append(x)
                yield (str(x),)
        conn = FakeConnection(rows())
        names, types, result = self.run_select(conn, batch_rows=2)
        self.assertEqual(names, ['value'])
        self.assertEqual(types, {'value': 25})
        self.assertEqual(result, [(str(x),) for x in range(9)])
        self.assertEqual(len(conn.named_options), 1)
        self.assertTrue(all(n <= 2 for n in conn.data.requests))
        self.assertEqual(conn.data.params, (7,))
        self.assertEqual(consumed, list(range(9)))
        self.assert_clean(conn)

    def test_empty_named_result_keeps_description_after_fetch(self):
        conn = FakeConnection()
        self.assertEqual(self.run_select(conn), (['value'], {'value': 25}, []))
        self.assert_clean(conn)

    def test_row_cap_refuses_without_consuming_entire_source(self):
        conn = FakeConnection((('row',) for _ in range(250001)))
        with self.assertRaisesRegex(RuntimeError, 'SMALLER_KEY_RANGE'):
            self.run_select(conn, max_rows=3, batch_rows=2)
        self.assertEqual(conn.data.produced, 4)
        self.assertEqual(conn.data.requests, [2, 2])
        self.assert_clean(conn)

    def test_exact_row_cap_requires_eof_not_silent_truncation(self):
        conn = FakeConnection([('x',)] * 3)
        self.assertEqual(len(self.run_select(conn, max_rows=3, batch_rows=2)[2]), 3)
        self.assertEqual(conn.data.requests, [2, 2, 1])
        self.assert_clean(conn)

    def test_logical_utf8_cap_refuses_and_rolls_back(self):
        conn = FakeConnection([('\u20ac',), ('\u20ac',), ('unused',)])
        with self.assertRaisesRegex(RuntimeError, 'SMALLER_KEY_RANGE'):
            self.run_select(conn, max_logical_bytes=5, batch_rows=1)
        self.assertEqual(conn.data.produced, 2)
        self.assert_clean(conn)

    def test_deadline_before_connection_access(self):
        conn = FakeConnection()
        with self.assertRaises(TimeoutError):
            self.run_select(conn, clock=lambda: NOW + timedelta(seconds=2))
        self.assertEqual(conn.events, [])

    def test_deadline_after_declare_closes_without_fetch(self):
        ticks = iter([NOW, NOW, NOW + timedelta(seconds=2)])
        conn = FakeConnection([('x',)])
        with self.assertRaises(TimeoutError):
            self.run_select(conn, clock=lambda: next(ticks))
        self.assertEqual(conn.data.requests, [])
        self.assert_clean(conn)

    def test_deadline_after_fetch_refuses_rows(self):
        ticks = iter([NOW] * 4 + [NOW + timedelta(seconds=2)])
        conn = FakeConnection([('x',)])
        with self.assertRaises(TimeoutError):
            self.run_select(conn, clock=lambda: next(ticks))
        self.assertEqual(conn.data.produced, 1)
        self.assert_clean(conn)

    def test_readonly_confirmation_refusal_before_named_cursor(self):
        conn = FakeConnection(readonly=False)
        with self.assertRaisesRegex(RuntimeError, 'READ_ONLY_NOT_CONFIRMED'):
            self.run_select(conn)
        self.assertEqual(conn.named_options, [])
        self.assert_clean(conn)

    def test_entitlement_sqlstate_survives_aborted_cursor_close(self):
        denied = Denied('redacted')
        conn = FakeConnection(execute_error=denied, close_error=RuntimeError('aborted transaction'))
        with self.assertRaises(Denied) as caught:
            self.run_select(conn)
        self.assertIs(caught.exception, denied)
        self.assertEqual(caught.exception.pgcode, '42501')
        self.assert_clean(conn)

    def test_fetch_failure_always_cleans_up(self):
        conn = FakeConnection(fetch_error=ValueError('fixture'))
        with self.assertRaises(ValueError):
            self.run_select(conn)
        self.assert_clean(conn)

    def test_close_failure_does_not_skip_rollback(self):
        conn = FakeConnection(close_error=ValueError('fixture'))
        with self.assertRaises(ValueError):
            self.run_select(conn)
        self.assert_clean(conn)

    def test_rollback_failure_closes_connection_and_prevents_reuse(self):
        conn = FakeConnection(rollback_error=ValueError('fixture'))
        with self.assertRaises(ValueError):
            self.run_select(conn)
        self.assertTrue(conn.closed)
        self.assertEqual(conn.events[-1], 'connection_closed')

    def test_separate_readonly_transaction_and_unique_cursor_per_select(self):
        conn = FakeConnection([('x',)])
        self.run_select(conn)
        self.run_select(conn)
        self.assertEqual(conn.events.count('rollback'), 2)
        self.assertNotEqual(conn.named_options[0]['name'], conn.named_options[1]['name'])
        self.assertTrue(conn.autocommit)

    def test_invalid_limits_fail_before_connection_access(self):
        for kwargs in ({'max_rows': 0}, {'max_logical_bytes': 0}, {'batch_rows': 0}):
            conn = FakeConnection()
            with self.assertRaises(ValueError):
                self.run_select(conn, **kwargs)
            self.assertEqual(conn.events, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
