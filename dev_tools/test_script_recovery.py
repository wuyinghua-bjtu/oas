"""Offline regressions for bounded game restart after capture/task failures."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from script import Script


class ScriptRecoveryTests(unittest.TestCase):
    def runner(self, black=False):
        runner = object.__new__(Script)
        runner.config_name = 'test'
        runner.config = Mock()
        runner.device = Mock()
        runner.device.package = 'com.netease.onmyoji'
        runner.device.last_screenshot_black = black
        return runner

    @patch('tasks.Restart.login.LoginHandler')
    def test_restart_logs_in_and_verifies_a_fresh_nonblack_frame(self, handler_cls):
        runner = self.runner(black=False)

        self.assertTrue(runner._restart_game_after_failure('KekkaiActivation'))

        self.assertEqual(runner.device.sleep.call_args_list, [call(10), call(2)])
        runner.device.app_stop.assert_called_once_with()
        runner.device.app_start.assert_called_once_with()
        handler_cls.assert_called_once_with(
            config=runner.config, device=runner.device)
        handler_cls.return_value._app_handle_login.assert_called_once_with()
        runner.device.screenshot.assert_called_once_with()
        runner.config.task_call.assert_not_called()

    @patch('tasks.Restart.login.LoginHandler')
    def test_black_frame_after_restart_is_a_bounded_failure(self, handler_cls):
        runner = self.runner(black=True)

        self.assertFalse(runner._restart_game_after_failure('KekkaiActivation'))

        handler_cls.return_value._app_handle_login.assert_called_once_with()
        runner.device.app_stop.assert_called_once_with()
        runner.device.app_start.assert_called_once_with()
        runner.config.task_call.assert_not_called()

    @patch('tasks.Restart.login.LoginHandler')
    def test_login_exception_does_not_escape_recovery_boundary(self, handler_cls):
        runner = self.runner(black=False)
        handler_cls.return_value._app_handle_login.side_effect = RuntimeError('login failed')

        self.assertFalse(runner._restart_game_after_failure('RyouToppa', 0))

        self.assertEqual(runner.device.sleep.call_args_list, [call(2)])
        runner.device.screenshot.assert_not_called()


class ScriptDeviceRoutingTests(unittest.TestCase):
    def runner(self, enabled=False, active=False):
        runner = object.__new__(Script)
        runner.config_name = 'oas_leveling'
        runner.config = SimpleNamespace(newbie_leveling=SimpleNamespace(
            scheduler=SimpleNamespace(enable=enabled)))
        runner._newbie_leveling_active = active
        return runner

    @patch('tasks.NewbieLeveling.device.LevelingDevice')
    @patch('module.device.device.Device')
    def test_daily_tasks_in_leveling_named_profile_use_normal_device(self, normal, isolated):
        runner = self.runner()
        self.assertIs(runner.device, normal.return_value)
        normal.assert_called_once_with(config=runner.config)
        isolated.assert_not_called()

    @patch('tasks.NewbieLeveling.device.LevelingDevice')
    @patch('module.device.device.Device')
    def test_enabled_leveling_keeps_isolated_device(self, normal, isolated):
        runner = self.runner(enabled=True)
        self.assertIs(runner.device, isolated.return_value)
        normal.assert_not_called()

    @patch('tasks.NewbieLeveling.device.LevelingDevice')
    @patch('module.device.device.Device')
    def test_direct_leveling_keeps_isolated_device(self, normal, isolated):
        runner = self.runner(active=True)
        self.assertIs(runner.device, isolated.return_value)
        normal.assert_not_called()


if __name__ == '__main__':
    unittest.main()
