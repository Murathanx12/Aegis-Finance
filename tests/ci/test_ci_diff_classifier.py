"""Offline classifier regressions, including real Git rename and merge trees."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('classifier', Path(__file__).resolve().parents[2] / 'scripts/ci_diff_classifier.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class ClassifierTests(unittest.TestCase):
    def test_allowlist_and_unknowns(self):
        for path in ['backend/services/a.py', 'backend/tests/a.py', 'scripts/a.py', 'docs/a.md', 'backend/data/public_receipts/a.json']:
            with self.subTest(path=path):
                self.assertEqual(c.classify([path], 'pull_request'), (False, True))
        for path in ['frontend/src/a.ts', 'package.json', 'package-lock.json', '.npmrc', '.github/workflows/ci.yml', 'shared/a.ts', 'backend/config.py', 'docs/a.json', 'scripts/a.sh', 'backend/services/a.ts', 'backend/services/../a.py', 'backend/services//a.py', 'backend\\services\\a.py']:
            with self.subTest(path=path):
                self.assertEqual(c.classify(['backend/tests/a.py', path], 'pull_request'), (False, False))
        self.assertEqual(c.classify([], 'push'), (False, False))

    def test_receipts_preserve_push_only_backend_skip(self):
        paths = ['backend/data/public_receipts/a.json']
        self.assertEqual(c.classify(paths, 'push'), (True, True))
        self.assertEqual(c.classify(paths, 'pull_request'), (False, True))
        self.assertEqual(c.classify(paths + ['backend/tests/a.py'], 'push'), (False, True))
        self.assertEqual(c.classify(paths + ['frontend/a.ts'], 'push'), (False, False))

    def test_unknown_events_refs_and_git_errors(self):
        for event, ref in [('push', ''), ('push', '0' * 40), ('push', 'x' * 40), ('merge_group', 'a' * 40)]:
            self.assertEqual(c.classify_event(event, ref), (False, False))
        for error in [OSError(), subprocess.CalledProcessError(1, 'git')]:
            with patch.object(c, 'git', side_effect=error):
                self.assertEqual(c.classify_event('push', 'a' * 40), (False, False))
        for raw in [b'', b'backend/services/a.py', b'backend/services/\xff.py\0']:
            with patch.object(c, 'git', return_value=raw):
                self.assertEqual(c.classify_event('push', 'a' * 40), (False, False))

    def test_cli_outputs_explicit_full_ci_on_unknown_event(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'output'
            env = dict(os.environ, EVENT='unknown', GITHUB_OUTPUT=str(output))
            subprocess.run([sys.executable, str(Path(c.__file__).resolve())], env=env, check=True, capture_output=True)
            self.assertEqual(output.read_text(), 'receipts_only=false\nfrontend_unaffected=false\ndocs_only=false\nneed_backend=true\n')


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.getcwd()
        os.chdir(self.temp.name)
        self.addCleanup(self.restore)
        self.git('init', '-b', 'main')
        self.git('config', 'user.email', 'ci@example.invalid')
        self.git('config', 'user.name', 'CI test')
        self.write('frontend/a.ts', 'export {}')
        self.write('backend/services/a.py', '# original')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD')

    def restore(self):
        os.chdir(self.old)
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', *args], stderr=subprocess.PIPE).decode().strip()

    def write(self, name, text):
        p = Path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-m', 'fixture')

    def test_push_multicommit_and_missing_history(self):
        self.write('frontend/a.ts', 'export const x=1')
        self.commit()
        self.write('backend/services/a.py', '# changed')
        self.commit()
        self.assertEqual(c.classify_event('push', self.base), (False, False))
        self.assertEqual(c.classify_event('push', 'a' * 40), (False, False))

    def test_rename_out_of_frontend_and_deletion(self):
        self.git('mv', 'frontend/a.ts', 'backend/services/renamed.py')
        self.commit()
        self.assertEqual(c.classify_event('push', self.base), (False, False))
        self.git('rm', 'backend/services/a.py')
        prev = self.git('rev-parse', 'HEAD')
        self.commit()
        self.assertEqual(c.classify_event('push', prev), (False, True))

    def test_pr_merge_tree_includes_base_drift(self):
        self.git('checkout', '-b', 'pr')
        self.write('backend/services/a.py', '# PR')
        self.commit()
        head = self.git('rev-parse', 'HEAD')
        self.git('checkout', 'main')
        self.write('frontend/a.ts', 'export const base=1')
        self.commit()
        base = self.git('rev-parse', 'HEAD')
        self.git('merge', '--no-ff', 'pr', '-m', 'synthetic merge')
        self.assertEqual(c.classify_event('pull_request', base=base, head=head), (False, False))
        self.assertEqual(c.classify_event('pull_request', base=base, head='a' * 40), (False, False))

    def test_pr_backend_only(self):
        self.git('checkout', '-b', 'pr')
        self.write('backend/services/a.py', '# PR')
        self.commit()
        head = self.git('rev-parse', 'HEAD')
        self.git('checkout', 'main')
        self.git('merge', '--no-ff', 'pr', '-m', 'synthetic merge')
        self.assertEqual(c.classify_event('pull_request', base=self.base, head=head), (False, True))


class DocsOnlyTests(GitTests):
    def test_docs_only_push_and_pr_cli(self):
        self.git('checkout', '-b', 'docs-pr')
        self.write('docs/nested/note.md', '# note')
        self.commit()
        head = self.git('rev-parse', 'HEAD')
        self.assertTrue(c.docs_only_event('push', self.base))
        self.git('checkout', 'main')
        self.git('merge', '--no-ff', 'docs-pr', '-m', 'merge docs')
        self.assertTrue(c.docs_only_event('pull_request', base=self.base, head=head))
        for event in ('push', 'pull_request'):
            with tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / 'output'
                env = dict(os.environ, EVENT=event, BEFORE=self.base,
                           BASE=self.base, PR_HEAD=head, GITHUB_OUTPUT=str(output))
                subprocess.run([sys.executable, str(Path(c.__file__).resolve())],
                               env=env, check=True, capture_output=True)
                self.assertIn('docs_only=true\nneed_backend=false\n', output.read_text())
        self.write('docs/nested/note.md', '# edited')
        self.commit()
        self.assertTrue(c.docs_only_event('push', head))

    def test_mixed_and_this_changeset_force_full_checks(self):
        self.write('docs/note.md', '# docs')
        for path in ('backend/services/a.py', 'README.md', 'shared/new.md',
                     '.github/workflows/ci.yml', 'scripts/ci_diff_classifier.py',
                     'tests/ci/test_ci_diff_classifier.py', 'docs/config.json'):
            with self.subTest(path=path):
                self.write(path, '# changed')
                self.commit()
                self.assertFalse(c.docs_only_event('push', self.base))
                self.assertEqual(c.classify_event('push', self.base), (False, False)
                                 if path != 'backend/services/a.py' else (False, True))

    def test_docs_rename_delete_and_type_change_run_backend(self):
        self.write('docs/original.md', '# docs')
        self.commit()
        before = self.git('rev-parse', 'HEAD')
        self.git('mv', 'docs/original.md', 'docs/renamed.md')
        self.commit()
        self.assertFalse(c.docs_only_event('push', before))
        before = self.git('rev-parse', 'HEAD')
        self.git('rm', 'docs/renamed.md')
        self.commit()
        self.assertFalse(c.docs_only_event('push', before))
        self.git('update-index', '--add', '--cacheinfo',
                 '120000,' + self.git('rev-parse', 'HEAD:backend/services/a.py') + ',docs/link.md')
        self.git('commit', '-m', 'symlink fixture')
        self.assertFalse(c.docs_only_event('push', before))

    def test_docs_pr_base_drift_and_missing_refs(self):
        self.git('checkout', '-b', 'docs-pr')
        self.write('docs/note.md', '# PR docs')
        self.commit()
        head = self.git('rev-parse', 'HEAD')
        self.git('checkout', 'main')
        self.write('backend/services/a.py', '# base drift')
        self.commit()
        base = self.git('rev-parse', 'HEAD')
        self.git('merge', '--no-ff', 'docs-pr', '-m', 'merge')
        self.assertFalse(c.docs_only_event('pull_request', base=base, head=head))
        self.assertFalse(c.docs_only_event('pull_request', base=base, head='a' * 40))
        self.assertFalse(c.docs_only_event('push', 'a' * 40))
        self.assertFalse(c.docs_only_event('push', self.git('rev-parse', 'HEAD')))

    def test_docs_unknown_errors_and_path_evasion(self):
        for event, kwargs in [('push', {}), ('push', {'before': '0' * 40}),
                              ('push', {'before': '--help'}), ('workflow_dispatch', {}),
                              ('pull_request', {'base': 'a' * 40})]:
            self.assertFalse(c.docs_only_event(event, **kwargs))
        for error in (OSError(), subprocess.CalledProcessError(1, 'git'), UnicodeError()):
            with patch.object(c, 'git', side_effect=error):
                self.assertFalse(c.docs_only_event('push', 'a' * 40))
        metadata = b':100644 100644 abc def M\0'
        for path in (b'docs/../code.md', b'docs//a.md', b'/docs/a.md',
                     b'docs/./a.md', b'docs\\a.md', b'docs/a.MD', b'docs/a.md/evil',
                     b'docs/a.md\n', b'docs/\xff.md', b'docs.md', b'Docs/a.md'):
            with self.subTest(path=path), patch.object(c, 'git', return_value=metadata + path + b'\0'):
                self.assertFalse(c.docs_only_event('push', 'a' * 40))
        for raw in (b'', b'broken', b'broken\0', b':100644 100755 abc def M\0docs/a.md\0',
                    b':120000 100644 abc def T\0docs/a.md\0'):
            with patch.object(c, 'git', return_value=raw):
                self.assertFalse(c.docs_only_event('push', 'a' * 40))


class WorkflowTests(unittest.TestCase):
    def test_backend_safe_default_and_frontend_preserved(self):
        workflow = (Path(c.__file__).resolve().parents[1] / '.github/workflows/ci.yml').read_text()
        self.assertIn("needs.changes.result != 'success' || needs.changes.outputs.need_backend != 'false'", workflow)
        self.assertIn("needs.changes.result != 'success' || needs.changes.outputs.frontend_unaffected != 'true'", workflow)
        self.assertIn('need_backend: ${{ steps.diff.outputs.need_backend }}', workflow)
        self.assertIn('docs_only: ${{ steps.diff.outputs.docs_only }}', workflow)


if __name__ == '__main__':
    unittest.main()
