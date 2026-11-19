import ast
import unittest
from pathlib import Path


class DevicePreflightTests(unittest.TestCase):
    def setUp(self):
        source = Path('tasks/GroupedAwakening/script_task.py').read_text(encoding='utf-8')
        self.tree = ast.parse(source)
        nodes = [node for node in self.tree.body
                 if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                 and node.name in ('TeamDevicesUnavailable', 'require_team_devices')]
        self.scope = {'GameStuckError': RuntimeError}
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


if __name__ == '__main__':
    unittest.main()
