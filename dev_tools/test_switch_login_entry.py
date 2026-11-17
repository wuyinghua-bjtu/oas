"""Offline SDK-transition checks; no real device is created."""
import unittest
from unittest.mock import Mock, patch

from module.exception import GameSessionExpiredError
from tasks.Component.SwitchAccount.login_account import LoginAccount


class LoginEntryTests(unittest.TestCase):
    def task(self, visible):
        task = object.__new__(LoginAccount)
        task.frame = 0
        task.device = Mock()
        def screenshot():
            task.frame += 1
        task.screenshot = Mock(side_effect=screenshot)
        task.appear = Mock(side_effect=lambda rule: visible(task.frame, rule, task))
        return task

    def test_user_center_is_a_valid_resume_entry(self):
        task = self.task(lambda frame, rule, t: rule is t.I_SA_SWITCH_ACCOUNT_BTN)
        self.assertTrue(task.wait_for_login_entry())
        self.assertEqual(task.frame, 1)

    def test_transition_waits_for_fresh_login_frame(self):
        task = self.task(lambda frame, rule, t: frame >= 3 and rule is t.I_CHECK_LOGIN_FORM)
        with patch('tasks.Component.SwitchAccount.login_account.time.sleep'):
            self.assertTrue(task.wait_for_login_entry())
        self.assertEqual(task.frame, 3)

    def test_unknown_page_has_a_finite_deadline_and_no_clicks(self):
        task = self.task(lambda *args: False)
        with patch('tasks.Component.SwitchAccount.login_account.time.monotonic', side_effect=[0, 0, 1, 3]), \
                patch('tasks.Component.SwitchAccount.login_account.time.sleep'):
            self.assertFalse(task.wait_for_login_entry(timeout=2))
        self.assertEqual(task.frame, 2)
        task.device.click.assert_not_called()
        task.device.app_stop.assert_not_called()
        task.device.app_start.assert_not_called()

    def test_remote_login_interrupt_is_preserved(self):
        task = self.task(lambda *args: False)
        task.screenshot.side_effect = GameSessionExpiredError('remote login')
        with self.assertRaises(GameSessionExpiredError):
            task.wait_for_login_entry()


if __name__ == '__main__':
    unittest.main()
