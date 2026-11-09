"""Offline regressions for other-device login recovery; never construct Device.

Run from Backend: toolkit/python.exe -m unittest dev_tools.test_remote_login
"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image

from module.atom.image import RuleImage
from module.exception import GameSessionExpiredError, GameStuckError, ScriptError
from script import Script
from tasks.base_task import BaseTask
from tasks.GlobalGame.config_emergency import FriendInvitation
from tasks.Restart.login import LoginHandler


FIXTURE = Path(__file__).parent / 'fixtures' / 'remote_login_dialog.png'
LOGIN_MODULE = 'tasks.Restart.login'


class RemoteLoginImageTests(unittest.TestCase):
    def task(self, frame=None):
        task = object.__new__(BaseTask)
        task.device = Mock()
        task.device.image = (np.array(Image.open(FIXTURE).convert('RGB'))
                             if frame is None else frame)
        task.interval_timer = {}
        task._burst = Mock()
        # Match changes roi_front. Keep class-level asset state isolated.
        for name in ('I_REMOTE_LOGIN_NOTICE', 'I_REMOTE_LOGIN_CONFIRM'):
            source = getattr(task, name)
            setattr(task, name, RuleImage(tuple(source.roi_front),
                    tuple(source.roi_back), source.method,
                    source.threshold, source.file))
        return task

    def assert_confirmed(self, task):
        with self.assertRaises(GameSessionExpiredError):
            task.handle_remote_login_dialog()
        task.device.click.assert_called_once()
        x, y = task.device.click.call_args.args
        left, top, width, height = task.I_REMOTE_LOGIN_CONFIRM.roi_front
        self.assertTrue(left <= x < left + width)
        self.assertTrue(top <= y < top + height)
        self.assertEqual(task.device.click.call_args.kwargs,
                         {'control_name': 'REMOTE_LOGIN_CONFIRM'})

    def test_real_dialog_requires_and_matches_both_templates(self):
        task = self.task()
        self.assertTrue(task.appear(task.I_REMOTE_LOGIN_NOTICE))
        self.assertTrue(task.appear(task.I_REMOTE_LOGIN_CONFIRM))
        self.assert_confirmed(task)

    def test_confirm_button_without_specific_notice_does_not_trigger(self):
        task = self.task()
        task.device.image[285:366, 449:831] = 0
        self.assertTrue(task.appear(task.I_REMOTE_LOGIN_CONFIRM))
        task.handle_remote_login_dialog()
        task.device.click.assert_not_called()
        task.device.save_screenshot.assert_not_called()

    def test_notice_without_confirm_button_does_not_trigger(self):
        task = self.task()
        task.device.image[356:460, 559:727] = 0
        self.assertTrue(task.appear(task.I_REMOTE_LOGIN_NOTICE))
        task.handle_remote_login_dialog()
        task.device.click.assert_not_called()

    def test_small_xy_shift_still_clicks_the_shifted_button(self):
        original = self.task().device.image
        for dx, dy in ((-3, -3), (3, 3), (-3, 3), (3, -3)):
            with self.subTest(dx=dx, dy=dy):
                transform = np.float32([[1, 0, dx], [0, 1, dy]])
                frame = cv2.warpAffine(original, transform, (1280, 720))
                task = self.task(frame)
                self.assert_confirmed(task)
                self.assertEqual(tuple(task.I_REMOTE_LOGIN_CONFIRM.roi_front[:2]),
                                 (575 + dx, 372 + dy))

    def test_black_frame_does_not_trigger(self):
        task = self.task(np.zeros((720, 1280, 3), dtype=np.uint8))
        task.handle_remote_login_dialog()
        task.device.click.assert_not_called()

    def test_public_screenshot_aborts_before_invitation_or_page_actions(self):
        task = self.task()
        with self.assertRaises(GameSessionExpiredError):
            task.screenshot()
        task.device.screenshot.assert_called_once()
        task._burst.assert_not_called()
        task.device.stuck_record_clear.assert_called_once()
        task.device.click_record_clear.assert_called_once()

    def test_normal_frame_still_processes_invitation(self):
        task = self.task(np.zeros((720, 1280, 3), dtype=np.uint8))
        self.assertIs(task.screenshot(), task.device.image)
        task._burst.assert_called_once()
        task.device.click.assert_not_called()

    def test_session_lost_inside_invitation_loop_aborts_invitation(self):
        task = self.task()
        task.config = SimpleNamespace(global_game=SimpleNamespace(
            emergency=SimpleNamespace(friend_invitation=FriendInvitation.ACCEPT)))
        task.device.detect_record = {'BATTLE_STATUS_S'}
        task.set_next_run = Mock()
        real_appear = task.appear

        def appear(target, **kwargs):
            # The first image has an invitation; the next raw Device screenshot
            # is the captured other-device dialog, inside _burst's own loop.
            if task.device.screenshot.call_count == 0 and target is task.I_G_ACCEPT:
                return True
            return real_appear(target, **kwargs)

        task.appear = Mock(side_effect=appear)
        with self.assertRaises(GameSessionExpiredError):
            BaseTask._burst(task)
        task.device.screenshot.assert_called_once()
        task.device.click.assert_called_once()
        self.assertEqual(task.device.click.call_args.kwargs,
                         {'control_name': 'REMOTE_LOGIN_CONFIRM'})
        task.set_next_run.assert_not_called()


class RemoteLoginSchedulerTests(unittest.TestCase):
    def scheduler(self):
        scheduler = object.__new__(Script)
        scheduler.__dict__['config'] = Mock()
        scheduler.__dict__['device'] = Mock()
        scheduler._try_acquire_queue_token = Mock(return_value=True)
        scheduler.instance_guard = None
        scheduler.config_name = 'offline-test'
        scheduler.save_error_log = Mock()
        scheduler.exception_handler = Mock()
        return scheduler

    def interrupted_module(self, events):
        old_task = Mock()

        def interrupted_run():
            events.append('old-task-enter')
            raise GameSessionExpiredError('fixture session expired')
            events.append('old-task-stale-continue')  # pragma: no cover

        old_task.run.side_effect = interrupted_run
        module = SimpleNamespace(ScriptTask=Mock(return_value=old_task))
        return module, old_task

    def test_relogin_requeues_original_task_without_resuming_old_stack(self):
        scheduler = self.scheduler()
        events = []
        module, old_task = self.interrupted_module(events)
        with patch('script.load_module', return_value=module), \
                patch(LOGIN_MODULE + '.LoginHandler') as login_class:
            login_class.return_value.app_handle_login.side_effect = (
                lambda: events.append('relogin-complete'))
            self.assertIs(scheduler.run('KekkaiUtilize'), True)
        self.assertEqual(events, ['old-task-enter', 'relogin-complete'])
        old_task.run.assert_called_once()
        module.ScriptTask.assert_called_once_with(
            config=scheduler.config, device=scheduler.device)
        scheduler.config.task_call.assert_called_once_with(
            'KekkaiUtilize', force_call=False)
        scheduler.device.app_stop.assert_not_called()
        scheduler.device.app_start.assert_not_called()
        scheduler.save_error_log.assert_not_called()

    def test_idle_goto_main_is_not_requeued_as_nonexistent_scheduler_task(self):
        scheduler = self.scheduler()
        module, _ = self.interrupted_module([])

        def reject_auxiliary(command, **kwargs):
            if command == 'GotoMain':
                raise ScriptError('GotoMain has no configured scheduler')

        scheduler.config.task_call.side_effect = reject_auxiliary
        with patch('script.load_module', return_value=module), \
                patch(LOGIN_MODULE + '.LoginHandler'):
            self.assertIs(scheduler.run('GotoMain'), True)
        scheduler.config.task_call.assert_not_called()

    def test_real_login_failure_reaches_outer_recovery_handler(self):
        scheduler = self.scheduler()
        module, _ = self.interrupted_module([])
        with patch('script.load_module', return_value=module), \
                patch(LOGIN_MODULE + '.LoginHandler') as login_class, \
                patch('script.I18n.trans_zh_cn', return_value='test'):
            login_class.return_value.app_handle_login.side_effect = GameStuckError('login stuck')
            self.assertIs(scheduler.run('RyouToppa'), False)
        scheduler.config.task_call.assert_called_once_with('Restart')
        scheduler.save_error_log.assert_called_once()
        scheduler.device.sleep.assert_called_once_with(10)
        scheduler.exception_handler.assert_called_once()


class RemoteLoginLoopTests(unittest.TestCase):
    def login(self):
        login = object.__new__(LoginHandler)
        login.device = Mock()
        login.device.last_screenshot_black = False
        login.config = SimpleNamespace(restart=SimpleNamespace(
            harvest_config=SimpleNamespace(enable=False)))
        login.screenshot = Mock()
        login.appear_then_click = Mock(return_value=False)
        login.ocr_appear_click = Mock(return_value=False)
        login.click = Mock(return_value=False)
        return login

    def test_main_loop_resets_confirmation_and_rechecks_after_session_loss(self):
        login = self.login()
        frame = {'number': 0}
        observations = []

        def screenshot():
            frame['number'] += 1
            if frame['number'] == 2:
                raise GameSessionExpiredError('lost after one courtyard sample')
            if frame['number'] > 5:
                raise AssertionError('login loop did not finish')

        def appear(rule, **kwargs):
            observations.append((frame['number'], rule.name))
            return (frame['number'] in (1, 4, 5) and rule in (
                login.I_BUFF_1, login.I_MAIN_GOTO_SHIKIGAMI_RECORDS))

        login.screenshot.side_effect = screenshot
        login.appear = Mock(side_effect=appear)
        confirm, orientation = Mock(), Mock()
        confirm.start.return_value = confirm
        confirm.reached.side_effect = [False, False, True]
        orientation.reached.return_value = True
        with patch(LOGIN_MODULE + '.Timer', side_effect=[confirm, orientation]), \
                patch(LOGIN_MODULE + '.time.sleep') as sleep:
            self.assertIs(login._app_handle_login(), True)
        confirm.reset.assert_called_once()
        self.assertEqual(frame['number'], 5)
        self.assertFalse(any(number == 2 for number, _ in observations))
        # Frame 2 began with login_success=True; loss must clear it so that
        # orientation is checked again on frames 3 and 4, not only frame 1.
        self.assertEqual(orientation.reached.call_count, 3)
        sleep.assert_called_once_with(5)

    def test_nested_login_actions_retry_without_restarting_game(self):
        login = self.login()
        login._app_handle_login = Mock(side_effect=[
            GameSessionExpiredError('lost in character selection'), True])
        with patch(LOGIN_MODULE + '.time.sleep') as sleep:
            self.assertIs(login.app_handle_login(), True)
        self.assertEqual(login._app_handle_login.call_count, 2)
        sleep.assert_called_once_with(10)
        login.device.app_stop.assert_not_called()
        login.device.app_start.assert_not_called()

    def test_session_loss_during_harvest_reenters_login(self):
        login = self.login()
        login.config.restart.harvest_config.enable = True
        login._app_handle_login = Mock(return_value=True)
        login.harvest = Mock(side_effect=[GameSessionExpiredError('lost during harvest'), None])
        with patch(LOGIN_MODULE + '.time.sleep'):
            self.assertIs(login.app_handle_login(), True)
        self.assertEqual(login._app_handle_login.call_count, 2)
        self.assertEqual(login.harvest.call_count, 2)
        login.device.app_stop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
