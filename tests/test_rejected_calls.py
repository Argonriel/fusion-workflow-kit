"""Host-rejection cancellation uses disposable state; no Fusion calls occur."""
from pathlib import Path
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fusion_guard'))
import rejected_calls as recovery


class RejectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent, prefix='rejection-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state_root = self.root / 'state'
        self.nonce = 'a' * 32
        self.transport = self.state_root / 'transport' / self.nonce
        self.transport.mkdir(parents=True)
        self.pending = {'status': 'pending', 'kind': 'sketch', 'call_id': 'call-1',
                        'session_id': 'test-session', 'nonce': self.nonce,
                        'created_at': 1.0, 'transport_dir': str(self.transport)}
        self.state = {'pending': copy.deepcopy(self.pending), 'probes': {}, 'document_registry': {'keep': True}}
        self.log = self.root / 'rollout-test-session.jsonl'
        self.event = {'type': 'event_msg', 'payload': {'type': 'item_completed',
            'thread_id': 'test-session', 'started_at_ms': 1000, 'completed_at_ms': 1500,
            'item': {'type': 'McpToolCall', 'id': 'call-1', 'server': 'fusion', 'tool': 'fusion_mcp_execute',
                     'status': 'failed', 'error': {'message': 'This action was rejected due to unacceptable risk.\nReason: Test rejection.\nDo not bypass this rejection.'},
                     'arguments': {'featureType': 'script', 'object': {'readOnly': False,
                         'script': '_fg_report_directory = ' + repr(str(self.transport)) + '\nnonce = ' + repr(self.nonce)}}}}}
        self.write_log()

    def write_log(self):
        self.log.write_text(json.dumps(self.event) + '\n', encoding='utf-8')

    def inspect(self):
        return recovery.inspect_rejection(self.state, self.state_root, self.log, 'call-1')

    def acknowledge(self, confirmed=True):
        return recovery.acknowledge_rejection(self.state, self.state_root, self.log, 'call-1', confirmed,
                                             'The user reviewed this host rejection and approved cancellation of this unexecuted call.')

    def test_inspection_never_changes_state(self):
        original = copy.deepcopy(self.state)
        self.assertEqual(self.inspect()['call_id'], 'call-1')
        self.assertEqual(self.state, original)
        self.assertFalse((self.state_root / 'rejected_calls').exists())

    def test_acknowledgement_preserves_operation_and_existing_reports(self):
        reports = self.state_root / 'reports'
        reports.mkdir()
        original = reports / 'older.json'
        original.write_bytes(b'original evidence')
        audit = json.loads(self.acknowledge().read_text(encoding='utf-8'))
        self.assertIsNone(self.state['pending'])
        self.assertEqual(audit['operation'], self.pending)
        self.assertFalse(audit['model_acceptance'])
        self.assertEqual(original.read_bytes(), b'original evidence')
        self.assertEqual(self.state['document_registry'], {'keep': True})

    def test_confirmation_is_required(self):
        with self.assertRaisesRegex(ValueError, 'Explicit user'):
            self.acknowledge(False)
        self.assertEqual(self.state['pending'], self.pending)

    def test_any_transport_evidence_blocks_cancellation(self):
        (self.transport / 'before.tmp').write_text('partial')
        with self.assertRaisesRegex(ValueError, 'report files'):
            self.acknowledge()
        self.assertEqual(self.state['pending'], self.pending)

    def test_before_or_after_snapshot_blocks_cancellation(self):
        for phase in ('before', 'after'):
            self.state['pending'] = dict(self.pending, **{phase: {'model': 'evidence'}})
            with self.assertRaisesRegex(ValueError, 'Fusion evidence'):
                self.inspect()

    def test_native_tool_error_is_not_host_rejection(self):
        self.event['payload']['item']['error']['message'] = 'RuntimeError: sketch over constrained'
        self.write_log()
        with self.assertRaisesRegex(ValueError, 'explicit host approval rejection'):
            self.inspect()

    def test_result_ambiguous_event_and_running_probe_are_rejected(self):
        self.event['payload']['item']['result'] = {'success': False}
        self.write_log()
        with self.assertRaises(ValueError):
            self.inspect()
        del self.event['payload']['item']['result']
        self.write_log()
        self.log.write_text(self.log.read_text() * 2)
        with self.assertRaisesRegex(ValueError, 'Exactly one'):
            self.inspect()
        self.write_log()
        self.state['probes'] = {'probe': {}}
        with self.assertRaisesRegex(ValueError, 'probe is still running'):
            self.inspect()

    def test_wrong_identity_nonce_and_directory_are_rejected(self):
        original = copy.deepcopy(self.event)
        for field, value in [('id', 'other-call'), ('server', 'other'), ('tool', 'other'), ('status', 'completed')]:
            self.event = copy.deepcopy(original)
            self.event['payload']['item'][field] = value
            self.write_log()
            with self.assertRaises(ValueError):
                self.inspect()
        for script in ["nonce = 'wrong'", '_fg_report_directory = ' + repr(str(self.transport)) + "\nnonce = 'wrong'"]:
            self.event = copy.deepcopy(original)
            self.event['payload']['item']['arguments']['object']['script'] = script
            self.write_log()
            with self.assertRaises(ValueError):
                self.inspect()

    def test_existing_audit_is_never_overwritten(self):
        directory = self.state_root / 'rejected_calls'
        directory.mkdir()
        path = directory / (self.nonce + '.json')
        path.write_text('previous audit', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            self.acknowledge()
        self.assertEqual(path.read_text(), 'previous audit')
        self.assertEqual(self.state['pending'], self.pending)

    def test_management_cli_handles_non_ascii_paths_with_ascii_stdout(self):
        (self.state_root / 'gate.json').write_text(json.dumps(self.state), encoding='utf-8')
        policy = self.root / 'policy.json'
        policy.write_text(json.dumps({'enabled': True, 'auto_undo': False}), encoding='utf-8')
        runtime = Path(__file__).resolve().parents[1] / 'fusion_guard'
        command = ('import sys; from pathlib import Path; sys.path.insert(0, ' + repr(str(runtime)) + '); import manage; '
                   'manage.STATE_ROOT = Path(' + repr(str(self.state_root)) + '); '
                   'manage.POLICY_PATH = Path(' + repr(str(policy)) + '); '
                   'sys.argv = ' + repr(['manage.py', 'acknowledge-rejection', '--call-id', 'call-1',
                       '--event-log', str(self.log), '--confirm-user-review', '--reason',
                       'The user reviewed the rejected call and explicitly approved cancellation.']) + '; manage.main()')
        env = dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0')
        result = subprocess.run([sys.executable, '-B', '-c', command], capture_output=True, text=True, encoding='ascii', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('host_rejected_before_execution', result.stdout)
        self.assertIsNone(json.loads((self.state_root / 'gate.json').read_text(encoding='utf-8'))['pending'])


if __name__ == '__main__':
    unittest.main()
