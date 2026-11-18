import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np

from module.exception import GameStuckError
from tasks.GameUi.assets import GameUiAssets
from tasks.BondlingFairyland.script_task import ScriptTask


class BondlingNavigationTests(unittest.TestCase):
    def test_exploration_anchor_matches_both_bottom_bar_positions(self):
        rule = GameUiAssets.I_CHECK_EXPLORATION
        source = cv2.imread(rule.file)
        self.assertIsNotNone(source)
        source = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
        x, y, width, height = rule.roi_front
        anchor = (source if source.shape[:2] == (height, width)
                  else source[y:y + height, x:x + width])
        for left in (233, 820):
            with self.subTest(left=left):
                image = np.zeros((720, 1280, 3), dtype=np.uint8)
                image[691:691 + height, left:left + width] = anchor
                self.assertTrue(rule.match(image))
        self.assertFalse(rule.match(np.zeros((720, 1280, 3), dtype=np.uint8)))

    def test_failed_navigation_stops_before_battle_preparation(self):
        task = ScriptTask.__new__(ScriptTask)
        task.config = SimpleNamespace(bondling_fairyland=SimpleNamespace(
            bondling_config=SimpleNamespace(check_enable=False)))
        task.switch_soul = Mock()
        task.ui_get_current_page = Mock()
        task.ui_goto = Mock(return_value=False)
        task.goto_ball_area = Mock()
        with self.assertRaisesRegex(GameStuckError, 'before battle preparation'):
            task.run()
        task.goto_ball_area.assert_not_called()


if __name__ == '__main__':
    unittest.main()
