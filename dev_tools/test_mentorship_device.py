import unittest
from types import SimpleNamespace as NS
from tasks.Mentorship.device import validate_profiles

def cfg(serial,handle,name):
    return NS(script=NS(device=NS(serial=serial,handle=handle,emulatorinfo_name=name)))

class BindingTests(unittest.TestCase):
    def test_distinct_known_devices(self):
        self.assertTrue(validate_profiles(cfg('127.0.0.1:16384','MuMu安卓设备','MuMuPlayer-15.0-0'),cfg('127.0.0.1:16416','MuMu安卓设备-1','MuMuPlayer-15.0-1')))
    def test_reject_swapped(self):
        with self.assertRaises(ValueError):
            validate_profiles(cfg('127.0.0.1:16416','MuMu安卓设备-1','MuMuPlayer-15.0-1'),cfg('127.0.0.1:16384','MuMu安卓设备','MuMuPlayer-15.0-0'))
if __name__ == '__main__': unittest.main()
