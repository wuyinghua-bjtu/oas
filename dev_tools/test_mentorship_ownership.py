import io
import json
import unittest
from unittest.mock import AsyncMock, patch

from tasks.Mentorship.ownership import verify_apprentice_idle, acquire_apprentice


class OwnershipTests(unittest.TestCase):
    def acquire(self, marker, states):
        def read(path, **kwargs):
            if path.name == 'deploy.yaml':
                return 'Deploy:\n  Webui:\n    WebuiPort: 22288\n'
            return json.dumps({'running_task': marker})
        with patch('tasks.Mentorship.ownership.Path.read_text', read), \
             patch('tasks.Mentorship.ownership.worker_state', AsyncMock(side_effect=states)), \
             patch('tasks.Mentorship.ownership._worker_action') as action, \
             patch('tasks.Mentorship.ownership.verify_apprentice_idle') as verify, \
             patch('tasks.Mentorship.ownership.time.sleep'):
            result = acquire_apprentice('oas_leveling', 'oas1')
            return result, action, verify

    def test_idle_listener_is_paused_and_verified(self):
        result, action, verify = self.acquire('', [1, 0])
        self.assertTrue(result)
        action.assert_called_once_with(22288, 'oas_leveling', 'stop')
        verify.assert_called_once_with('oas_leveling', 'oas1')

    def test_stopped_worker_needs_no_pause(self):
        result, action, verify = self.acquire('old', [0])
        self.assertFalse(result)
        action.assert_not_called()
        verify.assert_called_once()

    def test_busy_apprentice_is_never_stopped(self):
        with patch('tasks.Mentorship.ownership._worker_action') as action:
            with self.assertRaisesRegex(RuntimeError, '正在执行'):
                self.acquire('FindJade', [1])
            action.assert_not_called()

    def test_failed_exclusive_check_restores_listener(self):
        def read(path, **kwargs):
            if path.name == 'deploy.yaml':
                return 'Deploy:\n  Webui:\n    WebuiPort: 22288\n'
            return json.dumps({'running_task': ''})
        with patch('tasks.Mentorship.ownership.Path.read_text', read), \
             patch('tasks.Mentorship.ownership.worker_state', AsyncMock(side_effect=[1, 0])), \
             patch('tasks.Mentorship.ownership._worker_action') as action, \
             patch('tasks.Mentorship.ownership.verify_apprentice_idle', side_effect=RuntimeError('busy')), \
             patch('tasks.Mentorship.ownership.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'busy'):
                acquire_apprentice('oas_leveling', 'oas1')
            self.assertEqual([call.args[2] for call in action.call_args_list], ['stop', 'start'])

    def verify(self, states, extra=None):
        configs = {
            'oas_leveling': {'running_task': 'GroupedAwakening',
                             'script': {'device': {'handle': 'pupil', 'serial': 'pupil:1'}}},
            'oas1': {'script': {'device': {'handle': 'mentor', 'serial': 'mentor:1'}}},
        }
        configs.update(extra or {})

        def read(path, **kwargs):
            if path.name == 'deploy.yaml':
                return 'Deploy:\n  Webui:\n    WebuiPort: 22288\n'
            return json.dumps(configs[path.stem])

        async def state(port, name):
            value = states[name]
            if isinstance(value, Exception):
                raise value
            return value

        with patch('tasks.Mentorship.ownership.Path.read_text', read), \
                patch('tasks.Mentorship.ownership.urlopen',
                      return_value=io.StringIO(json.dumps(list(configs)))), \
                patch('tasks.Mentorship.ownership.worker_state', AsyncMock(side_effect=state)) as reader:
            verify_apprentice_idle('oas_leveling', 'oas1')
            return reader

    def test_inactive_worker_with_stale_task_marker_is_allowed(self):
        reader = self.verify({'oas_leveling': 0})
        reader.assert_awaited_once_with(22288, 'oas_leveling')

    def test_active_worker_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError, '仍在运行'):
            self.verify({'oas_leveling': 1})

    def test_same_device_competitor_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError, '仍在运行'):
            self.verify({'oas_leveling': 0, 'other': 1},
                        {'other': {'script': {'device': {'handle': 'pupil'}}}})

    def test_inactive_paired_task_with_stale_marker_is_allowed(self):
        self.verify({'oas_leveling': 0, 'other': 0},
                    {'other': {'running_task': 'TripleAwakening'}})

    def test_unknown_state_is_blocked(self):
        with self.assertRaises(RuntimeError):
            self.verify({'oas_leveling': None})

    def test_unreachable_worker_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError, 'offline'):
            self.verify({'oas_leveling': OSError('offline')})


if __name__ == '__main__':
    unittest.main()
