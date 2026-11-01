"""Whole _store_article execution, isolated DC/NR and real private file writes."""
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
J = Path(__file__).resolve().parents[2]


class StoreArticleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.private = Path(self.tmp.name)
        self.corpus = self.private / 'articles'
        self.ledger = self.private / 'registry'
        self.cfg_calls = []
        self.age = 4.0
        self.writes = []
        self.nr_calls = []
        self.dc = types.ModuleType('backend.services.dowjones_claims')
        self.dc.publisher_of = lambda *a: 'fixture'
        self.dc.text_sha = lambda text: hashlib.sha256(text.encode()).hexdigest()
        self.dc.now_iso = lambda: '2026-11-01T12:00:00+00:00'
        self.nr = types.ModuleType('backend.services.news_registry')
        def grade(row):
            self.nr_calls.append(row)
            return 'first_seen_only'
        self.nr.effective_pit_grade = grade
        backend = types.ModuleType('backend'); backend.__path__ = []
        services = types.ModuleType('backend.services'); services.__path__ = []
        self.modules = patch.dict(sys.modules, {'backend': backend, 'backend.services': services,
            'backend.services.dowjones_claims': self.dc, 'backend.services.news_registry': self.nr})
        self.modules.start()

    def tearDown(self):
        self.modules.stop()
        self.tmp.cleanup()

    def atomic(self, path, record):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(record, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        self.writes.append(path)

    def config(self, name, default):
        self.cfg_calls.append((name, default))
        self.assertEqual(name, 'READER_MAX_ARTICLE_AGE_DAYS')
        return self.age

    def function(self, source=None):
        source = source or J / 'backend/services/web_reader.py'
        tree = ast.parse(source.read_bytes())
        names = {'_store_article', 'registry_source_id', 'definitely_old_date_only'}
        constants = {'_MONTHS', 'DATE_RE', 'NUM_DATE_RE'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names
            or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets)]
        scope = {'Path': Path, 'datetime': datetime, 'timedelta': timedelta, 'timezone': timezone,
            're': re, 'json': json, 'LICENCE': 'PRIVATE_SYNTHETIC_FIXTURE', '_cfg': self.config,
            '_config': types.SimpleNamespace(OPTIMUS_LEDGER_DIR=self.ledger),
            'DG': types.SimpleNamespace(atomic_write_json=self.atomic)}
        # Deliberately no age_days global: the actual function must define it.
        self.assertNotIn('age_days', scope)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), scope)
        return scope['_store_article']

    def article(self, published=None, text='PRIVATE SYNTHETIC ARTICLE', **extra):
        return {'publisher': 'fixture', 'sha': hashlib.sha256(text.encode()).hexdigest(),
            'text': text, 'title': 'fixture', 'url': 'https://example.invalid/fixture',
            'first_seen_utc': '2026-11-01T12:00:00+00:00', 'published_utc': published, **extra}

    def store(self, article):
        result = self.function()(article, self.corpus)
        row = json.loads(Path(result['path']).read_bytes())
        self.assertEqual(len(self.nr_calls), 1)
        self.assertEqual(row['sha'], article['sha'])
        self.assertEqual(row['text'], article['text'])
        self.assertEqual(row['published_utc'], article['published_utc'])
        return result, row

    def test_known_recent_timestamp_writes_article_and_one_private_registry_row(self):
        result, row = self.store(self.article('2026-10-31T12:00:00+00:00'))
        self.assertFalse(row['archive'])
        paths = list(self.ledger.rglob('*.jsonl')); self.assertEqual(len(paths), 1)
        self.assertEqual(len(paths[0].read_text().splitlines()), 1)
        self.assertEqual(result['registry_id'], 'dj_reader_fixture')

    def test_known_past_timestamp_is_archived(self):
        _, row = self.store(self.article('2026-10-01T12:00:00+00:00'))
        self.assertTrue(row['archive'])

    def test_recent_date_only_has_no_invented_publication_instant(self):
        _, row = self.store(self.article(text='October 30, 2026\nPRIVATE SYNTHETIC ARTICLE'))
        self.assertFalse(row['archive']); self.assertIsNone(row['published_utc'])

    def test_past_date_only_archives_without_invented_publication_instant(self):
        _, row = self.store(self.article(text='October 20, 2026\nPRIVATE SYNTHETIC ARTICLE'))
        self.assertTrue(row['archive']); self.assertIsNone(row['published_utc'])

    def test_missing_publication_and_date_still_stores_without_nameerror(self):
        _, row = self.store(self.article())
        self.assertFalse(row['archive']); self.assertIsNone(row['published_utc'])

    def test_malformed_timestamp_retains_original_refusal_fallback(self):
        _, row = self.store(self.article('not-an-instant'))
        self.assertFalse(row['archive'])

    def test_actual_function_reads_configured_age_instead_of_injected_global(self):
        self.age = 1
        _, row = self.store(self.article('2026-10-30T12:00:00+00:00'))
        self.assertTrue(row['archive'])
        self.assertEqual(self.cfg_calls, [('READER_MAX_ARTICLE_AGE_DAYS', 4.0)])

    def test_duplicate_retains_original_files_and_does_not_append_registry_again(self):
        article = self.article('2026-10-31T12:00:00+00:00')
        first, _ = self.store(article)
        before = {p: p.read_bytes() for p in self.private.rglob('*') if p.is_file()}
        second = self.function()(article, self.corpus)
        self.assertTrue(second['duplicate']); self.assertEqual(first['path'], second['path'])
        self.assertEqual(len(self.writes), 1); self.assertEqual(len(self.nr_calls), 1)
        self.assertTrue(all(p.read_bytes() == raw for p, raw in before.items()))




if __name__ == '__main__': unittest.main(verbosity=2)
