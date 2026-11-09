import json
import unittest
from datetime import timedelta
from itertools import chain, repeat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from module.atom.image import RuleImage
from module.exception import TaskEnd
from tasks.KekkaiUtilize.assets import KekkaiUtilizeAssets
from tasks.KekkaiUtilize.script_task import ScriptTask


class FosterTimerTests(unittest.TestCase):
    def setUp(self):
        self.clock = 0
        def advance(seconds):
            self.clock += seconds
        sleeper = patch('tasks.KekkaiUtilize.script_task.time.sleep', side_effect=advance)
        monotonic = patch('tasks.KekkaiUtilize.script_task.time.monotonic',
                          side_effect=lambda: self.clock)
        sleeper.start()
        monotonic.start()
        self.addCleanup(sleeper.stop)
        self.addCleanup(monotonic.stop)

    def task(self, values=()):
        task = object.__new__(ScriptTask)
        task.device = SimpleNamespace(image=object())
        task.screenshot = Mock()
        task.in_shikigami_growth = Mock(return_value=True)
        task.appear = Mock(side_effect=lambda target: target is task.I_RS_RECORDS_SHIKI)
        task.O_UTILIZE_RES_TIME = Mock()
        task.O_UTILIZE_RES_TIME.ocr.side_effect = chain(values, repeat(values[-1] if values else timedelta(0)))
        return task

    def test_right_own_timer_decreases(self):
        remaining = timedelta(hours=2)
        task = self.task([remaining, remaining - timedelta(seconds=3)])
        self.assertEqual(task._verify_foster_timer(), remaining - timedelta(seconds=3))
        self.assertEqual(task.O_UTILIZE_RES_TIME.ocr.call_count, 2)

    def test_empty_own_slot_never_counts_as_active(self):
        task = self.task([timedelta(hours=2)])
        task.appear.side_effect = lambda target: target in (task.I_RS_RECORDS_SHIKI, task.I_UTILIZE_ADD)
        self.assertIsNone(task._verify_foster_timer())
        task.O_UTILIZE_RES_TIME.ocr.assert_not_called()

    def test_non_growth_page_never_counts_as_active(self):
        task = self.task([timedelta(hours=2)])
        task.appear.side_effect = None
        task.appear.return_value = False
        self.assertIsNone(task._verify_foster_timer())
        task.O_UTILIZE_RES_TIME.ocr.assert_not_called()

    def test_missing_timer_has_bounded_resampling(self):
        task = self.task([timedelta(0)])
        self.assertIsNone(task._verify_foster_timer())
        self.assertGreater(task.screenshot.call_count, 0)
        self.assertLessEqual(task.screenshot.call_count, 15)
        self.assertLessEqual(self.clock, 12)

    def test_frozen_increasing_and_implausible_timer_rejected(self):
        for second in (7200, 7201, 7100, 0):
            with self.subTest(second=second):
                task = self.task([timedelta(seconds=7200), timedelta(seconds=second)])
                self.assertIsNone(task._verify_foster_timer())

    def test_own_slot_becomes_empty_between_samples(self):
        task = self.task([timedelta(hours=2)])
        task.appear.side_effect = lambda target: (target is task.I_RS_RECORDS_SHIKI or
                                                 (target is task.I_UTILIZE_ADD and self.clock >= 3))
        self.assertIsNone(task._verify_foster_timer())
        self.assertEqual(task.O_UTILIZE_RES_TIME.ocr.call_count, 1)

    def test_missing_second_ocr_sample_recovers(self):
        task = self.task([timedelta(seconds=7200), timedelta(0), timedelta(seconds=7194)])
        self.assertEqual(task._verify_foster_timer(), timedelta(seconds=7194))
        self.assertEqual(task.O_UTILIZE_RES_TIME.ocr.call_count, 3)

    def test_missing_first_ocr_sample_recovers(self):
        task = self.task([timedelta(0), timedelta(seconds=7200), timedelta(seconds=7197)])
        self.assertEqual(task._verify_foster_timer(), timedelta(seconds=7197))

    def test_missing_page_marker_between_samples_recovers(self):
        task = self.task([timedelta(seconds=7200), timedelta(seconds=7194)])
        task.appear.side_effect = lambda target: target is task.I_RS_RECORDS_SHIKI and self.clock != 3
        self.assertEqual(task._verify_foster_timer(), timedelta(seconds=7194))

    def test_large_ocr_jump_requires_another_consistent_pair(self):
        task = self.task([timedelta(seconds=8000), timedelta(seconds=7200), timedelta(seconds=7197)])
        self.assertEqual(task._verify_foster_timer(), timedelta(seconds=7197))
        self.assertEqual(task.O_UTILIZE_RES_TIME.ocr.call_count, 3)

    def test_unchanged_frame_can_recover_but_is_not_itself_success(self):
        task = self.task([timedelta(seconds=7200), timedelta(seconds=7200), timedelta(seconds=7194)])
        self.assertEqual(task._verify_foster_timer(), timedelta(seconds=7194))
        self.assertEqual(task.O_UTILIZE_RES_TIME.ocr.call_count, 3)

    def test_confirmed_placement_waits_for_loading_plus_to_disappear(self):
        task = self.task([timedelta(seconds=7200), timedelta(seconds=7197)])
        task.appear.side_effect = lambda target: (target is task.I_RS_RECORDS_SHIKI or
                                                 (target is task.I_UTILIZE_ADD and self.clock < 5))
        self.assertEqual(task._verify_foster_timer(confirmed_placement=True), timedelta(seconds=7197))
        self.assertEqual(self.clock, 8)

    def test_unknown_own_state_defers_instead_of_entering_friend_list(self):
        task = self.task()
        task.config = SimpleNamespace(kekkai_utilize=SimpleNamespace(utilize_config=object()))
        task.realm_goto_grown = Mock()
        task._verify_foster_timer = Mock(return_value=None)
        task.device.save_screenshot = Mock()
        task.set_next_run = Mock()
        task.grown_goto_utilize = Mock()
        with self.assertRaises(TaskEnd):
            task.check_utilize_add()
        task.grown_goto_utilize.assert_not_called()
        task.device.save_screenshot.assert_called_once()
        self.assertEqual(task.set_next_run.call_args.kwargs['task'], 'KekkaiUtilize')
        self.assertFalse(task.set_next_run.call_args.kwargs['server'])

    def test_real_empty_own_slot_with_active_incoming_friend(self):
        frame = np.array(Image.open('dev_tools/fixtures/own_foster_empty_incoming_active.png').convert('RGB'))
        source = KekkaiUtilizeAssets.I_UTILIZE_ADD
        rule = RuleImage((1149, 54, 74, 67), source.roi_back,
                         source.method, source.threshold, source.file)
        self.assertTrue(rule.match(frame))
        self.assertEqual(rule.roi_front[:2], [1146, 54])
        task = self.task([timedelta(hours=1, minutes=41, seconds=24)])
        task.device.image = frame
        task.I_UTILIZE_ADD = rule
        task.appear.side_effect = lambda image: image.match(frame)
        self.assertIsNone(task._verify_foster_timer())
        task.O_UTILIZE_RES_TIME.ocr.assert_not_called()

    def test_generator_matches_runtime_and_has_no_incoming_timer(self):
        records = json.loads(Path('tasks/KekkaiUtilize/utilize/image.json').read_text(encoding='utf-8'))
        record = next(row for row in records if row['itemName'] == 'utilize_add')
        self.assertEqual(tuple(map(int, record['roiBack'].split(','))),
                         KekkaiUtilizeAssets.I_UTILIZE_ADD.roi_back)
        records = json.loads(Path('tasks/KekkaiUtilize/utilize/ocr.json').read_text(encoding='utf-8'))
        own_timer = next(row for row in records if row['itemName'] == 'utilize_res_time')
        self.assertEqual(tuple(map(int, own_timer['roiFront'].split(','))), (1140, 117, 100, 30))
        self.assertEqual(tuple(KekkaiUtilizeAssets.O_UTILIZE_RES_TIME.roi), (1140, 117, 100, 30))
        self.assertNotIn('utilize_res_time_middle', [row['itemName'] for row in records])
        self.assertFalse(hasattr(KekkaiUtilizeAssets, 'O_UTILIZE_RES_TIME_MIDDLE'))

    @patch('tasks.KekkaiUtilize.script_task.time.sleep')
    def test_open_own_plus_and_wait_for_friend_list(self, _sleep):
        task = self.task()
        task.appear.side_effect = [True, False, False, False, False, False, True]
        task.appear_then_click = Mock(return_value=True)
        self.assertTrue(task.grown_goto_utilize())
        task.appear_then_click.assert_called_once_with(task.I_UTILIZE_ADD, interval=2)

    @patch('tasks.KekkaiUtilize.script_task.Timer')
    def test_friend_list_timeout_is_not_success(self, timer):
        task = self.task()
        task.appear.side_effect = [True, False, False, False, False]
        timer.return_value.start.return_value.reached.return_value = True
        self.assertFalse(task.grown_goto_utilize())

    def test_real_friend_list_enter_button_detected(self):
        frame = np.array(Image.open('dev_tools/fixtures/own_foster_friend_list.png').convert('RGB'))
        source = KekkaiUtilizeAssets.I_U_ENTER_REALM
        rule = RuleImage((792, 531, 178, 67), source.roi_back,
                         source.method, source.threshold, source.file)
        self.assertTrue(rule.match(frame))
        self.assertEqual(rule.roi_front[:2], [787, 531])

    def test_real_active_own_slot_can_be_read_without_throttled_page_check(self):
        frame = np.array(Image.open('dev_tools/fixtures/own_foster_active.png').convert('RGB'))
        task = self.task([timedelta(hours=5, minutes=59, seconds=37)])
        task.device.image = frame
        task.appear.side_effect = lambda rule: rule.match(frame)
        task.in_shikigami_growth.return_value = False  # A repeated throttled call.
        _, remaining = task._read_active_foster_timer()
        self.assertEqual(remaining, timedelta(hours=5, minutes=59, seconds=37))
        task.in_shikigami_growth.assert_not_called()

    def test_realm_growth_entry_reads_timer_on_same_frame(self):
        task = self.task([timedelta(hours=5)])
        task.in_shikigami_growth.side_effect = [True, False]
        task.realm_goto_grown()
        task.screenshot.assert_called_once()
        task.in_shikigami_growth.assert_called_once()

    @patch('tasks.KekkaiUtilize.script_task.time.sleep')
    @patch('tasks.KekkaiUtilize.script_task.Timer')
    def test_no_more_than_three_entrance_clicks(self, timer, _sleep):
        task = self.task()
        task.appear.side_effect = lambda target, **kwargs: target is task.I_UTILIZE_ADD
        timer.return_value.start.return_value.reached.side_effect = [False] * 8 + [True]
        task.appear_then_click = Mock(return_value=True)
        self.assertFalse(task.grown_goto_utilize())
        self.assertEqual(task.appear_then_click.call_count, 3)


if __name__ == '__main__':
    unittest.main()
