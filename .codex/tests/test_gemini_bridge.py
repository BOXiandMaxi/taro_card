import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'gemini_bridge.py'
spec = importlib.util.spec_from_file_location('gemini_bridge', MODULE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bridge-test-')
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.css = self.root / 'style.css'
        self.css.write_bytes(b'.card {\r\n  padding: 8px;\r\n}\r\n')

    def report(self, files=None, edits=None, kind='ui'):
        _, snapshots = bridge.prepare(self.root, {'kind': kind, 'task': 'Increase card padding', 'files': files or ['style.css']}, 80000)
        return {'project': str(self.root), 'state': 'proposed', 'kind': kind, 'snapshots': snapshots,
                'proposal': {'summary': 'test', 'edits': edits if edits is not None else [{'path': 'style.css', 'before': 'padding: 8px;', 'after': 'padding: 16px;'}], 'checks': [], 'limitations': []}}

    def test_apply_preserves_bom_line_endings_and_reports_changed_file(self):
        self.css.write_bytes(b'\xef\xbb\xbf.card {\r\n  padding: 8px;\r\n}\r\n')
        report = self.report()
        file = self.root / 'result.json'
        bridge.save_json(file, report)
        result = bridge.apply_report(self.root, file)
        self.assertEqual(self.css.read_bytes(), b'\xef\xbb\xbf.card {\r\n  padding: 16px;\r\n}\r\n')
        self.assertEqual(result['changed_files'], ['style.css'])
        self.assertTrue(result['review_required'])
        with self.assertRaises(bridge.BridgeError):
            bridge.apply_report(self.root, file)

    def test_conflict_keeps_new_user_edits(self):
        report = self.report()
        self.css.write_text('/* user edit */', encoding='utf-8')
        with self.assertRaisesRegex(bridge.BridgeError, 'changed since'):
            bridge.planned_changes(self.root, report)
        self.assertEqual(self.css.read_text(), '/* user edit */')

    def test_outside_scope_or_read_only_file_cannot_be_edited(self):
        other = self.root / 'other.css'
        other.write_text('x', encoding='utf-8')
        for files, name in [(['style.css'], 'other.css'), ([{'path': 'style.css', 'editable': False}, 'other.css'], 'style.css')]:
            report = self.report(files=files, edits=[{'path': name, 'before': 'x', 'after': 'y'}])
            with self.assertRaisesRegex(bridge.BridgeError, 'authorized handoff'):
                bridge.planned_changes(self.root, report)

    def test_path_traversal_credentials_and_protected_paths_are_blocked(self):
        for name in ('../outside.css', '/outside.css', 'C:/outside.css', '.codex/config.toml', '.env', 'x/.env.local', 'node_modules/x.css', 'folder\\file.css', 'a//b.css', './style.css'):
            with self.subTest(name=name), self.assertRaises(bridge.BridgeError):
                bridge.project_file(self.root, name)

    def test_aliases_of_one_file_are_not_two_edit_targets(self):
        # Windows Path equality follows the case-insensitive filesystem.
        if bridge.os.name != 'nt':
            self.skipTest('Windows path aliases')
        with self.assertRaisesRegex(bridge.BridgeError, 'each file once'):
            self.report(files=['style.css', 'STYLE.css'])

    def test_duplicate_match_and_edit_outside_excerpt_fail_before_writes(self):
        self.css.write_text('first\npadding: 8px;\nlast\n', encoding='utf-8')
        report = self.report(files=[{'path': 'style.css', 'start': 1, 'end': 1}])
        with self.assertRaisesRegex(bridge.BridgeError, 'outside the supplied excerpt'):
            bridge.planned_changes(self.root, report)
        self.css.write_text('padding: 8px;\npadding: 8px;\n', encoding='utf-8')
        with self.assertRaisesRegex(bridge.BridgeError, 'ambiguous'):
            bridge.planned_changes(self.root, self.report())

    def test_summary_has_no_write_permission(self):
        with self.assertRaisesRegex(bridge.BridgeError, 'authorized handoff'):
            bridge.planned_changes(self.root, self.report(kind='summary'))

    def test_new_file_requires_explicit_scope_and_empty_before(self):
        report = self.report(files=['new.css'], edits=[{'path': 'new.css', 'before': '', 'after': '.new {}\n'}])
        result = self.root / 'result.json'
        bridge.save_json(result, report)
        bridge.apply_report(self.root, result)
        self.assertEqual((self.root / 'new.css').read_text(), '.new {}\n')
        with self.assertRaises(bridge.BridgeError):
            bridge.planned_changes(self.root, self.report(edits=[{'path': 'style.css', 'before': '', 'after': 'overwrite'}]))

    def test_batch_validation_prevents_partial_changes(self):
        report = self.report(edits=[{'path': 'style.css', 'before': 'padding: 8px;', 'after': 'padding: 16px;'}, {'path': 'missing.css', 'before': '', 'after': 'x'}])
        file = self.root / 'result.json'
        bridge.save_json(file, report)
        before = self.css.read_bytes()
        with self.assertRaises(bridge.BridgeError):
            bridge.apply_report(self.root, file)
        self.assertEqual(self.css.read_bytes(), before)

    def test_write_failure_rolls_back_previous_file(self):
        other = self.root / 'other.css'
        other.write_text('old', encoding='utf-8')
        report = self.report(files=['style.css', 'other.css'], edits=[{'path': 'style.css', 'before': 'padding: 8px;', 'after': 'padding: 16px;'}, {'path': 'other.css', 'before': 'old', 'after': 'new'}])
        file = self.root / 'result.json'
        bridge.save_json(file, report)
        before = self.css.read_bytes()
        real_replace = bridge.os.replace
        def fail_second(src, dst):
            if Path(dst).name == 'other.css':
                raise OSError('simulated disk error')
            return real_replace(src, dst)
        with patch.object(bridge.os, 'replace', side_effect=fail_second), self.assertRaises(OSError):
            bridge.apply_report(self.root, file)
        self.assertEqual(self.css.read_bytes(), before)
        self.assertEqual(other.read_text(), 'old')

    def test_report_commit_failure_rolls_back_edits_and_preserves_report(self):
        file = self.root / 'result.json'
        bridge.save_json(file, self.report())
        original, report_bytes = self.css.read_bytes(), file.read_bytes()
        real_replace = bridge.os.replace
        def fail_report(src, dst):
            if Path(dst) == file:
                raise OSError('simulated report commit failure')
            return real_replace(src, dst)
        with patch.object(bridge.os, 'replace', side_effect=fail_report), self.assertRaises(OSError):
            bridge.apply_report(self.root, file)
        self.assertEqual(self.css.read_bytes(), original)
        self.assertEqual(file.read_bytes(), report_bytes)

    def test_error_waiting_and_malformed_results_are_not_success(self):
        for result in ({'status': 'ERROR', 'error': 'authentication required'}, {'status': 'WAITING'}, {'status': 'SUCCESS', 'response': 'not json'}, {'status': 'SUCCESS', 'structured_output': {'summary': 'incomplete'}}):
            with self.subTest(result=result), self.assertRaises(bridge.BridgeError):
                bridge.parse_result(json.dumps({'event': 'result', 'result': result}))

    def test_structured_stream_returns_usage(self):
        proposal = self.report()['proposal']
        stream = json.dumps({'event': 'init'}) + '\n' + json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'structured_output': proposal, 'usage': {'total_tokens': 123}}})
        parsed, result = bridge.parse_result(stream)
        self.assertEqual(parsed, proposal)
        self.assertEqual(result['usage']['total_tokens'], 123)

    def test_context_budget_and_non_ui_files_fail_before_inference(self):
        with self.assertRaisesRegex(bridge.BridgeError, 'too large'):
            bridge.prepare(self.root, {'task': 'x', 'files': ['style.css']}, 10)
        with self.assertRaisesRegex(bridge.BridgeError, 'UI files'):
            bridge.prepare(self.root, {'task': 'x', 'files': ['migration.sql']}, 80000)


if __name__ == '__main__':
    unittest.main()
