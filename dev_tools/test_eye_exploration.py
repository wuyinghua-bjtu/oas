import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch

from module.exception import GameStuckError
from tasks.EyeAwakening.progress import ProgressUncertain
from tasks.EyeExploration.script_task import ScriptTask
from tasks.Exploration.base import Scene


class EyeExplorationTest(unittest.TestCase):
    def setUp(self):
        self.task = object.__new__(ScriptTask)
        self.task.device = NS(image=object())
        self.task.screenshot = lambda: None
        self.task.map_visible = lambda: True
        self.task.entry = {}
        self.task.save_state = lambda: None
        self.task.progress_current = 49
        self.task.minions_cnt = 1
        self.task.start_time = datetime.now()
        self.task.limit_time = timedelta(hours=2)
        self.task.original_config = NS(model=NS(eye_exploration=NS(options=NS(max_battles=5))))
        self.task.stop_reason = None

    def test_map_cap_stops_only_at_fifty(self):
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress', return_value=50):
            self.assertTrue(self.task.check_exit())
        self.assertEqual(self.task.stop_reason, '完成')
        self.assertEqual(self.task.entry['progress'], 50)

    def test_no_drop_keeps_farming(self):
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress', return_value=49):
            self.assertFalse(self.task.check_exit())
        self.assertIsNone(self.task.stop_reason)

    def test_chapter_entry_uses_last_confirmed_progress(self):
        self.task.map_visible = lambda: False
        self.task.appear = lambda rule: rule is self.task.I_E_EXPLORATION_CLICK
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress') as read_map:
            self.assertFalse(self.task.check_exit())
        read_map.assert_not_called()

    def test_battle_limit_is_not_reported_as_cap(self):
        self.task.minions_cnt = 5
        with patch('tasks.EyeExploration.script_task.EyeAwakeningTask.map_progress', return_value=49):
            self.assertTrue(self.task.check_exit())
        self.assertEqual(self.task.stop_reason, '战斗次数上限')

    def test_reward_counter_requires_two_reads_before_click(self):
        phase = {'done': False, 'calls': 0}
        self.task.screenshot = lambda: None
        self.task.appear = lambda rule: not phase['done'] and rule is self.task.I_REWARD
        self.task.get_current_scene = lambda: Scene.MAIN if phase['done'] else Scene.UNKNOWN
        def click(*args, **kwargs):
            self.assertGreaterEqual(phase['calls'], 2)
            phase['done'] = True
        self.task.click = click
        def reward(image):
            phase['calls'] += 1
            return (50, 50)
        with patch('tasks.EyeExploration.script_task.read_drop_popup_quota', side_effect=ProgressUncertain()), \
             patch('tasks.EyeExploration.script_task.read_reward_quota', side_effect=reward), \
             patch('tasks.EyeExploration.script_task.time.sleep'):
            self.assertTrue(self.task.finish_battle_settlement(True))
        self.assertEqual(self.task.progress_current, 50)

    def test_failure_never_claims_success(self):
        with self.assertRaises(GameStuckError):
            self.task.finish_battle_settlement(False)


if __name__ == '__main__':
    unittest.main()
