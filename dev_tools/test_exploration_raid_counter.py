import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tasks.Exploration.base import BaseExploration


class ExplorationRaidCounterTest(unittest.TestCase):
    def setUp(self):
        self.task = object.__new__(BaseExploration)
        self.task.device = SimpleNamespace(image=object())
        self.task.appear = Mock(return_value=True)
        self.task.O_REALM_RAID_NUMBER1 = Mock()
        self.task.ui_click_until_disappear = Mock()
        self.task.ui_goto = Mock(side_effect=RuntimeError('raid scheduling reached'))
        self.scrolls = SimpleNamespace(scrolls_enable=True, scrolls_threshold=25)

    def test_invalid_counters_do_not_schedule(self):
        for counter in ((0, 303, 303), (130, -100, 30), (30, 0, 303), (0, 0, 0)):
            with self.subTest(counter=counter):
                self.task.O_REALM_RAID_NUMBER1.ocr.return_value = counter
                self.task.activate_realm_raid(self.scrolls, SimpleNamespace())
                self.task.ui_goto.assert_not_called()

    def test_below_threshold_does_not_schedule(self):
        self.task.O_REALM_RAID_NUMBER1.ocr.return_value = (24, 6, 30)
        self.task.activate_realm_raid(self.scrolls, SimpleNamespace())
        self.task.ui_goto.assert_not_called()

    def test_threshold_and_full_counter_schedule(self):
        for current in (25, 30):
            with self.subTest(current=current):
                self.task.O_REALM_RAID_NUMBER1.ocr.return_value = (current, 30 - current, 30)
                with self.assertRaisesRegex(RuntimeError, 'raid scheduling reached'):
                    self.task.activate_realm_raid(self.scrolls, SimpleNamespace())


if __name__ == '__main__':
    unittest.main()
