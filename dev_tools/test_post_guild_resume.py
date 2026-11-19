"""Checkpoint selection and spend guards; no device actions."""
import json
import ast
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.GroupedAwakening.post_guild import finish_all, PostGuildSubmissionUncertain, return_to_courtyard


class PostGuildResumeTests(unittest.TestCase):
    def test_stopped_game_is_started_before_courtyard_check(self):
        task = Mock()
        task.device.app_is_running.return_value = False
        task.appear.return_value = True
        with patch('tasks.Restart.login.LoginHandler') as login, \
                patch('tasks.GroupedAwakening.post_guild._words', return_value=''), \
                patch('tasks.GroupedAwakening.post_guild.dismiss_received_fragment', return_value=False), \
                patch('tasks.GroupedAwakening.post_guild.dismiss_new_server_promotion', return_value=False):
            return_to_courtyard(task)
        task.device.app_start.assert_called_once_with()
        login.return_value._app_handle_login.assert_called_once_with()
        task.device.app_stop.assert_not_called()

    def test_recent_post_only_batch_survives_midnight(self):
        source = Path('tasks/GroupedAwakening/script_task.py').read_text(encoding='utf-8')
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == 'resumable_post_work')
        scope = dict(datetime=datetime, timedelta=timedelta)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<post-resume>', 'exec'), scope)
        check = scope['resumable_post_work']
        record = dict(status='出错', updated_at='2026-11-17T23:57:04',
                      failure=dict(stage='觉醒后完成寮任务与捐赠'),
                      groups=[dict(completed=15) for _ in range(4)])
        self.assertTrue(check(record, datetime(2026, 11, 18, 0, 8)))
        self.assertFalse(check(record, datetime(2026, 11, 18, 13)))
        record['groups'][0]['completed'] = 14
        self.assertFalse(check(record, datetime(2026, 11, 18, 0, 8)))

    def test_cross_midnight_preserves_completed_and_pending_accounts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'post_guild_2026-11-17.json'
            done = dict(verified_at='2026-11-17T23:00:00', guild_tasks='30/30',
                        jade_status='已确认奖励', jade_donated=100, courtyard_status='完成')
            uncertain = dict(guild_tasks='30/30', jade_status='待核对已提交',
                             jade_before=271, courtyard_status='完成')
            path.write_text(json.dumps(dict(date='2026-11-17', accounts={
                'done': done, 'pending': uncertain})), encoding='utf-8')
            accounts = [SimpleNamespace(character=name) for name in ('done', 'pending', 'remaining')]
            config = Mock()
            config.config_name = 'oas_leveling'
            task = Mock()
            def complete(task, name, data, entry, save):
                entry.update(done)
                save()
            with patch('tasks.GroupedAwakening.post_guild.Path', return_value=root), \
                 patch('tasks.GroupedAwakening.post_guild.select_accounts', return_value=accounts), \
                 patch('tasks.GroupedAwakening.post_guild.return_to_courtyard'), \
                 patch('tasks.GroupedAwakening.post_guild.FindJadeTask.switch_support_account', return_value=True) as switch, \
                 patch('tasks.GroupedAwakening.post_guild.finish_account', side_effect=complete) as finish:
                with self.assertRaises(PostGuildSubmissionUncertain):
                    finish_all(task, config, '2026-11-17')
            switch.assert_called_once_with(task, accounts[2])
            self.assertEqual(finish.call_args.args[1], 'remaining')
            result = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(result['accounts']['done'], done)
            self.assertEqual(result['accounts']['pending'], uncertain)
            self.assertEqual(result['accounts']['remaining'], done)
            self.assertEqual(result['status'], '待核对')
            self.assertEqual(result['pending_accounts'], ['pending'])

    def test_rejects_invalid_ledger_date_before_device_use(self):
        task = Mock()
        with self.assertRaises(ValueError):
            finish_all(task, Mock(), '../bad')
        task.step.assert_not_called()


if __name__ == '__main__':
    unittest.main()
