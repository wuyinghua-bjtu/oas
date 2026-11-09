"""Offline window-binding regression tests; never construct/connect a Device.

Run with toolkit/python.exe -m unittest dev_tools.test_newbie_leveling_device_binding.
Every native-window/process API and every underlying screenshot/click is mocked.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from module.device.device import Device
from module.exception import RequestHumanTakeover
from tasks.NewbieLeveling import device as device_module
from tasks.NewbieLeveling.device import LevelingDevice


class NewbieDeviceBindingTests(unittest.TestCase):
    ROOT = 101
    RENDER = 102
    FIRST = 201
    PID = 4242
    TITLE = 'MuMu安卓设备-1'
    VM = 'MuMuPlayer-15.0-1'

    def setUp(self):
        self.device = object.__new__(LevelingDevice)
        # Seed cached properties directly, without invoking their native getters.
        self.device.__dict__.update(
            root_handle_num=self.ROOT,
            root_handle_title=self.TITLE,
            screenshot_handle_num=self.RENDER,
            control_handle_list=[self.ROOT, self.RENDER],
            screenshot_size=(1280, 720),
        )
        self.device.serial = '127.0.0.1:16416'
        self.device.config = SimpleNamespace(script=SimpleNamespace(
            device=SimpleNamespace(
                serial='127.0.0.1:16416', handle=self.TITLE,
                emulatorinfo_name=self.VM, package_name='com.netease.onmyoji',
                screenshot_method='window_background',
                control_method='window_message', adb_restart=False,
            )))
        self.windows = [self.ROOT, self.FIRST]
        self.titles = {self.ROOT: self.TITLE, self.RENDER: 'MuMuNxDevice',
                       self.FIRST: 'MuMu安卓设备'}
        self.parents = {self.ROOT: 0, self.RENDER: self.ROOT, self.FIRST: 0}
        self.pids = {self.ROOT: self.PID, self.RENDER: self.PID, self.FIRST: 9999}
        self.rects = {self.ROOT: (0, 0, 1280, 765),
                      self.RENDER: (0, 0, 1280, 720)}
        self.process = Mock()
        self.process.name.return_value = 'MuMuNxDevice.exe'
        self.process.cmdline.return_value = [
            r'C:\Program Files\Netease\MuMu\nx_device\MuMuNxDevice.exe',
            '--vm', self.VM,
        ]
        self.process.create_time.return_value = 12345.0
        self.gui = Mock()
        self.gui.EnumWindows.side_effect = self._enum_windows
        self.gui.GetWindowText.side_effect = lambda hwnd: self.titles.get(hwnd, '')
        self.gui.IsWindow.side_effect = lambda hwnd: hwnd in self.titles
        self.gui.GetParent.side_effect = lambda hwnd: self.parents.get(hwnd, 0)
        self.gui.GetClientRect.side_effect = lambda hwnd: self.rects[hwnd]
        self.process_api = Mock()
        self.process_api.GetWindowThreadProcessId.side_effect = (
            lambda hwnd: (77, self.pids[hwnd]))
        self.psutil = Mock()
        self.psutil.Process.return_value = self.process
        for name, value in (('win32gui', self.gui),
                            ('win32process', self.process_api),
                            ('psutil', self.psutil)):
            patcher = patch.object(device_module, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _enum_windows(self, callback, extra):
        for hwnd in self.windows:
            callback(hwnd, extra)

    def guard(self):
        self.device._validate_window_binding()

    def assert_rejected(self):
        with self.assertRaises(RequestHumanTakeover):
            self.guard()

    def test_valid_binding_is_pinned_and_revalidated_on_every_call(self):
        self.guard()
        initial = self.device._leveling_window_binding
        self.assertIsInstance(initial, tuple)
        self.guard()
        self.assertEqual(self.device._leveling_window_binding, initial)
        self.assertEqual(self.gui.EnumWindows.call_count, 2)
        self.assertEqual(self.gui.GetClientRect.call_count, 2)
        self.assertEqual(self.process.create_time.call_count, 2)

    def test_missing_exact_title_never_selects_first_instance(self):
        self.windows = [self.FIRST]
        self.assert_rejected()

    def test_duplicate_exact_titles_are_ambiguous(self):
        self.titles[self.FIRST] = self.TITLE
        self.assert_rejected()

    def test_substring_title_is_not_an_exact_match(self):
        self.titles[self.ROOT] = self.TITLE + ' - copied'
        self.assert_rejected()

    def test_cached_root_must_equal_unique_title_match(self):
        self.device.root_handle_num = self.FIRST
        self.assert_rejected()

    def test_invalid_root_handle_is_rejected(self):
        self.gui.IsWindow.side_effect = lambda hwnd: hwnd != self.ROOT
        self.assert_rejected()

    def test_invalid_render_handle_is_rejected(self):
        self.gui.IsWindow.side_effect = lambda hwnd: hwnd != self.RENDER
        self.assert_rejected()

    def test_render_must_be_direct_child_not_first_instances_child(self):
        self.parents[self.RENDER] = self.FIRST
        self.assert_rejected()

    def test_render_must_have_exact_mumu_render_title(self):
        self.titles[self.RENDER] = 'MuMuPlayer'
        self.assert_rejected()

    def test_control_targets_must_be_exact_root_and_render_pair(self):
        for handles in ([], [self.ROOT], [self.RENDER, self.ROOT],
                        [self.FIRST, self.RENDER],
                        [self.ROOT, self.FIRST],
                        [self.ROOT, self.RENDER, self.FIRST]):
            with self.subTest(handles=handles):
                self.device.control_handle_list = handles
                self.assert_rejected()

    def test_root_and_render_must_belong_to_same_process(self):
        self.pids[self.RENDER] = 9999
        self.assert_rejected()

    def test_process_name_must_be_mumu_device_not_main_or_unrelated_app(self):
        for name in ('MuMuNxMain.exe', 'notepad.exe', 'MuMuNxDevice.exe.bak'):
            with self.subTest(name=name):
                self.process.name.return_value = name
                self.assert_rejected()

    def test_vm_option_must_be_unique_complete_and_exact(self):
        for arguments in (
                [], ['--vm'], ['--vm', 'MuMuPlayer-15.0-0'],
                ['--vm', self.VM + '-copy'], ['--vm=' + self.VM],
                ['--other', self.VM],
                ['--vm', self.VM, '--vm', self.VM],
                ['--vm', self.VM, '--vm', 'MuMuPlayer-15.0-0']):
            with self.subTest(arguments=arguments):
                self.process.cmdline.return_value = ['MuMuNxDevice.exe'] + arguments
                self.assert_rejected()

    def test_vm_flag_with_other_unrelated_flags_is_accepted(self):
        self.process.cmdline.return_value = [
            'MuMuNxDevice.exe', '--renderer', 'vulkan', '--vm', self.VM,
            '--user-data', r'C:\non-sensitive-test-directory']
        self.guard()

    def test_render_client_rect_must_remain_native_1280_by_720(self):
        for rect in ((0, 0, 1050, 591), (0, 0, 720, 1280),
                     (1, 0, 1281, 720), (0, 0, 1280, 719), (0, 0, 0, 0)):
            with self.subTest(rect=rect):
                self.rects[self.RENDER] = rect
                self.assert_rejected()

    def test_live_resize_is_rejected_despite_cached_screenshot_shape(self):
        self.guard()
        self.rects[self.RENDER] = (0, 0, 1050, 591)
        self.assertEqual(self.device.screenshot_size, (1280, 720))
        self.assert_rejected()

    def test_process_restart_with_reused_pid_is_rejected(self):
        self.guard()
        original = self.device._leveling_window_binding
        self.process.create_time.return_value = 12346.0
        self.assert_rejected()
        self.assertEqual(self.device._leveling_window_binding, original)

    def test_process_change_is_rejected_even_with_same_title_and_vm(self):
        self.guard()
        self.pids[self.ROOT] = self.pids[self.RENDER] = 4343
        self.assert_rejected()

    def test_recreated_root_is_not_silently_rebound(self):
        self.guard()
        new_root = 301
        self.windows = [new_root, self.FIRST]
        self.titles[new_root] = self.TITLE
        self.titles[self.ROOT] = 'old root'
        self.parents[self.RENDER] = new_root
        self.pids[new_root] = self.PID
        self.device.root_handle_num = new_root
        self.device.control_handle_list = [new_root, self.RENDER]
        self.assert_rejected()

    def test_recreated_render_is_not_silently_rebound(self):
        self.guard()
        new_render = 302
        self.titles[new_render] = 'MuMuNxDevice'
        self.parents[new_render] = self.ROOT
        self.pids[new_render] = self.PID
        self.rects[new_render] = (0, 0, 1280, 720)
        self.device.screenshot_handle_num = new_render
        self.device.control_handle_list = [self.ROOT, new_render]
        self.assert_rejected()

    def test_native_and_process_errors_are_normalized_to_human_takeover(self):
        for api in (self.gui.EnumWindows, self.gui.GetWindowText,
                    self.gui.IsWindow, self.gui.GetParent, self.gui.GetClientRect,
                    self.process_api.GetWindowThreadProcessId,
                    self.psutil.Process, self.process.name, self.process.cmdline,
                    self.process.create_time):
            with self.subTest(api=api):
                original = api.side_effect
                api.side_effect = OSError('offline mock API failure')
                try:
                    self.assert_rejected()
                finally:
                    api.side_effect = original

    def test_screenshot_validates_before_underlying_capture(self):
        events = []
        with patch.object(self.device, '_validate_window_binding',
                          side_effect=lambda: events.append('guard')) as guard, \
                patch.object(Device, 'screenshot',
                             side_effect=lambda: events.append('capture')) as capture:
            self.device.screenshot()
        self.assertEqual(events, ['guard', 'capture'])
        guard.assert_called_once_with()
        capture.assert_called_once_with()

    def test_failed_screenshot_guard_prevents_capture(self):
        with patch.object(self.device, '_validate_window_binding',
                          side_effect=RequestHumanTakeover('wrong window')), \
                patch.object(Device, 'screenshot') as capture:
            with self.assertRaises(RequestHumanTakeover):
                self.device.screenshot()
        capture.assert_not_called()

    def test_click_validates_before_underlying_control(self):
        events = []
        with patch.object(self.device, '_validate_window_binding',
                          side_effect=lambda: events.append('guard')) as guard, \
                patch.object(Device, 'click',
                             side_effect=lambda *args, **kwargs: events.append('click')) as click:
            self.device.click(640, 360, control_name='NEWBIE_OFFLINE_TEST')
        self.assertEqual(events, ['guard', 'click'])
        guard.assert_called_once_with()
        click.assert_called_once()
        self.assertEqual(click.call_args.args[:2], (640, 360))
        self.assertEqual(click.call_args.kwargs['control_name'], 'NEWBIE_OFFLINE_TEST')

    def test_failed_click_guard_prevents_all_control(self):
        with patch.object(self.device, '_validate_window_binding',
                          side_effect=RequestHumanTakeover('wrong window')), \
                patch.object(Device, 'click') as click:
            with self.assertRaises(RequestHumanTakeover):
                self.device.click(640, 360)
        click.assert_not_called()

    def test_screenshot_method_drift_cannot_use_default_adb_fallback(self):
        for method in ('ADB', 'auto', 'uiautomator2', 'typo'):
            with self.subTest(method=method):
                self.device.config.script.device.screenshot_method = method
                with patch.object(Device, 'screenshot') as capture:
                    with self.assertRaises(RequestHumanTakeover):
                        self.device.screenshot()
                capture.assert_not_called()

    def test_control_method_drift_cannot_use_default_adb_fallback(self):
        for method in ('ADB', 'auto', 'uiautomator2', 'typo'):
            with self.subTest(method=method):
                self.device.config.script.device.control_method = method
                with patch.object(Device, 'click') as click:
                    with self.assertRaises(RequestHumanTakeover):
                        self.device.click(640, 360)
                click.assert_not_called()

    def test_click_rejects_wrong_screenshot_method_too(self):
        self.device.config.script.device.screenshot_method = 'ADB'
        with patch.object(Device, 'click') as click:
            with self.assertRaises(RequestHumanTakeover):
                self.device.click(640, 360)
        click.assert_not_called()

    def test_emulator_and_app_recovery_remain_forbidden(self):
        for name in ('emulator_start', 'emulator_stop', 'app_start', 'app_stop'):
            with self.subTest(method=name), patch.object(Device, name) as underlying:
                with self.assertRaises(RequestHumanTakeover):
                    getattr(self.device, name)()
                underlying.assert_not_called()


if __name__ == '__main__':
    unittest.main()
