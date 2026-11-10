"""Explicit bindings for the two additional team windows; no app recovery."""
import psutil
import win32gui
import win32process
import win32con
import time
from module.device.device import Device
from module.exception import RequestHumanTakeover


class TeamDevice(Device):
    def __init__(self, config, expected):
        self.expected = expected
        self.binding = None
        super().__init__(config)

    def validate(self):
        info = self.expected
        root, render = self.root_handle_num, self.screenshot_handle_num
        matches = []
        win32gui.EnumWindows(lambda h, _: matches.append(h)
                            if win32gui.GetWindowText(h) == info['name'] else None, None)
        if matches != [root] or not win32gui.IsWindow(render):
            raise RequestHumanTakeover('Team window missing or ambiguous: ' + info['name'])
        if win32gui.GetParent(render) != root or win32gui.GetWindowText(render) != 'MuMuNxDevice':
            raise RequestHumanTakeover('Team render belongs to a different window')
        pid = win32process.GetWindowThreadProcessId(root)[1]
        if pid != info['pid'] or win32process.GetWindowThreadProcessId(render)[1] != pid:
            raise RequestHumanTakeover('Team window process changed')
        process = psutil.Process(pid)
        args = process.cmdline()
        if process.name().lower() != 'mumunxdevice.exe' or '--vm' not in args:
            raise RequestHumanTakeover('Unexpected team emulator process')
        vm = args[args.index('--vm') + 1]
        if vm != self.config.script.device.emulatorinfo_name:
            raise RequestHumanTakeover('Team VM does not match configured device')
        rect = win32gui.GetClientRect(render)
        if tuple(rect) != (0, 0, 1280, 720):
            width, height = rect[2], rect[3]
            # MuMu may shrink an otherwise identical 16:9 render during
            # a transition. Restore it after verifying the window and process.
            if (640 <= width <= 1280 and 360 <= height <= 720
                    and abs(width / height - 16 / 9) < .015
                    and not win32gui.IsIconic(root)):
                left, top, right, bottom = win32gui.GetWindowRect(root)
                win32gui.SetWindowPos(root, 0, 0, 0,
                                      right - left + 1280 - width,
                                      bottom - top + 720 - height,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
                time.sleep(.5)
            if tuple(win32gui.GetClientRect(render)) != (0, 0, 1280, 720):
                raise RequestHumanTakeover(info['name'] + ': keep render size 1280x720')
        binding = (pid, process.create_time(), root, render)
        if self.binding is not None and binding != self.binding:
            raise RequestHumanTakeover('Team window replaced during task')
        self.binding = binding

    def screenshot(self):
        self.validate()
        return super().screenshot()

    def click(self, *args, **kwargs):
        self.validate()
        return super().click(*args, **kwargs)

    def swipe(self, *args, **kwargs):
        self.validate()
        return super().swipe(*args, **kwargs)

    def long_click(self, *args, **kwargs):
        self.validate()
        return super().long_click(*args, **kwargs)

    def emulator_start(self, *args, **kwargs):
        raise RequestHumanTakeover('Open the three emulators manually')

    def emulator_stop(self, *args, **kwargs):
        raise RequestHumanTakeover('Team task cannot stop emulators')

    def app_start(self, *args, **kwargs):
        raise RequestHumanTakeover('Log into the three games manually')

    def app_stop(self, *args, **kwargs):
        raise RequestHumanTakeover('Team task cannot restart games')
