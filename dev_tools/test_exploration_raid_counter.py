import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from tasks.Exploration.base import BaseExploration
from module.exception import TaskEnd


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

    def test_eye_resume_without_scroll_submission(self):
        self.task.ui_goto = Mock()
        self.task.set_next_run = Mock()
        self.task.O_REALM_RAID_NUMBER1.ocr.return_value = (25, 5, 30)
        from datetime import timedelta
        self.scrolls.scrolls_cd = timedelta(minutes=30)
        options = SimpleNamespace(buff_gold_50_click=False, buff_gold_100_click=False,
                                  buff_exp_50_click=False, buff_exp_100_click=False)
        with self.assertRaises(TaskEnd):
            self.task.activate_realm_raid(self.scrolls, options,
                                         resume_task='EyeExploration', submit_scrolls=False)
        calls = self.task.set_next_run.call_args_list
        self.assertEqual([call.kwargs['task'] for call in calls], ['EyeExploration', 'RealmRaid'])
        self.assertFalse(calls[0].kwargs['server'])

    def test_ordinary_exploration_still_submits_scrolls(self):
        self.task.ui_goto = Mock()
        self.task.set_next_run = Mock()
        self.task.O_REALM_RAID_NUMBER1.ocr.return_value = (25, 5, 30)
        from datetime import timedelta
        self.scrolls.scrolls_cd = timedelta(minutes=30)
        options = SimpleNamespace(buff_gold_50_click=False, buff_gold_100_click=False,
                                  buff_exp_50_click=False, buff_exp_100_click=False)
        with self.assertRaises(TaskEnd):
            self.task.activate_realm_raid(self.scrolls, options)
        self.assertEqual([call.kwargs['task'] for call in self.task.set_next_run.call_args_list],
                         ['Exploration', 'RealmRaid', 'MemoryScrolls'])


if __name__ == '__main__':
    unittest.main()
