"""Offline regressions for an empty card slot being mistaken for an animation.

No Device or Config is constructed; the real frame is a captured, inert fixture.
Run from Backend: toolkit/python.exe -m unittest dev_tools.test_kekkai_activation
"""
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from module.atom.image import RuleImage
from module.device.control import Control
from module.exception import TaskEnd
from tasks.KekkaiActivation.assets import KekkaiActivationAssets
from tasks.KekkaiActivation.config import CardType
from tasks.KekkaiActivation.script_task import ScriptTask


MODULE = 'tasks.KekkaiActivation.script_task'
FIXTURE = Path(__file__).parent / 'fixtures' / 'activation_empty_gray.png'


class ActivationStateTests(unittest.TestCase):
    def task(self, visible=()):
        task = object.__new__(ScriptTask)
        task.device = SimpleNamespace(image=object(), save_screenshot=Mock())
        task.screenshot = Mock()
        task.appear = Mock(side_effect=lambda rule, **kwargs: rule in visible)
        task.set_next_run = Mock()
        return task

    def frame_task(self):
        task = self.task()
        task.device.image = np.array(Image.open(FIXTURE).convert('RGB'))
        # RuleImage.match updates coordinates; keep tests isolated from class assets.
        for name in dir(KekkaiActivationAssets):
            original = getattr(KekkaiActivationAssets, name)
            if isinstance(original, RuleImage):
                setattr(task, name, RuleImage(tuple(original.roi_front),
                        tuple(original.roi_back), original.method,
                        original.threshold, original.file))
        task.appear.side_effect = lambda rule, **kwargs: rule.match(
            task.device.image, threshold=kwargs.get('threshold'))
        return task

    def test_real_empty_gray_is_not_selected_or_active(self):
        task = self.frame_task()
        self.assertTrue(task.appear(task.I_A_EMPTY))
        self.assertTrue(task.appear(task.I_A_ACTIVATE_GRAY))
        # The broad yellow shape also matches this gray button at its old .8
        # threshold.  The empty-slot signal must take precedence over it.
        self.assertTrue(task.appear(task.I_A_ACTIVATE_YELLOW, threshold=0.8))
        self.assertIs(task.check_card_status(), False)
        self.assertIs(task.check_card_effect(), False)
        task.screenshot.assert_not_called()

    def test_unknown_effect_returns_none_without_taking_more_frames(self):
        task = self.task()
        self.assertIsNone(task.check_card_effect())
        self.assertIsNone(task.check_card_status())
        task.screenshot.assert_not_called()

    def test_real_black_frame_is_unknown_not_a_selected_card(self):
        task = self.frame_task()
        task.device.image = np.zeros_like(task.device.image)
        self.assertIsNone(task.check_card_status())
        self.assertIsNone(task.check_card_effect())
        task.screenshot.assert_not_called()

    def test_page_marker_alone_does_not_prove_card_is_selected(self):
        task = self.task()
        task.appear.side_effect = lambda rule, **kwargs: rule is task.I_A_CHECK_CARD
        self.assertIsNone(task.check_card_status())

    def test_invite_on_card_page_is_active(self):
        task = self.task()
        task.appear.side_effect = lambda rule, **kwargs: rule in (
            task.I_A_CHECK_CARD, task.I_A_INVITE)
        self.assertIs(task.check_card_status(), True)
        self.assertIs(task.check_card_effect(), True)

    def test_selected_yellow_card_is_not_yet_active(self):
        task = self.task()
        task.appear.side_effect = lambda rule, **kwargs: rule in (
            task.I_A_CHECK_CARD, task.I_A_ACTIVATE_YELLOW, task.I_A_DEMOUNT)
        self.assertIs(task.check_card_status(), True)
        self.assertIs(task.check_card_effect(), False)

    @patch(MODULE + '.time.sleep')
    def test_real_empty_slot_reaches_screening_instead_of_waiting(self, _sleep):
        task = self.frame_task()
        task.goto_cards = Mock()
        task.screening_card = Mock(side_effect=TaskEnd('screening reached'))
        task.appear_then_click = Mock(return_value=False)
        task._retry_activation = Mock(side_effect=AssertionError('unexpected retry'))
        with self.assertRaises(TaskEnd):
            task.run_activation(SimpleNamespace(card_type='test-card-type'))
        task.screening_card.assert_called_once_with('test-card-type')
        task.set_next_run.assert_not_called()

    @patch(MODULE + '.time.sleep')
    @patch(MODULE + '.Timer')
    def test_unknown_state_times_out_without_screening(self, timer, _sleep):
        task = self.task()
        task.goto_cards = Mock()
        task.screening_card = Mock()
        task.appear_then_click = Mock(return_value=False)
        task._retry_activation = Mock(side_effect=TaskEnd('bounded retry'))
        timer.return_value.start.return_value.reached.return_value = True
        task.screenshot.side_effect = [None] * 6 + [AssertionError('unbounded loop')]
        with self.assertRaises(TaskEnd):
            task.run_activation(SimpleNamespace(card_type='test-card-type'))
        task.screening_card.assert_not_called()
        task._retry_activation.assert_called_once()

    @patch(MODULE + '.time.sleep')
    @patch(MODULE + '.Timer')
    def test_card_page_entry_times_out_without_restart(self, timer, _sleep):
        task = self.task()
        task.appear_then_click_multi_scale = Mock(return_value=False)
        task._retry_activation = Mock(side_effect=TaskEnd('bounded retry'))
        timer.return_value.start.return_value.reached.return_value = True
        task.screenshot.side_effect = [None] * 6 + [AssertionError('unbounded loop')]
        with self.assertRaises(TaskEnd):
            task.goto_cards()
        task._retry_activation.assert_called_once()

    @patch(MODULE + '.time.sleep')
    @patch(MODULE + '.Timer')
    def test_unconfirmed_activation_times_out_without_success(self, timer, _sleep):
        task = self.task()
        task.goto_cards = Mock()
        task.appear.side_effect = lambda rule, **kwargs: rule in (
            task.I_A_CHECK_CARD, task.I_A_ACTIVATE_YELLOW, task.I_A_DEMOUNT)
        task.appear_then_click = Mock(return_value=False)
        task._schedule_active_card = Mock()
        task._retry_activation = Mock(side_effect=TaskEnd('bounded retry'))
        timer.return_value.start.return_value.reached.return_value = True
        task.screenshot.side_effect = [None] * 6 + [AssertionError('unbounded loop')]
        with self.assertRaises(TaskEnd):
            task.run_activation(SimpleNamespace(card_type='test-card-type'))
        task._schedule_active_card.assert_not_called()
        task.set_next_run.assert_not_called()
        task._retry_activation.assert_called_once()

    def test_retry_saves_evidence_and_schedules_three_minutes(self):
        task = self.task()
        before = datetime.now()
        with self.assertRaises(TaskEnd):
            task._retry_activation('test unknown card state')
        after = datetime.now()
        task.device.save_screenshot.assert_called_once_with(
            genre='kekkai_activation_state', interval=0)
        task.set_next_run.assert_called_once()
        args, kwargs = task.set_next_run.call_args
        self.assertEqual(args, ('KekkaiActivation',))
        self.assertGreaterEqual(kwargs['target'], before + timedelta(minutes=3))
        self.assertLessEqual(kwargs['target'], after + timedelta(minutes=3))

    def test_invalid_ocr_duration_returns_none_not_game_stuck(self):
        for result in (None, timedelta(0), timedelta(seconds=-1), 'bad OCR'):
            with self.subTest(result=result):
                task = self.task()
                task.O_CARD_ALL_TIME = Mock()
                task.O_CARD_ALL_TIME.ocr_duration.return_value = result
                self.assertIsNone(task.ocr_time())

    def test_positive_ocr_duration_is_preserved(self):
        task = self.task()
        task.O_CARD_ALL_TIME = Mock()
        task.O_CARD_ALL_TIME.ocr_duration.return_value = timedelta(hours=6)
        self.assertEqual(task.ocr_time(), timedelta(hours=6))

    @patch(MODULE + '.time.sleep')
    def test_active_timer_must_decrease_before_scheduling(self, _sleep):
        task = self.task()
        task.appear.side_effect = lambda rule, **kwargs: rule is task.I_A_INVITE
        task.ocr_time = Mock(side_effect=[timedelta(hours=6),
                                        timedelta(hours=6, seconds=-3)])
        task._retry_activation = Mock(side_effect=AssertionError('unexpected retry'))
        before = datetime.now()
        task._schedule_active_card()
        after = datetime.now()
        self.assertEqual(task.ocr_time.call_count, 2)
        task.set_next_run.assert_called_once()
        args, kwargs = task.set_next_run.call_args
        self.assertEqual(args, ('KekkaiActivation',))
        remaining = timedelta(hours=6, seconds=-3)
        self.assertGreaterEqual(kwargs['target'], before + remaining)
        self.assertLessEqual(kwargs['target'], after + remaining)
        task._retry_activation.assert_not_called()

    @patch(MODULE + '.time.sleep')
    def test_invalid_timer_pairs_retry_without_success_schedule(self, _sleep):
        for first, second in ((7200, 7200), (7200, 7201), (7200, 7100),
                              (7200, 0), (0, 0), (None, 7197), (7200, None)):
            with self.subTest(first=first, second=second):
                task = self.task()
                task.appear.side_effect = lambda rule, **kwargs: rule is task.I_A_INVITE
                task.ocr_time = Mock(side_effect=[
                    None if first is None else timedelta(seconds=first),
                    None if second is None else timedelta(seconds=second)])
                task._retry_activation = Mock(side_effect=TaskEnd('timer rejected'))
                with self.assertRaises(TaskEnd):
                    task._schedule_active_card()
                task.set_next_run.assert_not_called()
                task._retry_activation.assert_called_once()

    @patch(MODULE + '.time.sleep')
    def test_disappearing_invite_is_not_success(self, _sleep):
        task = self.task()
        task.ocr_time = Mock(side_effect=[timedelta(hours=6),
                                        timedelta(hours=6, seconds=-3)])
        task._retry_activation = Mock(side_effect=TaskEnd('invite missing'))
        task.screenshot.side_effect = lambda: setattr(
            task.appear, 'side_effect', lambda rule, **kwargs: False)
        task.appear.side_effect = lambda rule, **kwargs: rule is task.I_A_INVITE
        with self.assertRaises(TaskEnd):
            task._schedule_active_card()
        task.set_next_run.assert_not_called()
        task._retry_activation.assert_called_once()

    def test_generator_rois_match_runtime_assets(self):
        records = json.loads(Path('tasks/KekkaiActivation/a/image.json').read_text(encoding='utf-8'))
        for name in ('empty', 'activate_gray', 'activate_yellow', 'check_card',
                     'auto_invite', 'card_fish', 'card_kaiko'):
            with self.subTest(name=name):
                record = next(row for row in records if row['itemName'] == 'a_' + name)
                source = getattr(KekkaiActivationAssets, 'I_A_' + name.upper())
                self.assertEqual(tuple(map(int, record['roiBack'].split(','))),
                                 tuple(source.roi_back))

    def card_search_task(self, method):
        task = self.task()
        task.config = SimpleNamespace(
            kekkai_activation=SimpleNamespace(activation_config=SimpleNamespace(
                card_type=CardType.FISH, min_fish_num=16)),
            script=SimpleNamespace(device=SimpleNamespace(control_method=method)))
        task.device.config = task.config
        task.device.handle_control_check = Mock()
        task.device.swipe_window_message = Mock()
        task.device.swipe_adb = Mock(side_effect=AssertionError('ADB is forbidden'))
        task.device.swipe = Mock(side_effect=lambda *args, **kwargs: Control.swipe(
            task.device, *args, **kwargs))
        task.O_CHECK_CARD_NUMBER = Mock()
        task.O_CHECK_CARD_NUMBER.detect_and_ocr.return_value = []
        task._retry_activation = Mock(side_effect=TaskEnd('unsafe swipe rejected'))
        return task

    @patch(MODULE + '.time.sleep')
    def test_no_card_search_uses_window_message_without_tuple_error(self, _sleep):
        task = self.card_search_task('window_message')
        self.assertIsNone(task.check_card_num())
        self.assertEqual(task.O_CHECK_CARD_NUMBER.detect_and_ocr.call_count, 4)
        self.assertEqual(task.device.swipe_window_message.call_count, 3)
        self.assertEqual(task.device.swipe.call_count, 3)
        for call in task.device.swipe.call_args_list:
            self.assertIs(call.kwargs['distance_check'], False)
        task.device.swipe_adb.assert_not_called()
        task._retry_activation.assert_not_called()

    @patch(MODULE + '.time.sleep')
    def test_card_search_rejects_adb_fallback_before_any_swipe(self, _sleep):
        task = self.card_search_task('ADB')
        with self.assertRaises(TaskEnd):
            task.check_card_num()
        task.device.swipe.assert_not_called()
        task.device.swipe_adb.assert_not_called()
        task.device.swipe_window_message.assert_not_called()
        task._retry_activation.assert_called_once()


if __name__ == '__main__':
    unittest.main()
