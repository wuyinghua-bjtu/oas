import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tasks.EyeAwakening.script_task import ScriptTask, BACK


class Eye3RecoveryTest(unittest.TestCase):
    def recover(self, profile, screen):
        task = object.__new__(ScriptTask)
        task.config = SimpleNamespace(config_name=profile)
        task.screenshot = Mock()
        task.click = Mock()
        task.dismiss_activity_story = Mock(return_value=False)
        task.try_close_unknown_page = Mock()
        task.map_visible = Mock(return_value=screen == 'map')
        main_checks = iter((False, True))

        def appear(asset):
            if asset is task.I_CHECK_MAIN:
                return next(main_checks)
            return asset is getattr(task, screen, None)

        task.appear = Mock(side_effect=appear)
        with patch('tasks.EyeAwakening.script_task.time.sleep'):
            task.leave_inventory()
        return task

    def test_eye3_reward_is_dismissed(self):
        task = self.recover('oas_eye_3', 'I_REWARD')
        task.click.assert_called_once_with(task.C_REWARD_1, interval=1)

    def test_eye3_map_returns_safely(self):
        task = self.recover('oas_eye_3', 'map')
        task.click.assert_called_once_with(BACK, interval=1.5)

    def test_other_profiles_keep_existing_recovery(self):
        task = self.recover('oas_eye_2', 'I_REWARD')
        task.click.assert_not_called()
        task.try_close_unknown_page.assert_called_once_with(skip_screenshot=True)

    def test_unknown_eye3_page_is_not_clicked(self):
        task = self.recover('oas_eye_3', 'unknown')
        task.click.assert_not_called()
        task.try_close_unknown_page.assert_called_once_with(skip_screenshot=True)


if __name__ == '__main__':
    unittest.main()
