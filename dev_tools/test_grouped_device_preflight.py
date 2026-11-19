import ast
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock


class DevicePreflightTests(unittest.TestCase):
    def setUp(self):
        source = Path('tasks/GroupedAwakening/script_task.py').read_text(encoding='utf-8')
        self.tree = ast.parse(source)
        nodes = [node for node in self.tree.body
                 if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                 and node.name in ('TeamDevicesUnavailable', 'require_team_devices', 'wait_group_room')]
        self.scope = {'GameStuckError': RuntimeError, 'datetime': datetime, 'logger': Mock()}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<preflight>', 'exec'), self.scope)

    def test_returns_exact_devices_in_requested_order(self):
        first = {'name': 'leader', 'is_android_started': True}
        second = {'name': 'member', 'is_android_started': True}
        result = self.scope['require_team_devices']({'2': second, '1': first}, ['leader', 'member'])
        self.assertEqual(result, [first, second])

    def test_reports_all_missing_or_stopped_devices(self):
        with self.assertRaises(self.scope['TeamDevicesUnavailable']) as caught:
            self.scope['require_team_devices'](
                {'1': {'name': 'stopped', 'is_android_started': False}}, ['stopped', 'missing'])
        self.assertIn('stopped', str(caught.exception))
        self.assertIn('missing', str(caught.exception))

    def test_duplicate_names_fail_closed(self):
        info = {'name': 'leader', 'is_android_started': True}
        with self.assertRaises(self.scope['TeamDevicesUnavailable']):
            self.scope['require_team_devices']({'1': info, '2': info.copy()}, ['leader'])

    def test_post_work_requires_only_primary_device(self):
        info = {'name': 'leader', 'is_android_started': True}
        self.assertEqual(self.scope['require_team_devices']({'1': info}, ['leader']), [info])

    def test_unavailable_device_branch_disarms_and_ends_without_retry(self):
        checks = [node for node in ast.walk(self.tree) if isinstance(node, ast.If)
                  and ast.unparse(node.test) == 'isinstance(error, TeamDevicesUnavailable)']
        self.assertEqual(len(checks), 1)
        branch = ast.unparse(checks[0])
        self.assertIn("record['status'] = '等待设备'", branch)
        self.assertIn('scheduler.enable = False', branch)
        self.assertIsInstance(checks[0].body[-1], ast.Raise)

    def test_room_timeout_reforms_once_after_identity_verification(self):
        task = Mock()
        task.wait_room.side_effect = [RuntimeError('timeout'), None]
        player = Mock(expected_name='member')
        player.nickname.return_value = 'member'
        record = {'completed': 5}
        save = Mock()
        self.scope['wait_group_room'](task, [player], 'invitation', record, save)
        self.assertEqual(task.wait_room.call_count, 2)
        task.invite_with_refresh.assert_called_once_with([player], 'invitation', record, save)
        self.assertEqual(record['completed'], 5)
        self.assertEqual(len(record['room_recoveries']), 1)

    def test_active_battle_never_reforms(self):
        task = Mock()
        task.wait_room.side_effect = RuntimeError('timeout')
        player = Mock()
        with self.assertRaises(RuntimeError):
            self.scope['wait_group_room'](task, [player], None,
                                           {'completed': 5, 'battle_in_progress': True}, Mock())
        player.nickname.assert_not_called()
        task.invite_with_refresh.assert_not_called()

    def test_wrong_identity_never_reforms(self):
        task = Mock()
        task.wait_room.side_effect = RuntimeError('timeout')
        player = Mock(expected_name='member')
        player.nickname.return_value = 'other'
        with self.assertRaises(RuntimeError):
            self.scope['wait_group_room'](task, [player], None, {'completed': 5}, Mock())
        task.invite_with_refresh.assert_not_called()

    def test_second_timeout_does_not_loop(self):
        task = Mock()
        task.wait_room.side_effect = RuntimeError('timeout')
        player = Mock(expected_name='member')
        player.nickname.return_value = 'member'
        with self.assertRaises(RuntimeError):
            self.scope['wait_group_room'](task, [player], None, {'completed': 5}, Mock())
        self.assertEqual(task.wait_room.call_count, 2)
        self.assertEqual(task.invite_with_refresh.call_count, 1)

    def test_login_settlement_requires_persisted_win_and_identity(self):
        branches = [node for node in ast.walk(self.tree) if isinstance(node, ast.If)
                    and "pending.get('won', {}).get(WINDOWS[idx]) is True" in ast.unparse(node.test)]
        self.assertEqual(len(branches), 1)
        branch = ast.unparse(branches[0])
        self.assertIn('I_CHECK_LOGIN_FORM', branch)
        self.assertIn('participant.nickname() != group[idx]', branch)
        self.assertIn("pending['settled'][WINDOWS[idx]] = True", branch)


if __name__ == '__main__':
    unittest.main()
