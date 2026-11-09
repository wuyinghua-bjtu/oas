"""Offline post-login navigation regressions; never create a real Device."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.exception import GameSessionExpiredError, GameStuckError
from tasks.Restart.login import LoginHandler


MODULE = 'tasks.Restart.login'


class Clock:
    def __init__(self):
        self.value = 1000.0

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class HarvestNavigationTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        for target, effect in (
                (MODULE + '.time.monotonic', self.clock.now),
                (MODULE + '.time.sleep', self.clock.sleep),
                ('module.base.timer.time.time', self.clock.now)):
            patcher = patch(target, side_effect=effect)
            patcher.start()
            self.addCleanup(patcher.stop)

    def task(self, button=lambda frame: True, main=lambda frame: False):
        task = object.__new__(LoginHandler)
        task.device = Mock()
        task.frame = 0
        task._harvest_close_count = 0
        task.click = Mock()

        def screenshot():
            task.frame += 1
            self.clock.sleep(0.2)
            if task.frame > 1000:
                self.fail('harvest did not respect its bounded deadline')

        task.screenshot = Mock(side_effect=screenshot)

        def appear(rule, **kwargs):
            if rule is task.I_LOGIN_YELLOW_CLOSE:
                self.assertNotIn('interval', kwargs)
                return button(task.frame)
            if rule in (task.I_BUFF_1, task.I_MAIN_GOTO_SHIKIGAMI_RECORDS):
                return main(task.frame)
            return False

        task.appear = Mock(side_effect=appear)
        task.appear_then_click = Mock(return_value=False)
        task.ui_reward_appear_click = Mock(return_value=False)
        task.config = SimpleNamespace(restart=SimpleNamespace(
            harvest_config=SimpleNamespace(enable=True,
                enable_courtyard_affairs=False, enable_mail=False)))
        return task

    def test_unchanged_back_button_stops_after_three_attempts_with_evidence(self):
        task = self.task()
        with self.assertRaisesRegex(GameStuckError, 'did not change'):
            task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE)
        self.assertEqual(task.click.call_count, 3)
        self.assertGreaterEqual(self.clock.value - 1000, 12)
        task.device.save_screenshot.assert_called_once_with(
            genre='login_harvest_navigation', interval=0)
        task.device.click_record_clear.assert_not_called()
        task.device.app_start.assert_not_called()

    def test_success_waits_for_two_fresh_absent_samples_after_click(self):
        task = self.task(button=lambda frame: frame < 2)
        self.assertTrue(task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE))
        task.click.assert_called_once_with(task.I_LOGIN_YELLOW_CLOSE)
        self.assertEqual(task.frame, 3)
        task.device.save_screenshot.assert_not_called()

    def test_one_missing_frame_does_not_confirm_exit_or_reset_retry_budget(self):
        task = self.task(button=lambda frame: frame % 2 == 0 or frame == 1)
        with self.assertRaises(GameStuckError):
            task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE)
        self.assertEqual(task.click.call_count, 3)

    def test_transient_first_frame_is_not_clicked(self):
        task = self.task(button=lambda frame: frame == 0)
        self.assertTrue(task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE))
        task.click.assert_not_called()

    def test_courtyard_dual_markers_prevent_generic_back_false_positive(self):
        task = self.task(main=lambda frame: True)
        self.assertFalse(task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE))
        task.click.assert_not_called()

    def test_full_harvest_budget_covers_disappearing_and_reappearing_buttons(self):
        task = self.task(button=lambda frame: frame % 4 in (0, 1))
        for _ in range(6):
            self.assertTrue(task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE))
            task.screenshot()  # New overlay or false positive reappears.
        with self.assertRaisesRegex(GameStuckError, 'budget exhausted'):
            task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE)
        self.assertEqual(task.click.call_count, 6)
        task.device.click_record_clear.assert_not_called()

    def test_remote_login_interrupt_during_confirmation_propagates(self):
        task = self.task()
        task.screenshot.side_effect = GameSessionExpiredError('remote login')
        with self.assertRaises(GameSessionExpiredError):
            task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE)
        task.click.assert_not_called()
        task.device.app_stop.assert_not_called()

    def test_remote_login_interrupt_after_click_is_not_swallowed(self):
        task = self.task()
        task.screenshot.side_effect = [None, GameSessionExpiredError('remote login')]
        with self.assertRaises(GameSessionExpiredError):
            task._harvest_close_overlay(task.I_LOGIN_YELLOW_CLOSE)
        task.click.assert_called_once()
        task.device.save_screenshot.assert_not_called()

    def test_no_rewards_on_unknown_page_is_not_success(self):
        task = self.task(button=lambda frame: False)
        with self.assertRaisesRegex(GameStuckError, 'within 120s'):
            task.harvest()
        task.click.assert_not_called()
        task.device.save_screenshot.assert_called_once()

    def login_task(self, courtyard=lambda frame: True):
        task = self.task()
        task.device.last_screenshot_black = False
        task.device.click_record = []

        def appear(rule, **kwargs):
            if rule in (task.I_BUFF_1, task.I_MAIN_GOTO_SHIKIGAMI_RECORDS):
                # Reproduce the interval gate: only every other fast frame
                # passes, which must never be used as a page-presence check.
                return courtyard(task.frame) and (
                    not kwargs.get('interval') or task.frame % 2 == 0)
            return False

        task.appear = Mock(side_effect=appear)
        task.ocr_appear_click = Mock(return_value=False)
        return task

    def test_login_continuous_courtyard_confirms_without_throttled_observations(self):
        task = self.login_task()
        self.assertTrue(task._app_handle_login())
        self.assertLess(task.frame, 30)
        for call in task.appear.call_args_list:
            if call.args[0] in (task.I_BUFF_1, task.I_MAIN_GOTO_SHIKIGAMI_RECORDS,
                                task.I_CHECK_MAIN):
                self.assertNotIn('interval', call.kwargs)
        task.click.assert_not_called()
        task.device.app_stop.assert_not_called()
        task.device.app_start.assert_not_called()

    def test_login_one_courtyard_frame_is_not_success(self):
        task = self.login_task(courtyard=lambda frame: frame == 1)
        with self.assertRaisesRegex(GameStuckError, 'server list'):
            task._app_handle_login()
        task.click.assert_not_called()
        task.device.app_stop.assert_not_called()

    def test_login_session_loss_resets_courtyard_confirmation(self):
        task = self.login_task()
        capture = task.screenshot.side_effect

        def screenshot():
            capture()
            if task.frame == 3:
                raise GameSessionExpiredError('remote login')

        task.screenshot.side_effect = screenshot
        self.assertTrue(task._app_handle_login())
        self.assertGreater(task.frame, 10)
        task.device.app_stop.assert_not_called()

    def test_harvest_exits_only_after_two_courtyard_samples(self):
        task = self.task(button=lambda frame: False, main=lambda frame: True)
        task.harvest()
        observations = [call for call in task.appear.call_args_list
                        if call.args[0] is task.I_MAIN_GOTO_SHIKIGAMI_RECORDS]
        self.assertEqual(len(observations), 2)
        task.click.assert_not_called()
        task.device.save_screenshot.assert_not_called()

    def test_single_courtyard_sample_followed_by_unknown_does_not_exit(self):
        task = self.task(button=lambda frame: False)
        task._harvest_main_visible = Mock(side_effect=[True, False] + [False] * 1000)
        with self.assertRaises(GameStuckError):
            task.harvest()
        self.assertGreater(task._harvest_main_visible.call_count, 2)


if __name__ == '__main__':
    unittest.main()
