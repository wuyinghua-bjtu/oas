"""Offline regression coverage for the September 5 growth-page failures."""

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from module.atom.image import RuleImage
from module.exception import TaskEnd
from tasks.Component.ReplaceShikigami.assets import ReplaceShikigamiAssets
from tasks.KekkaiUtilize.script_task import ScriptTask


FIXTURES = Path(__file__).parent / 'fixtures'
SHIFTED_FRAMES = (
    ('growth_entry_shifted_222436.png', timedelta(hours=3, minutes=33, seconds=20)),
    ('growth_entry_shifted_222635.png', timedelta(hours=3, minutes=31, seconds=20)),
    ('growth_entry_shifted_222836.png', timedelta(hours=3, minutes=29, seconds=20)),
)


class GrowthEntryTests(unittest.TestCase):
    def frame(self, filename):
        with Image.open(FIXTURES / filename) as image:
            return np.array(image.convert('RGB'))

    def records_rule(self, roi_back=None):
        source = ReplaceShikigamiAssets.I_RS_RECORDS_SHIKI
        return RuleImage(
            (1148, 548, 49, 43),
            source.roi_back if roi_back is None else roi_back,
            source.method, source.threshold, source.file,
        )

    def task(self, frame=None):
        task = object.__new__(ScriptTask)
        task.device = Mock()
        task.device.image = frame
        task.I_RS_RECORDS_SHIKI = self.records_rule()
        # A bounded mock makes a reintroduced endless loop fail promptly.
        task.screenshot = Mock(side_effect=[None] * 5 + [AssertionError('Growth entry did not stop')])
        task.appear = Mock(side_effect=lambda rule, **kwargs: rule.match(frame))
        task.appear_then_click_multi_scale = Mock(return_value=False)
        task.O_UTILIZE_RES_TIME = Mock()
        task.set_next_run = Mock()
        return task

    def test_real_failures_reproduce_old_roi_and_match_fixed_roi(self):
        for filename, _remaining in SHIFTED_FRAMES:
            with self.subTest(filename=filename):
                frame = self.frame(filename)
                self.assertFalse(self.records_rule((1145, 548, 55, 90)).match(frame))
                fixed = self.records_rule()
                self.assertTrue(fixed.match(frame))
                self.assertEqual(fixed.roi_front[:2], [1143, 587])
                self.assertEqual(fixed.threshold, 0.8)

    def test_existing_growth_frames_still_match(self):
        for filename in ('own_foster_active.png', 'own_foster_empty_incoming_active.png'):
            with self.subTest(filename=filename):
                self.assertTrue(self.records_rule().match(self.frame(filename)))

    def test_non_growth_frames_do_not_match(self):
        for filename in ('activation_empty_gray.png', 'remote_login_dialog.png'):
            with self.subTest(filename=filename):
                self.assertFalse(self.records_rule().match(self.frame(filename)))

    def test_asset_generator_metadata_matches_runtime(self):
        metadata = Path('tasks/Component/ReplaceShikigami/rs/image.json')
        records = json.loads(metadata.read_text(encoding='utf-8'))
        record = next(item for item in records if item['itemName'] == 'rs_records_shiki')
        rule = self.records_rule()
        self.assertEqual(tuple(map(int, record['roiBack'].split(','))), rule.roi_back)
        self.assertEqual(record['threshold'], rule.threshold)

    def test_real_growth_entry_reaches_own_timer_and_returns(self):
        # Real image matching is retained; OCR is stubbed to the visible OWN
        # timer so this test runs without initializing an OCR engine/device.
        for filename, remaining in SHIFTED_FRAMES:
            with self.subTest(filename=filename):
                task = self.task(self.frame(filename))
                task.O_UTILIZE_RES_TIME.ocr.return_value = remaining
                task.realm_goto_grown()
                task.screenshot.assert_called_once()
                task.O_UTILIZE_RES_TIME.ocr.assert_called_once_with(task.device.image)
                task.appear_then_click_multi_scale.assert_not_called()
                task.set_next_run.assert_not_called()
                self.assertEqual(task.device.mock_calls, [])

    @patch('tasks.KekkaiUtilize.script_task.datetime')
    @patch('tasks.KekkaiUtilize.script_task.Timer')
    def test_timeout_saves_evidence_and_reschedules_current_task(self, timer_class, clock):
        now = datetime(2026, 9, 6, 8, 30, 0)
        clock.now.return_value = now
        for name in ('KekkaiUtilize', 'KekkaiActivation'):
            with self.subTest(name=name):
                timer_class.reset_mock()
                timer = timer_class.return_value
                timer.start.return_value = timer
                timer.reached.return_value = True
                task = self.task()
                task.appear.return_value = False
                task.appear.side_effect = None
                with self.assertRaises(TaskEnd):
                    task.realm_goto_grown(task=name)
                timer_class.assert_called_once_with(20)
                task.set_next_run.assert_called_once_with(
                    task=name, finish=True, server=False, target=now + timedelta(minutes=3))
                task.device.save_screenshot.assert_called_once_with(
                    genre='kekkai_growth_entry', interval=0)
                self.assertEqual(len(task.device.mock_calls), 1)
                task.O_UTILIZE_RES_TIME.ocr.assert_not_called()

    @patch('tasks.KekkaiUtilize.script_task.datetime')
    @patch('tasks.KekkaiUtilize.script_task.Timer')
    def test_repeated_click_matches_cannot_bypass_timeout(self, timer_class, clock):
        now = datetime(2026, 9, 6, 8, 30, 0)
        clock.now.return_value = now
        timer = timer_class.return_value
        timer.start.return_value = timer
        timer.reached.side_effect = [False, False, True]
        task = self.task()
        task.appear.return_value = False
        task.appear.side_effect = None
        task.appear_then_click_multi_scale.return_value = True
        with self.assertRaises(TaskEnd):
            task.realm_goto_grown()
        self.assertEqual(task.appear_then_click_multi_scale.call_count, 2)
        timer.reset.assert_not_called()
        task.set_next_run.assert_called_once_with(
            task='KekkaiUtilize', finish=True, server=False, target=now + timedelta(minutes=3))
        self.assertEqual(len(task.device.mock_calls), 1)

    def test_activation_growth_caller_passes_its_own_task_name(self):
        from tasks.KekkaiActivation.script_task import ScriptTask as ActivationTask

        task = object.__new__(ActivationTask)
        task.realm_goto_grown = Mock(side_effect=TaskEnd)
        with self.assertRaises(TaskEnd):
            task.check_max_lv()
        task.realm_goto_grown.assert_called_once_with(task='KekkaiActivation')


if __name__ == '__main__':
    unittest.main()
