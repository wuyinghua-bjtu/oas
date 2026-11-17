"""Invitation loading regression tests without devices or OCR inference."""
import unittest
import numpy as np
from unittest.mock import Mock, patch

from tasks.TripleAwakening.script_task import Participant, EvoTask, ScriptTask
from tasks.Component.GeneralInvite.config_invite import FindMode


class InviteLoadingTests(unittest.TestCase):
    def test_invitation_requires_complete_identity_and_dungeon(self):
        self.assertTrue(ScriptTask.invitation_verified(
            '邀 test003 觉醒业火轮拾层', 'test003'))
        for text in ('邀 test 觉醒业火轮拾层',
                     '邀 test0030 觉醒业火轮拾层',
                     '邀 test002 觉醒业火轮拾层',
                     '邀 test003 秘闻'):
            with self.subTest(text=text):
                self.assertFalse(ScriptTask.invitation_verified(text, 'test003'))
        self.assertFalse(ScriptTask.invitation_verified('觉醒业火轮拾层', ''))

    @patch('tasks.TripleAwakening.script_task.RuleOcr')
    @patch('tasks.TripleAwakening.script_task.time.sleep')
    @patch('tasks.TripleAwakening.script_task.time.monotonic')
    @patch.object(EvoTask, 'invite_friend', return_value=True)
    def test_refreshes_empty_dialog_before_retry(self, parent, clock, sleep, reader):
        task = self.task()
        clock.side_effect = (0, 0, 1, 13, 13, 13, 13, 14, 15)
        frames = iter(('empty', 'room', 'ready'))
        state = {}
        task.screenshot.side_effect = lambda: state.update(frame=next(frames))
        task.appear.side_effect = lambda rule: (
            rule is task.I_INVITE_ENSURE and state['frame'] != 'room')
        for name in ('O_F_LIST_1', 'O_F_LIST_2', 'O_F_LIST_3', 'O_F_LIST_4'):
            getattr(task, name).ocr.side_effect = lambda image: (
                '好友' if state['frame'] == 'ready' else '')
        reader.return_value.detect_and_ocr.return_value = [Mock(
            ocr_text='取消', box=np.array([[0, 0], [20, 0], [20, 20], [0, 20]]))]
        self.assertTrue(task.invite_friend('test002'))
        task.device.click.assert_called_once_with(430, 545, control_name='triple_refresh_friend_list')
        task.appear_then_click.assert_called_once_with(task.I_ADD_2, interval=2)
        parent.assert_called_once_with('test002', FindMode.AUTO_FIND)

    def task(self):
        task = Participant.__new__(Participant)
        task.device = Mock()
        task.screenshot = Mock()
        task.appear = Mock()
        task.appear_then_click = Mock(return_value=True)
        task._invite_without_category_text = Mock(return_value=False)
        for name in ('I_INVITE_ENSURE', 'I_LOAD_FRIEND', 'I_ADD_1', 'I_ADD_2'):
            setattr(task, name, object())
        for name in ('O_F_LIST_1', 'O_F_LIST_2', 'O_F_LIST_3', 'O_F_LIST_4'):
            setattr(task, name, Mock())
        return task

    @patch('tasks.TripleAwakening.script_task.time.sleep')
    def test_blank_headers_use_verified_tab_and_exact_selected_friend(self, sleep):
        task = self.task()
        task.I_FLAG_1_ON = object()
        task.I_FLAG_1_OFF = object()
        task.I_SELECTED = object()
        task.appear.return_value = True
        task.detect_select = Mock(return_value=True)
        task.click = Mock()
        self.assertTrue(Participant._invite_without_category_text(task, 'test002', FindMode.AUTO_FIND))
        task.detect_select.assert_called_once_with('test002')
        task.click.assert_called_once_with(task.I_INVITE_ENSURE, interval=1)

    @patch('tasks.TripleAwakening.script_task.time.sleep')
    def test_blank_headers_do_not_invite_missing_exact_friend(self, sleep):
        task = self.task()
        task.I_SELECTED = object()
        for index in range(1, 5):
            setattr(task, f'I_FLAG_{index}_ON', object())
            setattr(task, f'I_FLAG_{index}_OFF', object())
        task.appear.return_value = True
        task.detect_select = Mock(return_value=False)
        task.click = Mock()
        self.assertFalse(Participant._invite_without_category_text(task, 'test002', FindMode.AUTO_FIND))
        task.click.assert_not_called()

    @patch('tasks.TripleAwakening.script_task.time.sleep')
    @patch.object(EvoTask, 'invite_friend', return_value=True)
    def test_waits_for_loaded_labels_and_clicks_only_one_add(self, parent, sleep):
        task = self.task()
        frames = iter(('room', 'empty', 'ready'))
        state = {}
        def screenshot():
            state['frame'] = next(frames)
        task.screenshot.side_effect = screenshot
        task.appear.side_effect = lambda rule: (
            rule is task.I_INVITE_ENSURE and state['frame'] != 'room')
        for name in ('O_F_LIST_1', 'O_F_LIST_2', 'O_F_LIST_3', 'O_F_LIST_4'):
            getattr(task, name).ocr.side_effect = lambda image: (
                '好友' if state['frame'] == 'ready' else None)
        self.assertTrue(task.invite_friend('test002'))
        self.assertEqual(task.screenshot.call_count, 3)
        task.appear_then_click.assert_called_once_with(task.I_ADD_2, interval=2)
        parent.assert_called_once_with('test002', FindMode.AUTO_FIND)

    @patch.object(EvoTask, 'invite_friend', return_value=False)
    @patch('tasks.TripleAwakening.script_task.time.sleep')
    def test_preserves_recent_friend_mode_and_parent_result(self, sleep, parent):
        task = self.task()
        task.appear.side_effect = lambda rule: rule is task.I_INVITE_ENSURE
        for name in ('O_F_LIST_1', 'O_F_LIST_2', 'O_F_LIST_3', 'O_F_LIST_4'):
            getattr(task, name).ocr.return_value = '最近'
        self.assertFalse(task.invite_friend('test002', FindMode.RECENT_FRIEND))
        parent.assert_called_once_with('test002', FindMode.RECENT_FRIEND)
        task.appear_then_click.assert_called_once_with(task.I_ADD_2, interval=2)
        task._invite_without_category_text.assert_called_once_with('test002', FindMode.RECENT_FRIEND)

    @patch.object(EvoTask, 'invite_friend', return_value=False)
    @patch('tasks.TripleAwakening.script_task.time.sleep')
    def test_partial_headers_fall_back_to_physical_tabs(self, sleep, parent):
        task = self.task()
        task.appear.side_effect = lambda rule: rule is task.I_INVITE_ENSURE
        for index, label in enumerate(('', '最近', '', ''), 1):
            getattr(task, f'O_F_LIST_{index}').ocr.return_value = label
        task._invite_without_category_text.return_value = True
        self.assertTrue(task.invite_friend('test002', FindMode.AUTO_FIND))
        parent.assert_called_once_with('test002', FindMode.AUTO_FIND)
        task._invite_without_category_text.assert_called_once_with('test002', FindMode.AUTO_FIND)
