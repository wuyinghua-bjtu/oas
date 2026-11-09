"""Bind every operation to the verified second MuMu; disallow recovery."""

import psutil
import win32gui
import win32process

from module.device.device import Device
from module.exception import RequestHumanTakeover


class LevelingDevice(Device):
    def _validate_window_binding(self):
        """Read-only Win32 checks; never reselect a new handle mid-session.

        A configured ADB serial does not bind Win32 messages. Check the actual
        render process, its VM argument and live client size before either a
        capture or a click. Reject ambiguous/reused handles instead of falling
        back to another emulator or trusting cached geometry.
        """
        try:
            settings = self.config.script.device
            if (settings.serial != '127.0.0.1:16416' or
                    settings.handle != 'MuMu安卓设备-1' or
                    settings.emulatorinfo_name != 'MuMuPlayer-15.0-1' or
                    settings.screenshot_method != 'window_background' or
                    settings.control_method != 'window_message'):
                raise ValueError('isolated device configuration changed')
            matches = []
            win32gui.EnumWindows(
                lambda hwnd, _: matches.append(hwnd)
                if win32gui.GetWindowText(hwnd) == 'MuMu安卓设备-1' else None, None)
            root = self.root_handle_num
            render = self.screenshot_handle_num
            if matches != [root] or not win32gui.IsWindow(root) or not win32gui.IsWindow(render):
                raise ValueError('second MuMu root is missing, ambiguous or replaced')
            if (win32gui.GetParent(render) != root or
                    win32gui.GetWindowText(render) != 'MuMuNxDevice' or
                    list(self.control_handle_list) != [root, render]):
                raise ValueError('render/control handles no longer belong to the verified root')
            pid = win32process.GetWindowThreadProcessId(root)[1]
            if not pid or win32process.GetWindowThreadProcessId(render)[1] != pid:
                raise ValueError('render process differs from the second MuMu root')
            process = psutil.Process(pid)
            command = process.cmdline()
            if (process.name().lower() != 'mumunxdevice.exe' or
                    command.count('--vm') != 1 or
                    command.index('--vm') + 1 >= len(command) or
                    command[command.index('--vm') + 1] != 'MuMuPlayer-15.0-1'):
                raise ValueError('window process is not the second MuMu VM')
            size = tuple(win32gui.GetClientRect(render))
            if size != (0, 0, 1280, 720):
                raise ValueError('live second MuMu render size must stay 1280x720')
            binding = (pid, process.create_time(), root, render, size)
            previous = getattr(self, '_leveling_window_binding', None)
            if previous is not None and previous != binding:
                raise ValueError('second MuMu process or render was replaced during this run')
            self._leveling_window_binding = binding
        except Exception as exc:
            raise RequestHumanTakeover('NewbieLeveling window binding rejected: ' + str(exc)) from exc

    def screenshot(self):
        self._validate_window_binding()
        return super().screenshot()

    def click(self, *args, **kwargs):
        self._validate_window_binding()
        return super().click(*args, **kwargs)

    def emulator_start(self, *args, **kwargs):
        raise RequestHumanTakeover('Open the second MuMu manually before starting leveling')

    def emulator_stop(self, *args, **kwargs):
        raise RequestHumanTakeover('NewbieLeveling cannot stop either MuMu instance')

    def app_start(self, *args, **kwargs):
        raise RequestHumanTakeover('Log in to the leveling account manually before starting')

    def app_stop(self, *args, **kwargs):
        raise RequestHumanTakeover('NewbieLeveling cannot stop or switch the game session')
