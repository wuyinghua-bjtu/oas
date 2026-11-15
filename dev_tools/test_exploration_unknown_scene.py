import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameStuckError
from tasks.Exploration.base import BaseExploration


class UnknownSceneTests(unittest.TestCase):
    def task(self, since=0):
        task = SimpleNamespace(_unknown_scene_since=since, appear=Mock(return_value=False),
                               is_in_prepare=Mock(return_value=False), is_in_battle=Mock(return_value=False),
                               is_in_room=Mock(return_value=False), device=SimpleNamespace(save_screenshot=Mock()))
        for name in ('I_CHECK_EXPLORATION', 'I_E_EXPLORATION_CLICK', 'I_E_SETTINGS_BUTTON',
                     'I_E_AUTO_ROTATE_ON', 'I_E_AUTO_ROTATE_OFF', 'I_CREATE_ENSURE'):
            setattr(task, name, name)
        return task

    @patch('tasks.Exploration.base.time.monotonic', return_value=46)
    def test_unknown_scene_is_bounded(self, clock):
        task = self.task()
        with self.assertRaises(GameStuckError):
            BaseExploration.check_unknown_scene_timeout(task)
        task.device.save_screenshot.assert_called_once()

    @patch('tasks.Exploration.base.time.monotonic', return_value=20)
    def test_transient_unknown_scene_is_allowed(self, clock):
        task = self.task()
        BaseExploration.check_unknown_scene_timeout(task)
        task.device.save_screenshot.assert_not_called()

    def test_recognized_battle_resets_timeout(self):
        task = self.task()
        task.is_in_battle.return_value = True
        BaseExploration.check_unknown_scene_timeout(task)
        self.assertIsNone(task._unknown_scene_since)


if __name__ == '__main__':
    unittest.main()
