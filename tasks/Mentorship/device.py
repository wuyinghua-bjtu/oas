"""Device bindings for the two-person task; never infer from window order."""
from collections import deque
from module.base.timer import Timer
from module.device.device import Device


class BoundDevice(Device):
    def __init__(self, *args, **kwargs):
        # Device defaults are class attributes. Two simultaneous clients must
        # not share watchdog state or click history.
        self.detect_record = set()
        self.click_record = deque(maxlen=15)
        self.stuck_timer = Timer(60, count=60).start()
        self.stuck_timer_long = Timer(300, count=300).start()
        self._screen_size_checked = False
        super().__init__(*args, **kwargs)


def validate_profiles(mentor, apprentice):
    m = mentor.script.device
    a = apprentice.script.device
    if (m.serial, m.handle, m.emulatorinfo_name) != ('127.0.0.1:16384', 'MuMu安卓设备', 'MuMuPlayer-15.0-0'):
        raise ValueError('师父设备绑定不匹配')
    if (a.serial, a.handle) != ('127.0.0.1:16448', 'MuMu安卓设备-1-1'):
        raise ValueError('徒弟设备绑定不匹配')
    if m.serial == a.serial or m.handle == a.handle:
        raise ValueError('两个角色绑定到同一台设备')
    return True
