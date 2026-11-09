import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from tasks.Mentorship.buff_device import MasterBuffs, _locate_row


class Device:
    image = np.zeros((720, 1280, 3), np.uint8)
    def __init__(self): self.clicks = []
    def screenshot(self): pass
    def click(self, *args, **kwargs): self.clicks.append(args)
    def swipe(self, *args, **kwargs): pass


class BuffTests(unittest.TestCase):
    def test_distinguishes_50_and_100(self):
        box = np.array([[10,10], [120,10], [120,30], [10,30]])
        rule = SimpleNamespace(keyword='战斗胜利获得的经验增加50%', roi=(400,100,340,400),
                               detect_and_ocr=lambda _: [SimpleNamespace(ocr_text='战斗胜利获得的经验增加100%', box=box)])
        self.assertIsNone(_locate_row(Device.image, rule))
        rule.detect_and_ocr = lambda _: [SimpleNamespace(ocr_text=rule.keyword, box=box)]
        self.assertIsNotNone(_locate_row(Device.image, rule))

    def test_does_not_toggle_unknown_buff(self):
        device = Device()
        with patch.object(MasterBuffs, '_panel', return_value=True):
            self.assertFalse(MasterBuffs(device).set('unknown', True, timeout=.01))
        self.assertEqual(device.clicks, [])


if __name__ == '__main__': unittest.main()
