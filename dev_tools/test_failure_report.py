"""Offline tests; no actual provider calls, emulator actions or config writes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np

from module.handler.failure_report import build_report, redact
from script import Script
from module.exception import GameStuckError


class FailureReportTests(unittest.TestCase):
    def test_local_evidence_redaction_latest_and_dedup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / 'source.log'
            log.write_text('token: secret-value\nordinary log\n', encoding='utf-8')
            notifier = Mock()
            notifier.push.return_value = True
            kwargs = dict(root=root / 'repair', notifier=notifier, secret_values=['secret-value'],
                          images=[np.zeros((8, 8, 3), dtype=np.uint8)], log_path=log)
            first = build_report('oas1', 'RyouToppa', RuntimeError('token=secret-value'), now=10000, **kwargs)
            self.assertEqual(first['notification']['status'], 'request_accepted')
            self.assertFalse(first['notification']['delivery_confirmed'])
            self.assertEqual(len(first['screenshots']), 1)
            self.assertNotIn('secret-value', (Path(first['folder']) / 'traceback.txt').read_text(encoding='utf-8'))
            self.assertNotIn('secret-value', (Path(first['folder']) / 'log_tail.txt').read_text(encoding='utf-8'))
            self.assertNotIn('secret-value', notifier.push.call_args.kwargs['content'])
            second = build_report('oas1', 'RyouToppa', RuntimeError('token=secret-value'), now=10001, **kwargs)
            self.assertEqual(second['notification']['status'], 'deduplicated')
            self.assertNotEqual(first['folder'], second['folder'])
            notifier.push.assert_called_once()
            pointer = json.loads((root / 'repair/latest_oas1.json').read_text(encoding='utf-8'))
            self.assertEqual(pointer['report'], str(Path(second['folder']) / 'report.json'))
            third = build_report('oas1', 'RyouToppa', RuntimeError('token=secret-value'), now=12000, **kwargs)
            self.assertEqual(third['notification']['status'], 'request_accepted')
            self.assertEqual(notifier.push.call_count, 2)

    def test_failed_provider_does_not_suppress_retry(self):
        with tempfile.TemporaryDirectory() as root:
            notifier = Mock()
            notifier.push.side_effect = [RuntimeError('offline'), True]
            a = build_report('oas_leveling', 'Task', ValueError('failed'), root=root, notifier=notifier, now=100)
            b = build_report('oas_leveling', 'Task', ValueError('failed'), root=root, notifier=notifier, now=101)
            self.assertEqual(a['notification']['status'], 'failed')
            self.assertEqual(b['notification']['status'], 'request_accepted')

    def test_redact_json_and_yaml(self):
        self.assertNotIn('abc123', redact('{"token": "abc123"}'))
        self.assertNotIn('abc123', redact('password: abc123'))


class RecoveryBudgetTests(unittest.TestCase):
    def runner(self):
        obj = object.__new__(Script)
        obj.config = Mock()
        obj.config.script.error.handle_error = True
        obj.device = Mock()
        obj.device.image = np.zeros((8, 8, 3), dtype=np.uint8)
        obj._active_stage = 'lock_team'
        obj.exception_handler = Mock()
        obj._restart_game_after_failure = Mock(return_value=True)
        obj._report_final_failure = Mock()
        return obj

    def test_relogin_success_does_not_clear_failure_budget(self):
        obj = self.runner()
        for _ in range(3):
            self.assertFalse(obj._handle_recoverable_failure('RyouToppa', GameStuckError('stuck')))
        self.assertEqual(obj._restart_game_after_failure.call_count, 2)
        obj._report_final_failure.assert_called_once()
        self.assertTrue(obj._script_end_requested)
        self.assertEqual(obj._task_failures['RyouToppa']['attempts'], 3)
        self.assertEqual(len(obj._failure_images['RyouToppa']), 3)

    def test_run_routes_task_errors_and_returns_true_on_real_completion(self):
        from unittest.mock import patch
        from module.exception import TaskEnd
        obj = self.runner()
        obj.config_name = 'test'
        obj.instance_guard = None
        obj._try_acquire_queue_token = Mock(return_value=True)
        instance = Mock()
        instance.stage = 'lock_team'
        instance.run.side_effect = [GameStuckError('stuck')] * 3 + [TaskEnd()]
        module = Mock()
        module.ScriptTask.return_value = instance
        with patch('script.load_module', return_value=module):
            for _ in range(3):
                self.assertFalse(obj.run('RyouToppa'))
            self.assertTrue(obj.run('RyouToppa'))
        self.assertEqual(obj._restart_game_after_failure.call_count, 2)
        obj._report_final_failure.assert_called_once()

    def test_normal_return_is_task_success(self):
        from unittest.mock import patch
        obj = self.runner()
        obj.instance_guard = None
        obj._try_acquire_queue_token = Mock(return_value=True)
        module = Mock()
        module.ScriptTask.return_value.run.return_value = None
        with patch('script.load_module', return_value=module):
            self.assertTrue(obj.run('Task'))
        obj._restart_game_after_failure.assert_not_called()
        obj._report_final_failure.assert_not_called()

    def test_disabled_recovery_reports_without_restart(self):
        obj = self.runner()
        obj.config.script.error.handle_error = False
        obj._handle_recoverable_failure('Task', GameStuckError('stuck'))
        obj._restart_game_after_failure.assert_not_called()
        obj._report_final_failure.assert_called_once()


if __name__ == '__main__':
    unittest.main()
