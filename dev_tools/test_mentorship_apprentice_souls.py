import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tasks.Mentorship.apprentice_souls import run_apprentice_souls


class ApprenticeSoulsTests(unittest.TestCase):
    def test_pending_result_stops_before_device_access(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'souls.json'
            path.write_text(json.dumps({'date': '2026-10-31', 'confirmed_wins': 3, 'pending': True}),
                            encoding='utf-8')
            with patch('tasks.Mentorship.apprentice_souls.Path') as mocked_path:
                mocked_path.return_value.__truediv__.return_value.__truediv__.return_value = path
                with patch('tasks.Mentorship.apprentice_souls.OrochiTask') as task:
                    with self.assertRaisesRegex(RuntimeError, '未确认'):
                        run_apprentice_souls(SimpleNamespace(config_name='oas_leveling'), object(),
                                             day=date(2026, 10, 31))
                    task.assert_not_called()

    def test_completed_count_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'souls.json'
            path.write_text(json.dumps({'date': '2026-10-31', 'confirmed_wins': 15, 'pending': False}),
                            encoding='utf-8')
            with patch('tasks.Mentorship.apprentice_souls.Path') as mocked_path:
                mocked_path.return_value.__truediv__.return_value.__truediv__.return_value = path
                with patch('tasks.Mentorship.apprentice_souls.OrochiTask') as task:
                    self.assertEqual(run_apprentice_souls(SimpleNamespace(config_name='oas_leveling'), object(),
                                                           day=date(2026, 10, 31)), 15)
                    task.assert_not_called()


if __name__ == '__main__':
    unittest.main()
