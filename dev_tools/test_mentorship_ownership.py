import io
import json
import unittest
from unittest.mock import AsyncMock, patch

from tasks.Mentorship.ownership import verify_apprentice_idle


class OwnershipTests(unittest.TestCase):
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
